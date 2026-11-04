"""Línea de comandos de la v4.0 (modelo de equipo y métricas ancla).

    python -m bbequipo perfiles [--cortes] [--solo-cortes] [--temporadas T …]   # F0: perfiles ampliados x̃
    python -m bbequipo contrato                                                  # F0: contrato de datos (tramos)
    python -m bbequipo rapm-examen | rapm-producto | rapm-f1d                   # F1: examen, ajuste producto, F1-D

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
    sub.add_parser("rapm-examen", help="F1: examen prerregistrado §11.1, comprobaciones D2 y elección del prior (cortes)")
    sub.add_parser("rapm-f1d", help="F1-D: diagnóstico de contaminación del RAPM de origen")
    sub.add_parser("rapm-producto", help="F1: ajuste con todas las temporadas → data/modelos/v4_0/rapm_multiliga/<t>.csv.gz")
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
    elif a.orden == "rapm-examen":
        from . import examen_f1
        examen_f1.main(cfg)
    elif a.orden == "rapm-f1d":
        import json as _j
        import pandas as pd
        from . import examen_f1, rapm
        temps = list(cfg["perfil"]["temporadas"])
        perf = examen_f1.perfiles_completo(cfg, [t for t in temps if (C.dir_salida(cfg) / "perfiles" / f"{t}.csv.gz").exists()])
        d = rapm.dir_salida(cfg)
        tb = pd.concat([pd.read_csv(p_, low_memory=False) for p_ in sorted(d.glob("20*.csv.gz"))], ignore_index=True) if list(d.glob("20*.csv.gz")) else None
        res = examen_f1.f1d_contaminacion(cfg, perf, tb)
        (C.RAIZ / cfg["f1"]["f1d"]["salida"]).write_text(_j.dumps(res, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
        if tb is not None:                            # test-retest (§11.1 b) con el ajuste producto
            rt = examen_f1.test_retest(cfg, tb, perf)
            (examen_f1.dir_examen(cfg) / "test_retest.json").write_text(_j.dumps(rt, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
            print(_j.dumps(rt.get("resumen"), ensure_ascii=False))
    elif a.orden == "rapm-producto":
        from . import rapm
        rapm.exportar(cfg)
    print(json.dumps({"tiempo_s": round(time.time() - t0)}))


if __name__ == "__main__":
    main()
