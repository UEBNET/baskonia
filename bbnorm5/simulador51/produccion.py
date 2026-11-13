"""v5.1 F2 · Producción por liga de destino combinada v5 / v3.3 (las 9 métricas del simulador).

Para cada fichaje real del examen V32_corte (reproducido en la F0, motor v3.3) y cada métrica de producción:
- **v3.3:** la producción aplicada publicada (A2 + A4), reconstruida con `fichajes.banco_v33` sobre el examen
  reproducido;
- **v5:** la proyección publicada (ex ante, recalibrada) en la liga y temporada de destino. TS% sale de sus componentes
  (draws conjuntos); OREB/DREB/BLK por 100 posesiones, de los porcentajes × oportunidades por posesión de la liga de
  destino en la temporada anterior (ex ante); un factor de definición por métrica alinea la v5 con el registro de la
  v3.3 (fijado en la calibración);
- **combinada:** promedio de cuantiles w·v5 + (1 − w)·v3.3, con la regla de pesos de la F1 fijada en la temporada de
  calibración y examinada en las siguientes.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from bbnorm5 import config as C
from bbnorm5.aguas_abajo import hibrido as HB
from bbnorm5.salidas import combinada as CB
from bbnorm5.salidas import derivadas as DV
from bbnorm5.validacion import fichajes as VF

NIV = [("lo90", 0.05, "q5"), ("lo80", 0.10, "q10"), ("lo50", 0.25, "q25"), ("pred", 0.50, "q50"),
       ("hi50", 0.75, "q75"), ("hi80", 0.90, "q90"), ("hi90", 0.95, "q95")]


def dir_salida(cfg: dict):
    d = (C.DIR_DATOS / cfg["salida"]).resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


def banco(cfg: dict) -> pd.DataFrame:
    """Producción aplicada de la v3.3 sobre el examen reproducido en la F0 (no toca el banco versionado de la v5.0)."""
    f = dir_salida(cfg) / "banco_v33_reproducido.parquet"
    if f.exists():
        return pd.read_parquet(f)
    os.environ["CERNO_SIMULADOR"] = "v32"
    from bbfit import validacion as V
    V.DIR_VAL = C.RAIZ / cfg["reproducido"]
    return VF.banco_v33(salida=f)


def v5_destino(cfg: dict) -> pd.DataFrame:
    """Proyección publicada de la v5 (ex ante, recalibrada) en las 9 métricas, en formato largo."""
    from bbnorm5.validacion import protocolo as VP
    from bbnorm5.validacion import recalibracion as VR
    p, _ = VR.recalibradas(C.cargar("configs/v5/f8.yaml"))
    p = p[p["modelo"] == VR.RECAL]
    qs = [VF._q(q) for q in VF.CUANTILES]
    base = ["persona_v5", "liga", "anio", "obs"] + qs
    partes = []
    raz = DV.razones()
    raz["anio_sig"] = raz["temporada"].str[:4].astype(int) + 1          # razón de la temporada anterior (ex ante)
    for m, spec in cfg["metricas"].items():
        if spec.get("derivada") == "tiro":
            d = VP.derivadas_tiro(p, VR.RECAL, cfg["semilla"])
            d = d[d["metrica"] == m][base]
        else:
            d = p[p["metrica"] == spec["v5"]][base].copy()
            if spec.get("razon"):
                r = raz[["liga", "anio_sig", spec["razon"]]].rename(columns={"anio_sig": "anio", spec["razon"]: "r"})
                d = d.merge(r, on=["liga", "anio"], how="inner")
                for c in qs + ["obs"]:
                    d[c] = d[c] * d["r"]
                d = d.drop(columns="r")
        partes.append(d.assign(metrica=m))
    return pd.concat(partes, ignore_index=True)


def casos(cfg: dict) -> pd.DataFrame:
    """Fichajes × métrica con la v3.3 y la v5 en la misma escala (factor de definición fijado en la calibración)."""
    b = banco(cfg)
    b = b[b["metrica"].isin(cfg["metricas"]) & np.isfinite(b["real"]) & (b["min_total_real"] >= cfg["min_minutos"])]
    v = v5_destino(cfg).drop_duplicates(["persona_v5", "anio", "liga", "metrica"])
    d = b.merge(v, left_on=["persona_v5", "anio", "liga_d", "metrica"], right_on=["persona_v5", "anio", "liga", "metrica"],
                how="inner")
    cal = d[d["anio"].isin(cfg["pesos"]["calibracion"])]
    k = cal.groupby("metrica").apply(lambda g: float(np.nanmedian(g["real"] / g["obs"].replace(0, np.nan))),
                                     include_groups=False)
    d["k"] = d["metrica"].map(k)
    # mismo registro: fuera los casos cuyo observado de la v5 no es el de la v3.3 (p. ej., varios equipos en destino)
    d = d[np.abs(d["real"] / (d["k"] * d["obs"]) - 1) <= 0.05].copy()
    # defecto del producto publicado: la recalibración A4 de la v3.3 da intervalos de ±10¹⁰ en USG% de la Primera FEB
    # del corte 2022-23 (también en el banco versionado de la v5.0, aunque el examen de la F8 no los llegó a usar);
    # se excluyen esos casos de todas las versiones
    v33 = d[[c for c in d.columns if c.startswith("v33_")]].to_numpy(float)
    d["v33_defectuoso"] = ~np.all(np.isfinite(v33) & (np.abs(v33) < 1e3), axis=1)
    d = d[~d["v33_defectuoso"]].copy()
    for s, p, q in NIV:
        d[f"v5__{q}"] = d[q] * d["k"]
    d["v5__q50"] = d["q50"] * d["k"]
    for a, (lo, hi) in {50: ("q25", "q75"), 80: ("q10", "q90"), 90: ("q5", "q95")}.items():
        d[f"v5__lo{a}"], d[f"v5__hi{a}"] = d[lo] * d["k"], d[hi] * d["k"]
        d[f"v3.2__lo{a}"], d[f"v3.2__hi{a}"] = d[f"v33_lo{a}"], d[f"v33_hi{a}"]      # «v3.2» = el comparador (v3.3)
    d["v3.2__q50"] = d["v33_pred"]
    d["wis_v5"], d["wis_v3.2"] = HB._wis_mezcla(d, 1.0), HB._wis_mezcla(d, 0.0)
    return d[np.isfinite(d["wis_v5"]) & np.isfinite(d["wis_v3.2"])].reset_index(drop=True)


def examen(cfg: dict, d: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(cfg["semilla"])
    B = int(cfg["bootstrap"])
    cal = d[d["anio"].isin(cfg["pesos"]["calibracion"])]
    te = d[d["anio"].isin(cfg["prueba"])].reset_index(drop=True)
    pw = CB.pesos(cfg, cal)
    te["w"] = te["metrica"].map(dict(zip(pw["metrica"], pw["w"]))).fillna(0.5).to_numpy()
    reglas = {"v5": np.ones(len(te)), "v3.3": np.zeros(len(te)), "combinada": te["w"].to_numpy(float),
              "mezcla_50": np.full(len(te), 0.5)}
    esc = te.groupby("metrica")["wis_v3.2"].transform("mean").to_numpy()
    wis = {k: HB._wis_mezcla(te, w) for k, w in reglas.items()}
    filas = []
    for k, w in reglas.items():
        r, lo, hi = VF._boot_ratio(te["persona_v5"].to_numpy(), wis[k] / esc, wis["v3.3"] / esc, B, rng)
        filas.append({"version": k, "casos": len(te), "personas": int(te["persona_v5"].nunique()),
                      "frente_v33": r, "ic_lo": lo, "ic_hi": hi, "cobertura80": float(HB._cubre80(te, w).mean())})
    met = []
    for m, g in te.assign(**{f"wis_{k}": v for k, v in wis.items()}).groupby("metrica"):
        f = {"metrica": m, "casos": len(g), "w": float(g["w"].iloc[0]), "k_definicion": float(g["k"].iloc[0])}
        for k in reglas:
            f[f"{k}_frente_v33"] = float(g[f"wis_{k}"].mean() / g["wis_v3.3"].mean() - 1)
            f[f"cobertura80_{k}"] = float(HB._cubre80(g, reglas[k][g.index.to_numpy()]).mean())
        met.append(f)
    return pd.DataFrame(filas), pd.DataFrame(met), pw


def _excluidos(cfg: dict) -> int:
    b = banco(cfg)
    b = b[b["metrica"].isin(cfg["metricas"])]
    v = b[[c for c in b.columns if c.startswith("v33_")]].to_numpy(float)
    return int((~np.all(np.isfinite(v) & (np.abs(v) < 1e3), axis=1)).sum())


def ejecutar(cfg: dict) -> dict:
    out = dir_salida(cfg)
    d = casos(cfg)
    tot, met, pw = examen(cfg, d)
    pub = CB.pesos(cfg, d)                     # pesos para publicar: todas las temporadas
    tot.to_csv(out / "produccion_examen.csv", index=False)
    met.to_csv(out / "produccion_por_metrica.csv", index=False)
    pw.to_csv(out / "produccion_pesos_calibracion.csv", index=False)
    pub.to_csv(out / "produccion_pesos.csv", index=False)
    cols = ["persona_v5", "anio", "liga_d", "team_d", "temporada_d", "metrica", "real", "k", "min_total_real"] + \
        [c for c in d.columns if c.startswith(("v5__", "v3.2__"))]
    d[cols].to_parquet(out / "produccion_casos.parquet")
    comb = tot.set_index("version").loc["combinada"]
    v33 = tot.set_index("version").loc["v3.3"]
    lo, hi = cfg["publicar"]["cobertura_80"]
    decision = {"mejora_v33_ic_bajo_0": bool(comb["ic_hi"] < 0),
                "cobertura_no_peor": bool(abs(comb["cobertura80"] - 0.8) <= max(abs(v33["cobertura80"] - 0.8), 0.04)),
                "cobertura_en_rango": bool(lo <= comb["cobertura80"] <= hi)}
    decision["publicar"] = decision["mejora_v33_ic_bajo_0"] and decision["cobertura_no_peor"]
    res = {"casos": int(len(d)), "excluidos_v33_defectuoso": int(_excluidos(cfg)), "examen": tot.set_index("version").round(4).to_dict("index"), "decision": decision,
           "pesos": dict(zip(pub["metrica"], pub["w"]))}
    C.escribir_json({**C.metadatos(cfg), **res}, out / "meta_produccion.json")
    return res
