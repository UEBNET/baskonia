"""Rasgos de pista (jugada a jugada) por jugador-equipo-temporada, para los modelos A, B y de estilos.

De la capa de quintetos de bbstats (data/processed/<temp>/quintetos/<liga>/), temporada regular:
  * tiros.csv.gz  → perfil de tiro por zonas (aro, corta, media, triple de esquina y frontal; zonas.py) y
                    canastas asistidas (la fuente enlaza la asistencia con la canasta).
  * jugadores.csv → RAPM (ORAPM, DRAPM) de su liga y temporada y posesiones en pista.

Columnas por fila (liga, temporada, team_id, player_id):
  fga_pbp, fgm_pbp, fgm_asist          tiros de campo con coordenadas, canastas, canastas asistidas
  fga_<zona>, fgm_<zona>                intentos y canastas por zona
  poss_on, min_on                       posesiones y minutos en pista (exposición del RAPM)
  rapm, orapm, drapm                    RAPM de su liga y temporada (puntos por 100 posesiones)
  pct_aro, pct_corta, pct_media, pct_t3_esquina, pct_asistidas   (porcentajes; los calcula datos.py tras sumar)

La calibración de coordenadas (zonas.calibrar) se hace por liga y temporada; si separa 2 y 3 en menos
del 95 % de los tiros, esa liga-temporada queda sin zonas (en blanco).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import zonas as Z

RAIZ = Path(__file__).resolve().parent.parent
DIR_PROC = RAIZ / "data" / "processed"
DIR_SALIDA = RAIZ / "data" / "modelos" / "pista"
ACIERTO_MINIMO = 0.95
CONTEOS = ["fga_pbp", "fgm_pbp", "fgm_asist"] + [f"{p}_{z}" for z in Z.ZONAS for p in ("fga", "fgm")]
PISTA_COLS = CONTEOS + ["poss_on", "min_on", "rapm", "orapm", "drapm"]


def _tiros(liga: str, temporada: str) -> pd.DataFrame:
    p = DIR_PROC / temporada / "quintetos" / liga / "tiros.csv.gz"
    if not p.exists():
        return pd.DataFrame()
    t = pd.read_csv(p, dtype={"team_id": str, "player_id": str, "asistente_id": str},
                    usecols=["fase", "team_id", "player_id", "tipo", "anotado", "asistente_id", "x", "y"])
    return t[t["fase"] == "regular"]


def filas_liga(liga: str, temporada: str, calibracion: dict) -> pd.DataFrame:
    """Rasgos de pista de una liga-temporada (una fila por equipo-jugador)."""
    t = _tiros(liga, temporada)
    out = None
    if not t.empty:
        campo = t[t["tipo"].isin(["T2", "T3"])].copy()
        campo["anotado"] = campo["anotado"].astype(str).str.lower().isin(["true", "1"])
        campo["asist"] = campo["anotado"] & campo["asistente_id"].notna() & (campo["asistente_id"] != "")
        g = campo.groupby(["team_id", "player_id"])
        out = pd.DataFrame({"fgm_pbp": g["anotado"].sum(), "fgm_asist": g["asist"].sum()})
        sis, acierto = Z.calibrar(liga, t)
        calibracion[f"{liga}|{temporada}"] = {"acierto": round(acierto, 4), "aro": [float(v) for v in sis.aro],
                                              "escala": [float(v) for v in sis.escala], "eje_largo": sis.eje_largo,
                                              "regla": sis.regla, "pista_completa": sis.pista_completa}
        if acierto >= ACIERTO_MINIMO:
            p = Z.perfil_tiro(t, sis)
            p["anotado"] = p["anotado"].astype(str).str.lower().isin(["true", "1"])
            gz = p.groupby(["team_id", "player_id", "zona"])
            fga = gz.size().unstack(fill_value=0).reindex(columns=Z.ZONAS, fill_value=0)
            fgm = gz["anotado"].sum().unstack(fill_value=0).reindex(columns=Z.ZONAS, fill_value=0)
            out = out.join(fga.add_prefix("fga_"), how="outer").join(fgm.add_prefix("fgm_"), how="outer")
            out["fga_pbp"] = fga.sum(axis=1).reindex(out.index)
        out = out.reset_index()
    pj = DIR_PROC / temporada / "quintetos" / liga / "jugadores.csv"
    if pj.exists():
        j = pd.read_csv(pj, dtype={"team_id": str, "player_id": str})
        j = j[j["fase"] == "regular"][["team_id", "player_id", "min_on", "poss_on", "rapm", "orapm", "drapm"]]
        j = j[j["poss_on"].notna()]
        out = j if out is None else out.merge(j, on=["team_id", "player_id"], how="outer")
    if out is None:
        return pd.DataFrame(columns=["liga", "temporada", "team_id", "player_id"] + PISTA_COLS)
    for c in PISTA_COLS:
        if c not in out:
            out[c] = np.nan
    out.insert(0, "temporada", temporada)
    out.insert(0, "liga", liga)
    return out[["liga", "temporada", "team_id", "player_id"] + PISTA_COLS]


def construir(temporadas: list[str] | None = None, guardar: bool = True) -> pd.DataFrame:
    temporadas = temporadas or sorted(p.name for p in DIR_PROC.iterdir() if (p / "quintetos").exists())
    calib, frames = {}, []
    for temp in temporadas:
        for d in sorted((DIR_PROC / temp / "quintetos").iterdir()):
            frames.append(filas_liga(d.name, temp, calib))
    df = pd.concat(frames, ignore_index=True)
    if guardar:
        DIR_SALIDA.mkdir(parents=True, exist_ok=True)
        for temp, g in df.groupby("temporada"):
            g.round(4).to_csv(DIR_SALIDA / f"{temp}.csv", index=False)
        (DIR_SALIDA / "calibracion.json").write_text(json.dumps(calib, indent=1, ensure_ascii=False), encoding="utf-8")
    return df


def cargar(temporadas: list[str] | None = None) -> pd.DataFrame:
    """Rasgos de pista guardados (construir() si aún no existen)."""
    if not DIR_SALIDA.exists() or not any(DIR_SALIDA.glob("*.csv")):
        return construir(temporadas)
    fr = [pd.read_csv(p, dtype={"team_id": str, "player_id": str}) for p in sorted(DIR_SALIDA.glob("*.csv"))]
    df = pd.concat(fr, ignore_index=True)
    return df if temporadas is None else df[df["temporada"].isin(temporadas)]


def unir_a_filas(filas: pd.DataFrame, pista: pd.DataFrame) -> pd.DataFrame:
    """Añade los rasgos de pista a las filas jugador-equipo de bbstats (antes de agregar por liga).

    Unión por (liga, temporada, team_id, player_id). La EuroLeague y la EuroCup dan a los traspasados
    una sola fila «BAS;TEL»: allí se suman las filas de pista de todos sus equipos. El RAPM es de la liga
    (igual en todos sus equipos): se promedia ponderado por las posesiones de cada equipo."""
    f = filas.copy()
    f["_tid"] = f["team_id"].astype(str)
    p = pista.copy()
    p["_r_o"] = p["rapm"] * p["poss_on"]; p["_o_o"] = p["orapm"] * p["poss_on"]; p["_d_o"] = p["drapm"] * p["poss_on"]
    suma = CONTEOS + ["poss_on", "min_on", "_r_o", "_o_o", "_d_o"]
    directo = f.merge(p[["liga", "temporada", "team_id", "player_id"] + suma].rename(columns={"team_id": "_tid"}),
                      on=["liga", "temporada", "_tid", "player_id"], how="left")
    trasp = f["_tid"].str.contains(";", na=False)
    if trasp.any():
        por_jug = p.groupby(["liga", "temporada", "player_id"])[suma].sum(min_count=1).reset_index()
        t = f.loc[trasp, ["liga", "temporada", "player_id"]].merge(por_jug, on=["liga", "temporada", "player_id"], how="left")
        for c in suma:
            directo.loc[trasp.to_numpy(), c] = t[c].to_numpy()
    for c, s in (("rapm", "_r_o"), ("orapm", "_o_o"), ("drapm", "_d_o")):
        directo[c] = directo[s] / directo["poss_on"].where(directo["poss_on"] > 0)
    return directo.drop(columns=["_tid", "_r_o", "_o_o", "_d_o"])


def porcentajes(t: pd.DataFrame) -> pd.DataFrame:
    """Porcentajes de pista a partir de los conteos (tras sumar los equipos de cada jugador)."""
    t = t.copy()
    fga = t["fga_pbp"].where(t["fga_pbp"] > 0)
    for z in ("aro", "corta", "media", "t3_esquina"):
        t[f"pct_{z}"] = 100 * t[f"fga_{z}"] / fga
    t["pct_asistidas"] = 100 * t["fgm_asist"] / t["fgm_pbp"].where(t["fgm_pbp"] > 0)
    return t
