"""F9 bis · Métricas derivadas de las de la v5 para cubrir las de la v3.2 que no tienen verosimilitud propia.

1. **TS% y eFG%**, desde T2%, T3%, TL%, 3PAr y FTr (tasas en fracción):
       eFG = (1 − 3PAr)·T2 + 1,5·3PAr·T3
       TS  = [2(1 − 3PAr)·T2 + 3·3PAr·T3 + FTr·TL] / [2(1 + 0,44·FTr)]
   La incertidumbre se propaga con draws conjuntos en la escala del enlace: la marginal de cada componente se
   reconstruye desde sus cuantiles publicados (mediana y percentiles 10 y 90: η = enlace(q50), σ = [enlace(q90) −
   enlace(q10)] / 2,563) y la correlación es la de las capacidades de la capa latente (F5,
   `correlacion_capacidades.csv`). SUPUESTO: la del predictivo se aproxima con la misma correlación.
2. **Variantes «por 100 posesiones»** de la v3.2, desde la tasa de la v5 por su oportunidad y la razón
   oportunidades / posesiones en pista de la liga (temporada de referencia):
       OREB/100 = OREB% · oreb_op/pos · 100;   DREB/100 = DREB% · dreb_op/pos · 100;   BLK/100 = BLK% · blk_op/pos · 100
       STL% = STL/100 = robos por posesión · 100 (la oportunidad de la v5 ya es la posesión del rival);
       PF/100 = faltas por minuto · min/pos · 100.
   La razón es la de la liga, no la del jugador: es una conversión de unidades, no un modelo (SUPUESTO).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import special, stats

from bbnorm5 import config as C

COMPONENTES = ["t2_pct", "t3_pct", "tl_pct", "tpar", "ftr"]
ENLACE = {"t2_pct": "logit", "t3_pct": "logit", "tl_pct": "logit", "tpar": "logit", "ftr": "log"}
# v3.2 ← (métrica v5, razón de exposición o None)
POR_100 = {"oreb_p100": ("oreb_pct", "oreb_op"), "dreb_p100": ("dreb_pct", "dreb_op"),
           "blk_p100": ("blk_pct", "blk_op"), "stl_pct": ("stl_p100", None), "pf_p100": ("pf_p40", "min")}
Z90 = stats.norm.ppf(0.9)


def _enlace(x, e):
    x = np.clip(np.asarray(x, float), 1e-6, None)
    return special.logit(np.clip(x, 1e-6, 1 - 1e-6)) if e == "logit" else np.log(x)


def _inv(z, e):
    return special.expit(z) if e == "logit" else np.exp(z)


def correlacion() -> np.ndarray:
    c = pd.read_csv(C.DIR_DATOS / "latente" / "correlacion_capacidades.csv", index_col=0)
    return c.loc[COMPONENTES, COMPONENTES].to_numpy(float)


def razones(anio_ref: dict | None = None) -> pd.DataFrame:
    """Razón oportunidades / posesiones en pista por liga y temporada (suma de los jugadores-partido)."""
    d = pd.read_parquet(C.DIR_DATOS / "medida" / "partidos.parquet",
                        columns=["liga", "temporada", "poss_on", "oreb_op", "dreb_op", "blk_op", "min"])
    g = d.groupby(["liga", "temporada"]).sum()
    return g[["oreb_op", "dreb_op", "blk_op", "min"]].div(g["poss_on"], axis=0).reset_index()


def tiro_compuesto(q: dict, R: np.ndarray, rng, n: int = 400, cuantiles=(0.1, 0.25, 0.5, 0.75, 0.9)) -> dict:
    """`q[m]` = (q10, q50, q90) de cada componente (arrays por caso, tasas en fracción). Devuelve cuantiles de eFG y TS."""
    L = np.linalg.cholesky(R + 1e-9 * np.eye(len(R)))
    k = len(q[COMPONENTES[0]][1])
    z = rng.standard_normal((k, n, len(COMPONENTES))) @ L.T
    t = {}
    for j, m in enumerate(COMPONENTES):
        e = ENLACE[m]
        lo, c, hi = (_enlace(v, e) for v in q[m])
        s = np.maximum((hi - lo) / (2 * Z90), 1e-6)
        t[m] = _inv(c[:, None] + s[:, None] * z[:, :, j], e)
    efg = (1 - t["tpar"]) * t["t2_pct"] + 1.5 * t["tpar"] * t["t3_pct"]
    ts = (2 * (1 - t["tpar"]) * t["t2_pct"] + 3 * t["tpar"] * t["t3_pct"] + t["ftr"] * t["tl_pct"]) / \
        (2 * (1 + 0.44 * t["ftr"]))
    out = {}
    for nom, v in (("efg_pct", efg), ("ts_pct", ts)):
        qs = np.nanquantile(v, cuantiles, axis=1)
        out[nom] = {c: qs[i] for i, c in enumerate(cuantiles)}
        out[nom]["media"] = np.nanmean(v, axis=1)
    return out


def por_100(valor: np.ndarray, metrica_v32: str, razon: np.ndarray | float) -> np.ndarray:
    """Convierte una tasa de la v5 (fracción por su oportunidad) a la unidad de la v3.2 «por 100 posesiones»."""
    m5, col = POR_100[metrica_v32]
    r = 1.0 if col is None else razon
    return np.asarray(valor, float) * r * 100
