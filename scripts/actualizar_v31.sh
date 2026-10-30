#!/bin/bash
# Simulador v3.1 con los datos al día, SIN sustituir la v1/v2 del repositorio (docs/simulador_v31.md).
#
# Rehace en una copia aislada del repositorio (data/processed y data/raw enlazados, sólo lectura en la práctica;
# data/modelos y experimentos propios) toda la cadena:
#   1. normalización v2 (crosswalk, nacionalidades, pista, A, B, amortiguada, dataset, contexto, interacciones, escalas)
#   2. normalización v3.1 (CVAE corregida reentrenada + combinación con la v2 rehecha)
#   3. capas de encaje (roles, reemplazo, entropía, estilos unificados) y adaptación (fase 7 + adaptación v3)
#   4. simulador v3.1: examen completo (V31 con adaptación), pesos de producción, diagnóstico V31A, histórico, exportación
# y deja los resultados en <copia>/data/modelos; scripts/importar_v31.sh los copia a las carpetas versionadas.
#
#   scripts/actualizar_v31.sh [carpeta de la copia, por defecto /tmp/cerno_v31]
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
W="${1:-/tmp/cerno_v31}"
rm -rf "$W" && mkdir -p "$W"
(cd "$RAIZ" && tar --exclude=./.git --exclude=./data/processed --exclude=./data/raw --exclude=./experimentos -cf - .) | tar -xf - -C "$W"
mkdir -p "$W/data/processed" "$W/experimentos"
ln -s "$RAIZ/data/raw" "$W/data/raw"
for f in "$RAIZ"/data/processed/*; do      # carpetas por temporada enlazadas; ficheros de la raíz copiados (crosswalk escribe ahí)
  if [ -d "$f" ]; then ln -s "$f" "$W/data/processed/"; else cp "$f" "$W/data/processed/"; fi
done
cd "$W"
export PYTHONPATH=. MLFLOW_DISABLE_AGENT_HINT=1
paso() { echo "=== $(date +%H:%M:%S) $*"; "$@"; }
# 1-2. normalización
for o in crosswalk nacionalidades pista ajustar ajustar-b amortiguar; do paso python3 -m bbmodel $o; done
paso python3 -m bbmodel dataset-normalizado --salida "$W/_art"
paso python3 -m bbmodel contexto
paso python3 -m bbmodel dataset-normalizado --salida "$W/_art"
paso python3 -m bbmodel interacciones
paso python3 -m bbmodel escalas
rm -f data/modelos/v3_1/niveles.csv                   # niveles y traducción cruzada con las redes nuevas
paso python3 -m bbnorm3 --config configs/normalization_v31.yaml ajustar-combinada
ln -sfn v3_1 data/modelos/v3_1_20261029             # la configuración del simulador v3.1 lee esta carpeta
# 3. capas de encaje y adaptación
paso python3 -m bbfit roles
paso python3 -m bbfit reemplazo
paso python3 -m bbfit entropia
paso python3 -m bbfit estilos --reusar-k
paso python3 -m bbfit adaptacion
mkdir -p data/modelos/adaptacion/v3_1/fase7
cp data/modelos/adaptacion/curvas.csv data/modelos/adaptacion/adaptation_priors.csv data/modelos/adaptacion/v3_1/fase7/
# 4. simulador v3.1
export CERNO_SIMULADOR=v31
paso python3 -m bbfit adaptacion-v3
paso python3 -m bbfit backtest --fuente V31 --escenario inicio --adaptacion
paso python3 -m bbfit pesos-simulador
paso python3 -m bbfit backtest --fuente V31A --escenario inicio --adaptacion --pesos-de V31_inicio_adapt
paso python3 -m bbfit historico
paso python3 -m bbfit exportar-simulador --salida "$W/_sim"
echo "=== $(date +%H:%M:%S) FIN (copia en $W)"
