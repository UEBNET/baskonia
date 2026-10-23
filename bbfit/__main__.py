"""CLI de bbfit:  python -m bbfit <orden> [opciones]

Órdenes (cada una registra su ejecución con bbfit.registro.experimento):
  roles       fase 3: roles por minutos y tramos de rol → data/modelos/roles/
  reemplazo   fase 4: elasticidad uso-eficiencia, libro de roles, transiciones, tendencias → data/modelos/reemplazo/
  entropia    fase 5: entropía de estilo y de rol, volatilidad, entropía de equipo → data/modelos/entropia/
  estilos     fase 6: taxonomía unificada de estilos jugador ↔ equipo → data/modelos/estilos_unificados/
              (--reusar-k reutiliza la tabla de selección de K si la configuración no ha cambiado)
  adaptacion  fase 7: adaptación al cambio de liga (Δ jerárquico, curva, censura, ADAPT%) → data/modelos/adaptacion/
              (reanudable: caché en experimentos/cache_adaptacion; --rehacer la ignora; --sin-validacion)

Para añadir una orden: una función en ORDENES que reciba los argumentos ya leídos.
"""
from __future__ import annotations

import argparse
import os
import sys

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")


def _roles(a):
    from . import roles
    return roles.main(a.temporadas, a.ligas, a.rehacer)


def _reemplazo(a):
    from . import reemplazo
    return reemplazo.main()


def _entropia(a):
    from . import entropia
    return entropia.main(a.temporadas)


def _estilos(a):
    from . import estilos_unificados
    return estilos_unificados.ejecutar(reusar_k=getattr(a, "reusar_k", False))


def _adaptacion(a):
    from . import adaptacion
    return adaptacion.main(rehacer=a.rehacer, sin_validacion=getattr(a, "sin_validacion", False))


ORDENES = {"roles": _roles, "reemplazo": _reemplazo, "entropia": _entropia, "estilos": _estilos,
           "adaptacion": _adaptacion}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m bbfit")
    p.add_argument("orden", choices=sorted(ORDENES))
    p.add_argument("--temporadas", nargs="*", default=None)
    p.add_argument("--ligas", nargs="*", default=None)
    p.add_argument("--rehacer", action="store_true", help="ignora la caché por liga-temporada")
    p.add_argument("--reusar-k", action="store_true", help="estilos: reutiliza la tabla de selección de K guardada")
    p.add_argument("--sin-validacion", action="store_true", help="adaptacion: omite el examen temporal y dejar fuera una liga")
    a = p.parse_args(argv)
    res = ORDENES[a.orden](a)
    if isinstance(res, dict):
        import json
        print(json.dumps({k: v for k, v in res.items() if not isinstance(v, (list, dict)) or len(str(v)) < 2000},
                         ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
