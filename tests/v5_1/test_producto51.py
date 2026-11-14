"""v5.1 F6 · producto para el artifact: superposición sobre la v3.2 y conversión de vara."""
import numpy as np
import pandas as pd

from bbnorm5.salidas import producto51 as P


def _v32():
    base = {"liga": ["euroleague", "euroleague", "ligau"], "player_id": ["1", "2", "3"], "team_id": ["10", "10", "20"],
            "pos3": ["A", "A", "A"], "fuente_norm": "V3.2"}
    for c in P.COLUMNAS:
        base[c] = [1.0, 2.0, 3.0]
    return pd.DataFrame(base)


def _sup(v, m, x, x32=True):
    s = v.iloc[[0]][P.CLAVE].copy()
    s[m + "_v5"], s[m + "_v5_lo"], s[m + "_v5_hi"] = x, x - 1, x + 1
    return s


def test_aplicar_combina_con_la_v32_vigente_y_solo_donde_hay_v5():
    v = _v32()
    a = P.aplicar(v, _sup(v, "fg3_pct", 9.0), {"fg3_pct": 0.25})
    assert len(a) == 3 and list(a["fuente_norm"]) == ["V5.1", "V3.2", "V3.2"]
    assert np.isclose(a.loc[0, "fg3_pct"], 0.25 * 9 + 0.75 * 1)
    assert np.isclose(a.loc[0, "fg3_pct_lo"], 0.25 * 8 + 0.75 * 1)
    assert a.loc[0, "fg3_pct_pctel"] == 100.0                 # 3,0 > 2,0 entre los dos de la EuroLeague
    assert a.loc[0, "pts_p100"] == 1.0                        # métrica sin v5: sigue la v3.2
    assert a.loc[1, "fg3_pct"] == 2.0 and a.loc[2, "fg3_pct"] == 3.0
    assert a.loc[0, "v51_comb"] == 1 << P.ORDEN.index("fg3_pct") and a.loc[0, "v51_solo"] == 0


def test_aplicar_solo_v5_si_no_hay_v32():
    v = _v32()
    v.loc[0, "fg3_pct"] = np.nan
    a = P.aplicar(v, _sup(v, "fg3_pct", 9.0), {"fg3_pct": 0.25})
    assert a.loc[0, "fg3_pct"] == 9.0 and a.loc[0, "v51_solo"] == 1 << P.ORDEN.index("fg3_pct")


def test_aplicar_sin_superposicion_es_la_v32():
    v = _v32()
    a = P.aplicar(v, pd.DataFrame(columns=P.CLAVE), {})
    assert (a["fuente_norm"] == "V3.2").all()
    for c in P.COLUMNAS:
        assert np.allclose(a[c], v[c])


def test_convertir_identidad_en_la_euroleague_y_desplazamiento_en_el_enlace():
    L = ["acb", "euroleague"]
    vd = {"z80": 1.2815516, "ligas": L, "metricas": {"fg3_pct": {
        "familia": "binomial", "k": 100.0, "w": 0.3, "delta": {"acb": 0.2, "euroleague": 0.0},
        "sp": {"acb:2025-26": [0.0, 0.05]}}}}
    r = P.convertir(35.0, 30.0, 40.0, "fg3_pct", "acb", "2025-26", "euroleague", vd)
    assert np.allclose([r["valor"], r["lo"], r["hi"]], [35.0, 30.0, 40.0], atol=1e-6)
    r = P.convertir(35.0, 30.0, 40.0, "fg3_pct", "acb", "2026-27", "acb", vd)     # nodo ausente: el último
    from scipy import special
    assert np.isclose(r["valor"], 100 * special.expit(special.logit(0.35) - 0.2))
    assert r["lo"] < r["valor"] < r["hi"]
    assert P.convertir(35.0, 30.0, 40.0, "fg3_pct", "acb", "2025-26", "nba", vd) is None
