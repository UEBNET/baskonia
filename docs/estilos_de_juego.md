# Estilos de juego — dos redes neuronales con 12 neuronas de salida y mapa 3D

> Código: `bbestilo/` · Entrenar: `python -m bbestilo entrenar` (≈40 min en 4 núcleos) ·
> Encaje: `python -m bbestilo encaje --jugador "Nombre"` · Mapa: `artifact/mapa-estilos.html`
> (datos con `python -m bbestilo exportar`) · Resultados: `data/modelos/estilos/`

## 1. Qué resuelve

Asigna a cada **club-competición-temporada** de las 8 ligas (Baskonia EuroLeague 2025-26 y Baskonia
ACB 2025-26 son dos puntos distintos) uno de **12 estilos de juego**, con dos redes neuronales
distintas que comparten un contrato:

* la **última capa tiene 12 neuronas**, una por estilo, y sus salidas suman 1; el estilo asignado es
  la neurona con mayor salida;
* la capa anterior tiene **3 neuronas**, que son las coordenadas del **mapa 3D**. Clubes y jugadores
  se sitúan en el mismo mapa, así que se puede medir la distancia entre Baskonia, un jugador y el club
  de ese jugador, y si la plantilla está agrupada en un estilo o dispersa («una oveja de cada madre»).

Los estilos son abstractos (`E01`…`E12`); cada uno lleva una etiqueta automática con sus rasgos más
marcados y su perfil completo, que es lo que los diferencia matemáticamente.

## 2. Datos: siempre los normalizados

* **Fuente**: traducciones a la vara EuroLeague 2025-26 del estudio de normalización de ligas
  (`data/modelos/algoritmo_A|B/traducciones/`, columnas `<métrica>_el`). Se usa la combinación
  **A+B** que recomienda el estudio (media en la escala transformada de cada métrica). Si B no tiene
  al jugador (menos de 150 minutos) se usa A; en **2026-27** B sólo traduce 4 filas, así que la
  temporada en curso va sólo con A y se marca **provisional** (no entra en el entrenamiento).
* **Minutos por club**: filas jugador-equipo de temporada regular de bbstats. Un traspasado aporta a
  cada club sus minutos en él, con su perfil normalizado de esa liga y temporada.
* **Agregación**: el vector de un club es la **media ponderada por minutos** del de sus jugadores (el
  perfil medio de los cinco en pista). Es exacta y lineal en los minutos: un fichaje o un cambio de
  rotación mueve el club de forma calculable (ver §6).
* **Cobertura**: las traducciones cubren el 99-100 % de los minutos de cada liga; B, el 95-97 %.

### 2.1 Los 13 rasgos de estilo (entrada de las dos redes)

| Bloque | Rasgo | Origen | Transformación |
|---|---|---|---|
| Estructura | Ritmo relativo a su liga (z del ritmo del equipo en su liga y temporada) | contexto (**no** está en el estudio; se añade por decisión de la dirección deportiva) | — |
| Ataque | 3PAr (triples / tiros de campo) | A+B | — |
| Ataque | FTr (tiros libres / tiros de campo) | A+B | raíz |
| Ataque | AST% | A+B | log(1+x) |
| Ataque | TOV% | A+B | log(1+x) |
| Ataque | Rebotes ofensivos por 100 posesiones | A+B | log(1+x) |
| Estructura | Concentración del uso = E_w[USG²]/E_w[USG]² (1 = reparto; más = juego «heliocéntrico») | derivado de A+B | log(1+x) |
| Defensa | Rebotes defensivos por 100 posesiones | A+B | log(1+x) |
| Defensa | Robos por 100 posesiones | A+B | raíz |
| Defensa | Tapones por 100 posesiones | A+B | raíz |
| Defensa | Faltas por 100 posesiones | A+B | raíz |
| Estructura | Cuota de minutos de interiores (4-5) | posición del estudio | — |
| Estructura | Cuota de minutos de exteriores (1-2) | posición del estudio | — |

Las transformaciones son las del catálogo de bbmodel y se aplican **después** de agregar. Se usan las
versiones por 100 posesiones de rebote, robo y tapón porque existen en las 8 ligas (la LNB no tiene
OREB%, DREB% ni BLK%).

**Dos escalas, un mismo mapa.** Los clubes se estandarizan con la media y la desviación de los
997 clubes de entrenamiento; los jugadores, con las de los jugadores (150+ minutos, ponderadas por
minutos). Un jugador «tan extremo entre los jugadores» como un club lo es entre los clubes cae en el
mismo sitio: su punto indica el estilo que encarna y con qué intensidad.

### 2.2 Capa de nivel (no define estilos)

PER, Game Score/40, WS/40, ORtg, DRtg, puntos/100, TS% y eFG% (normalizados A+B) miden **cuánto** se
rinde, no **cómo** se juega. Quedan fuera de las redes para que los 12 estilos no acaben siendo
«buenos frente a malos». Se resumen en un índice de nivel (media de z con signo) que el mapa puede
usar como color.

## 3. Las dos redes

| | **Red 1 · IDEC** | **Red 2 · VaDE** |
|---|---|---|
| Familia | Agrupamiento profundo discriminativo (Deep Embedded Clustering mejorado, Xie et al. 2016; Guo et al. 2017) | Modelo generativo variacional con previa de mezcla (Variational Deep Embedding, Jiang et al. 2017) |
| Codificador | `13 → 64 → 32 → 3`, GELU | `13 → 64 → 32 → (μ_z, log σ²_z) ∈ ℝ³`, GELU |
| Mapa 3D | z (determinista) | μ_z (la red da además su incertidumbre σ_z) |
| Decodificador | `3 → 32 → 64 → 13` | `3 → 32 → 64 → 13`, verosimilitud gaussiana con varianza común |
| **Capa de salida (12 neuronas)** | `q_k ∝ (1 + ‖z − μ_k‖²/α)^−(α+1)/2`, α = 1 (núcleo t de Student, 12 centroides μ_k en el mapa) | `γ_k = π_k N(z ∣ μ_k, σ²_k) / Σ_j π_j N(z ∣ μ_j, σ²_j)` (12 gaussianas diagonales en el mapa) |
| Geometría de un estilo | Región alrededor de un centroide (de forma parecida en todos) | Elipsoide con centro y forma propios (estilos compactos y amplios) |
| Pérdida | ECM de reconstrucción + estrés MDS + 0,1·KL(P‖Q) | −ELBO de VaDE (β de 0,1 a 1 en 30 épocas) + 13·estrés MDS |
| Inicialización de estilos | k-medias (30 inicios) sobre el mapa preentrenado | EM de mezcla gaussiana (5 inicios) sobre el mapa preentrenado |
| Formación de estilos | Autoentrenamiento: P = q²/f normalizada, recalculada cada 3 épocas; parada si cambian < 0,1 % de las etiquetas | Paso M amortiguado (0,5) de la mezcla tras cada época con π uniforme, suelo de varianza (2 % de la varianza del mapa) y resiembra de componentes con < 1 % de los clubes |
| Optimizador | Adam 1e-3, lotes de 512, decaimiento 1e-5 | Adam 1e-3 con tasa coseno, lotes de 512, decaimiento 1e-5 |
| Épocas | 100 de preentreno + hasta 120 | 100 de preentreno + 120 |
| Parámetros | 6.196 | 6.344 |
| Lectura de la salida | Pertenencia relativa a cada centroide (suave en las fronteras) | Probabilidad a posteriori de cada estilo |

**Común a las dos.**

* **Estrés de MDS métrico** `Σ(d_mapa − d_perfil)² / Σ d_perfil²` en cada lote: la distancia en el
  mapa se lee en las mismas unidades que la del perfil de estilo (desviaciones típicas) y el mapa usa
  las tres dimensiones. Sin él, IDEC dejaba el mapa casi plano y VaDE colapsaba en 2 componentes.
  En VaDE pesa 13 (el número de rasgos) porque su −ELBO suma sobre los 13 rasgos y el ECM de IDEC
  promedia.
* **Plantillas remuestreadas**: 24 por club con los minutos × Gamma(4, 1/4) (desviación del 50 %).
  Multiplican la muestra (≈1.000 clubes → ≈25.000) y enseñan que un estilo no depende de quién jugó
  unos minutos más o menos.
* **Jugadores como muestras auxiliares** (peso 0,3): el codificador aprende la zona del espacio donde
  caen los jugadores, pero los jugadores **no definen los estilos** (en IDEC no entran en la pérdida de
  agrupamiento; en VaDE la mezcla se reestima sólo con clubes).
* **5 semillas** por red; el modelo final es la **semilla medoide** (la de mayor ARI medio con las
  demás). La dispersión entre semillas mide la estabilidad.
* **Orientación del mapa**: centrado, ejes principales (eje 1 = mayor varianza) con signo
  determinista y una escala única. No cambia distancias relativas ni asignaciones. Los estilos se
  numeran por la posición de su centro en el eje 1.
* Activación GELU con aproximación tanh, que el navegador reproduce exactamente
  (test `test_los_pesos_exportados_reproducen_la_red`).

## 4. Resultados y comparativa

_(Se completa con `data/modelos/estilos/comparativa.csv` tras el entrenamiento.)_

## 5. Cómo se evalúa

`bbestilo/evaluar.py`, sobre los 997 clubes de 2020-21 a 2025-26:

1. **Reparto y confianza**: tamaños de los 12 estilos, entropía del reparto, salida media de la
   neurona ganadora.
2. **Separación**: silueta en el mapa y en los 13 rasgos, Davies-Bouldin y Calinski-Harabasz.
   Referencia sin red: k-medias con 12 grupos sobre los 13 rasgos.
3. **Estabilidad**: ARI entre las 5 semillas; robustez al reparto de minutos (40 plantillas
   remuestreadas por club); reproducibilidad temporal (red entrenada sin 2024-25 ni 2025-26 frente a la
   red completa, sobre esos clubes).
4. **Fidelidad del mapa**: trustworthiness y continuidad (k = 10), estrés y correlación de Spearman
   entre distancias; R² de reconstrucción por rasgo.
5. **Diferenciación estadística**: distancia de Mahalanobis entre los perfiles medios de cada pareja
   de estilos (covarianza intra-estilo común) con prueba de permutación (999) y corrección de Holm;
   η² por rasgo; **replicabilidad** del perfil de cada estilo entre 2020-23 y 2023-26. Las pruebas
   entre grupos formados con los mismos datos son optimistas por construcción; la replicabilidad
   entre periodos no lo es y es la prueba que conviene mirar.
6. **Uso**: persistencia del estilo de un club de una temporada a la siguiente frente al azar, y
   cuota de minutos de cada plantilla que comparte el estilo de su club.

## 6. Encaje de un fichaje

`python -m bbestilo encaje --jugador "Nombre" [--club baskonia] [--competicion euroleague]
[--temporada 2025-26] [--red idec|vade|ambas] [--minutos 600] [--sustituye "Nombre"]`

Para cada red da:

* **Situación**: estilo y punto del club destino, del jugador y del club del jugador.
* **Distancias** con percentil de referencia: jugador → club destino frente a lo lejos que está cada
  jugador de su propio club; club del jugador → club destino frente a todas las parejas de clubes.
* **Afinidad**: salida del jugador en la neurona del estilo del club y similitud de las 12 salidas
  (1 − divergencia de Jensen-Shannon en base 2).
* **Plantilla**: reparto de minutos por estilo y **dispersión** (distancia media ponderada al centro
  de la plantilla) con su percentil entre todos los clubes. Percentil alto = plantilla dispersa.
* **Simulación**: el club recalculado con el fichaje. El jugador toma el ritmo del club y sus minutos
  salen de todos a prorrata (por defecto, su cuota de minutos actual) o del jugador al que sustituye.

La página `artifact/mapa-estilos.html` hace lo mismo en el navegador con los pesos exportados.

## 7. Limitaciones

* **Continuo, no grupos naturales.** El estilo de los clubes es un continuo; la silueta en los
  13 rasgos es baja con cualquier método, también con k-medias directo. Los 12 estilos son una
  partición útil y estable de ese continuo, no especies separadas: mire la probabilidad de la neurona
  ganadora y la robustez, y use la distancia en el mapa para matizar.
* **Perfil normalizado = capacidad, no rol.** Las traducciones A+B quitan suerte y parte del contexto
  de equipo. El estilo que se mide es el de los jugadores que el club pone en pista, no el sistema del
  entrenador en sentido estricto (tipos de jugada, defensas zonales…), que estos datos no tienen.
* **Ritmo del jugador = ritmo de su equipo.** No hay ritmo individual; en la simulación el fichaje toma
  el del club destino.
* **Posición estimada** en EuroLeague, EuroCup, LBA y parte de la G League (regresión del estudio,
  ≈77 % de acierto); afecta a las cuotas interior/exterior.
* **Traspasos en EuroLeague/EuroCup**: la fuente los da en una fila; sus minutos van al último equipo.
* **Enlace de clubes LBA/LNB entre temporadas** por nombre y continuidad de plantilla: puede partir
  un club que cambia de nombre y de plantilla a la vez (p. ej. Scafati 2026-27).
* **2026-27 provisional**: pocas jornadas y sólo algoritmo A.

## 8. Ficheros

| Ruta | Contenido |
|---|---|
| `data/modelos/estilos/escalas.json` | rasgos, transformaciones y escalas de club y de jugador |
| `data/modelos/estilos/<red>/modelo.pt` | pesos de PyTorch (`bbestilo.entrenar.cargar`) |
| `data/modelos/estilos/<red>/pesos.json` | pesos para el navegador |
| `data/modelos/estilos/<red>/clubes.csv` | club-competición-temporada: mapa (x, y, z), dispersión bootstrap, estilo, 12 salidas, robustez, nivel |
| `data/modelos/estilos/<red>/jugadores.csv` | jugador-equipo-temporada (100+ min): mapa, estilo, salida |
| `data/modelos/estilos/<red>/estilos.csv` | perfil medio de cada estilo, etiqueta, centro en el mapa, ligas y ejemplos |
| `data/modelos/estilos/<red>/evaluacion.json` | todas las métricas de §5 |
| `data/modelos/estilos/comparativa.csv`, `evaluacion.json` | comparativa de las dos redes y referencia k-medias |
| `artifact/mapa-estilos.html`, `artifact/estilos/*.json` | mapa 3D interactivo y sus datos |
