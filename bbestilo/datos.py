"""Datos de estilo: de las traducciones normalizadas (A+B) a vectores de jugador y de club.

Fuente: el estudio de normalización de ligas (bbmodel). Cada jugador-liga-temporada tiene su
equivalente EuroLeague (`<m>_el`) por el algoritmo A y por el B; aquí se combinan como recomienda
el estudio (media en la escala transformada de cada métrica, `bbmodel.mesa_normalizacion.combinar`).
Si B no tiene al jugador (menos de 150 minutos, o la temporada en curso) se usa A.

Unidad de club: club-COMPETICIÓN-temporada (Baskonia EuroLeague 2025-26 y Baskonia ACB 2025-26
son dos puntos). Los minutos de cada jugador en cada club salen de las filas jugador-equipo de
bbstats (temporada regular); su perfil es el normalizado de su liga y temporada.

Agregación: media ponderada por minutos de los perfiles de los jugadores, es decir, el perfil medio
de los cinco que hay en pista. Es lineal en los minutos: añadir un fichaje o cambiar el reparto de
minutos mueve al club de forma exacta (ver encaje.py). Los únicos rasgos no lineales se calculan
también a partir de momentos ponderados:
  * uso_conc = E_w[usg²] / E_w[usg]² = 1 + CV² del uso: 1 = uso repartido; más = equipo «heliocéntrico».
    Para un jugador: (usg / usg medio de su club)², su peso en esa concentración.
  * cuota_interior / cuota_exterior: parte de los minutos jugada por interiores (4-5) / exteriores (1-2).
El ritmo NO está en el estudio: se añade como z del ritmo del equipo dentro de su liga y temporada.
"""
from __future__ import annotations

import glob
import json
import re
import unicodedata
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from bbmodel.datos import cargar_filas
from bbmodel.identidad import clave_nombre
from bbmodel.mesa_normalizacion import combinar
from bbmodel.metricas import transformar as transformar_metrica

from . import config as C

# Columnas «crudas» por jugador-equipo (escala EuroLeague) a partir de las que se calcula el vector
CRUDAS = ["ritmo_rel"] + C.METRICAS_ESTILO + ["es_int", "es_ext"]
_I = {c: i for i, c in enumerate(CRUDAS)}
LIGAS_ID_INESTABLE = {"lba", "lnb"}   # cambian de team_id cada temporada


# ----------------------------------------------------------------------------- carga
def _leer(directorio, temporadas) -> pd.DataFrame:
    frames = []
    for t in temporadas:
        for p in sorted(glob.glob(str(directorio / f"{t}.csv"))):
            frames.append(pd.read_csv(p, dtype={"player_id": str}, low_memory=False))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def cargar_normalizadas(temporadas: list[str]) -> pd.DataFrame:
    """Una fila por jugador-liga-temporada con el valor normalizado A+B de cada métrica usada."""
    metricas = C.METRICAS_ESTILO + list(C.NIVEL)
    a = _leer(C.DIR_A, temporadas)
    b = _leer(C.DIR_B, temporadas)
    clave = ["liga", "temporada", "player_id"]
    base = a[clave + ["persona_id", "nombre", "pos3", "anio_nac", "min"]].copy()
    tiene_b = pd.Series(False, index=a.index)
    if len(b):
        bb = b[clave + [f"{m}_el" for m in metricas]].rename(columns={f"{m}_el": f"{m}_B" for m in metricas})
        a = a.merge(bb, on=clave, how="left")
        tiene_b = a[[f"{m}_B" for m in metricas]].notna().any(axis=1)
    for m in metricas:
        va = a[f"{m}_el"].to_numpy(float)
        vb = a[f"{m}_B"].to_numpy(float) if f"{m}_B" in a else np.full(len(a), np.nan)
        ab = combinar(va, vb, m)
        base[m] = np.where(np.isfinite(vb) & np.isfinite(va), ab, va)
    base["fuente_norm"] = np.where(tiene_b.to_numpy(), "A+B", "A")
    return base


def cargar_filas_equipo(temporadas: list[str]) -> pd.DataFrame:
    """Filas jugador-equipo de temporada regular con minutos, equipo y ritmo."""
    f = cargar_filas("regular", temporadas)
    f = f[["liga", "temporada", "player_id", "nombre", "team_id", "equipo", "min", "team_pace"]].copy()
    # mismo id que bbmodel en la BBL (nombre normalizado, estable entre equipos)
    bbl = f["liga"] == "bbl"
    claves = f.loc[bbl, "nombre"].map(clave_nombre)
    f.loc[bbl, "player_id"] = np.where(claves.notna(), "n:" + claves.fillna(""), f.loc[bbl, "player_id"])
    f["min"] = pd.to_numeric(f["min"], errors="coerce").fillna(0.0)
    f["team_pace"] = pd.to_numeric(f["team_pace"], errors="coerce")
    f["team_id"] = f["team_id"].astype(str)
    # EuroLeague/EuroCup dan a los traspasados en una fila «BAS;TEL»: va al último equipo (el de su contexto)
    f["traspaso"] = f["team_id"].str.contains(";")
    f["team_id"] = f["team_id"].str.split(";").str[-1]
    f["equipo"] = f["equipo"].astype(str).str.split(";").str[-1].str.strip()
    return f[f["min"] > 0].reset_index(drop=True)


def ritmo_relativo(f: pd.DataFrame) -> pd.Series:
    """z del ritmo de cada equipo dentro de su liga y temporada (para cada fila)."""
    limpio = f[~f["traspaso"]]
    ritmo = limpio.groupby(["liga", "temporada", "team_id"])["team_pace"].median()
    z = ritmo.groupby(level=[0, 1]).transform(lambda x: (x - x.mean()) / (x.std(ddof=0) or np.nan))
    idx = pd.MultiIndex.from_frame(f[["liga", "temporada", "team_id"]])
    return pd.Series(z.reindex(idx).to_numpy(), index=f.index)


# ----------------------------------------------------------------------------- clubes
_GENERICAS = {"basket", "basketball", "pallacanestro", "club", "sporting", "the", "and", "les", "des", "sasp",
              "ssd", "asd", "spa", "srl", "team", "pallacanestro", "basketbol", "victoria", "libertas", "virtus"}


def _tokens(nombre: str) -> set[str]:
    n = unicodedata.normalize("NFKD", str(nombre)).encode("ascii", "ignore").decode().lower()
    tokens = {re.sub(r"basket(ball)?$", "", t) for t in re.split(r"[^a-z]+", n)}   # «napolibasket» -> «napoli»
    return {t for t in tokens if len(t) >= 3 and t not in _GENERICAS}


def enlazar_clubes(f: pd.DataFrame) -> pd.Series:
    """club_id estable entre temporadas. En las ligas con id estable es el team_id; en LBA y LNB
    (id nuevo cada temporada) se enlaza cada equipo con el de la temporada anterior por nombre
    (palabras en común, sin patrocinadores genéricos) y continuidad de plantilla (jugadores en común)."""
    club = f["team_id"].copy()
    for liga in LIGAS_ID_INESTABLE & set(f["liga"]):
        g = f[f["liga"] == liga]
        activos: dict[str, dict] = {}   # club_id -> {"tokens", "plantilla", "ultima"} (todos los vistos)
        mapa: dict[tuple[str, str], str] = {}
        n_nuevo = 0
        orden = sorted(g["temporada"].unique())
        for t in orden:
            eq = g[g["temporada"] == t].groupby("team_id")
            equipos = list(eq.groups)
            info = {e: {"tokens": set().union(*[_tokens(x) for x in eq.get_group(e)["equipo"].unique()]),
                        "plantilla": set(eq.get_group(e)["nombre"].map(clave_nombre).dropna())} for e in equipos}
            candidatos = [c for c in activos if activos[c]["ultima"] != t]
            usados: set[str] = set()
            if candidatos:
                S = np.zeros((len(equipos), len(candidatos)))
                for i, e in enumerate(equipos):
                    for j, c in enumerate(candidatos):
                        a, b = info[e], activos[c]
                        jac = len(a["tokens"] & b["tokens"]) / max(1, len(a["tokens"] | b["tokens"]))
                        sol = len(a["plantilla"] & b["plantilla"]) / max(1, min(len(a["plantilla"]), len(b["plantilla"])))
                        hueco = orden.index(t) - orden.index(b["ultima"])
                        # temporada anterior: basta nombre parecido o plantilla parecida;
                        # vuelta tras un descenso: hace falta nombre muy parecido
                        ok = (jac >= 0.2 or sol >= 0.3) if hueco <= 1 else jac >= 0.5
                        S[i, j] = jac + sol if ok else 0.0
                fi, co = linear_sum_assignment(-S)
                for i, j in zip(fi, co):
                    if S[i, j] > 0:
                        mapa[(t, equipos[i])] = candidatos[j]
                        usados.add(equipos[i])
            for e in equipos:
                if e not in usados:
                    n_nuevo += 1
                    mapa[(t, e)] = f"c{n_nuevo:03d}"
                cid = mapa[(t, e)]
                activos[cid] = {"tokens": info[e]["tokens"] | activos.get(cid, {}).get("tokens", set()),
                                "plantilla": info[e]["plantilla"], "ultima": t}
        s = g.index
        club.loc[s] = [mapa[(t, e)] for t, e in zip(g["temporada"], g["team_id"])]
    return club


# ----------------------------------------------------------------------------- vectores
def matriz_cruda(df: pd.DataFrame) -> np.ndarray:
    """Columnas CRUDAS de un DataFrame de filas jugador-equipo (NaN donde no hay dato)."""
    R = np.full((len(df), len(CRUDAS)), np.nan)
    R[:, _I["ritmo_rel"]] = df["ritmo_rel"].to_numpy(float)
    for m in C.METRICAS_ESTILO:
        R[:, _I[m]] = df[m].to_numpy(float)
    pos = df["pos3"].astype(object)
    conocida = pos.isin(["E", "A", "I"]).to_numpy()
    R[:, _I["es_int"]] = np.where(conocida, (pos == "I").to_numpy(float), np.nan)
    R[:, _I["es_ext"]] = np.where(conocida, (pos == "E").to_numpy(float), np.nan)
    return R


def _media_w(R: np.ndarray, W: np.ndarray) -> np.ndarray:
    """Media ponderada que ignora NaN. R: (n, c); W: (b, n) -> (b, c)."""
    ok = np.isfinite(R)
    num = W @ np.where(ok, R, 0.0)
    den = W @ ok.astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        return num / den


def agregar(R: np.ndarray, W: np.ndarray) -> np.ndarray:
    """Vector de estilo (sin transformar) de un club para cada fila de pesos W (b, n) -> (b, 13)."""
    W = np.atleast_2d(W)
    M = _media_w(R, W)
    u = R[:, _I["usg_pct"]]
    M2 = _media_w((u ** 2)[:, None], W)[:, 0]
    out = np.empty((W.shape[0], len(C.COLS)))
    for k, col in enumerate(C.COLS):
        if col == "uso_conc":
            with np.errstate(invalid="ignore", divide="ignore"):
                out[:, k] = M2 / M[:, _I["usg_pct"]] ** 2
        elif col == "cuota_interior":
            out[:, k] = M[:, _I["es_int"]]
        elif col == "cuota_exterior":
            out[:, k] = M[:, _I["es_ext"]]
        else:
            out[:, k] = M[:, _I[col]]
    return out


def vectores_jugador(R: np.ndarray, club: np.ndarray, usg_club: float) -> np.ndarray:
    """Vector de estilo (sin transformar) de cada jugador de una plantilla. `club` es el vector del
    club (rellena los huecos del jugador: «sin dato = como su equipo») y `usg_club` su uso medio."""
    out = np.empty((R.shape[0], len(C.COLS)))
    for k, col in enumerate(C.COLS):
        if col == "uso_conc":
            out[:, k] = (R[:, _I["usg_pct"]] / usg_club) ** 2
        elif col == "cuota_interior":
            out[:, k] = R[:, _I["es_int"]]
        elif col == "cuota_exterior":
            out[:, k] = R[:, _I["es_ext"]]
        else:
            out[:, k] = R[:, _I[col]]
    return np.where(np.isfinite(out), out, club[None, :])


def transformar(V: np.ndarray) -> np.ndarray:
    """Transformación por rasgo (estabiliza la varianza, como en bbmodel.metricas)."""
    V = np.asarray(V, float)
    out = np.empty_like(V)
    for k, r in enumerate(C.RASGOS):
        x = V[..., k]
        if r.transf == "id":
            out[..., k] = x
        else:
            out[..., k] = transformar_metrica(x, r.transf)
    return out


@dataclass
class Escala:
    media: np.ndarray
    sd: np.ndarray

    def aplicar(self, T: np.ndarray) -> np.ndarray:
        return (T - self.media) / self.sd

    def a_dict(self) -> dict:
        return {"media": self.media.tolist(), "sd": self.sd.tolist()}


def _escala(T: np.ndarray, w: np.ndarray | None = None) -> Escala:
    w = np.ones(len(T)) if w is None else w
    mu = np.nansum(T * w[:, None], 0) / np.sum(w[:, None] * np.isfinite(T), 0)
    var = np.nansum(w[:, None] * (T - mu) ** 2, 0) / np.sum(w[:, None] * np.isfinite(T), 0)
    return Escala(mu, np.sqrt(np.maximum(var, 1e-12)))


# ----------------------------------------------------------------------------- conjunto
@dataclass
class Conjunto:
    """Todo lo que necesitan las redes y el mapa."""
    clubes: pd.DataFrame                 # una fila por club-competición-temporada
    jugadores: pd.DataFrame              # una fila por jugador-equipo-temporada
    plantillas: dict = field(default_factory=dict)   # clave_club -> (R crudas, minutos, índices en jugadores)
    escala_club: Escala | None = None
    escala_jugador: Escala | None = None
    Xc: np.ndarray | None = None          # clubes, transformado y estandarizado con la escala de club
    Xj: np.ndarray | None = None          # jugadores, con la escala de jugador

    def x_club(self, V: np.ndarray) -> np.ndarray:
        return self.escala_club.aplicar(transformar(V))

    def x_jugador(self, V: np.ndarray) -> np.ndarray:
        return self.escala_jugador.aplicar(transformar(V))


def _nombres_club(f: pd.DataFrame) -> pd.Series:
    """Nombre más reciente de cada club (el más frecuente en su última temporada)."""
    ult = f.groupby("clave_club")["temporada"].transform("max")
    g = f[f["temporada"] == ult].groupby("clave_club")["equipo"].agg(lambda s: s.value_counts().index[0])
    return g


def construir(temporadas: list[str] | None = None) -> Conjunto:
    temporadas = temporadas or (C.TEMPORADAS_ENTRENO + C.TEMPORADAS_PROVISIONALES)
    norm = cargar_normalizadas(temporadas)
    f = cargar_filas_equipo(temporadas)
    f["ritmo_rel"] = ritmo_relativo(f)
    f["club_id"] = enlazar_clubes(f)
    f["clave_club"] = f["liga"] + ":" + f["club_id"]
    f = f.merge(norm.drop(columns=["nombre", "min"]), on=["liga", "temporada", "player_id"], how="left")
    f["nombre_club"] = f["clave_club"].map(_nombres_club(f))
    f = f.reset_index(drop=True)

    R_all = matriz_cruda(f)
    filas_club, V_club, V_jug = [], [], np.full((len(f), len(C.COLS)), np.nan)
    plantillas = {}
    nivel_cols = list(C.NIVEL)
    for (liga, temp, clave), g in f.groupby(["liga", "temporada", "clave_club"], sort=True):
        idx = g.index.to_numpy()
        R, w = R_all[idx], g["min"].to_numpy(float)
        v = agregar(R, w[None, :])[0]
        u_club = float(_media_w(R[:, [_I["usg_pct"]]], w[None, :])[0, 0])
        V_jug[idx] = vectores_jugador(R, v, u_club)
        nivel = _media_w(g[nivel_cols].to_numpy(float), w[None, :])[0]
        clave_t = f"{clave}:{temp}"
        plantillas[clave_t] = (R, w, idx)
        filas_club.append({"clave": clave_t, "clave_club": clave, "liga": liga, "temporada": temp,
                           "club_id": clave.split(":", 1)[1], "equipo": g["equipo"].value_counts().index[0],
                           "nombre_club": g["nombre_club"].iloc[0], "min_total": float(w.sum()),
                           "jugadores": int(len(g)), "usg_medio": u_club,
                           "cobertura_ab": float(w[(g["fuente_norm"] == "A+B").to_numpy()].sum() / w.sum()),
                           "provisional": temp in C.TEMPORADAS_PROVISIONALES,
                           **{f"n_{c}": x for c, x in zip(nivel_cols, nivel)}})
        V_club.append(v)
    clubes = pd.DataFrame(filas_club)
    V_club = np.array(V_club)
    for k, c in enumerate(C.COLS):
        clubes[c] = V_club[:, k]
    jug = f[["liga", "temporada", "clave_club", "club_id", "nombre_club", "equipo", "player_id", "persona_id",
             "nombre", "pos3", "anio_nac", "min", "fuente_norm"] + nivel_cols].copy()
    jug["clave"] = jug["clave_club"] + ":" + jug["temporada"]
    for k, c in enumerate(C.COLS):
        jug[c] = V_jug[:, k]
    jug["provisional"] = jug["temporada"].isin(C.TEMPORADAS_PROVISIONALES)

    # Escalas: clubes reales de las temporadas de entrenamiento; jugadores con minutos suficientes
    ent_c = ~clubes["provisional"].to_numpy()
    esc_c = _escala(transformar(V_club[ent_c]))
    ent_j = (~jug["provisional"] & (jug["min"] >= C.MIN_ESCALA_JUGADOR)).to_numpy()
    esc_j = _escala(transformar(V_jug[ent_j]), jug.loc[ent_j, "min"].to_numpy(float))
    cj = Conjunto(clubes, jug, plantillas, esc_c, esc_j)
    cj.Xc = np.nan_to_num(cj.x_club(V_club))
    cj.Xj = np.nan_to_num(cj.x_jugador(V_jug))
    _nivel(cj)
    return cj


def _nivel(cj: Conjunto) -> None:
    """Índice de nivel (capa aparte, no define estilos): media de los z con signo de las métricas de
    nivel disponibles. Clubes: z entre clubes reales; jugadores: z entre jugadores (ponderado por minutos)."""
    for df, w in ((cj.clubes, None), (cj.jugadores, "min")):
        cols = [f"n_{c}" if df is cj.clubes else c for c in C.NIVEL]
        base = df[~df["provisional"]]
        if w:
            base = base[base["min"] >= C.MIN_ESCALA_JUGADOR]
        Z = []
        for c, s in zip(cols, C.NIVEL.values()):
            x = base[c].astype(float)
            pw = base[w].astype(float) if w else pd.Series(1.0, index=base.index)
            ok = x.notna()
            mu = np.average(x[ok], weights=pw[ok])
            sd = np.sqrt(np.average((x[ok] - mu) ** 2, weights=pw[ok]))
            Z.append(s * (df[c].astype(float) - mu) / sd)
        df["nivel"] = pd.concat(Z, axis=1).mean(axis=1, skipna=True)


def remuestrear(cj: Conjunto, n: int, rng: np.random.Generator, claves: list[str] | None = None):
    """Plantillas remuestreadas: minutos × Gamma(k, 1/k) (bootstrap bayesiano suave del reparto de
    minutos). Devuelve (X estandarizado con la escala de club, índice del club de origen)."""
    claves = claves or list(cj.clubes["clave"])
    pos = {c: i for i, c in enumerate(cj.clubes["clave"])}
    X, origen = [], []
    for c in claves:
        R, w, _ = cj.plantillas[c]
        G = rng.gamma(C.K_GAMMA, 1.0 / C.K_GAMMA, size=(n, len(w)))
        X.append(np.nan_to_num(cj.x_club(agregar(R, G * w[None, :]))))
        origen.append(np.full(n, pos[c]))
    return np.vstack(X), np.concatenate(origen)


def club_alias() -> dict:
    """Clubes con nombre propio (config/clubes.json)."""
    try:
        d = json.loads(C.CLUBES.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return {k: v for k, v in d.items() if not k.startswith("_")}
