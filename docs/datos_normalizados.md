# Dataset normalizado completo y nacionalidad

```bash
python -m bbmodel nacionalidades        # data/modelos/nacionalidades.csv
python -m bbmodel dataset-normalizado   # data/modelos/normalizado/<temp>.csv y JSON de la Mesa (data/artifact/)
```

## Qué es

El equivalente **EuroLeague 2025-26** de **todos** los jugadores de las 8 competiciones (EuroLeague, EuroCup, Liga
Endesa, NBA, G League, LBA, BBL, LNB) y las 7 temporadas (2020-21 a 2026-27), temporada regular: 19.508 filas
jugador-liga-temporada. Es la misma traducción que muestra el explorador «Jugadores traducidos a la EuroLeague» de la
pestaña «Normalización de ligas», ampliada a todos los jugadores, todas las temporadas y las 25 métricas.

| Temporada | Jugadores | A+B | Sólo A |
|---|---|---|---|
| 2020-21 | 2.632 | 1.861 | 771 |
| 2021-22 | 2.915 | 2.102 | 813 |
| 2022-23 | 2.792 | 2.090 | 702 |
| 2023-24 | 2.873 | 2.154 | 719 |
| 2024-25 | 2.853 | 2.101 | 752 |
| 2025-26 | 2.950 | 2.162 | 788 |
| 2026-27 (provisional) | 1.493 | 4 | 1.489 |

## Columnas (por métrica `<m>`, 25 métricas del estudio)

| Columna | Significado |
|---|---|
| `<m>` | Estimación final: media de A y B en la escala transformada de la métrica; **sólo A** si B no traduce al jugador (menos de 150 minutos, o 2026-27) |
| `<m>_obs` | Valor observado en su liga |
| `<m>_A`, `<m>_B` | Equivalente EuroLeague según cada algoritmo |
| `<m>_lo`, `<m>_hi` | Intervalo del 80 % (combinado igual que la estimación) |
| `<m>_pctel` | Percentil entre los jugadores de EuroLeague de su posición (media de A y B) |
| `fuente_norm` | «A+B» o «A» |

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
