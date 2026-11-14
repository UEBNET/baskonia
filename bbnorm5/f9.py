"""F9 · Contrato de salida de la v5 y sello de fiabilidad (encargo v5.0 §13): ejecuta los pasos en orden.

    python -m bbnorm5.f9 --config configs/v5/f9.yaml
    python -m bbnorm5.f9 --config configs/v5/f9.yaml --pasos destinos

Pasos:
- destinos: nivel, predictivo, traducción, probabilidades de umbral y sello por persona, métrica y liga de destino
  (`data/v5/salidas/<temporada>/destinos.parquet`), draws aparte y metadatos
- unir_destinos: junta las partes calculadas en paralelo (`--metricas … --parte k`) y añade TS%, eFG% y las
  variantes por 100 posesiones (derivadas.py)
- formato_v32: lo mismo en el formato de la v3.2 que consume el artifact (columnas de la v3.2, nunca menos, más las
  de la v5), en CSV comprimido
- diccionario: diccionario de columnas v5 y glosario ES/EN (ficheros hermanos; no se tocan los existentes)

Es el proceso paralelo de la v5: no modifica nada de la v3.2 ni el artifact.
"""
from __future__ import annotations

import argparse
import json
import time

from bbnorm5 import config as C


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bbnorm5.f9")
    ap.add_argument("--config", default="configs/v5/f9.yaml")
    ap.add_argument("--pasos", nargs="*")
    ap.add_argument("--metricas", nargs="*", help="destinos: sólo estas métricas (reparto entre procesos)")
    ap.add_argument("--parte", help="destinos: nombre de la parte (luego, paso unir_destinos)")
    a = ap.parse_args(argv)
    cfg = C.cargar(a.config)
    resumen = {}
    for paso in (a.pasos or cfg["pasos"]):
        t0 = time.time()
        print(f"== {paso}", flush=True)
        if paso == "destinos":
            from bbnorm5.salidas import destinos
            out = destinos.generar(cfg, a.metricas, a.parte)
        elif paso == "unir_destinos":
            from bbnorm5.salidas import destinos
            out = destinos.unir(cfg)
        elif paso == "formato_v32":
            from bbnorm5.salidas import formato_v32
            out = formato_v32.generar(cfg)
        elif paso == "diccionario":
            from bbnorm5.salidas import diccionario
            out = diccionario.generar(cfg)
        else:
            raise ValueError(paso)
        out["tiempo_s"] = round(time.time() - t0)
        resumen[paso] = out
        print(json.dumps(out, default=str, ensure_ascii=False), flush=True)
    return resumen


if __name__ == "__main__":
    main()
