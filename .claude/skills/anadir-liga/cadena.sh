#!/bin/bash
# Skill «anadir-liga», Fase 4: reajuste global de todos los modelos con una liga nueva ya descargada (Fases 1-3 hechas).
#   1. crosswalk (personas de la liga nueva; los persona_id existentes se conservan)
#   2. scripts/rehacer_identidades.sh desde cero: capas v2, encaje, normalización v3.2 (redes CVAE reentrenadas),
#      simulador v3.2 + v3.3, datos del artifact y lotes en experimentos/v33_artifact/_publicacion
#   3. modelo de equipo v4.0 (productos, con las decisiones prerregistradas vigentes) y su exportación
#   4. congelados del botón (modelos_hasta_* del simulador v3.3)
# Reanudable: cada paso deja una marca en experimentos/.pasos_liga/ (y la cadena del punto 2, las suyas en
# experimentos/.pasos_id/). Si un paso falla, se corrige y se relanza el mismo comando.
#
#   setsid nohup .claude/skills/anadir-liga/cadena.sh > experimentos/cadena_liga.log 2>&1 < /dev/null & disown
#
# Para empezar una liga nueva desde cero (otra ampliación): rm -rf experimentos/.pasos_liga
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$RAIZ"
export PYTHONPATH=. MLFLOW_DISABLE_AGENT_HINT=1 OMP_NUM_THREADS=${OMP_NUM_THREADS:-4}
M="$RAIZ/experimentos/.pasos_liga"; mkdir -p "$M"; N=0
paso() { N=$((N+1)); if [ -f "$M/$N" ]; then echo "--- (hecho) [$N] $*"; return 0; fi
  echo "=== $(date +%H:%M:%S) [$N] $*"; "$@"; touch "$M/$N"; }

# 1. identidades con la liga nueva
paso python3 -m bbmodel crosswalk
# 2. cadena completa vigente. Sus marcas se borran UNA vez (este paso queda hecho): así aparta las cachés que dependen
#    de los datos (redes CVAE incluidas) y lo rehace todo; si después falla a medias, se reanuda desde sus propias marcas
paso rm -rf experimentos/.pasos_id
paso scripts/rehacer_identidades.sh
# 3. modelo de equipo v4.0 (F0 → F5), productos con todas las temporadas
paso python3 -m bbequipo contrato
paso python3 -m bbequipo perfiles
for o in rapm-producto sinergia-producto dirigidos-producto conjunto-producto a5-producto equipo-producto anclas-producto; do
  paso python3 -m bbequipo $o
done
paso python3 -m bbequipo exportar-atlas --salida data/artifact/atlas_v40
paso python3 -c "from bbactualiza.recalibrar import equipos_v40; print(equipos_v40())"
# 4. congelados del botón: las piezas del simulador v3.3 ajustadas con temporadas ≤ 2024-25 y ≤ 2025-26
paso bash -c "mkdir -p data/modelos/simulador/v3_3/congelado && \
  cp experimentos/cache_simulador_v3_3/modelos_hasta_2024-25.pkl experimentos/cache_simulador_v3_3/modelos_hasta_2025-26.pkl \
     data/modelos/simulador/v3_3/congelado/"
echo "=== $(date +%H:%M:%S) FIN cadena de la liga nueva"
