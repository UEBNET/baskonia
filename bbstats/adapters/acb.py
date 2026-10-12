"""Liga Endesa (ACB) — API de datos de acb.com (api2.acb.com).

La web oficial (acb.com / live.acb.com) carga sus datos desde api2.acb.com con una clave de
cliente pública incluida en su propio código (cabecera X-APIKEY). Endpoints usados:

  /api/seasondata/Calendar/season-calendar?competitionId=1[&editionId=N]
        temporadas disponibles (editionId por año), jornadas y partidos. Las jornadas con
        `subphaseId` pertenecen a los playoffs; sin subfase = temporada regular.
  /api/matchdata/Result/boxscores?matchId=N
        boxscore completo: jugadores (id, titular, minutos, tiros, rebotes, asistencias, robos,
        pérdidas, tapones a favor/en contra, mates, faltas cometidas/recibidas, +/-, valoración),
        rebotes de equipo y totales.

Los partidos finalizados del JSON bruto anterior se reutilizan (no se vuelven a pedir).
"""
from __future__ import annotations

from typing import Any

from ..http import FetchError, HttpClient
from ..utils import parse_minutes
from .base import AdapterError, BaseAdapter, NoDataYet, ParsedLeague
from .boxscore import aggregate_by_phase

API = "https://api2.acb.com"
PUBLIC_KEY = "0dd94928-6f57-4c08-a3bd-b1b2f092976e"

_STATS = {"points": "pts", "twoPointersMade": "fg2m", "twoPointersAttempted": "fg2a",
          "threePointersMade": "fg3m", "threePointersAttempted": "fg3a", "freeThrowsMade": "ftm",
          "freeThrowsAttempted": "fta", "offRebounds": "oreb", "defRebounds": "dreb", "totalRebounds": "reb",
          "assists": "ast", "steals": "stl", "turnovers": "tov", "blocks": "blk", "receivedBlocks": "blka",
          "dunks": "dunks", "personalFouls": "pf", "foulsDrawn": "pfd", "plusMinus": "plus_minus", "rating": "pir"}


def _stats(rec: dict) -> dict:
    return {c: float(rec[k]) for k, c in _STATS.items() if rec.get(k) is not None}


def parse_boxscore(match_id: str, doc: dict, phase: str) -> dict:
    sides = []
    for tb in doc.get("teamBoxscores") or []:
        team = tb.get("team") or {}
        q0 = next((p for p in tb.get("statsByPeriods") or [] if p.get("quarter") == 0), None)
        if q0 is None:
            continue
        st = q0.get("stats") or {}
        players = []
        for pl in st.get("players") or []:
            info = pl.get("player") or {}
            line = {"player_id": str(info.get("id")),
                    "name": info.get("nickname") or f"{info.get('firstName', '')} {info.get('lastName', '')}".strip(),
                    "dorsal": info.get("shirtNumber"), "posicion": info.get("gameRole"),
                    "starter": bool(pl.get("isStarted")), "min": parse_minutes(pl.get("playTime"))}
            line.update(_stats(pl))
            players.append(line)
        totals = _stats(st.get("total") or {})
        totals.pop("plus_minus", None)
        sides.append({"team_id": str(team.get("clubId") or team.get("id")), "name": team.get("fullName"),
                      "code": team.get("abbreviatedName"), "totals": totals, "players": players})
    return {"game_id": str(match_id), "phase": phase, "final": bool(doc.get("matchFinished")), "teams": sides}


class ACBAdapter(BaseAdapter):
    name = "acb"
    version = "2.0"

    def _get(self, http: HttpClient, path: str, params: dict) -> Any:
        headers = {"X-APIKEY": self.cfg.get("api_key", PUBLIC_KEY), "Origin": "https://acb.com",
                   "Referer": "https://acb.com/", "Accept": "application/json"}
        return http.get_json(f"{self.cfg.get('base_url', API)}{path}", params=params, headers=headers)

    def fetch(self, season: str, http: HttpClient, previous_payload: Any | None = None) -> Any:
        sc = self.season_cfg(season)
        comp = int(self.cfg.get("competicion_id", 1))
        cal_path = "/api/seasondata/Calendar/season-calendar"
        edition = sc.get("edition_id")
        if edition is None:
            base_cal = self._get(http, cal_path, {"competitionId": comp})
            seasons = (base_cal.get("availableFilters") or {}).get("seasons") or []
            match = [s for s in seasons if s.get("seasonStartYear") == sc["start_year"]]
            if not match:
                raise NoDataYet(f"ACB: temporada {season} no disponible en el calendario")
            edition = match[0]["id"]
        calendar = self._get(http, cal_path, {"competitionId": comp, "editionId": edition})
        prev = (previous_payload or {}).get("boxscores", {}) if isinstance(previous_payload, dict) else {}
        boxscores: dict[str, Any] = {}
        reused = 0
        for rnd in calendar.get("rounds") or []:
            for m in rnd.get("matches") or []:
                if m.get("matchStatus") != "FINALIZED":
                    continue
                mid = str(m["id"])
                if mid in prev and (prev[mid] or {}).get("matchFinished"):
                    boxscores[mid] = prev[mid]
                    reused += 1
                    continue
                try:
                    boxscores[mid] = self._get(http, "/api/matchdata/Result/boxscores", {"matchId": mid})
                except FetchError as exc:
                    self.soft_fail(str(exc))
        if not boxscores:
            raise NoDataYet(f"ACB {season}: aún no hay partidos finalizados")
        return {"edition_id": edition, "calendar": calendar, "boxscores": boxscores, "reused_games": reused}

    def parse(self, payload: Any, season: str) -> dict[str, ParsedLeague]:
        phase_of: dict[str, str] = {}
        for rnd in (payload.get("calendar") or {}).get("rounds") or []:
            ph = "playoffs" if rnd.get("subphaseId") else "regular"
            for m in rnd.get("matches") or []:
                phase_of[str(m["id"])] = ph
        games = [parse_boxscore(mid, doc, phase_of.get(mid, "regular"))
                 for mid, doc in (payload.get("boxscores") or {}).items() if isinstance(doc, dict)]
        if not games:
            raise AdapterError("ACB: el bruto no contiene boxscores")
        return aggregate_by_phase(games, [f"{len(games)} boxscores ACB; {payload.get('reused_games', 0)} reutilizados"])
