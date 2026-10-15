"""EuroLeague (E) y EuroCup (U): jugada a jugada oficial de live.euroleague.net.

  Partidos:  https://api-live.euroleague.net/v2/competitions/{C}/seasons/{C}{año}/games
  PBP:       https://live.euroleague.net/api/PlayByPlay?gamecode=N&seasoncode=E2024
  Boxscore:  https://live.euroleague.net/api/Boxscore?...   (titulares IsStarter, Minutes, Plusminus)
  Tiros:     https://live.euroleague.net/api/Points?...      (COORD_X/COORD_Y; NUM_ANOT = NUMBEROFPLAY)
Ids: jugador "P004007" -> "004007", "PKIR" -> "KIR" (igual que en los datos principales); equipo = código de club.
Asistencias: evento AS sin enlace -> se enlaza al último tiro anotado del mismo equipo.
"""
from __future__ import annotations

import re

from ...http import FetchError
from ..model import Event, Game, clock_to_seconds, elapsed, link_assists_by_adjacency
from .base import Ctx, PBPSource

LIVE = "https://live.euroleague.net/api"
API = "https://api-live.euroleague.net/v2/competitions"
QUARTERS = ("FirstQuarter", "SecondQuarter", "ThirdQuarter", "ForthQuarter", "ExtraTime")
FOULS = {"CM", "CMU", "CMT", "CMD", "OF", "CMTI", "CMB"}


def _pid(v) -> str | None:
    s = (v or "").strip()
    if not s:
        return None
    return s[1:] if s[:1] == "P" and len(s) > 1 else s   # como el adaptador principal: "P004007" -> "004007", "PKIR" -> "KIR"


def _tid(v) -> str | None:
    s = (v or "").strip()
    return s or None


class EuroleaguePBP(PBPSource):
    name = "euroleague_live"
    version = "1.0"

    def _code(self, ctx: Ctx) -> str:
        return f"{ctx.cfg.get('competicion', 'E')}{ctx.start_year}"

    def games(self, ctx: Ctx) -> list[dict]:
        comp = ctx.cfg.get("competicion", "E")
        doc = ctx.http.get_json(f"{API}/{comp}/seasons/{self._code(ctx)}/games")
        out = []
        for g in doc.get("data", []):
            phase = "regular" if ((g.get("phaseType") or {}).get("code") == "RS") else "playoffs"
            out.append({"game_id": str(g["gameCode"]), "phase": phase, "final": bool(g.get("played")),
                        "date": g.get("date"), "round": g.get("round")})
        return out

    def fetch(self, ctx: Ctx, ref: dict) -> dict:
        params = {"gamecode": ref["game_id"], "seasoncode": self._code(ctx)}
        raw = {"pbp": ctx.http.get_json(f"{LIVE}/PlayByPlay", params=params),
               "box": ctx.http.get_json(f"{LIVE}/Boxscore", params=params)}
        try:
            raw["points"] = ctx.http.get_json(f"{LIVE}/Points", params=params)
        except FetchError as exc:
            ctx.errors.append(f"Points {ref['game_id']}: {exc}")
            raw["points"] = None
        return raw

    def parse(self, raw: dict, ref: dict, ctx: Ctx) -> Game:
        pbp, box = raw.get("pbp") or {}, raw.get("box") or {}
        teams = [_tid(pbp.get("CodeTeamA")), _tid(pbp.get("CodeTeamB"))]
        g = Game(game_id=ref["game_id"], phase=ref.get("phase", "regular"), teams=[t for t in teams if t],
                 date=ref.get("date"), coord_system="live.euroleague.net COORD_X/COORD_Y (unidades de la fuente)")
        g.team_names = {teams[0]: pbp.get("TeamA"), teams[1]: pbp.get("TeamB")}
        for tstats in box.get("Stats") or []:
            st = []
            for ps in tstats.get("PlayersStats") or []:
                pid, tid = _pid(ps.get("Player_ID")), _tid(ps.get("Team"))
                if not pid:
                    continue
                g.players[pid] = {"nombre": (ps.get("Player") or "").strip(), "team": tid}
                mins = ps.get("Minutes")
                sec = clock_to_seconds(mins) if mins and ":" in str(mins) else (0.0 if mins in (None, "", "DNP") else None)
                g.box[pid] = {"sec": sec, "pm": ps.get("Plusminus")}
                if ps.get("IsStarter"):
                    st.append(pid)
                if tid and tid not in g.starters:
                    g.starters[tid] = []
            if st:
                g.starters[_tid((tstats.get("PlayersStats") or [{}])[0].get("Team"))] = st
        coords = {}
        for r in ((raw.get("points") or {}).get("Rows") or []):
            coords[r.get("NUM_ANOT")] = (r.get("COORD_X"), r.get("COORD_Y"))
        g.has_shots = bool(coords)
        evs, markers, period, last_t, seq = [], [], 0, 0.0, 0
        for q in QUARTERS:
            for e in pbp.get(q) or []:
                pt = (e.get("PLAYTYPE") or "").strip()
                n = int(e.get("NUMBEROFPLAY") or 0)   # identifica el tiro en Points; no siempre es correlativo
                seq += 1
                if pt == "BP":
                    period += 1
                    last_t = elapsed(period, None, ctx.game_min, elapsed_in_period_s=0)
                    continue
                if period == 0:
                    period = QUARTERS.index(q) + 1
                rem = clock_to_seconds(e.get("MARKERTIME"))
                t = elapsed(period, rem, ctx.game_min) if rem is not None else last_t
                last_t = t
                tm, pid = _tid(e.get("CODETEAM")), _pid(e.get("PLAYER_ID"))
                kw = {"order": seq, "period": period, "t": t, "team": tm, "player": pid}
                m = re.match(r"^([23])FG([AM])$", pt)
                if pt == "IN":
                    evs.append(Event(kind="in", **kw))
                elif pt == "OUT":
                    evs.append(Event(kind="out", **kw))
                elif m:
                    v, made = int(m.group(1)), m.group(2) == "M"
                    x, y = coords.get(n, (None, None))
                    evs.append(Event(kind="shot", value=v, made=made, pts=v if made else 0, x=x, y=y, **kw))
                elif pt in ("FTM", "FTA"):
                    evs.append(Event(kind="ft", value=1, made=pt == "FTM", pts=1 if pt == "FTM" else 0, **kw))
                elif pt == "O":
                    evs.append(Event(kind="oreb", **kw))
                elif pt == "D":
                    evs.append(Event(kind="dreb", **kw))
                elif pt == "TO":
                    evs.append(Event(kind="tov", **kw))
                elif pt == "ST":
                    evs.append(Event(kind="stl", **kw))
                elif pt == "FV":
                    evs.append(Event(kind="blk", **kw))
                elif pt in FOULS:
                    evs.append(Event(kind="foul", **kw))
                elif pt == "RV":
                    evs.append(Event(kind="foul_drawn", **kw))
                elif pt == "AS" and pid and tm:
                    markers.append((seq, tm, pid, t))
        # Se respeta el orden de la lista aunque la numeración (NUMBEROFPLAY) o el reloj no sean correlativos:
        # recolocar por reloj las jugadas corregidas empeora la coincidencia con el +/- oficial (probado en
        # EuroCup 2025-26 y 2026-27 y EuroLeague 2026-27).
        items = sorted([(e.t, e.order, 0, e) for e in evs] + [(m[3], m[0], 1, m) for m in markers],
                       key=lambda it: it[1])
        markers2 = []
        for i, (_, _, is_marker, obj) in enumerate(items, 1):
            if is_marker:
                markers2.append((i, obj[1], obj[2]))
            else:
                obj.order = i
        g.events = sorted(evs, key=lambda e: e.order)
        left = link_assists_by_adjacency(g.events, markers2)
        if left:
            g.notes.append(f"{left} asistencias sin enlazar")
        return g
