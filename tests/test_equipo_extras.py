"""Extras de equipo: tiempos muertos (parcial antes/después, ATO), stops y quinteto inicial, con un partido sintético."""
from bbstats.lineups.equipo_extras import analizar_partido, _agregar
from bbstats.lineups.model import Event, Game
from bbstats.lineups.stints import build


def _partido() -> Game:
    A = [f"a{i}" for i in range(1, 6)]
    B = [f"b{i}" for i in range(1, 6)]
    g = Game(game_id="g1", phase="regular", teams=["A", "B"])
    g.players = {p: {"nombre": p, "team": "A"} for p in A} | {p: {"nombre": p, "team": "B"} for p in B}
    g.starters = {"A": A, "B": B}
    ev = []

    def add(kind, team, player=None, t=0.0, **kw):
        ev.append(Event(order=len(ev) + 1, period=1, t=t, kind=kind, team=team, player=player, **kw))

    add("shot", "B", "b1", 10, value=3, made=True, pts=3)     # B anota 3 (posesión de B)
    add("shot", "A", "a1", 20, value=2, made=False)           # A falla
    add("blk", "B", "b2", 20)                                 # con tapón de B
    add("dreb", "B", "b3", 21)                                # stop de B (tapón)
    add("shot", "B", "b1", 30, value=3, made=True, pts=3)     # B anota 3: parcial 6-0 de B
    add("timeout", "A", None, 31)                             # A pide tiempo muerto
    add("shot", "A", "a2", 40, value=2, made=True, pts=2)     # ATO: 2 puntos
    add("tov", "B", "b4", 50)                                 # pérdida de B
    add("stl", "A", "a3", 51)                                 # robo de A (1 s después)
    add("shot", "A", "a1", 60, value=3, made=True, pts=3)
    g.events = ev
    return g


def test_tiempo_muerto_parcial_y_ato():
    d = analizar_partido(_partido(), 40)
    to = d["A"]["tiempos_muertos"]
    assert len(to) == 1 and d["B"]["tiempos_muertos"] == []
    x = to[0]
    assert x["margen"] == -6 and x["parcial_antes"] == -6 and x["parcial_despues"] == 5 and x["ato_pts"] == 2


def test_stops_y_quinteto_inicial():
    d = analizar_partido(_partido(), 40)
    dfa = d["A"]["defensa"]          # defensa de A: posesiones de B
    assert dfa["pos"] == 3 and dfa["stops"] == 1 and dfa["stop_robo"] == 1
    dfb = d["B"]["defensa"]
    assert dfb["stops"] == 1 and dfb["stop_tapon"] == 1
    assert d["A"]["quinteto_inicial"] == "a1|a2|a3|a4|a5" and d["A"]["gana"] is False
    ag = _agregar([("regular", "g1", d["A"], True)])
    assert ag["regular"]["tiempos_muertos"]["tras_racha"] == 1
    assert ag["total"]["quintetos_iniciales"][0] == {"unidad": "a1|a2|a3|a4|a5", "partidos": 1, "victorias": 0}


def test_stints_ignoran_tiempos_muertos():
    g = _partido()
    con = build(g, 40)
    g.events = [e for e in g.events if e.kind != "timeout"]
    sin = build(g, 40)
    assert con.segments == sin.segments and con.seconds == sin.seconds
