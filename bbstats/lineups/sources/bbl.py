"""easyCredit BBL (Alemania): jugada a jugada de las páginas públicas de partido de easycredit-bbl.de.

No hace peticiones: el adaptador principal (bbstats/adapters/bbl.py) ya guarda en su bruto, por id de
partido, los datos de la página (`__NEXT_DATA__.props.pageProps`):
  initialGameData            temporada, fase (stage), estado, equipos (teamId) y resultado
  initialGameStats.actions[] type, period, gameTime ("00:09:34" restante), seasonTeamId, seasonPlayerId,
                             assistingSeasonPlayerId, qualifiers, coordinates{x,y}, orderId
  initialGameStats.<side>    boxscore: playerStats[] (secondsPlayed, plusMinus, isStartingFive, seasonPlayer)
Sólo si un partido del bruto no trae `actions` se vuelve a leer su página (fetch).

Ids: `seasonPlayerId` de las acciones = `seasonPlayer.id` del boxscore = `player_id` de los datos
principales; `seasonTeamId` = `teamId` (el adaptador usa initialGameData.<side>.teamId). Se comprueba al
interpretar y, si no coincidieran, se traducen.

Cambios (SUBSTITUTION): seasonPlayerId = sale, assistingSeasonPlayerId = entra → "out" + "in".
Los cambios entre cuartos no se anotan: stints.build deduce el quinteto de cada periodo.
Asistencias: assistingSeasonPlayerId en tiros (y tiros libres) anotados.

Temporadas 2020-21 … 2022-23: cambios, rebotes, faltas y tiros fallados sin jugador → has_lineups=False
(sí tiros anotados con asistente: redes de asistencias). 2023-24: algunos cambios con un jugador nulo; se
completa con el jugador que encaja (el que está en pista y no vuelve a actuar hasta reentrar / el que está
en el banquillo y actúa a continuación sin entrar).
"""
from __future__ import annotations

import json
import re

from ..model import Event, Game, clock_to_seconds, elapsed
from .base import Ctx, PBPSource

SITE = "https://www.easycredit-bbl.de"
REGULAR_STAGES = {"MAIN_ROUND"}
_NEXT = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
SIDES = ("homeTeam", "guestTeam")
PLAYER_TYPES = {"SUBSTITUTION", "TWO_POINT_THROW", "THREE_POINT_THROW", "FREE_THROW", "REBOUND", "TURN_OVER",
                "STEAL", "BLOCK", "FOUL", "RECEIVED_FOUL"}
SIMPLE = {"TURN_OVER": "tov", "TEAM_TURN_OVER": "tov", "STEAL": "stl", "BLOCK": "blk", "FOUL": "foul",
          "RECEIVED_FOUL": "foul_drawn"}


def _s(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s and s != "0" else None


def _num(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _games_of(payload) -> dict:
    return (payload or {}).get("games") or {} if isinstance(payload, dict) else {}


class BblPBP(PBPSource):
    name = "bbl_web"
    version = "1.0"
    uses_main_raw = True

    def games(self, ctx: Ctx) -> list[dict]:
        out = []
        for gid, doc in _games_of(ctx.main_payload).items():
            gd = (doc or {}).get("initialGameData") or {}
            if not gd:
                continue
            out.append({"game_id": str(gd.get("id") or gid),
                        "phase": "regular" if gd.get("stage") in REGULAR_STAGES else "playoffs",
                        "final": gd.get("status") == "OFFICIAL", "date": gd.get("scheduledTime"),
                        "stage": gd.get("stage")})
        return sorted(out, key=lambda r: (r.get("date") or "", r["game_id"]))

    def fetch(self, ctx: Ctx, ref: dict) -> dict:
        doc = _games_of(ctx.main_payload).get(str(ref["game_id"])) or {}
        if (doc.get("initialGameStats") or {}).get("actions") is not None and doc.get("initialGameData"):
            return {"initialGameData": doc["initialGameData"], "initialGameStats": doc["initialGameStats"]}
        if ctx.http is None:
            raise ValueError("el bruto principal no tiene las acciones de este partido")
        html = ctx.http.get_text(f"{SITE}/spiele/{ref['game_id']}")
        m = _NEXT.search(html or "")
        pp = ((json.loads(m.group(1)).get("props") or {}).get("pageProps") or {}) if m else {}
        return {"initialGameData": pp.get("initialGameData"), "initialGameStats": pp.get("initialGameStats")}

    def parse(self, raw: dict, ref: dict, ctx: Ctx) -> Game:
        gd, gs = raw.get("initialGameData") or {}, raw.get("initialGameStats") or {}
        tmap: dict[str, str] = {}
        teams = []
        for side in SIDES:
            tid = _s((gd.get(side) or {}).get("teamId")) or _s((gs.get(side) or {}).get("id"))
            teams.append(tid)
            for k in ((gs.get(side) or {}).get("id"), (gd.get(side) or {}).get("seasonTeamId"), tid):
                if _s(k):
                    tmap[_s(k)] = tid
        game_min = ctx.game_min
        g = Game(game_id=str(gd.get("id") or ref["game_id"]), phase=ref.get("phase") or (
            "regular" if gd.get("stage") in REGULAR_STAGES else "playoffs"), teams=[t for t in teams if t],
            date=ref.get("date") or gd.get("scheduledTime"),
            coord_system="easycredit-bbl.de coordinates{x,y} (unidades de la fuente; 0,0 = sin coordenadas)")
        g.team_names = {teams[i]: (gd.get(s) or {}).get("name") for i, s in enumerate(SIDES) if teams[i]}
        pmap: dict[str, str] = {}
        for i, side in enumerate(SIDES):
            st = []
            for ps in (gs.get(side) or {}).get("playerStats") or []:
                sp = ps.get("seasonPlayer") or {}
                pid = _s(sp.get("playerId")) or _s(sp.get("id"))
                if not pid:
                    continue
                pmap[_s(sp.get("id")) or pid] = pid
                pmap[pid] = pid
                g.players[pid] = {"nombre": f"{sp.get('firstName') or ''} {sp.get('lastName') or ''}".strip(),
                                  "team": teams[i]}
                g.box[pid] = {"sec": _num(ps.get("secondsPlayed")), "pm": _num(ps.get("plusMinus"))}
                if ps.get("isStartingFive"):
                    st.append(pid)
            if teams[i]:
                g.starters[teams[i]] = st if len(st) == 5 else []

        def P(v):
            v = _s(v)
            return pmap.get(v, v) if v else None

        actions = sorted((a for a in (gs.get("actions") or []) if isinstance(a, dict)),
                         key=lambda a: (a.get("orderId") is None, a.get("orderId") or 0))
        # Jugador "fantasma" (2023-24): juega según el boxscore pero no aparece en ninguna acción; sus
        # acciones llegan con seasonPlayerId nulo. Si en un equipo hay exactamente uno, se le asignan las
        # acciones nulas de su equipo mientras está en pista (ver _fill_nulls).
        seen = {P(a.get(k)) for a in actions for k in ("seasonPlayerId", "assistingSeasonPlayerId")}
        ghost: dict[str, str] = {}
        for t in g.teams:
            miss = [p for p, i in g.players.items() if i.get("team") == t and p not in seen
                    and (g.box.get(p, {}).get("sec") or 0) > 0]
            if len(miss) == 1:
                ghost[t] = miss[0]
        nullp: set[int] = set()
        evs: list[Event] = []
        n_sub = n_sub_ok = 0
        last = {}
        seq = 0
        for a in actions:
            typ = a.get("type")
            try:
                per = int(a.get("period") or 0)
            except (TypeError, ValueError):
                continue
            if not typ or per <= 0:
                continue
            rem = clock_to_seconds(a.get("gameTime"))
            t = elapsed(per, rem, game_min) if rem is not None else last.get(per, elapsed(per, None, game_min, 0))
            t = max(t, last.get(per, t))
            last[per] = t
            tm = tmap.get(_s(a.get("seasonTeamId")) or "", _s(a.get("seasonTeamId")))
            pid, ast = P(a.get("seasonPlayerId")), P(a.get("assistingSeasonPlayerId"))
            ok = bool(a.get("isSuccessful"))
            seq += 1
            kw = {"order": seq, "period": per, "t": t, "team": tm}
            if typ in PLAYER_TYPES and pid is None and typ != "SUBSTITUTION":
                nullp.add(seq)
            if typ == "SUBSTITUTION":
                n_sub += 1
                n_sub_ok += bool(pid and ast)
                evs.append(Event(kind="out", player=pid, **kw))
                seq += 1
                evs.append(Event(kind="in", player=ast, **{**kw, "order": seq}))
            elif typ in ("TWO_POINT_THROW", "THREE_POINT_THROW"):
                v = 2 if typ.startswith("TWO") else 3
                c = a.get("coordinates") or {}
                x, y = c.get("x"), c.get("y")
                if not x and not y:
                    x = y = None
                evs.append(Event(kind="shot", player=pid, value=v, made=ok, pts=v if ok else 0,
                                 assister=ast if ok and ast != pid else None, x=x, y=y, **kw))
            elif typ == "FREE_THROW":
                evs.append(Event(kind="ft", player=pid, value=1, made=ok, pts=1 if ok else 0,
                                 assister=ast if ok and ast and ast != pid else None,
                                 ast_ft=bool(ok and ast and ast != pid), **kw))
            elif typ in ("REBOUND", "TEAM_REBOUND"):
                q = a.get("qualifiers") or []
                kind = "oreb" if "OFFENSIVE" in q else "dreb"
                evs.append(Event(kind=kind, player=pid if typ == "REBOUND" else None, **kw))
            elif typ in SIMPLE:
                evs.append(Event(kind=SIMPLE[typ], player=pid if typ != "TEAM_TURN_OVER" else None, **kw))
        g.events = evs
        g.has_assists = any(e.assister for e in evs)
        g.has_shots = any(e.x is not None for e in evs if e.kind == "shot")
        if not actions:
            g.has_lineups = False
            g.notes.append("sin jugada a jugada")
        elif n_sub == 0 or n_sub_ok / n_sub < 0.5:
            g.has_lineups = False
            g.notes.append(f"cambios sin jugador ({n_sub - n_sub_ok}/{n_sub}): sin quintetos")
        else:
            fixed, left, n_ghost = _fill_nulls(g, ghost, nullp)
            if fixed or left:
                g.notes.append(f"cambios con jugador nulo: {fixed} completados, {left} sin completar")
            if n_ghost:
                g.notes.append(f"{n_ghost} acciones nulas asignadas al jugador del boxscore ausente del "
                               "jugada a jugada")
        unknown = {e.player for e in evs if e.player and e.player not in g.players}
        if unknown:
            g.notes.append(f"{len(unknown)} jugadores del jugada a jugada sin boxscore")
        return g


def _fill_nulls(g: Game, ghost: dict[str, str], nullp: set[int]) -> tuple[int, int, int]:
    """Completa jugadores nulos simulando quién está en pista (misma lógica de quinteto por periodo que
    stints.build).
      * ghost[team]: único jugador del boxscore que no aparece en el jugada a jugada. Ocupa el hueco del
        quinteto de un periodo si faltan 4, entra/sale en los cambios nulos y recibe las acciones nulas
        (`nullp`, por order) de su equipo mientras está en pista.
      * sin fantasma: salida nula -> jugador en pista cuya siguiente aparición es entrar (o que no vuelve a
        aparecer en el periodo); entrada nula -> jugador del banquillo que actúa antes sin haber entrado.
    Devuelve (cambios completados, cambios sin completar, acciones asignadas al fantasma)."""
    evs = sorted(g.events, key=lambda e: e.order)
    roster = {t: [p for p, i in g.players.items() if i.get("team") == t] for t in g.teams}
    on: dict[str, set] = {t: set(g.starters.get(t) or []) for t in g.teams}
    fixed = left = n_ghost = 0
    left_at: dict[str, float] = {}
    cur = None
    for i, e in enumerate(evs):
        if e.period != cur:
            cur = e.period
            first: dict[str, dict[str, str]] = {t: {} for t in g.teams}
            for x in evs[i:]:
                if x.period != cur:
                    break
                if x.player and x.team in first:
                    first[x.team].setdefault(x.player, x.kind)
            for t in g.teams:
                cand = [p for p, k in first[t].items() if k != "in"]
                if len(cand) == 4 and t in ghost and ghost[t] not in cand:
                    cand.append(ghost[t])
                if len(cand) == 5:
                    on[t] = set(cand)
        if e.team not in on:
            continue
        gh = ghost.get(e.team)
        if e.kind not in ("in", "out"):
            if e.player is None and e.order in nullp and gh and (gh in on[e.team] or len(on[e.team]) < 5):
                e.player = gh
                on[e.team].add(gh)
                n_ghost += 1
            continue
        if e.player is None:
            if gh and ((e.kind == "out") == (gh in on[e.team])) and left_at.get(gh) != e.t:
                best = gh
            else:
                nxt = _next_kind(evs, i, e.period)
                if e.kind == "out":
                    best = _pick(sorted(on[e.team]), nxt, prefer_in=True)
                else:
                    cands = [p for p in roster.get(e.team, []) if p not in on[e.team]
                             and (g.box.get(p, {}).get("sec") or 0) > 0]
                    best = _pick(cands, nxt, prefer_in=False)
            if best:
                e.player = best
                fixed += 1
            else:
                left += 1
                continue
        if e.kind == "in":
            on[e.team].add(e.player)
        else:
            on[e.team].discard(e.player)
            left_at[e.player] = e.t
    return fixed, left, n_ghost


def _next_kind(evs: list[Event], i: int, period: int) -> dict[str, tuple[int, str]]:
    out: dict[str, tuple[int, str]] = {}
    for j in range(i + 1, len(evs)):
        x = evs[j]
        if x.period != period:
            break
        for p, k in ((x.player, x.kind), (x.assister, "act")):
            if p and p not in out:
                out[p] = (j, k)
    return out


def _pick(cands: list[str], nxt: dict, prefer_in: bool) -> str | None:
    """prefer_in=True (sale alguien): mejor quien vuelve a aparecer entrando; si no, quien no aparece;
    si no, quien tarda más en actuar. prefer_in=False (entra alguien): quien actúa antes sin entrar."""
    if prefer_in:
        ins = [p for p in cands if nxt.get(p, (0, ""))[1] == "in"]
        if len(ins) == 1:
            return ins[0]
        if ins:
            return min(ins, key=lambda p: nxt[p][0])
        absent = [p for p in cands if p not in nxt]
        if len(absent) == 1:
            return absent[0]
        if absent:
            return None
        acts = [p for p in cands if nxt[p][1] != "out"]
        return max(acts, key=lambda p: nxt[p][0]) if acts else None
    acts = [p for p in cands if p in nxt and nxt[p][1] != "in"]
    return min(acts, key=lambda p: nxt[p][0]) if acts else None
