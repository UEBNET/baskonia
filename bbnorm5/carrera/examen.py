"""F4.2 · Examen fuera de tiempo de la capa de carrera.

Para cada corte T (temporada objetivo 2023-24, 2024-25 y 2025-26) y métrica:
1. se ajustan los modelos sólo con las temporadas anteriores a T (hiperparámetros y curva de edad);
2. para cada persona con historial y con ≥ 100 minutos en su liga principal de T, se predice su **producción de la
   temporada T** (la tasa, dadas las oportunidades que tuvo) desde su historial;
3. se evalúa la cobertura de los intervalos del 50, 80 y 95 %, el PIT y el CRPS, y la anchura del intervalo del
   **nivel** (sin el ruido de muestreo de la temporada T).

Sin fugas: la media de la liga-temporada-rol de destino es la de la temporada anterior de esa liga (la última
disponible), la sobredispersión también, y la deriva entre mitades de la variante `deriva` se estima sólo con
temporadas anteriores a T.
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd
from scipy import special

from bbnorm5.carrera import modelo as MOD
from bbnorm5.medida import datos as DM
from bbnorm5.medida import eb
from bbnorm5.medida import validacion as VM

S = 400
MIN_MINUTOS = 100.0


def _liga_previa(h: pd.DataFrame, metrica: str, anio: int) -> pd.DataFrame:
    """μ por rol, dispersión y σ de la última temporada anterior a `anio` de cada liga."""
    x = h[(h["metrica"] == metrica) & (h["temporada"].str[:4].astype(int) < anio)]
    x = x.sort_values("temporada").drop_duplicates("liga", keep="last")
    mu = x.melt(id_vars=["liga"], value_vars=[f"mu_{r}" for r in ("E", "A", "I", "X")], var_name="rol", value_name="mu_prev")
    mu["rol"] = mu["rol"].str[3:]
    return mu.dropna().merge(x[["liga", "disp", "sigma"]].rename(columns={"disp": "disp_prev", "sigma": "sigma_prev"}),
                             on="liga")


def objetivo(o: pd.DataFrame, hist: pd.DataFrame, anio: int, h: pd.DataFrame, metrica: str) -> pd.DataFrame:
    ult = hist.sort_values("anio").drop_duplicates("persona_v5", keep="last")[["persona_v5", "anio", "liga", "rol"]]
    x = o[(o["anio"] == anio) & (o["min_temp"] >= MIN_MINUTOS)].merge(ult, on="persona_v5", suffixes=("", "_ult"))
    x["gap"] = (x["anio"] - x["anio_ult"]).astype(float)
    x["cl"] = (x["liga"] != x["liga_ult"]).astype(float)
    x["cr"] = (x["rol"] != x["rol_ult"]).astype(float)
    lp = _liga_previa(h, metrica, anio)
    x = x.merge(lp, on=["liga", "rol"])
    # media del rol anterior en la liga de destino (temporada previa): para el desplazamiento por cambio de rol
    x = x.merge(lp[["liga", "rol", "mu_prev"]].rename(columns={"rol": "rol_ult", "mu_prev": "mu_prev_rol_ult"}),
                on=["liga", "rol_ult"], how="left")
    x["dmu"] = np.where(x["cr"] > 0, (x["mu_prev_rol_ult"] - x["mu_prev"]).fillna(0.0), 0.0)
    return x


def muestras_predictivas(pred: pd.DataFrame, fam: str, rng, N_muestreo=None) -> tuple:
    """Draws de la tasa observada de la temporada objetivo (S por caso) y de la tasa de nivel. Con `N_muestreo` el ruido
    de muestreo usa esa exposición en lugar de la observada (p. ej. la de la temporada anterior, conocida en t)."""
    n = len(pred)
    eta_nivel = pred["mu_prev"].to_numpy()[:, None] + pred["m_nivel"].to_numpy()[:, None] + \
        np.sqrt(pred["v_nivel"].to_numpy())[:, None] * rng.standard_normal((n, S))
    sd_u = np.sqrt(np.maximum(pred["v_y_sin_muestreo"] - pred["v_nivel"], 0)).to_numpy()[:, None]
    eta = eta_nivel + sd_u * rng.standard_normal((n, S))
    inv = {"binomial": special.expit, "poisson": np.exp}.get(fam, lambda z: z)
    tasa, tasa_nivel = inv(eta), inv(eta_nivel)
    N = pred["N"].to_numpy(float) if N_muestreo is None else np.asarray(N_muestreo, float)
    K = pred["K"].to_numpy(float)
    Nr = np.maximum(np.round(N), K if N_muestreo is None else 1) if fam == "binomial" else N
    disp = pred["disp_prev"].to_numpy(float)
    if fam == "normal":
        Ks = tasa * Nr[:, None] + np.sqrt(disp[:, None] * Nr[:, None]) * rng.standard_normal(tasa.shape)
    else:
        n2g = pred["N2g"].to_numpy(float)
        if N_muestreo is not None:      # Σ n_g² escala con el cuadrado de la exposición (mismo reparto entre partidos)
            n2g = n2g * (Nr / np.maximum(pred["N"].to_numpy(float), 1e-9)) ** 2
        Ks = eb.muestras_conteo(tasa, Nr, n2g, fam, disp, rng)
    return Ks / Nr[:, None], tasa_nivel


def evaluar(pred: pd.DataFrame, fam: str, nombre: str, rng) -> pd.DataFrame:
    n = len(pred)
    eta_nivel = pred["mu_prev"].to_numpy()[:, None] + pred["m_nivel"].to_numpy()[:, None] + \
        np.sqrt(pred["v_nivel"].to_numpy())[:, None] * rng.standard_normal((n, S))
    sd_u = np.sqrt(np.maximum(pred["v_y_sin_muestreo"] - pred["v_nivel"], 0)).to_numpy()[:, None]
    eta = eta_nivel + sd_u * rng.standard_normal((n, S))
    inv = {"binomial": special.expit, "poisson": np.exp}.get(fam, lambda z: z)
    tasa, tasa_nivel = inv(eta), inv(eta_nivel)
    N = pred["N"].to_numpy(float)
    K = pred["K"].to_numpy(float)
    Nr = np.maximum(np.round(N), K) if fam == "binomial" else N
    disp = pred["disp_prev"].to_numpy(float)
    if fam == "normal":
        Ks = tasa * Nr[:, None] + np.sqrt(pred["disp_prev"].to_numpy(float)[:, None] * Nr[:, None]) * \
            rng.standard_normal(tasa.shape)
    else:
        Ks = eb.muestras_conteo(tasa, Nr, pred["N2g"].to_numpy(float), fam, disp, rng)
    r = eb.evaluar(Ks / Nr[:, None], K / Nr, fam != "normal", rng)
    q = np.quantile(tasa_nivel, [0.1, 0.9], axis=1)
    qp = np.quantile(Ks / Nr[:, None], [0.1, 0.9], axis=1)
    return pd.DataFrame({"persona_v5": pred["persona_v5"].to_numpy(), "liga": pred["liga"].to_numpy(),
                         "rol": pred["rol"].to_numpy(), "edad": pred["edad"].to_numpy(), "N": N,
                         "obs": K / Nr, "pred_media": (Ks / Nr[:, None]).mean(axis=1),
                         "temporadas_hist": pred["temporadas_hist"].to_numpy(), "cambio_liga": pred["cl"].to_numpy(),
                         "cambio_rol": pred["cr"].to_numpy(), "gap": pred["gap"].to_numpy(),
                         "pit": r["pit"].to_numpy(), "crps": r["crps"].to_numpy(),
                         "ancho_nivel80": q[1] - q[0], "ancho_pred80": qp[1] - qp[0], "modelo": nombre})


def corte(o: pd.DataFrame, h: pd.DataFrame, casos_f3: pd.DataFrame, hiper_f3: pd.DataFrame, metrica: str, anio: int,
          semilla: int, variantes: list[str]) -> tuple[pd.DataFrame, list[dict]]:
    fam = DM.METRICAS[metrica][0]
    rng = np.random.default_rng((semilla + zlib.crc32(f"{metrica}|{anio}".encode())) % 2 ** 32)
    hist = o[o["anio"] < anio]
    M = MOD.matrices(hist)
    obj = objetivo(o, hist, anio, h, metrica)
    tau0 = float(h[(h["metrica"] == metrica) & (h["temporada"].str[:4].astype(int) < anio)]["sigma"].median())
    # deriva entre mitades con temporadas anteriores al corte (sin fuga)
    c = casos_f3[(casos_f3["metrica"] == metrica) & (casos_f3["temporada"].str[:4].astype(int) < anio)]
    der = VM.deriva_momentos(c, hiper_f3)
    tau2_d = float(der[der["liga"] == "todas"]["tau2_d"].iloc[0])
    filas, hip, ajustados = [], [], {}
    for v in variantes:
        if v == "solo_ultima":
            mod, sol = MOD.fijo(v, 0.0, tau0), True
        elif v == "solo_ultima_deriva":
            mod, sol = MOD.fijo(v, 2 * tau2_d, tau0), True
        elif v == "deriva":
            mod, sol = MOD.fijo(v, 2 * tau2_d, tau0), False
        elif v.endswith("_solo_ultima"):    # mismo modelo ajustado, pero prediciendo sólo desde la última temporada
            mod, sol = ajustados[v[: -len("_solo_ultima")]], True
        else:
            mod, sol = MOD.ajustar(M, v, tau0), False
            ajustados[v] = mod
        pred = MOD.predecir(M, mod, obj, solo_ultima=sol)
        filas.append(evaluar(pred, fam, v, rng).assign(metrica=metrica, anio=anio))
        hip.append({"metrica": metrica, "anio_objetivo": anio, "variante": v, "tau2_d": tau2_d, "tau0_f3": tau0,
                    **{k: mod["th"].get(k, np.nan) for k in MOD.PARAMS}, "logL": mod.get("logL", np.nan),
                    "n_par": mod.get("n_par", 0), "convergio": mod.get("convergio", True),
                    **{f"beta_{i}": b for i, b in enumerate(mod["beta"])}})
    return pd.concat(filas, ignore_index=True), hip


def resumen(c: pd.DataFrame, por: list[str]) -> pd.DataFrame:
    c = c.copy()
    for a in (50, 80, 95):
        c[f"cob{a}"] = (np.abs(c["pit"] - 0.5) <= a / 200).astype(float)
    return c.groupby(por).agg(casos=("pit", "size"), cob50=("cob50", "mean"), cob80=("cob80", "mean"),
                              cob95=("cob95", "mean"), crps=("crps", "mean"), ancho_nivel80=("ancho_nivel80", "median"),
                              ancho_pred80=("ancho_pred80", "median")).reset_index()
