#!/bin/bash
# CERNO v4.0 · F0 (docs/checkpoints/V40_F0.md): redes CVAE de la v3.2 (si faltan en experimentos/v3), perfiles
# ampliados del ajuste completo (producto), contrato de datos y perfiles por corte ≤ t (exámenes sin fuga).
# Reanudable: cada paso deja una marca en experimentos/.pasos_v40_f0/; las redes y las normalizaciones ≤ t se cachean.
#
#   scripts/perfiles_v40.sh [desde_paso]
#
# No toca nada de la v3.2/v3.3: sólo escribe en data/modelos/v4_0/ y en experimentos/.
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ"
export PYTHONPATH=. MLFLOW_DISABLE_AGENT_HINT=1 OMP_NUM_THREADS=${OMP_NUM_THREADS:-4}
N32=configs/normalization_v32.yaml
M="$RAIZ/experimentos/.pasos_v40_f0"; mkdir -p "$M"; N=0
paso() { N=$((N+1)); if [ -f "$M/$N" ]; then echo "--- (hecho) [$N] $*"; return 0; fi
  echo "=== $(date +%H:%M:%S) [$N] $*"; "$@"; touch "$M/$N"; }
# 1. redes de la configuración final de la v3.2 (ajuste completo + cortes 2024…2021, 20 semillas), 4 procesos × 1 hilo.
#    Mismo paso 3 de scripts/actualizar_v32.sh: si la caché experimentos/v3 existe, no entrena nada.
paso python3 -c "
from bbnorm3 import config as C, ablacion; from bbmodel import modelo as A
cfg = C.cargar(C.RAIZ / '$N32')
f = ablacion._tabla_cache(cfg)
t = None if f.exists() else A.preparar()[0]
f = ablacion.guardar_tabla(t, cfg)
ablacion.entrenar([(cfg, a, s) for a in [None, 2024, 2023, 2022, 2021] for s in cfg['semillas']], cfg, f)"
# 2. contrato de datos (inventario de tramos, cobertura, decisión por liga-temporada)
paso python3 -m bbequipo contrato
# 3. perfiles del ajuste completo (producto): data/modelos/v4_0/perfiles/<t>.csv.gz
paso python3 -m bbequipo perfiles
# 4. perfiles por corte ≤ t (exámenes): data/modelos/v4_0/perfiles/corte_<t>/<temporada>.csv.gz
#    (θ ≤ t con la fuente V32_corte del simulador: CERNO_SIMULADOR=v32 para sus cachés; A ≤ t se ajusta si falta)
for a in 2021 2022 2023 2024; do
  paso env CERNO_SIMULADOR=v32 python3 -m bbequipo perfiles --solo-cortes $a
done
echo "=== $(date +%H:%M:%S) FIN F0 v4.0"
