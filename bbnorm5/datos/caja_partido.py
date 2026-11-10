"""F2 · Caja jugador-partido derivada de los brutos (dependencia D1 de la F0), sin modificar la extracción.

Los adaptadores basados en boxscores (ACB, BBL, CBA, FEB, GBL, BSL, BNXT, BCL, FEC, LBA, NCAA) construyen una lista de
partidos en formato estándar (`bbstats/adapters/boxscore.py`) y la agregan con `aggregate_by_phase`. Aquí se repite
exactamente el reproceso sin red de `bbstats.pipeline._run_league` (`RawStore.load_season` + `build_adapter` +
`adapter.parse`), sustituyendo durante la llamada `aggregate_by_phase` por una envoltura que guarda la lista y llama a
la original. Así cada línea jugador-partido sale con los mismos nombres canónicos, ids y criterios que los totales de
`data/processed`, y la suma de las líneas reproduce esos totales (se comprueba en `comprobar`).

Las competiciones de agregados (EuroLeague, EuroCup, NBA, G League, LNB, NBL, VTB) no pasan por aquí: ver
`caja_partido_agregados` (jugada a jugada o boxscores en sus brutos `pbp_*`).

Salida: data/v5/limpios/caja_partido/<temporada>/<liga>.parquet, una fila por jugador × partido (jugó o no), con la
caja completa del jugador y los totales del equipo y del rival en ese partido.
"""
from __future__ import annotations

import importlib
import json
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd

from bbnorm5 import config as C

LIGAS_BOX = ["acb", "bbl", "cba", "feb1", "feb2", "feb3", "gbl", "bsl", "bnxt", "bcl", "fec", "lba", "ncaa", "nbl", "vtb"]
FECHA_APROXIMADA = {"bnxt", "bsl", "gbl"}     # fecha = modificación del fichero del partido (FIBA LiveStats)
CAMPOS_ID = ("name", "dorsal", "posicion", "nacionalidad", "altura_cm", "edad", "fecha_nacimiento")


@contextmanager
def _capturar(modulo):
    """Sustituye `aggregate_by_phase` en el módulo del adaptador mientras dura el bloque; devuelve la lista de partidos."""
    from bbstats.adapters import boxscore
    capturado: list = []
    original = getattr(modulo, "aggregate_by_phase")

    def envoltura(games, notes=None):
        capturado.extend(games)
        return boxscore.aggregate_by_phase(games, notes)

    setattr(modulo, "aggregate_by_phase", envoltura)
    try:
        yield capturado
    finally:
        setattr(modulo, "aggregate_by_phase", original)


@contextmanager
def _capturar_varios(modulos):
    from contextlib import ExitStack
    with ExitStack() as pila:
        caps = [pila.enter_context(_capturar(m)) for m in modulos]
        acumulado: list = []
        yield acumulado
        for c in caps:
            acumulado.extend(c)


def partidos(liga: str, temporada: str) -> tuple[list[dict], dict]:
    """Lista de partidos estándar de una liga-temporada desde su último bruto (sin red) y metadatos del bruto."""
    from bbstats.adapters import build_adapter
    from bbstats.config import load_config, resolve_path
    from bbstats.raw_store import RawStore
    cfg = load_config()
    lcfg = cfg["ligas"][liga]
    store = RawStore(resolve_path(cfg, "bruto"), compress=cfg.get("comprimir_bruto", False))
    ruta, doc = store.load_season(liga, temporada)
    if ruta is None:
        return [], {}
    adapter = build_adapter(liga, lcfg)
    # el módulo que llama a aggregate_by_phase puede ser el de una clase madre (NBL y VTB heredan de FIBA LiveStats)
    modulos = [importlib.import_module(k.__module__) for k in type(adapter).__mro__
               if k.__module__.startswith("bbstats.adapters")]
    modulos = [m for m in dict.fromkeys(modulos) if hasattr(m, "aggregate_by_phase")]
    if not modulos:
        raise ValueError(f"{liga}: el adaptador {type(adapter).__name__} no agrega boxscores")
    with _capturar_varios(modulos) as cap:
        adapter.parse(doc["payload"], temporada)
    meta = {"bruto": str(Path(ruta).relative_to(C.RAIZ)) if Path(ruta).is_relative_to(C.RAIZ) else str(ruta),
            "paquetes": len(doc["payload"].get("paquetes", [])) if isinstance(doc["payload"], dict) else 0,
            "fechas_bruto": (doc["payload"].get("fechas") or {}) if isinstance(doc["payload"], dict) else {}}
    return cap, meta


def completar_fechas(d: pd.DataFrame, liga: str, temporada: str, fechas_bruto: dict) -> pd.DataFrame:
    """Fecha de los partidos sin ella en el formato estándar (ACB, BNXT, BSL, GBL):
    1. `data/processed/<t>/entrenadores/<liga>_partidos.csv` si su fecha es ISO (ACB);
    2. si no, el campo `fechas` del bruto de FIBA LiveStats («Mon, 07 Oct 2024 19:06:51 GMT»). Es la fecha de
       modificación del fichero del partido, normalmente el mismo día o el siguiente: tolerancia de ±1 día, declarada.
    `fecha_origen` dice de dónde sale cada fecha."""
    if d.empty:
        return d
    ok = d["fecha"].astype(str).str.match(r"\d{4}-\d{2}-\d{2}")
    d["fecha_origen"] = np.where(ok, "boxscore", None)
    if ok.all():
        return d
    f = C.RAIZ / "data" / "processed" / temporada / "entrenadores" / f"{liga}_partidos.csv"
    if f.exists():
        e = pd.read_csv(f, usecols=["game_id", "fecha"], dtype=str).drop_duplicates("game_id")
        e = e[e["fecha"].astype(str).str.match(r"\d{4}-\d{2}-\d{2}")]
        m = d["game_id"].map(e.set_index("game_id")["fecha"].str[:10])
        sel = ~ok & m.notna()
        # en BNXT, BSL y GBL la fecha del calendario de entrenadores es la misma de modificación del fichero de
        # FIBA LiveStats (ya en ISO desde el 10-11-2026): sigue siendo aproximada
        origen = "modificacion_fichero" if liga in FECHA_APROXIMADA else "calendario"
        d.loc[sel, "fecha"], d.loc[sel, "fecha_origen"] = m[sel], origen
        ok = ok | sel
    if not ok.all() and fechas_bruto:
        fb = pd.to_datetime(pd.Series(fechas_bruto), errors="coerce", utc=True, format="%a, %d %b %Y %H:%M:%S %Z")
        fb = fb.dt.strftime("%Y-%m-%d")
        m = d["game_id"].map(fb)
        sel = ~ok & m.notna()
        d.loc[sel, "fecha"], d.loc[sel, "fecha_origen"] = m[sel], "modificacion_fichero"
    return d


def a_tabla(games: list[dict], liga: str, temporada: str) -> pd.DataFrame:
    """Una fila por jugador × partido. Columnas canónicas de bbstats (pts, fga, …, oreb, dreb, ast, stl, tov, blk, pf),
    min, starter, jugo, y los totales del equipo (team_*) y del rival (opp_*) en el partido."""
    from bbstats.adapters.boxscore import _played, _team_totals
    from bbstats.normalize import complete_counting
    from bbstats.schema import COUNTING_NAMES
    filas = []
    vistos = set()
    for g in games:
        sides = g.get("teams") or []
        if len(sides) != 2 or not g.get("final", True):
            continue
        gid = str(g.get("game_id"))
        if gid in vistos:                    # un partido repetido entre paquetes: se queda el primero (ya deduplicado)
            continue
        vistos.add(gid)
        tot = [_team_totals(s) for s in sides]
        for i, side in enumerate(sides):
            tid = str(side.get("team_id") or side.get("code") or side.get("name"))
            otid = str(sides[1 - i].get("team_id") or sides[1 - i].get("code") or sides[1 - i].get("name"))
            base = {"liga": liga, "temporada": temporada, "game_id": gid, "fecha": g.get("date"),
                    "fase": g.get("phase") or "regular", "team_id": tid, "equipo": side.get("name"), "opp_id": otid,
                    "local": i == 0}
            for k in COUNTING_NAMES:
                if k in tot[i]:
                    base[f"team_{k}"] = tot[i][k]
                if k in tot[1 - i]:
                    base[f"opp_{k}"] = tot[1 - i][k]
            for line in side.get("players") or []:
                ln = complete_counting(dict(line))
                f = dict(base)
                f["player_id"] = str(ln.get("player_id") or ln.get("name"))
                for k in CAMPOS_ID:
                    if ln.get(k) not in (None, ""):
                        f["nombre" if k == "name" else k] = ln[k]
                f["starter"] = ln.get("starter")
                f["jugo"] = bool(_played(ln))
                for k in COUNTING_NAMES:
                    if ln.get(k) is not None:
                        f[k] = float(ln[k])
                filas.append(f)
    d = pd.DataFrame(filas)
    if len(d):
        d["fecha"] = pd.to_datetime(d["fecha"], errors="coerce", utc=True).dt.tz_localize(None).dt.date.astype(str)
    return d


def comprobar(d: pd.DataFrame, liga: str, temporada: str, cols=("min", "pts", "fga", "fta", "oreb", "dreb", "ast",
                                                                 "stl", "tov", "blk", "pf")) -> dict:
    """Suma de las líneas por jugador-equipo y fase frente a data/processed/<t>/ligas/<liga>.csv (misma fase).
    Devuelve la fracción de jugador-equipo-fase con diferencia relativa < 1 % en cada columna."""
    f = C.RAIZ / "data" / "processed" / temporada / "ligas" / f"{liga}.csv"
    if not f.exists() or d.empty:
        return {}
    p = pd.read_csv(f, usecols=lambda c: c in {"fase", "player_id", "team_id", *cols}, low_memory=False,
                    dtype={"player_id": str, "team_id": str})
    out = {}
    for fase in ("regular", "playoffs"):
        s = d[(d["fase"] == fase) & d["jugo"]].groupby(["player_id", "team_id"])[[c for c in cols if c in d]].sum()
        q = p[p["fase"] == fase].set_index(["player_id", "team_id"])
        j = s.join(q, lsuffix="_caja", how="inner")
        if not len(j):
            continue
        r = {"filas_caja": int(len(s)), "filas_proc": int(len(q)), "emparejadas": int(len(j))}
        for c in cols:
            if f"{c}_caja" in j and c in j:
                a, b = j[f"{c}_caja"].astype(float), pd.to_numeric(j[c], errors="coerce")
                ok = b.notna()
                r[f"ok_{c}"] = float((np.abs(a[ok] - b[ok]) <= np.maximum(0.01 * np.abs(b[ok]), 0.51)).mean()) if ok.any() else None
        out[fase] = r
    return out


def construir(cfg: dict, ligas: list[str], temporadas: list[str]) -> pd.DataFrame:
    sal = C.DIR_DATOS / "limpios" / "caja_partido"
    resumen = []
    for t in temporadas:
        for liga in ligas:
            try:
                games, meta = partidos(liga, t)
            except Exception as exc:                  # noqa: BLE001 - se informa por liga
                resumen.append({"liga": liga, "temporada": t, "estado": f"error: {type(exc).__name__}: {exc}"[:300]})
                print(f"  {liga} {t}: error {exc}", flush=True)
                continue
            if not games:
                resumen.append({"liga": liga, "temporada": t, "estado": "sin bruto"})
                continue
            d = completar_fechas(a_tabla(games, liga, t), liga, t, meta.get("fechas_bruto") or {})
            (sal / t).mkdir(parents=True, exist_ok=True)
            d.to_parquet(sal / t / f"{liga}.parquet", index=False, compression="zstd")
            chk = comprobar(d, liga, t)
            fila = {"liga": liga, "temporada": t, "estado": "ok", "partidos": int(d["game_id"].nunique()),
                    "lineas": int(len(d)), "lineas_jugadas": int(d["jugo"].sum()),
                    "con_fecha": float(d["fecha"].astype(str).str.match(r"\d{4}-\d{2}-\d{2}").mean()),
                    "origen_fecha": ",".join(sorted(set(d["fecha_origen"].dropna()))), "bruto": meta.get("bruto")}
            for fase, r in chk.items():
                for k, v in r.items():
                    fila[f"{fase}_{k}"] = v
            resumen.append(fila)
            print(f"  {liga} {t}: {fila['partidos']} partidos, {fila['lineas_jugadas']} líneas jugadas · "
                  f"comprobación regular {json.dumps({k: v for k, v in chk.get('regular', {}).items() if k.startswith('ok_')})}",
                  flush=True)
    r = pd.DataFrame(resumen)
    return r
