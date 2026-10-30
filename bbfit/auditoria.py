"""Auditoría de identidades del simulador: comprueba con los NOMBRES (referencia independiente de los ids) que

1. cada persona_id de la fase de roles es un solo jugador (todos sus registros con nombres compatibles);
2. las plantillas que se exportan al navegador son las reales: cada miembro está en la plantilla del club en los datos
   procesados de esa temporada y tiene nombre (ningún código «P000…» sin nombre).

    python -m bbfit auditar [--simulador <carpeta de exportar-simulador>]

Falla (código de salida 1) si alguna comprobación supera su umbral. Origen: el 30-10-2026 una caché de roles con la
numeración antigua de personas se mezcló con un crosswalk regenerado y las plantillas salieron con jugadores de otros
equipos; esta auditoría lo habría detenido.
"""
from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

from .config import DIR_MOD, RAIZ

UMBRAL_MEZCLA = 0.002          # personas con registros de nombres incompatibles
UMBRAL_EQUIVOCADO = 0.06       # miembros de plantilla que no están en la plantilla real del club. Residuo legítimo
                               # (≈ 4,8 % en la v3): la tabla de datos guarda un solo equipo por jugador en la G League
                               # y omite fases que sí están en los roles; una mezcla de identidades da ≈ 30 %
UMBRAL_SIN_NOMBRE = 0.0        # miembros sin nombre


_GRIEGO = dict(zip("αβγδεζηθικλμνξοπρσςτυφχψω", ["a", "v", "g", "d", "e", "z", "i", "th", "i", "k", "l", "m", "n", "x", "o",
                                                    "p", "r", "s", "s", "t", "i", "f", "ch", "ps", "o"]))
_GRIEGO.update({"ου": "ou", "μπ": "b", "ντ": "d", "γκ": "g", "αι": "e", "ει": "i", "οι": "i"})


def _latino(s: str) -> str:
    """Transliteración aproximada del griego (la GBL publica los nombres en su alfabeto)."""
    for k in sorted(_GRIEGO, key=len, reverse=True):
        s = s.replace(k, _GRIEGO[k])
    return s


def fichas(nombre) -> frozenset:
    """Palabras del nombre en minúsculas, sin tildes y en alfabeto latino («SIMMONS, KOBI» = «Kobi Simmons»)."""
    s = "".join(c for c in unicodedata.normalize("NFKD", str(nombre or "")) if not unicodedata.combining(c)).lower()
    if "," in s:
        a, b = s.split(",", 1)
        s = f"{b} {a}"
    return frozenset(w for w in re.findall(r"[^\W\d_]+", _latino(s)) if len(w) > 1)


def latino(nombre) -> bool:
    """Nombre en alfabeto latino (los de la GBL en griego no se comparan: la transliteración no es fiable)."""
    letras = [c for c in str(nombre or "") if c.isalpha()]
    return bool(letras) and sum("LATIN" in unicodedata.name(c, "") for c in letras) / len(letras) > 0.8


def _parecidas(a: str, b: str) -> bool:
    return a == b or (min(len(a), len(b)) >= 4 and SequenceMatcher(None, a, b).ratio() >= 0.8)


def compatibles(a: frozenset, b: frozenset) -> bool:
    """Mismo jugador si comparten una palabra larga (apellido; también aproximada: transliteraciones, «Jr.», tildes)
    o, en nombres cortos, todas sus palabras. Dos jugadores distintos casi nunca comparten apellido Y equipo."""
    if not a or not b:
        return False
    largas = [(x, y) for x in a for y in b if len(x) >= 4 and len(y) >= 4]
    return any(_parecidas(x, y) for x, y in largas) or (min(len(a), len(b)) == 1 and bool(a & b))


def auditar_roles(roles: pd.DataFrame) -> dict:
    """Personas cuyos registros no comparten nombre: identidades mezcladas."""
    r = roles.dropna(subset=["persona_id", "nombre"])
    malas = []
    for p, g in r.groupby("persona_id"):
        f = [fichas(n) for n in g["nombre"].unique() if latino(n)]
        if len(f) > 1 and not all(compatibles(f[0], x) or any(compatibles(y, x) for y in f[1:] if y is not x) for x in f[1:]):
            malas.append({"persona_id": p, "nombres": sorted(set(g["nombre"]))[:4],
                          "registros": g[["liga", "temporada", "team_id"]].astype(str).agg(":".join, axis=1).tolist()[:4]})
    n = int(r["persona_id"].nunique())
    return {"personas": n, "mezcladas": len(malas), "tasa": len(malas) / max(n, 1), "ejemplos": malas[:10]}


def _plantillas_reales(temps: list[str], ligas: list[str]) -> dict:
    out = {}
    for t in temps:
        for liga in ligas:
            p = RAIZ / "data" / "processed" / t / "ligas" / f"{liga}.csv"
            if not p.exists():
                continue
            x = pd.read_csv(p, dtype=str, usecols=lambda c: c in {"team_id", "nombre", "fase"}, low_memory=False)
            x = x[x["fase"] == "regular"] if "fase" in x else x
            for tm, n in zip(x["team_id"].astype(str), x["nombre"]):
                if not latino(n):                     # GBL: nombres en griego, no comparables
                    continue
                for t1 in tm.split(";"):              # traspasados a mitad de temporada: «OLY;IST»
                    out.setdefault((liga, t, t1), []).append(fichas(n))
    return out


def auditar_simulador(carpeta: Path) -> dict:
    """Plantillas exportadas frente a las reales de los datos procesados."""
    c = json.loads((carpeta / "clubes.json").read_text(encoding="utf-8"))
    j = json.loads((carpeta / "jugadores.json").read_text(encoding="utf-8"))
    C = pd.DataFrame(c["filas"], columns=c["columnas"])
    J = pd.DataFrame(j["filas"], columns=j["columnas"]).set_index("id")
    reales = _plantillas_reales(sorted(C["temporada"].unique()), sorted(C["liga"].unique()))
    tot = bien = mal = sin_nombre = sin_real = 0
    ej_mal, ej_sin = [], []
    for r in C.itertuples():
        R = reales.get((r.liga, r.temporada, str(r.team)))
        for rid, _pres, _lmc, persona in r.plantilla:
            tot += 1
            nombre = J.at[rid, "nombre"] if rid is not None and rid in J.index else None
            if not isinstance(nombre, str) or not nombre.strip():
                sin_nombre += 1
                if len(ej_sin) < 10:
                    ej_sin.append(f"{r.liga} {r.temporada} {r.nombre}: {persona}")
                continue
            if R is None or not latino(nombre):  # sin plantilla real (temporada sin empezar) o nombre en griego
                sin_real += 1
                continue
            if any(compatibles(fichas(nombre), q) for q in R):
                bien += 1
            else:
                mal += 1
                if len(ej_mal) < 15:
                    ej_mal.append(f"{r.liga} {r.temporada} {r.nombre}: {nombre} ({persona})")
    comp = max(tot - sin_real - sin_nombre, 1)
    return {"miembros": tot, "bien": bien, "equivocados": mal, "tasa_equivocados": mal / comp,
            "sin_nombre": sin_nombre, "tasa_sin_nombre": sin_nombre / max(tot, 1), "no_comparables": sin_real,
            "ejemplos_equivocados": ej_mal, "ejemplos_sin_nombre": ej_sin}


def main(simulador: str | None = None) -> dict:
    roles = pd.read_csv(DIR_MOD / "roles" / "player_role_season.csv.gz", dtype=str,
                        usecols=["liga", "temporada", "team_id", "persona_id", "nombre"])
    res = {"roles": auditar_roles(roles)}
    fallos = []
    if res["roles"]["tasa"] > UMBRAL_MEZCLA:
        fallos.append(f"identidades mezcladas en roles: {res['roles']['mezcladas']} personas")
    if simulador:
        res["simulador"] = s = auditar_simulador(Path(simulador))
        if s["tasa_equivocados"] > UMBRAL_EQUIVOCADO:
            fallos.append(f"plantillas con jugadores equivocados: {s['equivocados']} ({s['tasa_equivocados']:.1%})")
        if s["tasa_sin_nombre"] > UMBRAL_SIN_NOMBRE:
            fallos.append(f"miembros de plantilla sin nombre: {s['sin_nombre']}")
    res["fallos"] = fallos
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    if fallos:
        raise SystemExit("AUDITORÍA FALLIDA: " + "; ".join(fallos))
    return res
