# Normalización v3.2

> Configuración: `configs/normalization_v32.yaml` · salida: `data/modelos/v3_2/` · código: `bbnorm3/`
> (modelo, ablación, combinación y vara de destino) · orden completo: `scripts/actualizar_v32.sh`.
> La v3.1 (`configs/normalization_v31.yaml`, `data/modelos/v3_1/`) no cambia.

La v3.2 es la v3.1 (mezcla de la normalización v2, A+B amortiguado, con la CVAE jerárquica) con las mejoras que el
usuario pidió el 02-11-2026. Cada mejora se aplica completa, se mide con **cortes anidados** y solo se queda si pasa
una regla fijada de antemano:

| Mejora | Qué es | Cómo se decide |
|---|---|---|
| B1 | Ablación de la CVAE: ciclo, FiLM por liga, cabezal por liga, factor propio ζ, IPW, K = 8 frente a 4 | No inferioridad (§3) |
| B2 | Peso de la CVAE en la mezcla por métrica (antes 0,5 fijo) | Mejora ≥ 1 % demostrada (§4) |
| B4 | Inferencia semiamortizada (200 pasos con el decodificador congelado) | No inferioridad (§3) |
| B5 | 20 redes en el conjunto (antes 5) | Se aplica siempre |
| B6 | Verosimilitud t de Student con ν por métrica (antes normal) | No inferioridad (§3) |
| B3 | Decodificar en la liga de destino | **Descartada** por el usuario |
| B8 | Modelo secuencial de trayectorias | **Descartada**; queda como trabajo futuro en el artículo |
| Vara de destino | Cualquier liga a 0 cuando es la de destino | Datos para el artifact (§5) |

## 1. Datos del examen

- **Casos.** Son los mismos que en la v3.1: cambios de liga t → t+1 con ≥ 300 minutos en ambas, 33 métricas.
- **Líneas base de la v2.** Antes solo existían con 15 ligas y en los cortes 2023 y 2024. Se rehicieron con las 20
  ligas en los cuatro cortes 2021-2024, en una copia aislada para no sobrescribir los ficheros versionados de la v2:
  - `bbmodel amortiguar --validar --variante sin_mapeo` y `bbmodel validar-b` → `data/modelos/v3_2/validacion/lineas_base/`;
  - F0 (la v2 con la covarianza completa del grafo) → `validacion/f0_<año>.csv.gz`.
- **El examen de la v3.1 nunca se repitió con 20 ligas.** La cadena del 31-10 reentrenó la v3.1, pero no el examen.
  Las cifras de la v3.1 citadas en la evaluación del 02-11 (CVAE sola +1,7 %, mezcla −3 %) son las de 15 ligas. El
  examen de la v3.2 incluye su comparación con 20 ligas en los mismos casos.

## 2. Cortes anidados

| Corte | Papel |
|---|---|
| 2021 (≤ 2021-22 → 2022-23) | Solo recalibra los intervalos del corte 2022 (recalibración conforme con el corte anterior) |
| 2022 | Primer corte de decisión. Sus resultados se aplican en el 2023 |
| 2023 | La decisión que se aplica en el 2024 usa 2022 + 2023 |
| 2024 | La decisión final (la de la v3.2 publicada) usa 2022 + 2023 + 2024 |

El examen informado de la v3.2 es el del **procedimiento**: lo que se aplica en cada corte sale solo de los
anteriores. Los cortes 2023 y 2024 ya se habían mirado al diseñar la v3.1, así que el examen limpio será
2025-26 → 2026-27, cuando acabe la temporada.

## 3. Regla de decisión de B1, B4 y B6

La regla se fijó con el usuario antes de ver ningún resultado.
- **02-11, primer plan.** Navaja sobre la CVAE sola: quitar si IC95,inf ≤ 0.
- **Mismo día, sustituida** por los criterios matemáticos del documento `CERNO_v3.2_criterios_matematicos` (§8),
  aprobados también antes de ver resultados.

Para cada pieza P se compara la configuración completa con la misma sin P:

- **Qué se evalúa.** La **mezcla** con peso fijo w = 0,5, no la red sola. Lo que se publica es la mezcla, y una pieza
  puede ser neutra sola y útil mezclada. El peso fijo separa B1 de B2.
- **Medida.** Δ_P = MAE_F(sin P)/MAE_F(con P) − 1. Primero se calcula el cociente de cada métrica, luego la media
  dentro de cada **familia** y luego entre familias.
  - Familias: tiro, uso y creación, rebote, defensa, impacto, perfil de tiro y global (`bbnorm3.ablacion.FAMILIAS`).
  - Así las seis métricas de tiro, que se mueven juntas, no pesan seis veces.
- **Intervalo del 95 %.** Bootstrap anidado: en cada réplica se remuestrean personas × corte y, por separado para «con»
  y «sin», las 5 semillas con reemplazo. Así entra la variabilidad del entrenamiento.
- **Cuándo se QUITA.** Cuando se cumple todo esto:
  - IC95,sup(Δ_P) < +0,5 % (no inferioridad);
  - la cobertura del 80 % recalibrada de la mezcla sin P sigue en [0,78, 0,85];
  - **salvaguarda de ciclo**, para todas las piezas: residuo medio de ciclo sin P ≤ 1,25 × con P, y no aumentan los
    triángulos con algún |R| > 0,5 DT (muestra fija de 60 triángulos de la última temporada del corte);
  - **salvaguarda de niveles**, obligatoria para la IPW: ningún nivel de competición se mueve más de una DT a
    posteriori en pts/100, TS%, PER ni RAPM. La IPW corrige la selección de los puentes, y el examen (que solo usa
    jugadores que cambian de liga) no puede mostrar su beneficio.
- **Cuándo se conserva.** Si IC95,inf(Δ_P) > 0 se **conserva**. Entre medias, la pieza es **indeterminada** y también
  se conserva.
- **Si se quitan dos o más piezas,** la configuración sin todas ellas debe cumplir la regla frente a la completa en el
  corte siguiente. Si no la cumple, se reincorporan una a una, empezando por la de mayor Δ, que es la que tiene la
  evidencia más débil para quitarla.
  - Lectura propia: el documento dice «en el orden de menor Δ». Lo he interpretado como devolver primero la pieza cuya
    retirada está peor justificada.
- **Redes.** La ablación usa 5 redes por variante. La configuración elegida se reentrena con 20 (B5).
- **B4, además,** se informa por tramo de minutos de origen (100-300, 300-800, > 800). Se espera la ganancia en el
  primer tramo; si solo aparece en el último, sería señal de sobreajuste del refinado.

## 4. Piezas nuevas

**B5 · 20 redes.** Se informa de la fracción de casos que activan la salvaguarda «DT entre redes > 0,5» con 5 y con
20 redes. Si difieren más de 2 puntos, el umbral pasa a ser el cuantil 95 % de los cortes anteriores.

**B6 · t de Student.** La verosimilitud tiene escala² = v + ψ, que es la varianza de la v3.1. Los grados de
libertad ν_m se estiman por métrica, acotados en [3, 30] (ν = 3 + 27·sigmoide(·), inicio en 10).
- *En la inferencia semiamortizada:* el experto usa la información de Fisher de la t, (ν + 1)/((ν + 3)·escala²).
- *En la predicción:* el ruido de contexto y de muestra sigue la t; el efecto equipo sigue siendo normal. Los
  intervalos salen de cuantiles Monte Carlo de la mezcla de muestras, no de z de la normal.
- *Posterior de los niveles:* deja de ser exacta. Con los expertos de información de Fisher es una aproximación de
  Laplace/Fisher.
- *Informe:* ν̂_m por métrica. Si alguna toca el límite inferior (3), hay que revisar la transformación de esa métrica.

**B4 · inferencia semiamortizada.** Parte de la media del codificador y optimiza la posición relativa r de cada fila
con el decodificador congelado (200 pasos). Así reduce el error del codificador en jugadores con pocas filas. No
cambia el entrenamiento: la huella de la caché de redes de la v3.2 excluye `inferencia`, así que con y sin B4 se
usan las mismas redes.

**B2 · peso por métrica** (§9 de los criterios).
- *Candidato:* ŵ_m = argmin del MAE en {0; 0,25; 0,5; 0,75; 1} con los cortes anteriores.
- *Cuándo se aplica:* el peso solo se aparta de 0,5 si la mejora es de al menos un 1 % y está demostrada:
  D = MAE(ŵ)/MAE(0,5) − 1 con IC95,sup(D) < −1 %, bootstrap por persona × corte.
- *Informe:* se publica cuántas métricas se apartan y en qué dirección.
- *Nivel de decisión:* por métrica, por decisión del usuario.
- Se cuentan solo los casos generales.
- Las salvaguardas de la v3.1 (liga con < 2 temporadas, discrepancia entre redes > 0,5 DT) y el ajuste por
  conocimiento de la Tercera FEB prevalecen sobre el peso por métrica.
- El ajuste de la Tercera FEB se rehace con el mismo procedimiento de la v3.1, sobreajuste asumido.

## 5. Vara de destino: cualquier liga a 0

La normalización no fija ninguna liga: el gauge es la media ponderada de todas las competiciones. «EuroLeague = 0»
es solo la forma de expresar la salida.

**Datos exportados** (`data/modelos/v3_2/destino/`):
- `capacidad/<temporada>.csv.gz`: θ de cada fila (DT de la vara EuroLeague) y la varianza **propia** del jugador,
  v_j = Var(θ) − Var(δ_o). Es decir, sin la incertidumbre del nivel de su liga frente a la EuroLeague.
- `constantes.json`: las mismas constantes lineales del simulador (escala, nivel, ψ, deriva, μ y τ por liga y
  posición) y el soporte observado de cada liga.
- `covarianza/<métrica>.json`: la covarianza conjunta Σ de los niveles δ de todas las competiciones-temporada.
  - Sale de la posterior de la contracción jerárquica del grafo de puentes (`covarianza_v2/`), pasada a las unidades
    de la v3.2 con la pendiente del sustituto lineal de cada liga.
  - Comprobación: su diagonal coincide con las desviaciones publicadas en `league_offsets.csv` (diferencia < 5·10⁻⁶).

**Traducción a la vara de la liga de destino d** (función de referencia `bbnorm3.destino.a_destino`; el simulador hace
lo mismo con `destino.vara: destino`):

```
z_d      = (θ + deriva(edad) − δ_d) / s_d                (recortado al soporte observado de d ± 0,25 DT)
valor    = T⁻¹(μ_{d,t,pos} + τ_{d,pos} · z_d)             (percentil en d = Φ(z_d))
Var(z_d) = (v_j + Σ_oo + Σ_dd − 2 Σ_od) / s_d²
nivel de X con d = 0:  δ_X − δ_d,  DT = √(Σ_XX + Σ_dd − 2 Σ_Xd)
```

**Qué cambia y qué no.**
- *Valor esperado:* poner la liga de destino a 0 no lo cambia. La traducción es afín en la escala de trabajo, así que
  la mezcla v2/CVAE da el mismo centro en cualquier vara.
- *Incertidumbre:* cambia. Se usa Var(δ_o − δ_d) con la covarianza en vez de sumar las dos varianzas frente a la
  EuroLeague. En pts/100, la DT del par ACB–BBL pasa de 0,076 a 0,072; en TS%, de 0,129 a 0,116.
- *Recorte de soporte:* pasa a ser el de la liga de destino.
- *Con d = EuroLeague* se recupera la salida de siempre.

**Criterios del 02-11 (§11), aplicados:**
- **(a) Covarianza de la mezcla.** La DT por par usa la cota de Cauchy-Schwarz:
  sd_mix(δ_o − δ_d) ≤ w_m·sd_CVAE + (1 − w_m)·sd_v2. Σ_CVAE se calcula por métrica a partir de las 20 redes:
  J Σ̃ Jᵀ más la varianza entre redes. Se guarda como `sd_par_triangular` y el simulador la usa.
- **(b) Varianza propia negativa.** Las filas con Var(θ) − Var(δ_o) < 0 son el 0,00-0,04 % (v3.1, 2024-25), por debajo
  del umbral del 1 %. Además, el código no trunca a 0: deja como mínimo el 10 % de Var(θ). Se informa en
  `constantes.json`.
- **(c) Centro sin recortar.** La distancia fuera del soporte se suma como varianza:
  sd_ext = √(sd² + (z − z*)²). Se añade la marca `extrapolacion`. Lo mismo en la CVAE (`prediccion.recorte_centro:
  false`).
- **(d) Comprobaciones.** Pruebas de invariancia y de recuperar la v3.1 con d = EuroLeague, y la tabla
  `reduccion_varianza_pares.csv` (pts/100 y TS%, 2025-26).
- **Peso del nivel de liga.** Es solo el 2-4 % de la varianza total de la capacidad de un jugador (mediana). La vara de
  destino corrige las cuentas, pero apenas cambia la anchura de los intervalos.
- **§12, ciclo.** Las traducciones publicadas son lineales y por construcción tienen residuo de ciclo exactamente 0. El
  residuo de 0,045 DT de media (máximo 0,86 en pts/100 y 0,63 en TS%, 25 triángulos > 0,5 DT de 1.140; con la
  configuración final y las identidades corregidas) es del camino
  codificar-decodificar de la CVAE, que no se publica desde que se descartó B3. Queda como diagnóstico y como
  salvaguarda de B1.

## 6. Resultados

### 6.1 Ablación (B1, B4, B6)

Tabla con la mezcla al 0,5 y 5 redes por variante; datos en `validacion/ablacion/decisiones.json`.
- Δ = MAE sin la pieza / MAE con ella − 1, con media por familias y su IC del 95 %.
- La salvaguarda de ciclo compara el residuo medio sin la pieza con el de la configuración completa.

| Pieza | Corte 2022 | Cortes 2022-23 | Cortes 2022-24 (final) | Decisión |
|---|---|---|---|---|
| K = 8 (frente a 4) | −0,65 % [−1,12, −0,10] | −0,67 % [−1,00, −0,34] | −0,91 % [−1,21, −0,67] | Se quita: **K = 4** |
| Inferencia semiamortizada (B4) | −0,38 % [−0,64, −0,09] | −0,51 % [−0,74, −0,30] | −0,67 % [−0,86, −0,51] | Se quita |
| FiLM por liga | −0,12 % [−0,29, +0,05] | −0,32 % [−0,53, −0,18] | −0,24 % [−0,41, −0,08] | Se quita |
| Cabezal por liga | +0,09 % [−0,12, +0,33] | −0,11 % [−0,31, +0,06] | +0,14 % [−0,03, +0,27] | Se quita (no inferior) |
| t de Student (B6) | +0,08 % [−0,13, +0,27] | −0,02 % [−0,21, +0,16] | +0,03 % [−0,13, +0,21] | Se quita (no inferior) |
| Factor propio ζ | +0,45 % [+0,21, +0,70] | +0,43 % [+0,19, +0,63] | +0,39 % [+0,18, +0,57] | **Se conserva** |
| Consistencia de ciclo | +0,09 % [−0,07, +0,25] | −0,04 % [−0,24, +0,09] | +0,12 % [−0,06, +0,28] | Se conserva: sin ella el ciclo pasa de 0,13 a 0,36 |
| IPW | −0,03 % [−0,32, +0,25] | −0,16 % [−0,39, +0,04] | −0,13 % [−0,33, +0,07] | Se conserva: sin ella los niveles se mueven hasta 4,8 DT |

**Coherencia y combinación**
- Las tres decisiones anidadas coinciden.
- La combinación de las cinco piezas quitadas cumple la regla frente a la completa en el corte siguiente: −1,1 %
  [−1,6, −0,7] en 2023 y −1,4 % [−1,9, −0,9] en 2024.

**Lectura**
- La red más simple (K = 4, sin ajustes por liga, amortizada y normal) predice mejor y con la misma cobertura.
- Las dos piezas nuevas de la v3.2 (B4 y B6) no aportan y la regla las retira.
- Las salvaguardas protegen dos piezas cuyo valor el error medio no distingue: la coherencia de ciclo y la IPW.
- Configuración final: `ablacion.quitadas` en `configs/normalization_v32.yaml`. La configuración completa queda en
  `_completa` al cargar.

### 6.2 Examen anidado (B2, B5)

Cortes 2022-2024, 1.431 personas × corte; datos en `validacion/examen_v32.json`. El error es la media de las 33
métricas, relativa a la v2.

**Cifras con las identidades corregidas** (03-11-2026, `docs/identidades_20261103.md`). La normalización v3.2 se
rehízo entera con los mismos datos, salvo la ablación (§6.1), que conserva su decisión. Antes de la corrección, la
v3.2 publicada daba −2,8 % [−3,2, −2,4] y la red sola −1,4 %.

| Variante | Error frente a la v2 [IC 95 %] | Cobertura del 80 % |
|---|---|---|
| Red sola (20 redes, configuración final) | −2,0 % [−2,7, −1,2] | 0,804 |
| Mezcla con peso 0,5 | −3,2 % [−3,6, −2,8] | 0,808 |
| Mezcla con B2 anidado | −3,2 % [−3,6, −2,8] | 0,808 |
| **v3.2 publicada** (B2 y ajuste de la Tercera FEB) | **−3,2 % [−3,6, −2,8]** | **0,811** |

**Lectura de la tabla**
- **La red sola ya gana a la v2.** En la v3.1, con 15 ligas, quedaba +1,7 %.
- **Por grupo de destino:**

  | Grupo de destino | Error frente a la v2 |
  |---|---|
  | EuroLeague | −2,2 % [−3,2, −1,0] |
  | Resto de Europa | −2,9 % |
  | FEB | −2,5 % |
  | NBA/G League | −4,1 % |

- **Puerta de control de la v3.1:**
  - Cumple el error global y el destino EuroLeague.
  - Falla la cobertura en 4 de los pares con ≥ 30 personas: Segunda → Tercera FEB 0,778; G League → NBA 0,857;
    NBA → G League 0,855; NCAA → NBA 0,771.
  - Se informa y se mantiene como pendiente para el examen limpio.
- **B2:**
  - Peso final: solo el **RAPM** se aparta de 0,5 y pasa a 1 (solo la red), con −6,2 % [−8,5, −3,9].
  - Ninguna otra métrica demuestra una mejora de al menos el 1 %. AST% (−1,4 % [−2,3, −0,6]) no llega: la regla
    exige que el extremo superior del IC quede por debajo de −1 %.
  - En los cortes anidados 2023 y 2024 ninguna métrica se apartó de 0,5.
- **B5.** Ningún caso activa la salvaguarda de discrepancia entre redes (> 0,5 DT), ni con 5 redes ni con 20. El
  umbral no cambia; su cuantil 95 % es 0,11.
- **B6.** No se informa de ν porque la t de Student quedó fuera.
- **Tercera FEB** (conocimiento, mismo procedimiento que la v3.1): peso 0,5 y factor de intervalo 1,06.
- **§14, RAPM.** La ganancia frente a la v2 es −10,3 % en todos los casos y −10,6 % con exposición alta en destino
  (ORAPM −6,6 / −6,7 %; DRAPM −2,4 / −1,9 %). Se mantiene con exposición alta, así que se puede comunicar como impacto
  en pista.

### 6.3 Vara de destino

**Reducción de la DT del nivel por par.** Datos en `destino/reduccion_varianza_pares.csv`. En pts/100, el par
ACB–BBL pasa de 0,081 (sumando las marginales) a 0,077 (v2 con covarianza) y a 0,066 (mezcla).

**§11b, filas en las que Var(θ) < Var(δ_o).**
- Con la varianza de nivel de la v2, son menos del 1 % en todas las métricas salvo el **RAPM (45 %)**.
- La v2 no tiene intervalo de RAPM, de modo que entre el 66 y el 95 % de sus filas usan solo la red.
- Para el RAPM, el nivel se resta con el mismo modelo que da el valor de cada fila: w_fila·sd_red + (1 − w_fila)·sd_v2.
  El resultado se informa en `constantes.json` (`v_j_negativa_tras_11b`).
- **Resultado.** En el RAPM la fracción baja del 45,0 % al 8,4 %. Sigue por encima del 1 %, porque en las filas que
  usan solo la red la varianza del nivel es comparable a la del propio RAPM. En esas filas no se trunca a 0: Var(θ)
  conserva el 10 %, de modo que su intervalo es algo más estrecho de lo que debería. Queda señalado para el examen
  limpio. En el resto de métricas no cambia nada (< 1 %).
