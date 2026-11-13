"""F10 · Estudio de viabilidad aguas abajo (encargo v5.0 §14; revisión 1.2): ejecuta los pasos en orden.

    python -m bbnorm5.f10 --config configs/v5/f10.yaml
    python -m bbnorm5.f10 --config configs/v5/f10.yaml --pasos landing

Pasos:
- landing: δ de la primera temporada en una liga nueva por métrica y grupo de origen-destino, y su persistencia

Las salidas van a `data/v5/aguas_abajo/`. Ningún proceso del producto las lee.
"""
from __future__ import annotations

import argparse
import json
import time

from bbnorm5 import config as C


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bbnorm5.f10")
    ap.add_argument("--config", default="configs/v5/f10.yaml")
    ap.add_argument("--pasos", nargs="*")
    a = ap.parse_args(argv)
    cfg = C.cargar(a.config)
    resumen = {}
    for paso in (a.pasos or cfg["pasos"]):
        t0 = time.time()
        print(f"== {paso}", flush=True)
        if paso == "landing":
            from bbnorm5.aguas_abajo import landing
            out = landing.ejecutar(cfg)
        else:
            raise ValueError(paso)
        out["tiempo_s"] = round(time.time() - t0)
        resumen[paso] = out
        print(json.dumps(out, default=str, ensure_ascii=False), flush=True)
    return resumen


if __name__ == "__main__":
    main()
