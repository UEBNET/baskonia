# Ligas añadidas el 31-10-2026: CBA, BNXT, NCAA D-I (top-50), NBL y VTB

Encargo: ampliar la base de jugadores con cinco competiciones, de 2020-21 a 2026-27 (corte **29-10-2026**), extraídas
**del jugada a jugada** siempre que exista (boxscore sólo como último recurso), y llevarlas a la normalización v3.1, al
simulador (cruzado: las 20 ligas como origen y destino) y a todo el artifact CERNO Analytics.

Las cinco usan el mismo patrón: el adaptador **traduce cada partido al formato del data.json de FIBA LiveStats**
(`to_fls`) y reutiliza íntegro el adaptador y el jugada a jugada de la BSL/GBL (`bbstats/adapters/fiba_livestats.py`,
`bbstats/lineups/sources/fiba_livestats.py`): boxscore, fases, quintetos, tramos, RAPM, tiros y entrenadores salen
del mismo código para todas. El bruto guarda el documento original de la fuente (sólo las claves con datos de juego).

Etiquetas: **DATO** = medido en los ficheros; **DECISIÓN** = elección del usuario o fijada de antemano; **HUECO** = lo
que la fuente no da.

## 1. Fuentes

| Liga | Código | Adaptador | Fuente | Ids |
|---|---|---|---|---|
| National Basketball League (Australia) | `nbl` | `adapters/nbl.py` | API pública de nbl.com.au (`prod.rosetta.nbl.com.au`: calendario por temporada y partido `/live/all`), modelo de datos de Genius Sports. 2023-24 (y 11 partidos de 2024-25) sin jugada a jugada allí: complemento con el data.json de FIBA LiveStats del mismo partido (`temporadas.<t>.fls_ids`, emparejado por fecha y equipo local; jugadores reasignados por apellido) | jugador y equipo = uuid de la NBL (estables entre temporadas) |
| BNXT League (Bélgica + Países Bajos) | `bnxt` | `fiba_livestats` (config) | FIBA LiveStats (`/data/<id>/data.json`); la web de la liga enlaza sus partidos a `/u/BNXT/<id>` | como BSL/GBL: nombre normalizado |
| VTB United League | `vtb` | `adapters/vtb.py` | Infobasket (`org.infobasket.su`, backend de vtb-league.com): `Comp/GetSeasonsForTag`, `Widget/CompIssue`, `Comp/GetCalendar`, `Widget/GetOnline/<id>` | PersonID / TeamID de Infobasket |
| NCAA División I (top-50) | `ncaa` | `adapters/ncaa.py` | ESPN (`site.api.espn.com/.../mens-college-basketball`: calendario por equipo, `summary?event=`, plantilla) | athlete id / team id de ESPN |
| Chinese Basketball Association | `cba` | `adapters/cba.py` | Tencent QQ (`matchweb.sports.qq.com`: calendario, `kbs/matchStat`, `textLive`) + Sina (`cba.sports.sina.com.cn`: rebotes ofensivos/defensivos y entrenador por partido) | playerId / teamId de QQ (estables entre temporadas) |

Fuentes descartadas (no se usan): `bnxt.sportpress.info` (API de la BNXT: exige una clave de cliente sacada del
código de su web) y `data-server.cbaleague.com` (respuestas cifradas con una clave del código de la web): en los dos
casos se evitó extraer secretos del código. `stats.ncaa.org` (403), `data.ncaa.com` (sólo marcadores), la API
interna de ncaa.com (no probada: pendiente de autorización del usuario), RealGM/Proballers (403).

## 2. Alcance y fases

* **NCAA — DECISIÓN:** sólo las **50 mejores universidades** de cada temporada según el **T-Rank final de Torvik**
  (`barttorvik.com/<año>_team_results.csv`, orden por barthag; CSV congelado en `config/sources.json →
  ligas.ncaa.temporadas.<t>.top50`). Se descargan TODOS los partidos de esos 50 (también contra rivales de fuera del
  top-50 o de fuera de D-I) para que los totales de equipo y de rival sean completos, pero sólo se conservan las filas
  de jugador de los top-50. Regular = temporada (incluidos torneos de inicio y de conferencia); playoffs = torneo NCAA
  (First Four incluido); NIT, CBI y Crown fuera. 2026-27: no ha empezado a 29-10 (lista de pretemporada guardada).
  Partido de dos mitades: cada mitad se traduce como dos periodos de 10' (tiempo, clutch y basura exactos).
* **BNXT — DECISIÓN:** desde 2021-22 (primera temporada; 2020-21 = ligas belga y neerlandesa separadas, fuera).
  Regular = fases nacionales + fase transfronteriza (Elite Gold/Silver) o liga única (desde 2024-25); playoffs =
  playoffs BNXT + playoffs nacionales, juntos. Copas y supercopas fuera.
* **NBL:** NBL Cup dentro de la temporada regular; finals (play-in + eliminatorias) = playoffs; exhibiciones fuera.
* **VTB:** regular = fases de liga; playoffs = play-in + eliminatorias + 3.er puesto (como el play-in de la EuroLeague);
  Copa y Supercopa (otra competición) fuera.
* **CBA:** regular = 常规赛; playoffs = 季后赛 (final incluida); All-Star, pretemporada, promoción y Copa fuera.
  Duración: **48' hasta 2024-25 y 40' desde 2025-26** (`temporadas.<t>.minutos_partido`, `bbstats.config.minutos_partido`).

## 3. Cobertura del jugada a jugada [DATO]

| Liga | Con jugada a jugada (cambios → quintetos) | Sólo boxscore (HUECO, último recurso) |
|---|---|---|
| NBL | 2020-21 → 2026-27 (2023-24 con FIBA LiveStats) | — |
| BNXT | 2021-22 → 2026-27 | — |
| VTB | desde el 11-03-2022 | 2020-21 y 2021-22 hasta el 07-03-2022 (Infobasket no tiene jugada a jugada; la liga no publicaba en FIBA LiveStats: comprobado por muestreo de ids) |
| NCAA | 2025-26 (y parte de 2024-25) con cambios; 2020-21 → 2023-24 jugada a jugada SIN cambios (tiros, rebotes, asistencias; no hay quintetos) | — |
| CBA | 2021-22 → 2023-24, oct-dic 2024, 2025-26 → | 2020-21 y ene-may 2025 (QQ sin texto en directo) |

Quintetos validados (minutos y +/- del jugada a jugada frente al boxscore, `quintetos/<liga>/validacion.csv`):
NBL 94-98 % (2023-24: 66 %), BNXT 93 %, VTB 97-100 % desde 2023-24 (2022-23: minutos al segundo pero +/- oficial
desviado 3-5 puntos), NCAA 97 % (2024-26), CBA 94 % (2026-27) y ≈ 50 % hasta 2024-25 (faltan cambios en el texto).

## 4. BNXT: localización de partidos y control

FIBA LiveStats no dice a qué competición pertenece un partido. Se localizaron así: muestreo de 1 de cada 10 ids por
temporada (cabecera del data.json), recorrido denso de cada bloque aceptando sólo partidos entre dos clubes de la liga
(sin filiales «PDL»/«B», femeninos VSE/DSE ni cantera), ventana de playoffs id a id; temporada y fase por la fecha
(cabecera `Last-Modified`). Copas fuera: partidos entre clubes del mismo país dentro de las ventanas de copa que forman
bloques de ids aislados o repiten una pareja más veces de las que da el calendario de liga.

Control contra los recuentos oficiales (Wikipedia + betexplorer; `scratchpad/sondeo/bnxt/CONTROL.md`):

| Temporada | Regular encontrados / oficiales | Playoffs | Copas excluidas |
|---|---|---|---|
| 2021-22 | 297 / 305 | 72 / 72 | 5 |
| 2022-23 | 277 / 280 | 74 / 74 | 6 |
| 2023-24 | 292 / 292 | 45 / 45 | 12 |
| 2024-25 | 341 / 342 | 38 / 38 | 4 |
| 2025-26 | 309 / 306 | 39 / 40 | 3 |
| 2026-27 (al 29-10) | 26 / 32 (+ búsqueda hacia delante del adaptador) | — | — |

## 5. Identidad y nombres

* NBL, VTB, NCAA y CBA tienen ids de persona propios y estables; BNXT, como BSL/GBL, id = nombre normalizado.
* CBA: nombres sólo en chino en la fuente. Chinos → pinyin «Apellido Nombre» (p. ej. Zhou Qi); extranjeros → nombre
  latino de QQ, casi siempre inicial + apellido («S. Cooper»). El crosswalk (`bbmodel/crosswalk.py`) añade una regla:
  **inicial + apellido + misma fecha de nacimiento completa** (sin fecha no se une).
* NCAA: ESPN no da fecha de nacimiento; la edad sólo se conoce si el jugador aparece en otra liga que la publique.

## 6. Normalización (cambios de modelo)

* **Desarrollo universitario — DECISIÓN del usuario:** los puentes NCAA(t) → profesional(t+1) mezclan nivel y
  desarrollo y no hay puentes en sentido contrario. Las unidades con origen en la NCAA usan un tramo de deriva propio
  (`bbmodel/enlace.py`, `TRAMO_NCAA`) estimado SÓLO con NCAA(t) → NCAA(t+1) del mismo jugador (dentro de la liga el
  nivel se cancela) y aplicado a NCAA → profesional; así esos puentes identifican el nivel. **HIPÓTESIS:** el salto
  de desarrollo del último año universitario al primero profesional ≈ el de un curso a otro. Test sintético:
  `tests/test_desarrollo_ncaa.py` (recupera desarrollo y nivel).
* **Escalones de contracción** (fijados de antemano, sin mirar resultados): doméstica alta + VTB y NBL; escalón nuevo
  «doméstica media» = BNXT y CBA; escalón propio «universitaria» = NCAA.
* **Adaptación:** grupo nuevo `NCAA_a_profesional` (va primero; Python y simulador JS).
* **Nivel provisional — DECISIÓN:** las ligas con pocos puentes se muestran con marca de nivel provisional.

## 7. Resultados con las 20 ligas (cadena completa del 01-11-2026) [DATO]

Cadena: `scripts/actualizar_20ligas.sh` (copia aislada, reanudable por pasos) e importación con
`scripts/importar_20ligas.sh`. La v3.1 de 15 ligas (`data/modelos/v3_1_20261029`) se retira (historial de git);
la nueva es `data/modelos/v3_1_20261031` (enlace a `v3_1`).

* **Niveles A (PER, DT de la EuroLeague, temporada de referencia 2025-26), puentes y error típico:** ACB −0,41;
  NCAA −0,61 (484 puentes, ±0,07); NBL −0,67 (183, ±0,09); VTB −0,95 (327, ±0,08); BNXT −1,40 (202, ±0,08);
  CBA −1,51 (88, ±0,12). La CBA tiene puentes gracias a la regla inicial + apellido + fecha de nacimiento.
* **Nivel provisional** (regla fijada de antemano: < 50 puentes o error típico del nivel PER > 0,25 σ): con los datos
  completos ninguna liga lo cumple; la marca queda en la Mesa (ranking y ficha de normalización) para cuando ocurra.
* **Desarrollo NCAA:** la deriva NCAA → NCAA estimada es ≈ 0 (pts/100 +0,01, PER −0,03). [LECTURA] Con métricas
  relativas a la propia liga, quien repite curso apenas progresa frente a la media (y los que más progresan se van):
  el tramo propio evita además que la deriva adulta se aplique a los universitarios.
* **Simulador v3.1 cruzado** (las 20 ligas como origen y destino; examen temporal 2021-22 → 2024-25, 6.028
  fichajes): MAE de minutos 4,87; acierto de rol 0,431; MAE de pts/100 3,91; cobertura del 90 % en pts/100 0,86.
  Por segmentos (cálculo directo sobre `predicciones.csv.gz`): entre las 15 ligas anteriores MAE de minutos 4,82;
  con origen o destino en una liga nueva 5,46 (NCAA y CBA, las más difíciles). Auditorías: 0 fallos.
* **Mapa 3D del Atlas:** agrupado con los 6 estilos unificados (LDA de los 12 rasgos; acierto 0,81); los equipos que
  calcula el navegador usan la aplicación lineal exportada (`estilos_unificados.desde_x`).

## 8. Artifact (límite de 256 MB por versión)

Con 20 ligas los datos no cabían (306 MB). Se publicó sin perder lo que leen las páginas:
`artifact/herramientas/compactar.py` (tablas por columnas a 4 cifras significativas; fuera las columnas `_am` de los
normalizados, copias exactas; normalizados y explorador con ≥ 100 minutos, el filtro por defecto de la Mesa),
`artifact/empaquetar.py` con zopfli (gzip estándar ≈ 4 % menor) y sin la evaluación de ligas de la fase de playoffs
(la de regular y total, completa). Versión publicada: 235 ficheros, ≈ 247 MB. El generador de la evaluación de
equipos de Quintetos (`artifact/herramientas/gen_equipos_quintetos.py`) se reconstruyó (no estaba en el repositorio)
y se comprobó contra la versión publicada.

## 9. Liga U de la ACB (`ligau`, añadida el 09-11-2026)

Competición sub-22 de la ACB (desde 2025-26) para jugadores españoles U22 de los equipos vinculados a los clubes de la
Liga Endesa. Decisiones, cobertura y resultados: `.claude/skills/anadir-liga/decisiones/ligau.md`.

* **Fuente — DECISIÓN del usuario:** la misma plataforma que las FEB. La web oficial (ligau.com) enlaza ids de partido
  FEB; en `baloncestoenvivo.feb.es` la competición es `g=74` (`slug: ligau`). Adaptador `feb` sin cambios de lógica (sólo
  la página de equipo pasa a pedirse por `/equipo/<id>`, porque `Equipo.aspx?i=` redirige a `http://`). Descartado el
  backend propio de ligau.com (exigiría sacar una clave del código de su web).
* **Alcance:** 2025-26 (primera edición) y 2026-27 (en curso, entra en el botón «Actualizar 2026-27»).
* **Fases:** liga regular y 2.ª fase (grupos A y B) = regular; play-out de acceso, eliminatorias, 3.er puesto y final =
  playoffs.
* **Cobertura [DATO]:** 2025-26, 206/206 partidos con jugada a jugada estructurado (cambios y coordenadas), quintetos
  validados en 205; 2026-27, 42/42 partidos jugados al 09-11-2026.
* **Identidad:** id de persona FEB (común a Primera, Segunda y Tercera FEB): la Liga U entra en el conjunto `FEB` del
  crosswalk y es concurrente con la ACB y las FEB (doble licencia). Personas de la Liga U con otra liga: 214 de 347
  (Tercera FEB 183, ACB 57, Segunda FEB 38, BCL 18, Primera FEB 15, FIBA Europe Cup 14, EuroCup 12, EuroLeague 5…).
* **Modelo (DECISIONES fijadas antes de ajustar):** escalón de contracción propio (`ligau: [ligau]`), país ES, grupo
  `feb` de la v4.0 (referencia IMPACTO `resto`), coordenadas de tiro del sistema FEB, 26 partidos de temporada regular
  por equipo en el simulador; en la recalibración de salida del simulador cuenta como origen `resto`.
* **Resultados [DATO]** (cadena completa del 09/10-11-2026): nivel A PER −2,97 ± 0,10 (83 puentes, no provisional),
  entre la Segunda y la Tercera FEB. Cambio en las demás ligas, simulador, estilos (K fijado en 6) y v4.2: ver
  `decisiones/ligau.md` §4. Publicado en los tres artifacts (Jugadores v36, Equipos v12, Metodología v11).
