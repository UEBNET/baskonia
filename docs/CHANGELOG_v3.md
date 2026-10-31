# CHANGELOG v3 — normalización cruzada con CVAE jerárquica

Regla suprema: **versionar, nunca sustituir**. La v1/v2 queda en `main` (y debía quedar congelada en la etiqueta
`v2-snapshot-20261029`; ver «Pendiente»). Todo lo de la v3 va en rutas nuevas.

## v3.0 (29-10-2026) — rama `claude/optimistic-pasteur-mlxi78` (sobre `datos/2026-27-actualizacion-20261029`)

### Nuevo
* `bbnorm3/`: paquete de la v3 (CLI `python -m bbnorm3 {elegir-k, f0, validar, lolo, ajustar}`).
  * `datos.py`: capa de medida reutilizada (identidades, pos3, transformaciones y ruido σ²/n del proyecto), sin fuga.
  * `modelo.py`: CVAE jerárquica (latente común u, niveles μ_c con jerarquía y gauge en la media, escala por liga,
    codificador amortizado con producto de expertos, decodificador con FiLM y cabezal residual por liga, efecto
    equipo-temporada y factor específico persona × métrica, IPW de los puentes, consistencia de ciclo).
  * `niveles.py`: posterior gaussiana exacta y conjunta de niveles y latentes (covarianza completa).
  * `prediccion.py`, `traduccion.py`: traducción con la posterior completa; niveles por métrica; matriz cruzada
    T_m(a → b) con Var = Σ_aa + Σ_bb − 2Σ_ab; residuo de ciclo.
  * `examen.py`, `f0.py`, `flujo.py`: examen sin fuga, líneas base (mismo percentil, `<m>_am`, F0), recalibración
    conforme, bootstrap por persona y puerta de control.
  * `exportar.py`, `salidas.py`: salidas en `data/modelos/v3/`.
* `configs/normalization_v3.yaml` (todo hiperparámetro y semilla), `configs/version.yaml` (`version_activa: v1`).
* `tests/test_bbnorm3.py`: gauge, invariancia, varianza de pares, ciclo, esquema y determinismo.
* `docs/normalizacion_v3_cvae.md`.
* `requirements-v3.txt`: `torch==2.5.1` (CPU). En un fichero aparte para que el workflow de extracción (que instala
  `requirements.txt`) no descargue PyTorch.

### Resultado de la puerta de control: NO SE CUMPLE (29-10-2026)
* Examen 2023 → 24 y 2024 → 25: v3 +12,6 % de MAE frente a `<m>_am` (IC 95 % +8,2 % a +16,9 %). Por corte: 2023
  +29,6 % (fallo de la Tercera FEB: escala latente degenerada, s = 15,6) y 2024 −5,0 % (IC −6,5 % a −3,4 %).
* Por tanto, **no** se ejecutan las fases 4 (aguas abajo) y 5 (datos del artifact), ni el ajuste final, ni dejar
  fuera una liga. `configs/version.yaml` sigue en `v1`. Detalle en `docs/normalizacion_v3_cvae.md` §5-6.
* Añadida la opción de diagnóstico `prior.escala_por_liga` (por defecto `true` = v3.0 tal como se examinó).
* `config/ESTILOS_VADE_OBSOLETOS.md`: deja constancia de que E01–E06 quedan desestimados en la v3 (sin tocar
  `config/estilos.json`).

## v3.1 (30-10-2026) — combinación v2 + CVAE corregida

* `configs/normalization_v31.yaml` y `bbnorm3/combinacion.py`. CLI:
  `python -m bbnorm3 --config configs/normalization_v31.yaml {validar-combinada, ajustar-combinada}`.
* CVAE con escala por liga fija (s_l = 1); mezcla caso a caso con `<m>_am` (w = 0,5 fijado de antemano); salvaguardas
  (liga con < 2 temporadas o redes que discrepan → sólo v2); parte v2 con la anchura de F0 (covarianza completa).
* Ajuste por conocimiento de la Tercera FEB (sobreajuste asumido por el CEO): w = 1,0 y anchura × 1,12.
* Examen orientativo (cortes ya vistos): −3,3 % de MAE frente a `<m>_am` (IC −4,1 % a −2,5 %); con la regla fija,
  −3,0 % (IC −3,5 % a −2,4 %). La puerta falla sólo por la cobertura del par Segunda → Tercera FEB (0,759 < 0,78).
* Salidas en `data/modelos/v3_1/`. El selector de versión sigue en `v1`. Detalle en
  `docs/normalizacion_v31_combinada.md`.
* Cachés de redes: la huella ya no incluye `version`, `salida` ni `combinacion` (no cambian el entrenamiento).

## Simulador v3 (30-10-2026) — normalización v3.1, ADAPT% ascendente y FEB visibles

* `configs/simulation_v3.yaml` (se activa con `CERNO_SIMULADOR=v3`): capacidad θ desde el dataset v3.1 (fuente
  `V31`), partidos reales por temporada en destino, contracción 1. Salidas en `data/modelos/simulador/v3/`.
* `bbfit/adaptacion_v3.py` (`python -m bbfit adaptacion-v3`): ADAPT%(g) = 100·(1 + D·e^(−g/κ)) con D ≤ 0, desde la
  curva bruta de los traspasos. Empieza por debajo de 100 (global 95,6 % en el partido 1) y sube hasta 100 (90 % del
  hueco cerrado en 3,8 partidos). Salidas en `data/modelos/adaptacion/v3/`. El motor del artifact no cambia.
* `bbestilo exportar --todas-las-ligas`: el Atlas de estilos exporta las 15 ligas (las FEB proyectadas con las
  escalas de las 12 de la red VaDE), así que las FEB aparecen en «Tu club» y en el buscador del simulador.
* `bbnorm3/artifact.py`: «Datos Normalizados» y el explorador de normalización con la v3.1.
* Pesos de utilidad, calibración y Fit: los de la v2 (no reentrenados). Detalle y límites en `docs/simulador_v3.md`.

## Simulador v3.1 (30-10-2026) — todo rehecho con los datos al 29-10

* `scripts/actualizar_v31.sh`: copia aislada del repositorio en la que se rehace, con los datos al 29-10, toda la
  cadena (normalización v2 y v3.1, roles, reemplazo, entropía, estilos unificados, fase 7, adaptación v3, examen,
  pesos, histórico y exportación). La v1/v2 del repositorio no se toca.
* Salidas versionadas: `data/modelos/v3_1_20261029/` (con `base_v2/`), `adaptacion/v3_1/`, `simulador/v3_1/`.
  Se usan con `configs/simulation_v31.yaml` (`CERNO_SIMULADOR=v31`).
* Constantes de traducción de la v3.1 (`sim_insumos.traduccion_v31`).
* Adaptación sin doble conteo en la producción.
* Ids de la fuente en la v3.1: la BBL llevaba ids de modelo.
* Tercera FEB con la v2 en el simulador (post hoc).
* Pesos reentrenados con el examen completo: minutos y rol igual o algo mejor que la v2; pts/100 empate; USG, AST,
  rebote y TOV mejor; TS% y cobertura del 90 % algo peor. Detalle en `docs/simulador_v31.md`.

### Sin cambios
* El código de `bbstats/`, `bbmodel/` y `artifact/` (página y motor JS). En `bbfit/` y `bbestilo/` sólo se añaden
  opciones nuevas; por defecto se comportan como la v2.
* Las salidas de la v1/v2 en `data/modelos/`: las nuevas van en carpetas propias (`v3_1/`, `adaptacion/v3/`,
  `simulador/v3/`). La exportación del Atlas con las 15 ligas se hace en una carpeta aparte.

### Pendiente (requiere aprobación del CEO)
* Etiqueta `v2-snapshot-20261029`: esta sesión no tenía permiso para subir etiquetas (HTTP 403). Comando para
  crearla: `git tag -a v2-snapshot-20261029 150e814 -m "…" && git push origin v2-snapshot-20261029`.
* Activar la v3 (`configs/version.yaml → version_activa: v3`) y la regeneración aguas abajo (fase 4), sólo si la v3 pasa
  la puerta de control.
