"""F1 · RAPM multiliga con prior del perfil (capa 1 de la v4.0; encargo §6).

    y_s = c_{ℓ,t} + κ·clutch_s + π·playoffs_s + Σ_{i∈A_s} β_i − Σ_{j∈B_s} β_j + ε_s,   ε_s ~ N(0, σ²/n_s)
    β_i ~ N( g(x̃_i; γ), τ² )

* Tramo s: quintetos A_s (equipo local, `team_a` de bbstats.lineups) y B_s (visitante), n_s posesiones (contrato:
  media de los dos lados de fga + 0,44·fta − oreb + tov), y_s = 100·(pts_A − pts_B)/n_s. Como A es siempre el local,
  el intercepto liga-temporada c_{ℓ,t} ES la ventaja local de esa liga-temporada (h_s y c_{ℓ,t} del encargo
  coinciden en este diseño; se declara). Clutch y playoffs entran como covariables globales.
* β_i por PERSONA-TEMPORADA (persona_id del crosswalk + temporada): un jugador que juega dos ligas la misma temporada
  tiene un solo β, y sus tramos en las dos ligas lo informan (puente en pista). Dentro de una liga, Σβ no es
  identificable por los diferenciales (sumar una constante a todos sus jugadores no cambia nada): el nivel entre ligas
  lo pone el prior g(x̃), que viene de la capa 0 en una escala común [HIPÓTESIS declarada en el encargo].
* g(x̃; γ): ridge o GBM pequeño sobre el perfil ampliado (bbequipo.perfiles) del registro principal de la persona en
  esa temporada, con la máscara de rasgos (qué bloques tienen dato) como indicadores. Se elige en el corte de
  selección (bbequipo.examen_f1). Un jugador sin perfil recibe la media del prior de su liga-temporada (marcado).
* Ajuste por bayes empírico: dado g, τ², σ², el posterior de β es ridge con media a priori g (mínimos cuadrados
  dispersos, LSQR sobre el sistema aumentado); dado β̂, se reajusta γ y se actualizan τ² (varianza entre jugadores
  del residuo β̂ − g más la varianza a posteriori, aproximada por su diagonal) y σ² (residuo ponderado). Iteraciones
  fijadas en el YAML.
* Descomposición O/D (`componente = "od"`): dos filas por tramo (ataque de A frente a defensa de B y viceversa),
  y = 100·pts/n, β^O (puntos anotados por 100) y β^D (puntos permitidos por 100; se publica drapm = −β^D para que
  DRAPM > 0 sea mejor, como en bbstats.lineups).
Todo hiperparámetro en configs/equipo_v40.yaml → f1. Salidas: data/modelos/v4_0/rapm_multiliga/.
"""
from __future__ import annotations

import json
import pickle
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from . import config as C
from .perfiles import estilos, rasgos, roles

RASGOS_PISTA = ("pct_aro", "pct_corta", "pct_media", "pct_t3_esquina", "pct_asistidas", "orapm", "drapm", "rapm")
COLS_TRAMOS = ["game_id", "fase", "sec", "team_a", "team_b", "quinteto_a", "quinteto_b", "n_a", "n_b", "clutch", "basura",
               "a_pts", "b_pts", "a_fga", "a_fta", "a_oreb", "a_tov", "b_fga", "b_fta", "b_oreb", "b_tov"]


def dir_salida(cfg: dict) -> Path:
    d = C.RAIZ / cfg["f1"]["salidas"]["rapm"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def anio(temp: str) -> int:
    return int(str(temp)[:4])


# =============================================================================================== datos
def ligas_incluidas(cfg: dict) -> pd.DataFrame:
    """Liga-temporadas que entran en F1–F3 según el contrato de datos (decision ≠ excluida)."""
    inv = pd.read_csv(C.dir_salida(cfg) / "contrato" / "inventario_tramos.csv")
    return inv[inv["decision"] != "excluida"][["liga", "temporada", "decision"]].reset_index(drop=True)


def _mapa_persona(liga: str, ids: pd.Series) -> dict:
    from bbfit.datos import persona
    u = pd.Series(pd.unique(ids.astype(str)))
    return dict(zip(u, persona(liga, u).astype(str)))


def tramos_liga_temporada(temp: str, liga: str, cfg: dict) -> pd.DataFrame:
    """Tramos válidos (contrato) de una liga-temporada con los quintetos como claves persona|temporada."""
    from .contrato import filtrar_tramos
    p = C.ruta(cfg, "quintetos", temporada=temp) / liga / "tramos.csv.gz"
    df = pd.read_csv(p, usecols=lambda c: c in COLS_TRAMOS, low_memory=False)
    tr, _ = filtrar_tramos(df, cfg)
    if tr.empty:
        return pd.DataFrame()
    ids = pd.concat([tr["quinteto_a"].str.split("|").explode(), tr["quinteto_b"].str.split("|").explode()])
    mp = _mapa_persona(liga, ids)
    sin_cw = sum(1 for k, v in mp.items() if v.startswith(liga + ":"))
    conv = lambda q: tuple(f"{mp[x]}|{temp}" for x in q.split("|"))  # noqa: E731
    out = pd.DataFrame({"liga": liga, "temporada": temp, "anio": anio(temp), "game_id": tr["game_id"].to_numpy(),
                        "fase": tr["fase"].to_numpy(), "team_a": tr["team_a"].astype(str).to_numpy(),
                        "team_b": tr["team_b"].astype(str).to_numpy(),
                        "clutch": tr["clutch"].astype(str).str.lower().isin(["true", "1"]).to_numpy(),
                        "playoffs": (tr["fase"] != "regular").to_numpy(),
                        "poss": tr["poss"].to_numpy(float), "a_pts": tr["a_pts"].to_numpy(float),
                        "b_pts": tr["b_pts"].to_numpy(float), "A": tr["quinteto_a"].map(conv).to_numpy(),
                        "B": tr["quinteto_b"].map(conv).to_numpy()})
    out["y"] = 100.0 * (out["a_pts"] - out["b_pts"]) / out["poss"]
    out.attrs["sin_crosswalk"] = sin_cw
    return out


def tramos(cfg: dict, hasta_anio: int | None = None, progreso=print) -> pd.DataFrame:
    """Todos los tramos válidos de las liga-temporadas incluidas (caché experimentos/v4_0/tramos.pkl), ≤ hasta_anio."""
    cache = C.RAIZ / "experimentos" / "v4_0" / "tramos.pkl"
    if cache.exists():
        t = pickle.loads(cache.read_bytes())
    else:
        t0 = time.time()
        partes = []
        for r in ligas_incluidas(cfg).itertuples():
            x = tramos_liga_temporada(r.temporada, r.liga, cfg)
            if len(x):
                partes.append(x)
        t = pd.concat(partes, ignore_index=True)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(pickle.dumps(t))
        if progreso:
            progreso(f"  tramos: {len(t)} válidos en {len(partes)} liga-temporadas · {time.time() - t0:.0f} s", flush=True)
    if hasta_anio is not None:
        t = t[t["anio"] <= int(hasta_anio)].reset_index(drop=True)
    return t


# =============================================================================================== diseño
@dataclass
class Diseno:
    X: sp.csr_matrix                  # filas × (componentes·jugadores + fijos)
    y: np.ndarray
    w: np.ndarray                     # posesiones de cada fila
    jugadores: list                   # claves persona|temporada
    fijos: list                       # nombres de las columnas fijas
    componentes: list                 # ["net"] o ["of", "def"]
    liga_temp: np.ndarray             # liga|temporada de cada fila
    partido: np.ndarray = None        # liga|temporada|game_id de cada fila (pliegues de la validación cruzada)
    idx_jugador: dict = field(default_factory=dict)

    @property
    def nJ(self):
        return len(self.jugadores)

    @property
    def nC(self):
        return len(self.componentes)

    def col(self, comp: int, j: int) -> int:
        return comp * self.nJ + j


def construir_diseno(tr: pd.DataFrame, componente: str = "net") -> Diseno:
    """Matriz dispersa del modelo (vectorizada: con ≈ 1 M de tramos las listas de Python agotaban la memoria)."""
    jug = sorted(set(k for q in tr["A"] for k in q) | set(k for q in tr["B"] for k in q))
    ij = {k: i for i, k in enumerate(jug)}
    lt = (tr["liga"] + "|" + tr["temporada"]).to_numpy()
    lts = sorted(set(lt))
    ilt = {k: i for i, k in enumerate(lts)}
    nJ, n = len(jug), len(tr)
    A = np.array([[ij[k] for k in q] for q in tr["A"]], dtype=np.int64)      # n × 5
    B = np.array([[ij[k] for k in q] for q in tr["B"]], dtype=np.int64)
    clutch, po = tr["clutch"].to_numpy(bool), tr["playoffs"].to_numpy(bool)
    ilt_s = np.array([ilt[k] for k in lt], dtype=np.int64)
    poss = tr["poss"].to_numpy(float)
    ar = np.arange(n)
    if componente == "net":
        comps, fijos = ["net"], [f"c_{k}" for k in lts] + ["clutch", "playoffs"]
        base = nJ
        rows = [np.repeat(ar, 5), np.repeat(ar, 5), ar, ar[clutch], ar[po]]
        cols = [A.ravel(), B.ravel(), base + ilt_s, np.full(clutch.sum(), base + len(lts)), np.full(po.sum(), base + len(lts) + 1)]
        vals = [np.ones(5 * n), -np.ones(5 * n), np.ones(n), np.ones(clutch.sum()), np.ones(po.sum())]
        y, w, lt_f, partido = tr["y"].to_numpy(float), poss, lt, lt + "|" + tr["game_id"].astype(str).to_numpy()
        nf = n
    else:   # od: dos filas por tramo; columnas [β^O (nJ), β^D (nJ), c_of liga|temp, local, clutch, playoffs]
        comps, fijos = ["of", "def"], [f"c_{k}" for k in lts] + ["local", "clutch", "playoffs"]
        base = 2 * nJ
        ra, rb = 2 * ar, 2 * ar + 1                                              # ataque de A (local) / ataque de B
        rows = [np.repeat(ra, 5), np.repeat(ra, 5), ra, ra, ra[clutch], ra[po],
                np.repeat(rb, 5), np.repeat(rb, 5), rb, rb[clutch], rb[po]]
        cols = [A.ravel(), nJ + B.ravel(), base + ilt_s, np.full(n, base + len(lts)), np.full(clutch.sum(), base + len(lts) + 1), np.full(po.sum(), base + len(lts) + 2),
                B.ravel(), nJ + A.ravel(), base + ilt_s, np.full(clutch.sum(), base + len(lts) + 1), np.full(po.sum(), base + len(lts) + 2)]
        vals = [np.ones(5 * n), np.ones(5 * n), np.ones(n), np.ones(n), np.ones(clutch.sum()), np.ones(po.sum()),
                np.ones(5 * n), np.ones(5 * n), np.ones(n), np.ones(clutch.sum()), np.ones(po.sum())]
        y = np.empty(2 * n); y[0::2] = 100.0 * tr["a_pts"].to_numpy(float) / poss; y[1::2] = 100.0 * tr["b_pts"].to_numpy(float) / poss
        w, lt_f, nf = np.repeat(poss, 2), np.repeat(lt, 2), 2 * n
        partido = np.repeat(lt + "|" + tr["game_id"].astype(str).to_numpy(), 2)
    X = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(nf, len(comps) * nJ + len(fijos)))
    return Diseno(X=X, y=np.asarray(y, float), w=np.asarray(w, float), jugadores=jug, fijos=fijos, componentes=comps,
                  liga_temp=np.asarray(lt_f), partido=np.asarray(partido), idx_jugador=ij)


# =============================================================================================== prior g(x̃)
def tabla_prior(perf: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Matriz de rasgos del prior por persona-temporada (registro principal = más minutos) con la máscara de bloques."""
    K = int(cfg["perfil"]["latente"]["K"])
    X, E, R = rasgos(cfg), estilos(cfg), roles(cfg)
    p = perf.sort_values("min", ascending=False).drop_duplicates(["persona_id", "temporada"]).copy()
    out = pd.DataFrame({"clave": p["persona_id"].astype(str) + "|" + p["temporada"].astype(str),
                        "persona_id": p["persona_id"].astype(str), "temporada": p["temporada"].astype(str),
                        "liga": p["liga"].astype(str), "min": pd.to_numeric(p["min"], errors="coerce").to_numpy(float),
                        "persona_norm": p["persona_norm"].astype(str) if "persona_norm" in p else "",
                        "player_id": p["player_id"].astype(str) if "player_id" in p else ""})
    num = [f"u{k + 1}" for k in range(K)] + [f"p_{e}" for e in E] + [f"{m}_th" for m in X] + [f"p_{r}" for r in R] \
        + ["rol_indice_esperado", "min_pct", "gs_pct", "edad"]
    for c in num:
        out[c] = pd.to_numeric(p[c], errors="coerce").to_numpy(float) if c in p else np.nan
    for pos in ("E", "A", "I"):
        out[f"pos_{pos}"] = (p["pos3"] == pos).astype(float).to_numpy()
    caja = [m for m in X if m not in RASGOS_PISTA]
    pista = [m for m in X if m in RASGOS_PISTA]
    out["m_latente"] = out["u1"].notna().astype(float)
    out["m_estilos"] = out[f"p_{E[0]}"].notna().astype(float)
    out["m_theta_caja"] = out[[f"{m}_th" for m in caja]].notna().all(axis=1).astype(float)
    out["m_theta_pista"] = out[[f"{m}_th" for m in pista]].notna().all(axis=1).astype(float) if pista else 1.0
    out["m_rol"] = out["rol_indice_esperado"].notna().astype(float)
    # rasgos de la TEMPORADA ANTERIOR de la misma persona (p. ej. su RAPM normalizado de t−1): información legítima para el
    # prior de la temporada t, al contrario que el RAPM de la propia temporada (circular con los tramos que se ajustan)
    prev_cols = list(cfg["f1"]["prior"].get("rasgos_temporada_anterior", []))
    if prev_cols:
        ant = out[["persona_id", "temporada"] + [c for c in prev_cols if c in out]].copy()
        ant["temporada"] = ant["temporada"].map(lambda t: f"{int(t[:4]) + 1}-{str(int(t[:4]) + 2)[-2:]}")
        ant = ant.rename(columns={c: f"{c}_prev" for c in prev_cols})
        out = out.merge(ant, on=["persona_id", "temporada"], how="left")
        for c in prev_cols:
            if f"{c}_prev" not in out:
                out[f"{c}_prev"] = np.nan
        out["m_prev"] = out[[f"{c}_prev" for c in prev_cols]].notna().all(axis=1).astype(float)
    out.attrs["bloques"] = {"latente": [f"u{k + 1}" for k in range(K)], "estilos": [f"p_{e}" for e in E],
                            "rasgos": [f"{m}_th" for m in X], "rol": [f"p_{r}" for r in R] + ["rol_indice_esperado", "min_pct", "gs_pct"],
                            "edad": ["edad"], "pos3": ["pos_E", "pos_A", "pos_I"],
                            **({"temporada_anterior": [f"{c}_prev" for c in prev_cols]} if prev_cols else {}),
                            "mascara": ["m_latente", "m_estilos", "m_theta_caja", "m_theta_pista", "m_rol"] + (["m_prev"] if prev_cols else [])}
    return out.reset_index(drop=True)


class Prior:
    """g(x̃; γ): ridge (estandarizado, NaN → 0 tras estandarizar, con la máscara como indicadores) o GBM pequeño
    (NaN nativos). `bloques_fuera`: bloques del perfil que no entran (ablaciones, D2)."""

    def __init__(self, tipo: str, cfg: dict, bloques_fuera: tuple[str, ...] = ()):
        self.tipo, self.cfg, self.bloques_fuera = tipo, cfg, tuple(bloques_fuera)
        self.columnas, self.media, self.sd, self.modelo, self.alpha = None, None, None, None, None

    def _cols(self, T: pd.DataFrame) -> list[str]:
        bl = T.attrs["bloques"]
        fuera = set(self.cfg["f1"]["prior"].get("rasgos_fuera", []))      # rasgos que no entran en g (p. ej. el RAPM de la misma temporada)
        cols = []
        for b, cs in bl.items():
            if b in self.bloques_fuera:
                continue
            if b == "mascara" and not self.cfg["f1"].get("mascara_rasgos", True):
                continue
            cols += [c for c in cs if c not in fuera]
        return cols

    def ajustar(self, T: pd.DataFrame, y: np.ndarray, w: np.ndarray | None = None) -> "Prior":
        self.columnas = self._cols(T)
        M = T[self.columnas].to_numpy(float)
        if self.tipo == "ridge":
            from sklearn.linear_model import RidgeCV
            self.media = np.nanmean(M, 0); self.sd = np.nanstd(M, 0); self.sd[~np.isfinite(self.sd) | (self.sd == 0)] = 1.0
            self.media[~np.isfinite(self.media)] = 0.0
            Z = (M - self.media) / self.sd
            Z[~np.isfinite(Z)] = 0.0
            self.modelo = RidgeCV(alphas=[float(a) for a in self.cfg["f1"]["prior"]["ridge_alpha_rejilla"]]).fit(Z, y, sample_weight=w)
            self.alpha = float(self.modelo.alpha_)
        else:
            from sklearn.ensemble import HistGradientBoostingRegressor
            g = self.cfg["f1"]["prior"]["gbm"]
            self.modelo = HistGradientBoostingRegressor(max_iter=int(g["max_iter"]), learning_rate=float(g["learning_rate"]),
                                                        max_depth=int(g["max_depth"]), min_samples_leaf=int(g["min_samples_leaf"]),
                                                        l2_regularization=float(g["l2_regularization"]),
                                                        random_state=int(self.cfg["semilla"])).fit(M, y, sample_weight=w)
        return self

    def predecir(self, T: pd.DataFrame) -> np.ndarray:
        M = T[self.columnas].to_numpy(float)
        if self.tipo == "ridge":
            Z = (M - self.media) / self.sd
            Z[~np.isfinite(Z)] = 0.0
            return self.modelo.predict(Z)
        return self.modelo.predict(M)

    def exportable(self) -> dict:
        d = {"tipo": self.tipo, "columnas": self.columnas, "bloques_fuera": list(self.bloques_fuera)}
        if self.tipo == "ridge":
            d.update({"alpha": self.alpha, "intercepto": float(self.modelo.intercept_),
                      "coeficientes": dict(zip(self.columnas, map(float, self.modelo.coef_))),
                      "media": dict(zip(self.columnas, map(float, self.media))), "sd": dict(zip(self.columnas, map(float, self.sd)))})
        return d


# =============================================================================================== ajuste
def resolver(D: Diseno, g: np.ndarray, tau2: float | np.ndarray, sigma2: float, beta0: np.ndarray | None = None,
             filas: np.ndarray | None = None, varianza: str = "diagonal", sondas: int = 32, semilla: int = 0) -> tuple[np.ndarray, np.ndarray, dict]:
    """Posterior de β (media) dado el prior N(g, τ²) y σ²: ridge con media a priori. Devuelve β (nC·nJ), fijos, info.
    Sistema aumentado [√(n/σ²)·X ; (1/τ)·I_jugadores] · [δ; fijos] = [√(n/σ²)·(y − X_jug·g); 0], con δ = β − g, LSQR.
    `filas`: subconjunto de filas (validación cruzada). `varianza`: "diagonal" (1/(Σ n/σ² + 1/τ²), cota inferior) o
    "hutchinson" (diagonal de (AᵀA)⁻¹ estimada con `sondas` vectores de Rademacher y gradiente conjugado)."""
    nJ, nF = D.nC * D.nJ, len(D.fijos)
    X, y, w = (D.X, D.y, D.w) if filas is None else (D.X[filas], D.y[filas], D.w[filas])
    sw = np.sqrt(w / sigma2)
    Xw = sp.diags(sw) @ X
    yw = sw * (y - X[:, :nJ] @ g)
    tau = np.sqrt(np.broadcast_to(np.asarray(tau2, float), (nJ,)))
    pen = sp.hstack([sp.diags(1.0 / tau), sp.csr_matrix((nJ, nF))]).tocsr()
    A = sp.vstack([Xw, pen]).tocsr()
    b = np.r_[yw, np.zeros(nJ)]
    x0 = None if beta0 is None else np.r_[beta0 - g, np.zeros(nF)]
    sol = spla.lsqr(A, b, atol=1e-8, btol=1e-8, iter_lim=3000, x0=x0)
    x = sol[0]
    beta, fijos = g + x[:nJ], x[nJ:]
    prec = np.asarray((Xw[:, :nJ].multiply(Xw[:, :nJ])).sum(0)).ravel() + 1.0 / tau ** 2
    v = 1.0 / prec
    if varianza == "hutchinson":
        AtA = (A.T @ A).tocsr() + 1e-6 * sp.identity(A.shape[1], format="csr")
        rng = np.random.default_rng(semilla)
        acc = np.zeros(nJ)
        for _ in range(sondas):
            z = rng.choice([-1.0, 1.0], AtA.shape[0])
            xz, _ = spla.cg(AtA, z, rtol=1e-6, maxiter=2000, M=sp.diags(1.0 / np.maximum(AtA.diagonal(), 1e-6)))
            acc += (z * xz)[:nJ]
        v = np.maximum(acc / sondas, 0.25 * v)       # la diagonal de la información es cota inferior de la varianza
    r = y - X @ x - X[:, :nJ] @ g
    info = {"iteraciones_lsqr": int(sol[2]), "residuo_norm": float(sol[3]),
            "sigma2_residual": float(np.sum(w * r ** 2) / len(r)), "rmse_ponderado": float(np.sqrt(np.sum(w * r ** 2) / w.sum()))}
    return beta, fijos, {"v": v, "resid": r, "x": x, **info}


def tau_validacion_cruzada(D: Diseno, g: np.ndarray, sigma2: float, rejilla: list[float], pliegues: int, semilla: int) -> dict:
    """τ por validación cruzada por partido: para cada τ de la rejilla, ajusta en (k−1) pliegues y mide el error
    ponderado de los tramos del pliegue restante (la misma pérdida que la verosimilitud gaussiana con pesos n_s)."""
    rng = np.random.default_rng(semilla)
    part = np.unique(D.partido)
    asig = dict(zip(part, rng.integers(0, pliegues, len(part))))
    fold = np.array([asig[p] for p in D.partido])
    nJ = D.nC * D.nJ
    err = {}
    for tau in rejilla:
        e = 0.0
        for k in range(pliegues):
            tr_, te_ = np.where(fold != k)[0], np.where(fold == k)[0]
            _, _, info = resolver(D, g, float(tau) ** 2, sigma2, filas=tr_)
            x = info["x"]
            pred = D.X[te_] @ x + D.X[te_][:, :nJ] @ g
            e += float(np.sum(D.w[te_] * (D.y[te_] - pred) ** 2))
        err[float(tau)] = e / float(np.sum(D.w))
    best = min(err, key=err.get)
    return {"tau": best, "error_cv": err}


# =============================================================================================== ajuste conjunto (γ y β a la vez)
class _Operador(spla.LinearOperator):
    """A·[γ; δ; f] = [√(w/σ²)·(X_J Z γ + X_J δ + X_F f) ; δ/τ ; √α·γ]  (sistema aumentado del ridge con media a priori Zγ).
    X_J Z se precalcula denso (n × p); el resto queda disperso."""

    def __init__(self, XJ, XZ, XF, sw, tau, alpha):
        self.XJ, self.XZ, self.XF, self.sw = XJ, XZ, XF, sw
        self.n, self.nJ, self.p, self.nF = XJ.shape[0], XJ.shape[1], XZ.shape[1], XF.shape[1]
        self.tau, self.sa = np.broadcast_to(np.asarray(tau, float), (self.nJ,)), np.sqrt(alpha)
        super().__init__(dtype=np.float64, shape=(self.n + self.nJ + self.p, self.p + self.nJ + self.nF))

    def _matvec(self, x):
        x = np.asarray(x).ravel()
        g, d, f = x[:self.p], x[self.p:self.p + self.nJ], x[self.p + self.nJ:]
        top = self.sw * (self.XZ @ g + self.XJ @ d + self.XF @ f)
        return np.r_[top, d / self.tau, self.sa * g]

    def _rmatvec(self, r):
        r = np.asarray(r).ravel()
        rt, rd, rg = r[:self.n] * self.sw, r[self.n:self.n + self.nJ], r[self.n + self.nJ:]
        return np.r_[self.XZ.T @ rt + self.sa * rg, self.XJ.T @ rt + rd / self.tau, self.XF.T @ rt]


def resolver_conjunto(D: Diseno, Z: np.ndarray, tau2, sigma2: float, alpha: float, x0=None, varianza: str = "diagonal",
                      sondas: int = 32, semilla: int = 0) -> dict:
    """β_i = Z_i γ + δ_i con δ ~ N(0, τ²): γ (prior lineal) y δ se estiman a la vez por mínimos cuadrados penalizados
    (LSQR). Devuelve γ, β = Zγ + δ, g = Zγ, fijos, residuo y varianzas aproximadas."""
    nJ, nF, p = D.nC * D.nJ, len(D.fijos), Z.shape[1]
    XJ, XF = D.X[:, :nJ].tocsr(), D.X[:, nJ:].tocsr()
    XZ = np.asarray(XJ @ Z)
    sw = np.sqrt(D.w / sigma2)
    tau = np.sqrt(np.broadcast_to(np.asarray(tau2, float), (nJ,)))
    A = _Operador(XJ, XZ, XF, sw, tau, alpha)
    b = np.r_[sw * D.y, np.zeros(nJ), np.zeros(p)]
    sol = spla.lsqr(A, b, atol=1e-9, btol=1e-9, iter_lim=5000, x0=x0)
    x = sol[0]
    gamma, delta, fijos = x[:p], x[p:p + nJ], x[p + nJ:]
    g = Z @ gamma
    beta = g + delta
    prec = np.asarray((XJ.multiply(XJ)).T @ (sw ** 2)).ravel() + 1.0 / tau ** 2
    v = 1.0 / prec
    if varianza == "hutchinson":
        rng = np.random.default_rng(semilla)
        eps = 1e-6                                  # columnas fijas vacías (p. ej. sin playoffs) harían singular AᵀA
        AtA = spla.LinearOperator((A.shape[1], A.shape[1]), matvec=lambda z: A.rmatvec(A.matvec(z)) + eps * z, dtype=np.float64)
        diag = np.r_[np.sum(XZ ** 2 * sw[:, None] ** 2, 0) + alpha, prec, np.asarray((XF.multiply(XF)).T @ (sw ** 2)).ravel()] + eps
        M = spla.LinearOperator(AtA.shape, matvec=lambda z: z / diag, dtype=np.float64)
        acc = np.zeros(nJ)
        for _ in range(sondas):
            z = rng.choice([-1.0, 1.0], A.shape[1])
            xz, _ = spla.cg(AtA, z, rtol=1e-6, maxiter=3000, M=M)
            acc += (z * xz)[p:p + nJ]
        v = np.maximum(acc / sondas, 0.25 * v)
    r = D.y - (XZ @ gamma + XJ @ delta + XF @ fijos)
    return {"gamma": gamma, "beta": beta, "g": g, "delta": delta, "fijos": fijos, "v": v, "resid": r, "x": x,
            "iteraciones_lsqr": int(sol[2]), "sigma2_residual": float(np.sum(D.w * r ** 2) / len(r)),
            "rmse_ponderado": float(np.sqrt(np.sum(D.w * r ** 2) / D.w.sum())), "XZ": XZ}


def log_marginal(D: Diseno, res: dict, tau2: float, sigma2: float, lu_cache: dict | None = None) -> float:
    """log p(y | τ², σ²) (hasta una constante), con γ y los efectos fijos en su estimación:
    −½ [ log|I + (τ²/σ²) X_JᵀWX_J| + (rᵀWr + δᵀδ/τ²)/σ² + Σ log(σ²/w_s) ]."""
    nJ = D.nC * D.nJ
    XJ = D.X[:, :nJ]
    if lu_cache is not None and "M0" in lu_cache:
        M0 = lu_cache["M0"]
    else:
        M0 = (XJ.T @ sp.diags(D.w) @ XJ).tocsc()
        if lu_cache is not None:
            lu_cache["M0"] = M0
    M = (sp.identity(nJ, format="csc") + (tau2 / sigma2) * M0).tocsc()
    lu = spla.splu(M)
    logdet = float(np.sum(np.log(np.abs(lu.U.diagonal()))))
    quad = (np.sum(D.w * res["resid"] ** 2) + np.sum(res["delta"] ** 2) / tau2) / sigma2
    return -0.5 * (logdet + quad + len(D.y) * np.log(sigma2) - np.sum(np.log(D.w)))


def log_marginal_conjunto(D: Diseno, Z: np.ndarray, res: dict, tau2: float, alpha: float, sigma2: float, cache: dict) -> float:
    """log p(y | τ², α, σ²) con γ ~ N(0, I/α) y δ ~ N(0, τ² I) integrados (efectos fijos en su estimación):
    −½ [ log|P + XᵀWX/σ²| − log|P| + (rᵀWr/σ² + α γᵀγ + δᵀδ/τ²) + Σ log(σ²/w_s) ],  P = diag(α·1_p, 1_nJ/τ²),
    X = [X_J Z, X_J]. La matriz tiene un borde denso de p filas/columnas; la LU dispersa lo absorbe."""
    nJ = D.nC * D.nJ
    p = Z.shape[1]
    if "bloques" not in cache:
        XJ = D.X[:, :nJ].tocsr()
        W = sp.diags(D.w)
        XZ = sp.csr_matrix(res["XZ"]) if "XZ" in res else sp.csr_matrix(np.asarray(XJ @ Z))
        cache["bloques"] = {"ZZ": (XZ.T @ W @ XZ).toarray(), "ZJ": (XZ.T @ W @ XJ).toarray(), "JJ": (XJ.T @ W @ XJ).tocsc()}
    B = cache["bloques"]
    ZZ = sp.csc_matrix(B["ZZ"] / sigma2 + alpha * np.eye(p))
    ZJ = sp.csc_matrix(B["ZJ"] / sigma2)
    JJ = (B["JJ"] / sigma2 + sp.identity(nJ, format="csc") / tau2).tocsc()
    M = sp.bmat([[ZZ, ZJ], [ZJ.T, JJ]], format="csc")
    lu = spla.splu(M)
    logdet = float(np.sum(np.log(np.abs(lu.U.diagonal())))) - (p * np.log(alpha) - nJ * np.log(tau2))
    quad = np.sum(D.w * res["resid"] ** 2) / sigma2 + alpha * float(res["gamma"] @ res["gamma"]) + float(res["delta"] @ res["delta"]) / tau2
    return -0.5 * (logdet + quad + len(D.y) * np.log(sigma2) - np.sum(np.log(D.w)))


def matriz_Z(D: Diseno, T: pd.DataFrame | None, cfg: dict, bloques_fuera=(), columnas: list[str] | None = None):
    """Z (nJ × p): rasgos estandarizados del prior por jugador (NaN → 0 tras estandarizar) + constante + indicador «sin
    perfil». Quien no tiene perfil recibe la media de Z de los jugadores con perfil de su temporada. Devuelve Z, los
    nombres de columna y la estandarización (para predecir el prior de jugadores nuevos)."""
    nJ = D.nJ
    temp_j = np.array([k.rsplit("|", 1)[1] for k in D.jugadores])
    if T is None or not len(T):
        Z = np.c_[np.ones(nJ)]
        return np.tile(Z, (D.nC, 1)), ["const"], {"media": {}, "sd": {}}
    cols = columnas or Prior("ridge", cfg, bloques_fuera)._cols(T)
    ix = {k: i for i, k in enumerate(T["clave"])}
    fila = np.array([ix.get(k, -1) for k in D.jugadores])
    con = fila >= 0
    M = np.full((nJ, len(cols)), np.nan)
    M[con] = T.iloc[fila[con]][cols].to_numpy(float)
    media = np.nanmean(M[con], 0); sd = np.nanstd(M[con], 0)
    sd[~np.isfinite(sd) | (sd == 0)] = 1.0; media[~np.isfinite(media)] = 0.0
    Zc = (M - media) / sd
    Zc[~np.isfinite(Zc)] = 0.0
    for tp in np.unique(temp_j):
        m = (temp_j == tp) & con
        if m.any():
            Zc[(temp_j == tp) & ~con] = Zc[m].mean(0)
    Z = np.c_[np.ones(nJ), Zc, (~con).astype(float)]
    nombres = ["const"] + cols + ["sin_perfil"]
    return np.tile(Z, (D.nC, 1)) if D.nC > 1 else Z, nombres, {"media": dict(zip(cols, media)), "sd": dict(zip(cols, sd)), "columnas": cols}


class PriorLineal:
    """Prior g(x̃) = γ₀ + Σ γ_k z_k ajustado CONJUNTAMENTE con β (resolver_conjunto); predice para jugadores nuevos."""
    tipo = "ridge"

    def __init__(self, gamma: np.ndarray, nombres: list[str], est: dict, bloques_fuera=()):
        self.gamma, self.nombres, self.est, self.bloques_fuera = np.asarray(gamma, float), list(nombres), est, tuple(bloques_fuera)
        self.columnas, self.alpha = est.get("columnas", []), None

    def predecir(self, T: pd.DataFrame) -> np.ndarray:
        cols = self.est["columnas"]
        M = T[cols].to_numpy(float)
        Z = (M - np.array([self.est["media"][c] for c in cols])) / np.array([self.est["sd"][c] for c in cols])
        Z[~np.isfinite(Z)] = 0.0
        g = self.gamma[0] + Z @ self.gamma[1:1 + len(cols)]
        return g

    def exportable(self) -> dict:
        return {"tipo": "ridge_conjunto", "columnas": self.nombres, "coeficientes": dict(zip(self.nombres, map(float, self.gamma))),
                "media": {k: float(v) for k, v in self.est["media"].items()}, "sd": {k: float(v) for k, v in self.est["sd"].items()},
                "bloques_fuera": list(self.bloques_fuera)}


def ajustar(D: Diseno, T: pd.DataFrame | None, cfg: dict, tipo_prior: str = "ridge", bloques_fuera: tuple[str, ...] = (),
            progreso=print) -> dict:
    """Bayes empírico (verosimilitud marginal) con prior lineal conjunto. `tipo_prior = "ridge"`: g = Zγ estimado a la
    vez que β (sin atenuación). `tipo_prior = "gbm"`: parte del ajuste conjunto y reajusta el prior con un GBM sobre
    β̂ (retroajuste, `f1.prior.gbm.retroajustes` ciclos), con τ reestimado por verosimilitud marginal."""
    f1 = cfg["f1"]; eb = f1["bayes_empirico"]
    nJ, nC = D.nJ, D.nC
    poss_j = np.asarray(abs(D.X[:, :nC * nJ]).T @ D.w).ravel()
    rejilla_alpha = [float(x) for x in f1["prior"].get("ridge_alpha_rejilla", [1.0])]
    Z, nombres, est = matriz_Z(D, T, cfg, bloques_fuera)
    con_prior = ~(Z[:nJ, -1] > 0) if Z.shape[1] > 1 else np.zeros(nJ, bool)
    rejilla = [float(x) for x in eb["tau_rejilla"]]
    sigma2 = float(np.sum(D.w * (D.y - np.average(D.y, weights=D.w)) ** 2) / len(D.y))
    t0 = time.time()
    hist, cache = [], {}
    tau2, alpha = float(eb["tau2_inicial"]), rejilla_alpha[0]
    res = None
    for it in range(int(eb["iteraciones"])):
        ll = {}
        x0 = None
        for a_ in rejilla_alpha:                         # γ ~ N(0, I/α) y δ ~ N(0, τ²): los dos por verosimilitud marginal
            for tau in rejilla:
                r = resolver_conjunto(D, Z, tau ** 2, sigma2, a_, x0=x0)
                x0 = r["x"]
                ll[(a_, tau)] = log_marginal_conjunto(D, Z, r, tau ** 2, a_, sigma2, cache)
        alpha, tau_best = max(ll, key=ll.get)
        tau2 = tau_best ** 2
        res = resolver_conjunto(D, Z, tau2, sigma2, alpha, x0=x0)
        sigma2 = max(res["sigma2_residual"], 1e-6)
        cache.pop("bloques", None)                       # σ² cambia: los bloques se reescalan dentro, pero se recalculan por claridad
        hist.append({"iteracion": it + 1, "tau": tau_best, "alpha": alpha, "sigma": float(np.sqrt(sigma2)), "rmse_ponderado": res["rmse_ponderado"],
                     "log_marginal_por_alpha_tau": {f"{k[0]}|{k[1]}": float(v) for k, v in ll.items()}, "lsqr_it": res["iteraciones_lsqr"],
                     "t_s": round(time.time() - t0)})
        if progreso:
            progreso(f"    EB {it + 1}/{eb['iteraciones']}: τ* {tau_best} · α* {alpha} · σ {np.sqrt(sigma2):.1f} · rmse {res['rmse_ponderado']:.3f} · {time.time() - t0:.0f} s", flush=True)
    priors = []
    for c in range(nC):
        pr = PriorLineal(res["gamma"], nombres, est, bloques_fuera)      # el mismo γ para todos los componentes si nC > 1 (Z apilada)
        priors.append(pr)
    g, beta, v = res["g"], res["beta"], res["v"]
    if tipo_prior == "gbm" and T is not None and con_prior.sum() >= 50:
        # retroajuste: GBM sobre β̂ de los jugadores con perfil y exposición mínima; τ por verosimilitud marginal
        ix = {k: i for i, k in enumerate(T["clave"])}
        fila = np.array([ix.get(k, -1) for k in D.jugadores])
        Tj = T.iloc[np.where(fila >= 0, fila, 0)].reset_index(drop=True)
        for ciclo in range(int(f1["prior"]["gbm"].get("retroajustes", 2))):
            g_new = np.zeros_like(g)
            priors = []
            for c in range(nC):
                sl = slice(c * nJ, (c + 1) * nJ)
                sel = con_prior & (poss_j[sl] >= float(f1["min_posesiones_jugador"]))
                pr = Prior("gbm", cfg, bloques_fuera).ajustar(Tj[sel], beta[sl][sel])
                gc = pr.predecir(Tj); gc[~con_prior] = np.nan
                temp_j = np.array([k.rsplit("|", 1)[1] for k in D.jugadores])
                for tp in np.unique(temp_j):
                    m = (temp_j == tp) & np.isfinite(gc)
                    gc[(temp_j == tp) & ~np.isfinite(gc)] = float(np.average(gc[m], weights=np.maximum(poss_j[sl][m], 1.0))) if m.any() else 0.0
                g_new[sl] = gc; priors.append(pr)
            g = g_new
            ll = {}
            for tau in rejilla:
                b_, f_, info = resolver(D, g, tau ** 2, sigma2)
                ll[tau] = log_marginal(D, {"resid": info["resid"], "delta": b_ - g}, tau ** 2, sigma2, cache)
            tau2 = max(ll, key=ll.get) ** 2
            beta, fijos, info = resolver(D, g, tau2, sigma2, varianza="diagonal")
            v = info["v"]
            sigma2 = max(info["sigma2_residual"], 1e-6)
            res = {**res, "beta": beta, "g": g, "delta": beta - g, "fijos": fijos, "v": v, "resid": info["resid"],
                   "rmse_ponderado": info["rmse_ponderado"], "iteraciones_lsqr": info["iteraciones_lsqr"]}
            hist.append({"iteracion": f"gbm_{ciclo + 1}", "tau": float(np.sqrt(tau2)), "sigma": float(np.sqrt(sigma2)),
                         "rmse_ponderado": info["rmse_ponderado"], "log_marginal_por_tau": {str(k): float(v_) for k, v_ in ll.items()}})
            if progreso:
                progreso(f"    GBM {ciclo + 1}: τ* {np.sqrt(tau2):.2f} · rmse {info['rmse_ponderado']:.3f}", flush=True)
    var_final = str(eb.get("varianza_final", "diagonal"))
    if var_final == "hutchinson":
        if tipo_prior == "gbm":
            _, _, info = resolver(D, g, tau2, sigma2, varianza="hutchinson", sondas=int(eb.get("sondas_hutchinson", 32)), semilla=int(cfg["semilla"]))
        else:
            info = resolver_conjunto(D, Z, tau2, sigma2, alpha, x0=res["x"], varianza="hutchinson", sondas=int(eb.get("sondas_hutchinson", 32)), semilla=int(cfg["semilla"]))
        v = info["v"]
    tau_vec = np.full(nC * nJ, tau2)
    peso_prior = np.clip(v / tau_vec, 0.0, 1.0)
    return {"beta": beta, "sd": np.sqrt(v), "g": g, "fijos": dict(zip(D.fijos, map(float, res["fijos"]))), "tau2": [float(tau2)] * nC,
            "sigma2": sigma2, "poss": poss_j, "con_prior": con_prior, "peso_prior": peso_prior, "priors": priors,
            "historial": hist, "componentes": D.componentes, "jugadores": D.jugadores, "tipo_prior": tipo_prior,
            "bloques_fuera": list(bloques_fuera), "metodo_tau": "verosimilitud_marginal", "alpha": float(alpha), "varianza": var_final,
            "gamma": {k: float(x) for k, x in zip(nombres, res["gamma"])},
            "info_final": {"iteraciones_lsqr": res["iteraciones_lsqr"], "rmse_ponderado": res["rmse_ponderado"]}}


def tabla_beta(res: dict, D: Diseno) -> pd.DataFrame:
    """Una fila por persona-temporada con β, sd, prior, peso del prior y exposición (por componente)."""
    nJ = D.nJ
    out = pd.DataFrame({"clave": D.jugadores})
    out["persona_id"] = out["clave"].str.rsplit("|", n=1).str[0]
    out["temporada"] = out["clave"].str.rsplit("|", n=1).str[1]
    for c, comp in enumerate(D.componentes):
        sl = slice(c * nJ, (c + 1) * nJ)
        suf = "" if comp == "net" else f"_{comp}"
        out[f"beta{suf}"] = res["beta"][sl]
        out[f"beta_sd{suf}"] = res["sd"][sl]
        out[f"prior{suf}"] = res["g"][sl]
        out[f"peso_prior{suf}"] = res["peso_prior"][sl]
        out[f"poss{suf}"] = res["poss"][sl]
    if "def" in D.componentes:
        out["orapm"] = out["beta_of"]
        out["drapm"] = -out["beta_def"]
        out["rapm_od"] = out["orapm"] + out["drapm"]
    out["con_perfil"] = res["con_prior"]
    return out


def ligas_jugador(tr: pd.DataFrame) -> pd.DataFrame:
    """Liga principal (más posesiones) y posesiones por liga de cada persona-temporada."""
    a = tr[["A", "liga", "poss"]].explode("A").rename(columns={"A": "clave"})
    b = tr[["B", "liga", "poss"]].explode("B").rename(columns={"B": "clave"})
    x = pd.concat([a, b]).groupby(["clave", "liga"])["poss"].sum().reset_index()
    x = x.sort_values("poss", ascending=False)
    princ = x.drop_duplicates("clave").rename(columns={"liga": "liga_principal", "poss": "poss_liga_principal"})
    n_ligas = x.groupby("clave").size().rename("n_ligas")
    return princ.merge(n_ligas, on="clave")


# =============================================================================================== producto
def exportar(cfg: dict, progreso=print) -> dict:
    """Ajuste con todas las temporadas incluidas (producto): β por persona-temporada (net y O/D) y el prior g."""
    from bbfit.registro import experimento
    t0 = time.time()
    tr = tramos(cfg, None, progreso)
    tipo, bloques_fuera = cfg["f1"]["prior"].get("elegido"), ()
    dec = dir_salida(cfg) / "examen" / "resumen_examen.json"
    if dec.exists():                                   # decisiones del examen (corte de selección): prior y bloques fuera
        d = json.loads(dec.read_text(encoding="utf-8")).get("decisiones", {})
        tipo = tipo or d.get("prior", {}).get("elegido")
        bloques_fuera = tuple(d.get("bloques_fuera", []))
    tipo = tipo or cfg["f1"]["prior"]["candidatos"][0]
    pr = cfg["f1"].get("producto") or {}
    if pr:                                             # rejillas reducidas a lo que eligió el examen (cfg local a esta función)
        cfg = C.con(cfg, **{"f1.bayes_empirico.tau_rejilla": pr.get("tau_rejilla", cfg["f1"]["bayes_empirico"]["tau_rejilla"]),
                            "f1.prior.ridge_alpha_rejilla": pr.get("ridge_alpha_rejilla", cfg["f1"]["prior"]["ridge_alpha_rejilla"])})
    perf = pd.concat([pd.read_csv(C.dir_salida(cfg) / "perfiles" / f"{t}.csv.gz", low_memory=False)
                      for t in sorted(tr["temporada"].unique())], ignore_index=True)
    T = tabla_prior(perf, cfg)
    out = dir_salida(cfg)
    with experimento(cfg["mlflow"], "F1_producto", params={"tipo_prior": tipo, "tramos": len(tr)}) as run:
        res = {}
        for comp in ("net", "od"):
            if progreso:
                progreso(f"  ajuste {comp}: diseño…", flush=True)
            D = construir_diseno(tr, comp)
            cache = C.RAIZ / "experimentos" / "v4_0" / f"producto_f1_{comp}_{tipo}_{C.huella(cfg, ('f1', 'contrato'))}.pkl"
            if cache.exists():                         # reanudable: el ajuste de cada componente se guarda al terminar
                r = pickle.loads(cache.read_bytes())
                if progreso:
                    progreso(f"    {comp}: ajuste reutilizado de {cache.name}", flush=True)
            else:
                r = ajustar(D, T, cfg, tipo, bloques_fuera, progreso=progreso)
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(pickle.dumps({k: v for k, v in r.items() if k != "XZ"}))
            res[comp] = (D, r)
            import gc; gc.collect()
        tb = tabla_beta(res["net"][1], res["net"][0]).merge(
            tabla_beta(res["od"][1], res["od"][0])[["clave", "beta_of", "beta_sd_of", "prior_of", "beta_def", "beta_sd_def", "prior_def",
                                                   "orapm", "drapm", "rapm_od"]], on="clave", how="left")
        tb = tb.merge(ligas_jugador(tr), on="clave", how="left")
        cols = ["persona_id", "temporada", "liga_principal", "n_ligas", "beta", "beta_sd", "prior", "peso_prior", "poss",
                "orapm", "drapm", "rapm_od", "beta_of", "beta_sd_of", "prior_of", "beta_def", "beta_sd_def", "prior_def", "con_perfil"]
        for t, g in tb.groupby("temporada"):
            g[cols].round(4).to_csv(out / f"{t}.csv.gz", index=False)
        rn = res["net"][1]
        doc = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "huella_config": C.huella(cfg, ("f1", "perfil", "contrato")),
               "tramos": int(len(tr)), "jugadores": int(res["net"][0].nJ), "tipo_prior": tipo, "bloques_fuera": list(bloques_fuera),
               "net": {"tau": [float(np.sqrt(x)) for x in rn["tau2"]], "sigma": float(np.sqrt(rn["sigma2"])), "fijos": rn["fijos"],
                       "historial": rn["historial"], "prior": rn["priors"][0].exportable() if rn["priors"][0] else None},
               "od": {"tau": [float(np.sqrt(x)) for x in res["od"][1]["tau2"]], "sigma": float(np.sqrt(res["od"][1]["sigma2"])),
                      "fijos": res["od"][1]["fijos"], "historial": res["od"][1]["historial"],
                      "prior_of": res["od"][1]["priors"][0].exportable() if res["od"][1]["priors"][0] else None,
                      "prior_def": res["od"][1]["priors"][1].exportable() if res["od"][1]["priors"][1] else None},
               "resumen_beta": {"sd_beta": float(tb["beta"].std()), "sd_prior": float(tb["prior"].std()),
                                "corr_beta_prior": float(tb[["beta", "prior"]].corr().iloc[0, 1]),
                                "peso_prior_mediano": float(tb["peso_prior"].median()),
                                "sin_perfil": int((~tb["con_perfil"]).sum())},
               "tiempo_s": round(time.time() - t0)}
        (C.RAIZ / cfg["f1"]["salidas"]["prior"]).write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
        if tipo == "gbm":
            (out / "g_prior_gbm.pkl").write_bytes(pickle.dumps({"net": rn["priors"][0], "of": res["od"][1]["priors"][0], "def": res["od"][1]["priors"][1]}))
        run.metricas({"tau_net": doc["net"]["tau"][0], "sigma_net": doc["net"]["sigma"], "corr_beta_prior": doc["resumen_beta"]["corr_beta_prior"]})
    if progreso:
        progreso(f"  F1 producto: {len(tb)} personas-temporada · τ {doc['net']['tau']} · {doc['tiempo_s']} s", flush=True)
    return doc
