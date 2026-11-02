#!/bin/bash
# Normalización v3.2 + simulador v3.2 (docs/normalizacion_v32.md, docs/simulador_v32.md). Parte de los datos y de las
# capas v2 del 29-10-2026 (las de la v3.1 con 20 ligas: data/modelos/normalizacion_amortiguada, algoritmo_A, B…) y
# NO toca la v3.1 (data/modelos/v3_1, data/modelos/simulador/v3_1). Reanudable: cada paso deja una marca en
# experimentos/.pasos_v32/ y casi todos guardan caché (redes en experimentos/v3/, examen en experimentos/cache_*).
#
#   scripts/actualizar_v32.sh [desde_paso]
#
# Paso 0 (aparte, en una copia aislada para no sobrescribir los ficheros versionados de la v2): líneas base de la v2
# rehechas con las 20 ligas en los cortes 2021-2024 (`bbmodel amortiguar --validar --variante sin_mapeo` con
# validacion.anios = [2021, 2022, 2023, 2024] y `bbmodel validar-b --anios 2021 2022 2023 2024`), copiadas a
# data/modelos/v3_2/validacion/lineas_base/ (sin_mapeo_<año>.csv.gz y b.csv.gz) y su caché del A por corte a
# experimentos/cache_normalizacion/ (la usa F0).
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ"
export PYTHONPATH=. MLFLOW_DISABLE_AGENT_HINT=1
N32=configs/normalization_v32.yaml
M="$RAIZ/experimentos/.pasos_v32"; mkdir -p "$M"; N=0
paso() { N=$((N+1)); if [ -f "$M/$N" ]; then echo "--- (hecho) [$N] $*"; return 0; fi
  echo "=== $(date +%H:%M:%S) [$N] $*"; "$@"; touch "$M/$N"; }
# 1. F0 (v2 con la covarianza completa) en los cuatro cortes
paso python3 -c "
from bbnorm3 import config as C, flujo; from bbmodel import modelo as A
cfg = C.con(C.cargar(C.RAIZ / '$N32'), **{'validacion.anios': [2021, 2022, 2023, 2024]})
flujo.f0(A.preparar()[0], cfg)"
# 2. B1 + B4 + B6: ablación con 5 redes por variante y cortes anidados → validacion/ablacion/decisiones.json
paso python3 -m bbnorm3 --config $N32 ablacion
# (la configuración final se fija en $N32 con las piezas que la regla quita: ver docs/normalizacion_v32.md §3)
# 3. B5: 20 redes de la configuración final en los cortes 2021-2024 y con todos los datos
paso python3 -c "
from bbnorm3 import config as C, ablacion; from bbmodel import modelo as A
cfg = C.cargar(C.RAIZ / '$N32'); t = A.preparar()[0]; f = ablacion.guardar_tabla(t, cfg)
ablacion.entrenar([(cfg, a, s) for a in [None, 2024, 2023, 2022, 2021] for s in cfg['semillas']], cfg, f)"
# 4. B2: examen anidado de la combinación con pesos por métrica → validacion/examen_v32.json
paso python3 -m bbnorm3 --config $N32 validar-v32
# 5. ajuste final: niveles, traducción cruzada y dataset normalizado v3.2 (data/modelos/v3_2/normalizado)
paso python3 -m bbnorm3 --config $N32 ajustar-combinada
paso python3 -m bbnorm3.artifact --origen data/modelos/v3_2/normalizado --etiqueta V3.2 --salida experimentos/v32_artifact/datos
# 6. simulador v3.2
export CERNO_SIMULADOR=v32
paso python3 -m bbfit dataset-simulador
paso python3 -m bbnorm3 --config $N32 destino                 # vara de destino (cualquier liga a 0)
paso python3 -m bbfit backtest --fuente V32 --escenario inicio --adaptacion
for v in sin_redistribuir_uso sin_adaptacion; do
  paso env CERNO_SIM_VARIANTE=$v python3 -m bbfit backtest --fuente V32 --escenario inicio --adaptacion \
    --pesos-de V32_inicio_adapt
done
paso python3 -m bbfit v32-decidir
paso python3 -m bbfit b7-b9
# (se fijan en configs/simulation_v32.yaml pasos, factor_ajustes_ts, produccion_publicada y aplicar_recalibracion)
paso python3 -m bbfit pesos-simulador
paso python3 -m bbfit historico
paso python3 -m bbfit exportar-simulador --salida experimentos/v32_artifact/simulador
paso python3 -m bbfit auditar --simulador experimentos/v32_artifact/simulador
echo "=== $(date +%H:%M:%S) FIN v3.2"
