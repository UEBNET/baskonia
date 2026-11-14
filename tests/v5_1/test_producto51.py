"""v5.1 F6 · producto para el artifact: superposición sobre la v3.2 y conversión de vara."""
import numpy as np
import pandas as pd

from bbnorm5.salidas import producto51 as P


def _v32():
    base = {"liga": ["acb", "acb", "ligau"], "player_id": ["1", "2", "3"], "team_id": ["10", "10", "20"],
            "fuente_norm": "V3.2"}
    for c in P.COLUMNAS:
        base[c] = [1.0, 2.0, 3.0]
    return pd.DataFrame(base)


def test_aplicar_solo_toca_filas_y_metricas_de_la_mascara():
    v = _v32()
    s = v.iloc[[0]][P.CLAVE].copy()
    for c in P.COLUMNAS:
        s[c] = 9.0
    s["v51_comb"], s["v51_solo"] = 1 << P.ORDEN.index("fg3_pct"), 0
    a = P.aplicar(v, s)
    assert len(a) == 3 and list(a["fuente_norm"]) == ["V5.1", "V3.2", "V3.2"]
    assert a.loc[0, "fg3_pct"] == 9.0 and a.loc[0, "fg3_pct_pctel"] == 9.0
    assert a.loc[0, "pts_p100"] == 1.0                      # métrica sin bit: sigue la v3.2
    assert a.loc[1, "fg3_pct"] == 2.0 and a.loc[2, "fg3_pct"] == 3.0


def test_aplicar_sin_superposicion_es_la_v32():
    v = _v32()
    a = P.aplicar(v, pd.DataFrame(columns=P.CLAVE + P.COLUMNAS + ["v51_comb", "v51_solo"]))
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
