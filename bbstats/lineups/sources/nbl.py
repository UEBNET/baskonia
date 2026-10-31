"""NBL (Australia): jugada a jugada del bruto principal (bbstats/adapters/nbl.py), traducido al formato del
data.json de FIBA LiveStats (`to_fls`) y leído con la misma fuente que la BSL/GBL. No hace peticiones."""
from __future__ import annotations

from ...adapters.nbl import to_fls
from .base import Ctx
from .fiba_livestats import FibaLiveStatsPBP, _games_of


class NblPBP(FibaLiveStatsPBP):
    name = "nbl"
    version = "1.0"

    @staticmethod
    def _conv(ctx: Ctx) -> Ctx:
        p = ctx.main_payload if isinstance(ctx.main_payload, dict) else {}
        games = {k: to_fls(v) for k, v in _games_of(p).items() if isinstance(v, dict)}
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
