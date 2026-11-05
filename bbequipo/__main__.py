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
    sub.add_parser("sinergia-examen", help="F2-A: examen de parejas nuevas (§11.2) y elección del rango")
    sub.add_parser("dirigidos-examen", help="F2-B: examen de los efectos dirigidos X→Y (§11.2)")
    sub.add_parser("sinergia-producto", help="F2-A: ajuste con todas las temporadas → data/modelos/v4_0/sinergia/")
    sub.add_parser("dirigidos-producto", help="F2-B: efectos publicados con todas las temporadas → sinergia/dirigidos/")
    sub.add_parser("conjunto-examen", help="F3: examen §11.3 de la función de conjunto en quintetos no vistos (puerta dura)")
    sub.add_parser("conjunto-producto", help="F3: ajuste con todas las temporadas, sólo si el examen lo autoriza")
    sub.add_parser("conjunto-ablacion", help="F3: ablación diagnóstica con ρ lineal (g aditiva por jugador)")
    sub.add_parser("conjunto-redes-corte", help="F3: redes por corte con la variante vigente (para los exámenes de F4)")
    eq = sub.add_parser("equipo-examen", help="F4: examen §11.4 de transiciones de equipo t → t+1 (ΔNet) por cortes")
    eq.add_argument("--ligas", nargs="*", default=None, help="sólo estas ligas (prueba rápida)")
    eq.add_argument("--cortes", nargs="*", type=int, default=None)
    sub.add_parser("a5-examen", help="A5: producción no lineal en minutos y rol frente a B9 lineal (§11.6), cortes anidados v3.3")
    sub.add_parser("a5-producto", help="A5: coeficientes con todos los cortes según la decisión por métrica → equipo/a5/")
    sub.add_parser("equipo-producto", help="F4: calibración con todos los cortes y Net̂ de los equipos de la última temporada → equipo/")
    an = sub.add_parser("anclas-examen", help="F5: NC e IM de los fichajes reales del examen y puerta §11.5 → equipo/anclas/")
    an.add_argument("--solo-nc", action="store_true")
    an.add_argument("--solo-im", action="store_true")
    an.add_argument("--cortes", nargs="*", type=int, default=None)
    sub.add_parser("anclas-producto", help="F5: referencias versionadas F_ref (liga×pos3) y F_mov (grupo de liga) → equipo/anclas/")
    ea = sub.add_parser("exportar-atlas", help="tablas v4.0 para el Atlas del artifact (β, parejas, red aditiva, referencias y calibraciones) → data/artifact/atlas_v40/")
    ea.add_argument("--salida", default=None)
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
    elif a.orden == "sinergia-examen":
        from . import examen_f2
        examen_f2.main(cfg)
    elif a.orden == "dirigidos-examen":
        from . import dirigidos
        dirigidos.examen(cfg)
    elif a.orden == "sinergia-producto":
        from . import sinergia
        sinergia.exportar(cfg)
    elif a.orden == "dirigidos-producto":
        from . import dirigidos
        dirigidos.exportar(cfg)
    elif a.orden == "conjunto-examen":
        from . import conjunto
        conjunto.main(cfg)
    elif a.orden == "conjunto-producto":
        from . import conjunto
        conjunto.exportar(cfg)
    elif a.orden == "conjunto-ablacion":
        from . import conjunto
        conjunto.ablacion_aditiva(cfg)
    elif a.orden == "conjunto-redes-corte":
        from . import conjunto
        conjunto.redes_corte(cfg)
    elif a.orden == "a5-examen":
        from . import a5
        a5.main(cfg)
    elif a.orden == "a5-producto":
        from . import a5
        a5.exportar(cfg)
    elif a.orden == "equipo-producto":
        from . import equipo
        equipo.exportar(cfg)
    elif a.orden == "anclas-examen":
        from . import anclas
        if a.solo_nc:
            d = anclas.nivel_cerno_examen(cfg); d.to_csv(anclas.dir_salida(cfg) / "nc_examen.csv.gz", index=False)
        elif a.solo_im:
            anclas.impacto_examen(cfg, cortes=a.cortes)
        else:
            anclas.main(cfg)
    elif a.orden == "exportar-atlas":
        from . import exportar_atlas as XA
        print(XA.main(a.salida or XA.SALIDA))
    elif a.orden == "anclas-producto":
        from . import anclas
        anclas.exportar(cfg)
    elif a.orden == "equipo-examen":
        from . import equipo
        equipo.main(cfg, solo_ligas=a.ligas, cortes=a.cortes)
    print(json.dumps({"tiempo_s": round(time.time() - t0)}))


if __name__ == "__main__":
    main()
