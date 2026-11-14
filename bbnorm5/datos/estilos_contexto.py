"""F2 (revisión 1.2) · Estilo de liga, estilo de equipo y contexto de compañeros por temporada.

Los nombres de estilo NO cambian: los seis estilos unificados de `configs/styles.yaml` (Spacing, Circulación,
Isolation, Old-School, Pistons, Pintura), tal como los asigna `data/modelos/estilos_unificados/` a jugadores y equipos.
La liga no recibe etiqueta: se describe con rasgos y con el reparto de sus equipos entre esos seis estilos.

Rasgos de caja, iguales en las 20 competiciones (desde la caja jugador-partido v5, totales de equipo por partido):
| Rasgo | Definición |
|---|---|
| ritmo | posesiones por 40 minutos de equipo |
| 3PAr | T3 intentados / TC intentados |
| FTr | TL intentados / TC intentados |
| OREB% | rebotes ofensivos / (ofensivos propios + defensivos del rival) |
| TOV% | pérdidas / posesiones |
| AST/TCm | asistencias / tiros de campo anotados |
| STL% | robos / posesiones del rival |
| BLK% | tapones / T2 intentados del rival |
| faltas/100 | faltas por 100 posesiones |
| eFG% | (TCm + 0,5·T3m) / TC intentados |

Salidas en data/v5/contexto/:
- `estilo_liga.csv`: liga × temporada, fase regular;
- `estilo_equipo.csv`: liga × temporada × equipo;
- `contexto_companeros.parquet`: persona × liga × temporada × equipo; composición de estilos de sus compañeros,
  ponderada por sus minutos, sin él.

SUPUESTO (declarado):
- La pertenencia a estilo de cada jugador y equipo se calcula con los datos de su temporada, pero los centroides de
  la taxonomía se ajustaron con todas las temporadas (`docs/estado_modelos.md`, ficha 13). Es una fuga leve de
  definición, no de resultado.
- La ponderación por minutos totales aproxima los minutos compartidos en pista. El cálculo exacto con los tramos del
  jugada a jugada queda para la F6 si el efecto de los compañeros resulta relevante.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from bbnorm5 import config as C

DIR = C.DIR_DATOS / "contexto"
ESTILOS = ["spacing", "circulacion", "isolation", "old_school", "pistons", "pintura"]


def _rasgos(g: pd.DataFrame) -> pd.Series:
    s = g.sum(numeric_only=True)
    poss = s["team_fga"] - s["team_oreb"] + s["team_tov"] + 0.44 * s["team_fta"]
    poss_r = s["opp_fga"] - s["opp_oreb"] + s["opp_tov"] + 0.44 * s["opp_fta"]
    return pd.Series({
        "partidos": len(g), "ritmo": 40 * poss / (s["team_min"] / 5),
        "3PAr": s["team_fg3a"] / s["team_fga"], "FTr": s["team_fta"] / s["team_fga"],
        "OREB%": s["team_oreb"] / (s["team_oreb"] + s["opp_dreb"]), "TOV%": s["team_tov"] / poss,
        "AST/TCm": s["team_ast"] / s["team_fgm"], "STL%": s["team_stl"] / poss_r,
        "BLK%": s["team_blk"] / s["opp_fg2a"], "faltas/100": 100 * s["team_pf"] / poss,
        "eFG%": (s["team_fgm"] + 0.5 * s["team_fg3m"]) / s["team_fga"]})


def partidos_equipo(temporadas: list[str]) -> pd.DataFrame:
    cols = ["min", "fga", "fgm", "fg2a", "fg3a", "fg3m", "fta", "oreb", "dreb", "ast", "stl", "tov", "blk", "pf", "pts"]
    fr = []
    for t in temporadas:
        for f in sorted((C.DIR_DATOS / "limpios" / "caja_partido" / t).glob("*.parquet")):
            d = pd.read_parquet(f)
            keep = ["liga", "temporada", "game_id", "fase", "team_id"] + [f"team_{c}" for c in cols] + [f"opp_{c}" for c in cols]
            d = d[[c for c in keep if c in d]].dropna(subset=["team_id"]).drop_duplicates(["game_id", "team_id"])
            fr.append(d)
    d = pd.concat(fr, ignore_index=True)
    d["team_id"] = d["team_id"].astype(str)
    return d[d["fase"] == "regular"]


def construir(temporadas: list[str]) -> dict:
    DIR.mkdir(parents=True, exist_ok=True)
    pe = partidos_equipo(temporadas)
    eq = pe.groupby(["liga", "temporada", "team_id"]).apply(_rasgos, include_groups=False).reset_index()
    lg = pe.groupby(["liga", "temporada"]).apply(_rasgos, include_groups=False).reset_index()
    # estilos unificados de equipo (nivel temporada) y reparto de la liga entre los seis
    ee = pd.read_csv(C.RAIZ / "data" / "modelos" / "estilos_unificados" / "equipos.csv", dtype={"team_id": str})
    ee = ee[ee["nivel"] == "temporada"][["liga", "temporada", "team_id", "estilo_nombre", "p_estilo"] + [f"p_{e}" for e in ESTILOS]]
    eq = eq.merge(ee, on=["liga", "temporada", "team_id"], how="left")
    rep = ee.groupby(["liga", "temporada"])[[f"p_{e}" for e in ESTILOS]].mean().add_prefix("reparto_")
    lg = lg.merge(rep, on=["liga", "temporada"], how="left")
    eq.to_csv(DIR / "estilo_equipo.csv", index=False)
    lg.to_csv(DIR / "estilo_liga.csv", index=False)
    # contexto de compañeros
    pj = pd.read_csv(C.RAIZ / "data" / "modelos" / "estilos_unificados" / "jugadores.csv.gz", low_memory=False,
                     dtype={"team_id": str, "player_id": str})
    pj = pj[pj["nivel"] == "temporada"][["liga", "temporada", "team_id", "player_id", "min"] + [f"p_{e}" for e in ESTILOS]]
    pj["min"] = pd.to_numeric(pj["min"], errors="coerce").fillna(0)
    for e in ESTILOS:
        pj[f"w_{e}"] = pj["min"] * pj[f"p_{e}"].fillna(0)
    tot = pj.groupby(["liga", "temporada", "team_id"])[["min"] + [f"w_{e}" for e in ESTILOS]].sum().add_suffix("_eq")
    x = pj.merge(tot, left_on=["liga", "temporada", "team_id"], right_index=True)
    otros = (x["min_eq"] - x["min"]).replace(0, np.nan)
    ctx = x[["liga", "temporada", "team_id", "player_id"]].copy()
    for e in ESTILOS:
        ctx[f"comp_{e}"] = (x[f"w_{e}_eq"] - x[f"w_{e}"]) / otros
    personas = pd.read_csv(C.DIR_DATOS / "limpios" / "entidades" / "personas_v5.csv", dtype=str)
    pm = personas.set_index(["fuente_liga", "fuente_id"])["persona_v5"]
    ctx["persona_v5"] = [pm.get((l, i)) for l, i in zip(ctx["liga"], ctx["player_id"])]
    ctx.to_parquet(DIR / "contexto_companeros.parquet", index=False, compression="zstd")
    return {"ligas_temporada": int(len(lg)), "equipos_temporada": int(len(eq)),
            "equipos_con_estilo": float(eq["estilo_nombre"].notna().mean()), "contexto_filas": int(len(ctx)),
            "contexto_con_persona": float(ctx["persona_v5"].notna().mean())}
