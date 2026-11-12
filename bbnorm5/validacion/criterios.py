"""F8 · Criterios de éxito 1–5 del encargo (§17) sobre la v5 publicada.

1. **Cobertura del nivel** al 80 % en [0,76, 0,84]:
   - el nivel es latente y no se puede examinar con datos de t+1 (F1 §4.3): se mide por simulación (examen de la F4,
     con el diseño real), por métrica e historial;
   - con datos, la cobertura del **predictivo** publicado (ex ante) fuera de tiempo, por métrica y por liga de
     destino, y la de λ en la LOLO.
2. **Anchura del intervalo de nivel** frente a la v3.2, en los mismos casos de la F1 (protocolo): mediana por caso de
   ancho v5 / ancho v3.2 publicado (que es de nivel, F1 §4.1), con IC por bootstrap de personas.
3. **Estabilidad de λ entre temporadas** (GLS del paso 2 de cada año objetivo, sólo con datos anteriores): salto de un
   año al siguiente en DT de su diferencia; ciclos de la NUTS.
4. **Anchura de λ** frente a la v3.2 (DT de la traducción ACB → liga en puntos de la tasa de la ACB).
5. **Probabilidades de umbral**: P(y_T > u_k) del predictivo publicado frente a la frecuencia observada, con u_k los
   percentiles 25, 50 y 75 de la liga de destino × rol en las temporadas anteriores (≥ 300 min). Diagrama de fiabilidad,
   Brier y error de calibración esperado (ECE).
"""
from __future__ import annotations

import pickle

import numpy as np
import pandas as pd

from bbnorm5 import config as C
from bbnorm5.validacion import fichajes as VF

DIR = C.DIR_DATOS / "validacion"
PUBLICADO = "ex_ante_sin_estilo_liga"
UMBRALES = (25, 50, 75)


# ------------------------------------------------------------------ 1
def cobertura_nivel() -> dict:
    s = pd.read_csv(C.DIR_DATOS / "carrera" / "examen_simulacion.csv")
    s = s[s["historial"].notna()]
    p = pd.read_parquet(DIR / "predicciones_v5.parquet", columns=["modelo", "metrica", "liga", "cambio_liga", "obs",
                                                                   "q10", "q90"])
    p = p[p["modelo"] == PUBLICADO]
    p["cubre"] = (p["obs"] >= p["q10"]) & (p["obs"] <= p["q90"])
    por_met = p.groupby("metrica")["cubre"].mean()
    por_liga = p.groupby("liga")["cubre"].mean()
    cambio = p[p["cambio_liga"] > 0].groupby("liga")["cubre"].agg(["mean", "size"])
    lolo = pd.read_csv(DIR / "lolo_v5.csv")
    t = s.groupby("metrica")["cob80_nivel"].agg(["min", "max"])
    t.to_csv(DIR / "criterio1_nivel_simulacion.csv")
    pd.DataFrame({"cob80_predictivo": por_met}).to_csv(DIR / "criterio1_predictivo_metrica.csv")
    pd.DataFrame({"cob80_predictivo": por_liga, "cob80_cambio_liga": cambio["mean"],
                  "casos_cambio_liga": cambio["size"]}).to_csv(DIR / "criterio1_predictivo_liga.csv")
    en = lambda x: bool((x >= 0.76) & (x <= 0.84))  # noqa: E731
    return {"nivel_sim_rango": [float(s["cob80_nivel"].min()), float(s["cob80_nivel"].max())],
            "nivel_sim_en_rango": f"{int(((s['cob80_nivel'] >= 0.76) & (s['cob80_nivel'] <= 0.84)).sum())}/{len(s)}",
            "predictivo_global": float(p["cubre"].mean()),
            "predictivo_metricas_en_rango": f"{sum(en(v) for v in por_met)}/{len(por_met)}",
            "predictivo_ligas_en_rango": f"{sum(en(v) for v in por_liga)}/{len(por_liga)}",
            "predictivo_cambio_liga": float(p.loc[p["cambio_liga"] > 0, "cubre"].mean()),
            "lolo_cob80_lambda": lolo.groupby("variante")["cubre80"].mean().round(3).to_dict()}


# ------------------------------------------------------------------ 2
def anchura_nivel(cfg: dict) -> dict:
    c = pd.read_parquet(DIR / "protocolo_f1_casos_publicada.parquet")
    c["ancho_v5"] = c["ancho_nivel80"] * c["k"]
    c["ancho_v32"] = c["v3.2_nivel__hi80"] - c["v3.2_nivel__lo80"]
    c = c[(c["ancho_v32"] > 0) & np.isfinite(c["ancho_v5"])]
    rng = np.random.default_rng(cfg["semilla"])
    B = int(cfg["examen"].get("bootstrap", 1000))
    filas = []
    for m, g in list(c.groupby("metrica")) + [("todas", c)]:
        lr = np.log(g["ancho_v5"].to_numpy() / g["ancho_v32"].to_numpy())
        per = g["persona_v5"].to_numpy()
        u, inv = np.unique(per, return_inverse=True)
        idx = [np.flatnonzero(inv == i) for i in range(len(u))]
        bs = []
        for _ in range(B):
            s = rng.integers(0, len(u), len(u))
            bs.append(np.median(lr[np.concatenate([idx[i] for i in s])]))
        lo, hi = np.exp(np.percentile(bs, [2.5, 97.5]))
        filas.append({"metrica": m, "casos": len(g), "ratio_mediano": float(np.exp(np.median(lr))), "ic_lo": lo,
                      "ic_hi": hi, "mas_estrecho": hi < 1, "ancho_v5_mediano": float(g["ancho_v5"].median()),
                      "ancho_v32_mediano": float(g["ancho_v32"].median())})
    t = pd.DataFrame(filas)
    t.to_csv(DIR / "criterio2_anchura_nivel.csv", index=False)
    met = t[t["metrica"] != "todas"]
    return {"metricas_mas_estrechas": f"{int(met['mas_estrecho'].sum())}/{len(met)}",
            "ratio_global": float(t.loc[t["metrica"] == "todas", "ratio_mediano"].iloc[0])}


# ------------------------------------------------------------------ 3
def estabilidad_lambda() -> dict:
    with open(C.DIR_DATOS / "ligas" / "lambda_paso2_modelos.pkl", "rb") as f:
        mods = pickle.load(f)
    filas = []
    anios = sorted({k[0] for k in mods})
    mets = sorted({k[1] for k in mods})
    for met in mets:
        for a0, a1 in zip(anios[:-1], anios[1:]):
            g0, g1 = mods.get((a0, met, "encogido")), mods.get((a1, met, "encogido"))
            if g0 is None or g1 is None:
                continue
            i0 = {l: i for i, l in enumerate(g0["ligas"])}
            sd_entre = float(np.std(g1["lambda"]))
            r = g1["ligas"][0]
            for j, l in enumerate(g1["ligas"]):
                if j == 0 or l not in i0 or r not in i0:
                    continue
                d0 = g0["lambda"][i0[l]] - g0["lambda"][i0[r]]
                d1 = g1["lambda"][j] - g1["lambda"][0]
                v0 = g0["cov"][i0[l], i0[l]] + g0["cov"][i0[r], i0[r]] - 2 * g0["cov"][i0[l], i0[r]]
                v1 = g1["cov"][j, j] + g1["cov"][0, 0] - 2 * g1["cov"][0, j]
                filas.append({"metrica": met, "liga": l, "de": a0, "a": a1, "salto": d1 - d0,
                              "z_salto": (d1 - d0) / np.sqrt(v0 + v1), "salto_rel_entre_ligas": abs(d1 - d0) / sd_entre})
    t = pd.DataFrame(filas)
    t.to_csv(DIR / "criterio3_estabilidad_lambda.csv", index=False)
    cy = pd.read_csv(C.DIR_DATOS / "ligas" / "ciclos_paso2.csv")
    return {"saltos": len(t), "z_abs_mediana": float(t["z_salto"].abs().median()),
            "cuota_z_abs_mayor_2": float((t["z_salto"].abs() > 2).mean()),
            "salto_rel_mediano": float(t["salto_rel_entre_ligas"].median()),
            "ciclo_conjunta_max": float(cy["residuo_conjunta_max"].abs().max()), "triangulos": len(cy)}


# ------------------------------------------------------------------ 4
def anchura_lambda() -> dict:
    from bbnorm5.ligas import modelo as LM
    from bbnorm5.ligas import resumen as LR
    from bbnorm5.ligas import resumen_paso2 as LR2
    lam = LR2.cargar(LM.BLOQUES_PASO2, "paso2_")
    temp = sorted({t for z in lam.values() for t in z["temporadas"]})[-1]
    v = LR.frente_v32(lam, temp)
    v["ratio"] = v["sd_v5_pp"] / v["sd_v32_pp"]
    v.to_csv(DIR / "criterio4_anchura_lambda.csv", index=False)
    g = v.groupby("metrica")["ratio"].median()
    return {"temporada": temp, "ratio_mediano_por_metrica": g.round(3).to_dict(),
            "ratio_mediano": float(v["ratio"].median())}


# ------------------------------------------------------------------ 5
def _p_supera(q: np.ndarray, u: np.ndarray) -> np.ndarray:
    """P(y > u) interpolando la función de distribución entre los cuantiles publicados (colas: la mitad del extremo)."""
    niv = np.array(VF.CUANTILES)
    out = np.empty(len(u))
    eps = 1e-9 * np.arange(len(niv))
    for i in range(len(u)):
        xp = q[i] + eps * max(abs(q[i]).max(), 1e-6)
        out[i] = 1 - np.interp(u[i], xp, niv, left=niv[0] / 2, right=1 - (1 - niv[-1]) / 2)
    return out


def umbrales(cfg: dict) -> dict:
    b = pd.read_parquet(DIR / "base_v5.parquet", columns=["persona_v5", "liga", "rol", "anio_obj", "metrica", "K",
                                                            "N", "min_temp"])
    b = b[(b["min_temp"] >= 300) & (b["N"] > 0)].drop_duplicates(["persona_v5", "liga", "anio_obj", "metrica"])
    b["tasa"] = b["K"] / b["N"]
    p = pd.read_parquet(DIR / "predicciones_v5.parquet")
    p = p[p["modelo"] == PUBLICADO].reset_index(drop=True)
    filas, casos = [], []
    for T, g in p.groupby("anio"):
        ref = b[(b["anio_obj"] < T) & (b["anio_obj"] >= T - 3)]
        pc = ref.groupby(["liga", "rol", "metrica"])["tasa"].quantile([u / 100 for u in UMBRALES]).unstack()
        pc = pc[ref.groupby(["liga", "rol", "metrica"]).size() >= 20]
        pc.columns = [f"u{u}" for u in UMBRALES]
        g = g.merge(pc.reset_index(), on=["liga", "rol", "metrica"], how="inner")
        q = g[[VF._q(x) for x in VF.CUANTILES]].to_numpy(float)
        for u in UMBRALES:
            ok = g[f"u{u}"].notna().to_numpy()
            pr = _p_supera(q[ok], g.loc[ok, f"u{u}"].to_numpy(float))
            casos.append(pd.DataFrame({"anio": T, "metrica": g.loc[ok, "metrica"].to_numpy(), "umbral": u,
                                       "p": pr, "supera": (g.loc[ok, "obs"] > g.loc[ok, f"u{u}"]).to_numpy()}))
    d = pd.concat(casos, ignore_index=True)
    d["tramo"] = np.minimum((d["p"] * 10).astype(int), 9)
    fia = d.groupby(["umbral", "tramo"]).agg(p_media=("p", "mean"), frecuencia=("supera", "mean"),
                                             casos=("p", "size")).reset_index()
    fia.to_csv(DIR / "criterio5_fiabilidad.csv", index=False)
    for (m, u), g in list(d.groupby(["metrica", "umbral"])) + [(("todas", u), g) for u, g in d.groupby("umbral")]:
        t = g.groupby("tramo").agg(p=("p", "mean"), f=("supera", "mean"), n=("p", "size"))
        filas.append({"metrica": m, "umbral": u, "casos": len(g), "brier": float(np.mean((g["p"] - g["supera"]) ** 2)),
                      "brier_clima": float(g["supera"].mean() * (1 - g["supera"].mean())),
                      "ece": float((t["n"] * (t["p"] - t["f"]).abs()).sum() / t["n"].sum()),
                      "p_media": float(g["p"].mean()), "frecuencia": float(g["supera"].mean())})
    t = pd.DataFrame(filas)
    t["habilidad_brier"] = 1 - t["brier"] / t["brier_clima"]
    t.to_csv(DIR / "criterio5_umbrales.csv", index=False)
    tot = t[t["metrica"] == "todas"]
    return {"casos": int(len(d)), "ece_por_umbral": dict(zip(tot["umbral"].astype(str), tot["ece"].round(4))),
            "habilidad_brier_por_umbral": dict(zip(tot["umbral"].astype(str), tot["habilidad_brier"].round(3))),
            "ece_max_metrica": float(t.loc[t["metrica"] != "todas", "ece"].max())}


def ejecutar(cfg: dict, cuales: tuple = (1, 2, 3, 4, 5)) -> dict:
    f = {1: lambda: cobertura_nivel(), 2: lambda: anchura_nivel(cfg), 3: lambda: estabilidad_lambda(),
         4: lambda: anchura_lambda(), 5: lambda: umbrales(cfg)}
    out = {f"criterio{k}": f[k]() for k in cuales}
    import json
    prev = json.loads((DIR / "criterios.json").read_text()) if (DIR / "criterios.json").exists() else {}
    C.escribir_json({**prev, **out}, DIR / "criterios.json")
    return out
