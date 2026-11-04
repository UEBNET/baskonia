"""Línea de comandos de la v4.0 (modelo de equipo y métricas ancla).

    python -m bbequipo perfiles [--cortes] [--solo-cortes] [--temporadas T …]   # F0: perfiles ampliados x̃
    python -m bbequipo contrato                                                  # F0: contrato de datos (tramos)

Las redes CVAE de la v3.2 se leen de experimentos/v3/ (no versionado); si faltan, se reentrenan con la configuración
final de configs/normalization_v32.yaml (misma semilla por red).
"""
from __future__ import annotations

import argparse
import json
import time

from . import config as C


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bbequipo", description="CERNO v4.0: modelo de equipo y métricas ancla")
    ap.add_argument("--config", default=None, help="configuración (por defecto configs/equipo_v40.yaml)")
    sub = ap.add_subparsers(dest="orden", required=True)
    pf = sub.add_parser("perfiles", help="F0: perfiles ampliados (ajuste completo y, con --cortes, por corte ≤ t)")
    pf.add_argument("--cortes", action="store_true", help="también los perfiles de los cortes de perfil.cortes")
    pf.add_argument("--solo-cortes", nargs="*", type=int, default=None,
                    help="sólo estos cortes (sin el ajuste completo); sin valores: todos los de perfil.cortes")
    pf.add_argument("--temporadas", nargs="*", default=None)
    sub.add_parser("contrato", help="F0: contrato de datos (inventario de tramos y decisión de cobertura)")
    a = ap.parse_args(argv)
    cfg = C.cargar(C.RAIZ / a.config if a.config else None)
    t0 = time.time()
    if a.orden == "perfiles":
        from . import perfiles
        cortes = None
        completo = True
        if a.solo_cortes is not None:
            cortes = a.solo_cortes or list(cfg["perfil"]["cortes"])
            completo = False
        elif a.cortes:
            cortes = list(cfg["perfil"]["cortes"])
        res = perfiles.exportar(cfg, cortes=cortes, temporadas=a.temporadas, completo=completo)
        print(json.dumps({"tiempo_s": res["tiempo_s"], "huella": res["huella"]}))
    elif a.orden == "contrato":
        from . import contrato
        contrato.generar(cfg)
    print(json.dumps({"tiempo_s": round(time.time() - t0)}))


if __name__ == "__main__":
    main()
