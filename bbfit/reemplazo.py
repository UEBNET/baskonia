"""Fase 4 — reemplazo de rol: formulación propia del proyecto.

Principios y su implementación (ecuación → función; detalle en docs/checkpoints/F4.md):

1. La producción no es invariante al rol. La tabla `produccion_por_rol` (liga × rol) mide cómo cambian USG%,
   TS% y puntos por 100 posesiones entre roles, y `proyectar_a_rol` condiciona la proyección al rol de destino:
       ΔUSG = USG_dest(rol) − USG_orig(rol)  (desplazamiento típico entre roles en la liga),
       TS'  = TS + β_i·ΔUSG,      P100' = P100 · (USG'/USG) · (TS'/TS)
   con β_i muestreado de su distribución posterior (intervalos por Monte Carlo).
2. Curva uso-eficiencia con rendimientos decrecientes: ΔTS% ≈ β_i·ΔUSG% (y ΔTOV% ≈ γ_i·ΔUSG%), con β_i estimado
   con variación DENTRO del jugador (partido a partido, centrado por jugador-equipo-temporada) y agrupamiento
   parcial por arquetipo/posición (bayes empírico):  β_i* = w_i·β̂_i + (1 − w_i)·β_g,  w_i = τ_g²/(τ_g² + se_i²).
3. Vacío de rol y redistribución: una plantilla es un sistema de suma fija (Σ minutos = 5·duración; Σ USG% en
   pista = 100 %, es decir Σ_i min_i·USG_i = 100·minutos de partido). `redistribuir` calcula lo que libera cada
   salida y lo que absorbe cada llegada y reescala a los que siguen.
4. Libro de minutos por rol entre temporadas consecutivas de cada club: volumen de rol V_k = Σ_i m_i·s_ik
   (m = minutos por partido del equipo, s = pertenencia blanda al rol). Para los que siguen, exactamente:
       m'·s' − m·s = (m' − m)·s  [desplazamiento de minutos]  +  m'·(s' − s)  [desplazamiento de rol]
   salidas D_k, llegadas I_k y tasa de relleno R_k = (I_k + DM_k + DR_k)/D_k (sin tope). Transiciones de rol de
   los que siguen (≥ N minutos en ambas) en matriz dura y blanda (Σ s ⊗ s'). Relación con el cambio de Net del
   equipo: descriptiva, con intervalos bootstrap — ASOCIACIÓN, no causalidad.
5. Calidad de los compañeros: nivel L medio de los compañeros ponderado por minutos compartidos (parejas).
6. Asignación endógena de minutos (para el simulador): `asignar_minutos`, Plackett-Luce sobre una puntuación
   (nivel + encaje posicional) con restricciones (Σ minutos, tope por jugador, mínimos por posición en el
   quinteto inicial) y las tendencias del entrenador (tamaño de rotación y curva de reparto por rango),
   devolviendo probabilidades de rol por Monte Carlo.
Parámetros en configs/reemplazo.yaml.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from . import datos as D
from .config import DIR_MOD, cargar
from .roles import ROLES, clasificar

DIR_REEMP = DIR_MOD / "reemplazo"
DIR_ROLES = DIR_MOD / "roles"


def _cfg() -> dict:
    return cargar("reemplazo")


def _z(nivel: float) -> float:
    return float(stats.norm.ppf(0.5 + nivel / 2))


# =============================================================================== 2. uso-eficiencia

def _pendiente_intra(df: pd.DataFrame, y: str, x: str, w: str, grupo: str) -> pd.DataFrame:
    """Pendiente por persona con variación dentro de `grupo` (centrado ponderado), su error estándar y n."""
    d = df[list(dict.fromkeys(["persona_id", grupo, x, y, w]))].dropna().copy()
    d = d[d[w] > 0]
    sw = d.groupby(grupo)[w].transform("sum")
    d["xc"] = d[x] - (d[x] * d[w]).groupby(d[grupo]).transform("sum") / sw
    d["yc"] = d[y] - (d[y] * d[w]).groupby(d[grupo]).transform("sum") / sw
    d["wxx"] = d[w] * d["xc"] ** 2
    d["wxy"] = d[w] * d["xc"] * d["yc"]
    g = d.groupby("persona_id")
    sxx, sxy = g["wxx"].sum(), g["wxy"].sum()
    beta = sxy / sxx.replace(0, np.nan)
    d["b"] = d["persona_id"].map(beta)
    d["res2"] = d[w] * (d["yc"] - d["b"] * d["xc"]) ** 2
    n = g.size()
    k = g[grupo].nunique()
    gl = (n - k - 1).clip(lower=0)
    # varianza residual común (por unidad de peso) a todas las personas: con 3-5 tramos por jugador la varianza
    # residual individual tiene 1-3 grados de libertad y haría inestable el error estándar
    validas = (gl > 0) & sxx.gt(0)
    s2 = float(d.groupby("persona_id")["res2"].sum()[validas].sum() / gl[validas].sum()) if validas.any() else np.nan
    se = np.sqrt(s2 / sxx.replace(0, np.nan))
    se = se.where(gl > 0)
    return pd.DataFrame({"beta_bruto": beta, "se": se, "n": n, "n_grupos": k}).reset_index()


def instrumento_vacio(pj: pd.DataFrame, min_pct_rotacion: float) -> pd.Series:
    """Instrumento de «vacío de rol» por fila partido-jugador: Σ de la cuota de uso de temporada de los compañeros de
    rotación (MIN% de temporada >= umbral) que NO juegan ese partido estando en la plantilla (ausencias entre su
    primer y último partido). Mueve el uso del jugador sin depender de su acierto de ese día."""
    k = ["liga", "temporada", "team_id"]
    j = pj[pj["jugo"]]
    uso = (j["fga"] + j["coef_tl"] * j["fta"]).groupby([j[c] for c in k] + [j["player_id"]]).sum()
    sec = j.groupby(k + ["player_id"])["sec"].sum()
    dur = j.groupby(k + ["player_id"])["dur_s"].sum()
    cuota = uso / uso.groupby(level=[0, 1, 2]).transform("sum")
    rot = cuota[(sec / dur) >= min_pct_rotacion].rename("cuota_rot")
    p = pj[k + ["game_id", "player_id", "jugo"]].merge(rot.reset_index(), on=k + ["player_id"], how="left")
    p["aus"] = np.where(~p["jugo"] & p["cuota_rot"].notna(), p["cuota_rot"], 0.0)
    tot = p.groupby(k + ["game_id"])["aus"].sum()
    idx = pd.MultiIndex.from_frame(pj[k + ["game_id"]])
    return pd.Series(tot.reindex(idx).fillna(0).to_numpy(), index=pj.index)


def _iv_intra(df: pd.DataFrame, y: str, x: str, zi: str, w: str, grupo: str, f_min: float) -> pd.DataFrame:
    """Pendiente con variable instrumental por persona, con centrado dentro de `grupo` (jugador-equipo-temporada):
    β̂_i = Σ w·z̃·ỹ / Σ w·z̃·x̃,  se_i² = σ²·Σ w·z̃² / (Σ w·z̃·x̃)²  (σ² residual común);  F_i de primera etapa."""
    d = df[list(dict.fromkeys(["persona_id", grupo, x, y, zi, w]))].dropna().copy()
    d = d[d[w] > 0]
    sw = d.groupby(grupo)[w].transform("sum")
    for c_ in (x, y, zi):
        d[c_ + "_c"] = d[c_] - (d[c_] * d[w]).groupby(d[grupo]).transform("sum") / sw
    d["zx"] = d[w] * d[zi + "_c"] * d[x + "_c"]
    d["zy"] = d[w] * d[zi + "_c"] * d[y + "_c"]
    d["zz"] = d[w] * d[zi + "_c"] ** 2
    g = d.groupby("persona_id")
    szx, szy, szz = g["zx"].sum(), g["zy"].sum(), g["zz"].sum()
    beta = szy / szx.replace(0, np.nan)
    pi = szx / szz.replace(0, np.nan)
    d["b"], d["pi"] = d["persona_id"].map(beta), d["persona_id"].map(pi)
    d["e2"] = d[w] * (d[y + "_c"] - d["b"] * d[x + "_c"]) ** 2
    d["v2"] = d[w] * (d[x + "_c"] - d["pi"] * d[zi + "_c"]) ** 2
    n, k = g.size(), g[grupo].nunique()
    gl = (n - k - 1).clip(lower=0)
    ok = (gl > 0) & szz.gt(0)
    s2 = float(d.groupby("persona_id")["e2"].sum()[ok].sum() / gl[ok].sum()) if ok.any() else np.nan
    s2v = float(d.groupby("persona_id")["v2"].sum()[ok].sum() / gl[ok].sum()) if ok.any() else np.nan
    se = np.sqrt(s2 * szz) / szx.abs().replace(0, np.nan)
    F = szx ** 2 / (szz.replace(0, np.nan) * s2v)
    se = se.where(ok & (F >= f_min))
    return pd.DataFrame({"beta_bruto": beta, "se": se, "n": n, "n_grupos": k, "f_primera_etapa": F}).reset_index()


def iv_grupo(df: pd.DataFrame, y: str, x: str, zi: str, w: str, grupo: str, por: str, B: int, semilla: int,
             nivel: float) -> pd.DataFrame:
    """Estimación con instrumento de cada grupo (`por`, p. ej. pos3) agregando todas sus filas, con intervalo por
    bootstrap de personas."""
    d = df[list(dict.fromkeys(["persona_id", grupo, por, x, y, zi, w]))].dropna().copy()
    sw = d.groupby(grupo)[w].transform("sum")
    for c_ in (x, y, zi):
        d[c_ + "_c"] = d[c_] - (d[c_] * d[w]).groupby(d[grupo]).transform("sum") / sw
    d["zx"] = d[w] * d[zi + "_c"] * d[x + "_c"]
    d["zy"] = d[w] * d[zi + "_c"] * d[y + "_c"]
    d["zz"] = d[w] * d[zi + "_c"] ** 2
    rng = np.random.default_rng(semilla)
    filas = []
    for gname, e in list(d.groupby(por)) + [("todos", d)]:
        pp = e.groupby("persona_id")[["zx", "zy", "zz"]].sum()
        b = pp["zy"].sum() / pp["zx"].sum()
        arr = pp.to_numpy()
        bs = []
        for _ in range(B):
            s_ = arr[rng.integers(0, len(arr), len(arr))].sum(0)
            bs.append(s_[1] / s_[0])
        fs = pp["zx"].sum() / pp["zz"].sum()
        filas.append({por: gname, "beta_iv": b, "beta_iv_sd": float(np.std(bs)),
                      "beta_iv_lo": float(np.quantile(bs, (1 - nivel) / 2)), "beta_iv_hi": float(np.quantile(bs, 1 - (1 - nivel) / 2)),
                      "primera_etapa": fs, "n_filas": len(e), "n_personas": len(pp)})
    return pd.DataFrame(filas)


def agrupamiento_parcial(est: pd.DataFrame, grupo: str, tau2_min: float, nivel: float,
                         objetivo: dict | None = None) -> pd.DataFrame:
    """Bayes empírico por grupo: β_g, τ_g² y contracción w_i = τ²/(τ² + se_i²).
    Sin `objetivo`: β_g = media ponderada y τ² de DerSimonian-Laird. Con `objetivo` {grupo: (β_g, var β_g)}:
    centro fijado (p. ej. la estimación de grupo con instrumento) y τ² por momentos alrededor de él:
    τ² = max(τ²_min, (Σ w_i (β̂_i − β_g)² − k) / Σ w_i),  w_i = 1/se_i²."""
    z = _z(nivel)
    out = []
    for g, d in est.groupby(grupo, dropna=False):
        ok = d["se"].notna() & np.isfinite(d["se"]) & (d["se"] > 0) & d["beta_bruto"].notna()
        di = d[ok]
        if objetivo is not None and g in objetivo and np.isfinite(objetivo[g][0]):
            bg, var_bg = objetivo[g]
            if len(di):
                wi = 1 / di["se"] ** 2
                Q = float((wi * (di["beta_bruto"] - bg) ** 2).sum())
                tau2 = max(tau2_min, (Q - len(di)) / float(wi.sum()))
            else:
                tau2 = np.nan
        elif len(di) >= 2:
            wi = 1 / di["se"] ** 2
            bg = float((wi * di["beta_bruto"]).sum() / wi.sum())
            Q = float((wi * (di["beta_bruto"] - bg) ** 2).sum())
            c = float(wi.sum() - (wi ** 2).sum() / wi.sum())
            tau2 = max(tau2_min, (Q - (len(di) - 1)) / c) if c > 0 else tau2_min
            var_bg = float(1 / (1 / (di["se"] ** 2 + tau2)).sum())
        elif len(di) == 1:
            bg, tau2, var_bg = float(di["beta_bruto"].iloc[0]), np.nan, float(di["se"].iloc[0] ** 2)
        else:
            bg, tau2, var_bg = np.nan, np.nan, np.nan
        d = d.copy()
        d["beta_grupo"], d["tau2_grupo"], d["n_grupo"] = bg, tau2, len(di)
        se2 = d["se"] ** 2
        w = tau2 / (tau2 + se2) if np.isfinite(tau2) else pd.Series(0.0, index=d.index)
        w = w.where(ok, 0.0)
        d["w"] = w
        d["beta_media"] = np.where(ok, w * d["beta_bruto"] + (1 - w) * bg, bg)
        var_post = np.where(ok, 1 / (1 / tau2 + 1 / se2) + (1 - w) ** 2 * var_bg if np.isfinite(tau2) else se2,
                            (tau2 if np.isfinite(tau2) else 0) + var_bg)
        d["beta_sd"] = np.sqrt(var_post)
        d["beta_lo"] = d["beta_media"] - z * d["beta_sd"]
        d["beta_hi"] = d["beta_media"] + z * d["beta_sd"]
        d["solo_grupo"] = ~ok
        out.append(d)
    return pd.concat(out, ignore_index=True) if out else est


_COLS_EST = ["beta_bruto", "se", "n", "n_grupos", "beta_grupo", "tau2_grupo", "n_grupo", "w", "beta_media", "beta_sd",
             "beta_lo", "beta_hi", "solo_grupo"]


def _estimar(df: pd.DataFrame, y: str, x: str, w: str, grupo: str, minimo: int, universo: pd.DataFrame,
             pos: pd.Series, c: dict, sufijo: str) -> pd.DataFrame:
    est = _pendiente_intra(df, y, x, w, grupo) if len(df) else pd.DataFrame(columns=["persona_id"] + _COLS_EST[:4])
    est = est[est["n"] >= minimo]
    est = universo.merge(est, on="persona_id", how="left")
    est["pos3"] = est["persona_id"].map(pos).fillna("NA")
    est = agrupamiento_parcial(est, "pos3", float(c["tau2_minimo"]), float(c["nivel_intervalo"]))
    return est.rename(columns={k: f"{k}_{sufijo}" for k in _COLS_EST})


def uso_eficiencia(pj: pd.DataFrame, temp_rec: pd.DataFrame, cfg: dict, tramos: pd.DataFrame | None = None) -> pd.DataFrame:
    """β (ΔTS% por +1 punto de USG%) y γ (ΔTOV% por +1 punto de USG%) por persona, con agrupamiento parcial.

    * `_ts` (principal): variable instrumental. Partido a partido dentro de jugador-equipo-temporada, el USG% se
      instrumenta con el vacío de rol del día (cuota de uso de los compañeros de rotación ausentes, z_vacio):
      β = Cov(z, TS)/Cov(z, USG). Centro de grupo = IV agregado por pos3 (intervalo bootstrap de personas);
      β_i propio sólo si su primera etapa es fuerte (F_i >= f_minimo_individual); contracción hacia el grupo.
    * `_ts_tramos` (diagnóstico): MCO entre tramos de rol y temporadas del mismo jugador (centrado por liga-temporada).
    * `_ts_partido` (diagnóstico): MCO partido a partido. Los dos MCO están sesgados al alza por selección (el uso se
      gana acertando): se publican para comparar, no para proyectar.
    * `_tov`: TOV% frente a USG% entre temporadas (caja; la fuente no da pérdidas por jugador y partido)."""
    c = cfg["uso_eficiencia"]
    pos = (temp_rec.dropna(subset=["pos3"]).groupby(["persona_id", "pos3"])["min_total"].sum()
           .reset_index().sort_values("min_total").drop_duplicates("persona_id", keep="last")
           .set_index("persona_id")["pos3"])
    nombres = temp_rec.sort_values("min_total").drop_duplicates("persona_id", keep="last").set_index("persona_id")
    universo = pd.DataFrame({"persona_id": temp_rec["persona_id"].unique()})
    # principal: variable instrumental (vacío de rol), partido a partido dentro de jugador-equipo-temporada
    pj = pj.copy()
    pj["z_vacio"] = instrumento_vacio(pj, float(c["vacio_min_pct_rotacion"]))
    g = pj[pj["jugo"]].copy()
    g["tsa"] = g["fga"] + g["coef_tl"] * g["fta"]
    g = g[g["tsa"] >= c["min_intentos_partido"]]
    g["grupo_intra"] = g["liga"] + "|" + g["temporada"] + "|" + g["team_id"].astype(str) + "|" + g["persona_id"]
    g["pos3_p"] = g["persona_id"].map(pos).fillna("NA")
    sem = int(cfg["semilla"])
    grp_ts = iv_grupo(g, "ts_pct", "usg_tiro", "z_vacio", "tsa", "grupo_intra", "pos3_p", int(c["bootstrap_grupo"]), sem,
                      float(c["nivel_intervalo"]))
    obj = {r["pos3_p"]: (r["beta_iv"], r["beta_iv_sd"] ** 2) for r in grp_ts.to_dict("records")}
    obj["NA"] = obj.get("todos", (np.nan, np.nan))      # sin posición: el centro de todos los jugadores
    est = _iv_intra(g, "ts_pct", "usg_tiro", "z_vacio", "tsa", "grupo_intra", float(c["f_minimo_individual"]))
    est = universo.merge(est[est["n"] >= c["min_partidos_jugador"]], on="persona_id", how="left")
    est["pos3"] = est["persona_id"].map(pos).fillna("NA")
    est = agrupamiento_parcial(est, "pos3", float(c["tau2_minimo"]), float(c["nivel_intervalo"]), objetivo=obj)
    ts_iv = est.rename(columns={k: f"{k}_ts" for k in _COLS_EST + ["f_primera_etapa"]})
    # diagnóstico 1: tramos y temporadas (MCO dentro de jugador; sesgo de selección: el uso se gana acertando)
    src = tramos if tramos is not None else temp_rec
    t = src[(src["fuente"] == "pbp")].copy()
    ng = t["n_partidos"] if "n_partidos" in t else t["gp"]
    t = t[(ng >= c["min_partidos_tramo"]) & (t["intentos_uso"] >= c["min_intentos_tramo"])].dropna(subset=["ts_pct", "usg_pct"])
    for col in ("ts_pct", "usg_pct"):
        t[col] = t[col] - t.groupby(["liga", "temporada"])[col].transform("mean")
    tst = _estimar(t, "ts_pct", "usg_pct", "intentos_uso", "persona_id", int(c["min_tramos_jugador"]), universo, pos, c,
                   "ts_tramos")
    # diagnóstico 2: partido a partido (MCO; sesgo al alza: quien acierta sigue tirando)
    tsp = _estimar(g, "ts_pct", "usg_tiro", "tsa", "grupo_intra", int(c["min_partidos_jugador"]), universo, pos, c,
                   "ts_partido")
    # TOV% frente a USG% entre temporadas (caja)
    filas = []
    for temp in D.temporadas():
        for liga in D.ligas_temporada(temp):
            lg = D.ligas(liga, temp)
            if lg.empty:
                continue
            lg = lg[lg["fase"] == "regular"][["player_id", "team_id", "min", "usg_pct", "tov_pct"]].copy()
            lg["liga"], lg["temporada"] = liga, temp
            filas.append(lg)
    caja = pd.concat(filas, ignore_index=True)
    for col in ("min", "usg_pct", "tov_pct"):
        caja[col] = pd.to_numeric(caja[col], errors="coerce")
    caja = caja[caja["min"] >= c["min_minutos_temporada_tov"]].dropna(subset=["usg_pct", "tov_pct"])
    caja["persona_id"] = caja.groupby("liga", group_keys=False)["player_id"].apply(lambda s: D.persona(s.name, s))
    for col in ("usg_pct", "tov_pct"):          # nivel de la liga-temporada fuera
        caja[col] = caja[col] - caja.groupby(["liga", "temporada"])[col].transform("mean")
    caja["peso"] = caja["min"]
    tov = _estimar(caja, "tov_pct", "usg_pct", "peso", "persona_id", int(c["min_temporadas_tov"]), universo, pos, c, "tov")
    out = ts_iv
    for e in (tst, tsp, tov):
        out = out.merge(e.drop(columns="pos3"), on="persona_id", how="outer")
    out.attrs["grupo_iv"] = grp_ts
    out["nombre"] = out["persona_id"].map(nombres["nombre"])
    out["liga_principal"] = out["persona_id"].map(nombres["liga"])
    cols = ["persona_id", "nombre", "liga_principal", "pos3"]
    return out[cols + [c_ for c_ in out.columns if c_ not in cols]]


# =============================================================================== 1. producción condicionada al rol

def produccion_por_rol(temp_rec: pd.DataFrame) -> pd.DataFrame:
    t = temp_rec[(temp_rec["fuente"] == "pbp") & ~temp_rec["rol_probabilistico"].astype(bool)].copy()
    t["pts_100"] = 100 * t["pts"] / t["poss_on"].replace(0, np.nan)
    filas = []
    for (liga, rol), d in t.groupby(["liga", "rol"]):
        f = {"liga": liga, "rol": rol, "n": len(d)}
        for col in ("usg_pct", "ts_pct", "pts_100", "ast_pct", "min_pct"):
            v = d[col].dropna()
            f[f"{col}_mediana"] = v.median() if len(v) else np.nan
            f[f"{col}_p25"] = v.quantile(0.25) if len(v) else np.nan
            f[f"{col}_p75"] = v.quantile(0.75) if len(v) else np.nan
        filas.append(f)
    return pd.DataFrame(filas)


def proyectar_a_rol(usg: float, ts: float, p100: float, rol_origen: str, rol_destino: str, tabla_liga: pd.DataFrame,
                    beta_media: float, beta_sd: float, n: int = 2000, semilla: int = 0) -> dict:
    """Proyección de USG%, TS% y puntos/100 al rol de destino con β ~ N(media, sd); devuelve medias e intervalos.
    tabla_liga: filas de produccion_por_rol de la liga de destino (columna `rol`, `usg_pct_mediana`)."""
    m = tabla_liga.set_index("rol")["usg_pct_mediana"]
    d_usg = float(m.get(rol_destino, np.nan) - m.get(rol_origen, np.nan))
    if not np.isfinite(d_usg):
        d_usg = 0.0
    rng = np.random.default_rng(semilla)
    b = rng.normal(beta_media, beta_sd if np.isfinite(beta_sd) else 0.0, n)
    usg2 = max(usg + d_usg, 0.1)
    ts2 = ts + b * (usg2 - usg)
    p2 = p100 * (usg2 / usg) * (ts2 / ts)
    q = lambda v: (float(np.mean(v)), float(np.quantile(v, 0.05)), float(np.quantile(v, 0.95)))  # noqa: E731
    return {"usg": usg2, "d_usg": d_usg, "ts": q(ts2), "p100": q(p2), "p100_lineal": p100 * usg2 / usg}


# =============================================================================== 3. redistribución

def redistribuir(plantilla: pd.DataFrame, salen: list, entran: pd.DataFrame | None = None,
                 total_min: float = 200.0) -> tuple[pd.DataFrame, dict]:
    """Sistema de suma fija. plantilla: player_id, min (por partido), usg (USG%). Las salidas liberan minutos
    y volumen de uso (min·USG/100); las llegadas absorben lo suyo; los que siguen se reescalan para cerrar
    Σ min = total y Σ min·USG = 100·total/5 (USG% medio en pista = 20 %)."""
    p = plantilla.copy()
    p["vol_uso"] = p["min"] * p["usg"] / 100
    sale = p[p["player_id"].isin(salen)]
    sigue = p[~p["player_id"].isin(salen)].copy()
    info = {"min_liberados": float(sale["min"].sum()), "uso_liberado": float(sale["vol_uso"].sum() / p["vol_uso"].sum())
            if p["vol_uso"].sum() else np.nan}
    if entran is not None and len(entran):
        e = entran.copy()
        e["vol_uso"] = e["min"] * e["usg"] / 100
        info["min_absorbidos"] = float(e["min"].sum())
        info["uso_absorbido"] = float(e["vol_uso"].sum() / p["vol_uso"].sum()) if p["vol_uso"].sum() else np.nan
        sigue["origen"] = "sigue"
        e["origen"] = "llega"
        nueva = pd.concat([sigue, e], ignore_index=True)
    else:
        info["min_absorbidos"], info["uso_absorbido"] = 0.0, 0.0
        sigue["origen"] = "sigue"
        nueva = sigue
    resto_min = total_min - nueva.loc[nueva["origen"] == "llega", "min"].sum()
    s = nueva["origen"] == "sigue"
    if nueva.loc[s, "min"].sum() > 0:
        nueva.loc[s, "min"] *= resto_min / nueva.loc[s, "min"].sum()
    objetivo_uso = total_min * 20.0 / 100            # Σ min·USG/100 con USG medio 20 % (5 en pista = 100 %)
    nueva["vol_uso"] = nueva["min"] * nueva["usg"] / 100
    vs = nueva.loc[s, "vol_uso"].sum()
    if vs > 0:
        f = (objetivo_uso - nueva.loc[~s, "vol_uso"].sum()) / vs
        nueva.loc[s, "usg"] *= f
        nueva["vol_uso"] = nueva["min"] * nueva["usg"] / 100
        info["factor_uso_siguen"] = float(f)
    return nueva, info


# =============================================================================== 4. libro de roles

def _club(temp_rec: pd.DataFrame, cfg: dict) -> pd.Series:
    """Clave de club estable entre temporadas: team_id, o el código de club donde el id cambia cada año (FEB)."""
    reglas = cfg["libro"]["club_clave"]
    club = temp_rec["team_id"].astype(str).copy()
    for (liga, temp), idx in temp_rec.groupby(["liga", "temporada"]).groups.items():
        col = reglas.get(liga, reglas["defecto"])
        if col == "team_id":
            continue
        lg = D.ligas(liga, temp)
        if lg.empty or col not in lg:
            continue
        m = lg.dropna(subset=[col]).drop_duplicates("team_id").set_index("team_id")[col].astype(str)
        club.loc[idx] = temp_rec.loc[idx, "team_id"].map(m).fillna(temp_rec.loc[idx, "team_id"])
    return club


def _vectores(temp_rec: pd.DataFrame) -> pd.DataFrame:
    t = temp_rec.copy()
    P = t[[f"p_{k}" for k in ROLES]].to_numpy(float, copy=True)
    sin = np.isnan(P).any(axis=1)
    onehot = np.array([[1.0 if r == k else 0.0 for k in ROLES] for r in t["rol_mas_probable"]])
    P[sin] = onehot[sin]
    t[[f"s_{k}" for k in ROLES]] = P
    t["s_origen"] = np.where(sin, "etiqueta", "probabilidad")
    return t


def _net_equipos() -> pd.DataFrame:
    filas = []
    for temp in D.temporadas():
        for liga in D.ligas_temporada(temp):
            e = D.quintetos_fichero(liga, temp, "equipos.csv")
            if e.empty:
                continue
            e = e[e["fase"] == "regular"][["team_id", "net_rtg_aj", "net_rtg"]]
            e["liga"], e["temporada"] = liga, temp
            filas.append(e)
    return pd.concat(filas, ignore_index=True) if filas else pd.DataFrame()


def libro_roles(temp_rec: pd.DataFrame, cfg: dict, partidos_equipo: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame,
                                                                                          pd.DataFrame]:
    """(libro por club × transición × rol, transiciones de rol, movimientos de los que siguen)."""
    c = cfg["libro"]
    t = _vectores(temp_rec)
    t["club"] = _club(t, cfg)
    t = t.merge(partidos_equipo, on=["liga", "temporada", "team_id"], how="left")
    gmax = t.groupby(["liga", "temporada", "team_id"])["gp"].transform("max")
    t["g_equipo"] = t["g_equipo"].fillna(gmax)
    t["m"] = t["min_total"] / t["g_equipo"]                       # minutos por partido del equipo
    t["vol_uso"] = t["m"] * t["usg_pct"].fillna(0) / 100
    S = [f"s_{k}" for k in ROLES]
    # una fila por persona y club-temporada (BBL cambia de id; traspasados dentro del club no se duplican)
    agg = {"m": "sum", "vol_uso": "sum", "min_total": "sum", "team_id": "first", "rol_mas_probable": "first",
           "rol_probabilistico": "min"}
    for s_ in S:
        t[s_ + "_w"] = t[s_] * t["m"]
        agg[s_ + "_w"] = "sum"
    g = t.groupby(["liga", "club", "temporada", "persona_id"]).agg(agg).reset_index()
    for s_ in S:
        g[s_] = g[s_ + "_w"] / g["m"].replace(0, np.nan)
        g = g.drop(columns=s_ + "_w")
    temps = D.temporadas()
    sig = {a: b for a, b in zip(temps[:-1], temps[1:])}
    net = _net_equipos()
    en_curso = max(temps)
    filas, mov = [], []
    for (liga, club), d in g.groupby(["liga", "club"]):
        for t0 in sorted(d["temporada"].unique()):
            t1 = sig.get(t0)
            if t1 is None or not (d["temporada"] == t1).any():
                continue
            a = d[d["temporada"] == t0].set_index("persona_id")
            b = d[d["temporada"] == t1].set_index("persona_id")
            ret = a.index.intersection(b.index)
            sal = a.index.difference(b.index)
            lle = b.index.difference(a.index)
            Sa, Sb = a[S].fillna(0).to_numpy(), b[S].fillna(0).to_numpy()
            ma, mb = a["m"].to_numpy(), b["m"].to_numpy()
            ia = {p: i for i, p in enumerate(a.index)}
            ib = {p: i for i, p in enumerate(b.index)}
            ra = np.array([ia[p] for p in ret], int)
            rb = np.array([ib[p] for p in ret], int)
            sa_i = np.array([ia[p] for p in sal], int)
            lb_i = np.array([ib[p] for p in lle], int)
            V0 = (ma[:, None] * Sa).sum(0)
            V1 = (mb[:, None] * Sb).sum(0)
            Dk = (ma[sa_i, None] * Sa[sa_i]).sum(0) if len(sa_i) else np.zeros(len(S))
            Ik = (mb[lb_i, None] * Sb[lb_i]).sum(0) if len(lb_i) else np.zeros(len(S))
            DM = ((mb[rb] - ma[ra])[:, None] * Sa[ra]).sum(0) if len(ret) else np.zeros(len(S))
            DR = (mb[rb, None] * (Sb[rb] - Sa[ra])).sum(0) if len(ret) else np.zeros(len(S))
            ida = a["team_id"].iloc[0]
            idb = b["team_id"].iloc[0]
            na = net[(net["liga"] == liga) & (net["temporada"] == t0) & (net["team_id"] == ida)]["net_rtg_aj"]
            nb = net[(net["liga"] == liga) & (net["temporada"] == t1) & (net["team_id"] == idb)]["net_rtg_aj"]
            n0 = float(na.iloc[0]) if len(na) else np.nan
            n1 = float(nb.iloc[0]) if len(nb) else np.nan
            vu_a = a["vol_uso"].sum()
            base = {"liga": liga, "club": club, "temporada_ant": t0, "temporada_nueva": t1, "team_id_ant": ida,
                    "team_id_nuevo": idb, "n_retornos": len(ret), "n_salidas": len(sal), "n_llegadas": len(lle),
                    "min_liberados": float(ma[sa_i].sum()) if len(sa_i) else 0.0,
                    "min_absorbidos": float(mb[lb_i].sum()) if len(lb_i) else 0.0,
                    "uso_liberado": float(a.loc[sal, "vol_uso"].sum() / vu_a) if vu_a else np.nan,
                    "uso_absorbido": float(b.loc[lle, "vol_uso"].sum() / b["vol_uso"].sum()) if b["vol_uso"].sum() else np.nan,
                    "net_ant": n0, "net_nuevo": n1, "delta_net": n1 - n0, "temporada_en_curso": t1 == en_curso}
            for i, k in enumerate(ROLES + ["TOTAL", "CLAVE"]):
                if k == "TOTAL":
                    sel = np.ones(len(ROLES), bool)
                elif k == "CLAVE":
                    sel = np.isin(ROLES, c["roles_clave"])
                else:
                    sel = np.arange(len(ROLES)) == i
                f = {**base, "rol": k, "vol_ant": V0[sel].sum(), "vol_nuevo": V1[sel].sum(), "salidas": Dk[sel].sum(),
                     "llegadas": Ik[sel].sum(), "desplaz_minutos": DM[sel].sum(), "desplaz_rol": DR[sel].sum()}
                f["tasa_relleno"] = (f["llegadas"] + f["desplaz_minutos"] + f["desplaz_rol"]) / f["salidas"] \
                    if f["salidas"] > 1e-9 else np.nan
                f["cierre_identidad"] = f["vol_nuevo"] - f["vol_ant"] - (f["llegadas"] - f["salidas"] + f["desplaz_minutos"]
                                                                       + f["desplaz_rol"])
                comp = {"externa": f["llegadas"], "interna_minutos": f["desplaz_minutos"], "interna_rol": f["desplaz_rol"]}
                f["estrategia"] = max(comp, key=comp.get) if f["salidas"] > 1e-9 else None
                filas.append(f)
            for p in ret:
                va, vb = a.loc[p, S].to_numpy(float), b.loc[p, S].to_numpy(float)
                mov.append({"liga": liga, "club": club, "temporada_ant": t0, "temporada_nueva": t1, "persona_id": p,
                            "min_ant": float(a.loc[p, "min_total"]), "min_nuevo": float(b.loc[p, "min_total"]),
                            "m_ant": float(a.loc[p, "m"]), "m_nuevo": float(b.loc[p, "m"]),
                            "rol_ant": a.loc[p, "rol_mas_probable"], "rol_nuevo": b.loc[p, "rol_mas_probable"],
                            "probabilistico": bool(a.loc[p, "rol_probabilistico"] or b.loc[p, "rol_probabilistico"]),
                            "dist_vector_rol": 0.5 * float(np.abs(vb - va).sum()),
                            "indice_rol_ant": float(va @ np.arange(len(ROLES))),
                            "indice_rol_nuevo": float(vb @ np.arange(len(ROLES))),
                            **{f"ant_{k}": va[j] for j, k in enumerate(S)}, **{f"nuevo_{k}": vb[j] for j, k in enumerate(S)}})
    libro = pd.DataFrame(filas)
    mov = pd.DataFrame(mov)
    tr = transiciones(mov, float(c["minutos_minimos_retorno"]))
    return libro, tr, mov


def transiciones(mov: pd.DataFrame, min_min: float) -> pd.DataFrame:
    if mov.empty:
        return pd.DataFrame()
    m = mov[(mov["min_ant"] >= min_min) & (mov["min_nuevo"] >= min_min) & ~mov["probabilistico"]]
    filas = []
    for liga, d in list(m.groupby("liga")) + [("todas", m)]:
        dura = pd.crosstab(d["rol_ant"], d["rol_nuevo"]).reindex(index=ROLES, columns=ROLES, fill_value=0)
        A = d[[f"ant_s_{k}" for k in ROLES]].to_numpy()
        B = d[[f"nuevo_s_{k}" for k in ROLES]].to_numpy()
        blanda = A.T @ B
        for i, ro in enumerate(ROLES):
            for j, rd in enumerate(ROLES):
                filas.append({"liga": liga, "rol_origen": ro, "rol_destino": rd, "n": int(dura.iloc[i, j]),
                              "prob": dura.iloc[i, j] / dura.iloc[i].sum() if dura.iloc[i].sum() else np.nan,
                              "n_suave": blanda[i, j], "prob_suave": blanda[i, j] / blanda[i].sum() if blanda[i].sum() else np.nan,
                              "n_jugadores_liga": len(d), "dist_vector_media": d["dist_vector_rol"].mean()})
    return pd.DataFrame(filas)


def asociacion_relleno(libro: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Δ Net del equipo por estrategia de relleno del volumen CLAVE y correlación de rangos relleno ↔ Δ Net,
    con intervalos bootstrap (remuestreo de transiciones club-temporada). ASOCIACIÓN DESCRIPTIVA."""
    c = cfg["libro"]
    B, z = int(c["bootstrap"]), float(c["nivel_intervalo"])
    rng = np.random.default_rng(int(cfg["semilla"]))
    d = libro[(libro["rol"] == "CLAVE") & libro["delta_net"].notna() & libro["tasa_relleno"].notna()
              & ~libro["temporada_en_curso"]]
    lo, hi = (1 - z) / 2, 1 - (1 - z) / 2
    filas = []
    for est, de in list(d.groupby("estrategia")) + [("todas", d)]:
        v = de["delta_net"].to_numpy()
        bs = [rng.choice(v, len(v)).mean() for _ in range(B)] if len(v) > 1 else [np.nan]
        filas.append({"medida": "delta_net_medio", "grupo": est, "n": len(v), "valor": float(v.mean()) if len(v) else np.nan,
                      "ic_lo": float(np.nanquantile(bs, lo)), "ic_hi": float(np.nanquantile(bs, hi)),
                      "nota": "asociación descriptiva, no causal"})
    if len(d) > 3:
        x, y = d["tasa_relleno"].to_numpy(), d["delta_net"].to_numpy()
        rho = stats.spearmanr(x, y).statistic
        bs = []
        for _ in range(B):
            i = rng.integers(0, len(x), len(x))
            bs.append(stats.spearmanr(x[i], y[i]).statistic)
        filas.append({"medida": "spearman_relleno_delta_net", "grupo": "todas", "n": len(x), "valor": float(rho),
                      "ic_lo": float(np.nanquantile(bs, lo)), "ic_hi": float(np.nanquantile(bs, hi)),
                      "nota": "asociación descriptiva, no causal"})
    return pd.DataFrame(filas)


# =============================================================================== 5. calidad de compañeros

def calidad_companeros(temp_rec: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for (liga, temp), d in temp_rec[temp_rec["fuente"] == "pbp"].groupby(["liga", "temporada"]):
        par = D.quintetos_fichero(liga, temp, "parejas.csv.gz")
        ctx = D.contexto(temp)
        if par.empty:
            continue
        fase = "total" if (par["fase"] == "total").any() else "regular"
        par = par[par["fase"] == fase][["team_id", "jugador_a_id", "jugador_b_id", "min"]]
        par = pd.concat([par, par.rename(columns={"jugador_a_id": "jugador_b_id", "jugador_b_id": "jugador_a_id"})])
        L = ctx[ctx["liga"] == liga].drop_duplicates(["team_id", "player_id"]).set_index(["team_id", "player_id"])["L"] \
            if len(ctx) else pd.Series(dtype=float)
        par["L_b"] = [L.get((t, p), np.nan) for t, p in zip(par["team_id"], par["jugador_b_id"])]
        par["wL"] = par["min"] * par["L_b"]
        par["min_conL"] = par["min"].where(par["L_b"].notna(), 0)
        g = par.groupby(["team_id", "jugador_a_id"]).agg(min_compartidos=("min", "sum"), min_conL=("min_conL", "sum"),
                                                         wL=("wL", "sum")).reset_index()
        g["L_companeros"] = g["wL"] / g["min_conL"].replace(0, np.nan)
        g["cobertura_L"] = g["min_conL"] / g["min_compartidos"].replace(0, np.nan)
        g = g.rename(columns={"jugador_a_id": "player_id"}).drop(columns=["wL", "min_conL"])
        g["L_propio"] = [L.get((t, p), np.nan) for t, p in zip(g["team_id"], g["player_id"])]
        g["liga"], g["temporada"] = liga, temp
        g["sin_L"] = g["L_companeros"].isna()
        filas.append(g)
    out = pd.concat(filas, ignore_index=True) if filas else pd.DataFrame()
    if len(out):
        out = out.merge(temp_rec[["liga", "temporada", "team_id", "player_id", "persona_id", "ts_pct", "usg_pct",
                                  "min_total", "poss_on", "pts"]], on=["liga", "temporada", "team_id", "player_id"],
                        how="left")
    return out


def efecto_companeros(cc: pd.DataFrame, semilla: int, B: int = 500, nivel: float = 0.9) -> pd.DataFrame:
    """Pendiente dentro de persona (y de liga-temporada) de la producción sobre L_companeros; bootstrap por persona."""
    d = cc.dropna(subset=["L_companeros"]).copy()
    d = d[d["min_total"] >= 300]
    d["pts_100"] = 100 * d["pts"] / d["poss_on"].replace(0, np.nan)
    rng = np.random.default_rng(semilla)
    filas = []
    for y in ("ts_pct", "usg_pct", "pts_100"):
        e = d.dropna(subset=[y]).copy()
        for col in (y, "L_companeros"):
            e[col] = e[col] - e.groupby(["liga", "temporada"])[col].transform("mean")
        n = e.groupby("persona_id").size()
        e = e[e["persona_id"].map(n) >= 2]
        for col in (y, "L_companeros"):
            e[col + "_c"] = e[col] - e.groupby("persona_id")[col].transform("mean")

        def pend(df):
            sxx = (df["L_companeros_c"] ** 2).sum()
            return (df["L_companeros_c"] * df[y + "_c"]).sum() / sxx if sxx else np.nan
        b0 = pend(e)
        personas = e["persona_id"].unique()
        grp = dict(tuple(e.groupby("persona_id")))
        bs = []
        for _ in range(B):
            mu = rng.choice(personas, len(personas))
            bs.append(pend(pd.concat([grp[p] for p in mu])))
        filas.append({"produccion": y, "pendiente_por_unidad_L": b0, "ic_lo": np.nanquantile(bs, (1 - nivel) / 2),
                      "ic_hi": np.nanquantile(bs, 1 - (1 - nivel) / 2), "n_filas": len(e), "n_personas": len(personas),
                      "nota": "asociación dentro de jugador, no causal"})
    return pd.DataFrame(filas)


# =============================================================================== 6. tendencias y asignación de minutos

def tendencias_entrenador(pj: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Por entrenador (todas sus ligas): tamaño de rotación (jugadores con >= X' por partido, en escala 40'),
    concentración (HHI de minutos) y curva de reparto por rango, contraídas hacia su liga con k partidos."""
    c = cfg["asignacion"]["tendencias"]
    R_ = int(c["rangos"])
    j = pj[pj["jugo"]].copy()
    j["min40"] = 40 * j["min_pct"]
    j["cuota"] = j["sec"] / j.groupby(["liga", "game_id", "team_id"])["sec"].transform("sum")
    j["rango"] = j.groupby(["liga", "game_id", "team_id"])["sec"].rank(ascending=False, method="first")
    pg = j.groupby(["liga", "game_id", "team_id"]).agg(entrenador_id=("entrenador_id", "first"),
                                                         rotacion=("min40", lambda s: int((s >= c["min_rotacion_min"]).sum())),
                                                         hhi=("cuota", lambda s: float((s ** 2).sum())))
    curva = j[j["rango"] <= R_].pivot_table(index=["liga", "game_id", "team_id"], columns="rango", values="cuota",
                                            fill_value=0)
    curva.columns = [f"cuota_r{int(k)}" for k in curva.columns]
    pg = pg.join(curva).reset_index()
    cols = ["rotacion", "hhi"] + list(curva.columns)
    liga_m = pg.groupby("liga")[cols].mean()
    liga_sd = pg.groupby("liga")["rotacion"].std()
    pg["entrenador_id"] = pg["entrenador_id"].fillna("__sin_dato__")
    e = pg.groupby("entrenador_id")
    out = e[cols].mean()
    out["rotacion_sd"] = e["rotacion"].std()
    out["n_partidos"] = e.size()
    out["liga_principal"] = e["liga"].agg(lambda s: s.mode().iloc[0])
    k = float(c["k_contraccion_partidos"])
    w = out["n_partidos"] / (out["n_partidos"] + k)
    base = liga_m.reindex(out["liga_principal"]).to_numpy()
    out[[f"{c_}_contraido" for c_ in cols]] = w.to_numpy()[:, None] * out[cols].to_numpy() + (1 - w.to_numpy()[:, None]) * base
    out["rotacion_sd"] = out["rotacion_sd"].fillna(out["liga_principal"].map(liga_sd))
    out = out.reset_index()
    lig = liga_m.reset_index().rename(columns={"liga": "liga_principal"})
    lig["entrenador_id"] = "__liga__:" + lig["liga_principal"]
    lig["n_partidos"] = pg.groupby("liga").size().to_numpy()
    lig["rotacion_sd"] = lig["liga_principal"].map(liga_sd)
    for c_ in cols:
        lig[f"{c_}_contraido"] = lig[c_]
    return pd.concat([out, lig], ignore_index=True)


def asignar_minutos(plantilla: pd.DataFrame, total_min: float = 200.0, minutos_partido: float = 40.0,
                    rotacion_media: float | None = None, rotacion_sd: float = 1.0, curva: np.ndarray | None = None,
                    n_sim: int | None = None, semilla: int | None = None, cfg: dict | None = None,
                    devolver_simulaciones: bool = False, niveles_sim: np.ndarray | None = None,
                    presencia: np.ndarray | None = None):
    """Asignación endógena de minutos por Monte Carlo.

    plantilla: player_id, nivel (p. ej. L), pos3 (E/A/I o NaN) y opcional encaje (0-1).
    Cada simulación: (1) orden de la rotación ~ Plackett-Luce con utilidades u_i = (nivel_i + w·encaje_i)/T
    (muestreo con ruido de Gumbel); (2) restricciones de posición en los 5 primeros (mínimos por pos3);
    (3) tamaño de rotación R ~ N(rotación media del entrenador, sd), recortado a [5, n]; (4) minutos por rango
    según la curva de reparto del entrenador (renormalizada a los R primeros), × total; (5) tope por jugador
    con redistribución proporcional del exceso. Devuelve por jugador minutos medios e intervalo y la
    probabilidad de cada rol (regla de bbfit.roles con titular = está entre los 5 primeros).

    Opcionales (simulador v2, bbfit/simulador.py): `niveles_sim` (n_sim × n) sustituye al nivel en cada simulación
    (incertidumbre del nivel acoplada a los minutos); `presencia` (n, 0-1): en cada simulación el jugador está en la
    plantilla con esa probabilidad (siempre quedan al menos 5)."""
    cfg = cfg or _cfg()
    a = cfg["asignacion"]
    n_sim = int(n_sim or a["simulaciones"])
    rng = np.random.default_rng(cfg["semilla"] if semilla is None else semilla)
    p = plantilla.reset_index(drop=True).copy()
    n = len(p)
    if n < 5:
        raise ValueError("hacen falta al menos 5 jugadores")
    enc = p["encaje"].fillna(0).to_numpy(float) if "encaje" in p else np.zeros(n)
    u = (p["nivel"].fillna(p["nivel"].min() if p["nivel"].notna().any() else 0).to_numpy(float)
         + float(a["encaje_peso"]) * enc) / float(a["temperatura"])
    pos = p["pos3"].to_numpy(object) if "pos3" in p else np.array([None] * n, object)
    rot_m = float(rotacion_media if rotacion_media is not None else a["rotacion_defecto"])
    tope = float(a["max_min_partido"]) * minutos_partido / 40.0 * total_min / (5 * minutos_partido)
    if curva is None:
        curva = np.linspace(1.0, 0.25, n)
    curva = np.asarray(curva, float)
    if len(curva) < n:
        curva = np.r_[curva, np.full(n - len(curva), curva[-1] if len(curva) else 0.1)]
    curva = np.clip(curva[:n], 1e-6, None)
    minimos = a["min_por_pos3"]
    M = np.zeros((n_sim, n))
    T5 = np.zeros((n_sim, n), bool)
    if niveles_sim is not None:
        U = (np.asarray(niveles_sim, float) + float(a["encaje_peso"]) * enc[None, :]) / float(a["temperatura"])
    pres = None if presencia is None else np.clip(np.nan_to_num(np.asarray(presencia, float), nan=1.0), 0, 1)
    for s in range(n_sim):
        us = U[s] if niveles_sim is not None else u
        g_ = rng.gumbel(size=n)
        if pres is not None:
            fuera = rng.random(n) > pres
            if (~fuera).sum() < 5:            # al menos 5 disponibles: vuelven los de más presencia
                fuera[np.argsort(-pres)[:5]] = False
            us = np.where(fuera, -np.inf, us)
        orden = list(np.argsort(-(us + g_)))
        if pres is not None:
            orden = [i for i in orden if np.isfinite(us[i])]
        # restricciones de posición en los 5 primeros
        for grupo, k in minimos.items():
            while sum(pos[i] == grupo for i in orden[:5]) < int(k):
                fuera = [i for i in orden[5:] if pos[i] == grupo]
                if not fuera:
                    break
                cuenta = {g: sum(pos[i] == g for i in orden[:5]) for g in set(pos[orden[:5]])}
                sobran = [i for i in orden[:5][::-1] if pos[i] != grupo and cuenta.get(pos[i], 0) > int(minimos.get(pos[i], 0))]
                if not sobran:
                    break
                sale, entra = sobran[0], fuera[0]
                i_s, i_e = orden.index(sale), orden.index(entra)
                orden[i_s], orden[i_e] = entra, sale
        R = int(np.clip(round(rng.normal(rot_m, rotacion_sd)), 5, len(orden)))
        w = curva[:R] / curva[:R].sum()
        mins = w * total_min
        for _ in range(20):                       # tope con redistribución proporcional
            exceso = np.clip(mins - tope, 0, None)
            if exceso.sum() < 1e-9:
                break
            mins = np.minimum(mins, tope)
            libres = mins < tope - 1e-9
            if not libres.any():
                break
            mins[libres] += exceso.sum() * mins[libres] / mins[libres].sum()
        M[s, np.array(orden[:R])] = mins
        T5[s, np.array(orden[:5])] = True
    gmin = total_min / 5.0
    out = p[["player_id"]].copy()
    out["min_media"] = M.mean(0)
    out["min_p10"] = np.quantile(M, 0.10, axis=0)
    out["min_p90"] = np.quantile(M, 0.90, axis=0)
    out["p_titular_quinteto"] = T5.mean(0)
    rcfg = cargar("roles")
    rol = clasificar((M / gmin).ravel(), T5.ravel().astype(float), np.full(M.size, np.nan), np.zeros(M.size, bool),
                     rcfg).reshape(M.shape)
    for k in ROLES[:-1]:
        out[f"p_{k}"] = (rol == k).mean(0)
    out["p_GO_TO_GUY"] = np.nan          # requiere el GTI (uso, PIE…), no sólo minutos
    if devolver_simulaciones:
        return out, M
    return out


# =============================================================================== orquestación

def _leer_roles() -> tuple[pd.DataFrame, pd.DataFrame]:
    tr = pd.read_csv(DIR_ROLES / "player_role_season.csv.gz", dtype={"team_id": str, "player_id": str}, low_memory=False)
    partes = [pd.read_csv(p, dtype={"team_id": str, "player_id": str, "game_id": str, "opp_id": str}, low_memory=False)
              for p in sorted((DIR_ROLES / "partidos_jugador").glob("*.csv.gz"))]
    return tr, pd.concat(partes, ignore_index=True)


def main() -> dict:
    from .registro import experimento
    cfg = _cfg()
    DIR_REEMP.mkdir(parents=True, exist_ok=True)
    with experimento("reemplazo", "rol_reemplazo_v1", params={k: cfg[k] for k in ("uso_eficiencia", "libro", "asignacion")},
                     semilla=cfg["semilla"]) as run:
        tr, pj = _leer_roles()
        pj["jugo"] = pj["jugo"].astype(str).str.lower().isin(["true", "1"])
        tr["rol_probabilistico"] = tr["rol_probabilistico"].astype(str).str.lower().isin(["true", "1"])
        res: dict = {}
        sp = pd.read_csv(DIR_ROLES / "player_role_spells.csv.gz", dtype={"team_id": str, "player_id": str},
                         low_memory=False)
        ue = uso_eficiencia(pj, tr, cfg, sp)
        ue.to_csv(DIR_REEMP / "uso_eficiencia.csv", index=False, float_format="%.5f")
        giv = ue.attrs.get("grupo_iv", pd.DataFrame())
        giv.to_csv(DIR_REEMP / "uso_eficiencia_grupos.csv", index=False, float_format="%.5f")
        con = ue[~ue["solo_grupo_ts"].astype(bool)]
        res["uso_eficiencia"] = {"personas": len(ue), "con_estimacion_propia_ts": int(len(con)),
                                 "beta_ts_grupo": ue.groupby("pos3")["beta_grupo_ts"].first().round(4).to_dict(),
                                 "tau2_ts_grupo": ue.groupby("pos3")["tau2_grupo_ts"].first().round(5).to_dict(),
                                 "beta_tov_grupo": ue.groupby("pos3")["beta_grupo_tov"].first().round(4).to_dict(),
                                 "w_media_ts": float(con["w_ts"].mean()) if len(con) else None,
                                 "beta_ts_partido_grupo_mco": ue.groupby("pos3")["beta_grupo_ts_partido"].first().round(4).to_dict(),
                                 "beta_ts_tramos_grupo_mco": ue.groupby("pos3")["beta_grupo_ts_tramos"].first().round(4).to_dict(),
                                 "iv_grupos": giv.round(4).to_dict("records")}
        prod = produccion_por_rol(tr)
        prod.to_csv(DIR_REEMP / "produccion_por_rol.csv", index=False, float_format="%.4f")
        pe = pj[pj["jugo"]].groupby(["liga", "temporada", "team_id"])["game_id"].nunique().rename("g_equipo").reset_index()
        libro, trans, mov = libro_roles(tr, cfg, pe)
        libro.to_csv(DIR_REEMP / "libro_roles_equipos.csv", index=False, float_format="%.4f")
        trans.to_csv(DIR_REEMP / "transiciones_rol.csv", index=False, float_format="%.4f")
        mov.to_csv(DIR_REEMP / "retornos_jugadores.csv.gz", index=False, float_format="%.4f")
        aso = asociacion_relleno(libro, cfg)
        aso.to_csv(DIR_REEMP / "asociacion_relleno_net.csv", index=False, float_format="%.4f")
        tot = libro[libro["rol"] == "TOTAL"]
        res["libro"] = {"transiciones_club": int(len(tot)), "cierre_identidad_max": float(libro["cierre_identidad"].abs().max()),
                        "relleno_clave_mediana": float(libro.loc[libro["rol"] == "CLAVE", "tasa_relleno"].median()),
                        "estrategias_clave": libro.loc[libro["rol"] == "CLAVE", "estrategia"].value_counts().to_dict(),
                        "asociacion": aso.to_dict("records")}
        todas = trans[trans["liga"] == "todas"]
        res["transiciones"] = {"persistencia": {r: float(todas[(todas["rol_origen"] == r) & (todas["rol_destino"] == r)]["prob"].iloc[0])
                                                for r in ROLES if len(todas)},
                               "n_retornos": int(todas["n_jugadores_liga"].iloc[0]) if len(todas) else 0}
        cc = calidad_companeros(tr)
        cc.to_csv(DIR_REEMP / "calidad_companeros.csv.gz", index=False, float_format="%.4f")
        ef = efecto_companeros(cc, int(cfg["semilla"]))
        ef.to_csv(DIR_REEMP / "calidad_companeros_efecto.csv", index=False, float_format="%.4f")
        res["calidad_companeros"] = {"filas": len(cc), "con_L_pct": float(cc["L_companeros"].notna().mean()) if len(cc) else 0,
                                     "efecto": ef.to_dict("records")}
        te = tendencias_entrenador(pj, cfg)
        te.to_csv(DIR_REEMP / "tendencias_entrenador.csv", index=False, float_format="%.4f")
        res["tendencias"] = {"entrenadores": int((~te["entrenador_id"].str.startswith("__")).sum())}
        (DIR_REEMP / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        run.metricas({"cierre_identidad_max": res["libro"]["cierre_identidad_max"],
                      "transiciones_club": res["libro"]["transiciones_club"]})
        run.artefacto(DIR_REEMP / "resumen.json")
    return res
