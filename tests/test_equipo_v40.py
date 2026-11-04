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


def test_posterior_rapida_contrastes_exactos(ensemble_sintetico):
    """Var(u_i − μ_c) y Var(μ_a − μ_c) por Schur coinciden con los contrastes exactos de la posterior."""
    _, _, D, cj = ensemble_sintetico
    P_ = cj[1][1]
    PR = P.PosteriorRapida(P_)
    R = P_.nPS + 2
    ips = np.array([0, 3, 10, P_.nPS - 1])
    exacto = P_.var_contrastes(ips, np.full(len(ips), R))
    assert np.allclose(PR.var_u_menos_mu(ips, R), exacto, rtol=1e-6, atol=1e-10)
    cs = P_.nPS + np.array([0, 1, 3])
    assert np.allclose(PR.var_mu_menos_mu(cs, R), P_.var_contrastes(cs, np.full(3, R)), rtol=1e-5, atol=1e-9)
    assert np.allclose(PR.diag(), P.diag_posterior(P_, np.arange(P_.media.shape[0]), lote=500), rtol=1e-6, atol=1e-10)
    # versión acotada a una referencia (la que usa la exportación): mismos valores para esa referencia, error para otra
    PR2 = P.PosteriorRapida(P_, comps_ref=[R])
    assert np.allclose(PR2.var_u_menos_mu(ips, R), exacto, rtol=1e-6, atol=1e-10)
    assert PR2.WS[0].shape[1] == 1 and np.allclose(PR2.diag(), PR.diag())
    with pytest.raises(KeyError):
        PR2.var_u_menos_mu(ips, R + 1)
    # varianza relativa a la competición principal de cada persona-temporada
    PR3 = P.PosteriorRapida(P_, comps_ref=[R], comp_de_u=D.ps_comp_principal)
    vr = np.stack(PR3.var_rel_u, 1)
    for i in (0, 7, P_.nPS - 1):
        c = P_.nPS + int(D.ps_comp_principal[i])
        assert np.allclose(vr[i], P_.var_contrastes(np.array([i]), np.array([c]))[0], rtol=1e-6, atol=1e-10)


def test_traducir_corte_reproduce_traducir_filas(ensemble_sintetico):
    """La traducción rápida da las mismas fuentes y centros (salvo ruido Monte Carlo) que bbnorm3.exportar.traducir_filas."""
    from bbnorm3 import config as C3, exportar
    cfg3, t, D, cj = ensemble_sintetico
    cfg3 = C3.con(cfg3, **{"prediccion.muestras": 400, "referencia_salida.temporada": "2024-25"})
    nueva = t.iloc[[0]].copy(); nueva["persona_id"] = 99999; nueva["player_id"] = "p99999"; nueva["min"] = 50.0
    filas = pd.concat([t[t["anio"] == 2024].head(60), nueva], ignore_index=True)
    mets = ["usg_pct", "ast_pct", "orapm"]
    a = P.traducir_corte(filas, D, cj, cfg3, mets)
    b = exportar.traducir_filas(filas, D, cj, cfg3)
    assert list(a["fuente_v3"]) == list(b["fuente_v3"]) and a["fuente_v3"].iloc[-1] == "codificador"
    for m in mets:
        sd = (b[f"{m}_v3_hi"] - b[f"{m}_v3_lo"]).to_numpy(float) / 2.563
        d = np.abs(a[f"{m}_v3"].to_numpy(float) - b[f"{m}_v3"].to_numpy(float)) / np.maximum(sd, 1e-9)
        assert np.median(d) < 0.15, (m, np.median(d))        # diferencia ≪ anchura del intervalo: sólo ruido MC


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
    sd_rel = lat[["u1_sd_rel", "u2_sd_rel", "u3_sd_rel"]].to_numpy(float)
    assert np.isfinite(u).all() and (sd > 0).all() and (sd_rel > 0).all() and (sd_rel <= sd + 1e-9).all()
    assert len(meta["sd_rel_mediana_por_dim"]) == 3
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
                        "u1_sd_rel": 0.02, "u2_sd_rel": 0.02, "u3_sd_rel": 0.02, "u4_sd_rel": 0.02,
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


# ------------------------------------------------------------------------------------------ F1 · RAPM multiliga sintético
def _tramos_sinteticos(semilla=3, n_por_liga=4000):
    """Dos ligas, 12 equipos de 9 jugadores; β verdadero = g(x) + ruido; tramos 5 contra 5 con y = Σβ_A − Σβ_B + local + ruido."""
    from bbequipo import rapm as RP
    rng = np.random.default_rng(semilla)
    jug, filas = [], []
    for liga, nivel in (("lg", 1.0), ("lh", -1.0)):
        for e in range(6):
            for j in range(9):
                pid = f"P{liga}{e}{j}"
                x1, x2 = rng.normal(), rng.normal()
                g = nivel + 1.5 * x1 - 0.8 * x2
                jug.append({"persona_id": pid, "temporada": "2024-25", "liga": liga, "team": f"{liga}_T{e}", "x1": x1, "x2": x2,
                            "g": g, "beta": g + rng.normal(0, 0.7), "pocos": j == 8})
    J = pd.DataFrame(jug)
    b = J.set_index("persona_id")["beta"]
    for liga in ("lg", "lh"):
        eq = [f"{liga}_T{e}" for e in range(6)]
        for s in range(n_por_liga):
            ta, tb = rng.choice(eq, 2, replace=False)
            pa = J[J.team == ta]; pb = J[J.team == tb]
            w_a = np.where(pa.pocos, 0.05, 1.0); w_b = np.where(pb.pocos, 0.05, 1.0)
            A = tuple(rng.choice(pa.persona_id, 5, replace=False, p=w_a / w_a.sum()) + "|2024-25")
            B = tuple(rng.choice(pb.persona_id, 5, replace=False, p=w_b / w_b.sum()) + "|2024-25")
            poss = float(rng.uniform(1, 6))
            mu = 3.0 + sum(b[k.split("|")[0]] for k in A) - sum(b[k.split("|")[0]] for k in B)
            y = mu + rng.normal(0, 90 / np.sqrt(poss))
            filas.append({"liga": liga, "temporada": "2024-25", "anio": 2024, "game_id": s, "fase": "regular", "team_a": ta, "team_b": tb,
                          "clutch": bool(rng.random() < 0.05), "playoffs": False, "poss": poss, "y": y,
                          "a_pts": poss * (1.1 + y / 200), "b_pts": poss * 1.1, "A": A, "B": B})
    return J, pd.DataFrame(filas)


def _tabla_prior_sintetica(J, cfg):
    from bbequipo import rapm as RP
    T = pd.DataFrame({"clave": J["persona_id"] + "|2024-25", "persona_id": J["persona_id"], "temporada": "2024-25", "liga": J["liga"],
                      "min": 500.0, "u1": J["x1"], "u2": J["x2"], "pos_E": 1.0, "m_latente": 1.0})
    T.attrs["bloques"] = {"latente": ["u1", "u2"], "pos3": ["pos_E"], "mascara": ["m_latente"]}
    return T


def test_rapm_recupera_beta_y_prior():
    from bbequipo import rapm as RP
    J, tr = _tramos_sinteticos()
    D = RP.construir_diseno(tr, "net")
    assert D.X.shape == (len(tr), D.nJ + len(D.fijos)) and D.nJ == len(J)
    fila = D.X[0].toarray().ravel()
    assert fila[:D.nJ].sum() == 0 and (fila[:D.nJ] != 0).sum() == 10         # +5 −5
    cfg = C.con(CFG, **{"f1.bayes_empirico.iteraciones": 4})
    T = _tabla_prior_sintetica(J, cfg)
    res = RP.ajustar(D, T, cfg, "ridge", progreso=None)
    tb = RP.tabla_beta(res, D).merge(J, on="persona_id")
    r_beta = np.corrcoef(tb["beta_x"], tb["beta_y"])[0, 1]
    r_prior = np.corrcoef(tb["prior"], tb["g"])[0, 1]
    # con el prior VERDADERO y τ = 0,7 la cota es 0,957; sin prior, 0,41 (la información por jugador es limitada:
    # error típico ≈ 1,7 frente a sd(β) ≈ 2,2). El bayes empírico debe quedar cerca de la cota y lejos de «sin prior».
    assert r_beta > 0.8 and r_prior > 0.85, (r_beta, r_prior)
    # el prior pesa más en quien juega poco; la ventaja local se recupera; τ y σ en el orden correcto
    assert tb.loc[tb.pocos, "peso_prior"].mean() > tb.loc[~tb.pocos, "peso_prior"].mean()
    assert abs(np.mean([v for k, v in res["fijos"].items() if k.startswith("c_")]) - 3.0) < 1.0
    assert 0.3 < np.sqrt(res["tau2"][0]) < 1.5 and 60 < np.sqrt(res["sigma2"]) < 130
    # O/D: el diseño tiene dos filas por tramo y β^O − β^D reproduce la escala del net
    Dod = RP.construir_diseno(tr, "od")
    assert Dod.X.shape[0] == 2 * len(tr) and Dod.nC == 2
    rod = RP.ajustar(Dod, T, cfg, "ridge", progreso=None)
    tod = RP.tabla_beta(rod, Dod).merge(J, on="persona_id")
    # el generador sintético no tiene estructura ataque/defensa: basta con que O + D reproduzca el net razonablemente
    assert np.corrcoef(tod["rapm_od"], tod["beta"])[0, 1] > 0.5
    # sin perfil (T = None): el prior es constante y β sigue correlacionando con la verdad
    res0 = RP.ajustar(D, None, cfg, "ridge", progreso=None)
    r0 = np.corrcoef(res0["beta"][:D.nJ], tb.sort_values("clave")["beta_y"])[0, 1]
    assert 0.3 < r0 < r_beta - 0.2, (r0, r_beta)
