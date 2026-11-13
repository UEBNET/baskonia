"""F10 bis · Híbrido por métrica v5 / v3.2: ¿se puede publicar en cada métrica la versión con menor error?

Examen: el protocolo de la F1 (cambios de liga t → t+1, ≥ 300 min en ambas; `protocolo_f1_casos_recal.parquet`), con el
WIS por caso de la v5 publicada (recalibrada) y de la v3.2 publicada.

Para que la ganancia no salga inflada («maldición del ganador»), las reglas se **deciden con el corte de calibración** y
se **evalúan en los cortes siguientes**, que no se usaron para decidir. El oráculo (elegir mirando el propio examen) se
muestra como cota optimista, no como resultado.

Reglas:
- v5 y v3.2 enteras;
- **elegir**: en cada métrica, la de menor WIS medio en la calibración;
- **elegir con prudencia**: la v3.2 sólo si gana en la calibración con IC 95 % (bootstrap de personas) que no cruza 0;
- **mezclar**: promedio de cuantiles (Vincent) w·q_v5 + (1 − w)·q_v3.2 con w por métrica en {0; 0,1; …; 1}, el de menor
  WIS en la calibración;
- **mezclar al 50 %**: w = 0,5 sin ajustar nada.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from bbnorm5 import config as C
from bbnorm5.validacion import fichajes as VF

CASOS = C.DIR_DATOS / "validacion" / "protocolo_f1_casos_recal.parquet"
FICHAJES = C.DIR_DATOS / "validacion" / "examen_fichajes_casos_recal.parquet"
NIV = (50, 80, 90)
REJILLA = np.round(np.linspace(0, 1, 11), 2)


def _wis_mezcla(c: pd.DataFrame, w) -> np.ndarray:
    w = np.asarray(w, float) if np.ndim(w) else np.full(len(c), float(w))
    m = lambda col: w * c[f"v5__{col}"].to_numpy(float) + (1 - w) * c[f"v3.2__{col}"].to_numpy(float)
    return VF.wis(c["real"].to_numpy(float), m("q50"), {a: m(f"lo{a}") for a in NIV}, {a: m(f"hi{a}") for a in NIV})


def _cubre80(c: pd.DataFrame, w) -> np.ndarray:
    w = np.asarray(w, float) if np.ndim(w) else np.full(len(c), float(w))
    lo = w * c["v5__lo80"].to_numpy(float) + (1 - w) * c["v3.2__lo80"].to_numpy(float)
    hi = w * c["v5__hi80"].to_numpy(float) + (1 - w) * c["v3.2__hi80"].to_numpy(float)
    y = c["real"].to_numpy(float)
    return (y >= lo) & (y <= hi)


def decidir(cal: pd.DataFrame, B: int, rng) -> pd.DataFrame:
    """Decisiones por métrica con el corte de calibración."""
    filas = []
    for m, g in cal.groupby("metrica"):
        a, b = g["wis_v5"].to_numpy(float), g["wis_v3.2"].to_numpy(float)
        r, lo, hi = VF._boot_ratio(g["persona_v5"].to_numpy(), a, b, B, rng)
        wis_w = [float(_wis_mezcla(g, w).mean()) for w in REJILLA]
        filas.append({"metrica": m, "casos_cal": len(g), "v5_frente_v32_cal": r, "ic_lo": lo, "ic_hi": hi,
                      "elegir": "v5" if a.mean() <= b.mean() else "v3.2",
                      "elegir_prudente": "v3.2" if lo > 0 else "v5",
                      "w_mezcla": float(REJILLA[int(np.argmin(wis_w))])})
    return pd.DataFrame(filas)


def evaluar(te: pd.DataFrame, dec: pd.DataFrame, B: int, rng) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = dec.set_index("metrica")
    te = te[te["metrica"].isin(d.index)].copy()
    w = {"v5": np.ones(len(te)), "v3.2": np.zeros(len(te)),
         "elegir": (te["metrica"].map(d["elegir"]) == "v5").to_numpy(float),
         "elegir_prudente": (te["metrica"].map(d["elegir_prudente"]) == "v5").to_numpy(float),
         "mezclar": te["metrica"].map(d["w_mezcla"]).to_numpy(float), "mezclar_50": np.full(len(te), 0.5)}
    # oráculo: la mejor versión de cada métrica mirando el propio examen (cota optimista)
    mejor = te.groupby("metrica")[["wis_v5", "wis_v3.2"]].mean().pipe(lambda x: (x["wis_v5"] <= x["wis_v3.2"]))
    w["oraculo"] = te["metrica"].map(mejor).to_numpy(float)
    esc = te.groupby("metrica")["wis_v3.2"].transform("mean").to_numpy()      # cada métrica pesa igual
    base = te["wis_v3.2"].to_numpy(float)
    filas, por_met = [], []
    for nom, ww in w.items():
        s = _wis_mezcla(te, ww)
        r, lo, hi = VF._boot_ratio(te["persona_v5"].to_numpy(), s / esc, base / esc, B, rng)
        filas.append({"regla": nom, "wis_frente_v32": r, "ic_lo": lo, "ic_hi": hi,
                      "cobertura80": float(_cubre80(te, ww).mean()), "casos": len(te),
                      "personas": int(te["persona_v5"].nunique())})
        te[f"wis_{nom}"] = s
    for m, g in te.groupby("metrica"):
        f = {"metrica": m, "casos_prueba": len(g)}
        for nom in w:
            f[f"{nom}_frente_v32"] = float(g[f"wis_{nom}"].mean() / g["wis_v3.2"].mean() - 1)
        por_met.append(f)
    return pd.DataFrame(filas), pd.DataFrame(por_met)


def fichajes(cfg: dict, rng) -> pd.DataFrame:
    """Lo mismo en el examen de fichajes reales de la F8 (producción de t+1 con su equipo real): v5 publicada frente a la
    v3.3 aplicada, en las 5 métricas comunes. Peso decidido con el primer corte y evaluado en los siguientes."""
    H = cfg["hibrido"]
    c = pd.read_parquet(FICHAJES)
    m5 = "ex_ante_sin_estilo_liga_recal"
    c = c.assign(**{"v5__q50": c[f"{m5}__q50"], "v3.2__q50": c["v33_pred"]})        # «v3.2» = la v3.3 aquí
    for a, (ql, qh) in {50: ("q25", "q75"), 80: ("q10", "q90"), 90: ("q5", "q95")}.items():
        c[f"v5__lo{a}"], c[f"v5__hi{a}"] = c[f"{m5}__{ql}"], c[f"{m5}__{qh}"]
        c[f"v3.2__lo{a}"], c[f"v3.2__hi{a}"] = c[f"v33_lo{a}"], c[f"v33_hi{a}"]
    c["real"] = c["y"]
    c["wis_v5"], c["wis_v3.2"] = _wis_mezcla(c, 1.0), _wis_mezcla(c, 0.0)
    c = c[np.isfinite(c["wis_v5"]) & np.isfinite(c["wis_v3.2"])]
    cal, te = c[c["anio"].isin(H["fichajes_calibracion"])], c[c["anio"].isin(H["fichajes_prueba"])]
    dec = decidir(cal, cfg["bootstrap"], rng)
    tot, _ = evaluar(te, dec, cfg["bootstrap"], rng)
    tot["examen"] = "fichajes (frente a la v3.3)"
    return tot.merge(dec[["w_mezcla"]].agg(["mean"]).T.rename(columns={"mean": "w_medio"}), how="cross")


def ejecutar(cfg: dict) -> dict:
    H = cfg["hibrido"]
    out_dir = C.dir_fase(cfg)
    rng = np.random.default_rng(cfg["semilla"] + 21)
    c = pd.read_parquet(CASOS)
    c = c[np.isfinite(c["wis_v5"]) & np.isfinite(c["wis_v3.2"])]
    cal, te = c[c["anio"].isin(H["calibracion"])], c[c["anio"].isin(H["prueba"])]
    dec = decidir(cal, cfg["bootstrap"], rng)
    tot, met = evaluar(te, dec, cfg["bootstrap"], rng)
    fi = fichajes(cfg, rng)
    fi.to_csv(out_dir / "hibrido_examen_fichajes.csv", index=False)
    # decisión para publicar: la misma regla con todos los cortes (para el formato; no se evalúa aquí)
    dec_todo = decidir(c, cfg["bootstrap"], rng)
    dec.to_csv(out_dir / "hibrido_decisiones_calibracion.csv", index=False)
    dec_todo.to_csv(out_dir / "hibrido_decisiones_todos.csv", index=False)
    tot.to_csv(out_dir / "hibrido_examen.csv", index=False)
    met.merge(dec, on="metrica").to_csv(out_dir / "hibrido_por_metrica.csv", index=False)
    res = {"calibracion": H["calibracion"], "prueba": H["prueba"],
           "examen": tot.set_index("regla").round(4).to_dict("index"),
           "examen_fichajes": fi.set_index("regla")[["wis_frente_v32", "ic_lo", "ic_hi", "cobertura80", "casos"]]
           .round(4).to_dict("index"),
           "decision_todos": dec_todo.set_index("metrica")[["elegir", "elegir_prudente", "w_mezcla"]].to_dict("index")}
    C.escribir_json({**C.metadatos(cfg, [CASOS]), **res}, out_dir / "meta_hibrido.json")
    return res
