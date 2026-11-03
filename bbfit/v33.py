"""Simulador v3.3 (docs/simulador_v33.md): el simulador v3.2 con dos piezas nuevas aprobadas el 03-11-2026.

M  · minutos del fichaje: el examen elige entre el motor (Plackett-Luce, v3.2), un gradient boosting supervisado
     (GBM, la línea base de §16, que ganó al motor: 4,67 frente a 4,86) y la mezcla 50/50 de los dos. Plackett-Luce
     sigue repartiendo los minutos del resto de la plantilla y dando el rol.
B9 · acoplamiento minutos-producción (Monte Carlo): la producción de cada simulación se ajusta a los minutos y al rol
     de esa simulación con  Δy_m = b_m·Δmin + c_m·Δrol,  Δmin = minutos − minutos esperados (min/partido),
     Δrol = índice del rol − índice esperado (0 RESIDUAL … 4 GO_TO_GUY). Sin rol asignado el centro no cambia (Δ de
     media 0); con rol asignado por el club, el centro se desplaza a lo que ese rol implica.

Examen: el mismo examen sin fuga de la v3.2 (fuente V32_corte, cortes 2021-22 → 2024-25, cortes anidados), con las
decisiones de la v3.2 de cada corte. Reglas fijadas ANTES de mirar (docs/simulador_v33.md §2):
  M  · se adopta el candidato con menor error de minutos entre los que mejoran al motor de forma significativa
       (IC90,inf[MAE_motor − MAE_cand] > 0, bootstrap por club × corte); si ninguno, el motor. El acierto de rol no
       cambia (lo sigue dando el motor). Los intervalos de minutos se recalibran (A4) con el centro elegido.
  B9 · coeficientes por mínimos cuadrados (sin término independiente) con los cortes anteriores. Escenario «rol
       asignado» (el club fija el rol real; minutos = mediana de su franja en la liga de destino, de los cortes
       anteriores): se adopta B9 si mejora el error de pts/100 de forma significativa (IC90,sup del cociente < 0) y
       no empeora el de TS% más de +0,5 % (IC90,sup). En el escenario libre el centro no cambia por construcción.

    CERNO_SIMULADOR=v32 python -m bbfit v33-decidir     (lee el examen de la v3.2; escribe data/modelos/simulador/v3_3)
    python -m bbfit v33-aplicar                          (configs/simulation_v33.yaml con las decisiones finales)
"""
from __future__ import annotations

import json
import pickle
import re
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from . import b7_b9 as B
from . import v32
from .config import DIR_CONFIGS, DIR_MOD
from .roles import ROLES

IDX = {r: i for i, r in enumerate(ROLES)}
DIR_V33 = DIR_MOD / "simulador" / "v3_3"
CANDIDATOS = ("motor", "gbm", "mezcla")
SEMILLA = 20261103


def cfg33() -> dict:
    return yaml.safe_load((DIR_CONFIGS / "simulation_v33.yaml").read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------------------ minutos GBM
def X_gbm(x: pd.DataFrame, columnas: list[str] | None = None) -> pd.DataFrame:
    """Matriz del GBM de minutos (mismas variables que B7/§16: registro de origen, salto de nivel, traducción, ligas,
    posición y rol de origen). `columnas` reordena y completa con 0 las indicadoras que falten (predicción)."""
    num = [c for c in x.columns if c in B.COLS_REG or c in ("d_nivel", "min_pct_o", "min_o")
           or re.fullmatch(r"v_\w+_trad", c)]
    X = x[num].apply(pd.to_numeric, errors="coerce")
    for col, pref in (("liga_o", "o_"), ("liga_d", "d_"), ("pos3", "p_"), ("rol_o", "r_")):
        if col in x:
            X = X.join(pd.get_dummies(x[col].astype(str), prefix=pref, dtype=float))
    if columnas is not None:
        X = X.reindex(columns=columnas, fill_value=0.0)
        for c in columnas:
            if c in num:
                X[c] = pd.to_numeric(X[c], errors="coerce")
    return X


def gbm_anidado(e: pd.DataFrame, X: pd.DataFrame) -> np.ndarray:
    """Predicción de minutos de cada corte con un GBM entrenado SÓLO con los cortes anteriores (el primero: NaN)."""
    cortes = sorted(e["corte"].unique())
    y = pd.to_numeric(e["min_real"], errors="coerce").to_numpy(float)
    ok = e["eval_min"].astype(bool).to_numpy() & np.isfinite(y)
    pred = np.full(len(e), np.nan)
    for k, t in enumerate(cortes[1:], 1):
        tr = e["corte"].isin(cortes[:k]).to_numpy() & ok
        te = (e["corte"] == t).to_numpy()
        pred[te] = B._aprendices()["gbm"]().fit(X[tr], y[tr]).predict(X[te])
    return pred


def candidato_minutos(base: pd.DataFrame, centro: np.ndarray, gm: np.ndarray) -> pd.DataFrame:
    """Minutos con otro centro: los intervalos del motor se desplazan con el centro (después, A4 los recalibra)."""
    p = base.copy()
    d = centro - p["pred"].to_numpy(float)
    p["pred"] = np.clip(centro, 0, gm)
    for a in v32.NIVELES:
        for s in ("lo", "hi"):
            if f"{s}{a}" in p:
                p[f"{s}{a}"] = np.clip(p[f"{s}{a}"].to_numpy(float) + d, 0, gm)
    return p


def centros(e: pd.DataFrame, motor: np.ndarray, gbm: np.ndarray) -> dict:
    g = np.where(np.isfinite(gbm), gbm, motor)
    return {"motor": motor, "gbm": g, "mezcla": 0.5 * (motor + g)}


def decidir_minutos(e: pd.DataFrame, cent: dict, c32: dict) -> dict:
    """Regla M sobre los casos de `e` con predicción GBM fuera de muestra."""
    y = e["min_real"].to_numpy(float)
    ok = e["eval_min"].astype(bool).to_numpy() & np.isfinite(y) & e["_gbm_ok"].to_numpy(bool)
    em = np.abs(cent["motor"] - y)
    out = {"casos": int(ok.sum()), "mae": {k: float(np.abs(v - y)[ok].mean()) for k, v in cent.items()}}
    sig = {}
    for k in ("gbm", "mezcla"):
        d, lo, hi = v32.boot_diferencia(e, em, np.abs(cent[k] - y), ok, 1000, SEMILLA)
        out[f"motor_menos_{k}"] = {"d": d, "ic90": [lo, hi]}
        if lo > 0:
            sig[k] = out["mae"][k]
    out["elegido"] = min(sig, key=sig.get) if sig else "motor"
    return out


# ------------------------------------------------------------------------------------------ B9
def _delta_rol(e: pd.DataFrame) -> np.ndarray:
    return (e["rol_real"].map(IDX).astype(float) - pd.to_numeric(e["v_indice_rol"], errors="coerce")).to_numpy(float)


def franja(prev: pd.DataFrame) -> dict:
    """Minutos/partido medianos por (liga de destino, rol real) y por rol, de los casos de `prev`."""
    p = prev[prev["eval_min"].astype(bool) & prev["rol_real"].notna()]
    por_liga = {f"{a}|{b}": float(v) for (a, b), v in p.groupby(["liga_d", "rol_real"])["min_real"].median().items()
                if ((p["liga_d"] == a) & (p["rol_real"] == b)).sum() >= 10}
    por_rol = {r: float(v) for r, v in p.groupby("rol_real")["min_real"].median().items()}
    return {"liga_rol": por_liga, "rol": por_rol}


def min_franja(e: pd.DataFrame, fr: dict) -> np.ndarray:
    return np.array([fr["liga_rol"].get(f"{a}|{b}", fr["rol"].get(b, np.nan))
                     for a, b in zip(e["liga_d"], e["rol_real"])], float)


def ajustar_b9(e: pd.DataFrame, prod: dict, min_pred: np.ndarray, mets: list[str]) -> dict:
    """b_m, c_m por mínimos cuadrados sin término independiente: (y − ŷ) ~ b·(min_real − min̂) + c·Δrol."""
    ok = v32.ok_produccion(e) & e["eval_min"].astype(bool).to_numpy()
    dm = e["min_real"].to_numpy(float) - min_pred
    dr = _delta_rol(e)
    out = {}
    for m in mets:
        r = e[f"{m}_real"].to_numpy(float) - prod[m]["pred"].to_numpy(float)
        s = ok & np.isfinite(r) & np.isfinite(dm) & np.isfinite(dr)
        A = np.c_[dm[s], dr[s]]
        coef, *_ = np.linalg.lstsq(A, r[s], rcond=None)
        out[m] = {"b_min": float(coef[0]), "c_rol": float(coef[1]), "casos": int(s.sum())}
    return out


def aplicar_b9(e: pd.DataFrame, prod: dict, coef: dict, dmin: np.ndarray, drol: np.ndarray) -> dict:
    out = {}
    for m, p in prod.items():
        if m not in coef:
            out[m] = p
            continue
        q = p.copy()
        d = np.nan_to_num(coef[m]["b_min"] * dmin + coef[m]["c_rol"] * drol)
        for col in q.columns:
            q[col] = q[col].to_numpy(float) + d
        out[m] = q
    return out


# ------------------------------------------------------------------------------------------ examen
def _rec(prev_pred: pd.DataFrame, y_prev, ok_prev, e_prev, pred: pd.DataFrame, e, corte_obj, cortes, c32):
    if prev_pred is None or not len(prev_pred):
        return pred, None
    w = v32.pesos_recencia(e_prev["corte"], corte_obj, cortes, float(c32["v32"]["recalibracion"].get("rho", 0.5)))
    f = v32.ajustar_recalibracion(prev_pred, y_prev, ok_prev, v32.grupo_destino(e_prev["liga_o"], e_prev["liga_d"]),
                                  v32.grupo_origen(e_prev["liga_o"]), w, c32)
    return v32.aplicar_recalibracion(pred, f, v32.grupo_destino(e["liga_o"], e["liga_d"]),
                                     v32.grupo_origen(e["liga_o"])), f


def _con_gbm(df: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    d = df.drop(columns=[c for c in ("_gbm", "_gbm_ok") if c in df])
    d = d.merge(ref, on=["persona_id", "corte", "liga_d", "team_d"], how="left")
    d["_gbm_ok"] = d["_gbm_ok"].fillna(False).astype(bool)
    return d


def main(progreso=print) -> dict:
    c32 = v32.cfg()
    c33 = cfg33()["v33"]
    EE = v32.cargar_ejecuciones(c32)
    fuente = "V32_corte"
    E = EE[fuente]
    e_all = E["completo"].reset_index(drop=True)
    cortes = sorted(e_all["corte"].unique())
    mets = list(c32["produccion"]["metricas"])
    # GBM de minutos con cortes anidados (registro de origen de la caché de cada corte)
    reg = B.registros_origen(e_all, fuente)
    X = X_gbm(e_all.merge(reg, on=["persona_id", "temporada_o"], how="left", suffixes=("", "_reg")))
    gbm = gbm_anidado(e_all, X)
    e_all["_gbm"] = gbm
    e_all["_gbm_ok"] = np.isfinite(gbm)
    REF = e_all[["persona_id", "corte", "liga_d", "team_d", "_gbm", "_gbm_ok"]].drop_duplicates(
        ["persona_id", "corte", "liga_d", "team_d"])
    informe = {"fuente": fuente, "cortes": cortes, "reglas": "docs/simulador_v33.md §2", "anidado": {}, "examen": {}}
    filas = {"v3.2": [], "v3.3": []}
    cond = {"v3.2": [], "v3.3": [], "oraculo": []}
    for k, t in enumerate(cortes):
        prev_c = cortes[:k]
        dec = v32.decidir_dos_fuentes(EE, prev_c, c32) if prev_c else None
        e_t = e_all[e_all["corte"] == t].reset_index(drop=True)
        prev = e_all[e_all["corte"].isin(prev_c)].reset_index(drop=True) if prev_c else None
        r32 = v32.aplicar(e_t, E, dec, prev, c32, t, cortes)
        src = _con_gbm(r32["e"], REF)
        src["_gbm_ok"] = src["_gbm_ok"].fillna(False).astype(bool)
        # --- M: decisión con los cortes anteriores que tienen GBM fuera de muestra
        prev_g = prev[prev["_gbm_ok"]] if prev is not None else None
        if prev_g is not None and len(prev_g):
            pp = v32.aplicar(prev_g.reset_index(drop=True), E, dec, None, c32, t, cortes)
            ep = _con_gbm(pp["e"], REF)
            dm_dec = decidir_minutos(ep, centros(ep, pp["min"]["pred"].to_numpy(float), ep["_gbm"].to_numpy(float)),
                                     c32)
        else:
            dm_dec = {"elegido": "motor", "motivo": "sin cortes anteriores con GBM fuera de muestra"}
        eleg = dm_dec["elegido"]
        # minutos v3.3 del corte: centro elegido; intervalos del motor desplazados y A4 con los cortes anteriores
        gm_t = v32._gm(src)
        base_min = v32.minutos(src)
        cm = centros(src, base_min["pred"].to_numpy(float), src["_gbm"].to_numpy(float))[eleg]
        min33 = candidato_minutos(base_min, cm, gm_t)
        if prev is not None and len(prev):
            pp = v32.aplicar(prev, E, dec, None, c32, t, cortes)
            ep = _con_gbm(pp["e"], REF)
            cmp = centros(ep, pp["min"]["pred"].to_numpy(float), ep["_gbm"].to_numpy(float))[eleg]
            minp = candidato_minutos(pp["min"], cmp, v32._gm(ep))
            min33, _ = _rec(minp, ep["min_real"].to_numpy(float), ep["eval_min"].to_numpy(bool), ep, min33, src, t,
                            cortes, c32)
        # producción v3.3 = la de la v3.2 (B9 no mueve el centro sin rol asignado); C con los minutos v3.3
        prod33 = {m: p.copy() for m, p in r32["prod"].items()}
        if "C" in prod33 and (dec or {}).get("produccion") == "atlas":
            dC = (min33["pred"].to_numpy(float) - r32["min"]["pred"].to_numpy(float)) / gm_t \
                * src["a_pts_p100_pred"].to_numpy(float)
            for col in prod33["C"].columns:
                prod33["C"][col] = prod33["C"][col].to_numpy(float) + np.nan_to_num(dC)
        r33 = {"e": src, "prod": prod33, "min": min33}
        # --- B9: coeficientes con los cortes anteriores; escenario «rol asignado»
        if prev is not None and len(prev):
            coef = ajustar_b9(ep, pp["prod"], cmp, mets)          # pp, ep, cmp: cortes anteriores (arriba)
            fr = franja(prev)
            dmin = min_franja(src, fr) - r33["min"]["pred"].to_numpy(float)
            drol = _delta_rol(src)
            pc = aplicar_b9(src, r32["prod"], coef, dmin, drol)
            po = aplicar_b9(src, r32["prod"], coef, src["min_real"].to_numpy(float) - r33["min"]["pred"].to_numpy(float),
                            drol)
            ok = v32.ok_produccion(src) & src["eval_min"].to_numpy(bool) & src["rol_real"].notna().to_numpy()
            cond["v3.2"].append((src[ok], {m: r32["prod"][m][ok] for m in mets}))
            cond["v3.3"].append((src[ok], {m: pc[m][ok] for m in mets}))
            cond["oraculo"].append((src[ok], {m: po[m][ok] for m in mets}))
        else:
            coef = None
        informe["anidado"][t] = {"decision_v32": dec and {k2: dec[k2] for k2 in ("quitar", "produccion")},
                                 "minutos": dm_dec, "b9": coef}
        informe["examen"][t] = {"v3.3": v32.medidas(r33, c32), "v3.2": v32.medidas(r32, c32)}
        filas["v3.3"].append(r33), filas["v3.2"].append(r32)
        if progreso:
            progreso(f"  corte {t}: minutos {eleg} · B9 {'con' if coef else 'sin'} coeficientes", flush=True)

    def unir(fs):
        return {"e": pd.concat([f["e"] for f in fs], ignore_index=True),
                "prod": {m: pd.concat([f["prod"][m] for f in fs], ignore_index=True) for m in fs[0]["prod"]},
                "min": pd.concat([f["min"] for f in fs], ignore_index=True)}
    T = {k: unir(v) for k, v in filas.items()}
    informe["examen"]["total"] = {k: v32.medidas(T[k], c32) for k in T}
    # minutos: v3.3 frente a v3.2 en todo el examen (IC 90 % por club × corte)
    e33 = T["v3.3"]["e"]
    y = e33["min_real"].to_numpy(float)
    okm = e33["eval_min"].to_numpy(bool)
    informe["examen"]["minutos_v33_menos_v32"] = dict(zip(("d", "lo", "hi"), v32.boot_diferencia(
        e33, np.abs(T["v3.3"]["min"]["pred"].to_numpy(float) - y), np.abs(T["v3.2"]["min"]["pred"].to_numpy(float) - y),
        okm, 1000, SEMILLA)))
    # B9 en el escenario «rol asignado» (cortes con coeficientes)
    b9 = {}
    ec = pd.concat([x[0] for x in cond["v3.2"]], ignore_index=True)
    for m in mets:
        yy = ec[f"{m}_real"].to_numpy(float)
        p2 = pd.concat([x[1][m] for x in cond["v3.2"]], ignore_index=True)["pred"].to_numpy(float)
        p3 = pd.concat([x[1][m] for x in cond["v3.3"]], ignore_index=True)["pred"].to_numpy(float)
        po = pd.concat([x[1][m] for x in cond["oraculo"]], ignore_index=True)["pred"].to_numpy(float)
        okc = np.isfinite(yy) & np.isfinite(p2) & np.isfinite(p3)
        d, lo, hi = v32.boot_cociente(ec, np.abs(p3 - yy), np.abs(p2 - yy), okc, 1000, SEMILLA)
        b9[m] = {"casos": int(okc.sum()), "mae_v32": float(np.abs(p2 - yy)[okc].mean()),
                 "mae_b9_rol_asignado": float(np.abs(p3 - yy)[okc].mean()),
                 "mae_oraculo_minutos_reales": float(np.abs(po - yy)[okc].mean()),
                 "cociente_menos_1": d, "ic90": [lo, hi]}
    informe["b9_rol_asignado"] = b9
    margen_ts = float(c33.get("margen_ts", 0.005))
    adoptar_b9 = b9["pts_p100"]["ic90"][1] < 0 and b9["ts_pct"]["ic90"][1] < margen_ts
    # decisión final con todos los cortes
    dec_f = v32.decidir_dos_fuentes(EE, cortes, c32)
    rf = v32.aplicar(e_all, E, dec_f, None, c32, "final", cortes + ["final"])
    ef = _con_gbm(rf["e"], REF)
    ef["_gbm_ok"] = ef["_gbm_ok"].fillna(False).astype(bool)
    dm_final = decidir_minutos(ef, centros(ef, rf["min"]["pred"].to_numpy(float), ef["_gbm"].to_numpy(float)), c32)
    eleg = dm_final["elegido"]
    cmf = centros(ef, rf["min"]["pred"].to_numpy(float), ef["_gbm"].to_numpy(float))[eleg]
    minf = candidato_minutos(rf["min"], cmf, v32._gm(ef))
    w = v32.pesos_recencia(ef["corte"], "final", cortes + ["final"], float(c32["v32"]["recalibracion"].get("rho", 0.5)))
    fac_min = v32.ajustar_recalibracion(minf, ef["min_real"].to_numpy(float), ef["eval_min"].to_numpy(bool),
                                        v32.grupo_destino(ef["liga_o"], ef["liga_d"]), v32.grupo_origen(ef["liga_o"]),
                                        w, c32)
    coef_f = ajustar_b9(ef, rf["prod"], minf["pred"].to_numpy(float), mets)
    informe["final"] = {"minutos": dm_final, "minutos_publicados": eleg, "b9": adoptar_b9,
                        "b9_coeficientes": coef_f, "franja_minutos": franja(e_all),
                        "recalibracion_minutos": fac_min}
    # GBM final (todos los cortes) para el simulador publicado y el artifact
    yv = e_all["min_real"].to_numpy(float)
    okv = e_all["eval_min"].astype(bool).to_numpy() & np.isfinite(yv)
    mdl = B._aprendices()["gbm"]().fit(X[okv], yv[okv])
    DIR_V33.mkdir(parents=True, exist_ok=True)
    (DIR_V33 / "gbm_minutos.pkl").write_bytes(pickle.dumps({"modelo": mdl, "columnas": list(X.columns)}))
    (DIR_V33 / "decisiones_v33.json").write_text(json.dumps(informe, indent=1, ensure_ascii=False, default=float),
                                                 encoding="utf-8")
    if progreso:
        tot = informe["examen"]["total"]
        progreso(json.dumps({"final": {k: informe["final"][k] for k in ("minutos_publicados", "b9")},
                             "minutos": dm_final["mae"], "b9_pts": b9["pts_p100"], "b9_ts": b9["ts_pct"],
                             "v3.3": {k: v for k, v in tot["v3.3"].items() if k.startswith(("mae", "cob"))},
                             "v3.2": {k: v for k, v in tot["v3.2"].items() if k.startswith(("mae", "cob"))}},
                            indent=1, default=float), flush=True)
    return informe


def aplicar_config(ruta: Path | None = None, progreso=print) -> dict:
    """Escribe en configs/simulation_v33.yaml las decisiones finales de v33-decidir."""
    ruta = ruta or DIR_CONFIGS / "simulation_v33.yaml"
    d = json.loads((DIR_V33 / "decisiones_v33.json").read_text(encoding="utf-8"))["final"]
    t = ruta.read_text(encoding="utf-8")
    t = re.sub(r"^(  minutos_publicados: )\w+", rf"\g<1>{d['minutos_publicados']}", t, flags=re.M)
    t = re.sub(r"^(  b9: )\w+", rf"\g<1>{'true' if d['b9'] else 'false'}", t, flags=re.M)
    ruta.write_text(t, encoding="utf-8")
    out = {"minutos_publicados": d["minutos_publicados"], "b9": d["b9"]}
    if progreso:
        progreso(f"  simulador v3.3 publicado: {out}", flush=True)
    return out
