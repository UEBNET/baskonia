# Quintetos, parejas, on/off y conexiones: fuentes verificadas y plan aprobado

Investigación del 15-10-2026 (≈500 peticiones reales, sin cambios en el código). **Estado: aprobada la
viabilidad; pendiente de la orden de implementación.**

Decisiones del usuario:
1. Alcance: las 8 ligas, temporadas 2020-21 a 2026-27; donde la fuente no lo permite, columnas en blanco y
   anotado en el informe.
2. NBA y G League: cálculo propio desde el play-by-play (mismo algoritmo que en Europa) + tablas oficiales
   (quintetos, on/off, pases) como contraste y columnas extra.
3. Play-by-play en bruto: en Git, un fichero comprimido por liga y temporada en `data/raw` (≈100 MB/temporada).

## Conclusión

Ninguna liga europea publica tablas de quintetos/parejas/on-off ya calculadas. Todas (salvo BBL 2020-23 y
LNB 2020-21) publican play-by-play con cambios, asistencias y coordenadas de tiro: los quintetos, parejas,
tríos, on/off y redes de asistencias se calculan a partir de él. Reconstrucciones de prueba contra el boxscore
oficial: minutos y +/- exactos o casi (detalle por liga abajo).

## Fuentes por liga

### EuroLeague (E) y EuroCup (U) — `live.euroleague.net` (GET, sin cabeceras)
- Lista de partidos: `https://api-live.euroleague.net/v2/competitions/{E|U}/seasons/{E2024}/games` →
  `gameCode`, `played`, `phaseType`, `round` (1 llamada/temporada; códigos 1..N sin huecos).
- Play-by-play: `https://live.euroleague.net/api/PlayByPlay?gamecode=N&seasoncode=E2024` → por cuarto
  (`FirstQuarter`…`ForthQuarter`, `ExtraTime`): `NUMBEROFPLAY, CODETEAM, PLAYER_ID, PLAYTYPE (IN|OUT|AS|2FGM|
  3FGA|FTM|D|O|TO|ST|CM|RV…), MINUTE, MARKERTIME "09:20" (tiempo restante), POINTS_A, POINTS_B`.
- Boxscore: `…/api/Boxscore?gamecode=&seasoncode=` → `IsStarter` (titulares: no están en el PBP), `Minutes`,
  `Plusminus`.
- Tiros: `…/api/Points?gamecode=&seasoncode=` → `ID_PLAYER, ID_ACTION, POINTS, COORD_X, COORD_Y, ZONE A–I,
  FASTBREAK, SECOND_CHANCE, POINTS_OFF_TURNOVER, NUM_ANOT (= NUMBEROFPLAY), UTC`.
- Asistencias: evento `AS` sin enlace; se empareja con el último tiro anotado del mismo equipo (99,9 %).
- Verificado E y U 2020-21 … 2026-27. Reconstrucción: 5 v 5 siempre; +/- exacto 12/13 (prórroga ±1);
  minutos ±3 s en 20/24 partidos (algún cambio con reloj mal anotado: 30–60 s).
- Coste: 3 llamadas/partido (≈1.000 EuroLeague, ≈560 EuroCup por temporada).
- No sirven: api-live v1/v2/v3 para PBP/lineups (404), feeds InCrowd lineups/onOff (404),
  euroleaguebasketball.net (429, protección Vercel).

### ACB — `api2.acb.com` (cabeceras: `X-APIKEY` pública de `acb.py`, `Origin/Referer: https://live.acb.com/`)
- PBP: `/api/matchdata/PlayByPlay/play-by-play?matchId=M` → `order, playType, quarter, minute, second`
  (restante), `local`, `playerLicenseId`. Titulares: evento 599 (10/partido). Cambios: 112 entra, 115 sale.
  Asistencias: 107 (tras 2 pts/mate), 108 (tras triple), 119 (antes de tiros libres), justo después del tiro.
- Tiros: `/api/matchdata/MatchShots/match-shots?matchId=M` → `posX/posY`, `zone`, anotado, jugador, reloj.
- Verificado 2020-21, 2023-24, 2025-26, 2026-27. Minutos reconstruidos exactos al segundo.
- Coste ≈660 llamadas/temporada (PBP + tiros). Ids de partido ya en `data/raw/acb`.

### LBA — `legabasket.it` (cabeceras `Accept` y `Referer: https://www.legabasket.it/`)
- PBP: `https://www.legabasket.it/api/championships/get-championships-matches-play-by-play?id=M` →
  `action_id, description` (italiano: `Ingresso`/`Uscita`), `player_id, team_id, period, minute/seconds`
  (transcurrido), `x,y` (0–100), `linked_action_id` (asistencia → tiro; nulo en 2020-21, se usa adyacencia).
- Titulares: no están en el PBP; `sf=1` en el boxscore (`get-championships-matches-scores-by-id`, ya
  descargado por el adaptador).
- Zonas de tiro por equipo (sin coordenadas): `/api/matches/get-championship-matches-shots-by-id?id=M&info=1`.
- Verificado 2020-21 … 2026-27. 5 v 5 siempre; minutos por jugador ±12–15 s de media (máx. 37 s) frente al
  boxscore; total de equipo exacto 200:00.
- Coste ≈260 llamadas/temporada.

### BBL — página pública de partido (la que ya descarga el adaptador; sin peticiones extra)
- `__NEXT_DATA__.props.pageProps.initialGameStats.actions[]`: `type, period, gameTime` (restante),
  `realTime, seasonTeamId, seasonPlayerId, assistingSeasonPlayerId, qualifiers, coordinates{x,y},
  homeTeamPoints/guestTeamPoints, orderId`. En `SUBSTITUTION`: `seasonPlayerId` = sale,
  `assistingSeasonPlayerId` = entra. Cambios entre cuartos no anotados: se infieren de quién actúa primero.
- 2023-24 … 2026-27: minutos y +/- exactos (10/10 desde 2024-25; en 2023-24 algún `seasonPlayerId=null`
  que se asigna al jugador que falta).
- **2020-21 … 2022-23: sin quintetos ni on/off** (cambios, rebotes y faltas sin jugador; `isStartingFive`
  falso). Sí asistencias (anotador + asistente) y tiros.
- No se usa la API privada `api.basketball-bundesliga.de`.

### LNB — widget Sportradar/Atrium que incrusta lnb.fr (sin token ni cabeceras)
- `https://embed-api.eui.connect.sportradar.com/v1/embed/12/fixture_detail?fixtureId=<uuid>&sub=pbp` →
  `periodData[].events[]`: `clock` ("PT9M2S" restante), `eventType/eventSubType` (cambios entra/sale por
  separado), `assist` como evento propio tras el tiro, `personId, entityId, scores, x/y` (0–100).
- `&sub=statistics` → boxscore con `starter`, `minutes`, `plusMinus`; `&sub=shot_chart`, `&sub=analysis`.
- Ids (uuid): `api-prod.lnb.fr/match/getMatchesByCompetitionAndRound` (POST, token anónimo de lnb.fr) o, desde
  2023, `…/embed/12/fixtures?seasonId=<uuid>` (toda la temporada en 1 llamada).
- 2021-22 … 2026-27: +/- y asistencias exactos; minutos ±7 s (procesar en orden de lista; reloj nunca hacia
  atrás). **2020-21: PBP vacío** (sólo boxscore).
- Coste ≈530 llamadas/temporada.

### NBA y G League — `stats.gleague.nba.com/stats` (Referer/Origin `https://gleague.nba.com`)
- `LeagueID=20` (G League) o `00` (NBA: uso no previsto de ese host; podría cerrarse). `stats.nba.com` y
  `cdn.nba.com` bloqueados desde aquí.
- Tablas oficiales (1 llamada por equipo; el listado de liga corta en 2.000 filas):
  `leaguedashlineups` (`GroupQuantity` 2/3/4/5, `MeasureType` Base/Advanced),
  `teamplayeronoffdetails` / `teamplayeronoffsummary`, `shotchartdetail`, `playerdashptpass` (sólo NBA:
  matriz pasador→receptor con tracking), `leaguegamelog` (ids).
- PBP: G League `playbyplayv2` (ids de ambos jugadores del cambio y del asistente); NBA `playbyplayv3`
  (asistente y jugador que entra sólo en el texto → mapear apellidos con el boxscore `boxscoretraditionalv3`).
  Titulares: `boxscoretraditionalv2` `START_POSITION` / v3 `position`.
- Verificado 2020-21, 2023-24, 2025-26 (ambas ligas).
- Contraste NBA: `api.pbpstats.com/get-totals/nba?Type=Lineup&TeamId=` (posesiones por quinteto),
  `get-on-off/nba`; Basketball-Reference `/teams/XXX/{Y}/lineups/` (top 20) y `/on-off/` (curl, 3,5 s).

### BasketNews (EuroLeague league_id 25, ACB 41; sólo 2024-25 en adelante)
- `team-profile/on-off.json` (ya usado) y `team-profile/combo.json` (POST `ajax=true&league_id&season&
  team_id&player_ids[]=…`, 2–5 ids): estadísticas de una combinación concreta. Sólo para contrastar.

## Plan de implementación (pendiente de la orden)

1. Adaptadores de PBP por liga → bruto por partido en `data/raw/<liga>/<temporada>/pbp_*.json.gz`
   (empaquetado por temporada), descarga incremental (sólo partidos nuevos).
2. Modelo común de eventos (`periodo, segundo_partido, equipo, jugador, tipo, puntos, asistente, x, y`) y
   reconstrucción de **tramos** (10 jugadores en pista, inicio/fin, puntos a favor/en contra, posesiones,
   eventos) con el mismo algoritmo en todas las ligas; validación por partido contra minutos y +/- oficiales.
3. Salidas por liga y temporada en `data/processed/<temporada>/quintetos/` (CSV, columnas idénticas en todas
   las ligas, fases regular/playoffs/total): `tramos`, `quintetos`, `trios`, `parejas`, `onoff`,
   `asistencias` (pasador → anotador: asistencias, puntos, tipo de tiro), `tiros` (con quinteto en pista).
   Ratings por 100 posesiones y contexto de liga como en el esquema actual.
4. NBA/G League: además, tablas oficiales como columnas `src_*` y contraste automático.
5. Lagunas (BBL 2020-23 sin quintetos/on-off; LNB 2020-21 sin PBP) en blanco y en el informe.
6. Coste de la carga inicial: ≈25.000–30.000 peticiones (varias horas, una vez).
