"""F3 · capa de medida: recuperación simulada de σ y de la sobredispersión, calibración de la predictiva y mitades."""
import numpy as np
import pandas as pd
import pytest

from bbnorm5.medida import datos as D
from bbnorm5.medida import eb


def _sim(rng, fam, disp, U=300, sigma=0.35, centro=-0.8):
    filas, verdad = [], []
    for i in range(U):
        G = rng.integers(6, 34)
        eta = centro + rng.normal(0, sigma)
        if fam == "binomial":
            p = 1 / (1 + np.exp(-eta))
            n = rng.integers(0, 10, G).astype(float)
            pg = rng.beta(p * (1 - disp) / disp, (1 - p) * (1 - disp) / disp, G) if disp > 0 else np.full(G, p)
            k = rng.binomial(n.astype(int), pg).astype(float)
        else:
            lam = np.exp(eta)
            n = rng.uniform(5, 40, G)
            k = rng.poisson(rng.gamma(n * lam / disp, disp) if disp > 0 else n * lam).astype(float)
        m = n > 0
        k, n = k[m], n[m]
        filas.append(dict(K=k.sum(), N=n.sum(), G=len(n), N2g=(n ** 2).sum(), N3g=(n ** 3).sum(), Sk2=(k ** 2).sum(),
                          Skn=(k * n).sum(), rol="E"))
        verdad.append(eta)
    return pd.DataFrame(filas), np.array(verdad)


@pytest.mark.parametrize("fam,disp", [("binomial", 0.0), ("binomial", 0.08), ("poisson", 0.0), ("poisson", 1.0)])
def test_recupera_sigma_y_sobredispersion(fam, disp):
    rng = np.random.default_rng(11)
    u, _ = _sim(rng, fam, disp, centro=-0.8 if fam == "binomial" else -3.0)
    m = eb.ajustar(u, fam, True)
    assert m["disp"] == pytest.approx(disp, abs=0.03 if fam == "binomial" else 0.25)
    assert np.exp(m["par"][1]) == pytest.approx(0.35, abs=0.08)


def test_posterior_cubre_el_nivel_verdadero():
    rng = np.random.default_rng(3)
    u, eta = _sim(rng, "binomial", 0.0, U=600)
    m = eb.ajustar(u, "binomial", False)
    r = eb.resumen_posterior(m)
    p = 1 / (1 + np.exp(-eta))
    cob = ((p >= r["q10"]) & (p <= r["q90"])).mean()
    assert 0.75 <= cob <= 0.85


def test_predictiva_calibrada_con_el_modelo_correcto():
    """Datos simulados de una binomial jerárquica: el PIT de la segunda mitad es uniforme (cobertura 80 % ± 4)."""
    rng = np.random.default_rng(8)
    U = 800
    p = 1 / (1 + np.exp(-(-0.5 + rng.normal(0, 0.4, U))))
    N1, N2 = rng.integers(20, 200, U), rng.integers(20, 200, U)
    u1 = pd.DataFrame({"K": rng.binomial(N1, p), "N": N1, "N2g": N1 * 5.0, "rol": "E"})
    K2 = rng.binomial(N2, p)
    m = eb.ajustar(u1, "binomial", False)
    t = eb.muestras_tasa(m, 400, rng)
    s = eb.muestras_conteo(t, N2, N2 * 5.0, "binomial", 0.0, rng)
    r = eb.evaluar(s, K2, True, rng)
    assert (np.abs(r["pit"] - 0.5) <= 0.4).mean() == pytest.approx(0.80, abs=0.04)


def test_dispersion_cero_si_no_hay_variacion_entre_partidos():
    u = pd.DataFrame({"K": [10.0, 20.0], "N": [20.0, 40.0], "G": [2, 2], "Sk2": [50.0, 200.0], "Skn": [100.0, 400.0],
                      "N2g": [200.0, 800.0], "N3g": [2000.0, 16000.0], "rol": "E"})
    assert eb.dispersion_momentos(u, "binomial") == 0.0


def test_mitades_por_fecha_y_suficientes():
    d = pd.DataFrame({"persona_v5": "P1", "liga": "acb", "temporada": "2024-25", "rol": "E",
                      "fecha": ["2024-10-01", "2024-10-08", "2024-10-15", "2024-10-22", "2024-10-29"],
                      "game_id": list("abcde"), "fg3m": [1, 2, 0, 3, 1], "fg3a": [3, 4, 0, 5, 2], "min": 20.0})
    orden = d.groupby(D.CLAVE).cumcount()
    d["mitad"] = np.where(orden < np.ceil(5 / 2), 1, 2)
    u1 = D.unidad_metrica(d, "t3_pct", 1)
    assert u1[["K", "N", "G"]].iloc[0].tolist() == [3.0, 7.0, 2]      # el partido sin intentos no cuenta
    u2 = D.unidad_metrica(d, "t3_pct", 2)
    assert u2[["K", "N", "N2g"]].iloc[0].tolist() == [4.0, 7.0, 29.0]


def test_binneg1_estable_igual_a_la_forma_gamma():
    """La log-verosimilitud BinNeg1 de la NUTS (forma estable Σ log(m + jδ)) es la misma que con gammaln."""
    numpyro = pytest.importorskip("numpyro")
    numpyro.enable_x64()
    import jax.numpy as jnp
    from scipy import special
    from bbnorm5.medida import nuts
    k = np.array([0.0, 1.0, 3.0, 7.0])
    m = np.array([0.5, 1.2, 2.0, 3.0])
    for d in (0.4, 1e-3, 2.0):
        a = np.array(nuts._loglik(jnp.array(k), jnp.ones(4), jnp.log(jnp.array(m)), "poisson", True, jnp.log(d)))
        s = m / d
        b = (special.gammaln(k + s) - special.gammaln(s) - special.gammaln(k + 1) - s * np.log1p(d)
             + k * (np.log(d) - np.log1p(d)))
        assert np.abs(a - b).max() < 1e-8


def test_rol_sin_datos_no_se_va_al_borde():
    """Un rol con unidades de exposición mínima y k = 0 queda cerca de la media de la liga, no en el borde."""
    rng = np.random.default_rng(4)
    u, _ = _sim(rng, "poisson", 0.0, U=300, centro=-3.8)
    x = pd.DataFrame({"K": 0.0, "N": rng.uniform(0.5, 3, 20), "G": 1, "N2g": 1.0, "N3g": 1.0, "Sk2": 0.0, "Skn": 0.0,
                      "rol": "X"})
    m = eb.ajustar(pd.concat([u, x], ignore_index=True), "poisson", False)
    mu = dict(zip(m["roles"], m["par"][:len(m["roles"])]))
    assert abs(mu["X"] - mu["E"]) < 1.5


def test_sigma_comun_liga_da_una_fila_por_temporada():
    """Con σ común a la liga (etiquetas «temporada|rol») los hiperparámetros salen por temporada con sus medias."""
    from bbnorm5.medida import validacion as V
    rng = np.random.default_rng(2)
    a, _ = _sim(rng, "binomial", 0.0, U=200, centro=-0.4)
    b, _ = _sim(rng, "binomial", 0.0, U=200, centro=-1.2)
    u = pd.concat([a.assign(temporada="2023-24"), b.assign(temporada="2024-25")], ignore_index=True)
    u = V._etiquetar(u, True)
    m = eb.ajustar(u, "binomial", False)
    h = V._hiper(m, u, liga="x", temporada="todas", metrica="t3_pct", modelo="jer", datos="temporada")
    assert [x["temporada"] for x in h] == ["2023-24", "2024-25"]
    assert h[0]["mu_E"] == pytest.approx(-0.4, abs=0.1) and h[1]["mu_E"] == pytest.approx(-1.2, abs=0.1)
    assert h[0]["sigma"] == h[1]["sigma"] == pytest.approx(0.35, abs=0.08)
