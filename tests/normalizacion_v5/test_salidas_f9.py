"""F9 · Tests del contrato de salida: sello, recalibración por grupo, umbrales y formato de la v3.2."""
import numpy as np
import pandas as pd

from bbnorm5.salidas import destinos as SD
from bbnorm5.validacion import recalibracion as VR

REGLAS = {"alta_exposicion": 3.0, "alta_temporadas": 2, "alta_conectividad": 0.25, "baja_exposicion": 1.0,
          "baja_conectividad": 0.5}


def test_sello_regla_explicita():
    e = np.array([5.0, 5.0, 0.5, 2.0, 5.0, 5.0])
    h = np.array([3, 1, 3, 3, 3, 3])
    c = np.array([0.0, 0.0, 0.0, 0.1, 0.3, 0.6])
    assert list(SD.sello(e, h, c, REGLAS)) == ["alta", "media", "baja", "media", "media", "baja"]


def test_grupo_recalibracion_como_v32_mas_misma_liga():
    lo = pd.Series(["acb", "acb", "feb1", "nba", "lnb", "acb"])
    ld = pd.Series(["acb", "euroleague", "acb", "lba", "bbl", "gleague"])
    assert list(VR.grupo(lo, ld)) == ["misma_liga", "a_euroleague", "feb", "nba_gleague", "europa", "nba_gleague"]


def test_factores_llevan_la_cobertura_al_80():
    rng = np.random.default_rng(0)
    n = 20000
    y = rng.normal(0, 1, n)
    # intervalo del 80 % demasiado ancho (×1,5): el factor debe ser ≈ 1/1,5
    z90 = 1.2816 * 1.5
    p = pd.DataFrame({"obs": y, "q50": 0.0, "q10": -z90, "q90": z90, "metrica": "m",
                      "liga_ult": "acb", "liga": "acb", "persona_v5": np.arange(n).astype(str)})
    for q in (0.025, 0.05, 0.25, 0.75, 0.95, 0.975):
        p[f"q{q * 100:g}".replace(".", "_")] = 1.5 * np.quantile(rng.normal(size=5000), q)
    f = VR.factores(p)
    assert abs(f["metrica"]["m"] - 1 / 1.5) < 0.03
    r = VR.aplicar(p, f)
    cob = ((r["obs"] >= r["q10"]) & (r["obs"] <= r["q90"])).mean()
    assert abs(cob - 0.8) < 0.01


def test_umbrales_con_respaldo_de_liga():
    filas = []
    rng = np.random.default_rng(1)
    for liga, roles in (("a", ["E", "I"]), ("b", ["X"])):
        for r in roles:
            for i in range(30):
                filas.append({"persona_v5": f"{liga}{r}{i}", "metrica": "m", "anio": 2025, "liga": liga, "rol": r,
                              "min_temp": 500.0, "K": float(rng.integers(10, 50)), "N": 100.0})
    o = pd.DataFrame(filas)
    u = SD.umbrales(o, "m", 2026)
    assert set(zip(u["liga"], u["rol"])) == {("a", "E"), ("a", "I"), ("a", "todos"), ("b", "X"), ("b", "todos")}
    assert (u["umbral_p25"] <= u["umbral_p50"]).all() and (u["umbral_p50"] <= u["umbral_p75"]).all()


def test_tiro_compuesto_formula_exacta_con_intervalos_estrechos():
    from bbnorm5.salidas import derivadas as DV
    v = {"t2_pct": 0.55, "t3_pct": 0.35, "tl_pct": 0.78, "tpar": 0.40, "ftr": 0.25}
    q = {m: (np.array([x * 0.999]), np.array([x]), np.array([x * 1.001])) for m, x in v.items()}
    r = DV.tiro_compuesto(q, np.eye(5), np.random.default_rng(0), cuantiles=(0.5,))
    efg = (1 - 0.4) * 0.55 + 1.5 * 0.4 * 0.35
    ts = (2 * 0.6 * 0.55 + 3 * 0.4 * 0.35 + 0.25 * 0.78) / (2 * (1 + 0.44 * 0.25))
    assert abs(r["efg_pct"][0.5][0] - efg) < 1e-3 and abs(r["ts_pct"][0.5][0] - ts) < 1e-3


def test_por_100_conversion():
    from bbnorm5.salidas import derivadas as DV
    assert np.isclose(DV.por_100(np.array([0.10]), "oreb_p100", 0.45)[0], 4.5)
    assert np.isclose(DV.por_100(np.array([0.02]), "stl_pct", 0.7)[0], 2.0)      # la oportunidad ya es la posesión
