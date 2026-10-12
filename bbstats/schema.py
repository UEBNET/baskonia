"""Esquema canónico de salida: MISMAS columnas y en el mismo orden para todas las ligas.

Toda columna que una liga no publique ni se pueda calcular queda en blanco (NaN / vacío),
nunca se elimina. El diccionario de columnas se exporta junto a los datos.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    name: str
    group: str
    description: str
    origin: str  # "fuente" (leído), "calculado" (motor de métricas), "contexto"


_COLS: list[Column] = []


def _add(name: str, group: str, description: str, origin: str = "calculado") -> None:
    _COLS.append(Column(name, group, description, origin))


# --------------------------------------------------------------------------------------
# 1. Identidad y contexto
# --------------------------------------------------------------------------------------
for _n, _d in [
    ("liga", "Código interno de la liga (euroleague, acb, nba, ...)"),
    ("liga_nombre", "Nombre oficial de la competición"),
    ("pais", "País / ámbito de la competición"),
    ("temporada", "Temporada canónica (p.ej. 2025-26)"),
    ("fase", "Fase: regular (temporada regular), playoffs (play-in + playoffs + final four/finales) o total"),
    ("fuente", "Origen de los datos (URL base / proveedor)"),
    ("fecha_extraccion", "Fecha UTC de la descarga del JSON bruto usado"),
    ("archivo_bruto", "Ruta del JSON bruto del que sale esta fila (trazabilidad)"),
    ("player_id", "Identificador del jugador en la fuente"),
    ("player_uid", "Identificador único global: <liga>:<player_id>"),
    ("nombre", "Nombre completo del jugador"),
    ("dorsal", "Dorsal"),
    ("posicion", "Posición publicada por la fuente"),
    ("altura_cm", "Altura en centímetros"),
    ("peso_kg", "Peso en kilogramos"),
    ("edad", "Edad"),
    ("fecha_nacimiento", "Fecha de nacimiento"),
    ("nacionalidad", "Nacionalidad / país"),
    ("team_id", "Identificador del equipo en la fuente"),
    ("equipo", "Nombre del equipo"),
    ("equipo_codigo", "Código / abreviatura del equipo"),
    ("minutos_partido", "Duración reglamentaria del partido en la liga (40 FIBA, 48 NBA)"),
    ("calidad_contexto", "completo = hay totales de equipo y rival; parcial = solo equipo; sin_contexto"),
]:
    _add(_n, "identidad", _d, "contexto")

# --------------------------------------------------------------------------------------
# 2. Totales (estadística básica acumulada en la temporada)
# --------------------------------------------------------------------------------------
COUNTING: list[tuple[str, str]] = [
    ("gp", "Partidos jugados"),
    ("gs", "Partidos como titular"),
    ("min", "Minutos totales"),
    ("pts", "Puntos"),
    ("fgm", "Tiros de campo anotados (T2+T3)"),
    ("fga", "Tiros de campo intentados"),
    ("fg2m", "Tiros de 2 anotados"),
    ("fg2a", "Tiros de 2 intentados"),
    ("fg3m", "Triples anotados"),
    ("fg3a", "Triples intentados"),
    ("ftm", "Tiros libres anotados"),
    ("fta", "Tiros libres intentados"),
    ("oreb", "Rebotes ofensivos"),
    ("dreb", "Rebotes defensivos"),
    ("reb", "Rebotes totales"),
    ("ast", "Asistencias"),
    ("stl", "Robos"),
    ("tov", "Pérdidas"),
    ("blk", "Tapones a favor"),
    ("blka", "Tapones recibidos"),
    ("pf", "Faltas personales cometidas"),
    ("pfd", "Faltas recibidas"),
    ("plus_minus", "Más/menos (+/-) acumulado"),
    ("pir", "Valoración (PIR / VAL) acumulada"),
    ("dunks", "Mates"),
    ("fastbreaks", "Contraataques (número de acciones; ACB 'C')"),
    ("pts_fastbreak", "Puntos de contraataque"),
    ("pts_paint", "Puntos en la pintura"),
    ("pts_2ndchance", "Puntos de segunda oportunidad"),
    ("pts_off_tov", "Puntos tras pérdida rival"),
    ("dd2", "Dobles-dobles"),
    ("td3", "Triples-dobles"),
]
COUNTING_NAMES = [c for c, _ in COUNTING]
for _n, _d in COUNTING:
    _add(_n, "totales", _d, "fuente")

# Estadísticas que se expresan también por partido / 36 / 40 / 100 posesiones
RATE_BASE = [c for c in COUNTING_NAMES if c not in {"gp", "gs", "min", "dd2", "td3"}]
_DESC = dict(COUNTING)
for _n in ["min"] + RATE_BASE:
    _add(f"{_n}_pg", "por_partido", f"{_DESC[_n]} por partido")
for _n in RATE_BASE:
    _add(f"{_n}_p36", "por_36", f"{_DESC[_n]} por 36 minutos")
for _n in RATE_BASE:
    _add(f"{_n}_p40", "por_40", f"{_DESC[_n]} por 40 minutos")
for _n in RATE_BASE:
    _add(f"{_n}_p100", "por_100_pos", f"{_DESC[_n]} por 100 posesiones de su equipo con él en pista")

# --------------------------------------------------------------------------------------
# 3. Tiro y eficiencia
# --------------------------------------------------------------------------------------
for _n, _d in [
    ("fg_pct", "% tiros de campo"),
    ("fg2_pct", "% tiros de 2"),
    ("fg3_pct", "% triples"),
    ("ft_pct", "% tiros libres"),
    ("efg_pct", "eFG%: (FGM + 0.5*3PM) / FGA"),
    ("ts_pct", "TS%: PTS / (2*(FGA + 0.44*FTA))"),
    ("tsa", "Intentos de tiro reales: FGA + 0.44*FTA"),
    ("pts_per_fga", "Puntos por tiro de campo intentado"),
    ("pts_per_tsa", "Puntos por intento real de tiro"),
    ("fg3a_rate", "3PAr: triples intentados / FGA"),
    ("fta_rate", "FTr: FTA / FGA"),
    ("ft_per_fga", "FTM / FGA"),
    ("fg2a_share", "Proporción de tiros de 2 sobre FGA"),
    ("pct_pts_2", "% de los puntos que llegan de 2"),
    ("pct_pts_3", "% de los puntos que llegan de 3"),
    ("pct_pts_ft", "% de los puntos que llegan de tiro libre"),
    ("pct_pts_paint", "% de los puntos en la pintura"),
    ("pct_pts_fastbreak", "% de los puntos al contraataque"),
    ("dunk_rate", "Mates / tiros de 2 intentados"),
]:
    _add(_n, "tiro", _d)

# --------------------------------------------------------------------------------------
# 4. Ratios y porcentajes avanzados (fórmulas Basketball-Reference / Dean Oliver)
# --------------------------------------------------------------------------------------
for _n, _d in [
    ("min_pct", "% de los minutos disponibles del equipo que juega"),
    ("usg_pct", "USG%: % de posesiones del equipo que usa en pista"),
    ("ast_pct", "AST%: % de canastas de compañeros asistidas en pista"),
    ("tov_pct", "TOV%: pérdidas por cada 100 jugadas propias"),
    ("oreb_pct", "OREB%: % de rebotes ofensivos disponibles capturados"),
    ("dreb_pct", "DREB%: % de rebotes defensivos disponibles capturados"),
    ("reb_pct", "REB%: % de rebotes totales disponibles capturados"),
    ("stl_pct", "STL%: % de posesiones rivales que acaban en robo suyo"),
    ("blk_pct", "BLK%: % de tiros de 2 rivales que tapona"),
    ("ast_to", "Asistencias / pérdidas"),
    ("ast_ratio", "AST ratio: asistencias por cada 100 jugadas propias"),
    ("tov_ratio", "TOV ratio (Hollinger): pérdidas por cada 100 jugadas propias"),
    ("stl_to_tov", "Robos / pérdidas"),
    ("blk_to_pf", "Tapones / faltas"),
    ("stl_plus_blk_p40", "Robos + tapones por 40 minutos"),
    ("pfd_to_pf", "Faltas recibidas / faltas cometidas"),
    ("pts_share", "% de los puntos del equipo"),
    ("reb_share", "% de los rebotes del equipo"),
    ("ast_share", "% de las asistencias del equipo"),
    ("fga_share", "% de los tiros de campo del equipo"),
    ("poss_on_court", "Posesiones estimadas del equipo con el jugador en pista"),
    ("poss_used", "Posesiones usadas: FGA + 0.44*FTA + TOV"),
]:
    _add(_n, "ratios", _d)

# --------------------------------------------------------------------------------------
# 5. Ratings / índices compuestos
# --------------------------------------------------------------------------------------
for _n, _d in [
    ("game_score", "Game Score (Hollinger) acumulado"),
    ("game_score_pg", "Game Score por partido"),
    ("game_score_p40", "Game Score por 40 minutos"),
    ("eff", "EFF (NBA): PTS+REB+AST+STL+BLK-fallos-TOV, acumulado"),
    ("eff_pg", "EFF por partido"),
    ("pir_calc", "PIR calculado con la fórmula Euroliga (comprobación de 'pir')"),
    ("pie", "PIE: impacto del jugador sobre el total del partido (equipo + rival)"),
    ("uper", "PER sin ajustar (uPER, Hollinger)"),
    ("per", "PER ajustado al ritmo y normalizado a media de liga = 15"),
    ("ortg", "Rating ofensivo individual (Dean Oliver): puntos producidos /100 posesiones"),
    ("drtg", "Rating defensivo individual (Dean Oliver): puntos permitidos /100 posesiones"),
    ("net_rtg", "ortg - drtg"),
    ("floor_pct", "Floor%: % de posesiones propias que acaban en anotación"),
    ("pprod", "Puntos producidos (Dean Oliver)"),
    ("scposs", "Posesiones anotadoras (Dean Oliver)"),
    ("totposs", "Posesiones individuales totales (Dean Oliver)"),
    ("stops", "Stops defensivos (Dean Oliver)"),
    ("stop_pct", "Stop%: % de posesiones rivales detenidas"),
    ("ows", "Offensive Win Shares"),
    ("dws", "Defensive Win Shares"),
    ("ws", "Win Shares totales"),
    ("ws_per_40", "Win Shares por 40 minutos"),
    ("ws_per_48", "Win Shares por 48 minutos"),
]:
    _add(_n, "ratings", _d)

# --------------------------------------------------------------------------------------
# 6. Contexto de equipo / rival / liga (para que puedas aplicar tus propios algoritmos)
# --------------------------------------------------------------------------------------
TEAM_STATS = ["gp", "w", "l", "min", "pts", "fgm", "fga", "fg2m", "fg2a", "fg3m", "fg3a",
              "ftm", "fta", "oreb", "dreb", "reb", "ast", "stl", "tov", "blk", "pf"]
for _n in TEAM_STATS:
    _add(f"team_{_n}", "contexto_equipo", f"Equipo: {_n} (totales de temporada)", "contexto")
for _n in TEAM_STATS:
    if _n in {"gp", "w", "l"}:
        continue
    _add(f"opp_{_n}", "contexto_rival", f"Rivales del equipo: {_n} (totales de temporada)", "contexto")
for _n, _d in [
    ("team_poss", "Posesiones del equipo en la temporada"),
    ("opp_poss", "Posesiones de los rivales"),
    ("team_pace", "Ritmo del equipo (posesiones por partido reglamentario)"),
    ("team_ortg", "Puntos del equipo por 100 posesiones"),
    ("team_drtg", "Puntos permitidos por 100 posesiones"),
    ("team_netrtg", "team_ortg - team_drtg"),
    ("lg_pace", "Ritmo medio de la liga"),
    ("lg_ortg", "Puntos por 100 posesiones de la liga"),
    ("lg_pts_per_game", "Puntos por partido y equipo en la liga"),
]:
    _add(_n, "contexto_liga", _d, "calculado")

# --------------------------------------------------------------------------------------
# 7. Métricas publicadas por la fuente (oficiales). Vacías en ligas que no las miden.
# --------------------------------------------------------------------------------------
SOURCE_METRICS: list[tuple[str, str]] = [
    ("src_ortg", "Rating ofensivo oficial de la fuente"),
    ("src_drtg", "Rating defensivo oficial de la fuente"),
    ("src_netrtg", "Net rating oficial"),
    ("src_pace", "Ritmo oficial con el jugador en pista"),
    ("src_poss", "Posesiones oficiales"),
    ("src_pie", "PIE oficial (NBA)"),
    ("src_usg_pct", "USG% oficial"),
    ("src_ts_pct", "TS% oficial"),
    ("src_efg_pct", "eFG% oficial"),
    ("src_ast_pct", "AST% oficial"),
    ("src_ast_ratio", "AST ratio oficial"),
    ("src_tov_ratio", "TOV ratio / TOV% oficial"),
    ("src_oreb_pct", "OREB% oficial"),
    ("src_dreb_pct", "DREB% oficial"),
    ("src_reb_pct", "REB% oficial"),
    ("src_fta_rate", "Free throw rate oficial"),
    ("src_fg3a_rate", "3PA rate oficial"),
    ("src_def_ws", "Defensive win shares oficiales (NBA)"),
    ("src_pct_fga_2pt", "% FGA de 2 (oficial)"),
    ("src_pct_fga_3pt", "% FGA de 3 (oficial)"),
    ("src_pct_pts_mid", "% puntos de media distancia"),
    ("src_pct_ast_fgm", "% canastas asistidas"),
    ("src_pct_uast_fgm", "% canastas no asistidas"),
    ("src_pct_ast_3pm", "% triples asistidos"),
    ("src_pct_uast_2pm", "% canastas de 2 no asistidas"),
    ("src_fantasy_pts", "Puntos fantasy oficiales"),
    ("src_contested_shots", "Tiros rivales defendidos (hustle)"),
    ("src_contested_shots_3pt", "Triples rivales defendidos (hustle)"),
    ("src_deflections", "Desvíos (hustle)"),
    ("src_charges_drawn", "Faltas en ataque provocadas (hustle)"),
    ("src_screen_assists", "Bloqueos que acaban en canasta (hustle)"),
    ("src_screen_ast_pts", "Puntos tras bloqueo (hustle)"),
    ("src_loose_balls", "Balones sueltos recuperados (hustle)"),
    ("src_box_outs", "Bloqueos de rebote (hustle)"),
    ("src_dist_miles", "Distancia recorrida en millas (tracking)"),
    ("src_avg_speed", "Velocidad media (tracking)"),
    ("src_touches", "Toques de balón (tracking)"),
    ("src_time_of_poss", "Tiempo de posesión en minutos (tracking)"),
    ("src_drives", "Penetraciones (tracking)"),
    ("src_drive_pts", "Puntos tras penetración (tracking)"),
    ("src_passes_made", "Pases realizados (tracking)"),
    ("src_potential_ast", "Asistencias potenciales (tracking)"),
    ("src_secondary_ast", "Asistencias secundarias (tracking)"),
    ("src_ft_ast", "Asistencias a tiro libre (tracking)"),
    ("src_ast_pts_created", "Puntos creados con asistencias (tracking)"),
    ("src_catch_shoot_fgm", "Catch & shoot anotados (tracking)"),
    ("src_catch_shoot_fga", "Catch & shoot intentados (tracking)"),
    ("src_catch_shoot_pts", "Puntos en catch & shoot (tracking)"),
    ("src_pull_up_fgm", "Tiros tras bote anotados (tracking)"),
    ("src_pull_up_fga", "Tiros tras bote intentados (tracking)"),
    ("src_pull_up_pts", "Puntos en tiros tras bote (tracking)"),
    ("src_paint_touches", "Toques en la pintura (tracking)"),
    ("src_post_touches", "Toques en el poste (tracking)"),
    ("src_elbow_touches", "Toques en el codo (tracking)"),
    # Basketball-Reference (NBA)
    ("src_per", "PER oficial de Basketball-Reference"),
    ("src_ows", "Offensive Win Shares (Basketball-Reference)"),
    ("src_dws", "Defensive Win Shares (Basketball-Reference)"),
    ("src_ws", "Win Shares (Basketball-Reference)"),
    ("src_ws48", "Win Shares por 48 minutos (Basketball-Reference)"),
    ("src_obpm", "Offensive Box Plus/Minus"),
    ("src_dbpm", "Defensive Box Plus/Minus"),
    ("src_bpm", "Box Plus/Minus"),
    ("src_vorp", "Value Over Replacement Player"),
    ("src_stl_pct", "STL% oficial"),
    ("src_blk_pct", "BLK% oficial"),
    ("src_pos_pg_pct", "% de minutos como base (estimado jugada a jugada)"),
    ("src_pos_sg_pct", "% de minutos como escolta"),
    ("src_pos_sf_pct", "% de minutos como alero"),
    ("src_pos_pf_pct", "% de minutos como ala-pívot"),
    ("src_pos_c_pct", "% de minutos como pívot"),
    ("src_on_court_pm100", "+/- del equipo por 100 posesiones con él en pista"),
    ("src_on_off_pm100", "+/- on-off por 100 posesiones"),
    ("src_tov_bad_pass", "Pérdidas por mal pase"),
    ("src_tov_lost_ball", "Pérdidas de balón en bote/manejo"),
    ("src_fouls_shooting", "Faltas personales en tiro cometidas"),
    ("src_fouls_offensive", "Faltas en ataque cometidas"),
    ("src_drawn_shooting", "Faltas en tiro recibidas"),
    ("src_drawn_offensive", "Faltas en ataque provocadas"),
    ("src_astd_pts", "Puntos generados con sus asistencias"),
    ("src_and1", "Jugadas de 2+1 / 3+1"),
    ("src_avg_shot_dist", "Distancia media de tiro (pies)"),
    ("src_pct_fga_00_03", "% FGA a 0-3 pies"),
    ("src_pct_fga_03_10", "% FGA a 3-10 pies"),
    ("src_pct_fga_10_16", "% FGA a 10-16 pies"),
    ("src_pct_fga_16_3p", "% FGA de 16 pies a la línea de 3"),
    ("src_fg_pct_00_03", "FG% a 0-3 pies"),
    ("src_fg_pct_03_10", "FG% a 3-10 pies"),
    ("src_fg_pct_10_16", "FG% a 10-16 pies"),
    ("src_fg_pct_16_3p", "FG% de 16 pies a la línea de 3"),
    ("src_pct_ast_fg2", "% de canastas de 2 asistidas"),
    ("src_pct_ast_fg3", "% de triples asistidos"),
    ("src_pct_fga_dunk", "% de FGA que son mates"),
    ("src_pct_fg3a_corner", "% de triples desde la esquina"),
    ("src_fg3_pct_corner", "3P% desde la esquina"),
    # Otras ligas
    ("src_eff", "Valoración / eficiencia publicada por la liga"),
    ("src_oer", "Offensive efficiency rating publicado por la liga (LBA)"),
]
for _n, _d in SOURCE_METRICS:
    _add(_n, "metricas_fuente", _d, "fuente")
SOURCE_METRIC_NAMES = [c for c, _ in SOURCE_METRICS]

# --------------------------------------------------------------------------------------
# 8. BasketNews (on/off, ratings individuales, stops...). Sólo EuroLeague y Liga Endesa.
# --------------------------------------------------------------------------------------
from .enrich.basketnews import BN_COLUMNS  # noqa: E402

for _n, _d in BN_COLUMNS:
    _add(_n, "basketnews", _d, "fuente")
BN_COLUMN_NAMES = [c for c, _ in BN_COLUMNS]

# --------------------------------------------------------------------------------------
# 9. Contexto de fase: en las filas de playoffs, valor en temporada regular y diferencia.
# --------------------------------------------------------------------------------------
PHASES = ["regular", "playoffs", "total"]
PHASE_CONTEXT_METRICS = ["gp", "min_pg", "pts_pg", "pts_p40", "reb_p40", "ast_p40", "ts_pct", "efg_pct",
                         "usg_pct", "ast_pct", "tov_pct", "reb_pct", "per", "ortg", "drtg", "net_rtg",
                         "game_score_pg", "pir_pg", "ws_per_40", "pie", "bn_netrtg_onoff"]
for _n in PHASE_CONTEXT_METRICS:
    _add(f"rs_{_n}", "contexto_fase", f"{_n} del mismo jugador y equipo en la temporada regular "
                                      f"(sólo filas de playoffs)", "calculado")
for _n in PHASE_CONTEXT_METRICS:
    if _n == "gp":
        continue
    _add(f"delta_{_n}", "contexto_fase", f"{_n} en playoffs menos {_n} en temporada regular", "calculado")

COLUMNS: list[Column] = list(_COLS)
COLUMN_NAMES: list[str] = [c.name for c in COLUMNS]
IDENTITY_NAMES: list[str] = [c.name for c in COLUMNS if c.group == "identidad"]

assert len(COLUMN_NAMES) == len(set(COLUMN_NAMES)), "Columnas duplicadas en el esquema"


def dictionary_records() -> list[dict]:
    return [{"columna": c.name, "grupo": c.group, "origen": c.origin, "descripcion": c.description}
            for c in COLUMNS]
