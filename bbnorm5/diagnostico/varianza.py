"""F1 §5.1 · Descomposición de varianza por métrica con REML exacto.

Modelo, por métrica m, en su escala de trabajo T (bbmodel.metricas.transformar), fila r = persona i × liga ℓ ×
temporada t (temporada regular, los equipos de una misma liga sumados):

    y_r = b_{ℓt} + a_i + u_{it} + ε_r
    a_i    ~ N(0, σ²_a)          capacidad estable del jugador (señal entre jugadores)
    u_{it} ~ N(0, σ²_u)          variación real de su nivel de una temporada a otra (común a todas sus ligas de esa
                                 temporada: es lo que comparten los puentes intra-temporada)
    ε_r    ~ N(0, σ²_g / n_r)    ruido de muestra: n_r = exposición (intentos, posesiones, minutos…), σ²_g por grupo
                                 (uno común si la exposición son tiros; uno por liga si son minutos o posesiones)
    b_{ℓt}                       efecto liga-temporada, FIJO (≈130 niveles con cientos de filas cada uno)

Relación con la ecuación del encargo (y = μ + a + b + e): e = u + ε. Separar u de ε es necesario para que la fiabilidad
diga algo útil: ε baja con la exposición, u no (es irreducible dentro de una temporada).

Por qué REML exacto y barato: con b fijo, la covarianza marginal es diagonal por bloques de persona, y cada bloque es
anidado (filas ⊂ temporadas ⊂ persona) con ruido diagonal. Su inversa y su determinante salen en forma cerrada con
Sherman–Morrison por niveles, así que la verosimilitud restringida se evalúa en O(N) más un sistema K×K (K = niveles
de b). Con w_r = n_r/σ²_g, W_s = Σ_{r∈s} w_r, f_s = 1/(1 + σ²_u W_s), Ω_i = Σ_{s∈i} W_s f_s, h_i = 1/(1 + σ²_a Ω_i):

    x'V⁻¹z = Σ_r w x z − σ²_u Σ_s f_s (Σ_{r∈s} w x)(Σ_{r∈s} w z) − σ²_a Σ_i h_i (Σ_{s∈i} f_s Σ_{r∈s} w x)(· z)
    log|V| = Σ_r log(1/w_r) + Σ_s log(1 + σ²_u W_s) + Σ_i log(1 + σ²_a Ω_i)

Salidas por métrica: σ²_a, σ²_u, σ²_b (varianza entre liga-temporadas, corregida por el error de b̂), σ² del ruido,
fiabilidades y puntos de estabilización:
    ρ_temp(n) = (σ²_a + σ²_u) / (σ²_a + σ²_u + σ²/n)    fiabilidad de una temporada para el nivel de ESA temporada
    ρ_carr(n) = σ²_a / (σ²_a + σ²_u + σ²/n)              fiabilidad de una temporada para la capacidad estable
    n*_temp   = σ² / (σ²_a + σ²_u)                       exposición con ρ_temp = 0,5 (comparable con la división de muestra)
    n*_carr   = σ² / (σ²_a − σ²_u)  si σ²_a > σ²_u        exposición con ρ_carr = 0,5 (si no, no se alcanza nunca)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.optimize import minimize

TIROS = ("tsa", "fga", "fg3a", "fg2a", "fta", "plays", "fga_pbp", "fgm_pbp")


# --------------------------------------------------------------------------------------------- estructura de datos
class Datos:
    """Índices y matrices dispersas del modelo anidado para una métrica."""

    def __init__(self, y, n, persona, temporada, grupo_b, grupo_s2):
        orden = np.lexsort((temporada, persona))
        self.y = np.asarray(y, float)[orden]
        self.n = np.asarray(n, float)[orden]
        per = np.asarray(persona)[orden]
        tem = np.asarray(temporada)[orden]
        self.persona_codigos, self.per = np.unique(per, return_inverse=True)
        clave_pt = pd.Series(per.astype(str)) + "|" + pd.Series(tem.astype(str))
        _, self.pt = np.unique(clave_pt.to_numpy(), return_inverse=True)
        self.S = int(self.pt.max()) + 1
        self.I = int(self.per.max()) + 1
        self.per_de_pt = np.zeros(self.S, int)
        self.per_de_pt[self.pt] = self.per
        self.b_niveles, self.b = np.unique(np.asarray(grupo_b)[orden], return_inverse=True)
        self.K = len(self.b_niveles)
        self.g_niveles, self.g = np.unique(np.asarray(grupo_s2)[orden], return_inverse=True)
        self.G = len(self.g_niveles)
        N = len(self.y)
        self.N = N
        # filas → (temporada de persona, nivel b): para las sumas Σ_{r∈s} w x con x indicador de b
        self._fila_sb = sp.csr_matrix((np.ones(N), (self.pt, self.b)), shape=(self.S, self.K))
        self.Pis = sp.csr_matrix((np.ones(self.S), (self.per_de_pt, np.arange(self.S))), shape=(self.I, self.S))


def _componentes(D: Datos, s2a: float, s2u: float, s2g: np.ndarray):
    w = D.n / s2g[D.g]
    W = np.bincount(D.pt, w, D.S)
    f = 1.0 / (1.0 + s2u * W)
    Om = np.bincount(D.per_de_pt, W * f, D.I)
    h = 1.0 / (1.0 + s2a * Om)
    return w, W, f, Om, h


def _formas(D: Datos, s2a, s2u, s2g):
    """X'V⁻¹X, X'V⁻¹y, y'V⁻¹y y log|V| (X = indicadores de b)."""
    w, W, f, Om, h = _componentes(D, s2a, s2u, s2g)
    y = D.y
    # Σ_{r∈s} w_r [indicador b]  (S × K) y Σ_{r∈s} w_r y_r  (S)
    Bs = sp.csr_matrix((w, (D.pt, D.b)), shape=(D.S, D.K))
    by = np.bincount(D.pt, w * y, D.S)
    Ci = D.Pis @ sp.diags(f) @ Bs                            # I × K
    cy = D.Pis @ (f * by)                                    # I
    XtVX = (sp.diags(np.bincount(D.b, w, D.K)) - s2u * (Bs.T @ sp.diags(f) @ Bs)
            - s2a * (Ci.T @ sp.diags(h) @ Ci)).toarray()
    XtVy = np.bincount(D.b, w * y, D.K) - s2u * (Bs.T @ (f * by)) - s2a * (Ci.T @ (h * cy))
    yVy = float(np.sum(w * y * y) - s2u * np.sum(f * by * by) - s2a * np.sum(h * cy * cy))
    logdet = float(np.sum(-np.log(w)) + np.sum(np.log1p(s2u * W)) + np.sum(np.log1p(s2a * Om)))
    return XtVX, np.asarray(XtVy).ravel(), yVy, logdet


def _nll_reml(theta: np.ndarray, D: Datos) -> float:
    s2a, s2u = np.exp(theta[0]), np.exp(theta[1])
    s2g = np.exp(theta[2:])
    XtVX, XtVy, yVy, logdet = _formas(D, s2a, s2u, s2g)
    signo, ld = np.linalg.slogdet(XtVX)
    if signo <= 0:
        return 1e100
    beta = np.linalg.solve(XtVX, XtVy)
    yPy = yVy - float(beta @ XtVy)
    return 0.5 * (logdet + ld + yPy)


def _hessiano(fun, x, eps=1e-3):
    k = len(x)
    H = np.zeros((k, k))
    f0 = fun(x)
    for i in range(k):
        for j in range(i, k):
            ei, ej = np.eye(k)[i] * eps, np.eye(k)[j] * eps
            if i == j:
                H[i, i] = (fun(x + ei) - 2 * f0 + fun(x - ei)) / eps ** 2
            else:
                H[i, j] = H[j, i] = (fun(x + ei + ej) - fun(x + ei - ej) - fun(x - ei + ej) + fun(x - ei - ej)) / (4 * eps ** 2)
    return H


def ajustar(D: Datos) -> dict:
    """REML de (σ²_a, σ²_u, σ²_g) en escala logarítmica; errores típicos por el hessiano observado (método delta)."""
    vy = float(np.var(D.y))
    nmed = float(np.median(D.n))
    x0 = np.r_[np.log(0.4 * vy), np.log(0.1 * vy), np.full(D.G, np.log(0.4 * vy * nmed))]
    res = minimize(_nll_reml, x0, args=(D,), method="L-BFGS-B",
                   bounds=[(np.log(vy) - 25, np.log(vy) + 5)] * 2 + [(np.log(vy * nmed) - 25, np.log(vy * nmed) + 8)] * D.G,
                   options={"maxiter": 500})
    th = res.x
    s2a, s2u, s2g = np.exp(th[0]), np.exp(th[1]), np.exp(th[2:])
    # Hessiano observado en (log σ²_a, log σ²_u, log k), con σ²_g → k·σ²_g: recoge la correlación de σ²_a y σ²_u con el
    # nivel de ruido sin derivar respecto a cada σ²_g por separado (hasta 21 grupos; el error típico de cada σ²_g no se
    # usa en la F1)
    try:
        def f3(z):
            return _nll_reml(np.r_[z[0], z[1], th[2:] + z[2]], D)
        H = _hessiano(f3, np.r_[th[0], th[1], 0.0])
        cov = np.linalg.pinv(H)
        se3 = np.sqrt(np.clip(np.diag(cov), 0, None))
        se_log = np.r_[se3[0], se3[1], np.full(D.G, se3[2])]
    except Exception:                                       # pragma: no cover - diagnóstico
        cov, se_log = None, np.full(len(th), np.nan)
    XtVX, XtVy, _, _ = _formas(D, s2a, s2u, s2g)
    cov_b = np.linalg.inv(XtVX)
    beta = cov_b @ XtVy
    # varianza entre liga-temporadas, corregida por el error de estimación de cada b̂
    s2b = float(max(np.var(beta, ddof=1) - np.mean(np.diag(cov_b)), 0.0))
    return {"convergio": bool(res.success), "nll": float(res.fun), "iter": int(res.nit),
            "s2a": float(s2a), "s2u": float(s2u), "s2g": dict(zip(map(str, D.g_niveles), map(float, s2g))),
            "se_log_s2a": float(se_log[0]), "se_log_s2u": float(se_log[1]),
            "corr_log_a_u": float(cov[0, 1] / np.sqrt(cov[0, 0] * cov[1, 1])) if cov is not None and cov[0, 0] > 0 and cov[1, 1] > 0 else np.nan,
            "se_log_k_s2g": float(se_log[2]),
            "s2b": s2b, "b": dict(zip(map(str, D.b_niveles), map(float, beta))),
            "n_filas": D.N, "n_personas": D.I, "n_persona_temporadas": D.S, "K_b": D.K}


# ------------------------------------------------------------------------------------------------- resumen por métrica
def resumen(aj: dict, n: np.ndarray, g: np.ndarray) -> dict:
    """Proporciones, fiabilidades y puntos de estabilización a la exposición media (y mediana) de la métrica."""
    s2a, s2u, s2b = aj["s2a"], aj["s2u"], aj["s2b"]
    s2_fila = np.array([aj["s2g"][str(x)] for x in g])
    ruido_medio = float(np.mean(s2_fila / n))               # varianza de muestra media de una temporada
    nbar, nmed = float(np.mean(n)), float(np.median(n))
    s2_tip = float(np.median(s2_fila))                      # σ² típico (mediana por filas)
    total = s2a + s2u + s2b + ruido_medio
    señal_temp = s2a + s2u
    out = {"n_medio": nbar, "n_mediano": nmed, "s2_ruido_tipico": s2_tip, "ruido_medio": ruido_medio,
           "prop_jugador": s2a / total, "prop_temporada_jugador": s2u / total, "prop_liga_temporada": s2b / total,
           "prop_ruido_muestra": ruido_medio / total,
           "rho_temp_nmedio": señal_temp / (señal_temp + s2_tip / nbar),
           "rho_carr_nmedio": s2a / (señal_temp + s2_tip / nbar),
           "rho_temp_medio_filas": float(np.mean(señal_temp / (señal_temp + s2_fila / n))),
           "techo_rho_carr": s2a / señal_temp,
           "n_estab_temp": s2_tip / señal_temp,
           "n_estab_carr": (s2_tip / (s2a - s2u)) if s2a > s2u else np.inf,
           # fórmula literal del encargo: ρ = σ²_a / (σ²_a + σ²_e/n̄) con e = u + ε (σ²_e/n̄ ≈ σ²_u + σ²/n̄)
           "rho_encargo": s2a / (s2a + s2u + s2_tip / nbar)}
    return out
