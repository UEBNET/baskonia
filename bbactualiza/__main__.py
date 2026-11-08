"""python -m bbactualiza [--sin-descarga] [--pasos …] [--forzar] [--publicacion carpeta] [--json]"""
from __future__ import annotations

import argparse
import json
import sys

from . import TEMPORADA
from .orquestador import NOMBRES, ejecutar, tabla_md


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m bbactualiza", description=__doc__)
    ap.add_argument("--temporada", default=TEMPORADA)
    ap.add_argument("--pasos", nargs="*", choices=NOMBRES, help="sólo estos pasos (por defecto, todos)")
    ap.add_argument("--sin-descarga", action="store_true", help="reprocesa los brutos guardados, sin red")
    ap.add_argument("--forzar", action="store_true", help="recalcula aunque no haya partidos nuevos")
    ap.add_argument("--ligas", nargs="*", help="descarga sólo estas ligas (el posproceso usa todas)")
    ap.add_argument("--publicacion", default=None, help="carpeta del lote a publicar (por defecto ./publicacion)")
    ap.add_argument("--json", action="store_true", help="informe completo en JSON al final")
    a = ap.parse_args(argv)
    if a.temporada != TEMPORADA:
        ap.error(f"sólo se actualiza la temporada en curso ({TEMPORADA}); el histórico es estático")
    inf = ejecutar(a.temporada, a.pasos, a.sin_descarga, a.forzar, a.ligas, a.publicacion,
                   log=lambda m: print(m, file=sys.stderr, flush=True))
    print(json.dumps(inf, ensure_ascii=False, indent=1, default=str) if a.json else tabla_md(inf))
    return {"ok": 0, "sin_cambios": 0, "ocupado": 2}.get(inf["estado"], 1)


if __name__ == "__main__":
    sys.exit(main())
