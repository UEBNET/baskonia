"""Acceso a las salidas procesadas (data/processed) que usan las fases 3-5 de bbfit.

Sólo lectura. Todas las funciones devuelven DataFrame vacío si el fichero no existe (nunca inventan datos).
Ids siempre como texto (hay ids con ceros a la izquierda).
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DIR_MOD, DIR_PROC


def temporadas() -> list[str]:
    return sorted(p.name for p in DIR_PROC.iterdir() if p.is_dir() and re.match(r"^\d{4}-\d{2}$", p.name))


def ligas_temporada(temp: str) -> list[str]:
    d = DIR_PROC / temp / "ligas"
    return sorted(p.stem for p in d.glob("*.csv")) if d.exists() else []


def minutos_partido(liga: str, cfg: dict) -> float:
    m = cfg["partido"]["minutos_reglamentarios"]
    return float(m.get(liga, m["defecto"]))


def _leer(p: Path, **kw) -> pd.DataFrame:
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p, low_memory=False, **kw)


def tramos(liga: str, temp: str) -> pd.DataFrame:
    return _leer(DIR_PROC / temp / "quintetos" / liga / "tramos.csv.gz",
                 dtype={"game_id": str, "team_a": str, "team_b": str, "quinteto_a": str, "quinteto_b": str})


def tiros(liga: str, temp: str) -> pd.DataFrame:
    t = _leer(DIR_PROC / temp / "quintetos" / liga / "tiros.csv.gz",
              dtype={"game_id": str, "team_id": str, "player_id": str, "asistente_id": str, "quinteto": str})
    if not t.empty:
        t["anotado"] = t["anotado"].astype(str).str.lower().isin(["true", "1"])
        t["asistente_id"] = t["asistente_id"].replace("", np.nan)
    return t


def validacion(liga: str, temp: str) -> pd.DataFrame:
    return _leer(DIR_PROC / temp / "quintetos" / liga / "validacion.csv", dtype={"game_id": str})


def quintetos_fichero(liga: str, temp: str, nombre: str) -> pd.DataFrame:
    return _leer(DIR_PROC / temp / "quintetos" / liga / nombre,
                 dtype={"team_id": str, "player_id": str, "pasador_id": str, "receptor_id": str,
                        "jugador_a_id": str, "jugador_b_id": str})


def ligas(liga: str, temp: str) -> pd.DataFrame:
    return _leer(DIR_PROC / temp / "ligas" / f"{liga}.csv",
                 dtype={"player_id": str, "team_id": str, "equipo_codigo": str})


def entrenadores_partidos(liga: str, temp: str) -> pd.DataFrame:
    return _leer(DIR_PROC / temp / "entrenadores" / f"{liga}_partidos.csv", dtype=str)


def contexto(temp: str) -> pd.DataFrame:
    return _leer(DIR_MOD / "contexto" / f"{temp}.csv", dtype={"team_id": str, "player_id": str})


@lru_cache(maxsize=1)
def crosswalk() -> pd.DataFrame:
    """(fuente_liga, fuente_id) → persona_id (identidad entre ligas y temporadas; bbmodel/crosswalk.py)."""
    p = DIR_PROC / "player_id_crosswalk.csv"
    if not p.exists():
        return pd.DataFrame(columns=["fuente_liga", "fuente_id", "persona_id"])
    return pd.read_csv(p, dtype=str, usecols=["fuente_liga", "fuente_id", "persona_id", "confianza"])


def persona(liga: str, player_ids: pd.Series) -> pd.Series:
    """persona_id del crosswalk; si falta, «<liga>:<player_id>» (y queda marcado por el prefijo)."""
    cw = crosswalk()
    m = cw[cw["fuente_liga"] == liga].drop_duplicates("fuente_id").set_index("fuente_id")["persona_id"]
    out = player_ids.map(m)
    return out.where(out.notna(), liga + ":" + player_ids.astype(str))


# --------------------------------------------------------------------------------------------- posición

def _sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def normalizar_posicion(raw) -> object:
    """Variantes de texto (FEB: «Ala-Pívot», «A-piv»…) a las etiquetas que entiende bbmodel.posicion."""
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return raw
    t = _sin_acentos(str(raw)).strip()
    if re.match(r"^a(la)?[- ]?piv", t):
        return "Ala-pívot"
    if t.startswith("piv"):
        return "Pívot"
    if t == "base":
        return "Base"
    if t == "escolta":
        return "Escolta"
    if t == "alero":
        return "Alero"
    return raw


def pos3_temporada(temp: str, filas: pd.DataFrame | None = None) -> pd.DataFrame:
    """pos3 (E/A/I) por (liga, player_id) en una temporada: oficial si la fuente la publica, estimada si no
    (bbmodel.posicion.asignar, regresión con el perfil estadístico). pos3_estimada: 0 oficial, 1 estimada,
    2 elegida entre una pista de la fuente; NaN = sin dato."""
    from bbmodel import posicion as P
    if filas is None:
        partes = []
        for liga in ligas_temporada(temp):
            d = ligas(liga, temp)
            if d.empty:
                continue
            partes.append(d[d["fase"] == "regular"])
        if not partes:
            return pd.DataFrame(columns=["liga", "player_id", "pos3", "pos3_estimada"])
        filas = pd.concat(partes, ignore_index=True)
    t = filas.copy()
    t["posicion"] = t["posicion"].map(normalizar_posicion)
    t["min"] = pd.to_numeric(t["min"], errors="coerce").fillna(0)
    for c in P.RASGOS:
        if c not in t:
            t[c] = np.nan
    try:
        t, _ = P.asignar(t)
    except Exception:          # sin posiciones oficiales suficientes: sólo las oficiales
        of = t["posicion"].map(P.oficial)
        t["pos3"] = of.map(lambda x: x[0])
        t["pos3_estimada"] = np.where(t["pos3"].notna(), 0, np.nan)
    t = t.sort_values("min", ascending=False).drop_duplicates(["liga", "player_id"])
    return t[["liga", "player_id", "pos3", "pos3_estimada"]].reset_index(drop=True)
