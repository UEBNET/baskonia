"""F0 · perfil ampliado x̃ de cada jugador-liga-temporada (capa 0 de la v4.0; encargo §5.1).

    x̃_i = [ u_i ∈ ℝ⁴ · p_i^estilo ∈ Δ⁶ · θ de los rasgos seleccionados (DT EuroLeague, v3.2) · rol · edad ]

Bloques y procedencia (todo con las identidades corregidas del 03-11-2026):
  * latente u (media y sd): posterior conjunta de las 20 redes CVAE de la configuración final de la v3.2 (K = 4), con
    el ajuste completo para el producto y con el ajuste ≤ t para los exámenes (misma caché de redes, experimentos/v3).
    El espacio latente de cada red es arbitrario (una transformación afín que el decodificador absorbe), así que las
    redes se alinean por mínimos cuadrados con la red de referencia antes de promediar; se publica el R² por red.
    Filas sin persona-temporada en el ajuste (< 100 min): codificador ⊗ prior N(μ_c, s_l²), como traducir_filas.
  * estilos: pertenencias p_<estilo> de los 6 estilos unificados (fase 6; ajuste con todas las temporadas, declarado).
  * rasgos: θ y varianza propia v_j de data/modelos/v3_2/destino/capacidad/<t>.csv.gz (ajuste completo) o de la
    normalización v3.2 ajustada ≤ t (fuente V32_corte del simulador) para los perfiles de corte.
  * rol: rol más probable, probabilidades de los 5 roles, índice ordinal esperado, MIN%, GS%, H_rol (por temporada).
  * edad y pos3 de la normalización; RAPM/ORAPM/DRAPM observados (pista) sólo como CONTRASTE para F1 y F1-D.
Salida: data/modelos/v4_0/perfiles/<t>.csv.gz (+ meta.json) y perfiles/corte_<t>/<temporada>.csv.gz.
Ningún valor ausente se imputa con 0: queda NaN y su aviso en la columna `avisos`.
"""
from __future__ import annotations

import json
import os
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C

Z80 = 1.2815515655446004
FUENTES_LATENTE = ("posterior_conjunta", "codificador", "codificador_nivel_temporada_anterior", "sin_latente")


def rasgos(cfg: dict) -> list[str]:
    return list(cfg["perfil"]["rasgos"])


def estilos(cfg: dict) -> list[str]:
    return list(cfg["perfil"]["estilos"])


def roles(cfg: dict) -> list[str]:
    return list(cfg["perfil"]["roles"])


def temp_de(a: int) -> str:
    return f"{a}-{str(a + 1)[-2:]}"


def metricas_corte(cfg: dict) -> list[str]:
    """Métricas que pide la normalización v2 ≤ t: los rasgos del perfil más las de traducción del simulador (entre
    ellas las de nivel, pts/100 y TS%, sin las cuales la amortiguación no puede medir la distancia entre ligas)."""
    from bbfit import sim_insumos as SI
    return sorted(set(rasgos(cfg)) | set(SI.metricas_traduccion()))


def dir_perfiles(cfg: dict, corte: int | None = None) -> Path:
    d = C.dir_salida(cfg) / "perfiles"
    if corte is not None:
        d = d / f"corte_{corte}"
    d.mkdir(parents=True, exist_ok=True)
    return d


# =============================================================================================== latente
def alinear(ref: np.ndarray, u: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Mínimos cuadrados afines u → ref (ref ≈ u·Aᵀ + b) sobre filas emparejadas. Devuelve A (K×K), b (K) y el R² por
    dimensión. La identidad (A = I, b = 0) para la red de referencia."""
    ok = np.isfinite(u).all(1) & np.isfinite(ref).all(1)
    X = np.c_[u[ok], np.ones(ok.sum())]
    coef, *_ = np.linalg.lstsq(X, ref[ok], rcond=None)
    A, b = coef[:-1].T, coef[-1]
    pred = X @ coef
    ss_res = ((ref[ok] - pred) ** 2).sum(0)
    ss_tot = ((ref[ok] - ref[ok].mean(0)) ** 2).sum(0)
    return A, b, 1.0 - ss_res / np.maximum(ss_tot, 1e-12)


def aplicar_afin(A: np.ndarray, b: np.ndarray, media: np.ndarray, var: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Media y varianza (diagonal) transformadas: ũ = A u + b; Var(ũ_k) = Σ_j A_kj² Var(u_j) (varianzas independientes)."""
    return media @ A.T + b, var @ (A ** 2).T


def diag_posterior(P, idx: np.ndarray, lote: int = 1000) -> np.ndarray:
    """Var(x_i) = e_iᵀ Q_k⁻¹ e_i de la posterior conjunta (bbnorm3.niveles.Posterior) para cada índice y dimensión."""
    idx = np.asarray(idx, int)
    n = P.media.shape[0]
    out = np.zeros((len(idx), len(P.lu)))
    for a in range(0, len(idx), lote):
        ii = idx[a:a + lote]
        E = np.zeros((n, len(ii)))
        E[ii, np.arange(len(ii))] = 1.0
        for k, f in enumerate(P.lu):
            X = f.solve(E)
            out[a:a + lote, k] = X[ii, np.arange(len(ii))]
    return np.maximum(out, 0.0)


def _matriz_Q(f) -> "sp.csc_matrix":
    """Reconstruye Q desde su factorización SuperLU (Pr·Q·Pc = L·U): Q = Prᵀ L U Pcᵀ."""
    import scipy.sparse as sp
    n = f.shape[0]
    Pr = sp.csc_matrix((np.ones(n), (f.perm_r, np.arange(n))), shape=(n, n))
    Pc = sp.csc_matrix((np.ones(n), (np.arange(n), f.perm_c)), shape=(n, n))
    return (Pr.T @ (f.L @ f.U) @ Pc.T).tocsc()


def _inversa_bloques(Quu) -> "sp.csr_matrix":
    """Inversa exacta de una matriz dispersa simétrica con estructura de bloques diagonales (componentes conexas:
    las personas-temporada de una misma persona, unidas por las transiciones), vectorizada por tamaño de bloque."""
    import scipy.sparse as sp
    from scipy.sparse.csgraph import connected_components
    n = Quu.shape[0]
    ncomp, lab = connected_components(Quu, directed=False)
    orden = np.argsort(lab, kind="stable")
    tam = np.bincount(lab, minlength=ncomp)
    inicio = np.r_[0, np.cumsum(tam)[:-1]]
    pos = np.empty(n, int)
    pos[orden] = np.arange(n) - inicio[lab[orden]]
    coo = Quu.tocoo()
    rows, cols, vals = [], [], []
    for s_ in np.unique(tam):
        comps = np.where(tam == s_)[0]
        kc = np.full(ncomp, -1); kc[comps] = np.arange(len(comps))
        sel = kc[lab[coo.row]] >= 0
        B = np.zeros((len(comps), s_, s_))
        np.add.at(B, (kc[lab[coo.row[sel]]], pos[coo.row[sel]], pos[coo.col[sel]]), coo.data[sel])
        Binv = np.linalg.inv(B)
        idx = np.stack([orden[inicio[c]:inicio[c] + s_] for c in comps]) if s_ > 0 else np.zeros((0, 0), int)
        rows.append(np.repeat(idx, s_, axis=1).ravel())
        cols.append(np.tile(idx, (1, s_)).ravel())
        vals.append(Binv.reshape(len(comps), -1).ravel())
    return sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))


class PosteriorRapida:
    """Covarianzas exactas de la posterior conjunta (bbnorm3.niveles.Posterior) por complemento de Schur. Q_uu
    (latentes) es diagonal por bloques (una persona por bloque, unida por sus transiciones) y el bloque de niveles
    (μ_c, μ_escalón) es pequeño:
        Q⁻¹_uu = Q_uu⁻¹ + W S⁻¹ Wᵀ,   Q⁻¹_uμ = −W S⁻¹,   Q⁻¹_μμ = S⁻¹,   W = Q_uu⁻¹ Q_uμ,   S = Q_μμ − Q_μu W.
    Con ello Var(u_i), Var(μ_c), Cov(u_i, μ_c) y Var(u_i − μ_c) salen en segundos para todas las variables."""

    def __init__(self, P, comps_ref: list[int] | None = None):
        """`comps_ref`: índices (en D.comps) de las competiciones de referencia cuyas covarianzas con los latentes se
        conservan (W S⁻¹ entero ocupa n_u × n_μ × K × 8 bytes por red: con 20 redes no cabe en memoria). None = todas."""
        self.nPS, self.n = P.nPS, P.media.shape[0]
        self.K = len(P.lu)
        self.cols = None if comps_ref is None else {int(c) - self.nPS: k for k, c in enumerate(comps_ref)}
        self.diag_u, self.WS, self.Sinv = [], [], []
        for f in P.lu:
            Q = _matriz_Q(f)
            Quu, Qum, Qmm = Q[:self.nPS, :self.nPS], Q[:self.nPS, self.nPS:], Q[self.nPS:, self.nPS:].toarray()
            Binv = _inversa_bloques(Quu)
            W = (Binv @ Qum).toarray()
            Sinv = np.linalg.inv(Qmm - Qum.T @ W)
            WS = W @ Sinv           # float64: Var(u − μ) = Var(u) + Var(μ) − 2·Cov cancela casi todo y float32 no basta
            self.diag_u.append(np.maximum(Binv.diagonal() + np.einsum("ij,ij->i", WS, W), 0.0))
            self.WS.append(WS if self.cols is None else WS[:, sorted(self.cols, key=self.cols.get)].copy())
            self.Sinv.append(Sinv)
            del Q, Quu, Qum, Binv, W, WS

    def _col(self, c: int) -> int:
        j = c - self.nPS
        if self.cols is None:
            return j
        if j not in self.cols:
            raise KeyError(f"competición {c} no está entre las referencias conservadas")
        return self.cols[j]

    def diag(self) -> np.ndarray:
        """diag(Q_k⁻¹) de todas las variables (n × K)."""
        out = np.zeros((self.n, self.K))
        for k in range(self.K):
            out[:self.nPS, k] = self.diag_u[k]
            out[self.nPS:, k] = np.maximum(np.diag(self.Sinv[k]), 0.0)
        return out

    def var_u_menos_mu(self, ips: np.ndarray, c: int) -> np.ndarray:
        """Var(u_i − μ_c) = Var(u_i) + Var(μ_c) − 2 Cov(u_i, μ_c), con Cov(u_i, μ_c) = −(W S⁻¹)[i, c]  (len(ips) × K)."""
        ips = np.asarray(ips, int)
        j, jc = c - self.nPS, self._col(c)
        out = np.zeros((len(ips), self.K))
        for k in range(self.K):
            out[:, k] = self.diag_u[k][ips] + self.Sinv[k][j, j] + 2.0 * self.WS[k][ips, jc]
        return np.maximum(out, 0.0)

    def var_mu_menos_mu(self, cs: np.ndarray, c: int) -> np.ndarray:
        """Var(μ_a − μ_c) para varias competiciones a (len(cs) × K)."""
        cs = np.asarray(cs, int) - self.nPS
        j = c - self.nPS
        out = np.zeros((len(cs), self.K))
        for k in range(self.K):
            S = self.Sinv[k]
            out[:, k] = S[cs, cs] + S[j, j] - 2.0 * S[cs, j]
        return np.maximum(out, 0.0)


def diag_posterior_completa(P) -> np.ndarray:
    """diag(Q_k⁻¹) de TODAS las variables (n × K), exacta y rápida (PosteriorRapida)."""
    return PosteriorRapida(P).diag()


def latente_red(m, P, D, t: pd.DataFrame, cfg_norm: dict, lote: int = 1000, diag: np.ndarray | None = None,
                rapida: "PosteriorRapida | None" = None):
    """u (coordenadas absolutas de la red) de cada fila de `t` para una red del ensemble.
    Filas con persona-temporada en el ajuste: media y varianza de la posterior conjunta. Resto: codificador ⊗ prior
    N(μ_c, s_l²) (precisión del experto + 1 en coordenadas relativas), con Var(μ_c) y, si la competición-temporada no
    está en el ajuste, el nivel de la última temporada de esa liga más el paso κ² (como bbnorm3.exportar.traducir_filas)."""
    import torch
    from bbnorm3.datos import POSICIONES, matrices_filas
    K, n = m.K, len(t)
    if diag is None:
        diag = (rapida or PosteriorRapida(P)).diag()
    media = np.full((n, K), np.nan)
    var = np.full((n, K), np.nan)
    fuente = np.full(n, "sin_latente", dtype=object)
    ps_idx = {p: i for i, p in enumerate(D.ps)}
    ps = (t["persona_id"].astype(str) + "|" + t["anio"].astype(int).astype(str)).map(ps_idx)
    ok = ps.notna().to_numpy()
    if ok.any():
        ips = ps[ok].astype(int).to_numpy()
        media[ok] = P.media[ips]
        var[ok] = diag[ips]
        fuente[ok] = "posterior_conjunta"
    resto = ~ok & t["liga"].isin(D.ligas).to_numpy() & t["pos3"].isin(POSICIONES).to_numpy()
    if resto.any():
        tr = t[resto]
        ultima = {}
        for c in D.comps:
            l, tt = c.split("|")
            if l not in ultima or tt > ultima[l].split("|")[1]:
                ultima[l] = c
        comp = (tr["liga"] + "|" + tr["temporada"]).to_numpy(object)
        comp_aj = np.array([c if c in D.comps else ultima.get(c.split("|")[0]) for c in comp], dtype=object)
        extra = np.where(comp == comp_aj, 0.0, cfg_norm["prior"]["kappa"] ** 2)
        Yn, Mn, Vn = matrices_filas(tr, D.esc)
        liga_n = np.array([D.ligas.index(l) for l in tr["liga"]])
        comp_n = np.array([D.comps.index(c) for c in comp_aj])
        pos_n = tr["pos3"].map({p: i for i, p in enumerate(POSICIONES)}).to_numpy(int)
        logmin = np.log(np.clip(tr["min"].to_numpy(float), 1, None)) / 7.0
        with torch.no_grad():
            mm, lp = m.codificar(torch.as_tensor(Yn), torch.as_tensor(Mn), torch.as_tensor(Vn),
                                 torch.as_tensor(liga_n.copy()), torch.as_tensor(pos_n.copy()),
                                 torch.as_tensor(logmin, dtype=torch.float32))
        prec = np.exp(lp.numpy().astype(float)) + 1.0
        rmed = mm.numpy().astype(float) * np.exp(lp.numpy().astype(float)) / prec
        sl = P.s[liga_n][:, None]
        vmu = diag[P.nPS + comp_n]
        media[resto] = P.media[P.nPS + comp_n] + sl * rmed
        var[resto] = sl ** 2 / prec + vmu + extra[:, None]
        fuente[resto] = np.where(extra > 0, "codificador_nivel_temporada_anterior", "codificador")
    return media, var, fuente


def latente_ensemble(D, cj, t: pd.DataFrame, cfg: dict, cfg_norm: dict, progreso=print,
                     liberar_lu: bool = False) -> tuple[pd.DataFrame, dict]:
    """u (media y sd) de cada fila de `t` promediando el deep ensemble tras alinear cada red con la de referencia.
    sd² = media de las varianzas alineadas (dentro de cada red) + varianza entre redes de las medias alineadas."""
    L = cfg["perfil"]["latente"]
    lote, iref = int(L.get("lote_varianza", 1000)), int(L.get("red_referencia", 0))
    ref = cj[iref][1].media[:cj[iref][1].nPS]
    medias, vars_, r2s, fuente, rapidas = [], [], [], None, []
    comp_ref = f"{cfg_norm['referencia_salida']['liga']}|{cfg_norm['referencia_salida']['temporada']}"
    refs = [D.comps.index(comp_ref)] if comp_ref in D.comps else []
    t0 = time.time()
    for k, (m, P) in enumerate(cj):
        A, b, r2 = alinear(ref, P.media[:P.nPS])
        PR = PosteriorRapida(P, comps_ref=refs)          # sólo la covarianza con la competición de referencia
        rapidas.append(PR)
        if liberar_lu:
            P.lu = None                                   # las factorizaciones (≈ 35 MB × K por red) ya no hacen falta
        med, var, fu = latente_red(m, P, D, t, cfg_norm, lote, rapida=PR)
        med, var = aplicar_afin(A, b, med, var)
        medias.append(med); vars_.append(var); r2s.append(r2)
        fuente = fu if fuente is None else fuente
        if progreso:
            progreso(f"    red {k + 1}/{len(cj)}: R² alineamiento {np.round(r2, 3).tolist()} · {time.time() - t0:.0f} s",
                     flush=True)
    M = np.stack(medias)                               # redes × filas × K
    V = np.stack(vars_)
    u = np.nanmean(M, 0)
    dentro = np.nanmean(V, 0)
    entre = np.nanvar(M, 0)
    sd = np.sqrt(dentro + entre)
    K = u.shape[1]
    out = pd.DataFrame({f"u{k + 1}": u[:, k] for k in range(K)}, index=t.index)
    for k in range(K):
        out[f"u{k + 1}_sd"] = sd[:, k]
    out["u_fuente"] = fuente
    out["u_discrepancia_redes"] = np.sqrt(entre).mean(1)
    r2 = np.array(r2s)
    meta = {"K": int(K), "redes": len(cj), "alineacion": L.get("alineacion"), "red_referencia": iref,
            "r2_alineamiento_por_red": [[round(float(x), 4) for x in r] for r in r2],
            "r2_alineamiento_medio": round(float(np.mean(r2[[k for k in range(len(cj)) if k != iref]])), 4)
            if len(cj) > 1 else None,
            "r2_alineamiento_minimo": round(float(r2[[k for k in range(len(cj)) if k != iref]].min()), 4)
            if len(cj) > 1 else None,
            "redes_con_r2_bajo": [k for k in range(len(cj)) if k != iref and float(r2[k].mean()) < float(L["r2_minimo_aviso"])],
            "fuentes": {k: int((fuente == k).sum()) for k in FUENTES_LATENTE},
            "discrepancia_redes_mediana": float(np.nanmedian(out["u_discrepancia_redes"]))}
    meta["_rapidas"] = rapidas          # posteriores rápidas (no se serializan): las reutiliza theta_corte
    return out, meta


# =============================================================================================== traducción rápida (cortes)
def traducir_corte(filas: pd.DataFrame, D, cj, cfg3: dict, metricas: list[str], rapidas: list | None = None,
                   progreso=None) -> pd.DataFrame:
    """Equivalente en la competición de referencia (EuroLeague de `cfg3.referencia_salida.temporada`) de cada fila,
    con la MISMA lógica que bbnorm3.exportar.traducir_filas (posterior conjunta para las filas del ajuste; codificador ⊗
    prior para el resto; factor específico ζ; soporte sin recortar el centro, §11c; deep ensemble) pero con las varianzas
    de (u − μ_R) por complemento de Schur (PosteriorRapida) en vez de una resolución por persona. Sólo `metricas`.
    Devuelve liga, temporada, player_id y <m>_v3, <m>_v3_lo, <m>_v3_hi, <m>_v3_sd_entre_z."""
    import torch
    from bbmodel.metricas import CATALOGO, destransformar
    from bbnorm3.datos import METRICAS, POSICIONES, matrices_filas
    from bbnorm3.prediccion import soporte
    ref = f"{cfg3['referencia_salida']['liga']}|{cfg3['referencia_salida']['temporada']}"
    R = D.comps.index(ref)
    lR = int(D.comp_liga[R])
    t = filas[filas["pos3"].notna()].copy()
    t["comp"] = t["liga"] + "|" + t["temporada"]
    ultima = {}
    for c in D.comps:
        l, tt = c.split("|")
        if l not in ultima or tt > ultima[l].split("|")[1]:
            ultima[l] = c
    t["comp_ajuste"] = np.where(t["comp"].isin(D.comps), t["comp"], t["liga"].map(ultima))
    t = t[t["comp_ajuste"].notna() & t["liga"].isin(D.ligas)]
    extra_kappa = np.where(t["comp"] == t["comp_ajuste"], 0.0, cfg3["prior"]["kappa"] ** 2)
    ps_idx = {p: i for i, p in enumerate(D.ps)}
    en_ent = (t["persona_id"].astype(str) + "|" + t["anio"].astype(int).astype(str)).map(ps_idx)
    grupos_R = np.array([D.grupos.index(f"{ref}|{p}") for p in t["pos3"]])
    S = int(cfg3["prediccion"]["muestras"])
    rng = np.random.default_rng(int(cfg3["semillas"][0]))
    Yn, Mn, Vn = matrices_filas(t, D.esc)
    liga_n = np.array([D.ligas.index(l) for l in t["liga"]])
    comp_n = np.array([D.comps.index(c) for c in t["comp_ajuste"]])
    pos_n = t["pos3"].map({p: i for i, p in enumerate(POSICIONES)}).to_numpy(int)
    logmin = np.log(np.clip(t["min"].to_numpy(float), 1, None)) / 7.0
    ok = en_ent.notna().to_numpy()
    ips = en_ent[ok].astype(int).to_numpy()
    per_idx = {p: i for i, p in enumerate(D.personas)}
    pi = t["persona_id"].map(per_idx)
    okp = pi.notna().to_numpy()
    margen = cfg3["prediccion"].get("margen_soporte")
    lo_s, hi_s = soporte(D, float(margen)) if margen is not None else (None, None)
    kk = [METRICAS.index(m) for m in metricas]
    partes = []
    for i_red, (m, P) in enumerate(cj):
        PR = rapidas[i_red] if rapidas is not None else PosteriorRapida(P)
        K = m.K
        media = np.zeros((len(t), K)); var = np.zeros((len(t), K))
        media[ok] = P.media[ips] - P.media[P.nPS + R]
        var[ok] = PR.var_u_menos_mu(ips, P.nPS + R)
        if (~ok).any():
            with torch.no_grad():
                mm_, lp = m.codificar(torch.as_tensor(Yn[~ok]), torch.as_tensor(Mn[~ok]), torch.as_tensor(Vn[~ok]),
                                      torch.as_tensor(liga_n[~ok].copy()), torch.as_tensor(pos_n[~ok].copy()),
                                      torch.as_tensor(logmin[~ok], dtype=torch.float32))
            prec = np.exp(lp.numpy().astype(float)) + 1.0
            rmed = mm_.numpy().astype(float) * np.exp(lp.numpy().astype(float)) / prec
            sl = P.s[liga_n[~ok]][:, None]
            media[~ok] = P.media[P.nPS + comp_n[~ok]] + sl * rmed - P.media[P.nPS + R]
            var[~ok] = sl ** 2 / prec + PR.var_mu_menos_mu(P.nPS + comp_n[~ok], P.nPS + R) + extra_kappa[~ok][:, None]
        z = np.zeros((len(t), len(METRICAS))); vz = np.zeros_like(z)
        if m.usar_unicidad:
            vz[:] = m.s2Z.numpy()[None, :]
            prec_z = m.precision_unicidad().numpy()
            z[okp] = m.Z.detach().numpy()[pi[okp].astype(int)]
            vz[okp] = 1.0 / (prec_z[pi[okp].astype(int)] + 1.0 / m.s2Z.numpy()[None, :])
        partes.append((m, P, media, var, z, vz))
        if progreso:
            progreso(f"      red {i_red + 1}/{len(cj)}: posterior de (u − μ_R) lista", flush=True)
    n = len(t)
    centro = np.zeros((n, len(METRICAS))); entre = np.zeros_like(centro)
    lo = np.zeros_like(centro); hi = np.zeros_like(centro)
    bloque = 1000
    with torch.no_grad():
        for a in range(0, n, bloque):
            sl_ = slice(a, min(a + bloque, n))
            nb = sl_.stop - sl_.start
            cent_b, mues_b = [], []
            for m, P, media, var, z, vz in partes:
                K = m.K
                eps = rng.standard_normal((nb, S, K))
                r = (media[sl_, None, :] + np.sqrt(np.maximum(var[sl_], 0))[:, None, :] * eps) / P.s[lR]
                yh = m.decodificar(torch.as_tensor(r.reshape(-1, K), dtype=torch.float32),
                                   torch.full((nb * S,), lR), torch.as_tensor(np.repeat(grupos_R[sl_], S))).numpy()
                yh = yh.reshape(nb, S, -1).astype(float)
                yh = yh + z[sl_, None, :] + np.sqrt(vz[sl_])[:, None, :] * rng.standard_normal(yh.shape)
                if margen is not None:
                    yc = np.clip(yh, lo_s[lR][None, None, :], hi_s[lR][None, None, :])
                    if cfg3["prediccion"].get("recorte_centro", True):
                        yh = yc
                    else:
                        yh = yh + np.abs(yh - yc) * rng.standard_normal(yh.shape)
                cent_b.append(yh.mean(1)); mues_b.append(yh[:, :, kk])
            centro[sl_] = np.mean(cent_b, 0)
            entre[sl_] = np.std(cent_b, 0)
            q = np.quantile(np.concatenate(mues_b, 1), [0.1, 0.9], axis=1)
            lo[sl_, kk], hi[sl_, kk] = q[0], q[1]
    out = {"liga": t["liga"].to_numpy(), "temporada": t["temporada"].to_numpy(), "player_id": t["player_id"].to_numpy(),
           "fuente_v3": np.where(ok, "posterior_conjunta", np.where(extra_kappa > 0, "codificador_nivel_temporada_anterior",
                                                                    "codificador"))}
    for k, col in zip(kk, metricas):
        tr = CATALOGO[col].transf
        c, s_ = D.esc.c[col], D.esc.s[col]
        out[f"{col}_v3"] = destransformar(c + s_ * centro[:, k], tr)
        out[f"{col}_v3_lo"] = destransformar(c + s_ * lo[:, k], tr)
        out[f"{col}_v3_hi"] = destransformar(c + s_ * hi[:, k], tr)
        out[f"{col}_v3_sd_entre_z"] = entre[:, k]
    return pd.DataFrame(out, index=t.index)


# =============================================================================================== bloques
def _leer(p: Path, usecols=None, **kw) -> pd.DataFrame:
    dt = {"player_id": str, "team_id": str, "persona_id": str, "pid_estilos": str}
    if usecols is not None:
        cab = pd.read_csv(p, nrows=0).columns
        usecols = [c for c in usecols if c in cab]
    return pd.read_csv(p, dtype=dt, usecols=usecols, low_memory=False, **kw)


def capacidad(cfg: dict, temp: str) -> pd.DataFrame:
    """θ y v_j (destino/capacidad/<t>.csv.gz) de los rasgos del perfil + identidad; persona_id → persona_norm."""
    p = C.ruta(cfg, "destino") / "capacidad" / f"{temp}.csv.gz"
    cols = ["persona_id", "liga", "temporada", "player_id", "team_id", "pos3", "edad", "min"] + \
        [f"{m}_{s}" for m in rasgos(cfg) for s in ("th", "vj")]
    d = _leer(p, cols).rename(columns={"persona_id": "persona_norm"})
    for m in rasgos(cfg):
        for s in ("th", "vj"):
            if f"{m}_{s}" not in d:
                d[f"{m}_{s}"] = np.nan
    return d.sort_values("min", ascending=False).drop_duplicates(["liga", "temporada", "player_id"])


_ROLES: list = []


def bloque_roles(cfg: dict) -> pd.DataFrame:
    if not _ROLES:
        R = roles(cfg)
        cols = ["liga", "temporada", "team_id", "player_id", "persona_id", "rol_mas_probable", "min_pct", "gs_pct",
                "H_rol", "fuente", "gp", "min_total"] + [f"p_{r}" for r in R]
        d = _leer(C.ruta(cfg, "roles"), cols)
        d = d[pd.to_numeric(d["min_total"], errors="coerce").fillna(0) > 0]
        d = d.sort_values("min_total", ascending=False).drop_duplicates(["liga", "temporada", "player_id"])
        d = d.rename(columns={"persona_id": "persona_cw_roles", "fuente": "rol_fuente", "gp": "rol_gp",
                              "min_total": "rol_min_total"})
        P = d[[f"p_{r}" for r in R]].apply(pd.to_numeric, errors="coerce").to_numpy(float)
        d["rol_indice_esperado"] = P @ np.arange(len(R), dtype=float)
        d["rol_indice"] = d["rol_mas_probable"].map({r: i for i, r in enumerate(R)})
        _ROLES.append(d)
    return _ROLES[0]


_ESTILOS: list = []


def bloque_estilos(cfg: dict) -> pd.DataFrame:
    if not _ESTILOS:
        E = estilos(cfg)
        cols = ["liga", "temporada", "team_id", "player_id", "nivel", "min", "fiable", "estilo", "p_estilo"] + \
            [f"p_{e}" for e in E]
        d = _leer(C.ruta(cfg, "estilos"), cols)
        d = d[d["nivel"] == "temporada"].drop(columns=["nivel"])
        d = d.sort_values("min", ascending=False).drop_duplicates(["liga", "temporada", "player_id"])
        d = d.rename(columns={"min": "estilo_min", "fiable": "estilo_fiable", "p_estilo": "estilo_p"})
        _ESTILOS.append(d)
    return _ESTILOS[0]


def bloque_pista(cfg: dict, temp: str) -> pd.DataFrame:
    p = C.ruta(cfg, "pista") / f"{temp}.csv"
    if not p.exists():
        return pd.DataFrame(columns=["liga", "temporada", "player_id", "rapm_obs", "orapm_obs", "drapm_obs", "poss_on_obs"])
    d = _leer(p, ["liga", "temporada", "team_id", "player_id", "rapm", "orapm", "drapm", "poss_on"])
    d = d.sort_values("poss_on", ascending=False).drop_duplicates(["liga", "temporada", "player_id"])
    return d.drop(columns=["team_id"]).rename(columns={"rapm": "rapm_obs", "orapm": "orapm_obs", "drapm": "drapm_obs",
                                                       "poss_on": "poss_on_obs"})


def persona_crosswalk(liga: str, player_ids: pd.Series) -> pd.Series:
    from bbfit.datos import persona
    return persona(liga, player_ids.astype(str))


def _tramo_edad(edad: pd.Series) -> pd.Series:
    from bbmodel.enlace import tramo_edad
    return edad.map(lambda e: tramo_edad(float(e)) if pd.notna(e) else "s/d")   # «s/d» como en la normalización


# =============================================================================================== perfil por temporada
COLUMNAS_ID = ["persona_id", "persona_norm", "liga", "temporada", "player_id", "team_id", "pos3", "edad", "tramo_edad",
               "min"]


def perfil_temporada(temp: str, lat: pd.DataFrame | None, cfg: dict, theta: pd.DataFrame | None = None,
                     bloques: dict | None = None) -> pd.DataFrame:
    """Une los bloques de x̃ de una temporada. `lat`: latente por fila (liga, temporada, persona_norm, u…).
    `theta`: θ/v_j alternativos (ajuste ≤ t) con las columnas de `capacidad`; por defecto, el ajuste completo.
    `bloques` (tests): {"roles", "estilos", "pista", "persona"} en lugar de los ficheros del repositorio."""
    bl = bloques or {}
    R, E, X = roles(cfg), estilos(cfg), rasgos(cfg)
    base = (theta if theta is not None else capacidad(cfg, temp)).copy()
    base = base[base["temporada"] == temp]
    base["persona_norm"] = base["persona_norm"].astype(str)
    # identidad entre ligas: persona_id del crosswalk (P…); sin él, «<liga>:<player_id>»
    per = bl.get("persona", persona_crosswalk)
    base["persona_id"] = None
    for liga, g in base.groupby("liga"):
        base.loc[g.index, "persona_id"] = per(liga, g["player_id"]).to_numpy()
    base["tramo_edad"] = _tramo_edad(pd.to_numeric(base["edad"], errors="coerce"))
    # latente
    K = int(cfg["perfil"]["latente"]["K"])
    ucols = [f"u{k + 1}" for k in range(K)] + [f"u{k + 1}_sd" for k in range(K)] + ["u_fuente", "u_discrepancia_redes"]
    if lat is not None and len(lat):
        l = lat[lat["temporada"] == temp].copy()
        l["persona_norm"] = l["persona_norm"].astype(str)
        l = l.sort_values("min", ascending=False).drop_duplicates(["liga", "temporada", "persona_norm"])
        base = base.merge(l[["liga", "temporada", "persona_norm"] + [c for c in ucols if c in l]],
                          on=["liga", "temporada", "persona_norm"], how="left")
    for c in ucols:
        if c not in base:
            base[c] = np.nan
    base["u_fuente"] = base["u_fuente"].where(base["u_fuente"].notna(), "sin_latente")
    # estilos, rol y pista (contraste) por (liga, temporada, player_id)
    est = bl.get("estilos", None)
    est = bloque_estilos(cfg) if est is None else est
    est = est[est["temporada"] == temp].drop(columns=[c for c in ("team_id",) if c in est])
    base = base.merge(est, on=["liga", "temporada", "player_id"], how="left")
    rol = bl.get("roles", None)
    rol = bloque_roles(cfg) if rol is None else rol
    rol = rol[rol["temporada"] == temp].drop(columns=[c for c in ("team_id",) if c in rol])
    base = base.merge(rol, on=["liga", "temporada", "player_id"], how="left")
    pis = bl.get("pista", None)
    pis = bloque_pista(cfg, temp) if pis is None else pis
    base = base.merge(pis[pis["temporada"] == temp], on=["liga", "temporada", "player_id"], how="left")
    # avisos (nunca se imputa con 0)
    av = []
    th_cols = [f"{m}_th" for m in X]
    sin_theta = base[th_cols].isna().all(axis=1)
    sin_estilo = base[[f"p_{e}" for e in E]].isna().all(axis=1)
    sin_rol = base["rol_mas_probable"].isna()
    for i in range(len(base)):
        a = []
        f = base["u_fuente"].iat[i]
        if f == "sin_latente":
            a.append("sin_latente")
        elif f != "posterior_conjunta":
            a.append("latente_codificador")
        if float(base["u_discrepancia_redes"].iat[i] or 0) > float(cfg["perfil"]["max_discrepancia_redes"]):
            a.append("red_discrepante")
        if sin_estilo.iat[i]:
            a.append("sin_estilo")
        if sin_rol.iat[i]:
            a.append("sin_rol")
        if pd.isna(base["rapm_obs"].iat[i]):
            a.append("sin_rapm")
        if sin_theta.iat[i]:
            a.append("sin_theta")
        if str(base["persona_id"].iat[i]).startswith(base["liga"].iat[i] + ":"):
            a.append("sin_persona_crosswalk")
        if float(pd.to_numeric(base["min"].iat[i], errors="coerce") or 0) < float(cfg["perfil"]["min_minutos_completo"]):
            a.append("muestra_corta")
        av.append(";".join(a))
    base["avisos"] = av
    base["completo"] = [a == "" or set(a.split(";")) <= {"muestra_corta", "latente_codificador"} for a in av]
    orden = COLUMNAS_ID + ucols + ["estilo", "estilo_p", "estilo_fiable", "estilo_min"] + [f"p_{e}" for e in E] + \
        [f"{m}_{s}" for m in X for s in ("th", "vj")] + \
        ["rol_mas_probable", "rol_indice", "rol_indice_esperado"] + [f"p_{r}" for r in R] + \
        ["min_pct", "gs_pct", "H_rol", "rol_fuente", "rol_gp", "rol_min_total", "persona_cw_roles",
         "rapm_obs", "orapm_obs", "drapm_obs", "poss_on_obs", "completo", "avisos"]
    return base[[c for c in orden if c in base]].reset_index(drop=True)


def resumen_perfil(p: pd.DataFrame, cfg: dict) -> dict:
    """Cobertura de cada bloque (global y por liga) para meta.json."""
    E, X = estilos(cfg), rasgos(cfg)
    K = int(cfg["perfil"]["latente"]["K"])

    def cob(g):
        return {"filas": int(len(g)), "latente": float(g["u1"].notna().mean()) if "u1" in g else 0.0,
                "latente_posterior": float((g["u_fuente"] == "posterior_conjunta").mean()),
                "estilos": float(g[f"p_{E[0]}"].notna().mean()),
                "theta": float(g[[f"{m}_th" for m in X]].notna().all(axis=1).mean()),
                "rol": float(g["rol_mas_probable"].notna().mean()), "rapm_obs": float(g["rapm_obs"].notna().mean()),
                "persona_crosswalk": float((~g["avisos"].str.contains("sin_persona_crosswalk")).mean()),
                "completo": float(g["completo"].mean())}
    out = {"global": cob(p), "por_liga": {l: cob(g) for l, g in p.groupby("liga")}, "K": K,
           "filas_min_300": int((pd.to_numeric(p["min"], errors="coerce") >= 300).sum())}
    g300 = p[pd.to_numeric(p["min"], errors="coerce") >= 300]
    out["cobertura_min_300"] = cob(g300) if len(g300) else None
    return out


# =============================================================================================== θ por corte (sin fuga)
def theta_corte(anio: int, temporadas: list[str], tabla: pd.DataFrame, cfg: dict, D, cj, progreso=print,
                rapidas: list | None = None) -> pd.DataFrame:
    """θ y v_j de las filas de `temporadas` (≤ anio) con la normalización v3.2 ajustada SÓLO con temporadas ≤ anio
    (fuente «V32_corte» del simulador, generalizada a cualquier temporada ≤ t): mezcla v2 ≤ t (A amortiguado) con la
    CVAE ≤ t (las redes del corte), pesos B2 del corte, salvaguardas y constantes del sustituto lineal del corte.
    Reutiliza bbfit.sim_insumos (CERNO_SIMULADOR=v32) y la lógica de bbnorm3.exportar.traducir_filas (traducir_corte). Devuelve las columnas de
    `capacidad` (persona_norm, liga, temporada, player_id, team_id, pos3, edad, min, <m>_th, <m>_vj)."""
    os.environ.setdefault("CERNO_SIMULADOR", cfg["insumos"].get("simulador_env_corte", "v32"))
    from bbfit import sim_insumos as SI
    from bbmodel import amortiguacion as AM
    from bbmodel import modelo as A2
    from bbmodel.metricas import CATALOGO, destransformar, transformar
    from bbnorm3 import combinacion as CB
    from bbnorm3 import config as C3
    t0 = time.time()
    temp = temp_de(anio)
    X = rasgos(cfg)
    # v2 ≤ t (A ajustado ≤ t: la misma caché que deja `bbmodel amortiguar --validar`; si falta, se ajusta igual)
    pa = AM.DIR_CACHE / f"A_hasta_{anio}.pkl"
    if not pa.exists():
        if progreso:
            progreso(f"    A ≤ {anio}: sin caché, ajustando (bbmodel.modelo.ajustar)…", flush=True)
        AM.DIR_CACHE.mkdir(parents=True, exist_ok=True)
        nb = int((AM.config().get("validacion") or {}).get("bootstrap", 10))
        pa.write_bytes(pickle.dumps(A2.ajustar(tabla, hasta_anio=anio, n_boot=nb, progreso=None)))
    nh = SI.normalizacion_hasta(anio, metricas_corte(cfg), progreso=None)
    th2, trad2 = nh["theta"], nh["traduccion"]
    th2 = th2[th2["temporada"].isin(temporadas)].drop_duplicates(["liga", "temporada", "player_id"])
    # CVAE ≤ t traducida a la vara EuroLeague de la temporada t
    cfg3 = C3.con(C3.cargar(C.ruta(cfg, "normalizacion")), **{"referencia_salida.temporada": temp})
    filas = tabla[tabla["temporada"].isin(temporadas)]
    tr = traducir_corte(filas, D, cj, cfg3, X, rapidas=rapidas, progreso=progreso)
    tr = tr.drop_duplicates(["liga", "temporada", "player_id"])
    x = th2.merge(tr, on=["liga", "temporada", "player_id"], how="inner", suffixes=("", "_cvae"))
    if "min" not in x:
        x = x.merge(filas[["liga", "temporada", "player_id", "min"]].drop_duplicates(["liga", "temporada", "player_id"]),
                    on=["liga", "temporada", "player_id"], how="left")
    ex = C.RAIZ / cfg3["salida"] / "validacion" / "examen_v32.json"
    exj = json.loads(ex.read_text(encoding="utf-8")) if ex.exists() else {}
    w_met = (exj.get("pesos_por_corte") or {}).get(str(anio)) or {}
    w_con = (exj.get("combinada_b2_con_conocimiento_feb3") or {}).get("peso_v3_conocimiento_elegido")
    cb = cfg3["combinacion"]
    temporadas_liga = CB.temporadas_por_liga(tabla, cfg3, anio)
    const2 = trad2["constantes"]
    th = x[["liga", "temporada", "player_id", "pos3", "min"]].copy()
    nv = x[["liga", "temporada", "player_id", "pos3", "min"]].copy()
    for m in X:
        if m not in const2 or f"{m}_th" not in x or f"{m}_v3" not in x:
            continue
        k, trf = const2[m], CATALOGO[m].transf
        mu = np.array([SI.entorno(k, "euroleague", temp, p)[0] if isinstance(p, str) else np.nan for p in x["pos3"]])
        tau = np.array([SI.entorno(k, "euroleague", temp, p)[1] if isinstance(p, str) else np.nan for p in x["pos3"]])
        m2 = mu + tau * x[f"{m}_th"].to_numpy(float)
        s2 = np.maximum(tau * x[f"{m}_thsd"].to_numpy(float), 1e-6)
        m3 = transformar(x[f"{m}_v3"].to_numpy(float), trf)
        s3 = np.maximum((transformar(x[f"{m}_v3_hi"].to_numpy(float), trf)
                         - transformar(x[f"{m}_v3_lo"].to_numpy(float), trf)) / (2 * Z80), 1e-6)
        w = np.full(len(x), float(w_met.get(m, cb["peso_v3"])))
        if w_con is not None:
            w[x["liga"].isin(cb["ligas_conocimiento"]).to_numpy()] = float(w_con)
        w[(x["liga"].map(temporadas_liga).fillna(0) < cb["min_temporadas_liga"]).to_numpy()] = 0.0
        w[x[f"{m}_v3_sd_entre_z"].to_numpy(float) > cb["max_discrepancia_redes"]] = 0.0
        w[~np.isfinite(m3) | ~np.isfinite(s3)] = 0.0
        m3, s3 = np.where(np.isfinite(m3), m3, m2), np.where(np.isfinite(s3), s3, s2)
        media = w * m3 + (1 - w) * m2
        lo, hi = CB._cuantiles_mezcla(w, m3, s3, m2, s2, (0.1, 0.9))
        nv[f"{m}_am"], nv[f"{m}_am_v1"] = destransformar(media, trf), destransformar(m2, trf)
        th[f"{m}_th"] = (media - mu) / tau
        th[f"{m}_thsd"] = (hi - lo) / (2 * Z80 * tau)
    # constantes del corte (sustituto lineal sobre la temporada t) → varianza del nivel de origen → v_j propia
    trad = SI.sustituto_lineal(trad2, nv[nv["temporada"] == temp], [m for m in X if f"{m}_am" in nv], temp_ref=temp)
    for m in X:
        if f"{m}_thsd" in th:
            vo = np.array([SI._nodo(trad["nodos"].get(m, {}), lg, tp)[1] for lg, tp in zip(th["liga"], th["temporada"])])
            vo = np.where(np.isfinite(vo), vo, 0.0)
            s_ = th[f"{m}_thsd"].to_numpy(float)
            th[f"{m}_vj"] = np.maximum(s_ ** 2 - vo, 0.1 * s_ ** 2)
        else:
            th[f"{m}_th"] = np.nan
            th[f"{m}_vj"] = np.nan
    ident = filas[["persona_id", "liga", "temporada", "player_id", "team_id", "edad"]].drop_duplicates(
        ["liga", "temporada", "player_id"]).rename(columns={"persona_id": "persona_norm"})
    th = th.merge(ident, on=["liga", "temporada", "player_id"], how="left")
    th["player_id"] = th["player_id"].astype(str)
    th["team_id"] = th["team_id"].astype(str)
    th = th[["persona_norm", "liga", "temporada", "player_id", "team_id", "pos3", "edad", "min"]
            + [f"{m}_{s}" for m in X for s in ("th", "vj")]]
    if progreso:
        progreso(f"    θ ≤ {anio} (sin fuga) de {len(th)} filas en {len(temporadas)} temporadas · {time.time() - t0:.0f} s",
                 flush=True)
    return th


# =============================================================================================== exportación
def _tabla(cfg: dict, progreso=print) -> pd.DataFrame:
    p = C.ruta(cfg, "tabla_cache")
    if p.exists():
        return pickle.loads(p.read_bytes())
    from bbmodel import modelo as A
    if progreso:
        progreso("  preparando la tabla (identidades y posiciones)…", flush=True)
    t, _ = A.preparar()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(pickle.dumps(t))
    return t


def _filas_latente(tabla: pd.DataFrame, temporadas: list[str]) -> pd.DataFrame:
    t = tabla[tabla["temporada"].isin(temporadas) & tabla["pos3"].notna()].copy()
    return t


def exportar(cfg: dict, cortes: list[int] | None = None, temporadas: list[str] | None = None, completo: bool = True,
             progreso=print) -> dict:
    """F0 · perfiles del ajuste completo (producto) y, si `cortes`, de cada corte ≤ t (exámenes). Registra en MLflow."""
    from bbfit.registro import experimento
    from bbnorm3 import config as C3, flujo
    t0 = time.time()
    tabla = _tabla(cfg, progreso)
    temporadas = temporadas or [t for t in cfg["perfil"]["temporadas"] if t in set(tabla["temporada"])]
    cfg_norm = C3.cargar(C.ruta(cfg, "normalizacion"))
    assert int(cfg_norm["latente"]["K"]) == int(cfg["perfil"]["latente"]["K"]), "K del perfil ≠ K de la v3.2 final"
    res = {"version": cfg["version"], "huella": C.huella(cfg), "temporadas": temporadas, "cortes": {}}
    with experimento(cfg["mlflow"], "F0_perfiles", params={"huella": res["huella"], "K": cfg["perfil"]["latente"]["K"],
                                                             "redes": cfg["perfil"]["latente"]["redes"],
                                                             "cortes": cortes or [], "completo": completo}) as run:
        if completo:
            if progreso:
                progreso("  ajuste completo: redes y posterior…", flush=True)
            D, cj = flujo.conjunto(tabla, cfg_norm, None, progreso=progreso)
            t = _filas_latente(tabla, temporadas)
            lat, meta_lat = latente_ensemble(D, cj, t, cfg, cfg_norm, progreso, liberar_lu=True)
            lat = pd.concat([t[["persona_id", "liga", "temporada", "player_id", "min"]].rename(
                columns={"persona_id": "persona_norm"}), lat], axis=1)
            meta_lat.pop("_rapidas", None)
            meta = {"version": cfg["version"], "ajuste": "completo", "huella_config": res["huella"], "latente": meta_lat,
                    "filas_ajuste": int(len(D.t)), "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "temporadas": {}}
            out = dir_perfiles(cfg)
            for temp in temporadas:
                p = perfil_temporada(temp, lat, cfg)
                p.to_csv(out / f"{temp}.csv.gz", index=False, float_format="%.5g")
                meta["temporadas"][temp] = resumen_perfil(p, cfg)
                if progreso:
                    g = meta["temporadas"][temp]["global"]
                    progreso(f"  {temp}: {g['filas']} filas · latente {g['latente']:.3f} · estilos {g['estilos']:.3f} · "
                             f"θ {g['theta']:.3f} · rol {g['rol']:.3f} · completo {g['completo']:.3f}", flush=True)
            (out / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
            res["completo"] = meta
            run.metricas({"filas_completo": sum(v["global"]["filas"] for v in meta["temporadas"].values()),
                          "r2_alineamiento_medio": meta_lat.get("r2_alineamiento_medio") or 0.0})
            run.artefacto(out / "meta.json")
        for a in (cortes or []):
            temps_a = [tp for tp in temporadas if int(tp[:4]) <= a]
            if progreso:
                progreso(f"  corte ≤ {a}: redes y posterior…", flush=True)
            cfg_a = C3.con(cfg_norm, **{"referencia_salida.temporada": temp_de(a)})
            D, cj = flujo.conjunto(tabla, cfg_a, a, progreso=progreso)
            t = _filas_latente(tabla, temps_a)
            lat, meta_lat = latente_ensemble(D, cj, t, cfg, cfg_a, progreso, liberar_lu=True)
            lat = pd.concat([t[["persona_id", "liga", "temporada", "player_id", "min"]].rename(
                columns={"persona_id": "persona_norm"}), lat], axis=1)
            meta = {"version": cfg["version"], "ajuste": f"<= {a}", "corte": a, "huella_config": res["huella"],
                    "latente": meta_lat, "filas_ajuste": int(len(D.t)), "generado": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "temporadas": {}, "theta": "V32_corte"}
            try:
                th = theta_corte(a, temps_a, tabla, cfg, D, cj, progreso, rapidas=meta_lat.pop("_rapidas", None))
            except Exception as exc:  # noqa: BLE001 — se informa en meta; los perfiles salen sin θ (aviso sin_theta)
                th = None
                meta["theta"] = f"ERROR: {type(exc).__name__}: {exc}"
                if progreso:
                    progreso(f"    θ ≤ {a} no disponible ({exc}); perfiles del corte sin θ", flush=True)
            out = dir_perfiles(cfg, a)
            for temp in temps_a:
                th_t = None
                if th is not None:
                    th_t = th[th["temporada"] == temp]
                else:
                    th_t = capacidad(cfg, temp)
                    for m in rasgos(cfg):
                        th_t[f"{m}_th"] = np.nan
                        th_t[f"{m}_vj"] = np.nan
                p = perfil_temporada(temp, lat, cfg, theta=th_t)
                p.to_csv(out / f"{temp}.csv.gz", index=False, float_format="%.5g")
                meta["temporadas"][temp] = resumen_perfil(p, cfg)
            (out / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
            res["cortes"][a] = meta
            run.artefacto(out / "meta.json")
        run.metricas({"tiempo_s": time.time() - t0})
    res["tiempo_s"] = round(time.time() - t0)
    return res
