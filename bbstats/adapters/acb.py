"""Liga Endesa (ACB) — boxscores oficiales de acb.com (HTML).

1. Calendario por jornada -> ids de partido  (/partido/estadisticas/id/<id>)
2. Página de estadísticas de cada partido   -> tablas por equipo (Min, P, T2, T3, T1, REB, A,
   BR, BP, C, TAP F/C, M, FP C/F, +/-, V) con fila 'Total'.
3. Agregación de boxscores -> totales de temporada exactos de jugador, equipo y rival.

Los partidos ya finalizados de la descarga anterior se reutilizan (no se vuelven a pedir).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from bs4 import BeautifulSoup

from ..http import FetchError, HttpClient
from ..utils import parse_made_attempted, parse_minutes, parse_sum_pair, to_float
from .base import AdapterError, BaseAdapter, ParsedLeague
from .boxscore import aggregate_games

DEFAULT_CALENDAR = ("https://www.acb.com/resultados-clasificacion/ver/temporada_id/{temporada_id}"
                    "/competicion_id/{competicion_id}/jornada_numero/{jornada}")
DEFAULT_GAME = "https://www.acb.com/partido/estadisticas/id/{game_id}"
GAME_ID_RE = re.compile(r"/partido/estadisticas/id/(\d+)")
PLAYER_ID_RE = re.compile(r"/jugador/[a-z\-]+/(?:id/)?(\d+)")
TEAM_ID_RE = re.compile(r"/club/[a-z\-]+/(?:id/)?(\d+)")

# etiqueta normalizada (grupo+subcolumna) -> campo
LABELS = {
    "D": "dorsal", "DORSAL": "dorsal", "NOMBRE": "name", "JUGADOR": "name",
    "MIN": "min", "P": "pts", "PTS": "pts", "PUNTOS": "pts",
    "T2": "t2", "T3": "t3", "T1": "t1",
    "REBT": "reb", "T": "reb", "REBOTEST": "reb", "REB": "reb",
    "REBD+O": "rebdo", "D+O": "rebdo", "REBOTESD+O": "rebdo",
    "A": "ast", "AS": "ast", "BR": "stl", "BP": "tov", "C": "fastbreaks",
    "TAPF": "blk", "TAPONESF": "blk", "TPF": "blk", "TAPC": "blka", "TAPONESC": "blka", "TPC": "blka",
    "M": "dunks", "FPC": "pf", "FALTASC": "pf", "FC": "pf", "FPF": "pfd", "FPR": "pfd",
    "FALTASR": "pfd", "FALTASF": "pfd", "FR": "pfd", "+/-": "plus_minus", "V": "pir", "VAL": "pir",
}


def _norm_label(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", "", s.upper())


def _header_labels(table) -> list[str]:
    """Cabecera (posiblemente en dos filas con rowspan/colspan) -> etiquetas planas 'GRUPO+SUB'.

    Ejemplo: 'Rebotes' (colspan=2) sobre 'T' y 'D+O' -> 'REBOTEST', 'REBOTESD+O'.
    """
    thead = table.find("thead")
    rows = thead.find_all("tr") if thead else \
        [tr for tr in table.find_all("tr") if tr.find("th") and not tr.find("td")]
    grid: dict[tuple[int, int], str] = {}
    ncols = 0
    for r, tr in enumerate(rows):
        c = 0
        for cell in tr.find_all(["th", "td"]):
            while (r, c) in grid:
                c += 1
            rs = int(cell.get("rowspan", 1) or 1)
            cs = int(cell.get("colspan", 1) or 1)
            txt = cell.get_text(" ", strip=True)
            for dr in range(rs):
                for dc in range(cs):
                    grid[(r + dr, c + dc)] = txt
            c += cs
            ncols = max(ncols, c)
    labels = []
    for c in range(ncols):
        parts: list[str] = []
        for r in range(len(rows)):
            t = grid.get((r, c), "")
            if t and (not parts or parts[-1] != t):
                parts.append(t)
        labels.append(_norm_label("".join(parts)))
    return labels


def _row_to_line(labels: list[str], cells, starter_mark: str = "*") -> dict:
    line: dict[str, Any] = {}
    for lab, cell in zip(labels, cells):
        field = LABELS.get(lab)
        txt = cell.get_text(" ", strip=True)
        if field is None:
            continue
        if field == "name":
            line["name"] = txt
            a = cell.find("a", href=PLAYER_ID_RE)
            if a:
                line["player_id"] = PLAYER_ID_RE.search(a["href"]).group(1)
        elif field == "dorsal":
            line["starter"] = starter_mark in txt
            line["dorsal"] = txt.replace(starter_mark, "").strip()
        elif field == "min":
            line["min"] = parse_minutes(txt)
        elif field in ("t2", "t3", "t1"):
            m, a = parse_made_attempted(txt)
            key = {"t2": "fg2", "t3": "fg3", "t1": "ft"}[field]
            line[f"{key}m"], line[f"{key}a"] = m, a
        elif field == "rebdo":
            d, o = parse_sum_pair(txt)
            line["dreb"], line["oreb"] = d, o
        else:
            line[field] = to_float(txt)
    return line


def parse_acb_game(game_id: str, html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    sides = []
    for table in soup.find_all("table"):
        labels = _header_labels(table)
        if "MIN" not in labels or not any(l in labels for l in ("T2", "P", "PTS")):
            continue
        body = table.find("tbody") or table
        players, totals = [], None
        for tr in body.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) < len(labels) - 2 or tr.find_parent("thead"):
                continue
            line = _row_to_line(labels, cells)
            nm = (line.get("name") or "").strip().lower()
            first = cells[0].get_text(" ", strip=True).lower()
            if nm.startswith("total") or first.startswith("total"):
                totals = {k: v for k, v in line.items() if k not in {"name", "dorsal", "starter", "player_id"}}
            elif nm in {"equipo", "equipo:"} or first == "equipo" or not nm:
                continue  # rebotes de equipo: quedan dentro de 'Total'
            else:
                players.append(line)
        # nombre / id del equipo: título o enlace anterior a la tabla
        name, team_id = None, None
        cap = table.find("caption")
        heading = cap or table.find_previous(
            lambda tag: tag.name in {"h1", "h2", "h3", "h4", "h5", "h6", "div", "span", "a"}
            and tag.get("class") and any(re.search(r"equipo|team|nombre", c) for c in tag.get("class")))
        if heading is not None:
            name = heading.get_text(" ", strip=True) or None
            link = heading if heading.name == "a" and heading.get("href") else heading.find("a", href=TEAM_ID_RE)
            if link is not None and link.get("href") and TEAM_ID_RE.search(link["href"]):
                team_id = TEAM_ID_RE.search(link["href"]).group(1)
        roster = frozenset(p.get("player_id") or p.get("name") for p in players)
        if not players or any(sd["_roster"] == roster for sd in sides):
            continue  # tabla vacía o duplicada (p.ej. versión móvil de la misma tabla)
        sides.append({"_roster": roster, "team_id": team_id or name or f"equipo_{len(sides) + 1}", "name": name,
                      "code": None, "totals": totals, "players": players})
    sides = sides[:2]
    for sd in sides:
        sd.pop("_roster", None)
    # Si no se pudo leer el nombre de los equipos, usar el <title> 'Local - Visitante'
    if len(sides) == 2 and (not sides[0]["name"] or sides[0]["team_id"] == sides[1]["team_id"]):
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        parts = re.split(r"\s+(?:-|vs\.?|–)\s+", title.split("|")[0])
        if len(parts) >= 2:
            for side, nm in zip(sides, parts[:2]):
                side["name"] = nm.strip()
                side["team_id"] = nm.strip()
    final = len(sides) == 2 and all(s["totals"] and s["totals"].get("pts") is not None for s in sides)
    date = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", soup.get_text(" "))
    return {"game_id": str(game_id), "date": date.group(1) if date else None, "final": final, "teams": sides}


class ACBAdapter(BaseAdapter):
    name = "acb"
    version = "1.0"

    def fetch(self, season: str, http: HttpClient, previous_payload: Any | None = None) -> Any:
        sc = self.season_cfg(season)
        fmt = {"temporada_id": sc.get("temporada_id", sc["start_year"]),
               "competicion_id": sc.get("competicion_id", self.cfg.get("competicion_id", 1))}
        cal_tpl = self.cfg.get("calendar_url", DEFAULT_CALENDAR)
        max_j = int(self.cfg.get("max_jornadas", 45))
        calendar: dict[str, str] = {}
        ids: list[str] = list(map(str, sc.get("game_ids", [])))
        empty_streak = 0
        for j in range(1, max_j + 1):
            try:
                html = http.get_text(cal_tpl.format(jornada=j, **fmt))
            except FetchError as exc:
                self.soft_fail(str(exc))
                empty_streak += 1
                if empty_streak >= 3 and ids:
                    break
                continue
            calendar[str(j)] = html
            found = GAME_ID_RE.findall(html)
            empty_streak = 0 if found else empty_streak + 1
            ids.extend(found)
            if empty_streak >= 3 and ids:
                break
        ids = list(dict.fromkeys(ids))
        if not ids:
            raise AdapterError("ACB: no se encontraron partidos en el calendario")
        prev = (previous_payload or {}).get("games", {}) if isinstance(previous_payload, dict) else {}
        games: dict[str, str] = {}
        reused = 0
        for gid in ids:
            if gid in prev and parse_acb_game(gid, prev[gid])["final"]:
                games[gid] = prev[gid]
                reused += 1
                continue
            try:
                games[gid] = http.get_text(self.cfg.get("game_url", DEFAULT_GAME).format(game_id=gid))
            except FetchError as exc:
                self.soft_fail(str(exc))
        return {"params": fmt, "calendar": calendar, "games": games, "reused_games": reused}

    def parse(self, payload: Any, season: str) -> ParsedLeague:
        games = [parse_acb_game(gid, html) for gid, html in (payload.get("games") or {}).items()]
        notes = [f"{len(games)} páginas de partido ACB; {payload.get('reused_games', 0)} reutilizadas"]
        return aggregate_games(games, notes)
