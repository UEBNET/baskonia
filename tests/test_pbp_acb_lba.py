"""Fuentes de jugada a jugada ACB y LBA con partidos reales guardados (sin red)."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from bbstats.lineups import stints
from bbstats.lineups.sources.acb import AcbPBP
from bbstats.lineups.sources.base import Ctx
from bbstats.lineups.sources.lba import LbaPBP

DATA = Path(__file__).resolve().parent / "data" / "pbp"
FIXTURES = {
    "acb_2025-26_104722": (AcbPBP, "regular", 5),     # prórroga
    "lba_2025-26_25176": (LbaPBP, "regular", 5),      # prórroga, asistencias con linked_action_id
    "lba_2020-21_23078": (LbaPBP, "regular", 4),      # 2020-21: asistencias por adyacencia
}


def _load(name: str) -> dict:
    with gzip.open(DATA / f"{name}.json.gz", "rt", encoding="utf-8") as fh:
        return json.load(fh)


def _parse(name: str):
    cls, _, _ = FIXTURES[name]
    doc = _load(name)
    ctx = Ctx(doc["league"], doc["season"], {"minutos_partido": 40}, None, doc["main_payload"])
    src = cls()
    refs = {r["game_id"]: r for r in src.games(ctx)}
    ref = refs[doc["game_id"]]
    return doc, ref, src.parse(doc["raw"], ref, ctx)


@pytest.mark.parametrize("name", list(FIXTURES))
def test_games_from_main_payload(name):
    _, phase, _ = FIXTURES[name]
    doc, ref, _ = _parse(name)
    assert ref["game_id"] == doc["game_id"] and ref["final"] is True and ref["phase"] == phase and ref["date"]


@pytest.mark.parametrize("name", list(FIXTURES))
def test_lineups_and_validation(name):
    _, _, periods = FIXTURES[name]
    doc, _, g = _parse(name)
    assert len(g.teams) == 2 and all(len(g.starters.get(t, [])) == 5 for t in g.teams)
    assert max(e.period for e in g.events) == periods
    # t = segundos desde el inicio; no retrocede dentro de cada periodo
    evs = sorted(g.events, key=lambda e: e.order)
    for a, b in zip(evs, evs[1:]):
        if a.period == b.period:
            assert b.t >= a.t
    assert all(0 <= e.t <= 2400 + 300 * (periods - 4) for e in evs)
    res = stints.build(g, 40)
    assert res.segments and all(s["n_a"] == 5 and s["n_b"] == 5 for s in res.segments)
    v = res.validation()
    assert v["valido"]
    if doc["league"] == "acb":
        assert v["dif_min_max_s"] <= 2 and v["dif_pm_max"] == 0
    else:   # el boxscore LBA da minutos enteros
        assert v["dif_min_max_s"] <= 60 and v["dif_min_media_s"] <= 25 and v["dif_pm_max"] <= 3
    # total de segundos de cada equipo = 5 x duración del partido
    total = 2400 + 300 * (periods - 4)
    for t in g.teams:
        assert abs(sum(res.seconds[p] for p, info in g.players.items() if info["team"] == t) - 5 * total) < 1


@pytest.mark.parametrize("name", list(FIXTURES))
def test_assists_shots_and_ids(name):
    doc, _, g = _parse(name)
    raw = doc["raw"]
    assisted = [e for e in g.events if e.assister]
    assert all(e.made and e.kind in ("shot", "ft") for e in assisted)
    assert all(g.players[e.assister]["team"] == e.team for e in assisted)
    if doc["league"] == "acb":
        box_ast = 0
        for tb in raw["box"]["teamBoxscores"]:
            q0 = next(p for p in tb["statsByPeriods"] if p["quarter"] == 0)
            box_ast += sum(p.get("assists") or 0 for p in q0["stats"]["players"])
            assert str(tb["team"]["clubId"]) in g.teams          # ids de equipo = clubId (datos principales)
            assert {str(p["player"]["id"]) for p in q0["stats"]["players"]} <= set(g.players)
        assert box_ast - 2 <= len(assisted) <= box_ast
    else:
        rows = [r for side in ("ht", "vt") for r in raw["scores"]["scores"][side]["rows"]]
        assert len(assisted) == sum(int(r.get("ass") or 0) for r in rows)
        assert {str(r["player_id"]) for r in rows} <= set(g.players)
    shots = [e for e in g.events if e.kind == "shot"]
    with_xy = [e for e in shots if e.x is not None and e.y is not None]
    assert g.has_shots and g.has_assists and len(with_xy) >= 0.85 * len(shots)
    fts = [e for e in g.events if e.kind == "ft"]
    assert fts and {e.kind for e in g.events} >= {"in", "out", "oreb", "dreb", "tov", "stl", "foul", "foul_drawn"}
    # los puntos del jugada a jugada cuadran con el marcador final del boxscore
    pts = sorted(sum(e.pts for e in g.events if e.team == t and e.made) for t in g.teams)
    if doc["league"] == "acb":
        box_pts = [next(p for p in tb["statsByPeriods"] if p["quarter"] == 0)["stats"]["total"]["points"]
                   for tb in raw["box"]["teamBoxscores"]]
    else:
        box_pts = [raw["scores"]["scores"][side]["totals"]["pun"] for side in ("ht", "vt")]
    assert pts == sorted(box_pts)


class _FakeHttp:
    def __init__(self, docs):
        self.docs, self.calls = docs, []

    def get_json(self, url, params=None, headers=None):
        self.calls.append((url, dict(params or {}), dict(headers or {})))
        for key, doc in self.docs.items():
            if key in url:
                return doc
        raise AssertionError(url)


def test_fetch_requests():
    doc = _load("acb_2025-26_104722")
    http = _FakeHttp({"PlayByPlay": doc["raw"]["pbp"], "MatchShots": doc["raw"]["shots"]})
    ctx = Ctx("acb", "2025-26", {}, http, {"boxscores": {"104722": doc["raw"]["box"]}})
    raw = AcbPBP().fetch(ctx, {"game_id": "104722"})
    assert len(http.calls) == 2 and raw["box"] == doc["raw"]["box"]
    assert all(c[1] == {"matchId": "104722"} and c[2]["X-APIKEY"] and "live.acb.com" in c[2]["Referer"]
               for c in http.calls)

    doc = _load("lba_2025-26_25176")
    http = _FakeHttp({"play-by-play": doc["raw"]["pbp"]})
    ctx = Ctx("lba", "2025-26", {}, http, {"scores": {"25176": doc["raw"]["scores"]}})
    raw = LbaPBP().fetch(ctx, {"game_id": "25176"})
    assert len(http.calls) == 1 and http.calls[0][1] == {"id": "25176"} and raw["scores"] == doc["raw"]["scores"]


def test_lba_without_actions():
    doc = _load("lba_2020-21_23078")
    raw = {"pbp": {"pbp": {"actions": [], "ht_id": 1, "vt_id": 2}}, "scores": doc["raw"]["scores"]}
    g = LbaPBP().parse(raw, {"game_id": "x"}, Ctx("lba", "2020-21", {}, None, None))
    assert not g.has_lineups and not g.events and g.notes
