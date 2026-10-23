"""Normalización con AMORTIGUACIÓN del salto de nivel (capa sobre el algoritmo A).

El algoritmo A traduce con una recta por liga, `a = m_l + s_l·z*`, igual en todas las temporadas, y enlaza las ligas
sin puente directo con la EuroLeague mediante el EM conjunto. Con las FEB (Primera, Segunda y Tercera) el salto de
nivel hasta la EuroLeague es grande y casi todo indirecto (Tercera → Segunda → Primera → ACB → EuroLeague): una recta
extrapola sin freno a los mejores jugadores de las ligas lejanas y no dice cuánta incertidumbre se acumula por el
camino. Esta capa conserva los pasos 1-2 del A (z sin suerte en su liga-temporada-posición, ψ, deriva por edad, escala
s) y sustituye el paso 3 por seis piezas (configs/normalization.yaml; docs/normalizacion_amortiguada.md):

1. Encadenamiento jerárquico. Nodo = competición-temporada; arista = desfase de nivel medido con los puentes entre
   dos nodos (misma temporada, o temporadas consecutivas descontando la deriva por edad). El nivel de cada nodo es la
   solución de mínimos cuadrados ponderados del grafo con la EuroLeague = 0: en una cadena, suma de desfases y suma de
   varianzas; con varios caminos, combinación por precisión inversa (`resolver_grafo`; es la ley de resistencias en
   serie/paralelo y la generaliza a caminos que comparten aristas).
2. Contracción bayesiana parcial: nivel(c, t) ~ N(μ_escalón(c), τ²) con μ y τ² por bayes empírico (EM exacto sobre el
   modelo conjunto grafo + previa, `contraccion_jerarquica`). Una temporada con pocos puentes se acerca a su escalón.
3. Mapeo de cuantiles monótono por liga y métrica: F_l (forma), estimada con los puentes (tramos de cuantiles,
   contracción hacia la recta, regresión isotónica y PCHIP). F_l(x) = x si no hay datos.
4. Transferibilidad / compresión de colas: θ_ref = μ_origen + λ(d)·(θ_traducido − μ_origen), λ(0) = 1, decreciente en
   la distancia de nivel d a la EuroLeague; λ̂ por liga se mide como la pendiente (con efecto fijo de arista) del valor
   del puente en la otra competición sobre su valor traducido, y la forma de λ(d) (constante, exponencial, logística)
   se elige por error dejando fuera una liga.
5. Sesgo de selección de los puentes: pesos de probabilidad inversa de un logit de «ser puente» (nivel en su liga,
   edad, minutos, liga y temporada).
6. Unidades: todo en z de capacidad (por 100 posesiones o por minuto dentro de su liga); la duración del partido
   (40 o 48 minutos) sólo cambia la exposición, que aquí se mide en posesiones (`exposicion_posesiones`).

Traducción final de un jugador de la competición c = (l, t) y una métrica:
    θ = δ_c + λ(d_l) · s_l · F_l(z*),   z* = z/(1 + v + ψ_l)
    var θ = var δ_c + (λ s F')² v_post + (λ F)² se(s)²
y su valor en la EuroLeague de referencia μ_EL,pos + τ_EL,pos·θ (deshaciendo la transformación de la métrica).

    python -m bbmodel amortiguar                     # ajuste con todas las temporadas → data/modelos/normalizacion_amortiguada/
    python -m bbmodel amortiguar --validar           # examen temporal (2023→24, 2024→25) y dejando fuera una liga
    python -m bbmodel amortiguar --diagnostico P     # diagnóstico del esquema lineal a partir de un parametros.json
"""
from __future__ import annotations

import heapq
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator
from scipy.optimize import minimize_scalar, minimize
from scipy.stats import norm

from .metricas import CATALOGO, destransformar, transformar

RAIZ = Path(__file__).resolve().parent.parent
DIR_SALIDA = RAIZ / "data" / "modelos" / "normalizacion_amortiguada"
DIR_CACHE = RAIZ / "experimentos" / "cache_normalizacion"     # no versionado (.gitignore)
Z90 = norm.ppf(0.95)
Z80 = norm.ppf(0.9)


def config() -> dict:
    try:
        from bbfit.config import cargar
        return cargar("normalization")
    except Exception:  # noqa: BLE001 — los tests pueden correr sin YAML
        p = RAIZ / "configs" / "normalization.yaml"
        import yaml
        return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}


# =============================================================================================== 1. grafo
def resolver_grafo(n: int, aristas: list[tuple[int, int, float, float]], ref: int | None = 0,
                   previa_media=None, previa_var=None) -> tuple[np.ndarray, np.ndarray]:
    """Niveles δ (n nodos) a partir de aristas (i, j, d, v): d mide δ_i − δ_j con varianza v.

    `ref`: nodo fijado a 0 (None si no hay). Previa opcional δ_k ~ N(previa_media_k, previa_var_k) (np.inf = sin previa).
    Devuelve (media, covarianza); los nodos sin camino a la referencia ni previa quedan en NaN.
    Equivale a sumar desfases y varianzas a lo largo de un camino y a combinar caminos por precisión inversa."""
    libres = [k for k in range(n) if k != ref]
    pos = np.full(n, -1)
    pos[libres] = np.arange(len(libres))
    m = len(libres)
    P = np.zeros((m, m))
    b = np.zeros(m)
    if len(aristas):
        A = np.asarray(aristas, float)
        i, j = A[:, 0].astype(int), A[:, 1].astype(int)
        w, d = 1.0 / A[:, 3], A[:, 2]
        pi, pj = pos[i], pos[j]
        si, sj = pi >= 0, pj >= 0
        np.add.at(b, pi[si], w[si] * d[si])
        np.add.at(b, pj[sj], -w[sj] * d[sj])
        np.add.at(P, (pi[si], pi[si]), w[si])
        np.add.at(P, (pj[sj], pj[sj]), w[sj])
        ambos = si & sj
        np.add.at(P, (pi[ambos], pj[ambos]), -w[ambos])
        np.add.at(P, (pj[ambos], pi[ambos]), -w[ambos])
    if previa_var is not None:
        pv = np.asarray(previa_var, float)
        pm = np.asarray(previa_media, float)
        for k in libres:
            if np.isfinite(pv[k]) and pv[k] > 0:
                P[pos[k], pos[k]] += 1.0 / pv[k]
                b[pos[k]] += pm[k] / pv[k]
    media = np.full(n, np.nan)
    cov = np.full((n, n), np.nan)
    if ref is not None:
        media[ref] = 0.0
        cov[ref, :] = 0.0
        cov[:, ref] = 0.0
    # componentes identificadas: las conectadas (por aristas) a la referencia o con previa
    ident = _identificados(n, aristas, ref, previa_var)
    sel = [pos[k] for k in libres if ident[k]]
    if sel:
        Ps = P[np.ix_(sel, sel)]
        C = np.linalg.inv(Ps)
        mu = C @ b[sel]
        orden = np.array([libres[s] for s in sel])
        media[orden] = mu
        cov[np.ix_(orden, orden)] = C
    return media, cov


def _identificados(n, aristas, ref, previa_var) -> np.ndarray:
    ady = [[] for _ in range(n)]
    for i, j, _, _ in aristas:
        ady[i].append(j)
        ady[j].append(i)
    semilla = set()
    if ref is not None:
        semilla.add(ref)
    if previa_var is not None:
        semilla |= {k for k in range(n) if np.isfinite(previa_var[k]) and previa_var[k] > 0}
    vis = np.zeros(n, bool)
    pila = list(semilla)
    for s in pila:
        vis[s] = True
    while pila:
        a = pila.pop()
        for c in ady[a]:
            if not vis[c]:
                vis[c] = True
                pila.append(c)
    return vis


def camino_preciso(n: int, aristas: list[tuple[int, int, float, float]], origen: int, ref: int) -> tuple[list[int], float]:
    """Camino de menor varianza acumulada de `origen` a `ref` (Dijkstra) y esa varianza."""
    ady = [[] for _ in range(n)]
    for i, j, _, v in aristas:
        ady[i].append((j, v))
        ady[j].append((i, v))
    dist = np.full(n, np.inf)
    prev = [-1] * n
    dist[origen] = 0.0
    h = [(0.0, origen)]
    while h:
        d, a = heapq.heappop(h)
        if d > dist[a]:
            continue
        if a == ref:
            break
        for c, v in ady[a]:
            if d + v < dist[c]:
                dist[c] = d + v
                prev[c] = a
                heapq.heappush(h, (d + v, c))
    if not np.isfinite(dist[ref]):
        return [], np.inf
    camino = [ref]
    while camino[-1] != origen:
        camino.append(prev[camino[-1]])
    return camino[::-1], float(dist[ref])


# =============================================================================================== 2. contracción
def contraccion_jerarquica(n: int, aristas, ref: int, escalon: list[str | None], tau2_inicial: float = 0.05,
                           tau2_minimo: float = 0.0025, hiperprevia_sd: float = 2.0, iteraciones: int = 200) -> dict:
    """Contracción bayesiana parcial: nivel_c = μ_escalón(c) + ε_c, ε_c ~ N(0, τ²), μ_escalón ~ N(0, hiperprevia_sd²).

    Las medias de escalón son nodos LATENTES del grafo (una arista δ_c − μ_k = 0 con varianza τ² por cada nodo del
    escalón, y una previa débil sobre μ_k): la posterior conjunta integra la incertidumbre de μ (un escalón de una sola
    liga comparte el camino de puentes de todas sus temporadas, y esa incertidumbre común no desaparece al promediar).
    τ² por bayes empírico con EM: τ² = media de E[(δ_c − μ_k)²] = (m_c − m_k)² + V_cc + V_kk − 2·V_ck.
    El nodo de referencia no entra en la previa (está fijado a 0)."""
    escalones = sorted({e for k, e in enumerate(escalon) if e is not None and k != ref})
    nodo_mu = {e: n + i for i, e in enumerate(escalones)}
    N = n + len(escalones)
    libres = [k for k in range(n) if k != ref and escalon[k] is not None]
    pv = np.full(N, np.inf)
    for e in escalones:
        pv[nodo_mu[e]] = hiperprevia_sd ** 2
    pm = np.zeros(N)
    tau2 = float(tau2_inicial)

    def resolver(t2):
        ar = list(aristas) + [(k, nodo_mu[escalon[k]], 0.0, t2) for k in libres]
        return resolver_grafo(N, ar, ref, pm, pv)

    it = 0
    for it in range(iteraciones):
        media, cov = resolver(tau2)
        t2 = float(np.mean([(media[k] - media[nodo_mu[escalon[k]]]) ** 2 + cov[k, k] + cov[nodo_mu[escalon[k]], nodo_mu[escalon[k]]]
                            - 2 * cov[k, nodo_mu[escalon[k]]] for k in libres])) if libres else tau2
        t2 = max(t2, tau2_minimo)
        cambio = abs(t2 - tau2)
        tau2 = t2
        if cambio < 1e-7:
            break
    media, cov = resolver(tau2)
    mu = {e: float(media[nodo_mu[e]]) for e in escalones}
    mu_sd = {e: float(np.sqrt(cov[nodo_mu[e], nodo_mu[e]])) for e in escalones}
    return {"media": media[:n], "cov": cov[:n, :n], "mu_escalon": mu, "mu_escalon_sd": mu_sd, "tau2": tau2,
            "iteraciones": it + 1}


# =============================================================================================== 3. mapeo monótono
def isotonica(y: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Regresión isotónica creciente (PAVA) de y con pesos w (y ya ordenado por x)."""
    y = np.asarray(y, float)
    w = np.asarray(w, float)
    bloques = []  # [media, peso, tamaño]
    for yi, wi in zip(y, w):
        bloques.append([yi, wi, 1])
        while len(bloques) > 1 and bloques[-2][0] > bloques[-1][0]:
            m2, w2, n2 = bloques.pop()
            m1, w1, n1 = bloques.pop()
            ww = w1 + w2
            bloques.append([(m1 * w1 + m2 * w2) / ww if ww > 0 else (m1 + m2) / 2, ww, n1 + n2])
    out = []
    for m, _, k in bloques:
        out += [m] * k
    return np.array(out)


class Mapeo:
    """Función monótona creciente F con F(0) = 0, lineal (pendiente 1) fuera de los nodos."""

    def __init__(self, xs=None, ys=None):
        if xs is None or len(xs) < 2:
            self.xs = np.array([-1.0, 1.0])
            self.ys = np.array([-1.0, 1.0])
        else:
            self.xs = np.asarray(xs, float)
            self.ys = np.asarray(ys, float)
        self._f = PchipInterpolator(self.xs, self.ys, extrapolate=False)
        self._c = 0.0
        self._c = float(self(0.0))

    @property
    def es_lineal(self) -> bool:
        return bool(np.allclose(self.ys - self.xs, (self.ys - self.xs)[0]))

    def __call__(self, x):
        x = np.asarray(x, float)
        y = self._f(np.clip(x, self.xs[0], self.xs[-1]))
        y = np.where(x < self.xs[0], self.ys[0] + (x - self.xs[0]), y)
        y = np.where(x > self.xs[-1], self.ys[-1] + (x - self.xs[-1]), y)
        return y - self._c

    def derivada(self, x):
        """F'(x), con suelo 0,05 (evita varianzas nulas en tramos casi planos)."""
        x = np.asarray(x, float)
        d = self._f.derivative()(np.clip(x, self.xs[0], self.xs[-1]))
        return np.maximum(np.where((x < self.xs[0]) | (x > self.xs[-1]), 1.0, d), 0.05)

    def inversa(self, y):
        """F⁻¹ (numérica: F es estrictamente creciente salvo tramos planos, donde se toma el centro)."""
        y = np.asarray(y, float)
        malla = np.linspace(self.xs[0] - 10, self.xs[-1] + 10, 4001)
        fm = self(malla)
        fm = np.maximum.accumulate(fm + np.arange(len(fm)) * 1e-12)
        return np.interp(y, fm, malla, left=np.nan, right=np.nan)

    def a_dict(self) -> dict:
        return {"x": [round(float(v), 5) for v in self.xs], "y": [round(float(v), 5) for v in self.ys]}


def ajustar_mapeo(x: np.ndarray, y: np.ndarray, w: np.ndarray, nodos: int = 7, puentes_previa: float = 30,
                  min_puentes: int = 40) -> Mapeo:
    """Forma monótona de y frente a x (ambos en la misma escala): tramos de cuantiles de x, media ponderada de y en
    cada tramo contraída hacia la recta y = x con el peso de `puentes_previa` puentes, regresión isotónica y PCHIP.
    Con menos de `min_puentes` puentes devuelve la recta."""
    x, y, w = (np.asarray(v, float) for v in (x, y, w))
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(w) & (w > 0)
    x, y, w = x[ok], y[ok], w[ok]
    if len(x) < min_puentes:
        return Mapeo()
    cortes = np.unique(np.quantile(x, np.linspace(0, 1, nodos + 1)))
    if len(cortes) < 3:
        return Mapeo()
    tramo = np.clip(np.searchsorted(cortes, x, side="right") - 1, 0, len(cortes) - 2)
    xs, ys, ws = [], [], []
    for b in range(len(cortes) - 1):
        s = tramo == b
        if not s.any():
            continue
        wb = w[s] / w[s].mean()                # pesos relativos (n efectivo ≈ número de puentes del tramo)
        n_ef = wb.sum() ** 2 / (wb ** 2).sum()
        xb = float(np.average(x[s], weights=wb))
        yb = float(np.average(y[s], weights=wb))
        k = n_ef / (n_ef + puentes_previa)
        xs.append(xb)
        ys.append(k * yb + (1 - k) * xb)
        ws.append(n_ef + puentes_previa)
    if len(xs) < 2:
        return Mapeo()
    xs = np.array(xs)
    ys = isotonica(np.array(ys), np.array(ws))
    # estrictamente creciente: los empates de la isotónica dejarían tramos planos (F' = 0 → puentes sin varianza)
    ys = ys + np.arange(len(ys)) * 1e-3 * max(float(np.ptp(xs)), 1e-3)
    # estrictamente creciente (PCHIP necesita x distintos; y no decreciente basta) y anclas lineales en los extremos
    xs, idx = np.unique(xs, return_index=True)
    ys = ys[idx]
    return Mapeo(xs, ys)


# =============================================================================================== 4. λ(d)
def forma_lambda(forma: str, d, p, lambda_minimo: float = 0.0):
    d = np.asarray(d, float)
    if forma == "constante":
        lam = np.ones_like(d)
    elif forma == "exponencial":
        lam = np.exp(-d / max(p[0], 1e-6))
    elif forma == "logistica":
        d0, s = p[0], max(p[1], 1e-3)
        lam = (1 + np.exp(-d0 / s)) / (1 + np.exp((d - d0) / s))
    else:
        raise ValueError(forma)
    return np.clip(lam, lambda_minimo, 1.0)


def ajustar_forma_lambda(forma: str, d, lam, var, lambda_minimo: float = 0.0):
    """Mínimos cuadrados ponderados (1/var) de λ̂ frente a d con la forma dada. Devuelve parámetros."""
    d, lam, var = (np.asarray(v, float) for v in (d, lam, var))
    w = 1.0 / var
    if forma == "constante":
        return []
    if forma == "exponencial":
        f = lambda ld: float(np.sum(w * (lam - forma_lambda("exponencial", d, [np.exp(ld)], lambda_minimo)) ** 2))  # noqa: E731
        r = minimize_scalar(f, bounds=(np.log(0.05), np.log(200.0)), method="bounded")
        return [float(np.exp(r.x))]
    f = lambda q: float(np.sum(w * (lam - forma_lambda("logistica", d, [q[0], np.exp(q[1])], lambda_minimo)) ** 2))  # noqa: E731
    mejor = None
    for d0 in (0.5, 1.0, 2.0, 3.0):
        for ls in (np.log(0.2), np.log(0.5), np.log(1.0)):
            r = minimize(f, [d0, ls], method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-8, "maxiter": 2000})
            if mejor is None or r.fun < mejor.fun:
                mejor = r
    return [float(mejor.x[0]), float(np.exp(mejor.x[1]))]


def elegir_lambda(tabla: pd.DataFrame, formas: list[str], lambda_minimo: float = 0.0) -> dict:
    """tabla: liga, d, lam, var (una fila por liga y métrica). Error dejando fuera una liga (ponderado por 1/var)
    para cada forma; se elige la de menor error (a igualdad, la más simple: orden de `formas`)."""
    t = tabla[np.isfinite(tabla["lam"]) & np.isfinite(tabla["var"]) & (tabla["var"] > 0)].copy()
    # heterogeneidad entre ligas y métricas (por momentos) para no sobreponderar las λ̂ muy precisas
    w = 1 / t["var"]
    media = np.average(t["lam"], weights=w)
    het = max(0.0, float(np.average((t["lam"] - media) ** 2, weights=w) - np.average(t["var"], weights=w)))
    t["var_tot"] = t["var"] + het
    res = {"heterogeneidad": het, "formas": {}}
    for forma in formas:
        err, pesos = 0.0, 0.0
        for liga in t["liga"].unique():
            tr, te = t[t["liga"] != liga], t[t["liga"] == liga]
            p = ajustar_forma_lambda(forma, tr["d"], tr["lam"], tr["var_tot"], lambda_minimo)
            pred = forma_lambda(forma, te["d"], p, lambda_minimo)
            ww = 1 / te["var_tot"].to_numpy()
            err += float(np.sum(ww * (te["lam"].to_numpy() - pred) ** 2))
            pesos += float(ww.sum())
        p = ajustar_forma_lambda(forma, t["d"], t["lam"], t["var_tot"], lambda_minimo)
        res["formas"][forma] = {"parametros": p, "error_lolo": err / pesos if pesos else np.nan}
    validas = [f for f in formas if np.isfinite(res["formas"][f]["error_lolo"])]
    mejor = min(validas, key=lambda f: (round(res["formas"][f]["error_lolo"], 6), formas.index(f)))
    res["elegida"] = mejor
    res["parametros"] = res["formas"][mejor]["parametros"]
    return res


# =============================================================================================== 5. selección
def pesos_ipw(filas: pd.DataFrame, puente: np.ndarray, C: float = 1.0, recorte=(0.01, 0.99)) -> tuple[np.ndarray, dict]:
    """Probabilidad de ser puente con un logit (nivel en su liga, edad, minutos, liga, temporada) → pesos 1/p,
    recortados por percentiles y normalizados a media 1 entre los puentes."""
    from sklearn.linear_model import LogisticRegression
    X = pd.DataFrame({"nivel": filas["nivel"].fillna(0.0), "edad": filas["edad"].fillna(filas["edad"].median()),
                      "sin_edad": filas["edad"].isna().astype(float), "log_min": np.log(filas["min"].clip(lower=1))})
    X["edad2"] = (X["edad"] - 26) ** 2
    X["nivel2"] = X["nivel"] ** 2
    X = pd.concat([X, pd.get_dummies(filas["liga"], prefix="l", dtype=float),
                   pd.get_dummies(filas["temporada"], prefix="t", dtype=float)], axis=1)
    mu, sd = X.mean(), X.std().replace(0, 1)
    Xs = ((X - mu) / sd).to_numpy(float)
    y = np.asarray(puente, int)
    if y.min() == y.max():
        return np.ones(len(y)), {"ipw": False}
    m = LogisticRegression(C=C, max_iter=2000).fit(Xs, y)
    p = m.predict_proba(Xs)[:, 1]
    w = 1.0 / np.clip(p, 1e-4, 1)
    lo, hi = np.quantile(w[y == 1], recorte)
    w = np.clip(w, lo, hi)
    w = w / w[y == 1].mean()
    coef = dict(zip(X.columns, (m.coef_[0] / sd.to_numpy()).round(4)))
    info = {"ipw": True, "n": int(len(y)), "puentes": int(y.sum()), "p_media_puentes": float(p[y == 1].mean()),
            "p_media_resto": float(p[y == 0].mean()),
            "coef_nivel": float(coef["nivel"]), "coef_edad": float(coef["edad"]), "coef_log_min": float(coef["log_min"])}
    return w, info


# =============================================================================================== 6. unidades
def exposicion_posesiones(t: pd.DataFrame, minutos_partido: dict) -> pd.Series:
    """Posesiones en pista de cada fila; si faltan, minutos × ritmo del equipo / minutos de partido (40 FIBA, 48 NBA)."""
    mp = t["liga"].map(lambda l: minutos_partido.get(l, minutos_partido.get("defecto", 40))).astype(float)
    est = pd.to_numeric(t.get("min"), errors="coerce") * pd.to_numeric(t.get("team_pace"), errors="coerce") / mp
    return pd.to_numeric(t.get("poss_on_court"), errors="coerce").fillna(est)


# =============================================================================================== datos
def z_por_metrica(tabla: pd.DataFrame, params: dict, metricas: list[str] | None = None) -> dict:
    """z_obs, v_obs del paso 1 del A para cada métrica (se recalculan: son deterministas dados los datos)."""
    from . import suerte
    if "_z" in params:
        return params["_z"]
    return {col: suerte.ajustar_metrica(tabla, col)[0] for col in (metricas or params["metricas"])}


def filas_metrica(tabla: pd.DataFrame, z: pd.DataFrame, enlace: dict) -> pd.DataFrame:
    """Filas con z*, varianzas y el nodo competición-temporada."""
    f = tabla[["persona_id", "liga", "temporada", "anio", "anio_nac", "min", "pos3", "player_id"]].join(z[["z_obs", "v_obs"]])
    f = f[f["z_obs"].notna() & f["liga"].isin(list(enlace["m"]))].copy()
    psi = f["liga"].map(enlace["psi"]).astype(float)
    f["psi"] = psi
    f["z_est"] = f["z_obs"] / (1 + f["v_obs"] + psi)
    f["v_est"] = (f["v_obs"] + psi) / (1 + f["v_obs"] + psi)
    f["s"] = f["liga"].map(enlace["s"]).astype(float)
    f["s_se"] = f["liga"].map(enlace.get("s_se", {})).astype(float).fillna(0.0)
    f["nodo"] = f["liga"] + ":" + f["temporada"]
    return f


def construir_puentes(f: pd.DataFrame, min_minutos: float, consecutivas: bool = True) -> pd.DataFrame:
    """Parejas de observaciones de la misma persona en dos competiciones distintas (misma temporada o t, t+1)."""
    g = f[f["min"] >= min_minutos][["persona_id", "liga", "anio", "nodo"]].reset_index().rename(columns={"index": "fila"})
    a = g.merge(g, on="persona_id", suffixes=("_a", "_b"))
    a = a[a["liga_a"] != a["liga_b"]]
    mismo = a[(a["anio_a"] == a["anio_b"]) & (a["liga_a"] < a["liga_b"])]
    partes = [mismo]
    if consecutivas:
        partes.append(a[a["anio_b"] == a["anio_a"] + 1])
    p = pd.concat(partes, ignore_index=True)
    p["dt"] = p["anio_b"] - p["anio_a"]
    return p[["persona_id", "fila_a", "fila_b", "nodo_a", "nodo_b", "liga_a", "liga_b", "anio_a", "dt"]]


class Estado:
    """Parámetros vigentes de la amortiguación (por métrica): nivel por nodo, forma F y λ por liga."""

    def __init__(self, enlace: dict, nodos: list[str], ref_liga: str):
        self.enlace = enlace
        self.nodos = nodos
        self.idx = {n: i for i, n in enumerate(nodos)}
        self.ref_liga = ref_liga
        # arranque: nivel = m_l del A en todas sus temporadas, λ = 1, F = recta
        self.delta = np.array([enlace["m"].get(n.split(":")[0], 0.0) for n in nodos], float)
        self.delta_var = np.zeros(len(nodos))
        self.F = {}
        self.lam = {}

    def g(self, liga, z):
        """Desviación respecto al nivel de su competición en la vara de referencia: λ_l · F_l(s_l·z)."""
        F = self.F.get(liga) or Mapeo()
        return self.lam.get(liga, 1.0) * F(self.enlace["s"][liga] * np.asarray(z, float))

    def gp(self, liga, z):
        F = self.F.get(liga) or Mapeo()
        s = self.enlace["s"][liga]
        return self.lam.get(liga, 1.0) * s * F.derivada(s * np.asarray(z, float))


def medidas_puentes(P: pd.DataFrame, f: pd.DataFrame, est: Estado, ipw: np.ndarray | None) -> pd.DataFrame:
    """Cada puente mide δ_x − δ_y (x = lado de menor nivel, que se predice; y = lado observado)."""
    e = est.enlace
    A = f.loc[P["fila_a"]].reset_index(drop=True)
    B = f.loc[P["fila_b"]].reset_index(drop=True)
    da = est.delta[[est.idx[n] for n in A["nodo"]]]
    db = est.delta[[est.idx[n] for n in B["nodo"]]]
    x_es_a = (da <= db) | (B["liga"] == est.ref_liga).to_numpy()
    x_es_a &= ~(A["liga"] == est.ref_liga).to_numpy()
    X = pd.concat([A[x_es_a], B[~x_es_a]]).sort_index()
    Y = pd.concat([B[x_es_a], A[~x_es_a]]).sort_index()
    signo = np.where(x_es_a, 1.0, -1.0)            # tiempo de y menos tiempo de x
    dt = P["dt"].to_numpy() * signo
    edad = (np.where(x_es_a, A["anio"], B["anio"]) - X["anio_nac"].to_numpy())
    from .enlace import tramo_edad
    der = np.array([e["deriva"].get(tramo_edad(v), 0.0) for v in edad])
    gx = np.empty(len(P)); gy = np.empty(len(P)); vx = np.empty(len(P)); vy = np.empty(len(P)); xs = np.empty(len(P))
    for liga in set(X["liga"]) | set(Y["liga"]):
        sx = (X["liga"] == liga).to_numpy()
        sy = (Y["liga"] == liga).to_numpy()
        if sx.any():
            zx = X.loc[sx, "z_est"].to_numpy()
            gx[sx] = est.g(liga, zx)
            xs[sx] = e["s"][liga] * zx
            vx[sx] = est.gp(liga, zx) ** 2 * X.loc[sx, "v_est"].to_numpy()
        if sy.any():
            zy = Y.loc[sy, "z_obs"].to_numpy()
            gy[sy] = est.g(liga, zy)
            vy[sy] = est.gp(liga, zy) ** 2 * (Y.loc[sy, "v_obs"].to_numpy() + Y.loc[sy, "psi"].to_numpy())
    var = np.maximum(vx + vy + e["eta2"] * np.abs(dt), 1e-4)
    out = pd.DataFrame({"persona_id": P["persona_id"].to_numpy(), "nodo_x": X["nodo"].to_numpy(),
                        "nodo_y": Y["nodo"].to_numpy(), "liga_x": X["liga"].to_numpy(), "liga_y": Y["liga"].to_numpy(),
                        "medida": gy - gx - der * dt, "var": var, "x": xs, "gx": gx,
                        "y_ref": gy + est.delta[[est.idx[n] for n in Y["nodo"]]] - der * dt, "w": 1.0})
    if ipw is not None:
        out["w"] = np.sqrt(ipw[P["fila_a"].to_numpy()] * ipw[P["fila_b"].to_numpy()])
    out["arista"] = np.where(out["nodo_x"] < out["nodo_y"], out["nodo_x"] + "|" + out["nodo_y"],
                             out["nodo_y"] + "|" + out["nodo_x"])
    return out


def aristas_de(med: pd.DataFrame, est: Estado, cfg: dict) -> tuple[list, pd.DataFrame]:
    """Una arista por pareja de nodos: media ponderada (w/var) de las medidas, con varianza sándwich."""
    vmin = float(cfg.get("encadenamiento", {}).get("varianza_minima_arista", 4e-4))
    sobre = bool(cfg.get("encadenamiento", {}).get("sobredispersion", True))
    nmin = int(cfg.get("puentes", {}).get("min_puentes_arista", 3))
    filas = []
    for (nx, ny), g in med.groupby(["nodo_x", "nodo_y"]):
        if len(g) < nmin:
            continue
        om = g["w"].to_numpy() / g["var"].to_numpy()
        d = float(np.sum(om * g["medida"]) / om.sum())
        v_mod = float(np.sum(om ** 2 * g["var"]) / om.sum() ** 2)
        v = v_mod
        if sobre and len(g) > 1:
            v_emp = float(np.sum(om ** 2 * (g["medida"] - d) ** 2) / om.sum() ** 2) * len(g) / (len(g) - 1)
            v = max(v_mod, v_emp)
        filas.append({"nodo_x": nx, "nodo_y": ny, "d": d, "var": max(v, vmin), "n": len(g),
                      "n_personas": int(g["persona_id"].nunique())})
    ar = pd.DataFrame(filas)
    lista = [(est.idx[r.nodo_x], est.idx[r.nodo_y], r.d, r.var) for r in ar.itertuples()] if len(ar) else []
    return lista, ar


def lambda_por_liga(med: pd.DataFrame) -> pd.DataFrame:
    """λ̂ de cada liga (lado x): pendiente del valor de referencia del puente sobre s·z* con efecto fijo de arista."""
    filas = []
    for liga, g in med.groupby("liga_x"):
        om = g["w"].to_numpy() / g["var"].to_numpy()
        # medias ponderadas por arista (efecto fijo: cada pareja de competiciones tiene su propio desfase)
        dfw = pd.DataFrame({"a": g["arista"], "om": om, "x": g["x"], "y": g["y_ref"]})
        sw = dfw.groupby("a")["om"].transform("sum")
        xb = (dfw["om"] * dfw["x"]).groupby(dfw["a"]).transform("sum") / sw
        yb = (dfw["om"] * dfw["y"]).groupby(dfw["a"]).transform("sum") / sw
        dx, dy = (dfw["x"] - xb).to_numpy(), (dfw["y"] - yb).to_numpy()
        sxx = float(np.sum(om * dx * dx))
        if sxx <= 0 or len(g) < 20:
            continue
        lam = float(np.sum(om * dx * dy) / sxx)
        res = dy - lam * dx
        var = float(np.sum(om ** 2 * dx ** 2 * res ** 2) / sxx ** 2) * len(g) / max(len(g) - 1, 1)
        filas.append({"liga": liga, "lam": lam, "var": max(var, 1e-6), "n": len(g),
                      "resid_x": dx, "resid_y": dy, "om": om, "xm": xb.to_numpy()})
    return pd.DataFrame(filas)


# =============================================================================================== ajuste
def ajustar_metrica(col: str, f: pd.DataFrame, enlace: dict, cfg: dict, lam_liga: dict, ipw: np.ndarray | None,
                    escalon_de: dict, ref: str, iter_internas: int = 2, mapeo: bool = True) -> dict:
    """Niveles por competición-temporada (encadenamiento + contracción), forma F y λ̂ por liga para una métrica."""
    pc = cfg.get("puentes", {})
    P = construir_puentes(f, float(pc.get("min_minutos", 150)), bool(pc.get("consecutivas", True)))
    nodos = sorted(f["nodo"].unique())
    est = Estado(enlace, nodos, ref)
    est.lam = dict(lam_liga)
    ref_nodos = [n for n in nodos if n.startswith(ref + ":")]
    # la referencia es la EuroLeague de TODAS las temporadas (nivel 0, como en el A): un nodo virtual común
    # → se colapsan sus nodos en uno (índice del primero)
    cc = cfg.get("contraccion", {})
    mp = cfg.get("mapeo", {})
    res = {}
    for _ in range(iter_internas):
        med = medidas_puentes(P, f, est, ipw)
        med = med.assign(nodo_x=med["nodo_x"].where(~med["nodo_x"].isin(ref_nodos), "REF"),
                         nodo_y=med["nodo_y"].where(~med["nodo_y"].isin(ref_nodos), "REF"))
        nodos_g = ["REF"] + [n for n in nodos if n not in ref_nodos]
        est_g = Estado(enlace, nodos_g, ref)
        aristas, ar = aristas_de(med, est_g, cfg)
        escalon = [None] + [escalon_de.get(n.split(":")[0]) for n in nodos_g[1:]]
        ch = contraccion_jerarquica(len(nodos_g), aristas, 0, escalon, float(cc.get("tau2_inicial", 0.05)),
                                    float(cc.get("tau2_minimo", 0.0025)), float(cc.get("hiperprevia_sd", 2.0)),
                                    int(cc.get("iteraciones_em", 200)))
        bruto, cov_b = resolver_grafo(len(nodos_g), aristas, 0)
        for n in nodos:
            k = 0 if n in ref_nodos else nodos_g.index(n)
            est.delta[est.idx[n]] = ch["media"][k]
            est.delta_var[est.idx[n]] = max(ch["cov"][k, k], 0.0) if np.isfinite(ch["cov"][k, k]) else np.nan
        # forma F por liga (puentes del lado x), centrada en λ̂ de la propia liga
        med = medidas_puentes(P, f, est, ipw)
        lp = lambda_por_liga(med)
        if mapeo:
            for r in lp.itertuples():
                if r.liga == ref or r.lam <= 0.2:
                    continue
                g = med[med["liga_x"] == r.liga]
                # y en la escala de x: (y_ref − media de su arista) / λ̂ + media de x de su arista
                yy = r.resid_y / r.lam + r.xm
                est.F[r.liga] = ajustar_mapeo(g["x"].to_numpy(), yy, r.om * np.mean(1 / r.om),
                                              int(mp.get("nodos", 7)), float(mp.get("puentes_previa", 30)),
                                              int(mp.get("min_puentes_liga", 40)))
        res = {"aristas": ar, "contraccion": ch, "bruto": (bruto, cov_b), "nodos_g": nodos_g, "lam_hat": lp,
               "medidas": med}
    # camino de mayor precisión de cada nodo a la referencia
    caminos = {}
    for n in nodos:
        if n in ref_nodos:
            caminos[n] = n
            continue
        k = nodos_g.index(n)
        cam, _ = camino_preciso(len(nodos_g), aristas, k, 0)
        caminos[n] = "→".join(("euroleague" if c == 0 else nodos_g[c]) for c in cam) if cam else "sin camino (escalón)"
    med = res["medidas"]
    cuenta = pd.concat([med["nodo_x"], med["nodo_y"]]).value_counts()
    n_puentes = {n: int(cuenta.get(n, 0)) for n in nodos}
    res.update({"estado": est, "caminos": caminos, "n_puentes": n_puentes, "ref_nodos": ref_nodos, "metrica": col})
    return res


def nivel_filas(tabla: pd.DataFrame, zs: dict, metricas_nivel: list[str]) -> pd.Series:
    """Nivel de cada fila en su liga-temporada: media de z* con signo de las métricas de nivel (para el logit)."""
    cols = []
    for c in metricas_nivel:
        if c in zs:
            z = zs[c]
            cols.append(CATALOGO[c].sentido * (z["z_obs"] / (1 + z["v_obs"])).reindex(tabla.index))
    return pd.concat(cols, axis=1).mean(axis=1) if cols else pd.Series(0.0, index=tabla.index)


def indicador_puente(tabla: pd.DataFrame, min_minutos: float) -> np.ndarray:
    g = tabla[tabla["min"] >= min_minutos][["persona_id", "liga", "anio"]]
    a = g.reset_index().merge(g, on="persona_id", suffixes=("", "_o"))
    a = a[(a["liga"] != a["liga_o"]) & ((a["anio_o"] - a["anio"]).abs() <= 1)]
    return tabla.index.isin(a["index"].unique())


def distancia_liga(offsets: dict, metricas_nivel: list[str]) -> dict:
    """d_l = |mediana con signo del nivel de la liga (media de sus temporadas) en las métricas de nivel|. Mediana y no
    media: una métrica de nivel muy dependiente del equipo (DRtg individual) puede encadenar desfases erráticos y
    no debe decidir sola la distancia."""
    acum = {}
    for c in metricas_nivel:
        if c not in offsets:
            continue
        for liga, v in offsets[c].items():
            acum.setdefault(liga, []).append(CATALOGO[c].sentido * v)
    return {l: float(abs(np.median(v))) for l, v in acum.items()}


def ajustar(tabla: pd.DataFrame, params: dict, cfg: dict | None = None, hasta_anio: int | None = None,
            ipw: bool | None = None, mapeo: bool = True, amortiguar_lambda: bool = True, progreso=print,
            metricas: list[str] | None = None) -> dict:
    """Ajuste completo de la amortiguación sobre unos parámetros del algoritmo A."""
    cfg = cfg or config()
    ref = cfg.get("referencia", "euroleague")
    base = tabla if hasta_anio is None else tabla[tabla["anio"] <= hasta_anio]
    tc0 = (cfg.get("transferibilidad", {}) or {}).get("metricas_nivel", [])
    zs = z_por_metrica(base, params, None if metricas is None else sorted(set(metricas) | set(tc0)))
    escalon_de = {l: e for e, ls in cfg.get("escalones", {}).items() for l in ls}
    tc = cfg.get("transferibilidad", {})
    mn = tc.get("metricas_nivel", ["per", "pts_p100"])
    lam_min = float(tc.get("lambda_minimo", 0.2))
    pc = cfg.get("puentes", {})
    sel = cfg.get("seleccion", {})
    usar_ipw = bool(sel.get("ipw", True)) if ipw is None else ipw
    w_ipw, info_ipw = None, {"ipw": False}
    if usar_ipw:
        niv = nivel_filas(base, zs, mn)
        fil = base.assign(nivel=niv, edad=base["anio"] - base["anio_nac"])
        es_p = indicador_puente(base, float(pc.get("min_minutos", 150)))
        w, info_ipw = pesos_ipw(fil, es_p, float(sel.get("C", 1.0)), tuple(sel.get("recorte_pesos", (0.01, 0.99))))
        w_ipw = pd.Series(w, index=base.index)
    metricas = [m for m in (metricas or list(params["metricas"])) if m in params["metricas"]]
    filas = {}
    for col in metricas:
        filas[col] = filas_metrica(base, zs[col], params["metricas"][col]["enlace"])
    ipw_arr = None
    if w_ipw is not None:
        ipw_arr = np.ones(int(tabla.index.max()) + 1)
        ipw_arr[base.index.to_numpy()] = w_ipw.to_numpy()
    # distancias iniciales con el A
    lam_liga = {}
    dist = distancia_liga({c: params["metricas"][c]["enlace"]["m"] for c in metricas}, mn)
    resultados, info_lambda = {}, {}
    n_ext = int(cfg.get("iteraciones_externas", 4))
    lam_prev = {}
    for it in range(n_ext):
        lam_tab = []
        for col in metricas:
            r = ajustar_metrica(col, filas[col], params["metricas"][col]["enlace"], cfg, lam_liga.get(col, {}),
                                ipw_arr, escalon_de, ref, mapeo=mapeo)
            resultados[col] = r
            for x in r["lam_hat"].itertuples():
                if x.liga in dist:
                    lam_tab.append({"metrica": col, "liga": x.liga, "lam": x.lam, "var": x.var, "n": x.n})
        # niveles medios por liga (media de temporadas, ponderada por precisión) → distancias
        offs = {}
        for col, r in resultados.items():
            est = r["estado"]
            dfn = pd.DataFrame({"nodo": est.nodos, "d": est.delta, "v": est.delta_var})
            dfn["liga"] = dfn["nodo"].str.split(":").str[0]
            offs[col] = dfn.groupby("liga")["d"].mean().to_dict()
        dist = distancia_liga(offs, mn)
        lt = pd.DataFrame(lam_tab)
        lt["d"] = lt["liga"].map(dist)
        if amortiguar_lambda and len(lt):
            info_lambda = elegir_lambda(lt, list(tc.get("formas", ["constante", "exponencial", "logistica"])), lam_min)
            lam_g = {l: float(forma_lambda(info_lambda["elegida"], d, info_lambda["parametros"], lam_min)) for l, d in dist.items()}
        else:
            info_lambda = {"elegida": "constante", "parametros": []}
            lam_g = {l: 1.0 for l in dist}
        lam_g[ref] = 1.0
        lam_liga = {c: dict(lam_g) for c in metricas}
        info_lambda["lambda_hat"] = lt.drop(columns=[c for c in ("resid_x",) if c in lt]).to_dict("records")
        if progreso:
            progreso(f"  iteración {it + 1}/{n_ext}: forma λ(d) = {info_lambda['elegida']} {np.round(info_lambda['parametros'], 3).tolist()}"
                     f" · λ FEB3 {lam_g.get('feb3', np.nan):.3f} · d FEB3 {dist.get('feb3', np.nan):.2f}")
        # convergencia de la alternancia desfases ↔ λ: cambio máximo de λ entre ligas < tolerancia
        cambio = max(abs(lam_g[l] - lam_prev.get(l, 1.0)) for l in lam_g)
        lam_prev = dict(lam_g)
        info_lambda["iteraciones_externas"] = it + 1
        if cambio < float(cfg.get("tolerancia_externa", 0.005)):
            break
    # última pasada con las λ finales
    for col in metricas:
        resultados[col] = ajustar_metrica(col, filas[col], params["metricas"][col]["enlace"], cfg, lam_liga[col], ipw_arr,
                                          escalon_de, ref, mapeo=mapeo)
    return {"resultados": resultados, "lambda": info_lambda, "lam_liga": lam_g, "distancia": dist, "ipw": info_ipw,
            "hasta_anio": hasta_anio, "filas": filas, "zs": zs, "cfg": cfg, "ref": ref}


# =============================================================================================== traducción
def theta(ajuste: dict, col: str, liga: str, nodo: str, z_obs, v_obs):
    """Capacidad amortiguada en la vara de referencia (media, varianza) de filas de un nodo."""
    r = ajuste["resultados"][col]
    est = r["estado"]
    e = est.enlace
    psi = e["psi"][liga]
    z_est = np.asarray(z_obs, float) / (1 + np.asarray(v_obs, float) + psi)
    v_est = (np.asarray(v_obs, float) + psi) / (1 + np.asarray(v_obs, float) + psi)
    if nodo in est.idx:
        dl, dv = est.delta[est.idx[nodo]], est.delta_var[est.idx[nodo]]
    else:  # competición-temporada sin filas de ajuste (p. ej. futura): nivel medio de la liga
        k = [i for i, n in enumerate(est.nodos) if n.startswith(liga + ":")]
        dl = float(np.mean(est.delta[k])) if k else e["m"].get(liga, np.nan)
        dv = float(np.mean(est.delta_var[k])) + float(ajuste["resultados"][col]["contraccion"]["tau2"]) if k else np.nan
    F = est.F.get(liga) or Mapeo()
    lam = est.lam.get(liga, 1.0) if liga != ajuste["ref"] else 1.0
    s, s_se = e["s"][liga], e.get("s_se", {}).get(liga, 0.0)
    th = dl + lam * F(s * z_est)
    var = dv + (lam * s * F.derivada(s * z_est)) ** 2 * v_est + (lam * F(s * z_est) / max(s, 1e-6)) ** 2 * s_se ** 2
    return th, var


def traducir(tabla: pd.DataFrame, params: dict, ajuste: dict, temporada_ref: str = "2025-26") -> pd.DataFrame:
    """Columnas amortiguadas por fila jugador-liga-temporada: <m>_am (valor EuroLeague), _am_lo/_am_hi (80 %),
    _am_pct (percentil EuroLeague), _am_a y _am_sd (capacidad en DT EuroLeague)."""
    from .modelo import _entorno
    out = tabla[["persona_id", "liga", "temporada", "player_id"]].copy()
    nuevas = {}
    zs = z_por_metrica(tabla, params) if ajuste["hasta_anio"] is not None else ajuste["zs"]
    for col in ajuste["resultados"]:
        m = CATALOGO[col]
        p1 = params["metricas"][col]["suerte"]
        z = zs[col].reindex(tabla.index)
        th = np.full(len(tabla), np.nan)
        va = np.full(len(tabla), np.nan)
        e = params["metricas"][col]["enlace"]
        nodo = (tabla["liga"] + ":" + tabla["temporada"]).to_numpy()
        for n in np.unique(nodo):
            liga = n.split(":")[0]
            if liga not in e["m"]:
                continue
            s = (nodo == n) & z["z_obs"].notna().to_numpy()
            if s.any():
                th[s], va[s] = theta(ajuste, col, liga, n, z["z_obs"].to_numpy()[s], z["v_obs"].to_numpy()[s])
        mu = np.array([_entorno(p1, ajuste["ref"], temporada_ref, g)[0] if isinstance(g, str) else np.nan for g in tabla["pos3"]])
        tau = np.array([_entorno(p1, ajuste["ref"], temporada_ref, g)[1] if isinstance(g, str) else np.nan for g in tabla["pos3"]])
        sd = np.sqrt(va)
        nuevas[f"{col}_am"] = destransformar(mu + tau * th, m.transf)
        nuevas[f"{col}_am_lo"] = destransformar(mu + tau * (th - Z80 * sd), m.transf)
        nuevas[f"{col}_am_hi"] = destransformar(mu + tau * (th + Z80 * sd), m.transf)
        nuevas[f"{col}_am_pct"] = 100 * norm.cdf(th)
        nuevas[f"{col}_am_a"] = th
        nuevas[f"{col}_am_sd"] = sd
    return pd.concat([out.reset_index(drop=True), pd.DataFrame(nuevas)], axis=1)


# =============================================================================================== tablas
def tabla_offsets(ajuste: dict, params: dict, ajuste_sin_ipw: dict | None = None) -> pd.DataFrame:
    """league_offsets: competición × temporada × métrica (media, sd, intervalo 90 %, puentes, camino)."""
    filas = []
    for col, r in ajuste["resultados"].items():
        est = r["estado"]
        e = params["metricas"][col]["enlace"]
        bruto, cov_b = r["bruto"]
        ng = r["nodos_g"]
        sin = ajuste_sin_ipw["resultados"].get(col) if ajuste_sin_ipw else None
        for n in est.nodos:
            liga, temp = n.split(":")
            k = 0 if n in r["ref_nodos"] else ng.index(n)
            mu, v = est.delta[est.idx[n]], est.delta_var[est.idx[n]]
            sd = float(np.sqrt(v)) if np.isfinite(v) else np.nan
            fila = {"competicion": liga, "temporada": temp, "metrica": col, "media": mu, "sd": sd,
                    "lo90": mu - Z90 * sd, "hi90": mu + Z90 * sd, "n_puentes": r["n_puentes"].get(n, 0),
                    "camino": r["caminos"].get(n, ""),
                    "escalon": next((e_ for e_, ls in ajuste["cfg"].get("escalones", {}).items() if liga in ls), ""),
                    "media_encadenada": bruto[k], "sd_encadenada": float(np.sqrt(cov_b[k, k])) if np.isfinite(cov_b[k, k]) else np.nan,
                    "media_lineal_A": e["m"].get(liga, np.nan), "sd_lineal_A": e.get("m_se", {}).get(liga, np.nan),
                    "s_A": e["s"].get(liga, np.nan), "lambda": est.lam.get(liga, 1.0) if liga != ajuste["ref"] else 1.0,
                    "distancia_d": ajuste["distancia"].get(liga, 0.0),
                    "forma_no_lineal": int(liga in est.F and not est.F[liga].es_lineal),
                    "mu_escalon": r["contraccion"]["mu_escalon"].get(
                        next((e_ for e_, ls in ajuste["cfg"].get("escalones", {}).items() if liga in ls), ""), np.nan),
                    "tau_escalon": float(np.sqrt(r["contraccion"]["tau2"]))}
            if sin is not None and n in sin["estado"].idx:
                fila["media_sin_ipw"] = sin["estado"].delta[sin["estado"].idx[n]]
            filas.append(fila)
    return pd.DataFrame(filas)


def diagnostico(tabla: pd.DataFrame, params: dict, min_minutos: float = 150) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Esquema lineal (A): desfase m por liga y métrica, error, anchura del intervalo del 90 % y puentes; y puentes
    (personas) por pareja de ligas, en la misma temporada o en temporadas consecutivas."""
    filas = []
    for col, p in params["metricas"].items():
        e = p["enlace"]
        for liga in e["ligas"]:
            se = e.get("m_se", {}).get(liga, np.nan)
            filas.append({"competicion": liga, "metrica": col, "offset_m": e["m"][liga], "sd": se,
                          "ancho_ic90": 2 * Z90 * se if se == se else np.nan, "s": e["s"][liga],
                          "s_sd": e.get("s_se", {}).get(liga, np.nan), "psi": e["psi"][liga],
                          "unidades_puente": e["puentes_por_liga"].get(liga, 0),
                          "sigma2": p["suerte"]["sigma2"].get(liga, p["suerte"]["sigma2"].get("todas"))})
    d = pd.DataFrame(filas)
    g = tabla[tabla["min"] >= min_minutos][["persona_id", "liga", "anio"]].drop_duplicates()
    a = g.merge(g, on="persona_id", suffixes=("_a", "_b"))
    a = a[(a["liga_a"] < a["liga_b"]) & ((a["anio_a"] - a["anio_b"]).abs() <= 1)]
    a["tipo"] = np.where(a["anio_a"] == a["anio_b"], "misma", "consecutiva")
    pares = a.groupby(["liga_a", "liga_b"]).agg(personas=("persona_id", "nunique")).reset_index()
    for tipo in ("misma", "consecutiva"):
        pares = pares.merge(a[a["tipo"] == tipo].groupby(["liga_a", "liga_b"])["persona_id"].nunique()
                            .rename(f"personas_{tipo}").reset_index(), on=["liga_a", "liga_b"], how="left")
    return d, pares.fillna(0)


def resumen_ligas(d: pd.DataFrame, pares: pd.DataFrame, metricas_nivel: list[str]) -> pd.DataFrame:
    """Una fila por liga: desfase medio (con signo) y anchura media del IC90 en las métricas de nivel; puentes."""
    x = d[d["metrica"].isin(metricas_nivel)].copy()
    x["signo"] = x["metrica"].map(lambda c: CATALOGO[c].sentido)
    x["off"] = x["offset_m"] * x["signo"]
    r = x.groupby("competicion").agg(offset_nivel=("off", "mean"), ancho_ic90_nivel=("ancho_ic90", "mean"),
                                     sd_nivel=("sd", "mean")).reset_index()
    pp = d[d["metrica"] == "pts_p100"].set_index("competicion")[["offset_m", "ancho_ic90", "unidades_puente"]]
    r = r.join(pp.add_suffix("_pts_p100"), on="competicion")
    tot = pd.concat([pares.rename(columns={"liga_a": "c", "liga_b": "o"}), pares.rename(columns={"liga_b": "c", "liga_a": "o"})])
    r["puentes_total"] = r["competicion"].map(tot.groupby("c")["personas"].sum())
    r["puentes_con_euroleague"] = r["competicion"].map(tot[tot["o"] == "euroleague"].set_index("c")["personas"])
    return r


# =============================================================================================== validación
def predecir_cambios(tabla: pd.DataFrame, anio: int, params: dict, ajuste: dict) -> pd.DataFrame:
    """Mismo examen que bbmodel.validacion: casos t → t+1 (≥300 min en ambas), predicción amortiguada."""
    from . import enlace as E, modelo, validacion
    from .metricas import EXPOSICIONES
    c = validacion.casos(tabla, anio)
    filas = []
    temp_t = f"{anio}-{str(anio + 1)[-2:]}"
    for col in ajuste["resultados"]:
        p = params["metricas"][col]
        e, s1, m = p["enlace"], p["suerte"], CATALOGO[col]
        z = params["_z"][col]
        r = ajuste["resultados"][col]
        est = r["estado"]
        for _, x in c.iterrows():
            lo, ld, pos = x["liga_o"], x["liga_d"], x["pos3_o"]
            y_real = x[f"{col}_d"]
            if not isinstance(pos, str) or lo not in e["m"] or ld not in e["m"] or not np.isfinite(y_real):
                continue
            zo, vo = z.loc[x["index_o"], ["z_obs", "v_obs"]]
            if not np.isfinite(zo):
                continue
            mu_d, tau_d = modelo._entorno(s1, ld, temp_t, pos)
            if not np.isfinite(mu_d):
                continue
            th, vth = theta(ajuste, col, lo, f"{lo}:{x['temporada_o']}", np.array([zo]), np.array([vo]))
            edad = x["anio_o"] - x["anio_nac_o"]
            th1 = th[0] + e["deriva"].get(E.tramo_edad(edad), 0.0)
            v1 = vth[0] + e["eta2"]
            # destino: nivel de su liga en la temporada t (la de t+1 aún no se conoce)
            nd = f"{ld}:{temp_t}"
            if ld == ajuste["ref"]:
                dl_d, dv_d, lam_d, F_d = 0.0, 0.0, 1.0, Mapeo()
            else:
                if nd in est.idx:
                    dl_d, dv_d = est.delta[est.idx[nd]], est.delta_var[est.idx[nd]]
                else:
                    k = [i for i, n in enumerate(est.nodos) if n.startswith(ld + ":")]
                    if not k:
                        continue
                    dl_d, dv_d = float(np.mean(est.delta[k])), float(np.mean(est.delta_var[k]))
                lam_d = est.lam.get(ld, 1.0)
                F_d = est.F.get(ld) or Mapeo()
            s_d = e["s"][ld]
            u = (th1 - dl_d) / lam_d
            xd = F_d.inversa(np.array([u]))[0]
            if not np.isfinite(xd):
                continue
            zd = xd / s_d
            der = lam_d * s_d * float(F_d.derivada(np.array([xd]))[0])
            vzd = (v1 + dv_d) / max(der, 1e-3) ** 2
            n_d = x.get(f"{EXPOSICIONES[m.exposicion]}_d", np.nan)
            ruido = s1["sigma2"].get(ld, s1["sigma2"].get("todas", np.nan)) / (n_d * tau_d ** 2) \
                if np.isfinite(n_d) and n_d > 0 else 0
            sd = np.sqrt(vzd + e["psi"][ld] + ruido)
            pred = destransformar(mu_d + tau_d * zd, m.transf)
            y_t = float(transformar(y_real, m.transf))
            filas.append({"metrica": col, "anio": anio, "persona_id": x["persona_id"], "nombre": x["nombre_o"],
                          "liga_o": lo, "liga_d": ld, "real": y_real, "amortiguado": float(pred),
                          "dentro_80_am": bool(abs(y_t - (mu_d + tau_d * zd)) <= Z80 * tau_d * sd)})
    return pd.DataFrame(filas)


def dejar_fuera_liga(ajuste: dict, params: dict, cfg: dict, ligas: list[str] | None = None,
                     metricas: list[str] | None = None) -> pd.DataFrame:
    """Para cada liga: se quitan TODAS sus aristas y su nivel sale sólo de la previa del escalón (contracción) frente
    al esquema sin jerarquía (sin puentes, el A la deja en el nivel de la referencia: m = 0). Se compara con el nivel
    estimado con todos los datos: error y cobertura del IC90."""
    filas = []
    ref = ajuste["ref"]
    escalon_de = {l: e for e, ls in cfg.get("escalones", {}).items() for l in ls}
    cc = cfg.get("contraccion", {})
    for col in (metricas or list(ajuste["resultados"])):
        r = ajuste["resultados"][col]
        ng, ar = r["nodos_g"], r["aristas"]
        if not len(ar):
            continue
        est = r["estado"]
        for liga in (ligas or sorted({n.split(":")[0] for n in ng[1:]})):
            keep = ar[~ar["nodo_x"].str.startswith(liga + ":") & ~ar["nodo_y"].str.startswith(liga + ":")]
            idx = {n: i for i, n in enumerate(ng)}
            aristas = [(idx[a.nodo_x], idx[a.nodo_y], a.d, a.var) for a in keep.itertuples()]
            escalon = [None] + [escalon_de.get(n.split(":")[0]) for n in ng[1:]]
            ch = contraccion_jerarquica(len(ng), aristas, 0, escalon, float(cc.get("tau2_inicial", 0.05)),
                                        float(cc.get("tau2_minimo", 0.0025)), float(cc.get("hiperprevia_sd", 2.0)),
                                        int(cc.get("iteraciones_em", 200)))
            for n in ng[1:]:
                if not n.startswith(liga + ":"):
                    continue
                k = idx[n]
                verdad = est.delta[est.idx[n]]
                pred, sd = ch["media"][k], float(np.sqrt(ch["cov"][k, k]))
                otros = [l for l, e in escalon_de.items() if e == escalon_de.get(liga) and l != liga]
                filas.append({"metrica": col, "liga": liga, "nodo": n, "escalon": escalon_de.get(liga),
                              "escalon_con_otras_ligas": bool(otros), "nivel_todos": verdad,
                              "pred_jerarquica": pred, "sd_jerarquica": sd,
                              "error_jerarquica": abs(pred - verdad), "dentro_90": abs(pred - verdad) <= Z90 * sd,
                              "pred_sin_jerarquia": 0.0, "error_sin_jerarquia": abs(verdad)})
    return pd.DataFrame(filas)


# =============================================================================================== principal
def _guardar_json(obj, ruta: Path):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)),
                    encoding="utf-8")


def cargar_parametros_A(ruta: Path | None = None) -> dict:
    ruta = ruta or (RAIZ / "data" / "modelos" / "algoritmo_A" / "parametros.json")
    p = json.loads(Path(ruta).read_text(encoding="utf-8"))
    return {"metricas": p["metricas"], "info": p.get("info", {})}


def ejemplos_puentes(tabla: pd.DataFrame, params: dict, ajuste: dict, trad: pd.DataFrame, n_por_par: int = 3,
                     metrica: str = "pts_p100") -> pd.DataFrame:
    """Jugadores puente REALES (cambian de liga de t a t+1, ≥ 300 min en ambas) con su traducción lineal (A) y
    amortiguada y lo que hicieron después. Pares FEB → superior y hacia la EuroLeague."""
    from . import validacion
    from .modelo import traducir as traducir_A
    filas = []
    ta = traducir_A(tabla, {"metricas": {metrica: params["metricas"][metrica]}, "_z": ajuste["zs"]}, "2025-26")
    clave = ["liga", "temporada", "player_id"]
    ta = ta.set_index(clave)
    tr = trad.set_index(clave)
    pares = [("feb3", "feb2"), ("feb2", "feb1"), ("feb1", "acb"), ("feb1", "eurocup"), ("feb2", "acb"), ("acb", "euroleague"),
             ("eurocup", "euroleague"), ("gleague", "euroleague"), ("bcl", "euroleague")]
    for anio in sorted(tabla["anio"].unique())[:-1]:
        try:
            c = validacion.casos(tabla, int(anio))
        except KeyError:      # temporada siguiente sin nadie con 300 minutos (2026-27 en curso)
            continue
        for lo, ld in pares:
            s = c[(c["liga_o"] == lo) & (c["liga_d"] == ld)].sort_values("min_o", ascending=False).head(n_por_par)
            for _, x in s.iterrows():
                ko = (lo, x["temporada_o"], x["player_id_o"])
                kd = (ld, x["temporada_d"], x["player_id_d"])
                if ko not in ta.index or kd not in ta.index:
                    continue
                filas.append({"nombre": x["nombre_o"], "origen": f"{lo} {x['temporada_o']}", "destino": f"{ld} {x['temporada_d']}",
                              "min_origen": x["min_o"], "min_destino": x["min_d"], "metrica": metrica,
                              "valor_origen": x[f"{metrica}_o"], "valor_destino": x[f"{metrica}_d"],
                              "a_origen_lineal": ta.loc[ko, f"{metrica}_a"], "a_origen_amortiguado": tr.loc[ko, f"{metrica}_am_a"],
                              "a_destino_lineal": ta.loc[kd, f"{metrica}_a"], "a_destino_amortiguado": tr.loc[kd, f"{metrica}_am_a"],
                              "el_origen_lineal": ta.loc[ko, f"{metrica}_el"], "el_origen_amortiguado": tr.loc[ko, f"{metrica}_am"],
                              "el_destino_lineal": ta.loc[kd, f"{metrica}_el"], "el_destino_amortiguado": tr.loc[kd, f"{metrica}_am"]})
    d = pd.DataFrame(filas)
    if len(d):
        d["error_lineal"] = (d["a_origen_lineal"] - d["a_destino_lineal"]).abs()
        d["error_amortiguado"] = (d["a_origen_amortiguado"] - d["a_destino_amortiguado"]).abs()
    return d


def main(validar: bool = False, diagnostico_params: str | None = None, salida: Path = DIR_SALIDA) -> None:
    from . import modelo
    t0 = time.time()
    cfg = config()
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    tabla, info = modelo.preparar()
    mn = cfg.get("transferibilidad", {}).get("metricas_nivel", [])
    print(f"tabla: {info['registros']} registros, {info['personas']} personas · crosswalk {info.get('crosswalk')}", flush=True)
    if diagnostico_params:
        params = cargar_parametros_A(Path(diagnostico_params))
        d, pares = diagnostico(tabla, params)
        r = resumen_ligas(d, pares, mn)
        d.round(5).to_csv(salida / "diagnostico_antes.csv", index=False)
        pares.to_csv(salida / "diagnostico_antes_puentes.csv", index=False)
        r.round(4).to_csv(salida / "diagnostico_antes_ligas.csv", index=False)
        print(r.round(3).to_string(index=False))
        return
    from bbfit.registro import experimento
    if validar:
        _validar(tabla, cfg, salida)
        print(f"validación en {time.time() - t0:.0f} s")
        return
    params = cargar_parametros_A()
    with experimento("normalizacion_amortiguada", "ajuste_completo", params={"config": json.dumps(cfg)[:480]}) as run:
        aj = ajustar(tabla, params, cfg)
        aj_sin = ajustar(tabla, params, cfg, ipw=False, progreso=None)
        off = tabla_offsets(aj, params, aj_sin)
        off.round(5).to_csv(salida / "league_offsets.csv", index=False)
        trad = traducir(tabla, params, aj)
        (salida / "traducciones").mkdir(exist_ok=True)
        for temp, g in trad.groupby("temporada"):
            g.round(4).to_csv(salida / "traducciones" / f"{temp}.csv", index=False)
        ej = ejemplos_puentes(tabla, params, aj, trad)
        ej.round(4).to_csv(salida / "ejemplos_puentes.csv", index=False)
        lam = {k: v for k, v in aj["lambda"].items() if k != "lambda_hat"}
        lh = pd.DataFrame(aj["lambda"]["lambda_hat"])
        lh.round(5).to_csv(salida / "lambda_por_liga.csv", index=False)
        mapeos = {col: {l: F.a_dict() for l, F in r["estado"].F.items() if not F.es_lineal}
                  for col, r in aj["resultados"].items()}
        nivel = off[off["metrica"].isin(mn)].copy()
        nivel["s"] = nivel["metrica"].map(lambda c: CATALOGO[c].sentido)
        res_liga = (nivel.assign(m=nivel["media"] * nivel["s"], ms=nivel["media_sin_ipw"] * nivel["s"],
                                 ml=nivel["media_lineal_A"] * nivel["s"], me=nivel["media_encadenada"] * nivel["s"])
                    .groupby("competicion")[["m", "ms", "ml", "me", "sd"]].mean())
        resumen = {"lambda": lam, "lambda_por_liga": aj["lam_liga"], "distancia": aj["distancia"], "ipw": aj["ipw"],
                   "tau_escalon": {c: float(np.sqrt(r["contraccion"]["tau2"])) for c, r in aj["resultados"].items()},
                   "mu_escalon": {c: r["contraccion"]["mu_escalon"] for c, r in aj["resultados"].items()},
                   "nivel_medio_liga": res_liga.round(4).to_dict("index"),
                   "efecto_ipw_medio_abs": float((off["media"] - off["media_sin_ipw"]).abs().mean()),
                   "mapeos_no_lineales": mapeos, "info_identidad": info.get("crosswalk"),
                   "tiempo_s": round(time.time() - t0)}
        _guardar_json(resumen, salida / "resumen.json")
        run.metricas({"efecto_ipw_medio_abs": resumen["efecto_ipw_medio_abs"],
                      "lambda_feb3": aj["lam_liga"].get("feb3"), "lambda_acb": aj["lam_liga"].get("acb")})
        run.artefacto(salida / "league_offsets.csv")
        run.artefacto(salida / "resumen.json")
    print(res_liga.round(3).to_string())
    print(f"forma λ(d): {aj['lambda'].get('elegida')} {aj['lambda'].get('parametros')} · {time.time() - t0:.0f} s")


def _validar(tabla: pd.DataFrame, cfg: dict, salida: Path) -> None:
    """Examen temporal (A lineal frente a amortiguado, mismos casos) y dejar fuera una liga. Reanudable: los
    parámetros del A de cada corte se guardan en experimentos/cache_normalizacion/."""
    import pickle
    from bbfit.registro import experimento
    from . import modelo, validacion
    vc = cfg.get("validacion", {})
    DIR_CACHE.mkdir(parents=True, exist_ok=True)
    res = []
    with experimento("normalizacion_amortiguada", "validacion", params={"anios": vc.get("anios")}) as run:
        for anio in vc.get("anios", [2023, 2024]):
            cache = DIR_CACHE / f"A_hasta_{anio}.pkl"
            if cache.exists():
                p = pickle.loads(cache.read_bytes())
            else:
                p = modelo.ajustar(tabla, hasta_anio=anio, n_boot=int(vc.get("bootstrap", 10)), progreso=None)
                cache.write_bytes(pickle.dumps(p))
            print(f"  A ≤ {anio} listo", flush=True)
            ra = validacion.evaluar(tabla, anio, p)
            aj = ajustar(tabla[tabla["anio"] <= anio], p, cfg, hasta_anio=None, progreso=print)
            aj["hasta_anio"] = anio
            rb = predecir_cambios(tabla, anio, p, aj)
            m = ra.merge(rb[["metrica", "anio", "persona_id", "amortiguado", "dentro_80_am"]],
                         on=["metrica", "anio", "persona_id"], how="inner")
            res.append(m)
            print(f"  corte {anio}: {len(m)} predicciones", flush=True)
            if anio == max(vc.get("anios", [2023, 2024])):
                lolo = dejar_fuera_liga(aj, p, cfg)
                lolo.round(5).to_csv(salida / "validacion_lolo.csv", index=False)
        r = pd.concat(res)
        r.round(4).to_csv(salida / "validacion_casos.csv.gz", index=False)
        out = []
        for col, g in r.groupby("metrica"):
            ea, em = (g["algoritmo_A"] - g["real"]).abs(), (g["amortiguado"] - g["real"]).abs()
            ep = (g["mismo_percentil"] - g["real"]).abs()
            out.append({"metrica": col, "casos": len(g), "mae_lineal_A": ea.mean(), "mae_amortiguado": em.mean(),
                        "mae_mismo_percentil": ep.mean(), "mejora_mae_%": 100 * (1 - em.mean() / ea.mean()),
                        "cobertura80_lineal": g["dentro_80"].mean(), "cobertura80_amortiguado": g["dentro_80_am"].mean()})
            for grupo, s in (("a_euroleague", g["liga_d"] == "euroleague"), ("desde_feb", g["liga_o"].str.startswith("feb")),
                             ("hacia_feb", g["liga_d"].str.startswith("feb"))):
                out[-1][f"casos_{grupo}"] = int(s.sum())
                out[-1][f"mae_lineal_{grupo}"] = ea[s].mean() if s.any() else np.nan
                out[-1][f"mae_amortiguado_{grupo}"] = em[s].mean() if s.any() else np.nan
        resumen = pd.DataFrame(out)
        resumen.round(4).to_csv(salida / "validacion.csv", index=False)
        lolo = pd.read_csv(salida / "validacion_lolo.csv")
        run.metricas({"mae_rel_medio": float((resumen["mae_amortiguado"] / resumen["mae_lineal_A"]).mean()),
                      "cob80_lineal": float(resumen["cobertura80_lineal"].mean()),
                      "cob80_amortiguado": float(resumen["cobertura80_amortiguado"].mean()),
                      "lolo_error_jerarquica": float(lolo["error_jerarquica"].mean()),
                      "lolo_error_sin_jerarquia": float(lolo["error_sin_jerarquia"].mean()),
                      "lolo_cobertura90": float(lolo["dentro_90"].mean())})
        run.artefacto(salida / "validacion.csv")
    print(resumen[["metrica", "casos", "mae_lineal_A", "mae_amortiguado", "cobertura80_lineal", "cobertura80_amortiguado"]]
          .round(3).to_string(index=False))
