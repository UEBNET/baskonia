"""v5.1 F6 · Kit del proceso paralelo: lo mínimo de la v5 para que el botón de la temporada en curso funcione en la rama
de producción, que no lleva los 2,9 GB de `data/v5/`.

Misma estructura de carpetas que `data/v5/` (y `data/v5_1/salidas/combinada/meta.json`), de modo que el código de
`bbnorm5` no cambia: en producción el kit se copia en `data/v5/`; aquí se comprueba con `BBNORM5_DATOS` apuntando al kit.

| Fichero | Para qué | Reducción |
|---|---|---|
| limpios/entidades/personas_v5.csv | personas por id de fuente | — |
| medida/hiperparametros.csv | media del rol, dispersión y σ congelados | sólo la última temporada |
| medida/partidos.parquet | razones oportunidades/posesiones de la vara (TS%, eFG%, por 100) | sumas por liga-temporada |
| carrera/observaciones.parquet | serie histórica que recorre el filtro | sólo las columnas del filtro |
| carrera/modelos_final.pkl, nacimiento_persona.csv | θ, β y edades | — |
| ligas/lambda_paso2_*.npz | traducción entre ligas | las dos últimas temporadas |
| latente/correlacion_capacidades.csv | correlación de las capacidades (TS%, eFG%) | — |
| v5_1/salidas/combinada/meta.json | pesos y factores de unidad de la combinada | — |

La caja por partido de la temporada en curso la rehace el propio botón desde los brutos (`--rehacer-caja`).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from bbnorm5 import config as C

V5 = C.RAIZ / "data" / "v5"
COLS_OBS = ["persona_v5", "liga", "temporada", "rol", "mu", "mu_E", "mu_A", "mu_I", "mu_X", "y", "v", "anio", "edad",
            "metrica"]


def exportar(destino: Path | None = None, ultima: str = "2025-26") -> dict:
    kit = Path(destino or C.RAIZ / "data" / "v5_1" / "kit")
    v5 = kit / "v5"
    for sub in ("limpios/entidades", "medida", "carrera", "ligas", "latente"):
        (v5 / sub).mkdir(parents=True, exist_ok=True)
    out = {}
    for f in ("limpios/entidades/personas_v5.csv", "carrera/modelos_final.pkl", "carrera/nacimiento_persona.csv",
              "latente/correlacion_capacidades.csv"):
        shutil.copy2(V5 / f, v5 / f)
    h = pd.read_csv(V5 / "medida" / "hiperparametros.csv")
    h[h["temporada"] == ultima].to_csv(v5 / "medida" / "hiperparametros.csv", index=False)
    p = pd.read_parquet(V5 / "medida" / "partidos.parquet",
                        columns=["liga", "temporada", "poss_on", "oreb_op", "dreb_op", "blk_op", "min"])
    p.groupby(["liga", "temporada"], as_index=False).sum().to_parquet(v5 / "medida" / "partidos.parquet")
    o = pd.read_parquet(V5 / "carrera" / "observaciones.parquet", columns=COLS_OBS)
    for c in ("persona_v5", "liga", "temporada", "rol", "metrica"):
        o[c] = o[c].astype("category")
    o.to_parquet(v5 / "carrera" / "observaciones.parquet", compression="zstd")
    for f in sorted((V5 / "ligas").glob("lambda_paso2_*.npz")):
        z = dict(np.load(f, allow_pickle=True))
        t = list(z["temporadas"])
        k = [t.index(x) for x in t[-2:]]
        z["lam"], z["temporadas"] = z["lam"][:, :, k], np.asarray(t[-2:])
        np.savez_compressed(v5 / "ligas" / f.name, **z)
    m = kit / "v5_1" / "salidas" / "combinada"
    m.mkdir(parents=True, exist_ok=True)
    shutil.copy2(C.RAIZ / "data" / "v5_1" / "salidas" / "combinada" / "meta.json", m / "meta.json")
    tam = {str(f.relative_to(kit)): f.stat().st_size for f in sorted(kit.rglob("*")) if f.is_file()}
    out["ficheros"], out["mb"] = len(tam), round(sum(tam.values()) / 1e6, 1)
    C.escribir_json({**C.metadatos({"fase": "v5.1-F6-kit"}), "ultima": ultima, "tamanos": tam}, kit / "meta_kit.json")
    return out
