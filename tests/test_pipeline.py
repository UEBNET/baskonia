from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from conftest import FakeHttp

from bbstats.pipeline import run
from bbstats.schema import COLUMN_NAMES

LEAGUES = ["euroleague", "acb", "nba", "gleague", "lba", "lnb"]


def _run(config, router, **kw):
    return run(config=config, http_factory=lambda: FakeHttp(router), paralelo=False, **kw)


@pytest.fixture
def first_run(config, router):
    rep = _run(config, router)
    out = Path(config["rutas"]["procesado"]) / "2025-26"
    return rep, out


def test_all_leagues_ok_and_same_columns(first_run):
    rep, out = first_run
    states = {l["liga"]: l["estado"] for l in rep["ligas"]}
    assert states == {l: "ok" for l in LEAGUES}, rep
    df = pd.read_csv(out / "todas_las_ligas.csv", low_memory=False)
    assert list(df.columns) == COLUMN_NAMES
    assert df.groupby("liga").size().to_dict() == {l: 32 for l in LEAGUES}
    for liga in LEAGUES:  # mismo esquema exacto en cada fichero de liga
        assert list(pd.read_csv(out / "ligas" / f"{liga}.csv", nrows=1).columns) == COLUMN_NAMES
    assert (out / "diccionario_columnas.csv").exists() and (out / "completitud.csv").exists()
    js = json.loads((out / "todas_las_ligas.json").read_text())
    assert len(js) == 192 and set(js[0]) == set(COLUMN_NAMES)


def test_raw_snapshots_saved(first_run, config):
    raw = Path(config["rutas"]["bruto"])
    for liga in LEAGUES:
        files = list((raw / liga / "2025-26").glob(f"{liga}_2025-26_*.json"))
        assert len(files) == 1
        doc = json.loads(files[0].read_text())
        assert set(doc) == {"meta", "payload"} and doc["meta"]["fecha_extraccion"]


def test_metrics_consistent_across_sources(first_run):
    """Los mismos partidos servidos por fuentes distintas deben dar las mismas métricas."""
    _, out = first_run
    df = pd.read_csv(out / "todas_las_ligas.csv", low_memory=False).set_index(["liga", "nombre"])
    full = ["ts_pct", "efg_pct", "usg_pct", "ast_pct", "oreb_pct", "dreb_pct", "stl_pct", "blk_pct",
            "pie", "per", "ortg", "drtg", "ws", "pts_p100", "game_score", "pir"]
    ref = df.loc["lba"]
    for liga in ["euroleague", "acb", "nba", "gleague"]:
        other = df.loc[liga].reindex(ref.index)
        for col in full:
            np.testing.assert_allclose(other[col], ref[col], rtol=1e-6, atol=1e-6, err_msg=f"{liga}.{col}")
    basic = ["ts_pct", "pts_p36", "fg3_pct", "game_score", "pts_pg"]
    lnb = df.loc["lnb"].reindex(ref.index)
    for col in basic:
        np.testing.assert_allclose(lnb[col], ref[col], rtol=1e-6, err_msg=f"lnb.{col}")


def test_context_quality_and_invariants(first_run):
    _, out = first_run
    df = pd.read_csv(out / "todas_las_ligas.csv", low_memory=False)
    q = df.groupby("liga")["calidad_contexto"].first().to_dict()
    assert q["lnb"] == "parcial" and all(q[l] == "completo" for l in LEAGUES if l != "lnb")
    for liga, g in df.groupby("liga"):
        assert np.isclose((g["per"] * g["min"]).sum() / g["min"].sum(), 15.0), liga
        if liga != "lnb":
            assert np.isclose((g["usg_pct"] * g["min"]).sum() / g["min"].sum(), 20.0), liga
    lba = df[df.liga == "lba"]
    assert lba["team_pace"].between(50, 120).all()
    nba = df[df.liga == "nba"]  # misma liga a 48 minutos: ritmo escalado 48/40
    np.testing.assert_allclose(nba["team_pace"].values, lba["team_pace"].values * 48 / 40)


def test_starts_and_double_doubles_from_boxscores(first_run, games):
    import synth
    _, out = first_run
    pl, _ = synth.season_totals(games)
    expected_gs = {P["name"]: P["gs"] for P in pl.values()}
    expected_dd = {P["name"]: P["dd2"] for P in pl.values()}
    df = pd.read_csv(out / "todas_las_ligas.csv", low_memory=False)
    for liga in ("acb", "lba"):
        g = df[df.liga == liga].set_index("nombre")
        assert g["gs"].to_dict() == pytest.approx(expected_gs), liga
        assert g["dd2"].to_dict() == pytest.approx(expected_dd), liga
    # La NBA no publica titularidades en ese endpoint: columna en blanco, no se elimina
    assert df[df.liga == "nba"]["gs"].isna().all()


def test_source_metrics_kept_and_blank_elsewhere(first_run):
    _, out = first_run
    df = pd.read_csv(out / "todas_las_ligas.csv", low_memory=False)
    nba = df[df.liga == "nba"]
    assert np.allclose(nba["src_ts_pct"], 55.0)          # 0.55 -> escala 0-100
    assert (nba["src_deflections"] == 10).all()
    assert nba["altura_cm"].iloc[0] == pytest.approx(203.2)
    assert df[df.liga == "acb"]["src_deflections"].isna().all()
    assert (df[df.liga == "euroleague"]["src_ts_pct"] == 55.5).all()


def test_reprocess_without_network(first_run, config):
    _, out = first_run
    before = pd.read_csv(out / "todas_las_ligas.csv", low_memory=False)
    offline = FakeHttp(lambda u, p: (_ for _ in ()).throw(AssertionError("no debe haber red")))
    rep = run(config=config, descargar=False, http_factory=lambda: offline, paralelo=False)
    assert all(l["estado"] == "ok" for l in rep["ligas"])
    after = pd.read_csv(out / "todas_las_ligas.csv", low_memory=False)
    pd.testing.assert_frame_equal(before, after)


def test_failed_download_falls_back_and_reuses_games(first_run, config, router):
    router.state["down"].add("feeds.incrowdsports.com")
    try:
        rep = _run(config, router)
    finally:
        router.state["down"].clear()
    st = {l["liga"]: l for l in rep["ligas"]}
    assert st["euroleague"]["estado"] == "ok_bruto_anterior" and st["euroleague"]["jugadores"] == 32
    assert st["acb"]["estado"] == "ok"
    raw = Path(config["rutas"]["bruto"])
    acb_files = sorted((raw / "acb" / "2025-26").glob("*.json"))
    assert len(acb_files) == 2
    latest = json.loads(acb_files[-1].read_text())
    assert latest["payload"]["reused_games"] == 12  # partidos finalizados no se vuelven a pedir


def test_one_league_error_does_not_stop_others(config, router):
    config["ligas"]["bbl"] = {"adaptador": "fiba_livestats", "activa": True, "minutos_partido": 40}
    rep = _run(config, router)
    st = {l["liga"]: l["estado"] for l in rep["ligas"]}
    assert st["bbl"] == "error" and st["acb"] == "ok"
