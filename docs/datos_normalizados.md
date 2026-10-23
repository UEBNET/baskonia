# Dataset normalizado completo y nacionalidad

```bash
python -m bbmodel nacionalidades        # data/modelos/nacionalidades.csv
python -m bbmodel dataset-normalizado   # data/modelos/normalizado/<temp>.csv y JSON de la Mesa (data/artifact/)
```

## Qué es

El equivalente **EuroLeague 2025-26** de **todos** los jugadores de las 15 competiciones (EuroLeague, EuroCup, Liga
Endesa, NBA, G League, LBA, BBL, LNB, BCL, FIBA Europe Cup, BSL, GBL y Primera, Segunda y Tercera FEB) y las 7
temporadas (2020-21 a 2026-27), temporada regular: 39.647 filas jugador-liga-temporada (octubre de 2026). Es la misma
traducción que muestra el explorador «Jugadores traducidos a la EuroLeague» de la pestaña «Normalización de ligas»,
ampliada a todos los jugadores, todas las temporadas y las 33 métricas (25 de caja + 8 de pista).

| Temporada | Jugadores | A+B | Sólo A |
|---|---|---|---|
| 2020-21 | 3.864 | 2.325 | 1.539 |
| 2021-22 | 4.043 | 2.573 | 1.470 |
| 2022-23 | 4.215 | 2.788 | 1.427 |
| 2023-24 | 7.165 | 4.642 | 2.523 |
| 2024-25 | 7.303 | 4.623 | 2.680 |
| 2025-26 | 7.785 | 4.917 | 2.868 |
| 2026-27 (provisional) | 5.272 | 5 | 5.267 |

## Columnas (por métrica `<m>`, 33 métricas del estudio)

| Columna | Significado |
|---|---|
| `<m>` | Estimación final: media de A y B en la escala transformada de la métrica; **sólo A** si B no traduce al jugador (menos de 150 minutos, o 2026-27) |
| `<m>_obs` | Valor observado en su liga |
| `<m>_A`, `<m>_B` | Equivalente EuroLeague según cada algoritmo |
| `<m>_lo`, `<m>_hi` | Intervalo del 80 % (combinado igual que la estimación) |
| `<m>_pctel` | Percentil entre los jugadores de EuroLeague de su posición (media de A y B) |
| `fuente_norm` | «A+B» o «A» |
| `<m>_A_am` | Equivalente EuroLeague del algoritmo A con el salto de nivel **amortiguado** ([`normalizacion_amortiguada.md`](normalizacion_amortiguada.md)) |
| `<m>_am` | Estimación final amortiguada: la A+B de `<m>` más la corrección de la amortiguación del A, en la escala transformada |
| `<m>_am_lo`, `<m>_am_hi` | Intervalo del 80 % amortiguado (incluye la incertidumbre del nivel de su competición-temporada, que crece con el camino de puentes) |
| `<m>_am_pctel` | Percentil EuroLeague amortiguado (media del A amortiguado y del B) |
| `<m>_ctx` | Valor sin contexto de plantilla (métricas con β de contexto claro) |

Identidad: `persona_id` (une a la persona entre ligas), `player_uid`, `player_id`, `team_id`, `liga`, `temporada`,
`nombre`, `equipo`, `posicion` (de la fuente), `pos3` (exterior/alero/interior del estudio), `edad`, `anio_nac`,
`fecha_nacimiento`, `nacionalidad`, `nacionalidad_fuente`, `altura_cm`, `gp`, `min`, `min_pg`.

## Nacionalidad

Sólo tres fuentes la publican en lo que se descarga: **LNB** (todos los jugadores), **G League** (índice de jugadores
de la liga; los que siguen activos) y **BBL** (el máximo anotador de cada partido). La EuroLeague, la EuroCup, la ACB,
la LBA y la NBA no la incluyen. Se propaga:

1. a otras temporadas del mismo jugador en la misma liga (`nacionalidad_fuente` = «misma liga»), y
2. a sus filas en otras ligas, por persona (`persona_id`; «otra liga»).

Los países se escriben en español con un único nombre (p. ej. «USA», «United States of America» y «US» → «Estados
Unidos»); si hay dos nacionalidades, «Estados Unidos / Ghana». Cobertura de las filas: LNB 100 %, G League 97 %,
BBL 53 %, NBA 47 %, EuroLeague 40 %, EuroCup 34 %, ACB 24 %, LBA 21 %.

## En la Mesa

* **Datos Normalizados**: la misma tabla que «Tabla de datos» (temporada, ligas, búsqueda, minutos, posición, edad,
  nacionalidad, vistas, filtros por métrica, mapa de calor, ficha) con los equivalentes EuroLeague.
* **Tabla de datos** y **Datos Normalizados**: columna «Nac.» y filtro de nacionalidad.
* **Normalización de ligas**: el explorador ofrece todas las temporadas y todos los jugadores.
