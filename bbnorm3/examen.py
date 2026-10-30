"""Examen de la v3 frente a las líneas base, recalibración conforme y puerta de control.

Líneas base (mismos casos, ajustadas sólo con ≤ t; ficheros versionados de la v2):
  * «mismo percentil»  data/modelos/normalizacion_amortiguada/validacion_variantes/sin_mapeo_<t>.csv.gz
  * «F0»               A amortiguado (grafo + contracción + IPW, la variante elegida «sin_mapeo»): niveles del grafo
                       amortiguado actual; su intervalo se recalcula aparte con la covarianza completa (si existe
                       data/modelos/v3/validacion/f0_<t>.csv.gz) — sin él sólo se compara el punto.
  * «<m>_am»           A+B amortiguado, igual que el dataset normalizado: T⁻¹(T(AB) + T(A_am) − T(A)), con
                       T(AB) = media de T(A) y T(B) si B traduce al jugador y T(A) si no (B: data/modelos/algoritmo_B/
                       validacion_casos.csv, examen sin fuga de la v1). Cobertura: la del A amortiguado.

Recalibración conforme por cuantiles (sin mirar el examen): para el corte t se usan las predicciones del modelo
ajustado con ≤ t−1 sobre los cambios t−1 → t. Residuo estandarizado e = (y − centro)/sd; κ = cuantil 80 % de |e|
dividido por z₀,₉. Factor por métrica × ajuste por grupo origen → destino (a la EuroLeague, FEB, NBA/G League, resto
de Europa) si el grupo tiene ≥ 30 casos; si no, el global.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from bbmodel.metricas import CATALOGO, destransformar, transformar

from .config import RAIZ
from .prediccion import Z80

DIR_AM = RAIZ / "data" / "modelos" / "normalizacion_amortiguada" / "validacion_variantes"
FICH_B = RAIZ / "data" / "modelos" / "algoritmo_B" / "validacion_casos.csv"
CLAVE = ["metrica", "anio", "nombre", "liga_o", "liga_d", "real_r"]


def grupo(liga_o: pd.Series, liga_d: pd.Series) -> pd.Series:
    g = np.where(liga_d == "euroleague", "a_euroleague",
                 np.where(liga_o.str.startswith("feb") | liga_d.str.startswith("feb"), "feb",
                          np.where(liga_o.isin(["nba", "gleague"]) | liga_d.isin(["nba", "gleague"]), "nba_gleague",
                                   "europa")))
    return pd.Series(g, index=liga_o.index)


def lineas_base(anio: int, fich_am: Path | None = None, fich_b: Path | None = None) -> pd.DataFrame:
    am = pd.read_csv(fich_am or DIR_AM / f"sin_mapeo_{anio}.csv.gz")
    b = pd.read_csv(fich_b or FICH_B)
    b = b[b["anio"] == anio]
    am["real_r"] = am["real"].round(3)
    b["real_r"] = b["real"].round(3)
    b = b.drop_duplicates(["metrica", "anio", "liga_d", "real_r"], keep=False)   # sólo emparejamientos únicos
    am = am.merge(b[["metrica", "anio", "liga_d", "real_r", "algoritmo_B"]], on=["metrica", "anio", "liga_d", "real_r"],
                  how="left")
    out = []
    for col, g in am.groupby("metrica"):
        tr = CATALOGO[col].transf
        TA, Tam = transformar(g["algoritmo_A"], tr), transformar(g["amortiguado"], tr)
        TB = transformar(g["algoritmo_B"], tr)
        TAB = np.where(np.isfinite(TB), 0.5 * (TA + TB), TA)
        g = g.assign(am=destransformar(TAB + Tam - TA, tr), F0=g["amortiguado"], con_B=np.isfinite(TB))
        out.append(g)
    return pd.concat(out, ignore_index=True)


def unir(v3: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    v3 = v3.assign(real_r=v3["real"].round(3))
    base = base.drop_duplicates(CLAVE, keep=False)
    v3 = v3.drop_duplicates(CLAVE, keep=False)
    cols = CLAVE + [c for c in ["mismo_percentil", "algoritmo_A", "dentro_80", "am", "F0", "dentro_80_am", "con_B",
                                "centro_t_F0", "sd_t_F0", "dentro_80_F0"] if c in base]
    return v3.merge(base[cols], on=CLAVE, how="inner")


# ---------------------------------------------------------------------------------------------- calibración
def factores_calibracion(cal: pd.DataFrame, min_casos: int) -> dict:
    e = (cal["real_z"] - cal["v3_centro_z"]).abs() / cal["v3_sd_z"]
    cal = cal.assign(e=e, grupo=grupo(cal["liga_o"], cal["liga_d"]))
    k_glob = float(np.quantile(cal["e"], 0.8) / Z80)
    k_met = {m: float(np.quantile(g["e"], 0.8) / Z80) for m, g in cal.groupby("metrica")}
    k_grp = {}
    for gname, g in cal.groupby("grupo"):
        if g["persona_id"].nunique() >= min_casos:
            k_grp[gname] = float(np.quantile(g["e"], 0.8) / Z80) / k_glob
    return {"global": k_glob, "metrica": k_met, "grupo": k_grp, "casos": int(len(cal))}


def aplicar_calibracion(r: pd.DataFrame, f: dict) -> pd.DataFrame:
    g = grupo(r["liga_o"], r["liga_d"])
    k = r["metrica"].map(f["metrica"]).fillna(f["global"]) * g.map(f["grupo"]).fillna(1.0)
    half = k * Z80 * r["v3_sd_z"]
    lo_z, hi_z = r["v3_centro_z"] - half, r["v3_centro_z"] + half
    r = r.assign(kappa=k.to_numpy(), dentro_80_v3c=((r["real_z"] >= lo_z) & (r["real_z"] <= hi_z)).to_numpy())
    return r


def intervalos_calibrados(r: pd.DataFrame, esc) -> pd.DataFrame:
    """v3_lo_c / v3_hi_c en unidades reales (para informes)."""
    lo, hi = [], []
    for col, g in r.groupby("metrica", sort=False):
        tr = CATALOGO[col].transf
        c, s = esc.c[col], esc.s[col]
        half = g["kappa"] * Z80 * g["v3_sd_z"]
        lo.append(pd.Series(destransformar(c + s * (g["v3_centro_z"] - half), tr), index=g.index))
        hi.append(pd.Series(destransformar(c + s * (g["v3_centro_z"] + half), tr), index=g.index))
    return r.assign(v3_lo_c=pd.concat(lo), v3_hi_c=pd.concat(hi))


# ---------------------------------------------------------------------------------------------- resumen
METODOS = {"v3": "v3", "am": "am", "F0": "F0", "mismo_percentil": "mismo_percentil", "A": "algoritmo_A"}


def resumen_metricas(r: pd.DataFrame) -> pd.DataFrame:
    out = []
    for col, g in r.groupby("metrica"):
        fila = {"metrica": col, "nombre": CATALOGO[col].nombre, "casos": len(g)}
        for k, c in METODOS.items():
            fila[f"mae_{k}"] = float((g[c] - g["real"]).abs().mean())
        fila["mae_rel_v3_am"] = fila["mae_v3"] / fila["mae_am"]
        fila["cob80_v3_bruta"] = float(g["dentro_80_v3"].mean())
        fila["cob80_v3"] = float(g["dentro_80_v3c"].mean()) if "dentro_80_v3c" in g else np.nan
        fila["cob80_am"] = float(g["dentro_80_am"].mean())
        fila["cob80_A"] = float(g["dentro_80"].mean())
        out.append(fila)
    return pd.DataFrame(out)


def mae_rel_medio(r: pd.DataFrame, a: str = "v3", b: str = "am") -> float:
    m = r.assign(ea=(r[a] - r["real"]).abs(), eb=(r[b] - r["real"]).abs()).groupby("metrica")[["ea", "eb"]].mean()
    return float((m["ea"] / m["eb"]).mean() - 1.0)


def bootstrap_persona(r: pd.DataFrame, a: str, b: str, B: int, semilla: int) -> dict:
    """IC 95 % de (media sobre métricas de MAE_a/MAE_b) − 1, remuestreando personas (persona × corte)."""
    r = r.assign(ea=(r[a] - r["real"]).abs(), eb=(r[b] - r["real"]).abs(),
                 unidad=r["persona_id"].astype(str) + "|" + r["anio"].astype(str))
    tab = r.pivot_table(index="unidad", columns="metrica", values=["ea", "eb"], aggfunc="sum")
    cnt = r.pivot_table(index="unidad", columns="metrica", values="ea", aggfunc="count").fillna(0)
    EA, EB, C = tab["ea"].fillna(0).to_numpy(), tab["eb"].fillna(0).to_numpy(), cnt.to_numpy()
    rng = np.random.default_rng(semilla)
    n = len(EA)
    vals = np.empty(B)
    for i in range(B):
        w = np.bincount(rng.integers(0, n, n), minlength=n).astype(float)
        sa, sb, sc = w @ EA, w @ EB, w @ C
        ok = sc > 0
        vals[i] = np.mean((sa[ok] / sc[ok]) / (sb[ok] / sc[ok])) - 1.0
    est = mae_rel_medio(r, a, b)
    lo, hi = np.quantile(vals, [0.025, 0.975])
    return {"estimacion": est, "ic95": [float(lo), float(hi)], "unidades": int(n), "remuestreos": B}


def cobertura_grupos(r: pd.DataFrame, min_casos: int, col: str = "dentro_80_v3c") -> pd.DataFrame:
    out = []
    for (lo, ld), g in r.groupby(["liga_o", "liga_d"]):
        n = g["persona_id"].nunique()
        if n >= min_casos:
            out.append({"liga_o": lo, "liga_d": ld, "personas": n, "predicciones": len(g),
                        "cobertura80": float(g[col].mean()),
                        "mae_rel_v3_am": mae_rel_medio(g), "mae_rel_v3_percentil": mae_rel_medio(g, "v3", "mismo_percentil")})
    return pd.DataFrame(out)


def puerta(r: pd.DataFrame, cfg: dict) -> dict:
    v = cfg["validacion"]
    lo, hi = v["cobertura_objetivo"]
    bs = bootstrap_persona(r, "v3", "am", int(v["bootstrap"]), int(v["semilla_bootstrap"]))
    cg = cobertura_grupos(r, int(v["min_casos_grupo"]))
    cob_m = r.groupby("metrica")["dentro_80_v3c"].mean()
    el = r[r["liga_d"] == "euroleague"]
    bs_el = bootstrap_persona(el, "v3", "am", int(v["bootstrap"]), int(v["semilla_bootstrap"])) if len(el) else None
    c1 = bs["ic95"][1] < 0
    c2 = bool(((cg["cobertura80"] >= lo) & (cg["cobertura80"] <= hi)).all()) if len(cg) else False
    c3 = bs_el is not None and bs_el["estimacion"] <= 0
    return {"pasa": bool(c1 and c2 and c3),
            "criterio_1_mae": {"cumple": bool(c1), **bs},
            "criterio_2_cobertura": {"cumple": c2, "rango": [lo, hi], "grupos": len(cg),
                                     "grupos_fuera": cg[(cg["cobertura80"] < lo) | (cg["cobertura80"] > hi)]
                                     [["liga_o", "liga_d", "personas", "cobertura80"]].round(3).to_dict("records"),
                                     "cobertura_media": float(r["dentro_80_v3c"].mean()),
                                     "metricas_fuera": {k: round(float(x), 3) for k, x in cob_m.items() if not lo <= x <= hi}},
            "criterio_3_euroleague": {"cumple": bool(c3), **(bs_el or {})}}
