"""F7 · Resumen de la NUTS del paso 2 (puentes intra + traspasos entre temporadas, bloques reagrupados).

- diagnósticos por bloque;
- matriz de traducción 2025-26 (todas las parejas) y versión legible desde la ACB en puntos;
- ciclos (conjunta frente a pares independientes, sólo puentes intra);
- compatibilidad con el paso 1 (z de la diferencia de λ por liga y métrica, 2025-26);
- precisión: DT de λ del paso 2 ÷ DT del paso 1, por liga;
- correlación entre métricas de los efectos de liga dentro de cada bloque (de los draws de λ, entre ligas).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy import special

from bbnorm5 import config as C
from bbnorm5.ligas import modelo as LM
from bbnorm5.ligas import resumen as LR
from bbnorm5.medida import datos as DM

DIR = C.DIR_DATOS / "ligas"
DESTINOS = ["euroleague", "eurocup", "bcl", "lba", "bbl", "lnb", "nba", "gleague", "feb1", "feb2", "ncaa"]


def cargar(bloques: dict, prefijo: str) -> dict:
    """λ por métrica (draws × L × T) desde los ficheros lambda_<prefijo><bloque>.npz."""
    out = {}
    for bloque in bloques:
        z = np.load(DIR / f"lambda_{prefijo}{bloque}.npz", allow_pickle=True)
        ligas, temps = list(z["ligas"]), list(z["temporadas"])
        for k, m in enumerate(z["metricas"]):
            out[str(m)] = {"lam": z["lam"][..., k], "ligas": ligas, "temporadas": temps, "bloque": bloque}
    return out


def legible(tr: pd.DataFrame, temporada: str) -> pd.DataFrame:
    """Traducción desde la ACB en puntos de la tasa media de la ACB (binomial: logit; Poisson: log; normal: identidad)."""
    h = pd.read_csv(DM.DIR / "hiperparametros.csv")
    h = h[(h["datos"] == "temporada") & (h["liga"] == "acb") & (h["temporada"] == temporada)]
    h = h.sort_values("modelo").drop_duplicates("metrica", keep="last").set_index("metrica")
    filas = []
    for m in DM.METRICAS:
        if m not in h.index:
            continue
        fam, p = DM.METRICAS[m][0], float(h.loc[m, "tasa_media"])
        if fam == "binomial":
            f = lambda e: (special.expit(special.logit(p) + e) - p) * 100
        elif fam == "poisson":
            f = lambda e: (p * np.exp(e) - p) * 100
        else:
            f = lambda e: e * 100
        x = tr[(tr["metrica"] == m) & (tr["desde"] == "acb")].set_index("hacia")
        for l in DESTINOS:
            if l in x.index:
                r = x.loc[l]
                filas.append((m, l, f(r["media"]), f(r["q10"]), f(r["q90"])))
    t = pd.DataFrame(filas, columns=["metrica", "hacia", "media", "q10", "q90"])
    t["txt"] = t.apply(lambda r: f"{r.media:+.1f} ({r.q10:+.1f} a {r.q90:+.1f})".replace(".", ","), axis=1)
    return t


def frente_paso1(l1: dict, l2: dict, temporada: str) -> pd.DataFrame:
    """Por liga y métrica (2025-26, relativo a la ACB): medias, DT y z de la diferencia paso 2 − paso 1."""
    filas = []
    for m, a in l1.items():
        b = l2[m]
        ta, tb = a["temporadas"].index(temporada), b["temporadas"].index(temporada)
        for l in a["ligas"]:
            if l == LM.REF or l not in b["ligas"]:
                continue
            x, y = a["lam"][:, a["ligas"].index(l), ta], b["lam"][:, b["ligas"].index(l), tb]
            filas.append({"metrica": m, "liga": l, "media_p1": x.mean(), "sd_p1": x.std(), "media_p2": y.mean(),
                          "sd_p2": y.std(), "z": (y.mean() - x.mean()) / np.sqrt(x.var() + y.var())})
    r = pd.DataFrame(filas)
    r["ratio_sd"] = r["sd_p2"] / r["sd_p1"]
    return r


def correlacion_bloques(lam: dict, temporada: str) -> pd.DataFrame:
    """Correlación entre métricas de λ entre ligas (2025-26), media sobre draws, para cada par de métricas."""
    ms = list(lam)
    filas = []
    for i, m1 in enumerate(ms):
        for m2 in ms[i + 1:]:
            a, b = lam[m1], lam[m2]
            ligas = [l for l in a["ligas"] if l in b["ligas"] and l != LM.REF]
            x = a["lam"][:, [a["ligas"].index(l) for l in ligas], a["temporadas"].index(temporada)]
            y = b["lam"][:, [b["ligas"].index(l) for l in ligas], b["temporadas"].index(temporada)]
            # bloques con distinto número de draws (p. ej., un bloque relanzado con más muestras): submuestra regular
            n = min(len(x), len(y))
            x, y = x[np.linspace(0, len(x) - 1, n).astype(int)], y[np.linspace(0, len(y) - 1, n).astype(int)]
            xc, yc = x - x.mean(1, keepdims=True), y - y.mean(1, keepdims=True)
            r = (xc * yc).sum(1) / np.sqrt((xc ** 2).sum(1) * (yc ** 2).sum(1))
            filas.append({"m1": m1, "m2": m2, "mismo_bloque": a["bloque"] == b["bloque"], "r_media": r.mean(),
                          "r_q10": np.quantile(r, 0.1), "r_q90": np.quantile(r, 0.9)})
    return pd.DataFrame(filas)


def ejecutar(cfg6: dict) -> dict:
    temp = cfg6["temporadas"][-1]
    l2 = cargar(LM.BLOQUES_PASO2, "paso2_")
    l1 = cargar(LM.BLOQUES, "")
    tr = LR.traduccion(l2, temp)
    tr.to_csv(DIR / f"traduccion_paso2_{temp}.csv.gz", index=False)
    legible(tr, temp).to_csv(DIR / f"traduccion_acb_legible_paso2_{temp}.csv", index=False)
    pares = pd.read_parquet(DIR / "pares_intra.parquet")
    cy = LR.ciclos(l2, pares)
    cy.to_csv(DIR / "ciclos_paso2.csv", index=False)
    fp = frente_paso1(l1, l2, temp)
    fp.to_csv(DIR / "paso2_frente_paso1_nuts.csv", index=False)
    cb2, cb1 = correlacion_bloques(l2, temp), correlacion_bloques(l1, temp)
    cb = cb2.merge(cb1[["m1", "m2", "mismo_bloque", "r_media"]].rename(columns={"mismo_bloque": "mismo_bloque_p1",
                                                                             "r_media": "r_media_p1"}), on=["m1", "m2"])
    cb.to_csv(DIR / "correlacion_metricas_paso2.csv", index=False)
    diag = json.loads((DIR / "lambda_paso2_diagnosticos.json").read_text(encoding="utf-8"))
    return {"diagnosticos": diag, "ciclo_conjunta_max": float(cy["residuo_conjunta_max"].max()),
            "ciclo_pares_mediana_abs": float(cy["residuo_pares"].abs().median()),
            "z_abs_mediana": float(fp["z"].abs().median()), "z_abs_max": float(fp["z"].abs().max()),
            "ratio_sd_por_liga": fp.groupby("liga")["ratio_sd"].median().round(3).to_dict()}
