"""Agregación de boxscores partido a partido -> totales de temporada de jugador, equipo y rival.

Formato estándar de partido que producen los adaptadores basados en boxscores:

    {
      "game_id": "104516", "date": "2025-11-02", "final": True,
      "teams": [
        {"team_id": "...", "name": "...", "code": "...",
         "totals": {canon: valor, ...} | None,       # fila 'Total' de la fuente si existe
         "players": [{"player_id", "name", "dorsal", "posicion", "starter": bool,
                      canon: valor, ...}, ...]},
        {...}                                         # rival
      ]
    }

Ventaja: los totales de equipo y rival son exactos, lo que mejora todas las métricas
avanzadas (posesiones, USG%, REB%, DRtg, ...).
"""
from __future__ import annotations

from collections import OrderedDict

from ..normalize import complete_counting
from ..schema import COUNTING_NAMES, TEAM_STATS
from .base import ParsedLeague

_TEAM_SUM = [s for s in TEAM_STATS if s not in {"gp", "w", "l"}]
_PLAYER_SUM = [c for c in COUNTING_NAMES if c not in {"gp", "gs", "dd2", "td3"}]
_DD_CATS = ("pts", "reb", "ast", "stl", "blk")


def _played(line: dict) -> bool:
    m = line.get("min")
    if m is not None:
        return m > 0
    return any((line.get(k) or 0) != 0 for k in ("pts", "fga", "fta", "reb", "ast", "stl", "tov", "pf", "blk"))


def _team_totals(side: dict) -> dict:
    tot = dict(side.get("totals") or {})
    players = side.get("players") or []
    for k in _TEAM_SUM:
        if tot.get(k) is None:
            vals = [p.get(k) for p in players if p.get(k) is not None]
            if vals:
                tot[k] = float(sum(vals))
    complete_counting(tot)
    return tot


def aggregate_games(games: list[dict], notes: list[str] | None = None) -> ParsedLeague:
    notes = list(notes or [])
    players: "OrderedDict[tuple, dict]" = OrderedDict()
    teams: "OrderedDict[str, dict]" = OrderedDict()
    n_games = 0
    for g in games:
        sides = g.get("teams") or []
        if len(sides) != 2:
            notes.append(f"Partido {g.get('game_id')} ignorado: {len(sides)} equipos en el boxscore")
            continue
        if not g.get("final", True):
            notes.append(f"Partido {g.get('game_id')} no finalizado: no se agrega")
            continue
        n_games += 1
        totals = [_team_totals(s) for s in sides]
        for i, side in enumerate(sides):
            tid = str(side.get("team_id") or side.get("code") or side.get("name"))
            t = teams.setdefault(tid, {"team_id": tid, "equipo": side.get("name"),
                                       "equipo_codigo": side.get("code"),
                                       "team_gp": 0.0, "team_w": 0.0, "team_l": 0.0})
            t["equipo"] = side.get("name") or t["equipo"]
            t["equipo_codigo"] = side.get("code") or t["equipo_codigo"]
            own, opp = totals[i], totals[1 - i]
            t["team_gp"] += 1
            if own.get("pts") is not None and opp.get("pts") is not None:
                t["team_w"] += own["pts"] > opp["pts"]
                t["team_l"] += own["pts"] < opp["pts"]
            for k in _TEAM_SUM:
                if own.get(k) is not None:
                    t[f"team_{k}"] = t.get(f"team_{k}", 0.0) + own[k]
                if opp.get(k) is not None:
                    t[f"opp_{k}"] = t.get(f"opp_{k}", 0.0) + opp[k]
            for line in side.get("players") or []:
                line = complete_counting(dict(line))
                pid = str(line.get("player_id") or line.get("name"))
                key = (pid, tid)
                p = players.setdefault(key, {"player_id": pid, "team_id": tid, "gp": 0.0, "gs": 0.0,
                                             "dd2": 0.0, "td3": 0.0})
                for idf in ("name", "dorsal", "posicion", "nacionalidad", "altura_cm", "edad",
                            "fecha_nacimiento", "peso_kg"):
                    if line.get(idf) not in (None, ""):
                        p["nombre" if idf == "name" else idf] = line[idf]
                p["equipo"] = side.get("name")
                p["equipo_codigo"] = side.get("code")
                if not _played(line):
                    continue
                p["gp"] += 1
                if "starter" in line:
                    p["_starter_info"] = True
                p["gs"] += 1 if line.get("starter") else 0
                for k in _PLAYER_SUM:
                    if line.get(k) is not None:
                        p[k] = p.get(k, 0.0) + float(line[k])
                tens = sum(1 for c in _DD_CATS if (line.get(c) or 0) >= 10)
                p["dd2"] += tens >= 2
                p["td3"] += tens >= 3
    for p in players.values():  # sin dato de titularidad en la fuente -> en blanco, no 0
        if not p.pop("_starter_info", False):
            p["gs"] = None
    notes.append(f"{n_games} partidos agregados")
    return ParsedLeague(players=list(players.values()), teams=list(teams.values()), notes=notes)


def aggregate_by_phase(games: list[dict], notes: list[str] | None = None) -> dict[str, ParsedLeague]:
    """Agrega por fase usando la clave 'phase' de cada partido ('regular', 'playoffs', ...).

    'total' incluye todos los partidos de la competición (también play-in u otras fases)."""
    out: dict[str, ParsedLeague] = {}
    phases = sorted({g.get("phase") or "regular" for g in games})
    for ph in phases:
        sel = [g for g in games if (g.get("phase") or "regular") == ph]
        out[ph] = aggregate_games(sel, [f"fase {ph}: {len(sel)} partidos en origen"])
    out["total"] = aggregate_games(games, list(notes or []))
    return out
