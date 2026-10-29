"""Tests sintéticos del simulador de encaje v2 (bbfit/simulador.py, bbfit/validacion.py).

Una liga inventada con dos equipos, constantes de traducción sencillas y piezas de modelo fijas: comprueban la
reproducibilidad con semilla, las restricciones de suma (minutos y uso), que no hay minutos manuales, la coherencia
de las salidas (probabilidades, intervalos, Fit aditivo) y las piezas de la validación (verosimilitud
Plackett-Luce, log-loss, bootstrap).
"""
from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest

from bbfit import sim_insumos as SI
from bbfit import simulador as S
from bbfit import validacion as V
from bbfit.roles import ROLES

METS = ["pts_p100", "ts_pct", "usg_pct", "ast_pct", "oreb_p100", "dreb_p100", "stl_p100", "blk_p100", "tov_pct", "rapm"]
TRANSF = {"pts_p100": "raiz", "ts_pct": "id", "usg_pct": "id", "ast_pct": "id", "oreb_p100": "raiz", "dreb_p100": "raiz",
          "stl_p100": "raiz", "blk_p100": "raiz", "tov_pct": "id", "rapm": "id"}
MEDIA = {"pts_p100": 4.5, "ts_pct": 55, "usg_pct": 19, "ast_pct": 14, "oreb_p100": 1.6, "dreb_p100": 2.6, "stl_p100": 1.1,
         "blk_p100": 0.7, "tov_pct": 13, "rapm": 0.0}
TAU = {"pts_p100": 0.8, "ts_pct": 6, "usg_pct": 5, "ast_pct": 6, "oreb_p100": 0.5, "dreb_p100": 0.5, "stl_p100": 0.3,
       "blk_p100": 0.4, "tov_pct": 4, "rapm": 1.5}


def _constantes():
    c = {}
    for m in METS:
        c[m] = {"transf": TRANSF[m], "sentido": 1, "exposicion": "pos",
                "s": {"euroleague": 1.0, "lig1": 1.0, "lig2": 0.9}, "psi": {"euroleague": 0.05, "lig1": 0.05, "lig2": 0.08},
                "m": {"euroleague": 0.0, "lig1": -0.3, "lig2": -0.8},
                "deriva": {"≤23": 0.05, "24-26": 0.0, "27-29": 0.0, "30-32": -0.03, "33+": -0.08, "s/d": 0.0}, "eta2": 0.0,
                "mu": {f"{l}|2024-25|{p}": MEDIA[m] for l in ("euroleague", "lig1", "lig2") for p in "EAI"}
                | {f"euroleague|2025-26|{p}": MEDIA[m] for p in "EAI"},
                "tau2": {f"{l}|{p}": TAU[m] ** 2 for l in ("euroleague", "lig1", "lig2") for p in "EAI"},
                "sigma2": {"lig1": 30.0, "lig2": 30.0, "euroleague": 30.0}}
    nodos = {m: {"lig1:2024-25": (-0.3, 0.01), "lig2:2024-25": (-0.8, 0.04)} for m in METS}
    return {"constantes": c, "nodos": nodos, "fuente": "sintetica"}


def _corte(semilla=0) -> S.Corte:
    rng = np.random.default_rng(semilla)
    ids = SI.estilos_ids()
    filas = []
    k = 0
    for liga, n_eq in (("lig1", 2), ("lig2", 1)):
        for e in range(n_eq):
            team = f"{liga}_T{e}"
            for j in range(13):
                L = rng.normal(0.3 if liga == "lig1" else -0.5, 0.6)
                mp = float(np.clip(0.65 - 0.045 * j + rng.normal(0, 0.03), 0.03, 0.9))
                f = {"persona_id": f"P{k:03d}", "nombre": f"Jugador {k}", "liga": liga, "team_id": team, "club": f"{liga}|{team}",
                     "pos3": "EAI"[j % 3], "edad": float(rng.integers(20, 34)), "gp": 30, "g_equipo": 34, "presencia": 1.0,
                     "min_total": mp * 40 * 30, "min_pg": mp * 40, "min_pct": mp, "gs_pct": 1.0 if j < 5 else 0.0,
                     "rol_mas_probable": "TITULAR" if j < 5 else "ROTACION", "L": L, "L_sd": 0.3, "gti": rng.normal(0, 2),
                     "usg_pct_obs": float(np.clip(rng.normal(19, 4), 8, 35)), "ast_pct_obs": float(rng.uniform(5, 30)),
                     "sigma": 12.0, "H_rol": 1.0, "nacionalidad": None, "principal": True}
                for m in METS:
                    f[f"{m}_th"] = L + rng.normal(0, 0.3)
                    f[f"{m}_thsd"] = 0.3
                p = rng.dirichlet(np.ones(len(ids)))
                for i, s_ in zip(ids, p):
                    f[f"eu_{i}"] = float(s_)
                filas.append(f)
                k += 1
    reg = pd.DataFrame(filas)
    eq = reg.groupby(["liga", "team_id", "club"]).size().rename("jugadores").reset_index()
    eq["temporada"], eq["team_pace"], eq["lg_pace"], eq["eu"] = "2024-25", 72.0, 72.0, ids[0]
    for i in ids:
        eq[f"eu_{i}"] = 1 / len(ids)
    eq["entrenador"] = None
    curva = [0.16, 0.15, 0.14, 0.13, 0.12, 0.1, 0.08, 0.06, 0.04, 0.02, 0.0, 0.0]
    tend = pd.DataFrame([{"entrenador_id": f"__liga__:{l}", "liga_principal": l, "rotacion": 9.0, "rotacion_contraido": 9.0,
                          "rotacion_sd": 1.0, **{f"cuota_r{r + 1}_contraido": v for r, v in enumerate(curva)}}
                         for l in ("lig1", "lig2")])
    mod = {"tendencias": tend, "beta_uso": {"E": (-0.1, 0.05), "A": (-0.1, 0.05), "I": (-0.1, 0.05), "todos": (-0.1, 0.05)},
           "companeros": {"ts_pct": (2.0, 0.5)}, "min_rol": {("lig1", "RESIDUAL"): 0.08}, "min_rol_global": {"RESIDUAL": 0.08}}
    cfg = SI.cfg_sim()
    ref = S.referencias(reg, eq, "2024-25")
    c = S.Corte("2024-25", "sintetica", reg, eq, _constantes(), mod, ref, cfg)
    c.w_util = {"L": 1.0, "lmin_club": 1.0, "lmin_fuera": 0.5, "nuevo": -0.3, "sin_dato": -0.5, "encaje_pos": 0.5,
                "encaje_estilo": 0.0, "edad_c": 0.0, "edad_c2": 0.0}
    c.calib = {"rotacion_extra": 2.0, "escala_utilidad": 1.0, "rotacion_sd_factor": 0.3, "disponibilidad": 0.85}
    return c


@pytest.fixture(scope="module")
def corte():
    return _corte()


def _simular(c, persona="P030", semilla=7, n=300, **kw):
    miembros = S.miembros_actuales(c, "lig1|lig1_T0")
    return S.simular(c, persona, "lig1", "lig1_T0", miembros, n_sim=n, semilla=semilla, sin_adaptacion=True, **kw)


# --------------------------------------------------------------------------------------------- reproducibilidad
def test_semilla_reproducible(corte):
    a, b = _simular(corte), _simular(corte)
    assert a["minutos"] == b["minutos"]
    assert a["roles"] == b["roles"]
    assert a["produccion_p100"]["pts_p100"] == b["produccion_p100"]["pts_p100"]
    c_ = _simular(corte, semilla=8)
    assert c_["minutos"]["media"] != a["minutos"]["media"]


def test_sin_minutos_manuales():
    """La interfaz del simulador no acepta minutos: sólo jugador, club, plantilla (escenario) y opciones de cálculo."""
    params = set(inspect.signature(S.simular).parameters)
    assert not any("min" in p and p != "miembros" for p in params)
    assert not any("min" in p for p in inspect.signature(S.simular_cli).parameters)


# --------------------------------------------------------------------------------------------- restricciones
def test_suma_de_minutos_de_la_plantilla(corte):
    r = _simular(corte, n=400)
    tot = sum(p["minutos"] for p in r["plantilla"])
    assert tot == pytest.approx(200.0, abs=1e-6)
    assert all(p["minutos"] <= 36 + 1e-9 for p in r["plantilla"])


def test_redistribucion_de_uso_suma_fija():
    rng = np.random.default_rng(1)
    M = rng.uniform(0, 30, (50, 12))
    M = M / M.sum(1, keepdims=True) * 200
    U = rng.uniform(10, 30, (50, 12))
    U2, f = S.redistribuir_uso(M, U, 20.0, 1.0)
    assert np.allclose((M * U2).sum(1), 20.0 * M.sum(1))
    U3, _ = S.redistribuir_uso(M, U, 20.0, 0.0)
    assert np.allclose(U3, U)


def test_probabilidades_e_intervalos(corte):
    r = _simular(corte)
    assert sum(r["roles"].values()) == pytest.approx(1.0)
    assert set(r["roles"]) == set(ROLES)
    for d in [r["minutos"]] + list(r["produccion_p100"].values()):
        if d["media"] is None:
            continue
        assert d["lo90"] <= d["lo50"] <= d["mediana"] <= d["hi50"] <= d["hi90"]
    assert 0 <= r["p_titular"] <= 1


def test_mejor_nivel_mas_minutos(corte):
    c = corte
    fila = dict(S.jugador_insumos(c, "P030"))
    alto = {**fila, "L": 2.5, **{f"{m}_th": 2.5 for m in METS}}
    bajo = {**fila, "L": -2.0, **{f"{m}_th": -2.0 for m in METS}}
    ra = _simular(c, registro=alto)
    rb = _simular(c, registro=bajo)
    assert ra["minutos"]["media"] > rb["minutos"]["media"]
    assert ra["indice_rol"] > rb["indice_rol"]


def test_traduccion_monotona_y_liga_mas_dificil(corte):
    c = corte
    f = dict(S.jugador_insumos(c, "P030"))
    v1 = S.traducir(c, f, "lig1", ["pts_p100"])["pts_p100"]
    v2 = S.traducir(c, f, "lig2", ["pts_p100"])["pts_p100"]
    f2 = {**f, "pts_p100_th": f["pts_p100_th"] + 1}
    assert S.traducir(c, f2, "lig1", ["pts_p100"])["pts_p100"] > v1
    assert v2 > v1                              # misma capacidad rinde más en la liga más floja


def test_fit_aditivo(corte):
    c = corte
    x = {k: 0.1 * i for i, k in enumerate(V.RASGOS_FIT)}
    F = {"b0": 0.2, "w": {k: 0.1 for k in V.RASGOS_FIT}, "media": {k: 0.0 for k in V.RASGOS_FIT},
         "sd": {k: 1.0 for k in V.RASGOS_FIT}}
    c.fit = F
    r = S.indice_fit(c, x)
    assert r["total"] == pytest.approx(r["base"] + sum(r["componentes"].values()))
    assert sum(r["componentes"].values()) == pytest.approx(sum(r["rasgos"].values()))
    c.fit = None


def test_adaptacion_curva_en_salida(corte):
    r = _simular(corte)
    ad = r["adaptacion"]
    assert ad["adapt_pct_temporada"]["media"] == pytest.approx(100.0)       # sin adaptación: Δ = 0
    assert len(ad["curva"]) > 5


# --------------------------------------------------------------------------------------------- validación
def test_verosimilitud_pl_recupera_pesos():
    rng = np.random.default_rng(3)
    w_true = np.array([1.5, -0.7])
    bloques = []
    for _ in range(300):
        X = rng.normal(size=(10, 2))
        u = X @ w_true + rng.gumbel(size=10)
        o = np.argsort(-u)
        bloques.append({"X": np.c_[X[o], np.zeros((10, len(S.RASGOS_UTIL) - 2))], "y": None, "n": 10})
    cfg = SI.cfg_sim()
    cfg = {**cfg, "utilidad": {**cfg["utilidad"], "regularizacion": 0.0, "inicial": {k: 0.0 for k in S.RASGOS_UTIL}}}
    w = V.ajustar_utilidad(bloques, cfg)
    assert w[S.RASGOS_UTIL[0]] == pytest.approx(1.5, abs=0.2)
    assert w[S.RASGOS_UTIL[1]] == pytest.approx(-0.7, abs=0.2)


def test_logloss_y_bootstrap():
    P = np.array([[0.9, 0.1], [0.2, 0.8]])
    assert V._logloss(P, np.array([0, 1])) == pytest.approx(-np.log([0.9, 0.8]))
    rng = np.random.default_rng(0)
    n = 300
    e = pd.DataFrame({"liga_d": "x", "team_d": [str(i % 40) for i in range(n)], "corte": "2024-25", "eval_min": True,
                      "v_err_min": rng.uniform(0, 4, n), "a_err_min": rng.uniform(1, 6, n), "b_err_min": rng.uniform(1, 6, n),
                      "v_logloss": 1.0, "a_logloss": 1.0, "b_logloss": 1.0, "v_acierto": 1.0, "a_acierto": 0.0, "b_acierto": 0.0})
    cfg = SI.cfg_sim()
    bt = V.bootstrap_diferencias(e, cfg, B=200)
    r = bt[(bt["metrica"] == "mae_min") & (bt["baseline"] == "a")].iloc[0]
    assert r["veredicto"] == "v2 mejor" and r["ic90_hi"] < 0
    r = bt[(bt["metrica"] == "acierto_rol") & (bt["baseline"] == "b")].iloc[0]
    assert r["veredicto"] == "v2 mejor"


def test_mapa_clubes_por_continuidad():
    roles = pd.DataFrame({"temporada": ["t"] * 6 + ["u"] * 6, "liga": ["a"] * 6 + ["b"] * 6,
                          "team_id": ["X"] * 6 + ["Y"] * 6, "persona_id": list("pqrstu") + list("pqrsvw"), "presencia": 1.0})
    m = V.mapa_clubes(roles, "t", "u")
    assert m[("b", "Y")] == ("a", "X")


def test_calibracion_de_salida():
    C = {"min": {"c": [2.0, 0.8, 0.1, 0.1], "s50": 0.9, "s90": 1.2},
         "roles": {"theta": [0, 0.5, 0.5, 0.5, 0.5], "alfa": 0.5, "beta": 0.5}}
    P = np.array([[0.1, 0.2, 0.3, 0.3, 0.1], [0.0, 0.0, 0.0, 1.0, 0.0]])
    m, iv, Pc = S.calibrar_salida(C, np.array([20.0, 30.0]), {"50": (np.array([15.0, 25.0]), np.array([25.0, 33.0]))},
                                  P, np.array([18.0, 28.0]), np.array([19.0, 27.0]), P)
    assert np.allclose(Pc.sum(1), 1) and (Pc > 0).all()
    assert m[0] == pytest.approx(2 + 16 + 1.8 + 1.9)
    assert (iv["50"][0] <= m).all() and (iv["50"][1] >= m).all()
