"""Análisis estadísticos complementarios de los estilos (v2, red VaDE salvo que se indique).

    python -m bbestilo analisis      → data/modelos/estilos/analisis.json (+ tablas CSV en analisis/)

  1. barrido_k        ¿Cuántos estilos admiten los datos? BIC e ICL de mezclas gaussianas en los 13 rasgos
                      (sin nivel) y en el mapa 3D, silueta y estabilidad por submuestreo de k-medias, K = 2..14.
  2. neutralizacion   Cuánto explicaba el nivel de cada rasgo y qué queda tras neutralizar.
  3. exito            ¿Hay estilos que ganan más a igual nivel? Net rating del equipo (z dentro de su liga y
                      temporada) frente al estilo, con y sin controlar el índice de nivel (modelos anidados).
  4. encaje           ¿Rinden mejor los jugadores que fichan por un club de estilo parecido al suyo?
                      Cambios de club entre temporadas consecutivas (300+ minutos en ambas): Δ nivel y Δ cuota
                      de minutos frente a la distancia en el mapa, con controles (MCO con errores HC3).
  5. continuidad      Continuidad de plantilla (minutos de t+1 jugados por quien ya estaba en t) frente al
                      desplazamiento del club en el mapa y a conservar el estilo.
  6. ligas            Estilo × liga y estilo × temporada (χ², V de Cramér), centroides de liga y distancias.
  7. baskonia         Estilo, clubes más parecidos y desplazamiento de Baskonia en cada temporada.
"""
from __future__ import annotations

import glob
import json

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
import torch
from scipy.stats import chi2_contingency, spearmanr
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.mixture import GaussianMixture

from . import config as CF
from .datos import Conjunto, club_alias
from .resultados import nombre_estilo

ENT = CF.TEMPORADAS_ENTRENO


@torch.no_grad()
def _pred(red, X):
    x = torch.tensor(np.asarray(X), dtype=torch.float32)
    return red.salida(x).numpy(), red.mapa(x).numpy()


def _f(x, d=4):
    return None if x is None or not np.isfinite(x) else round(float(x), d)


# ----------------------------------------------------------------------------- 1
def barrido_k(cj: Conjunto, red, ks=range(2, 15), semilla: int = 0) -> dict:
    sel = cj.clubes["temporada"].isin(ENT).to_numpy()
    X = cj.Xc[sel]
    _, Z = _pred(red, X)
    rng = np.random.default_rng(semilla)
    out = {"k": list(ks), "bic_rasgos": [], "icl_rasgos": [], "bic_mapa": [], "icl_mapa": [],
           "silueta_kmedias": [], "estabilidad_kmedias": []}

    def bic_icl(D, k, cov):
        g = GaussianMixture(k, covariance_type=cov, n_init=3, reg_covar=1e-4, random_state=semilla).fit(D)
        r = g.predict_proba(D)
        bic = g.bic(D)
        return bic, bic - 2 * float((r * np.log(r + 1e-12)).sum())

    for k in ks:
        b, i = bic_icl(X, k, "diag")
        out["bic_rasgos"].append(b)
        out["icl_rasgos"].append(i)
        b, i = bic_icl(Z, k, "full")
        out["bic_mapa"].append(b)
        out["icl_mapa"].append(i)
        km = KMeans(k, n_init=10, random_state=semilla).fit(X)
        out["silueta_kmedias"].append(float(silhouette_score(X, km.labels_)))
        aris = []
        for _ in range(10):
            m = rng.random(len(X)) < 0.8
            sub = KMeans(k, n_init=5, random_state=int(rng.integers(1e6))).fit(X[m])
            aris.append(adjusted_rand_score(km.labels_, sub.predict(X)))
        out["estabilidad_kmedias"].append(float(np.mean(aris)))
    for c in ("bic_rasgos", "icl_rasgos", "bic_mapa", "icl_mapa"):
        out[f"k_optimo_{c}"] = int(out["k"][int(np.argmin(out[c]))])
    return out


# ----------------------------------------------------------------------------- 2
def neutralizacion(cj: Conjunto) -> dict:
    sel = ~cj.clubes["provisional"].to_numpy()
    L = cj.clubes["nivel"].to_numpy()[sel]
    antes = [float(np.corrcoef(cj.Xc_bruto[sel][:, k], L)[0, 1]) for k in range(len(CF.COLS))]
    despues = [float(np.corrcoef(cj.Xc[sel][:, k], L)[0, 1]) for k in range(len(CF.COLS))]
    niv_liga = cj.clubes[sel].groupby("liga")["nivel"].agg(["mean", "std", "size"]).round(3)
    return {"rasgos": CF.COLS, "r2_club": cj.neutral_club.r2.round(4).tolist() if cj.neutral_club else None,
            "r2_jugador": cj.neutral_jugador.r2.round(4).tolist() if cj.neutral_jugador else None,
            "corr_nivel_antes": antes, "corr_nivel_despues": despues,
            "nivel_por_liga": niv_liga.reset_index().to_dict(orient="records")}


# ----------------------------------------------------------------------------- 3
def _equipos() -> pd.DataFrame:
    """Net rating y % de victorias de cada equipo (temporada regular), z dentro de su liga y temporada."""
    frames = []
    for t in ENT + CF.TEMPORADAS_PROVISIONALES:
        for f in glob.glob(str(CF.RAIZ / "data" / "processed" / t / "ligas" / "*.csv")):
            d = pd.read_csv(f, usecols=["liga", "temporada", "fase", "team_id", "team_netrtg", "team_w", "team_l"],
                            dtype={"team_id": str}, low_memory=False)
            frames.append(d[(d["fase"] == "regular") & ~d["team_id"].astype(str).str.contains(";")])
    e = pd.concat(frames).groupby(["liga", "temporada", "team_id"])[["team_netrtg", "team_w", "team_l"]].median().reset_index()
    e["net_z"] = e.groupby(["liga", "temporada"])["team_netrtg"].transform(lambda x: (x - x.mean()) / x.std(ddof=0))
    e["pct_v"] = e["team_w"] / (e["team_w"] + e["team_l"])
    return e


def exito(cj: Conjunto, red) -> dict:
    sel = cj.clubes["temporada"].isin(ENT).to_numpy()
    P, _ = _pred(red, cj.Xc[sel])
    d = cj.clubes[sel][["liga", "temporada", "team_id", "nivel", "clave"]].copy()
    d["estilo"] = [nombre_estilo(k) for k in P.argmax(1)]
    d = d.merge(_equipos(), on=["liga", "temporada", "team_id"], how="left").dropna(subset=["net_z"])
    m0 = smf.ols("net_z ~ C(estilo)", d).fit()
    m1 = smf.ols("net_z ~ nivel", d).fit()
    m2 = smf.ols("net_z ~ nivel + C(estilo)", d).fit()
    cmp = sm.stats.anova_lm(m1, m2)
    d["resid"] = m1.resid
    por = d.groupby("estilo").agg(n=("net_z", "size"), net_z=("net_z", "mean"), resid=("resid", "mean"),
                                  sd=("resid", "std"), nivel=("nivel", "mean")).reset_index()
    por["ic95"] = 1.96 * por["sd"] / np.sqrt(por["n"])
    return {"clubes": int(len(d)), "r_nivel_net": _f(np.corrcoef(d["nivel"], d["net_z"])[0, 1]),
            "r2_nivel": _f(m1.rsquared), "r2_estilo": _f(m0.rsquared), "r2_nivel_estilo": _f(m2.rsquared),
            "f_estilo_sin_control": _f(m0.fvalue), "p_estilo_sin_control": _f(m0.f_pvalue, 6),
            "f_estilo_dado_nivel": _f(cmp["F"].iloc[1]), "p_estilo_dado_nivel": _f(cmp["Pr(>F)"].iloc[1], 6),
            "eta2_parcial_estilo": _f((m1.ssr - m2.ssr) / m1.ssr),
            "por_estilo": por.round(4).to_dict(orient="records")}


# ----------------------------------------------------------------------------- 4
def encaje(cj: Conjunto, red, min_min: float = 300) -> dict:
    J = cj.jugadores.copy()
    J["i"] = np.arange(len(J))
    J = J[J["temporada"].isin(ENT) & J["persona_id"].notna() & (J["min"] >= min_min)]
    J = J.sort_values("min", ascending=False).drop_duplicates(["persona_id", "temporada"])   # fila principal
    J["anio"] = J["temporada"].str[:4].astype(int)
    tot = cj.clubes.set_index("clave")["min_total"]
    J["cuota"] = J["min"] / J["clave"].map(tot)
    a = J.merge(J.assign(anio=J["anio"] - 1), on=["persona_id", "anio"], suffixes=("", "_s"))
    a = a[a["clave_club"] != a["clave_club_s"]]
    a["dest_t"] = a["clave_club_s"] + ":" + a["temporada"]       # club destino ANTES del fichaje
    pos = dict(zip(cj.clubes["clave"], range(len(cj.clubes))))
    a = a[a["dest_t"].isin(pos)].copy()
    Pj, Zj = _pred(red, cj.Xj[a["i"].to_numpy()])
    ic = a["dest_t"].map(pos).to_numpy()
    Pc, Zc = _pred(red, cj.Xc[ic])
    io = a["clave"].map(pos).to_numpy()
    _, Zo = _pred(red, cj.Xc[io])
    a["distancia"] = np.linalg.norm(Zj - Zc, axis=1)
    a["afinidad"] = Pj[np.arange(len(a)), Pc.argmax(1)]
    a["mismo_estilo"] = (Pj.argmax(1) == Pc.argmax(1)).astype(int)
    a["d_nivel"] = a["nivel_s"] - a["nivel"]
    a["d_cuota"] = a["cuota_s"] - a["cuota"]
    a["edad"] = a["anio"] - pd.to_numeric(a["anio_nac"], errors="coerce")
    a["edad_nd"] = a["edad"].isna().astype(int)
    a["edad"] = a["edad"].fillna(a["edad"].mean())
    a["cambio_liga"] = (a["liga"] != a["liga_s"]).astype(int)
    a["nivel_dest"] = cj.clubes["nivel"].to_numpy()[ic]
    a["dist_clubes"] = np.linalg.norm(Zo - Zc, axis=1)
    ctrl = "nivel + edad + I(edad**2) + edad_nd + cambio_liga + nivel_dest"
    res = {"casos": int(len(a)), "min_minutos": min_min}
    for y in ("d_nivel", "d_cuota"):
        for x in ("distancia", "afinidad"):
            m = smf.ols(f"{y} ~ {x} + {ctrl}", a).fit(cov_type="HC3")
            ci = m.conf_int().loc[x]
            res[f"{y}~{x}"] = {"coef": _f(m.params[x]), "ic95": [_f(ci[0]), _f(ci[1])], "p": _f(m.pvalues[x], 6),
                               "r2": _f(m.rsquared)}
    a["tercil"] = pd.qcut(a["distancia"], 3, labels=["cerca", "media", "lejos"])
    res["por_tercil"] = a.groupby("tercil", observed=True).agg(n=("d_nivel", "size"), distancia=("distancia", "mean"),
                                                              d_nivel=("d_nivel", "mean"), d_cuota=("d_cuota", "mean")).round(4).reset_index().to_dict(orient="records")
    res["spearman_distancia_dnivel"] = _f(spearmanr(a["distancia"], a["d_nivel"]).statistic)
    a[["persona_id", "nombre", "temporada", "clave", "dest_t", "distancia", "afinidad", "d_nivel", "d_cuota",
       "cambio_liga"]].to_csv(CF.DIR_SALIDA / "analisis" / "encaje_casos.csv", index=False, float_format="%.4f")
    return res


# ----------------------------------------------------------------------------- 5
def continuidad(cj: Conjunto, red) -> dict:
    J = cj.jugadores[cj.jugadores["temporada"].isin(ENT)].copy()
    J["persona"] = J["persona_id"].fillna(J["liga"] + ":" + J["player_id"].astype(str))
    sel = cj.clubes["temporada"].isin(ENT).to_numpy()
    P, Z = _pred(red, cj.Xc[sel])
    c = cj.clubes[sel][["clave_club", "temporada"]].copy()
    c["anio"] = c["temporada"].str[:4].astype(int)
    c["e"] = P.argmax(1)
    c[["x", "y", "z"]] = Z
    filas = []
    plant = {k: g.groupby("persona")["min"].sum() for k, g in J.groupby("clave")}
    for r in c.itertuples():
        sig = c[(c["clave_club"] == r.clave_club) & (c["anio"] == r.anio + 1)]
        if sig.empty:
            continue
        s = sig.iloc[0]
        a, b = plant.get(f"{r.clave_club}:{r.temporada}"), plant.get(f"{r.clave_club}:{s.temporada}")
        if a is None or b is None:
            continue
        cont = float(b[b.index.isin(a.index)].sum() / b.sum())
        filas.append({"clave_club": r.clave_club, "temporada": r.temporada, "continuidad": cont,
                      "desplazamiento": float(np.linalg.norm([s.x - r.x, s.y - r.y, s.z - r.z])),
                      "mismo_estilo": int(s.e == r.e)})
    d = pd.DataFrame(filas)
    lg = smf.logit("mismo_estilo ~ continuidad", d).fit(disp=0)
    d["cuartil"] = pd.qcut(d["continuidad"], 4, labels=["Q1", "Q2", "Q3", "Q4"])
    return {"parejas": int(len(d)), "continuidad_media": _f(d["continuidad"].mean()),
            "spearman_continuidad_desplazamiento": _f(spearmanr(d["continuidad"], d["desplazamiento"]).statistic),
            "p_spearman": _f(spearmanr(d["continuidad"], d["desplazamiento"]).pvalue, 8),
            "or_mismo_estilo_por_10pp": _f(float(np.exp(lg.params["continuidad"] * 0.1))),
            "p_logit": _f(lg.pvalues["continuidad"], 8),
            "por_cuartil": d.groupby("cuartil", observed=True).agg(n=("continuidad", "size"), continuidad=("continuidad", "mean"),
                                                                    desplazamiento=("desplazamiento", "mean"),
                                                                    mismo_estilo=("mismo_estilo", "mean")).round(4).reset_index().to_dict(orient="records")}


# ----------------------------------------------------------------------------- 6
def _cramer(t: pd.DataFrame) -> tuple[float, float, float]:
    chi2, p, _, _ = chi2_contingency(t)
    n = t.to_numpy().sum()
    return float(chi2), float(p), float(np.sqrt(chi2 / (n * (min(t.shape) - 1))))


def ligas(cj: Conjunto, red) -> dict:
    sel = cj.clubes["temporada"].isin(ENT).to_numpy()
    P, Z = _pred(red, cj.Xc[sel])
    d = cj.clubes[sel][["liga", "temporada"]].copy()
    d["estilo"] = [nombre_estilo(k) for k in P.argmax(1)]
    d[["x", "y", "z"]] = Z
    tl = pd.crosstab(d["liga"], d["estilo"])
    tt = pd.crosstab(d["temporada"], d["estilo"])
    chi_l, p_l, v_l = _cramer(tl)
    chi_t, p_t, v_t = _cramer(tt)
    cen = d.groupby("liga")[["x", "y", "z"]].mean()
    D = pd.DataFrame(np.linalg.norm(cen.to_numpy()[:, None] - cen.to_numpy()[None], axis=2), index=cen.index, columns=cen.index)
    disp = d.groupby("liga")[["x", "y", "z"]].apply(lambda g: float(np.linalg.norm(g - g.mean(), axis=1).mean()))
    return {"liga_x_estilo": (tl.div(tl.sum(1), axis=0)).round(4).to_dict(orient="index"),
            "liga_x_estilo_n": tl.to_dict(orient="index"),
            "chi2_liga": _f(chi_l), "p_liga": _f(p_l, 10), "v_cramer_liga": _f(v_l),
            "temporada_x_estilo": (tt.div(tt.sum(1), axis=0)).round(4).to_dict(orient="index"),
            "chi2_temporada": _f(chi_t), "p_temporada": _f(p_t, 8), "v_cramer_temporada": _f(v_t),
            "centroides": cen.round(4).to_dict(orient="index"), "distancias": D.round(4).to_dict(orient="index"),
            "dispersion_interna": disp.round(4).to_dict()}


# ----------------------------------------------------------------------------- 7
def baskonia(cj: Conjunto, red, alias: str = "baskonia") -> dict:
    claves = club_alias().get(alias, {}).get("claves", [])
    P, Z = _pred(red, cj.Xc)
    c = cj.clubes.reset_index(drop=True)
    sel = c["temporada"].isin(ENT).to_numpy()
    # desplazamiento de cada club entre temporadas consecutivas (referencia)
    pos = {(r.clave_club, r.temporada): i for i, r in enumerate(c.itertuples())}
    temps = sorted(c["temporada"].unique())
    despl = [float(np.linalg.norm(Z[pos[(k, t2)]] - Z[pos[(k, t1)]])) for (k, t1) in pos for t2 in temps
             if t2 > t1 and int(t2[:4]) == int(t1[:4]) + 1 and (k, t2) in pos and t2 in ENT]
    despl = np.array(despl)
    out = []
    for k in claves:
        prev = None
        for t in temps:
            if (k, t) not in pos:
                continue
            i = pos[(k, t)]
            mismo = (c["temporada"] == t).to_numpy() & (np.arange(len(c)) != i)
            dist = np.linalg.norm(Z - Z[i], axis=1)
            orden = np.argsort(np.where(mismo, dist, np.inf))[:5]
            fila = {"clave": f"{k}:{t}", "liga": c.at[i, "liga"], "temporada": t, "estilo": nombre_estilo(int(P[i].argmax())),
                    "p": _f(P[i].max()), "nivel": _f(c.at[i, "nivel"]), "provisional": bool(c.at[i, "provisional"]),
                    "mas_parecidos": [{"club": c.at[j, "nombre_club"], "liga": c.at[j, "liga"], "d": _f(dist[j])} for j in orden]}
            if prev is not None:
                dd = float(np.linalg.norm(Z[i] - Z[prev]))
                fila["desplazamiento"] = _f(dd)
                fila["pct_desplazamiento"] = _f((despl <= dd).mean() * 100, 1)
            out.append(fila)
            prev = i
    return {"temporadas": out, "desplazamiento_mediano_clubes": _f(float(np.median(despl)))}


def main() -> dict:
    from .encaje import conjunto, red_guardada
    (CF.DIR_SALIDA / "analisis").mkdir(parents=True, exist_ok=True)
    cj = conjunto()
    red = red_guardada("vade")
    out = {}
    for nombre, f in (("neutralizacion", lambda: neutralizacion(cj)), ("barrido_k", lambda: barrido_k(cj, red)),
                      ("exito", lambda: exito(cj, red)), ("encaje", lambda: encaje(cj, red)),
                      ("continuidad", lambda: continuidad(cj, red)), ("ligas", lambda: ligas(cj, red)),
                      ("baskonia", lambda: baskonia(cj, red))):
        print(f"  {nombre}…", flush=True)
        out[nombre] = f()
    out["idec_exito"] = exito(cj, red_guardada("idec"))
    (CF.DIR_SALIDA / "analisis.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return out
