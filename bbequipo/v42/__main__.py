"""python -m bbequipo.v42 <orden> (CERNO v4.2; configs/v42.yaml)."""
from __future__ import annotations

import argparse
import json
import time


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m bbequipo.v42")
    sub = ap.add_subparsers(dest="orden", required=True)
    sub.add_parser("historial-examen", help="D1: examen prerregistrado de la normalización v4.2 (historial del jugador)")
    sub.add_parser("historial-examen-centrado", help="D1-c (POST HOC): variante centrada por temporada")
    sub.add_parser("historial-exportar", help="D1: previas por temporada para el artifact (sólo métricas que pasan)")
    a = ap.parse_args()
    t0 = time.time()
    if a.orden == "historial-examen":
        from . import historial as H
        r = H.examen()
        print(json.dumps(r["resumen"], ensure_ascii=False, indent=1))
    elif a.orden == "historial-examen-centrado":
        from . import historial as H
        r = H.examen(centrado=True)
        print(json.dumps(r["resumen"], ensure_ascii=False, indent=1))
    elif a.orden == "historial-exportar":
        from . import historial as H
        r = H.exportar()
        print(json.dumps({"metricas": r["metricas"]}, ensure_ascii=False))
    print(f"hecho en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
