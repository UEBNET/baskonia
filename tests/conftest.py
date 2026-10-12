from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bbstats.http import FetchError, HttpClient  # noqa: E402

import synth  # noqa: E402


class FakeHttp(HttpClient):
    """Cliente HTTP falso: responde desde los datos sintéticos, sin red."""

    def __init__(self, router):
        super().__init__(delay_s=0)
        self.router = router
        self.calls: list[str] = []

    def _route(self, url, params):
        self.calls.append(url)
        res = self.router(url, params or {})
        if res is None:
            raise FetchError(f"404 simulado: {url}")
        return res

    def get_json(self, url, params=None, headers=None):
        return self._route(url, params)

    def get_text(self, url, params=None, headers=None):
        return self._route(url, params)


@pytest.fixture(scope="session")
def games():
    return synth.make_games()


@pytest.fixture(scope="session")
def router(games):
    el = synth.to_euroleague(games)
    nba = synth.to_nba(games)
    acb_html = {g["game_id"]: synth.to_acb_html(g) for g in games}
    fiba = {g["game_id"]: synth.to_fiba(g) for g in games}
    table = synth.to_html_table(games)
    state = {"down": set()}

    def route(url, params):
        if any(d in url for d in state["down"]):
            return None
        m = re.search(r"/statistics/(players|teams)/(\w+)$", url)
        if m:
            page = el[m.group(1)].get(m.group(2))
            return page[0] if page else None
        if "leaguedashplayerstats" in url:
            return nba.get(params.get("MeasureType"))
        if "leaguedashteamstats" in url:
            return nba.get("teams_" + params.get("MeasureType", ""))
        if "leaguehustlestatsplayer" in url:
            return nba["hustle"]
        if "playerindex" in url:
            return nba["playerindex"]
        if "leaguedashptstats" in url:
            return None  # tracking no disponible: debe registrarse como error no fatal
        m = re.search(r"jornada_numero/(\d+)", url)
        if m:
            return synth.acb_calendar_html(list(acb_html)) if m.group(1) == "1" else "<html></html>"
        m = re.search(r"/partido/estadisticas/id/(\d+)", url)
        if m:
            return acb_html.get(m.group(1))
        m = re.search(r"/data/(\d+)/data.json", url)
        if m:
            return fiba.get(m.group(1))
        if "lnb-test" in url:
            return table
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
        "ligas": {
            "euroleague": league("euroleague", competicion="E"),
            "acb": league("acb"),
            "nba": league("nba", minutos_partido=48),
            "gleague": league("gleague", minutos_partido=48),
            "lba": league("fiba_livestats", temporadas={"2025-26": {"match_ids": [str(100001 + i) for i in range(12)]}}),
            "lnb": league("html_table", temporadas={"2025-26": {"players_urls": ["https://lnb-test/players"]}}),
        },
    }
