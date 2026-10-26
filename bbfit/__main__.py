"""CLI de bbfit:  python -m bbfit <orden> [opciones]

Órdenes (cada una registra su ejecución con bbfit.registro.experimento):
  roles       fase 3: roles por minutos y tramos de rol → data/modelos/roles/
  reemplazo   fase 4: elasticidad uso-eficiencia, libro de roles, transiciones, tendencias → data/modelos/reemplazo/
  entropia    fase 5: entropía de estilo y de rol, volatilidad, entropía de equipo → data/modelos/entropia/
  estilos     fase 6: taxonomía unificada de estilos jugador ↔ equipo → data/modelos/estilos_unificados/
              (--reusar-k reutiliza la tabla de selección de K si la configuración no ha cambiado)
  simular     fase 8: simulador de encaje v2 de un jugador en un club (sin minutos manuales)
              --jugador «nombre» --club «nombre» [--liga acb] [--temporada 2025-26] [--bajas «a» «b»] [--json f.json]
  backtest    fase 8: examen temporal del simulador frente a los baselines (reanudable)
              [--fuente AB|A|A_corte] [--escenario inicio|real] [--adaptacion] [--pesos-de AB_inicio] [--cortes …]
  pesos-simulador   fase 8: pesos de producción (utilidad, calibración, Fit) → data/modelos/simulador/v2/pesos.json
  historico   fase 8: simulación v2 de todos los fichajes reales → data/modelos/simulador/v2/historico_<temp>.csv.gz
  exportar-simulador  fase 8: insumos del motor del navegador → data/artifact/simulador/ [--salida carpeta]
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


def _simular(a):
    from . import simulador as S
    if not a.jugador or not a.club:
        raise SystemExit("simular: hacen falta --jugador y --club")
    r = S.simular_cli(a.jugador, a.club, a.temporada, a.liga, a.bajas, a.n_sim, a.json)
    print(S.texto_resumen(r))
    return None


def _backtest(a):
    from . import validacion as V
    r = V.main(a.fuente, a.escenario, a.adaptacion, a.pesos_de, a.cortes)
    return {"resumen": r["resumen"], "bootstrap": r["bootstrap"]}


def _pesos(a):
    from . import validacion as V
    return V.pesos_produccion()


def _historico(a):
    from . import validacion as V
    return V.historico(a.temporadas)


def _exportar_sim(a):
    from . import sim_exportar as E
    return E.exportar(a.salida or E.SALIDA)


ORDENES = {"roles": _roles, "reemplazo": _reemplazo, "entropia": _entropia, "estilos": _estilos,
           "adaptacion": _adaptacion, "simular": _simular, "backtest": _backtest, "pesos-simulador": _pesos,
           "historico": _historico, "exportar-simulador": _exportar_sim}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m bbfit")
    p.add_argument("orden", choices=sorted(ORDENES))
    p.add_argument("--temporadas", nargs="*", default=None)
    p.add_argument("--ligas", nargs="*", default=None)
    p.add_argument("--rehacer", action="store_true", help="ignora la caché por liga-temporada")
    p.add_argument("--reusar-k", action="store_true", help="estilos: reutiliza la tabla de selección de K guardada")
    p.add_argument("--jugador", help="simular: nombre (o parte) del jugador")
    p.add_argument("--club", help="simular: nombre (o parte) del club de destino")
    p.add_argument("--liga", help="simular: competición del club de destino")
    p.add_argument("--temporada", help="simular: temporada base de los insumos (por defecto la de configs/simulation.yaml)")
    p.add_argument("--bajas", nargs="*", default=None, help="simular: jugadores de la plantilla que no estarán")
    p.add_argument("--n-sim", type=int, default=None, help="simular: iteraciones Monte Carlo")
    p.add_argument("--json", default=None, help="simular: guarda la salida completa en este fichero")
    p.add_argument("--fuente", default="AB", help="backtest: AB | A | A_corte")
    p.add_argument("--escenario", default="inicio", help="backtest: inicio | real")
    p.add_argument("--adaptacion", action="store_true", help="backtest: usa los priors de adaptación (fase 7)")
    p.add_argument("--pesos-de", default=None, help="backtest: reutiliza los pesos por corte de otra ejecución")
    p.add_argument("--cortes", nargs="*", default=None, help="backtest: temporadas t de examen (t → t+1)")
    p.add_argument("--salida", default=None, help="exportar-simulador: carpeta de salida")
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
