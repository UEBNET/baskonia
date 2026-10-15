"""Paso 1 — Quitar la suerte (bayes empírico).

Idea para el ojeador: un jugador con 80 minutos y un 60 % en triples no es un tirador del 60 %;
es un tirador normal con una buena racha. Cuanta menos muestra tiene un jugador, más hay que
acercar su número a lo habitual entre los de su posición en su liga.

Modelo, para cada métrica (en su escala transformada, ver metricas.py) y cada grupo
g = (liga, temporada, posición):
    valor observado   y_i = θ_i + ruido_i,   ruido_i ~ N(0, σ² / n_i)
    capacidad real    θ_i ~ N(μ_g, τ²)
  * n_i es la exposición del jugador (minutos, tiros...). Más exposición, menos ruido.
  * σ² (ruido por unidad de exposición) se estima por liga; τ² (cuánto difieren de verdad los
    jugadores entre sí) por liga y posición; μ_g por liga, temporada y posición.
  * Se estiman por momentos: dentro de un grupo, E[(y − μ)²] = τ² + σ²/n. Se ajusta una recta
    de (y − μ)² contra 1/n: la ordenada es τ² y la pendiente σ².

Salida por jugador, ya estandarizada dentro de su grupo (z = 0 es el jugador medio de su posición
en su liga y temporada; z = 1, una desviación típica de capacidad por encima):
    z_obs   (y − μ_g) / τ          valor observado estandarizado
    v_obs   σ² / (n τ²)            varianza del ruido de muestra, en las mismas unidades
    z_post  z_obs · 1/(1 + v_obs)  estimación sin suerte (encogida hacia 0 según la muestra)
    v_post  v_obs / (1 + v_obs)    su incertidumbre
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .metricas import CATALOGO, EXPOSICIONES, transformar

MIN_EXPOSICION_AJUSTE = {"min": 100, "pos": 200, "tsa": 40, "fga": 40, "fg3a": 25, "fg2a": 25, "fta": 15, "plays": 50,
                         "fga_pbp": 40, "fgm_pbp": 20, "rposs": 300}


def _media_ponderada(y, w, grupos):
    g = np.asarray(grupos)
    num = pd.Series(y * w).groupby(g).sum()
    den = pd.Series(w).groupby(g).sum()
    return (num / den).reindex(g).to_numpy()


def valor_y_exposicion(t: pd.DataFrame, col: str) -> tuple[np.ndarray, np.ndarray]:
    """Métrica en escala transformada (recortada) y su exposición, fila a fila.
    Muestras minúsculas dan valores imposibles (TS% de 795 con medio intento): se recortan a los
    percentiles 0,5-99,5 de los jugadores con exposición suficiente; su peso ya es casi nulo."""
    m = CATALOGO[col]
    y = transformar(pd.to_numeric(t[col], errors="coerce"), m.transf)
    n = pd.to_numeric(t[EXPOSICIONES[m.exposicion]], errors="coerce").to_numpy(float)
    ref = y[np.isfinite(y) & (n >= MIN_EXPOSICION_AJUSTE[m.exposicion])]
    if len(ref):
        lo, hi = np.quantile(ref, [0.005, 0.995]); span = hi - lo
        y = np.clip(y, lo - 0.25 * span, hi + 0.25 * span)
    return y, n


def ajustar_metrica(t: pd.DataFrame, col: str, iter_: int = 4) -> tuple[pd.DataFrame, dict]:
    """Devuelve (filas con z_obs, v_obs, z_post, v_post; parámetros estimados)."""
    m = CATALOGO[col]
    y, n = valor_y_exposicion(t, col)
    ok = np.isfinite(y) & np.isfinite(n) & (n > 0) & t["pos3"].notna().to_numpy()
    d = t.loc[ok, ["liga", "temporada", "pos3"]].copy()
    d["y"] = y[ok]; d["n"] = n[ok]
    d["g"] = d["liga"] + "|" + d["temporada"] + "|" + d["pos3"]
    d["lp"] = d["liga"] + "|" + d["pos3"]
    ajuste = d["n"] >= MIN_EXPOSICION_AJUSTE[m.exposicion]

    # El ruido por unidad de exposición (σ²) es común a todas las ligas cuando la exposición son
    # TIROS: el azar de un tiro no depende de la liga. Cuando son minutos o posesiones, se estima
    # por liga, porque el ritmo cambia cuánto «pasa» en cada minuto.
    por_tiro = m.exposicion in ("tsa", "fga", "fg3a", "fg2a", "fta", "plays")
    d["gs"] = "todas" if por_tiro else d["liga"]   # grupo que comparte σ²

    # arranque: la mitad de la varianza para cada componente
    sigma2 = d.groupby("gs")["y"].var().mul(0.5 * d["n"].median()).to_dict()
    tau2 = d[ajuste].groupby("lp")["y"].var().mul(0.5).to_dict()
    for _ in range(iter_):
        s2 = d["gs"].map(sigma2).to_numpy(); t2 = d["lp"].map(tau2).to_numpy()
        w = 1.0 / (t2 + s2 / d["n"].to_numpy())
        d["mu"] = _media_ponderada(d["y"].to_numpy(), w, d["g"])
        r2 = (d["y"] - d["mu"]) ** 2
        # recta r² = τ²_{liga,pos} + σ² · (1/n), mínimos cuadrados ponderados
        for gs, dl in d[ajuste].groupby("gs"):
            pos = sorted(dl["lp"].unique())
            X = np.column_stack([(dl["lp"] == p).to_numpy(float) for p in pos] + [1.0 / dl["n"].to_numpy()])
            ww = 1.0 / (dl["lp"].map(tau2).to_numpy() + sigma2[gs] / dl["n"].to_numpy()) ** 2
            beta, *_ = np.linalg.lstsq(X * np.sqrt(ww)[:, None], r2[dl.index].to_numpy() * np.sqrt(ww), rcond=None)
            vt = dl["y"].var()
            sigma2[gs] = float(max(beta[-1], 1e-6 * vt * dl["n"].median()))
            for p, b in zip(pos, beta[:-1]):
                tau2[p] = float(max(b, 0.02 * vt))   # suelo: τ² no puede ser 0 (habría un solo tipo de jugador)

    s2 = d["gs"].map(sigma2).to_numpy(); t2 = d["lp"].map(tau2).to_numpy()
    tau = np.sqrt(t2)
    z_obs = (d["y"].to_numpy() - d["mu"].to_numpy()) / tau
    v_obs = s2 / (d["n"].to_numpy() * t2)
    out = pd.DataFrame(index=t.index, columns=["mu", "tau", "z_obs", "v_obs", "z_post", "v_post"], dtype=float)
    out.loc[ok, "mu"] = d["mu"].to_numpy(); out.loc[ok, "tau"] = tau
    out.loc[ok, "z_obs"] = z_obs; out.loc[ok, "v_obs"] = v_obs
    out.loc[ok, "z_post"] = z_obs / (1 + v_obs); out.loc[ok, "v_post"] = v_obs / (1 + v_obs)
    grupos = d.groupby("g").agg(mu=("mu", "first"), n_jug=("y", "size")).reset_index()
    params = {"metrica": col, "sigma2": sigma2, "tau2": tau2,
              "mu": {g: float(v) for g, v in zip(grupos["g"], grupos["mu"])},
              "fiabilidad_media": {liga: float(np.median(1 / (1 + v_obs[(d["liga"] == liga).to_numpy() & ajuste.to_numpy()])))
                                   for liga in sorted(d["liga"].unique())}}
    return out, params
