"""F3 · Capa de medida (encargo v5.0 §7 y revisión 1.2): ejecuta los pasos en orden.

    python -m bbnorm5.f3 --config configs/v5/f3.yaml                  # todos los pasos
    python -m bbnorm5.f3 --config configs/v5/f3.yaml --pasos ajuste

Pasos:
- datos: jugador-partido de temporada regular con oportunidades reales, rol y mitad (bbnorm5/medida/datos.py)
- ajuste: por liga-temporada y métrica, validación primera → segunda mitad y ajuste de la temporada completa
  (bbnorm5/medida/validacion.py, bbnorm5/medida/eb.py)
- comprobaciones: contracción frente a exposición y sensibilidad del n* (bbnorm5/medida/comprobaciones.py)
- nuts: contraste en NumPyro (NUTS) del modelo por partido en ligas representativas (bbnorm5/medida/nuts.py)
- figuras: figuras del informe (bbnorm5/medida/figuras.py)
"""
from __future__ import annotations

import argparse
import time
from concurrent.futures import ProcessPoolExecutor

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


def ajuste(cfg: dict) -> dict:
    from bbnorm5.medida import datos as D
    from bbnorm5.medida import validacion as V
    a = cfg["ajuste"]
    V.S, V.MIN_UNIDADES = a["muestras_predictiva"], a["min_unidades"]
    V.EVAL_MIN_PARTIDOS, V.EVAL_MIN_MINUTOS = a["eval_min_partidos"], a["eval_min_minutos"]
    ls = pd.read_parquet(D.DIR / "partidos.parquet", columns=["liga", "temporada"]).drop_duplicates()
    pares = sorted(zip(ls["liga"], ls["temporada"]))

    def pasada(deriva):
        tareas = [(l, t, cfg["semilla"], None if deriva is None else
                   deriva[deriva["liga"] == l].set_index("metrica")["tau2_d"].to_dict()) for l, t in pares]
        casos, hiper, post = [], [], []
        with ProcessPoolExecutor(a["procesos"]) as ex:
            for (l, t, _, _), (c, h, p) in zip(tareas, ex.map(_una, tareas)):
                print(f"  {l} {t}: {len(c)} casos", flush=True)
                casos.append(c), hiper.append(h), post.append(p)
        return (pd.concat(x, ignore_index=True) for x in (casos, hiper, post))
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
    return {"ligas_temporada": len(pares), "casos": len(casos), "unidades_posterior": len(post)}


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
