# Normalización v3.2

> Configuración: `configs/normalization_v32.yaml` · salida: `data/modelos/v3_2/` · código: `bbnorm3/`
> (modelo, ablación, combinación y vara de destino) · orden completo: `scripts/actualizar_v32.sh`.
> La v3.1 (`configs/normalization_v31.yaml`, `data/modelos/v3_1/`) no cambia.

La v3.2 es la v3.1 (mezcla de la normalización v2, A+B amortiguado, con la CVAE jerárquica) con las mejoras que el
usuario pidió el 02-11-2026. Cada mejora se aplica completa, se mide con **cortes anidados** y solo se queda si pasa
una regla fijada de antemano:

| Mejora | Qué es | Cómo se decide |
|---|---|---|
| B1 | Ablación de la CVAE: ciclo, FiLM por liga, cabezal por liga, factor propio ζ, IPW, K = 8 frente a 4 | Navaja (§3) |
| B2 | Peso de la CVAE en la mezcla por métrica (antes 0,5 fijo) | Mínimo error por métrica en los cortes anteriores |
| B4 | Inferencia semiamortizada (200 pasos con el decodificador congelado) | Navaja (§3) |
| B5 | 20 redes en el conjunto (antes 5) | Se aplica siempre |
| B6 | Verosimilitud t de Student con ν por métrica (antes normal) | Navaja (§3) |
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

## 3. Regla de la navaja (B1, B4, B6)

La regla se fijó con el usuario antes de ver ningún resultado. Para cada pieza P se compara la CVAE **sola** (sin
mezclar con la v2), completa, frente a la misma CVAE sin P. Así se mide la red, no la mezcla.

- **Diferencia de error.** Se calcula Δ = MAE_sin / MAE_con − 1 (media de las 33 métricas) con su intervalo del 95 %
  bootstrap, remuestreando persona × corte.
- **Cuándo se quita.** La pieza se **quita** si quitarla no empeora de forma significativa: el extremo inferior del
  intervalo es ≤ 0 y la cobertura media del 80 % recalibrada sin ella sigue en [0,78, 0,85].
- **Redes.** La ablación usa 5 redes por variante (las 5 primeras semillas). La configuración elegida se reentrena
  con 20 redes (B5) en todos los cortes y con todos los datos.
- **Piezas evaluadas.** Una por variante, frente a la completa: ciclo, FiLM, cabezal por liga, ζ, IPW, K8 (frente a
  K = 4), t de Student (frente a la normal) y refinado (B4, solo inferencia: mismas redes).
- **Piezas que se quitan a la vez.** Si la regla quita varias, la combinación se comprueba en el corte siguiente
  (ver §6).

## 4. Piezas nuevas

**B6 · t de Student.** La verosimilitud tiene escala² = v + ψ, que es la varianza de la v3.1. Los grados de
libertad ν_m se estiman por métrica, acotados en [3, 30] (ν = 3 + 27·sigmoide(·), inicio en 10).
- *En la inferencia semiamortizada:* el experto usa la información de Fisher de la t, (ν + 1)/((ν + 3)·escala²).
- *En la predicción:* el ruido de contexto y de muestra sigue la t; el efecto equipo sigue siendo normal.

**B4 · inferencia semiamortizada.** Parte de la media del codificador y optimiza la posición relativa r de cada fila
con el decodificador congelado (200 pasos). Así reduce el error del codificador en jugadores con pocas filas. No
cambia el entrenamiento: la huella de la caché de redes de la v3.2 excluye `inferencia`, así que con y sin B4 se
usan las mismas redes.

**B2 · peso por métrica.** Para cada métrica, el peso de la CVAE se elige entre {0; 0,25; 0,5; 0,75; 1} por mínimo
MAE en los cortes anteriores. En caso de empate (diferencia < 0,1 %) gana el más cercano a 0,5.
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

## 6. Resultados

*(se completan al terminar el cálculo: decisiones de la ablación por corte, examen anidado de la v3.2 frente a la v3.1
con 20 ligas y frente a la v2, pesos por métrica y vara de destino)*
