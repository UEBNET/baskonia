"""F0.4 · Prueba de orden de las sinergias (encargo v4.1 §2.2): ¿hay estructura propia de pareja, de trío o de quinteto
más allá de lo aditivo, y es legible unidad a unidad?

Diseño (por liga-temporada ℓt, sólo tramos del contrato v4.0: sin basura, 5 contra 5, ≥ 1 posesión):

1. Los partidos de ℓt se reparten al azar en tres tercios T₀, T₁, T₂ (semilla derivada de ℓt).
2. Rotación k: el modelo aditivo se ajusta con T_k y se calcula el residuo r_s = y_s − ŷ_s de cada tramo de los otros
   dos tercios (a, b). y_s = 100·(pts_A − pts_B)/n_s (pts/100 del local), peso n_s = posesiones.
       (a) RAPM ridge simple: y = c + κ·clutch + π·playoffs + Σ_A β − Σ_B β, β ~ N(0, σ²/λ), λ por validación interna
           (pliegues por partido dentro de T_k).
       (b) β de F1 v4.0: el MISMO modelo con β ~ N(g(x̃), τ²), g = prior del producto F1 por persona-temporada y τ, σ del
           producto. Es el posterior de F1 re-resuelto con sólo T_k (hiperparámetros fijos) para que los tercios de medida
           no informen β.
3. Residuo medio de una unidad u (jugador, pareja, trío o quinteto del mismo equipo) en el tercio t:
       x_u,t = Σ_{s∈t, u en pista} n_s·(±r_s) / Σ n_s     (signo + si u es del local, − si es del visitante)
   «Propio» de orden o: x_u − media de las x de sus sub-unidades de orden inferior en el mismo tercio
   (pareja − media de sus 2 jugadores; trío − media de sus 3 parejas; quinteto − media de sus 10 tríos).
4. El ruido de a y b es independiente, así que la covarianza ponderada entre tercios estima la varianza de la parte
   estable: V = Σ h·(x_a − m_a)(x_b − m_b) / Σ h, con h = 1/(1/n_a + 1/n_b), unidades con ≥ 150 posesiones en cada
   tercio de medida. Se agrupan las tres rotaciones y todas las ℓt del segmento; el rango del 80 % y el IC95 salen de un
   bootstrap de equipos-temporada (B del YAML).
5. Calibraciones sobre el diseño real [añadidas en la v4.1]. (i) Nula: el error de β estimado en T_k es COMÚN a los tercios a y b, así que entra en
   la covarianza aunque no exista sinergia (sobre todo en las unidades «brutas» y, en menor medida, en las «propias»,
   porque las sub-unidades no comparten exactamente los mismos compañeros). Para medirlo se repite la tubería entera con
   y* = ŷ_aditivo(todo ℓt) + ε*, ε* ~ N(0, σ̂²_ℓt / n_s): sin sinergia por construcción. V_nulo es el sesgo del
   estimador; V − V_nulo es la varianza propia corregida. (ii) Plantada: y* = ŷ_aditivo + Σ_A u − Σ_B u + ε*, con un
   efecto propio u ~ N(0, sd²) por unidad del orden o (y sólo de ese orden). La medida «propia» ATENÚA el efecto verdadero
   (la mayor parte lo absorben los efectos de jugador del ajuste aditivo y las sub-unidades): k_o = (V_plantado − V_nulo)/sd²
   es el factor de atenuación del diseño, y V_corregido / k_o estima la varianza verdadera del efecto propio.
6. Fiabilidad de la unidad propia a n posesiones: V / (V + c/n), con c = Σ(x_a − x_b)² / Σ(1/n_a + 1/n_b) (varianza de
   ruido por posesión de la medida propia).
7. Prueba predictiva (segunda prueba del §2.2): sobre el residuo del aditivo, efectos ridge de unidad (pareja, trío o
   quinteto; λ por validación interna) ajustados en un tercio de medida y evaluados en el otro; error cuadrático ponderado
   frente al aditivo solo. IC95 por bootstrap de partidos dentro de cada ℓt.

Salidas: data/modelos/v4_1/orden_sinergias/{filas_obs_<v>.csv.gz, predictiva_<v>.csv.gz, info_<v>.json, resumen.json};
las filas con las réplicas nulas y plantadas, en experimentos/v4_1/orden_sinergias/filas_<v>.csv.gz (no versionado).
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from itertools import combinations

import numpy as np
import pandas as pd
import scipy.linalg as sla
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from . import config as CE

ORDENES = (1, 2, 3, 5)
SUB = {2: 1, 3: 2, 5: 3}
COMB = {o: np.array(list(combinations(range(5), o)), dtype=np.int64) for o in ORDENES}
NOMBRE = {1: "jugador", 2: "pareja", 3: "trio", 5: "quinteto"}


# =============================================================================================== datos de una liga-temporada
@dataclass
class LT:
    liga: str
    temporada: str
    PA: np.ndarray            # n × 5, códigos de jugador ordenados (local)
    PB: np.ndarray            # n × 5 (visitante)
    ta: np.ndarray            # código de equipo local
    tb: np.ndarray
    y: np.ndarray             # pts/100 del local
    w: np.ndarray             # posesiones
    F: np.ndarray             # n × 3: intercepto, clutch, playoffs
    partido: np.ndarray       # código de partido
    tercio: np.ndarray        # 0, 1, 2 (por partido)
    claves: list              # clave persona|temporada de cada código
    equipos: list

    @property
    def nP(self) -> int:
        return len(self.claves)

    @property
    def n(self) -> int:
        return len(self.y)

    def con_y(self, y: np.ndarray) -> "LT":
        return LT(self.liga, self.temporada, self.PA, self.PB, self.ta, self.tb, np.asarray(y, float), self.w, self.F,
                  self.partido, self.tercio, self.claves, self.equipos)


def preparar(tr: pd.DataFrame, semilla: int) -> LT:
    """Codifica los tramos de UNA liga-temporada (formato de bbequipo.rapm.tramos) y sortea los tercios por partido."""
    claves = sorted(set(k for q in tr["A"] for k in q) | set(k for q in tr["B"] for k in q))
    ij = {k: i for i, k in enumerate(claves)}
    PA = np.sort(np.array([[ij[k] for k in q] for q in tr["A"]], dtype=np.int64), axis=1)
    PB = np.sort(np.array([[ij[k] for k in q] for q in tr["B"]], dtype=np.int64), axis=1)
    eq_codes, equipos = pd.factorize(pd.concat([tr["team_a"].astype(str), tr["team_b"].astype(str)]), sort=True)
    n = len(tr)
    ta, tb = eq_codes[:n].astype(np.int64), eq_codes[n:].astype(np.int64)
    pc, partidos = pd.factorize(tr["game_id"].astype(str), sort=True)
    rng = np.random.default_rng(semilla)
    t_partido = rng.permutation(len(partidos)) % 3
    F = np.c_[np.ones(n), tr["clutch"].to_numpy(bool).astype(float), tr["playoffs"].to_numpy(bool).astype(float)]
    if len(claves) ** 5 >= 2 ** 63:
        raise ValueError(f"demasiados jugadores para codificar quintetos: {len(claves)}")
    return LT(liga=str(tr["liga"].iloc[0]), temporada=str(tr["temporada"].iloc[0]), PA=PA, PB=PB, ta=ta, tb=tb,
              y=tr["y"].to_numpy(float), w=tr["poss"].to_numpy(float), F=F, partido=pc.astype(np.int64),
              tercio=t_partido[pc].astype(np.int64), claves=claves, equipos=list(equipos))


def diseno(lt: LT) -> sp.csr_matrix:
    """X = [jugadores (+1 local, −1 visitante) | intercepto, clutch, playoffs]."""
    n, nP = lt.n, lt.nP
    ar = np.repeat(np.arange(n), 5)
    Xp = sp.csr_matrix((np.r_[np.ones(5 * n), -np.ones(5 * n)], (np.r_[ar, ar], np.r_[lt.PA.ravel(), lt.PB.ravel()])),
                       shape=(n, nP))
    return sp.hstack([Xp, sp.csr_matrix(lt.F)]).tocsr()


# =============================================================================================== modelo aditivo
def _gram(X: sp.csr_matrix, y: np.ndarray, w: np.ndarray):
    Xw = X.multiply(w[:, None]).tocsr()
    return (X.T @ Xw).toarray(), np.asarray(X.T @ (w * y)).ravel()


def _resolver(G: np.ndarray, b: np.ndarray, nP: int, lam: float) -> np.ndarray:
    A = G.copy()
    d = np.arange(nP)
    A[d, d] += lam
    f = np.arange(nP, G.shape[0])
    A[f, f] += 1e-6                                               # efectos fijos prácticamente sin penalizar
    try:
        return sla.solve(A, b, assume_a="pos", check_finite=False)
    except np.linalg.LinAlgError:                                 # fijos colineales (p. ej. sin playoffs): mínima norma
        return np.linalg.lstsq(A, b, rcond=None)[0]


def ajustar_aditivo(lt: LT, X: sp.csr_matrix, filas: np.ndarray, version: str, cfg_o: dict, g: np.ndarray | None = None,
                    sigma: float | None = None, semilla: int = 0) -> tuple[np.ndarray, dict]:
    """Coeficientes [β (nP), fijos (3)] ajustados con las filas dadas. (a): λ por validación interna con pliegues por
    partido. (b): λ = σ²/τ² y media a priori g (β = g + δ)."""
    nP = lt.nP
    Xf, wf = X[filas], lt.w[filas]
    if version == "b":
        lam = float(sigma) ** 2 / float(cfg_o["version_b"]["tau"]) ** 2
        gfull = np.r_[g, np.zeros(lt.F.shape[1])]
        yf = lt.y[filas] - Xf @ gfull
        G, b = _gram(Xf, yf, wf)
        return gfull + _resolver(G, b, nP, lam), {"lambda": lam}
    va = cfg_o["version_a"]
    rej, K = [float(v) for v in va["lambda_rejilla"]], int(va["pliegues_validacion"])
    yf = lt.y[filas]
    rng = np.random.default_rng(semilla)
    part = lt.partido[filas]
    up = np.unique(part)
    pl = dict(zip(up, rng.permutation(len(up)) % K))
    fold = np.array([pl[p] for p in part])
    Gs, bs = zip(*[_gram(Xf[fold == f], yf[fold == f], wf[fold == f]) for f in range(K)])
    G, b = sum(Gs), sum(bs)
    sse = np.zeros(len(rej))
    for f in range(K):
        m = fold == f
        for i, lam in enumerate(rej):
            c = _resolver(G - Gs[f], b - bs[f], nP, lam)
            e = yf[m] - Xf[m] @ c
            sse[i] += np.sum(wf[m] * e ** 2)
    lam = rej[int(np.argmin(sse))]
    return _resolver(G, b, nP, lam), {"lambda": lam, "lambda_en_borde": bool(lam in (rej[0], rej[-1]))}


# =============================================================================================== unidades y residuos medios
def claves_unidad(P: np.ndarray, orden: int, nP: int) -> np.ndarray:
    """n × C(5, orden) claves enteras de las unidades de cada quinteto (P con columnas ordenadas → tuplas ordenadas)."""
    cmb = COMB[orden]
    k = np.zeros((len(P), len(cmb)), dtype=np.int64)
    for c in range(cmb.shape[1]):
        k = k * nP + P[:, cmb[:, c]]
    return k


def descomponer(clave: np.ndarray, orden: int, nP: int) -> np.ndarray:
    """Inverso de claves_unidad: m × orden códigos de jugador."""
    out = np.zeros((len(clave), orden), dtype=np.int64)
    k = clave.copy()
    for c in range(orden - 1, -1, -1):
        out[:, c] = k % nP
        k //= nP
    return out


def agregar(lt: LT, filas: np.ndarray, r: np.ndarray, orden: int) -> pd.DataFrame:
    """Residuo medio ponderado (x) y posesiones (n) de cada unidad (equipo, clave) en las filas dadas; r ya es de esas filas."""
    m = len(COMB[orden])
    kA, kB = claves_unidad(lt.PA[filas], orden, lt.nP), claves_unidad(lt.PB[filas], orden, lt.nP)
    w = lt.w[filas]
    rw = r * w
    df = pd.DataFrame({"team": np.r_[np.repeat(lt.ta[filas], m), np.repeat(lt.tb[filas], m)],
                       "key": np.r_[kA.ravel(), kB.ravel()],
                       "n": np.r_[np.repeat(w, m), np.repeat(w, m)],
                       "s": np.r_[np.repeat(rw, m), -np.repeat(rw, m)]})
    g = df.groupby(["team", "key"], sort=False)[["n", "s"]].sum()
    g["x"] = g["s"] / g["n"]
    return g[["x", "n"]]


def propio(ag: pd.DataFrame, ag_sub: pd.DataFrame | None, orden: int, nP: int) -> pd.Series:
    """x propio = x de la unidad − media de x de sus sub-unidades de orden SUB[orden] (mismo tercio)."""
    if orden == 1:
        return ag["x"]
    team = ag.index.get_level_values(0).to_numpy()
    comp = descomponer(ag.index.get_level_values(1).to_numpy(), orden, nP)
    so = SUB[orden]
    acc = np.zeros(len(ag))
    sub_comb = list(combinations(range(orden), so))
    for sc in sub_comb:
        k = np.zeros(len(ag), dtype=np.int64)
        for c in sc:
            k = k * nP + comp[:, c]
        v = ag_sub["x"].reindex(pd.MultiIndex.from_arrays([team, k])).to_numpy()
        if np.isnan(v).any():
            raise RuntimeError("sub-unidad sin residuo en el mismo tercio (no debería ocurrir)")
        acc += v
    return pd.Series(ag["x"].to_numpy() - acc / len(sub_comb), index=ag.index)


def filas_rotacion(lt: LT, r: np.ndarray, k: int, min_pos: float, ordenes=ORDENES) -> pd.DataFrame:
    """Unidades con ≥ min_pos posesiones en los dos tercios de medida de la rotación k (x bruto y propio en cada uno)."""
    a, b = [t for t in range(3) if t != k]
    res = {}
    for t in (a, b):
        m = lt.tercio == t
        ags = {}
        for o in sorted(set(ordenes) | {SUB[o] for o in ordenes if o in SUB}):
            ags[o] = agregar(lt, m, r[m], o)
        res[t] = {o: (ags[o], propio(ags[o], ags.get(SUB.get(o)), o, lt.nP)) for o in ordenes}
    out = []
    for o in ordenes:
        (ga, pa_), (gb, pb_) = res[a][o], res[b][o]
        j = ga.join(gb, how="inner", lsuffix="_a", rsuffix="_b")
        j = j[(j["n_a"] >= min_pos) & (j["n_b"] >= min_pos)]
        if j.empty:
            continue
        out.append(pd.DataFrame({"orden": o, "rot": k, "team": j.index.get_level_values(0).to_numpy(),
                                 "key": j.index.get_level_values(1).to_numpy(),
                                 "xa": j["x_a"].to_numpy(), "xb": j["x_b"].to_numpy(),
                                 "pa": pa_.reindex(j.index).to_numpy(), "pb": pb_.reindex(j.index).to_numpy(),
                                 "na": j["n_a"].to_numpy(), "nb": j["n_b"].to_numpy()}))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


# =============================================================================================== prueba predictiva
def _diseno_unidades(lt: LT, filas: np.ndarray, orden: int):
    m = len(COMB[orden])
    kA, kB = claves_unidad(lt.PA[filas], orden, lt.nP), claves_unidad(lt.PB[filas], orden, lt.nP)
    n = int(filas.sum())
    rows = np.r_[np.repeat(np.arange(n), m), np.repeat(np.arange(n), m)]
    team = np.r_[np.repeat(lt.ta[filas], m), np.repeat(lt.tb[filas], m)]
    key = np.r_[kA.ravel(), kB.ravel()]
    sgn = np.r_[np.ones(n * m), -np.ones(n * m)]
    return rows, team, key, sgn, n


def _ridge_sparse(X: sp.csr_matrix, r: np.ndarray, w: np.ndarray, lam: float, x0=None) -> np.ndarray:
    G = (X.T @ X.multiply(w[:, None])).tocsr()
    b = np.asarray(X.T @ (w * r)).ravel()
    A = G + lam * sp.identity(G.shape[0], format="csr")
    Mp = sp.diags(1.0 / A.diagonal())
    u, _ = spla.cg(A, b, x0=x0, rtol=1e-8, maxiter=5000, M=Mp)
    return u


def _cv_ridge(X: sp.csr_matrix, r: np.ndarray, w: np.ndarray, fold: np.ndarray, rej: list[float]) -> float:
    """λ por validación cruzada (pliegues dados) con arranque en caliente de más a menos penalización."""
    sse = np.zeros(len(rej))
    for f in np.unique(fold):
        tr_, te = fold != f, fold == f
        u = None
        for lam in sorted(rej, reverse=True):
            u = _ridge_sparse(X[tr_], r[tr_], w[tr_], lam, x0=u)
            e = r[te] - X[te] @ u
            sse[rej.index(lam)] += np.sum(w[te] * e ** 2)
    return rej[int(np.argmin(sse))]


def predictiva(lt: LT, r: np.ndarray, k: int, orden: int, cfg_p: dict, semilla: int, rej_jug: list[float]) -> pd.DataFrame:
    """Efectos de unidad sobre el residuo del aditivo (rotación k): ajuste en un tercio de medida, error en el otro (y al
    revés). El residuo de los dos tercios de medida comparte el error de β estimado en T_k; para que los efectos de unidad
    no ganen por corregir ese error, PRIMERO se reajustan los jugadores en el tercio de ajuste (ridge, λ por validación) y
    se aplica esa corrección a los dos tercios; DESPUÉS se ajustan las unidades sobre lo que queda. Devuelve, por partido
    del tercio de evaluación, el error ponderado del aditivo de T_k (sse_k), del aditivo con jugadores reajustados (sse0)
    y con los efectos de unidad encima (sse1)."""
    a, b = [t for t in range(3) if t != k]
    rej, K = [float(v) for v in cfg_p["lambda_rejilla"]], int(cfg_p["pliegues_validacion"])
    out = []
    Xp_f = diseno(lt)[:, :lt.nP]
    for fit, ev in ((a, b), (b, a)):
        mf, me = lt.tercio == fit, lt.tercio == ev
        rf, wf = r[mf], lt.w[mf]
        re, we = r[me], lt.w[me]
        rng = np.random.default_rng(semilla + 7919 * fit)
        part = lt.partido[mf]
        up = np.unique(part)
        pl = dict(zip(up, rng.permutation(len(up)) % K))
        fold = np.array([pl[p] for p in part])
        # 1) jugadores reajustados en el tercio de ajuste (control del error de β común)
        Xf_p, Xe_p = Xp_f[mf], Xp_f[me]
        lam_p = _cv_ridge(Xf_p, rf, wf, fold, rej_jug)
        dp = _ridge_sparse(Xf_p, rf, wf, lam_p)
        rf2, re2 = rf - Xf_p @ dp, re - Xe_p @ dp
        # 2) unidades sobre lo que queda
        rows, team, key, sgn, n = _diseno_unidades(lt, mf, orden)
        cod = pd.DataFrame({"t": team, "k": key}).groupby(["t", "k"], sort=False).ngroup().to_numpy()
        nU = int(cod.max()) + 1
        X = sp.csr_matrix((sgn, (rows, cod)), shape=(n, nU))
        lam = _cv_ridge(X, rf2, wf, fold, rej)
        u = _ridge_sparse(X, rf2, wf, lam)
        mapa = pd.DataFrame({"t": team, "k": key, "c": cod}).drop_duplicates(["t", "k"]).set_index(["t", "k"])["c"]
        rows_e, team_e, key_e, sgn_e, n_e = _diseno_unidades(lt, me, orden)
        c_e = mapa.reindex(pd.MultiIndex.from_arrays([team_e, key_e])).to_numpy()
        vis = ~np.isnan(c_e)
        pred = np.zeros(n_e)
        np.add.at(pred, rows_e[vis], sgn_e[vis] * u[c_e[vis].astype(np.int64)])
        d = pd.DataFrame({"partido": lt.partido[me], "sse_k": we * re ** 2, "sse0": we * re2 ** 2,
                          "sse1": we * (re2 - pred) ** 2, "w": we})
        g = d.groupby("partido", sort=False)[["sse_k", "sse0", "sse1", "w"]].sum().reset_index()
        g["orden"], g["rot"], g["ajuste"], g["lambda"], g["lambda_jug"] = orden, k, fit, lam, lam_p
        g["lambda_en_borde"] = lam in (rej[0], rej[-1])
        g["frac_unidades_vistas"] = float(vis.mean())
        out.append(g)
    return pd.concat(out, ignore_index=True)


def efecto_plantado(lt: LT, orden: int, sd: float, rng) -> np.ndarray:
    """Σ_A u − Σ_B u por tramo, con u ~ N(0, sd²) independiente por unidad (equipo, clave) del orden dado."""
    m = len(COMB[orden])
    kA, kB = claves_unidad(lt.PA, orden, lt.nP), claves_unidad(lt.PB, orden, lt.nP)
    team = np.r_[np.repeat(lt.ta, m), np.repeat(lt.tb, m)]
    key = np.r_[kA.ravel(), kB.ravel()]
    cod = pd.DataFrame({"t": team, "k": key}).groupby(["t", "k"], sort=False).ngroup().to_numpy()
    u = rng.normal(0.0, sd, int(cod.max()) + 1)[cod]
    n = lt.n
    return u[: n * m].reshape(n, m).sum(1) - u[n * m:].reshape(n, m).sum(1)


# =============================================================================================== una liga-temporada completa
def procesar_lt(lt: LT, version: str, cfg: dict, g: np.ndarray | None = None, sigma: float | None = None,
                con_nulo: bool = True, con_predictiva: bool = True) -> dict:
    """Filas de unidades (observado y réplicas nulas) y errores de la prueba predictiva de una liga-temporada."""
    co = cfg["orden_sinergias"]
    min_pos = float(co["min_posesiones_tercio"])
    ordenes = tuple(int(o) for o in co["ordenes"])
    sem = CE.semilla(cfg, f"{lt.liga}|{lt.temporada}|{version}")
    X = diseno(lt)
    info = {"liga": lt.liga, "temporada": lt.temporada, "tramos": lt.n, "jugadores": lt.nP,
            "partidos": int(lt.partido.max()) + 1, "lambdas": []}
    filas, pred = [], []

    def tuberia(lt_, etiqueta, predict):
        for k in range(3):
            coef, inf = ajustar_aditivo(lt_, X, lt_.tercio == k, version, co, g=g, sigma=sigma, semilla=sem + k)
            if etiqueta == "obs":
                info["lambdas"].append(inf.get("lambda"))
            r = lt_.y - X @ coef
            fr = filas_rotacion(lt_, r, k, min_pos, ordenes)
            if len(fr):
                fr["tipo"] = etiqueta
                filas.append(fr)
            if predict:
                for o in co["prueba_predictiva"]["ordenes"]:
                    p = predictiva(lt_, r, k, int(o), co["prueba_predictiva"], sem + 101 * k + int(o),
                                   [float(v) for v in co["version_a"]["lambda_rejilla"]])
                    p["tipo"] = etiqueta
                    pred.append(p)

    tuberia(lt, "obs", con_predictiva)
    cn, cp = co["calibracion_nula"], co.get("calibracion_plantada", {})
    if con_nulo and (int(cn["replicas"]) > 0 or int(cp.get("replicas", 0)) > 0):
        todas = np.ones(lt.n, bool)
        coef, _ = ajustar_aditivo(lt, X, todas, version, co, g=g, sigma=sigma, semilla=sem + 99)
        yhat = X @ coef
        s2 = float(np.sum(lt.w * (lt.y - yhat) ** 2) / lt.n)          # σ̂² por posesión (Var ε_s = σ²/n_s)
        info["sigma_hat"] = float(np.sqrt(s2))
        rng = np.random.default_rng(sem + 12345)
        for rep in range(int(cn["replicas"])):
            ys = yhat + rng.standard_normal(lt.n) * np.sqrt(s2 / lt.w)
            tuberia(lt.con_y(ys), f"nulo{rep}", False)
        # calibración plantada: efecto propio conocido de orden o (DT sd) sobre el mismo diseño → factor de atenuación
        for o in cp.get("ordenes", []):
            for rep in range(int(cp.get("replicas", 0))):
                ys = yhat + rng.standard_normal(lt.n) * np.sqrt(s2 / lt.w) + efecto_plantado(lt, int(o), float(cp["sd"]), rng)
                tuberia(lt.con_y(ys), f"plantado{int(o)}_{rep}", False)
    f = pd.concat(filas, ignore_index=True) if filas else pd.DataFrame()
    p = pd.concat(pred, ignore_index=True) if pred else pd.DataFrame()
    for d in (f, p):
        if len(d):
            d["liga"], d["temporada"] = lt.liga, lt.temporada
    if len(f):
        f["team"] = [lt.equipos[i] for i in f["team"]]
    return {"filas": f, "predictiva": p, "info": info}


# =============================================================================================== estimación agregada
def _sumas(d: pd.DataFrame, col_a: str, col_b: str, clusters: pd.Index) -> np.ndarray:
    h = 1.0 / (1.0 / d["na"] + 1.0 / d["nb"])
    xa, xb = d[col_a], d[col_b]
    s = pd.DataFrame({"c": d["cluster"], "h": h, "hx": h * xa, "hy": h * xb, "hxy": h * xa * xb,
                      "d2": (xa - xb) ** 2, "inv": 1.0 / d["na"] + 1.0 / d["nb"]})
    return s.groupby("c")[["h", "hx", "hy", "hxy", "d2", "inv"]].sum().reindex(clusters).fillna(0.0).to_numpy()


def _V(S: np.ndarray) -> np.ndarray:
    """S (…, 6): varianza estable ponderada (covarianza centrada entre tercios)."""
    h, hx, hy, hxy = S[..., 0], S[..., 1], S[..., 2], S[..., 3]
    with np.errstate(invalid="ignore", divide="ignore"):
        return hxy / h - (hx / h) * (hy / h)


def _c(S: np.ndarray) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        return S[..., 4] / S[..., 5]


def estimar(filas: pd.DataFrame, B: int, semilla: int, posesiones_fiab=(150, 500, 1000), sd_plantado: float | None = None) -> dict:
    """V observado, V nulo (media de réplicas) y V corregido por orden y medida (bruto/propio), con rango del 80 % e IC95
    por bootstrap de equipos-temporada (los mismos remuestreos para observado y nulo)."""
    d = filas.copy()
    d["cluster"] = d["liga"] + "|" + d["temporada"] + "|" + d["team"].astype(str)
    clusters = pd.Index(sorted(d["cluster"].unique()))
    rng = np.random.default_rng(semilla)
    Wb = rng.multinomial(len(clusters), np.full(len(clusters), 1.0 / len(clusters)), size=B).astype(float)
    reps = sorted(t for t in d["tipo"].unique() if t.startswith("nulo"))
    out = {}
    for o in sorted(d["orden"].unique()):
        do = d[d["orden"] == o]
        for medida, (ca, cb) in (("bruto", ("xa", "xb")), ("propio", ("pa", "pb"))):
            if o == 1 and medida == "propio":
                continue
            obs = do[do["tipo"] == "obs"]
            if obs.empty:
                continue
            S = _sumas(obs, ca, cb, clusters)
            v, c = float(_V(S.sum(0))), float(_c(S.sum(0)))
            vb = _V(Wb @ S)
            Sn = [_sumas(do[do["tipo"] == t], ca, cb, clusters) for t in reps]
            res = {"n_filas": int(len(obs)), "n_unidades": int(obs.drop_duplicates(["liga", "temporada", "team", "key"]).shape[0]),
                   "equipos_temporada": int(obs["cluster"].nunique()),
                   "V": v, "V_r80": _q(vb, (0.10, 0.90)), "V_ic95": _q(vb, (0.025, 0.975)),
                   "DT": float(np.sqrt(max(v, 0.0))), "c_ruido": c,
                   "posesiones_mediana": float(np.median(np.r_[obs["na"], obs["nb"]]))}
            if Sn:
                vn = np.mean([float(_V(s.sum(0))) for s in Sn])
                vnb = np.mean([_V(Wb @ s) for s in Sn], axis=0)
                vc = vb - vnb
                res.update({"V_nulo": float(vn), "V_nulo_r80": _q(vnb, (0.10, 0.90)), "V_corregido": float(v - vn),
                            "V_corregido_r80": _q(vc, (0.10, 0.90)), "V_corregido_ic95": _q(vc, (0.025, 0.975)),
                            "DT_corregida": float(np.sqrt(max(v - vn, 0.0)))})
            # factor de atenuación k = (V_plantado − V_nulo) / sd² del mismo orden y medida → V verdadera ≈ V_corregido / k
            tp = sorted(t for t in d["tipo"].unique() if t.startswith(f"plantado{o}_"))
            if tp and Sn and sd_plantado:
                vp = np.mean([float(_V(_sumas(do[do["tipo"] == t], ca, cb, clusters).sum(0))) for t in tp])
                k = (vp - res["V_nulo"]) / sd_plantado ** 2
                res["atenuacion_k"] = float(k)
                if k > 0.02:
                    res["V_verdadera_est"] = float(res["V_corregido"] / k)
                    res["V_verdadera_r80"] = [float(v / k) for v in res["V_corregido_r80"]]
                    res["V_verdadera_ic95"] = [float(v / k) for v in res["V_corregido_ic95"]]
                    res["DT_verdadera_est"] = float(np.sqrt(max(res["V_verdadera_est"], 0.0)))
            fi = {}
            for npos in posesiones_fiab:
                f_obs = v / (v + c / npos) if v > 0 else 0.0
                fi[str(npos)] = {"observada": float(f_obs)}
                if Sn:
                    vcor = max(v - res["V_nulo"], 0.0)
                    fi[str(npos)]["corregida"] = float(vcor / (vcor + c / npos)) if vcor > 0 else 0.0
            res["fiabilidad"] = fi
            out[f"{NOMBRE[o]}_{medida}"] = res
    return out


def _q(x: np.ndarray, qs) -> list:
    x = x[np.isfinite(x)]
    return [float(np.quantile(x, q)) for q in qs] if len(x) else [float("nan")] * len(qs)


def resumen_predictiva(p: pd.DataFrame, B: int, semilla: int) -> dict:
    """Por orden: cambio relativo del error ponderado (efectos de unidad frente a aditivo) agregado y por liga-temporada."""
    out = {}
    if p.empty:
        return out
    obs = p[p["tipo"] == "obs"].copy()
    obs["lt"] = obs["liga"] + "|" + obs["temporada"]
    rng = np.random.default_rng(semilla)
    for o, d in obs.groupby("orden"):
        g = d.groupby(["lt", "partido"])[["sse_k", "sse0", "sse1"]].sum().reset_index()
        tot = float(g["sse1"].sum() / g["sse0"].sum() - 1.0)
        tot_jug = float(g["sse0"].sum() / g["sse_k"].sum() - 1.0)            # ganancia de reajustar jugadores (control)
        por_lt = []
        for lt, gl in g.groupby("lt"):
            s0, s1 = gl["sse0"].to_numpy(), gl["sse1"].to_numpy()
            idx = rng.integers(0, len(gl), size=(B, len(gl)))
            bs = s1[idx].sum(1) / s0[idx].sum(1) - 1.0
            por_lt.append({"lt": lt, "delta_rel": float(s1.sum() / s0.sum() - 1.0), "ic95": _q(bs, (0.025, 0.975))})
        # agregado: bootstrap estratificado de partidos dentro de cada liga-temporada
        ag = []
        grupos = [gl[["sse0", "sse1"]].to_numpy() for _, gl in g.groupby("lt")]
        for _ in range(min(B, 500)):
            s0 = s1 = 0.0
            for arr in grupos:
                i = rng.integers(0, len(arr), len(arr))
                s0 += arr[i, 0].sum()
                s1 += arr[i, 1].sum()
            ag.append(s1 / s0 - 1.0)
        lam = d.drop_duplicates(["lt", "rot", "ajuste"])
        out[NOMBRE[int(o)]] = {
            "delta_rel_agregado": tot, "delta_rel_agregado_ic95": _q(np.array(ag), (0.025, 0.975)),
            "delta_rel_reajuste_jugadores": tot_jug,
            "ligas_temporada": len(por_lt),
            "lt_mejora_ic95": int(sum(x["ic95"][1] < 0 for x in por_lt)),
            "lt_empeora_ic95": int(sum(x["ic95"][0] > 0 for x in por_lt)),
            "lt_sin_diferencia": int(sum(x["ic95"][0] <= 0 <= x["ic95"][1] for x in por_lt)),
            "lambda_en_borde_superior_frac": float((lam["lambda"] == lam["lambda"].max()).mean()),
            "lambda_mediana": float(lam["lambda"].median()),
            "por_lt": por_lt}
    return out


# =============================================================================================== orquestación
def _priors(cfg: dict) -> tuple[dict, float]:
    co = cfg["orden_sinergias"]["version_b"]
    d = CE.RAIZ / co["prior"]
    pri = {}
    for f in sorted(d.glob("20??-??.csv.gz")):
        t = pd.read_csv(f, usecols=["persona_id", "temporada", "prior"])
        pri.update(dict(zip(t["persona_id"].astype(str) + "|" + t["temporada"].astype(str), t["prior"].astype(float))))
    sigma = co.get("sigma") or json.loads((d / "g_prior.json").read_text())["net"]["sigma"]
    return pri, float(sigma)


def _trabajo(args):
    tr_lt, version, cfg, priors, sigma, con_nulo, con_pred = args
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    lt = preparar(tr_lt, CE.semilla(cfg, f"tercios|{tr_lt['liga'].iloc[0]}|{tr_lt['temporada'].iloc[0]}"))
    g = None
    if version == "b":
        gl = np.array([priors.get(k, np.nan) for k in lt.claves])
        falta = np.isnan(gl)
        gl[falta] = np.nanmean(gl) if (~falta).any() else 0.0           # sin prior: media de la liga-temporada (marcado)
    t0 = time.time()
    res = procesar_lt(lt, version, cfg, g=gl if version == "b" else None, sigma=sigma, con_nulo=con_nulo,
                      con_predictiva=con_pred)
    res["info"]["segundos"] = round(time.time() - t0, 1)
    if version == "b":
        res["info"]["sin_prior"] = int(falta.sum())
    return res


def ejecutar(cfg: dict, version: str = "a", ligas=None, procesos: int = 3, con_nulo: bool = True, con_pred: bool = True,
             progreso=print) -> dict:
    from .. import rapm
    cfg40 = CE.cargar_v40(cfg)
    co = cfg["orden_sinergias"]
    tr = rapm.tramos(cfg40, progreso=progreso)
    tr = tr[tr["temporada"].isin(co["temporadas"])]
    if ligas:
        tr = tr[tr["liga"].isin(ligas)]
    priors, sigma = _priors(cfg) if version == "b" else ({}, None)
    grupos = [(d, version, cfg, priors, sigma, con_nulo, con_pred) for _, d in tr.groupby(["liga", "temporada"])]
    grupos.sort(key=lambda a: -len(a[0]))                                # los grandes primero (reparto de carga)
    t0 = time.time()
    resultados = []
    if procesos > 1:
        import multiprocessing as mp
        with mp.get_context("fork").Pool(procesos) as pool:
            for i, r in enumerate(pool.imap_unordered(_trabajo, grupos)):
                resultados.append(r)
                if progreso:
                    progreso(f"  [{version}] {i + 1}/{len(grupos)} {r['info']['liga']} {r['info']['temporada']} "
                             f"({r['info']['tramos']} tramos, {r['info']['segundos']} s) · {time.time() - t0:.0f} s", flush=True)
    else:
        for i, a in enumerate(grupos):
            resultados.append(_trabajo(a))
    filas = pd.concat([r["filas"] for r in resultados if len(r["filas"])], ignore_index=True)
    pred = pd.concat([r["predictiva"] for r in resultados if len(r["predictiva"])], ignore_index=True) if con_pred else pd.DataFrame()
    info = sorted([r["info"] for r in resultados], key=lambda x: (x["liga"], x["temporada"]))
    dsal = CE.dir_salida(cfg, "orden_sinergias")
    suf = version if not ligas else f"{version}_{'-'.join(ligas)}"
    # versionado: sólo las filas observadas; las réplicas nulas y plantadas (≈ 100 MB) van a experimentos/ (regenerables)
    dexp = CE.RAIZ / "experimentos" / "v4_1" / "orden_sinergias"
    dexp.mkdir(parents=True, exist_ok=True)
    filas.to_csv(dexp / f"filas_{suf}.csv.gz", index=False, float_format="%.6g")
    filas[filas["tipo"] == "obs"].to_csv(dsal / f"filas_obs_{suf}.csv.gz", index=False, float_format="%.6g")
    if len(pred):
        pred.to_csv(dsal / f"predictiva_{suf}.csv.gz", index=False, float_format="%.8g")
    (dsal / f"info_{suf}.json").write_text(json.dumps(info, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return {"filas": filas, "predictiva": pred, "info": info, "tramos": int(len(tr)), "ligas": sorted(tr["liga"].unique()),
            "ligas_temporada": int(tr.groupby(["liga", "temporada"]).ngroups), "segundos": round(time.time() - t0)}


def resumir(cfg: dict, filas: pd.DataFrame, pred: pd.DataFrame) -> dict:
    co, cm = cfg["orden_sinergias"], cfg["comunes"]
    B, sem = int(cm["bootstrap"]), int(cm["semilla_bootstrap"])
    elite = set(cm["segmentos"]["elite_club"])
    out = {}
    for seg, m in (("global", np.ones(len(filas), bool)), ("elite_club", filas["liga"].isin(elite).to_numpy())):
        out[seg] = estimar(filas[m], B, sem, tuple(co["fiabilidad_posesiones"]),
                           sd_plantado=float(co.get("calibracion_plantada", {}).get("sd", 0)) or None)
        if len(pred):
            mp_ = pred["liga"].isin(elite) if seg == "elite_club" else np.ones(len(pred), bool)
            out[seg]["predictiva"] = resumen_predictiva(pred[mp_], B, sem)
    return out
