"""NBL: traducción del partido de nbl.com.au al data.json de FIBA LiveStats (to_fls)."""
from bbstats.adapters.nbl import to_fls

H, A = {"id": "h", "name": "Home"}, {"id": "a", "name": "Away"}


def _p(pid, team, **kw):
    base = {"period": "0", "player": {"id": pid, "first_name": pid.upper(), "last_name": "X"}, "team": {"id": team},
            "minutes": "20:00", "starter": True, "points": 0}
    base.update(kw)
    return base


def _a(n, at, team, pid=None, **kw):
    d = {"action_id": n, "action_type": at, "period": 1, "period_type": "regular", "clock": "09:00",
         "team": {"id": team}, "coordinates": {}}
    if pid:
        d["personId"] = pid
    d.update(kw)
    return d


def test_to_fls_basico():
    doc = {"match_status": "complete", "home_team": H, "away_team": A, "home_score": 2, "away_score": 0,
           "player_match_statistics": [_p("p1", "h", points=2, two_points_made=1), _p("q1", "a", minutes=12.5)],
           "team_match_statistics": [{"period": "0", "team": {"id": "h"}, "points": 2}],
           "play_by_play": [
               _a(9, "3pt", "a", "q1", success=False, coordinates={"x": 10, "y": 20}),
               _a(3, "block", "h", "p1"),                       # orden del fichero, no el action_id
               _a(5, "2pt", "h", "p1", success=True, coordinates={"x": 90, "y": 50}),
               _a(4, "assist", "h", "p1"),
               _a(7, "foul", "a", "q1", sub_type="Personal"),
               _a(8, "foul", "h", "p1", sub_type="Drawn"),
               _a(6, "substitution", "a", "q1", sub_type="Out"),
           ]}
    f = to_fls(doc)
    assert f["status"] == "complete"
    p1 = f["tm"]["1"]["pl"]["1"]
    q1 = f["tm"]["2"]["pl"]["1"]
    assert p1["personId"] == "p1" and p1["sPoints"] == 2 and p1["sTwoPointersMade"] == 1
    assert q1["sMinutes"] == "12:30"
    assert p1["sFoulsOn"] == 1 and q1["sBlocksReceived"] == 1
    acts = list(reversed(f["pbp"]))                           # data.json: orden descendente
    assert [a["actionNumber"] for a in acts] == list(range(1, 8))
    assert [a["actionType"] for a in acts] == ["3pt", "block", "2pt", "assist", "foul", "foulon", "substitution"]
    assert acts[3]["previousAction"] == acts[2]["actionNumber"]
    assert acts[6]["subType"] == "out"
    assert f["tm"]["1"]["shot"][0]["x"] == 90 and f["tm"]["1"]["tot_sPoints"] == 2
