"""Tests sintéticos de la v4.1 · capa E (F0): prueba de orden de sinergias, auditoría de ausencias, inventario y
configuración. Ninguno lee datos reales: cada test construye su liga sintética con una verdad conocida."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bbequipo.ecosistema import config as CE
from bbequipo.ecosistema import orden_sinergias as OS

CFG = CE.cargar()


# =============================================================================================== liga sintética
def liga_sintetica(sd_pareja: float = 0.0, sd_quinteto: float = 0.0, equipos: int = 8, plantilla: int = 9, partidos: int = 360,
                   tramos_partido: int = 28, sigma: float = 110.0, semilla: int = 0) -> pd.DataFrame:
    """Tramos de UNA liga-temporada (formato de bbequipo.rapm.tramos) con β ~ N(0, 4²), sinergia de pareja ~ N(0, sd_pareja²)
    y efecto propio de quinteto ~ N(0, sd_quinteto²); y_s = 2 + Σ_A(β + pareja + quinteto) − Σ_B(…) + ε, ε ~ N(0, σ²/n_s)."""
    rng = np.random.default_rng(semilla)
    jug = {e: [f"P{e:02d}{j:02d}|2024-25" for j in range(plantilla)] for e in range(equipos)}
    beta = {k: rng.normal(0, 4) for v in jug.values() for k in v}
    pareja, quinteto = {}, {}
    peso = np.linspace(2.0, 0.4, plantilla)
    peso /= peso.sum()

    def efecto(e, q):
        s = 0.0
        for i in range(5):
            for j in range(i + 1, 5):
                k = (q[i], q[j])
                if k not in pareja:
                    pareja[k] = rng.normal(0, sd_pareja) if sd_pareja > 0 else 0.0
                s += pareja[k]
        if sd_quinteto > 0:
            if q not in quinteto:
                quinteto[q] = rng.normal(0, sd_quinteto)
            s += quinteto[q]
        return s + sum(beta[k] for k in q)

    filas = []
    for g in range(partidos):
        a, b = rng.choice(equipos, 2, replace=False)
        for _ in range(tramos_partido):
            qa = tuple(sorted(rng.choice(jug[a], 5, replace=False, p=peso)))
            qb = tuple(sorted(rng.choice(jug[b], 5, replace=False, p=peso)))
            n = float(rng.poisson(7) + 1)
            y = 2.0 + efecto(a, qa) - efecto(b, qb) + rng.normal(0, sigma / np.sqrt(n))
            filas.append({"liga": "sint", "temporada": "2024-25", "anio": 2024, "game_id": g, "fase": "regular",
                          "team_a": str(a), "team_b": str(b), "clutch": False, "playoffs": False, "poss": n,
                          "a_pts": 0.0, "b_pts": 0.0, "A": qa, "B": qb, "y": y})
    return pd.DataFrame(filas)


def _cfg_rapido(replicas: int = 2, min_pos: float = 150.0, plantado: list | None = None, sd: float = 3.0) -> dict:
    return CE.con(CFG, **{"orden_sinergias.calibracion_nula.replicas": replicas,
                          "orden_sinergias.calibracion_plantada.ordenes": plantado or [],
                          "orden_sinergias.calibracion_plantada.sd": sd,
                          "orden_sinergias.calibracion_plantada.replicas": 2,
                          "orden_sinergias.min_posesiones_tercio": min_pos,
                          "orden_sinergias.version_a.lambda_rejilla": [1000, 3000, 10000]})


# =============================================================================================== piezas
def test_claves_unidad_y_descomponer_son_inversas():
    rng = np.random.default_rng(1)
    nP = 3000
    P = np.sort(np.array([rng.choice(nP, 5, replace=False) for _ in range(200)]), axis=1)
    for o in OS.ORDENES:
        k = OS.claves_unidad(P, o, nP)
        assert k.shape == (200, len(OS.COMB[o]))
        for c, cmb in enumerate(OS.COMB[o]):
            assert np.array_equal(OS.descomponer(k[:, c], o, nP), P[:, cmb])


def test_agregar_y_propio_exactos_en_un_caso_pequeno():
    tr = pd.DataFrame({"liga": "x", "temporada": "t", "game_id": [1, 1], "team_a": ["A", "A"], "team_b": ["B", "B"],
                       "clutch": False, "playoffs": False, "poss": [10.0, 30.0], "y": [0.0, 0.0],
                       "A": [("a1", "a2", "a3", "a4", "a5"), ("a1", "a2", "a3", "a4", "a6")],
                       "B": [("b1", "b2", "b3", "b4", "b5")] * 2})
    lt = OS.preparar(tr, 0)
    r = np.array([10.0, 2.0])                      # residuo del local en cada tramo
    m = np.ones(2, bool)
    ag1, ag2 = OS.agregar(lt, m, r, 1), OS.agregar(lt, m, r, 2)
    ij = {k: i for i, k in enumerate(lt.claves)}
    tA, tB = lt.equipos.index("A"), lt.equipos.index("B")
    assert ag1.loc[(tA, ij["a1"]), "x"] == pytest.approx((10 * 10 + 30 * 2) / 40)
    assert ag1.loc[(tA, ij["a5"]), "x"] == pytest.approx(10.0)
    assert ag1.loc[(tB, ij["b1"]), "x"] == pytest.approx(-(10 * 10 + 30 * 2) / 40)   # el visitante con signo cambiado
    p2 = OS.propio(ag2, ag1, 2, lt.nP)
    k15 = ij["a1"] * lt.nP + ij["a5"]
    assert p2.loc[(tA, k15)] == pytest.approx(10.0 - (4.0 + 10.0) / 2)            # pareja − media de sus 2 jugadores
    k12 = ij["a1"] * lt.nP + ij["a2"]
    assert p2.loc[(tA, k12)] == pytest.approx(0.0)                                # siempre juntos: propio nulo


def test_estimar_recupera_una_covarianza_conocida():
    rng = np.random.default_rng(3)
    n = 4000
    s = rng.normal(0, 2.0, n)                                                     # parte estable, varianza 4
    na, nb = rng.uniform(150, 600, n), rng.uniform(150, 600, n)
    xa, xb = s + rng.normal(0, 60, n) / np.sqrt(na), s + rng.normal(0, 60, n) / np.sqrt(nb)
    f = pd.DataFrame({"liga": "x", "temporada": "t", "team": rng.integers(0, 400, n), "key": np.arange(n), "orden": 2,
                      "rot": 0, "xa": xa, "xb": xb, "pa": xa, "pb": xb, "na": na, "nb": nb, "tipo": "obs"})
    r = OS.estimar(f, 300, 1)["pareja_propio"]
    assert r["V"] == pytest.approx(4.0, rel=0.15)
    assert r["V_ic95"][0] < 4.0 < r["V_ic95"][1]
    assert r["c_ruido"] == pytest.approx(3600.0, rel=0.1)                         # ruido por posesión


# =============================================================================================== extremo a extremo (sintético)
@pytest.fixture(scope="module")
def sin_sinergia():
    tr = liga_sintetica(0.0, semilla=11)
    lt = OS.preparar(tr, 5)
    cfg = _cfg_rapido()
    return OS.procesar_lt(lt, "a", cfg, con_predictiva=False), cfg


@pytest.fixture(scope="module")
def con_sinergia():
    tr = liga_sintetica(3.0, semilla=12)
    lt = OS.preparar(tr, 5)
    cfg = _cfg_rapido(plantado=[2], sd=3.0)
    return OS.procesar_lt(lt, "a", cfg, con_predictiva=False), cfg


def test_tercios_por_partido_y_determinismo():
    tr = liga_sintetica(0.0, partidos=60, semilla=2)
    a, b = OS.preparar(tr, 9), OS.preparar(tr, 9)
    assert np.array_equal(a.tercio, b.tercio)
    for g in np.unique(a.partido):                                                # todo el partido en el mismo tercio
        assert len(np.unique(a.tercio[a.partido == g])) == 1
    assert set(np.bincount(a.tercio)) and np.bincount(a.tercio).min() > 0


def test_nulo_corrige_el_sesgo_del_error_de_beta(sin_sinergia):
    """Sin sinergia: la covarianza bruta de los jugadores es grande (error de β común a los dos tercios de medida) y la
    calibración nula la reproduce; la varianza propia corregida de la pareja es compatible con 0."""
    res, _ = sin_sinergia
    e = OS.estimar(res["filas"], 300, 4)
    assert e["jugador_bruto"]["V"] > 1.0 and e["jugador_bruto"]["V_nulo"] > 1.0
    assert abs(e["jugador_bruto"]["V_corregido"]) < 0.5 * e["jugador_bruto"]["V"]
    lo, hi = e["pareja_propio"]["V_corregido_ic95"]
    assert lo < 0.0 < hi or abs(e["pareja_propio"]["V_corregido"]) < 0.5


def test_detecta_sinergia_de_pareja_y_corrige_la_atenuacion(con_sinergia):
    """Con sinergia de pareja de DT 3 (varianza 9): la varianza propia corregida es positiva pero ATENUADA (la medida
    «propia» del §2.2 pierde la parte que absorben los jugadores); la calibración plantada (k) recupera el orden de magnitud."""
    res, _ = con_sinergia
    e = OS.estimar(res["filas"], 300, 4, sd_plantado=3.0)["pareja_propio"]
    assert e["V_corregido_ic95"][0] > 0
    assert e["V_corregido"] < 0.5 * 9.0                       # atenuación fuerte en este diseño (plantillas de 9)
    assert 0.02 < e["atenuacion_k"] < 0.6
    assert 4.0 < e["V_verdadera_est"] < 20.0                  # varianza verdadera 9


def test_version_b_con_prior_exacto_y_paridad_de_fijos():
    """(b) con g = β verdadero y τ pequeño: el ajuste se queda en el prior; los efectos fijos recuperan la ventaja local."""
    tr = liga_sintetica(0.0, partidos=120, semilla=21)
    lt = OS.preparar(tr, 1)
    rng = np.random.default_rng(21)                  # β verdadero: mismo orden de sorteo que liga_sintetica
    beta = {f"P{e:02d}{j:02d}|2024-25": rng.normal(0, 4) for e in range(8) for j in range(9)}
    g = np.array([beta[k] for k in lt.claves])
    cfg = CE.con(CFG, **{"orden_sinergias.version_b.tau": 0.05})
    X = OS.diseno(lt)
    coef, inf = OS.ajustar_aditivo(lt, X, np.ones(lt.n, bool), "b", cfg["orden_sinergias"], g=g, sigma=110.0)
    assert np.max(np.abs(coef[:lt.nP] - g)) < 0.5
    assert coef[lt.nP] == pytest.approx(2.0, abs=0.6)


def test_procesar_es_determinista():
    tr = liga_sintetica(0.0, partidos=90, semilla=4)
    cfg = _cfg_rapido(replicas=1, min_pos=60.0)
    a = OS.procesar_lt(OS.preparar(tr, 3), "a", cfg, con_predictiva=False)["filas"]
    b = OS.procesar_lt(OS.preparar(tr, 3), "a", cfg, con_predictiva=False)["filas"]
    pd.testing.assert_frame_equal(a, b)


def test_predictiva_no_premia_unidades_sin_sinergia():
    """Sin sinergia y con el control de jugadores reajustados, los efectos de pareja no mejoran el error fuera de muestra
    de forma apreciable (|Δ relativo| < 0,5 %)."""
    tr = liga_sintetica(0.0, partidos=150, semilla=8)
    cfg = _cfg_rapido(replicas=0, min_pos=60.0)
    cfg = CE.con(cfg, **{"orden_sinergias.prueba_predictiva.ordenes": [2],
                         "orden_sinergias.prueba_predictiva.lambda_rejilla": [1000, 100000]})
    res = OS.procesar_lt(OS.preparar(tr, 2), "a", cfg, con_nulo=False, con_predictiva=True)
    p = res["predictiva"]
    assert abs(p["sse1"].sum() / p["sse0"].sum() - 1.0) < 0.005
    assert (p["sse0"].sum() <= p["sse_k"].sum() * 1.01)        # reajustar jugadores no empeora


# =============================================================================================== ausencias
def test_ausencias_detecta_huecos_internos_y_rachas():
    from bbequipo.ecosistema import ausencias as AU
    filas = []
    for g in range(10):
        for p, mins in (("p1", 30.0), ("p2", 25.0), ("p3", 5.0)):
            jugo = not (p == "p1" and g in (3, 6, 7)) and not (p == "p2" and g in (0, 9))
            filas.append({"liga": "x", "temporada": "t", "game_id": str(g), "fase": "regular", "team_id": "T",
                          "player_id": p, "persona_id": p, "jugo": jugo, "min": mins if jugo else 0.0,
                          "fecha": pd.Timestamp("2024-10-01") + pd.Timedelta(days=g)})
    d = pd.DataFrame(filas)
    aus, info = AU.ausencias_liga_temporada(d, {"fase": "regular"}, 0.15)
    a1 = aus[aus["player_id"] == "p1"].sort_values("orden")
    assert list(a1["orden"]) == [3, 6, 7]                        # p2 falta en el primero y el último: no cuentan
    assert list(a1["long_episodio"]) == [1, 2, 2]
    assert set(aus["player_id"]) == {"p1"}                       # p3 no es de rotación (< 15 % de los minutos)
    assert info["equipo_partidos_un_ausente"] == 3


# =============================================================================================== inventario y configuración
def test_inventario_patrones():
    from bbequipo.ecosistema import inventario as INV
    fa = INV.PATRONES_FIT_ADAPT
    assert fa["fit_texto"].search("Índice Fit del jugador")
    assert fa["adapt_texto"].search("Adaptación (ADAPT%)")
    assert not fa["fit_id"].search("import bbfit")
    assert INV.PATRONES_CLUB_TEMP["club"].search("Kosner Baskonia")
    assert INV.PATRONES_CLUB_TEMP["temporada"].search("temporada 2026-27")


def test_configuracion_y_criterios_prerregistrados():
    c = CE.cargar()
    assert c["version"] == "v4.1" and c["base"]["commit"] == "6fb6abd"
    cr = c["criterios"]
    assert cr["comunes"]["cortes_decision"] == [2022, 2023, 2024] and cr["comunes"]["corte_calibracion"] == 2021
    assert cr["f1"]["paridad_capa4_pts100"] == 0.01
    assert cr["f2"]["monotonia_no_peor_que_im_v40"] == {"spearman_ref": 0.149, "ic95_inferior_diferencia": -0.02}
    assert cr["f2"]["cobertura_80"] == [0.75, 0.85] and cr["f2"]["calibracion_deciles_tolerancia"] == 7
    assert cr["f3_trios"]["dt_phi_trio_minima"] == 0.10
    assert set(cr["f3_sellos"]) >= {"alta", "media", "baja", "lineas_base"}
    assert c["comunes"]["bootstrap"] == 2000
    assert CE.semilla(c, "x") == CE.semilla(c, "x") != CE.semilla(c, "y")


# =============================================================================================== modelo mixto (REML)
def test_mixto_formula_rapida_igual_a_reml_por_fuerza_bruta():
    """−2ℓ_R por las ecuaciones del modelo mixto (Henderson) = REML con V explícita, salvo la constante Σ log w."""
    from bbequipo.ecosistema import sinergia_mixta as SM
    tr = liga_sintetica(1.0, equipos=4, plantilla=7, partidos=24, tramos_partido=6, semilla=31)
    lt = OS.preparar(tr, 0)
    S = SM.Sistema(lt, (2,), g=None)
    S.preparar("pareja")
    gt, g2 = 4.0 / 110 ** 2, 1.0 / 110 ** 2
    rapido, _ = S.m2ll({"jugadores": gt, "pareja": g2})
    A = S.A.toarray()
    F, X, Z = A[:, :S.p], A[:, S.ini[1]:S.ini[2]], A[:, S.ini[2]:S.ini[3]]
    V1 = np.diag(1.0 / lt.w) + gt * X @ X.T + g2 * Z @ Z.T
    Vi = np.linalg.inv(V1)
    FtVF = F.T @ Vi @ F
    P = Vi - Vi @ F @ np.linalg.solve(FtVF, F.T @ Vi)
    n, p = lt.n, S.p
    s2 = float(S.y @ P @ S.y) / (n - p)
    bruto = (n - p) * np.log(s2) + np.linalg.slogdet(V1)[1] + np.linalg.slogdet(FtVF)[1] + (n - p)
    assert rapido - bruto == pytest.approx(np.sum(np.log(lt.w)), abs=1e-6)
    # γ → 0 es el modelo sin el bloque
    sin, _ = S.m2ll({"jugadores": gt})
    casi, _ = S.m2ll({"jugadores": gt, "pareja": 1e-14})
    assert casi == pytest.approx(sin, abs=1e-4)


def _mixto(sd, semilla):
    from bbequipo.ecosistema import sinergia_mixta as SM
    tr = liga_sintetica(sd, semilla=semilla)
    lt = OS.preparar(tr, 0)
    cm = CFG["sinergia_mixta"]
    c = SM.curvas_lt(lt, "a", 2, cm, None, {}, cm["q_max_denso"])
    return SM.agregar([c], 200, 1)


def test_mixto_recupera_la_sinergia_de_pareja_plantada():
    """Sinergia de pareja de DT 3: el modelo mixto la recupera sin atenuación (la medida «propia» del §2.2 veía ≈ 1/10)."""
    r = _mixto(3.0, 12)
    lo, hi = r["sigma_ic95_perfil"]
    assert lo <= 3.0 <= hi and lo > 0.5
    assert 2.0 < r["sigma"] < 4.0
    assert r["p_sigma_0"] < 1e-3


def test_mixto_sin_sinergia_no_inventa():
    r = _mixto(0.0, 11)
    assert r["sigma_ic95_perfil"][0] == 0.0 and r["sigma"] < 1.5


def test_ruido_ampliado_recupera_la_heterocedasticidad():
    """Var(y_s) = σ²·(1/n + c/n²) con c = 1,5: preparar_ampliado estima c y añade los efectos fijos del marcador."""
    from bbequipo.ecosistema import sinergia_mixta as SM
    tr = liga_sintetica(0.0, partidos=300, sigma=110.0, semilla=41)
    rng = np.random.default_rng(41)
    n = tr["poss"].to_numpy()
    tr["y"] = tr["y"] + rng.normal(0, 110.0 * np.sqrt(1.5) / n)          # término c/n² con c = 1,5
    tr["margen"] = rng.integers(-20, 21, len(tr)).astype(float)
    tr["periodo"] = rng.integers(1, 5, len(tr))
    cfg = CE.con(CFG, **{"sinergia_mixta.ruido.modelo": "ampliado"})
    lt, info = SM.preparar_ampliado(tr, 0, cfg)
    assert info["modelo"] == "ampliado" and info["fijos_marcador"] == 13
    assert 0.9 < info["c"] < 2.3
    assert lt.F.shape[1] == 3 + 13 and np.all(lt.w < n)                  # pesos 1/(1/n + c/n²) < n
    lt0, info0 = SM.preparar_ampliado(tr, 0, CE.con(CFG, **{"sinergia_mixta.ruido.modelo": "simple"}))
    assert info0 == {"modelo": "simple"} and np.allclose(lt0.w, n)


# =============================================================================================== capa XP (puntos esperados)
def test_catalogo_xp_y_codigo_coinciden():
    """Todo campo no «propuesto» del catálogo tiene implementación registrada, y no hay implementación sin catálogo."""
    from bbequipo.ecosistema import puntos_esperados as PE
    cat = CFG["puntos_esperados"]["catalogo"]
    activos = {(v["grano"], k) for k, v in cat.items() if v["estado"] != "propuesto"}
    assert activos == set(PE.CAMPOS)
    for k, v in cat.items():
        assert v["grano"] in ("tiro", "tramo", "jugador") and v["estado"] in ("validado", "experimental", "propuesto")
        assert v.get("def") and v.get("unidad")


def _tiros_sinteticos():
    q_a, q_b = "1|2|3|4|5", "6|7|8|9|10"
    filas = []
    for i, (tipo, anot, x, y, t, eq) in enumerate([("T2", True, 0, 50, 10, 1), ("T2", False, 0, 60, 20, 1),
                                                   ("T3", True, 0, 700, 30, 2), ("TL", True, None, None, 40, 1),
                                                   ("TL", False, None, None, 40, 1), ("T2", True, None, None, 70, 2)]):
        qo, qd = (q_a, q_b) if eq == 1 else (q_b, q_a)
        filas.append({"game_id": 1, "periodo": 1, "t": float(t), "team_id": eq, "player_id": 1 if eq == 1 else 6,
                      "nombre": "x", "tipo": tipo, "anotado": anot, "puntos": {"T2": 2, "T3": 3, "TL": 1}[tipo] * anot,
                      "asistente_id": 2.0 if (anot and tipo != "TL") else np.nan, "x": x, "y": y,
                      "quinteto": qo, "quinteto_rival": qd})
    return pd.DataFrame(filas), q_a, q_b


def test_xp_suma_y_emparejamiento_con_tramos():
    """xp = p × valor; cada tiro cae en su tramo (incluido el que está justo en el cambio) y los puntos se reconstruyen."""
    from bbequipo.ecosistema import puntos_esperados as PE
    t, q_a, q_b = _tiros_sinteticos()
    t["zona"] = np.where(t["tipo"] == "TL", "tiro_libre", np.where(t["tipo"] == "T3", "t3_frontal", "aro"))
    t.loc[t["x"].isna() & (t["tipo"] != "TL"), "zona"] = "sin_zona"
    mod = PE.modelo_lt(t, CFG)
    a = PE.anotar_tiros(t, mod, CFG)
    valor = a["tipo"].map({"T2": 2, "T3": 3, "TL": 1})
    assert np.allclose(a["xp"], a["p_acierto"] * valor)
    assert np.allclose(a["residuo_tiro"], a["puntos"] - a["xp"])
    tr = pd.DataFrame({"game_id": [1, 1], "periodo": [1, 1], "t0": [0.0, 40.0], "t1": [40.0, 80.0], "team_a": ["1", "1"],
                       "team_b": ["2", "2"], "quinteto_a": [q_a, q_a], "quinteto_b": [q_b, q_b], "a_pts": [3, 0], "b_pts": [3, 2]})
    x = PE.tramos_xp(tr, a)
    assert x.attrs["tiros_emparejados"] == 1.0
    # los TL en t = 40 (justo en el cambio) pertenecen al tramo que termina en 40
    assert list(x["pts_tiros_a"]) == [3.0, 0.0] and list(x["pts_tiros_b"]) == [3.0, 2.0]
    assert np.isclose(x[["xp_a", "xp_b"]].to_numpy().sum(), a["xp"].sum())


def test_xp_contraccion_de_zona_y_tiro_libre():
    from bbequipo.ecosistema import puntos_esperados as PE
    rng = np.random.default_rng(0)
    n = 4000
    t = pd.DataFrame({"tipo": rng.choice(["T2", "T3", "TL"], n, p=[0.5, 0.3, 0.2]), "player_id": rng.integers(0, 50, n),
                      "asistente_id": np.nan})
    t["zona"] = np.where(t["tipo"] == "TL", "tiro_libre", np.where(t["tipo"] == "T3", "t3_frontal", "aro"))
    t.loc[t.index[:5], "zona"] = "media"                         # zona con 5 intentos: casi toda la tasa es la del tipo
    t["anotado"] = rng.random(n) < t["tipo"].map({"T2": 0.55, "T3": 0.35, "TL": 0.75})
    t["puntos"] = t["anotado"] * t["tipo"].map({"T2": 2, "T3": 3, "TL": 1})
    mod = PE.modelo_lt(t, CFG)
    p_t = mod["tipo"][t.loc[0, "tipo"]] if t.loc[0, "tipo"] != "TL" else None
    pm = mod["zona"].get((t.loc[0, "tipo"], "media"))
    if pm and p_t is not None:
        assert abs(pm["p"] - p_t) < 0.03
    a = PE.anotar_tiros(t, mod, CFG)
    tl = a[a["tipo"] == "TL"]
    assert tl["p_acierto"].between(0.6, 0.9).all()               # TL del tirador contraído hacia la liga
    assert abs(a["xp"].sum() / a["puntos"].sum() - 1) < 0.02


# =============================================================================================== efecto mínimo detectable
def test_potencia_wilson_y_emd():
    from bbequipo.ecosistema import potencia as PO
    p, lo, hi = PO.wilson(16, 20)
    assert p == 0.8 and lo < 0.8 < hi and 0.5 < lo and hi < 0.95
    assert PO.emd({0.1: 0.0, 0.5: 0.5, 1.0: 1.0}) == pytest.approx(0.8)          # interpolación lineal entre 0,5 y 1
    assert PO.emd({0.1: 0.1, 0.5: 0.3}) is None                                   # ningún δ llega al 80 %


def test_rasgos_de_trio_contienen_la_sinergia_cp_sembrada():
    """La sinergia CP (A·u_i)(A·u_j)(A·u_k) sumada sobre los 10 tríos de un quinteto es EXACTAMENTE lineal en los 20 rasgos
    de trío, con coeficientes λ·A_a·A_b·A_c: el modelo del examen puede representarla sin error."""
    from bbequipo.ecosistema import potencia as PO
    rng = np.random.default_rng(3)
    U5 = rng.normal(size=(50, 5, 4))
    A = rng.normal(size=(1, 4)); lam = np.array([1.7])
    phi = PO._phi_cp(U5, A, lam).sum(1)
    _, Ft, Ft3 = PO.rasgos_lado(U5)
    coef = np.array([lam[0] * A[0, a] * A[0, b] * A[0, c] for a, b, c in PO.SIM3])
    assert np.allclose(Ft @ coef, phi)
    assert np.allclose((Ft3 @ coef).sum(1), phi)


# =============================================================================================== F1 · motor de escenarios
class _MotorFicticio:
    """Imita lo que el motor de escenarios usa del simulador v3.3 (bbfit.simulador)."""
    def minutos_partido(self, liga):
        return 40.0

    def forzar_roles(self, M, fuerza, total, gm, liga, c, rng):
        cen = {"TITULAR": 28.0, "ROTACION": 18.0, "PROFUNDIDAD": 9.0, "RESIDUAL": 3.0, "GO_TO_GUY": 33.0}
        libres = np.array([i not in fuerza for i in range(M.shape[1])])
        for s in range(M.shape[0]):
            for i, r in fuerza.items():
                M[s, i] = cen[r] + rng.normal(0, 1.0)
            fijo = M[s, list(fuerza)].sum()
            M[s, libres] *= (total - fijo) / M[s, libres].sum()

    def redistribuir_uso(self, M, USG, usg_medio=20.0, amortiguar=1.0):
        from bbfit.simulador import redistribuir_uso
        return redistribuir_uso(M, USG, usg_medio, amortiguar)

    def _uso_natural(self, c, rr, liga):
        return rr["usg"], np.nan


class _EquipoFicticio:
    """Capa 4 ficticia con la interfaz de bbequipo.equipo.Equipo (para usar sus métodos fuerza y delta reales)."""
    def __init__(self, n_jug=30, semilla=0):
        from bbequipo import config as C40
        rng = np.random.default_rng(semilla)
        self.cfg = C40.cargar()
        self.S = _MotorFicticio()
        self.c = type("C", (), {"ref": {"uso": {}}, "cfg": {"rol_asignado": {}}})()
        self.cal = {"conjunto": {"prediccion": {"c": 0.4, "d": 0.3}, "intervalo": {"s0": 4.0, "q": 1.2}}, "por_grupo": {}}
        self.jug = [f"P{i:03d}" for i in range(n_jug)]
        self.b = dict(zip(self.jug, rng.normal(0, 3, n_jug)))
        self.zz = dict(zip(self.jug, rng.normal(0, 1, (n_jug, 3))))
        self.Mr = 0.05 * np.eye(3)
        self.us = dict(zip(self.jug, rng.uniform(12, 30, n_jug)))

    def valor(self, pid, liga):
        return float(self.b[pid]), 1.0, "beta"

    def z(self, pids):
        return np.array([self.zz[p] for p in pids])

    def h(self, pids):
        return np.array([0.1 * self.b[p] for p in pids])

    def plantilla_minutos(self, liga, team_id, miembros, n_sim, semilla):
        rng = np.random.default_rng(semilla)
        pids = [p for p, _ in miembros]
        u = np.array([self.b[p] for p in pids])
        W = np.exp(u / 3)[None, :] * rng.gamma(2.0, 1.0, (n_sim, len(pids)))
        M = 200.0 * W / W.sum(1, keepdims=True)
        from bbequipo.ecosistema.escenarios import ajustar_suma
        M = ajustar_suma(M, 200.0, 36.0)
        P = pd.DataFrame({"persona_id": pids, "_reg": [{"usg": self.us[p]} for p in pids]})
        return P, M / 40.0

    from bbequipo.equipo import Equipo as _E
    fuerza = _E.fuerza
    delta = _E.delta


@pytest.fixture(scope="module")
def ecosistema_ficticio():
    from bbequipo.ecosistema.escenarios import Ecosistema
    eq = _EquipoFicticio()
    E = Ecosistema(CFG, "2025-26", equipo=eq, progreso=None)
    E.cal_min = None
    plant = [(p, 1.0) for p in eq.jug[:14]]
    return E, eq, plant


def test_escenarios_paridad_exacta_con_la_capa4(ecosistema_ficticio):
    E, eq, plant = ecosistema_ficticio
    s = E.simular("acb", "1", plant, [("P020", None)], [], 2.0, n_sim=300, semilla=5, paridad_capa4=True)
    ref = eq.delta("acb", "1", plant, ["P020"], [], 2.0, n_sim=300, semilla=5)
    assert abs(s["equipo"]["delta_net"] - ref["delta_net"]) <= CFG["criterios"]["f1"]["paridad_capa4_pts100"]
    assert s["equipo"]["delta_net"] == pytest.approx(ref["delta_net"], abs=1e-12)


@pytest.mark.parametrize("altas,bajas", [([("P020", "TITULAR"), ("P021", None)], ["P000"]),
                                         ([("P020", "TITULAR"), ("P021", "ROTACION")], ["P000", "P001", "P002"])])
def test_escenarios_shapley_y_restricciones_fisicas(ecosistema_ficticio, altas, bajas):
    E, eq, plant = ecosistema_ficticio
    s = E.simular("acb", "1", plant, altas, bajas, 1.5, n_sim=200, semilla=9)
    c = s["control"]
    assert abs(c["identidad_contable"]) < 1e-9                         # Δ = Σ Shapley + diferencia de la base + regresión
    assert s["equipo"]["diferencia_mc_base"] == 0.0                     # números aleatorios comunes
    assert c["suma_minutos_max_desvio"] < 1e-9 and c["minutos_fuera_de_limites"] == 0 and c["uso_desvio_max"] < 1e-9
    assert c["shapley_exacto"] == (len(altas) + len(bajas) <= 4)
    J = s["jugadores"]
    assert set(J.loc[J["estado"] == "alta", "persona_id"]) == {a for a, _ in altas}
    tit = J.loc[J["persona_id"] == "P020", "min_media_despues"].iloc[0]
    assert 25 < tit < 31                                                # rol fijado TITULAR (centro 28')
    aj = s["atribucion_jugadores"]
    tot = aj.groupby("persona_id")["phi_min"].sum()                     # Shapley de minutos suma el cambio de minutos
    for p, dm in zip(J["persona_id"], J["d_min"]):
        if c["shapley_exacto"]:
            assert tot[p] == pytest.approx(dm, abs=1e-8)


def test_escenarios_deterministas(ecosistema_ficticio):
    E, eq, plant = ecosistema_ficticio
    a = E.simular("acb", "1", plant, [("P020", "TITULAR")], ["P000"], 0.0, n_sim=100, semilla=3)
    b = E.simular("acb", "1", plant, [("P020", "TITULAR")], ["P000"], 0.0, n_sim=100, semilla=3)
    assert a["equipo"] == b["equipo"]
    pd.testing.assert_frame_equal(a["jugadores"], b["jugadores"])


def test_ajustar_suma_y_pares_en_pista():
    from bbequipo.ecosistema.escenarios import ajustar_suma, pares_en_pista
    rng = np.random.default_rng(1)
    M = rng.uniform(0, 45, (50, 12))
    A = ajustar_suma(M, 200.0, 40.0)
    assert np.allclose(A.sum(1), 200.0) and A.min() >= 0 and A.max() <= 40.0 + 1e-12
    assert np.array_equal(ajustar_suma(A, 200.0, 40.0), A)             # ya válida: no cambia (paridad)
    P = pares_en_pista(A / 40.0)
    assert np.isclose(np.triu(P, 1).sum(), 10.0)                       # 10 parejas en pista


# =============================================================================================== F2 · Impacto en pista
def test_pi_suma_diez_parejas_y_valor_en_pista():
    from bbequipo.ecosistema import impacto_pista as IP
    rng = np.random.default_rng(3)
    Pm = rng.dirichlet(np.ones(9), 50) * 5
    PI = IP.pi_matriz(Pm)
    assert np.allclose(np.einsum("si,sij->s", Pm, PI), 20.0)            # Σ_j p_j Σ_k π_jk = 2 · Σ_{j<k} P_jk = 20
    assert np.allclose(PI[:, np.arange(9), np.arange(9)], 0.0)

    class Ins:
        Mr = np.diag([0.5, -0.2]); P4 = np.eye(2)
        def valor(self, p, l): return (1.0 if p == "a" else 0.0), 0.0, "beta"
        def z(self, ps): return np.array([[1.0, 0.0] if p in ("a", "b") else [0.0, 0.0] for p in ps])
        def h(self, ps): return np.zeros(len(ps))
    pids = ["a", "b"] + [f"x{i}" for i in range(7)]
    r = IP.valor_en_pista(Ins(), "acb", pids, Pm, rng)
    # la sinergia de «a» es π_ab·φ_ab con φ_ab = z_aᵀ M z_b = 0,5; la de los demás (z = 0) es 0
    assert np.allclose(r["syn"][0], 0.5 * PI[:, 0, 1].mean()) and np.allclose(r["syn"][2:], 0.0)
    assert np.allclose(r["v"].mean(0)[2:], 0.0)


def test_familiaridad_pares_y_matriz():
    from bbequipo.ecosistema import impacto_pista as IP
    tr = pd.DataFrame({"A": [("a|t", "b|t", "c|t", "d|t", "e|t")], "B": [("f|t", "g|t", "h|t", "i|t", "j|t")], "poss": [100.0]})
    pares = IP.pares_temporada(pd.concat([tr, tr.assign(poss=50.0)], ignore_index=True))
    assert pares[("a", "b")] == 150.0 and ("a", "f") not in pares and len(pares) == 20
    G = IP.familiaridad_matriz(pares, ["b", "a", "z"])
    assert G[0, 1] == G[1, 0] == pytest.approx(np.log1p(1.5)) and G[0, 2] == 0.0


def test_familiaridad_fwl_desplazamiento_exacto():
    """Sembrar δ·x en el resultado desplaza δ̂ exactamente en δ (estimador lineal): base del EMD analítico."""
    from bbequipo.ecosistema import familiaridad as FA
    tr = liga_sintetica(partidos=120, semilla=4)
    lt = OS.preparar(tr, 1)
    lt.y_xp = lt.y.copy()
    rng = np.random.default_rng(2)
    x = rng.normal(0, 1, lt.n)
    cfg = _cfg_rapido()
    r0 = FA.delta_lt(lt, x, cfg)
    lt2 = lt.con_y(lt.y + 0.7 * x)
    lt2.y_xp = lt2.y.copy()
    r1 = FA.delta_lt(lt2, x, cfg)
    if r1["lambda"] == r0["lambda"]:
        assert r1["delta"] - r0["delta"] == pytest.approx(0.7, abs=1e-8)
    ag = FA.agregar(pd.DataFrame({"delta": [1.0, 3.0], "ee": [1.0, 1.0], "liga": ["a", "b"], "temporada": ["s", "s"]}))
    assert ag["delta"] == pytest.approx(2.0) and ag["ee"] == pytest.approx(1 / np.sqrt(2))


def test_pct_esperado_y_calibracion_sin_fuga():
    from bbequipo.ecosistema import examen_impacto as EX
    ref = np.arange(100.0)
    assert EX.pct_esperado(np.array([49.5]), np.array([0.0]), ref)[0] == pytest.approx(50.0, abs=0.6)
    p = EX.pct_esperado(np.array([0.0, 50.0, 99.0]), np.array([5.0, 5.0, 5.0]), ref)
    assert np.all(np.diff(p) > 0)
    rng = np.random.default_rng(0)
    n = 1500
    e = pd.DataFrame({"anio": np.repeat([2021, 2022, 2023], n), "c": rng.uniform(0, 100, 3 * n), "onoff_ok": True})
    e["pct_onoff"] = np.clip(e["c"] + rng.normal(0, 20, 3 * n), 0, 100)
    a = EX.calibrar(e.copy(), "c", [2021, 2022, 2023], "X")
    e2 = e.copy()
    e2.loc[e2["anio"] == 2023, "pct_onoff"] = 0.0                     # el realizado del propio corte no entra en su calibración
    b = EX.calibrar(e2, "c", [2021, 2022, 2023], "X")
    s = e["anio"] == 2023
    assert np.allclose(a.loc[s, "X"], b.loc[s, "X"]) and (a.loc[s, "X_lo80"] <= a.loc[s, "X"]).all()


def test_bootstrap_por_equipos_y_spearman():
    from bbequipo.ecosistema import examen_impacto as EX
    rng = np.random.default_rng(1)
    d = pd.DataFrame({"anio": 2022, "liga_d": "acb", "team_d": rng.integers(0, 40, 800).astype(str), "x": rng.normal(size=800)})
    d["y"] = d["x"] + rng.normal(size=800)
    assert len(EX.clusters(d)) == d["team_d"].nunique()
    bs = EX.bootstrap(d, lambda z: np.array([EX.spearman(z["x"], z["y"])]), 200, 0)
    lo, hi = EX._ic(bs[:, 0])
    assert lo < EX.spearman(d["x"], d["y"]) < hi and lo > 0.5


def test_xp_onoff_identidad():
    from bbequipo.ecosistema import puntos_esperados as PE
    tr = pd.DataFrame({"team_a": ["1", "1"], "team_b": ["2", "2"], "quinteto_a": ["a|b|c|d|e", "a|b|c|d|f"],
                       "quinteto_b": ["g|h|i|j|k"] * 2, "poss": [10.0, 30.0], "xp_a": [12.0, 30.0], "xp_b": [10.0, 33.0],
                       "a_pts": [14, 27], "b_pts": [9, 36]})
    O = PE.en_pista(tr)
    e = O.loc[("1", "e")]
    # e: en pista sólo el tramo 1 (net +50), fuera el tramo 2 (net −30) → on/off = +80; con xp: +20 − (−10) = +30
    assert PE.CAMPOS[("jugador", "net_onoff")](e) == pytest.approx(80.0)
    assert PE.CAMPOS[("jugador", "xnet_onoff")](e) == pytest.approx(30.0)
    assert np.isnan(PE.CAMPOS[("jugador", "net_off")](O.loc[("1", "a")]))   # siempre en pista: sin «off»


def test_escala_producto_monotona():
    from bbequipo.ecosistema import impacto_pista as IP
    ref = {"F_grupo": {"domestica_alta": {"n": 100, "cuantiles": {f"{q:.2f}": float(q * 10 - 5) for q in np.linspace(0, 1, 21)}}},
           "isotonica": {"x": [0.0, 100.0], "y": [10.0, 90.0]},
           "rango_deciles": {"bordes": list(np.linspace(0, 100, 11)), "q10": [0.0] * 10, "q90": [100.0] * 10}, "sello": "EXPERIMENTAL"}
    V = np.random.default_rng(0).normal(0, 0.3, (200, 3)) + np.array([-3.0, 0.0, 3.0])
    out = IP.escala_producto(ref, "acb", CE.cargar_v40(CFG), V)
    assert np.all(np.diff(out["impacto_pista"]) > 0) and (out["impacto_pista_sello"] == "EXPERIMENTAL").all()
