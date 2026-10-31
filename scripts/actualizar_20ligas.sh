#!/bin/bash
# Cadena completa con las 20 ligas (31-10-2026: + CBA, BNXT, NCAA top-50, NBL, VTB; docs/fuentes_ligas_nuevas.md).
# Igual que scripts/actualizar_v31.sh (del que parte), con la v3.1 en data/modelos/v3_1_20261031. Tras «FIN», la
# importación al repositorio la hace scripts/importar_20ligas.sh (sustituye las capas de data/modelos por las nuevas).
#
# Rehace en una copia aislada del repositorio (data/processed y data/raw enlazados, sólo lectura en la práctica;
# data/modelos y experimentos propios) toda la cadena:
#   1. normalización v2 (crosswalk, nacionalidades, pista, A, B, amortiguada, dataset, contexto, interacciones, escalas)
#   2. normalización v3.1 (CVAE corregida reentrenada + combinación con la v2 rehecha)
#   3. capas de encaje (roles, reemplazo, entropía, estilos unificados) y adaptación (fase 7 + adaptación v3)
#   4. simulador v3.1: examen completo (V31 con adaptación), pesos de producción, diagnóstico V31A, histórico, exportación
# y deja los resultados en <copia>/data/modelos. Importación a las carpetas versionadas del repositorio:
#   <copia>/data/modelos/v3_1           → data/modelos/v3_1_<fecha>/ (sin base_v2) y su normalizado v2 en base_v2/ (gzip)
#   <copia>/data/modelos/adaptacion/v3_1 y simulador/v3_1 → las mismas rutas del repositorio
#
#   scripts/actualizar_20ligas.sh [carpeta de la copia] [reanudar]
set -euo pipefail          # cualquier paso que falle (también la auditoría) detiene la actualización
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
W="${1:-/tmp/cerno_20ligas}"
DESDE="${2:-}"            # opcional: nombre de un paso para reanudar sin rehacer la copia (p. ej. "roles")
if [ -z "$DESDE" ]; then rm -rf "$W" && mkdir -p "$W"
(cd "$RAIZ" && tar --exclude=./.git --exclude=./data/processed --exclude=./data/raw --exclude=./experimentos -cf - .) | tar -xf - -C "$W"
mkdir -p "$W/data/processed" "$W/experimentos"
ln -s "$RAIZ/data/raw" "$W/data/raw"
for f in "$RAIZ"/data/processed/*; do      # carpetas por temporada enlazadas; ficheros de la raíz copiados (crosswalk escribe ahí)
  if [ -d "$f" ]; then ln -s "$f" "$W/data/processed/"; else cp "$f" "$W/data/processed/"; fi
done
fi
cd "$W"
export PYTHONPATH=. MLFLOW_DISABLE_AGENT_HINT=1
# cada paso deja una marca en $W/.pasos/: al relanzar con el mismo $W y un 2.º argumento cualquiera (reanudar),
# los pasos ya hechos se saltan (un paso que falló se repite)
N=0; mkdir -p "$W/.pasos"
paso() { N=$((N+1)); if [ -f "$W/.pasos/$N" ]; then echo "--- (hecho) $*"; return 0; fi
  echo "=== $(date +%H:%M:%S) [$N] $*"; "$@"; touch "$W/.pasos/$N"; }
# 1-2. normalización
for o in crosswalk nacionalidades pista ajustar ajustar-b amortiguar; do paso python3 -m bbmodel $o; done
paso python3 -m bbmodel dataset-normalizado --salida "$W/_art"
paso python3 -m bbmodel contexto
paso python3 -m bbmodel dataset-normalizado --salida "$W/_art"
paso python3 -m bbmodel interacciones
paso python3 -m bbmodel escalas
paso rm -f data/modelos/v3_1/niveles.csv                 # niveles y traducción cruzada con las redes nuevas
paso python3 -m bbnorm3 --config configs/normalization_v31.yaml ajustar-combinada
ln -sfn v3_1 data/modelos/v3_1_20261031             # la configuración del simulador v3.1 lee esta carpeta
mkdir -p data/modelos/v3_1/base_v2 && ln -sfn ../../normalizado data/modelos/v3_1/base_v2/normalizado   # su base v2
# 3. capas de encaje y adaptación. Los roles se rehacen SIN caché: el crosswalk de arriba renumera a las personas y
#    una caché con la numeración anterior las mezclaría (fallo del 30-10-2026); la auditoría lo comprueba
rm -rf data/modelos/roles/_cache
paso python3 -m bbfit roles --rehacer
paso python3 -m bbfit auditar
paso python3 -m bbfit reemplazo
paso python3 -m bbfit entropia
paso python3 -m bbfit estilos --reusar-k
paso python3 -m bbfit adaptacion
mkdir -p data/modelos/adaptacion/v3_1/fase7
cp data/modelos/adaptacion/curvas.csv data/modelos/adaptacion/adaptation_priors.csv data/modelos/adaptacion/v3_1/fase7/
# 4. simulador v3.1
export CERNO_SIMULADOR=v31
paso python3 -m bbfit dataset-simulador             # v3.1 con la Tercera FEB de la v2 (docs/simulador_v31.md §4.1)
paso python3 -m bbfit adaptacion-v3
paso python3 -m bbfit backtest --fuente V31 --escenario inicio --adaptacion
paso python3 -m bbfit pesos-simulador
paso python3 -m bbfit historico
paso python3 -m bbfit exportar-simulador --salida "$W/_sim"
paso python3 -m bbfit auditar --simulador "$W/_sim"      # plantillas reales, con nombre y fichas de todos los ≥ 100 min
# 5. datos del artifact que dependen de lo anterior (atlas/estilos, datos/normalizados, normalización, informe)
paso python3 -m bbestilo exportar --salida "$W/_art/atlas/estilos" --todas-las-ligas
paso python3 -m bbnorm3.artifact --salida "$W/_art/datos"
paso python3 -m bbmodel mesa-normalizacion --salida "$W/_art/datos"
paso python3 -m bbmodel evaluacion-ligas --salida "$W/_art/datos"
paso python3 -m bbstats artifact --salida "$W/_art/datos"            # tablas de datos (<temporada>/regular.json…)
paso python3 -m bbestilo informe --atlas "$W/_art/atlas/estilos" --datos "$W/_art/datos" \
  --normalizado data/modelos/v3_1/normalizado --salida "$W/_art/atlas/informe"
echo "=== $(date +%H:%M:%S) FIN (copia en $W)"
