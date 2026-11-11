"""F7 · selección en los traspasos: el probit recupera sus coeficientes y, en una simulación de regresión a la media
(sube quien tuvo una temporada observada alta), λ con la temporada previa en bruto sale sesgado y con el nivel encogido
no."""
import numpy as np
import pandas as pd
import pytest

from bbnorm5.ligas import datos as LD
from bbnorm5.ligas import seleccion as LS


def test_probit_recupera_coeficientes():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(20000, 2))
    y = (0.3 + X @ np.array([0.8, -0.5]) + rng.normal(size=20000) > 0).astype(float)
    b = LS.probit(X, y)
    assert b == pytest.approx([0.3, 0.8, -0.5], abs=0.05)


def _sim(rng, n=20000, lam_b=-0.3, tau=0.4, ruido=0.5):
    """Nivel verdadero θ ~ N(0, τ²) en la liga a; temporada observada y = θ + ruido; sube a la liga b (λ_b) quien tiene
    y alto; en b se observa θ + λ_b + ruido. El nivel encogido es E[θ | y] = y·τ²/(τ² + ruido²)."""
    th = rng.normal(0, tau, n)
    y = th + rng.normal(0, ruido, n)
    sube = y > np.quantile(y, 0.8)
    yb = th + lam_b + rng.normal(0, ruido, n)
    k = tau ** 2 / (tau ** 2 + ruido ** 2)
    m = pd.DataFrame({"metrica": "m", "liga_ult": "a", "liga": "b", "eta_obs": yb, "eta_ult": y, "v_obs": ruido ** 2,
                      "v_ult": ruido ** 2, "s2_u": 0.0, "mu_origen": 0.0, "m_nivel": k * y,
                      "v_y_sin_muestreo": k * ruido ** 2, "w_ipw": 1.0, "imr_sube": 0.0, "imr_baja": 0.0})[sube]
    intra = pd.DataFrame({"metrica": "m", "liga_a": ["a", "a"], "liga_b": ["c", "c"], "d": [0.0, 0.0], "var": [1.0, 1.0],
                          **{c: [0.0, 0.0] for c in LD.CONTEXTO}})
    return intra, m


def test_regresion_a_la_media_crudo_sesga_y_encogido_no():
    rng = np.random.default_rng(1)
    intra, inter = _sim(rng)
    inter = inter.assign(liga_ult="acb")
    intra = intra.assign(liga_a="acb")
    crudo = LS.gls_paso2(intra, inter, "m", "crudo")
    enc = LS.gls_paso2(intra, inter, "m", "encogido")
    lb = lambda g: g["lambda"][g["ligas"].index("b")]
    assert lb(crudo) < -0.3 - 0.15          # la liga de destino parece más difícil de lo que es
    assert lb(enc) == pytest.approx(-0.3, abs=0.03)
