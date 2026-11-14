"""F9 · Recalibración del predictivo por métrica y grupo de ligas (decisión 4 de la puerta de la F8).

Como la v3.2 (`bbnorm3/examen.py`): con los casos de la temporada objetivo anterior (T − 1, sin fugas) se mide
cuánto hay que ensanchar o estrechar el intervalo para que cubra el 80 %:

    e = |y − mediana| / semiancho80,   k_métrica = cuantil 80 % de e en la métrica,
    k = k_métrica × k_grupo / k_global,

con k_grupo el mismo cuantil en el grupo (todas las métricas juntas) si tiene ≥ `min_casos` personas. Grupos: los de
la v3.2 para los cambios de liga (hacia la EuroLeague, FEB, NBA/G League, resto de Europa) más «misma liga», porque
la v5 también predice a quien no cambia. Todos los cuantiles se reescalan alrededor de la mediana:
q' = mediana + k (q − mediana).

**Criterio de adopción** (fijado antes de ver resultados): mejora el WIS del examen de fichajes (criterio 9) con IC 95 %
por jugadores entero por debajo de 0, y no empeora el protocolo de la F1 (IC que no quede entero por encima de 0).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from bbnorm5 import config as C
from bbnorm5.validacion import fichajes as VF

DIR = VF.DIR
MODELO = "ex_ante_sin_estilo_liga"
RECAL = f"{MODELO}_recal"


def grupo(liga_o: pd.Series, liga_d: pd.Series) -> np.ndarray:
    lo, ld = liga_o.astype(str), liga_d.astype(str)
    return np.where(lo == ld, "misma_liga",
                    np.where(ld == "euroleague", "a_euroleague",
                             np.where(lo.str.startswith("feb") | ld.str.startswith("feb"), "feb",
                                      np.where(lo.isin(["nba", "gleague"]) | ld.isin(["nba", "gleague"]), "nba_gleague",
                                               "europa"))))


def factores(cal: pd.DataFrame, min_casos: int = 30) -> dict:
    semi = np.maximum((cal["q90"] - cal["q10"]).to_numpy(float) / 2, 1e-12)
    e = np.abs(cal["obs"].to_numpy(float) - cal["q50"].to_numpy(float)) / semi
    c = cal.assign(e=e, grupo=grupo(cal["liga_ult"], cal["liga"]))
    c = c[np.isfinite(c["e"])]
    k_glob = float(np.quantile(c["e"], 0.8))
    k_met = {m: float(np.quantile(g["e"], 0.8)) for m, g in c.groupby("metrica")}
    k_grp = {g_: float(np.quantile(g["e"], 0.8)) / k_glob for g_, g in c.groupby("grupo")
             if g["persona_v5"].nunique() >= min_casos}
    return {"global": k_glob, "metrica": k_met, "grupo": k_grp, "casos": int(len(c))}


def aplicar(p: pd.DataFrame, f: dict) -> pd.DataFrame:
    p = p.copy()
    k = p["metrica"].map(f["metrica"]).fillna(f["global"]).to_numpy(float) * \
        pd.Series(grupo(p["liga_ult"], p["liga"])).map(f["grupo"]).fillna(1.0).to_numpy(float)
    q50 = p["q50"].to_numpy(float)
    for c in [VF._q(q) for q in VF.CUANTILES]:
        p[c] = q50 + k * (p[c].to_numpy(float) - q50)
    p["factor_recal"] = k
    p["crps"] = np.nan
    p["pit"] = np.nan
    return p


def recalibradas(cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Predicciones del modelo publicado recalibradas para cada año de prueba con el año anterior."""
    p = pd.read_parquet(DIR / "predicciones_v5.parquet")
    p22 = pd.read_parquet(DIR / "predicciones_v5_2022.parquet")
    todas = pd.concat([p22[p22["modelo"] == MODELO], p[p["modelo"] == MODELO]], ignore_index=True)
    filas, fac = [], []
    for T in cfg["examen"]["cortes_prueba"]:
        cal = todas[todas["anio"] == T - 1]
        f = factores(cal, int(cfg.get("recalibracion", {}).get("min_casos", 30)))
        filas.append(aplicar(todas[todas["anio"] == T], f).assign(modelo=RECAL))
        fac.append(pd.DataFrame([{"anio": T, "tipo": "global", "clave": "", "k": f["global"]}]
                                + [{"anio": T, "tipo": "metrica", "clave": m, "k": v} for m, v in f["metrica"].items()]
                                + [{"anio": T, "tipo": "grupo", "clave": g, "k": v} for g, v in f["grupo"].items()]))
    return pd.concat(filas, ignore_index=True), pd.concat(fac, ignore_index=True)


def evaluar(cfg: dict) -> dict:
    from bbnorm5.validacion import protocolo as VP
    r, fac = recalibradas(cfg)
    fac.to_csv(DIR / "recalibracion_factores.csv", index=False)
    p = pd.concat([pd.read_parquet(DIR / "predicciones_v5.parquet"), r], ignore_index=True)
    # 1. examen de fichajes: mismos casos, recalibrada frente a sin recalibrar (y ambas frente a la v3.3)
    VF.comparar(cfg, p=p, modelos_extra=(RECAL,), sufijo="_recal")
    d = pd.read_parquet(DIR / "examen_fichajes_casos_recal.parquet")
    rng = np.random.default_rng(cfg["semilla"])
    B = int(cfg["examen"].get("bootstrap", 1000))

    def wis(x, m):
        return VF.wis(x["y"], x[f"{m}__q50"], {a: x[f"{m}__{VF._q(l)}"] for a, (l, h) in VF.NIVELES.items()},
                      {a: x[f"{m}__{VF._q(h)}"] for a, (l, h) in VF.NIVELES.items()})
    filas = []
    for m, g in list(d.groupby("metrica")) + [("todas", d)]:
        a, b = wis(g, RECAL), wis(g, MODELO)
        if m == "todas":
            w = g["metrica"].map(pd.Series(b, index=g.index).groupby(g["metrica"]).mean()).to_numpy()   # cada métrica pesa igual
            a, b = a / w, b / w
        r_, lo, hi = VF._boot_ratio(g["persona_v5"].to_numpy(), a, b, B, rng)
        y = g["y"].to_numpy(float)
        filas.append({"examen": "fichajes", "grupo": m, "casos": len(g), "recal_frente_sin": r_, "ic_lo": lo, "ic_hi": hi,
                      "cob80_sin": float(((y >= g[f"{MODELO}__q10"]) & (y <= g[f"{MODELO}__q90"])).mean()),
                      "cob80_recal": float(((y >= g[f"{RECAL}__q10"]) & (y <= g[f"{RECAL}__q90"])).mean())})
    # 2. protocolo de la F1 con la recalibrada (misma tabla que la publicada)
    cfg1 = C.cargar("configs/v5/f1.yaml")
    VP.comparar(cfg, cfg1, p=p, modelo=RECAL, sufijo="_recal")
    c1 = pd.read_parquet(DIR / "protocolo_f1_casos_publicada.parquet")
    c2 = pd.read_parquet(DIR / "protocolo_f1_casos_recal.parquet")
    k = ["persona_v5", "metrica", "anio", "liga_o", "liga_d"]
    c = c1[k + ["wis_v5", "wis_v3.2", "real", "v5__lo80", "v5__hi80"]].merge(
        c2[k + ["wis_v5", "v5__lo80", "v5__hi80"]], on=k, suffixes=("_sin", "_recal"))
    c = c.drop_duplicates(k)
    for m, g in list(c.groupby("metrica")) + [("todas", c)]:
        esc = g.groupby("metrica")["wis_v3.2"].transform("mean").to_numpy()
        r_, lo, hi = VF._boot_ratio(g["persona_v5"].to_numpy(), g["wis_v5_recal"].to_numpy() / esc,
                                    g["wis_v5_sin"].to_numpy() / esc, B, rng)
        y = g["real"].to_numpy(float)
        filas.append({"examen": "protocolo_f1", "grupo": m, "casos": len(g), "recal_frente_sin": r_, "ic_lo": lo,
                      "ic_hi": hi,
                      "cob80_sin": float(((y >= g["v5__lo80_sin"]) & (y <= g["v5__hi80_sin"])).mean()),
                      "cob80_recal": float(((y >= g["v5__lo80_recal"]) & (y <= g["v5__hi80_recal"])).mean())})
    t = pd.DataFrame(filas)
    t.to_csv(DIR / "recalibracion_examen.csv", index=False)
    fich = t[(t["examen"] == "fichajes") & (t["grupo"] == "todas")].iloc[0]
    prot = t[(t["examen"] == "protocolo_f1") & (t["grupo"] == "todas")].iloc[0]
    adopta = bool(fich["ic_hi"] < 0 and not prot["ic_lo"] > 0)
    out = {"fichajes": fich.to_dict(), "protocolo_f1": prot.to_dict(), "adopta": adopta}
    C.escribir_json(out, DIR / "recalibracion.json")
    return out
