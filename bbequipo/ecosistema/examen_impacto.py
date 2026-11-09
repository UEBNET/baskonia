"""F2 · examen del Impacto en pista (criterios congelados `criterios.f2`; prerregistro `f2`, 08-11-2026).

Tubería por variante (crudo → percentil → calibración), idéntica a la del IMPACTO v4.0 (anclas.examen_im_onoff):
  1. crudo: 100·E_pred[F_grupo(v_j)], F_grupo = v̂ de los jugadores de las plantillas del grupo de liga y el corte;
     E_pred con β_j ~ N(β̂_j, sd_j) (cuadratura de Gauss–Hermite sobre la predictiva normal de v_j);
  2. calibración isotónica con los cortes ANTERIORES frente al percentil del on/off realizado de los fichajes (2021: el
     propio corte, sólo calibra) y rango del 80 % por deciles de crudo (cuantiles 10/90 de los cortes anteriores).
Variantes: IP (decide), beta (β solo, diagnóstico), IP_ctx (candidato contexto c_j, F2-e), IP_fam (candidato familiaridad).

Examen (cortes 2022–2024; mismas filas que el IM v4.0): monotonía (Spearman con net_rtg_aj_onoff; pareada frente al IM v4.0,
al aditivo y a β solo; bootstrap de equipos-temporada, B = 2000), calibración por deciles (±7), cobertura del 80 %,
segmento élite informado, EMD (sembrado sobre los datos reales, ≥ 20 réplicas) y población secundaria (todos ≥ 300 min).
Contextualidad: jugadores que siguen, Δv = v(R_t+1) − v(R_t) frente al Δ del percentil on/off.
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd
from scipy.stats import rankdata
from sklearn.isotonic import IsotonicRegression

from . import config as CE

_GX, _GW = np.polynomial.hermite_e.hermegauss(15)
_GW = _GW / _GW.sum()
Z = 1.959963984540054
Z80 = 0.8416212335729143                                      # potencia 0,80


# =============================================================================================== utilidades
def pct_esperado(m, sd, ref) -> np.ndarray:
    """100·E[F_ref(V)], V ~ N(m, sd²), F_ref = CDF empírica (anclas.Empirica) de los valores de referencia."""
    from ..anclas import Empirica
    F = Empirica(np.asarray(ref, float))
    m, sd = np.asarray(m, float), np.nan_to_num(np.asarray(sd, float), nan=0.0)
    return 100.0 * (F(m[:, None] + sd[:, None] * _GX[None, :]) @ _GW)


def spearman(x, y) -> float:
    rx, ry = rankdata(x), rankdata(y)
    return float(np.corrcoef(rx, ry)[0, 1])


def clusters(d: pd.DataFrame, cols=("anio", "liga_d", "team_d")) -> list[np.ndarray]:
    k = pd.factorize(pd.MultiIndex.from_frame(d[list(cols)].astype(str)))[0]
    o = np.argsort(k, kind="stable")
    cortes = np.flatnonzero(np.diff(k[o])) + 1
    return np.split(o, cortes)


def bootstrap(d: pd.DataFrame, f, B: int, semilla: int, cols=("anio", "liga_d", "team_d")) -> np.ndarray:
    """f(d_b) → vector, con remuestreo de equipos-temporada (conglomerados)."""
    cl = clusters(d, cols)
    rng = np.random.default_rng(semilla)
    return np.array([f(d.iloc[np.concatenate([cl[i] for i in rng.integers(0, len(cl), len(cl))])]) for _ in range(B)])


def _ic(v) -> list[float]:
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    return [float(np.quantile(v, .025)), float(np.quantile(v, .975))] if len(v) else [np.nan, np.nan]


# =============================================================================================== escala y calibración
def crudo(R: pd.DataFrame, col_m: str, col_sd: str | None) -> pd.Series:
    """Percentil esperado dentro de (corte, grupo de liga) frente a todos los jugadores de las plantillas del grupo."""
    out = pd.Series(np.nan, index=R.index)
    for _, x in R[R[col_m].notna()].groupby(["anio", "grupo"]):
        sd = x[col_sd] if col_sd else np.zeros(len(x))
        out[x.index] = pct_esperado(x[col_m], sd, x[col_m])
    return out


def _rango(prev: pd.DataFrame, col_c: str, col_y: str, v: np.ndarray):
    bordes = np.quantile(prev[col_c], np.linspace(0, 1, 11)); bordes[0], bordes[-1] = -np.inf, np.inf
    bp = np.clip(np.searchsorted(bordes, prev[col_c], side="right") - 1, 0, 9)
    q = {}
    for p in (.10, .90):
        q[p] = pd.Series([np.quantile(prev[col_y][bp == b], p) if (bp == b).sum() >= 20 else np.nan for b in range(10)]
                         ).interpolate(limit_direction="both").to_numpy()
    b = np.clip(np.searchsorted(bordes, np.nan_to_num(v, nan=50.0), side="right") - 1, 0, 9)
    return q[.10][b], q[.90][b]


def calibrar(e: pd.DataFrame, col_c: str, cortes: list[int], nombre: str) -> pd.DataFrame:
    """Isotónica con los cortes anteriores (corte 0: el propio) frente a pct_onoff; rango 80 % por deciles."""
    for c in (nombre, f"{nombre}_lo80", f"{nombre}_hi80"):
        e[c] = np.nan
    for k, a in enumerate(cortes):
        sel = (e["anio"] == a) & e[col_c].notna()
        ok = e["onoff_ok"] & e[col_c].notna()
        prev = e[e["anio"].isin(cortes[:k]) & ok] if k else e[sel & ok]
        if len(prev) < 300 or not sel.any():
            continue
        g = IsotonicRegression(y_min=0, y_max=100, out_of_bounds="clip").fit(prev[col_c], prev["pct_onoff"])
        v = e.loc[sel, col_c].to_numpy(float)
        cal = g.predict(v)
        lo, hi = _rango(prev, col_c, "pct_onoff", v)
        e.loc[sel, nombre] = cal
        e.loc[sel, f"{nombre}_lo80"] = np.minimum(lo, cal)
        e.loc[sel, f"{nombre}_hi80"] = np.maximum(hi, cal)
    return e


# =============================================================================================== datos
def roles(cfg: dict) -> pd.DataFrame:
    cfg40 = CE.cargar_v40(cfg)
    f = CE.RAIZ / cfg40["insumos"]["roles"]
    return pd.read_csv(f, usecols=["liga", "temporada", "team_id", "persona_id", "net_rtg_aj_onoff", "min_total"],
                       dtype={"team_id": str, "persona_id": str}, low_memory=False)


def xp_onoff(cfg: dict) -> pd.DataFrame:
    """net_onoff y xnet_onoff (capa XP, F2-d) por liga, temporada, equipo y persona."""
    dv = CE.dir_salida(cfg, "puntos_esperados")
    partes = []
    for f in sorted(dv.glob("jugadores_*.csv.gz")):
        J = pd.read_csv(f, usecols=lambda c: c in ("liga", "temporada", "team_id", "persona_id", "poss_on", "net_onoff", "xnet_onoff"),
                        dtype={"team_id": str, "persona_id": str}, low_memory=False)
        partes.append(J)
    X = pd.concat(partes, ignore_index=True)
    X = X.sort_values("poss_on", ascending=False).drop_duplicates(["liga", "temporada", "team_id", "persona_id"])
    return X.drop(columns="poss_on")


def objetivo_f2e(d: pd.DataFrame) -> pd.Series:
    """F2-e: on/off con un 25 % menos de suerte de tiro = net_rtg_aj_onoff − 0,25·(net_onoff − xnet_onoff)."""
    s = (d["net_onoff"] - d["xnet_onoff"]).fillna(0.0)
    return d["net_rtg_aj_onoff"] - 0.25 * s


def preparar(cfg: dict, R: pd.DataFrame, im: pd.DataFrame) -> pd.DataFrame:
    """Une las filas del IM v4.0 (fichajes del examen, con su on/off ya fijado) con el Impacto en pista de cada corte."""
    from .. import anclas as AN
    cfg40 = CE.cargar_v40(cfg)
    R = R.copy()
    R["grupo"] = R["liga"].map(lambda l: AN.grupo_im(cfg40, l))
    e = im.copy()
    e["team_d"] = e["team_d"].astype(str)
    e["persona_id"] = e["persona_id"].astype(str)
    F = R[R["fichaje"]].drop_duplicates(["anio", "liga", "team", "persona_id"])
    e = e.merge(F.rename(columns={"liga": "liga_d", "team": "team_d"}), on=["anio", "liga_d", "team_d", "persona_id"],
                how="left", suffixes=("", "_ip"))
    xp = xp_onoff(cfg).rename(columns={"liga": "liga_d", "team_id": "team_d", "temporada": "temporada_d"})
    e = e.merge(xp, on=["liga_d", "team_d", "temporada_d", "persona_id"], how="left")
    e["y_f2e"] = objetivo_f2e(e)
    return e, R


# =============================================================================================== variantes
def delta_por_corte(fam: dict | None, cortes) -> dict:
    """δ de familiaridad estimado con las temporadas ≤ t (sin fuga) para cada corte t."""
    if not fam:
        return {}
    h = fam.get("hasta_temporada", {})
    return {int(a): float((h.get(f"{a}-{str(a + 1)[-2:]}") or {}).get("delta", np.nan)) for a in cortes}


def variantes(cfg: dict, R: pd.DataFrame, e: pd.DataFrame, fam: dict | None) -> tuple[pd.DataFrame, dict]:
    """Crudos y calibrados de IP, beta, IP_fam (δ ≤ t) e IP_ctx (γ con los cortes < t, F2-e). fam: familiaridad.json."""
    cortes = [int(c) for c in cfg["comunes"]["cortes"]]
    info = {}
    R["c_IP"] = crudo(R, "v_media", "v_sd")
    R["c_beta"] = crudo(R, "beta", "beta_sd")
    if fam:
        dlt = delta_por_corte(fam, cortes)
        info["delta_familiaridad_por_corte"] = dlt
        R["v_fam"] = R["v_media"] + R["anio"].map(dlt).fillna(0.0) * R["familiaridad"].fillna(0.0)
        R["c_IP_fam"] = crudo(R, "v_fam", "v_sd")
    # contexto c_j: y_f2e ~ 1 + v̂ + c_j con los fichajes de los cortes < t (MCP por minutos), aplicado a todo el corte t
    comp = ["nivel_companeros"] + [f"perfil_companeros_{k}" for k in range(4)]
    R["s_ctx"], gam = puntuacion_contexto(R, e, cortes, comp)
    info["gamma_contexto_por_corte"] = {str(a): dict(zip(["intercepto", "v"] + comp, g)) for a, g in gam.items()}
    R["c_IP_ctx"] = crudo(R, "s_ctx", None)
    cols = [c for c in R.columns if c.startswith("c_")]
    keys = ["anio", "liga", "team", "persona_id"]
    e = e.drop(columns=[c for c in cols if c in e]).merge(
        R[R["fichaje"]].drop_duplicates(keys)[keys + cols].rename(columns={"liga": "liga_d", "team": "team_d"}),
        on=["anio", "liga_d", "team_d", "persona_id"], how="left")
    for c in cols:
        e = calibrar(e, c, cortes, c[2:])
    return e, info


def puntuacion_contexto(R: pd.DataFrame, e: pd.DataFrame, cortes: list[int], comp: list[str],
                        objetivo: str = "y_f2e") -> tuple[pd.Series, dict]:
    """s = [1, v̂, c_j]·γ, γ por MCP (pesos = minutos) con los fichajes de los cortes < t (2021: el propio, sólo calibra)."""
    ee = e[e["onoff_ok"] & e["v_media"].notna() & e[objetivo].notna()]
    s = pd.Series(np.nan, index=R.index)
    gam = {}
    for k, a in enumerate(cortes):
        tr = ee[ee["anio"].isin(cortes[:k])] if k else ee[ee["anio"] == a]
        if len(tr) < 300:
            continue
        A = np.c_[np.ones(len(tr)), tr["v_media"], tr[comp].fillna(0.0)]
        w = np.sqrt(tr["min_total"].to_numpy(float))
        coef = np.linalg.lstsq(A * w[:, None], tr[objetivo].to_numpy(float) * w, rcond=None)[0]
        gam[a] = coef.tolist()
        m = R["anio"] == a
        s[m] = np.c_[np.ones(m.sum()), R.loc[m, "v_media"], R.loc[m, comp].fillna(0.0)] @ coef
    return s, gam


# =============================================================================================== examen
def monotonia(d: pd.DataFrame, cols: list[str], B: int, semilla: int, ref: str = "net_rtg_aj_onoff") -> dict:
    """Spearman de cada columna con el on/off y diferencias pareadas (IC95 por equipos-temporada)."""
    def f(x):
        ry = rankdata(x[ref])
        return np.array([np.corrcoef(rankdata(x[c]), ry)[0, 1] for c in cols])
    p = f(d)
    bs = bootstrap(d, f, B, semilla)
    out = {"n": int(len(d)), "equipos_temporada": len(clusters(d))}
    for i, c in enumerate(cols):
        out[c] = {"spearman": float(p[i]), "ic95": _ic(bs[:, i]), "ee": float(np.nanstd(bs[:, i]))}
    out["_bs"] = bs
    return out


def diferencia(m: dict, a: str, b: str, cols: list[str]) -> dict:
    bs = m["_bs"]
    i, j = cols.index(a), cols.index(b)
    dd = bs[:, i] - bs[:, j]
    return {"diferencia": m[a]["spearman"] - m[b]["spearman"], "ic95": _ic(dd), "ee": float(np.nanstd(dd))}


def emd_monotonia(d: pd.DataFrame, rhos, replicas: int, B: int, semilla: int, ref: str = "net_rtg_aj_onoff") -> list[dict]:
    """Sembrado sobre los datos reales (prerregistro `f2.potencia.monotonia`): s = y con una fracción q de las filas
    permutada al azar (Spearman esperado ≈ 1 − q, medido en cada réplica); se repite el examen (IC95 por equipos-temporada)
    y se cuenta la detección (IC95 > 0)."""
    rng = np.random.default_rng(semilla)
    y = d[ref].to_numpy(float)
    cl = clusters(d)
    out = []
    for rho in rhos:
        det, med = [], []
        for r in range(replicas):
            s = y.copy()
            idx = rng.random(len(y)) < (1 - rho)
            s[idx] = rng.permutation(y[idx])
            s = s + 1e-9 * rng.standard_normal(len(s))
            med.append(spearman(s, y))
            bb = []
            for _ in range(B):
                ii = np.concatenate([cl[i] for i in rng.integers(0, len(cl), len(cl))])
                bb.append(spearman(s[ii], y[ii]))
            det.append(np.quantile(bb, .025) > 0)
        out.append({"rho_sembrado": rho, "rho_medido": float(np.mean(med)), "deteccion": float(np.mean(det)), "replicas": replicas})
    return out


def potencia_no_inferioridad(ee: float, margen: float) -> float:
    """P(IC95 inferior de la diferencia > −margen | diferencia real 0) con EE dado (aproximación normal)."""
    from scipy.stats import norm
    return float(norm.cdf(margen / ee - Z)) if ee > 0 else np.nan


def ejecutar(cfg: dict, R: pd.DataFrame, im: pd.DataFrame, fam: dict | None, progreso=print) -> dict:
    from .. import anclas as AN
    t0 = time.time()
    cc = cfg["criterios"]["f2"]
    B = int(cfg["comunes"]["bootstrap"])
    sem = int(cfg["comunes"]["semilla_bootstrap"])
    dec = [int(c) for c in cfg["comunes"]["cortes_decision"]]
    elite = set(cfg["comunes"]["segmentos"]["elite_club"])
    e, R = preparar(cfg, R, im)
    e, info = variantes(cfg, R, e, fam)
    base = e["anio"].isin(dec) & e["onoff_ok"] & e["IM_onoff"].notna()
    d = e[base & e["IP"].notna()].copy()
    res = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "criterios": cc, **info,
           "cobertura_filas_im": {"filas_im_decision": int(base.sum()), "con_impacto_en_pista": int(len(d))}}
    cols = ["IP", "IM_onoff", "IM_aditivo", "beta", "c_IP"]
    m = monotonia(d, cols, B, sem)
    res["monotonia"] = {c: m[c] for c in cols} | {"n": m["n"], "equipos_temporada": m["equipos_temporada"]}
    res["monotonia"]["IP_menos_IM_v40"] = diferencia(m, "IP", "IM_onoff", cols)
    res["monotonia"]["IP_menos_aditivo"] = diferencia(m, "IP", "IM_aditivo", cols)
    res["monotonia"]["IP_menos_beta"] = diferencia(m, "IP", "beta", cols)
    for s, nombre in ((d["liga_d"].isin(elite), "elite_club"), (d["grupo_im"] == "elite", "grupo_elite")):
        ms = monotonia(d[s], ["IP", "IM_onoff"], B, sem + 1)
        res[f"monotonia_{nombre}"] = {"IP": ms["IP"], "IM_onoff": ms["IM_onoff"], "n": ms["n"],
                                      "IP_menos_IM_v40": diferencia(ms, "IP", "IM_onoff", ["IP", "IM_onoff"])}
    res["monotonia_por_corte"] = {str(a): {"n": int((d["anio"] == a).sum()),
                                           "IP": spearman(d.loc[d["anio"] == a, "IP"], d.loc[d["anio"] == a, "net_rtg_aj_onoff"]),
                                           "IM_onoff": spearman(d.loc[d["anio"] == a, "IM_onoff"], d.loc[d["anio"] == a, "net_rtg_aj_onoff"])}
                                  for a in dec}
    res["calibracion"] = AN.examen_calibracion(d, "IP", "pct_onoff", float(cc["calibracion_deciles_tolerancia"]))
    res["cobertura_80"] = AN.cobertura(d, "IP_lo80", "IP_hi80", "pct_onoff")
    res["anchura_80_media"] = float((d["IP_hi80"] - d["IP_lo80"]).mean())
    # objetivo F2-e (diagnóstico): el mismo examen frente al on/off con un 25 % menos de suerte de tiro
    dx = d[d["y_f2e"].notna()]
    mx = monotonia(dx, ["IP", "IM_onoff"], B, sem + 2, ref="y_f2e")
    res["monotonia_objetivo_f2e"] = {"IP": mx["IP"], "IM_onoff": mx["IM_onoff"], "n": mx["n"],
                                     "IP_menos_IM_v40": diferencia(mx, "IP", "IM_onoff", ["IP", "IM_onoff"])}
    # F2-d: ¿cuánto del on/off realizado es suerte de tiro? (diagnóstico)
    ok = d["xnet_onoff"].notna() & d["net_onoff"].notna()
    res["diagnostico_xnet_onoff"] = {
        "n": int(ok.sum()), "spearman_net_rtg_aj_vs_net_onoff_tramos": spearman(d.loc[ok, "net_rtg_aj_onoff"], d.loc[ok, "net_onoff"]),
        "spearman_IP_vs_xnet_onoff": spearman(d.loc[ok, "IP"], d.loc[ok, "xnet_onoff"]),
        "spearman_IM_vs_xnet_onoff": spearman(d.loc[ok, "IM_onoff"], d.loc[ok, "xnet_onoff"]),
        "dt_net_onoff": float(d.loc[ok, "net_onoff"].std()), "dt_xnet_onoff": float(d.loc[ok, "xnet_onoff"].std())}
    # candidatos
    cand = {}
    for c in ("IP_ctx", "IP_fam"):
        if c not in d or d[c].notna().sum() < 300:
            continue
        dc = d[d[c].notna()]
        mc = monotonia(dc, ["IP", c, "IM_onoff"], B, sem + 3)
        cand[c] = {c: mc[c], "IP": mc["IP"], "n": mc["n"], "mejora_sobre_IP": diferencia(mc, c, "IP", ["IP", c, "IM_onoff"]),
                   "frente_IM_v40": diferencia(mc, c, "IM_onoff", ["IP", c, "IM_onoff"]),
                   "calibracion": AN.examen_calibracion(dc, c, "pct_onoff", float(cc["calibracion_deciles_tolerancia"])),
                   "cobertura_80": AN.cobertura(dc, f"{c}_lo80", f"{c}_hi80", "pct_onoff")}
    res["candidatos"] = cand
    # potencia (regla de la F0)
    cp = cfg["potencia"]
    ee_dif = res["monotonia"]["IP_menos_IM_v40"]["ee"]
    margen = -float(cc["monotonia_no_peor_que_im_v40"]["ic95_inferior_diferencia"])
    res["potencia"] = {
        "monotonia_sembrada": emd_monotonia(d, [0.02, 0.04, 0.06, 0.08], int(cp["replicas_minimas"]), 300, sem + 4),
        "emd_diferencia_pareada_vs_IM": float((Z + Z80) * ee_dif),
        "emd_diferencia_vs_aditivo": float((Z + Z80) * res["monotonia"]["IP_menos_aditivo"]["ee"]),
        "potencia_no_inferioridad_si_igual_al_IM": potencia_no_inferioridad(ee_dif, margen),
        "nota": "diferencias pareadas: EMD = (1,96 + 0,84)·EE bootstrap; la no inferioridad usa el margen prerregistrado"}
    # puerta F2-a
    mon = res["monotonia"]
    pasa = {"monotonia_no_peor_que_im_v40": mon["IP_menos_IM_v40"]["ic95"][0] > -margen,
            "monotonia_frente_aditivo": mon["IP_menos_aditivo"]["ic95"][0] > 0,
            "calibracion": res["calibracion"]["pasa"],
            "cobertura_80": cc["cobertura_80"][0] <= res["cobertura_80"] <= cc["cobertura_80"][1]}
    res["puerta"] = {**pasa, "pasa": bool(all(pasa.values())),
                     "regla_si_no": cfg["f2"]["regla_si_no_alcanza_im_v40"]}
    res["candidatos_entran"] = {
        "IP_ctx": bool("IP_ctx" in cand and cand["IP_ctx"]["mejora_sobre_IP"]["ic95"][0] > 0),
        "IP_fam": bool("IP_fam" in cand and cand["IP_fam"]["mejora_sobre_IP"]["ic95"][0] > 0
                       and bool((fam or {}).get("global", {}).get("excluye_0", False)))}
    # población secundaria (informada): todos los jugadores ≥ 300 min de las plantillas de t+1
    res["poblacion_secundaria"] = secundaria(cfg, R, B, sem + 5)
    res["segundos"] = round(time.time() - t0)
    return res, e


def secundaria(cfg: dict, R: pd.DataFrame, B: int, semilla: int) -> dict:
    rr = roles(cfg)
    rr = rr[rr["min_total"] >= float(cfg["criterios"]["f2"]["realizado_min_minutos"])]
    R = R.copy()
    R["temporada"] = R["anio"].map(lambda a: f"{a + 1}-{str(a + 2)[-2:]}")
    x = R.merge(rr.rename(columns={"team_id": "team"}), on=["liga", "temporada", "team", "persona_id"], how="inner")
    x = x[x["anio"].isin([int(c) for c in cfg["comunes"]["cortes_decision"]]) & x["c_IP"].notna() & x["net_rtg_aj_onoff"].notna()]
    x = x.rename(columns={"liga": "liga_d", "team": "team_d"})
    m = monotonia(x, ["c_IP", "c_beta"], min(B, 1000), semilla)
    return {"n": m["n"], "IP_crudo": m["c_IP"], "beta_crudo": m["c_beta"],
            "IP_menos_beta": diferencia(m, "c_IP", "c_beta", ["c_IP", "c_beta"])}


# =============================================================================================== contextualidad
def contextualidad(cfg: dict, R: pd.DataFrame, B: int, semilla: int, delta_fam: dict | None = None) -> dict:
    """Jugadores que siguen en el club de t a t+1 (≥ 300 min en las dos, ≥ 1 alta o baja de rotación): Spearman de
    Δv = v(R_t+1) − v(R_t) con el Δ del percentil on/off (dentro de temporada y grupo de liga, jugadores ≥ 300 min).
    Δv por componentes (β y h son los mismos en las dos plantillas: Δv = Δ sinergia [+ γ Δc] — sin ruido de Monte Carlo)."""
    from .. import anclas as AN
    cfg40 = CE.cargar_v40(cfg)
    mm = float(cfg["criterios"]["f2"]["realizado_min_minutos"])
    rr = roles(cfg)
    rr = rr[(rr["min_total"] >= mm) & rr["net_rtg_aj_onoff"].notna()].copy()
    rr["grupo"] = rr["liga"].map(lambda l: AN.grupo_im(cfg40, l))
    rr["pct"] = rr.groupby(["temporada", "grupo"])["net_rtg_aj_onoff"].rank(pct=True) * 100
    rr = rr.sort_values("min_total", ascending=False).drop_duplicates(["liga", "temporada", "team_id", "persona_id"])
    S = R[R.get("sigue", pd.Series(False, index=R.index)).fillna(False).astype(bool)].copy()
    S["temporada1"] = S["anio"].map(lambda a: f"{a + 1}-{str(a + 2)[-2:]}")
    S["temporada0"] = S["anio"].map(lambda a: f"{a}-{str(a + 1)[-2:]}")
    S = S.merge(rr[["liga", "temporada", "team_id", "persona_id", "pct", "min_total"]].rename(
        columns={"temporada": "temporada1", "team_id": "team", "pct": "pct1", "min_total": "min1"}),
        on=["liga", "temporada1", "team", "persona_id"], how="inner")
    S = S.merge(rr[["liga", "temporada", "team_id", "persona_id", "pct", "min_total"]].rename(
        columns={"liga": "liga0", "temporada": "temporada0", "team_id": "team0", "pct": "pct0", "min_total": "min0"}),
        on=["liga0", "temporada0", "team0", "persona_id"], how="inner")
    S = S[(S["altas_rotacion"] + S["bajas_rotacion"]) >= 1].copy()
    S["d_pred"] = S["sinergia"] - S["sinergia0"]
    if delta_fam:
        S["d_pred_fam"] = S["d_pred"] + S["anio"].map(delta_fam).fillna(0.0) * S["familiaridad"].fillna(0.0)
    S["d_real"] = S["pct1"] - S["pct0"]
    dec = [int(c) for c in cfg["comunes"]["cortes_decision"]]
    d = S[S["anio"].isin(dec)].rename(columns={"liga": "liga_d", "team": "team_d"})
    out = {"n": int(len(d)), "por_corte": d.groupby("anio").size().to_dict()}
    if len(d) < 50:
        return out
    m = monotonia(d, ["d_pred"], B, semilla, ref="d_real")
    out["spearman"] = m["d_pred"]
    out["pasa"] = bool(m["d_pred"]["ic95"][0] > 0)
    out["emd_rho"] = float((Z + Z80) * m["d_pred"]["ee"])
    out["potencia_sembrada"] = emd_monotonia(d, [0.05, 0.10, 0.15], int(cfg["potencia"]["replicas_minimas"]), 300, semilla + 1,
                                              ref="d_real")
    out["dt_d_pred"] = float(d["d_pred"].std())
    out["dt_d_real"] = float(d["d_real"].std())
    return out


# =============================================================================================== contexto: diagnóstico POST HOC
def post_hoc_contexto(cfg: dict, R: pd.DataFrame, e: pd.DataFrame, B: int, semilla: int, min_poss: float = 500.0) -> dict:
    """[POST HOC, 09-11-2026] ¿De dónde sale la mejora del término de contexto c_j?
    (i) ablación: sólo el nivel medio de los compañeros / sólo sus perfiles / los dos (el prerregistrado);
    (ii) contraste con un realizado que NO depende mecánicamente de los compañeros: el β RAPM de la temporada t+1 (F1 v4.0
    publicado, ajustado por compañeros y rivales; jugadores con ≥ min_poss posesiones). Si c_j mejora frente al on/off pero
    no frente al β de t+1, lo que añade es la dependencia del on/off respecto a los compañeros, no valor del jugador."""
    cortes = [int(c) for c in cfg["comunes"]["cortes"]]
    dec = [int(c) for c in cfg["comunes"]["cortes_decision"]]
    perf = [f"perfil_companeros_{k}" for k in range(4)]
    var = {"ctx_solo_nivel": ["nivel_companeros"], "ctx_solo_perfil": perf, "ctx_completo": ["nivel_companeros"] + perf}
    R = R.copy()
    keys = ["anio", "liga", "team", "persona_id"]
    gam = {}
    for n, comp in var.items():
        R[f"s_{n}"], g = puntuacion_contexto(R, e, cortes, comp)
        gam[n] = {str(a): dict(zip(["intercepto", "v"] + comp, x)) for a, x in g.items()}
        R[f"c_{n}"] = crudo(R, f"s_{n}", None)
    cols = [f"c_{n}" for n in var]
    e = e.drop(columns=[c for c in cols if c in e]).merge(
        R[R["fichaje"]].drop_duplicates(keys)[keys + cols].rename(columns={"liga": "liga_d", "team": "team_d"}),
        on=["anio", "liga_d", "team_d", "persona_id"], how="left")
    for c in cols:
        e = calibrar(e, c, cortes, c[2:])
    d = e[e["anio"].isin(dec) & e["onoff_ok"] & e["IM_onoff"].notna() & e["IP"].notna()].dropna(subset=list(var))
    c_all = ["IP", *var, "IM_onoff", "IM_aditivo"]
    m = monotonia(d, c_all, B, semilla)
    out = {"etiqueta": "POST HOC", "n": m["n"], "gamma": gam,
           "on_off": {c: m[c] for c in c_all},
           "frente_IP": {n: diferencia(m, n, "IP", c_all) for n in var},
           "ctx_completo_menos_IM_v40": diferencia(m, "ctx_completo", "IM_onoff", c_all),
           "ctx_completo_menos_aditivo": diferencia(m, "ctx_completo", "IM_aditivo", c_all),
           "por_corte": {str(a): {c: spearman(d.loc[d["anio"] == a, c], d.loc[d["anio"] == a, "net_rtg_aj_onoff"]) for c in ("IP", "ctx_completo", "IM_onoff")} for a in dec}}
    elite = set(cfg["comunes"]["segmentos"]["elite_club"])
    me = monotonia(d[d["liga_d"].isin(elite)], ["IP", "ctx_completo", "IM_onoff"], B, semilla + 1)
    out["elite_club"] = {c: me[c] for c in ("IP", "ctx_completo", "IM_onoff")} | {"n": me["n"]}
    # (ii) β RAPM realizado en t+1
    cfg40 = CE.cargar_v40(cfg)
    partes = []
    for a in dec:
        f = CE.RAIZ / cfg40["f1"]["salidas"]["rapm"] / f"{a + 1}-{str(a + 2)[-2:]}.csv.gz"
        if f.exists():
            t = pd.read_csv(f, usecols=["persona_id", "beta", "poss"], dtype={"persona_id": str})
            partes.append(t.assign(anio=a).rename(columns={"beta": "beta_t1", "poss": "poss_t1"}))
    if partes:
        T = pd.concat(partes).sort_values("poss_t1").drop_duplicates(["anio", "persona_id"], keep="last")
        x = d.merge(T, on=["anio", "persona_id"], how="inner")
        x = x[x["poss_t1"] >= min_poss]
        mb = monotonia(x, ["IP", "ctx_completo", "ctx_solo_nivel", "ctx_solo_perfil", "IM_onoff", "beta"], B, semilla + 2, ref="beta_t1")
        cc = ["IP", "ctx_completo", "ctx_solo_nivel", "ctx_solo_perfil", "IM_onoff", "beta"]
        out["beta_rapm_t1"] = {"n": mb["n"], "min_poss": min_poss, **{c: mb[c] for c in cc},
                               "ctx_completo_menos_IP": diferencia(mb, "ctx_completo", "IP", cc),
                               "ctx_solo_nivel_menos_IP": diferencia(mb, "ctx_solo_nivel", "IP", cc),
                               "IP_menos_IM_v40": diferencia(mb, "IP", "IM_onoff", cc)}
    # nivel de los compañeros frente al on/off con el Impacto en pista fijo (correlación parcial de rangos)
    from scipy.stats import rankdata as rk
    rr = {c: rk(d[c]) for c in ("net_rtg_aj_onoff", "IP", "nivel_companeros")}
    X = np.c_[np.ones(len(d)), rr["IP"]]
    res_y = rr["net_rtg_aj_onoff"] - X @ np.linalg.lstsq(X, rr["net_rtg_aj_onoff"], rcond=None)[0]
    res_c = rr["nivel_companeros"] - X @ np.linalg.lstsq(X, rr["nivel_companeros"], rcond=None)[0]
    out["parcial_onoff_nivel_companeros_dado_IP"] = float(np.corrcoef(res_y, res_c)[0, 1])
    return out
