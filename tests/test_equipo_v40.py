"""v4.0 · F0: configuración única, perfil ampliado x̃ (latente alineado del ensemble, bloques, avisos) y contrato de
datos (filtro de tramos y decisión de cobertura). Datos sintéticos; no leen data/."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from bbequipo import config as C
from bbequipo import contrato as K
from bbequipo import perfiles as P

CFG = C.cargar()


# ------------------------------------------------------------------------------------------ configuración
def test_configuracion_unica_y_prerregistro():
    for s in ("insumos", "perfil", "contrato", "f1", "f2", "f3", "f4", "f5", "criterios"):
        assert s in CFG, s
    r = P.rasgos(CFG)
    assert len(r) == 16 and len(set(r)) == 16
    assert "pts_p100" not in r and "ts_pct" not in r          # lo que las capas predicen no entra en x̃
    assert {"orapm", "drapm", "usg_pct", "pct_asistidas"} <= set(r)
    assert P.roles(CFG) == ["RESIDUAL", "PROFUNDIDAD", "ROTACION", "TITULAR", "GO_TO_GUY"]
    assert len(P.estilos(CFG)) == 6
    assert CFG["perfil"]["latente"]["K"] == 4
    # la K del perfil es la de la configuración FINAL de la v3.2 (ablación: K = 8 se quitó)
    from bbnorm3 import config as C3
    assert C3.cargar(C.ruta(CFG, "normalizacion"))["latente"]["K"] == 4
    f5 = CFG["criterios"]["f5"]
    assert f5["nc_separacion"] == {"diferencia_minima": 10, "fraccion_minima": 0.62, "ic95_inferior_minimo": 0.55}
    assert CFG["f5"]["nivel_cerno"]["horizontes"]["titular"] == 1
    assert CFG["contrato"]["tramos"]["basura"] == "excluir" and CFG["contrato"]["tramos"]["clutch"] == "covariable"
    assert C.huella(CFG) == C.huella(C.cargar()) and len(C.huella(CFG)) == 10
    assert C.con(CFG, **{"perfil.latente.K": 3})["perfil"]["latente"]["K"] == 3 and CFG["perfil"]["latente"]["K"] == 4


# ------------------------------------------------------------------------------------------ latente: alineamiento
def test_alinear_recupera_la_transformacion_afin():
    rng = np.random.default_rng(1)
    u = rng.normal(size=(500, 3))
    A = np.array([[0.5, -1.0, 0.2], [2.0, 0.3, 0.0], [0.1, 0.1, -1.5]])
    b = np.array([1.0, -2.0, 0.5])
    ref = u @ A.T + b
    A2, b2, r2 = P.alinear(ref, u)
    assert np.allclose(A2, A, atol=1e-8) and np.allclose(b2, b, atol=1e-8) and np.allclose(r2, 1.0)
    med, var = P.aplicar_afin(A2, b2, u, np.full_like(u, 0.04))
    assert np.allclose(med, ref)
    assert np.allclose(var, 0.04 * (A ** 2).sum(1)[None, :])    # Var(ũ_k) = Σ_j A_kj² Var(u_j)
    # la referencia consigo misma es la identidad
    I, z, r2i = P.alinear(ref, ref)
    assert np.allclose(I, np.eye(3), atol=1e-8) and np.allclose(z, 0, atol=1e-8)
    # filas con NaN no rompen el ajuste
    u2 = u.copy(); u2[0] = np.nan
    A3, _, _ = P.alinear(ref, u2)
    assert np.allclose(A3, A, atol=1e-6)


class _Post:
    def __init__(self, Qs, nPS):
        self.lu = [spla.splu(Q.tocsc()) for Q in Qs]
        self.media = np.zeros((Qs[0].shape[0], len(Qs)))
        self.nPS = nPS


def test_diag_posterior_coincide_con_la_inversa_densa():
    rng = np.random.default_rng(2)
    n = 60
    Qs = []
    for _ in range(2):
        B = sp.random(n, n, density=0.08, random_state=rng.integers(1e6)).toarray()
        Q = B @ B.T + np.diag(rng.uniform(0.5, 2.0, n))
        Qs.append(sp.csr_matrix(Q))
    P_ = _Post(Qs, 40)
    idx = np.array([0, 5, 17, 39, 41, 59])
    d = P.diag_posterior(P_, idx, lote=4)                       # lotes más pequeños que el número de índices
    for k, Q in enumerate(Qs):
        assert np.allclose(d[:, k], np.diag(np.linalg.inv(Q.toarray()))[idx], rtol=1e-8)


# ------------------------------------------------------------------------------------------ latente: ensemble sintético
@pytest.fixture(scope="module")
def ensemble_sintetico():
    torch = pytest.importorskip("torch")   # noqa: F841
    from bbnorm3 import config as C3, datos, modelo, niveles
    from test_bbnorm3 import tabla_sintetica
    c32 = C3.cargar(C.ruta(CFG, "normalizacion"))
    cfg3 = C3.con(c32, **{"entrenamiento.pasos": 60, "latente.K": 3, "red.oculta_codificador": 32,
                          "red.oculta_decodificador": 16, "entrenamiento.ipw": False, "inferencia.refinar_pasos": 0})
    t = tabla_sintetica()
    D = datos.construir(t, cfg3, hasta_anio=2024)
    cj = []
    for s in (1, 2):
        m = modelo.entrenar(D, cfg3, s, progreso=None)
        cj.append((m, niveles.posterior(m, D, cfg3)))
    return cfg3, t, D, cj


def test_diag_posterior_completa_es_exacta(ensemble_sintetico):
    """La vía rápida (complemento de Schur sobre los bloques por persona) coincide con e_iᵀ Q⁻¹ e_i."""
    _, _, _, cj = ensemble_sintetico
    P_ = cj[0][1]
    d = P.diag_posterior_completa(P_)
    n = P_.media.shape[0]
    idx = np.r_[np.arange(0, 25), np.arange(P_.nPS - 5, P_.nPS + 4), [n - 1]]
    assert d.shape == (n, 3) and (d > 0).all()
    assert np.allclose(d[idx], P.diag_posterior(P_, idx, lote=7), rtol=1e-7, atol=1e-10)


def test_latente_ensemble_sintetico(ensemble_sintetico):
    cfg3, t, D, cj = ensemble_sintetico
    cfg = C.con(CFG, **{"perfil.latente.K": 3, "perfil.latente.lote_varianza": 50})
    # filas: las del ajuste + una persona nueva con pocos minutos (codificador) + una temporada posterior al ajuste
    nueva = t.iloc[[0]].copy(); nueva["persona_id"] = 99999; nueva["player_id"] = "p99999"; nueva["min"] = 50.0
    futura = t.iloc[[1]].copy(); futura["persona_id"] = 99998; futura["player_id"] = "p99998"
    futura["anio"], futura["temporada"] = 2025, "2025-26"
    filas = pd.concat([t, nueva, futura], ignore_index=True)
    lat, meta = P.latente_ensemble(D, cj, filas, cfg, cfg3, progreso=None)
    assert len(lat) == len(filas) and meta["K"] == 3 and meta["redes"] == 2
    u = lat[["u1", "u2", "u3"]].to_numpy(float)
    sd = lat[["u1_sd", "u2_sd", "u3_sd"]].to_numpy(float)
    assert np.isfinite(u).all() and (sd > 0).all()
    assert (lat["u_fuente"].iloc[:len(t)] == "posterior_conjunta").all()
    assert lat["u_fuente"].iloc[-2] == "codificador"
    assert lat["u_fuente"].iloc[-1] == "codificador_nivel_temporada_anterior"
    # misma persona-temporada en dos ligas → mismo latente
    ps = t["persona_id"].astype(str) + "|" + t["anio"].astype(str)
    dup = ps[ps.duplicated(keep=False)]
    if len(dup):
        g = lat.iloc[:len(t)].groupby(ps.to_numpy())[["u1", "u2", "u3"]].nunique()
        assert (g.loc[dup.unique()] == 1).all().all()
    assert len(meta["r2_alineamiento_por_red"]) == 2 and meta["r2_alineamiento_por_red"][0] == [1.0, 1.0, 1.0]
    assert meta["fuentes"]["posterior_conjunta"] == len(t)
    # con una sola red, el resultado es la propia red (sin varianza entre redes)
    lat1, _ = P.latente_ensemble(D, cj[:1], t, cfg, cfg3, progreso=None)
    assert np.allclose(lat1["u_discrepancia_redes"], 0.0)


# ------------------------------------------------------------------------------------------ perfil por temporada
def _bloques_sinteticos(cfg, temp="2024-25"):
    R, E, X = P.roles(cfg), P.estilos(cfg), P.rasgos(cfg)
    ids = ["a1", "a2", "a3", "b1"]
    theta = pd.DataFrame({"persona_norm": ["1", "2", "3", "4"], "liga": ["lg", "lg", "lg", "lh"], "temporada": temp,
                          "player_id": ids, "team_id": ["T1", "T1", "T2", "T9"], "pos3": ["E", "A", "I", "E"],
                          "edad": [24.0, 31.0, np.nan, 20.0], "min": [900.0, 400.0, 80.0, 500.0]})
    for m in X:
        theta[f"{m}_th"] = [0.1, -0.2, np.nan, 0.5]
        theta[f"{m}_vj"] = [0.01, 0.02, np.nan, 0.03]
    lat = pd.DataFrame({"persona_norm": ["1", "2", "4"], "liga": ["lg", "lg", "lh"], "temporada": temp,
                        "player_id": ["a1", "a2", "b1"], "min": [900.0, 400.0, 500.0],
                        "u1": [0.3, -0.1, 1.0], "u2": [0.0, 0.2, -0.4], "u3": [1, 1, 1], "u4": [0, 0, 0],
                        "u1_sd": 0.1, "u2_sd": 0.1, "u3_sd": 0.1, "u4_sd": 0.1,
                        "u_fuente": ["posterior_conjunta", "posterior_conjunta", "posterior_conjunta"],
                        "u_discrepancia_redes": [0.05, 0.9, 0.02]})
    roles = pd.DataFrame({"liga": ["lg", "lg", "lh"], "temporada": temp, "team_id": ["T1", "T1", "T9"],
                          "player_id": ["a1", "a2", "b1"], "rol_mas_probable": ["TITULAR", "ROTACION", "GO_TO_GUY"],
                          "min_pct": [0.7, 0.4, 0.8], "gs_pct": [1.0, 0.0, 1.0], "H_rol": [0.5, 1.2, 0.3],
                          "rol_fuente": "pbp", "rol_gp": 30, "rol_min_total": [900.0, 400.0, 500.0],
                          "persona_cw_roles": ["P1", "P2", "P4"]})
    probs = np.array([[0, 0, 0.1, 0.9, 0], [0, 0.3, 0.7, 0, 0], [0, 0, 0, 0.2, 0.8]])
    for i, r in enumerate(R):
        roles[f"p_{r}"] = probs[:, i]
    roles["rol_indice_esperado"] = probs @ np.arange(5.0)
    roles["rol_indice"] = roles["rol_mas_probable"].map({r: i for i, r in enumerate(R)})
    estilos = pd.DataFrame({"liga": ["lg", "lg"], "temporada": temp, "player_id": ["a1", "a2"], "estilo": ["spacing", "pintura"],
                            "estilo_p": [0.7, 0.9], "estilo_fiable": [True, True], "estilo_min": [900.0, 400.0]})
    pe = np.array([[0.1, 0.05, 0.7, 0.05, 0.05, 0.05], [0.02, 0.9, 0.02, 0.02, 0.02, 0.02]])
    for i, e in enumerate(E):
        estilos[f"p_{e}"] = pe[:, i]
    pista = pd.DataFrame({"liga": ["lg", "lh"], "temporada": temp, "player_id": ["a1", "b1"], "rapm_obs": [2.0, -1.0],
                          "orapm_obs": [1.5, -0.5], "drapm_obs": [0.5, -0.5], "poss_on_obs": [1800.0, 1000.0]})

    def persona(liga, pids):
        m = {"a1": "P1", "a2": "P2", "b1": "P4"}
        return pids.map(lambda x: m.get(x, f"{liga}:{x}"))
    return theta, lat, {"roles": roles, "estilos": estilos, "pista": pista, "persona": persona}


def test_perfil_temporada_une_bloques_sin_imputar():
    cfg = CFG
    theta, lat, bl = _bloques_sinteticos(cfg)
    p = P.perfil_temporada("2024-25", lat, cfg, theta=theta, bloques=bl)
    assert len(p) == 4 and list(p.columns[:3]) == ["persona_id", "persona_norm", "liga"]
    a1, a2, a3, b1 = (p[p["player_id"] == k].iloc[0] for k in ("a1", "a2", "a3", "b1"))
    assert a1["persona_id"] == "P1" and a3["persona_id"] == "lg:a3"
    assert a1["u1"] == pytest.approx(0.3) and np.isnan(a3["u1"]) and a3["u_fuente"] == "sin_latente"
    assert a1["rol_indice_esperado"] == pytest.approx(2.9) and b1["rol_indice"] == 4
    assert a1["p_spacing"] == pytest.approx(0.7) and np.isnan(a3["p_spacing"])     # ausente = NaN, nunca 0
    assert np.isnan(a3["usg_pct_th"]) and np.isnan(a2["rapm_obs"])
    assert a1["tramo_edad"] == "24-26" and a3["tramo_edad"] == "s/d"
    av = {k: set(p.loc[p["player_id"] == k, "avisos"].iloc[0].split(";")) - {""} for k in ("a1", "a2", "a3", "b1")}
    assert av["a1"] == set()
    assert av["a2"] == {"sin_rapm", "red_discrepante"}
    assert av["a3"] == {"sin_latente", "sin_estilo", "sin_rol", "sin_rapm", "sin_theta", "sin_persona_crosswalk", "muestra_corta"}
    assert av["b1"] == {"sin_estilo"}
    assert bool(a1["completo"]) and not bool(a3["completo"]) and not bool(b1["completo"])
    r = P.resumen_perfil(p, cfg)
    assert r["global"]["filas"] == 4 and r["global"]["rol"] == 0.75 and r["cobertura_min_300"]["theta"] == 1.0
    # sin latente (lat = None) las columnas u existen vacías
    p2 = P.perfil_temporada("2024-25", None, cfg, theta=theta, bloques=bl)
    assert p2["u1"].isna().all() and (p2["u_fuente"] == "sin_latente").all()


# ------------------------------------------------------------------------------------------ contrato de datos
def test_contrato_filtra_tramos_segun_las_reglas():
    df = pd.DataFrame({"game_id": [1, 1, 1, 1, 2, 2], "fase": ["regular"] * 5 + ["copa"], "sec": [100, 50, 30, 10, 200, 60],
                       "team_a": "A", "team_b": "B", "quinteto_a": ["q1", "q1", "q2", "q2", "q3", "q3"],
                       "quinteto_b": ["r1", "r1", "r1", "r2", "r3", "r3"], "n_a": [5, 5, 4, 5, 5, 5], "n_b": [5, 5, 5, 5, 5, 5],
                       "clutch": [False, True, False, False, False, False], "basura": [False, False, False, True, False, False],
                       "a_fga": [10, 5, 3, 1, 20, 6], "a_fta": [2, 0, 0, 0, 4, 0], "a_oreb": [1, 0, 0, 0, 2, 0],
                       "a_tov": [2, 1, 0, 0, 3, 1], "b_fga": [9, 4, 3, 0, 18, 5], "b_fta": [0, 2, 0, 0, 6, 0],
                       "b_oreb": [0, 1, 0, 0, 1, 0], "b_tov": [1, 1, 0, 0, 2, 0]})
    assert np.allclose(K.posesiones(df, "a")[:2], [10 + 0.88 - 1 + 2, 5 + 0 - 0 + 1])
    tr, info = K.filtrar_tramos(df, CFG)
    assert info == {"tramos": 6, "basura_excluidos": 1, "incompletos_excluidos": 1, "fase_excluidos": 1,
                    "posesiones_minimas_excluidos": 0, "tramos_validos": 3}
    assert set(tr.index) == {0, 1, 4} and (tr["h"] == 1.0).all()
    assert tr.loc[0, "poss"] == pytest.approx(0.5 * (11.88 + 10))
    inv = pd.DataFrame({"liga": ["a", "b", "c", "d"], "temporada": "2024-25",
                        "fraccion_partidos_con_quintetos": [0.99, 0.70, 0.30, np.nan], "tramos_por_partido": [40, 30, 35, 2]})
    d = K.decidir(inv, CFG)
    assert list(d["decision"]) == ["incluida", "incluida_con_aviso", "excluida", "excluida"]
    inv2 = inv.assign(fraccion_partidos_con_quintetos=0.99, tramos_por_partido=[40, 3.5, 40, 40])
    assert list(K.decidir(inv2, CFG)["decision"]) == ["incluida", "excluida", "incluida", "incluida"]
