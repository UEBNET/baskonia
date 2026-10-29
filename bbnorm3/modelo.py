"""CVAE jerárquica de normalización cruzada (v3).

Notación (docs/normalizacion_v3_cvae.md §2): persona-temporada (i, t) con latente ABSOLUTO u_it ∈ ℝ^K; competición-
temporada c = (l, t) con nivel μ_c ∈ ℝ^K y escala s_l > 0. Posición RELATIVA del jugador en su competición:
    r = (u_it − μ_c) / s_l
  * Prior por nivel:  u_it ~ N(μ_c*, s_l*² I)  (c* = competición con más minutos de esa persona-temporada).
  * Entre temporadas: u_{i,t+1} − u_it − d(edad) ~ N(0, η² I)  (término de prior, campo aleatorio gaussiano).
  * Jerarquía de μ:   μ_{l,t} − μ_{l,t−1} ~ N(0, κ² I) (paseo aleatorio); media de la liga ~ N(μ_escalón, τ² I);
                      μ_escalón ~ N(0, sd_escalon² I).
  * Gauge: Σ_c w_c μ_c = 0 y Σ_l w_l log s_l = 0 (w ∝ filas). Ninguna liga está fijada a 0: «liga X = 0» es sólo
    una reparametrización de la salida.
  * Codificador amortizado q(r | y, máscara, v, liga, pos) por fila → experto gaussiano diagonal; las filas de una
    misma persona-temporada se combinan por producto de expertos (así entran los jugadores puente) junto con el prior.
  * Decodificador: ŷ_r = b_{l,t,p} + T_{equipo-temporada} + L r + (W2 + V_l) · [γ_l ⊙ tanh(W1 r + c1) + β_l]
    con FiLM por liga (γ_l, β_l) y cabezal residual por liga V_l contraídos hacia la red común, y efecto
    equipo-temporada aleatorio T ~ N(0, σ²_T,m) (σ²_T por bayes empírico).
  * Factor específico (unicidad) persona × métrica: ζ_{i,m} ~ N(0, ω²_m), común a todas las filas de la persona
    (todas sus ligas y temporadas). Recoge la parte de cada métrica que el latente común no explica (p. ej. el TL%
    propio de un tirador) y viaja con el jugador al traducirlo. ω² por bayes empírico (EM).
  * Verosimilitud heterocedástica: y_{r,m} ~ N(ŷ_{r,m} + ζ_{i,m}, v_{r,m} + ψ_{l,m}) con v conocido (σ²/n).
  * Selección: cada persona-temporada pesa w (IPW del logit de «ser puente»; 1 para quien no es puente).
  * Consistencia de ciclo: codificar(decodificar_b(r)) ≈ r para una liga b al azar (penalización).

Se ajusta por máxima ELBO (Adam, lote completo, una muestra por paso) con semilla fija.
"""
from __future__ import annotations

import math

import numpy as np
import torch
from torch import nn

from .datos import Datos


def _t(x, dtype=torch.float32):
    return torch.as_tensor(np.array(x), dtype=dtype)


class CVAE(nn.Module):
    def __init__(self, D: Datos, cfg: dict, semilla: int):
        super().__init__()
        torch.manual_seed(semilla)
        np.random.seed(semilla % (2 ** 32))
        self.cfg = cfg
        K = int(cfg["latente"]["K"])
        H = int(cfg["red"]["oculta_decodificador"])
        He = int(cfg["red"]["oculta_codificador"])
        N, Mm = D.Y.shape
        self.K, self.H, self.Mm = K, H, Mm
        self.nL, self.nC, self.nG, self.nE, self.nPS = len(D.ligas), len(D.comps), len(D.grupos), len(D.equipos), len(D.ps)
        self.nT = len(D.tramos)
        # --- datos como tensores (lote completo)
        self.register_buffer("Y", _t(D.Y)); self.register_buffer("Mk", _t(D.M)); self.register_buffer("V", _t(D.V))
        for k in ("liga", "comp", "grupo", "equipo", "ps", "pos", "persona_id"):
            self.register_buffer(f"i_{k}", _t(D.idx[k], torch.long))
        self.register_buffer("ps_comp", _t(D.ps_comp_principal, torch.long))
        self.register_buffer("ps_tramo", _t(D.ps_tramo, torch.long))
        self.register_buffer("tr", _t(D.transiciones, torch.long).reshape(-1, 2))
        self.register_buffer("w_ps", _t(D.peso_ps))
        self.register_buffer("w_prior", _t(D.peso_prior))
        self.register_buffer("comp_liga", _t(D.comp_liga, torch.long))
        self.register_buffer("comp_anio", _t(D.comp_anio, torch.long))
        self.register_buffer("logmin", _t(np.log(np.clip(D.t["min"].to_numpy(float), 1, None)) / 7.0))
        filas_comp = np.bincount(D.idx["comp"], minlength=self.nC).astype(float)
        filas_liga = np.bincount(D.idx["liga"], minlength=self.nL).astype(float)
        self.register_buffer("w_comp", _t(filas_comp / filas_comp.sum()))
        self.register_buffer("w_liga", _t(filas_liga / filas_liga.sum()))
        # paseo aleatorio: pares (c_prev, c) de la misma liga en temporadas consecutivas con datos
        pares = []
        for l in range(self.nL):
            cs = sorted(np.where(D.comp_liga == l)[0], key=lambda c: D.comp_anio[c])
            pares += list(zip(cs[:-1], cs[1:]))
        self.register_buffer("rw", _t(np.array(pares, np.int64).reshape(-1, 2), torch.long))
        esc_nombres = sorted(set(D.escalon_de_liga.get(l, l) for l in D.ligas))
        self.register_buffer("liga_esc", _t([esc_nombres.index(D.escalon_de_liga.get(l, l)) for l in D.ligas], torch.long))
        self.nEsc = len(esc_nombres)
        self.esc_nombres = esc_nombres
        # --- codificador: [y·M, M, log v·M, liga, pos, log min] → (media, log precisión) de r
        din = 3 * Mm + self.nL + 3 + 1
        self.enc = nn.Sequential(nn.Linear(din, He), nn.SiLU(), nn.Linear(He, He), nn.SiLU(), nn.Linear(He, 2 * K))
        # --- decodificador
        self.W1 = nn.Linear(K, H)
        self.W2 = nn.Linear(H, Mm, bias=False)
        self.Lin = nn.Linear(K, Mm, bias=False)
        self.film_g = nn.Parameter(torch.zeros(self.nL, H))
        self.film_b = nn.Parameter(torch.zeros(self.nL, H))
        self.Vl = nn.Parameter(torch.zeros(self.nL, Mm, H))
        bG = np.zeros((self.nG, Mm), np.float32)
        num = np.zeros((self.nG, Mm)); den = np.zeros((self.nG, Mm))
        np.add.at(num, D.idx["grupo"], D.Y * D.M); np.add.at(den, D.idx["grupo"], D.M)
        bG[:] = num / np.maximum(den, 1)
        self.bG = nn.Parameter(_t(bG))
        self.T = nn.Parameter(torch.zeros(self.nE, Mm))
        self.register_buffer("s2T", torch.full((Mm,), 0.05))
        self.nPer = len(D.personas)
        self.usar_unicidad = bool(cfg["red"].get("unicidad", False))
        self.Z = nn.Parameter(torch.zeros(self.nPer, Mm))
        self.register_buffer("s2Z", torch.full((Mm,), 0.05))
        self.log_psi = nn.Parameter(torch.full((self.nL, Mm), math.log(0.2)))
        # --- niveles y escalas
        self.mu_raw = nn.Parameter(torch.zeros(self.nC, K))
        self.mu_esc = nn.Parameter(torch.zeros(self.nEsc, K))
        self.ls_raw = nn.Parameter(torch.zeros(self.nL))
        self.drift = nn.Parameter(torch.zeros(self.nT, K))
        # liga destino del término de ciclo: para cada grupo (l, t, p), los grupos de otras ligas en la misma t y p
        g_info = [g.split("|") for g in D.grupos]
        por_tp = {}
        for gi, (l, t_, p) in enumerate(g_info):
            por_tp.setdefault((t_, p), []).append(gi)
        alt = np.full((self.nG, self.nL), -1, np.int64)
        for (t_, p), gs in por_tp.items():
            for g in gs:
                for h in gs:
                    alt[g, D.ligas.index(g_info[h][0])] = h
        self.register_buffer("grupo_alt", _t(alt, torch.long))
        self.register_buffer("grupo_liga", _t([D.ligas.index(x[0]) for x in g_info], torch.long))
        self.register_buffer("grupo_pos", _t([["E", "A", "I"].index(x[2]) for x in g_info], torch.long))

    # ------------------------------------------------------------------------------------------ piezas
    def mu(self):
        """Niveles con el gauge Σ w_c μ_c = 0."""
        return self.mu_raw - (self.w_comp[:, None] * self.mu_raw).sum(0, keepdim=True)

    def log_s(self):
        return self.ls_raw - (self.w_liga * self.ls_raw).sum()

    def codificar(self, Y, Mk, V, liga, pos, logmin):
        x = torch.cat([Y * Mk, Mk, torch.log(V + 1e-3) * Mk, nn.functional.one_hot(liga, self.nL).float(),
                       nn.functional.one_hot(pos, 3).float(), logmin[:, None]], 1)
        o = self.enc(x)
        m, lp = o[:, :self.K], o[:, self.K:].clamp(-6, 8)
        return m, lp

    def decodificar(self, r, liga, grupo, equipo=None):
        h = torch.tanh(self.W1(r))
        h = h * (1 + self.film_g[liga]) + self.film_b[liga]
        # cabezal residual por liga: h · V_lᵀ para todas las ligas a la vez y se toma el bloque de la liga de la fila
        todas = (h @ self.Vl.reshape(self.nL * self.Mm, self.H).T).view(-1, self.nL, self.Mm)
        out = self.bG[grupo] + self.Lin(r) + self.W2(h) + todas[torch.arange(len(h)), liga]
        if equipo is not None:
            out = out + self.T[equipo]
        return out

    def posterior_ps(self, m, lp, mu, s):
        """Producto de expertos por persona-temporada (en coordenadas absolutas u) con el prior N(μ_c*, s*²)."""
        sl = s[self.i_liga][:, None]
        prec = torch.exp(lp) / sl ** 2
        media = mu[self.i_comp] + sl * m
        c_star = self.ps_comp
        s_star = s[self.comp_liga[c_star]][:, None]
        wp = self.w_prior[:, None]
        P = torch.zeros(self.nPS, self.K).index_add_(0, self.i_ps, prec) + wp / s_star ** 2
        eta = torch.zeros(self.nPS, self.K).index_add_(0, self.i_ps, prec * media) + wp * mu[c_star] / s_star ** 2
        return eta / P, 1.0 / P

    # ------------------------------------------------------------------------------------------ ELBO
    def perdida(self, ciclo: bool = True):
        c = self.cfg
        mu, ls = self.mu(), self.log_s()
        s = torch.exp(ls)
        m, lp = self.codificar(self.Y, self.Mk, self.V, self.i_liga, self.i_pos, self.logmin)
        mq, Sq = self.posterior_ps(m, lp, mu, s)
        u = mq + torch.sqrt(Sq) * torch.randn_like(mq)
        sl = s[self.i_liga][:, None]
        r = (u[self.i_ps] - mu[self.i_comp]) / sl
        yhat = self.decodificar(r, self.i_liga, self.i_grupo, self.i_equipo)
        if self.usar_unicidad:
            yhat = yhat + self.Z[self.i_persona_id]
        var = self.V + torch.exp(self.log_psi[self.i_liga]) + c["red"]["psi_minimo"]
        ll_f = -0.5 * (self.Mk * (torch.log(2 * math.pi * var) + (self.Y - yhat) ** 2 / var)).sum(1)
        w = self.w_ps
        rec = (w[self.i_ps] * ll_f).sum()
        # prior por nivel y entropía de q
        c_star = self.ps_comp
        s_star = s[self.comp_liga[c_star]][:, None]
        lprior = self.w_prior * (-0.5 * (((mq - mu[c_star]) ** 2 + Sq) / s_star ** 2).sum(1) - self.K * torch.log(s_star[:, 0]))
        ent = 0.5 * torch.log(Sq).sum(1)
        kl = (w * (lprior + ent)).sum()
        # transiciones entre temporadas
        eta2 = c["prior"]["eta"] ** 2
        a, b = self.tr[:, 0], self.tr[:, 1]
        d = self.drift[self.ps_tramo[a]]
        ltr = -0.5 / eta2 * ((mq[b] - mq[a] - d) ** 2 + Sq[a] + Sq[b]).sum()
        # jerarquía de los niveles
        pen = 0.0
        if len(self.rw):
            pen = pen + 0.5 / c["prior"]["kappa"] ** 2 * ((mu[self.rw[:, 1]] - mu[self.rw[:, 0]]) ** 2).sum()
        mu_liga = torch.zeros(self.nL, self.K).index_add_(0, self.comp_liga, mu)
        n_liga = torch.zeros(self.nL).index_add_(0, self.comp_liga, torch.ones(self.nC))
        mu_liga = mu_liga / n_liga[:, None]
        pen = pen + 0.5 / c["prior"]["tau"] ** 2 * ((mu_liga - self.mu_esc[self.liga_esc]) ** 2).sum()
        pen = pen + 0.5 / c["prior"]["sd_escalon"] ** 2 * (self.mu_esc ** 2).sum()
        pen = pen + 0.5 / c["prior"]["sd_log_escala"] ** 2 * (ls ** 2).sum()
        # contracción de la red por liga y del efecto equipo
        pen = pen + 0.5 / c["red"]["sd_film"] ** 2 * ((self.film_g ** 2).sum() + (self.film_b ** 2).sum())
        pen = pen + 0.5 / c["red"]["sd_cabezal_liga"] ** 2 * (self.Vl ** 2).sum()
        pen = pen + 0.5 * ((self.T ** 2) / self.s2T).sum()
        if self.usar_unicidad:
            pen = pen + 0.5 * ((self.Z ** 2) / self.s2Z).sum()
        wd = c["red"]["decaimiento_pesos"]
        pen = pen + wd * sum((p ** 2).sum() for n_, p in self.named_parameters()
                             if n_.startswith(("enc.", "W1", "W2", "Lin")) and p.dim() > 1)
        # consistencia de ciclo: codificar(decodificar_b(r)) ≈ r
        cyc = torch.zeros(())
        if ciclo and c["entrenamiento"]["ciclo_peso"] > 0:
            n = min(int(c["entrenamiento"]["ciclo_filas"]), len(r))
            sel = torch.randint(0, len(r), (n,))
            g = self.i_grupo[sel]
            lb = torch.randint(0, self.nL, (n,))
            gb = self.grupo_alt[g, lb]
            ok = gb >= 0
            if ok.any():
                rr, gb = r[sel][ok].detach(), gb[ok]
                lb, pb = self.grupo_liga[gb], self.grupo_pos[gb]
                yb = self.decodificar(rr, lb, gb)
                ones = torch.ones_like(yb)
                vb = torch.full_like(yb, 0.02)
                mb, _ = self.codificar(yb, ones, vb, lb, pb, self.logmin[sel][ok])
                cyc = ((mb - rr) ** 2).sum(1).mean()
        elbo = rec + kl + ltr
        N = float(len(self.Y))
        total = -(elbo - pen) / N + c["entrenamiento"]["ciclo_peso"] * cyc
        return total, {"elbo_fila": float(elbo / N), "rec_fila": float(rec / N), "ciclo": float(cyc)}

    @torch.no_grad()
    def precision_unicidad(self) -> torch.Tensor:
        """Σ_r M/var de cada persona y métrica (precisión de los datos sobre ζ)."""
        var = self.V + torch.exp(self.log_psi[self.i_liga]) + self.cfg["red"]["psi_minimo"]
        return torch.zeros(self.nPer, self.Mm).index_add_(0, self.i_persona_id, self.Mk / var)

    @torch.no_grad()
    def actualizar_s2T(self):
        """Bayes empírico de la varianza del efecto equipo-temporada y, con EM, de la unicidad ω²."""
        self.s2T.copy_(torch.clamp((self.T ** 2).mean(0), min=self.cfg["red"]["s2_equipo_minimo"]))
        if self.usar_unicidad:
            P = self.precision_unicidad()
            vpost = 1.0 / (P + 1.0 / self.s2Z)
            con = P > 0
            num = ((self.Z ** 2 + vpost) * con).sum(0)
            self.s2Z.copy_(torch.clamp(num / con.sum(0).clamp(min=1), min=1e-3))


def entrenar(D: Datos, cfg: dict, semilla: int, progreso=print) -> CVAE:
    torch.set_num_threads(max(1, torch.get_num_threads()))
    modelo = CVAE(D, cfg, semilla)
    e = cfg["entrenamiento"]
    opt = torch.optim.Adam(modelo.parameters(), lr=e["lr"])
    pasos = int(e["pasos"])
    gamma = (e["lr_final"] / e["lr"]) ** (1.0 / max(pasos, 1))
    sch = torch.optim.lr_scheduler.ExponentialLR(opt, gamma)
    for paso in range(pasos):
        opt.zero_grad()
        loss, info = modelo.perdida(ciclo=True)
        loss.backward()
        nn.utils.clip_grad_norm_(modelo.parameters(), 50.0)
        opt.step(); sch.step()
        if paso % 50 == 49:
            modelo.actualizar_s2T()
        if progreso and (paso % 250 == 0 or paso == pasos - 1):
            progreso(f"    semilla {semilla} paso {paso:5d}  pérdida {float(loss):.4f}  ELBO/fila {info['elbo_fila']:.3f}"
                     f"  ciclo {info['ciclo']:.4f}")
    modelo.eval()
    return modelo
