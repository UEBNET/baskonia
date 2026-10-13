"""Línea de comandos de los algoritmos A y B.

    python -m bbmodel ajustar              # ajusta con todas las temporadas y guarda resultados
    python -m bbmodel validar              # examen: predice los cambios de liga 2023-24→24-25 y 24-25→25-26
    python -m bbmodel evaluacion-ligas     # recalcula los JSON de la pestaña «Evaluación de ligas»
    python -m bbmodel ajustar-b            # algoritmo B (red neuronal): ajuste final y traducciones
    python -m bbmodel validar-b            # algoritmo B: mismo examen que el A
    python -m bbmodel mesa-normalizacion   # JSON de la pestaña «Normalización de ligas»

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
    b = sub.add_parser("ajustar-b", help="algoritmo B: entrena el conjunto de redes y traduce")
    b.add_argument("--redes", type=int, default=5)
    b.add_argument("--pasos", type=int, default=3000)
    vb = sub.add_parser("validar-b", help="algoritmo B: examen fuera de muestra")
    vb.add_argument("--anios", type=int, nargs="+", default=[2023, 2024])
    vb.add_argument("--redes", type=int, default=3)
    e = sub.add_parser("evaluacion-ligas", help="recalcula la evaluación de ligas de la Mesa")
    e.add_argument("--salida", default="data/artifact", help="misma carpeta que python -m bbstats artifact")
    mn = sub.add_parser("mesa-normalizacion", help="datos de la pestaña «Normalización de ligas» (A y B)")
    mn.add_argument("--salida", default="data/artifact")
    args = ap.parse_args(argv)

    if args.orden == "mesa-normalizacion":
        from . import mesa_normalizacion
        mesa_normalizacion.main(args.salida)
        return
    if args.orden == "evaluacion-ligas":
        from . import evaluacion_ligas
        evaluacion_ligas.main(args.salida)
        return

    t0 = time.time()
    print("Preparando datos (identidades y posiciones)…", flush=True)
    tabla, info = modelo.preparar()
    print(f"  {info['registros']} registros, {info['personas']} personas, acierto de posición {info['posicion']['acierto_cv']:.0%}")

    if args.orden in ("ajustar-b", "validar-b"):
        from . import algoritmo_b as B
        if args.orden == "ajustar-b":
            cj = B.ConjuntoB(tabla, n_redes=args.redes, pasos=args.pasos)
            trad = cj.traducir()
            B.guardar(cj, trad, B.niveles_por_liga(cj))
            print(f"Guardado en {B.DIR_SALIDA_B} ({time.time() - t0:.0f} s)")
        else:
            import pandas as pd
            from . import validacion
            res = []
            for anio in args.anios:
                cj = B.ConjuntoB(tabla, hasta_anio=anio, n_redes=args.redes)
                res.append(cj.predecir_cambios(validacion.casos(tabla, anio)))
            B.DIR_SALIDA_B.mkdir(parents=True, exist_ok=True)
            pd.concat(res).round(5).to_csv(B.DIR_SALIDA_B / "validacion_casos.csv", index=False)
            print(f"Guardado en {B.DIR_SALIDA_B / 'validacion_casos.csv'}")
        return

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
