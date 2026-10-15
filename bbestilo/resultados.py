"""Tablas de resultados de una red: estilos, clubes y jugadores."""
from __future__ import annotations

import numpy as np
import pandas as pd
import torch

from . import config as C
from .datos import Conjunto, remuestrear
from .evaluar import predecir


def nombre_estilo(k: int) -> str:
    return f"E{k + 1:02d}"


def descriptor(perfil: np.ndarray, umbral: float = 0.5, maximo: int = 4) -> str:
    """Texto corto con los rasgos más marcados del estilo (z medio frente al club medio)."""
    orden = np.argsort(-np.abs(perfil))
    partes = []
    for i in orden[:maximo]:
        if abs(perfil[i]) < umbral:
            break
        flecha = ("↑↑" if perfil[i] > 1.2 else "↑") if perfil[i] > 0 else ("↓↓" if perfil[i] < -1.2 else "↓")
        partes.append(f"{C.RASGOS[i].corto} {flecha}")
    return " · ".join(partes) if partes else "perfil equilibrado"


@torch.no_grad()
def tabla_estilos(red, cj: Conjunto, P: np.ndarray) -> pd.DataFrame:
    sel = ~cj.clubes["provisional"].to_numpy()
    lab = P.argmax(1)
    centros = red.a_mapa(red.centros()).numpy()
    filas = []
    for k in range(C.N_ESTILOS):
        m = sel & (lab == k)
        perfil = cj.Xc[m].mean(0) if m.any() else np.zeros(len(C.COLS))
        sub = cj.clubes[m]
        ligas = (sub["liga"].value_counts(normalize=True).round(3).to_dict()) if len(sub) else {}
        top = sub.assign(p=P[m, k]).sort_values("p", ascending=False).head(4)
        filas.append({"estilo": nombre_estilo(k), "clubes": int(m.sum()), "descriptor": descriptor(perfil),
                      "x": centros[k, 0], "y": centros[k, 1], "z": centros[k, 2],
                      "nivel_medio": float(sub["nivel"].mean()) if len(sub) else np.nan,
                      "ligas": ligas, "ejemplos": " | ".join(f"{r.nombre_club} {r.temporada[2:]} ({r.liga})" for r in top.itertuples()),
                      **{f"z_{c}": float(v) for c, v in zip(C.COLS, perfil)}})
    return pd.DataFrame(filas)


@torch.no_grad()
def tabla_clubes(red, cj: Conjunto, n_boot: int = 30, semilla: int = 5) -> tuple[pd.DataFrame, np.ndarray]:
    P, Z = predecir(red, cj.Xc)
    lab = P.argmax(1)
    rng = np.random.default_rng(semilla)
    Xb, origen = remuestrear(cj, n_boot, rng)
    Pb, Zb = predecir(red, Xb)
    lb = Pb.argmax(1)
    robustez = np.bincount(origen, weights=(lb == lab[origen]).astype(float), minlength=len(lab)) / n_boot
    sd = np.vstack([Zb[origen == i].std(0) for i in range(len(lab))])
    t = cj.clubes[["clave", "clave_club", "nombre_club", "equipo", "liga", "temporada", "provisional", "min_total",
                   "jugadores", "cobertura_ab", "nivel"]].copy()
    t["x"], t["y"], t["z"] = Z[:, 0], Z[:, 1], Z[:, 2]
    t["sd_x"], t["sd_y"], t["sd_z"] = sd[:, 0], sd[:, 1], sd[:, 2]
    t["estilo"] = [nombre_estilo(k) for k in lab]
    t["p_estilo"] = P.max(1)
    t["robustez"] = robustez
    for k in range(C.N_ESTILOS):
        t[f"p_{nombre_estilo(k)}"] = P[:, k]
    return t, P


@torch.no_grad()
def tabla_jugadores(red, cj: Conjunto) -> pd.DataFrame:
    m = (cj.jugadores["min"] >= C.MIN_JUGADOR).to_numpy()
    P, Z = predecir(red, cj.Xj[m])
    t = cj.jugadores.loc[m, ["clave", "clave_club", "nombre_club", "equipo", "liga", "temporada", "player_id",
                             "persona_id", "nombre", "pos3", "min", "nivel", "fuente_norm", "provisional"]].copy()
    t["x"], t["y"], t["z"] = Z[:, 0], Z[:, 1], Z[:, 2]
    t["estilo"] = [nombre_estilo(k) for k in P.argmax(1)]
    t["p_estilo"] = P.max(1)
    return t
