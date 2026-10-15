"""Fuentes de jugada a jugada NBA y G League (stats.gleague.nba.com) con partidos reales guardados (sin red)."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from bbstats.lineups import stints
from bbstats.lineups.sources.base import Ctx
from bbstats.lineups.sources.nba_stats import GLeaguePBP, NbaPBP, _Resolver, norm_name

DATA = Path(__file__).resolve().parent / "data" / "pbp"
GL_CFG = {"minutos_partido": 48, "league_id": "20",
          "season_types": {"regular": "Regular Season", "playoffs": "Playoffs", "copa": "Showcase"}}
NBA_CFG = {"minutos_partido": 48}
FIXTURES = {
    "gleague_2025-26_2022500333": (GLeaguePBP, GL_CFG, "regular", 4),   # tiros libres únicos de 2 y 3 puntos
    "nba_2025-26_0042500173": (NbaPBP, NBA_CFG, "playoffs", 5),          # playoffs con prórroga
    "nba_2020-21_0022000828": (NbaPBP, NBA_CFG, "regular", 4),           # "Kanter" (Freedom), Williams/Williams III
}


class _GamelogHttp:
    """Responde leaguegamelog con el gamelog guardado (sólo para su SeasonType) y falla con el resto."""

    def __init__(self, doc: dict) -> None:
        self.doc, self.calls = doc, []

    def get_json(self, url, params=None, headers=None):
        self.calls.append((url.rsplit("/", 1)[-1], dict(params or {})))
        assert url.endswith("/leaguegamelog") and headers["Origin"] == "https://gleague.nba.com"
        if params["SeasonType"] == self.doc["season_type"]:
            return self.doc["gamelog"]
        return {"resultSets": [{"name": "LeagueGameLog", "headers": [], "rowSet": []}]}


def _load(name: str) -> dict:
    with gzip.open(DATA / f"{name}.json.gz", "rt", encoding="utf-8") as fh:
        return json.load(fh)


def _parse(name: str):
    cls, cfg, _, _ = FIXTURES[name]
    doc = _load(name)
    http = _GamelogHttp(doc)
    ctx = Ctx(doc["league"], doc["season"], cfg, http, doc["main_payload"])
    src = cls()
    refs = {r["game_id"]: r for r in src.games(ctx)}
    return doc, http, refs[doc["game_id"]], src.parse(doc["raw"], refs[doc["game_id"]], ctx)


@pytest.mark.parametrize("name", list(FIXTURES))
def test_games_from_gamelog(name):
    _, cfg, phase, _ = FIXTURES[name]
    doc, http, ref, _ = _parse(name)
    assert ref["final"] is True and ref["phase"] == phase and ref["date"]
    assert ref["home_team"] != ref["away_team"]
    lid = {c[1]["LeagueID"] for c in http.calls}
    assert lid == ({"20"} if doc["league"] == "gleague" else {"00"})
    assert len(http.calls) == (3 if doc["league"] == "gleague" else 2)  # una llamada por fase


@pytest.mark.parametrize("name", list(FIXTURES))
def test_lineups_and_validation(name):
    _, _, _, periods = FIXTURES[name]
    doc, _, _, g = _parse(name)
    assert len(g.teams) == 2 and all(len(g.starters.get(t, [])) == 5 for t in g.teams)
    assert max(e.period for e in g.events) == periods
    evs = sorted(g.events, key=lambda e: e.order)
    for a, b in zip(evs, evs[1:]):
        if a.period == b.period:
            assert b.t >= a.t
    assert all(0 <= e.t <= 2880 + 300 * (periods - 4) for e in evs)
    # los puntos de los eventos cuadran con el boxscore
    box = doc["raw"]["box"]["boxScoreTraditional"]
    pts = {t: sum(e.pts for e in evs if e.team == t and e.made and e.kind in ("shot", "ft")) for t in g.teams}
    assert sorted(pts.values()) == sorted(box[k]["statistics"]["points"] for k in ("homeTeam", "awayTeam"))
    res = stints.build(g, 48)
    assert res.segments and all(s["n_a"] == 5 and s["n_b"] == 5 for s in res.segments)
    v = res.validation()
    assert v["valido"] and v["anomalias"] == 0
    assert v["dif_min_max_s"] <= 1 and v["dif_pm_max"] == 0
    assert "sin identificar" not in v["notas"]
    assert sum(1 for e in evs if e.kind == "shot" and e.assister) > 30


def test_gleague_ids_and_single_free_throws():
    _, _, _, g = _parse("gleague_2025-26_2022500333")
    assert all(t.startswith("1612709") for t in g.teams)
    assert all(p.isdigit() for p in g.players)
    fts = [e for e in g.events if e.kind == "ft" and e.made]
    assert {e.pts for e in fts} >= {1, 2}       # "Free Throw 2PT" vale 2; el adicional (and-one) 1
    assert all(e.value == 1 for e in fts)


def test_nba_ids_mapped_to_basketball_reference():
    _, _, _, g = _parse("nba_2025-26_0042500173")
    assert set(g.teams) <= {"ATL", "BOS", "BRK", "CHI", "CHO", "CLE", "DAL", "DEN", "DET", "GSW", "HOU", "IND",
                            "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK", "OKC", "ORL", "PHI", "PHO",
                            "POR", "SAC", "SAS", "TOR", "UTA", "WAS"}
    played = [p for p, b in g.box.items() if b["sec"]]
    assert played and not [p for p in played if p.startswith("nba:")]
    assert all(e.assister is None or not e.assister.startswith("nba:") for e in g.events)
    _, _, _, g2 = _parse("nba_2020-21_0022000828")
    assert "kanteen01" in g2.players and g2.players["kanteen01"]["nombre"] == "Enes Freedom"
    assert {"williro04", "willigr01"} <= set(g2.players)


def test_free_throws_follow_the_foul_lineup():
    """Cambios listados entre la falta y el tiro libre: el TL va con el quinteto de la falta (+/- oficial)."""
    _, _, _, g = _parse("nba_2025-26_0042500173")
    evs = sorted(g.events, key=lambda e: e.order)
    for i, e in enumerate(evs):
        if e.kind == "ft":
            j = i - 1
            while j >= 0 and evs[j].kind == "ft" and evs[j].t == e.t:
                j -= 1
            prev = evs[j]
            assert prev.kind != "in" or prev.player == e.player or prev.t != e.t


def test_resolver_names():
    box = {"homeTeam": {"teamId": 1, "players": [
        {"personId": 11, "firstName": "Jalen", "familyName": "Williams", "nameI": "J. Williams", "statistics": {"minutes": "30:00"}},
        {"personId": 12, "firstName": "Jaylin", "familyName": "Williams", "nameI": "J. Williams", "statistics": {"minutes": "10:00"}},
        {"personId": 13, "firstName": "Robert", "familyName": "Williams III", "nameI": "R. Williams III", "statistics": {"minutes": "20:00"}},
        {"personId": 14, "firstName": "Jaime", "familyName": "Jaquez Jr.", "nameI": "J. Jaquez Jr.", "statistics": {"minutes": "20:00"}},
        {"personId": 15, "firstName": "Enes", "familyName": "Freedom", "nameI": "E. Freedom", "statistics": {"minutes": "20:00"}},
    ]}, "awayTeam": {"teamId": 2, "players": []}}
    acts = [{"teamId": 1, "personId": 15, "playerName": "Freedom", "actionType": "Substitution",
             "description": "SUB: Jaquez Jr. FOR Kanter"}]
    r = _Resolver(box, acts)
    assert r.resolve(1, "Jal. Williams") == 11 and r.resolve(1, "Jay. Williams") == 12
    assert r.resolve(1, "Williams III") == 13
    assert r.resolve(1, "Jaquez Jr.") == 14 and r.resolve(1, "Kanter") == 15
    # ambiguo: se prefiere el que no está en pista para una entrada y el que está para una asistencia
    assert r.resolve(1, "Williams", on={11}, want_on=False) == 12
    assert r.resolve(1, "Williams", on={12}, want_on=True) == 12
    assert norm_name("Nikola Jokić") == "nikola jokic" and norm_name("Gary Trent Jr.") == "gary trent"


@pytest.mark.parametrize("league", ["gleague", "nba"])
def test_official_tables(league):
    doc = _load(f"{league}_2025-26_oficial")
    src = GLeaguePBP() if league == "gleague" else NbaPBP()
    ctx = Ctx(league, "2025-26", GL_CFG if league == "gleague" else NBA_CFG, None, doc["main_payload"])
    out = src.parse_official(doc["raw"], ctx)
    assert set(out) == {"quintetos", "parejas", "onoff"}
    assert out["quintetos"] and all(r["n_jugadores"] == 5 and len(r["jugadores"].split("|")) == 5
                                    for r in out["quintetos"])
    assert out["parejas"] and all(len(r["jugadores"].split("|")) == 2 for r in out["parejas"])
    q = out["quintetos"][0]
    assert q["fase"] == "regular" and "net_rating" in q and "plus_minus" in q and "poss" in q  # Base + Advanced
    o = out["onoff"][0]
    assert "on_net_rating" in o and "off_net_rating" in o and o["player_id"]
    if league == "nba":
        assert q["team_id"] == "OKC"
        ids = [p for r in out["quintetos"] for p in r["jugadores"].split("|")]
        assert ids and all(not p.startswith("nba:") for p in ids)
    else:
        assert q["team_id"].startswith("1612709")
    json.dumps(doc["raw"])  # el bruto sigue siendo JSON tras interpretarlo
