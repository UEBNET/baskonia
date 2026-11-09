"""F1 · utilidades de calibración (bbnorm5.diagnostico.pasos_f1) y estimador de división de muestra."""
import numpy as np
import pandas as pd
import pytest
from scipy import integrate
from scipy.stats import norm

from bbnorm5.diagnostico import pasos_f1 as P


def test_crps_normal_igual_a_integral():
    y, mu, sd = 0.7, 0.2, 1.3
    num, _ = integrate.quad(lambda x: (norm.cdf(x, mu, sd) - (x >= y)) ** 2, -30, 30, points=[y], limit=200)
    assert P.crps_normal(y, mu, sd) == pytest.approx(num, rel=1e-6)


def test_coberturas_de_una_normal_bien_calibrada():
    rng = np.random.default_rng(3)
    mu = rng.normal(size=200_000)
    sd = rng.uniform(0.5, 2, size=mu.size)
    y = mu + sd * rng.standard_normal(mu.size)
    r = P.medidas(y, mu, sd)
    assert r["cob50"] == pytest.approx(0.5, abs=0.005)
    assert r["cob80"] == pytest.approx(0.8, abs=0.005)
    assert r["cob95"] == pytest.approx(0.95, abs=0.005)
    assert r["pit_ks"] < 0.01
    # el mismo error con intervalos el doble de anchos: infraconfiado
    assert P.diagnostico_cobertura(P.medidas(y, mu, 2 * sd)["cob80"]) == "infraconfiado"
    assert P.diagnostico_cobertura(P.medidas(y, mu, 0.6 * sd)["cob80"]) == "sobreconfiado"


def test_division_de_muestra_recupera_n_estrella():
    """Mitades simuladas de una proporción (T3%): con señal Var(θ) y ruido binomial, n* = σ²/Var(θ)."""
    from bbnorm5.diagnostico import division
    rng = np.random.default_rng(11)
    J = 6000
    p = np.clip(rng.normal(0.34, 0.035, J), 0.05, 0.95)
    a1, a2 = rng.integers(30, 250, J), rng.integers(30, 250, J)
    m = pd.DataFrame({"liga": "L", "temporada": "2024-25", "pos3_1": "A", "fg3a_1": a1, "fg3a_2": a2,
                      "fg3m_1": rng.binomial(a1, p), "fg3m_2": rng.binomial(a2, p)})
    r = division.estimar(m, "fg3_pct")
    # n* teórico en la escala de trabajo («id», en puntos de %): σ² = p(1−p)·100², Var(θ) = (3,5)²
    teorico = 0.34 * 0.66 * 100 ** 2 / 3.5 ** 2
    assert r["n_estab_momentos"] == pytest.approx(teorico, rel=0.12)
