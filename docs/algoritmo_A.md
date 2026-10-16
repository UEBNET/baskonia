# Algoritmo A — Traductor por puestos + tipo de cambio

**Para qué sirve.** Poner a todos los jugadores, jueguen donde jueguen, en la misma vara: la de la
**EuroLeague** (temporada de referencia 2025-26). Para cada jugador y cada métrica da su valor
equivalente en la EuroLeague, un intervalo del 80 % y su percentil entre los jugadores de EuroLeague
de su posición. También da una proyección para la temporada siguiente, que tiene en cuenta la edad.

**Código:** `bbmodel/` · **Ejecutar:** `python -m bbmodel ajustar` (≈15 min) ·
**Validar:** `python -m bbmodel validar` · **Resultados:** `data/modelos/algoritmo_A/`

---

## 1. La idea en una frase

Un número de una liga mezcla tres cosas: **el jugador**, **el entorno** de su liga (ritmo,
reglamento, cómo anota el estadístico) y **el nivel** de su liga (lo difícil que es). El algoritmo
separa las tres:

1. quita la **suerte** de las muestras pequeñas;
2. mira el **puesto** del jugador dentro de su liga y posición, lo que elimina el entorno;
3. aplica el **tipo de cambio** de su liga a la EuroLeague, aprendido de jugadores que han jugado
   en las dos (el nivel);
4. lo **traduce** a números de EuroLeague con su incertidumbre.

Es como cambiar divisas. El paso 2 dice cuántos «dólares» tiene el jugador en su país; el paso 3
dice a cuántos «euros» equivale un dólar; y el tipo de cambio se aprende de los viajeros que han
pagado en las dos monedas.

## 2. Los datos que usa

* Temporada regular 2020-21 a 2026-27 de las 8 ligas (`data/processed/*/ligas/*.csv`).
  Son 18.508 registros jugador-liga-temporada y 5.806 personas distintas.
* **Identidad** (`identidad.py`). Las fuentes no comparten identificadores, así que el mismo jugador
  se reconoce por el nombre normalizado. Los homónimos se separan con el año de nacimiento
  (temporada − edad) y con la imposibilidad de jugar dos calendarios completos a la vez.
  Ejemplo: el Devin Booker del Olimpia Milano (nacido en 1991) no es el de Phoenix (1996).
  Resultado: **4.336 enlaces entre ligas**, de los que 1.064 son en la misma temporada (por
  ejemplo, EuroLeague + ACB) y 3.272 cambios de liga de una temporada a otra. Se dejan 17 casos
  ambiguos sin enlazar: se prefiere perder un puente a crear uno falso.
* **Posición** (`posicion.py`). Hay tres grupos: exterior (1-2), alero (3) e interior (4-5).
  Donde la fuente no la publica (EuroLeague, EuroCup, LBA y parte de la G League), se estima con
  una regresión logística sobre el perfil estadístico. Acierta el 77 % con validación cruzada y
  entre el 73 % y el 78 % en una liga que no vio al entrenar. Un jugador conserva la misma posición
  en todas sus ligas.

## 3. Los cuatro pasos

### Paso 1 — Quitar la suerte (`suerte.py`)
Con 80 minutos, un 60 % en triples es casi todo suerte. Cada valor observado se descompone en
capacidad real + ruido. El ruido se reduce con la **exposición** (minutos, tiros o posesiones,
según la métrica):

    observado = capacidad + ruido,   ruido ~ N(0, σ²/n),   capacidad ~ N(μ_grupo, τ²)

* `n`: exposición del jugador. `σ²`: ruido por unidad de exposición. Para métricas de tiro es
  común a todas las ligas, porque el azar de un tiro no depende de la liga; para las de minutos o
  posesiones se estima por liga, porque el ritmo cambia cuánto pasa en cada minuto.
  `τ²`: cuánto difieren de verdad los jugadores (por liga y posición). `μ`: media por liga,
  temporada y posición.
* Se estiman por momentos: dentro de cada grupo, `E[(y − μ)²] = τ² + σ²/n`, una recta contra `1/n`.
* Antes se transforma cada métrica para que se parezca a una normal: raíz para tapones o tiros
  libres por tiro, logaritmo para asistencias o rebote, y sin cambio para porcentajes de tiro o
  ratings. La transformación se eligió comparando la asimetría de cada opción.
* Comprobación interna: para casi todas las métricas, la dispersión observada coincide con la real
  más el ruido estimado (DRtg 1,10 frente a 1,10; PER 1,61 frente a 1,69; TS% 4,49 frente a 4,43).
  La excepción es el T3%, cuyo ruido se sobreestima algo.

**Fiabilidad** (cuánto de lo que se ve es real, mediana con 100+ minutos, EuroLeague):
USG% 0,96 · AST% 0,83 · Pts/100 0,85 · PER 0,66 · BLK% 0,62 · TS% 0,23 · ORtg 0,20 · T3% 0,13.
En lenguaje de scouting: el uso y la creación se ven pronto; la eficiencia de tiro necesita
muchos partidos para distinguirse del azar.

### Paso 2 — El puesto dentro de su liga
Con lo anterior, cada jugador queda como un **z** frente a los de su posición en su liga y
temporada: z = 0 es el jugador medio, z = 1 una desviación típica de capacidad por encima.
Este paso elimina el entorno: ritmo, reglamento y criterio de anotación afectan a todos los
jugadores de esa liga por igual.

### Paso 3 — El tipo de cambio (`enlace.py`)
Ser z = 1 en la LBA no es ser z = 1 en la EuroLeague. Cada liga tiene una equivalencia lineal con
la vara EuroLeague:

    capacidad en la vara EuroLeague:   u = m_liga + s_liga · z

* **m** («nivel»): cuánto vale en la EuroLeague el jugador MEDIO de esa liga, en desviaciones
  típicas de la EuroLeague. Negativo = liga más floja.
* **s** («escala»): si las diferencias entre jugadores de esa liga se estiran (s > 1) o se
  comprimen (s < 1) al llevarlas a la EuroLeague.
* La EuroLeague es la referencia: m = 0, s = 1.

**Cómo se estima.** Con los jugadores puente, mediante un modelo de factor latente:

    z observado en la liga l = (a + d·Δ − m_l)/s_l + ruido de muestra + ψ_l + η²·Δ

* `a`: capacidad latente del jugador en la vara EuroLeague (lo que se quiere conocer).
* `d(edad)`: cuánto cambia un jugador de una temporada a la siguiente (Δ = 1), según su edad.
  Separa «rinde más porque la liga es más floja» de «rinde más porque ha mejorado».
* `ψ_l`: parte del número que es contexto (rol, entrenador, compañeros). `η²`: cambio real
  impredecible de un año a otro.
* Se ajusta con el **algoritmo EM**. Paso E: con los tipos de cambio actuales se estima la
  capacidad de cada puente y su incertidumbre. Paso M: con esas capacidades se reajustan m, s, d,
  ψ y η². Corregir por la incertidumbre de la capacidad evita el sesgo de atenuación de una
  regresión ingenua.
* Las ligas sin puente directo se enlazan en cadena (G League → NBA → EuroLeague). Una previa
  suave mantiene s cerca de 1 cuando hay pocos puentes (equivale a 10 observaciones con s = 1).
* Incertidumbre de m y s: bootstrap por jugadores (20 remuestreos).

Es la misma técnica que usan los psicómetras para **igualar dos versiones de un examen con
alumnos que hacen ambas**.

### Paso 4 — Traducir (`modelo.py`)
Para un jugador de la liga l:

1. Su z sin suerte y sin contexto: `z* = z/(1 + v + ψ_l)`.
2. Su capacidad en la vara EuroLeague: `a = m_l + s_l · z*`. La incertidumbre suma la del propio
   jugador y la de m y s.
3. Su valor en la EuroLeague 2025-26, en su posición: `μ_EL + τ_EL · a`, deshaciendo la
   transformación. Su percentil entre los de EuroLeague de su posición es `Φ(a)`.
4. Su proyección para la temporada siguiente: `a + d(edad)`, con la varianza extra η².

Los jugadores de la EuroLeague pasan por el mismo proceso. También se les quita la suerte y el
contexto, porque sólo así todos se comparan con la misma vara.

## 4. Validación (examen fuera de muestra)

`python -m bbmodel validar`. El modelo se ajusta SÓLO con temporadas hasta t y se predice qué
hicieron en t+1 los jugadores que cambiaron de liga (300+ minutos en ambas): 2023-24 → 2024-25 y
2024-25 → 2025-26, **412 jugadores**. Se compara con dos métodos:

* «mismo número»: suponer que repite su número.
* «mismo percentil»: suponer que ocupa el mismo puesto relativo en la nueva liga. Es lo que hace
  casi todo el mundo.

Resultados completos en `data/modelos/algoritmo_A/validacion.csv`.


**Lectura.** El algoritmo A reduce el error cuadrático frente a «mismo percentil» en las
25 métricas, y frente a «mismo número» también en todas. Las mayores mejoras están en las
métricas de producción y valoración: PER, Game Score/40, USG%, Pts/100, DRtg y WS/40 (+36 % a +42 %). En porcentajes de tiro la mejora es pequeña,
porque son sobre todo ruido. El intervalo del 80 % contiene al valor real entre el
80 % y el 89 % de las veces: está bien calibrado,
algo prudente. «Mejora» = 1 − ECM(A)/ECM(percentil).

| Métrica | Casos | Error medio: mismo número | mismo percentil | **algoritmo A** | Mejora vs percentil | Llegadas a EL: mejora | Cobertura 80 % |
|---|---|---|---|---|---|---|---|
| AST% | 412 | 4,42 | 4,05 | **3,70** | +7 % | -13 % | 85 % |
| Tapones por 100 pos. | 412 | 0,37 | 0,35 | **0,31** | +15 % | +24 % | 85 % |
| BLK% | 313 | 0,79 | 0,73 | **0,64** | +18 % | +23 % | 83 % |
| Rebotes defensivos por 100 pos. | 412 | 1,32 | 1,15 | **1,05** | +18 % | +15 % | 86 % |
| DREB% | 313 | 2,96 | 2,52 | **2,33** | +18 % | +15 % | 86 % |
| DRtg individual | 313 | 6,63 | 4,54 | **3,57** | +36 % | +56 % | 83 % |
| eFG% | 412 | 5,57 | 4,64 | **4,57** | +6 % | -9 % | 82 % |
| T2% | 412 | 6,44 | 5,33 | **5,23** | +3 % | -11 % | 83 % |
| T3% | 386 | 7,44 | 6,23 | **6,16** | +3 % | +5 % | 80 % |
| Triples / tiros de campo (3PAr) | 412 | 7,45 | 7,68 | **7,40** | +6 % | +6 % | 81 % |
| TL% | 412 | 7,51 | 7,00 | **6,80** | +6 % | +4 % | 89 % |
| Tiros libres / tiros de campo (FTr) | 412 | 9,99 | 7,79 | **7,59** | +2 % | +4 % | 84 % |
| Game Score por 40' | 404 | 3,82 | 3,01 | **2,38** | +42 % | +31 % | 84 % |
| Rebotes ofensivos por 100 pos. | 412 | 0,70 | 0,66 | **0,63** | +7 % | +0 % | 84 % |
| OREB% | 313 | 1,45 | 1,43 | **1,41** | +1 % | -6 % | 85 % |
| ORtg individual | 313 | 8,82 | 7,43 | **7,22** | +11 % | -14 % | 85 % |
| PER | 404 | 4,41 | 3,33 | **2,58** | +41 % | +38 % | 86 % |
| Faltas por 100 pos. | 404 | 1,27 | 0,95 | **0,89** | +13 % | +16 % | 88 % |
| Puntos por 100 posesiones | 412 | 5,48 | 4,76 | **3,80** | +38 % | +30 % | 83 % |
| Robos por 100 pos. | 412 | 0,53 | 0,45 | **0,45** | +2 % | +4 % | 88 % |
| STL% | 412 | 0,53 | 0,45 | **0,45** | +2 % | +2 % | 87 % |
| TOV% | 404 | 2,83 | 2,77 | **2,74** | +2 % | +3 % | 84 % |
| TS% | 412 | 5,99 | 4,49 | **4,23** | +13 % | -2 % | 86 % |
| USG% | 404 | 3,94 | 3,53 | **2,66** | +42 % | +33 % | 80 % |
| Win Shares por 40' | 313 | 0,07 | 0,05 | **0,04** | +37 % | +29 % | 87 % |

## 5. El tipo de cambio estimado

`data/modelos/algoritmo_A/tipo_de_cambio.csv` tiene m, s, su error típico, ψ y el número de
puentes por métrica y liga.

**Nivel m** (en desviaciones típicas de la EuroLeague; ± error típico). Ejemplo: PER −0,47 en la ACB significa que el jugador medio de la ACB rendiría en la EuroLeague media desviación típica por debajo del jugador medio de la EuroLeague de su posición. En DRtg (menos es mejor) un valor positivo significa peor defensa.

| Métrica | NBA | G League | ACB | EuroCup | LNB | LBA | BBL |
|---|---|---|---|---|---|---|---|
| PER | +0,58 ±0,06 | −0,36 ±0,06 | −0,47 ±0,04 | −0,73 ±0,07 | −0,56 ±0,07 | −0,79 ±0,06 | −0,97 ±0,07 |
| Game Score por 40' | +0,55 ±0,06 | −0,30 ±0,05 | −0,41 ±0,03 | −0,69 ±0,06 | −0,51 ±0,07 | −0,72 ±0,05 | −0,88 ±0,06 |
| Win Shares por 40' | −0,05 ±0,07 | −0,75 ±0,06 | −0,50 ±0,06 | −0,77 ±0,05 | – | −0,88 ±0,06 | −1,16 ±0,05 |
| Puntos por 100 posesiones | +0,81 ±0,07 | −0,02 ±0,06 | −0,30 ±0,05 | −0,42 ±0,05 | −0,41 ±0,03 | −0,41 ±0,04 | −0,57 ±0,04 |
| USG% | +1,03 ±0,07 | +0,22 ±0,05 | −0,14 ±0,02 | −0,21 ±0,03 | −0,16 ±0,04 | −0,17 ±0,03 | −0,33 ±0,05 |
| AST% | +0,06 ±0,05 | −0,47 ±0,05 | −0,13 ±0,04 | −0,33 ±0,05 | −0,31 ±0,05 | −0,31 ±0,04 | −0,43 ±0,04 |
| TS% | +0,08 ±0,13 | −0,85 ±0,19 | −0,54 ±0,09 | −0,83 ±0,14 | −0,85 ±0,08 | −0,98 ±0,10 | −1,03 ±0,13 |
| DREB% | +0,48 ±0,05 | +0,07 ±0,06 | −0,06 ±0,04 | −0,27 ±0,06 | – | −0,20 ±0,06 | −0,44 ±0,05 |
| BLK% | +0,59 ±0,12 | +0,43 ±0,12 | −0,11 ±0,05 | −0,18 ±0,07 | – | −0,21 ±0,05 | −0,23 ±0,08 |
| DRtg individual | −0,11 ±0,07 | +0,29 ±0,07 | +0,41 ±0,05 | +0,62 ±0,06 | – | +0,72 ±0,06 | +1,12 ±0,08 |

El orden de nivel que sale en las métricas globales es NBA > EuroLeague > G League ≈ ACB > LNB > EuroCup ≈ LBA > BBL. La escala s está entre 0,7 y 1,2: en G League y LNB las diferencias entre jugadores se comprimen al llevarlas a la EuroLeague (s ≈ 0,81 y 0,74 en PER); en NBA se estiran (s ≈ 1,20).

**Edad (deriva d, PER, en desviaciones típicas por temporada):** ≤23: +0,06 · 24-26: +0,04 · 27-29: −0,02 · 30-32: −0,14 · 33+: −0,28.

*(Tablas regeneradas tras corregir el año de nacimiento a nivel de persona, octubre de 2026.)*

## 6. Ficheros de salida

| Fichero | Contenido |
|---|---|
| `parametros.json` | Todos los parámetros: μ, τ, σ², m, s, ψ, η², deriva por edad, errores |
| `tipo_de_cambio.csv` | m y s por métrica y liga, con su error y puentes |
| `traducciones/<temporada>.csv` | Una fila por jugador-liga-temporada. Por métrica: valor original, `<m>_el` (equivalente EuroLeague), `<m>_el_lo` / `<m>_el_hi` (intervalo del 80 %), `<m>_pct_el` (percentil EuroLeague en su posición), `<m>_el_prox` (proyección a la temporada siguiente), `<m>_a` y `<m>_a_sd` (capacidad en desviaciones típicas EuroLeague) |
| `validacion.csv`, `validacion_casos.csv` | Examen fuera de muestra: resumen y cada predicción |

## 7. Limitaciones conocidas

* **Cada métrica se traduce por separado.** Un jugador puede salir alto en una y bajo en otra
  sin que el modelo use que suelen ir juntas. El algoritmo B (`docs/algoritmo_B.md`) lo hace de forma conjunta.
* **Eficiencia y asistencias al llegar a la EuroLeague.** En los 88 casos de llegada a la EuroLeague
  el algoritmo no mejora a «mismo percentil» en las métricas de eficiencia (TS% −2 %, eFG% −9 %,
  T2% −11 %, ORtg −14 %), en AST% (−13 %) ni en OREB% (−6 %). Sí mejora claramente en producción,
  uso, rebote defensivo, tapones, DRtg y valoraciones globales (+15 % a +56 %). Probable causa: los
  clubes de EuroLeague fichan a quien esperan que mantenga su eficiencia y su papel (selección por
  el resultado), y el tipo de cambio de eficiencia, aprendido sobre todo de jugadores de clubes
  EuroLeague en su liga nacional, castiga demasiado al recién llegado. Hasta corregirlo, en esas
  métricas conviene mirar también el percentil en su liga.
* **Linealidad.** El tipo de cambio es una recta por liga y métrica, igual en todas las posiciones
  y temporadas.
* **Sesgo de selección de los puentes.** Sólo se ve en la EuroLeague a quien alguien fichó, y
  quien no juega minutos no cuenta. Se mitiga con umbrales bajos (150 minutos) y con el ruido de
  muestra explícito, pero no desaparece.
* **Contexto de equipo.** z es relativo a la liga, no al equipo: un jugador de un equipo dominante
  puede salir inflado en ratings de equipo (DRtg, WS). ψ absorbe parte de eso.
* **Edad.** La ACB, la LBA y la BBL no publican edad. Esos jugadores usan la deriva media salvo que
  su edad se conozca por otra liga. En la LNB la columna `edad` es la actual, no la de cada
  temporada; aquí se usa la fecha de nacimiento.
* **LNB.** Sin totales de rivales: no hay traducción de ORtg, DRtg, WS, OREB%, DREB% ni BLK%.
  Se usan las versiones por 100 posesiones.

## Métricas de pista (oct. 2026)

El catálogo pasa de 25 a **33 métricas**: se añaden 8 del jugada a jugada (grupo «Pista» de `bbmodel/metricas.py`;
datos de `bbmodel/pista.py`): % de tiros en el aro, cortos, de media distancia y triples de esquina (exposición:
tiros con coordenadas), % de canastas propias asistidas (exposición: canastas) y RAPM, ORAPM y DRAPM (exposición:
posesiones en pista). Examen fuera de muestra (412 cambios de liga), mejora de A+B frente a «mismo percentil»: RAPM
+46 %, ORAPM +49 %, DRAPM +40 %, zonas y asistidas +16-23 %; A+B gana a A en las 33. Las 25 métricas de caja no
cambian en A (cada métrica se ajusta aparte) y se mueven ±2 puntos en B. Detalle, contexto de nivel y química de
estilos: [`contexto_y_quimica.md`](contexto_y_quimica.md).
