# Estilos de juego (v2): VaDE con 8 estilos sin nivel y mapa 3D

> Código: `bbestilo/` · Artículo completo (PDF): [`docs/articulo/estilos_de_juego_baskonia.pdf`](articulo/estilos_de_juego_baskonia.pdf) ·
> Atlas interactivo: Artifact «Atlas de Estilos» (`artifact/mapa-estilos.html`, datos `artifact/estilos/`) ·
> Resultados: `data/modelos/estilos/` (v1 de 12 estilos: `data/modelos/estilos/v1_12estilos/`)

```bash
pip install -r requirements-estilos.txt
python -m bbestilo entrenar     # IDEC y VaDE, 5 semillas cada una, consenso y ajuste fino de VaDE (≈ 25-45 min)
python -m bbestilo evaluar      # reevalúa las redes guardadas
python -m bbestilo analisis     # K, nivel, éxito, efecto del encaje, continuidad, ligas, Baskonia
python -m bbestilo encaje --jugador "Nombre" [--club baskonia] [--competicion euroleague] [--temporada 2025-26]
python -m bbestilo parecidos --club baskonia [--jugador "Nombre"] [--alcance 30] [--temporadas 2025-26 ...]
python -m bbestilo exportar     # datos del Atlas (modelos de 8 y de 6 estilos)
python -m bbestilo articulo     # PDF
# 6 estilos: python -m bbestilo entrenar --estilos 6 --salida data/modelos/estilos/k6 (y evaluar/analisis igual)
# v1: python -m bbestilo entrenar --estilos 12 --sin-neutralizar --salida data/modelos/estilos/v1_12estilos
```

## 1. Qué cambia respecto a la v1

| | v1 | v2 |
|---|---|---|
| Estilos (neuronas de salida) | 12 | **8** |
| Nivel | dentro de los rasgos (la vara EuroLeague lo arrastra) | **neutralizado** antes de entrenar |
| Red principal | IDEC y VaDE en pie de igualdad | **VaDE**; IDEC sólo como contraste |
| Mezcla de VaDE | gaussianas diagonales | **covarianza completa** (elipsoides con orientación) |
| Modelo final | semilla medoide | **consenso de 5 semillas** + ajuste fino con la mezcla fijada en el consenso |
| Nivel explicado por el estilo (η²) | 74 % | **0,8 %** |
| Información estilo-liga (NMI) | 0,39 | **0,07** |

## 2. Datos

* Equivalentes EuroLeague 2025-26 del estudio de normalización (A+B; sólo A donde B no llega y en 2026-27),
  temporada regular, 8 ligas. 997 clubes-competición-temporada de entrenamiento (2020-21 a 2025-26) y 120
  provisionales (2026-27). 18.768 filas jugador-equipo.
* Vector de club = media de sus jugadores ponderada por minutos (13 rasgos: ritmo relativo a su liga, 3PAr, FTr,
  AST%, TOV%, rebote ofensivo y defensivo, robos, tapones y faltas por 100 posesiones, concentración del uso y
  cuotas de minutos de interiores y exteriores). Lineal en los minutos: los fichajes se simulan de forma exacta.
* **Capa de nivel**: PER, Game Score/40, WS/40, ORtg, DRtg, puntos/100, TS% y eFG% (normalizados) → índice L
  (media de z con signo). No entra en las redes.

## 3. Neutralización del nivel

Para cada rasgo transformado y estandarizado: `x̃ = (x − β₀ − β₁·L − β₂·L²) / s` (MCO sobre los clubes de
entrenamiento; los jugadores con su propia regresión ponderada por minutos). El nivel se recalcula para cualquier
reparto de minutos antes de neutralizar.

**No duplica la normalización entre ligas.** La normalización pone a todos los jugadores en la misma escala (sin
ella, una regresión común en ocho ligas no tendría sentido); la neutralización quita de los rasgos de estilo la
parte que predice la calidad, sea cual sea la liga. Lo que el nivel explicaba antes de neutralizar (clubes):
rebote defensivo 74 %, faltas 71 %, AST% 64 %, FTr 58 %, tapones 38 %, TOV% 34 %; ritmo, rebote ofensivo,
concentración del uso y posiciones, < 10 %.

## 4. VaDE v2

* Codificador `13 → 64 → 32 → (μ, log σ²) ∈ ℝ³` (GELU); μ = punto en el mapa. Decodificador `3 → 32 → 64 → 13` con
  varianza común. **Capa de salida: 8 neuronas** = probabilidad a posteriori de 8 gaussianas de covarianza completa.
  6.364 parámetros.
* Pérdida: −ELBO de VaDE + 13 · estrés de MDS métrico (distancia del mapa = distancia del perfil, escala fija).
* Entrenamiento: 997 clubes + 23.928 plantillas remuestreadas (minutos × Gamma(4, 1/4)) + 12.753 jugadores (peso 0,3,
  no definen estilos). Preentreno 100 épocas, mezcla inicial por EM, 120 épocas (Adam 1e-3, coseno) con paso M
  amortiguado (π uniforme, suelo de varianza, resiembra).
* **Consenso**: 5 semillas → matriz de co-asociación → enlace medio en 8 grupos. La semilla más cercana al consenso
  (23) se ajusta 40 épocas con la mezcla **fijada** en el consenso (con paso M se alejaba de él: ARI 0,57).
  ARI del modelo final con el consenso 0,68; con las semillas, 0,50 de media (más central que cualquier semilla).

## 5. Resultados (997 clubes, 2020-26)

| Métrica | VaDE v2 | IDEC v2 | VaDE v1 |
|---|---|---|---|
| Nivel explicado por el estilo (η²) | **0,008** | 0,021 | 0,740 |
| Información estilo-liga (NMI) | **0,072** | 0,104 | 0,388 |
| Pureza de liga media de los estilos | **0,27** | 0,31 | 0,51 |
| Seguridad media de la asignación | **0,79** | 0,43 | 0,74 |
| Estabilidad de los estilos entre semillas (ARI) | **0,41** | 0,31 | 0,38 |
| Centralidad del modelo final (ARI con las semillas) | **0,50** | 0,37 | 0,40 |
| Estabilidad del mapa entre semillas (r) | **0,95** | 0,84 | 0,96 |
| Robustez al reparto de minutos | **0,55** | 0,50 | 0,52 |
| Reproducibilidad temporal (ARI) | 0,40 | **0,49** | 0,37 |
| Trustworthiness (k = 10) | 0,87 | **0,89** | 0,91 |
| Silueta en los 13 rasgos (k-medias directo: 0,082) | 0,026 | **0,051** | 0,057 |
| Parejas de estilos distintas (permutación 9.999, Holm) | 28/28 | 28/28 | 66/66 |
| Replicabilidad de perfiles 2020-23 / 2023-26 (r) | 0,89 | **0,94** | 0,92 |

VaDE es la red recomendada: asigna con mucha más seguridad, su mapa es más estable y es más neutral al nivel.
Cede separación en los rasgos (silueta) a cambio de estabilidad; la IDEC reproduce algo mejor la partición sin las
dos últimas temporadas.

### Los 8 estilos (nombres en `config/estilos_v2.json`)

| | Estilo | Rasgos | Clubes |
|---|---|---|---|
| E01 | Estrella y presión | uso concentrado, triple, pocas pérdidas; robos y faltas; poco rebote defensivo | 113 |
| E02 | Perímetro pausado | ritmo bajo, mucho triple, pocos tiros libres y pérdidas; quintetos pequeños | 158 |
| E03 | Equilibrado | sin rasgos extremos | 47 |
| E04 | Pintura física | interiores, rebote ofensivo, tapones, robos, muchas faltas, poco triple | 126 |
| E05 | Exterior y riesgo | bases y escoltas, asistencias, robos, tiros libres; más pérdidas | 154 |
| E06 | Tamaño y rebote | pocos exteriores, rebote en los dos aros, defensa conservadora | 108 |
| E07 | Ritmo y pase | ritmo alto, triple y asistencias, muy pocas faltas, poco rebote ofensivo | 137 |
| E08 | Ataque al aro | penetración y tiros libres, asistencias, rebote defensivo, poco triple | 154 |

## 6. Hallazgos complementarios (`analisis.json`)

* **Número de estilos.** BIC e ICL sobre los 13 rasgos sin nivel prefieren **6**; la estabilidad de k-medias es
  alta hasta 5 (0,72) y cae desde 6 (K = 8: 0,41). Los datos respaldan con claridad 4-6 estilos; 8 es una
  resolución más fina. Ver el modelo de 6 estilos (sección 7).
* **Estilo y éxito.** A igual nivel, el estilo explica una parte relevante del net rating (η² parcial 26 %,
  p < 0,001); «Estrella y presión» +0,71 σ, «Ataque al aro» −0,81 σ. Parte es mecánica (pérdidas, rebote y tiros
  libres son «cuatro factores» de eficiencia).
* **Efecto del encaje.** 2.214 cambios de club (300+ min): parecerse al estilo del nuevo club **no** mejora el
  rendimiento; la asociación es pequeña y de signo contrario (+0,038 de nivel por unidad de distancia,
  p < 0,001) y no monótona por terciles. Compatible con fichajes de complementariedad.
* **Continuidad.** Cada +10 puntos de minutos que repiten multiplican por 1,15 la odds de conservar el estilo
  (p < 0,001); cuartil más bajo 24 % conserva el estilo, más alto 43 %.
* **Ligas.** Estilo × liga: V de Cramér 0,21 (p < 0,001); estilo × temporada: V 0,09 (p = 0,18, sin tendencia).
  Más parecidas a la EuroLeague: G League (0,25), LBA (0,50); a la Liga Endesa: LBA (0,36), EuroCup (0,55).
* **Baskonia.** EuroLeague: Equilibrado (20-21), Ritmo y pase (21-22, 23-24, 25-26), Estrella y presión (22-23),
  Tamaño y rebote (24-25). Es de los clubes que más cambian de estilo (desplazamientos en los percentiles 59-93).

## 7. Modelo alternativo de 6 estilos (`data/modelos/estilos/k6/`)

Como BIC e ICL prefieren 6, se entrenó un segundo VaDE con **6 neuronas de salida** (mismos datos, neutralización,
semillas, consenso y ajuste fino). Nombres en `config/estilos_k6.json`.

| Métrica (997 clubes) | VaDE 8 | VaDE 6 |
|---|---|---|
| Seguridad media de la asignación | 0,79 | **0,81** |
| Estilo más pequeño (clubes) | 47 | **127** |
| Nivel explicado por el estilo (η²) | 0,008 | 0,009 |
| Información estilo-liga (NMI) | 0,072 | 0,073 |
| Estabilidad de los estilos entre semillas (ARI) | 0,41 | **0,51** |
| Centralidad del modelo final | 0,50 | **0,56** |
| Estabilidad del mapa (r) | 0,953 | **0,955** |
| Reproducibilidad temporal (ARI) | 0,40 | **0,55** |
| Robustez al reparto de minutos | 0,55 | **0,58** |
| Silueta en los 13 rasgos | 0,026 | **0,056** |
| Mahalanobis mínima entre estilos | 1,71 | **2,20** |
| Replicabilidad de perfiles (r) | 0,89 | **0,92** |
| Parejas de estilos distintas (Holm) | 28/28 | 15/15 |

El de 6 es **mejor en casi todo lo que mide estabilidad y separación**, con la misma neutralidad al nivel; el de 8
da más matices (separa «Equilibrado» y «Ritmo y pase»). Las particiones son coherentes (ARI 0,44, NMI 0,52; el 72 %
de los clubes cae en el estilo de 6 al que va la mayoría de su estilo de 8). Con 6, el estilo explica el 26 % del net
rating a igual nivel (mejor E01 +0,55 σ, peor E06 −0,76 σ) y Baskonia EuroLeague 2025-26 es «Pase y juego limpio».

| | Estilo (6) | Rasgos | Clubes |
|---|---|---|---|
| E01 | Perímetro y control | mucho triple, pocos tiros libres y pérdidas; poco rebote defensivo | 164 |
| E02 | Físico y presión | interiores, rebote ofensivo, robos y tapones; muchas faltas | 189 |
| E03 | Exterior y riesgo | bases y escoltas, asistencias y robos; más pérdidas | 127 |
| E04 | Tamaño y control | pocos exteriores y asistencias, muy pocas pérdidas, buen rebote defensivo | 168 |
| E05 | Pase y juego limpio | asistencias y triple, muy pocas faltas, poco rebote ofensivo | 172 |
| E06 | Ataque al aro | penetración y tiros libres, asistencias, rebote defensivo, poco triple | 177 |

## 8. Buscador de parecidos (`bbestilo/similares.py`, CLI `parecidos`, sección del Atlas)

El parecido se mide en los **13 rasgos sin nivel** (no en el mapa ni en las etiquetas), así que no depende del
modelo de 6 u 8. Una distancia se traduce a «parecido» 0-100 con su percentil entre parejas reales del mismo tipo
(club-club, jugador-jugador, jugador-su club): 100 = más parecido que cualquier pareja real, 50 = pareja típica.

* **Clubes que juegan como el mío**: los clubes-competición-temporada más cercanos al de referencia (excluye el
  propio club en todas sus competiciones), con filtros de temporadas y ligas.
* **Jugadores** en dos modos: *como un jugador* (p. ej. uno que se va) o *que encaje con el estilo del club*.
  Opcionalmente sólo en los N clubes más parecidos al de referencia: «alguien como X, en un equipo que juegue como
  el mío». Puntuación = peso · parecido del jugador + (1 − peso) · parecido de su club. Filtros de posición,
  minutos, edad y nivel mínimo (el nivel no entra en el parecido). Cada persona aparece una vez.
* En el Atlas, los clubes se pueden añadir al comparador y los jugadores se pueden simular en el club de
  referencia; los 10 primeros se marcan en el mapa. El cálculo en el navegador coincide con Python.

## 9. Atlas de Estilos (Artifact)

Selector de modelo (8 o 6 estilos; por defecto 8); resumen ejecutivo; buscador de parecidos; filtros de temporadas, competiciones, estilos, nivel, posición y minutos de jugadores; capas
(clubes, jugadores, centros, elipsoides de los estilos, trayectorias, centros de liga); color por estilo, liga,
nivel o temporada; tamaño por nivel o robustez; cámaras predefinidas y giro; comparador de hasta 4 equipos o ligas
(perfil, reparto entre estilos, distancias) con **jugador opcional** (encaje y simulación del fichaje); ligas ×
estilos y evolución por temporada; Baskonia por temporada; tarjetas de los estilos; correspondencia 8 ↔ 6; hallazgos; ficha del modelo;
descarga del artículo en PDF. La red se ejecuta en el navegador con los pesos exportados (comprobado: misma salida
que Python, diferencia máxima 0,006 en el mapa).

## 10. Limitaciones

Estilo continuo (etiquetas menos fiables que la distancia en el mapa); rasgos de jugador en pista, no del sistema
del entrenador (sin tipos de jugada, zonas de tiro ni quintetos); neutralización lineal-cuadrática en un índice
único de nivel; posiciones estimadas en EuroLeague, EuroCup, LBA y parte de la G League; traspasos de EuroLeague y
EuroCup en una fila; enlace de clubes LBA/LNB por nombre; 2026-27 provisional. Detalle, dificultades y mejoras
futuras en el artículo (secciones 6-8; el modelo de 6, sección 4.9).
