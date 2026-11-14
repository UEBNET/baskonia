"""v5.1 F2 · Tests del ensamblaje (recalibración de minutos y de la contribución)."""
import numpy as np
import pandas as pd

from bbnorm5.aguas_abajo import por_partido as PP
from bbnorm5.simulador51 import ensamblaje as EN


def _minutos(n=3000, ancho=12.0, seed=0):
    rng = np.random.default_rng(seed)
    med = rng.uniform(15, 30, n)
    y = med + rng.normal(0, 4.0, n)                         # la verdad: DT 4 → banda del 80 % ≈ ±5,1
    filas = {"min_real": y, "v_min_pred": med}
    for (q, p) in PP.Q_V33:                                  # el motor: demasiado ancho (DT 12)
        from scipy import stats
        filas[f"v_min_{q}"] = med + stats.norm.ppf(p) * ancho
    return pd.DataFrame(filas)


def test_escala_minutos_recupera_la_cobertura():
    d = _minutos()
    s = EN.escala_minutos(d)
    assert 0.3 <= s <= 0.4                                   # 4 / 12 ≈ 0,33
    v = EN._min_escalados(d, s)
    cob = np.mean((d["min_real"] >= v[:, 1]) & (d["min_real"] <= v[:, 5]))
    assert abs(cob - 0.8) < 0.03


def test_reescalar_conserva_la_mediana_y_no_da_negativos():
    rng = np.random.default_rng(1)
    D = rng.gamma(2.0, 3.0, (50, 400))
    R = EN._reescalar(D, 0.5)
    assert np.allclose(np.median(R, axis=1), np.median(D, axis=1))
    assert (R >= 0).all() and np.all(np.std(R, axis=1) < np.std(D, axis=1))


def test_corte_de_la_temporada_de_destino():
    from bbnorm5.simulador51 import nivel_kerno as NK
    assert NK._corte(2024) == "2023-24" and NK._corte(2025) == "2024-25"


def test_contraccion_latente_recupera_un_efecto_de_factor():
    """Si los δ de las métricas siguen exactamente Λγ (sin desviación propia), la contracción devuelve Λγ y τ = 0."""
    from bbnorm5.simulador51 import landing51 as L51
    L = pd.read_csv(L51.CARGAS, index_col=0)[L51.FACTORES]
    gam = np.array([3.0, -2.0, 1.5])                         # cargas de 0,04 a 0,8: señal de 0,1 a 1,5 DT
    rng = np.random.default_rng(3)
    se = np.full(len(L), 0.05)
    d = L.to_numpy() @ gam + rng.normal(0, 0.01, len(L))
    t = pd.DataFrame({"metrica": L.index, "fase": "segunda", "grupo": "EEUU_a_Europa", "delta": d, "se": se,
                      "delta_escala": d * 2})
    r = L51.contraer(t)
    assert np.allclose(r["delta_lat"], L.to_numpy() @ gam, atol=0.03)
    assert (r["se_lat"] <= r["se"] + 1e-9).all()               # contraer nunca da menos precisión


def test_traduccion_extrapolada_temporada_sin_nuts():
    """λ de una temporada sin NUTS: la de la última, con la varianza de la innovación de un año añadida."""
    import numpy as np
    from bbnorm5.simulador51 import incremental as I

    def original(z, ligas, t):
        i = z["temporadas"].index(t)
        return np.full(len(ligas), float(i)), np.full(len(ligas), 0.01)

    rng = np.random.default_rng(0)
    lam = rng.normal(size=(200, 3, 2))
    lam[:, :, 1] = lam[:, :, 0] + rng.normal(scale=0.1, size=(200, 3))
    z = {"temporadas": ["2024-25", "2025-26"], "lam": lam}
    f = I._traduccion_extrapolada(original)
    m, v = f(z, np.array(["a", "b"]), "2025-26")
    assert np.allclose(m, 1.0) and np.allclose(v, 0.01)
    m, v = f(z, np.array(["a", "b"]), "2026-27")
    assert np.allclose(m, 1.0)
    assert 0.01 + 0.005 < v[0] < 0.01 + 0.02          # 0,1² de innovación


def test_anterior():
    from bbnorm5.simulador51 import incremental as I
    assert I._anterior("2026-27") == "2025-26"
    assert I._anterior("2030-31") == "2029-30"
