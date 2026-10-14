# Estilos de juego: VaDE con 6 estilos sin nivel y mapa 3D

> Código: `bbestilo/` · Artículo completo (PDF): [`docs/articulo/estilos_de_juego_baskonia.pdf`](articulo/estilos_de_juego_baskonia.pdf) ·
> Atlas interactivo: Artifact «Atlas de Estilos» (`artifact/mapa-estilos.html`, datos `artifact/estilos/`) ·
> Modelo final: `data/modelos/estilos/` · Iteraciones anteriores (métricas y asignaciones): `data/modelos/estilos/historial/`

```bash
pip install -r requirements-estilos.txt
python -m bbestilo entrenar     # VaDE, 10 semillas, consenso y ajuste fino, red de reserva y evaluación (≈ 20 min en 4 núcleos)
python -m bbestilo evaluar      # reevalúa la red guardada
python -m bbestilo analisis     # K, nivel, éxito, efecto del encaje, continuidad, ligas, Baskonia
python -m bbestilo encaje --jugador "Nombre" [--club baskonia] [--competicion euroleague] [--temporada 2025-26]
python -m bbestilo encaje --jugador "A" "B" [--minutos 900 700] [--baja "C"]    # varios fichajes y bajas a la vez
python -m bbestilo parecidos --club baskonia [--jugador "Nombre"] [--alcance 30] [--temporadas 2025-26 ...]
python -m bbestilo exportar     # datos del Atlas
python -m bbestilo articulo     # PDF
```

## 1. Iteraciones

| | v1 | v2 | v3 | **Final** |
|---|---|---|---|---|
| Estilos (neuronas de salida) | 12 | 8 | 6 | **6** |
| Nivel | dentro de los rasgos | neutralizado | neutralizado | **neutralizado** |
| Redes | IDEC y VaDE (diagonal) | VaDE (covarianza completa) + IDEC de contraste | ídem | **sólo VaDE** |
| Modelo final | semilla medoide | consenso de 5 semillas + ajuste fino | ídem | **consenso de 10 semillas + ajuste fino** |
| Nivel explicado por el estilo (η²) | 0,740 | 0,008 | 0,010 | **0,004** |
| Información estilo-liga (NMI) | 0,388 | 0,072 | 0,073 | **0,076** |
| Seguridad media de la asignación | 0,74 | 0,79 | 0,81 | **0,82** |
| Estilo más pequeño (clubes) | 33 | 47 | 127 | **139** |
| ARI entre semillas | 0,38 | 0,41 | 0,51 | **0,46** |
| Estabilidad del mapa (r) | 0,962 | 0,953 | 0,955 | **0,945** |
| Reproducibilidad temporal (ARI) | 0,37 | 0,40 | 0,55 | **0,45** |
| Robustez al reparto de minutos | 0,52 | 0,55 | 0,58 | **0,60** |
| Silueta en los 13 rasgos | 0,057 | 0,026 | 0,056 | **0,047** |
| Replicabilidad de perfiles (r) | 0,92 | 0,89 | 0,92 | **0,91** |

* **v1 → v2.** La vara EuroLeague arrastraba el nivel de cada liga al estilo: estilos «de liga» y 74 % del nivel
  explicado por el estilo. Se neutraliza el nivel y se refuerza VaDE.
* **v2 → v3.** BIC e ICL eligen 6 estilos y la estabilidad de k-medias cae a partir de 6: con 6 neuronas mejoran el
  acuerdo entre semillas, la reproducibilidad temporal y la separación.
* **v3 → final.** Se retira la IDEC y el consenso pasa de 5 a 10 semillas. La partición de la v3 no se sostenía
  frente a las 5 semillas nuevas (ARI 0,35; el modelo final, 0,54) ni frente al consenso de 10 (0,41; final 0,60):
  sus métricas de acuerdo eran optimistas. Frente a las 10 redes, el modelo final es el más central (ARI medio 0,49
  frente a 0,46). Las métricas de acuerdo bajan algo porque se miden sobre redes más diversas; ganan la seguridad,
  el tamaño mínimo, la robustez y la neutralidad. La partición final coincide sólo en parte con la v3 (ARI 0,42):
  la etiqueta de los clubes de frontera depende del conjunto de redes, por eso la distancia en el mapa es la medida
  más fiable.

## 2. Datos y neutralización

* Equivalentes EuroLeague 2025-26 del estudio de normalización (A+B; sólo A donde B no llega y en 2026-27),
  temporada regular, 8 ligas. 997 clubes-competición-temporada de entrenamiento (2020-21 a 2025-26) y 120
  provisionales (2026-27). 18.768 filas jugador-equipo.
* Vector de club = media de sus jugadores ponderada por minutos (13 rasgos: ritmo relativo a su liga, 3PAr, FTr,
  AST%, TOV%, rebote ofensivo y defensivo, robos, tapones y faltas por 100 posesiones, concentración del uso y
  cuotas de minutos de interiores y exteriores). Lineal en los minutos: fichajes y bajas se simulan de forma exacta.
* **Capa de nivel**: PER, Game Score/40, WS/40, ORtg, DRtg, puntos/100, TS% y eFG% → índice L. No entra en la red.
* **Neutralización**: `x̃ = (x − β₀ − β₁·L − β₂·L²) / s` por rasgo (clubes y jugadores con regresiones propias); el
  nivel se recalcula para cualquier reparto de minutos. Lo que el nivel explicaba antes (clubes): rebote defensivo
  74 %, faltas 71 %, AST% 64 %, FTr 58 %.

## 3. La red

* Codificador `13 → 64 → 32 → (μ, log σ²) ∈ ℝ³` (GELU); μ = punto en el mapa. Decodificador `3 → 32 → 64 → 13` con
  varianza común. **Capa de salida: 6 neuronas** = probabilidad a posteriori de 6 gaussianas de covarianza completa.
* Pérdida: −ELBO de VaDE + 13 · estrés de MDS métrico (distancia del mapa = distancia del perfil, escala fija).
* Entrenamiento: clubes + 24 plantillas remuestreadas por club (minutos × Gamma(4, 1/4)) + jugadores (peso 0,3, no
  definen estilos); preentreno, mezcla inicial por EM, paso M amortiguado (π uniforme, suelo de varianza, resiembra).
* **Consenso de 10 semillas** (co-asociación, enlace medio); la semilla más cercana (23) se ajusta 40 épocas con la
  mezcla fijada en el consenso. ARI del modelo final con el consenso 0,60.

## 4. Los 6 estilos (nombres en `config/estilos.json`)

| | Estilo | Rasgos | Clubes |
|---|---|---|---|
| E01 | Perímetro y presión | quintetos pequeños, triple, robos, uso concentrado; pocas pérdidas, muy poco rebote defensivo | 147 |
| E02 | Pausado y seguro | ritmo bajo, muy pocas pérdidas y pocas asistencias, triple, pocos tiros libres | 139 |
| E03 | Pintura física | interiores, rebote ofensivo, muchas faltas; pocas asistencias | 169 |
| E04 | Exterior y riesgo | bases y escoltas, robos, tiros libres, asistencias; más pérdidas y faltas | 176 |
| E05 | Ritmo y juego limpio | ritmo alto, muy pocas faltas y poca presión, rebote defensivo | 195 |
| E06 | Ataque al aro | penetración, tiros libres, asistencias, rebote defensivo; muy poco triple | 171 |

## 5. Hallazgos (`analisis.json`)

* **Número de estilos.** BIC e ICL eligen 6.
* **Estilo y éxito.** A igual nivel, el estilo explica el 24 % del net rating restante (η² parcial, p < 0,001):
  «Perímetro y presión» +0,42 σ, «Ataque al aro» −0,81 σ. Parte es mecánica (cuatro factores).
* **Efecto del encaje.** 2.214 cambios de club: parecerse al estilo del destino no mejora el rendimiento
  (+0,038 de nivel por unidad de distancia, p < 0,001, signo contrario al del encaje), compatible con fichajes de
  complementariedad.
* **Continuidad.** Cada +10 puntos de minutos que repiten multiplican por 1,18 la odds de conservar el estilo; cuartil
  más bajo 31 %, más alto 50 %.
* **Ligas.** Estilo × liga: V de Cramér 0,24; estilo × temporada: V 0,08 (p = 0,08).
* **Baskonia.** EuroLeague 2025-26 «Ritmo y juego limpio» (también en 2021-22, 2023-24 y 2024-25); Liga Endesa
  2025-26 «Exterior y riesgo». Sus cambios de estilo entre temporadas están entre los más grandes (percentiles 65-90).

## 6. Herramientas

* **Simulación de fichajes y bajas** (`encaje.simular_plantilla`, Atlas «Simular fichajes»): los minutos totales del
  club no cambian; los que siguen se reescalan a prorrata, cada fichaje entra con su perfil (y el ritmo del destino).
  Resultado: estilo antes y después, desplazamiento en el mapa, encaje de cada fichaje, minutos por estilo y
  dispersión de la plantilla. El Atlas guarda escenarios en el navegador.
* **Buscador de parecidos** (`similares.py`, CLI `parecidos`, Atlas «Buscar parecidos»): distancias en los 13 rasgos
  sin nivel, como percentil entre parejas reales. Clubes que juegan como el de referencia; jugadores parecidos a uno
  dado o que encajan con el estilo del club, opcionalmente sólo en los clubes más parecidos.
* La red se ejecuta en el navegador con los pesos exportados (comprobado: diferencia máxima 0,005 en el mapa; una
  simulación de 2 fichajes y 1 baja, 0,004).

## 7. Atlas de Estilos

Resumen ejecutivo arriba y cinco pestañas: **Comparar clubes** (mapa 3D con filtros de temporada, liga, estilo, nivel,
posición y minutos; capas; color, tamaño y etiquetas; comparador de hasta 4 equipos o ligas con perfil, reparto y
distancias), **Simular fichajes** (club, bajas y varios fichajes con sus minutos; escenarios guardados), **Buscar
parecidos**, **Ligas y estilos** (liga × estilo, temporadas, Baskonia, tarjetas de los 6 estilos) y **Hallazgos y
modelo** (pruebas y evolución de las iteraciones). Descarga del artículo en PDF.

## 8. Riesgos y limitaciones

Estilo continuo (leer la probabilidad y la distancia, no sólo la etiqueta); el encaje no predice rendimiento; la
simulación supone que el jugador lleva su perfil al nuevo club; rasgos de jugador en pista, no del sistema del
entrenador; neutralización lineal-cuadrática en un índice único de nivel; posiciones estimadas en algunas ligas;
2026-27 provisional. Tabla de riesgos y mejoras del modelo y del proyecto en el artículo (secciones 10 y 11).
