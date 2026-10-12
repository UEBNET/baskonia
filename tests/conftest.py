from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bbstats.http import FetchError, HttpClient  # noqa: E402

import synth  # noqa: E402


class FakeResp:
    def __init__(self, url: str, status: int, payload) -> None:
        self.url, self.status_code = url, status
        self.ok = 200 <= status < 400
        self.encoding = self.apparent_encoding = "utf-8"
        self._payload = payload
        self.text = payload if isinstance(payload, str) else json.dumps(payload)

    def json(self):
        return self._payload if not isinstance(self._payload, str) else json.loads(self._payload)


class FakeHttp(HttpClient):
    """Cliente HTTP falso: responde desde la liga sintética, sin red."""

    def __init__(self, router):
        super().__init__(delay_s=0)
        self.router = router
        self.calls: list[str] = []

    def request(self, method, url, params=None, headers=None, data=None, json_body=None, ok_status=()):
        self.calls.append(url)
        res = self.router(method, url, params or {}, data or json_body or {})
        if res is None:
            if 404 in ok_status:
                return FakeResp(url, 404, "")
            raise FetchError(f"404 simulado: {url}")
        return FakeResp(url, 200, res)


@pytest.fixture(scope="session")
def games():
    return synth.make_games()


@pytest.fixture(scope="session")
def router(games):
    el = {ph: synth.to_euroleague(games, ph) for ph in ("total", "regular")}
    gl = {ph: synth.to_nba_stats(games, ph) for ph in ("regular", "playoffs")}
    acb = synth.to_acb(games)
    lba = synth.to_lba(games)
    bbl = synth.to_bbl_pages(games)
    lnb = synth.to_lnb(games)
    bref = synth.to_bref(games)
    bn = synth.to_basketnews([f"Jugador A{k}" for k in range(8)])
    state = {"down": set()}

    def route(method, url, params, body):
        if any(d in url for d in state["down"]):
            return None
        # Euroliga
        m = re.search(r"/statistics/(players|teams)/(\w+)$", url)
        if m:
            ph = "regular" if params.get("phaseTypeCode") == "RS" else "total"
            return el[ph][m.group(1)].get(m.group(2))
        # G League
        if "leaguedashplayerstats" in url or "leaguedashteamstats" in url:
            ph = "playoffs" if params.get("SeasonType") == "Playoffs" else "regular"
            key = params.get("MeasureType") if "player" in url else "teams_" + params.get("MeasureType", "")
            return gl[ph].get(key)
        if "playerindex" in url:
            return gl["regular"]["playerindex"]
        # ACB
        if "season-calendar" in url:
            return acb["calendar"] if params.get("editionId") else acb["seasons"]
        if "Result/boxscores" in url:
            return acb["boxscores"].get(str(params.get("matchId")))
        # LBA
        if "get-championships-calendar-by-id" in url:
            cid = str(params.get("id"))
            if "d" not in params:
                return {"filters": {"days": [{"event_serial": 1}]}, "matches": []}
            return {"matches": lba["calendar"][cid]}
        if "get-championships-matches-scores-by-id" in url:
            return lba["scores"].get(str(params.get("id")))
        if "championships/get-championships" in url:
            return lba["champs"]
        # BBL
        m = re.search(r"easycredit-bbl\.de/spiele/(\d+)", url)
        if m:
            return bbl.get(m.group(1))
        # LNB
        if url.endswith("lnb.fr/api/token"):
            return {"token": "anon"}
        if "getDivisionCompetitionByYear" in url:
            return lnb["comps"]
        if "getPersonCriterion" in url:
            return lnb["players"][body["competitionExternalId"]]
        if "getTeamsCriterion" in url:
            return lnb["teams"][body["competitionExternalId"]]
        if "teams/getRoster" in url:
            return lnb["rosters"].get(str(params.get("team_external_id")))
        if "getPersonSeasonAll" in url:
            return lnb["season_all"].get((str(body["person_external_id"]), body["competition_external_id"]))
        # Basketball-Reference
        if "basketball-reference.com/leagues/NBA_2026_totals" in url:
            return bref["totals"]
        if "basketball-reference.com/leagues/NBA_2026.html" in url:
            return bref["teams_regular"]
        if "basketball-reference.com/playoffs/NBA_2026.html" in url:
            return bref["teams_playoffs"]
        # BasketNews
        if "basketnews.com" in url:
            return bn["players"] if url.endswith("players.json") else bn["onoff"]
        return None

    route.state = state
    return route


@pytest.fixture
def config(tmp_path):
    def league(adapter, **kw):
        return {"adaptador": adapter, "activa": True, "nombre": adapter.upper(), "pais": "X",
                "minutos_partido": 40, **kw}

    return {
        "temporada_por_defecto": "2025-26",
        "rutas": {"bruto": str(tmp_path / "raw"), "procesado": str(tmp_path / "processed")},
        "http": {"delay_s": 0},
        "comprimir_bruto": True,
        "ligas": {
            "euroleague": league("euroleague", competicion="E", basketnews_league_id=25),
            "gleague": league("gleague", season_types={"regular": "Regular Season", "playoffs": "Playoffs"}),
            "acb": league("acb"),
            "lba": league("lba"),
            "bbl": league("bbl", max_huecos=3, temporadas={"2025-26": {"semillas": [synth.FIRST_ID + 3]}}),
            "lnb": league("lnb"),
            "nba": league("bref_nba"),
        },
    }
