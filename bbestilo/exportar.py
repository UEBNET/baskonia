"""Datos del mapa 3D para el Artifact (artifact/estilos/).

    estilos/meta.json        rasgos, escalas, estilos de cada red, evaluación y comparativa, pesos
                             de las dos redes (el navegador recalcula el punto de un club con un fichaje)
    estilos/clubes.json      un registro por club-competición-temporada: coordenadas, estilo y salida
                             de las dos redes, nivel y las sumas ponderadas que permiten simular fichajes
    estilos/jugadores.json   un registro por jugador-equipo-temporada (100+ min): coordenadas y estilo
                             en las dos redes, y su fila «cruda» normalizada para simular el fichaje

Formato columnar {"columnas": [...], "filas": [[...]]} para que pese poco.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from .datos import CRUDAS, _I, construir
from .encaje import red_guardada, referencias_distancia

REDES = ["idec", "vade"]


def _r(x, d=4):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return x
    return None if not np.isfinite(x) else round(x, d)


def _columnar(df: pd.DataFrame, dec: dict | None = None) -> dict:
    dec = dec or {}
    filas = []
    for fila in df.itertuples(index=False):
        filas.append([_r(v, dec.get(c, 4)) if isinstance(v, (float, np.floating)) else
                      (v.item() if isinstance(v, np.generic) else v) for c, v in zip(df.columns, fila)])
    return {"columnas": list(df.columns), "filas": filas}


def main(salida: str) -> None:
    d = Path(salida)
    d.mkdir(parents=True, exist_ok=True)
    cj = construir()
    ev = json.loads((C.DIR_SALIDA / "evaluacion.json").read_text(encoding="utf-8"))
    comp = pd.read_csv(C.DIR_SALIDA / "comparativa.csv")
    meta = {"rasgos": [r.__dict__ for r in C.RASGOS], "crudas": CRUDAS, "nivel": C.NIVEL,
            "escala_club": cj.escala_club.a_dict(), "escala_jugador": cj.escala_jugador.a_dict(),
            "temporadas_entreno": C.TEMPORADAS_ENTRENO, "temporadas_provisionales": C.TEMPORADAS_PROVISIONALES,
            "min_jugador": C.MIN_JUGADOR, "referencia_kmedias": ev.get("referencia_kmedias"),
            "comparativa": json.loads(comp.to_json(orient="records")),
            "clubes_con_nombre": {k: v for k, v in json.loads(C.CLUBES.read_text(encoding="utf-8")).items() if not k.startswith("_")},
            "redes": {}}
    clubes = cj.clubes[["clave", "clave_club", "nombre_club", "liga", "temporada", "provisional", "min_total",
                        "jugadores", "cobertura_ab", "nivel"]].copy()
    jug = cj.jugadores[cj.jugadores["min"] >= C.MIN_JUGADOR].copy()
    for red in REDES:
        rd = C.DIR_SALIDA / red
        est = pd.read_csv(rd / "estilos.csv")
        e = {k: v for k, v in ev[red].items() if k not in ("ari_matriz",)}
        ref = referencias_distancia(red_guardada(red), cj)
        q = np.linspace(0, 100, 101)
        meta["redes"][red] = {"pesos": json.loads((rd / "pesos.json").read_text(encoding="utf-8")),
                              "estilos": json.loads(est.drop(columns=["ligas"]).to_json(orient="records")),
                              "evaluacion": e,
                              # percentiles 0..100 de las distancias de referencia (encaje.referencias_distancia)
                              "referencias": {k: [_r(x, 4) for x in np.percentile(v, q)] for k, v in ref.items()}}
        tc = pd.read_csv(rd / "clubes.csv")
        assert (tc["clave"].to_numpy() == clubes["clave"].to_numpy()).all(), "clubes.csv no corresponde a los datos"
        clubes[f"{red}_x"], clubes[f"{red}_y"], clubes[f"{red}_z"] = tc["x"].to_numpy(), tc["y"].to_numpy(), tc["z"].to_numpy()
        clubes[f"{red}_e"] = tc["estilo"].str[1:].astype(int).to_numpy() - 1
        clubes[f"{red}_p"] = tc["p_estilo"].to_numpy()
        clubes[f"{red}_rob"] = tc["robustez"].to_numpy()
        clubes[f"{red}_sd"] = tc[["sd_x", "sd_y", "sd_z"]].mean(1).to_numpy()
        tj = pd.read_csv(rd / "jugadores.csv", dtype={"player_id": str})
        assert len(tj) == len(jug) and (tj["clave"].to_numpy() == jug["clave"].to_numpy()).all() \
            and (tj["player_id"].to_numpy() == jug["player_id"].astype(str).to_numpy()).all(), \
            "jugadores.csv no corresponde a los datos"
        jug[f"{red}_x"], jug[f"{red}_y"], jug[f"{red}_z"] = tj["x"].to_numpy(), tj["y"].to_numpy(), tj["z"].to_numpy()
        jug[f"{red}_e"] = tj["estilo"].str[1:].astype(int).to_numpy() - 1
        jug[f"{red}_p"] = tj["p_estilo"].to_numpy()
    # sumas ponderadas por club para simular fichajes en el navegador (misma cuenta que datos.agregar)
    S, W = [], []
    for c in clubes["clave"]:
        R, w, _ = cj.plantillas[c]
        ok = np.isfinite(R)
        u2 = R[:, _I["usg_pct"]] ** 2
        S.append(list((np.where(ok, R, 0) * w[:, None]).sum(0)) + [float(np.nansum(u2 * w))])
        W.append(list((ok * w[:, None]).sum(0)) + [float((np.isfinite(u2) * w).sum())])
    clubes["S"] = [[_r(x, 3) for x in s] for s in S]
    clubes["W"] = [[_r(x, 2) for x in s] for s in W]
    # fila cruda de cada jugador (para simular su fichaje y para restar al sustituido)
    pos = {}
    for c, (R, w, idx) in cj.plantillas.items():
        for k, i in enumerate(idx):
            pos[i] = R[k]
    jug["R"] = [[_r(x, 3) for x in pos[i]] for i in jug.index]
    cols_j = ["nombre", "clave", "nombre_club", "liga", "temporada", "pos3", "min", "nivel", "fuente_norm", "provisional",
              "persona_id"] + [f"{r}_{k}" for r in REDES for k in ("x", "y", "z", "e", "p")] + ["R"]
    jug = jug[cols_j]
    dec = {**{f"{r}_{k}": 3 for r in REDES for k in ("x", "y", "z", "p", "rob", "sd")}, "nivel": 3, "min": 0,
           "min_total": 0, "cobertura_ab": 3}
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (d / "clubes.json").write_text(json.dumps(_columnar(clubes, dec), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (d / "jugadores.json").write_text(json.dumps(_columnar(jug, dec), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tam = {p.name: p.stat().st_size for p in d.glob("*.json")}
    print("escrito", d, tam)
