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

Entrenamiento del 13-10-2026: 997 clubes-competición-temporada (2020-21 a 2025-26) + 120 provisionales de
2026-27; 5 semillas por red (semilla final: IDEC 51, VaDE 37); 19 minutos en 4 núcleos. Mapa interactivo:
Artifact «Atlas de Estilos» (https://claude.ai/artifact/D2ULCYstYh4ykwSzExUPNU, privado).

| Métrica (997 clubes) | IDEC | VaDE | Mejor |
|---|---|---|---|
| Equilibrio del reparto (entropía, 1 = igual) | 0,963 | **0,970** | VaDE |
| Estilo más pequeño (clubes) | 29 | **33** | VaDE |
| Confianza media de la neurona ganadora | 0,39 | **0,74** | VaDE |
| Silueta en el mapa 3D | **0,273** | 0,212 | IDEC |
| Silueta en los 13 rasgos (k-medias directo: 0,094) | 0,043 | **0,057** | VaDE |
| Davies-Bouldin en el mapa (menos es mejor) | **1,02** | 1,52 | IDEC |
| Estabilidad de los estilos entre semillas (ARI medio) | **0,43** | 0,38 | IDEC |
| Estabilidad del mapa entre semillas (r de distancias) | 0,916 | **0,962** | VaDE |
| Robustez al reparto de minutos | 0,49 | **0,52** | VaDE |
| Reproducibilidad temporal (ARI, red sin 2024-26) | 0,28 | **0,37** | VaDE |
| Fidelidad del mapa: trustworthiness (k = 10) | **0,926** | 0,912 | IDEC |
| Fidelidad del mapa: continuidad (k = 10) | 0,921 | **0,931** | VaDE |
| Correlación de Spearman distancias mapa / perfil | 0,810 | **0,824** | VaDE |
| R² medio de reconstrucción | **0,71** | 0,65 | IDEC |
| Parejas de estilos distintas (permutación 9.999, Holm 5 %) | 66/66 | 66/66 | = |
| Mahalanobis mínima / mediana entre estilos | 2,22 / 4,37 | 2,26 / 4,19 | ≈ |
| Replicabilidad de perfiles 2020-23 / 2023-26 (r medio) | **0,94** | 0,92 | IDEC |
| Persistencia del estilo de un club al año siguiente (azar) | 35 % (10 %) | **44 %** (10 %) | VaDE |
| Minutos de la plantilla en el estilo de su club (azar) | **14 %** (8 %) | 12 % (8 %) | IDEC |
| Información compartida estilo-liga (NMI) | 0,32 | 0,39 | — |

**Lectura.**

* **Los 12 estilos están matemática y estadísticamente diferenciados en las dos redes**: las 66 parejas
  difieren tras corregir por comparaciones múltiples, la distancia de Mahalanobis mínima entre perfiles
  medios es 2,2 desviaciones, y, lo más importante porque no es circular, el perfil de cada estilo se
  replica entre 2020-23 y 2023-26 (r = 0,94 y 0,92).
* **VaDE** gana en 10 de las 16 métricas comparables y en las que más importan para fichar: la
  confianza de la asignación (0,74 frente a 0,39), la estabilidad del mapa entre semillas (0,96), la
  reproducibilidad temporal y la persistencia. **IDEC** forma regiones más compactas en el mapa (silueta,
  Davies-Bouldin), conserva mejor la vecindad local y reconstruye mejor el perfil.
* **Recomendación**: VaDE como red principal (mapa más estable y probabilidades interpretables) e IDEC
  como contraste: cuando las dos coinciden en que un jugador está cerca del club, la señal es sólida.
* **Estilo continuo.** Con cualquier método la separación en los 13 rasgos es baja (k-medias directo:
  0,094; las redes ceden algo de esa separación a cambio de un mapa 3D fiel y compartido con los
  jugadores). La estabilidad de las etiquetas entre semillas es moderada (ARI 0,38-0,43), y la del mapa,
  alta (0,92-0,96): **la distancia en el mapa es más fiable que la etiqueta**, sobre todo cerca de las
  fronteras.
* **El nivel de la liga se cuela en el estilo.** Aunque las métricas de calidad están fuera, la vara
  EuroLeague traslada el nivel de cada liga a las métricas de estilo (un jugador NBA, traducido,
  rebotea y asiste más y hace menos faltas). Por eso 2 estilos de VaDE (E11, E12) y 3 de IDEC
  (E10-E12) son casi sólo NBA y el nivel medio de los estilos va de −0,9 a +1,5. Es coherente con
  los datos normalizados, pero significa que «estilo» incluye en parte «nivel de liga».
* **Qué define los estilos** (η², parte de la varianza de cada rasgo explicada por el estilo):
  rebote defensivo 0,74-0,77, faltas 0,71-0,73, AST% 0,67-0,70, FTr 0,61-0,66, 3PAr 0,52-0,58; menos,
  tapones, posiciones, pérdidas y robos (0,31-0,50); casi nada, la concentración del uso (0,10-0,15) y
  el **ritmo (0,03)**: el ritmo está en el mapa, pero al ser relativo a cada liga pesa poco frente a
  los rasgos que arrastran el nivel de la liga.

**Saski Baskonia por temporada** (estilo · salida de la neurona ganadora):

| Temporada | VaDE EuroLeague | VaDE ACB | IDEC EuroLeague | IDEC ACB |
|---|---|---|---|---|
| 2020-21 | E09 · 0,82 | E09 · 0,90 | E12 · 0,21 | E08 · 0,25 |
| 2021-22 | E09 · 0,70 | E07 · 0,52 | E11 · 0,20 | E08 · 0,22 |
| 2022-23 | E07 · 0,68 | E07 · 0,84 | E11 · 0,27 | E06 · 0,27 |
| 2023-24 | E07 · 0,93 | E07 · 0,95 | E06 · 0,21 | E06 · 0,35 |
| 2024-25 | E09 · 0,80 | E09 · 0,85 | E08 · 0,41 | E08 · 0,59 |
| 2025-26 | E07 · 0,69 | E09 · 0,55 | E06 · 0,35 | E06 · 0,41 |
| 2026-27 (provisional) | E01 · 0,98 | E01 · 0,95 | E06 · 0,60 | E06 · 0,63 |

En VaDE, E07 = «TOV% ↓ · uso concentrado ↑ · 3PAr ↑» y E09 = «faltas ↓» (estilo con más clubes EuroLeague).
El cambio de 2026-27 descansa en 3-4 jornadas, sólo algoritmo A y muy pocos minutos de interiores: hay que
esperar.

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
