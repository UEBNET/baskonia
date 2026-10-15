"""Fuentes de jugada a jugada BBL y LNB con partidos reales guardados (sin red)."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from bbstats.lineups import stints
from bbstats.lineups.sources.base import Ctx
from bbstats.lineups.sources.bbl import BblPBP
from bbstats.lineups.sources.lnb import LnbPBP

DATA = Path(__file__).resolve().parent / "data" / "pbp"


def _load(name: str) -> dict:
    with gzip.open(DATA / f"{name}.json.gz", "rt", encoding="utf-8") as fh:
        return json.load(fh)


def _ctx(doc: dict, http=None) -> Ctx:
    return Ctx(doc["league"], doc["season"], {"minutos_partido": 40}, http, doc["main_payload"])


def _bbl(name: str):
    doc = _load(name)
    ctx, src = _ctx(doc), BblPBP()
    ref = {r["game_id"]: r for r in src.games(ctx)}[doc["game_id"]]
    raw = src.fetch(ctx, ref)          # del bruto principal: sin red (ctx.http es None)
    return doc, ref, src.parse(raw, ref, ctx)


def _check_lineups(g, periods: int, max_sec: float = 10) -> dict:
    assert len(g.teams) == 2 and all(len(g.starters.get(t, [])) == 5 for t in g.teams)
    assert max(e.period for e in g.events) == periods
    evs = sorted(g.events, key=lambda e: e.order)
    for a, b in zip(evs, evs[1:]):
        if a.period == b.period:
            assert b.t >= a.t
    assert all(0 <= e.t <= 2400 + 300 * (periods - 4) for e in evs)
    res = stints.build(g, 40)
    assert res.segments and all(s["n_a"] == 5 and s["n_b"] == 5 for s in res.segments)
    v = res.validation()
    assert v["valido"] and v["dif_pm_max"] == 0 and v["dif_min_max_s"] <= max_sec
    return v


# ---------------------------------------------------------------- BBL
def test_bbl_games_phase_and_ids():
    doc, ref, g = _bbl("bbl_2025-26_2005772")
    assert ref["final"] and ref["phase"] == "playoffs" and ref["stage"] == "FINALS" and ref["date"]
    gd = doc["main_payload"]["games"][doc["game_id"]]["initialGameData"]
    assert g.teams == [gd["homeTeam"]["teamId"], gd["guestTeam"]["teamId"]]
    box_ids = {ps["seasonPlayer"]["playerId"] for side in ("homeTeam", "guestTeam")
               for ps in doc["main_payload"]["games"][doc["game_id"]]["initialGameStats"][side]["playerStats"]}
    assert set(g.players) == box_ids                      # mismos ids que los datos principales
    assert {e.player for e in g.events if e.player} <= box_ids
    assert all(g.players[p]["team"] in g.teams for p in g.players)


def test_bbl_substitution_split_and_assists():
    doc, _, g = _bbl("bbl_2025-26_2005772")
    acts = doc["main_payload"]["games"][doc["game_id"]]["initialGameStats"]["actions"]
    subs = [a for a in acts if a.get("type") == "SUBSTITUTION"]
    evs = sorted(g.events, key=lambda e: e.order)
    pairs = [(a, b) for a, b in zip(evs, evs[1:]) if a.kind == "out" and b.kind == "in"]
    assert len(pairs) == len(subs)
    assert (pairs[0][0].player, pairs[0][1].player) == (subs[0]["seasonPlayerId"], subs[0]["assistingSeasonPlayerId"])
    made = [e for e in g.events if e.kind == "shot" and e.made]
    assert g.has_assists and any(e.assister for e in made)
    assert all(e.assister != e.player for e in g.events if e.assister)


def test_bbl_lineups_valid():
    _, _, g = _bbl("bbl_2025-26_2005772")
    assert g.has_lineups and g.has_shots
    _check_lineups(g, 4)


def test_bbl_2023_24_null_player_filled():
    """2023-24: un jugador del boxscore no aparece en las acciones (llegan con seasonPlayerId nulo)."""
    _, ref, g = _bbl("bbl_2023-24_33195")
    assert ref["phase"] == "regular"
    assert any("ausente" in n for n in g.notes)
    assert not [e for e in g.events if e.kind in ("in", "out") and e.player is None]
    _check_lineups(g, 6)                                   # dos prórrogas


def test_bbl_2020_21_without_lineups():
    _, _, g = _bbl("bbl_2020-21_25498")
    assert g.has_lineups is False and g.has_assists
    assert any(e.assister for e in g.events if e.kind == "shot")
    v = stints.build(g, 40).validation()
    assert v["valido"] is False and v["tramos"] == 0


# ---------------------------------------------------------------- LNB
class FakeHttp:
    """Responde con las respuestas reales guardadas en el fixture (fixtures del widget vacío -> jornadas)."""

    def __init__(self, api: dict) -> None:
        self.api, self.calls = api, []

    def get_json(self, url, params=None, headers=None):
        self.calls.append(url)
        if url.endswith("/fixtures"):
            return {"data": {"fixtures": []}}
        if url.endswith("/api/token"):
            return {"token": "x"}
        if url.endswith("getCompetitionRounds"):
            return self.api.get(f"rounds_{params['competition_external_id']}", {"data": []})
        raise AssertionError(url)

    def post_json(self, url, data=None, json_body=None, headers=None):
        self.calls.append(url)
        key = f"matches_{json_body['competition_external_id']}_{json_body['round_number']}"
        return self.api.get(key, {"data": {"matches": []}})


def _lnb(name: str):
    doc = _load(name)
    ctx = _ctx(doc)
    return doc, LnbPBP().parse(doc["raw"], doc["ref"], ctx)


def test_lnb_games_fallback_to_lnb_rounds():
    doc = _load("lnb_2025-26_6bdfcd47")
    http = FakeHttp(doc["api"])
    refs = LnbPBP().games(_ctx(doc, http))
    assert [r["game_id"] for r in refs] == [doc["game_id"]]
    assert refs[0]["phase"] == "playoffs" and refs[0]["final"] and refs[0]["competition"] == "311"
    assert any(u.endswith("/fixtures") for u in http.calls)        # primero el widget, luego jornadas


def test_lnb_ids_match_main_data():
    doc, g = _lnb("lnb_2025-26_6bdfcd47")
    main_players = {str(r["person"]["external_id"]) for d in doc["main_payload"]["players"].values()
                    for r in d["data"]}
    main_teams = {str(r["team"]["external_id"]) for d in doc["main_payload"]["teams"].values() for r in d["data"]}
    assert set(g.teams) <= main_teams and g.team_names[g.teams[0]] == "Paris"
    played = [p for p, b in g.box.items() if (b["sec"] or 0) > 0]
    assert played and all(p.isdigit() for p in g.players)           # ids numéricos de lnb.fr, no uuids
    assert set(played) <= main_players | {str(r["person"]["external_id"])
                                          for d in doc["main_payload"]["rosters"].values() for r in d["data"]}


def test_lnb_lineups_assists_valid():
    _, g = _lnb("lnb_2025-26_6bdfcd47")
    assert g.has_lineups and g.has_assists and g.has_shots
    assert not any("sin enlazar" in n for n in g.notes)
    assert sum(1 for e in g.events if e.assister) > 10
    _check_lineups(g, 4, max_sec=20)      # minutos ±16 s: un cambio de la fuente mal anotado


def test_lnb_2020_21_box_only():
    _, g = _lnb("lnb_2020-21_fcf2cf4c")
    assert g.has_lineups is False and g.has_assists is False and not g.events
    assert len(g.box) > 15 and all(p.isdigit() for p in g.players)
    assert stints.build(g, 40).validation()["valido"] is False


@pytest.mark.parametrize("name", ["bbl_2025-26_2005772", "bbl_2023-24_33195", "bbl_2020-21_25498",
                                  "lnb_2025-26_6bdfcd47", "lnb_2020-21_fcf2cf4c"])
def test_fixture_size(name):
    assert (DATA / f"{name}.json.gz").stat().st_size <= 300_000
