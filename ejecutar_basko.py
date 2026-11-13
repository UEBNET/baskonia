"""Botón EJECUTAR de la capa Federación Vasca (basketbasko.com) en versión script.

    python ejecutar_basko.py                          # todas las ligas activas, temporada en curso
    python ejecutar_basko.py esf_1nac esf_jun         # sólo esas ligas
    python ejecutar_basko.py --temporada 2024-25      # otra temporada (sólo esa)

Sólo descarga cuando se ejecuta: no hay ninguna tarea programada. Lo ya descargado no se vuelve a pedir.
"""
import sys

from bbstats.esf.__main__ import main

if __name__ == "__main__":
    args = sys.argv[1:]
    temporada = []
    if "--temporada" in args:
        i = args.index("--temporada")
        temporada = ["--temporada", args[i + 1]]
        args = args[:i] + args[i + 2:]
    sys.exit(main(["ejecutar"] + (["--ligas", *args] if args else []) + temporada))
