# v5.1 · F2 · Simulador: producción combinada por liga de destino y ensamblaje

Fecha: 13-11-2026 · Kerno Analytics · encargo v5.1 (`docs/v5_1/00_encargo_v5_1.md`).

**Código**
- `bbnorm5/simulador51/produccion.py`: producción v5, v3.3 y combinada en las 9 métricas, con su examen.
- `bbnorm5/simulador51/ensamblaje.py`: contribución por partido, dependencias y recalibraciones; jugador, equipo y
  grupos de cinco.
- `bbnorm5/validacion/fichajes.py`: `banco_v33(salida=)`, para no sobrescribir el banco versionado.
- `bbnorm5/v51.py`.

**Configuración.** `configs/v5_1/f2.yaml`, con las reglas fijadas antes del examen.

**Salidas.** `data/v5_1/simulador/`.

**Tests.** `tests/v5_1/test_simulador51.py` (2).

```bash
python -m bbnorm5.v51 --config configs/v5_1/f2.yaml --pasos produccion ensamblaje      # ≈ 5 min, con las cachés de la F0
```

Etiquetas: **DATO**, **LECTURA**, **SUPUESTO**, **RIESGO**, **VERIFICAR**.

---

## Informe de auditoría · v5.1 · Fase F2 · Simulador

### Resumen ejecutivo

**El simulador con la v5.1 mejora al vigente en los fichajes reales y queda calibrado en los tres niveles: jugador,
equipo y grupo de cinco.**

- **Producción por liga de destino.** La combinada mejora la producción publicada de la v3.3 un 10,3 %
  [IC 95 % −11,0 %, −9,7 %] en las 9 métricas, con cobertura del 80 % de 0,83. 19.856 casos y 2.282 fichajes de
  2024-25 y 2025-26.
- **Contribución por partido** (minutos del motor × producción).
  - Frente a la contribución publicada de la v3.3: −25,7 % [−27,8 %, −23,6 %], con cobertura de 0,81 frente a 0,78.
  - La producción combinada aporta un 1,7 % [−2,7 %, −0,7 %] con el mismo ensamblaje.
  - El resto viene de ensamblar bien: minutos recalibrados, dependencia estimada (no el z común) y calibración final.
- **Al agregar**, la cobertura queda en rango: equipo 0,83 (la publicada de la v3.3, 0,57); grupos de cinco a la misma
  liga 0,82.
- **El GBM de minutos no se reentrena:** la v5 no aporta información sobre el error de minutos (§2.4).
- **Defecto en el producto publicado:** 86 intervalos de USG% de la v3.3 son del orden de ±10¹⁰. Están en el corte
  2022-23, sobre todo en la Primera FEB, y salen de la recalibración A4. Se excluyen de esta comparación. El examen de la
  F8 no los llegó a usar.

---

## 1. Qué se hizo

### 1.1 Producción por liga de destino (9 métricas del simulador)

- **v3.3:** la producción aplicada publicada (A2 + A4) reconstruida sobre el examen V32_corte reproducido en la F0
  (`banco_v33_reproducido.parquet`).
- **v5:** la proyección publicada (ex ante, recalibrada) en la liga y temporada de destino.
  - Pts/100, USG%, AST%, robos/100 y TOV%: directas.
  - TS%: de sus 5 componentes, con draws conjuntos.
  - OREB, DREB y BLK por 100: porcentaje × oportunidades por posesión de la liga de destino **en la temporada anterior**
    (ex ante).
  - Un factor de definición por métrica, fijado en la calibración, alinea la escala. Sale entre 99,7 y 101,6 sobre 100:
    pts/100 y robos/100 ≈ +1,5 %, porque la v3.3 cuenta las posesiones con otra fórmula.
- **Combinada:** promedio de cuantiles con la regla de pesos de la F1, fijada en 2023-24 y examinada en 2024-25 y
  2025-26.
- **Casos:** fichajes con 300 min o más en destino y el mismo registro en las dos versiones (|real/obs − 1| ≤ 5 %).
- **Exclusión:** casos con intervalos de la v3.3 no finitos o de |valor| ≥ 1.000 (§5.1).

### 1.2 Ensamblaje de la contribución por partido

C = M / gm × P, con:
- **M:** minutos del motor v3.3 (examen reproducido);
- **P:** pts/100 combinados.

Todo lo que sigue se estima **sólo con temporadas anteriores**:
- ρ entre minutos y producción del mismo jugador (cópula gaussiana);
- factor común de compañeros (minutos y producción);
- factor común de liga y temporada en la producción: la innovación de λ de t+1 que la F10 no propagaba;
- **recalibración de los minutos:** su dispersión alrededor de la mediana × s, con s tal que la banda del 80 % cubra el
  80 %. Sale s = 0,75 en los dos cortes;
- **calibración final de C:** su dispersión × s_C por versión, fijada con la temporada anterior. Sale entre 0,83 y 0,90.

Se compara con la contribución publicada de la v3.3 y con una v3.3 ensamblada igual, con sus pts/100. Esta segunda
aísla la producción.

## 2. Resultados (DATO)

### 2.1 Producción (2024-25 y 2025-26; WIS frente a la v3.3 publicada)

| Versión | WIS frente a la v3.3 | IC 95 % | Cobertura 80 % |
|---|---|---|---|
| v3.3 publicada | 0 | — | 0,818 |
| v5 | −8,1 % | [−9,1, −7,0] | 0,789 |
| **Combinada** | **−10,3 %** | **[−11,0, −9,7]** | **0,827** |
| Mezcla al 50 % | −9,4 % | [−10,0, −8,9] | 0,833 |

Por métrica (peso fijado en 2023-24; cobertura del 80 % de la v3.3 y de la combinada):

| Métrica | Peso v5 | v5 | Combinada | Cobertura v3.3 | Cobertura combinada |
|---|---|---|---|---|---|
| BLK/100 | 0,68 | −17,7 % | −19,6 % | 0,81 | 0,82 |
| AST% | 0,72 | −16,5 % | −16,8 % | 0,84 | 0,83 |
| OREB/100 | 0,75 | −14,3 % | −15,8 % | 0,81 | 0,81 |
| DREB/100 | 0,70 | −11,0 % | −12,2 % | 0,82 | 0,82 |
| TS% | 0,50 | −6,6 % | −8,3 % | 0,82 | 0,85 |
| Pts/100 | 0,57 | −3,3 % | −8,1 % | 0,82 | 0,83 |
| Robos/100 | 0,57 | −7,3 % | −7,7 % | 0,80 | 0,81 |
| USG% | 0,57 | −4,0 % | −7,5 % | 0,83 | 0,83 |
| TOV% | 0,57 | −0,5 % | −4,5 % | 0,81 | 0,84 |

**Decisión** (regla de `f2.yaml`): mejora con IC < 0 y cobertura no peor → **se publica**.

Pesos para publicar (todas las temporadas): AST% 0,78 · BLK 0,76 · DREB 0,77 · OREB 0,76 · Pts 0,59 · robos 0,68 ·
TOV% 0,50 · TS% 0,59 · USG% 0,59.

### 2.2 Contribución por partido, jugador (2.465 fichajes, 2.076 personas)

| Modelo de C | Frente a la C publicada de la v3.3 | Frente a la v3.3 ensamblada | Cobertura 80 % |
|---|---|---|---|
| C publicada de la v3.3 | 0 | — | 0,783 |
| v3.3 ensamblada | −24,3 % [−26,5, −22,3] | 0 | 0,824 |
| v5 | −23,6 % [−26,0, −21,4] | +0,9 % [−0,8, +2,6] | 0,797 |
| **Combinada** | **−25,7 % [−27,8, −23,6]** | **−1,7 % [−2,7, −0,7]** | **0,806** |
| Combinada con ρ = 1 (supuesto de la v3.3) | −22,0 % | +3,1 % [+2,0, +4,5] | 0,931 |
| Combinada sin recalibrar los minutos | −19,5 % | +6,4 % | 0,927 |
| Combinada sin la calibración final de C | −24,4 % | −0,0 % | 0,877 |

- **Minutos:** la banda del 80 % del motor cubre el 0,92 en quien acaba jugando ≥ 300 min; recalibrada, 0,83.
- **Dependencias estimadas** (cortes 2024 y 2025):
  - ρ minutos–producción: 0,27 y 0,24;
  - compañeros: minutos 0,21 y 0,15, producción 0,06 y 0,05;
  - liga-temporada: 0,06 y 0,04.

### 2.3 Agregación

| Agregado | Modelo | WIS | Cobertura 50 % | Cobertura 80 % |
|---|---|---|---|---|
| Equipo (suma de sus fichajes; 614 equipos) | C publicada de la v3.3 | 7,40 | 0,29 | **0,57** |
| | v3.3 ensamblada, con dependencias | 4,28 | 0,54 | 0,85 |
| | **Combinada, con dependencias** | **4,34** | 0,50 | **0,83** |
| | Combinada, independientes | 4,33 | 0,45 | 0,77 |
| Cinco a la misma liga (media de pts/100; 473 grupos) | v3.3 ensamblada, factor de liga | 1,083 | 0,55 | 0,85 |
| | **Combinada, factor de liga** | **0,975** | 0,55 | **0,82** |
| | Combinada, independientes | 0,972 | 0,52 | 0,79 |

### 2.4 ¿Reentrenar el GBM de minutos con la v5?

- **Lo que la v5 ve distinto de la v3.3** (centro de pts/100 v5 − v3.3) **frente a lo que falla el motor en minutos**
  (PIT): correlación de rangos 0,035 [−0,002, +0,075].
- **Regresión fuera de tiempo** del error de minutos sobre esa diferencia: R² −0,071 (2024-25) y −0,009 (2025-26).
- **El nivel de producción en sí sí se relaciona** con el error de minutos: 0,12 [0,09, 0,15]. El motor da a los
  mejores menos minutos de los que juegan, pero esa información ya está en la v3.2 que usa el motor.

## 3. Interpretación (LECTURA)

1. **La producción combinada es la mejor de las tres en todas las métricas.** Gana más donde la v5 aporta contexto:
   rebote, tapones y asistencias, del −12 % al −20 %. Gana menos en pérdidas y tiro (−4 % a −8 %).
2. **En la contribución por partido, la producción es la parte pequeña.** Lo grande es cómo se ensambla:
   - minutos recalibrados (de 0,92 a 0,83 de cobertura);
   - dependencia estimada (ρ ≈ 0,25, no 1);
   - una calibración final.

   La C publicada de la v3.3 falla por eso: cobertura 0,78 en el jugador y 0,57 en el equipo.
3. **El factor común de liga hace falta para los grupos de cinco.** Pasan de 0,79 a 0,82 de cobertura. Es el error
   común por liga-temporada que la F10 dejó como pendiente.
4. **En el equipo, la combinada y la v3.3 ensamblada empatan** (WIS 4,34 frente a 4,28). Con 3,7 fichajes por equipo,
   lo que manda son los minutos.
5. **Reentrenar el GBM de minutos con la v5 no ganaría nada.** Mejorar los minutos es otro proyecto, sobre el motor; la
   pista es que infravalora el nivel.

## 4. Supuestos (SUPUESTO)

1. **Minutos del motor tal como salen del examen reproducido** (escenario «inicio»). Recalibrarlos sólo cambia su
   anchura, no su mediana.
2. **Selección por minutos:** fichajes con 300 min o más en destino, como en la F8. Las recalibraciones de anchura se
   estiman en esa misma población, así que sirven para quien llega a jugar.
3. **Oportunidades por posesión de la temporada anterior** para OREB, DREB y BLK por 100: ex ante, sin el ritmo de la
   temporada de destino.
4. **Las dependencias son factores comunes gaussianos** (intraclase), estimados con las temporadas anteriores.

## 5. Riesgos y verificaciones pendientes (RIESGO · VERIFICAR)

1. **RIESGO · defecto en la v3.3 publicada.** 86 intervalos de USG% del orden de ±10¹⁰ en el corte 2022-23 (76 en la
   Primera FEB; también BBL, BNXT y otras). Salen de la recalibración A4. Están en el banco versionado de la v5.0 y en el
   reproducido. Afecta a lo que se publicó para esos jugadores en esa temporada. Propuesta: corregirlo al sustituir la
   producción en la F6.
2. **VERIFICAR · fichajes con menos de 300 min.** Las anchuras recalibradas sirven para quien llega a jugar. Para el
   producto (todos los fichajes), la calibración final de C debe ajustarse con todos, como hace hoy el NK con su
   isotónica.
3. **VERIFICAR · quintetos reales con el plantel completo.** Los grupos de cinco son fichajes a la misma liga. El
   quinteto con el plantel entero necesita la simulación del equipo completo, que llega con la F4 (Impacto).

## 6. Verificación de no regresión

- `fichajes.banco_v33` sin `salida` escribe donde siempre. El banco versionado de la v5.0 no se ha tocado.
- Nada de `bbfit/`, `data/modelos/` ni los artifacts cambia. Las cachés y el examen reproducido viven en
  `experimentos/` (F0).
- Suite completa: **393 passed**.

## 7. Siguiente fase

**F3 · Nivel Kerno:** NK = 100·E[F_ref(C)] con la C de esta fase (combinada, calibrada), frente al NK vigente
reproducido en la F0:
- número frontal predictivo;
- rango de nivel y rango del año;
- sello de fiabilidad.

Esperando GO.
