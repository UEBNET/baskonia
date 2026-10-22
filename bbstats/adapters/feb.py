"""Competiciones de la Federación Española de Baloncesto (FEB): Primera FEB, Segunda FEB y Tercera FEB.

Nombres históricos (ver config/competition_aliases.json): Primera FEB = LEB Oro, Segunda FEB = LEB Plata,
Tercera FEB = Liga EBA. Las tres se sirven con el mismo sistema (código de competición `g` 1, 2 y 3).

Fuentes públicas y anónimas (sin claves embebidas en JS):
  Resultados   https://baloncestoenvivo.feb.es/resultados/<slug>/<g>/<año>   (ASP.NET WebForms)
               desplegables de GRUPO (liga regular, play-offs, copa…) y de JORNADA; se cambia de grupo y de
               jornada con el «postback» del formulario (los mismos campos ocultos que envía el navegador).
               Cada fila: equipos (Equipo.aspx?i=<id equipo>), resultado (Partido.aspx?p=<id partido>), fecha.
  Partido      https://intrafeb.feb.es/LiveStats.API/api/v1/KeyFacts/<id>  (JSON: HEADER, SCOREBOARD = boxscore
               en directo, TEAMSTATS, PLAYBYPLAY.LINES = jugada a jugada)
               https://intrafeb.feb.es/LiveStats.API/api/v1/BoxScore/<id>  (JSON: BOXSCORE oficial)
               La API pide la cabecera `Authorization: Bearer <token>`; el token es ANÓNIMO: la propia página
               pública lo entrega a cualquier visitante en un campo oculto (`_ctl0_token`, caduca en 24 h, rol de
               sólo lectura). No es un secreto del código JS (igual que el token anónimo de la LNB).
  Equipo       https://baloncestoenvivo.feb.es/Equipo.aspx?i=<id equipo>   (plantilla de esa temporada con fecha
               de nacimiento, nacionalidad, formación, altura y puesto; entrenador principal)
               Del HTML se guarda sólo el fragmento del entrenador y de la tabla de plantilla.

Formatos del jugada a jugada (verificado con datos reales):
  * desde 2024-25: líneas estructuradas (`action` shoot/fthrow/rebound/assist/foul/lose/recovery/blockshot/subst/
    timeout/period, `idPlayer`, `idLicense`, `logParam*`, coordenadas `Position` "x|y").
  * 2020-21 a 2023-24: sólo texto ("(EQUIPO) J. PEREZ: 3Pts Tiro FALLADO, A. LOPEZ:  (TotReb. 2)"); sin ids de
    jugador ni coordenadas: los nombres se emparejan con el boxscore (bbstats/lineups/sources/feb.py).
    En ese formato el SCOREBOARD no trae minutos ni los ids oficiales: el boxscore sale de BoxScore.
  * algunos partidos no tienen ni boxscore ni jugada a jugada (404): cuentan como «sin datos» en la cobertura.

Fases (por nombre de grupo, `fases_grupo` de la config con expresiones regulares): «Liga Regular …» (incluidas las
segundas fases de liga) = `regular`; play-offs, eliminatorias, fases finales y de ascenso, final four = `playoffs`;
copas (Copa Princesa, Copa LEB Plata…) y permanencia/descenso = excluidas (no se descargan; sí se cuentan en la
cobertura). El grupo (id y nombre originales) se conserva como atributo de cada partido.

Ids: equipo = id de inscripción FEB de esa temporada (`HEADER.TEAM[].id`, el de Equipo.aspx; cambia cada
temporada; `clubCode` se guarda aparte), jugador = id de persona FEB (`BOXSCORE…PLAYER[].id`; estable entre
temporadas y competiciones FEB).
Bruto INCREMENTAL (como fiba_web): cada ejecución guarda sólo los partidos nuevos, en paquetes de
`partidos_por_paquete`; claves incrementales: games, equipos, calendario.
"""
from __future__ import annotations

import html as htmllib
import re
from typing import Any

from ..http import FetchError, HttpClient
from ..utils import to_float
from .base import AdapterError, BaseAdapter, NoDataYet, ParsedLeague
from .boxscore import aggregate_by_phase

SITE = "https://baloncestoenvivo.feb.es"
API = "https://intrafeb.feb.es/LiveStats.API/api/v1"

# nombre de grupo -> fase (primera coincidencia, sin distinguir mayúsculas). None = excluida.
DEFAULT_PHASE_RULES = [
    [r"copa", None],
    [r"liga regular", "regular"],
    [r"perman|descen", None],
    [r"2\S* fase|clasif", "regular"],
    [r".", "playoffs"],
]

# campo FEB -> columna canónica
_MAP = {"pts": "pts", "p1m": "ftm", "p1a": "fta", "p2m": "fg2m", "p2a": "fg2a", "p3m": "fg3m", "p3a": "fg3a",
        "fgm": "fgm", "fga": "fga", "ro": "oreb", "rd": "dreb", "rt": "reb", "assist": "ast", "st": "stl",
        "to": "tov", "bs": "blk", "tc": "blka", "mt": "dunks", "pf": "pf", "rf": "pfd", "pllss": "plus_minus",
        "val": "pir"}
_TOKEN = re.compile(r'id="_ctl0_token"\s+value="([^"]+)"')
_HIDDEN = re.compile(r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"')
_SELECT = re.compile(r'<select name="([^"]+)"[^>]*>(.*?)</select>', re.S)
_OPTION = re.compile(r'<option (selected="selected" )?value="([^"]*)">([^<]*)</option>')


# ------------------------------------------------------------------------------------------ HTML
def form_fields(html: str) -> dict:
    """Campos que envía el formulario ASP.NET (ocultos + valor seleccionado de cada desplegable)."""
    f = {n: htmllib.unescape(v) for n, v in _HIDDEN.findall(html or "")}
    for name, body in _SELECT.findall(html or ""):
        opts = _OPTION.findall(body)
        sel = [v for s, v, _ in opts if s] or [v for _, v, _ in opts[:1]]
        f[name] = sel[0] if sel else ""
    return f


def select_options(html: str, key: str) -> list[tuple[str, str, bool]]:
    """Opciones (valor, texto, seleccionada) del desplegable cuyo nombre contiene `key`."""
    for name, body in _SELECT.findall(html or ""):
        if key in name:
            return [(v, htmllib.unescape(t).strip(), bool(s)) for s, v, t in _OPTION.findall(body)]
    return []


def select_name(html: str, key: str) -> str | None:
    for name, _ in _SELECT.findall(html or ""):
        if key in name:
            return name
    return None


def result_rows(html: str) -> list[dict]:
    """Filas de la página de resultados: id de partido, ids de equipos, resultado ("83-90" o vacío) y fecha."""
    out = []
    for tr in re.findall(r"<tr>(.*?)</tr>", html or "", re.S):
        m = re.search(r"Partido\.aspx\?p=(\d+)['\"]>([^<]*)<", tr)
        if not m:
            continue
        teams = re.findall(r"Equipo\.aspx\?i=(\d+)\">([^<]*)<", tr)
        fecha = re.search(r"(\d{2}/\d{2}/\d{4})", tr)
        out.append({"partido": m.group(1), "resultado": m.group(2).strip(),
                    "local": teams[0][0] if teams else None, "visitante": teams[1][0] if len(teams) > 1 else None,
                    "fecha": _date(fecha.group(1)) if fecha else None})
    return out


def _date(txt: str | None) -> str | None:
    """"07/10/2022" | "07-10-2022 - 21:00" -> "2022-10-07"."""
    if not txt:
        return None
    m = re.search(r"(\d{2})[/-](\d{2})[/-](\d{4})", str(txt))
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def _reciente(fecha: str | None, dias: int = 30) -> bool:
    from datetime import date, timedelta
    try:
        return date.fromisoformat(str(fecha)) >= date.today() - timedelta(days=dias)
    except ValueError:
        return False


def played(resultado: str | None) -> bool:
    return bool(re.fullmatch(r"\d+\s*-\s*\d+", (resultado or "").strip()))


def phase_of_group(name: str, rules: list | None = None) -> str | None:
    for pat, ph in rules or DEFAULT_PHASE_RULES:
        if re.search(pat, name or "", re.I):
            return ph
    return "playoffs"


def team_fragment(html: str) -> str:
    """Fragmento de Equipo.aspx con el entrenador y la tabla de plantilla (lo único que se guarda en el bruto)."""
    i = (html or "").find('class="box-entrenador"')
    j = (html or "").find("Nombre</th>")
    start = i if i >= 0 else j
    if start < 0:
        return ""
    end = html.find("</table>", max(start, j))
    head = re.search(r'<h1 class="titulo-modulo">\s*([^<]*)', html)   # nombre de la competición y temporada
    return ((f"<!--titulo: {head.group(1).strip()}-->" if head else "") + html[start:end + 8 if end > 0 else start + 50000])


def parse_team_page(fragment: str) -> dict:
    """Fragmento de Equipo.aspx -> {"entrenador": {id, nombre, fecha_nacimiento}, "jugadores": {pid: {...}}}."""
    out: dict[str, Any] = {"entrenador": None, "jugadores": {}}
    if not fragment:
        return out
    m = re.search(r'class="box-entrenador".*?Foto\.aspx\?c=(\d+).*?class="nombre">([^<]*)<.*?'
                  r'class="fecha nacimiento">([^<]*)<', fragment, re.S)
    if m and m.group(2).strip():
        out["entrenador"] = {"id": m.group(1), "nombre": " ".join(m.group(2).split()),
                             "fecha_nacimiento": _date(m.group(3))}
    for tr in re.findall(r"<tr>(.*?)</tr>", fragment, re.S):
        pm = re.search(r"Jugador\.aspx\?i=\d+&c=(\d+)'>([^<]*)<", tr)
        if not pm:
            continue
        cell = {k: " ".join(htmllib.unescape(v).split()) for k, v in
                re.findall(r'<td class="([a-z ]+)">([^<]*)</td>', tr)}
        nac = cell.get("nacionalidad") or None
        alt = to_float(cell.get("altura"))
        out["jugadores"][pm.group(1)] = {
            "nombre": " ".join(htmllib.unescape(pm.group(2)).split()),
            "posicion": cell.get("puesto") or None, "dorsal": cell.get("dorsal") or None,
            "fecha_nacimiento": _date(cell.get("fecha nacimiento")),
            "nacionalidad": nac.title() if nac and nac != "-" else None,
            "formacion": cell.get("formacion") or None,
            "altura_cm": alt if alt and 150 <= alt <= 235 else None}
    return out


# ------------------------------------------------------------------------------------------ partido
def is_final(doc: dict | None) -> bool:
    h = ((doc or {}).get("keyfacts") or (doc or {}).get("boxscore") or {}).get("HEADER") or {}
    return str(h.get("time") or "").upper() == "FINAL" or str(h.get("statusText") or "").upper() == "FINISHED"


def pbp_lines(doc: dict | None) -> list[dict]:
    pbp = (((doc or {}).get("keyfacts") or {}).get("PLAYBYPLAY") or {})
    return [ln for ln in (pbp.get("LINES") or []) if isinstance(ln, dict)]


def pbp_format(doc: dict | None) -> str:
    """"estructurado" (2024-25+), "texto" (2020-24), "" (sin jugada a jugada)."""
    lines = pbp_lines(doc)
    if not lines:
        return ""
    return "estructurado" if any(ln.get("action") for ln in lines) else "texto"


def box_teams(doc: dict) -> list[dict]:
    """Equipos con jugadores del boxscore: BoxScore oficial si existe; si no, SCOREBOARD de KeyFacts (sin
    minutos en el formato antiguo)."""
    bs = ((doc.get("boxscore") or {}).get("BOXSCORE") or {}).get("TEAM")
    if bs:
        return bs
    kf = doc.get("keyfacts") or {}
    teams = ((kf.get("SCOREBOARD") or {}).get("TEAM")) or []
    stats = {str(t.get("id")): t for t in ((kf.get("TEAMSTATS") or {}).get("TEAM") or [])}
    return [{**t, "TOTAL": stats.get(str(t.get("id")))} for t in teams]


def header(doc: dict) -> dict:
    return ((doc.get("keyfacts") or doc.get("boxscore") or {}).get("HEADER")) or {}


def _stats(rec: dict | None) -> dict:
    rec = rec or {}
    out = {c: to_float(rec.get(k)) for k, c in _MAP.items() if rec.get(k) not in (None, "")}
    return {k: v for k, v in out.items() if v is not None}


def parse_game(gid: str, doc: dict, phase: str, rosters: dict | None = None, meta: dict | None = None) -> dict:
    """Documento de partido del bruto -> formato estándar de boxscore (ver boxscore.py)."""
    h = header(doc)
    rosters = rosters or {}
    by_id = {str(t.get("id")): t for t in box_teams(doc)}
    sides = []
    for ht in h.get("TEAM") or []:
        tid = str(ht.get("id"))
        t = by_id.get(tid) or {}
        ros = (rosters.get(tid) or {}).get("jugadores") or {}
        players = []
        for p in t.get("PLAYER") or []:
            pid = str(p.get("id"))
            bio = ros.get(pid) or {}
            line = {"player_id": pid, "name": bio.get("nombre") or " ".join(str(p.get("name") or pid).split()),
                    "dorsal": p.get("no"), "posicion": bio.get("posicion"), "starter": str(p.get("inn")) == "1",
                    "fecha_nacimiento": bio.get("fecha_nacimiento"), "nacionalidad": bio.get("nacionalidad"),
                    "altura_cm": bio.get("altura_cm")}
            line.update(_stats(p))
            sec = to_float(p.get("min"))
            line["min"] = sec / 60 if sec is not None else None
            if line["min"] == 0 and any(line.get(k) for k in ("pts", "fga", "fta", "reb", "pf")):
                line["min"] = None      # minutos no registrados (formato antiguo del directo)
            players.append(line)
        totals = _stats(t.get("TOTAL"))
        totals.pop("plus_minus", None)
        totals.pop("pir", None)
        if totals.get("pts") is None and ht.get("pts") is not None:
            totals["pts"] = to_float(ht.get("pts"))
        sides.append({"team_id": tid, "name": " ".join(str(ht.get("name") or tid).split()),
                      "code": ht.get("clubCode"), "totals": totals, "players": players})
    m = meta or {}
    q = ((h.get("QUARTERS") or {}).get("QUARTER")) or []
    return {"game_id": str(gid), "phase": phase, "final": is_final(doc), "teams": sides,
            "date": m.get("fecha") or _date(h.get("starttime")), "grupo": m.get("grupo"),
            "n_periodos": len(q) if isinstance(q, list) and q else None}


# ------------------------------------------------------------------------------------------ adaptador
class FebAdapter(BaseAdapter):
    """Config de la liga: `competicion_feb` (1, 2, 3), `slug` (primerafeb, segundafeb, tercerafeb),
    `fases_grupo` (reglas nombre de grupo -> fase), `partidos_por_paquete`."""
    name = "feb"
    version = "1.0"

    def __init__(self, league: str, cfg: dict) -> None:
        super().__init__(league, cfg)
        self._token: str | None = None

    # -------------------------------------------------------------- red
    def _page(self, http: HttpClient, url: str, data: dict | None = None) -> str:
        resp = http.request("POST" if data else "GET", url, data=data)
        resp.encoding = "utf-8"
        txt = resp.text
        m = _TOKEN.search(txt)
        if m:
            self._token = m.group(1)
        return txt

    def _api(self, http: HttpClient, ep: str, gid: str) -> dict | None:
        """JSON de la API (None si el partido no tiene ese dato: 404). Renueva el token anónimo si caduca."""
        for attempt in range(2):
            if not self._token:
                self._page(http, f"{SITE}/partido/{gid}")
            resp = http.get(f"{API}/{ep}/{gid}", headers={"Authorization": f"Bearer {self._token}",
                                                         "Accept": "application/json"}, ok_status=(401, 404))
            if resp.status_code == 401 and attempt == 0:
                self._token = None
                continue
            if resp.status_code != 200:
                return None
            try:
                return resp.json()
            except ValueError:
                return None
        return None

    def discover(self, http: HttpClient, season: str) -> dict:
        """Calendario de la temporada: {"grupos": {id: {nombre, fase}}, "partidos": {id: {grupo, jornada, fecha,
        resultado, local, visitante}}} recorriendo cada grupo y cada jornada de la página de resultados."""
        y = int(season[:4])
        url = f"{SITE}/resultados/{self.cfg['slug']}/{self.cfg['competicion_feb']}/{y}"
        base = self._page(http, url)
        seasons = [v for v, _, _ in select_options(base, "temporadas")]
        if seasons and str(y) not in seasons:
            raise NoDataYet(f"{self.league} {season}: la temporada no existe en la web de la FEB")
        sel = [v for v, _, s in select_options(base, "temporadas") if s]
        if sel and sel[0] != str(y):
            raise NoDataYet(f"{self.league} {season}: la web devuelve otra temporada ({sel[0]})")
        rules = self.cfg.get("fases_grupo") or DEFAULT_PHASE_RULES
        grupos, partidos = {}, {}
        gname = select_name(base, "grupos")
        for gid, gtxt, gsel in select_options(base, "grupos"):
            ph = phase_of_group(gtxt, rules)
            grupos[gid] = {"nombre": gtxt, "fase": ph}
            page = base if gsel else self._page(http, url, {**form_fields(base), gname: gid,
                                                            "__EVENTTARGET": gname.replace(":", "$"),
                                                            "__EVENTARGUMENT": ""})
            jname = select_name(page, "jornadas")
            jornadas = select_options(page, "jornadas")
            grupos[gid]["jornadas"] = len(jornadas)
            for jid, jtxt, jsel in jornadas or [("", "", True)]:
                jp = page if jsel else self._page(http, url, {**form_fields(page), jname: jid,
                                                              "__EVENTTARGET": jname.replace(":", "$"),
                                                              "__EVENTARGUMENT": ""})
                for r in result_rows(jp):
                    partidos[r["partido"]] = {**r, "grupo": gid, "jornada": jtxt}
        if not partidos:
            raise NoDataYet(f"{self.league} {season}: sin partidos en el calendario")
        return {"grupos": grupos, "partidos": partidos}

    def fetch(self, season: str, http: HttpClient, previous_payload: Any | None = None) -> Any:
        prev = previous_payload if isinstance(previous_payload, dict) else {}
        prev_games = prev.get("games") or {}
        prev_teams = prev.get("equipos") or {}
        cal = self.discover(http, season)
        block = int(self.cfg.get("partidos_por_paquete", 400))
        limit = int(self.cfg.get("max_partidos_por_ejecucion") or 0)
        new: dict[str, dict] = {}
        new_teams: dict[str, str] = {}
        reused = n_new = sin_datos = 0
        todo = sorted((pid for pid, r in cal["partidos"].items()
                       if cal["grupos"].get(r["grupo"], {}).get("fase") and played(r.get("resultado"))), key=int)
        for pid in todo:
            old = prev_games.get(pid)
            if old and (is_final(old) or (old.get("sin_datos") and not _reciente(cal["partidos"][pid].get("fecha")))):
                reused += 1      # un partido sin datos se vuelve a pedir sólo si se jugó hace menos de 30 días
                continue
            if limit and n_new >= limit:
                break
            try:
                kf = self._api(http, "KeyFacts", pid)
                doc: dict[str, Any] = {"keyfacts": kf}
                if kf is None or pbp_format(doc) != "estructurado":
                    doc["boxscore"] = self._api(http, "BoxScore", pid)   # formato antiguo: boxscore oficial aparte
            except FetchError as exc:      # error de red persistente: se reintenta en la próxima ejecución
                self.soft_fail(f"{pid}: {exc}")
                continue
            if kf is None and doc.get("boxscore") is None:
                doc = {"sin_datos": True}       # la fuente no tiene datos del partido (se anota en la cobertura)
                sin_datos += 1
            else:
                for t in header(doc).get("TEAM") or []:
                    tid = str(t.get("id"))
                    if tid not in prev_teams and tid not in new_teams:
                        try:
                            new_teams[tid] = team_fragment(self._page(http, f"{SITE}/Equipo.aspx?i={tid}"))
                        except FetchError as exc:
                            self.soft_fail(f"equipo {tid}: {exc}")
            new[pid] = doc
            n_new += 1
            if len(new) >= block:
                self.save_partial(season, {"claves_incrementales": ["games", "equipos"], "games": new,
                                           "equipos": new_teams, "calendario": cal})
                prev_teams = {**prev_teams, **new_teams}
                new, new_teams = {}, {}
        if not new and not prev_games and not n_new:
            raise NoDataYet(f"{self.league} {season}: aún no hay partidos jugados")
        return {"incremental": True, "claves_incrementales": ["games", "equipos"], "calendario": cal,
                "games": new, "equipos": new_teams, "reused_games": reused, "partidos_nuevos": n_new,
                "partidos_sin_datos": sin_datos}

    # -------------------------------------------------------------- parse
    def parse(self, payload: Any, season: str) -> dict[str, ParsedLeague]:
        cal = payload.get("calendario") or {}
        grupos, meta = cal.get("grupos") or {}, cal.get("partidos") or {}
        rosters = {tid: parse_team_page(fr) for tid, fr in (payload.get("equipos") or {}).items()}
        games = []
        for gid, doc in sorted((payload.get("games") or {}).items(), key=lambda kv: int(kv[0])):
            if not isinstance(doc, dict) or doc.get("sin_datos") or not header(doc):
                continue
            m = meta.get(gid) or {}
            ph = (grupos.get(m.get("grupo")) or {}).get("fase", "regular") if m else "regular"
            if ph not in ("regular", "playoffs"):
                continue
            games.append(parse_game(gid, doc, ph, rosters, m))
        if not games:
            raise AdapterError(f"{self.league}: el bruto no contiene partidos")
        return aggregate_by_phase(games, [f"{len(games)} partidos FEB (baloncestoenvivo/intrafeb); "
                                          f"{payload.get('reused_games', 0)} reutilizados"])


def game_rows(payload: dict) -> list[dict]:
    """Una fila por partido del calendario (también los excluidos y los sin datos) para la cobertura:
    game_id, grupo_id, grupo, fase, jornada, fecha, jugado, descargado, con_box, formato_pbp."""
    cal = (payload or {}).get("calendario") or {}
    grupos = cal.get("grupos") or {}
    games = (payload or {}).get("games") or {}
    out = []
    for pid, r in sorted((cal.get("partidos") or {}).items(), key=lambda kv: int(kv[0])):
        g = grupos.get(r.get("grupo")) or {}
        doc = games.get(pid)
        out.append({"game_id": pid, "grupo_id": r.get("grupo"), "grupo": g.get("nombre"),
                    "fase": g.get("fase") or "excluida", "jornada": r.get("jornada"), "fecha": r.get("fecha"),
                    "jugado": played(r.get("resultado")), "descargado": doc is not None,
                    "con_box": bool(doc and not doc.get("sin_datos") and box_teams(doc)),
                    "formato_pbp": pbp_format(doc) if doc and not doc.get("sin_datos") else ""})
    return out
