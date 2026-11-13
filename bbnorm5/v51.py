"""v5.1 · Ejecutor de fases (docs/v5_1/00_encargo_v5_1.md).

    python -m bbnorm5.v51 --config configs/v5_1/f1.yaml --pasos examen generar

F1 · versión combinada:
- examen: pesos por métrica con la regla fijada, examen fuera de muestra y decisión de publicación
- generar: tablas normalizadas de la versión combinada en el formato de la v3.2 (data/v5_1/salidas/combinada/)
"""
from __future__ import annotations

import argparse
import json
import time

from bbnorm5 import config as C


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bbnorm5.v51")
    ap.add_argument("--config", default="configs/v5_1/f1.yaml")
    ap.add_argument("--pasos", nargs="*", default=["examen", "generar"])
    a = ap.parse_args(argv)
    cfg = C.cargar(a.config)
    resumen = {}
    for paso in a.pasos:
        t0 = time.time()
        print(f"== {paso}", flush=True)
        if paso == "examen":
            from bbnorm5.salidas import combinada
            out = combinada.ejecutar_examen(cfg)
        elif paso == "generar":
            from bbnorm5.salidas import combinada
            out = combinada.generar(cfg)
        else:
            raise ValueError(paso)
        out["tiempo_s"] = round(time.time() - t0)
        resumen[paso] = out
        print(json.dumps(out, default=str, ensure_ascii=False), flush=True)
    return resumen


if __name__ == "__main__":
    main()
