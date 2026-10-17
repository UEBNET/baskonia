"""Competiciones de FIBA Europa (Basketball Champions League, FIBA Europe Cup): páginas públicas de fiba.basketball.

Las páginas de la web de FIBA (Next.js) incluyen en su HTML (flujo RSC `self.__next_f.push`) los datos que
muestran; no se usa la API `digital-api.fiba.basketball/hapi`, que exige una clave de suscripción.

  Calendario  https://www.fiba.basketball/en/history/<ruta_historia>/<competition_id>/games
              todos los partidos de la competición con gameId, ronda (roundCode, roundName, roundType G = de
              grupo / NG = eliminatoria), estado (statusCode VALID = acta cerrada), equipos y resultado.
              (Para las temporadas recientes también /en/events/<slug>/games, que redirige o es equivalente.)
  Partido     https://www.fiba.basketball/en/games/<gameId>   (redirige a la página canónica)
              game (cabecera), gameDetails (boxscore: c[] por equipo con Stats de equipo y Children[] =
              jugadores P_<personId> con Stats), playersTeamA/B (nombre, dorsal, posición), playByPlay
              (items por periodo: ac = código de acción, pId/oId = persona/organización, Time = reloj
              restante, SA/SB = marcador, x/y del tiro) y staffA/staffB (entrenadores).

En el bruto se guarda, por partido, sólo ese JSON de datos (sin HTML, menús ni textos de la web) y el boxscore
y el jugada a jugada salen del MISMO documento (la capa de quintetos lo lee del bruto principal).

Fases: rondas de grupo (roundType G: Regular Season, Round of 16 / Second Round) = `regular`; eliminatorias
(roundType NG: Play-ins, cuartos, semifinales, final, tercer puesto) = `playoffs`; las rondas de clasificación
(`rondas_excluidas`, p.ej. Q = Qualifiers y QT = Qualifying Tournaments de la FIBA Europe Cup) no se cargan.
Ids: equipo = organisationId (estable entre temporadas; es el oId del jugada a jugada), jugador = personId.

Bruto INCREMENTAL: cada ejecución guarda sólo los partidos nuevos (troceados en paquetes de
`partidos_por_paquete`); el pipeline une todos los paquetes de la temporada (RawStore.load_season).
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from ..http import FetchError, HttpClient
from ..utils import parse_minutes, to_float
from .base import AdapterError, BaseAdapter, NoDataYet, ParsedLeague
from .boxscore import aggregate_by_phase

SITE = "https://www.fiba.basketball"
_PUSH = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')
EXCLUDED_ROUNDS = ("Q", "QT", "QR", "Q1", "Q2", "Q3")
_MAP = {"PTS": "pts", "FG2M": "fg2m", "FG2A": "fg2a", "FG3M": "fg3m", "FG3A": "fg3a", "FTM": "ftm", "FTA": "fta",
        "FGM": "fgm", "FGA": "fga", "OR": "oreb", "DR": "dreb", "REB": "reb", "AS": "ast", "ST": "stl", "TO": "tov",
        "BS": "blk", "BSR": "blka", "PF": "pf", "FD": "pfd", "PM": "plus_minus", "EFF": "src_eff"}
_TEAM_EXTRA = {"A_PIP": "pts_paint", "A_SCP": "pts_2ndchance", "A_FBP": "pts_fastbreak", "A_PAT": "pts_off_tov"}


def flight_text(html: str) -> str:
    """Texto del flujo RSC de una página Next.js (concatenación de los self.__next_f.push)."""
    return "".join(json.loads(m.group(1)) for m in _PUSH.finditer(html or ""))


def _enclosing(text: str, marker: str, key: str) -> dict | None:
    """Objeto JSON más interno del texto que contiene `marker` y tiene la clave `key`."""
    i = text.find(marker)
    if i < 0:
        return None
    dec = json.JSONDecoder()
    j = i
    while j > 0:
        j = text.rfind("{", 0, j)
        if j < 0:
            return None
        try:
            obj, end = dec.raw_decode(text, j)
        except ValueError:
            continue
        if end > i and isinstance(obj, dict) and key in obj:
            return obj
    return None


def page_doc(html: str) -> dict | None:
    """JSON de datos de una página de partido: {"page": {game, gameDetails, playersTeamA/B, playByPlay,
    teamAScore, teamBScore, technicalName, pageStatus}, "staff": {staffA, staffB}}."""
    text = flight_text(html)
    page = _enclosing(text, '"gameDetails":{', "gameDetails")
    if not page or not isinstance(page.get("game"), dict):
        return None
    keep = ("technicalName", "pageStatus", "game", "playByPlay", "playersTeamA", "playersTeamB", "gameDetails",
            "teamAScore", "teamBScore")
    staff = _enclosing(text, '"staffA":', "staffA") or {}
    return {"page": {k: page.get(k) for k in keep},
            "staff": {k: staff.get(k) for k in ("staffA", "staffB") if k in staff}}


def schedule_games(html: str, competition_id: int | None = None) -> list[dict]:
    """Partidos del calendario (objetos con gameId, round y competition) de una página de calendario."""
    text = flight_text(html)
    dec = json.JSONDecoder()
    out: dict[int, dict] = {}
    for m in re.finditer(r'\{"gameId":', text):
        try:
            obj, _ = dec.raw_decode(text, m.start())
        except ValueError:
            continue
        if not isinstance(obj.get("round"), dict) or not isinstance(obj.get("competition"), dict):
            continue
        if competition_id and int(obj["competition"].get("competitionId") or 0) != int(competition_id):
            continue
        out.setdefault(int(obj["gameId"]), obj)
    return [out[k] for k in sorted(out)]


def round_phase(rnd: dict, excluded=EXCLUDED_ROUNDS) -> str | None:
    """Fase de una ronda: None = clasificación (excluida), "regular" = grupos, "playoffs" = eliminatoria."""
    code = str(rnd.get("roundCode") or "")
    name = str(rnd.get("roundName") or "").lower()
    if code in excluded or "qualif" in name:
        return None
    return "regular" if rnd.get("roundType") == "G" else "playoffs"


def is_final(game: dict) -> bool:
    return (game or {}).get("statusCode") == "VALID" and (game or {}).get("teamAScore") is not None


def _stats(rec: dict | None) -> dict:
    rec = rec or {}
    out = {c: to_float(rec.get(k)) for k, c in _MAP.items() if rec.get(k) is not None}
    if rec.get("TP") not in (None, ""):
        out["min"] = parse_minutes(rec.get("TP"))
    return {k: v for k, v in out.items() if v is not None}


def team_ids(doc: dict) -> tuple[str | None, str | None]:
    g = (doc.get("page") or {}).get("game") or {}
    a, b = g.get("teamA") or {}, g.get("teamB") or {}
    return (str(a["organisationId"]) if a.get("organisationId") else None,
            str(b["organisationId"]) if b.get("organisationId") else None)


def parse_game(doc: dict, phase: str = "regular") -> dict:
    """Documento de partido del bruto -> formato estándar de boxscore (ver boxscore.py)."""
    page = doc.get("page") or {}
    g = page.get("game") or {}
    gd = page.get("gameDetails") or {}
    by_team = {str(c.get("Id", "")).removeprefix("T_"): c for c in gd.get("c") or []}
    sides = []
    for key, roster_key in (("teamA", "playersTeamA"), ("teamB", "playersTeamB")):
        t = g.get(key) or {}
        tid = str(t.get("organisationId") or t.get("teamId"))
        roster = {str(p.get("personId")): p for p in page.get(roster_key) or []}
        c = by_team.get(tid) or {}
        players = []
        for ch in c.get("Children") or []:
            pid = str(ch.get("Id", "")).removeprefix("P_")
            st = ch.get("Stats") if isinstance(ch.get("Stats"), dict) else {}
            info = roster.get(pid, {})
            line = {"player_id": pid,
                    "name": f"{info.get('firstName') or ''} {info.get('lastName') or ''}".strip() or pid,
                    "dorsal": info.get("uniformNumber"), "posicion": info.get("position"),
                    "starter": bool(st.get("Starter"))}
            line.update(_stats(st))
            if not st.get("HasPlayed", True):
                line["min"] = 0.0
            players.append(line)
        tst = c.get("Stats") if isinstance(c.get("Stats"), dict) else {}
        totals = _stats(tst)
        totals.pop("min", None)
        totals.pop("plus_minus", None)
        totals.update({c2: to_float(tst.get(k)) for k, c2 in _TEAM_EXTRA.items() if tst.get(k) is not None})
        if totals.get("pts") is None and c.get("Score") is not None:
            totals["pts"] = to_float(c.get("Score"))
        sides.append({"team_id": tid, "name": t.get("shortName") or t.get("officialName"), "code": t.get("code"),
                      "totals": totals, "players": players})
    return {"game_id": str(g.get("gameId")), "phase": phase, "final": is_final(g), "teams": sides,
            "date": g.get("gameDateTimeUTC") or g.get("gameDateTime")}


class FibaWebAdapter(BaseAdapter):
    name = "fiba_web"
    version = "1.0"

    def _get(self, http: HttpClient, url: str) -> str:
        return http.get_text(url, headers={"Accept": "text/html"})

    def _schedule_url(self, cid: int) -> str:
        return f"{SITE}/en/history/{self.cfg['ruta_historia']}/{cid}/games"

    def _discover_competition(self, season: str, http: HttpClient) -> tuple[int, str]:
        """competition_id de la temporada desde la página del evento (/en/events/<slug>-YY-YY/games)."""
        y = int(season[:4])
        slug = self.cfg["slug_evento"].format(yy1=f"{y % 100:02d}", yy2=f"{(y + 1) % 100:02d}")
        html = self._get(http, f"{SITE}/en/events/{slug}/games")
        cids = {int(x) for x in re.findall(r'"competitionId":(\d+),"competitionCode":"' + re.escape(
            self.cfg["codigo_competicion"]) + r'","season":' + str(y + 1), flight_text(html))}
        if len(cids) != 1:
            raise NoDataYet(f"{self.league} {season}: competición no encontrada en /en/events/{slug} ({cids})")
        return cids.pop(), html

    def fetch(self, season: str, http: HttpClient, previous_payload: Any | None = None) -> Any:
        sc = self.season_cfg(season)
        cid = sc.get("competition_id")
        html = None
        if not cid:
            cid, html = self._discover_competition(season, http)
            self.config_updates = {"temporadas": {season: {"competition_id": cid}}}
        url = self._schedule_url(int(cid))
        schedule = []
        for attempt in range(3):   # la web a veces sirve la página sin los datos: se reintenta
            schedule = schedule_games(self._get(http, url), int(cid))
            if schedule:
                break
            time.sleep(2 + 3 * attempt)
        if not schedule and html:
            schedule = schedule_games(html, int(cid))
        if not schedule:
            raise NoDataYet(f"{self.league} {season}: calendario vacío ({url})")
        excluded = tuple(self.cfg.get("rondas_excluidas", EXCLUDED_ROUNDS))
        prev = (previous_payload or {}).get("games", {}) if isinstance(previous_payload, dict) else {}
        block = int(self.cfg.get("partidos_por_paquete", 400))
        new: dict[str, dict] = {}
        reused = n_new = 0
        for gm in schedule:
            if round_phase(gm["round"], excluded) is None or not is_final(gm):
                continue
            gid = str(gm["gameId"])
            old = prev.get(gid)
            if old and is_final((old.get("page") or {}).get("game") or {}):
                reused += 1
                continue
            doc = None
            for attempt in range(4):   # la web sirve a veces la página sin datos (caché): se reintenta
                try:
                    doc = page_doc(self._get(http, f"{SITE}/en/games/{gid}"))
                except FetchError as exc:
                    self.soft_fail(str(exc))
                    break
                if doc:
                    break
                time.sleep(1.5 * (attempt + 1))
            if not doc:
                self.soft_fail(f"{gid}: la página no trae datos de partido")
                continue
            new[gid] = doc
            n_new += 1
            if len(new) >= block:
                self.save_partial(season, {"competition_id": cid, "games": new})
                new = {}
        n_final = sum(1 for gm in schedule if is_final(gm))
        if not new and not prev and not n_new:
            raise NoDataYet(f"{self.league} {season}: aún no hay partidos descargados "
                            f"({len(schedule)} en el calendario, {n_final} finalizados; errores: {self.errors[:3]})")
        return {"incremental": True, "competition_id": cid, "calendario": schedule, "games": new,
                "reused_games": reused, "partidos_nuevos": n_new}

    def phase_of(self, payload: dict) -> dict[str, str | None]:
        excluded = tuple(self.cfg.get("rondas_excluidas", EXCLUDED_ROUNDS))
        return {str(g["gameId"]): round_phase(g["round"], excluded) for g in payload.get("calendario") or []}

    def parse(self, payload: Any, season: str) -> dict[str, ParsedLeague]:
        phases = self.phase_of(payload)
        games = []
        for gid, doc in sorted((payload.get("games") or {}).items()):
            g = (doc.get("page") or {}).get("game") or {}
            ph = phases.get(gid) or (round_phase(g["round"], tuple(self.cfg.get("rondas_excluidas", EXCLUDED_ROUNDS)))
                                     if isinstance(g.get("round"), dict) else "regular")
            if ph is None:
                continue
            games.append(parse_game(doc, ph))
        if not games:
            raise AdapterError(f"{self.league}: el bruto no contiene partidos")
        return aggregate_by_phase(games, [f"{len(games)} partidos fiba.basketball; "
                                          f"{payload.get('reused_games', 0)} reutilizados"])
