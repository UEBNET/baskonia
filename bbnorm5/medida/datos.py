"""F3.1 · Datos de la capa de medida: aciertos k y oportunidades reales n por métrica, por partido y por unidad.

Unidad de medida: persona_v5 × liga × temporada, **temporada regular** (los equipos de una misma liga se suman: el
nivel del jugador en esa liga-temporada es uno). Los playoffs quedan fuera de la medida (otro contexto, F6).

Mitades por fecha: los partidos de cada unidad se ordenan por fecha (y por game_id a igualdad); la primera mitad son
los ⌈G/2⌉ primeros. Es la validación decisiva de la F3: ajustar con la primera mitad y predecir la segunda.
RIESGO: BNXT, BSL y GBL tienen fecha aproximada (modificación del fichero, F2 §3); el orden puede alterarse en
partidos cercanos, no entre meses.

Rol (media a priori): pos3 de la tabla de la F1 (E exterior, A alero, I interior); sin posición → «X».
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from bbnorm5 import config as C

DIR = C.DIR_DATOS / "medida"

# nombre → (familia, aciertos k, oportunidades n, descripción)
METRICAS = {
    "t2_pct": ("binomial", "fg2m", "fg2a", "T2%: canastas de dos / tiros de dos"),
    "t3_pct": ("binomial", "fg3m", "fg3a", "T3%: triples / intentos de triple"),
    "tl_pct": ("binomial", "ftm", "fta", "TL%: libres / intentos de libre"),
    "tpar": ("binomial", "fg3a", "fga", "3PAr: intentos de triple / tiros de campo"),
    "oreb_pct": ("binomial", "oreb", "oreb_op", "OREB%: rebotes ofensivos / disponibles en pista"),
    "dreb_pct": ("binomial", "dreb", "dreb_op", "DREB%: rebotes defensivos / disponibles en pista"),
    "ast_pct": ("binomial", "ast", "ast_op", "AST%: asistencias / canastas de compañeros en pista"),
    "tov_pct": ("binomial", "tov", "plays", "TOV%: pérdidas / jugadas propias"),
    "blk_pct": ("binomial", "blk", "blk_op", "BLK%: tapones / tiros de dos del rival en pista"),
    "stl_p100": ("poisson", "stl", "stl_op", "Robos por posesión del rival en pista"),
    "pf_p40": ("poisson", "pf", "min", "Faltas por minuto"),
    "ftr": ("poisson", "fta", "fga", "FTr: tiros libres intentados por tiro de campo"),
    "pts_p100": ("normal", "pts", "poss_on", "Puntos por posesión en pista"),
    "usg_pct": ("normal", "plays", "usg_op", "USG%: jugadas propias / jugadas del equipo en pista"),
}
METRICAS_BASE = dict(METRICAS)          # las 14 de la F3 (las que usa la capa latente, F5)
# F9 bis: métricas de jugada a jugada de la v3.2 (sólo ligas con jugada a jugada; zonas sólo con coordenadas válidas)
METRICAS_PBP = {
    "pct_aro": ("binomial", "fga_aro", "fga_pbp", "% de sus tiros de campo en el aro (< 1,8 m)"),
    "pct_corta": ("binomial", "fga_corta", "fga_pbp", "% de sus tiros de campo cortos (1,8–4,25 m)"),
    "pct_media": ("binomial", "fga_media", "fga_pbp", "% de sus tiros de campo de media distancia"),
    "pct_t3_esquina": ("binomial", "fga_t3_esquina", "fga_pbp", "% de sus tiros de campo que son triples de esquina"),
    "pct_asistidas": ("binomial", "fgm_asist", "fgm_pbp", "% de sus canastas que son asistidas"),
}
METRICAS.update(METRICAS_PBP)
CLAVE = ["persona_v5", "liga", "temporada"]


def _pos3(temporadas: list[str]) -> pd.Series:
    from bbnorm5.diagnostico import datos_f1
    t, _ = datos_f1.tabla({"datos": {"temporadas": temporadas}})
    t = t[["liga", "temporada", "player_id", "pos3"]].dropna().astype(str).drop_duplicates(["liga", "temporada", "player_id"])
    return t.set_index(["liga", "temporada", "player_id"])["pos3"]


def partidos(temporadas: list[str]) -> pd.DataFrame:
    """Una fila por jugador-partido de temporada regular con persona, rol, mitad y las columnas k y n de cada métrica."""
    from bbnorm5.datos import puentes as P
    d = P.caja(temporadas)
    d = d[d["fase"] == "regular"]
    per = pd.read_csv(C.DIR_DATOS / "limpios" / "entidades" / "personas_v5.csv", dtype=str)
    p = per.set_index(["fuente_liga", "fuente_id"])["persona_v5"]
    d = d.assign(persona_v5=[p.get((l, i)) for l, i in zip(d["liga"], d["player_id"])]).dropna(subset=["persona_v5"])
    d = P.exposiciones(d)
    d = d[d["min"] > 0]
    fp = C.DIR_DATOS / "medida" / "pista_partidos.parquet"
    if fp.exists():          # F9 bis: zonas y asistidas por partido (bbnorm5.datos.pista_partido)
        pp = pd.read_parquet(fp)
        d = d.merge(pp, on=["liga", "temporada", "game_id", "player_id"], how="left")
    pos = _pos3(temporadas)
    d["rol"] = [pos.get(x, "X") for x in zip(d["liga"], d["temporada"], d["player_id"])]
    # rol de la unidad: el de más minutos
    r = d.groupby(CLAVE + ["rol"])["min"].sum().reset_index().sort_values("min").drop_duplicates(CLAVE, keep="last")
    d = d.drop(columns="rol").merge(r[CLAVE + ["rol"]], on=CLAVE)
    d = d.sort_values(CLAVE + ["fecha", "game_id"]).reset_index(drop=True)
    orden = d.groupby(CLAVE).cumcount()
    g = d.groupby(CLAVE)["game_id"].transform("size")
    d["mitad"] = np.where(orden < np.ceil(g / 2), 1, 2)
    cols = set(CLAVE + ["rol", "mitad", "fecha", "game_id", "team_id", "min"])
    for fam, k, n, _ in METRICAS.values():
        cols |= {k, n}
    return d[[c for c in d.columns if c in cols]]


def unidad_metrica(d: pd.DataFrame, metrica: str, mitad: int | None = None) -> pd.DataFrame:
    """Suficientes por unidad para una métrica: K = Σk, N = Σn, G partidos con n > 0, y las sumas por partido que
    piden los estimadores de dispersión dentro de jugador: S2 = Σ k²/n (normal), Sk2 = Σk², Skn = Σ k·n, N2g = Σ n²,
    N3g = Σ n³ (binomial y Poisson)."""
    fam, k, n, _ = METRICAS[metrica]
    x = d if mitad is None else d[d["mitad"] == mitad]
    x = x[x[n] > 0]
    kk, nn = x[k].astype(float), x[n].astype(float)
    if fam == "binomial":
        nn = np.maximum(nn, kk)          # oportunidades estimadas por debajo de los aciertos: se iguala (SUPUESTO)
    t = pd.DataFrame({**{c: x[c] for c in CLAVE + ["rol"]}, "k": kk, "n": nn, "k2n": kk ** 2 / nn, "n2": nn ** 2,
                      "k2": kk ** 2, "kn": kk * nn, "n3": nn ** 3})
    u = t.groupby(CLAVE + ["rol"], sort=False).agg(K=("k", "sum"), N=("n", "sum"), G=("k", "size"), S2=("k2n", "sum"),
                                                    N2g=("n2", "sum"), Sk2=("k2", "sum"), Skn=("kn", "sum"),
                                                    N3g=("n3", "sum")).reset_index()
    return u


def construir(temporadas: list[str]) -> pd.DataFrame:
    DIR.mkdir(parents=True, exist_ok=True)
    d = partidos(temporadas)
    d.to_parquet(DIR / "partidos.parquet")
    return d


def cargar() -> pd.DataFrame:
    return pd.read_parquet(DIR / "partidos.parquet")
