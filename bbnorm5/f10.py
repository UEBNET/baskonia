"""F10 · Estudio de viabilidad aguas abajo (encargo v5.0 §14; revisión 1.2): ejecuta los pasos en orden.

    python -m bbnorm5.f10 --config configs/v5/f10.yaml
    python -m bbnorm5.f10 --config configs/v5/f10.yaml --pasos landing

Pasos:
- por_partido: contribución por partido (producción v5 × minutos del motor v3.3), jugador, equipo y grupos de cinco
- nivel_kerno: NK desde el predictivo y desde el nivel de la v5, con el examen del NK vigente
- impacto: fiabilidad del RAPM, predicción del RAPM de t+1 con carrera, perfil v5 y grafo, y puentes
- landing: δ de la primera temporada en una liga nueva por métrica y grupo de origen-destino, y su persistencia
- hibrido: ¿la mejor versión (v5 o v3.2) en cada métrica? Decidido con un corte, examinado en los siguientes
- figuras: figuras del informe 10

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
        if paso == "por_partido":
            from bbnorm5.aguas_abajo import por_partido
            out = por_partido.ejecutar(cfg)
        elif paso == "nivel_kerno":
            from bbnorm5.aguas_abajo import nivel_kerno
            out = nivel_kerno.ejecutar(cfg)
        elif paso == "impacto":
            from bbnorm5.aguas_abajo import impacto
            out = impacto.ejecutar(cfg)
        elif paso == "landing":
            from bbnorm5.aguas_abajo import landing
            out = landing.ejecutar(cfg)
        elif paso == "hibrido":
            from bbnorm5.aguas_abajo import hibrido
            out = hibrido.ejecutar(cfg)
        elif paso == "figuras":
            from bbnorm5.aguas_abajo import figuras_f10
            out = {"figuras": figuras_f10.todas(cfg)}
        else:
            raise ValueError(paso)
        out["tiempo_s"] = round(time.time() - t0)
        resumen[paso] = out
        print(json.dumps(out, default=str, ensure_ascii=False), flush=True)
    return resumen


if __name__ == "__main__":
    main()
