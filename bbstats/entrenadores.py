"""Entrenadores principales por partido, tramos de entrenador (club-temporada-entrenador) y tabla global.

Para cada liga y temporada:
  1. Universo de partidos = los partidos del bruto jugada a jugada (`pbp_<liga>_<t>_*.json.gz`, los mismos
     `game_id` que data/processed/<t>/quintetos/<liga>/tramos.csv.gz) más los del bruto principal cuando éste
     trae el boxscore de cada partido (ACB, LBA, BBL).
  2. Un **lector** por liga saca de cada partido, sin red: fecha, fase, los dos equipos (mismos ids que las
     tablas de quintetos y que `team_id` de ligas/<liga>.csv), puntos y, si el documento lo trae, el entrenador.
       EuroLeague/EuroCup  live.euroleague.net Boxscore  Stats[i].Coach ("APELLIDO, NOMBRE")
       ACB                 api2.acb.com Result/boxscores teamBoxscores[i].headCoach
       LBA                 legabasket matches-scores-by-id coaches_extra.home/visitor (id, fechas de contrato)
       BBL                 easycredit-bbl.de: coachComments[].seasonCoach (quién habla en la rueda de prensa
                           de ESE partido) + homeTeam/guestTeam.headCoachName (entrenador de la temporada)
  3. Si la liga no trae el entrenador en el partido, un **complemento de temporada** lo descarga de una fuente
     pública (paquete bruto `entrenadores_<liga>_<t>_<fecha>.json.gz`, nunca se sobrescribe) y lo asigna:
       NBA       basketball-reference.com/teams/<EQ>/<año>.html  "Coach: A (a-b), B (c-d)" en orden
                 cronológico → los partidos de temporada regular del equipo, por fecha, en ese orden;
                 playoffs = último entrenador de la temporada regular. Se comprueba el V-D de cada bloque.
       G League  stats.gleague.nba.com commonteamroster (Coaches, COACH_TYPE = "Head Coach") → toda la temporada
       LNB       api-prod.lnb.fr altrstats/getCoachingStaff {teamExternalId, year} (HEAD_COACH con from/to)
  4. Ids: `entrenador_id` = slug del nombre normalizado (sin acentos, "APELLIDO, NOMBRE" → "nombre-apellido"),
     traducido con config/entrenadores_alias.json (variantes de escritura) → el mismo id en todas las ligas y
     temporadas. El id propio de la fuente queda en `entrenador_id_fuente`.
  5. Huecos: un partido sin entrenador entre dos partidos del mismo entrenador recibe ese entrenador
     (`imputado = 1`, metodo = "tramo"); al principio o al final de la temporada, el más cercano
     (metodo = "tramo_borde"). Entre dos entrenadores distintos queda vacío. Nunca se inventan nombres.
  6. Salida: data/processed/<t>/entrenadores/<liga>_partidos.csv y <liga>_tramos.csv,
     data/processed/entrenadores.csv (tabla global) y data/processed/entrenadores_cobertura.csv.

Registro de extractores: `EXTRACTORES` (por código de liga o por nombre de la fuente jugada a jugada
`config.ligas.<liga>.pbp`). Una liga nueva se añade con `registrar(clave, Extractor(lector=...))`; para FIBA
LiveStats (data.json: tm["1"]["coach"], tm["1"]["coachDetails"]) está `extractor_fiba_livestats(doc)` y el
lector genérico `lector_fiba_livestats`.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from . import __version__
from .config import PROJECT_ROOT, active_leagues, load_config, resolve_path, season_range
from .http import FetchError, HttpClient
from .raw_store import RawStore
from .utils import utc_now, utc_stamp

log = logging.getLogger(__name__)

ALIAS_PATH = PROJECT_ROOT / "config" / "entrenadores_alias.json"
KIND = "entrenadores"
PARTIDO_COLS = ["liga", "temporada", "game_id", "fecha", "fase", "equipo_id", "equipo", "rival_id", "local",
                "puntos", "puntos_rival", "resultado", "entrenador", "entrenador_id", "entrenador_id_fuente",
                "fuente", "metodo", "imputado"]
TRAMO_COLS = ["liga", "temporada", "equipo_id", "equipo", "orden", "entrenador_id", "entrenador",
              "n_partidos", "n_regular", "n_playoffs", "n_otras", "n_imputados", "primer_partido",
              "ultimo_partido", "victorias", "derrotas", "victorias_regular", "derrotas_regular",
              "victorias_playoffs", "derrotas_playoffs", "n_tramos_consecutivos", "interino", "entrenadores_equipo",
              "validacion_vd", "fuente", "partidos_ids"]


# =============================================================================================== nombres
_TRANS = str.maketrans({"đ": "dj", "Đ": "Dj", "ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "ß": "ss", "æ": "ae",
                        "Æ": "Ae", "ı": "i", "þ": "th", "ð": "d"})


def _ascii(s: str) -> str:
    s = (s or "").translate(_TRANS)
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def _titulo(s: str) -> str:
    """'O'SHEA' -> "O'Shea", 'DE RAFFAELE' -> 'De Raffaele' (sólo para nombres en mayúsculas/minúsculas)."""
    def cap(m):
        w = m.group(0)
        if len(w) <= 3 and not re.search(r"[aeiouyáéíóúàèìòùäëïöüAEIOUY]", w, re.I):
            return w.upper()                    # iniciales: 'TJ', 'JJ'
        return w.capitalize()
    return re.sub(r"[^\W\d_]+", cap, s.lower())


def nombre_visible(raw: Any) -> str | None:
    """Nombre de la fuente → 'Nombre Apellido'. 'IVANOVIC, DUSKO' -> 'Dusko Ivanovic'; vacíos -> None."""
    if raw is None:
        return None
    s = " ".join(str(raw).replace(" ", " ").split()).strip(" ,.-")
    if not s or s.lower() in {"none", "null", "nan", "n/a", "-"}:
        return None
    if "," in s:
        last, first = (x.strip() for x in s.split(",", 1))
        s = f"{first} {last}".strip()
    letters = [c for c in s if c.isalpha()]
    if letters and (all(c.isupper() for c in letters) or all(c.islower() for c in letters)):
        s = _titulo(s)
    return s or None


def slug(raw: Any) -> str | None:
    """Clave normalizada: sin acentos, minúsculas, guiones. 'Dusko Ivanović' == 'IVANOVIC, DUSKO'."""
    n = nombre_visible(raw)
    if not n:
        return None
    s = re.sub(r"[^a-z0-9]+", "-", _ascii(n).lower()).strip("-")
    return s or None


@dataclass
class Alias:
    """config/entrenadores_alias.json: {"alias": {slug_variante: slug_canónico}, "nombres": {slug: nombre}}."""
    alias: dict = field(default_factory=dict)
    nombres: dict = field(default_factory=dict)
    distintos: set = field(default_factory=set)   # pares {slug, slug} que NO son la misma persona

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Alias":
        p = Path(path or ALIAS_PATH)
        if not p.exists():
            return cls()
        doc = json.loads(p.read_text(encoding="utf-8"))
        distintos = set()
        for txt in doc.get("_no_son_la_misma_persona") or []:
            par = [x.strip() for x in re.split(r"[/(]", txt)[:2]]
            if len(par) == 2 and all(par):
                distintos.add(frozenset(par))
        return cls({k: v for k, v in (doc.get("alias") or {}).items() if not k.startswith("_")},
                   {k: v for k, v in (doc.get("nombres") or {}).items() if not k.startswith("_")}, distintos)

    def id_de(self, raw: Any) -> str | None:
        s = slug(raw)
        seen = set()
        while s in self.alias and s not in seen:   # cadenas de alias
            seen.add(s)
            s = self.alias[s]
        return s


def _mejor_nombre(variantes: list[str]) -> str:
    """Entre las grafías de una persona: mayúsculas/minúsculas mezcladas, con acentos, la más frecuente, la más corta."""
    def score(v: str) -> tuple:
        mixed = any(c.islower() for c in v) and any(c.isupper() for c in v)
        return (mixed, any(ord(c) > 127 for c in v))
    cnt = Counter(variantes)
    return max(cnt, key=lambda v: (score(v), cnt[v], -len(v)))


# =============================================================================================== variantes
def _tokens_nombre(i: str) -> list[str]:
    return [t for t in (i or "").split("-") if len(t) > 1]


def _parecido(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def misma_persona(a: str, b: str, umbral: float = 0.8) -> bool:
    """Dos ids (slugs) de entrenador son la misma persona escrita de otra forma: el nombre de pila y el
    apellido del más corto aparecen (con erratas leves) en el más largo, en ese orden. 'pablo-laso' ==
    'pablo-lasso-biurrun', 'ahmet-kandemir' == 'ahmet-dursun-kandemir', 'roger-gregare' ==
    'roger-grimau-gregera'; 'joonas-iisalo' != 'tuomas-iisalo' (el nombre de pila no coincide)."""
    ta, tb = _tokens_nombre(a), _tokens_nombre(b)
    if not ta or not tb or a == b:
        return a == b
    if len(ta) > len(tb):
        ta, tb = tb, ta
    if len(ta) == 1:
        return False
    # nombre de pila: primero del corto en algún sitio del largo (el largo puede llevar un nombre delante)
    i0 = next((i for i, t in enumerate(tb) if _parecido(ta[0], t) >= umbral), None)
    if i0 is None:
        return False
    # apellido: último del corto en un token posterior del largo
    return any(_parecido(ta[-1], t) >= umbral for t in tb[i0 + 1:])


def fusionar_variantes(df: pd.DataFrame, alias: Alias) -> pd.DataFrame:
    """Une las grafías de un mismo entrenador dentro de cada club-temporada (la fuente de la BSL y la GBL
    teclea el nombre partido a partido: 'Gianmarco Pozzeco' / 'Gianmarco Pozzecco'). El id que queda es el
    más frecuente del grupo. No une los pares declarados distintos en config/entrenadores_alias.json."""
    if df.empty or "entrenador_id" not in df:
        return df
    distintos = alias.distintos
    df = df.copy()
    for _, g in df[df["entrenador_id"].notna()].groupby("equipo_id"):
        cuenta = g["entrenador_id"].value_counts()
        ids = list(cuenta.index)          # del más frecuente al menos
        # todas las grafías de cada id (el id puede venir de un alias manual: «carlos-duran-ortega» → «carles-duran»)
        grafias = {i: {i} | {slug(n) for n in g.loc[g["entrenador_id"] == i, "entrenador"].dropna()} for i in ids}
        destino = {}
        for i, a in enumerate(ids):
            if a in destino:
                continue
            for b in ids[i + 1:]:
                if b in destino or frozenset((a, b)) in distintos:
                    continue
                if any(misma_persona(x, y, 0.7) for x in grafias[a] | {k for k, v in destino.items() if v == a}
                       for y in grafias[b]):
                    destino[b] = a
        if destino:
            m = df.index.isin(g.index) & df["entrenador_id"].isin(list(destino))
            df.loc[m, "entrenador_id"] = df.loc[m, "entrenador_id"].map(destino)
    return df


# =============================================================================================== FIBA LiveStats
def extractor_fiba_livestats(doc: dict) -> list[dict]:
    """data.json de FIBA LiveStats (fibalivestats.dcd.shared.geniussports.com/data/<id>/data.json) →
    [{"lado": "1"|"2", "equipo", "codigo", "entrenador", "entrenador_id_fuente", "puntos", "asistentes"}].
    tm["N"]["coach"] es "Nombre Apellido" (a veces "N. Apellido"); coachDetails trae firstName/familyName
    (y sus versiones internationalFirstName/internationalFamilyName, sin caracteres locales)."""
    out = []
    tms = (doc or {}).get("tm") or {}
    for lado in ("1", "2"):
        t = tms.get(lado) or {}
        if not t:
            continue
        det = t.get("coachDetails") or {}
        first = det.get("internationalFirstName") or det.get("firstName")
        last = det.get("internationalFamilyName") or det.get("familyName")
        name = f"{first or ''} {last or ''}".strip() or t.get("coach")
        # el nombre local (con acentos) es mejor para mostrar; el internacional, para el id
        local = f"{det.get('firstName') or ''} {det.get('familyName') or ''}".strip()
        pts = t.get("full_score", t.get("score"))
        out.append({"lado": lado, "equipo": t.get("name") or t.get("nameInternational"),
                    "codigo": t.get("code") or t.get("shortName"),
                    "entrenador": local or name or None, "entrenador_clave": name or None,
                    "entrenador_id_fuente": det.get("personId") or det.get("id"),
                    "puntos": _num(pts),
                    "asistentes": [x for x in (t.get("assistcoach1"), t.get("assistcoach2")) if x]})
    return out


def _find_livestats(docs: Any) -> dict | None:
    if isinstance(docs, dict):
        if isinstance(docs.get("tm"), dict):
            return docs
        for v in docs.values():
            if isinstance(v, dict) and isinstance(v.get("tm"), dict):
                return v
    return None


def lector_fiba_livestats(item: dict, lc: "LectorCtx") -> dict | None:
    """Lector genérico para fuentes cuyo bruto pbp guarda el data.json de FIBA LiveStats. Los ids de equipo
    salen del parse() de la propia fuente (los mismos que en quintetos): tm["1"] → equipo cuyo nombre
    coincide (o, si no, el primero de Game.teams), tm["2"] → el otro."""
    doc = _find_livestats(item.get("docs"))
    if not doc:
        return None
    sides = extractor_fiba_livestats(doc)
    g = lc.src.parse(item["docs"], item["ref"], lc.ctx)
    teams = list(g.teams)
    if len(teams) != 2 or len(sides) != 2:
        return None
    names = {t: _norm(g.team_names.get(t)) for t in teams}
    first = next((t for t in teams if names[t] and names[t] == _norm(sides[0]["equipo"])), teams[0])
    order = [first, teams[1] if first == teams[0] else teams[0]]
    lados = []
    for s, tid in zip(sides, order):
        lados.append({"equipo_id": tid, "equipo": g.team_names.get(tid) or s["equipo"], "puntos": s["puntos"],
                      "entrenador": s["entrenador"], "entrenador_clave": s.get("entrenador_clave"),
                      "entrenador_id_fuente": s["entrenador_id_fuente"]})
    return {"fecha": g.date, "fase": g.phase, "lados": lados, "local_primero": True}


# =============================================================================================== utilidades
def _num(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _s(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _ascii(str(s or "")).lower()).strip()


def _fecha(v) -> str | None:
    s = _s(v)
    return s[:10] if s else None


# =============================================================================================== lectores
@dataclass
class LectorCtx:
    liga: str
    temporada: str
    ctx: Any          # bbstats.lineups.sources.base.Ctx
    src: Any          # PBPSource de la liga
    main: Any         # payload del último bruto principal


def _lector_euroleague(item: dict, lc: LectorCtx) -> dict | None:
    docs, ref = item.get("docs") or {}, item.get("ref") or {}
    pbp, box = docs.get("pbp") or {}, docs.get("box") or {}
    codes = [_s(pbp.get("CodeTeamA")), _s(pbp.get("CodeTeamB"))]
    names = {codes[0]: pbp.get("TeamA"), codes[1]: pbp.get("TeamB")}
    per_team = {}
    for i, st in enumerate(box.get("Stats") or []):
        tid = next((_s(p.get("Team")) for p in st.get("PlayersStats") or [] if _s(p.get("Team"))), None)
        tid = tid or (codes[i] if i < 2 else None)
        per_team[tid] = {"coach": st.get("Coach"), "pts": _num((st.get("totr") or {}).get("Points")),
                         "name": st.get("Team")}
    if not all(codes):
        codes = list(per_team)[:2]
    lados = []
    for tid in codes:
        d = per_team.get(tid) or {}
        lados.append({"equipo_id": tid, "equipo": names.get(tid) or d.get("name"), "puntos": d.get("pts"),
                      "entrenador": d.get("coach")})
    return {"fecha": ref.get("date"), "fase": ref.get("phase"), "lados": lados, "local_primero": True}


def _acb_club(team: dict | None) -> str | None:
    team = team or {}
    return _s(team.get("clubId") or team.get("id"))


def _lector_acb(item: dict, lc: LectorCtx) -> dict | None:
    docs, ref = item.get("docs") or {}, item.get("ref") or {}
    pbp = docs.get("pbp") or {}
    box = docs.get("box")
    if not box and isinstance(lc.main, dict):
        box = (lc.main.get("boxscores") or {}).get(str(ref.get("game_id")))
    box = box or {}
    tbs = box.get("teamBoxscores") or []
    home, away = _acb_club(pbp.get("homeTeam")), _acb_club(pbp.get("awayTeam"))
    if (not home or not away) and len(tbs) == 2:
        home, away = _acb_club(tbs[0].get("team")), _acb_club(tbs[1].get("team"))
    names = {home: (pbp.get("homeTeam") or {}).get("fullName"), away: (pbp.get("awayTeam") or {}).get("fullName")}
    per = {}
    for tb in tbs:
        tid = _acb_club(tb.get("team"))
        q0 = next((p for p in tb.get("statsByPeriods") or [] if p.get("quarter") == 0), None)
        st = (q0 or {}).get("stats") or {}
        pts = (st.get("total") or {}).get("points")
        if pts is None:
            pts = sum((p.get("points") or 0) for p in st.get("players") or []) + ((st.get("team") or {}).get("points") or 0) \
                if st.get("players") else None
        per[tid] = {"coach": tb.get("headCoach"), "pts": _num(pts), "name": (tb.get("team") or {}).get("fullName")}
    lados = [{"equipo_id": t, "equipo": names.get(t) or (per.get(t) or {}).get("name"),
              "puntos": (per.get(t) or {}).get("pts"), "entrenador": (per.get(t) or {}).get("coach")}
             for t in (home, away)]
    return {"fecha": ref.get("date"), "fase": ref.get("phase"), "lados": lados, "local_primero": True}


def _lector_lba(item: dict, lc: LectorCtx) -> dict | None:
    docs, ref = item.get("docs") or {}, item.get("ref") or {}
    pbp = ((docs.get("pbp") or {}).get("pbp")) or {}
    scores = docs.get("scores")
    if not scores and isinstance(lc.main, dict):
        scores = (lc.main.get("scores") or {}).get(str(ref.get("game_id")))
    scores = scores or {}
    rt = ref.get("teams") or [None, None]
    home, away = _s(pbp.get("ht_id")) or rt[0], _s(pbp.get("vt_id")) or rt[1]
    names = ref.get("team_names") or {}
    ce = scores.get("coaches_extra") or {}
    sc = scores.get("scores") or {}
    lados = []
    for tid, side, sk in ((home, "home", "ht"), (away, "visitor", "vt")):
        c = ce.get(side) or {}
        name = f"{c.get('name') or ''} {c.get('surname') or ''}".strip() or None
        lados.append({"equipo_id": tid, "equipo": names.get(tid) or tid,
                      "puntos": _num(((sc.get(sk) or {}).get("totals") or {}).get("pun")),
                      "entrenador": name, "entrenador_id_fuente": c.get("id"),
                      "extra": {"desde": c.get("start_date"), "hasta": c.get("end_date")}})
    return {"fecha": ref.get("date"), "fase": ref.get("phase"), "lados": lados, "local_primero": True}


def _lector_bbl(item: dict, lc: LectorCtx) -> dict | None:
    docs, ref = item.get("docs") or {}, item.get("ref") or {}
    gd, gs = docs.get("initialGameData") or {}, docs.get("initialGameStats") or {}
    comments = defaultdict(list)
    for c in gd.get("coachComments") or []:
        sc = c.get("seasonCoach") or {}
        tid = _s((sc.get("seasonTeam") or {}).get("id"))
        name = f"{sc.get('firstName') or ''} {sc.get('lastName') or ''}".strip()
        if tid and name:
            comments[tid].append({"nombre": name, "es_principal": bool(sc.get("isHeadCoach")), "id": sc.get("id")})
    res = gd.get("result") or {}
    lados = []
    for side, key in (("homeTeam", "homeTeamFinalScore"), ("guestTeam", "guestTeamFinalScore")):
        t, ts = gd.get(side) or {}, gs.get(side) or {}
        tid = _s(t.get("teamId")) or _s(ts.get("id"))
        com = comments.get(_s(t.get("seasonTeamId")) or "") or comments.get(tid or "") or comments.get(_s(ts.get("id")) or "") or []
        lados.append({"equipo_id": tid, "equipo": t.get("name"), "puntos": _num(res.get(key)), "entrenador": None,
                      "extra": {"comentarios": com, "temporada": ts.get("headCoachName")}})
    return {"fecha": ref.get("date") or gd.get("scheduledTime"), "fase": ref.get("phase"), "lados": lados,
            "local_primero": True}


def _lector_statsv3(item: dict, lc: LectorCtx) -> dict | None:
    """NBA y G League (boxscoretraditionalv3): equipos y puntos; el entrenador viene del complemento."""
    docs, ref = item.get("docs") or {}, item.get("ref") or {}
    box = (docs.get("box") or {}).get("boxScoreTraditional") or {}
    lados = []
    for key in ("homeTeam", "awayTeam"):
        t = box.get(key) or {}
        if not t:
            continue
        tid = lc.src.team_id(t.get("teamId"), t.get("teamTricode"), lc.ctx)
        lados.append({"equipo_id": tid, "equipo": f"{t.get('teamCity', '')} {t.get('teamName', '')}".strip(),
                      "puntos": _num((t.get("statistics") or {}).get("points")), "entrenador": None,
                      "extra": {"team_id_api": t.get("teamId"), "tricode": t.get("teamTricode")}})
    if len(lados) != 2:
        return None
    return {"fecha": ref.get("date"), "fase": ref.get("phase"), "lados": lados, "local_primero": True}


def _lector_lnb(item: dict, lc: LectorCtx) -> dict | None:
    docs, ref = item.get("docs") or {}, item.get("ref") or {}
    sts, pbp = docs.get("statistics") or {}, docs.get("pbp") or {}
    fx = sts.get("fixture") or pbp.get("fixture") or {}
    comps = sorted(fx.get("competitors") or [], key=lambda c: not c.get("isHome"))
    g = lc.src.parse(docs, ref, lc.ctx)   # ids de equipo (external_id de lnb.fr) igual que en quintetos
    if len(g.teams) != len(comps) or len(comps) != 2:
        return None
    lados = [{"equipo_id": tid, "equipo": g.team_names.get(tid) or c.get("name"), "puntos": _num(c.get("score")),
              "entrenador": None} for tid, c in zip(g.teams, comps)]
    return {"fecha": ref.get("date") or fx.get("startTimeUTC"), "fase": ref.get("phase"), "lados": lados,
            "local_primero": True}


# =============================================================================================== complementos
@dataclass
class TemporadaCtx:
    liga: str
    temporada: str
    cfg: dict                 # config completa
    lcfg: dict                # config de la liga
    store: RawStore
    descargar: bool
    http_factory: Callable[[], HttpClient]
    progreso: Callable[[str], None]
    errores: list = field(default_factory=list)
    _http: HttpClient | None = None

    @property
    def http(self) -> HttpClient:
        if self._http is None:
            self._http = self.http_factory()
        return self._http

    @property
    def start_year(self) -> int:
        return int(self.temporada[:4])


def _cargar_paquetes(tc: TemporadaCtx) -> dict:
    """Une los paquetes entrenadores_<liga>_<t>_*.json.gz guardados: {clave: documento} (el más reciente gana)."""
    out: dict = {}
    for p in tc.store.list(tc.liga, tc.temporada, kind=KIND):
        out.update((RawStore.load(p).get("payload") or {}).get("documentos") or {})
    return out


def _guardar_paquete(tc: TemporadaCtx, nuevos: dict, fuente: str) -> None:
    if not nuevos:
        return
    now = utc_now()
    meta = {"liga": tc.liga, "temporada": tc.temporada, "tipo": KIND, "fuente": fuente,
            "version_bbstats": __version__, "fecha_extraccion": now.isoformat(),
            "fecha_extraccion_stamp": utc_stamp(now), "claves": sorted(nuevos),
            "peticiones": tc.http.request_log() if tc._http else [], "errores": list(tc.errores)}
    path = tc.store.save(tc.liga, tc.temporada, meta, {"documentos": nuevos}, kind=KIND)
    tc.progreso(f"[{tc.liga}] entrenadores: bruto guardado en {path.name} ({len(nuevos)} documentos)")


def _descargar(tc: TemporadaCtx, claves: dict[str, Callable[[], Any]], fuente: str,
               refrescar: Callable[[str], bool] = lambda k: False) -> dict:
    """Devuelve {clave: documento}: los ya guardados y, si hay descarga, los que falten (o los que
    `refrescar(clave)` pide actualizar). Lo nuevo se guarda en un paquete aparte."""
    docs = _cargar_paquetes(tc)
    if not tc.descargar:
        return docs
    nuevos = {}
    for k, fn in claves.items():
        if k in docs and not refrescar(k):
            continue
        try:
            nuevos[k] = fn()
        except Exception as exc:  # noqa: BLE001 - una petición caída no detiene el resto
            tc.errores.append(f"{k}: {type(exc).__name__}: {exc}")
    _guardar_paquete(tc, nuevos, fuente)
    docs.update(nuevos)
    return docs


# ---- NBA: Basketball-Reference
BREF = "https://www.basketball-reference.com"
_COACH_LINE = re.compile(r"Coach:</strong>(.*?)</p>", re.S)
_COACH_ITEM = re.compile(r'<a href="/coaches/([^"/]+)\.html">([^<]+)</a>\s*\((\d+)-(\d+)\)')


def parse_bref_coaches(html: str) -> list[dict]:
    """'Coach: <a href="/coaches/jenkita01c.html">Taylor Jenkins</a> (44-29), …' → [{id, nombre, v, d}]."""
    m = _COACH_LINE.search(html or "")
    if not m:
        return []
    return [{"id": a, "nombre": b.strip(), "v": int(c), "d": int(d)} for a, b, c, d in _COACH_ITEM.findall(m.group(1))]


def _complemento_nba(df: pd.DataFrame, tc: TemporadaCtx) -> pd.DataFrame:
    if df.empty:
        return df
    year = tc.start_year + 1
    teams = sorted(df["equipo_id"].dropna().unique())
    actual = tc.temporada == tc.cfg.get("temporada_por_defecto")

    def fetch(t):
        return lambda: tc.http.get_text(f"{BREF}/teams/{t}/{year}.html")

    docs = _descargar(tc, {f"bref:{t}": fetch(t) for t in teams}, "basketball-reference.com teams/<EQ>/<año>.html",
                      refrescar=lambda k: actual)
    df = df.copy()
    for t in teams:
        coaches = parse_bref_coaches(docs.get(f"bref:{t}") or "")
        if not coaches:
            tc.errores.append(f"bref {t}: sin línea 'Coach:'")
            continue
        idx = df.index[(df["equipo_id"] == t)]
        sub = df.loc[idx].sort_values(["fecha", "game_id"])
        reg = sub[sub["fase"] == "regular"]
        pos = 0
        for c in coaches:
            n = c["v"] + c["d"]
            block = reg.iloc[pos: pos + n]
            pos += n
            ok = (block["resultado"] == "V").sum() == c["v"] and (block["resultado"] == "D").sum() == c["d"]
            df.loc[block.index, ["entrenador", "entrenador_id_fuente", "metodo", "validacion_vd"]] = \
                [c["nombre"], f"bref:{c['id']}", "orden_vd", "ok" if ok else "no_coincide"]
        if pos != len(reg):
            tc.errores.append(f"bref {t}: {len(reg)} partidos de temporada regular y {pos} en la línea Coach")
        last = coaches[-1]
        post = sub[sub["fase"] != "regular"]
        df.loc[post.index, ["entrenador", "entrenador_id_fuente", "metodo"]] = \
            [last["nombre"], f"bref:{last['id']}", "temporada_ultimo"]
    df["fuente"] = df["fuente"].where(df["entrenador"].isna(), "basketball-reference.com")
    return df


# ---- G League: stats.gleague.nba.com commonteamroster
def _complemento_gleague(df: pd.DataFrame, tc: TemporadaCtx) -> pd.DataFrame:
    if df.empty:
        return df
    base = (tc.lcfg.get("base_url") or "https://stats.gleague.nba.com/stats").rstrip("/")
    headers = {"Accept": "application/json, text/plain, */*", **(tc.lcfg.get("headers") or {})}
    season = ((tc.lcfg.get("temporadas") or {}).get(tc.temporada) or {}).get("season", tc.temporada)
    actual = tc.temporada == tc.cfg.get("temporada_por_defecto")
    api_ids = {}
    for ex, tid in zip(df["extra"], df["equipo_id"]):
        if isinstance(ex, dict) and ex.get("team_id_api"):
            api_ids[str(tid)] = ex["team_id_api"]

    def fetch(api_id):
        return lambda: tc.http.get_json(f"{base}/commonteamroster", headers=headers,
                                        params={"LeagueID": tc.lcfg.get("league_id", "20"), "Season": season,
                                                "TeamID": api_id})

    docs = _descargar(tc, {f"roster:{t}": fetch(a) for t, a in api_ids.items()},
                      "stats.gleague.nba.com commonteamroster", refrescar=lambda k: actual)
    from .lineups.sources.nba_stats import rows
    df = df.copy()
    for t in api_ids:
        heads = [r for r in rows(docs.get(f"roster:{t}"), "Coaches") if str(r.get("COACH_TYPE", "")).lower() == "head coach"]
        if len(heads) != 1:
            if heads:
                tc.errores.append(f"G League {t}: {len(heads)} entrenadores principales sin fechas; no se asignan")
            continue
        h = heads[0]
        m = df["equipo_id"] == t
        df.loc[m, ["entrenador", "entrenador_id_fuente", "metodo", "fuente"]] = \
            [h.get("COACH_NAME"), f"gleague:{h.get('COACH_ID')}", "temporada", "stats.gleague.nba.com commonteamroster"]
    return df


# ---- LNB: api-prod.lnb.fr altrstats/getCoachingStaff
def _complemento_lnb(df: pd.DataFrame, tc: TemporadaCtx) -> pd.DataFrame:
    if df.empty:
        return df
    from .adapters.lnb import API, TOKEN_URL
    teams = sorted(df["equipo_id"].dropna().unique())
    actual = tc.temporada == tc.cfg.get("temporada_por_defecto")
    tok: dict = {}

    def headers():
        if "t" not in tok:
            tok["t"] = tc.http.get_json(TOKEN_URL)["token"]
        return {"Authorization": f"Bearer {tok['t']}", "device_type": "web", "language_code": "fr",
                "Origin": "https://lnb.fr", "Referer": "https://lnb.fr/"}

    def fetch(t):
        return lambda: tc.http.post_json(f"{API}/altrstats/getCoachingStaff", headers=headers(),
                                         json_body={"teamExternalId": int(t), "year": tc.start_year})

    docs = _descargar(tc, {f"staff:{t}": fetch(t) for t in teams if str(t).isdigit()},
                      "api-prod.lnb.fr altrstats/getCoachingStaff", refrescar=lambda k: actual)
    df = df.copy()
    for t in teams:
        heads = [r for r in ((docs.get(f"staff:{t}") or {}).get("data") or []) if r.get("role_type") == "HEAD_COACH"]
        if not heads:
            continue
        m = df.index[df["equipo_id"] == t]
        for i in m:
            f = df.at[i, "fecha"]
            cand = [h for h in heads if (h.get("from_date") or "0000") <= (f or "") <= (h.get("to_date") or "9999")]
            if len(heads) == 1:
                cand = heads
            if len(cand) > 1:   # solapes: el que empezó más tarde (el sustituto)
                cand = sorted(cand, key=lambda h: h.get("from_date") or "")[-1:]
            if len(cand) == 1:
                p = cand[0].get("person") or {}
                df.loc[i, ["entrenador", "entrenador_id_fuente", "metodo", "fuente"]] = [
                    f"{p.get('first_name') or ''} {p.get('family_name') or ''}".strip(),
                    f"lnb:{p.get('external_id')}", "temporada_fechas" if len(heads) > 1 else "temporada",
                    "api-prod.lnb.fr getCoachingStaff"]
    return df


# ---- BBL: quién habla en la rueda de prensa (coachComments) + entrenador de la temporada
def _resolver_bbl(df: pd.DataFrame, tc: TemporadaCtx, alias: Alias) -> pd.DataFrame:
    """Para cada equipo-temporada: candidatos a principal = headCoachName (último de la temporada) ∪ quienes
    hablan con isHeadCoach = true. En cada partido, si habla un candidato → ese entrenador (metodo
    "rueda_prensa"). Si habla otro (ayudante): si lo hace en ≥ 2 partidos seguidos, o justo entre dos
    entrenadores principales distintos, se toma como interino; si no, el partido queda para imputar."""
    df = df.copy()
    for t, sub in df.groupby("equipo_id", sort=False):
        sub = sub.sort_values(["fecha", "game_id"])
        heads = set()
        for ex in sub["extra"]:
            ex = ex if isinstance(ex, dict) else {}
            if ex.get("temporada"):
                heads.add(alias.id_de(ex["temporada"]))
            for c in ex.get("comentarios") or []:
                if c.get("es_principal"):
                    heads.add(alias.id_de(c["nombre"]))
        speakers = []
        for i, ex in zip(sub.index, sub["extra"]):
            ex = ex if isinstance(ex, dict) else {}
            com = ex.get("comentarios") or []
            pick = next((c for c in com if alias.id_de(c["nombre"]) in heads), None)
            if pick:
                speakers.append((i, pick, True))
            elif com:
                speakers.append((i, com[0], False))
            else:
                speakers.append((i, None, None))
        # tramos de no principales
        n = len(speakers)
        k = 0
        while k < n:
            i, c, is_head = speakers[k]
            if c is not None and is_head:
                df.loc[i, ["entrenador", "entrenador_id_fuente", "metodo"]] = [c["nombre"], _bbl_id(c), "rueda_prensa"]
                k += 1
                continue
            if c is None:
                k += 1
                continue
            sid = alias.id_de(c["nombre"])
            j = k
            while j + 1 < n and speakers[j + 1][1] is not None and not speakers[j + 1][2] \
                    and alias.id_de(speakers[j + 1][1]["nombre"]) == sid:
                j += 1
            before = next((alias.id_de(speakers[x][1]["nombre"]) for x in range(k - 1, -1, -1)
                           if speakers[x][1] is not None and speakers[x][2]), None)
            after = next((alias.id_de(speakers[x][1]["nombre"]) for x in range(j + 1, n)
                          if speakers[x][1] is not None and speakers[x][2]), None)
            run = j - k + 1
            if run >= 2 or (before and after and before != after) or (before is None and after is None):
                for x in range(k, j + 1):
                    ii, cc, _ = speakers[x]
                    df.loc[ii, ["entrenador", "entrenador_id_fuente", "metodo"]] = \
                        [cc["nombre"], _bbl_id(cc), "rueda_prensa_no_principal"]
            k = j + 1
        # equipos sin ninguna rueda de prensa: entrenador de la temporada (headCoachName)
        if all(c is None for _, c, _ in speakers):
            name = next((ex.get("temporada") for ex in sub["extra"] if isinstance(ex, dict) and ex.get("temporada")), None)
            if name:
                df.loc[sub.index, ["entrenador", "metodo"]] = [name, "temporada"]
    df["fuente"] = "easycredit-bbl.de (coachComments / headCoachName)"
    return df


def _bbl_id(c: dict) -> str | None:
    return f"bbl:{c['id']}" if c.get("id") else None


# =============================================================================================== registro
@dataclass
class Extractor:
    """Cómo obtener entrenadores en una liga.
    lector(item, LectorCtx) -> {"fecha", "fase", "lados": [{equipo_id, equipo, puntos, entrenador,
        entrenador_id_fuente?, extra?}, …(2)]} | None.  `item` = {"ref", "docs"} del bruto pbp.
    docs_principal(main_payload, game_id) -> docs del partido sacados del bruto principal (si el pbp no lo tiene).
    complemento(df, TemporadaCtx) -> df con entrenador/metodo/fuente rellenados (fuente de temporada, con red).
    resolver(df, TemporadaCtx, Alias) -> df (lógica propia de la liga sobre los partidos ya leídos, sin red)."""
    lector: Callable[[dict, LectorCtx], dict | None]
    fuente: str = ""
    docs_principal: Callable[[Any, str], dict | None] | None = None
    complemento: Callable[[pd.DataFrame, TemporadaCtx], pd.DataFrame] | None = None
    resolver: Callable[[pd.DataFrame, TemporadaCtx, Alias], pd.DataFrame] | None = None


EXTRACTORES: dict[str, Extractor] = {}


def registrar(clave: str, extractor: Extractor) -> None:
    """`clave` = código de liga (p.ej. "bcl") o nombre de la fuente pbp (config.ligas.<liga>.pbp)."""
    EXTRACTORES[clave] = extractor


def extractor_de(liga: str, lcfg: dict) -> Extractor | None:
    for k in (liga, lcfg.get("entrenadores"), lcfg.get("pbp")):
        if k and k in EXTRACTORES:
            return EXTRACTORES[k]
    return None


registrar("euroleague", Extractor(_lector_euroleague, "live.euroleague.net Boxscore (Stats[].Coach)"))
registrar("eurocup", Extractor(_lector_euroleague, "live.euroleague.net Boxscore (Stats[].Coach)"))
registrar("acb", Extractor(_lector_acb, "api2.acb.com Result/boxscores (headCoach)",
                           docs_principal=lambda m, g: {"box": ((m or {}).get("boxscores") or {}).get(g)}
                           if ((m or {}).get("boxscores") or {}).get(g) else None))
registrar("lba", Extractor(_lector_lba, "legabasket.it matches-scores-by-id (coaches_extra)",
                           docs_principal=lambda m, g: {"scores": ((m or {}).get("scores") or {}).get(g)}
                           if ((m or {}).get("scores") or {}).get(g) else None))
registrar("bbl", Extractor(_lector_bbl, "easycredit-bbl.de (coachComments / headCoachName)",
                           docs_principal=lambda m, g: ((m or {}).get("games") or {}).get(g),
                           resolver=_resolver_bbl))
registrar("nba", Extractor(_lector_statsv3, "basketball-reference.com", complemento=_complemento_nba))
registrar("gleague", Extractor(_lector_statsv3, "stats.gleague.nba.com commonteamroster",
                               complemento=_complemento_gleague))
registrar("lnb", Extractor(_lector_lnb, "api-prod.lnb.fr getCoachingStaff", complemento=_complemento_lnb))
registrar("fiba_livestats", Extractor(lector_fiba_livestats, "FIBA LiveStats data.json (tm[].coach)"))
# Ligas nuevas (bcl, fec: fiba.basketball; bsl, gbl: FIBA LiveStats con el data.json en el bruto principal)
from .lineups.sources import fiba_livestats as _fls, fiba_web as _fweb  # noqa: E402
registrar("fiba_web", Extractor(_fweb.lector_entrenadores, "fiba.basketball staffA/staffB (Head Coach)",
                                docs_principal=_fweb.docs_principal))
for _liga in ("bsl", "gbl", "bnxt"):
    registrar(_liga, Extractor(lector_fiba_livestats, "FIBA LiveStats data.json (tm[].coach)",
                               docs_principal=_fls.docs_principal))
# NCAA (ESPN): un entrenador por temporada (plantilla de ESPN, sólo top-50), traducido a tm[].coach por to_fls
from .lineups.sources import ncaa as _ncaa, vtb as _vtb  # noqa: E402
registrar("vtb", Extractor(lector_fiba_livestats, "Infobasket GetOnline (Coaches, PosID 1000)",
                           docs_principal=_vtb.docs_principal))
registrar("ncaa", Extractor(lector_fiba_livestats, "ESPN teams/<id>/roster (coach, uno por temporada)",
                            docs_principal=_ncaa.docs_principal))


# ---- FEB (Primera, Segunda y Tercera FEB): el partido NO trae el entrenador; la página pública del equipo de esa
# temporada (Equipo.aspx?i=<id inscripción>, guardada en el bruto principal: payload["equipos"]) trae UN entrenador
# principal (el vigente al descargar: para temporadas cerradas, el último de la temporada). Se asigna a todos los
# partidos del equipo con metodo = "temporada" (como la G League): no se ven los cambios a mitad de temporada.
def _lector_feb(item: dict, lc: LectorCtx) -> dict | None:
    from .adapters.feb import header
    doc = (item.get("docs") or {}).get("data") or {}
    ref = item.get("ref") or {}
    teams = header(doc).get("TEAM") or []
    if len(teams) != 2:
        return None
    lados = [{"equipo_id": _s(t.get("id")), "equipo": " ".join(str(t.get("name") or "").split()),
              "puntos": _num(t.get("pts")), "entrenador": None} for t in teams]
    return {"fecha": ref.get("date"), "fase": ref.get("phase"), "lados": lados, "local_primero": True}


def _complemento_feb(df: pd.DataFrame, tc: TemporadaCtx) -> pd.DataFrame:
    from .adapters.feb import parse_team_page
    if df.empty:
        return df
    _, doc = tc.store.load_season(tc.liga, tc.temporada)
    equipos = ((doc or {}).get("payload") or {}).get("equipos") or {}
    df = df.copy()
    sin = []
    for tid in df["equipo_id"].dropna().unique():
        ent = parse_team_page(equipos.get(str(tid)) or "").get("entrenador")
        if not ent:
            sin.append(tid)
            continue
        m = df["equipo_id"] == tid
        df.loc[m, ["entrenador", "entrenador_id_fuente", "metodo", "fuente"]] = \
            [ent["nombre"], f"feb:{ent['id']}" if ent.get("id") else None, "temporada", "baloncestoenvivo.feb.es Equipo.aspx (entrenador)"]
    if sin:
        tc.errores.append(f"{len(sin)} equipos sin entrenador en su página: {sorted(map(str, sin))[:10]}")
    return df


from .lineups.sources import feb as _feb  # noqa: E402
registrar("feb", Extractor(_lector_feb, "baloncestoenvivo.feb.es Equipo.aspx (entrenador de la temporada)",
                           docs_principal=_feb.docs_principal, complemento=_complemento_feb))


# =============================================================================================== núcleo puro
def imputar(df: pd.DataFrame) -> pd.DataFrame:
    """Rellena huecos de entrenador por equipo-temporada (orden por fecha): entre dos partidos del mismo
    entrenador → ese entrenador (metodo "tramo"); antes del primero / después del último → el más cercano
    (metodo "tramo_borde"). Entre dos entrenadores distintos se deja vacío. Marca imputado = 1."""
    df = df.copy()
    if "imputado" not in df:
        df["imputado"] = 0
    if "metodo" not in df:
        df["metodo"] = None
    for _, sub in df.groupby(["liga", "temporada", "equipo_id"], sort=False):
        sub = sub.sort_values(["fecha", "game_id"])
        ids = list(sub["entrenador_id"])
        known = [k for k, v in enumerate(ids) if isinstance(v, str) and v]
        if not known:
            continue
        idx = list(sub.index)
        for k, v in enumerate(ids):
            if isinstance(v, str) and v:
                continue
            prev = max((x for x in known if x < k), default=None)
            nxt = min((x for x in known if x > k), default=None)
            src = None
            if prev is not None and nxt is not None:
                if ids[prev] == ids[nxt]:
                    src, how = prev, "tramo"
            elif prev is not None or nxt is not None:
                src, how = (prev if prev is not None else nxt), "tramo_borde"
            if src is not None:
                i, j = idx[k], idx[src]
                for c in ("entrenador", "entrenador_id", "entrenador_id_fuente"):
                    if c in df:
                        df.at[i, c] = df.at[j, c]
                df.at[i, "imputado"] = 1
                df.at[i, "metodo"] = how
    return df


def construir_tramos(df: pd.DataFrame) -> pd.DataFrame:
    """Partidos (una fila por partido-equipo) → una fila por club-temporada-entrenador.
    `orden` = orden del primer partido; `n_tramos_consecutivos` > 1 si el entrenador vuelve tras otro
    (p.ej. interino durante una baja). `interino` = 1 (heurístico) si hay más de un entrenador y este no es el
    primero y dirige ≤ 5 partidos, o queda entre dos tramos del mismo otro entrenador."""
    rows = []
    if df.empty:
        return pd.DataFrame(columns=TRAMO_COLS)
    for (liga, temp, tid), sub in df.groupby(["liga", "temporada", "equipo_id"], sort=False):
        sub = sub[sub["entrenador_id"].notna() & (sub["entrenador_id"] != "")].sort_values(["fecha", "game_id"])
        if sub.empty:
            continue
        seq = list(sub["entrenador_id"])
        runs = []                       # tramos consecutivos [(id, ini, fin)]
        for k, v in enumerate(seq):
            if runs and runs[-1][0] == v:
                runs[-1][2] = k
            else:
                runs.append([v, k, k])
        order = list(dict.fromkeys(seq))
        n_coaches = len(order)
        equipo = sub["equipo"].dropna().iloc[-1] if sub["equipo"].notna().any() else tid
        for o, cid in enumerate(order, 1):
            g = sub[sub["entrenador_id"] == cid]
            res, fase = g["resultado"], g["fase"]
            my_runs = [r for r in runs if r[0] == cid]
            between_same = False
            for r in my_runs:
                b = next((x[0] for x in reversed(runs) if x[2] < r[1]), None)
                a = next((x[0] for x in runs if x[1] > r[2]), None)
                if b is not None and b == a and b != cid:
                    between_same = True
            interino = int(n_coaches > 1 and ((o > 1 and len(g) <= 5) or between_same))
            vd = g["validacion_vd"].dropna() if "validacion_vd" in g else pd.Series(dtype=object)
            rows.append({
                "liga": liga, "temporada": temp, "equipo_id": tid, "equipo": equipo, "orden": o,
                "entrenador_id": cid, "entrenador": g["entrenador"].dropna().iloc[0] if g["entrenador"].notna().any() else cid,
                "n_partidos": len(g), "n_regular": int((fase == "regular").sum()),
                "n_playoffs": int((fase == "playoffs").sum()), "n_otras": int((~fase.isin(["regular", "playoffs"])).sum()),
                "n_imputados": int(pd.to_numeric(g.get("imputado", 0), errors="coerce").fillna(0).astype(int).sum()),
                "primer_partido": g["fecha"].min(), "ultimo_partido": g["fecha"].max(),
                "victorias": int((res == "V").sum()), "derrotas": int((res == "D").sum()),
                "victorias_regular": int(((res == "V") & (fase == "regular")).sum()),
                "derrotas_regular": int(((res == "D") & (fase == "regular")).sum()),
                "victorias_playoffs": int(((res == "V") & (fase == "playoffs")).sum()),
                "derrotas_playoffs": int(((res == "D") & (fase == "playoffs")).sum()),
                "n_tramos_consecutivos": len(my_runs), "interino": interino, "entrenadores_equipo": n_coaches,
                "validacion_vd": (vd.iloc[0] if vd.nunique() == 1 else ";".join(sorted(vd.unique()))) if len(vd) else None,
                "fuente": ";".join(sorted(set(g["fuente"].dropna()))) if "fuente" in g else None,
                "partidos_ids": ";".join(g["game_id"].astype(str)),
            })
    return pd.DataFrame(rows, columns=TRAMO_COLS)


# =============================================================================================== ejecución
def _ligas_nombres(processed: Path, temporada: str, liga: str) -> dict:
    """team_id → equipo de ligas/<liga>.csv (temporada regular primero)."""
    p = processed / temporada / "ligas" / f"{liga}.csv"
    if not p.exists():
        return {}
    try:
        d = pd.read_csv(p, usecols=["team_id", "equipo", "fase"], dtype=str)
    except ValueError:
        return {}
    d = d[d["team_id"].notna() & ~d["team_id"].str.contains(";", na=False)]
    d = d.sort_values("fase", key=lambda s: s.map({"regular": 0, "playoffs": 1}).fillna(2))
    return d.drop_duplicates("team_id").set_index("team_id")["equipo"].to_dict()


def _partidos(liga: str, temporada: str, cfg: dict, store: RawStore, ext: Extractor,
              errores: list) -> pd.DataFrame:
    from .lineups.run import load_games, make_source
    from .lineups.sources.base import Ctx
    lcfg = cfg["ligas"][liga]
    src = make_source(lcfg["pbp"]) if lcfg.get("pbp") else None
    _, doc_main = store.load_season(liga, temporada)   # une los paquetes incrementales de la temporada
    main = doc_main["payload"] if doc_main else None
    ctx = Ctx(league=liga, season=temporada, cfg=lcfg, main_payload=main)
    lc = LectorCtx(liga, temporada, ctx, src, main)
    stored, _ = load_games(store, liga, temporada)
    items = {str(k): v for k, v in stored.items()}
    if ext.docs_principal and src is not None and main is not None:
        try:
            refs = src.games(ctx)          # sin red: usa el bruto principal (ACB, LBA, BBL)
        except Exception as exc:  # noqa: BLE001
            refs = []
            errores.append(f"lista de partidos del bruto principal: {type(exc).__name__}: {exc}")
        for ref in refs:
            gid = str(ref["game_id"])
            if gid in items or not ref.get("final"):
                continue
            docs = ext.docs_principal(main, gid)
            if docs:
                items[gid] = {"ref": ref, "docs": docs}
    rows = []
    for gid, item in items.items():
        try:
            g = ext.lector(item, lc)
        except Exception as exc:  # noqa: BLE001
            errores.append(f"{gid}: {type(exc).__name__}: {exc}")
            continue
        if not g or len(g.get("lados") or []) != 2:
            errores.append(f"{gid}: partido sin dos equipos")
            continue
        a, b = g["lados"]
        for me, op, local in ((a, b, 1), (b, a, 0)):
            pa, pb = me.get("puntos"), op.get("puntos")
            res = None if pa is None or pb is None or pa == pb else ("V" if pa > pb else "D")
            rows.append({"liga": liga, "temporada": temporada, "game_id": gid, "fecha": _fecha(g.get("fecha")),
                         "fase": g.get("fase") or (item.get("ref") or {}).get("phase"),
                         "equipo_id": _s(me.get("equipo_id")), "equipo": me.get("equipo"),
                         "rival_id": _s(op.get("equipo_id")), "local": local if g.get("local_primero") else None,
                         "puntos": pa, "puntos_rival": pb, "resultado": res,
                         "entrenador": nombre_visible(me.get("entrenador")),
                         "entrenador_clave": me.get("entrenador_clave"),
                         "entrenador_id_fuente": (f"{liga}:{me['entrenador_id_fuente']}"
                                                  if me.get("entrenador_id_fuente") not in (None, "") else None),
                         "fuente": ext.fuente if me.get("entrenador") else None,
                         "metodo": "partido" if me.get("entrenador") else None, "imputado": 0,
                         "validacion_vd": None, "extra": me.get("extra")})
    return pd.DataFrame(rows)


def run_league(liga: str, temporada: str, cfg: dict, store: RawStore, out_dir: Path, alias: Alias,
               descargar: bool, http_factory: Callable[[], HttpClient],
               progreso: Callable[[str], None]) -> dict:
    lcfg = cfg["ligas"][liga]
    rep: dict[str, Any] = {"liga": liga, "temporada": temporada, "estado": "sin_extractor", "errores": []}
    ext = extractor_de(liga, lcfg)
    if ext is None:
        return rep
    tc = TemporadaCtx(liga, temporada, cfg, lcfg, store, descargar, http_factory, progreso)
    df = _partidos(liga, temporada, cfg, store, ext, tc.errores)
    if df.empty:
        rep.update(estado="sin_datos", errores=tc.errores[:50])
        return rep
    if ext.complemento:
        df = ext.complemento(df, tc)
    if ext.resolver:
        df = ext.resolver(df, tc, alias)
    # nombre y id normalizados
    df["entrenador"] = df["entrenador"].map(nombre_visible)
    clave = df["entrenador_clave"].where(df["entrenador_clave"].notna(), df["entrenador"]) \
        if "entrenador_clave" in df else df["entrenador"]
    df["entrenador_id"] = clave.map(alias.id_de)
    vacio = df["entrenador_id"].isna()
    df.loc[vacio, ["entrenador", "entrenador_id_fuente", "fuente", "metodo"]] = None
    df = fusionar_variantes(df, alias)
    df["entrenador"] = [alias.nombres.get(i) or n for i, n in zip(df["entrenador_id"], df["entrenador"])]
    df = imputar(df)
    names = _ligas_nombres(resolve_path(cfg, "procesado"), temporada, liga)
    df["equipo"] = [names.get(t) or e for t, e in zip(df["equipo_id"], df["equipo"])]
    df = df.sort_values(["fecha", "game_id", "local"], ascending=[True, True, False]).reset_index(drop=True)
    tramos = construir_tramos(df)
    d = out_dir / temporada / "entrenadores"
    d.mkdir(parents=True, exist_ok=True)
    out_cols = PARTIDO_COLS + ["validacion_vd"]
    df.reindex(columns=out_cols).to_csv(d / f"{liga}_partidos.csv", index=False, encoding="utf-8")
    tramos.to_csv(d / f"{liga}_tramos.csv", index=False, encoding="utf-8")
    con = df["entrenador_id"].notna()
    clubs = df.groupby("equipo_id")["entrenador_id"].nunique()
    rep.update(estado="ok", partidos=int(df["game_id"].nunique()), filas=len(df),
               pct_con_entrenador=round(100 * con.mean(), 1),
               pct_observado=round(100 * (con & (df["imputado"] == 0)).mean(), 1),
               clubes=int(df["equipo_id"].nunique()), clubes_varios=int((clubs > 1).sum()),
               entrenadores=int(df["entrenador_id"].nunique()), errores=tc.errores[:50],
               n_errores=len(tc.errores))
    progreso(f"[{liga}] {temporada} entrenadores: {rep['partidos']} partidos, {rep['pct_con_entrenador']} % con "
             f"entrenador ({rep['pct_observado']} % observado), {rep['clubes']} clubes, {rep['clubes_varios']} con "
             f"más de uno" + (f", {len(tc.errores)} avisos" if tc.errores else ""))
    return rep


def tabla_global(processed: Path, alias: Alias | None = None) -> pd.DataFrame:
    """data/processed/entrenadores.csv a partir de todos los <t>/entrenadores/*_partidos.csv."""
    alias = alias or Alias.load()
    frames = [pd.read_csv(p, dtype=str) for p in sorted(processed.glob("*/entrenadores/*_partidos.csv"))]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df = df[df["entrenador_id"].notna()]
    rows = []
    for cid, g in df.groupby("entrenador_id"):
        clubs = (g["liga"] + ":" + g["temporada"] + ":" + g["equipo"].fillna(g["equipo_id"])).drop_duplicates()
        fuentes = sorted(set(g["entrenador_id_fuente"].dropna()))
        rows.append({"entrenador_id": cid,
                     "entrenador": alias.nombres.get(cid) or _mejor_nombre(list(g["entrenador"].dropna())),
                     "nacionalidad": None,
                     "ligas": ";".join(sorted(g["liga"].unique())),
                     "temporadas": ";".join(sorted(g["temporada"].unique())),
                     "n_temporadas": g["temporada"].nunique(),
                     "clubes": ";".join(sorted(clubs)),
                     "n_partidos": len(g), "n_imputados": int((g["imputado"] == "1").sum()),
                     "variantes_nombre": ";".join(sorted(set(g["entrenador"].dropna()))),
                     "ids_fuente": ";".join(fuentes)})
    out = pd.DataFrame(rows).sort_values("entrenador_id")
    out.to_csv(processed / "entrenadores.csv", index=False, encoding="utf-8")
    return out


def cobertura(processed: Path) -> pd.DataFrame:
    rows = []
    for p in sorted(processed.glob("*/entrenadores/*_partidos.csv")):
        df = pd.read_csv(p, dtype=str)
        if df.empty:
            continue
        con = df["entrenador_id"].notna()
        obs = con & (df["imputado"] != "1")
        clubs = df.groupby("equipo_id")["entrenador_id"].nunique()
        rows.append({"liga": df["liga"].iloc[0], "temporada": df["temporada"].iloc[0],
                     "partidos": df["game_id"].nunique(), "filas_partido_equipo": len(df),
                     "pct_con_entrenador": round(100 * con.mean(), 1),
                     "pct_observado": round(100 * obs.mean(), 1),
                     "pct_imputado": round(100 * (con & ~obs).mean(), 1),
                     "clubes": df["equipo_id"].nunique(), "clubes_varios_entrenadores": int((clubs > 1).sum()),
                     "entrenadores": df["entrenador_id"].nunique(),
                     "metodos": ";".join(f"{k}={v}" for k, v in df["metodo"].fillna("sin").value_counts().items())})
    out = pd.DataFrame(rows).sort_values(["liga", "temporada"]) if rows else pd.DataFrame()
    if not out.empty:
        out.to_csv(processed / "entrenadores_cobertura.csv", index=False, encoding="utf-8")
    return out


def ejecutar(temporadas: list[str] | None = None, ligas: list[str] | None = None, descargar: bool = True,
             config: dict | str | None = None, progreso: Callable[[str], None] | None = None) -> dict:
    cfg = config if isinstance(config, dict) else load_config(config)
    temporadas = temporadas or season_range(cfg.get("temporada_inicial"), cfg.get("temporada_por_defecto"))
    ligas = ligas or [l for l in active_leagues(cfg) if extractor_de(l, cfg["ligas"][l])]
    hcfg = cfg.get("http", {})
    factory = lambda: HttpClient(delay_s=hcfg.get("delay_s", 1.0), timeout_s=hcfg.get("timeout_s", 30),  # noqa: E731
                                 retries=hcfg.get("retries", 3), domain_delays=hcfg.get("delay_por_dominio", {}),
                                 curl_domains=tuple(hcfg.get("dominios_curl", [])))
    store = RawStore(resolve_path(cfg, "bruto"), compress=cfg.get("comprimir_bruto", False))
    processed = resolve_path(cfg, "procesado")
    alias = Alias.load()
    progress = progreso or print
    out = {}
    for t in temporadas:
        for l in ligas:
            try:
                out[f"{l}/{t}"] = run_league(l, t, cfg, store, processed, alias, descargar, factory, progress)
            except Exception as exc:  # noqa: BLE001 - una liga caída no detiene el resto
                log.exception("entrenadores %s %s", l, t)
                out[f"{l}/{t}"] = {"liga": l, "temporada": t, "estado": "error", "errores": [repr(exc)]}
                progress(f"[{l}] {t} entrenadores: ERROR {exc!r}")
    tabla_global(processed, alias)
    cob = cobertura(processed)
    if not cob.empty:
        progress("\n" + cob.drop(columns=["metodos"]).to_string(index=False))
    return out
