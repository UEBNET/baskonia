"""F1 · REML anidado de bbnorm5.diagnostico.varianza: exactitud de la forma cerrada y recuperación de parámetros."""
import numpy as np
import pytest

from bbnorm5.diagnostico import varianza as V


def _simular(rng, I=1500, s2a=0.5, s2u=0.15, s2=4.0, s2b=0.3):
    filas = []
    ligas = [f"L{k}" for k in range(6)]
    b = {(l, t): rng.normal(0, np.sqrt(s2b)) for l in ligas for t in range(5)}
    for i in range(I):
        a = rng.normal(0, np.sqrt(s2a))
        t0 = rng.integers(0, 3)
        for t in range(t0, t0 + rng.integers(1, 4)):
            u = rng.normal(0, np.sqrt(s2u))
            # un 20 % juega dos ligas la misma temporada (puente intra-temporada)
            for l in rng.choice(ligas, size=1 + (rng.random() < 0.2), replace=False):
                n = rng.uniform(5, 60)
                filas.append((i, t, l, b[(l, t)] + a + u + rng.normal(0, np.sqrt(s2 / n)), n))
    i, t, l, y, n = map(np.array, zip(*filas))
    return y, n, i, t, np.char.add(np.char.add(l.astype(str), "|"), t.astype(str)), np.zeros(len(y), int)


def _nll_denso(theta, y, n, per, pt, b):
    s2a, s2u, s2 = np.exp(theta)
    N = len(y)
    Vm = np.diag(s2 / n) + s2a * (per[:, None] == per[None, :]) + s2u * (pt[:, None] == pt[None, :])
    X = (b[:, None] == np.unique(b)[None, :]).astype(float)
    Vi = np.linalg.inv(Vm)
    XtVX = X.T @ Vi @ X
    beta = np.linalg.solve(XtVX, X.T @ Vi @ y)
    r = y - X @ beta
    return 0.5 * (np.linalg.slogdet(Vm)[1] + np.linalg.slogdet(XtVX)[1] + r @ Vi @ r)


def test_forma_cerrada_igual_a_densa():
    rng = np.random.default_rng(1)
    y, n, per, t, b, g = _simular(rng, I=25)
    D = V.Datos(y, n, per, t, b, g)
    # la versión densa con el mismo orden de filas que Datos
    orden = np.lexsort((t, per))
    pt = np.unique(np.char.add(np.char.add(per[orden].astype(str), "|"), t[orden].astype(str)), return_inverse=True)[1]
    for theta in (np.log([0.5, 0.15, 4.0]), np.log([1.2, 0.01, 9.0])):
        assert V._nll_reml(theta, D) == pytest.approx(_nll_denso(theta, y[orden], n[orden], per[orden], pt, b[orden]), rel=1e-9)


def test_recupera_parametros():
    rng = np.random.default_rng(7)
    y, n, per, t, b, g = _simular(rng)
    aj = V.ajustar(V.Datos(y, n, per, t, b, g))
    assert aj["convergio"]
    assert aj["s2a"] == pytest.approx(0.5, rel=0.15)
    assert aj["s2u"] == pytest.approx(0.15, rel=0.35)
    assert list(aj["s2g"].values())[0] == pytest.approx(4.0, rel=0.15)
    assert aj["s2b"] == pytest.approx(0.3, rel=0.6)
    r = V.resumen(aj, n, g)
    assert r["n_estab_temp"] == pytest.approx(4.0 / 0.65, rel=0.25)
