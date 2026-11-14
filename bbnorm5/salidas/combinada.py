"""v5.1 F1 · Versión combinada v5 / v3.2 (encargo v5.1 §2; F10 bis §13.1).

En cada métrica, la distribución publicada es el promedio de cuantiles de la v5 y la v3.2:

    Q_comb(u) = w·Q_v5(u) + (1 − w)·Q_v3.2(u)

**Pesos (regla fijada en configs/v5_1/f1.yaml antes de examinarla).** ŵ minimiza el WIS del examen de la F1 (cambios de
liga t → t+1) en una rejilla de 0 a 1; después se contrae hacia 0,5 según el número de casos:
w = 0,5 + n / (n + n0)·(ŵ − 0,5). Las métricas que el examen no cubre usan 0,5. Las variantes por 100 posesiones heredan
el peso de su métrica base.

**Examen.** Cada corte de prueba fija los pesos sólo con los cortes anteriores. Se compara con la v3.2 y con la v5 enteras
(WIS con IC 95 % por bootstrap de personas; cada métrica pesa igual) y se mide la cobertura del 80 %.

**Publicación.** Pesos con todos los cortes; tablas en el formato de la v3.2 (`formato_v32.normalizado` con `pesos`).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from bbnorm5 import config as C
from bbnorm5.aguas_abajo import hibrido as HB
from bbnorm5.salidas import derivadas as DV
from bbnorm5.salidas import formato_v32 as F
from bbnorm5.validacion import fichajes as VF

CASOS = HB.CASOS


def _dir(cfg: dict):
    d = (C.DIR_DATOS / cfg["salida"]).resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


def pesos(cfg: dict, c: pd.DataFrame) -> pd.DataFrame:
    """Peso de la v5 por métrica (nombres de la v3.2) con la regla de la configuración."""
    P = cfg["pesos"]
    rej = np.asarray(P["rejilla"], float)
    filas = []
    for m, g in c.groupby("metrica"):
        wis = np.array([HB._wis_mezcla(g, w).mean() for w in rej])
        w_hat = float(rej[int(np.argmin(wis))])
        n = len(g)
        w = 0.5 + n / (n + float(P["n0"])) * (w_hat - 0.5)
        filas.append({"metrica": m, "casos": n, "w_hat": w_hat, "w": round(w, 3),
                      "wis_v5": float(g["wis_v5"].mean()), "wis_v32": float(g["wis_v3.2"].mean()),
                      "wis_w": float(HB._wis_mezcla(g, w).mean())})
    return pd.DataFrame(filas)


def pesos_publicados(cfg: dict, tabla: pd.DataFrame) -> dict:
    """{métrica de la v3.2: w} para todas las del formato: examinadas, variantes por 100 y sin examen."""
    w = dict(zip(tabla["metrica"], tabla["w"]))
    out = {}
    for m3 in list(F.A_V32.values()) + ["efg_pct", "ts_pct"]:
        out[m3] = float(w.get(m3, cfg["pesos"]["sin_examen"]))
    for m32, (m5, _) in DV.POR_100.items():
        out[m32] = float(w.get(F.A_V32.get(m5, m5), cfg["pesos"]["sin_examen"]))
    return out


def _cubre(c: pd.DataFrame, w: np.ndarray) -> np.ndarray:
    return HB._cubre80(c, w)


def examen(cfg: dict, c: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(cfg["semilla"])
    B = int(cfg["bootstrap"])
    partes, tabla_pesos = [], []
    for T in cfg["examen"]["cortes_prueba"]:
        cal, te = c[c["anio"] < T], c[c["anio"] == T].copy()
        p = pesos(cfg, cal).assign(corte_prueba=T)
        tabla_pesos.append(p)
        te["w"] = te["metrica"].map(dict(zip(p["metrica"], p["w"]))).fillna(cfg["pesos"]["sin_examen"]).to_numpy()
        partes.append(te)
    te = pd.concat(partes, ignore_index=True)
    reglas = {"v5": np.ones(len(te)), "v3.2": np.zeros(len(te)), "combinada": te["w"].to_numpy(float),
              "mezcla_50": np.full(len(te), 0.5)}
    esc = te.groupby("metrica")["wis_v3.2"].transform("mean").to_numpy()
    wis = {k: HB._wis_mezcla(te, w) for k, w in reglas.items()}
    filas = []
    for k, w in reglas.items():
        fila = {"version": k, "casos": len(te), "personas": int(te["persona_v5"].nunique()),
                "cobertura80": float(_cubre(te, w).mean()), "wis_medio": float((wis[k] / esc).mean())}
        for ref in ("v3.2", "v5"):
            r, lo, hi = VF._boot_ratio(te["persona_v5"].to_numpy(), wis[k] / esc, wis[ref] / esc, B, rng)
            fila.update({f"frente_{ref}": r, f"ic_lo_{ref}": lo, f"ic_hi_{ref}": hi})
        filas.append(fila)
    tot = pd.DataFrame(filas)
    por_met = []
    for m, g in te.assign(**{f"wis_{k}": v for k, v in wis.items()}).groupby("metrica"):
        f = {"metrica": m, "casos": len(g), "w_medio": float(g["w"].mean()),
             "cobertura80_combinada": float(_cubre(g, g["w"].to_numpy(float)).mean())}
        for k in reglas:
            f[f"{k}_frente_v32"] = float(g[f"wis_{k}"].mean() / g["wis_v3.2"].mean() - 1)
        por_met.append(f)
    return tot, pd.DataFrame(por_met), pd.concat(tabla_pesos, ignore_index=True)


def ejecutar_examen(cfg: dict) -> dict:
    out = _dir(cfg)
    c = pd.read_parquet(CASOS)
    c = c[np.isfinite(c["wis_v5"]) & np.isfinite(c["wis_v3.2"])]
    tot, met, pc = examen(cfg, c)
    pub = pesos(cfg, c)
    tot.to_csv(out / "examen.csv", index=False)
    met.to_csv(out / "examen_por_metrica.csv", index=False)
    pc.to_csv(out / "pesos_por_corte.csv", index=False)
    pub.to_csv(out / "pesos.csv", index=False)
    comb = tot.set_index("version").loc["combinada"]
    lo, hi = cfg["publicar"]["cobertura_80"]
    decision = {"mejora_v32_ic_bajo_0": bool(comb["ic_hi_v3.2"] < 0),
                "cobertura_en_rango": bool(lo <= comb["cobertura80"] <= hi)}
    decision["publicar"] = all(decision.values())
    res = {"examen": tot.set_index("version").round(4).to_dict("index"), "decision": decision,
           "pesos": pesos_publicados(cfg, pub)}
    C.escribir_json({**C.metadatos(cfg, [CASOS]), **res}, out / "meta_examen.json")
    return res


def generar(cfg: dict) -> dict:
    """Tablas normalizadas de la versión combinada (formato de la v3.2), con los pesos publicados."""
    import json
    out = _dir(cfg)
    w = json.loads((out / "meta_examen.json").read_text())["pesos"]
    niv = pd.read_parquet(C.DIR_DATOS / "carrera" / "niveles_carrera.parquet")
    o = pd.read_parquet(C.DIR_DATOS / "carrera" / "observaciones.parquet",
                        columns=["persona_v5", "liga", "temporada", "metrica", "K", "N"])
    o = o[o["N"] > 0].assign(tasa=lambda x: x["K"] / x["N"])
    o = o.groupby(["persona_v5", "liga", "temporada", "metrica"], as_index=False)["tasa"].mean()
    k = F.factores_unidad(niv, o)
    n = F.normalizado(niv, o, k, excluir=(), dir_salida=out, pesos=w)
    meta = {**C.metadatos(cfg, None, {"paso": "generar"}), "factor_unidades": k, "normalizado": n, "pesos": w}
    C.escribir_json(meta, out / "meta.json")
    return {"temporadas": len(n), "filas": sum(x["filas"] for x in n)}
