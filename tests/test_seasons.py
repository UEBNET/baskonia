"""Histórico de temporadas y guardado en config de lo que descubren las fuentes (semillas BBL)."""
from __future__ import annotations

import copy
import json

from bbstats.adapters.bbl import BBLAdapter
from bbstats.config import configured_seasons, load_config, season_range, update_league_config
from bbstats.pipeline import run, run_seasons

import synth
from conftest import FakeHttp


def test_season_range_newest_first():
    assert season_range("2020-21", "2026-27") == ["2026-27", "2025-26", "2024-25", "2023-24", "2022-23",
                                                  "2021-22", "2020-21"]
    assert season_range("2026-27", "2025-26") == ["2026-27", "2025-26"]
    assert configured_seasons({"temporada_inicial": "2024-25", "temporada_por_defecto": "2026-27"}) == \
        ["2026-27", "2025-26", "2024-25"]
    assert configured_seasons(load_config())[-1] == "2020-21"


def test_block_starts():
    assert BBLAdapter.block_starts([5, 1, 2, 3, 40, 41, 300], 30) == [1, 40, 300]


def test_update_league_config_memory_and_disk(tmp_path):
    p = tmp_path / "sources.json"
    p.write_text(json.dumps({"ligas": {"bbl": {"temporadas": {"2025-26": {"semillas": [1]}}}}}), encoding="utf-8")
    cfg = load_config(p)
    assert update_league_config(cfg, "bbl", {"temporadas": {"2024-25": {"semillas": [7, 9]}}})
    disk = json.loads(p.read_text(encoding="utf-8"))
    for c in (cfg, disk):
        assert c["ligas"]["bbl"]["temporadas"] == {"2025-26": {"semillas": [1]}, "2024-25": {"semillas": [7, 9]}}
    assert "_path" not in disk
    assert not update_league_config({"ligas": {}}, "bbl", {"x": 1})  # sin fichero: sólo memoria


def _bbl_config(config, tmp_path):
    cfg = copy.deepcopy(config)
    cfg["ligas"] = {"bbl": cfg["ligas"]["bbl"]}
    # Sólo se conoce un id de una temporada posterior: 2025-26 (pasada) se descubre bajando desde ahí.
    cfg["ligas"]["bbl"].update(temporadas={"2026-27": {"semillas": [synth.FIRST_ID + 100]}}, paso_busqueda=4)
    p = tmp_path / "sources.json"
    p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return load_config(p), p


def test_bbl_discovered_seeds_are_saved(config, router, tmp_path):
    cfg, path = _bbl_config(config, tmp_path)
    rep = run(config=cfg, temporada="2025-26", http_factory=lambda: FakeHttp(router), paralelo=False)
    (bbl,) = rep["ligas"]
    assert bbl["estado"] == "ok" and bbl["jugadores"] > 0
    expected = {"semillas": [synth.FIRST_ID]}
    assert json.loads(path.read_text(encoding="utf-8"))["ligas"]["bbl"]["temporadas"]["2025-26"] == expected
    assert cfg["ligas"]["bbl"]["temporadas"]["2025-26"] == expected

    # Segunda vez: usa las semillas guardadas, sin volver a buscar desde la temporada posterior.
    http = FakeHttp(router)
    run(config=load_config(path), temporada="2025-26", http_factory=lambda: http, paralelo=False)
    probed = [u for u in http.calls if "/spiele/" in u]
    assert probed and all(int(u.rsplit("/", 1)[1]) < synth.FIRST_ID + 40 for u in probed)


def test_run_seasons_writes_season_index(config, router, tmp_path):
    out = run_seasons(["2025-26", "2024-25"], ligas=["acb", "euroleague"], config=config,
                      http_factory=lambda: FakeHttp(router), paralelo=False)
    assert [r["temporada"] for r in out["informes"]] == ["2025-26", "2024-25"]
    idx = json.loads((tmp_path / "processed" / "temporadas.json").read_text(encoding="utf-8"))
    seasons = [s["temporada"] for s in idx["temporadas"]]
    assert seasons[0] == "2025-26"
    assert set(idx["temporadas"][0]["ligas"]) == {"acb", "euroleague"}
