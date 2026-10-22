"""Tabla de correspondencia de jugadores entre ligas (crosswalk) con confianza y cola de revisión manual.

`identidad.resolver` (usada por los modelos A/B) une por nombre y año de nacimiento y prefiere perder puentes a
crearlos falsos, pero no deja rastro de POR QUÉ une ni de los casos dudosos. Este módulo hace el emparejamiento
explícito para todas las ligas (incluidas las FEB, que traen fecha de nacimiento y nacionalidad de la plantilla):

  nodo     = (liga, player_id) con sus registros de todas las temporadas (data/processed/<t>/ligas/<liga>.csv,
             fase total): nombre, fecha/año de nacimiento, nacionalidad (ISO), equipos y partidos por temporada.
  pareja   = dos nodos de ligas distintas (o de la misma liga si sus ids no son estables: BBL) que comparten al
             menos dos palabras del nombre normalizado, una contenida en la otra (las FEB dan nombre y dos apellidos,
             la ACB a veces un apellido).
  puntuación (0-1, suma acotada):
      nombre       igual 0,55 · contenido 0,45
      nacimiento   misma fecha +0,40 · dos fechas completas distintas → RECHAZO · (sin fecha completa) mismo
                   año ±1 +0,25 · años separados > 1,5 → RECHAZO
      nacionalidad igual +0,10 · distinta −0,25 (puede haber doble nacionalidad)
      unicidad     el nombre es único en las dos ligas (y no hay otra pareja posible) +0,20
      trayectoria  temporadas contiguas o solapadas compatibles +0,05; club con nombre común (filial) +0,05
      calendario   misma temporada en dos ligas que no se juegan a la vez sumando más partidos de los posibles,
                   o la misma liga con otro id en la misma temporada → RECHAZO
      ids FEB      el id de persona de la FEB es común a Primera, Segunda y Tercera FEB: mismo id = 1,0 (id_feb)
  Se unen (unión-búsqueda) las parejas con confianza >= `umbral_fusion`; las de [`umbral_revision`,
  `umbral_fusion`) y las que unirían dos ids distintos de una misma liga de ids estables van a la cola de revisión
  y NO se aplican. Tras una primera pasada, la fecha/año de nacimiento y la nacionalidad conocidos de un grupo se
  usan para volver a puntuar las parejas dudosas (una ACB sin fecha hereda la de su EuroLeague).
  Umbrales en config/sources.json → "identidad" (por defecto 0,80 y 0,50).

Salidas:
  data/processed/player_id_crosswalk.csv   fuente_liga, fuente_id, persona_id, confianza, metodo, nombre,
                                           anio_nacimiento, nacionalidad_iso, temporadas
  data/processed/crosswalk_revision.csv    parejas dudosas: los dos nodos, confianza, metodo, motivo
Uso: python -m bbmodel crosswalk
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from .identidad import CONCURRENTES, SUFIJOS

RAIZ = Path(__file__).resolve().parent.parent
PROC = RAIZ / "data" / "processed"
FEB = {"feb1", "feb2", "feb3"}
ID_INESTABLE = {"bbl"}            # ids de jugador que cambian entre temporadas: se permiten uniones en la liga
# pares de ligas que se juegan a la vez (un jugador puede estar en las dos la misma temporada): además de las de
# identidad.py, la ACB con las FEB y las FEB entre sí (jugadores vinculados / doble licencia)
CONC = set(CONCURRENTES) | {frozenset({a, b}) for a in FEB | {"acb"} for b in FEB if a != b}
COLS = ["liga", "temporada", "fase", "player_id", "nombre", "fecha_nacimiento", "edad", "nacionalidad", "equipo",
        "gp", "team_gp", "min"]


def tokens_nombre(nombre: str) -> frozenset:
    """Palabras normalizadas del nombre (sin acentos, sufijos ni partículas de una letra)."""
    if not isinstance(nombre, str) or not nombre.strip():
        return frozenset()
    n = nombre
    if "," in n:
        a, b = n.split(",", 1)
        n = f"{b} {a}"
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[.'’`´]", "", n)
    return frozenset(t for t in re.split(r"[^a-z]+", n) if len(t) > 1 and t not in SUFIJOS
                     and t not in {"de", "del", "la", "las", "los", "da", "dos", "van", "der", "von", "y"})


def _iso(v):
    from .nacionalidad import codigo
    return codigo(v)


def cargar_nodos(proc: Path = PROC, temporadas: list[str] | None = None) -> pd.DataFrame:
    """Un nodo por (liga, player_id) con sus atributos de todas las temporadas."""
    filas = []
    for d in sorted(proc.glob("20*-*")):
        if temporadas and d.name not in temporadas:
            continue
        for f in sorted((d / "ligas").glob("*.csv")):
            try:
                x = pd.read_csv(f, usecols=lambda c: c in COLS, dtype={"player_id": str})
            except ValueError:
                continue
            x = x[x["fase"] == "total"]
            filas.append(x)
    if not filas:
        return pd.DataFrame()
    t = pd.concat(filas, ignore_index=True)
    t["anio"] = t["temporada"].str[:4].astype(int)
    nac = pd.to_datetime(t["fecha_nacimiento"], errors="coerce")
    t["anio_nac"] = nac.dt.year.astype(float)
    sin = t["anio_nac"].isna() & t["edad"].notna()
    t.loc[sin, "anio_nac"] = t.loc[sin, "anio"] - np.floor(pd.to_numeric(t.loc[sin, "edad"], errors="coerce"))
    t["fecha_nac"] = nac.dt.strftime("%Y-%m-%d")
    t["iso"] = t["nacionalidad"].map(_iso)
    t["frac"] = pd.to_numeric(t["gp"], errors="coerce") / pd.to_numeric(t["team_gp"], errors="coerce")
    # nombre de las ligas con alfabeto propio: el id ya es "apellido-nombre" internacional (BSL, GBL)
    t["nombre_cmp"] = np.where(t["liga"].isin(["gbl", "bsl"]), t["player_id"].str.replace("-", " "), t["nombre"])

    def agg(g: pd.DataFrame) -> pd.Series:
        fn = g["fecha_nac"].dropna()
        an = g["anio_nac"].dropna()
        iso = g["iso"].dropna()
        return pd.Series({
            "nombre": g["nombre"].mode().iat[0] if g["nombre"].notna().any() else None,
            "tokens": tokens_nombre(g["nombre_cmp"].mode().iat[0]) if g["nombre_cmp"].notna().any() else frozenset(),
            "fecha_nac": fn.mode().iat[0] if len(fn) else None,
            "anio_nac": float(an.median()) if len(an) else np.nan,
            "iso": iso.mode().iat[0] if len(iso) else None,
            "temporadas": {s: float(fr) if fr == fr else 0.0 for s, fr in g.groupby("temporada")["frac"].sum().items()},
            "equipos": {s: set(v) for s, v in g.groupby("temporada")["equipo"].agg(lambda s: set(s.dropna())).items()},
            "min": float(pd.to_numeric(g["min"], errors="coerce").sum()),
        })

    nodos = t.groupby(["liga", "player_id"]).apply(agg, include_groups=False).reset_index()
    nodos["nodo"] = nodos["liga"] + ":" + nodos["player_id"]
    return nodos.set_index("nodo", drop=False)


def _club_tokens(equipos: dict) -> set:
    out = set()
    for v in equipos.values():
        for e in v:
            out |= {w for w in tokens_nombre(str(e)) if len(w) > 3}
    return out


_CLUB_GENERICO = {"basket", "basquet", "baloncesto", "club", "bàsquet", "basketball", "team", "cb", "real"}


def _txt(v) -> str | None:
    return v if isinstance(v, str) and v else None


def puntuar(a: pd.Series, b: pd.Series, unico: bool = False) -> tuple[float, str, str]:
    """(confianza, método, motivo de rechazo o '') de la pareja de nodos a, b."""
    a, b = a.copy(), b.copy()
    for nd in (a, b):
        nd["fecha_nac"], nd["iso"] = _txt(nd.get("fecha_nac")), _txt(nd.get("iso"))
        nd["anio_nac"] = float(nd["anio_nac"]) if nd.get("anio_nac") is not None and nd["anio_nac"] == nd["anio_nac"] else np.nan
    if a["liga"] in FEB and b["liga"] in FEB and a["player_id"] == b["player_id"]:
        return 1.0, "id_feb", ""
    ta, tb = a["tokens"], b["tokens"]
    if len(ta & tb) < 2 or not (ta <= tb or tb <= ta):
        return 0.0, "", "nombre distinto"
    met = []
    if ta == tb:
        s = 0.55
        met.append("nombre_igual")
    else:
        s = 0.45
        met.append("nombre_contenido")
    # calendario
    for temp, fa in a["temporadas"].items():
        fb = b["temporadas"].get(temp)
        if fb is None:
            continue
        if a["liga"] == b["liga"] and a["liga"] not in ID_INESTABLE:
            return 0.0, "+".join(met), "misma liga y temporada con otro id"
        if a["liga"] == b["liga"] or (frozenset({a["liga"], b["liga"]}) not in CONC and fa + fb > 1.1):
            return 0.0, "+".join(met), "calendario imposible"
    # nacimiento
    if a["fecha_nac"] and b["fecha_nac"]:
        if a["fecha_nac"] == b["fecha_nac"]:
            s += 0.40
            met.append("fecha_nac")
        else:      # dos fechas completas distintas = dos personas (p.ej. hermanos «P. SALO» y «A. SALO»)
            return 0.0, "+".join(met), "fecha de nacimiento distinta"
    elif not np.isnan(a["anio_nac"]) and not np.isnan(b["anio_nac"]):
        d = abs(a["anio_nac"] - b["anio_nac"])
        if d > 1.5:
            return 0.0, "+".join(met), "año de nacimiento distinto"
        s += 0.25
        met.append("anio_nac")
    # nacionalidad
    if a["iso"] and b["iso"]:
        if a["iso"] == b["iso"]:
            s += 0.10
            met.append("nacionalidad")
        else:
            s -= 0.25
            met.append("nacionalidad_distinta")
    if unico:
        s += 0.20
        met.append("nombre_unico")
    ya = {int(x[:4]) for x in a["temporadas"]}
    yb = {int(x[:4]) for x in b["temporadas"]}
    if min(abs(x - y) for x in ya for y in yb) <= 1:
        s += 0.05
        met.append("trayectoria_contigua")
    ca, cb = _club_tokens(a["equipos"]) - _CLUB_GENERICO, _club_tokens(b["equipos"]) - _CLUB_GENERICO
    if ca & cb:
        s += 0.05
        met.append("club_comun")
    return float(min(1.0, max(0.0, s))), "+".join(met), ""


def candidatos(nodos: pd.DataFrame) -> list[tuple[str, str]]:
    """Parejas que comparten >= 2 palabras del nombre (índice invertido por las dos palabras más raras)."""
    freq = defaultdict(int)
    for tk in nodos["tokens"]:
        for w in tk:
            freq[w] += 1
    idx = defaultdict(set)
    for n, tk in zip(nodos.index, nodos["tokens"]):
        for w in tk:
            idx[w].add(n)
    pares = set()
    for n, tk, liga in zip(nodos.index, nodos["tokens"], nodos["liga"]):
        if len(tk) < 2:
            continue
        raras = sorted(tk, key=lambda w: freq[w])[:2]
        for w in raras:
            for m in idx[w]:
                if m <= n:
                    continue
                tm = nodos.at[m, "tokens"]
                if len(tk & tm) >= 2 and (tk <= tm or tm <= tk):
                    pares.add((n, m))
    return sorted(pares)


class _UF:
    """Unión-búsqueda que guarda, por grupo, las ligas de sus miembros (para detectar conflictos)."""

    def __init__(self, items, liga_de):
        self.p = {i: i for i in items}
        self.ligas = {i: {liga_de[i]} for i in items}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            lo, hi = min(ra, rb), max(ra, rb)
            self.p[hi] = lo
            self.ligas[lo] |= self.ligas.pop(hi)


def resolver(nodos: pd.DataFrame, umbral_fusion: float = 0.80, umbral_revision: float = 0.50,
             pasadas: int = 2) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(crosswalk, revisión) a partir de la tabla de nodos."""
    pares = candidatos(nodos)
    # unicidad: el nombre exacto sólo aparece una vez en cada una de las dos ligas y el nodo tiene una sola pareja
    # posible en la otra liga
    por_liga_nombre = nodos.groupby(["liga", nodos["tokens"].map(lambda t: " ".join(sorted(t)))]).size()
    n_pareja = defaultdict(int)
    for a, b in pares:
        n_pareja[(a, nodos.at[b, "liga"])] += 1
        n_pareja[(b, nodos.at[a, "liga"])] += 1

    def es_unico(a, b):
        ka = " ".join(sorted(nodos.at[a, "tokens"]))
        kb = " ".join(sorted(nodos.at[b, "tokens"]))
        return (por_liga_nombre.get((nodos.at[a, "liga"], ka), 0) == 1 and
                por_liga_nombre.get((nodos.at[b, "liga"], kb), 0) == 1 and
                n_pareja[(a, nodos.at[b, "liga"])] == 1 and n_pareja[(b, nodos.at[a, "liga"])] == 1)

    uf = _UF(nodos.index, nodos["liga"].to_dict())
    enlace: dict[str, tuple[float, str]] = {}
    attrs = nodos[["fecha_nac", "anio_nac", "iso"]].copy()
    revision = []
    for pasada in range(pasadas):
        revision = []
        # atributos del grupo (segunda pasada): fecha, año y nacionalidad conocidos en cualquier miembro
        grupo_attr = {}
        if pasada:
            raiz = pd.Series({n: uf.find(n) for n in nodos.index})
            a2 = attrs.assign(_r=raiz)
            fn = a2.dropna(subset=["fecha_nac"]).groupby("_r")["fecha_nac"].agg(lambda s: s.mode().iat[0])
            an = a2.groupby("_r")["anio_nac"].median()
            iso = a2.dropna(subset=["iso"]).groupby("_r")["iso"].agg(lambda s: s.mode().iat[0])
            grupo_attr = {r: (fn.get(r), an.get(r, np.nan), iso.get(r)) for r in set(raiz)}
        for a, b in pares:
            ra, rb = uf.find(a), uf.find(b)
            if ra == rb:
                continue
            na, nb = nodos.loc[a].copy(), nodos.loc[b].copy()
            if pasada:
                for nd, r in ((na, ra), (nb, rb)):
                    fn, an, iso = grupo_attr.get(r, (None, np.nan, None))
                    nd["fecha_nac"] = _txt(nd["fecha_nac"]) or _txt(fn)
                    nd["anio_nac"] = nd["anio_nac"] if not np.isnan(nd["anio_nac"]) else an
                    nd["iso"] = _txt(nd["iso"]) or _txt(iso)
            conf, met, motivo = puntuar(na, nb, es_unico(a, b))
            if motivo or conf < umbral_revision:
                continue
            # conflicto: el grupo resultante tendría dos ids distintos de una liga de ids estables (salvo que la
            # fecha de nacimiento coincida: la FEB, por ejemplo, a veces da otro id de persona al mismo jugador)
            conflicto = conf >= umbral_fusion and bool((uf.ligas[ra] & uf.ligas[rb]) - ID_INESTABLE) \
                and "fecha_nac" not in met.split("+")
            if conf >= umbral_fusion and not conflicto:
                uf.union(a, b)
                for n in (a, b):
                    if n not in enlace or enlace[n][0] < conf:
                        enlace[n] = (conf, met)
            else:
                revision.append({"liga_a": nodos.at[a, "liga"], "id_a": nodos.at[a, "player_id"],
                                 "nombre_a": nodos.at[a, "nombre"], "nacimiento_a": _txt(na["fecha_nac"]) or
                                 (None if np.isnan(na["anio_nac"]) else int(na["anio_nac"])),
                                 "nacionalidad_a": na["iso"], "temporadas_a": ",".join(sorted(nodos.at[a, "temporadas"])),
                                 "liga_b": nodos.at[b, "liga"], "id_b": nodos.at[b, "player_id"],
                                 "nombre_b": nodos.at[b, "nombre"], "nacimiento_b": _txt(nb["fecha_nac"]) or
                                 (None if np.isnan(nb["anio_nac"]) else int(nb["anio_nac"])),
                                 "nacionalidad_b": nb["iso"], "temporadas_b": ",".join(sorted(nodos.at[b, "temporadas"])),
                                 "confianza": round(conf, 2), "metodo": met,
                                 "motivo": "uniría dos ids de la misma liga" if conflicto else "confianza bajo el umbral"})
    raiz = {n: uf.find(n) for n in nodos.index}
    orden = {r: i for i, r in enumerate(sorted(set(raiz.values())))}
    cw = pd.DataFrame({"fuente_liga": nodos["liga"], "fuente_id": nodos["player_id"],
                       "persona_id": [f"P{orden[raiz[n]]:06d}" for n in nodos.index],
                       "confianza": [round(enlace.get(n, (1.0, ""))[0], 2) for n in nodos.index],
                       "metodo": [enlace.get(n, (1.0, "propio"))[1] for n in nodos.index],
                       "nombre": nodos["nombre"], "fecha_nacimiento": nodos["fecha_nac"],
                       "anio_nacimiento": nodos["anio_nac"], "nacionalidad_iso": nodos["iso"],
                       "temporadas": nodos["temporadas"].map(lambda d: ",".join(sorted(d)))})
    rev = pd.DataFrame(revision)
    if not rev.empty:
        rev = rev.sort_values(["confianza", "liga_a", "nombre_a"], ascending=[False, True, True])
    return cw.reset_index(drop=True), rev


def ejecutar(proc: Path = PROC, config: Path = RAIZ / "config" / "sources.json") -> dict:
    cfg = json.loads(Path(config).read_text(encoding="utf-8")).get("identidad") or {}
    nodos = cargar_nodos(proc)
    cw, rev = resolver(nodos, float(cfg.get("umbral_fusion", 0.80)), float(cfg.get("umbral_revision", 0.50)))
    cw.to_csv(proc / "player_id_crosswalk.csv", index=False, encoding="utf-8")
    rev.to_csv(proc / "crosswalk_revision.csv", index=False, encoding="utf-8")
    multi = cw.groupby("persona_id")["fuente_liga"].nunique()
    feb = cw[cw["fuente_liga"].isin(FEB)]
    feb_otras = cw[cw["persona_id"].isin(feb["persona_id"]) & ~cw["fuente_liga"].isin(FEB)]
    return {"nodos": len(cw), "personas": int(cw["persona_id"].nunique()), "personas_varias_ligas": int((multi > 1).sum()),
            "nodos_feb": len(feb), "personas_feb_con_otra_liga": int(feb_otras["persona_id"].nunique()),
            "revision": len(rev),
            "revision_con_feb": int(((rev.get("liga_a", pd.Series(dtype=str)).isin(FEB)) |
                                     (rev.get("liga_b", pd.Series(dtype=str)).isin(FEB))).sum()) if len(rev) else 0,
            "metodos": cw["metodo"].value_counts().head(15).to_dict()}
