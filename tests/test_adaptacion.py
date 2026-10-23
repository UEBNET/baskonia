"""Tests sintéticos de la fase 7 (bbfit/adaptacion.py): interfaz del simulador y piezas del modelo."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from bbfit import adaptacion as A


# ------------------------------------------------------------------------------------------- interfaz
def test_curva_forma_y_limites():
    assert A.curva(0, -0.1, 5) == pytest.approx(0.9)
    assert A.curva(1e6, -0.1, 5) == pytest.approx(1.0)
    k = 6.0
    # al 50 % del hueco en κ·ln2 partidos, al 90 % en κ·ln10
    assert A.curva(k * math.log(2), -0.2, k) == pytest.approx(1 - 0.1)
    assert A.curva(k * math.log(10), -0.2, k) == pytest.approx(1 - 0.02)
    g = np.arange(0, 30)
    f = A.curva(g, -0.15, 4.0)
    assert f.shape == g.shape and np.all(np.diff(f) > 0)          # penalización que se cierra de forma monótona
    assert A.curva(3, 0.0, 4.0) == pytest.approx(1.0)
    assert A.partidos_hasta(0.5, k) == pytest.approx(k * math.log(2))
    assert A.partidos_hasta(0.9, k) == pytest.approx(k * math.log(10))
    assert A.curva(2, -0.1, 0) == pytest.approx(1.0)                # κ = 0: adaptación instantánea


def test_grupo_nacionalidad():
    g = A.grupo_nacionalidad
    assert g("US", "nba", "acb") == "EEUU_a_Europa"
    assert g("Estados Unidos", "gleague", "lba") == "EEUU_a_Europa"
    assert g("FR", "nba", "lnb") == "otro_desde_EEUU"
    assert g(None, "nba", "lnb") == "desconocido"
    assert g(float("nan"), "acb", "lba") == "desconocido"
    assert g(None, "acb", "nba") == "hacia_EEUU"
    assert g("ES", "nba", "gleague") == "intra_EEUU"
    assert g("ES", "feb1", "acb") == "nacional_mismo_pais"
    assert g("España", "feb3", "feb2") == "nacional_mismo_pais"
    assert g("US", "feb1", "acb") == "extranjero_mismo_pais"
    assert g("RS", "acb", "lba") == "europeo_cambia_liga"
    assert g("ES", "acb", "euroleague") == "europeo_cambia_liga"      # copa europea: sin país
    assert g("US", "acb", "lba") == "extranjero_cambia_pais"
    assert g("Alemania / Estados Unidos", "lnb", "bbl") == "europeo_cambia_liga"
    assert g("Alemania / Estados Unidos", "nba", "bbl") == "EEUU_a_Europa"


def _tabla_sintetica():
    filas = []
    base = dict(delta_lo=-0.2, delta_hi=0.1, kappa_lo=1, kappa_hi=10, escalon_destino="*")
    for met in ("L", "pts_p100"):
        filas += [
            dict(nivel="global", liga_origen="*", liga_destino="*", grupo_nacionalidad="*", pos3="*", metrica=met,
                 n=500, delta_media=-0.01, delta_sd=0.05, kappa_media=4.0, kappa_sd=1.0, **base),
            dict(nivel="global_grupo", liga_origen="*", liga_destino="*", grupo_nacionalidad="EEUU_a_Europa",
                 pos3="*", metrica=met, n=100, delta_media=-0.05, delta_sd=0.04, kappa_media=7.0, kappa_sd=2.0, **base),
            {**dict(nivel="escalon", liga_origen="*", liga_destino="*", grupo_nacionalidad="*", pos3="*",
                    metrica=met, n=200, delta_media=-0.02, delta_sd=0.03, kappa_media=4.5, kappa_sd=1.0, **base),
             "escalon_destino": "domestica_alta"},
            dict(nivel="par", liga_origen="feb1", liga_destino="acb", grupo_nacionalidad="*", pos3="*", metrica=met,
                 n=40, delta_media=-0.06, delta_sd=0.03, kappa_media=5.0, kappa_sd=1.5, **base),
            dict(nivel="celda", liga_origen="feb1", liga_destino="acb", grupo_nacionalidad="nacional_mismo_pais",
                 pos3="E", metrica=met, n=12, delta_media=-0.07, delta_sd=0.04, kappa_media=5.5, kappa_sd=1.5, **base),
            dict(nivel="celda", liga_origen="feb1", liga_destino="acb", grupo_nacionalidad="nacional_mismo_pais",
                 pos3="I", metrica=met, n=3, delta_media=-0.30, delta_sd=0.20, kappa_media=9.0, kappa_sd=3.0, **base),
        ]
    return pd.DataFrame(filas)


def test_prior_jerarquia_de_reserva(tmp_path):
    ruta = tmp_path / "adaptation_priors.csv"
    _tabla_sintetica().to_csv(ruta, index=False)
    claves = {"delta_media", "delta_sd", "kappa_media", "kappa_sd", "n", "nivel_fallback"}
    r = A.prior("feb1", "acb", "nacional_mismo_pais", "E", ruta=ruta)
    assert set(r) == claves and r["nivel_fallback"] == "celda" and r["delta_media"] == pytest.approx(-0.07)
    r = A.prior("feb1", "acb", "nacional_mismo_pais", "I", ruta=ruta)          # celda con n < n_min → par
    assert r["nivel_fallback"] == "par" and r["n"] == 40
    r = A.prior("lba", "acb", "europeo_cambia_liga", "A", ruta=ruta)           # sin par → escalón de destino
    assert r["nivel_fallback"] == "escalon" and r["delta_media"] == pytest.approx(-0.02)
    r = A.prior("lba", "euroleague", "EEUU_a_Europa", "A", metrica="pts_p100", ruta=ruta)
    assert r["nivel_fallback"] == "global_grupo" and r["kappa_media"] == pytest.approx(7.0)
    r = A.prior("lba", "euroleague", "europeo_cambia_liga", "A", ruta=ruta)
    assert r["nivel_fallback"] == "global"
    with pytest.raises(ValueError):
        A.prior("feb1", "acb", "nacional_mismo_pais", "E", metrica="xyz", ruta=ruta)


def test_prior_sin_tabla_devuelve_defecto(tmp_path):
    r = A.prior("feb1", "acb", "nacional_mismo_pais", "E", ruta=tmp_path / "no_existe.csv")
    assert r["nivel_fallback"] == "sin_datos" and r["delta_media"] == 0.0 and r["n"] == 0
    assert r["delta_sd"] > 0 and r["kappa_media"] > 0
