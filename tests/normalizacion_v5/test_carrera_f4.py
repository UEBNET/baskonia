"""F4 · capa de carrera: filtro de Kalman exacto, gradiente JAX coherente, pesos de temporadas y recuperación simulada."""
import numpy as np
import pandas as pd
import pytest

from bbnorm5.carrera import modelo as MOD


def _obs(n_personas=1, anios=(2020, 2021, 2022), ligas=("acb", "acb", "lba"), roles=("E", "E", "I"), edad0=24.0):
    filas = []
    for i in range(n_personas):
        for k, (a, l, r) in enumerate(zip(anios, ligas, roles)):
            filas.append({"persona_v5": f"P{i}", "anio": a, "liga": l, "rol": r, "edad": edad0 + k, "y": 0.0, "v": 0.05})
    return pd.DataFrame(filas)


def test_matrices_saltos_y_cambios():
    M = MOD.matrices(_obs(anios=(2020, 2021, 2023)))
    assert M["gap"][0].tolist() == [0, 1, 2]
    assert M["cl"][0].tolist() == [0, 0, 1]
    assert M["cr"][0].tolist() == [0, 0, 1]


def test_verosimilitud_kalman_igual_a_la_normal_multivariante():
    from scipy import stats
    o = _obs()
    o["y"] = [0.3, -0.1, 0.4]
    o["v"] = [0.05, 0.08, 0.02]
    M = MOD.matrices(o)
    th = {"log_s_eta": np.log(0.2), "log_s_u": np.log(0.15), "log_s_L": np.log(0.3), "log_s_R": np.log(0.1),
          "log_tau0": np.log(0.5), "kappa": 0.1, "log_c": np.log(1.2)}
    ll, _ = MOD.filtrar(M, th, np.zeros(MOD.n_base()))
    # a1 ~ N(κ, τ0²); a2 = a1 + w2 (Δt σ_η²); a3 = a2 + w3 (σ_η² + σ_L² + σ_R²); y = a + u + e
    t0, se, sL, sR, su, c = 0.25, 0.04, 0.09, 0.01, 0.0225, 1.2
    V = np.array([[t0, t0, t0], [t0, t0 + se, t0 + se], [t0, t0 + se, t0 + 2 * se + sL + sR]])
    V += np.diag(su + c * o["v"].to_numpy())
    ref = stats.multivariate_normal(np.full(3, 0.1), V).logpdf(o["y"].to_numpy())
    assert ll[0] == pytest.approx(ref, abs=1e-9)


def test_gradiente_jax_coherente_con_el_filtro_numpy():
    rng = np.random.default_rng(1)
    o = _obs(n_personas=30)
    o["y"] = rng.normal(0, 0.4, len(o))
    o["edad"] = o["edad"] + rng.integers(-3, 4, len(o)).repeat(1)
    M = MOD.matrices(o)
    libres, edad = MOD.VARIANTES["completo"]
    f = MOD._nll_jax(M, libres, {"kappa": 0.0, "log_c": 0.0}, MOD.penalizacion(edad, MOD.n_base()))
    x = np.r_[np.log([0.1, 0.2, 0.15, 0.1, 0.4]), 0.05, 0.1, 0.7, rng.normal(0, 0.05, MOD.n_base())]
    val, _ = f(x)
    th = dict(zip(libres, x[:len(libres)]))
    beta = x[len(libres):]
    ll, _ = MOD.filtrar(M, th, beta)
    pen = 0.5 * beta @ MOD.penalizacion(edad, MOD.n_base()) @ beta
    assert val == pytest.approx(-ll.sum() + pen, rel=1e-9)


def test_pesos_iguales_sin_cambio_y_mas_peso_a_la_ultima_con_cambio():
    th = {"log_tau0": np.log(0.3), "kappa": 0.0, "log_c": 0.0, "log_s_eta": np.log(1e-6), "log_s_u": np.log(1e-6)}
    mod = {"th": th, "beta": np.zeros(MOD.n_base())}
    w = MOD.pesos_temporadas(mod, 0.09, 4)
    assert np.allclose(w, w[0], atol=1e-6) and 0 < w.sum() < 1
    mod["th"] = {**th, "log_s_eta": np.log(0.2)}
    w2 = MOD.pesos_temporadas(mod, 0.09, 4)
    assert w2[-1] > w2[0]


def test_recupera_parametros_en_simulacion():
    rng = np.random.default_rng(7)
    o = _obs(n_personas=1500, anios=(2020, 2021, 2022, 2023), ligas=("a", "a", "b", "b"), roles=("E",) * 4)
    o["v"] = rng.uniform(0.01, 0.1, len(o))
    M = MOD.matrices(o)
    verdad = {"th": {"log_s_eta": np.log(0.1), "log_s_u": np.log(0.12), "log_s_L": np.log(0.2), "log_s_R": np.log(0.05),
                     "log_tau0": np.log(0.35), "kappa": 0.0, "log_c": 0.0}, "beta": np.zeros(MOD.n_base())}
    S = MOD.simular(M, verdad, rng)
    rec = MOD.ajustar(S, "completo_sin_edad", 0.3)
    assert np.exp(rec["th"]["log_tau0"]) == pytest.approx(0.35, abs=0.05)
    assert np.exp(rec["th"]["log_s_u"]) == pytest.approx(0.12, abs=0.04)
    _, out = MOD.filtrar(S, rec["th"], rec["beta"])
    z = (S["a_verdadero"] - out["a"]) / np.sqrt(out["P"])
    assert (np.abs(z[S["mask"]]) <= 1.2816).mean() == pytest.approx(0.80, abs=0.03)


def test_cambio_de_rol_conserva_el_nivel_absoluto_con_phi_1():
    """Con φ = 1, al cambiar de rol se conserva el nivel absoluto: la posición relativa se desplaza en
    μ(rol anterior) − μ(rol nuevo) de la liga-temporada."""
    o = _obs(anios=(2020, 2021), ligas=("a", "a"), roles=("X", "I"))
    o["mu"] = [-4.0, -3.0]
    for r, m in zip("EAIX", (-4.5, -4.0, -3.0, -4.0)):
        o[f"mu_{r}"] = m
    M = MOD.matrices(o)
    assert M["dmu"][0].tolist() == [0.0, -1.0]
    th = {"log_tau0": np.log(1e-3), "kappa": 0.5, "log_c": 0.0, "phi_rol": 1.0, "log_s_R": np.log(1e-6)}
    M["v"][:] = 1e6           # sin información: la predicción del segundo año es la media desplazada
    _, out = MOD.filtrar(M, th, np.zeros(MOD.n_base()))
    assert out["m_pred"][0, 1] == pytest.approx(-0.5, abs=1e-3)
