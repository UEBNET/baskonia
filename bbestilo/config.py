"""Constantes: rasgos de estilo, capa de nivel, rutas e hiperparámetros."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIR_A = RAIZ / "data" / "modelos" / "algoritmo_A" / "traducciones"
DIR_B = RAIZ / "data" / "modelos" / "algoritmo_B" / "traducciones"
DIR_SALIDA = RAIZ / "data" / "modelos" / "estilos"
CLUBES = RAIZ / "config" / "clubes.json"

TEMPORADAS_ENTRENO = ["2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
# Temporada en curso: B no la traduce (sólo 4 filas), se usa A y se marca como provisional.
TEMPORADAS_PROVISIONALES = ["2026-27"]
MIN_CUOTA_ESTILO = 0.05   # un estilo reúne al menos el 5 % de los clubes (consenso de semillas)
N_ESTILOS = 6           # iteraciones anteriores (12 y 8 estilos): data/modelos/estilos/historial/
D_MAPA = 3
# Neutralización del nivel: a cada rasgo de estilo se le quita la parte que explica el índice de nivel
# (regresión en 1, nivel y nivel², ajustada sobre la vara común A+B de todas las ligas a la vez).
NEUTRALIZAR_NIVEL = True
GRADO_NEUTRALIZACION = 2
MIN_JUGADOR = 100        # minutos mínimos de una fila jugador-equipo para situarla en el mapa
MIN_ESCALA_JUGADOR = 150  # minutos mínimos para estimar la escala de los jugadores


@dataclass(frozen=True)
class Rasgo:
    col: str
    nombre: str
    bloque: str
    transf: str       # transformación aplicada DESPUÉS de agregar (igual que en bbmodel.metricas)
    origen: str       # "A+B" (estudio de normalización), "derivado A+B" o "contexto"
    corto: str = ""


# Vector de estilo. Todos se agregan de jugador a club como media ponderada por minutos (perfil
# medio de los cinco en pista), así que fichar o dar minutos a un jugador mueve al club de forma exacta.
RASGOS = [
    Rasgo("ritmo_rel", "Ritmo relativo a su liga", "Estructura", "id", "contexto", "Ritmo"),
    Rasgo("fg3a_rate", "Triples / tiros de campo (3PAr)", "Ataque", "id", "A+B", "3PAr"),
    Rasgo("fta_rate", "Tiros libres / tiros de campo (FTr)", "Ataque", "raiz", "A+B", "FTr"),
    Rasgo("ast_pct", "AST%", "Ataque", "log1", "A+B", "AST%"),
    Rasgo("tov_pct", "TOV%", "Ataque", "log1", "A+B", "TOV%"),
    Rasgo("oreb_p100", "Rebotes ofensivos por 100 pos.", "Ataque", "log1", "A+B", "Reb. of."),
    Rasgo("uso_conc", "Concentración del uso", "Estructura", "log1", "derivado A+B", "Uso concentrado"),
    Rasgo("dreb_p100", "Rebotes defensivos por 100 pos.", "Defensa", "log1", "A+B", "Reb. def."),
    Rasgo("stl_p100", "Robos por 100 pos.", "Defensa", "raiz", "A+B", "Robos"),
    Rasgo("blk_p100", "Tapones por 100 pos.", "Defensa", "raiz", "A+B", "Tapones"),
    Rasgo("pf_p100", "Faltas por 100 pos.", "Defensa", "raiz", "A+B", "Faltas"),
    Rasgo("cuota_interior", "Minutos de interiores (4-5)", "Estructura", "id", "derivado A+B", "Interiores"),
    Rasgo("cuota_exterior", "Minutos de exteriores (1-2)", "Estructura", "id", "derivado A+B", "Exteriores"),
    # jugada a jugada (bbmodel/pista.py, normalizados A+B como el resto): dónde tira y cómo llega a la canasta
    Rasgo("pct_aro", "% de tiros en el aro (< 1,8 m)", "Tiro", "proporcion", "A+B (jugada a jugada)", "Aro"),
    Rasgo("pct_media", "% de tiros de media distancia", "Tiro", "proporcion", "A+B (jugada a jugada)", "Media dist."),
    Rasgo("pct_t3_esquina", "% de tiros que son triples de esquina", "Tiro", "proporcion", "A+B (jugada a jugada)", "Triple esquina"),
    Rasgo("pct_asistidas", "% de canastas propias asistidas", "Ataque", "proporcion", "A+B (jugada a jugada)", "Asistidas"),
]
COLS = [r.col for r in RASGOS]
# Métricas normalizadas que entran en el vector (las demás columnas del vector se derivan).
METRICAS_ESTILO = ["fg3a_rate", "fta_rate", "ast_pct", "tov_pct", "oreb_p100", "dreb_p100", "stl_p100",
                   "blk_p100", "pf_p100", "usg_pct", "pct_aro", "pct_media", "pct_t3_esquina", "pct_asistidas"]
# Capa de NIVEL: miden cuánto se rinde, no cómo se juega. No definen los estilos; se muestran aparte.
# sentido: +1 más es mejor, -1 menos es mejor.
NIVEL = {"per": 1, "game_score_p40": 1, "ws_per_40": 1, "ortg": 1, "drtg": -1, "pts_p100": 1,
         "ts_pct": 1, "efg_pct": 1}

# Hiperparámetros comunes
SEMILLAS = [11, 23, 37, 51, 73, 89, 97, 113, 131, 149]   # v1-v3: las 5 primeras
BOOTSTRAP_POR_CLUB = 24     # plantillas remuestreadas por club-temporada para entrenar
K_GAMMA = 4.0               # forma de la Gamma del remuestreo de minutos (CV = 1/sqrt(k) = 0,5)
PESO_JUGADORES = 0.3        # peso de las muestras de jugador (auxiliares) en la pérdida
