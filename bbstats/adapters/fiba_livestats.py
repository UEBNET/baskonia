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
from typing import Any

from ..http import FetchError, HttpClient
from ..normalize import map_counting
from ..utils import height_to_cm, parse_minutes, to_float
from .base import AdapterError, BaseAdapter, NoDataYet, ParsedLeague
from .boxscore import aggregate_by_phase

DEFAULT_DATA_URL = "https://fibalivestats.dcd.shared.geniussports.com/data/{match_id}/data.json"
DEFAULT_ID_REGEX = r"fibalivestats\.dcd\.shared\.geniussports\.com/(?:u/[A-Za-z0-9]+/|data/)(\d{5,8})"
_NAME = re.compile(r'"name":\s*"((?:[^"\\]|\\.)*)"')
_EXTRA = {"sPointsInThePaint": "pts_paint", "sPointsSecondChance": "pts_2ndchance",
          "sPointsFastBreak": "pts_fastbreak", "sPointsFromTurnovers": "pts_off_tov"}


_GREEK = {"α": "a", "β": "v", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "i", "θ": "th", "ι": "i", "κ": "k",
          "λ": "l", "μ": "m", "ν": "n", "ξ": "x", "ο": "o", "π": "p", "ρ": "r", "σ": "s", "ς": "s", "τ": "t",
          "υ": "y", "φ": "f", "χ": "ch", "ψ": "ps", "ω": "o"}
_TR = {"ı": "i", "ş": "s", "ğ": "g", "ç": "c", "ö": "o", "ü": "u", "İ": "i"}


def norm(s: Any) -> str:
    """Texto comparable: minúsculas sin acentos, griego transliterado, sólo letras/cifras y espacios."""
    s = "".join(_TR.get(c, c) for c in str(s or ""))
    s = "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))
    s = "".join(_GREEK.get(c, c) for c in s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def player_key(p: dict) -> str:
    """Id de jugador: apellido|nombre internacionales normalizados (el data.json no trae personId)."""
    fam = p.get("internationalFamilyName") or p.get("familyName") or ""
    first = p.get("internationalFirstName") or p.get("firstName") or ""
    k = f"{norm(fam)}|{norm(first)}"
    return k if k != "|" else norm(p.get("name") or p.get("scoreboardName"))


def _team_name(t: dict) -> str:
    return t.get("name") or t.get("nameInternational") or t.get("shortName") or t.get("code") or ""


def season_teams(docs: dict, aliases: dict | None = None, min_common: int = 4) -> dict[tuple[str, str], tuple[str, str]]:
    """Equipo de cada lado de cada partido de una temporada: {(id, "1"|"2"): (team_id, nombre)}.

    En LiveStats cada club introduce el nombre del rival a su manera ("Δόξα Λευκάδας" / "DOXA LEFKADAS
    ELABET") y los patrocinadores cambian a mitad de temporada, así que las variantes se unen por PLANTILLA:
    dos nombres son el mismo equipo si comparten al menos `min_common` jugadores (o el mismo nombre
    normalizado, o un alias de la config). team_id = nombre normalizado más usado como local; nombre = el
    nombre local más usado."""
    aliases = {norm(k): norm(v) for k, v in (aliases or {}).items()}
    sides: list[tuple[tuple[str, str], str, str, set]] = []
    for mid, doc in (docs or {}).items():
        tm = (doc or {}).get("tm") or {}
        for k in ("1", "2"):
            t = tm.get(k) or {}
            raw = _team_name(t)
            n = norm(raw)
            n = aliases.get(n, n)
            roster = {player_key(p) for p in (t.get("pl") or {}).values()
                      if (parse_minutes(p.get("sMinutes")) or 0) > 0}
            sides.append(((str(mid), k), n, raw, roster))
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    rosters: dict[str, set] = {}
    for _, n, _, r in sides:
        find(n)
        rosters.setdefault(n, set()).update(r)
    names = sorted(rosters)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if len(rosters[a] & rosters[b]) >= min_common and find(a) != find(b):
                parent[find(b)] = find(a)
    home: dict[str, dict[str, int]] = {}
    raw_home: dict[str, dict[str, int]] = {}
    for (mid, k), n, raw, _ in sides:
        c = find(n)
        w = 2 if k == "1" else 1      # el nombre que pone el propio club (local) vale más
        home.setdefault(c, {})[n] = home.setdefault(c, {}).get(n, 0) + w
        raw_home.setdefault(c, {})[raw] = raw_home.setdefault(c, {}).get(raw, 0) + w
    canon = {c: max(v, key=lambda x: (v[x], x)) for c, v in home.items()}
    disp = {c: max(v, key=lambda x: (v[x], x)) for c, v in raw_home.items()}
    return {key: (canon[find(n)].replace(" ", "-"), disp[find(n)].strip()) for key, n, _, _ in sides}


def standings(games: dict[str, tuple[str, str, float, float]]) -> list[str]:
    """Clasificación (victorias, diferencia) de partidos {id: (equipo1, equipo2, pts1, pts2)}."""
    w: dict[str, list] = {}
    for a, b, p1, p2 in games.values():
        for t in (a, b):
            w.setdefault(t, [0, 0.0])
        if p1 is None or p2 is None:
            continue
        w[a][0] += p1 > p2
        w[b][0] += p2 > p1
        w[a][1] += p1 - p2
        w[b][1] += p2 - p1
    return sorted(w, key=lambda t: (-w[t][0], -w[t][1]))


def phase_map(payload: dict, docs: dict, teams: dict, cfg: dict, season: str) -> dict[str, str | None]:
    """Fase de cada partido: la de la config (`partidos` por fase); los de playoffs se quedan en "playoffs"
    sólo si sus dos equipos acabaron la temporada regular entre los `plazas_playoffs` primeros (si no son
    play-outs o partidos de clasificación: "excluida"). Ids de `excluir` -> None."""
    sc = ((cfg.get("temporadas") or {}).get(season) or {})
    excl = {str(i) for i in expand_ids(sc.get("excluir") or [])}
    fases = dict((payload or {}).get("fases") or {})
    for ph, items in (sc.get("partidos") or {}).items():
        for i in expand_ids(items):
            fases.setdefault(str(i), ph)
    out: dict[str, str | None] = {}
    res = {}
    for mid, doc in (docs or {}).items():
        if mid in excl:
            out[mid] = None
            continue
        out[mid] = fases.get(mid, "regular")
        tm = (doc or {}).get("tm") or {}
        t1, t2 = teams.get((mid, "1")), teams.get((mid, "2"))
        if t1 and t2:
            res[mid] = (t1[0], t2[0], to_float((tm.get("1") or {}).get("score")),
                        to_float((tm.get("2") or {}).get("score")))
    n = int(cfg.get("plazas_playoffs") or 0)
    if n:
        top = set(standings({m: r for m, r in res.items() if out.get(m) == "regular"})[:n])
        for mid, r in res.items():
            if out.get(mid) == "playoffs" and not (r[0] in top and r[1] in top):
                out[mid] = "excluida"
    return out


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


def parse_fiba_game(match_id: str, doc: dict, phase: str = "regular",
                    teams: tuple | None = None) -> dict:
    """data.json de FIBA LiveStats -> formato estándar de partido (ver boxscore.py).
    `teams` = ((team_id, nombre) local, (team_id, nombre) visitante) de season_teams (si no, el nombre)."""
    sides = []
    for idx, k in enumerate(("1", "2")):
        t = (doc.get("tm") or {}).get(k) or {}
        name = _team_name(t)
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
            pid = p.get("personId") or player_key(p)
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
        tid, tname = (teams[idx] if teams and teams[idx] else (norm(name).replace(" ", "-") or code, name))
        sides.append({"team_id": tid, "name": tname, "code": code, "totals": totals, "players": players})
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
    """Ids -> (rangos [desde, hasta] e ids sueltos, ids de dentro de los rangos que NO están = excluir)."""
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


class FibaLiveStatsAdapter(BaseAdapter):
    """Partidos de una liga en FIBA LiveStats.

    Config por temporada (`temporadas.<t>`):
      partidos   {"regular": [...], "playoffs": [...]}: ids o rangos [desde, hasta] (lo que se descarga)
      excluir    ids de esos rangos que no son de la liga (o no existen)
      equipos    nombres (locales) de los equipos de la liga, para el descubrimiento
      ventanas   {"regular": [[desde, hasta]], "playoffs": [...]}: rangos de ids donde BUSCAR partidos de la
                 liga cuando aún no hay `partidos` de esa fase (descubrimiento; el resultado se guarda en
                 `partidos` y `excluir`)
      en_curso   true: en cada ejecución se busca además hacia delante desde el último id conocido
                 (`avance_busqueda` ids, por defecto 8000) para recoger las jornadas creadas después;
                 los ids >= `playoffs_desde` son de playoffs
    Fase de playoffs: sólo partidos entre equipos del top `plazas_playoffs` de la temporada regular (los
    play-outs y partidos de clasificación de fin de temporada quedan fuera).
    """
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

    def _head(self, http: HttpClient, mid: int) -> str | None:
        """Nombre (normalizado) del equipo local leyendo sólo los primeros bytes del data.json."""
        try:
            resp = http.get(self._url(mid), headers={"Range": "bytes=0-450"}, ok_status=(403, 404, 416))
        except FetchError:
            return None
        if resp.status_code not in (200, 206):
            return None
        m = _NAME.search(resp.text)
        return norm(json.loads(f'"{m.group(1)}"')) if m else None

    def _doc(self, http: HttpClient, mid: Any) -> tuple[dict | None, str | None]:
        try:
            resp = http.get(self._url(mid), ok_status=(403, 404))
        except FetchError as exc:
            self.soft_fail(f"{mid}: {exc}")
            return None, None
        if resp.status_code != 200:
            return None, None
        try:
            doc = resp.json()
        except ValueError:
            return None, None
        return (doc if isinstance(doc, dict) and doc.get("tm") else None), resp.headers.get("Last-Modified")

    def _scan(self, http: HttpClient, ids, known: set, docs: dict, dates: dict, stop_after: int | None = None) -> list[int]:
        """Partidos de la liga entre `ids`: local con nombre conocido y visitante conocido (o con al menos 4
        jugadores de un equipo conocido). Aprende las variantes de nombre. `stop_after` = parar tras ese número
        de ids seguidos sin partido de la liga."""
        found, miss = [], 0
        rosters: dict[str, set] = {}
        for d in docs.values():
            for t in ((d.get("tm") or {}).get(k) or {} for k in ("1", "2")):
                rosters.setdefault(norm(_team_name(t)), set()).update(player_key(p) for p in (t.get("pl") or {}).values())
        for mid in ids:
            h = self._head(http, mid)
            if h and h in known:
                doc, lm = self._doc(http, mid)
                if doc:
                    t2 = (doc.get("tm") or {}).get("2") or {}
                    n2 = norm(_team_name(t2))
                    r2 = {player_key(p) for p in (t2.get("pl") or {}).values()}
                    if n2 in known or any(len(r2 & r) >= 4 for r in rosters.values()):
                        known.add(n2)
                        rosters.setdefault(n2, set()).update(r2)
                        docs[str(mid)], dates[str(mid)] = doc, lm
                        found.append(mid)
                        miss = 0
                        continue
            miss += 1
            if stop_after and miss > stop_after:
                break
        return found

    def _season_ids(self, season: str, http: HttpClient | None, prev_games: dict) -> dict[str, list[int]]:
        """{fase: [ids]} de la config; descubre las fases sin `partidos` en sus `ventanas` y, si la temporada
        está `en_curso`, busca hacia delante. Lo descubierto se guarda en config (config_updates)."""
        sc = self.season_cfg(season)
        partidos = {ph: list(v) for ph, v in (sc.get("partidos") or {}).items()}
        excl = set(expand_ids(sc.get("excluir") or []))
        out = {ph: [i for i in expand_ids(v) if i not in excl] for ph, v in partidos.items()}
        if http is None or not (sc.get("equipos") or prev_games):
            return out
        known = {norm(n) for n in sc.get("equipos") or []}
        for d in prev_games.values():
            known.update(norm(_team_name((d.get("tm") or {}).get(k) or {})) for k in ("1", "2"))
        new: dict[str, list[int]] = {}
        for ph, wins in (sc.get("ventanas") or {}).items():
            if ph in partidos:
                continue
            ids = [i for a, b in wins for i in range(int(a), int(b) + 1)]
            new[ph] = self._scan(http, ids, known, self._probe_docs, self._probe_dates)
        if sc.get("en_curso"):
            last = max([i for v in out.values() for i in v] + [i for v in new.values() for i in v] + [0])
            if last:
                ids = range(last + 1, last + 1 + int(self.cfg.get("avance_busqueda", 8000)))
                po = int(sc.get("playoffs_desde") or 0)
                for mid in self._scan(http, ids, known, self._probe_docs, self._probe_dates,
                                      stop_after=int(self.cfg.get("avance_busqueda", 8000))):
                    new.setdefault("playoffs" if po and mid >= po else "regular", []).append(mid)
        if any(new.values()):
            upd_p, all_excl = {}, set(expand_ids(sc.get("excluir") or []))
            for ph, ids in new.items():
                if not ids:
                    continue
                allids = sorted(set(ids) | set(out.get(ph, [])))
                rng, ex = compress_ids(allids)
                upd_p[ph] = rng
                all_excl |= set(ex)
                out[ph] = allids
            upd = {"partidos": {**partidos, **upd_p}}
            if all_excl:
                upd["excluir"] = compress_ids(sorted(all_excl), 0)[0]
            self.config_updates = {"temporadas": {season: upd}}
        return out

    def fetch(self, season: str, http: HttpClient, previous_payload: Any | None = None) -> Any:
        self._probe_docs: dict[str, dict] = {}
        self._probe_dates: dict[str, str | None] = {}
        prev_games = (previous_payload or {}).get("games", {}) if isinstance(previous_payload, dict) else {}
        pages: dict[str, str] = {}
        by_phase = self._season_ids(season, http, prev_games)
        legacy = self.discover_ids(season, http, pages)
        if legacy:
            by_phase.setdefault("regular", []).extend(int(x) for x in legacy if str(x).isdigit())
        if not any(by_phase.values()):
            raise AdapterError(
                f"{self.league} {season}: no hay ids de partido. Configura 'temporadas.{season}.partidos' "
                f"(o 'equipos' + 'ventanas') en config/sources.json")
        block = int(self.cfg.get("partidos_por_paquete", 400))
        new: dict[str, Any] = {}
        dates: dict[str, str | None] = {}
        reused = n_new = 0
        phases = {str(i): ph for ph, ids in by_phase.items() for i in ids}
        for mid in sorted(phases, key=int):
            if mid in prev_games and _is_final(prev_games[mid]):
                reused += 1
                continue
            doc, lm = (self._probe_docs[mid], self._probe_dates.get(mid)) if mid in self._probe_docs \
                else self._doc(http, mid)
            if not doc:
                continue
            if mid in prev_games and json.dumps(prev_games[mid], sort_keys=True) == json.dumps(doc, sort_keys=True):
                reused += 1
                continue
            new[mid], dates[mid] = doc, lm
            n_new += 1
            if len(new) >= block:
                self.save_partial(season, {"claves_incrementales": ["games", "fechas"], "fases": phases,
                                           "fechas": dates, "games": new})
                new, dates = {}, {}
        if not n_new and not prev_games:
            raise NoDataYet(f"{self.league} {season}: aún no hay partidos disponibles")
        return {"incremental": True, "claves_incrementales": ["games", "fechas"], "fases": phases,
                "fechas": dates, "discovery_pages": pages, "games": new, "reused_games": reused,
                "partidos_nuevos": n_new}

    def parse(self, payload: Any, season: str) -> dict[str, ParsedLeague]:
        docs = {k: v for k, v in (payload.get("games") or {}).items() if isinstance(v, dict) and v.get("tm")}
        teams = season_teams(docs, self.cfg.get("alias_equipos"))
        phases = phase_map(payload, docs, teams, self.cfg, season)
        games = []
        for mid in sorted(docs, key=lambda k: int(k) if k.isdigit() else 0):
            ph = phases.get(mid)
            if ph not in ("regular", "playoffs"):
                continue
            games.append(parse_fiba_game(mid, docs[mid], ph, (teams.get((mid, "1")), teams.get((mid, "2")))))
        if not games:
            raise AdapterError(f"{self.league}: el bruto no contiene partidos")
        n_excl = sum(1 for v in phases.values() if v == "excluida")
        return aggregate_by_phase(games, [f"{len(games)} boxscores FIBA LiveStats; {n_excl} de play-out/"
                                          f"clasificación excluidos; {payload.get('reused_games', 0)} reutilizados"])
