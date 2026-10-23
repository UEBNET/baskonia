# Registro de cambios

## 2026-10-23 — Fases 3, 4 y 5: roles por minutos, reemplazo de rol y entropía (`bbfit`)

Añadido
- `python -m bbfit roles|reemplazo|entropia` (`bbfit/__main__.py`); cada ejecución queda registrada en MLflow
  (`bbfit.registro`, almacén local `experimentos/`, no versionado). Umbrales y pesos en `configs/roles.yaml`,
  `configs/reemplazo.yaml` y `configs/entropia.yaml`.
- Fase 3 (`bbfit/roles.py`, `bbfit/cambios.py`, `bbfit/datos.py`): tabla partido × jugador desde los tramos y tiros
  (`data/modelos/roles/partidos_jugador/<t>.csv.gz`, con ausencias), respaldo de caja donde no hay jugada a jugada,
  roles RESIDUAL/PROFUNDIDAD/ROTACIÓN/TITULAR/GO-TO-GUY por MIN% (40'/48'), GTI, vector de rol Dirichlet para
  muestras < 5 partidos, H_rol, cambios de rol con detección bayesiana en línea (BOCPD propio) y covariables
  (entrenador, vacío de rol, fichaje, rendimiento reciente). Salidas `player_role_spells.csv.gz`,
  `player_role_season.csv.gz`, `team_role_structure.csv` y validación.
- Fase 4 (`bbfit/reemplazo.py`): producción por rol y proyección condicionada al rol de destino; elasticidad
  uso-eficiencia con variable instrumental (vacío de rol del partido) y agrupamiento parcial por pos3; redistribución
  de suma fija; libro de minutos por rol entre temporadas (identidad exacta) con tasa de relleno, transiciones de
  rol, asociación con el cambio de Net (bootstrap, no causal); calidad de compañeros; tendencias de entrenador y
  `asignar_minutos` (Plackett-Luce con restricciones) para el simulador. Salidas en `data/modelos/reemplazo/`.
- Fase 5 (`bbfit/entropia.py`): H_estilo (zonas de tiro + acciones de caja, Dirichlet con intervalo), H_rol
  posterior, volatilidad intrínseca σ_i (residuo sin contexto, varianza por exposición, contracción jerárquica de
  log σ²) y entropía de equipo (uso, tiros, minutos, red de pases). Salidas en `data/modelos/entropia/`.
- Tests sintéticos `tests/test_roles.py`, `tests/test_reemplazo.py`, `tests/test_entropia.py` (29).

Cambiado
- `bbfit/registro.py`: permite el almacén de ficheros de MLflow 3 (`MLFLOW_ALLOW_FILE_STORE`).
- `.gitignore`: caché `data/modelos/roles/_cache/`.

Detalle, resultados y riesgos: `docs/checkpoints/F3.md`, `F4.md`, `F5.md`.

## 2026-10-23 — Fase 6: taxonomía unificada de estilos jugador ↔ equipo

Añadido
- `bbfit/estilos_unificados.py` y `python -m bbfit estilos [--reusar-k]`: 12 rasgos con la misma definición para
  jugador y equipo (ritmo, 3PAr, triple de esquina, aro, FTr, canastas sin asistencia, AST%, rebote ofensivo,
  TOV%, robos, tapones, faltas) en z por rangos dentro de cada liga-temporada (15 ligas, incluidas las FEB);
  mezcla gaussiana ajustada sobre jugadores (≥ 300 min) con proyección de los equipos; K por BIC + estabilidad
  bootstrap → **6 estilos**: Spacing, Circulación, Isolation, Old-School, Pistons, Pintura. Estilo principal,
  secundario, vector de pertenencia y etiqueta («puro», «A · B») por equipo-temporada, jugador-etapa y tramo de
  entrenador. Registro en MLflow (experimento `estilos_unificados`).
- `configs/styles.yaml` (umbrales, regla de K, nombres, colores, definiciones y firmas de nombre).
- Salidas `data/modelos/estilos_unificados/{equipos.csv, jugadores.csv.gz, estilos.json, seleccion_k.json,
  correspondencia_vade.csv}`; correspondencia con VaDE (ARI 0,03: miden cosas distintas).
- Tests sintéticos `tests/test_estilos_unificados.py`.

Cambiado
- `bbestilo/exportar.py`: campos nuevos `eu`, `eu2`, `eu_p`, `eu_probs`, `eu_etiqueta` en clubes, etapas de
  entrenador y jugadores del Atlas, y `meta.estilos_unificados`; los campos VaDE no cambian.
- `bbfit/__main__.py`: orden `estilos`.

Detalle, resultados y riesgos: `docs/checkpoints/F6.md`.

## 2026-10-22 — Fase 1: competiciones FEB (Primera, Segunda y Tercera FEB)

Añadido
- Tres ligas nuevas en el mismo esquema y tubería: `feb1` (Primera FEB / LEB Oro), `feb2` (Segunda FEB / LEB Plata)
  y `feb3` (Tercera FEB / Liga EBA): Primera FEB 2022-23 a 2026-27, Segunda y Tercera 2023-24 a 2026-27 (alcance
  decidido por el usuario; `temporada_inicial` por liga en config). Grupo = atributo del partido.
  `config/competition_aliases.json` con los nombres históricos por temporada.
- Adaptador `bbstats/adapters/feb.py` (calendario por postback de baloncestoenvivo.feb.es, KeyFacts/BoxScore de
  intrafeb.feb.es con el token anónimo de la página pública, plantillas y entrenador de Equipo.aspx). Bruto incremental.
- Fuente de jugada a jugada `feb` (`bbstats/lineups/sources/feb.py`): formato estructurado (2024-25+, con
  coordenadas) y formato texto (hasta 2023-24, nombres emparejados con el boxscore).
- `bbstats/lineups/possessions.py`: posesiones reales evento a evento (`possession_id`), genérico para todas las ligas.
- `bbstats/contrato.py` y `python -m bbstats contrato --ligas feb1 feb2 feb3`; `python -m bbstats feb` (partidos con
  grupo, `feb_cobertura.csv`, `feb_posesiones.csv`, `feb_sesgo_registro.csv`).
- `bbmodel/crosswalk.py` y `python -m bbmodel crosswalk`: `player_id_crosswalk.csv` (confianza y método) y
  `crosswalk_revision.csv` (casos dudosos, no aplicados). Umbrales en `config/sources.json → identidad`.
- Entrenadores FEB (uno por equipo y temporada, de la página del equipo) en `bbstats/entrenadores.py`.
- Sistemas de coordenadas FEB en `bbmodel/zonas.py` (calibrados: 99,1-99,3 % de acierto 2/3).
- Tests `tests/test_contract_feb.py` (datos sintéticos).

Cambiado
- `bbstats/http.py`: la pausa por dominio es común a todos los clientes del proceso (antes, por cliente), para que
  varias ligas del mismo dominio en paralelo respeten la cortesía.
- `bbmodel/identidad.py`: las FEB cuentan como ligas nacionales (pueden coincidir con copas europeas).

Detalle, resultados y riesgos: `docs/checkpoints/F1.md`.
