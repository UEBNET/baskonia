"""Química de estilos: cómo cambia el juego de un jugador según el estilo (y el nivel) del compañero con el que
comparte pista. Une la VaDE (probabilidad de cada estilo de cada jugador) con los efectos X → Y del jugada a
jugada (bbmodel/interacciones.py) y la sinergia de parejas.

    python -m bbestilo quimica      → data/modelos/estilos/interacciones.json

Pasos:
  1. Salida de la VaDE (6 probabilidades) de cada fila jugador-equipo-temporada con minutos suficientes.
  2. Paso a los identificadores del jugada a jugada (id de la fuente; en la BBL el modelo usa «n:<nombre>»).
  3. Nivel L de cada jugador (contexto.py, vara EuroLeague) como control.
  4. bbmodel.interacciones.modelo_estilos (efectos dirigidos) y sinergia_estilos (parejas, simétrica).
  5. Ejemplos reales de cada celda (parejas con más minutos cuyo X y Y son nítidamente de esos estilos).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from bbmodel import interacciones as I
from bbmodel.contexto import cargar as cargar_contexto

from . import config as C
from .encaje import conjunto, red_guardada
from .evaluar import predecir


def tabla_estilos() -> pd.DataFrame:
    """liga, temporada, player_id (id de la fuente), nombre, team_id, L y p_E01…p_EK (media por minutos si
    el jugador tiene varios equipos en la liga)."""
    cj = conjunto()
    red = red_guardada("vade")
    J = cj.jugadores
    P, _ = predecir(red, cj.Xj)
    pcols = [f"p_E{k + 1:02d}" for k in range(P.shape[1])]
    d = J[["liga", "temporada", "player_id", "nombre", "min"]].copy()
    d[pcols] = P
    d = d[d["min"] >= 60]
    # media ponderada por minutos por jugador-liga-temporada (ids del modelo)
    for c in pcols:
        d[c] = d[c] * d["min"]
    g = d.groupby(["liga", "temporada", "player_id"])
    t = g[pcols + ["min"]].sum()
    t[pcols] = t[pcols].div(t["min"], axis=0)
    t = t.reset_index().rename(columns={"player_id": "pid_modelo"})
    # ids de la fuente (los del jugada a jugada) y nivel L
    ctx = cargar_contexto()[["liga", "temporada", "player_id", "pid_modelo", "L", "nombre"]]
    ctx = ctx.drop_duplicates(["liga", "temporada", "player_id"])
    out = ctx.merge(t, on=["liga", "temporada", "pid_modelo"], how="inner")
    return out


def ejemplos(ef: pd.DataFrame, tabla: pd.DataFrame, k: int, umbral: float = 0.6, n: int = 3) -> list:
    """Parejas reales con más minutos juntos cuyo X es nítidamente del estilo s y Y del estilo t."""
    pcols = [f"p_E{i + 1:02d}" for i in range(k)]
    T = tabla.set_index(["liga", "temporada", "player_id"])
    kx = pd.MultiIndex.from_frame(ef[["liga", "temporada", "x"]])
    ky = pd.MultiIndex.from_frame(ef[["liga", "temporada", "y"]])
    PX = T[pcols].reindex(kx).to_numpy(float); PY = T[pcols].reindex(ky).to_numpy(float)
    nx = T["nombre"].reindex(kx).to_numpy(); ny = T["nombre"].reindex(ky).to_numpy()
    ex = ef.assign(sx=np.nanargmax(np.nan_to_num(PX, nan=-1), 1), px=np.nanmax(np.nan_to_num(PX, nan=-1), 1),
                   sy=np.nanargmax(np.nan_to_num(PY, nan=-1), 1), py=np.nanmax(np.nan_to_num(PY, nan=-1), 1),
                   nx=nx, ny=ny)
    ex = ex[(ex["px"] >= umbral) & (ex["py"] >= umbral)].sort_values("sec_con", ascending=False)
    out = [[[] for _ in range(k)] for _ in range(k)]
    for (s, t_), g in ex.groupby(["sx", "sy"]):
        out[int(s)][int(t_)] = [{"x": r.nx, "y": r.ny, "liga": r.liga, "temporada": r.temporada,
                                 "min": round(r.sec_con / 60), "d_efg": round(r.d_efg, 1) if np.isfinite(r.d_efg) else None,
                                 "d_cuota_tiro": round(r.d_cuota_tiro, 1) if np.isfinite(r.d_cuota_tiro) else None}
                                for r in g.head(n).itertuples()]
    return out


def main() -> dict:
    tabla = tabla_estilos()
    ef = I.cargar_efectos()
    res = I.modelo_estilos(ef, tabla)
    res["sinergia"] = I.sinergia_estilos(tabla)
    res["ejemplos"] = ejemplos(ef, tabla, C.N_ESTILOS)
    res["jugadores_con_estilo"] = int(len(tabla))
    p = C.DIR_SALIDA / "interacciones.json"
    p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("escrito", p)
    for k, e in res["efectos"].items():
        print(f"{k:14s} n={e['n']:6d}  nivel X {e['nivel_x']:+.3f} ± {e['nivel_x_se']:.3f}")
        print(np.array(e["matriz"]).round(2))
    s = res["sinergia"]
    print("sinergia", s["n_parejas"], "nivel_suma", s["nivel_suma"], "±", s["nivel_suma_se"])
    print(np.array(s["matriz"]).round(2))
    return res
