"""F6.2 · Proyección en contexto: la proyección de la F4 más la traducción entre ligas y el contexto, con examen fuera de
tiempo y navaja por bloques (criterio 11 de la revisión 1.2).

Base (F4): η = μ(liga de destino, rol, temporada previa) + a (posición relativa del jugador) [+ edad, cambio de rol].
Para quien cambia de liga, la F4 conserva la posición relativa (sólo ensancha con σ_L).

Bloques que se añaden, sobre la escala del enlace:
1. `liga`: traducción absoluta. Para quien cambia de liga, η_λ = μ(origen) + a + (λ_destino − λ_origen), es decir,
   Δ = μ(origen) − μ(destino) + λ_destino − λ_origen sobre la base; con la varianza de λ. λ por GLS con puentes de
   temporadas anteriores al corte (sin fugas).
2. `volumen`: volumen–eficiencia. log((N_T + 1)/(N_última + 1)) por rol (exterior, alero, interior). Se condiciona en el
   volumen de la temporada objetivo, como la producción esperada «dado un volumen».
3. `companeros`: estilo de los compañeros. Cambio en la composición de estilos de los compañeros (6 estilos unificados,
   ponderados por minutos, F2) entre la última temporada y la objetivo; 5 diferencias (suman 0).
4. `tipo`: efecto de liga según el tipo de jugador. Δλ × (perfiles latentes estables de la F5: tiro, interior-exterior,
   creación) y Δλ × rol.
5. `estilo_liga`: estilo de la liga según el tipo de jugador. Cambio de rasgos de liga (3PAr, ritmo, AST/TCm, FTr,
   OREB%; destino − origen, estandarizados) × perfiles latentes.

Coeficientes por métrica con regresión bayesiana con contracción (prior N(0, τ²) por bloque; τ por máxima verosimilitud
marginal en el entrenamiento). Pesos 1/(varianza predictiva de la base + muestreo de la temporada objetivo).
Entrenamiento con los cortes anteriores: se prueba en 2024-25 (entrenado con 2023-24) y en 2025-26 (con 2023-24 y
2024-25).
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd
from scipy import optimize, special

from bbnorm5 import config as C
from bbnorm5.carrera import datos as CD
from bbnorm5.carrera import examen as EX
from bbnorm5.carrera import modelo as MC
from bbnorm5.ligas import gls
from bbnorm5.medida import datos as DM

DIR = C.DIR_DATOS / "ligas"
ESTILOS = ["spacing", "circulacion", "isolation", "old_school", "pistons", "pintura"]
RASGOS = ["3PAr", "ritmo", "AST/TCm", "FTr", "OREB%"]
PERFILES = ["z2", "z3", "z5"]          # tiro y anotación, interior-exterior, creación (F5, estables)


# ------------------------------------------------------------------ base: predicción F4 por corte
def base_corte(o: pd.DataFrame, h: pd.DataFrame, metrica: str, anio: int) -> pd.DataFrame:
    hist = o[o["anio"] < anio]
    M = MC.matrices(hist)
    tau0 = float(h[(h["metrica"] == metrica) & (h["temporada"].str[:4].astype(int) < anio)]["sigma"].median())
    mod = MC.ajustar(M, "completo", tau0)
    obj = EX.objetivo(o, hist, anio, h, metrica)
    pred = MC.predecir(M, mod, obj)
    # media del rol de la última temporada en la liga de origen (para la traducción absoluta)
    lp = EX._liga_previa(h, metrica, anio)[["liga", "rol", "mu_prev"]]
    pred = pred.merge(lp.rename(columns={"liga": "liga_ult", "rol": "rol_ult", "mu_prev": "mu_origen"}),
                      on=["liga_ult", "rol_ult"], how="left")
    ult = hist.sort_values("anio").drop_duplicates("persona_v5", keep="last")[["persona_v5", "N", "temporada"]]
    pred = pred.merge(ult.rename(columns={"N": "N_ult", "temporada": "temporada_ult"}), on="persona_v5", how="left")
    return pred.assign(metrica=metrica, anio_obj=anio, s2_u=float(np.exp(2 * mod["th"].get("log_s_u", -30))))


def observacion(x: pd.DataFrame, fam: str) -> tuple[np.ndarray, np.ndarray]:
    """η observado de la temporada objetivo (escala del enlace) y su varianza de muestreo (como la F4)."""
    K, N = x["K"].to_numpy(float), x["N"].to_numpy(float)
    d = x["disp_prev"].to_numpy(float)
    if fam == "binomial":
        p = (K + 0.5) / (N + 1)
        return special.logit(p), (1 + d * np.maximum(x["N2g"].to_numpy(float) / N - 1, 0)) / (N * p * (1 - p))
    if fam == "poisson":
        lam = (K + 0.5) / N
        return np.log(lam), (1 + d) / (N * lam)
    return K / N, d / N


# ------------------------------------------------------------------ rasgos
def rasgos(base: pd.DataFrame, lam_gls: dict, perfiles: pd.DataFrame, ctx: pd.DataFrame, liga: pd.DataFrame) -> pd.DataFrame:
    x = base.copy()
    m = x["metrica"].iloc[0]
    # 1. traducción absoluta para quien cambia de liga
    d = [gls.diferencia(lam_gls[m], a, b) for a, b in zip(x["liga_ult"], x["liga"])]
    dl = np.array([z[0] for z in d])
    vl = np.array([z[1] for z in d])
    ok = (x["cl"] > 0) & np.isfinite(dl) & x["mu_origen"].notna()
    x["delta_lambda"] = np.where(ok, dl, 0.0)
    x["var_lambda"] = np.where(ok, vl, 0.0)
    x["ajuste_liga"] = np.where(ok, x["mu_origen"] - x["mu_prev"] + dl, 0.0)
    # 2. volumen
    vol = np.log((x["N"] + 1) / (x["N_ult"].fillna(x["N"]) + 1))
    for r in ("E", "A", "I"):
        x[f"vol_{r}"] = np.where(x["rol"] == r, vol, 0.0)
    # 3. compañeros (destino − última temporada)
    c = ctx.groupby(["persona_v5", "liga", "temporada"])[[f"comp_{e}" for e in ESTILOS]].mean()
    tgt = c.reindex(pd.MultiIndex.from_arrays([x["persona_v5"], x["liga"], x["anio_obj"].map(lambda a: f"{a}-{str(a + 1)[2:]}")])).to_numpy()
    prev = c.reindex(pd.MultiIndex.from_arrays([x["persona_v5"], x["liga_ult"], x["temporada_ult"]])).to_numpy()
    dc = np.nan_to_num(tgt - prev)
    for k, e in enumerate(ESTILOS[:-1]):
        x[f"dcomp_{e}"] = dc[:, k]
    # 4. tipo: perfiles de la última temporada × Δλ
    z = perfiles.set_index(["persona_v5", "temporada"])[PERFILES]
    zz = z.reindex(pd.MultiIndex.from_arrays([x["persona_v5"], x["temporada_ult"]])).to_numpy()
    zz = np.nan_to_num(zz)
    for k, p in enumerate(PERFILES):
        x[f"dl_{p}"] = x["delta_lambda"] * zz[:, k]
        x[f"z_{p}"] = zz[:, k]
    for r in ("E", "I"):
        x[f"dl_rol_{r}"] = x["delta_lambda"] * (x["rol"] == r)
    # 5. estilo de liga × tipo
    lg = liga.set_index(["liga", "temporada"])[RASGOS]
    lg = (lg - lg.mean()) / lg.std()
    temp_obj = x["anio_obj"].map(lambda a: f"{a - 1}-{str(a)[2:]}")         # rasgos de la temporada previa (sin fugas)
    dest = lg.reindex(pd.MultiIndex.from_arrays([x["liga"], temp_obj])).to_numpy()
    orig = lg.reindex(pd.MultiIndex.from_arrays([x["liga_ult"], x["temporada_ult"]])).to_numpy()
    dr = np.where((x["cl"] > 0).to_numpy()[:, None], np.nan_to_num(dest - orig), 0.0)
    for k, rr in enumerate(RASGOS):
        for j, p in enumerate(PERFILES):
            x[f"est_{rr}_{p}"] = dr[:, k] * zz[:, j]
    return x


BLOQUES = {
    # peso de la traducción absoluta frente a conservar la posición relativa (F4): coeficiente sobre el ajuste de liga
    # (efecto total = (1 + β)·ajuste); β = −1 vuelve a la F4, β = 0 es la traducción λ completa
    "peso_liga": ["ajuste_liga"],
    "volumen": [f"vol_{r}" for r in ("E", "A", "I")],
    "companeros": [f"dcomp_{e}" for e in ESTILOS[:-1]],
    "tipo": [f"dl_{p}" for p in PERFILES] + [f"dl_rol_{r}" for r in ("E", "I")],
    "estilo_liga": [f"est_{r}_{p}" for r in RASGOS for p in PERFILES],
}


# ------------------------------------------------------------------ regresión bayesiana con contracción por bloque
def ajustar_beta(X: np.ndarray, r: np.ndarray, w: np.ndarray, grupos: np.ndarray) -> dict:
    """r ~ N(Xβ, 1/w), β_j ~ N(0, τ_g²). τ por bloque por máxima verosimilitud marginal."""
    G = int(grupos.max()) + 1

    def nlml(lt):
        tau2 = np.exp(2 * lt)[grupos]
        A = X.T @ (X * w[:, None]) + np.diag(1 / tau2)
        b = X.T @ (w * r)
        Lc = np.linalg.cholesky(A)
        al = np.linalg.solve(Lc, b)
        # −log p(r) salvo constantes: ½[log|A| + Σ log τ² − αᵀα + Σ w r²]
        return 0.5 * (2 * np.log(np.diag(Lc)).sum() + np.log(tau2).sum() - al @ al + (w * r * r).sum())
    res = optimize.minimize(nlml, np.full(G, np.log(0.1)), method="L-BFGS-B", bounds=[(np.log(1e-4), np.log(3.0))] * G)
    tau2 = np.exp(2 * res.x)[grupos]
    A = X.T @ (X * w[:, None]) + np.diag(1 / tau2)
    cov = np.linalg.inv(A)
    return {"beta": cov @ (X.T @ (w * r)), "cov": cov, "tau": np.exp(res.x)}


def aplicar(x: pd.DataFrame, cols: list[str], fit: dict | None, con_liga: bool) -> pd.DataFrame:
    y = x.copy()
    if con_liga:
        y["m_nivel"] = y["m_nivel"] + y["ajuste_liga"]
        y["v_nivel"] = y["v_nivel"] + y["var_lambda"]
        y["v_y_sin_muestreo"] = y["v_y_sin_muestreo"] + y["var_lambda"]
    if fit is not None and cols:
        X = y[cols].to_numpy(float)
        mu = X @ fit["beta"]
        v = np.einsum("ij,jk,ik->i", X, fit["cov"], X)
        y["m_nivel"] = y["m_nivel"] + mu
        y["v_nivel"] = y["v_nivel"] + v
        y["v_y_sin_muestreo"] = y["v_y_sin_muestreo"] + v
    return y


# ------------------------------------------------------------------ recalibración de la varianza en los cambios de liga
def factor_recalibracion(tr: pd.DataFrame, cols: list[str], fit: dict | None, con_liga: bool, eta, vo) -> float:
    """Factor f de la varianza no muestral en los cambios de liga, por máxima verosimilitud en el entrenamiento:
    r ~ N(0, f·v_pred + v_obs) en los cambios de liga de los cortes anteriores (el estimador por momentos encogía
    demasiado en sucesos raros: 1.ª versión descartada)."""
    trp = aplicar(tr, cols, fit, con_liga)
    rr = eta - (trp["mu_prev"] + trp["m_nivel"]).to_numpy()
    cm = (trp["cl"] > 0).to_numpy() & np.isfinite(rr)
    vp = trp["v_y_sin_muestreo"].to_numpy(float)
    vo_c = np.asarray(vo, float)[cm]
    nll = lambda lf: 0.5 * np.sum(np.log(np.exp(lf) * vp[cm] + vo_c) + rr[cm] ** 2 / (np.exp(lf) * vp[cm] + vo_c))
    return float(np.exp(optimize.minimize_scalar(nll, bounds=(np.log(0.3), np.log(2.0)), method="bounded").x))


def recalibrar(y: pd.DataFrame, f: float) -> pd.DataFrame:
    y = y.copy()
    k = (y["cl"] > 0).to_numpy()
    for col in ("v_nivel", "v_y_sin_muestreo"):
        y.loc[k, col] = y.loc[k, col] * f
    return y


# ------------------------------------------------------------------ examen con navaja
MODELOS = {
    "base_F4": (False, []),
    "liga": (True, []),
    "liga+volumen": (True, ["volumen"]),
    "liga+companeros": (True, ["companeros"]),
    "liga+tipo": (True, ["tipo"]),
    "liga+estilo_liga": (True, ["estilo_liga"]),
    "liga+peso": (True, ["peso_liga"]),
    "liga+todos": (True, ["volumen", "companeros", "tipo", "estilo_liga"]),
    "liga+peso+todos": (True, ["peso_liga", "volumen", "companeros", "tipo", "estilo_liga"]),
    "liga+peso+todos+recal": (True, ["peso_liga", "volumen", "companeros", "tipo", "estilo_liga"]),
    # publicado (criterio 11 de la revisión 1.2, F8): el estilo de liga no supera la navaja en los fichajes reales
    "publicado": (True, ["peso_liga", "volumen", "companeros", "tipo"]),
}
RECALIBRAR = {"liga+peso+todos+recal", "publicado"}
PUBLICADO = "publicado"


def preparar(cfg: dict, cortes: list[int] | None = None, salida: str = "contexto_base.parquet") -> pd.DataFrame:
    o = CD.cargar()
    h = CD._hiper_preferido(pd.read_csv(DM.DIR / "hiperparametros.csv"))
    perf = pd.read_parquet(C.DIR_DATOS / "latente" / "perfiles_latentes.parquet")
    ctx = pd.read_parquet(C.DIR_DATOS / "contexto" / "contexto_companeros.parquet")
    liga = pd.read_csv(C.DIR_DATOS / "contexto" / "estilo_liga.csv")
    pares = pd.read_parquet(DIR / "pares_intra.parquet")
    filas = []
    for anio in (cortes or cfg["contexto"]["cortes"]):
        pp = pares[pares["temporada"].str[:4].astype(int) < anio]
        lam = gls.todas(pp, list(DM.METRICAS))
        for met in DM.METRICAS:
            om = o[o["metrica"] == met]
            b = base_corte(om, h, met, anio)
            filas.append(rasgos(b, lam, perf, ctx, liga))
            print(f"  base {anio} {met}: {len(b)}", flush=True)
    x = pd.concat(filas, ignore_index=True)
    x.to_parquet(DIR / salida)
    return x


def examen(cfg: dict, x: pd.DataFrame | None = None, sufijo: str = "") -> pd.DataFrame:
    x = pd.read_parquet(DIR / "contexto_base.parquet") if x is None else x
    casos, coefs, escalas = [], [], []
    for test in cfg["contexto"]["cortes_prueba"]:
        for met in DM.METRICAS:
            fam = DM.METRICAS[met][0]
            xm = x[x["metrica"] == met]
            tr, te = xm[xm["anio_obj"] < test], xm[xm["anio_obj"] == test]
            eta, vo = observacion(tr, fam)
            for nom, (con_liga, bloques) in MODELOS.items():
                cols = [c for b in bloques for c in BLOQUES[b]]
                fit = None
                if cols:
                    trl = aplicar(tr, [], None, con_liga)
                    r = eta - (trl["mu_prev"] + trl["m_nivel"]).to_numpy()
                    w = 1 / (trl["v_y_sin_muestreo"].to_numpy(float) + np.asarray(vo, float))
                    ok = np.isfinite(r) & np.isfinite(w)
                    grupos = np.concatenate([[k] * len(BLOQUES[b]) for k, b in enumerate(bloques)])
                    fit = ajustar_beta(tr[cols].to_numpy(float)[ok], r[ok], w[ok], grupos)
                    coefs.append(pd.DataFrame({"prueba": test, "metrica": met, "modelo": nom, "variable": cols,
                                               "beta": fit["beta"], "sd": np.sqrt(np.diag(fit["cov"]))}))
                y = aplicar(te, cols, fit, con_liga)
                if con_liga and nom in RECALIBRAR:
                    f = factor_recalibracion(tr, cols, fit, con_liga, eta, vo)
                    escalas.append({"prueba": test, "metrica": met, "modelo": nom, "factor_var_cambio_liga": f})
                    y = recalibrar(y, f)
                rng = np.random.default_rng((cfg["semilla"] + zlib.crc32(f"{test}|{met}|{nom}".encode())) % 2 ** 32)
                casos.append(EX.evaluar(y, fam, nom, rng).assign(metrica=met, anio=test))
            print(f"  prueba {test} {met}", flush=True)
    c = pd.concat(casos, ignore_index=True)
    c.to_parquet(DIR / f"contexto_casos{sufijo}.parquet")
    pd.concat(coefs).to_csv(DIR / f"contexto_coeficientes{sufijo}.csv", index=False)
    pd.DataFrame(escalas).to_csv(DIR / f"contexto_escala_cambio_liga{sufijo}.csv", index=False)
    return c


def navaja(c: pd.DataFrame, semilla: int) -> pd.DataFrame:
    """Diferencia de CRPS relativo (modelo − referencia) con IC 95 % por bootstrap de personas: bloques frente a
    «liga»; «liga» frente a «base_F4». Todos los casos y sólo cambios de liga."""
    rng = np.random.default_rng(semilla)
    k = ["metrica", "anio", "persona_v5"]
    p = c.pivot_table(index=k, columns="modelo", values="crps")
    cl = c[c["modelo"] == "base_F4"].set_index(k)["cambio_liga"].reindex(p.index)
    p = p.div(p.groupby(level="metrica")["base_F4"].transform("mean"), axis=0)
    filas = []
    comparaciones = ([("liga", "base_F4"), ("liga+peso", "base_F4"), ("liga+peso+todos", "base_F4"),
                      ("liga+peso+todos", "liga+todos"), ("liga+peso+todos+recal", "base_F4"),
                      ("liga+peso+todos+recal", "liga+peso+todos")] + [(m, "liga") for m in MODELOS if m.startswith("liga+") and m not in RECALIBRAR])
    for sub, mask in (("todos", np.ones(len(p), bool)), ("cambio de liga", (cl == 1).to_numpy())):
        q = p[mask]
        per = q.index.get_level_values("persona_v5")
        up, inv = np.unique(per, return_inverse=True)
        for a, b in comparaciones:
            d = (q[a] - q[b]).to_numpy()
            s, n = np.bincount(inv, weights=d), np.bincount(inv)
            bs = [s[i].sum() / n[i].sum() for i in (rng.integers(0, len(up), len(up)) for _ in range(400))]
            lo, hi = np.quantile(bs, [0.025, 0.975])
            filas.append({"casos": sub, "modelo": a, "frente_a": b, "dif_crps_rel": d.mean(), "ic95_lo": lo, "ic95_hi": hi,
                          "n": len(d), "supera_navaja": bool(hi < 0)})
    return pd.DataFrame(filas)
