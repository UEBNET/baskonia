"""Catálogo de métricas que traduce el algoritmo A.

Para cada métrica se fija:
  * col        columna del CSV de bbstats.
  * exposicion cuánta «evidencia» aporta cada fila: minutos, tiros, posesiones... Un 50 % en
               triples con 4 intentos vale menos que con 200; la exposición mide eso.
    * transf     transformación (elegida comparando la asimetría de cada opción en 2020-21..2025-26) que vuelve la métrica aproximadamente normal y con ruido estable:
               - "proporcion": arcoseno de la raíz de p (porcentajes 0-100). Estabiliza la varianza
                 de una proporción y admite ceros (pívots que no tiran triples).
               - "raiz": raíz cuadrada (conteos por 100 posesiones). Estabiliza la varianza de un
                 conteo tipo Poisson.
               - "log1": logaritmo de (x + 1) (tasas muy asimétricas: asistencias, rebote, pérdidas).
                 Un base con AST% 40 y otro con 30 se separan menos que un pívot con 8 y otro con 4.
               - "id": sin transformar (ratings que pueden ser negativos o ya son casi normales).
  * sentido    +1 más es mejor, -1 menos es mejor, 0 neutra (rol o estilo, no calidad).
  * grupo      para agrupar en informes.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# columna del CSV que mide la exposición de cada tipo
EXPOSICIONES = {"min": "min", "pos": "poss_on_court", "tsa": "tsa", "fga": "fga", "fg3a": "fg3a",
                "fg2a": "fg2a", "fta": "fta", "plays": "plays"}


@dataclass(frozen=True)
class Metrica:
    col: str
    nombre: str
    grupo: str
    exposicion: str
    transf: str
    sentido: int


_M = [
    # anotación y tiro
    Metrica("pts_p100", "Puntos por 100 posesiones", "Anotación", "pos", "raiz", 1),
    Metrica("ts_pct", "TS%", "Anotación", "tsa", "id", 1),
    Metrica("efg_pct", "eFG%", "Anotación", "fga", "id", 1),
    Metrica("fg2_pct", "T2%", "Anotación", "fg2a", "id", 1),
    Metrica("fg3_pct", "T3%", "Anotación", "fg3a", "id", 1),
    Metrica("ft_pct", "TL%", "Anotación", "fta", "proporcion", 1),
    Metrica("fg3a_rate", "Triples / tiros de campo (3PAr)", "Anotación", "fga", "id", 0),
    Metrica("fta_rate", "Tiros libres / tiros de campo (FTr)", "Anotación", "fga", "raiz", 1),
    # uso y creación
    Metrica("usg_pct", "USG%", "Uso y creación", "min", "proporcion", 0),
    Metrica("ast_pct", "AST%", "Uso y creación", "min", "log1", 1),
    Metrica("tov_pct", "TOV%", "Uso y creación", "plays", "log1", -1),
    # rebote
    Metrica("oreb_pct", "OREB%", "Rebote", "min", "log1", 1),
    Metrica("dreb_pct", "DREB%", "Rebote", "min", "log1", 1),
    Metrica("oreb_p100", "Rebotes ofensivos por 100 pos.", "Rebote", "pos", "log1", 1),
    Metrica("dreb_p100", "Rebotes defensivos por 100 pos.", "Rebote", "pos", "log1", 1),
    # defensa
    Metrica("stl_pct", "STL%", "Defensa", "min", "raiz", 1),
    Metrica("blk_pct", "BLK%", "Defensa", "min", "raiz", 1),
    Metrica("stl_p100", "Robos por 100 pos.", "Defensa", "pos", "raiz", 1),
    Metrica("blk_p100", "Tapones por 100 pos.", "Defensa", "pos", "raiz", 1),
    Metrica("pf_p100", "Faltas por 100 pos.", "Defensa", "pos", "raiz", -1),
    Metrica("drtg", "DRtg individual", "Defensa", "min", "id", -1),
    # valoración global
    Metrica("per", "PER", "Global", "min", "id", 1),
    Metrica("ortg", "ORtg individual", "Global", "min", "id", 1),
    Metrica("game_score_p40", "Game Score por 40'", "Global", "min", "id", 1),
    Metrica("ws_per_40", "Win Shares por 40'", "Global", "min", "id", 1),
]
# PIE no se incluye: es una cuota de los eventos de todo el partido (crece con los minutos), no una
# tasa, y no cumple el modelo de ruido «varianza ∝ 1/exposición».
CATALOGO: dict[str, Metrica] = {m.col: m for m in _M}


def transformar(x, transf: str):
    """Valor original -> escala de trabajo (aproximadamente normal)."""
    x = np.asarray(x, dtype=float)
    if transf == "proporcion":
        return np.arcsin(np.sqrt(np.clip(x, 0, 100) / 100.0))
    if transf == "raiz":
        return np.sqrt(np.clip(x, 0, None))
    if transf == "log1":
        return np.log1p(np.clip(x, 0, None))
    return x


def destransformar(y, transf: str):
    """Escala de trabajo -> valor original (inversa de transformar)."""
    y = np.asarray(y, dtype=float)
    if transf == "proporcion":
        return 100.0 * np.sin(np.clip(y, 0, np.pi / 2)) ** 2
    if transf == "raiz":
        return np.clip(y, 0, None) ** 2
    if transf == "log1":
        return np.expm1(np.clip(y, 0, None))
    return y
