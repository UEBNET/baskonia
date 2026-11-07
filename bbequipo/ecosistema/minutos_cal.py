"""P5 (workaround aprobado por el CEO el 06-11-2026) · rangos de minutos recalibrados de la capa E, sin tocar el motor v3.3.

El histórico del producto v3.3 tiene la cola superior saturada (extremo del 90 % = extremo del 80 % en el 97,7 % de las
fichas; cobertura del 90 % 0,87; V41_F0 §3.4). La capa E no cambia el motor: toma su centro (minutos medios del motor
Plackett-Luce) y construye los rangos con los residuos FUERA DE MUESTRA del examen por cortes de la v3.2 (fuente
V32_corte, motor sin GBM: columnas *_motor), como hace la capa 4 con sus intervalos:

    rango_q(jugador) = clip( m̂ + gm · Q_q(e | tramo de m̂/gm), 0, gm ),   e = (minutos reales − m̂)/gm

con Q_q los cuantiles empíricos (5, 10, 90, 95 %) de los residuos en fracción del partido, por tramo de minutos
proyectados (los residuos dependen del nivel: quien proyecta pocos minutos no puede perder muchos).
Examen: cortes 2022–2024 con cuantiles de los cortes anteriores (2021 calibra); criterio prerregistrado
`criterios.f1.minutos_cobertura_recalibrada` (80 % en [0,75, 0,85] y 90 % en [0,85, 0,95]), frente a los rangos del motor.
Producto: cuantiles con todos los cortes → data/modelos/v4_1/escenarios/minutos_calibracion.json.

Límites declarados: (i) el examen de la v3.2 sólo evalúa a los fichajes que llegan a un mínimo de minutos (eval_min), así
que en el tramo de pocos minutos proyectados casi todos los residuos son positivos; se impone que el rango contenga siempre
al centro del motor. (ii) Los residuos son de FICHAJES (lo más incierto); aplicados a los jugadores que siguen, los rangos son
conservadores. El banco V-TRANS de la F3 permitirá separar las dos poblaciones.
"""
from __future__ import annotations

import json
import os
import time

import numpy as np
import pandas as pd

from . import config as CE

QS = (0.05, 0.10, 0.90, 0.95)


def _examen() -> pd.DataFrame:
    os.environ.setdefault("CERNO_SIMULADOR", "v32")
    from bbfit import v32, simulador as S
    E = v32.cargar_ejecuciones(v32.cfg())["V32_corte"]["completo"]
    E = E[E["eval_min"].astype(bool) & E["min_real"].notna()].copy()
    E["gm"] = E["liga_d"].map(lambda l: float(S.minutos_partido(l)))
    E["anio"] = E["corte"].str[:4].astype(int)
    E["pred"] = E["v_min_pred_motor"].astype(float)
    E["r"] = E["pred"] / E["gm"]
    E["e"] = (E["min_real"].astype(float) - E["pred"]) / E["gm"]
    return E


def cuantiles(d: pd.DataFrame, cortes_r: list[float]) -> dict:
    """Cuantiles de e por tramo de r = m̂/gm (tramos por los cortes dados)."""
    b = np.digitize(d["r"].to_numpy(float), cortes_r)
    out = {}
    for k in range(len(cortes_r) + 1):
        e = d["e"].to_numpy(float)[b == k]
        out[str(k)] = {str(q): float(np.quantile(e, q)) if len(e) >= 30 else None for q in QS} | {"n": int(len(e))}
    return out


def aplicar(cal: dict, m: np.ndarray, gm: float) -> dict:
    """Rangos 80 % y 90 % de minutos para centros m (minutos por partido) en una liga de duración gm."""
    m = np.asarray(m, float)
    b = np.digitize(m / gm, cal["cortes_tramo"])
    out = {}
    for lo, hi, nombre in ((0.10, 0.90, "80"), (0.05, 0.95, "90")):
        qlo = np.array([cal["tramos"][str(k)][str(lo)] or cal["global"][str(lo)] for k in b])
        qhi = np.array([cal["tramos"][str(k)][str(hi)] or cal["global"][str(hi)] for k in b])
        # el rango siempre contiene el centro: en el tramo de pocos minutos casi todos los residuos son positivos (el examen
        # de la v3.2 sólo evalúa fichajes que llegan a un mínimo de minutos: sesgo de selección declarado)
        out[f"lo{nombre}"] = np.clip(np.minimum(m + gm * qlo, m), 0, gm)
        out[f"hi{nombre}"] = np.clip(np.maximum(m + gm * qhi, m), 0, gm)
    return out


def _cal(d: pd.DataFrame, cortes_r) -> dict:
    return {"cortes_tramo": list(cortes_r), "tramos": cuantiles(d, cortes_r),
            "global": {str(q): float(np.quantile(d["e"], q)) for q in QS}, "n": int(len(d))}


def ejecutar(cfg: dict, progreso=print) -> dict:
    cc = cfg["f1"]["minutos_intervalos"]
    cortes_r = [float(x) for x in cc["tramos_fraccion_partido"]]
    E = _examen()
    dec = [int(c) for c in cfg["comunes"]["cortes_decision"]]
    elite = set(cfg["comunes"]["segmentos"]["elite_club"])
    filas = []
    for a in dec:
        prev, x = E[E["anio"] < a], E[E["anio"] == a].copy()
        cal = _cal(prev, cortes_r)
        for g in x["gm"].unique():
            m = x["gm"] == g
            r = aplicar(cal, x.loc[m, "pred"].to_numpy(), float(g))
            for k, v in r.items():
                x.loc[m, k] = v
        y = x["min_real"].astype(float)
        for seg, s in (("global", np.ones(len(x), bool)), ("elite_club", x["liga_d"].isin(elite).to_numpy())):
            xs, ys = x[s], y[s]
            filas.append({"corte": a, "segmento": seg, "n": int(s.sum()),
                          "cob80": float(((ys >= xs["lo80"]) & (ys <= xs["hi80"])).mean()),
                          "cob90": float(((ys >= xs["lo90"]) & (ys <= xs["hi90"])).mean()),
                          "anchura80": float((xs["hi80"] - xs["lo80"]).mean()),
                          "cob80_motor": float(((ys >= xs["v_min_lo80"]) & (ys <= xs["v_min_hi80"])).mean()),
                          "cob90_motor": float(((ys >= xs["v_min_lo90_motor"]) & (ys <= xs["v_min_hi90_motor"])).mean()),
                          "por_encima_hi90": float((ys > xs["hi90"]).mean()), "por_debajo_lo90": float((ys < xs["lo90"]).mean()),
                          "fuera_de_limites": int(((xs["lo90"] < 0) | (xs["hi90"] > xs["gm"])).sum())})
    T = pd.DataFrame(filas)
    crit = cfg["criterios"]["f1"]["minutos_cobertura_recalibrada"]
    ok = lambda v, r: r[0] <= v <= r[1]  # noqa: E731
    agg = {}
    for seg, t in T.groupby("segmento"):
        w = t["n"]
        agg[seg] = {"cob80": float(np.average(t["cob80"], weights=w)), "cob90": float(np.average(t["cob90"], weights=w)),
                    "cob80_motor": float(np.average(t["cob80_motor"], weights=w)),
                    "cob90_motor": float(np.average(t["cob90_motor"], weights=w)),
                    "cumple_80_en_cada_corte": bool(all(ok(v, crit["0.8"]) for v in t["cob80"])),
                    "cumple_90_en_cada_corte": bool(all(ok(v, crit["0.9"]) for v in t["cob90"]))}
    cal_prod = _cal(E, cortes_r)
    res = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "criterio": crit,
           "por_corte": T.to_dict("records"), "agregado": agg,
           "puerta": bool(agg["global"]["cumple_80_en_cada_corte"] and agg["global"]["cumple_90_en_cada_corte"]),
           "producto": cal_prod}
    d = CE.dir_salida(cfg, "escenarios")
    (d / "minutos_calibracion.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    if progreso:
        progreso(T.round(3).to_string())
        progreso(json.dumps(agg, indent=1))
    return res
