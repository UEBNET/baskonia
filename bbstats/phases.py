"""Fases de competición: regular, playoffs y total.

Cada adaptador devuelve un dict {fase: ParsedLeague}. Cuando la fuente no publica alguna fase
directamente se deriva de forma exacta con las estadísticas de conteo (son aditivas):

  * total    = suma de todas las fases (regular + playoffs + otras, p.ej. la Showcase Cup de la G League)
  * playoffs = total - regular (p.ej. Euroliga, donde el feed da el total y la temporada regular)

Las métricas oficiales `src_*` (porcentajes, ratings) NO son aditivas: en una fase derivada quedan
en blanco, y el motor de métricas recalcula todo lo avanzado con los totales de esa fase.
"""
from __future__ import annotations

from .adapters.base import ParsedLeague
from .normalize import complete_counting
from .schema import COUNTING_NAMES, TEAM_STATS

PHASES = ("regular", "playoffs", "total")
_ID_FIELDS = ("nombre", "equipo", "equipo_codigo", "posicion", "dorsal", "altura_cm", "peso_kg", "edad",
              "fecha_nacimiento", "nacionalidad")
_TEAM_KEYS = [f"team_{s}" for s in TEAM_STATS] + [f"opp_{s}" for s in TEAM_STATS if s not in {"gp", "w", "l"}]
_NON_ADDITIVE = {"edad"}


def _key(r: dict) -> tuple:
    return str(r.get("player_id")), str(r.get("team_id"))


def sum_phases(parts: list[ParsedLeague], notes: list[str] | None = None) -> ParsedLeague:
    players: dict[tuple, dict] = {}
    teams: dict[str, dict] = {}
    for part in parts:
        for r in part.players:
            p = players.setdefault(_key(r), {"player_id": r.get("player_id"), "team_id": r.get("team_id")})
            for f in _ID_FIELDS:
                if r.get(f) not in (None, ""):
                    p[f] = r[f]
            for c in COUNTING_NAMES:
                if r.get(c) is not None:
                    p[c] = (p.get(c) or 0.0) + float(r[c])
        for t in part.teams:
            tid = str(t.get("team_id"))
            q = teams.setdefault(tid, {"team_id": tid})
            for f in ("equipo", "equipo_codigo"):
                if t.get(f):
                    q[f] = t[f]
            for c in _TEAM_KEYS:
                if t.get(c) is not None:
                    q[c] = (q.get(c) or 0.0) + float(t[c])
    for p in players.values():
        complete_counting(p)
    return ParsedLeague(players=list(players.values()), teams=list(teams.values()), notes=list(notes or []))


def subtract_phase(total: ParsedLeague, part: ParsedLeague, notes: list[str] | None = None) -> ParsedLeague:
    """total - part para estadísticas de conteo. Se descartan filas sin partidos en el resultado."""
    sub_p = {_key(r): r for r in part.players}
    sub_t = {str(t.get("team_id")): t for t in part.teams}
    players = []
    for r in total.players:
        s = sub_p.get(_key(r), {})
        p = {f: r.get(f) for f in ("player_id", "team_id", *_ID_FIELDS) if r.get(f) is not None}
        for c in COUNTING_NAMES:
            if r.get(c) is not None:
                p[c] = float(r[c]) - float(s.get(c) or 0.0)
        if (p.get("gp") or 0) > 0:
            complete_counting(p)
            players.append(p)
    teams = []
    for t in total.teams:
        s = sub_t.get(str(t.get("team_id")), {})
        q = {f: t.get(f) for f in ("team_id", "equipo", "equipo_codigo") if t.get(f) is not None}
        for c in _TEAM_KEYS:
            if t.get(c) is not None:
                q[c] = float(t[c]) - float(s.get(c) or 0.0)
        if (q.get("team_gp") or 0) > 0:
            teams.append(q)
    return ParsedLeague(players=players, teams=teams, notes=list(notes or []))


def ensure_phases(parsed: dict[str, ParsedLeague]) -> dict[str, ParsedLeague]:
    """Garantiza que existe 'total' (sumando fases) y elimina fases vacías."""
    parsed = {k: v for k, v in parsed.items() if v is not None and v.players}
    if "total" not in parsed and parsed:
        parsed["total"] = sum_phases(list(parsed.values()),
                                     [f"Fase total = suma de: {', '.join(sorted(parsed))}"])
    return parsed
