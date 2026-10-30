# Simulador de encaje v3.1: todo rehecho con los datos al 29-10-2026

**Configuración:** `configs/simulation_v31.yaml` (`CERNO_SIMULADOR=v31`). **Guion completo:** `scripts/actualizar_v31.sh`.
**Salidas versionadas:**
* `data/modelos/v3_1_20261029/`: normalización v3.1 rehecha, más su base v2 en `base_v2/normalizado`.
* `data/modelos/adaptacion/v3_1/`: adaptación v3, más la fase 7 rehecha en `fase7/`.
* `data/modelos/simulador/v3_1/`: pesos, examen e histórico.

La v1/v2 del repositorio y la v3 publicada antes no se tocan. Etiquetas: **[DATO]**, **[LECTURA]**, **[POST HOC]**
(decisión tomada después de ver el examen).

## 1. Qué se ha rehecho y por qué

| Pieza | Antes (v3) | Ahora (v3.1) |
|---|---|---|
| Datos | Procesados al 29-10, pero rasgos de pista de 2026-27 del 23-10 y v2 de 2026-27 del 14-10 | Todo con los datos al 29-10 |
| Normalización v2 (A, B, amortiguada) | La del repositorio | Rehecha: crosswalk, nacionalidades, pista, A, B, amortiguación, dataset, contexto, interacciones y escalas |
| v3.1 en 2026-27 | Sólo CVAE: la v2 de 2026-27 estaba desactualizada | Combinación real v2 + CVAE (peso 0,5 en 3.563 filas); CVAE final reentrenada (5 redes) |
| Ids de la BBL en la v3.1 | Id de modelo («n:nombre»): el simulador no encontraba la capacidad de los jugadores de la BBL | Id de la fuente |
| Traducción a la liga de destino | Constantes de la normalización amortiguada | Constantes de la v3.1 (§2) |
| Adaptación | Factor de temporada también en la producción (doble conteo de −0,2 % a −0,5 %) | Sólo en la ADAPT% mostrada (§3) |
| Roles, reemplazo, entropía, estilos unificados, fase 7 | Calculados con datos anteriores | Rehechos |
| Pesos de utilidad, calibración y Fit | Copiados de la v2 | Reentrenados con el examen completo (§4) |

## 2. Constantes de traducción de la v3.1 (`sim_insumos.traduccion_v31`)

El motor del navegador traduce la capacidad θ (DT de la vara EuroLeague) a la liga de destino con
z = (θ − δ)/s. Con las constantes amortiguadas, esa fórmula es la inversa de la v2, ya validada.

Para una θ de la v3.1 se predice primero su equivalente v2 en esa liga, E[θ_v2 | θ_v31] = c_lt + d_l·θ_v31. Se
ajusta con los jugadores con ≥ 400 min de la liga: pendiente común a sus temporadas e intercepto por temporada.
Componiendo las dos fórmulas:
* δ' = (δ − c)/d
* s' = s/d

Así cambian sólo los datos que lee el motor, no su código.

[DATO] 189 combinaciones métrica-liga:
* d mediana 0,87 (p10 0,73, p90 1,00): la v3.1 separa algo más a los jugadores que la v2.
* Correlación v3.1–v2 ≥ 0,96 en todas.
* Se usa la regresión en el sentido de la predicción (v2 sobre v3.1) y no su inversa: donde la relación es
  débil, la inversa exagera las diferencias.

## 3. Adaptación sin doble conteo (`bbfit/adaptacion_v3.py`)

* **ADAPT%(g)** = 100·(1 + D·e^(−g/κ)), con D ≤ 0. Es la que se muestra: empieza por debajo de 100 y sube.
* **El factor de temporada 1 + D·w̄** se aplica ahora sólo a esa métrica (L_rel).
* **La producción y el nivel L** ya salen de la v3.1, que predice el promedio de temporada de quien cambia de liga
  (con su arranque incluido): su factor de temporada es 1.

[DATO] Adaptación rehecha con los datos al 29-10 (curva bruta de los traspasos, por grupo de nacionalidad):

| Grupo | Partido 1 | 10 primeros | Temporada | 90 % del hueco cerrado en |
|---|---|---|---|---|
| Global | 95,6 | 99,0 | 99,7 | 3,9 partidos |
| De EE. UU. a Europa | 95,5 | 98,2 | 99,4 | 8,9 |
| Hacia EE. UU. | 94,4 | 98,0 | 99,4 | 7,5 |
| Dentro de EE. UU. | 93,6 | 97,3 | 99,1 | 9,3 |
| Europeo que cambia de liga | 96,8 | 99,0 | 99,7 | 6,1 |
| Nacional en su país | 96,5 | 99,0 | 99,7 | 5,4 |

## 4. Examen completo (`data/modelos/simulador/v3_1/validacion/V31_inicio_adapt/`)

* **Diseño:** el mismo examen temporal que la v2 (docs/checkpoints/F8.md §3): cortes 2021-22 … 2024-25, pesos en
  orden cronológico, plantilla al inicio de t+1.
* **Variante de producción:** con adaptación. La adaptación ya no cambia la producción, así que no hay fuga por esa
  vía.
* **Comparación:** con la v2 en los mismos fichajes, emparejados por nombre, corte, ligas y club. El `persona_id`
  cambia al rehacer el crosswalk.

[DATO]

| Métrica | v2 | v3.1 | v3.1 − v2 [IC90 bootstrap] |
|---|---|---|---|
| MAE minutos/partido (4.512) | 4,71 | **4,70** | |
| Acierto de rol | 0,443 | **0,447** | |
| Log-loss de rol | **1,235** | 1,238 | |
| MAE pts/100 (3.342 emparejados) | 3,79 | **3,77** | −0,02 [−0,04; +0,01] empate |
| MAE USG% | 2,65 | **2,58** | −0,08 [−0,10; −0,05] mejor |
| MAE AST% | 4,14 | **3,92** | −0,23 [−0,31; −0,13] mejor |
| MAE rebote of./def. por 100 | 0,78 / 1,30 | **0,74 / 1,24** | mejor |
| MAE TOV% | 2,67 | **2,60** | −0,07 [−0,09; −0,05] mejor |
| MAE TS% | **6,02** | 6,22 | +0,20 [+0,16; +0,24] **peor** |
| Cobertura del 90 % en pts/100 | **0,88** | 0,85 | |
| Índice Fit: correlación de rangos con el éxito | 0,524 | **0,530** | |

Frente a los dos modelos de referencia del examen, la v3.1 gana en minutos (−1,15 y −0,94), rol y pts/100 al simple
(b) (−0,04 [−0,07; −0,01]). Pierde en TS% con los dos y en pts/100 con la lógica del Atlas anterior (a), que con la
v3.1 mejora mucho (3,64).

### 4.1 Decisión post hoc: la Tercera FEB toma la capacidad de la v2 (`bbfit dataset-simulador`)

[DATO] Primera pasada, con la v3.1 tal cual. Fuera de la Tercera FEB, la v3.1 mejoraba a la v2 en pts/100 (3,58
frente a 3,65). En los fichajes con destino la Tercera FEB (777, casi todos desde ella misma) empeoraba:
* pts/100 5,09 frente a 4,39;
* cobertura del 90 % 0,54 frente a 0,81.

El diagnóstico con las constantes antiguas (V31A) daba lo mismo, así que el problema no era la traducción. Es la
capacidad: en esa liga la v3.1 usa sólo la CVAE (peso 1, el ajuste por conocimiento), que comprime las diferencias
entre jugadores. La correlación v3.1–v2 en PER es 0,37.

[POST HOC] El simulador lee un dataset propio: la v3.1, con las filas de la Tercera FEB tomadas del A+B amortiguado.
Con eso, en la Tercera FEB la v3.1 y la v2 coinciden y la traducción conserva las constantes amortiguadas.
Resultado:
* fichajes con la Tercera FEB: 4,54 frente a 4,36 de la v2, todavía algo peor;
* resto: 3,58 frente a 3,65.

Los diagnósticos están en `validacion/diagnostico_previo/`.

## 5. Producción y artifact [DATO]
* **Pesos de producción** (`simulador/v3_1/pesos.json`): utilidad con todas las temporadas cerradas, calibración del
  último corte, y Fit y calibración de salida con las predicciones del examen V31.
* **Histórico** (`historico_<temporada>.csv.gz`, columna `version` = v3.1): 854 / 818 / 964 / 1.444 / 1.509 / 1.765
  fichajes simulados para 2021-22 … 2026-27.
* **Paridad Python ↔ navegador:** 6 de 6 casos dentro de tolerancia, con el motor del repositorio y con el publicado.
* **Intervalo de la ADAPT%:** el motor muestrea Δ_temp con una normal sin recortar. La sd se limita a |media|/1,645
  para que el intervalo del 90 % no pase de 100.
* **Artifact «Cerno Analytics»** (sólo datos; página y motor sin cambios):
  * simulador v3.1;
  * Atlas de estilos con las 15 ligas y los estilos unificados rehechos;
  * estilos unificados de Quintetos, regenerados con los generadores de `artifact-v2-candidata`;
  * «Datos Normalizados» y explorador de normalización con la v3.1 al 29-10;
  * resumen de «Normalización de ligas» y «Evaluación de ligas» con la v2 rehecha.
* **Pestaña «Informe» del Atlas** (`atlas/informe/<temporada>.json`): su generador no estaba en el repositorio y los
  datos publicados eran antiguos.
  * Sólo coincidían 7 de 3.346 claves con el Atlas, y 2026-27 tenía 173 jugadores sin ACB, FEB ni NBA.
  * Reconstruido en `bbestilo/informe.py` (`python -m bbestilo informe`) a partir del formato publicado y de cómo lo
    lee la página. Validado reproduciendo 2025-26: valores observados y ficha idénticos; percentiles y referencias a
    ±1-2 puntos, por la versión distinta del dataset.
  * Regenerado con los datos al 29-10: 2.665 / 2.937 / 3.165 / 5.259 / 5.230 / 5.583 / 1.284 jugadores-club en 2020-21
    … 2026-27, todos con su fila de datos y su normalización (v3.1), FEB incluidas.

## 6. Lo que queda abierto [LECTURA]

* **TS% y cobertura de producción.**
  * El TS% es algo peor que en la v2 (+0,20) y el intervalo del 90 % de pts/100 cubre el 85 % (v2 88 %). En la
    Tercera FEB cubre el 70 %.
  * No se ha seguido ajustando contra el examen: sería sobreajustar.
  * Arreglarlo bien exige tocar el motor: un intervalo de producción recalibrado, como la capa de calibración que ya
    existe para los minutos.
* **Fuga en el examen.** La normalización v3.1 y la v2 están ajustadas con todas las temporadas, igual que en la v2.
  * En la v2 se midió que la fuga no cambiaba las conclusiones.
  * En la v3.1 no se ha repetido esa medida: haría falta reajustar la CVAE por corte.
* **Puerta de control de la v3.1.** Sigue igual: falla sólo por la cobertura del par Segunda → Tercera FEB.
  * Se decide con el examen limpio 2025-26 → 2026-27.
  * Con 6-8 jornadas (datos al 29-10) aún no es fiable, sobre todo por pares de ligas.
  * `configs/version.yaml` sigue en `v1`.
* **Mapa VaDE de las FEB.** Sigue siendo una proyección.
  * La taxonomía VaDE (E01–E06) está desestimada en la v3 (`config/ESTILOS_VADE_OBSOLETOS.md`).
  * Reentrenarla cambiaría el significado de esos estilos.
  * Los estilos oficiales (unificados) se han rehecho con las FEB.
