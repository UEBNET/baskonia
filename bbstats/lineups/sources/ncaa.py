"""NCAA D-I (top-50, ESPN): jugada a jugada del bruto principal (bbstats/adapters/ncaa.py), traducido al formato
del data.json de FIBA LiveStats (`to_fls`) y leído con la misma fuente que la BSL/GBL. No hace peticiones.

Ids de equipo = team id de ESPN (los del adaptador principal, no los de season_teams). Cada mitad de 20' llega
como dos periodos de 10' (ver adapters/ncaa.py), así que `periodo` 1-4 son tramos de 10' y 5+ las prórrogas.
Partidos sin sustituciones (todos antes de 2024-25, parte de 2024-25): has_lineups=False (sólo tiros y
asistencias), como los de FIBA LiveStats sin cambios."""
from __future__ import annotations

from ...adapters.ncaa import to_fls
from .base import Ctx
from .fiba_livestats import FibaLiveStatsPBP, _games_of


class NcaaPBP(FibaLiveStatsPBP):
    name = "ncaa"
    version = "1.0"

    def games(self, ctx: Ctx) -> list[dict]:
        p = ctx.main_payload if isinstance(ctx.main_payload, dict) else {}
        fases, fechas = p.get("fases") or {}, p.get("fechas") or {}
        self._payload = p
        out = []
        for gid, raw in _games_of(p).items():
            ph = fases.get(gid)
            if ph not in ("regular", "playoffs") or not isinstance(raw, dict):
                continue
            comp = (((raw.get("header") or {}).get("competitions") or [{}])[0]) or {}
            cs = sorted(comp.get("competitors") or [], key=lambda c: 0 if c.get("homeAway") == "home" else 1)
            out.append({"game_id": gid, "phase": ph,
                        "final": bool(((comp.get("status") or {}).get("type") or {}).get("completed")),
                        "date": fechas.get(gid) or comp.get("date"),
                        "teams": [str(c.get("id")) for c in cs[:2]],
                        "team_names": {str(c.get("id")): (c.get("team") or {}).get("displayName") for c in cs[:2]}})
        return sorted(out, key=lambda r: (r["date"] or "", r["game_id"]))

    def fetch(self, ctx: Ctx, ref: dict) -> dict:
        p = getattr(self, "_payload", None) or (ctx.main_payload if isinstance(ctx.main_payload, dict) else {})
        d = docs_principal(p, str(ref["game_id"]))
        if not d:
            raise ValueError("partido ausente del bruto principal")
        return d


def docs_principal(main_payload, game_id: str) -> dict | None:
    """data.json (traducido) del partido sacado del bruto principal: para quintetos y para el registro de
    entrenadores (lector_fiba_livestats lee tm[].coach / coachDetails, que salen de la plantilla de ESPN)."""
    p = main_payload if isinstance(main_payload, dict) else {}
    raw = _games_of(p).get(str(game_id))
    return {"data": to_fls(raw, p.get("equipos") or {})} if isinstance(raw, dict) else None
