"""Carga de datos: de los CSV de bbstats a una tabla «jugador-liga-temporada».

Los CSV procesados tienen una fila por jugador-EQUIPO-fase. Un jugador traspasado dentro de una
liga aparece en varias filas (una por equipo). Para modelizar necesitamos una fila por
jugador-LIGA-temporada, así que aquí:
  * nos quedamos con la temporada regular (la muestra más grande y comparable);
  * sumamos los totales (minutos, tiros, posesiones...) de todos sus equipos en esa liga;
  * para cada métrica de tasa hacemos la media ponderada por su «exposición» (minutos, tiros...),
    que es la forma correcta de combinar tasas de dos equipos;
  * el equipo «principal» es el de más minutos.
"""
from __future__ import annotations

import glob
from pathlib import Path

import numpy as np
import pandas as pd

from .identidad import clave_nombre
from .metricas import CATALOGO, EXPOSICIONES

RAIZ = Path(__file__).resolve().parent.parent
DIR_PROCESADOS = RAIZ / "data" / "processed"

# Columnas de identidad y contexto que se conservan
COLS_ID = ["liga", "temporada", "player_id", "nombre", "posicion", "edad", "fecha_nacimiento", "altura_cm",
           "nacionalidad", "team_id", "equipo", "gp", "min", "team_gp", "team_pace", "minutos_partido"]
# Totales que se suman entre equipos (para exposiciones y para recalcular)
COLS_SUMA = ["gp", "min", "fga", "fta", "fg3a", "fg2a", "tov", "poss_on_court"]


def temporadas_disponibles(dir_procesados: Path = DIR_PROCESADOS) -> list[str]:
    return sorted(p.name for p in Path(dir_procesados).iterdir() if p.is_dir() and (p / "ligas").exists())


def cargar_filas(fase: str = "regular", temporadas: list[str] | None = None,
                 dir_procesados: Path = DIR_PROCESADOS) -> pd.DataFrame:
    """Lee todos los CSV (liga x temporada) y devuelve las filas de una fase."""
    temporadas = temporadas or temporadas_disponibles(dir_procesados)
    metricas = sorted({m.col for m in CATALOGO.values()})
    usar = sorted(set(COLS_ID + COLS_SUMA + metricas))
    frames = []
    for t in temporadas:
        for f in sorted(glob.glob(str(Path(dir_procesados) / t / "ligas" / "*.csv"))):
            d = pd.read_csv(f, low_memory=False, dtype={"player_id": str, "team_id": str},
                            usecols=lambda c: c in usar or c == "fase")
            frames.append(d[d["fase"] == fase])
    df = pd.concat(frames, ignore_index=True)
    for c in usar:
        if c not in df:
            df[c] = np.nan
    return df


def tabla_jugador_liga(filas: pd.DataFrame) -> pd.DataFrame:
    """Una fila por (liga, temporada, player_id), combinando sus equipos dentro de la liga."""
    filas = filas.copy()
    filas["min"] = pd.to_numeric(filas["min"], errors="coerce").fillna(0)
    # La BBL da un id distinto por equipo y temporada: un jugador traspasado tendría dos ids.
    # Allí se usa como id el nombre normalizado (estable entre equipos y temporadas).
    bbl = filas["liga"] == "bbl"
    claves = filas.loc[bbl, "nombre"].map(clave_nombre)
    filas.loc[bbl, "player_id"] = np.where(claves.notna(), "n:" + claves.fillna(""), filas.loc[bbl, "player_id"])
    filas["tsa"] = filas["fga"].fillna(0) + 0.44 * filas["fta"].fillna(0)
    filas["plays"] = filas["tsa"] + filas["tov"].fillna(0)
    clave = ["liga", "temporada", "player_id"]

    # 1) totales sumados
    tot = filas.groupby(clave, sort=False)[COLS_SUMA + ["tsa", "plays"]].sum(min_count=1)

    # 2) identidad: equipo principal = el de más minutos
    filas = filas.sort_values("min", ascending=False)
    ident = filas.groupby(clave, sort=False).first()[[c for c in COLS_ID if c not in clave + ["gp", "min"]]]
    ident["n_equipos"] = filas.groupby(clave, sort=False)["team_id"].nunique()

    # 3) métricas: media ponderada por la exposición de cada una
    out = tot.join(ident)
    for m in CATALOGO.values():
        exp_col = EXPOSICIONES[m.exposicion]
        x = pd.to_numeric(filas[m.col], errors="coerce")
        w = pd.to_numeric(filas[exp_col], errors="coerce").fillna(0)
        ok = x.notna() & (w > 0)
        num = (x.where(ok, 0) * w.where(ok, 0)).groupby([filas[k] for k in clave]).sum()
        den = w.where(ok, 0).groupby([filas[k] for k in clave]).sum()
        out[m.col] = (num / den.replace(0, np.nan)).reindex(out.index)
    out = out.reset_index()
    out["anio"] = out["temporada"].str[:4].astype(int)
    return out


def cargar(fase: str = "regular", temporadas: list[str] | None = None) -> pd.DataFrame:
    """Atajo: tabla jugador-liga-temporada de la fase pedida."""
    return tabla_jugador_liga(cargar_filas(fase, temporadas))
