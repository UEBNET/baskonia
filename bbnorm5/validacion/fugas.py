"""F8 · Auditoría de fugas (encargo §12): que ningún dato de t+1 entre en el ajuste hasta t.

Comprobaciones con datos (las demás, por construcción del código, se documentan en el informe):
- **Identidades** unidas por la v5 con evidencia sólo de temporadas ≥ T (mismo club en dos competiciones esa
  temporada): sus casos de T usarían un enlace que en t aún no se conocía.
- **Rol, volumen y exposición de T** en la proyección publicada (condicionada): diferencia de error con la versión ex
  ante (rol desconocido, sin volumen, exposición de la temporada anterior).
- **λ por año objetivo**: los GLS del paso 2 sólo usan puentes intra de temporadas < T y traspasos con año objetivo < T
  (lo comprueba un test: añadir datos de T o posteriores no cambia el GLS de T).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from bbnorm5 import config as C

DIR = C.DIR_DATOS / "validacion"


def identidades_tardias(p: pd.DataFrame) -> dict:
    r = pd.read_csv(C.DIR_DATOS / "limpios" / "entidades" / "revision_identidades.csv", dtype=str)
    u = r[(r["tipo"] == "enlace_perdido") & r["accion_v5"].str.startswith("unido")].copy()
    u["anio_evid"] = u["detalle"].str[:4].astype(int)
    per = pd.read_csv(C.DIR_DATOS / "limpios" / "entidades" / "personas_v5.csv", dtype=str)
    nodo = dict(zip(per["fuente_liga"] + ":" + per["fuente_id"], per["persona_v5"]))
    u["persona_v5"] = u["nodo_a"].map(nodo)
    primera = u.groupby("persona_v5")["anio_evid"].min()
    casos = p[["persona_v5", "anio"]].drop_duplicates()
    casos["evid"] = casos["persona_v5"].map(primera)
    tard = casos["evid"].notna() & (casos["evid"] >= casos["anio"])
    return {"personas_unidas_v5": int(primera.size), "casos_persona_anio": int(len(casos)),
            "casos_con_union_de_evidencia_posterior": int(tard.sum()),
            "cuota": float(tard.mean())}


def rol_volumen(p: pd.DataFrame) -> pd.DataFrame:
    """CRPS medio relativo de la proyección condicionada (rol, volumen y exposición de T) frente a la ex ante."""
    q = p[p["modelo"].isin(["final", "final_exposicion_t", "ex_ante"])]
    w = q.pivot_table(index=["persona_v5", "liga", "anio", "metrica"], columns="modelo", values="crps").dropna()
    filas = []
    for m, g in list(w.groupby(level="metrica")) + [("todas", w)]:
        filas.append({"metrica": m, "casos": len(g),
                      "condicionada_frente_ex_ante": float(g["final"].mean() / g["ex_ante"].mean() - 1),
                      "solo_exposicion_t_frente_ex_ante": float(g["final_exposicion_t"].mean() / g["ex_ante"].mean() - 1)})
    return pd.DataFrame(filas)


def ejecutar(cfg: dict) -> dict:
    p = pd.read_parquet(DIR / "predicciones_v5.parquet")
    rv = rol_volumen(p)
    rv.to_csv(DIR / "fugas_rol_volumen.csv", index=False)
    ident = identidades_tardias(p)
    out = {"identidades": ident, "rol_volumen_todas": rv[rv["metrica"] == "todas"].iloc[0].to_dict()}
    C.escribir_json(out, DIR / "fugas.json")
    return out
