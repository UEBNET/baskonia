"""D2 · β v4.2: β RAPM con historial del jugador (configs/v42.yaml → motor_v42.piezas.beta_v42 y examen_beta).

[DATO] El β v4.0 (bbequipo.rapm, capa 1) es un β por PERSONA-TEMPORADA: cada temporada tiene su propio β, informado sólo por
los tramos de esa temporada y por el prior g(x̃) del perfil de esa temporada. El ÚNICO puente entre temporadas es que g lleva
como rasgo el RAPM normalizado (v3.2, en pista, de una liga) de la temporada ANTERIOR (f1.prior.rasgos_temporada_anterior:
orapm_th, drapm_th de t−1). No hay agregación explícita de los β de varias temporadas. Por eso la comparación es
β v4.0 (temporada t) frente a β v4.0 + Kalman explícito sobre sus estimaciones por temporada (β v4.2).

Modelo (mismo filtro que D1, bbequipo.v42.historial):
    observación de la temporada s:  y_s = β̂_s (v4.0),  var = c·sd²_β,s  (sd de Hutchinson del ajuste v4.0)
    estado:  θ_s = θ_{s−1} + η,  η ~ N(0, τ²) por año (un hueco de k años suma k·τ²)
    previa de la primera temporada:  N(μ_pos, σ²_pos) por posición (pos3 del perfil v4.0 de esa temporada), por momentos
τ² y c por máxima verosimilitud de las innovaciones un paso adelante.

Sin fuga: en el corte t las observaciones son los β del ajuste v4.0 del corte t (data/modelos/v4_0/rapm_multiliga/examen/
beta_corte_<t>.csv.gz: tramos, prior y τ con temporadas ≤ t); τ² y c se ajustan con esas mismas filas; el valor filtrado
en s usa temporadas ≤ s.

Examen prerregistrado (motor_v42.examen_beta; cortes de decisión 2022–2024, 2021 calibra y sólo se informa):
  (a) Spearman con el on/off ajustado realizado de t+1 (net_rtg_aj_onoff, filas jugador-equipo con ≥ 300 min, el realizado
      de F2 v4.1): β v4.0 de t frente a β v4.2 (m_t). Pasa si IC95 inferior de (ρ_v42 − ρ_v40) ≥ −0,02.
  (b) MAE frente al β de t+1: pasa si IC95 superior de (MAE_v42 − MAE_v40) < 0.
  Bootstrap B = 2000: (a) por equipo-temporada (como F2 v4.1), (b) por persona (configs/v42.yaml → bootstrap.unidad).

    python -m bbequipo.v42.beta            → data/modelos/v4_2/beta/examen_d2_beta.json (+ filas del examen)
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from .historial import CFG, RAIZ, Z80, ajustar, filtrar

V40 = RAIZ / "data" / "modelos" / "v4_0"
DIR_RAPM = V40 / "rapm_multiliga"
DIR_PERF = V40 / "perfiles"
ROLES = RAIZ / "data" / "modelos" / "roles" / "player_role_season.csv.gz"
SALIDA = RAIZ / "data" / "modelos" / "v4_2" / "beta"
MIN_EXAMEN = 300.0
MARGEN_SPEARMAN = -0.02
SEMILLA = 20261109
CORTES = [int(CFG["cortes"]["calibracion"])] + [int(x) for x in CFG["cortes"]["decision"]]
DECISION = [int(x) for x in CFG["cortes"]["decision"]]
B = int(CFG["bootstrap"]["B"])


def temp(a: int) -> str:
    return f"{a}-{str(a + 1)[-2:]}"


# =============================================================================================== datos
def perfiles() -> pd.DataFrame:
    """pos3 (registro con más minutos) y minutos totales por persona-temporada (perfil v4.0 de cada temporada)."""
    fr = []
    for t in CFG["temporadas"]:
        f = DIR_PERF / f"{t}.csv.gz"
        if f.exists():
            fr.append(pd.read_csv(f, usecols=["persona_id", "temporada", "pos3", "min"], dtype={"persona_id": str}, low_memory=False))
    p = pd.concat(fr, ignore_index=True)
    p["min"] = pd.to_numeric(p["min"], errors="coerce").fillna(0.0)
    p["anio"] = p["temporada"].str[:4].astype(int)
    pos = p.sort_values("min").groupby(["persona_id", "anio"])["pos3"].last()
    mins = p.groupby(["persona_id", "anio"])["min"].sum()
    return pd.DataFrame({"pos3": pos, "min_temp": mins}).reset_index()


def betas_corte(t: int) -> pd.DataFrame:
    b = pd.read_csv(DIR_RAPM / "examen" / f"beta_corte_{t}.csv.gz", dtype={"persona_id": str})
    b["anio"] = b["temporada"].str[:4].astype(int)
    return b


def betas_producto() -> pd.DataFrame:
    fr = [pd.read_csv(DIR_RAPM / f"{t}.csv.gz", usecols=["persona_id", "temporada", "beta", "beta_sd", "poss", "liga_principal"],
                      dtype={"persona_id": str}) for t in CFG["temporadas"] if (DIR_RAPM / f"{t}.csv.gz").exists()]
    b = pd.concat(fr, ignore_index=True)
    b["anio"] = b["temporada"].str[:4].astype(int)
    return b


def observaciones(b: pd.DataFrame, P: pd.DataFrame) -> pd.DataFrame:
    """Formato del filtro de D1: persona_id, anio, y, v (sd²), min (posesiones), pos3."""
    o = b[["persona_id", "anio", "beta", "beta_sd", "poss"]].merge(P[["persona_id", "anio", "pos3"]], on=["persona_id", "anio"], how="left")
    o = o[np.isfinite(o["beta"]) & np.isfinite(o["beta_sd"]) & (o["beta_sd"] > 0)]
    o["pos3"] = o["pos3"].where(o["pos3"].isin(("E", "A", "I")), "A")
    o = o.rename(columns={"beta": "y", "poss": "min"})
    o["v"] = o.pop("beta_sd") ** 2
    return o[["persona_id", "anio", "y", "v", "min", "pos3"]].sort_values(["persona_id", "anio"]).reset_index(drop=True)


def realizado() -> pd.DataFrame:
    r = pd.read_csv(ROLES, usecols=["liga", "temporada", "team_id", "persona_id", "net_rtg_aj_onoff", "min_total"],
                    dtype={"team_id": str, "persona_id": str}, low_memory=False)
    r = r[(r["min_total"] >= MIN_EXAMEN) & r["net_rtg_aj_onoff"].notna()]
    r = r.sort_values("min_total", ascending=False).drop_duplicates(["liga", "temporada", "team_id", "persona_id"])
    r["anio"] = r["temporada"].str[:4].astype(int)
    return r.reset_index(drop=True)


# =============================================================================================== utilidades
def spearman(x, y) -> float:
    return float(np.corrcoef(rankdata(x), rankdata(y))[0, 1])


def pct_liga(d: pd.DataFrame, col: str) -> pd.Series:
    """Percentil del predictor dentro de (liga, temporada) de t+1: el on/off es relativo al equipo y β lleva el nivel de la liga."""
    return d.groupby(["liga", "temporada"])[col].rank(pct=True)


def grupos(keys: pd.DataFrame) -> list[np.ndarray]:
    k = pd.factorize(pd.MultiIndex.from_frame(keys.astype(str)))[0]
    o = np.argsort(k, kind="stable")
    return np.split(o, np.flatnonzero(np.diff(k[o])) + 1)


def ic(v) -> list[float]:
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    return [float(np.quantile(v, .025)), float(np.quantile(v, .975))]


def alineacion(x_t: pd.DataFrame, obj_t: pd.DataFrame) -> tuple[float, float, int]:
    """y_obj = a + b·β_corte en la temporada t (sin mirar t+1): pasa el ajuste del corte a la escala del ajuste objetivo.
    [DATO] el nivel global de β no está identificado por los tramos (lo fija g) y cambia de un ajuste a otro (p. ej. la media
    de 2022-23 es −0,10 en el corte 2022 y +3,78 en el producto); sin alinear, el MAE mediría ese desfase y no el método."""
    j = x_t[["persona_id", "y"]].merge(obj_t[["persona_id", "beta"]], on="persona_id")
    b, a = np.polyfit(j["y"].to_numpy(float), j["beta"].to_numpy(float), 1)
    return float(a), float(b), int(len(j))


# =============================================================================================== un corte
def filtrar_corte(o: pd.DataFrame, t: int) -> tuple[pd.DataFrame, dict]:
    tr = o[o["anio"] <= t]
    par = ajustar(tr)
    f = filtrar(tr, par["tau2"], par["c"], par["pp"])
    return f, par


def filas_corte(t: int, P: pd.DataFrame, prod: pd.DataFrame, R: pd.DataFrame, esquema: str = "corte") -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Filas del examen MAE (persona) y Spearman (jugador-equipo de t+1) del corte t.
    esquema = "corte": observaciones del ajuste v4.0 del corte t (sin fuga; principal).
    esquema = "producto": observaciones del β publicado (ajuste con todas las temporadas: fuga leve por γ, τ, interceptos; sensibilidad)."""
    b = betas_corte(t) if esquema == "corte" else prod[prod["anio"] <= t]
    o = observaciones(b, P)
    f, par = filtrar_corte(o, t)
    ft = f[f["anio"] == t].copy()
    ft["sd_t"] = np.sqrt(ft["v"])
    info = {"tau2": par["tau2"], "c": par["c"], "nll": par["nll"], "n_obs": int(len(o[o["anio"] <= t])),
            "previa_pos": {k: [float(x) for x in v] for k, v in par["pp"].items()},
            "personas_t": int(len(ft)), "temporadas_previas_media": float(f[f["anio"] <= t].groupby("persona_id").size().reindex(ft["persona_id"]).mean())}

    # objetivos β de t+1: (i) producto (principal), (ii) ajuste del corte t+1 cuando existe (sensibilidad)
    objetivos = {"producto": prod}
    if esquema == "corte" and (DIR_RAPM / "examen" / f"beta_corte_{t + 1}.csv.gz").exists():
        objetivos["corte_t1"] = betas_corte(t + 1)
    M = []
    for nom, ob in objetivos.items():
        a, bb, nal = (0.0, 1.0, 0) if (esquema == "producto" and nom == "producto") else alineacion(ft, ob[ob["anio"] == t])
        info[f"alineacion_{nom}"] = {"a": a, "b": bb, "n": nal}
        y1 = ob[ob["anio"] == t + 1][["persona_id", "beta", "beta_sd"]].rename(columns={"beta": "y1", "beta_sd": "sd1"})
        x = ft.merge(y1, on="persona_id").merge(P[["persona_id", "anio", "min_temp"]], on=["persona_id", "anio"], how="left")
        x = x.merge(P[P["anio"] == t + 1][["persona_id", "min_temp"]].rename(columns={"min_temp": "min_t1"}), on="persona_id", how="left")
        x = x[(x["min_temp"] >= MIN_EXAMEN) & (x["min_t1"] >= MIN_EXAMEN)]
        p40, p42 = a + bb * x["y"], a + bb * x["m"]
        S42 = bb ** 2 * (x["P"] + par["tau2"]) + par["c"] * x["sd1"] ** 2
        M.append(pd.DataFrame({
            "corte": t, "objetivo": nom, "persona_id": x["persona_id"].to_numpy(),
            "e40": np.abs(x["y1"] - p40).to_numpy(), "e42": np.abs(x["y1"] - p42).to_numpy(),
            "e40_sin_alinear": np.abs(x["y1"] - x["y"]).to_numpy(), "e42_sin_alinear": np.abs(x["y1"] - x["m"]).to_numpy(),
            "cub42": (np.abs(x["y1"] - p42) <= Z80 * np.sqrt(S42)).to_numpy(),
            "cub40_mostrado": (np.abs(x["y1"] - p40) <= Z80 * bb * x["sd_t"]).to_numpy(),
            "cub40_predictivo": (np.abs(x["y1"] - p40) <= Z80 * np.sqrt(bb ** 2 * x["v"] + x["sd1"] ** 2)).to_numpy(),
            "ancho42_nivel": (2 * Z80 * np.sqrt(x["P"])).to_numpy(), "ancho40_nivel": (2 * Z80 * x["sd_t"]).to_numpy(),
            "ancho42_pred": (2 * Z80 * np.sqrt(S42)).to_numpy(), "ancho40_pred": (2 * Z80 * np.sqrt(bb ** 2 * x["v"] + x["sd1"] ** 2)).to_numpy(),
            "ratio_ancho_nivel": np.sqrt(x["P"] / x["v"]).to_numpy(),
            "r_v42": np.abs(x["y1"] - p42).to_numpy(), "s_v42": np.sqrt(S42).to_numpy(),
            "r_v40_predictivo": np.abs(x["y1"] - p40).to_numpy(), "s_v40_predictivo": np.sqrt(bb ** 2 * x["v"] + x["sd1"] ** 2).to_numpy()}))
    M = pd.concat(M, ignore_index=True)

    s = R[R["anio"] == t + 1].merge(ft[["persona_id", "y", "m", "P", "sd_t"]].rename(columns={"y": "beta40", "m": "beta42"}), on="persona_id")
    s["corte"] = t
    s["p40"], s["p42"] = pct_liga(s, "beta40"), pct_liga(s, "beta42")
    return M, s, info


# =============================================================================================== bootstrap
def boot_spearman(s: pd.DataFrame, semilla: int, unidad: str = "equipo") -> dict:
    cols = ["liga", "temporada", "team_id"] if unidad == "equipo" else ["persona_id"]
    cl = grupos(s[cols])
    y, a, b = s["net_rtg_aj_onoff"].to_numpy(float), s["p40"].to_numpy(float), s["p42"].to_numpy(float)
    r40, r42 = spearman(a, y), spearman(b, y)
    rng = np.random.default_rng(semilla)
    bs = np.empty((B, 2))
    for i in range(B):
        idx = np.concatenate([cl[k] for k in rng.integers(0, len(cl), len(cl))])
        bs[i] = spearman(a[idx], y[idx]), spearman(b[idx], y[idx])
    d = bs[:, 1] - bs[:, 0]
    return {"n": int(len(s)), "conglomerados": int(len(cl)), "unidad": unidad, "rho_v40": r40, "rho_v42": r42,
            "rho_v40_ic95": ic(bs[:, 0]), "rho_v42_ic95": ic(bs[:, 1]), "diferencia": r42 - r40, "diferencia_ic95": ic(d)}


def boot_mae(h: pd.DataFrame, semilla: int, e40: str = "e40", e42: str = "e42") -> dict:
    u, inv = np.unique(h["persona_id"].to_numpy(), return_inverse=True)
    dd = (h[e42] - h[e40]).to_numpy(float)
    rng = np.random.default_rng(semilla)
    bs = np.empty(B)
    for i in range(B):
        k = rng.multinomial(len(u), np.full(len(u), 1 / len(u)))[inv]
        bs[i] = (k * dd).sum() / k.sum()
    return {"n": int(len(h)), "personas": int(len(u)), "mae_v40": float(h[e40].mean()), "mae_v42": float(h[e42].mean()),
            "diferencia": float(dd.mean()), "diferencia_ic95": ic(bs)}


def recalibracion(Mp: pd.DataFrame) -> dict:
    """Conformal con el corte de calibración (configs/v42.yaml → motor_v42.recalibracion): factor k del radio del 80 %
    tal que la cobertura en 2021 sea 0,80; cobertura de los cortes de decisión con ese k (informado; no decide β)."""
    out = {}
    for v, cub in (("v42", "cub42"), ("v40_predictivo", "cub40_predictivo")):
        r, S = Mp[f"r_{v}"].to_numpy(float), Mp[f"s_{v}"].to_numpy(float)
        cal = (Mp["corte"] == CORTES[0]).to_numpy()
        k = float(np.quantile(r[cal] / (Z80 * S[cal]), 0.80))
        d = Mp["corte"].isin(DECISION).to_numpy()
        out[v] = {"k": k, "cobertura80_decision": float(np.mean(r[d] <= k * Z80 * S[d])),
                  "ancho80_mediano_decision": float(np.median(2 * k * Z80 * S[d])),
                  "por_corte": {int(t): float(np.mean(r[(Mp["corte"] == t).to_numpy()] <= k * Z80 * S[(Mp["corte"] == t).to_numpy()]))
                                for t in DECISION}}
    return out


def estimacion_anclas(S: pd.DataFrame) -> dict:
    """[LECTURA] cuánto movería β v4.2 al componente β de IMPACTO (capa 4 v4.0 e Impacto en pista v4.1 usan el β más
    reciente ≤ t vía Insumos.valor): percentil dentro de (liga, temporada) de β v4.0 frente a β v4.2 en las filas del examen.
    NIVEL KERNO no usa β (es el percentil de la contribución del motor v3.3): no cambia por D2-β."""
    d = S[S["corte"].isin(DECISION)]
    dp = 100 * (d["p42"] - d["p40"]).abs()
    return {"n": int(len(d)), "spearman_p40_p42": spearman(d["p40"], d["p42"]),
            "delta_percentil_abs_mediana": float(dp.median()), "delta_percentil_abs_p90": float(dp.quantile(.9)),
            "fraccion_mueve_mas_de_10_puntos": float((dp > 10).mean()),
            "ratio_mediano_sd": float(np.median(np.sqrt(d["P"]) / d["sd_t"]))}


def resumen_intervalos(h: pd.DataFrame) -> dict:
    return {"cobertura80_v42_predictivo": float(h["cub42"].mean()), "cobertura80_v40_mostrado": float(h["cub40_mostrado"].mean()),
            "cobertura80_v40_predictivo": float(h["cub40_predictivo"].mean()),
            "ratio_mediano_ancho_nivel_v42_v40": float(h["ratio_ancho_nivel"].median()),
            "ancho80_nivel_mediano": {"v42": float(h["ancho42_nivel"].median()), "v40": float(h["ancho40_nivel"].median())},
            "ancho80_predictivo_mediano": {"v42": float(h["ancho42_pred"].median()), "v40": float(h["ancho40_pred"].median())}}


# =============================================================================================== examen
def examen(progreso=print) -> dict:
    t0 = time.time()
    P, prod, R = perfiles(), betas_producto(), realizado()
    Ms, Ss, info = [], [], {}
    for t in CORTES:
        M, S, inf = filas_corte(t, P, prod, R, "corte")
        Ms.append(M); Ss.append(S); info[t] = inf
        progreso(f"  corte {t}: τ²={inf['tau2']:.3f} c={inf['c']:.3f} · MAE n={int((M['objetivo'] == 'producto').sum())} · "
                 f"Spearman n={len(S)} · {time.time() - t0:.0f} s", flush=True)
    M, S = pd.concat(Ms, ignore_index=True), pd.concat(Ss, ignore_index=True)
    Mp = M[M["objetivo"] == "producto"]
    dec = lambda x: x[x["corte"].isin(DECISION)]  # noqa: E731

    res_cortes = {}
    for t in CORTES:
        sem = SEMILLA + t
        mt = Mp[Mp["corte"] == t]
        res_cortes[t] = {**info[t], "spearman": boot_spearman(S[S["corte"] == t], sem), "mae": boot_mae(mt, sem + 1),
                         "intervalos": resumen_intervalos(mt), "papel": "calibracion" if t not in DECISION else "decision"}
        progreso(f"  corte {t}: ρ40={res_cortes[t]['spearman']['rho_v40']:.3f} ρ42={res_cortes[t]['spearman']['rho_v42']:.3f} "
                 f"ΔMAE={res_cortes[t]['mae']['diferencia']:+.3f} {res_cortes[t]['mae']['diferencia_ic95']} · {time.time() - t0:.0f} s", flush=True)

    conj = {"spearman": boot_spearman(dec(S), SEMILLA + 1), "mae": boot_mae(dec(Mp), SEMILLA + 2), "intervalos": resumen_intervalos(dec(Mp))}
    pasa_a = conj["spearman"]["diferencia_ic95"][0] >= MARGEN_SPEARMAN
    pasa_b = conj["mae"]["diferencia_ic95"][1] < 0
    progreso(f"  conjunto: (a) {pasa_a} (b) {pasa_b} · {time.time() - t0:.0f} s", flush=True)

    # sensibilidades (informadas; no deciden)
    conj["recalibracion_conformal_2021"] = recalibracion(Mp)
    conj["estimacion_anclas"] = estimacion_anclas(S)
    sens = {
        "spearman_bootstrap_por_persona": boot_spearman(dec(S), SEMILLA + 3, "persona"),
        "spearman_beta_crudo_sin_percentil_liga": {
            "rho_v40": spearman(dec(S)["beta40"], dec(S)["net_rtg_aj_onoff"]), "rho_v42": spearman(dec(S)["beta42"], dec(S)["net_rtg_aj_onoff"])},
        "mae_sin_alinear_objetivo_producto": boot_mae(dec(Mp), SEMILLA + 4, "e40_sin_alinear", "e42_sin_alinear"),
    }
    Mc = M[(M["objetivo"] == "corte_t1")]
    sens["mae_objetivo_corte_t1_2022_2023"] = boot_mae(dec(Mc), SEMILLA + 5)
    sens["mae_objetivo_corte_t1_2022_2023"]["intervalos"] = resumen_intervalos(dec(Mc))
    # esquema «producto»: Kalman sobre el β publicado (fuga leve por hiperparámetros globales)
    Mq, Sq, iq = [], [], {}
    for t in DECISION:
        m_, s_, i_ = filas_corte(t, P, prod, R, "producto")
        Mq.append(m_); Sq.append(s_); iq[t] = {"tau2": i_["tau2"], "c": i_["c"]}
    Mq, Sq = pd.concat(Mq, ignore_index=True), pd.concat(Sq, ignore_index=True)
    sens["esquema_producto"] = {"parametros": iq, "spearman": boot_spearman(Sq, SEMILLA + 6),
                                "mae": boot_mae(Mq[Mq["objetivo"] == "producto"], SEMILLA + 7),
                                "intervalos": resumen_intervalos(Mq[Mq["objetivo"] == "producto"])}
    progreso(f"  sensibilidades · {time.time() - t0:.0f} s", flush=True)

    pasa = bool(pasa_a and pasa_b)
    res = {
        "version": "v4.2", "pieza": "D2 · β v4.2", "prerregistro": "configs/v42.yaml → motor_v42.examen_beta",
        "generado": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "beta_v40_agrega_temporadas": ("no explícitamente: β por persona-temporada; el prior g lleva el RAPM normalizado v3.2 de la "
                                       "temporada anterior (orapm_th, drapm_th de t−1) como rasgo. β v4.2 = Kalman sobre los β v4.0 por temporada."),
        "diseno": {
            "observaciones": "β v4.0 del ajuste del corte t (examen/beta_corte_<t>.csv.gz), var = c·beta_sd²",
            "objetivo_mae": "β v4.0 publicado de t+1 (rapm_multiliga/<t+1>.csv.gz), predictor alineado a su escala con a + b·β (temporada t)",
            "poblacion_mae": f"personas con β en t y t+1 y ≥ {MIN_EXAMEN:.0f} min (perfil v4.0, todas sus ligas) en t y en t+1",
            "spearman": f"filas jugador-equipo de t+1 con ≥ {MIN_EXAMEN:.0f} min y net_rtg_aj_onoff; predictor en percentil dentro de (liga, temporada t+1)",
            "bootstrap": {"B": B, "spearman": "equipo-temporada", "mae": "persona"},
            "cortes": {"calibracion": CORTES[0], "decision": DECISION}},
        "cortes": {str(k): v for k, v in res_cortes.items()},
        "conjunto_decision": conj,
        "criterios": {"a_spearman_no_peor": {"regla": "IC95 inferior de ρ_v42 − ρ_v40 ≥ −0,02", "pasa": bool(pasa_a)},
                      "b_mae_mejor": {"regla": "IC95 superior de MAE_v42 − MAE_v40 < 0", "pasa": bool(pasa_b)}},
        "pasa": pasa,
        "decision": "β v4.2 sustituye al β v4.0" if pasa else "se mantiene el β v4.0 (β v4.2 no pasa)",
        "sensibilidades": sens,
        "tiempo_s": round(time.time() - t0, 1),
    }
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "examen_d2_beta.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    M.to_csv(SALIDA / "filas_mae.csv.gz", index=False)
    S[["corte", "liga", "temporada", "team_id", "persona_id", "min_total", "net_rtg_aj_onoff", "beta40", "beta42", "P", "sd_t", "p40", "p42"]
      ].to_csv(SALIDA / "filas_spearman.csv.gz", index=False)
    return res


if __name__ == "__main__":
    r = examen()
    print(json.dumps({"criterios": r["criterios"], "decision": r["decision"], "tiempo_s": r["tiempo_s"]}, ensure_ascii=False, indent=1))
