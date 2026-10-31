# Normalización v3.1: combinación v2 + CVAE corregida

**Código:** `bbnorm3/combinacion.py` · **Configuración:** `configs/normalization_v31.yaml` · **Salidas:**
`data/modelos/v3_1/` · **Selector de versión:** `configs/version.yaml` (sigue en `v1`) · **Base:** la v3.0
([`normalizacion_v3_cvae.md`](normalizacion_v3_cvae.md)), que no pasó la puerta de control.

```bash
python -m bbnorm3 --config configs/normalization_v31.yaml validar-combinada   # examen (orientativo, ver §4)
python -m bbnorm3 --config configs/normalization_v31.yaml ajustar-combinada   # ajuste final y dataset normalizado
```

Etiquetas: **DATO** = sale de un fichero reproducible; **LECTURA** = interpretación; **HIPÓTESIS** = supuesto;
**SOBREAJUSTE** = decisión tomada mirando el examen.

## 1. Idea

La v2 (`<m>_am`, A+B amortiguado) gana porque promedia dos modelos que fallan de forma distinta. La v3.1 añade un
tercero: la CVAE jerárquica. Las piezas son tres:

1. **CVAE corregida.** Se fija la escala latente por liga (s_l = 1). En la v3.0 la escala libre de la Tercera FEB
   se degeneró (s = 15,6) en el corte 2023 y la «desconectó» de sus puentes. La corrección es general: vale para
   cualquier liga.
2. **Mezcla con la v2, caso a caso.** Se hace en la escala de trabajo de cada métrica (transformada y estandarizada):
   * centro = w · CVAE + (1 − w) · v2;
   * predictiva = mezcla de las dos normales, con la anchura de F0 en la parte v2. F0 es el intervalo del A
     amortiguado con la covarianza completa del grafo, que corrige el doble conteo de la v2;
   * recalibración conforme con el corte anterior, igual que en la v3.0.
3. **Pesos.**

| Regla | w (peso de la CVAE) | Origen |
|---|---|---|
| General | 0,5 | Fijado de antemano (sin mirar el examen) |
| Liga de origen o destino con < 2 temporadas en el ajuste | 0 (sólo v2) | Salvaguarda general: la CVAE no tiene con qué anclar el nivel |
| Las 5 redes de la CVAE discrepan > 0,5 DT en esa métrica | 0 (sólo v2) | Salvaguarda general, fijada de antemano |
| Casos con origen o destino en la **Tercera FEB** | `peso_v3_conocimiento`, elegido entre {0, 0,25, 0,5, 0,75, 1} | **SOBREAJUSTE** asumido por el CEO: conocimiento de esta liga |

**HIPÓTESIS.** Los errores de la v2 y de la CVAE están poco correlacionados, así que su media es más precisa que
cada una. **LECTURA** previa al examen: en el corte de selección (2022 → 23), la media simple de la CVAE v3.0 y
`<m>_am` ya mejoraba un 1,1 % a `<m>_am`.

## 2. Qué se reutiliza
* Las redes de la CVAE con s_l = 1 de los cortes 2022 y 2023 son las del diagnóstico post hoc de la v3.0 (misma
  configuración y semillas; la caché las identifica por huella). El corte 2024 y el ajuste final se entrenan nuevos.
* Líneas base: `<m>_am`, F0 y mismo percentil de la v2. Las del corte 2022 se recalcularon con ≤ 2022 y se
  guardan en `data/modelos/v3_1/validacion/lineas_base_2022/`.

## 3. Salidas (`data/modelos/v3_1/`)
| Fichero | Contenido |
|---|---|
| `normalizado/<temporada>.csv.gz` | Esquema del v1 (mismas columnas y orden). Las columnas de estimación final (`<m>`, `_lo`, `_hi`, `_pctel`, `<m>_am`, `_am_lo`, `_am_hi`, `_am_pctel`) llevan la v3.1. Se conservan `<m>_v1` y `<m>_am_v1` (originales), las de la CVAE (`<m>_v3*`) y las propias (`<m>_v31`, `_v31_lo`, `_v31_hi`, `_v31_pctel`, `_v31_peso_cvae`) |
| `niveles.csv`, `niveles_covarianza.csv.gz`, `traduccion_cruzada/`, `puentes.csv`, `ciclo.csv`, `resumen.json` | Los mismos ficheros de la v3.0 (§4 de su documento), con la CVAE corregida |
| `validacion/examen_v31.json` | El examen de las tres variantes (§4) |
| `validacion/casos_combinada.csv.gz`, `resumen_metricas_combinada.csv` | Casos y resumen por métrica de la variante con conocimiento |

Reglas del dataset normalizado, fila a fila (columna `fuente_v3` y `<m>_v31_peso_cvae`):
* `posterior_conjunta`: fila del entrenamiento (≥ 100 min); combinación con w = 0,5 (Tercera FEB: w = 1, intervalo
  × 1,12; redes que discrepan > 0,5 DT: w = 0).
* `codificador`: fila con < 100 min; la CVAE la traduce con su codificador y el prior por nivel.
* `codificador_nivel_temporada_anterior`: competición sin ninguna fila de entrenamiento (p. ej. la BCL 2026-27, en
  la que nadie llega aún a 100 min). Usa el nivel y el entorno de la última temporada de esa liga, más el paso
  aleatorio κ² de una temporada.
* `solo_v1`: fila que la CVAE no traduce (jugador sin posición estimada); se conserva el valor v1 (w = 0).
* Sólo CVAE (w = 1) si la fila no existe en el v1 o el v1 la calculó con otros partidos. Pasa en 2026-27: el v1 es del
  14-10 y no se mezcla un valor viejo con uno nuevo.
* Cruce con el v1 por (player_id, team_id, liga, temporada). Si falla, se cruza por nombre normalizado + equipo (los ids
  de la BBL 2025-26 han cambiado de formato).
* Comprobación: en la EuroLeague 2025-26 (la vara), la mediana traducida coincide con la observada (pts/100 21,7
  frente a 21,1; PER 14,2 frente a 13,7). En el resto de ligas la CVAE sitúa los niveles algo más lejos de la
  EuroLeague que la v2 (mediana de pts/100 de todas las filas: v2 16,6; CVAE 13,4; v3.1 15,0).

## 4. Examen (orientativo)

Es el mismo examen que el de la v3.0: cortes 2023 → 24 y 2024 → 25, con la CVAE reentrenada en cada corte (5
semillas), mismos casos y la misma puerta. **Aviso:** esos cortes ya se habían visto al diseñar la v3.1, así que los
números son orientativos. La decisión debe tomarse con el examen limpio 2025-26 → 2026-27.

### 4.1 Las tres variantes [DATO: `validacion/examen_v31.json`]
| Variante | MAE frente a `<m>_am` (IC 95 %) | Corte 2023 | Corte 2024 | Cobertura 80 % | A la EuroLeague | ¿Puerta? |
|---|---|---|---|---|---|---|
| CVAE corregida sola | +1,7 % (+0,1 %, +3,4 %) | +7,5 % | −3,9 % | 0,803 | +3,6 % | No |
| **Combinación, regla fijada de antemano** | **−3,0 % (−3,5 %, −2,4 %)** | −0,9 % | −4,8 % | 0,808 | −1,2 % (−2,7 %, +0,6 %) | No (sólo cobertura FEB) |
| Combinación + conocimiento FEB3 (**SOBREAJUSTE**) | −3,3 % (−4,1 %, −2,5 %) | −0,9 % | −5,4 % | 0,815 | −1,2 % | No (un par, por poco) |

Criterios de la variante con conocimiento: (1) MAE: **cumple**; (3) EuroLeague: **cumple**; (2) cobertura: media
0,815, pero el par Segunda → Tercera FEB (44 personas) queda en 0,759, por debajo de 0,78. En la regla fija también
fallan Segunda → Tercera (0,718) y Tercera → Segunda (0,777).

Ajustes por conocimiento elegidos con el examen: peso de la CVAE en los casos con Tercera FEB **w = 1,0** (rejilla
frente a `<m>_am` en esos casos: w 0 → 0 %, 0,25 → −2,4 %, 0,5 → −4,2 %, 0,75 → −5,3 %, 1 → −5,4 %) y anchura del
intervalo × **1,12**. En el corte 2023 esos casos ya van sólo con la v2 por la salvaguarda de temporadas (la Tercera
FEB tenía una sola temporada), así que w sólo actúa en el corte 2024.

No se añade un factor por cada sentido del par Segunda ↔ Tercera FEB: aprobaría la puerta por construcción y no
diría nada sobre el futuro.

### 4.2 Por grupo y métrica [DATO]
* Grupos (variante con conocimiento, frente a `<m>_am`): a la EuroLeague −1,2 %, resto de Europa −1,9 %, FEB −5,6 %,
  NBA/G League −2,5 %. Cobertura 0,805-0,822 en los cuatro.
* Métricas: mejora en **31 de 33**. Los que más: RAPM −22 %, RAPM ofensivo −17 %, % de tiros cortos −7 %, FTr −6 %,
  % en el aro −5 %, 3PAr −5 %, rebote ofensivo −4 %. Empata en TS%, PER, ORtg y USG% (0 % a −0,7 %) y empeora un
  poco en T3% (+0,3 %) y WS/40 (+0,2 %). En pts/100: error medio 3,74 frente a 3,79 de `<m>_am` y 5,15 de «mismo
  percentil».

### 4.3 Lectura [LECTURA]
* La combinación funciona como se esperaba: la CVAE sola no supera a la v2, pero las dos juntas sí, en los dos
  cortes, en todos los grupos y en casi todas las métricas. Incluso con la regla fijada de antemano (sin mirar el
  examen) la mejora es del 3 % y su IC excluye el 0.
* La ganancia es modesta en las métricas de nivel (PER, TS%, ORtg: casi empate) y grande en las de impacto en pista y
  perfil de tiro (RAPM, zonas). Ahí es donde la CVAE aporta información que la v2 no tiene.
* El único punto débil sigue siendo la incertidumbre en el escalón más bajo (Segunda ↔ Tercera FEB): el punto
  mejora, pero el intervalo se queda algo corto.

## 5. Ajuste final con todos los datos [DATO: `data/modelos/v3_1/`]
* Niveles 2025-26 re-anclados con ACB = 0 (CVAE corregida, `niveles.csv`; entre paréntesis, la v2):
  - pts/100: NBA +1,13 (+0,87); EuroLeague +0,20 (+0,14); EuroCup −0,21; BBL −0,28; FEC −0,41; Primera FEB
    −1,08 (−0,90); Segunda FEB −1,88 (−1,89); Tercera FEB −3,20 (−3,20).
  - PER: Tercera FEB −4,82 (−3,75).
  - La Tercera FEB ya no se degenera.
* Matriz cruzada (`traduccion_cruzada/`), con el efecto de quitar el doble conteo. Ejemplo, PER de Tercera FEB a
  Primera FEB: sd 0,12 con la covarianza conjunta, frente a 0,17 sumando varianzas marginales.
* Residuo de ciclo a → b → c → a: 0,07 DT de media (máximo 0,48) en los 455 triángulos de ligas de 2025-26.
* Dataset normalizado: las mismas filas que el v1 en 2020-21 a 2025-26 (+2 a +5 filas por cruces nuevos) y 5.911
  en 2026-27 (el v1 tenía 5.272, con datos hasta el 14-10).

## 6. Siguiente paso
Validar la regla (con los parámetros de conocimiento ya fijados) en el **examen limpio 2025-26 → 2026-27** cuando
la temporada en curso tenga suficientes minutos, sin volver a tocar nada. Si pasa la puerta, se activa
`version_activa: v3` en `configs/version.yaml` y se regenera aguas abajo (fases 4 y 5 del encargo).
