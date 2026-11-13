"""Capa Federación Vasca (bbstats.esf): fases, divisiones, zonas de tiro, jugada a jugada y decodificación de la API.

Partido sintético en el formato real de la fuente (acta `getJsonWithMatchStats` + cronología `getJsonWithMatchMoves`).
"""
import base64
import json

import pandas as pd

from bbstats.esf.cliente import _decode, urls_de_pagina
from bbstats.esf.construir import asignar_division, construir_liga, fase_slug, fase_tipo, unidades
from bbstats.esf.eventos import procesar_partido, zona_tiro
from bbstats.esf.pipeline import load_config
from bbstats.lineups import stints


def _mv(i, team, actor, idm, mn, sc, per=1, score="0-0", lic=None, team_action=False, uuid=None):
    return {"idTeam": team, "actorName": f"J{actor}", "actorId": actor, "actorShirtNumber": str(actor % 100), "idMove": idm,
            "move": str(idm), "min": mn, "sec": sc, "period": per, "score": score, "teamAction": team_action,
            "timestamp": f"2026{i:010d}", "licenseId": lic or actor + 1000, "eventUuid": uuid or f"u{i}"}


def partido_sintetico():
    """Local 1 (jugadores 11-15, banquillo 16) contra visitante 2 (21-25). Un cambio, 6 canastas, rebotes, robo."""
    A, B = 1, 2
    moves = [
        _mv(0, A, 11, 93, 9, 50, uuid="s1"),                    # 2-0 canasta de 2
        _mv(1, B, 21, 98, 9, 30, uuid="s2"),                    # fallo de 3
        _mv(2, A, 12, 104, 9, 28),                              # rebote defensivo local
        _mv(3, A, 12, 94, 9, 22, uuid="s3"),                    # 5-0 triple al contraataque (6 s)
        _mv(4, B, 22, 106, 9, 0),                               # pérdida visitante
        _mv(5, A, 13, 103, 8, 59),                              # robo local
        _mv(6, A, 13, 97, 8, 50, uuid="s4"),                    # fallo de 2
        _mv(7, A, 14, 101, 8, 49),                              # rebote ofensivo
        _mv(8, A, 14, 93, 8, 47, uuid="s5"),                    # 7-0 segunda oportunidad
        _mv(9, B, 23, 159, 8, 47),                              # falta (sin tiros)
        _mv(10, A, 15, 115, 8, 40),                             # cambio: sale 15
        _mv(11, A, 16, 112, 8, 40),                             # entra 16
        _mv(12, B, 24, 93, 8, 30, uuid="s6"),                   # 7-2
        _mv(13, A, 16, 110, 8, 10),                             # falta recibida
        _mv(14, B, 25, 161, 8, 10),                             # falta personal con 2 TL
        _mv(15, A, 16, 92, 8, 10),                              # TL anotado
        _mv(16, A, 16, 96, 8, 10),                              # TL fallado
        _mv(17, B, 25, 104, 8, 9),                              # rebote defensivo visitante
        _mv(0, 0, 0, 116, 0, 0, team_action=True),              # fin de periodo
    ]
    def pdata(**k):
        base = {"score": 0, "shotsOfOneSuccessful": 0, "shotsOfOneAttempted": 0, "shotsOfTwoSuccessful": 0,
                "shotsOfTwoAttempted": 0, "shotsOfThreeSuccessful": 0, "shotsOfThreeAttempted": 0, "offensiveRebound": 0,
                "defensiveRebound": 0, "rebounds": 0, "assists": 0, "steals": 0, "lost": 0, "block": 0, "blockReceived": 0,
                "faults": 0, "faultReceived": 0, "dunk": 0, "valoration": 0}
        base.update(k)
        return base
    shots_local = {"shootingOfTwoSuccessfulPoint": [{"eventUuid": "s1", "xnormalize": 6.0, "ynormalize": 50.0},
                                                    {"eventUuid": "s5", "xnormalize": 16.0, "ynormalize": 46.0}],
                   "shootingOfThreeSuccessfulPoint": [{"eventUuid": "s3", "xnormalize": 30.0, "ynormalize": 15.0}],
                   "shootingOfTwoFailedPoint": [{"eventUuid": "s4", "xnormalize": 18.0, "ynormalize": 80.0}]}
    mins = {15: 1, 16: 9}     # el acta redondea a minutos enteros (el 15 sale a 8:40, entra el 16)
    pl_a = [{"actorId": a, "uuid": f"p{a}", "name": f"J{a}", "dorsal": str(a % 100), "starting": a <= 15,
             "timePlayed": mins.get(a, 10), "inOut": 0, "data": pdata()} for a in (11, 12, 13, 14, 15, 16)]
    pl_b = [{"actorId": a, "uuid": f"p{a}", "name": f"J{a}", "dorsal": str(a % 100), "starting": True,
             "timePlayed": 10, "inOut": 0, "data": pdata()} for a in (21, 22, 23, 24, 25)]
    pl_a[0]["data"] = pdata(score=2, shotsOfTwoSuccessful=1, shotsOfTwoAttempted=1)
    pl_a[5]["data"] = pdata(score=1, shotsOfOneSuccessful=1, shotsOfOneAttempted=2, faultReceived=1)
    acta = {"localId": 101, "visitId": 102, "periodDuration": 10, "periodDurationList": [10, 10, 10, 10],
            "teams": [{"teamIdIntern": A, "teamIdExtern": 101, "name": "LOCAL", "shortName": "LOC",
                       "data": {**pdata(score=8), **shots_local}, "players": pl_a},
                      {"teamIdIntern": B, "teamIdExtern": 102, "name": "VISITA", "shortName": "VIS",
                       "data": pdata(score=2), "players": pl_b}]}
    return acta, moves


def test_fase_slug_y_tipo():
    reglas = load_config()["fases_tipo"]
    assert fase_slug("LVJM-Primera Fase") == "primera_fase"
    assert fase_slug("1ª Mas-Liga Regular") == "liga_regular"
    assert fase_slug("LVCM-Fase Clasificaion") == "fase_clasificacion"
    assert fase_slug("CVNRJM-Prim. Fase") == "primera_fase"
    assert fase_slug("Prim.Div.Mas") == "liga_regular"
    assert fase_slug("Segunda Fase LVCM") == "segunda_fase"
    assert fase_tipo("1ª Mas-Fase Clasifiacion", reglas) == "clasificacion"
    assert fase_tipo("LVJM-Copa", reglas) == "copa"


def test_divisiones_a1_a2_y_cruce():
    cfg = load_config()
    rows = [  # primera fase (A1): 1 y 2 · segunda fase A-1: 1 y 2 · A-2: 3 y 4 · clasificación: 2 contra 3 (cruce), 3 contra 4 (A2)
        ("g1", "primera_fase", "Unico", "2025-10-01", "1", "2"), ("g2", "segunda_fase", "A-1", "2026-01-10", "1", "2"),
        ("g3", "segunda_fase", "GRUPO A-2", "2026-01-10", "3", "4"), ("g4", "fase_clasificacion", "Unico", "2026-03-01", "2", "3"),
        ("g5", "fase_clasificacion", "Unico", "2026-03-02", "3", "4")]
    df = pd.DataFrame(rows, columns=["game_id", "fase", "grupo", "fecha", "local_id", "visitante_id"])
    d = asignar_division(df, cfg["reglas_division"], True)
    assert list(d) == ["A1", "A1", "A2", "cruce", "A2"]
    assert set(asignar_division(df, cfg["reglas_division"], False)) == {"única"}
    df["division"], df["jugado"], df["fase_orden"] = d, True, [1, 2, 2, 3, 3]
    u = {(x["fase"], x["division"]) for x in unidades(df, True)}
    assert {("total", "todas"), ("total_a1", "A1"), ("total_a2", "A2"), ("segunda_fase", "A2"), ("fase_clasificacion", "cruce")} <= u


def test_zonas_de_tiro():
    assert zona_tiro(6.0, 50.0, 2)[0] == "aro"            # 1,68 m de la línea de fondo, centrado
    assert zona_tiro(16.0, 46.0, 2)[0] == "pintura"
    assert zona_tiro(30.0, 85.0, 2)[0] == "media_distancia"
    assert zona_tiro(5.0, 3.0, 3)[0] == "triple_esquina"
    assert zona_tiro(35.0, 50.0, 3)[0] == "triple_frontal"
    assert zona_tiro(94.0, 50.0, 2)[0] == "aro"           # la otra canasta (simetría)


def test_partido_jugada_a_jugada_cuadra_con_acta():
    acta, moves = partido_sintetico()
    pr = procesar_partido("1", "primera_fase", acta, moves, "2025-10-01")
    l11, l12, l14, l16 = (pr.lineas[f"p{a}"] for a in (11, 12, 14, 16))
    assert l11["pts"] == 2 and l11["fga"] == 1
    assert l12["pts"] == 3 and l12["fg3m"] == 1 and l12["dreb"] == 1
    assert l12["pts_fastbreak"] == 3                   # triple 6 s después del rebote defensivo
    assert l14["pts_2ndchance"] == 2 and l14["oreb"] == 1
    assert l16["ftm"] == 1 and l16["fta"] == 2 and l16["pfd"] == 1
    assert pr.lineas["p25"]["pf"] == 1 and pr.lineas["p25"]["pf_tiro"] == 1
    assert pr.registra["ast"] is False                 # la mesa no registra asistencias: no se inventan ceros
    zonas = {t["player_id"]: t["zona"] for t in pr.tiros}
    assert zonas["p11"] == "aro" and zonas["p12"] == "triple_frontal"
    # quintetos: el cambio 15 -> 16 se aplica y el +/- se reconstruye
    gr = stints.build(pr.game, pr.game_min)
    assert gr.pm["p16"] == -1 and gr.pm["p15"] == 7 and gr.pm["p21"] == -6


def test_construir_liga_sin_red():
    acta, moves = partido_sintetico()
    cfg = load_config()
    match = {"idMatch": "1", "universallyid": "x", "nameCompetition": "LVJM-Primera Fase", "nameGroup": "Unico",
             "numMatchDay": "1", "matchDay": "2025-10-01 10:00:00", "idLocalTeam": "101", "nameLocalTeam": "LOCAL",
             "idVisitorTeam": "102", "nameVisitorTeam": "VISITA", "localScore": "8", "visitorScore": "2",
             "idCategorySigned": "555", "nameLocalTeamOrganization": "CLUB L", "nameVisitorTeamOrganization": "CLUB V"}
    payload = {"categorias": {"555": {"categoryRegisteredName": "Liga Vasca Jun Masc."}}, "grupos": {"9": {}},
               "calendario": {"9": {"rounds": {"1": {"matches": {"1": match}}}}},
               "games": {"1": {"universallyid": "x", "acta": acta, "jugadas": moves}}, "equipos": {}}
    t = construir_liga("esf_jun", cfg["ligas"]["esf_jun"], cfg, "2025-26", payload)
    j = t["jugadores"]
    assert set(j["fase"]) == {"primera_fase", "total", "total_a1"}
    assert set(j["division"]) == {"A1", "todas"}
    tot = j[j["fase"] == "total"].set_index("player_id")
    assert tot.loc["p12", "pts"] == 3 and pd.isna(tot.loc["p12", "ast"])   # no registrado -> vacío, nunca 0
    assert tot["game_score"].notna().all() and tot["usg_pct"].notna().any() and not tot["registra_asistencias"].any()
    assert list(t["partidos"]["division"]) == ["A1"]


def test_decodificacion_api_y_urls():
    doc = {"result": "OK", "errorCode": 0, "messageData": [1, 2]}
    assert _decode(json.dumps(base64.b64encode(json.dumps(doc).encode()).decode())) == doc
    html = 'var owbasket = {"owbasket-apis":[{"esb":{"url":"https:\\/\\/esb.example\\/esf\\/1\\/K"},"msstats":{"url":"https://ms.example/v1"},"fede":{"url":"esf"}}]};'
    u = urls_de_pagina(html)
    assert u == {"esb": "https://esb.example/esf/1/K", "msstats": "https://ms.example/v1", "fede": "esf"}
