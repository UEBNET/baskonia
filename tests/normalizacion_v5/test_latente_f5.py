"""F5 · capa latente: con K = 0 el filtro multivariante es la suma de los univariantes de la F4; recuperación de cargas;
varimax y congruencia."""
import numpy as np
import pandas as pd
import pytest

from bbnorm5.carrera import modelo as MC
from bbnorm5.latente import modelo as ML


def _o(rng, P=40, T=3, faltan=0.2):
    filas = []
    for i in range(P):
        for t in range(T):
            for m in ML.METRICAS:
                if rng.random() < faltan:
                    continue
                filas.append({"persona_v5": f"P{i:03d}", "anio": 2020 + t, "liga": "a" if t < 2 else "b",
                              "rol": "E", "edad": 24.0 + t, "metrica": m, "y": rng.normal(0, 0.4),
                              "v": rng.uniform(0.01, 0.1)})
    return pd.DataFrame(filas)


def _f4(rng):
    out = {}
    for m in ML.METRICAS:
        th = {"log_s_eta": np.log(rng.uniform(0.05, 0.2)), "log_s_u": np.log(rng.uniform(0.05, 0.2)),
              "log_s_L": np.log(rng.uniform(0.05, 0.3)), "log_s_R": np.log(0.1), "log_tau0": np.log(0.3),
              "kappa": rng.normal(0, 0.05), "log_c": np.log(rng.uniform(0.8, 1.2))}
        out[m] = {"th": th, "beta": np.zeros(MC.n_base())}
    return out


def test_k0_es_la_suma_de_los_filtros_univariantes():
    """Sin métricas ausentes. (Con ausencias difieren a propósito: en la F5 la capacidad de una métrica no observada
    evoluciona desde la primera temporada del jugador; en la F4 su primera observación arranca del prior.)"""
    import jax
    import jax.numpy as jnp
    jax.config.update("jax_enable_x64", True)
    rng = np.random.default_rng(0)
    o, f4 = _o(rng, faltan=0.0), _f4(rng)
    S = ML.matrices(o, f4)
    psi = rng.uniform(0.05, 0.3, len(ML.METRICAS))
    ll, _ = ML._filtro(S, jnp.zeros((len(ML.METRICAS), 0)), jnp.asarray(psi), "diag")
    tot = 0.0
    for k, m in enumerate(ML.METRICAS):
        x = o[o["metrica"] == m]
        th = {**f4[m]["th"], "log_tau0": 0.5 * np.log(psi[k])}
        l1, _ = MC.filtrar(MC.matrices(x), th, f4[m]["beta"])
        tot += l1.sum()
    assert float(ll.sum()) == pytest.approx(tot, rel=1e-9)


def test_recupera_cargas_simuladas():
    rng = np.random.default_rng(3)
    Mm, K, P = len(ML.METRICAS), 2, 2500
    L = np.zeros((Mm, K))
    L[:7, 0] = 0.4
    L[7:, 1] = 0.35
    L[3:9, 1] += 0.2
    psi = np.full(Mm, 0.04)
    a = rng.multivariate_normal(np.zeros(Mm), L @ L.T + np.diag(psi), P)
    v = rng.uniform(0.01, 0.05, (P, Mm))
    y = a + rng.normal(0, np.sqrt(v))
    filas = [{"persona_v5": f"P{i}", "anio": 2020, "liga": "a", "rol": "E", "edad": 25.0, "metrica": m,
              "y": y[i, k], "v": v[i, k]} for i in range(P) for k, m in enumerate(ML.METRICAS)]
    f4 = {m: {"th": {"log_s_eta": np.log(0.1), "log_s_u": -30.0, "log_s_L": np.log(0.1), "log_s_R": np.log(0.1),
                     "log_tau0": 0.0, "kappa": 0.0, "log_c": 0.0}, "beta": np.zeros(MC.n_base())} for m in ML.METRICAS}
    S = ML.matrices(pd.DataFrame(filas), f4)
    mod = ML.ajustar(S, K, "corr", maxiter=300)
    cg = ML.congruencia(ML.varimax(L)[0], ML.varimax(mod["L"])[0])
    assert (np.abs(cg) > 0.95).all()


def test_varimax_ortogonal_y_congruencia_invariante_a_rotacion():
    rng = np.random.default_rng(1)
    L = rng.normal(size=(14, 4))
    Lr, R = ML.varimax(L)
    assert np.allclose(R.T @ R, np.eye(4), atol=1e-8)
    Q, _ = np.linalg.qr(rng.normal(size=(4, 4)))
    assert np.allclose(np.abs(ML.congruencia(L, L @ Q)), 1, atol=1e-8)
