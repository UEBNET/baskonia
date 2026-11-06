"""Prueba de orden de las sinergias por MODELO MIXTO (máxima verosimilitud restringida, REML) · orden del CEO del
06-11-2026. Sustituye, como estimador principal, a la covarianza entre tercios del §2.2 (orden_sinergias.py), que mezcla
dos sesgos de signo contrario (el error de β común a los tercios y la atenuación de la medida «propia»).

Modelo, por liga-temporada ℓt (tramos del contrato v4.0, 2020-21 a 2025-26):

    y_s = F_s·f + Σ_{i∈A_s} β_i − Σ_{i∈B_s} β_i + Σ_{u⊂A_s} u − Σ_{u⊂B_s} u + ε_s,    ε_s ~ N(0, σ²/n_s)
    β_i ~ N(m_i, τ²)           (a) m_i = 0  ·  (b) m_i = g(x̃_i), el prior del producto F1 (β de F1 como modelo aditivo)
    u ~ N(0, σ_o²)             un efecto propio por pareja (o = 2), trío (o = 3) y quinteto (o = 5) del mismo equipo

Todo efecto entra a la vez: jugadores y unidades se estiman conjuntamente, así que la parte que el jugador explica no se
«resta» antes (sin atenuación) y no hay tercios (sin error de β común). Lo que se estima es σ_o, la DT del efecto propio
VERDADERO de una unidad de orden o, en pts/100.

REML con σ² perfilado. Con C = AᵀWA + diag(0_fijos, 1/γ_k) (A = [F | X | Z_2 | Z_3 | Z_5], γ_k = σ_k²/σ²):
    −2ℓ_R = (n − p)·log σ̂² + log|C| + Σ_k q_k·log γ_k + (n − p),     σ̂² = (yᵀWy − b̂ᵀAᵀWy)/(n − p),  b̂ = C⁻¹AᵀWy
(constantes fuera). Factorización de Cholesky densa (BLAS multihilo); en este contenedor no hay CHOLMOD y la LU dispersa
era 6–15 veces más lenta.

Estimación agregada: σ_o común a todas las ℓt del segmento; τ (varianza de jugadores) propio de cada ℓt y perfilado.
    Etapa 2: perfil de −2ℓ en una rejilla de σ_2 (τ re-perfilado en cada punto) → suma sobre ℓt → σ̂_2.
    Etapa 3: perfil en σ_3 con σ_2 = σ̂_2 (agregado) y τ = τ̂_ℓt(σ̂_2) fijos → σ̂_3.
    Etapa 5: perfil en σ_5 con σ_2, σ_3 y τ fijos → σ̂_5.
Intervalos: (i) de verosimilitud perfilada (Δ(−2ℓ) = 1,642 para el 80 %, 3,841 para el 95 %); (ii) bootstrap de
ligas-temporada (B del YAML) sobre las curvas, robusto a la mala especificación de la verosimilitud gaussiana. Contraste
σ_o = 0: razón de verosimilitudes con la mezcla ½χ²₀ + ½χ²₁ (parámetro en la frontera).
Fiabilidad de una unidad con n posesiones: σ̂_o² / (σ̂_o² + σ̂²/n).

Límites declarados: la etapa 5 (quintetos) sólo se calcula en el segmento élite (`segmento_por_etapa`; coste y decisión 8);
σ_o común entre ligas; en las etapas 3 y 5 τ y los órdenes inferiores quedan fijos (perfil
condicional); las ℓt cuyo sistema no cabe en memoria densa (q > máximo del YAML) se omiten en esa etapa y se listan.

Salidas: data/modelos/v4_1/sinergia_mixta/{curvas_<v>.json, resumen.json}; caché por ℓt en experimentos/v4_1/sinergia_mixta/.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.linalg as sla
import scipy.sparse as sp
from scipy.interpolate import PchipInterpolator
from scipy.optimize import minimize_scalar
from scipy.stats import chi2

from . import config as CE
from . import orden_sinergias as OS

NOMBRE = {2: "pareja", 3: "trio", 5: "quinteto"}


# =============================================================================================== sistema de una liga-temporada
class Sistema:
    """AᵀWA denso, AᵀWy e yᵀWy de una liga-temporada, con los bloques [fijos | jugadores | parejas | tríos | quintetos]."""

    def __init__(self, lt: OS.LT, ordenes: tuple[int, ...], g: np.ndarray | None = None):
        n = lt.n
        F = lt.F[:, lt.F.std(0) > 0] if lt.F.shape[1] > 1 else lt.F
        F = np.c_[np.ones(n), F[:, 1:]] if F.shape[1] else np.ones((n, 1))
        F = F[:, [0] + [j for j in range(1, F.shape[1]) if F[:, j].std() > 0]]
        Xp = OS.diseno(lt)[:, :lt.nP]
        y = lt.y - (Xp @ g if g is not None else 0.0)
        bloques = [sp.csr_matrix(F), Xp]
        self.nombres = ["fijos", "jugadores"]
        for o in ordenes:
            rows, team, key, sgn, nn = OS._diseno_unidades(lt, np.ones(n, bool), o)
            cod = pd.DataFrame({"t": team, "k": key}).groupby(["t", "k"], sort=False).ngroup().to_numpy()
            bloques.append(sp.csr_matrix((sgn, (rows, cod)), shape=(n, int(cod.max()) + 1)))
            self.nombres.append(NOMBRE[o])
        self.dims = [b.shape[1] for b in bloques]
        self.ini = np.r_[0, np.cumsum(self.dims)]
        self.p = self.dims[0]
        self.n = n
        self.w = lt.w
        self.y = y
        self.A = sp.hstack(bloques).tocsr()
        self.G = None
        self.r = np.asarray(self.A.T @ (lt.w * y)).ravel()
        self.yWy = float(np.sum(lt.w * y * y))

    def q_total(self, hasta: str) -> int:
        return int(self.ini[self.nombres.index(hasta) + 1])

    def preparar(self, hasta: str):
        """Calcula AᵀWA denso hasta el bloque `hasta` (incluido)."""
        m = self.q_total(hasta)
        if self.G is None or self.G.shape[0] < m:
            Am = self.A[:, :m]
            self.G = np.asarray((Am.T @ Am.multiply(self.w[:, None])).todense())

    def m2ll(self, gammas: dict[str, float]) -> tuple[float, float]:
        """−2ℓ_R perfilado en σ² y σ̂². `gammas`: {bloque: γ = σ_k²/σ²} para los bloques aleatorios incluidos (en orden;
        un γ = 0 excluye el bloque, que es el límite exacto del modelo sin él)."""
        incl = [0]
        diag = [np.zeros(self.p)]
        logg = 0.0
        for k, nombre in enumerate(self.nombres[1:], 1):
            gk = gammas.get(nombre)
            if not gk:
                continue
            incl.append(k)
            diag.append(np.full(self.dims[k], 1.0 / gk))
            logg += self.dims[k] * math.log(gk)
        idx = np.concatenate([np.arange(self.ini[k], self.ini[k + 1]) for k in incl])
        m = len(idx)
        C = self.G[:m, :m].copy() if idx[-1] == m - 1 else self.G[np.ix_(idx, idx)]   # bloques contiguos: copia rápida
        C[np.diag_indices_from(C)] += np.concatenate(diag)
        c, low = sla.cho_factor(C, lower=True, overwrite_a=True, check_finite=False)
        logdet = 2.0 * float(np.sum(np.log(np.diag(c))))
        b = sla.cho_solve((c, low), self.r[idx], check_finite=False)
        quad = self.yWy - float(b @ self.r[idx])
        s2 = quad / (self.n - self.p)
        return (self.n - self.p) * math.log(s2) + logdet + logg + (self.n - self.p), s2


def _perfil_tau(S: Sistema, fijos: dict, s0: float, x0: float, paso: float = 0.2) -> tuple[float, float]:
    """Mínimo de −2ℓ en x = log τ con los demás γ fijos: horquilla de 3 puntos alrededor de x0 (se desplaza hasta que el
    central es el menor) y un paso parabólico. Devuelve (−2ℓ mínimo, log τ̂)."""
    cache: dict[float, float] = {}

    def F(x: float) -> float:
        x = round(x, 5)
        if x not in cache:
            cache[x] = S.m2ll({**fijos, "jugadores": math.exp(2 * x) / s0 ** 2})[0]
        return cache[x]

    a, b, c = x0 - paso, x0, x0 + paso
    for _ in range(12):
        fa, fb, fc = F(a), F(b), F(c)
        if fb <= fa and fb <= fc:
            break
        a, b, c = (a - paso, a, b) if fa < fc else (b, c, c + paso)
    fa, fb, fc = F(a), F(b), F(c)
    den = (b - a) * (fb - fc) - (b - c) * (fb - fa)
    if den != 0:
        v = b - 0.5 * ((b - a) ** 2 * (fb - fc) - (b - c) ** 2 * (fb - fa)) / den
        if a < v < c:
            F(v)
    x = min(cache, key=cache.get)
    return float(cache[x]), float(x)


# =============================================================================================== una liga-temporada
def curvas_lt(lt: OS.LT, version: str, etapa: int, cfg_m: dict, g: np.ndarray | None, condicion: dict,
              q_max: dict) -> dict:
    """Curva de perfil de −2ℓ en la rejilla de σ_etapa para una liga-temporada.
    `condicion`: σ de los órdenes inferiores ya estimados (agregados) para las etapas 3 y 5."""
    ordenes = tuple(o for o in (2, 3, 5) if o <= etapa)
    S = Sistema(lt, ordenes, g=g if version == "b" else None)
    nombre = NOMBRE[etapa]
    info = {"liga": lt.liga, "temporada": lt.temporada, "n": lt.n, "dims": dict(zip(S.nombres, S.dims)),
            "q": S.q_total(nombre)}
    if info["q"] > int(q_max[str(etapa)]):
        return {**info, "omitida": f"q = {info['q']} > {q_max[str(etapa)]} (memoria densa)"}
    t0 = time.time()
    S.preparar(nombre)
    # escala σ² y τ̂ del modelo sólo con jugadores (dos pasadas: σ inicial bruto, luego el σ̂ del ajuste)
    s0 = math.sqrt(S.yWy / S.n)
    for _ in range(2):
        res = minimize_scalar(lambda x: S.m2ll({"jugadores": math.exp(2 * x) / s0 ** 2})[0],
                              bounds=(math.log(0.1), math.log(30.0)), method="bounded", options={"xatol": 1e-3})
        s0 = math.sqrt(S.m2ll({"jugadores": math.exp(2 * res.x) / s0 ** 2})[1])
    log_tau0, m2ll_jug = float(res.x), float(res.fun)
    info.update({"sigma0": s0, "tau_jugadores_solo": math.exp(log_tau0), "m2ll_jugadores_solo": m2ll_jug})
    rejilla = [float(x) for x in cfg_m["rejilla"][str(etapa)]]
    fijos = {}
    if etapa >= 3:
        fijos["pareja"] = condicion["pareja"] ** 2 / s0 ** 2
    if etapa >= 5:
        fijos["trio"] = condicion["trio"] ** 2 / s0 ** 2
    curva, taus = [], []
    if etapa == 2:
        lt0 = log_tau0
        for sd in rejilla:
            gm = {**fijos, nombre: sd ** 2 / s0 ** 2} if sd > 0 else dict(fijos)
            v, lt0 = _perfil_tau(S, gm, s0, lt0)
            curva.append(v); taus.append(math.exp(lt0))
    else:
        tau = condicion["tau"][f"{lt.liga}|{lt.temporada}"]
        for sd in rejilla:
            gm = {**fijos, "jugadores": tau ** 2 / s0 ** 2}
            if sd > 0:
                gm[nombre] = sd ** 2 / s0 ** 2
            curva.append(S.m2ll(gm)[0]); taus.append(tau)
    info.update({"rejilla": rejilla, "m2ll": curva, "tau": taus, "segundos": round(time.time() - t0, 1)})
    return info


# =============================================================================================== agregación
def _minimo(rejilla: np.ndarray, curva: np.ndarray, fino: int = 3001) -> tuple[float, np.ndarray, np.ndarray]:
    f = PchipInterpolator(rejilla, curva)
    xs = np.linspace(rejilla[0], rejilla[-1], fino)
    ys = f(xs)
    return float(xs[int(np.argmin(ys))]), xs, ys


def agregar(curvas: list[dict], B: int, semilla: int) -> dict:
    """σ̂ común, intervalos de perfil y de bootstrap de ligas-temporada, contraste de σ = 0 y fiabilidad."""
    cs = [c for c in curvas if "m2ll" in c]
    if not cs:
        return {"ligas_temporada": 0}
    rej = np.array(cs[0]["rejilla"])
    M = np.array([c["m2ll"] for c in cs])                      # ℓt × rejilla
    M0 = M - M[:, [0]]                                         # relativo a σ = 0 (estabilidad numérica)
    tot = M0.sum(0)
    sig, xs, ys = _minimo(rej, tot)
    ymin = float(ys.min())
    dentro = lambda d: [float(xs[ys <= ymin + d].min()), float(xs[ys <= ymin + d].max())]  # noqa: E731
    lrt = float(tot[0] - ymin)
    p = float(0.5 * chi2.sf(lrt, 1)) if lrt > 0 else 0.5
    rng = np.random.default_rng(semilla)
    idx = rng.integers(0, len(cs), size=(B, len(cs)))
    bs = np.array([_minimo(rej, M0[i].sum(0), 601)[0] for i in idx])
    s0 = float(np.median([c["sigma0"] for c in cs]))
    fiab = {str(n): float(sig ** 2 / (sig ** 2 + s0 ** 2 / n)) if sig > 0 else 0.0 for n in (150, 500, 1000, 3000)}
    return {"ligas_temporada": len(cs), "tramos": int(sum(c["n"] for c in cs)),
            "unidades": int(sum(c["dims"].get(_ult(c), 0) for c in cs)),
            "sigma": sig, "varianza": sig ** 2,
            "sigma_r80_perfil": dentro(chi2.ppf(0.80, 1)), "sigma_ic95_perfil": dentro(chi2.ppf(0.95, 1)),
            "sigma_r80_bootstrap": [float(np.quantile(bs, 0.10)), float(np.quantile(bs, 0.90))],
            "sigma_ic95_bootstrap": [float(np.quantile(bs, 0.025)), float(np.quantile(bs, 0.975))],
            "frac_bootstrap_en_cero": float(np.mean(bs <= rej[1] / 2)),
            "en_borde_superior": bool(sig >= rej[-1] - 1e-9),
            "lrt_sigma_0": lrt, "p_sigma_0": p, "sigma0_mediana": s0, "fiabilidad_unidad": fiab,
            "curva_total": {"rejilla": rej.tolist(), "m2ll_rel": tot.tolist()}}


def _ult(c: dict) -> str:
    return list(c["dims"])[-1]


# =============================================================================================== modelo de ruido ampliado
def tramos_ampliados(cfg: dict) -> pd.DataFrame:
    """Tramos del contrato v4.0 (mismos filtros que bbequipo.rapm.tramos) con el periodo y el margen del local al inicio
    del tramo, que la caché de la v4.0 no guarda. Caché: experimentos/v4_1/tramos_ampliados.pkl."""
    import pickle
    from .. import config as C40, rapm
    from ..contrato import filtrar_tramos
    cache = CE.RAIZ / "experimentos" / "v4_1" / "tramos_ampliados.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    cfg40 = CE.cargar_v40(cfg)
    temps = set(cfg["orden_sinergias"]["temporadas"])
    partes = []
    for r in rapm.ligas_incluidas(cfg40).itertuples():
        if r.temporada not in temps:
            continue
        p = C40.ruta(cfg40, "quintetos", temporada=r.temporada) / r.liga / "tramos.csv.gz"
        df = pd.read_csv(p, usecols=lambda c: c in rapm.COLS_TRAMOS + ["periodo", "margen_inicio"], low_memory=False)
        tr, _ = filtrar_tramos(df, cfg40)
        if tr.empty:
            continue
        ids = pd.concat([tr["quinteto_a"].str.split("|").explode(), tr["quinteto_b"].str.split("|").explode()])
        mp = rapm._mapa_persona(r.liga, ids)
        conv = lambda q, t=r.temporada: tuple(f"{mp[x]}|{t}" for x in q.split("|"))  # noqa: E731
        o = pd.DataFrame({"liga": r.liga, "temporada": r.temporada, "game_id": tr["game_id"].to_numpy(),
                          "fase": tr["fase"].to_numpy(), "team_a": tr["team_a"].astype(str).to_numpy(),
                          "team_b": tr["team_b"].astype(str).to_numpy(),
                          "clutch": tr["clutch"].astype(str).str.lower().isin(["true", "1"]).to_numpy(),
                          "playoffs": (tr["fase"] != "regular").to_numpy(), "poss": tr["poss"].to_numpy(float),
                          "periodo": pd.to_numeric(tr["periodo"], errors="coerce").fillna(1).to_numpy(int),
                          "margen": pd.to_numeric(tr["margen_inicio"], errors="coerce").fillna(0).to_numpy(float),
                          "A": tr["quinteto_a"].map(conv).to_numpy(), "B": tr["quinteto_b"].map(conv).to_numpy(),
                          "y": (100.0 * (pd.to_numeric(tr["a_pts"]) - pd.to_numeric(tr["b_pts"])) / tr["poss"]).to_numpy()})
        partes.append(o)
    t = pd.concat(partes, ignore_index=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pickle.dumps(t))
    return t


def preparar_ampliado(d: pd.DataFrame, semilla: int, cfg: dict) -> tuple[OS.LT, dict]:
    """LT con (i) efectos fijos del estado del marcador (margen del local al inicio del tramo por tramos, y su interacción
    con el último cuarto y la prórroga) y (ii) varianza de tramo σ²·(1/n + c/n²), c estimado en la propia ℓt con los
    residuos de un primer ajuste aditivo (los tramos cortos son más ruidosos de lo que dice 1/n: error del estimador de
    posesiones). Con el modelo «simple» devuelve el LT de siempre (varianza σ²/n, sin marcador)."""
    lt = OS.preparar(d, semilla)
    cr = cfg["sinergia_mixta"].get("ruido", {})
    if cr.get("modelo", "simple") != "ampliado":
        return lt, {"modelo": "simple"}
    m = d["margen"].to_numpy(float)
    cortes = [float(x) for x in cr["margen_cortes"]]
    bin_ = np.digitize(m, cortes)                               # 0 … len(cortes)
    base = int(np.digitize([0.0], cortes)[0])
    ult = (d["periodo"].to_numpy(int) >= 4).astype(float)
    cols = [(bin_ == k).astype(float) for k in range(len(cortes) + 1) if k != base]
    if cr.get("interaccion_ultimo_cuarto", True):
        cols += [c * ult for c in cols] + [ult]
    F = np.c_[lt.F, np.column_stack(cols)] if cols else lt.F
    lt = OS.LT(lt.liga, lt.temporada, lt.PA, lt.PB, lt.ta, lt.tb, lt.y, lt.w, F, lt.partido, lt.tercio, lt.claves, lt.equipos)
    # varianza: n·r² = a + b/n  →  Var(y_s) ∝ 1/n + c/n², c = b/a (≥ 0)
    X = sp.hstack([OS.diseno(lt)[:, :lt.nP], sp.csr_matrix(F)]).tocsr()
    G = (X.T @ X.multiply(lt.w[:, None])).toarray()
    G[np.arange(lt.nP), np.arange(lt.nP)] += float(cr.get("lambda_primer_ajuste", 3000.0))
    G[np.arange(lt.nP, G.shape[0]), np.arange(lt.nP, G.shape[0])] += 1e-6
    coef = np.linalg.solve(G, np.asarray(X.T @ (lt.w * lt.y)).ravel())
    r = lt.y - X @ coef
    n = lt.w
    Z = np.c_[np.ones(len(n)), 1.0 / n]
    a, b = np.linalg.lstsq(Z, n * r * r, rcond=None)[0]
    c = float(max(b / a, 0.0)) if a > 0 else 0.0
    w = 1.0 / (1.0 / n + c / n ** 2)
    lt = OS.LT(lt.liga, lt.temporada, lt.PA, lt.PB, lt.ta, lt.tb, lt.y, w, F, lt.partido, lt.tercio, lt.claves, lt.equipos)
    # diagnóstico: dispersión del error por partido frente a la que supone el modelo (1 = coherente)
    e = r * w
    vr = float((pd.Series(e).groupby(lt.partido).sum() ** 2).sum() / (np.sum(w * r * r) / len(r) * w.sum()))
    return lt, {"modelo": "ampliado", "c": c, "a": float(a), "fijos_marcador": len(cols), "razon_var_partido": vr}


# =============================================================================================== orquestación
def _lts(cfg: dict, ligas=None) -> list[pd.DataFrame]:
    if cfg["sinergia_mixta"].get("ruido", {}).get("modelo", "simple") == "ampliado":
        tr = tramos_ampliados(cfg)
    else:
        from .. import rapm
        tr = rapm.tramos(CE.cargar_v40(cfg), progreso=None)
    tr = tr[tr["temporada"].isin(cfg["orden_sinergias"]["temporadas"])]
    if ligas:
        tr = tr[tr["liga"].isin(ligas)]
    return [d for _, d in tr.groupby(["liga", "temporada"])]


def _g(lt: OS.LT, priors: dict) -> np.ndarray:
    gl = np.array([priors.get(k, np.nan) for k in lt.claves])
    gl[np.isnan(gl)] = np.nanmean(gl) if np.isfinite(gl).any() else 0.0
    return gl


def ejecutar(cfg: dict, versiones=("a", "b"), etapas=(2, 3, 5), ligas=None, progreso=print) -> dict:
    cm, co = cfg["sinergia_mixta"], cfg["comunes"]
    elite = set(co["segmentos"]["elite_club"])
    B, sem = int(co["bootstrap"]), int(co["semilla_bootstrap"])
    priors, _ = OS._priors(cfg)
    grupos = _lts(cfg, ligas)
    dcache = CE.RAIZ / "experimentos" / "v4_1" / "sinergia_mixta"
    dcache.mkdir(parents=True, exist_ok=True)
    dsal = CE.dir_salida(cfg, "sinergia_mixta")
    p_res = dsal / "resumen.json"
    resumen = json.loads(p_res.read_text()) if p_res.exists() and not ligas else {}
    resumen.update({"version": cfg["version"], "config": cm})
    resumen.setdefault("versiones", {})
    for v in versiones:
        rv = resumen["versiones"].setdefault(v, {})
        condicion = {"tau": {}}
        for e in etapas:
            if e not in [int(x) for x in cm["etapas"][v]]:
                continue
            if e >= 3:
                if "pareja" not in rv:
                    raise RuntimeError("la etapa 3 necesita la etapa 2 de la misma versión")
                condicion["pareja"] = rv["pareja"]["global"]["sigma"]
                cur2 = json.loads((dsal / f"curvas_{v}_2.json").read_text())
                for c in cur2:
                    if "m2ll" in c:                            # τ̂ de cada ℓt en el σ̂_2 agregado (interpolado)
                        condicion["tau"][f"{c['liga']}|{c['temporada']}"] = float(np.interp(
                            condicion["pareja"], c["rejilla"], c["tau"]))
            if e >= 5:
                condicion["trio"] = rv["trio"]["global"]["sigma"]
            curvas = []
            t0 = time.time()
            seg_e = cm.get("segmento_por_etapa", {}).get(str(e), "global")
            grupos_e = [d for d in grupos if seg_e == "global" or str(d["liga"].iloc[0]) in elite]
            for i, d in enumerate(sorted(grupos_e, key=len)):
                lg, tp = str(d["liga"].iloc[0]), str(d["temporada"].iloc[0])
                fc = dcache / f"{cm.get('ruido', {}).get('modelo', 'simple')}_{v}_{e}_{lg}_{tp}.json"
                if fc.exists():
                    c = json.loads(fc.read_text())
                else:
                    lt, ruido = preparar_ampliado(d, CE.semilla(cfg, f"tercios|{lg}|{tp}"), cfg)
                    if e >= 3 and f"{lg}|{tp}" not in condicion["tau"]:
                        c = {"liga": lg, "temporada": tp, "n": lt.n, "omitida": "sin etapa 2"}
                    else:
                        c = curvas_lt(lt, v, e, cm, _g(lt, priors) if v == "b" else None, condicion, cm["q_max_denso"])
                        c["ruido"] = ruido
                    fc.write_text(json.dumps(c, default=float))
                curvas.append(c)
                if progreso:
                    progreso(f"  [{v}·{NOMBRE[e]}] {i + 1}/{len(grupos_e)} {lg} {tp} "
                             f"{c.get('omitida') or str(c.get('segundos')) + ' s'} · {time.time() - t0:.0f} s", flush=True)
            if not ligas:
                (dsal / f"curvas_{v}_{e}.json").write_text(json.dumps(curvas, default=float, ensure_ascii=False),
                                                           encoding="utf-8")
            rv[NOMBRE[e]] = {
                "global": agregar(curvas, B, sem),
                "elite_club": agregar([c for c in curvas if c["liga"] in elite], B, sem),
                "omitidas": sorted(f"{c['liga']} {c['temporada']}" for c in curvas if "omitida" in c),
                "condicion": {k: v_ for k, v_ in condicion.items() if k != "tau"},
                "segmento_calculado": seg_e,
            }
            if progreso:
                gg = rv[NOMBRE[e]]["global"]
                progreso(f"[{v}] {NOMBRE[e]}: σ̂ = {gg.get('sigma', float('nan')):.3f} · r80 perfil "
                         f"{gg.get('sigma_r80_perfil')} · IC95 bootstrap {gg.get('sigma_ic95_bootstrap')} · "
                         f"p(σ=0) {gg.get('p_sigma_0')}", flush=True)
            if not ligas:
                resumen["generado"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                p_res.write_text(json.dumps(resumen, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return resumen


# =============================================================================================== calibración plantada sobre datos reales
def plantada(cfg: dict, version: str = "a", sds=(0.5, 1.0), segmento: str = "elite_club", replicas: int = 1,
             progreso=print) -> dict:
    """Control de validez sobre el diseño y el ruido REALES: y* = y + Σ_A u − Σ_B u con u ~ N(0, sd²) por pareja, y se
    vuelve a estimar σ_2. Si el modelo mixto está bien calibrado con el ruido real, σ̂_2(y*)² ≈ σ̂_2(y)² + sd². Si el ruido
    real tuviera estructura que el modelo no recoge (p. ej. dependencia entre tramos de un mismo partido), σ̂ se quedaría
    corto y este cociente lo mediría."""
    cm, co = cfg["sinergia_mixta"], cfg["comunes"]
    elite = set(co["segmentos"]["elite_club"])
    priors, _ = OS._priors(cfg)
    grupos = [d for d in _lts(cfg) if segmento == "global" or str(d["liga"].iloc[0]) in elite]
    out = {"version": version, "segmento": segmento, "sds": list(sds), "replicas": replicas,
           "ruido": cm.get("ruido", {}), "resultados": {}}
    for sd in sds:
        curvas = []
        for rep in range(replicas):
            for d in sorted(grupos, key=len):
                lg, tp = str(d["liga"].iloc[0]), str(d["temporada"].iloc[0])
                lt, ruido = preparar_ampliado(d, CE.semilla(cfg, f"tercios|{lg}|{tp}"), cfg)
                rng = np.random.default_rng(CE.semilla(cfg, f"plantada|{lg}|{tp}|{sd}|{rep}"))
                lt2 = lt.con_y(lt.y + OS.efecto_plantado(lt, 2, float(sd), rng))
                c = curvas_lt(lt2, version, 2, cm, _g(lt, priors) if version == "b" else None, {}, cm["q_max_denso"])
                c["ruido"] = ruido
                curvas.append(c)
                if progreso:
                    progreso(f"  [plantada sd={sd} rep={rep}] {lg} {tp} {c.get('segundos')} s", flush=True)
        ag = agregar(curvas, 500, int(co["semilla_bootstrap"]))
        ag.pop("curva_total", None)
        out["resultados"][str(sd)] = ag
    d = CE.dir_salida(cfg, "sinergia_mixta")
    (d / f"plantada_{version}_{segmento}_{cm.get('ruido', {}).get('modelo', 'simple')}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float),
                                                         encoding="utf-8")
    return out
