# Registro de cambios

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
