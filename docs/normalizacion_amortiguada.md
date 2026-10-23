# Normalización amortiguada del salto de nivel

**Para qué sirve.** El algoritmo A ([`algoritmo_A.md`](algoritmo_A.md)) lleva cualquier jugador a la vara de la
EuroLeague con una recta por liga (`a = m_l + s_l·z`). Con las tres ligas FEB el salto hasta la EuroLeague es muy
grande y casi todo indirecto (Tercera → Segunda → Primera → ACB → EuroLeague). Una recta única extrapola sin freno a
los mejores de las ligas lejanas y no dice cuánta incertidumbre se acumula en el camino. Esta capa conserva los pasos
1-2 del A (quitar la suerte; puesto en su liga-temporada-posición; ψ, deriva por edad y escala s) y cambia el
paso 3 (el nivel de cada competición) por seis piezas.

**Código:** `bbmodel/amortiguacion.py` · **Configuración:** `configs/normalization.yaml` ·
**Ejecutar:** `python -m bbmodel amortiguar` (tras `python -m bbmodel ajustar`) ·
**Validar:** `python -m bbmodel amortiguar --validar` · **Diagnóstico del esquema lineal:**
`python -m bbmodel amortiguar --diagnostico <parametros.json>` · **Resultados:** `data/modelos/normalizacion_amortiguada/`

---

## 1. Las seis piezas

Notación: c = (liga, temporada) es una **competición-temporada**; δ_c su nivel en desviaciones típicas (DT) de
capacidad de la EuroLeague (δ = 0 en la EuroLeague de todas las temporadas, como en el A); z* = z/(1 + v + ψ) la
capacidad estimada del jugador dentro de su liga-temporada-posición (pasos 1-2 del A).

### 1.1 Encadenamiento jerárquico (grafo de competiciones)
* **Nodos**: las competiciones-temporada. **Aristas**: cada pareja de nodos con al menos 3 jugadores puente
  (≥ 150 minutos en las dos; a la vez en la misma temporada o al cambiar de liga de t a t+1, descontando la deriva
  por edad del A).
* Cada puente i entre el nodo de menor nivel x y el de mayor nivel y mide
  `δ_x − δ_y ≈ g_y(z_y) − g_x(z*_x) − d(edad)·Δt`, con g la parte del jugador (pieza 3-4). El lado x se toma sin
  suerte (z*, su esperanza dado lo observado) y el y tal cual (medida insesgada), lo que evita el sesgo de
  atenuación. La arista es la media ponderada por precisión (y por los pesos de selección, pieza 5), con varianza
  «sándwich» (el máximo de la del modelo y la empírica).
* **Nivel de cada nodo** = mínimos cuadrados ponderados del grafo con la EuroLeague fija en 0. En una cadena
  equivale a **sumar los desfases y sumar las varianzas**; con dos caminos independientes, a **combinarlos por
  precisión inversa** (como resistencias en serie y en paralelo), y lo generaliza a caminos que comparten aristas.
  `league_offsets.csv` guarda también el camino de mayor precisión de cada nodo (`camino`).

### 1.2 Contracción bayesiana parcial por escalón
`δ_c ~ N(μ_escalón(c), τ²)`, con escalones fijados en el YAML: élite (EuroLeague, NBA), doméstica alta (ACB, LBA,
BBL, LNB, BSL, GBL), copas europeas (EuroCup, BCL, FEC), desarrollo (G League), Primera FEB, Segunda FEB, Tercera
FEB. Las medias de escalón μ son **nodos latentes del grafo** (cada competición-temporada se une a su μ con una
arista δ_c − μ = 0 de varianza τ²; μ ~ N(0, 2²), previa débil que sólo pesa en un escalón sin puentes), de modo
que la posterior conjunta **integra la incertidumbre de μ**: las temporadas de Tercera FEB comparten el mismo
camino de puentes hasta la EuroLeague, y esa incertidumbre común no se reduce por tener cuatro temporadas. τ² se
estima por **bayes empírico con EM** (τ² = media de E[(δ_c − μ)²]). Una temporada con pocos puentes (p. ej.
2026-27, en curso) se acerca a su escalón; una con muchos apenas se mueve.

> Primera versión (descartada): μ como estimación puntual (EM clásico). Daba desviaciones típicas de 0,06-0,07 al
> nivel de Tercera FEB a través de 4-5 aristas, porque trataba la media del escalón como conocida.

### 1.3 Mapeo de cuantiles monótono (forma)
En vez de sólo desplazar, la parte del jugador es `g_l(z) = λ(d_l)·F_l(s_l·z)`, con F_l monótona creciente, F(0) = 0 y
pendiente 1 fuera de la zona con puentes. F_l se estima por liga y métrica con sus puentes: tramos de cuantiles
(7), media de cada tramo contraída hacia la recta con el peso de 30 puentes, regresión isotónica (PAVA) y
interpolación monótona PCHIP. Con menos de 40 puentes la liga usa la recta. F sólo recoge **curvatura**: la
pendiente global la pone λ.

### 1.4 Compresión de colas / transferibilidad λ(d)
`θ_ref = μ_origen + λ(d)·(θ_traducido − μ_origen)`, con μ_origen = δ_c (el nivel medio de la competición de origen
en la vara de referencia), λ(0) = 1 y λ decreciente en la distancia de nivel d_l = |mediana con signo de δ (media de sus temporadas) en las 8
métricas de nivel (PER, GmSc/40, WS/40, ORtg, DRtg, pts/100, TS%, eFG%)|.
* **Medición empírica**: para cada liga y métrica, λ̂ = pendiente del valor del puente en la otra competición (vara
  de referencia) sobre su valor traducido s·z*, con efecto fijo por arista (cada pareja de competiciones conserva su
  desfase). Es la «regresión a la media» que se ve en los puentes, más allá de la que ya quita el paso 1.
* **Forma**: constante (λ = 1), exponencial `exp(−d/δ₀)` o logística normalizada
  `(1 + e^{−d₀/w})/(1 + e^{(d−d₀)/w})`, ajustadas por mínimos cuadrados ponderados (con heterogeneidad entre ligas) y
  **elegidas por error dejando fuera una liga**; a igualdad, la más simple. Suelo λ ≥ 0,2.
* **Decisión**: μ_origen es el nivel de la competición de origen, no la media de la EuroLeague (0). Con la media de la
  EuroLeague, un jugador medio de Tercera FEB se acercaría a la EuroLeague tanto más cuanto más lejos esté su liga,
  contradiciendo los desfases medidos con puentes. Lo que se comprime es la distancia del jugador a la media de su
  propia competición (las colas), que es lo que los puentes muestran que no se transfiere entero.

### 1.5 Sesgo de selección de los puentes (ponderación por probabilidad inversa)
Quien cambia de liga no es una muestra al azar. Un logit de «ser puente» (≥ 150 min en otra competición la misma
temporada o la siguiente) con su nivel en su liga (media con signo de z* en las métricas de nivel, y su cuadrado),
edad (y su cuadrado; indicador de edad desconocida), log-minutos, liga y temporada da p; cada puente pesa
`√(w_x·w_y)`, `w = 1/p` recortado a los percentiles 1-99 y normalizado. La tabla guarda el nivel sin pesos
(`media_sin_ipw`) para medir el efecto. La alternativa de tipo Heckman (selección por inobservables) no se ha
implementado: con IPW sólo se corrige la selección por lo observable.

### 1.6 Unidades
Todo se trabaja en z de capacidad dentro de cada liga-temporada-posición: las métricas por 100 posesiones no
dependen de la duración del partido y las «por 40'» se comparan por su puesto en la liga, no por su número. La
duración del partido sólo cambia la exposición (y por tanto el ruido): `exposicion_posesiones` usa las posesiones en
pista y, si faltan, minutos × ritmo / 40 (FIBA) o 48 (NBA, G League). El valor final se expresa en la EuroLeague
2025-26 (40 minutos).

### Traducción de un jugador
```
θ   = δ_c + λ(d_l) · F_l(s_l · z*)
var = var(δ_c) + (λ s F′)² · v_post + (λ F)² · se(s)²
valor EuroLeague = μ_EL,pos + τ_EL,pos · θ   (deshaciendo la transformación de la métrica)
```
La incertidumbre del nivel de la competición (que crece con la longitud del camino de puentes) entra en el
intervalo de cada jugador.

## 2. Salidas

| Fichero | Contenido |
|---|---|
| `league_offsets.csv` | competición × temporada × métrica: `media`, `sd`, `lo90`, `hi90`, `n_puentes`, `camino`, `escalon`, `media_encadenada` (sólo grafo, sin contracción), `media_lineal_A` (m del A), `media_sin_ipw`, `lambda`, `distancia_d`, `mu_escalon`, `tau_escalon`, `forma_no_lineal` |
| `traducciones/<temp>.csv` | por jugador-liga-temporada y métrica: `<m>_am`, `<m>_am_lo`/`_am_hi` (80 %), `<m>_am_pct`, `<m>_am_a`, `<m>_am_sd` |
| `lambda_por_liga.csv` | λ̂ por liga y métrica (con su varianza y puentes) |
| `resumen.json` | forma elegida de λ(d) y parámetros, λ y d por liga, τ y μ de los escalones, logit de selección, efecto medio de los pesos, mapeos no lineales |
| `ejemplos_puentes.csv` | jugadores puente reales: valor en origen y destino, traducción lineal y amortiguada |
| `diagnostico_antes*.csv` | esquema lineal (A) antes de la amortiguación: desfase por liga y métrica, error, anchura del IC90 y puentes por pareja de ligas |
| `validacion*.csv` | examen temporal (A lineal frente a amortiguado, mismos casos) y dejando fuera una liga |

En el **dataset normalizado** (`python -m bbmodel dataset-normalizado`) se añaden, sin tocar las columnas
anteriores: `<m>_A_am` (A amortiguado), `<m>_am` (A+B de siempre más la corrección de la amortiguación del A en la
escala transformada), `<m>_am_lo`/`<m>_am_hi` (80 %, con la anchura del A amortiguado) y `<m>_am_pctel`. El índice
de nivel **L**, el contexto (`bbmodel contexto`) y las escalas ±100 (`bbmodel escalas`: nivel y RAPM) leen `<m>_am`
cuando `configs/normalization.yaml → usar_amortiguado` lo indica (activado).

## 3. Resultados (octubre de 2026; 15 ligas, crosswalk con umbral 0,75)

Etiquetas: **[verificado]** = salida de los ficheros citados; **[decisión]** = elección razonada.

### 3.1 Antes: el esquema lineal del A con las FEB (diagnóstico) [verificado]
`diagnostico_antes*.csv` (A ajustado con las 15 ligas, el crosswalk 0,75 y SIN la corrección de σ²). Puentes =
personas con ≥ 150 min en las dos ligas, la misma temporada o consecutivas:

| Pareja | Personas | (misma temporada / consecutivas) |
|---|---|---|
| Segunda FEB – Tercera FEB | 195 | 21 / 190 |
| Primera FEB – Segunda FEB | 104 | 6 / 103 |
| ACB – Primera FEB | 42 | 4 / 42 |
| Primera FEB – FEC / EuroCup / BBL / GBL / G League | 8 / 7 / 7 / 6 / 6 | |
| EuroLeague – Primera FEB | 2 | 0 / 2 |
| Segunda o Tercera FEB – EuroLeague | 0 | |
| (referencia) ACB – EuroLeague | 170 | 138 / 144 |

Tercera y Segunda FEB no tienen ningún puente directo con la EuroLeague: su nivel sale de la cadena.

### 3.2 Nivel por competición: antes y después [verificado]
Mediana con signo (DRtg invertido) en las 8 métricas de nivel, en DT de capacidad EuroLeague; «después» = mediana
de las temporadas 2020-21 a 2025-26 de `league_offsets.csv` (variante elegida); IC90 = anchura mediana.

| Competición | Antes (A lineal) | IC90 antes | Después (amortiguado) | IC90 después | Puentes por temporada (mediana) |
|---|---|---|---|---|---|
| NBA | +0,13 | 0,31 | +0,56 | 0,50 | 163 |
| EuroLeague | 0 | 0 | 0 | 0 | 368 |
| ACB | −0,40 | 0,19 | −0,23 | 0,26 | 384 |
| LNB | −0,50 | 0,21 | −0,32 | 0,26 | 255 |
| BSL | −0,77 | 0,30 | −0,34 | 0,32 | 173 |
| G League | −0,52 | 0,24 | −0,35 | 0,46 | 236 |
| GBL | −0,92 | 0,28 | −0,41 | 0,34 | 130 |
| EuroCup | −0,67 | 0,19 | −0,42 | 0,27 | 329 |
| LBA | −0,83 | 0,25 | −0,45 | 0,30 | 233 |
| BBL | −0,91 | 0,27 | −0,53 | 0,30 | 241 |
| BCL | −1,14 | 0,35 | −0,57 | 0,31 | 265 |
| FEC | −1,82 | 0,56 | −0,75 | 0,36 | 135 |
| Primera FEB | −1,02 | 0,34 | −1,19 | 0,85 | 59 |
| Segunda FEB | −1,81 | 0,39 | −2,32 | 0,90 | 109 |
| Tercera FEB | −3,14 | 0,41 | −3,46 | 0,98 | 81 |

Lectura: (i) las ligas con muchos puentes se acercan a la EuroLeague (el A lineal, con una recta común a todas las
temporadas y el EM conjunto, abría más el abanico; la red B ya daba distancias parecidas a las nuevas); (ii) las FEB
quedan **algo más lejos** y, sobre todo, con un intervalo **2-2,5 veces más ancho**: ahora la incertidumbre se
acumula por el camino (Tercera FEB 2024-25 en PER: −3,96 ± 0,23, camino
`feb3:2024-25 → feb2:2023-24 → feb1:2024-25 → acb:2023-24 → euroleague`). El A lineal daba a Tercera FEB un IC90 de
0,41 con cero puentes directos. En pts/100: Primera FEB −0,87 → −1,00 (sd 0,14), Segunda −1,81 → −2,09 (0,18),
Tercera −3,28 → −3,33 (0,21); 2026-27 (en curso) sin puentes: nivel del escalón (sd ≈ 0,25-0,29).

### 3.3 λ(d) (compresión de colas) [verificado + decisión]
* λ̂ por liga (mediana entre métricas, `lambda_por_liga.csv`): ACB 1,22 · GBL 1,24 · BCL 1,14 · BBL, LBA, LNB 1,13 ·
  BSL 1,10 · EuroCup 1,09 · FEC 1,08 · Primera FEB 1,06 · G League 0,97 · Tercera FEB 0,89 · NBA 0,87 · Segunda FEB
  0,84. Por encima de 1 en casi todas: los puentes **no** muestran regresión a la media más allá de la que ya quita
  el paso 1 del A (z* encoge, si acaso, de más). Sólo en Segunda/Tercera FEB, NBA y en RAPM (λ̂ ≈ 0,2-0,4 en
  casi todas las ligas) se ve compresión.
* Error dejando fuera una liga (variante elegida, sin mapeo): constante 0,2272 · exponencial (δ₀ = 30,3) 0,2284 ·
  logística 0,2509 → **λ = 1 (constante)**. Con el mapeo monótono activo gana la exponencial (δ₀ ≈ 7-8; λ Tercera
  FEB ≈ 0,67-0,70), pero esa combinación predice peor (3.5). **[decisión]** Los puentes no identifican una λ(d)
  decreciente con claridad: se usa la forma más simple; λ(d) exponencial queda implementada y se activa con la
  variante `completo`.

### 3.4 Sesgo de selección [verificado]
Logit de «ser puente» (9.103 de 39.647 filas): probabilidad media 0,55 en los puentes y 0,13 en el resto; coeficientes
(por unidad): nivel +0,30 por DT, log-minutos +1,08, edad −0,011 por año (más liga y temporada). Efecto de los pesos
sobre los niveles: 0,033 DT de media; 0,10 en Tercera FEB, 0,085 en Segunda, 0,049 en Primera, 0,02-0,04 en el resto.

### 3.5 Validación sin fuga temporal [verificado]
Mismos casos que `bbmodel validar` (ajuste con ≤ t, predicción de t+1 de quien cambia de liga con ≥ 300 min; 722
casos por métrica; 11.381 + 11.108 predicciones). La variante se **elige con el corte 2023-24 → 2024-25** y se
**confirma con el 2024-25 → 2025-26** (`validacion_variantes.csv`; MAE amortiguado / MAE lineal, media de 33 métricas):

| Variante | Corte 2023 | Corte 2024 | Cobertura 80 % (2023 / 2024; lineal 0,831 / 0,828) |
|---|---|---|---|
| completo (mapeo + λ + IPW) | 1,0108 | 1,0103 | 0,832 / 0,832 |
| **sin_mapeo (λ elegida = constante) + IPW** ← elegida | **1,0062** | **0,9997** | 0,843 / 0,839 |
| grafo + contracción + IPW | 1,0062 | 0,9997 | 0,843 / 0,839 |
| grafo + contracción sin IPW | 1,0064 | 0,9986 | 0,839 / 0,837 |

Con la variante elegida (`validacion.csv`, los dos cortes): MAE mejor en 13 de 33 métricas (orapm −6,5 %, RAPM −3,7 %,
eFG% −2,7 %, tapones −2,2 %, DRtg −1,8 %, BLK% −1,4 %, WS/40 −1,1 %, TS% −0,9 %), peor en pts/100 (+4,4 %), USG%
(+3,2 %), PER (+3,1 %), GmSc/40 (+2,7 %) y ±1-1,7 % en el resto; llegadas a la EuroLeague 0,4-1,4 % mejor. Cobertura
media del intervalo del 80 %: 0,829 (lineal) → 0,841 (amortiguado). El empeoramiento en pts/100 viene sobre todo de
Segunda ↔ Tercera FEB (sesgo −4,0 en quien baja a Tercera): el desfase amortiguado entre las dos es menor que el del
A. **Conclusión: la amortiguación no mejora la predicción puntual en conjunto (empate, ±0,6 %); lo que aporta es
nivel por temporada, intervalos honestos que crecen con la cadena y mejor calibración.**

**Dejar fuera una liga** (`validacion_lolo.csv`; se quitan todas las aristas de la liga y su nivel sale sólo del
escalón): error medio 0,147 DT con la jerarquía frente a 0,315 sin ella (A sin puentes = nivel de la EuroLeague) en
las ligas de escalones con varias ligas, cobertura del IC90 0,88. En escalones de una sola liga (Primera, Segunda,
Tercera FEB, G League, NBA) el escalón no tiene otra información: error = el de no tener jerarquía (0,83) y el
intervalo es enorme (sd ≈ 2), lo que es correcto (cobertura 0,95).

### 3.6 Jugadores puente reales (`ejemplos_puentes.csv`, pts/100) [verificado]
Capacidad en la vara EuroLeague (DT) en la temporada de origen y en la de destino, lineal → amortiguado:

| Jugador | Origen → destino | pts/100 origen → destino | a origen | a destino |
|---|---|---|---|---|
| Marin Maric | Primera FEB 2022-23 → ACB 2023-24 | 35,5 → 31,7 | 0,85 → 0,69 | 0,88 → 0,96 |
| Yunio Barrueta | Primera FEB 2023-24 → ACB 2024-25 | 31,2 → 23,1 | 1,32 → 1,21 | 0,09 → 0,22 |
| Gonzalo Corbalán | Primera FEB 2024-25 → ACB 2025-26 | 31,7 → 29,1 | 0,32 → 0,20 | 0,41 → 0,56 |
| Lionel Kouadio | Segunda FEB 2023-24 → Primera FEB 2024-25 | 29,6 → 29,4 | −0,25 → −0,57 | 0,04 → −0,08 |
| Isaac Vázquez | Tercera FEB 2023-24 → Segunda FEB 2024-25 | 25,1 → 24,0 | −1,97 → −2,00 | −1,25 → −1,57 |
| Daniel Arjol | Tercera FEB 2024-25 → Segunda FEB 2025-26 | 21,8 → 19,8 | −2,54 → −2,69 | −1,87 → −2,11 |

En los pares FEB → superior la diferencia media |a origen − a destino| baja con la amortiguación (Primera FEB → ACB
0,52 → 0,44; Segunda → Primera 0,40 → 0,37; Tercera → Segunda 0,64 → 0,58); en EuroCup → EuroLeague sube (0,35 →
0,45) y en ACB → EuroLeague casi no cambia (0,57 → 0,61). (No descuenta la deriva por edad: es una comparación
descriptiva, el examen formal es 3.5.)

### 3.7 Integración [verificado]
* `dataset-normalizado`: columnas `<m>_A_am`, `<m>_am`, `<m>_am_lo/_hi`, `<m>_am_pctel` (las anteriores no cambian);
  39.647 filas en 7 temporadas.
* Índice L, contexto y escalas ±100 leen `<m>_am` (`usar_amortiguado` en el YAML). L medio ponderado por minutos en
  2025-26 (`contexto/por_jugador_liga.csv`): NBA +0,72, EuroLeague +0,46, ACB +0,32, BSL +0,24, EuroCup +0,21,
  LBA +0,21, G League +0,20, GBL +0,19, BCL +0,17, LNB +0,07, FEC +0,05, BBL +0,04, Primera FEB −0,39, Segunda FEB
  −1,08, Tercera FEB −1,75.

## 4. Limitaciones
* **pts/100, USG% y PER** predicen algo peor que el A lineal en el examen temporal; si se usan para fichar en la
  cadena FEB, mirar también `<m>_A`.
* El lado «x» de cada puente usa z* del paso 1 del A (encogido con 1/(1 + v + ψ)); λ̂ > 1 en la mayoría de ligas
  sugiere que ese encogimiento es algo excesivo para los puentes (supuesto no corregido).
* DRtg individual encadena desfases erráticos (muy dependiente del equipo; τ del escalón 0,48 frente a 0,10-0,24 en
  las demás): por eso la distancia d usa la mediana de las métricas de nivel.
* Sólo se corrige la selección por lo observable (IPW); no hay modelo de tipo Heckman.
* Los puentes de una misma persona en varias aristas se tratan como independientes (varianza algo optimista).
