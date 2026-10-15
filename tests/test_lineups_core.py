"""Núcleo de quintetos: tramos, validación y métricas sobre partidos sintéticos de resultado conocido."""
from __future__ import annotations

import random

import numpy as np
import pandas as pd
import pytest

from bbstats.lineups import metrics as M
from bbstats.lineups.model import Event, Game, clock_to_seconds, elapsed, link_assists_by_adjacency
from bbstats.lineups.stints import build

A = [f"a{i}" for i in range(8)]
B = [f"b{i}" for i in range(8)]


def _game(gid="1", star_bonus=0.0, seed=0, phase="regular") -> Game:
    """Partido de 4 cuartos de 10'. Cambio cada 5 minutos: A rota a0..a7, B fijo b0..b4 y b5..b7.
    Cada 20 s ataca un equipo; con `a0` en pista A anota con más probabilidad (star_bonus)."""
    rnd = random.Random(seed)
    g = Game(game_id=gid, phase=phase, teams=["A", "B"], team_names={"A": "Equipo A", "B": "Equipo B"})
    g.players = {p: {"nombre": p.upper(), "team": "A"} for p in A} | {p: {"nombre": p.upper(), "team": "B"} for p in B}
    g.starters = {"A": A[:5], "B": B[:5]}
    evs, order = [], 0
    on = {"A": list(A[:5]), "B": list(B[:5])}

    def add(**kw):
        nonlocal order
        order += 1
        evs.append(Event(order=order, **kw))

    for per in range(1, 5):
        for step in range(30):  # 30 posesiones de 20 s por cuarto
            t = elapsed(per, 600 - step * 20 - 10, 40)
            if step == 15:  # cambio a mitad de cuarto
                for team, pool in (("A", A), ("B", B)):
                    for _ in range(2):  # dos cambios por equipo, en posiciones al azar
                        slot = rnd.randrange(5)
                        out_p = on[team][slot]
                        in_p = [p for p in pool if p not in on[team]][rnd.randrange(3)]
                        add(period=per, t=t, kind="out", team=team, player=out_p)
                        add(period=per, t=t, kind="in", team=team, player=in_p)
                        on[team][slot] = in_p
            team = "A" if step % 2 == 0 else "B"
            shooter = on[team][rnd.randrange(5)]
            prob = 0.5 + (star_bonus if team == "A" and "a0" in on["A"] else 0)
            made = rnd.random() < prob
            ast = on[team][(on[team].index(shooter) + 1) % 5] if made and rnd.random() < 0.6 else None
            add(period=per, t=t, kind="shot", team=team, player=shooter, value=2, made=made, pts=2 if made else 0,
                assister=ast)
            if not made:
                add(period=per, t=t + 1, kind="dreb", team="B" if team == "A" else "A",
                    player=on["B" if team == "A" else "A"][0])
    g.events = evs
    # boxscore "oficial" coherente con lo simulado (para la validación)
    from bbstats.lineups.stints import build as _b
    r = _b(g, 40)
    g.box = {p: {"sec": r.seconds.get(p, 0.0), "pm": r.pm.get(p, 0.0)} for p in A + B}
    return g


def test_clock_helpers():
    assert clock_to_seconds("09:20") == 560 and clock_to_seconds("PT9M2S") == 542 and clock_to_seconds("00:09:34") == 574
    assert elapsed(2, 600, 40) == 600 and elapsed(5, 0, 40) == 2700 and elapsed(1, 0, 48) == 720


def test_segments_and_validation():
    g = _game()
    r = build(g, 40)
    v = r.validation()
    assert v["valido"] and v["dif_min_max_s"] == 0
    assert set(r.anomalies) <= {"quinteto_periodo_arrastrado"}  # jugador sin acciones en un cuarto: se arrastra
    seg = pd.DataFrame(r.segments)
    assert (seg["n_a"] == 5).all() and (seg["n_b"] == 5).all()
    assert seg["sec"].sum() == pytest.approx(2400)
    # minutos por equipo = 5 × 40 minutos
    assert sum(r.seconds[p] for p in A) == pytest.approx(5 * 2400)
    # +/- de los jugadores de A suma 5 × diferencia final
    final = seg["a_pts"].sum() - seg["b_pts"].sum()
    assert sum(r.pm[p] for p in A) == pytest.approx(5 * final)


def test_period_lineup_inference_without_subs_between_periods():
    """Si la fuente no anota cambios entre cuartos (BBL), el quinteto se deduce de quién actúa primero."""
    g = Game(game_id="x", phase="regular", teams=["A", "B"], starters={"A": A[:5], "B": B[:5]})
    o = 0
    for per, la in ((1, A[:5]), (2, A[1:6])):          # a0 deja la pista entre cuartos sin cambio anotado
        for i, p in enumerate(la + B[:5]):
            o += 1
            g.events.append(Event(order=o, period=per, t=elapsed(per, 590 - i, 40), kind="foul_drawn",
                                  team="A" if p in A else "B", player=p))
    r = build(g, 40)
    assert r.seconds["a0"] == pytest.approx(600) and r.seconds["a5"] == pytest.approx(600)
    assert r.seconds["a1"] == pytest.approx(1200) and not r.anomalies


def test_assist_linking_by_adjacency():
    evs = [Event(order=1, period=1, t=10, kind="shot", team="A", player="a1", value=2, made=True, pts=2),
           Event(order=3, period=1, t=11, kind="foul", team="B", player="b1"),
           Event(order=4, period=1, t=30, kind="shot", team="B", player="b2", value=3, made=True, pts=3)]
    left = link_assists_by_adjacency(evs, [(2, "A", "a2"), (5, "B", "b3"), (6, "A", "a4")])
    assert evs[0].assister == "a2" and evs[2].assister == "b3" and left == 1


def _tables(games):
    results = [build(g, 40) for g in games]
    seg = pd.DataFrame([s for r in results for s in r.segments])
    rows = M.team_rows(seg)
    lg = M.league_context(rows, 0.44)
    return results, rows, lg


def test_unit_onoff_and_wowy_consistency():
    results, rows, lg = _tables([_game(str(i), seed=i) for i in range(6)])
    q5 = M.unit_table(rows, 5, lg, 40, 0.44, 300)
    pairs = M.unit_table(rows, 2, lg, 40, 0.44, 300)
    on = M.onoff_table(rows, lg, 40, 0.44, 300)
    team_min = rows.groupby("team_id")["sec"].sum() / 60
    # minutos de quintetos de un equipo = minutos del equipo
    assert q5.groupby("team_id")["min"].sum()["A"] == pytest.approx(team_min["A"])
    # on + off = minutos del equipo
    a = on[on["team_id"] == "A"]
    assert (a["min_on"] + a["min_off"]).round(6).eq(round(team_min["A"], 6)).all()
    # +/- on de un jugador = suma del +/- de sus parejas / 4 (cada minuto suyo aparece en 4 parejas)
    p0 = pairs[(pairs["team_id"] == "A") & pairs["unidad"].str.contains("a1")]
    assert p0["plus_minus"].sum() / 4 == pytest.approx(a.set_index("player_id").loc["a1", "plus_minus_on"])
    w = M.wowy_pairs(rows, pairs, M.on_sums(rows), lg, 40, 0.44, 300)
    tot = pairs["min"] + w["min_a_sin_b"] + w["min_b_sin_a"] + w["min_ninguno"]
    assert np.allclose(tot[pairs["team_id"] == "A"], team_min["A"])


def test_rapm_finds_the_better_player():
    results, rows, lg = _tables([_game(str(i), star_bonus=0.35, seed=i) for i in range(40)])
    rp = M.rapm(rows, 0.44, lam=200).set_index("player_id")
    assert rp.loc["a0", "orapm"] == rp.loc[[p for p in A]]["orapm"].max()
    assert rp.loc["a0", "orapm"] > 5


def test_assist_network():
    results, rows, lg = _tables([_game(str(i), seed=i) for i in range(5)])
    ast = pd.DataFrame([x for r in results for x in r.assists])
    fgm = pd.Series({p: sum(r.player_events.get(p, {}).get("shot_made", 0) for r in results) for p in A + B})
    pairs = M.unit_table(rows, 2, lg, 40, 0.44, 300)
    con, net = M.assist_tables(ast, fgm, pairs[["team_id", "unidad", "min"]])
    assert con["ast"].sum() == len(ast)
    assert net["pagerank_asistencias"].groupby(net["team_id"]).sum().round(6).eq(1).all()
    assert (net["pct_canastas_asistidas"].dropna() <= 100).all()


def test_garbage_time_rule():
    from bbstats.lineups.stints import _garbage
    assert _garbage(4, 0.9, 26, 2) and not _garbage(4, 0.9, 24, 2)
    assert _garbage(4, 0.6, -20, 0) and _garbage(4, 0.3, 10, 1)
    assert not _garbage(4, 0.3, 30, 3)          # demasiados titulares en pista
    assert not _garbage(3, 0.1, 40, 0) and not _garbage(5, 0.1, 40, 0)


def test_luck_adjustment_is_neutral_for_the_whole_league():
    results, rows, lg = _tables([_game(str(i), seed=i) for i in range(6)])
    s = rows[M.SUM_COLS].sum().to_frame().T
    m = M.rate_metrics(s, lg, 40, 0.44, 300)
    assert m["drtg_suerte"].iloc[0] == pytest.approx(m["drtg"].iloc[0])
    assert m["min_clutch"].iloc[0] >= 0 and m["min_basura"].iloc[0] >= 0


def test_rotation_and_team_tables():
    games = [_game(str(i), seed=i) for i in range(6)]
    results, rows, lg = _tables(games)
    rot = M.rotation_table(rows).set_index("player_id")
    assert (rot.loc[A[:5], "titular_partidos"] == 6).all() and rot.loc["a5", "titular_partidos"] == 0
    pct = rot[[c for c in rot.columns if c.startswith("pct_min_")]].sum(axis=1)
    assert np.allclose(pct, 100)
    assert (rot["relevos_por_partido"] >= 1).all()
    q5 = M.unit_table(rows, 5, lg, 40, 0.44, 300)
    pl = M.onoff_table(rows, lg, 40, 0.44, 300)
    eq = M.team_table(rows, q5, pl, lg, 40, 0.44, 300, {}).set_index("team_id")
    assert eq.loc["A", "partidos_quinteto_titular"] == 6 and eq.loc["A", "quintetos_titulares_distintos"] == 1
    assert eq.loc["A", "net_rtg"] == pytest.approx(-eq.loc["B", "net_rtg"], abs=1e-9)
    assert 2000 / 3 <= eq.loc["A", "hhi_minutos"] <= 2000          # 8 jugadores: entre 1/8 y 1/5
    exp = M.expected_net(rows, pd.Series({p: 0.0 for p in A + B}), 0.44, 2)
    assert (exp["net_esperado"] == 0).all()


def test_incoherent_official_plus_minus_is_ignored():
    g = _game()
    for p in A[:3]:
        g.box[p]["pm"] += 7            # la suma del equipo deja de ser ±5 × diferencia
    v = build(g, 40).validation()
    assert v["valido"] and not v["pm_oficial_coherente"] and "incoherente" in v["notas"]
    v2 = build(_game(), 40).validation()
    assert v2["pm_oficial_coherente"]
