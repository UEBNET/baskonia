"""F6 · ligas y contexto: recuperación de λ en un grafo simulado (GLS), ciclos nulos con la estimación conjunta y
contracción de los coeficientes de contexto."""
import itertools

import numpy as np
import pandas as pd
import pytest

from bbnorm5.ligas import contexto as LC
from bbnorm5.ligas import datos as LD
from bbnorm5.ligas import gls


def _pares(rng, lam, n=3000, s_c=0.2):
    ligas = list(lam)
    filas = []
    for _ in range(n):
        a, b = rng.choice(ligas, 2, replace=False)
        x = rng.normal(0, [0.4, 0.3, 0.2, 0.05])
        v = rng.uniform(0.02, 0.2)
        d = lam[b] - lam[a] + 0.3 * x[0] + rng.normal(0, np.sqrt(v + s_c ** 2))
        filas.append({"metrica": "m", "liga_a": a, "liga_b": b, "d": d, "var": v,
                      **dict(zip(LD.CONTEXTO, x)), "puente": len(filas), "persona_v5": f"P{len(filas)}"})
    return pd.DataFrame(filas)


def test_gls_recupera_lambda_y_contexto():
    rng = np.random.default_rng(1)
    lam = {"acb": 0.0, "lba": -0.3, "nba": 0.5, "feb2": 0.8, "bbl": -0.1}
    m = gls.ajustar(_pares(rng, lam), "m")
    est = dict(zip(m["ligas"], m["lambda"]))
    sd = dict(zip(m["ligas"], np.sqrt(np.diag(m["cov"]))))
    for l, v in lam.items():
        assert est[l] == pytest.approx(v, abs=4 * sd[l] + 1e-9)
    assert m["beta"][0] == pytest.approx(0.3, abs=0.05)
    assert m["s_c2"] ** 0.5 == pytest.approx(0.2, abs=0.05)


def test_traduccion_conjunta_cumple_los_ciclos():
    rng = np.random.default_rng(2)
    lam = {"acb": 0.0, "lba": -0.3, "nba": 0.5, "feb2": 0.8}
    m = gls.ajustar(_pares(rng, lam, 1500), "m")
    for a, b, c in itertools.combinations(m["ligas"], 3):
        r = gls.diferencia(m, a, b)[0] + gls.diferencia(m, b, c)[0] - gls.diferencia(m, a, c)[0]
        assert abs(r) < 1e-12


def test_contraccion_del_contexto_sin_senal():
    """Sin señal, la regresión con contracción por bloque deja los coeficientes cerca de 0."""
    rng = np.random.default_rng(3)
    X = rng.normal(size=(4000, 6))
    r = rng.normal(0, 1, 4000)
    fit = LC.ajustar_beta(X, r, np.ones(4000), np.array([0, 0, 0, 1, 1, 1]))
    assert np.abs(fit["beta"]).max() < 0.05
    y = X[:, 0] * 0.5 + rng.normal(0, 1, 4000)
    fit = LC.ajustar_beta(X, y, np.ones(4000), np.array([0, 0, 0, 1, 1, 1]))
    assert fit["beta"][0] == pytest.approx(0.5, abs=0.06)
