"""Normalización v5.1 de la temporada en curso (encargo v5.1 F6; docs/v5_1/07_F6_integracion.md).

La v5.1 es, en cada métrica, la combinación w·v5 + (1 − w)·v3.2 que menos falla fuera de muestra. El botón la pone al
día con los modelos de la v5 congelados (como la v3.2 con su CVAE congelada):

1. `normalizacion_v51` (tras `roles`): caja por partido de 2026-27 desde los brutos, zonas, medida y carrera de la v5 con
   los parámetros congelados (kit de `data/v5/`), equivalente EuroLeague 2025-26 de la v5 y su componente por fila en
   `data/v5_1/producto/superposicion/<t>.csv.gz` (lo único que se versiona; los intermedios van a carpetas ignoradas).
2. `artifact` → `normalizados_v51`: combina ese componente con la v3.2 publicada (`bbnorm5.salidas.producto51.aplicar`)
   y escribe `datos/normalizados/<t>/regular_v51.json` y `datos/normalizados/vara_v51.json`.

El histórico (2020-21 … 2025-26) no cambia: su componente v5 está versionado y se combina con la v3.2 vigente al
publicar todo (`python -m bbactualiza.normalizacion51 --todas`).
"""
from __future__ import annotations

import argparse
import json

from . import TEMPORADA


def ejecutar(temporada: str = TEMPORADA, progreso=print) -> dict:
    from bbnorm5.salidas import producto51
    from bbnorm5.simulador51 import incremental
    r = incremental.ejecutar(temporada, rehacer_caja=True)
    s = producto51.superposicion(temporada)
    progreso(f"    v5.1 {temporada}: {r['personas']} personas ({r['personas_nuevas']} nuevas), "
             f"{s['filas']} de {s['de']} filas con v5")
    return {"personas": r["personas"], "personas_nuevas": r["personas_nuevas"], "filas_v5": s["filas"],
            "filas": s["de"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m bbactualiza.normalizacion51")
    ap.add_argument("--temporada", default=TEMPORADA)
    ap.add_argument("--todas", action="store_true", help="sólo publica (regular_v51.json) todas las temporadas")
    a = ap.parse_args(argv)
    from . import artefacto as A
    if a.todas:
        print(json.dumps(A.normalizados_v51_todas(), ensure_ascii=False))
    else:
        print(json.dumps(ejecutar(a.temporada), ensure_ascii=False))
        A.normalizados_v51(a.temporada)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
