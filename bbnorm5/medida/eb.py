"""F3.2 · Modelos de medida por familia, Bayes empírico con cuadratura exacta en rejilla.

Para cada métrica y liga-temporada, y para cada unidad u (persona en esa liga-temporada) con rol r(u):

    binomial:  K_u | p_u ~ Binomial(N_u, p_u)                logit p_u = μ_r(u) + α_u,  α_u ~ N(0, σ²)
    + sobred.: K_u | p_u ~ BetaBinomial(N_u, p_u, ρ_ef,u)    ρ_ef,u = ρ·(Σn_g²/N_u − 1)/(N_u − 1)
    poisson:   K_u | λ_u ~ Poisson(N_u λ_u)                   log λ_u  = μ_r(u) + α_u
    + sobred.: K_u | λ_u ~ BinNeg1(N_u λ_u, δ)               Var = N_u λ_u (1 + δ)
    normal:    K_u | θ_u ~ N(θ_u N_u, φ N_u)                   θ_u = μ_r(u) + α_u   (conjugado, sin rejilla)

- ρ es la correlación intra-partido de los intentos (rachas, contexto del partido): con ρ > 0, el conteo de la
  temporada suma partidos sobredispersos y su varianza crece en Σ n_g (1 + (n_g − 1)ρ). La beta-binomial de la
  unidad con ρ_ef iguala esa varianza (SUPUESTO: aproximación por momentos; la F3.3 la contrasta con el modelo por
  partido en NUTS).
- BinNeg1: la suma de partidos BinNeg1 con el mismo δ es BinNeg1 exacta.
- φ (normal): varianza dentro de jugador entre partidos, por liga-temporada, con los residuos por partido.

Ajuste: la verosimilitud marginal de cada unidad es ∫ L(K_u | η) N(η; μ_r, σ²) dη; se integra **exactamente** en una
rejilla fija de η (paso 0,02 en la escala del enlace), que no depende de los hiperparámetros. Los hiperparámetros
(μ_r, log σ) se maximizan con gradiente analítico (esperanzas posteriores en la rejilla), con un prior débil sobre las
medias de rol, μ_r ~ N(μ_liga, 1²): sin él, un rol casi sin datos (los «X» sin posición, con exposición mínima y casi
todos k = 0) llevaba su media al borde de la rejilla en 362 de 1.294 ajustes (detectado al contrastar con la NUTS en
FEB2, robos). La posterior de cada unidad son los pesos de la rejilla.

La sobredispersión (ρ, δ) **no** se estima por máxima verosimilitud de los totales de temporada: ahí se confunde
con σ² (sólo la separa la forma en que la varianza crece con N, y en simulación sale sesgada al doble). Se estima
por momentos con la variación entre partidos dentro de cada jugador (`dispersion_momentos`), que la identifica.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import optimize, special

PASO = 0.02
ROLES = ["E", "A", "I", "X"]


def roles_de(u: pd.DataFrame) -> list[str]:
    """Etiquetas de grupo de la media a priori: los roles conocidos en su orden y, si las hay, otras (p. ej.
    «2024-25|E» cuando σ se comparte entre las temporadas de una liga y cada temporada tiene sus medias)."""
    vistos = set(u["rol"])
    return [r for r in ROLES if r in vistos] + sorted(vistos - set(ROLES))


# ------------------------------------------------------------------ rejilla y verosimilitud por unidad
def rejilla(K, N, familia: str) -> np.ndarray:
    tasa = (K + 0.5) / (N + 1.0)
    e = special.logit(np.clip(tasa, 1e-4, 1 - 1e-4)) if familia == "binomial" else np.log((K + 0.5) / np.maximum(N, 1e-9))
    lo, hi = np.quantile(e, [0.002, 0.998])
    lo, hi = lo - 2.5, hi + 2.5
    if familia == "binomial":
        lo, hi = max(lo, -9.0), min(hi, 9.0)
    return np.arange(lo, hi + PASO, PASO)


def rho_efectiva(N, N2g, rho: float) -> np.ndarray:
    m = np.where(N > 1, (N2g / np.maximum(N, 1e-9) - 1.0) / np.maximum(N - 1.0, 1e-9), 0.0)
    return np.clip(rho * m, 0.0, 0.999)


def loglik(K, N, N2g, eta, familia: str, disp: float = 0.0) -> np.ndarray:
    """Matriz U × J de log L(K_u | η_j)."""
    K, N, N2g = (np.asarray(x, float)[:, None] for x in (K, N, N2g))
    e = eta[None, :]
    if familia == "binomial":
        lc = special.gammaln(N + 1) - special.gammaln(K + 1) - special.gammaln(N - K + 1)
        if disp <= 0:
            return lc + K * special.log_expit(e) + (N - K) * special.log_expit(-e)
        r = rho_efectiva(N, N2g, disp)
        c = np.where(r > 1e-9, (1 - r) / np.maximum(r, 1e-12), 1e12)
        p = special.expit(e)
        a, b = p * c, (1 - p) * c
        ll = lc + special.betaln(K + a, N - K + b) - special.betaln(a, b)
        binom = lc + K * special.log_expit(e) + (N - K) * special.log_expit(-e)
        return np.where(r > 1e-9, ll, binom)
    mu = N * np.exp(e)
    if disp <= 0:
        return K * np.log(np.maximum(mu, 1e-300)) - mu - special.gammaln(K + 1)
    s = mu / disp
    return (special.gammaln(K + s) - special.gammaln(s) - special.gammaln(K + 1) - s * np.log1p(disp)
            + K * (np.log(disp) - np.log1p(disp)))


# ------------------------------------------------------------------ hiperparámetros (μ_r, σ) dada la verosimilitud
SD_ROL = 1.0     # prior débil de las medias de rol alrededor de la media de la liga: μ_r ~ N(μ_liga, SD_ROL²)


def _marginal(par, LL, eta, idx_rol, nr, mu0=None):
    mu, ls = par[:nr], par[nr]
    s = np.exp(ls)
    z = (eta[None, :] - mu[idx_rol][:, None]) / s
    lp = -0.5 * z ** 2 - ls - 0.5 * np.log(2 * np.pi) + np.log(PASO)
    A = LL + lp
    m = A.max(axis=1, keepdims=True)
    W = np.exp(A - m)
    Z = W.sum(axis=1, keepdims=True)
    lm = (m + np.log(Z))[:, 0]
    W /= Z
    Ez = (W * z).sum(axis=1)
    Ez2 = (W * z ** 2).sum(axis=1)
    g_mu = np.bincount(idx_rol, weights=Ez / s, minlength=nr)
    g_ls = (Ez2 - 1).sum()
    pen = 0.0
    if mu0 is not None:     # sin él, un rol casi sin datos (p. ej. «X» con exposición mínima) se va al borde
        pen = 0.5 * ((mu - mu0) ** 2).sum() / SD_ROL ** 2
        g_mu = g_mu - (mu - mu0) / SD_ROL ** 2
    return -lm.sum() + pen, -np.r_[g_mu, g_ls], W


def ajustar_hiper(LL, eta, idx_rol, nr, x0=None):
    """Máx. de la marginal en (μ_r, log σ). Primero con un solo rol (μ_liga) y después con las medias de rol bajo el
    prior débil μ_r ~ N(μ_liga, SD_ROL²). Devuelve los parámetros, la log-marginal **sin** la penalización y los pesos."""
    b1 = [(eta[0], eta[-1]), (np.log(0.01), np.log(4.0))]
    z = np.zeros(len(idx_rol), int)
    x1 = np.r_[eta[np.argmax(LL.sum(axis=0))], np.log(0.3)]
    r1 = optimize.minimize(lambda p: _marginal(p, LL, eta, z, 1)[:2], x1, jac=True, method="L-BFGS-B", bounds=b1)
    mu_liga = float(r1.x[0])
    if x0 is None:
        x0 = np.r_[np.full(nr, mu_liga), r1.x[1]]
    f = lambda p: _marginal(p, LL, eta, idx_rol, nr, mu_liga)[:2]
    b = [(eta[0], eta[-1])] * nr + [(np.log(0.01), np.log(4.0))]
    r = optimize.minimize(f, x0, jac=True, method="L-BFGS-B", bounds=b)
    nll, _, W = _marginal(r.x, LL, eta, idx_rol, nr)
    return r.x, -nll, W


def dispersion_momentos(u: pd.DataFrame, familia: str) -> float:
    """Sobredispersión dentro de jugador por momentos, con la variación entre partidos de cada unidad.

    Con p̂_u = K/N, la suma de cuadrados SS_u = Σ_g (k_g − n_g p̂_u)² tiene esperanza
        binomial: p q [A_u + ρ B_u],  A_u = N − Σn²/N,  B_u = Σw − 2Σ n w/N + (Σn²/N²) Σw,  w = n(n − 1)
        Poisson:  λ (1 + δ) A_u
    y se despeja ρ (o δ) agregando todas las unidades con G ≥ 2. Se recorta a ≥ 0."""
    x = u[(u["G"] >= 2) & (u["N"] > 0)]
    K, N, Sk2, Skn, N2, N3 = (x[c].to_numpy(float) for c in ("K", "N", "Sk2", "Skn", "N2g", "N3g"))
    p = K / N
    SS = Sk2 - 2 * p * Skn + p ** 2 * N2
    A = N - N2 / N
    if familia == "binomial":
        ok = (p > 0) & (p < 1)
        pq = p * (1 - p)
        Sw = N2 - N
        B = Sw - 2 * (N3 - N2) / N + N2 / N ** 2 * Sw
        num = (SS[ok] - pq[ok] * A[ok]).sum()
        den = (pq[ok] * B[ok]).sum()
        return float(max(num / den, 0.0)) if den > 0 else 0.0
    ok = p > 0
    return float(max(SS[ok].sum() / (p[ok] * A[ok]).sum() - 1.0, 0.0))


def ajustar(u: pd.DataFrame, familia: str, sobredispersion: bool, disp: float | None = None) -> dict:
    """Ajusta una métrica en una liga-temporada. u: K, N, N2g, rol (+ sumas por partido si hay sobredispersión).
    Devuelve hiperparámetros, logL marginal, rejilla y pesos posteriores (U × J)."""
    roles = roles_de(u)
    idx = u["rol"].map({r: i for i, r in enumerate(roles)}).to_numpy()
    K, N, N2g = (u[c].to_numpy(float) for c in ("K", "N", "N2g"))
    eta = rejilla(K, N, familia)
    d = 0.0
    if sobredispersion:
        d = dispersion_momentos(u, familia) if disp is None else float(disp)
    LL = loglik(K, N, N2g, eta, familia, d)
    x, l, W = ajustar_hiper(LL, eta, idx, len(roles))
    return dict(familia=familia, roles=roles, idx=idx, eta=eta, par=x, logL=l, W=W, disp=d)


def resumen_posterior(m: dict) -> pd.DataFrame:
    """Media, sd y cuantiles 10/50/90 de la tasa (p o λ) por unidad."""
    eta, W = m["eta"], m["W"]
    t = special.expit(eta) if m["familia"] == "binomial" else np.exp(eta)
    media = W @ t
    sd = np.sqrt(np.maximum(W @ t ** 2 - media ** 2, 0))
    cw = np.cumsum(W, axis=1)
    q = {f"q{int(100 * a)}": t[np.minimum((cw < a).sum(axis=1), len(t) - 1)] for a in (0.1, 0.5, 0.9)}
    return pd.DataFrame({"media": media, "sd": sd, **q})


def puntos_estabilizacion(m: dict, u: pd.DataFrame) -> dict:
    """n* (exposición con fiabilidad 0,5 de una temporada) implícito en el modelo, a la tasa media de la liga.
    binomial: Var(K/N | p) = p(1−p)(1 + ρ(n̄_g − 1))/N, Var(p) ≈ σ² [p(1−p)]² → n* = (1 + ρ(n̄_g−1)) / (σ² p(1−p)).
    poisson:  Var(K/N | λ) = λ(1+δ)/N, Var(λ) ≈ σ² λ² → n* = (1+δ) / (σ² λ)."""
    nr = len(m["roles"])
    s2 = float(np.exp(m["par"][nr])) ** 2
    t = float(u["K"].sum() / u["N"].sum())
    if m["familia"] == "binomial":
        ng = float(np.median(u["N2g"] / u["N"]))
        return {"tasa_media": t, "sigma": s2 ** 0.5, "n_estab": (1 + m["disp"] * (ng - 1)) / (s2 * t * (1 - t)),
                "n_partido_medio": ng}
    return {"tasa_media": t, "sigma": s2 ** 0.5, "n_estab": (1 + m["disp"]) / (s2 * t), "n_partido_medio": np.nan}


# ------------------------------------------------------------------ familia normal (conjugada)
def ajustar_normal(u: pd.DataFrame) -> dict:
    K, N, G, S2 = (u[c].to_numpy(float) for c in ("K", "N", "G", "S2"))
    ok = G >= 2
    phi = float((S2[ok] - K[ok] ** 2 / N[ok]).sum() / (G[ok] - 1).sum())
    y = K / N
    roles = roles_de(u)
    idx = u["rol"].map({r: i for i, r in enumerate(roles)}).to_numpy()
    nr = len(roles)

    def perfil(lt):
        v = np.exp(lt) + phi / N
        w = 1 / v
        mu = np.bincount(idx, weights=w * y, minlength=nr) / np.bincount(idx, weights=w, minlength=nr)
        return 0.5 * (np.log(v) + (y - mu[idx]) ** 2 / v).sum(), mu
    r = optimize.minimize_scalar(lambda lt: perfil(lt)[0], bounds=(np.log(1e-8), np.log(10 * y.var() + 1e-8)),
                                 method="bounded")
    tau2 = float(np.exp(r.x))
    mu = perfil(r.x)[1]
    prec = N / phi + 1 / tau2
    m_post = (y * N / phi + mu[idx] / tau2) / prec
    return dict(familia="normal", roles=roles, idx=idx, mu=mu, tau2=tau2, phi=phi, m_post=m_post, v_post=1 / prec,
                logL=-r.fun - 0.5 * len(y) * np.log(2 * np.pi))


# ------------------------------------------------------------------ predictiva de la segunda mitad
def muestras_tasa(m: dict, S: int, rng) -> np.ndarray:
    """U × S muestras posteriores de la tasa."""
    if m["familia"] == "normal":
        return m["m_post"][:, None] + np.sqrt(m["v_post"])[:, None] * rng.standard_normal((len(m["m_post"]), S))
    cw = np.cumsum(m["W"], axis=1)
    cw /= cw[:, -1:]
    uu = rng.random((cw.shape[0], S))
    j = np.stack([np.searchsorted(cw[i], uu[i]) for i in range(cw.shape[0])])
    j = np.minimum(j, len(m["eta"]) - 1)
    e = m["eta"][j] + (rng.random(j.shape) - 0.5) * PASO
    return special.expit(e) if m["familia"] == "binomial" else np.exp(e)


def muestras_conteo(tasa: np.ndarray, N2, N2g, familia: str, disp, rng, phi: float = 0.0) -> np.ndarray:
    """U × S muestras de K2 dadas las tasas y las oportunidades de la segunda mitad (se condiciona en ellas).
    disp puede ser un escalar o un vector por unidad."""
    N2 = np.asarray(N2, float)[:, None]
    d = np.broadcast_to(np.asarray(disp, float), (N2.shape[0],))
    if familia == "binomial":
        n = np.round(N2).astype(np.int64)
        p = tasa
        if (d > 0).any():
            r = rho_efectiva(N2[:, 0], np.asarray(N2g, float), d)[:, None]
            c = np.where(r > 1e-9, (1 - r) / np.maximum(r, 1e-12), 0)
            con = (r > 1e-9) & np.ones_like(p, bool)
            a, b = np.maximum(p * c, 1e-9), np.maximum((1 - p) * c, 1e-9)
            p = np.where(con, rng.beta(a, b), p)
        return rng.binomial(np.broadcast_to(n, p.shape), p).astype(float)
    if familia == "poisson":
        mu = N2 * tasa
        if (d > 0).any():
            dd = np.maximum(d, 1e-12)[:, None]
            mu = np.where(d[:, None] > 0, rng.gamma(mu / dd, dd), mu)
        return rng.poisson(mu).astype(float)
    return tasa * N2 + np.sqrt(phi * N2) * rng.standard_normal(tasa.shape)


def evaluar(muestras: np.ndarray, k: np.ndarray, discreta: bool, rng) -> pd.DataFrame:
    """PIT aleatorizado, CRPS (en la escala de las muestras) por unidad."""
    k = np.asarray(k, float)[:, None]
    S = muestras.shape[1]
    menor = (muestras < k - 1e-9).sum(axis=1)
    igual = (np.abs(muestras - k) <= 1e-9).sum(axis=1) if discreta else 0
    pit = (menor + rng.random(len(menor)) * igual) / S
    xs = np.sort(muestras, axis=1)
    i = np.arange(1, S + 1)
    e1 = np.abs(muestras - k).mean(axis=1)
    e2 = ((2 * i - S - 1) * xs).sum(axis=1) / S ** 2
    return pd.DataFrame({"pit": pit, "crps": e1 - e2})
