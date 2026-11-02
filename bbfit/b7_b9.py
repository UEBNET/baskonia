"""Evaluación del impacto posible de B7 y B9 (sin cambiar el simulador), sobre el examen temporal del simulador.

B7 · modelo supervisado directo sobre los fichajes: del registro de origen (métricas observadas y normalizadas,
     nivel L, minutos, rol, edad, posición), las ligas de origen y destino, el salto de nivel y la traducción
     normalizada, predecir directamente la producción en destino. Dos aprendices: gradient boosting (árboles,
     pérdida absoluta) y una red neuronal pequeña (MLP 64-32). Cortes anidados: para el corte t se entrena SÓLO con los
     fichajes de los cortes < t (el primero no se predice). Se compara con el motor (v) y con la línea base del Atlas
     (a) en los MISMOS casos.
B9 · minutos y producción en un solo modelo: cota superior de lo que ganaría la producción si el modelo conociera el
     error de minutos/rol. (1) correlación entre el error de minutos y el de producción; (2) «oráculo»: regresión
     del error de producción sobre el error de minutos y el cambio de rol real (ajustada con los cortes anteriores):
     lo que se reduciría el MAE si esa relación se pudiera explotar. Si la cota es pequeña, B9 no compensa.

    python -m bbfit b7-b9 [--etiqueta V31_inicio_adapt]  (con CERNO_SIMULADOR de la versión del examen)
"""
from __future__ import annotations

import json
import pickle

import numpy as np
import pandas as pd

from . import sim_insumos as SI
from . import validacion as V
from .roles import ROLES

METS = ["pts_p100", "ts_pct", "usg_pct", "ast_pct", "oreb_p100", "dreb_p100", "stl_p100", "blk_p100", "tov_pct"]
OBJETIVOS = ["pts_p100", "ts_pct", "ast_pct", "usg_pct"]


def registros_origen(e: pd.DataFrame, fuente: str) -> pd.DataFrame:
    filas = []
    for t in sorted(e["temporada_o"].unique()):
        f = SI.DIR_CACHE / f"corte_{t}_{fuente}.pkl"
        if not f.exists():
            continue
        reg = pickle.loads(f.read_bytes())[0]
        if "principal" in reg:
            reg = reg[reg["principal"].astype(bool)]
        reg = reg.sort_values("min_total", ascending=False).drop_duplicates("persona_id")
        cols = ["persona_id", "edad", "pos3", "min_pct", "gs_pct", "min_total", "L", "L_sd", "usg_tiro", "ts_tiro",
                "gti", "H_rol", "sigma"] + [f"{m}_obs" for m in METS] + [f"{m}_th" for m in METS]
        r = reg[[c for c in cols if c in reg]].copy()
        r["temporada_o"] = t
        filas.append(r)
    return pd.concat(filas, ignore_index=True)


def matriz(e: pd.DataFrame, reg: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    x = e.merge(reg, on=["persona_id", "temporada_o"], how="left", suffixes=("", "_reg"))
    num = [c for c in reg.columns if c not in ("persona_id", "temporada_o", "pos3")]
    num += ["d_nivel", "min_pct_o", "min_o"] + [f"v_{m}_trad" for m in METS if f"v_{m}_trad" in x]
    X = x[num].apply(pd.to_numeric, errors="coerce")
    for col, pref in (("liga_o", "o_"), ("liga_d", "d_"), ("pos3", "p_"), ("rol_o", "r_")):
        X = X.join(pd.get_dummies(x[col].astype(str), prefix=pref, dtype=float))
    return X, num


def _aprendices():
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.neural_network import MLPRegressor
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return {
        "gbm": lambda: HistGradientBoostingRegressor(loss="absolute_error", max_iter=400, learning_rate=0.05,
                                                     max_leaf_nodes=31, min_samples_leaf=40, l2_regularization=1.0,
                                                     random_state=20261102),
        "mlp": lambda: make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                                     MLPRegressor(hidden_layer_sizes=(64, 32), alpha=1e-2, learning_rate_init=1e-3,
                                                  max_iter=400, early_stopping=True, random_state=20261102)),
    }


def b7(e: pd.DataFrame, X: pd.DataFrame, min_prod: float) -> dict:
    cortes = sorted(e["corte"].unique())
    ok = (e["min_total_real"] >= min_prod).to_numpy()
    res = {}
    for m in OBJETIVOS:
        y = pd.to_numeric(e[f"{m}_real"], errors="coerce").to_numpy(float)
        preds = {k: np.full(len(e), np.nan) for k in _aprendices()}
        for k, t in enumerate(cortes[1:], 1):
            tr = e["corte"].isin(cortes[:k]).to_numpy() & ok & np.isfinite(y)
            te = (e["corte"] == t).to_numpy()
            for nombre, f in _aprendices().items():
                mdl = f().fit(X[tr], y[tr])
                preds[nombre][te] = mdl.predict(X[te])
        ev = ok & np.isfinite(y) & e["corte"].isin(cortes[1:]).to_numpy()
        fila = {"casos": int(ev.sum())}
        for nombre, p in {**preds, "motor": e[f"v_{m}_pred"].to_numpy(float),
                          "atlas": e[f"a_{m}_pred"].to_numpy(float)}.items():
            s = ev & np.isfinite(p)
            fila[f"mae_{nombre}"] = float(np.abs(p[s] - y[s]).mean())
        # mezcla motor + gbm (¿aporta información nueva?)
        p = 0.5 * (preds["gbm"] + e[f"v_{m}_pred"].to_numpy(float))
        s = ev & np.isfinite(p)
        fila["mae_mezcla_motor_gbm"] = float(np.abs(p[s] - y[s]).mean())
        fila["mejora_gbm_frente_motor_%"] = 100 * (fila["mae_gbm"] / fila["mae_motor"] - 1)
        fila["mejora_mlp_frente_motor_%"] = 100 * (fila["mae_mlp"] / fila["mae_motor"] - 1)
        fila["mejora_gbm_frente_atlas_%"] = 100 * (fila["mae_gbm"] / fila["mae_atlas"] - 1)
        res[m] = fila
    return res


def b9(e: pd.DataFrame, min_prod: float) -> dict:
    cortes = sorted(e["corte"].unique())
    ok = (e["min_total_real"] >= min_prod) & e["eval_min"].astype(bool)
    em = (e["v_min_pred"] - e["min_real"]).to_numpy(float)
    idx = {r: i for i, r in enumerate(ROLES)}
    dr = (e["rol_real"].map(idx) - e["rol_o"].map(idx)).to_numpy(float)
    res = {}
    for m in OBJETIVOS:
        ep = (e[f"v_{m}_pred"] - e[f"{m}_real"]).to_numpy(float)
        s = ok.to_numpy() & np.isfinite(ep) & np.isfinite(em)
        rho = float(np.corrcoef(em[s], ep[s])[0, 1])
        # oráculo con cortes anidados: ep ≈ a + b·em + c·Δrol (+ |em|) ajustado con los cortes anteriores
        mejora, base = [], []
        for k, t in enumerate(cortes[1:], 1):
            tr = s & e["corte"].isin(cortes[:k]).to_numpy() & np.isfinite(dr)
            te = s & (e["corte"] == t).to_numpy() & np.isfinite(dr)
            A = lambda i: np.c_[np.ones(i.sum()), em[i], dr[i], np.abs(em[i])]  # noqa: E731
            coef, *_ = np.linalg.lstsq(A(tr), ep[tr], rcond=None)
            corr = ep[te] - A(te) @ coef
            mejora.append(np.abs(corr)), base.append(np.abs(ep[te]))
        mb, mo = float(np.concatenate(base).mean()), float(np.concatenate(mejora).mean())
        res[m] = {"casos": int(s.sum()), "correlacion_error_min_error_prod": rho,
                  "mae_motor": mb, "mae_oraculo_con_minutos_reales": mo, "cota_mejora_%": 100 * (mo / mb - 1)}
    return res


def main(etiqueta: str | None = None, progreso=print) -> dict:
    cfg = V.cfg_sim()
    fuente, esc, ad = V.ruta_produccion(cfg)
    etiqueta = etiqueta or V._etiqueta(fuente, esc, ad)
    e = pd.read_csv(V.DIR_VAL / etiqueta / "predicciones.csv.gz", low_memory=False)
    e = e[e["error"].isna()].reset_index(drop=True) if "error" in e else e
    reg = registros_origen(e, fuente)
    X, _ = matriz(e, reg)
    mp = float(cfg["validacion"]["min_minutos_produccion"])
    out = {"etiqueta": etiqueta, "fichajes": int(len(e)), "cortes": sorted(e["corte"].unique()),
           "B7": b7(e, X, mp), "B9": b9(e, mp)}
    dest = SI.DIR_MOD / "simulador" / "v3_2"            # la evaluación se guarda con la v3.2 (sobre el examen dado)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / f"evaluacion_b7_b9_{etiqueta}.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    if progreso:
        progreso(json.dumps(out, indent=1, default=float))
    return out
