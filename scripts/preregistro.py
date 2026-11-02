"""§15 (criterios del 02-11-2026) · prerregistro del examen limpio 2025-26 → 2026-27.

Fija, ANTES de ver los datos del examen, el commit y la huella SHA-256 de las configuraciones de la normalización y del
simulador v3.2, las poblaciones, las métricas, los criterios de aceptación y la fecha de corte de los datos. Cualquier
cambio posterior abre una v3.3, que espera al siguiente corte limpio.

    python scripts/preregistro.py   →  docs/preregistro_2026-27.md
"""
from __future__ import annotations

import hashlib
import subprocess
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FICHEROS = ["configs/normalization_v32.yaml", "configs/simulation_v32.yaml", "configs/normalization.yaml",
            "configs/roles.yaml", "configs/reemplazo.yaml", "configs/adaptacion.yaml"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> Path:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=RAIZ, capture_output=True, text=True).stdout.strip()
    filas = "\n".join(f"| `{f}` | `{sha(RAIZ / f)}` |" for f in FICHEROS if (RAIZ / f).exists())
    texto = f"""# Prerregistro del examen limpio 2025-26 → 2026-27 (v3.2)

Fecha del registro: {date.today().isoformat()} · commit `{commit}` · datos hasta el 29-10-2026.

**Regla.** Este examen se evalúa con las configuraciones de abajo, tal como están en este commit. Si después de ver el
examen se cambia cualquier parámetro, el cambio abre una v3.3, que espera al siguiente corte limpio. Las huellas
permiten comprobar que no ha habido cambios.

## Configuraciones (SHA-256)

| Fichero | SHA-256 |
|---|---|
{filas}

## Normalización v3.2

- **Casos.** Personas con ≥ 300 minutos en 2025-26 y en 2026-27, en ligas distintas (`bbmodel.validacion.casos`).
  Ajuste con temporadas ≤ 2025-26.
- **Métricas.** Las 33 del catálogo. Se mide el error medio relativo a la v2 (`<m>_am`) con IC 95 % por persona.
- **Criterios de aceptación** (la puerta de la v3.1):
  - IC95,sup del error relativo < 0;
  - cobertura del 80 % recalibrada en [0,78, 0,85] en cada par origen → destino con ≥ 30 personas;
  - no peor frente a la v2 con destino EuroLeague.

## Simulador v3.2

- **Fichajes.** Cambios de club de 2025-26 a 2026-27. Normalización ajustada con ≤ 2025-26 (fuente sin fuga).
- **Poblaciones.**
  - P_all: ≥ 5 partidos en destino.
  - P_300: ≥ 300 minutos.
  - P_50-300: entre 50 y 300 minutos.
- **Métricas.**
  - Error medio de minutos y de las 9 métricas de producción.
  - Acierto y log-loss del rol.
  - Contribución C (P_all).
  - Coberturas del 50, 80 y 90 %.
  - Winkler.
  - §7: Spearman por liga de destino, decil superior, Brier y fiabilidad de P(C ≥ p75).
- **Criterio de aceptación** (A4, §5e): |Cob − α| ≤ 2√(α(1−α)/n) + 0,02 por métrica y grupo de destino con
  n ≥ 100.
- **Informe.** Siempre por grupo de destino y por corte; la media global no se publica sola.

## Fecha de cierre

El examen se ejecuta cuando la temporada 2026-27 esté cerrada en todas las ligas. Antes de abrirlo se comprueban
estas huellas.
"""
    out = RAIZ / "docs" / "preregistro_2026-27.md"
    out.write_text(texto, encoding="utf-8")
    print(out)
    return out


if __name__ == "__main__":
    main()
