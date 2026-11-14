"""F2 §6.3 · Resolución de entidades v5: persona única entre ligas y competiciones, con control de coherencia.

Parte del crosswalk vigente (`data/processed/player_id_crosswalk.csv`, nodos = (liga, id de la fuente)) sin
modificarlo, y produce una capa propia de la v5:

1. Evidencia por nodo:
   - año de nacimiento: el del crosswalk o, si falta, temporada − edad de las filas procesadas (±1 de tolerancia);
   - fechas en que jugó: caja por partido v5, `data/v5/limpios/caja_partido`.
2. Coherencia de cada persona con ≥ 2 nodos:
   - **nacimiento**: dos nodos con años separados más de 1,5;
   - **calendario**: dos nodos de ligas distintas que jugaron el mismo día en 2 o más fechas (no se puede jugar dos
     partidos a la vez en dos equipos);
   - nombre: similitud de Jaro-Winkler < 0,80 entre los nombres normalizados (sólo aviso).
3. Separación conservadora («un puente mal resuelto es peor que ningún puente»):
   - en una persona con conflicto de nacimiento o de calendario, se queda con el `persona_id` el subconjunto coherente
     con más minutos;
   - el resto de nodos se separan (persona nueva) y van a la tabla de revisión;
   - los nodos sin evidencia de nacimiento ni de calendario dentro de una persona en conflicto se separan también,
     como dudosos.
4. Enlaces perdidos:
   - mismo club en dos competiciones de la misma temporada, detectado porque los dos equipos comparten ≥ 3 personas;
   - dentro de cada par de clubes, jugadores que sólo aparecen en uno de los dos equipos;
   - se unen si coinciden apellido (Jaro-Winkler ≥ 0,95 entre tokens) e inicial del nombre, la pareja es única a ambos
     lados y no hay conflicto de nacimiento ni de calendario;
   - las parejas con similitud ≥ 0,85 que no cumplen todo eso van a revisión.

Salidas en data/v5/limpios/entidades/:
- `personas_v5.csv`: nodo → persona_v5, persona del crosswalk, cambio y motivo;
- `revision_identidades.csv`: tabla corregible por el usuario (columna `decision_usuario`: «aceptar», «rechazar» o
  vacío);
- `resumen.json`.

Si existe `revision_identidades.csv` con decisiones, se respetan al regenerar.
"""
from __future__ import annotations

import json
import re
import unicodedata

import numpy as np
import pandas as pd
from rapidfuzz.distance import JaroWinkler

from bbnorm5 import config as C

DIR = C.DIR_DATOS / "limpios" / "entidades"


# --------------------------------------------------------------------------------------------------- nombres
def normalizar(nombre: str) -> str:
    """«ROGKAVOPOULOS, NIKOLAOS» → «nikolaos rogkavopoulos»; sin acentos, sin puntuación."""
    s = str(nombre or "")
    if "," in s:
        a, b = s.split(",", 1)
        s = f"{b} {a}"
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def apellido_inicial(nombre_norm: str) -> tuple[list[str], str]:
    t = nombre_norm.split()
    if not t:
        return [], ""
    return t[1:] if len(t) > 1 else t, t[0][:1]


def similitud(a: str, b: str) -> float:
    return float(JaroWinkler.similarity(a, b))


def mismo_apellido_inicial(a: str, b: str) -> bool:
    ap_a, in_a = apellido_inicial(a)
    ap_b, in_b = apellido_inicial(b)
    if not ap_a or not ap_b or in_a != in_b:
        return False
    return max(similitud(x, y) for x in ap_a for y in ap_b if len(x) > 2 and len(y) > 2) >= 0.95 \
        if any(len(x) > 2 for x in ap_a) and any(len(y) > 2 for y in ap_b) else False


# --------------------------------------------------------------------------------------------------- evidencia
def filas_procesadas(temporadas: list[str]) -> pd.DataFrame:
    """Una fila por (liga, temporada, team_id, player_id) con minutos, edad y fecha de nacimiento (temporada regular y
    playoffs). Los traspasados de la EuroLeague y la EuroCup («A;B») se reparten en sus equipos."""
    fr = []
    for t in temporadas:
        for f in sorted((C.RAIZ / "data" / "processed" / t / "ligas").glob("*.csv")):
            d = pd.read_csv(f, usecols=lambda c: c in {"liga", "temporada", "fase", "team_id", "player_id", "nombre",
                                                         "min", "edad", "fecha_nacimiento"},
                            dtype={"team_id": str, "player_id": str}, low_memory=False)
            d = d[d["fase"].isin(["regular", "playoffs"])]
            fr.append(d)
    d = pd.concat(fr, ignore_index=True)
    d["team_id"] = d["team_id"].fillna("").str.split(";")
    d = d.explode("team_id")
    d["min"] = pd.to_numeric(d["min"], errors="coerce").fillna(0)
    d["anio"] = d["temporada"].str[:4].astype(int)
    return d


def evidencia_nacimiento(cw: pd.DataFrame, filas: pd.DataFrame) -> pd.Series:
    """Año de nacimiento por nodo: crosswalk o, si falta, mediana de (año de inicio de temporada − edad) o la fecha
    de nacimiento de las filas procesadas."""
    a = pd.to_numeric(cw["anio_nacimiento"], errors="coerce")
    a.index = list(zip(cw["fuente_liga"], cw["fuente_id"]))
    f = filas.copy()
    f["fn"] = pd.to_numeric(f["fecha_nacimiento"].astype(str).str[:4], errors="coerce")
    f["est"] = f["fn"].fillna(f["anio"] - pd.to_numeric(f["edad"], errors="coerce"))
    est = f.dropna(subset=["est"]).groupby(["liga", "player_id"])["est"].median()
    est.index = list(est.index)
    return a.fillna(est.reindex(a.index))


def nacimiento_es_estimado(cw: pd.DataFrame) -> set:
    """Nodos cuyo año de nacimiento no viene del crosswalk (se estima con temporada − edad: ±1 año de error)."""
    a = pd.to_numeric(cw["anio_nacimiento"], errors="coerce")
    return {(l, i) for l, i, v in zip(cw["fuente_liga"], cw["fuente_id"], a) if not np.isfinite(v)}


# ligas que se juegan a la vez con jugadores compartidos de forma legítima (contratos dobles, vinculaciones FEB):
# en ellas coincidir en fecha no prueba nada
CONCURRENTES = [{"nba", "gleague"}, {"feb1", "feb2", "feb3"}]


def concurrentes(la: str, lb: str) -> bool:
    return any(la in g and lb in g for g in CONCURRENTES)


def fechas_jugadas(temporadas: list[str]) -> pd.DataFrame:
    fr = []
    base = C.DIR_DATOS / "limpios" / "caja_partido"
    for t in temporadas:
        for f in sorted((base / t).glob("*.parquet")):
            d = pd.read_parquet(f)
            d = d[d["jugo"] & d["player_id"].notna()]
            # la prueba de calendario sólo usa fechas fiables: no la de modificación del fichero de FIBA LiveStats
            # (aproximada, ±1 día o más: provocaba coincidencias falsas con los partidos europeos)
            if "fecha_origen" in d:
                d = d[d["fecha_origen"].isin(["boxscore", "calendario"])]
            fr.append(d[["liga", "player_id", "fecha"]])
    d = pd.concat(fr, ignore_index=True) if fr else pd.DataFrame(columns=["liga", "player_id", "fecha"])
    d = d[d["fecha"].astype(str).str.match(r"\d{4}-\d{2}-\d{2}")]
    return d[["liga", "player_id", "fecha"]].drop_duplicates()


# --------------------------------------------------------------------------------------------------- coherencia
def conflictos(cw: pd.DataFrame, nac: pd.Series, fechas: pd.DataFrame, minutos: pd.Series,
               estimado: set | None = None) -> pd.DataFrame:
    """Para cada persona con ≥ 2 nodos: pares de nodos en conflicto (nacimiento, calendario) y aviso de nombre."""
    nodos = cw.assign(nodo=list(zip(cw["fuente_liga"], cw["fuente_id"])))
    grupos = nodos.groupby("persona_id")["nodo"].apply(list)
    grupos = grupos[grupos.str.len() >= 2]
    f = fechas.assign(nodo=list(zip(fechas["liga"], fechas["player_id"])))
    fechas_de = f.groupby("nodo")["fecha"].apply(set).to_dict()
    nombre_de = dict(zip(nodos["nodo"], nodos["nombre"].map(normalizar)))
    filas = []
    for pid, ns in grupos.items():
        for i in range(len(ns)):
            for j in range(i + 1, len(ns)):
                a, b = ns[i], ns[j]
                ya, yb = nac.get(a, np.nan), nac.get(b, np.nan)
                tol = 2.0 if estimado and (a in estimado or b in estimado) else 1.5
                mismo_id_federativo = a[0].startswith("feb") and b[0].startswith("feb") and a[1] == b[1]
                c_nac = bool(np.isfinite(ya) and np.isfinite(yb) and abs(ya - yb) > tol) and not mismo_id_federativo
                comunes = len(fechas_de.get(a, set()) & fechas_de.get(b, set())) \
                    if a[0] != b[0] and not concurrentes(a[0], b[0]) and not mismo_id_federativo else 0
                sim = similitud(nombre_de.get(a, ""), nombre_de.get(b, ""))
                if c_nac or comunes >= 2 or sim < 0.80:
                    filas.append({"persona_id": pid, "nodo_a": f"{a[0]}:{a[1]}", "nodo_b": f"{b[0]}:{b[1]}",
                                  "nombre_a": nombre_de.get(a), "nombre_b": nombre_de.get(b), "nac_a": ya, "nac_b": yb,
                                  "conflicto_nacimiento": c_nac, "fechas_comunes": comunes,
                                  "conflicto_calendario": comunes >= 2, "similitud_nombre": round(sim, 3)})
    return pd.DataFrame(filas)


def separar(cw: pd.DataFrame, conf: pd.DataFrame, nac: pd.Series, minutos: pd.Series) -> dict:
    """Persona con conflicto fuerte → núcleo coherente con más minutos conserva el id; el resto, persona nueva."""
    fuertes = conf[conf["conflicto_nacimiento"] | conf["conflicto_calendario"]]
    nuevo = {}
    for pid, g in fuertes.groupby("persona_id"):
        ns = cw.loc[cw["persona_id"] == pid, ["fuente_liga", "fuente_id"]].apply(tuple, axis=1).tolist()
        malos = {(x["nodo_a"], x["nodo_b"]) for _, x in g.iterrows()}
        clave = lambda n: f"{n[0]}:{n[1]}"   # noqa: E731

        def compatibles(a, b):
            return (clave(a), clave(b)) not in malos and (clave(b), clave(a)) not in malos
        # nodos con evidencia (año o fechas en conflicto) y sin ella
        con_ev = [n for n in ns if np.isfinite(nac.get(n, np.nan)) or any(clave(n) in p for p in malos)]
        # núcleos: agrupación voraz de los nodos con evidencia, por minutos descendentes
        nucleos: list[list] = []
        for n in sorted(con_ev, key=lambda n: -minutos.get(n, 0)):
            for nu in nucleos:
                if all(compatibles(n, m) for m in nu):
                    nu.append(n)
                    break
            else:
                nucleos.append([n])
        nucleos.sort(key=lambda nu: -sum(minutos.get(n, 0) for n in nu))
        principal = set(nucleos[0])
        for k, nu in enumerate(nucleos[1:], start=1):
            for n in nu:
                nuevo[n] = (f"{pid}-s{k}", "separado: conflicto de nacimiento o de calendario")
        for n in ns:
            if n not in principal and n not in nuevo:
                nuevo[n] = (f"{pid}-d{ns.index(n)}", "separado: sin evidencia en una persona en conflicto (dudoso)")
    return nuevo


# --------------------------------------------------------------------------------------------------- enlaces perdidos
def pares_de_clubes(filas: pd.DataFrame, persona: dict, minimo: int = 3) -> pd.DataFrame:
    """Equipos de competiciones distintas, misma temporada, que comparten ≥ `minimo` personas: el mismo club."""
    f = filas.assign(persona=[persona.get((l, p)) for l, p in zip(filas["liga"], filas["player_id"])]).dropna(subset=["persona"])
    eq = f.groupby(["temporada", "liga", "team_id"])["persona"].apply(set).reset_index()
    out = []
    for t, g in eq.groupby("temporada"):
        g = g.reset_index(drop=True)
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                if g.at[i, "liga"] == g.at[j, "liga"]:
                    continue
                n = len(g.at[i, "persona"] & g.at[j, "persona"])
                if n >= minimo:
                    out.append({"temporada": t, "liga_a": g.at[i, "liga"], "team_a": g.at[i, "team_id"],
                                "liga_b": g.at[j, "liga"], "team_b": g.at[j, "team_id"], "compartidos": n})
    return pd.DataFrame(out)


def enlaces_perdidos(filas: pd.DataFrame, persona: dict, nac: pd.Series, clubes: pd.DataFrame,
                     fechas_de: dict) -> pd.DataFrame:
    f = filas.assign(persona=[persona.get((l, p)) for l, p in zip(filas["liga"], filas["player_id"])])
    f = f.dropna(subset=["persona"]).drop_duplicates(["temporada", "liga", "team_id", "player_id"])
    f["nnorm"] = f["nombre"].map(normalizar)
    por_eq = {k: g for k, g in f.groupby(["temporada", "liga", "team_id"])}
    cand = []
    for r in clubes.itertuples(index=False):
        A = por_eq.get((r.temporada, r.liga_a, r.team_a))
        B = por_eq.get((r.temporada, r.liga_b, r.team_b))
        if A is None or B is None:
            continue
        solo_a = A[~A["persona"].isin(set(B["persona"]))]
        solo_b = B[~B["persona"].isin(set(A["persona"]))]
        for x in solo_a.itertuples(index=False):
            for y in solo_b.itertuples(index=False):
                sim = similitud(x.nnorm, y.nnorm)
                api = mismo_apellido_inicial(x.nnorm, y.nnorm)
                if sim < 0.85 and not api:
                    continue
                na, nb = nac.get((x.liga, x.player_id), np.nan), nac.get((y.liga, y.player_id), np.nan)
                c_nac = bool(np.isfinite(na) and np.isfinite(nb) and abs(na - nb) > 2.0)
                comunes = 0 if concurrentes(x.liga, y.liga) else \
                    len(fechas_de.get((x.liga, x.player_id), set()) & fechas_de.get((y.liga, y.player_id), set()))
                cand.append({"temporada": r.temporada, "nodo_a": f"{x.liga}:{x.player_id}", "nodo_b": f"{y.liga}:{y.player_id}",
                             "persona_a": x.persona, "persona_b": y.persona, "nombre_a": x.nombre, "nombre_b": y.nombre,
                             "club": f"{r.liga_a}:{r.team_a} = {r.liga_b}:{r.team_b}", "similitud": round(sim, 3),
                             "apellido_inicial": api, "conflicto_nacimiento": c_nac, "fechas_comunes": comunes})
    c = pd.DataFrame(cand)
    if c.empty:
        return c
    # unicidad a ambos lados dentro del par de clubes
    c["n_a"] = c.groupby(["temporada", "club", "nodo_a"])["nodo_b"].transform("count")
    c["n_b"] = c.groupby(["temporada", "club", "nodo_b"])["nodo_a"].transform("count")
    # mejor pareja a ambos lados (por similitud)
    c["mejor_a"] = c["similitud"] == c.groupby(["temporada", "club", "nodo_a"])["similitud"].transform("max")
    c["mejor_b"] = c["similitud"] == c.groupby(["temporada", "club", "nodo_b"])["similitud"].transform("max")
    sin_conflicto = ~c["conflicto_nacimiento"] & (c["fechas_comunes"] < 2)
    c["automatico"] = sin_conflicto & (
        (c["apellido_inicial"] & (c["n_a"] == 1) & (c["n_b"] == 1)) |
        ((c["similitud"] >= 0.97) & c["mejor_a"] & c["mejor_b"]))
    return c


# --------------------------------------------------------------------------------------------------- orquestación
def resolver(temporadas: list[str]) -> dict:
    DIR.mkdir(parents=True, exist_ok=True)
    cw = pd.read_csv(C.RAIZ / "data" / "processed" / "player_id_crosswalk.csv", dtype=str)
    filas = filas_procesadas(temporadas)
    minutos = filas.groupby(["liga", "player_id"])["min"].sum()
    minutos.index = list(minutos.index)
    nac = evidencia_nacimiento(cw, filas)
    fechas = fechas_jugadas(temporadas)
    fechas_de = fechas.assign(n=list(zip(fechas["liga"], fechas["player_id"]))).groupby("n")["fecha"].apply(set).to_dict()
    conf = conflictos(cw, nac, fechas, minutos, nacimiento_es_estimado(cw))
    sep = separar(cw, conf, nac, minutos)
    persona = {(l, i): p for l, i, p in zip(cw["fuente_liga"], cw["fuente_id"], cw["persona_id"])}
    persona_sep = {n: sep.get(n, (p, ""))[0] for n, p in persona.items()}
    clubes = pares_de_clubes(filas, persona_sep)
    perd = enlaces_perdidos(filas, persona_sep, nac, clubes, fechas_de)
    # decisiones del usuario (si existen) prevalecen
    rev_f = DIR / "revision_identidades.csv"
    decis = {}
    if rev_f.exists():
        r0 = pd.read_csv(rev_f, dtype=str)
        if "decision_usuario" in r0:
            decis = {(a, b): d for a, b, d in zip(r0["nodo_a"], r0["nodo_b"], r0["decision_usuario"]) if isinstance(d, str) and d}
    # uniones automáticas (y las aceptadas por el usuario): fusión de personas con unión-búsqueda
    padre: dict = {}

    def raiz(x):
        while padre.get(x, x) != x:
            x = padre[x]
        return x
    unidas = []
    if len(perd):
        for r in perd.itertuples(index=False):
            d = decis.get((r.nodo_a, r.nodo_b), "")
            if d == "rechazar" or (not r.automatico and d != "aceptar"):
                continue
            ra, rb = raiz(r.persona_a), raiz(r.persona_b)
            if ra != rb:
                padre[max(ra, rb)] = min(ra, rb)
                unidas.append((r.nodo_a, r.nodo_b))
    out = pd.DataFrame({"fuente_liga": cw["fuente_liga"], "fuente_id": cw["fuente_id"], "persona_crosswalk": cw["persona_id"],
                        "nombre": cw["nombre"]})
    out["persona_v5"] = [raiz(persona_sep[(l, i)]) for l, i in zip(out["fuente_liga"], out["fuente_id"])]
    out["motivo"] = [sep.get((l, i), (None, ""))[1] for l, i in zip(out["fuente_liga"], out["fuente_id"])]
    unidas_nodos = {n for par in unidas for n in par}
    en_union = np.array([f"{l}:{i}" in unidas_nodos for l, i in zip(out["fuente_liga"], out["fuente_id"])])
    out.loc[en_union & (out["motivo"] == "").to_numpy(), "motivo"] = "unido: mismo club en dos competiciones, apellido e inicial"
    out["cambio"] = out["persona_v5"] != out["persona_crosswalk"]
    out.to_csv(DIR / "personas_v5.csv", index=False)
    # tabla de revisión: separaciones, dudosos y candidatas no automáticas
    rev = []
    for r in conf.itertuples(index=False):
        rev.append({"tipo": "conflicto", "nodo_a": r.nodo_a, "nodo_b": r.nodo_b, "nombre_a": r.nombre_a, "nombre_b": r.nombre_b,
                    "detalle": f"nac {r.nac_a}/{r.nac_b} · fechas comunes {r.fechas_comunes} · sim {r.similitud_nombre}",
                    "accion_v5": "separado" if (r.conflicto_nacimiento or r.conflicto_calendario) else "aviso de nombre",
                    "decision_usuario": decis.get((r.nodo_a, r.nodo_b), "")})
    if len(perd):
        for r in perd.itertuples(index=False):
            rev.append({"tipo": "enlace_perdido", "nodo_a": r.nodo_a, "nodo_b": r.nodo_b, "nombre_a": r.nombre_a,
                        "nombre_b": r.nombre_b, "detalle": f"{r.temporada} · {r.club} · sim {r.similitud} · "
                        f"apellido+inicial {r.apellido_inicial} · nac {r.conflicto_nacimiento} · fechas {r.fechas_comunes}",
                        "accion_v5": "unido" if r.automatico else (
                            "unido (aceptado por el usuario)" if decis.get((r.nodo_a, r.nodo_b)) == "aceptar" else
                            "no unido (rechazado por el usuario)" if decis.get((r.nodo_a, r.nodo_b)) == "rechazar" else
                            "pendiente (no unido)"),
                        "decision_usuario": decis.get((r.nodo_a, r.nodo_b), "")})
    pd.DataFrame(rev).to_csv(rev_f, index=False)
    clubes.to_csv(DIR / "pares_de_clubes.csv", index=False)
    res = {"nodos": int(len(cw)), "personas_crosswalk": int(cw["persona_id"].nunique()),
           "personas_v5": int(out["persona_v5"].nunique()), "personas_con_conflicto_fuerte": int(len({p for p in conf.loc[conf["conflicto_nacimiento"] | conf["conflicto_calendario"], "persona_id"]})),
           "nodos_separados": int(len(sep)), "avisos_nombre": int((~conf["conflicto_nacimiento"] & ~conf["conflicto_calendario"]).sum()) if len(conf) else 0,
           "enlaces_perdidos_candidatos": int(len(perd)), "enlaces_unidos": int(len(unidas)),
           "pares_de_clubes": int(len(clubes)), "nodos_con_nacimiento": float(np.isfinite(nac.to_numpy(float)).mean())}
    C.escribir_json({**res, "meta": C.metadatos({"fase": "F2", "salida": "f2"},
                                                 [C.RAIZ / "data" / "processed" / "player_id_crosswalk.csv"])}, DIR / "resumen.json")
    return res
