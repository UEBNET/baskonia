"""F10 · Impacto en pista y RAPM con la v5 (encargo §14.3).

Tres preguntas, con los datos que hay (el RAPM multiliga de la v4.0 necesita cachés que no están en el repositorio):

1. **Fiabilidad.** Correlación de una temporada a la siguiente del RAPM por liga-temporada (ridge λ = 1.500,
   `data/modelos/pista/<t>.csv`) frente a la de las medidas de la v5, en quienes siguen en la misma liga.
2. **¿Ganan con la capa de carrera y el grafo de ligas?** Predicción fuera de tiempo del RAPM de t+1 (lo que el Impacto
   necesita de un fichaje) con: (a) el RAPM de t; (b) el RAPM de t y t−1 con pesos aprendidos (la idea de la capa de
   carrera); (c) (b) + el perfil de nivel de la v5 en t (estado filtrado de la F4, sin ver t+1); (d) sólo el perfil.
   Para quien cambia de liga se añade la traducción de la v5 (Δλ de pts/100 del paso 2) y el cambio de liga.
3. **Puentes intra-temporada.** Jugadores con RAPM en dos ligas la misma temporada: ¿el RAPM del mismo jugador se
   parece entre ligas lo bastante para traducirlo?
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import RidgeCV

from bbnorm5 import config as C
from bbnorm5.medida import datos as DM

PISTA = C.RAIZ / "data" / "modelos" / "pista"
PERSONAS = C.DIR_DATOS / "limpios" / "entidades" / "personas_v5.csv"
NIVELES = C.DIR_DATOS / "carrera" / "niveles_carrera.parquet"
BASE = C.DIR_DATOS / "validacion" / "base_v5.parquet"
OBJ = ["rapm", "orapm", "drapm"]
PERFIL = ["pts_p100", "usg_pct", "ast_pct", "tov_pct", "oreb_pct", "dreb_pct", "stl_p100", "blk_pct", "t2_pct",
          "t3_pct", "tpar", "ftr", "pct_asistidas"]


def rapm_persona(min_pos: float) -> pd.DataFrame:
    """RAPM por persona v5, liga y temporada (media ponderada por posesiones si jugó en dos equipos)."""
    per = pd.read_csv(PERSONAS, dtype=str)[["fuente_liga", "fuente_id", "persona_v5"]].drop_duplicates(
        ["fuente_liga", "fuente_id"])
    partes = []
    for f in sorted(PISTA.glob("20*.csv")):
        d = pd.read_csv(f, usecols=["liga", "temporada", "player_id", "poss_on"] + OBJ, dtype={"player_id": str})
        partes.append(d)
    d = pd.concat(partes, ignore_index=True).merge(per, left_on=["liga", "player_id"],
                                                    right_on=["fuente_liga", "fuente_id"], how="inner")
    d = d[d["poss_on"] > 0]
    w = d["poss_on"]
    g = d.assign(**{f"{c}_w": d[c] * w for c in OBJ}).groupby(["persona_v5", "liga", "temporada"])
    r = g[[f"{c}_w" for c in OBJ] + ["poss_on"]].sum()
    for c in OBJ:
        r[c] = r[f"{c}_w"] / r["poss_on"]
    r = r[OBJ + ["poss_on"]].reset_index()
    r["anio"] = r["temporada"].str[:4].astype(int)
    return r[r["poss_on"] >= min_pos]


def perfil_v5() -> pd.DataFrame:
    """Nivel filtrado de la F4 (η = μ + nivel, sin ver temporadas posteriores) en columnas, por persona-liga-temporada."""
    n = pd.read_parquet(NIVELES, columns=["persona_v5", "liga", "temporada", "metrica", "mu", "nivel_carrera"])
    n = n[n["metrica"].isin(PERFIL)]
    n["eta"] = n["mu"] + n["nivel_carrera"]
    p = n.pivot_table(index=["persona_v5", "liga", "temporada"], columns="metrica", values="eta").reset_index()
    p.columns = [c if c in ("persona_v5", "liga", "temporada") else f"v5_{c}" for c in p.columns]
    return p


# ------------------------------------------------------------------ 1. fiabilidad
def fiabilidad(r: pd.DataFrame) -> pd.DataFrame:
    a = r.merge(r.assign(anio=r["anio"] - 1), on=["persona_v5", "liga", "anio"], suffixes=("", "_sig"))
    filas = [{"medida": c, "fuente": "RAPM por liga-temporada", "pares": len(a),
              "r": float(np.corrcoef(a[c], a[f"{c}_sig"])[0, 1])} for c in OBJ]
    n = pd.read_parquet(NIVELES, columns=["persona_v5", "liga", "temporada", "metrica", "y", "v"])
    n = n[n["metrica"].isin(PERFIL)]
    n["anio"] = n["temporada"].str[:4].astype(int)
    keys = a[["persona_v5", "liga", "anio"]].drop_duplicates()
    for m, g in n.groupby("metrica"):
        g = g.merge(keys, on=["persona_v5", "liga", "anio"])
        b = g.merge(n[n["metrica"] == m].assign(anio=lambda x: x["anio"] - 1)[["persona_v5", "liga", "anio", "y"]],
                    on=["persona_v5", "liga", "anio"], suffixes=("", "_sig"))
        filas.append({"medida": m, "fuente": "medida v5 (F3)", "pares": len(b),
                      "r": float(np.corrcoef(b["y"], b["y_sig"])[0, 1])})
    return pd.DataFrame(filas)


# ------------------------------------------------------------------ 2. predicción del RAPM de t+1
def transiciones(r: pd.DataFrame, p: pd.DataFrame) -> pd.DataFrame:
    """Persona en t (liga de más posesiones) → t+1 (liga de más posesiones), con RAPM de t−1 si existe y perfil v5 en t."""
    top = r.sort_values("poss_on", ascending=False).drop_duplicates(["persona_v5", "anio"])
    x = top.merge(top.assign(anio=top["anio"] - 1), on=["persona_v5", "anio"], suffixes=("", "_sig"))
    x["anio_sig"] = x["anio"] + 1
    prev = top.assign(anio=top["anio"] + 1)[["persona_v5", "anio", "liga"] + OBJ + ["poss_on"]]
    x = x.merge(prev, on=["persona_v5", "anio"], how="left", suffixes=("", "_ant"))
    x = x.merge(p, on=["persona_v5", "liga", "temporada"], how="left")
    x["cambia"] = (x["liga"] != x["liga_sig"]).astype(float)
    # traducción v5 (paso 2) de pts/100 para quien cambia, de la base de la F8 (sin fugas: estimada con años anteriores)
    b = pd.read_parquet(BASE, columns=["persona_v5", "anio_obj", "metrica", "liga", "liga_ult", "delta_lambda"])
    b = b[b["metrica"] == "pts_p100"].drop_duplicates(["persona_v5", "anio_obj", "liga"])
    x = x.merge(b.rename(columns={"anio_obj": "anio_sig", "liga": "liga_sig", "liga_ult": "liga_b"})[
        ["persona_v5", "anio_sig", "liga_sig", "delta_lambda"]], on=["persona_v5", "anio_sig", "liga_sig"], how="left")
    x["delta_lambda"] = x["delta_lambda"].fillna(0.0)
    return x


def _X(x: pd.DataFrame, conjunto: str, obj: str) -> np.ndarray:
    cols = []
    if conjunto in ("t", "carrera", "carrera_perfil", "carrera_perfil_grafo"):
        cols.append(x[obj].to_numpy(float))
        cols.append(np.log(x["poss_on"].to_numpy(float)) * x[obj].to_numpy(float))
    if conjunto in ("carrera", "carrera_perfil", "carrera_perfil_grafo"):
        tiene = x[f"{obj}_ant"].notna().to_numpy(float)
        cols += [x[f"{obj}_ant"].fillna(0).to_numpy(float), tiene,
                 tiene * (x["liga_ant"] != x["liga"]).to_numpy(float) * x[f"{obj}_ant"].fillna(0).to_numpy(float)]
    if conjunto in ("carrera_perfil", "perfil", "carrera_perfil_grafo"):
        cols += [x[f"v5_{m}"].to_numpy(float) for m in PERFIL]
    if conjunto in ("carrera_perfil_grafo",):
        cols += [x["cambia"].to_numpy(float), x["delta_lambda"].to_numpy(float),
                 x["cambia"].to_numpy(float) * x[obj].to_numpy(float)]
    return np.column_stack(cols)


CONJUNTOS = ["t", "carrera", "carrera_perfil", "carrera_perfil_grafo", "perfil"]


def prediccion(cfg: dict, x: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    I = cfg["impacto"]
    x = x[x[[f"v5_{m}" for m in PERFIL]].notna().all(axis=1)].reset_index(drop=True)
    preds = []
    for obj in OBJ:
        for T in I["cortes"]:
            tr, te = x[x["anio_sig"] < T], x[x["anio_sig"] == T]
            if te.empty or len(tr) < 500:
                continue
            fila = te[["persona_v5", "anio_sig", "liga", "liga_sig", "cambia", f"{obj}_sig"]].rename(
                columns={f"{obj}_sig": "y"}).assign(objetivo=obj)
            for cj in CONJUNTOS:
                Xtr, Xte = _X(tr, cj, obj), _X(te, cj, obj)
                mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
                m = RidgeCV(alphas=np.logspace(-2, 3, 12)).fit((Xtr - mu) / sd, tr[f"{obj}_sig"].to_numpy(float))
                fila[cj] = m.predict((Xte - mu) / sd)
            preds.append(fila)
    P = pd.concat(preds, ignore_index=True)
    rng = np.random.default_rng(cfg["semilla"] + 3)
    filas = []
    for (obj, grupo), g in [((o, "todos"), P[P["objetivo"] == o]) for o in OBJ] + \
            [((o, "siguen"), P[(P["objetivo"] == o) & (P["cambia"] == 0)]) for o in OBJ] + \
            [((o, "cambian"), P[(P["objetivo"] == o) & (P["cambia"] == 1)]) for o in OBJ]:
        u, inv = np.unique(g["persona_v5"], return_inverse=True)
        base = {cj: stats.spearmanr(g[cj], g["y"]).statistic for cj in CONJUNTOS}
        bs = {cj: [] for cj in CONJUNTOS}
        for _ in range(cfg["bootstrap"] // 5):
            sel = np.repeat(np.arange(len(g)), np.bincount(rng.integers(0, len(u), len(u)), minlength=len(u))[inv])
            for cj in CONJUNTOS:
                bs[cj].append(stats.spearmanr(g[cj].to_numpy()[sel], g["y"].to_numpy()[sel]).statistic)
        mse0 = float(np.mean((g["t"] - g["y"]) ** 2))
        for cj in CONJUNTOS:
            dif = np.array(bs[cj]) - np.array(bs["t"])
            filas.append({"objetivo": obj, "grupo": grupo, "conjunto": cj, "casos": len(g), "spearman": base[cj],
                          "dif_frente_t": base[cj] - base["t"], "ic_lo": float(np.quantile(dif, .025)),
                          "ic_hi": float(np.quantile(dif, .975)),
                          "mse_rel": float(np.mean((g[cj] - g["y"]) ** 2)) / mse0})
    return P, pd.DataFrame(filas)


# ------------------------------------------------------------------ 3. puentes
def puentes(r: pd.DataFrame, min_pos: float) -> tuple[pd.DataFrame, dict]:
    a = r[r["poss_on"] >= min_pos]
    m = a.merge(a, on=["persona_v5", "temporada"], suffixes=("_a", "_b"))
    m = m[m["liga_a"] < m["liga_b"]]
    res = {"jugadores_puente": int(len(m)), "pares_de_ligas": int(m.groupby(["liga_a", "liga_b"]).ngroups)}
    for c in OBJ:
        res[f"r_{c}"] = float(np.corrcoef(m[f"{c}_a"], m[f"{c}_b"])[0, 1]) if len(m) > 2 else np.nan
    t = m.groupby(["liga_a", "liga_b"]).apply(lambda g: pd.Series({
        "jugadores": len(g), "dif_rapm": (g["rapm_b"] - g["rapm_a"]).mean(),
        "se_dif": (g["rapm_b"] - g["rapm_a"]).std(ddof=1) / np.sqrt(len(g)) if len(g) > 1 else np.nan,
        "r_rapm": np.corrcoef(g["rapm_a"], g["rapm_b"])[0, 1] if len(g) > 2 else np.nan}), include_groups=False)
    return t.reset_index().sort_values("jugadores", ascending=False), res


def ejecutar(cfg: dict) -> dict:
    I = cfg["impacto"]
    out_dir = C.dir_fase(cfg)
    r = rapm_persona(I["min_posesiones"])
    f = fiabilidad(r)
    x = transiciones(r, perfil_v5())
    P, t = prediccion(cfg, x)
    pu, rp = puentes(rapm_persona(I["min_posesiones_puente"]), I["min_posesiones_puente"])
    f.to_csv(out_dir / "impacto_fiabilidad.csv", index=False)
    t.to_csv(out_dir / "impacto_prediccion.csv", index=False)
    pu.to_csv(out_dir / "impacto_puentes.csv", index=False)
    res = {"fiabilidad": f.set_index("medida")["r"].round(3).to_dict(),
           "prediccion": t[t["grupo"].isin(["siguen", "cambian"]) & (t["objetivo"] == "rapm")][
               ["grupo", "conjunto", "casos", "spearman", "dif_frente_t", "ic_lo", "ic_hi"]].round(3).to_dict("records"),
           "puentes": rp}
    C.escribir_json({**C.metadatos(cfg, [NIVELES, BASE, PERSONAS]), **res}, out_dir / "meta_impacto.json")
    return res
