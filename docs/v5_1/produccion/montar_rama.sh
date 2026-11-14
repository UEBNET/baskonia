#!/usr/bin/env bash
# v5.1 F6 · Reconstruye la rama de integración en producción (claude/v51-produccion) desde la rama de producción, con
# el parche de esta carpeta (portal, bbactualiza, skills, tests) y el código y los datos de la v5.1 de esta rama.
#   bash docs/v5_1/produccion/montar_rama.sh <carpeta de destino>
# Después, en el destino: PYTHONPATH=. python -m bbactualiza.normalizacion51 (2026-27 con los datos de producción).
set -euo pipefail
ORIG=$(cd "$(dirname "$0")/../../.." && pwd)
DEST=${1:?carpeta de destino}
git -C "$ORIG" fetch -q origin claude/jolly-thompson-qczxl4
git -C "$ORIG" worktree add -q -b claude/v51-produccion "$DEST" origin/claude/jolly-thompson-qczxl4
cd "$DEST"
git apply --binary "$ORIG/docs/v5_1/produccion/v51_produccion.patch"
cp -r "$ORIG/bbnorm5" bbnorm5 && find bbnorm5 -name __pycache__ -type d -prune -exec rm -rf {} +
mkdir -p configs data/v5 data/v5_1/salidas/combinada
cp -r "$ORIG/configs/v5" configs/v5 && cp -r "$ORIG/configs/v5_1" configs/v5_1
cp -r "$ORIG/data/v5_1/kit/v5/." data/v5/ && cp "$ORIG/data/v5_1/kit/meta_kit.json" data/v5/meta_kit.json
cp "$ORIG/data/v5_1/kit/v5_1/salidas/combinada/meta.json" data/v5_1/salidas/combinada/meta.json
cp -r "$ORIG/data/v5_1/producto" data/v5_1/producto
echo "Rama montada en $DEST. Falta: PYTHONPATH=. python -m bbactualiza.normalizacion51 y commit."
