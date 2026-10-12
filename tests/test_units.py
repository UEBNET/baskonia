from __future__ import annotations

import math

import pandas as pd
import pytest

from bbstats.metrics import compute_player_metrics, finalize_columns
from bbstats.normalize import canonical_field, complete_counting, map_counting
from bbstats.schema import COLUMN_NAMES
from bbstats.utils import height_to_cm, parse_made_attempted, parse_minutes, to_float


@pytest.mark.parametrize("raw,expected", [
    ("25:30", 25.5), (25.5, 25.5), ("PT25M30.00S", 25.5), ("1:05:30", 65.5), ("", None), ("DNP", None),
])
def test_parse_minutes(raw, expected):
    assert parse_minutes(raw) == expected


def test_to_float_and_pairs():
    assert to_float("55.3%") == 55.3 and to_float("12,5") == 12.5 and to_float("-") is None
    assert parse_made_attempted("5/9") == (5.0, 9.0)
    assert height_to_cm("6-8") == pytest.approx(203.2) and height_to_cm("2.03") == 203.0


def test_aliases_across_sources():
    assert canonical_field("twoPointersMade") == "fg2m"
    assert canonical_field("FG3A") == "fg3a"
    assert canonical_field("sReboundsOffensive") == "oreb"
    assert canonical_field("foulsDrawn") == "pfd"
    assert canonical_field("PLUS_MINUS") == "plus_minus"
    rec = map_counting({"player.code": "X", "minutesPlayed": "100:30", "pointsScored": "40"})
    assert rec == {"min": 100.5, "pts": 40.0}


def test_complete_counting_never_overwrites():
    d = complete_counting({"fg2m": 4, "fg3m": 2, "fg2a": 8, "fg3a": 5, "ftm": 1, "oreb": 1, "dreb": 3})
    assert d["fgm"] == 6 and d["fga"] == 13 and d["reb"] == 4 and d["pts"] == 15
    d = complete_counting({"fgm": 6, "fg3m": 2, "pts": 99})
    assert d["fg2m"] == 4 and d["pts"] == 99


def test_metrics_formulas_simple_case():
    players = pd.DataFrame([
        {"player_id": "a", "team_id": "t", "gp": 1, "min": 40, "pts": 20, "fgm": 7, "fga": 15, "fg3m": 2,
         "fg3a": 5, "ftm": 4, "fta": 5, "oreb": 1, "dreb": 4, "reb": 5, "ast": 3, "stl": 1, "tov": 2,
         "blk": 0, "pf": 2},
    ])
    teams = pd.DataFrame([{"team_id": "t", "team_gp": 1, "team_min": 200, "team_pts": 80, "team_fgm": 30,
                           "team_fga": 70, "team_fg3m": 8, "team_fg3a": 25, "team_ftm": 12, "team_fta": 16,
                           "team_oreb": 10, "team_dreb": 25, "team_reb": 35, "team_ast": 18, "team_stl": 7,
                           "team_tov": 12, "team_blk": 3, "team_pf": 18,
                           "opp_min": 200, "opp_pts": 75, "opp_fgm": 28, "opp_fga": 68, "opp_fg3m": 7,
                           "opp_fg3a": 22, "opp_ftm": 12, "opp_fta": 17, "opp_oreb": 9, "opp_dreb": 26,
                           "opp_reb": 35, "opp_ast": 15, "opp_stl": 6, "opp_tov": 13, "opp_blk": 2, "opp_pf": 17}])
    df = compute_player_metrics(players, teams, 40)
    r = df.iloc[0]
    assert r["ts_pct"] == pytest.approx(100 * 20 / (2 * (15 + 0.44 * 5)))
    assert r["efg_pct"] == pytest.approx(100 * (7 + 1) / 15)
    assert r["usg_pct"] == pytest.approx(100 * (15 + 2.2 + 2) * 40 / (40 * (70 + 0.44 * 16 + 12)))
    assert r["fg2m"] if "fg2m" in r else True
    assert r["game_score"] == pytest.approx(20 + 2.8 - 10.5 - 0.4 + 0.7 + 1.2 + 1 + 2.1 + 0 - 0.8 - 2)
    assert 50 < r["team_pace"] < 100 and math.isfinite(r["ortg"]) and math.isfinite(r["drtg"])
    assert r["min_pct"] == pytest.approx(100.0)
    out = finalize_columns(df)
    assert list(out.columns) == COLUMN_NAMES


def test_zero_minutes_player_kept_with_blanks():
    players = pd.DataFrame([{"player_id": "a", "team_id": "t", "gp": 0, "min": 0, "pts": 0},
                            {"player_id": "b", "team_id": "t", "gp": 1, "min": 10, "pts": 4, "fga": 3}])
    df = finalize_columns(compute_player_metrics(players, pd.DataFrame(), 40))
    assert len(df) == 2 and pd.isna(df.loc[0, "pts_p40"]) and df.loc[1, "pts_p40"] == 16
