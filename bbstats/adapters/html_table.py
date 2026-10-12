"""Adaptador genérico de tablas HTML de estadísticas de temporada (configurable sin programar).

Sirve para enchufar cualquier web que publique una tabla de jugadores (y opcionalmente una
de equipos) en HTML estático. Todo se define en config/sources.json:

  "adaptador": "html_table",
  "temporadas": {"2025-26": {
      "players_urls": ["https://.../stats?page={page}"], "pages": {"from": 1, "to": 5},
      "teams_url": "https://.../team-stats",            (opcional)
      "opp_teams_url": "https://.../opponent-stats"      (opcional)
  }},
  "column_map": {"Jugador": "nombre", "Equipo": "equipo", "PJ": "gp", ...},  (opcional)
  "promedios": true      # si la tabla está en promedios por partido -> se pasa a totales
  "match_table": "MIN"   # texto que debe aparecer en la cabecera de la tabla buscada
"""
from __future__ import annotations

from io import StringIO
from typing import Any

import pandas as pd

from ..http import FetchError, HttpClient
from ..normalize import canonical_field, complete_counting, per_game_to_totals
from ..schema import COUNTING_NAMES, TEAM_STATS
from ..utils import parse_minutes, slugify, to_float
from .base import AdapterError, BaseAdapter, ParsedLeague

_IDENTITY = {"nombre", "equipo", "equipo_codigo", "player_id", "team_id", "posicion", "dorsal",
             "nacionalidad", "edad", "altura_cm", "peso_kg"}
_ID_ALIASES = {"jugador": "nombre", "player": "nombre", "name": "nombre", "nombre": "nombre",
               "spieler": "nombre", "joueur": "nombre", "giocatore": "nombre",
               "equipo": "equipo", "team": "equipo", "club": "equipo", "squadra": "equipo",
               "equipe": "equipo", "mannschaft": "equipo", "pos": "posicion", "posicion": "posicion"}


def _tables(html: str, match: str | None) -> list[pd.DataFrame]:
    try:
        dfs = pd.read_html(StringIO(html))
    except ValueError:
        return []
    out = []
    for df in dfs:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [" ".join(str(x) for x in col if "Unnamed" not in str(x)).strip() for col in df.columns]
        if match is None or any(match.lower() in str(c).lower() for c in df.columns):
            out.append(df)
    return out


def _map_columns(cols: list[str], column_map: dict) -> dict[str, str]:
    mapping = {}
    for c in cols:
        if c in column_map:
            mapping[c] = column_map[c]
            continue
        key = slugify(c).replace("-", "")
        if key in _ID_ALIASES:
            mapping[c] = _ID_ALIASES[key]
            continue
        canon = canonical_field(c)
        if canon:
            mapping[c] = canon
    return mapping


class HtmlTableAdapter(BaseAdapter):
    name = "html_table"
    version = "1.0"

    def fetch(self, season: str, http: HttpClient, previous_payload: Any | None = None) -> Any:
        sc = self.season_cfg(season)
        urls = []
        rng = sc.get("pages")
        for tpl in sc.get("players_urls", []):
            if rng and "{page}" in tpl:
                urls += [tpl.format(page=i, **sc) for i in range(rng["from"], rng["to"] + 1)]
            else:
                urls.append(tpl.format(**sc))
        if not urls:
            raise AdapterError(f"{self.league}: falta 'temporadas.{season}.players_urls' en config")
        payload: dict[str, Any] = {"players": {}, "teams": None, "opp_teams": None}
        for u in urls:
            try:
                payload["players"][u] = http.get_text(u)
            except FetchError as exc:
                self.soft_fail(str(exc))
        if not payload["players"]:
            raise AdapterError(f"{self.league}: no se pudo descargar ninguna tabla de jugadores")
        for key, cfg_key in (("teams", "teams_url"), ("opp_teams", "opp_teams_url")):
            if sc.get(cfg_key):
                try:
                    payload[key] = http.get_text(sc[cfg_key].format(**sc))
                except FetchError as exc:
                    self.soft_fail(str(exc))
        return payload

    def _rows(self, html: str) -> list[dict]:
        rows = []
        cmap = self.cfg.get("column_map", {})
        for df in _tables(html, self.cfg.get("match_table", "MIN")):
            mapping = _map_columns([str(c) for c in df.columns], cmap)
            for rec in df.to_dict("records"):
                row: dict[str, Any] = {}
                for src, dst in mapping.items():
                    v = rec.get(src)
                    if dst in _IDENTITY:
                        row[dst] = None if pd.isna(v) else str(v)
                    elif dst == "min":
                        row[dst] = parse_minutes(v)
                    else:
                        row[dst] = to_float(v)
                rows.append(row)
        return rows

    def parse(self, payload: Any, season: str) -> ParsedLeague:
        notes: list[str] = []
        players: list[dict] = []
        for html in (payload.get("players") or {}).values():
            for r in self._rows(html):
                if not r.get("nombre") or str(r["nombre"]).lower().startswith(("total", "media")):
                    continue
                r.setdefault("player_id", f"{slugify(r['nombre'])}|{slugify(r.get('equipo') or '')}")
                r.setdefault("team_id", slugify(r.get("equipo") or ""))
                players.append(r)
        if self.cfg.get("promedios"):
            per_game_to_totals(players, COUNTING_NAMES)
            notes.append("Tabla en promedios por partido: convertida a totales")
        for r in players:
            complete_counting(r)
        teams: dict[str, dict] = {}
        for key, prefix in (("teams", "team_"), ("opp_teams", "opp_")):
            if not payload.get(key):
                continue
            for r in self._rows(payload[key]):
                tid = slugify(r.get("equipo") or r.get("nombre") or "")
                if not tid:
                    continue
                t = teams.setdefault(tid, {"team_id": tid, "equipo": r.get("equipo") or r.get("nombre")})
                if self.cfg.get("promedios"):
                    per_game_to_totals([r], TEAM_STATS)
                for k in TEAM_STATS:
                    if r.get(k) is not None and not (prefix == "opp_" and k in {"gp", "w", "l"}):
                        t[f"{prefix}{k}"] = r[k]
        for t in teams.values():
            complete_counting(t, "team_")
            complete_counting(t, "opp_")
        return ParsedLeague(players=players, teams=list(teams.values()), notes=notes)
