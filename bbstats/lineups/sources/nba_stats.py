"""NBA y G League: jugada a jugada de la API de estadísticas (stats.gleague.nba.com/stats).

  Partidos:  leaguegamelog (PlayerOrTeam=T; una fila por equipo y partido)
  PBP:       playbyplayv3 (playbyplayv2 responde HTTP 500 en ambas ligas desde 2025: se usa v3 en las dos)
  Boxscore:  boxscoretraditionalv3 (titulares = `position` no vacío, minutos, +/-, nombres)
  Quinteto al empezar un periodo (sólo si el PBP no lo deja claro): boxscoretraditionalv3 con
             RangeType=2 en los primeros segundos del periodo (jugadores en pista en esa ventana).
  Oficiales: leaguedashlineups (GroupQuantity 5 y 2 × MeasureType Base y Advanced, una llamada por equipo
             porque el listado de liga corta en 2.000 filas) y teamplayeronoffdetails (Advanced).

`stats.nba.com` está bloqueado desde aquí; el host de la G League sirve también la NBA con LeagueID=00.

En v3 el asistente y el jugador que ENTRA en un cambio sólo aparecen en el texto ("SUB: Eason FOR Smith Jr.",
"(Dort 1 AST)"): se resuelven con los apellidos de la plantilla del partido (boxscore + nombres que usa el
propio PBP), desempatando por quién está en pista. Tiros libres: los puntos salen del cambio de marcador
(en la G League un tiro libre único vale 2 o 3).

Ids:
  * G League: ids de la API (equipo 1612709xxx, jugador personId), igual que los datos principales.
  * NBA: los datos principales vienen de Basketball-Reference → equipo = abreviatura BR (BRK, CHO, PHO) y
    jugador = id BR ("jamesle01") emparejado por nombre normalizado dentro del equipo; si no hay pareja se
    conserva el personId con prefijo "nba:".
Fases: las de `season_types` de la config (G League: regular, playoffs y copa = Showcase Cup, igual que el
adaptador principal, que la deja fuera de "regular" y la suma sólo al total). NBA: regular y playoffs
(sin play-in ni final de la NBA Cup, que Basketball-Reference tampoco cuenta).
"""
from __future__ import annotations

import csv
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ...http import FetchError
from ..model import Event, Game, clock_to_seconds, elapsed, period_length
from .base import Ctx, PBPSource

BASE = "https://stats.gleague.nba.com/stats"
GL_HEADERS = {"Accept": "application/json, text/plain, */*", "Referer": "https://gleague.nba.com/",
              "Origin": "https://gleague.nba.com"}
BOX_PARAMS = {"StartPeriod": "0", "EndPeriod": "14", "StartRange": "0", "EndRange": "0", "RangeType": "0"}
DASH_COMMON = {
    "Conference": "", "DateFrom": "", "DateTo": "", "Division": "", "GameSegment": "", "LastNGames": "0",
    "Location": "", "Month": "0", "OpponentTeamID": "0", "Outcome": "", "PORound": "0", "PaceAdjust": "N",
    "Period": "0", "PlusMinus": "N", "Rank": "N", "SeasonSegment": "", "ShotClockRange": "",
    "VsConference": "", "VsDivision": "", "PerMode": "Totals",
}
# tricode de la API -> abreviatura de Basketball-Reference
BREF_TEAM = {"BKN": "BRK", "CHA": "CHO", "PHX": "PHO"}
_AST = re.compile(r"\(([^()]+?) \d+ AST\)")
_SUB = re.compile(r"^SUB:\s*(.+?)\s+FOR\s+(.+?)\s*$")
_OWN = re.compile(r"^(?:MISS )?(.+?) (?:REBOUND|STEAL|BLOCK|[A-Z.]*FOUL|Free Throw|\d+'|3PT)")
_ABBR = re.compile(r"^([A-Za-z]{1,4})\.\s+(.+)$")
_SUFFIX = {"jr", "sr", "ii", "iii", "iv", "v"}


# --------------------------------------------------------------------------------------------- utilidades
def rows(doc: Any, index: int | str = 0) -> list[dict]:
    """resultSets (headers + rowSet) -> lista de dicts. `index` = posición o nombre del resultSet."""
    if not isinstance(doc, dict):
        return []
    rs = doc.get("resultSets", doc.get("resultSet"))
    if isinstance(rs, dict):
        rs = [rs]
    if not rs:
        return []
    if isinstance(index, str):
        rs = [r for r in rs if r.get("name") == index]
        index = 0
    if len(rs) <= index:
        return []
    headers = rs[index].get("headers") or []
    if headers and isinstance(headers[0], dict):
        headers = headers[-1].get("columnNames", [])
    return [dict(zip(headers, r)) for r in rs[index].get("rowSet") or []]


def norm_name(s: str | None, keep_suffix: bool = False) -> str:
    """'Nikola Jokić' -> 'nikola jokic'; quita puntos, guiones, apóstrofos y sufijos (Jr., III)."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[.'`’]", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(t for t in s.split() if keep_suffix or t not in _SUFFIX)


def _snake(k: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(k).lower()).strip("_")


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------------------------- fuente común
class _StatsV3PBP(PBPSource):
    version = "1.0"
    league_id = "20"
    default_types = {"regular": "Regular Season", "playoffs": "Playoffs"}

    # ---- configuración
    def _base(self, ctx: Ctx) -> str:
        return (ctx.cfg.get("pbp_base_url") or ctx.cfg.get("base_url") or BASE).rstrip("/")

    def _lid(self, ctx: Ctx) -> str:
        return str(ctx.cfg.get("pbp_league_id") or self.league_id)

    def _season(self, ctx: Ctx) -> str:
        return ((ctx.cfg.get("temporadas") or {}).get(ctx.season) or {}).get("season", ctx.season)

    def _types(self, ctx: Ctx) -> dict:
        return ctx.cfg.get("pbp_season_types") or self.default_types

    def _get(self, ctx: Ctx, endpoint: str, params: dict) -> Any:
        return ctx.http.get_json(f"{self._base(ctx)}/{endpoint}", params=params, headers=GL_HEADERS)

    # ---- ids (la G League los deja tal cual; la NBA los pasa a Basketball-Reference)
    def team_id(self, tid, tricode: str | None, ctx: Ctx) -> str:
        return str(tid)

    def player_map(self, box_players: list[dict], ctx: Ctx) -> dict[int, str]:
        return {p["personId"]: str(p["personId"]) for p in box_players}

    # ---- partidos
    def games(self, ctx: Ctx) -> list[dict]:
        out: dict[str, dict] = {}
        for phase, st in self._types(ctx).items():
            try:
                doc = self._get(ctx, "leaguegamelog", {
                    "Counter": "0", "DateFrom": "", "DateTo": "", "Direction": "ASC", "LeagueID": self._lid(ctx),
                    "PlayerOrTeam": "T", "Season": self._season(ctx), "SeasonType": st, "Sorter": "DATE"})
            except FetchError as exc:
                ctx.errors.append(f"leaguegamelog {st}: {exc}")
                continue
            for r in rows(doc):
                gid = str(r.get("GAME_ID"))
                g = out.setdefault(gid, {"game_id": gid, "phase": phase, "season_type": st,
                                         "date": r.get("GAME_DATE"), "final": True})
                tid = str(r.get("TEAM_ID"))
                if " vs. " in (r.get("MATCHUP") or ""):
                    g["home_team"] = tid
                else:
                    g["away_team"] = tid
                g["final"] = g["final"] and r.get("WL") not in (None, "")
        return sorted(out.values(), key=lambda g: (g.get("date") or "", g["game_id"]))

    # ---- descarga
    def fetch(self, ctx: Ctx, ref: dict) -> dict:
        gid = ref["game_id"]
        raw = {"pbp": self._get(ctx, "playbyplayv3", {"GameID": gid, "StartPeriod": "0", "EndPeriod": "14"}),
               "box": self._get(ctx, "boxscoretraditionalv3", {"GameID": gid, **BOX_PARAMS}),
               "period_box": {}}
        # quinteto al inicio de los periodos que el PBP no resuelve (1 petición por periodo dudoso; el v3 no
        # admite RangeType=2, el v2 sí: jugadores con minutos entre 0,5 y 5 s del periodo, en décimas de s)
        for per in self._unclear_periods(raw):
            t0 = int(elapsed(per, None, ctx.game_min, elapsed_in_period_s=0) * 10)
            try:
                raw["period_box"][str(per)] = self._get(ctx, "boxscoretraditionalv2", {
                    "GameID": gid, "StartPeriod": "0", "EndPeriod": "0", "RangeType": "2",
                    "StartRange": str(t0 + 5), "EndRange": str(t0 + 50)})
            except FetchError as exc:
                ctx.errors.append(f"boxscore periodo {per} {gid}: {exc}")
        return raw

    def _unclear_periods(self, raw: dict) -> list[int]:
        """Periodos (>1) en los que algún equipo no tiene exactamente 5 jugadores cuyo primer evento no sea
        una entrada (con nombres resueltos con la misma lógica que parse)."""
        box = (raw.get("box") or {}).get("boxScoreTraditional") or {}
        if not box:
            return []
        acts = ((raw.get("pbp") or {}).get("game") or {}).get("actions") or []
        res = _Resolver(box, acts)
        first: dict[int, dict] = defaultdict(lambda: defaultdict(dict))
        for a in acts:
            per, tid, pid = a.get("period") or 0, a.get("teamId"), a.get("personId")
            if a.get("actionType") == "Substitution":
                m = _SUB.match(a.get("description") or "")
                pin = res.resolve(tid, m.group(1), want_on=False) if m else None
                if pin:
                    first[per][tid].setdefault(pin, "in")
                if pid in res.roster.get(tid, {}):
                    first[per][tid].setdefault(pid, "out")
                continue
            if pid in res.roster.get(tid, {}):
                first[per][tid].setdefault(pid, "act")
                m = _AST.search(a.get("description") or "")
                if m and a.get("actionType") == "Made Shot":
                    pa = res.resolve(tid, m.group(1), want_on=True)
                    if pa:
                        first[per][tid].setdefault(pa, "act")
        out = []
        for per in sorted(first):
            if per <= 1:
                continue
            if any(sum(k != "in" for k in first[per][t].values()) != 5 for t in res.roster):
                out.append(per)
        return out

    # ---- interpretación
    def parse(self, raw: dict, ref: dict, ctx: Ctx) -> Game:
        box = (raw.get("box") or {}).get("boxScoreTraditional") or {}
        acts = ((raw.get("pbp") or {}).get("game") or {}).get("actions") or []
        ht, at = box.get("homeTeam") or {}, box.get("awayTeam") or {}
        tmap = {t.get("teamId"): self.team_id(t.get("teamId"), t.get("teamTricode"), ctx) for t in (ht, at)}
        all_players = [dict(p, teamId=t.get("teamId"), teamTricode=t.get("teamTricode")) for t in (ht, at) for p in t.get("players") or []]
        pmap = self.player_map(all_players, ctx)
        g = Game(game_id=ref["game_id"], phase=ref.get("phase", "regular"), teams=[tmap[ht.get("teamId")],
                 tmap[at.get("teamId")]], date=ref.get("date"),
                 coord_system="xLegacy/yLegacy de la API NBA (décimas de pie, aro en 0,0; y hacia el centro)")
        for t in (ht, at):
            tid = tmap[t.get("teamId")]
            g.team_names[tid] = f"{t.get('teamCity', '')} {t.get('teamName', '')}".strip()
            g.starters[tid] = []
            for p in t.get("players") or []:
                pid = pmap[p["personId"]]
                st = p.get("statistics") or {}
                g.players[pid] = {"nombre": f"{p.get('firstName', '')} {p.get('familyName', '')}".strip(),
                                  "team": tid, "person_id": p["personId"]}
                mins = st.get("minutes")
                sec = clock_to_seconds(mins) if mins else 0.0
                g.box[pid] = {"sec": sec, "pm": st.get("plusMinusPoints") if sec else None}
                if p.get("position") and len(g.starters[tid]) < 5:
                    g.starters[tid].append(pid)
        res = _Resolver(box, acts)
        unresolved: Counter = Counter()
        unresolved_txt: list[str] = []
        # Tiros libres: el +/- oficial los atribuye al quinteto que había al pitarse la falta (los cambios que
        # el PBP lista entre la falta y el tiro libre cuentan después). Se recolocan justo tras su falta.
        anchor: dict = {}
        ins_since: set = set()
        on: dict[int, set] = {t.get("teamId"): set() for t in (ht, at)}
        score = {"h": 0, "v": 0}
        evs: list[Event] = []
        seq, period, last_t, last_miss_team = 0, 0, 0.0, None
        # quintetos de inicio de periodo dados por el boxscore por rangos: se anotan como cambios explícitos
        forced = self._forced_starters(raw, res)

        def add(kind: str, tid, pid=None, **kw) -> None:
            nonlocal seq
            seq += 1
            e = Event(order=seq, period=period, t=last_t, kind=kind, team=tmap.get(tid),
                      player=pmap.get(pid) if pid is not None else None, **kw)
            if (kind == "ft" and anchor and anchor["per"] == period and anchor["t"] == last_t
                    and anchor["team"] != tid and pid not in ins_since):
                evs.insert(anchor["pos"], e)
                anchor["pos"] += 1
                return
            evs.append(e)
            if kind == "foul":
                anchor.clear()
                anchor.update(per=period, t=last_t, team=tid, pos=len(evs))
                ins_since.clear()
            elif kind == "in":
                ins_since.add(pid)

        for a in acts:
            per = int(a.get("period") or 0)
            if per != period:
                period = per
                last_t = elapsed(per, None, ctx.game_min, elapsed_in_period_s=0)
                for t in on:
                    on[t] = set()
                for tid, pids in (forced.get(per) or {}).items():
                    for pid in pids:  # "out"+"in" en el segundo 0: stints los toma como quinteto inicial
                        add("out", tid, pid)
                        add("in", tid, pid)
                        on[tid].add(pid)
                anchor.clear()
            rem = clock_to_seconds(a.get("clock"))
            if rem is not None and rem <= period_length(per, ctx.game_min) + 0.01:
                last_t = max(last_t, elapsed(per, rem, ctx.game_min))
            at_ = a.get("actionType") or ""
            desc = a.get("description") or ""
            tid, pid = a.get("teamId"), a.get("personId")
            if tid not in tmap:  # tiempos muertos de equipo, inicio/fin de periodo...
                tid = pid if pid in tmap else None
                pid = None
            elif pid not in res.roster.get(tid, {}):
                pid = None  # acción de equipo o de entrenador
            # marcador -> puntos reales de la acción
            pts = 0
            if a.get("scoreHome") not in (None, "") and a.get("scoreAway") not in (None, ""):
                sh, sv = _int(a["scoreHome"]) or 0, _int(a["scoreAway"]) or 0
                pts = (sh - score["h"]) + (sv - score["v"])
                score["h"], score["v"] = sh, sv
            if pid is not None and tid is not None and at_ != "Substitution":
                on[tid].add(pid)
            if at_ == "Substitution":
                m = _SUB.match(desc)
                pin = res.resolve(tid, m.group(1), on=on.get(tid), want_on=False) if m else None
                if pid is not None:
                    add("out", tid, pid)
                    on[tid].discard(pid)
                else:
                    unresolved["sale"] += 1
                if pin is not None:
                    add("in", tid, pin)
                    on[tid].add(pin)
                else:
                    unresolved["entra"] += 1
                    unresolved_txt.append(desc)
            elif at_ in ("Made Shot", "Missed Shot"):
                made = at_ == "Made Shot"
                v = 3 if (a.get("shotValue") == 3 or "3PT" in desc) else 2
                ast = None
                m = _AST.search(desc) if made else None
                if m:
                    ast = res.resolve(tid, m.group(1), on=on.get(tid), want_on=True, exclude=pid)
                    if ast is None:
                        unresolved["asistente"] += 1
                        unresolved_txt.append(m.group(1))
                    else:
                        on[tid].add(ast)
                x, y = a.get("xLegacy"), a.get("yLegacy")
                add("shot", tid, pid, value=v, made=made, pts=(pts or v) if made else 0,
                    assister=pmap.get(ast) if ast is not None else None, x=x, y=y)
                if not made:
                    last_miss_team = tid
            elif at_ == "Free Throw":
                made = not desc.upper().startswith("MISS")
                add("ft", tid, pid, value=1, made=made, pts=(pts or 1) if made else 0)
                if not made:
                    last_miss_team = tid
            elif at_ == "Rebound":
                if tid is None:
                    continue
                add("oreb" if tid == last_miss_team else "dreb", tid, pid)
            elif at_ == "Turnover":
                if tid is not None:
                    add("tov", tid, pid)
            elif at_ == "Foul":
                if tid is not None:
                    add("foul", tid, pid)
            elif at_ == "" and pid is not None:
                if "STEAL" in desc:
                    add("stl", tid, pid)
                elif "BLOCK" in desc:
                    add("blk", tid, pid)
        for i, e in enumerate(evs, 1):
            e.order = i
        g.events = evs
        g.notes += [f"{v} {k} sin identificar" for k, v in unresolved.items()]
        if unresolved_txt:
            g.notes.append("textos sin identificar: " + "; ".join(unresolved_txt[:5]))
        if forced:
            g.notes.append("quinteto de inicio de periodo del boxscore por rangos: "
                           + ",".join(str(p) for p in sorted(forced)))
        return g

    def _forced_starters(self, raw: dict, res: "_Resolver") -> dict[int, dict]:
        out: dict[int, dict] = {}
        for per, doc in (raw.get("period_box") or {}).items():
            sets: dict = defaultdict(list)
            for r in rows(doc, "PlayerStats"):
                tid, pid = r.get("TEAM_ID"), r.get("PLAYER_ID")
                if r.get("MIN") not in (None, "", "0:00") and pid in res.roster.get(tid, {}):
                    sets[tid].append(pid)
            if len(sets) == 2 and all(len(v) == 5 for v in sets.values()):
                out[int(per)] = dict(sets)
        return out

    # ---- tablas oficiales
    def _teams_in(self, ctx: Ctx, st: str) -> list[tuple[str, str]]:
        doc = self._get(ctx, "leaguegamelog", {
            "Counter": "0", "DateFrom": "", "DateTo": "", "Direction": "ASC", "LeagueID": self._lid(ctx),
            "PlayerOrTeam": "T", "Season": self._season(ctx), "SeasonType": st, "Sorter": "DATE"})
        return sorted({(str(r["TEAM_ID"]), r.get("TEAM_ABBREVIATION")) for r in rows(doc)})

    def official_team(self, ctx: Ctx, st: str, team: str) -> dict:
        base = {**DASH_COMMON, "LeagueID": self._lid(ctx), "Season": self._season(ctx), "SeasonType": st,
                "TeamID": team}
        out = {}
        for n in (5, 2):
            for m in ("Base", "Advanced"):
                key = f"l{n}_{m.lower()}"
                try:
                    out[key] = self._get(ctx, "leaguedashlineups", {**base, "GroupQuantity": str(n), "MeasureType": m})
                except FetchError as exc:
                    ctx.errors.append(f"leaguedashlineups {team} {n} {m}: {exc}")
        try:
            out["onoff"] = self._get(ctx, "teamplayeronoffdetails", {**base, "MeasureType": "Advanced"})
        except FetchError as exc:
            ctx.errors.append(f"teamplayeronoffdetails {team}: {exc}")
        return out

    def official(self, ctx: Ctx, teams: list[str] | None = None) -> dict[str, Any]:
        raw: dict[str, Any] = {"season": self._season(ctx), "tipos": {}}
        for phase, st in self._types(ctx).items():
            try:
                tlist = self._teams_in(ctx, st)
            except FetchError as exc:
                ctx.errors.append(f"leaguegamelog {st}: {exc}")
                continue
            if teams is not None:
                tlist = [t for t in tlist if t[0] in teams]
            if tlist:
                raw["tipos"][phase] = {"season_type": st,
                                       "teams": {tid: self.official_team(ctx, st, tid) for tid, _ in tlist}}
        return raw

    def official_player_id(self, person_id, team: str, ctx: Ctx, raw: dict) -> str:
        return str(person_id)

    def parse_official(self, raw: dict, ctx: Ctx) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {"quintetos": [], "parejas": [], "onoff": []}
        for phase, data in (raw.get("tipos") or {}).items():
            for _tid, docs in (data.get("teams") or {}).items():
                for n, name in ((5, "quintetos"), (2, "parejas")):
                    merged: dict[str, dict] = {}
                    for m in ("base", "advanced"):
                        for r in rows(docs.get(f"l{n}_{m}")):
                            gid = r.get("GROUP_ID") or ""
                            team = self.team_id(r.get("TEAM_ID"), r.get("TEAM_ABBREVIATION"), ctx)
                            row = merged.get(gid)
                            if row is None:
                                pids = [p for p in gid.strip("-").split("-") if p]
                                ids = sorted(self.official_player_id(int(p), team, ctx, raw) for p in pids)
                                row = merged[gid] = {"fase": phase, "team_id": team, "n_jugadores": n,
                                                     "jugadores": "|".join(ids), "nombres": r.get("GROUP_NAME"),
                                                     "group_id_fuente": gid}
                            for k, v in r.items():
                                if k in ("GROUP_SET", "GROUP_ID", "GROUP_NAME", "TEAM_ID", "TEAM_ABBREVIATION") \
                                        or k.endswith("_RANK"):
                                    continue
                                row.setdefault(_snake(k), v)
                    out[name] += list(merged.values())
                players: dict[str, dict] = {}
                for status in ("On", "Off"):
                    rs = "PlayersOnCourtTeamPlayerOnOffDetails" if status == "On" else "PlayersOffCourtTeamPlayerOnOffDetails"
                    for r in rows(docs.get("onoff"), rs):
                        team = self.team_id(r.get("TEAM_ID"), r.get("TEAM_ABBREVIATION"), ctx)
                        pid = self.official_player_id(r.get("VS_PLAYER_ID"), team, ctx, raw)
                        row = players.setdefault(pid, {"fase": phase, "team_id": team, "player_id": pid,
                                                       "nombre": r.get("VS_PLAYER_NAME"),
                                                       "person_id_fuente": r.get("VS_PLAYER_ID")})
                        for k, v in r.items():
                            if k in ("GROUP_SET", "TEAM_ID", "TEAM_ABBREVIATION", "TEAM_NAME", "VS_PLAYER_ID",
                                     "VS_PLAYER_NAME", "COURT_STATUS") or k.endswith("_RANK"):
                                continue
                            row[f"{status.lower()}_{_snake(k)}"] = v
                out["onoff"] += list(players.values())
        return out


class _Resolver:
    """Nombres del texto del PBP v3 -> personId del equipo (plantilla del boxscore + nombres del propio PBP)."""

    def __init__(self, box: dict, acts: list[dict]) -> None:
        self.roster: dict[int, dict[int, dict]] = {}
        self.keys: dict[int, dict[str, set]] = {}
        mins: dict[int, float] = {}
        for t in (box.get("homeTeam") or {}, box.get("awayTeam") or {}):
            tid = t.get("teamId")
            self.roster[tid] = {p["personId"]: p for p in t.get("players") or []}
            k = self.keys[tid] = defaultdict(set)
            for p in t.get("players") or []:
                pid = p["personId"]
                mins[pid] = clock_to_seconds((p.get("statistics") or {}).get("minutes")) or 0.0
                fam, first = p.get("familyName") or "", p.get("firstName") or ""
                for s in (fam, p.get("nameI"), f"{first} {fam}", f"{first[:1]}. {fam}"):
                    if s and s.strip(". "):
                        k[norm_name(s)].add(pid)
                        k["=" + norm_name(s, True)].add(pid)
        for a in acts:  # el nombre que usa el PBP para cada jugador (campos y texto de sus propias acciones)
            tid, pid = a.get("teamId"), a.get("personId")
            if tid in self.keys and pid in self.roster[tid]:
                names = [a.get("playerName"), a.get("playerNameI")]
                desc = a.get("description") or ""
                m = _SUB.match(desc) if a.get("actionType") == "Substitution" else _OWN.match(desc)
                if m:  # "SUB: X FOR <él>" / "<él> REBOUND ..." (p.ej. Kanter en el texto, Freedom en el campo)
                    names.append(m.group(2) if a.get("actionType") == "Substitution" else m.group(1))
                for s in names:
                    if s:
                        self.keys[tid][norm_name(s)].add(pid)
                        self.keys[tid]["=" + norm_name(s, True)].add(pid)
        self.mins = mins

    def candidates(self, tid, text: str) -> set:
        k = self.keys.get(tid)
        if not k or not text:
            return set()
        m = _ABBR.match(text.strip())
        if m:  # "Jal. Williams" / "K. Williams": inicial(es) del nombre + apellido
            pre, fam = norm_name(m.group(1)), norm_name(m.group(2))
            c = {pid for pid, p in self.roster.get(tid, {}).items()
                 if norm_name(p.get("familyName")) == fam and norm_name(p.get("firstName")).startswith(pre)}
            if c:
                return c
        cands = set(k.get("=" + norm_name(text, True), ()))  # exacto: "Williams" ≠ "Williams III"
        if len(cands) == 1:
            return cands
        n = norm_name(text)
        cands = cands or set(k.get(n, ()))
        if not cands:  # "Jones Garcia" vs "Jones-Garcia", o sólo una parte del apellido
            cands = {pid for key, ps in k.items() if key[:1] != "=" for pid in ps
                     if key.endswith(" " + n) or n.endswith(" " + key)}
        return cands

    def resolve(self, tid, text: str, on: set | None = None, want_on: bool = True, exclude=None) -> int | None:
        cands = self.candidates(tid, text)
        cands.discard(exclude)
        if len(cands) <= 1:
            return next(iter(cands), None)
        if on is not None:
            pref = [p for p in cands if (p in on) == want_on]
            if len(pref) == 1:
                return pref[0]
            if pref:
                cands = set(pref)
        return max(cands, key=lambda p: self.mins.get(p, 0.0))  # el que más jugó


# --------------------------------------------------------------------------------------------- G League
class GLeaguePBP(_StatsV3PBP):
    name = "gleague_stats"
    league_id = "20"
    default_types = {"regular": "Regular Season", "playoffs": "Playoffs", "copa": "Showcase"}

    def _lid(self, ctx: Ctx) -> str:
        return str(ctx.cfg.get("pbp_league_id") or ctx.cfg.get("league_id") or self.league_id)

    def _types(self, ctx: Ctx) -> dict:
        return ctx.cfg.get("pbp_season_types") or ctx.cfg.get("season_types") or self.default_types


# --------------------------------------------------------------------------------------------- NBA
class NbaPBP(_StatsV3PBP):
    name = "nba_stats"
    league_id = "00"
    default_types = {"regular": "Regular Season", "playoffs": "Playoffs"}

    def _base(self, ctx: Ctx) -> str:  # la config NBA apunta a Basketball-Reference (adaptador principal)
        return (ctx.cfg.get("pbp_base_url") or BASE).rstrip("/")

    def _lid(self, ctx: Ctx) -> str:
        return str(ctx.cfg.get("pbp_league_id") or self.league_id)

    def team_id(self, tid, tricode: str | None, ctx: Ctx) -> str:
        return BREF_TEAM.get(tricode or "", tricode or str(tid))

    # ---- plantillas de Basketball-Reference (datos principales)
    def bref_roster(self, ctx: Ctx) -> list[dict]:
        """[{player_id, team_id, nombre}] de los datos principales: bruto de BR en ctx.main_payload o, si no
        está, el CSV procesado de la temporada. Se guarda en caché por temporada."""
        cache = self.__dict__.setdefault("_roster_cache", {})
        key = (ctx.season, id(ctx.main_payload))
        if key in cache:
            return cache[key]
        roster: list[dict] = []
        pages = (ctx.main_payload or {}).get("pages") if isinstance(ctx.main_payload, dict) else None
        if pages and pages.get("totals"):
            from ...adapters.bref_nba import BRefNBAAdapter, _soup
            ad = BRefNBAAdapter("nba", ctx.cfg)
            soups = {"totals": _soup(pages["totals"])}
            for suffix in ("", "_post"):
                roster += [{"player_id": r["player_id"], "team_id": r["team_id"], "nombre": r.get("nombre")}
                           for r in ad._players(soups, suffix)]
        else:
            root = Path(ctx.cfg.get("pbp_processed_dir") or Path(__file__).resolve().parents[3] / "data" / "processed")
            f = root / ctx.season / "ligas" / "nba.csv"
            if f.exists():
                with f.open(encoding="utf-8") as fh:
                    roster = [{"player_id": r["player_id"], "team_id": r["team_id"], "nombre": r["nombre"]}
                              for r in csv.DictReader(fh)]
        cache[key] = roster
        return roster

    def _index(self, ctx: Ctx) -> dict:
        cache = self.__dict__.setdefault("_index_cache", {})
        key = (ctx.season, id(ctx.main_payload))
        if key not in cache:
            by_team: dict[tuple, set] = defaultdict(set)
            by_name: dict[str, set] = defaultdict(set)
            for r in self.bref_roster(ctx):
                n = norm_name(r["nombre"])
                by_team[(r["team_id"], n)].add(r["player_id"])
                by_name[n].add(r["player_id"])
                parts = n.split()
                if parts:
                    by_team[(r["team_id"], "~" + parts[-1])].add(r["player_id"])
                    by_team[(r["team_id"], "~" + parts[0][:1] + " " + parts[-1])].add(r["player_id"])
                    by_name["~" + parts[0][:1] + " " + parts[-1]].add(r["player_id"])
            cache[key] = (by_team, by_name)
        return cache[key]

    def match_bref(self, first: str, family: str, team: str, ctx: Ctx) -> str | None:
        by_team, by_name = self._index(ctx)
        n = norm_name(f"{first} {family}")
        parts = n.split()
        if not parts:
            return None
        ini = "~" + parts[0][:1] + " " + norm_name(family).split()[-1] if norm_name(family) else None
        fam_last = "~" + (norm_name(family).split() or [""])[-1]
        for cands in (by_team.get((team, n)), by_name.get(n), by_team.get((team, ini)),
                      by_team.get((team, fam_last)), by_name.get(ini) if ini else None):
            if cands and len(cands) == 1:
                return next(iter(cands))
        return None

    def parse(self, raw: dict, ref: dict, ctx: Ctx) -> Game:
        g = super().parse(raw, ref, ctx)
        n = len(g.players)
        ok = sum(not p.startswith("nba:") for p in g.players)
        g.notes.append(f"ids BR emparejados {ok}/{n}")
        miss = [p["nombre"] for k, p in g.players.items() if k.startswith("nba:") and (g.box.get(k) or {}).get("sec")]
        if miss:
            g.notes.append("sin id BR (con minutos): " + ", ".join(miss))
        return g

    def player_map(self, box_players: list[dict], ctx: Ctx) -> dict[int, str]:
        out = {}
        for p in box_players:
            team = self.team_id(p.get("teamId"), p.get("teamTricode"), ctx)
            bid = self.match_bref(p.get("firstName") or "", p.get("familyName") or "", team, ctx)
            out[p["personId"]] = bid or f"nba:{p['personId']}"
        return out

    # ---- tablas oficiales: personId -> id BR con el índice de jugadores de la temporada
    def official(self, ctx: Ctx, teams: list[str] | None = None) -> dict[str, Any]:
        raw = super().official(ctx, teams)
        try:
            raw["playerindex"] = self._get(ctx, "playerindex", {
                "LeagueID": self._lid(ctx), "Season": self._season(ctx), "Historical": "1", "Active": "",
                "AllStar": "", "College": "", "Country": "", "DraftPick": "", "DraftRound": "", "DraftYear": "",
                "Height": "", "TeamID": "0", "Weight": "", "SeasonType": "Regular Season"})
        except FetchError as exc:
            ctx.errors.append(f"playerindex: {exc}")
        return raw

    def official_player_id(self, person_id, team: str, ctx: Ctx, raw: dict) -> str:
        cache = self.__dict__.setdefault("_names_cache", {})
        names = cache.get(id(raw))
        if names is None:
            names = cache[id(raw)] = {}
            for r in rows(raw.get("playerindex")):
                names[_int(r.get("PERSON_ID"))] = (r.get("PLAYER_FIRST_NAME") or "", r.get("PLAYER_LAST_NAME") or "")
            for data in (raw.get("tipos") or {}).values():  # respaldo: "Apellido, Nombre" del on/off
                for docs in (data.get("teams") or {}).values():
                    for r in rows(docs.get("onoff"), "PlayersOnCourtTeamPlayerOnOffDetails"):
                        last, _, first = (r.get("VS_PLAYER_NAME") or "").partition(", ")
                        names.setdefault(_int(r.get("VS_PLAYER_ID")), (first, last))
        pid = _int(person_id)
        first, last = names.get(pid, ("", ""))
        bid = self.match_bref(first, last, team, ctx) if (first or last) else None
        return bid or f"nba:{person_id}"
