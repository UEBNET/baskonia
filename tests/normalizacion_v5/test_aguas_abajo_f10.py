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
                      "grupo_prev": "", "r": 0.0, "r_adj": rng.normal(delta if cambia else 0.0, 1.0),
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
