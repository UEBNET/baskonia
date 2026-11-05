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


# ---------------------------------------------------------------------------------------------- F2-A · sinergia de pares
class _RasgosSinteticos:
    """Sustituto mínimo de sinergia.Rasgos: z por clave desde un diccionario (sin perfil → 0)."""

    def __init__(self, Z: dict[str, np.ndarray], p: int):
        self.Z, self.p = Z, p

    def de(self, claves):
        return np.array([self.Z.get(k, np.zeros(self.p)) for k in claves])


def _tramos_sinergia(rng, n_jug=60, n_tramos=6000, p=5):
    from bbequipo import sinergia as S
    Z = {f"j{i}": rng.normal(size=p) for i in range(n_jug)}
    R = _RasgosSinteticos(Z, p)
    B = rng.normal(size=(p, 2)); M = B @ B.T - 0.5 * np.eye(p)   # simétrica, rango bajo + diagonal
    ids = list(Z)
    A = [list(rng.choice(ids, 5, replace=False)) for _ in range(n_tramos)]
    Bq = [list(rng.choice([j for j in ids if j not in a], 5, replace=False)) for a in A]
    tr = pd.DataFrame({"A": A, "B": Bq, "poss": rng.uniform(2, 20, n_tramos),
                       "liga": "x", "temporada": "t", "game_id": rng.integers(0, 300, n_tramos)})
    phi = np.zeros(n_tramos)
    for s, (qa, qb) in enumerate(zip(A, Bq)):
        for q, sg in ((qa, 1.0), (qb, -1.0)):
            for a in range(5):
                for b in range(a + 1, 5):
                    phi[s] += sg * float(Z[q[a]] @ M @ Z[q[b]])
    return S, tr, R, M, phi


def test_sinergia_recupera_M_por_quintetos():
    """y = Σ_{A} φ − Σ_{B} φ + ruido con φ = zᵢᵀ M zⱼ: la fila lineal ⟨M, Q_A − Q_B⟩ y el ridge exacto recuperan M."""
    rng = np.random.default_rng(3)
    S, tr, R, M, phi = _tramos_sinergia(rng)
    sigma2 = 4.0
    w = tr["poss"].to_numpy(float)
    r = phi + rng.normal(size=len(tr)) * np.sqrt(sigma2 / w)
    # la fila u_s reproduce la suma de las 10 parejas de cada quinteto
    idx, U = next(S.rasgos_tramos(tr, R, lote=len(tr)))
    iu, _ = S._iu(R.p)
    assert np.allclose(U @ M[iu], phi, atol=1e-9)
    G, b, rr = S.acumular(tr, R, r, w)
    fit = S.ajustar_M(G, b, rr, len(tr), sigma2, [1e-3, 1e-2, 1e-1, 1.0, 10.0])
    Mh = S.vec_a_matriz(fit["m"], R.p)
    assert np.corrcoef(Mh[iu], M[iu])[0, 1] > 0.95
    Mr, proy = S.truncar(Mh, 3)
    assert np.allclose(Mr, (proy["P"] * proy["w"]) @ proy["P"].T)
    assert np.linalg.norm(Mr - M) < 0.5 * np.linalg.norm(M)   # M tiene rango 2 + diagonal: rango 3 la aproxima


def test_psi_no_se_publica_si_el_residuo_es_ruido():
    """Con residuo puro ruido, la línea base ψ = 0 gana la validación cruzada y no se publica ninguna pareja; con un efecto
    propio de pareja real, se publica y recupera el signo."""
    rng = np.random.default_rng(5)
    S, tr, R, M, phi = _tramos_sinergia(rng, n_jug=20, n_tramos=4000)
    w = tr["poss"].to_numpy(float)
    ruido = rng.normal(size=len(tr)) * np.sqrt(4.0 / w)
    out = S.psi_parejas(tr, ruido, w, 4.0, [0.5, 1.0, 2.0, 4.0], 3, 0, 100.0)
    assert out["kappa"] == 0.0 and out["parejas_publicadas"] == 0
    assert min(out["error_cv"], key=out["error_cv"].get) == 0.0
    # efecto propio grande en la pareja (j0, j1)
    psi_real = np.array([3.0 * sum(sg for q, sg in ((a, 1.0), (b, -1.0)) if "j0" in q and "j1" in q) for a, b in zip(tr["A"], tr["B"])])
    out2 = S.psi_parejas(tr, ruido + psi_real, w, 4.0, [0.5, 1.0, 2.0, 4.0], 3, 0, 100.0)
    assert out2["kappa"] > 0 and out2["psi"][("j0", "j1")][0] > 1.0


# ---------------------------------------------------------------------------------------------- F3 · función de conjunto
def test_conjunto_aprende_una_funcion_no_aditiva_del_quinteto():
    """y = g(S_A) − g(S_B) + ruido con g no aditiva (cuadrado de la suma de un rasgo): la red deep sets reduce el RMSE
    fuera de muestra frente a 0 y frente a una red sin entrenar; con residuo puro ruido no inventa estructura."""
    from bbequipo import conjunto as CJ
    rng = np.random.default_rng(11)
    n_jug, p, n = 80, 6, 12000
    Z = rng.normal(size=(n_jug, p))
    idx = np.array([rng.choice(n_jug, 10, replace=False) for _ in range(n)])
    g = lambda q: 0.6 * (Z[q, 0].sum(-1) ** 2 - 5) + Z[q, 1].sum(-1) * Z[q, 2].sum(-1) / 3
    y = g(idx[:, :5]) - g(idx[:, 5:]) + rng.normal(size=n) * 1.0
    w = np.ones(n)
    cfg = {"f3": {"oculta_phi": 16, "oculta_rho": 16, "decaimiento_pesos": 1e-3, "semillas": 2, "pasos": 1500, "lote": 1024, "lr": 3e-3}}
    red = CJ.ConjuntoNet(Z, cfg)
    tr, te = np.arange(0, 9000), np.arange(9000, n)
    red.ajustar(idx[tr], y[tr], w[tr], 0)
    pred = red.predecir(idx[te])
    rmse0, rmse1 = np.sqrt(np.mean(y[te] ** 2)), np.sqrt(np.mean((y[te] - pred) ** 2))
    assert rmse1 < 0.7 * rmse0, (rmse0, rmse1)
    assert np.corrcoef(pred, y[te])[0, 1] > 0.7
    # sin perfil → índice extra → fila 0 → g constante: la diferencia A−B de dos quintetos sin perfil es 0
    sin = np.full((3, 10), n_jug)
    assert np.allclose(red.predecir(sin), 0.0, atol=1e-6)
    # ruido puro: la red muy regularizada no debe empeorar fuera de muestra de forma apreciable
    ruido = rng.normal(size=n)
    red2 = CJ.ConjuntoNet(Z, {"f3": {**cfg["f3"], "decaimiento_pesos": 1e-2}})
    red2.ajustar(idx[tr], ruido[tr], w[tr], 0)
    pr2 = red2.predecir(idx[te])
    assert np.sqrt(np.mean((ruido[te] - pr2) ** 2)) < 1.03 * np.sqrt(np.mean(ruido[te] ** 2))


# ---------------------------------------------------------------------------------------------- F4 · capa de equipo y A5
def test_calibracion_f4_recupera_c_y_d_y_cubre():
    """Net_{t+1} = c·T1' + d·Net_t + ruido: la calibración con cortes anteriores recupera (c, d) y el intervalo conformal
    cubre ≈ 80 % en el corte siguiente; la primera pasada (sin cortes previos) se marca con sus propios coeficientes."""
    from bbequipo import equipo as EQ
    rng = np.random.default_rng(7)
    filas = []
    for corte in (2021, 2022, 2023):
        n = 150
        T1 = rng.normal(0, 8, n); n0 = rng.normal(0, 5, n); sd = rng.uniform(1, 2, n)
        n1 = 0.5 * T1 + 0.3 * n0 + rng.normal(0, 3, n)
        for i in range(n):
            filas.append({"corte": corte, "grupo": "g" if i % 2 else "h", "liga": "x", "T1": T1[i], "T1_sd": sd[i], "T1_aditivo": T1[i], "T1_oraculo": T1[i],
                          "net_ant": n0[i], "net_nuevo": n1[i], "delta_real": n1[i] - n0[i], "n_sin_beta": i % 5, "n_plantilla": 15, "min_altas": rng.uniform(0, 1),
                          **{f"T1_{q}": T1[i] + z * sd[i] for q, z in (("p05", -1.64), ("p10", -1.28), ("p25", -0.67), ("p75", 0.67), ("p90", 1.28), ("p95", 1.64))}})
    pred = pd.DataFrame(filas)
    cal = EQ.calibrar_prediccion(pred, [2021, 2022, 2023])
    u = cal[cal["corte"] == 2023]
    assert abs(u["c_cal"].mean() - 0.5) < 0.08 and abs(u["d_cal"].mean() - 0.3) < 0.12
    cal = EQ.calibrar_intervalos(cal, [2021, 2022, 2023])
    cob = np.mean((u.index.map(lambda i: cal.loc[i, "delta_real"] >= cal.loc[i, "lo80"] and cal.loc[i, "delta_real"] <= cal.loc[i, "hi80"])))
    assert 0.7 < cob < 0.9, cob
    # el MAE calibrado debe batir a la persistencia con holgura en el corte fuera de muestra
    mae_cal = np.mean(np.abs(u["delta_real"] - cal.loc[u.index, "delta_pred"])); mae_pers = np.mean(np.abs(u["delta_real"]))
    assert mae_cal < 0.8 * mae_pers


def test_a5_recupera_spline_y_matriz_contraida():
    """Residuo = spline cóncavo de Δmin + c·Δrol + δ sólo en un par: A5 recupera la curvatura, c y la δ del par poblado, y
    deja ≈ 0 los pares con pocos casos (contracción)."""
    from bbequipo import a5 as A
    rng = np.random.default_rng(3)
    n = 4000
    roles = np.array(A.ROLES[1:])
    ro = rng.choice(roles, n); rd = rng.choice(roles, n)
    dm = rng.normal(0, 5, n); drol = np.array([A.IDX[b] - A.IDX[a] for a, b in zip(ro, rd)], float) + rng.normal(0, 0.3, n)
    s = np.where(dm < 0, 0.3 * dm, 0.1 * dm)                      # cóncavo: más pendiente a la izquierda
    delta = np.where((ro == "ROTACION") & (rd == "GO_TO_GUY"), 2.0, 0.0)
    r = s + 0.8 * drol + delta + rng.normal(0, 1.0, n)
    cfg = {"minutos": {"cuantiles_nudos": [0.25, 0.5, 0.75]}, "transicion_rol": {"min_casos_par_aviso": 30}}
    mod = A.A5(cfg).ajustar(r, dm, drol, ro, rd, np.full(n, 25.0))
    assert abs(mod.coef_lin[4] - 0.8) < 0.1
    pend = np.cumsum(mod.coef_lin[:4])                            # pendientes por tramo
    assert pend[0] > pend[-1] + 0.1                               # cóncava
    assert mod.pares["ROTACION>GO_TO_GUY"]["delta"] > 1.2
    otros = [v["delta"] for k, v in mod.pares.items() if k != "ROTACION>GO_TO_GUY"]
    assert max(abs(x) for x in otros) < 0.6
    pred = mod.predecir(dm, drol, ro, rd, np.full(n, 25.0))
    assert np.mean(np.abs(r - pred)) < np.mean(np.abs(r - (0.2 * dm + 0.8 * drol)))   # mejor que una recta


# ---------------------------------------------------------------------------------------------- F5 · anclas
def test_anclas_percentil_esperado_y_complemento_companeros():
    """E_pred[F_ref(C)] empuja hacia 50 con más incertidumbre; la agregación del efecto sobre compañeros pondera por cuotas."""
    from bbequipo import anclas as A, dirigidos as DG
    rng = np.random.default_rng(2)
    F = A.Empirica(rng.normal(10, 3, 5000))
    estrecha = pd.Series({"C_lo90": 13.5, "C_lo80": 13.7, "C_lo50": 13.9, "C_pred": 14.0, "C_hi50": 14.1, "C_hi80": 14.3, "C_hi90": 14.5})
    ancha = pd.Series({"C_lo90": 4.0, "C_lo80": 6.0, "C_lo50": 10.0, "C_pred": 14.0, "C_hi50": 18.0, "C_hi80": 22.0, "C_hi90": 24.0})
    nc_e, lo_e, hi_e = A.percentil_esperado(F, A.muestras_predictivas(estrecha, "C", 2000, rng))
    nc_a, lo_a, hi_a = A.percentil_esperado(F, A.muestras_predictivas(ancha, "C", 2000, rng))
    assert nc_e > 85 and 50 < nc_a < nc_e and lo_e <= nc_e <= hi_e and (hi_a - lo_a) > (hi_e - lo_e)
    class Lineal:
        def predecir(self, X): return X[:, 0] * 0 + X[:, -1]            # efecto = último rasgo del producto z_X ⊙ z_Y
    mods = {"modelos": {"d_pts100": Lineal()}}
    zx = np.array([1.0, 2.0]); Zy = np.array([[0.0, 1.0], [0.0, 3.0]]); cuotas = np.array([2.5, 2.5])
    out = DG.efectos_sobre_companeros(mods, zx, Zy, cuotas)
    assert abs(out["d_pts100"] - (0.5 * 2.0 + 0.5 * 6.0)) < 1e-9
