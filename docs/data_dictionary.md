# Diccionario de datos

Todas las tablas del repositorio: dónde están, qué es una fila (grano), qué la identifica (clave), qué significa cada
columna, en qué unidades y qué banderas lleva. Recuentos de filas a 23-10-2026 (cambian con cada carga; para las
tablas por temporada se indica el fichero de ejemplo). Las tablas de la fase 8 (simulador) se completarán con su
informe (`docs/checkpoints/F8.md`).

## 0. Convenciones

* **Formato**: CSV (UTF-8, separador coma, punto decimal); `.csv.gz` = CSV comprimido (pandas los lee igual); JSON
  para resúmenes y fichas. Ningún fichero versionado pasa de 40 MB (las tablas grandes se parten por temporada).
* **Dato ausente** = vacío (NaN), **nunca 0**. Una categoría que una fuente no publica queda vacía y, donde importa,
  con una bandera (`*_desconocido`, `categorias_faltantes`, `sin_L`, `sin_ast`…).
* **Porcentajes**: las columnas `*_pct` del esquema de caja y de los modelos están en **0-100** (USG%, TS%, AST%…),
  salvo las que se indican como fracción **0-1** (MIN%, GS%, CLOSE%, cuotas, probabilidades, `p_*`).
* **Tasas**: `*_p100` = por 100 posesiones del equipo con el jugador en pista; `*_p40` = por 40 minutos.
* **Unidades de nivel**: DT de capacidad EuroLeague (EuroLeague = 0 en cada temporada); `L` = índice de nivel
  compuesto en esa escala; escalas de lectura ±100 = `100·tanh(z/2)`.
* **Minutos**: los roles se definen sobre 40' (MIN% = minutos / duración real del partido, con prórrogas; 48' en NBA
  y G League). `m_i` del libro de rol = minutos por partido **del equipo**.
* **Temporada** `AAAA-AA` (2020-21 … 2026-27; 2026-27 en curso: marcada `provisional`, `temporada_en_curso` o
  `en_curso` según la tabla).

## 1. Claves e identidades

| Clave | Qué identifica | Notas |
|---|---|---|
| `liga` | competición (15): `euroleague`, `eurocup`, `acb`, `nba`, `gleague`, `lba`, `bbl`, `lnb`, `bcl`, `fec`, `bsl`, `gbl`, `feb1`, `feb2`, `feb3` | cada código FEB es una serie histórica (nombres antiguos en `config/competition_aliases.json`) |
| `player_id` | jugador **dentro de una liga** (id de la fuente) | `player_uid` = `<liga>:<player_id>`. BBL cambia de id por equipo y temporada; BSL/GBL usan nombre normalizado; FEB usa el id de persona FEB (común a las tres FEB) |
| `persona_id` | persona entre ligas | `player_id_crosswalk.csv` (confianza ≥ 0,75) + unión por nombre del algoritmo A; puede cambiar si se reconstruye el crosswalk |
| `team_id` | equipo en una liga-temporada | FEB: id de inscripción (cambia cada año; club estable = `equipo_codigo`); EuroLeague/EuroCup juntan traspasados (`ASV;ULK`) |
| `club` | club estable entre temporadas (libro de rol) | `team_id`, salvo FEB (código de club) |
| `game_id` | partido | el mismo en `quintetos/`, `entrenadores/`, `feb/` y `roles/partidos_jugador/` |
| `entrenador_id` | entrenador | slug del nombre + `config/entrenadores_alias.json`; común a todas las ligas |
| `fase` | `regular`, `playoffs`, `total` (caja) | los modelos de rol usan regular + playoffs; estilos unificados, sólo regular |

## 2. Datos procesados (`data/processed/`)

### `data/processed/<temporada>/ligas/<liga>.csv`

**Estadísticas de temporada por fase.** Grano: jugador × equipo × liga × temporada × fase. Clave: `liga, temporada,
fase, player_id, team_id`. 480 columnas idénticas en todas las ligas (orden y descripción en
`data/processed/<temporada>/diccionario_columnas.csv`, generado de `bbstats/schema.py`; completitud por liga y fase
en `completitud.csv`). Grupos: `identidad` (23), `totales` (32), `por_partido` (28), `por_36`, `por_40`, `por_100_pos`
(27 cada uno: `<stat>_pg`, `_p36`, `_p40`, `_p100`), `tiro` (19), `ratios` (22, en %), `ratings` (23: PER, ORtg/DRtg,
WS, PIE…), `contexto_equipo` (21, `team_*`), `contexto_rival` (18, `opp_*`), `contexto_liga` (9, `lg_*`),
`metricas_fuente` (96, `src_*`: cifras oficiales de cada fuente, no comparables entre fuentes), `basketnews` (67,
`bn_*`: EuroLeague y ACB desde 2024-25) y `contexto_fase` (41: `rs_*` y `delta_*` en las filas de playoffs).
Banderas: `calidad_contexto` (`completo` / `parcial` / `sin_contexto`), `minutos_partido` (40/48). Fórmulas:
`CONTEXTO_AGENTE.md` §6.

Otros ficheros por temporada: `indice.json` (ligas, filas por fase, fecha), `informe_ejecucion.json` (estado de cada
liga), `informes/` (no versionado); global: `data/processed/temporadas.json`.

### `data/processed/<temporada>/quintetos/<liga>/`

**Capa de jugada a jugada** (`bbstats/lineups`). Todas las métricas por fase (`regular`, `playoffs`, `total`) y por
equipo; detalle de métricas en `CONTEXTO_AGENTE.md` §9b.

| Fichero | Grano | Clave | Contenido |
|---|---|---|---|
| `tramos.csv.gz` | tramo de juego sin cambios (partido × periodo × intervalo) | `game_id, periodo, t0` | quintetos de los dos equipos, segundos, margen al empezar, banderas `clutch` y `basura`, conteos de caja de cada equipo en el tramo (`a_*`, `b_*`) |
| `tiros.csv.gz` | tiro | `game_id, periodo, t, player_id` | tipo, anotado, puntos, asistente, coordenadas `x, y` (sistema de la fuente; zonas calibradas en `bbmodel/zonas.py`), quintetos y margen previo |
| `quintetos.csv.gz`, `trios.csv.gz`, `parejas.csv.gz` | unidad (5, 3 o 2 jugadores) × equipo × fase | jugadores de la unidad + `team_id, fase` | minutos, posesiones, ratings, `*_aj` (contracción k = 300 posesiones), cuatro factores, suerte, `net_esperado` y sinergia (RAPM) |
| `jugadores.csv` | jugador × equipo × fase | `player_id, team_id, fase` | on/off, RAPM (`rapm`, `orapm`, `drapm`), rotación, clutch, red de asistencias |
| `equipos.csv` | equipo × fase | `team_id, fase` | ratings, suerte, quintetos, rotación, `hhi_minutos` |
| `asistencias.csv` | pareja pasador → receptor × fase | `team_id, pasador_id, receptor_id, fase` | asistencias por tipo de canasta, puntos asistidos, cuotas, minutos juntos |
| `validacion.csv` | partido | `game_id` | diferencia de minutos y +/- frente a lo oficial, anomalías, `valido` (≤ 120 s) y `usado_en_quintetos` |

### `data/processed/<t>/entrenadores/<liga>_partidos.csv`

**Entrenador por partido.** Grano: partido × equipo. Clave: `liga, temporada, game_id, equipo_id` · 654 filas (en `processed/2025-26/entrenadores/acb_partidos.csv`).

`metodo` = por partido, por orden o fechas, `temporada` (FEB, G League) o imputado; `imputado` = True si se rellenó por tramo.

| Columna | Tipo | Descripción |
|---|---|---|
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `temporada` | texto | temporada `AAAA-AA` |
| `game_id` | entero | id de partido de la fuente |
| `fecha` | texto | fecha del partido (AAAA-MM-DD) |
| `fase` | texto | `regular` o `playoffs` |
| `equipo_id` | entero | `team_id` del equipo |
| `equipo` | texto | nombre del equipo |
| `rival_id` | entero | equipo rival |
| `local` | entero | True si juega en casa |
| `puntos` | número | puntos propios |
| `puntos_rival` | número | puntos del rival |
| `resultado` | texto | V o D |
| `entrenador` | texto | nombre del entrenador |
| `entrenador_id` | texto | id de entrenador (slug del nombre; común a todas las ligas) |
| `entrenador_id_fuente` | número | id del entrenador en la fuente |
| `fuente` | texto | `pbp` (tramos de jugada a jugada) o `box` (respaldo de caja) |
| `metodo` | texto | regla que unió (`propio`, `nombre_igual+anio_…`) |
| `imputado` | entero | True si el entrenador se imputó |
| `validacion_vd` | número | comprobación V-D con la fuente |

### `data/processed/<t>/entrenadores/<liga>_tramos.csv`

**Tramos club-temporada-entrenador.** Grano: equipo × temporada × entrenador × tramo consecutivo. Clave: `liga, temporada, equipo_id, orden` · 25 filas (en `processed/2025-26/entrenadores/acb_tramos.csv`).

| Columna | Tipo | Descripción |
|---|---|---|
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `temporada` | texto | temporada `AAAA-AA` |
| `equipo_id` | entero | `team_id` |
| `equipo` | texto | nombre del equipo |
| `orden` | entero | orden del tramo en la temporada |
| `entrenador_id` | texto | id de entrenador (slug del nombre; común a todas las ligas) |
| `entrenador` | texto | nombre del entrenador |
| `n_partidos` | entero | partidos del tramo |
| `n_regular` | entero | partidos de temporada regular |
| `n_playoffs` | entero | partidos de playoffs incluidos |
| `n_otras` | entero | partidos de otras fases |
| `n_imputados` | entero | partidos con entrenador imputado |
| `primer_partido` | texto | fecha del primero |
| `ultimo_partido` | texto | fecha del último |
| `victorias` | entero | victorias |
| `derrotas` | entero | derrotas |
| `victorias_regular` | entero | victorias en regular |
| `derrotas_regular` | entero | derrotas en regular |
| `victorias_playoffs` | entero | victorias en playoffs |
| `derrotas_playoffs` | entero | derrotas en playoffs |
| `n_tramos_consecutivos` | entero | bloques consecutivos fundidos |
| `interino` | entero | True si es un interino heurístico (pocos partidos entre dos tramos) |
| `entrenadores_equipo` | entero | entrenadores del equipo en la temporada |
| `validacion_vd` | número | comprobación V-D |
| `fuente` | texto | `pbp` (tramos de jugada a jugada) o `box` (respaldo de caja) |
| `partidos_ids` | texto | lista de `game_id` |

Globales: `data/processed/entrenadores.csv` (un entrenador por fila: ligas, temporadas, clubes, partidos, variantes de nombre, ids de fuente) y `entrenadores_cobertura.csv` (liga × temporada: % de partidos con entrenador observado o imputado, métodos).

### `data/processed/<t>/feb/<liga>_partidos.csv`

**Partidos FEB con grupo (fase 1).** Grano: partido. Clave: `liga, temporada, game_id` · 290 filas (en `processed/2025-26/feb/feb1_partidos.csv`).

Sólo `feb1`, `feb2`, `feb3`. El grupo es un atributo del partido, no una liga. Equipo 1 = local.

| Columna | Tipo | Descripción |
|---|---|---|
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `temporada` | texto | temporada `AAAA-AA` |
| `game_id` | entero | id de partido de la fuente |
| `grupo_id` | entero | id del grupo FEB |
| `grupo` | texto | grupo |
| `fase` | texto | `regular` o `playoffs` |
| `jornada` | texto | jornada (texto original) |
| `fecha` | texto | fecha del partido (AAAA-MM-DD) |
| `jugado` | lógico | partido jugado |
| `descargado` | lógico | datos descargados |
| `con_box` | lógico | tiene boxscore |
| `formato_pbp` | texto | `estructurado` (2024+) o `texto` (2022-24) |
| `pbp_available` | lógico | jugada a jugada utilizable |
| `con_cambios` | lógico | tiene cambios (quintetos) |
| `quintetos_validos` | lógico | minutos reconstruidos a ≤ 120 s de los oficiales |
| `con_coordenadas` | lógico | tiros con coordenadas |
| `dif_min_max_s` | número | máxima diferencia de minutos reconstruidos vs oficiales (s) |
| `equipo_1_id` | entero | equipo local |
| `equipo_1` | texto | nombre local |
| `pts_1` | número | puntos local |
| `pos_box_1` | número | posesiones estimadas de caja (local) |
| `pos_pbp_1` | entero | posesiones reales (local) |
| `fgm_1` | número | canastas local |
| `ast_1` | número | asistencias local |
| `equipo_2_id` | entero | visitante |
| `equipo_2` | texto | nombre visitante |
| `pts_2` | número | puntos visitante |
| `pos_box_2` | número | posesiones de caja (visitante) |
| `pos_pbp_2` | entero | posesiones reales (visitante) |
| `fgm_2` | número | canastas visitante |
| `ast_2` | número | asistencias visitante |

### `data/processed/<t>/feb/<liga>_equipos.csv`

**Equipos FEB por grupo.** Grano: equipo × grupo × temporada. Clave: `liga, temporada, team_id, grupo_id` · 17 filas (en `processed/2025-26/feb/feb1_equipos.csv`).

| Columna | Tipo | Descripción |
|---|---|---|
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `temporada` | texto | temporada `AAAA-AA` |
| `team_id` | entero | id de equipo de la fuente (FEB: id de inscripción de esa temporada; BSL/GBL: nombre normalizado) |
| `equipo` | texto | nombre del equipo |
| `grupo_id` | entero | id del grupo FEB |
| `grupo` | texto | grupo |
| `entrenador` | texto | nombre del entrenador |
| `entrenador_id_feb` | número | id FEB del entrenador |
| `jugadores_plantilla` | entero | jugadores en la plantilla publicada |

### `data/processed/feb_cobertura.csv`

**Cobertura FEB.** Grano: competición × temporada × grupo. Clave: `liga, temporada, grupo_id` · 132 filas (en `processed/feb_cobertura.csv`).

Incluye las filas `fuera_de_alcance` (temporadas fuera del alcance decidido) y las copas excluidas.

| Columna | Tipo | Descripción |
|---|---|---|
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `temporada` | texto | temporada `AAAA-AA` |
| `grupo_id` | número | id del grupo FEB |
| `grupo` | texto | grupo |
| `fase` | texto | `regular` o `playoffs` |
| `partidos` | número | partidos |
| `pct_pbp` | número | % con jugada a jugada |
| `pct_solo_box` | número | % sólo boxscore |
| `pct_sin_datos` | número | % sin datos (404) |
| `pct_con_cambios` | número | % con cambios |
| `pct_quintetos_validos` | número | % con quintetos válidos |
| `pct_coordenadas` | número | % con coordenadas |
| `formato_pbp` | texto | `estructurado` (2024+) o `texto` (2022-24) |
| `descargado` | lógico | datos descargados |

### `data/processed/feb_contrato.csv`

**Contrato de datos FEB.** Grano: competición × temporada. Clave: `liga, temporada` · 16 filas (en `processed/feb_contrato.csv`).

Reglas: tipos, rangos, identidades (fgm = fg2m + fg3m…), nulos, clave única, minutos (200 + 25 por prórroga ± 1), marcador y jugada a jugada ↔ boxscore (puntos, FGA, FGM, rebotes ±3, asistencias ±2). `python -m bbstats contrato`.

| Columna | Tipo | Descripción |
|---|---|---|
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `temporada` | texto | temporada `AAAA-AA` |
| `partidos` | entero | partidos |
| `tipos_pct` | número | % de partidos que cumplen la regla `tipos` |
| `tipos_n` | entero | partidos evaluados la regla `tipos` |
| `rangos_pct` | número | % de partidos que cumplen la regla `rangos` |
| `rangos_n` | entero | partidos evaluados la regla `rangos` |
| `identidades_pct` | número | % de partidos que cumplen la regla `identidades` |
| `identidades_n` | entero | partidos evaluados la regla `identidades` |
| `nulos_pct` | número | % de partidos que cumplen la regla `nulos` |
| `nulos_n` | entero | partidos evaluados la regla `nulos` |
| `clave_unica_pct` | número | % de partidos que cumplen la regla `clave_unica` |
| `clave_unica_n` | entero | partidos evaluados la regla `clave_unica` |
| `minutos_pct` | número | % de partidos que cumplen la regla `minutos` |
| `minutos_n` | entero | partidos evaluados la regla `minutos` |
| `marcador_pct` | número | % de partidos que cumplen la regla `marcador` |
| `marcador_n` | entero | partidos evaluados la regla `marcador` |
| `pbp_pts_pct` | número | % de partidos que cumplen la regla `pbp_pts` |
| `pbp_pts_n` | entero | partidos evaluados la regla `pbp_pts` |
| `pbp_fga_pct` | número | % de partidos que cumplen la regla `pbp_fga` |
| `pbp_fga_n` | entero | partidos evaluados la regla `pbp_fga` |
| `pbp_fgm_pct` | número | % de partidos que cumplen la regla `pbp_fgm` |
| `pbp_fgm_n` | entero | partidos evaluados la regla `pbp_fgm` |
| `pbp_reb_pct` | número | % de partidos que cumplen la regla `pbp_reb` |
| `pbp_reb_n` | entero | partidos evaluados la regla `pbp_reb` |
| `pbp_ast_pct` | número | % de partidos que cumplen la regla `pbp_ast` |
| `pbp_ast_n` | entero | partidos evaluados la regla `pbp_ast` |

### `data/processed/feb_posesiones.csv`

**Posesiones reales frente a la estimación de caja.** Grano: competición × temporada × formato de jugada a jugada. Clave: `liga, temporada, formato_pbp` · 20 filas (en `processed/feb_posesiones.csv`).

Estimación de caja = FGA + 0,44·FTA − OREB + TOV.

| Columna | Tipo | Descripción |
|---|---|---|
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `temporada` | texto | temporada `AAAA-AA` |
| `formato_pbp` | texto | `estructurado` (2024+) o `texto` (2022-24) |
| `equipos_partido` | entero | filas equipo-partido |
| `pos_pbp_media` | número | posesiones reales medias |
| `pos_box_media` | número | estimación de caja media |
| `dif_media` | número | diferencia media (real − caja) |
| `dif_abs_media` | número | diferencia absoluta media |
| `dif_pct_media` | número | diferencia media (%) |
| `correlacion` | número | correlación real–caja |

### `data/processed/feb_sesgo_registro.csv`

**Sesgo de registro (asistencias por canasta, OREB%).** Grano: liga × temporada (todas las ligas FIBA). Clave: `liga, temporada` · 79 filas (en `processed/feb_sesgo_registro.csv`).

| Columna | Tipo | Descripción |
|---|---|---|
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `temporada` | texto | temporada `AAAA-AA` |
| `equipos` | entero | equipos |
| `partidos_equipo` | entero | filas equipo-partido |
| `ast_por_fgm` | número | asistencias por canasta |
| `oreb_pct` | número | OREB% (%) |

### `data/processed/player_id_crosswalk.csv`

**Correspondencia de jugadores entre ligas (crosswalk).** Grano: nodo = liga × id de jugador. Clave: `fuente_liga, fuente_id` · 23.747 filas (en `processed/player_id_crosswalk.csv`).

Una persona (`persona_id`) agrupa nodos de varias ligas. Sólo las uniones con confianza ≥ 0,75 se aplican (`configs/normalization.yaml`, `config/sources.json → identidad`).

| Columna | Tipo | Descripción |
|---|---|---|
| `fuente_liga` | texto | liga del nodo |
| `fuente_id` | entero | id del jugador en esa liga |
| `persona_id` | texto | persona entre ligas (crosswalk + unión por nombre; texto) |
| `confianza` | número | confianza de la unión (0-1; ≥ 0,75 se aplica) |
| `metodo` | texto | regla que unió (`propio`, `nombre_igual+anio_…`) |
| `nombre` | texto | nombre del jugador |
| `fecha_nacimiento` | número | fecha de nacimiento (si la fuente la da) |
| `anio_nacimiento` | número | año de nacimiento |
| `nacionalidad_iso` | número | nacionalidad ISO alfa-2 |
| `temporadas` | texto | temporadas del nodo |

### `data/processed/crosswalk_revision.csv`

**Cola de revisión del crosswalk.** Grano: pareja de nodos dudosa. Clave: `liga_a, id_a, liga_b, id_b` · 3.975 filas (en `processed/crosswalk_revision.csv`).

**No se aplica**: casos bajo el umbral o con conflicto (motivo).

| Columna | Tipo | Descripción |
|---|---|---|
| `liga_a` | texto | liga A |
| `id_a` | texto | id A |
| `nombre_a` | texto | nombre A |
| `nacimiento_a` | texto | nacimiento A |
| `nacionalidad_a` | texto | nacionalidad A |
| `temporadas_a` | texto | temporadas A |
| `liga_b` | texto | liga B |
| `id_b` | texto | id B |
| `nombre_b` | texto | nombre B |
| `nacimiento_b` | texto | nacimiento B |
| `nacionalidad_b` | texto | nacionalidad B |
| `temporadas_b` | texto | temporadas B |
| `confianza` | número | confianza de la unión (0-1; ≥ 0,75 se aplica) |
| `metodo` | texto | regla que unió (`propio`, `nombre_igual+anio_…`) |
| `motivo` | texto | por qué queda en revisión |

## 3. Modelos (`data/modelos/`)

### Normalización A y B, dataset normalizado, pista, contexto, interacciones, estilos VaDE

| Ruta | Grano | Contenido | Documentación |
|---|---|---|---|
| `algoritmo_A/parametros.json`, `tipo_de_cambio.csv`, `traducciones/<t>.csv`, `validacion*.csv` | métrica × liga (tipo de cambio: `m`, `s`, `psi`, `puentes`); jugador × liga × temporada (traducciones `<m>_a`…) | algoritmo A lineal | `docs/algoritmo_A.md` |
| `algoritmo_B/nivel_por_liga.csv`, `redes.npz`, `traducciones/<t>.csv` | métrica × liga (`nivel`, `nivel_se`); jugador | algoritmo B (red) | `docs/algoritmo_B.md` |
| `normalizado/<t>.csv` | jugador × equipo × liga × temporada (temporada regular) | 33 métricas: `<m>` (A+B, A de respaldo), `<m>_lo/_hi` (80 %), `<m>_pctel` (percentil EuroLeague), `<m>_obs` (valor en su liga), `<m>_A`, `<m>_B`, y **amortiguado** `<m>_A_am`, `<m>_am`, `<m>_am_lo/_hi`, `<m>_am_pctel`; identidad (`persona_id`, `player_uid`, `pos3`, `pos3_estimada`, `edad`, `nacionalidad`…), `fuente_norm`, `L` y `ctx_*` | `docs/datos_normalizados.md`, `docs/normalizacion_amortiguada.md` |
| `pista/<t>.csv` | jugador × equipo × liga × temporada | tiros y canastas por zona (`fga_aro`, `fgm_aro`, `corta`, `media`, `t3_esquina`, `t3_frontal`), canastas asistidas, posesiones y minutos en pista, RAPM | `docs/contexto_y_quimica.md` |
| `contexto/<t>.csv`, `por_jugador_liga.csv`, `sensibilidad.csv`, `escala_nivel.json` | jugador × equipo × liga × temporada; métrica | nivel `L`, contexto de plantilla, compañeros y rivales (`ctx_*`, `_dev`, `_ref`), sensibilidad β de cada métrica al nivel de compañeros y rivales | `docs/contexto_y_quimica.md` |
| `interacciones/efectos_<t>.csv.gz` | pareja dirigida X → Y de compañeros × equipo × temporada | métricas de Y con y sin X en pista (`*_con`, `*_sin`) y diferencias `d_*` | `docs/contexto_y_quimica.md` |
| `nacionalidades.csv` | jugador × liga × temporada | nacionalidad (español e ISO) y su fuente | `CONTEXTO_AGENTE.md` §9.1 |
| `estilos/` (`vade/clubes.csv`, `vade/jugadores.csv`, `estilos.csv`, `evaluacion.json`, `analisis.json`, `interacciones.json`, `entrenadores.csv`, `historial/`) | club × liga × temporada; jugador | estilos VaDE (Parte I del artículo): `estilo`, `p_estilo`, `p_E01…E06`, coordenadas `x, y, z` del mapa, `nivel`, `provisional` | `docs/estilos_de_juego.md` |

### Normalización amortiguada (`normalizacion_amortiguada/`, fase 2)

### `data/modelos/normalizacion_amortiguada/league_offsets.csv`

**Nivel de cada competición-temporada por métrica.** Grano: competición × temporada × métrica. Clave: `competicion, temporada, metrica` · 2.932 filas (en `modelos/normalizacion_amortiguada/league_offsets.csv`).

Unidades: DT de capacidad EuroLeague (EuroLeague = 0). `media`/`sd`/`lo90`/`hi90` = posterior con contracción por escalón (variante elegida).

| Columna | Tipo | Descripción |
|---|---|---|
| `competicion` | texto | liga (competición) |
| `temporada` | texto | temporada `AAAA-AA` |
| `metrica` | texto | métrica |
| `media` | número | tiros de media distancia |
| `sd` | número | desviación típica |
| `lo90` | número | IC 90 % inferior |
| `hi90` | número | IC 90 % superior |
| `n_puentes` | entero | puentes del nodo |
| `camino` | texto | camino de mayor precisión hasta la EuroLeague |
| `escalon` | texto | escalón de contracción |
| `media_encadenada` | número | nivel sólo del grafo (sin contracción) |
| `sd_encadenada` | número | sd del grafo |
| `media_lineal_A` | número | m del algoritmo A lineal |
| `sd_lineal_A` | número | sd del A |
| `s_A` | número | escala s del A |
| `lambda` | número | λ aplicada |
| `distancia_d` | número | distancia de nivel d (DT) |
| `forma_no_lineal` | entero | 1 si se aplicó mapeo monótono |
| `mu_escalon` | número | media del escalón (nodo latente) |
| `tau_escalon` | número | τ del escalón |
| `media_sin_ipw` | número | nivel sin pesos de selección |
| `variante` | texto | variante del modelo (`ipcw`, `sin_ipcw`, `sin_rol`; normalización: `sin_mapeo`…) |

### `data/modelos/normalizacion_amortiguada/traducciones/<t>.csv`

**Traducción amortiguada por jugador.** Grano: persona × liga × temporada. Clave: `persona_id, liga, temporada,
player_id`. Para cada una de las 33 métricas `<m>`: `<m>_am` (equivalente EuroLeague 2025-26, unidades de la métrica),
`<m>_am_lo` / `<m>_am_hi` (intervalo del 80 %), `<m>_am_pct` (percentil EuroLeague), `<m>_am_a` (capacidad θ en DT
EuroLeague) y `<m>_am_sd` (su desviación, con la incertidumbre del nivel de la competición).

### `data/modelos/normalizacion_amortiguada/lambda_por_liga.csv`

**λ̂ medida en los puentes.** Grano: métrica × liga. Clave: `metrica, liga` · 445 filas (en `modelos/normalizacion_amortiguada/lambda_por_liga.csv`).

| Columna | Tipo | Descripción |
|---|---|---|
| `metrica` | texto | métrica |
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `lam` | número | λ̂ medida en los puentes |
| `var` | número | varianza de λ̂ |
| `n` | entero | número de casos |
| `d` | número | distancia de nivel |

### `data/modelos/normalizacion_amortiguada/ejemplos_puentes.csv`

**Jugadores puente reales: lineal frente a amortiguado.** Grano: jugador × métrica. Clave: `nombre, origen, destino, metrica` · 60 filas (en `modelos/normalizacion_amortiguada/ejemplos_puentes.csv`).

| Columna | Tipo | Descripción |
|---|---|---|
| `nombre` | texto | nombre del jugador |
| `origen` | texto | competición y temporada de origen |
| `destino` | texto | de destino |
| `min_origen` | número | minutos en origen |
| `min_destino` | número | minutos en destino |
| `metrica` | texto | métrica |
| `valor_origen` | número | valor en origen |
| `valor_destino` | número | valor en destino |
| `a_origen_lineal` | número | capacidad (DT EL) en origen, lineal |
| `a_origen_amortiguado` | número | ídem amortiguado |
| `a_destino_lineal` | número | en destino, lineal |
| `a_destino_amortiguado` | número | en destino, amortiguado |
| `el_origen_lineal` | número | equivalente EuroLeague en origen, lineal |
| `el_origen_amortiguado` | número | ídem amortiguado |
| `el_destino_lineal` | número | en destino, lineal |
| `el_destino_amortiguado` | número | en destino, amortiguado |
| `error_lineal` | número | |a_origen − a_destino| lineal |
| `error_amortiguado` | número | ídem amortiguado |

### `data/modelos/normalizacion_amortiguada/diagnostico_antes.csv`

**Diagnóstico del esquema lineal (A) antes de amortiguar.** Grano: competición × métrica. Clave: `competicion, metrica` · 489 filas (en `modelos/normalizacion_amortiguada/diagnostico_antes.csv`).

| Columna | Tipo | Descripción |
|---|---|---|
| `competicion` | texto | liga (competición) |
| `metrica` | texto | métrica |
| `offset_m` | número | desfase m del A lineal |
| `sd` | número | desviación típica |
| `ancho_ic90` | número | anchura del IC90 |
| `s` | número | escala s |
| `s_sd` | número | sd de s |
| `psi` | número | ψ (varianza de temporada) |
| `unidades_puente` | entero | unidades puente |
| `sigma2` | número | σ² de muestreo |

### `data/modelos/normalizacion_amortiguada/diagnostico_antes_ligas.csv`

**Diagnóstico lineal por competición.** Grano: competición. Clave: `competicion` · 15 filas (en `modelos/normalizacion_amortiguada/diagnostico_antes_ligas.csv`).

| Columna | Tipo | Descripción |
|---|---|---|
| `competicion` | texto | liga (competición) |
| `offset_nivel` | número | desfase de nivel (mediana de métricas de nivel) |
| `ancho_ic90_nivel` | número | anchura del IC90 del nivel |
| `sd_nivel` | número | sd del nivel |
| `offset_m_pts_p100` | número | desfase de pts/100 |
| `ancho_ic90_pts_p100` | número | IC90 de pts/100 |
| `unidades_puente_pts_p100` | entero | puentes de pts/100 |
| `puentes_total` | entero | puentes totales |
| `puentes_con_euroleague` | número | puentes directos con la EuroLeague |

### `data/modelos/normalizacion_amortiguada/diagnostico_antes_puentes.csv`

**Puentes por pareja de ligas.** Grano: pareja de ligas. Clave: `liga_a, liga_b` · 82 filas (en `modelos/normalizacion_amortiguada/diagnostico_antes_puentes.csv`).

| Columna | Tipo | Descripción |
|---|---|---|
| `liga_a` | texto | liga A |
| `liga_b` | texto | liga B |
| `personas` | entero | personas puente |
| `personas_misma` | número | en la misma temporada |
| `personas_consecutiva` | entero | en temporadas consecutivas |

### `data/modelos/normalizacion_amortiguada/validacion.csv`

**Examen temporal: A lineal frente a amortiguado (mismos casos).** Grano: métrica. Clave: `metrica, variante` · 33 filas (en `modelos/normalizacion_amortiguada/validacion.csv`).

| Columna | Tipo | Descripción |
|---|---|---|
| `metrica` | texto | métrica |
| `casos` | entero | casos del examen |
| `mae_lineal_A` | número | MAE del A lineal |
| `mae_amortiguado` | número | MAE amortiguado |
| `mae_mismo_percentil` | número | MAE de «mismo percentil» |
| `mejora_mae_%` | número | mejora del MAE (%) |
| `cobertura80_lineal` | número | cobertura 80 % lineal |
| `cobertura80_amortiguado` | número | cobertura 80 % amortiguada |
| `casos_a_euroleague` | entero | casos a euroleague |
| `mae_lineal_a_euroleague` | número | MAE lineal — casos a euroleague |
| `mae_amortiguado_a_euroleague` | número | MAE amortiguado — casos a euroleague |
| `cob80_lineal_a_euroleague` | número | cobertura 80 % lineal — casos a euroleague |
| `cob80_amortiguado_a_euroleague` | número | cobertura 80 % amortiguado — casos a euroleague |
| `casos_desde_feb` | entero | casos desde feb |
| `mae_lineal_desde_feb` | número | MAE lineal — casos desde feb |
| `mae_amortiguado_desde_feb` | número | MAE amortiguado — casos desde feb |
| `cob80_lineal_desde_feb` | número | cobertura 80 % lineal — casos desde feb |
| `cob80_amortiguado_desde_feb` | número | cobertura 80 % amortiguado — casos desde feb |
| `casos_hacia_feb` | entero | casos hacia feb |
| `mae_lineal_hacia_feb` | número | MAE lineal — casos hacia feb |
| `mae_amortiguado_hacia_feb` | número | MAE amortiguado — casos hacia feb |
| `cob80_lineal_hacia_feb` | número | cobertura 80 % lineal — casos hacia feb |
| `cob80_amortiguado_hacia_feb` | número | cobertura 80 % amortiguado — casos hacia feb |
| `variante` | texto | variante del modelo (`ipcw`, `sin_ipcw`, `sin_rol`; normalización: `sin_mapeo`…) |

### `data/modelos/normalizacion_amortiguada/validacion_lolo.csv`

**Dejar fuera una liga.** Grano: métrica × competición-temporada. Clave: `metrica, nodo` · 1.855 filas (en `modelos/normalizacion_amortiguada/validacion_lolo.csv`).

| Columna | Tipo | Descripción |
|---|---|---|
| `metrica` | texto | métrica |
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `nodo` | texto | competición-temporada |
| `escalon` | texto | escalón de contracción |
| `escalon_con_otras_ligas` | lógico | True si el escalón tiene otras ligas |
| `nivel_todos` | número | nivel con todas las aristas |
| `pred_jerarquica` | número | nivel predicho sin sus aristas (con jerarquía) |
| `sd_jerarquica` | número | sd |
| `error_jerarquica` | número | error |
| `dentro_90` | lógico | dentro del IC90 |
| `pred_sin_jerarquia` | número | predicción sin jerarquía (0 = EuroLeague) |
| `error_sin_jerarquia` | número | error sin jerarquía |

### `data/modelos/normalizacion_amortiguada/validacion_variantes.csv`

**Comparación de variantes (elección con el corte 2023, confirmación con el 2024).** Grano: variante. Clave: `variante` · 4 filas (en `modelos/normalizacion_amortiguada/validacion_variantes.csv`).

| Columna | Tipo | Descripción |
|---|---|---|
| `variante` | texto | variante del modelo (`ipcw`, `sin_ipcw`, `sin_rol`; normalización: `sin_mapeo`…) |
| `mapeo` | lógico | mapeo monótono activo |
| `amortiguar_lambda` | lógico | λ(d) activa |
| `ipw` | lógico | pesos de selección activos |
| `mae_rel_2023` | número | mae rel (corte 2023) |
| `cob80_lineal_2023` | número | cob80 lineal (corte 2023) |
| `cob80_amortiguado_2023` | número | cob80 amortiguado (corte 2023) |
| `metricas_mejor_2023` | entero | metricas mejor (corte 2023) |
| `mae_rel_desde_feb_2023` | número | mae rel desde feb (corte 2023) |
| `mae_rel_hacia_feb_2023` | número | mae rel hacia feb (corte 2023) |
| `mae_rel_a_euroleague_2023` | número | mae rel a euroleague (corte 2023) |
| `mae_rel_2024` | número | mae rel (corte 2024) |
| `cob80_lineal_2024` | número | cob80 lineal (corte 2024) |
| `cob80_amortiguado_2024` | número | cob80 amortiguado (corte 2024) |
| `metricas_mejor_2024` | entero | metricas mejor (corte 2024) |
| `mae_rel_desde_feb_2024` | número | mae rel desde feb (corte 2024) |
| `mae_rel_hacia_feb_2024` | número | mae rel hacia feb (corte 2024) |
| `mae_rel_a_euroleague_2024` | número | mae rel a euroleague (corte 2024) |
| `elegida_por_corte` | entero | corte con el que se eligió |

Además: `validacion_casos.csv.gz` (caso × métrica del examen) y `validacion_variantes/<variante>_<corte>.csv.gz` (casos por variante), `resumen.json` (forma de λ(d) elegida, λ y d por liga, τ y μ de los escalones, logit de selección, efecto de los pesos).

### Roles (`roles/`, fase 3)

### `data/modelos/roles/partidos_jugador/<t>.csv.gz`

**Tabla partido × jugador.** Grano: partido × jugador (incluidas ausencias, `jugo = False`). Clave: `liga, temporada, game_id, team_id, player_id` · 74.647 filas (en `modelos/roles/partidos_jugador/2020-21.csv.gz`).

Una por temporada (0,7-7,8 MB). Reconstruida de los tramos y tiros; en las liga-temporada sin jugada a jugada suficiente, de la caja (`fuente = box`).

| Columna | Tipo | Descripción |
|---|---|---|
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `temporada` | texto | temporada `AAAA-AA` |
| `game_id` | entero | id de partido de la fuente |
| `fase` | texto | `regular` o `playoffs` |
| `team_id` | entero | id de equipo de la fuente (FEB: id de inscripción de esa temporada; BSL/GBL: nombre normalizado) |
| `opp_id` | entero | id del rival |
| `player_id` | entero | id de jugador de la fuente (único dentro de la liga) |
| `sec` | número | segundos en pista |
| `sec_close` | número | segundos de cierre igualado |
| `sec_q4` | número | segundos en el 4.º cuarto |
| `titular` | entero | 1 si estaba en pista al empezar |
| `poss_on` | número | posesiones del equipo con él en pista |
| `pm` | número | +/- en pista |
| `dur_s` | número | duración real del partido (s, con prórrogas) |
| `dur_q4` | número | duración del 4.º cuarto (s) |
| `sec_close_equipo` | número | segundos de cierre igualado del partido |
| `fga` | número | tiros de campo intentados |
| `fgm` | número | canastas de campo |
| `fg3a` | número | triples intentados |
| `fg3m` | número | triples anotados |
| `fta` | número | tiros libres intentados |
| `ftm` | número | tiros libres anotados |
| `pts` | número | puntos |
| `fgm_asist` | número | canastas asistidas |
| `fga_cl` | número | tiros de campo en cierre igualado |
| `fta_cl` | número | tiros libres en cierre igualado |
| `ast` | número | asistencias |
| `team_fga_on` | número | FGA del equipo con él en pista |
| `team_fgm_on` | número | FGM del equipo en pista |
| `team_fta_on` | número | FTA del equipo en pista |
| `team_fga_on_cl` | número | FGA del equipo en pista en cierre |
| `team_fta_on_cl` | número | FTA del equipo en pista en cierre |
| `fecha` | texto | fecha del partido (AAAA-MM-DD) |
| `entrenador_id` | texto | id de entrenador (slug del nombre; común a todas las ligas) |
| `orden_equipo` | entero | número de partido del equipo |
| `jugo` | lógico | False = ausencia (no salió estando en el rango de partidos con el equipo) |
| `min` | número | minutos |
| `min_pct` | número | MIN% medio: minutos / duración real del partido (0-1) |
| `usg_tiro` | número | USG% de tiro del partido (%) |
| `ts_pct` | número | TS% (%) |
| `close_share` | número | fracción del cierre igualado jugada |
| `rango_min` | número | puesto en minutos dentro del equipo en el partido |
| `coef_tl` | número | peso del tiro libre usado (0,44; G League con su coeficiente) |
| `persona_id` | texto | persona entre ligas (crosswalk + unión por nombre; texto) |
| `pos3` | texto | posición en 3 grupos: E exterior, A alero, I interior (oficial o estimada) |
| `fuente` | texto | `pbp` (tramos de jugada a jugada) o `box` (respaldo de caja) |
| `estado` | texto | estado de rol del partido |
| `tramo` | entero | número de tramo de rol dentro del jugador-equipo-temporada (1, 2…) |

### `data/modelos/roles/player_role_spells.csv.gz`

**Tramos de rol.** Grano: liga × temporada × club × jugador × entrenador × tramo. Clave: `liga, temporada, team_id, player_id, tramo` · 44.416 filas (en `modelos/roles/player_role_spells.csv.gz`).

Banderas: `rol_probabilistico` (< 5 partidos), `fuente` (`pbp`/`box`), covariables `cov_*` del cambio que abre el tramo. `p_<ROL>` es la pertenencia blanda s_ik que usa el reemplazo.

| Columna | Tipo | Descripción |
|---|---|---|
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `temporada` | texto | temporada `AAAA-AA` |
| `team_id` | texto | id de equipo de la fuente (FEB: id de inscripción de esa temporada; BSL/GBL: nombre normalizado) |
| `player_id` | texto | id de jugador de la fuente (único dentro de la liga) |
| `persona_id` | texto | persona entre ligas (crosswalk + unión por nombre; texto) |
| `nombre` | texto | nombre del jugador |
| `pos3` | texto | posición en 3 grupos: E exterior, A alero, I interior (oficial o estimada) |
| `entrenador_id` | texto | id de entrenador (slug del nombre; común a todas las ligas) |
| `tramo` | entero | número de tramo de rol dentro del jugador-equipo-temporada (1, 2…) |
| `fuente` | texto | `pbp` (tramos de jugada a jugada) o `box` (respaldo de caja) |
| `inicio` | texto | fecha del primer partido del tramo |
| `fin` | texto | fecha del último partido del tramo |
| `inicio_orden` | número | orden del primer partido en el calendario del equipo |
| `fin_orden` | número | orden del último partido |
| `n_partidos` | entero | partidos jugados en el tramo |
| `ausencias` | número | partidos del equipo sin jugar entre su primer y su último partido |
| `rol` | texto | rol duro (vacío si < 5 partidos: ver `rol_mas_probable`) |
| `rol_mas_probable` | texto | rol con mayor probabilidad del vector p_k |
| `probabilidad` | número | probabilidad del rol más probable (0-1) |
| `rol_probabilistico` | lógico | True si < 5 partidos (sin etiqueta dura) |
| `motivo_inicio` | texto | por qué empieza el tramo: `inicio`, `entrenador`, `cambio` (BOCPD), `traspaso`, `temporada_caja` |
| `prob_cambio` | número | probabilidad posterior del cambio que abre el tramo (BOCPD) |
| `n_playoffs` | número | partidos de playoffs incluidos |
| `min_total` | número | minutos totales |
| `min_pg` | número | minutos por partido jugado |
| `min_pct` | número | MIN% medio: minutos / duración real del partido (0-1) |
| `gs_pct` | número | fracción de partidos como titular (0-1) |
| `min_sd` | número | desviación típica de los minutos por partido |
| `min_cv` | número | coeficiente de variación de los minutos |
| `close_pct` | número | fracción de los minutos de cierre igualado del equipo que juega (0-1) |
| `min_close` | número | minutos de cierre igualado (últimos 300 s de cada periodo ≥ 4 con |margen| ≤ 5) |
| `q4_share` | número | fracción del 4.º cuarto en pista (0-1) |
| `rango_min_equipo` | número | puesto medio en minutos dentro de su equipo (1 = el que más juega) |
| `usg_pct` | número | USG% de tiro: (FGA + 0,44·FTA) / lo mismo del equipo en pista (%) |
| `intentos_uso` | número | FGA + 0,44·FTA propios |
| `ast_pct` | número | AST% desde los tiros asistidos del jugada a jugada (%) |
| `fgm` | número | canastas de campo |
| `fgm_no_asist` | número | canastas sin asistencia |
| `cuota_tiros_pista` | número | % de los tiros del equipo en pista que son suyos |
| `usg_clutch_bruto` | número | USG% en cierres igualados sin contraer (%) |
| `intentos_equipo_clutch` | número | intentos del equipo en pista en cierres igualados |
| `ts_pct` | número | TS% (%) |
| `pts` | número | puntos |
| `poss_on` | número | posesiones del equipo con él en pista |
| `pm_por40` | número | +/- por 40 minutos |
| `pie` | número | PIE de temporada (caja, jugador-equipo) |
| `per` | número | PER de temporada (caja) |
| `usg_pct_caja` | número | USG% de caja (con pérdidas; temporada) |
| `ast_pct_caja` | número | AST% de caja (temporada) |
| `pfd_p40` | número | faltas recibidas por 40 (caja) |
| `gs_caja` | número | titularidades (caja) |
| `gp_caja` | número | partidos (caja) |
| `min_caja` | número | minutos (caja) |
| `edad` | número | edad en la temporada (años) |
| `net_rtg_aj_onoff` | número | on/off de net rating contraído (quintetos, temporada) |
| `rapm` | número | RAPM (puntos por 100 posesiones) |
| `orapm` | número | RAPM ofensivo |
| `drapm` | número | RAPM defensivo (> 0 = mejor defensa) |
| `rapm_poss` | número | posesiones del RAPM |
| `usg_clutch` | número | USG% de cierre contraído hacia su USG% (k = 15 intentos) |
| `pct_no_asistidas` | número | % de canastas no asistidas contraído hacia la liga (k = 20) |
| `z_usg` | número | z de USG% en su liga-temporada (referencia MIN% ≥ 25 %, ≥ 5 partidos) |
| `z_pie` | número | z de PIE |
| `z_no_asistidas` | número | z del % no asistido |
| `z_usg_clutch` | número | z del USG% de cierre |
| `gti` | número | GTI = suma de las 4 z (umbral GO-TO-GUY 4,0) |
| `gti_componentes` | entero | componentes del GTI disponibles (0-4) |
| `gti_rango_equipo` | número | puesto del GTI dentro del equipo |
| `rol_regla` | texto | rol por la regla de minutos/GTI antes del tratamiento de muestra pequeña |
| `n_RESIDUAL` | número | partidos en el estado RESIDUAL (o jugadores con ese rol, en equipos) |
| `n_PROFUNDIDAD` | número | partidos en el estado PROFUNDIDAD (o jugadores con ese rol, en equipos) |
| `n_ROTACION` | número | partidos en el estado ROTACION (o jugadores con ese rol, en equipos) |
| `n_TITULAR` | número | partidos en el estado TITULAR (o jugadores con ese rol, en equipos) |
| `n_GO_TO_GUY` | número | partidos en el estado GO-TO-GUY (o jugadores con ese rol, en equipos) |
| `p_RESIDUAL` | número | probabilidad del rol RESIDUAL (vector Dirichlet, α = 2) |
| `p_PROFUNDIDAD` | número | probabilidad del rol PROFUNDIDAD (vector Dirichlet, α = 2) |
| `p_ROTACION` | número | probabilidad del rol ROTACION (vector Dirichlet, α = 2) |
| `p_TITULAR` | número | probabilidad del rol TITULAR (vector Dirichlet, α = 2) |
| `p_GO_TO_GUY` | número | probabilidad del rol GO-TO-GUY (vector Dirichlet, α = 2) |
| `H_rol` | número | entropía del reparto de estados de rol por partido (bits) |
| `H_rol_norm` | número | H_rol / log2(5) |
| `cov_cambio_entrenador` | texto | covariable del cambio: cambio de entrenador en ±4 partidos |
| `cov_vacio_rol` | texto | covariable: vacío de rol (compañero de su pos3 con MIN% ≥ 50 % que deja de jugar) |
| `cov_vacio_rol_ids` | texto | ids de los compañeros ausentes |
| `cov_fichaje_posicion` | texto | covariable: fichaje en su posición con el equipo en marcha |
| `cov_fichaje_ids` | texto | ids de los fichajes |
| `cov_ts_reciente` | número | TS% de los 4 partidos previos (%) |
| `cov_ts_dif_reciente` | número | TS% reciente − su media previa (puntos) |
| `cov_pm40_reciente` | número | +/- por 40 de los 4 partidos previos |
| `cov_pm40_dif_reciente` | número | +/- por 40 reciente − media previa |
| `rol_anterior` | texto | rol del tramo anterior |
| `dif_min_pct` | número | MIN% del tramo − MIN% del tramo anterior |
| `cobertura_pbp` | número | fracción de los partidos del equipo con tramos de jugada a jugada |
| `adapt_pct` | número | vacío en este fichero: el ADAPT% está en `adaptacion/adapt_pct_roles.csv` (`bbfit.adaptacion.rellenar_adapt_pct`) |

### `data/modelos/roles/player_role_season.csv.gz`

**Rol de temporada.** Grano: liga × temporada × club × jugador. Clave: `liga, temporada, team_id, player_id` · 40.084 filas (en `modelos/roles/player_role_season.csv.gz`).

Mismas métricas que los tramos, agregadas a la temporada en el club; `rol_modal_*` resume los tramos.

| Columna | Tipo | Descripción |
|---|---|---|
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `temporada` | texto | temporada `AAAA-AA` |
| `team_id` | texto | id de equipo de la fuente (FEB: id de inscripción de esa temporada; BSL/GBL: nombre normalizado) |
| `player_id` | texto | id de jugador de la fuente (único dentro de la liga) |
| `persona_id` | texto | persona entre ligas (crosswalk + unión por nombre; texto) |
| `nombre` | texto | nombre del jugador |
| `pos3` | texto | posición en 3 grupos: E exterior, A alero, I interior (oficial o estimada) |
| `fuente` | texto | `pbp` (tramos de jugada a jugada) o `box` (respaldo de caja) |
| `gp` | entero | partidos jugados |
| `rol` | texto | rol duro (vacío si < 5 partidos: ver `rol_mas_probable`) |
| `rol_mas_probable` | texto | rol con mayor probabilidad del vector p_k |
| `rol_probabilistico` | lógico | True si < 5 partidos (sin etiqueta dura) |
| `probabilidad` | número | probabilidad del rol más probable (0-1) |
| `rol_modal_minutos` | texto | rol de más minutos de la temporada en el club |
| `rol_modal_jugador_liga` | texto | rol de más minutos del jugador en la liga (todos sus clubes) |
| `secuencia_roles` | texto | roles de sus tramos en orden («ROTACION>TITULAR») |
| `n_tramos` | entero | número de tramos |
| `ausencias` | número | partidos del equipo sin jugar entre su primer y su último partido |
| `n_playoffs` | número | partidos de playoffs incluidos |
| `inicio_orden` | número | orden del primer partido en el calendario del equipo |
| `fin_orden` | número | orden del último partido |
| `inicio_fecha` | texto | primer partido |
| `fin_fecha` | texto | último partido |
| `min_total` | número | minutos totales |
| `min_pg` | número | minutos por partido jugado |
| `min_pct` | número | MIN% medio: minutos / duración real del partido (0-1) |
| `gs_pct` | número | fracción de partidos como titular (0-1) |
| `min_sd` | número | desviación típica de los minutos por partido |
| `min_cv` | número | coeficiente de variación de los minutos |
| `close_pct` | número | fracción de los minutos de cierre igualado del equipo que juega (0-1) |
| `min_close` | número | minutos de cierre igualado (últimos 300 s de cada periodo ≥ 4 con |margen| ≤ 5) |
| `q4_share` | número | fracción del 4.º cuarto en pista (0-1) |
| `rango_min_equipo` | número | puesto medio en minutos dentro de su equipo (1 = el que más juega) |
| `usg_pct` | número | USG% de tiro: (FGA + 0,44·FTA) / lo mismo del equipo en pista (%) |
| `intentos_uso` | número | FGA + 0,44·FTA propios |
| `ast_pct` | número | AST% desde los tiros asistidos del jugada a jugada (%) |
| `fgm` | número | canastas de campo |
| `fgm_no_asist` | número | canastas sin asistencia |
| `cuota_tiros_pista` | número | % de los tiros del equipo en pista que son suyos |
| `usg_clutch_bruto` | número | USG% en cierres igualados sin contraer (%) |
| `intentos_equipo_clutch` | número | intentos del equipo en pista en cierres igualados |
| `ts_pct` | número | TS% (%) |
| `pts` | número | puntos |
| `poss_on` | número | posesiones del equipo con él en pista |
| `pm_por40` | número | +/- por 40 minutos |
| `pie` | número | PIE de temporada (caja, jugador-equipo) |
| `per` | número | PER de temporada (caja) |
| `usg_pct_caja` | número | USG% de caja (con pérdidas; temporada) |
| `ast_pct_caja` | número | AST% de caja (temporada) |
| `pfd_p40` | número | faltas recibidas por 40 (caja) |
| `gs_caja` | número | titularidades (caja) |
| `gp_caja` | número | partidos (caja) |
| `min_caja` | número | minutos (caja) |
| `edad` | número | edad en la temporada (años) |
| `net_rtg_aj_onoff` | número | on/off de net rating contraído (quintetos, temporada) |
| `rapm` | número | RAPM (puntos por 100 posesiones) |
| `orapm` | número | RAPM ofensivo |
| `drapm` | número | RAPM defensivo (> 0 = mejor defensa) |
| `rapm_poss` | número | posesiones del RAPM |
| `usg_clutch` | número | USG% de cierre contraído hacia su USG% (k = 15 intentos) |
| `pct_no_asistidas` | número | % de canastas no asistidas contraído hacia la liga (k = 20) |
| `z_usg` | número | z de USG% en su liga-temporada (referencia MIN% ≥ 25 %, ≥ 5 partidos) |
| `z_pie` | número | z de PIE |
| `z_no_asistidas` | número | z del % no asistido |
| `z_usg_clutch` | número | z del USG% de cierre |
| `gti` | número | GTI = suma de las 4 z (umbral GO-TO-GUY 4,0) |
| `gti_componentes` | entero | componentes del GTI disponibles (0-4) |
| `gti_rango_equipo` | número | puesto del GTI dentro del equipo |
| `rol_regla` | texto | rol por la regla de minutos/GTI antes del tratamiento de muestra pequeña |
| `n_RESIDUAL` | número | partidos en el estado RESIDUAL (o jugadores con ese rol, en equipos) |
| `n_PROFUNDIDAD` | número | partidos en el estado PROFUNDIDAD (o jugadores con ese rol, en equipos) |
| `n_ROTACION` | número | partidos en el estado ROTACION (o jugadores con ese rol, en equipos) |
| `n_TITULAR` | número | partidos en el estado TITULAR (o jugadores con ese rol, en equipos) |
| `n_GO_TO_GUY` | número | partidos en el estado GO-TO-GUY (o jugadores con ese rol, en equipos) |
| `p_RESIDUAL` | número | probabilidad del rol RESIDUAL (vector Dirichlet, α = 2) |
| `p_PROFUNDIDAD` | número | probabilidad del rol PROFUNDIDAD (vector Dirichlet, α = 2) |
| `p_ROTACION` | número | probabilidad del rol ROTACION (vector Dirichlet, α = 2) |
| `p_TITULAR` | número | probabilidad del rol TITULAR (vector Dirichlet, α = 2) |
| `p_GO_TO_GUY` | número | probabilidad del rol GO-TO-GUY (vector Dirichlet, α = 2) |
| `H_rol` | número | entropía del reparto de estados de rol por partido (bits) |
| `H_rol_norm` | número | H_rol / log2(5) |
| `cobertura_pbp` | número | fracción de los partidos del equipo con tramos de jugada a jugada |
| `adapt_pct` | número | vacío en este fichero: el ADAPT% está en `adaptacion/adapt_pct_roles.csv` (`bbfit.adaptacion.rellenar_adapt_pct`) |
| `entrenador_id` | texto | id de entrenador (slug del nombre; común a todas las ligas) |
| `entrenadores_varios` | texto | True si tuvo más de un entrenador en el club esa temporada |

### `data/modelos/roles/team_role_structure.csv`

**Estructura de roles del equipo.** Grano: equipo × temporada. Clave: `liga, temporada, team_id` · 2.496 filas (en `modelos/roles/team_role_structure.csv`).

`n_<ROL>` = jugadores con ese rol duro; `n_esperado_<ROL>` = suma de probabilidades.

| Columna | Tipo | Descripción |
|---|---|---|
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `temporada` | texto | temporada `AAAA-AA` |
| `team_id` | texto | id de equipo de la fuente (FEB: id de inscripción de esa temporada; BSL/GBL: nombre normalizado) |
| `fuente` | texto | `pbp` (tramos de jugada a jugada) o `box` (respaldo de caja) |
| `jugadores_usados` | entero | jugadores que jugaron |
| `rotacion` | entero | jugadores con ≥ 15' de media |
| `hhi_minutos` | número | Herfindahl del reparto de minutos |
| `hhi_uso` | número | Herfindahl del reparto del uso |
| `cuota_uso_top1` | número | cuota de uso del jugador de más uso |
| `cuota_uso_top2` | número | cuota de uso de los dos de más uso |
| `cuota_min_top5` | número | cuota de minutos de los 5 que más juegan |
| `entrenador_principal` | texto | entrenador con más partidos |
| `n_RESIDUAL` | entero | partidos en el estado RESIDUAL (o jugadores con ese rol, en equipos) |
| `n_esperado_RESIDUAL` | número | jugadores esperados en RESIDUAL (suma de probabilidades) |
| `cuota_min_RESIDUAL` | número | cuota de minutos del equipo en RESIDUAL |
| `cuota_uso_RESIDUAL` | número | cuota de uso en RESIDUAL |
| `n_PROFUNDIDAD` | entero | partidos en el estado PROFUNDIDAD (o jugadores con ese rol, en equipos) |
| `n_esperado_PROFUNDIDAD` | número | jugadores esperados en PROFUNDIDAD (suma de probabilidades) |
| `cuota_min_PROFUNDIDAD` | número | cuota de minutos del equipo en PROFUNDIDAD |
| `cuota_uso_PROFUNDIDAD` | número | cuota de uso en PROFUNDIDAD |
| `n_ROTACION` | entero | partidos en el estado ROTACION (o jugadores con ese rol, en equipos) |
| `n_esperado_ROTACION` | número | jugadores esperados en ROTACION (suma de probabilidades) |
| `cuota_min_ROTACION` | número | cuota de minutos del equipo en ROTACION |
| `cuota_uso_ROTACION` | número | cuota de uso en ROTACION |
| `n_TITULAR` | entero | partidos en el estado TITULAR (o jugadores con ese rol, en equipos) |
| `n_esperado_TITULAR` | número | jugadores esperados en TITULAR (suma de probabilidades) |
| `cuota_min_TITULAR` | número | cuota de minutos del equipo en TITULAR |
| `cuota_uso_TITULAR` | número | cuota de uso en TITULAR |
| `n_GO_TO_GUY` | entero | partidos en el estado GO-TO-GUY (o jugadores con ese rol, en equipos) |
| `n_esperado_GO_TO_GUY` | número | jugadores esperados en GO-TO-GUY (suma de probabilidades) |
| `cuota_min_GO_TO_GUY` | número | cuota de minutos del equipo en GO-TO-GUY |
| `cuota_uso_GO_TO_GUY` | número | cuota de uso en GO-TO-GUY |

Validación: `distribucion_roles.csv` (liga: fracción de registros por rol, `NA` = sin rol), `validacion_top_anotadores.csv` (rol de los 10 máximos anotadores por liga), `validacion_ejemplos.csv` (casos conocidos), `resumen.json`. Caché `roles/_cache/` no versionada.

### Reemplazo de rol (`reemplazo/`, fase 4)

### `data/modelos/reemplazo/uso_eficiencia.csv`

**Elasticidad uso–eficiencia por jugador.** Grano: persona. Clave: `persona_id` · 15.049 filas (en `modelos/reemplazo/uso_eficiencia.csv`).

Sufijos: `_ts` = estimación principal (IV partido a partido); `_ts_tramos`, `_ts_partido` = MCO de diagnóstico (sesgados por selección); `_tov` = TOV% entre temporadas (asociación). β en puntos de TS% (o TOV%) por +1 punto de USG%.

| Columna | Tipo | Descripción |
|---|---|---|
| `persona_id` | texto | persona entre ligas (crosswalk + unión por nombre; texto) |
| `nombre` | texto | nombre del jugador |
| `liga_principal` | texto | liga con más partidos/minutos |
| `pos3` | texto | posición en 3 grupos: E exterior, A alero, I interior (oficial o estimada) |
| `beta_bruto_ts` | número | β propio — TS% por IV partido a partido (principal) |
| `se_ts` | número | error típico de β propio — TS% por IV partido a partido (principal) |
| `n_ts` | número | observaciones — TS% por IV partido a partido (principal) |
| `n_grupos_ts` | número | grupos — TS% por IV partido a partido (principal) |
| `f_primera_etapa_ts` | número | F de la primera etapa propia — TS% por IV partido a partido (principal) |
| `beta_grupo_ts` | número | β del grupo pos3 — TS% por IV partido a partido (principal) |
| `tau2_grupo_ts` | número | τ² entre jugadores — TS% por IV partido a partido (principal) |
| `n_grupo_ts` | entero | jugadores del grupo — TS% por IV partido a partido (principal) |
| `w_ts` | número | peso propio w = τ²/(τ² + se²) — TS% por IV partido a partido (principal) |
| `beta_media_ts` | número | β* agrupado (media) — TS% por IV partido a partido (principal) |
| `beta_sd_ts` | número | sd de β* — TS% por IV partido a partido (principal) |
| `beta_lo_ts` | número | IC 90 % inferior — TS% por IV partido a partido (principal) |
| `beta_hi_ts` | número | IC 90 % superior — TS% por IV partido a partido (principal) |
| `solo_grupo_ts` | lógico | True si se usa sólo el del grupo — TS% por IV partido a partido (principal) |
| `beta_bruto_ts_tramos` | número | β propio — TS% MCO entre tramos (diagnóstico) |
| `se_ts_tramos` | número | error típico de β propio — TS% MCO entre tramos (diagnóstico) |
| `n_ts_tramos` | número | observaciones — TS% MCO entre tramos (diagnóstico) |
| `n_grupos_ts_tramos` | número | grupos — TS% MCO entre tramos (diagnóstico) |
| `beta_grupo_ts_tramos` | número | β del grupo pos3 — TS% MCO entre tramos (diagnóstico) |
| `tau2_grupo_ts_tramos` | número | τ² entre jugadores — TS% MCO entre tramos (diagnóstico) |
| `n_grupo_ts_tramos` | entero | jugadores del grupo — TS% MCO entre tramos (diagnóstico) |
| `w_ts_tramos` | número | peso propio w = τ²/(τ² + se²) — TS% MCO entre tramos (diagnóstico) |
| `beta_media_ts_tramos` | número | β* agrupado (media) — TS% MCO entre tramos (diagnóstico) |
| `beta_sd_ts_tramos` | número | sd de β* — TS% MCO entre tramos (diagnóstico) |
| `beta_lo_ts_tramos` | número | IC 90 % inferior — TS% MCO entre tramos (diagnóstico) |
| `beta_hi_ts_tramos` | número | IC 90 % superior — TS% MCO entre tramos (diagnóstico) |
| `solo_grupo_ts_tramos` | lógico | True si se usa sólo el del grupo — TS% MCO entre tramos (diagnóstico) |
| `beta_bruto_ts_partido` | número | β propio — TS% MCO partido a partido (diagnóstico) |
| `se_ts_partido` | número | error típico de β propio — TS% MCO partido a partido (diagnóstico) |
| `n_ts_partido` | número | observaciones — TS% MCO partido a partido (diagnóstico) |
| `n_grupos_ts_partido` | número | grupos — TS% MCO partido a partido (diagnóstico) |
| `beta_grupo_ts_partido` | número | β del grupo pos3 — TS% MCO partido a partido (diagnóstico) |
| `tau2_grupo_ts_partido` | número | τ² entre jugadores — TS% MCO partido a partido (diagnóstico) |
| `n_grupo_ts_partido` | entero | jugadores del grupo — TS% MCO partido a partido (diagnóstico) |
| `w_ts_partido` | número | peso propio w = τ²/(τ² + se²) — TS% MCO partido a partido (diagnóstico) |
| `beta_media_ts_partido` | número | β* agrupado (media) — TS% MCO partido a partido (diagnóstico) |
| `beta_sd_ts_partido` | número | sd de β* — TS% MCO partido a partido (diagnóstico) |
| `beta_lo_ts_partido` | número | IC 90 % inferior — TS% MCO partido a partido (diagnóstico) |
| `beta_hi_ts_partido` | número | IC 90 % superior — TS% MCO partido a partido (diagnóstico) |
| `solo_grupo_ts_partido` | lógico | True si se usa sólo el del grupo — TS% MCO partido a partido (diagnóstico) |
| `beta_bruto_tov` | número | β propio — TOV% entre temporadas (asociación) |
| `se_tov` | número | error típico de β propio — TOV% entre temporadas (asociación) |
| `n_tov` | número | observaciones — TOV% entre temporadas (asociación) |
| `n_grupos_tov` | número | grupos — TOV% entre temporadas (asociación) |
| `beta_grupo_tov` | número | β del grupo pos3 — TOV% entre temporadas (asociación) |
| `tau2_grupo_tov` | número | τ² entre jugadores — TOV% entre temporadas (asociación) |
| `n_grupo_tov` | entero | jugadores del grupo — TOV% entre temporadas (asociación) |
| `w_tov` | número | peso propio w = τ²/(τ² + se²) — TOV% entre temporadas (asociación) |
| `beta_media_tov` | número | β* agrupado (media) — TOV% entre temporadas (asociación) |
| `beta_sd_tov` | número | sd de β* — TOV% entre temporadas (asociación) |
| `beta_lo_tov` | número | IC 90 % inferior — TOV% entre temporadas (asociación) |
| `beta_hi_tov` | número | IC 90 % superior — TOV% entre temporadas (asociación) |
| `solo_grupo_tov` | lógico | True si se usa sólo el del grupo — TOV% entre temporadas (asociación) |

### `data/modelos/reemplazo/uso_eficiencia_grupos.csv`

**β IV por grupo de posición.** Grano: pos3 (y `todos`). Clave: `pos3_p` · 5 filas (en `modelos/reemplazo/uso_eficiencia_grupos.csv`).

IC 90 % por bootstrap de personas.

| Columna | Tipo | Descripción |
|---|---|---|
| `pos3_p` | texto | grupo de posición del IV |
| `beta_iv` | número | β IV del grupo (ΔTS% por +1 USG%) |
| `beta_iv_sd` | número | desviación bootstrap |
| `beta_iv_lo` | número | IC 90 % inferior |
| `beta_iv_hi` | número | IC 90 % superior |
| `primera_etapa` | número | coeficiente de la primera etapa (USG% por unidad de cuota ausente) |
| `n_filas` | entero | filas |
| `n_personas` | entero | personas |

### `data/modelos/reemplazo/produccion_por_rol.csv`

**Producción típica por liga y rol.** Grano: liga × rol. Clave: `liga, rol` · 75 filas (en `modelos/reemplazo/produccion_por_rol.csv`).

Medianas y cuartiles de USG%, TS%, puntos por 100, AST% y MIN%.

| Columna | Tipo | Descripción |
|---|---|---|
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `rol` | texto | rol duro (vacío si < 5 partidos: ver `rol_mas_probable`) |
| `n` | entero | número de casos |
| `usg_pct_mediana` | número | mediana de usg_pct en el rol |
| `usg_pct_p25` | número | p25 de usg_pct en el rol |
| `usg_pct_p75` | número | p75 de usg_pct en el rol |
| `ts_pct_mediana` | número | mediana de ts_pct en el rol |
| `ts_pct_p25` | número | p25 de ts_pct en el rol |
| `ts_pct_p75` | número | p75 de ts_pct en el rol |
| `pts_100_mediana` | número | mediana de pts_100 en el rol |
| `pts_100_p25` | número | p25 de pts_100 en el rol |
| `pts_100_p75` | número | p75 de pts_100 en el rol |
| `ast_pct_mediana` | número | mediana de ast_pct en el rol |
| `ast_pct_p25` | número | p25 de ast_pct en el rol |
| `ast_pct_p75` | número | p75 de ast_pct en el rol |
| `min_pct_mediana` | número | mediana de min_pct en el rol |
| `min_pct_p25` | número | p25 de min_pct en el rol |
| `min_pct_p75` | número | p75 de min_pct en el rol |

### `data/modelos/reemplazo/libro_roles_equipos.csv`

**Libro de volumen de rol entre temporadas.** Grano: club × transición t → t+1 × rol. Clave: `liga, club, temporada_ant, rol` · 9.324 filas (en `modelos/reemplazo/libro_roles_equipos.csv`).

Volumen en minutos por partido del equipo; la identidad `vol_nuevo − vol_ant = llegadas − salidas + desplaz_minutos + desplaz_rol` se cumple con error ≈ 10⁻¹³ (`cierre_identidad`).

| Columna | Tipo | Descripción |
|---|---|---|
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `club` | texto | club estable entre temporadas (`team_id`; FEB: código de club) |
| `temporada_ant` | texto | temporada t |
| `temporada_nueva` | texto | temporada t+1 |
| `team_id_ant` | texto | id de equipo en t |
| `team_id_nuevo` | texto | id en t+1 |
| `n_retornos` | entero | jugadores que siguen |
| `n_salidas` | entero | jugadores que se van |
| `n_llegadas` | entero | llegadas |
| `min_liberados` | número | minutos por partido de los que se van |
| `min_absorbidos` | número | minutos por partido de los que llegan |
| `uso_liberado` | número | fracción del volumen de uso de t que se va |
| `uso_absorbido` | número | volumen de uso de los que llegan / volumen de t |
| `net_ant` | número | net rating del equipo en t |
| `net_nuevo` | número | net rating en t+1 |
| `delta_net` | número | net_nuevo − net_ant |
| `temporada_en_curso` | lógico | True si t+1 es la temporada en curso |
| `rol` | texto | rol duro (vacío si < 5 partidos: ver `rol_mas_probable`) |
| `vol_ant` | número | volumen del rol en t: Σ m·s (minutos por partido) |
| `vol_nuevo` | número | volumen en t+1 |
| `salidas` | número | D_k: volumen de los que se van |
| `llegadas` | número | llegadas con temporada cerrada |
| `desplaz_minutos` | número | DM_k: Σ (m' − m)·s de los que siguen |
| `desplaz_rol` | número | DR_k: Σ m'·(s' − s) de los que siguen |
| `tasa_relleno` | número | R_k = (I + DM + DR) / D (sin tope) |
| `cierre_identidad` | número | error de la identidad V' − V − (I − D + DM + DR) (≈ 0) |
| `estrategia` | texto | término dominante: `externa`, `interna_minutos`, `interna_rol` |

### `data/modelos/reemplazo/transiciones_rol.csv`

**Matrices de transición de rol de los que siguen.** Grano: liga × rol de origen × rol de destino. Clave: `liga, rol_origen, rol_destino` · 325 filas (en `modelos/reemplazo/transiciones_rol.csv`).

Jugadores con ≥ 300' en las dos temporadas.

| Columna | Tipo | Descripción |
|---|---|---|
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `rol_origen` | texto | rol en t |
| `rol_destino` | texto | rol en t+1 |
| `n` | entero | número de casos |
| `prob` | número | probabilidad de transición (matriz dura) |
| `n_suave` | número | conteo de la matriz blanda Σ s ⊗ s' |
| `prob_suave` | número | probabilidad de la matriz blanda |
| `n_jugadores_liga` | entero | jugadores de la liga en la matriz |
| `dist_vector_media` | número | distancia de variación total media entre vectores de rol |

### `data/modelos/reemplazo/retornos_jugadores.csv.gz`

**Jugadores que siguen en el club.** Grano: persona × club × transición. Clave: `liga, club, temporada_ant, persona_id` · 7.920 filas (en `modelos/reemplazo/retornos_jugadores.csv.gz`).

| Columna | Tipo | Descripción |
|---|---|---|
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `club` | texto | club estable entre temporadas (`team_id`; FEB: código de club) |
| `temporada_ant` | texto | temporada t |
| `temporada_nueva` | texto | temporada t+1 |
| `persona_id` | texto | persona entre ligas (crosswalk + unión por nombre; texto) |
| `min_ant` | número | minutos en t |
| `min_nuevo` | número | minutos en t+1 |
| `m_ant` | número | minutos por partido del equipo en t |
| `m_nuevo` | número | en t+1 |
| `rol_ant` | texto | rol en t |
| `rol_nuevo` | texto | rol en t+1 |
| `probabilistico` | lógico | True si algún vector es de muestra pequeña |
| `dist_vector_rol` | número | distancia de variación total entre vectores |
| `indice_rol_ant` | número | índice de rol esperado en t (0 RESIDUAL … 4 GO-TO-GUY) |
| `indice_rol_nuevo` | número | índice de rol esperado en t+1 |
| `ant_s_RESIDUAL` | número | pertenencia al rol RESIDUAL en t |
| `ant_s_PROFUNDIDAD` | número | pertenencia al rol PROFUNDIDAD en t |
| `ant_s_ROTACION` | número | pertenencia al rol ROTACION en t |
| `ant_s_TITULAR` | número | pertenencia al rol TITULAR en t |
| `ant_s_GO_TO_GUY` | número | pertenencia al rol GO_TO_GUY en t |
| `nuevo_s_RESIDUAL` | número | pertenencia al rol RESIDUAL en t+1 |
| `nuevo_s_PROFUNDIDAD` | número | pertenencia al rol PROFUNDIDAD en t+1 |
| `nuevo_s_ROTACION` | número | pertenencia al rol ROTACION en t+1 |
| `nuevo_s_TITULAR` | número | pertenencia al rol TITULAR en t+1 |
| `nuevo_s_GO_TO_GUY` | número | pertenencia al rol GO_TO_GUY en t+1 |

### `data/modelos/reemplazo/calidad_companeros.csv.gz`

**Calidad de compañeros.** Grano: jugador × equipo × liga × temporada. Clave: `liga, temporada, team_id, player_id` · 38.824 filas (en `modelos/reemplazo/calidad_companeros.csv.gz`).

L̄ ponderada por minutos compartidos (parejas).

| Columna | Tipo | Descripción |
|---|---|---|
| `team_id` | entero | id de equipo de la fuente (FEB: id de inscripción de esa temporada; BSL/GBL: nombre normalizado) |
| `player_id` | entero | id de jugador de la fuente (único dentro de la liga) |
| `min_compartidos` | número | minutos compartidos con compañeros (suma por parejas) |
| `L_companeros` | número | L̄: media de L de los compañeros ponderada por minutos compartidos |
| `cobertura_L` | número | fracción de minutos compartidos con L conocido |
| `L_propio` | número | L del jugador |
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `temporada` | texto | temporada `AAAA-AA` |
| `sin_L` | lógico | True si no hay L de compañeros (FEB cuando se calculó) |
| `persona_id` | texto | persona entre ligas (crosswalk + unión por nombre; texto) |
| `ts_pct` | número | TS% (%) |
| `usg_pct` | número | USG% de tiro: (FGA + 0,44·FTA) / lo mismo del equipo en pista (%) |
| `min_total` | número | minutos totales |
| `poss_on` | número | posesiones del equipo con él en pista |
| `pts` | número | puntos |

### `data/modelos/reemplazo/calidad_companeros_efecto.csv`

**Efecto de la calidad de compañeros.** Grano: métrica de producción. Clave: `produccion` · 3 filas (en `modelos/reemplazo/calidad_companeros_efecto.csv`).

Pendiente dentro de jugador y liga-temporada (asociación). Las cifras del informe F4 se calcularon antes de incluir L en las FEB; el fichero se recalcula con cada `bbfit reemplazo`.

| Columna | Tipo | Descripción |
|---|---|---|
| `produccion` | texto | métrica de producción |
| `pendiente_por_unidad_L` | número | pendiente dentro de jugador por +1 de L̄ |
| `ic_lo` | número | límite inferior del IC 90 % |
| `ic_hi` | número | límite superior del IC 90 % |
| `n_filas` | entero | filas |
| `n_personas` | entero | personas |
| `nota` | texto | nota de lectura |

### `data/modelos/reemplazo/tendencias_entrenador.csv`

**Tendencias de rotación del entrenador.** Grano: entrenador (y filas `__liga__:<liga>` de referencia, `__sin_dato__`). Clave: `entrenador_id` · 965 filas (en `modelos/reemplazo/tendencias_entrenador.csv`).

Rotación = jugadores con ≥ 10' (escala 40'); curva de reparto por rango r1-r12; `_contraido` = hacia la liga con k = 30 partidos.

| Columna | Tipo | Descripción |
|---|---|---|
| `entrenador_id` | texto | id de entrenador (slug del nombre; común a todas las ligas) |
| `rotacion` | número | jugadores con ≥ 15' de media |
| `hhi` | número | HHI de minutos por partido |
| `cuota_r1` | número | cuota de minutos del rango 1 de la rotación |
| `cuota_r2` | número | cuota de minutos del rango 2 de la rotación |
| `cuota_r3` | número | cuota de minutos del rango 3 de la rotación |
| `cuota_r4` | número | cuota de minutos del rango 4 de la rotación |
| `cuota_r5` | número | cuota de minutos del rango 5 de la rotación |
| `cuota_r6` | número | cuota de minutos del rango 6 de la rotación |
| `cuota_r7` | número | cuota de minutos del rango 7 de la rotación |
| `cuota_r8` | número | cuota de minutos del rango 8 de la rotación |
| `cuota_r9` | número | cuota de minutos del rango 9 de la rotación |
| `cuota_r10` | número | cuota de minutos del rango 10 de la rotación |
| `cuota_r11` | número | cuota de minutos del rango 11 de la rotación |
| `cuota_r12` | número | cuota de minutos del rango 12 de la rotación |
| `rotacion_sd` | número | desviación de la rotación partido a partido |
| `n_partidos` | entero | partidos jugados en el tramo |
| `liga_principal` | texto | liga con más partidos/minutos |
| `rotacion_contraido` | número | rotación contraída hacia la liga (k = 30 partidos) |
| `hhi_contraido` | número | HHI contraído |
| `cuota_r1_contraido` | número | cuota de minutos del rango 1 de la rotación (contraída hacia la liga) |
| `cuota_r2_contraido` | número | cuota de minutos del rango 2 de la rotación (contraída hacia la liga) |
| `cuota_r3_contraido` | número | cuota de minutos del rango 3 de la rotación (contraída hacia la liga) |
| `cuota_r4_contraido` | número | cuota de minutos del rango 4 de la rotación (contraída hacia la liga) |
| `cuota_r5_contraido` | número | cuota de minutos del rango 5 de la rotación (contraída hacia la liga) |
| `cuota_r6_contraido` | número | cuota de minutos del rango 6 de la rotación (contraída hacia la liga) |
| `cuota_r7_contraido` | número | cuota de minutos del rango 7 de la rotación (contraída hacia la liga) |
| `cuota_r8_contraido` | número | cuota de minutos del rango 8 de la rotación (contraída hacia la liga) |
| `cuota_r9_contraido` | número | cuota de minutos del rango 9 de la rotación (contraída hacia la liga) |
| `cuota_r10_contraido` | número | cuota de minutos del rango 10 de la rotación (contraída hacia la liga) |
| `cuota_r11_contraido` | número | cuota de minutos del rango 11 de la rotación (contraída hacia la liga) |
| `cuota_r12_contraido` | número | cuota de minutos del rango 12 de la rotación (contraída hacia la liga) |

### `data/modelos/reemplazo/asociacion_relleno_net.csv`

**Asociación estrategia de relleno ↔ Δ Net.** Grano: medida × grupo. Clave: `medida, grupo` · 5 filas (en `modelos/reemplazo/asociacion_relleno_net.csv`).

Bootstrap; **no causal**.

| Columna | Tipo | Descripción |
|---|---|---|
| `medida` | texto | medida |
| `grupo` | texto | grupo |
| `n` | entero | número de casos |
| `valor` | número | valor |
| `ic_lo` | número | límite inferior del IC 90 % |
| `ic_hi` | número | límite superior del IC 90 % |
| `nota` | texto | nota de lectura |

`resumen.json`: cierre de la identidad, medianas del libro, primera etapa del IV.

### Entropía y volatilidad (`entropia/`, fase 5)

### `data/modelos/entropia/jugadores.csv.gz`

**Entropía de estilo, de rol y volatilidad del jugador.** Grano: jugador × equipo × liga × temporada (regular + playoffs). Clave: `liga, temporada, team_id, player_id` · 41.659 filas (en `modelos/entropia/jugadores.csv.gz`).

Conteos de acciones (T2, T3, zonas, visitas al TL, AST, TOV, faltas recibidas, OREB) → H_estilo posterior (Dirichlet α = 5, 400 muestras, IC 90 %); σ_i con contracción por liga × pos3.

| Columna | Tipo | Descripción |
|---|---|---|
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `temporada` | texto | temporada `AAAA-AA` |
| `team_id` | entero | id de equipo de la fuente (FEB: id de inscripción de esa temporada; BSL/GBL: nombre normalizado) |
| `player_id` | entero | id de jugador de la fuente (único dentro de la liga) |
| `persona_id` | texto | persona entre ligas (crosswalk + unión por nombre; texto) |
| `nombre` | texto | nombre del jugador |
| `pos3` | texto | posición en 3 grupos: E exterior, A alero, I interior (oficial o estimada) |
| `fuente` | texto | `pbp` (tramos de jugada a jugada) o `box` (respaldo de caja) |
| `gp` | número | partidos jugados |
| `min_total` | número | minutos totales |
| `rol_mas_probable` | texto | rol con mayor probabilidad del vector p_k |
| `H_rol` | número | entropía del reparto de estados de rol por partido (bits) |
| `H_rol_norm` | número | H_rol / log2(5) |
| `n_RESIDUAL` | número | partidos en el estado RESIDUAL (o jugadores con ese rol, en equipos) |
| `n_PROFUNDIDAD` | número | partidos en el estado PROFUNDIDAD (o jugadores con ese rol, en equipos) |
| `n_ROTACION` | número | partidos en el estado ROTACION (o jugadores con ese rol, en equipos) |
| `n_TITULAR` | número | partidos en el estado TITULAR (o jugadores con ese rol, en equipos) |
| `n_GO_TO_GUY` | número | partidos en el estado GO-TO-GUY (o jugadores con ese rol, en equipos) |
| `T2` | número | tiros de 2 intentados |
| `T3` | número | triples intentados |
| `fta` | número | tiros libres intentados |
| `visitas_tl` | número | 0,44·FTA |
| `aro` | número | % de tiros en el aro, < 1,8 m (0-1) (valor bruto, contraído en jugadores) |
| `corta` | número | tiros de corta distancia |
| `media` | número | tiros de media distancia |
| `t3_esquina` | número | triples de esquina |
| `t3_frontal` | número | triples frontales |
| `cobertura_zonas` | número | fracción de tiros con zona |
| `ast` | número | asistencias |
| `tov` | número | pérdidas |
| `pfd` | número | faltas recibidas |
| `oreb` | número | rebotes ofensivos |
| `nivel_categorias` | texto | `zonas` (10 categorías) o `basico` (7) |
| `origen_zonas` | texto | fuente de la calibración de zonas |
| `H_estilo_basico` | número | entropía básica posterior (7 categorías, bits) |
| `H_estilo_basico_lo` | número | IC 90 % inferior |
| `H_estilo_basico_hi` | número | IC 90 % superior |
| `H_estilo_basico_bruta` | número | entropía empírica básica |
| `K_basico` | número | categorías básicas usadas |
| `H_estilo_basico_norm` | número | básica / log2 K |
| `H_estilo` | número | entropía de estilo posterior (10 categorías con zonas, bits) |
| `H_estilo_lo` | número | IC 90 % inferior |
| `H_estilo_hi` | número | IC 90 % superior |
| `H_estilo_bruta` | número | entropía empírica |
| `K_estilo` | número | categorías usadas |
| `H_estilo_norm` | número | H_estilo / log2 K |
| `acciones` | número | acciones contadas |
| `muestra_pequena` | lógico | True si < 20 acciones |
| `categorias_faltantes` | número | categorías que la liga no publica (excluidas, no 0) |
| `caja_fusionada` | número | registros de caja fusionados (traspasos) |
| `H_rol_post` | número | H_rol posterior Dirichlet (bits) |
| `H_rol_lo` | número | IC 90 % inferior |
| `H_rol_hi` | número | IC 90 % superior |
| `n_partidos_vol` | número | partidos válidos de la volatilidad |
| `y_media` | número | producción media por 100 posesiones: 100·(PTS + AST)/poss |
| `sin_ast` | texto | True si la fuente no enlaza asistencias (sólo puntos) |
| `log_s2` | número | log de la varianza residual reescalada (corregido de sesgo) |
| `var_muestreo` | número | 2/(n − 1) |
| `log_s2_post` | número | media posterior de log σ² |
| `log_s2_sd` | número | desviación posterior |
| `tau2_grupo` | número | τ² del grupo liga × pos3 |
| `w_contraccion` | número | peso de los datos propios (0-1) |
| `sigma` | número | σ_i: volatilidad (puntos por 100 posesiones en un partido de 30 posesiones) |
| `sigma_lo` | número | IC 90 % inferior |
| `sigma_hi` | número | IC 90 % superior |
| `sigma_bruta` | número | σ sin contraer |

### `data/modelos/entropia/equipos.csv`

**Concentración y entropía del equipo.** Grano: equipo × temporada. Clave: `liga, temporada, team_id` · 2.394 filas (en `modelos/entropia/equipos.csv`).

Reparto del uso (FGA + 0,44·FTA), de tiros y de minutos; red de pases de `asistencias.csv` (fase total).

| Columna | Tipo | Descripción |
|---|---|---|
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `temporada` | texto | temporada `AAAA-AA` |
| `team_id` | texto | id de equipo de la fuente (FEB: id de inscripción de esa temporada; BSL/GBL: nombre normalizado) |
| `jugadores` | entero | jugadores |
| `hhi_uso` | número | Herfindahl del reparto del uso |
| `H_uso` | número | entropía del reparto del uso (bits) |
| `n_efectivo_uso` | número | número efectivo 2^H del uso |
| `H_uso_norm` | número | H_uso / log2(n) |
| `hhi_tiros` | número | HHI de tiros |
| `H_tiros` | número | entropía de tiros (bits) |
| `n_efectivo_tiros` | número | número efectivo de tiros |
| `H_tiros_norm` | número | normalizada |
| `hhi_minutos` | número | Herfindahl del reparto de minutos |
| `H_minutos` | número | entropía de minutos (bits) |
| `n_efectivo_minutos` | número | número efectivo de minutos |
| `H_minutos_norm` | número | normalizada |
| `H_red_pases` | número | entropía de la red pasador → anotador (bits) |
| `hhi_red_pases` | número | HHI de las aristas de la red |
| `aristas_red` | entero | parejas con asistencias |
| `nodos_red` | entero | jugadores en la red |
| `H_red_pases_norm` | número | H_red / log2(n(n−1)) |
| `H_pasadores` | número | entropía de los pasadores (bits) |
| `H_receptores` | número | entropía de los receptores (bits) |
| `asistencias` | número | asistencias de la red |
| `H_rol_medio_minutos` | número | H_rol medio ponderado por minutos |

### Estilos unificados (`estilos_unificados/`, fase 6)

### `data/modelos/estilos_unificados/equipos.csv`

**Estilo unificado del equipo.** Grano: equipo × temporada (`nivel = temporada`) o tramo de entrenador (`nivel = tramo`). Clave: `liga, temporada, team_id, nivel, entrenador_id` · 3.130 filas (en `modelos/estilos_unificados/equipos.csv`).

Rasgos brutos (equipo) y su z por rangos dentro de la liga-temporada (equipos sin ponderar). Estilos: `pistons`, `isolation`, `old_school`, `spacing`, `circulacion`, `pintura`.

| Columna | Tipo | Descripción |
|---|---|---|
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `temporada` | texto | temporada `AAAA-AA` |
| `team_id` | texto | id de equipo de la fuente (FEB: id de inscripción de esa temporada; BSL/GBL: nombre normalizado) |
| `equipo` | texto | nombre del equipo |
| `nivel` | texto | `temporada` o `tramo` (tramo de entrenador) |
| `entrenador_id` | texto | id de entrenador (slug del nombre; común a todas las ligas) |
| `entrenador` | texto | nombre del entrenador |
| `gp` | entero | partidos jugados |
| `n_partidos` | número | partidos jugados en el tramo |
| `peso_tramo` | número | peso del jugada a jugada del tramo (n/(n+8) o m/(m+200)) |
| `en_ajuste` | lógico | True si entró en el ajuste de la mezcla |
| `estilo` | texto | estilo principal (id) |
| `estilo_nombre` | texto | nombre del estilo |
| `p_estilo` | número | probabilidad del estilo principal |
| `estilo2` | texto | estilo secundario |
| `estilo2_nombre` | texto | nombre del secundario |
| `p_estilo2` | número | probabilidad del secundario |
| `etiqueta` | texto | «<Estilo> puro» (p ≥ 0,80), «A · B» (p₂ ≥ 0,25) o «<Estilo>» |
| `p_pistons` | número | probabilidad del estilo pistons |
| `p_isolation` | número | probabilidad del estilo isolation |
| `p_old_school` | número | probabilidad del estilo old_school |
| `p_spacing` | número | probabilidad del estilo spacing |
| `p_circulacion` | número | probabilidad del estilo circulacion |
| `p_pintura` | número | probabilidad del estilo pintura |
| `ritmo` | número | ritmo (posesiones por 40') (valor bruto, contraído en jugadores) |
| `triple` | número | 3PAr: triples / tiros de campo (0-1) (valor bruto, contraído en jugadores) |
| `esquina` | número | % de tiros que son triple de esquina (0-1) (valor bruto, contraído en jugadores) |
| `aro` | número | % de tiros en el aro, < 1,8 m (0-1) (valor bruto, contraído en jugadores) |
| `tiros_libres` | número | FTr: tiros libres / tiros de campo (valor bruto, contraído en jugadores) |
| `autocreacion` | número | % de canastas propias sin asistencia (0-1) (valor bruto, contraído en jugadores) |
| `asistencia` | número | AST% (%) (valor bruto, contraído en jugadores) |
| `reb_ofensivo` | número | rebotes ofensivos por 100 posesiones (valor bruto, contraído en jugadores) |
| `perdidas` | número | TOV% (pérdidas por posesión usada, %) (valor bruto, contraído en jugadores) |
| `robos` | número | robos por 100 posesiones (valor bruto, contraído en jugadores) |
| `tapones` | número | tapones por 100 posesiones (valor bruto, contraído en jugadores) |
| `faltas` | número | faltas por 100 posesiones (valor bruto, contraído en jugadores) |
| `z_ritmo` | número | z por rangos dentro de la liga-temporada de: ritmo (posesiones por 40') |
| `z_triple` | número | z por rangos dentro de la liga-temporada de: 3PAr: triples / tiros de campo (0-1) |
| `z_esquina` | número | z por rangos dentro de la liga-temporada de: % de tiros que son triple de esquina (0-1) |
| `z_aro` | número | z por rangos dentro de la liga-temporada de: % de tiros en el aro, < 1,8 m (0-1) |
| `z_tiros_libres` | número | z por rangos dentro de la liga-temporada de: FTr: tiros libres / tiros de campo |
| `z_autocreacion` | número | z por rangos dentro de la liga-temporada de: % de canastas propias sin asistencia (0-1) |
| `z_asistencia` | número | z por rangos dentro de la liga-temporada de: AST% (%) |
| `z_reb_ofensivo` | número | z por rangos dentro de la liga-temporada de: rebotes ofensivos por 100 posesiones |
| `z_perdidas` | número | z por rangos dentro de la liga-temporada de: TOV% (pérdidas por posesión usada, %) |
| `z_robos` | número | z por rangos dentro de la liga-temporada de: robos por 100 posesiones |
| `z_tapones` | número | z por rangos dentro de la liga-temporada de: tapones por 100 posesiones |
| `z_faltas` | número | z por rangos dentro de la liga-temporada de: faltas por 100 posesiones |
| `clave_vade` | texto | clave del club en la tabla VaDE (liga:team:temporada) |

### `data/modelos/estilos_unificados/jugadores.csv.gz`

**Estilo unificado del jugador.** Grano: jugador × equipo × liga × temporada (≥ 40 min) o tramo de entrenador. Clave: `liga, temporada, team_id, player_id, nivel, entrenador_id` · 37.944 filas (en `modelos/estilos_unificados/jugadores.csv.gz`).

Tasa del jugador contraída m/(m+150) hacia su liga; z ponderada por minutos. `fiable` = ≥ 300 min.

| Columna | Tipo | Descripción |
|---|---|---|
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `temporada` | texto | temporada `AAAA-AA` |
| `team_id` | texto | id de equipo de la fuente (FEB: id de inscripción de esa temporada; BSL/GBL: nombre normalizado) |
| `equipo` | texto | nombre del equipo |
| `player_id` | texto | id de jugador de la fuente (único dentro de la liga) |
| `pid_estilos` | texto | id del jugador en el módulo de estilos |
| `nombre` | texto | nombre del jugador |
| `posicion` | texto | posición oficial |
| `nivel` | texto | `temporada` o `tramo` (tramo de entrenador) |
| `entrenador_id` | texto | id de entrenador (slug del nombre; común a todas las ligas) |
| `entrenador` | texto | nombre del entrenador |
| `min` | número | minutos |
| `peso_tramo` | número | peso del jugada a jugada del tramo (n/(n+8) o m/(m+200)) |
| `fiable` | lógico | True si ≥ 300 minutos |
| `en_ajuste` | lógico | True si entró en el ajuste de la mezcla |
| `traspaso` | lógico | True si jugó en más de un equipo |
| `estilo` | texto | estilo principal (id) |
| `estilo_nombre` | texto | nombre del estilo |
| `p_estilo` | número | probabilidad del estilo principal |
| `estilo2` | texto | estilo secundario |
| `estilo2_nombre` | texto | nombre del secundario |
| `p_estilo2` | número | probabilidad del secundario |
| `etiqueta` | texto | «<Estilo> puro» (p ≥ 0,80), «A · B» (p₂ ≥ 0,25) o «<Estilo>» |
| `p_pistons` | número | probabilidad del estilo pistons |
| `p_isolation` | número | probabilidad del estilo isolation |
| `p_old_school` | número | probabilidad del estilo old_school |
| `p_spacing` | número | probabilidad del estilo spacing |
| `p_circulacion` | número | probabilidad del estilo circulacion |
| `p_pintura` | número | probabilidad del estilo pintura |
| `ritmo` | número | ritmo (posesiones por 40') (valor bruto, contraído en jugadores) |
| `triple` | número | 3PAr: triples / tiros de campo (0-1) (valor bruto, contraído en jugadores) |
| `esquina` | número | % de tiros que son triple de esquina (0-1) (valor bruto, contraído en jugadores) |
| `aro` | número | % de tiros en el aro, < 1,8 m (0-1) (valor bruto, contraído en jugadores) |
| `tiros_libres` | número | FTr: tiros libres / tiros de campo (valor bruto, contraído en jugadores) |
| `autocreacion` | número | % de canastas propias sin asistencia (0-1) (valor bruto, contraído en jugadores) |
| `asistencia` | número | AST% (%) (valor bruto, contraído en jugadores) |
| `reb_ofensivo` | número | rebotes ofensivos por 100 posesiones (valor bruto, contraído en jugadores) |
| `perdidas` | número | TOV% (pérdidas por posesión usada, %) (valor bruto, contraído en jugadores) |
| `robos` | número | robos por 100 posesiones (valor bruto, contraído en jugadores) |
| `tapones` | número | tapones por 100 posesiones (valor bruto, contraído en jugadores) |
| `faltas` | número | faltas por 100 posesiones (valor bruto, contraído en jugadores) |
| `z_ritmo` | número | z por rangos dentro de la liga-temporada de: ritmo (posesiones por 40') |
| `z_triple` | número | z por rangos dentro de la liga-temporada de: 3PAr: triples / tiros de campo (0-1) |
| `z_esquina` | número | z por rangos dentro de la liga-temporada de: % de tiros que son triple de esquina (0-1) |
| `z_aro` | número | z por rangos dentro de la liga-temporada de: % de tiros en el aro, < 1,8 m (0-1) |
| `z_tiros_libres` | número | z por rangos dentro de la liga-temporada de: FTr: tiros libres / tiros de campo |
| `z_autocreacion` | número | z por rangos dentro de la liga-temporada de: % de canastas propias sin asistencia (0-1) |
| `z_asistencia` | número | z por rangos dentro de la liga-temporada de: AST% (%) |
| `z_reb_ofensivo` | número | z por rangos dentro de la liga-temporada de: rebotes ofensivos por 100 posesiones |
| `z_perdidas` | número | z por rangos dentro de la liga-temporada de: TOV% (pérdidas por posesión usada, %) |
| `z_robos` | número | z por rangos dentro de la liga-temporada de: robos por 100 posesiones |
| `z_tapones` | número | z por rangos dentro de la liga-temporada de: tapones por 100 posesiones |
| `z_faltas` | número | z por rangos dentro de la liga-temporada de: faltas por 100 posesiones |

### `data/modelos/estilos_unificados/correspondencia_vade.csv`

**Correspondencia VaDE ↔ estilos unificados.** Grano: estilo VaDE. Clave: `estilo_vade` · 6 filas (en `modelos/estilos_unificados/correspondencia_vade.csv`).

ARI 0,031, NMI 0,046 (informe F6).

| Columna | Tipo | Descripción |
|---|---|---|
| `estilo_vade` | texto | estilo VaDE (E01…E06) |
| `nombre_vade` | texto | nombre del estilo VaDE |
| `equipos` | entero | equipos |
| `n_pistons` | entero | equipos VaDE asignados a pistons |
| `n_isolation` | entero | equipos VaDE asignados a isolation |
| `n_old_school` | entero | equipos VaDE asignados a old_school |
| `n_spacing` | entero | equipos VaDE asignados a spacing |
| `n_circulacion` | entero | equipos VaDE asignados a circulacion |
| `n_pintura` | entero | equipos VaDE asignados a pintura |
| `pct_pistons` | número | % de ellos en pistons |
| `pct_isolation` | número | % de ellos en isolation |
| `pct_old_school` | número | % de ellos en old_school |
| `pct_spacing` | número | % de ellos en spacing |
| `pct_circulacion` | número | % de ellos en circulacion |
| `pct_pintura` | número | % de ellos en pintura |
| `principal_nuevo` | texto | estilo unificado más frecuente |

Además: `estilos.json` (fichas de los 6 estilos: definición de equipo y de jugador, centroide, rasgos que lo caracterizan, ejemplos; mezcla completa; resumen) y `seleccion_k.json` (BIC, ARI bootstrap y grupo mínimo por K y covarianza; alternativas descartadas).

### Adaptación al cambio de liga (`adaptacion/`, fase 7)

### `data/modelos/adaptacion/adaptation_priors.csv`

**Priors de adaptación (interfaz `bbfit.adaptacion.prior`).** Grano: nivel de la jerarquía × celda × métrica. Clave: `nivel, liga_origen, liga_destino, grupo_nacionalidad, pos3, metrica` · 9.696 filas (en `modelos/adaptacion/adaptation_priors.csv`).

`nivel` ∈ celda, par_grupo, par, escalon_grupo, escalon, global_grupo, global (se usa el primero con n ≥ 8). δ relativo (L: aditivo); curva 1 + δ·exp(−g/κ) con g = partidos en la liga nueva.

| Columna | Tipo | Descripción |
|---|---|---|
| `nivel` | texto | `temporada` o `tramo` (tramo de entrenador) |
| `liga_origen` | texto | liga de origen |
| `liga_destino` | texto | liga de destino |
| `grupo_nacionalidad` | texto | grupo de nacionalidad (9 grupos) |
| `pos3` | texto | posición en 3 grupos: E exterior, A alero, I interior (oficial o estimada) |
| `escalon_destino` | texto | escalón de la liga de destino |
| `metrica` | texto | métrica |
| `unidad` | texto | `relativa` (fracción) o `aditiva` (unidades de L) |
| `n` | entero | número de casos |
| `n_efectivo_ipcw` | número | n efectivo con los pesos IPCW |
| `delta_media` | número | δ de la interfaz (media) |
| `delta_sd` | número | δ (sd) |
| `delta_lo` | número | δ IC 90 % inferior |
| `delta_hi` | número | δ IC 90 % superior |
| `kappa_media` | número | κ de la interfaz (partidos; hasta 500 = persistente) |
| `kappa_sd` | número | sd de κ |
| `kappa_lo` | número | κ inferior |
| `kappa_hi` | número | κ superior |
| `delta_temporada_media` | número | Δ de temporada (media) |
| `delta_temporada_sd` | número | sd |
| `delta_temporada_lo` | número | IC inferior |
| `delta_temporada_hi` | número | IC superior |
| `p_delta_temporada_negativo` | número | P(Δ < 0) |
| `serie_curva` | texto | serie por partido de la curva |
| `grupo_curva` | texto | grupo de la curva |
| `D_forma_media` | número | D del transitorio |
| `kappa_forma_media` | número | κ del transitorio (partidos) |
| `kappa_forma_lo` | número | inferior |
| `kappa_forma_hi` | número | superior |
| `partidos_50` | número | partidos hasta cerrar el 50 % del hueco |
| `partidos_90` | número | partidos hasta el 90 % |
| `partidos_1a_temporada` | número | partidos de la 1.ª temporada (mediana) |
| `contraccion_par` | número | contracción del efecto de pareja (0 = previa, 1 = datos) |

### `data/modelos/adaptacion/adapt_historico.csv.gz`

**Traspasos con ŷ, observado y ADAPT%.** Grano: traspaso (persona × liga de origen → liga de destino × temporada de destino). Clave: `id` · 5.040 filas (en `modelos/adaptacion/adapt_historico.csv.gz`).

ADAPT% = E[y]/ŷ × 100 (100 = lo esperado). Banderas: `*_desconocido` (covariable ausente, valor 0 en el modelo), `en_curso` (2026-27, censura administrativa), `observado` (no censurado), `w_ipcw`.

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | texto | id del traspaso (persona:liga:temporada de destino) |
| `persona_id` | entero | persona entre ligas (crosswalk + unión por nombre; texto) |
| `nombre` | texto | nombre del jugador |
| `tipo` | texto | `salida`, `adicion` o `intra` (dentro de la temporada) |
| `regreso` | lógico | vuelve a una liga ya jugada |
| `liga_origen` | texto | liga de origen |
| `temporada_origen` | texto | temporada de origen |
| `player_id_origen` | texto | id en origen |
| `liga_destino` | texto | liga de destino |
| `temporada_destino` | texto | temporada de destino |
| `player_id_destino` | texto | id en destino |
| `team_destino` | texto | equipo de destino |
| `grupo_nacionalidad` | texto | grupo de nacionalidad (9 grupos) |
| `nacionalidad_iso` | texto | nacionalidad ISO alfa-2 |
| `nacionalidad_desconocida` | lógico | sin nacionalidad (no se imputa) |
| `pos3` | texto | posición en 3 grupos: E exterior, A alero, I interior (oficial o estimada) |
| `edad` | número | edad en destino |
| `edad_desconocida` | lógico | sin edad |
| `arquetipo` | texto | estilo unificado del jugador en origen |
| `rol_origen` | texto | rol en t |
| `rol_destino` | texto | rol en t+1 |
| `cambio_rol` | número | escalones de rol subidos (destino − origen; endógeno) |
| `rol_desconocido` | lógico | sin rol |
| `distancia_estilo_equipo` | número | variación total entre las pertenencias de estilo del equipo de origen y del de destino |
| `estilo_desconocido` | lógico | sin estilo |
| `cambio_entrenador` | número | cambia de entrenador |
| `entrenador_desconocido` | lógico | sin entrenador |
| `canterano` | número | NaN: no hay fuente |
| `canterano_desconocido` | lógico | siempre True |
| `salto_nivel` | número | nivel de destino − origen (DT EuroLeague) |
| `direccion` | texto | `sube`, `baja` o `lateral` |
| `escalon_destino` | texto | escalón de destino |
| `primer_anio_europa` | lógico | primer año en Europa (estadounidense) |
| `min_origen` | número | minutos en origen |
| `min_destino` | número | minutos en destino |
| `partidos_destino` | número | partidos en destino |
| `observado` | lógico | True si juega ≥ 25 % de los minutos disponibles y ≥ 150' |
| `en_curso` | lógico | destino en la temporada en curso |
| `p_observado` | número | probabilidad de ser observado (logit de censura) |
| `w_ipcw` | número | peso IPCW = 1/p (recortado) |
| `pts_p100_esperado` | número | ŷ: valor esperado tras la normalización (pts_p100) |
| `pts_p100_esperado_lo` | número | ŷ, IC 80 % inferior (pts_p100) |
| `pts_p100_esperado_hi` | número | ŷ, IC 80 % superior (pts_p100) |
| `pts_p100_observado` | número | valor observado en destino (pts_p100) |
| `adapt_pts_p100_obs` | número | ADAPT% observado (pts_p100) |
| `adapt_pts_p100` | número | ADAPT% previsto (pts_p100) |
| `adapt_pts_p100_lo` | número | ADAPT% IC 80 % inferior (pts_p100) |
| `adapt_pts_p100_hi` | número | ADAPT% IC 80 % superior (pts_p100) |
| `adapt_pts_p100_pi_lo` | número | ADAPT% predictivo 80 % inferior (pts_p100) |
| `adapt_pts_p100_pi_hi` | número | ADAPT% predictivo 80 % superior (pts_p100) |
| `adapt_pts_p100_fuera_muestra` | número | ADAPT% previsto sin fuga (pts_p100) |
| `adapt_pts_p100_primeros10` | número | ADAPT% previsto, primeros 10 partidos (pts_p100) |
| `adapt_pts_p100_primeros10_obs` | número | ADAPT% observado, primeros 10 partidos (pts_p100) |
| `ts_pct_esperado` | número | ŷ: valor esperado tras la normalización (ts_pct) |
| `ts_pct_esperado_lo` | número | ŷ, IC 80 % inferior (ts_pct) |
| `ts_pct_esperado_hi` | número | ŷ, IC 80 % superior (ts_pct) |
| `ts_pct_observado` | número | valor observado en destino (ts_pct) |
| `adapt_ts_pct_obs` | número | ADAPT% observado (ts_pct) |
| `adapt_ts_pct` | número | ADAPT% previsto (ts_pct) |
| `adapt_ts_pct_lo` | número | ADAPT% IC 80 % inferior (ts_pct) |
| `adapt_ts_pct_hi` | número | ADAPT% IC 80 % superior (ts_pct) |
| `adapt_ts_pct_pi_lo` | número | ADAPT% predictivo 80 % inferior (ts_pct) |
| `adapt_ts_pct_pi_hi` | número | ADAPT% predictivo 80 % superior (ts_pct) |
| `adapt_ts_pct_fuera_muestra` | número | ADAPT% previsto sin fuga (ts_pct) |
| `adapt_ts_pct_primeros10` | número | ADAPT% previsto, primeros 10 partidos (ts_pct) |
| `adapt_ts_pct_primeros10_obs` | número | ADAPT% observado, primeros 10 partidos (ts_pct) |
| `usg_pct_esperado` | número | ŷ: valor esperado tras la normalización (usg_pct) |
| `usg_pct_esperado_lo` | número | ŷ, IC 80 % inferior (usg_pct) |
| `usg_pct_esperado_hi` | número | ŷ, IC 80 % superior (usg_pct) |
| `usg_pct_observado` | número | valor observado en destino (usg_pct) |
| `adapt_usg_pct_obs` | número | ADAPT% observado (usg_pct) |
| `adapt_usg_pct` | número | ADAPT% previsto (usg_pct) |
| `adapt_usg_pct_lo` | número | ADAPT% IC 80 % inferior (usg_pct) |
| `adapt_usg_pct_hi` | número | ADAPT% IC 80 % superior (usg_pct) |
| `adapt_usg_pct_pi_lo` | número | ADAPT% predictivo 80 % inferior (usg_pct) |
| `adapt_usg_pct_pi_hi` | número | ADAPT% predictivo 80 % superior (usg_pct) |
| `adapt_usg_pct_fuera_muestra` | número | ADAPT% previsto sin fuga (usg_pct) |
| `adapt_usg_pct_primeros10` | número | ADAPT% previsto, primeros 10 partidos (usg_pct) |
| `adapt_usg_pct_primeros10_obs` | número | ADAPT% observado, primeros 10 partidos (usg_pct) |
| `ast_pct_esperado` | número | ŷ: valor esperado tras la normalización (ast_pct) |
| `ast_pct_esperado_lo` | número | ŷ, IC 80 % inferior (ast_pct) |
| `ast_pct_esperado_hi` | número | ŷ, IC 80 % superior (ast_pct) |
| `ast_pct_observado` | número | valor observado en destino (ast_pct) |
| `adapt_ast_pct_obs` | número | ADAPT% observado (ast_pct) |
| `adapt_ast_pct` | número | ADAPT% previsto (ast_pct) |
| `adapt_ast_pct_lo` | número | ADAPT% IC 80 % inferior (ast_pct) |
| `adapt_ast_pct_hi` | número | ADAPT% IC 80 % superior (ast_pct) |
| `adapt_ast_pct_pi_lo` | número | ADAPT% predictivo 80 % inferior (ast_pct) |
| `adapt_ast_pct_pi_hi` | número | ADAPT% predictivo 80 % superior (ast_pct) |
| `adapt_ast_pct_fuera_muestra` | número | ADAPT% previsto sin fuga (ast_pct) |
| `adapt_ast_pct_primeros10` | número | ADAPT% previsto, primeros 10 partidos (ast_pct) |
| `reb_p100_esperado` | número | ŷ: valor esperado tras la normalización (reb_p100) |
| `reb_p100_esperado_lo` | número | ŷ, IC 80 % inferior (reb_p100) |
| `reb_p100_esperado_hi` | número | ŷ, IC 80 % superior (reb_p100) |
| `reb_p100_observado` | número | valor observado en destino (reb_p100) |
| `adapt_reb_p100_obs` | número | ADAPT% observado (reb_p100) |
| `adapt_reb_p100` | número | ADAPT% previsto (reb_p100) |
| `adapt_reb_p100_lo` | número | ADAPT% IC 80 % inferior (reb_p100) |
| `adapt_reb_p100_hi` | número | ADAPT% IC 80 % superior (reb_p100) |
| `adapt_reb_p100_pi_lo` | número | ADAPT% predictivo 80 % inferior (reb_p100) |
| `adapt_reb_p100_pi_hi` | número | ADAPT% predictivo 80 % superior (reb_p100) |
| `adapt_reb_p100_fuera_muestra` | número | ADAPT% previsto sin fuga (reb_p100) |
| `adapt_reb_p100_primeros10` | número | ADAPT% previsto, primeros 10 partidos (reb_p100) |
| `per_esperado` | número | ŷ: valor esperado tras la normalización (per) |
| `per_esperado_lo` | número | ŷ, IC 80 % inferior (per) |
| `per_esperado_hi` | número | ŷ, IC 80 % superior (per) |
| `per_observado` | número | valor observado en destino (per) |
| `adapt_per_obs` | número | ADAPT% observado (per) |
| `adapt_per` | número | ADAPT% previsto (per) |
| `adapt_per_lo` | número | ADAPT% IC 80 % inferior (per) |
| `adapt_per_hi` | número | ADAPT% IC 80 % superior (per) |
| `adapt_per_pi_lo` | número | ADAPT% predictivo 80 % inferior (per) |
| `adapt_per_pi_hi` | número | ADAPT% predictivo 80 % superior (per) |
| `adapt_per_fuera_muestra` | número | ADAPT% previsto sin fuga (per) |
| `adapt_per_primeros10` | número | ADAPT% previsto, primeros 10 partidos (per) |
| `L_esperado` | número | L esperado |
| `L_observado` | número | L observado |
| `delta_L_obs` | número | ΔL observado (aditivo) |
| `delta_L` | número | ΔL previsto |
| `delta_L_lo` | número | IC 80 % inferior |
| `delta_L_hi` | número | IC 80 % superior |
| `delta_L_pi_lo` | número | predictivo 80 % inferior |
| `delta_L_pi_hi` | número | predictivo 80 % superior |
| `adapt_L_rel_obs` | número | ADAPT% observado (L_rel) |
| `adapt_L_rel` | número | ADAPT% previsto (L_rel) |
| `adapt_L_rel_lo` | número | ADAPT% IC 80 % inferior (L_rel) |
| `adapt_L_rel_hi` | número | ADAPT% IC 80 % superior (L_rel) |
| `adapt_L_rel_pi_lo` | número | ADAPT% predictivo 80 % inferior (L_rel) |
| `adapt_L_rel_pi_hi` | número | ADAPT% predictivo 80 % superior (L_rel) |
| `adapt_L_rel_fuera_muestra` | número | ADAPT% previsto sin fuga (L_rel) |
| `adapt_L_rel_primeros10` | número | ADAPT% previsto, primeros 10 partidos (L_rel) |
| `adapt_L_rel_primeros10_obs` | número | ADAPT% observado, primeros 10 partidos (L_rel) |
| `adapt_pct` | número | ADAPT% principal (= `adapt_L_rel`) |
| `adapt_pct_lo` | número | IC 80 % inferior |
| `adapt_pct_hi` | número | IC 80 % superior |
| `adapt_pct_obs` | número | observado |
| `adapt_pct_primeros10` | número | previsto en los primeros 10 partidos |
| `adapt_pct_primeros10_obs` | número | observado en los primeros 10 partidos |

### `data/modelos/adaptacion/adapt_pct_roles.csv`

**ADAPT% para unir a la tabla de roles.** Grano: jugador × liga × temporada de destino. Clave: `liga, temporada, player_id, team_id` · 5.040 filas (en `modelos/adaptacion/adapt_pct_roles.csv`).

Se une con `bbfit.adaptacion.rellenar_adapt_pct(df)`.

| Columna | Tipo | Descripción |
|---|---|---|
| `liga` | texto | código de competición (`acb`, `euroleague`, `feb1`…) |
| `temporada` | texto | temporada `AAAA-AA` |
| `player_id` | texto | id de jugador de la fuente (único dentro de la liga) |
| `team_id` | texto | id de equipo de la fuente (FEB: id de inscripción de esa temporada; BSL/GBL: nombre normalizado) |
| `adapt_pct` | número | vacío en este fichero: el ADAPT% está en `adaptacion/adapt_pct_roles.csv` (`bbfit.adaptacion.rellenar_adapt_pct`) |
| `adapt_pct_lo` | número | IC 80 % inferior |
| `adapt_pct_hi` | número | IC 80 % superior |
| `adapt_pct_obs` | número | ADAPT% observado |
| `adapt_pct_primeros10` | número | ADAPT% previsto en los primeros 10 partidos |

### `data/modelos/adaptacion/coeficientes.csv`

**Coeficientes del modelo jerárquico.** Grano: variante × métrica × coeficiente. Clave: `variante, metrica, coeficiente` · 717 filas (en `modelos/adaptacion/coeficientes.csv`).

| Columna | Tipo | Descripción |
|---|---|---|
| `variante` | texto | variante del modelo (`ipcw`, `sin_ipcw`, `sin_rol`; normalización: `sin_mapeo`…) |
| `metrica` | texto | métrica |
| `coeficiente` | texto | nombre del coeficiente |
| `media` | número | tiros de media distancia |
| `sd` | número | desviación típica |
| `lo90` | número | IC 90 % inferior |
| `hi90` | número | IC 90 % superior |
| `p_negativo` | número | P(coef < 0) |

### `data/modelos/adaptacion/curvas.csv`

**Curvas de adaptación por partido.** Grano: serie × población × perfil. Clave: `serie, poblacion, perfil` · 235 filas (en `modelos/adaptacion/curvas.csv`).

| Columna | Tipo | Descripción |
|---|---|---|
| `serie` | texto | serie por partido (`pts_p100`, `prod_p100`…) |
| `poblacion` | texto | `control_permanecen`, `traspasos_bruto`, `traspasos_neto` |
| `perfil` | texto | perfil (global o grupo=valor) |
| `n_jugadores` | entero | jugadores |
| `kappa` | número | κ (partidos) |
| `kappa_lo` | número | κ inferior |
| `kappa_hi` | número | κ superior |
| `kappa_en_borde` | lógico | True si κ toca el borde de la rejilla |
| `D` | número | hueco inicial relativo |
| `D_lo` | número | inferior |
| `D_hi` | número | superior |
| `p_D_negativo` | número | P(D < 0) |
| `hueco_medio_partidos_1_5` | número | hueco medio en los partidos 1-5 |
| `hueco_1_5_lo` | número | inferior |
| `hueco_1_5_hi` | número | superior |
| `partidos_50` | número | partidos hasta cerrar el 50 % del hueco |
| `partidos_50_lo` | número | inferior |
| `partidos_50_hi` | número | superior |
| `partidos_90` | número | partidos hasta el 90 % |
| `partidos_90_lo` | número | inferior |
| `partidos_90_hi` | número | superior |
| `partidos_1a_temporada_mediana` | número | partidos de la 1.ª temporada (mediana) |

### `data/modelos/adaptacion/hipotesis_eeuu.csv`

**Contraste del estadounidense en su primer año europeo.** Grano: variante × métrica × contraste. Clave: `variante, metrica, contraste` · 60 filas (en `modelos/adaptacion/hipotesis_eeuu.csv`).

| Columna | Tipo | Descripción |
|---|---|---|
| `variante` | texto | variante del modelo (`ipcw`, `sin_ipcw`, `sin_rol`; normalización: `sin_mapeo`…) |
| `metrica` | texto | métrica |
| `contraste` | texto | contraste (EEUU_a_Europa − grupo de referencia) |
| `media` | número | tiros de media distancia |
| `lo90` | número | IC 90 % inferior |
| `hi90` | número | IC 90 % superior |
| `p_menor_que_0` | número | P(contraste < 0) |
| `unidad` | texto | `relativa` (fracción) o `aditiva` (unidades de L) |

### `data/modelos/adaptacion/censura.csv`

**Efecto del IPCW sobre Δ.** Grano: métrica. Clave: `metrica` · 8 filas (en `modelos/adaptacion/censura.csv`).

| Columna | Tipo | Descripción |
|---|---|---|
| `metrica` | texto | métrica |
| `delta_ipcw` | número | Δ medio con IPCW |
| `delta_ipcw_lo` | número | IC inferior |
| `delta_ipcw_hi` | número | IC superior |
| `delta_sin_ipcw` | número | Δ medio sin IPCW |
| `delta_sin_ipcw_lo` | número | IC inferior |
| `delta_sin_ipcw_hi` | número | IC superior |
| `efecto_ipcw` | número | con − sin IPCW |
| `media_bruta_observados` | número | media bruta de los observados |
| `media_bruta_todas_llegadas_pesos_minutos` | número | media bruta de todas las llegadas ponderada por minutos |

### `data/modelos/adaptacion/supervivencia.csv`

**Supervivencia (seguir jugando) de las llegadas.** Grano: perfil. Clave: `perfil` · 10 filas (en `modelos/adaptacion/supervivencia.csv`).

| Columna | Tipo | Descripción |
|---|---|---|
| `perfil` | texto | perfil (global o grupo=valor) |
| `llegadas` | entero | llegadas con temporada cerrada |
| `pct_observado` | número | fracción observada (no censurada) |
| `temprano_logr_observados` | número | log-cociente de pts/100 en los 5 primeros partidos (observados) |
| `temprano_logr_censurados` | número | ídem censurados |
| `pct_llega_5_partidos` | número | fracción que llega a 5 partidos |
| `pct_llega_10_partidos` | número | a 10 |
| `pct_llega_20_partidos` | número | a 20 |
| `pct_llega_30_partidos` | número | a 30 |

### `data/modelos/adaptacion/segunda_temporada.csv`

**Segunda temporada en la liga.** Grano: perfil. Clave: `perfil` · 13 filas (en `modelos/adaptacion/segunda_temporada.csv`).

| Columna | Tipo | Descripción |
|---|---|---|
| `perfil` | texto | perfil (global o grupo=valor) |
| `n_llegadas` | entero | llegadas |
| `n_siguen` | entero | siguen en la liga en la 2.ª temporada (≥ 300') |
| `pct_siguen` | número | fracción que sigue |
| `ganancia_L_rel_sin_ipcw` | número | ganancia de L_rel en la 2.ª temporada sin IPCW |
| `ganancia_L_rel_ipcw` | número | con IPCW |
| `lo90` | número | IC 90 % inferior |
| `hi90` | número | IC 90 % superior |
| `ganancia_pts_ipcw` | número | ganancia en pts/100 con IPCW |
| `d1_L_rel_siguen` | número | Δ de 1.ª temporada de los que siguen |
| `d1_L_rel_no_siguen` | número | de los que no siguen |

### `data/modelos/adaptacion/validacion.csv`

**Examen del ADAPT% (temporal y dejar fuera una liga).** Grano: métrica × corte (× liga fuera). Clave: `metrica, corte, examen, liga_fuera` · 160 filas (en `modelos/adaptacion/validacion.csv`).

| Columna | Tipo | Descripción |
|---|---|---|
| `metrica` | texto | métrica |
| `corte` | número | corte temporal t (ajuste con destino ≤ t) |
| `n` | número | número de casos |
| `mae_sin_adaptacion` | número | MAE del log-cociente sin adaptar |
| `mae_adapt` | número | MAE con ADAPT% |
| `sesgo_sin` | número | sesgo sin adaptar |
| `sesgo_adapt` | número | sesgo con ADAPT% |
| `cobertura_80` | número | cobertura del intervalo del 80 % |
| `corr_prev_obs` | número | correlación previsto–observado |
| `mejora_mae_pct` | número | mejora del MAE (%) |
| `n_estricto` | número | casos del examen estricto |
| `mae_estricto_sin` | número | MAE estricto sin |
| `mae_estricto_adapt` | número | MAE estricto con |
| `mejora_estricto_pct` | número | mejora estricta (%) |
| `examen` | texto | `temporal` o `dejar_fuera_liga` |
| `liga_fuera` | texto | liga dejada fuera |

### `data/modelos/adaptacion/validacion_casos.csv.gz`

**Casos del examen.** Grano: corte × métrica × traspaso. Clave: `corte, metrica, id` · 13.536 filas (en `modelos/adaptacion/validacion_casos.csv.gz`).

| Columna | Tipo | Descripción |
|---|---|---|
| `corte` | entero | corte temporal t (ajuste con destino ≤ t) |
| `metrica` | texto | métrica |
| `id` | texto | id del traspaso (persona:liga:temporada de destino) |
| `persona_id` | entero | persona entre ligas (crosswalk + unión por nombre; texto) |
| `liga_origen` | texto | liga de origen |
| `liga_destino` | texto | liga de destino |
| `grupo_nacionalidad` | texto | grupo de nacionalidad (9 grupos) |
| `observado` | número | valor observado en destino |
| `previsto` | número | valor previsto |
| `pi_lo` | número | intervalo predictivo 80 % inferior |
| `pi_hi` | número | superior |
| `pred_lo` | número | intervalo creíble inferior |
| `pred_hi` | número | superior |
| `w_ipcw_test` | número | peso IPCW del caso |
| `logr_estricto` | número | log-cociente con ŷ sin fuga |

### `data/modelos/adaptacion/calibracion.csv`

**Calibración por deciles.** Grano: muestra × métrica × decil. Clave: `muestra, metrica, bin` · 240 filas (en `modelos/adaptacion/calibracion.csv`).

| Columna | Tipo | Descripción |
|---|---|---|
| `muestra` | texto | `en_muestra` o `fuera_muestra` |
| `metrica` | texto | métrica |
| `bin` | entero | decil de la predicción |
| `n` | entero | número de casos |
| `previsto_medio` | número | predicción media |
| `observado_medio` | número | observado medio |
| `observado_lo` | número | IC inferior |
| `observado_hi` | número | IC superior |
| `cobertura_80` | número | cobertura del intervalo del 80 % |

`resumen.json`: traspasos (total, por tipo, observados), tiempos, convergencia de Gibbs.

### Simulador de encaje v2 (`simulador/v2/`, fase 8) — pendiente del informe F8

[[F8: tablas definitivas, columnas y recuentos; ver docs/checkpoints/F8.md]]

Según el diseño (`bbfit/simulador.py`, `bbfit/validacion.py`, `configs/simulation.yaml`): `pesos.json` (utilidad de
Plackett-Luce, calibración de temperatura y rotación, pesos del índice Fit), `historico_<temporada>.csv.gz`
(simulación de cada fichaje real: minutos, rol, producción con intervalos del 50 y 90 %, Fit y componentes, avisos) y
`validacion/` (examen temporal sin fuga frente a los dos modelos de referencia: métricas por corte, desgloses, dejar
fuera una liga, intervalos bootstrap). La exportación al navegador va a `data/artifact/simulador/` (no versionado).

## 4. Banderas frecuentes

| Bandera | Dónde | Significado |
|---|---|---|
| `provisional`, `temporada_en_curso`, `en_curso` | estilos, libro de rol, adaptación | temporada 2026-27 sin terminar |
| `rol_probabilistico` | roles | < 5 partidos: sólo vector de rol |
| `fuente = box` | roles | sin jugada a jugada suficiente: minutos de caja, sin cierre ni tramos |
| `muestra_pequena` | entropía | < 20 acciones |
| `categorias_faltantes` | entropía | categorías que la liga no publica (no se cuentan como 0) |
| `sin_L`, `sin_ast` | reemplazo, entropía | sin nivel de compañeros; fuente sin asistencias enlazadas |
| `fiable`, `en_ajuste` | estilos unificados | ≥ 300 min; entró en el ajuste de la mezcla |
| `*_desconocido` | adaptación | covariable ausente (0 en el modelo + bandera) |
| `observado`, `w_ipcw` | adaptación | no censurado; peso de censura |
| `pos3_estimada` | normalizado | posición estimada por modelo (no oficial) |
| `calidad_contexto` | ligas | `completo`, `parcial` (sin rival), `sin_contexto` |
| `valido`, `usado_en_quintetos` | quintetos/validacion | partido con minutos reconstruidos a ≤ 120 s |
| `fuera_de_alcance` | feb_cobertura | temporada FEB fuera del alcance decidido |
