# Prerregistro del examen limpio 2025-26 → 2026-27 (v3.2)

Fecha del registro: 2026-11-04 · commit `4f3c50b5fcc26554d4dacc2252b78bce79bd91a4` · datos hasta el 29-10-2026.

**Regla.** Este examen se evalúa con las configuraciones de abajo, tal como están en este commit. Si después de ver el
examen se cambia cualquier parámetro, el cambio abre una v3.3, que espera al siguiente corte limpio. Las huellas
permiten comprobar que no ha habido cambios.

## Configuraciones (SHA-256)

| Fichero | SHA-256 |
|---|---|
| `configs/normalization_v32.yaml` | `00d7e2143e85dd3c8a08206d6f9300b03f113fa7d7a0bfc7d9af41f2dfc80b52` |
| `configs/simulation_v32.yaml` | `8426a3cb9280f965cbd31f639a5a7c7cd3104d7668bbe63d18e1b08f16ceaa96` |
| `configs/simulation_v33.yaml` | `5569da6a0bd104834dfee4848acfe180a9ceb807220fa2999974a824a79221a7` |
| `configs/normalization.yaml` | `1990de07c422a269b3779cc5401006d3ac74e944fd29dedc4f165b5e2951351c` |
| `configs/roles.yaml` | `1cddfbd9d97638f3a1aa48680f91a29c2b44219550f113aa9f52f954b329e9af` |
| `configs/reemplazo.yaml` | `155e99c345e1bb816e85604dcb94f3e64c689ee600b7387af579c5aab5e1bfa0` |
| `configs/adaptacion.yaml` | `13ceeb1f59923d4ab578a1c666e5fd0bf40d2d533a4fd20e0d2bb3bf3174cb33` |

## Normalización v3.2

- **Casos.** Personas con ≥ 300 minutos en 2025-26 y en 2026-27, en ligas distintas (`bbmodel.validacion.casos`).
  Ajuste con temporadas ≤ 2025-26.
- **Métricas.** Las 33 del catálogo. Se mide el error medio relativo a la v2 (`<m>_am`) con IC 95 % por persona.
- **Criterios de aceptación** (la puerta de la v3.1):
  - IC95,sup del error relativo < 0;
  - cobertura del 80 % recalibrada en [0,78, 0,85] en cada par origen → destino con ≥ 30 personas;
  - no peor frente a la v2 con destino EuroLeague.

## Simulador v3.3 (y v3.2)

El examen limpio se hace con el simulador v3.3 publicado (minutos de la mezcla motor + GBM y B9) y, como referencia,
con la v3.2. B9 se evalúa además en el escenario de rol asignado (rol real en destino).

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
