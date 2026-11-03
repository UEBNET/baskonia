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

## 5. Resultados

Se completan al terminar la cadena (`scripts/rehacer_identidades.sh`, con los datos de identidades corregidos).
