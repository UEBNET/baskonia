"""Línea de comandos.

    python -m bbstats ejecutar                          # todas las ligas activas, temporada por defecto
    python -m bbstats ejecutar --ligas acb euroleague --temporada 2025-26
    python -m bbstats reprocesar                        # sin red, desde el último JSON bruto
    python -m bbstats historico                         # carga histórica: temporada_inicial .. temporada_por_defecto
    python -m bbstats historico --desde 2020-21 --hasta 2024-25 --ligas bbl
    python -m bbstats estado
    python -m bbstats servidor --puerto 8765            # API HTTP para el botón EJECUTAR
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

from . import api


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bbstats", description="Extractor de estadísticas de baloncesto")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("ejecutar", "reprocesar"):
        p = sub.add_parser(name)
        p.add_argument("--ligas", nargs="*", help="Códigos de liga (por defecto, todas las activas)")
        p.add_argument("--temporada", help="Temporada, p.ej. 2025-26")
        p.add_argument("--config", help="Ruta alternativa a sources.json")
        if name == "ejecutar":
            p.add_argument("--secuencial", action="store_true", help="No paralelizar ligas")
    p = sub.add_parser("historico", help="Varias temporadas (por defecto de temporada_inicial a temporada_por_defecto)")
    p.add_argument("--ligas", nargs="*")
    p.add_argument("--desde", help="Primera temporada, p.ej. 2020-21")
    p.add_argument("--hasta", help="Última temporada, p.ej. 2026-27")
    p.add_argument("--temporadas", nargs="*", help="Lista explícita de temporadas")
    p.add_argument("--sin-descarga", action="store_true", help="Reprocesar los brutos sin red")
    p.add_argument("--config")
    p.add_argument("--secuencial", action="store_true")
    p = sub.add_parser("estado")
    p.add_argument("--temporada")
    p.add_argument("--config")
    p = sub.add_parser("servidor")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--puerto", type=int, default=8765)
    p.add_argument("--config")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    if args.cmd == "ejecutar":
        rep = api.ejecutar(ligas=args.ligas or None, temporada=args.temporada, config=args.config,
                           paralelo=not args.secuencial, progreso=print)
    elif args.cmd == "reprocesar":
        rep = api.reprocesar(ligas=args.ligas or None, temporada=args.temporada, config=args.config,
                             progreso=print)
    elif args.cmd == "historico":
        out = api.ejecutar_temporadas(temporadas=args.temporadas or None, desde=args.desde, hasta=args.hasta,
                                      ligas=args.ligas or None, config=args.config, paralelo=not args.secuencial,
                                      progreso=print, descargar=not args.sin_descarga)
        ok = True
        for rep in out["informes"]:
            print(f"\nResumen {rep['temporada']}:")
            ok &= _summary(rep)
        print("\nHistórico terminado")
        return 0 if ok else 1
    elif args.cmd == "estado":
        print(json.dumps(api.estado(args.temporada, args.config), ensure_ascii=False, indent=2))
        return 0
    else:
        from .server import serve
        serve(args.host, args.puerto, args.config)
        return 0
    print("\nResumen:")
    return 0 if _summary(rep) else 1


def _summary(rep: dict) -> bool:
    for l in rep["ligas"]:
        print(f"  {l['liga']:<11} {l['estado']:<18} jugadores={l['jugadores']:<5} "
              f"columnas_con_datos={l['columnas_con_datos']}" + (f"  errores={len(l['errores'])}" if l["errores"] else ""))
    print(f"Salida combinada: {rep['salida_combinada']}")
    return all(l["estado"] != "error" for l in rep["ligas"])


if __name__ == "__main__":
    sys.exit(main())
