"""F10 · Tests de los prototipos aguas abajo (no tocan el producto)."""
import numpy as np
import pandas as pd

from bbnorm5.aguas_abajo import landing as LD

CFG = {"semilla": 1, "bootstrap": 200,
       "landing": {"min_minutos": 300, "identificable": {"min_personas": 100, "semiancho_ic95": 0.10},
                   "relevante": 0.10}}


def _sintetico(delta: float, n: int = 1500, seed: int = 0) -> pd.DataFrame:
    """Residuos ya ajustados: estables con media 0 y cambios de ACB a LBA con media δ (en DT)."""
    rng = np.random.default_rng(seed)
    filas = []
    for i in range(n):
        cambia = i % 3 == 0
        filas.append({"persona_v5": f"P{i}", "metrica": "t3_pct", "liga_ult": "acb", "liga": "lba" if cambia else "acb",
                      "fase": "primera" if cambia else "estable", "grupo": "europa" if cambia else "misma_liga",
                      "grupo_prev": "", "r": 0.0, "r_adj": rng.normal(delta if cambia else 0.0, 1.0), "r_adj_pub": 0.0,
                      "var_lambda": 0.0, "v": 1.0, "deriv": 0.25})
    return pd.DataFrame(filas)


def test_landing_recupera_delta_inyectado():
    d = _sintetico(-0.30, n=6000, seed=7)
    t = LD.estimar(CFG, d)
    r = t[(t["grupo"] == "europa") & (t["fase"] == "primera")].iloc[0]
    x = d.loc[d["fase"] == "primera", "r_adj"]
    assert np.isclose(r["delta"], x.mean())                               # estimador: media por persona
    assert abs(r["se"] / (x.std() / np.sqrt(len(x))) - 1) < 0.15          # bootstrap ≈ error típico analítico
    assert abs(r["delta"] + 0.30) < 4 * r["se"]
    assert r["relevante"] and r["identificable"]


def test_landing_sin_efecto_no_es_relevante():
    t = LD.estimar(CFG, _sintetico(0.0, seed=3))
    r = t[(t["grupo"] == "europa") & (t["fase"] == "primera")].iloc[0]
    assert not r["relevante"]


def test_landing_error_de_traduccion_ensancha_el_ic():
    d = _sintetico(-0.30)
    t0 = LD.estimar(CFG, d).query("grupo == 'europa'").iloc[0]
    t1 = LD.estimar(CFG, d.assign(var_lambda=0.04)).query("grupo == 'europa'").iloc[0]
    assert t1["se_traduccion"] > 0.15 and t1["se"] > 2 * t0["se"]


# ------------------------------------------------------------------ prototipo por partido
from bbnorm5.aguas_abajo import por_partido as PP


def test_cuantil_y_cdf_son_inversas():
    p = np.array([0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95])
    v = np.array([[2.0, 4.0, 8.0, 12.0, 16.0, 20.0, 24.0], [10.0, 11.0, 12.0, 15.0, 18.0, 19.0, 21.0]])
    u = np.array([[0.07, 0.3, 0.5, 0.88], [0.12, 0.26, 0.6, 0.93]])
    x = PP.cuantil(u, p, v)
    for i in range(2):
        assert np.allclose(PP.cdf(x[i], p, np.repeat(v[i:i + 1], 4, axis=0)), u[i], atol=1e-6)


def test_correlacion_entre_companeros_recupera_la_intraclase():
    rng = np.random.default_rng(5)
    g = np.repeat(np.arange(600), 4)
    z = np.sqrt(0.3) * rng.standard_normal(600)[g] + np.sqrt(0.7) * rng.standard_normal(len(g))
    d = pd.DataFrame({"temporada_d": "2024-25", "liga_d": "acb", "team_d": g.astype(str), "z": z})
    assert abs(PP._corr_companeros(d, ["temporada_d", "liga_d", "team_d"], "z") - 0.3) < 0.06


def test_dependencia_minutos_produccion_en_la_simulacion():
    q = [0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.975]
    fila = {**{f"v_min_{s}": m for (s, _), m in zip(PP.Q_V33, [5, 8, 12, 20, 26, 30, 33])},
            **{f"v_C_{s}": m for (s, _), m in zip(PP.Q_V33, [1, 2, 4, 8, 12, 15, 17])},
            **{f"v33_{s}": m for (s, _), m in zip(PP.Q_V33, [12, 14, 17, 21, 25, 28, 30])},
            **{f"{PP.MODELO}__{s}": m for s, m in zip(["q2_5", "q5", "q10", "q25", "q50", "q75", "q90", "q95", "q97_5"],
                                                       [10, 12, 14, 17, 21, 25, 28, 30, 32])},
            "gm": 40.0, "temporada_d": "2024-25", "liga_d": "acb", "team_d": "1"}
    d = pd.DataFrame([fila])
    dep = {"rho_mp": 0.0, "eq_m": 0.0, "eq_p": 0.0, "liga_p": 0.0}
    rng = np.random.default_rng(0)
    s1 = PP.simular(d, dep, 4000, rng, rho_mp=1.0)
    s0 = PP.simular(d, dep, 4000, rng, rho_mp=0.0)
    from scipy import stats
    assert stats.spearmanr(s1["M"][0], s1["P"][0]).statistic > 0.99
    assert abs(stats.spearmanr(s0["M"][0], s0["P"][0]).statistic) < 0.05
    # con ρ = 1 la contribución es más dispersa que con ρ = 0
    assert np.std(s1["C_v5"][0]) > np.std(s0["C_v5"][0])


# ------------------------------------------------------------------ híbrido v5 / v3.2
from bbnorm5.aguas_abajo import hibrido as HB


def _casos_hibrido(n=400, seed=2):
    rng = np.random.default_rng(seed)
    y = rng.normal(0, 1, n)
    filas = {"real": y, "metrica": "t3_pct", "persona_v5": [f"P{i}" for i in range(n)]}
    for mod, sesgo in (("v5", 0.4), ("v3.2", -0.4)):            # errores opuestos: la mezcla debe ganar a ambas
        c = sesgo + rng.normal(0, 0.3, n)
        filas[f"{mod}__q50"] = c
        for a, z in ((50, 0.674), (80, 1.2816), (90, 1.645)):
            filas[f"{mod}__lo{a}"], filas[f"{mod}__hi{a}"] = c - z, c + z
    d = pd.DataFrame(filas)
    d["wis_v5"], d["wis_v3.2"] = HB._wis_mezcla(d, 1.0), HB._wis_mezcla(d, 0.0)
    return d


def test_mezcla_con_peso_extremo_es_cada_version():
    d = _casos_hibrido()
    assert np.allclose(HB._wis_mezcla(d, 1.0), d["wis_v5"]) and np.allclose(HB._wis_mezcla(d, 0.0), d["wis_v3.2"])


def test_mezcla_gana_con_errores_opuestos():
    d = _casos_hibrido()
    dec = HB.decidir(d, 100, np.random.default_rng(0))
    assert 0.3 <= dec["w_mezcla"].iloc[0] <= 0.7
    assert HB._wis_mezcla(d, 0.5).mean() < min(d["wis_v5"].mean(), d["wis_v3.2"].mean())
