"""v3.2: t de Student (B6), interruptores de ablación (B1), pesos por métrica (B2), recalibración conforme del
simulador (A4) y vara de destino (cualquier liga a 0)."""
import math

import numpy as np
import pandas as pd
import pytest

torch = pytest.importorskip("torch")

from bbnorm3 import config, datos, modelo, niveles  # noqa: E402
from test_bbnorm3 import _caso_comb, tabla_sintetica  # noqa: E402

CFG32 = config.RAIZ / "configs" / "normalization_v32.yaml"


def _cfg(**c):
    base = {"entrenamiento.pasos": 60, "latente.K": 3, "red.oculta_codificador": 32, "red.oculta_decodificador": 16,
            "entrenamiento.ipw": False, "inferencia.refinar_pasos": 0}
    c32 = config.cargar(CFG32)
    c32 = c32.get("_completa", c32)          # las pruebas usan la configuración completa (antes de la ablación)
    return config.con(c32, **{**base, **c})


@pytest.fixture(scope="module")
def datos_sint():
    t = tabla_sintetica()
    return t, datos.construir(t, _cfg(), hasta_anio=2024)


def test_student_logverosimilitud_y_nu(datos_sint):
    from scipy.stats import t as tdist
    _, D = datos_sint
    m = modelo.CVAE(D, _cfg(), 1)
    assert m.student and 3.0 <= float(m.nu().min()) and float(m.nu().max()) <= 30.0
    assert float(m.nu()[0]) == pytest.approx(10.0, rel=1e-5)
    Y = torch.tensor([[0.3, -1.0]]); yh = torch.tensor([[0.0, 0.5]]); var = torch.tensor([[0.2, 0.5]])
    Mk = torch.ones_like(Y)
    m.nu_raw.data = m.nu_raw.data[:2]
    lp = float(m.log_verosimilitud(Y, yh, var, Mk))
    ref = sum(tdist.logpdf(float(Y[0, k]), df=10.0, loc=float(yh[0, k]), scale=math.sqrt(float(var[0, k])))
              for k in range(2))
    assert lp == pytest.approx(ref, rel=1e-5)


def test_normal_es_la_v31(datos_sint):
    _, D = datos_sint
    m = modelo.CVAE(D, _cfg(**{"red.verosimilitud": "normal"}), 1)
    Y = torch.tensor([[0.3]]); yh = torch.tensor([[0.0]]); var = torch.tensor([[0.2]])
    lp = float(m.log_verosimilitud(Y, yh, var, torch.ones_like(Y)))
    assert lp == pytest.approx(-0.5 * (math.log(2 * math.pi * 0.2) + 0.09 / 0.2), rel=1e-6)


def test_interruptores_ablacion(datos_sint):
    _, D = datos_sint
    m = modelo.CVAE(D, _cfg(**{"red.film": False, "red.cabezal_liga": False}), 1)
    with torch.no_grad():
        m.film_g.data += 5.0
        m.Vl.data += 5.0                  # sin FiLM ni cabezal, tocarlos no cambia la salida
        r = torch.zeros(4, m.K)
        a = m.decodificar(r, torch.zeros(4, dtype=torch.long), torch.zeros(4, dtype=torch.long))
        m.film_g.data -= 5.0
        m.Vl.data -= 5.0
        b = m.decodificar(r, torch.zeros(4, dtype=torch.long), torch.zeros(4, dtype=torch.long))
    assert torch.allclose(a, b)


def test_entrena_y_refina_con_student(datos_sint):
    _, D = datos_sint
    cfg = _cfg(**{"inferencia.refinar_pasos": 5})
    m = modelo.entrenar(D, cfg, 3, progreso=None)
    P = niveles.posterior(m, D, cfg)
    assert np.isfinite(P.media).all()


def test_huella_v32_ignora_inferencia():
    from bbnorm3.flujo import _huella
    a, b = _cfg(), _cfg(**{"inferencia.refinar_pasos": 200})
    assert _huella(a) == _huella(b)                      # B4 no reentrena
    c31 = config.cargar(config.RAIZ / "configs" / "normalization_v31.yaml")
    assert _huella(c31) != _huella(config.con(c31, **{"inferencia.refinar_pasos": 7}))   # la v3.1 sin cambios


def test_variantes_ablacion():
    from bbnorm3 import ablacion
    c32 = config.cargar(CFG32)
    V = ablacion.variantes(c32.get("_completa", c32))
    assert "completa" in V and V["sin_student"]["red"]["verosimilitud"] == "normal"
    assert V["sin_K8"]["latente"]["K"] == 4 and V["sin_ciclo"]["entrenamiento"]["ciclo_peso"] == 0.0


def test_pesos_por_metrica():
    from bbnorm3 import combinacion
    cfg = config.cargar(CFG32)
    j = _caso_comb()
    out = combinacion.combinar(j, cfg, peso_conocimiento=0.25, peso_metrica={j["metrica"].iloc[0]: 0.75})
    # el peso por métrica sustituye al general; conocimiento y salvaguardas prevalecen, como en la v3.1
    assert list(out["peso_cvae"]) == [0.75, 0.25, 0.0, 0.0]


def test_recalibracion_conforme_cubre_lo_nominal():
    """A4 (§5): dos colas por separado, pesos por recencia, contracción por grupos y corrección de muestra finita."""
    import os
    os.environ["CERNO_SIMULADOR"] = "v32"
    from bbfit import v32
    from bbfit.config import cargar
    cargar.cache_clear()
    c = cargar("simulation")
    rng = np.random.default_rng(0)
    n = 6000
    y = rng.gamma(2.0, 1.0, n) - 2.0                     # residuo asimétrico (cola derecha larga)
    p = pd.DataFrame({"pred": np.zeros(n), **{f"lo{a}": -0.5 for a in ("50", "80", "90")},
                      **{f"hi{a}": 0.5 for a in ("50", "80", "90")}})
    gd = pd.Series(np.where(rng.random(n) < 0.5, "europa", "feb"))
    go = pd.Series(np.where(rng.random(n) < 0.2, "ncaa", "resto"))
    ok = np.ones(n, bool)
    w = np.ones(n)
    f = v32.ajustar_recalibracion(p, y, ok, gd, go, w, c)
    q = v32.aplicar_recalibracion(p, f, gd, go)
    for a, nominal in (("50", 0.5), ("80", 0.8), ("90", 0.9)):
        dentro = (y >= q[f"lo{a}"]) & (y <= q[f"hi{a}"])
        assert dentro.mean() == pytest.approx(nominal, abs=0.02)
        # cada cola deja fuera ≈ (1 − α)/2
        assert (y < q[f"lo{a}"]).mean() == pytest.approx((1 - nominal) / 2, abs=0.015)
    # sin intervalo propio (A2): semiamplitudes con signo
    p2 = p.assign(**{f"{s_}{a}": np.nan for a in ("50", "80", "90") for s_ in ("lo", "hi")})
    f2 = v32.ajustar_recalibracion(p2, y, ok, gd, go, w, c)
    assert f2["90"]["tipo"] == "semiamplitud"
    q2 = v32.aplicar_recalibracion(p2, f2, gd, go)
    assert ((y >= q2["lo90"]) & (y <= q2["hi90"])).mean() == pytest.approx(0.9, abs=0.02)
    # pesos por recencia: el corte anterior pesa 1, el de antes ρ
    wr = v32.pesos_recencia(pd.Series(["2021-22", "2022-23"]), "2023-24", ["2021-22", "2022-23", "2023-24"], 0.5)
    assert list(wr) == [0.5, 1.0]
    os.environ.pop("CERNO_SIMULADOR")
    cargar.cache_clear()


def test_vara_destino_invariante_en_el_centro():
    """Poner a 0 la liga de destino no cambia el valor esperado; con d = EuroLeague se recupera la v3.1."""
    from bbnorm3.destino import a_destino
    cdoc = {"metricas": {"pts_p100": {
        "transf": "id", "deriva": {}, "s": {"acb": 1.1, "euroleague": 1.0},
        "nodos": {"acb:2025-26": [-0.4, 0.004], "bbl:2025-26": [-0.7, 0.006]},
        "mu": {"acb|2025-26|A": 10.0, "euroleague|2025-26|A": 11.0}, "tau2": {"acb|A": 4.0, "euroleague|A": 4.0},
        "soporte": {}}}}
    nodos = ["acb:2025-26", "bbl:2025-26", "euroleague:2025-26"]
    S = np.array([[0.004, 0.003, 0.0], [0.003, 0.006, 0.0], [0.0, 0.0, 0.0]])
    cov = ({k: i for i, k in enumerate(nodos)}, S)
    fila = {"liga": "bbl", "temporada": "2025-26", "pts_p100_th": -0.2, "pts_p100_vj": 0.05, "pos3": "A", "edad": None}
    r = a_destino(fila, "pts_p100", "acb", "2025-26", cdoc, cov)
    assert r["z"] == pytest.approx((-0.2 + 0.4) / 1.1)
    assert r["valor"] == pytest.approx(10.0 + 2.0 * r["z"])
    # varianza con la covarianza del par (0,004 + 0,006 − 2·0,003), no con la suma de marginales
    assert r["sd_z"] == pytest.approx(math.sqrt(0.05 + 0.004) / 1.1)
    el = a_destino(fila, "pts_p100", "euroleague", "2025-26", cdoc, cov)
    assert el["z"] == pytest.approx(-0.2) and el["sd_z"] == pytest.approx(math.sqrt(0.05 + 0.006))


def test_configuracion_final_quita_las_piezas():
    """La decisión de la ablación se aplica al cargar la configuración v3.2 (y la completa queda en _completa)."""
    c = config.cargar(CFG32)
    q = c["ablacion"].get("quitadas") or []
    if "student" in q:
        assert c["red"]["verosimilitud"] == "normal" and c["_completa"]["red"]["verosimilitud"] == "student"
    if "K8" in q:
        assert c["latente"]["K"] == 4
