"""Datos de la pestaña «Informe» del Atlas (bbestilo.informe): percentiles y emparejamiento con la tabla de datos."""
import numpy as np
import pandas as pd

from bbestilo import informe as I


def test_percentil_rango_medio():
    pool = np.array([1.0, 2.0, 3.0, 4.0])
    assert I._pct(2.5, pool) == 50 and I._pct(0.0, pool) == 0 and I._pct(9.0, pool) == 100
    assert I._pct(2.0, pool) == 38          # empate: cuenta la mitad (rango medio)
    assert I._pct(None, pool) is None


def test_emparejar_por_jugador_con_codigo_de_club():
    # la clave del Atlas usa un código de club («c005»); el jugador cambió de equipo: gana la fila de minutos parecidos
    a = pd.DataFrame({"liga": ["feb1", "acb"], "pid": ["7", "9"], "team_id": ["c005", "16"], "min": [300.0, 500.0]})
    t = pd.DataFrame({"liga": ["feb1", "feb1", "acb", "acb"], "player_id": ["7", "7", "9", "9"],
                      "team_id": ["11", "12", "16", "20"], "_min": [100.0, 310.0, 50.0, 480.0], "v": [1, 2, 3, 4]})
    r = I._emparejar(a, t)
    assert r["v"].tolist() == [2, 3]        # feb1: minutos más parecidos; acb: mismo team_id aunque los minutos difieran
