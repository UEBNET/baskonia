"""F10 · Landing: efecto de la primera temporada en una liga nueva (δ), por métrica y grupo de origen-destino.

Idea (encargo §14.4). La proyección de la v5 para la temporada t+1 de quien cambia de liga es

    η̂ = μ_rol(destino) + nivel de carrera + Δλ(origen → destino)

Si existe una adaptación, el observado de la primera temporada queda sistemáticamente por debajo (o por encima) de η̂:

    η_obs − η̂ = δ_grupo + ruido.

**Identificación.** Δλ tiene que venir sólo de los puentes de la misma temporada (paso 1 de la F6): el paso 2 se estima
con los propios traspasos y absorbería δ (sería circular). Se compara con los jugadores que no cambian de liga en la
misma liga de destino y temporada, para quitar el sesgo medio del modelo en cada liga-temporada.

**Pasajero o permanente.** Si δ es adaptación, la segunda temporada en la liga nueva vuelve a la línea (o la supera,
porque el nivel de carrera ya incorpora parte de la primera temporada baja). Si δ es un cambio de papel o un error de
traducción, persiste.

Unidades: DT del residuo (η_obs − η̂ dividido por su DT predictiva sin contexto) y la escala de la métrica en el punto
medio de los casos.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from bbnorm5 import config as C
from bbnorm5.ligas import contexto as LC
from bbnorm5.medida import datos as DM
from bbnorm5.validacion.recalibracion import grupo

ENTRADA = C.DIR_DATOS / "ligas" / "seleccion_base.parquet"
# escala publicada (como la v3.2): porcentajes y tasas por 100; faltas por 40 minutos
UNIDAD = {"pf_p40": 40.0}


def residuos(cfg: dict, x: pd.DataFrame | None = None) -> pd.DataFrame:
    """Residuo de cada transición con la traducción del paso 1, ajustado por el de quienes no cambian de liga en la
    misma liga de destino, temporada y métrica."""
    x = pd.read_parquet(ENTRADA) if x is None else x
    L = cfg["landing"]
    partes = []
    for m, g in x.groupby("metrica", sort=True):
        fam = DM.METRICAS[m][0]
        eta, vo = LC.observacion(g, fam)
        pred = (g["mu_prev"] + g["m_nivel"] + g["ajuste_liga"]).to_numpy(float)
        v = np.asarray(vo, float) + (g["v_y_sin_muestreo"] + g["var_lambda"]).to_numpy(float)
        # derivada de la escala publicada respecto de η en la predicción (δ en DT → δ en la escala de la métrica)
        if fam == "binomial":
            p = 1 / (1 + np.exp(-pred))
            deriv = p * (1 - p)
        elif fam == "poisson":
            deriv = np.exp(pred)
        else:
            deriv = np.ones(len(g))
        deriv = deriv * UNIDAD.get(m, 100.0)
        partes.append(g[["persona_v5", "anio_obj", "anio_ult", "liga", "liga_ult", "cl", "min_temp", "var_lambda"]]
                      .assign(metrica=m, e=eta - pred, v=v, deriv=deriv))
    d = pd.concat(partes, ignore_index=True)
    d = d[np.isfinite(d["e"]) & np.isfinite(d["v"]) & (d["v"] > 0) & (d["min_temp"] >= L["min_minutos"])].copy()
    d["r"] = d["e"] / np.sqrt(d["v"])
    d["grupo"] = grupo(d["liga_ult"], d["liga"])
    # ¿la temporada de origen fue la primera en su liga? (el caso anterior de la misma persona cambió de liga)
    prev = (d[["persona_v5", "metrica", "anio_obj", "cl", "liga_ult", "liga"]]
            .rename(columns={"anio_obj": "anio_ult", "cl": "cl_prev", "liga_ult": "liga_prev_o", "liga": "liga_prev_d"}))
    d = d.merge(prev, on=["persona_v5", "metrica", "anio_ult"], how="left")
    d["fase"] = np.where(d["cl"] > 0, "primera", np.where(d["cl_prev"] > 0, "segunda", "estable"))
    d["grupo_prev"] = np.where(d["fase"] == "segunda", grupo(d["liga_prev_o"].fillna(""), d["liga_prev_d"].fillna("")), "")
    # referencia: media de quienes no cambian (ni cambiaron el año anterior) en la misma liga, temporada y métrica
    ref = (d[d["fase"] == "estable"].groupby(["metrica", "liga", "anio_obj"])["r"].mean().rename("r_ref"))
    d = d.join(ref, on=["metrica", "liga", "anio_obj"])
    d["r_adj"] = d["r"] - d["r_ref"]
    return d[np.isfinite(d["r_adj"])]


def _boot_media(personas: np.ndarray, y: np.ndarray, B: int, rng) -> tuple[float, float]:
    """Media de y y su DT por bootstrap de personas (cada persona pesa por sus filas)."""
    u, inv = np.unique(personas, return_inverse=True)
    s, n = np.bincount(inv, y), np.bincount(inv).astype(float)
    w = rng.multinomial(len(u), np.full(len(u), 1 / len(u)), size=B).astype(float)
    medias = (w @ s) / (w @ n)
    return float(s.sum() / n.sum()), float(np.std(medias, ddof=1))


def _eb(d: np.ndarray, se: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Contracción hacia la media de los grupos (DerSimonian-Laird): devuelve δ contraída, media y τ."""
    w = 1 / se ** 2
    mu = float(np.sum(w * d) / np.sum(w))
    q = float(np.sum(w * (d - mu) ** 2))
    tau2 = max(0.0, (q - (len(d) - 1)) / (np.sum(w) - np.sum(w ** 2) / np.sum(w))) if len(d) > 1 else 0.0
    b = tau2 / (tau2 + se ** 2) if tau2 > 0 else np.zeros_like(se)
    return mu + b * (d - mu), mu, float(np.sqrt(tau2))


def estimar(cfg: dict, d: pd.DataFrame) -> pd.DataFrame:
    """δ (primera temporada) y su persistencia (segunda temporada) por métrica y grupo, con IC por bootstrap de
    personas más la incertidumbre de la traducción del paso 1 (común a los traspasos del mismo par de ligas)."""
    L, B = cfg["landing"], cfg["bootstrap"]
    rng = np.random.default_rng(cfg["semilla"])
    filas = []
    for (m, fase), gm in d[d["fase"] != "estable"].groupby(["metrica", "fase"]):
        col = "grupo" if fase == "primera" else "grupo_prev"
        for gr, g in list(gm.groupby(col)) + [("todos", gm)]:
            if gr in ("misma_liga", ""):
                continue
            delta, se_b = _boot_media(g["persona_v5"].to_numpy(), g["r_adj"].to_numpy(float), B, rng)
            # traducción: el error de Δλ es común a todas las filas del mismo par → no se promedia
            se_l = 0.0
            if fase == "primera":
                par = g.groupby(["liga_ult", "liga"]).agg(n=("r", "size"), vl=("var_lambda", "mean"), v=("v", "mean"))
                se_l = float(np.sqrt(np.sum((par["n"] / par["n"].sum()) ** 2 * par["vl"] / par["v"])))
            se = float(np.hypot(se_b, se_l))
            filas.append({"metrica": m, "fase": fase, "grupo": gr, "personas": g["persona_v5"].nunique(),
                          "filas": len(g), "delta": delta, "se_bootstrap": se_b, "se_traduccion": se_l, "se": se,
                          "ic_lo": delta - 1.96 * se, "ic_hi": delta + 1.96 * se,
                          "delta_escala": delta * float(np.median(np.sqrt(g["v"]) * g["deriv"])),
                          "familia": DM.METRICAS[m][0]})
    t = pd.DataFrame(filas)
    # contracción entre grupos dentro de cada métrica y fase (sin el agregado «todos»)
    t["delta_eb"], t["media_grupos"], t["tau"] = np.nan, np.nan, np.nan
    for (m, fase), idx in t[t["grupo"] != "todos"].groupby(["metrica", "fase"]).groups.items():
        e, mu, tau = _eb(t.loc[idx, "delta"].to_numpy(float), t.loc[idx, "se"].to_numpy(float))
        t.loc[idx, "delta_eb"], t.loc[idx, "media_grupos"], t.loc[idx, "tau"] = e, mu, tau
    ic = (t["ic_hi"] - t["ic_lo"]) / 2
    t["identificable"] = (t["personas"] >= L["identificable"]["min_personas"]) & (ic <= L["identificable"]["semiancho_ic95"])
    t["relevante"] = (t["delta"].abs() >= L["relevante"]) & ((t["ic_lo"] > 0) | (t["ic_hi"] < 0))
    return t


def persistencia(t: pd.DataFrame) -> pd.DataFrame:
    """Primera frente a segunda temporada (mismo grupo del cambio): ¿vuelve hacia 0?"""
    a = t[t["fase"] == "primera"].set_index(["metrica", "grupo"])
    b = t[t["fase"] == "segunda"].set_index(["metrica", "grupo"])
    j = a[["delta", "se", "relevante"]].join(b[["delta", "se", "personas"]], rsuffix="_2", how="inner")
    j["recupera"] = np.sign(j["delta"]) * j["delta_2"]          # < 0: la segunda va en sentido contrario (vuelve)
    j["persiste"] = j["relevante"] & (np.sign(j["delta_2"]) == np.sign(j["delta"])) & \
        (np.abs(j["delta_2"]) > 1.96 * j["se_2"])
    j["pasajero"] = j["relevante"] & (np.abs(j["delta_2"] - j["delta"]) > 1.96 * np.hypot(j["se"], j["se_2"])) & \
        ~j["persiste"]
    return j.reset_index()


def ejecutar(cfg: dict) -> dict:
    out_dir = C.dir_fase(cfg)
    d = residuos(cfg)
    t = estimar(cfg, d)
    p = persistencia(t)
    t.to_csv(out_dir / "landing_delta.csv", index=False)
    p.to_csv(out_dir / "landing_persistencia.csv", index=False)
    pr = t[(t["fase"] == "primera") & (t["grupo"] != "todos")]
    res = {"transiciones": int(len(d)), "primera": int((d["fase"] == "primera").sum()),
           "segunda": int((d["fase"] == "segunda").sum()),
           "celdas": int(len(pr)), "identificables": int(pr["identificable"].sum()),
           "relevantes": int(pr["relevante"].sum()),
           "persisten": int(p["persiste"].sum()), "pasajeros": int(p["pasajero"].sum()),
           "media_abs_delta": float(pr["delta"].abs().mean()),
           "semiancho_ic_mediano": float(((pr["ic_hi"] - pr["ic_lo"]) / 2).median())}
    C.escribir_json({**C.metadatos(cfg, [ENTRADA]), **res}, out_dir / "meta_landing.json")
    return res
