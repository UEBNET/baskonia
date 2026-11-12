# Exportación CSV de capas v5.0 (encargo de la presentación DD)

Fecha: 12-11-2026 · Kerno Analytics · normalización cruzada v5.0.

Copias en CSV de parquets de la v5.0 para leerlos sin `pyarrow`. **No sustituyen a los parquet**, que siguen siendo la
fuente.

**Formato**
- CSV comprimido con gzip, separador coma, decimal punto, UTF-8 y sin índice.
- Decimales con hasta 10 cifras significativas.
- Mismas filas y columnas que el parquet de origen.

**Verificación.** Se relee cada CSV y se compara con su parquet: número de filas, nombres y orden de las columnas, y la
suma de 2 columnas numéricas. Coinciden en los cuatro ficheros.

**Identificador**
- Todas las tablas usan `persona_v5` (`P` + 6 dígitos), la persona de la v5.
- No hay columna `persona_id`. Para pasar a la persona del crosswalk (`persona_id` de
  `data/processed/player_id_crosswalk.csv`) o al `player_id` de cada liga, se usa
  `data/v5/limpios/entidades/personas_v5.csv`, con las columnas `fuente_liga`, `fuente_id` = `player_id`,
  `persona_crosswalk` = `persona_id` y `persona_v5`.
- `contexto_companeros` trae también el `player_id` de su liga.

**Escala de enlace por métrica (F3)**
- Binomial, enlace logit: `t2_pct`, `t3_pct`, `tl_pct`, `tpar`, `oreb_pct`, `dreb_pct`, `ast_pct`, `tov_pct`,
  `blk_pct`. Tasa = expit(η).
- Poisson, enlace log: `stl_p100`, `pf_p40`, `ftr`. Tasa = exp(η).
- Normal, identidad: `pts_p100`, `usg_pct`.
- Las tasas van en fracción por oportunidad, no en %: por ejemplo t2_pct 0,52 y pts_p100 0,12 = 12 puntos por 100
  posesiones.

---

## 1. `data/v5/carrera/niveles_carrera.csv.gz`

**Qué es.** El nivel de carrera (F4, filtro de Kalman) de cada persona en cada liga, temporada y métrica: la capacidad
persistente estimada con su historia hasta esa temporada, sin datos posteriores.

| | |
|---|---|
| Origen | `niveles_carrera.parquet` |
| Filas | 543.013 |
| Commit de origen | e2d2ed4 (12-11-2026; capas F2–F4 regeneradas con las identidades revisadas en la F8) |
| Tamaño | 17,3 MB |
| Nota | El parquet guarda además el índice de pandas (`__index_level_0__`); no es una columna y no se exporta |

| Columna | Tipo | Descripción |
|---|---|---|
| `persona_v5` | texto | **Identificador** de la persona (v5) |
| `liga` | texto | Competición |
| `temporada` | texto | Temporada (p. ej. 2024-25) |
| `rol` | texto | Rol en esa liga y temporada: E exterior, A mixto, I interior, X sin reparto de roles |
| `edad` | real | Edad en la temporada |
| `y` | real | Posición observada esa temporada respecto a la media de su liga, temporada y rol, en la escala de enlace |
| `v` | real | Varianza de muestreo de `y` |
| `mu` | real | Media de la liga, temporada y rol, en la escala de enlace |
| `metrica` | texto | Métrica (las 14 de la v5) |
| `nivel_carrera` | real | **Nivel**: posición persistente estimada respecto a `mu`, en la escala de enlace |
| `var_nivel_carrera` | real | **Varianza del nivel** |

**Nivel e intervalo del 80 % en la escala de la métrica**
- En la escala de enlace: η = `mu` + `nivel_carrera`, con intervalo η ± 1,2816 · √`var_nivel_carrera`.
- En la escala de la métrica: se aplica la inversa del enlace al centro y a los dos extremos.

## 2. `data/v5/carrera/proyeccion_2026_27.csv.gz`

**Qué es.** La proyección de la F4 a 2026-27 de quien jugó alguna de las dos últimas temporadas. Supuesto: misma liga y
rol que en su última temporada (la proyección en contexto con cambio de liga es la de la F6–F7). Son dos objetos
distintos:
- **nivel**: la capacidad persistente;
- **producción esperada**: lo que registrará dado un volumen, más ancha por naturaleza.

| | |
|---|---|
| Origen | `proyeccion_2026_27.parquet` |
| Filas | 152.609 |
| Commit de origen | e2d2ed4 (12-11-2026) |
| Tamaño | 7,7 MB |

| Columna | Tipo | Descripción |
|---|---|---|
| `persona_v5` | texto | **Identificador** de la persona (v5) |
| `metrica` | texto | Métrica |
| `temporada_objetivo` | texto | 2026-27 |
| `liga` | texto | Liga supuesta (la de su última temporada) |
| `rol` | texto | Rol supuesto (el de su última temporada) |
| `ultima_temporada` | texto | Última temporada observada |
| `temporadas_hist` | entero | Temporadas de historia usadas |
| `edad` | real | Edad en 2026-27 |
| `nivel_media` | real | **Nivel proyectado** (media), en la escala de la métrica (tasa) |
| `nivel_q10` | real | **Extremo inferior del intervalo del 80 % del nivel** |
| `nivel_q50` | real | Mediana del nivel |
| `nivel_q90` | real | **Extremo superior del intervalo del 80 % del nivel** |
| `volumen_supuesto` | real | Oportunidades supuestas: las de su última temporada |
| `produccion_media` | real | Producción esperada (media), dado ese volumen |
| `produccion_q10` | real | Extremo inferior del intervalo del 80 % de la producción |
| `produccion_q50` | real | Mediana de la producción |
| `produccion_q90` | real | Extremo superior del intervalo del 80 % de la producción |

## 3. `data/v5/contexto/contexto_companeros.csv.gz`

**Qué es.** El contexto de compañeros (F2) de cada jugador en cada equipo, liga y temporada: la composición de estilos
de sus compañeros, ponderada por minutos y sin contarle a él.

| | |
|---|---|
| Origen | `contexto_companeros.parquet` |
| Filas | 42.188 |
| Commit de origen | e2d2ed4 (12-11-2026) |
| Tamaño | 1,8 MB |

| Columna | Tipo | Descripción |
|---|---|---|
| `liga` | texto | Competición |
| `temporada` | texto | Temporada |
| `team_id` | texto | Equipo (id de su liga) |
| `player_id` | texto | **Identificador** del jugador en su liga |
| `comp_spacing` | real | Cuota de minutos de compañeros de estilo «Spacing» |
| `comp_circulacion` | real | Ídem, «Circulación» |
| `comp_isolation` | real | Ídem, «Isolation» |
| `comp_old_school` | real | Ídem, «Old School» |
| `comp_pistons` | real | Ídem, «Pistons» |
| `comp_pintura` | real | Ídem, «Pintura» |
| `persona_v5` | texto | **Identificador** de la persona (v5) |

No tiene nivel ni intervalo: es una variable de contexto.

## 4. `data/v5/latente/perfiles_latentes.csv.gz`

**Qué es.** El perfil latente (F5, modelo factorial dinámico) de cada persona en cada temporada: E[z | estado filtrado]
= Λᵀ Σ₀⁻¹ (a − κ − g), con la historia hasta esa temporada.

| | |
|---|---|
| Origen | `perfiles_latentes.parquet` |
| Filas | 39.960 |
| Commit de origen | a3e7f15 (10-11-2026; F5 con las identidades de entonces, anterior a la revisión de la F8) |
| Tamaño | 1,4 MB |

**Limitaciones**
- **No guarda intervalos.** Es el único parquet de `data/v5/latente/` con una fila por jugador y temporada, y es la
  media del perfil.
- **Es un perfil de tipo de jugador, no un nivel.** El nivel por métrica está en `niveles_carrera`.

| Columna | Tipo | Descripción |
|---|---|---|
| `persona_v5` | texto | **Identificador** de la persona (v5) |
| `temporada` | texto | Temporada |
| `liga` | texto | Liga principal de esa temporada |
| `rol` | texto | Rol (E, A, I, X) |
| `edad` | real | Edad |
| `z1` | real | Factor 1 (no estable entre submuestras; sin interpretación) |
| `z2` | real | Factor 2: **tiro y anotación** (estable) |
| `z3` | real | Factor 3: **interior–exterior** (estable) |
| `z4` | real | Factor 4 (no estable; sin interpretación) |
| `z5` | real | Factor 5: **creación** (estable) |

Los factores están en la escala del factor, con prior N(0, 1). En la tabla tienen media ≈ 0 y DT de 0,66 a 0,85, más
pequeña que 1 por la contracción. Los tres estables (z2, z3 y z5) son los que usa la proyección en contexto (F6).
