"""D3 · unidades v4.2 de la temporada en curso para el botón «Actualizar 2026-27» (sin reajustar nada).

`unidades.exportar()` ajusta los hiperparámetros con las temporadas cerradas y escribe la estimación de todas las
temporadas (y se niega a sobrescribir). La temporada en curso no entra en ese ajuste, así que al llegar partidos nuevos
basta con:

1. filtrar otra vez cada tipo que pasó (tríos, parejas, sinergia) con los parámetros CONGELADOS de
   `data/modelos/v4_2/unidades/parametros_v42.json` (el filtro es causal: las filas de temporadas cerradas salen
   idénticas);
2. sustituir en `<tipo>_v42.csv.gz` sólo las filas de la temporada en curso (el resto, byte a byte igual);
3. reexportar para la página `artifact/kerno/quintetos/datos_v42/<temporada>/<liga>.gz.txt` e `indice.json`.

    PYTHONPATH=. python -m bbequipo.v42.actualizar [--temporada 2026-27]
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import unidades as U
from . import unidades_artifact as UA

COLS = ["liga", "temporada", "team_id", "unidad", "poss", "observado", "vigente_v41", "esperado_jugadores", "v42",
        "v42_lo", "v42_hi", "previa_m", "previa_sd", "temporadas_previas", "peso_temporada"]


def estimar(tipo: str, par: dict) -> pd.DataFrame:
    """Estimación v4.2 de todas las temporadas con parámetros dados (mismas columnas que `unidades.exportar`)."""
    todo = U.cargar(tipo)
    base = todo[todo["poss"] >= U.MIN_POSS_AJUSTE].reset_index(drop=True)
    f = U.filtrar(base, par)
    est = U._estructura(base)
    out = base.assign(v42=f["theta"], v42_lo=f["theta"] - U.Z80 * np.sqrt(f["P"]),
                      v42_hi=f["theta"] + U.Z80 * np.sqrt(f["P"]), esperado_jugadores=f["mu"],
                      temporadas_previas=est["paso"], previa_m=f["m_pred"], previa_sd=np.sqrt(f["P_pred"]),
                      peso_temporada=1 - f["P"] / np.maximum(f["P_pred"], 1e-12))
    out = out.rename(columns={"y": "observado", "vigente": "vigente_v41"})
    return out[COLS].round(4)


def empalmar(previo: pd.DataFrame, nuevo: pd.DataFrame, temporada: str) -> pd.DataFrame:
    """Filas de las demás temporadas tal cual; las de `temporada`, las nuevas (ordenadas como las escribe exportar)."""
    return pd.concat([previo[previo["temporada"] != temporada], nuevo[nuevo["temporada"] == temporada]],
                     ignore_index=True)


def _csv_gz(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:
        g.write(df.to_csv(index=False).encode("utf-8"))
    return buf.getvalue()


def temporada_en_curso(temporada: str | None = None, salida_artifact: Path = UA.SALIDA) -> dict:
    temporada = temporada or U.CFG["temporadas"][-1]
    if temporada != U.CFG["temporadas"][-1]:
        raise ValueError(f"sólo la temporada en curso ({U.CFG['temporadas'][-1]}): las cerradas fijan los parámetros")
    params = json.loads((U.SALIDA / "parametros_v42.json").read_text(encoding="utf-8"))
    res = {}
    for tipo, par in params.items():
        dest = U.SALIDA / f"{tipo}_v42.csv.gz"
        previo = pd.read_csv(dest, dtype={"team_id": str, "unidad": str, "temporada": str}, low_memory=False)
        nuevo = estimar(tipo, par)
        nuevo["temporada"] = nuevo["temporada"].astype(str)
        d = empalmar(previo, nuevo, temporada)
        dest.write_bytes(_csv_gz(d))
        res[tipo] = {"filas_temporada": int((d["temporada"] == temporada).sum()),
                     "filas_antes": int((previo["temporada"] == temporada).sum())}
    U._CACHE.clear()
    res["artifact"] = UA.exportar(salida_artifact, temporadas=[temporada])
    return res


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m bbequipo.v42.actualizar")
    ap.add_argument("--temporada", default=None)
    a = ap.parse_args()
    t0 = time.time()
    r = temporada_en_curso(a.temporada)
    print(json.dumps({k: v for k, v in r.items() if k != "artifact"}, ensure_ascii=False))
    print(f"hecho en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
