"""F5 · Examen fuera de tiempo de la capa latente, con el mismo protocolo y las mismas funciones que la F4
(bbnorm5/carrera/examen.py): para cada corte T se ajustan la F4 (por métrica) y Λ, ψ con las temporadas anteriores a T, y
se predice la producción de T de cada persona con historial y ≥ 100 minutos en su liga principal de T."""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

from bbnorm5.carrera import datos as CD
from bbnorm5.carrera import examen as EX
from bbnorm5.carrera import modelo as MC
from bbnorm5.latente import modelo as ML
from bbnorm5.medida import datos as DM


def f4_por_metrica(o: pd.DataFrame, h: pd.DataFrame, anio: int | None) -> dict:
    out = {}
    for met in ML.METRICAS:
        x = o[o["metrica"] == met]
        hh = h[h["metrica"] == met]
        if anio is not None:
            hh = hh[hh["temporada"].str[:4].astype(int) < anio]
        out[met] = MC.ajustar(MC.matrices(x), "completo", float(hh["sigma"].median()))
    return out


def objetivo_persona(o: pd.DataFrame, anio: int) -> pd.DataFrame:
    b = o.drop_duplicates(["persona_v5", "anio"])[["persona_v5", "anio", "liga", "rol", "edad"]]
    hist = b[b["anio"] < anio].sort_values("anio").drop_duplicates("persona_v5", keep="last")
    t = b[b["anio"] == anio].merge(hist, on="persona_v5", suffixes=("", "_ult"))
    t["gap"] = (t["anio"] - t["anio_ult"]).astype(float)
    t["cl"] = (t["liga"] != t["liga_ult"]).astype(float)
    t["cr"] = (t["rol"] != t["rol_ult"]).astype(float)
    return t[["persona_v5", "edad", "gap", "cl", "cr"]]


def corte(o: pd.DataFrame, h: pd.DataFrame, anio: int, variantes: list[tuple[int, str]], semilla: int,
          n_sub: int = 7000, maxiter: int = 300):
    hp = CD._hiper_preferido(h)
    hist = o[o["anio"] < anio]
    f4 = f4_por_metrica(hist, hp, anio)
    S = ML.matrices(hist, f4)
    obj_p = objetivo_persona(o, anio)
    casos, mods = [], {}
    Ssub = ML.submuestra(S, n_sub, np.random.default_rng(semilla + anio))
    for var in variantes:
        K, cambios = var[0], var[1]
        kr = var[2] if len(var) > 2 else 0
        mod = ML.ajustar(Ssub, K, cambios, maxiter=maxiter, kr=kr)
        mods[tuple(var)] = mod
        nombre = f"K{K}_{cambios}" + (f"_r{kr}" if kr else "")
        pred = ML.predecir(S, mod, obj_p)
        for met in ML.METRICAS:
            fam = DM.METRICAS[met][0]
            om = o[o["metrica"] == met]
            obj = EX.objetivo(om, om[om["anio"] < anio], anio, hp, met)
            pm = pred[pred["metrica"] == met].drop(columns="metrica")
            x = obj.merge(pm, on="persona_v5")
            x["temporadas_hist"] = x["persona_v5"].map(hist.drop_duplicates(["persona_v5", "anio"]).groupby("persona_v5").size())
            rng = np.random.default_rng((semilla + zlib.crc32(f"{met}|{anio}|{nombre}".encode())) % 2 ** 32)
            casos.append(EX.evaluar(x, fam, nombre, rng).assign(metrica=met, anio=anio))
        print(f"  {anio} {nombre}: logL {mod['logL']:.1f}, convergió {mod['convergio']}", flush=True)
    return pd.concat(casos, ignore_index=True), mods
