"""Botón EJECUTAR en versión script: actualiza todas las ligas activas.

    python ejecutar.py                       # todas las ligas activas, temporada por defecto
    python ejecutar.py acb euroleague        # sólo esas ligas
    python ejecutar.py --temporada 2024-25   # otra temporada
"""
import sys

from bbstats.__main__ import main

if __name__ == "__main__":
    args = sys.argv[1:]
    temporada = []
    if "--temporada" in args:
        i = args.index("--temporada")
        temporada = ["--temporada", args[i + 1]]
        args = args[:i] + args[i + 2:]
    sys.exit(main(["ejecutar"] + (["--ligas", *args] if args else []) + temporada))
