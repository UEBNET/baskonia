"""F2 §6.1 · Contrato de datos v5: nada entra en el modelo sin pasarlo.

Se valida con reglas propias (sin pandera, que no aporta nada aquí): tipos, rangos, nulos, claves y coherencia
interna. Cada regla devuelve las filas que la violan. El informe por liga y temporada se escribe en
`data/v5/brutos_validados/informe_contrato.csv`; las filas que violan una regla **bloqueante** quedan marcadas
(`valida = False`) y no se usan aguas abajo.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from bbnorm5 import config as C

DIR = C.DIR_DATOS / "brutos_validados"
MIN_MAX_PARTIDO = 70.0          # 40 o 48 minutos + prórrogas

# (nombre, bloqueante, función fila → bool de violación)
REGLAS_CAJA = [
    ("clave_unica", True, None),
    ("min_en_rango", True, lambda d: ~d["min"].between(0, MIN_MAX_PARTIDO)),
    ("conteos_no_negativos", True, lambda d: (d[["pts", "fga", "fgm", "fta", "ftm", "oreb", "dreb", "ast", "stl", "tov",
                                                 "blk", "pf"]].fillna(0) < 0).any(axis=1)),
    ("anotados_le_intentados", True, lambda d: (d["fgm"] > d["fga"]) | (d["fg3m"] > d["fg3a"]) | (d["ftm"] > d["fta"])),
    ("triples_le_tiros", True, lambda d: (d["fg3a"] > d["fga"]) | (d["fg3m"] > d["fgm"])),
    # la G League juega con tiro libre único (vale 2 o 3 puntos): la identidad de puntos no aplica allí
    ("puntos_coherentes", True, lambda d: (d["liga"] != "gleague") &
     ((d["pts"] - (2 * (d["fgm"] - d["fg3m"]) + 3 * d["fg3m"] + d["ftm"])).abs() > 0.5)),
    ("rebotes_coherentes", False, lambda d: d["reb"].notna() & ((d["reb"] - d["oreb"] - d["dreb"]).abs() > 0.5)),
    ("equipo_identificado", True, lambda d: d["team_id"].isna() | (d["team_id"].astype(str) == "nan")),
    ("fecha_valida", False, lambda d: ~d["fecha"].astype(str).str.match(r"\d{4}-\d{2}-\d{2}")),
    ("persona_resuelta", False, lambda d: d["player_id"].isna()),
]
REGLAS_UNIDAD = [
    ("clave_unica", True, None),
    ("partidos_ge_1", True, lambda u: u["partidos"] < 1),
    ("min_pp_en_rango", True, lambda u: ~u["min_pp"].between(0, MIN_MAX_PARTIDO)),
    ("pct_titular_0_1", True, lambda u: ~u["pct_titular"].between(0, 1)),
    ("cuota_min_0_1", False, lambda u: ~u["cuota_min"].between(0, 1.02)),
    ("posesiones_positivas", False, lambda u: (u["min"] > 0) & ~(u["poss_on"] > 0)),
]
CLAVES = {"caja": ["liga", "temporada", "game_id", "team_id", "player_id"],
          "unidad": ["persona_v5", "liga", "temporada", "fase", "team_id"]}


def aplicar(d: pd.DataFrame, reglas, clave: list[str]) -> tuple[pd.DataFrame, pd.Series]:
    """Devuelve (una columna booleana por regla: True = viola) y la máscara de filas válidas (sin bloqueantes)."""
    V = pd.DataFrame(index=d.index)
    bloq = pd.Series(False, index=d.index)
    for nombre, bloqueante, f in reglas:
        if f is None:   # clave única entre las filas identificadas (las no identificadas ya caen por otra regla)
            ident = d[clave].notna().all(axis=1) & (d[clave].astype(str) != "nan").all(axis=1)
            v = d.duplicated(clave, keep=False) & ident
        else:
            try:
                v = f(d).fillna(False).astype(bool)
            except KeyError:
                continue
        V[nombre] = v
        if bloqueante:
            bloq |= v
    return V, ~bloq


def validar(temporadas: list[str]) -> pd.DataFrame:
    DIR.mkdir(parents=True, exist_ok=True)
    filas = []
    for t in temporadas:
        for f in sorted((C.DIR_DATOS / "limpios" / "caja_partido" / t).glob("*.parquet")):
            d = pd.read_parquet(f)
            d = d[d["jugo"]]
            V, ok = aplicar(d, REGLAS_CAJA, CLAVES["caja"])
            fila = {"tabla": "caja_partido", "liga": f.stem, "temporada": t, "filas": int(len(d)),
                    "validas": float(ok.mean()) if len(d) else np.nan}
            fila.update({f"viola_{c}": int(V[c].sum()) for c in V})
            filas.append(fila)
    u = pd.read_parquet(C.DIR_DATOS / "puentes" / "unidades.parquet")
    V, ok = aplicar(u, REGLAS_UNIDAD, CLAVES["unidad"])
    for (liga, t), idx in u.groupby(["liga", "temporada"]).groups.items():
        fila = {"tabla": "unidades", "liga": liga, "temporada": t, "filas": int(len(idx)), "validas": float(ok.loc[idx].mean())}
        fila.update({f"viola_{c}": int(V.loc[idx, c].sum()) for c in V})
        filas.append(fila)
    r = pd.DataFrame(filas)
    r.to_csv(DIR / "informe_contrato.csv", index=False)
    pd.DataFrame({"valida": ok}).to_parquet(DIR / "unidades_validas.parquet")
    return r
