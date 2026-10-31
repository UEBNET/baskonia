#!/bin/bash
# Importa al repositorio los modelos rehechos por scripts/actualizar_20ligas.sh (20 ligas, datos al 29-10-2026).
# La copia empezó siendo una réplica del repositorio: data/modelos se sustituye entero por el de la copia
# (conservando los enlaces v3_1_20261031 → v3_1 y v3_1/base_v2/normalizado → ../../normalizado) y se retira la
# versión anterior de 15 ligas (data/modelos/v3_1_20261029; sigue en el historial de git). Las cachés no se versionan.
#   scripts/importar_20ligas.sh [carpeta de la copia, por defecto /tmp/cerno_20ligas]
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
W="${1:-/tmp/cerno_20ligas}"
grep -q "FIN" "$W/actualizar.log" 2>/dev/null || { echo "la cadena de $W no ha terminado (falta FIN en actualizar.log)"; exit 1; }
rm -rf "$W/data/modelos/v3_1_20261029"
find "$W/data/modelos" -depth -type d \( -name "_cache" -o -name "cache_*" \) -exec rm -rf {} +
rm -rf "$RAIZ/data/modelos.nuevo" && cp -a "$W/data/modelos" "$RAIZ/data/modelos.nuevo"
rm -rf "$RAIZ/data/modelos" && mv "$RAIZ/data/modelos.nuevo" "$RAIZ/data/modelos"
echo "importado: $(du -sh "$RAIZ/data/modelos" | cut -f1) en data/modelos"
