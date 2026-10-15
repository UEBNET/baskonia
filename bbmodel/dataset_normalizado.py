"""Dataset completo de datos normalizados: el equivalente EuroLeague 2025-26 de TODOS los jugadores, de todas las
competiciones y temporadas, en las 25 métricas del estudio de normalización.

Para cada jugador-liga-temporada (temporada regular) y métrica:
    <m>_obs      valor observado en su liga
    <m>_A, <m>_B equivalente EuroLeague según el algoritmo A y el B
    <m>          estimación final A+B: media de A y B en la escala transformada de la métrica; sólo A cuando B no
                 traduce al jugador (menos de 150 minutos o la temporada en curso, 2026-27)
    <m>_lo/_hi   intervalo del 80 % (A+B del mismo modo)
    <m>_pctel    percentil del jugador entre los jugadores de la EuroLeague de su posición (A+B)
y la identidad del jugador (nombre, equipo, posición, edad, nacionalidad…), minutos y partidos, y `fuente_norm`
(«A+B» o «A»).

    python -m bbmodel dataset-normalizado [--salida data/artifact]
        data/modelos/normalizado/<temp>.csv                  el dataset (CSV, una fila por jugador-liga-temporada)
        <salida>/normalizados/<temp>/regular.json            mismo contenido en JSON columnar para la Mesa
        <salida>/normalizados/indice.json                    temporadas, ligas y filas por liga
        <salida>/normalizacion/jugadores_<temp>.json         explorador de «Normalización de ligas», todas las temporadas
        <salida>/<temp>/nacionalidades.json                  nacionalidad por jugador para la «Tabla de datos»
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .metricas import CATALOGO, destransformar, transformar
from .nacionalidad import SALIDA as NACIONALIDADES, id_modelo

RAIZ = Path(__file__).resolve().parent.parent
DA = RAIZ / "data" / "modelos" / "algoritmo_A" / "traducciones"
DB = RAIZ / "data" / "modelos" / "algoritmo_B" / "traducciones"
PROC = RAIZ / "data" / "processed"
SALIDA_CSV = RAIZ / "data" / "modelos" / "normalizado"
METRICAS = list(CATALOGO)
NOMBRES_LIGA = {"euroleague": "EuroLeague", "eurocup": "EuroCup", "acb": "Liga Endesa", "nba": "NBA", "gleague": "G League",
                "lba": "LBA", "bbl": "BBL", "lnb": "LNB"}
IDENTIDAD_BRUTA = ["player_uid", "team_id", "posicion", "edad", "fecha_nacimiento", "altura_cm", "peso_kg", "dorsal", "equipo_codigo",
                   "liga_nombre", "fecha_extraccion"]


def combinar(a, b, col: str):
    """A+B en la escala transformada de la métrica; sólo A (o sólo B) donde falta el otro."""
    tr = CATALOGO[col].transf
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    ab = destransformar((transformar(a, tr) + transformar(b, tr)) / 2, tr)
    return pd.Series(np.where(b.isna(), a, np.where(a.isna(), b, ab)), index=a.index)


def _brutos(temporada: str) -> pd.DataFrame:
    """Identidad del jugador en los datos procesados (temporada regular), con el id del estudio de normalización."""
    filas = []
    for f in sorted((PROC / temporada / "ligas").glob("*.csv")):
        d = pd.read_csv(f, dtype={"player_id": str, "dorsal": str}, low_memory=False)
        d = d[d["fase"] == "regular"]
        cols = ["liga", "player_id", "nombre"] + [c for c in IDENTIDAD_BRUTA if c in d]
        filas.append(d[cols].sort_values(cols[:2]).drop_duplicates(["liga", "player_id"]))
    b = pd.concat(filas, ignore_index=True)
    b["pid_modelo"] = id_modelo(b["liga"], b["player_id"], b["nombre"])
    return b.drop(columns=["nombre"]).rename(columns={"player_id": "player_id_fuente"}).drop_duplicates(["liga", "pid_modelo"])


def construir(temporada: str) -> pd.DataFrame:
    a = pd.read_csv(DA / f"{temporada}.csv", dtype={"player_id": str}, low_memory=False)
    pb = DB / f"{temporada}.csv"
    b = pd.read_csv(pb, dtype={"player_id": str}, low_memory=False) if pb.exists() else pd.DataFrame(columns=["persona_id", "liga"])
    clave = ["persona_id", "liga", "temporada"]
    cols_b = [c for m in METRICAS for c in (f"{m}_el", f"{m}_el_lo", f"{m}_el_hi", f"{m}_pct_el") if c in b]
    m = a.merge(b[clave + cols_b], on=clave, how="left", suffixes=("", "_B"))
    out = m[["persona_id", "liga", "temporada", "player_id", "nombre", "equipo", "pos3", "pos3_estimada", "anio_nac",
             "gp", "min"]].copy().rename(columns={"player_id": "pid_modelo"})
    out["min_pg"] = out["min"] / out["gp"].where(out["gp"] > 0)
    tiene_b = pd.Series(False, index=m.index)
    cols = {}
    for c in METRICAS:
        A, lo_a, hi_a, p_a = m[f"{c}_el"], m[f"{c}_el_lo"], m[f"{c}_el_hi"], m[f"{c}_pct_el"]
        B = m.get(f"{c}_el_B", pd.Series(np.nan, index=m.index))
        lo_b = m.get(f"{c}_el_lo_B", pd.Series(np.nan, index=m.index))
        hi_b = m.get(f"{c}_el_hi_B", pd.Series(np.nan, index=m.index))
        p_b = m.get(f"{c}_pct_el_B", pd.Series(np.nan, index=m.index))
        tiene_b |= B.notna()
        cols[c] = combinar(A, B, c)
        cols[f"{c}_lo"] = combinar(lo_a, lo_b, c)
        cols[f"{c}_hi"] = combinar(hi_a, hi_b, c)
        cols[f"{c}_pctel"] = pd.concat([p_a, p_b], axis=1).mean(axis=1)
        cols[f"{c}_obs"] = m[c]
        cols[f"{c}_A"] = A
        cols[f"{c}_B"] = B
    out = pd.concat([out, pd.DataFrame(cols)], axis=1)
    out["fuente_norm"] = np.where(tiene_b, "A+B", "A")
    # identidad de los datos brutos y nacionalidad
    out = out.merge(_brutos(temporada), on=["liga", "pid_modelo"], how="left")
    out["player_id"] = out["player_id_fuente"].fillna(out["pid_modelo"])
    out["player_uid"] = out["player_uid"].fillna(out["liga"] + ":" + out["player_id"].astype(str))
    out["liga_nombre"] = out["liga"].map(NOMBRES_LIGA)
    out["edad"] = out["edad"].where(out["edad"].notna(), int(temporada[:4]) - out["anio_nac"])
    if NACIONALIDADES.exists():
        nac = pd.read_csv(NACIONALIDADES, dtype={"player_id": str})
        nac = nac[nac["temporada"] == temporada][["liga", "player_id", "nacionalidad", "nacionalidad_fuente"]]
        out = out.merge(nac, on=["liga", "player_id"], how="left")
    ident = ["persona_id", "player_uid", "player_id", "team_id", "liga", "liga_nombre", "temporada", "nombre", "equipo", "posicion",
             "pos3", "pos3_estimada", "edad", "anio_nac", "fecha_nacimiento", "nacionalidad", "nacionalidad_fuente",
             "altura_cm", "gp", "min", "min_pg", "fuente_norm"]
    ident = [c for c in ident if c in out]
    out = out[ident + list(cols)].drop_duplicates(["liga", "player_id"])
    return anadir_contexto(out, temporada)


CTX = RAIZ / "data" / "modelos" / "contexto"
CTX_COLS = ["L", "ctx_comp", "ctx_riv", "ctx_plantilla", "ctx_plantilla_dev"]


def anadir_contexto(out: pd.DataFrame, temporada: str) -> pd.DataFrame:
    """Contexto de nivel (bbmodel/contexto.py) y valores sin contexto `<m>_ctx`: lo que marcaría con compañeros de
    nivel EuroLeague medio, para las métricas cuya sensibilidad al contexto es clara (|β| > 2 errores típicos).
    Se resta β · desviación del contexto de plantilla en la escala transformada (τ de la EuroLeague de su posición)."""
    pj, ps = CTX / "por_jugador_liga.csv", CTX / "sensibilidad.csv"
    if not pj.exists() or not ps.exists():
        return out
    c = pd.read_csv(pj, dtype={"player_id": str})
    c = c[c["temporada"] == temporada][["liga", "player_id"] + CTX_COLS].rename(columns={"player_id": "pid_modelo"})
    out = out.copy()
    out["pid_modelo"] = out["player_id"]
    from .nacionalidad import id_modelo
    out["pid_modelo"] = id_modelo(out["liga"], out["player_id"], out["nombre"])
    out = out.merge(c, on=["liga", "pid_modelo"], how="left").drop(columns=["pid_modelo"])
    sens = pd.read_csv(ps)
    params = json.loads((RAIZ / "data" / "modelos" / "algoritmo_A" / "parametros.json").read_text(encoding="utf-8"))["metricas"]
    dev = out["ctx_plantilla_dev"].fillna(0.0).to_numpy(float)
    nuevas = {}
    for r in sens.itertuples():
        if r.metrica not in out or abs(r.beta_comp) <= 2 * r.beta_comp_se or r.metrica not in params:
            continue
        tr = CATALOGO[r.metrica].transf
        tau2 = params[r.metrica]["suerte"]["tau2"]
        tau = out["pos3"].map(lambda p: np.sqrt(tau2.get(f"euroleague|{p}", np.nan)) if isinstance(p, str) else np.nan)
        y = transformar(pd.to_numeric(out[r.metrica], errors="coerce"), tr)
        nuevas[f"{r.metrica}_ctx"] = destransformar(y - tau.to_numpy(float) * r.beta_comp * dev, tr)
    return pd.concat([out, pd.DataFrame(nuevas, index=out.index)], axis=1)


def _columnar(df: pd.DataFrame, dec: int = 3) -> dict:
    filas = []
    for t in df.itertuples(index=False):
        fila = []
        for v in t:
            if isinstance(v, (float, np.floating)):
                fila.append(None if not np.isfinite(v) else round(float(v), dec))
            elif isinstance(v, np.integer):
                fila.append(int(v))
            elif v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA:
                fila.append(None)
            else:
                fila.append(v)
        filas.append(fila)
    return {"columnas": list(df.columns), "filas": filas}


def _dump(obj, ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")


def explorador(df: pd.DataFrame) -> dict:
    """Formato de datos/normalizacion/jugadores_<temp>.json (pestaña «Normalización de ligas»), ahora con todos
    los jugadores y la estimación A+B para todos (sólo A donde B no traduce)."""
    from .mesa_normalizacion import EXPLORADOR
    j = df.rename(columns={"edad": "_edad"})
    cols = ["nombre", "equipo", "liga", "pos3", "pos3_estimada", "anio_nac", "nacionalidad", "gp", "min", "fuente_norm"]
    data = {k: j[k] for k in cols}
    for c in EXPLORADOR:
        data.update({c: j[f"{c}_obs"], f"{c}_el_A": j[f"{c}_A"], f"{c}_el_B": j[f"{c}_B"], f"{c}_el_AB": j[c],
                     f"{c}_pct_el_AB": j[f"{c}_pctel"], f"{c}_el_lo_AB": j[f"{c}_lo"], f"{c}_el_hi_AB": j[f"{c}_hi"]})
    return _columnar(pd.DataFrame(data), 2)


def main(salida: str = "data/artifact") -> None:
    sal = Path(salida)
    SALIDA_CSV.mkdir(parents=True, exist_ok=True)
    indice = {"generado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "temporadas": {},
              "descripcion": "Equivalente EuroLeague 2025-26 (A+B; sólo A donde B no traduce) de todos los jugadores, "
                             "temporada regular", "metricas": METRICAS}
    for f in sorted(DA.glob("*.csv")):
        temp = f.stem
        df = construir(temp)
        df.to_csv(SALIDA_CSV / f"{temp}.csv", index=False, float_format="%.4f")
        _dump(_columnar(df), sal / "normalizados" / temp / "regular.json")
        _dump(explorador(df), sal / "normalizacion" / f"jugadores_{temp}.json")
        ligas = {}
        pi = PROC / temp / "indice.json"
        fechas = {k: v.get("fecha_extraccion") for k, v in json.loads(pi.read_text(encoding="utf-8")).get("ligas", {}).items()} if pi.exists() else {}
        for liga, g in df.groupby("liga"):
            fe = fechas.get(liga)
            ligas[liga] = {"nombre": NOMBRES_LIGA.get(liga, liga), "fases": {"regular": int(len(g))}, "fecha_extraccion": fe,
                           "a_mas_b": int((g["fuente_norm"] == "A+B").sum())}
        indice["temporadas"][temp] = {"temporada": temp, "fases": ["regular"], "fases_con_datos": ["regular"], "ligas": ligas}
        print(f"  {temp}: {len(df)} jugadores · A+B {int((df['fuente_norm'] == 'A+B').sum())} · sólo A "
              f"{int((df['fuente_norm'] == 'A').sum())} · con nacionalidad {int(df['nacionalidad'].notna().sum())}", flush=True)
    _dump(indice, sal / "normalizados" / "indice.json")
    # nacionalidad para la «Tabla de datos» (datos brutos): por player_uid y temporada
    if NACIONALIDADES.exists():
        nac = pd.read_csv(NACIONALIDADES, dtype={"player_id": str}).dropna(subset=["nacionalidad"])
        for temp, g in nac.groupby("temporada"):
            g = g.assign(player_uid=g["liga"] + ":" + g["player_id"])
            _dump(_columnar(g[["player_uid", "nacionalidad", "nacionalidad_fuente"]].drop_duplicates("player_uid")),
                  sal / temp / "nacionalidades.json")
    print("escrito", SALIDA_CSV, "y", sal)
