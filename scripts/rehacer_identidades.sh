#!/bin/bash
# Cadena completa tras la corrección de identidades del 03-11-2026 (docs/identidades_20261103.md):
#   BNXT y GBL reprocesadas con la clave de jugador corregida (bbstats/adapters/fiba_livestats.py) y crosswalk con
#   persona_id estables (bbmodel/crosswalk.py: ids_estables). Rehace, EN EL REPOSITORIO:
#   1. capas v2 (nacionalidades, pista, A, B, amortiguada, dataset, contexto, interacciones) y nombres canónicos,
#   2. capas de encaje (roles, reemplazo, entropía, estilos unificados) y adaptación (fase 7 → adaptacion/v3_2/fase7),
#   3. líneas base de la v2 en los cortes 2021-2024 (para el examen de la v3.2),
#   4. normalización v3.2 (F0, 20 redes, examen B2, ajuste final, vara de destino) SIN repetir la ablación
#      (ablacion.quitadas se conserva: decisión del 02/03-11-2026),
#   5. simulador v3.2 (examen con y sin fuga, variantes, decisiones, B7/B9, histórico, exportación, auditoría),
#   6. simulador v3.3 (minutos GBM y B9: v33-decidir, v33-aplicar, histórico, exportación, auditoría),
#   7. datos del artifact (sin publicar) en experimentos/v33_artifact/.
# La v3.1 (data/modelos/v3_1, simulador/v3_1, adaptacion/v3_1) no se rehace ni se toca.
# Reanudable: cada paso deja una marca en experimentos/.pasos_id/.
#
#   nohup setsid scripts/rehacer_identidades.sh > experimentos/cadena_id.log 2>&1 &
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ"
export PYTHONPATH=. MLFLOW_DISABLE_AGENT_HINT=1
N32=configs/normalization_v32.yaml
ART=experimentos/v33_artifact
M="$RAIZ/experimentos/.pasos_id"; mkdir -p "$M"; N=0
paso() { N=$((N+1)); if [ -f "$M/$N" ]; then echo "--- (hecho) [$N] $*"; return 0; fi
  echo "=== $(date +%H:%M:%S) [$N] $*"; "$@"; touch "$M/$N"; }
# 0. cachés que dependen de los datos (las redes se guardan por huella de configuración, no de datos)
if [ ! -f "$M/cache" ]; then
  for d in v3 cache_normalizacion cache_simulador_v3_2 cache_simulador_v3_3; do
    [ -e "experimentos/$d" ] && mv "experimentos/$d" "experimentos/${d}_antes_id_$(date +%Y%m%d%H%M)"
  done
  rm -rf data/modelos/roles/_cache
  # salidas que sus pasos reutilizan si existen (se saltan lo ya hecho): con datos nuevos hay que borrarlas
  rm -f data/modelos/v3_2/validacion/f0_20*.csv.gz data/modelos/v3_2/validacion/ablacion/pred_final_*.csv.gz \
    data/modelos/v3_2/validacion/ablacion/escala_*.pkl data/modelos/v3_2/niveles.csv \
    data/modelos/v3_2/destino/covarianza_v2/_hecho data/modelos/simulador/v3_2/historico_20*.csv.gz \
    data/modelos/simulador/v3_3/historico_20*.csv.gz
  touch "$M/cache"
fi
# 1. capas v2 y nombres canónicos (el crosswalk ya está rehecho)
paso python3 -m bbmodel nombres
for o in nacionalidades pista ajustar ajustar-b amortiguar; do paso python3 -m bbmodel $o; done
paso python3 -m bbmodel dataset-normalizado --salida "$ART/datos"
paso python3 -m bbmodel contexto
paso python3 -m bbmodel dataset-normalizado --salida "$ART/datos"
paso python3 -m bbmodel interacciones
# 2. capas de encaje y adaptación
paso python3 -m bbfit roles --rehacer
paso python3 -m bbfit auditar
paso python3 -m bbfit reemplazo
paso python3 -m bbfit entropia
paso python3 -m bbfit estilos --reusar-k
paso python3 -m bbfit adaptacion --rehacer
paso bash -c "mkdir -p data/modelos/adaptacion/v3_2/fase7 && cp data/modelos/adaptacion/curvas.csv \
  data/modelos/adaptacion/adaptation_priors.csv data/modelos/adaptacion/v3_2/fase7/"
# 3. líneas base de la v2 en los cortes 2021-2024 (fuera de las carpetas de validación de la v2)
paso python3 -c "
import shutil; from pathlib import Path; from threadpoolctl import threadpool_limits; threadpool_limits(1)
from bbmodel import amortiguacion as AM, modelo
cfg = AM.config(); cfg['validacion'] = {**cfg.get('validacion', {}), 'anios': [2021, 2022, 2023, 2024]}
t = modelo.preparar()[0]; tmp = Path('experimentos/lineas_base_id'); shutil.rmtree(tmp, ignore_errors=True)
AM._validar(t, cfg, tmp, 'sin_mapeo')
d = Path('data/modelos/v3_2/validacion/lineas_base')
for a in [2021, 2022, 2023, 2024]:
    shutil.copy(tmp / 'validacion_variantes' / f'sin_mapeo_{a}.csv.gz', d / f'sin_mapeo_{a}.csv.gz')"
paso python3 -c "
import pandas as pd; from threadpoolctl import threadpool_limits; threadpool_limits(1)
from bbmodel import algoritmo_b as B, modelo, validacion
t = modelo.preparar()[0]
r = [B.ConjuntoB(t, hasta_anio=a, n_redes=3).predecir_cambios(validacion.casos(t, a)) for a in [2021, 2022, 2023, 2024]]
pd.concat(r).round(5).to_csv('data/modelos/v3_2/validacion/lineas_base/b.csv.gz', index=False)"
# 4. normalización v3.2 (configuración final de la ablación)
paso python3 -c "
from bbnorm3 import config as C, flujo; from bbmodel import modelo as A
cfg = C.con(C.cargar(C.RAIZ / '$N32'), **{'validacion.anios': [2021, 2022, 2023, 2024]})
flujo.f0(A.preparar()[0], cfg)"
paso python3 -c "
from bbnorm3 import config as C, ablacion; from bbmodel import modelo as A
cfg = C.cargar(C.RAIZ / '$N32'); t = A.preparar()[0]; f = ablacion.guardar_tabla(t, cfg)
ablacion.entrenar([(cfg, a, s) for a in [None, 2024, 2023, 2022, 2021] for s in cfg['semillas']], cfg, f)"
paso python3 -c "
import shutil; from bbnorm3 import config as C, ablacion, flujo
cfg = C.cargar(C.RAIZ / '$N32'); f = ablacion._tabla_cache(cfg)
n = len(cfg['semillas'])
ablacion.predecir([('final', cfg, a) for a in [2024, 2023, 2022, 2021]], cfg, f, n, salvaguardas_=False, procesos=2)
for a in [2021, 2022, 2023, 2024]:
    shutil.copy(ablacion.ruta_pred(cfg, 'final', a, n), flujo.dir_val(cfg) / f'predicciones_cvae_{a}.csv.gz')"
paso python3 -m bbnorm3 --config $N32 validar-v32
paso python3 -m bbnorm3 --config $N32 ajustar-combinada
# 5. simulador v3.2
export CERNO_SIMULADOR=v32
paso python3 -m bbfit dataset-simulador
paso python3 -m bbnorm3 --config $N32 destino
paso python3 -m bbfit backtest --fuente V32 --escenario inicio --adaptacion
paso python3 -m bbfit backtest --fuente V32_corte --escenario inicio --adaptacion --pesos-de V32_inicio_adapt
for f in V32 V32_corte; do
  for v in sin_redistribuir_uso sin_adaptacion; do
    paso env CERNO_SIM_VARIANTE=$v python3 -m bbfit backtest --fuente $f --escenario inicio --adaptacion \
      --pesos-de V32_inicio_adapt
  done
done
paso python3 -m bbfit v32-decidir
paso python3 -m bbfit b7-b9 --etiqueta V32_corte_inicio_adapt
paso python3 -m bbfit v32-aplicar
paso python3 -m bbfit pesos-simulador
paso python3 -m bbfit historico
paso python3 -m bbfit exportar-simulador --salida experimentos/v32_artifact/simulador
paso python3 -m bbfit auditar --simulador experimentos/v32_artifact/simulador
# 6. simulador v3.3 (decide sobre el examen sin fuga de la v3.2)
paso python3 -m bbfit v33-decidir
paso python3 -m bbfit v33-aplicar
export CERNO_SIMULADOR=v33
paso bash -c "mkdir -p data/modelos/simulador/v3_3 && cp data/modelos/simulador/v3_2/pesos.json data/modelos/simulador/v3_3/"
paso python3 -m bbfit historico
paso python3 -m bbfit exportar-simulador --salida "$ART/simulador"
paso python3 -m bbfit auditar --simulador "$ART/simulador"
# 7. datos del artifact (nombres canónicos; normalización v3.2; simulador v3.3)
unset CERNO_SIMULADOR
paso python3 -m bbestilo exportar --salida "$ART/atlas/estilos" --todas-las-ligas
paso python3 -m bbnorm3.artifact --origen data/modelos/v3_2/normalizado --etiqueta V3.2 --salida "$ART/datos"
paso python3 -m bbmodel mesa-normalizacion --salida "$ART/datos"
paso python3 -m bbmodel evaluacion-ligas --salida "$ART/datos"
paso python3 -m bbstats artifact --salida "$ART/datos"
paso python3 -m bbestilo informe --atlas "$ART/atlas/estilos" --datos "$ART/datos" \
  --normalizado data/modelos/v3_2/normalizado --salida "$ART/atlas/informe"
paso python3 -m bbmodel escalas --salida "$ART"
echo "=== $(date +%H:%M:%S) FIN identidades"
