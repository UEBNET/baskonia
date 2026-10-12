"""Euroliga (y EuroCup) — feed oficial de estadísticas v3 (proveedor InCrowd).

Endpoints (configurables en config/sources.json):
  {base}/{comp}/statistics/players/{traditional|advanced|misc|scoring}
  {base}/{comp}/statistics/teams/{traditional|advanced|opponentsTraditional|opponentsAdvanced}
con parámetros seasonMode=Single, seasonCode=E2025, statisticMode=Accumulated.
"""
from __future__ import annotations

from typing import Any

from ..http import FetchError, HttpClient
from ..normalize import (complete_counting, is_per_game_scale, map_counting, map_source_metrics,
                         per_game_to_totals)
from ..schema import COUNTING_NAMES, TEAM_STATS
from ..utils import first_present, flatten, to_float
from ..phases import subtract_phase
from .base import AdapterError, BaseAdapter, ParsedLeague

DEFAULT_BASE = "https://feeds.incrowdsports.com/provider/euroleague-feeds/v3/competitions"
PLAYER_ENDPOINTS = ["traditional", "advanced", "misc", "scoring"]
TEAM_ENDPOINTS = ["traditional", "advanced", "opponentsTraditional", "opponentsAdvanced"]


def _items(doc: Any, key: str) -> list[dict]:
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict):
        for k in (key, "data", "items", "results"):
            if isinstance(doc.get(k), list):
                return doc[k]
    return []


class EuroleagueAdapter(BaseAdapter):
    name = "euroleague"
    version = "1.0"

    def _params(self, season: str) -> dict:
        sc = self.season_cfg(season)
        comp = self.cfg.get("competicion", "E")
        params = {"seasonMode": "Single",
                  "seasonCode": sc.get("season_code", f"{comp}{sc['start_year']}"),
                  "statisticMode": self.cfg.get("statistic_mode", "Accumulated"),
                  "limit": self.cfg.get("limit", 1000),
                  "sortDirection": "descending"}
        if self.cfg.get("phase_type_code"):
            params["phaseTypeCode"] = self.cfg["phase_type_code"]
        return params

    def _get_all(self, http: HttpClient, url: str, params: dict, key: str) -> Any:
        """Descarga paginando con offset si la fuente lo indica con 'total'."""
        first = http.get_json(url, params=params)
        items = _items(first, key)
        total = first.get("total") if isinstance(first, dict) else None
        pages = [first]
        offset = len(items)
        while isinstance(total, int) and offset < total and items:
            nxt = http.get_json(url, params={**params, "offset": offset})
            items = _items(nxt, key)
            pages.append(nxt)
            offset += len(items)
        return pages

    def _fetch_set(self, http: HttpClient, params: dict) -> dict:
        base = self.cfg.get("base_url", DEFAULT_BASE).rstrip("/")
        comp = self.cfg.get("competicion", "E")
        out: dict[str, Any] = {"players": {}, "teams": {}}
        for ep in PLAYER_ENDPOINTS:
            url = f"{base}/{comp}/statistics/players/{ep}"
            try:
                out["players"][ep] = self._get_all(http, url, params, "players")
            except FetchError as exc:
                if ep == "traditional":
                    raise AdapterError(f"Euroliga: sin datos de jugadores ({exc})") from exc
                self.soft_fail(str(exc))
        for ep in TEAM_ENDPOINTS:
            url = f"{base}/{comp}/statistics/teams/{ep}"
            try:
                out["teams"][ep] = self._get_all(http, url, params, "teams")
            except FetchError as exc:
                self.soft_fail(str(exc))
        return out

    def fetch(self, season: str, http: HttpClient, previous_payload: Any | None = None) -> Any:
        params = self._params(season)
        params.pop("phaseTypeCode", None)
        payload: dict[str, Any] = {"params": params, "fases": {}}
        payload["fases"]["total"] = self._fetch_set(http, params)
        try:
            payload["fases"]["regular"] = self._fetch_set(http, {**params, "phaseTypeCode": "RS"})
        except AdapterError as exc:
            self.soft_fail(f"Temporada regular: {exc}")
        return payload

    # ------------------------------------------------------------------ parse
    @staticmethod
    def _player_key(rec: dict) -> tuple[str, str]:
        f = flatten(rec)
        pid = first_present(f, ["player.code", "playerCode", "code", "player.id"])
        tid = first_present(f, ["player.team.code", "team.code", "teamCode", "player.clubCode"])
        return str(pid), str(tid)

    def parse(self, payload: Any, season: str) -> dict[str, ParsedLeague]:
        fases = payload.get("fases") or {"total": payload}
        out: dict[str, ParsedLeague] = {}
        for ph, data in fases.items():
            out[ph] = self._parse_set(data)
        if "total" in out and "regular" in out:
            out["playoffs"] = subtract_phase(out["total"], out["regular"],
                                             ["Playoffs (play-in + playoffs + final four) = total - temporada regular"])
        return out

    def _parse_set(self, payload: Any) -> ParsedLeague:
        notes: list[str] = []
        pl = payload.get("players", {})
        by_key: dict[tuple, dict] = {}
        for page in pl.get("traditional", []):
            for rec in _items(page, "players"):
                f = flatten(rec)
                key = self._player_key(rec)
                row = {
                    "player_id": key[0], "team_id": key[1],
                    "nombre": first_present(f, ["player.name", "playerName", "name"]),
                    "edad": to_float(first_present(f, ["player.age", "age"])),
                    "equipo": first_present(f, ["player.team.name", "team.name", "teamName"]),
                    "equipo_codigo": first_present(f, ["player.team.tvCodes", "player.team.code", "team.code"]),
                    "nacionalidad": first_present(f, ["player.country.name", "player.nationality", "country"]),
                    "posicion": first_present(f, ["player.position", "position"]),
                    "dorsal": first_present(f, ["player.dorsal", "dorsal"]),
                    "_raw_img": f.get("player.imageUrl"),
                }
                row.update(map_counting(f))
                row.update(map_source_metrics(f))
                by_key[key] = row
        rows = list(by_key.values())
        if is_per_game_scale(rows):
            per_game_to_totals(rows, COUNTING_NAMES)
            notes.append("Euroliga devolvió promedios por partido: convertidos a totales (x partidos)")
        for ep in ("advanced", "misc", "scoring"):
            for page in pl.get(ep, []):
                for rec in _items(page, "players"):
                    f = flatten(rec)
                    row = by_key.get(self._player_key(rec))
                    if row is None:
                        continue
                    for k, v in map_source_metrics(f).items():
                        if k != "src_poss":  # en el feed avanzado las posesiones son por partido
                            row.setdefault(k, v)
                    # conteos que sólo aparecen en misc/scoring (dobles-dobles, puntos pintura...)
                    for k, v in map_counting(f).items():
                        if row.get(k) is None and k not in {"gp", "min", "pts"}:
                            row[k] = v
        for r in rows:
            r.pop("_raw_img", None)
            complete_counting(r)

        teams: dict[str, dict] = {}
        tm = payload.get("teams", {})
        for ep, prefix in (("traditional", "team_"), ("opponentsTraditional", "opp_")):
            pages = tm.get(ep, [])
            recs = [r for page in pages for r in _items(page, "teams")]
            scaled = []
            for rec in recs:
                f = flatten(rec)
                tid = str(first_present(f, ["team.code", "teamCode", "code", "club.code"]))
                t = teams.setdefault(tid, {"team_id": tid})
                t.setdefault("equipo", first_present(f, ["team.name", "teamName", "name"]))
                vals = map_counting(f, only=set(TEAM_STATS))
                scaled.append((t, prefix, vals))
            # normalización de escala (promedios -> totales) para equipos
            if scaled and all((v.get("min") or 0) <= 450 and (v.get("gp") or 0) >= 5 for _, _, v in scaled):
                pts_like = [v.get("pts") or 0 for _, _, v in scaled]
                if max(pts_like) < 150:
                    for _, _, v in scaled:
                        gp = v.get("gp") or 0
                        for k in list(v):
                            if k not in {"gp", "w", "l"}:
                                v[k] = v[k] * gp
                    notes.append(f"Equipos ({ep}) devueltos como promedios: convertidos a totales")
            for t, pfx, v in scaled:
                for k, val in v.items():
                    if k in {"gp", "w", "l"}:
                        if pfx == "team_":
                            t[f"team_{k}"] = val
                    else:
                        t[f"{pfx}{k}"] = val
        for t in teams.values():
            complete_counting(t, "team_")
            complete_counting(t, "opp_")
        if not teams:
            notes.append("Euroliga: sin totales de equipo; el contexto se reconstruirá sumando jugadores")
        return ParsedLeague(players=rows, teams=list(teams.values()), notes=notes)
