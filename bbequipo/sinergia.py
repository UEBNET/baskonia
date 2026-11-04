"""F2-A · Sinergia simétrica de pares (capa 2; encargo §7). Sobre F1, congelando β:

    y_s = [F1] + Σ_{(i,j)∈A_s} φ(i,j) − Σ_{(i,j)∈B_s} φ(i,j) + ε_s,     φ(i,j) = z_iᵀ W z_j + ψ_ij

* z_i: rasgos estandarizados del perfil ampliado (las mismas columnas que el prior de F1: sin el RAPM de la misma
  temporada). φ por perfiles = z_iᵀ M z_j con M simétrica (p × p). Para un quinteto, Σ_{a<b} z_aᵀ M z_b = ⟨M, Q⟩ con
  Q = ((Σz)(Σz)ᵀ − Σ z zᵀ)/2: la suma de las 10 parejas de un quinteto se calcula sin enumerar parejas. Por tramo,
  u_s = vec(Q_A − Q_B) (diagonal × 1, fuera de la diagonal × 2) y el modelo es lineal en m = vec(M):
  r_s = u_sᵀ m + ε_s con r_s el RESIDUO de F1 y pesos n_s/σ². m por ridge con λ por verosimilitud marginal (G = Σ w u uᵀ
  es denso de p(p+1)/2 ≈ 1.500 filas: todo exacto por autovalores).
* Proyección de rango r (encargo: r ∈ {4, 6, 8}): M_r = P_r W_r P_rᵀ con los r autovectores de mayor |autovalor|; r se
  elige en el corte de selección con el examen de parejas nuevas (§11.2). Pareja nueva: φ̂ = z_iᵀ M_r z_j, sólo perfiles.
* ψ_ij ~ N(0, κ²): efecto propio de cada pareja observada (ridge disperso sobre indicadores de pareja, sobre el residuo
  tras M), κ por validación cruzada por partido; sólo para parejas con historia (producto/F4), nunca para predecir
  parejas nuevas.
Salidas: data/modelos/v4_0/sinergia/.
"""
from __future__ import annotations

import json
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from . import config as C
from . import rapm as RP


def dir_salida(cfg: dict) -> Path:
    d = C.RAIZ / cfg["f2"]["salida"]
    d.mkdir(parents=True, exist_ok=True)
    return d


# =============================================================================================== rasgos z por persona-temporada
class Rasgos:
    """z_i estandarizados (NaN → 0, columnas del prior de F1) por clave persona|temporada; sin perfil → vector 0."""

    def __init__(self, T: pd.DataFrame, cfg: dict):
        pr = RP.Prior("ridge", cfg, ())
        self.columnas = pr._cols(T)
        M = T[self.columnas].to_numpy(float)
        self.media = np.nanmean(M, 0); self.sd = np.nanstd(M, 0)
        self.sd[~np.isfinite(self.sd) | (self.sd == 0)] = 1.0; self.media[~np.isfinite(self.media)] = 0.0
        Z = (M - self.media) / self.sd
        Z[~np.isfinite(Z)] = 0.0
        self.Z = Z
        self.idx = {k: i for i, k in enumerate(T["clave"])}
        self.p = len(self.columnas)

    def de(self, claves) -> np.ndarray:
        """Matriz (n × p) de z para una secuencia de claves; vector 0 para quien no tiene perfil."""
        out = np.zeros((len(claves), self.p))
        for n, k in enumerate(claves):
            i = self.idx.get(k)
            if i is not None:
                out[n] = self.Z[i]
        return out

    def exportable(self) -> dict:
        return {"columnas": self.columnas, "media": dict(zip(self.columnas, map(float, self.media))),
                "sd": dict(zip(self.columnas, map(float, self.sd)))}


def _iu(p: int):
    iu = np.triu_indices(p)
    pesos = np.where(iu[0] == iu[1], 1.0, 2.0)
    return iu, pesos


def q_quinteto(Z5: np.ndarray) -> np.ndarray:
    """Q (n × p × p) = ((Σz)(Σz)ᵀ − Σ z zᵀ)/2 = Σ_{a<b} (z_a z_bᵀ + z_b z_aᵀ)/2 para n quintetos (n × 5 × p)."""
    S = Z5.sum(1)
    return 0.5 * (np.einsum("nk,nl->nkl", S, S) - np.einsum("nak,nal->nkl", Z5, Z5))


def rasgos_tramos(tr: pd.DataFrame, R: Rasgos, lote: int = 20000):
    """Generador de (índices, U) con U (n × p(p+1)/2) = vec(Q_A − Q_B) con pesos de simetría, por lotes."""
    p = R.p
    iu, pesos = _iu(p)
    for a in range(0, len(tr), lote):
        g = tr.iloc[a:a + lote]
        ZA = R.de([k for q in g["A"] for k in q]).reshape(len(g), 5, p)
        ZB = R.de([k for q in g["B"] for k in q]).reshape(len(g), 5, p)
        Q = q_quinteto(ZA) - q_quinteto(ZB)
        yield np.arange(a, a + len(g)), Q[:, iu[0], iu[1]] * pesos


def vec_a_matriz(m: np.ndarray, p: int) -> np.ndarray:
    iu, _ = _iu(p)
    M = np.zeros((p, p))
    M[iu] = m
    M = M + M.T - np.diag(np.diag(M))
    return M


def phi_pareja(M: np.ndarray, zi: np.ndarray, zj: np.ndarray) -> np.ndarray:
    return np.einsum("nk,kl,nl->n", np.atleast_2d(zi), M, np.atleast_2d(zj))


# =============================================================================================== residuo de F1
def mu_f1(cfg: dict, aj: dict, tr: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """μ_F1 de cada tramo con el ajuste de F1 `aj` (corte t): β̂_t para quien lo tiene, prior g_t para quien tiene perfil
    sin tramos, media de β̂ de su liga para los nuevos (misma regla que examen_f1.examen_margen). Devuelve (μ, fracción de
    puestos «nuevos» por tramo)."""
    from .examen_f1 import perfiles_corte  # noqa: F401 (misma convención)
    res, D, T, tb = aj["res"], aj["D"], aj["T"], aj["tb"]
    c = res["fijos"]
    temps = sorted(set(k.rsplit("|", 1)[1] for k in D.jugadores))
    beta = dict(zip(D.jugadores, res["beta"][:D.nJ]))
    pr = res["priors"][0]
    g_all = dict(zip(T["clave"], pr.predecir(T))) if pr is not None else {}
    media_liga = tb.groupby(["liga_principal", "temporada"]).apply(
        lambda g: np.average(g["beta"], weights=np.maximum(g["poss"], 1.0))).to_dict()
    c_media = float(np.mean([v for k, v in c.items() if k.startswith("c_")]))
    kcl, kpo = c.get("clutch", 0.0), c.get("playoffs", 0.0)
    ultima = {}
    for k, v in c.items():
        if k.startswith("c_"):
            l, t = k[2:].split("|")
            if l not in ultima or t > ultima[l][0]:
                ultima[l] = (t, v)
    mu = np.zeros(len(tr)); nuevos = np.zeros(len(tr))
    for s, row in enumerate(tr.itertuples()):
        ct = c.get(f"c_{row.liga}|{row.temporada}")
        if ct is None:
            ct = ultima.get(row.liga, (None, c_media))[1]
        tot = ct + (kcl if row.clutch else 0.0) + (kpo if row.playoffs else 0.0)
        n_new = 0
        for sign, q in ((1.0, row.A), (-1.0, row.B)):
            for k in q:
                if k in beta:
                    v = beta[k]
                elif k in g_all:
                    v = g_all[k]
                else:
                    temp = k.rsplit("|", 1)[1]
                    v = media_liga.get((row.liga, temp), media_liga.get((row.liga, temps[-1]), 0.0)); n_new += 1
                tot += sign * v
        mu[s] = tot; nuevos[s] = n_new / 10.0
    return mu, nuevos


# =============================================================================================== ajuste de M
def acumular(tr: pd.DataFrame, R: Rasgos, r: np.ndarray, w: np.ndarray, progreso=None):
    """G = Σ w u uᵀ, b = Σ w u r, rr = Σ w r² por lotes (todo denso de dimensión p(p+1)/2)."""
    q = R.p * (R.p + 1) // 2
    G = np.zeros((q, q)); b = np.zeros(q); rr = 0.0
    t0 = time.time()
    for idx, U in rasgos_tramos(tr, R):
        Uw = U * w[idx][:, None]
        G += Uw.T @ U; b += Uw.T @ r[idx]; rr += float(np.sum(w[idx] * r[idx] ** 2))
        if progreso and idx[0] % 200000 == 0:
            progreso(f"    rasgos de pareja: {idx[-1] + 1}/{len(tr)} tramos · {time.time() - t0:.0f} s", flush=True)
    return G, b, rr


def ajustar_M(G: np.ndarray, b: np.ndarray, rr: float, n: int, sigma2: float, rejilla_lambda: list[float]) -> dict:
    """m = (G/σ² + λI)⁻¹ b/σ² con λ (precisión a priori de m) por verosimilitud marginal exacta (autovalores de G)."""
    g, V = np.linalg.eigh(G)
    g = np.maximum(g, 0.0)
    bv = V.T @ b
    ll = {}
    for lam in rejilla_lambda:
        d = g / sigma2 + lam
        quad = (rr - np.sum(bv ** 2 / d) / sigma2) / sigma2
        logdet = float(np.sum(np.log1p(g / (sigma2 * lam))))
        ll[lam] = -0.5 * (logdet + quad)
    lam = max(ll, key=ll.get)
    m = V @ (bv / sigma2 / (g / sigma2 + lam))
    return {"m": m, "lambda": float(lam), "log_marginal": {str(k): float(v) for k, v in ll.items()}, "autovalores_G": g}


def truncar(M: np.ndarray, r: int | None) -> tuple[np.ndarray, dict]:
    """M_r con los r autovectores de mayor |autovalor| (r = None: completa). Devuelve M_r y (P_r, w_r)."""
    w, P = np.linalg.eigh(M)
    orden = np.argsort(-np.abs(w))
    if r is not None:
        orden = orden[:r]
    Pr, wr = P[:, orden], w[orden]
    return (Pr * wr) @ Pr.T, {"P": Pr, "w": wr}


# =============================================================================================== ψ por pareja
def psi_parejas(tr: pd.DataFrame, r2: np.ndarray, w: np.ndarray, sigma2: float, rejilla_kappa: list[float], pliegues: int,
                semilla: int, min_poss: float, progreso=None) -> dict:
    """ψ_ij ~ N(0, κ²) por pareja observada (ridge disperso sobre indicadores, sobre el residuo r2 tras M); κ por validación
    cruzada por partido. Devuelve {clave_pareja: (ψ, posesiones)} y κ."""
    pares = {}
    rows, cols, vals = [], [], []
    for s, row in enumerate(tr.itertuples()):
        for sign, q in ((1.0, row.A), (-1.0, row.B)):
            for a in range(5):
                for b_ in range(a + 1, 5):
                    k = (q[a], q[b_]) if q[a] < q[b_] else (q[b_], q[a])
                    j = pares.get(k)
                    if j is None:
                        j = pares[k] = len(pares)
                    rows.append(s); cols.append(j); vals.append(sign)
    n, nP = len(tr), len(pares)
    X = sp.csr_matrix((np.array(vals), (np.array(rows), np.array(cols))), shape=(n, nP))
    poss_par = np.asarray(abs(X).T @ w).ravel()
    sw = np.sqrt(w / sigma2)
    Xw = sp.diags(sw) @ X
    yw = sw * r2
    rng = np.random.default_rng(semilla)
    part = np.unique(tr["partido"].to_numpy() if "partido" in tr else (tr["liga"] + "|" + tr["temporada"] + "|" + tr["game_id"].astype(str)).to_numpy())
    pid = (tr["liga"] + "|" + tr["temporada"] + "|" + tr["game_id"].astype(str)).to_numpy()
    asig = dict(zip(part, rng.integers(0, pliegues, len(part))))
    fold = np.array([asig[p_] for p_ in pid])

    def resolver(kappa, filas):
        A = sp.vstack([Xw[filas], sp.diags(np.full(nP, 1.0 / kappa))]).tocsr()
        bb = np.r_[yw[filas], np.zeros(nP)]
        return spla.lsqr(A, bb, atol=1e-8, btol=1e-8, iter_lim=2000)[0]

    err = {}
    for kappa in rejilla_kappa:
        e = 0.0
        for k in range(pliegues):
            trn, te = np.where(fold != k)[0], np.where(fold == k)[0]
            psi = resolver(kappa, trn)
            e += float(np.sum(w[te] * (r2[te] - X[te] @ psi) ** 2))
        err[float(kappa)] = e
        if progreso:
            progreso(f"    ψ · κ = {kappa}: error CV {e / w.sum():.4f}", flush=True)
    kappa = min(err, key=err.get)
    psi = resolver(kappa, np.arange(n))
    out = {k: (float(psi[j]), float(poss_par[j])) for k, j in pares.items() if poss_par[j] >= min_poss}
    return {"psi": out, "kappa": kappa, "error_cv": err, "parejas": nP, "parejas_publicadas": len(out)}


# =============================================================================================== flujo por corte / producto
def ajustar(cfg: dict, aj_f1: dict, tr: pd.DataFrame, R: Rasgos, progreso=print, con_psi: bool = False) -> dict:
    """M (y, opcionalmente, ψ) sobre el residuo de F1 en los tramos `tr` (≤ t)."""
    f2 = cfg["f2"]["sinergia"]
    t0 = time.time()
    mu, _ = mu_f1(cfg, aj_f1, tr)
    r = tr["y"].to_numpy(float) - mu
    w = tr["poss"].to_numpy(float)
    sigma2 = float(aj_f1["res"]["sigma2"])
    G, b, rr = acumular(tr, R, r, w, progreso)
    fit = ajustar_M(G, b, rr, len(tr), sigma2, [float(x) for x in f2["lambda_rejilla"]])
    M = vec_a_matriz(fit["m"], R.p)
    out = {"M": M, "lambda": fit["lambda"], "log_marginal": fit["log_marginal"], "sigma2": sigma2, "p": R.p,
           "tramos": int(len(tr)), "rasgos": R.exportable(), "autovalores_M": np.linalg.eigvalsh(M).tolist()}
    if progreso:
        ev = np.sort(np.abs(np.linalg.eigvalsh(M)))[::-1]
        progreso(f"    M ajustada: λ* {fit['lambda']} · |autovalores| mayores {np.round(ev[:6], 4).tolist()} · {time.time() - t0:.0f} s", flush=True)
    if con_psi:
        r2 = r.copy()
        for idx, U in rasgos_tramos(tr, R):
            r2[idx] -= U @ fit["m"]
        ps = psi_parejas(tr, r2, w, sigma2, [float(x) for x in f2["kappa_rejilla"]], int(f2["pliegues"]), int(cfg["semilla"]),
                         float(f2["min_posesiones_pareja_psi"]), progreso)
        out["psi"] = ps
    return out


# =============================================================================================== producto
def exportar(cfg: dict, progreso=print) -> dict:
    """Ajuste con todas las temporadas sobre el residuo del F1 producto: M (rango del examen), ψ de las parejas observadas,
    y los rasgos z para predecir φ̂ de cualquier pareja (F4). Salidas en data/modelos/v4_0/sinergia/."""
    from bbfit.registro import experimento
    from .examen_f1 import perfiles_completo
    t0 = time.time()
    out = dir_salida(cfg)
    tr = RP.tramos(cfg, None, progreso)
    temps = sorted(tr["temporada"].unique())
    T = RP.tabla_prior(perfiles_completo(cfg, temps), cfg)
    # F1 producto (caché del ajuste net)
    tipo = cfg["f1"]["prior"].get("elegido") or json.loads((RP.dir_salida(cfg) / "examen" / "resumen_examen.json").read_text())["decisiones"]["prior"]["elegido"]
    pr = cfg["f1"].get("producto") or {}
    cfg_p = C.con(cfg, **{"f1.bayes_empirico.tau_rejilla": pr.get("tau_rejilla", cfg["f1"]["bayes_empirico"]["tau_rejilla"]),
                          "f1.prior.ridge_alpha_rejilla": pr.get("ridge_alpha_rejilla", cfg["f1"]["prior"]["ridge_alpha_rejilla"])}) if pr else cfg
    cache = C.RAIZ / "experimentos" / "v4_0" / f"producto_f1_net_{tipo}_{RP.huella_ajuste(cfg_p)}.pkl"
    if not cache.exists():
        raise FileNotFoundError(f"falta el ajuste producto de F1 ({cache.name}): ejecute `python -m bbequipo rapm-producto`")
    res = pickle.loads(cache.read_bytes())
    D = RP.construir_diseno(tr, "net")
    tb = RP.tabla_beta(res, D).merge(RP.ligas_jugador(tr), on="clave", how="left")
    aj = {"corte": None, "D": D, "res": res, "T": T, "tb": tb}
    R = Rasgos(T, cfg)
    ex = json.loads((out / "examen" / "resumen_examen_f2a.json").read_text(encoding="utf-8")) if (out / "examen" / "resumen_examen_f2a.json").exists() else {}
    rango = ex.get("decisiones", {}).get("rango", "4")
    r_ = None if rango in ("completa", None) else int(rango)
    with experimento(cfg["mlflow"], "F2A_producto", params={"rango": rango, "tramos": len(tr)}) as run:
        fit = ajustar(cfg, aj, tr, R, progreso=progreso, con_psi=bool(cfg["f2"]["sinergia"].get("psi", True)))
        Mr, proy = truncar(fit["M"], r_)
        np.save(out / "M_completa.npy", fit["M"]); np.save(out / "M_rango.npy", Mr)
        doc = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "rango": rango, "lambda": fit["lambda"],
               "log_marginal": fit["log_marginal"], "p": R.p, "tramos": int(len(tr)), "rasgos": R.exportable(),
               "P": proy["P"].tolist(), "w": proy["w"].tolist(), "autovalores_M": fit["autovalores_M"],
               "formula": "φ̂(i,j) = z_iᵀ M_r z_j, z = (x − media)/sd (NaN → 0); M_r = P diag(w) Pᵀ; sin perfil → z = 0 → φ̂ = 0",
               "sigma2_f1": fit["sigma2"]}
        if "psi" in fit:
            ps = fit["psi"]
            pd.DataFrame([{"i": k[0], "j": k[1], "psi": v[0], "poss": v[1]} for k, v in ps["psi"].items()]).round(4).to_csv(out / "psi.csv.gz", index=False)
            doc["psi"] = {"kappa": ps["kappa"], "error_cv": ps["error_cv"], "parejas": ps["parejas"], "publicadas": ps["parejas_publicadas"]}
        doc["tiempo_s"] = round(time.time() - t0)
        (out / "W_sinergia.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
        run.metricas({"lambda": fit["lambda"], "autovalor_max": float(np.max(np.abs(fit["autovalores_M"])))})
    if progreso:
        progreso(f"  F2-A producto: rango {rango} · λ {fit['lambda']} · {doc['tiempo_s']} s", flush=True)
    return doc
