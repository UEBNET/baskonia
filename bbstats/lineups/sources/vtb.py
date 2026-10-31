"""VTB United League: jugada a jugada del bruto principal (bbstats/adapters/vtb.py, Infobasket GetOnline),
traducido al formato del data.json de FIBA LiveStats (`to_fls`) y leído con la misma fuente que la BSL/GBL.
No hace peticiones. Los partidos sin OnlinePlays (2020-21 y 2021-22 hasta el 07-03-2022) salen sin quintetos
("la fuente no tiene jugada a jugada de este partido")."""
from __future__ import annotations

from ...adapters.vtb import to_fls
from .base import Ctx
from .fiba_livestats import FibaLiveStatsPBP, _games_of


class VtbPBP(FibaLiveStatsPBP):
    name = "vtb"
    version = "1.0"

    @staticmethod
    def _conv(ctx: Ctx) -> Ctx:
        p = ctx.main_payload if isinstance(ctx.main_payload, dict) else {}
        mover = bool((ctx.cfg or {}).get("cambios_tras_acciones"))
        games = {k: to_fls(v, mover) for k, v in _games_of(p).items() if isinstance(v, dict)}
        return Ctx(league=ctx.league, season=ctx.season, cfg=ctx.cfg, http=ctx.http,
                   main_payload={**p, "games": games}, errors=ctx.errors)

    def games(self, ctx: Ctx) -> list[dict]:
        ctx2 = self._conv(ctx)
        self._cache = ctx2.main_payload
        return super().games(ctx2)

    def fetch(self, ctx: Ctx, ref: dict) -> dict:
        p = getattr(self, "_cache", None) or self._conv(ctx).main_payload
        doc = _games_of(p).get(str(ref["game_id"]))
        if not doc:
            raise ValueError("partido ausente del bruto principal")
        return {"data": doc}


def docs_principal(main_payload, game_id: str) -> dict | None:
    """data.json (traducido) del partido sacado del bruto principal, para el registro de entrenadores
    (bbstats/entrenadores.py: Extractor(lector_fiba_livestats, ..., docs_principal=vtb.docs_principal))."""
    doc = _games_of(main_payload).get(str(game_id))
    return {"data": to_fls(doc)} if isinstance(doc, dict) else None
