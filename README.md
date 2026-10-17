# baskonia · `bbstats` — extractor multi-liga de estadísticas de baloncesto

Extrae, guarda en bruto, normaliza y enriquece las estadísticas de **todos los jugadores** de
8 competiciones, separadas por **fase (temporada regular / playoffs / total)**, con **las mismas
columnas para todas las ligas**, listas para aplicar tus propios algoritmos.

- Temporadas descargadas: **de 2020-21 a 2025-26** (completas, con playoffs) y **2026-27** (hasta el 12-10-2026).
  La temporada por defecto es 2026-27; cualquier otra: `python ejecutar.py --temporada 2024-25`.
- Datos reales en el repositorio: ver [¿Dónde están los datos?](#3-dónde-están-los-datos).
- **Contexto para agentes de IA**: [`CONTEXTO_AGENTE.md`](CONTEXTO_AGENTE.md) explica todo el proceso operativo, el esquema, las fórmulas, las limitaciones y el Artifact asociado.

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
| FIBA LiveStats | ninguna de estas ligas publica ahí; el adaptador genérico `fiba_livestats` se mantiene para otras ligas |

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

Traduce las métricas de cualquier jugador de las 8 ligas a su **equivalente en la EuroLeague** (entorno
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
las 8 ligas y las 7 temporadas (19.508 jugador-liga-temporada, temporada regular) en las 25 métricas, con el valor en
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

Asigna a cada **club-competición-temporada** de las 8 ligas uno de **6 estilos de juego** y lo sitúa, junto con
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

