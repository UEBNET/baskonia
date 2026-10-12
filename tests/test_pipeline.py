from __future__ import annotations

import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from conftest import FakeHttp

import synth
from bbstats.pipeline import run
from bbstats.schema import COLUMN_NAMES

LEAGUES = ["euroleague", "gleague", "acb", "lba", "bbl", "lnb", "nba"]
FULL_CONTEXT = ["euroleague", "gleague", "acb", "lba", "bbl", "nba"]
N_PLAYERS = 32  # 4 equipos x 8 jugadores


def _run(config, router, **kw):
    return run(config=config, http_factory=lambda: FakeHttp(router), paralelo=False, **kw)


def _read(out: Path) -> pd.DataFrame:
    return pd.read_csv(out / "todas_las_ligas.csv", low_memory=False, dtype={"player_id": str, "team_id": str})


@pytest.fixture
def first_run(config, router):
    rep = _run(config, router)
    return rep, Path(config["rutas"]["procesado"]) / "2025-26"


def test_all_leagues_ok_same_columns_and_phases(first_run):
    rep, out = first_run
    assert {l["liga"]: l["estado"] for l in rep["ligas"]} == {l: "ok" for l in LEAGUES}, rep
    df = _read(out)
    assert list(df.columns) == COLUMN_NAMES
    counts = df.groupby(["liga", "fase"]).size().unstack()
    assert (counts["regular"] == N_PLAYERS).all() and (counts["total"] == N_PLAYERS).all(), counts
    assert (counts["playoffs"] == N_PLAYERS).all(), counts  # los 4 equipos juegan playoffs en la liga sintética
    for liga in LEAGUES:
        assert list(pd.read_csv(out / "ligas" / f"{liga}.csv", nrows=1).columns) == COLUMN_NAMES
    for f in ("diccionario_columnas.csv", "completitud.csv", "indice.json", "por_fase/regular.json",
              "por_fase/playoffs.json", "por_fase/total.json", "todas_las_ligas.json"):
        assert (out / f).exists(), f
    from bbstats.pipeline import read_columnar_json
    rows = read_columnar_json(out / "por_fase" / "playoffs.json")
    assert len(rows) == len(LEAGUES) * N_PLAYERS and set(rows[0]) == set(COLUMN_NAMES)
    assert all(r["fase"] == "playoffs" for r in rows)
    idx = json.loads((out / "indice.json").read_text())
    assert set(idx["ligas"]) == set(LEAGUES) and idx["fases"] == ["regular", "playoffs", "total"]


def test_raw_snapshots_saved_gzipped(first_run, config):
    raw = Path(config["rutas"]["bruto"])
    for liga in LEAGUES:
        files = list((raw / liga / "2025-26").glob(f"{liga}_2025-26_*.json.gz"))
        assert len(files) == 1, liga
        doc = json.loads(gzip.decompress(files[0].read_bytes()))
        assert set(doc) == {"meta", "payload"} and doc["meta"]["fecha_extraccion"]


@pytest.mark.parametrize("phase", ["regular", "playoffs", "total"])
def test_metrics_consistent_across_sources(first_run, phase):
    """Los mismos partidos servidos por fuentes distintas deben dar las mismas métricas."""
    _, out = first_run
    df = _read(out)
    df = df[df.fase == phase].set_index(["liga", "nombre"])
    cols = ["pts", "min", "ts_pct", "efg_pct", "usg_pct", "ast_pct", "oreb_pct", "dreb_pct", "stl_pct", "blk_pct",
            "pie", "per", "ortg", "drtg", "ws", "pts_p100", "game_score", "team_pace"]
    ref = df.loc["acb"]
    for liga in FULL_CONTEXT:
        other = df.loc[liga].reindex(ref.index)
        for col in cols:
            np.testing.assert_allclose(other[col], ref[col], rtol=1e-6, atol=1e-6, err_msg=f"{liga}.{phase}.{col}")
    lnb = df.loc["lnb"].reindex(ref.index)
    for col in ["pts", "ts_pct", "pts_p36", "fg3_pct", "efg_pct"]:
        np.testing.assert_allclose(lnb[col], ref[col], rtol=1e-6, err_msg=f"lnb.{phase}.{col}")
    # los jugadores recuperados de su ficha no tienen pérdidas: métricas que las usan quedan en blanco
    full = ~lnb.index.str.endswith(str(synth.LNB_HIDDEN_K))
    for col in ["game_score", "usg_pct"]:
        np.testing.assert_allclose(lnb.loc[full, col], ref.loc[full, col], rtol=1e-6, err_msg=f"lnb.{phase}.{col}")
        assert lnb.loc[~full, col].isna().all()


def test_phase_context_columns(first_run, games):
    _, out = first_run
    df = _read(out)
    acb = df[df.liga == "acb"].set_index(["fase", "player_id"])
    po = acb.loc["playoffs"]
    rs = acb.loc["regular"]
    np.testing.assert_allclose(po["rs_ts_pct"], rs.loc[po.index, "ts_pct"])
    np.testing.assert_allclose(po["delta_ts_pct"], po["ts_pct"] - rs.loc[po.index, "ts_pct"], rtol=1e-6, atol=1e-6)
    assert acb.loc["regular"]["rs_ts_pct"].isna().all()  # sólo en filas de playoffs
    pl, _ = synth.season_totals(synth.by_phase(games, "playoffs"))
    assert po["gp"].sum() == sum(P["gp"] for P in pl.values())


def test_invariants_and_quality(first_run):
    _, out = first_run
    df = _read(out)
    q = df[df.fase == "total"].groupby("liga")["calidad_contexto"].first().to_dict()
    assert q["lnb"] == "parcial" and all(q[l] == "completo" for l in FULL_CONTEXT)
    for (liga, fase), g in df.groupby(["liga", "fase"]):
        g_per = g[g["per"].notna()]
        assert np.isclose((g_per["per"] * g_per["min"]).sum() / g_per["min"].sum(), 15.0), (liga, fase)
        if liga != "lnb":
            assert np.isclose((g["usg_pct"] * g["min"]).sum() / g["min"].sum(), 20.0), (liga, fase)


def test_source_specific_fields(first_run, games):
    _, out = first_run
    df = _read(out)
    tot = df[df.fase == "total"]
    pl, _ = synth.season_totals(games)
    exp_gs = {P["name"]: P["gs"] for P in pl.values()}
    for liga in ("acb", "lba", "bbl", "lnb", "nba", "euroleague"):
        got = tot[tot.liga == liga].set_index("nombre")["gs"].to_dict()
        assert got == pytest.approx(exp_gs), liga
    assert tot[tot.liga == "gleague"]["gs"].isna().all()       # la fuente no publica titularidades
    assert tot[tot.liga == "bbl"]["blka"].isna().all()         # la BBL no publica tapones recibidos
    assert tot[tot.liga == "acb"]["dunks"].notna().all()
    reg = df[(df.fase == "regular") & (df.liga == "gleague")]
    assert np.allclose(reg["src_ts_pct"], 55.0)                # 0.55 -> escala 0-100
    # LNB: jugadores bajo el umbral del ranking recuperados desde su ficha (sin pérdidas)
    hidden = tot[(tot.liga == "lnb") & tot.player_id.str.endswith(str(synth.LNB_HIDDEN_K))]
    assert len(hidden) == 4 and hidden["tov"].isna().all() and hidden["fg3a"].notna().all()
    assert tot[tot.liga == "lnb"]["altura_cm"].eq(200).all()


def test_basketnews_enrichment(first_run):
    _, out = first_run
    df = _read(out)
    el = df[(df.liga == "euroleague") & (df.fase == "regular")]
    team_a = el[el.nombre.str.startswith("Jugador A")]
    assert (team_a["bn_usg_pct"] == 22.5).all() and (team_a["bn_netrtg_onoff"] == 3.0).all()
    assert np.allclose(team_a["bn_min_on"], 10.0)
    assert el[~el.nombre.str.startswith("Jugador A")]["bn_usg_pct"].isna().all()
    assert df[df.liga == "acb"]["bn_usg_pct"].isna().all()   # liga sin enriquecimiento configurado


def test_reprocess_without_network(first_run, config):
    _, out = first_run
    before = _read(out)
    offline = FakeHttp(lambda *a: (_ for _ in ()).throw(AssertionError("no debe haber red")))
    rep = run(config=config, descargar=False, http_factory=lambda: offline, paralelo=False)
    assert all(l["estado"] == "ok" for l in rep["ligas"])
    pd.testing.assert_frame_equal(before, _read(out))


def test_failed_download_falls_back_and_reuses_games(first_run, config, router):
    router.state["down"].add("feeds.incrowdsports.com")
    try:
        rep = _run(config, router)
    finally:
        router.state["down"].clear()
    st = {l["liga"]: l for l in rep["ligas"]}
    assert st["euroleague"]["estado"] == "ok_bruto_anterior" and st["euroleague"]["jugadores"] == N_PLAYERS
    raw = Path(config["rutas"]["bruto"])
    for liga, key in (("acb", "reused_games"), ("lba", "reused_games"), ("bbl", "reused_games")):
        files = sorted((raw / liga / "2025-26").glob("*.json.gz"))
        assert len(files) == 2
        assert json.loads(gzip.decompress(files[-1].read_bytes()))["payload"][key] == 16, liga


def test_one_league_error_does_not_stop_others(config, router):
    config["ligas"]["roto"] = {"adaptador": "fiba_livestats", "activa": True, "minutos_partido": 40}
    rep = _run(config, router)
    st = {l["liga"]: l["estado"] for l in rep["ligas"]}
    assert st["roto"] == "error" and st["acb"] == "ok"
