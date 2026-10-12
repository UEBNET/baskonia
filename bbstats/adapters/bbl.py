"""easyCredit BBL (Alemania) — datos embebidos en las páginas públicas de partido de easycredit-bbl.de.

La API de la BBL (api.basketball-bundesliga.de) exige credenciales de su web, así que se lee el
JSON que cada página pública de partido incluye (`__NEXT_DATA__`):
    https://www.easycredit-bbl.de/spiele/<id>
  initialGameData : temporada, competición (BBL / BBL_CUP), fase (MAIN_ROUND, PLAYINS, ROUND_OF_8,
                    SEMI_FINALS, FINALS), estado, equipos y resultado
  initialGameStats: boxscore por equipo (gameStat) y por jugador (playerStats: segundos, tiros,
                    rebotes, asistencias, robos, pérdidas, tapones, faltas cometidas y recibidas,
                    titular, +/-, valoración)

Descubrimiento de partidos: los ids de cada temporada forman bloques consecutivos (temporada
regular por un lado y playoffs por otro). Se parte de ids semilla (config `semillas`, y para la
temporada en curso los partidos de /saison/aktuelle-spiele) y se recorre cada bloque hacia
ambos lados hasta encontrar `max_huecos` ids seguidos sin partido de la temporada.
En el bruto se guarda el JSON de datos de cada página (sin el HTML ni los menús).
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..http import FetchError, HttpClient
from ..utils import to_float
from .base import BaseAdapter, NoDataYet, ParsedLeague
from .boxscore import aggregate_by_phase

SITE = "https://www.easycredit-bbl.de"
_NEXT = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
REGULAR_STAGES = {"MAIN_ROUND"}
_MAP = {"points": "pts", "twoPointShotsMade": "fg2m", "twoPointShotsAttempted": "fg2a",
        "threePointShotsMade": "fg3m", "threePointShotsAttempted": "fg3a", "freeThrowsMade": "ftm",
        "freeThrowsAttempted": "fta", "fieldGoalsMade": "fgm", "fieldGoalsAttempted": "fga",
        "offensiveRebounds": "oreb", "defensiveRebounds": "dreb", "totalRebounds": "reb", "assists": "ast",
        "steals": "stl", "turnovers": "tov", "blocks": "blk", "foulsCommitted": "pf", "foulsReceived": "pfd",
        "plusMinus": "plus_minus", "efficiency": "src_eff"}


def _stats(rec: dict) -> dict:
    out = {c: to_float(rec.get(k)) for k, c in _MAP.items() if rec.get(k) is not None}
    if rec.get("secondsPlayed") is not None:
        out["min"] = to_float(rec["secondsPlayed"]) / 60.0
    return {k: v for k, v in out.items() if v is not None}


def _page_data(html: str) -> dict | None:
    m = _NEXT.search(html or "")
    if not m:
        return None
    pp = (json.loads(m.group(1)).get("props") or {}).get("pageProps") or {}
    if not pp.get("initialGameData"):
        return None
    return {"initialGameData": pp.get("initialGameData"), "initialGameStats": pp.get("initialGameStats")}


def parse_game(doc: dict) -> dict:
    gd = doc.get("initialGameData") or {}
    gs = doc.get("initialGameStats") or {}
    sides = []
    for key, tkey in (("homeTeam", "homeTeam"), ("guestTeam", "guestTeam")):
        info = gd.get(tkey) or {}
        st = gs.get(key) or {}
        players = []
        for p in st.get("playerStats") or []:
            sp = p.get("seasonPlayer") or {}
            line = {"player_id": str(sp.get("playerId") or sp.get("id")),
                    "name": f"{sp.get('firstName', '')} {sp.get('lastName', '')}".strip(),
                    "dorsal": sp.get("shirtNumber"), "posicion": sp.get("position"),
                    "starter": bool(p.get("isStartingFive"))}
            line.update(_stats(p))
            line.pop("src_eff", None)
            players.append(line)
        totals = _stats(st.get("gameStat") or {})
        totals.pop("plus_minus", None)
        totals.pop("src_eff", None)
        sides.append({"team_id": str(info.get("teamId")), "name": info.get("name"), "code": info.get("tlc"),
                      "totals": totals, "players": players})
    phase = "regular" if gd.get("stage") in REGULAR_STAGES else "playoffs"
    return {"game_id": str(gd.get("id")), "phase": phase, "final": gd.get("status") == "OFFICIAL",
            "teams": sides, "date": gd.get("scheduledTime")}


class BBLAdapter(BaseAdapter):
    name = "bbl"
    version = "1.0"

    def _game(self, http: HttpClient, gid: int) -> dict | None:
        resp = http.get(f"{SITE}/spiele/{gid}", ok_status=(400, 404))
        if not resp.ok:
            return None
        return _page_data(resp.text)

    def _current_seeds(self, http: HttpClient) -> list[int]:
        try:
            html = http.get_text(f"{SITE}/saison/aktuelle-spiele")
        except FetchError as exc:
            self.soft_fail(str(exc))
            return []
        return sorted({int(x) for x in re.findall(r'"id":\s*"(\d{7})"', html)})

    def fetch(self, season: str, http: HttpClient, previous_payload: Any | None = None) -> Any:
        sc = self.season_cfg(season)
        year = int(sc.get("season_id", sc["start_year"]))
        max_gap = int(self.cfg.get("max_huecos", 30))
        prev = (previous_payload or {}).get("games", {}) if isinstance(previous_payload, dict) else {}
        seeds = [int(x) for x in sc.get("semillas", [])] or self._current_seeds(http)
        games: dict[str, Any] = {}
        visited: set[int] = set()
        reused = 0

        def get(gid: int) -> dict | None:
            nonlocal reused
            visited.add(gid)
            if str(gid) in prev and (prev[str(gid)].get("initialGameData") or {}).get("status") == "OFFICIAL":
                reused += 1
                return prev[str(gid)]
            try:
                return self._game(http, gid)
            except FetchError as exc:
                self.soft_fail(str(exc))
                return None

        for seed in seeds:
            if seed in visited:
                continue
            for step in (-1, 1):
                gid, gap = seed if step == 1 else seed - 1, 0
                while gap < max_gap:
                    if gid in visited and str(gid) not in games:
                        gid += step
                        gap += 1
                        continue
                    doc = games.get(str(gid)) or get(gid)
                    gd = (doc or {}).get("initialGameData") or {}
                    if gd.get("seasonId") == year and gd.get("competition") == self.cfg.get("competicion", "BBL"):
                        games[str(gid)] = doc
                        gap = 0
                    else:
                        gap += 1
                    gid += step
        finished = {k: v for k, v in games.items() if (v.get("initialGameData") or {}).get("status") == "OFFICIAL"}
        if not finished:
            raise NoDataYet(f"BBL {season}: no se encontraron partidos finalizados (revisa 'semillas')")
        return {"season_id": year, "seeds": seeds, "games": finished, "reused_games": reused,
                "ids_scanned": len(visited)}

    def parse(self, payload: Any, season: str) -> dict[str, ParsedLeague]:
        games = [parse_game(doc) for doc in (payload.get("games") or {}).values()]
        return aggregate_by_phase(games, [f"{len(games)} partidos BBL; {payload.get('reused_games', 0)} reutilizados; "
                                          f"{payload.get('ids_scanned')} ids explorados"])
