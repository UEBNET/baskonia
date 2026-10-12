"""easyCredit BBL (Alemania) — datos embebidos en las páginas públicas de partido de easycredit-bbl.de.

La API de la BBL (api.basketball-bundesliga.de) exige credenciales de su web, así que se lee el
JSON que cada página pública de partido incluye (`__NEXT_DATA__`):
    https://www.easycredit-bbl.de/spiele/<id>
  initialGameData : temporada, competición (BBL / BBL_CUP), fase (MAIN_ROUND, PLAYINS, ROUND_OF_8,
                    SEMI_FINALS, FINALS), estado, equipos y resultado
  initialGameStats: boxscore por equipo (gameStat) y por jugador (playerStats: segundos, tiros,
                    rebotes, asistencias, robos, pérdidas, tapones, faltas cometidas y recibidas,
                    titular, +/-, valoración)

Descubrimiento de partidos: los ids de cada temporada forman bloques consecutivos (temporada
regular por un lado y playoffs por otro). Se parte de ids semilla (config `semillas`, y para la
temporada en curso los partidos de /saison/aktuelle-spiele) y se recorre cada bloque hacia
ambos lados hasta encontrar `max_huecos` ids seguidos sin partido de la temporada.
En el bruto se guarda el JSON de datos de cada página (sin el HTML ni los menús).
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..http import FetchError, HttpClient
from ..utils import to_float
from .base import BaseAdapter, NoDataYet, ParsedLeague
from .boxscore import aggregate_by_phase

SITE = "https://www.easycredit-bbl.de"
_NEXT = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
REGULAR_STAGES = {"MAIN_ROUND"}
_MAP = {"points": "pts", "twoPointShotsMade": "fg2m", "twoPointShotsAttempted": "fg2a",
        "threePointShotsMade": "fg3m", "threePointShotsAttempted": "fg3a", "freeThrowsMade": "ftm",
        "freeThrowsAttempted": "fta", "fieldGoalsMade": "fgm", "fieldGoalsAttempted": "fga",
        "offensiveRebounds": "oreb", "defensiveRebounds": "dreb", "totalRebounds": "reb", "assists": "ast",
        "steals": "stl", "turnovers": "tov", "blocks": "blk", "foulsCommitted": "pf", "foulsReceived": "pfd",
        "plusMinus": "plus_minus", "efficiency": "src_eff"}


def _stats(rec: dict) -> dict:
    out = {c: to_float(rec.get(k)) for k, c in _MAP.items() if rec.get(k) is not None}
    if rec.get("secondsPlayed") is not None:
        out["min"] = to_float(rec["secondsPlayed"]) / 60.0
    return {k: v for k, v in out.items() if v is not None}


def _page_data(html: str) -> dict | None:
    m = _NEXT.search(html or "")
    if not m:
        return None
    pp = (json.loads(m.group(1)).get("props") or {}).get("pageProps") or {}
    if not pp.get("initialGameData"):
        return None
    return {"initialGameData": pp.get("initialGameData"), "initialGameStats": pp.get("initialGameStats")}


def parse_game(doc: dict) -> dict:
    gd = doc.get("initialGameData") or {}
    gs = doc.get("initialGameStats") or {}
    sides = []
    for key, tkey in (("homeTeam", "homeTeam"), ("guestTeam", "guestTeam")):
        info = gd.get(tkey) or {}
        st = gs.get(key) or {}
        players = []
        for p in st.get("playerStats") or []:
            sp = p.get("seasonPlayer") or {}
            line = {"player_id": str(sp.get("playerId") or sp.get("id")),
                    "name": f"{sp.get('firstName', '')} {sp.get('lastName', '')}".strip(),
                    "dorsal": sp.get("shirtNumber"), "posicion": sp.get("position"),
                    "starter": bool(p.get("isStartingFive"))}
            line.update(_stats(p))
            line.pop("src_eff", None)
            players.append(line)
        totals = _stats(st.get("gameStat") or {})
        totals.pop("plus_minus", None)
        totals.pop("src_eff", None)
        sides.append({"team_id": str(info.get("teamId")), "name": info.get("name"), "code": info.get("tlc"),
                      "totals": totals, "players": players})
    phase = "regular" if gd.get("stage") in REGULAR_STAGES else "playoffs"
    return {"game_id": str(gd.get("id")), "phase": phase, "final": gd.get("status") == "OFFICIAL",
            "teams": sides, "date": gd.get("scheduledTime")}


class BBLAdapter(BaseAdapter):
    name = "bbl"
    version = "1.0"

    def _game(self, http: HttpClient, gid: int) -> dict | None:
        resp = http.get(f"{SITE}/spiele/{gid}", ok_status=(400, 404))
        if not resp.ok:
            return None
        return _page_data(resp.text)

    @staticmethod
    def block_starts(ids: list[int], max_gap: int) -> list[int]:
        """Primer id de cada bloque de partidos (bloques separados por más de `max_gap` ids)."""
        out: list[int] = []
        prev = None
        for gid in sorted(ids):
            if prev is None or gid - prev > max_gap:
                out.append(gid)
            prev = gid
        return out

    @staticmethod
    def _is_past(season: str) -> bool:
        from datetime import date
        today = date.today()
        current_start = today.year if today.month >= 8 else today.year - 1
        return int(season[:4]) < current_start

    def _current_seeds(self, http: HttpClient) -> list[int]:
        try:
            html = http.get_text(f"{SITE}/saison/aktuelle-spiele")
        except FetchError as exc:
            self.soft_fail(str(exc))
            return []
        return sorted({int(x) for x in re.findall(r'"id":\s*"(\d{7})"', html)})

    def _probe(self, http: HttpClient, gid: int) -> dict:
        try:
            doc = self._game(http, gid)
        except FetchError as exc:
            self.soft_fail(str(exc))
            doc = None
        return (doc or {}).get("initialGameData") or {}

    def _discover_seeds(self, http: HttpClient, year: int) -> list[int]:
        """Temporadas pasadas sin `semillas`: busca ids de partido de esa temporada.

        Paso A: parte del id semilla más bajo conocido de una temporada posterior (config o temporada
        en curso) y baja en saltos de `paso_busqueda` ids leyendo la temporada de cada página; se para
        cuando las páginas ya son de dos temporadas anteriores o tras muchos saltos vacíos.
        Paso B: si no ha aparecido la temporada regular (MAIN_ROUND), recorre de arriba abajo los
        `rangos_busqueda` en saltos de `paso_rango`. Hace falta porque la web cambió de numeración en
        2025: hasta la temporada regular 2024-25 los ids son bajos (p.ej. 2020-21 ≈ 25500) y desde los
        playoffs 2024-25 empiezan en 2003000; entre medias hay partidos históricos (1968-1998) importados.
        Se devuelven todos los ids de la temporada buscada que aparezcan (regular y playoffs van en
        bloques distintos); fetch() recorre después cada bloque entero.
        """
        comp = self.cfg.get("competicion", "BBL")
        later = [int(x) for t, v in (self.cfg.get("temporadas") or {}).items()
                 if int(t[:4]) > year for x in (v.get("semillas") or [])]
        anchors = later or self._current_seeds(http)
        found: list[int] = []
        regular = False
        if anchors:
            step = int(self.cfg.get("paso_busqueda", 40))
            max_probes = int(self.cfg.get("max_saltos_busqueda", 1500))
            gid, empty, older = min(anchors), 0, 0
            for _ in range(max_probes):
                gid -= step
                if gid <= 0:
                    break
                gd = self._probe(http, gid)
                sid = gd.get("seasonId")
                if sid is None:
                    empty += 1
                    if empty > 150:
                        break
                    continue
                empty = 0
                if sid == year and gd.get("competition") == comp:
                    found.append(gid)
                    regular |= gd.get("stage") in REGULAR_STAGES
                older = older + 1 if sid < year - 1 else 0
                if older >= 25:
                    break
        if not regular:
            step = int(self.cfg.get("paso_rango", 100))
            for lo, hi in self.cfg.get("rangos_busqueda", [[1, 40000]]):
                gid, after = int(hi), 0
                while gid >= int(lo):
                    gd = self._probe(http, gid)
                    sid = gd.get("seasonId")
                    if sid == year and gd.get("competition") == comp:
                        found.append(gid)
                        after = 0
                        regular |= gd.get("stage") in REGULAR_STAGES
                    elif regular and sid is not None and sid < year:
                        after += 1
                        if after >= 15:  # ya por debajo de la temporada regular buscada
                            break
                    gid -= step
                if regular:
                    break
        if regular and found:
            # Paso C: en la numeración antigua los playoffs quedan lejos de su temporada regular (p.ej.
            # 2022-23: regular 27480-27770, playoffs ≈ 30500) y hay partidos sueltos; se barre una ventana
            # alrededor de lo encontrado en saltos finos para recogerlos.
            window = int(self.cfg.get("ventana_busqueda", 3500))
            step = int(self.cfg.get("paso_fino", 10))
            known = set(found)
            for gid in range(max(1, min(found) - window), max(found) + window + 1, step):
                if gid in known:
                    continue
                gd = self._probe(http, gid)
                if gd.get("seasonId") == year and gd.get("competition") == comp:
                    found.append(gid)
        return sorted(set(found))

    def fetch(self, season: str, http: HttpClient, previous_payload: Any | None = None) -> Any:
        sc = self.season_cfg(season)
        year = int(sc.get("season_id", sc["start_year"]))
        max_gap = int(self.cfg.get("max_huecos", 30))
        prev = (previous_payload or {}).get("games", {}) if isinstance(previous_payload, dict) else {}
        seeds = [int(x) for x in sc.get("semillas", [])]
        if not seeds:
            seeds = self._current_seeds(http) if "semillas" in sc else []
        discovered = False
        if not seeds or (self._is_past(season) and "semillas" not in sc):
            found = self._discover_seeds(http, year)
            discovered = bool(found)
            seeds = found or seeds
        games: dict[str, Any] = {}
        visited: set[int] = set()
        reused = 0

        def get(gid: int) -> dict | None:
            nonlocal reused
            visited.add(gid)
            if str(gid) in prev and (prev[str(gid)].get("initialGameData") or {}).get("status") == "OFFICIAL":
                reused += 1
                return prev[str(gid)]
            try:
                return self._game(http, gid)
            except FetchError as exc:
                self.soft_fail(str(exc))
                return None

        for seed in seeds:
            if seed in visited:
                continue
            for step in (-1, 1):
                gid, gap = seed if step == 1 else seed - 1, 0
                while gap < max_gap:
                    if gid in visited and str(gid) not in games:
                        gid += step
                        gap += 1
                        continue
                    doc = games.get(str(gid)) or get(gid)
                    gd = (doc or {}).get("initialGameData") or {}
                    if gd.get("seasonId") == year and gd.get("competition") == self.cfg.get("competicion", "BBL"):
                        games[str(gid)] = doc
                        gap = 0
                    else:
                        gap += 1
                    gid += step
        finished = {k: v for k, v in games.items() if (v.get("initialGameData") or {}).get("status") == "OFFICIAL"}
        if not finished:
            raise NoDataYet(f"BBL {season}: no se encontraron partidos finalizados (revisa 'semillas')")
        n_teams = len({t.get("teamId") for v in finished.values() for t in
                       ((v.get("initialGameData") or {}).get("homeTeam") or {},
                        (v.get("initialGameData") or {}).get("guestTeam") or {}) if t.get("teamId")})
        n_regular = sum((v.get("initialGameData") or {}).get("stage") in REGULAR_STAGES for v in finished.values())
        if self._is_past(season) and n_teams and n_regular < n_teams * (n_teams - 1):
            self.soft_fail(f"BBL {season}: {n_regular} partidos de temporada regular encontrados; "
                           f"con {n_teams} equipos deberían ser {n_teams * (n_teams - 1)}")
        has_regular = any((v.get("initialGameData") or {}).get("stage") in REGULAR_STAGES for v in finished.values())
        if discovered and has_regular:
            # Se guardan en config/sources.json (lo hace el pipeline): la próxima ejecución de esta
            # temporada no repite la búsqueda y la temporada anterior la empieza desde aquí.
            # Sólo si está la temporada regular: unas semillas a medias impedirían volver a buscar.
            block_seeds = self.block_starts([int(g) for g in finished], max_gap)
            self.config_updates = {"temporadas": {season: {"semillas": block_seeds}}}
        elif discovered:
            self.soft_fail(f"BBL {season}: no se encontró la temporada regular; semillas no guardadas")
        return {"season_id": year, "seeds": seeds, "games": finished, "reused_games": reused,
                "ids_scanned": len(visited)}

    def parse(self, payload: Any, season: str) -> dict[str, ParsedLeague]:
        games = [parse_game(doc) for doc in (payload.get("games") or {}).values()]
        return aggregate_by_phase(games, [f"{len(games)} partidos BBL; {payload.get('reused_games', 0)} reutilizados; "
                                          f"{payload.get('ids_scanned')} ids explorados"])
