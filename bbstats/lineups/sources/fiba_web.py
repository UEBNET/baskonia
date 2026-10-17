"""Basketball Champions League y FIBA Europe Cup: jugada a jugada de las páginas públicas de fiba.basketball.

No hace peticiones: el adaptador principal (bbstats/adapters/fiba_web.py) guarda en su bruto, por partido, el
JSON de datos de la página (`page`): el mismo documento sirve al boxscore y al jugada a jugada.

  page.playByPlay.items.<Q1..Q4, OT1..>.items[]:
      ac    código: P2 / P3 (tiro de campo, `made`, `pts`, `x`/`y`), FT (tiro libre), REB (rebote; `txt`
            "offensive rebound"/"defensive rebound", nulo en 2020-21), TREB (rebote de equipo), ASS
            (asistencia: la canasta anotada inmediatamente anterior del mismo equipo), ST (robo), BS (tapón),
            TO / TTO (pérdida / de equipo), FOUL (falta cometida), RFOUL (falta recibida), SUBST (cambio:
            `in` = "IN" | "OUT"), JB/JS (salto), TIMO (tiempo muerto), STARTP/ENDP/STARTG/ENDG, VTR
      Time  reloj RESTANTE del periodo ("9:44"; en 2020-21 "9:0")
      pId   personId del jugador; oId = organisationId del equipo; Id = número de acción; order (desde 2025)
  page.gameDetails.c[].Children[].Stats: TP (minutos "mm:ss"), PM (+/-), Starter (titular).

Orden: el de la lista de cada periodo cuando la fuente trae `order` (desde 2025-26); antes, reloj y número
de acción (Id), porque la lista mezcla acciones de un mismo segundo (asistencia antes de su canasta).
Rebotes sin texto (2020-21): ofensivo si el último tiro fallado era del mismo equipo.
Coordenadas: x, y del tiro en unidades de la web (media pista de 0-280 × 0-~260, el aro hacia x≈140, y≈25:
se calibran en bbmodel/zonas.py).
"""
from __future__ import annotations

import re

from ...adapters.fiba_web import EXCLUDED_ROUNDS, is_final, round_phase
from ...utils import parse_minutes, to_float
from ..model import Event, Game, clock_to_seconds, elapsed, link_assists_by_adjacency
from .base import Ctx, PBPSource

_PER = re.compile(r"^(Q|OT)(\d+)$")


def _s(v) -> str | None:
    if v is None or v == "" or v == "$undefined":
        return None
    return str(v)


def _games_of(payload) -> dict:
    return (payload or {}).get("games") or {} if isinstance(payload, dict) else {}


def _period(key: str) -> int:
    m = _PER.match(str(key))
    if not m:
        return 0
    return int(m.group(2)) if m.group(1) == "Q" else 4 + int(m.group(2))


class FibaWebPBP(PBPSource):
    name = "fiba_web"
    version = "1.0"
    uses_main_raw = True

    def games(self, ctx: Ctx) -> list[dict]:
        p = ctx.main_payload if isinstance(ctx.main_payload, dict) else {}
        excluded = tuple(ctx.cfg.get("rondas_excluidas", EXCLUDED_ROUNDS))
        phases = {str(g["gameId"]): round_phase(g["round"], excluded) for g in p.get("calendario") or []}
        out = []
        for gid, doc in _games_of(p).items():
            g = (doc.get("page") or {}).get("game") or {}
            ph = phases.get(gid) or (round_phase(g["round"], excluded) if isinstance(g.get("round"), dict) else None)
            if ph is None:
                continue
            out.append({"game_id": gid, "phase": ph, "final": is_final(g), "date": g.get("gameDateTimeUTC")})
        return sorted(out, key=lambda r: (r.get("date") or "", r["game_id"]))

    def fetch(self, ctx: Ctx, ref: dict) -> dict:
        doc = _games_of(ctx.main_payload).get(str(ref["game_id"]))
        if not doc:
            raise ValueError("partido ausente del bruto principal")
        return {"page": doc.get("page")}

    def parse(self, raw: dict, ref: dict, ctx: Ctx) -> Game:
        page = raw.get("page") or {}
        gm = page.get("game") or {}
        teams = [_s((gm.get(k) or {}).get("organisationId")) for k in ("teamA", "teamB")]
        g = Game(game_id=str(ref["game_id"]), phase=ref.get("phase", "regular"), teams=[t for t in teams if t],
                 date=ref.get("date") or gm.get("gameDateTimeUTC"),
                 coord_system="fiba.basketball x/y (media pista, unidades de la web; aro ≈ (140, 25))")
        g.team_names = {teams[i]: (gm.get(k) or {}).get("shortName") for i, k in enumerate(("teamA", "teamB"))}
        names = {}
        for rk, tid in (("playersTeamA", teams[0]), ("playersTeamB", teams[1])):
            for p in page.get(rk) or []:
                names[str(p.get("personId"))] = (f"{p.get('firstName') or ''} {p.get('lastName') or ''}".strip(), tid)
        for c in (page.get("gameDetails") or {}).get("c") or []:
            tid = str(c.get("Id", "")).removeprefix("T_")
            st = []
            for ch in c.get("Children") or []:
                pid = str(ch.get("Id", "")).removeprefix("P_")
                s = ch.get("Stats") if isinstance(ch.get("Stats"), dict) else {}
                g.players[pid] = {"nombre": (names.get(pid) or (pid,))[0], "team": tid}
                sec = parse_minutes(s.get("TP"))
                g.box[pid] = {"sec": sec * 60 if sec is not None else (0.0 if not s.get("HasPlayed", True) else None),
                              "pm": to_float(s.get("PM"))}
                if s.get("Starter"):
                    st.append(pid)
            g.starters[tid] = st if len(st) == 5 else []

        evs: list[Event] = []
        markers: list[tuple[int, str, str]] = []
        last_miss_team = None
        n_xy = n_sub = 0
        order = 0
        periods = sorted((page.get("playByPlay") or {}).get("items", {}).items(), key=lambda kv: _period(kv[0]))
        for key, per in periods:
            period = _period(key)
            if not period:
                continue
            items = per.get("items") or []
            if not any(isinstance(a.get("order"), (int, float)) for a in items):
                # hasta 2024-25 no hay `order` y la lista no siempre respeta la secuencia dentro de un mismo
                # segundo (asistencia antes de su canasta, entra antes de sale): reloj y número de acción
                items = sorted(items, key=lambda a: (-(clock_to_seconds(a.get("Time")) or 0),
                                                     int(to_float(a.get("Id")) or 0)))
            for a in items:
                ac = a.get("ac")
                order += 1
                rem = clock_to_seconds(a.get("Time"))
                t = elapsed(period, rem, ctx.game_min)
                tm, pid = _s(a.get("oId")), _s(a.get("pId"))
                if pid and pid not in g.players and tm:
                    g.players[pid] = {"nombre": (names.get(pid) or (pid,))[0], "team": tm}
                kw = {"order": order, "period": period, "t": t, "team": tm, "player": pid}
                if ac in ("P2", "P3"):
                    v = 2 if ac == "P2" else 3
                    made = bool(a.get("made"))
                    x, y = to_float(a.get("x")), to_float(a.get("y"))
                    if x is not None and y is not None and (x or y):
                        n_xy += 1
                    else:
                        x = y = None
                    evs.append(Event(kind="shot", value=v, made=made, pts=v if made else 0, x=x, y=y, **kw))
                    last_miss_team = None if made else tm
                elif ac == "FT":
                    made = bool(a.get("made"))
                    evs.append(Event(kind="ft", value=1, made=made, pts=1 if made else 0, **kw))
                    last_miss_team = None if made else tm
                elif ac in ("REB", "TREB"):
                    txt = str(a.get("txt") or "").lower()
                    if "offensive" in txt:
                        kind = "oreb"
                    elif "defensive" in txt:
                        kind = "dreb"
                    else:
                        kind = "oreb" if last_miss_team is not None and last_miss_team == tm else "dreb"
                    if ac == "TREB":
                        kw["player"] = None
                    evs.append(Event(kind=kind, **kw))
                    last_miss_team = None
                elif ac == "ASS":
                    if pid and tm:
                        markers.append((order, tm, pid))
                elif ac == "ST":
                    evs.append(Event(kind="stl", **kw))
                elif ac == "BS":
                    evs.append(Event(kind="blk", **kw))
                elif ac in ("TO", "TTO"):
                    if ac == "TTO":
                        kw["player"] = None
                    evs.append(Event(kind="tov", **kw))
                elif ac == "FOUL":
                    evs.append(Event(kind="foul", **kw))
                elif ac == "RFOUL":
                    evs.append(Event(kind="foul_drawn", **kw))
                elif ac == "SUBST" and pid:
                    n_sub += 1
                    evs.append(Event(kind="in" if str(a.get("in")).upper() == "IN" else "out", **kw))
        g.events = evs
        g.has_shots = n_xy > 0
        g.has_assists = bool(markers)
        if not evs:
            g.has_lineups = g.has_assists = False
            g.notes.append("la fuente no tiene jugada a jugada de este partido")
            return g
        if not n_sub:
            g.has_lineups = False
            g.notes.append("jugada a jugada sin cambios: sólo tiros y asistencias")
        left = link_assists_by_adjacency(evs, markers)
        if left:
            g.notes.append(f"{left}/{len(markers)} asistencias sin enlazar")
        return g
