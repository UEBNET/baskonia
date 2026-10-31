"""Registro de adaptadores. Para añadir una fuente nueva:
1. Crea una clase que herede de BaseAdapter (fetch + parse).
2. Regístrala aquí en ADAPTERS.
3. Añade la liga en config/sources.json con "adaptador": "<nombre>".
"""
from __future__ import annotations

from .acb import ACBAdapter
from .bref_nba import BRefNBAAdapter
from .bbl import BBLAdapter
from .base import AdapterError, BaseAdapter, NoDataYet, ParsedLeague
from .euroleague import EuroleagueAdapter
from .feb import FebAdapter
from .fiba_livestats import FibaLiveStatsAdapter
from .fiba_web import FibaWebAdapter
from .html_table import HtmlTableAdapter
from .lba import LBAAdapter
from .lnb import LNBAdapter
from .nba import GLeagueAdapter, NBAAdapter
from .nbl import NBLAdapter
from .ncaa import NCAAAdapter
from .vtb import VTBAdapter

ADAPTERS: dict[str, type[BaseAdapter]] = {
    "euroleague": EuroleagueAdapter,
    "nba": NBAAdapter,
    "gleague": GLeagueAdapter,
    "acb": ACBAdapter,
    "fiba_livestats": FibaLiveStatsAdapter,
    "fiba_web": FibaWebAdapter,
    "feb": FebAdapter,
    "html_table": HtmlTableAdapter,
    "bref_nba": BRefNBAAdapter,
    "lba": LBAAdapter,
    "bbl": BBLAdapter,
    "lnb": LNBAdapter,
    "nbl": NBLAdapter,
    "ncaa": NCAAAdapter,
    "vtb": VTBAdapter,
}


def build_adapter(league: str, cfg: dict) -> BaseAdapter:
    name = cfg.get("adaptador", league)
    if name not in ADAPTERS:
        raise AdapterError(f"Adaptador desconocido '{name}' para la liga '{league}'")
    return ADAPTERS[name](league, cfg)


__all__ = ["ADAPTERS", "AdapterError", "BaseAdapter", "NoDataYet", "ParsedLeague", "build_adapter"]
