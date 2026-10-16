# Estilos de juego: VaDE con 6 estilos sin nivel, 17 rasgos (con jugada a jugada) y mapa 3D

> Código: `bbestilo/` · Artículo completo (PDF): [`docs/articulo/estilos_de_juego_baskonia.pdf`](articulo/estilos_de_juego_baskonia.pdf) ·
> Atlas interactivo: Artifact «Atlas de Estilos» (`artifact/mapa-estilos.html`, datos `artifact/estilos/`) ·
> Modelo final: `data/modelos/estilos/` · Iteraciones anteriores (métricas y asignaciones): `data/modelos/estilos/historial/`

```bash
pip install -r requirements-estilos.txt
python -m bbestilo barrido      # número de estilos (BIC/ICL y k-medias) antes de entrenar
python -m bbestilo entrenar     # VaDE, 10 semillas, consenso y ajuste fino, red de reserva y evaluación (≈ 60 min en 4 núcleos)
python -m bbestilo quimica      # química de estilos: efectos X → Y y sinergia estilo × estilo (docs/contexto_y_quimica.md)
python -m bbestilo evaluar      # reevalúa la red guardada
python -m bbestilo analisis     # K, nivel, éxito, efecto del encaje, continuidad, ligas, Baskonia
python -m bbestilo encaje --jugador "Nombre" [--club baskonia] [--competicion euroleague] [--temporada 2025-26]
python -m bbestilo encaje --jugador "A" "B" [--minutos 900 700] [--baja "C"]    # varios fichajes y bajas a la vez
python -m bbestilo parecidos --club baskonia [--jugador "Nombre"] [--alcance 30] [--temporadas 2025-26 ...]
python -m bbestilo exportar     # datos del Atlas
python -m bbestilo articulo     # PDF
```

## 1. Iteraciones

| | v1 | v2 | v3 | v4 | **Final** |
|---|---|---|---|---|---|
| Rasgos | 13 | 13 | 13 | 13 de caja | **17 (13 + 4 del jugada a jugada)** |
| Estilos (neuronas de salida) | 12 | 8 | 6 | 6 | **6** |
| Nivel | dentro de los rasgos | neutralizado | neutralizado | neutralizado | **neutralizado** |
| Modelo | semilla medoide | consenso de 5 + ajuste fino | ídem | consenso de 10 + ajuste fino | **consenso de 10 + ajuste fino** |
| Nivel explicado por el estilo (η²) | 0,740 | 0,008 | 0,010 | 0,004 | **0,014** |
| Información estilo-liga (NMI) | 0,388 | 0,072 | 0,073 | 0,076 | **0,103** |
| Seguridad media de la asignación | 0,74 | 0,79 | 0,81 | 0,82 | **0,79** |
| Estilo más pequeño (clubes) | 33 | 47 | 127 | 139 | **135** |
| ARI entre semillas | 0,38 | 0,41 | 0,51 | 0,46 | **0,52** |
| Estabilidad del mapa (r) | 0,962 | 0,953 | 0,955 | 0,945 | **0,979** |
| Reproducibilidad temporal (ARI) | 0,37 | 0,40 | 0,55 | 0,45 | **0,55** |
| Robustez al reparto de minutos | 0,52 | 0,55 | 0,58 | 0,60 | **0,60** |
| Silueta en los rasgos | 0,057 | 0,026 | 0,056 | 0,047 | **0,067** |
| Replicabilidad de perfiles (r) | 0,92 | 0,89 | 0,92 | 0,91 | **0,94** |

* **v1 → v2.** La vara EuroLeague arrastraba el nivel de cada liga al estilo: estilos «de liga» y 74 % del nivel
  explicado por el estilo. Se neutraliza el nivel y se refuerza VaDE.
* **v2 → v3.** BIC e ICL eligen 6 estilos y la estabilidad de k-medias cae a partir de 6.
* **v3 → v4.** Se retira la IDEC y el consenso pasa de 5 a 10 semillas (modelo final anterior; guardado en
  `historial/v4_6estilos_box/`, nombres en su `nombres.json`).
* **v4 → final: jugada a jugada.** Entran 4 rasgos del jugada a jugada normalizados a la EuroLeague como los de caja:
  % de tiros en el aro, % de media distancia, % de triples de esquina y % de canastas propias asistidas (zonas con
  coordenadas calibradas en las 8 fuentes; `docs/contexto_y_quimica.md`). El barrido previo (`barrido_k.json`) vuelve a
  elegir 6 estilos (ICL; la estabilidad de k-medias cae después de 6). El modelo gana en estabilidad del mapa (0,98),
  acuerdo entre semillas, reproducibilidad temporal, separación y replicabilidad, y sigue siendo neutral al nivel
  (η² 0,014). La partición cambia mucho (ARI 0,14 con la v4): dónde tira un equipo y cuánto depende del pase
  redefinen los estilos, por eso tienen nombres nuevos.

## 2. Datos y neutralización

* Equivalentes EuroLeague 2025-26 del estudio de normalización (A+B; sólo A donde B no llega y en 2026-27),
  temporada regular, 8 ligas. 997 clubes-competición-temporada de entrenamiento (2020-21 a 2025-26) y 120
  provisionales (2026-27). 18.768 filas jugador-equipo.
* Vector de club = media de sus jugadores ponderada por minutos (17 rasgos: ritmo relativo a su liga, 3PAr, FTr,
  AST%, TOV%, rebote ofensivo y defensivo, robos, tapones y faltas por 100 posesiones, concentración del uso,
  cuotas de minutos de interiores y exteriores y, del jugada a jugada, % de tiros en el aro, % de media distancia,
  % de triples de esquina y % de canastas asistidas). Lineal en los minutos: fichajes y bajas se simulan de forma exacta.
* **Capa de nivel**: PER, Game Score/40, WS/40, ORtg, DRtg, puntos/100, TS% y eFG% → índice L. No entra en la red.
* **Neutralización**: `x̃ = (x − β₀ − β₁·L − β₂·L²) / s` por rasgo (clubes y jugadores con regresiones propias); el
  nivel se recalcula para cualquier reparto de minutos. Lo que el nivel explicaba antes (clubes): rebote defensivo
  74 %, faltas 71 %, AST% 64 %, FTr 58 %.

## 3. La red

* Codificador `17 → 64 → 32 → (μ, log σ²) ∈ ℝ³` (GELU); μ = punto en el mapa. Decodificador `3 → 32 → 64 → 17` con
  varianza común. **Capa de salida: 6 neuronas** = probabilidad a posteriori de 6 gaussianas de covarianza completa.
* Pérdida: −ELBO de VaDE + 17 · estrés de MDS métrico (distancia del mapa = distancia del perfil, escala fija).
* Entrenamiento: clubes + 24 plantillas remuestreadas por club (minutos × Gamma(4, 1/4)) + jugadores (peso 0,3, no
  definen estilos); preentreno, mezcla inicial por EM, paso M amortiguado (π uniforme, suelo de varianza, resiembra).
* **Consenso de 10 semillas** (co-asociación, enlace medio); la semilla más cercana (23) se ajusta 40 épocas con la
  mezcla fijada en el consenso. ARI del modelo final con el consenso 0,60.

## 4. Los 6 estilos (nombres en `config/estilos.json`)

| | Estilo | Rasgos | Clubes |
|---|---|---|---|
| E01 | Creación individual | poco triple (casi ningún triple de esquina), media distancia, tiros libres, canastas sin asistencia; rebote defensivo y tapones | 207 |
| E02 | Pintura física | tiros en el aro y tiros libres, rebote ofensivo, interiores, faltas y robos; poco triple, más pérdidas | 135 |
| E03 | Pausado y seguro | muy pocas pérdidas, pocas asistencias y pocos bases; defensa conservadora; canastas de pase | 160 |
| E04 | Lejos del aro | muy pocos tiros cerca de la canasta, media distancia y triple, poco rebote ofensivo y pocos tiros libres | 153 |
| E05 | Exterior y presión | bases y escoltas, ritmo, presión y robos, asistencias y creación propia; poco rebote | 138 |
| E06 | Circulación y triple | mucho triple, sobre todo de esquina, canastas asistidas, sin media distancia; poco rebote defensivo | 204 |

## 5. Hallazgos (`analisis.json`, `interacciones.json`)

* **Número de estilos.** ICL elige 6 (BIC plano entre 6 y 11).
* **Estilo y éxito.** A igual nivel, el estilo explica el 13,7 % del net rating restante (η² parcial, p < 0,001):
  «Circulación y triple» +0,44 σ, «Creación individual» −0,56 σ. Parte es mecánica (cuatro factores).
* **Efecto del encaje.** 2.214 cambios de club: parecerse al estilo del destino no mejora el rendimiento
  (+0,049 de nivel por unidad de distancia, signo contrario al del encaje), compatible con fichajes de complementariedad.
* **Continuidad.** Cada +10 puntos de minutos que repiten multiplican por 1,16 la odds de conservar el estilo.
* **Baskonia.** EuroLeague 2025-26 «Exterior y presión»; Liga Endesa 2025-26 «Circulación y triple».
* **Química de estilos** (detalle en `docs/contexto_y_quimica.md`): un compañero mejor quita tiros pero los da mejores
  («efecto MVP»: cuota de tiro −0,77, eFG% +0,40, % asistidas +1,33 por unidad de nivel); «Creación individual» quita
  tiros al resto; dos «Circulación y triple» suman +1,0 de sinergia por 100 posesiones y dos «Creación individual» −1,0.

## 6. Herramientas

* **Simulación de fichajes y bajas** (`encaje.simular_plantilla`, Atlas «Simular fichajes»): los minutos totales del
  club no cambian; los que siguen se reescalan a prorrata, cada fichaje entra con su perfil (y el ritmo del destino).
  Resultado: estilo antes y después, desplazamiento en el mapa, encaje de cada fichaje, minutos por estilo y
  dispersión de la plantilla. El Atlas guarda escenarios en el navegador.
* **Buscador de parecidos** (`similares.py`, CLI `parecidos`, Atlas «Buscar parecidos»): distancias en los 17 rasgos
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
