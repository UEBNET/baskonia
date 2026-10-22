"""Línea de comandos.

    python -m bbstats ejecutar                          # todas las ligas activas, temporada por defecto
    python -m bbstats ejecutar --ligas acb euroleague --temporada 2025-26
    python -m bbstats reprocesar                        # sin red, desde el último JSON bruto
    python -m bbstats historico                         # carga histórica: temporada_inicial .. temporada_por_defecto
    python -m bbstats historico --desde 2020-21 --hasta 2024-25 --ligas bbl
    python -m bbstats estado
    python -m bbstats servidor --puerto 8765            # API HTTP para el botón EJECUTAR
    python -m bbstats artifact --temporada 2026-27      # JSON del Artifact en data/artifact/ (no versionado)
    python -m bbstats entrenadores [--temporada T ...] [--ligas acb nba] [--sin-descarga]
    python -m bbstats feb [--ligas feb1 feb2 feb3] [--temporada T ...]   # informes FEB (cobertura, posesiones…)
    python -m bbstats contrato --ligas feb1 feb2 feb3                   # contrato de datos sobre los datos reales
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
    p = sub.add_parser("quintetos", help="Sólo quintetos y conexiones (jugada a jugada); ejecutar/historico ya los incluyen")
    p.add_argument("--ligas", nargs="*")
    p.add_argument("--temporadas", nargs="*")
    p.add_argument("--desde")
    p.add_argument("--hasta")
    p.add_argument("--sin-descarga", action="store_true")
    p.add_argument("--config")
    p = sub.add_parser("entrenadores", help="Entrenadores por partido, tramos club-temporada-entrenador y tabla global")
    p.add_argument("--temporada", nargs="*", help="Temporadas (por defecto, temporada_inicial .. temporada_por_defecto)")
    p.add_argument("--ligas", nargs="*")
    p.add_argument("--sin-descarga", action="store_true", help="Sólo brutos guardados, sin red")
    p.add_argument("--config")
    p = sub.add_parser("feb", help="Informes FEB sin red: partidos con grupo, cobertura, posesiones, sesgo de registro")
    p.add_argument("--ligas", nargs="*", help="feb1 feb2 feb3 (por defecto, las tres)")
    p.add_argument("--temporada", nargs="*")
    p.add_argument("--config")
    p = sub.add_parser("contrato", help="Contrato de datos (tipos, rangos, nulos, claves, minutos, jugada a jugada ↔ caja)")
    p.add_argument("--ligas", nargs="*", help="Por ahora, ligas FEB (feb1 feb2 feb3)")
    p.add_argument("--temporada", nargs="*")
    p.add_argument("--config")
    p = sub.add_parser("artifact", help="Genera los JSON que lee el Artifact a partir de los CSV procesados")
    p.add_argument("--temporada", nargs="*", help="Temporadas (por defecto, todas las procesadas)")
    p.add_argument("--salida", default="data/artifact", help="Carpeta de salida (no se versiona)")
    p.add_argument("--config")
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
    elif args.cmd == "quintetos":
        from .config import load_config, season_range
        cfg = load_config(args.config)
        temps = args.temporadas or (season_range(args.desde or cfg.get("temporada_inicial"), args.hasta or cfg.get("temporada_por_defecto"))
                                    if (args.desde or args.hasta) else None)
        out = api.quintetos(temporadas=temps, ligas=args.ligas or None, descargar=not args.sin_descarga, config=cfg,
                            progreso=print)
        print(json.dumps({k: {kk: v.get(kk) for kk in ("estado", "partidos", "partidos_nuevos", "quintetos", "validos_pct")}
                          for k, v in out.items()}, ensure_ascii=False, indent=1))
        print("Quintetos terminado")
        return 0
    elif args.cmd == "entrenadores":
        from .entrenadores import ejecutar as ejecutar_entrenadores
        out = ejecutar_entrenadores(temporadas=args.temporada or None, ligas=args.ligas or None,
                                    descargar=not args.sin_descarga, config=args.config, progreso=print)
        print("Entrenadores terminado")
        return 0 if all(v.get("estado") != "error" for v in out.values()) else 1
    elif args.cmd in ("feb", "contrato"):
        import pandas as pd
        from . import feb_informe
        ligas = args.ligas or list(feb_informe.FEB)
        otras = [l for l in ligas if l not in feb_informe.FEB]
        if otras:
            print(f"Ligas sin contrato automático todavía (sólo FEB): {otras}")
            ligas = [l for l in ligas if l in feb_informe.FEB]
        out = feb_informe.ejecutar(ligas=ligas, temporadas=args.temporada or None, config=args.config,
                                   progreso=print)
        with pd.option_context("display.width", 200, "display.max_columns", 40, "display.max_rows", 200):
            if args.cmd == "contrato":
                c = out["contrato"]
                cols = ["liga", "temporada", "partidos"] + [x for x in c.columns if x.endswith("_pct")]
                print(c[cols].to_string(index=False) if not c.empty else "Sin partidos")
                print("\n% de partidos que cumplen cada regla (sobre los aplicables); detalle en "
                      "data/processed/feb_contrato.csv")
            else:
                print(out["cobertura"].to_string(index=False) if not out["cobertura"].empty else "Sin partidos")
                print(out["posesiones"].to_string(index=False) if not out["posesiones"].empty else "")
        print("FEB terminado" if args.cmd == "feb" else "Contrato terminado")
        return 0
    elif args.cmd == "artifact":
        from pathlib import Path
        from .config import load_config, resolve_path
        from .pipeline import export_artifact
        cfg = load_config(args.config)
        root = resolve_path(cfg, "procesado")
        seasons = args.temporada or sorted((d.name for d in root.glob("*-*") if (d / "indice.json").exists()),
                                           reverse=True)
        for t in seasons:
            for f in export_artifact(root, t, Path(args.salida)):
                print(f)
        return 0
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
