"""Fase 4 (bbfit/reemplazo.py) con datos sintéticos."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bbfit import datos as D
from bbfit import reemplazo as RE
from bbfit.config import cargar
from bbfit.roles import ROLES


@pytest.fixture(scope="module")
def cfg():
    return cargar("reemplazo")


def _plantilla(n=12, semilla=0):
    rng = np.random.default_rng(semilla)
    pos = (["E"] * 5 + ["A"] * 3 + ["I"] * 4)[:n]
    return pd.DataFrame({"player_id": [f"p{i}" for i in range(n)], "nivel": np.sort(rng.normal(0, 1, n))[::-1],
                         "pos3": pos})


# --------------------------------------------------------------------------- asignar_minutos

def test_asignar_minutos_suma_tope_y_reproducible(cfg):
    p = _plantilla()
    out, M = RE.asignar_minutos(p, total_min=200, n_sim=300, semilla=1, cfg=cfg, devolver_simulaciones=True)
    assert np.allclose(M.sum(axis=1), 200)
    assert M.max() <= cfg["asignacion"]["max_min_partido"] + 1e-6
    out2 = RE.asignar_minutos(p, total_min=200, n_sim=300, semilla=1, cfg=cfg)
    pd.testing.assert_frame_equal(out, out2)


def test_asignar_minutos_mejor_nivel_mas_minutos(cfg):
    p = _plantilla()
    out = RE.asignar_minutos(p, n_sim=500, semilla=2, cfg=cfg)
    assert out["min_media"].iloc[0] > out["min_media"].iloc[-1]
    assert np.corrcoef(p["nivel"], out["min_media"])[0, 1] > 0.8


def test_asignar_minutos_probabilidades_de_rol(cfg):
    out = RE.asignar_minutos(_plantilla(), n_sim=400, semilla=3, cfg=cfg)
    P = out[[f"p_{k}" for k in ROLES[:-1]]].to_numpy()
    assert np.allclose(P.sum(axis=1), 1)
    assert out["p_GO_TO_GUY"].isna().all()


def test_asignar_minutos_restriccion_posicional(cfg):
    # los 6 mejores son exteriores; debe entrar al menos un interior en el quinteto inicial
    p = pd.DataFrame({"player_id": [f"p{i}" for i in range(9)], "nivel": [5, 4.9, 4.8, 4.7, 4.6, 4.5, 0, -1, -2],
                      "pos3": ["E"] * 6 + ["I", "I", "A"]})
    out = RE.asignar_minutos(p, n_sim=200, semilla=4, cfg=cfg)
    assert out.loc[out["player_id"].isin(["p6", "p7"]), "p_titular_quinteto"].sum() == pytest.approx(1.0)


def test_asignar_minutos_tendencia_de_rotacion(cfg):
    p = _plantilla()
    _, Mc = RE.asignar_minutos(p, rotacion_media=7, rotacion_sd=0.01, n_sim=200, semilla=5, cfg=cfg,
                               devolver_simulaciones=True)
    _, Ml = RE.asignar_minutos(p, rotacion_media=11, rotacion_sd=0.01, n_sim=200, semilla=5, cfg=cfg,
                               devolver_simulaciones=True)
    assert ((Mc > 0).sum(axis=1) == 7).all() and ((Ml > 0).sum(axis=1) == 11).all()
    assert Mc.max(axis=1).mean() > Ml.max(axis=1).mean()


def test_asignar_minutos_nba_240(cfg):
    out, M = RE.asignar_minutos(_plantilla(), total_min=240, minutos_partido=48, n_sim=100, semilla=6, cfg=cfg,
                                devolver_simulaciones=True)
    assert np.allclose(M.sum(axis=1), 240) and M.max() <= 36 * 48 / 40 + 1e-6


# --------------------------------------------------------------------------- uso-eficiencia

def test_agrupamiento_parcial_contrae_hacia_el_grupo():
    est = pd.DataFrame({"persona_id": list("abcdef"), "pos3": ["E"] * 6,
                        "beta_bruto": [-0.5, -0.4, -0.6, -0.5, 1.5, -0.45], "se": [0.1, 0.1, 0.1, 0.1, 2.0, 0.1],
                        "n": 30, "n_grupos": 1})
    out = RE.agrupamiento_parcial(est, "pos3", 1e-6, 0.9).set_index("persona_id")
    # el ruidoso (se = 2) queda casi en la media del grupo; los precisos apenas se mueven
    assert abs(out.loc["e", "beta_media"] - out.loc["e", "beta_grupo"]) < 0.2
    assert abs(out.loc["a", "beta_media"] - (-0.5)) < 0.1
    assert (out["beta_lo"] < out["beta_media"]).all() and (out["beta_hi"] > out["beta_media"]).all()


def test_pendiente_intra_recupera_beta():
    rng = np.random.default_rng(0)
    filas = []
    for j in range(40):
        nivel_u, nivel_ts = rng.normal(20, 5), rng.normal(55, 4)
        for g in range(30):
            u = nivel_u + rng.normal(0, 4)
            filas.append({"persona_id": f"j{j}", "grupo": f"j{j}", "usg": u, "ts": nivel_ts - 0.4 * (u - nivel_u)
                          + rng.normal(0, 3), "w": 1.0})
    est = RE._pendiente_intra(pd.DataFrame(filas), "ts", "usg", "w", "grupo")
    assert est["beta_bruto"].mean() == pytest.approx(-0.4, abs=0.05)
    assert est["se"].notna().all()


def test_proyectar_a_rol_rendimientos_decrecientes():
    tabla = pd.DataFrame({"rol": ["ROTACION", "GO_TO_GUY"], "usg_pct_mediana": [18.0, 28.0]})
    r = RE.proyectar_a_rol(18.0, 56.0, 20.0, "ROTACION", "GO_TO_GUY", tabla, beta_media=-0.3, beta_sd=0.05)
    assert r["d_usg"] == pytest.approx(10)
    assert r["ts"][0] == pytest.approx(53.0, abs=0.1)
    assert r["p100"][0] < r["p100_lineal"]          # escalar sin rol sobreestima
    assert r["p100"][1] <= r["p100"][0] <= r["p100"][2]


def test_redistribuir_suma_fija():
    p = pd.DataFrame({"player_id": list("abcdefgh"), "min": [34, 32, 30, 28, 26, 22, 18, 10],
                      "usg": [30, 25, 20, 18, 17, 15, 14, 12]})
    p["min"] = p["min"] * 200 / p["min"].sum()
    nueva, info = RE.redistribuir(p, ["a"], pd.DataFrame({"player_id": ["z"], "min": [20.0], "usg": [22.0]}))
    assert nueva["min"].sum() == pytest.approx(200)
    assert (nueva["min"] * nueva["usg"] / 100).sum() == pytest.approx(40)
    assert info["min_liberados"] == pytest.approx(p.loc[0, "min"]) and info["min_absorbidos"] == 20


# --------------------------------------------------------------------------- libro de roles

def _temp_rec():
    filas = []

    def fila(temp, pid, mins, s, gp=30):
        d = {"liga": "sint", "temporada": temp, "team_id": "T", "player_id": pid, "persona_id": "P" + pid,
             "min_total": mins, "gp": gp, "usg_pct": 20.0, "rol_mas_probable": ROLES[int(np.argmax(s))],
             "rol_probabilistico": False, "fuente": "pbp"}
        d.update({f"p_{k}": v for k, v in zip(ROLES, s)})
        return d
    filas += [fila("2024-25", "a", 900, [0, 0, 0, 0.2, 0.8]), fila("2024-25", "b", 600, [0, 0.1, 0.6, 0.3, 0]),
              fila("2024-25", "c", 300, [0.2, 0.8, 0, 0, 0])]
    filas += [fila("2025-26", "b", 900, [0, 0, 0.2, 0.5, 0.3]), fila("2025-26", "c", 450, [0, 0.5, 0.5, 0, 0]),
              fila("2025-26", "d", 450, [0, 0, 0.5, 0.5, 0])]
    return pd.DataFrame(filas)


def test_libro_identidad_exacta(monkeypatch, cfg):
    monkeypatch.setattr(D, "temporadas", lambda: ["2024-25", "2025-26"])
    monkeypatch.setattr(D, "ligas_temporada", lambda t: ["sint"])
    eq = {"2024-25": pd.DataFrame({"fase": ["regular"], "team_id": ["T"], "net_rtg_aj": [1.0], "net_rtg": [1.0]}),
          "2025-26": pd.DataFrame({"fase": ["regular"], "team_id": ["T"], "net_rtg_aj": [4.0], "net_rtg": [4.0]})}
    monkeypatch.setattr(D, "quintetos_fichero", lambda liga, temp, nombre: eq[temp].copy())
    pe = pd.DataFrame({"liga": "sint", "temporada": ["2024-25", "2025-26"], "team_id": "T", "g_equipo": 30})
    libro, trans, mov = RE.libro_roles(_temp_rec(), cfg, pe)
    assert libro["cierre_identidad"].abs().max() < 1e-9
    tot = libro[libro["rol"] == "TOTAL"].iloc[0]
    assert tot["n_retornos"] == 2 and tot["n_salidas"] == 1 and tot["n_llegadas"] == 1
    assert tot["salidas"] == pytest.approx(30.0)              # 900' / 30 partidos
    assert tot["delta_net"] == pytest.approx(3.0)
    # desplazamiento de minutos de b: (900-600)/30 · s_ant
    g = libro[libro["rol"] == "ROTACION"].iloc[0]
    assert g["desplaz_minutos"] == pytest.approx(10 * 0.6 + 5 * 0.0)
    assert g["desplaz_rol"] == pytest.approx(30 * (0.2 - 0.6) + 15 * (0.5 - 0.0))
    assert set(mov["persona_id"]) == {"Pb", "Pc"}
    t = trans[trans["liga"] == "todas"]
    assert t["n"].sum() == 2


def test_tendencias_entrenador_contraen():
    filas = []
    for g in range(4):
        for i in range(10):
            filas.append({"liga": "sint", "game_id": str(g), "team_id": "T", "entrenador_id": "c1", "jugo": True,
                          "sec": 2400 * (0.9 if i < 5 else 0.3), "min_pct": 0.9 if i < 5 else 0.3})
    pj = pd.DataFrame(filas)
    te = RE.tendencias_entrenador(pj, cargar("reemplazo")).set_index("entrenador_id")
    assert te.loc["c1", "rotacion"] == pytest.approx(10)
    assert te.loc["c1", "n_partidos"] == 4
    assert "__liga__:sint" in te.index
