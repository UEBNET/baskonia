"""Línea de comandos del extractor de la intranet clubes.basketbasko.com.

Credenciales en variables de entorno (nunca en el código ni en ficheros versionados):
    export BB_USUARIO='usuario-del-club'  BB_PASSWORD='***'

    python -m basketbasko explorar          # paso 1: muestra mínima + estructura (data/basketbasko/explorar/)
    python -m basketbasko extraer           # rastreo completo + procesado + dashboard
    python -m basketbasko procesar          # rehace tablas/dashboard desde el último bruto, sin red
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .client import ApiError, BasketBaskoClient
from .extract import explorar, extraer, leer_bruto, load_config, ultimo_bruto
from .transform import procesar


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="basketbasko", description="Extractor de la intranet de clubes de Basket Basko")
    ap.add_argument("comando", choices=("explorar", "extraer", "procesar"))
    ap.add_argument("--config", help="Ruta alternativa a config/basketbasko.json")
    ap.add_argument("--rivales", action="store_true", help="Rastrear también los equipos rivales")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(args.config)
    if args.rivales:
        cfg["incluir_rivales"] = True
    base = Path(cfg["directorio_datos"])
    try:
        if args.comando == "explorar":
            res = explorar(BasketBaskoClient(cfg), base / "explorar")
            print(json.dumps(res, ensure_ascii=False, indent=2)[:6000])
            print(f"\nMuestras guardadas en {base / 'explorar'}")
            return 0
        if args.comando == "extraer":
            bruto_path = extraer(BasketBaskoClient(cfg), cfg)
        else:
            bruto_path = ultimo_bruto(cfg)
            if not bruto_path:
                print("No hay ningún bruto todavía: ejecuta primero `extraer`", file=sys.stderr)
                return 1
        res = procesar(leer_bruto(bruto_path), base / "processed")
    except ApiError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"Procesado: {res.get('club', {})} → {base / 'processed'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
