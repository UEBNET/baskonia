"""Taxonomía unificada de estilos (bbfit/estilos_unificados.py) con datos sintéticos."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from bbfit import estilos_unificados as EU

R = ["ritmo", "triple", "esquina", "aro", "tiros_libres", "autocreacion", "asistencia", "reb_ofensivo",
     "perdidas", "robos", "tapones", "faltas"]


def _cfg(**extra):
    c = {"semilla": 7, "rasgos": [{"id": r, "corto": r} for r in R], "normalizacion": {"percentil_min": 0.01},
         "datos": {"contraccion_minutos_jugador": 100, "min_minutos_referencia": 100},
         "mezcla": {"k_min": 2, "k_max": 5, "covarianzas": ["full"], "n_init": 2, "max_iter": 300, "reg_covar": 1e-4,
                    "bootstrap": 5, "estabilidad_min": 0.6, "cuota_min": 0.04},
         "asignacion": {"umbral_puro": 0.8, "umbral_mezcla": 0.25}}
    c.update(extra)
    return c


def test_ecdf_z_monotona_y_centrada():
    ref = np.arange(1, 101, dtype=float)
    z = EU._ecdf_z(ref, np.ones(100), np.array([1.0, 50.5, 100.0, np.nan]), 0.01)
    assert z[0] < z[1] < z[2]
    assert abs(z[1]) < 1e-9          # mediana → 0
    assert np.isnan(z[3])
    assert z[2] == pytest.approx(-z[0])


def test_ecdf_z_ponderada():
    ref = np.array([0.0, 0.5, 1.0])
    # casi todo el peso en 0: el valor 1 queda en un percentil alto
    z = EU._ecdf_z(ref, np.array([98.0, 1.0, 1.0]), np.array([1.0]), 0.001)
    assert z[0] > 2


def test_contraer():
    assert EU.contraer(np.array([10.0]), np.array([100.0]), 0.0, 100.0)[0] == pytest.approx(5.0)
    assert EU.contraer(np.array([10.0]), np.array([0.0]), 3.0, 100.0)[0] == pytest.approx(3.0)


def _blobs(n=150, d=4, sep=6.0, k=3, semilla=0):
    rng = np.random.default_rng(semilla)
    centros = rng.normal(0, sep, (k, d))
    X = np.vstack([c + rng.normal(0, 1, (n, d)) for c in centros])
    return X, np.repeat(np.arange(k), n)


def test_posterior_completa_igual_que_sklearn():
    from sklearn.mixture import GaussianMixture
    X, _ = _blobs()
    g = GaussianMixture(3, covariance_type="full", random_state=0).fit(X)
    P = EU.posterior(g.means_, EU.covarianzas_completas(g), g.weights_, X)
    assert np.allclose(P, g.predict_proba(X), atol=1e-6)


def test_posterior_con_huecos_es_la_marginal():
    from sklearn.mixture import GaussianMixture
    X, _ = _blobs()
    g = GaussianMixture(3, covariance_type="diag", random_state=0).fit(X)
    covs = EU.covarianzas_completas(g)
    Xn = X.copy()
    Xn[:10, 2] = np.nan
    P = EU.posterior(g.means_, covs, g.weights_, Xn)
    # marginal: mezcla con las dimensiones observadas
    g2 = GaussianMixture(3, covariance_type="diag")
    g2.weights_, g2.means_ = g.weights_, g.means_[:, [0, 1, 3]]
    g2.covariances_ = g.covariances_[:, [0, 1, 3]]
    g2.precisions_cholesky_ = 1 / np.sqrt(g2.covariances_)
    assert np.allclose(P[:10], g2.predict_proba(X[:10][:, [0, 1, 3]]), atol=1e-6)
    assert np.allclose(P.sum(1), 1)
    todo_nan = EU.posterior(g.means_, covs, g.weights_, np.full((1, 4), np.nan))
    assert np.isnan(todo_nan).all()


def test_seleccion_k_encuentra_tres_grupos():
    X, y = _blobs(n=120, d=4, sep=8.0, k=3)
    tabla, el = EU.seleccionar_k(X, _cfg(), log=lambda *_: None)
    assert el["k"] == 3
    assert len(tabla) == 4
    assert all(0 <= f["cuota_min"] <= 1 for f in tabla)


def test_regla_de_eleccion():
    c = _cfg()
    f = lambda cov, k, bic, ari, cuota=0.1: {"covarianza": cov, "k": k, "bic": bic, "estabilidad_ari": ari,
                                             "cuota_min": cuota}
    # caso 1: mínimo interior del BIC y estable → ese K
    t1 = [f("full", 2, 100, 0.9), f("full", 3, 90, 0.8), f("full", 4, 95, 0.7), f("diag", 3, 120, 0.9)]
    assert EU.elegir(t1, c)["k"] == 3 and EU.elegir(t1, c)["caso"] == "bic"
    # caso 2: el BIC crece con K (continuo) → mayor K estable y sin grupos diminutos
    t2 = [f("full", 2, 90, 0.9), f("full", 3, 95, 0.7), f("full", 4, 99, 0.65), f("full", 5, 101, 0.4),
          f("full", 6, 103, 0.8, cuota=0.01), f("diag", 6, 110, 0.9)]
    el = EU.elegir(t2, c)
    assert (el["covarianza"], el["k"], el["caso"]) == ("full", 4, "continuo")
    # caso 3: nada cumple → la más estable con K > 1
    t3 = [{**x, "estabilidad_ari": a} for x, a in zip(t2, [0.3, 0.5, 0.2, 0.1, 0.1, 0.1])]
    assert EU.elegir(t3, c)["k"] == 3
    # k_taxonomia: el mínimo global del BIC (K=2) queda como diagnóstico; se decide en K ≥ 3
    t4 = [f("full", 1, 100, 1.0, 1.0), f("full", 2, 80, 0.9), f("full", 3, 85, 0.8), f("full", 4, 90, 0.7),
          f("full", 5, 95, 0.3)]
    c4 = _cfg()
    c4["mezcla"]["k_taxonomia"] = 3
    el = EU.elegir(t4, c4)
    assert (el["k"], el["k_bic_global"], el["caso"]) == (4, 2, "continuo")


def test_nombrar_por_firma():
    estilos = {"spacing": {"firma": {"triple": 1, "esquina": 1, "aro": -1}},
               "pintura": {"firma": {"aro": 1, "tiros_libres": 1, "triple": -1}},
               "vertigo": {"firma": {"ritmo": 1, "robos": 1}}}
    medias = np.zeros((3, len(R)))
    medias[0, R.index("aro")], medias[0, R.index("triple")] = 1.2, -1.0
    medias[1, R.index("ritmo")], medias[1, R.index("robos")] = 1.0, 0.8
    medias[2, R.index("triple")], medias[2, R.index("esquina")] = 1.1, 0.9
    assert EU.nombrar(medias, R, estilos, 0.3) == ["pintura", "vertigo", "spacing"]
    # sin firma que case: nombre genérico
    medias[1] = 0
    medias[1, R.index("perdidas")] = 1
    assert EU.nombrar(medias, R, estilos, 0.3)[1] == "estilo_2"


def test_etiqueta():
    c = _cfg()
    assert EU.etiqueta("Spacing", 0.9, "Pintura", 0.05, c) == "Spacing puro"
    assert EU.etiqueta("Spacing", 0.6, "Pintura", 0.3, c) == "Spacing · Pintura"
    assert EU.etiqueta("Spacing", 0.6, "Pintura", 0.2, c) == "Spacing"


def test_asignar_principal_y_secundario():
    df = pd.DataFrame({"a": [1, 2, 3]})
    P = np.array([[0.7, 0.2, 0.1], [0.1, 0.05, 0.85], [np.nan, np.nan, np.nan]])
    out = EU.asignar(df, P, ["x", "y", "z"], {"x": "X", "y": "Y", "z": "Z"}, _cfg())
    assert list(out["estilo"][:2]) == ["x", "z"]
    assert list(out["estilo2"][:2]) == ["y", "x"]
    assert out["etiqueta"].tolist() == ["X", "Z puro", ""]
    assert out["p_y"].iloc[0] == pytest.approx(0.2)


def _filas():
    """Liga sintética: 3 equipos × 4 jugadores, totales de equipo coherentes con los jugadores."""
    rng = np.random.default_rng(1)
    filas = []
    for t in range(3):
        for j in range(4):
            fga = 100 + 20 * j
            filas.append({"liga": "x", "temporada": "2025-26", "fase": "regular", "player_id": f"p{t}{j}",
                          "nombre": f"J{t}{j}", "posicion": "Base", "team_id": f"t{t}", "equipo": f"E{t}", "gp": 20,
                          "min": 300.0 + 50 * j, "fga": fga, "fgm": fga // 2, "fg3a": 30 + 10 * t + j, "fta": 20 + j,
                          "ast": 10 + t, "tov": 10, "oreb": 5 + j, "stl": 4, "blk": 1, "pf": 8,
                          "ast_pct": 10.0 + j, "oreb_p100": 2.0 + j, "stl_p100": 1.0 + t, "blk_p100": 0.5,
                          "pf_p100": 4.0 + rng.random(), "poss_on_court": 600.0, "team_gp": 20,
                          "team_pace": 70.0 + t, "team_poss": 1400.0, "opp_poss": 1400.0})
    f = pd.DataFrame(filas)
    for c in ["fga", "fgm", "fg3a", "fta", "ast", "tov", "oreb", "stl", "blk", "pf"]:
        f[f"team_{c}"] = f.groupby("team_id")[c].transform("sum")
    pi = pd.DataFrame({"liga": "x", "temporada": "2025-26", "team_id": f["team_id"], "player_id": f["player_id"],
                       "fga_pbp": f["fga"], "fgm_pbp": f["fgm"], "fgm_asist": f["fgm"] // 3,
                       "fga_aro": f["fga"] // 4, "fga_t3_esquina": 5, "poss_on": 600.0, "min_on": f["min"]})
    for c in ["fgm_aro", "fga_corta", "fgm_corta", "fga_media", "fgm_media", "fgm_t3_esquina", "fga_t3_frontal",
              "fgm_t3_frontal", "rapm", "orapm", "drapm"]:
        pi[c] = 0.0
    return f, pi


def test_rasgos_equipo_y_jugador_misma_definicion():
    f, pi = _filas()
    e = EU.rasgos_equipo(f, pi).set_index("team_id")
    j = EU.rasgos_jugador(f, pi)
    g = f[f["team_id"] == "t1"]
    assert e.loc["t1", "triple"] == pytest.approx(g["fg3a"].sum() / g["fga"].sum())
    assert e.loc["t1", "aro"] == pytest.approx((g["fga"] // 4).sum() / g["fga"].sum())
    assert e.loc["t1", "ritmo"] == pytest.approx(71.0)
    fila = j[j["player_id"] == "p12"].iloc[0]
    assert fila["triple"] == pytest.approx(g.iloc[2]["fg3a"] / g.iloc[2]["fga"])
    assert fila["autocreacion"] == pytest.approx(1 - (g.iloc[2]["fgm"] // 3) / g.iloc[2]["fgm"])
    # el ritmo del jugador es el del equipo corregido por su ritmo en pista (aquí distinto por minutos)
    assert np.isfinite(j["ritmo"]).all()


def test_puntuar_liga_z_dentro_de_la_liga():
    f, pi = _filas()
    c = _cfg()
    e, j, ref = EU.puntuar_liga(EU.rasgos_equipo(f, pi), EU.rasgos_jugador(f, pi), c)
    # 3 equipos: la puntuación del rasgo «ritmo» (70, 71, 72) es simétrica
    z = e.set_index("team_id")["z_ritmo"]
    assert z["t1"] == pytest.approx(0, abs=1e-9) and z["t0"] == pytest.approx(-z["t2"])
    assert set(ref) == {"equipo", "jugador", "media_jugador"}
    assert j[[f"z_{r}" for r in ["triple", "aro", "asistencia"]]].notna().all().all()


def test_campos_atlas(tmp_path, monkeypatch):
    monkeypatch.setattr(EU, "DIR_SAL", tmp_path)
    ids = ["a", "b"]
    eq = pd.DataFrame({"liga": ["x", "x"], "temporada": ["2025-26"] * 2, "team_id": ["1", "1"],
                       "nivel": ["temporada", "entrenador"], "entrenador_id": [None, "c2"],
                       "estilo": ["a", "b"], "estilo2": ["b", "a"], "p_estilo": [0.9, 0.6], "etiqueta": ["A puro", "B · A"],
                       "p_a": [0.9, 0.4], "p_b": [0.1, 0.6]})
    jg = pd.DataFrame({"liga": ["x"], "temporada": ["2025-26"], "team_id": ["1"], "player_id": ["7"],
                       "pid_estilos": ["7"], "nivel": ["temporada"], "entrenador_id": [None], "estilo": ["b"],
                       "estilo2": ["a"], "p_estilo": [0.7], "etiqueta": ["B"], "p_a": [0.3], "p_b": [0.7]})
    eq.to_csv(tmp_path / "equipos.csv", index=False)
    jg.to_csv(tmp_path / "jugadores.csv.gz", index=False)
    doc = {"rasgos": [], "asignacion": {}, "resumen": {},
           "estilos": [{"id": i, "nombre": i.upper(), "color": "#000", "definicion": "", "equipo": "", "jugador": "",
                        "rol_jugador": "", "metricas_caracterizan": [], "ejemplos_equipos": [], "ejemplos_jugadores": []}
                       for i in ids]}
    (tmp_path / "estilos.json").write_text(json.dumps(doc), encoding="utf-8")
    clubes = pd.DataFrame({"liga": ["x", "x"], "temporada": ["2025-26", "2025-26"], "team_id": ["1", "9"],
                           "entrenadores": [[{"entrenador_id": "c1"}, {"entrenador_id": "c2"}], None]})
    jug = pd.DataFrame({"liga": ["x"], "temporada": ["2025-26"], "team_id": ["1"], "player_id": ["7"]})
    c2, j2, meta = EU.campos_atlas(clubes, jug)
    assert c2.loc[0, "eu"] == 0 and c2.loc[0, "eu2"] == 1 and c2.loc[0, "eu_etiqueta"] == "A puro"
    assert c2.loc[1, "eu"] is None
    et = c2.loc[0, "entrenadores"]
    assert et[0]["eu"] == 0 and et[1]["eu"] == 1 and et[1]["eu_probs"] == [0.4, 0.6]
    assert j2.loc[0, "eu"] == 1 and j2.loc[0, "eu_probs"] == [0.3, 0.7]
    assert [e["nombre"] for e in meta["estilos"]] == ["A", "B"]
