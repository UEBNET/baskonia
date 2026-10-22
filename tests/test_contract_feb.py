"""FEB (Primera, Segunda y Tercera FEB): adaptador, jugada a jugada (formatos estructurado y texto), posesiones,
contrato de datos y correspondencia de jugadores entre ligas. Todo con datos sintéticos, sin red."""
from __future__ import annotations

import copy
import json
from collections import Counter

import numpy as np
import pandas as pd
import pytest

from bbmodel import crosswalk as CW
from bbstats.adapters.feb import (FebAdapter, form_fields, game_rows, parse_game, parse_team_page, phase_of_group,
                                  result_rows, select_options)
from bbstats.contrato import check_box, check_pbp, resumen
from bbstats.lineups.model import Event
from bbstats.lineups.possessions import box_possessions, count_possessions
from bbstats.lineups.sources.base import Ctx
from bbstats.lineups.sources.feb import FebPBP, game_refs, norm_name, text_clauses
from bbstats.lineups.stints import build
from bbstats.raw_store import RawStore

A, B = "100", "200"
PL = {A: [f"1{i}" for i in range(1, 7)], B: [f"2{i}" for i in range(1, 7)]}
NAME = {pid: f"{chr(64 + int(pid[1]))}. JUGADOR{pid}" for t in PL for pid in PL[t]}


# ------------------------------------------------------------------------------------------ fixtures
def _player(pid, sec, starter, pm=0, **st):
    base = {k: "0" for k in ("p1m", "p1a", "p2m", "p2a", "p3m", "p3a", "fgm", "fga", "ro", "rd", "rt", "assist",
                             "st", "to", "bs", "tc", "mt", "pf", "rf", "val", "pts")}
    base.update({k: str(v) for k, v in st.items()})
    base["fgm"] = str(int(base["p2m"]) + int(base["p3m"]))
    base["fga"] = str(int(base["p2a"]) + int(base["p3a"]))
    base["rt"] = str(int(base["ro"]) + int(base["rd"]))
    base["pts"] = str(2 * int(base["p2m"]) + 3 * int(base["p3m"]) + int(base["p1m"]))
    return {**base, "id": pid, "no": pid[-1], "name": NAME[pid], "min": str(sec), "inn": "1" if starter else "0",
            "pllss": str(pm)}


def box_doc(minutes: dict | None = None, stats: dict | None = None, n_q: int = 4) -> dict:
    """BoxScore sintético: 6 jugadores por equipo; por defecto 40 min los titulares (200 por equipo)."""
    minutes = minutes or {}
    stats = stats or {}
    teams = []
    for t in (A, B):
        pls = []
        for i, pid in enumerate(PL[t]):
            sec = minutes.get(pid, 2400 if i < 5 else 0)
            pls.append(_player(pid, sec, i < 5, **stats.get(pid, {})))
        tot = {k: str(sum(int(p[k]) for p in pls)) for k in ("p1m", "p1a", "p2m", "p2a", "p3m", "p3a", "fgm", "fga",
                                                            "ro", "rd", "rt", "assist", "st", "to", "pts")}
        teams.append({"id": t, "name": f"EQUIPO {t}", "PLAYER": pls, "TOTAL": {**tot, "min": "12000"}})
    pts = {t["id"]: t["TOTAL"]["pts"] for t in teams}
    header = {"competition": "PRIMERA FEB", "time": "FINAL", "starttime": "26-09-2026 - 19:00",
              "TEAM": [{"id": t, "name": f"EQUIPO {t}", "pts": pts[t], "clubCode": f"C{t}"} for t in (A, B)],
              "QUARTERS": {"QUARTER": [{"n": str(q)} for q in range(1, n_q + 1)]}}
    return {"HEADER": header, "BOXSCORE": {"TEAM": teams}}


def line(num, q, clock, action, team=None, pid=None, text="", **kw):
    lic = {p: f"L{p}" for t in PL for p in PL[t]}
    d = {"num": str(num), "quarter": str(q), "time": clock, "action": action, "text": text,
         "team": None if team is None else ("1" if team == A else "2"), "idTeam": team, "idPlayer": pid,
         "idLicense": lic.get(pid), "deleted": None, "Position": ""}
    d.update({k: (str(v) if v is not None else None) for k, v in kw.items()})
    return d


def structured_keyfacts() -> dict:
    """Un cuarto de 10 minutos: quinteto inicial anotado como entradas, canasta asistida, triple fallado con
    rebote defensivo, falta con 2 TL (el 1.º fallado), pérdida + robo, cambio y canasta final."""
    L = []
    n = 0

    def add(*a, **k):
        nonlocal n
        n += 1
        L.append(line(n, *a, **k))
    for t in (A, B):
        for pid in PL[t][:5]:
            add(1, "10:00", "subst", t, pid, text="Sustitución (Entra a pista)")
    add(1, "10:00", "period", text="Comienzo del Cuarto 1")
    add(1, "09:40", "shoot", A, "11", logParam4=1, logParam6=2, Position="7.0|50.0")
    add(1, "09:40", "assist", A, "12", text="ASISTENCIA")
    add(1, "09:20", "shoot", B, "21", logParam4=0, logParam6=3, Position="70.0|10.0")
    add(1, "09:18", "rebound", A, "13")
    add(1, "09:00", "foul", B, "22", text="FALTA Personal", logParam4="L14")
    add(1, "09:00", "fthrow", A, "14", logParam4=0)
    add(1, "09:00", "fthrow", A, "14", logParam4=1)
    add(1, "08:30", "lose", B, "23")
    add(1, "08:30", "recovery", A, "15")
    add(1, "05:00", "subst", A, "15", text="Sustitución (Sale de pista)")
    add(1, "05:00", "subst", A, "16", text="Sustitución (Entra a pista)")
    add(1, "04:00", "shoot", B, "24", logParam4=1, logParam6=3, Position="80.0|50.0")
    add(1, "00:00", "period", text="Fin del Cuarto 1")
    box = _q1_box()
    header = box["HEADER"]
    sb = {"TEAM": [{k: v for k, v in t.items() if k != "TOTAL"} for t in box["BOXSCORE"]["TEAM"]]}
    ts = {"TEAM": [{**t["TOTAL"], "id": t["id"]} for t in box["BOXSCORE"]["TEAM"]]}
    return {"HEADER": header, "SCOREBOARD": sb, "TEAMSTATS": ts, "PLAYBYPLAY": {"LINES": list(reversed(L))}}


def _q1_box() -> dict:
    """Boxscore coherente con el cuarto del jugada a jugada sintético."""
    mins = {p: 600 for t in PL for p in PL[t][:5]}
    mins.update({"15": 300, "16": 300})
    stats = {"11": {"p2m": 1, "p2a": 1}, "12": {"assist": 1}, "21": {"p3a": 1}, "13": {"rd": 1},
             "14": {"p1m": 1, "p1a": 2}, "24": {"p3m": 1, "p3a": 1}, "23": {"to": 1}, "15": {"st": 1}}
    return box_doc(mins, stats, n_q=1)


def structured_doc() -> dict:
    return {"keyfacts": structured_keyfacts(), "boxscore": _q1_box()}


def text_doc() -> dict:
    """Formato antiguo (2020-24): sólo texto."""
    N = {p: NAME[p] for p in NAME}
    rows = []
    for t in (A, B):
        for pid in PL[t][:5]:
            rows.append((1, "10:00", t, f"(EQUIPO {t}) Sustitución: (Entra) {N[pid]}"))
    rows += [(1, "10:00", None, "Comienzo del Cuarto 1"),
             (1, "09:40", A, f"(EQUIPO {A}) {N['11']}: Tiro en suspensión ANOTADO (2 Pts), {N['12']}: Asistencias (1 As)"),
             (1, "09:20", B, f"(EQUIPO {B}) {N['21']}: 3Pts Tiro FALLADO, {N['13']}:  (TotReb. 1)"),
             (1, "09:00", B, f"(EQUIPO {B}) {N['22']}: Personal De tiro, 1 Falta/s cometida/s. 2 tiro/s libre/s otorgado/s."),
             (1, "09:00", A, f"(EQUIPO {A}) {N['14']}:Tiros libres 1 de 2 FALLADO"),
             (1, "09:00", A, f"(EQUIPO {A}) {N['14']}:Tiros libres 2 de 2 ANOTADO (1 Pts)"),
             (1, "08:30", B, f"(EQUIPO {B}) {N['23']}: Pérdida (, 1 PER), {N['15']}: Robo (1 Rob)"),
             (1, "05:00", A, f"(EQUIPO {A}) Sustitución: (Sale) {N['15']}"),
             (1, "05:00", A, f"(EQUIPO {A}) Sustitución: (Entra) {N['16']}"),
             (1, "04:00", B, f"(EQUIPO {B}) {N['24']}:  ANOTADO (3 Pts)"),
             (1, "00:00", None, "Fin del Cuarto 1")]
    L = [{"num": str(i), "quarter": str(q), "time": c, "team": None if t is None else ("1" if t == A else "2"),
          "text": txt, "action": None, "deleted": None} for i, (q, c, t, txt) in enumerate(rows, 1)]
    d = structured_doc()
    d["keyfacts"]["PLAYBYPLAY"]["LINES"] = list(reversed(L))
    return d


def ctx():
    return Ctx(league="feb1", season="2026-27", cfg={"minutos_partido": 40})


REF = {"game_id": "9001", "phase": "regular", "teams": [A, B]}


# ------------------------------------------------------------------------------------------ HTML / calendario
RES_HTML = """
<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="vs&amp;1" />
<input type="hidden" name="_ctl0:token" id="_ctl0_token" value="TOKEN1" />
<select name="_ctl0:Main:temporadasDropDownList" id="t"><option selected="selected" value="2026">2026/2027</option>
<option value="2025">2025/2026</option></select>
<select name="_ctl0:Main:gruposDropDownList" id="g"><option value="2">Play-Offs Final</option>
<option selected="selected" value="1">Liga Regular &#218;nico</option><option value="3">Copa Princesa &#218;nico</option></select>
<select name="_ctl0:Main:jornadasDropDownList" id="j"><option selected="selected" value="J1">Jornada 1(26/09/2026)</option></select>
<table><tr><td><a id="x" href="https://baloncestoenvivo.feb.es/Equipo.aspx?i=100">EQUIPO 100</a> -
<a id="y" href="https://baloncestoenvivo.feb.es/Equipo.aspx?i=200">EQUIPO 200</a></td><td>
<a id="r" href="https://baloncestoenvivo.feb.es/Partido.aspx?p=9001">64-63</a></td><td>26/09/2026</td></tr>
<tr><td><a href="https://baloncestoenvivo.feb.es/Equipo.aspx?i=200">EQUIPO 200</a> -
<a href="https://baloncestoenvivo.feb.es/Equipo.aspx?i=100">EQUIPO 100</a></td><td>
<a href="https://baloncestoenvivo.feb.es/Partido.aspx?p=9002"></a></td><td>03/10/2026</td></tr></table>
"""

TEAM_HTML = """<h1 class="titulo-modulo">EQUIPO 100 PRIMERA FEB 2026/2027</h1><div class="box-entrenador">
<div class="foto"><img src="https://imagenes.feb.es/Foto.aspx?c=777" /></div><div class="titulo">Entrenador</div>
<div class="nombre">JUAN  ENTRENADOR PEREZ</div><div class="fecha nacimiento">17/10/1972</div></div>
<table><tr><th class="nombre jugador">Nombre</th></tr>
<tr><td class="foto jugador"></td><td class="nombre jugador"><a href='https://baloncestoenvivo.feb.es/Jugador.aspx?i=100&c=11'>ANA MARIA GARCIA LOPEZ</a></td>
<td class="puesto">Base     </td><td class="dorsal">1</td><td class="fecha nacimiento">02/06/2003</td>
<td class="nacionalidad">ESPAÑA</td><td class="formacion">SI</td><td class="altura">186</td><td class="peso">-</td></tr></table>"""


def test_html_helpers_and_phases():
    f = form_fields(RES_HTML)
    assert f["__VIEWSTATE"] == "vs&1" and f["_ctl0:Main:gruposDropDownList"] == "1"
    assert [o[1] for o in select_options(RES_HTML, "grupos")] == ["Play-Offs Final", "Liga Regular Único",
                                                                  "Copa Princesa Único"]
    rows = result_rows(RES_HTML)
    assert rows[0] == {"partido": "9001", "resultado": "64-63", "local": "100", "visitante": "200",
                       "fecha": "2026-09-26"}
    assert rows[1]["resultado"] == ""
    assert phase_of_group("Liga Regular \"A-B\"") == "regular"
    assert phase_of_group('Liga Regular 2ª Fase "Oro-Perman"') == "regular"
    assert phase_of_group("Play-Offs 1/4 Final") == "playoffs"
    assert phase_of_group("FASE FINAL-A FFA1") == "playoffs"
    assert phase_of_group("Copa Princesa de Asturias Único") is None
    assert phase_of_group("PERMANENCIA 1/2 Final") is None and phase_of_group("EDescen EDesc-2") is None
    tp = parse_team_page(TEAM_HTML)
    assert tp["entrenador"] == {"id": "777", "nombre": "JUAN ENTRENADOR PEREZ", "fecha_nacimiento": "1972-10-17"}
    assert tp["jugadores"]["11"]["fecha_nacimiento"] == "2003-06-02"
    assert tp["jugadores"]["11"]["nacionalidad"] == "España" and tp["jugadores"]["11"]["altura_cm"] == 186


class _Resp:
    def __init__(self, status, payload):
        self.status_code, self.encoding = status, "utf-8"
        self.ok = status == 200
        self.text = payload if isinstance(payload, str) else json.dumps(payload)
        self._p = payload

    def json(self):
        return self._p


class _Http:
    """Cliente falso: páginas de resultados/equipo y API KeyFacts/BoxScore; exige el token anónimo."""

    def __init__(self, docs):
        self.docs, self.calls = docs, []

    def request(self, method, url, params=None, headers=None, data=None, ok_status=()):
        self.calls.append((method, url))
        if "/resultados/" in url:
            grupo = (data or {}).get("_ctl0:Main:gruposDropDownList", "1")
            return _Resp(200, RES_HTML if grupo == "1" else RES_HTML.split("<table>")[0])   # otros grupos vacíos
        if "Equipo.aspx" in url:
            return _Resp(200, TEAM_HTML)
        return _Resp(404, "")

    def get(self, url, params=None, headers=None, ok_status=()):
        self.calls.append(("GET", url))
        if (headers or {}).get("Authorization") != "Bearer TOKEN1":
            return _Resp(401, "")
        ep, gid = url.rsplit("/", 2)[-2:]
        doc = (self.docs.get(gid) or {}).get(ep)
        return _Resp(200, doc) if doc is not None else _Resp(404, "")


def test_adapter_fetch_parse_incremental(tmp_path):
    d = structured_doc()
    docs = {"9001": {"KeyFacts": d["keyfacts"]}}
    ad = FebAdapter("feb1", {"competicion_feb": 1, "slug": "primerafeb"})
    ad.store = RawStore(tmp_path, compress=True)
    http = _Http(docs)
    p = ad.fetch("2026-27", http)
    assert list(p["games"]) == ["9001"]                      # 9002 aún sin jugar; la copa no se descarga
    assert "boxscore" not in p["games"]["9001"]              # formato estructurado: basta KeyFacts
    assert set(p["equipos"]) == {A, B}
    assert p["calendario"]["grupos"]["3"]["fase"] is None
    rows = game_rows(p)
    assert [r["formato_pbp"] for r in rows if r["game_id"] == "9001"] == ["estructurado"]
    parsed = ad.parse(p, "2026-27")
    assert set(parsed) == {"regular", "total"}
    pl = {r["player_id"]: r for r in parsed["total"].players}
    assert pl["11"]["fecha_nacimiento"] == "2003-06-02" and pl["11"]["nombre"] == "ANA MARIA GARCIA LOPEZ"
    # segunda ejecución: nada nuevo
    p2 = FebAdapter("feb1", {"competicion_feb": 1, "slug": "primerafeb"}).fetch("2026-27", _Http(docs), p)
    assert p2["games"] == {} and p2["reused_games"] == 1
    # partido sin datos (404 en las dos API) -> marcado sin_datos, no se reintenta
    p3 = FebAdapter("feb1", {"competicion_feb": 1, "slug": "primerafeb"}).fetch("2026-27", _Http({}))
    assert p3["games"]["9001"] == {"sin_datos": True} and p3["partidos_sin_datos"] == 1


def test_parse_game_box_fields():
    g = parse_game("9001", {"boxscore": box_doc(stats={"11": {"p2m": 3, "p2a": 5, "p3m": 1, "p3a": 2, "tc": 1,
                                                                   "mt": 1, "rf": 2}})}, "regular")
    p = next(x for x in g["teams"][0]["players"] if x["player_id"] == "11")
    assert p["pts"] == 9 and p["fgm"] == 4 and p["fga"] == 7 and p["blka"] == 1 and p["dunks"] == 1
    assert p["pfd"] == 2 and p["min"] == 40 and p["starter"] is True
    assert g["n_periodos"] == 4 and g["date"] == "2026-09-26"


# ------------------------------------------------------------------------------------------ jugada a jugada
def test_structured_pbp_events_and_lineups():
    g = FebPBP().parse({"data": structured_doc()}, REF, ctx())
    k = Counter(e.kind for e in g.events)
    assert k["shot"] == 3 and k["ft"] == 2 and k["dreb"] == 1 and k["tov"] == 1 and k["stl"] == 1
    assert k["foul"] == 1 and k["foul_drawn"] == 1 and k["in"] == 1 and k["out"] == 1
    shot = next(e for e in g.events if e.kind == "shot" and e.player == "11")
    assert shot.made and shot.value == 2 and shot.assister == "12" and (shot.x, shot.y) == (7.0, 50.0)
    assert next(e for e in g.events if e.kind == "foul_drawn").player == "14"
    assert g.starters[A] == PL[A][:5] and g.has_lineups and g.has_shots
    v = build(g).validation()
    # los titulares 12 (sólo asiste) y 25 no actúan: el quinteto sale de los titulares (anomalía informativa)
    assert v["dif_min_max_s"] == 0 and v["valido"] and v["detalle_anomalias"] == "quinteto_inicial_de_titulares=2"


def test_text_pbp_matches_structured():
    s = FebPBP().parse({"data": structured_doc()}, REF, ctx())
    t = FebPBP().parse({"data": text_doc()}, REF, ctx())
    ks = lambda g: Counter((e.kind, e.team, e.player, e.made, e.value) for e in g.events  # noqa: E731
                           if e.kind not in ("foul", "foul_drawn"))
    assert ks(t) == ks(s)
    assert next(e for e in t.events if e.kind == "shot" and e.player == "24").value == 3   # (3 Pts) sin tipo
    assert next(e for e in t.events if e.kind == "shot" and e.player == "11").assister == "12"
    assert not t.has_shots and build(t).validation()["dif_min_max_s"] == 0


def test_text_clauses_and_names():
    team, cl = text_clauses("(CLUB X) A. PEREZ: 3Pts Tiro FALLADO, B. LOPEZ:  (TotReb. 2)")
    assert team == "CLUB X" and cl == [("A. PEREZ", "3Pts Tiro FALLADO"), ("B. LOPEZ", "(TotReb. 2)")]
    _, cl = text_clauses("(CLUB X) A. PEREZ: 3Pts Tiro FALLADO,  (TotReb. 26)")
    assert cl == [("A. PEREZ", "3Pts Tiro FALLADO"), (None, "(TotReb. 26)")]
    _, cl = text_clauses("(CLUB X) Sustitución: (Entra) M. N´GUESSAN")
    assert cl == [("M. N´GUESSAN", "Entra")]
    assert norm_name("M. N´GUESSAN ") == "M NGUESSAN"


def test_game_refs_skip_excluded_and_no_data():
    payload = {"calendario": {"grupos": {"1": {"fase": "regular"}, "3": {"fase": None}},
                              "partidos": {"9001": {"grupo": "1"}, "9002": {"grupo": "3"}, "9003": {"grupo": "1"}}},
               "games": {"9001": structured_doc(), "9002": structured_doc(), "9003": {"sin_datos": True}}}
    refs = game_refs(payload)
    assert [r["game_id"] for r in refs] == ["9001"] and refs[0]["teams"] == [A, B] and refs[0]["final"]


# ------------------------------------------------------------------------------------------ posesiones
def _ev(order, kind, team, made=None, t=0.0, period=1, value=2):
    return Event(order=order, period=period, t=t, kind=kind, team=team, made=made, value=value)


def test_possessions_rules():
    evs = [_ev(1, "shot", "A", True, 10),            # canasta A
           _ev(2, "shot", "B", False, 20), _ev(3, "oreb", "B", t=21),   # B mantiene
           _ev(4, "shot", "B", True, 25),            # 2+1: la posesión acaba en el TL
           _ev(5, "ft", "B", True, 25),
           _ev(6, "shot", "A", False, 40), _ev(7, "dreb", "B", t=41),   # fin A
           _ev(8, "tov", "B", t=50),                 # fin B
           _ev(9, "ft", "A", False, 60), _ev(10, "ft", "A", True, 60),  # tanda: último anotado
           _ev(11, "shot", "B", False, 590)]          # fallo sin rebote al final del periodo
    n, pid = count_possessions(evs, ["A", "B"])
    assert n == Counter({"A": 3, "B": 3})
    assert pid[2] == pid[3] == pid[4] == pid[5] and pid[6] > pid[5]
    assert box_possessions(10, 5, 2, 3) == pytest.approx(13.2)


def test_possessions_real_structured_game():
    g = FebPBP().parse({"data": structured_doc()}, REF, ctx())
    n, _ = count_possessions(g.events, g.teams)
    # A: canasta, tanda de TL; B: triple fallado (rebote A), pérdida, triple anotado
    assert n[A] == 2 and n[B] == 3


# ------------------------------------------------------------------------------------------ contrato
def test_contract_valid_game_passes():
    g = parse_game("9001", {"boxscore": box_doc(stats={"11": {"p2m": 2, "p2a": 3}, "21": {"p3m": 1, "p3a": 4}})},
                   "regular")
    c = check_box(g)
    assert all(c[k] for k in ("tipos", "rangos", "identidades", "nulos", "clave_unica", "minutos", "marcador"))
    assert c["prorrogas"] == 0


def test_contract_detects_violations():
    base = parse_game("9001", {"boxscore": box_doc(n_q=5, stats={"11": {"p2m": 2, "p2a": 3}})}, "regular")
    assert check_box(base)["minutos"] is False          # 200 min con una prórroga (esperado 225)
    g = copy.deepcopy(base)
    g["n_periodos"] = 4
    p = g["teams"][0]["players"][0]
    p["fgm"] = 9                                         # anotados > intentados y fgm != fg2m + fg3m
    g["teams"][0]["players"].append(dict(g["teams"][0]["players"][1]))   # clave duplicada
    g["teams"][1]["players"][0]["min"] = "40"            # texto en vez de número
    c = check_box(g)
    assert not c["rangos"] and not c["identidades"] and not c["clave_unica"] and not c["tipos"]
    r = resumen([check_box(base | {"n_periodos": 4}), c])
    assert r["clave_unica_pct"] == 50.0 and r["partidos"] == 2


def test_contract_pbp_coherence():
    d = structured_doc()
    g = parse_game("9001", d, "regular")
    evs = FebPBP().parse({"data": d}, REF, ctx()).events
    c = check_pbp(g, evs)
    assert c["pbp_pts"] and c["pbp_fga"] and c["pbp_fgm"] and c["pbp_reb"] and c["pbp_ast"]
    evs2 = [e for e in evs if not (e.kind == "shot" and e.made)]     # faltan canastas en el jugada a jugada
    c2 = check_pbp(g, evs2)
    assert c2["pbp_pts"] is False and c2["dif_pts"] == 3
    assert check_pbp(g, [])["pbp_pts"] is None


# ------------------------------------------------------------------------------------------ crosswalk
def _node(liga, pid, nombre, fecha=None, anio=np.nan, iso=None, temps=None, equipos=None):
    return {"liga": liga, "player_id": pid, "nodo": f"{liga}:{pid}", "nombre": nombre,
            "tokens": CW.tokens_nombre(nombre), "fecha_nac": fecha,
            "anio_nac": float(fecha[:4]) if fecha else anio, "iso": iso,
            "temporadas": {t: 0.8 for t in (temps or ["2024-25"])},
            "equipos": {t: set(equipos or []) for t in (temps or ["2024-25"])}, "min": 500.0}


def test_crosswalk_scoring_and_queue():
    nodos = pd.DataFrame([
        _node("feb1", "1001", "JOSE IGNACIO NOGUES JARNE", "1995-07-24", iso="ES", temps=["2022-23"]),
        _node("feb2", "1001", "JOSE IGNACIO NOGUES JARNE", "1995-07-24", iso="ES", temps=["2023-24"]),
        _node("euroleague", "E1", "NOGUES JARNE, JOSE IGNACIO", anio=1995, temps=["2024-25"]),
        _node("acb", "A1", "Jose Ignacio Nogues", temps=["2024-25"]),                 # sin fecha: hereda del grupo
        _node("feb3", "2002", "CARLOS PEREZ GOMEZ", "2001-01-01", iso="ES", temps=["2021-22"]),
        _node("acb", "A2", "Carlos Perez Gomez", temps=["2024-25"]),                  # sólo nombre: dudoso
        _node("feb3", "3003", "LUIS MARTIN RUIZ", "1990-05-05", temps=["2021-22"]),
        _node("lnb", "L3", "Luis Martin Ruiz", "1998-02-02", temps=["2023-24"]),      # fecha distinta: rechazo
    ]).set_index("nodo", drop=False)
    a, b = nodos.loc["feb1:1001"], nodos.loc["feb2:1001"]
    assert CW.puntuar(a, b) == (1.0, "id_feb", "")
    assert CW.puntuar(nodos.loc["feb3:3003"], nodos.loc["lnb:L3"])[2] == "fecha de nacimiento distinta"
    cw, rev = CW.resolver(nodos, umbral_fusion=0.8, umbral_revision=0.5)
    per = cw.set_index(cw["fuente_liga"] + ":" + cw["fuente_id"])["persona_id"]
    assert per["feb1:1001"] == per["feb2:1001"] == per["euroleague:E1"]
    assert per["feb3:2002"] != per["acb:A2"]                                     # no se aplica: va a revisión
    assert per["feb3:3003"] != per["lnb:L3"]
    assert ((rev["id_a"] == "A2") | (rev["id_b"] == "A2")).any()
    assert cw["confianza"].between(0, 1).all() and cw["persona_id"].str.match(r"P\d{6}$").all()


def test_crosswalk_conflict_same_league_goes_to_review():
    nodos = pd.DataFrame([
        _node("feb1", "1", "PEDRO SANZ ORTIZ", anio=1999, temps=["2021-22"]),
        _node("feb1", "2", "PEDRO SANZ ORTIZ", anio=1999, temps=["2023-24"]),
        _node("euroleague", "E", "SANZ ORTIZ, PEDRO", anio=1999, temps=["2022-23"]),
    ]).set_index("nodo", drop=False)
    cw, rev = CW.resolver(nodos)
    per = cw.set_index("fuente_id")["persona_id"]
    assert per["1"] != per["2"]                     # dos ids FEB distintos sin fecha exacta: no se unen solos
    assert (rev["motivo"] == "uniría dos ids de la misma liga").any()


def test_domain_delay_shared_between_clients():
    """La pausa por dominio es común a todos los clientes del proceso (ligas FEB en paralelo, mismo dominio)."""
    import time
    from bbstats.http import HttpClient
    a = HttpClient(domain_delays={"pausa.test": 0.2})
    b = HttpClient(domain_delays={"pausa.test": 0.2})
    t0 = time.monotonic()
    a._throttle("https://pausa.test/x")
    b._throttle("https://pausa.test/y")
    a._throttle("https://pausa.test/z")
    assert time.monotonic() - t0 >= 0.38


def test_possessions_implicit_defensive_rebound():
    """Fallo de A sin rebote anotado y después tira B: la posesión de A termina igualmente."""
    evs = [_ev(1, "shot", "A", False, 10), _ev(2, "shot", "B", True, 20)]
    n, pid = count_possessions(evs, ["A", "B"])
    assert n == Counter({"A": 1, "B": 1}) and pid[2] > pid[1]
