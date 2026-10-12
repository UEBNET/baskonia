"""Enriquecimiento con BasketNews (basketnews.com/advanced-stats).

BasketNews calcula, a partir de los datos oficiales jugada a jugada, métricas que las ligas no
publican: ratings individuales (Dean Oliver), stops, puntos creados/asistidos y un on/off
completo de cada jugador (rendimiento del equipo con él en pista y sin él).

Cobertura (comprobada): EuroLeague (league_id=25) y Liga Endesa (league_id=41).
Endpoints (POST, los mismos que usa su web):
    https://basketnews.com/advanced-stats/team-profile/players.json
    https://basketnews.com/advanced-stats/team-profile/on-off.json
    parámetros: ajax=true, league_id, season (año de inicio), stage_id (opcional)

Sus valores de conteo vienen en promedio por partido y redondeados, así que SÓLO se usan como
columnas adicionales `bn_*` (ratios, ratings, on/off), nunca para sustituir los totales oficiales.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from ..http import FetchError, HttpClient

BASE = "https://basketnews.com/advanced-stats/team-profile"

# columna -> (fichero, clave en BasketNews, descripción)
_PLAYER_FIELDS = [
    ("bn_usg_pct", "players", "usage_percentage", "USG% (BasketNews)"),
    ("bn_ts_pct", "players", "ts_percentage", "TS% (BasketNews)"),
    ("bn_ast_pct", "players", "assist_percentage", "AST% (BasketNews)"),
    ("bn_tov_pct", "players", "turnover_percentage", "TOV% (BasketNews)"),
    ("bn_stl_pct", "players", "steal_percentage", "STL% (BasketNews)"),
    ("bn_blk_pct", "players", "block_percentage", "BLK% (BasketNews)"),
    ("bn_oreb_pct", "players", "offensive_rebound_percentage", "OREB% (BasketNews)"),
    ("bn_dreb_pct", "players", "defensive_rebound_percentage", "DREB% (BasketNews)"),
    ("bn_fg3a_rate", "players", "3p_attempted_rate", "3PAr (BasketNews)"),
    ("bn_ast_to", "players", "assist_turnover_ratio", "AST/TO (BasketNews)"),
    ("bn_poss_pg", "players", "possessions", "Posesiones individuales por partido"),
    ("bn_ortg_ind", "players", "offensive_rating_ind", "Rating ofensivo individual (BasketNews)"),
    ("bn_drtg_ind", "players", "defensive_rating_ind", "Rating defensivo individual (BasketNews)"),
    ("bn_netrtg_ind", "players", "net_rating_ind", "Net rating individual (BasketNews)"),
    ("bn_stops_pg", "players", "stops", "Stops defensivos por partido"),
    ("bn_foul_stops_pg", "players", "foul_stops", "Stops por falta por partido"),
    ("bn_stop_pct", "players", "stop_percentage", "Stop% (BasketNews)"),
    ("bn_created_pts_pg", "players", "created_points", "Puntos creados por partido (propios + asistidos)"),
    ("bn_assisted_pts_pg", "players", "assisted_points", "Puntos generados con asistencias por partido"),
    ("bn_3fta_poss_pg", "players", "3fta_possessions", "Posesiones con tiro libre de 3 por partido"),
    ("bn_pir_pg", "players", "pir", "PIR por partido (BasketNews)"),
]
_ONOFF_FIELDS = [
    ("bn_min_on", "onoff", "time_played_lineup", "Minutos con el jugador en pista"),
    ("bn_poss_on", "onoff", "possessions_lineup", "Posesiones del equipo con él en pista"),
    ("bn_poss_on_pct", "onoff", "possession_percentage_lineup", "% de las posesiones del equipo con él en pista"),
    ("bn_pts_on", "onoff", "points_lineup", "Puntos del equipo con él en pista"),
    ("bn_opp_pts_on", "onoff", "points_opponent_lineup", "Puntos del rival con él en pista"),
    ("bn_net_pts_on", "onoff", "net_points_lineup", "Diferencial de puntos con él en pista"),
    ("bn_ortg_on", "onoff", "offensive_rating_lineup", "ORtg del equipo con él en pista"),
    ("bn_drtg_on", "onoff", "defensive_rating_lineup", "DRtg del equipo con él en pista"),
    ("bn_netrtg_on", "onoff", "net_rating_lineup", "Net rating del equipo con él en pista"),
    ("bn_ortg_off", "onoff", "offensive_rating_lineup_wo", "ORtg del equipo con él en el banquillo"),
    ("bn_drtg_off", "onoff", "defensive_rating_lineup_wo", "DRtg del equipo con él en el banquillo"),
    ("bn_netrtg_off", "onoff", "net_rating_lineup_wo", "Net rating del equipo con él en el banquillo"),
    ("bn_ortg_onoff", "onoff", "offensive_rating_lineup_diff", "ORtg on - off"),
    ("bn_drtg_onoff", "onoff", "defensive_rating_lineup_diff", "DRtg on - off"),
    ("bn_netrtg_onoff", "onoff", "net_rating_lineup_diff", "Net rating on - off (impacto)"),
]
_ONOFF_FACTORS = [
    ("2p_pct", "2p_percentage", "2P% del equipo"),
    ("3p_pct", "3p_percentage", "3P% del equipo"),
    ("fg3a_rate", "3p_attempted_rate", "3PAr del equipo"),
    ("ast_pct", "assist_percentage", "AST% del equipo"),
    ("tov_pct", "turnover_percentage", "TOV% del equipo"),
    ("oreb_pct", "offensive_rebound_percentage", "OREB% del equipo"),
    ("dreb_pct", "defensive_rebound_percentage", "DREB% del equipo"),
    ("reb_pct", "rebound_percentage", "REB% del equipo"),
    ("foul_rate", "fouls_rate", "Faltas cometidas (tasa) del equipo"),
    ("fouled_rate", "fouls_received_rate", "Faltas recibidas (tasa) del equipo"),
    ("opp_2p_pct", "2p_percentage_opponent", "2P% del rival"),
    ("opp_3p_pct", "3p_percentage_opponent", "3P% del rival"),
    ("opp_fg3a_rate", "3p_attempted_rate_opponent", "3PAr del rival"),
    ("opp_ast_pct", "assist_percentage_opponent", "AST% del rival"),
    ("opp_tov_pct", "turnover_percentage_opponent", "TOV% del rival"),
]
for short, key, desc in _ONOFF_FACTORS:
    _ONOFF_FIELDS.append((f"bn_{short}_on", "onoff", f"{key}_lineup", f"{desc} con él en pista"))
    _ONOFF_FIELDS.append((f"bn_{short}_onoff", "onoff", f"{key}_lineup_diff", f"{desc}: diferencia on - off"))

FIELDS = _PLAYER_FIELDS + _ONOFF_FIELDS
BN_COLUMNS: list[tuple[str, str]] = [("bn_player_id", "Id del jugador en BasketNews (trazabilidad del cruce)")] + \
    [(c, d) for c, _, _, d in FIELDS]


# --------------------------------------------------------------------------------------------- nombres
_SUFFIX = {"jr", "sr", "ii", "iii", "iv"}


def name_tokens(name: str) -> frozenset[str]:
    """'LLULL, SERGIO' / 'Sergio Llull' / 'S. Llull' -> {'llull','sergio'} (sin acentos ni sufijos)."""
    n = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[.'’`]", "", n)  # P.J. -> pj, O'Shae -> oshae
    toks = [t for t in re.split(r"[^a-z]+", n) if t and t not in _SUFFIX]
    return frozenset(toks)


def split_name(name: str) -> tuple[frozenset[str], str]:
    """(tokens del apellido, inicial del nombre). 'LLULL, SERGIO' y 'Sergio Llull' -> ({'llull'}, 's')."""
    raw = str(name or "")
    if "," in raw:
        last, first = raw.split(",", 1)
    else:
        parts = raw.strip().split()
        first, last = (" ".join(parts[:-1]), parts[-1]) if len(parts) > 1 else ("", raw)
    ft = sorted(name_tokens(first))
    return name_tokens(last), (min(ft, key=lambda t: raw.lower().find(t))[0] if ft else "")


def _match_score(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b) + (0.5 if max(a, key=len) in b or max(b, key=len) in a else 0)


def _team_tokens(name: str) -> frozenset[str]:
    return frozenset(t for t in name_tokens(name) if len(t) > 3)


# --------------------------------------------------------------------------------------------- fetch
def fetch(http: HttpClient, league_id: int, season_start: int, errors: list[str]) -> dict:
    """Descarga players.json y on-off.json para la temporada completa y para cada fase (stage)."""
    headers = {"X-Requested-With": "XMLHttpRequest",
               "Referer": f"https://basketnews.com/advanced-stats/{league_id}/{season_start}"}
    out: dict[str, Any] = {"league_id": league_id, "season": season_start, "stages": [], "players": {},
                           "onoff": {}}
    base = {"ajax": "true", "league_id": league_id, "season": season_start}
    try:
        first = http.post_json(f"{BASE}/players.json", data=base, headers=headers)
    except FetchError as exc:
        errors.append(f"BasketNews: {exc}")
        return out
    out["players"]["total"] = first
    out["stages"] = ((first or {}).get("data") or {}).get("stages") or []
    try:
        out["onoff"]["total"] = http.post_json(f"{BASE}/on-off.json", data=base, headers=headers)
    except FetchError as exc:
        errors.append(f"BasketNews on/off: {exc}")
    for st in out["stages"]:
        sid = st.get("stage_id")
        for kind, ep in (("players", "players.json"), ("onoff", "on-off.json")):
            try:
                out[kind][str(sid)] = http.post_json(f"{BASE}/{ep}", data={**base, "stage_id": sid}, headers=headers)
            except FetchError as exc:
                errors.append(f"BasketNews {ep} stage {sid}: {exc}")
    return out


def stage_phase(stage: dict) -> str:
    name = ((stage.get("translations") or {}).get("en") or {}).get("name", "").lower()
    return "regular" if "regular" in name else "playoffs"


# --------------------------------------------------------------------------------------------- parse
def _rows(doc: Any) -> tuple[dict[tuple, dict], dict, dict]:
    data = (doc or {}).get("data") or {}
    players = {p["id"]: p for p in data.get("players") or []}
    teams = {t["id"]: t for t in data.get("teams") or []}
    stats = {(s["player_id"], s["team_id"]): s for s in data.get("stats") or []}
    return stats, players, teams


def _val(v: Any) -> Any:
    if isinstance(v, dict):
        v = v.get("value")
    return v


def phase_records(payload: dict, phase: str) -> list[dict]:
    """Registros bn_* por jugador-equipo para una fase ('total', 'regular' o 'playoffs')."""
    if not payload:
        return []
    if phase == "total":
        keys = ["total"]
    else:
        stages = [s for s in payload.get("stages") or [] if stage_phase(s) == phase]
        if phase == "playoffs":  # BasketNews no combina fases: se usa la de más partidos (Playoffs)
            stages = sorted(stages, key=lambda s: -(s.get("total_games") or 0))[:1]
        keys = [str(s["stage_id"]) for s in stages]
    out: dict[tuple, dict] = {}
    for key in keys:
        p_stats, players, teams = _rows(payload.get("players", {}).get(key))
        o_stats, players2, teams2 = _rows(payload.get("onoff", {}).get(key))
        players.update(players2)
        teams.update(teams2)
        for k in set(p_stats) | set(o_stats):
            pid, tid = k
            rec = out.setdefault(k, {"bn_player_id": str(pid),
                                     "_name": (players.get(pid) or {}).get("full_name"),
                                     "_team": (teams.get(tid) or {}).get("name")})
            for col, file, key_, _ in FIELDS:
                src = p_stats.get(k) if file == "players" else o_stats.get(k)
                if src is None or key_ not in src:
                    continue
                v = _val(src[key_])
                if col == "bn_min_on" and v is not None:
                    v = v / 60.0
                rec[col] = v
    return list(out.values())


def apply(df, payload: dict, phase: str, notes: list[str]):
    """Añade columnas bn_* a un DataFrame de jugadores emparejando por nombre (+ equipo)."""
    recs = phase_records(payload, phase)
    if df is None or df.empty or not recs:
        return df
    by_tokens: dict[frozenset, list[dict]] = {}
    for r in recs:
        by_tokens.setdefault(name_tokens(r["_name"]), []).append(r)
    matched = 0
    cols = {c: [None] * len(df) for c, _ in BN_COLUMNS}
    for i, (name, team) in enumerate(zip(df["nombre"].tolist(), df["equipo"].tolist())):
        toks = name_tokens(name)
        cands = by_tokens.get(toks)
        if not cands:
            scored = [(_match_score(toks, k), k) for k in by_tokens]
            scored = [s for s in scored if s[0] >= 0.9]
            if scored:
                cands = by_tokens[max(scored, key=lambda s: s[0])[1]]
        if not cands:  # respaldo: mismo apellido, mismo equipo y misma inicial (Zac/Zachary, Will/William)
            sur, ini = split_name(name)
            tt = _team_tokens(team or "")
            cands = [r for r in recs if sur and sur <= name_tokens(r["_name"])
                     and (not tt or tt & _team_tokens(r["_team"] or ""))
                     and (not ini or split_name(r["_name"])[1] == ini)]
            if len(cands) != 1:
                continue
        if len(cands) > 1:
            tt = _team_tokens(team or "")
            cands = sorted(cands, key=lambda r: -len(tt & _team_tokens(r["_team"] or "")))
        r = cands[0]
        matched += 1
        for c, _ in BN_COLUMNS:
            cols[c][i] = r.get(c)
    for c, vals in cols.items():
        df[c] = vals
    notes.append(f"BasketNews ({phase}): {matched}/{len(df)} jugadores emparejados")
    return df
