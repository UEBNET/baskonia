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
FEB. μ y τ² se estiman por **bayes empírico con un EM exacto** sobre el modelo conjunto (grafo + previa); μ_escalón
tiene una hiperprevia débil N(media global, 2²) que sólo pesa en un escalón sin puentes. Una temporada con pocos
puentes (p. ej. 2026-27, en curso) se acerca a su escalón; una con muchos apenas se mueve.

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
