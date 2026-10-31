"""Identidad: reconocer al mismo jugador en distintas ligas y temporadas.

Problema: cada fuente usa sus propios identificadores. Los de una misma liga sirven entre
temporadas (salvo la BBL, que cambia el id cada temporada), pero entre ligas no hay nada común.
Solución: emparejar por NOMBRE y descartar homónimos con dos pruebas.

1. Nombre normalizado: sin acentos, sin puntuación ni sufijos (Jr., II), y como conjunto de
   palabras, para que «LLULL, SERGIO» y «Sergio Llull» coincidan.
2. Año de nacimiento implícito: temporada − edad. Lo publican EuroLeague, EuroCup, NBA,
   G League y LNB. Dos registros con el mismo nombre y años de nacimiento separados más de
   un año son personas distintas (el Devin Booker del Olimpia Milano, nacido en 1991, no es
   el de Phoenix, nacido en 1996).
3. Calendario imposible: si en una misma temporada aparecen en dos ligas que no se juegan a la
   vez (por ejemplo NBA y LBA) y entre ambas suman más partidos de los que caben, son personas
   distintas. Las parejas que sí se juegan a la vez (EuroLeague/EuroCup con su liga nacional,
   NBA con G League) quedan permitidas.

Un registro sin edad (ACB, LBA, BBL) se une a una persona sólo si hay UNA única persona
compatible; si hay varias, queda aparte (se prefiere perder un puente a crear uno falso).
Resultado: columna `persona_id` y una lista de casos ambiguos para revisar.

Emparejamiento EXPLÍCITO con confianza (fecha de nacimiento, nacionalidad, trayectoria de clubes, ids FEB) y cola
de revisión manual: `crosswalk()` → bbmodel/crosswalk.py (data/processed/player_id_crosswalk.csv y
crosswalk_revision.csv). Las uniones de confianza baja NO se aplican automáticamente.
"""
from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd

SUFIJOS = {"jr", "sr", "ii", "iii", "iv"}
# ligas que se juegan a la vez con otras (un jugador puede estar en ambas en la misma temporada)
EUROPA_COPAS = {"euroleague", "eurocup", "bcl", "fec"}
NACIONALES = {"acb", "lba", "bbl", "lnb", "bsl", "gbl", "feb1", "feb2", "feb3", "bnxt", "vtb"}
CONCURRENTES = {frozenset({a, b}) for a in EUROPA_COPAS for b in NACIONALES} | {frozenset({"nba", "gleague"})}


def clave_nombre(nombre: str) -> str | None:
    """'LLULL, SERGIO' y 'Sergio Llull' -> 'llull sergio'."""
    if not isinstance(nombre, str) or not nombre.strip():
        return None
    n = nombre
    if "," in n:
        apellido, nom = n.split(",", 1)
        n = f"{nom} {apellido}"
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[.'’`]", "", n)
    tokens = [t for t in re.split(r"[^a-z]+", n) if t and t not in SUFIJOS]
    return " ".join(sorted(set(tokens))) if len(tokens) >= 2 else None


def _anio_nacimiento(g: pd.DataFrame) -> float:
    """Año de nacimiento estimado de un registro (mediana entre temporadas)."""
    fn = pd.to_datetime(g["fecha_nacimiento"], errors="coerce").dropna()
    if len(fn):
        return float(fn.dt.year.median())
    e = pd.to_numeric(g["edad"], errors="coerce")
    ok = e.notna()
    if ok.any():
        # edad al empezar la temporada ≈ año de inicio − año de nacimiento (± 1)
        return float(np.median(g.loc[ok, "anio"] - np.floor(e[ok])))
    return np.nan


def resolver(tabla: pd.DataFrame, tolerancia_anios: float = 1.5, holgura_calendario: float = 1.1) -> pd.DataFrame:
    """Añade `persona_id` a la tabla jugador-liga-temporada y devuelve (tabla, informe)."""
    t = tabla.copy()
    t["clave"] = t["nombre"].map(clave_nombre)
    # partidos máximos por liga-temporada (para la prueba de calendario)
    max_gp = t.groupby(["liga", "temporada"])["team_gp"].max()
    t["frac_gp"] = t["gp"] / t.set_index(["liga", "temporada"]).index.map(max_gp).to_numpy()

    # nodo = registro estable dentro de una liga: (liga, player_id). En la BBL, datos.py ya ha
    # sustituido el id por el nombre normalizado (la fuente cambia el id con cada equipo y temporada).
    t["nodo"] = t["liga"] + ":" + t["player_id"]
    nodos = (t.groupby("nodo")
               .apply(lambda g: pd.Series({"clave": g["clave"].iloc[0], "liga": g["liga"].iloc[0],
                                           "anio_nac": _anio_nacimiento(g),
                                           "temporadas": {s: f for s, f in zip(g["temporada"], g["frac_gp"])}}),
                      include_groups=False))

    persona = {}
    ambiguos = []
    siguiente = 0
    for clave, grupo in nodos.groupby("clave", dropna=False):
        if clave is None or (isinstance(clave, float) and np.isnan(clave)):
            for n in grupo.index:
                persona[n] = siguiente; siguiente += 1
            continue
        # primero los nodos con año de nacimiento (anclan a las personas), después el resto
        orden = grupo.assign(_sin=grupo["anio_nac"].isna()).sort_values(["_sin"]).index
        personas: list[dict] = []  # cada una: {"id", "anio", "temporadas": {temp: [(liga, frac)]}}
        for n in orden:
            fila = grupo.loc[n]
            compatibles = []
            for p in personas:
                if not np.isnan(fila["anio_nac"]) and not np.isnan(p["anio"]) and abs(fila["anio_nac"] - p["anio"]) > tolerancia_anios:
                    continue
                choque = False
                for temp, frac in fila["temporadas"].items():
                    for liga_p, frac_p in p["temporadas"].get(temp, []):
                        if liga_p == fila["liga"]:
                            choque = True  # mismo nombre, misma liga y temporada, otro id: otra persona
                        elif frozenset({liga_p, fila["liga"]}) not in CONCURRENTES and (frac or 0) + (frac_p or 0) > holgura_calendario:
                            choque = True
                if not choque:
                    compatibles.append(p)
            if len(compatibles) == 1:
                p = compatibles[0]
            elif len(compatibles) == 0 or not np.isnan(fila["anio_nac"]):
                if len(compatibles) > 1:  # con edad pero varias personas posibles: la de año más cercano
                    p = min(compatibles, key=lambda q: abs(q["anio"] - fila["anio_nac"]) if not np.isnan(q["anio"]) else 9)
                else:
                    p = {"id": siguiente, "anio": fila["anio_nac"], "temporadas": {}}
                    siguiente += 1
                    personas.append(p)
            else:  # sin edad y varias personas posibles: no se une a ninguna
                ambiguos.append({"nodo": n, "clave": clave, "candidatas": len(compatibles)})
                p = {"id": siguiente, "anio": np.nan, "temporadas": {}}
                siguiente += 1
                personas.append(p)
            persona[n] = p["id"]
            if np.isnan(p["anio"]) and not np.isnan(fila["anio_nac"]):
                p["anio"] = fila["anio_nac"]
            for temp, frac in fila["temporadas"].items():
                p["temporadas"].setdefault(temp, []).append((fila["liga"], frac))

    t["persona_id"] = t["nodo"].map(persona).astype(int)
    # el año de nacimiento es de la PERSONA: si una liga lo publica (EuroLeague), vale también para
    # sus filas en ligas que no lo publican (ACB). Mediana entre sus registros.
    t["anio_nac"] = t["nodo"].map(nodos["anio_nac"])
    t["anio_nac"] = t.groupby("persona_id")["anio_nac"].transform("median")
    return t.drop(columns=["frac_gp"]), pd.DataFrame(ambiguos)


def puentes(t: pd.DataFrame, min_minutos: float = 150) -> pd.DataFrame:
    """Cuenta jugadores puente por par de ligas: a la vez (misma temporada) o al cambiar de liga
    de una temporada a la siguiente. Sólo registros con `min_minutos` o más."""
    s = t[t["min"] >= min_minutos][["persona_id", "liga", "anio"]].drop_duplicates()
    filas = []
    a = s.merge(s, on="persona_id", suffixes=("_a", "_b"))
    mismo = a[(a.anio_a == a.anio_b) & (a.liga_a < a.liga_b)]
    for (la, lb), g in mismo.groupby(["liga_a", "liga_b"]):
        filas.append({"tipo": "misma temporada", "liga_a": la, "liga_b": lb, "n": g.persona_id.nunique()})
    sig = a[(a.anio_b == a.anio_a + 1) & (a.liga_a != a.liga_b)]
    for (la, lb), g in sig.groupby(["liga_a", "liga_b"]):
        filas.append({"tipo": "temporada siguiente", "liga_a": la, "liga_b": lb, "n": len(g)})
    return pd.DataFrame(filas)


def crosswalk(**kw):
    """Tabla de correspondencia con confianza y cola de revisión (ver bbmodel/crosswalk.py)."""
    from .crosswalk import ejecutar
    return ejecutar(**kw)


def unir_crosswalk(t: pd.DataFrame, ruta=None, umbral: float = 0.80) -> tuple[pd.DataFrame, dict]:
    """Une además las personas que el crosswalk explícito (bbmodel/crosswalk.py) enlaza AUTOMÁTICAMENTE.

    `resolver` une por nombre exacto (conjunto de palabras): no reconoce «ALEIX FONT RODRIGUEZ» (Primera FEB, nombre
    y dos apellidos) y «Aleix Font» (ACB). El crosswalk sí (nombre contenido + fecha de nacimiento + unicidad +
    trayectoria), con confianza 0-1. Aquí sólo se usan sus uniones automáticas (confianza ≥ `umbral`, por defecto el
    umbral de fusión 0,80; la cola de revisión NUNCA se aplica). Cada grupo del crosswalk funde los `persona_id` de
    `resolver` de sus nodos, salvo que la fusión deje a una persona dos veces en la misma liga y temporada (se
    descarta esa unión). El año de nacimiento del crosswalk (fecha completa de la FEB) rellena el de la persona.
    `t` es la salida de `resolver` (liga, player_id con «n:<nombre>» en la BBL, temporada, persona_id, anio_nac)."""
    from pathlib import Path
    ruta = Path(ruta) if ruta else Path(__file__).resolve().parent.parent / "data" / "processed" / "player_id_crosswalk.csv"
    info = {"crosswalk": str(ruta.name), "umbral": umbral, "uniones": 0, "descartadas_conflicto": 0}
    if not ruta.exists():
        info["crosswalk"] = None
        return t, info
    cw = pd.read_csv(ruta, dtype={"fuente_id": str})
    cw = cw[cw["confianza"] >= umbral]
    # nodo del modelo: (liga, player_id); en la BBL el id es «n:<nombre normalizado>»
    pid = cw["fuente_id"].astype(str)
    bbl = cw["fuente_liga"] == "bbl"
    k = cw.loc[bbl, "nombre"].map(clave_nombre)
    pid[bbl] = ("n:" + k.fillna("")).where(k.notna(), pid[bbl])
    cw = cw.assign(nodo=cw["fuente_liga"] + ":" + pid)
    t = t.copy()
    t["_nodo"] = t["liga"] + ":" + t["player_id"].astype(str)
    nodo_persona = t.drop_duplicates("_nodo").set_index("_nodo")["persona_id"]
    cw = cw[cw["nodo"].isin(nodo_persona.index)]
    cw = cw.assign(pid_res=cw["nodo"].map(nodo_persona))
    # unión-búsqueda sobre los persona_id de resolver, con control de choque (misma liga y temporada)
    padre = {p: p for p in t["persona_id"].unique()}
    huella = {p: set(map(tuple, g[["liga", "temporada"]].to_numpy())) for p, g in t.groupby("persona_id")}

    def raiz(x):
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    for _, g in cw.groupby("persona_id"):
        ids = list(dict.fromkeys(g["pid_res"].astype(int)))
        for b in ids[1:]:
            ra, rb = raiz(ids[0]), raiz(b)
            if ra == rb:
                continue
            if huella[ra] & huella[rb]:
                info["descartadas_conflicto"] += 1
                continue
            lo, hi = min(ra, rb), max(ra, rb)
            padre[hi] = lo
            huella[lo] |= huella.pop(hi)
            info["uniones"] += 1
    t["persona_id"] = t["persona_id"].map(lambda p: raiz(p)).astype(int)
    # año de nacimiento: el de la persona (mediana) y, si falta, el del crosswalk
    an_cw = cw.dropna(subset=["anio_nacimiento"]).set_index("nodo")["anio_nacimiento"]
    t["_an_cw"] = t["_nodo"].map(an_cw[~an_cw.index.duplicated()])
    t["anio_nac"] = t["anio_nac"].fillna(t["_an_cw"])
    t["anio_nac"] = t.groupby("persona_id")["anio_nac"].transform("median")
    info["personas"] = int(t["persona_id"].nunique())
    return t.drop(columns=["_nodo", "_an_cw"]), info
