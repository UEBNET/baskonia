"""F1 · Datos de la auditoría: la misma tabla jugador-liga-temporada que usan la v1 y la v3.2.

`bbmodel.modelo.preparar()` (temporada regular, equipos de una liga sumados, identidad persona_id entera de bbmodel con
las uniones del crosswalk ≥ 0,75, posición pos3) + transformación y exposición de cada métrica de
`bbmodel.suerte.valor_y_exposicion`. Así la descomposición mide el ruido del mismo dato del que parten los modelos.
Caché (no versionada) en experimentos/v5/.
"""
from __future__ import annotations

import pickle

import numpy as np
import pandas as pd

from bbnorm5 import config as C

DIR_CACHE = C.RAIZ / "experimentos" / "v5"


def entradas_procesadas(temporadas: list[str]) -> list:
    """Ficheros de los que depende la tabla (para el hash de datos de entrada)."""
    fs = []
    for t in temporadas:
        fs += sorted((C.RAIZ / "data" / "processed" / t / "ligas").glob("*.csv"))
    fs += [C.RAIZ / "data" / "processed" / "player_id_crosswalk.csv"]
    fs += sorted((C.RAIZ / "data" / "modelos" / "pista").glob("*"))
    return fs


def tabla(cfg: dict) -> tuple[pd.DataFrame, str]:
    """Tabla jugador-liga-temporada (todas las temporadas de cfg.datos.temporadas) y el hash de sus entradas."""
    from bbmodel import modelo as A
    temps = cfg["datos"]["temporadas"]
    h = C.hash_ficheros(entradas_procesadas(temps))
    f = DIR_CACHE / f"tabla_{h}.pkl"
    if f.exists():
        return pickle.loads(f.read_bytes()), h
    t, info = A.preparar()
    t = t[t["temporada"].isin(temps)].reset_index(drop=True)
    DIR_CACHE.mkdir(parents=True, exist_ok=True)
    f.write_bytes(pickle.dumps(t))
    return t, h


def metrica(t: pd.DataFrame, col: str, min_minutos: float) -> pd.DataFrame:
    """Filas válidas de una métrica: y transformada (recortada como en la v1), exposición n > 0, persona, liga,
    temporada, posición y grupo de σ² (común si la exposición son tiros; por liga si no)."""
    from bbmodel import suerte
    from bbmodel.metricas import CATALOGO
    from bbnorm5.diagnostico.varianza import TIROS
    y, n = suerte.valor_y_exposicion(t, col)
    ok = np.isfinite(y) & np.isfinite(n) & (n > 0) & (pd.to_numeric(t["min"], errors="coerce").to_numpy(float) >= min_minutos)
    d = t.loc[ok, ["persona_id", "liga", "temporada", "anio", "pos3", "min"]].copy()
    d["y"], d["n"] = y[ok], n[ok]
    d["lt"] = d["liga"] + "|" + d["temporada"]
    d["g_s2"] = "todas" if CATALOGO[col].exposicion in TIROS else d["liga"]
    return d.reset_index(drop=True)
