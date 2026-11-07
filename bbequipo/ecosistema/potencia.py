"""Efecto mínimo detectable (EMD) · obligatorio en todo examen de la v4.1 (propuesta 1 aprobada por el CEO, 07-11-2026).

Idea: antes de usar un examen para decidir, se mide qué tamaño de efecto es capaz de ver. Se SIEMBRA un efecto de tamaño
conocido δ sobre los datos REALES (así se conservan el ruido, el diseño de las rotaciones y todo lo que el modelo no
recoge), se repite el examen tal y como está prerregistrado y se cuenta en cuántas réplicas detecta. La tasa de detección
en función de δ es la curva de potencia; el EMD es el δ con el que se alcanza la potencia objetivo (80 % por defecto).
Regla (configs/ecosistema_v41.yaml → potencia): si el EMD es mayor que el efecto plausible o que el umbral que el examen
pide, el examen NO es informativo y no decide; se declara así en el checkpoint.

Primera aplicación: la puerta F3-T (§6.3 del encargo: sinergia de trío por perfiles φ_jkl, DT ≥ 0,10 pts/100 y reducción
del error con IC95 < 0). Versión del examen usada para medir la potencia [declarada como cota OPTIMISTA]:
  · rasgos de perfil u_i = Pᵀ z_i (los 4 componentes de la sinergia de parejas F2-A de la v4.0);
  · modelo: y = fijos + Σβ (jugadores, ridge) + φ_pareja(u) + φ_trío(u), con φ_trío(u_i, u_j, u_k) = ⟨T, sim(u_i⊗u_j⊗u_k)⟩,
    T tensor simétrico 4×4×4 (20 parámetros comunes a todos los tríos: es la versión lineal del modelo CP de rango bajo);
  · examen: error en el tercio de partidos no usado (3 rotaciones) con y sin el término de trío; detecta si el IC95
    superior del Δ relativo < 0 (bootstrap de partidos estratificado por liga-temporada) Y la DT de φ̂_trío en los tríos
    reales ≥ 0,10;
  · efecto sembrado: φ_trío = Σ_r λ_r (a_r·u_i)(a_r·u_j)(a_r·u_k) con 2 direcciones al azar, escalado a DT δ en los tríos
    reales de cada liga-temporada.
Es optimista frente al examen real de la F3-T (t → t+1 con tríos nuevos y cada corte por separado): si aquí no se detecta
δ = 0,10, allí tampoco.

Salidas: data/modelos/v4_1/potencia/trios_<segmento>.json.
"""
from __future__ import annotations

import json
import time
from itertools import combinations, permutations

import numpy as np
import pandas as pd
import scipy.linalg as sla

from . import config as CE
from . import orden_sinergias as OS


# =============================================================================================== herramientas generales
def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """Proporción y su IC95 de Wilson."""
    if n == 0:
        return np.nan, np.nan, np.nan
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return float(p), float(max(c - h, 0.0)), float(min(c + h, 1.0))


def emd(curva: dict[float, float], objetivo: float = 0.8) -> float | None:
    """δ mínimo con potencia ≥ objetivo (interpolación lineal entre los δ sembrados); None si ningún δ llega."""
    ds = sorted(curva)
    for d0, d1 in zip([0.0] + ds, ds):
        p0, p1 = (curva.get(d0, 0.0) if d0 else 0.0), curva[d1]
        if p1 >= objetivo:
            return float(d1 if p1 == p0 else d0 + (objetivo - p0) * (d1 - d0) / (p1 - p0))
    return None


# =============================================================================================== rasgos de perfil (F2-A v4.0)
def perfiles_u(cfg: dict) -> dict[str, np.ndarray]:
    """u = Pᵀ z por clave persona|temporada, con las columnas, medias y DT de los rasgos de la sinergia F2-A (v4.0)."""
    from .. import rapm as RP
    from ..examen_f1 import perfiles_completo
    cfg40 = CE.cargar_v40(cfg)
    W = json.loads((CE.RAIZ / cfg40["f2"]["salida"] / "W_sinergia.json").read_text(encoding="utf-8"))
    cols, med, sd = W["rasgos"]["columnas"], W["rasgos"]["media"], W["rasgos"]["sd"]
    P = np.array(W["P"], float)
    T = RP.tabla_prior(perfiles_completo(cfg40, cfg40["perfil"]["temporadas"]), cfg40)
    Z = np.column_stack([(T[c].to_numpy(float) - med[c]) / sd[c] if c in T else np.zeros(len(T)) for c in cols])
    Z[~np.isfinite(Z)] = 0.0
    U = Z @ P
    return dict(zip(T["clave"].astype(str), U))


SIM3 = [(a, b, c) for a in range(4) for b in range(a, 4) for c in range(b, 4)]       # 20 componentes del tensor simétrico
SIM2 = [(a, b) for a in range(4) for b in range(a, 4)]                               # 10 de la matriz simétrica
TRIOS = list(combinations(range(5), 3))
PARES = list(combinations(range(5), 2))


def rasgos_lado(U5: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Para quintetos (n × 5 × 4): rasgos de pareja (n × 10) y de trío (n × 20) sumados sobre sus 10 parejas y 10 tríos,
    y los rasgos de cada trío (n × 10 × 20), para evaluar φ̂ en los tríos reales."""
    n = U5.shape[0]
    Fp = np.zeros((n, len(SIM2)))
    for i, j in PARES:
        for c, (a, b) in enumerate(SIM2):
            Fp[:, c] += 0.5 * (U5[:, i, a] * U5[:, j, b] + U5[:, i, b] * U5[:, j, a])
    Ft3 = np.zeros((n, len(TRIOS), len(SIM3)))
    for t, (i, j, k) in enumerate(TRIOS):
        for c, (a, b, cc) in enumerate(SIM3):
            # suma sobre las permutaciones distintas de (a, b, c): base de las formas cúbicas simétricas que contiene
            # exactamente a la sinergia CP sembrada, (A·u_i)(A·u_j)(A·u_k) = Σ_{a≤b≤c} A_a A_b A_c · rasgo_abc
            Ft3[:, t, c] = sum(U5[:, i, q[0]] * U5[:, j, q[1]] * U5[:, k, q[2]] for q in set(permutations((a, b, cc))))
    return Fp, Ft3.sum(1), Ft3


def _phi_cp(U5: np.ndarray, A: np.ndarray, lam: np.ndarray) -> np.ndarray:
    """φ_trío sembrado por trío (n × 10): Σ_r λ_r (a_r·u_i)(a_r·u_j)(a_r·u_k)."""
    S = np.einsum("npk,rk->npr", U5, A)                   # n × 5 × R
    out = np.zeros((U5.shape[0], len(TRIOS)))
    for t, (i, j, k) in enumerate(TRIOS):
        out[:, t] = (S[:, i] * S[:, j] * S[:, k]) @ lam
    return out


# =============================================================================================== potencia de la puerta F3-T
class LTtrios:
    """Diseño de una liga-temporada para la puerta F3-T. Rasgos de perfil (parejas y tríos) estandarizados; jugadores con
    el λ del RAPM ridge (validación interna); λ de los rasgos elegido por validación cruzada ANIDADA dentro de los dos
    tercios de ajuste de cada rotación (nunca con el tercio de evaluación), por separado en el modelo con y sin tríos."""

    def __init__(self, tr: pd.DataFrame, U: dict, cfg: dict):
        lg, tp = str(tr["liga"].iloc[0]), str(tr["temporada"].iloc[0])
        self.lt = OS.preparar(tr, CE.semilla(cfg, f"tercios|{lg}|{tp}"))
        lt = self.lt
        Uc = np.array([U.get(k, np.zeros(4)) for k in lt.claves])
        UA, UB = Uc[lt.PA], Uc[lt.PB]                       # n × 5 × 4
        self.UA, self.UB = UA, UB
        FpA, FtA, FtA3 = rasgos_lado(UA)
        FpB, FtB, FtB3 = rasgos_lado(UB)
        w = lt.w
        Rp, Rt = FpA - FpB, FtA - FtB
        sd = lambda M: np.sqrt(np.average((M - np.average(M, 0, weights=w)) ** 2, 0, weights=w)) + 1e-12  # noqa: E731
        self.sp, self.st = sd(Rp), sd(Rt)
        Xp = OS.diseno(lt).toarray()
        self.nP, self.nF = lt.nP, lt.F.shape[1]
        self.X1 = np.c_[Xp, Rp / self.sp, Rt / self.st]
        self.k0 = self.nP + self.nF + Rp.shape[1]
        self.k1 = self.X1.shape[1]
        self.FtA3, self.FtB3 = FtA3, FtB3
        self.lam_p = OS.ajustar_aditivo(lt, OS.diseno(lt), np.ones(lt.n, bool), "a", cfg["orden_sinergias"], semilla=1)[1]["lambda"]
        self.rej = [float(v) for v in cfg["potencia"]["trios"]["lambda_rejilla"]]
        self.G = {t: (self.X1[lt.tercio == t] * w[lt.tercio == t, None]).T @ self.X1[lt.tercio == t] for t in range(3)}
        self.w_trio = np.repeat(w, len(TRIOS))

    def _resolver(self, G, b, k, lam_f):
        pen = np.r_[np.full(self.nP, self.lam_p), np.full(self.nF, 1e-6), np.full(k - self.nP - self.nF, lam_f)]
        return sla.solve(G[:k, :k] + np.diag(pen), b[:k], assume_a="pos", check_finite=False)

    def _elegir(self, ts, bs, k):
        """λ de los rasgos por validación cruzada de 2 pliegues dentro de los tercios de ajuste ts = (a, b)."""
        lt, w = self.lt, self.lt.w
        mejor, best = None, np.inf
        for lam in self.rej:
            sse = 0.0
            for f, v in ((ts[0], ts[1]), (ts[1], ts[0])):
                c = self._resolver(self.G[f], bs[f], k, lam)
                m = lt.tercio == v
                e = self._y[m] - self.X1[m, :k] @ c
                sse += float(np.sum(w[m] * e ** 2))
            if sse < best:
                mejor, best = lam, sse
        return mejor

    def sembrar(self, delta: float, rng) -> np.ndarray:
        if delta <= 0:
            return self.lt.y
        R = 2
        A = rng.normal(size=(R, 4))
        A /= np.linalg.norm(A, axis=1, keepdims=True)
        lam = rng.choice([-1.0, 1.0], R)
        pa, pb = _phi_cp(self.UA, A, lam), _phi_cp(self.UB, A, lam)
        todos = np.r_[pa.ravel(), pb.ravel()]
        ww = np.r_[self.w_trio, self.w_trio]
        m = np.average(todos, weights=ww)
        dt = np.sqrt(np.average((todos - m) ** 2, weights=ww))
        f = delta / dt if dt > 0 else 0.0
        return self.lt.y + f * (pa.sum(1) - pb.sum(1))

    def examen(self, y: np.ndarray) -> tuple[pd.DataFrame, float]:
        """Error por partido del tercio no usado con (sse1) y sin (sse0) el término de trío, y DT de φ̂_trío real."""
        lt, w = self.lt, self.lt.w
        self._y = y
        bs = {t: (self.X1[lt.tercio == t] * w[lt.tercio == t, None]).T @ y[lt.tercio == t] for t in range(3)}
        filas, dts = [], []
        for k in range(3):
            ts = tuple(t for t in range(3) if t != k)
            G = self.G[ts[0]] + self.G[ts[1]]
            b = bs[ts[0]] + bs[ts[1]]
            c0 = self._resolver(G, b, self.k0, self._elegir(ts, bs, self.k0))
            c1 = self._resolver(G, b, self.k1, self._elegir(ts, bs, self.k1))
            te = lt.tercio == k
            e0 = y[te] - self.X1[te, :self.k0] @ c0
            e1 = y[te] - self.X1[te] @ c1
            filas.append(pd.DataFrame({"partido": lt.partido[te], "sse0": w[te] * e0 ** 2, "sse1": w[te] * e1 ** 2}))
            T = c1[self.k0:] / self.st                     # coeficientes en la escala original de los rasgos
            ph = np.r_[(self.FtA3 @ T).ravel(), (self.FtB3 @ T).ravel()]
            ww = np.r_[self.w_trio, self.w_trio]
            m = np.average(ph, weights=ww)
            dts.append(float(np.sqrt(np.average((ph - m) ** 2, weights=ww))))
        d = pd.concat(filas).groupby("partido")[["sse0", "sse1"]].sum()
        return d, float(np.mean(dts))


def _decidir(partes: list[pd.DataFrame], dts: list[float], umbral_dt: float, B: int, rng) -> dict:
    s0 = sum(p["sse0"].sum() for p in partes)
    s1 = sum(p["sse1"].sum() for p in partes)
    bs = []
    arrs = [p[["sse0", "sse1"]].to_numpy() for p in partes]
    for _ in range(B):
        a0 = a1 = 0.0
        for a in arrs:
            i = rng.integers(0, len(a), len(a))
            a0 += a[i, 0].sum(); a1 += a[i, 1].sum()
        bs.append(a1 / a0 - 1)
    hi = float(np.quantile(bs, 0.975))
    dt = float(np.average(dts, weights=[p["sse0"].sum() for p in partes]))
    return {"delta_rel": float(s1 / s0 - 1), "ic95_sup": hi, "detecta_error": hi < 0, "dt_phi": dt,
            "detecta_dt": dt >= umbral_dt, "detecta": bool(hi < 0 and dt >= umbral_dt)}


def potencia_trios(cfg: dict, segmento: str = "elite_club", progreso=print) -> dict:
    from .. import rapm
    cp, cm = cfg["potencia"], cfg["comunes"]
    ct = cp["trios"]
    elite = set(cm["segmentos"]["elite_club"])
    U = perfiles_u(cfg)
    tr = rapm.tramos(CE.cargar_v40(cfg), progreso=None)
    tr = tr[tr["temporada"].isin(cfg["orden_sinergias"]["temporadas"])]
    if segmento == "elite_club":
        tr = tr[tr["liga"].isin(elite)]
    grupos = [d for _, d in tr.groupby(["liga", "temporada"]) if int(OS.preparar(d, 0).nP) <= int(ct["max_jugadores_lt"])]
    t0 = time.time()
    L = []
    for d in grupos:
        L.append(LTtrios(d, U, cfg))
        if progreso:
            progreso(f"  F3-T potencia · preparado {d['liga'].iloc[0]} {d['temporada'].iloc[0]} · {time.time() - t0:.0f} s",
                     flush=True)
    rng = np.random.default_rng(int(cfg["semilla"]) + 3)
    B = int(ct["bootstrap"])
    umbral = float(ct["umbral_dt"])
    obs = [x.examen(x.lt.y) for x in L]
    real = _decidir([o[0] for o in obs], [o[1] for o in obs], umbral, B, rng)
    curva, detalle = {}, {}
    for delta in [float(v) for v in ct["deltas"]]:
        det = []
        for r in range(int(ct["replicas"])):
            res = [x.examen(x.sembrar(delta, rng)) for x in L]
            det.append(_decidir([o[0] for o in res], [o[1] for o in res], umbral, B, rng))
        k = sum(d["detecta"] for d in det)
        p, lo, hi = wilson(k, len(det))
        curva[delta] = p
        detalle[str(delta)] = {"replicas": len(det), "potencia": p, "potencia_ic95": [lo, hi],
                               "potencia_solo_error": float(np.mean([d["detecta_error"] for d in det])),
                               "potencia_solo_dt": float(np.mean([d["detecta_dt"] for d in det])),
                               "dt_phi_media": float(np.mean([d["dt_phi"] for d in det])),
                               "delta_rel_medio": float(np.mean([d["delta_rel"] for d in det]))}
        if progreso:
            progreso(f"  δ = {delta}: potencia {p:.2f} [{lo:.2f}, {hi:.2f}] · DT φ̂ media {detalle[str(delta)]['dt_phi_media']:.3f}"
                     f" · {time.time() - t0:.0f} s", flush=True)
    e = emd(curva, float(cp["objetivo"]))
    out = {"segmento": segmento, "ligas_temporada": len(L), "omitidas_por_tamano": int(tr.groupby(["liga", "temporada"]).ngroups - len(L)),
           "examen": "cota optimista de la puerta F3-T (ver módulo)", "real": real, "curva": detalle, "emd": e,
           "umbral_puerta_dt": umbral, "potencia_objetivo": cp["objetivo"],
           "informativo": bool(e is not None and e <= umbral),
           "lectura": ("el examen puede ver una sinergia de trío por perfiles del tamaño que pide la puerta" if (e is not None and e <= umbral)
                       else "el examen NO puede ver una sinergia de trío por perfiles del tamaño que pide la puerta: no es informativo")}
    d = CE.dir_salida(cfg, "potencia")
    (d / f"trios_{segmento}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return out
