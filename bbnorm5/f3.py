"""F3 · Capa de medida (encargo v5.0 §7 y revisión 1.2): ejecuta los pasos en orden.

    python -m bbnorm5.f3 --config configs/v5/f3.yaml                  # todos los pasos
    python -m bbnorm5.f3 --config configs/v5/f3.yaml --pasos ajuste

Pasos:
- datos: jugador-partido de temporada regular con oportunidades reales, rol y mitad (bbnorm5/medida/datos.py)
- ajuste: por liga-temporada y métrica, validación primera → segunda mitad y ajuste de la temporada completa
  (bbnorm5/medida/validacion.py, bbnorm5/medida/eb.py)
- sigma_comun: experimento σ común a las temporadas de cada liga frente a σ por liga-temporada
- comprobaciones: contracción frente a exposición y sensibilidad del n* (bbnorm5/medida/comprobaciones.py)
- nuts: contraste en NumPyro (NUTS) del modelo por partido en ligas representativas (bbnorm5/medida/nuts.py)
- nuts_recomparar: rehace la comparación NUTS ↔ EB con las salidas EB actuales, sin volver a muestrear
- figuras: figuras del informe (bbnorm5/medida/figuras.py)
"""
from __future__ import annotations

import argparse
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from bbnorm5 import config as C


def _una(args):
    import os
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    from bbnorm5.medida import datos as D
    from bbnorm5.medida import validacion as V
    liga, temporada, semilla, deriva = args
    d = pd.read_parquet(D.DIR / "partidos.parquet", filters=[("liga", "==", liga), ("temporada", "==", temporada)])
    return V.liga_temporada(d, liga, temporada, semilla, deriva=deriva)


def _una_liga(args):
    import os
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    from bbnorm5.medida import datos as D
    from bbnorm5.medida import validacion as V
    liga, semilla, deriva = args
    d = pd.read_parquet(D.DIR / "partidos.parquet", filters=[("liga", "==", liga)])
    return V.liga_temporada(d, liga, "todas", semilla, deriva=deriva, sigma_comun=True)


def sigma_comun(cfg: dict) -> dict:
    """Experimento (decisión 3 de la puerta F3): σ común a las temporadas de cada liga, con medias por temporada y rol,
    frente a σ por liga-temporada. Mismas mitades, misma deriva (sin la liga) y mismas semillas por métrica."""
    from bbnorm5.medida import datos as D
    from bbnorm5.medida import validacion as V
    a = cfg["ajuste"]
    V.S, V.MIN_UNIDADES = a["muestras_predictiva"], a["min_unidades"]
    V.EVAL_MIN_PARTIDOS, V.EVAL_MIN_MINUTOS = a["eval_min_partidos"], a["eval_min_minutos"]
    der = pd.read_csv(D.DIR / "deriva_entre_mitades.csv")
    ligas = sorted(pd.read_parquet(D.DIR / "partidos.parquet", columns=["liga"])["liga"].unique())
    tareas = [(l, cfg["semilla"], der[der["liga"] == l].set_index("metrica")["tau2_d"].to_dict()) for l in ligas]
    casos, hiper, post = [], [], []
    with ProcessPoolExecutor(a["procesos"]) as ex:
        for (l, _, _), (c, h, p) in zip(tareas, ex.map(_una_liga, tareas)):
            print(f"  {l}: {len(c)} casos", flush=True)
            casos.append(c), hiper.append(h), post.append(p)
    casos, hiper, post = (pd.concat(x, ignore_index=True) for x in (casos, hiper, post))
    casos["rol"] = casos["rol"].str.split("|").str[-1]
    post["rol"] = post["rol"].str.split("|").str[-1]
    sal = D.DIR / "sigma_comun"
    sal.mkdir(exist_ok=True)
    casos.to_parquet(sal / "validacion_casos.parquet")
    hiper.to_csv(sal / "hiperparametros.csv", index=False)
    post.to_parquet(sal / "posteriores.parquet")
    base = pd.read_parquet(D.DIR / "validacion_casos.parquet")
    k = D.CLAVE + ["metrica", "modelo"]
    m = base.merge(casos[k + ["pit", "crps"]], on=k, suffixes=("_lt", "_liga"))
    m = m[m["modelo"].isin(["jer_sd_d", "jer_d"])]
    for x in ("lt", "liga"):
        m[f"cob80_{x}"] = (np.abs(m[f"pit_{x}"] - 0.5) <= 0.4).astype(float)
        m[f"cob50_{x}"] = (np.abs(m[f"pit_{x}"] - 0.5) <= 0.25).astype(float)
    r = m.groupby("metrica").agg(casos=("crps_lt", "size"), crps_lt=("crps_lt", "mean"), crps_liga=("crps_liga", "mean"),
                                 cob50_lt=("cob50_lt", "mean"), cob50_liga=("cob50_liga", "mean"),
                                 cob80_lt=("cob80_lt", "mean"), cob80_liga=("cob80_liga", "mean")).reset_index()
    r["mejora_crps"] = 1 - r["crps_liga"] / r["crps_lt"]
    # error estándar de la mejora por bootstrap de jugadores
    rng = np.random.default_rng(cfg["semilla"])
    ee = {}
    for met, g in m.groupby("metrica"):
        dif = (g["crps_lt"] - g["crps_liga"]).to_numpy()
        ee[met] = float(np.std([dif[rng.integers(0, len(dif), len(dif))].mean() for _ in range(200)]) / g["crps_lt"].mean())
    r["ee_mejora"] = r["metrica"].map(ee)
    r.to_csv(sal / "comparacion.csv", index=False)
    l = m.groupby(["liga", "metrica"]).agg(crps_lt=("crps_lt", "mean"), crps_liga=("crps_liga", "mean"),
                                           cob80_lt=("cob80_lt", "mean"), cob80_liga=("cob80_liga", "mean")).reset_index()
    l.to_csv(sal / "comparacion_por_liga.csv", index=False)
    return {"casos": len(m), "mejora_crps_mediana": float(r["mejora_crps"].median())}


def ajuste(cfg: dict) -> dict:
    from bbnorm5.medida import datos as D
    from bbnorm5.medida import validacion as V
    a = cfg["ajuste"]
    V.S, V.MIN_UNIDADES = a["muestras_predictiva"], a["min_unidades"]
    V.EVAL_MIN_PARTIDOS, V.EVAL_MIN_MINUTOS = a["eval_min_partidos"], a["eval_min_minutos"]
    ls = pd.read_parquet(D.DIR / "partidos.parquet", columns=["liga", "temporada"]).drop_duplicates()
    ligas = sorted(ls["liga"].unique())
    comun = a.get("sigma_comun_liga", True)

    def pasada(deriva):
        if comun:     # σ común a las temporadas de cada liga (decisión 3 de la puerta F3), medias por temporada y rol
            tareas = [(l, cfg["semilla"], None if deriva is None else
                       deriva[deriva["liga"] == l].set_index("metrica")["tau2_d"].to_dict()) for l in ligas]
            fn, nombres = _una_liga, [t[0] for t in tareas]
        else:
            tareas = [(l, t, cfg["semilla"], None if deriva is None else
                       deriva[deriva["liga"] == l].set_index("metrica")["tau2_d"].to_dict())
                      for l, t in sorted(zip(ls["liga"], ls["temporada"]))]
            fn, nombres = _una, [f"{t[0]} {t[1]}" for t in tareas]
        casos, hiper, post = [], [], []
        with ProcessPoolExecutor(a["procesos"]) as ex:
            for n, (c, h, p) in zip(nombres, ex.map(fn, tareas)):
                print(f"  {n}: {len(c)} casos", flush=True)
                casos.append(c), hiper.append(h), post.append(p)
        casos, hiper, post = (pd.concat(x, ignore_index=True) for x in (casos, hiper, post))
        for x in (casos, post):
            x["rol"] = x["rol"].str.split("|").str[-1]
        return casos, hiper, post
    # 1.ª pasada: sin deriva; con sus casos se estima τ²_d dejando fuera cada liga; 2.ª pasada: con deriva
    casos, hiper, _ = pasada(None)
    der = V.deriva_momentos(casos, hiper)
    der.to_csv(D.DIR / "deriva_entre_mitades.csv", index=False)
    casos, hiper, post = pasada(der)
    # posteriores publicadas: sólo el modelo preferido para el nivel de la temporada completa (sin deriva, que es de
    # validación): jer_sd en binomial y Poisson, jer en la normal
    normal = post["metrica"].map(lambda m: D.METRICAS[m][0] == "normal")
    post = post[(post["modelo"] == "jer_sd") | (normal & (post["modelo"] == "jer"))].reset_index(drop=True)
    casos.to_parquet(D.DIR / "validacion_casos.parquet")
    hiper.to_csv(D.DIR / "hiperparametros.csv", index=False)
    post.to_parquet(D.DIR / "posteriores.parquet")
    for nom, por in {"metrica": ["metrica", "modelo"], "liga": ["liga", "metrica", "modelo"],
                     "temporada": ["temporada", "metrica", "modelo"]}.items():
        V.resumen(casos, por).to_csv(D.DIR / f"validacion_por_{nom}.csv", index=False)
    # decisión 4 de la puerta F3: «muestra insuficiente» = sin posición (rol X) y N < n*/4 de su liga-temporada
    ns = hiper[(hiper["datos"] == "temporada")].sort_values("modelo").drop_duplicates(
        ["liga", "temporada", "metrica"], keep="last")[["liga", "temporada", "metrica", "n_estab"]]
    post = post.merge(ns, on=["liga", "temporada", "metrica"], how="left")
    post["muestra_insuficiente"] = (post["rol"] == "X") & (post["N"] < post["n_estab"] / 4)
    post.to_parquet(D.DIR / "posteriores.parquet")
    return {"ligas": len(ligas), "sigma_comun_liga": comun,
            "muestra_insuficiente": int(post["muestra_insuficiente"].sum()), "casos": len(casos), "unidades_posterior": len(post)}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bbnorm5.f3")
    ap.add_argument("--config", default="configs/v5/f3.yaml")
    ap.add_argument("--pasos", nargs="*")
    a = ap.parse_args(argv)
    cfg = C.cargar(a.config)
    from bbnorm5.medida import datos as D
    resumen = {}
    for paso in (a.pasos or cfg["pasos"]):
        t0 = time.time()
        print(f"== {paso}", flush=True)
        if paso == "datos":
            d = D.construir(cfg["temporadas"])
            out = {"jugador_partido": len(d), "unidades": int(d.groupby(D.CLAVE).ngroups)}
        elif paso == "ajuste":
            out = ajuste(cfg)
        elif paso == "sigma_comun":
            out = sigma_comun(cfg)
        elif paso == "comprobaciones":
            from bbnorm5.medida import comprobaciones as K
            c = K.contraccion(pd.read_parquet(D.DIR / "posteriores.parquet"), pd.read_csv(D.DIR / "hiperparametros.csv"))
            c.to_csv(D.DIR / "contraccion_por_exposicion.csv", index=False)
            s = K.sensibilidad_estabilizacion(D.cargar())
            s.to_csv(D.DIR / "estabilizacion_sensibilidad.csv", index=False)
            out = {"max_dif_peso": float((c["w_empirico"] - c["w_teorico"]).abs().max())}
        elif paso == "nuts":
            from bbnorm5.medida import nuts
            out = nuts.ejecutar(cfg)
        elif paso == "nuts_recomparar":
            from bbnorm5.medida import nuts
            out = nuts.recomparar(cfg)
        elif paso == "figuras":
            from bbnorm5.medida import figuras
            out = figuras.todas(cfg)
        else:
            raise ValueError(paso)
        out["tiempo_s"] = round(time.time() - t0)
        resumen[paso] = out
        print(out, flush=True)
        C.escribir_json({**C.metadatos(cfg, [D.DIR / "partidos.parquet"], {"paso": paso}), **out},
                        D.DIR / f"meta_{paso}.json")
    from bbfit.registro import experimento
    with experimento("v5_f3_medida", "+".join(resumen), params={"config": cfg["_ruta"]}, semilla=cfg["semilla"]) as run:
        run.metricas({f"{p}_tiempo_s": v["tiempo_s"] for p, v in resumen.items()})
    return resumen


if __name__ == "__main__":
    main()
