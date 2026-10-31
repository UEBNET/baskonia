"""NCAA (ESPN): traducción del summary al data.json de FIBA LiveStats (to_fls), fases, mitades -> periodos de
10', filtro top-50 en el parse y jugada a jugada (con y sin cambios)."""
from bbstats.adapters.ncaa import NCAAAdapter, _period_clock, phase_of, to_fls
from bbstats.lineups.model import clock_to_seconds, elapsed
from bbstats.lineups.sources.base import Ctx
from bbstats.lineups.sources.ncaa import NcaaPBP
from bbstats.lineups.stints import build

KEYS = ["minutes", "points", "fieldGoalsMade-fieldGoalsAttempted",
        "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "freeThrowsMade-freeThrowsAttempted",
        "rebounds", "assists", "turnovers", "steals", "blocks", "offensiveRebounds", "defensiveRebounds", "fouls"]


def _ath(pid, starter, stats):
    return {"athlete": {"id": pid, "displayName": f"Player {pid}", "jersey": "1",
                        "position": {"abbreviation": "G"}}, "starter": starter, "stats": stats}


def _team(tid, pids, pts_first):
    aths = [_ath(pids[0], True, ["40", str(pts_first), "1-2", "0-1", "1-1", "1", "1", "0", "0", "0", "0", "1", "1"])]
    aths += [_ath(p, True, ["40", "0", "0-0", "0-0", "0-0", "0", "0", "0", "0", "0", "0", "0", "0"]) for p in pids[1:5]]
    aths.append(_ath(pids[5], False, []))                  # no jugó
    return {"team": {"id": tid}, "statistics": [{"keys": KEYS, "athletes": aths}]}


def _play(n, tt, team, parts=(), per=1, clock="19:00", **kw):
    d = {"id": str(n), "type": {"text": tt}, "text": kw.pop("text", tt), "team": {"id": team},
         "participants": [{"athlete": {"id": p}} for p in parts], "period": {"number": per},
         "clock": {"displayValue": clock}, "scoringPlay": False, "shootingPlay": False,
         "coordinate": {"x": 25, "y": 0}}
    d.update(kw)
    return d


H = ["h1", "h2", "h3", "h4", "h5", "h6"]
A = ["a1", "a2", "a3", "a4", "a5", "a6"]


def _doc(subs=True):
    plays = [
        _play(1, "JumpShot", "10", ["h1", "h2"], clock="18:00", shootingPlay=True, scoringPlay=True,
              pointsAttempted=2, coordinate={"x": 30, "y": 10}),
        _play(2, "JumpShot", "20", ["a1"], clock="17:30", shootingPlay=True, pointsAttempted=3,
              coordinate={"x": 25, "y": 0}),                # (25, 0) = relleno: sin coordenadas
        _play(3, "Block Shot", "10", ["h3"], clock="17:30"),
        _play(4, "Defensive Rebound", "10", [], clock="17:29"),
        _play(41, "PersonalFoul", "10", ["h4"], clock="5:00"),          # 1.ª mitad, 2.º tramo de 10'
        _play(42, "PersonalFoul", "20", ["a4"], per=2, clock="15:00"),  # 2.ª mitad, 1.er tramo
        _play(5, "MadeFreeThrow", "20", ["a1"], per=2, clock="5:00", shootingPlay=True, scoringPlay=True,
              pointsAttempted=1),
        _play(6, "Lost Ball Turnover", "10", ["h1"], per=2, clock="4:00"),
        _play(7, "Steal", "20", ["a2"], per=2, clock="4:00"),
        _play(8, "PersonalFoul", "20", ["a3"], per=3, clock="2:00"),
        _play(9, "End Game", "20", [], per=3, clock="0:00"),
    ]
    if subs:
        plays[5:5] = [_play(50, "Substitution", "10", ["h5"], per=2, clock="8:00", text="P subbing out for H"),
                      _play(51, "Substitution", "10", ["h6"], per=2, clock="8:00", text="P subbing in for H")]
    return {"header": {"competitions": [{"date": "2026-01-10T20:00Z", "status": {"type": {"completed": True}},
                                         "competitors": [
                                             {"id": "20", "homeAway": "away", "score": "1",
                                              "team": {"id": "20", "displayName": "Away U"}},
                                             {"id": "10", "homeAway": "home", "score": "2",
                                              "team": {"id": "10", "displayName": "Home U", "abbreviation": "HU"}}]}]},
            "boxscore": {"teams": [{"team": {"id": "10"}, "statistics": [
                {"name": "totalRebounds", "displayValue": "1"}, {"name": "totalTurnovers", "displayValue": "1"},
                {"name": "fieldGoalsMade-fieldGoalsAttempted", "displayValue": "1-1"},
                {"name": "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "displayValue": "0-0"}]}],
                "players": [_team("20", A, 1), _team("10", H, 2)]},
            "plays": plays}


ROSTERS = {"10": {"coach": [{"id": "c1", "firstName": "Coach", "lastName": "Home"}],
                  "athletes": [{"id": "h1", "height": 75.0}]}}


def test_fases_y_reloj():
    assert phase_of(2, "SEC Tournament - Final") == "regular"
    assert phase_of(3, "Men's Basketball Championship - First Four") == "playoffs"
    assert phase_of(3, "NIT - Quarterfinal") == "excluida"
    assert phase_of(1, "") is None
    # mitad de 20' -> dos periodos de 10'; el tiempo transcurrido del modelo común sale exacto
    for half, clock, t in ((1, "20:00", 0), (1, "15:00", 300), (1, "10:00", 600), (1, "4:30", 930),
                           (2, "20:00", 1200), (2, "0:00", 2400), (3, "5:00", 2400), (3, "1:00", 2640)):
        per, ptype, gt = _period_clock(half, clock)
        per = per + 4 if ptype == "OVERTIME" else per
        assert elapsed(per, clock_to_seconds(gt), 40) == t


def test_to_fls():
    f = to_fls(_doc(), ROSTERS)
    h, a = f["tm"]["1"], f["tm"]["2"]                 # local primero
    assert h["teamId"] == "10" and a["teamId"] == "20" and h["coach"] == "Coach Home"
    p1 = h["pl"]["1"]
    assert p1["personId"] == "h1" and p1["sMinutes"] == "40:00" and p1["sTwoPointersMade"] == 1
    assert p1["sThreePointersAttempted"] == 1 and p1["height"] == 75.0
    assert h["pl"]["6"]["sMinutes"] == "0:00"
    assert h["tot_sTurnovers"] == 1 and h["tot_sTwoPointersMade"] == 1
    acts = list(reversed(f["pbp"]))
    kinds = [x["actionType"] for x in acts]
    assert kinds[:5] == ["2pt", "assist", "3pt", "block", "rebound"]
    assert acts[1]["previousAction"] == acts[0]["actionNumber"] and acts[1]["pno"] == 2
    assert acts[4].get("qualifier") == ["team"] and acts[4]["subType"] == "defensive"
    assert len(h["shot"]) == 1 and not a["shot"]
    assert h["shot"][0]["x"] == round(15.25 / 94 * 100, 2) and h["shot"][0]["y"] == 60.0
    assert a["pl"]["1"]["sBlocksReceived"] == 1
    assert f["status"] == "complete"


def _cfg():
    return {"minutos_partido": 40, "temporadas": {"2025-26": {"top50": [{"espn_id": "10", "nombre": "Home U"}]}}}


def test_parse_filtra_top50():
    payload = {"games": {"1": _doc()}, "fases": {"1": "regular"}, "fechas": {"1": "2026-01-10"},
               "equipos": ROSTERS}
    out = NCAAAdapter("ncaa", _cfg()).parse(payload, "2025-26")
    reg = out["regular"]
    assert {t["team_id"] for t in reg.teams} == {"10"}
    assert {p["team_id"] for p in reg.players} == {"10"}
    t = reg.teams[0]
    assert t["team_pts"] == 2 and t["opp_pts"] == 1 and t["team_w"] == 1
    assert sum(p.get("pts") or 0 for p in reg.players) == t["team_pts"]


def test_pbp_con_y_sin_cambios():
    for subs in (True, False):
        payload = {"games": {"1": _doc(subs)}, "fases": {"1": "playoffs"}, "fechas": {"1": "2026-03-20"},
                   "equipos": ROSTERS}
        ctx = Ctx(league="ncaa", season="2025-26", cfg=_cfg(), main_payload=payload)
        src = NcaaPBP()
        refs = src.games(ctx)
        assert refs[0]["teams"] == ["10", "20"] and refs[0]["phase"] == "playoffs"
        g = src.parse(src.fetch(ctx, refs[0]), refs[0], ctx)
        assert g.has_lineups is subs
        shot = next(e for e in g.events if e.kind == "shot" and e.made)
        assert shot.assister == "h2" and shot.x is not None
        ft = next(e for e in g.events if e.kind == "ft")
        assert ft.t == 2100                               # 2.ª mitad, 5:00 restantes
        res = build(g, 40)
        if subs:
            assert res.segments and abs(res.seconds["h1"] - 2700) < 1      # 40' + 5' de prórroga
        else:
            assert not res.segments and res.shots
