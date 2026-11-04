# Simulador de encaje v3.3

El simulador v3.2 con dos piezas nuevas, aprobadas el 03-11-2026:

- **M · minutos del fichaje con gradient boosting.**
- **B9 · minutos y producción en un solo modelo** (acoplamiento Monte Carlo).

Las dos se deciden con el mismo examen sin fuga de la v3.2. Las reglas de decisión se fijaron antes de ver ese
examen.

| | |
|---|---|
| Configuración | `configs/simulation_v33.yaml` (`CERNO_SIMULADOR=v33`) |
| Código | `bbfit/v33.py` y `bbfit/simulador.py` (`_minutos_v33`, `_b9_rol_asignado`) |
| Resultados | `data/modelos/simulador/v3_3/` |
| La v3.2 | No cambia |

## 1. Punto de partida

**§16 de los criterios.** Un gradient boosting supervisado predice los minutos de los fichajes mejor que la utilidad
de Plackett-Luce del motor: error de 4,67 frente a 4,86. El motor no gana con claridad.

**B9.** El error de minutos y el de producción del motor están correlacionados (0,35). Si se conocieran los minutos
y el rol reales, el error de pts/100 bajaría un 7,7 % (oráculo). La regla de apertura de B9 se cumplió y el usuario
aprobó abrirlo.

**Decisiones del usuario:**
- B9 como **acoplamiento en el Monte Carlo**.
- Minutos: **que elija el examen** entre el motor, el GBM y la mezcla de ambos.

## 2. Reglas (fijadas antes del examen)

El examen es el mismo de la v3.2:
- Fuente sin fuga `V32_corte`.
- Fichajes de 2021-22 → 2024-25 con cortes anidados.
- En cada corte se aplican las decisiones de la v3.2 tomadas con los cortes anteriores.

### M · minutos

**Candidatos.**
- **Motor:** minutos calibrados de la v3.2.
- **GBM:** `HistGradientBoosting` con pérdida absoluta. Usa las mismas variables que B7/§16:
  - registro de origen;
  - salto de nivel;
  - traducción media de las 9 métricas;
  - ligas de origen y destino;
  - posición;
  - rol de origen.
- **Mezcla:** la media del motor y del GBM.

**Entrenamiento.** El GBM de cada corte se entrena solo con los cortes anteriores. El primer corte no tiene
predicción del GBM.

**Decisión en el corte t.** Se usan los cortes anteriores que tienen predicción del GBM fuera de muestra.
- Un candidato mejora al motor si IC90,inf[MAE_motor − MAE_cand] > 0, con bootstrap por club de destino × corte.
- Entre los que mejoran se elige el de menor error. Si ninguno mejora, se queda el motor.

**Intervalos y rol.**
- Los intervalos del motor se desplazan con el centro elegido, se recortan a [0, minutos del partido] y se
  recalibran (A4, dos colas, recencia ρ = 0,5) con los cortes anteriores.
- El rol lo sigue dando el motor, así que el acierto de rol no cambia.
- Con producción del Atlas, la contribución C se recalcula con los minutos nuevos.

### B9 · acoplamiento minutos-producción

En cada simulación:

> Δy_m = b_m · Δmin + c_m · Δrol

- **Δmin** = minutos de esa simulación − minutos esperados (min/partido).
- **Δrol** = índice del rol de esa simulación − índice esperado. El índice va de 0 (RESIDUAL) a 4 (GO_TO_GUY).
- **b_m y c_m:** mínimos cuadrados sin término independiente sobre los residuos de la producción publicada, con los
  cortes anteriores.

**Sin rol asignado.** El centro no cambia: la media de Δmin y de Δrol es 0. La producción publicada sigue siendo la
del Atlas (A2), un valor puntual con intervalos de A4.

**Con rol asignado por el club.** La producción se desplaza a lo que ese rol implica:
- Δmin = minutos de la franja del rol − minutos esperados sin rol (v3.3).
- Δrol = índice del rol − índice esperado sin rol.

**Escenario del examen «rol asignado».**
- El club fija el rol real del fichaje.
- Minutos = mediana de los minutos reales de ese rol en la liga de destino, de los cortes anteriores. Si hay menos
  de 10 casos, se usa la del rol.

**Regla de adopción.** B9 se adopta si se cumplen las dos condiciones:
- mejora el error de pts/100 de forma significativa: IC90,sup del cociente < 0;
- no empeora el de TS% más de +0,5 % (IC90,sup).

**Oráculo (solo informativo).** El mismo ajuste con los minutos reales.

## 3. Rol asignado en la configuración

`configs/simulation_v31.yaml` y `simulation_v32.yaml` no tenían el bloque `rol_asignado` de la v2.1. Por eso el
motor Python de esas versiones no admitía rol asignado, y la exportación publicaba `meta.rol_asignado = null`. La
v3.3 lo incluye con los mismos valores que `simulation.yaml`.

## 4. Para el artifact

`exportar-simulador` (v3.3) añade dos cosas.

**`meta.v33`:**
- minutos publicados (motor, gbm o mezcla);
- B9 activo o no;
- coeficientes b_m y c_m;
- factores de recalibración de minutos;
- franjas de minutos por rol;
- la regla de uso.

**`jugadores.json`:** una columna `min_gbm` con los minutos del GBM de cada registro en cada liga de destino
(`meta.v33.ligas_min_gbm`). El navegador no necesita evaluar los árboles.

**Motor del navegador** (`artifact/atlas/simulador.js`, sustituye a `simulador_v2.js`): mismos pasos que
`bbfit.simulador` con `CERNO_SIMULADOR=v33` (mezcla de minutos, recalibración, B9 con rol asignado, producción del
Atlas con A4). Paridad en 12 casos con rol libre, ROTACION y TITULAR: todos dentro de tolerancia
(`tests/js/paridad_simulador.js`). Estado de la publicación: `docs/checkpoints/ARTIFACT-v3.3.md`.

## 5. Resultados

Examen sin fuga de la v3.2 rehecho con las identidades corregidas (`scripts/rehacer_identidades.sh`, 04-11-2026).
Datos en `data/modelos/simulador/v3_3/decisiones_v33.json`.

### 5.1 M · minutos

**Decisión por corte** (con los cortes anteriores que tienen GBM fuera de muestra):

| Corte | Decisión | Error de minutos con los cortes anteriores (motor / GBM / mezcla) |
|---|---|---|
| 2021-22 y 2022-23 | Motor | Sin cortes anteriores con GBM fuera de muestra |
| 2023-24 | **Mezcla** | 4,99 / 4,82 / 4,76 |
| 2024-25 | **Mezcla** | 4,92 / 4,74 / 4,65 |

**Decisión final** (cortes 2022-23 a 2024-25, 4.956 fichajes): **mezcla 50/50 del motor y el GBM**.
- Error de minutos: motor 4,86; GBM 4,67; mezcla 4,59.
- Motor − mezcla = +0,27 [IC 90 % +0,23, +0,31]. Motor − GBM = +0,19 [+0,11, +0,27].
- Entre los dos que mejoran al motor, la mezcla es la de menor error.

**Examen anidado** (cada corte con su decisión):

| Medida | v3.2 | v3.3 |
|---|---|---|
| Error medio de minutos | 4,87 | **4,70** |
| v3.3 − v3.2 en minutos [IC 90 %] | | −0,17 [−0,20, −0,14] |
| Acierto de rol | 42,7 % | 42,7 % |
| Cobertura 50 / 80 / 90 % de minutos | 0,57 / 0,83 / 0,93 | 0,57 / 0,83 / 0,93 |
| Error medio de la contribución C | 4,50 | **4,45** |
| Cobertura del 80 % de C | 0,78 | 0,79 |

**Lectura.**
- El GBM aporta información que el motor no tiene, y la media de los dos es mejor que cada uno por separado.
- Los intervalos de minutos siguen algo anchos en el nivel del 50 % (cobertura 0,57), igual que en la v3.2.
- La producción sin rol asignado no cambia, así que el error de pts/100 y de TS% es el de la v3.2.

### 5.2 B9 · rol asignado

Cortes 2022-23 a 2024-25 (coeficientes con los cortes anteriores). Error medio absoluto en el escenario en que el
club fija el rol real:

| Métrica | v3.2 | v3.3 (B9) | Oráculo (minutos reales) | Cambio [IC 90 %] |
|---|---|---|---|---|
| pts/100 | 3,83 | **3,65** | 3,65 | **−4,6 %** [−5,7, −3,7] |
| TS% | 4,93 | **4,82** | 4,82 | **−2,2 %** [−3,1, −1,5] |
| USG% | 2,86 | **2,77** | 2,77 | −3,1 % [−3,9, −2,4] |
| AST% | 4,13 | 4,11 | 4,09 | −0,6 % [−1,2, −0,02] |
| Rebotes of. /100 | 0,75 | 0,74 | 0,74 | −0,9 % [−1,4, −0,4] |
| Tapones /100 | 0,354 | 0,351 | 0,352 | −0,7 % [−1,2, −0,2] |
| Pérdidas % | 2,77 | 2,76 | 2,76 | −0,4 % [−0,8, −0,1] |
| Rebotes def. y robos | | | | sin cambio significativo |

**Regla.** Se cumplen las dos condiciones (pts/100 mejora de forma significativa y TS% no empeora): **B9 se
adopta**.

**Coeficientes finales** (todos los cortes): por cada minuto más de lo esperado y por cada escalón de rol más alto,
- pts/100: +0,09 y +0,95;
- TS%: +0,07 y +0,64;
- USG%: +0,06 y +0,55.

**Lectura.**
- Casi toda la mejora viene del rol (Δrol), no de los minutos.
- La v3.3 en el escenario de rol asignado está prácticamente en la cota del oráculo con los minutos reales: el rol
  real ya resume casi toda la información de los minutos.

### 5.3 Simulador publicado

`configs/simulation_v33.yaml`:
- `minutos_publicados: mezcla` y `b9: true`;
- los pasos y la producción de la v3.2 publicada: sin uso-eficiencia ni compañeros, producción del Atlas,
  recalibración A4.

La auditoría de identidades de la exportación v3.3 (`bbfit auditar`) pasa sin fallos. Hay 2 personas con nombres
distintos, y las dos son la misma persona (§1 de `docs/identidades_20261103.md`).
