"""Nombre canónico de cada persona («Nombre Apellido», con los dos apellidos cuando la fuente los da).

Cada fuente escribe los nombres a su manera: «GIRARD III, JOSEPH» (EuroLeague), «J. GODSPOWER JOHNSON» (actas FEB),
«JUAN LÓPEZ YUSTE» (plantillas FEB), «Oj. Mayo» (CBA), «Tre'shaun Fletcher» (BNXT)… El artifact debe mostrar una sola
forma por persona. Reglas (decididas con el usuario el 03-11-2026):

1. «APELLIDO, NOMBRE» → «NOMBRE APELLIDO».
2. Entre las variantes de una persona (todos sus registros, en todas las ligas) se prefiere la completa (sin
   iniciales sueltas) y, entre las completas, la forma (orden de palabras sin tildes) con más minutos.
3. Dentro de esa forma: mejor la que no está toda en mayúsculas y la que lleva tildes; si todas están en mayúsculas,
   se pasa a «Nombre Apellido» (partículas de/del/van/der… en minúscula, Mc/O', números romanos, guiones) y se
   recuperan las tildes que alguna variante de la misma persona tenga en esa palabra.
4. Si sólo hay formas con inicial («J. BOCCA»), queda la inicial («J. Bocca»).

    python -m bbmodel nombres      → data/processed/nombres_canonicos.csv (fuente_liga, fuente_id, persona_id, nombre)
    nombres.canonico_nodo() / canonico_persona()  diccionarios para las exportaciones del artifact
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
PROC = RAIZ / "data" / "processed"
SALIDA = PROC / "nombres_canonicos.csv"

PARTICULAS = {"de", "del", "la", "las", "los", "da", "das", "do", "dos", "di", "du", "van", "von", "der", "den", "ten",
              "ter", "y", "e", "el", "le", "dei", "della"}
ROMANOS = {"ii", "iii", "iv", "v", "vi"}
SUFIJOS = {"jr": "Jr.", "sr": "Sr."}


def _sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def latino(s) -> bool:
    letras = [c for c in str(s or "") if c.isalpha()]
    return bool(letras) and all("LATIN" in unicodedata.name(c, "") for c in letras)


_GRIEGO = {"ου": "ou", "μπ": "b", "ντ": "d", "γκ": "g", "αι": "e", "ει": "i", "οι": "i", "α": "a", "β": "v", "γ": "g",
           "δ": "d", "ε": "e", "ζ": "z", "η": "i", "θ": "th", "ι": "i", "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x",
           "ο": "o", "π": "p", "ρ": "r", "σ": "s", "ς": "s", "τ": "t", "υ": "y", "φ": "f", "χ": "ch", "ψ": "ps", "ω": "o"}
_CIRILICO = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
             "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
             "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e",
             "ю": "yu", "я": "ya", "і": "i", "ї": "yi", "є": "ye", "ў": "u"}


def transliterar(nombre: str) -> str:
    """Griego y cirílico a alfabeto latino (aproximado; sólo cuando la persona no tiene ninguna variante latina)."""
    s = "".join(c for c in unicodedata.normalize("NFKD", str(nombre)) if not unicodedata.combining(c)).lower()
    for tabla in (_GRIEGO, _CIRILICO):
        for k in sorted(tabla, key=len, reverse=True):
            s = s.replace(k, tabla[k])
    return capitalizar(s)


def _solo_latino(nombre: str) -> str:
    """Quita las palabras que no están en alfabeto latino si quedan otras («B. Mclemore 麦克勒莫» → «B. Mclemore»)."""
    ws = [w for w in palabras(nombre) if latino(w) or not any(c.isalpha() for c in w)]
    if any(latino(w) and not es_inicial(w) for w in ws):
        return " ".join(ws)
    return nombre if latino(nombre) else transliterar(nombre)


def reordenar(nombre: str) -> str:
    """«GIRARD III, JOSEPH» → «JOSEPH GIRARD III»; espacios y comas sueltas normalizados."""
    n = re.sub(r"\s+", " ", str(nombre or "")).strip().strip(",").strip()
    n = _solo_latino(n)
    if n.count(",") == 1:
        a, b = (x.strip() for x in n.split(","))
        if a and b:
            n = f"{b} {a}"
    elif n.count(",") > 1:                    # «Kylian, Jimmy, Issa Patrick»: sin orden reconocible, sólo sin comas
        n = " ".join(x.strip() for x in n.split(",") if x.strip())
    return n


def palabras(nombre: str) -> list[str]:
    return [w for w in re.split(r"\s+", nombre) if w]


def es_inicial(w: str) -> bool:
    """«J.», «J», «Oj.», «D.» (una o dos letras con punto, o una sola letra)."""
    base = w.rstrip(".")
    return (w.endswith(".") and len(base) <= 2) or len(base) == 1


def completo(nombre: str) -> bool:
    ws = palabras(nombre)          # una inicial intermedia («Michael J. Smith») no impide que sea completo
    return len(ws) >= 2 and not es_inicial(ws[0]) and not es_inicial(ws[-1])


def clave_forma(nombre: str) -> tuple:
    return tuple(re.sub(r"[^a-z0-9]", "", _sin_tildes(w).lower()) for w in palabras(nombre))


def todo_mayusculas(nombre: str) -> bool:
    letras = [c for c in nombre if c.isalpha()]
    return bool(letras) and all(c.isupper() for c in letras)


def tiene_tildes(nombre: str) -> bool:
    return _sin_tildes(nombre) != nombre


def _capitalizar(w: str, primera: bool) -> str:
    lw = w.lower()
    if not primera and lw in PARTICULAS:
        return lw
    if lw.rstrip(".") in ROMANOS:
        return lw.rstrip(".").upper()
    if lw.rstrip(".") in SUFIJOS:
        return SUFIJOS[lw.rstrip(".")]
    if es_inicial(w):
        return w[0].upper() + w[1:].lower() if len(w.rstrip(".")) > 1 else w.upper()
    partes = re.split(r"([-'’])", lw)
    out = []
    for p in partes:
        if p in ("-", "'", "’") or not p:
            out.append(p)
        elif p.startswith("mc") and len(p) > 3:
            out.append("Mc" + p[2:].capitalize())
        else:
            out.append(p.capitalize())
    return "".join(out)


def capitalizar(nombre: str) -> str:
    return " ".join(_capitalizar(w, k == 0) for k, w in enumerate(palabras(nombre)))


def canonico(variantes: list[tuple[str, float]]) -> str | None:
    """Nombre canónico a partir de (nombre, minutos) de todos los registros de una persona."""
    vs = [(reordenar(n), float(m or 0)) for n, m in variantes if isinstance(n, str) and n.strip()]
    lat = [(n, m) for n, m in vs if latino(n)]
    if not lat:
        return transliterar(max(vs, key=lambda x: x[1])[0]) if vs else None
    # tildes conocidas por palabra (sin tildes y en minúscula → forma con tildes)
    tildes = {}
    for n, _ in lat:
        for w in palabras(n):
            if tiene_tildes(w):
                tildes.setdefault(_sin_tildes(w).lower(), w)
    cand = [(n, m) for n, m in lat if completo(n)] or lat
    peso = defaultdict(float)
    for n, m in cand:
        peso[clave_forma(n)] += m + 1e-3
    forma = max(peso, key=lambda k: (peso[k], len(k), k))
    grupo = [(n, m) for n, m in cand if clave_forma(n) == forma]
    n = max(grupo, key=lambda x: (not todo_mayusculas(x[0]), tiene_tildes(x[0]), x[1], x[0]))[0]
    if todo_mayusculas(n) or n == n.lower():
        n = capitalizar(n)
    elif n[:1].islower():                        # «alberto Vicente Sabariego»
        n = n[:1].upper() + n[1:]
    # tildes de otras variantes en palabras que aquí no las llevan
    ws = []
    for w in palabras(n):
        t = tildes.get(_sin_tildes(w).lower())
        if t and not tiene_tildes(w):
            w = _capitalizar(t, not ws) if (todo_mayusculas(t) or todo_mayusculas(w)) else t
        ws.append(w)
    n = " ".join(ws)
    # «Iii» / «Jr» al final
    return re.sub(r"\s+", " ", n).strip()


def variantes_por_nodo(proc: Path = PROC) -> pd.DataFrame:
    """(liga, player_id, nombre, minutos) de todos los registros procesados (fase total)."""
    filas = []
    for f in sorted(proc.glob("20*/ligas/*.csv")):
        d = pd.read_csv(f, dtype=str, usecols=lambda c: c in ("player_id", "nombre", "fase", "min"), low_memory=False)
        if "fase" in d:
            tot = d[d["fase"] == "total"]
            d = tot if len(tot) else d
        d = d.dropna(subset=["player_id", "nombre"])
        d["min"] = pd.to_numeric(d.get("min"), errors="coerce").fillna(0)
        g = d.groupby(["player_id", "nombre"], as_index=False)["min"].sum()
        g["liga"] = f.stem
        filas.append(g)
    return pd.concat(filas, ignore_index=True)


def _apellidos_compatibles(acta: str, web: str) -> bool:
    """El nombre de la plantilla web contiene los apellidos del acta («J. LÓPEZ YUSTE» ⊂ «JUAN LÓPEZ YUSTE»)."""
    a = [w for w in clave_forma(reordenar(acta)) if len(w) > 1]
    b = set(clave_forma(reordenar(web)))
    return bool(a) and all(w in b for w in a)


def variantes_web(proc: Path, v: pd.DataFrame) -> pd.DataFrame:
    """Nombres completos de las plantillas de la web de la FEB (scripts/feb_nombres_web.py) para los nodos FEB, sólo
    si contienen los apellidos que da el acta del mismo id."""
    f = proc / "feb_nombres_web.csv"
    if not f.exists():
        return v.iloc[0:0]
    w = pd.read_csv(f, dtype=str).dropna(subset=["player_id", "nombre"]).drop_duplicates(["player_id", "nombre"])
    feb = v[v["fuente_liga"].isin(["feb1", "feb2", "feb3"])][["fuente_liga", "fuente_id", "nombre"]]
    x = feb.merge(w.rename(columns={"player_id": "fuente_id", "nombre": "web"}), on="fuente_id")
    x = x[[_apellidos_compatibles(a, b) for a, b in zip(x["nombre"], x["web"])]]
    return x.drop_duplicates(["fuente_liga", "fuente_id", "web"]).assign(nombre=lambda d: d["web"], min=0.0)[
        ["fuente_liga", "fuente_id", "nombre", "min"]]


def construir(proc: Path = PROC) -> pd.DataFrame:
    cw = pd.read_csv(proc / "player_id_crosswalk.csv", dtype=str, usecols=["fuente_liga", "fuente_id", "persona_id"])
    v = variantes_por_nodo(proc).rename(columns={"liga": "fuente_liga", "player_id": "fuente_id"})
    v = pd.concat([v, variantes_web(proc, v)], ignore_index=True)
    v = v.merge(cw, on=["fuente_liga", "fuente_id"], how="left")
    v["persona_id"] = v["persona_id"].fillna(v["fuente_liga"] + ":" + v["fuente_id"])
    nom = {p: canonico(list(zip(g["nombre"], g["min"]))) for p, g in v.groupby("persona_id")}
    out = v.drop_duplicates(["fuente_liga", "fuente_id"])[["fuente_liga", "fuente_id", "persona_id"]].copy()
    out["nombre"] = out["persona_id"].map(nom)
    return out.sort_values(["persona_id", "fuente_liga", "fuente_id"]).reset_index(drop=True)


def ejecutar(proc: Path = PROC) -> dict:
    t = construir(proc)
    t.to_csv(SALIDA, index=False, encoding="utf-8")
    canonico_nodo.cache_clear()
    canonico_persona.cache_clear()
    return {"nodos": len(t), "personas": int(t["persona_id"].nunique()), "salida": str(SALIDA)}


@lru_cache(maxsize=1)
def _tabla() -> pd.DataFrame:
    if not SALIDA.exists():
        return pd.DataFrame(columns=["fuente_liga", "fuente_id", "persona_id", "nombre"])
    return pd.read_csv(SALIDA, dtype=str)


@lru_cache(maxsize=1)
def canonico_nodo() -> dict:
    """(liga, player_id) → nombre canónico."""
    t = _tabla()
    return dict(zip(zip(t["fuente_liga"], t["fuente_id"]), t["nombre"]))


@lru_cache(maxsize=1)
def canonico_persona() -> dict:
    """persona_id del crosswalk (P000123) → nombre canónico."""
    t = _tabla()
    return dict(zip(t["persona_id"], t["nombre"]))


def aplicar(df: pd.DataFrame, col_nombre: str = "nombre", col_liga: str | None = "liga",
            col_id: str | None = "player_id", col_persona: str | None = None, fuente: bool = True) -> pd.DataFrame:
    """Sustituye `col_nombre` por el canónico (por persona del crosswalk o por nodo liga:player_id); con `fuente`
    deja el original en `<col_nombre>_fuente`. Las filas sin canónico conservan su nombre. Se usa SÓLO al exportar
    (artifact): la identidad (crosswalk, ids «n:nombre» de la BBL) sigue usando el nombre de la fuente."""
    if col_nombre not in df:
        return df
    df = df.copy()
    nuevo = pd.Series(pd.NA, index=df.index, dtype=object)
    if col_persona and col_persona in df:
        nuevo = df[col_persona].astype(str).map(canonico_persona())
    if col_liga and col_id and col_liga in df and col_id in df:
        por_nodo = pd.Series([canonico_nodo().get((str(a), str(b))) for a, b in zip(df[col_liga], df[col_id])],
                             index=df.index)
        nuevo = nuevo.where(nuevo.notna(), por_nodo)
    if fuente:
        df[f"{col_nombre}_fuente"] = df[col_nombre]
    df[col_nombre] = nuevo.where(nuevo.notna(), df[col_nombre])
    return df
