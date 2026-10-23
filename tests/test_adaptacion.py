"""Tests sintéticos de la fase 7 (bbfit/adaptacion.py): interfaz del simulador y piezas del modelo."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from bbfit import adaptacion as A


# ------------------------------------------------------------------------------------------- interfaz
def test_curva_forma_y_limites():
    assert A.curva(0, -0.1, 5) == pytest.approx(0.9)
    assert A.curva(1e6, -0.1, 5) == pytest.approx(1.0)
    k = 6.0
    # al 50 % del hueco en κ·ln2 partidos, al 90 % en κ·ln10
    assert A.curva(k * math.log(2), -0.2, k) == pytest.approx(1 - 0.1)
    assert A.curva(k * math.log(10), -0.2, k) == pytest.approx(1 - 0.02)
    g = np.arange(0, 30)
    f = A.curva(g, -0.15, 4.0)
    assert f.shape == g.shape and np.all(np.diff(f) > 0)          # penalización que se cierra de forma monótona
    assert A.curva(3, 0.0, 4.0) == pytest.approx(1.0)
    assert A.partidos_hasta(0.5, k) == pytest.approx(k * math.log(2))
    assert A.partidos_hasta(0.9, k) == pytest.approx(k * math.log(10))
    assert A.curva(2, -0.1, 0) == pytest.approx(1.0)                # κ = 0: adaptación instantánea


def test_grupo_nacionalidad():
    g = A.grupo_nacionalidad
    assert g("US", "nba", "acb") == "EEUU_a_Europa"
    assert g("Estados Unidos", "gleague", "lba") == "EEUU_a_Europa"
    assert g("FR", "nba", "lnb") == "otro_desde_EEUU"
    assert g(None, "nba", "lnb") == "desconocido"
    assert g(float("nan"), "acb", "lba") == "desconocido"
    assert g(None, "acb", "nba") == "hacia_EEUU"
    assert g("ES", "nba", "gleague") == "intra_EEUU"
    assert g("ES", "feb1", "acb") == "nacional_mismo_pais"
    assert g("España", "feb3", "feb2") == "nacional_mismo_pais"
    assert g("US", "feb1", "acb") == "extranjero_mismo_pais"
    assert g("RS", "acb", "lba") == "europeo_cambia_liga"
    assert g("ES", "acb", "euroleague") == "europeo_cambia_liga"      # copa europea: sin país
    assert g("US", "acb", "lba") == "extranjero_cambia_pais"
    assert g("Alemania / Estados Unidos", "lnb", "bbl") == "europeo_cambia_liga"
    assert g("Alemania / Estados Unidos", "nba", "bbl") == "EEUU_a_Europa"


def _tabla_sintetica():
    filas = []
    base = dict(delta_lo=-0.2, delta_hi=0.1, kappa_lo=1, kappa_hi=10, escalon_destino="*")
    for met in ("L", "pts_p100"):
        filas += [
            dict(nivel="global", liga_origen="*", liga_destino="*", grupo_nacionalidad="*", pos3="*", metrica=met,
                 n=500, delta_media=-0.01, delta_sd=0.05, kappa_media=4.0, kappa_sd=1.0, **base),
            dict(nivel="global_grupo", liga_origen="*", liga_destino="*", grupo_nacionalidad="EEUU_a_Europa",
                 pos3="*", metrica=met, n=100, delta_media=-0.05, delta_sd=0.04, kappa_media=7.0, kappa_sd=2.0, **base),
            {**dict(nivel="escalon", liga_origen="*", liga_destino="*", grupo_nacionalidad="*", pos3="*",
                    metrica=met, n=200, delta_media=-0.02, delta_sd=0.03, kappa_media=4.5, kappa_sd=1.0, **base),
             "escalon_destino": "domestica_alta"},
            dict(nivel="par", liga_origen="feb1", liga_destino="acb", grupo_nacionalidad="*", pos3="*", metrica=met,
                 n=40, delta_media=-0.06, delta_sd=0.03, kappa_media=5.0, kappa_sd=1.5, **base),
            dict(nivel="celda", liga_origen="feb1", liga_destino="acb", grupo_nacionalidad="nacional_mismo_pais",
                 pos3="E", metrica=met, n=12, delta_media=-0.07, delta_sd=0.04, kappa_media=5.5, kappa_sd=1.5, **base),
            dict(nivel="celda", liga_origen="feb1", liga_destino="acb", grupo_nacionalidad="nacional_mismo_pais",
                 pos3="I", metrica=met, n=3, delta_media=-0.30, delta_sd=0.20, kappa_media=9.0, kappa_sd=3.0, **base),
        ]
    return pd.DataFrame(filas)


def test_prior_jerarquia_de_reserva(tmp_path):
    ruta = tmp_path / "adaptation_priors.csv"
    _tabla_sintetica().to_csv(ruta, index=False)
    claves = {"delta_media", "delta_sd", "kappa_media", "kappa_sd", "n", "nivel_fallback"}
    r = A.prior("feb1", "acb", "nacional_mismo_pais", "E", ruta=ruta)
    assert set(r) == claves and r["nivel_fallback"] == "celda" and r["delta_media"] == pytest.approx(-0.07)
    r = A.prior("feb1", "acb", "nacional_mismo_pais", "I", ruta=ruta)          # celda con n < n_min → par
    assert r["nivel_fallback"] == "par" and r["n"] == 40
    r = A.prior("lba", "acb", "europeo_cambia_liga", "A", ruta=ruta)           # sin par → escalón de destino
    assert r["nivel_fallback"] == "escalon" and r["delta_media"] == pytest.approx(-0.02)
    r = A.prior("lba", "euroleague", "EEUU_a_Europa", "A", metrica="pts_p100", ruta=ruta)
    assert r["nivel_fallback"] == "global_grupo" and r["kappa_media"] == pytest.approx(7.0)
    r = A.prior("lba", "euroleague", "europeo_cambia_liga", "A", ruta=ruta)
    assert r["nivel_fallback"] == "global"
    with pytest.raises(ValueError):
        A.prior("feb1", "acb", "nacional_mismo_pais", "E", metrica="xyz", ruta=ruta)


def test_prior_sin_tabla_devuelve_defecto(tmp_path):
    r = A.prior("feb1", "acb", "nacional_mismo_pais", "E", ruta=tmp_path / "no_existe.csv")
    assert r["nivel_fallback"] == "sin_datos" and r["delta_media"] == 0.0 and r["n"] == 0
    assert r["delta_sd"] > 0 and r["kappa_media"] > 0


# ------------------------------------------------------------------------------------------- piezas del modelo
def test_gibbs_recupera_efectos_y_contrae_parejas():
    rng = np.random.default_rng(0)
    n, J = 3000, 30
    X = np.column_stack([np.ones(n), rng.integers(0, 2, n).astype(float), rng.standard_normal(n)])
    beta = np.array([0.02, -0.06, 0.03])
    g1 = rng.integers(0, J, n)
    g2 = g1 % 3
    u = rng.standard_normal(J) * 0.04
    v = np.array([0.0, 0.03, -0.03])
    w = rng.uniform(0.3, 1.0, n)
    y = X @ beta + u[g1] + v[g2] + rng.standard_normal(n) * 0.15 / np.sqrt(w)
    r = A.gibbs_jerarquico(y, X, w / w.mean(), g1, g2, J, 3, iteraciones=1500, calentamiento=500, semilla=1)
    b = r["beta"].mean(0)
    assert abs(b[1] - beta[1]) < 0.02 and abs(b[2] - beta[2]) < 0.01
    assert 0.01 < np.sqrt(r["tau2_u"]).mean() < 0.08
    assert np.corrcoef(r["u"].mean(0), u)[0, 1] > 0.5


def test_curva_recupera_kappa_y_hueco():
    rng = np.random.default_rng(2)
    filas = []
    for i in range(400):
        A_i = rng.uniform(15, 25)
        for g in range(1, 31):
            pos = rng.uniform(30, 60)
            y = A_i * (1 - 0.15 * np.exp(-g / 4.0)) + rng.standard_normal() * 8 / np.sqrt(pos / 45)
            filas.append({"id": str(i), "g": g, "y_pts_p100": y, "w_pts_p100": pos})
    ser = pd.DataFrame(filas)
    K = np.geomspace(0.5, 80, 49)
    ids, Sxx, Sxy, Syy = A.estadisticos_curva(ser, "pts_p100", K)
    r = A.ajustar_kappa(Sxx, Sxy, Syy, K, previa={"previa_kappa": 5, "previa_log_kappa_sd": 1.0, "previa_D_sd": 0.15})
    assert 2.0 < r["kappa"] < 8.0
    assert -0.22 < r["D"] < -0.09
    # sin transitorio: D ≈ 0
    ser2 = ser.copy()
    ser2["y_pts_p100"] = 20 + rng.standard_normal(len(ser2)) * 8 / np.sqrt(ser2["w_pts_p100"] / 45)
    ids, Sxx, Sxy, Syy = A.estadisticos_curva(ser2, "pts_p100", K)
    r2 = A.ajustar_kappa(Sxx, Sxy, Syy, K, previa={"previa_kappa": 5, "previa_log_kappa_sd": 1.0, "previa_D_sd": 0.15})
    assert abs(r2["D"]) < 0.03


def test_proyeccion_a_la_interfaz():
    K = np.geomspace(0.5, 500, 73)
    # transitorio puro, sin desfase de temporada → recupera κ y un δ negativo
    dl, kp = A.proyectar_interfaz(np.array([0.0]), np.array([-0.2]), np.array([5.0]), 30, 60, K)
    assert dl[0] < -0.05 and 2 < kp[0] < 12
    # sin transitorio: efecto persistente → δ ≈ Δ_temporada y κ en el extremo alto
    dl, kp = A.proyectar_interfaz(np.array([-0.05]), np.array([0.0]), np.array([5.0]), 30, 60, K)
    assert dl[0] == pytest.approx(-0.05, abs=0.01) and kp[0] >= 40
    # aditiva (L)
    dl, kp = A.proyectar_interfaz(np.array([0.1]), np.array([0.0]), np.array([5.0]), 30, 60, K, aditiva=True)
    assert dl[0] == pytest.approx(0.1, abs=0.02)


def test_ipcw_corrige_la_seleccion():
    """Los que rinden mal en los primeros partidos dejan de jugar (censura): la media de los observados sobreestima la
    adaptación; con IPCW (usando el rendimiento temprano) se acerca a la de todas las llegadas."""
    rng = np.random.default_rng(5)
    n = 4000
    verdad = rng.normal(-0.05, 0.15, n)
    temprano = verdad + rng.normal(0, 0.1, n)
    p = 1 / (1 + np.exp(-(0.3 + 6 * temprano)))
    obs = rng.uniform(size=n) < p
    m = pd.DataFrame({"grupo_nacionalidad": "europeo_cambia_liga", "pos3": "E", "arquetipo": "circulacion",
                      "edad": 26.0, "rol_origen_num": 2.0, "cambio_rol": 0.0, "salto_nivel": 0.0, "salto_nivel_abs": 0.0,
                      "distancia_estilo_equipo": 0.6, "cambio_entrenador": 1.0, "edad_desconocida": False,
                      "rol_desconocido": False, "estilo_desconocido": False, "entrenador_desconocido": False,
                      "intra_temporada": 0.0, "adicion": 0.0, "regreso": False, "min_origen": 800.0, "L_origen": 0.0,
                      "temprano_logr": temprano, "escalon_destino": "domestica_alta"})
    w, info = A.pesos_ipcw(m, obs)
    ingenua = verdad[obs].mean()
    corregida = np.average(verdad[obs], weights=w[obs])
    assert ingenua > verdad.mean() + 0.02
    assert abs(corregida - verdad.mean()) < abs(ingenua - verdad.mean()) / 2
    assert info["coef_temprano_logr"] > 0


def test_identificar_traspasos_sintetico():
    fechas = pd.to_datetime
    tem = pd.DataFrame([
        # persona 1: feb1 2023 → acb 2024 (salida)
        dict(persona_id="1", liga="feb1", temporada="2023-24", anio=2023, player_id="a", nombre="Uno", min=900.0, gp=30),
        dict(persona_id="1", liga="acb", temporada="2024-25", anio=2024, player_id="b", nombre="Uno", min=600.0, gp=30),
        # persona 2: acb 2023 → acb + euroleague 2024 (adición)
        dict(persona_id="2", liga="acb", temporada="2023-24", anio=2023, player_id="c", nombre="Dos", min=900.0, gp=34),
        dict(persona_id="2", liga="acb", temporada="2024-25", anio=2024, player_id="c", nombre="Dos", min=800.0, gp=34),
        dict(persona_id="2", liga="euroleague", temporada="2024-25", anio=2024, player_id="d", nombre="Dos", min=400.0, gp=30),
        # persona 3: dentro de la temporada, lba (hasta enero) → bbl (desde febrero)
        dict(persona_id="3", liga="lba", temporada="2024-25", anio=2024, player_id="e", nombre="Tres", min=400.0, gp=15),
        dict(persona_id="3", liga="bbl", temporada="2024-25", anio=2024, player_id="f", nombre="Tres", min=350.0, gp=14),
        # persona 4: euroleague + acb a la vez (concurrentes): no es traspaso
        dict(persona_id="4", liga="acb", temporada="2024-25", anio=2024, player_id="g", nombre="Cuatro", min=700.0, gp=30),
        dict(persona_id="4", liga="euroleague", temporada="2024-25", anio=2024, player_id="h", nombre="Cuatro", min=500.0, gp=30),
    ])
    et = pd.DataFrame([
        dict(liga="feb1", temporada="2023-24", player_id="a", fecha_ini=fechas("2023-10-01"), fecha_fin=fechas("2024-05-01")),
        dict(liga="acb", temporada="2024-25", player_id="b", fecha_ini=fechas("2024-10-01"), fecha_fin=fechas("2025-05-01")),
        dict(liga="acb", temporada="2023-24", player_id="c", fecha_ini=fechas("2023-10-01"), fecha_fin=fechas("2024-05-01")),
        dict(liga="acb", temporada="2024-25", player_id="c", fecha_ini=fechas("2024-10-01"), fecha_fin=fechas("2025-05-01")),
        dict(liga="euroleague", temporada="2024-25", player_id="d", fecha_ini=fechas("2024-10-03"), fecha_fin=fechas("2025-04-01")),
        dict(liga="lba", temporada="2024-25", player_id="e", fecha_ini=fechas("2024-10-01"), fecha_fin=fechas("2025-01-20")),
        dict(liga="bbl", temporada="2024-25", player_id="f", fecha_ini=fechas("2025-02-01"), fecha_fin=fechas("2025-05-01")),
        dict(liga="acb", temporada="2024-25", player_id="g", fecha_ini=fechas("2024-10-01"), fecha_fin=fechas("2025-05-01")),
        dict(liga="euroleague", temporada="2024-25", player_id="h", fecha_ini=fechas("2024-10-02"), fecha_fin=fechas("2025-04-01")),
    ])
    m = A.identificar_traspasos(tem, et)
    k = {(r.persona_id, r.liga_origen, r.liga_destino, r.tipo) for r in m.itertuples()}
    assert ("1", "feb1", "acb", "salida") in k
    assert ("2", "acb", "euroleague", "adicion") in k
    assert ("3", "lba", "bbl", "intra_temporada") in k
    assert not any(p == "4" for p, *_ in k)
    assert len(m) == 3


def test_esperado_en_destino_inverso_exacto():
    """θ de un jugador observado en la liga de destino → esperado en esa misma liga-temporada = su valor observado."""
    from bbmodel.metricas import transformar
    norm = {"params": {"metricas": {"pts_p100": {
        "suerte": {"mu": {"acb|2024-25|E": 4.6}, "tau2": {"acb|E": 0.25}},
        "enlace": {"s": {"acb": 0.9}, "deriva": {"24-26": 0.03, "s/d": 0.0}, "eta2": 0.0}}}},
        "offsets": pd.DataFrame([{"competicion": "acb", "temporada": "2024-25", "metrica": "pts_p100", "media": -0.2,
                                  "sd": 0.05, "lambda": 1.0, "forma_no_lineal": 0}]).set_index(["competicion", "temporada", "metrica"])}
    y = 22.0
    z = (float(transformar(y, "raiz")) - 4.6) / 0.5
    th = -0.2 + 0.9 * z
    yh, lo, hi, _ = A.esperado_en_destino(th, 0.1, "acb", "2024-25", "E", "pts_p100", norm, anios=0, edad=25)
    assert yh == pytest.approx(y, rel=1e-9) and lo < yh < hi
    assert A.theta_observado(y, "acb", "2024-25", "E", "pts_p100", norm) == pytest.approx(th)
    # un año después con deriva por edad positiva: espera algo más
    yh1 = A.esperado_en_destino(th, 0.1, "acb", "2024-25", "E", "pts_p100", norm, anios=1, edad=25)[0]
    assert yh1 > yh
    # sin nivel de la competición de destino → NaN (no se inventa)
    assert np.isnan(A.esperado_en_destino(th, 0.1, "lba", "2024-25", "E", "pts_p100", norm, anios=0, edad=25)[0])
