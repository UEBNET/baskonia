"""VTB: traducción del partido de Infobasket (GetOnline) al data.json de FIBA LiveStats (to_fls) y calendario."""
from bbstats.adapters.vtb import VTBAdapter, to_fls


def _pl(pid, team, num, **kw):
    base = {"PersonID": pid, "TeamNumber": team, "FirstNameEn": f"F{pid}", "LastNameEn": f"L{pid}",
            "DisplayNumber": str(num), "Seconds": 600, "IsStart": True}
    base.update(kw)
    return base


def _team(n, name, players, **kw):
    t = {"TeamNumber": n, "TeamID": 100 + n, "TeamName": {"CompTeamNameEn": name, "CompTeamShortNameEn": name[:3]},
         "Players": players, "Coach": {"PersonID": 800 + n, "FirstNameEn": "Asst", "LastNameEn": name},
         "Coaches": [{"PersonID": 800 + n, "PosID": 1001, "PlayerNumber": 2, "FirstNameEn": "Asst", "LastNameEn": name},
                     {"PersonID": 900 + n, "PosID": 1000, "PlayerNumber": 1, "FirstNameEn": "Coach", "LastNameEn": name}]}
    t.update(kw)
    return t


# StartID: 1 / 2 = equipos; 10.. = jugadores del 1; 20.. = jugadores del 2
def _starts():
    st = [{"StartID": 1, "TeamNumber": 1, "StartType": 0, "PersonID": 0},
          {"StartID": 2, "TeamNumber": 2, "StartType": 0, "PersonID": 0}]
    st += [{"StartID": 10 + i, "TeamNumber": 1, "StartType": 1, "PersonID": 1000 + i} for i in range(6)]
    st += [{"StartID": 20 + i, "TeamNumber": 2, "StartType": 1, "PersonID": 2000 + i} for i in range(6)]
    return st


def _p(pid, typ, sid, per=1, sec=0, parent=None, order=0, **kw):
    d = {"PlayID": pid, "PlayTypeID": typ, "StartID": sid, "PlayPeriod": per, "PlaySecond": sec,
         "ParentPlayID": parent, "PlaySortOrder": order, "SysStatus": 1}
    d.update(kw)
    return d


def _doc(plays, **kw):
    p1 = [_pl(1000 + i, 1, i, IsStart=i < 5) for i in range(6)]
    p2 = [_pl(2000 + i, 2, i, IsStart=i < 5) for i in range(6)]
    p1[0].update(Points=2, Goal2=1, Shot2=1, PlusMinus=2)
    d = {"GameStatus": 1, "MaxPeriod": 5, "GameDate": "05.10.2026", "OnlineStarts": _starts(),
         "OnlinePeriods": [{"Period": i, "Seconds": 600 if i <= 4 else 300} for i in range(1, 6)],
         "GameTeams": [_team(1, "Home", p1, Score=2, Goal2=1, Shot2=1, TeamOffRebound=1),
                       _team(2, "Away", p2, Score=0)],
         "OnlinePlays": plays}
    d.update(kw)
    return d


def _start(pid, per, team1, team2, sec=0):
    out = [_p(pid, 21, 0, per, sec)]
    for i, s in enumerate([10 + x for x in team1] + [20 + x for x in team2], 1):
        out.append(_p(pid + i, 8, s, per, sec, parent=pid, order=i))
    return out


def test_to_fls_caja_y_jugadas():
    plays = _start(1, 1, range(5), range(5)) + [
        # fallo de 3 del visitante, tapón del local 1 y rebote defensivo del local 2 (hijas del tiro)
        _p(30, 6, 20, 1, 300, PlayX=0, PlayY=70), _p(31, 27, 11, 1, 300, parent=30, order=2),
        _p(32, 28, 12, 1, 300, parent=30, order=3),
        # canasta de 2 del local 0 con asistencia del 3 (anotadas al revés: manda PlaySortOrder)
        _p(41, 25, 13, 1, 450, parent=40, order=2), _p(40, 2, 10, 1, 450, PlayX=-15, PlayY=0),
        # falta en ataque del visitante 1 -> falta + pérdida; el saque lo recibe el local 4
        _p(50, 40, 21, 1, 500), _p(51, 47, 21, 1, 500, parent=50, order=1), _p(52, 50, 14, 1, 500, parent=50, order=2),
        # cambio: entra el visitante 5 por el 0
        _p(60, 7, 0, 1, 600), _p(61, 8, 25, 1, 600, parent=60, order=1), _p(62, 9, 20, 1, 600, parent=60, order=2),
        # falta sobre el local 1 con 2 TL y «asistencia» del local 2: anota uno -> asistencia del TL
        _p(70, 40, 22, 1, 700), _p(71, 52, 11, 1, 700, parent=70, order=1), _p(72, 25, 12, 1, 700, parent=70, order=2),
        _p(73, 4, 11, 1, 700), _p(74, 1, 11, 1, 700),
        # rebote ofensivo de equipo tras un fallo del local
        _p(80, 5, 13, 1, 800), _p(81, 28, 1, 1, 800, parent=80, order=1),
        # reloj, corrección y fin de periodo: fuera
        _p(90, 70, 0, 1, 900), _p(91, 22, 0, 1, 6000),
    ] + _start(100, 2, [0, 1, 2, 3, 5], range(1, 6)) + [
        # prórroga (periodo 5): tiro a 1:00 del final
        *_start(200, 5, [0, 1, 2, 3, 5], range(1, 6)), _p(210, 3, 15, 5, 2400, PlayX=30, PlayY=60),
    ]
    f = to_fls(_doc(plays))
    assert f["status"] == "complete" and f["matchDate"] == "2026-10-05"
    assert f["period"] == 1 and f["periodType"] == "OVERTIME"
    t1, t2 = f["tm"]["1"], f["tm"]["2"]
    assert t1["name"] == "Home" and t1["coach"] == "Coach Home" and t1["coachDetails"]["personId"] == 901
    assert t1["assistcoach1"] == "Asst Home"
    p = t1["pl"]["1"]
    assert p["personId"] == "1000" and p["firstName"] == "F1000" and p["sMinutes"] == "10:00"
    assert p["sPoints"] == 2 and p["sFieldGoalsMade"] == 1 and p["sPlusMinusPoints"] == 2 and p["starter"] == 1
    assert t2["pl"]["1"]["sBlocksReceived"] == 1 and t1["tot_sReboundsTeamOffensive"] == 1
    acts = list(reversed(f["pbp"]))
    assert [a["actionNumber"] for a in acts] == list(range(1, len(acts) + 1))
    seq = [(a["actionType"], a["subType"], a["tno"], a["pno"]) for a in acts]
    i = seq.index(("3pt", "", 2, 1))
    assert seq[i + 1] == ("block", "", 1, 2) and seq[i + 2] == ("rebound", "defensive", 1, 3)
    j = seq.index(("2pt", "", 1, 1))
    assert seq[j + 1] == ("assist", "", 1, 4) and acts[j + 1]["previousAction"] == acts[j]["actionNumber"]
    assert acts[j]["s1"] == 2 and acts[j]["gt"] == "09:15"
    k = seq.index(("foul", "offensive", 2, 2))
    assert seq[k + 1] == ("turnover", "offensive", 2, 2) and seq[k + 2] == ("foulon", "", 1, 5)
    assert ("substitution", "in", 2, 6) in seq and ("substitution", "out", 2, 1) in seq
    ft = [a for a in acts if a["actionType"] == "freethrow"]
    assert [x["success"] for x in ft] == [0, 1]
    ast_ft = [a for a in acts if a["actionType"] == "assist" and a["previousAction"] == ft[1]["actionNumber"]]
    assert len(ast_ft) == 1 and ast_ft[0]["pno"] == 3
    reb = [a for a in acts if a["actionType"] == "rebound" and a["subType"] == "offensive"]
    assert reb[0]["pno"] == 0 and reb[0]["qualifier"] == ["team"]
    assert not any(a["actionType"] in ("timeout",) for a in acts)
    # inicio del 2.º periodo: sólo los cambios respecto a cómo acabó el 1.º (local: entra el 5 por el 4)
    k2 = [x for x in acts if x["period"] == 2 and x["periodType"] == "REGULAR" and x["actionType"] == "substitution"]
    assert {(x["subType"], x["tno"], x["pno"]) for x in k2} == {("out", 1, 5), ("in", 1, 6)}
    ot = [a for a in acts if a["actionType"] == "3pt"][-1]
    assert ot["period"] == 1 and ot["periodType"] == "OVERTIME" and ot["gt"] == "01:00"
    shots = {s["actionNumber"]: s for s in t1["shot"]}
    s2 = shots[acts[j]["actionNumber"]]
    assert s2["x"] == round(15.75 * 100 / 280, 2) and s2["y"] == 40.0 and s2["r"] == 1
    assert f["tm"]["2"]["shot"][0]["x"] == round((15.75 + 70) * 100 / 280, 2)


def test_to_fls_tl_sin_anotar_y_cambio_antes_de_tl():
    plays = _start(1, 1, range(5), range(5)) + [
        # falta con «asistencia» y los dos TL fallados: la asistencia se descarta
        _p(20, 40, 21, 1, 100), _p(21, 52, 11, 1, 100, parent=20, order=1), _p(22, 25, 12, 1, 100, parent=20, order=2),
        _p(23, 4, 11, 1, 100), _p(24, 4, 11, 1, 100),
        # falta sobre el local 0; el cambio que lo saca se teclea antes de sus tiros libres
        _p(30, 40, 21, 1, 200), _p(31, 52, 10, 1, 200, parent=30, order=1),
        _p(32, 7, 0, 1, 200), _p(33, 8, 15, 1, 200, parent=32, order=1), _p(34, 9, 10, 1, 200, parent=32, order=2),
        _p(35, 1, 10, 1, 200), _p(36, 1, 10, 1, 200),
    ]
    f = to_fls(_doc(plays))
    acts = list(reversed(f["pbp"]))
    assert not [a for a in acts if a["actionType"] == "assist"]
    seq = [(a["actionType"], a["subType"], a["pno"]) for a in acts if a["tno"] == 1]
    # por defecto, el orden de anotación (el que sigue el +/- oficial)
    assert seq.index(("substitution", "out", 1)) < seq.index(("freethrow", "", 1))
    f2 = to_fls(_doc(plays), cambios_tras_acciones=True)
    seq2 = [(a["actionType"], a["subType"], a["pno"]) for a in reversed(f2["pbp"]) if a["tno"] == 1]
    assert seq2.index(("substitution", "out", 1)) > max(i for i, s in enumerate(seq2) if s[0] == "freethrow")


def test_to_fls_sin_jugadas_y_titulares():
    d = _doc([])
    for p in d["GameTeams"][0]["Players"]:
        p["IsStart"] = False
    f = to_fls(d)
    assert f["pbp"] == [] and "sBlocksReceived" not in f["tm"]["1"]["pl"]["1"]
    assert sum(p["starter"] for p in f["tm"]["1"]["pl"].values()) == 0       # sin jugadas no hay de dónde sacarlos
    d = _doc(_start(1, 1, [1, 2, 3, 4, 5], range(5)))
    for p in d["GameTeams"][0]["Players"]:
        p["IsStart"] = False
    f = to_fls(d)
    assert [n for n, p in f["tm"]["1"]["pl"].items() if p["starter"]] == ["2", "3", "4", "5", "6"]


class _Resp:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class _Http:
    def __init__(self, routes):
        self.routes, self.urls = routes, []

    def get(self, url, headers=None, **kw):
        self.urls.append(url)
        for k, v in self.routes.items():
            if k in url:
                return _Resp(v)
        raise AssertionError(url)


def test_fetch_fases_y_corte():
    game = _doc(_start(1, 1, range(5), range(5)))
    routes = {
        "CompIssue/500": {"Comps": [{"CompID": 503, "CompType": 0}, {"CompID": 502, "CompType": 10},
                                    {"CompID": 501, "CompType": 0}]},
        "comps=501": [{"GameID": 1, "GameStatus": 1, "GameDate": "01.10.2026", "CompNameEn": "Regular Season"},
                      {"GameID": 2, "GameStatus": 0, "GameDate": "02.10.2026"},
                      {"GameID": 3, "GameStatus": 1, "GameDate": "30.10.2026"}],
        "comps=502": [{"GameID": 4, "GameStatus": 1, "GameDate": "20.10.2026", "CompNameEn": "Play-in. Game 1"}],
        "comps=503": [],
        "GetOnline/": {**game, "VideoID": "<iframe>"},
    }
    ad = VTBAdapter("vtb", {"temporadas": {"2026-27": {"comp_id": 500, "fecha_corte": "2026-10-29"}}})
    http = _Http(routes)
    out = ad.fetch("2026-27", http)
    assert out["fases"] == {"1": "regular", "4": "playoffs"} and out["fechas"]["4"] == "2026-10-20"
    assert set(out["games"]) == {"1", "4"} and "VideoID" not in out["games"]["1"]
    # segunda ejecución: los partidos terminados se reutilizan sin pedirlos
    http2 = _Http(routes)
    out2 = ad.fetch("2026-27", http2, previous_payload=out)
    assert out2["reused_games"] == 2 and not any("GetOnline" in u for u in http2.urls)
    parsed = ad.parse(out, "2026-27")
    assert set(parsed) >= {"regular", "playoffs"}
