"""LNB Betclic ÉLITE (Francia) — API de lnb.fr (api-prod.lnb.fr), la que usa su "stats centre".

La web obtiene un token anónimo en https://lnb.fr/api/token (lo recibe cualquier visitante sin
registrarse) y con él consulta:
  competition/getDivisionCompetitionByYear?year=Y&division_external_id=1
        competiciones del año: Betclic ÉLITE (temporada regular), Play-In, Playoffs, copas...
  altrstats/getPersonCriterion  (POST {competitionExternalId, year, format: "total", criterion})
        totales de temporada de TODOS los jugadores de la competición
  altrstats/getTeamsCriterion   (POST, mismo cuerpo) totales de equipo

Son agregados por competición: temporada regular, play-in y playoffs vienen por separado y el
total se obtiene sumándolos. La LNB no publica totales de los rivales; sólo se reconstruyen los
puntos encajados (puntos - más/menos), así que el contexto de rival queda parcial.
"""
from __future__ import annotations

from typing import Any

from ..http import FetchError, HttpClient
from ..normalize import complete_counting
from ..utils import to_float
from .base import AdapterError, BaseAdapter, NoDataYet, ParsedLeague

API = "https://api-prod.lnb.fr"
TOKEN_URL = "https://lnb.fr/api/token"
_MAP = {"s_games": "gp", "s_games_started": "gs", "s_minutes_average": "min", "s_points_average": "pts",
        "s_two_pointers_made_average": "fg2m", "s_two_pointers_attempted_average": "fg2a",
        "s_three_pointers_made_average": "fg3m", "s_three_pointers_attempted_average": "fg3a",
        "s_free_throws_made_average": "ftm", "s_free_throws_attempted_average": "fta",
        "s_rebounds_offensive_average": "oreb", "s_rebounds_defensive_average": "dreb",
        "s_rebounds_total_average": "reb", "s_assists_average": "ast", "s_blocks_average": "blk",
        "s_blocks_received": "blka", "s_steals_average": "stl", "s_turnovers_average": "tov",
        "s_fouls_total_average": "pf", "s_fouls_on_average": "pfd", "s_plus_minus_points": "plus_minus"}


def phase_of(comp: dict) -> str | None:
    name = (comp.get("competition_name") or "").lower()
    abbrev = (comp.get("competition_abbrev") or "").upper()
    if not abbrev.startswith("PROA"):
        return None  # copas, all-star...
    if "play" in name:
        return "playoffs"  # play-in y playoffs
    return "regular"


class LNBAdapter(BaseAdapter):
    name = "lnb"
    version = "1.0"

    def _headers(self, http: HttpClient) -> dict:
        if not getattr(self, "_token", None):
            self._token = http.get_json(TOKEN_URL)["token"]
        return {"Authorization": f"Bearer {self._token}", "device_type": "web", "language_code": "fr",
                "Origin": "https://lnb.fr", "Referer": "https://lnb.fr/"}

    def fetch(self, season: str, http: HttpClient, previous_payload: Any | None = None) -> Any:
        sc = self.season_cfg(season)
        year = sc["start_year"]
        comps = http.get_json(f"{API}/competition/getDivisionCompetitionByYear",
                              params={"year": year, "division_external_id": self.cfg.get("division", 1)},
                              headers=self._headers(http)).get("data") or []
        selected = [c for c in comps if phase_of(c)]
        if not selected:
            raise NoDataYet(f"LNB: sin competiciones Betclic ÉLITE para {season}")
        out: dict[str, Any] = {"year": year, "competitions": selected, "players": {}, "teams": {}}
        for c in selected:
            body = {"competitionExternalId": c["external_id"], "year": year, "format": "total",
                    "criterion": "sPoints"}
            for kind, ep in (("players", "getPersonCriterion"), ("teams", "getTeamsCriterion")):
                try:
                    out[kind][str(c["external_id"])] = http.post_json(f"{API}/altrstats/{ep}", json_body=body,
                                                                      headers=self._headers(http))
                except FetchError as exc:
                    self.soft_fail(f"{ep} {c['external_id']}: {exc}")
        if not any((d or {}).get("data") for d in out["players"].values()):
            raise NoDataYet(f"LNB {season}: sin estadísticas publicadas todavía")
        self._complete_rosters(http, out)
        return out

    def _complete_rosters(self, http: HttpClient, out: dict) -> None:
        """El ranking sólo incluye jugadores con un mínimo de partidos. Para no omitir a nadie se
        recorre la plantilla de cada equipo y se piden las fichas de los jugadores que faltan."""
        out["rosters"], out["extra_players"] = {}, {}
        team_ids = sorted({str((r.get("team") or {}).get("external_id"))
                           for d in out["teams"].values() for r in (d or {}).get("data") or []})
        first_comp = str(out["competitions"][0]["external_id"])
        for tid in team_ids:
            try:
                out["rosters"][tid] = http.get_json(f"{API}/teams/getRoster",
                                                    params={"team_external_id": tid, "competition_external_id": first_comp},
                                                    headers=self._headers(http))
            except FetchError as exc:
                self.soft_fail(f"getRoster {tid}: {exc}")
        for c in out["competitions"]:
            cid = str(c["external_id"])
            have = {(str((r.get("person") or {}).get("external_id")), str((r.get("team") or {}).get("external_id")))
                    for r in (out["players"].get(cid) or {}).get("data") or []}
            teams_in_comp = {str((r.get("team") or {}).get("external_id"))
                             for r in (out["teams"].get(cid) or {}).get("data") or []}
            for tid in teams_in_comp:
                for r in (out["rosters"].get(tid) or {}).get("data") or []:
                    pid = str((r.get("person") or {}).get("external_id"))
                    if (pid, tid) in have:
                        continue
                    body = {"person_external_id": int(pid), "competition_external_id": int(cid),
                            "team_external_id": int(tid), "format": "total"}
                    try:
                        doc = http.post_json(f"{API}/person/getPersonSeasonAll", json_body=body,
                                             headers=self._headers(http))
                    except FetchError as exc:
                        self.soft_fail(f"getPersonSeasonAll {pid}: {exc}")
                        continue
                    out["extra_players"][f"{cid}|{tid}|{pid}"] = doc

    @staticmethod
    def _bio(rosters: dict) -> dict[str, dict]:
        bio = {}
        for doc in (rosters or {}).values():
            for r in (doc or {}).get("data") or []:
                p, role = r.get("person") or {}, r.get("player_role") or {}
                bio[str(p.get("external_id"))] = {
                    "altura_cm": to_float(p.get("height")), "nacionalidad": p.get("nationality"),
                    "fecha_nacimiento": (p.get("dob") or "")[:10] or None, "edad": to_float(p.get("age")),
                    "posicion": role.get("playing_position"), "dorsal": role.get("shirt_number")}
        return bio

    @staticmethod
    def _extra_player(key: str, doc: Any, teams: dict) -> dict | None:
        cid, tid, pid = key.split("|")
        data = (doc or {}).get("data") or {}
        g = data.get("general") or {}
        if not to_float(g.get("games")):
            return None
        row = {"player_id": pid, "team_id": tid, "equipo": teams.get(tid), "gp": to_float(g.get("games")),
               "gs": to_float(g.get("first_five")), "min": to_float(g.get("minutes")), "pts": to_float(g.get("points")),
               "reb": to_float(g.get("rebounds")), "ast": to_float(g.get("assists")), "stl": to_float(g.get("steals")),
               "blk": to_float(g.get("blocks")), "_fuente_parcial": True}
        log = data.get("general_game_log") or []
        for k, c in (("two_p", "fg2m"), ("two_pa", "fg2a"), ("three_p", "fg3m"), ("three_pa", "fg3a"),
                     ("ft", "ftm"), ("fta", "fta"), ("or", "oreb"), ("dr", "dreb")):
            vals = [to_float(x.get(k)) for x in log if to_float(x.get(k)) is not None]
            if vals:
                row[c] = float(sum(vals))
        complete_counting(row)
        return row

    @staticmethod
    def _parse_comp(players_doc: Any, teams_doc: Any) -> ParsedLeague:
        players, teams = [], []
        for r in (players_doc or {}).get("data") or []:
            person, team = r.get("person") or {}, r.get("team") or {}
            row = {"player_id": str(person.get("external_id")), "team_id": str(team.get("external_id")),
                   "nombre": f"{person.get('first_name', '')} {person.get('family_name', '')}".strip(),
                   "equipo": team.get("team_name")}
            for k, c in _MAP.items():
                v = to_float(r.get(k))
                if v is not None:
                    row[c] = v
            complete_counting(row)
            players.append(row)
        for r in (teams_doc or {}).get("data") or []:
            team = r.get("team") or {}
            t = {"team_id": str(team.get("external_id")), "equipo": team.get("team_name")}
            for k, c in _MAP.items():
                v = to_float(r.get(k))
                if v is None or c in ("gs", "blka", "pfd"):
                    continue
                if c == "plus_minus":
                    continue
                t[f"team_{c}"] = v
            wl = str(r.get("s_w_l") or "")
            if "-" in wl:
                w, l_ = wl.split("-", 1)
                t["team_w"], t["team_l"] = to_float(w), to_float(l_)
            pm = to_float(r.get("s_plus_minus_points"))
            if pm is not None and t.get("team_pts") is not None:
                t["opp_pts"] = t["team_pts"] - pm  # puntos encajados = puntos - diferencial
            complete_counting(t, "team_")
            teams.append(t)
        return ParsedLeague(players=players, teams=teams)

    def parse(self, payload: Any, season: str) -> dict[str, ParsedLeague]:
        from ..phases import sum_phases
        by_phase: dict[str, list[ParsedLeague]] = {}
        bio = self._bio(payload.get("rosters"))
        extra_n = 0
        for c in payload.get("competitions") or []:
            key = str(c["external_id"])
            part = self._parse_comp(payload["players"].get(key), payload["teams"].get(key))
            team_names = {t["team_id"]: t.get("equipo") for t in part.teams}
            for k, doc in (payload.get("extra_players") or {}).items():
                if k.startswith(f"{key}|"):
                    row = self._extra_player(k, doc, team_names)
                    if row:
                        part.players.append(row)
                        extra_n += 1
            for r in part.players:
                for f, v in bio.get(r["player_id"], {}).items():
                    if v is not None and r.get(f) is None:
                        r[f] = v
                if not r.get("nombre"):
                    r["nombre"] = self._roster_name(payload.get("rosters"), r["player_id"])
            if part.players:
                by_phase.setdefault(phase_of(c), []).append(part)
        if not by_phase:
            raise AdapterError("LNB: el bruto no contiene estadísticas")
        out = {ph: (parts[0] if len(parts) == 1 else sum_phases(parts, ["play-in + playoffs"]))
               for ph, parts in by_phase.items()}
        for p in out.values():
            p.notes.append("LNB: la fuente no publica totales de los rivales (sólo puntos encajados)")
            p.notes.append(f"LNB: {extra_n} filas completadas desde fichas individuales (sin pérdidas, "
                           "faltas, tapones recibidos ni +/-, que la ficha no publica)")
        return out

    @staticmethod
    def _roster_name(rosters: dict, pid: str) -> str | None:
        for doc in (rosters or {}).values():
            for r in (doc or {}).get("data") or []:
                p = r.get("person") or {}
                if str(p.get("external_id")) == pid:
                    return f"{p.get('first_name', '')} {p.get('family_name', '')}".strip()
        return None
