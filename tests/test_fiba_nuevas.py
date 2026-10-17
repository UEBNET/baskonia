"""Ligas nuevas: BCL / FIBA Europe Cup (fiba.basketball) y BSL / GBL (FIBA LiveStats), con documentos sintéticos.

Un mismo partido sintético en los dos formatos: el equipo A cambia a su 5.º jugador por el 6.º a falta de 5:00
del 2.º cuarto; el B juega 40 minutos con sus cinco titulares. Minutos y +/- del boxscore son los exactos, así
que la reconstrucción de tramos debe cuadrar al segundo.
"""
from __future__ import annotations

import json

from bbstats.adapters.fiba_livestats import (FibaLiveStatsAdapter, compress_ids, expand_ids, norm, parse_fiba_game,
                                            phase_map, season_teams)
from bbstats.adapters.fiba_web import FibaWebAdapter, page_doc, parse_game, round_phase, schedule_games
from bbstats.lineups.sources.base import Ctx
from bbstats.lineups.sources.fiba_livestats import FibaLiveStatsPBP
from bbstats.lineups.sources.fiba_web import FibaWebPBP, lector_entrenadores
from bbstats.lineups.stints import build
from bbstats.raw_store import RawStore

# (periodo, reloj restante, equipo A|B, jugador 1-6, acción, extra)
SCRIPT = [
    (1, "9:00", "A", 1, "2pt", True), (1, "9:00", "A", 2, "assist", None),
    (2, "5:00", "A", 5, "out", None), (2, "5:00", "A", 6, "in", None),
    (2, "3:00", "B", 1, "3pt", True),
    (3, "5:00", "A", 6, "3pt", True), (3, "5:00", "A", 1, "assist", None),
    (4, "1:00", "B", 2, "2pt", False), (4, "0:59", "A", 3, "rebound", "defensive"),
    (4, "0:30", "B", 3, "foul", None), (4, "0:30", "A", 1, "freethrow", True),
]
MIN = {"A": {1: "40:00", 2: "40:00", 3: "40:00", 4: "40:00", 5: "15:00", 6: "25:00"},
       "B": {1: "40:00", 2: "40:00", 3: "40:00", 4: "40:00", 5: "40:00", 6: "0:00"}}
PM = {"A": {1: 3, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1}, "B": {i: (-3 if i <= 5 else 0) for i in range(1, 7)}}
PTS = {"A": {1: 3, 6: 3}, "B": {1: 3}}


def _pname(team, i):
    return ("Ana" if team == "A" else "Bea") + str(i), ("Alfa" if team == "A" else "Beta") + str(i)


# ------------------------------------------------------------------ FIBA LiveStats (data.json)
def livestats_doc(name_a="Equipo Alfa", name_b="Equipo Beta", s1=6, s2=3) -> dict:
    tm = {}
    for k, team, name in (("1", "A", name_a), ("2", "B", name_b)):
        pl = {}
        for i in range(1, 7):
            first, fam = _pname(team, i)
            pl[str(i)] = {"firstName": first, "familyName": fam, "internationalFirstName": first,
                          "internationalFamilyName": fam, "name": f"{first[0]}. {fam}", "shirtNumber": str(i),
                          "starter": 1 if i <= 5 else 0, "sMinutes": MIN[team][i], "sPlusMinusPoints": PM[team][i],
                          "sPoints": PTS[team].get(i, 0), "sReboundsDefensive": 1 if (team, i) == ("A", 3) else 0}
        tm[k] = {"name": name, "code": name[:3].upper(), "score": s1 if k == "1" else s2, "pl": pl,
                 "coach": f"Coach {team}", "coachDetails": {"firstName": "Coach", "familyName": team},
                 "tot_sPoints": s1 if k == "1" else s2, "tot_sFieldGoalsMade": 2 if k == "1" else 1,
                 "tot_sFieldGoalsAttempted": 2 if k == "1" else 2, "shot": []}
    pbp, n = [], 0
    for per, clock, team, i, act, extra in SCRIPT:
        n += 1
        k = "1" if team == "A" else "2"
        e = {"actionNumber": n, "period": per, "periodType": "REGULAR", "gt": f"0{clock}" if len(clock) == 4 else clock,
             "tno": int(k), "pno": i, "actionType": act, "subType": "", "success": 1, "previousAction": "",
             "qualifier": []}
        if act in ("2pt", "3pt"):
            e["success"] = 1 if extra else 0
            tm[k]["shot"].append({"actionNumber": n, "x": 10.0, "y": 50.0, "r": e["success"]})
        elif act == "assist":
            e["previousAction"] = str(n - 1)
        elif act in ("in", "out"):
            e["actionType"], e["subType"] = "substitution", act
        elif act == "rebound":
            e["subType"] = extra
        elif act == "freethrow":
            e["subType"] = "1of1"
        elif act == "foul":
            e["subType"] = "personal"
        pbp.append(e)
    n += 1
    pbp.append({"actionNumber": n, "period": 4, "gt": "00:00", "tno": 0, "pno": 0, "actionType": "game",
                "subType": "end", "success": 1, "qualifier": []})
    return {"clock": "00:00", "period": 4, "tm": tm, "pbp": list(reversed(pbp))}


def test_livestats_box_and_lineups():
    doc = livestats_doc()
    g = parse_fiba_game("101", doc, "regular")
    a = g["teams"][0]
    assert g["final"] and a["team_id"] == "equipo-alfa" and a["totals"]["pts"] == 6
    assert {p["player_id"] for p in a["players"]} >= {"alfa1-ana1", "alfa6-ana6"}
    assert next(p for p in a["players"] if p["player_id"] == "alfa5-ana5")["min"] == 15
    ctx = Ctx("gbl", "2026-27", {"minutos_partido": 40}, main_payload={"games": {"101": doc}})
    src = FibaLiveStatsPBP()
    ref = src.games(ctx)[0]
    assert ref["phase"] == "regular" and ref["teams"] == ["equipo-alfa", "equipo-beta"]
    game = src.parse(src.fetch(ctx, ref), ref, ctx)
    shot = next(e for e in game.events if e.kind == "shot" and e.player == "alfa1-ana1")
    assert shot.assister == "alfa2-ana2" and shot.x == 10.0
    v = build(game, 40).validation()
    assert v["con_quintetos"] and v["valido"] and v["dif_min_max_s"] == 0 and v["dif_pm_max"] == 0


def test_livestats_overtime_period():
    doc = livestats_doc()
    doc["pbp"].insert(0, {"actionNumber": 99, "period": 1, "periodType": "OVERTIME", "gt": "04:00", "tno": 1,
                          "pno": 1, "actionType": "turnover", "subType": "badpass", "success": 1, "qualifier": []})
    ctx = Ctx("gbl", "2026-27", {"minutos_partido": 40}, main_payload={"games": {"101": doc}})
    src = FibaLiveStatsPBP()
    ref = src.games(ctx)[0]
    g = src.parse(src.fetch(ctx, ref), ref, ctx)
    assert max(e.period for e in g.events) == 5


def test_season_teams_merges_variants_by_roster():
    d1 = livestats_doc("Δόξα Λευκάδας", "Equipo Beta")
    d2 = livestats_doc("Equipo Beta", "DOXA LEFKADAS ELABET")
    # en d2 el equipo B (visitante) son los jugadores de "Δόξα Λευκάδας": se intercambian plantillas
    d2["tm"]["1"]["pl"], d2["tm"]["2"]["pl"] = d1["tm"]["2"]["pl"], d1["tm"]["1"]["pl"]
    t = season_teams({"1": d1, "2": d2})
    assert t[("1", "1")][0] == t[("2", "2")][0] == "doxa-leykadas"   # el nombre que pone el propio club (local)
    assert norm("ΟΛΥΜΠΙΑΚΟΣ") == "olympiakos" and norm("TÜRK TELEKOM ") == "turk telekom"


def test_phase_map_playoffs_only_top_teams():
    docs, fases = {}, {}
    names = ["T1", "T2", "T3"]
    n = 0
    for a in names:
        for b in names:
            if a != b:
                n += 1
                s1, s2 = (90, 80) if names.index(a) < names.index(b) else (80, 90)
                d = livestats_doc(a, b, s1, s2)
                for k, tn in (("1", a), ("2", b)):     # plantillas propias por equipo
                    for p in d["tm"][k]["pl"].values():
                        p["familyName"] = p["internationalFamilyName"] = tn + p["familyName"]
                docs[str(n)], fases[str(n)] = d, "regular"
    for mid, (a, b) in (("50", ("T1", "T2")), ("51", ("T3", "T2"))):
        d = livestats_doc(a, b)
        for k, tn in (("1", a), ("2", b)):
            for p in d["tm"][k]["pl"].values():
                p["familyName"] = p["internationalFamilyName"] = tn + p["familyName"]
        docs[mid], fases[mid] = d, "playoffs"
    teams = season_teams(docs)
    ph = phase_map({"fases": fases}, docs, teams, {"plazas_playoffs": 2}, "2025-26")
    assert ph["50"] == "playoffs" and ph["51"] == "excluida" and ph["1"] == "regular"


def test_ids_compress_expand():
    rng, excl = compress_ids([5, 10, 11, 13, 14, 40])
    assert rng == [5, [10, 14], 40] and excl == [12]
    assert [i for i in expand_ids(rng) if i not in excl] == [5, 10, 11, 13, 14, 40]


class FakeResp:
    def __init__(self, status, body, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.text = body if isinstance(body, str) else json.dumps(body)

    def json(self):
        return self._body if not isinstance(self._body, str) else json.loads(self._body)


class FakeHttp:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, params=None, headers=None, ok_status=()):
        self.calls.append(url)
        r = self.routes.get(url)
        if r is None:
            return FakeResp(404, "")
        if headers and headers.get("Range"):
            return FakeResp(206, json.dumps(r)[:450])
        return FakeResp(200, r, {"Last-Modified": "Sat, 03 Oct 2026 20:00:00 GMT"})

    def get_text(self, url, params=None, headers=None):
        self.calls.append(url)
        return self.routes[url]

    def request_log(self):
        return []


def test_livestats_adapter_discovery_and_incremental(tmp_path):
    url = "https://fibalivestats.dcd.shared.geniussports.com/data/{}/data.json"
    routes = {url.format(1000): livestats_doc(), url.format(1001): livestats_doc("Otra Liga", "Ajeno"),
              url.format(1002): livestats_doc("Equipo Beta", "Equipo Alfa", 70, 60)}
    d = routes[url.format(1002)]["tm"]
    d["1"]["pl"], d["2"]["pl"] = d["2"]["pl"], d["1"]["pl"]      # Beta en casa con su plantilla
    cfg = {"temporadas": {"2026-27": {"equipos": ["Equipo Alfa", "Equipo Beta"],
                                      "ventanas": {"regular": [[999, 1003]]}}}}
    ad = FibaLiveStatsAdapter("gbl", cfg)
    ad.store = RawStore(tmp_path, compress=True)
    payload = ad.fetch("2026-27", FakeHttp(routes))
    assert sorted(payload["games"]) == ["1000", "1002"] and payload["incremental"]
    assert ad.config_updates["temporadas"]["2026-27"]["partidos"]["regular"] == [[1000, 1002]]
    assert ad.config_updates["temporadas"]["2026-27"]["excluir"] == [1001]
    parsed = ad.parse(payload, "2026-27")
    assert {t["team_id"] for t in parsed["regular"].teams} == {"equipo-alfa", "equipo-beta"}
    # segunda ejecución con los partidos ya en config: reutiliza todo
    cfg2 = {"temporadas": {"2026-27": {"partidos": {"regular": [[1000, 1002]]}, "excluir": [1001]}}}
    ad2 = FibaLiveStatsAdapter("gbl", cfg2)
    p2 = ad2.fetch("2026-27", FakeHttp(routes), payload)
    assert p2["games"] == {} and p2["reused_games"] == 2


# ------------------------------------------------------------------ fiba.basketball (BCL / FIBA Europe Cup)
ORG = {"A": 101, "B": 202}
AC = {"2pt": "P2", "3pt": "P3", "freethrow": "FT", "assist": "ASS", "rebound": "REB", "foul": "FOUL"}


def web_page(game_id=5001, final=True) -> dict:
    roster = {t: [{"personId": ORG[t] * 100 + i, "firstName": _pname(t, i)[0], "lastName": _pname(t, i)[1],
                   "uniformNumber": str(i), "position": "G"} for i in range(1, 7)] for t in "AB"}
    c = []
    for t in "AB":
        ch = [{"Id": f"P_{ORG[t] * 100 + i}", "Stats": {"TP": MIN[t][i], "PM": PM[t][i], "Starter": i <= 5,
                                                         "HasPlayed": MIN[t][i] != "0:00",
                                                         "PTS": PTS[t].get(i, 0)}} for i in range(1, 7)]
        c.append({"Id": f"T_{ORG[t]}", "Score": 6 if t == "A" else 3, "Children": ch,
                  "Stats": {"PTS": 6 if t == "A" else 3, "A_PIP": 2 if t == "A" else 0}})
    items = {f"Q{q}": {"name": f"Q{q}", "items": []} for q in range(1, 5)}
    order = 0
    for per, clock, team, i, act, extra in SCRIPT:
        order += 1000
        a = {"act": "x", "Time": clock, "SA": 0, "SB": 0, "oId": ORG[team], "pId": ORG[team] * 100 + i,
             "Id": str(order // 1000), "order": order}
        if act in ("in", "out"):
            a.update(ac="SUBST", txt="Sub-In" if act == "in" else "Sub-Out", **{"in": act.upper()})
        else:
            a["ac"] = AC[act]
            if act in ("2pt", "3pt", "freethrow"):
                a.update(made=bool(extra), pts=int(act[0]) if act != "freethrow" else 1, x=140, y=60)
            if act == "rebound":
                a["txt"] = f"{extra} rebound"
        items[f"Q{per}"]["items"].append(a)
    game = {"gameId": game_id, "statusCode": "VALID" if final else "INIT", "teamAScore": 6 if final else None,
            "teamBScore": 3, "gameDateTimeUTC": "2026-10-06T16:30:00",
            "teamA": {"organisationId": ORG["A"], "code": "AAA", "shortName": "Alfa"},
            "teamB": {"organisationId": ORG["B"], "code": "BBB", "shortName": "Beta"},
            "round": {"roundCode": "RS", "roundName": "Regular Season", "roundType": "G"},
            "competition": {"competitionId": 209123}}
    page = {"technicalName": "x", "pageStatus": "AFTER", "game": game, "playByPlay": {"items": items},
            "playersTeamA": roster["A"], "playersTeamB": roster["B"], "gameDetails": {"c": c},
            "teamAScore": game["teamAScore"], "teamBScore": 3}
    staff = {"staffA": [{"personId": 9, "firstName": "Carla", "lastName": "Coach", "function": "Head Coach",
                         "isHeadCoach": 1}], "staffB": []}
    return {"page": page, "staff": staff}


def _html(*objs) -> str:
    """HTML con el flujo RSC de Next.js (self.__next_f.push) que contiene los objetos."""
    text = "".join(f'9:["$","x",null,{json.dumps(o, separators=(",", ":"))}]\n' for o in objs)
    return "<html><script>self.__next_f.push([1," + json.dumps(text) + "])</script></html>"


def test_fiba_web_page_extraction_and_box():
    doc = web_page()
    html = _html({"sidebar": "$L1", **doc["page"], "children": []}, {"game": doc["page"]["game"], **doc["staff"]})
    got = page_doc(html)
    assert got["page"]["game"]["gameId"] == 5001 and got["staff"]["staffA"][0]["lastName"] == "Coach"
    g = parse_game(got, "regular")
    a, b = g["teams"]
    assert a["team_id"] == "101" and a["totals"]["pts"] == 6 and a["totals"]["pts_paint"] == 2
    assert next(p for p in a["players"] if p["player_id"] == "10105")["min"] == 15
    assert next(p for p in b["players"] if p["player_id"] == "20206")["min"] == 0
    assert round_phase({"roundCode": "Q", "roundType": "NG"}) is None
    assert round_phase({"roundCode": "Play-ins", "roundType": "NG"}) == "playoffs"
    assert round_phase({"roundCode": "R16", "roundType": "G"}) == "regular"


def test_fiba_web_lineups_and_coaches():
    doc = web_page()
    ctx = Ctx("bcl", "2026-27", {"minutos_partido": 40},
              main_payload={"calendario": [doc["page"]["game"]], "games": {"5001": doc}})
    src = FibaWebPBP()
    ref = src.games(ctx)[0]
    game = src.parse(src.fetch(ctx, ref), ref, ctx)
    shot = next(e for e in game.events if e.kind == "shot" and e.player == "10101")
    assert shot.assister == "10102" and shot.x == 140
    v = build(game, 40).validation()
    assert v["valido"] and v["dif_min_max_s"] == 0 and v["dif_pm_max"] == 0
    co = lector_entrenadores({"docs": doc, "ref": ref}, None)
    assert co["lados"][0]["entrenador"] == "Carla Coach" and co["lados"][1]["entrenador"] is None


def test_fiba_web_adapter_incremental(tmp_path):
    done, pending = web_page(5001), web_page(5002, final=False)
    sched = _html({"games": [done["page"]["game"], pending["page"]["game"]]})
    cfg = {"ruta_historia": "112-x", "temporadas": {"2026-27": {"competition_id": 209123}},
           "partidos_por_paquete": 1}
    routes = {"https://www.fiba.basketball/en/history/112-x/209123/games": sched,
              "https://www.fiba.basketball/en/games/5001": _html({**done["page"]}, {"game": {}, **done["staff"]})}
    assert len(schedule_games(sched, 209123)) == 2
    store = RawStore(tmp_path, compress=True)
    ad = FibaWebAdapter("bcl", cfg)
    ad.store = store
    payload = ad.fetch("2026-27", FakeHttp(routes))
    # partidos_por_paquete = 1: el partido descargado va a un paquete parcial; el final sólo trae el calendario
    assert payload["games"] == {} and payload["partidos_nuevos"] == 1
    store.save("bcl", "2026-27", {"fecha_extraccion_stamp": "20991231T000000Z"}, payload)
    _, merged = store.load_season("bcl", "2026-27")
    assert list(merged["payload"]["games"]) == ["5001"]
    parsed = ad.parse(merged["payload"], "2026-27")
    assert parsed["regular"].notes[-1] == "1 partidos agregados"
    again = FibaWebAdapter("bcl", cfg).fetch("2026-27", FakeHttp(routes), merged["payload"])
    assert again["reused_games"] == 1 and again["partidos_nuevos"] == 0
