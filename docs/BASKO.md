# Federación Vasca de Baloncesto · pauta de extracción (`bbstats.esf`)

Capa del repositorio que extrae, de forma completa y reproducible, las estadísticas de las competiciones de la
Federación Vasca (ESF · Euskal Saskibaloi Federazioa) publicadas en
[basketbasko.com · Resultados - Federación Vasca](https://basketbasko.com/es/competicion-esf/), desde **2018-19**
hasta la temporada en curso (**2026-27**). Todo nace del **jugada a jugada de cada partido**; el acta digital sirve de
control y de respaldo.

## 1. Cómo se ejecuta (sólo cuando se pulsa EJECUTAR)

No hay ninguna tarea programada: la actualización periódica ocurre únicamente al ejecutar.

```bash
python ejecutar_basko.py                       # EJECUTAR: todas las ligas activas, temporada en curso
python ejecutar_basko.py esf_jun esf_cad       # sólo esas ligas
python ejecutar_basko.py --temporada 2024-25   # otra temporada (sólo esa)
python -m bbstats.esf historico                # carga histórica 2018-19 … 2026-27 (de la más reciente a la más antigua)
python -m bbstats.esf reprocesar               # regenera toda la salida desde los brutos, SIN red
python -m bbstats.esf artifact                 # datos del Artifact «Kerno Basque Analytics»
python -m pytest -q tests/test_esf.py
```

Desde el Artifact **Kerno Basque Analytics** (https://claude.ai/artifact/5bU3CLLhW7i3K9pcQyaSX7): botón «Ejecutar» de la
cabecera, que lanza la tarea bajo demanda «EJECUTAR Kerno Basque Analytics» (`trig_01Tmstsk4KswuUPmpBjhHgKf`, sin
programación): abre una sesión de Claude Code que actualiza la temporada elegida, sube los datos a FTAB y vuelve a
publicar los datos de la página. Código de la página: `artifact/kerno-basque/index.html` (datos:
`python -m bbstats.esf artifact` → `data/basko/artifact/`).

También desde GitHub: pestaña *Actions* → «EJECUTAR Federación Vasca» → *Run workflow*
(`.github/workflows/ejecutar_basko.yml`, sólo manual). Cada ejecución descarga **sólo lo nuevo** (partidos ya guardados
con acta no se vuelven a pedir) y regenera la salida de esa temporada.

## 2. Arquitectura por capas

| Capa | Módulo | Qué hace |
|---|---|---|
| 1 · Extractores por fuente | `bbstats/esf/extractor.py` (`EsfAdapter`), `cliente.py` | Un adaptador por liga, configurado en `config/basko.json`. Lee de la página pública las URL de la API que usa su widget y recorre categoría → fases → grupos → calendario → acta + jugada a jugada de cada partido + fichas de equipo |
| 2 · Almacén bruto | `bbstats/raw_store.py` | `data/basko/raw/<liga>/<temporada>/<liga>_<temporada>_<YYYYmmddTHHMMSSZ>.json.gz`: respuestas originales **sin tocar**, con fecha, de sólo lectura. Incremental (paquetes de 350 partidos); `reprocesar` trabaja sólo con estos ficheros |
| 3 · Normalización (jugada a jugada) | `bbstats/esf/eventos.py` | Catálogo completo de acciones (códigos 92–600 del propio widget), eventos normalizados con reloj y marcador, posesiones, zonas de tiro, clutch, quintetos (`bbstats/lineups`) |
| 4 · Métricas | `bbstats/metrics.py` (común a las 20+ ligas del repositorio) + `bbstats/esf/construir.py` | Mismas fórmulas que el resto de ligas (Hollinger, Dean Oliver, Basketball-Reference) por fase × división y totales |
| 5 · Salida unificada | `data/basko/processed/<temporada>/` | Mismas columnas en todas las ligas y temporadas |

### Ligas (adaptadores) — sólo categorías MASCULINAS

| Código | Competición | Categoría web (`idCategory`) | Divisiones |
|---|---|---|---|
| `esf_1nac` | Primera Nacional Masculina (1ª División Masculina) | 46 | única |
| `esf_2nac` | Segunda Nacional Masculina (2ª División Masculina) | 3 | única |
| `esf_jun` | Liga Vasca Junior Masculina | 54 | **A1 y A2** |
| `esf_cad` | Liga Vasca Cadete Masculina | 29 | **A1 y A2** |
| `esf_jun_sel`, `esf_cad_sel` | Campeonatos interterritoriales de selecciones (Junior / Cadete) | 74+100 / 71+101 | desactivadas (no son la Liga Vasca); `activa: true` para extraerlas aparte |

## 3. Fases y divisiones (Junior y Cadete)

- **Fase** = competición de la web normalizada (`primera_fase`, `fase_clasificacion`, `segunda_fase`, `tercera_fase`,
  `copa`, `liga_regular`, `final_a_cuatro`…); el nombre original va en `fase_nombre`, el tipo en `fase_tipo`
  (liga · clasificación · eliminatoria · copa) y el orden cronológico en `fase_orden`.
- **División** (`division`): en Junior y Cadete **A1 y A2 son divisiones distintas**. Reglas (`config/basko.json →
  reglas_division`): Segunda Fase grupo A-1 = A1, grupo A-2 = A2; Primera Fase, Tercera Fase, Copa, Final a Cuatro y
  Cruces = A1; un partido sin regla (Fase de Clasificación) toma la división de sus dos equipos y, si son de divisiones
  distintas, `cruce`. Ligas senior: `única`.
- **Unidades de agregación** (filas de `jugadores` y `equipos`): cada **fase × división** (contexto de liga propio:
  PER = 15 y USG% = 20 dentro de cada unidad), `total` = **todas las fases y divisiones juntas** (evaluación anual del
  jugador y del club) y, en Junior/Cadete, `total_a1` y `total_a2` (cada división por separado; los cruces sólo cuentan
  en `total`). Para analizar equipos por división, filtrar `division`.

## 4. Salida (`data/basko/processed/<temporada>/`)

| Fichero | Fila | Contenido |
|---|---|---|
| `jugadores/<liga>.csv` | jugador-equipo-fase-división | 480 columnas del esquema común (`bbstats/schema.py`) + extensiones ESF + on/off (`pbp_*`) — **673 columnas idénticas en todas las ligas** |
| `equipos/<liga>.csv` | equipo-fase-división | récord, puntos, posesiones, ritmo, ORtg/DRtg/Net, cuatro factores propios y del rival, tipos de punto, zonas de tiro, quintetos, entrenadores |
| `partidos/<liga>.csv` | partido | calendario completo (también 2018-19 a 2021-22), fase, grupo, división, jornada, pabellón, marcador y validación |
| `boxscores/<liga>.csv.gz` | jugador-partido | boxscore de la cronología, minutos exactos, +/- en pista, valoración oficial, zonas, clutch, Game Score |
| `eventos/<liga>.csv.gz` | acción | jugada a jugada normalizado: periodo, reloj, segundos transcurridos, equipo, jugador, acción, tipo, marcador, clutch, coordenadas y zona |
| `tiros/<liga>.csv.gz` | tiro de campo | coordenadas, zona, distancia, contraataque, segunda oportunidad, tras pérdida, clutch, margen previo |
| `plantillas/<liga>.csv` | licencia | jugadores y entrenadores de cada equipo con licencia y uuid de persona |
| `quintetos/<liga>/` | — | quintetos, tríos, parejas, on/off, RAPM, asistencias, equipos, validación y tramos (`division_A1/`, `division_A2/` en Junior y Cadete) |
| `indice.json`, `completitud.csv`, `diccionario_columnas.csv` | — | índice, % de filas con dato por columna × (liga, fase, división), descripción de cada columna |

Convenciones: porcentajes 0–100; **dato no publicado o no registrado por la mesa = vacío, nunca 0**; ninguna fila ni
columna se elimina. Identidad: `player_id` = uuid de la persona federada del acta (estable entre partidos, equipos y
temporadas; `fnb_…` para licencias navarras); si falta, licencia de la temporada o `n-<equipo>-<nombre>`.

### Extensiones de la capa ESF (además del esquema común)

`division`, `categoria`, `nivel`, `fase_nombre`, `fase_tipo`, `fase_orden`, `grupos`, `club`, `cobertura`,
`partidos_con_acta`, `partidos_pbp`, `persona_uuid`, `licencia_id`, minutos exactos (`min_pbp`) y del acta, faltas por
tipo, `and1`, zonas de tiro (aro, pintura, media distancia, triple de esquina y frontal: intentos, aciertos, % y
frecuencia; distancia media), puntos por cuarto, **clutch** (últimos 5 min, ±5), % de puntos al contraataque, de segunda
oportunidad y tras pérdida, regularidad (desviación típica de puntos y Game Score, máximos, partidos de 10/20 puntos),
`registra_asistencias`, `registra_tapones` y on/off `pbp_*` (net en pista y fuera, on−off, ajustado por muestra y por suerte, RAPM, relevos,
minutos por cuarto, quintetos distintos, clutch). Lista completa en `diccionario_columnas.csv`.

### Asistencias, tapones y mates (registro parcial según la temporada)

La mesa de la Federación Vasca no siempre registra asistencias, tapones y mates. Partidos con cada dato registrado:

| Temporada | Asistencias | Tapones | Mates |
|---|---|---|---|
| 2022-23 a 2024-25 | ninguno | ninguno | algunos |
| 2025-26 | ninguno | ≈ 40 % de los partidos | algunos |
| 2026-27 | prácticamente todos | prácticamente todos | algunos |

La detección es por partido: un dato se considera registrado en un partido si algún equipo tiene un valor > 0.
Norma aplicada:

- Los **conteos no medidos** quedan vacíos, nunca 0: `ast`, `blk`, `blka`, `dunks` (y sus versiones por partido,
  por 40 y por 100) se suman sólo con los partidos en que la mesa los registró; si no hay ninguno, vacíos. Lo mismo los
  ratios que sólo miden eso (`ast_pct`, `ast_to`, `ast_ratio`, `ast_share`, `blk_pct`, `dunk_rate`…).
- Las **métricas compuestas se calculan siempre**, en sus columnas canónicas: PER y uPER, ORtg/DRtg de Dean Oliver,
  Net, Floor%, puntos producidos, posesiones individuales, stops, Win Shares (OWS, DWS, WS, WS/40), Game Score, EFF, PIE
  y TOV ratio. Las componentes no registradas entran con valor 0, igual para todos los jugadores, equipos y rivales de la
  unidad, de modo que el contexto y la normalización (PER medio = 15) se mantienen. Cuando todo está registrado
  (2026-27) el cálculo es exactamente el estándar.
- `registra_asistencias` y `registra_tapones` indican en cada fila si hubo partidos con ese dato registrado.
- Interpretación: dentro de una misma temporada las métricas son plenamente comparables entre jugadores, fases y
  divisiones. Entre temporadas con distinto registro (p.ej. 2025-26 frente a 2026-27), o frente a otras ligas, el PER y
  el ORtg de pasadores y taponadores no incluyen esas acciones en las temporadas sin registro.

## 5. Del jugada a jugada a las métricas

1. Cada acción se normaliza (catálogo de acciones del propio widget: canastas de 1/2/3, palmeos, mates, rebotes,
   robos, pérdidas, tapones, asistencias, faltas por tipo, cambios, tiempos muertos, fin de periodo…).
2. Conteos por jugador y partido desde la cronología. **Control: deben coincidir con el acta**; si un partido no
   cuadra con el marcador del acta, su boxscore sale del acta (`fuente_box`, `pbp_cuadra_marcador`).
3. Quién está en pista (entradas/salidas) → tramos → minutos exactos, +/- en pista, quintetos, on/off y RAPM (motor
   común `bbstats/lineups`). Control: +/- reconstruido = +/- del acta.
4. Totales de equipo = suma de la cronología + lo que sólo es de equipo (rebotes y pérdidas de equipo del acta).
5. Métricas por unidad (fase × división, totales) con el motor común.

Heurísticas declaradas (no las publica la fuente): posesión (cambia con canasta o último tiro libre anotado, rebote
defensivo, pérdida/robo y fin de periodo), puntos tras pérdida, segunda oportunidad, contraataque (≤ 8 s tras recuperar
o marca de la mesa), clutch (últimos 5 min del 4.º/prórroga con ±5) y zonas de tiro (pista FIBA 28 × 15 m; la
calibración clasifica bien el 99,9 % de 21.004 tiros de 2026-27 como de 2 o de 3).

### Validación con datos reales (2025-26)

- Cronología = acta en el 100 % de los partidos (puntos, tiros, rebotes, robos, pérdidas y faltas por jugador).
- +/- reconstruido = +/- del acta en todos los partidos con cambios registrados.
- Invariantes por unidad: PER medio ponderado por minutos = 15,0; USG% medio ≈ 20.
- Win Shares (`ws`) ≈ victorias: Junior 155,6 / 153; Primera Nacional 200,1 / 199.
- Minutos del acta: enteros (redondeados por la mesa); los minutos exactos salen de la cronología (`min_pbp`).

## 6. Cobertura y limitaciones

| Temporadas | Qué hay |
|---|---|
| 2018-19 a 2021-22 | La web **sólo publica calendario, resultados y plantillas** (no existe acta digital): partidos, clasificaciones y récords de equipo por fase y división; jugadores de las plantillas con `cobertura = sin_acta_digital` y estadísticas vacías |
| 2022-23 a 2026-27 | Acta digital + jugada a jugada en prácticamente todos los partidos: todas las métricas |

- Sin edad, altura, peso, posición ni nacionalidad: la fuente no los publica (columnas vacías).
- Asistencias y tapones sólo donde la mesa los registra (2026-27 completo; tapones en parte de 2025-26); las métricas compuestas se calculan siempre (ver §4).
- Los equipos navarros de Primera/Segunda Nacional no tienen ficha en la ESF (plantilla vacía; sí juegan y tienen
  estadísticas).
- Clave de la API: la que la propia página pública entrega a cualquier visitante; se relee en cada ejecución.

## 7. Cargar los datos (Python)

```python
import pandas as pd
j = pd.read_csv("data/basko/processed/2025-26/jugadores/esf_jun.csv", low_memory=False)
a1 = j[(j.fase == "total_a1")]                       # División A1, todas sus fases
por_fase = j[(j.division == "A2") & (j.fase != "total_a2")]
total = j[j.fase == "total"]                          # todas las fases y divisiones
```

Todas las ligas y temporadas tienen las mismas columnas: se concatenan sin transformaciones.

## Kerno Basque Analytics: misma tipología que «Kerno Analytics · Equipos»

El Artifact https://claude.ai/artifact/5bU3CLLhW7i3K9pcQyaSX7 replica el sitio general de equipos sobre las cuatro
ligas vascas (Primera y Segunda Nacional, Junior y Cadete; 2022-23 en adelante, con jugada a jugada):

- **Lectura** (tu equipo hoy: diferencial, ratings, Nivel Kerno de la plantilla, banquillo, cuatro factores, estilo).
- **01 Diagnóstico**: evaluación, rotación, quintetos, parejas y tríos, conexiones, impacto en pista, la liga e
  **informe de equipo en PDF** (14 páginas: identidad, veredicto, huella del entrenador con **tiempos muertos**,
  rotación, ataque, defensa y stops, quintetos de referencia, red de pases, glosario).
- **02 Estilos**: los seis estilos unificados (Pistons, Isolation, Old-School, Spacing, Circulación, Pintura), con
  los doce rasgos medidos frente a su propia liga, y el mapa de estilos.
- **03 Jugadores**: Nivel Kerno de la liga, ficha (percentiles, trayectoria) y lista corta con comparativa.
- **04 Federación Vasca**: la vista anterior (tabla de jugadores, clasificación por fase, fases, calidad, extracción).
- Ikurriña en miniatura en la esquina de la barra de filtros (única diferencia visual con el sitio general).

**Nivel Kerno vasco** (`bbstats/esf/kerno.py::nivel_kerno`), sin simulador ni puente entre ligas: Producción = media
de la puntuación normal por rangos (frente a su liga y temporada, contraída con k = 300 min) de PER, WS/40, GmSc/40 y
PIE; Impacto = la de RAPM y on/off ajustado; NK = 0,6·P + 0,4·I re-estandarizado y llevado a 0–100 con
50 + 50·tanh(z/2); rango del 80 % = z ± 1,2816·√(300/(min+300)).

Regenerar y montar:

    python -m bbstats.esf artifact          # vista Federación Vasca  → data/basko/artifact/datos
    python -m bbstats.esf kerno             # equipos, quintetos, estilos, Nivel Kerno, Atlas → data/basko/artifact/sitio
    python artifact/kerno-basque/montar.py  # publicacion/kerno-basque/ + publicacion/kerno-basque.json (lista para publicar)

Código del sitio: `artifact/kerno-basque/sitio/` (`_build.py` ensambla `index.html`); las páginas `quintetos/` y
`atlas/` son las del sitio general con los parches de `artifact/kerno-basque/parches/`.
