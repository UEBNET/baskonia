"""Algoritmo B — «ADN del jugador»: red neuronal multitarea que separa jugador, liga, temporada y equipo.

Idea para el ojeador. Cada jugador tiene un «ADN» (un vector de 8 números) que describe cómo juega
y cuánto vale, y que NO depende de dónde juega. Lo que vemos en la estadística es ese ADN
«expresado» en un sitio concreto:

    lo que vemos = ENTORNO (liga, temporada, posición)
                 + CONTEXTO (su equipo esa temporada)
                 + EXPRESIÓN DEL ADN EN ESA LIGA (red neuronal propia de cada liga)
                 + ruido (muestra pequeña y contexto no explicado)

Para traducirlo a la EuroLeague basta con «expresar» su ADN con la red de la EuroLeague, en el
entorno EuroLeague 2025-26 y con un equipo medio. Esto normaliza a la vez por nivel, liga, temporada
y equipo. La red aprende las 25 métricas a la vez, así que usa sus relaciones: si un jugador rebotea
mucho y tapona mucho, la red sabe que suele ser un tipo concreto de interior y lo traduce como tal.

Modelo (todas las métricas en escala transformada y estandarizada; jugadores con 150+ minutos):
    z_{i,t}  = u_i + A[edad_{i,t}] + e_{i,t}                       ADN (8 números) del jugador i en la temporada t
               u_i ~ N(m_L(i), I)      (m_L: ADN medio de su liga principal; m_EuroLeague = 0)
               e_{i,t} ~ N(0, η² I)    (lo que cambia un año concreto; η = 0,01)
               A[edad]                 (curva de edad común; 0 si la edad es desconocida)
    h        = tanh(W1 z + c_l)                                     capa oculta, desplazada por la liga (FiLM)
    x̂_{r,k}  = b_{l,t,pos,k} + T_{equipo-temporada,k} + [(W2 + V_l) h]_k
    y_{r,k}  ~ N(x̂_{r,k}, v_{r,k} + ψ_{l,k})                        v: ruido de muestra (σ²/n, paso 1 del A)
Priors: T ~ N(0, σ_T,k²) y V_l ~ N(0, σ_V²), con varianzas estimadas por bayes empírico; pesos con
decaimiento leve. Entrenamiento: máxima a posteriori con Adam (gradientes calculados a mano).
Incertidumbre: aproximación de Laplace del ADN de cada jugador-temporada + conjunto (ensemble) de redes
entrenadas con distintas semillas.

Los embeddings (u, e) se aprenden directamente por optimización, sin un codificador aparte
(«auto-decoder»). Para un jugador nuevo se reoptimiza sólo su ADN con la red congelada.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.stats import norm

from . import enlace, suerte
from .metricas import CATALOGO, destransformar

REFERENCIA = "euroleague"
Z80 = norm.ppf(0.9)


# ------------------------------------------------------------------------------------------ datos
def preparar_matrices(t: pd.DataFrame, min_minutos: float = 50) -> dict:
    """Matrices de entrenamiento: Y (filas x métricas), máscara, ruido conocido y los índices."""
    t = t[(t["min"] >= min_minutos) & t["pos3"].notna()].copy()
    metricas = list(CATALOGO)
    N, K = len(t), len(metricas)
    Y = np.zeros((N, K)); M = np.zeros((N, K)); Vn = np.ones((N, K))
    escala, sigma2 = {}, {}
    for k, col in enumerate(metricas):
        y, n = suerte.valor_y_exposicion(t, col)
        _, p1 = suerte.ajustar_metrica(t, col)
        ok = np.isfinite(y) & np.isfinite(n) & (n > 0)
        ref = ok & (t["min"].to_numpy() >= 300)
        mu, sd = float(np.mean(y[ref])), float(np.std(y[ref]))
        escala[col] = (mu, sd)
        sigma2[col] = p1["sigma2"]
        s2 = np.array([p1["sigma2"].get(l, p1["sigma2"].get("todas", np.nan)) for l in t["liga"]])
        Y[ok, k] = (y[ok] - mu) / sd
        Vn[ok, k] = s2[ok] / n[ok] / sd ** 2
        M[ok, k] = 1.0
    M[~np.isfinite(Vn)] = 0; Vn[~np.isfinite(Vn)] = 1.0
    t["ps"] = t["persona_id"].astype(str) + "|" + t["anio"].astype(str)
    t["g"] = t["liga"] + "|" + t["temporada"] + "|" + t["pos3"]
    t["eq"] = t["liga"] + "|" + t["temporada"] + "|" + t["team_id"].astype(str)
    t["tramo"] = (t["anio"] - t["anio_nac"]).map(enlace.tramo_edad)
    # liga principal de cada persona (la de más minutos en su carrera): fija la media de su ADN
    principal = t.groupby(["persona_id", "liga"])["min"].sum().reset_index().sort_values("min").drop_duplicates("persona_id", keep="last")
    t["liga_principal"] = t["persona_id"].map(principal.set_index("persona_id")["liga"])
    cod = {}
    for c in ("persona_id", "ps", "g", "eq", "liga", "tramo"):
        codes, uniques = pd.factorize(t[c], sort=True)
        cod[c] = (codes, list(uniques))
    ligas = cod["liga"][1]
    pers = cod["persona_id"][1]
    lp = pd.Series(t["liga_principal"].to_numpy(), index=t["persona_id"]).groupby(level=0).first()
    liga_de_persona = np.array([ligas.index(lp[p]) for p in pers])
    return {"t": t.reset_index(drop=True), "metricas": metricas, "Y": Y, "M": M, "Vn": Vn, "escala": escala, "sigma2": sigma2,
            "cod": cod, "ligas": ligas, "liga_de_persona": liga_de_persona}


def _onehot(codes, n):
    return sp.csr_matrix((np.ones(len(codes)), (np.arange(len(codes)), codes)), shape=(len(codes), n))


# ------------------------------------------------------------------------------------------ red
class RedADN:
    # Configuración elegida con el corte de ajuste 2022-23 → 2023-24 (los cortes de examen 2023 y 2024
    # no se usaron para elegirla): ADN de 8 dimensiones, η = 0,01 (el ADN apenas cambia de un año a
    # otro: cuanta menos libertad, mejor predice), 32 neuronas, jugadores con 150+ minutos.
    def __init__(self, D: dict, d: int = 8, H: int = 32, eta: float = 0.01, semilla: int = 0, psi_min: float = 0.0,
                 wd: float = 1e-3):
        rng = np.random.default_rng(semilla)
        self.D = D; self.d, self.H, self.eta = d, H, eta
        self.log_psi_min = np.log(psi_min) if psi_min > 0 else -np.inf
        self.wd = wd
        N, K = D["Y"].shape
        c = D["cod"]
        self.n = {k: len(v[1]) for k, v in c.items()}
        L = self.n["liga"]
        self.ref = D["ligas"].index(REFERENCIA)
        # matrices de asignación (dispersas): fila -> persona, persona-temporada, grupo, equipo, liga, tramo
        self.O = {k: _onehot(v[0], self.n[k]) for k, v in c.items()}
        self.OT = {k: v.T.tocsr() for k, v in self.O.items()}
        self.filas_liga = [np.where(c["liga"][0] == l)[0] for l in range(L)]
        # parámetros
        Y, M = D["Y"], D["M"]
        bG = (self.OT["g"] @ (Y * M)) / np.maximum(self.OT["g"] @ M, 1)
        self.p = {
            "U": rng.normal(0, 0.1, (self.n["persona_id"], d)),
            "E": np.zeros((self.n["ps"], d)),
            "A": np.zeros((self.n["tramo"], d)),
            "mL": np.zeros((L, d)),
            "W1": rng.normal(0, 1 / np.sqrt(d), (H, d)),
            "C": np.zeros((L, H)),
            "W2": rng.normal(0, 1 / np.sqrt(H), (K, H)),
            "V": np.zeros((L, K, H)),
            "bG": np.asarray(bG),
            "T": np.zeros((self.n["eq"], K)),
            "rho": np.full((L, K), np.log(0.2)),
        }
        self.s2T = np.full(K, 0.05); self.s2V = 0.05
        self.sd = c["tramo"][1].index("s/d") if "s/d" in c["tramo"][1] else None
        self.adam = {k: (np.zeros_like(v), np.zeros_like(v)) for k, v in self.p.items()}
        self.paso = 0

    # -------------------------------------------------------------- hacia delante
    def z(self, p=None):
        p = p or self.p
        c = self.D["cod"]
        return p["U"][c["persona_id"][0]] + p["A"][c["tramo"][0]] + p["E"][c["ps"][0]]

    def salida_red(self, Z, ligas_fila):
        """(W2 + V_l) tanh(W1 z + c_l) para cada fila."""
        p = self.p
        Hh = np.tanh(Z @ p["W1"].T + p["C"][ligas_fila])
        O = Hh @ p["W2"].T
        for l in np.unique(ligas_fila):
            s = ligas_fila == l
            O[s] += Hh[s] @ p["V"][l].T
        return O, Hh

    def perdida_y_gradientes(self):
        p, D, c = self.p, self.D, self.D["cod"]
        Y, M, Vn = D["Y"], D["M"], D["Vn"]
        l = c["liga"][0]
        Z = self.z()
        O, Hh = self.salida_red(Z, l)
        Xh = p["bG"][c["g"][0]] + p["T"][c["eq"][0]] + O
        Psi = np.exp(p["rho"])[l]
        S = Vn + Psi
        R = (Y - Xh) * M
        nll = float(np.sum(M * (R ** 2 / (2 * S) + 0.5 * np.log(S))))
        g = {}
        GX = -R / S
        GS = M * (-(R ** 2) / (2 * S ** 2) + 1 / (2 * S))
        g["rho"] = (self.OT["liga"] @ (GS * Psi))
        g["bG"] = self.OT["g"] @ GX
        g["T"] = self.OT["eq"] @ GX + p["T"] / self.s2T
        g["W2"] = GX.T @ Hh + self.wd * p["W2"]
        GH = GX @ p["W2"]
        g["V"] = np.zeros_like(p["V"])
        for li, filas in enumerate(self.filas_liga):
            g["V"][li] = GX[filas].T @ Hh[filas] + p["V"][li] / self.s2V
            GH[filas] += GX[filas] @ p["V"][li]
        GA = GH * (1 - Hh ** 2)
        g["W1"] = GA.T @ Z + self.wd * p["W1"]
        g["C"] = self.OT["liga"] @ GA
        GZ = GA @ p["W1"]
        dif = p["U"] - p["mL"][D["liga_de_persona"]]
        g["U"] = self.OT["persona_id"] @ GZ + dif
        g["mL"] = -np.asarray(sp.csr_matrix((np.ones(len(dif)), (D["liga_de_persona"], np.arange(len(dif)))),
                                            shape=(len(p["mL"]), len(dif))) @ dif)
        g["mL"][self.ref] = 0.0   # la EuroLeague es el origen de la vara
        g["E"] = self.OT["ps"] @ GZ + p["E"] / self.eta ** 2
        g["A"] = self.OT["tramo"] @ GZ + p["A"]
        prior = 0.5 * (np.sum(dif ** 2) + np.sum(p["E"] ** 2) / self.eta ** 2 + np.sum(p["T"] ** 2 / self.s2T)
                       + np.sum(p["V"] ** 2) / self.s2V + np.sum(p["A"] ** 2))
        return nll + prior, nll, g

    # -------------------------------------------------------------- entrenamiento
    def entrenar(self, pasos: int = 3000, lr: float = 0.02, cada: int = 250, progreso=None):
        b1, b2, eps = 0.9, 0.999, 1e-8
        hist = []
        for it in range(pasos):
            self.paso += 1
            lr_t = lr * (0.1 + 0.9 * 0.5 * (1 + np.cos(np.pi * it / pasos)))   # coseno de lr a lr/10
            total, nll, g = self.perdida_y_gradientes()
            for k, gr in g.items():
                m, v = self.adam[k]
                m[:] = b1 * m + (1 - b1) * gr
                v[:] = b2 * v + (1 - b2) * gr ** 2
                mh = m / (1 - b1 ** self.paso); vh = v / (1 - b2 ** self.paso)
                self.p[k] -= lr_t * mh / (np.sqrt(vh) + eps)
            self.p["mL"][self.ref] = 0.0
            self.p["rho"] = np.maximum(self.p["rho"], self.log_psi_min)   # suelo del contexto no explicado
            self.p["A"][self.sd] = 0.0     # edad desconocida: sin efecto de edad (no puede actuar como comodín de liga)
            if (it + 1) % cada == 0:
                # bayes empírico de las varianzas de los efectos de equipo y de liga
                self.s2T = np.maximum(0.005, np.mean(self.p["T"] ** 2, axis=0) * self.n["eq"] / max(self.n["eq"] - 1, 1))
                self.s2V = max(0.002, float(np.mean(self.p["V"] ** 2)))
                hist.append((it + 1, total, nll))
                if progreso:
                    progreso(f"    paso {it + 1}: pérdida {total:,.0f} (verosimilitud {nll:,.0f})")
        return hist

    # -------------------------------------------------------------- traducción
    def expresar(self, Z, liga: str, g_clave: list[str]):
        """Valor esperado (escala estandarizada) del ADN Z expresado en `liga`, con entorno g_clave
        (liga|temporada|pos de destino) y equipo medio. Devuelve (X, Jacobiano K x d por fila)."""
        p = self.p
        li = self.D["ligas"].index(liga)
        gi = np.array([self.D["cod"]["g"][1].index(k) if k in self.D["cod"]["g"][1] else -1 for k in g_clave])
        Hh = np.tanh(Z @ p["W1"].T + p["C"][li])
        Wl = p["W2"] + p["V"][li]
        X = Hh @ Wl.T + np.where(gi[:, None] >= 0, p["bG"][np.maximum(gi, 0)], np.nan)
        J = np.einsum("kh,nh,hd->nkd", Wl, 1 - Hh ** 2, p["W1"])
        return X, J

    def varianza_adn(self):
        """Aproximación de Laplace: covarianza del ADN de cada persona-temporada a partir de la
        información de sus propias filas (conservadora: no usa las otras temporadas)."""
        p, D, c = self.p, self.D, self.D["cod"]
        l = c["liga"][0]
        Z = self.z()
        Hh = np.tanh(Z @ p["W1"].T + p["C"][l])
        W = D["M"] / (D["Vn"] + np.exp(p["rho"])[l])
        info = np.zeros((self.n["ps"], self.d, self.d))
        for li, filas in enumerate(self.filas_liga):
            Wl = p["W2"] + p["V"][li]
            J = np.einsum("kh,nh,hd->nkd", Wl, 1 - Hh[filas] ** 2, p["W1"])
            F = np.einsum("nkd,nk,nke->nde", J, W[filas], J)
            np.add.at(info, c["ps"][0][filas], F)
        info += np.eye(self.d) / (1 + self.eta ** 2)
        return np.linalg.inv(info)


# ------------------------------------------------------------------------------------------ conjunto
class ConjuntoB:
    """Varias redes con distinta semilla sobre los mismos datos (deep ensemble). La media es la
    predicción; la dispersión entre redes mide la incertidumbre del propio modelo."""

    def __init__(self, t: pd.DataFrame, hasta_anio: int | None = None, n_redes: int = 5, pasos: int = 3000,
                 progreso=print, min_minutos: float = 150, **kw):
        base = t if hasta_anio is None else t[t["anio"] <= hasta_anio]
        self.D = preparar_matrices(base, min_minutos=min_minutos)
        self.redes = []
        for s in range(n_redes):
            r = RedADN(self.D, semilla=s, **kw)
            r.entrenar(pasos=pasos)
            self.redes.append(r)
            if progreso:
                progreso(f"  red {s + 1}/{n_redes} entrenada")
        self.cov = [r.varianza_adn() for r in self.redes]
        self.hasta_anio = hasta_anio

    def _orig(self, k, x):
        col = self.D["metricas"][k]
        mu, sd = self.D["escala"][col]
        return destransformar(x * sd + mu, CATALOGO[col].transf)

    def expresar_filas(self, idx_ps: np.ndarray, Zs: list[np.ndarray], liga: str, g_clave: list[str],
                       extra_var: float = 0.0):
        """Media y varianza (escala estandarizada) de ADN dados (uno por red) expresados en `liga`."""
        Xs, Vs = [], []
        for r, Z, C in zip(self.redes, Zs, self.cov):
            X, J = r.expresar(Z, liga, g_clave)
            Sz = C[idx_ps] + extra_var * np.eye(r.d)
            Vs.append(np.einsum("nkd,nde,nke->nk", J, Sz, J))
            Xs.append(X)
        Xs = np.array(Xs); Vs = np.array(Vs)
        return Xs.mean(0), Vs.mean(0) + Xs.var(0)

    def traducir(self, temporada_ref: str = "2025-26") -> pd.DataFrame:
        """Equivalente EuroLeague de cada fila (jugador-liga-temporada), en su posición, equipo medio."""
        t = self.D["t"]; c = self.D["cod"]
        gk = [f"{REFERENCIA}|{temporada_ref}|{p}" for p in t["pos3"]]
        Zs = [r.z() for r in self.redes]
        X, V = self.expresar_filas(c["ps"][0], Zs, REFERENCIA, gk)
        # proyección a la temporada siguiente: ADN estable + curva de edad del año siguiente
        tr_sig = (t["anio"] + 1 - t["anio_nac"]).map(enlace.tramo_edad)
        it = np.array([c["tramo"][1].index(x) if x in c["tramo"][1] else 0 for x in tr_sig])
        Zn = [r.p["U"][c["persona_id"][0]] + r.p["A"][it] for r in self.redes]
        Xn, _ = self.expresar_filas(c["ps"][0], Zn, REFERENCIA, gk)
        out = t[["persona_id", "liga", "temporada", "anio", "player_id", "nombre", "equipo", "pos3", "min"]].copy()
        ref = ((t["liga"] == REFERENCIA) & (t["temporada"] == temporada_ref) & (t["min"] >= 300)).to_numpy()
        nuevas = {}
        for k, col in enumerate(self.D["metricas"]):
            sd = np.sqrt(V[:, k])
            nuevas[f"{col}_el"] = self._orig(k, X[:, k])
            nuevas[f"{col}_el_lo"] = self._orig(k, X[:, k] - Z80 * sd)
            nuevas[f"{col}_el_hi"] = self._orig(k, X[:, k] + Z80 * sd)
            nuevas[f"{col}_el_prox"] = self._orig(k, Xn[:, k])
            # percentil entre los jugadores de EuroLeague de su posición (temporada de referencia)
            pct = np.full(len(t), np.nan)
            for pos in ("E", "A", "I"):
                refv = np.sort(X[ref & (t["pos3"] == pos).to_numpy(), k])
                s = (t["pos3"] == pos).to_numpy()
                if len(refv):
                    pct[s] = 100 * np.searchsorted(refv, X[s, k]) / len(refv)
            nuevas[f"{col}_pct_el"] = pct
            nuevas[f"{col}_x"] = X[:, k]
        return pd.concat([out.reset_index(drop=True), pd.DataFrame(nuevas)], axis=1)

    def predecir_cambios(self, casos: pd.DataFrame) -> pd.DataFrame:
        """Validación: para cada jugador que cambia de liga entre t y t+1, predice su valor en la liga
        de destino en t+1 usando sólo datos hasta t."""
        D, c = self.D, self.D["cod"]
        pers = {p: i for i, p in enumerate(c["persona_id"][1])}
        ps = {p: i for i, p in enumerate(c["ps"][1])}
        filas = []
        for (ld, anio), g in casos.groupby(["liga_d", "anio_o"]):
            if ld not in D["ligas"]:
                continue
            g = g[g["persona_id"].isin(pers)]
            g = g[[f"{x}|{anio}" in ps for x in g["persona_id"].astype(str)]]
            if not len(g):
                continue
            ip = np.array([pers[p] for p in g["persona_id"]])
            ips = np.array([ps[f"{p}|{anio}"] for p in g["persona_id"].astype(str)])
            tr = (anio + 1 - g["anio_nac_o"]).map(enlace.tramo_edad)
            it = np.array([c["tramo"][1].index(x) if x in c["tramo"][1] else 0 for x in tr])
            Zs = [r.p["U"][ip] + r.p["A"][it] for r in self.redes]
            temp_t = f"{anio}-{str(anio + 1)[-2:]}"
            gk = [f"{ld}|{temp_t}|{p}" for p in g["pos3_o"]]
            X, V = self.expresar_filas(ips, Zs, ld, gk, extra_var=self.redes[0].eta ** 2)
            li = D["ligas"].index(ld)
            psi = np.mean([np.exp(r.p["rho"][li]) for r in self.redes], axis=0)
            for k, col in enumerate(D["metricas"]):
                mu, sd = D["escala"][col]
                real = g[f"{col}_d"].to_numpy(float)
                y_real, n_d = suerte.valor_y_exposicion(g.rename(columns=lambda x: x[:-2] if x.endswith("_d") else x + "__o"), col)
                filas.append(pd.DataFrame({
                    "metrica": col, "anio": anio, "persona_id": g["persona_id"].to_numpy(), "liga_d": ld,
                    "real": real, "algoritmo_B": self._orig(k, X[:, k]),
                    "x_pred": X[:, k], "v_pred": V[:, k] + psi[k], "y_real": (y_real - mu) / sd,
                    "v_real": D["sigma2"][col].get(ld, D["sigma2"][col].get("todas", np.nan)) / n_d / sd ** 2}))
        return pd.concat(filas, ignore_index=True)


# ------------------------------------------------------------------------------------------ informes
from pathlib import Path  # noqa: E402

DIR_SALIDA_B = Path(__file__).resolve().parent.parent / "data" / "modelos" / "algoritmo_B"


def niveles_por_liga(cj: ConjuntoB, temporada: str = "2025-26", min_minutos: float = 300) -> pd.DataFrame:
    """Nivel de cada liga en la vara EuroLeague según B: posición media (en desviaciones típicas de
    los jugadores de EuroLeague de la misma posición) que tendrían sus jugadores en la EuroLeague.
    Comparable con el «m» del algoritmo A. La incertidumbre es la dispersión entre redes."""
    t = cj.D["t"]; c = cj.D["cod"]
    gk = [f"{REFERENCIA}|{temporada}|{p}" for p in t["pos3"]]
    por_red = []
    for r in cj.redes:
        X, _ = r.expresar(r.z(), REFERENCIA, gk)
        por_red.append(X)
    sel = ((t["temporada"] == temporada) & (t["min"] >= min_minutos)).to_numpy()
    ref = sel & (t["liga"] == REFERENCIA).to_numpy()
    filas = []
    for k, col in enumerate(cj.D["metricas"]):
        niv = {}
        for X in por_red:
            z = np.full(len(t), np.nan)
            for pos in ("E", "A", "I"):
                s = (t["pos3"] == pos).to_numpy()
                mu, sd = X[ref & s, k].mean(), X[ref & s, k].std()
                z[s] = (X[s, k] - mu) / sd
            for liga in cj.D["ligas"]:
                v = z[sel & (t["liga"] == liga).to_numpy() & np.isfinite(z)]
                if len(v):
                    niv.setdefault(liga, []).append(v.mean())
        for liga, v in niv.items():
            filas.append({"metrica": col, "liga": liga, "nivel": float(np.mean(v)), "nivel_se": float(np.std(v))})
    return pd.DataFrame(filas)


def guardar(cj: ConjuntoB, trad: pd.DataFrame, niveles: pd.DataFrame, dir_salida: Path = DIR_SALIDA_B) -> None:
    import json
    dir_salida = Path(dir_salida)
    (dir_salida / "traducciones").mkdir(parents=True, exist_ok=True)
    for temp, g in trad.groupby("temporada"):
        g.drop(columns=[c for c in g.columns if c.endswith("_x")]).round(4).to_csv(dir_salida / "traducciones" / f"{temp}.csv", index=False)
    niveles.round(4).to_csv(dir_salida / "nivel_por_liga.csv", index=False)
    r0 = cj.redes[0]
    resumen = {
        "redes": len(cj.redes), "dim_adn": r0.d, "neuronas_ocultas": r0.H, "eta": r0.eta,
        "filas": int(len(cj.D["t"])), "personas": int(r0.n["persona_id"]), "persona_temporadas": int(r0.n["ps"]),
        "equipos_temporada": int(r0.n["eq"]), "grupos_entorno": int(r0.n["g"]),
        "metricas": cj.D["metricas"], "ligas": cj.D["ligas"],
        "sigma_equipo": {m: float(np.mean([np.sqrt(r.s2T[k]) for r in cj.redes])) for k, m in enumerate(cj.D["metricas"])},
        "psi_mediana_liga": {l: float(np.median([np.exp(r.p["rho"][i]) for r in cj.redes])) for i, l in enumerate(cj.D["ligas"])},
        "curva_edad_norma": {tr: float(np.mean([np.linalg.norm(r.p["A"][i]) for r in cj.redes])) for i, tr in enumerate(cj.D["cod"]["tramo"][1])},
    }
    (dir_salida / "resumen_modelo.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    np.savez_compressed(dir_salida / "redes.npz", **{f"r{i}_{k}": v for i, r in enumerate(cj.redes) for k, v in r.p.items()})
