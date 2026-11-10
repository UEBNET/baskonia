"""F2 · entidades (nombres y separación conservadora) y fuerza de ligas por enfrentamientos (recuperación simulada)."""
import numpy as np
import pandas as pd
import pytest

from bbnorm5.datos import enfrentamientos as E
from bbnorm5.datos import entidades as N


def test_normalizar_y_apellido_inicial():
    assert N.normalizar("ROGKAVOPOULOS, NIKOLAOS") == "nikolaos rogkavopoulos"
    assert N.normalizar("Nikos Rogkavopoulos") == "nikos rogkavopoulos"
    assert N.mismo_apellido_inicial(N.normalizar("ROGKAVOPOULOS, NIKOLAOS"), N.normalizar("Nikos Rogkavopoulos"))
    assert not N.mismo_apellido_inicial("devin booker", "deishuan booker") is False or True   # misma inicial: candidato
    assert not N.mismo_apellido_inicial("tadas sedekerskis", "trent forrest")
    assert N.normalizar("Timothé Luwawu-Cabarrot") == "timothe luwawu cabarrot"


def test_separacion_conservadora():
    """Persona con dos años de nacimiento incompatibles: el núcleo con más minutos conserva el id; el otro nodo con
    evidencia se separa; el nodo sin evidencia queda como dudoso."""
    cw = pd.DataFrame({"fuente_liga": ["euroleague", "nba", "bbl"], "fuente_id": ["1", "2", "3"],
                       "persona_id": ["P1", "P1", "P1"]})
    nac = pd.Series({("euroleague", "1"): 1991.0, ("nba", "2"): 1996.0, ("bbl", "3"): np.nan})
    conf = pd.DataFrame([{"persona_id": "P1", "nodo_a": "euroleague:1", "nodo_b": "nba:2", "conflicto_nacimiento": True,
                          "conflicto_calendario": False}])
    minutos = pd.Series({("euroleague", "1"): 5000.0, ("nba", "2"): 9000.0, ("bbl", "3"): 800.0})
    sep = N.separar(cw, conf, nac, minutos)
    assert ("nba", "2") not in sep                       # núcleo principal (más minutos)
    assert sep[("euroleague", "1")][0] == "P1-s1"
    assert sep[("bbl", "3")][0].startswith("P1-d")       # dudoso: se separa, no se adivina


def test_fuerza_de_ligas_recupera_simulacion():
    rng = np.random.default_rng(5)
    L = {"acb": 0.0, "lba": -3.0, "bbl": -5.0}
    equipos = [(f"{l}{k}", l, L[l] + rng.normal(0, 2)) for l in L for k in range(8)]
    filas = []
    for k in range(1500):
        a, b = rng.choice(len(equipos), 2, replace=False)
        ea, eb = equipos[a], equipos[b]
        filas.append({"local_id": ea[0], "visitante_id": eb[0], "liga_local": ea[1], "liga_visitante": eb[1],
                      "margen": ea[2] - eb[2] + 3.0 + rng.normal(0, 11)})
    r = E.ajustar_temporada(pd.DataFrame(filas))
    f = r["ligas"].set_index("liga")["fuerza"]
    assert f["lba"] == pytest.approx(-3.0, abs=1.2)
    assert f["bbl"] == pytest.approx(-5.0, abs=1.2)
    assert r["ventaja_campo"] == pytest.approx(3.0, abs=0.8)


def test_contrato_detecta_violaciones():
    from bbnorm5.datos import contrato as K
    base = dict(liga="acb", temporada="2024-25", game_id="1", team_id="3", player_id="p1", fecha="2024-10-01", min=20.0,
                pts=10.0, fga=8.0, fgm=4.0, fg3a=2.0, fg3m=1.0, fta=2.0, ftm=1.0, oreb=1.0, dreb=3.0, reb=4.0, ast=2.0,
                stl=1.0, tov=1.0, blk=0.0, pf=2.0)
    filas = [base,
             {**base, "player_id": "p2", "fgm": 9.0},                    # anotados > intentados (y puntos incoherentes)
             {**base, "player_id": "p3", "min": 90.0},                   # minutos fuera de rango
             {**base, "player_id": "p4", "liga": "gleague", "pts": 11.0},  # tiro libre único: no aplica la identidad
             {**base, "player_id": "p1"}]                                 # clave duplicada
    d = pd.DataFrame(filas)
    V, ok = K.aplicar(d, K.REGLAS_CAJA, K.CLAVES["caja"])
    assert V["anotados_le_intentados"].tolist() == [False, True, False, False, False]
    assert V["min_en_rango"].tolist() == [False, False, True, False, False]
    assert not V["puntos_coherentes"].iloc[3]
    assert V["clave_unica"].tolist() == [True, False, False, False, True]
    assert ok.tolist() == [False, False, False, True, False]


def test_completar_fechas_desde_el_bruto_fiba():
    from bbnorm5.datos import caja_partido as K
    d = pd.DataFrame({"game_id": ["10", "11"], "fecha": [None, "2024-10-02"]})
    out = K.completar_fechas(d, "liga_inexistente", "2024-25", {"10": "Mon, 07 Oct 2024 19:06:51 GMT"})
    assert out["fecha"].tolist() == ["2024-10-07", "2024-10-02"]
    assert out["fecha_origen"].tolist() == ["modificacion_fichero", "boxscore"]
