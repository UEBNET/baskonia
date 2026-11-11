"""F6.1 · Resumen de los efectos de liga: matriz de traducción, ciclos, grafo, prior de enfrentamientos y anchura frente
a la v3.2."""
from __future__ import annotations

import itertools
import json

import numpy as np
import pandas as pd

from bbnorm5 import config as C
from bbnorm5.ligas import modelo as LM
from bbnorm5.medida import datos as DM

DIR = C.DIR_DATOS / "ligas"


def cargar_lambda(con_fuerza: bool = False) -> dict:
    """λ por métrica: draws × L × T, combinando los bloques (posteriores independientes entre bloques)."""
    out = {}
    for bloque in LM.BLOQUES:
        f = DIR / f"lambda_{bloque}{'_fuerza' if con_fuerza and (DIR / f'lambda_{bloque}_fuerza.npz').exists() else ''}.npz"
        z = np.load(f, allow_pickle=True)
        ligas, temps = list(z["ligas"]), list(z["temporadas"])
        for k, m in enumerate(z["metricas"]):
            out[str(m)] = {"lam": z["lam"][..., k], "ligas": ligas, "temporadas": temps}
    return out


def traduccion(lam: dict, temporada: str) -> pd.DataFrame:
    filas = []
    for m, x in lam.items():
        t = x["temporadas"].index(temporada)
        L = x["lam"][:, :, t]
        for ia, la in enumerate(x["ligas"]):
            D = L - L[:, [ia]]                       # draws × destino: λ_b − λ_a
            q = np.quantile(D, [0.1, 0.9], axis=0)
            for ib, lb in enumerate(x["ligas"]):
                filas.append((temporada, m, la, lb, D[:, ib].mean(), q[0, ib], q[1, ib], D[:, ib].std()))
    return pd.DataFrame(filas, columns=["temporada", "metrica", "desde", "hacia", "media", "q10", "q90", "sd"])


def ciclos(lam: dict, pares: pd.DataFrame, min_puentes: int = 10) -> pd.DataFrame:
    """Residuo de ciclo r = T(a→b) + T(b→c) − T(a→c): conjunta (draws; cero por construcción) frente a estimaciones por
    pares independientes (media de las diferencias de los puentes de cada par, ponderada por precisión, todas las
    temporadas)."""
    filas = []
    for m, x in lam.items():
        p = pares[pares["metrica"] == m]
        w = 1 / p["var"]
        g = p.assign(w=w, wd=w * p["d"]).groupby(["liga_a", "liga_b"]).agg(wd=("wd", "sum"), w=("w", "sum"),
                                                                          n=("d", "size"))
        g = g[g["n"] >= min_puentes]
        T = {}
        for (a, b), r in g.iterrows():
            T[(a, b)] = r["wd"] / r["w"]
            T[(b, a)] = -T[(a, b)]
        ligas = sorted({l for k in T for l in k})
        t = len(x["temporadas"]) - 1
        il = {l: i for i, l in enumerate(x["ligas"])}
        for a, b, c in itertools.combinations(ligas, 3):
            if (a, b) in T and (b, c) in T and (a, c) in T:
                r_par = T[(a, b)] + T[(b, c)] - T[(a, c)]
                L = x["lam"][:, :, t]
                if all(l in il for l in (a, b, c)):
                    rj = (L[:, il[b]] - L[:, il[a]]) + (L[:, il[c]] - L[:, il[b]]) - (L[:, il[c]] - L[:, il[a]])
                    filas.append((m, a, b, c, r_par, float(np.abs(rj).max()), abs(T[(a, c)])))
    return pd.DataFrame(filas, columns=["metrica", "a", "b", "c", "residuo_pares", "residuo_conjunta_max", "T_ac_abs"])


def grafo(lam: dict, pares: pd.DataFrame, temporada: str) -> pd.DataFrame:
    """Por liga: puentes, aristas, la arista que más pesa y la anchura media del intervalo de λ (relativo a la ACB)."""
    pu = pares.drop_duplicates("puente")
    filas = []
    ligas = sorted(set(pu["liga_a"]) | set(pu["liga_b"]))
    for l in ligas:
        x = pu[(pu["liga_a"] == l) | (pu["liga_b"] == l)]
        otra = np.where(x["liga_a"] == l, x["liga_b"], x["liga_a"])
        vc = pd.Series(otra).value_counts()
        anchos = []
        for m, z in lam.items():
            if l in z["ligas"]:
                t = z["temporadas"].index(temporada)
                d = z["lam"][:, z["ligas"].index(l), t] / np.std(pares.loc[pares["metrica"] == m, "d"])
                anchos.append(np.quantile(d, 0.9) - np.quantile(d, 0.1))
        filas.append({"liga": l, "puentes": len(x), "personas": x["persona_v5"].nunique(), "aristas": len(vc),
                      "arista_principal": vc.index[0] if len(vc) else None,
                      "cuota_arista_principal": float(vc.iloc[0] / vc.sum()) if len(vc) else np.nan,
                      "ancho80_lambda_std": float(np.median(anchos)) if anchos else np.nan})
    return pd.DataFrame(filas).sort_values("ancho80_lambda_std")


def efecto_fuerza() -> pd.DataFrame:
    """λ de pts/100 con y sin el prior de enfrentamientos (2025-26)."""
    a, b = cargar_lambda(False)["pts_p100"], cargar_lambda(True)["pts_p100"]
    t = len(a["temporadas"]) - 1
    filas = []
    for i, l in enumerate(a["ligas"]):
        x, y = a["lam"][:, i, t], b["lam"][:, i, t]
        filas.append({"liga": l, "media_sin": x.mean(), "sd_sin": x.std(), "media_con": y.mean(), "sd_con": y.std()})
    r = pd.DataFrame(filas)
    r["reduccion_sd"] = 1 - r["sd_con"] / r["sd_sin"]
    return r


def frente_v32(lam: dict, temporada: str) -> pd.DataFrame:
    """Anchura de la traducción ACB → liga en puntos porcentuales: v5 (λ en logit × p(1−p) a la tasa media de la ACB)
    frente a la v3.2 (DT del par en la vara EuroLeague × DT EuroLeague de la métrica, métricas en escala identidad)."""
    from bbnorm3.destino import sd_par_matriz
    const = json.loads((C.RAIZ / "data" / "modelos" / "v3_2" / "destino" / "constantes.json").read_text(encoding="utf-8"))
    h = pd.read_csv(DM.DIR / "hiperparametros.csv")
    h = h[(h["datos"] == "temporada") & (h["liga"] == "acb") & (h["temporada"] == temporada)]
    eq = {"t2_pct": "fg2_pct", "t3_pct": "fg3_pct", "tpar": "fg3a_rate"}
    filas = []
    for m5, m3 in eq.items():
        cv = json.loads((C.RAIZ / "data" / "modelos" / "v3_2" / "destino" / "covarianza" / f"{m3}.json").read_text())
        Tm = sd_par_matriz(cv)
        ix = {n: i for i, n in enumerate(cv["nodos"])}
        tau = np.mean([v for k, v in const["metricas"][m3]["tau2"].items() if k.startswith("euroleague|")]) ** 0.5
        p = float(h[h["metrica"] == m5]["tasa_media"].iloc[0])
        z = lam[m5]
        t = z["temporadas"].index(temporada)
        ia = z["ligas"].index("acb")
        for ib, lb in enumerate(z["ligas"]):
            if lb == "acb":
                continue
            d = z["lam"][:, ib, t] - z["lam"][:, ia, t]
            v5 = d.std() * p * (1 - p) * 100
            a, b = f"acb:{temporada}", f"{lb}:{temporada}"
            v3 = Tm[ix[a], ix[b]] * tau if a in ix and b in ix else np.nan
            filas.append({"metrica": m5, "hacia": lb, "sd_v5_pp": v5, "sd_v32_pp": v3})
    return pd.DataFrame(filas)


def intra(cfg: dict) -> dict:
    pares = pd.read_parquet(DIR / "pares_intra.parquet")
    lam = cargar_lambda(False)
    temp = cfg["temporadas"][-1]
    tr = traduccion(lam, temp)
    tr.to_csv(DIR / f"traduccion_{temp}.csv.gz", index=False)
    cy = ciclos(lam, pares)
    cy.to_csv(DIR / "ciclos.csv", index=False)
    gr = grafo(lam, pares, temp)
    gr.to_csv(DIR / "grafo_diagnostico.csv", index=False)
    out = {"triangulos": len(cy), "ciclo_conjunta_max": float(cy["residuo_conjunta_max"].max()) if len(cy) else None,
           "ciclo_pares_mediana_abs": float(cy["residuo_pares"].abs().median()) if len(cy) else None}
    try:
        fz = efecto_fuerza()
        fz.to_csv(DIR / "efecto_prior_fuerza.csv", index=False)
        out["reduccion_sd_fuerza_mediana"] = float(fz["reduccion_sd"].median())
    except FileNotFoundError:
        pass
    v = frente_v32(lam, temp)
    v.to_csv(DIR / "anchura_frente_v32.csv", index=False)
    out["ratio_sd_v5_v32_mediana"] = float((v["sd_v5_pp"] / v["sd_v32_pp"]).median())
    return out
