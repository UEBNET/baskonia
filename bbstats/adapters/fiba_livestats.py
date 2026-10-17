"""FIBA LiveStats (Genius Sports) — data.json partido a partido (boxscore + jugada a jugada + tiros).

    https://fibalivestats.dcd.shared.geniussports.com/data/{match_id}/data.json

  tm["1"|"2"]   equipo (name, code, score, coach/coachDetails), totales tot_s*, jugadores pl[pno] (sMinutes,
                sPlusMinusPoints, starter, s* de conteo, nombre) y tiros shot[] (x, y en % de la pista completa)
  pbp[]         jugada a jugada (orden DESCENDENTE de actionNumber): actionType, subType, success, tno, pno,
                period, periodType, gt (reloj restante "MM:SS"), previousAction, qualifier, s1/s2

El data.json no dice a qué competición pertenece el partido (ni la fecha): los ids de una liga se localizan
en `config/sources.json` → `ligas.<liga>.temporadas.<t>.partidos` ({"regular": [...], "playoffs": [...]},
cada elemento un id o un rango [desde, hasta]); `excluir` = ids de esos rangos que no son de la liga.
Si una fase no tiene `partidos` pero sí `semillas` (ids conocidos de esa fase), se DESCUBRE: los ids de una
liga se crean en bloques casi consecutivos, así que se recorre cada bloque hacia ambos lados (petición con
Range de los primeros bytes: nombre del equipo local) aceptando los partidos de equipos de la liga, hasta
`max_huecos` ids seguidos ajenos; el resultado se guarda en config (`partidos`). Ver `discover_block`.

También acepta la configuración antigua (genérica): `temporadas.<t>.match_ids` y `temporadas.<t>.discovery`
(páginas de calendario + regex de ids).

Ids: jugador = apellido|nombre internacionales normalizados (el data.json no trae personId); equipo = nombre
del equipo normalizado (o `alias_equipos` de la config).
Bruto INCREMENTAL (como fiba_web): cada ejecución guarda sólo los partidos nuevos; los paquetes se unen al leer.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
from typing import Any, Callable

from ..http import FetchError, HttpClient
from ..normalize import map_counting
from ..utils import height_to_cm, parse_minutes, to_float
from .base import AdapterError, BaseAdapter, NoDataYet, ParsedLeague
from .boxscore import aggregate_by_phase

DEFAULT_DATA_URL = "https://fibalivestats.dcd.shared.geniussports.com/data/{match_id}/data.json"
DEFAULT_ID_REGEX = r"fibalivestats\.dcd\.shared\.geniussports\.com/(?:u/[A-Za-z0-9]+/|data/)(\d{5,8})"
_NAME = re.compile(r'"name":"((?:[^"\\]|\\.)*)"')
_EXTRA = {"sPointsInThePaint": "pts_paint", "sPointsSecondChance": "pts_2ndchance",
          "sPointsFastBreak": "pts_fastbreak", "sPointsFromTurnovers": "pts_off_tov"}


def norm(s: Any) -> str:
    """Texto sin acentos, en minúsculas y con espacios simples (para comparar nombres)."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def greek_norm(s: Any) -> str:
    """Como norm() pero conservando letras griegas sin tildes (los nombres griegos no tienen forma ASCII)."""
    s = "".join(c for c in unicodedata.normalize("NFKD", str(s or "")) if not unicodedata.combining(c))
    return re.sub(r"[^0-9a-zα-ω]+", " ", s.lower()).strip()


def team_key(t: dict, aliases: dict | None = None) -> str:
    name = t.get("name") or t.get("nameInternational") or t.get("shortName") or t.get("code") or ""
    k = greek_norm(name)
    return (aliases or {}).get(k, k)


def player_key(p: dict) -> str:
    fam = p.get("internationalFamilyName") or p.get("familyName") or ""
    first = p.get("internationalFirstName") or p.get("firstName") or ""
    k = f"{greek_norm(fam)}|{greek_norm(first)}"
    return k if k != "|" else greek_norm(p.get("name") or p.get("scoreboardName"))


def _is_final(doc: Any) -> bool:
    if not isinstance(doc, dict):
        return False
    status = str(doc.get("periodStatus") or doc.get("status") or doc.get("matchStatus") or "").lower()
    if status in {"finished", "final", "complete", "completed", "ended", "endofgame"}:
        return True
    if any(e.get("actionType") == "game" and e.get("subType") == "end" for e in (doc.get("pbp") or [])[:5]):
        return True
    tm = doc.get("tm") or {}
    try:
        s1, s2 = to_float(tm["1"].get("score")), to_float(tm["2"].get("score"))
    except (KeyError, AttributeError):
        return False
    clock = str(doc.get("clock") or "")
    period = to_float(doc.get("period")) or 0
    return s1 is not None and s2 is not None and s1 != s2 and period >= 4 and clock in {"00:00", "0:00", "00:00:00"}


def parse_fiba_game(match_id: str, doc: dict, phase: str = "regular", aliases: dict | None = None) -> dict:
    """data.json de FIBA LiveStats -> formato estándar de partido (ver boxscore.py)."""
    sides = []
    for k in ("1", "2"):
        t = (doc.get("tm") or {}).get(k) or {}
        name = t.get("name") or t.get("nameInternational") or t.get("shortName")
        code = t.get("code") or t.get("shortName")
        tot_rec = {key[4:]: v for key, v in t.items() if key.startswith("tot_")}
        totals = map_counting(tot_rec)
        totals.pop("min", None)
        totals.pop("plus_minus", None)
        totals.update({c: to_float(tot_rec.get(s)) for s, c in _EXTRA.items() if tot_rec.get(s) is not None})
        if t.get("score") is not None and totals.get("pts") is None:
            totals["pts"] = to_float(t.get("score"))
        players = []
        for p in (t.get("pl") or {}).values():
            first = p.get("firstName") or p.get("internationalFirstName") or ""
            family = p.get("familyName") or p.get("internationalFamilyName") or ""
            full = f"{first} {family}".strip() or p.get("name")
            pid = p.get("personId") or p.get("playerId") or player_key(p)
            line = {"player_id": str(pid), "name": full,
                    "dorsal": p.get("shirtNumber"), "posicion": p.get("playingPosition") or None,
                    "starter": bool(to_float(p.get("starter")) or 0),
                    "altura_cm": height_to_cm(p.get("height")) if p.get("height") else None}
            stats = {key: v for key, v in p.items() if key.startswith("s") or key.startswith("eff")}
            line.update(map_counting(stats))
            line.update({c: to_float(stats.get(s)) for s, c in _EXTRA.items() if stats.get(s) is not None})
            if p.get("sMinutes") is not None:
                line["min"] = parse_minutes(p.get("sMinutes"))
            players.append(line)
        sides.append({"team_id": team_key(t, aliases) or code or name, "name": name, "code": code,
                      "totals": totals, "players": players})
    return {"game_id": str(match_id), "phase": phase, "date": doc.get("matchDate") or doc.get("date"),
            "final": _is_final(doc), "teams": sides}


def expand_ids(items: list) -> list[int]:
    """[5, [10, 13]] -> [5, 10, 11, 12, 13]."""
    out = []
    for it in items or []:
        if isinstance(it, (list, tuple)) and len(it) == 2:
            out.extend(range(int(it[0]), int(it[1]) + 1))
        else:
            out.append(int(it))
    return out


def compress_ids(ids: list[int], max_gap: int = 3) -> tuple[list, list[int]]:
    """Ids ordenados -> (rangos/ids sueltos, ids de los rangos que NO están en la lista = excluir)."""
    ids = sorted(set(int(i) for i in ids))
    out, excl = [], []
    i = 0
    while i < len(ids):
        j = i
        while j + 1 < len(ids) and ids[j + 1] - ids[j] <= max_gap + 1:
            j += 1
        if j == i:
            out.append(ids[i])
        else:
            out.append([ids[i], ids[j]])
            have = set(ids[i:j + 1])
            excl += [x for x in range(ids[i], ids[j] + 1) if x not in have]
        i = j + 1
    return out, excl


def discover_block(seed: int, probe: Callable[[int], tuple[str, str] | None], max_gap: int = 30,
                   max_span: int = 6000, min_games_team: int = 3, learn_teams: int = 6) -> list[int]:
    """Ids del bloque de partidos de una liga alrededor de `seed`.

    probe(id) -> (equipo local, equipo visitante) normalizados, o None si el id no existe o no es accesible.
    Desde la semilla, en cada sentido: mientras se conocen menos de `learn_teams` equipos se aceptan los ids
    CONTIGUOS (así se aprenden los equipos del bloque); después, los partidos con algún equipo ya conocido.
    Se para tras `max_gap` ids seguidos no aceptados. Al final se descartan los partidos con algún equipo de
    menos de `min_games_team` partidos (ids ajenos colados en los bordes del bloque)."""
    first = probe(seed)
    if not first:
        return []
    teams = {first[0], first[1]}
    accepted: dict[int, tuple[str, str]] = {seed: first}
    for step in (1, -1):
        gap, cur, streak = 0, seed, True
        while gap <= max_gap and abs(cur - seed) < max_span:
            cur += step
            r = probe(cur)
            ok = bool(r) and ((streak and len(teams) < learn_teams) or r[0] in teams or r[1] in teams)
            if ok:
                accepted[cur] = r
                teams.update(r)
                gap = 0
            else:
                gap += 1
                streak = False
    count: dict[str, int] = {}
    for a, b in accepted.values():
        count[a] = count.get(a, 0) + 1
        count[b] = count.get(b, 0) + 1
    return sorted(i for i, (a, b) in accepted.items()
                  if count[a] >= min_games_team and count[b] >= min_games_team)


class FibaLiveStatsAdapter(BaseAdapter):
    name = "fiba_livestats"
    version = "2.0"

    # ---------------------------------------------------------------- descubrimiento genérico (antiguo)
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

    # ---------------------------------------------------------------- red
    def _url(self, mid: Any) -> str:
        return self.cfg.get("data_url", DEFAULT_DATA_URL).format(match_id=mid)

    def _probe_factory(self, http: HttpClient, cache: dict) -> Callable[[int], tuple[str, str] | None]:
        aliases = self.cfg.get("alias_equipos") or {}

        def probe(mid: int):
            if mid in cache:
                return cache[mid]
            try:
                resp = http.get(self._url(mid), ok_status=(403, 404))
            except FetchError:
                cache[mid] = None
                return None
            if resp.status_code != 200:
                cache[mid] = None
                return None
            try:
                doc = resp.json()
                t1, t2 = (doc.get("tm") or {}).get("1") or {}, (doc.get("tm") or {}).get("2") or {}
                cache[mid] = (team_key(t1, aliases), team_key(t2, aliases)) if t1 and t2 else None
                cache[("doc", mid)] = doc
            except ValueError:
                cache[mid] = None
            return cache[mid]
        return probe

    def _season_ids(self, season: str, http: HttpClient | None) -> dict[str, list[int]]:
        """{fase: [ids]} de la config; las fases con `semillas` y sin `partidos` se descubren (y se guardan)."""
        sc = self.season_cfg(season)
        partidos = dict(sc.get("partidos") or {})
        excl = set(expand_ids(sc.get("excluir") or []))
        out = {ph: [i for i in expand_ids(v) if i not in excl] for ph, v in partidos.items()}
        seeds = sc.get("semillas") or {}
        found = {}
        for ph, ss in seeds.items():
            if ph in partidos or not ss or http is None:
                continue
            cache: dict = {}
            probe = self._probe_factory(http, cache)
            ids: set[int] = set()
            for s in ss:
                if s not in ids:
                    ids.update(discover_block(int(s), probe, int(self.cfg.get("max_huecos", 30))))
            self._probe_docs.update({str(k[1]): v for k, v in cache.items() if isinstance(k, tuple)})
            if ids:
                rng, ex = compress_ids(sorted(ids))
                found[ph] = (rng, ex)
                out[ph] = sorted(ids)
        if found:
            excl_all = sorted(set(expand_ids(sc.get("excluir") or [])) | {x for _, ex in found.values() for x in ex})
            upd = {"partidos": {**partidos, **{ph: r for ph, (r, _) in found.items()}}}
            if excl_all:
                upd["excluir"], _ = compress_ids(excl_all, 0)
            self.config_updates = {"temporadas": {season: upd}}
        return out

    def fetch(self, season: str, http: HttpClient, previous_payload: Any | None = None) -> Any:
        self._probe_docs: dict[str, dict] = {}
        pages: dict[str, str] = {}
        by_phase = self._season_ids(season, http)
        legacy = self.discover_ids(season, http, pages)
        if legacy:
            by_phase.setdefault("regular", []).extend(int(x) for x in legacy if str(x).isdigit())
        if not any(by_phase.values()):
            raise NoDataYet(
                f"{self.league} {season}: no hay ids de partido. Configura 'temporadas.{season}.partidos' "
                f"(o 'semillas') en config/sources.json")
        prev_games = (previous_payload or {}).get("games", {}) if isinstance(previous_payload, dict) else {}
        block = int(self.cfg.get("partidos_por_paquete", 400))
        new: dict[str, Any] = {}
        reused = n_new = 0
        phases = {str(i): ph for ph, ids in by_phase.items() for i in ids}
        for mid in sorted(phases, key=int):
            if mid in prev_games and _is_final(prev_games[mid]):
                reused += 1
                continue
            doc = self._probe_docs.get(mid)
            if doc is None:
                try:
                    resp = http.get(self._url(mid), ok_status=(403, 404))
                    doc = resp.json() if resp.status_code == 200 else None
                    if doc is None:
                        self.soft_fail(f"{mid}: HTTP {resp.status_code}")
                except (FetchError, ValueError) as exc:
                    self.soft_fail(f"{mid}: {exc}")
            if not isinstance(doc, dict) or not doc.get("tm"):
                continue
            new[mid] = doc
            n_new += 1
            if len(new) >= block:
                self.save_partial(season, {"fases": phases, "games": new})
                new = {}
        if not n_new and not prev_games:
            raise NoDataYet(f"{self.league} {season}: no se pudo descargar ningún partido")
        return {"incremental": True, "fases": phases, "discovery_pages": pages, "games": new,
                "reused_games": reused, "partidos_nuevos": n_new}

    def parse(self, payload: Any, season: str) -> dict[str, ParsedLeague]:
        phases = payload.get("fases") or {}
        aliases = self.cfg.get("alias_equipos") or {}
        excl = {str(i) for i in expand_ids(self.season_cfg(season).get("excluir") or [])}
        games = []
        for mid, doc in sorted((payload.get("games") or {}).items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
            if not isinstance(doc, dict) or mid in excl:
                continue
            ph = phases.get(mid, "regular") if phases else "regular"
            if ph not in ("regular", "playoffs"):
                continue
            games.append(parse_fiba_game(mid, doc, ph, aliases))
        if not games:
            raise AdapterError(f"{self.league}: el bruto no contiene partidos")
        return aggregate_by_phase(games, [f"{len(games)} boxscores FIBA LiveStats; "
                                          f"{payload.get('reused_games', 0)} reutilizados"])
