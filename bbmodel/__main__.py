"""Línea de comandos del algoritmo A.

    python -m bbmodel ajustar              # ajusta con todas las temporadas y guarda resultados
    python -m bbmodel validar              # examen: predice los cambios de liga 2023-24→24-25 y 24-25→25-26
    python -m bbmodel evaluacion-ligas     # recalcula los JSON de la pestaña «Evaluación de ligas»

Resultados en data/modelos/algoritmo_A/:
    parametros.json             todos los parámetros (para reutilizar sin reajustar)
    tipo_de_cambio.csv          m, s y su error por métrica y liga (lo más legible)
    traducciones/<temp>.csv     equivalente EuroLeague de cada jugador, por temporada
    validacion.csv / validacion_casos.csv
"""
from __future__ import annotations

import argparse
import json
import time

from . import modelo


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bbmodel", description="Algoritmo A: traducción de métricas a la EuroLeague")
    sub = ap.add_subparsers(dest="orden", required=True)
    a = sub.add_parser("ajustar", help="ajusta con todas las temporadas y guarda las traducciones")
    a.add_argument("--bootstrap", type=int, default=20, help="remuestreos para la incertidumbre (20 por defecto)")
    a.add_argument("--temporada-ref", default=modelo.TEMPORADA_REF, help="entorno EuroLeague de referencia")
    v = sub.add_parser("validar", help="examen fuera de muestra con cambios de liga reales")
    v.add_argument("--anios", type=int, nargs="+", default=[2023, 2024], help="año de inicio de la temporada de origen")
    v.add_argument("--bootstrap", type=int, default=10)
    e = sub.add_parser("evaluacion-ligas", help="recalcula la evaluación de ligas de la Mesa")
    e.add_argument("--salida", default="data/artifact/datos")
    args = ap.parse_args(argv)

    if args.orden == "evaluacion-ligas":
        from . import evaluacion_ligas
        evaluacion_ligas.main(args.salida)
        return

    t0 = time.time()
    print("Preparando datos (identidades y posiciones)…", flush=True)
    tabla, info = modelo.preparar()
    print(f"  {info['registros']} registros, {info['personas']} personas, acierto de posición {info['posicion']['acierto_cv']:.0%}")

    if args.orden == "ajustar":
        params = modelo.ajustar(tabla, n_boot=args.bootstrap)
        trad = modelo.traducir(tabla, params, args.temporada_ref)
        modelo.guardar(params, info, trad)
        print(f"Guardado en {modelo.DIR_SALIDA} ({time.time() - t0:.0f} s)")
    elif args.orden == "validar":
        import pandas as pd
        from . import validacion
        res = []
        for anio in args.anios:
            p = modelo.ajustar(tabla, hasta_anio=anio, n_boot=args.bootstrap, progreso=None)
            res.append(validacion.evaluar(tabla, anio, p))
            print(f"  temporada de origen {anio}: {len(res[-1])} predicciones", flush=True)
        r = pd.concat(res)
        resumen = validacion.resumir(r)
        modelo.DIR_SALIDA.mkdir(parents=True, exist_ok=True)
        r.round(4).to_csv(modelo.DIR_SALIDA / "validacion_casos.csv", index=False)
        resumen.round(4).to_csv(modelo.DIR_SALIDA / "validacion.csv", index=False)
        print(resumen.round(3).to_string(index=False))
        print(json.dumps({"tiempo_s": round(time.time() - t0)}))


if __name__ == "__main__":
    main()
