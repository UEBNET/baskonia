"""F0.3 · Benchmark de decisión sobre la v4.0 REAL (sustituye al informe «CERNO_Benchmark-v4.0_Plan-v4.1.md», que evaluó la
rama main: simulador v2, Índice Fit, ADAPT%). Sólo lee exámenes ya guardados de la v4.0 y de la v3.2/v3.3 (sin fuga: cortes
≤ t); no reajusta ningún modelo.

Bloques (cortes de decisión 2022–2024; segmentos «elite_club» = EuroLeague + EuroCup + ACB, y «global»):
  A. NIVEL CERNO: Spearman(NC₁, percentil realizado), ordenación top-k (precisión@k frente al azar k/n y percentil
     realizado medio del top-k), cobertura del rango del 80 %. Con «rol oráculo»: C_oráculo = (minutos reales de t+1 /
     minutos del partido) × pts/100 predichos (el analista fija los minutos y el rol reales); se compara la ordenación de
     C_pred y de C_oráculo frente a C realizada.
  B. IMPACTO frente al on/off del fichaje: Spearman(IM, percentil on/off) y frente al aditivo (β × minutos); top-k.
  C. ΔNet de equipo (capa 4): MAE frente a persistencia y aditivo, Spearman, cobertura del 80 %, y con los minutos reales
     de t+1 (rol oráculo de la F4).
  D. Límites físicos de los intervalos de minutos del motor v3.3 (examen por cortes y producto): ¿alguno fuera de
     [0, duración del partido]? Cobertura del 80 % y 90 % y saturación de la cola superior.
  E. Tasa de avisos por ficha (producto v3.3).
  F. Backtest agregado del club cliente (configs → benchmark.club_cliente): sólo agregados, nunca nombres.
IC95 por bootstrap de equipos-temporada (B y semilla del YAML).

Salidas: data/modelos/v4_1/benchmark/{benchmark.json, tablas/*.csv}.
"""
from __future__ import annotations

import json
import os
import time

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from . import config as CE


# =============================================================================================== utilidades
def _rho(x, y) -> float:
    m = np.isfinite(x) & np.isfinite(y)
    return float(spearmanr(x[m], y[m]).statistic) if m.sum() > 3 else np.nan


def _boot_clusters(d: pd.DataFrame, cl: str, f, B: int, sem: int) -> list[float]:
    """IC95 (2,5–97,5 %) de f(d) remuestreando clusters (equipos-temporada)."""
    rng = np.random.default_rng(sem)
    g = {k: v.index.to_numpy() for k, v in d.groupby(cl)}
    keys = list(g)
    out = []
    for _ in range(B):
        idx = np.concatenate([g[keys[i]] for i in rng.integers(0, len(keys), len(keys))])
        out.append(f(d.loc[idx]))
    out = np.array(out, float)
    out = out[np.isfinite(out)]
    return [float(np.quantile(out, 0.025)), float(np.quantile(out, 0.975))] if len(out) else [np.nan, np.nan]


def _seg(d: pd.DataFrame, col: str, elite: set) -> dict:
    return {"global": d, "elite_club": d[d[col].isin(elite)]}


def _topk(d: pd.DataFrame, col_pred: str, col_real: str, ks, por: str) -> dict:
    """Precisión@k (fracción del top-k predicho que está en el top-k realizado), su valor al azar (k/n) y el percentil
    realizado medio del top-k predicho; promedio sobre los grupos `por` (cortes) con n ≥ 2k."""
    out = {}
    for k in ks:
        prec, azar, media_top, media_todos, n = [], [], [], [], 0
        for _, g in d.groupby(por):
            g = g[np.isfinite(g[col_pred]) & np.isfinite(g[col_real])]
            if len(g) < 2 * k:
                continue
            tp = set(g.nlargest(k, col_pred).index)
            tr = set(g.nlargest(k, col_real).index)
            prec.append(len(tp & tr) / k)
            azar.append(k / len(g))
            media_top.append(float(g.loc[list(tp), col_real].mean()))
            media_todos.append(float(g[col_real].mean()))
            n += 1
        if n:
            out[str(k)] = {"grupos": n, "precision": float(np.mean(prec)), "azar": float(np.mean(azar)),
                           "lift": float(np.mean(prec) / np.mean(azar)), "real_medio_topk": float(np.mean(media_top)),
                           "real_medio_todos": float(np.mean(media_todos))}
    return out


# =============================================================================================== A · NIVEL CERNO
def _examen_v32():
    os.environ.setdefault("CERNO_SIMULADOR", "v32")
    from bbfit import v32, simulador as S
    E = v32.cargar_ejecuciones(v32.cfg())["V32_corte"]["completo"]
    E = E.copy()
    E["gm"] = E["liga_d"].map(lambda l: S.minutos_partido(l))
    return E


def bloque_nc(cfg: dict, E: pd.DataFrame, B: int, sem: int, elite: set, cortes_dec: list[int], ks) -> dict:
    nc = pd.read_csv(CE.RAIZ / cfg["benchmark"]["insumos"]["nc_examen"], low_memory=False)
    nc = nc[nc["eval"].astype(bool) & nc["anio"].isin(cortes_dec)].copy()
    nc["team_d"] = nc["team_d"].astype(str)
    e = E[["corte", "persona_id", "liga_d", "team_d", "min_real", "gm", "v_pts_p100_pred", "v_C_pred", "C_real"]].copy()
    e["team_d"] = e["team_d"].astype(str)
    e = e.drop_duplicates(["corte", "persona_id", "liga_d", "team_d"])
    d = nc.merge(e.drop(columns=["C_real"]), on=["corte", "persona_id", "liga_d", "team_d"], how="left",
                 suffixes=("", "_e"))
    d["C_oraculo"] = d["min_real_e"] / d["gm"] * d["v_pts_p100_pred"]
    d["cluster"] = d["liga_d"] + "|" + d["temporada_d"] + "|" + d["team_d"]
    d = d.reset_index(drop=True)
    out = {}
    for seg, x in _seg(d, "liga_d", elite).items():
        x = x.reset_index(drop=True)
        r = {"n": int(len(x)),
             "spearman_NC1_pct": _rho(x["NC1"].to_numpy(), x["pct_realizado"].to_numpy()),
             "spearman_NC1_pct_ic95": _boot_clusters(x, "cluster", lambda z: _rho(z["NC1"].to_numpy(), z["pct_realizado"].to_numpy()), B, sem),
             "spearman_Cpred_Creal": _rho(x["C_pred"].to_numpy(), x["C_real"].to_numpy()),
             "spearman_Coraculo_Creal": _rho(x["C_oraculo"].to_numpy(), x["C_real"].to_numpy()),
             "cobertura_80": float(((x["pct_realizado"] >= x["NC1_lo80"]) & (x["pct_realizado"] <= x["NC1_hi80"])).mean()),
             "anchura_80_media": float((x["NC1_hi80"] - x["NC1_lo80"]).mean()),
             "topk_NC1": _topk(x, "NC1", "pct_realizado", ks, "anio"),
             "topk_Cpred_frente_Creal": _topk(x, "C_pred", "C_real", ks, "anio"),
             "topk_Coraculo_frente_Creal": _topk(x, "C_oraculo", "C_real", ks, "anio"),
             "frac_con_oraculo": float(np.isfinite(x["C_oraculo"]).mean())}
        dif = lambda z: _rho(z["C_oraculo"].to_numpy(), z["C_real"].to_numpy()) - _rho(z["C_pred"].to_numpy(), z["C_real"].to_numpy())  # noqa: E731
        r["dif_oraculo_menos_pred_ic95"] = _boot_clusters(x, "cluster", dif, B, sem + 1)
        out[seg] = r
    return out


# =============================================================================================== B · IMPACTO
def bloque_im(cfg: dict, B: int, sem: int, elite: set, cortes_dec: list[int], ks) -> dict:
    im = pd.read_csv(CE.RAIZ / cfg["benchmark"]["insumos"]["im_examen"], low_memory=False)
    im = im[im["anio"].isin(cortes_dec) & im["onoff_ok"].astype(bool)].copy()
    im["team_d"] = im["team_d"].astype(str)
    im["cluster"] = im["liga_d"] + "|" + im["temporada_d"] + "|" + im["team_d"]
    im = im.reset_index(drop=True)
    out = {}
    for seg, x in _seg(im, "liga_d", elite).items():
        x = x.reset_index(drop=True)
        r = {"n": int(len(x))}
        # criterio de la v4.0 (V40_F5 §3.1): Spearman frente al Net on/off ajustado BRUTO; secundario: su percentil en el grupo
        for nombre, real in (("onoff", "net_rtg_aj_onoff"), ("pct_grupo", "pct_onoff")):
            f_im = lambda z, real=real: _rho(z["IM_onoff"].to_numpy(), z[real].to_numpy())  # noqa: E731
            f_ad = lambda z, real=real: _rho(z["IM_aditivo"].to_numpy(), z[real].to_numpy())  # noqa: E731
            r[f"spearman_IM_{nombre}"] = f_im(x)
            r[f"spearman_IM_{nombre}_ic95"] = _boot_clusters(x, "cluster", f_im, B, sem)
            r[f"spearman_aditivo_{nombre}"] = f_ad(x)
            r[f"dif_IM_menos_aditivo_{nombre}_ic95"] = _boot_clusters(x, "cluster", lambda z, a=f_im, b=f_ad: a(z) - b(z), B, sem + 1)
        r.update({"cobertura_80": float(((x["pct_onoff"] >= x["IM_onoff_lo80"]) & (x["pct_onoff"] <= x["IM_onoff_hi80"])).mean()),
                  "topk_IM": _topk(x, "IM_onoff", "pct_onoff", ks, "anio"),
                  "IM_rango_publicado_p05_p95": [float(x["IM_onoff"].quantile(0.05)), float(x["IM_onoff"].quantile(0.95))]})
        out[seg] = r
    return out


# =============================================================================================== C · ΔNet de equipo
def bloque_delta(cfg: dict, B: int, sem: int, elite: set, cortes_dec: list[int]) -> dict:
    p = pd.read_csv(CE.RAIZ / cfg["benchmark"]["insumos"]["f4_examen"] / "predicciones_f4.csv.gz", low_memory=False)
    p = p[p["corte"].isin(cortes_dec)].copy()
    p["cluster"] = p["liga"] + "|" + p["temporada_nueva"] + "|" + p["club"].astype(str)
    p = p.reset_index(drop=True)
    out = {}
    for seg, x in _seg(p, "liga", elite).items():
        x = x.reset_index(drop=True)
        mae = lambda z, c: float(np.mean(np.abs(z["delta_real"] - (0.0 if c is None else z[c]))))  # noqa: E731
        r = {"n": int(len(x)), "mae_f4": mae(x, "delta_pred"), "mae_persistencia": mae(x, None),
             "mae_aditivo": mae(x, "delta_aditivo"), "mae_oraculo_minutos": mae(x, "delta_oraculo_minutos"),
             "dif_f4_persistencia_ic95": _boot_clusters(x, "cluster", lambda z: mae(z, "delta_pred") - mae(z, None), B, sem),
             "dif_oraculo_f4_ic95": _boot_clusters(x, "cluster", lambda z: mae(z, "delta_oraculo_minutos") - mae(z, "delta_pred"), B, sem + 1),
             "spearman": _rho(x["delta_pred"].to_numpy(), x["delta_real"].to_numpy()),
             "cobertura_80": float(((x["delta_real"] >= x["lo80"]) & (x["delta_real"] <= x["hi80"])).mean()),
             "anchura_80_media": float((x["hi80"] - x["lo80"]).mean())}
        out[seg] = r
    return out


# =============================================================================================== D · intervalos de minutos
def bloque_minutos(E: pd.DataFrame, elite: set, cortes_dec_txt: list[str]) -> dict:
    out = {}
    e = E[E["corte"].isin(cortes_dec_txt)]

    def chequeo(x: pd.DataFrame, pref: str, gm: pd.Series) -> dict:
        lo80, hi80, lo90, hi90, pr = (x[f"{pref}min_lo80"], x[f"{pref}min_hi80"], x[f"{pref}min_lo90"], x[f"{pref}min_hi90"],
                                      x[f"{pref}min_pred"])
        fuera = (lo90 < 0) | (hi90 > gm) | (lo80 < 0) | (hi80 > gm) | (pr < 0) | (pr > gm)
        r = {"n": int(len(x)), "fuera_de_limites": int(fuera.sum()), "min_lo90": float(lo90.min()), "max_hi90": float(hi90.max()),
             "max_hi90_sobre_duracion": float((hi90 / gm).max()),
             "orden_incoherente_lo80_gt_pred_o_pred_gt_hi80": int(((lo80 > pr + 1e-9) | (pr > hi80 + 1e-9)).sum()),
             "saturacion_cola_superior_frac": float(((hi90 - hi80) < 0.5).mean()),
             "hi80_mediana": float(hi80.median()), "hi90_mediana": float(hi90.median())}
        if "min_real" in x and x["min_real"].notna().any():
            m = x["min_real"].notna()
            r["cobertura_80"] = float(((x.loc[m, "min_real"] >= lo80[m]) & (x.loc[m, "min_real"] <= hi80[m])).mean())
            r["cobertura_90"] = float(((x.loc[m, "min_real"] >= lo90[m]) & (x.loc[m, "min_real"] <= hi90[m])).mean())
            r["frac_real_por_encima_hi90"] = float((x.loc[m, "min_real"] > hi90[m]).mean())
            r["frac_real_por_debajo_lo90"] = float((x.loc[m, "min_real"] < lo90[m]).mean())
        return r

    for seg, x in _seg(e, "liga_d", elite).items():
        out[f"examen_corte_{seg}"] = chequeo(x, "v_", x["gm"])
    # producto v3.3 (histórico del simulador, escenario «inicio», todas las temporadas)
    fr = []
    for f in sorted((CE.RAIZ / "data/modelos/simulador/v3_3").glob("historico_*.csv.gz")):
        fr.append(pd.read_csv(f, low_memory=False, usecols=["persona_id", "liga_d", "team_d", "temporada_d", "min_real",
                                                            "min_pred", "min_lo80", "min_hi80", "min_lo90", "min_hi90", "avisos"]))
    H = pd.concat(fr, ignore_index=True)
    gm = H["liga_d"].map(lambda l: 48.0 if l in ("nba", "gleague") else 40.0)
    for seg, x in _seg(H, "liga_d", elite).items():
        out[f"producto_v33_{seg}"] = chequeo(x, "", gm.loc[x.index])
    return out, H


# =============================================================================================== E · avisos
def bloque_avisos(H: pd.DataFrame, elite: set) -> dict:
    out = {}
    for seg, x in _seg(H, "liga_d", elite).items():
        a = x["avisos"].fillna("").astype(str)
        lst = a.map(lambda s: [t for t in s.replace(";", "|").split("|") if t.strip()])
        n = lst.map(len)
        tipos = pd.Series([t.strip() for l in lst for t in l]).value_counts()
        out[seg] = {"fichas": int(len(x)), "frac_con_aviso": float((n > 0).mean()), "avisos_medios": float(n.mean()),
                    "frac_2_o_mas": float((n >= 2).mean()),
                    "por_tipo_frac_fichas": {k: float(v / len(x)) for k, v in tipos.items()}}
    return out


# =============================================================================================== F · club cliente
def bloque_club(cfg: dict, E: pd.DataFrame, cortes_dec: list[int]) -> dict:
    cc = cfg["benchmark"]["club_cliente"]
    ids = {str(k): str(v) for k, v in cc["ids"].items()}
    nc = pd.read_csv(CE.RAIZ / cfg["benchmark"]["insumos"]["nc_examen"], low_memory=False)
    im = pd.read_csv(CE.RAIZ / cfg["benchmark"]["insumos"]["im_examen"], low_memory=False)
    p = pd.read_csv(CE.RAIZ / cfg["benchmark"]["insumos"]["f4_examen"] / "predicciones_f4.csv.gz", low_memory=False)
    es = lambda d, l, t: d[l].astype(str).map(ids).eq(d[t].astype(str)) & d[l].astype(str).isin(ids)  # noqa: E731
    out = {"nota": "sólo agregados; ningún nombre ni identificador de jugador", "cortes": cortes_dec}
    x = nc[es(nc, "liga_d", "team_d") & nc["eval"].astype(bool) & nc["anio"].isin(cortes_dec)]
    if len(x):
        out["nc"] = {"fichajes": int(len(x)), "NC1_medio": float(x["NC1"].mean()), "pct_realizado_medio": float(x["pct_realizado"].mean()),
                     "error_medio": float((x["pct_realizado"] - x["NC1"]).mean()),
                     "error_absoluto_medio": float((x["pct_realizado"] - x["NC1"]).abs().mean()),
                     "cobertura_80": float(((x["pct_realizado"] >= x["NC1_lo80"]) & (x["pct_realizado"] <= x["NC1_hi80"])).mean()),
                     "spearman": _rho(x["NC1"].to_numpy(), x["pct_realizado"].to_numpy()) if len(x) >= 8 else None}
    y = im[es(im, "liga_d", "team_d") & im["anio"].isin(cortes_dec) & im["onoff_ok"].astype(bool)]
    if len(y):
        out["im"] = {"fichajes": int(len(y)), "IM_medio": float(y["IM_onoff"].mean()), "pct_onoff_medio": float(y["pct_onoff"].mean()),
                     "cobertura_80": float(((y["pct_onoff"] >= y["IM_onoff_lo80"]) & (y["pct_onoff"] <= y["IM_onoff_hi80"])).mean()),
                     "spearman": _rho(y["IM_onoff"].to_numpy(), y["pct_onoff"].to_numpy()) if len(y) >= 8 else None}
    z = p[es(p, "liga", "club") & p["corte"].isin(cortes_dec)]
    if len(z):
        out["delta_net"] = {"transiciones": int(len(z)), "mae_f4": float((z["delta_real"] - z["delta_pred"]).abs().mean()),
                            "mae_persistencia": float(z["delta_real"].abs().mean()),
                            "cobertura_80": float(((z["delta_real"] >= z["lo80"]) & (z["delta_real"] <= z["hi80"])).mean())}
    return out


# =============================================================================================== orquestación
def ejecutar(cfg: dict, progreso=print) -> dict:
    cm, cb = cfg["comunes"], cfg["benchmark"]
    B, sem = int(cm["bootstrap"]), int(cm["semilla_bootstrap"])
    elite = set(cm["segmentos"]["elite_club"])
    dec = [int(c) for c in cm["cortes_decision"]]
    dec_txt = [f"{c}-{str(c + 1)[-2:]}" for c in dec]
    ks = [int(k) for k in cb["top_k"]]
    t0 = time.time()
    E = _examen_v32()
    res = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "cortes_decision": dec,
           "segmentos": {"elite_club": sorted(elite), "global": "todas"}, "bootstrap": B}
    res["A_nivel_cerno"] = bloque_nc(cfg, E, B, sem, elite, dec, ks)
    if progreso:
        progreso(f"  A (NC) · {time.time() - t0:.0f} s", flush=True)
    res["B_impacto"] = bloque_im(cfg, B, sem, elite, dec, ks)
    res["C_delta_net"] = bloque_delta(cfg, B, sem, elite, dec)
    res["D_minutos"], H = bloque_minutos(E, elite, dec_txt)
    res["E_avisos"] = bloque_avisos(H, elite)
    res["F_club_cliente"] = bloque_club(cfg, E, dec)
    res["segundos"] = round(time.time() - t0)
    ds = CE.dir_salida(cfg, "benchmark")
    (ds / "benchmark.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    if progreso:
        progreso(json.dumps(res, ensure_ascii=False, indent=1, default=float)[:6000])
    return res
