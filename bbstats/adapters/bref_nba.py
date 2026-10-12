"""NBA — Basketball-Reference (basketball-reference.com).

stats.nba.com bloquea las conexiones desde servidores/cloud; Basketball-Reference recoge los
datos oficiales y los publica en HTML estático con atributos `data-stat` estables.

Páginas por temporada (año = año de fin, 2025-26 -> 2026):
  leagues/NBA_{Y}_totals.html        totales      (tabla temporada regular + tabla *_post = playoffs)
  leagues/NBA_{Y}_advanced.html      PER, TS%, USG%, WS, BPM, VORP...
  leagues/NBA_{Y}_per_poss.html      ORtg / DRtg individuales
  leagues/NBA_{Y}_play-by-play.html  % por posición, on/off, tipos de pérdida y falta, tapones recibidos
  leagues/NBA_{Y}_shooting.html      distancias de tiro, % asistido, mates, triples de esquina
  leagues/NBA_{Y}.html               totales de equipo y de rivales (temporada regular)
  playoffs/NBA_{Y}.html              totales de equipo y de rivales (playoffs)

Las tablas están dentro de comentarios HTML; se descomentan antes de parsear.
Jugadores traspasados: se conservan las filas por equipo y se descartan las agregadas (2TM, 3TM...).
Límite de la web: ~20 peticiones/minuto -> pausa de 3,5 s por petición (config http.delay_por_dominio).
"""
from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from ..http import FetchError, HttpClient
from ..normalize import complete_counting
from ..utils import to_float
from .base import AdapterError, BaseAdapter, NoDataYet, ParsedLeague

BASE = "https://www.basketball-reference.com"
PLAYER_PAGES = {"totals": "totals_stats", "advanced": "advanced", "per_poss": "per_poss",
                "play-by-play": "pbp_stats", "shooting": "shooting"}

COUNTING_MAP = {"games": "gp", "games_started": "gs", "mp": "min", "pts": "pts", "fg": "fgm", "fga": "fga",
                "fg2": "fg2m", "fg2a": "fg2a", "fg3": "fg3m", "fg3a": "fg3a", "ft": "ftm", "fta": "fta",
                "orb": "oreb", "drb": "dreb", "trb": "reb", "ast": "ast", "stl": "stl", "blk": "blk", "tov": "tov",
                "pf": "pf", "tpl_dbl": "td3"}
SRC_MAP = {
    "advanced": {"per": "src_per", "ts_pct": "src_ts_pct", "fg3a_per_fga_pct": "src_fg3a_rate",
                 "fta_per_fga_pct": "src_fta_rate", "orb_pct": "src_oreb_pct", "drb_pct": "src_dreb_pct",
                 "trb_pct": "src_reb_pct", "ast_pct": "src_ast_pct", "stl_pct": "src_stl_pct",
                 "blk_pct": "src_blk_pct", "tov_pct": "src_tov_ratio", "usg_pct": "src_usg_pct",
                 "ows": "src_ows", "dws": "src_dws", "ws": "src_ws", "ws_per_48": "src_ws48", "obpm": "src_obpm",
                 "dbpm": "src_dbpm", "bpm": "src_bpm", "vorp": "src_vorp"},
    "per_poss": {"off_rtg": "src_ortg", "def_rtg": "src_drtg"},
    "play-by-play": {"pct_1": "src_pos_pg_pct", "pct_2": "src_pos_sg_pct", "pct_3": "src_pos_sf_pct",
                     "pct_4": "src_pos_pf_pct", "pct_5": "src_pos_c_pct", "plus_minus_on": "src_on_court_pm100",
                     "plus_minus_net": "src_on_off_pm100", "tov_bad_pass": "src_tov_bad_pass",
                     "tov_lost_ball": "src_tov_lost_ball", "fouls_shooting": "src_fouls_shooting",
                     "fouls_offensive": "src_fouls_offensive", "drawn_shooting": "src_drawn_shooting",
                     "drawn_offensive": "src_drawn_offensive", "astd_pts": "src_astd_pts", "and1s": "src_and1"},
    "shooting": {"avg_dist": "src_avg_shot_dist", "pct_fga_00_03": "src_pct_fga_00_03",
                 "pct_fga_03_10": "src_pct_fga_03_10", "pct_fga_10_16": "src_pct_fga_10_16",
                 "pct_fga_16_xx": "src_pct_fga_16_3p", "pct_fga_fg3a": "src_pct_fga_3pt",
                 "pct_fga_fg2a": "src_pct_fga_2pt", "fg_pct_00_03": "src_fg_pct_00_03",
                 "fg_pct_03_10": "src_fg_pct_03_10", "fg_pct_10_16": "src_fg_pct_10_16",
                 "fg_pct_16_xx": "src_fg_pct_16_3p", "pct_ast_fg2": "src_pct_ast_fg2",
                 "pct_ast_fg3": "src_pct_ast_fg3", "pct_fga_dunk": "src_pct_fga_dunk",
                 "pct_fg3a_corner3": "src_pct_fg3a_corner", "fg_pct_corner3": "src_fg3_pct_corner"},
}
# conteos adicionales que salen de páginas no-totales
EXTRA_COUNTING = {"play-by-play": {"own_shots_blk": "blka", "drawn_shooting": None},
                  "shooting": {"fg_dunk": "dunks"}}
TEAM_MAP = {"g": "gp", "mp": "min", "pts": "pts", "fg": "fgm", "fga": "fga", "fg2": "fg2m", "fg2a": "fg2a",
            "fg3": "fg3m", "fg3a": "fg3a", "ft": "ftm", "fta": "fta", "orb": "oreb", "drb": "dreb", "trb": "reb",
            "ast": "ast", "stl": "stl", "blk": "blk", "tov": "tov", "pf": "pf"}
_PID = re.compile(r"/players/\w/([a-z0-9]+)\.html")
_TID = re.compile(r"/teams/([A-Z0-9]{2,4})/")
# porcentajes que BR publica en escala 0-1 (se pasan a 0-100)
_FRACTION = {"src_ts_pct", "src_fg3a_rate", "src_fta_rate", "src_pct_fga_00_03", "src_pct_fga_03_10",
             "src_pct_fga_10_16", "src_pct_fga_16_3p", "src_pct_fga_3pt", "src_pct_fga_2pt", "src_fg_pct_00_03",
             "src_fg_pct_03_10", "src_fg_pct_10_16", "src_fg_pct_16_3p", "src_pct_ast_fg2", "src_pct_ast_fg3",
             "src_pct_fga_dunk", "src_pct_fg3a_corner", "src_fg3_pct_corner"}


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(re.sub(r"<!--|-->", "", html or ""), "lxml")


def _table_rows(soup: BeautifulSoup, table_id: str) -> list[dict]:
    t = soup.find("table", id=table_id)
    if t is None or t.find("tbody") is None:
        return []
    out = []
    for tr in t.find("tbody").find_all("tr"):
        if "thead" in (tr.get("class") or []):
            continue
        rec: dict[str, Any] = {}
        for c in tr.find_all(["th", "td"]):
            ds = c.get("data-stat")
            if not ds:
                continue
            rec[ds] = c.get_text(strip=True)
            a = c.find("a", href=True)
            if a:
                rec[f"{ds}__href"] = a["href"]
        out.append(rec)
    return out


class BRefNBAAdapter(BaseAdapter):
    name = "bref_nba"
    version = "1.0"

    def _year(self, season: str) -> int:
        return int(self.season_cfg(season).get("bref_year", int(season[:4]) + 1))

    def fetch(self, season: str, http: HttpClient, previous_payload: Any | None = None) -> Any:
        y = self._year(season)
        pages: dict[str, str] = {}
        for name in PLAYER_PAGES:
            url = f"{BASE}/leagues/NBA_{y}_{name}.html"
            try:
                pages[name] = http.get_text(url)
            except FetchError as exc:
                if name == "totals":
                    if "404" in str(exc):
                        raise NoDataYet(f"NBA {season}: Basketball-Reference aún no publica la temporada") from exc
                    raise AdapterError(f"NBA {season}: sin página de totales ({exc})") from exc
                self.soft_fail(str(exc))
            if name == "totals" and "totals_stats" not in pages.get("totals", ""):
                raise NoDataYet(f"NBA {season}: la temporada aún no tiene estadísticas")
        for key, url in (("teams_regular", f"{BASE}/leagues/NBA_{y}.html"),
                         ("teams_playoffs", f"{BASE}/playoffs/NBA_{y}.html")):
            try:
                pages[key] = http.get_text(url)
            except FetchError as exc:
                self.soft_fail(str(exc))
        return {"year": y, "pages": pages}

    def _players(self, soups: dict, suffix: str) -> list[dict]:
        rows: dict[tuple, dict] = {}
        for page, table in PLAYER_PAGES.items():
            soup = soups.get(page)
            if soup is None:
                continue
            for r in _table_rows(soup, table + suffix):
                team = r.get("team_name_abbr", "")
                href = r.get("name_display__href", "")
                m = _PID.search(href)
                if not m or re.fullmatch(r"\d+TM|TOT", team):
                    continue  # filas agregadas de traspasados o filas de cabecera / media
                tm = _TID.search(r.get("team_name_abbr__href", "")) or None
                key = (m.group(1), team)
                row = rows.setdefault(key, {"player_id": m.group(1), "team_id": tm.group(1) if tm else team,
                                            "nombre": r.get("name_display"), "equipo_codigo": team,
                                            "posicion": r.get("pos"), "edad": to_float(r.get("age"))})
                if page == "totals":
                    for k, c in COUNTING_MAP.items():
                        v = to_float(r.get(k))
                        if v is not None:
                            row[c] = v
                for k, c in EXTRA_COUNTING.get(page, {}).items():
                    if c and to_float(r.get(k)) is not None:
                        row[c] = to_float(r.get(k))
                for k, c in SRC_MAP.get(page, {}).items():
                    v = to_float(r.get(k))
                    if v is not None:
                        row[c] = v * 100 if c in _FRACTION else v
        players = list(rows.values())
        for p in players:
            complete_counting(p)
        return players

    @staticmethod
    def _teams(soup: BeautifulSoup | None) -> list[dict]:
        if soup is None:
            return []
        teams: dict[str, dict] = {}
        for table, prefix in (("totals-team", "team_"), ("totals-opponent", "opp_")):
            for r in _table_rows(soup, table):
                m = _TID.search(r.get("team__href", ""))
                if not m:
                    continue
                t = teams.setdefault(m.group(1), {"team_id": m.group(1),
                                                  "equipo": (r.get("team") or "").rstrip("*")})
                for k, c in TEAM_MAP.items():
                    v = to_float(r.get(k if prefix == "team_" or k in ("g", "mp") else f"opp_{k}"))
                    if v is None:
                        continue
                    if c == "gp":
                        if prefix == "team_":
                            t["team_gp"] = v
                        continue
                    t[f"{prefix}{c}"] = v
        for r in _table_rows(soup, "advanced-team"):
            m = _TID.search(r.get("team__href", ""))
            if m and m.group(1) in teams:
                teams[m.group(1)]["team_w"] = to_float(r.get("wins"))
                teams[m.group(1)]["team_l"] = to_float(r.get("losses"))
        for t in teams.values():
            complete_counting(t, "team_")
            complete_counting(t, "opp_")
        return list(teams.values())

    def parse(self, payload: Any, season: str) -> dict[str, ParsedLeague]:
        pages = payload.get("pages") or {}
        soups = {k: _soup(v) for k, v in pages.items() if k in PLAYER_PAGES}
        reg = ParsedLeague(players=self._players(soups, ""),
                           teams=self._teams(_soup(pages["teams_regular"]) if pages.get("teams_regular") else None),
                           notes=["Basketball-Reference: temporada regular"])
        po = ParsedLeague(players=self._players(soups, "_post"),
                          teams=self._teams(_soup(pages["teams_playoffs"]) if pages.get("teams_playoffs") else None),
                          notes=["Basketball-Reference: playoffs (incluye play-in según la web)"])
        names = {t["team_id"]: t.get("equipo") for t in reg.teams + po.teams}
        for p in reg.players + po.players:
            p["equipo"] = names.get(p["team_id"], p.get("equipo_codigo"))
        return {"regular": reg, "playoffs": po}
