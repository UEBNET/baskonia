"""FIBA LiveStats (Genius Sports) — boxscores JSON partido a partido.

Muchas ligas europeas publican sus partidos en:
    https://fibalivestats.dcd.shared.geniussports.com/data/{match_id}/data.json

Este adaptador es GENÉRICO: cualquier liga que use FIBA LiveStats se configura indicando
cómo obtener los ids de partido (lista fija y/o páginas de calendario + regex) en
config/sources.json. Los partidos ya finalizados de la descarga anterior se reutilizan.
"""
from __future__ import annotations

import re
from typing import Any

from ..http import FetchError, HttpClient
from ..normalize import map_counting
from ..utils import height_to_cm, parse_minutes, to_float
from .base import AdapterError, BaseAdapter, ParsedLeague
from .boxscore import aggregate_games

DEFAULT_DATA_URL = "https://fibalivestats.dcd.shared.geniussports.com/data/{match_id}/data.json"
DEFAULT_ID_REGEX = r"fibalivestats\.dcd\.shared\.geniussports\.com/(?:u/[A-Za-z0-9]+/|data/)(\d{5,8})"


def _is_final(doc: Any) -> bool:
    if not isinstance(doc, dict):
        return False
    status = str(doc.get("periodStatus") or doc.get("status") or doc.get("matchStatus") or "").lower()
    if status in {"finished", "final", "complete", "completed", "ended", "endofgame"}:
        return True
    tm = doc.get("tm") or {}
    try:
        s1, s2 = to_float(tm["1"].get("score")), to_float(tm["2"].get("score"))
    except (KeyError, AttributeError):
        return False
    clock = str(doc.get("clock") or "")
    period = to_float(doc.get("period")) or 0
    return s1 is not None and s2 is not None and s1 != s2 and period >= 4 and clock in {"00:00", "0:00", "00:00:00"}


def parse_fiba_game(match_id: str, doc: dict) -> dict:
    """data.json de FIBA LiveStats -> formato estándar de partido (ver boxscore.py)."""
    sides = []
    for k in ("1", "2"):
        t = (doc.get("tm") or {}).get(k) or {}
        name = t.get("name") or t.get("nameInternational") or t.get("shortName")
        code = t.get("code") or t.get("shortName")
        tot_rec = {key[4:]: v for key, v in t.items() if key.startswith("tot_")}
        totals = map_counting(tot_rec)
        if t.get("score") is not None and totals.get("pts") is None:
            totals["pts"] = to_float(t.get("score"))
        players = []
        for p in (t.get("pl") or {}).values():
            first = p.get("firstName") or p.get("internationalFirstName") or ""
            family = p.get("familyName") or p.get("internationalFamilyName") or ""
            full = p.get("name") or f"{first} {family}".strip()
            pid = p.get("personId") or p.get("playerId") or f"{family}|{first}".lower()
            line = {"player_id": str(pid), "name": full,
                    "dorsal": p.get("shirtNumber"), "posicion": p.get("playingPosition"),
                    "starter": bool(to_float(p.get("starter")) or 0),
                    "altura_cm": height_to_cm(p.get("height")) if p.get("height") else None}
            stats = {key: v for key, v in p.items() if key.startswith("s") or key.startswith("eff")}
            line.update(map_counting(stats))
            if p.get("sMinutes") is not None:
                line["min"] = parse_minutes(p.get("sMinutes"))
            players.append(line)
        sides.append({"team_id": code or name, "name": name, "code": code,
                      "totals": totals, "players": players})
    return {"game_id": str(match_id), "date": doc.get("matchDate") or doc.get("date"),
            "final": _is_final(doc), "teams": sides}


class FibaLiveStatsAdapter(BaseAdapter):
    name = "fiba_livestats"
    version = "1.0"

    def discover_ids(self, season: str, http: HttpClient, pages: dict) -> list[str]:
        sc = self.season_cfg(season)
        ids: list[str] = [str(x) for x in sc.get("match_ids", [])]
        for disc in sc.get("discovery", []):
            url_tpl = disc["url"]
            regex = re.compile(disc.get("regex", DEFAULT_ID_REGEX))
            rng = disc.get("pages")  # p.ej. {"from": 1, "to": 40} para recorrer jornadas
            urls = ([url_tpl.format(page=i, **sc) for i in range(rng["from"], rng["to"] + 1)]
                    if rng else [url_tpl.format(**sc)])
            for url in urls:
                try:
                    html = http.get_text(url)
                except FetchError as exc:
                    self.soft_fail(str(exc))
                    continue
                pages[url] = html
                ids.extend(regex.findall(html))
        seen, out = set(), []
        for i in ids:
            if i not in seen:
                seen.add(i)
                out.append(i)
        return out

    def fetch(self, season: str, http: HttpClient, previous_payload: Any | None = None) -> Any:
        pages: dict[str, str] = {}
        ids = self.discover_ids(season, http, pages)
        if not ids:
            raise AdapterError(
                f"{self.league}: no hay ids de partido. Configura 'temporadas.{season}.match_ids' o "
                f"'temporadas.{season}.discovery' en config/sources.json")
        prev_games = (previous_payload or {}).get("games", {}) if isinstance(previous_payload, dict) else {}
        url_tpl = self.cfg.get("data_url", DEFAULT_DATA_URL)
        games: dict[str, Any] = {}
        reused = 0
        for mid in ids:
            if mid in prev_games and _is_final(prev_games[mid]):
                games[mid] = prev_games[mid]
                reused += 1
                continue
            try:
                games[mid] = http.get_json(url_tpl.format(match_id=mid))
            except FetchError as exc:
                self.soft_fail(str(exc))
        if not games:
            raise AdapterError(f"{self.league}: no se pudo descargar ningún partido")
        return {"match_ids": ids, "discovery_pages": pages, "games": games, "reused_games": reused}

    def parse(self, payload: Any, season: str) -> ParsedLeague:
        games = [parse_fiba_game(mid, doc) for mid, doc in (payload.get("games") or {}).items()
                 if isinstance(doc, dict)]
        notes = [f"{len(games)} boxscores FIBA LiveStats; {payload.get('reused_games', 0)} reutilizados"]
        return aggregate_games(games, notes)
