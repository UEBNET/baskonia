"""Datos de la pestaña «Quintetos y conexiones» de la Mesa (y del apartado «Conexiones» de la ficha).

Un fichero por liga y temporada, JSON comprimido con gzip y en base64 (el Artifact sólo sirve tipos de texto):
<salida>/quintetos/datos/<temp>/<liga>.gz.txt (la página lo decodifica y descomprime en el navegador). Índice: <salida>/quintetos/datos/indice.json.

Contenido (tablas en formato columnar {"c": [columnas], "f": [[fila], ...]}; jugadores por índice):
  jugadores      id, nombre, equipo, posición del estudio y, si existen, nivel L, contexto, estilo VaDE y RAPM
                 traducido a la EuroLeague (algoritmos A+B)
  equipos        equipos.csv (estructura de quintetos y rotación), las tres fases
  on_off         jugadores.csv: on/off, RAPM, clutch, basura, rotación, red de pases; + zonas de tiro (pista)
  quintetos      quintetos con 10+ minutos (todas las fases)
  trios          los 20 tríos con más minutos de cada equipo y fase
  parejas        parejas con 40+ minutos (regular y total)
  asistencias    pasador → anotador con 2+ asistencias
  efectos        X → Y (con Y en pista: cambio de su cuota de tiro, eFG%, % asistidas, % en el aro y puntos/100
                 cuando X está en pista frente a cuando no), temporada regular, 60+ minutos juntos
  cobertura      partidos, con quintetos, validados y usados
"""
from __future__ import annotations

import glob
import base64
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
DIR_PROC = RAIZ / "data" / "processed"
DIR_MOD = RAIZ / "data" / "modelos"
NOMBRES_LIGA = {"euroleague": "EuroLeague", "eurocup": "EuroCup", "acb": "Liga Endesa", "nba": "NBA",
                "gleague": "G League", "lba": "LBA", "bbl": "BBL", "lnb": "LNB"}
FASES = ["regular", "playoffs", "total"]

UNIDAD = ["fase", "gp", "min", "poss", "pts_for", "pts_against", "plus_minus", "ortg", "drtg", "net_rtg",
          "net_rtg_aj", "net_rtg_suerte", "ritmo", "efg_pct", "opp_efg_pct", "tov_pct", "opp_tov_pct", "oreb_pct",
          "dreb_pct", "ft_rate", "opp_ft_rate", "fg3a_rate", "opp_fg3a_rate", "ast_pct", "min_clutch", "min_basura"]
Q_EXTRA = ["rapm_suma", "net_esperado", "sinergia"]
T_EXTRA = ["net_esperado", "sinergia_rapm"]
P_COLS = ["fase", "min", "poss", "ortg", "drtg", "net_rtg", "net_rtg_aj", "min_a_sin_b", "net_rtg_aj_a_sin_b",
          "min_b_sin_a", "net_rtg_aj_b_sin_a", "min_ninguno", "net_rtg_aj_ninguno", "sinergia", "sinergia_rapm",
          "net_esperado", "pct_min_a_con_b", "pct_min_b_con_a", "ast_a_a_b", "ast_b_a_a"]
J_COLS = ["fase", "gp", "min_on", "poss_on", "min_pct_equipo", "quintetos_distintos", "titular_partidos",
          "cierra_partidos", "relevos_por_partido", "min_por_relevo", "pct_min_q1", "pct_min_q2", "pct_min_q3",
          "pct_min_q4", "pct_min_prorroga", "net_rtg_on", "net_rtg_off", "net_rtg_onoff", "net_rtg_aj_onoff",
          "net_rtg_suerte_onoff", "ortg_onoff", "drtg_onoff", "efg_pct_onoff", "opp_efg_pct_onoff", "tov_pct_onoff",
          "opp_tov_pct_onoff", "oreb_pct_onoff", "dreb_pct_onoff", "ritmo_onoff", "clutch_min", "clutch_net_rtg",
          "basura_min", "net_rtg_onoff_sin_basura", "orapm", "drapm", "rapm", "rapm_poss", "ast_dadas",
          "ast_recibidas", "pct_canastas_asistidas", "pts_generados_asist", "socios_asistencia", "hhi_asistencias",
          "pagerank_asistencias"]
ZONAS = ["aro", "corta", "media", "t3_esquina", "t3_frontal"]
E_COLS = ["fga_con", "fga_sin", "sec_con", "d_cuota_tiro", "d_efg", "d_pct_asistidas", "d_pct_aro", "d_pts100"]


def _num(v, nd=2):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    if not np.isfinite(f):
        return None
    r = round(f, nd)
    return int(r) if r == int(r) and abs(r) < 1e15 else r


def _tabla(df: pd.DataFrame, cols: list[str], nd: dict | None = None) -> dict:
    nd = nd or {}
    filas = []
    for row in df[cols].itertuples(index=False):
        filas.append([_num(v, nd.get(c, 2)) if not isinstance(v, str) else v for c, v in zip(cols, row)])
    return {"c": cols, "f": filas}


def _leer(p: Path, **kw) -> pd.DataFrame:
    return pd.read_csv(p, **kw) if p.exists() else pd.DataFrame()


def _opcional(ruta: str, temporada: str) -> pd.DataFrame:
    p = DIR_MOD / ruta.format(t=temporada)
    return pd.read_csv(p, dtype={"player_id": str, "team_id": str}, low_memory=False) if p.exists() else pd.DataFrame()


def exportar_liga(liga: str, temporada: str, extras: dict) -> dict | None:
    d = DIR_PROC / temporada / "quintetos" / liga
    if not d.exists():
        return None
    ids = {"dtype": {"team_id": str, "player_id": str}}
    jug = _leer(d / "jugadores.csv", **ids)
    if jug.empty:
        return None
    q5 = _leer(d / "quintetos.csv.gz", dtype={"team_id": str, "unidad": str})
    q3 = _leer(d / "trios.csv.gz", dtype={"team_id": str, "unidad": str})
    pa = _leer(d / "parejas.csv.gz", dtype={"team_id": str, "jugador_a_id": str, "jugador_b_id": str})
    asi = _leer(d / "asistencias.csv", dtype={"team_id": str, "pasador_id": str, "receptor_id": str})
    eqp = _leer(d / "equipos.csv", dtype={"team_id": str})
    val = _leer(d / "validacion.csv")

    # catálogo de jugadores (índice compacto)
    base = jug.sort_values("min_on", ascending=False).drop_duplicates(["team_id", "player_id"])
    pids = list(dict.fromkeys(base["player_id"]))
    pix = {p: i for i, p in enumerate(pids)}
    nombres = jug.drop_duplicates("player_id").set_index("player_id")["nombre"]
    equipos_nombre = jug.drop_duplicates("team_id").set_index("team_id")["equipo"].to_dict()
    cat = pd.DataFrame({"player_id": pids, "nombre": [nombres.get(p, p) for p in pids]})
    # equipo principal (más minutos en la temporada regular, o en total)
    princ = (jug.sort_values("min_on", ascending=False).drop_duplicates("player_id").set_index("player_id")["team_id"])
    cat["team_id"] = cat["player_id"].map(princ)
    for nombre, df in extras.items():
        if nombre.startswith("_") or df.empty:
            continue
        m = df[(df["liga"] == liga) & (df["temporada"] == temporada)].drop(columns=["liga", "temporada"])
        m = m.drop_duplicates("player_id")
        cat = cat.merge(m, on="player_id", how="left")
    cat_cols = [c for c in cat.columns if c != "player_id"]
    cat_tab = _tabla(cat, ["player_id"] + cat_cols)

    def idx_unidad(u: str) -> list[int]:
        return [pix.get(p, -1) for p in str(u).split("|")]

    # on/off por jugador-equipo-fase + zonas
    on = jug.copy()
    on["j"] = on["player_id"].map(pix)
    zon = extras.get("_zonas")
    if zon is not None and not zon.empty:
        z = zon[(zon["liga"] == liga) & (zon["temporada"] == temporada)]
        on = on.merge(z.drop(columns=["liga", "temporada"]), on=["team_id", "player_id"], how="left")
    on_cols = ["j", "team_id"] + [c for c in J_COLS if c in on] + [c for c in on.columns if c.startswith(("fga_", "fgm_"))]
    on_cols = list(dict.fromkeys(on_cols))
    out = {"liga": liga, "nombre_liga": NOMBRES_LIGA.get(liga, liga), "temporada": temporada,
           "estilos_nombres": extras.get("_estilos_nombres"),
           "equipos_nombre": equipos_nombre, "jugadores": cat_tab,
           "on_off": _tabla(on, on_cols, {"pagerank_asistencias": 4}),
           "equipos": _tabla(eqp, list(eqp.columns)) if not eqp.empty else None}
    if not q5.empty:
        q = q5[q5["min"] >= 10].copy()
        q["u"] = q["unidad"].map(idx_unidad)
        cols = ["team_id", "u"] + [c for c in UNIDAD + Q_EXTRA if c in q]
        out["quintetos"] = _tabla(q, cols)
    if not q3.empty:
        t = q3.sort_values("min", ascending=False).groupby(["team_id", "fase"]).head(20).copy()
        t["u"] = t["unidad"].map(idx_unidad)
        out["trios"] = _tabla(t, ["team_id", "u"] + [c for c in UNIDAD + T_EXTRA if c in t])
    if not pa.empty:
        p = pa[(pa["min"] >= 40) & pa["fase"].isin(["regular", "total"])].copy()
        p["a"] = p["jugador_a_id"].map(pix); p["b"] = p["jugador_b_id"].map(pix)
        out["parejas"] = _tabla(p, ["team_id", "a", "b"] + [c for c in P_COLS if c in p])
    if not asi.empty:
        a = asi[asi["ast"] >= 2].copy()
        a["p"] = a["pasador_id"].map(pix); a["r"] = a["receptor_id"].map(pix)
        a = a[a["p"].notna() & a["r"].notna()]
        out["asistencias"] = _tabla(a, ["team_id", "fase", "p", "r", "ast", "ast_2", "ast_3", "ast_tl", "pts_asistidos",
                                        "min_juntos", "ast_por40_juntos"])
    ef = extras.get("_efectos")
    if ef is not None and not ef.empty:
        e = ef[(ef["liga"] == liga) & (ef["temporada"] == temporada)].copy()
        e["xi"] = e["x"].map(pix); e["yi"] = e["y"].map(pix)
        e = e[e["xi"].notna() & e["yi"].notna()]
        out["efectos"] = _tabla(e, ["team_id", "xi", "yi"] + E_COLS, {"sec_con": 0})
    if not val.empty:
        cq = val["con_quintetos"].astype(str).str.lower() == "true"
        out["cobertura"] = {"partidos": int(len(val)), "con_quintetos": int(cq.sum()),
                            "validados": int((val["valido"].astype(str).str.lower() == "true")[cq].sum()),
                            "usados": int((val["usado_en_quintetos"].astype(str).str.lower() == "true").sum()),
                            "pm_oficial_incoherente": int((val.get("pm_oficial_coherente", pd.Series(True, index=val.index))
                                                           .astype(str).str.lower() == "false").sum())}
    return out


def extras_globales() -> dict:
    """Tablas opcionales por jugador-liga-temporada (si los modelos ya se han ejecutado)."""
    ex = {}
    # los modelos usan en la BBL el id «n:<nombre>»; el jugada a jugada, el de la fuente: tabla de paso
    mapa = None
    fr_ctx = [pd.read_csv(p, dtype={"player_id": str, "pid_modelo": str}, usecols=["liga", "temporada", "player_id", "pid_modelo", "min"])
              for p in sorted(glob.glob(str(DIR_MOD / "contexto" / "20*.csv")))]
    if fr_ctx:
        mapa = (pd.concat(fr_ctx, ignore_index=True).sort_values("min", ascending=False)
                .drop_duplicates(["liga", "temporada", "player_id"])[["liga", "temporada", "player_id", "pid_modelo"]])

    def a_fuente(df: pd.DataFrame) -> pd.DataFrame:
        if mapa is None:
            return df
        d = df.rename(columns={"player_id": "pid_modelo"}).merge(mapa, on=["liga", "temporada", "pid_modelo"], how="inner")
        return d.drop(columns=["pid_modelo"])

    ctx = DIR_MOD / "contexto" / "por_jugador_liga.csv"
    if ctx.exists():
        c = pd.read_csv(ctx, dtype={"player_id": str})
        ex["contexto"] = a_fuente(c[["liga", "temporada", "player_id", "L", "ctx_comp", "ctx_riv", "ctx_plantilla",
                                     "ctx_comp_dev", "ctx_plantilla_dev"]])
    zonas = []
    for p in sorted(glob.glob(str(DIR_MOD / "pista" / "*.csv"))):
        z = pd.read_csv(p, dtype={"team_id": str, "player_id": str})
        zonas.append(z[["liga", "temporada", "team_id", "player_id"] + [f"{a}_{b}" for b in ZONAS for a in ("fga", "fgm")]])
    if zonas:
        ex["_zonas"] = pd.concat(zonas, ignore_index=True)
    efs = sorted(glob.glob(str(DIR_MOD / "interacciones" / "efectos_*.csv.gz")))
    if efs:
        ex["_efectos"] = pd.concat([pd.read_csv(p, dtype={"team_id": str, "x": str, "y": str}) for p in efs],
                                   ignore_index=True)
    est = DIR_MOD / "estilos" / "vade" / "jugadores.csv"
    if est.exists():
        e = pd.read_csv(est, dtype={"player_id": str})
        e = e.sort_values("min", ascending=False).drop_duplicates(["liga", "temporada", "player_id"])
        ex["estilo"] = a_fuente(e[["liga", "temporada", "player_id", "estilo", "p_estilo", "x", "y", "z"]].rename(
            columns={"x": "mx", "y": "my", "z": "mz"}))
    norm = sorted(glob.glob(str(DIR_MOD / "normalizado" / "*.csv")))
    if norm:
        cols = ["liga", "temporada", "player_id", "pos3", "edad", "rapm", "orapm", "drapm", "rapm_pctel"]
        fr = []
        for p in norm:
            n = pd.read_csv(p, dtype={"player_id": str}, low_memory=False)
            keep = [c for c in cols if c in n]
            n = n[keep].rename(columns={"rapm": "rapm_el", "orapm": "orapm_el", "drapm": "drapm_el", "rapm_pctel": "rapm_pct_el"})
            fr.append(n)
        ex["normalizado"] = pd.concat(fr, ignore_index=True)
    cfg = RAIZ / "config" / "estilos.json"
    if cfg.exists():
        cfg_d = {k: v for k, v in json.loads(cfg.read_text(encoding="utf-8")).items() if not k.startswith("_")}
        ex["_estilos_nombres"] = {k: {"nombre": v["nombre"], "resumen": v.get("resumen", ""), "color": COLORES_ESTILO[i % 6]}
                                  for i, (k, v) in enumerate(sorted(cfg_d.items()))}
    return ex


# mismos colores que el Atlas de Estilos (E01…E06)
COLORES_ESTILO = ["#3b7fe0", "#e8702f", "#1fae7e", "#e3a51a", "#e27aa8", "#7b68ee"]


def main(salida: str = "data/artifact") -> None:
    raiz = Path(salida) / "quintetos" / "datos"
    ex = extras_globales()
    indice = {"generado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "temporadas": {}}
    for tdir in sorted(DIR_PROC.iterdir(), reverse=True):
        if not (tdir / "quintetos").exists():
            continue
        temp = tdir.name
        for ldir in sorted((tdir / "quintetos").iterdir()):
            d = exportar_liga(ldir.name, temp, ex)
            if not d:
                continue
            p = raiz / temp / f"{ldir.name}.gz.txt"
            p.parent.mkdir(parents=True, exist_ok=True)
            data = json.dumps(d, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            p.write_bytes(base64.b64encode(gzip.compress(data, 9)))
            indice["temporadas"].setdefault(temp, {})[ldir.name] = {
                "nombre": NOMBRES_LIGA.get(ldir.name, ldir.name), "bytes": p.stat().st_size,
                "quintetos": bool(d.get("quintetos")), "cobertura": d.get("cobertura")}
            print(f"{temp} {ldir.name}: {p.stat().st_size / 1024:.0f} KB ({len(data) / 1024:.0f} KB sin comprimir)")
    (raiz / "indice.json").write_text(json.dumps(indice, ensure_ascii=False, indent=1), encoding="utf-8")
