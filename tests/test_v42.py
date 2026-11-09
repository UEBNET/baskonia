"""CERNO v4.2 · tests de la normalización v4.2 (historial del jugador) y de sus salidas."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from bbequipo.v42 import historial as H


def _obs(ys, vs, pos="A", pid=1):
    return pd.DataFrame({"persona_id": pid, "anio": np.arange(2020, 2020 + len(ys)), "y": ys, "v": vs, "min": 500.0, "pos3": pos})


def test_filtro_kalman_cerrado():
    # una sola observación: posterior conjugada normal-normal exacta
    o = _obs([10.0], [4.0])
    f = H.filtrar(o, tau2=1.0, c=1.0, pp={"E": (0.0, 4.0), "A": (0.0, 4.0), "I": (0.0, 4.0)})
    assert abs(f["m"].iloc[0] - 5.0) < 1e-12 and abs(f["P"].iloc[0] - 2.0) < 1e-12
    # dos temporadas: la previa de la 2.ª es la posterior de la 1.ª más τ²
    o = _obs([10.0, 10.0], [4.0, 4.0])
    f = H.filtrar(o, tau2=1.0, c=1.0, pp={"E": (0.0, 4.0), "A": (0.0, 4.0), "I": (0.0, 4.0)})
    assert abs(f["P_pred"].iloc[1] - 3.0) < 1e-12 and f["P"].iloc[1] < f["P"].iloc[0]


def test_centrar_quita_la_media_de_cada_temporada():
    o = pd.concat([_obs([10.0, 12.0], [1.0, 1.0], pid=1), _obs([20.0, 22.0], [1.0, 1.0], pid=2)], ignore_index=True)
    c = H.centrar(o)
    assert np.allclose(c.groupby("anio")["y"].mean(), 0.0)


def test_examen_d1_y_versiones():
    ex = json.loads((H.SALIDA / "examen_d1.json").read_text(encoding="utf-8"))
    ver = json.loads((H.SALIDA / "version_por_metrica.json").read_text(encoding="utf-8"))
    for m, v in ex["metricas"].items():
        assert v["sello"] in ("ALTA", "MEDIA", "BAJA")
        if v["sello"] != "BAJA":
            assert ver[m].startswith("v4.2")                # la literal que pasa se usa
            assert 0.75 <= v["conjunto"]["cobertura_80"] <= 0.85
    assert sum(x.startswith("v4.2") for x in ver.values()) == 12


def test_d3_empalme_solo_temporada_en_curso():
    from bbequipo.v42 import actualizar as A
    previo = pd.DataFrame({"temporada": ["2025-26", "2025-26", "2026-27"], "unidad": ["a", "b", "a"], "v42": [1.0, 2.0, 3.0]})
    nuevo = pd.DataFrame({"temporada": ["2025-26", "2026-27", "2026-27"], "unidad": ["a", "a", "c"], "v42": [9.0, 4.0, 5.0]})
    d = A.empalmar(previo, nuevo, "2026-27")
    assert d[d["temporada"] == "2025-26"]["v42"].tolist() == [1.0, 2.0]       # cerradas: las de antes, intactas
    assert d[d["temporada"] == "2026-27"]["v42"].tolist() == [4.0, 5.0]
