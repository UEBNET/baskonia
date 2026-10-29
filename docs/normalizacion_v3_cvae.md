# Normalización cruzada v3: CVAE jerárquica

**Código:** `bbnorm3/` · **Configuración:** `configs/normalization_v3.yaml` · **Selector de versión:**
`configs/version.yaml` (sigue en `v1` hasta que el CEO apruebe la v3) · **Salidas:** `data/modelos/v3/` ·
**Tests:** `tests/test_bbnorm3.py` · **Cambios:** [`CHANGELOG_v3.md`](CHANGELOG_v3.md)

```bash
python -m bbnorm3 elegir-k     # corte de selección 2022-23 → 2023-24: compara K (no mira el examen)
python -m bbnorm3 f0           # línea base F0: el grafo amortiguado actual con su covarianza completa
python -m bbnorm3 validar      # examen 2023 → 24 y 2024 → 25 (reentrena por corte) + puerta de control
python -m bbnorm3 lolo         # dejar fuera una liga
python -m bbnorm3 ajustar      # ajuste con todos los datos → data/modelos/v3/
```

Etiquetas: **DATO** = sale de un fichero o de un cálculo reproducible; **LECTURA** = interpretación de un dato;
**HIPÓTESIS** = supuesto del modelo que los datos no prueban por sí solos.

---

## 1. Qué problema resuelve

Para comparar a un jugador de la Tercera FEB con uno de la EuroLeague hay que saber cuánto «vale» cada liga. La
versión actual (v1/v2) lo hace en cuatro capas apiladas (algoritmo A → A amortiguado → A+B → A+B amortiguado) que no
comparten un modelo común. Tiene tres defectos (leídos en el código):

1. **Doble conteo de la incertidumbre del camino.** Al traducir entre dos ligas que no son la EuroLeague se suman las
   varianzas de sus dos niveles, var(δ_a) + var(δ_b). Si las dos cuelgan del mismo camino de puentes (Tercera →
   Segunda → Primera FEB → ACB → EuroLeague), esa parte común se cuenta dos veces. Lo correcto es
   **Var(δ_b − δ_a) = Σ_aa + Σ_bb − 2Σ_ab**.
2. **Capas sin modelo común.** El intervalo de una capa se aplica al punto de otra.
3. **EuroLeague fijada a 0** en cada temporada: su propia evolución no se ve.

La v3 es **un único modelo probabilístico**: un autoencoder variacional condicional (CVAE) jerárquico. Los niveles de
todas las competiciones, el «ADN» de cada jugador y la incertidumbre conjunta de todo salen del mismo ajuste.

## 2. El modelo, pieza a pieza

Notación: persona i, temporada t, competición-temporada c = (l, t), posición p (exterior / alero / interior), y ∈ ℝ³³ las
33 métricas transformadas y estandarizadas (25 de caja + 8 de pista), con máscara de faltantes (p. ej. la LNB no
tiene totales del rival), y v = σ²_m/n el ruido de muestra conocido (paso 1 del A, `bbmodel/suerte.py`).

| Pieza | Fórmula | Para qué |
|---|---|---|
| Latente del jugador | u_it ∈ ℝ^K (K = 8) | su capacidad y su estilo, **la misma en cualquier liga** |
| Posición relativa | r = (u_it − μ_c)/s_l | dónde está el jugador dentro de su competición |
| Prior por nivel | u_it ~ N(μ_c*, s²_l* I) | c* = competición con más minutos de esa persona-temporada |
| Niveles jerárquicos | μ_{l,t} − μ_{l,t−1} ~ N(0, κ²) · media de la liga ~ N(μ_escalón, τ²) · μ_escalón ~ N(0, 2²) | ligas con pocos puentes se acercan a su escalón; las temporadas se parecen entre sí |
| Gauge | Σ_c w_c μ_c = 0 (w ∝ filas) | **ninguna liga está fijada a 0**; «liga X = 0» es sólo una forma de presentar la salida |
| Entre temporadas | u_{i,t+1} = u_it + d(edad) + η, η ~ N(0, 0,03²) | el ADN apenas cambia; d(edad) es la curva de edad |
| Codificador amortizado | q(r ∣ y, máscara, v, liga, pos) por fila; las filas de la misma persona-temporada se combinan por **producto de expertos** | así entran los jugadores puente: un jugador en dos ligas tiene un solo u |
| Decodificador | ŷ = b_{l,t,p} + T_equipo + L r + (W₂ + V_l)·[γ_l ⊙ tanh(W₁ r) + β_l] | entorno de la liga-temporada-posición, efecto equipo-temporada (aleatorio), red común con FiLM por liga y cabezal residual por liga contraídos |
| Factor específico | ζ_{i,m} ~ N(0, ω²_m), común a todas las filas de la persona | lo que cada métrica tiene de propio y el latente común no recoge (p. ej. el TL% de un tirador) |
| Verosimilitud | y_{r,m} ~ N(ŷ_{r,m} + ζ_{i,m}, v_{r,m} + ψ_{l,m}) | heterocedástica: más minutos, menos ruido |
| Selección | cada persona-temporada puente pesa w = 1/p (logit de «ser puente» de `bbmodel/amortiguacion.py`) | quien cambia de liga no es una muestra al azar |
| Consistencia de ciclo | penalización ‖codificar(decodificar_b(r)) − r‖² con una liga b al azar | traducir a b y volver da lo mismo |

Se ajusta maximizando la ELBO (Adam, lote completo, 2.500 pasos) con 5 semillas fijas (**deep ensemble**). Las
varianzas del efecto equipo y del factor específico se estiman por bayes empírico (EM) durante el ajuste.

**HIPÓTESIS.** (i) El latente u es el mismo en todas las ligas (lo que cambia es la competición, no el jugador); (ii)
la selección de los puentes sólo depende de lo observable (IPW; no se modela la selección por inobservables); (iii) el
factor específico ζ viaja entero con el jugador al cambiar de liga.

### 2.1 Por qué los niveles quedan identificados
Si se desplaza el nivel μ_c y a la vez el latente de todos los jugadores que sólo juegan en c, nada cambia… salvo
para los **jugadores puente**, que tienen un único u en dos competiciones. Por eso el nivel relativo de dos
competiciones lo fijan sus puentes (directos o por cadenas), igual que en el grafo amortiguado; y una competición sin
puentes queda en su escalón con un intervalo ancho.

### 2.2 Posterior conjunta exacta de los niveles (`bbnorm3/niveles.py`)
Con el codificador y el decodificador ya entrenados, cada fila aporta un experto gaussiano. Junto con el prior por
nivel, las transiciones y la jerarquía, todo es lineal-gaussiano en (u, μ, μ_escalón) y, como las precisiones son
diagonales, se separa en K sistemas dispersos que se resuelven exactamente. De ahí sale la **covarianza conjunta** de
todos los μ_c (Σ_aa, Σ_bb, Σ_ab de cualquier par) y la del latente de cada jugador con el nivel de destino.

### 2.3 Traducción de un jugador y matriz cruzada (`bbnorm3/prediccion.py`, `bbnorm3/traduccion.py`)
* Jugador de a a b: r_b = (u + d(edad) + η − μ_b)/s_b; valor = E[g(r_b, b, p)] + ζ, integrando por Monte Carlo la
  posterior completa (u − μ_b con su covarianza, η, equipo, ψ y, si se predice un valor observado, el ruido σ²/n).
* Nivel de c en la métrica m (en DT de capacidad de la competición de referencia R):
  δ_{c,m} = media_p[g_m((μ_c − μ_R)/s_R, R, p) − g_m(0, R, p)]/τ_{R,m}; sólo depende de μ_c − μ_R (invariante al gauge).
* **Matriz cruzada** T_m(a → b) = δ_{a,m} − δ_{b,m}, con Var = J_a Σ̃_aa J_aᵀ + J_b Σ̃_bb J_bᵀ − 2 J_a Σ̃_ab J_bᵀ
  (Σ_aa + Σ_bb − 2Σ_ab en el latente). Los ficheros guardan también la sd que daría sumar varianzas marginales, para
  ver el tamaño del doble conteo.
* Incertidumbre total = dentro de cada red (posterior) + entre las 5 redes (ensemble).

### 2.4 Recalibración conforme (`bbnorm3/examen.py`)
Los intervalos se recalibran por cuantiles con datos que no son del examen: para el corte t se usan las predicciones
del modelo ajustado con ≤ t−1 sobre los cambios t−1 → t. Residuo estandarizado e = (y − centro)/sd; factor
κ = q80(|e|)/z₀,₉ por métrica, con un ajuste por grupo origen → destino (a la EuroLeague, FEB, NBA/G League, resto
de Europa) si el grupo tiene ≥ 30 personas. Para el corte 2024 la calibración usa los cambios 2023 → 2024 predichos
con ≤ 2023 (que son los casos del corte 2023, no los del 2024).

## 3. Decisiones tomadas con el corte de selección (2022-23 → 2023-24)

El encargo pide elegir K «solo con el corte 2022-23 → 2023-24, sin mirar el examen». Ese corte se usó para **todas**
las decisiones de diseño. Como el corte no tiene líneas base versionadas, se recalcularon A, el amortiguado y B con
≤ 2022 con los mismos procedimientos (`bbmodel validar`, `amortiguar --validar`, `validar-b`). Resultados en
`data/modelos/v3/validacion/seleccion_2022.csv` (MAE medio de la v3 relativo a `<m>_am`, 1-3 semillas):

**DATO** (`seleccion_2022.csv`; 7.653 predicciones, 33 métricas; «v3/am» = MAE medio de la v3 relativo a `<m>_am`,
media de las 33 métricas; negativo = mejor):

| Variante | Semillas | v3/am | a la EuroLeague | FEB (13 personas) | resto de Europa |
|---|---|---|---|---|---|
| Sin factor específico, η = 0,15 | 1 | +3,0 % | +1,8 % | +26 % | +2,6 % |
| Sin factor específico, η = 0,03 | 1 | +2,5 % | +0,3 % | +46 % | +1,1 % |
| K = 4 | 1 | +10,3 % | +5,8 % | +57 % | +10,8 % |
| K = 12 | 1 | +3,0 % | −0,1 % | +44 % | +2,7 % |
| Sin factor específico, ensemble | 3 | +2,9 % | −0,5 % | +42 % | +2,4 % |
| Inferencia semi-amortizada (refinada) | 3 | +4,2 % | 0,0 % | +64 % | +2,0 % |
| **Con factor específico** ζ, η = 0,03 | 3 | +0,5 % | −2,5 % | +43 % | −0,6 % |
| Con ζ, η = 0,08, acotado al soporte ← **elegida** | 2 | −0,1 % | −2,6 % | +33 % | 0,0 % |
| Con ζ, η = 0,15, acotado al soporte | 2 | +0,2 % | −2,6 % | +27 % | −0,1 % |
| Con ζ, 4.000 pasos (sin acotar) | 2 | +6,1 % | −3,7 % | +152 % | −0,2 % |

**LECTURA.**
* La v3 sin factor específico ya era **mejor que cada modelo de la v2 por separado** (en el mismo corte: A +3,9 %,
  B +6,2 %, A amortiguado +5,3 % frente a `<m>_am`). `<m>_am` gana porque promedia dos modelos distintos (A y B).
* Lo que le faltaba a la v3 es lo que aporta el A: la parte de cada métrica que es propia del jugador. Un latente
  común de 8 dimensiones no recoge, por ejemplo, el TL% de un tirador. El **factor específico persona × métrica**
  (unicidad del análisis factorial) recupera unos 2,5 puntos.
* K = 4 se queda corto; K = 12 no mejora a K = 8 → **K = 8**.
* El grupo FEB del corte de selección son 13 personas (en 2022-23 sólo existe la Primera FEB) y lo domina un caso
  extremo: un pívot de 2,20 m de Primera FEB al que el decodificador, sin freno, llevaba en la ACB a un TS% > 100. De
  ahí el **acotado al soporte**: el valor traducido no puede salir del rango observado en la liga de destino ± 0,25
  DT. Con tan pocos casos, este corte no permite afinar la FEB (ver limitaciones).

## 4. Salidas (`data/modelos/v3/`)

| Fichero | Contenido |
|---|---|
| `normalizado/<temporada>.csv.gz` | mismo esquema que `data/modelos/normalizado/<temporada>.csv` (mismas columnas, mismo orden) + columnas `<m>_v3`, `_v3_lo`, `_v3_hi` (80 %), `_v3_sd`, `_v3_pctel`, `<m>_v1`, `<m>_am_v1`, `fuente_v3`. Las columnas de estimación final (`<m>`, `_lo`, `_hi`, `_pctel`, `<m>_am`, `_am_lo`, `_am_hi`, `_am_pctel`) llevan la v3; las originales se conservan con sufijo `_v1`. Comprimido para no inflar el repositorio |
| `niveles.csv` | nivel por competición-temporada y métrica, con el gauge en la media y re-anclado con ACB = 0, sd y lo80/hi80 |
| `niveles_covarianza.csv.gz` | covarianza conjunta (gauge en la media) del índice de nivel entre todas las competiciones-temporada |
| `traduccion_cruzada/<m>.csv` | T_m(a → b) de todos los pares de la temporada de referencia: media, sd, lo80, hi80 y la sd con varianzas marginales sumadas |
| `puentes.csv` | grafo de puentes (personas con ≥ 150 min en ambas ligas, misma temporada o consecutivas) |
| `ciclo.csv` | residuo de ciclo a → b → c → a por triángulo de ligas (en DT de la escala de trabajo) |
| `validacion/` | examen, líneas base, calibración, puerta de control, dejar fuera una liga, elección de K |
| `resumen.json` | configuración, escalas por liga, ω² del factor específico, ponderación de selección |

## 5. Validación (puerta de control): **NO SE CUMPLE**

Examen idéntico al de la v1/v2: se ajusta con ≤ t y se predice t+1 de quien cambia de liga con ≥ 300 minutos en
ambas, en los cortes 2023 → 24 y 2024 → 25. La CVAE se **reentrena en cada corte** (5 semillas). Son 22.254
predicciones de 722 persona-cortes, emparejadas caso a caso con las líneas base. Ficheros en
`data/modelos/v3/validacion/` (`puerta.json`, `resumen_metricas.csv`, `casos.csv.gz`, `diagnostico_por_corte.json`).

### 5.1 Criterios del CEO [DATO]
| Criterio | Resultado | ¿Cumple? |
|---|---|---|
| 1. MAE medio mejor que `<m>_am`, con un IC 95 % bootstrap por persona de la diferencia que excluya el 0 | **+12,6 %** (IC +8,2 % a +16,9 %): **peor** | **No** |
| 2. Cobertura del 80 % entre 0,78 y 0,85 en grupos con ≥ 30 casos | media 0,790; 2 de los 5 pares origen → destino con ≥ 30 personas fuera de rango (Segunda → Tercera FEB 0,71; Tercera → Segunda FEB 0,65; en 2023 sólo, 0,34) y 11 de 33 métricas fuera | **No** |
| 3. No empeorar en las llegadas a la EuroLeague | +1,7 % (IC −1,1 % a +4,8 %) | **No** (empate estadístico, pero la estimación es peor) |

Otras comparaciones (media de 33 métricas): v3 frente a «mismo percentil» −0,5 %; frente a F0 +9,1 %. Como
referencia, `<m>_am` frente a «mismo percentil» −11,3 % y F0 frente a `<m>_am` +3,3 %. Cobertura del 80 %: v3 0,790
(recalibrada; 0,833 sin recalibrar), `<m>_am` 0,842, F0 0,832.

### 5.2 Por corte y grupo [DATO]
| Corte | v3 frente a `<m>_am` (IC 95 %) | A la EuroLeague | FEB | Resto de Europa | NBA / G League | Cobertura v3 / `<m>_am` / F0 |
|---|---|---|---|---|---|---|
| 2023 → 24 | **+29,6 %** (+22,3 %, +37,4 %) | +5,1 % | **+80,0 %** | +2,7 % | +0,2 % | 0,737 / 0,844 / 0,832 |
| 2024 → 25 | **−5,0 %** (−6,5 %, −3,4 %) | +0,1 % | −9,2 % | −2,5 % | −3,4 % | 0,845 / 0,839 / 0,832 |

Cobertura por grupo en 2024 (v3): EuroLeague 0,757, resto de Europa 0,803, FEB 0,988 (demasiado ancha), NBA/G League
0,773. Por métrica (los dos cortes): la v3 mejora en RAPM (−17 %), RAPM ofensivo (−7 %), % de tiros cortos (−8 %),
en el aro (−4 %) y de media distancia (−4 %); queda igual en triples de esquina y canastas asistidas (±1 %), y empeora en el resto (+5 % a +39 %; tapones y rebote, los que más).

### 5.3 Diagnóstico del fallo [DATO + LECTURA]
* **DATO.** En el corte 2023, la escala latente de la Tercera FEB sale s = 15,6, frente a 0,3-2,2 en las demás ligas
  (2022: 0,35-3,4; 2024: FEB3 0,40). Su nivel en pts/100 queda en −11,4 DT frente a −3,3 del amortiguado (PER −13,2
  frente a −3,7). A los 43 jugadores que suben de Tercera a Segunda FEB la v3 les sobrestima el rendimiento (sesgo
  +10 pts/100, +12 PER, +13 TS%; con `<m>_am`, +1 a +3) y su intervalo sólo cubre el 34 %.
* **LECTURA.** Con s enorme, la posición relativa r = (u − μ)/s de un jugador de la Tercera FEB apenas depende de su
  latente: la red «desconecta» la liga de sus 9 puentes de esa temporada y su nivel queda sin anclar. El prior de la
  escala (log s ~ N(0, 0,3²)) cuesta unos pocos nats frente a la verosimilitud de miles de filas, así que no lo
  impide. En 2023-24 la Tercera FEB tiene una sola temporada (sin transiciones que la aten) y muy pocos puentes del
  mismo año. En 2024, con dos temporadas FEB y sus transiciones, el defecto no aparece y la v3 mejora a `<m>_am`.
* **Por qué no se vio antes.** En el corte de selección (2022-23) no hay ni Segunda ni Tercera FEB: el defecto no se
  podía observar sin mirar el examen.

### 5.4 Lo que no se ejecutó
* **Dejar fuera una liga** (`python -m bbnorm3 lolo`): implementado y no ejecutado. La puerta ya falla por el
  criterio 1, y son unos 75 minutos de cálculo que no cambian la decisión.
* **Ajuste final y salidas** (`python -m bbnorm3 ajustar`: `niveles.csv`, `traduccion_cruzada/`, `normalizado/`…):
  implementado y no ejecutado. Con la puerta sin pasar no tiene sentido publicar niveles ni traducciones de un modelo
  que no se va a usar.
* Fases 4 y 5 (índice L, contexto, escalas, estilos, simulador v3, datos del artifact): **no se ejecutan**, tal como
  manda el encargo cuando la puerta no se cumple.

## 6. Propuesta v3.1 (pendiente de aprobación)

1. **Escala por liga acotada o fija** (s_l = 1, o |log s_l| ≤ 0,5 con una parametrización acotada en lugar de un prior
   débil). Ya está implementado como opción: `prior.escala_por_liga: false`. Hay un diagnóstico **post hoc** en el
   corte 2023 en `validacion/diagnostico_posthoc/` (ver el informe). **No vale como examen**, porque la variante se
   eligió después de ver el resultado.
2. **Examen limpio para la v3.1.** Como los cortes 2023 y 2024 ya se han visto, la v3.1 debería validarse en un corte
   nuevo: 2025-26 → 2026-27 cuando la temporada en curso tenga suficientes minutos (≥ 300 por jugador, hacia
   enero-febrero de 2027). Otra opción es que el CEO acepte, de forma explícita, reutilizar los cortes actuales
   sabiendo que hay sesgo de selección.
3. **Recalibración por grupo más fina** (en 2024, la FEB sale demasiado ancha y la EuroLeague y la NBA demasiado
   estrechas): un factor por grupo origen → destino estimado con su propio corte anterior.

## 7. Limitaciones
* La IPW sólo corrige la selección por lo observable (no por inobservables).
* El factor específico ζ viaja entero con el jugador (sin contracción por distancia de nivel).
* El acotado al soporte impide extrapolar fuera del rango observado en la liga de destino: un jugador
  verdaderamente excepcional queda recortado al máximo observado ± 0,25 DT.
* El efecto equipo y el factor específico son estimaciones puntuales con su varianza a posteriori aproximada (no se
  integra la incertidumbre de ω² ni de σ²_T).
