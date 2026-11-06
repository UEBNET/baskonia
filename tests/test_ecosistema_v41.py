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
