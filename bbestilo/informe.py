"""Datos de la pestaña «Informe» del Atlas (lectura de fichaje en PDF): atlas/informe/<temporada>.json.

    python -m bbestilo informe --atlas <carpeta atlas/estilos> --datos <carpeta datos> --normalizado <carpeta> \\
                               --salida <carpeta atlas/informe>

Una entrada por jugador-club del Atlas (clave «persona_id|clave», la que busca la página: ifKey):
    m[métrica] = [valor en la vara Euroliga, valor en su liga, percentil, percentil del extremo bajo, del alto]
        * métricas normalizadas: <m> y <m>_obs del dataset normalizado; el percentil compara el valor Euroliga con el de
          los jugadores de su posición de la Euroliga de referencia (pool) y los extremos son los de <m>_lo/<m>_hi;
        * sin normalizar (PIE, STOP%, AST/TO, MIN%, on/off, triple frontal): [None, valor en su liga, percentil frente a
          los valores brutos del pool, None, None];
        * L (Nivel Cerno: columna «nivel» del Atlas) y AST%/USG% (cociente de las dos normalizadas): sin intervalo.
    b = la fila del jugador en la tabla de datos (temporada regular), sin vacíos.
    fn = fuente de la normalización (fuente_norm del dataset).
Pool de referencia: jugadores de la Euroliga de esa temporada (de la última completa si la temporada es provisional)
con ≥ 300 min, por posición (E, A, I; «*» todos). ref[pos][m] = [p10, p50, p90, n]. ritmo_el = ritmo de la Euroliga.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

NORMALIZADAS = ["rapm", "orapm", "drapm", "per", "ortg", "drtg", "ws_per_40", "game_score_p40", "pts_p100", "usg_pct",
                "ts_pct", "efg_pct", "fg2_pct", "fg3_pct", "ft_pct", "fg3a_rate", "fta_rate", "ast_pct", "tov_pct",
                "oreb_pct", "dreb_pct", "oreb_p100", "dreb_p100", "stl_pct", "blk_pct", "stl_p100", "blk_p100",
                "pf_p100", "pct_aro", "pct_corta", "pct_media", "pct_t3_esquina", "pct_asistidas"]
BRUTAS = {"pie": "pie", "stop_pct": "stop_pct", "ast_to": "ast_to", "pct_t3_frontal": "q_pct_t3_frontal",
          "onoff": "q_onoff", "min_pct": "min_pct"}
CAJA = ["dorsal", "posicion", "equipo", "gp", "gs", "min", "min_pg", "pts_pg", "reb_pg", "oreb_pg", "dreb_pg", "ast_pg",
        "stl_pg", "blk_pg", "tov_pg", "pf_pg", "pfd_pg", "pir_pg", "plus_minus_pg", "pts_p40", "reb_p40", "ast_p40",
        "stl_p40", "blk_p40", "tov_p40", "ast_p100", "pts_p100", "fg2m", "fg2a", "fg3m", "fg3a", "ftm", "fta", "fg2_pct",
        "fg3_pct", "ft_pct", "ts_pct", "usg_pct", "per", "pie", "q_titular", "q_cierra", "q_pct_min_q4", "q_clutch_min",
        "q_clutch_net", "q_onoff", "q_rapm", "team_gp", "team_w", "team_l", "team_ortg", "team_drtg", "team_netrtg",
        "team_pace", "lg_pace", "edad", "altura_cm", "nacionalidad", "peso_kg", "fecha_nacimiento", "src_bpm", "src_obpm",
        "src_dbpm", "src_vorp", "src_fg_pct_00_03", "src_fg_pct_03_10", "src_fg_pct_10_16", "src_fg_pct_16_3p",
        "src_fg3_pct_corner", "src_pct_fga_00_03", "src_pct_fga_03_10", "src_pct_fga_10_16", "src_pct_fga_16_3p",
        "src_pct_fg3a_corner"]
MIN_POOL = 300


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _r(v, d=2):
    f = _num(v)
    return None if f is None else round(f, d)


def _leer_json(p: Path):
    import base64
    import gzip
    for q in (p, p.with_name(p.name + ".gz.txt")):
        if q.exists():
            t = q.read_text(encoding="utf-8").strip()
            return json.loads(gzip.decompress(base64.b64decode(t)) if t.startswith("H4sI") else t)
    raise FileNotFoundError(p)


def _tabla(obj) -> pd.DataFrame:
    return pd.DataFrame(obj["filas"], columns=obj["columnas"])


def _normalizado(carpeta: Path, temp: str) -> pd.DataFrame:
    p = carpeta / f"{temp}.csv.gz"
    p = p if p.exists() else carpeta / f"{temp}.csv"
    cols = ["liga", "player_id", "team_id", "fuente_norm", "min"] + [f"{m}{s}" for m in NORMALIZADAS for s in ("", "_lo", "_hi", "_obs")]
    d = pd.read_csv(p, dtype={"player_id": str, "team_id": str}, usecols=lambda c: c in cols, low_memory=False)
    d = d.drop_duplicates(["liga", "player_id", "team_id"])
    return d.rename(columns={c: f"N_{c}" for c in d.columns if c not in ("liga", "player_id", "team_id")})


def _pct(v, pool: np.ndarray):
    """Percentil (rango medio) de v entre los valores del pool."""
    if v is None or not len(pool):
        return None
    return int(round(100 * ((pool < v).sum() + 0.5 * (pool == v).sum()) / len(pool)))


def _emparejar(a: pd.DataFrame, t: pd.DataFrame) -> pd.DataFrame:
    """Fila de t (tabla de datos o dataset normalizado) de cada jugador del Atlas: mismo jugador (liga, id) y, si jugó
    en varios equipos, el mismo team_id o, si la clave del Atlas usa un código de club («c005»), los minutos más
    parecidos. Devuelve t reindexada en el orden de a (filas vacías si no hay pareja)."""
    t = t.reset_index(drop=True).assign(_t=lambda d: np.arange(len(d)))
    c = a[["liga", "pid", "team_id", "min"]].reset_index().merge(
        t[["liga", "player_id", "team_id", "_t", "_min"]].rename(columns={"player_id": "pid", "team_id": "team_t"}),
        on=["liga", "pid"], how="inner")
    c["_orden"] = np.where(c["team_id"] == c["team_t"], -1.0,
                           (pd.to_numeric(c["min"], errors="coerce") - pd.to_numeric(c["_min"], errors="coerce")).abs().fillna(1e9))
    c = c.sort_values(["index", "_orden"]).drop_duplicates("index")
    fila = pd.Series(-1, index=a.index).astype(int)
    fila.loc[c["index"].to_numpy()] = c["_t"].to_numpy()
    out = t.reindex(fila.to_numpy()).reset_index(drop=True)
    out.index = a.index
    return out.drop(columns=["_t"])


def _filas(atlas: pd.DataFrame, temp: str, datos: Path, norm: Path) -> pd.DataFrame:
    """Jugadores del Atlas de la temporada con su fila de la tabla de datos y del dataset normalizado."""
    a = atlas[atlas["temporada"] == temp].copy().reset_index(drop=True)
    a["team_id"] = a["clave"].str.split(":").str[1]
    a["pid"] = a["pid"].astype(str)
    try:                                      # ids de modelo («n:nombre», BBL) → id de la fuente
        from bbmodel.dataset_normalizado import _brutos
        b = _brutos(temp)
        mapa = {(l, str(m)): str(f) for l, m, f in zip(b["liga"], b["pid_modelo"], b["player_id_fuente"])}
        a["pid"] = [mapa.get((l, p), p) for l, p in zip(a["liga"], a["pid"])]
    except Exception:  # noqa: BLE001
        pass
    reg = _tabla(_leer_json(datos / temp / "regular.json"))
    reg["player_id"], reg["team_id"] = reg["player_id"].astype(str), reg["team_id"].astype(str)
    reg["_min"] = reg["min"]
    reg = reg.drop_duplicates(["liga", "player_id", "team_id"])
    n = _normalizado(norm, temp)
    n["_min"] = n["N_min"] if "N_min" in n else np.nan
    r = _emparejar(a, reg).drop(columns=["_min"])
    r = r.rename(columns={c: f"{c}_reg" for c in r.columns if c in a.columns or c in ("player_id",)})
    nn = _emparejar(a, n).drop(columns=["_min", "player_id", "team_id", "liga"])
    x = pd.concat([a, r, nn], axis=1)
    # métricas normalizadas (columnas N_ del dataset): Euroliga, su liga, extremo bajo y alto
    for m in NORMALIZADAS:
        for s in ("", "_lo", "_hi", "_obs"):
            if f"N_{m}{s}" not in x:
                x[f"N_{m}{s}"] = np.nan
    x = x.copy()
    num = lambda c: pd.to_numeric(x[c], errors="coerce")  # noqa: E731
    x["N_ast_usg"] = num("N_ast_pct") / num("N_usg_pct")
    x["N_ast_usg_obs"] = num("N_ast_pct_obs") / num("N_usg_pct_obs")
    return x


def _pool(x: pd.DataFrame) -> dict:
    """Valores del pool (Euroliga, ≥ 300 min) por posición: normalizadas en la vara Euroliga y brutas en su liga."""
    el = x[(x["liga"] == "euroleague") & (pd.to_numeric(x["min_reg"], errors="coerce") >= MIN_POOL)]
    out = {}
    for pos in ("E", "A", "I", "*"):
        g = el if pos == "*" else el[el["pos3"] == pos]
        v = {"L": pd.to_numeric(g["nivel"], errors="coerce")}           # Nivel Cerno = «nivel» del Atlas
        for m in NORMALIZADAS + ["ast_usg"]:
            v[m] = pd.to_numeric(g[f"N_{m}"], errors="coerce")
        for k, c in BRUTAS.items():
            v[k] = pd.to_numeric(g[c], errors="coerce") if c in g else pd.Series(dtype=float)
        out[pos] = {k: s.dropna().to_numpy(float) for k, s in v.items()}
    return out


def construir(temp: str, atlas: pd.DataFrame, datos: Path, norm: Path, pool_de: str) -> dict:
    x = _filas(atlas, temp, datos, norm)
    xp = x if pool_de == temp else _filas(atlas, pool_de, datos, norm)
    P = _pool(xp)
    ref = {pos: {k: [_r(np.quantile(v, 0.1)), _r(np.quantile(v, 0.5)), _r(np.quantile(v, 0.9)), int(len(v))]
                 for k, v in P[pos].items() if len(v)} for pos in P}
    ritmo = pd.to_numeric(xp.loc[xp["liga"] == "euroleague", "lg_pace"], errors="coerce").dropna()
    j = {}
    for r in x.to_dict("records"):
        pos = r.get("pos3") if r.get("pos3") in ("E", "A", "I") else "*"
        pp = P[pos]
        m = {}
        L = _r(r.get("nivel"))
        m["L"] = [L, None, _pct(L, pp["L"]), None, None]
        for k in NORMALIZADAS:
            v, o, lo, hi = (_num(r.get(f"N_{k}{s}")) for s in ("", "_obs", "_lo", "_hi"))
            if v is None and o is None:
                continue
            m[k] = [_r(v), _r(o), _pct(v, pp[k]), _pct(lo, pp[k]), _pct(hi, pp[k])]
        v, o = _num(r.get("N_ast_usg")), _num(r.get("N_ast_usg_obs"))
        if v is not None or o is not None:
            m["ast_usg"] = [_r(v), _r(o), _pct(v, pp["ast_usg"]), None, None]
        for k, c in BRUTAS.items():
            o = _num(r.get(c))
            if o is not None:
                m[k] = [None, _r(o), _pct(o, pp[k]), None, None]
        b = {}
        for c in CAJA:
            v = r.get(f"{c}_reg") if f"{c}_reg" in r else r.get(c)     # columnas de la tabla de datos
            if v is None or (isinstance(v, float) and not math.isfinite(v)):
                continue
            b[c] = _r(v) if isinstance(v, (int, float, np.floating, np.integer)) and not isinstance(v, bool) else v
        j[f"{r['persona_id']}|{r['clave']}"] = {"m": m, "b": b, "fn": r.get("N_fuente_norm") if isinstance(r.get("N_fuente_norm"), str) else None}
    return {"temporada": temp, "ritmo_el": _r(ritmo.median()) if len(ritmo) else None, "min_pool": MIN_POOL,
            "pool_de": pool_de, "pool_n": {pos: int(len(P[pos]["L"])) for pos in ("E", "A", "I")}, "ref": ref, "j": j}


def main(atlas: str, datos: str, normalizado: str, salida: str) -> dict:
    a = _tabla(_leer_json(Path(atlas) / "jugadores.json"))
    meta = _leer_json(Path(atlas) / "meta.json")
    provisionales = set(meta.get("temporadas_provisionales") or [])
    temps = sorted(a["temporada"].unique())
    completas = [t for t in temps if t not in provisionales]
    sal = Path(salida)
    sal.mkdir(parents=True, exist_ok=True)
    res = {}
    for t in temps:
        pool_de = t if t not in provisionales else max(completas)
        d = construir(t, a, Path(datos), Path(normalizado), pool_de)
        from .exportar import _sin_nan
        (sal / f"{t}.json").write_text(json.dumps(_sin_nan(d), ensure_ascii=False, separators=(",", ":"), allow_nan=False),
                                       encoding="utf-8")
        res[t] = {"jugadores": len(d["j"]), "pool_de": pool_de, "pool_n": d["pool_n"]}
        print(t, res[t], flush=True)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--atlas", required=True)
    ap.add_argument("--datos", required=True)
    ap.add_argument("--normalizado", required=True)
    ap.add_argument("--salida", required=True)
    a = ap.parse_args()
    main(a.atlas, a.datos, a.normalizado, a.salida)
