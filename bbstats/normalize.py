"""Normalización: mapea los nombres de campo de cada fuente a las columnas canónicas.

Cada fuente nombra igual cosas distintas (camelCase en Euroliga, MAYUS_SNAKE en NBA,
'sXxx' en FIBA LiveStats, abreviaturas en castellano en ACB...). Aquí se centraliza
la tabla de alias para que cualquier adaptador nuevo la reutilice.
"""
from __future__ import annotations

from typing import Any

from .utils import norm_key, parse_minutes, to_float

# canónico -> alias conocidos (se comparan con norm_key)
FIELD_ALIASES: dict[str, list[str]] = {
    "gp": ["gp", "gamesplayed", "games", "g", "partidos", "pj", "spiele"],
    "gs": ["gs", "gamesstarted", "starts", "titular", "starter"],
    "min": ["min", "minutes", "minutesplayed", "mp", "sminutes", "minutos", "timeplayed"],
    "pts": ["pts", "points", "pointsscored", "spoints", "puntos", "p"],
    "fgm": ["fgm", "fieldgoalsmade", "sfieldgoalsmade", "fg"],
    "fga": ["fga", "fieldgoalsattempted", "sfieldgoalsattempted"],
    "fg2m": ["fg2m", "twopointersmade", "stwopointersmade", "2pm", "t2m"],
    "fg2a": ["fg2a", "twopointersattempted", "stwopointersattempted", "2pa", "t2a"],
    "fg3m": ["fg3m", "threepointersmade", "sthreepointersmade", "3pm", "t3m"],
    "fg3a": ["fg3a", "threepointersattempted", "sthreepointersattempted", "3pa", "t3a"],
    "ftm": ["ftm", "freethrowsmade", "sfreethrowsmade", "t1m"],
    "fta": ["fta", "freethrowsattempted", "sfreethrowsattempted", "t1a"],
    "oreb": ["oreb", "offensiverebounds", "sreboundsoffensive", "orb", "reboundsoffensive"],
    "dreb": ["dreb", "defensiverebounds", "sreboundsdefensive", "drb", "reboundsdefensive"],
    "reb": ["reb", "totalrebounds", "sreboundstotal", "trb", "rebounds", "reboundstotal"],
    "ast": ["ast", "assists", "sassists"],
    "stl": ["stl", "steals", "ssteals"],
    "tov": ["tov", "turnovers", "sturnovers", "to"],
    "blk": ["blk", "blocks", "sblocks", "blocksfavour", "blocksinfavour"],
    "blka": ["blka", "blocksagainst", "sblocksreceived", "blocksreceived"],
    "pf": ["pf", "foulscommited", "foulscommitted", "sfoulspersonal", "personalfouls", "fouls"],
    "pfd": ["pfd", "foulsdrawn", "sfoulson", "foulsreceived", "foulsreceived"],
    "plus_minus": ["plusminus", "splusminuspoints", "+/-", "valorationplusminus"],
    "pir": ["pir", "valuation", "valoracion", "val", "performanceindexrating", "eff_7", "seff7"],
    "dunks": ["dunks", "mates", "sdunks"],
    "fastbreaks": ["fastbreaks", "contraataques"],
    "pts_fastbreak": ["ptsfb", "fastbreakpoints", "spointsfastbreak", "pointsfastbreak"],
    "pts_paint": ["ptspaint", "pointsinpaint", "spointsinthepaint", "pointsinthepaint"],
    "pts_2ndchance": ["pts2ndchance", "secondchancepoints", "spointssecondchance", "pointssecondchance"],
    "pts_off_tov": ["ptsofftov", "pointsoffturnovers", "spointsfromturnovers", "pointsfromturnovers"],
    "dd2": ["dd2", "doubledoubles"],
    "td3": ["td3", "tripledoubles"],
    "w": ["w", "wins", "won", "victorias"],
    "l": ["l", "losses", "lost", "derrotas"],
}

SOURCE_ALIASES: dict[str, list[str]] = {
    "src_ortg": ["offrating", "offensiverating", "ortg"],
    "src_drtg": ["defrating", "defensiverating", "drtg"],
    "src_netrtg": ["netrating", "netrtg"],
    "src_pace": ["pace"],
    "src_poss": ["poss", "possessions", "possesions"],
    "src_pie": ["pie"],
    "src_usg_pct": ["usgpct", "usage", "usagepercentage", "usagerate"],
    "src_ts_pct": ["tspct", "trueshootingpercentage", "trueshooting"],
    "src_efg_pct": ["efgpct", "effectivefieldgoalpercentage", "effectivefieldgoal"],
    "src_ast_pct": ["astpct", "assistspercentage", "assistpercentage"],
    "src_ast_ratio": ["astratio", "assistsratio", "assistratio"],
    "src_tov_ratio": ["tmtovpct", "turnoversratio", "turnoverratio", "turnoverspercentage"],
    "src_oreb_pct": ["orebpct", "offensivereboundspercentage", "offensivereboundpercentage"],
    "src_dreb_pct": ["drebpct", "defensivereboundspercentage", "defensivereboundpercentage"],
    "src_reb_pct": ["rebpct", "reboundspercentage", "reboundpercentage", "totalreboundspercentage"],
    "src_fta_rate": ["freethrowsrate", "freethrowrate", "ftrate"],
    "src_fg3a_rate": ["threepointattemptsratio", "threepointersattemptsratio", "fg3arate"],
    "src_def_ws": ["defws"],
    "src_pct_fga_2pt": ["pctfga2pt", "twopointattemptsratio", "twopointersattemptsratio"],
    "src_pct_fga_3pt": ["pctfga3pt"],
    "src_pct_pts_mid": ["pctpts2ptmr"],
    "src_pct_ast_fgm": ["pctastfgm"],
    "src_pct_uast_fgm": ["pctuastfgm"],
    "src_pct_ast_3pm": ["pctast3pm"],
    "src_pct_uast_2pm": ["pctuast2pm"],
    "src_fantasy_pts": ["nbafantasypts", "fantasypts", "fantasypoints"],
    "src_contested_shots": ["contestedshots"],
    "src_contested_shots_3pt": ["contestedshots3pt"],
    "src_deflections": ["deflections"],
    "src_charges_drawn": ["chargesdrawn"],
    "src_screen_assists": ["screenassists"],
    "src_screen_ast_pts": ["screenastpts"],
    "src_loose_balls": ["looseballsrecovered"],
    "src_box_outs": ["boxouts"],
    "src_dist_miles": ["distmiles"],
    "src_avg_speed": ["avgspeed"],
    "src_touches": ["touches"],
    "src_time_of_poss": ["timeofposs"],
    "src_drives": ["drives"],
    "src_drive_pts": ["drivepts"],
    "src_passes_made": ["passesmade"],
    "src_potential_ast": ["potentialast"],
    "src_secondary_ast": ["secondaryast"],
    "src_ft_ast": ["ftast"],
    "src_ast_pts_created": ["astptscreated"],
    "src_catch_shoot_fgm": ["catchshootfgm"],
    "src_catch_shoot_fga": ["catchshootfga"],
    "src_catch_shoot_pts": ["catchshootpts"],
    "src_pull_up_fgm": ["pullupfgm"],
    "src_pull_up_fga": ["pullupfga"],
    "src_pull_up_pts": ["pulluppts"],
    "src_paint_touches": ["painttouches"],
    "src_post_touches": ["posttouches"],
    "src_elbow_touches": ["elbowtouches"],
}


def _build_index(aliases: dict[str, list[str]]) -> dict[str, str]:
    idx: dict[str, str] = {}
    for canon, als in aliases.items():
        for a in [canon, *als]:
            idx.setdefault(norm_key(a), canon)
    return idx


_FIELD_IDX = _build_index(FIELD_ALIASES)
_SOURCE_IDX = _build_index(SOURCE_ALIASES)


def canonical_field(key: str) -> str | None:
    """Clave de origen -> columna canónica de conteo (o None)."""
    return _FIELD_IDX.get(norm_key(key))


def canonical_source_metric(key: str) -> str | None:
    return _SOURCE_IDX.get(norm_key(key))


def map_counting(record: dict, prefix: str = "", only: set[str] | None = None) -> dict:
    """Extrae del registro de origen las estadísticas de conteo canónicas.

    `prefix` se antepone a la columna destino (p.ej. 'team_' u 'opp_').
    Si hay dos alias para la misma columna gana el primero encontrado no vacío.
    """
    out: dict[str, Any] = {}
    for k, v in record.items():
        c = canonical_field(k.split(".")[-1])
        if c is None or (only is not None and c not in only):
            continue
        val = parse_minutes(v) if c == "min" else to_float(v)
        dest = prefix + c
        if val is not None and out.get(dest) is None:
            out[dest] = val
    return out


def map_source_metrics(record: dict) -> dict:
    out: dict[str, Any] = {}
    for k, v in record.items():
        c = canonical_source_metric(k.split(".")[-1])
        if c is None:
            continue
        val = to_float(v)
        if val is not None and out.get(c) is None:
            out[c] = val
    return out


def _g(d: dict, k: str) -> float | None:
    v = d.get(k)
    return None if v is None else float(v)


def complete_counting(d: dict, prefix: str = "") -> dict:
    """Rellena totales derivables (FGM=2PM+3PM, REB=OREB+DREB, ...). Modifica y devuelve d.

    Nunca sobrescribe un valor publicado por la fuente.
    """
    p = prefix

    def get(k):
        return _g(d, p + k)

    def setd(k, v):
        if d.get(p + k) is None and v is not None:
            d[p + k] = v

    for made, att in (("m", "a"),):
        fg2m, fg3m, fgm = get("fg2" + made), get("fg3" + made), get("fg" + made)
        fg2a, fg3a, fga = get("fg2" + att), get("fg3" + att), get("fg" + att)
        if fgm is None and fg2m is not None and fg3m is not None:
            setd("fgm", fg2m + fg3m)
        if fga is None and fg2a is not None and fg3a is not None:
            setd("fga", fg2a + fg3a)
        fgm, fga = get("fgm"), get("fga")
        if fg2m is None and fgm is not None and fg3m is not None:
            setd("fg2m", fgm - fg3m)
        if fg2a is None and fga is not None and fg3a is not None:
            setd("fg2a", fga - fg3a)
    oreb, dreb, reb = get("oreb"), get("dreb"), get("reb")
    if reb is None and oreb is not None and dreb is not None:
        setd("reb", oreb + dreb)
    elif dreb is None and reb is not None and oreb is not None:
        setd("dreb", reb - oreb)
    elif oreb is None and reb is not None and dreb is not None:
        setd("oreb", reb - dreb)
    if get("pts") is None and get("fg2m") is not None and get("fg3m") is not None and get("ftm") is not None:
        setd("pts", 2 * get("fg2m") + 3 * get("fg3m") + get("ftm"))
    return d


def is_per_game_scale(rows: list[dict]) -> bool:
    """Detecta si una fuente devolvió promedios en lugar de totales (minutos <= duración de partido)."""
    sample = [r for r in rows if (r.get("gp") or 0) >= 5 and r.get("min") is not None]
    if len(sample) < 5:
        return False
    return max(r["min"] for r in sample) <= 48.5


def per_game_to_totals(rows: list[dict], counting: list[str]) -> None:
    for r in rows:
        gp = r.get("gp")
        if not gp:
            continue
        for c in counting:
            if c in {"gp", "gs", "dd2", "td3", "w", "l"}:
                continue
            if r.get(c) is not None:
                r[c] = r[c] * gp
