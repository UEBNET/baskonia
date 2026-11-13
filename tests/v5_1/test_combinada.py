"""v5.1 F1 · Tests de la versión combinada."""
import numpy as np
import pandas as pd

from bbnorm5.salidas import combinada as CB
from bbnorm5.salidas import formato_v32 as F

CFG = {"pesos": {"rejilla": [0.0, 0.25, 0.5, 0.75, 1.0], "n0": 300, "sin_examen": 0.5}}


def _tabla():
    v = pd.DataFrame({"liga": ["euroleague", "euroleague", "acb", "acb"], "pos3": ["E", "E", "E", "E"],
                      "fg3_pct": [40.0, 30.0, 35.0, 33.0], "fg3_pct_lo": [35.0, 25.0, 30.0, 28.0],
                      "fg3_pct_hi": [45.0, 35.0, 40.0, 38.0], "fg3_pct_pctel": [50.0, 50.0, 50.0, 50.0],
                      "fg3_pct_v32": [38.0, 32.0, 34.0, np.nan], "fg3_pct_v32_lo": [33.0, 27.0, 29.0, np.nan],
                      "fg3_pct_v32_hi": [43.0, 37.0, 39.0, np.nan], "fuente_fg3_pct": ["V5", "V5", "V3.2", "V5"]})
    return v


def test_combinar_mezcla_donde_hay_las_dos():
    v = _tabla()
    F.combinar(v, {"fg3_pct": 0.25})
    assert np.isclose(v.loc[0, "fg3_pct"], 0.25 * 40 + 0.75 * 38) and np.isclose(v.loc[0, "fg3_pct_lo"], 0.25 * 35 + 0.75 * 33)
    assert v.loc[0, "fuente_fg3_pct"] == "COMB" and v.loc[0, "peso_v5_fg3_pct"] == 0.25
    assert v.loc[0, "fg3_pct_v5"] == 40.0                      # la v5 se conserva
    assert v.loc[2, "fg3_pct"] == 35.0 and v.loc[2, "fuente_fg3_pct"] == "V3.2"   # sin v5: queda la v3.2
    assert v.loc[3, "fg3_pct"] == 33.0 and v.loc[3, "fuente_fg3_pct"] == "V5"     # sin v3.2: queda la v5
    assert 0 <= v["fg3_pct_pctel"].min() and v["fg3_pct_pctel"].max() <= 100


def test_pesos_contraidos_hacia_la_mitad():
    rng = np.random.default_rng(0)
    n = 60
    y = rng.normal(0, 1, n)
    d = {"real": y, "metrica": "fg3_pct", "persona_v5": [f"P{i}" for i in range(n)]}
    for mod, s in (("v5", 0.0), ("v3.2", 1.5)):                 # la v5 es claramente mejor
        c = y * 0 + s
        d[f"{mod}__q50"] = c
        for a, z in ((50, 0.674), (80, 1.2816), (90, 1.645)):
            d[f"{mod}__lo{a}"], d[f"{mod}__hi{a}"] = c - z, c + z
    d = pd.DataFrame(d)
    from bbnorm5.aguas_abajo import hibrido as HB
    d["wis_v5"], d["wis_v3.2"] = HB._wis_mezcla(d, 1.0), HB._wis_mezcla(d, 0.0)
    p = CB.pesos(CFG, d).iloc[0]
    assert p["w_hat"] >= 0.75 and 0.5 < p["w"] < p["w_hat"]      # pocos casos: cerca de 0,5


def test_pesos_publicados_heredan_por_100():
    t = pd.DataFrame({"metrica": ["oreb_pct", "blk_pct"], "w": [0.4, 0.3]})
    w = CB.pesos_publicados(CFG, t)
    assert w["oreb_p100"] == 0.4 and w["blk_p100"] == 0.3 and w["pf_p40"] == 0.5
