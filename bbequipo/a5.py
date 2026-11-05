"""A5 · Producción no lineal en minutos y rol (encargo §9.6; puerta §11.6). Generaliza el acoplamiento B9 de la v3.3
(Δy = b·Δmin + c·Δrol) con la MISMA maquinaria del examen v3.2/v3.3 (cortes anidados, fuente V32_corte, escenario «rol
asignado»):

    y_real − ŷ = s(Δmin) + c·Δrol + δ[rol_origen → rol_destino] + ε

* s(Δmin): spline lineal a trozos, monótono-libre (sin signo ni linealidad impuestos), 3 nudos en los cuantiles 0,25 /
  0,5 / 0,75 de Δmin de los casos de ajuste.
* c·Δrol: la recta ordinal de B9 (Δrol = índice del rol real − índice esperado).
* δ[o → d]: matriz 5 × 5 de desviaciones por par (rol de origen → rol de destino) contraída jerárquicamente hacia la recta
  (δ ~ N(0, τ²), τ² por Bayes empírico, método de momentos): un par con pocos casos se queda en la recta.
* Carga (diagnóstico): pendiente dentro de jugador de TS% por partido frente a minutos por partido (proxy de fatiga), por
  temporada; si es estable (mismo signo en todas las temporadas e IC95 conjunto que excluye 0) entra como covariable
  (minutos absolutos de destino por encima de 30') en una variante de A5 que también se examina.
* Puerta §11.6: frente a B9 lineal (reajustado con los mismos insumos), en cortes anidados: MAE de pts/100 y de TS% con
  IC90 que excluya 0 en al menos una sin empeorar la otra más de un +0,5 %; contracción efectiva (ningún par con < 30 casos
  se aleja de la recta más de 1 error típico). k_β = k_c = 0 de la v3.2 no se tocan.
Salidas: data/modelos/v4_0/equipo/a5/.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C

ROLES = ["RESIDUAL", "PROFUNDIDAD", "ROTACION", "TITULAR", "GO_TO_GUY"]
IDX = {r: i for i, r in enumerate(ROLES)}
SEMILLA = 20261105


def dir_salida(cfg: dict) -> Path:
    d = C.RAIZ / cfg["f4"]["salida"] / "a5"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _v():
    cfg = C.cargar()
    os.environ.setdefault("CERNO_SIMULADOR", cfg["insumos"].get("simulador_env_corte", "v32"))
    from bbfit import v32, v33  # noqa: E402
    return v32, v33


# =============================================================================================== modelo
def _base_spline(dm: np.ndarray, nudos: np.ndarray) -> np.ndarray:
    return np.c_[dm, np.clip(dm[:, None] - nudos[None, :], 0, None)]


class A5:
    """Ajuste de un efecto (métrica) sobre el residuo de la producción predicha."""

    def __init__(self, cfg_a5: dict, con_carga: bool = False):
        self.cfg = cfg_a5
        self.con_carga = con_carga
        self.nudos = None; self.coef_lin = None; self.delta = {}; self.tau2 = None; self.sigma2 = None; self.pares = {}

    def _X(self, dm, drol, min_abs):
        X = [_base_spline(dm, self.nudos), drol[:, None]]
        if self.con_carga:
            X.append(np.clip(min_abs - 30.0, 0, None)[:, None])
        return np.hstack(X)

    def ajustar(self, r: np.ndarray, dm: np.ndarray, drol: np.ndarray, rol_o: np.ndarray, rol_d: np.ndarray, min_abs: np.ndarray):
        ok = np.isfinite(r) & np.isfinite(dm) & np.isfinite(drol)
        r, dm, drol, rol_o, rol_d, min_abs = r[ok], dm[ok], drol[ok], rol_o[ok], rol_d[ok], min_abs[ok]
        q = [float(x) for x in self.cfg["minutos"]["cuantiles_nudos"]]
        self.nudos = np.quantile(dm, q)
        X = self._X(dm, drol, min_abs)
        pares = np.array([f"{a}>{b}" for a, b in zip(rol_o, rol_d)])
        offset = np.zeros(len(r))
        for _ in range(3):                                      # alternancia: parte lineal ↔ desviaciones por par
            A = np.c_[X, np.ones(len(r))]
            lam = 1e-3 * len(r)
            coef = np.linalg.solve(A.T @ A + lam * np.eye(A.shape[1]), A.T @ (r - offset))
            res = r - A @ coef
            self.sigma2 = float(np.var(res))
            med = {}; n = {}
            for p in np.unique(pares):
                s = pares == p
                med[p] = float(res[s].mean()); n[p] = int(s.sum())
            # Bayes empírico (momentos): τ² = max(0, var(δ̂) − media(σ²/n))
            d_hat = np.array(list(med.values())); nn = np.array(list(n.values()), float)
            self.tau2 = float(max(np.var(d_hat) - np.mean(self.sigma2 / nn), 1e-6))
            self.delta = {p: med[p] * n[p] / (n[p] + self.sigma2 / self.tau2) for p in med}
            self.pares = {p: {"n": n[p], "delta_crudo": med[p], "delta": self.delta[p],
                              "se": float(np.sqrt(self.sigma2 / n[p]))} for p in med}
            offset = np.array([self.delta[p] for p in pares])
        self.coef_lin = coef
        return self

    def predecir(self, dm, drol, rol_o, rol_d, min_abs) -> np.ndarray:
        X = np.c_[self._X(np.nan_to_num(dm), np.nan_to_num(drol), np.nan_to_num(min_abs)), np.ones(len(dm))]
        d = np.array([self.delta.get(f"{a}>{b}", 0.0) for a, b in zip(rol_o, rol_d)])
        return X @ self.coef_lin + d

    def exportable(self) -> dict:
        return {"nudos": self.nudos.tolist(), "coef_spline": self.coef_lin[:4].tolist(), "c_rol": float(self.coef_lin[4]),
                "coef_carga": float(self.coef_lin[5]) if self.con_carga else None, "intercepto": float(self.coef_lin[-1]),
                "tau2": self.tau2, "sigma2": self.sigma2, "pares": self.pares}


def ajustar_b9_lineal(r, dm, drol):
    ok = np.isfinite(r) & np.isfinite(dm) & np.isfinite(drol)
    A = np.c_[dm[ok], drol[ok]]
    coef, *_ = np.linalg.lstsq(A, r[ok], rcond=None)
    return {"b_min": float(coef[0]), "c_rol": float(coef[1]), "casos": int(ok.sum())}


# =============================================================================================== diagnóstico de carga
def diagnostico_carga(cfg: dict, temporadas: list[str], progreso=print) -> dict:
    """Pendiente dentro de jugador de TS% (por partido) frente a minutos por partido, por temporada: jugadores con ≥ 15
    partidos con ≥ 8 minutos; TS% y minutos centrados por jugador-temporada; pendiente ponderada por intentos; IC95 por
    bootstrap de jugadores."""
    rng = np.random.default_rng(SEMILLA)
    out = {}
    for t in temporadas:
        p = C.RAIZ / "data/modelos/roles/partidos_jugador" / f"{t}.csv.gz"
        if not p.exists():
            continue
        d = pd.read_csv(p, usecols=["liga", "persona_id", "team_id", "min", "ts_pct", "fga", "fta", "jugo"], low_memory=False)
        d = d[(d["jugo"].astype(str).isin(["True", "1", "true"])) & (d["min"] >= 8) & d["ts_pct"].notna()]
        d["int"] = d["fga"] + 0.44 * d["fta"]
        d = d[d["int"] > 0]
        g = d.groupby(["liga", "persona_id", "team_id"])
        d = d[g["min"].transform("size") >= 15].copy()
        g = d.groupby(["liga", "persona_id", "team_id"])
        d["dm"] = d["min"] - g["min"].transform("mean"); d["dts"] = d["ts_pct"] - g["ts_pct"].transform("mean")
        w = d["int"].to_numpy(float); x = d["dm"].to_numpy(float); y = d["dts"].to_numpy(float)
        pend = float(np.sum(w * x * y) / np.sum(w * x * x))
        jug = (d["liga"] + "|" + d["persona_id"].astype(str) + "|" + d["team_id"].astype(str)).to_numpy()
        u, inv = np.unique(jug, return_inverse=True)
        sxy = np.bincount(inv, w * x * y); sxx = np.bincount(inv, w * x * x)
        bs = []
        for _ in range(500):
            ii = rng.integers(0, len(u), len(u)); bs.append(sxy[ii].sum() / sxx[ii].sum())
        out[t] = {"jugadores": int(len(u)), "partidos": int(len(d)), "pendiente_ts_por_minuto": pend,
                  "ic95": [float(np.quantile(bs, .025)), float(np.quantile(bs, .975))]}
        if progreso:
            progreso(f"    carga {t}: {len(u)} jugadores · TS% por minuto extra {pend:+.4f} {np.round(out[t]['ic95'], 4).tolist()}", flush=True)
    signos = [np.sign(v["pendiente_ts_por_minuto"]) for v in out.values()]
    excl = [v["ic95"][0] > 0 or v["ic95"][1] < 0 for v in out.values()]
    estable = bool(out) and len(set(signos)) == 1 and all(excl)
    return {"por_temporada": out, "estable": estable, "regla": "mismo signo en todas las temporadas e IC95 que excluye 0 en cada una"}


# =============================================================================================== examen §11.6
def main(cfg: dict, progreso=print) -> dict:
    v32, v33 = _v()
    t0 = time.time()
    a5c = cfg["f4"]["a5"]
    out_dir = dir_salida(cfg)
    c32 = v32.cfg()
    EE = v32.cargar_ejecuciones(c32)
    E = EE["V32_corte"]
    e_all = E["completo"].reset_index(drop=True)
    cortes = sorted(e_all["corte"].unique())
    mets = [m for m in a5c["metricas"] if f"{m}_real" in e_all]
    temps_carga = [t for t in cfg["perfil"]["temporadas"] if t <= cortes[-1]]
    carga = diagnostico_carga(cfg, temps_carga, progreso)
    variantes = {"a5": False} | ({"a5_carga": True} if carga["estable"] else {})
    acum = {k: {m: [] for m in mets} for k in ["b9"] + list(variantes)}
    ecs = []
    coefs = {}
    for k, t in enumerate(cortes):
        if k == 0:
            continue
        prev_c = cortes[:k]
        dec = v32.decidir_dos_fuentes(EE, prev_c, c32)
        e_t = e_all[e_all["corte"] == t].reset_index(drop=True)
        prev = e_all[e_all["corte"].isin(prev_c)].reset_index(drop=True)
        rp = v32.aplicar(prev, E, dec, None, c32, t, cortes)
        rt = v32.aplicar(e_t, E, dec, prev, c32, t, cortes)
        ep, et = rp["e"], rt["e"]
        # ajuste (cortes anteriores): Δmin = real − previsto; Δrol = real − esperado
        dm_p = ep["min_real"].to_numpy(float) - rp["min"]["pred"].to_numpy(float)
        dr_p = v33._delta_rol(ep)
        ok_p = v32.ok_produccion(ep) & ep["eval_min"].to_numpy(bool) & ep["rol_real"].notna().to_numpy()
        # examen (corte t), escenario «rol asignado»: minutos de la franja del rol real (cortes anteriores) − previstos
        fr = v33.franja(prev)
        dm_t = v33.min_franja(et, fr) - rt["min"]["pred"].to_numpy(float)
        dr_t = v33._delta_rol(et)
        ok_t = v32.ok_produccion(et) & et["eval_min"].to_numpy(bool) & et["rol_real"].notna().to_numpy()
        min_abs_p = ep["min_real"].to_numpy(float); min_abs_t = v33.min_franja(et, fr)
        coefs[t] = {}
        for m in mets:
            r_p = ep[f"{m}_real"].to_numpy(float) - rp["prod"][m]["pred"].to_numpy(float)
            y_t = et[f"{m}_real"].to_numpy(float); p_t = rt["prod"][m]["pred"].to_numpy(float)
            b9 = ajustar_b9_lineal(r_p[ok_p], dm_p[ok_p], dr_p[ok_p])
            pred_b9 = p_t + np.nan_to_num(b9["b_min"] * dm_t + b9["c_rol"] * dr_t)
            acum["b9"][m].append(pd.DataFrame({"y": y_t, "pred": pred_b9, "ok": ok_t}))
            coefs[t][m] = {"b9": b9}
            for nombre, con_carga in variantes.items():
                mod = A5(a5c, con_carga).ajustar(r_p[ok_p], dm_p[ok_p], dr_p[ok_p], ep["rol_o"].to_numpy(object)[ok_p],
                                                  ep["rol_real"].to_numpy(object)[ok_p], min_abs_p[ok_p])
                pred = p_t + mod.predecir(dm_t, dr_t, et["rol_o"].to_numpy(object), et["rol_real"].to_numpy(object), min_abs_t)
                acum[nombre][m].append(pd.DataFrame({"y": y_t, "pred": pred, "ok": ok_t}))
                coefs[t][m][nombre] = mod.exportable()
        ecs.append(et)
        if progreso:
            progreso(f"  A5 corte {t}: {int(ok_t.sum())} casos de examen · ajuste con {int(ok_p.sum())}", flush=True)
    ec = pd.concat(ecs, ignore_index=True)
    res = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "cortes_examen": cortes[1:], "carga": carga,
           "metricas": {}, "coeficientes_por_corte": coefs}
    for nombre in variantes:
        res["metricas"][nombre] = {}
        for m in mets:
            yb = pd.concat(acum["b9"][m], ignore_index=True); ya = pd.concat(acum[nombre][m], ignore_index=True)
            y = yb["y"].to_numpy(float); ok = yb["ok"].to_numpy(bool) & np.isfinite(y)
            xa, xb = np.abs(ya["pred"].to_numpy(float) - y), np.abs(yb["pred"].to_numpy(float) - y)
            d, lo, hi = v32.boot_cociente(ec, xa, xb, ok, 1000, SEMILLA, nivel=0.9)
            res["metricas"][nombre][m] = {"casos": int((ok & np.isfinite(xa) & np.isfinite(xb)).sum()), "mae_b9": float(np.nanmean(xb[ok])),
                                           "mae_a5": float(np.nanmean(xa[ok])), "cociente_menos_1": d, "ic90": [lo, hi]}
    # contracción efectiva: pares con < 30 casos a ≤ 1 error típico de la recta (último corte, variante a5)
    ult = coefs[cortes[-1]]
    viol = []
    for m in mets:
        for p, v in ult[m]["a5"]["pares"].items():
            if v["n"] < int(a5c["transicion_rol"]["min_casos_par_aviso"]) and abs(v["delta"]) > v["se"]:
                viol.append({"metrica": m, "par": p, "n": v["n"], "delta": v["delta"], "se": v["se"]})
    res["contraccion"] = {"pares_pocos_casos_fuera_de_1se": viol, "ok": len(viol) == 0}
    # puerta §11.6
    def puerta(nombre):
        pts, ts = res["metricas"][nombre]["pts_p100"], res["metricas"][nombre]["ts_pct"]
        mejora = (pts["ic90"][1] < 0) or (ts["ic90"][1] < 0)
        no_empeora = pts["cociente_menos_1"] <= 0.005 and ts["cociente_menos_1"] <= 0.005
        return {"mejora_alguna_ic90": bool(mejora), "no_empeora_otra_mas_de_0_5pct": bool(no_empeora), "contraccion_ok": res["contraccion"]["ok"],
                "pasa": bool(mejora and no_empeora and res["contraccion"]["ok"])}
    res["puerta_11_6"] = {k: puerta(k) for k in variantes}
    # la covariable de carga sólo se adopta si mejora a la variante simple con IC90 que excluya 0 en pts/100 (parsimonia)
    elegida = "a5" if res["puerta_11_6"]["a5"]["pasa"] else None
    if "a5_carga" in variantes and res["puerta_11_6"]["a5_carga"]["pasa"]:
        ya = pd.concat(acum["a5"]["pts_p100"], ignore_index=True); yc = pd.concat(acum["a5_carga"]["pts_p100"], ignore_index=True)
        y = ya["y"].to_numpy(float); ok = ya["ok"].to_numpy(bool) & np.isfinite(y)
        d, lo, hi = v32.boot_cociente(ec, np.abs(yc["pred"].to_numpy(float) - y), np.abs(ya["pred"].to_numpy(float) - y), ok, 1000, SEMILLA, nivel=0.9)
        res["carga_frente_a_a5"] = {"cociente_menos_1_pts": d, "ic90": [lo, hi], "adoptar": bool(hi < 0)}
        if hi < 0:
            elegida = "a5_carga"
    # por métrica: A5 (variante elegida) donde no empeora a B9 más de un +0,5 % con IC90; B9 lineal en las demás
    por_metrica = {}
    if elegida:
        for m in mets:
            x = res["metricas"][elegida][m]
            por_metrica[m] = elegida if x["ic90"][0] <= 0.005 and x["cociente_menos_1"] <= 0.005 else "b9_lineal"
    else:
        por_metrica = {m: "b9_lineal" for m in mets}
    res["decisiones"] = {"publicar": elegida or "b9_lineal", "por_metrica": por_metrica,
                         "regla": "§11.6; si ninguna variante pasa, se conserva B9 lineal; la covariable de carga sólo si mejora a A5 simple con IC90 < 0; "
                                  "por métrica, B9 donde A5 empeora más de un +0,5 % (IC90)"}
    res["tiempo_s"] = round(time.time() - t0)
    (out_dir / "resumen_a5.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    if progreso:
        for k in variantes:
            progreso(f"  A5 [{k}]: pts/100 {res['metricas'][k]['pts_p100']} · TS% {res['metricas'][k]['ts_pct']} · puerta {res['puerta_11_6'][k]}", flush=True)
        progreso(f"  A5 decisión: {res['decisiones']} · {res['tiempo_s']} s", flush=True)
    return res


# =============================================================================================== producto
def exportar(cfg: dict, progreso=print) -> dict:
    """A5 para producción: coeficientes ajustados con TODOS los cortes del examen v3.2 (misma preparación que el examen), por
    métrica según la decisión (`a5/resumen_a5.json → decisiones.por_metrica`): A5 (variante elegida) o B9 lineal."""
    v32, v33 = _v()
    a5c = cfg["f4"]["a5"]
    out_dir = dir_salida(cfg)
    res = json.loads((out_dir / "resumen_a5.json").read_text(encoding="utf-8"))
    dec = res["decisiones"]
    c32 = v32.cfg()
    EE = v32.cargar_ejecuciones(c32); E = EE["V32_corte"]
    e_all = E["completo"].reset_index(drop=True)
    cortes = sorted(e_all["corte"].unique())
    d_f = v32.decidir_dos_fuentes(EE, cortes, c32)
    r = v32.aplicar(e_all, E, d_f, None, c32, "final", cortes + ["final"])
    e = r["e"]
    dm = e["min_real"].to_numpy(float) - r["min"]["pred"].to_numpy(float)
    dr = v33._delta_rol(e)
    ok = v32.ok_produccion(e) & e["eval_min"].to_numpy(bool) & e["rol_real"].notna().to_numpy()
    min_abs = e["min_real"].to_numpy(float)
    coef = {}
    for m in a5c["metricas"]:
        if f"{m}_real" not in e:
            continue
        rr = e[f"{m}_real"].to_numpy(float) - r["prod"][m]["pred"].to_numpy(float)
        eleccion = dec["por_metrica"].get(m, "b9_lineal")
        b9 = ajustar_b9_lineal(rr[ok], dm[ok], dr[ok])
        if eleccion == "b9_lineal":
            coef[m] = {"modelo": "b9_lineal", **b9}
        else:
            mod = A5(a5c, con_carga=(eleccion == "a5_carga")).ajustar(rr[ok], dm[ok], dr[ok], e["rol_o"].to_numpy(object)[ok],
                                                                      e["rol_real"].to_numpy(object)[ok], min_abs[ok])
            coef[m] = {"modelo": eleccion, **mod.exportable(), "b9_referencia": b9}
    doc = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "casos": int(ok.sum()), "cortes": cortes,
           "formula": "y − ŷ = s(Δmin) + c·Δrol + δ[rol_o → rol_d] (+ coef_carga·max(min_destino − 30, 0)); B9: b·Δmin + c·Δrol",
           "franja_minutos": v33.franja(e_all), "coeficientes": coef}
    (out_dir / "coeficientes_producto_a5.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    if progreso:
        progreso(f"  A5 producto: {len(coef)} métricas · {int(ok.sum())} casos", flush=True)
    return doc


def aplicar(coef_m: dict, dmin: np.ndarray, drol: np.ndarray, rol_o, rol_d, min_dest: np.ndarray) -> np.ndarray:
    """Corrección de producción (unidades de la métrica) para un fichaje: A5 o B9 según `coef_m`."""
    dmin, drol, min_dest = np.nan_to_num(np.asarray(dmin, float)), np.nan_to_num(np.asarray(drol, float)), np.nan_to_num(np.asarray(min_dest, float))
    if coef_m["modelo"] == "b9_lineal":
        return coef_m["b_min"] * dmin + coef_m["c_rol"] * drol
    X = np.c_[_base_spline(dmin, np.array(coef_m["nudos"])), drol[:, None]]
    out = X @ np.r_[coef_m["coef_spline"], coef_m["c_rol"]] + coef_m["intercepto"]
    if coef_m.get("coef_carga") is not None:
        out = out + coef_m["coef_carga"] * np.clip(min_dest - 30.0, 0, None)
    pares = coef_m["pares"]
    out = out + np.array([pares.get(f"{a}>{b}", {}).get("delta", 0.0) for a, b in zip(rol_o, rol_d)])
    return out
