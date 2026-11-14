"""v5.1 F6 · Proceso paralelo de la temporada en curso (2026-27) con los modelos congelados.

Lo que la v3.2 hace con el botón «Actualizar 2026-27» (CVAE congelada + v2 al día), aquí para la v5 y la combinada:

1. **Caja por partido** de la temporada (F2 de la v5) desde los brutos (opcional: en producción, con los partidos nuevos).
2. **Zonas y % asistidas** por partido de la temporada (F9 bis), en un fichero propio.
3. **Personas:** las conocidas por su id de fuente; las nuevas, por su persona del crosswalk si ya existe en la v5; si
   no, una persona nueva («N…»).
4. **Medida (F3) congelada:** media del rol, dispersión y σ de cada liga, los de la temporada anterior.
5. **Carrera (F4) congelada:** el filtro de Kalman con θ y β guardados (`carrera/modelos_final.pkl`) sobre toda la
   serie, de la que se toma la temporada en curso.
6. **Equivalente EuroLeague 2025-26 y combinada:** como la F1 de la v5.1 (mismos pesos y factores de unidad). λ de la
   temporada en curso = λ de la anterior, con la varianza de la innovación de un año añadida (la NUTS del paso 2 no
   tiene aún la temporada en curso).

Nada de la v3.2 se toca: la v3.2 de la temporada en curso es la que deja el botón. Salidas en
`data/v5_1/incremental/<temporada>/`.
"""
from __future__ import annotations

import json
import pickle

import numpy as np
import pandas as pd

from bbnorm5 import config as C
from bbnorm5.carrera import datos as CD
from bbnorm5.carrera import modelo as MOD
from bbnorm5.medida import datos as DM
from bbnorm5.salidas import formato_v32 as F

COMBINADA = C.DIR_DATOS.parent / "v5_1" / "salidas" / "combinada"


def dir_salida(t: str):
    d = C.DIR_DATOS.parent / "v5_1" / "incremental" / t
    d.mkdir(parents=True, exist_ok=True)
    return d


def _anterior(t: str) -> str:
    a = int(t[:4]) - 1
    return f"{a}-{str(a + 1)[-2:]}"


# ------------------------------------------------------------------ 1-2. caja y zonas
def _ligas(t: str) -> list[str]:
    return sorted(f.stem for f in (C.DIR_DATOS / "limpios" / "caja_partido" / t).glob("*.parquet"))


def caja(t: str) -> dict:
    """Rehace la caja por partido de la temporada desde los brutos (sólo esa temporada)."""
    from bbnorm5.datos import caja_partido as K
    from bbnorm5.datos import caja_partido_agregados as KA
    cfg2 = C.cargar("configs/v5/f2.yaml")
    ligas = list(cfg2.get("ligas") or _ligas(_anterior(t)))
    r = K.construir(cfg2, ligas, [t])
    ra = KA.construir(ligas, [t])
    return {"caja": int(len(r)), "agregados": int(len(ra))}


def zonas(t: str, ligas: list[str]) -> pd.DataFrame:
    from bbnorm5.datos import pista_partido as PZ
    fr = []
    for l in ligas:
        try:
            d, _ = PZ.liga_temporada(l, t)
        except Exception:  # noqa: BLE001 - liga sin jugada a jugada en la temporada
            continue
        if len(d):
            fr.append(d)
    z = pd.concat(fr, ignore_index=True) if fr else pd.DataFrame()
    if len(z):
        z.to_parquet(dir_salida(t) / "pista_partidos.parquet")
    return z


# ------------------------------------------------------------------ 3. personas
def personas(d: pd.DataFrame) -> np.ndarray:
    per = pd.read_csv(C.DIR_DATOS / "limpios" / "entidades" / "personas_v5.csv", dtype=str)
    m1 = per.drop_duplicates(["fuente_liga", "fuente_id"]).set_index(["fuente_liga", "fuente_id"])["persona_v5"]
    m2 = per.groupby("persona_crosswalk")["persona_v5"].agg(lambda s: s.mode().iloc[0])
    cw = pd.read_csv(C.RAIZ / "data" / "processed" / "player_id_crosswalk.csv", dtype=str,
                     usecols=["fuente_liga", "fuente_id", "persona_id"]).drop_duplicates(["fuente_liga", "fuente_id"])
    mc = cw.set_index(["fuente_liga", "fuente_id"])["persona_id"]
    out = []
    for l, i in zip(d["liga"], d["player_id"]):
        p = m1.get((l, i))
        if p is None:
            c = mc.get((l, i))
            p = m2.get(c) if c is not None else None
            if p is None:
                p = f"N{c}" if c is not None else f"N{l}:{i}"
        out.append(p)
    return np.asarray(out)


def partidos(t: str) -> pd.DataFrame:
    """Como medida.datos.partidos para una temporada, con las personas nuevas y las zonas de la temporada."""
    from bbnorm5.datos import puentes as P
    d = P.caja([t])
    d = d[d["fase"] == "regular"].copy()
    d["persona_v5"] = personas(d)
    d = P.exposiciones(d)
    d = d[d["min"] > 0]
    fz = dir_salida(t) / "pista_partidos.parquet"
    if fz.exists():
        d = d.merge(pd.read_parquet(fz), on=["liga", "temporada", "game_id", "player_id"], how="left")
    pos = DM._pos3([t])
    d["rol"] = [pos.get(x, "X") for x in zip(d["liga"], d["temporada"], d["player_id"])]
    r = d.groupby(DM.CLAVE + ["rol"])["min"].sum().reset_index().sort_values("min").drop_duplicates(DM.CLAVE, keep="last")
    d = d.drop(columns="rol").merge(r[DM.CLAVE + ["rol"]], on=DM.CLAVE)
    d = d.sort_values(DM.CLAVE + ["fecha", "game_id"]).reset_index(drop=True)
    orden = d.groupby(DM.CLAVE).cumcount()
    g = d.groupby(DM.CLAVE)["game_id"].transform("size")
    d["mitad"] = np.where(orden < np.ceil(g / 2), 1, 2)
    cols = set(DM.CLAVE + ["rol", "mitad", "fecha", "game_id", "team_id", "player_id", "min"])
    for fam, k, n, _ in DM.METRICAS.values():
        cols |= {k, n}
    return d[[c for c in d.columns if c in cols]]


# ------------------------------------------------------------------ 4. medida congelada
def hiper(t: str) -> pd.DataFrame:
    h = pd.read_csv(DM.DIR / "hiperparametros.csv")
    a = h[(h["temporada"] == _anterior(t)) & (h["datos"] == "temporada")].assign(temporada=t)
    return pd.concat([h[h["temporada"] != t], a], ignore_index=True)


def posteriores(d: pd.DataFrame, h: pd.DataFrame, t: str) -> pd.DataFrame:
    """Media de la tasa de cada unidad (para la varianza de la observación): la empírica contraída hacia la media del
    rol con n* de la liga (como la F3, sin rejilla)."""
    hp = CD._hiper_preferido(h)
    hp = hp[hp["temporada"] == t]
    from scipy import special
    fr = []
    for m, (fam, *_r) in DM.METRICAS.items():
        u = DM.unidad_metrica(d, m, None)
        if u.empty:
            continue
        x = hp[hp["metrica"] == m].set_index("liga")
        u = u[u["liga"].isin(x.index)].copy()
        rolmu = [x.loc[l, f"mu_{r}"] if f"mu_{r}" in x.columns and np.isfinite(x.loc[l, f"mu_{r}"]) else x.loc[l, "mu_A"]
                 for l, r in zip(u["liga"], u["rol"])]
        inv = {"binomial": special.expit, "poisson": np.exp}.get(fam, lambda z: z)
        p0 = inv(np.asarray(rolmu, float))
        ns = u["liga"].map(x["n_estab"]).to_numpy(float)
        K, N = u["K"].to_numpy(float), u["N"].to_numpy(float)
        tasa = (K + ns * p0) / (N + ns)
        fr.append(pd.DataFrame({"persona_v5": u["persona_v5"], "liga": u["liga"], "temporada": u["temporada"],
                                "metrica": m, "media": tasa, "q10": tasa, "q50": tasa, "q90": tasa}))
    return pd.concat(fr, ignore_index=True)


def observaciones(d: pd.DataFrame, t: str) -> pd.DataFrame:
    h = hiper(t)
    post = posteriores(d, h, t)
    nac = CD.nacimiento_persona([])
    o = pd.concat([CD.observaciones(d, m, h, post, nac) for m in DM.METRICAS], ignore_index=True)
    return o[o["temporada"] == t]


# ------------------------------------------------------------------ 5. carrera congelada
def niveles(o_t: pd.DataFrame) -> pd.DataFrame:
    mods = pickle.loads((CD.DIR / "modelos_final.pkl").read_bytes())
    hist = CD.cargar()
    t = o_t["temporada"].iloc[0]
    fr = []
    for m, mod in mods.items():
        x = pd.concat([hist[hist["metrica"] == m], o_t[o_t["metrica"] == m]], ignore_index=True)
        x = x.sort_values(["persona_v5", "anio"]).reset_index(drop=True)
        M = MOD.matrices(x)
        _, out = MOD.filtrar(M, mod["th"], mod["beta"])
        pid, j = M["fila"]
        r = x[["persona_v5", "liga", "temporada", "rol", "edad", "y", "v", "mu"]].assign(
            metrica=m, nivel_carrera=out["a"][pid, j], var_nivel_carrera=out["P"][pid, j])
        fr.append(r[r["temporada"] == t])
    return pd.concat(fr, ignore_index=True)


# ------------------------------------------------------------------ 6. equivalente EuroLeague y combinada
def _traduccion_extrapolada(original):
    """λ de una temporada sin NUTS: la de la última temporada, con la varianza de la innovación de un año (mediana entre
    ligas de E[(λ_T − λ_{T−1})²] en los draws) añadida."""
    def f(z, ligas, t):
        if t in z["temporadas"]:
            return original(z, ligas, t)
        ult = z["temporadas"][-1]
        m, v = original(z, ligas, ult)
        if len(z["temporadas"]) >= 2:
            d = z["lam"][:, :, -1] - z["lam"][:, :, -2]
            v = v + float(np.median(np.mean(d ** 2, axis=0)))
        return m, v
    return f


def formato(niv_t: pd.DataFrame, o_t: pd.DataFrame, t: str, mapa: pd.DataFrame) -> dict:
    meta = json.loads((COMBINADA / "meta.json").read_text())
    w, k = meta["pesos"], meta["factor_unidades"]
    obs = o_t.assign(tasa=o_t["K"] / o_t["N"])[["persona_v5", "liga", "temporada", "metrica", "tasa"]]
    original, per0 = F._traduccion, F._personas
    F._traduccion = _traduccion_extrapolada(original)
    F._personas = lambda: mapa          # personas de la temporada, nuevas incluidas
    try:
        n = F.normalizado(niv_t, obs, k, excluir=(), dir_salida=dir_salida(t), pesos=w)
    finally:
        F._traduccion, F._personas = original, per0
    return {"normalizado": n}


def ejecutar(t: str = "2026-27", rehacer_caja: bool = False) -> dict:
    import time
    t0 = time.time()
    res = {"temporada": t}
    if rehacer_caja:
        res["caja"] = caja(t)
    ligas = _ligas(t)
    z = zonas(t, ligas)
    res["zonas_filas"] = int(len(z))
    d = partidos(t)
    res["jugador_partido"], res["personas"] = int(len(d)), int(d["persona_v5"].nunique())
    res["personas_nuevas"] = int(d.loc[d["persona_v5"].str.startswith("N"), "persona_v5"].nunique())
    o_t = observaciones(d, t)
    o_t.to_parquet(dir_salida(t) / "observaciones.parquet")
    niv = niveles(o_t)
    niv.to_parquet(dir_salida(t) / "niveles_carrera.parquet")
    res["niveles"] = int(len(niv))
    mapa = d[["liga", "player_id", "persona_v5"]].drop_duplicates(["liga", "player_id"])
    res.update(formato(niv, o_t, t, mapa))
    res["tiempo_s"] = round(time.time() - t0)
    C.escribir_json({**C.metadatos({"fase": "v5.1-F6-incremental"}), **res}, dir_salida(t) / "meta.json")
    return res
