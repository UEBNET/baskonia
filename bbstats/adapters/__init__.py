"""Registro de adaptadores. Para añadir una fuente nueva:
1. Crea una clase que herede de BaseAdapter (fetch + parse).
2. Regístrala aquí en ADAPTERS.
3. Añade la liga en config/sources.json con "adaptador": "<nombre>".
"""
from __future__ import annotations

from .acb import ACBAdapter
from .base import AdapterError, BaseAdapter, ParsedLeague
from .euroleague import EuroleagueAdapter
from .fiba_livestats import FibaLiveStatsAdapter
from .html_table import HtmlTableAdapter
from .nba import GLeagueAdapter, NBAAdapter

ADAPTERS: dict[str, type[BaseAdapter]] = {
    "euroleague": EuroleagueAdapter,
    "nba": NBAAdapter,
    "gleague": GLeagueAdapter,
    "acb": ACBAdapter,
    "fiba_livestats": FibaLiveStatsAdapter,
    "html_table": HtmlTableAdapter,
}


def build_adapter(league: str, cfg: dict) -> BaseAdapter:
    name = cfg.get("adaptador", league)
    if name not in ADAPTERS:
        raise AdapterError(f"Adaptador desconocido '{name}' para la liga '{league}'")
    return ADAPTERS[name](league, cfg)


__all__ = ["ADAPTERS", "AdapterError", "BaseAdapter", "ParsedLeague", "build_adapter"]
