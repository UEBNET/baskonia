"""Actualización rápida de la temporada en curso (bbactualiza): el histórico no se toca y las reglas de mezcla v3.2
se reproducen."""
from __future__ import annotations

import gzip

import numpy as np
import pandas as pd
import pytest

from bbactualiza import capas, normalizacion as N


def _csv(p, df, **kw):
    df.to_csv(p, index=False, **kw)
    return p.read_bytes() if not str(p).endswith(".gz") else gzip.open(p).read()


def test_empalmar_conserva_el_historico_byte_a_byte(tmp_path):
    df = pd.DataFrame({"temporada": ["2024-25"] * 3 + ["2025-26"] * 2 + ["2026-27"] * 2,
                       "player_id": ["1", "2", "3", "1", "2", "1", "9"], "x": [0.1, 2.0, np.nan, 3.25, 4.0, 5.0, 6.0],
                       "pais": ["NA", "ES", "", "FR", "IT", "ES", "US"]})
    p = tmp_path / "t.csv"
    original = _csv(p, df)
    nuevo = pd.DataFrame({"temporada": ["2026-27"] * 3, "player_id": ["1", "9", "10"], "x": [5.5, 6.0, 7.125],
                          "pais": ["ES", "US", "BR"]})
    assert capas.empalmar(p, nuevo, "2026-27") == 3
    out = pd.read_csv(p, dtype=str, keep_default_na=False)
    # el histórico, idéntico (también «NA» = Namibia y la celda vacía); la temporada en curso, sustituida
    lineas_o, lineas_n = original.decode().splitlines(), p.read_text().splitlines()
    assert lineas_n[:6] == lineas_o[:6]
    assert list(out.loc[out["temporada"] == "2026-27", "player_id"]) == ["1", "9", "10"]
    assert out.loc[0, "pais"] == "NA"


def test_empalmar_sin_cambios_deja_el_fichero_igual(tmp_path):
    df = pd.DataFrame({"temporada": ["2025-26", "2026-27", "2026-27", "2024-25"], "v": [1.5, 2.25, np.nan, 4.0]})
    p = tmp_path / "t.csv.gz"
    original = _csv(p, df)
    capas.empalmar(p, pd.read_csv(p, dtype=str, keep_default_na=False, na_values=[""]), "2026-27")
    assert gzip.open(p).read() == original


def test_mapa_personas_conserva_ids_y_numera_las_nuevas():
    viejos = pd.DataFrame({"persona_id": [10, 10, 20], "liga": ["acb", "acb", "lba"], "player_id": ["a", "a", "b"],
                           "temporada": ["2024-25", "2025-26", "2025-26"]})
    t = pd.DataFrame({"persona_id": [1, 1, 2, 3], "liga": ["acb", "acb", "lba", "nba"], "player_id": ["a", "a", "b", "z"],
                      "temporada": ["2025-26", "2026-27", "2026-27", "2026-27"]})
    m = N.mapa_personas(t, viejos)
    assert m[1] == 10 and m[2] == 20          # la temporada en curso hereda el id de su historia
    assert m[3] == 21                          # persona nueva: por encima del máximo histórico


def test_recombinar_v32_sin_valor_cvae_es_la_v2():
    cfg = N._cfg_v32()
    base = pd.DataFrame({"liga": ["acb", "acb"], "pts_p100_am": [20.0, 18.0], "pts_p100_am_lo": [17.0, 15.0],
                         "pts_p100_am_hi": [23.0, 21.0], "pts_p100_am_pctel": [60.0, 40.0]})
    v3 = pd.DataFrame({"pts_p100_v3": [np.nan, 22.0], "pts_p100_v3_lo": [np.nan, 19.0], "pts_p100_v3_hi": [np.nan, 25.0],
                       "pts_p100_v3_sd_entre_z": [np.nan, 0.1], "pts_p100_v3_pctel": [np.nan, 70.0]})
    out = N.recombinar_v32(base, v3, {"acb": 7}, cfg)
    assert out.loc[0, "pts_p100_v31"] == pytest.approx(20.0)            # sin CVAE: sólo v2 (peso 0)
    assert out.loc[0, "pts_p100_v31_peso_cvae"] == 0.0
    w = out.loc[1, "pts_p100_v31_peso_cvae"]
    assert 0.0 <= w <= 1.0 and out.loc[1, "pts_p100_v31"] == pytest.approx(18.0 + w * 4.0, rel=0.05)
    # liga con menos temporadas que el mínimo: sólo v2
    assert N.recombinar_v32(base, v3, {"acb": 1}, cfg).loc[1, "pts_p100_v31_peso_cvae"] == 0.0
