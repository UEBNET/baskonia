# Contexto para agentes: datos de baloncesto multi-liga (`bbstats`) y Mesa Multiliga Baskonia

> Documento de contexto para un agente que diseña **algoritmos y modelos de evaluación de ligas y
> jugadores**. Describe qué datos existen, de dónde salen, cómo se procesan, qué significa cada
> columna, qué limitaciones tienen y cómo actualizarlos. Repositorio: `uebnet/baskonia`, rama
> `claude/basketball-stats-extractor-jpas93`. Última actualización de datos: 13-10-2026 (temporadas 2020-21 a 2026-27).

---

## 1. Resumen en 10 líneas

1. `bbstats` es un paquete Python que extrae estadísticas de **todos los jugadores** de 8 competiciones:
   EuroLeague, EuroCup, Liga Endesa (ACB), NBA, NBA G League, LBA (Italia), BBL (Alemania) y LNB (Francia).
2. Cada liga tiene un **adaptador** que descarga su fuente (oficial siempre que existe) y la guarda **sin tocar**
   como JSON comprimido con fecha (almacén bruto).
3. Los datos se normalizan a **un esquema único de 480 columnas**, idéntico para todas las ligas.
4. Todo se separa en **fases**: `regular`, `playoffs` y `total`. Cada fase tiene sus propios totales y métricas.
5. Un **motor de métricas** recalcula con las **mismas fórmulas** en todas las ligas: por partido/36/40/100 posesiones,
   eficiencia de tiro, ratios (USG%, AST%, REB%…), PER, ORtg/DRtg de Dean Oliver, Win Shares, PIE, Game Score…
6. Se conservan además las métricas **oficiales** de cada fuente (`src_*`) y el **on/off de BasketNews** (`bn_*`).
7. En las filas de playoffs hay columnas **`rs_*`** (valor en temporada regular) y **`delta_*`** (playoffs − regular).
8. Datos reales versionados en `data/`: **de 2020-21 a 2025-26 completas** (regular + playoffs) y **2026-27 en curso**.
   La carga histórica se hace una vez (`python -m bbstats historico`); después se actualiza **una temporada cada vez**.
9. La extracción sólo se ejecuta bajo demanda (`python ejecutar.py`, CLI, API, GitHub Actions o el botón EJECUTAR).
10. Un **Artifact** de claude.ai ("Mesa Multiliga Baskonia") muestra los datos con selector de temporada/fase y botón EJECUTAR.

---

## 2. Mapa del repositorio

```
baskonia/
├── CONTEXTO_AGENTE.md        ← este documento
├── README.md                 ← guía de uso y fuentes consultadas
├── ejecutar.py               ← "botón EJECUTAR" en script: python ejecutar.py [ligas] [--temporada T]
├── requirements.txt          ← requests, pandas, numpy, beautifulsoup4, lxml   (+ requirements-dev.txt: pytest)
├── config/sources.json       ← configuración de ligas, URLs, temporadas, pausas HTTP (editable sin tocar código)
├── bbstats/
│   ├── adapters/             ← 1 adaptador por fuente (fetch() descarga, parse() normaliza por fase)
│   │   ├── base.py           ← contrato BaseAdapter, ParsedLeague, AdapterError, NoDataYet
│   │   ├── euroleague.py     ← EuroLeague y EuroCup (feed oficial v3)
│   │   ├── acb.py            ← Liga Endesa (api2.acb.com)
│   │   ├── bref_nba.py       ← NBA (Basketball-Reference)
│   │   ├── nba.py            ← G League (API oficial stats.gleague.nba.com; también válido para stats.nba.com)
│   │   ├── lba.py            ← LBA (API de legabasket.it)
│   │   ├── bbl.py            ← BBL (JSON embebido en páginas de partido de easycredit-bbl.de)
│   │   ├── lnb.py            ← LNB (API del stats centre de lnb.fr)
│   │   ├── boxscore.py       ← agregación partido a partido → totales jugador/equipo/rival por fase
│   │   ├── fiba_livestats.py, html_table.py ← adaptadores genéricos de reserva (no usados por las 8 ligas)
│   ├── enrich/basketnews.py  ← enriquecimiento bn_* (EuroLeague y ACB)
│   ├── normalize.py          ← tabla de alias campo-de-origen → columna canónica, completado de conteos
│   ├── phases.py             ← suma/resta de fases (total = Σ fases; playoffs = total − regular)
│   ├── metrics.py            ← motor de métricas (fórmulas en §6)
│   ├── schema.py             ← esquema canónico: lista ordenada de las 480 columnas con descripción
│   ├── pipeline.py           ← orquestación: descarga → bruto → parse → métricas → fases → salida
│   ├── raw_store.py          ← almacén bruto (JSON gz con fecha, nunca se sobrescribe)
│   ├── http.py               ← cliente HTTP: reintentos, pausas por dominio, transporte curl
│   ├── api.py                ← API Python: ejecutar(), reprocesar(), estado(), datos(), dataframe(), diccionario()
│   ├── server.py             ← API HTTP mínima (POST /api/ejecutar, GET /api/datos…)
│   └── __main__.py           ← CLI: python -m bbstats {ejecutar|reprocesar|estado|servidor}
├── data/
│   ├── raw/<liga>/<temporada>/<liga>_<temporada>_<YYYYmmddTHHMMSSZ>.json.gz   ← brutos originales
│   └── processed/<temporada>/                                                ← salida unificada (ver §5)
├── artifact/mesa-multiliga.html  ← código de la página del Artifact
├── tests/                    ← 25 tests con una liga sintética servida en el formato real de cada fuente
└── .github/workflows/ejecutar.yml ← ejecución manual en GitHub Actions (workflow_dispatch)
```

---

## 3. Proceso operativo de extracción (paso a paso)

```
EJECUTAR
 └─► por cada liga activa (en paralelo; una liga caída no detiene al resto)
      1. adapter.fetch(temporada, http, bruto_anterior)
           · descarga la fuente; reutiliza del bruto anterior los partidos ya finalizados (ACB, LBA, BBL)
           · si la liga añade enriquecimiento (EuroLeague/ACB) descarga BasketNews y lo guarda en el mismo bruto
      2. RawStore.save()  → data/raw/<liga>/<temporada>/<liga>_<temporada>_<fecha>.json.gz
           · contenido: {"meta": {fecha, adaptador, peticiones HTTP, errores}, "payload": respuestas originales}
           · si la descarga falla se usa el último bruto (estado "ok_bruto_anterior")
           · si la temporada aún no tiene partidos: estado "sin_datos" (no es error)
      3. adapter.parse(payload) → {fase: ParsedLeague(players, teams)}   (sin red)
           · normalización de nombres de campo con normalize.py
           · por boxscores: suma partido a partido, separando fases por el calendario
           · por agregados: fases que da la fuente; total = suma, o playoffs = total − regular
      4. por cada fase: metrics.compute_player_metrics()  (contexto de equipo, rival y liga de ESA fase)
      5. enriquecimiento BasketNews por fase (emparejado por nombre + equipo)
      6. columnas rs_*/delta_* en las filas de playoffs
      7. finalize_columns(): reordena al esquema de 480 columnas (las ausentes quedan vacías)
      8. escribe data/processed/<temporada>/ligas/<liga>.csv
 └─► write_combined(): indice.json, diccionario_columnas.csv, completitud.csv, informe_ejecucion.json
     y data/processed/temporadas.json   (los datos quedan sólo en ligas/<liga>.csv)
 └─► (para el Artifact, aparte) python -m bbstats artifact → data/artifact/<temporada>/<fase>.json
```

Comandos:

```bash
python ejecutar.py                                   # todas las ligas activas, temporada por defecto (2026-27)
python ejecutar.py acb euroleague --temporada 2025-26   # una temporada (sólo esa)
python -m bbstats historico                          # carga histórica: temporada_inicial (2020-21) .. temporada_por_defecto
python -m bbstats historico --desde 2020-21 --hasta 2024-25 --ligas bbl
python -m bbstats historico --sin-descarga           # reprocesa todas las temporadas desde los brutos
python -m bbstats reprocesar --temporada 2025-26     # recalcula una temporada desde los brutos, sin red
python -m bbstats estado
python -m pytest -q                                  # 31 tests
```

**Modo de operación (desde la versión 1.1):**
1. Carga histórica, una sola vez: `historico` recorre las temporadas de `temporada_inicial` a
   `temporada_por_defecto` (config), **de la más reciente a la más antigua**, compartiendo la configuración
   en memoria (lo que una temporada descubre sirve a la anterior).
2. Mantenimiento: cada actualización (`ejecutar --temporada X`, botón EJECUTAR del Artifact o GitHub Actions)
   descarga **una única temporada** y no toca las demás.
3. Tras cada ejecución se reescribe `data/processed/temporadas.json` (temporadas con datos, ligas y filas por
   fase); el Artifact construye con él su selector de temporada.
4. Lo que una fuente descubre sola se guarda en `config/sources.json` (`guardar_descubrimientos: true`):
   `adapter.config_updates` → `config.update_league_config()` (en memoria y en disco, releyendo el fichero).

`reprocesar` es clave para el agente: si se cambia una fórmula en `metrics.py` o se añade una columna en
`schema.py`, se regenera toda la salida histórica sin volver a descargar.

Tiempos aproximados de una ejecución completa: 10-20 min (BBL y ACB son las más lentas: un acceso por partido
con pausa de cortesía; Basketball-Reference exige 3,5 s entre peticiones).

---

## 4. Fuentes por liga (verificadas con datos reales)

| Código | Liga | Fuente | Tipo de dato | Fases |
|---|---|---|---|---|
| `euroleague` | EuroLeague | `feeds.incrowdsports.com/provider/euroleague-feeds/v3/competitions/E/statistics/...` (feed oficial) | agregados de temporada (jugador, equipo, rivales) | `phaseTypeCode=RS` = regular; playoffs = total − RS (play-in + playoffs + Final Four) |
| `eurocup` | EuroCup | mismo feed, competición `U` | idem | idem |
| `acb` | Liga Endesa | `api2.acb.com` (calendario `season-calendar` + `Result/boxscores` por partido) | boxscores partido a partido | jornadas con `subphaseId` = playoffs |
| `nba` | NBA | Basketball-Reference (`leagues/NBA_Y_{totals,advanced,per_poss,play-by-play,shooting}`, `leagues/NBA_Y`, `playoffs/NBA_Y`) | agregados; tablas `*_post` = playoffs | regular y playoffs; total = suma |
| `gleague` | G League | `stats.gleague.nba.com/stats` (leaguedashplayerstats Base/Advanced/Misc/Scoring/Usage/Defense, leaguedashteamstats Base/Opponent/Advanced, playerindex) | agregados | Regular Season, Playoffs, Showcase (copa); total = suma de las tres |
| `lba` | LBA Serie A | `legabasket.it/api/championships/...` (campeonatos RS/PO, calendario por jornada, `matches-scores-by-id`) | boxscores | RS = regular, PO = playoffs |
| `bbl` | easyCredit BBL | `easycredit-bbl.de/spiele/<id>` (JSON `__NEXT_DATA__` de la página pública) | boxscores | `MAIN_ROUND` = regular; play-in, cuartos, semis y final = playoffs |
| `lnb` | LNB Betclic ÉLITE | `api-prod.lnb.fr` (token anónimo de `lnb.fr/api/token`; `altrstats/getPersonCriterion`, `getTeamsCriterion`, `teams/getRoster`, `person/getPersonSeasonAll`) | agregados por competición | Betclic ÉLITE = regular; Play-In + Playoffs = playoffs |
| (enriquecimiento) | EuroLeague, ACB | BasketNews `basketnews.com/advanced-stats/team-profile/{players,on-off}.json` | ratings individuales, stops, on/off | total, regular y fase "Playoffs" |

Detalles operativos relevantes:
- ACB usa la clave de cliente pública incluida en el código de acb.com; LNB el token anónimo que su web da a cualquier visitante.
- La API privada de la BBL exige un secreto ofuscado: **no se usa**; se leen las páginas públicas.
- BBL: los ids de partido de una temporada son bloques consecutivos (regular y playoffs, cada uno el suyo). La
  temporada en curso toma sus partidos de `/saison/aktuelle-spiele`. Una temporada pasada sin `semillas` las
  **descubre sola**: (A) baja en saltos de `paso_busqueda` desde el id más bajo conocido de una temporada
  posterior; (B) si no aparece la temporada regular, recorre `rangos_busqueda` (`[[1, 40000]]`) en saltos de
  `paso_rango` (100). Al encontrarlas guarda en `config/sources.json` el primer id de cada bloque
  (`ligas.bbl.temporadas.<t>.semillas`), sólo si incluye la temporada regular, y la temporada anterior parte de ahí.
  Motivo del paso B: la web cambió de numeración en 2025. Hasta la temporada regular 2024-25 los ids son bajos
  (2019-20 ≈ 24000, 2020-21 ≈ 25500, 2021-22 ≈ 26000, 2022-23 ≈ 27500); desde los playoffs 2024-25 (≈ 2003212) y
  2025-26 (≈ 2004000) son ≥ 2003000; entre 2000000 y 2003000 hay partidos históricos (1968-1998) importados.
- Basketball-Reference rechaza la huella TLS de `requests`: se descarga con el binario `curl`.
- Descartadas: stats.nba.com (bloquea servidores), RealGM y Proballers (Cloudflare), FIBA LiveStats (no usado por estas ligas).

---

## 5. Datos disponibles y cómo cargarlos

### 5.1 Ficheros (`data/processed/<temporada>/`)

| Fichero | Contenido | Formato |
|---|---|---|
| `ligas/<liga>.csv` | **los datos**: una liga, todas sus fases | CSV, 480 columnas, 1 fila = jugador-equipo-fase, números con 4 decimales |
| `indice.json` | ligas, filas por fase, fecha de extracción | JSON |
| `diccionario_columnas.csv` | columna, grupo, origen, descripción | CSV |
| `completitud.csv` | % de filas con dato por columna × (liga\|fase) | CSV |
| `informe_ejecucion.json` | estado, notas y errores de cada liga en la última ejecución | JSON |
| `../temporadas.json` | temporadas con datos, ligas y filas por fase | JSON |

Desde la versión 1.2 los datos procesados se guardan **sólo como CSV por liga y temporada** (antes había además
un CSV combinado y copias JSON: ~4 veces más espacio). Para tener todas las ligas juntas se concatenan los CSV
(`bbstats.api.dataframe(temporada=T)` o `bbstats.pipeline.read_season(Path)`). Los JSON que lee el Artifact se
generan aparte, sin versionar: `python -m bbstats artifact [--temporada T]` → `data/artifact/<T>/<fase>.json`
(JSON columnar `{"columnas": [...], "filas": [[...]]}`), `indice.json`, `diccionario_columnas.json`, `temporadas.json`.

### 5.2 Volumen (filas jugador-equipo: temporada regular / playoffs)

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

2026-27 en curso a 12-10-2026 (2-5 jornadas; NBA y G League aún sin partidos). Fase `total` ≈ regular + playoffs.

### 5.3 Carga en Python

```python
import pandas as pd
from bbstats.api import dataframe, diccionario
df = dataframe(temporada="2025-26")            # une data/processed/2025-26/ligas/*.csv
acb = dataframe(liga="acb", temporada="2023-24")
# Varias temporadas:
hist = pd.concat([dataframe(temporada=t) for t in ["2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]])
reg = df[df.fase == "regular"]
po  = df[df.fase == "playoffs"]                 # incluye rs_* y delta_*
dic = pd.DataFrame(diccionario())               # descripción de cada columna

# CSV directo, sin bbstats:
df = pd.read_csv("data/processed/2025-26/ligas/acb.csv", dtype={"player_id": str, "team_id": str})
```

Claves:
- `player_uid` = `<liga>:<player_id>` identifica al jugador **dentro de una liga** (los ids no se comparten entre ligas;
  para cruzar ligas hay que emparejar por nombre/fecha de nacimiento).
- Una fila es **jugador-equipo-fase**. Un jugador traspasado tiene varias filas en ACB, LBA, BBL, LNB y NBA (una por equipo).
  En EuroLeague/EuroCup y G League la fuente da una sola fila acumulada (ver §7).
- Para agregar por jugador en una liga: agrupar por `player_uid` y `fase`, sumando columnas del grupo `totales`, y
  recalcular tasas (no promediar porcentajes).

---

## 6. Esquema (480 columnas) y fórmulas

Todas las ligas tienen exactamente las mismas columnas, en el mismo orden (`bbstats/schema.py`).
**Convenciones:** porcentajes en escala 0-100; dato no publicado/no calculable = vacío (NaN), nunca 0;
ninguna fila ni columna se elimina.

| Grupo (nº columnas) | Contenido |
|---|---|
| `identidad` (23) | liga, liga_nombre, pais, temporada, **fase**, fuente, fecha_extraccion, archivo_bruto, player_id, player_uid, nombre, dorsal, posicion, altura_cm, peso_kg, edad, fecha_nacimiento, nacionalidad, team_id, equipo, equipo_codigo, minutos_partido (40/48), **calidad_contexto** |
| `totales` (32) | gp, gs, min, pts, fgm, fga, fg2m, fg2a, fg3m, fg3a, ftm, fta, oreb, dreb, reb, ast, stl, tov, blk, blka (tapones recibidos), pf, pfd (faltas recibidas), plus_minus, pir (valoración), dunks, fastbreaks, pts_fastbreak, pts_paint, pts_2ndchance, pts_off_tov, dd2, td3 |
| `por_partido` (28), `por_36` (27), `por_40` (27), `por_100_pos` (27) | `<stat>_pg`, `<stat>_p36`, `<stat>_p40`, `<stat>_p100` de cada conteo (p100 = por 100 posesiones de su equipo con él en pista) |
| `tiro` (19) | fg_pct, fg2_pct, fg3_pct, ft_pct, efg_pct, ts_pct, tsa, pts_per_fga, pts_per_tsa, fg3a_rate, fta_rate, ft_per_fga, fg2a_share, pct_pts_2/3/ft/paint/fastbreak, dunk_rate |
| `ratios` (22) | min_pct, usg_pct, ast_pct, tov_pct, oreb_pct, dreb_pct, reb_pct, stl_pct, blk_pct, ast_to, ast_ratio, tov_ratio, stl_to_tov, blk_to_pf, stl_plus_blk_p40, pfd_to_pf, pts/reb/ast/fga_share, poss_on_court, poss_used |
| `ratings` (23) | game_score(_pg/_p40), eff(_pg), pir_calc, pie, uper, per, ortg, drtg, net_rtg, floor_pct, pprod, scposs, totposs, stops, stop_pct, ows, dws, ws, ws_per_40, ws_per_48 |
| `contexto_equipo` (21), `contexto_rival` (18), `contexto_liga` (9) | team_<stat> y opp_<stat> (totales de la fase), team_poss, opp_poss, team_pace, team_ortg, team_drtg, team_netrtg, lg_pace, lg_ortg, lg_pts_per_game |
| `metricas_fuente` (96) `src_*` | cifras oficiales de la fuente: PER/OWS/DWS/WS/WS48/OBPM/DBPM/BPM/VORP, % por posición, on/off por 100, tipos de pérdida y falta, distancias y % de tiro por zona (NBA vía Basketball-Reference); ORtg/DRtg/Net/Pace/PIE/USG%/TS% oficiales y % de puntos por tipo (G League); TS%/eFG%/% rebote/AST ratio oficiales (EuroLeague/EuroCup); src_eff, src_oer… |
| `basketnews` (67) `bn_*` | (EuroLeague y ACB) USG/TS/AST/TOV/STL/BLK/OREB/DREB%, ORtg/DRtg/Net individuales, stops, Stop%, puntos creados y asistidos, PIR, y **on/off**: minutos y posesiones con él, ORtg/DRtg/Net on, off y on−off, y % de tiro/rebote/pérdidas/faltas del equipo y del rival con él en pista |
| `contexto_fase` (41) | sólo en filas de playoffs: `rs_<m>` (valor en temporada regular del mismo jugador-equipo) y `delta_<m>` (playoffs − regular) para m ∈ gp, min_pg, pts_pg, pts_p40, reb_p40, ast_p40, ts_pct, efg_pct, usg_pct, ast_pct, tov_pct, reb_pct, per, ortg, drtg, net_rtg, game_score_pg, pir_pg, ws_per_40, pie, bn_netrtg_onoff |

### 6.1 Fórmulas principales (metrics.py)

Notación: MP = minutos del jugador, TmMP = minutos-jugador del equipo (≈200 por partido FIBA, 240 NBA), Tm* = totales
del equipo, Opp* = de los rivales, lg* = suma de la liga en la fase. Todas son de Basketball-Reference (Hollinger / Dean Oliver).

- Posesiones de equipo: `0.5·[(TmFGA + 0.4·TmFTA − 1.07·TmORB/(TmORB+OppDRB)·(TmFGA−TmFG) + TmTOV) + (lo mismo del rival)]`
  (sin datos de rival: `FGA + 0.44·FTA − ORB + TOV`). Ritmo = `minutos_partido · Poss / (TmMP/5)`.
- `ts_pct = PTS / (2·(FGA + 0.44·FTA))`, `efg_pct = (FGM + 0.5·3PM)/FGA`.
- `usg_pct = 100·(FGA + 0.44·FTA + TOV)·(TmMP/5) / (MP·(TmFGA + 0.44·TmFTA + TmTOV))`.
- `ast_pct = 100·AST / ((MP/(TmMP/5))·TmFG − FG)`; `oreb/dreb/reb_pct = 100·X·(TmMP/5)/(MP·(TmX + OppX'))`;
  `stl_pct = 100·STL·(TmMP/5)/(MP·OppPoss)`; `blk_pct = 100·BLK·(TmMP/5)/(MP·(OppFGA − Opp3PA))`.
- `game_score = PTS + 0.4·FG − 0.7·FGA − 0.4·(FTA−FT) + 0.7·ORB + 0.3·DRB + STL + 0.7·AST + 0.7·BLK − 0.4·PF − TOV`.
- `pir_calc` (y `pir` si la fuente no lo publica) = `PTS+REB+AST+STL+BLK+PFD − fallos de campo − fallos de TL − TOV − BLKA − PF`.
- `pie = 100·(PTS+FGM+FTM−FGA−FTA+DREB+0.5·OREB+AST+STL+0.5·BLK−PF−TOV) / (lo mismo de equipo + rival)`.
- `per`: uPER de Hollinger, ajustado por ritmo (`lgPace/TmPace`) y normalizado para que la media ponderada por minutos de la liga en la fase = 15.
- `ortg`, `floor_pct`, `pprod`, `scposs`, `totposs`: puntos producidos y posesiones individuales de Dean Oliver; `drtg`, `stops`, `stop_pct`: rating defensivo individual de Oliver.
- Win Shares: `OWS = (PProd − 0.92·lgPPP·TotPoss)/MPPW`, `DWS = (MP/TmMP)·OppPoss·(1.08·lgPPP − DRtg/100)/MPPW`,
  `MPPW = 0.32·lgPts/partido·(TmPace/lgPace)`.
- **G League (`tiro_libre_unico`)**: un único tiro libre vale 2 o 3 puntos; puntos de TL = `PTS − 2·T2 − 3·T3` y la
  probabilidad de anotar una visita a la línea = FT% (no `1−(1−FT%)²`). Afecta a PProd, ORtg, WS y PER.

### 6.2 Validación con datos reales (2025-26)
- TS% calculado = TS% oficial de la Euroliga (exacto); USG% difiere en décimas del de BasketNews.
- Suma de Win Shares ≈ victorias: ACB 306/306, BBL 305/306, LBA 206/210, EuroLeague 375/380, EuroCup 177/180,
  NBA 1259/1230, G League 574/558.
- Invariantes por liga y fase: PER medio ponderado por minutos = 15; USG% medio = 20 (salvo LNB, sin contexto de rival).

---

## 7. Limitaciones y sesgos que el agente debe tener en cuenta

| Liga | Limitación | Consecuencia para modelos |
|---|---|---|
| NBA | sin faltas recibidas totales (`pfd`) | `pir` vacío; usar `src_drawn_shooting`/`src_drawn_offensive` si interesa |
| G League | sin titularidades (`gs`); jugadores traspasados en una fila (equipo = último) y muchos asignados desde la NBA | contexto de equipo aproximado para traspasados; filtrar por minutos |
| Todas (validación) | Win Shares de temporada regular ≈ victorias reales: ±3 % en ACB, BBL, G League, LBA y NBA de 2020-21 a 2025-26; excepción ACB 2022-23 (279 / 306) | tratar WS de ACB 2022-23 con cautela |
| EuroCup 2020-21 | el feed sólo distingue `RS`; el Top 16 de esa temporada cae en `playoffs` (= total − RS) | 211 filas de "playoffs" en 2020-21 |
| EuroLeague / EuroCup | sin +/-, mates ni puntos por zona; equipos sin V/D en el feed; traspasados en una fila (`team_id` = `ASV;ULK`, contexto del último equipo) | `team_w/team_l` vacíos; `team_id` con `;` indica traspaso |
| BBL | sin tapones recibidos ni mates; temporadas pasadas localizadas por búsqueda de ids (semillas guardadas en `config/sources.json`); 2021-22: 305 de 306 partidos de temporada regular | `pir` vacío |
| LNB | la fuente no publica totales de rivales (sólo puntos encajados) → `calidad_contexto = parcial` | **ortg, drtg, ws, stl_pct, blk_pct, reb_pct… vacíos**; usar ratios sin rival (ts, usg, ast_ratio, por 40). Jugadores bajo el umbral del ranking (≈40 % de la plantilla) se completan desde su ficha: sin tov, pf, pfd, blka ni +/- |
| BasketNews | sólo EuroLeague y ACB y **sólo desde 2024-25** (para 2020-21…2023-24 su API responde 422: `bn_*` vacíos, anotado en el informe); promedios redondeados; en playoffs usa sólo su fase "Playoffs" (no play-in ni Final Four); ~99 % de jugadores emparejados en regular (fallan apodos: Sasha/Aleksandr Vezenkov) | `bn_*` vacíos en el resto de ligas |
| General | duraciones distintas (40' FIBA vs 48' NBA), ritmos distintos (≈67 EuroLeague, ≈75 FIBA nacional, ≈97-99 NBA/G League) y nivel competitivo distinto | comparar entre ligas con tasas por posesión/40', percentiles dentro de liga-fase, y un factor de nivel de liga que el agente debe estimar (no está en los datos) |
| Muestras pequeñas | jugadores con pocos minutos dan ratings extremos | filtrar por `min` (p.ej. ≥ 200 en regular, ≥ 60 en playoffs) o usar estimadores bayesianos con shrinkage |

`calidad_contexto`: `completo` = hay totales de equipo y rival (todas las métricas); `parcial` = sólo equipo;
`sin_contexto` = ninguno. Consultar `completitud.csv` antes de usar una columna en una liga.

---

## 8. Artifact asociado: "Mesa Multiliga Baskonia"

- URL: https://claude.ai/artifact/F4AxayFrM2d1D5JEoNiDoN (privado del propietario; se comparte desde su menú Compartir).
- Código: `artifact/mesa-multiliga.html`. Datos publicados junto a la página como ficheros:
  `datos/<temporada>/{indice,regular,playoffs,total}.json`, `datos/diccionario_columnas.json` y `datos/temporadas.json`,
  generados con `python -m bbstats artifact` en `data/artifact/` (no versionado).
- Funciones: selector de temporada (lista leída de `datos/temporadas.json`: 2026-27 … 2020-21); pestañas de fase **Temporada regular / Playoffs / Total**;
  filtros por liga, búsqueda y minutos mínimos; vistas (básico, tiro, por 40'/100, avanzada, ratings, on/off,
  playoffs vs regular, métricas oficiales, contexto de equipo); tabla ordenable; ficha del jugador con barras
  playoffs frente a regular.
- **Botón EJECUTAR**: la página no puede ejecutar Python, así que usa la capacidad `mcp` con el conector
  **Claude Code Remote** (herramientas `get_trigger` y `fire_trigger`) para lanzar la Routine
  `EJECUTAR Mesa Multiliga Baskonia` (`trig_01VA8u4RqAzGbKy4v4bFn1mw`, sólo bajo demanda). El mensaje que envía es
  `temporada=<T> ligas=<l1 l2 …>` y **sólo se actualiza esa temporada**. La Routine abre una sesión de Claude Code que:
  adjunta el repositorio con permiso de escritura (`add_repo`), clona/actualiza la rama, ejecuta
  `python -m bbstats ejecutar --temporada <T>`, hace commit y push de `data/` y `config/sources.json`, y republica
  en el Artifact (misma URL) `datos/temporadas.json` y los ficheros `datos/<T>/*.json` de esa temporada.
  Primera ejecución real (12-10-2026, 2026-27): descarga y republicación correctas; el push falló (403) porque la
  sesión no tenía el repositorio autorizado, de ahí el paso `add_repo` añadido después.
- Para editar la página: pedirlo a Claude con la URL (lee la versión publicada y republica en la misma URL), o editar
  `artifact/mesa-multiliga.html` y republicarlo con `url` = la del Artifact.

---

## 9. Guía para construir algoritmos y modelos sobre estos datos

1. **Unidad de análisis**: fila jugador-equipo-fase. Para evaluar jugadores, usar normalmente `fase == "regular"`
   (muestra mayor) y `playoffs` como señal adicional con `delta_*`.
2. **Filtrar muestra**: `min` mínimo por fase; ponderar por `min` o `poss_on_court` al promediar.
3. **Comparar entre ligas**: usar tasas (`*_p40`, `*_p100`, `*_pct`, ratings) y estandarizar dentro de cada
   (liga, temporada, fase) — z-scores o percentiles — antes de mezclar ligas; añadir un coeficiente de nivel de liga
   (p.ej. estimado con jugadores que cambian de liga entre temporadas).
4. **Rasgos útiles**: perfil de tiro (fg3a_rate, fta_rate, pct_pts_*, src_pct_fga_*), creación (ast_pct, usg_pct,
   bn_created_pts_pg), cuidado del balón (tov_pct), rebote (oreb/dreb_pct), defensa (stl_pct, blk_pct, drtg,
   bn_stop_pct, bn_drtg_onoff), impacto (net_rtg, bn_netrtg_onoff, src_bpm, ws_per_40), físico/biografía
   (altura_cm, edad, posicion) y contexto (team_pace, team_netrtg, min_pct).
5. **Columnas con huecos**: comprobar `completitud.csv`; no imputar con 0. Usar modelos que admitan NaN o imputación por liga.
6. **No mezclar** `src_*` de distintas fuentes como si fueran la misma métrica: cada fuente usa su propia definición.
   Para comparabilidad usar las columnas calculadas por el motor (mismas fórmulas en todas las ligas).
7. **Reproducibilidad**: cada fila lleva `fecha_extraccion` y `archivo_bruto`; cualquier cambio de métrica se aplica
   con `python -m bbstats reprocesar --temporada T`.
8. **Ampliar**: nuevas métricas → `schema.py` (columna + descripción) y `metrics.py` (cálculo), y luego `reprocesar`;
   nuevas ligas → adaptador en `bbstats/adapters/` + entrada en `config/sources.json`; nuevas temporadas → `--temporada`, o `temporada_inicial` + `historico`.

---

### 9.1 Modelos ya construidos (`bbmodel/`)
- **Algoritmo A** (`docs/algoritmo_A.md`): traducción de 25 métricas de tasa a la EuroLeague 2025-26.
  Identidad entre ligas por nombre + año de nacimiento + calendario (`bbmodel/identidad.py`); posición en
  3 grupos E/A/I con regresión logística donde falta (`posicion.py`); bayes empírico por exposición
  (`suerte.py`); tipo de cambio m, s por liga y métrica con EM sobre jugadores puente y deriva por edad
  (`enlace.py`); traducción con intervalos (`modelo.py`); examen fuera de muestra (`validacion.py`).
  Resultados versionados en `data/modelos/algoritmo_A/`. Reajustar tras cada carga de datos:
  `python -m bbmodel ajustar`.
- **Algoritmo B** (`docs/algoritmo_B.md`, `bbmodel/algoritmo_b.py`): red neuronal en numpy (ADN de 8 dimensiones por
  jugador-temporada, capa oculta de 32 con desplazamiento por liga, entorno liga × temporada × posición, efecto de
  equipo-temporada con varianza por bayes empírico, Laplace + conjunto de 5 redes). Hiperparámetros elegidos sólo con
  el corte 2022 (no con el examen). Resultados en `data/modelos/algoritmo_B/`. `python -m bbmodel ajustar-b`.
- **A+B** (`bbmodel/mesa_normalizacion.py`): media de A y B en escala transformada; es la estimación recomendada.
  `python -m bbmodel mesa-normalizacion` genera `normalizacion/resumen.json` y `normalizacion/jugadores_<temp>.json`
  para la pestaña «Normalización de ligas» (publicar en `datos/normalizacion/`).
- Corrección (oct. 2026): `identidad.py` asigna el año de nacimiento por persona (mediana), no por nodo de liga.
- **Evaluación de ligas** (`bbmodel/evaluacion_ligas.py`): genera `data/artifact/<temporada>/evaluacion_<fase>.json`
  para la pestaña del Artifact (publicarlos con el resto de datos, ruta `datos/<temporada>/`).
- Dato a saber: en la LNB la columna `edad` es la edad ACTUAL (no la de cada temporada); usar
  `fecha_nacimiento`.
- **Estilos de juego** (`bbestilo/`, `docs/estilos_de_juego.md`, artículo `docs/articulo/estilos_de_juego_baskonia.pdf`):
  modelo final = **VaDE de 6 estilos** por club-competición-temporada (mezcla de 6 gaussianas de covarianza completa en
  un latente 3D = mapa; consenso de 10 semillas y ajuste fino con la mezcla fijada), sobre los equivalentes EuroLeague
  A+B agregados por minutos (13 rasgos) **con el nivel neutralizado** (regresión de cada rasgo en [1, L, L²], L = índice
  de calidad: PER, GmSc/40, WS/40, ORtg, DRtg, pts/100, TS%, eFG%). η² nivel-estilo 0,4 %. Sin IDEC (retirada).
  Nombres de estilos en `config/estilos.json` (revisar si se reentrena). Iteraciones anteriores (v1 12 estilos, v2 8,
  v3 6 con 5 semillas) sólo como métricas y asignaciones en `data/modelos/estilos/historial/` (la tabla de evolución
  del Atlas y del artículo sale de ahí). `python -m bbestilo entrenar | evaluar | analisis | encaje | parecidos |
  exportar | articulo`. Simulación de varios fichajes y bajas: `encaje.simular_plantilla` (CLI `encaje --jugador A B
  --baja C`), igual que el JS del Atlas. Buscador de parecidos: `similares.py`.
  Atlas: Artifact «Atlas de Estilos» (https://claude.ai/artifact/D2ULCYstYh4ykwSzExUPNU; cinco pestañas; republicar
  con `files` = `estilos/{meta,clubes,jugadores}.json` y `articulo/estilos_de_juego_baskonia.pdf`, capacidad
  `downloads`). Hallazgos: BIC/ICL eligen 6 estilos; el encaje por similitud no predice el rendimiento del fichaje;
  la continuidad de plantilla predice conservar el estilo; Baskonia cambia mucho de estilo.

## 10. Historial

- Commit 1 — arquitectura por capas, esquema, motor de métricas, tests.
- Commit 2 — fuentes reales validadas, fases, BasketNews, corrección de tiro libre único (G League) y traspasos
  (EuroLeague), datos 2025-26 y 2026-27.
- Commit 3 — Artifact "Mesa Multiliga Baskonia" y Routine EJECUTAR.
- Commit 4 — este documento de contexto.
- 6b9ec9a — G League: coeficiente de tiro libre en posesiones 0,79 (calibrado); BasketNews: emparejamiento determinista;
  BBL: descubrimiento de semillas para temporadas pasadas.
- Commit 6 — modo histórico (desde 2020-21) + actualización por temporada; la BBL guarda en config las semillas que
  descubre y busca también por rangos (cambio de numeración de su web); `temporadas.json`; Artifact con selector
  de temporadas dinámico.
- Datos 2020-21 a 2024-25 de las 8 ligas; procesados sólo en CSV por liga y temporada (~80 MB en total).
- Correcciones: G League (mismo coeficiente de tiro libre en las fórmulas de Oliver: WS vuelven a ≈ victorias),
  LBA (playoffs por fase `ph_id` y competición ausente del listado) y LNB ("Phase Finale" 2020-21 = playoffs).
- Artifact (versión 16): la página publicada se rediseñó fuera de este repositorio ("Moneyball Analytics", con
  Comparador y Evaluación de ligas); `artifact/mesa-multiliga.html` es ahora esa versión con el selector de
  temporadas dinámico. La pestaña Evaluación usa `datos/<T>/evaluacion_<fase>.json`, que sólo existen para
  2025-26 y 2026-27 (los generó un script `compute_eval.py` que no está en este repositorio).
- Algoritmo A (`bbmodel`) y cálculo de la evaluación de ligas en el repositorio; resultados en `data/modelos/algoritmo_A/`.
- Algoritmo B, combinación A+B y pestaña «Normalización de ligas» (Artifact versión 17); A reajustado tras corregir el
  año de nacimiento por persona. `artifact/mesa-multiliga.html` = página publicada con la nueva pestaña.
- Rama `claude/bold-euler-hubmhk`: estilos de juego (`bbestilo`). v1: IDEC y VaDE con 12 estilos. v2: 8 estilos, nivel
  neutralizado, VaDE con covarianza completa y consenso, análisis complementarios, Atlas rediseñado y artículo en PDF. Después: modelo de 6 estilos y buscador de parecidos. Final: sólo VaDE de 6
  estilos con 10 semillas, simulador de varios fichajes y bajas, Atlas en pestañas y artículo reescrito.
