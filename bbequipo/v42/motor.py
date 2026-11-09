"""D2 · motor v4.2 (configs/v42.yaml → motor_v42): el motor de minutos y producción v3.3 con la capacidad θ de cada
jugador sustituida por su NIVEL CON HISTORIAL (filtro de Kalman sobre sus temporadas ≤ s, el modelo de la D1:
bbequipo/v42/historial.py) en la escala θ (DT de la vara EuroLeague) de cada métrica.

Modelo (por métrica, sin RAPM, que va en D2-β):
    observación de la temporada s:  y = θ_s (media ponderada por precisión de sus ligas),  var = c·v,  v = sd(θ_s)²
    estado:  θ_s = θ_{s−1} + η,  η ~ N(0, τ²) por año;  previa de la primera temporada N(μ_pos, σ²_pos)
    τ², c por máxima verosimilitud de las innovaciones un paso adelante (historial.ajustar) con datos ≤ t.

Examen (el mismo que decidió la v3.3: fuente V32_corte, fichajes reales 2021-22 → 2024-25, cortes anidados):
  * brazo «v3.3»: los registros de la temporada t del corte V32_corte (θ de la normalización v3.2 ajustada con ≤ t);
  * brazo «v4.2»: los MISMOS registros con θ, sd, valor en la vara y varianza propia de las métricas filtradas
    sustituidos por el nivel filtrado en t (historia = temporadas ≤ t traducidas con los modelos ≤ t del corte: la CVAE
    de las 20 redes ≤ t y el A amortiguado ≤ t; nada de t+1). L y L_sd se recalculan con esos valores.
  Todo lo demás es idéntico en los dos brazos: pesos de la utilidad, calibración, Fit y capa de calibración de salida
  por corte (los de la ejecución V32_inicio_adapt, como el examen original), matriz de transición, plantillas, semillas,
  iteraciones Monte Carlo, decisiones anidadas de la v3.2 (pasos, k, producción) y de la v3.3 (centro de minutos).
  Recalibración del 80 % (prerregistro): conformal con el corte de calibración (2021-22) sólo; nunca con los de decisión.

    python -m bbequipo.v42.motor theta      → historia θ ≤ t por corte (experimentos/cache_simulador_v4_2/examen)
    python -m bbequipo.v42.motor brazos     → cachés de los dos brazos (corte V32_corte original / filtrado)
    python -m bbequipo.v42.motor backtest   → ejecuciones de los dos brazos (data/modelos/v4_2/motor/validacion/<brazo>)
    python -m bbequipo.v42.motor examen     → data/modelos/v4_2/motor/examen_d2_motor.json
    python -m bbequipo.v42.motor dataset    → dataset del simulador v4.2 (experimentos/cache_simulador_v4_2/normalizado)
    python -m bbequipo.v42.motor todo       → todo lo anterior, reanudable (≈ 1 h; las cachés se reutilizan)
"""
from __future__ import annotations

import json
import os
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

os.environ["CERNO_SIMULADOR"] = "v42"      # antes de importar bbfit: su configuración se lee (y se guarda) al importarlo

RAIZ = Path(__file__).resolve().parents[2]
CFG42 = yaml.safe_load((RAIZ / "configs" / "v42.yaml").read_text(encoding="utf-8"))
Z80 = float(CFG42["z80"])
CACHE32 = RAIZ / "experimentos" / "cache_simulador_v3_2"          # sólo lectura
CACHE42 = RAIZ / "experimentos" / "cache_simulador_v4_2"
DIR_EX = CACHE42 / "examen"
SALIDA = RAIZ / "data" / "modelos" / "v4_2" / "motor"
DIR_VAL32 = RAIZ / "data" / "modelos" / "simulador" / "v3_2" / "validacion"   # sólo lectura
DEC33 = RAIZ / "data" / "modelos" / "simulador" / "v3_3" / "decisiones_v33.json"   # sólo lectura
CORTES = ["2021-22", "2022-23", "2023-24", "2024-25"]
CAL = "2021-22"
DECISION = ["2022-23", "2023-24", "2024-25"]
PESOS_DE = "V32_inicio_adapt"          # pesos por corte del examen original de V32_corte (resumen.json → pesos_de)
SIN_FILTRO = ("rapm", "orapm", "drapm")


def _env():
    """Simulador v4.2 (configs/simulation_v42.yaml) en ESTADO DE EXAMEN, en memoria (no se toca ningún yaml):
    motor completo, k = (1, 1), producción del motor, sin A4 ni bloque v33 (sus decisiones finales usan todos los
    cortes: serían fuga). Mismo estado en que corrió el examen V32_corte de la v3.2/v3.3 (v32.config_examen)."""
    from bbfit.config import cargar
    c = cargar("simulation")
    assert c.get("version") == "v4.2", "bbfit se importó antes que bbequipo.v42.motor sin CERNO_SIMULADOR=v42"
    for p in list(c["pasos"]):
        c["pasos"][p] = True
    c["produccion"]["factor_ajustes_ts"] = [1.0, 1.0]
    c["v32"]["produccion_publicada"] = "motor"
    c["v32"]["aplicar_recalibracion"] = False
    c["v33"] = None
    c["normalizacion"]["dir"] = "experimentos/cache_simulador_v3_2/normalizado"   # columnas de línea base (idénticas)
    return c


# ------------------------------------------------------------------------------------------------ historia θ ≤ t
def _metricas(cfg) -> list[str]:
    from bbfit import sim_insumos as SI
    return [m for m in SI.metricas_traduccion(cfg) if m not in SIN_FILTRO]


def _tabla():
    f = DIR_EX / "tabla_normalizacion.pkl"
    if f.exists():
        return pickle.loads(f.read_bytes())
    from bbmodel import modelo as A
    t = A.preparar()[0]
    DIR_EX.mkdir(parents=True, exist_ok=True)
    f.write_bytes(pickle.dumps(t))
    return t


def theta_historia(anio_corte: int, progreso=print) -> pd.DataFrame:
    """θ (DT, vara EuroLeague de la temporada t) de las filas de las temporadas < t con los modelos del corte ≤ t: la
    misma mezcla CVAE ≤ t + A amortiguado ≤ t que bbfit.sim_insumos.normalizacion_hasta_v32 hace para las filas de t.
    Sin fuga: ningún modelo ve t+1. Caché: experimentos/cache_simulador_v4_2/examen/theta_hist_<año>.pkl."""
    dest = DIR_EX / f"theta_hist_{anio_corte}.pkl"
    if dest.exists():
        return pickle.loads(dest.read_bytes())
    from bbfit import sim_insumos as SI
    from bbmodel.metricas import CATALOGO, destransformar, transformar
    from bbnorm3 import combinacion as CB, config as C3, exportar, flujo
    t0 = time.time()
    cfg = _env()
    mets = _metricas(cfg)
    temp = SI.temp_de(anio_corte)
    nh = pickle.loads((CACHE32 / f"norm_hasta_{anio_corte}.pkl").read_bytes())       # A amortiguado ≤ t (caché v3.2)
    th2, const2 = nh["theta"], nh["traduccion"]["constantes"]
    th2 = th2[th2["temporada"] < temp].drop_duplicates(["liga", "temporada", "player_id"])
    cfg3 = C3.cargar(RAIZ / cfg["normalizacion"].get("config_normalizacion", "configs/normalization_v32.yaml"))
    cfg3 = C3.con(cfg3, **{"referencia_salida.temporada": temp})
    # redes CVAE ≤ t del examen de la v3.2 (experimentos/v3, sólo lectura): enlaces en una carpeta propia para que la
    # caché de traducciones de estas filas nuevas no se escriba junto a las de la v3.2
    dcv = DIR_EX / "cvae"
    dcv.mkdir(parents=True, exist_ok=True)
    for f in (RAIZ / "experimentos" / "v3").glob(f"h{anio_corte}_*.pt"):
        if not (dcv / f.name).exists():
            (dcv / f.name).symlink_to(f)
    flujo.DIR_CACHE = dcv
    tabla = _tabla()
    D, cj = flujo.conjunto(tabla, cfg3, anio_corte, progreso=progreso)
    filas = tabla[(tabla["anio"] <= anio_corte) & (tabla["temporada"] < temp)]
    tr = exportar.traducir_filas(filas, D, cj, cfg3).drop_duplicates(["liga", "temporada", "player_id"])
    x = th2.merge(tr, on=["liga", "temporada", "player_id"], how="inner", suffixes=("", "_cvae"))
    extra = [c for c in ("min", "persona_id") if c not in x]
    if extra:
        x = x.merge(filas[["liga", "temporada", "player_id"] + extra].drop_duplicates(["liga", "temporada", "player_id"]),
                    on=["liga", "temporada", "player_id"], how="left")
    ex = RAIZ / cfg3["salida"] / "validacion" / "examen_v32.json"
    exj = json.loads(ex.read_text(encoding="utf-8")) if ex.exists() else {}
    w_met = (exj.get("pesos_por_corte") or {}).get(str(anio_corte)) or {}
    w_con = (exj.get("combinada_b2_con_conocimiento_feb3") or {}).get("peso_v3_conocimiento_elegido")
    cb = cfg3["combinacion"]
    temporadas = CB.temporadas_por_liga(tabla, cfg3, anio_corte)
    th = x[["liga", "temporada", "player_id", "persona_id", "pos3", "min"]].copy()
    for m in mets:
        if m not in const2 or f"{m}_th" not in x or f"{m}_v3" not in x:
            continue
        k, trf = const2[m], CATALOGO[m].transf
        mu = np.array([SI.entorno(k, "euroleague", temp, p)[0] if isinstance(p, str) else np.nan for p in x["pos3"]])
        tau = np.array([SI.entorno(k, "euroleague", temp, p)[1] if isinstance(p, str) else np.nan for p in x["pos3"]])
        m2 = mu + tau * x[f"{m}_th"].to_numpy(float)
        s2 = np.maximum(tau * x[f"{m}_thsd"].to_numpy(float), 1e-6)
        m3 = transformar(x[f"{m}_v3"].to_numpy(float), trf)
        s3 = np.maximum((transformar(x[f"{m}_v3_hi"].to_numpy(float), trf)
                         - transformar(x[f"{m}_v3_lo"].to_numpy(float), trf)) / (2 * Z80), 1e-6)
        w = np.full(len(x), float(w_met.get(m, cb["peso_v3"])))
        if w_con is not None:
            w[x["liga"].isin(cb["ligas_conocimiento"]).to_numpy()] = float(w_con)
        w[(x["liga"].map(temporadas).fillna(0) < cb["min_temporadas_liga"]).to_numpy()] = 0.0
        w[x[f"{m}_v3_sd_entre_z"].to_numpy(float) > cb["max_discrepancia_redes"]] = 0.0
        w[~np.isfinite(m3) | ~np.isfinite(s3)] = 0.0
        m3, s3 = np.where(np.isfinite(m3), m3, m2), np.where(np.isfinite(s3), s3, s2)
        media = w * m3 + (1 - w) * m2
        lo, hi = CB._cuantiles_mezcla(w, m3, s3, m2, s2, (0.1, 0.9))
        th[f"{m}_am"] = destransformar(media, trf)
        th[f"{m}_th"] = (media - mu) / tau
        th[f"{m}_thsd"] = (hi - lo) / (2 * Z80 * tau)
    DIR_EX.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(pickle.dumps(th))
    if progreso:
        progreso(f"  historia θ ≤ {anio_corte} (temporadas < {temp}, vara EuroLeague {temp}): {len(th)} filas, "
                 f"{time.time() - t0:.0f} s", flush=True)
    return th


# ------------------------------------------------------------------------------------------------ filtro
def observaciones_theta(th: pd.DataFrame, m: str) -> pd.DataFrame:
    """Una fila por persona-año (como historial.observaciones, en la escala θ): ȳ ponderada por precisión, v̄ = 1/Σw."""
    y = th[f"{m}_th"].to_numpy(float)
    v = th[f"{m}_thsd"].to_numpy(float) ** 2
    pid = pd.to_numeric(th["persona_id"], errors="coerce").to_numpy(float)
    ok = np.isfinite(y) & np.isfinite(v) & (v > 0) & np.isfinite(pid)
    pos = th["pos3"].where(th["pos3"].isin(("E", "A", "I")), "A").to_numpy()
    x = pd.DataFrame({"persona_id": pid[ok].astype(np.int64), "anio": th["temporada"].str[:4].astype(int).to_numpy()[ok],
                      "y": y[ok], "w": 1 / v[ok], "min": pd.to_numeric(th["min"], errors="coerce").fillna(0).to_numpy()[ok],
                      "pos3": pos[ok]})
    x["wy"] = x["w"] * x["y"]
    g = x.sort_values("min").groupby(["persona_id", "anio"])
    o = g.agg(w=("w", "sum"), wy=("wy", "sum"), min=("min", "sum"), pos3=("pos3", "last")).reset_index()
    o["y"] = o["wy"] / o["w"]
    o["v"] = 1 / o["w"]
    return o[["persona_id", "anio", "y", "v", "min", "pos3"]].sort_values(["persona_id", "anio"]).reset_index(drop=True)


def filtrar_corte(th_hist: pd.DataFrame, th_t: pd.DataFrame, anio_corte: int, mets: list[str]) -> tuple[dict, dict]:
    """Nivel filtrado en t por persona y métrica (m, P) con τ², c ajustados con las temporadas ≤ t de este corte."""
    from . import historial as H
    todo = pd.concat([th_hist, th_t], ignore_index=True)
    niv, par = {}, {}
    for m in mets:
        if f"{m}_th" not in th_t or f"{m}_th" not in th_hist:
            continue
        o = observaciones_theta(todo, m)
        o = o[o["anio"] <= anio_corte]
        p = H.ajustar(o)
        f = H.filtrar(o, p["tau2"], p["c"], p["pp"])
        ft = f[f["anio"] == anio_corte]
        niv[m] = ft.set_index("persona_id")[["m", "P", "y", "v"]]
        con_hist = int(ft["persona_id"].isin(set(o.loc[o["anio"] < anio_corte, "persona_id"])).sum())
        par[m] = {"tau2": p["tau2"], "c": p["c"], "pos": {k: list(v) for k, v in p["pp"].items()}, "var_y": p["var_y"],
                  "personas_t": int(len(ft)), "con_historia": con_hist}
    return niv, par


# ------------------------------------------------------------------------------------------------ brazos del examen
BRAZOS = ("v33", "v42_d1", "v42")
# v42_d1 (PRERREGISTRO, motor_v42.entradas_motor_v42): nivel con historial SÓLO en las métricas que pasaron la D1
#        (data/modelos/v4_2/normalizacion/examen_d1.json → version «v4.2», modelo literal); decide.
# v42    (variante pedida en el encargo de la pieza): nivel con historial en TODAS las métricas del motor salvo RAPM.
BRAZO_DECIDE = "v42_d1"
D1 = RAIZ / "data" / "modelos" / "v4_2" / "normalizacion" / "examen_d1.json"


def metricas_d1() -> list[str]:
    """Métricas que pasaron la D1 con el modelo literal (sello ALTA o MEDIA → versión v4.2)."""
    d = json.loads(D1.read_text(encoding="utf-8"))["metricas"]
    return sorted(m for m, v in d.items() if v.get("version") == "v4.2")


def metricas_brazo(b: str, cfg) -> list[str]:
    todas = _metricas(cfg)
    return [m for m in todas if m in set(metricas_d1())] if b == "v42_d1" else todas
COMUNES = ["partidos_jugador.pkl", "roles_temporada.pkl", "theta_V32.pkl", "traduccion_v31.pkl"]


def dir_brazo(b: str) -> Path:
    return DIR_EX / f"brazo_{b}"


def _enlazar(dst: Path, src: Path) -> None:
    if not dst.exists() and src.exists():
        dst.symlink_to(src)


def preparar_brazos(progreso=print) -> None:
    """Cachés de los dos brazos: insumos que no dependen de θ enlazados (sólo lectura) a la caché de la v3.2; el corte
    V32_corte de cada temporada t: el original (brazo v33) o el mismo con el nivel filtrado (brazo v42)."""
    for b in BRAZOS:
        d = dir_brazo(b)
        d.mkdir(parents=True, exist_ok=True)
        for f in COMUNES + [p.name for p in CACHE32.glob("modelos_hasta_*.pkl")] + ["corte_2025-26_V32.pkl"]:
            _enlazar(d / f, CACHE32 / f)
    for t in CORTES:
        _enlazar(dir_brazo("v33") / f"corte_{t}_V32_corte.pkl", CACHE32 / f"corte_{t}_V32_corte.pkl")
        for b in BRAZOS[1:]:
            if not (dir_brazo(b) / f"corte_{t}_V32_corte.pkl").exists():
                corte_filtrado(t, b, progreso)
    # insumos de la temporada de destino (V32) y casos de los cortes previos: no dependen de θ, se comparten
    for b in BRAZOS[1:]:
        for f in list(dir_brazo("v33").glob("corte_20*_V32.pkl")) + list(dir_brazo("v33").glob("casos_20*_V32.pkl")):
            _enlazar(dir_brazo(b) / f.name, f)


def corte_filtrado(t: str, brazo: str = "v42", progreso=print) -> dict:
    """Registros de la temporada t del corte V32_corte con θ, sd, <m>_am y varianza propia de las métricas filtradas
    sustituidos por el nivel con historial (persona), y L, L_sd recalculados. Guarda corte_<t>_V32_corte.pkl del brazo
    v42 y los parámetros del filtro."""
    from bbfit import sim_insumos as SI
    from bbmodel.metricas import destransformar
    cfg = _env()
    a = SI.anio(t)
    mets = metricas_brazo(brazo, cfg)
    reg, eq, trad = pickle.loads((CACHE32 / f"corte_{t}_V32_corte.pkl").read_bytes())
    nv = pickle.loads((CACHE32 / f"norm_v32_hasta_{a}.pkl").read_bytes())
    const2 = pickle.loads((CACHE32 / f"norm_hasta_{a}.pkl").read_bytes())["traduccion"]["constantes"]
    th_t = nv["theta"].copy()
    tabla = _tabla()
    ft = tabla[tabla["temporada"] == t][["liga", "player_id", "persona_id", "min"]].drop_duplicates(["liga", "player_id"])
    th_t = th_t.merge(ft, on=["liga", "player_id"], how="left")
    hist = theta_historia(a, progreso)
    niv, par = filtrar_corte(hist, th_t, a, mets)
    r = reg.copy()
    pid = pd.to_numeric(r["persona_id"], errors="coerce")
    # persona del registro = la de la tabla de la normalización (mismo identificador que la historia)
    mapa = ft.dropna(subset=["persona_id"]).set_index(["liga", "player_id"])["persona_id"]
    pid_n = pd.Series([mapa.get((l, p), np.nan) for l, p in zip(r["liga"], r["player_id"].astype(str))], index=r.index)
    pid_n = pd.to_numeric(pid_n, errors="coerce").fillna(pid)
    pos = r["pos3"].astype(object).to_numpy()
    cambios = {}
    for m, N in niv.items():
        mm = pid_n.map(N["m"]).to_numpy(float)
        PP = pid_n.map(N["P"]).to_numpy(float)
        ok = np.isfinite(mm) & np.isfinite(PP) & np.isfinite(pd.to_numeric(r[f"{m}_th"], errors="coerce").to_numpy(float))
        k = const2[m]
        mu = np.array([SI.entorno(k, "euroleague", t, p)[0] if isinstance(p, str) else np.nan for p in pos])
        tau = np.array([SI.entorno(k, "euroleague", t, p)[1] if isinstance(p, str) else np.nan for p in pos])
        ok &= np.isfinite(mu) & np.isfinite(tau)
        s0 = np.array(r[f"{m}_thsd"], dtype=float, copy=True)
        vj0 = np.array(r[f"{m}_vj"], dtype=float, copy=True) if f"{m}_vj" in r else np.full(len(r), np.nan)
        vo = np.where(np.isfinite(vj0), np.maximum(s0 ** 2 - vj0, 0.0), 0.0)        # varianza del nivel de liga
        th0 = np.array(r[f"{m}_th"], dtype=float, copy=True)
        r.loc[ok, f"{m}_th"] = mm[ok]
        r.loc[ok, f"{m}_thsd"] = np.sqrt(PP[ok])
        r.loc[ok, f"{m}_am"] = destransformar(mu[ok] + tau[ok] * mm[ok], k["transf"])
        if f"{m}_vj" in r:
            r.loc[ok, f"{m}_vj"] = np.maximum(PP[ok] - vo[ok], 0.1 * PP[ok])
        cambios[m] = {"filas": int(ok.sum()), "de": int(len(r)), "con_historia": par[m]["con_historia"],
                      "dif_media_abs_theta": float(np.nanmean(np.abs(mm[ok] - th0[ok]))),
                      "cociente_sd_mediano": float(np.nanmedian(np.sqrt(PP[ok]) / s0[ok]))}
    r["L"] = SI.indice_L(r, "_am")
    r["L_sd"] = SI.L_intervalo(r, trad["constantes"])
    d = dir_brazo(brazo)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"corte_{t}_V32_corte.pkl").write_bytes(pickle.dumps((r, eq, trad)))
    info = {"corte": t, "brazo": brazo, "metricas": mets, "parametros": par, "cambios": cambios}
    (d / f"filtro_{t}.json").write_text(json.dumps(info, indent=1, default=float), encoding="utf-8")
    if progreso:
        progreso(f"  corte {t} filtrado ({brazo}): " + ", ".join(f"{m} τ²={p['tau2']:.3f} c={p['c']:.2f}" for m, p in
                                                     list(par.items())[:4]) + " …", flush=True)
    return info


def _usar_brazo(b: str):
    """Apunta las cachés y salidas de bbfit al brazo `b` (en memoria)."""
    cfg = _env()
    from bbfit import sim_insumos as SI, simulador as S, validacion as V
    SI.DIR_CACHE = dir_brazo(b)
    V.DIR_VAL = SALIDA / "validacion"
    S._CORTES.clear()
    return cfg, SI, S, V


def pesos_originales(V, cfg, roles, progreso=print) -> dict:
    """(pesos, Fit, matriz de transición) y capa de calibración de salida de cada corte de la ejecución V32_inicio_adapt
    (la que reutilizó el examen V32_corte: resumen.json → pesos_de). La matriz de transición no se guardó: se rehace con
    los fichajes de los cortes anteriores (rol de origen y rol real: no dependen de θ)."""
    r = json.loads((DIR_VAL32 / PESOS_DE / "resumen.json").read_text(encoding="utf-8"))
    temps = [t for t in cfg["historico"]["temporadas"] if t <= CORTES[-1]]
    casos = {}
    for t in temps:
        if t < CORTES[-1]:
            casos[t] = V.preparar_corte(t, "V32", cfg, roles, progreso)["casos"]
    out = {}
    for t in CORTES:
        prev = [casos[s] for s in temps if s < t]
        trans = V.matriz_transicion(pd.concat(prev, ignore_index=True)[["rol_o", "rol_real"]]) if prev else None
        out[t] = {"pesos": r["pesos"][t], "fit": r["fit"][t], "trans": trans, "cal_s": r["calibracion_salida"].get(t)}
    return out


def backtest_brazo(b: str, progreso=print) -> pd.DataFrame:
    """Examen V32_corte (escenario inicio, adaptación) del brazo `b` con los pesos por corte del examen original."""
    dest = SALIDA / "validacion" / b / "predicciones.csv.gz"
    if dest.exists():
        return pd.read_csv(dest, low_memory=False)
    cfg, SI, S, V = _usar_brazo(b)
    roles = V._roles()
    P = pesos_originales(V, cfg, roles, progreso)
    preds = []
    t0 = time.time()
    for t in CORTES:
        p = P[t]
        d = V.ejecutar_corte(t, "V32_corte", cfg, roles, p["pesos"], p["fit"], p["trans"], "inicio", progreso,
                             sin_adaptacion=False, etiqueta="_adapt")
        d["v_fit"] = V.aplicar_fit(d.assign(**{f"c_{r}": d.get(f"v_c_{r}") for r in V.RASGOS_FIT}), p["fit"])
        d = V.aplicar_calibracion(d, p["cal_s"])
        preds.append(d)
        if progreso:
            progreso(f"  brazo {b} · corte {t}: {len(d)} fichajes ({time.time() - t0:.0f} s)", flush=True)
    e = V.errores(pd.concat(preds, ignore_index=True), cfg)
    dest.parent.mkdir(parents=True, exist_ok=True)
    e.to_csv(dest, index=False, float_format="%.4f")
    (dest.parent / "resumen.json").write_text(json.dumps(
        {"brazo": b, "fuente": "V32_corte", "escenario": "inicio", "adaptacion": True, "pesos_de": PESOS_DE,
         "simulaciones": int(cfg["validacion"]["simulaciones"]), "cortes": CORTES,
         "resumen": V.resumen_metricas(e, cfg), "tiempo_s": round(time.time() - t0)},
        ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return e


# ------------------------------------------------------------------------------------------------ examen D2 · motor
MARGEN_V40 = {"pts_p100": 0.005, "ts_pct": 0.005, "min": 0.01}          # simulation_v40.yaml → v32.margenes
MARGEN_OTRAS = 0.01                                                     # «secundarias» (USG, AST, TOV; resto igual)
MARGEN_C = 0.01                                                         # «contribucion»
CLAVE = ["persona_id", "corte", "liga_d", "team_d"]


def decisiones_anidadas() -> dict:
    """Decisiones de la v3.2 (pasos, k, producción) y de la v3.3 (centro de minutos) de cada corte, tomadas en su día
    con los cortes anteriores (sin fuga). Son el diseño del motor: iguales en los dos brazos."""
    d32 = json.loads((DIR_VAL32.parent / "decisiones_v32.json").read_text(encoding="utf-8"))["anidado"]
    d33 = json.loads(DEC33.read_text(encoding="utf-8"))["anidado"]
    out = {}
    for t in CORTES:
        dec = d32[t].get("decision")
        if dec:
            assert not {"redistribuir_uso", "adaptacion"} & set(dec["quitar"]), "haría falta la ejecución sin el paso"
            dec = {"quitar": dec["quitar"], "produccion": dec["produccion"],
                   "A3": {"k_beta": dec["A3"]["k_beta"], "k_comp": dec["A3"]["k_comp"]}}
        out[t] = {"dec": dec, "minutos": d33[t]["minutos"]["elegido"]}
    return out


def _cargar_brazo(b: str) -> pd.DataFrame:
    e = pd.read_csv(SALIDA / "validacion" / b / "predicciones.csv.gz", low_memory=False)
    return e[e["error"].isna()].reset_index(drop=True) if "error" in e else e


def predicciones_v33(b: str, e_all: pd.DataFrame, D: dict, c32: dict) -> dict:
    """Centros y rangos (sin recalibrar) del motor v3.3 por corte para el brazo b: producción de la decisión anidada
    de la v3.2 y minutos con el centro anidado de la v3.3 (GBM entrenado SÓLO con los cortes anteriores del mismo
    brazo, con sus registros de origen)."""
    from bbfit import b7_b9 as B, v32, v33
    _usar_brazo(b)
    reg = B.registros_origen(e_all, "V32_corte")
    X = v33.X_gbm(e_all.merge(reg, on=["persona_id", "temporada_o"], how="left", suffixes=("", "_reg")))
    gbm = v33.gbm_anidado(e_all, X)
    out = {}
    for t in CORTES:
        s = (e_all["corte"] == t).to_numpy()
        e_t = e_all[s].reset_index(drop=True)
        dec = D[t]["dec"]
        if dec is None:
            prod = v32.produccion(e_t, "motor")
        else:
            prod = v32.produccion(e_t, dec["produccion"], dec["A3"]["k_beta"], dec["A3"]["k_comp"],
                                  sin_ruido="ruido_personal" in dec["quitar"])
        base = v32.minutos(e_t)
        cm = v33.centros(e_t, base["pred"].to_numpy(float), gbm[s])[D[t]["minutos"]]
        out[t] = {"e": e_t, "prod": prod, "min": v33.candidato_minutos(base, cm, v32._gm(e_t)), "gbm": gbm[s]}
    return out


def recalibrar_con_calibracion(P: dict, D: dict, c32: dict) -> dict:
    """Prerregistro: factores conformales de dos colas (A4, mismos grupos y contracción, peso 1) ajustados SÓLO con los
    fichajes del corte de calibración (2021-22) con el mismo método de producción y centro de minutos que el corte de
    decisión; se aplican al corte de decisión."""
    from bbfit import v32, v33
    ec = P[CAL]["e"]
    gdc, goc = v32.grupo_destino(ec["liga_o"], ec["liga_d"]), v32.grupo_origen(ec["liga_o"])
    w = np.ones(len(ec))
    okc = v32.ok_produccion(ec)
    out = {}
    for t in DECISION:
        dec, e = D[t]["dec"], P[t]["e"]
        gd, go = v32.grupo_destino(e["liga_o"], e["liga_d"]), v32.grupo_origen(e["liga_o"])
        pc = v32.produccion(ec, dec["produccion"], dec["A3"]["k_beta"], dec["A3"]["k_comp"],
                            sin_ruido="ruido_personal" in dec["quitar"])
        prod = {}
        for m, p in P[t]["prod"].items():
            yy = ec["C_real"].to_numpy(float) if m == "C" else ec[f"{m}_real"].to_numpy(float)
            okm = ec["eval_min"].to_numpy(bool) if m == "C" else okc
            f = v32.ajustar_recalibracion(pc[m], yy, okm, gdc, goc, w, c32)
            prod[m] = v32.aplicar_recalibracion(p, f, gd, go)
        bc = v32.minutos(ec)
        cmc = v33.centros(ec, bc["pred"].to_numpy(float), np.full(len(ec), np.nan))[D[t]["minutos"]]
        mc = v33.candidato_minutos(bc, cmc, v32._gm(ec))
        f = v32.ajustar_recalibracion(mc, ec["min_real"].to_numpy(float), ec["eval_min"].to_numpy(bool), gdc, goc, w, c32)
        out[t] = {"e": e, "prod": prod, "min": v32.aplicar_recalibracion(P[t]["min"], f, gd, go)}
    return out


def recalibrar_anidada(P: dict, D: dict, c32: dict) -> dict:
    """Secundario (como el examen v3.3): A4 con los cortes ANTERIORES y pesos por recencia ρ^(t−1−s)."""
    from bbfit import v32, v33
    rho = float(c32["v32"]["recalibracion"].get("rho", 0.5))
    out = {}
    for k, t in enumerate(DECISION, 1):
        dec, e = D[t]["dec"], P[t]["e"]
        prev = CORTES[:CORTES.index(t)]
        ep = pd.concat([P[s]["e"] for s in prev], ignore_index=True)
        pp = v32.produccion(ep, dec["produccion"], dec["A3"]["k_beta"], dec["A3"]["k_comp"],
                            sin_ruido="ruido_personal" in dec["quitar"])
        w = v32.pesos_recencia(ep["corte"], t, CORTES, rho)
        gdp, gop = v32.grupo_destino(ep["liga_o"], ep["liga_d"]), v32.grupo_origen(ep["liga_o"])
        gd, go = v32.grupo_destino(e["liga_o"], e["liga_d"]), v32.grupo_origen(e["liga_o"])
        okp = v32.ok_produccion(ep)
        prod = {}
        for m, p in P[t]["prod"].items():
            yy = ep["C_real"].to_numpy(float) if m == "C" else ep[f"{m}_real"].to_numpy(float)
            okm = ep["eval_min"].to_numpy(bool) if m == "C" else okp
            prod[m] = v32.aplicar_recalibracion(p, v32.ajustar_recalibracion(pp[m], yy, okm, gdp, gop, w, c32), gd, go)
        gbm_p = np.concatenate([P[s]["gbm"] for s in prev])
        bp = v32.minutos(ep)
        cmp_ = v33.centros(ep, bp["pred"].to_numpy(float), gbm_p)[D[t]["minutos"]]
        mp = v33.candidato_minutos(bp, cmp_, v32._gm(ep))
        f = v32.ajustar_recalibracion(mp, ep["min_real"].to_numpy(float), ep["eval_min"].to_numpy(bool), gdp, gop, w, c32)
        out[t] = {"e": e, "prod": prod, "min": v32.aplicar_recalibracion(P[t]["min"], f, gd, go)}
    return out


def _boot_cluster(cl: np.ndarray, xa: np.ndarray, xb: np.ndarray, B: int, semilla: int) -> dict:
    """MAE_a − MAE_b y MAE_a/MAE_b − 1 (pareados) con IC95 por remuestreo de conglomerados."""
    u, inv = np.unique(cl, return_inverse=True)
    nc = len(u)
    sa, sb = np.bincount(inv, xa, nc), np.bincount(inv, xb, nc)
    n = np.bincount(inv, minlength=nc).astype(float)
    rng = np.random.default_rng(semilla)
    bd, br = np.empty(B), np.empty(B)
    for i in range(B):
        k = np.bincount(rng.integers(0, nc, nc), minlength=nc)
        bd[i] = (k @ sa - k @ sb) / (k @ n)
        br[i] = (k @ sa) / (k @ sb) - 1
    return {"dif": float((sa.sum() - sb.sum()) / n.sum()), "dif_ic95": [float(x) for x in np.quantile(bd, [.025, .975])],
            "rel": float(sa.sum() / sb.sum() - 1), "rel_ic95": [float(x) for x in np.quantile(br, [.025, .975])],
            "conglomerados": int(nc)}


def _filas(R: dict, b: str, cortes: list[str]) -> pd.DataFrame:
    """Por fichaje: error absoluto, cobertura y anchura del 80 % de cada métrica y de los minutos."""
    from bbfit import v32
    fr = []
    for t in cortes:
        r = R[b][t]
        e = r["e"]
        x = e[CLAVE].copy()
        okp = v32.ok_produccion(e)
        em = e["eval_min"].to_numpy(bool)
        for m, p in list(r["prod"].items()) + [("min", r["min"])]:
            y = e["C_real" if m == "C" else ("min_real" if m == "min" else f"{m}_real")].to_numpy(float)
            c = p["pred"].to_numpy(float)
            ok = (em if m in ("C", "min") else okp) & np.isfinite(y) & np.isfinite(c)
            lo, hi = p["lo80"].to_numpy(float), p["hi80"].to_numpy(float)
            x[f"ok_{m}"] = ok
            x[f"err_{m}"] = np.where(ok, np.abs(c - y), np.nan)
            x[f"cub_{m}"] = np.where(ok & np.isfinite(lo), ((y >= lo) & (y <= hi)).astype(float), np.nan)
            x[f"ancho_{m}"] = np.where(ok & np.isfinite(lo), hi - lo, np.nan)
        fr.append(x)
    return pd.concat(fr, ignore_index=True)


def reproduccion() -> dict:
    """Control: el brazo v3.3 rehecho frente a las predicciones guardadas del examen V32_corte original."""
    a = pd.read_csv(SALIDA / "validacion" / "v33" / "predicciones.csv.gz", low_memory=False)
    b = pd.read_csv(DIR_VAL32 / "V32_corte_inicio_adapt" / "predicciones.csv.gz", low_memory=False)
    m = a.merge(b, on=CLAVE, suffixes=("_n", "_o"))
    out = {"fichajes": [int(len(a)), int(len(b)), int(len(m))]}
    for c in ("v_min_pred", "v_pts_p100_pred", "v_ts_pct_pred", "a_pts_p100_pred"):
        d = (m[f"{c}_n"].astype(float) - m[f"{c}_o"].astype(float)).abs().dropna()
        out[c] = {"dif_abs_media": float(d.mean()), "dif_abs_max": float(d.max()), "fraccion_identica": float((d < 1e-3).mean())}
    return out


def examen(progreso=print) -> dict:
    """Examen prerregistrado D2 · motor: cada brazo v4.2 frente a v3.3 en los mismos fichajes y cortes. Decide el brazo
    prerregistrado (v42_d1); el de todas las métricas (v42) se informa."""
    t0 = time.time()
    c32 = _env()
    D = decisiones_anidadas()
    brazos = [b for b in BRAZOS if (SALIDA / "validacion" / b / "predicciones.csv.gz").exists()]
    E = {b: _cargar_brazo(b) for b in brazos}
    k = E["v33"][CLAVE].drop_duplicates(CLAVE)
    for b in brazos[1:]:
        k = k.merge(E[b][CLAVE].drop_duplicates(CLAVE), on=CLAVE)                     # mismos fichajes en todos
    E = {b: e.merge(k, on=CLAVE).drop_duplicates(CLAVE).sort_values(CLAVE).reset_index(drop=True) for b, e in E.items()}
    P = {b: predicciones_v33(b, E[b], D, c32) for b in brazos}
    R = {b: recalibrar_con_calibracion(P[b], D, c32) for b in brazos}
    RN = {b: recalibrar_anidada(P[b], D, c32) for b in brazos}
    RAW = {b: {t: P[b][t] for t in DECISION} for b in brazos}
    mets = list(c32["produccion"]["metricas"]) + ["C", "min"]
    B, sem = int(CFG42["bootstrap"]["B"]), 20261109

    def comparar(bz: str, cortes: list[str]) -> dict:
        a, b_ = _filas(R, bz, cortes), _filas(R, "v33", cortes)
        an, bn = _filas(RN, bz, cortes), _filas(RN, "v33", cortes)
        ar, br_ = _filas(RAW, bz, cortes), _filas(RAW, "v33", cortes)
        assert (a[CLAVE].astype(str).to_numpy() == b_[CLAVE].astype(str).to_numpy()).all()
        res = {}
        for m in mets:
            ok = a[f"ok_{m}"].to_numpy(bool) & b_[f"ok_{m}"].to_numpy(bool)
            xa, xb = a[f"err_{m}"].to_numpy(float)[ok], b_[f"err_{m}"].to_numpy(float)[ok]
            per = a["persona_id"].astype(str).to_numpy()[ok]
            club = (a["liga_d"].astype(str) + "|" + a["team_d"].astype(str) + "|" + a["corte"].astype(str)).to_numpy()[ok]
            d = {"n": int(ok.sum()), "mae_v33": float(xb.mean()), "mae_v42": float(xa.mean()),
                 "persona": _boot_cluster(per, xa, xb, B, sem), "club_corte": _boot_cluster(club, xa, xb, B, sem)}
            for nom, (A_, B_) in {"cal": (a, b_), "anidada": (an, bn), "sin_recalibrar": (ar, br_)}.items():
                ca, cb = A_[f"cub_{m}"].to_numpy(float)[ok], B_[f"cub_{m}"].to_numpy(float)[ok]
                wa, wb = A_[f"ancho_{m}"].to_numpy(float)[ok], B_[f"ancho_{m}"].to_numpy(float)[ok]
                s = np.isfinite(wa) & np.isfinite(wb) & (wb > 0)
                d[f"cob80_{nom}"] = {"v33": float(np.nanmean(cb)) if np.isfinite(cb).any() else None,
                                     "v42": float(np.nanmean(ca)) if np.isfinite(ca).any() else None}
                d[f"anchura80_{nom}"] = {"mediana_v33": float(np.median(wb[s])) if s.any() else None,
                                         "mediana_v42": float(np.median(wa[s])) if s.any() else None,
                                         "cociente_mediano_v42_v33": float(np.median(wa[s] / wb[s])) if s.any() else None}
            res[m] = d
        return res

    def regla(g: dict) -> tuple[dict, bool]:
        reglas, pasa = {}, True
        for m in mets:
            x = g[m]
            margen = MARGEN_V40.get(m, MARGEN_C if m == "C" else MARGEN_OTRAS)
            # IC95 superior: el mayor de los dos remuestreos (persona, prerregistro; club de destino × corte, el del
            # examen v3.2/v3.3), para no elegir a posteriori el más favorable
            sup = max(x["persona"]["rel_ic95"][1], x["club_corte"]["rel_ic95"][1])
            cob = x["cob80_cal"]["v42"]
            cob_ok = cob is not None and 0.75 <= cob <= 0.85
            reglas[m] = {"margen_rel": margen, "ic95_sup_rel": sup, "mae_no_peor": bool(sup < margen),
                         "cobertura80_v42": cob, "cobertura_en_rango": bool(cob_ok), "cumple": bool(sup < margen and cob_ok)}
            if m == "C":            # contribución: no es producción por 100 ni minutos → informativa, no decide
                reglas[m]["decide"] = False
                continue
            pasa &= reglas[m]["cumple"]
        return reglas, bool(pasa)

    out = {"prerregistro": "configs/v42.yaml → motor_v42 (examen_motor, entradas_motor_v42, recalibracion; commit d606f47)",
           "banco": "fichajes reales del examen sin fuga V32_corte (escenario inicio, adaptación) que decidió la v3.3",
           "cortes": {"calibracion": CAL, "decision": DECISION}, "fichajes_comunes": int(len(k)),
           "simulaciones_por_fichaje": int(c32["validacion"]["simulaciones"]),
           "decisiones_anidadas": D, "brazo_que_decide": BRAZO_DECIDE, "metricas_d1": metricas_d1(), "brazos": {}}
    for bz in brazos[1:]:
        g = {"conjunto": comparar(bz, DECISION), "por_corte": {t: comparar(bz, [t]) for t in DECISION}}
        g["regla"], g["pasa"] = regla(g["conjunto"])
        g["filtro_por_corte"] = {t: json.loads((dir_brazo(bz) / f"filtro_{t}.json").read_text(encoding="utf-8"))
                                 for t in CORTES if (dir_brazo(bz) / f"filtro_{t}.json").exists()}
        out["brazos"][bz] = g
    out["reproduccion_v33"] = reproduccion()
    pasa = BRAZO_DECIDE in out["brazos"] and out["brazos"][BRAZO_DECIDE]["pasa"]
    out["pasa"] = bool(pasa)
    out["decision"] = "v4.2 sustituye a v3.3" if pasa else "se mantiene la v3.3"
    out["tiempo_s"] = round(time.time() - t0)
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "examen_d2_motor.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float),
                                                 encoding="utf-8")
    if progreso:
        for bz, g in out["brazos"].items():
            progreso(f"  brazo {bz}: {'PASA' if g['pasa'] else 'NO PASA'}", flush=True)
            for m in mets:
                x = g["conjunto"][m]
                progreso(f"    {m:10s} MAE v3.3 {x['mae_v33']:.3f} v4.2 {x['mae_v42']:.3f} · Δ {x['persona']['dif']:+.3f} "
                         f"{np.round(x['persona']['dif_ic95'], 3)} · ΔR {x['persona']['rel']:+.2%} "
                         f"{np.round(np.array(x['persona']['rel_ic95']) * 100, 2)} % · cob80 {x['cob80_cal']} · "
                         f"anch {x['anchura80_cal']['cociente_mediano_v42_v33']} · {'OK' if g['regla'][m]['cumple'] else 'NO'}",
                         flush=True)
        progreso(f"  → {out['decision']}", flush=True)
    return out


# ------------------------------------------------------------------------------------------------ dataset publicado
def dataset(progreso=print, solo_d1: bool = True) -> dict:
    """Dataset del simulador v4.2 (normalizacion.dir de configs/simulation_v42.yaml): copia del de la v3.3
    (experimentos/cache_simulador_v3_2/normalizado, `bbfit dataset-simulador`) con <m>_am, <m>_am_lo y <m>_am_hi de
    cada métrica que pasó la D1 (prerregistro: entradas_motor_v42; solo_d1=False: todas salvo RAPM) sustituidos por el nivel filtrado en s (temporadas ≤ s; todas en la misma vara
    EuroLeague 2025-26) y su rango del 80 %: T⁻¹(m_s ± z80·√P_s). τ² y c por máxima verosimilitud SÓLO con las
    temporadas ≤ 2021-22 (corte de calibración): el dataset no usa nada de los cortes de decisión para ajustar.
    <m>_am_pctel no se recalcula (el motor no lo lee)."""
    from bbmodel.metricas import CATALOGO, destransformar, transformar
    from . import historial as H
    origen = CACHE32 / "normalizado"
    dest = CACHE42 / "normalizado"
    dest.mkdir(parents=True, exist_ok=True)
    ficheros = sorted(origen.glob("*.csv.gz"))
    dd = {f.name: pd.read_csv(f, dtype={"player_id": str, "team_id": str, "persona_id": str}, low_memory=False)
          for f in ficheros}
    cab = next(iter(dd.values())).columns
    d1 = set(metricas_d1()) if solo_d1 else set(CATALOGO)
    mets = [m for m in CATALOGO if m not in SIN_FILTRO and m in d1
            and all(f"{m}{s}" in cab for s in ("_am", "_am_lo", "_am_hi"))]
    todo = pd.concat([d.assign(_f=k, _i=np.arange(len(d))) for k, d in dd.items()], ignore_index=True)
    todo["anio"] = todo["temporada"].str[:4].astype(int)
    pid = pd.to_numeric(todo["persona_id"], errors="coerce")
    par = {}
    cal = int(CFG42["cortes"]["calibracion"])
    for m in mets:
        tr = CATALOGO[m].transf
        y = transformar(todo[f"{m}_am"].to_numpy(float), tr)
        lo, hi = transformar(todo[f"{m}_am_lo"].to_numpy(float), tr), transformar(todo[f"{m}_am_hi"].to_numpy(float), tr)
        v = ((hi - lo) / (2 * Z80)) ** 2
        ok = np.isfinite(y) & np.isfinite(v) & (v > 0) & pid.notna().to_numpy()
        x = pd.DataFrame({"persona_id": pid[ok].astype(np.int64).to_numpy(), "anio": todo["anio"].to_numpy()[ok],
                          "y": y[ok], "w": 1 / v[ok], "min": pd.to_numeric(todo["min"], errors="coerce").fillna(0)
                          .to_numpy()[ok], "pos3": todo["pos3"].where(todo["pos3"].isin(H.POS), "A").to_numpy()[ok]})
        x["wy"] = x["w"] * x["y"]
        o = x.sort_values("min").groupby(["persona_id", "anio"]).agg(
            w=("w", "sum"), wy=("wy", "sum"), min=("min", "sum"), pos3=("pos3", "last")).reset_index()
        o["y"], o["v"] = o["wy"] / o["w"], 1 / o["w"]
        o = o.sort_values(["persona_id", "anio"]).reset_index(drop=True)
        p = H.ajustar(o[o["anio"] <= cal])
        f = H.filtrar(o, p["tau2"], p["c"], p["pp"]).set_index(["persona_id", "anio"])
        key = pd.MultiIndex.from_arrays([pid.fillna(-1).astype(np.int64).to_numpy(), todo["anio"].to_numpy()])
        mm = f["m"].reindex(key).to_numpy(float)
        PP = f["P"].reindex(key).to_numpy(float)
        s = ok & np.isfinite(mm) & np.isfinite(PP)
        todo.loc[s, f"{m}_am"] = destransformar(mm[s], tr)
        todo.loc[s, f"{m}_am_lo"] = destransformar(mm[s] - Z80 * np.sqrt(PP[s]), tr)
        todo.loc[s, f"{m}_am_hi"] = destransformar(mm[s] + Z80 * np.sqrt(PP[s]), tr)
        par[m] = {"tau2": p["tau2"], "c": p["c"], "pos": {k: list(v) for k, v in p["pp"].items()}, "filas": int(s.sum()),
                  "anchura_mediana_cociente": float(np.nanmedian(np.sqrt(PP[s] / v[s])))}
        if progreso:
            progreso(f"  {m:16s} τ²={p['tau2']:.4f} c={p['c']:.2f} filas {s.sum()} · anchura ×{par[m]['anchura_mediana_cociente']:.2f}",
                     flush=True)
    for k, d in dd.items():
        g = todo[todo["_f"] == k].sort_values("_i")
        g[d.columns].to_csv(dest / k, index=False)
    info = {"version": "v4.2", "origen": str(origen.relative_to(RAIZ)), "metricas": mets, "solo_d1": solo_d1,
            "ajuste": f"temporadas ≤ {cal}",
            "parametros": par}
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "dataset_simulador_v42.json").write_text(json.dumps(info, ensure_ascii=False, indent=1, default=float),
                                                       encoding="utf-8")
    return info


if __name__ == "__main__":      # python -m bbequipo.v42.motor <theta|brazos|backtest|examen|dataset|todo>
    import sys
    orden = sys.argv[1] if len(sys.argv) > 1 else "todo"
    t0 = time.time()
    if orden in ("theta", "todo"):
        for a in [int(t[:4]) for t in CORTES]:
            theta_historia(a)
    if orden in ("brazos", "todo"):
        preparar_brazos()
    if orden in ("backtest", "todo"):
        for b in BRAZOS:
            backtest_brazo(b)
    if orden in ("examen", "todo"):
        examen()
    if orden in ("dataset", "todo"):
        dataset()
    print(f"hecho en {time.time() - t0:.0f} s")
