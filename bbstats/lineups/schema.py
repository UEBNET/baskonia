"""Columnas de los ficheros de quintetos y conexiones (idénticas en todas las ligas) y su descripción."""
from __future__ import annotations

ID_UNIT = [("liga", "Código de liga"), ("temporada", "Temporada"), ("fase", "regular | playoffs | total"),
           ("team_id", "Id del equipo (mismo que en los datos de jugadores)"), ("equipo", "Equipo"),
           ("unidad", "Ids de los jugadores de la unidad, ordenados y separados por |"),
           ("jugadores", "Nombres de los jugadores de la unidad"), ("n_jugadores", "Jugadores de la unidad (5, 3 o 2)")]

RATES = [
    ("gp", "Partidos en los que la unidad estuvo en pista"), ("tramos", "Tramos (intervalos sin cambios) jugados"),
    ("min", "Minutos juntos en pista"), ("min_pct_equipo", "% de los minutos del equipo"),
    ("min_clutch", "Minutos en clutch (últimos 5 min del último cuarto o prórroga, ±5 puntos)"),
    ("min_basura", "Minutos de la basura (4.º cuarto, ≤ 2 titulares en pista y diferencia ≥ 25/20/10 según el reloj)"),
    ("poss_of", "Posesiones ofensivas estimadas (TCI − RO + PER + c·TLI)"), ("poss_def", "Posesiones defensivas"),
    ("poss", "Posesiones (media de ataque y defensa)"),
    ("pts_for", "Puntos a favor"), ("pts_against", "Puntos en contra"), ("plus_minus", "+/-"),
    ("pm_por40", "+/- por 40 minutos"),
    ("ortg", "Rating ofensivo: puntos por 100 posesiones"), ("drtg", "Rating defensivo: puntos permitidos por 100 posesiones"),
    ("net_rtg", "Rating neto (ORtg − DRtg)"),
    ("ortg_aj", "ORtg ajustado por muestra (contracción bayesiana hacia la media de la liga, k posesiones)"),
    ("drtg_aj", "DRtg ajustado por muestra"), ("net_rtg_aj", "Net ajustado por muestra (comparable entre unidades con pocos minutos)"),
    ("drtg_suerte", "DRtg ajustado por suerte: % de triples y de tiros libres del rival sustituidos por la media de la liga"),
    ("net_rtg_suerte", "Net ajustado por suerte (ORtg − DRtg_suerte)"),
    ("net_rtg_suerte_aj", "Net ajustado por suerte y por muestra"),
    ("ritmo", "Posesiones por partido completo (40 o 48 minutos)"),
    ("efg_pct", "eFG% a favor"), ("opp_efg_pct", "eFG% del rival"), ("ts_pct", "TS% a favor"), ("opp_ts_pct", "TS% del rival"),
    ("tov_pct", "Pérdidas por 100 jugadas"), ("opp_tov_pct", "Pérdidas forzadas al rival por 100 jugadas"),
    ("oreb_pct", "% de rebote ofensivo"), ("dreb_pct", "% de rebote defensivo"),
    ("ft_rate", "Tiros libres intentados por cada 100 tiros de campo"), ("opp_ft_rate", "FTr del rival"),
    ("fg3a_rate", "% de tiros de campo que son triples"), ("opp_fg3a_rate", "3PAr del rival"),
    ("fg2_pct", "T2%"), ("opp_fg2_pct", "T2% del rival"), ("fg3_pct", "T3%"), ("opp_fg3_pct", "T3% del rival"),
    ("ft_pct", "TL%"), ("opp_ft_pct", "TL% del rival"),
    ("ast_pct", "% de canastas asistidas"), ("opp_ast_pct", "% de canastas asistidas del rival"),
    ("stl_pct", "Robos por 100 posesiones del rival"), ("blk_pct", "Tapones por cada 100 tiros de 2 del rival"),
    ("pf_por100", "Faltas cometidas por 100 posesiones del rival"), ("opp_pf_por100", "Faltas recibidas por 100 posesiones propias"),
]

LINEUP_EXTRA = [("rapm_suma", "Suma del RAPM de los 5 jugadores"),
                ("net_esperado", "Net esperado según el RAPM: Σ RAPM propios − Σ RAPM de los rivales que tuvo enfrente "
                                 "(ponderado por posesiones)"),
                ("sinergia", "(Net − Net esperado) contraído hacia 0 por la muestra: poss/(poss+k)·(Net − esperado). "
                             "> 0 = el quinteto rinde más que la suma de sus jugadores")]

PAIR_EXTRA = [("jugador_a_id", "Id jugador A"), ("jugador_a", "Jugador A"), ("jugador_b_id", "Id jugador B"),
              ("jugador_b", "Jugador B"),
              ("min_a_sin_b", "Minutos de A sin B"), ("net_rtg_a_sin_b", "Net de A sin B"), ("net_rtg_aj_a_sin_b", "Net_aj de A sin B"),
              ("min_b_sin_a", "Minutos de B sin A"), ("net_rtg_b_sin_a", "Net de B sin A"), ("net_rtg_aj_b_sin_a", "Net_aj de B sin A"),
              ("min_ninguno", "Minutos del equipo sin ninguno de los dos"), ("net_rtg_ninguno", "Net sin ninguno"),
              ("net_rtg_aj_ninguno", "Net_aj sin ninguno"),
              ("sinergia", "Net_aj juntos − (Net_aj A sin B + Net_aj B sin A − Net_aj ninguno): > 0 = se potencian"),
              ("pct_min_a_con_b", "% de los minutos de A que juega con B"),
              ("pct_min_b_con_a", "% de los minutos de B que juega con A"),
              ("net_esperado", "Net esperado según el RAPM de los 10 jugadores en pista cuando la pareja está junta"),
              ("sinergia_rapm", "Sinergia frente al RAPM: poss/(poss+k)·(Net − Net esperado)"),
              ("ast_a_a_b", "Asistencias de A a B"), ("ast_b_a_a", "Asistencias de B a A"),
              ("ast_por40_juntos", "Asistencias entre ambos por 40 minutos juntos")]

TRIO_EXTRA = [("net_esperado", "Net esperado según el RAPM de los 10 jugadores en pista cuando el trío está junto"),
              ("sinergia_rapm", "Sinergia frente al RAPM: poss/(poss+k)·(Net − Net esperado)")]

LINEUP_COLS = ID_UNIT + RATES + LINEUP_EXTRA
TRIO_COLS = ID_UNIT + RATES + TRIO_EXTRA
PAIR_COLS = ID_UNIT[:6] + PAIR_EXTRA[:4] + RATES + PAIR_EXTRA[4:]

ONOFF_BASE = ["min", "poss", "pts_for", "pts_against", "plus_minus", "pm_por40", "ortg", "drtg", "net_rtg",
               "ortg_aj", "drtg_aj", "net_rtg_aj", "net_rtg_suerte", "net_rtg_suerte_aj", "ritmo", "efg_pct", "opp_efg_pct", "ts_pct", "opp_ts_pct",
               "tov_pct", "opp_tov_pct", "oreb_pct", "dreb_pct", "ft_rate", "opp_ft_rate", "fg3a_rate",
               "opp_fg3a_rate", "ast_pct"]
ONOFF_DIFF = ["ortg", "drtg", "net_rtg", "net_rtg_aj", "net_rtg_suerte", "net_rtg_suerte_aj", "ritmo", "efg_pct", "opp_efg_pct", "ts_pct", "opp_ts_pct",
               "tov_pct", "opp_tov_pct", "oreb_pct", "dreb_pct", "ft_rate", "opp_ft_rate", "fg3a_rate", "ast_pct"]
_RATE_DESC = dict(RATES)

PLAYER_COLS = ([("liga", "Código de liga"), ("temporada", "Temporada"), ("fase", "regular | playoffs | total"),
                ("team_id", "Id del equipo"), ("equipo", "Equipo"), ("player_id", "Id del jugador (mismo que en los datos de jugadores)"),
                ("nombre", "Jugador"), ("gp", "Partidos con minutos en el jugada a jugada"), ("tramos", "Tramos jugados"),
                ("min_pct_equipo", "% de los minutos del equipo en pista"),
                ("quintetos_distintos", "Quintetos distintos en los que ha jugado"),
                ("titular_partidos", "Partidos en el quinteto inicial (según el jugada a jugada)"),
                ("cierra_partidos", "Partidos en pista en el último tramo del partido"),
                ("relevos", "Veces que entra a pista (relevos o turnos)"),
                ("relevos_por_partido", "Relevos por partido"), ("min_por_partido", "Minutos por partido"),
                ("min_por_relevo", "Duración media de cada relevo (minutos)"),
                ("pct_min_q1", "% de sus minutos en el 1.er cuarto"), ("pct_min_q2", "% en el 2.º cuarto"),
                ("pct_min_q3", "% en el 3.er cuarto"), ("pct_min_q4", "% en el 4.º cuarto"),
                ("pct_min_prorroga", "% en prórrogas")]
               + [(f"{c}_on", f"Con el jugador en pista: {_RATE_DESC.get(c, c)}") for c in ONOFF_BASE]
               + [(f"{c}_off", f"Con el jugador en el banquillo: {_RATE_DESC.get(c, c)}") for c in ONOFF_BASE]
               + [(f"{c}_onoff", f"On − Off: {_RATE_DESC.get(c, c)}") for c in ONOFF_DIFF]
               + [("clutch_min", "Minutos en clutch (últimos 5 min del último cuarto o prórroga, ±5 puntos)"),
                  ("basura_min", "Minutos de la basura"),
                  ("net_rtg_on_sin_basura", "Net en pista sin minutos de la basura"),
                  ("net_rtg_onoff_sin_basura", "On − Off del Net sin minutos de la basura"),
                  ("net_rtg_aj_onoff_sin_basura", "On − Off del Net_aj sin minutos de la basura"),
                  ("clutch_plus_minus", "+/- en clutch"), ("clutch_net_rtg", "Net en clutch"), ("clutch_net_rtg_aj", "Net_aj en clutch"),
                  ("orapm", "RAPM ofensivo (puntos por 100 posesiones sobre la media, ajustado por compañeros y rivales)"),
                  ("drapm", "RAPM defensivo (> 0 = mejor defensa)"), ("rapm", "RAPM total (ORAPM + DRAPM)"),
                  ("rapm_poss", "Posesiones ofensivas en la regresión RAPM"),
                  ("ast_dadas", "Asistencias dadas (jugada a jugada)"), ("ast_recibidas", "Canastas propias asistidas"),
                  ("pct_canastas_asistidas", "% de sus canastas que fueron asistidas"),
                  ("pts_generados_asist", "Puntos generados con sus asistencias"),
                  ("socios_asistencia", "Compañeros distintos a los que asiste"),
                  ("socios_asistido_por", "Compañeros distintos que le asisten"),
                  ("hhi_asistencias", "Concentración de sus asistencias (HHI 0–10.000; alto = siempre al mismo)"),
                  ("receptor_principal", "Compañero al que más asiste"), ("asistente_principal", "Compañero que más le asiste"),
                  ("pagerank_asistencias", "Centralidad PageRank en la red de asistencias de su equipo")])

ASSIST_COLS = [("liga", "Código de liga"), ("temporada", "Temporada"), ("fase", "regular | playoffs | total"),
               ("team_id", "Id del equipo"), ("equipo", "Equipo"), ("pasador_id", "Id del pasador"), ("pasador", "Pasador"),
               ("receptor_id", "Id del anotador"), ("receptor", "Anotador"), ("gp", "Partidos con al menos una asistencia"),
               ("ast", "Asistencias del pasador al anotador"), ("ast_2", "…en canastas de 2"), ("ast_3", "…en triples"),
               ("ast_tl", "…en tiros libres (si la fuente las registra)"), ("pts_asistidos", "Puntos generados"),
               ("pct_ast_pasador", "% de las asistencias del pasador que van a este anotador"),
               ("pct_asistidas_receptor", "% de las canastas asistidas del anotador que vienen de este pasador"),
               ("min_juntos", "Minutos juntos en pista"), ("ast_por40_juntos", "Asistencias por 40 minutos juntos")]

TEAM_COLS = [("liga", "Código de liga"), ("temporada", "Temporada"), ("fase", "regular | playoffs | total"),
             ("team_id", "Id del equipo"), ("equipo", "Equipo"), ("gp", "Partidos con quintetos"),
             ("min", "Minutos"), ("poss", "Posesiones"), ("ortg", "Rating ofensivo"), ("drtg", "Rating defensivo"),
             ("net_rtg", "Rating neto"), ("net_rtg_aj", "Net ajustado por muestra"),
             ("drtg_suerte", "DRtg ajustado por suerte"), ("net_rtg_suerte", "Net ajustado por suerte"),
             ("ritmo", "Posesiones por partido"), ("efg_pct", "eFG%"), ("opp_efg_pct", "eFG% del rival"),
             ("tov_pct", "TOV%"), ("opp_tov_pct", "TOV% del rival"), ("oreb_pct", "OREB%"), ("dreb_pct", "DREB%"),
             ("ft_rate", "FTr"), ("opp_ft_rate", "FTr del rival"),
             ("min_clutch", "Minutos en clutch"), ("clutch_net_rtg", "Net en clutch"),
             ("min_basura", "Minutos de la basura"),
             ("quintetos_distintos", "Quintetos distintos utilizados"),
             ("quintetos_100_poss", "Quintetos con ≥ 100 posesiones"),
             ("quinteto_principal", "Quinteto con más minutos"),
             ("min_pct_quinteto_principal", "% de los minutos del equipo del quinteto principal"),
             ("net_rtg_quinteto_principal", "Net del quinteto principal"),
             ("min_pct_top5_quintetos", "% de los minutos de los 5 quintetos más usados (estabilidad)"),
             ("quinteto_titular_habitual", "Quinteto inicial más repetido"),
             ("partidos_quinteto_titular", "Partidos que salió el quinteto inicial habitual"),
             ("quintetos_titulares_distintos", "Quintetos iniciales distintos"),
             ("net_rtg_quinteto_titular", "Net del quinteto inicial habitual"),
             ("jugadores_usados", "Jugadores con minutos"),
             ("jugadores_rotacion", "Jugadores con ≥ 25 % de los minutos del equipo"),
             ("hhi_minutos", "Concentración de los minutos (HHI 0–10.000; 2.000 = 5 jugadores con todo)"),
             ("hhi_pagerank_asistencias", "Concentración de la red de asistencias (HHI del PageRank; alto = juego "
                                          "centralizado en pocos jugadores)")]

SHOT_COLS = ["liga", "temporada", "fase", "game_id", "periodo", "t", "team_id", "player_id", "nombre", "tipo", "anotado",
             "puntos", "asistente_id", "asistente", "x", "y", "quinteto", "quinteto_rival", "margen_previo"]

FILES = {"quintetos": LINEUP_COLS, "trios": TRIO_COLS, "parejas": PAIR_COLS, "jugadores": PLAYER_COLS,
         "asistencias": ASSIST_COLS, "equipos": TEAM_COLS}


def dictionary_records() -> list[dict]:
    out = []
    for f, cols in FILES.items():
        for c, d in cols:
            out.append({"fichero": f, "columna": c, "descripcion": d})
    return out
