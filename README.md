# baskonia · `bbstats` — extractor multi-liga de estadísticas de baloncesto

Extrae, guarda en bruto, normaliza y enriquece las estadísticas de **todos los jugadores** de
15 competiciones (las 12 originales más Primera, Segunda y Tercera FEB, §16), separadas por **fase (temporada
regular / playoffs / total)**, con **las mismas columnas para todas las ligas**, listas para aplicar tus propios
algoritmos. Encima de los datos hay tres paquetes de modelos: `bbmodel` (normalización entre ligas, §11 y §17),
`bbestilo` (estilos de juego VaDE, §13) y `bbfit` (encaje v2: roles, reemplazo, entropía, estilos unificados,
adaptación y simulador, §17).

- Temporadas descargadas: **de 2020-21 a 2025-26** (completas, con playoffs) y **2026-27** (hasta el 12-10-2026).
  La temporada por defecto es 2026-27; cualquier otra: `python ejecutar.py --temporada 2024-25`.
- Datos reales en el repositorio: ver [¿Dónde están los datos?](#3-dónde-están-los-datos).
- **Contexto para agentes de IA**: [`CONTEXTO_AGENTE.md`](CONTEXTO_AGENTE.md) explica todo el proceso operativo, el esquema, las fórmulas, las limitaciones y el Artifact asociado.
- **Diccionario de datos** de todas las tablas (claves, granularidad, columnas, unidades, banderas):
  [`docs/data_dictionary.md`](docs/data_dictionary.md). **Glosario** de roles, estilos y medidas en lenguaje de
  dirección deportiva: [`docs/glosario.md`](docs/glosario.md).
- **Artículo técnico** (Parte I estilos; Parte II encaje v2 con notación formal):
  [`docs/articulo/estilos_de_juego_baskonia.pdf`](docs/articulo/estilos_de_juego_baskonia.pdf) y el LaTeX de la
  Parte II [`docs/articulo/fit_v2.tex`](docs/articulo/fit_v2.tex) (§20). Informes de cada fase: `docs/checkpoints/F*.md`.

**Jugadores (filas jugador-equipo) descargados — temporada regular / playoffs:**

| Liga | 2020-21 | 2021-22 | 2022-23 | 2023-24 | 2024-25 | 2025-26 | 2026-27 |
|---|---|---|---|---|---|---|---|
| EuroLeague | 297 / 110 | 293 / 102 | 295 / 101 | 287 / 125 | 295 / 125 | 335 / 124 | 263 / – |
| EuroCup | 342 / 211 | 311 / 169 | 306 / 168 | 307 / 136 | 300 / 130 | 315 / 131 | 367 / – |
| ACB | 365 / 102 | 325 / 104 | 330 / 102 | 318 / 100 | 328 / 102 | 339 / 103 | 237 / – |
| NBA | 626 / 239 | 715 / 217 | 609 / 217 | 657 / 214 | 654 / 219 | 661 / 230 | sin datos |
| G League | 246 / 83 | 493 / 124 | 471 / 123 | 512 / 120 | 510 / 121 | 526 / 160 | sin datos |
| LBA | 244 / 106 | 315 / 99 | 287 / 100 | 289 / 104 | 306 / 103 | 265 / 103 | 210 / – |
| BBL | 307 / 107 | 315 / 100 | 287 / 99 | 299 / 127 | 306 / 124 | 331 / 128 | 237 / – |
| LNB | 313 / 87 | 287 / 93 | 299 / 91 | 305 / 93 | 262 / 113 | 275 / 118 | 179 / – |

Comprobación de coherencia con los datos reales: la suma de Win Shares de temporada regular coincide
con el número de victorias con un margen de ±3 % (p.ej. ACB 2025-26 306 / 306; BBL 2024-25 270 / 272;
G League 2025-26 572 / 558; NBA 2025-26 1.259 / 1.230). Excepción: ACB 2022-23 (279 / 306).

---

## 1. Ligas y fuentes consultadas

Todas las fuentes se han comprobado descargando datos reales (octubre de 2026).

| Código | Competición | Fuente principal | Cómo se obtiene | Fases |
|---|---|---|---|---|
| `euroleague` | Turkish Airlines EuroLeague | Feed oficial de estadísticas de la Euroliga (proveedor InCrowd) | `feeds.incrowdsports.com/provider/euroleague-feeds/v3/competitions/E/statistics/{players,teams}/{traditional,advanced,misc,scoring}` (también `opponentsTraditional`) con `seasonCode=E2025`, `statisticMode=Accumulated`; con `phaseTypeCode=RS` para la temporada regular | regular (RS) · playoffs (= total − RS: play-in + playoffs + Final Four) · total |
| `eurocup` | BKT EuroCup | Mismo feed oficial, competición `U` | igual que Euroliga con `seasonCode=U2025` | regular · playoffs · total |
| `acb` | Liga Endesa (ACB) | API de datos de acb.com (la que usa su web) | `api2.acb.com/api/seasondata/Calendar/season-calendar` (temporadas y jornadas; las jornadas con subfase son playoffs) + `api2.acb.com/api/matchdata/Result/boxscores?matchId=N` (boxscore de cada partido). Clave de cliente pública incluida en el propio código de acb.com | regular · playoffs · total |
| `nba` | NBA | Basketball-Reference (recoge los datos oficiales de la NBA) | `basketball-reference.com/leagues/NBA_2026_{totals,advanced,per_poss,play-by-play,shooting}.html` (tablas de temporada regular y `_post` de playoffs), `leagues/NBA_2026.html` y `playoffs/NBA_2026.html` (equipos y rivales) | regular · playoffs · total |
| `gleague` | NBA G League | API oficial de estadísticas de la G League | `stats.gleague.nba.com/stats/leaguedashplayerstats` (Base, Advanced, Misc, Scoring, Usage, Defense), `leaguedashteamstats` (Base, Opponent, Advanced), `playerindex`; `SeasonType` = Regular Season / Playoffs / Showcase | regular · playoffs · total (incluye la Showcase Cup) |
| `lba` | LBA Serie A (Italia) | API pública de legabasket.it (la que usa su web) | `legabasket.it/api/championships/get-championships` (campeonatos RS y PO por año), `…/get-championships-calendar-by-id?id=C&d=J` (partidos por jornada), `…/get-championships-matches-scores-by-id?id=M` (boxscore) | regular · playoffs · total |
| `bbl` | easyCredit BBL (Alemania) | Páginas públicas de partido de easycredit-bbl.de | JSON embebido (`__NEXT_DATA__`) en `easycredit-bbl.de/spiele/<id>`: datos del partido y boxscore de jugadores. Los ids de cada temporada forman bloques consecutivos que se recorren desde ids semilla | regular (MAIN_ROUND) · playoffs (play-in, cuartos, semis, final) · total |
| `lnb` | LNB Betclic ÉLITE (Francia) | API del "stats centre" de lnb.fr | token anónimo `lnb.fr/api/token` + `api-prod.lnb.fr/competition/getDivisionCompetitionByYear`, `altrstats/getPersonCriterion` y `getTeamsCriterion` (totales por competición), `teams/getRoster` y `person/getPersonSeasonAll` (plantillas y fichas para no omitir a jugadores con pocos partidos) | regular · playoffs (play-in + playoffs) · total |
| `bcl` | Basketball Champions League (FIBA) | Páginas públicas de fiba.basketball (Next.js: los datos van en el HTML) | calendario `fiba.basketball/en/history/112-fiba-mens-european-club-competitions-tier-1/<competition_id>/games` y cada partido `fiba.basketball/en/games/<gameId>` (boxscore `gameDetails`, plantillas, jugada a jugada con cambios y coordenadas de tiro, entrenadores `staffA/B`). No se usa `digital-api.fiba.basketball/hapi` (exige clave de suscripción) | regular (rondas de grupos: Regular Season + Round of 16) · playoffs (Play-ins, cuartos, Final Four) · total; rondas de clasificación fuera |
| `fec` | FIBA Europe Cup | Igual que la BCL (`212-fiba-mens-european-club-competitions-tier-2`) | igual | regular (Regular Season + Second Round) · playoffs (eliminatorias) · total; `Q` (Qualifiers) y `QT` (Qualifying Tournaments) fuera |
| `bsl` | Basketbol Süper Ligi (Turquía) | FIBA LiveStats (Genius Sports) | `fibalivestats.dcd.shared.geniussports.com/data/<id>/data.json` (boxscore + jugada a jugada + tiros en el mismo documento). Ids localizados recorriendo los ids públicos de la fuente y guardados en `config/sources.json` | regular · playoffs (top 8) · total; Copa y Supercopa fuera |
| `gbl` | Greek Basket League (A1) | FIBA LiveStats (Genius Sports); calendario de control en esake.gr | igual que la BSL; comprobado con los resultados de `esake.gr/el/action/EsakeResults` (Α Φάση = regular, Β Φάση = playoffs/play-outs) | regular · playoffs (top 8; play-outs y clasificación fuera) · total; Supercopa fuera |
| `feb1` | Primera FEB (antes LEB Oro) | Web pública de la FEB | calendario `baloncestoenvivo.feb.es/resultados/<slug>/<g>/<año>` (grupos y jornadas por postback ASP.NET), partido `intrafeb.feb.es/LiveStats.API/api/v1/{KeyFacts,BoxScore}/<id>` con el token anónimo que la página pública da a cualquier visitante, plantilla y entrenador `Equipo.aspx` (§16) | regular · playoffs (eliminatorias y fases de ascenso) · total; copas y permanencia fuera |
| `feb2` | Segunda FEB (antes LEB Plata) | Igual | igual (grupos Este/Oeste = atributo del partido) | igual |
| `feb3` | Tercera FEB (antes Liga EBA) | Igual | igual (10-31 grupos por temporada = atributo del partido) | igual |

**Enriquecimiento (fuente no oficial contrastada):**

| Fuente | Ligas | Qué aporta | Endpoints |
|---|---|---|---|
| [BasketNews advanced stats](https://basketnews.com/advanced-stats/on-off/25-euroleague/2026/709-kosner-baskonia-vitoria-gasteiz) | EuroLeague y Liga Endesa (las únicas que cubre) | columnas `bn_*`: ratings individuales (ORtg/DRtg/Net), stops y Stop%, puntos creados y asistidos, USG%/AST%/TOV%/STL%/BLK%, **on/off completo** de cada jugador (ORtg/DRtg/Net con él en pista, en el banquillo y diferencia; % de tiro, rebote, pérdidas y faltas del equipo y del rival con él en pista) | `basketnews.com/advanced-stats/team-profile/players.json` y `on-off.json` (POST `league_id`, `season`, `stage_id`) |

**Fuentes evaluadas y descartadas:**

| Fuente | Motivo |
|---|---|
| stats.nba.com / cdn.nba.com | bloquean conexiones desde servidores/cloud (sin respuesta / 403) → NBA vía Basketball-Reference |
| api.basketball-bundesliga.de (BBL) | exige un secreto ofuscado de su web → se usan las páginas públicas de partido |
| RealGM, Proballers | protegidos con Cloudflare (403) |
| Basketball-Reference internacional | no cubre la BBL; para el resto hay fuentes oficiales mejores |
| FIBA LiveStats para BCL / FIBA Europe Cup | la web de FIBA no da el id de LiveStats de sus partidos; sus páginas traen los mismos datos (boxscore, jugada a jugada, tiros) |
| hosted.dcd.shared.geniussports.com (TBF, HEBA, FIBA) | responde vacío (200 sin contenido) o 404 |
| tbf.org.tr, bsl.org.tr, basketbolsuperligi.com | Cloudflare (403) / conexión cortada / página vacía |
| widgets.baskethotel.com (jugada a jugada de esake.gr) | funciona, pero en texto libre; FIBA LiveStats trae lo mismo estructurado |
| RealGM, eurobasket.com | 403 |

> Las fuentes no oficiales (Basketball-Reference, BasketNews) reproducen los datos oficiales.
> Validación con datos reales: el TS% que calcula este proyecto coincide exactamente con el
> oficial de la Euroliga, y el USG% difiere en décimas del de BasketNews.

---

## 2. Arquitectura por capas

```
 EJECUTAR ─► 1. EXTRACTORES      bbstats/adapters/*  (un adaptador por fuente; fetch() sin transformar)
            2. ALMACÉN BRUTO     data/raw/<liga>/<temporada>/<liga>_<temporada>_<fecha>.json.gz
            3. NORMALIZACIÓN     parse() + normalize.py + boxscore.py  -> totales por FASE
            4. ENRIQUECIMIENTO   enrich/basketnews.py (bn_*)
            5. MÉTRICAS          metrics.py (mismas fórmulas en todas las ligas, por fase)
            6. CONTEXTO DE FASE  rs_* y delta_* en las filas de playoffs
            7. SALIDA UNIFICADA  data/processed/<temporada>/  (mismas columnas en todas las ligas)
```

`reprocesar` regenera toda la salida desde los brutos sin volver a descargar.

## 3. ¿Dónde están los datos?

En este repositorio, rama `claude/basketball-stats-extractor-jpas93`:

| Ruta | Contenido |
|---|---|
| `data/raw/<liga>/<temporada>/<liga>_<temporada>_<YYYYmmddTHHMMSSZ>.json.gz` | **JSON original por liga y descarga**, con fecha, nunca se sobrescribe. Es JSON comprimido con gzip (los boxscores ocupan mucho); se abre con cualquier descompresor o con `RawStore.load()`. Contiene `meta` (fecha, peticiones hechas, errores) y `payload` (respuestas originales de la fuente). |
| `data/processed/<temporada>/ligas/<liga>.csv` | **Datos procesados: un CSV por liga y temporada**, todas sus fases (columna `fase`), 480 columnas, números con 4 decimales. Es la única copia de los datos procesados (sin duplicados combinados ni JSON, para ocupar menos). Todas las ligas juntas: `bbstats.api.dataframe(temporada=...)` |
| `data/processed/<temporada>/indice.json` | Índice: ligas, filas por fase, fecha de extracción, rutas de ficheros |
| `data/processed/<temporada>/diccionario_columnas.csv` | Descripción de cada columna |
| `data/processed/<temporada>/completitud.csv` | % de filas con dato por columna, liga y fase |
| `data/processed/<temporada>/informe_ejecucion.json` | Estado de cada liga en la última ejecución |
| `data/processed/temporadas.json` | Temporadas con datos, ligas y filas por fase |
| `data/artifact/` (**no versionado**) | JSON columnar por temporada y fase para el Artifact; se genera con `python -m bbstats artifact [--temporada T]` |
| `data/processed/<temporada>/quintetos/<liga>/`, `entrenadores/`, `feb/` | Jugada a jugada (tramos, quintetos, parejas, tiros, asistencias, on/off, RAPM), entrenadores por partido y partidos FEB con grupo (§12, §14, §16) |
| `data/processed/player_id_crosswalk.csv` | Correspondencia de jugadores entre ligas (persona, confianza, método) |
| `data/modelos/` | Salidas de los modelos: `algoritmo_A/`, `algoritmo_B/`, `normalizacion_amortiguada/`, `normalizado/`, `pista/`, `contexto/`, `interacciones/`, `estilos/` (VaDE), `roles/`, `reemplazo/`, `entropia/`, `estilos_unificados/`, `adaptacion/`, `simulador/` (fase 8). Todas descritas en [`docs/data_dictionary.md`](docs/data_dictionary.md) |
| `configs/*.yaml` | Umbrales e hiperparámetros de las capas nuevas (§18) |
| `experimentos/` (**no versionado**) | Registro MLflow y cachés reanudables de los modelos (§19) |

## 4. Ejecutar (sólo cuando tú lo pides)

```bash
pip install -r requirements.txt
python ejecutar.py                              # todas las ligas activas, temporada por defecto
python ejecutar.py acb euroleague               # sólo algunas
python ejecutar.py --temporada 2026-27          # otra temporada (sólo esa)
python -m bbstats historico                     # carga histórica: temporada_inicial (2020-21) .. temporada_por_defecto
python -m bbstats historico --desde 2020-21 --hasta 2024-25 --ligas bbl acb
python -m bbstats historico --sin-descarga      # reprocesa todas las temporadas desde los brutos
python -m bbstats reprocesar --temporada 2025-26   # recalcula desde los brutos, sin red
python -m bbstats estado
```

**Modo de trabajo:** la carga histórica (`historico`) se hace una vez y recorre las temporadas de
la más reciente a la más antigua. Después, cada actualización (`ejecutar --temporada X`, el botón
EJECUTAR del Artifact o GitHub Actions) descarga **una sola temporada** y no toca las demás.
`data/processed/temporadas.json` lista las temporadas con datos (lo usa el selector del Artifact).

```python
from bbstats import ejecutar
from bbstats.api import dataframe
ejecutar(ligas=["acb"], temporada="2026-27")
df = dataframe(temporada="2025-26")                      # todas las ligas y fases
playoffs = df[df.fase == "playoffs"]
```

* Ligas en paralelo; una liga caída no detiene al resto. Si una descarga falla, se reprocesa su
  último bruto (`ok_bruto_anterior`). Una temporada que aún no ha empezado queda `sin_datos`.
* Los partidos ya finalizados del bruto anterior se reutilizan (ACB, LBA, BBL).
* Pausa de cortesía por dominio (3,5 s en Basketball-Reference por su límite de 20 peticiones/min).
  Basketball-Reference rechaza la huella TLS de `requests`, así que para ese dominio se usa el
  programa `curl` (incluido en Windows 10+, macOS y Linux).

## 5. Fases y contexto de playoffs

Cada fila tiene `fase` = `regular`, `playoffs` o `total`. En cada fase se recalculan TODAS las
métricas con los totales de esa fase (y el contexto de equipo, rival y liga de esa fase: ritmo,
ORtg de la liga en playoffs, etc.). Además, en las filas de playoffs:

* `rs_<métrica>`: el valor del mismo jugador y equipo en temporada regular.
* `delta_<métrica>`: playoffs − temporada regular.

Métricas con contexto: partidos, minutos, puntos, puntos/rebotes/asistencias por 40, TS%, eFG%,
USG%, AST%, TOV%, REB%, PER, ORtg, DRtg, Net, Game Score, PIR, WS/40, PIE y on/off (BasketNews).

Para el Artifact, `python -m bbstats artifact` genera `data/artifact/<temporada>/<fase>.json` (una fase por
fichero, JSON columnar) a partir de los CSV; el selector de fase carga el de la fase elegida.

## 6. Esquema (480 columnas, idénticas en todas las ligas)

| Grupo | Ejemplos |
|---|---|
| identidad | liga, temporada, fase, fuente, fecha_extraccion, archivo_bruto, player_uid, nombre, equipo, posición, altura, edad, nacionalidad, calidad_contexto |
| totales | gp, gs, min, pts, tiros de 2/3/libres, rebotes, ast, stl, tov, blk, blka, pf, pfd, +/-, PIR, mates, puntos en pintura/contraataque/2ª oportunidad/tras pérdida, dobles-dobles |
| por partido / 36 / 40 / 100 posesiones | todos los conteos en cada escala |
| tiro | FG%, 2P%, 3P%, FT%, eFG%, TS%, 3PAr, FTr, reparto de puntos |
| ratios | USG%, AST%, TOV%, OREB%, DREB%, REB%, STL%, BLK%, AST/TO, cuotas sobre el equipo |
| ratings | Game Score, EFF, PIR, PIE, PER, ORtg, DRtg, Net, Floor%, Stops, Stop%, OWS, DWS, WS, WS/40, WS/48 |
| contexto | totales de equipo y rivales, posesiones, ritmo, ORtg/DRtg de equipo y liga |
| `src_*` | métricas oficiales de la fuente: PER/BPM/VORP/WS de Basketball-Reference, distancias de tiro, on/off y posición NBA, ORtg/DRtg/PIE/USG oficiales de la G League, TS%/eFG% oficiales de la Euroliga… |
| `bn_*` | BasketNews (EuroLeague y ACB): ratings individuales, stops, on/off |
| `rs_*`, `delta_*` | contexto de playoffs frente a temporada regular |

Convenciones: ninguna columna ni jugador se elimina; lo que una liga no publica queda en blanco.
Porcentajes en escala 0-100. `calidad_contexto`: `completo` (hay totales de equipo y rival) o
`parcial` (LNB: la fuente no publica totales de los rivales, sólo puntos encajados).

### Qué falta en cada liga (queda en blanco)

| Liga | No publicado por la fuente |
|---|---|
| NBA | faltas recibidas totales (sólo en tiro y en ataque, en `src_*`) → PIR en blanco |
| G League | partidos de titular. Nota: la G League juega con **tiro libre único** (vale 2 o 3 puntos); el motor lo tiene en cuenta (`tiro_libre_unico` en la configuración) para los puntos producidos, ORtg, Win Shares y PER |
| Euroliga / EuroCup | +/-, mates, puntos por zona; victorias/derrotas de equipo. Los traspasados vienen en una fila (`team_id` = `ASV;ULK`) y usan el contexto del último equipo |
| BBL | tapones recibidos, mates → PIR en blanco |
| LNB | totales de rivales; para jugadores bajo el umbral del ranking (pocos partidos) no hay pérdidas, faltas, tapones recibidos ni +/- |
| LBA, ACB | — (boxscore completo) |
| BasketNews | en playoffs sólo se usa su fase "Playoffs" (no combina play-in ni Final Four) |

## 7. Integración con un botón "EJECUTAR"

Un Artifact se ejecuta en el navegador: no puede correr Python ni leer las webs de las ligas
(CORS). El botón debe llamar a un sitio donde corra este código:

1. **API HTTP incluida**: `python -m bbstats servidor --puerto 8765` → `POST /api/ejecutar`,
   `GET /api/trabajo/<id>`, `GET /api/estado`, `GET /api/datos?liga=acb&temporada=2025-26`,
   `GET /api/diccionario`. Con `BBSTATS_TOKEN` exige `Authorization: Bearer <token>`.
2. **GitHub Actions** (`.github/workflows/ejecutar.yml`): botón *Run workflow*.

## 8. Ampliar

* Otra temporada: `--temporada`, o `historico --desde`. Para empezar el histórico antes, cambia
  `temporada_inicial` en `config/sources.json`.
* BBL: la temporada en curso toma sus partidos de la web. Para una temporada pasada sin
  `semillas`, las busca sola bajando desde los ids de la temporada siguiente, y al encontrarlas
  **las guarda en `config/sources.json`** (`ligas.bbl.temporadas.<t>.semillas`, primer id de cada
  bloque: temporada regular y playoffs). La siguiente ejecución de esa temporada ya no busca, y
  la temporada anterior empieza la búsqueda desde ahí. Se desactiva con `"guardar_descubrimientos": false`.
* Otra liga con fuente ya soportada: nueva entrada en `config/sources.json`.
* Otra fuente: nuevo adaptador en `bbstats/adapters/` (`fetch()` + `parse()` por fase).

## 9. Tests

```bash
pip install -r requirements-dev.txt && python -m pytest -q
```

Una liga sintética (temporada regular + playoffs) se sirve en el formato real de cada fuente
(Euroliga, G League, ACB, LBA, BBL, LNB, Basketball-Reference y BasketNews). Se comprueba que
todas dan las mismas métricas para los mismos partidos en cada fase, el contexto de playoffs,
PER medio = 15, USG% medio = 20, brutos comprimidos, reproceso sin red, respaldo con el bruto
anterior y reutilización de partidos.

## 10. Artifact "Mesa Multiliga Baskonia"

Página interactiva publicada en claude.ai: https://claude.ai/artifact/F4AxayFrM2d1D5JEoNiDoN
(fuente en `artifact/mesa-multiliga.html`; los datos son los `data/artifact/<temporada>/<fase>.json` que genera `python -m bbstats artifact`).

* Selector de temporada y pestañas de fase (Temporada regular / Playoffs / Total), filtros por liga,
  búsqueda, minutos mínimos y vistas de columnas (básico, tiro, por 40/100, avanzada, ratings,
  on/off, playoffs frente a regular, métricas oficiales, contexto de equipo). Ficha del jugador
  con la comparación playoffs/regular. Columna y filtro de **nacionalidad** (`datos/<temporada>/nacionalidades.json`).
* Pestañas: Tabla de datos · **Datos Normalizados** (la misma tabla con los equivalentes EuroLeague de
  `datos/normalizados/<temporada>/regular.json`; vistas de tiro, creación, defensa, ratings, percentil EuroLeague y
  valor en su liga; ficha con intervalo y algoritmos A y B) · Evaluación de ligas · Normalización de ligas ·
  Atlas de Estilos (marco con `atlas/index.html`). La pestaña Comparador se retiró.
* **EJECUTAR** lanza la Routine de Claude Code `EJECUTAR Mesa Multiliga Baskonia`
  (`trig_01VA8u4RqAzGbKy4v4bFn1mw`, sólo bajo demanda) mediante el conector Claude Code Remote:
  descarga las ligas elegidas de **la temporada elegida (sólo esa)**, sube los datos a esta rama
  y republica los datos de esa temporada en el Artifact. La sesión de la Routine adjunta el
  repositorio con permiso de escritura (`add_repo`) antes de subir los datos.

---

## 11. Modelos: `bbmodel` (algoritmos A y B)

Traduce las métricas de cualquier jugador de las 12 ligas a su **equivalente en la EuroLeague** (entorno
2025-26), con intervalo del 80 % y percentil EuroLeague por posición. Separa el entorno de cada liga de su
nivel, usando 4.336 jugadores puente entre ligas. Explicación completa, fórmulas y validación:
[`docs/algoritmo_A.md`](docs/algoritmo_A.md).

```bash
pip install -r requirements.txt
python -m bbmodel ajustar            # ≈ 10-15 min; escribe data/modelos/algoritmo_A/
python -m bbmodel validar            # examen fuera de muestra con cambios de liga reales
python -m bbmodel evaluacion-ligas   # JSON de la pestaña «Evaluación de ligas» (en data/artifact/)
python -m bbmodel ajustar-b          # algoritmo B (red neuronal, 5 redes); escribe data/modelos/algoritmo_B/
python -m bbmodel validar-b          # examen fuera de muestra del B
python -m bbmodel mesa-normalizacion # resumen de la pestaña «Normalización de ligas» (data/artifact/normalizacion/resumen.json)
python -m bbmodel nacionalidades     # nacionalidad de cada jugador (data/modelos/nacionalidades.csv)
python -m bbmodel dataset-normalizado # dataset completo de equivalentes EuroLeague (data/modelos/normalizado/) y sus JSON
```

**Dataset normalizado completo** ([`docs/datos_normalizados.md`](docs/datos_normalizados.md)):
`data/modelos/normalizado/<temporada>.csv` tiene el equivalente EuroLeague 2025-26 de **todos** los jugadores de
las 12 ligas y las 7 temporadas (temporada regular) en las 25 métricas, con el valor en
su liga, A, B, A+B (sólo A donde B no traduce), intervalo del 80 % y percentil EuroLeague, más identidad y
nacionalidad. Alimenta la pestaña **«Datos Normalizados»** de la Mesa y el explorador de «Normalización de ligas».

**Algoritmo B** ([`docs/algoritmo_B.md`](docs/algoritmo_B.md)): red neuronal multitarea que aprende un «ADN» de 8
números por jugador y separa a la vez nivel, liga, temporada, posición y equipo. La estimación recomendada es la
media **A+B**: en el examen fuera de muestra (412 cambios de liga) reduce el error frente a «mismo percentil» una
mediana del 20 % por métrica (A 10,8 %, B 8,1 %) y gana a A en las 25 métricas.

Resultado principal: `data/modelos/algoritmo_A/traducciones/<temporada>.csv` (una fila por jugador-liga-
temporada; columnas `<métrica>_el`, `_el_lo`, `_el_hi`, `_pct_el`, `_el_prox`) y `tipo_de_cambio.csv`.


## 12. Quintetos, parejas y conexiones (jugada a jugada)

Desde la versión 1.3 cada ejecución (`ejecutar`, `historico`, botón EJECUTAR, GitHub Actions) incluye
**siempre** una capa adicional por liga: descarga el jugada a jugada de los partidos terminados que falten,
reconstruye quién está en pista en cada momento y calcula métricas de unidades y conexiones con las mismas
fórmulas en todas las ligas. Sólo esta capa: `python -m bbstats quintetos [--temporadas …] [--ligas …] [--sin-descarga]`.

| Fichero (`data/processed/<temporada>/quintetos/<liga>/`) | Contenido |
|---|---|
| `quintetos.csv.gz`, `trios.csv.gz`, `parejas.csv.gz` (CSV comprimido: `pd.read_csv` los lee tal cual) | Una fila por unidad y fase: minutos (y de ellos en clutch y en la basura), posesiones, puntos a favor/en contra, +/-, ORtg/DRtg/Net, ajustados por muestra (`*_aj`) y por suerte (`*_suerte`), ritmo, cuatro factores a favor y del rival, perfil de tiro, % asistidas, robos/tapones/faltas. Quintetos: suma de RAPM, net esperado y **sinergia**. Tríos y parejas: net esperado y `sinergia_rapm`. Parejas además: con/sin (WOWY) y su **sinergia**, % de los minutos de cada uno que juegan juntos, asistencias entre ambos |
| `jugadores.csv` | On/off completo (on, off y on−off de ratings, suerte y factores), on/off sin minutos de la basura, clutch, **RAPM** (ORAPM/DRAPM), rotación (titularidades, partidos cerrados, relevos, minutos por relevo, reparto por cuartos), red de asistencias (dadas, recibidas, % canastas asistidas, socios, concentración HHI, PageRank) |
| `equipos.csv` | Estructura de cada equipo: ratings (también por suerte y en clutch), quintetos distintos, quinteto principal y titular habitual con su Net, estabilidad (% de minutos de los 5 quintetos más usados), jugadores de rotación, concentración de minutos y de la red de asistencias |
| `asistencias.csv` | Conexiones pasador → anotador: asistencias (de 2, de 3, en tiros libres), puntos generados, minutos juntos, por 40 min, cuotas |
| `tiros.csv.gz` | Cada tiro con coordenadas de la fuente, asistente, los dos quintetos en pista y el marcador previo |
| `tramos.csv.gz` | Tramos (10 jugadores fijos) con marcas de clutch y basura: base para cualquier cálculo nuevo |
| `validacion.csv` | Por partido: diferencias de minutos y +/- frente al boxscore oficial, anomalías y si entra en los quintetos |
| `*_oficial.csv` | NBA y G League: tablas oficiales de quintetos/parejas/on-off para contrastar |

Catálogo de métricas (mismas fórmulas en todas las ligas; descripción de cada columna en el diccionario):

| Familia | Métricas | Para qué |
|---|---|---|
| Eficiencia | ORtg, DRtg, Net, +/- por 40, ritmo | Rendimiento por 100 posesiones de cualquier unidad |
| Muestra | `*_aj` (contracción bayesiana hacia la media de la liga, k = 300 posesiones) | Comparar unidades con pocos minutos sin que dominen los extremos |
| Suerte | `drtg_suerte`, `net_rtg_suerte(_aj)`: % de triples y tiros libres del rival → media de la liga | Separar defensa de acierto ajeno (estilo Cleaning the Glass) |
| Cuatro factores | eFG%, TOV%, OREB%/DREB%, FTr, a favor y del rival; TS%, T2%, T3%, TL%, 3PAr, % asistidas, STL%, BLK% | Por qué funciona (o no) una unidad |
| Contexto | minutos clutch (últimos 5', ±5) y de la basura (4.º cuarto, ≤ 2 titulares, ±25/20/10 según reloj) | Filtrar o ponderar minutos sin valor competitivo |
| On/off | on, off y on−off de todo lo anterior; sin basura | Impacto bruto de un jugador en su equipo |
| RAPM | ORAPM, DRAPM, RAPM (ridge ponderado por posesiones, λ = 1500) | Impacto aislado de compañeros y rivales |
| Sinergia | quintetos: poss/(poss+k)·(Net − Net esperado por RAPM de los 10 en pista); tríos y parejas: `sinergia_rapm` igual; parejas: WOWY Net(A+B) − [Net(A sin B) + Net(B sin A) − Net(ninguno)] | Qué combinaciones rinden más que la suma de sus piezas |
| Conexiones | pasador → anotador, asistencias por 40 juntos, PageRank, HHI, socios, % de minutos juntos | Redes de juego y dependencias |
| Rotación | titularidades, cierres, relevos, minutos por relevo, % de minutos por cuarto; por equipo: quintetos distintos, estabilidad, rotación, HHI de minutos | Uso del entrenador y profundidad |

Cobertura (15-10-2026): partidos con quintetos · % validados (minutos ±90 s y +/- ±3 frente al boxscore
oficial; en la G League, cuyo +/- oficial a menudo no cuadra, sólo minutos en esos partidos). Los partidos
con más de 120 s de desajuste quedan fuera de quintetos y on/off, pero sí cuentan para tiros y asistencias.

| Liga | 2020-21 | 2021-22 | 2022-23 | 2023-24 | 2024-25 | 2025-26 | 2026-27 |
|---|---|---|---|---|---|---|---|
| euroleague | 328 · 91 % | 299 · 94 % | 328 · 94 % | 331 · 96 % | 330 · 95 % | 402 · 95 % | 50 · 96 % |
| eurocup | 185 · 93 % | 189 · 94 % | 195 · 93 % | 195 · 94 % | 196 · 96 % | 195 · 91 % | 47 · 96 % |
| acb | 360 · 99 % | 327 · 99 % | 325 · 99 % | 326 · 100 % | 325 · 100 % | 327 · 100 % | 27 · 100 % |
| nba | 1165 · 98 % | 1317 · 98 % | 1314 · 97 % | 1312 · 98 % | 1314 · 97 % | 1315 · 98 % | — |
| gleague | 142 · 84 % | 671 · 86 % | 763 · 87 % | 789 · 93 % | 789 · 93 % | 791 · 92 % | — |
| lba | 209 · 95 % | 266 · 98 % | 268 · 99 % | 268 · 100 % | 266 · 100 % | 240 · 100 % | 24 · 100 % |
| bbl | 334 · sólo tiros/asist. | 329 · sólo tiros/asist. | 329 · sólo tiros/asist. | 336 · 84 % | 304 · 98 % | 338 · 96 % | 43 · 95 % |
| lnb | 313 · sin jugada a jugada | 328 · 99 % | 325 · 98 % | 329 · 98 % | 266 · 100 % | 266 · 97 % | 24 · 96 % |

- BBL 2020-21 a 2022-23: la fuente no anota los cambios con jugador → sólo tiros, asistencias y red de pases.
- LNB 2020-21: la fuente no publica jugada a jugada (columnas en blanco).
- EuroLeague 2021-22: 299 de 327 partidos; la fuente no marca los otros 28 como jugados (probablemente los afectados por la exclusión de los equipos rusos; sin verificar).
- Ids de jugador y equipo iguales a los de `data/processed/<temporada>/ligas/<liga>.csv` (99–100 % en todas).

Bruto: `data/raw/<liga>/<temporada>/pbp_<liga>_<temporada>_<fecha>.json.gz`, un paquete por ejecución con
sólo los partidos nuevos (nunca se sobrescribe). Fuentes, cobertura y lagunas: `docs/INVESTIGACION_QUINTETOS.md`.
Configuración: `quintetos` en `config/sources.json` (`contraccion_posesiones`, `rapm_lambda`,
`excluir_si_dif_min_s`, `guardar_cada_partidos`) y `pbp` (fuente) en cada liga. Las descargas largas se guardan
en paquetes de 150 partidos: si se cortan, la siguiente ejecución sólo pide lo que falte.

## 13. Estilos de juego: `bbestilo` (VaDE, 6 estilos sin nivel, 17 rasgos con jugada a jugada y mapa 3D)

Asigna a cada **club-competición-temporada** de las 12 ligas uno de **6 estilos de juego** y lo sitúa, junto con
sus jugadores, en un **mapa 3D**. Usa sólo los datos **normalizados A+B** (equivalentes EuroLeague de `bbmodel`),
agregados por minutos, más el ritmo relativo a la liga: 13 rasgos de caja y 4 del jugada a jugada (% de tiros en el aro,
de media distancia y de triples de esquina, % de canastas asistidas). **Neutraliza el nivel**: a cada rasgo se le quita la parte
que explica un índice de calidad, para que el estilo diga cómo juega un equipo y no cuán bueno es.

* **Red: VaDE**, autoencoder variacional con previa de mezcla de 6 gaussianas de covarianza completa en un latente de
  3 neuronas (el mapa); capa de salida de 6 neuronas; consenso de 10 semillas y ajuste fino.
* **Simulación de fichajes y bajas** (uno o varios jugadores a la vez) y **buscador de parecidos** (clubes que juegan
  como el tuyo, jugadores parecidos o que encajan con tu estilo).
* **Química de estilos y contexto de nivel** (`docs/contexto_y_quimica.md`): cómo cambia el juego de un jugador según
  el estilo y el nivel del compañero con el que comparte pista (efectos X → Y del jugada a jugada, matrices estilo ×
  estilo) y proyección de cualquier jugador al contexto de una plantilla de la EuroLeague. Estilos: Creación individual,
  Pintura física, Pausado y seguro, Lejos del aro, Exterior y presión, Circulación y triple.
* Iteraciones anteriores (12 y 8 estilos, IDEC de contraste, 6 estilos con 5 y con 10 semillas sólo con rasgos de caja):
  métricas y asignaciones en `data/modelos/estilos/historial/`; su evolución, en el artículo.

```bash
pip install -r requirements-estilos.txt   # requirements.txt + torch (CPU)
python -m bbestilo barrido          # número de estilos antes de entrenar
python -m bbestilo entrenar         # ≈ 60 min en 4 núcleos; escribe data/modelos/estilos/
python -m bbestilo quimica          # química de estilos (efectos X → Y y sinergia por estilo × estilo)
python -m bbestilo evaluar          # reevalúa la red guardada sin reentrenar
python -m bbestilo analisis         # K óptimo, nivel, éxito, efecto del encaje, continuidad, ligas, Baskonia
python -m bbestilo encaje --jugador "A" "B" --baja "C" --club baskonia --competicion euroleague --temporada 2025-26
python -m bbestilo parecidos --club baskonia --jugador "Nombre" --alcance 30
python -m bbestilo exportar         # datos del Atlas de Estilos (artifact/estilos/)
python -m bbestilo articulo         # artículo científico en PDF (docs/articulo/estilos_de_juego_baskonia.pdf)
```

Escalas de lectura ±100 (Euroliga = 0) del Atlas y de Quintetos: `python -m bbmodel escalas`, explicadas en [`docs/contexto_y_quimica.md`](docs/contexto_y_quimica.md) §7.

Documentación técnica: [`docs/estilos_de_juego.md`](docs/estilos_de_juego.md). Artículo completo:
[`docs/articulo/estilos_de_juego_baskonia.pdf`](docs/articulo/estilos_de_juego_baskonia.pdf).


**Estilo por entrenador** (`python -m bbestilo entrenadores`, y automáticamente al exportar el Atlas): cada tramo
club-temporada-entrenador tiene su propio vector y estilo con la misma red (minutos que repartió ese entrenador y
rasgos de equipo de sus partidos, contraídos hacia la temporada con peso n / (n + 8)); un club puede tener así dos o
tres estilos en una temporada. Detalle en `docs/estilos_de_juego.md` (v5 → final). Modelo actual: 12 ligas, consenso
con suelo de tamaño del 5 %; el de 8 ligas queda en `data/modelos/estilos/historial/v5_6estilos_8ligas/`.

## 14. Entrenadores por partido y tramos de entrenador

`python -m bbstats entrenadores [--temporada T …] [--ligas …] [--sin-descarga]` (módulo `bbstats/entrenadores.py`)
asigna a cada partido y equipo su **entrenador principal** y agrupa los partidos en **tramos
club-temporada-entrenador** (cada destitución o interino es un tramo propio, para darle después su estilo de juego).

| Fichero | Contenido |
|---|---|
| `data/processed/<t>/entrenadores/<liga>_partidos.csv` | Una fila por partido × equipo: `game_id` (el mismo de `quintetos/<liga>/tramos.csv.gz`), `fecha`, `fase`, `equipo_id`/`equipo` (los de `ligas/<liga>.csv` y quintetos), `rival_id`, `local`, puntos y `resultado` (V/D), `entrenador`, `entrenador_id`, `entrenador_id_fuente`, `fuente`, `metodo`, `imputado`, `validacion_vd` (NBA) |
| `data/processed/<t>/entrenadores/<liga>_tramos.csv` | Una fila por club-temporada-entrenador: `orden` (1, 2, 3… por su primer partido), partidos (total, regular, playoffs, otras), `n_imputados`, primer y último partido, V-D (total, regular, playoffs), `n_tramos_consecutivos` (> 1 si vuelve tras un interino), `interino` (heurístico), `entrenadores_equipo`, `partidos_ids` (lista con `;`) |
| `data/processed/entrenadores.csv` | Tabla global: `entrenador_id`, nombre, ligas, temporadas, clubes (`liga:temporada:equipo`), partidos, grafías vistas e ids de fuente |
| `data/processed/entrenadores_cobertura.csv` | Liga × temporada: partidos, % con entrenador, % observado, % imputado, clubes, clubes con más de uno |
| `config/entrenadores_alias.json` | Variantes de escritura → id canónico (p.ej. «IVANOVIC, DUSKO», «Dusko Ivanović»; «Chus Mateo», «MATEO, JESUS») |

**Ids**: `entrenador_id` = slug del nombre (sin acentos, «APELLIDO, NOMBRE» → `nombre-apellido`) pasado por el
alias: es el mismo en todas las ligas y temporadas (Pablo Laso en ACB, EuroLeague y BBL; Tiago Splitter en LNB,
EuroLeague y NBA; Tuomas Iisalo en BBL, LNB, EuroCup y NBA). El id propio de cada fuente queda en `entrenador_id_fuente`.

**Fuentes** (primero lo que ya está en los brutos; si no, una fuente pública guardada como
`data/raw/<liga>/<t>/entrenadores_<liga>_<t>_<fecha>.json.gz`, nunca sobrescrita):

| Liga | Fuente del entrenador | `metodo` |
|---|---|---|
| EuroLeague, EuroCup | Boxscore de live.euroleague.net (`Stats[].Coach`) en el bruto pbp | `partido` |
| ACB | `teamBoxscores[].headCoach` (bruto principal y pbp) | `partido` |
| LBA | `coaches_extra` de matches-scores-by-id (con id y fechas de contrato) | `partido` |
| BBL | quién habla en la rueda de prensa de cada partido (`coachComments[].seasonCoach`) + `headCoachName` (entrenador final de la temporada, no por partido) | `rueda_prensa`, `rueda_prensa_no_principal` (ayudante en ≥ 2 partidos seguidos o entre dos principales = interino) |
| NBA | Basketball-Reference, página de equipo-temporada: «Coach: A (a-b), B (c-d)» en orden → partidos de temporada regular por fecha; se comprueba el V-D de cada bloque (196/196 coinciden); playoffs = último entrenador | `orden_vd`, `temporada_ultimo` |
| G League | stats.gleague.nba.com `commonteamroster` (Coaches, «Head Coach»): un entrenador por equipo-temporada, sin fechas | `temporada` |
| LNB | api-prod.lnb.fr `altrstats/getCoachingStaff` {teamExternalId, year} (HEAD_COACH con fechas desde/hasta) | `temporada`, `temporada_fechas` |

Huecos: un partido sin entrenador entre dos del mismo entrenador recibe ese entrenador (`metodo = tramo`,
`imputado = 1`); al principio o al final de la temporada, el más cercano (`tramo_borde`); entre dos distintos queda vacío.

Cobertura (17-10-2026): % de filas partido-equipo con entrenador (entre paréntesis, observado sin imputar) ·
clubes con más de un entrenador / clubes.

| Liga | 2020-21 | 2021-22 | 2022-23 | 2023-24 | 2024-25 | 2025-26 | 2026-27 |
|---|---|---|---|---|---|---|---|
| acb | 99.9 (99.6) · 5/19 | 99.5 (99.1) · 9/18 | 100.0 (100.0) · 3/18 | 100.0 (100.0) · 5/18 | 99.8 (99.5) · 4/18 | 99.8 (99.8) · 6/18 | 100.0 (100.0) · 0/18 |
| bbl | 98.8 (90.4) · 4/18 | 100.0 (87.5) · 6/18 | 100.0 (90.1) · 4/18 | 100.0 (66.4) · 2/18 | 100.0 (98.2) · 6/17 | 100.0 (97.9) · 6/18 | 100.0 (100.0) · 0/18 |
| eurocup | 100.0 (100.0) · 11/24 | 100.0 (100.0) · 10/20 | 100.0 (99.5) · 5/20 | 100.0 (100.0) · 8/20 | 100.0 (100.0) · 5/20 | 100.0 (100.0) · 2/20 | 100.0 (100.0) · 0/32 |
| euroleague | 100.0 (100.0) · 10/18 | 100.0 (99.8) · 8/18 | 100.0 (100.0) · 6/18 | 100.0 (100.0) · 7/18 | 100.0 (100.0) · 6/18 | 100.0 (100.0) · 10/20 | 100.0 (100.0) · 0/20 |
| gleague | 94.4 · 0/18 | 96.1 · 0/30 | 73.0 · 0/30 | 83.7 · 0/31 | 58.0 · 0/31 | 47.9 · 0/31 | — |
| lba | 100.0 · 5/15 | 100.0 · 6/16 | 100.0 · 4/16 | 100.0 · 5/16 | 100.0 · 7/16 | 100.0 · 7/15 | 100.0 · 0/16 |
| lnb | 100.0 (100.0) · 3/18 | 99.4 (99.4) · 3/18 | 99.8 (99.8) · 2/18 | 99.2 (95.6) · 4/18 | 99.8 (99.8) · 2/16 | 99.8 (99.8) · 1/16 | 100.0 (100.0) · 0/16 |
| nba | 100.0 · 2/30 | 100.0 · 1/30 | 100.0 · 2/30 | 100.0 · 3/30 | 100.0 · 4/30 | 100.0 · 2/30 | — |

Lagunas: G League sólo un entrenador por equipo-temporada y sin él para los equipos cuya ficha no lo trae (no
detecta cambios a mitad de temporada); NBA y LNB son listas de temporada repartidas por orden o por fechas, no el
banquillo de cada partido (una baja puntual de un partido no aparece); en EuroLeague/EuroCup/ACB/LBA sí aparecen
los sustitutos de un partido (enfermedad, sanción). Unir con quintetos:

```python
q = pd.read_csv("data/processed/2025-26/quintetos/acb/tramos.csv.gz", dtype={"game_id": str, "team_a": str})
e = pd.read_csv("data/processed/2025-26/entrenadores/acb_partidos.csv", dtype=str)
q = q.merge(e[["game_id", "equipo_id", "entrenador_id"]], left_on=["game_id", "team_a"],
            right_on=["game_id", "equipo_id"], how="left")      # (y lo mismo con team_b para el rival)
```

Ligas nuevas: registrar un lector en `bbstats.entrenadores.EXTRACTORES` (`registrar(liga_o_fuente_pbp, Extractor(...))`);
para FIBA LiveStats hay `extractor_fiba_livestats(doc)` (data.json: `tm["1"]["coach"]`, `coachDetails`) y el lector
genérico `lector_fiba_livestats`, registrado con la clave `fiba_livestats`.

## 15. Ligas nuevas: Basketball Champions League, FIBA Europe Cup, Basketbol Süper Ligi y Greek Basket League

Cuatro competiciones más (oct. 2026), con el mismo esquema de 480 columnas, las mismas fases y la capa de
quintetos completa (quintetos, parejas, on/off, RAPM, red de asistencias, zonas de tiro):

| Código | Nombre (`liga_nombre`) | Adaptador · fuente jugada a jugada | De dónde salen los ids de partido |
|---|---|---|---|
| `bcl` | Basketball Champions League | `fiba_web` · `fiba_web` | calendario de la competición en fiba.basketball (`competition_id` por temporada en config; si falta, se descubre en `/en/events/basketball-champions-league-YY-YY/games` y se guarda) |
| `fec` | FIBA Europe Cup | `fiba_web` · `fiba_web` | igual (`/en/events/fiba-europe-cup-YY-YY/games`) |
| `bsl` | Basketbol Süper Ligi | `fiba_livestats` · `fiba_livestats` | `config/sources.json` → `ligas.bsl.temporadas.<t>.partidos` (rangos de ids de FIBA LiveStats por fase) |
| `gbl` | Greek Basket League (A1) | `fiba_livestats` · `fiba_livestats` | igual (`ligas.gbl.temporadas.<t>.partidos`) |

**Fuentes consultadas por liga**

- **BCL y FIBA Europe Cup** — páginas públicas de `www.fiba.basketball` (y `www.championsleague.basketball`, a la
  que redirigen los partidos de la BCL). Son páginas Next.js que llevan los datos en el HTML (`self.__next_f.push`):
  el calendario (`/en/history/<ruta>/<competition_id>/games`: todos los partidos con ronda, tipo de ronda y estado) y
  cada partido (`/en/games/<gameId>`): boxscore oficial (`gameDetails`: minutos, +/-, titulares, totales de equipo con
  puntos en la pintura, de segunda oportunidad, de contraataque y tras pérdida), plantillas, jugada a jugada con
  cambios, coordenadas de tiro y entrenadores. Ids: equipo = `organisationId` de FIBA (estable entre temporadas),
  jugador = `personId` de FIBA (el mismo en BCL y FEC). La API `digital-api.fiba.basketball/hapi` exige una clave
  de suscripción: no se usa. Las páginas de los partidos de BCL/FEC no dan el id de FIBA LiveStats.
- **BSL y GBL** — FIBA LiveStats (Genius Sports): `fibalivestats.dcd.shared.geniussports.com/data/<id>/data.json`,
  un documento por partido con boxscore (`tm[k].pl`), totales, entrenadores, jugada a jugada (`pbp`) y tiros
  (`tm[k].shot`, x/y en % de la pista completa). El data.json no dice a qué competición pertenece ni la fecha, y las
  webs de las ligas no publican los ids: `hosted.dcd.shared.geniussports.com` (códigos TBF, HEBA) responde vacío,
  `tbf.org.tr` está tras Cloudflare (403), `bsl.org.tr` corta la conexión y `basketbolsuperligi.com` es una página
  vacía; esake.gr sólo enlaza los widgets de baskethotel (jugada a jugada en texto). Por eso los ids se localizaron
  **recorriendo los ids públicos** de FIBA LiveStats (cabeceras de 450 bytes con el nombre del equipo local) y uniendo
  los equipos por **plantilla** (dos equipos son el mismo si comparten ≥ 4 jugadores; los clubes turcos tienen equipos
  femeninos, filiales y de cantera con el mismo nombre en la misma cuenta). Los resultados se contrastaron con
  esake.gr (`EsakeResults?idchampionship=…&idseason=…&mode=2`: Α Φάση = temporada regular, Β Φάση = playoffs,
  play-outs y clasificación). Lo localizado está en config (`partidos`, `excluir`, `equipos`); la temporada en curso
  (`en_curso`) busca en cada ejecución, en paralelo, los ids nuevos tras el último conocido (`avance_busqueda`).
  Ids: jugador = `apellido-nombre` normalizado (sin personId en LiveStats), equipo = nombre local normalizado más
  usado (las variantes que cada club teclea para el rival se unen por plantilla) — ambos son por temporada.

**Fases**: BCL/FEC — rondas de grupo (Regular Season, Round of 16 / Second Round) = `regular`; Play-ins, cuartos,
Final Four / finales y 3.er puesto = `playoffs`; rondas de clasificación (`Q`, `QT`) fuera (`rondas_excluidas`).
BSL/GBL — liga regular = `regular`; partidos posteriores entre equipos del top 8 (`plazas_playoffs`) = `playoffs`;
play-outs, partidos de clasificación, Copa y Supercopa fuera.

**Brutos sin duplicar y < 40 MB**: un mismo documento sirve al boxscore y al jugada a jugada (la capa de quintetos lo
lee del bruto principal, sin paquete `pbp_`). Los brutos de estas ligas son **incrementales**: cada ejecución guarda
sólo los partidos nuevos (`"incremental": true`), troceados en paquetes de `partidos_por_paquete` (400 ≈ 12 MB), y
`RawStore.load_season()` une todos los paquetes de la temporada al reprocesar.

**Cobertura** (17-10-2026). Filas jugador-equipo (regular / playoffs):

| Liga | 2020-21 | 2021-22 | 2022-23 | 2023-24 | 2024-25 | 2025-26 | 2026-27 |
|---|---|---|---|---|---|---|---|
| bcl | 467 / 96 | 465 / 277 | 491 / 275 | 479 / 257 | 482 / 253 | 493 / 287 | 394 / – |
| fec | 260 / 189 | 422 / 316 | 431 / 330 | 503 / 98 | 562 / 105 | 572 / 106 | 590 / – |
| bsl | 295 / 105 | sin datos | sin datos | sin datos | sin datos | 332 / 102 | 246 / – |
| gbl | 229 / 100 | 255 / 86 | 228 / 106 | 232 / 113 | 239 / 98 | 249 / 107 | 190 / – |

Partidos (regular + playoffs) y jugada a jugada (partidos · % con cambios validados contra minutos y +/- oficiales):

| Liga | 2020-21 | 2021-22 | 2022-23 | 2023-24 | 2024-25 | 2025-26 | 2026-27 |
|---|---|---|---|---|---|---|---|
| bcl | 132 + 8 | 135 + 34 | 141 + 34 | 141 + 35 | 144 + 33 | 144 + 32 | 24 + 0 |
| fec | 30 + 16 | 141 + 29 | 141 + 32 | 148 + 14 | 168 + 14 | 168 + 14 | 47 + 0 |
| bsl | 199 + 20 | — | — | — | — | 239 + 22 | 26 + 0 |
| gbl | 131 + 27 | 156 + 14 | 130 + 24 | 132 + 27 | 127 + 19 | 155 + 18 | 19 + 0 |

| Liga | 2020-21 | 2021-22 | 2022-23 | 2023-24 | 2024-25 | 2025-26 | 2026-27 |
|---|---|---|---|---|---|---|---|
| bcl | 152 · 82 % | 172 · 96 % | 179 · 95 % | 179 · 96 % | 177 · 100 % | 176 · 99 % | 24 · 100 % |
| fec | 46 · 100 % | 173 · 95 % | 176 · 96 % | 164 · 98 % | 182 · 99 % | 182 · 100 % | 47 · 100 % |
| bsl | 219 · 100 % | — | — | — | — | 261 · 96 % | 26 · 92 % |
| gbl | 158 · 98 % | 170 · 99 % | 154 · 95 % | 159 · 94 % | 146 · 92 % | 173 · 90 % | 19 · 95 % |

Lagunas: BSL 2021-22 a 2024-25 no están en FIBA LiveStats (muestreo de todos los ids de esas temporadas, 1 de cada 20,
sin partidos de la BSL) y no hay otra fuente accesible: sin datos. BSL 2020-21: faltan partidos de 3 equipos y la Copa
no se puede separar (las fechas de esa temporada en la fuente no son fiables). GBL: 1-5 partidos por temporada con el
data.json cortado a mitad (no se agregan). BCL 2020-21 (burbujas por la COVID): la mitad de los partidos (76 de 152) no anota los cambios → sólo tiros y asistencias, y de los que sí, 82 % validados; FIBA Europe Cup 2020-21: 16 de 46 sin cambios. BCL 2025-26: algún partido de playoffs con el boxscore incompleto en la
fuente (Trapani, excluido de la competición). Calibración de coordenadas (`bbmodel/zonas.py`): 99,6-99,9 % de tiros de
2 y 3 separados por la línea en las cuatro ligas.

---

## 16. Competiciones FEB: Primera FEB, Segunda FEB y Tercera FEB (fase 1, oct. 2026)

Tres competiciones españolas más, en el **mismo esquema y la misma tubería** que las otras 12 (sin tablas
paralelas): `ligas/<liga>.csv` (480 columnas), `quintetos/<liga>/` (quintetos, parejas, on/off, RAPM, asistencias,
tiros) y `entrenadores/<liga>_*.csv`.

| Código | Nombre actual | Nombre histórico (hasta 2023-24) | Código web FEB |
|---|---|---|---|
| `feb1` | Primera FEB | LEB Oro | `g=1` (`primerafeb`) |
| `feb2` | Segunda FEB | LEB Plata | `g=2` (`segundafeb`) |
| `feb3` | Tercera FEB | Liga EBA | `g=3` (`tercerafeb`) |

Alcance (decisión del usuario, 22-10-2026): **Primera FEB 2022-23 → 2026-27; Segunda y Tercera FEB 2023-24 →
2026-27** (`config/sources.json → ligas.feb*.temporada_inicial`; las temporadas anteriores quedan fuera de alcance).
Cada código es **una serie histórica**: `config/competition_aliases.json` da el nombre de cada temporada. En
Tercera FEB los grupos (A-A, A-B… E-B) **no** son ligas distintas: el grupo es un atributo de cada partido
(`grupo_id` y nombre originales en `data/processed/<t>/feb/feb3_partidos.csv` y `feb3_equipos.csv`).

**Fuentes (públicas, anónimas; robots.txt de www.feb.es leído: sólo regula a `Mediapartners-Google`;
baloncestoenvivo.feb.es y competiciones.feb.es no tienen robots.txt):**

- Calendario: `baloncestoenvivo.feb.es/resultados/<slug>/<g>/<año>` (ASP.NET): desplegables de grupo y de jornada,
  recorridos con el mismo «postback» que hace el navegador. Da todos los grupos (liga regular, play-offs, copa…).
- Partido: `intrafeb.feb.es/LiveStats.API/api/v1/KeyFacts/<id>` (jugada a jugada + boxscore del directo) y
  `…/BoxScore/<id>` (boxscore oficial). La API pide un token que **la propia página pública entrega a cualquier
  visitante** (campo oculto `_ctl0_token`, rol de sólo lectura, caduca en 24 h): no es un secreto del JS.
- Equipo: `baloncestoenvivo.feb.es/Equipo.aspx?i=<id>`: plantilla de esa temporada (fecha de nacimiento,
  nacionalidad, formación, altura, puesto) y entrenador principal. Se guarda sólo ese fragmento.
- Cortesía: ≥ 1 s entre peticiones por dominio (`http.delay_por_dominio`), con la pausa **compartida por todos los
  clientes del proceso** (las tres FEB van en paralelo contra el mismo dominio), reintentos con espera exponencial.

**Fases:** «Liga Regular …» (incluidas las segundas fases de liga) = `regular`; play-offs, eliminatorias, fases
finales / de ascenso = `playoffs`; copas (Copa Princesa, Copa LEB Plata) y permanencia/descenso = fuera (no se
descargan; sí cuentan en la cobertura). Reglas en `config/sources.json → ligas.feb*.fases_grupo`.

**Jugada a jugada:** desde 2024-25 estructurado (acciones con ids de jugador y coordenadas de tiro); hasta 2023-24
sólo texto («J. PEREZ: 3Pts Tiro FALLADO, A. LOPEZ: (TotReb. 2)»), que se interpreta emparejando los nombres
con el boxscore oficial (sin coordenadas). Fuente de quintetos `feb` (`bbstats/lineups/sources/feb.py`), lee el
bruto principal. Coordenadas: `bbmodel/zonas.py` (% de la pista completa).

**Brutos**: incrementales (`games`, `equipos`), paquetes de 400 partidos (< 10 MB), `data/raw/feb*/<t>/`.

**Comandos propios:**

```bash
python -m bbstats historico --ligas feb1 feb2 feb3            # descarga (≈ 1 petición/s: horas para Tercera FEB)
python -m bbstats feb                                         # partidos con grupo, cobertura, posesiones, sesgo
python -m bbstats contrato --ligas feb1 feb2 feb3             # contrato de datos sobre los datos reales
python -m bbstats entrenadores --ligas feb1 feb2 feb3 --sin-descarga
python -m bbmodel crosswalk                                   # correspondencia de jugadores entre ligas
```

Salidas: `data/processed/feb_cobertura.csv` (competición × temporada × grupo: partidos, % con jugada a jugada,
% sólo boxscore, % sin datos, % quintetos válidos), `feb_contrato.csv`, `feb_posesiones.csv`,
`feb_sesgo_registro.csv`, `player_id_crosswalk.csv` y `crosswalk_revision.csv`. Resultados, decisiones y riesgos:
[`docs/checkpoints/F1.md`](docs/checkpoints/F1.md).

**Entrenadores:** el partido no trae el entrenador; se toma el de la página del equipo de esa temporada
(`metodo = temporada`, como la G League): no se ven los cambios a mitad de temporada.

---

## 17. Encaje v2: `bbfit` (fases 2-8), en el orden de ejecución

Cada orden lee las salidas de la anterior, registra su ejecución en MLflow (§19) y deja sus resultados en
`data/modelos/<capa>/`. Resultados, decisiones y riesgos de cada fase: `docs/checkpoints/F1.md` … `F8.md`;
formulación completa: Parte II del artículo (§20).

```bash
# 0. Datos (fase 1): FEB + correspondencia de jugadores entre ligas
python -m bbstats historico --ligas feb1 feb2 feb3 [--sin-descarga]
python -m bbstats feb && python -m bbstats contrato --ligas feb1 feb2 feb3
python -m bbstats entrenadores --ligas feb1 feb2 feb3 --sin-descarga
python -m bbmodel crosswalk

# 1. Normalización (fase 2): A, B y capa amortiguada; dataset normalizado, contexto, escalas
python -m bbmodel pista
python -m bbmodel ajustar && python -m bbmodel ajustar-b
python -m bbmodel amortiguar                      # ≈ 6 min; --validar --variante V | --elegir | --diagnostico P
python -m bbmodel dataset-normalizado && python -m bbmodel contexto && python -m bbmodel dataset-normalizado
python -m bbmodel interacciones && python -m bbmodel escalas

# 2. Capas de encaje (fases 3-7)
python -m bbfit roles                             # roles por minutos, GTI, tramos BOCPD  (≈ 10 min; --rehacer)
python -m bbfit reemplazo                         # libro de rol, elasticidad IV, transiciones, entrenadores (≈ 7 min)
python -m bbfit entropia                          # H_estilo, H_rol, volatilidad σ_i, entropía de equipo (≈ 4 min)
python -m bbfit estilos [--reusar-k]              # taxonomía unificada jugador ↔ equipo (≈ 2-8 min)
python -m bbfit adaptacion [--rehacer] [--sin-validacion]   # Δ jerárquico, curva, censura, ADAPT% (5-8 min)

# 3. Simulador de encaje (fase 8)
python -m bbfit simular --jugador «nombre» --club «nombre» [--liga acb] [--temporada 2025-26] [--bajas …]
#    (pesos, examen temporal, histórico y exportación al navegador: ver docs/checkpoints/F8.md)

# 4. Artículo y pruebas
python -m bbestilo articulo                       # = python -m bbfit.articulo; PDF + docs/articulo/fit_v2.tex
python -m pytest -q
```

| Orden | Módulo | Salida (`data/modelos/…`) | Informe |
|---|---|---|---|
| `bbmodel amortiguar` | `bbmodel/amortiguacion.py` | `normalizacion_amortiguada/` (`league_offsets.csv`, traducciones, validación) | F2 |
| `bbfit roles` | `bbfit/roles.py`, `bbfit/cambios.py`, `bbfit/datos.py` | `roles/` (tramos, temporadas, estructura de equipo, partido × jugador) | F3 |
| `bbfit reemplazo` | `bbfit/reemplazo.py` | `reemplazo/` (uso–eficiencia, libro de rol, transiciones, compañeros, entrenadores) | F4 |
| `bbfit entropia` | `bbfit/entropia.py` | `entropia/` (jugadores, equipos) | F5 |
| `bbfit estilos` | `bbfit/estilos_unificados.py` | `estilos_unificados/` (equipos, jugadores, fichas, selección de K, VaDE) | F6 |
| `bbfit adaptacion` | `bbfit/adaptacion.py` | `adaptacion/` (priors, histórico, curvas, censura, validación) | F7 |
| `bbfit simular` y órdenes de la fase 8 | `bbfit/simulador.py`, `sim_insumos.py`, `validacion.py`, `sim_exportar.py` | `simulador/v2/` | F8 |

Interfaz entre capas usada por el simulador: `bbfit.adaptacion.prior(liga_origen, liga_destino, grupo, pos3,
metrica)`, `grupo_nacionalidad(...)`, `curva(g, delta, kappa)`; `bbfit.reemplazo.asignar_minutos(...)` (minutos
endógenos por Plackett-Luce) y `redistribuir(...)` (suma fija de minutos y uso); `bbfit.roles.clasificar(...)`.

## 18. Configuración: `configs/*.yaml`

Todos los umbrales e hiperparámetros de las capas nuevas viven en YAML (el código no fija ninguno); se leen con
`bbfit.config.cargar("<nombre>")`. Cambiar un valor y volver a ejecutar la orden correspondiente basta.

| Fichero | Capa | Qué fija |
|---|---|---|
| `configs/normalization.yaml` | normalización amortiguada (fase 2) | identidad (crosswalk, umbral 0,75), puentes (≥ 150 min, ≥ 3 por arista), escalones de contracción, mapeo de cuantiles, formas de λ(d), IPW, variantes validadas y la elegida (`sin_mapeo`), capas que leen `<m>_am` |
| `configs/roles.yaml` | roles (fase 3) | duración reglamentaria (40'/48'), ventana de cierre, umbrales de rol en minutos, solape 22-25', GTI (pesos, referencia, top-2, umbral, contracciones), Dirichlet α, BOCPD (riesgo 1/20, previas, suelos de ruido, retardo, tramo mínimo, interinos), covariables de cambio |
| `configs/reemplazo.yaml` | reemplazo (fase 4) | mínimos de la elasticidad uso–eficiencia, instrumento (rotación ≥ 25 %), F mínimo individual, bootstrap, libro (retornos ≥ 300', roles clave, club estable por liga), asignación de minutos (simulaciones, temperatura, tope 36', mínimos por posición, contracción del entrenador k = 30) |
| `configs/entropia.yaml` | entropía (fase 5) | categorías de acciones, acierto mínimo de zonas, prior Dirichlet α = 5, muestras, volatilidad (peso de AST, 30 posesiones de referencia, mínimos, grupos de contracción) |
| `configs/styles.yaml` | estilos unificados (fase 6) | temporadas, mínimos de minutos, contracción m/(m+150), los 12 rasgos, regla de selección de K, umbrales «puro»/mezcla, tramos de entrenador, firmas y nombres de los estilos |
| `configs/adaptacion.yaml` | adaptación (fase 7) | definición de traspaso, país de cada liga, grupos de nacionalidad, métricas, modelo jerárquico (previas, Gibbs, pesos por minutos), curva (previas de κ y D, bootstrap, control), censura (IPCW), jerarquía de priors, validación |
| `configs/simulation.yaml` | simulador (fase 8) | iteraciones, intervalos, fuente de la normalización, plantilla, producción y suma fija de uso, utilidad de Plackett-Luce, GO-TO-GUY proyectado, contracción de la adaptación (0,55), índice Fit, avisos, validación y exportación |

## 19. Registro de experimentos (MLflow)

`bbfit.registro.experimento(nombre, run, params, semilla)` registra cada ejecución (parámetros = la sección del YAML,
semilla, métricas de resumen y artefactos como `resumen.json`) en un almacén de ficheros local,
`experimentos/mlruns` (**no versionado**; MLflow 3 necesita `MLFLOW_ALLOW_FILE_STORE=true`, que el módulo fija). Si
MLflow no está instalado, el registro se degrada a `experimentos/registro_local.jsonl` sin fallar.

| Experimento | Lo escribe | Runs |
|---|---|---|
| `normalizacion_amortiguada` | `bbmodel amortiguar` | `ajuste_<variante>`, `validacion_<variante>` |
| `roles` | `bbfit roles` | `reglas_minutos_bocpd` |
| `reemplazo` | `bbfit reemplazo` | `rol_reemplazo_v1` |
| `entropia` | `bbfit entropia` | `entropia_v1` |
| `estilos_unificados` | `bbfit estilos` | `gmm_k<K>_<covarianza>` |
| `adaptacion` | `bbfit adaptacion` | `fase7` |
| `simulador_v2` | examen temporal del simulador (fase 8) | `examen_<fuente>_<escenario>…` |

Consulta: `mlflow ui --backend-store-uri experimentos/mlruns` (o `mlflow.search_runs(experiment_names=[...])`).
Las cachés reanudables también viven en `experimentos/` (`cache_normalizacion/`, `cache_adaptacion/`,
`cache_simulador/`).

## 20. Artículo técnico y documentación

`python -m bbestilo articulo` (o `python -m bbfit.articulo [--fuentes DIR] [--sin-pdf]`) compone el artículo
completo en HTML y lo imprime a PDF con Chromium sin interfaz: **Parte I** (estilos VaDE, contexto de nivel y
química; `bbestilo/articulo.py`, con las cifras leídas de `data/modelos/estilos/`) y **Parte II** (encaje v2:
FEB, normalización amortiguada, roles, reemplazo, entropía, estilos unificados, adaptación y simulador;
`bbfit/articulo.py`, con las cifras de los informes de fase). Las fórmulas se escriben en LaTeX y se componen con
KaTeX incrustado (`bbestilo/recursos/katex/`, sin red); las fuentes tipográficas van en `bbestilo/recursos/fuentes/`.
Salidas: `docs/articulo/estilos_de_juego_baskonia.pdf` (copia en `artifact/articulo/` para el Atlas),
`docs/articulo/fit_v2.tex` (LaTeX autónomo de la Parte II, compila con pdflatex, xelatex o lualatex) y sus
figuras en `docs/articulo/fit_v2_figuras/`. Los resultados de la fase 8 pendientes aparecen como marcadores
`[[F8: …]]`.

Otros documentos: [`docs/data_dictionary.md`](docs/data_dictionary.md) (todas las tablas),
[`docs/glosario.md`](docs/glosario.md) (roles, estilos y medidas en lenguaje de dirección deportiva),
[`docs/normalizacion_amortiguada.md`](docs/normalizacion_amortiguada.md), [`docs/estilos_de_juego.md`](docs/estilos_de_juego.md),
[`docs/contexto_y_quimica.md`](docs/contexto_y_quimica.md), [`docs/AUDIT_2026-10-21.md`](docs/AUDIT_2026-10-21.md)
(línea base del proyecto multifase) y [`CHANGELOG.md`](CHANGELOG.md).
