"""CLI de la capa Federación Vasca.

    python -m bbstats.esf ejecutar [--ligas esf_1nac esf_jun] [--temporada 2026-27]   # botón EJECUTAR
    python -m bbstats.esf historico [--desde 2018-19] [--hasta 2026-27] [--ligas ...] [--sin-procesar]
    python -m bbstats.esf reprocesar [--temporadas 2024-25 2025-26] [--ligas ...]       # sin red
    python -m bbstats.esf estado
"""
from __future__ import annotations

import argparse
import json
import sys

from . import pipeline as P


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m bbstats.esf")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("ejecutar", help="descarga lo nuevo de UNA temporada (por defecto la actual) y la procesa")
    e.add_argument("--ligas", nargs="*")
    e.add_argument("--temporada")
    e.add_argument("--secuencial", action="store_true")
    h = sub.add_parser("historico", help="carga histórica: varias temporadas, de la más reciente a la más antigua")
    h.add_argument("--desde")
    h.add_argument("--hasta")
    h.add_argument("--ligas", nargs="*")
    h.add_argument("--sin-procesar", action="store_true")
    h.add_argument("--sin-descarga", action="store_true")
    r = sub.add_parser("reprocesar", help="regenera la salida desde los brutos (sin red)")
    r.add_argument("--ligas", nargs="*")
    r.add_argument("--temporadas", nargs="*")
    sub.add_parser("estado", help="temporadas, ligas y filas disponibles")
    sub.add_parser("artifact", help="datos del Artifact Kerno Basque Analytics (data/basko/artifact)")
    a = ap.parse_args(argv)
    cfg = P.load_config()
    if a.cmd == "ejecutar":
        rep = P.ejecutar(a.ligas, a.temporada, config=cfg, paralelo=not a.secuencial)
    elif a.cmd == "historico":
        ts = list(reversed(P.temporadas(cfg, a.desde, a.hasta)))
        rep = P.run(a.ligas, ts, descargar=not a.sin_descarga, procesar=not a.sin_procesar, config=cfg)
    elif a.cmd == "reprocesar":
        rep = P.reprocesar(a.ligas, a.temporadas, config=cfg)
    elif a.cmd == "artifact":
        from .artifact import exportar
        print(exportar())
        return 0
    else:
        idx = P.ruta(cfg, "procesado") / "temporadas.json"
        print(idx.read_text(encoding="utf-8") if idx.exists() else "Sin datos procesados todavía.")
        return 0
    bad = [r for r in rep["resultados"] if r["estado"] == "error"]
    for r in rep["resultados"]:
        print(f"{r['temporada']} {r['liga']:12s} {r['estado']:18s} nuevos={r['partidos_nuevos']:4d} "
              f"acta={r['partidos_con_acta']}/{r['partidos_calendario']} filas={r['filas_jugadores']}"
              + (f"  ERRORES: {r['errores'][:2]}" if r["errores"] else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
