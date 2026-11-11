"""F4.2 · Modelo de carrera: filtro de Kalman por jugador, en la escala del enlace y relativo a su liga-temporada-rol.

Para cada métrica, la posición relativa observada de la persona i en la temporada t (F4.1) es

    y_it = a_it + u_it + e_it,      e_it ~ N(0, c·v_it)   (muestreo, de la F3)     u_it ~ N(0, σ_u²) (transitorio)
    a_it = a_i,t−1 + g(edad_it) − g(edad_i,t−1) + w_it,
    w_it ~ N(0, Δt·σ_η² + 1[cambia de liga]·σ_L² + 1[cambia de rol]·σ_R²)
    a_i,primera ~ N(κ + g(edad), τ₀²)

- a: capacidad persistente (lo que se arrastra de una temporada a otra); u: lo propio de una temporada que no se
  arrastra (contexto, compañeros, suerte de rol); Δt: años desde la última observación.
- g: curva de edad común, B-spline cúbico con g(26) = 0 y penalización de segundas diferencias (P-spline) o con prior
  de proceso gaussiano RBF sobre los coeficientes (variante «gp»).
- El peso que recibe cada temporada pasada lo **aprende** el modelo: es la ganancia de Kalman, que depende de la
  antigüedad (Δt·σ_η²), de la edad (g), del cambio de rol y de liga (σ_R², σ_L²), de la exposición (v) y de σ_u².

Variantes (todas con el mismo filtro):
- `solo_ultima`: sólo la última temporada, sin cambio esperado (la capa de medida sola).
- `solo_ultima_deriva`: lo anterior + la varianza de cambio que implica la deriva entre mitades de la F3.
- `deriva`: historial completo, paseo aleatorio con σ_η² = 2·τ²_d (la deriva de media temporada de la F3, llevada a
  una temporada), sin σ_u, sin edad ni cambios. Es el modelo «de la deriva» que pidió el usuario evaluar.
- `d1`: estructura de la v4.2 D1 (paseo aleatorio con σ_η² y escala c de la varianza de observación libres).
- `completo`: todo lo anterior libre, con la edad en P-spline; `completo_gp`: con la edad en GP.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
from scipy import optimize
from scipy.interpolate import BSpline

EDAD_REF = 26.0
NUDOS = np.arange(15.0, 46.0, 3.0)
GRADO = 3
PARAMS = ["log_s_eta", "log_s_u", "log_s_L", "log_s_R", "log_tau0", "kappa", "log_c", "phi_rol"]
ROLES_EDAD = ["E", "A", "I", "X"]
LAM_ROL = 50.0      # contracción de las curvas por rol hacia la común (P-spline con λ 5 veces mayor)


# ------------------------------------------------------------------ edad
def base_edad(edad: np.ndarray) -> np.ndarray:
    """Matriz B-spline (n × nb) con g(EDAD_REF) = 0 (se resta la fila de la edad de referencia)."""
    t = np.r_[[NUDOS[0]] * GRADO, NUDOS, [NUDOS[-1]] * GRADO]
    nb = len(t) - GRADO - 1
    e = np.clip(np.nan_to_num(edad, nan=EDAD_REF), NUDOS[0], NUDOS[-1] - 1e-6)
    B = BSpline.design_matrix(e, t, GRADO).toarray()
    r = BSpline.design_matrix(np.array([EDAD_REF]), t, GRADO).toarray()
    return B - r


def n_base() -> int:
    return len(NUDOS) + GRADO - 1


def penalizacion(tipo: str, nb: int, lam: float = 10.0, escala_gp: float = 0.4, long_gp: float = 6.0) -> np.ndarray:
    """Matriz Q de la penalización ½ βᵀQβ: P-spline (λ·D₂ᵀD₂) o GP (K⁻¹ con K RBF sobre los centros de las bases)."""
    if tipo == "pspline_rol":     # β común + desviación por rol, contraída con λ·LAM_ROL/10
        Qc = penalizacion("pspline", nb, lam)
        Qr = penalizacion("pspline", nb, LAM_ROL) + 1.0 * np.eye(nb)
        return np.block([[Qc, np.zeros((nb, 4 * nb))], [np.zeros((4 * nb, nb)), np.kron(np.eye(4), Qr)]])
    if tipo == "gp":
        c = np.linspace(NUDOS[0], NUDOS[-1], nb)
        K = escala_gp ** 2 * np.exp(-0.5 * (c[:, None] - c[None, :]) ** 2 / long_gp ** 2) + 1e-6 * np.eye(nb)
        return np.linalg.inv(K)
    D2 = np.diff(np.eye(nb), n=2, axis=0)
    return lam * D2.T @ D2 + 1e-4 * np.eye(nb)


# ------------------------------------------------------------------ datos en rejilla persona × temporada
def matrices(o: pd.DataFrame) -> dict:
    """Ordena las observaciones de una métrica en matrices P × T (persona × orden de temporada), con máscara."""
    o = o.sort_values(["persona_v5", "anio"]).reset_index(drop=True)
    j = o.groupby("persona_v5").cumcount().to_numpy()
    pid, personas = pd.factorize(o["persona_v5"])
    P, T = len(personas), int(j.max()) + 1
    M = {k: np.zeros((P, T)) for k in ("y", "v", "gap", "cl", "cr", "dmu")}
    M["mask"] = np.zeros((P, T), bool)
    M["B"] = np.zeros((P, T, n_base()))
    B = base_edad(o["edad"].to_numpy(float))
    prev_anio = o.groupby("persona_v5")["anio"].shift()
    prev_liga = o.groupby("persona_v5")["liga"].shift()
    prev_rol = o.groupby("persona_v5")["rol"].shift()
    M["y"][pid, j] = o["y"]
    M["v"][pid, j] = o["v"]
    M["gap"][pid, j] = (o["anio"] - prev_anio).fillna(0).to_numpy()
    M["cl"][pid, j] = (prev_liga.notna() & (o["liga"] != prev_liga)).to_numpy(float)
    M["cr"][pid, j] = (prev_rol.notna() & (o["rol"] != prev_rol)).to_numpy(float)
    # cambio de rol: diferencia entre la media del rol anterior y la del nuevo en la liga-temporada actual. Con φ = 1 se
    # conserva el nivel absoluto; con φ = 0, la posición relativa (auditoría de la puerta F5: el paso «X» → «I»)
    if all(f"mu_{r}" in o for r in ROLES_EDAD):
        mus = o[[f"mu_{r}" for r in ROLES_EDAD]].to_numpy(float)
        ip = prev_rol.map({r: i for i, r in enumerate(ROLES_EDAD)})
        mprev = np.where(ip.notna(), mus[np.arange(len(o)), ip.fillna(0).astype(int)], np.nan)
        dmu = np.where(M["cr"][pid, j] > 0, mprev - o["mu"].to_numpy(float), 0.0)
        M["dmu"][pid, j] = np.nan_to_num(dmu)
    M["mask"][pid, j] = True
    M["B"][pid, j] = B
    M["rol"] = np.zeros((P, T), int)
    M["rol"][pid, j] = o["rol"].map({r: i for i, r in enumerate(ROLES_EDAD)}).fillna(3).to_numpy(int)
    M["personas"], M["fila"] = personas, (pid, j)
    return M


# ------------------------------------------------------------------ filtro (numpy, vectorizado sobre personas)
def _g(M: dict, beta: np.ndarray) -> np.ndarray:
    """g(edad) por celda: β común (nb) o β común + desviación por rol (nb·(1 + 4))."""
    nb = M["B"].shape[-1]
    if len(beta) == nb:
        return M["B"] @ beta
    b = beta[:nb][None, :] + beta[nb:].reshape(len(ROLES_EDAD), nb)[M["rol"]]
    return (M["B"] * b).sum(-1)


def _var(th: dict) -> dict:
    return {k: (np.exp(2 * th[f"log_s_{k}"]) if f"log_s_{k}" in th else 0.0) for k in ("eta", "u", "L", "R")}


def filtrar(M: dict, th: dict, beta: np.ndarray):
    """Filtro de Kalman. Devuelve la log-verosimilitud por persona y, por celda, la predicción (media, var) de y
    antes de verla y el estado filtrado (a, P) después."""
    s2 = _var(th)
    tau0, kappa, c = np.exp(2 * th["log_tau0"]), th["kappa"], np.exp(th["log_c"])
    P_, T = M["y"].shape
    g = _g(M, beta)
    a = np.zeros(P_)
    Pv = np.zeros(P_)
    g_prev = np.zeros(P_)
    ll = np.zeros(P_)
    out = {k: np.full((P_, T), np.nan) for k in ("m_pred", "s_pred", "a", "P", "P_pred")}
    for t in range(T):
        m = M["mask"][:, t]
        primera = m & (t == 0)
        ap = np.where(t == 0, kappa + g[:, t], a + g[:, t] - g_prev + th.get("phi_rol", 0.0) * M["dmu"][:, t])
        Pp = np.where(t == 0, tau0, Pv + M["gap"][:, t] * s2["eta"] + M["cl"][:, t] * s2["L"] + M["cr"][:, t] * s2["R"])
        S = Pp + s2["u"] + c * M["v"][:, t]
        r = M["y"][:, t] - ap
        ll += np.where(m, -0.5 * (np.log(2 * np.pi * S) + r ** 2 / S), 0.0)
        K = Pp / S
        out["m_pred"][:, t] = np.where(m, ap, np.nan)
        out["s_pred"][:, t] = np.where(m, S, np.nan)
        out["P_pred"][:, t] = np.where(m, Pp, np.nan)
        a = np.where(m, ap + K * r, a)
        Pv = np.where(m, (1 - K) * Pp, Pv)
        g_prev = np.where(m, g[:, t], g_prev)
        out["a"][:, t] = np.where(m, a, np.nan)
        out["P"][:, t] = np.where(m, Pv, np.nan)
        del primera
    return ll, out


# ------------------------------------------------------------------ ajuste (JAX para el gradiente)
def _nll_jax(M: dict, libres: list[str], fijos: dict, Q: np.ndarray | None):
    os.environ.setdefault("JAX_ENABLE_X64", "1")
    import jax
    import jax.numpy as jnp
    jax.config.update("jax_enable_x64", True)
    y, v, gap, cl, cr, dmu = (jnp.asarray(M[k].T) for k in ("y", "v", "gap", "cl", "cr", "dmu"))
    mask = jnp.asarray(M["mask"].T)
    B = jnp.asarray(np.transpose(M["B"], (1, 0, 2)))
    R = jnp.asarray(M["rol"].T)
    nb = M["B"].shape[-1]
    usa_edad = Q is not None
    por_rol = usa_edad and Q.shape[0] > nb
    Qj = jnp.asarray(Q) if usa_edad else None

    def nll(x):
        th = dict(fijos)
        for i, k in enumerate(libres):
            th[k] = x[i]
        beta = x[len(libres):] if usa_edad else jnp.zeros(nb)
        if por_rol:
            bmat = beta[:nb][None, :] + beta[nb:].reshape(len(ROLES_EDAD), nb)
        se = jnp.exp(2 * th["log_s_eta"]) if "log_s_eta" in th else 0.0
        su = jnp.exp(2 * th["log_s_u"]) if "log_s_u" in th else 0.0
        sL = jnp.exp(2 * th["log_s_L"]) if "log_s_L" in th else 0.0
        sR = jnp.exp(2 * th["log_s_R"]) if "log_s_R" in th else 0.0
        tau0, kappa, c = jnp.exp(2 * th["log_tau0"]), th["kappa"], jnp.exp(th["log_c"])
        phi = th.get("phi_rol", 0.0)

        def paso(carry, xs):
            a, Pv, gp, ll, t = carry
            yt, vt, gt_, clt, crt, mt, Bt, Rt, dmt = xs
            g = (Bt * bmat[Rt]).sum(-1) if por_rol else Bt @ beta
            ap = jnp.where(t == 0, kappa + g, a + g - gp + phi * dmt)
            Pp = jnp.where(t == 0, tau0, Pv + gt_ * se + clt * sL + crt * sR)
            S = Pp + su + c * vt
            r = yt - ap
            ll = ll + jnp.where(mt, -0.5 * (jnp.log(2 * jnp.pi * S) + r ** 2 / S), 0.0)
            K = Pp / S
            a = jnp.where(mt, ap + K * r, a)
            Pv = jnp.where(mt, (1 - K) * Pp, Pv)
            gp = jnp.where(mt, g, gp)
            return (a, Pv, gp, ll, t + 1), None
        n = y.shape[1]
        z = jnp.zeros(n)
        (_, _, _, ll, _), _ = jax.lax.scan(paso, (z, z, z, z, 0), (y, v, gap, cl, cr, mask, B, R, dmu))
        pen = 0.5 * beta @ Qj @ beta if usa_edad else 0.0
        return -ll.sum() + pen
    f = jax.jit(jax.value_and_grad(nll))
    fun = lambda x: tuple(np.asarray(z, dtype=float) for z in f(jnp.asarray(x)))
    fun.hessiana = lambda x: np.asarray(jax.hessian(nll)(jnp.asarray(x)), dtype=float)
    return fun


VARIANTES = {
    # libres, usa edad (tipo de penalización)
    "d1": (["log_s_eta", "log_tau0", "log_c"], None),
    "completo": (["log_s_eta", "log_s_u", "log_s_L", "log_s_R", "log_tau0", "kappa", "log_c", "phi_rol"], "pspline"),
    "completo_gp": (["log_s_eta", "log_s_u", "log_s_L", "log_s_R", "log_tau0", "kappa", "log_c", "phi_rol"], "gp"),
    "completo_sin_edad": (["log_s_eta", "log_s_u", "log_s_L", "log_s_R", "log_tau0", "kappa", "log_c", "phi_rol"], None),
    "completo_rol": (["log_s_eta", "log_s_u", "log_s_L", "log_s_R", "log_tau0", "kappa", "log_c", "phi_rol"], "pspline_rol"),
}


def ajustar(M: dict, variante: str, tau0_ini: float, con_hessiana: bool = False) -> dict:
    libres, edad = VARIANTES[variante]
    fijos = {"kappa": 0.0, "log_c": 0.0, "phi_rol": 0.0}
    nb = n_base()
    Q = penalizacion(edad, nb) if edad else None
    nq = Q.shape[0] if edad else 0
    x0 = {"log_s_eta": np.log(0.3 * tau0_ini), "log_s_u": np.log(0.3 * tau0_ini), "log_s_L": np.log(0.3 * tau0_ini),
          "log_s_R": np.log(0.3 * tau0_ini), "log_tau0": np.log(tau0_ini), "kappa": 0.0, "log_c": 0.0,
          "phi_rol": 0.5}
    x = np.r_[[x0[k] for k in libres], np.zeros(nq)]
    f = _nll_jax(M, libres, fijos, Q)
    lim = {"log_c": (np.log(0.05), np.log(5.0)), "kappa": (-3.0, 3.0), "phi_rol": (-0.5, 1.5)}
    b = [lim.get(k, (np.log(1e-4), np.log(10.0))) for k in libres] + [(-5.0, 5.0)] * nq
    r = optimize.minimize(f, x, jac=True, method="L-BFGS-B", bounds=b, options={"maxiter": 2000})
    th = dict(fijos)
    th.update({k: float(r.x[i]) for i, k in enumerate(libres)})
    beta = np.asarray(r.x[len(libres):]) if edad else np.zeros(nb)
    ll, _ = filtrar(M, th, beta)
    out = {"variante": variante, "th": th, "beta": beta, "logL": float(ll.sum()), "nll_pen": float(r.fun),
           "convergio": bool(r.success), "n_par": len(libres), "Q": Q, "x": r.x, "libres": libres}
    if con_hessiana:
        H = f.hessiana(r.x)
        out["cov"] = np.linalg.pinv(H)
    return out


def fijo(variante: str, sigma_eta2: float, tau0: float) -> dict:
    """Variantes sin ajuste (de la F3): `deriva` (paseo aleatorio con σ_η² = 2τ²_d) y las de «sólo la última»."""
    th = {"log_tau0": 0.5 * np.log(tau0 ** 2), "kappa": 0.0, "log_c": 0.0}
    if sigma_eta2 > 0:
        th["log_s_eta"] = 0.5 * np.log(sigma_eta2)
    return {"variante": variante, "th": th, "beta": np.zeros(n_base()), "n_par": 0}


def predecir(M_hist: dict, mod: dict, objetivo: pd.DataFrame, solo_ultima: bool = False) -> pd.DataFrame:
    """Predicción de y en la temporada objetivo para cada persona con historial: media y varianza predictivas del
    nivel persistente (sin el transitorio ni el muestreo) y la varianza total de y (con σ_u², sin el muestreo de la
    temporada objetivo, que se simula aparte con sus oportunidades)."""
    th, beta = mod["th"], mod["beta"]
    s2 = _var(th)
    M = M_hist
    if solo_ultima:     # sólo la última temporada observada de cada persona
        last = M["mask"].sum(axis=1) - 1
        P_, T = M["y"].shape
        M = {k: (np.zeros((P_, 1, M[k].shape[-1])) if k == "B" else np.zeros((P_, 1), int if k == "rol" else float))
             for k in ("y", "v", "gap", "cl", "cr", "dmu", "B", "rol")}
        idx = np.arange(P_)
        for k in ("y", "v", "B", "rol"):
            M[k][:, 0] = M_hist[k][idx, last]
        M["mask"] = np.ones((P_, 1), bool)
        M["personas"] = M_hist["personas"]
    _, out = filtrar(M, th, beta)
    last = M["mask"].sum(axis=1) - 1
    idx = np.arange(len(last))
    a, P = out["a"][idx, last], out["P"][idx, last]
    g_last = _g(M, beta)[idx, last]
    hist = pd.DataFrame({"persona_v5": M["personas"], "a": a, "P": P, "g_last": g_last,
                         "temporadas_hist": M["mask"].sum(axis=1)})
    x = objetivo.merge(hist, on="persona_v5")
    Bt = base_edad(x["edad"].to_numpy(float))
    nb = Bt.shape[1]
    if len(beta) == nb:
        gT = Bt @ beta
    else:
        ri = x["rol"].map({r: i for i, r in enumerate(ROLES_EDAD)}).fillna(3).to_numpy(int)
        gT = (Bt * (beta[:nb][None, :] + beta[nb:].reshape(len(ROLES_EDAD), nb)[ri])).sum(-1)
    var_w = (x["gap"] * s2["eta"] + x["cl"] * s2["L"] + x["cr"] * s2["R"]).to_numpy(float)
    dmu = x["dmu"].to_numpy(float) if "dmu" in x else 0.0
    x["m_nivel"] = x["a"] + gT - x["g_last"] + th.get("phi_rol", 0.0) * dmu
    x["v_nivel"] = x["P"] + var_w
    x["v_y_sin_muestreo"] = x["v_nivel"] + s2["u"]
    return x


# ------------------------------------------------------------------ curva de edad con bandas
def curva_edad(mod: dict, edades=np.arange(18, 39)) -> pd.DataFrame:
    """g(edad) con banda del 80 % (Laplace: inversa de la hessiana de la verosimilitud penalizada en β)."""
    B = base_edad(edades.astype(float))
    nb = B.shape[1]
    k = len(mod["libres"])
    beta, cov = mod["beta"], mod["cov"][k:, k:]
    filas = []
    for r, bloques in [("todos", None)] + ([(rr, i) for i, rr in enumerate(ROLES_EDAD)] if len(beta) > nb else []):
        if bloques is None:
            L = np.c_[B, np.zeros((len(edades), len(beta) - nb))]
        else:
            L = np.zeros((len(edades), len(beta)))
            L[:, :nb] = B
            L[:, nb * (1 + bloques): nb * (2 + bloques)] = B
        g = L @ beta
        sd = np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", L, cov, L), 0))
        filas.append(pd.DataFrame({"rol": r, "edad": edades, "g": g, "lo80": g - 1.2816 * sd, "hi80": g + 1.2816 * sd}))
    return pd.concat(filas, ignore_index=True)


# ------------------------------------------------------------------ examen por simulación
def simular(M: dict, mod: dict, rng) -> dict:
    """Simula carreras con el diseño real (mismas personas, edades, saltos, cambios y varianzas de muestreo) y los
    parámetros ajustados. Devuelve una copia de M con y simulada y el nivel verdadero a."""
    th, beta = mod["th"], mod["beta"]
    s2 = _var(th)
    tau0, kappa, c = np.exp(2 * th["log_tau0"]), th["kappa"], np.exp(th["log_c"])
    g = _g(M, beta)
    P_, T = M["y"].shape
    a = np.zeros((P_, T))
    for t in range(T):
        if t == 0:
            a[:, 0] = kappa + g[:, 0] + np.sqrt(tau0) * rng.standard_normal(P_)
        else:
            var = M["gap"][:, t] * s2["eta"] + M["cl"][:, t] * s2["L"] + M["cr"][:, t] * s2["R"]
            a[:, t] = (a[:, t - 1] + g[:, t] - g[:, t - 1] + th.get("phi_rol", 0.0) * M["dmu"][:, t]
                       + np.sqrt(var) * rng.standard_normal(P_))
    y = a + np.sqrt(s2["u"]) * rng.standard_normal((P_, T)) + np.sqrt(c * M["v"]) * rng.standard_normal((P_, T))
    S = dict(M)
    S["y"] = np.where(M["mask"], y, 0.0)
    S["a_verdadero"] = a
    return S


# ------------------------------------------------------------------ peso aprendido de cada temporada pasada
def pesos_temporadas(mod: dict, v_tipica: float, n_temp: int = 4, edad_final: float = 27.0,
                     cambio_liga_ultimo: bool = False, cambio_rol_ultimo: bool = False) -> np.ndarray:
    """Peso de cada temporada pasada (de la más antigua a la última) en la predicción del nivel de la siguiente, para
    un jugador tipo con n_temp temporadas consecutivas de exposición típica (v_tipica). La predicción del filtro es
    lineal en las observaciones: m = Σ w_k y_k + resto; w_k se obtiene con observaciones unitarias. El resto (1 − Σw)
    es el peso del prior (la media de su rol en la liga)."""
    edades = edad_final - np.arange(n_temp)[::-1] - 1
    base = {"y": np.zeros((1, n_temp)), "v": np.full((1, n_temp), v_tipica), "gap": np.r_[0, np.ones(n_temp - 1)][None],
            "cl": np.zeros((1, n_temp)), "cr": np.zeros((1, n_temp)), "dmu": np.zeros((1, n_temp)),
            "mask": np.ones((1, n_temp), bool),
            "B": base_edad(edades)[None], "rol": np.zeros((1, n_temp), int), "personas": np.array(["tipo"])}
    if cambio_liga_ultimo:
        base["cl"][0, -1] = 1.0
    if cambio_rol_ultimo:
        base["cr"][0, -1] = 1.0
    th = mod["th"]
    beta = np.zeros_like(mod["beta"])         # los pesos no dependen de la curva de edad (sólo desplaza la media)
    _, o0 = filtrar(base, th, beta)
    w = np.zeros(n_temp)
    for k in range(n_temp):
        M = {**base, "y": base["y"].copy()}
        M["y"][0, k] = 1.0
        _, o = filtrar(M, th, beta)
        w[k] = o["a"][0, -1] - o0["a"][0, -1]
    return w
