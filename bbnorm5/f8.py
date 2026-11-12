"""F8 · Validación integral (encargo v5.0 §12; revisión 1.2, criterios 9–11).

    python -m bbnorm5.f8 --config configs/v5/f8.yaml

Pasos:
- base: base de la proyección en contexto con λ del paso 2 estimado sin fugas para cada año objetivo
- predicciones: predicciones fuera de tiempo de la v5 (2023-24 a 2025-26) con sus variantes
- banco: banco de fichajes reales V32_corte con la producción aplicada de la v3.3 (y el centro de la v4.2)
- fichajes: examen principal (WIS con IC por persona, cobertura, anchura, navaja de estilos)
"""
from __future__ import annotations

import argparse
import json
import time

from bbnorm5 import config as C

DIR = C.DIR_DATOS / "validacion"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bbnorm5.f8")
    ap.add_argument("--config", default="configs/v5/f8.yaml")
    ap.add_argument("--pasos", nargs="*")
    a = ap.parse_args(argv)
    cfg = C.cargar(a.config)
    DIR.mkdir(parents=True, exist_ok=True)
    resumen = {}
    for paso in (a.pasos or cfg["pasos"]):
        t0 = time.time()
        print(f"== {paso}", flush=True)
        from bbnorm5.validacion import fichajes as VF
        if paso == "base":
            out = {"filas": len(VF.base_v5(cfg))}
        elif paso == "predicciones":
            out = {"filas": len(VF.predicciones_v5(cfg))}
        elif paso == "banco":
            out = {"filas": len(VF.banco_v33())}
        elif paso == "fichajes":
            out = VF.comparar(cfg)
        else:
            raise ValueError(paso)
        out["tiempo_s"] = round(time.time() - t0)
        resumen[paso] = out
        print(json.dumps(out, default=str, ensure_ascii=False)[:3000], flush=True)
        C.escribir_json({**C.metadatos(cfg, None, {"paso": paso}), **out}, DIR / f"meta_{paso}.json")
    from bbfit.registro import experimento
    with experimento("v5_f8_validacion", "+".join(resumen), params={"config": cfg["_ruta"]}, semilla=cfg["semilla"]) as run:
        run.metricas({f"{p}_tiempo_s": v["tiempo_s"] for p, v in resumen.items()})
    return resumen


if __name__ == "__main__":
    main()
