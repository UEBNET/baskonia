"""Taxonomía unificada de estilos jugador ↔ equipo (fase 6).

Un mismo nombre de estilo describe a un equipo y a un jugador. Para eso los dos viven en el MISMO espacio de
12 rasgos (configs/styles.yaml → `rasgos`), cada uno medido con la versión que corresponde a cada unidad:

  rasgo          equipo (totales del equipo, tasas de equipo)        jugador (sus tasas individuales)
  ritmo          posesiones por 40/48 min (team_pace)                ritmo del equipo × (ritmo con él en pista /
                                                                     ritmo del equipo en el jugada a jugada)
  triple         FG3A / FGA                                          FG3A / FGA propios
  esquina        triples de esquina / tiros con coordenadas          ídem, sus tiros (data/modelos/pista)
  aro            tiros a < 1,8 m / tiros con coordenadas             ídem, sus tiros
  tiros_libres   FTA / FGA                                           FTA / FGA propios
  autocreacion   1 − canastas asistidas / canastas (jugada a jugada) ídem, sus canastas
  asistencia     AST / FGM del equipo (AST% de equipo)               AST% (asistencias / canastas de compañeros)
  reb_ofensivo   OREB por 100 posesiones                             OREB por 100 posesiones con él en pista
  perdidas       TOV / (FGA + 0,44·FTA + TOV)                        ídem, propios
  robos/tapones/faltas  por 100 posesiones                           por 100 posesiones con él en pista

Las tasas del equipo son tasas de equipo (sus totales), no medias de jugadores. Cada rasgo se convierte en
puntuación normal por rangos DENTRO de su liga-temporada y de su población (equipos sin ponderar; jugadores
ponderados por minutos y con la tasa contraída hacia la media de la liga, m / (m + k)): z = Φ⁻¹(percentil).
No depende de la normalización de nivel entre ligas (bbmodel A+B): un equipo «muy de triple» lo es frente a
su liga.

Mezcla gaussiana: se ajusta sólo sobre equipos-temporada (la unidad donde «estilo» está definido) y los
jugadores se proyectan con la misma mezcla (probabilidad a posteriori). Ajustar a la vez equipos y jugadores
haría que los ~20 jugadores por equipo dominaran la verosimilitud y los grupos serían posiciones (base,
alero, pívot), no estilos. Con rasgos en z de su población, «+1 en triple» significa lo mismo (un percentil
84 en su liga) para un equipo y para un jugador, y la proyección se lee igual.

Número de grupos: BIC y estabilidad bootstrap (ARI medio) por (covarianza, K); regla en configs/styles.yaml.
Nombres: tras el ajuste, emparejando centroides con firmas (método húngaro). Cada jugador-etapa y equipo-temporada
(y, con relevo de entrenador, cada tramo) recibe estilo principal, secundario, vector de pertenencia y etiqueta
(«Spacing puro», «Pintura · Pistons»).

Salidas: data/modelos/estilos_unificados/{equipos.csv, jugadores.csv.gz, estilos.json, seleccion_k.json,
correspondencia_vade.csv}. Registro: bbfit.registro (MLflow, experimento «estilos_unificados»).
"""
from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from scipy.special import logsumexp
from scipy.stats import norm

from . import config as CF

DIR_SAL = CF.DIR_MOD / "estilos_unificados"
NOMBRE_CFG = "styles"
LIGAS_48 = {"nba", "gleague"}


def cfg() -> dict:
    return CF.cargar(NOMBRE_CFG)


def rasgos(c: dict | None = None) -> list[str]:
    return [r["id"] for r in (c or cfg())["rasgos"]]


def _div(a, b):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(b > 0, a / np.where(b > 0, b, 1.0), np.nan)


# =============================================================================== carga
COLS_JUG = ["liga", "temporada", "fase", "player_id", "nombre", "posicion", "team_id", "equipo", "gp", "min",
            "fga", "fgm", "fg3a", "fta", "ast", "tov", "oreb", "stl", "blk", "pf", "ast_pct", "oreb_p100",
            "stl_p100", "blk_p100", "pf_p100", "poss_on_court", "team_gp", "team_pace", "team_poss", "opp_poss",
            "team_fga", "team_fgm", "team_fg3a", "team_fta", "team_ast", "team_tov", "team_oreb", "team_stl",
            "team_blk", "team_pf"]


def ligas_temporada(temp: str) -> list[str]:
    return sorted(p.stem for p in (CF.DIR_PROC / temp / "ligas").glob("*.csv"))


def filas_jugador(liga: str, temp: str, fase: str = "regular") -> pd.DataFrame:
    p = CF.DIR_PROC / temp / "ligas" / f"{liga}.csv"
    d = pd.read_csv(p, usecols=lambda c: c in COLS_JUG, dtype={"player_id": str, "team_id": str}, low_memory=False)
    d = d[d["fase"] == fase].copy()
    for c in COLS_JUG:
        if c not in d:
            d[c] = np.nan
    d["min"] = pd.to_numeric(d["min"], errors="coerce").fillna(0.0)
    return d[d["min"] > 0].reset_index(drop=True)


_PISTA: dict[str, pd.DataFrame] = {}


def pista(liga: str, temp: str) -> pd.DataFrame:
    """Conteos de pista (zonas y canastas asistidas) por equipo-jugador, temporada regular. De
    data/modelos/pista/<temp>.csv; si la liga no está (FEB, calculada antes de su ingesta), se calcula en
    memoria con la misma función (bbmodel.pista.filas_liga), sin escribir nada."""
    from bbmodel import pista as P
    if temp not in _PISTA:
        f = CF.DIR_MOD / "pista" / f"{temp}.csv"
        _PISTA[temp] = pd.read_csv(f, dtype={"team_id": str, "player_id": str}) if f.exists() else pd.DataFrame()
    d = _PISTA[temp]
    if len(d) and (d["liga"] == liga).any():
        return d[d["liga"] == liga].copy()
    return P.filas_liga(liga, temp, {})


# =============================================================================== rasgos brutos
def rasgos_jugador(f: pd.DataFrame, pi: pd.DataFrame) -> pd.DataFrame:
    """Rasgos brutos por fila jugador-equipo (una liga-temporada). Los traspasados de EuroLeague/EuroCup
    («BAS;TEL») suman su pista de todos sus equipos y quedan en el último (como en bbestilo)."""
    from bbmodel.pista import unir_a_filas
    d = unir_a_filas(f, pi) if len(pi) else f.assign(**{c: np.nan for c in ("fga_pbp", "fgm_pbp", "fgm_asist",
                                                                           "fga_aro", "fga_t3_esquina", "poss_on", "min_on")})
    d["traspaso"] = d["team_id"].astype(str).str.contains(";")
    d["team_id"] = d["team_id"].astype(str).str.split(";").str[-1]
    d["equipo"] = d["equipo"].astype(str).str.split(";").str[-1].str.strip()
    # ritmo: el del equipo corregido por el ritmo con él en pista frente al del equipo (mismo jugada a jugada)
    ppm = _div(d["poss_on"], d["min_on"])
    sin_t = ~d["traspaso"]
    eq = d[sin_t].groupby("team_id")[["poss_on", "min_on"]].sum(min_count=1)
    ppm_eq = d["team_id"].map(pd.Series(_div(eq["poss_on"], eq["min_on"]), index=eq.index)).astype(float).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.where((d["min_on"].fillna(0).to_numpy() >= 20) & np.isfinite(ppm) & np.isfinite(ppm_eq),
                         ppm / ppm_eq, 1.0)
    pace_eq = d[sin_t].groupby("team_id")["team_pace"].first()
    pace = d["team_id"].map(pace_eq).astype(float)
    out = pd.DataFrame(index=d.index)
    out["ritmo"] = pace * ratio
    out["triple"] = _div(d["fg3a"], d["fga"])
    out["esquina"] = _div(d["fga_t3_esquina"], d["fga_pbp"])
    out["aro"] = _div(d["fga_aro"], d["fga_pbp"])
    out["tiros_libres"] = _div(d["fta"], d["fga"])
    out["autocreacion"] = 1 - _div(d["fgm_asist"], d["fgm_pbp"])
    out["asistencia"] = pd.to_numeric(d["ast_pct"], errors="coerce")
    out["reb_ofensivo"] = pd.to_numeric(d["oreb_p100"], errors="coerce")
    out["perdidas"] = 100 * _div(d["tov"], d["fga"] + 0.44 * d["fta"] + d["tov"])
    out["robos"] = pd.to_numeric(d["stl_p100"], errors="coerce")
    out["tapones"] = pd.to_numeric(d["blk_p100"], errors="coerce")
    out["faltas"] = pd.to_numeric(d["pf_p100"], errors="coerce")
    base = d[["liga", "temporada", "team_id", "equipo", "player_id", "nombre", "posicion", "gp", "min", "traspaso"]]
    return pd.concat([base, out], axis=1)


def rasgos_equipo(f: pd.DataFrame, pi: pd.DataFrame) -> pd.DataFrame:
    """Rasgos brutos por equipo-temporada (una liga-temporada) con los totales del equipo."""
    g = f[~f["team_id"].astype(str).str.contains(";")]
    tcols = [c for c in COLS_JUG if c.startswith("team_") or c == "opp_poss"]
    T = g.groupby("team_id").agg({**{c: "first" for c in tcols}, "equipo": lambda s: s.value_counts().index[0]})
    for c in tcols:
        T[c] = pd.to_numeric(T[c], errors="coerce")
    # equipos sin totales en la fuente: suma de sus jugadores
    suma = g.groupby("team_id")[["fga", "fgm", "fg3a", "fta", "ast", "tov", "oreb", "stl", "blk", "pf"]].sum(min_count=1)
    for c in suma.columns:
        T[f"team_{c}"] = T[f"team_{c}"].fillna(suma[c])
    out = pd.DataFrame(index=T.index)
    poss = T["team_poss"]
    out["ritmo"] = T["team_pace"]
    out["triple"] = _div(T["team_fg3a"], T["team_fga"])
    out["tiros_libres"] = _div(T["team_fta"], T["team_fga"])
    out["asistencia"] = 100 * _div(T["team_ast"], T["team_fgm"])
    out["reb_ofensivo"] = 100 * _div(T["team_oreb"], poss)
    out["perdidas"] = 100 * _div(T["team_tov"], T["team_fga"] + 0.44 * T["team_fta"] + T["team_tov"])
    out["robos"] = 100 * _div(T["team_stl"], poss)
    out["tapones"] = 100 * _div(T["team_blk"], poss)
    out["faltas"] = 100 * _div(T["team_pf"], poss)
    if len(pi):
        s = pi.groupby(pi["team_id"].astype(str))[["fga_pbp", "fgm_pbp", "fgm_asist", "fga_aro", "fga_t3_esquina"]].sum(min_count=1)
        s = s.reindex(T.index)
        out["esquina"] = _div(s["fga_t3_esquina"], s["fga_pbp"])
        out["aro"] = _div(s["fga_aro"], s["fga_pbp"])
        out["autocreacion"] = 1 - _div(s["fgm_asist"], s["fgm_pbp"])
    else:
        out["esquina"] = out["aro"] = out["autocreacion"] = np.nan
    out["gp"] = T["team_gp"]
    out["equipo"] = T["equipo"]
    out = out.reset_index()
    out.insert(0, "temporada", f["temporada"].iloc[0])
    out.insert(0, "liga", f["liga"].iloc[0])
    return out


# =============================================================================== normalización
def _ecdf_z(ref: np.ndarray, w: np.ndarray, x: np.ndarray, pmin: float) -> np.ndarray:
    """z = Φ⁻¹(percentil ponderado de x en la distribución de referencia (ref, w)); percentil medio en empates."""
    ok = np.isfinite(ref) & (w > 0)
    out = np.full(len(x), np.nan)
    if ok.sum() < 3:
        return out
    v, ww = ref[ok], w[ok]
    o = np.argsort(v, kind="mergesort")
    v, ww = v[o], ww[o]
    cw = np.concatenate([[0.0], np.cumsum(ww)])
    W = cw[-1]
    fx = np.isfinite(x)
    lo = np.searchsorted(v, x[fx], side="left")
    hi = np.searchsorted(v, x[fx], side="right")
    F = (cw[lo] + 0.5 * (cw[hi] - cw[lo])) / W
    out[fx] = norm.ppf(np.clip(F, pmin, 1 - pmin))
    return out


def contraer(x: np.ndarray, m: np.ndarray, mu: float, k: float) -> np.ndarray:
    """Tasa contraída hacia la media de la liga: (m·x + k·μ) / (m + k)."""
    return (m * x + k * mu) / (m + k)


def puntuar_liga(eq: pd.DataFrame, jg: pd.DataFrame, c: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Añade z_<rasgo> a equipos y jugadores de UNA liga-temporada. Devuelve también la referencia (para
    puntuar después los tramos de entrenador con la misma distribución)."""
    R = rasgos(c)
    pmin = c["normalizacion"]["percentil_min"]
    k = c["datos"]["contraccion_minutos_jugador"]
    mref = c["datos"]["min_minutos_referencia"]
    ref = {"equipo": {}, "jugador": {}, "media_jugador": {}}
    eq, jg = eq.copy(), jg.copy()
    m = jg["min"].to_numpy(float)
    en_ref = m >= mref
    for r in R:
        xe = eq[r].to_numpy(float)
        ref["equipo"][r] = xe
        eq[f"z_{r}"] = _ecdf_z(xe, np.ones(len(xe)), xe, pmin)
        xj = jg[r].to_numpy(float)
        okr = en_ref & np.isfinite(xj)
        mu = float(np.average(xj[okr], weights=m[okr])) if okr.any() else np.nan
        xs = np.where(np.isfinite(xj), contraer(xj, m, mu, k), np.nan)
        jg[f"{r}_c"] = xs
        ref["jugador"][r] = (xs[okr], m[okr])
        ref["media_jugador"][r] = mu
        jg[f"z_{r}"] = _ecdf_z(xs[okr], m[okr], xs, pmin) if okr.sum() >= 3 else np.nan
    return eq, jg, ref


# =============================================================================== mezcla
def _ajustar_gmm(X: np.ndarray, k: int, cov: str, c: dict, semilla: int):
    from sklearn.mixture import GaussianMixture
    m = c["mezcla"]
    return GaussianMixture(k, covariance_type=cov, n_init=m["n_init"], max_iter=m["max_iter"],
                           reg_covar=m["reg_covar"], random_state=semilla).fit(X)


def covarianzas_completas(g) -> np.ndarray:
    if g.covariance_type == "full":
        return g.covariances_
    if g.covariance_type == "diag":
        return np.array([np.diag(v) for v in g.covariances_])
    if g.covariance_type == "tied":
        return np.repeat(g.covariances_[None], g.n_components, 0)
    return np.array([np.eye(g.means_.shape[1]) * v for v in g.covariances_])


def posterior(medias: np.ndarray, covs: np.ndarray, pesos: np.ndarray, X: np.ndarray) -> np.ndarray:
    """Probabilidad a posteriori de cada componente con rasgos ausentes (NaN): verosimilitud marginal en
    los rasgos observados (submatrices de covarianza). Sin NaN coincide con GaussianMixture.predict_proba."""
    X = np.atleast_2d(X)
    n, K = len(X), len(pesos)
    out = np.full((n, K), np.nan)
    obs = np.isfinite(X)
    patrones, inv = np.unique(obs, axis=0, return_inverse=True)
    for ip, pat in enumerate(patrones):
        filas = np.where(inv.ravel() == ip)[0]
        if not pat.any():
            continue
        xo = X[np.ix_(filas, np.where(pat)[0])]
        L = np.empty((len(filas), K))
        for k in range(K):
            S = covs[k][np.ix_(pat, pat)]
            mu = medias[k][pat]
            sign, logdet = np.linalg.slogdet(S)
            D = xo - mu
            sol = np.linalg.solve(S, D.T).T
            L[:, k] = np.log(pesos[k]) - 0.5 * (np.sum(D * sol, 1) + logdet + pat.sum() * np.log(2 * np.pi))
        out[filas] = np.exp(L - logsumexp(L, axis=1, keepdims=True))
    return out


def seleccionar_k(X: np.ndarray, c: dict, log=print) -> tuple[list[dict], dict]:
    """BIC y estabilidad bootstrap (ARI medio de la partición de cada remuestreo, predicha sobre todos los
    datos, frente a la del ajuste completo) para cada (covarianza, K). Devuelve la tabla y la elección."""
    from sklearn.metrics import adjusted_rand_score
    m = c["mezcla"]
    semilla = c["semilla"]
    tabla = []
    for cov in m["covarianzas"]:
        for k in range(m["k_min"], m["k_max"] + 1):
            t0 = time.time()
            g = _ajustar_gmm(X, k, cov, c, semilla)
            ref = g.predict(X)
            rng = np.random.default_rng(semilla + 1000 * k)
            aris = []
            for b in range(m["bootstrap"]):
                idx = rng.integers(0, len(X), len(X))
                gb = _ajustar_gmm(X[idx], k, cov, {**c, "mezcla": {**m, "n_init": 1}}, semilla + b + 1)
                aris.append(adjusted_rand_score(ref, gb.predict(X)))
            cuotas = np.bincount(ref, minlength=k) / len(ref)
            fila = {"covarianza": cov, "k": k, "bic": float(g.bic(X)), "aic": float(g.aic(X)),
                    "log_verosimilitud_media": float(g.score(X)), "estabilidad_ari": float(np.mean(aris)),
                    "estabilidad_ari_sd": float(np.std(aris)), "cuota_min": float(cuotas.min()),
                    "seguridad_media": float(g.predict_proba(X).max(1).mean()), "segundos": round(time.time() - t0, 1)}
            tabla.append(fila)
            log(f"  {cov:4s} K={k:2d} BIC={fila['bic']:.0f} ARI={fila['estabilidad_ari']:.3f} "
                f"cuota_min={fila['cuota_min']:.3f} ({fila['segundos']} s)")
    return tabla, elegir(tabla, c)


def elegir(tabla: list[dict], c: dict) -> dict:
    """Regla de selección (configs/styles.yaml → mezcla). K se busca en [k_taxonomia, k_max]; los K menores
    se calculan sólo como diagnóstico (qué estructura gruesa ve el BIC).

    1. Familia de covarianza: la de menor BIC (su mínimo en todo el rango).
    2. Dentro de ella y en K ≥ k_taxonomia: si el BIC tiene su mínimo en un K > k_taxonomia y ese K es estable
       (ARI bootstrap ≥ estabilidad_min) y sin grupos diminutos (cuota ≥ cuota_min), ese K.
    3. Si el BIC crece con K desde k_taxonomia (ningún grupo adicional tiene apoyo: los estilos son regiones
       de un continuo), el BIC no decide; se toma el MAYOR K estable y sin grupos diminutos: la partición
       más fina del continuo que se reproduce al remuestrear.
    4. Si ninguna opción cumple los umbrales, la más estable."""
    m = c["mezcla"]
    kt = m.get("k_taxonomia", m["k_min"])
    fam = min({f["covarianza"] for f in tabla}, key=lambda cv: min(f["bic"] for f in tabla if f["covarianza"] == cv))
    todo = sorted([f for f in tabla if f["covarianza"] == fam], key=lambda f: f["k"])
    k_bic_global = min(todo, key=lambda f: f["bic"])["k"]
    T = [f for f in todo if f["k"] >= kt] or todo

    def _ok(f):
        return f["estabilidad_ari"] >= m["estabilidad_min"] and f["cuota_min"] >= m["cuota_min"]

    base = {"covarianza": fam, "k_bic_global": k_bic_global, "k_taxonomia": kt}
    mejor_bic = min(T, key=lambda f: f["bic"])
    if mejor_bic["k"] > T[0]["k"] and _ok(mejor_bic):
        return {**base, "k": mejor_bic["k"], "caso": "bic",
                "motivo": f"covarianza {fam} (menor BIC); en K ≥ {kt} el BIC es mínimo en K={mejor_bic['k']} y es estable"}
    estables = [f for f in T if f["k"] > 1 and _ok(f)]
    if estables:
        f = max(estables, key=lambda f: f["k"])
        caso = "continuo" if mejor_bic["k"] == T[0]["k"] else "bic_inestable"
        return {**base, "k": f["k"], "caso": caso,
                "motivo": (f"covarianza {fam} (menor BIC; mínimo global en K={k_bic_global}); en K ≥ {kt} el BIC "
                           f"{'crece con K: continuo, sin grupos separados' if caso == 'continuo' else 'tiene su mínimo en un K inestable'}; "
                           f"mayor K con ARI ≥ {m['estabilidad_min']} y grupo mínimo ≥ {m['cuota_min']:.0%}")}
    f = max([f for f in T if f["k"] > 1] or T, key=lambda f: f["estabilidad_ari"])
    return {**base, "k": f["k"], "caso": "sin_umbral", "motivo": "ninguna opción cumple los umbrales: la más estable"}


# =============================================================================== nombres y etiquetas
def nombrar(medias: np.ndarray, R: list[str], estilos: dict, firma_min: float) -> list[str]:
    """Clave de estilo (de configs/styles.yaml) para cada componente: método húngaro sobre la similitud del
    coseno entre el centroide (z) y la firma (signo esperado de cada rasgo). Sin firma suficiente →
    'estilo_<n>'."""
    K = len(medias)
    claves = list(estilos)
    if not claves:
        return [f"estilo_{k + 1}" for k in range(K)]
    F = np.array([[float(estilos[e].get("firma", {}).get(r, 0.0)) for r in R] for e in claves])
    Mn = medias / np.maximum(np.linalg.norm(medias, axis=1, keepdims=True), 1e-9)
    Fn = F / np.maximum(np.linalg.norm(F, axis=1, keepdims=True), 1e-9)
    S = Mn @ Fn.T                                   # (K, n_estilos)
    fi, co = linear_sum_assignment(-S)
    out = [f"estilo_{k + 1}" for k in range(K)]
    for i, j in zip(fi, co):
        if S[i, j] >= firma_min:
            out[i] = claves[j]
    return out


def etiqueta(n1: str, p1: float, n2: str, p2: float, c: dict) -> str:
    a = c["asignacion"]
    if not np.isfinite(p1):
        return ""
    if p1 >= a["umbral_puro"]:
        return f"{n1} puro"
    if np.isfinite(p2) and p2 >= a["umbral_mezcla"]:
        return f"{n1} · {n2}"
    return n1


def asignar(df: pd.DataFrame, P: np.ndarray, ids: list[str], nombres: dict, c: dict) -> pd.DataFrame:
    df = df.copy()
    ok = np.isfinite(P).all(1)
    o = np.argsort(-np.where(ok[:, None], P, 0), axis=1)
    p1 = np.where(ok, P[np.arange(len(P)), o[:, 0]], np.nan)
    p2 = np.where(ok, P[np.arange(len(P)), o[:, 1]], np.nan)
    e1 = np.where(ok, np.array(ids, object)[o[:, 0]], None)
    e2 = np.where(ok, np.array(ids, object)[o[:, 1]], None)
    df["estilo"], df["p_estilo"], df["estilo2"], df["p_estilo2"] = e1, p1, e2, p2
    df["estilo_nombre"] = [nombres.get(e, "") if e else "" for e in e1]
    df["estilo2_nombre"] = [nombres.get(e, "") if e else "" for e in e2]
    df["etiqueta"] = [etiqueta(a, x, b, y, c) if e else "" for a, x, b, y, e in
                      zip(df["estilo_nombre"], p1, df["estilo2_nombre"], p2, e1)]
    for k, e in enumerate(ids):
        df[f"p_{e}"] = P[:, k]
    return df


# =============================================================================== tramos de entrenador
def _coach_por_partido(liga: str, temp: str, fase: str) -> pd.DataFrame:
    p = CF.DIR_PROC / temp / "entrenadores" / f"{liga}_partidos.csv"
    if not p.exists():
        return pd.DataFrame()
    d = pd.read_csv(p, dtype=str)
    d = d[(d["fase"] == fase) & d["entrenador_id"].notna() & (d["entrenador_id"] != "")]
    return d[["game_id", "equipo_id", "entrenador_id", "entrenador"]].rename(columns={"equipo_id": "team_id"})


_SUM = ["pts", "fga", "fgm", "fg3a", "fta", "oreb", "dreb", "tov", "stl", "blk", "ast", "pf"]


def _tramos_largos(liga: str, temp: str, fase: str, juegos: set) -> pd.DataFrame:
    """Tramos de quinteto en formato largo (una fila por equipo y tramo): propios y del rival."""
    p = CF.DIR_PROC / temp / "quintetos" / liga / "tramos.csv.gz"
    if not p.exists():
        return pd.DataFrame()
    t = pd.read_csv(p, dtype={"game_id": str, "team_a": str, "team_b": str})
    t = t[(t["fase"] == fase) & t["game_id"].isin(juegos)]
    out = []
    for yo, el in (("a", "b"), ("b", "a")):
        x = pd.DataFrame({"game_id": t["game_id"], "team_id": t[f"team_{yo}"], "sec": t["sec"],
                          "quinteto": t[f"quinteto_{yo}"]})
        for s in _SUM:
            x[s] = t[f"{yo}_{s}"].to_numpy()
            x[f"o_{s}"] = t[f"{el}_{s}"].to_numpy()
        out.append(x)
    return pd.concat(out, ignore_index=True)


def _tiros(liga: str, temp: str, fase: str, juegos: set):
    from bbmodel import zonas as Z
    p = CF.DIR_PROC / temp / "quintetos" / liga / "tiros.csv.gz"
    if not p.exists():
        return pd.DataFrame()
    t = pd.read_csv(p, dtype={"game_id": str, "team_id": str, "player_id": str, "asistente_id": str},
                    usecols=["fase", "game_id", "team_id", "player_id", "tipo", "anotado", "asistente_id", "x", "y"])
    t = t[t["fase"] == fase]
    sis, acierto = Z.calibrar(liga, t)
    t = t[t["game_id"].isin(juegos)].copy()
    t["anotado"] = t["anotado"].astype(str).str.lower().isin(["true", "1"])
    t["campo"] = t["tipo"].isin(["T2", "T3"])
    t["asist"] = t["campo"] & t["anotado"] & t["asistente_id"].notna() & (t["asistente_id"] != "")
    t["zona"] = None
    if acierto >= 0.95:
        z = Z.perfil_tiro(t, sis)["zona"]
        t.loc[z.index, "zona"] = z
    return t


def _feats_pbp(s: pd.DataFrame) -> pd.DataFrame:
    """Rasgos medibles en el jugada a jugada a partir de sumas (equipo o jugador en pista + sus tiros)."""
    out = pd.DataFrame(index=s.index)
    poss = 0.5 * ((s["fga"] - s["oreb"] + s["tov"] + 0.44 * s["fta"]) + (s["o_fga"] - s["o_oreb"] + s["o_tov"] + 0.44 * s["o_fta"]))
    out["ppm"] = _div(poss, s["sec"] / 60)
    out["triple"] = _div(s["i_fg3a"], s["i_fga"])
    out["tiros_libres"] = _div(s["i_fta"], s["i_fga"])
    out["esquina"] = _div(s["i_esquina"], s["i_fga_xy"])
    out["aro"] = _div(s["i_aro"], s["i_fga_xy"])
    out["autocreacion"] = 1 - _div(s["i_asistidas"], s["i_fgm"])
    out["asistencia"] = 100 * _div(s["i_ast"], s["ast_base"])
    out["reb_ofensivo"] = 100 * _div(s["oreb"], poss)
    out["perdidas"] = 100 * _div(s["tov"], s["fga"] + 0.44 * s["fta"] + s["tov"])
    out["robos"] = 100 * _div(s["stl"], poss)
    out["tapones"] = 100 * _div(s["blk"], poss)
    out["faltas"] = 100 * _div(s["pf"], poss)
    return out


def _sumas_tiros(t: pd.DataFrame, por: list[str], quien: str = "player_id") -> pd.DataFrame:
    c = t[t["campo"]]
    g = c.groupby(por)
    s = pd.DataFrame({"i_fga": g.size(), "i_fg3a": g["tipo"].apply(lambda x: (x == "T3").sum()),
                      "i_fgm": g["anotado"].sum(), "i_asistidas": g["asist"].sum(),
                      "i_fga_xy": g["zona"].apply(lambda x: x.notna().sum()),
                      "i_aro": g["zona"].apply(lambda x: (x == "aro").sum()),
                      "i_esquina": g["zona"].apply(lambda x: (x == "t3_esquina").sum())})
    tl = t[t["tipo"] == "TL"].groupby(por).size().rename("i_fta")
    return s.join(tl, how="outer").fillna(0)


def tramos_entrenador(liga: str, temp: str, eq_temp: pd.DataFrame, jg_temp: pd.DataFrame, ref: dict, c: dict
                      ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Filas de equipo y de jugador por tramo de entrenador, en clubes con ≥ 2 entrenadores en la fase.

    rasgo_tramo = rasgo_temporada + w · (rasgo_pbp_tramo − rasgo_pbp_temporada), w = n / (n + n0) (equipo,
    n partidos) o m / (m + m0) (jugador, m minutos); el ritmo, de forma multiplicativa. Los rasgos que el
    jugada a jugada no da por jugador (rebote ofensivo, pérdidas, robos, tapones, faltas) se quedan en el
    valor de la temporada para los jugadores. Se puntúan con la distribución de referencia de su
    liga-temporada (la de las filas de temporada)."""
    fase = c["datos"]["fase"]
    ce = c["entrenadores"]
    R = rasgos(c)
    cp = _coach_por_partido(liga, temp, fase)
    if cp.empty:
        return pd.DataFrame(), pd.DataFrame()
    n_coach = cp.groupby("team_id")["entrenador_id"].nunique()
    relevo = set(n_coach[n_coach >= 2].index)
    cp = cp[cp["team_id"].isin(relevo)]
    if cp.empty:
        return pd.DataFrame(), pd.DataFrame()
    juegos = set(cp["game_id"])
    L = _tramos_largos(liga, temp, fase, juegos)
    if L.empty:
        return pd.DataFrame(), pd.DataFrame()
    L = L[L["team_id"].isin(relevo)].merge(cp[["game_id", "team_id", "entrenador_id"]], on=["game_id", "team_id"])
    t = _tiros(liga, temp, fase, juegos)
    if t.empty:
        return pd.DataFrame(), pd.DataFrame()
    t = t.merge(cp[["game_id", "team_id", "entrenador_id"]], on=["game_id", "team_id"])
    pmin = c["normalizacion"]["percentil_min"]
    # ---------------- equipos
    sumL = ["sec"] + _SUM + [f"o_{s}" for s in _SUM]
    filas_e = []
    for nivel_por in (["team_id"], ["team_id", "entrenador_id"]):
        s = L.groupby(nivel_por)[sumL].sum()
        st = _sumas_tiros(t, nivel_por)
        a = t[t["asist"]].groupby(nivel_por).size().rename("i_ast")
        s = s.join(st).join(a).fillna({"i_ast": 0})
        s["ast_base"] = s["i_fgm"]
        f = _feats_pbp(s)
        f["n_partidos"] = L.groupby(nivel_por)["game_id"].nunique()
        filas_e.append(f)
    pbp_t, pbp_c = filas_e
    cob = cp.groupby(["team_id", "entrenador_id"])["game_id"].nunique()
    nombres_c = cp.drop_duplicates(["team_id", "entrenador_id"]).set_index(["team_id", "entrenador_id"])["entrenador"]
    E = eq_temp.set_index("team_id")
    out_e = []
    for (tid, cid), f in pbp_c.iterrows():
        if tid not in E.index:
            continue
        n_tot = int(cob.get((tid, cid), 0))
        n = int(f["n_partidos"])
        if n_tot == 0 or n / n_tot < ce["min_cobertura_pbp"]:
            continue
        w = n / (n + ce["contraccion_partidos_equipo"])
        base = E.loc[tid]
        fila = {"liga": liga, "temporada": temp, "team_id": tid, "equipo": base["equipo"], "nivel": "entrenador",
                "entrenador_id": cid, "entrenador": nombres_c.get((tid, cid), ""), "n_partidos": n_tot,
                "n_partidos_pbp": n, "peso_tramo": w, "gp": base["gp"]}
        for r in R:
            v0 = base[r]
            if r == "ritmo":
                rat = _div(f["ppm"], pbp_t.loc[tid, "ppm"])
                fila[r] = v0 * (1 + w * (rat - 1)) if np.isfinite(rat) else v0
            else:
                d = f[r] - pbp_t.loc[tid, r]
                fila[r] = v0 + w * d if np.isfinite(d) and np.isfinite(v0) else v0
        out_e.append(fila)
    TE = pd.DataFrame(out_e)
    if len(TE):
        for r in R:
            TE[f"z_{r}"] = _ecdf_z(ref["equipo"][r], np.ones(len(ref["equipo"][r])), TE[r].to_numpy(float), pmin)
    # ---------------- jugadores
    Lx = L.assign(player_id=L["quinteto"].astype(str).str.split("|")).explode("player_id")
    TJ = pd.DataFrame()
    filas_j = []
    for nivel_por in (["team_id", "player_id"], ["team_id", "entrenador_id", "player_id"]):
        s = Lx.groupby(nivel_por)[sumL].sum()
        st = _sumas_tiros(t, nivel_por)
        tc = t[t["asist"]].rename(columns={"player_id": "_tirador", "asistente_id": "player_id"})
        a = tc.groupby(nivel_por).size().rename("i_ast")
        s = s.join(st).join(a)
        s[["i_fga", "i_fg3a", "i_fgm", "i_asistidas", "i_fga_xy", "i_aro", "i_esquina", "i_fta", "i_ast"]] = \
            s[["i_fga", "i_fg3a", "i_fgm", "i_asistidas", "i_fga_xy", "i_aro", "i_esquina", "i_fta", "i_ast"]].fillna(0)
        s["ast_base"] = s["fgm"] - s["i_fgm"]
        f = _feats_pbp(s)
        f["min_pbp"] = s["sec"] / 60
        filas_j.append(f)
    pj_t, pj_c = filas_j
    J = jg_temp[~jg_temp["traspaso"]].drop_duplicates(["team_id", "player_id"]).set_index(["team_id", "player_id"])
    medibles = ["triple", "tiros_libres", "esquina", "aro", "autocreacion", "asistencia"]
    out_j = []
    for (tid, cid, pid), f in pj_c.iterrows():
        if (tid, pid) not in J.index or (tid, pid) not in pj_t.index:
            continue
        m = float(f["min_pbp"])
        if m < c["datos"]["min_minutos_asignar"]:
            continue
        w = m / (m + ce["contraccion_minutos_jugador"])
        base = J.loc[(tid, pid)]
        ft = pj_t.loc[(tid, pid)]
        fila = {"liga": liga, "temporada": temp, "team_id": tid, "equipo": base["equipo"], "player_id": pid,
                "nombre": base["nombre"], "posicion": base["posicion"], "nivel": "entrenador", "entrenador_id": cid,
                "entrenador": nombres_c.get((tid, cid), ""), "min": m, "peso_tramo": w, "traspaso": False}
        for r in R:
            v0 = base[f"{r}_c"]
            if r == "ritmo":
                rat = _div(f["ppm"], ft["ppm"])
                fila[f"{r}_c"] = v0 * (1 + w * (rat - 1)) if np.isfinite(rat) else v0
            elif r in medibles:
                d = f[r] - ft[r]
                fila[f"{r}_c"] = v0 + w * d if np.isfinite(d) and np.isfinite(v0) else v0
            else:
                fila[f"{r}_c"] = v0
            fila[r] = base[r]
        out_j.append(fila)
    TJ = pd.DataFrame(out_j)
    if len(TJ):
        for r in R:
            v, w_ = ref["jugador"][r]
            TJ[f"z_{r}"] = _ecdf_z(v, w_, TJ[f"{r}_c"].to_numpy(float), pmin) if len(v) >= 3 else np.nan
    return TE, TJ


# =============================================================================== VaDE
def clave_vade(eq: pd.DataFrame, jg: pd.DataFrame) -> pd.Series:
    """Clave del club en el modelo VaDE (bbestilo: <liga>:<club_id>:<temp>) de cada equipo-temporada.
    En ligas con id estable club_id = team_id; en LBA, LNB, BSL y GBL (id nuevo cada temporada) se enlaza por
    mayoría de jugadores en común con data/modelos/estilos/vade/jugadores.csv."""
    p = CF.DIR_MOD / "estilos" / "vade" / "jugadores.csv"
    pc = CF.DIR_MOD / "estilos" / "vade" / "clubes.csv"
    if not p.exists() or not pc.exists():
        return pd.Series(None, index=eq.index, dtype=object)
    vc = set(pd.read_csv(pc, usecols=["clave"])["clave"])
    directa = eq["liga"] + ":" + eq["team_id"].astype(str) + ":" + eq["temporada"]
    vj = pd.read_csv(p, usecols=["clave", "liga", "temporada", "player_id"], dtype={"player_id": str})
    vj = vj[vj["liga"].isin(["lba", "lnb", "bsl", "gbl"])]
    jj = jg[~jg["traspaso"]][["liga", "temporada", "team_id", "player_id"]]
    m = jj.merge(vj, on=["liga", "temporada", "player_id"])
    voto = (m.groupby(["liga", "temporada", "team_id", "clave"]).size().reset_index(name="n")
            .sort_values("n", ascending=False).drop_duplicates(["liga", "temporada", "team_id"]))
    k = eq[["liga", "temporada", "team_id"]].merge(voto, how="left", on=["liga", "temporada", "team_id"])["clave"]
    out = np.where(eq["liga"].isin(["lba", "lnb", "bsl", "gbl"]).to_numpy(), k.to_numpy(), directa.to_numpy())
    return pd.Series([x if isinstance(x, str) and x in vc else None for x in out], index=eq.index)


def correspondencia_vade(eq: pd.DataFrame, ids: list[str], nombres: dict) -> tuple[pd.DataFrame, dict]:
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score
    pc = CF.DIR_MOD / "estilos" / "vade" / "clubes.csv"
    v = pd.read_csv(pc, usecols=["clave", "estilo"])
    try:
        nv = json.loads((CF.RAIZ / "config" / "estilos.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        nv = {}
    e = eq[(eq["nivel"] == "temporada") & eq["clave_vade"].notna() & eq["estilo"].notna()]
    e = e.merge(v.rename(columns={"clave": "clave_vade", "estilo": "estilo_vade"}), on="clave_vade")
    tab = pd.crosstab(e["estilo_vade"], e["estilo"]).reindex(columns=ids, fill_value=0)
    filas = []
    for ev, fila in tab.iterrows():
        n = int(fila.sum())
        d = {"estilo_vade": ev, "nombre_vade": nv.get(ev, {}).get("nombre", ev), "equipos": n}
        for i in ids:
            d[f"n_{i}"] = int(fila[i])
        for i in ids:
            d[f"pct_{i}"] = round(100 * fila[i] / n, 1) if n else np.nan
        d["principal_nuevo"] = nombres.get(fila.idxmax(), fila.idxmax())
        filas.append(d)
    resumen = {"equipos_emparejados": int(len(e)),
               "ari": float(adjusted_rand_score(e["estilo_vade"], e["estilo"])),
               "nmi": float(normalized_mutual_info_score(e["estilo_vade"], e["estilo"]))}
    return pd.DataFrame(filas), resumen


# =============================================================================== fichas
def fichas(eq: pd.DataFrame, jg: pd.DataFrame, ids: list[str], medias: np.ndarray, c: dict) -> list[dict]:
    R = rasgos(c)
    rn = {r["id"]: r for r in c["rasgos"]}
    est = c.get("estilos") or {}
    ej = c["ejemplos"]
    E = eq[eq["nivel"] == "temporada"]
    J = jg[jg["nivel"] == "temporada"]
    out = []
    for k, i in enumerate(ids):
        meta = est.get(i, {})
        mu = medias[k]
        orden = np.argsort(-np.abs(mu))
        car = [{"rasgo": R[j], "nombre": rn[R[j]]["corto"], "z": round(float(mu[j]), 2)} for j in orden if abs(mu[j]) >= 0.4]
        e_k = E[E["estilo"] == i]
        j_k = J[J["estilo"] == i]
        ejE = (E[E["temporada"].isin(ej["temporadas"])].sort_values(f"p_{i}", ascending=False)
               .drop_duplicates(["liga", "team_id"]).head(ej["n_equipos"]))
        ejJ = (J[J["temporada"].isin(ej["temporadas"]) & (J["min"] >= ej["min_minutos_jugador"])]
               .sort_values(f"p_{i}", ascending=False).drop_duplicates(["player_id"]).head(ej["n_jugadores"]))
        mins = J.loc[J["estilo"].notna(), "min"].sum()
        out.append({
            "id": i, "nombre": meta.get("nombre", i), "color": meta.get("color", "#888888"),
            "definicion": meta.get("definicion", ""), "equipo": meta.get("equipo", ""), "jugador": meta.get("jugador", ""),
            "rol_jugador": meta.get("rol_jugador", ""),
            "centroide": {R[j]: round(float(mu[j]), 3) for j in range(len(R))},
            "metricas_caracterizan": car,
            "equipos": int(len(e_k)), "cuota_equipos": round(len(e_k) / max(1, E["estilo"].notna().sum()), 4),
            "jugadores": int(len(j_k)), "cuota_minutos_jugadores": round(float(j_k["min"].sum() / mins), 4) if mins else None,
            "ligas": {k2: round(v, 3) for k2, v in e_k["liga"].value_counts(normalize=True).head(8).items()},
            "ejemplos_equipos": [{"equipo": r.equipo, "liga": r.liga, "temporada": r.temporada, "p": round(float(r[f"p_{i}"]), 3)}
                                 for _, r in ejE.iterrows()],
            "ejemplos_jugadores": [{"nombre": r.nombre, "equipo": r.equipo, "liga": r.liga, "temporada": r.temporada,
                                    "min": round(float(r["min"])), "p": round(float(r[f"p_{i}"]), 3)} for _, r in ejJ.iterrows()],
        })
    return out


# =============================================================================== proceso completo
def construir_datos(c: dict, log=print) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Rasgos brutos y z de todos los equipos-temporada y jugadores-etapa; refs por liga-temporada."""
    eqs, jgs, refs = [], [], {}
    for temp in c["datos"]["temporadas"]:
        for liga in ligas_temporada(temp):
            f = filas_jugador(liga, temp, c["datos"]["fase"])
            if f.empty:
                continue
            pi = pista(liga, temp)
            je = rasgos_jugador(f, pi)
            ee = rasgos_equipo(f, pi)
            ee, je, ref = puntuar_liga(ee, je, c)
            refs[(liga, temp)] = ref
            eqs.append(ee)
            jgs.append(je)
            log(f"  {temp} {liga}: {len(ee)} equipos, {len(je)} jugadores-equipo")
    eq = pd.concat(eqs, ignore_index=True)
    jg = pd.concat(jgs, ignore_index=True)
    eq["nivel"], jg["nivel"] = "temporada", "temporada"
    return eq, jg, refs


def pid_estilos(jg: pd.DataFrame) -> pd.Series:
    """Id de jugador como en bbestilo (BBL: «n:» + nombre normalizado), para unir con el Atlas."""
    from bbmodel.identidad import clave_nombre
    pid = jg["player_id"].astype(str).copy()
    bbl = jg["liga"] == "bbl"
    cl = jg.loc[bbl, "nombre"].map(clave_nombre)
    pid.loc[bbl] = np.where(cl.notna(), "n:" + cl.fillna(""), pid.loc[bbl])
    return pid


def _tabla_guardada(c: dict, n: int) -> tuple[list[dict], dict] | None:
    """Tabla de selección de K ya calculada con los mismos rasgos, datos y configuración de la mezcla."""
    p = DIR_SAL / "seleccion_k.json"
    if not p.exists():
        return None
    s = json.loads(p.read_text(encoding="utf-8"))
    claves = ("k_min", "k_max", "covarianzas", "n_init", "max_iter", "reg_covar", "bootstrap")   # las que cambian la tabla
    previa = s.get("config_mezcla", {})
    if s.get("rasgos") != rasgos(c) or s.get("n_ajuste") != n or s.get("semilla") != c["semilla"] \
            or any(previa.get(k) != c["mezcla"].get(k) for k in claves):
        return None
    return s["tabla"], elegir(s["tabla"], c)


def ejecutar(c: dict | None = None, log=print, entrenadores: bool = True, reusar_k: bool = False) -> dict:
    from .registro import experimento
    c = c or cfg()
    R = rasgos(c)
    Z = [f"z_{r}" for r in R]
    t0 = time.time()
    log("1/6 rasgos por liga-temporada")
    eq, jg, refs = construir_datos(c, log)
    d = c["datos"]
    ajuste = (eq["temporada"].isin(d["temporadas_ajuste"]) & (eq["gp"].fillna(0) >= d["min_partidos_equipo_ajuste"])
              & eq[Z].notna().all(1)).to_numpy()
    eq["en_ajuste"] = ajuste
    X = eq.loc[ajuste, Z].to_numpy(float)
    log(f"2/6 selección de K sobre {len(X)} equipos-temporada completos")
    previa = _tabla_guardada(c, len(X)) if reusar_k else None
    if previa:
        log("   tabla de K reutilizada (seleccion_k.json con la misma configuración)")
    tabla, elegido = previa or seleccionar_k(X, c, log)
    log(f"   elegido: {elegido}")
    g = _ajustar_gmm(X, elegido["k"], elegido["covarianza"], c, c["semilla"])
    est = c.get("estilos") or {}
    ids = nombrar(g.means_, R, est, c.get("firma_min", 0.3))
    nombres = {i: est.get(i, {}).get("nombre", i) for i in ids}
    covs = covarianzas_completas(g)
    log("3/6 asignación de equipos y jugadores")
    min_obs = d["min_rasgos_observados"]

    def _post(df):
        Xd = df[Z].to_numpy(float)
        P = posterior(g.means_, covs, g.weights_, Xd)
        P[np.isfinite(Xd).sum(1) < min_obs] = np.nan
        return P

    eq = asignar(eq, _post(eq), ids, nombres, c)
    jg = jg[jg["min"] >= d["min_minutos_asignar"]].reset_index(drop=True)
    jg = asignar(jg, _post(jg), ids, nombres, c)
    jg["fiable"] = jg["min"] >= d["min_minutos_fiable"]
    if entrenadores:
        log("4/6 tramos de entrenador")
        TE, TJ = [], []
        for (liga, temp), ref in refs.items():
            e_t = eq[(eq["liga"] == liga) & (eq["temporada"] == temp)]
            j_t = jg[(jg["liga"] == liga) & (jg["temporada"] == temp)]
            try:
                te, tj = tramos_entrenador(liga, temp, e_t, j_t, ref, c)
            except Exception as e:  # noqa: BLE001  (un fallo de una liga no tumba el resto; queda en el log)
                log(f"   {temp} {liga}: sin tramos ({type(e).__name__}: {e})")
                continue
            if len(te):
                TE.append(asignar(te, _post(te), ids, nombres, c))
            if len(tj):
                tj = asignar(tj, _post(tj), ids, nombres, c)
                tj["fiable"] = tj["min"] >= d["min_minutos_fiable"]
                TJ.append(tj)
        if TE:
            eq = pd.concat([eq, *TE], ignore_index=True)
        if TJ:
            jg = pd.concat([jg, *TJ], ignore_index=True)
        log(f"   tramos: {sum(map(len, TE))} de equipo, {sum(map(len, TJ))} de jugador")
    eq["entrenador_id"] = eq.get("entrenador_id")
    jg["entrenador_id"] = jg.get("entrenador_id")
    eq["en_ajuste"] = eq["en_ajuste"].fillna(False).astype(bool)
    jg["pid_estilos"] = pid_estilos(jg)
    log("5/6 correspondencia con VaDE y fichas")
    eq["clave_vade"] = clave_vade(eq, jg)
    corr, corr_res = correspondencia_vade(eq, ids, nombres)
    tarjetas = fichas(eq, jg, ids, g.means_, c)
    log("6/6 escritura")
    DIR_SAL.mkdir(parents=True, exist_ok=True)
    pcols = [f"p_{i}" for i in ids]
    cab_e = ["liga", "temporada", "team_id", "equipo", "nivel", "entrenador_id", "entrenador", "gp", "n_partidos",
             "peso_tramo", "en_ajuste", "estilo", "estilo_nombre", "p_estilo", "estilo2", "estilo2_nombre", "p_estilo2",
             "etiqueta"] + pcols + R + Z + ["clave_vade"]
    for col in cab_e:
        if col not in eq:
            eq[col] = np.nan
    eq = eq.sort_values(["temporada", "liga", "team_id", "nivel", "entrenador_id"], na_position="first")
    eq[cab_e].round(4).to_csv(DIR_SAL / "equipos.csv", index=False)
    cab_j = ["liga", "temporada", "team_id", "equipo", "player_id", "pid_estilos", "nombre", "posicion", "nivel",
             "entrenador_id", "entrenador", "min", "peso_tramo", "fiable", "traspaso", "estilo", "estilo_nombre",
             "p_estilo", "estilo2", "estilo2_nombre", "p_estilo2", "etiqueta"] + pcols + R + Z
    for col in cab_j:
        if col not in jg:
            jg[col] = np.nan
    jg = jg.sort_values(["temporada", "liga", "team_id", "player_id", "nivel", "entrenador_id"], na_position="first")
    jg[cab_j].round(4).to_csv(DIR_SAL / "jugadores.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    corr.to_csv(DIR_SAL / "correspondencia_vade.csv", index=False)
    sel = {"generado": date.today().isoformat(), "unidad_ajuste": "equipo-temporada", "n_ajuste": int(len(X)),
           "rasgos": R, "regla": {k: c["mezcla"][k] for k in ("estabilidad_min", "cuota_min", "bootstrap")},
           "config_mezcla": c["mezcla"], "semilla": c["semilla"], "elegido": elegido, "tabla": tabla}
    (DIR_SAL / "seleccion_k.json").write_text(json.dumps(sel, ensure_ascii=False, indent=1), encoding="utf-8")
    Et = eq[eq["nivel"] == "temporada"]
    Jt = jg[jg["nivel"] == "temporada"]
    resumen = {"k": elegido["k"], "covarianza": elegido["covarianza"],
               "seguridad_media_equipos": float(Et.loc[Et["en_ajuste"], "p_estilo"].mean()),
               "seguridad_media_jugadores": float(Jt.loc[Jt["fiable"].astype(bool), "p_estilo"].mean()),
               "equipos_asignados": int(Et["estilo"].notna().sum()), "jugadores_asignados": int(Jt["estilo"].notna().sum()),
               "tramos_equipo": int((eq["nivel"] == "entrenador").sum()),
               "tramos_jugador": int((jg["nivel"] == "entrenador").sum()),
               "vade": corr_res, "segundos": round(time.time() - t0)}
    doc = {"generado": date.today().isoformat(),
           "descripcion": "Taxonomía unificada jugador ↔ equipo: mezcla gaussiana sobre 12 rasgos en z por rangos dentro "
                          "de cada liga-temporada; los jugadores se proyectan con la mezcla ajustada en equipos.",
           "rasgos": c["rasgos"], "mezcla": {"k": elegido["k"], "covarianza": elegido["covarianza"],
                                             "pesos": [round(float(w), 4) for w in g.weights_],
                                             "medias": [[round(float(x), 4) for x in m] for m in g.means_],
                                             "covarianzas": [[[round(float(x), 5) for x in f] for f in S] for S in covs]},
           "asignacion": c["asignacion"], "resumen": resumen, "estilos": tarjetas}
    (DIR_SAL / "estilos.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    params = {"rasgos": ",".join(R), "k": elegido["k"], "covarianza": elegido["covarianza"],
              "n_ajuste": len(X), **{f"mezcla_{k}": v for k, v in c["mezcla"].items()}}
    # MLflow ≥ 3.x sólo acepta el almacén de ficheros (experimentos/mlruns) con este permiso explícito
    os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
    try:
        with experimento("estilos_unificados", f"gmm_k{elegido['k']}_{elegido['covarianza']}", params=params,
                         semilla=c["semilla"]) as run:
            run.metricas({kk: vv for kk, vv in resumen.items() if isinstance(vv, (int, float))}
                         | {"vade_ari": corr_res["ari"], "vade_nmi": corr_res["nmi"]})
            for nombre in ("seleccion_k.json", "estilos.json", "correspondencia_vade.csv"):
                run.artefacto(DIR_SAL / nombre)
    except Exception as e:  # noqa: BLE001  (las salidas ya están escritas; el registro no debe tumbarlas)
        log(f"aviso: registro MLflow fallido ({type(e).__name__}: {str(e)[:200]})")
    log(f"hecho en {resumen['segundos']} s: {json.dumps(resumen, ensure_ascii=False)}")
    return resumen


# =============================================================================== Atlas
def cargar_salidas() -> tuple[pd.DataFrame, pd.DataFrame, dict] | None:
    pe, pj, ps = DIR_SAL / "equipos.csv", DIR_SAL / "jugadores.csv.gz", DIR_SAL / "estilos.json"
    if not (pe.exists() and pj.exists() and ps.exists()):
        return None
    eq = pd.read_csv(pe, dtype={"team_id": str, "entrenador_id": str})
    jg = pd.read_csv(pj, dtype={"team_id": str, "player_id": str, "pid_estilos": str, "entrenador_id": str},
                     low_memory=False)
    return eq, jg, json.loads(ps.read_text(encoding="utf-8"))


def campos_atlas(clubes: pd.DataFrame, jugadores: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict] | None:
    """Campos nuevos del Atlas (bbestilo/exportar.py), sin tocar los antiguos.

    clubes: columnas liga, temporada, team_id (y opcionalmente `entrenadores`, lista de etapas con
    entrenador_id). jugadores: liga, temporada, team_id, player_id (id de bbestilo). Añade:
      eu        índice del estilo unificado principal (en meta["estilos_unificados"]["estilos"])
      eu2       índice del secundario
      eu_p      probabilidad del principal
      eu_probs  vector de pertenencia (mismo orden que los estilos)
      eu_etiqueta  «Spacing puro», «Pintura · Pistons», …
    Devuelve (clubes, jugadores, meta) o None si no hay salidas."""
    s = cargar_salidas()
    if s is None:
        return None
    eq, jg, doc = s
    ids = [e["id"] for e in doc["estilos"]]
    pos = {i: k for k, i in enumerate(ids)}
    pc = [f"p_{i}" for i in ids]

    def _campos(df, ref, clave):
        r = ref.drop_duplicates(clave).set_index(clave)
        k = pd.MultiIndex.from_frame(df[clave].astype(str))
        rr = r.reindex(k)
        out = pd.DataFrame(index=df.index)
        out["eu"] = pd.Series([pos.get(x) if isinstance(x, str) else None for x in rr["estilo"]], index=df.index, dtype=object)
        out["eu2"] = pd.Series([pos.get(x) if isinstance(x, str) else None for x in rr["estilo2"]], index=df.index,
                               dtype=object)
        out["eu_p"] = rr["p_estilo"].to_numpy(float)
        P = rr[pc].to_numpy(float)
        out["eu_probs"] = [None if not np.isfinite(p).all() else [round(float(x), 3) for x in p] for p in P]
        out["eu_etiqueta"] = [x if isinstance(x, str) else None for x in rr["etiqueta"]]
        return out

    E = eq[eq["nivel"] == "temporada"].copy()
    c2 = clubes.copy()
    ce = _campos(c2, E, ["liga", "temporada", "team_id"])
    for col in ce:
        c2[col] = ce[col]
    if "entrenadores" in c2:
        T = eq[eq["nivel"] == "entrenador"].set_index(["liga", "temporada", "team_id", "entrenador_id"])
        nuevas = []
        for (_, fila) in c2.iterrows():
            etapas = fila["entrenadores"]
            if not isinstance(etapas, list):
                nuevas.append(etapas)
                continue
            lst = []
            for et in etapas:
                et = dict(et)
                k = (fila["liga"], fila["temporada"], str(fila["team_id"]), str(et.get("entrenador_id")))
                src = T.loc[k] if k in T.index else None
                if src is not None and isinstance(src, pd.DataFrame):
                    src = src.iloc[0]
                if src is not None:
                    et["eu"], et["eu_p"] = pos.get(src["estilo"]), round(float(src["p_estilo"]), 3)
                    et["eu_probs"] = [round(float(src[p]), 3) for p in pc]
                    et["eu_etiqueta"] = src["etiqueta"]
                else:   # un solo entrenador en la temporada: el del club
                    et["eu"], et["eu_p"], et["eu_probs"], et["eu_etiqueta"] = (
                        fila["eu"], fila["eu_p"], fila["eu_probs"], fila["eu_etiqueta"])
                lst.append(et)
            nuevas.append(lst)
        c2["entrenadores"] = nuevas
    Jt = jg[jg["nivel"] == "temporada"].copy()
    Jt["player_id"] = Jt["pid_estilos"]
    j2 = jugadores.copy()
    cj = _campos(j2, Jt, ["liga", "temporada", "team_id", "player_id"])
    for col in cj:
        j2[col] = cj[col]
    meta = {"estilos": [{k: e[k] for k in ("id", "nombre", "color", "definicion", "equipo", "jugador", "rol_jugador",
                                            "metricas_caracterizan", "ejemplos_equipos", "ejemplos_jugadores")}
                        for e in doc["estilos"]],
            "rasgos": doc["rasgos"], "asignacion": doc["asignacion"], "resumen": doc["resumen"],
            "nota": "Taxonomía unificada jugador ↔ equipo (data/modelos/estilos_unificados). Campos eu, eu2, eu_p, "
                    "eu_probs, eu_etiqueta en clubes, etapas de entrenador y jugadores; los campos VaDE (e, p, probs) siguen."}
    return c2, j2, meta
