"""LNB Betclic ÉLITE (Francia): jugada a jugada del widget Sportradar/Atrium que incrusta lnb.fr.

  PBP:      https://embed-api.eui.connect.sportradar.com/v1/embed/12/fixture_detail?fixtureId=<uuid>&sub=pbp
            periodData[].events[] (en orden): clock ("PT9M2S" restante), eventType/eventSubType, personId,
            entityId, success, x/y (0–100), scores. Los cambios llegan ya separados (in / out) y la
            asistencia es un evento propio tras el tiro (se enlaza con link_assists_by_adjacency).
  Boxscore: ...&sub=statistics  (starter, minutes "PT17M17S", plusMinus por jugador)
Sin token ni cabeceras. 2 peticiones por partido.

Partidos (uuid de Sportradar): por cada competición del bruto principal (Betclic ÉLITE = regular;
Play-In / Playoffs / "Phase Finale" = playoffs, con adapters.lnb.phase_of):
  1) …/embed/12/fixtures?seasonId=<competition.season_id>  (1 petición; toda la competición)
  2) si devuelve menos partidos terminados de los que dicen las estadísticas de equipo del bruto
     principal (Σ partidos jugados / 2) — p.ej. 2021-22 —, api-prod.lnb.fr con el token anónimo de lnb.fr:
     competition/getCompetitionRounds + match/getMatchesByCompetitionAndRound (POST) por jornada; el
     campo `match_id` es el uuid del fixture.

Ids: el PBP usa uuids de Sportradar; los datos principales, los `external_id` numéricos de lnb.fr.
  * jugador: `person.person_id` (uuid) -> `person.external_id` en los rankings del bruto principal
    (altrstats/getPersonCriterion). Si un jugador no está en el ranking (pocos partidos), se busca por
    nombre (y si no, por dorsal) en la plantilla del equipo (teams/getRoster). Si tampoco, se deja el uuid.
  * equipo: equipo mayoritario (en los datos principales) de sus jugadores ya traducidos; si no, nombre.
2020-21: el PBP está vacío (sólo boxscore) -> has_lineups=False, has_assists=False.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

from ...adapters.lnb import API, TOKEN_URL, phase_of
from ...http import FetchError
from ..model import Event, Game, clock_to_seconds, elapsed, link_assists_by_adjacency
from .base import Ctx, PBPSource

EMBED = "https://embed-api.eui.connect.sportradar.com/v1/embed/12"
SIMPLE = {"turnover": "tov", "steal": "stl", "block": "blk"}
NO_PLAYER_FOULS = {"coachTechnical", "benchTechnical", "coachDisqualifying", "benchDisqualifying",
                   "adminTechnical"}


def _norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _num(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


class LnbPBP(PBPSource):
    name = "lnb_atrium"
    version = "1.0"

    # ------------------------------------------------------------------ partidos
    def _headers(self, ctx: Ctx) -> dict:
        if not getattr(self, "_token", None):
            self._token = ctx.http.get_json(TOKEN_URL)["token"]
        return {"Authorization": f"Bearer {self._token}", "device_type": "web", "language_code": "fr",
                "Origin": "https://lnb.fr", "Referer": "https://lnb.fr/"}

    @staticmethod
    def _expected(payload: dict, comp_ext: str) -> int:
        rows = ((payload.get("teams") or {}).get(comp_ext) or {}).get("data") or []
        return int(sum(_num(r.get("s_games")) or 0 for r in rows) // 2)

    def games(self, ctx: Ctx) -> list[dict]:
        payload = ctx.main_payload if isinstance(ctx.main_payload, dict) else {}
        out: dict[str, dict] = {}
        for comp in payload.get("competitions") or []:
            phase = phase_of(comp)
            if not phase:
                continue
            cext = str(comp.get("external_id"))
            refs = self._from_embed(ctx, comp, phase)
            need = self._expected(payload, cext)
            if sum(r["final"] for r in refs) < need:
                try:
                    refs = self._from_lnb(ctx, comp, phase) or refs
                except FetchError as exc:
                    ctx.errors.append(f"LNB jornadas {cext}: {exc}")
            for r in refs:
                out.setdefault(r["game_id"], r)
        return sorted(out.values(), key=lambda r: (r.get("date") or "", r["game_id"]))

    def _from_embed(self, ctx: Ctx, comp: dict, phase: str) -> list[dict]:
        if not comp.get("season_id"):
            return []
        try:
            doc = ctx.http.get_json(f"{EMBED}/fixtures", params={"seasonId": comp["season_id"]})
        except FetchError as exc:
            ctx.errors.append(f"LNB fixtures {comp.get('external_id')}: {exc}")
            return []
        out = []
        for f in ((doc or {}).get("data") or {}).get("fixtures") or []:
            st = f.get("status") or {}
            st = st.get("value") if isinstance(st, dict) else st
            if not f.get("fixtureId"):
                continue
            out.append({"game_id": f["fixtureId"], "phase": phase, "final": st == "CONFIRMED",
                        "date": f.get("startTimeUTC") or f.get("startTimeLocal"),
                        "competition": str(comp.get("external_id")), "name": f.get("name")})
        return out

    def _from_lnb(self, ctx: Ctx, comp: dict, phase: str) -> list[dict]:
        cext = comp.get("external_id")
        rounds = ctx.http.get_json(f"{API}/competition/getCompetitionRounds",
                                   params={"competition_external_id": cext}, headers=self._headers(ctx))
        out = []
        for rd in (rounds or {}).get("data") or []:
            body = {"competition_external_id": cext, "round_number": rd.get("round_number")}
            doc = ctx.http.post_json(f"{API}/match/getMatchesByCompetitionAndRound", json_body=body,
                                     headers=self._headers(ctx))
            for m in ((doc or {}).get("data") or {}).get("matches") or []:
                if not m.get("match_id"):
                    continue
                out.append({"game_id": m["match_id"], "phase": phase,
                            "final": m.get("match_status") == "COMPLETE", "date": m.get("match_time_utc"),
                            "competition": str(cext), "match_external_id": m.get("external_id"),
                            "name": m.get("match_name")})
        return out

    # ------------------------------------------------------------------ descarga
    def fetch(self, ctx: Ctx, ref: dict) -> dict:
        raw = {}
        for sub in ("pbp", "statistics"):
            doc = ctx.http.get_json(f"{EMBED}/fixture_detail", params={"fixtureId": ref["game_id"], "sub": sub})
            raw[sub] = (doc or {}).get("data") or {}
        return raw

    # ------------------------------------------------------------------ ids
    @staticmethod
    def _id_maps(payload) -> tuple[dict, dict, dict, dict]:
        """(uuid -> external_id, external_id -> team ext, team ext -> nombre, team ext -> plantilla)."""
        payload = payload if isinstance(payload, dict) else {}
        uuid2ext, p_team, t_name, roster = {}, {}, {}, {}
        for doc in (payload.get("players") or {}).values():
            for r in (doc or {}).get("data") or []:
                per, tm = r.get("person") or {}, r.get("team") or {}
                ext, text = per.get("external_id"), tm.get("external_id")
                if ext is None:
                    continue
                if per.get("person_id"):
                    uuid2ext[per["person_id"]] = str(ext)
                if text is not None:
                    p_team.setdefault(str(ext), Counter())[str(text)] += 1
                    t_name[str(text)] = tm.get("team_name")
        for doc in (payload.get("teams") or {}).values():
            for r in (doc or {}).get("data") or []:
                tm = r.get("team") or {}
                if tm.get("external_id") is not None:
                    t_name[str(tm["external_id"])] = tm.get("team_name")
        for tid, doc in (payload.get("rosters") or {}).items():
            for r in (doc or {}).get("data") or []:
                per, role = r.get("person") or {}, r.get("player_role") or {}
                if per.get("external_id") is None:
                    continue
                roster.setdefault(str(tid), []).append({
                    "id": str(per["external_id"]), "first": per.get("first_name"), "last": per.get("family_name"),
                    "bib": str(role.get("shirt_number") or "").strip()})
        return uuid2ext, p_team, t_name, roster

    # ------------------------------------------------------------------ interpretación
    def parse(self, raw: dict, ref: dict, ctx: Ctx) -> Game:
        pbp, sts = raw.get("pbp") or {}, raw.get("statistics") or {}
        fx = sts.get("fixture") or pbp.get("fixture") or {}
        comps = sorted(fx.get("competitors") or [], key=lambda c: not c.get("isHome"))
        uuids = [c.get("entityId") for c in comps if c.get("entityId")]
        uuid2ext, p_team, t_name, roster = self._id_maps(ctx.main_payload)
        base = ((sts.get("statistics") or {}).get("data") or {}).get("base") or {}

        rows_by_team: dict[str, list[dict]] = {}
        for side in ("home", "away"):
            for grp in (base.get(side) or {}).get("persons") or []:
                for r in grp.get("rows") or []:
                    if r.get("personId") and r.get("entityId"):
                        rows_by_team.setdefault(r["entityId"], []).append(r)

        # equipo: mayoría de sus jugadores ya traducidos; si no, nombre
        tmap: dict[str, str] = {}
        name_of = {c.get("entityId"): c.get("name") for c in comps}
        for tu in uuids:
            votes = Counter()
            for r in rows_by_team.get(tu, []):
                ext = uuid2ext.get(r["personId"])
                if ext and ext in p_team:
                    votes.update(p_team[ext])
            if votes:
                tmap[tu] = votes.most_common(1)[0][0]
            else:
                hits = [t for t, n in t_name.items() if _norm(n) == _norm(name_of.get(tu))]
                tmap[tu] = hits[0] if len(hits) == 1 else tu
        teams = [tmap[u] for u in uuids]
        g = Game(game_id=ref["game_id"], phase=ref.get("phase", "regular"), teams=teams,
                 date=ref.get("date") or fx.get("startTimeUTC"),
                 coord_system="Sportradar x/y 0–100 (unidades de la fuente)")
        g.team_names = {tmap[u]: name_of.get(u) for u in uuids}

        # jugadores
        pmap: dict[str, str] = {}
        unmapped = 0
        for tu, rows in rows_by_team.items():
            text = tmap.get(tu, tu)
            ros = roster.get(text, [])
            for r in rows:
                pu = r["personId"]
                pid = uuid2ext.get(pu) or self._by_name(r, ros)
                if not pid:
                    pid, unmapped = pu, unmapped + 1
                pmap[pu] = pid
                g.players[pid] = {"nombre": (r.get("personName") or "").strip(), "team": text}
                s = r.get("statistics") or {}
                mins = s.get("minutes")
                sec = clock_to_seconds(mins) if isinstance(mins, str) else _num(mins)
                if sec is None and r.get("participated") is False:
                    sec = 0.0
                g.box[pid] = {"sec": sec, "pm": _num(s.get("plusMinus"))}
                if r.get("starter"):
                    g.starters.setdefault(text, []).append(pid)
        for t in list(g.starters):
            if len(g.starters[t]) != 5:
                g.starters[t] = []
        if unmapped:
            g.notes.append(f"{unmapped} jugadores sin id de lnb.fr (se usa el uuid de Sportradar)")

        # eventos (orden de la lista; el reloj nunca retrocede)
        evs: list[Event] = []
        markers: list[tuple[int, str, str]] = []
        seq, last_t = 0, 0.0
        for pdat in pbp.get("periodData") or []:
            for e in pdat.get("events") or []:
                seq += 1
                try:
                    per = int(e.get("periodId") or pdat.get("periodId") or 0)
                except (TypeError, ValueError):
                    continue
                if per <= 0:
                    continue
                rem = clock_to_seconds(e.get("clock"))
                t = elapsed(per, rem, ctx.game_min) if rem is not None else last_t
                t = max(t, last_t)
                last_t = t
                typ, sub = e.get("eventType"), e.get("eventSubType")
                tm = tmap.get(e.get("entityId"), e.get("entityId"))
                pu = e.get("personId")
                pid = pmap.get(pu, uuid2ext.get(pu, pu)) if pu else None
                kw = {"order": seq, "period": per, "t": t, "team": tm, "player": pid}
                ok = e.get("success") is True
                x, y = _num(e.get("x")), _num(e.get("y"))
                if typ in ("2pt", "3pt"):
                    v = 2 if typ == "2pt" else 3
                    evs.append(Event(kind="shot", value=v, made=ok, pts=v if ok else 0, x=x, y=y, **kw))
                elif typ == "freeThrow":
                    evs.append(Event(kind="ft", value=1, made=ok, pts=1 if ok else 0, **kw))
                elif typ == "assist":
                    if pid and tm:
                        markers.append((seq, tm, pid))
                elif typ == "substitution" and sub in ("in", "out") and pid:
                    evs.append(Event(kind=sub, **kw))
                elif typ == "rebound":
                    evs.append(Event(kind="oreb" if sub == "offensive" else "dreb", **kw))
                elif typ in SIMPLE:
                    evs.append(Event(kind=SIMPLE[typ], **kw))
                elif typ == "foul":
                    if sub == "drawn":
                        if pid:
                            evs.append(Event(kind="foul_drawn", **kw))
                    elif pid and sub not in NO_PLAYER_FOULS:
                        evs.append(Event(kind="foul", **kw))
        g.events = evs
        left = link_assists_by_adjacency(evs, markers)
        if left:
            g.notes.append(f"{left} asistencias sin enlazar")
        g.has_assists = bool(markers)
        g.has_shots = any(e.x is not None for e in evs if e.kind == "shot")
        if not any(e.kind in ("in", "out") for e in evs):
            g.has_lineups = False
            g.notes.append("sin jugada a jugada (sólo boxscore)" if not evs else "sin cambios: sin quintetos")
        return g

    @staticmethod
    def _by_name(row: dict, ros: list[dict]) -> str | None:
        """Jugador fuera de los rankings: nombre completo, apellido único o dorsal único en la plantilla."""
        if not ros:
            return None
        full = _norm(row.get("personName"))
        hits = [p["id"] for p in ros if _norm(f"{p['first'] or ''} {p['last'] or ''}") == full]
        if len(hits) == 1:
            return hits[0]
        toks = set(full.split())
        hits = [p["id"] for p in ros if p["last"] and set(_norm(p["last"]).split()) <= toks]
        if len(hits) == 1:
            return hits[0]
        bib = str(row.get("bib") or "").strip()
        hits = [p["id"] for p in ros if bib and p["bib"] == bib]
        return hits[0] if len(hits) == 1 else None
