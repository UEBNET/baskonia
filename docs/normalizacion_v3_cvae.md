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

(se completa con los resultados: ver §5)

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

## 5. Validación (puerta de control)

(se completa con los resultados del examen)
