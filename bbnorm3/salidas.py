"""Salidas de la v3 en data/modelos/v3/ (rutas nuevas; nada de la v1/v2 se toca).

* normalizado/<temporada>.csv   MISMO esquema que data/modelos/normalizado/<temporada>.csv (mismas columnas y en el
                                mismo orden) más columnas propias. Para que los módulos aguas abajo lean la v3 sin
                                cambiar sus nombres de columna, las columnas de estimación final se rellenan con la
                                v3 y las originales se conservan con sufijo _v1:
                                  <m>, <m>_lo, <m>_hi, <m>_pctel, <m>_am, <m>_am_lo, <m>_am_hi, <m>_am_pctel ← v3
                                  <m>_v1 = <m> original (A+B), <m>_am_v1 = <m>_am original (A+B amortiguado)
                                  <m>_v3, <m>_v3_lo, <m>_v3_hi (80 %), <m>_v3_sd, <m>_v3_pctel  (columnas propias)
                                <m>_obs, <m>_A, <m>_B, <m>_A_am, <m>_ctx se copian sin cambios. fuente_norm = «V3».
* niveles.csv                   δ por competición-temporada y métrica (gauge en la media y re-anclado ACB = 0), sd,
                                lo80/hi80 y la covarianza en formato largo (niveles_covarianza.csv.gz)
* traduccion_cruzada/<m>.csv    T_m(a → b) de todos los pares de competiciones de la última temporada completa
* puentes.csv, ciclo.csv        grafo de puentes (personas con ≥ 150 min en ambas) y residuos de ciclo por triángulo
"""
from __future__ import annotations

import pandas as pd

SUSTITUIR = ["", "_lo", "_hi", "_pctel", "_am", "_am_lo", "_am_hi", "_am_pctel"]
FUENTE_V3 = {"": "_v3", "_lo": "_v3_lo", "_hi": "_v3_hi", "_pctel": "_v3_pctel",
             "_am": "_v3", "_am_lo": "_v3_lo", "_am_hi": "_v3_hi", "_am_pctel": "_v3_pctel"}


def combinar_normalizado(v1: pd.DataFrame, v3: pd.DataFrame, metricas: list[str], sufijo: str = "_v3",
                         fuente: str = "V3") -> pd.DataFrame:
    """v1: dataset normalizado actual (mismas filas y orden que v3); v3: columnas <m><sufijo>* (sufijo «_v3» en la
    v3.0, «_v31» en la v3.1). Devuelve el esquema del v1 delante (mismo orden) y las columnas nuevas al final."""
    out = v1.reset_index(drop=True).copy()
    v3 = v3.reset_index(drop=True)
    mapa = {k: x.replace("_v3", sufijo) for k, x in FUENTE_V3.items()}
    nuevas = {}
    for m in metricas:
        if f"{m}{sufijo}" not in v3:
            continue
        nuevas[f"{m}_v1"] = out[m].copy() if m in out else None
        if f"{m}_am" in out:
            nuevas[f"{m}_am_v1"] = out[f"{m}_am"].copy()
        for suf in SUSTITUIR:
            col, origen = f"{m}{suf}", f"{m}{mapa[suf]}"
            if col in out and origen in v3:
                out[col] = v3[origen].to_numpy()
        for c in v3.columns:
            if c.startswith(f"{m}_v3"):
                nuevas[c] = v3[c].to_numpy()
    if "fuente_norm" in out:
        out["fuente_norm"] = fuente
    extra = pd.DataFrame({k: v for k, v in nuevas.items() if v is not None})
    return pd.concat([out, extra], axis=1)
