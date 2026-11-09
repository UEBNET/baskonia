# Checkpoint V42_D2_motor — motor de minutos y producción v4.2 (historial del jugador)

Fecha: 09-11-2026. Prerregistro: `configs/v42.yaml → motor_v42` (commit `d606f47`, antes de calcular; no se ha tocado).
Código: `bbequipo/v42/motor.py`. Configuración: `configs/simulation_v42.yaml` (`CERNO_SIMULADOR=v42`).
Resultado: `data/modelos/v4_2/motor/examen_d2_motor.json`. Etiquetas: **[DATO]** medido · **[LECTURA]** interpretación ·
**[SUPUESTO]** elección no prerregistrada · **[POST HOC]** mirado después de ver resultados · **[DECISIÓN]**.

## 0. Resumen

1. **[DECISIÓN] Se mantiene el motor v3.3.** La v4.2 no pasa el examen prerregistrado, ni en el brazo prerregistrado
   (historial sólo en las 6 métricas del motor que pasaron la D1) ni en la variante con historial en todas.
2. **[DATO] Motivo:**
   - empeora el rebote ofensivo por 100: **+3,3 %** [+1,4; +5,2];
   - empeora los tapones por 100: **+1,8 %** [+0,2; +3,4];
   - en USG% no se descarta un empeoramiento mayor que el margen: IC95 superior +1,25 % frente a +1 %.
3. **[DATO] Lo que no cambia o mejora sin significación:** pts/100 −0,66 % [−1,47; +0,18], minutos −0,10 % [−0,38; +0,17]
   y cobertura del 80 % en rango en todo.
4. **[DATO] Los intervalos no salen más estrechos.** Antes de recalibrar el motor da rangos del 80 % de pts/100 un 15 %
   más estrechos, pero cubren 0,66. Con la recalibración conformal del corte de calibración, la anchura mediana queda en
   ×1,02 de la v3.3.

## 1. Qué cambia en el motor v4.2

**Antes (v3.3).** El motor lee la capacidad θ de cada jugador en cada métrica de una sola temporada:
- normalización v3.2;
- DT de la vara EuroLeague, con su rango del 80 %.

**Ahora (v4.2).** Usa el nivel con historial: el filtro de Kalman de la D1 (`historial.py`) aplicado en la escala θ.
- **Estado:** paseo aleatorio con τ² por año.
- **Observación:** θ de la temporada, con varianza c·sd². Varias ligas en una temporada se combinan con media ponderada
  por precisión.
- **Previa de la primera temporada:** N(μ_pos, σ²_pos).
- **Ajuste:** τ² y c por máxima verosimilitud de las innovaciones un paso adelante, con temporadas ≤ t.
- **Qué se sustituye en los registros de la temporada t:** `<m>_th`, `<m>_thsd`, `<m>_am` y la varianza propia `<m>_vj`.
  L y L_sd se recalculan.
- **Compañeros:** los de la plantilla también llevan el nivel filtrado.

**Brazos del examen:**

| Brazo | Métricas con historial | Papel |
|---|---|---|
| `v42_d1` | Las 6 del motor que pasaron la D1: pts_p100, usg_pct, tov_pct, oreb_p100, stl_p100, blk_p100 | **Decide** (`entradas_motor_v42`: «donde la métrica pasó D1») |
| `v42` | Las 15 del motor salvo RAPM (incluye TS%, eFG%, AST%, DREB, PER, ratings, WS, game score) | Variante del encargo de la pieza; se informa |

**Sin fuga (por corte t):**
- La historia son las temporadas < t traducidas con los **modelos del propio corte**: la CVAE de las 20 redes ≤ t
  (`experimentos/v3/h<t>_*.pt`) y el A amortiguado ≤ t.
- Va en la vara EuroLeague de la temporada t, la misma mezcla que `normalizacion_hasta_v32` hace para las filas de t.
- La temporada t es la del corte V32_corte original, sin cambios.
- Ningún modelo ni parámetro ve t+1.

**Cambio en `bbfit`:** una sola línea. `bbfit/config.py` acepta `CERNO_SIMULADOR=v42`. Sin la variable, o con
v3/v31/v32/v33/v40, todo sigue igual. Comprobado: con v33 se carga la configuración v3.3 y la caché de siempre.

**Publicación.** `configs/simulation_v42.yaml` es copia de la v3.3 con:
- `version: "v4.2"` y `carpeta: v4_2`;
- `normalizacion.dir: experimentos/cache_simulador_v4_2/normalizado`. Es el dataset del simulador v3.3 con
  `<m>_am`, `_am_lo` y `_am_hi` filtrados en las 11 métricas que pasaron la D1, con τ² y c ajustados sólo con
  temporadas ≤ 2021-22.

Prueba de humo: `CERNO_SIMULADOR=v42 python -m bbfit simular …` funciona. **No se publica**: la v4.2 no pasa.

## 2. Examen (el mismo que decidió la v3.3)

**Banco:**
- Fichajes reales del examen sin fuga V32_corte (escenario inicio, con adaptación): 6.322 en los cortes 2021-22 → 2024-25.
- Mismos fichajes en los tres brazos.
- Producción: fichajes con ≥ 300 min en destino de los cortes de decisión (≈ 3.600). Minutos: 4.956.

**Idéntico en los tres brazos (sólo cambia θ):**
- pesos de la utilidad, calibración, Fit y capa de calibración de salida por corte: los de `V32_inicio_adapt`, como en
  el examen original;
- matriz de transición, plantillas y semillas;
- **400 iteraciones Monte Carlo por fichaje**: el examen completo, sin recortes;
- decisiones anidadas de la v3.2: pasos, k = (0, 0), producción motor/Atlas/motor en 2022/2023/2024;
- centro de minutos anidado de la v3.3 (motor/mezcla), con su GBM reentrenado en cada brazo sólo con los cortes
  anteriores.

**Recalibración (prerregistro):** factores conformales A4 ajustados **sólo con el corte 2021-22**, con el mismo método que
el corte de decisión. La recalibración anidada del examen v3.3 se informa aparte.

**Medidas:**
- MAE pareado, v4.2 − v3.3, en unidades y relativo, con IC95 bootstrap con B = 2000. Se remuestrea por persona
  (prerregistro) y por club de destino × corte; se toma el IC95 superior mayor de los dos.
- **[SUPUESTO]** Margen de no inferioridad, el de la v4.0 (`simulation_v40.yaml → margenes`):
  - pts/100 y TS%: +0,5 %;
  - minutos: +1 %;
  - resto de métricas: +1 % («secundarias»).
- La contribución C se informa, pero no decide: no es producción por 100 ni minutos.

### 2.1 Brazo que decide (`v42_d1`): conjunto 2022-23 a 2024-25 [DATO]

| Métrica | MAE v3.3 | MAE v4.2 | Δ [IC95] | ΔR [IC95] (persona) | Cob 80 % v3.3 / v4.2 | Anchura v4.2/v3.3 | Cumple |
|---|---|---|---|---|---|---|---|
| pts_p100 | 3,830 | 3,805 | −0,025 [−0,057; +0,007] | −0,66 % [−1,47; +0,18] | 0,797 / 0,795 | 1,02 | sí |
| ts_pct | 4,934 | 4,931 | −0,002 [−0,008; +0,003] | −0,05 % [−0,16; +0,06] | 0,814 / 0,809 | 1,00 | sí |
| usg_pct | 2,858 | 2,865 | +0,007 [−0,022; +0,036] | +0,23 % [−0,78; **+1,25**] | 0,815 / 0,813 | 0,99 | **no** |
| ast_pct | 4,140 | 4,133 | −0,007 [−0,018; +0,004] | −0,17 % [−0,43; +0,11] | 0,801 / 0,796 | 0,99 | sí |
| oreb_p100 | 0,753 | 0,777 | **+0,024 [+0,011; +0,039]** | **+3,25 % [+1,43; +5,19]** | 0,815 / 0,814 | 1,09 | **no** |
| dreb_p100 | 1,264 | 1,262 | −0,002 [−0,006; +0,002] | −0,15 % [−0,47; +0,16] | 0,796 / 0,796 | 1,00 | sí |
| stl_p100 | 0,494 | 0,491 | −0,003 [−0,006; +0,001] | −0,56 % [−1,25; +0,16] | 0,788 / 0,785 | 1,01 | sí |
| blk_p100 | 0,354 | 0,360 | **+0,006 [+0,001; +0,012]** | **+1,81 % [+0,24; +3,41]** | 0,832 / 0,828 | 1,07 | **no** |
| tov_pct | 2,768 | 2,750 | −0,018 [−0,037; +0,002] | −0,64 % [−1,35; +0,06] | 0,771 / 0,793 | 1,04 | sí |
| minutos | 4,652 | 4,647 | −0,005 [−0,018; +0,008] | −0,10 % [−0,38; +0,17] | 0,810 / 0,813 | 1,00 | sí |
| C (informativa) | 4,467 | 4,478 | +0,011 [−0,003; +0,024] | +0,24 % [−0,06; +0,55] | 0,654 / 0,659 | 1,00 | — |

**Por club × corte:** los IC95 son casi iguales; por ejemplo, USG% [−0,77; +1,30] y oreb [+1,16; +5,17].

**Anchura del 80 % sin recalibrar (v4.2/v3.3):**

| Métrica | Anchura | Cobertura v3.3 → v4.2 |
|---|---|---|
| pts/100 | 0,85 | 0,75 → 0,66 |
| tov | 0,75 | 0,72 → 0,58 |
| oreb | 0,88 | — |
| blk | 0,88 | — |

**Con la recalibración anidada del examen v3.3:** cobertura de pts/100 0,815 / 0,812 y de minutos 0,806 / 0,807.

### 2.2 Variante con todas las métricas (`v42`) [DATO]

**No pasa.** Por métrica:

| Métrica | ΔR [IC95] |
|---|---|
| oreb_p100 | **+3,49 % [+1,69; +5,34]** |
| blk_p100 | **+1,80 % [+0,25; +3,40]** |
| USG% | +0,15 % [−0,85; +1,17] |
| AST% | +0,94 % [−0,66; +2,64] |
| DREB | +0,64 % [−0,79; +2,13] |
| C | +0,61 % [+0,23; +0,99] |
| **TS%** | **−3,77 % [−4,75; −2,81]** (mejora clara) |
| pts/100 | −0,62 % [−1,44; +0,23] |
| minutos | −0,09 % [−0,45; +0,26] |

La cobertura está en rango en todas.

### 2.3 Por corte (brazo `v42_d1`, ΔR puntual) [DATO]

| Corte (producción) | pts | USG | oreb | blk | tov | min |
|---|---|---|---|---|---|---|
| 2022-23 (motor) | +0,2 % | +3,0 % | −3,2 % | −2,5 % | −0,5 % | −0,1 % |
| 2023-24 (**Atlas**) | −0,0 % | +0,9 % | **+14,3 %** | **+10,1 %** | −0,7 % | −0,4 % |
| 2024-25 (motor) | −1,8 % | −2,2 % | −1,7 % | −2,9 % | −0,7 % | +0,1 % |

## 3. Lecturas

- **[LECTURA, POST HOC]** El daño se concentra en el corte 2023-24, el único en que la decisión anidada de la v3.2 usa la
  producción del Atlas (A2).
  - Ahí el nivel filtrado entra casi directo en la predicción.
  - El sesgo medio de oreb mejora (−0,30 → −0,19), pero el MAE sube en casi todas las ligas de origen, sobre todo en
    G League (+0,30) y NCAA (+0,11).
  - El historial y la previa por posición aplanan las diferencias entre jugadores que el Atlas necesita.
  - Con producción del motor (2022 y 2024), la v4.2 mejora casi todo. **No cambia la decisión:** la regla es el
    conjunto, y el simulador publicado v3.3 usa precisamente la producción del Atlas (`produccion_publicada: atlas`).
- **[LECTURA]** Que los rangos del 80 % de la normalización salgan entre 2 y 5 veces más estrechos (c ≈ 0,13–0,66) no se
  traslada al motor. Su intervalo lo dominan el ruido personal, el de muestreo, el rol y los minutos. La recalibración
  honesta devuelve la anchura de la v3.3.
- **[LECTURA]** La mejora de TS% en la variante de todas las métricas es real en el motor (−3,8 %), aunque la D1 dejó TS%
  en la v3.2. No basta: en esa variante empeoran rebote y tapones, y no se puede descartar un empeoramiento en AST% y
  DREB.

## 4. Controles y supuestos

**Reproducción [DATO].** El brazo v3.3 rehecho frente a las predicciones guardadas del examen original
(`data/modelos/simulador/v3_2/validacion/V32_corte_inicio_adapt`):
- minutos idénticos en el 97 % de los fichajes (diferencia media 0,005);
- producción con diferencia media 0,03 pts/100: insumos de datos actualizados después del examen, comunes a los tres
  brazos;
- el MAE de pts/100 y minutos de la v3.3 por corte reproduce `decisiones_v33.json`, por ejemplo 3,6915 frente a 3,6926 y
  4,9916 frente a 4,9900 en 2022-23.

**Parámetros del filtro [DATO]** (brazo `v42_d1`, corte 2024-25):

| Métrica | τ² | c |
|---|---|---|
| pts | 0,13 | 0,28 |
| USG | 0,10 | 0,24 |
| oreb | 0,05 | 0,20 |
| stl | 0,07 | 0,24 |
| blk | 0,02 | 0,15 |
| tov | 0,04 | 0,12 |

- La sd del nivel queda en ×0,27–0,45 de la de una temporada.
- Con historia: 60 % de las personas en 2024-25, y sólo el 43 % en 2023-24, por las ligas nuevas.
- En el corte 2021-22 sólo hay dos temporadas, y τ² = 0 en pts y USG.

**Supuestos [SUPUESTO]:**
- Historia en la vara EuroLeague de t, con los modelos de t.
- Nivel por persona: varias ligas en t comparten el mismo valor filtrado.
- `_vj` = máx(P − v_liga, 0,1·P).
- Margen +1 % para oreb, dreb, stl y blk.
- IC95 superior: el mayor de los dos remuestreos.
- C, informativa.
- **Net del equipo:** el criterio prerregistrado lo nombra, pero el banco del motor no lo produce. Es el examen de la
  capa 4 de la v4.0 (pieza D2-β) y aquí no se ha evaluado. No cambiaría la decisión: el motor ya no pasa.

**Publicación v4.2 (no activa):** las constantes de traducción (`traduccion_v31.pkl`), el GBM de minutos y los factores
A4 son los de la v3.3, enlazados en la caché `experimentos/cache_simulador_v4_2`.

## 5. Cómo reproducir

```
PYTHONPATH=. python -m bbequipo.v42.motor theta      # historia θ ≤ t por corte (≈ 10–40 min por corte, CVAE)
PYTHONPATH=. python -m bbequipo.v42.motor brazos     # cachés de los brazos (cortes V32_corte original y filtrados)
PYTHONPATH=. python -m bbequipo.v42.motor backtest   # 3 brazos × 4 cortes, 400 iteraciones (≈ 12 min por brazo)
PYTHONPATH=. python -m bbequipo.v42.motor examen     # ≈ 35 s → data/modelos/v4_2/motor/examen_d2_motor.json
PYTHONPATH=. python -m bbequipo.v42.motor dataset    # ≈ 90 s → experimentos/cache_simulador_v4_2/normalizado
```

Todo es reanudable y queda en caché en `experimentos/cache_simulador_v4_2/examen/`. Esa carpeta y `normalizado/` no se
versionan. La caché de la v3.2 y `experimentos/v3` sólo se leen.

**Tiempo de esta ejecución:**
- historia θ: 9, 13, 23 y 40 min, con la CPU compartida;
- brazos: ≈ 12–15 min de simulación cada uno;
- examen: 35 s;
- total de reloj: ≈ 1 h 35 min.

**Salidas:**

| Fichero | Contenido |
|---|---|
| `data/modelos/v4_2/motor/examen_d2_motor.json` | Examen completo, por corte, reglas y parámetros |
| `data/modelos/v4_2/motor/validacion/{v33,v42_d1,v42}/` | Predicciones y resumen de cada brazo |
| `data/modelos/v4_2/motor/dataset_simulador_v42.json` | Parámetros del dataset publicado |
