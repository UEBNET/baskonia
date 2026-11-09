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


# ------------------------------------------------------------------------------------- v4.2: tres artifacts
def _sitios(tmp_path):
    import json
    man = {"jugadores": {"ficheros": ["index.html", "datos/temporadas.json.gz.txt", "datos/2026-27/regular.json.gz.txt",
                                      "datos/actualizacion.json"],
                         "borrar_al_republicar": ["quintetos/datos/2026-27/acb.gz.txt"]},
           "equipos": {"ficheros": ["index.html", "datos/temporadas.json.gz.txt", "datos/actualizacion.json",
                                    "quintetos/datos/2026-27/acb.gz.txt", "quintetos/datos/2026-27/acb.extras.gz.txt",
                                    "quintetos/datos_v42/2026-27/acb.gz.txt"]},
           "metodologia": {"ficheros": ["index.html", "datos/temporadas.json.gz.txt", "datos/actualizacion.json",
                                        "quintetos/datos/2026-27/acb.gz.txt", "quintetos/datos_v42/2026-27/acb.gz.txt"]}}
    for s, m in man.items():
        (tmp_path / f"{s}.json").write_text(json.dumps({"sitio": s, **m}))
        (tmp_path / f"sitio_{s}.json").write_text(json.dumps({"sitio": s, "urls": {s: f"https://x/{s}"}}))
    return tmp_path


def test_repartir_por_sitio(tmp_path):
    import json
    from bbactualiza import sitios as S
    (tmp_path / "m").mkdir()
    car = _sitios(tmp_path / "m")
    loc = tmp_path / "f"
    loc.mkdir()
    rutas = ["datos/temporadas.json", "datos/temporadas.json.gz.txt", "datos/actualizacion.json",
             "datos/2026-27/regular.json.gz.txt", "quintetos/datos/2026-27/acb.gz.txt",
             "quintetos/datos/2026-27/gleague.gz.txt", "quintetos/datos/2026-27/gleague.extras.gz.txt",
             "quintetos/datos_v42/2026-27/gleague.gz.txt", "atlas/algo_nuevo/x.bin"]
    lote = {}
    for i, r in enumerate(rutas):
        f = loc / f"{i}.txt"
        f.write_text("x" * 10)
        lote[r] = str(f)
    pub = tmp_path / "pub"
    pub.mkdir()
    res = S.repartir(lote, pub, car)
    lotes = {s: json.loads((pub / f"lote_{s}_0.json").read_text()) for s in S.SITIOS}
    assert set(lotes["jugadores"]) == {"datos/temporadas.json.gz.txt", "datos/actualizacion.json",
                                       "datos/2026-27/regular.json.gz.txt"}       # nunca los quintetos borrados
    assert set(lotes["equipos"]) == {"datos/temporadas.json.gz.txt", "datos/actualizacion.json",
                                     "quintetos/datos/2026-27/acb.gz.txt", "quintetos/datos/2026-27/gleague.gz.txt",
                                     "quintetos/datos/2026-27/gleague.extras.gz.txt",
                                     "quintetos/datos_v42/2026-27/gleague.gz.txt"}
    assert "quintetos/datos/2026-27/gleague.extras.gz.txt" not in lotes["metodologia"]   # extras: sólo Equipos
    assert res["rutas_nuevas"]["quintetos/datos_v42/2026-27/gleague.gz.txt"] == ["equipos", "metodologia"]
    assert res["sin_sitio"] == ["atlas/algo_nuevo/x.bin"]
    assert res["duplicados_en_claro_omitidos"] == 1                                  # datos/temporadas.json
    assert res["sitios"]["equipos"]["url"] == "https://x/equipos"
    m = json.loads((car / "equipos.json").read_text())                          # la ruta nueva queda anotada
    assert "quintetos/datos_v42/2026-27/gleague.gz.txt" in m["ficheros"] and m["n_ficheros"] == len(m["ficheros"])
    assert S.repartir(lote, pub, car)["rutas_nuevas"] == {}                       # y la próxima vez ya es «manifiesto»


def test_trocear_respeta_limites(tmp_path):
    from bbactualiza import sitios as S
    rutas = {}
    for i in range(7):
        f = tmp_path / f"{i}"
        f.write_bytes(b"x" * 100)
        rutas[f"r{i}"] = str(f)
    t = S.trocear(rutas, max_mb=250, max_n=3)
    assert [len(x) for x in t] == [2, 2, 2, 1] and sum(len(x) for x in t) == 7
    assert [len(x) for x in S.trocear(rutas, max_mb=1e9, max_n=3)] == [3, 3, 1]


def test_manifiestos_reales_y_urls():
    from bbactualiza import sitios as S
    m = S.manifiestos()
    assert m["jugadores"]["url"].endswith("A7rufkL84rvRFcUBFBxFbC")
    assert all(m[s]["url"].startswith("https://claude.ai/artifact/") for s in S.SITIOS)
    assert not any(r.startswith("quintetos/datos/2026-27/") for r in m["jugadores"]["ficheros"])
