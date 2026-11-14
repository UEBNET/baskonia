"""v5.1 · Ejecutor de fases (docs/v5_1/00_encargo_v5_1.md).

    python -m bbnorm5.v51 --config configs/v5_1/f1.yaml --pasos examen generar

F1 · versión combinada:
- examen: pesos por métrica con la regla fijada, examen fuera de muestra y decisión de publicación
- generar: tablas normalizadas de la versión combinada en el formato de la v3.2 (data/v5_1/salidas/combinada/)

F2 · simulador (configs/v5_1/f2.yaml):
- produccion: producción por liga de destino combinada v5 / v3.3 en las 9 métricas, examen y decisión
- ensamblaje: contribución por partido con los minutos del motor y dependencias estimadas; jugador, equipo y grupos de cinco

F3 · Nivel Kerno (configs/v5_1/f2.yaml):
- nivel_kerno: NK con la contribución de la F2 frente al NK vigente reproducido; rango del año, rango de nivel y sello

F4 · Impacto (configs/v5_1/f2.yaml):
- impacto: RAPM multiliga con el perfil de nivel de la v5 en el prior; exámenes de equipo e Impacto frente a la F0

F5 · Landing (configs/v5_1/f2.yaml; la Landing de la F10 con configs/v5/f10.yaml):
- landing: δ₁ y δ₂ por grupo contraídos a través del perfil latente, examen de publicación y escalón en puntos de NK

F6 · Integración (cualquier config):
- incremental: proceso paralelo de la temporada en curso con los modelos congelados (data/v5_1/incremental/<t>/)
- producto: superposición por temporada sobre la v3.2 y vara_v51.json (data/v5_1/producto/)
- kit: lo mínimo de la v5 para el proceso paralelo en la rama de producción (data/v5_1/kit/)
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
    ap.add_argument("--temporada", default="2026-27")
    ap.add_argument("--rehacer-caja", action="store_true")
    a = ap.parse_args(argv)
    cfg = C.cargar(a.config)
    resumen = {}
    for paso in a.pasos:
        t0 = time.time()
        print(f"== {paso}", flush=True)
        if paso == "examen":
            from bbnorm5.salidas import combinada
            out = combinada.ejecutar_examen(cfg)
        elif paso == "produccion":
            from bbnorm5.simulador51 import produccion
            out = produccion.ejecutar(cfg)
        elif paso == "ensamblaje":
            from bbnorm5.simulador51 import ensamblaje
            out = ensamblaje.ejecutar(cfg)
        elif paso == "nivel_kerno":
            from bbnorm5.simulador51 import nivel_kerno
            out = nivel_kerno.ejecutar(cfg)
        elif paso == "impacto":
            from bbnorm5.simulador51 import impacto
            out = impacto.ejecutar(cfg)
        elif paso == "landing":
            from bbnorm5.simulador51 import landing51
            out = landing51.ejecutar(cfg)
        elif paso == "incremental":
            from bbnorm5.simulador51 import incremental
            out = incremental.ejecutar(a.temporada, rehacer_caja=a.rehacer_caja)
        elif paso == "producto":
            from bbnorm5.salidas import producto51
            out = producto51.generar()
        elif paso == "kit":
            from bbnorm5.simulador51 import kit
            out = kit.exportar()
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
