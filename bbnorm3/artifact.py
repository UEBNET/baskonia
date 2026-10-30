"""Datos del artifact con la normalización v3.1 (mismo formato que bbmodel.dataset_normalizado, sin tocar la página).

    python -m bbnorm3.artifact [--salida data/artifact]

    <salida>/normalizados/<temp>/regular.json     pestaña «Datos Normalizados»: columnas del esquema v1, valores v3.1
    <salida>/normalizados/indice.json             temporadas, ligas y filas por liga
    <salida>/normalizacion/jugadores_<temp>.json  explorador de «Normalización de ligas»: «A+B» pasa a ser la v3.1

Las columnas y su orden son exactamente las del dataset normalizado v1, así que la página las lee igual. Cambian los
valores de las estimaciones finales (<m>, _lo, _hi, _pctel, <m>_am…: v3.1) y `fuente_norm` («V3.1»). Las columnas
<m>_A y <m>_B siguen siendo las del algoritmo A y del B.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from bbmodel.dataset_normalizado import METRICAS, NOMBRES_LIGA, _columnar, _dump, explorador

from .config import RAIZ

DIR_V1 = RAIZ / "data" / "modelos" / "normalizado"
DIR_V31 = RAIZ / "data" / "modelos" / "v3_1" / "normalizado"
PROC = RAIZ / "data" / "processed"


def main(salida: str = "data/artifact") -> None:
    sal = Path(salida)
    indice = {"generado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "temporadas": {},
              "descripcion": "Equivalente EuroLeague 2025-26 de todos los jugadores con la normalización v3.1 "
                             "(combinación de A+B amortiguado y la CVAE jerárquica), temporada regular",
              "metricas": METRICAS}
    for f in sorted(DIR_V31.glob("*.csv.gz")):
        temp = f.name[:7]
        cols = pd.read_csv(DIR_V1 / f"{temp}.csv", nrows=0).columns
        df = pd.read_csv(f, low_memory=False)[list(cols)]
        df["fuente_norm"] = "V3.1"
        _dump(_columnar(df), sal / "normalizados" / temp / "regular.json")
        _dump(explorador(df), sal / "normalizacion" / f"jugadores_{temp}.json")
        pi = PROC / temp / "indice.json"
        fechas = {k: v.get("fecha_extraccion") for k, v in json.loads(pi.read_text(encoding="utf-8")).get("ligas", {}).items()} \
            if pi.exists() else {}
        ligas = {liga: {"nombre": NOMBRES_LIGA.get(liga, liga), "fases": {"regular": int(len(g))},
                        "fecha_extraccion": fechas.get(liga), "a_mas_b": int(len(g))} for liga, g in df.groupby("liga")}
        indice["temporadas"][temp] = {"temporada": temp, "fases": ["regular"], "fases_con_datos": ["regular"],
                                      "ligas": ligas}
        print(f"  {temp}: {len(df)} jugadores", flush=True)
    _dump(indice, sal / "normalizados" / "indice.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default="data/artifact")
    main(ap.parse_args().salida)
