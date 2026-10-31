"""CBA: jugada a jugada de QQ guardado en el bruto principal (bbstats/adapters/cba.py), traducido al formato del
data.json de FIBA LiveStats (`to_fls`) y leído con la fuente de la BSL/GBL. No hace peticiones.

Ids: jugador = playerId de QQ, equipo = id de equipo de QQ (los mismos que ligas/cba.csv). Los partidos sin
jugada a jugada en QQ (2020-21 entera, ene-may 2025) entran sin eventos ("la fuente no tiene jugada a jugada").
"""
from __future__ import annotations

from ...adapters.cba import season_docs, team_names, to_fls
from ..model import Game
from .base import Ctx
from .fiba_livestats import FibaLiveStatsPBP, _games_of


class CbaPBP(FibaLiveStatsPBP):
    name = "cba"
    version = "1.0"

    def games(self, ctx: Ctx) -> list[dict]:
        p = ctx.main_payload if isinstance(ctx.main_payload, dict) else {}
        docs = season_docs(p, ctx.cfg)
        self._docs = docs
        names = team_names(docs)
        fases = p.get("fases") or {}
        out = []
        for mid, d in docs.items():
            t1, t2 = d["tm"]["1"]["teamId"], d["tm"]["2"]["teamId"]
            out.append({"game_id": mid, "phase": fases.get(mid), "final": d.get("status") == "complete",
                        "date": str(d.get("matchDate") or "")[:10] or None, "teams": [t1, t2],
                        "team_names": {t1: names.get(t1), t2: names.get(t2)}})
        return sorted(out, key=lambda r: (r["date"] or "", r["game_id"]))

    def fetch(self, ctx: Ctx, ref: dict) -> dict:
        docs = getattr(self, "_docs", None)
        doc = (docs or {}).get(str(ref["game_id"]))
        if doc is None:
            d = docs_principal(ctx.main_payload, str(ref["game_id"]), ctx.cfg)
            doc = (d or {}).get("data")
        if not doc:
            raise ValueError("partido ausente del bruto principal")
        return {"data": doc}

    def parse(self, raw: dict, ref: dict, ctx: Ctx) -> Game:
        g = super().parse(raw, ref, ctx)
        doc = raw.get("data") or {}
        for k in ("1", "2"):                       # nombre latino visible ("Zhou Qi"), igual que en ligas/cba.csv
            for p in ((doc.get("tm") or {}).get(k) or {}).get("pl", {}).values():
                pid = str(p.get("personId"))
                if pid in g.players and p.get("name"):
                    g.players[pid]["nombre"] = p["name"]
        g.notes.extend((doc.get("notas") or [])[:3])
        return g


def docs_principal(main_payload, game_id: str, cfg: dict | None = None) -> dict | None:
    """data.json (traducido) del partido sacado del bruto principal, para el registro de entrenadores
    (bbstats/entrenadores.py: Extractor(lector_fiba_livestats, ..., docs_principal=cba.docs_principal))."""
    p = main_payload if isinstance(main_payload, dict) else {}
    g = _games_of(p).get(str(game_id))
    return {"data": to_fls(g, p.get("jugadores") or {}, cfg or {})} if isinstance(g, dict) else None
