"""F1 · examen prerregistrado (§11.1), comprobaciones D2 (aprobación del CEO, 04-11-2026) y diagnóstico F1-D.

Exámenes sin fuga: en el corte t se ajusta el RAPM multiliga con los tramos ≤ t y los perfiles de `perfiles/corte_<t>/`;
se predice la temporada t+1.
  * Margen por partido (t+1): margen_pred = Σ_s n_s/100 · (ĉ_{ℓ,t} + Σβ_A − Σβ_B), con β̂_t para quien tiene β en t,
    g_t(x̃_t) para quien tiene perfil en t pero no tramos, y la media de β̂_t de su liga para quien es nuevo (marcado).
    Líneas base: (a) interceptos liga-equipo-temporada ajustados en t (equipo nuevo = 0); (b) aditivo con el RAPM
    traducido de la v3.2 (`rapm_am`, el «L actual» del impacto); (c) sólo la ventaja local. RMSE con IC95 por bootstrap
    de conglomerados (liga × equipo local × temporada).
  * Test-retest: corr(β̂_t, β̂_{t+1}) de la misma persona (ajuste producto) frente a corr(RAPM_t, RAPM_{t+1}) de la
    misma persona y liga (pista).
  * Fichajes (cambian de liga principal entre t y t+1): corr(g_t(x̃_t), β̂_{t+1}) con IC95 (β̂_{t+1} del corte t+1; para
    2024 → 2025-26, del ajuste producto, declarado).
  * Elección del prior (ridge | gbm) y comprobaciones D2 en el corte de selección 2022 con la misma medida: error del
    prior g_2022(x̃_2022) al predecir β̂_2023 (corte 2023) en personas con ≥ 300 posesiones en 2023-24.
  * F1-D: RAPM de origen (pista, temporada t) ~ Net del equipo + prior de caja + log(minutos), por liga y exposición.
Salidas en data/modelos/v4_0/rapm_multiliga/examen/.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from . import rapm as RP

Z95 = 1.959963984540054


def dir_examen(cfg: dict) -> Path:
    d = RP.dir_salida(cfg) / "examen"
    d.mkdir(parents=True, exist_ok=True)
    return d


def perfiles_corte(cfg: dict, a: int) -> pd.DataFrame:
    d = C.dir_salida(cfg) / "perfiles" / f"corte_{a}"
    fr = [pd.read_csv(p, low_memory=False) for p in sorted(d.glob("*.csv.gz")) if not p.name.startswith("latente")]
    return pd.concat(fr, ignore_index=True)


def perfiles_completo(cfg: dict, temporadas) -> pd.DataFrame:
    d = C.dir_salida(cfg) / "perfiles"
    return pd.concat([pd.read_csv(d / f"{t}.csv.gz", low_memory=False) for t in temporadas], ignore_index=True)


def grupo_liga(cfg: dict) -> dict:
    g = cfg["f5"]["impacto"]["referencia"]["grupos"]
    return {l: k for k, ls in g.items() for l in ls}


# =============================================================================================== ajuste de un corte
def ajuste_corte(cfg: dict, a: int, tr_all: pd.DataFrame, tipo_prior: str, bloques_fuera=(), T: pd.DataFrame | None = None,
                 progreso=print) -> dict:
    """Ajuste F1 del corte a (tramos ≤ a, perfiles de corte_<a>). Caché en experimentos/v4_0/ajuste_f1_<a>_<prior>_<huella>.pkl
    (reanudable: un examen interrumpido no repite los ajustes ya hechos)."""
    import pickle
    tr = tr_all[tr_all["anio"] <= a].reset_index(drop=True)
    sub = {"f1": {k: v for k, v in cfg["f1"].items() if k in ("modelo", "unidad", "intercepto_liga_temporada", "localia", "clutch",
                                                             "fase_playoffs", "prior", "bayes_empirico", "descomposicion_od",
                                                             "min_posesiones_jugador", "mascara_rasgos")},
           "contrato": cfg["contrato"]}                      # sólo lo que cambia el ajuste de un corte (no producto, f1d, d2, salidas)
    huella = C.huella(sub, ("f1", "contrato")) + ("_" + "-".join(bloques_fuera) if bloques_fuera else "")
    cache = C.RAIZ / "experimentos" / "v4_0" / f"ajuste_f1_{a}_{tipo_prior}_{huella}.pkl"
    if T is None:
        T = RP.tabla_prior(perfiles_corte(cfg, a), cfg)
    D = RP.construir_diseno(tr, "net")
    if cache.exists():
        res = pickle.loads(cache.read_bytes())
        if progreso:
            progreso(f"    corte {a} ({tipo_prior}): ajuste reutilizado de {cache.name}", flush=True)
    else:
        res = RP.ajustar(D, T, cfg, tipo_prior, bloques_fuera, progreso=progreso)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(pickle.dumps({k: v for k, v in res.items() if k != "XZ"}))
    tb = RP.tabla_beta(res, D).merge(RP.ligas_jugador(tr), on="clave", how="left")
    return {"corte": a, "D": D, "res": res, "tb": tb, "T": T, "tramos": len(tr)}


def _bootstrap_rmse(err_a: np.ndarray, err_b: np.ndarray | None, grupos: np.ndarray, B: int, semilla: int):
    """IC95 del RMSE de err_a y de la diferencia RMSE(a) − RMSE(b), remuestreando conglomerados."""
    rng = np.random.default_rng(semilla)
    u, inv = np.unique(grupos, return_inverse=True)
    idx_por = [np.where(inv == k)[0] for k in range(len(u))]
    r_a, r_d = [], []
    for _ in range(B):
        pick = rng.integers(0, len(u), len(u))
        ii = np.concatenate([idx_por[k] for k in pick])
        ra = np.sqrt(np.mean(err_a[ii] ** 2))
        r_a.append(ra)
        if err_b is not None:
            r_d.append(ra - np.sqrt(np.mean(err_b[ii] ** 2)))
    out = {"rmse": float(np.sqrt(np.mean(err_a ** 2))), "ic95": [float(np.quantile(r_a, 0.025)), float(np.quantile(r_a, 0.975))]}
    if err_b is not None:
        out["dif_rmse"] = float(np.sqrt(np.mean(err_a ** 2)) - np.sqrt(np.mean(err_b ** 2)))
        out["dif_ic95"] = [float(np.quantile(r_d, 0.025)), float(np.quantile(r_d, 0.975))]
    return out


# =============================================================================================== margen por partido
def _rapm_traducido(cfg: dict, temp: str) -> dict:
    """RAPM traducido a la vara EuroLeague (v3.2, `rapm_am`) por persona (crosswalk) de la temporada t."""
    from bbfit.datos import persona
    p = C.ruta(cfg, "normalizado") / f"{temp}.csv.gz"
    n = pd.read_csv(p, usecols=["liga", "player_id", "min", "rapm_am"], dtype={"player_id": str}, low_memory=False)
    n = n[n["rapm_am"].notna()].sort_values("min", ascending=False)
    out = {}
    for liga, g in n.groupby("liga"):
        per = persona(liga, g["player_id"].astype(str))
        for k, v in zip(per, g["rapm_am"]):
            out.setdefault(str(k), float(v))
    return out


def examen_margen(cfg: dict, aj: dict, tr_all: pd.DataFrame, progreso=print) -> tuple[pd.DataFrame, dict]:
    a = aj["corte"]
    temp_t, temp_t1 = RP.temp_de(a) if hasattr(RP, "temp_de") else f"{a}-{str(a + 1)[-2:]}", f"{a + 1}-{str(a + 2)[-2:]}"
    tr1 = tr_all[tr_all["anio"] == a + 1].reset_index(drop=True)
    if tr1.empty:
        return pd.DataFrame(), {"corte": a, "nota": "sin temporada t+1"}
    tr_t = tr_all[tr_all["anio"] == a]
    tb, res, D, T = aj["tb"], aj["res"], aj["D"], aj["T"]
    nJ = D.nJ
    # β̂ de la temporada t por persona; prior g_t de quien tiene perfil en t y no tramos; media de liga para los nuevos
    bt = tb[tb["temporada"] == temp_t]
    beta_t = dict(zip(bt["persona_id"], bt["beta"]))
    media_liga = bt.groupby("liga_principal").apply(lambda g: np.average(g["beta"], weights=np.maximum(g["poss"], 1.0))).to_dict()
    pr = res["priors"][0]
    g_t = {}
    if pr is not None:
        Tt = T[T["temporada"] == temp_t]
        g_t = dict(zip(Tt["persona_id"], pr.predecir(Tt)))
    c = res["fijos"]
    c_liga = {k[2:].split("|")[0]: v for k, v in c.items() if k.startswith("c_") and k.endswith("|" + temp_t)}
    c_media = float(np.mean([v for k, v in c.items() if k.startswith("c_")]))
    kcl, kpo = c.get("clutch", 0.0), c.get("playoffs", 0.0)
    rapm_tr = _rapm_traducido(cfg, temp_t)
    perf_t = perfiles_corte(cfg, a)
    pt = perf_t[perf_t["temporada"] == temp_t].sort_values("min", ascending=False).drop_duplicates("persona_id")
    rapm_raw = {k: v for k, v in zip(pt["persona_id"].astype(str), pd.to_numeric(pt["rapm_obs"], errors="coerce")) if np.isfinite(v)}
    # jugadores sin RAPM en t (nuevos o sin dato): media de su liga en t, como hace F1 con la media de β̂ de la liga
    # (imputar 0 sesgaría a las ligas cuyo nivel traducido está lejos de 0, p. ej. la Tercera FEB a −11 pts/100)
    lig_t = dict(zip(pt["persona_id"].astype(str), pt["liga"].astype(str)))
    med_tr = pd.Series(rapm_tr).groupby(pd.Series(rapm_tr).index.map(lig_t)).mean().to_dict()
    med_raw = pd.Series(rapm_raw).groupby(pd.Series(rapm_raw).index.map(lig_t)).mean().to_dict()
    med_tr_g, med_raw_g = float(np.mean(list(rapm_tr.values()))), float(np.mean(list(rapm_raw.values())))
    # línea base (a): interceptos liga-equipo-temporada ajustados en t
    eq = _efectos_equipo(tr_t)

    def val(persona, liga):
        if persona in beta_t:
            return beta_t[persona], "beta"
        if persona in g_t:
            return g_t[persona], "prior"
        return media_liga.get(liga, 0.0), "nuevo"

    filas = []
    for (liga, gid), g in tr1.groupby(["liga", "game_id"], sort=False):
        poss = g["poss"].to_numpy()
        n_tot = poss.sum()
        real = float(g["a_pts"].sum() - g["b_pts"].sum())
        pred, pred_b, pred_raw, n_nuevo, n_tot_j = 0.0, 0.0, 0.0, 0, 0
        cl = c_liga.get(liga, c_media)
        for s, row in enumerate(g.itertuples()):
            fuentes = []
            dA = 0.0; dB = 0.0; bA = 0.0; bB = 0.0; rA = 0.0; rB = 0.0
            mt, mr = med_tr.get(liga, med_tr_g), med_raw.get(liga, med_raw_g)
            for k in row.A:
                p = k.rsplit("|", 1)[0]
                v, f = val(p, liga); dA += v; fuentes.append(f)
                bA += rapm_tr.get(p, mt); rA += rapm_raw.get(p, mr)
            for k in row.B:
                p = k.rsplit("|", 1)[0]
                v, f = val(p, liga); dB += v; fuentes.append(f)
                bB += rapm_tr.get(p, mt); rB += rapm_raw.get(p, mr)
            n_nuevo += sum(1 for f in fuentes if f == "nuevo"); n_tot_j += 10
            mu = cl + (kcl if row.clutch else 0.0) + (kpo if row.playoffs else 0.0) + dA - dB
            pred += poss[s] / 100.0 * mu
            pred_b += poss[s] / 100.0 * (cl + bA - bB)
            pred_raw += poss[s] / 100.0 * (cl + rA - rB)
        ta, tb_ = g["team_a"].iloc[0], g["team_b"].iloc[0]
        pred_eq = n_tot / 100.0 * (eq["c"].get(liga, c_media) + eq["e"].get((liga, ta), 0.0) - eq["e"].get((liga, tb_), 0.0))
        pred_local = n_tot / 100.0 * cl
        filas.append({"liga": liga, "temporada": temp_t1, "game_id": gid, "team_a": ta, "team_b": tb_, "poss": n_tot, "real": real,
                      "pred_f1": pred, "pred_equipos": pred_eq, "pred_rapm_v32": pred_b, "pred_rapm_liga": pred_raw,
                      "pred_local": pred_local, "fraccion_nuevos": n_nuevo / max(n_tot_j, 1)})
    m = pd.DataFrame(filas)
    gl = grupo_liga(cfg)
    m["grupo"] = m["liga"].map(gl).fillna("resto")
    B = int(cfg["criterios"]["comunes"]["bootstrap"]); sem = int(cfg["criterios"]["comunes"]["semilla_bootstrap"])
    clus = (m["liga"] + "|" + m["team_a"].astype(str)).to_numpy()
    e = {k: (m[f"pred_{k}"] - m["real"]).to_numpy() for k in ("f1", "equipos", "rapm_v32", "rapm_liga", "local")}
    res_ex = {"corte": a, "temporada_examen": temp_t1, "partidos": int(len(m)), "fraccion_jugadores_nuevos": float(m["fraccion_nuevos"].mean()),
              "rmse": {k: _bootstrap_rmse(e[k], None, clus, B, sem) for k in e},
              "f1_frente_a": {k: _bootstrap_rmse(e["f1"], e[k], clus, B, sem) for k in ("equipos", "rapm_v32", "rapm_liga", "local")},
              "por_grupo": {}}
    for gname, gg in m.groupby("grupo"):
        eg = {k: (gg[f"pred_{k}"] - gg["real"]).to_numpy() for k in ("f1", "equipos", "rapm_v32", "local")}
        cg = (gg["liga"] + "|" + gg["team_a"].astype(str)).to_numpy()
        res_ex["por_grupo"][gname] = {"partidos": int(len(gg)), "rmse": {k: float(np.sqrt(np.mean(v ** 2))) for k, v in eg.items()},
                                      "f1_frente_a_rapm_v32": _bootstrap_rmse(eg["f1"], eg["rapm_v32"], cg, 500, sem),
                                      "f1_frente_a_equipos": _bootstrap_rmse(eg["f1"], eg["equipos"], cg, 500, sem)}
    res_ex["por_liga"] = {l: {"partidos": int(len(gg)), **{k: float(np.sqrt(np.mean((gg[f"pred_{k}"] - gg["real"]) ** 2))) for k in ("f1", "equipos", "rapm_v32", "local")}}
                          for l, gg in m.groupby("liga")}
    if progreso:
        r = res_ex["rmse"]
        progreso(f"    margen {temp_t1}: {len(m)} partidos · RMSE F1 {r['f1']['rmse']:.2f} · equipos {r['equipos']['rmse']:.2f} · "
                 f"RAPM v3.2 {r['rapm_v32']['rmse']:.2f} · local {r['local']['rmse']:.2f}", flush=True)
    return m, res_ex


def _efectos_equipo(tr_t: pd.DataFrame) -> dict:
    """Línea base (a): y_s = c_ℓ + e_A − e_B con efectos de equipo-temporada (ridge leve), ponderado por posesiones."""
    import scipy.sparse as sp
    import scipy.sparse.linalg as spla
    eqs = sorted(set(zip(tr_t["liga"], tr_t["team_a"])) | set(zip(tr_t["liga"], tr_t["team_b"])))
    ie = {k: i for i, k in enumerate(eqs)}
    ligas = sorted(tr_t["liga"].unique()); il = {l: i for i, l in enumerate(ligas)}
    n, nE = len(tr_t), len(eqs)
    rows = np.repeat(np.arange(n), 3)
    cols = np.column_stack([[ie[(l, a)] for l, a in zip(tr_t["liga"], tr_t["team_a"])],
                            [ie[(l, b)] for l, b in zip(tr_t["liga"], tr_t["team_b"])],
                            [nE + il[l] for l in tr_t["liga"]]]).ravel()
    vals = np.tile([1.0, -1.0, 1.0], n)
    sw = np.sqrt(tr_t["poss"].to_numpy(float))
    X = sp.diags(sw) @ sp.csr_matrix((vals, (rows, cols)), shape=(n, nE + len(ligas)))
    pen = sp.hstack([sp.diags(np.full(nE, 1.0)), sp.csr_matrix((nE, len(ligas)))])
    A = sp.vstack([X, pen]).tocsr()
    b = np.r_[sw * tr_t["y"].to_numpy(float), np.zeros(nE)]
    x = spla.lsqr(A, b, atol=1e-8, btol=1e-8, iter_lim=2000)[0]
    return {"e": {k: float(x[i]) for k, i in ie.items()}, "c": {l: float(x[nE + i]) for l, i in il.items()}}


# =============================================================================================== test-retest y fichajes
def test_retest(cfg: dict, tb_prod: pd.DataFrame, perf_all: pd.DataFrame, min_poss: float = 300.0) -> dict:
    out = {}
    temps = sorted(tb_prod["temporada"].unique())
    pr = perf_all.sort_values("min", ascending=False).drop_duplicates(["persona_id", "temporada"])
    pr = pr[["persona_id", "temporada", "liga", "rapm_obs", "poss_on_obs"]].copy()
    for t, t1 in zip(temps[:-1], temps[1:]):
        a = tb_prod[(tb_prod["temporada"] == t) & (tb_prod["poss"] >= min_poss)]
        b = tb_prod[(tb_prod["temporada"] == t1) & (tb_prod["poss"] >= min_poss)]
        x = a.merge(b, on="persona_id", suffixes=("_t", "_t1"))
        r_beta = float(np.corrcoef(x["beta_t"], x["beta_t1"])[0, 1]) if len(x) > 10 else np.nan
        r_prior = float(np.corrcoef(x["prior_t"], x["beta_t1"])[0, 1]) if len(x) > 10 else np.nan
        pa = pr[(pr["temporada"] == t) & (pd.to_numeric(pr["poss_on_obs"], errors="coerce") >= min_poss)]
        pb = pr[(pr["temporada"] == t1) & (pd.to_numeric(pr["poss_on_obs"], errors="coerce") >= min_poss)]
        y = pa.merge(pb, on="persona_id", suffixes=("_t", "_t1"))
        y = y[y["rapm_obs_t"].notna() & y["rapm_obs_t1"].notna()]
        r_rapm = float(np.corrcoef(y["rapm_obs_t"], y["rapm_obs_t1"])[0, 1]) if len(y) > 10 else np.nan
        ym = y[y["liga_t"] == y["liga_t1"]]
        r_rapm_misma = float(np.corrcoef(ym["rapm_obs_t"], ym["rapm_obs_t1"])[0, 1]) if len(ym) > 10 else np.nan
        xm = x[x["liga_principal_t"] == x["liga_principal_t1"]]
        r_beta_misma = float(np.corrcoef(xm["beta_t"], xm["beta_t1"])[0, 1]) if len(xm) > 10 else np.nan
        out[f"{t}→{t1}"] = {"n_beta": int(len(x)), "corr_beta": r_beta, "corr_prior_t_beta_t1": r_prior, "corr_beta_misma_liga": r_beta_misma,
                            "n_rapm": int(len(y)), "corr_rapm_liga": r_rapm, "corr_rapm_misma_liga": r_rapm_misma}
    vals = [v for v in out.values() if np.isfinite(v["corr_beta"]) and np.isfinite(v["corr_rapm_misma_liga"])]
    out["resumen"] = {"corr_beta_media": float(np.mean([v["corr_beta"] for v in vals])) if vals else None,
                      "corr_rapm_misma_liga_media": float(np.mean([v["corr_rapm_misma_liga"] for v in vals])) if vals else None,
                      "beta_no_peor": bool(np.mean([v["corr_beta"] for v in vals]) >= np.mean([v["corr_rapm_misma_liga"] for v in vals])) if vals else None}
    return out


def fichajes(cfg: dict, aj_t: dict, tb_t1: pd.DataFrame, min_poss: float = 300.0) -> dict:
    """Personas que cambian de liga principal entre t y t+1: corr(g_t(x̃_t), β̂_{t+1}) e IC95 por bootstrap de personas;
    como referencia, corr(β̂_t, β̂_{t+1}) en las mismas personas."""
    a = aj_t["corte"]
    temp_t, temp_t1 = f"{a}-{str(a + 1)[-2:]}", f"{a + 1}-{str(a + 2)[-2:]}"
    T, pr = aj_t["T"], aj_t["res"]["priors"][0]
    Tt = T[T["temporada"] == temp_t][["persona_id", "liga"]].copy()
    Tt["g"] = pr.predecir(T[T["temporada"] == temp_t]) if pr is not None else np.nan
    bt = aj_t["tb"][aj_t["tb"]["temporada"] == temp_t][["persona_id", "beta"]].rename(columns={"beta": "beta_t"})
    b1 = tb_t1[(tb_t1["temporada"] == temp_t1) & (tb_t1["poss"] >= min_poss)][["persona_id", "beta", "liga_principal"]] \
        .rename(columns={"beta": "beta_t1", "liga_principal": "liga_t1"})
    x = Tt.merge(b1, on="persona_id").merge(bt, on="persona_id", how="left")
    x = x[(x["liga"] != x["liga_t1"]) & x["g"].notna() & x["beta_t1"].notna()]
    if len(x) < 20:
        return {"corte": a, "n": int(len(x)), "nota": "pocos fichajes"}
    rng = np.random.default_rng(int(cfg["criterios"]["comunes"]["semilla_bootstrap"]))
    g, b = x["g"].to_numpy(float), x["beta_t1"].to_numpy(float)
    rs = []
    for _ in range(int(cfg["criterios"]["comunes"]["bootstrap"])):
        ii = rng.integers(0, len(x), len(x)); rs.append(np.corrcoef(g[ii], b[ii])[0, 1])
    out = {"corte": a, "temporada_destino": temp_t1, "n": int(len(x)), "corr_prior_beta_t1": float(np.corrcoef(g, b)[0, 1]),
           "ic95": [float(np.quantile(rs, 0.025)), float(np.quantile(rs, 0.975))], "positiva_ic95": bool(np.quantile(rs, 0.025) > 0)}
    ok = x["beta_t"].notna()
    if ok.sum() > 20:
        out["corr_beta_t_beta_t1"] = float(np.corrcoef(x.loc[ok, "beta_t"], x.loc[ok, "beta_t1"])[0, 1]); out["n_con_beta_t"] = int(ok.sum())
    return out


# =============================================================================================== selección del prior y D2
def error_prior(aj_t: dict, tb_t1: pd.DataFrame, cfg: dict, min_poss: float = 300.0, latente_alt: pd.DataFrame | None = None,
                tipo: str | None = None, bloques_fuera=()) -> dict:
    """Error (MSE) del prior ajustado en el corte t al predecir β̂_{t+1} (personas con ≥ min_poss en t+1), con bootstrap
    por persona. Permite reajustar el prior sobre los mismos β̂_t con otro tipo, otros bloques o un latente alternativo."""
    a = aj_t["corte"]
    temp_t, temp_t1 = f"{a}-{str(a + 1)[-2:]}", f"{a + 1}-{str(a + 2)[-2:]}"
    T = aj_t["T"].copy()
    if latente_alt is not None:
        K = int(cfg["perfil"]["latente"]["K"])
        la = latente_alt.copy()
        la["liga"], la["temporada"], la["player_id"] = la["liga"].astype(str), la["temporada"].astype(str), la["player_id"].astype(str)
        la = la.sort_values("min", ascending=False).drop_duplicates(["liga", "temporada", "player_id"])
        T = T.drop(columns=[f"u{k + 1}" for k in range(K)]).merge(la[["liga", "temporada", "player_id"] + [f"u{k + 1}" for k in range(K)]],
                                                                 on=["liga", "temporada", "player_id"], how="left")
        T.attrs = aj_t["T"].attrs
    res, D = aj_t["res"], aj_t["D"]
    if tipo is None and not bloques_fuera and latente_alt is None:
        pr = res["priors"][0]
    else:
        tipo = tipo or res["tipo_prior"]
        beta, poss = res["beta"][:D.nJ], res["poss"][:D.nJ]
        ix = {k: i for i, k in enumerate(T["clave"])}
        fila = np.array([ix.get(k, -1) for k in D.jugadores])
        sel = (fila >= 0) & (poss >= float(cfg["f1"]["min_posesiones_jugador"]))
        pr = RP.Prior(tipo, cfg, bloques_fuera).ajustar(T.iloc[fila[sel]].reset_index(drop=True), beta[sel])
    Tt = T[T["temporada"] == temp_t]
    g = pd.Series(pr.predecir(Tt), index=Tt["persona_id"].astype(str).to_numpy())
    b1 = tb_t1[(tb_t1["temporada"] == temp_t1) & (tb_t1["poss"] >= min_poss)]
    x = pd.DataFrame({"persona_id": b1["persona_id"].astype(str).to_numpy(), "b": b1["beta"].to_numpy(float)})
    x["g"] = x["persona_id"].map(g)
    x = x[x["g"].notna()]
    e = (x["g"] - x["b"]).to_numpy() ** 2
    return {"n": int(len(x)), "mse": float(e.mean()), "errores": e, "personas": x["persona_id"].to_numpy(), "tipo": pr.tipo,
            "bloques_fuera": list(bloques_fuera), "alpha": getattr(pr, "alpha", None)}


def comparar_errores(ea: dict, eb: dict, B: int, semilla: int) -> dict:
    """Δ = MSE(a)/MSE(b) − 1 con IC95 por bootstrap de personas (emparejadas)."""
    x = pd.DataFrame({"p": ea["personas"], "ea": ea["errores"]}).merge(pd.DataFrame({"p": eb["personas"], "eb": eb["errores"]}), on="p")
    rng = np.random.default_rng(semilla)
    d = []
    for _ in range(B):
        ii = rng.integers(0, len(x), len(x))
        d.append(x["ea"].to_numpy()[ii].mean() / x["eb"].to_numpy()[ii].mean() - 1)
    return {"n": int(len(x)), "delta": float(x["ea"].mean() / x["eb"].mean() - 1), "ic95": [float(np.quantile(d, 0.025)), float(np.quantile(d, 0.975))]}


# =============================================================================================== F1-D
def f1d_contaminacion(cfg: dict, perf_all: pd.DataFrame, tb_prod: pd.DataFrame | None, progreso=print) -> dict:
    """RAPM de origen (pista) ~ Net del equipo-temporada + prior de caja (9 θ de caja) + log(min), por liga y por tramo de
    exposición; coeficiente de arrastre (puntos de RAPM por punto de Net del equipo) con IC95 bootstrap. Como contraste,
    la misma regresión con β de F1 (ajuste producto)."""
    caja = [m for m in RP.rasgos(cfg) if m not in RP.RASGOS_PISTA]
    bins = [float(b) for b in cfg["f1"]["f1d"]["bins_exposicion"]]
    B = int(cfg["f1"]["f1d"]["bootstrap"]); rng = np.random.default_rng(int(cfg["semilla"]))
    # Net del equipo-temporada (fase regular) de quintetos/<liga>/equipos.csv
    eqs = []
    for temp in sorted(perf_all["temporada"].unique()):
        raiz = C.ruta(cfg, "quintetos", temporada=temp)
        if not raiz.exists():
            continue
        for d in raiz.iterdir():
            p = d / "equipos.csv"
            if p.exists():
                e = pd.read_csv(p, usecols=["liga", "temporada", "fase", "team_id", "net_rtg"], dtype={"team_id": str})
                eqs.append(e[e["fase"] == "regular"])
    eq = pd.concat(eqs, ignore_index=True).drop_duplicates(["liga", "temporada", "team_id"])
    p = perf_all.copy()
    p["team_id"] = p["team_id"].astype(str)
    p = p.merge(eq[["liga", "temporada", "team_id", "net_rtg"]], on=["liga", "temporada", "team_id"], how="left")
    p["rapm_obs"] = pd.to_numeric(p["rapm_obs"], errors="coerce")
    p["minutos"] = pd.to_numeric(p["min"], errors="coerce")
    p = p[p["rapm_obs"].notna() & p["net_rtg"].notna() & (p["minutos"] >= 50)].copy()
    if tb_prod is not None:
        p = p.merge(tb_prod[["persona_id", "temporada", "beta"]], on=["persona_id", "temporada"], how="left")

    def regresion(g: pd.DataFrame, ycol: str) -> dict | None:
        g = g[g[ycol].notna()]
        if len(g) < 60:
            return None
        Xc = g[[f"{m}_th" for m in caja]].to_numpy(float)
        Xc = np.where(np.isfinite(Xc), Xc, 0.0)
        X = np.column_stack([np.ones(len(g)), g["net_rtg"].to_numpy(float), Xc, np.log(g["minutos"].to_numpy(float))])
        y = g[ycol].to_numpy(float)
        coef = np.linalg.lstsq(X, y, rcond=None)[0]
        bs = []
        for _ in range(min(B, 500)):
            ii = rng.integers(0, len(g), len(g))
            bs.append(np.linalg.lstsq(X[ii], y[ii], rcond=None)[0][1])
        return {"n": int(len(g)), "arrastre": float(coef[1]), "ic95": [float(np.quantile(bs, 0.025)), float(np.quantile(bs, 0.975))]}

    out = {"modelo": cfg["f1"]["f1d"]["modelo"], "global": {"rapm_origen": regresion(p, "rapm_obs")},
           "por_liga": {}, "por_exposicion": {}}
    if tb_prod is not None:
        out["global"]["beta_f1"] = regresion(p, "beta")
    for l, g in p.groupby("liga"):
        r = regresion(g, "rapm_obs")
        if r:
            out["por_liga"][l] = {"rapm_origen": r, **({"beta_f1": regresion(g, "beta")} if tb_prod is not None else {})}
    for lo, hi in zip(bins[:-1], bins[1:]):
        g = p[(p["minutos"] >= lo) & (p["minutos"] < hi)]
        r = regresion(g, "rapm_obs")
        if r:
            out["por_exposicion"][f"{int(lo)}-{int(hi)}"] = {"rapm_origen": r, **({"beta_f1": regresion(g, "beta")} if tb_prod is not None else {})}
    if progreso and out["global"]["rapm_origen"]:
        progreso(f"    F1-D: arrastre del Net del equipo sobre el RAPM de origen {out['global']['rapm_origen']['arrastre']:.3f} "
                 f"{out['global']['rapm_origen']['ic95']}", flush=True)
    return out


# =============================================================================================== flujo completo
def main(cfg: dict, progreso=print) -> dict:
    from bbfit.registro import experimento
    t0 = time.time()
    out = dir_examen(cfg)
    tr_all = RP.tramos(cfg, None, progreso)
    cortes = [int(a) for a in cfg["criterios"]["comunes"]["cortes"]]
    sel = int(cfg["f1"]["comprobaciones_d2"]["corte"])
    B, sem = int(cfg["criterios"]["comunes"]["bootstrap"]), int(cfg["criterios"]["comunes"]["semilla_bootstrap"])
    margen_min = float(cfg["f1"]["comprobaciones_d2"]["ablacion_latente_margen"])
    resultado = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "cortes": {}, "decisiones": {}}
    with experimento(cfg["mlflow"], "F1_examen", params={"cortes": cortes, "corte_seleccion": sel}) as run:
        # 1. corte de selección: ridge frente a GBM, con la misma medida (error del prior al predecir β̂_{t+1})
        candidatos = list(cfg["f1"]["prior"]["candidatos"])
        if progreso:
            progreso(f"  corte de selección {sel}: ajuste con cada candidato de prior", flush=True)
        aj_sel = {c: ajuste_corte(cfg, sel, tr_all, c, progreso=progreso) for c in candidatos}
        aj_sel1 = ajuste_corte(cfg, sel + 1, tr_all, candidatos[0], progreso=progreso)     # β̂_{t+1} para medir el prior
        err = {c: error_prior(aj_sel[c], aj_sel1["tb"], cfg) for c in candidatos}
        comp = {f"{candidatos[1]}_frente_a_{candidatos[0]}": comparar_errores(err[candidatos[1]], err[candidatos[0]], B, sem)} if len(candidatos) > 1 else {}
        elegido = candidatos[0]
        if len(candidatos) > 1:
            d = comp[f"{candidatos[1]}_frente_a_{candidatos[0]}"]
            if d["ic95"][1] < 0:                                   # el segundo sólo si es mejor de forma significativa
                elegido = candidatos[1]
        resultado["decisiones"]["prior"] = {"candidatos": candidatos, "errores": {c: {"n": err[c]["n"], "mse": err[c]["mse"]} for c in candidatos},
                                            "comparacion": comp, "elegido": elegido, "regla": "el GBM sólo si IC95,sup(MSE_gbm/MSE_ridge − 1) < 0"}
        # 2. comprobaciones D2 (sobre el prior elegido)
        d2 = {}
        base = aj_sel[elegido]
        ref1 = C.dir_salida(cfg) / "perfiles" / f"corte_{sel}" / "latente_ref1.csv.gz"
        if ref1.exists():
            e_ref1 = error_prior(base, aj_sel1["tb"], cfg, latente_alt=pd.read_csv(ref1, low_memory=False), tipo=elegido)
            c1 = comparar_errores(e_ref1, err[elegido], B, sem)
            umbral = float(cfg["f1"]["comprobaciones_d2"]["umbral_sensibilidad"])
            d2["sensibilidad_referencia"] = {"referencia_alternativa": 1, "mse_ref0": err[elegido]["mse"], "mse_ref1": e_ref1["mse"],
                                             "delta": c1["delta"], "ic95": c1["ic95"], "umbral": umbral,
                                             "supera": bool(abs(c1["delta"]) > umbral),
                                             "consecuencia": "latente sólo por ridge" if abs(c1["delta"]) > umbral else "ninguna"}
            if elegido == "gbm" and abs(c1["delta"]) > umbral:
                elegido = "ridge"
                resultado["decisiones"]["prior"]["elegido"] = "ridge"
                resultado["decisiones"]["prior"]["nota"] = "D2: sensibilidad a la referencia > umbral → el latente sólo entra por ridge"
        else:
            d2["sensibilidad_referencia"] = {"nota": f"falta {ref1.name}: no se pudo comprobar"}
        e_sin_u = error_prior(base, aj_sel1["tb"], cfg, tipo=elegido, bloques_fuera=("latente",))
        c2 = comparar_errores(e_sin_u, err[elegido] if elegido == base["res"]["tipo_prior"] else error_prior(base, aj_sel1["tb"], cfg, tipo=elegido), B, sem)
        d2["ablacion_latente"] = {"mse_con": err[elegido]["mse"], "mse_sin": e_sin_u["mse"], "delta_sin_frente_a_con": c2["delta"],
                                  "ic95": c2["ic95"], "margen": margen_min,
                                  "latente_aporta": bool(c2["ic95"][0] > 0),
                                  "se_quita": bool(c2["ic95"][1] < margen_min),
                                  "regla": "se quita el latente si IC95,sup(MSE_sin/MSE_con − 1) < +0,5 % (no inferioridad)"}
        bloques_fuera = ("latente",) if d2["ablacion_latente"]["se_quita"] else ()
        resultado["decisiones"]["bloques_fuera"] = list(bloques_fuera)
        resultado["d2"] = d2
        (out / "d2.json").write_text(json.dumps(d2, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
        if progreso:
            progreso(f"  prior elegido: {elegido} · D2 sensibilidad {d2['sensibilidad_referencia'].get('delta')} · ablación latente "
                     f"{d2['ablacion_latente']['delta_sin_frente_a_con']:.4f} {d2['ablacion_latente']['ic95']}", flush=True)
        # 3. exámenes por corte con la decisión tomada en el corte de selección
        ajustes = {}
        for a in cortes:
            if a in aj_sel and elegido in aj_sel and not bloques_fuera and a == sel:
                ajustes[a] = aj_sel[elegido]
            elif a == sel + 1 and not bloques_fuera and elegido == candidatos[0]:
                ajustes[a] = aj_sel1
            else:
                if progreso:
                    progreso(f"  corte {a}: ajuste F1 ({elegido})", flush=True)
                ajustes[a] = ajuste_corte(cfg, a, tr_all, elegido, bloques_fuera, progreso=progreso)
        margenes = []
        for a in cortes:
            m, rex = examen_margen(cfg, ajustes[a], tr_all, progreso)
            if len(m):
                margenes.append(m)
            fx = fichajes(cfg, ajustes[a], ajustes[a + 1]["tb"]) if (a + 1) in ajustes else None
            resultado["cortes"][a] = {"tramos": ajustes[a]["tramos"], "jugadores": int(ajustes[a]["D"].nJ),
                                      "tau": float(np.sqrt(ajustes[a]["res"]["tau2"][0])), "sigma": float(np.sqrt(ajustes[a]["res"]["sigma2"])),
                                      "margen": rex, "fichajes": fx}
            ajustes[a]["tb"].round(4).to_csv(out / f"beta_corte_{a}.csv.gz", index=False)
        if margenes:
            pd.concat(margenes, ignore_index=True).round(3).to_csv(out / "margen_partidos.csv.gz", index=False)
        # resumen global del margen (cortes de decisión, sin el de calibración)
        dec = [a for a in cortes if a != int(cfg["criterios"]["comunes"]["corte_calibracion"]) and resultado["cortes"][a]["margen"].get("partidos")]
        if dec:
            mm = pd.concat([mg for mg in margenes if int(mg["temporada"].iloc[0][:4]) - 1 in dec], ignore_index=True)
            clus = (mm["liga"] + "|" + mm["team_a"].astype(str) + "|" + mm["temporada"]).to_numpy()
            e = {k: (mm[f"pred_{k}"] - mm["real"]).to_numpy() for k in ("f1", "equipos", "rapm_v32", "rapm_liga", "local")}
            resultado["margen_global"] = {"cortes": dec, "partidos": int(len(mm)), "rmse": {k: _bootstrap_rmse(e[k], None, clus, B, sem) for k in e},
                                          "f1_frente_a": {k: _bootstrap_rmse(e["f1"], e[k], clus, B, sem) for k in ("equipos", "rapm_v32", "rapm_liga", "local")}}
            fa = resultado["margen_global"]["f1_frente_a"]
            resultado["puerta_11_1"] = {"mejor_que_equipos": bool(fa["equipos"]["dif_ic95"][1] < 0),
                                        "mejor_que_rapm_v32_ic95_excluye_0": bool(fa["rapm_v32"]["dif_ic95"][1] < 0)}
        resultado["tiempo_s"] = round(time.time() - t0)
        (out / "resumen_examen.json").write_text(json.dumps(resultado, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
        run.metricas({"rmse_f1": resultado.get("margen_global", {}).get("rmse", {}).get("f1", {}).get("rmse", 0.0)})
    if progreso:
        progreso(f"  examen F1: {resultado.get('puerta_11_1')} · {resultado['tiempo_s']} s", flush=True)
    return resultado


def recalcular_margenes(cfg: dict, progreso=print) -> dict:
    """Vuelve a calcular los márgenes de los cuatro cortes (y el resumen global) con los ajustes en caché, sin reajustar."""
    out = dir_examen(cfg)
    res_path = out / "resumen_examen.json"
    resultado = json.loads(res_path.read_text(encoding="utf-8"))
    tr_all = RP.tramos(cfg, None, progreso)
    cortes = [int(a) for a in cfg["criterios"]["comunes"]["cortes"]]
    elegido = resultado["decisiones"]["prior"]["elegido"]
    bloques_fuera = tuple(resultado["decisiones"].get("bloques_fuera", []))
    B, sem = int(cfg["criterios"]["comunes"]["bootstrap"]), int(cfg["criterios"]["comunes"]["semilla_bootstrap"])
    margenes = []
    for a in cortes:
        aj = ajuste_corte(cfg, a, tr_all, elegido, bloques_fuera, progreso=progreso)
        m, rex = examen_margen(cfg, aj, tr_all, progreso)
        if len(m):
            margenes.append(m)
        resultado["cortes"][str(a)]["margen"] = rex
    pd.concat(margenes, ignore_index=True).round(3).to_csv(out / "margen_partidos.csv.gz", index=False)
    dec = [a for a in cortes if a != int(cfg["criterios"]["comunes"]["corte_calibracion"])]
    mm = pd.concat([mg for mg in margenes if int(mg["temporada"].iloc[0][:4]) - 1 in dec], ignore_index=True)
    clus = (mm["liga"] + "|" + mm["team_a"].astype(str) + "|" + mm["temporada"]).to_numpy()
    e = {k: (mm[f"pred_{k}"] - mm["real"]).to_numpy() for k in ("f1", "equipos", "rapm_v32", "rapm_liga", "local")}
    resultado["margen_global"] = {"cortes": dec, "partidos": int(len(mm)), "rmse": {k: _bootstrap_rmse(e[k], None, clus, B, sem) for k in e},
                                  "f1_frente_a": {k: _bootstrap_rmse(e["f1"], e[k], clus, B, sem) for k in ("equipos", "rapm_v32", "rapm_liga", "local")}}
    fa = resultado["margen_global"]["f1_frente_a"]
    resultado["puerta_11_1"] = {"mejor_que_equipos": bool(fa["equipos"]["dif_ic95"][1] < 0),
                                "mejor_que_rapm_v32_ic95_excluye_0": bool(fa["rapm_v32"]["dif_ic95"][1] < 0)}
    resultado["nota_margenes"] = "recalculados con imputación de la media de liga en las líneas base (antes 0)"
    res_path.write_text(json.dumps(resultado, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    if progreso:
        progreso(f"  márgenes recalculados: {resultado['puerta_11_1']} · {resultado['margen_global']['rmse']['f1']['rmse']:.3f} vs "
                 f"rapm_v32 {resultado['margen_global']['rmse']['rapm_v32']['rmse']:.3f}", flush=True)
    return resultado
