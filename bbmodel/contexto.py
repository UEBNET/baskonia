"""Contexto de nivel: con quién y contra quién juega cada jugador, en la vara EuroLeague.

No es lo mismo promediar 15 puntos al lado del MVP de la EuroLeague que en un equipo de la BBL. Esta
capa mide el NIVEL de los compañeros y de los rivales con los que cada jugador ha compartido pista y
cuánto cambia cada métrica normalizada cuando cambia ese entorno, para poder:
  * quitar a sus números normalizados la parte que se debe a su entorno (contexto «EuroLeague medio»), y
  * proyectarlos al entorno de un equipo concreto de la EuroLeague (Atlas: simular fichajes).

1. Nivel de cada jugador-liga-temporada: el índice L del Atlas de Estilos (media de los z con signo de PER,
   Game Score/40, WS/40, ORtg, DRtg, puntos/100, TS% y eFG% normalizados A+B), con la misma escala
   (jugadores de 150+ minutos de las temporadas de entrenamiento, ponderados por minutos).
2. Contexto en pista (jugada a jugada): en cada tramo, la media de L de sus 4 compañeros y de los 5 rivales;
   media ponderada por los segundos de cada tramo. Jugadores sin L (muy pocos minutos): L medio de los
   jugadores de rotación corta (< 300 minutos) de su liga y temporada.
3. Contexto de plantilla: media de L de sus compañeros ponderada por sus minutos (sin él). Existe en todas
   las ligas y temporadas (también donde no hay quintetos: BBL 2020-23, LNB 2020-21).
4. Desviación: cada contexto menos el de un jugador medio de su liga y temporada (ponderado por minutos).
   La diferencia ENTRE ligas ya la recoge el tipo de cambio de A y B (los puentes cambian de liga y de
   compañeros a la vez); aquí sólo cuenta la diferencia DENTRO de la liga.
5. Sensibilidad β de cada métrica al contexto: regresión con efecto fijo de persona (el mismo jugador en
   distintos entornos) de su capacidad en la vara EuroLeague (`<m>_a` del algoritmo A) sobre la desviación
   del contexto de plantilla y la del contexto de rivales, con tramos de edad; pesos 1/varianza; error por
   bootstrap de personas. Se usa el contexto de PLANTILLA y no el de pista porque el de pista mezcla el rol:
   quien mejora pasa a jugar con los titulares y su contexto sube por su propio nivel.
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .datos import cargar_filas
from .enlace import tramo_edad
from .identidad import clave_nombre
from .metricas import CATALOGO

RAIZ = Path(__file__).resolve().parent.parent
DIR_PROC = RAIZ / "data" / "processed"
DIR_NORM = RAIZ / "data" / "modelos" / "normalizado"
DIR_A = RAIZ / "data" / "modelos" / "algoritmo_A" / "traducciones"
DIR_SALIDA = RAIZ / "data" / "modelos" / "contexto"
NIVEL = {"per": 1, "game_score_p40": 1, "ws_per_40": 1, "ortg": 1, "drtg": -1, "pts_p100": 1,
         "ts_pct": 1, "efg_pct": 1}
TEMPORADAS_ESCALA = ["2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
MIN_ESCALA = 150
MIN_BETA = 300


# ------------------------------------------------------------------------------------------ nivel
def _leer(d: Path, cols=None) -> pd.DataFrame:
    fr = [pd.read_csv(p, dtype={"player_id": str, "team_id": str}, low_memory=False, usecols=cols)
          for p in sorted(glob.glob(str(d / "*.csv")))]
    return pd.concat(fr, ignore_index=True)


def escala_nivel(norm: pd.DataFrame) -> dict:
    """Media y desviación (ponderadas por minutos) de las métricas de nivel en los jugadores de referencia."""
    ref = norm[norm["temporada"].isin(TEMPORADAS_ESCALA) & (norm["min"] >= MIN_ESCALA)]
    out = {}
    for c in NIVEL:
        x = ref[c].to_numpy(float); w = ref["min"].to_numpy(float); ok = np.isfinite(x)
        mu = np.average(x[ok], weights=w[ok])
        out[c] = (float(mu), float(np.sqrt(np.average((x[ok] - mu) ** 2, weights=w[ok]))))
    return out


def indice_nivel(df: pd.DataFrame, escala: dict) -> np.ndarray:
    Z = np.column_stack([NIVEL[c] * (df[c].to_numpy(float) - escala[c][0]) / escala[c][1] for c in NIVEL])
    ok = np.isfinite(Z)
    n = ok.sum(1)
    return np.where(n > 0, np.where(ok, Z, 0).sum(1) / np.maximum(n, 1), np.nan)


# ------------------------------------------------------------------------------------------ ids
def ids_modelo(filas: pd.DataFrame) -> pd.DataFrame:
    """(liga, temporada, team_id, player_id de la fuente) -> player_id del modelo (BBL: «n:<nombre>»)."""
    f = filas[["liga", "temporada", "team_id", "player_id", "nombre", "min"]].copy()
    f["pid_modelo"] = f["player_id"]
    bbl = f["liga"] == "bbl"
    claves = f.loc[bbl, "nombre"].map(clave_nombre)
    f.loc[bbl, "pid_modelo"] = np.where(claves.notna(), "n:" + claves.fillna(""), f.loc[bbl, "player_id"])
    return f


# ------------------------------------------------------------------------------------------ contexto
def _tramos(liga: str, temporada: str) -> pd.DataFrame:
    p = DIR_PROC / temporada / "quintetos" / liga / "tramos.csv.gz"
    if not p.exists():
        return pd.DataFrame()
    t = pd.read_csv(p, usecols=["fase", "sec", "team_a", "team_b", "quinteto_a", "quinteto_b"],
                    dtype={"team_a": str, "team_b": str, "quinteto_a": str, "quinteto_b": str})
    return t[(t["fase"] == "regular") & (t["sec"] > 0) & t["quinteto_a"].notna() & t["quinteto_b"].notna()]


def contexto_pista(liga: str, temporada: str, L: dict, L_banquillo: float) -> pd.DataFrame:
    """Contexto en pista por (team_id, player_id de la fuente): media de L de compañeros y rivales."""
    t = _tramos(liga, temporada)
    if t.empty:
        return pd.DataFrame(columns=["team_id", "player_id", "sec_pista", "ctx_comp_pista", "ctx_riv_pista"])
    lv = lambda q: [L.get(p, L_banquillo) for p in q.split("|")]  # noqa: E731
    cache: dict[str, tuple[float, int]] = {}

    def suma(q):
        if q not in cache:
            v = lv(q)
            cache[q] = (float(np.sum(v)), len(v))
        return cache[q]

    filas = []
    for lado, otro in (("a", "b"), ("b", "a")):
        sA = t[f"quinteto_{lado}"].map(lambda q: suma(q)[0]).to_numpy()
        nA = t[f"quinteto_{lado}"].map(lambda q: suma(q)[1]).to_numpy()
        sB = t[f"quinteto_{otro}"].map(lambda q: suma(q)[0]).to_numpy()
        nB = t[f"quinteto_{otro}"].map(lambda q: suma(q)[1]).to_numpy()
        d = pd.DataFrame({"team_id": t[f"team_{lado}"].to_numpy(), "q": t[f"quinteto_{lado}"].to_numpy(),
                          "sec": t["sec"].to_numpy(float), "sA": sA, "nA": nA, "riv": sB / np.maximum(nB, 1)})
        d["player_id"] = d["q"].str.split("|")
        d = d.explode("player_id")
        d["Lp"] = d["player_id"].map(lambda p: L.get(p, L_banquillo))
        d["comp"] = (d["sA"] - d["Lp"]) / np.maximum(d["nA"] - 1, 1)
        filas.append(d[["team_id", "player_id", "sec", "comp", "riv"]])
    d = pd.concat(filas, ignore_index=True)
    d["wc"] = d["sec"] * d["comp"]; d["wr"] = d["sec"] * d["riv"]
    g = d.groupby(["team_id", "player_id"])[["sec", "wc", "wr"]].sum()
    return pd.DataFrame({"sec_pista": g["sec"], "ctx_comp_pista": g["wc"] / g["sec"],
                         "ctx_riv_pista": g["wr"] / g["sec"]}).reset_index()


def construir(guardar: bool = True) -> pd.DataFrame:
    """Contexto de cada jugador-equipo-temporada (temporada regular, todas las ligas)."""
    norm = _leer(DIR_NORM).copy()
    escala = escala_nivel(norm)
    norm["L"] = indice_nivel(norm, escala)
    filas = cargar_filas("regular")
    filas["min"] = pd.to_numeric(filas["min"], errors="coerce").fillna(0)
    filas = filas[filas["min"] > 0]
    ids = ids_modelo(filas)
    # el dataset normalizado usa el id de la fuente (también en la BBL); si no está, se busca por nombre
    Lm = norm.set_index(["liga", "temporada", "player_id"])["L"]
    Lm = Lm[~Lm.index.duplicated()]
    norm["_clave"] = norm["nombre"].map(clave_nombre)
    Ln = norm.dropna(subset=["_clave"]).set_index(["liga", "temporada", "_clave"])["L"]
    Ln = Ln[~Ln.index.duplicated()]
    ids["L"] = Lm.reindex(pd.MultiIndex.from_frame(ids[["liga", "temporada", "player_id"]])).to_numpy()
    falta = ids["L"].isna()
    ids.loc[falta, "L"] = Ln.reindex(pd.MultiIndex.from_arrays(
        [ids.loc[falta, "liga"], ids.loc[falta, "temporada"], ids.loc[falta, "nombre"].map(clave_nombre)])).to_numpy()
    out = []
    for (liga, temp), g in ids.groupby(["liga", "temporada"]):
        g = g.copy()
        corto = g[(g["min"] < 300) & g["L"].notna()]
        if len(corto):
            L_banq = float(np.average(corto["L"], weights=corto["min"]))
        else:
            L_banq = float(g["L"].mean()) if g["L"].notna().any() else -1.0
        g["L_usado"] = g["L"].fillna(L_banq)
        # plantilla: media de L de los compañeros ponderada por minutos (sin él)
        g["_wl"] = g["min"] * g["L_usado"]
        tot = g.groupby("team_id")[["_wl", "min"]].transform("sum")
        g["ctx_plantilla"] = (tot["_wl"] - g["_wl"]) / (tot["min"] - g["min"]).where(lambda s: s > 0)
        # pista: tramos (ids de la fuente)
        Lsrc = dict(zip(g["player_id"], g["L_usado"]))
        cp = contexto_pista(liga, temp, Lsrc, L_banq)
        g = g.merge(cp, on=["team_id", "player_id"], how="left")
        # rivales cuando no hay quintetos: media de la liga ponderada por minutos, sin su equipo
        tot_liga_wl, tot_liga_m = g["_wl"].sum(), g["min"].sum()
        eq = g.groupby("team_id")[["_wl", "min"]].sum()
        riv_plant = (tot_liga_wl - g["team_id"].map(eq["_wl"])) / (tot_liga_m - g["team_id"].map(eq["min"]))
        g["ctx_riv"] = g["ctx_riv_pista"].fillna(riv_plant)
        g["ctx_comp"] = g["ctx_comp_pista"].fillna(g["ctx_plantilla"])
        g["fuente_ctx"] = np.where(g["ctx_comp_pista"].notna(), "pista", "plantilla")
        for c in ("ctx_plantilla", "ctx_comp", "ctx_riv"):
            ok = g[c].notna()
            ref = float(np.average(g.loc[ok, c], weights=g.loc[ok, "min"])) if ok.any() else np.nan
            g[f"{c}_ref"] = ref
            g[f"{c}_dev"] = g[c] - ref
        g["L_banquillo"] = L_banq
        out.append(g.drop(columns=["_wl"]))
    df = pd.concat(out, ignore_index=True)
    if guardar:
        DIR_SALIDA.mkdir(parents=True, exist_ok=True)
        cols = ["liga", "temporada", "team_id", "player_id", "pid_modelo", "nombre", "min", "L", "L_usado",
                "ctx_plantilla", "ctx_plantilla_dev", "sec_pista", "ctx_comp_pista", "ctx_riv_pista",
                "ctx_comp", "ctx_comp_dev", "ctx_riv", "ctx_riv_dev", "fuente_ctx",
                "ctx_plantilla_ref", "ctx_comp_ref", "ctx_riv_ref", "L_banquillo"]
        for temp, g in df.groupby("temporada"):
            g[cols].round(4).to_csv(DIR_SALIDA / f"{temp}.csv", index=False)
        (DIR_SALIDA / "escala_nivel.json").write_text(json.dumps(escala, indent=1), encoding="utf-8")
    return df


def cargar() -> pd.DataFrame:
    return _leer(DIR_SALIDA)


# ------------------------------------------------------------------------------------------ sensibilidad
def por_jugador_liga(ctx: pd.DataFrame) -> pd.DataFrame:
    """Contexto por jugador-liga-temporada (ids del modelo), media ponderada por minutos de sus equipos."""
    c = ctx.copy()
    cols = ["L", "ctx_plantilla_dev", "ctx_comp_dev", "ctx_riv_dev", "ctx_plantilla", "ctx_comp", "ctx_riv"]
    for x in cols:
        c[f"_w_{x}"] = c[x] * c["min"]
        c[f"_m_{x}"] = c["min"].where(c[x].notna(), 0)
    g = c.groupby(["liga", "temporada", "pid_modelo"])
    out = pd.DataFrame({x: g[f"_w_{x}"].sum() / g[f"_m_{x}"].sum().replace(0, np.nan) for x in cols})
    out["min"] = g["min"].sum()
    return out.reset_index().rename(columns={"pid_modelo": "player_id"})


def _within(df: pd.DataFrame, cols: list[str], g: str, w: np.ndarray) -> pd.DataFrame:
    """Resta la media ponderada de cada persona (efecto fijo)."""
    out = df[cols].copy()
    ww = pd.Series(w, index=df.index)
    for c in cols:
        m = (df[c] * ww).groupby(df[g]).transform("sum") / ww.groupby(df[g]).transform("sum")
        out[c] = df[c] - m
    return out


def sensibilidad(ctx_jl: pd.DataFrame, n_boot: int = 50, semilla: int = 7) -> pd.DataFrame:
    """β de cada métrica (en desviaciones típicas de capacidad EuroLeague por unidad de nivel de contexto)."""
    trad = _leer(DIR_A)
    d = trad.merge(ctx_jl, on=["liga", "temporada", "player_id"], how="inner", suffixes=("", "_c"))
    d = d[(d["min"] >= MIN_BETA) & d["ctx_plantilla_dev"].notna()]
    d["tramo"] = (d["anio"] - d["anio_nac"]).map(tramo_edad)
    d = d[d.groupby("persona_id")["persona_id"].transform("size") >= 2]
    d["ctx_riv_dev"] = d["ctx_riv_dev"].fillna(0.0)
    tramos = pd.get_dummies(d["tramo"], prefix="t", dtype=float)
    tramos = tramos.drop(columns=[c for c in tramos.columns if c == "t_s/d"], errors="ignore")
    d = pd.concat([d, tramos], axis=1)
    X_cols = ["ctx_plantilla_dev", "ctx_riv_dev"] + list(tramos.columns)
    rng = np.random.default_rng(semilla)
    personas = d["persona_id"].unique()
    filas = []
    for col in CATALOGO:
        a, sd = f"{col}_a", f"{col}_a_sd"
        if a not in d:
            continue
        s = d[d[a].notna() & d[sd].notna()].copy()
        s = s[s.groupby("persona_id")["persona_id"].transform("size") >= 2]
        if len(s) < 200:
            continue
        w = 1.0 / (s[sd].to_numpy() ** 2 + 0.05)

        def ajuste(sub, ww):
            W = _within(sub, [a] + X_cols, "persona_id", ww)
            X = W[X_cols].to_numpy(float); y = W[a].to_numpy(float)
            sw = np.sqrt(ww)[:, None]
            b, *_ = np.linalg.lstsq(X * sw, y * sw[:, 0], rcond=None)
            res = y - X @ b
            r2 = 1 - np.average(res ** 2, weights=ww) / np.average(y ** 2, weights=ww)
            return b, r2

        b, r2 = ajuste(s, w)
        bs = []
        for _ in range(n_boot):
            el = pd.Series(rng.choice(personas, len(personas), replace=True)).value_counts()
            sb = s[s["persona_id"].isin(el.index)]
            rep = sb["persona_id"].map(el).to_numpy()
            sb = sb.loc[sb.index.repeat(rep)].copy()
            sb["persona_id"] = sb["persona_id"].astype(str) + "|" + sb.groupby(level=0).cumcount().astype(str)
            wb = 1.0 / (sb[sd].to_numpy() ** 2 + 0.05)
            bs.append(ajuste(sb, wb)[0][:2])
        bs = np.array(bs)
        m = CATALOGO[col]
        filas.append({"metrica": col, "nombre": m.nombre, "grupo": m.grupo, "sentido": m.sentido,
                      "beta_comp": float(b[0]), "beta_comp_se": float(bs[:, 0].std()),
                      "beta_riv": float(b[1]), "beta_riv_se": float(bs[:, 1].std()),
                      "r2_dentro": float(r2), "filas": int(len(s)), "personas": int(s["persona_id"].nunique())})
    return pd.DataFrame(filas)


def main(n_boot: int = 50) -> None:
    ctx = construir()
    jl = por_jugador_liga(ctx)
    jl.round(4).to_csv(DIR_SALIDA / "por_jugador_liga.csv", index=False)
    sens = sensibilidad(jl, n_boot=n_boot)
    sens.round(5).to_csv(DIR_SALIDA / "sensibilidad.csv", index=False)
    print(sens[["metrica", "beta_comp", "beta_comp_se", "beta_riv", "beta_riv_se", "r2_dentro", "personas"]]
          .round(3).to_string(index=False))
