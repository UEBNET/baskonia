"""F6.2 · Efectos de liga por mínimos cuadrados generalizados (GLS), estáticos, sin fugas para el examen.

El mismo modelo de la F6.1 (bbnorm5/ligas/modelo.py) sin la dinámica entre temporadas ni la correlación entre métricas:

    d_pm = λ_b,m − λ_a,m + β_mᵀ Δx_p + e,   e ~ N(0, var_pm + σ_c,m²)

con un prior débil λ ~ N(0, (2·DT(d))²) que sólo pesa en las ligas sin puentes. Es lineal y gaussiano: solución
cerrada (media y covarianza de λ). σ_c² se estima por momentos, iterando. Para el examen fuera de tiempo se ajusta sólo
con los puentes de temporadas anteriores al corte, sin fugas. La NUTS de la F6.1 (todas las temporadas, con dinámica y
correlación) es la que se publica; aquí se comprueba que ambas coinciden.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from bbnorm5.ligas import datos as LD

REF = "acb"


def ajustar(p: pd.DataFrame, metrica: str, ligas: list[str] | None = None, iter_sc: int = 10) -> dict:
    x = p[p["metrica"] == metrica]
    ligas = ligas or sorted(set(x["liga_a"]) | set(x["liga_b"]) | {REF})
    ligas = [REF] + [l for l in ligas if l != REF]
    il = {l: i for i, l in enumerate(ligas)}
    n, L, K = len(x), len(ligas) - 1, len(LD.CONTEXTO)
    A = np.zeros((n, L))
    ia, ib = x["liga_a"].map(il).to_numpy(), x["liga_b"].map(il).to_numpy()
    r = np.arange(n)
    A[r[ib > 0], ib[ib > 0] - 1] += 1
    A[r[ia > 0], ia[ia > 0] - 1] -= 1
    X = np.c_[A, x[LD.CONTEXTO].to_numpy(float)]
    y = x["d"].to_numpy(float)
    v = x["var"].to_numpy(float)
    pr = np.r_[np.full(L, 1 / (2 * y.std()) ** 2), np.full(K, 1 / 0.5 ** 2)]
    s2 = 0.0
    for _ in range(iter_sc):
        w = 1 / (v + s2)
        H = X.T @ (X * w[:, None]) + np.diag(pr)
        b = np.linalg.solve(H, X.T @ (w * y))
        res = y - X @ b
        s2_new = max(float(np.mean(res ** 2 - v)), 0.0)
        if abs(s2_new - s2) < 1e-6:
            break
        s2 = s2_new
    cov = np.linalg.inv(H)
    lam = np.r_[0.0, b[:L]]
    cl = np.zeros((L + 1, L + 1))
    cl[1:, 1:] = cov[:L, :L]
    return {"ligas": ligas, "lambda": lam, "cov": cl, "beta": b[L:], "s_c2": s2, "n": n}


def todas(p: pd.DataFrame, metricas: list[str]) -> dict:
    return {m: ajustar(p, m) for m in metricas}


def diferencia(mod: dict, a: str, b: str) -> tuple[float, float]:
    """λ_b − λ_a y su varianza; (nan, nan) si alguna liga no está en el grafo."""
    il = {l: i for i, l in enumerate(mod["ligas"])}
    if a not in il or b not in il:
        return np.nan, np.nan
    i, j = il[a], il[b]
    return mod["lambda"][j] - mod["lambda"][i], mod["cov"][i, i] + mod["cov"][j, j] - 2 * mod["cov"][i, j]
