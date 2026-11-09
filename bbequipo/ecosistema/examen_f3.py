"""F3 · examen del impacto cruzado y de las bajas: sello por métrica × banco (criterios congelados `criterios.f3_sellos`;
prerregistro `f3`, 09-11-2026).

Para cada banco (V-AUS, V-MID, V-TRANS), métrica (minutos, uso, cuota de tiro, % asistidas, pts/100) y corte:
  MAE ponderado del modelo frente a (i) Δ = 0 y (ii) redistribución proporcional; IC95 de la diferencia (base − modelo) por
  bootstrap de equipos-temporada; rango del 80 % conformal con los cortes anteriores y su cobertura.
Sello del banco: ALTA (mejora a (i) y (ii) con IC95 > 0 en cada corte de decisión y cobertura en rango), MEDIA (en el
agregado), BAJA (resto). Sello de la métrica = mín(V-AUS, máx(V-MID, V-TRANS)).
Valor de baja: ΔNet del equipo en V-AUS frente a (i), como la capa 4. EMD sembrado sobre los datos reales.
Salida: data/modelos/v4_1/bancos/examen_f3.json y filas por banco.
"""
from __future__ import annotations

import json
import pickle
import time

import numpy as np
import pandas as pd

from . import config as CE
from .bancos import DIR, EXPOSICION, METRICAS

ORDEN = {"BAJA": 0, "MEDIA": 1, "ALTA": 2}
UMBRAL_X = {"partidos": "partidos", "team_tsa_on": "team_fga_on", "team_fga_on": "team_fga_on", "fgm": "fgm", "poss_on": "poss_on"}


# =============================================================================================== línea base (ii)
def base_ii(C: pd.DataFrame) -> pd.DataFrame:
    """Redistribución proporcional (prerregistro f3.redistribucion_proporcional), con datos ≤ el movimiento."""
    C = C.copy()
    tot_m = C.groupby("evento")["base_minutos"].transform("sum")
    for c in ("ii_minutos", "ii_uso", "ii_cuota_tiro"):
        C[c] = 0.0
    for i, (mv, mk, uk, ck, gm, tm) in enumerate(zip(C["movers"], C["base_minutos"], C["base_uso"], C["base_cuota_tiro"],
                                                      C["gm"], tot_m)):
        dm = du = dc = 0.0
        for x in mv:
            sg = 1.0 if x["tipo"] == "baja" else -1.0
            m = x.get("m")
            m = 0.0 if m is None or not np.isfinite(m) else float(m)
            if tm > 0 and np.isfinite(mk):
                dm += sg * m * mk / tm
            for s_k, nombre, acc in ((uk, "uso", "du"), (ck, "cuota_tiro", "dc")):
                s_x = x.get(nombre)
                s_x = 20.0 if s_x is None or not np.isfinite(s_x) else float(s_x)
                if np.isfinite(s_k) and s_x < 100:
                    v = sg * (m / gm) * (s_x - 20.0) * s_k / (100.0 - s_x)
                    if acc == "du":
                        du += v
                    else:
                        dc += v
        C.iat[i, C.columns.get_loc("ii_minutos")] = dm
        C.iat[i, C.columns.get_loc("ii_uso")] = du
        C.iat[i, C.columns.get_loc("ii_cuota_tiro")] = dc
    with np.errstate(invalid="ignore", divide="ignore"):
        C["ii_pts100"] = np.where(C["base_uso"] > 0, C["base_pts100"] * C["ii_uso"] / C["base_uso"], 0.0)
    C["ii_pct_asistidas"] = 0.0
    return C


# =============================================================================================== intervalos conformales
def conformal(d: pd.DataFrame, cortes: list[int], col_y="obs", col_p="pred", col_w="w") -> pd.DataFrame:
    """q10/q90 del residuo de los cortes anteriores por tercil de peso (2021: en muestra)."""
    d = d.copy()
    d["lo80"], d["hi80"] = np.nan, np.nan
    for k, a in enumerate(cortes):
        sel = d["anio"] == a
        prev = d[d["anio"].isin(cortes[:k])] if k else d[sel]
        if len(prev) < 30 or not sel.any():
            continue
        r = (prev[col_y] - prev[col_p]).to_numpy(float)
        bordes = np.quantile(prev[col_w], [1 / 3, 2 / 3])
        bp = np.digitize(prev[col_w], bordes)
        q = {b: (np.quantile(r[bp == b], .10), np.quantile(r[bp == b], .90)) if (bp == b).sum() >= 20 else
             (np.quantile(r, .10), np.quantile(r, .90)) for b in range(3)}
        bs = np.digitize(d.loc[sel, col_w], bordes)
        d.loc[sel, "lo80"] = d.loc[sel, col_p].to_numpy() + np.array([q[b][0] for b in bs])
        d.loc[sel, "hi80"] = d.loc[sel, col_p].to_numpy() + np.array([q[b][1] for b in bs])
    return d


# =============================================================================================== MAE ponderado y bootstrap
def mae_boot(d: pd.DataFrame, cols: list[str], B: int, semilla: int) -> dict:
    """MAE ponderado de cada predictor y diferencias (base − modelo) con IC95 por equipos-temporada (conteos multinomiales)."""
    cl = pd.factorize(d["anio"].astype(str) + "|" + d["liga"] + "|" + d["team"].astype(str))[0]
    ncl = cl.max() + 1
    w = d["w"].to_numpy(float)
    W = np.bincount(cl, weights=w, minlength=ncl)
    S = {c: np.bincount(cl, weights=w * np.abs(d["obs"].to_numpy(float) - d[c].to_numpy(float)), minlength=ncl) for c in cols}
    rng = np.random.default_rng(semilla)
    cnt = rng.multinomial(ncl, np.full(ncl, 1.0 / ncl), size=B).astype(float)
    tw = cnt @ W
    mb = {c: (cnt @ S[c]) / tw for c in cols}
    out = {"n": int(len(d)), "equipos_temporada": int(ncl)}
    for c in cols:
        out[f"mae_{c}"] = float(S[c].sum() / W.sum())
    for b in [c for c in cols if c != "pred"]:
        dd = mb[b] - mb["pred"]
        out[f"mejora_{b}"] = {"diferencia": out[f"mae_{b}"] - out["mae_pred"], "ic95": [float(np.quantile(dd, .025)), float(np.quantile(dd, .975))],
                              "ee": float(dd.std())}
    return out


def tabla_metrica(C: pd.DataFrame, m: str, minimos: dict) -> pd.DataFrame:
    x = UMBRAL_X[EXPOSICION[m]]
    d = C[C[f"obs_{m}"].notna() & C[f"pred_{m}"].notna() & (C[f"xmin_{m}"] >= float(minimos.get(x, 0)))]
    return pd.DataFrame({"anio": d["anio"], "liga": d["liga"], "team": d["team"], "banco": d["banco"], "evento": d["evento"],
                         "persona_id": d["persona_id"], "obs": d[f"obs_{m}"], "pred": d[f"pred_{m}"], "i": 0.0,
                         "ii": d[f"ii_{m}"], "w": d[f"w_{m}"]})


def sello(res_cortes: dict, agg: dict, cob: float, rango) -> str:
    ok = lambda r: r["mejora_i"]["ic95"][0] > 0 and r["mejora_ii"]["ic95"][0] > 0  # noqa: E731
    en = rango[0] <= cob <= rango[1]
    if all(ok(r) for r in res_cortes.values()) and en:
        return "ALTA"
    if ok(agg) and en:
        return "MEDIA"
    return "BAJA"


def emd_sembrado(d: pd.DataFrame, base: str, kappas, replicas: int, B: int, semilla: int) -> list[dict]:
    """y* = b + κ·(p − b) + e*, e* = residuos reales de la línea base permutados dentro de corte (prerregistro f3.potencia)."""
    rng = np.random.default_rng(semilla)
    out = []
    b = d[base].to_numpy(float); p = d["pred"].to_numpy(float); e = d["obs"].to_numpy(float) - b
    an = d["anio"].to_numpy()
    for k in kappas:
        det = []
        for r in range(replicas):
            es = e.copy()
            for a in np.unique(an):
                ii = np.flatnonzero(an == a)
                es[ii] = e[rng.permutation(ii)]
            x = d.copy()
            x["obs"] = b + k * (p - b) + es
            det.append(mae_boot(x, ["pred", base], B, int(rng.integers(1e9)))[f"mejora_{base}"]["ic95"][0] > 0)
        out.append({"kappa": k, "deteccion": float(np.mean(det)), "replicas": replicas})
    return out


# =============================================================================================== orquestación
def ejecutar(cfg: dict, progreso=print) -> dict:
    t0 = time.time()
    cf, cc = cfg["f3"], cfg["criterios"]["f3_sellos"]
    rango = [float(x) for x in cfg["criterios"]["f2"]["cobertura_80"]]
    cortes = [int(c) for c in cfg["comunes"]["cortes"]]
    dec = [int(c) for c in cfg["comunes"]["cortes_decision"]]
    B = int(cfg["comunes"]["bootstrap"])
    sem = int(cfg["comunes"]["semilla_bootstrap"])
    R = [pickle.loads((DIR / f"corte_{a}.pkl").read_bytes()) for a in cortes if (DIR / f"corte_{a}.pkl").exists()]
    C = base_ii(pd.concat([r["companeros"] for r in R], ignore_index=True))
    E = pd.concat([r["equipos"] for r in R], ignore_index=True)
    minimos = cf["minimo_exposicion"]
    res = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "criterios": cc,
           "eventos": E.groupby(["banco", "anio"]).size().unstack(fill_value=0).to_dict("index"),
           "filas_companeros": C.groupby("banco").size().to_dict(), "metricas": {}, "sello_final": {}}
    filas_out = []
    for m in METRICAS:
        res["metricas"][m] = {}
        for banco in ("V-AUS", "V-MID", "V-TRANS"):
            d = tabla_metrica(C[C["banco"] == banco], m, minimos)
            if d["anio"].isin(dec).sum() < 50:
                res["metricas"][m][banco] = {"n": int(len(d)), "sello": "BAJA", "motivo": "muestra insuficiente"}
                continue
            d = conformal(d, cortes)
            dd = d[d["anio"].isin(dec)]
            agg = mae_boot(dd, ["pred", "i", "ii"], B, sem)
            por = {str(a): mae_boot(dd[dd["anio"] == a], ["pred", "i", "ii"], B, sem + a) for a in dec if (dd["anio"] == a).sum() >= 30}
            cob = float(((dd["obs"] >= dd["lo80"]) & (dd["obs"] <= dd["hi80"])).mean())
            s = sello(por, agg, cob, rango)
            r = {"n": int(len(dd)), "agregado": agg, "por_corte": por, "cobertura_80": cob,
                 "media_obs": float(np.average(dd["obs"], weights=dd["w"])), "media_pred": float(np.average(dd["pred"], weights=dd["w"])),
                 "media_ii": float(np.average(dd["ii"], weights=dd["w"])),
                 "frac_rango_incluye_0": float(((dd["lo80"] <= 0) & (dd["hi80"] >= 0)).mean()),
                 "spearman_pred_obs": float(dd[["pred", "obs"]].rank().corr().iloc[0, 1]), "sello": s}
            base = "ii" if m != "pct_asistidas" else "i"
            r["emd_sembrado"] = {"frente_a": base, "curva": emd_sembrado(dd, base, [0.25, 0.5, 1.0], int(cfg["potencia"]["replicas_minimas"]),
                                                                         300, sem + 17)}
            res["metricas"][m][banco] = r
            filas_out.append(d.assign(metrica=m))
            if progreso:
                progreso(f"  F3 {m} {banco}: n {len(dd)} · MAE modelo {agg['mae_pred']:.3f} (i) {agg['mae_i']:.3f} (ii) {agg['mae_ii']:.3f} · "
                         f"cob {cob:.3f} · {s} · {time.time() - t0:.0f} s", flush=True)
        sv = res["metricas"][m]
        s_aus = sv.get("V-AUS", {}).get("sello", "BAJA")
        s_otro = max((sv.get(b, {}).get("sello", "BAJA") for b in ("V-MID", "V-TRANS")), key=ORDEN.get)
        res["sello_final"][m] = min(s_aus, s_otro, key=ORDEN.get)
    for m in cf["candidatos_sin_via"]:
        res["sello_final"][m] = "BAJA (sin vía de predicción examinada, §3.4)"
    # Valor de baja: ΔNet del equipo en V-AUS (y, informados, V-MID y V-TRANS)
    res["delta_net"] = {}
    for banco in ("V-AUS", "V-MID", "V-TRANS"):
        e = E[(E["banco"] == banco) & E["net_obs"].notna() & (E["poss_min"] >= float(minimos["posesiones"]))]
        d = pd.DataFrame({"anio": e["anio"], "liga": e["liga"], "team": e["team"], "obs": e["net_obs"], "pred": e["pred_net"],
                          "i": 0.0, "w": e["w_net"]})
        if d["anio"].isin(dec).sum() < 50:
            continue
        d = conformal(d, cortes)
        dd = d[d["anio"].isin(dec)]
        agg = mae_boot(dd, ["pred", "i"], B, sem + 31)
        cob = float(((dd["obs"] >= dd["lo80"]) & (dd["obs"] <= dd["hi80"])).mean())
        res["delta_net"][banco] = {"n": int(len(dd)), "agregado": agg, "cobertura_80": cob,
                                   "por_corte": {str(a): mae_boot(dd[dd["anio"] == a], ["pred", "i"], B, sem + a) for a in dec},
                                   "spearman_pred_obs": float(dd[["pred", "obs"]].rank().corr().iloc[0, 1]),
                                   "media_obs": float(np.average(dd["obs"], weights=dd["w"])),
                                   "media_pred": float(np.average(dd["pred"], weights=dd["w"])),
                                   "emd_sembrado": emd_sembrado(dd, "i", [0.25, 0.5, 1.0], int(cfg["potencia"]["replicas_minimas"]), 300, sem + 41),
                                   "pasa_como_capa4": bool(agg["mejora_i"]["ic95"][0] > 0 and rango[0] <= cob <= rango[1])}
    res["valor_de_baja"] = {"examen": "V-AUS frente a Δ = 0 (criterios de la capa 4)",
                            "pasa": bool(res["delta_net"].get("V-AUS", {}).get("pasa_como_capa4", False))}
    res["segundos"] = round(time.time() - t0)
    d = CE.dir_salida(cfg, "bancos")
    (d / "examen_f3.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    if filas_out:
        pd.concat(filas_out, ignore_index=True).round(4).to_csv(d / "filas_f3.csv.gz", index=False)
    E.round(4).to_csv(d / "eventos_f3.csv.gz", index=False)
    return res
