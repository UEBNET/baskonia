"""Contrato común de los extractores (adaptadores) por fuente.

Cada adaptador hace DOS cosas separadas:
  1. fetch(): descarga y devuelve el payload ORIGINAL (JSON o HTML como texto), sin transformar.
     El pipeline lo guarda tal cual en el almacén bruto.
  2. parse(): a partir de ese payload (sin red) produce filas de jugador y de equipo con
     nombres de columna canónicos. Así se puede reprocesar sin volver a descargar.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..http import HttpClient


@dataclass
class ParsedLeague:
    """Resultado de parse().

    players: una fila por jugador-equipo con identidad, totales de conteo y src_* (si existen).
    teams:   una fila por equipo con team_<stat> y opp_<stat> (totales de temporada).
    """
    players: list[dict]
    teams: list[dict]
    notes: list[str] = field(default_factory=list)


class AdapterError(RuntimeError):
    pass


class NoDataYet(AdapterError):
    """La temporada/competición todavía no tiene datos publicados (no es un error)."""


class BaseAdapter(ABC):
    name: str = "base"
    version: str = "1.0"

    def __init__(self, league: str, cfg: dict) -> None:
        self.league = league
        self.cfg = cfg
        self.errors: list[str] = []  # errores no fatales durante fetch (se guardan en meta)
        # Valores descubiertos durante fetch que conviene guardar en config/sources.json para
        # la liga (p.ej. ids semilla de la BBL). El pipeline los aplica tras una descarga correcta.
        self.config_updates: dict = {}

    # ---------------------------------------------------------------- temporada
    def season_cfg(self, season: str) -> dict:
        """Parámetros específicos de temporada (config 'temporadas') con valores por defecto."""
        base = {"start_year": int(season[:4])}
        base.update((self.cfg.get("temporadas") or {}).get(season, {}))
        return base

    @property
    def source_url(self) -> str:
        return self.cfg.get("fuente") or self.cfg.get("base_url") or ""

    # ---------------------------------------------------------------- contrato
    @abstractmethod
    def fetch(self, season: str, http: HttpClient, previous_payload: Any | None = None) -> Any:
        """Descarga los datos originales. `previous_payload` = último bruto (para reutilizar
        partidos ya finalizados y no volver a descargarlos)."""

    @abstractmethod
    def parse(self, payload: Any, season: str) -> "dict[str, ParsedLeague] | ParsedLeague":
        """Convierte el payload original a filas canónicas por fase ('regular', 'playoffs', 'total'
        u otras). No accede a la red. Devolver un único ParsedLeague equivale a {'total': ...}."""

    # ---------------------------------------------------------------- helpers
    def soft_fail(self, msg: str) -> None:
        self.errors.append(msg)
