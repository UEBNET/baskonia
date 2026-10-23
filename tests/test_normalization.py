"""Tests sintéticos de la normalización amortiguada (bbmodel/amortiguacion.py) y de la corrección de σ² (suerte.py)."""
import numpy as np
import pandas as pd
import pytest

from bbmodel import amortiguacion as AM
from bbmodel import suerte


def test_cadena_suma_desfases_y_acumula_varianza():
    # FEB3 (3) → FEB2 (2) → FEB1 (1) → EuroLeague (0): cada arista mide δ_i − δ_j
    aristas = [(1, 0, -1.0, 0.01), (2, 1, -0.5, 0.04), (3, 2, -0.7, 0.09)]
    media, cov = AM.resolver_grafo(4, aristas, ref=0)
    assert media[3] == pytest.approx(-2.2)
    assert cov[3, 3] == pytest.approx(0.01 + 0.04 + 0.09)
    assert cov[1, 1] < cov[2, 2] < cov[3, 3]             # la incertidumbre crece a lo largo del camino
    camino, var = AM.camino_preciso(4, aristas, 3, 0)
    assert camino == [3, 2, 1, 0] and var == pytest.approx(0.14)


def test_caminos_paralelos_se_combinan_por_precision_inversa():
    # dos caminos independientes de 1 a la referencia: directo (−1, var 0.04) y por 2 (−0.4 −0.8 = −1.2, var 0.02+0.02)
    aristas = [(1, 0, -1.0, 0.04), (1, 2, -0.4, 0.02), (2, 0, -0.8, 0.02)]
    media, cov = AM.resolver_grafo(3, aristas, ref=0)
    w1, w2 = 1 / 0.04, 1 / 0.04
    assert media[1] == pytest.approx((w1 * -1.0 + w2 * -1.2) / (w1 + w2))
    assert cov[1, 1] == pytest.approx(1 / (w1 + w2))


def test_nodo_sin_camino_queda_sin_identificar_y_la_previa_lo_rescata():
    aristas = [(1, 0, -1.0, 0.01)]
    media, _ = AM.resolver_grafo(3, aristas, ref=0)
    assert np.isnan(media[2])
    media, cov = AM.resolver_grafo(3, aristas, ref=0, previa_media=[0, -1, -2], previa_var=[np.inf, np.inf, 0.25])
    assert media[2] == pytest.approx(-2.0) and cov[2, 2] == pytest.approx(0.25)


def test_contraccion_hacia_el_escalon():
    rng = np.random.default_rng(1)
    # 6 temporadas de una liga del mismo escalón; una con muchos puentes y otra con muy pocos
    verdad = -1.0 + rng.normal(0, 0.1, 6)
    var = np.array([0.001, 0.001, 0.001, 0.001, 0.001, 1.0])
    aristas = [(k + 1, 0, verdad[k] + (0.0 if k < 5 else 0.8), var[k]) for k in range(6)]
    r = AM.contraccion_jerarquica(7, aristas, 0, [None] + ["x"] * 6, hiperprevia_sd=10)
    # la temporada ruidosa (medida −0,2 aprox.) se acerca mucho a la media del escalón (≈ −1)
    assert abs(r["media"][6] - r["mu_escalon"]["x"]) < 0.3
    assert r["mu_escalon"]["x"] == pytest.approx(verdad[:5].mean(), abs=0.1)
    assert 0.0025 <= r["tau2"] < 0.1


def test_isotonica_y_mapeo_monotono():
    y = np.array([1.0, 3.0, 2.0, 4.0, 3.5, 5.0])
    iso = AM.isotonica(y, np.ones_like(y))
    assert np.all(np.diff(iso) >= 0)
    rng = np.random.default_rng(0)
    x = rng.normal(0, 1, 2000)
    yy = np.tanh(x) * 1.5 + rng.normal(0, 0.3, len(x))  # compresión en las colas
    F = AM.ajustar_mapeo(x, yy, np.ones_like(x), nodos=8, puentes_previa=5, min_puentes=40)
    malla = np.linspace(-4, 4, 200)
    v = F(malla)
    assert np.all(np.diff(v) >= -1e-9)                   # monótona
    assert F(0.0) == pytest.approx(0.0, abs=1e-9)        # F(0) = 0
    assert v[-1] - v[-2] == pytest.approx(malla[-1] - malla[-2], rel=1e-6)   # pendiente 1 fuera de los nodos
    assert F.inversa(F(np.array([0.7])))[0] == pytest.approx(0.7, abs=1e-2)
    # con pocos puentes: la recta
    G = AM.ajustar_mapeo(x[:10], yy[:10], np.ones(10), min_puentes=40)
    assert G(np.array([2.0]))[0] == pytest.approx(2.0)


@pytest.mark.parametrize("forma,p", [("constante", []), ("exponencial", [1.5]), ("logistica", [2.0, 0.5])])
def test_lambda_acotada_y_decreciente(forma, p):
    d = np.linspace(0, 6, 61)
    lam = AM.forma_lambda(forma, d, p, lambda_minimo=0.2)
    assert lam[0] == pytest.approx(1.0)
    assert np.all((lam > 0) & (lam <= 1.0))
    assert np.all(lam >= 0.2)
    assert np.all(np.diff(lam) <= 1e-12)


def test_eleccion_de_lambda_recupera_la_exponencial():
    rng = np.random.default_rng(3)
    filas = []
    for k, d in enumerate(np.linspace(0.2, 3, 12)):
        for _ in range(5):
            filas.append({"liga": f"l{k}", "d": d, "lam": np.exp(-d / 2.0) + rng.normal(0, 0.02), "var": 0.02 ** 2})
    r = AM.elegir_lambda(pd.DataFrame(filas), ["constante", "exponencial", "logistica"])
    assert r["elegida"] in ("exponencial", "logistica")
    assert r["formas"]["exponencial"]["parametros"][0] == pytest.approx(2.0, rel=0.1)
    assert r["formas"]["constante"]["error_lolo"] > r["formas"]["exponencial"]["error_lolo"]


def test_sigma2_no_identificado_se_imputa_con_la_mediana():
    s = {"acb": 120.0, "bbl": 90.0, "bcl": 1.8e-4, "euroleague": 60.0, "nba": 0.00125}
    imp = suerte._sigma2_no_identificado(s)
    assert imp == ["bcl", "nba"]
    assert s["bcl"] > 50 and s["nba"] > 50
    assert suerte._sigma2_no_identificado({"a": 1.0, "b": 2.0}) == []


def test_exposicion_en_posesiones_partidos_de_48_minutos():
    t = pd.DataFrame({"liga": ["nba", "acb"], "min": [48.0, 40.0], "team_pace": [100.0, 72.0],
                      "poss_on_court": [np.nan, np.nan]})
    pos = AM.exposicion_posesiones(t, {"nba": 48, "defecto": 40})
    assert pos.tolist() == pytest.approx([100.0, 72.0])   # un partido completo = las posesiones del equipo


def test_contraccion_no_borra_la_incertidumbre_del_camino_comun():
    # 4 temporadas de una liga lejana que sólo se enlazan con la referencia por UNA arista común (var 0.09):
    # 1 (puente) — 0 (ref); temporadas 2..5 enlazadas con 1 con mucha precisión
    aristas = [(1, 0, -1.0, 0.09)] + [(k, 1, -1.0, 0.001) for k in range(2, 6)]
    r = AM.contraccion_jerarquica(6, aristas, 0, [None, "a", "b", "b", "b", "b"])
    for k in range(2, 6):
        assert r["cov"][k, k] >= 0.09 * 0.95          # el camino común no se promedia entre temporadas
    assert "mu_escalon_sd" in r and r["mu_escalon_sd"]["b"] > 0.25
