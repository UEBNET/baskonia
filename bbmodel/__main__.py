"""Línea de comandos de los algoritmos A y B.

    python -m bbmodel ajustar              # ajusta con todas las temporadas y guarda resultados
    python -m bbmodel validar              # examen: predice los cambios de liga 2023-24→24-25 y 24-25→25-26
    python -m bbmodel evaluacion-ligas     # recalcula los JSON de la pestaña «Evaluación de ligas»
    python -m bbmodel ajustar-b            # algoritmo B (red neuronal): ajuste final y traducciones
    python -m bbmodel validar-b            # algoritmo B: mismo examen que el A
    python -m bbmodel mesa-normalizacion   # JSON de la pestaña «Normalización de ligas»
    python -m bbmodel nacionalidades       # nacionalidad de cada jugador (datos brutos + enlace por persona)
    python -m bbmodel dataset-normalizado  # dataset completo A+B (todas las ligas, temporadas y jugadores)
    python -m bbmodel pista                # rasgos de pista: zonas de tiro, canastas asistidas, RAPM (jugada a jugada)
    python -m bbmodel contexto             # nivel de compañeros y rivales en pista y sensibilidad de cada métrica
    python -m bbmodel interacciones        # efectos X → Y entre compañeros (cuota de tiro, eFG%, asistidas…)
    python -m bbmodel mesa-quintetos       # datos de la pestaña «Quintetos y conexiones»
    python -m bbmodel escalas              # escalas ±100 (Euroliga = 0) para el Atlas y Quintetos
    python -m bbmodel amortiguar [--validar [--variante V] | --elegir | --diagnostico parametros.json]
                                           # normalización con el salto de nivel amortiguado (docs/normalizacion_amortiguada.md)

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
    sub.add_parser("nacionalidades", help="nacionalidad de cada jugador → data/modelos/nacionalidades.csv")
    sub.add_parser("crosswalk", help="correspondencia de jugadores entre ligas con confianza → "
                                     "data/processed/player_id_crosswalk.csv y crosswalk_revision.csv")
    mq = sub.add_parser("mesa-quintetos", help="datos de la pestaña «Quintetos y conexiones» (JSON comprimidos)")
    mq.add_argument("--salida", default="data/artifact")
    es = sub.add_parser("escalas", help="escalas de lectura ±100 (referencia Euroliga) → meta.json del Atlas e indice.json de Quintetos")
    es.add_argument("--salida", default="data/artifact")
    sub.add_parser("pista", help="rasgos de pista (zonas de tiro, canastas asistidas, RAPM) → data/modelos/pista/")
    cx = sub.add_parser("contexto", help="contexto de nivel (compañeros y rivales) y sensibilidad de cada métrica")
    cx.add_argument("--bootstrap", type=int, default=50)
    sub.add_parser("interacciones", help="efectos X → Y entre compañeros → data/modelos/interacciones/")
    am = sub.add_parser("amortiguar", help="normalización amortiguada → data/modelos/normalizacion_amortiguada/")
    am.add_argument("--validar", action="store_true", help="examen temporal y dejando fuera una liga (lineal vs amortiguado)")
    am.add_argument("--diagnostico", default=None, help="parametros.json de un ajuste del A: diagnóstico del esquema lineal")
    am.add_argument("--variante", default=None, help="variante de configs/normalization.yaml (por defecto, la elegida)")
    am.add_argument("--elegir", action="store_true", help="compara las variantes validadas y elige con el corte más antiguo")
    dn = sub.add_parser("dataset-normalizado", help="dataset completo de equivalentes EuroLeague (A+B) y JSON de la Mesa")
    dn.add_argument("--salida", default="data/artifact", help="carpeta de los JSON de la Mesa (datos/)")
    args = ap.parse_args(argv)

    if args.orden == "amortiguar":
        from threadpoolctl import threadpool_limits
        threadpool_limits(1)
        from . import amortiguacion
        amortiguacion.main(validar=args.validar, diagnostico_params=args.diagnostico, variante=args.variante,
                           elegir=args.elegir)
        return
    if args.orden == "mesa-quintetos":
        from . import mesa_quintetos
        mesa_quintetos.main(args.salida)
        return
    if args.orden == "escalas":
        from . import escalas
        escalas.escribir(args.salida)
        return
    if args.orden == "pista":
        from . import pista
        pista.construir()
        return
    if args.orden == "contexto":
        from . import contexto
        contexto.main(args.bootstrap)
        return
    if args.orden == "interacciones":
        from . import interacciones
        interacciones.construir()
        return
    if args.orden == "crosswalk":
        from . import crosswalk
        print(json.dumps(crosswalk.ejecutar(), ensure_ascii=False, indent=1))
        return
    if args.orden == "nacionalidades":
        from . import nacionalidad
        nacionalidad.main()
        return
    if args.orden == "dataset-normalizado":
        from . import dataset_normalizado
        dataset_normalizado.main(args.salida)
        return
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
        # Matrices pequeñas: con varios hilos de BLAS cada paso es ~14 veces más lento (sobresuscripción)
        from threadpoolctl import threadpool_limits
        threadpool_limits(1)
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
