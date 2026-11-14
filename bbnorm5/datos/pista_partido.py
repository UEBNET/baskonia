"""F9 bis · Zonas de tiro y canastas asistidas por jugador y **partido** (jugada a jugada), para medir en la v5 las
cinco métricas de pista de la v3.2: % de tiros en el aro, cortos, de media distancia, triples de esquina y % de canastas
asistidas.

Misma fuente y clasificación que `bbmodel/pista.py` (la de la v3.2), pero sin agregar por temporada:
- `data/processed/<t>/quintetos/<liga>/tiros.csv.gz`, temporada regular, tiros de campo (T2, T3);
- zonas con la calibración de coordenadas de `bbmodel.zonas` por liga y temporada; si separa 2 y 3 en menos del 95 %
  de los tiros, esa liga-temporada queda sin zonas (como en la v3.2), pero conserva las asistidas;
- control de calidad: zonas sólo si hay ≥ 2.000 tiros con zona en la liga-temporada y ≥ 5 % en el aro;
- `fga_pbp` = tiros de campo con zona; `fgm_pbp` = canastas; `fgm_asist` = canastas con asistente.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from bbnorm5 import config as C

ZONAS_V5 = ["aro", "corta", "media", "t3_esquina"]
MIN_TIROS_ZONA = 2000          # tiros de campo con zona en la liga-temporada
MIN_CUOTA_ARO = 0.05           # en baloncesto, entre el 25 % y el 45 % de los tiros son en el aro
COLS = ["fga_pbp", "fgm_pbp", "fgm_asist"] + [f"fga_{z}" for z in ZONAS_V5]


def liga_temporada(liga: str, temporada: str) -> tuple[pd.DataFrame, dict]:
    from bbmodel import pista as BP
    from bbmodel import zonas as Z
    p = BP.DIR_PROC / temporada / "quintetos" / liga / "tiros.csv.gz"
    if not p.exists():
        return pd.DataFrame(columns=["liga", "temporada", "game_id", "player_id"] + COLS), {}
    t = pd.read_csv(p, dtype={"team_id": str, "player_id": str, "asistente_id": str, "game_id": str},
                    usecols=["fase", "game_id", "team_id", "player_id", "tipo", "anotado", "asistente_id", "x", "y"])
    t = t[t["fase"] == "regular"]
    campo = t[t["tipo"].isin(["T2", "T3"])].copy()
    campo["anotado"] = campo["anotado"].astype(str).str.lower().isin(["true", "1"])
    campo["asist"] = campo["anotado"] & campo["asistente_id"].notna() & (campo["asistente_id"] != "")
    g = campo.groupby(["game_id", "player_id"])
    out = pd.DataFrame({"fgm_pbp": g["anotado"].sum(), "fgm_asist": g["asist"].sum()})
    info = {"tiros": int(len(campo))}
    if len(campo):
        sis, acierto = Z.calibrar(liga, t)
        info["acierto_zonas"] = round(float(acierto), 4)
        if acierto >= BP.ACIERTO_MINIMO:
            s = Z.perfil_tiro(t, sis)
            gz = s.groupby(["game_id", "player_id", "zona"]).size().unstack(fill_value=0)
            gz = gz.reindex(columns=Z.ZONAS, fill_value=0)
            tot = float(gz.to_numpy().sum())
            aro = float(gz["aro"].sum()) / tot if tot else 0.0
            info["tiros_con_zona"], info["cuota_aro"] = int(tot), round(aro, 4)
            # control de calidad (F9 bis): sin coordenadas útiles la calibración puede pasar y las zonas salir vacías
            # (FEB1 2023-24: 116 tiros con zona y 0 % en el aro, igual en la v3.2)
            if tot >= MIN_TIROS_ZONA and aro >= MIN_CUOTA_ARO:
                out = out.join(gz[ZONAS_V5].add_prefix("fga_"), how="outer")
                out["fga_pbp"] = gz.sum(axis=1).reindex(out.index)
            else:
                info["zonas_descartadas"] = True
    out = out.reset_index()
    for c in COLS:
        if c not in out:
            out[c] = np.nan
    out.insert(0, "temporada", temporada)
    out.insert(0, "liga", liga)
    return out[["liga", "temporada", "game_id", "player_id"] + COLS], info


def construir(temporadas: list[str]) -> pd.DataFrame:
    from bbmodel import pista as BP
    frames, info = [], {}
    for t in temporadas:
        d = BP.DIR_PROC / t / "quintetos"
        if not d.exists():
            continue
        for lg in sorted(x.name for x in d.iterdir() if x.is_dir()):
            f, i = liga_temporada(lg, t)
            frames.append(f)
            info[f"{lg}|{t}"] = i
    df = pd.concat(frames, ignore_index=True)
    sal = C.DIR_DATOS / "medida"
    df.to_parquet(sal / "pista_partidos.parquet")
    C.escribir_json(info, sal / "pista_partidos_info.json")
    return df
