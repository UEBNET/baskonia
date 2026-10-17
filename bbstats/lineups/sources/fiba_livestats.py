"""Ligas con FIBA LiveStats (Basketbol Süper Ligi, Greek Basket League): jugada a jugada del data.json.

No hace peticiones: el adaptador principal (bbstats/adapters/fiba_livestats.py) guarda en su bruto el
data.json de cada partido, que trae a la vez el boxscore, el jugada a jugada y los tiros (se guarda UNA vez y
lo leen las dos capas).

  pbp[]  (orden DESCENDENTE de actionNumber; se ordena ascendente)
    actionType  2pt / 3pt (success = anotado), freethrow, rebound (subType offensive/defensive; pno 0 o
                qualifier "team" = de equipo), assist (previousAction = actionNumber de la canasta), turnover,
                steal, block, foul (comete; pno 0 = banquillo/entrenador), foulon (recibe), substitution
                (subType in/out), jumpball, timeout, period, game
    tno / pno   equipo 1|2 y número del jugador en tm[tno].pl
    period, periodType (REGULAR | OVERTIME: la prórroga N llega como period N con periodType OVERTIME)
    gt          reloj RESTANTE del periodo "MM:SS"
  tm[k].pl[pno]  sMinutes ("MM:SS"), sPlusMinusPoints, starter (0/1), nombre
  tm[k].shot[]   x, y (0-100, % de la pista COMPLETA, dos canastas), actionNumber (= el del pbp), r (anotado)

Ids: jugador = clave de nombre (adapters.fiba_livestats.player_key), equipo = el que asigna el adaptador
(adapters.fiba_livestats.season_teams: variantes del nombre unidas por plantilla), igual que en ligas/<liga>.csv.
"""
from __future__ import annotations

from ...adapters.fiba_livestats import _is_final, phase_map, player_key, season_teams
from ...utils import parse_minutes, to_float
from ..model import Event, Game, clock_to_seconds, elapsed
from .base import Ctx, PBPSource

SIMPLE = {"steal": "stl", "block": "blk", "turnover": "tov", "foul": "foul", "foulon": "foul_drawn"}


def _games_of(payload) -> dict:
    return (payload or {}).get("games") or {} if isinstance(payload, dict) else {}


class FibaLiveStatsPBP(PBPSource):
    name = "fiba_livestats"
    version = "1.0"
    uses_main_raw = True

    def games(self, ctx: Ctx) -> list[dict]:
        p = ctx.main_payload if isinstance(ctx.main_payload, dict) else {}
        docs = _games_of(p)
        teams = season_teams(docs, ctx.cfg.get("alias_equipos"))
        phases = phase_map(p, docs, teams, ctx.cfg, ctx.season)
        out = []
        for mid, doc in docs.items():
            ph = phases.get(mid)
            if ph not in ("regular", "playoffs"):
                continue
            t1, t2 = teams.get((mid, "1")), teams.get((mid, "2"))
            out.append({"game_id": mid, "phase": ph, "final": _is_final(doc),
                        "date": (p.get("fechas") or {}).get(mid),
                        "teams": [t1[0] if t1 else None, t2[0] if t2 else None],
                        "team_names": {t[0]: t[1] for t in (t1, t2) if t}})
        return sorted(out, key=lambda r: int(r["game_id"]) if r["game_id"].isdigit() else 0)

    def fetch(self, ctx: Ctx, ref: dict) -> dict:
        doc = _games_of(ctx.main_payload).get(str(ref["game_id"]))
        if not doc:
            raise ValueError("partido ausente del bruto principal")
        return {"data": doc}

    def parse(self, raw: dict, ref: dict, ctx: Ctx) -> Game:
        doc = raw.get("data") or {}
        tm = doc.get("tm") or {}
        tids = list(ref.get("teams") or [None, None])
        for i, k in enumerate(("1", "2")):
            tids[i] = tids[i] or (tm.get(k) or {}).get("name") or k
        tid_of = {"1": tids[0], "2": tids[1]}
        g = Game(game_id=str(ref["game_id"]), phase=ref.get("phase", "regular"), teams=tids, date=ref.get("date"),
                 coord_system="FIBA LiveStats x/y 0-100 (% de la pista completa, dos canastas)")
        g.team_names = {tid_of[k]: (ref.get("team_names") or {}).get(tid_of[k]) or (tm.get(k) or {}).get("name")
                        for k in ("1", "2")}
        pid_of: dict[tuple[str, str], str] = {}
        for k in ("1", "2"):
            st = []
            for pno, p in ((tm.get(k) or {}).get("pl") or {}).items():
                pid = str(p.get("personId") or player_key(p))
                pid_of[(k, str(pno))] = pid
                name = f"{p.get('firstName') or ''} {p.get('familyName') or ''}".strip() or p.get("name")
                g.players[pid] = {"nombre": name, "team": tid_of[k]}
                m = parse_minutes(p.get("sMinutes"))
                g.box[pid] = {"sec": m * 60 if m is not None else None, "pm": to_float(p.get("sPlusMinusPoints"))}
                if to_float(p.get("starter")):
                    st.append(pid)
            g.starters[tid_of[k]] = st if len(st) == 5 else []
        xy = {}
        for k in ("1", "2"):
            for s in (tm.get(k) or {}).get("shot") or []:
                xy[s.get("actionNumber")] = (to_float(s.get("x")), to_float(s.get("y")))

        acts = sorted((a for a in doc.get("pbp") or [] if isinstance(a, dict)),
                      key=lambda a: int(to_float(a.get("actionNumber")) or 0))
        evs: list[Event] = []
        by_num: dict = {}
        assists: list[tuple[str, str, object]] = []
        n_sub = 0
        for order, a in enumerate(acts, 1):
            at, sub = a.get("actionType"), a.get("subType")
            per = int(to_float(a.get("period")) or 1)
            if str(a.get("periodType") or "").upper() == "OVERTIME" and per <= 4:
                per += 4
            t = elapsed(per, clock_to_seconds(a.get("gt")), ctx.game_min)
            k = str(a.get("tno") or "")
            team = tid_of.get(k)
            pno = str(a.get("pno") or "0")
            pid = pid_of.get((k, pno)) if pno != "0" else None
            kw = {"order": order, "period": per, "t": t, "team": team, "player": pid}
            e = None
            if at in ("2pt", "3pt"):
                v = 2 if at == "2pt" else 3
                made = bool(to_float(a.get("success")))
                x, y = xy.get(a.get("actionNumber"), (None, None))
                e = Event(kind="shot", value=v, made=made, pts=v if made else 0, x=x, y=y, **kw)
            elif at == "freethrow":
                made = bool(to_float(a.get("success")))
                e = Event(kind="ft", value=1, made=made, pts=1 if made else 0, **kw)
            elif at == "rebound":
                if "team" in (a.get("qualifier") or []):
                    kw["player"] = None
                e = Event(kind="oreb" if sub == "offensive" else "dreb", **kw)
            elif at == "substitution" and pid and sub in ("in", "out"):
                n_sub += 1
                e = Event(kind=sub, **kw)
            elif at in SIMPLE and team:
                e = Event(kind=SIMPLE[at], **kw)
            elif at == "assist" and pid and team:
                assists.append((team, pid, a.get("previousAction")))
            if e is not None:
                evs.append(e)
                by_num[a.get("actionNumber")] = e
        left = 0
        for team, pid, prev in assists:
            target = by_num.get(prev if not isinstance(prev, str) or not prev.isdigit() else int(prev))
            if target is not None and target.kind in ("shot", "ft") and target.made and target.team == team \
                    and target.assister is None and target.player != pid:
                target.assister, target.ast_ft = pid, target.kind == "ft"
            else:
                left += 1
        g.events = evs
        g.has_shots = any(e.x is not None for e in evs if e.kind == "shot")
        g.has_assists = bool(assists)
        if not evs:
            g.has_lineups = g.has_assists = False
            g.notes.append("la fuente no tiene jugada a jugada de este partido")
        elif not n_sub:
            g.has_lineups = False
            g.notes.append("jugada a jugada sin cambios: sólo tiros y asistencias")
        if left:
            g.notes.append(f"{left}/{len(assists)} asistencias sin enlazar")
        return g


def docs_principal(main_payload, game_id: str) -> dict | None:
    """data.json del partido sacado del bruto principal (para el registro de entrenadores)."""
    doc = _games_of(main_payload).get(str(game_id))
    return {"data": doc} if doc else None
