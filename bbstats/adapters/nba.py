"""NBA y G League — API de estadísticas oficial (stats.nba.com / stats.gleague.nba.com).

Formato de respuesta: {"resultSets": [{"name", "headers": [...], "rowSet": [[...], ...]}]}.
Se descargan TOTALES de temporada (PerMode=Totals) en todas las MeasureType disponibles,
totales de equipo y de rivales, y (sólo NBA) hustle + tracking + índice de jugadores (bio).
"""
from __future__ import annotations

from typing import Any

from ..http import FetchError, HttpClient
from ..normalize import complete_counting, map_counting, map_source_metrics
from ..schema import TEAM_STATS
from ..utils import height_to_cm, to_float, weight_to_kg
from .base import AdapterError, BaseAdapter, NoDataYet, ParsedLeague

NBA_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
    "Connection": "keep-alive",
}

_COMMON = {
    "College": "", "Conference": "", "Country": "", "DateFrom": "", "DateTo": "", "Division": "",
    "DraftPick": "", "DraftYear": "", "GameScope": "", "GameSegment": "", "Height": "",
    "LastNGames": "0", "Location": "", "Month": "0", "OpponentTeamID": "0", "Outcome": "",
    "PORound": "0", "PaceAdjust": "N", "Period": "0", "PlayerExperience": "", "PlayerPosition": "",
    "PlusMinus": "N", "Rank": "N", "SeasonSegment": "", "ShotClockRange": "", "StarterBench": "",
    "TeamID": "0", "TwoWay": "0", "VsConference": "", "VsDivision": "", "Weight": "", "ISTRound": "",
}

PLAYER_MEASURES = ["Base", "Advanced", "Misc", "Scoring", "Usage", "Defense"]
TEAM_MEASURES = ["Base", "Opponent", "Advanced"]
TRACKING = ["SpeedDistance", "Possessions", "Drives", "Passing", "CatchShoot", "PullUpShot",
            "ElbowTouch", "PostTouch", "PaintTouch"]


def result_rows(doc: Any, index: int = 0) -> list[dict]:
    """Convierte un resultSet (headers + rowSet) a lista de diccionarios."""
    if not isinstance(doc, dict):
        return []
    rs = doc.get("resultSets", doc.get("resultSet"))
    if isinstance(rs, dict):
        rs = [rs]
    if not rs or len(rs) <= index:
        return []
    headers = rs[index].get("headers") or []
    if headers and isinstance(headers[0], dict):  # cabeceras multinivel
        headers = headers[-1].get("columnNames", [])
    return [dict(zip(headers, row)) for row in rs[index].get("rowSet") or []]


class NBAAdapter(BaseAdapter):
    name = "nba"
    version = "1.0"
    default_base = "https://stats.nba.com/stats"
    league_id = "00"
    extras = True  # hustle + tracking + playerindex

    def _base(self) -> str:
        return self.cfg.get("base_url", self.default_base).rstrip("/")

    def _season(self, season: str) -> str:
        return self.season_cfg(season).get("season", season)

    def _get(self, http: HttpClient, endpoint: str, params: dict) -> Any:
        headers = {**NBA_HEADERS, **(self.cfg.get("headers") or {})}
        return http.get_json(f"{self._base()}/{endpoint}", params=params, headers=headers)

    def _fetch_type(self, http: HttpClient, s: str, season_type: str, lid: str, required: bool) -> dict:
        base = {**_COMMON, "LeagueID": lid, "Season": s, "SeasonType": season_type, "PerMode": "Totals"}
        out: dict[str, Any] = {"players": {}, "teams": {}, "hustle": None, "tracking": {}}
        for m in PLAYER_MEASURES:
            try:
                out["players"][m] = self._get(http, "leaguedashplayerstats", {**base, "MeasureType": m})
            except FetchError as exc:
                if m == "Base" and required:
                    raise AdapterError(f"{self.league}: sin datos base de jugadores ({exc})") from exc
                self.soft_fail(str(exc))
                if m == "Base":
                    return out
        if not result_rows(out["players"].get("Base")):
            return out  # fase sin partidos (p.ej. playoffs aún no jugados)
        for m in TEAM_MEASURES:
            try:
                out["teams"][m] = self._get(http, "leaguedashteamstats", {**base, "MeasureType": m})
            except FetchError as exc:
                self.soft_fail(str(exc))
        if self.cfg.get("extras", self.extras):
            try:
                out["hustle"] = self._get(http, "leaguehustlestatsplayer", base)
            except FetchError as exc:
                self.soft_fail(str(exc))
            for pt in TRACKING:
                try:
                    out["tracking"][pt] = self._get(http, "leaguedashptstats",
                                                    {**base, "PlayerOrTeam": "Player", "PtMeasureType": pt})
                except FetchError as exc:
                    self.soft_fail(str(exc))
        return out

    def fetch(self, season: str, http: HttpClient, previous_payload: Any | None = None) -> Any:
        s = self._season(season)
        lid = self.cfg.get("league_id", self.league_id)
        types = self.cfg.get("season_types") or {"regular": "Regular Season", "playoffs": "Playoffs"}
        payload: dict[str, Any] = {"season": s, "tipos": {}, "playerindex": None}
        for i, (phase, st) in enumerate(types.items()):
            payload["tipos"][phase] = {"season_type": st, **self._fetch_type(http, s, st, lid, required=i == 0)}
        if not any(result_rows((t.get("players") or {}).get("Base")) for t in payload["tipos"].values()):
            raise NoDataYet(f"{self.league} {season}: la temporada aún no tiene partidos")
        try:
            payload["playerindex"] = self._get(http, "playerindex", {
                "LeagueID": lid, "Season": s, "Historical": "0", "Active": "", "AllStar": "",
                "College": "", "Country": "", "DraftPick": "", "DraftRound": "", "DraftYear": "",
                "Height": "", "TeamID": "0", "Weight": "", "SeasonType": "Regular Season"})
        except FetchError as exc:
            self.soft_fail(str(exc))
        return payload

    def parse(self, payload: Any, season: str) -> dict[str, ParsedLeague]:
        if "tipos" not in payload:  # formato antiguo (una sola fase)
            return {"regular": self._parse_type(payload, payload)}
        out = {}
        for phase, data in payload["tipos"].items():
            parsed = self._parse_type(data, payload)
            if parsed.players:
                out[phase] = parsed
        return out

    def _parse_type(self, payload: Any, root: Any) -> ParsedLeague:
        notes: list[str] = []
        rows: dict[str, dict] = {}
        for r in result_rows((payload.get("players") or {}).get("Base")):
            pid = str(r.get("PLAYER_ID"))
            row = {"player_id": pid, "team_id": str(r.get("TEAM_ID")),
                   "nombre": r.get("PLAYER_NAME"), "equipo_codigo": r.get("TEAM_ABBREVIATION"),
                   "equipo": r.get("TEAM_ABBREVIATION"), "edad": to_float(r.get("AGE"))}
            row.update(map_counting(r))
            row.update(map_source_metrics(r))
            rows[pid] = row
        for m in PLAYER_MEASURES[1:]:
            for r in result_rows((payload.get("players") or {}).get(m)):
                row = rows.get(str(r.get("PLAYER_ID")))
                if row is None:
                    continue
                for k, v in map_source_metrics(r).items():
                    row.setdefault(k, v)
                if m == "Misc":  # puntos contraataque, pintura, 2ª oportunidad, tras pérdida
                    for k in ("pts_fastbreak", "pts_paint", "pts_2ndchance", "pts_off_tov"):
                        v = map_counting(r).get(k)
                        if v is not None:
                            row[k] = v
        extra_docs = [payload.get("hustle")] + list((payload.get("tracking") or {}).values())
        for doc in extra_docs:
            for r in result_rows(doc):
                row = rows.get(str(r.get("PLAYER_ID")))
                if row is not None:
                    for k, v in map_source_metrics(r).items():
                        row.setdefault(k, v)
        for r in result_rows(root.get("playerindex")):
            row = rows.get(str(r.get("PERSON_ID")))
            if row is None:
                continue
            row["altura_cm"] = height_to_cm(r.get("HEIGHT"))
            row["peso_kg"] = weight_to_kg(r.get("WEIGHT"), "lb")
            row["posicion"] = r.get("POSITION")
            row["nacionalidad"] = r.get("COUNTRY")
            row["dorsal"] = r.get("JERSEY_NUMBER")
            if r.get("TEAM_NAME"):
                row["equipo"] = f"{r.get('TEAM_CITY', '')} {r['TEAM_NAME']}".strip()
        players = list(rows.values())
        for r in players:
            complete_counting(r)
        notes.append("NBA/G League agrupa a los jugadores traspasados en una sola fila (equipo = último)")
        if all(r.get("gs") is None for r in players):
            notes.append("La fuente no publica partidos como titular en este endpoint: 'gs' en blanco")

        teams: dict[str, dict] = {}
        for m, prefix in (("Base", "team_"), ("Opponent", "opp_")):
            for r in result_rows((payload.get("teams") or {}).get(m)):
                tid = str(r.get("TEAM_ID"))
                t = teams.setdefault(tid, {"team_id": tid, "equipo": r.get("TEAM_NAME")})
                # En 'Opponent' las columnas vienen como OPP_FGM, OPP_PTS...
                rec = {(k[4:] if k.startswith("OPP_") else k): v for k, v in r.items()}
                for k, v in map_counting(rec, only=set(TEAM_STATS)).items():
                    if k in {"gp", "w", "l"}:
                        if prefix == "team_":
                            t[f"team_{k}"] = v
                        continue
                    if k == "min":  # NBA publica minutos de partido (48*G); pasar a minutos-jugador
                        v = v * 5
                    t[f"{prefix}{k}"] = v
        for t in teams.values():
            if t.get("opp_min") is None and t.get("team_min") is not None:
                t["opp_min"] = t["team_min"]
            complete_counting(t, "team_")
            complete_counting(t, "opp_")
        for r in players:  # nombre completo del equipo
            t = teams.get(r["team_id"])
            if t and t.get("equipo") and r.get("equipo") == r.get("equipo_codigo"):
                r["equipo"] = t["equipo"]
        return ParsedLeague(players=players, teams=list(teams.values()), notes=notes)


class GLeagueAdapter(NBAAdapter):
    name = "gleague"
    default_base = "https://stats.gleague.nba.com/stats"
    league_id = "20"
    extras = False  # la G League no publica hustle ni tracking
