"""LBA Serie A (Italia) — API pública de legabasket.it (la que usa su propia web).

  /api/championships/get-championships?page=N                 competiciones por año (paginado)
        ctype_code RS = temporada regular, PO = playoffs; cserie_code A1 = Serie A
  /api/championships/get-championships-calendar-by-id?id=C&d=J partidos de la jornada J (event_serial)
  /api/championships/get-championships-matches-scores-by-id?id=M boxscore (tabellino)

Campos del boxscore: pun (puntos), sec (segundos), sf (quinteto inicial), t2_r/t2_t, t3_r/t3_t,
tl_r/tl_t (anotados/intentados), rimbalzi_o/d/t, ass, palle_r (recuperaciones), palle_p (pérdidas),
stoppate_dat/sub (tapones dados/recibidos), falli_c/falli_sf (faltas cometidas/recibidas),
sc (mates), plus_minus, val_lega (valoración), val_oer.
"""
from __future__ import annotations

from typing import Any

from ..http import FetchError, HttpClient
from ..utils import to_float
from .base import AdapterError, BaseAdapter, NoDataYet, ParsedLeague
from .boxscore import aggregate_by_phase

API = "https://www.legabasket.it/api"
PHASE_BY_TYPE = {"RS": "regular", "PO": "playoffs"}
_MAP = {"pun": "pts", "t2_r": "fg2m", "t2_t": "fg2a", "t3_r": "fg3m", "t3_t": "fg3a", "tl_r": "ftm", "tl_t": "fta",
        "rimbalzi_o": "oreb", "rimbalzi_d": "dreb", "rimbalzi_t": "reb", "ass": "ast", "palle_r": "stl",
        "palle_p": "tov", "stoppate_dat": "blk", "stoppate_sub": "blka", "falli_c": "pf", "falli_sf": "pfd",
        "sc": "dunks", "plus_minus": "plus_minus", "val_lega": "pir"}
FINISHED = {"2"}


def _stats(rec: dict) -> dict:
    out = {c: to_float(rec.get(k)) for k, c in _MAP.items() if rec.get(k) is not None}
    if rec.get("sec") is not None:
        out["min"] = to_float(rec["sec"]) / 60.0
    return {k: v for k, v in out.items() if v is not None}


def parse_scores(match: dict, doc: dict, phase: str) -> dict:
    sc = (doc or {}).get("scores") or {}
    sides = []
    for side, prefix in (("ht", "h"), ("vt", "v")):
        t = sc.get(side) or {}
        players = []
        for r in t.get("rows") or []:
            line = {"player_id": str(r.get("player_id")),
                    "name": f"{r.get('player_name', '')} {str(r.get('player_surname', '')).title()}".strip(),
                    "dorsal": r.get("player_num"), "starter": str(r.get("sf")) == "1",
                    "src_oer": to_float(r.get("val_oer"))}
            line.update(_stats(r))
            players.append(line)
        totals = _stats(t.get("totals") or {})
        totals.pop("plus_minus", None)
        sides.append({"team_id": str(match.get(f"{prefix}_team_id")), "name": match.get(f"{prefix}_team_name"),
                      "code": match.get(f"{prefix}_club_code"), "totals": totals, "players": players})
    return {"game_id": str(match.get("id")), "phase": phase, "final": True, "teams": sides,
            "date": match.get("match_datetime")}


class LBAAdapter(BaseAdapter):
    name = "lba"
    version = "1.0"

    def _get(self, http: HttpClient, path: str, params: dict | None = None) -> Any:
        return http.get_json(f"{self.cfg.get('base_url', API)}/{path}", params=params,
                             headers={"Accept": "application/json", "Referer": "https://www.legabasket.it/"})

    def _championships(self, http: HttpClient, year: int) -> list[dict]:
        first = self._get(http, "championships/get-championships", {"page": 1})
        pages = int((first.get("pagination") or {}).get("pages") or 1)
        found: list[dict] = []
        for page in range(pages, 0, -1):  # las más recientes están al final
            doc = first if page == 1 else self._get(http, "championships/get-championships", {"page": page})
            comps = doc.get("competitions") or []
            found += [c for c in comps if c.get("year") == year and c.get("cserie_code") == self.cfg.get("serie", "A1")
                      and c.get("ctype_code") in PHASE_BY_TYPE]
            if comps and max(c.get("year") or 0 for c in comps) < year:
                break
        return found

    def fetch(self, season: str, http: HttpClient, previous_payload: Any | None = None) -> Any:
        sc = self.season_cfg(season)
        champs = sc.get("championships") or self._championships(http, sc["start_year"])
        if not champs:
            raise NoDataYet(f"LBA: sin competiciones para {season}")
        prev = (previous_payload or {}).get("scores", {}) if isinstance(previous_payload, dict) else {}
        calendars: dict[str, dict] = {}
        scores: dict[str, Any] = {}
        reused = 0
        for ch in champs:
            cid = ch["id"]
            first = self._get(http, "championships/get-championships-calendar-by-id", {"id": cid})
            days = ((first.get("filters") or {}).get("days")) or []
            calendars[str(cid)] = {}
            for day in days:
                try:
                    doc = self._get(http, "championships/get-championships-calendar-by-id",
                                    {"id": cid, "d": day["event_serial"]})
                except FetchError as exc:
                    self.soft_fail(str(exc))
                    continue
                calendars[str(cid)][str(day["event_serial"])] = doc
                for m in doc.get("matches") or []:
                    if str(m.get("game_status")) not in FINISHED:
                        continue
                    mid = str(m["id"])
                    if mid in prev:
                        scores[mid] = prev[mid]
                        reused += 1
                        continue
                    try:
                        scores[mid] = self._get(http, "championships/get-championships-matches-scores-by-id",
                                                {"id": mid})
                    except FetchError as exc:
                        self.soft_fail(str(exc))
        if not scores:
            raise NoDataYet(f"LBA {season}: aún no hay partidos finalizados")
        return {"championships": champs, "calendars": calendars, "scores": scores, "reused_games": reused}

    def parse(self, payload: Any, season: str) -> dict[str, ParsedLeague]:
        phase_of_champ = {str(c["id"]): PHASE_BY_TYPE.get(c.get("ctype_code"), "regular")
                          for c in payload.get("championships") or []}
        games, seen = [], set()
        for cid, days in (payload.get("calendars") or {}).items():
            for doc in days.values():
                for m in doc.get("matches") or []:
                    mid = str(m["id"])
                    if mid in seen or mid not in (payload.get("scores") or {}):
                        continue
                    seen.add(mid)
                    games.append(parse_scores(m, payload["scores"][mid], phase_of_champ.get(cid, "regular")))
        if not games:
            raise AdapterError("LBA: el bruto no contiene boxscores")
        return aggregate_by_phase(games, [f"{len(games)} boxscores LBA; {payload.get('reused_games', 0)} reutilizados"])
