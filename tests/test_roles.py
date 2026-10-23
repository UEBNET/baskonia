"""Fase 3 (bbfit/roles.py, bbfit/cambios.py) con datos sintéticos."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bbfit import cambios as C
from bbfit import datos as D
from bbfit import roles as R
from bbfit.config import cargar


@pytest.fixture(scope="module")
def cfg():
    return cargar("roles")


# --------------------------------------------------------------------------- changepoints

def test_bocpd_filas_suman_uno():
    x = np.r_[np.full(10, 0.3), np.full(10, 0.7)]
    P = C.bocpd(x[:, None], [0.5], [0.04], [0.01], 1 / 20)
    assert np.allclose(P.sum(axis=1), 1)
    assert np.allclose(np.triu(P, 1)[:, :].sum(), np.triu(P, 1).sum())  # sin masa fuera de ℓ <= t
    assert (P[np.triu_indices(20, 1)] == 0).all()


def test_segmentar_detecta_salto_de_minutos(cfg):
    rng = np.random.default_rng(0)
    x = np.r_[0.25 + 0.05 * rng.standard_normal(20), 0.70 + 0.05 * rng.standard_normal(20)]
    segs, pi = C.segmentar(x, [0.45], [0.0625], [0.0036], cfg["cambios"])
    assert len(segs) == 2
    assert abs(segs[1][0] - 20) <= 1
    assert pi[segs[1][0]] >= cfg["cambios"]["umbral_prob"]


def test_segmentar_serie_estable_un_tramo(cfg):
    rng = np.random.default_rng(1)
    x = 0.5 + 0.06 * rng.standard_normal(40)
    segs, _ = C.segmentar(x, [0.45], [0.0625], [0.0036], cfg["cambios"])
    assert segs == [(0, 39)]


def test_segmentar_dos_dimensiones_con_huecos(cfg):
    rng = np.random.default_rng(2)
    m = 0.5 + 0.03 * rng.standard_normal(40)
    u = np.r_[0.15 + 0.02 * rng.standard_normal(20), 0.32 + 0.02 * rng.standard_normal(20)]
    u[[3, 17, 25]] = np.nan                       # USG% ausente (pocos minutos)
    segs, _ = C.segmentar(np.column_stack([m, u]), [0.45, 0.2], [0.0625, 0.01], [0.0036, 0.0025], cfg["cambios"])
    assert len(segs) == 2 and abs(segs[1][0] - 20) <= 1


def test_bloques_entrenador_absorbe_interinos():
    b = R._bloques_entrenador(np.array(list("aaaaabbaaaccccc")), 3)
    assert b.tolist() == [0] * 10 + [1] * 5


# --------------------------------------------------------------------------- reglas

def test_reglas_fiba(cfg):
    m = np.array([3, 10, 18, 23, 23, 23, 30, 30]) / 40
    gs = np.array([0, 0, 0, 0.6, 0.1, 0.1, 0, 1])
    cl = np.array([0, 0, 0, 0.0, 0.7, 0.1, 0, 1])
    gtg = np.array([0, 0, 0, 0, 0, 0, 0, 1], bool)
    out = R.clasificar(m, gs, cl, gtg, cfg).tolist()
    assert out == ["RESIDUAL", "PROFUNDIDAD", "ROTACION", "TITULAR", "TITULAR", "ROTACION", "TITULAR", "GO_TO_GUY"]


def test_reglas_nba_escalan_a_48(cfg):
    # 26,5' de 48 = MIN% 55,2 % ≈ 22,1' de 40: solape
    assert D.minutos_partido("nba", cfg) == 48 and D.minutos_partido("acb", cfg) == 40
    out = R.clasificar(np.array([26.5 / 48, 26.5 / 48]), np.array([1.0, 0.0]), np.array([0.0, 0.0]),
                       np.zeros(2, bool), cfg)
    assert out.tolist() == ["TITULAR", "ROTACION"]


def test_go_to_guy_exige_minutos(cfg):
    out = R.clasificar(np.array([18 / 40]), np.array([1.0]), np.array([1.0]), np.array([True]), cfg)
    assert out.tolist() == ["ROTACION"]


# --------------------------------------------------------------------------- tabla por partido sintética

def _partido(gid, quintetos_a, quintetos_b, cortes, margenes):
    """Un partido FIBA de 4 cuartos con cambios en `cortes` (s) y el margen al empezar cada tramo."""
    filas = []
    t_prev = 0.0
    for i, t in enumerate(cortes):
        per = int(t_prev // 600) + 1
        filas.append({"game_id": gid, "fase": "regular", "periodo": per, "t0": t_prev, "t1": t, "sec": t - t_prev,
                      "team_a": "A", "team_b": "B", "quinteto_a": "|".join(quintetos_a[i]),
                      "quinteto_b": "|".join(quintetos_b[i]), "n_a": 5, "n_b": 5, "margen_inicio": margenes[i],
                      "clutch": False, "basura": False,
                      **{f"{s}_{k}": 0 for s in "ab" for k in ("pts", "fga", "fgm", "fg2a", "fg2m", "fg3a", "fg3m",
                                                                "fta", "ftm", "oreb", "dreb", "tov", "stl", "blk",
                                                                "ast", "pf")}})
        t_prev = t
    return filas


@pytest.fixture()
def sintetico(monkeypatch):
    A1 = ["a1", "a2", "a3", "a4", "a5"]
    A2 = ["a1", "a2", "a3", "a4", "a6"]
    B1 = ["b1", "b2", "b3", "b4", "b5"]
    # partido 1: a5 juega 0-1800 y a6 1800-2400 (con margen ±3 en el cierre)
    g1 = _partido("1", [A1, A1, A2], [B1, B1, B1], [1200, 1800, 2400], [0, 4, 3])
    # partido 2: a5 no juega; a6 todo el partido
    g2 = _partido("2", [A2, A2], [B1, B1], [1200, 2400], [0, 10])
    # partido 3: a5 vuelve
    g3 = _partido("3", [A1], [B1], [2400], [0])
    tr = pd.DataFrame(g1 + g2 + g3)
    for c in ("a_pts", "b_pts"):
        tr[c] = 2
    tr["a_fga"] = 4
    ti = pd.DataFrame([
        {"fase": "regular", "game_id": "1", "periodo": 4, "t": 2350.0, "team_id": "A", "player_id": "a6", "tipo": "T2",
         "anotado": True, "puntos": 2, "asistente_id": np.nan, "x": np.nan, "y": np.nan,
         "quinteto": "|".join(A2), "quinteto_rival": "|".join(B1), "margen_previo": 3},
        {"fase": "regular", "game_id": "1", "periodo": 1, "t": 100.0, "team_id": "A", "player_id": "a1", "tipo": "T3",
         "anotado": True, "puntos": 3, "asistente_id": "a5", "x": np.nan, "y": np.nan,
         "quinteto": "|".join(A1), "quinteto_rival": "|".join(B1), "margen_previo": 0},
        {"fase": "regular", "game_id": "1", "periodo": 1, "t": 200.0, "team_id": "A", "player_id": "a1", "tipo": "TL",
         "anotado": False, "puntos": 0, "asistente_id": np.nan, "x": np.nan, "y": np.nan,
         "quinteto": "|".join(A1), "quinteto_rival": "|".join(B1), "margen_previo": 3},
    ])
    ep = pd.DataFrame([{"game_id": g, "equipo_id": t, "fecha": f"2025-10-0{g}", "entrenador_id": "coach_" + t}
                       for g in ("1", "2", "3") for t in ("A", "B")])
    monkeypatch.setattr(D, "tramos", lambda liga, temp: tr.copy())
    monkeypatch.setattr(D, "tiros", lambda liga, temp: ti.copy())
    monkeypatch.setattr(D, "entrenadores_partidos", lambda liga, temp: ep.copy())
    monkeypatch.setattr(D, "persona", lambda liga, s: liga + ":" + s.astype(str))
    return tr


def test_partidos_jugador_minutos_titular_cierre_y_ausencias(sintetico, cfg):
    pj = R.partidos_jugador("sint", "2025-26", cfg)
    g1 = pj[(pj["game_id"] == "1")].set_index("player_id")
    assert g1.loc["a1", "min"] == pytest.approx(40)
    assert g1.loc["a5", "min"] == pytest.approx(30) and g1.loc["a6", "min"] == pytest.approx(10)
    assert g1.loc["a5", "titular"] == 1 and g1.loc["a6", "titular"] == 0
    # cierre: últimos 300 s del 4.º cuarto con |margen| <= 5 → a6 (en pista 1800-2400 con margen 3)
    assert g1.loc["a6", "sec_close"] == pytest.approx(300) and g1.loc["a5", "sec_close"] == 0
    assert g1.loc["a6", "close_share"] == pytest.approx(1.0)
    assert g1.loc["a6", "min_pct"] == pytest.approx(0.25)
    # a5 no juega el partido 2 pero sí el 1 y el 3 → fila de ausencia
    a5 = pj[pj["player_id"] == "a5"].set_index("game_id")
    assert not a5.loc["2", "jugo"] and a5.loc["2", "min"] == 0
    # uso: a1 tiene 1 FGA + 1 FTA de 2 FGA + 1 FTA del equipo con él en pista
    assert g1.loc["a1", "usg_tiro"] == pytest.approx(100 * 1.44 / 2.44)
    assert g1.loc["a5", "ast"] == 1 and g1.loc["a1", "fgm_asist"] == 1
    assert (pj["entrenador_id"].dropna().str.startswith("coach_")).all()


def test_agregar_y_probabilidades(sintetico, cfg):
    pj = R.partidos_jugador("sint", "2025-26", cfg)
    pj["estado"] = R.estado_partido(pj["min_pct"], pj["titular"], pj["close_share"], cfg)
    pj.loc[~pj["jugo"], "estado"] = None
    rec = R.agregar(pj, ["team_id", "player_id"], cfg)
    rec["rol_regla"] = R.clasificar(rec["min_pct"], rec["gs_pct"], rec["close_pct"], np.zeros(len(rec), bool), cfg)
    pi = pj.loc[pj["jugo"], "estado"].value_counts(normalize=True)
    out = R._probabilidades(pj, rec, ["team_id", "player_id"], cfg, pi).set_index("player_id")
    assert out.loc["a5", "gp"] == 2 and out.loc["a5", "ausencias"] == 1
    p = out[[f"p_{k}" for k in R.ROLES]].to_numpy()
    assert np.allclose(p.sum(axis=1), 1)
    # muestra < N partidos → sin etiqueta dura, con vector
    assert out["rol_probabilistico"].all() and out["rol"].isna().all()
    assert out.loc["a1", "H_rol"] == pytest.approx(0.0)


def test_covariables_vacio_de_rol(cfg):
    filas = []
    for o in range(1, 11):
        filas.append({"orden_equipo": o, "player_id": "titular", "pos3": "I", "min_pct": 0.8 if o <= 5 else 0.0,
                      "jugo": o <= 5, "entrenador_id": "c", "fga": 5, "fta": 0, "pts": 6, "pm": 2, "sec": 1500,
                      "coef_tl": 0.44})
        filas.append({"orden_equipo": o, "player_id": "suplente", "pos3": "I", "min_pct": 0.2 if o <= 5 else 0.7,
                      "jugo": True, "entrenador_id": "c", "fga": 2, "fta": 0, "pts": 2, "pm": 0, "sec": 500,
                      "coef_tl": 0.44})
    cv = C.covariables_cambio(pd.DataFrame(filas), "suplente", 6, "I", cfg["cambios"])
    assert cv["cov_vacio_rol"] and cv["cov_vacio_rol_ids"] == "titular"
    assert not cv["cov_cambio_entrenador"] and not cv["cov_fichaje_posicion"]
