"""Modelo A: el tramo de desarrollo NCAA separa el nivel de la NCAA del progreso del jugador universitario."""
import numpy as np
import pandas as pd

from bbmodel import enlace


def _sintetico(n=1500, dev=0.30, nivel=-1.0, semilla=1):
    rng = np.random.default_rng(semilla)
    filas = []
    pid = 0
    for _ in range(n):                      # universitarios: dos cursos y (algunos) pasan a profesional
        pid += 1
        a = rng.normal(0, 1)
        z1 = (a - nivel) + rng.normal(0, 0.2)                  # z en la NCAA: u = m + s·z con s = 1
        z2 = (a + dev - nivel) + rng.normal(0, 0.2)            # año siguiente en la NCAA: mejora `dev`
        filas += [(pid, "ncaa", 2021, np.nan, 600, z1, 0.02), (pid, "ncaa", 2022, np.nan, 600, z2, 0.02)]
        if rng.random() < 0.5:
            z3 = (a + 2 * dev) + rng.normal(0, 0.2)            # profesional (EuroLeague) en t+1
            filas.append((pid, "euroleague", 2023, np.nan, 600, z3, 0.02))
    for _ in range(800):                    # profesionales que repiten liga (fijan la deriva adulta ≈ 0)
        pid += 1
        a = rng.normal(0, 1)
        for anio in (2021, 2022):
            filas.append((pid, "euroleague", anio, 1995, 900, a + rng.normal(0, 0.2), 0.02))
    return pd.DataFrame(filas, columns=["persona_id", "liga", "anio", "anio_nac", "min", "z", "v"])


def test_tramo_ncaa_identifica_nivel_y_desarrollo():
    r = enlace.ajustar_metrica(_sintetico(), n_boot=0)
    assert enlace.TRAMO_NCAA in r["tramos"]
    assert abs(r["deriva"][enlace.TRAMO_NCAA] - 0.30) < 0.08
    assert abs(r["m"]["ncaa"] - (-1.0)) < 0.15


def test_tramo_de_origen():
    assert enlace.tramo(20, "ncaa") == enlace.TRAMO_NCAA
    assert enlace.tramo(20, "acb") == "≤23"
