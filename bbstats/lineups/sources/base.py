"""Contrato de las fuentes de jugada a jugada.

Una fuente hace tres cosas, separadas como los adaptadores principales (descargar ≠ interpretar):

  games(ctx)        -> lista de partidos de la temporada: [{"game_id", "phase", "final", "date", ...}]
                       (puede usar `ctx.main_payload`, el último bruto del adaptador principal, para no
                       repetir peticiones; "final" = partido terminado)
  fetch(ctx, ref)   -> documentos originales del partido, sin transformar (dict JSON-serializable).
                       Sólo se llama para partidos terminados que aún no estén en el bruto pbp.
  parse(raw, ref, ctx) -> bbstats.lineups.model.Game (sin red)

Las fuentes que ya tienen el jugada a jugada dentro del bruto principal (BBL) devuelven en fetch() lo
necesario a partir de ctx.main_payload sin hacer peticiones.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...http import HttpClient
from ..model import Game


@dataclass
class Ctx:
    league: str
    season: str
    cfg: dict                       # config de la liga (config/sources.json → ligas.<liga>)
    http: HttpClient | None = None
    main_payload: Any = None        # payload del último bruto del adaptador principal (o None)
    errors: list[str] = field(default_factory=list)

    @property
    def start_year(self) -> int:
        return int(self.season[:4])

    @property
    def game_min(self) -> float:
        from ...config import minutos_partido
        return minutos_partido(self.cfg, self.season)


class PBPSource:
    name = "base"
    version = "1.0"
    # True si el jugada a jugada ya viene dentro del bruto principal de la liga (BBL): no se descarga ni se
    # guarda un paquete pbp aparte; se lee de ahí en cada ejecución.
    uses_main_raw = False

    def games(self, ctx: Ctx) -> list[dict]:
        raise NotImplementedError

    def fetch(self, ctx: Ctx, ref: dict) -> dict:
        raise NotImplementedError

    def parse(self, raw: dict, ref: dict, ctx: Ctx) -> Game:
        raise NotImplementedError

    # Tablas oficiales opcionales (NBA / G League): {"nombre": rows} que se guardan en el bruto y se
    # escriben como CSV *_oficial. Por defecto, ninguna.
    def official(self, ctx: Ctx) -> dict[str, Any]:
        return {}

    def parse_official(self, raw: dict, ctx: Ctx) -> dict[str, list[dict]]:
        return {}
