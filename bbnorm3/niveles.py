"""Posterior conjunta de los niveles μ_c y de los latentes u_it (campo aleatorio gaussiano).

Con el codificador y el decodificador ya entrenados, cada fila r aporta un «experto» gaussiano sobre su posición
relativa r = (u − μ_c)/s_l (media m_r, precisión P_r, diagonales). Junto con el prior por nivel, las transiciones
entre temporadas y la jerarquía de μ, todo es lineal-gaussiano en x = (u, μ, μ_escalón), y como todas las
precisiones son diagonales en las K dimensiones, el sistema se separa en K sistemas dispersos independientes:

    Q_k x_k = b_k,   Q_k = Σ_potenciales w · a aᵀ,   b_k = Σ w · a · objetivo

  * fila r:        a = e_u(ps) − e_μ(c),  objetivo = s_l m_rk,  w = w_ps · P_rk / s_l²
  * prior nivel:   a = e_u(ps) − e_μ(c*), objetivo = 0,          w = w_ps · w_prior / s_l*²
  * transición:    a = e_u(b) − e_u(a),   objetivo = d_k(edad),  w = 1/η²
  * paseo:         a = e_μ(c) − e_μ(c'),  objetivo = 0,          w = 1/κ²
  * escalón:       a = media_t e_μ(l,t) − e_esc, objetivo = 0,   w = 1/τ²;  e_esc con w = 1/sd_escalon²

La posterior es exacta dado el modelo de medida: la media y la COVARIANZA CONJUNTA de todos los μ_c salen de Q⁻¹
(Σ_aa, Σ_bb y Σ_ab de cualquier par), y la varianza de una traducción usa Var(δ_b − δ_a) = Σ_aa + Σ_bb − 2Σ_ab
en vez de sumar varianzas marginales. El gauge (Σ w_c μ_c = 0) se aplica al final proyectando: μ ← P μ, Σ ← P Σ Pᵀ.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
import torch

from .datos import Datos
from .modelo import CVAE


@dataclass
class Posterior:
    nPS: int
    nC: int
    nEsc: int
    media: np.ndarray            # (n_var, K)
    lu: list                     # factorizaciones por dimensión
    s: np.ndarray                # escala por liga
    drift: np.ndarray            # (tramos, K)

    def iu(self, ps):
        return np.asarray(ps)

    def imu(self, c):
        return self.nPS + np.asarray(c)

    def var_contraste(self, a: np.ndarray) -> np.ndarray:
        """aᵀ Q_k⁻¹ a para cada dimensión k (a: vector disperso denso de longitud n_var)."""
        return np.array([float(a @ f.solve(a)) for f in self.lu])

    def cov_mu(self) -> np.ndarray:
        """Covarianza conjunta de los μ_c (K × nC × nC), sin gauge."""
        n = self.media.shape[0]
        E = np.zeros((n, self.nC))
        E[self.nPS + np.arange(self.nC), np.arange(self.nC)] = 1.0
        out = []
        for f in self.lu:
            X = f.solve(E)
            out.append(X[self.nPS:self.nPS + self.nC, :])
        return np.stack(out)


@torch.no_grad()
def expertos(modelo: CVAE) -> tuple[np.ndarray, np.ndarray]:
    m, lp = modelo.codificar(modelo.Y, modelo.Mk, modelo.V, modelo.i_liga, modelo.i_pos, modelo.logmin)
    return m.numpy().astype(float), np.exp(lp.numpy().astype(float))


def expertos_refinados(modelo: CVAE, pasos: int, lr: float = 0.05, sd_previa: float = 2.0):
    """Inferencia semi-amortizada: parte del codificador y optimiza r de cada fila con el decodificador congelado
    (máxima verosimilitud con una previa débil N(0, sd_previa²)), y aproxima la verosimilitud por Laplace con
    Gauss-Newton diagonal: precisión H_kk = Σ_m M/var · (∂ŷ_m/∂r_k)² y media r* + H⁻¹ r*/sd_previa² (se quita la
    previa débil para que el experto sea sólo verosimilitud, como en el producto de expertos)."""
    with torch.no_grad():
        m0, _ = modelo.codificar(modelo.Y, modelo.Mk, modelo.V, modelo.i_liga, modelo.i_pos, modelo.logmin)
        var = modelo.V + torch.exp(modelo.log_psi[modelo.i_liga]) + modelo.cfg["red"]["psi_minimo"]
    r = m0.clone().requires_grad_(True)
    opt = torch.optim.Adam([r], lr=lr)
    for _ in range(pasos):
        opt.zero_grad()
        yhat = modelo.decodificar(r, modelo.i_liga, modelo.i_grupo, modelo.i_equipo)
        if modelo.usar_unicidad:
            yhat = yhat + modelo.Z[modelo.i_persona_id].detach()
        loss = (0.5 * modelo.Mk * (modelo.Y - yhat) ** 2 / var).sum() + 0.5 * (r ** 2).sum() / sd_previa ** 2
        loss.backward()
        opt.step()
    with torch.no_grad():
        r = r.detach()
        base = modelo.decodificar(r, modelo.i_liga, modelo.i_grupo, modelo.i_equipo)
        h = 1e-3
        H = torch.zeros_like(r)
        for k in range(r.shape[1]):
            e = torch.zeros_like(r); e[:, k] = h
            d = (modelo.decodificar(r + e, modelo.i_liga, modelo.i_grupo, modelo.i_equipo) - base) / h
            H[:, k] = (modelo.Mk * d ** 2 / var).sum(1)
        H = H.clamp(min=1e-3)
        media = r + r / sd_previa ** 2 / H
    return media.numpy().astype(float), H.numpy().astype(float)


@torch.no_grad()
def posterior(modelo: CVAE, D: Datos, cfg: dict) -> Posterior:
    pasos = int(cfg.get("inferencia", {}).get("refinar_pasos", 0))
    if pasos > 0:
        with torch.enable_grad():
            m, P = expertos_refinados(modelo, pasos)
    else:
        m, P = expertos(modelo)
    s = torch.exp(modelo.log_s()).numpy().astype(float)
    drift = modelo.drift.numpy().astype(float)
    K = m.shape[1]
    nPS, nC, nEsc = modelo.nPS, modelo.nC, modelo.nEsc
    n = nPS + nC + nEsc
    w_ps = D.peso_ps
    il, ic, ips = D.idx["liga"], D.idx["comp"], D.idx["ps"]
    pr = cfg["prior"]
    # potenciales w·(ca·x_i + cb·x_j − objetivo)²: (i, j, ca, cb, w (n, K), objetivo (n, K))
    pots = []
    sl = s[il]
    pots.append((ips, nPS + ic, 1.0, -1.0, w_ps[ips][:, None] * P / sl[:, None] ** 2, sl[:, None] * m))
    cst = D.ps_comp_principal
    s_star = s[D.comp_liga[cst]]
    pots.append((np.arange(nPS), nPS + cst, 1.0, -1.0, np.repeat((w_ps * D.peso_prior / s_star ** 2)[:, None], K, 1),
                 np.zeros((nPS, K))))
    if len(D.transiciones):
        a, bb = D.transiciones[:, 0], D.transiciones[:, 1]
        pots.append((bb, a, 1.0, -1.0, np.full((len(a), K), 1.0 / pr["eta"] ** 2), drift[D.ps_tramo[a]]))
    rw = modelo.rw.numpy()
    if len(rw):
        pots.append((nPS + rw[:, 1], nPS + rw[:, 0], 1.0, -1.0, np.full((len(rw), K), 1.0 / pr["kappa"] ** 2),
                     np.zeros((len(rw), K))))
    Qs = []
    for k in range(K):
        rows, cols, vals = [], [], []
        bk = np.zeros(n)
        for ia, ja, ca, cb, w, obj in pots:
            wk, ok = w[:, k], obj[:, k]
            # (ca x_i + cb x_j − o)² · w → Q_ii += w ca², Q_jj += w cb², Q_ij += w ca cb; b_i += w ca o; b_j += w cb o
            rows += [ia, ja, ia, ja]; cols += [ia, ja, ja, ia]
            vals += [wk * ca * ca, wk * cb * cb, wk * ca * cb, wk * ca * cb]
            np.add.at(bk, ia, wk * ca * ok); np.add.at(bk, ja, wk * cb * ok)
        Q = sp.coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n)).tocsr()
        # escalón: (media_t μ_{l,t} − μ_esc(l))² / τ² y μ_esc² / sd²
        A = sp.lil_matrix((modelo.nL, n))
        for l in range(modelo.nL):
            cs = np.where(D.comp_liga == l)[0]
            for c in cs:
                A[l, nPS + c] = 1.0 / len(cs)
            A[l, nPS + nC + int(modelo.liga_esc[l])] = -1.0
        A = A.tocsr()
        Q = Q + (A.T @ A) / pr["tau"] ** 2
        Q = Q + sp.diags(np.r_[np.zeros(nPS + nC), np.full(nEsc, 1.0 / pr["sd_escalon"] ** 2)])
        Qs.append((Q.tocsc(), bk))
    media = np.zeros((n, K))
    lus = []
    for k, (Q, bk) in enumerate(Qs):
        f = spla.splu(Q)
        media[:, k] = f.solve(bk)
        lus.append(f)
    return Posterior(nPS=nPS, nC=nC, nEsc=nEsc, media=media, lu=lus, s=s, drift=drift)


def proyector_gauge(w: np.ndarray) -> np.ndarray:
    """P = I − 1 wᵀ: resta la media ponderada (gauge Σ w_c μ_c = 0)."""
    n = len(w)
    return np.eye(n) - np.outer(np.ones(n), w / w.sum())
