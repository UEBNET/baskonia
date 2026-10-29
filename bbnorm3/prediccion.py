"""Traducción a → b con la posterior completa y examen de cambios de liga (mismos casos que `bbmodel validar`).

Para un jugador de la persona-temporada (i, t) que se traduce a la competición b = (l_b, t_b):
    r_b = (u_it + d(edad)·[t_b > t] + η − μ_b) / s_{l_b}
    ŷ   = decodificador(r_b, l_b, grupo b, p) + ζ_i  (+ equipo ~ N(0, σ²_T) + contexto ~ N(0, ψ) + ruido σ²/n)
(ζ_i: factor específico de la persona en cada métrica, con su incertidumbre a posteriori).
La media y la varianza de (u_it − μ_b) salen de la posterior conjunta (niveles.py), que incluye la covarianza entre
el latente del jugador y el nivel de destino; la no linealidad del decodificador se integra por Monte Carlo.
Deep ensemble: la media es el promedio de las 5 redes y el intervalo sale de la mezcla de sus muestras.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import torch
from scipy.stats import norm

from bbmodel.metricas import CATALOGO, destransformar, transformar

from .datos import METRICAS, Datos, matrices_filas
from .modelo import CVAE
from .niveles import Posterior

Z80 = norm.ppf(0.9)


@torch.no_grad()
def muestras_traduccion(modelo: CVAE, post: Posterior, D: Datos, ps: np.ndarray, comp_b: np.ndarray,
                        grupo_b: np.ndarray, avanzar: np.ndarray, S: int, rng: np.random.Generator,
                        V_obs: np.ndarray | None = None, kappa_extra: np.ndarray | None = None):
    """Muestras (n, S, 33) del valor decodificado (sin ruido) y del valor observado (con equipo, ψ y ruido)."""
    n, K = len(ps), modelo.K
    cfg = modelo.cfg
    eta2 = cfg["prior"]["eta"] ** 2
    kap2 = cfg["prior"]["kappa"] ** 2
    media = post.media[ps] - post.media[post.nPS + comp_b]
    var = np.zeros((n, K))
    nv = post.media.shape[0]
    for j in range(n):
        a = np.zeros(nv)
        a[ps[j]] += 1.0
        a[post.nPS + comp_b[j]] -= 1.0
        var[j] = post.var_contraste(a)
    d = post.drift[D.ps_tramo[ps]]
    media = media + avanzar[:, None] * d
    var = var + avanzar[:, None] * (eta2 + (kap2 if kappa_extra is None else kappa_extra[:, None]))
    liga_b = D.comp_liga[comp_b]
    sb = post.s[liga_b][:, None]
    eps = rng.standard_normal((n, S, K))
    r = (media[:, None, :] + np.sqrt(np.maximum(var, 0))[:, None, :] * eps) / sb[:, :, None]
    rt = torch.as_tensor(r.reshape(n * S, K), dtype=torch.float32)
    lt = torch.as_tensor(np.repeat(liga_b, S), dtype=torch.long)
    gt = torch.as_tensor(np.repeat(grupo_b, S), dtype=torch.long)
    yhat = modelo.decodificar(rt, lt, gt).numpy().reshape(n, S, -1).astype(float)
    psi = (np.exp(modelo.log_psi.numpy()[liga_b]) + cfg["red"]["psi_minimo"])[:, None, :]
    s2T = modelo.s2T.numpy()[None, None, :]
    ruido = psi + s2T + (0.0 if V_obs is None else V_obs[:, None, :])
    if modelo.usar_unicidad:
        # factor específico de la persona: media a posteriori (entrenada) y su varianza (precisión de sus filas)
        per = D.ps_persona[ps]
        zeta = modelo.Z.numpy()[per].astype(float)
        vz = 1.0 / (modelo.precision_unicidad().numpy()[per] + 1.0 / modelo.s2Z.numpy()[None, :])
        yhat = yhat + zeta[:, None, :] + np.sqrt(vz)[:, None, :] * rng.standard_normal(yhat.shape)
    yobs = yhat + np.sqrt(ruido) * rng.standard_normal(yhat.shape)
    return yhat, yobs


def casos_examen(tabla: pd.DataFrame, anio: int) -> pd.DataFrame:
    from bbmodel import validacion
    return validacion.casos(tabla, anio)


def predecir_cambios(conjunto: list[tuple[CVAE, Posterior]], D: Datos, tabla: pd.DataFrame, anio: int,
                     cfg: dict, semilla: int = 0) -> pd.DataFrame:
    """Examen temporal: ajustado con ≤ anio, predice en t+1 a quien cambia de liga (≥ 300 min en ambas)."""
    c = casos_examen(tabla, anio)
    temp_t = f"{anio}-{str(anio + 1)[-2:]}"
    ps_idx = {p: i for i, p in enumerate(D.ps)}
    comp_idx = {x: i for i, x in enumerate(D.comps)}
    grp_idx = {x: i for i, x in enumerate(D.grupos)}
    sel, ps, cb, gb = [], [], [], []
    for k, x in c.iterrows():
        p = ps_idx.get(f"{x['persona_id']}|{anio}")
        cc = comp_idx.get(f"{x['liga_d']}|{temp_t}")
        g = grp_idx.get(f"{x['liga_d']}|{temp_t}|{x['pos3_o']}") if isinstance(x["pos3_o"], str) else None
        if p is None or cc is None or g is None:
            continue
        sel.append(k); ps.append(p); cb.append(cc); gb.append(g)
    c = c.loc[sel].reset_index(drop=True)
    ps, cb, gb = map(np.asarray, (ps, cb, gb))
    dest = tabla.loc[c["index_d"]]
    _, Md, Vd = matrices_filas(dest, D.esc)
    S = int(cfg["prediccion"]["muestras"])
    rng = np.random.default_rng(semilla)
    centros, obs = [], []
    for modelo, post in conjunto:
        yh, yo = muestras_traduccion(modelo, post, D, ps, cb, gb, np.ones(len(ps)), S, rng, V_obs=Vd)
        centros.append(yh.mean(1)); obs.append(yo)
    centro = np.mean(centros, 0)
    mezcla = np.concatenate(obs, 1)
    q10, q90 = np.quantile(mezcla, [0.1, 0.9], axis=1)
    sd = mezcla.std(1)
    filas = []
    for k, col in enumerate(METRICAS):
        m = CATALOGO[col]
        cm, sm = D.esc.c[col], D.esc.s[col]
        real = pd.to_numeric(c[f"{col}_d"], errors="coerce").to_numpy(float)
        ok = np.isfinite(real)
        y_std = (transformar(real, m.transf) - cm) / sm
        f = pd.DataFrame({"metrica": col, "anio": anio, "persona_id": c["persona_id"], "nombre": c["nombre_o"],
                          "liga_o": c["liga_o"], "liga_d": c["liga_d"], "pos3": c["pos3_o"], "real": real,
                          "v3": destransformar(cm + sm * centro[:, k], m.transf),
                          "v3_lo": destransformar(cm + sm * q10[:, k], m.transf),
                          "v3_hi": destransformar(cm + sm * q90[:, k], m.transf),
                          "v3_centro_z": centro[:, k], "v3_sd_z": sd[:, k], "real_z": y_std,
                          "dentro_80_v3": (y_std >= q10[:, k]) & (y_std <= q90[:, k]),
                          "min_d": c["min_d"].to_numpy(float)})
        filas.append(f[ok])
    return pd.concat(filas, ignore_index=True)
