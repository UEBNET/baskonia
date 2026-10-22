"""Informes de las competiciones FEB (feb1, feb2, feb3): partidos con su grupo, cobertura, contrato de datos,
posesiones reconstruidas y sesgo de registro. Sin red: sólo lee los brutos (data/raw/<liga>/<t>/).

    python -m bbstats feb [--ligas feb1 feb2 feb3] [--temporada T ...]
        data/processed/<t>/feb/<liga>_partidos.csv   un partido por fila, TODOS los del calendario (también los
                                                     excluidos y los que no tienen datos): grupo_id y grupo
                                                     originales, fase, jornada, fecha, con_box, formato_pbp,
                                                     pbp_available, con_cambios, quintetos_validos, posesiones
                                                     del jugada a jugada y de caja de cada equipo
        data/processed/<t>/feb/<liga>_equipos.csv    equipo (id de inscripción de la temporada), clubCode,
                                                     grupo(s) de liga regular, entrenador de su página
        data/processed/feb_cobertura.csv             competición × temporada × grupo: partidos, % con jugada a
                                                     jugada, % sólo boxscore, % sin datos, % quintetos válidos
        data/processed/feb_posesiones.csv            posesiones reconstruidas vs estimación de caja por
                                                     competición y temporada
        data/processed/feb_sesgo_registro.csv        AST/FGM y OREB% por liga y temporada (FEB y ligas FIBA)
    python -m bbstats contrato --ligas feb1 feb2 feb3
        imprime y guarda data/processed/feb_contrato.csv (bbstats/contrato.py: % de partidos que pasan cada
        comprobación, por liga y temporada)
"""
from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from .adapters.feb import game_rows, parse_game, parse_team_page
from .config import configured_seasons, load_config, resolve_path
from .contrato import check_box, check_pbp, resumen
from .lineups.possessions import box_possessions, count_possessions
from .lineups.sources.base import Ctx
from .lineups.sources.feb import FebPBP
from .lineups.stints import build
from .raw_store import RawStore

log = logging.getLogger(__name__)
FEB = ("feb1", "feb2", "feb3")
FIBA_REF = ("acb", "lba", "bbl", "lnb", "bcl", "fec", "bsl", "gbl", "euroleague", "eurocup")


def analizar_temporada(liga: str, temporada: str, cfg: dict, store: RawStore) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    """(partidos, equipos, filas de contrato) de una liga y temporada a partir del bruto."""
    _, doc = store.load_season(liga, temporada)
    if not doc:
        return pd.DataFrame(), pd.DataFrame(), []
    payload = doc["payload"]
    lcfg = cfg["ligas"][liga]
    max_dif = float((cfg.get("quintetos") or {}).get("excluir_si_dif_min_s", 120))
    rosters = {tid: parse_team_page(fr) for tid, fr in (payload.get("equipos") or {}).items()}
    games = payload.get("games") or {}
    meta = (payload.get("calendario") or {}).get("partidos") or {}
    src, ctx = FebPBP(), Ctx(league=liga, season=temporada, cfg=lcfg, main_payload=payload)
    refs = {r["game_id"]: r for r in src.games(ctx)}
    rows, contrato = [], []
    for r in game_rows(payload):
        gid = r["game_id"]
        rec = {"liga": liga, "temporada": temporada, **r, "pbp_available": False, "con_cambios": False,
               "quintetos_validos": False, "con_coordenadas": False}
        d = games.get(gid)
        ref = refs.get(gid)
        if d and not d.get("sin_datos") and ref:
            g = parse_game(gid, d, ref["phase"], rosters, meta.get(gid))
            game = src.parse({"data": d}, ref, ctx)
            evs = game.events
            rec["pbp_available"] = bool(evs)
            rec["con_cambios"] = bool(game.has_lineups and evs)
            rec["con_coordenadas"] = bool(game.has_shots)
            if game.has_lineups and evs:
                v = build(game, ctx.game_min).validation()
                rec["quintetos_validos"] = bool(v["dif_min_max_s"] is None or v["dif_min_max_s"] <= max_dif)
                rec["dif_min_max_s"] = v["dif_min_max_s"]
            n_pos, _ = count_possessions(evs, game.teams) if evs else (Counter(), {})
            for i, s in enumerate(g["teams"][:2], 1):
                tot = {k: sum((p.get(k) or 0) for p in s["players"]) for k in ("fga", "fta", "oreb", "tov", "fgm",
                                                                                "ast", "pts")}
                rec[f"equipo_{i}_id"] = s["team_id"]
                rec[f"equipo_{i}"] = s["name"]
                rec[f"pts_{i}"] = (s.get("totals") or {}).get("pts")
                rec[f"pos_box_{i}"] = round(box_possessions(tot["fga"], tot["fta"], tot["oreb"], tot["tov"]), 2)
                rec[f"pos_pbp_{i}"] = n_pos.get(s["team_id"]) if evs else None
                rec[f"fgm_{i}"], rec[f"ast_{i}"] = tot["fgm"], tot["ast"]
            c = {"liga": liga, "temporada": temporada, "fase": r["fase"], "formato_pbp": r["formato_pbp"],
                 **check_box(g, evs), **check_pbp(g, evs)}
            contrato.append(c)
        rows.append(rec)
    partidos = pd.DataFrame(rows)
    eq = []
    grupo_de: dict[str, set] = {}
    for gid, m in meta.items():
        for side in ("local", "visitante"):
            if m.get(side):
                grupo_de.setdefault(m[side], set()).add(m.get("grupo"))
    grupos = (payload.get("calendario") or {}).get("grupos") or {}
    nombres = {}
    for i in (1, 2):
        if f"equipo_{i}_id" in partidos:
            nombres.update(dict(zip(partidos[f"equipo_{i}_id"].dropna(), partidos[f"equipo_{i}"].dropna())))
    for tid, ro in rosters.items():
        gs = sorted(g for g in grupo_de.get(tid, set()) if (grupos.get(g) or {}).get("fase") == "regular")
        ent = ro.get("entrenador") or {}
        name = nombres.get(tid)
        eq.append({"liga": liga, "temporada": temporada, "team_id": tid, "equipo": name,
                   "grupo_id": ";".join(gs), "grupo": ";".join((grupos.get(g) or {}).get("nombre", "") for g in gs),
                   "entrenador": ent.get("nombre"), "entrenador_id_feb": ent.get("id"),
                   "jugadores_plantilla": len(ro.get("jugadores") or {})})
    return partidos, pd.DataFrame(eq), contrato


def cobertura(partidos: pd.DataFrame) -> pd.DataFrame:
    """Matriz competición × temporada × grupo (partidos jugados de cada grupo)."""
    if partidos.empty:
        return pd.DataFrame()
    p = partidos[partidos["jugado"].astype(bool)].copy()
    out = []
    for (liga, t, gid, gname, fase), g in p.groupby(["liga", "temporada", "grupo_id", "grupo", "fase"], dropna=False):
        n = len(g)
        incl = fase != "excluida"
        box = g["con_box"].astype(bool)
        pbp = g["pbp_available"].astype(bool)
        out.append({"liga": liga, "temporada": t, "grupo_id": gid, "grupo": gname, "fase": fase, "partidos": n,
                    "pct_pbp": round(100 * pbp.mean(), 1) if incl else None,
                    "pct_solo_box": round(100 * (box & ~pbp).mean(), 1) if incl else None,
                    "pct_sin_datos": round(100 * (~box).mean(), 1) if incl else None,
                    "pct_con_cambios": round(100 * g["con_cambios"].astype(bool).mean(), 1) if incl else None,
                    "pct_quintetos_validos": round(100 * g["quintetos_validos"].astype(bool).mean(), 1) if incl else None,
                    "pct_coordenadas": round(100 * g["con_coordenadas"].astype(bool).mean(), 1) if incl else None,
                    "formato_pbp": ";".join(sorted(x for x in g["formato_pbp"].dropna().unique() if x)),
                    "descargado": bool(incl)})
    return pd.DataFrame(out).sort_values(["liga", "temporada", "fase", "grupo"]).reset_index(drop=True)


def posesiones(partidos: pd.DataFrame) -> pd.DataFrame:
    """Posesiones del jugada a jugada frente a la estimación de caja FGA + 0,44·FTA − OREB + TOV."""
    if partidos.empty or "pos_pbp_1" not in partidos:
        return pd.DataFrame()
    rows = []
    for i in (1, 2):
        d = partidos[["liga", "temporada", "formato_pbp", f"pos_pbp_{i}", f"pos_box_{i}"]].dropna()
        d.columns = ["liga", "temporada", "formato_pbp", "pbp", "box"]
        rows.append(d)
    d = pd.concat(rows)
    d = d[d["pbp"] > 0]
    d["dif"] = d["pbp"] - d["box"]
    out = []
    for keys, g in list(d.groupby(["liga", "temporada", "formato_pbp"])) + \
            [((l, "todas", f), g) for (l, f), g in d.groupby(["liga", "formato_pbp"])]:
        out.append({"liga": keys[0], "temporada": keys[1], "formato_pbp": keys[2], "equipos_partido": len(g),
                    "pos_pbp_media": round(g["pbp"].mean(), 2), "pos_box_media": round(g["box"].mean(), 2),
                    "dif_media": round(g["dif"].mean(), 2), "dif_abs_media": round(g["dif"].abs().mean(), 2),
                    "dif_pct_media": round(100 * (g["dif"] / g["box"]).mean(), 2),
                    "correlacion": round(float(np.corrcoef(g["pbp"], g["box"])[0, 1]), 3) if len(g) > 2 else None})
    return pd.DataFrame(out)


def sesgo_registro(processed: Path, temporadas: list[str], ligas: tuple = FEB + FIBA_REF) -> pd.DataFrame:
    """AST/FGM (asistencias por canasta) y OREB% = OREB / (OREB + DREB rival), por liga y temporada, de los
    totales de equipo de ligas/<liga>.csv (fase total, una fila por equipo)."""
    out = []
    for t in temporadas:
        for liga in ligas:
            f = processed / t / "ligas" / f"{liga}.csv"
            if not f.exists():
                continue
            try:
                d = pd.read_csv(f, usecols=["fase", "team_id", "team_ast", "team_fgm", "team_oreb", "opp_dreb",
                                            "team_gp"], dtype={"team_id": str})
            except ValueError:
                continue
            d = d[d["fase"] == "total"].drop_duplicates("team_id")
            if d.empty:
                continue
            ast, fgm = d["team_ast"].sum(), d["team_fgm"].sum()
            oreb, odr = d["team_oreb"].sum(), d["opp_dreb"].sum()
            out.append({"liga": liga, "temporada": t, "equipos": len(d), "partidos_equipo": d["team_gp"].sum(),
                        "ast_por_fgm": round(ast / fgm, 4) if fgm else None,
                        "oreb_pct": round(100 * oreb / (oreb + odr), 2) if oreb and odr == odr and odr else None})
    return pd.DataFrame(out)


def ejecutar(ligas: list[str] | None = None, temporadas: list[str] | None = None, config: dict | str | None = None,
             progreso: Callable[[str], None] = print, escribir: bool = True) -> dict:
    cfg = config if isinstance(config, dict) else load_config(config)
    ligas = ligas or list(FEB)
    temporadas = temporadas or configured_seasons(cfg)
    store = RawStore(resolve_path(cfg, "bruto"), compress=cfg.get("comprimir_bruto", False))
    processed = resolve_path(cfg, "procesado")
    all_p, all_c = [], []
    for t in temporadas:
        for liga in ligas:
            p, e, c = analizar_temporada(liga, t, cfg, store)
            if p.empty:
                continue
            progreso(f"[{liga}] {t}: {len(p)} partidos en el calendario, {int(p['descargado'].sum())} descargados, "
                     f"{int(p['pbp_available'].sum())} con jugada a jugada")
            if escribir:
                d = processed / t / "feb"
                d.mkdir(parents=True, exist_ok=True)
                p.to_csv(d / f"{liga}_partidos.csv", index=False, encoding="utf-8")
                e.to_csv(d / f"{liga}_equipos.csv", index=False, encoding="utf-8")
            all_p.append(p)
            all_c.extend(c)
    partidos = pd.concat(all_p, ignore_index=True) if all_p else pd.DataFrame()
    cob, pos = cobertura(partidos), posesiones(partidos)
    ses = sesgo_registro(processed, temporadas)
    con = contrato_resumen(all_c)
    if escribir and not partidos.empty:
        _merge_write(cob, processed / "feb_cobertura.csv", ligas, temporadas)
        _merge_write(pos, processed / "feb_posesiones.csv", ligas, temporadas)
        _merge_write(ses, processed / "feb_sesgo_registro.csv", ligas=list(FEB + FIBA_REF), temporadas=temporadas)
        _merge_write(con, processed / "feb_contrato.csv", ligas, temporadas)
    return {"partidos": partidos, "cobertura": cob, "posesiones": pos, "sesgo": ses, "contrato": con}


def contrato_resumen(filas: list[dict]) -> pd.DataFrame:
    if not filas:
        return pd.DataFrame()
    df = pd.DataFrame(filas)
    out = []
    for (liga, t), g in df.groupby(["liga", "temporada"]):
        out.append({"liga": liga, "temporada": t, **resumen(g.to_dict("records"))})
    for liga, g in df.groupby("liga"):
        out.append({"liga": liga, "temporada": "todas", **resumen(g.to_dict("records"))})
    return pd.DataFrame(out)


def _merge_write(df: pd.DataFrame, path: Path, ligas: list[str], temporadas: list[str]) -> None:
    """Reescribe sólo las filas de `ligas` × `temporadas` (y su fila "todas", que resume las temporadas de esta
    ejecución); las demás ya calculadas se conservan."""
    if path.exists() and not df.empty:
        old = pd.read_csv(path, dtype=str)
        old = old[~(old["liga"].isin(ligas) & old["temporada"].isin(list(temporadas) + ["todas"]))]
        df = pd.concat([old, df.astype(object)], ignore_index=True)
    df.to_csv(path, index=False, encoding="utf-8")
