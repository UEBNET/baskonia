"""F8 · piezas del examen: WIS (para un punto es el error absoluto; para la normal se acerca al CRPS), la versión con
otro rol de la predicción (con el mismo rol no cambia nada), la recalibración oráculo (cobertura nominal en la prueba)
y que el GLS del paso 2 de un año objetivo no mira datos de ese año ni posteriores."""
import numpy as np
import pandas as pd
import pytest
from scipy import stats

from bbnorm5.validacion import fichajes as VF


def test_wis_punto_es_error_absoluto():
    y = np.array([1.0, 2.0, 5.0])
    c = np.array([1.5, 2.0, 3.0])
    lo = {a: c for a in (50, 80, 90)}
    assert VF.wis(y, c, lo, lo) == pytest.approx(np.abs(y - c))


def test_wis_aproxima_crps_normal():
    rng = np.random.default_rng(1)
    y = rng.normal(size=20000)
    niveles = {50: 0.25, 80: 0.10, 90: 0.05}
    lo = {a: np.full(y.size, stats.norm.ppf(q)) for a, q in niveles.items()}
    hi = {a: np.full(y.size, stats.norm.ppf(1 - q)) for a, q in niveles.items()}
    w = VF.wis(y, np.zeros(y.size), lo, hi).mean()
    crps = (y * (2 * stats.norm.cdf(y) - 1) + 2 * stats.norm.pdf(y) - 1 / np.sqrt(np.pi)).mean()
    # con sólo los intervalos del 50, 80 y 90 % el WIS es ≈ 0,8 × CRPS (faltan las colas): proporcional, no igual
    assert 0.75 < w / crps < 0.86
    # propio: la predicción correcta gana a una demasiado ancha y a una sesgada
    ancho = VF.wis(y, np.zeros(y.size), {a: 2 * v for a, v in lo.items()}, {a: 2 * v for a, v in hi.items()}).mean()
    sesgo = VF.wis(y, np.full(y.size, 0.5), {a: v + 0.5 for a, v in lo.items()}, {a: v + 0.5 for a, v in hi.items()}).mean()
    assert w < ancho and w < sesgo


def _caso():
    return pd.DataFrame({"liga": ["acb", "acb"], "rol": ["E", "I"], "rol_ult": ["E", "A"], "cl": [0.0, 1.0],
                         "cr": [0.0, 1.0], "dmu": [0.0, 0.2], "m_nivel": [0.1, 0.3], "v_nivel": [0.02, 0.05],
                         "v_y_sin_muestreo": [0.03, 0.06], "phi_rol": [0.5, 0.5], "s2_R": [0.01, 0.01],
                         "mu_prev": [0.0, -0.4], "mu_prev_rol_ult": [0.0, -0.2], "mu_origen": [0.1, -0.1],
                         "delta_lambda": [0.0, 0.05], "ajuste_liga": [0.0, 0.0], "vol_E": [0.0, 0.0],
                         "vol_A": [0.0, 0.0], "vol_I": [0.0, 0.0], "dl_rol_E": [0.0, 0.0], "dl_rol_I": [0.0, 0.05]})


def test_con_rol_mismo_rol_no_cambia_nivel():
    x = _caso()
    lp = pd.DataFrame({"liga": ["acb"] * 3, "rol": ["E", "A", "I"], "mu_prev": [0.0, -0.2, -0.4]})
    y, ok = VF.con_rol(x, "I", lp)
    assert ok.all()
    assert y["m_nivel"].iloc[1] == pytest.approx(x["m_nivel"].iloc[1])
    assert y["v_nivel"].iloc[1] == pytest.approx(x["v_nivel"].iloc[1])
    assert y["mu_prev"].iloc[1] == pytest.approx(-0.4)
    # el mismo jugador, si siguiera en su rol (A): sin desplazamiento ni varianza de cambio de rol
    z, _ = VF.con_rol(x, "A", lp)
    assert z["m_nivel"].iloc[1] == pytest.approx(0.3 - 0.5 * 0.2)
    assert z["v_nivel"].iloc[1] == pytest.approx(0.05 - 0.01)
    assert z["mu_prev"].iloc[1] == pytest.approx(-0.2)


def test_recalibracion_oraculo_da_cobertura_nominal():
    rng = np.random.default_rng(2)
    n = 4000
    y = rng.normal(0, 2, n)
    d = pd.DataFrame({"metrica": "m", "y": y, "v33_pred": 0.0})
    for a, q in VF.NIVELES.items():
        d[f"v33_lo{a}"], d[f"v33_hi{a}"] = stats.norm.ppf(q[0]), stats.norm.ppf(q[1])     # demasiado estrechos
    o = VF.recalibrar_oraculo(d, "v33_", "v33_pred")
    for a in VF.NIVELES:
        cob = ((o["y"] >= o[f"v33_lo{a}"]) & (o["y"] <= o[f"v33_hi{a}"])).mean()
        assert cob == pytest.approx(a / 100, abs=0.01)


def test_gls_paso2_no_mira_el_futuro():
    from bbnorm5.ligas import datos as LD
    from bbnorm5.ligas import seleccion as LS
    rng = np.random.default_rng(3)
    n = 400
    intra = pd.DataFrame({"metrica": "m", "liga_a": rng.choice(["acb", "x"], n), "temporada": "2021-22",
                          "d": rng.normal(size=n), "var": 0.1})
    intra["liga_b"] = np.where(intra["liga_a"] == "acb", "x", "acb")
    for c in LD.CONTEXTO:
        intra[c] = 0.0
    futuro = intra.assign(temporada="2024-25", d=intra["d"] + 5)
    vacio = pd.DataFrame(columns=["metrica", "liga_ult", "liga", "eta_obs", "mu_origen", "m_nivel", "v_obs",
                                  "v_y_sin_muestreo", "anio_obj", "cl"])
    T = 2023
    todo = pd.concat([intra, futuro])
    a = LS.gls_paso2(todo[todo["temporada"].str[:4].astype(int) < T], vacio, "m", "encogido")
    b = LS.gls_paso2(intra, vacio, "m", "encogido")
    assert np.allclose(a["lambda"], b["lambda"])
