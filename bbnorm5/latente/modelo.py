"""F5 · Capa latente: modelo factorial dinámico de las 14 métricas (encargo v5.0 §9).

Para cada persona, el vector de capacidades persistentes a_t ∈ R^M (M = 14 métricas, escala del enlace, relativo a la
media de su rol en su liga-temporada, como en la F4) sigue

    y_t = a_t + u_t + e_t,             u_t ~ N(0, diag σ_u²),  e_t ~ N(0, diag c·v_t)          (F4, por métrica)
    a_t = a_{t−1} + Δg(edad) + w_t,     w_t ~ N(0, D_t^{½} C D_t^{½}),  D_t = Δt·σ_η² + cl·σ_L² + cr·σ_R²   (F4)
    a_primera ~ N(κ + g(edad), Σ₀),     Σ₀ = Λ Λᵀ + diag ψ,  Λ ∈ R^{M×K}

- **Lo nuevo de la F5** es Σ₀: la covarianza entre métricas de la capacidad de los jugadores, con K factores comunes
  (Λ, triangular inferior con diagonal positiva para identificarla) más una parte específica de cada métrica (ψ), que
  impide «aplanar» a los especialistas.
- Los cambios entre temporadas tienen la misma correlación C = corr(Σ₀) (variante «corr»): cuando cambia el rol, las
  métricas que van juntas cambian juntas. Variante «diag»: cambios independientes.
- Equivale a a_t = Λ z_t + s_t con z ~ N(0, I) (perfil latente) y s específica: z_t es el perfil del jugador.
- K = 0 es la F4 con métricas independientes (Σ₀ diagonal): la referencia.
- Las métricas que faltan en una temporada (p. ej. T3% sin triples) no se observan y se infieren por la correlación.

Ajuste: verosimilitud exacta del filtro (las 14 métricas a la vez, observadas por máscara), gradiente en JAX, L-BFGS-B;
los parámetros por métrica de la F4 se mantienen fijos y sólo se estiman Λ y ψ.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import optimize

from bbnorm5.carrera import modelo as MC
from bbnorm5.medida import datos as DM

METRICAS = list(DM.METRICAS_BASE)          # las 14 de la F3 (F9 bis añade otras a DM.METRICAS)
GRANDE = 1e6


# ------------------------------------------------------------------ datos en rejilla persona × temporada × métrica
def matrices(o: pd.DataFrame, f4: dict[str, dict]) -> dict:
    """o: observaciones F4 (todas las métricas). f4: modelo F4 por métrica (th, beta). Una fila por persona-temporada
    (liga principal, común a todas las métricas)."""
    o = o[o["metrica"].isin(METRICAS)]
    o = o if "temporada" in o else o.assign(temporada=o["anio"].astype(str))
    base = o.sort_values(["persona_v5", "anio"]).drop_duplicates(["persona_v5", "anio"])[
        ["persona_v5", "anio", "liga", "rol", "edad", "temporada"]].reset_index(drop=True)
    j = base.groupby("persona_v5").cumcount().to_numpy()
    pid, personas = pd.factorize(base["persona_v5"])
    P, T, Mm = len(personas), int(j.max()) + 1, len(METRICAS)
    idx = pd.Series(np.arange(len(base)), index=pd.MultiIndex.from_frame(base[["persona_v5", "anio"]]))
    Y, V, MK = np.zeros((P, T, Mm)), np.ones((P, T, Mm)), np.zeros((P, T, Mm), bool)
    for m, met in enumerate(METRICAS):
        x = o[o["metrica"] == met]
        r = idx.reindex(pd.MultiIndex.from_frame(x[["persona_v5", "anio"]])).to_numpy()
        ok = ~np.isnan(r)
        r = r[ok].astype(int)
        Y[pid[r], j[r], m] = x["y"].to_numpy()[ok]
        V[pid[r], j[r], m] = x["v"].to_numpy()[ok]
        MK[pid[r], j[r], m] = True
    prev = base.groupby("persona_v5")[["anio", "liga", "rol"]].shift()
    S = {"y": Y, "v": V, "mask": MK, "obs": np.zeros((P, T), bool)}
    for k in ("gap", "cl", "cr"):
        S[k] = np.zeros((P, T))
    S["obs"][pid, j] = True
    S["gap"][pid, j] = (base["anio"] - prev["anio"]).fillna(0).to_numpy()
    S["cl"][pid, j] = (prev["liga"].notna() & (base["liga"] != prev["liga"])).to_numpy(float)
    S["cr"][pid, j] = (prev["rol"].notna() & (base["rol"] != prev["rol"])).to_numpy(float)
    # g(edad) por métrica con la curva de la F4
    G = np.zeros((P, T, Mm))
    B = MC.base_edad(base["edad"].to_numpy(float))
    for m, met in enumerate(METRICAS):
        G[pid, j, m] = B @ f4[met]["beta"][:B.shape[1]]
    S["g"] = G
    S["personas"], S["fila"], S["base"] = personas, (pid, j), base
    # parámetros F4 por métrica
    th = {k: np.array([f4[m]["th"].get(k, -30.0 if k.startswith("log_s") else 0.0) for m in METRICAS])
          for k in MC.PARAMS}
    S["s2"] = {k: np.exp(2 * th[f"log_s_{k}"]) for k in ("eta", "u", "L", "R")}
    S["c"], S["kappa"], S["tau0"] = np.exp(th["log_c"]), th["kappa"], np.exp(th["log_tau0"])
    S["f4beta"] = [f4[m]["beta"] for m in METRICAS]
    return S


# ------------------------------------------------------------------ parámetros
def n_libres(K: int) -> int:
    Mm = len(METRICAS)
    return Mm * K - K * (K - 1) // 2


def desempaquetar(x: np.ndarray, K: int, kr: int = 0):
    """x → (Λ triangular inferior con diagonal positiva, ψ[, Λ_r]). Λ_r (M × kr) da la correlación del residuo de la
    temporada (transitorio + muestreo) entre métricas: C_r = normaliza(Λ_r Λ_rᵀ + I)."""
    import jax.numpy as jnp
    Mm = len(METRICAS)
    nl = n_libres(K)
    L = jnp.zeros((Mm, K))
    if K:
        filas, cols = _indices_tril(Mm, K)
        L = L.at[filas, cols].set(x[:nl])
        d = np.arange(K)
        L = L.at[d, d].set(jnp.exp(L[d, d]))
    psi = jnp.exp(2 * x[nl:nl + Mm])
    if kr:
        f, c = _indices_tril(Mm, kr)
        Lr = jnp.zeros((Mm, kr)).at[f, c].set(x[nl + Mm:nl + Mm + n_libres(kr)])
        return L, psi, Lr
    return L, psi


def _indices_tril(Mm: int, K: int):
    f, c = [], []
    for i in range(Mm):
        for k in range(min(i + 1, K)):
            f.append(i), c.append(k)
    return np.array(f), np.array(c)


# ------------------------------------------------------------------ filtro (JAX; también para predecir)
def _corr_residuo(Lr):
    import jax.numpy as jnp
    A = Lr @ Lr.T + jnp.eye(Lr.shape[0])
    d = jnp.sqrt(jnp.diag(A))
    return A / (d[:, None] * d[None, :])


def _filtro(S: dict, L, psi, cambios: str, devolver: bool = False, Lr=None):
    import jax
    import jax.numpy as jnp
    Sig0 = L @ L.T + jnp.diag(psi)
    sd0 = jnp.sqrt(jnp.diag(Sig0))
    C = Sig0 / (sd0[:, None] * sd0[None, :]) if cambios == "corr" else jnp.eye(Sig0.shape[0])
    se, su, sL, sR = (jnp.asarray(S["s2"][k]) for k in ("eta", "u", "L", "R"))
    c, kappa = jnp.asarray(S["c"]), jnp.asarray(S["kappa"])
    Y, V, MK = (jnp.asarray(np.swapaxes(S[k], 0, 1)) for k in ("y", "v", "mask"))
    G = jnp.asarray(np.swapaxes(S["g"], 0, 1))
    OB = jnp.asarray(S["obs"].T)
    gap, cl, cr = (jnp.asarray(S[k].T) for k in ("gap", "cl", "cr"))
    P_, Mm = Y.shape[1], Y.shape[2]
    I = jnp.eye(Mm)
    Cr = None if Lr is None else _corr_residuo(Lr)

    def paso(carry, xs):
        a, Pm, gp, ll, t = carry
        y, v, mk, g, ob, gt, clt, crt = xs
        ap = jnp.where(t == 0, kappa[None] + g, a + g - gp)
        D = gt[:, None] * se[None] + clt[:, None] * sL[None] + crt[:, None] * sR[None]
        Q = jnp.sqrt(D)[:, :, None] * C[None] * jnp.sqrt(D)[:, None, :]
        Pp = jnp.where(t == 0, Sig0[None], Pm + Q)
        mkf = mk.astype(Pp.dtype)
        R = su[None] + c[None] * v
        if Cr is None:
            Sm = Pp + jnp.eye(Mm)[None] * R[:, :, None]
        else:
            sr = jnp.sqrt(R)
            Sm = Pp + sr[:, :, None] * Cr[None] * sr[:, None, :]
        Sm = Sm * mkf[:, :, None] * mkf[:, None, :] + (1 - mkf)[:, :, None] * I[None]
        r = (y - ap) * mkf
        Lc = jnp.linalg.cholesky(Sm)
        sol = jax.scipy.linalg.cho_solve((Lc, True), r[..., None])[..., 0]
        logdet = 2 * jnp.log(jnp.diagonal(Lc, axis1=1, axis2=2)).sum(-1)
        nobs = mkf.sum(-1)
        lli = -0.5 * (logdet + (r * sol).sum(-1) + nobs * jnp.log(2 * jnp.pi))
        ll = ll + jnp.where(ob, lli, 0.0)
        PM = Pp * mkf[:, None, :]                                    # P Hᵀ (columnas observadas)
        Kg = jax.scipy.linalg.cho_solve((Lc, True), jnp.swapaxes(PM, 1, 2))   # S⁻¹ H P
        Kg = jnp.swapaxes(Kg, 1, 2) * mkf[:, None, :]
        an = ap + (Kg @ r[..., None])[..., 0]
        Pn = Pp - Kg @ (Pp * mkf[:, :, None])
        Pn = 0.5 * (Pn + jnp.swapaxes(Pn, 1, 2))
        a = jnp.where(ob[:, None], an, a)
        Pm = jnp.where(ob[:, None, None], Pn, Pm)
        gp = jnp.where(ob[:, None], g, gp)
        out = (a, Pm, ap, Pp) if devolver else None
        return (a, Pm, gp, ll, t + 1), out
    z = jnp.zeros((P_, Mm))
    Z = jnp.zeros((P_, Mm, Mm))
    (a, Pm, gp, ll, _), hist = jax.lax.scan(paso, (z, Z, z, jnp.zeros(P_), 0), (Y, V, MK, G, OB, gap, cl, cr))
    return ll, (a, Pm, gp, hist)


def ajustar(S: dict, K: int, cambios: str = "corr", x0: np.ndarray | None = None, maxiter: int = 400,
            kr: int = 0) -> dict:
    import jax
    import jax.numpy as jnp
    jax.config.update("jax_enable_x64", True)
    Mm = len(METRICAS)
    if x0 is None:
        x0 = inicial(S, K)
        if kr:     # Λ_r = 0 es un punto de silla (entra al cuadrado): se arranca de un valor pequeño al azar
            x0 = np.r_[x0, 0.3 * np.random.default_rng(K + 17 * kr).standard_normal(n_libres(kr))]

    def nll(x):
        par = desempaquetar(x, K, kr)
        ll, _ = _filtro(S, par[0], par[1], cambios, Lr=par[2] if kr else None)
        return -ll.sum()
    f = jax.jit(jax.value_and_grad(nll))
    fun = lambda x: tuple(np.asarray(z, dtype=float) for z in f(jnp.asarray(x)))
    nl = n_libres(K)
    b = [(-5.0, 5.0)] * nl + [(np.log(1e-3), np.log(5.0))] * Mm + [(-5.0, 5.0)] * n_libres(kr)
    r = optimize.minimize(fun, x0, jac=True, method="L-BFGS-B", bounds=b, options={"maxiter": maxiter})
    par = desempaquetar(jnp.asarray(r.x), K, kr)
    return {"K": K, "kr": kr, "cambios": cambios, "x": r.x, "L": np.asarray(par[0]), "psi": np.asarray(par[1]),
            "Lr": np.asarray(par[2]) if kr else None, "logL": -float(r.fun),
            "convergio": bool(r.success), "n_par": nl + Mm + n_libres(kr), "iter": int(r.nit)}


def inicial(S: dict, K: int) -> np.ndarray:
    """Arranque: Σ₀ empírica de las primeras temporadas con mucha exposición (covarianza de y menos el ruido medio),
    descompuesta en sus K primeros vectores propios; ψ el resto de la diagonal."""
    Y, V, MK = S["y"][:, 0], S["v"][:, 0], S["mask"][:, 0]
    Mm = len(METRICAS)
    ok = MK.all(axis=1)
    Ys = Y[ok] - S["kappa"]
    Cv = np.cov(Ys.T) - np.diag((S["s2"]["u"] + S["c"] * V[ok]).mean(axis=0))
    w, U = np.linalg.eigh(Cv)
    w = np.maximum(w, 1e-4)
    d = np.sqrt(np.maximum(np.diag(Cv), 1e-3))
    if K:
        L = U[:, ::-1][:, :K] * np.sqrt(w[::-1][:K])
        Qr, _ = np.linalg.qr(L[:K].T)           # rota Λ para que su bloque K × K superior sea triangular inferior
        L = L @ Qr
        L = L * np.sign(np.diag(L[:K, :K]))[None]
        psi = np.maximum(np.diag(Cv) - (L ** 2).sum(1), 0.05 * d ** 2)
        f, c = _indices_tril(Mm, K)
        lv = L[f, c].copy()
        dd = np.where(f == c)[0]
        lv[dd] = np.log(np.maximum(np.abs(L[f[dd], c[dd]]), 1e-3))
        return np.r_[lv, 0.5 * np.log(psi)]
    return 0.5 * np.log(np.maximum(np.diag(Cv), 1e-3))


# ------------------------------------------------------------------ predicción para el examen
def predecir(S_hist: dict, mod: dict, objetivo: pd.DataFrame) -> pd.DataFrame:
    """Para cada persona con historial: media y varianza del nivel persistente en la temporada objetivo, por métrica.
    objetivo: persona_v5, edad, gap, cl, cr (una fila por persona)."""
    import jax.numpy as jnp
    L, psi = jnp.asarray(mod["L"]), jnp.asarray(mod["psi"])
    Lr = None if mod.get("Lr") is None else jnp.asarray(mod["Lr"])
    _, (a, Pm, gp, _) = _filtro(S_hist, L, psi, mod["cambios"], Lr=Lr)
    a, Pm, gp = np.asarray(a), np.asarray(Pm), np.asarray(gp)
    x = objetivo.set_index("persona_v5")
    pos = pd.Series(np.arange(len(S_hist["personas"])), index=S_hist["personas"])
    i = pos.reindex(x.index).to_numpy()
    ok = ~np.isnan(i)
    i = i[ok].astype(int)
    x = x[ok]
    Sig0 = mod["L"] @ mod["L"].T + np.diag(mod["psi"])
    sd0 = np.sqrt(np.diag(Sig0))
    C = Sig0 / np.outer(sd0, sd0) if mod["cambios"] == "corr" else np.eye(len(sd0))
    D = (x["gap"].to_numpy()[:, None] * S_hist["s2"]["eta"][None] + x["cl"].to_numpy()[:, None] * S_hist["s2"]["L"][None]
         + x["cr"].to_numpy()[:, None] * S_hist["s2"]["R"][None])
    B = MC.base_edad(x["edad"].to_numpy(float))
    gT = np.stack([B @ S_hist["f4beta"][m][:B.shape[1]] for m in range(len(METRICAS))], axis=1)
    m_niv = a[i] + gT - gp[i]
    v_niv = np.einsum("pmm->pm", Pm[i]) + D        # varianza marginal por métrica (diagonal de P + Q)
    return pd.DataFrame({"persona_v5": x.index.repeat(len(METRICAS)), "metrica": np.tile(METRICAS, len(x)),
                         "m_nivel": m_niv.ravel(), "v_nivel": v_niv.ravel(),
                         "v_y_sin_muestreo": (v_niv + S_hist["s2"]["u"][None]).ravel()})


def puntuaciones(S: dict, mod: dict) -> pd.DataFrame:
    """Perfil latente z por persona-temporada: E[z | a filtrado] = Λᵀ Σ₀⁻¹ (a − κ − g), con su covarianza."""
    import jax.numpy as jnp
    L, psi = mod["L"], mod["psi"]
    K = L.shape[1]
    Lr = None if mod.get("Lr") is None else jnp.asarray(mod["Lr"])
    _, (_, _, _, hist) = _filtro(S, jnp.asarray(L), jnp.asarray(psi), mod["cambios"], devolver=True, Lr=Lr)
    a_f = np.asarray(hist[0])           # T × P × M (estado filtrado tras cada temporada)
    Sig0 = L @ L.T + np.diag(psi)
    W = L.T @ np.linalg.inv(Sig0)        # K × M
    pid, j = S["fila"]
    a = a_f[j, pid] - S["kappa"][None] - S["g"][pid, j]
    z = a @ W.T
    out = S["base"][["persona_v5", "temporada", "liga", "rol", "edad"]].copy()
    for k in range(K):
        out[f"z{k + 1}"] = z[:, k]
    return out


def submuestra(S: dict, n: int, rng) -> dict:
    """Submuestra de personas para estimar Λ y ψ (el filtro y las predicciones usan a todas)."""
    P_ = S["y"].shape[0]
    if n >= P_:
        return S
    i = np.sort(rng.choice(P_, n, replace=False))
    out = {k: (v[i] if isinstance(v, np.ndarray) and v.shape[:1] == (P_,) else v) for k, v in S.items()}
    out["personas"] = S["personas"][i]
    return out


def varimax(L: np.ndarray, iters: int = 200, tol: float = 1e-8) -> tuple[np.ndarray, np.ndarray]:
    """Rotación varimax de las cargas (para interpretar); devuelve (Λ rotada, matriz de rotación)."""
    p, k = L.shape
    R = np.eye(k)
    d = 0.0
    for _ in range(iters):
        Lr = L @ R
        u, s, vt = np.linalg.svd(L.T @ (Lr ** 3 - Lr @ np.diag((Lr ** 2).sum(0)) / p))
        R = u @ vt
        d_new = s.sum()
        if d_new < d * (1 + tol):
            break
        d = d_new
    Lr = L @ R
    sg = np.sign(Lr.sum(0) + 1e-12)           # signo: que la suma de cargas de cada factor sea positiva
    return Lr * sg, R * sg


def alinear(L: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """Permutación con signo P (k × k) que lleva las columnas de L a las de `ref` (máxima |congruencia de Tucker| por
    pares, asignación húngara). El factorial sólo está identificado salvo orden y signo: sin esto, una semilla distinta
    puede intercambiar z2 y z3 y cambiar su significado."""
    from scipy.optimize import linear_sum_assignment
    num = ref.T @ L
    den = np.sqrt(np.outer((ref ** 2).sum(0), (L ** 2).sum(0)))
    C = num / den
    fila, col = linear_sum_assignment(-np.abs(C))
    P = np.zeros((L.shape[1], ref.shape[1]))
    for i, j in zip(fila, col):
        P[j, i] = np.sign(C[i, j]) or 1.0
    return P


def congruencia(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Congruencia de Tucker por factor tras alinear B con A (Procrustes ortogonal)."""
    u, _, vt = np.linalg.svd(B.T @ A)
    Bt = B @ (u @ vt)
    return (A * Bt).sum(0) / np.sqrt((A ** 2).sum(0) * (Bt ** 2).sum(0))
