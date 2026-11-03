"""Corrección de identidades (03-11-2026), nombres canónicos y piezas del simulador v3.3."""
import numpy as np
import pandas as pd

from bbmodel import nombres as N
from bbmodel.crosswalk import ids_estables
from bbstats.adapters.fiba_livestats import nombre_visible, player_key


def _p(fi, ff, f, l):
    return {"internationalFirstName": fi, "internationalFamilyName": ff, "firstName": f, "familyName": l}


def test_clave_usa_el_nombre_local_si_la_ficha_es_de_otro():
    assert player_key(_p("Stefan", "Pot", "Maarten", "Vandenbossche")) == "vandenbossche-maarten"
    assert player_key(_p("Stefan", "Pot", "Stefan", "Pot")) == "pot-stefan"


def test_clave_no_separa_nombre_y_apellido_invertidos():
    assert player_key(_p("Saulius", "Grigas", "Grigas", "Saulius")) == "grigas-saulius"   # internacional, como antes
    assert player_key(_p("Douglas", "Ntesa Bunzu", "Harris", "Jordan")) == "harris-jordan"   # alias del local invertido


def test_clave_y_nombre_con_griego():
    p = _p("Frank", "Bartley", "Φρανκ", "Μπάρτλεϊ")
    assert player_key(p) == "bartley-frank"
    assert nombre_visible(p) == "Frank Bartley"


def test_ids_estables_conservan_y_numeran_lo_nuevo():
    nodos = pd.DataFrame({"liga": ["a", "b", "a", "c"], "player_id": ["1", "2", "3", "9"]})
    previo = pd.DataFrame({"fuente_liga": ["a", "b", "a"], "fuente_id": ["1", "2", "3"],
                           "persona_id": ["P000007", "P000007", "P000004"]})
    # el nodo a:3 sigue solo; a:1 y b:2 juntos; c:9 es nuevo
    raiz = {0: 0, 1: 0, 2: 2, 3: 3}
    pid = ids_estables(nodos, raiz, previo)
    assert pid[0] == "P000007" and pid[2] == "P000004" and pid[3] == "P000008"


def test_ids_estables_un_grupo_partido_conserva_el_id_en_la_parte_mayor():
    nodos = pd.DataFrame({"liga": ["a", "b", "c"], "player_id": ["1", "2", "3"]})
    previo = pd.DataFrame({"fuente_liga": ["a", "b", "c"], "fuente_id": ["1", "2", "3"], "persona_id": ["P000001"] * 3})
    pid = ids_estables(nodos, {0: 0, 1: 0, 2: 2}, previo)
    assert pid[0] == "P000001" and pid[2] == "P000002"


def test_nombre_canonico():
    c = N.canonico
    assert c([("GIRARD III, JOSEPH", 264), ("Joseph Girard III", 2868), ("Joseph Girard", 67)]) == "Joseph Girard III"
    assert c([("J. LÓPEZ YUSTE", 735), ("JUAN LOPEZ YUSTE", 740)]) == "Juan López Yuste"
    assert c([("J. BOCCA", 1800)]) == "J. Bocca"
    assert c([("GUILLERMO DE LA FUENTE", 300)]) == "Guillermo de la Fuente"
    assert c([("MCDONALD, JOHN", 300)]) == "John McDonald"
    assert c([("Κωνσταντίνος Χατζής", 10)]) == "Konstadinos Chatzis"
    assert c([("B. Mclemore 麦克勒莫", 10)]) == "B. Mclemore"


def test_aplicar_conserva_nombres_sin_canonico(monkeypatch):
    monkeypatch.setattr(N, "canonico_nodo", lambda: {("acb", "1"): "Juan López Yuste"})
    monkeypatch.setattr(N, "canonico_persona", lambda: {})
    d = pd.DataFrame({"liga": ["acb", "acb"], "player_id": ["1", "2"], "nombre": ["J. LÓPEZ YUSTE", "X"]})
    r = N.aplicar(d)
    assert r["nombre"].tolist() == ["Juan López Yuste", "X"] and r["nombre_fuente"].tolist() == ["J. LÓPEZ YUSTE", "X"]


def test_v33_candidato_minutos_desplaza_y_recorta():
    from bbfit import v33
    base = pd.DataFrame({"pred": [10.0, 30.0], "lo80": [5.0, 25.0], "hi80": [15.0, 38.0]})
    p = v33.candidato_minutos(base, np.array([12.0, 40.0]), np.array([40.0, 40.0]))
    assert p["pred"].tolist() == [12.0, 40.0] and p["lo80"].tolist() == [7.0, 35.0] and p["hi80"].tolist() == [17.0, 40.0]


def test_v33_b9_minimos_cuadrados_recupera_coeficientes():
    from bbfit import v33
    rng = np.random.default_rng(1)
    n = 400
    dm, dr = rng.normal(0, 5, n), rng.integers(-2, 3, n).astype(float)
    e = pd.DataFrame({"min_total_real": 600, "eval_min": True, "min_real": 20 + dm, "rol_real": "ROTACION",
                      "v_indice_rol": 2 - dr})
    pred = pd.DataFrame({"pred": np.full(n, 15.0)})
    e["pts_p100_real"] = 15 + 0.1 * dm + 0.8 * dr
    import bbfit.v32 as V32
    old = V32.ok_produccion
    V32.ok_produccion = lambda x: np.ones(len(x), bool)
    try:
        k = v33.ajustar_b9(e, {"pts_p100": pred}, np.full(n, 20.0), ["pts_p100"])["pts_p100"]
    finally:
        V32.ok_produccion = old
    assert abs(k["b_min"] - 0.1) < 1e-6 and abs(k["c_rol"] - 0.8) < 1e-6
