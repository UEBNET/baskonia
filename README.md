# baskonia · `bbstats` — extractor multi-liga de estadísticas de baloncesto

Extrae, guarda en bruto, normaliza y enriquece las estadísticas de **todos los jugadores** de
varias ligas, y las entrega con **las mismas 330 columnas para todas las ligas**, listas para
aplicar tus propios algoritmos.

Ligas configuradas (temporada 2025-26; cualquier otra temporada vale con `--temporada`):

| Código | Liga | Fuente / adaptador | Estado |
|---|---|---|---|
| `euroleague` | Turkish Airlines EuroLeague | Feed oficial v3 (InCrowd): traditional, advanced, misc, scoring + equipos y rivales | Implementado, **sin validar contra la web real** |
| `acb` | Liga Endesa | acb.com: calendario → boxscore HTML de cada partido → agregación | Implementado, **sin validar contra la web real** |
| `nba` | NBA | stats.nba.com: Base, Advanced, Misc, Scoring, Usage, Defense, hustle, tracking, bio | Implementado, **sin validar contra la web real** |
| `gleague` | NBA G League | stats.gleague.nba.com (misma API, LeagueID=20) | Implementado, **sin validar contra la web real** |
| `lba` | LBA Serie A (Italia) | FIBA LiveStats (boxscores JSON), adaptador genérico | **Falta configurar** el origen de los ids de partido |
| `bbl` | easyCredit BBL (Alemania) | FIBA LiveStats (boxscores JSON), adaptador genérico | **Falta configurar** el origen de los ids de partido |
| `lnb` | LNB Betclic ÉLITE (Francia) | Tabla HTML genérica configurable | **Falta configurar** la URL de la tabla |
| `eurocup` | BKT EuroCup (desactivada) | Igual que Euroliga | Ejemplo de ampliación |

> **Importante — validación pendiente.** El código se ha escrito y probado de principio a fin con
> datos sintéticos que imitan el formato de cada fuente (23 tests). El entorno donde se construyó
> no tenía acceso de red a las webs de las ligas, así que **ningún adaptador se ha probado todavía
> contra la web real**. La primera ejecución real dirá, liga a liga, qué funciona; las URLs y los
> parámetros están en `config/sources.json` para poder ajustarlos sin tocar código.

---

## 1. Arquitectura por capas

```
                ┌─────────────────────────────────────────────────────────────┐
  EJECUTAR ───► │ 1. EXTRACTORES (bbstats/adapters/*)  un adaptador por fuente │
                │    fetch(): descarga SIN transformar                         │
                └──────────────┬──────────────────────────────────────────────┘
                               ▼
                ┌─────────────────────────────────────────────────────────────┐
                │ 2. ALMACÉN BRUTO (bbstats/raw_store.py)                      │
                │    data/raw/<liga>/<temporada>/<liga>_<temporada>_<fecha>.json│
                │    {meta: peticiones, errores, fecha...,  payload: original} │
                │    nunca se sobrescribe; se puede reprocesar sin red         │
                └──────────────┬──────────────────────────────────────────────┘
                               ▼
                ┌─────────────────────────────────────────────────────────────┐
                │ 3. NORMALIZACIÓN (parse() + bbstats/normalize.py)            │
                │    alias de campos de cada fuente → columnas canónicas       │
                │    boxscores → totales de jugador, equipo y RIVAL            │
                └──────────────┬──────────────────────────────────────────────┘
                               ▼
                ┌─────────────────────────────────────────────────────────────┐
                │ 4. MOTOR DE MÉTRICAS (bbstats/metrics.py)                    │
                │    mismas fórmulas para todas las ligas: /partido, /36, /40, │
                │    /100 pos., TS%, USG%, AST%, REB%, PER, ORtg/DRtg, WS, PIE…│
                └──────────────┬──────────────────────────────────────────────┘
                               ▼
                ┌─────────────────────────────────────────────────────────────┐
                │ 5. SALIDA UNIFICADA (bbstats/pipeline.py)                    │
                │    data/processed/<temporada>/ — mismo esquema en cada liga  │
                └─────────────────────────────────────────────────────────────┘
```

Cada capa es independiente: si cambias una fórmula, `reprocesar` regenera toda la salida desde
los JSON brutos sin volver a descargar nada.

## 2. Instalación

```bash
pip install -r requirements.txt          # requests, pandas, numpy, beautifulsoup4, lxml
pip install -r requirements-dev.txt      # + pytest, para los tests
```

## 3. Ejecutar (la actualización sólo ocurre cuando tú lo pides)

No hay ninguna tarea programada: los datos se actualizan **sólo** al llamar a `ejecutar`.

```bash
python ejecutar.py                              # todas las ligas activas
python ejecutar.py acb euroleague               # sólo algunas
python ejecutar.py --temporada 2024-25          # otra temporada

python -m bbstats ejecutar --ligas nba gleague  # equivalente con la CLI
python -m bbstats reprocesar                    # recalcula desde el último bruto, sin red
python -m bbstats estado                        # ligas, últimos brutos, último informe
```

Desde Python (para tus algoritmos):

```python
from bbstats import ejecutar, reprocesar, estado
from bbstats.api import dataframe

informe = ejecutar(ligas=["acb", "euroleague"])   # dict JSON-serializable
df = dataframe()                                   # todas las ligas, 330 columnas
acb = dataframe("acb")
```

Comportamiento de `ejecutar`:

* Las ligas se procesan en paralelo; **una liga caída no detiene a las demás**.
* Si la descarga de una liga falla, se reprocesa su **último JSON bruto** y el informe lo marca
  como `ok_bruto_anterior`.
* En ligas basadas en boxscores (ACB, FIBA LiveStats) los partidos **ya finalizados** se copian del
  bruto anterior en vez de volver a pedirse (más rápido y más respetuoso con las webs). El nuevo
  JSON bruto sigue siendo completo y autónomo.
* Pausa de cortesía entre peticiones al mismo dominio (`http.delay_s`, 1 s por defecto) y
  reintentos con espera creciente.

## 4. Salidas

En `data/processed/<temporada>/`:

| Fichero | Contenido |
|---|---|
| `todas_las_ligas.csv` / `.json` | Todas las ligas juntas, una fila por jugador-equipo |
| `ligas/<liga>.csv` / `.json` | Una liga |
| `diccionario_columnas.csv` / `.json` | Nombre, grupo, origen (fuente/calculado/contexto) y descripción de cada columna |
| `completitud.csv` | % de filas con dato en cada columna, por liga |
| `informe_ejecucion.json` | Estado de cada liga, nº de jugadores, bruto usado, errores, columnas vacías |
| `informes/informe_<fecha>.json` | Histórico de informes |

`todas_las_ligas` se reconstruye con el último procesado de **cada** liga, así que si hoy falla una
liga no desaparece de la salida combinada.

### Esquema (330 columnas, idénticas en todas las ligas)

| Grupo | Ejemplos |
|---|---|
| identidad | liga, temporada, fuente, fecha_extraccion, archivo_bruto, player_uid, nombre, equipo, posición, altura_cm, edad, calidad_contexto |
| totales | gp, gs, min, pts, fgm/fga, fg2m/fg2a, fg3m/fg3a, ftm/fta, oreb, dreb, reb, ast, stl, tov, blk, blka, pf, pfd, plus_minus, pir, mates, puntos en pintura/contraataque/2ª oportunidad/tras pérdida, dobles-dobles… |
| por_partido / por_36 / por_40 / por_100_pos | todas las estadísticas anteriores en cada escala |
| tiro | fg%, 2P%, 3P%, FT%, eFG%, TS%, puntos por tiro, 3PAr, FTr, reparto de puntos 2/3/TL/pintura |
| ratios | min%, USG%, AST%, TOV%, OREB%, DREB%, REB%, STL%, BLK%, AST/TO, AST ratio, cuotas sobre el equipo, posesiones usadas |
| ratings | Game Score, EFF, PIR, PIE, uPER, PER, ORtg, DRtg, Net, Floor%, Stops, Stop%, OWS, DWS, WS, WS/40, WS/48 |
| contexto | totales del equipo y de sus rivales, posesiones, ritmo, ORtg/DRtg de equipo y de liga |
| metricas_fuente (`src_*`) | métricas oficiales publicadas por la fuente: ORtg/DRtg/PIE/USG oficiales, hustle y tracking NBA… |

Convenciones:

* **Ninguna columna se elimina nunca.** Si una liga no publica un dato ni se puede calcular, la
  celda queda en blanco. Ningún jugador se descarta (los de 0 minutos salen con las tasas en blanco).
* Todos los porcentajes en escala **0-100** (también los `src_*`, que se reescalan si la fuente
  los da en 0-1).
* Las métricas avanzadas se **calculan** igual para todas las ligas (fórmulas de
  Basketball-Reference / Dean Oliver / Hollinger, ajustadas a 40' FIBA o 48' NBA). Así toda liga
  tiene estadística avanzada aunque su web no la publique, y además se conservan aparte (`src_*`)
  las cifras oficiales cuando existen, para que puedas compararlas.
* `calidad_contexto`: `completo` (hay totales de equipo **y** de rivales → todas las métricas),
  `parcial` (sólo equipo, reconstruido sumando jugadores → sin las que necesitan al rival),
  `sin_contexto`.
* NBA/G League: un jugador traspasado aparece en una fila (equipo = el último), como lo publica la
  fuente. En ligas por boxscore aparece una fila por equipo.

## 5. Configurar LBA, BBL y LNB

Están implementadas con adaptadores **genéricos** y sólo falta indicarles de dónde leer.

**FIBA LiveStats (`lba`, `bbl`)** — en `config/sources.json`, dentro de `temporadas."2025-26"`:

```json
"match_ids": ["2512345", "2512346"],
"discovery": [
  {"url": "https://<web-de-la-liga>/calendario?jornada={page}",
   "pages": {"from": 1, "to": 34},
   "regex": "fibalivestats\\.dcd\\.shared\\.geniussports\\.com/u/[A-Za-z0-9]+/(\\d+)"}
]
```

Se puede usar una lista fija de ids, páginas de calendario de las que extraer los ids con una
expresión regular, o ambas. Cada partido se descarga de
`https://fibalivestats.dcd.shared.geniussports.com/data/<id>/data.json`.
Si una liga no usa FIBA LiveStats, cámbiala a `html_table` o crea un adaptador propio.

**Tabla HTML (`lnb` o cualquier liga)**:

```json
"adaptador": "html_table",
"promedios": true,
"column_map": {"Joueur": "nombre", "Équipe": "equipo", "MJ": "gp"},
"temporadas": {"2025-26": {
  "players_urls": ["https://.../stats/joueurs?page={page}"], "pages": {"from": 1, "to": 6},
  "teams_url": "https://.../stats/equipes", "opp_teams_url": "https://.../stats/adversaires"
}}
```

Las cabeceras más habituales (PTS, FGM, 3PA, REB, AST, MIN…) se reconocen solas; `column_map`
sólo hace falta para las que no.

## 6. Ampliar

* **Otra temporada**: `--temporada 2024-25`. Euroliga, NBA, G League y ACB derivan sus parámetros
  del año (E2024, 2024-25, temporada_id 2024); se pueden fijar a mano en `temporadas`.
* **Otra liga con una fuente ya soportada**: añade una entrada en `config/sources.json` (ver
  `eurocup`).
* **Otra fuente**: crea `bbstats/adapters/<fuente>.py` heredando de `BaseAdapter`
  (`fetch()` descarga el original, `parse()` devuelve filas con columnas canónicas; la tabla de
  alias de `normalize.py` hace casi todo el mapeo) y regístrala en `bbstats/adapters/__init__.py`.

## 7. Integración con un botón "EJECUTAR" (Artifact / web)

Una página web (incluido un Artifact) se ejecuta en el navegador: no puede correr Python ni leer
directamente las webs de las ligas (CORS). El botón tiene que llamar a un sitio donde corra este
código. Hay dos opciones preparadas:

1. **API HTTP incluida** (`python -m bbstats servidor --puerto 8765`), sólo librería estándar:

   | Método | Ruta | Uso |
   |---|---|---|
   | POST | `/api/ejecutar` `{"ligas": [...], "temporada": "2025-26"}` | lanza la actualización, devuelve `job_id` |
   | GET | `/api/trabajo/<job_id>` | progreso y, al terminar, el informe |
   | POST | `/api/reprocesar` | recalcula sin descargar |
   | GET | `/api/estado` · `/api/datos?liga=acb` · `/api/diccionario` | lectura |

   Con la variable de entorno `BBSTATS_TOKEN` exige `Authorization: Bearer <token>`. Sólo admite
   una ejecución a la vez.

2. **GitHub Actions** (`.github/workflows/ejecutar.yml`): botón *Run workflow* en la pestaña
   Actions del repositorio; deja los CSV/JSON como artefacto descargable. Ojo: stats.nba.com suele
   bloquear las IPs de proveedores cloud, así que NBA/G League pueden fallar ahí.

## 8. Tests

```bash
python -m pytest -q
```

Los tests generan una liga sintética (datos inventados) y la sirven en el formato de cada fuente
(JSON Euroliga, resultSets NBA, data.json FIBA, HTML ACB, tabla HTML). Comprueban, entre otras cosas:
mismo esquema en todas las ligas, **mismas métricas** desde fuentes distintas para los mismos
partidos, PER medio ponderado = 15, USG% medio = 20, guardado del bruto, reproceso sin red,
respaldo con el bruto anterior y reutilización de partidos finalizados.
