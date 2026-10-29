"""bbnorm3 (normalización v3, CVAE jerárquica): gauge, ciclo, varianza de pares, esquema y determinismo.

Datos sintéticos con niveles conocidos (3 ligas, 3 temporadas, jugadores puente) para que los tests sean rápidos
y no dependan de data/processed.
"""
import numpy as np
import pandas as pd
import pytest

torch = pytest.importorskip("torch")

from bbmodel.metricas import CATALOGO, EXPOSICIONES, destransformar  # noqa: E402
from bbnorm3 import config, datos, modelo, niveles, traduccion  # noqa: E402

NIVELES = {"euroleague": 0.0, "acb": -0.5, "feb1": -1.5}


def tabla_sintetica(semilla=0, n_por_liga=70):
    rng = np.random.default_rng(semilla)
    filas, pid = [], 0
    ligas = list(NIVELES)
    for liga in ligas:
        for _ in range(n_por_liga):
            pid += 1
            cap = rng.normal(NIVELES[liga], 0.6)
            pos = rng.choice(["E", "A", "I"])
            nac = int(rng.integers(1990, 2002))
            # un 30 % cambia de liga en la temporada siguiente (puentes)
            trayecto = [liga] * 3
            if rng.random() < 0.3:
                otra = ligas[(ligas.index(liga) + rng.choice([-1, 1])) % 3]
                trayecto = [liga, otra, otra]
            for k, anio in enumerate((2022, 2023, 2024)):
                lg = trayecto[k]
                rel = cap - NIVELES[lg]
                f = {"persona_id": pid, "liga": lg, "temporada": f"{anio}-{str(anio + 1)[-2:]}", "anio": anio,
                     "pos3": pos, "team_id": int(rng.integers(0, 6)), "min": float(rng.uniform(200, 1500)),
                     "anio_nac": nac, "player_id": f"p{pid}", "nombre": f"J{pid}", "gp": 30}
                for col, m in CATALOGO.items():
                    base = {"proporcion": 0.6, "raiz": 4.0, "log1": 2.5, "id": 10.0}[m.transf]
                    val = base + 0.25 * base * (0.8 * rel + 0.3 * rng.normal()) * (1 if sum(map(ord, col)) % 2 else -1)
                    f[col] = float(destransformar(val if m.transf != "proporcion" else np.clip(val, 0.05, 1.5), m.transf))
                for e in set(EXPOSICIONES.values()):
                    f[e] = f["min"] * 2
                filas.append(f)
    return pd.DataFrame(filas)


@pytest.fixture(scope="module")
def ajuste():
    cfg = config.con(config.cargar(), **{"entrenamiento.pasos": 150, "latente.K": 3, "red.oculta_codificador": 32,
                                         "red.oculta_decodificador": 16, "entrenamiento.ipw": False})
    t = tabla_sintetica()
    D = datos.construir(t, cfg, hasta_anio=2024)
    m = modelo.entrenar(D, cfg, semilla=7, progreso=None)
    P = niveles.posterior(m, D, cfg)
    return cfg, t, D, m, P


def test_determinismo(ajuste):
    cfg, t, D, m, _ = ajuste
    m2 = modelo.entrenar(D, cfg, semilla=7, progreso=None)
    assert torch.allclose(m.mu(), m2.mu())
    assert torch.allclose(m.log_psi, m2.log_psi)


def test_gauge_modelo(ajuste):
    _, _, D, m, _ = ajuste
    mu = m.mu().detach().numpy()
    w = m.w_comp.numpy()
    assert np.allclose((w[:, None] * mu).sum(0), 0, atol=1e-5)
    assert abs(float((m.w_liga * m.log_s()).sum())) < 1e-5


def test_invariancia_gauge_niveles(ajuste):
    """δ depende sólo de μ_c − μ_R: desplazar todos los μ por una constante no cambia los niveles."""
    _, _, D, m, P = ajuste
    R = D.comps.index("euroleague|2023-24")
    mu = P.media[P.nPS:P.nPS + P.nC]
    d1, J1 = traduccion.niveles(m, P, D, R, mu)
    d2, J2 = traduccion.niveles(m, P, D, R, mu + 0.37)
    assert np.allclose(d1, d2, atol=1e-5)
    assert np.allclose(J1, J2, atol=1e-5)


def test_orden_de_niveles(ajuste):
    """Con niveles sintéticos EL > ACB > FEB1, la v3 recupera el orden en las métricas que miden capacidad."""
    _, _, D, m, P = ajuste
    R = D.comps.index("euroleague|2023-24")
    d, _ = traduccion.niveles(m, P, D, R)
    i = {l: D.comps.index(f"{l}|2023-24") for l in NIVELES}
    k = datos.METRICAS.index("per")
    signo = 1 if sum(map(ord, "per")) % 2 else -1
    assert signo * d[i["feb1"], k] < signo * d[i["acb"], k] < signo * d[i["euroleague"], k] + 1e-6


def test_varianza_de_pares(ajuste):
    """Var(T(a→b)) = Var(δ_a) + Var(δ_b) − 2 Cov(δ_a, δ_b), comprobado por Monte Carlo con la covarianza conjunta."""
    _, _, D, m, P = ajuste
    R = D.comps.index("euroleague|2023-24")
    d, J = traduccion.niveles(m, P, D, R)
    cov = P.cov_mu()
    a, b = D.comps.index("acb|2023-24"), D.comps.index("feb1|2023-24")
    t = traduccion.traduccion_cruzada(d, J, cov, R, [(a, b)])[0]
    rng = np.random.default_rng(0)
    k_m = datos.METRICAS.index("per")
    # muestras de (μ_a − μ_R, μ_b − μ_R) por dimensión latente (independientes entre dimensiones)
    var_mc = 0.0
    for k in range(cov.shape[0]):
        idx = [a, b, R]
        C = cov[k][np.ix_(idx, idx)]
        x = rng.multivariate_normal(np.zeros(3), C, 20000)
        lin = J[a, k_m, k] * (x[:, 0] - x[:, 2]) - J[b, k_m, k] * (x[:, 1] - x[:, 2])
        var_mc += lin.var()
    assert t["sd"][k_m] ** 2 == pytest.approx(var_mc, rel=0.05)
    assert np.all(t["lo80"] <= t["media"]) and np.all(t["media"] <= t["hi80"])


def test_ciclo_exacto_en_latente(ajuste):
    """En el latente las traducciones se componen exactamente: T(a→b) + T(b→c) = T(a→c)."""
    _, _, D, m, P = ajuste
    R = D.comps.index("euroleague|2023-24")
    d, _ = traduccion.niveles(m, P, D, R)
    a, b, c = (D.comps.index(f"{l}|2023-24") for l in ("euroleague", "acb", "feb1"))
    assert np.allclose((d[a] - d[b]) + (d[b] - d[c]), d[a] - d[c])
    res = traduccion.residuo_ciclo(m, P, D, (a, b, c), n=50)
    assert res.shape == (len(datos.METRICAS),) and np.all(np.isfinite(res))


def test_esquema_normalizado_v3():
    """El normalizado v3 conserva todas las columnas del v1/v2 y añade las suyas."""
    from bbnorm3 import salidas
    v1 = pd.DataFrame({"persona_id": [1], "liga": ["acb"], "temporada": ["2025-26"], "per": [10.0], "per_obs": [12.0],
                       "per_A": [9.0], "per_B": [11.0], "per_lo": [8.0], "per_hi": [12.0], "per_pctel": [50.0],
                       "fuente_norm": ["A+B"], "per_A_am": [9.5], "per_am": [10.2], "per_am_lo": [8.1],
                       "per_am_hi": [12.3], "per_am_pctel": [51.0]})
    v3 = pd.DataFrame({"per_v3": [10.5], "per_v3_lo": [8.0], "per_v3_hi": [13.0], "per_v3_sd": [1.2],
                       "per_v3_pctel": [53.0]})
    out = salidas.combinar_normalizado(v1, v3, ["per"])
    assert list(out.columns[:len(v1.columns)]) == list(v1.columns)
    assert {"per_v3", "per_v3_lo", "per_v3_hi", "per_v1"}.issubset(out.columns)
    assert out["per_am"].iloc[0] == pytest.approx(10.5) and out["per_v1"].iloc[0] == pytest.approx(10.0)


def _caso_comb(n=4):
    from bbnorm3 import datos as dd
    esc = dd.Escala(c={"per": 10.0}, s={"per": 4.0}, sigma2={"per": {"todas": 1.0}}, recorte={"per": (-1e9, 1e9)})
    j = pd.DataFrame({"metrica": "per", "anio": 2024, "persona_id": range(n), "nombre": "x",
                      "liga_o": ["acb", "feb3", "acb", "acb"][:n], "liga_d": ["euroleague", "feb2", "lba", "bbl"][:n],
                      "real": 12.0, "real_z": 0.5, "v3": 0.0, "v3_lo": 0.0, "v3_hi": 0.0, "dentro_80_v3": True,
                      "v3_centro_z": 1.0, "v3_sd_z": 0.5, "v3_sd_entre_z": [0.1, 0.1, 0.1, 0.9][:n],
                      "v2_centro_z": 0.0, "v2_sd_z": 0.5, "temporadas_o": [4, 4, 1, 4][:n], "temporadas_d": 4})
    j.attrs["esc"] = esc
    return j


def test_combinacion_pesos_y_salvaguardas():
    from bbnorm3 import combinacion
    cfg = config.cargar(config.RAIZ / "configs" / "normalization_v31.yaml")
    out = combinacion.combinar(_caso_comb(), cfg, peso_conocimiento=0.25)
    # general 0,5; FEB3 por conocimiento 0,25; liga con 1 temporada → 0; redes que discrepan → 0
    assert list(out["peso_cvae"]) == [0.5, 0.25, 0.0, 0.0]
    assert out["v3_centro_z"].tolist() == pytest.approx([0.5, 0.25, 0.0, 0.0])
    assert "cvae_centro_z" in out and out["cvae_centro_z"].iloc[0] == pytest.approx(1.0)
    # la varianza de la mezcla incluye la separación de los dos centros
    assert out["v3_sd_z"].iloc[0] == pytest.approx(np.sqrt(0.25 + 0.25), rel=1e-6)


def test_cuantiles_mezcla():
    from scipy.stats import norm
    from bbnorm3.combinacion import _cuantiles_mezcla
    w, c3, s3, c2, s2 = (np.array([x]) for x in (0.3, 1.0, 0.5, -1.0, 0.8))
    lo, hi = _cuantiles_mezcla(w, c3, s3, c2, s2, (0.1, 0.9))
    F = lambda x: 0.3 * norm.cdf((x - 1) / 0.5) + 0.7 * norm.cdf((x + 1) / 0.8)  # noqa: E731
    assert F(lo[0]) == pytest.approx(0.1, abs=1e-6) and F(hi[0]) == pytest.approx(0.9, abs=1e-6)
