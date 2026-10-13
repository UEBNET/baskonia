"""Paso 3 — El «tipo de cambio» entre ligas, estimado con jugadores puente.

Idea para el ojeador: el paso 2 nos dice en qué puesto está un jugador dentro de SU liga
(su z). Pero ser el 85 % de la LBA no es lo mismo que ser el 85 % de la EuroLeague. Para saber
cuánto vale cada liga usamos a los jugadores que han jugado en dos: el mismo jugador, medido con
dos varas distintas, nos dice cómo se convierte una vara en la otra. Es lo que hacen los
psicómetras para igualar dos versiones de un examen con alumnos que hacen ambas.

Modelo (para cada métrica). Cada jugador puente tiene una capacidad latente `a` medida en la vara
de la EuroLeague (a = 0 es el jugador medio de la EuroLeague en su posición; a = 1, una desviación
típica por encima). Lo que vemos en la liga l es:
    z_obs = α_l + β_l · (a + d·Δ) + ruido
  * EuroLeague es la referencia: α = 0, β = 1.
  * Equivalencia: u = m_l + s_l · z, con m_l = −α_l/β_l («cuánto vale en la EuroLeague el jugador
    medio de la liga l») y s_l = 1/β_l («cuánto se estira o se comprime la escala»).
  * d: cuánto cambia un jugador de una temporada a la siguiente (Δ = 1), según su edad. Separa
    «es mejor porque la liga es más floja» de «es mejor porque ha mejorado».
  * ruido = ruido de muestra (paso 1, conocido) + ψ_l (contexto: rol, entrenador, compañeros)
    + η²·Δ (cambio real impredecible de un año a otro).

Unidades de enlace: para cada jugador y temporada t, todas sus observaciones en t y en t+1. Un
jugador de EuroLeague y ACB a la vez aporta un enlace en la misma temporada (Δ = 0); uno que pasa
de la G League a la EuroLeague, uno entre temporadas (Δ = 1). También entran los que repiten liga:
enseñan cuánto cambia un jugador de un año a otro (d y η²). Las ligas sin puente directo con la
EuroLeague se enlazan en cadena (G League → NBA → EuroLeague).

Estimación: algoritmo EM (esperanza-maximización), que alterna dos pasos hasta converger:
  E: con los tipos de cambio actuales, estima la capacidad `a` de cada jugador puente y su
     incertidumbre (media ponderada de todas sus observaciones, ya pasadas a la vara EuroLeague).
  M: con esas capacidades, reajusta α_l, β_l (regresión de lo observado contra la capacidad,
     corrigiendo por la incertidumbre de `a`, lo que evita el sesgo de atenuación), d, ψ y η².
La incertidumbre de los parámetros se mide con bootstrap por jugadores.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

REFERENCIA = "euroleague"
TRAMOS_EDAD = [(-1, 23, "≤23"), (24, 26, "24-26"), (27, 29, "27-29"), (30, 32, "30-32"), (33, 99, "33+")]


def tramo_edad(edad: float) -> str:
    if edad is None or not np.isfinite(edad):
        return "s/d"
    for lo, hi, nombre in TRAMOS_EDAD:
        if lo <= edad <= hi:
            return nombre
    return "s/d"


def construir_unidades(obs: pd.DataFrame) -> pd.DataFrame:
    """obs: persona_id, liga, anio, z, v, min, anio_nac. Devuelve una fila por (unidad, observación)."""
    obs = obs.reset_index(drop=True)
    obs["oid"] = np.arange(len(obs))
    # unidad (persona, t) = observaciones de la persona en t y t+1
    a = obs[["persona_id", "anio"]].drop_duplicates()
    filas = []
    for delta in (0, 1):
        b = a.assign(anio_obs=a["anio"] + delta).merge(obs, left_on=["persona_id", "anio_obs"],
                                                        right_on=["persona_id", "anio"], suffixes=("", "_o"))
        b["delta"] = delta
        filas.append(b.drop(columns=["anio_o"]))
    u = pd.concat(filas, ignore_index=True)
    u["unidad"] = u["persona_id"].astype(str) + "|" + u["anio"].astype(str)
    n_obs = u.groupby("unidad")["oid"].transform("size")
    u = u[n_obs >= 2].copy()
    # cada observación aparece en hasta 2 unidades: se reparte su peso
    u["w"] = 1.0 / u.groupby("oid")["unidad"].transform("size")
    # liga ancla de la unidad (la de más minutos en la temporada t) y tramo de edad en t
    t0 = u[u["delta"] == 0].sort_values("min", ascending=False).drop_duplicates("unidad")
    u["ancla"] = u["unidad"].map(t0.set_index("unidad")["liga"]).fillna(u["liga"])
    u["tramo"] = (u["anio"] - u["anio_nac"]).map(tramo_edad)
    u["uid"] = pd.factorize(u["unidad"])[0]
    return u.reset_index(drop=True)


class Enlace:
    """Ajuste EM del modelo de enlace para UNA métrica."""

    def __init__(self, ligas: list[str], tramos: list[str], anclas: list[str], kappa: float = 10.0):
        self.kappa = kappa
        self.ligas = ligas
        self.tramos = tramos
        self.anclas = anclas
        L = len(ligas)
        self.alfa = np.zeros(L); self.beta = np.ones(L); self.psi = np.full(L, 0.2)
        self.d = np.zeros(len(tramos)); self.eta2 = 0.05
        self.mu_a = np.zeros(len(anclas)); self.var_a = np.ones(len(anclas))
        self.ref = ligas.index(REFERENCIA)

    # ------------------------------------------------------------------ pasos
    def _e(self, D):
        l, tr, an = D["l"], D["tr"], D["an"]
        be = self.beta[l]
        V = D["v"] + self.psi[l] + be ** 2 * self.eta2 * D["delta"]
        c = D["w"] / V
        resto = D["z"] - self.alfa[l] - be * self.d[tr] * D["delta"]
        U = D["n_u"]
        prec = np.bincount(D["u"], weights=c * be ** 2, minlength=U)
        num = np.bincount(D["u"], weights=c * be * resto, minlength=U)
        prec = prec + 1.0 / self.var_a[D["an_u"]]
        num = num + self.mu_a[D["an_u"]] / self.var_a[D["an_u"]]
        a_hat = num / prec
        return a_hat, 1.0 / prec, V

    def _m(self, D, a_hat, va, V):
        l, tr = D["l"], D["tr"]
        c = D["w"] / V
        ex = a_hat[D["u"]] + self.d[tr] * D["delta"]
        ex2 = ex ** 2 + va[D["u"]]
        for k in range(len(self.ligas)):
            if k == self.ref:
                continue
            s = l == k
            if s.sum() < 5:
                continue
            # previa suave sobre la escala: β ~ N(1, 1/κ). Con muchos puentes no pesa; con pocos evita
            # escalas absurdas en métricas muy ruidosas (equivale a κ observaciones con β = 1).
            A = np.array([[c[s].sum(), (c[s] * ex[s]).sum()], [(c[s] * ex[s]).sum(), (c[s] * ex2[s]).sum() + self.kappa]])
            b = np.array([(c[s] * D["z"][s]).sum(), (c[s] * D["z"][s] * ex[s]).sum() + self.kappa])
            try:
                al, be = np.linalg.solve(A, b)
            except np.linalg.LinAlgError:
                continue
            if be > 0.05:  # una pendiente negativa no tiene sentido (mejor jugador = peor métrica)
                self.alfa[k], self.beta[k] = al, be
        be = self.beta[l]
        # deriva por tramo de edad (sólo observaciones con Δ = 1)
        resto = D["z"] - self.alfa[l] - be * a_hat[D["u"]]
        for j in range(len(self.tramos)):
            s = (tr == j) & (D["delta"] == 1)
            if s.sum() >= 20:
                self.d[j] = (c[s] * be[s] * resto[s]).sum() / (c[s] * be[s] ** 2).sum()
        # varianzas de contexto (ψ) y de cambio anual (η²), por momentos
        r2 = (D["z"] - self.alfa[l] - be * (a_hat[D["u"]] + self.d[tr] * D["delta"])) ** 2 + be ** 2 * va[D["u"]]
        for k in range(len(self.ligas)):
            s = (l == k)
            if s.sum() >= 5:
                exc = r2[s] - D["v"][s] - be[s] ** 2 * self.eta2 * D["delta"][s]
                self.psi[k] = float(np.clip((D["w"][s] * exc).sum() / D["w"][s].sum(), 0.01, 3.0))
        s = D["delta"] == 1
        if s.sum() >= 5:  # sin enlaces entre temporadas, η² no se puede estimar y se deja como está
            exc = (r2[s] - D["v"][s] - self.psi[l[s]]) / be[s] ** 2
            self.eta2 = float(np.clip((D["w"][s] * exc).sum() / D["w"][s].sum(), 0.0, 2.0))
        # distribución previa de la capacidad, por liga ancla de la unidad
        for g in range(len(self.anclas)):
            s = D["an_u"] == g
            if s.sum() >= 5:
                self.mu_a[g] = a_hat[s].mean()
                self.var_a[g] = max(0.05, ((a_hat[s] - self.mu_a[g]) ** 2 + va[s]).mean())

    def ajustar(self, D, iteraciones: int = 1500, tol: float = 2e-4):
        prev = None
        it = 0
        for it in range(iteraciones):
            a_hat, va, V = self._e(D)
            self._m(D, a_hat, va, V)
            # el EM avanza despacio: se mira el cambio acumulado cada 25 iteraciones
            if it % 25 == 0:
                cur = np.concatenate([self.m, self.s, self.d])
                if prev is not None and np.max(np.abs(cur - prev)) < tol * 25:
                    break
                prev = cur
        self.iteraciones = it + 1
        return self

    def copia(self):
        o = Enlace(self.ligas, self.tramos, self.anclas, self.kappa)
        for k in ("alfa", "beta", "psi", "d", "mu_a", "var_a"):
            setattr(o, k, getattr(self, k).copy())
        o.eta2 = self.eta2
        return o

    # ------------------------------------------------------------------ lectura
    @property
    def m(self):
        return -self.alfa / self.beta

    @property
    def s(self):
        return 1.0 / self.beta


def _arrays(u: pd.DataFrame, ligas, tramos, anclas) -> dict:
    uid = u["uid"].to_numpy()
    an_u = np.zeros(uid.max() + 1, dtype=int)
    an_u[uid] = pd.Categorical(u["ancla"], categories=anclas).codes
    return {"u": uid, "n_u": uid.max() + 1, "an_u": an_u,
            "l": pd.Categorical(u["liga"], categories=ligas).codes.astype(int),
            "tr": pd.Categorical(u["tramo"], categories=tramos).codes.astype(int),
            "an": pd.Categorical(u["ancla"], categories=anclas).codes.astype(int),
            "delta": u["delta"].to_numpy(float), "z": u["z"].to_numpy(float),
            "v": u["v"].to_numpy(float), "w": u["w"].to_numpy(float)}


def ajustar_metrica(obs: pd.DataFrame, n_boot: int = 20, semilla: int = 20261013) -> dict:
    """Ajusta el enlace de una métrica. `obs`: una fila por jugador-liga-temporada con
    persona_id, liga, anio, anio_nac, min, z (= z_obs del paso 1) y v (= v_obs)."""
    u = construir_unidades(obs)
    ligas = sorted(u["liga"].unique())
    if REFERENCIA not in ligas:
        raise ValueError("la métrica no tiene datos de la liga de referencia")
    tramos = [t[2] for t in TRAMOS_EDAD] + ["s/d"]
    anclas = ligas
    D = _arrays(u, ligas, tramos, anclas)
    base = Enlace(ligas, tramos, anclas).ajustar(D)

    # bootstrap por personas: se remuestrean jugadores (con todas sus unidades)
    rng = np.random.default_rng(semilla)
    personas = u["persona_id"].unique()
    boots = []
    for _ in range(n_boot):
        elegidas = pd.Series(rng.choice(personas, len(personas), replace=True)).value_counts()
        ub = u[u["persona_id"].isin(elegidas.index)].copy()
        rep = ub["persona_id"].map(elegidas).to_numpy()
        ub = ub.loc[ub.index.repeat(rep)].copy()
        ub["uid"] = pd.factorize(ub["uid"].astype(str) + "|" + ub.groupby(level=0).cumcount().astype(str))[0]
        e = base.copia().ajustar(_arrays(ub, ligas, tramos, anclas), iteraciones=400)
        boots.append((e.m.copy(), e.s.copy(), e.d.copy()))
    M = np.array([b[0] for b in boots]); S = np.array([b[1] for b in boots])
    puentes = {}
    multi = u.groupby("unidad")["liga"].transform("nunique") >= 2
    for k in ligas:
        puentes[k] = int(u.loc[multi & (u["liga"] == k), "unidad"].nunique())
    return {
        "ligas": ligas, "tramos": tramos,
        "m": dict(zip(ligas, base.m.tolist())), "s": dict(zip(ligas, base.s.tolist())),
        "m_se": dict(zip(ligas, M.std(axis=0).tolist())) if n_boot else {},
        "s_se": dict(zip(ligas, S.std(axis=0).tolist())) if n_boot else {},
        "cov_ms": dict(zip(ligas, [float(np.cov(M[:, i], S[:, i])[0, 1]) if n_boot > 1 else 0.0 for i in range(len(ligas))])),
        "psi": dict(zip(ligas, base.psi.tolist())), "eta2": base.eta2,
        "deriva": dict(zip(tramos, base.d.tolist())),
        "unidades": int(u["unidad"].nunique()), "puentes_por_liga": puentes,
        "iteraciones": base.iteraciones,
    }
