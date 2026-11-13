"""v5.1 F3 · Nivel Kerno con la contribución de la F2 (encargo v5.1 §2; F10 §3.2).

NK = 100·E[F_ref(C)], con C = minutos del motor (recalibrados) × pts/100 combinados (v5 / v3.3), ensamblados con las
dependencias estimadas y la calibración final de la F2. F_ref y la calibración isotónica son las del NK vigente
(`bbequipo/anclas.py`, sólo lectura); el examen y la comparación, con el NK vigente reproducido en la F0, en los mismos
fichajes.

Tres lecturas para el producto:
- **número frontal:** el NK predictivo calibrado (el que mejor ordena, F10 §2.3);
- **rango del año:** el del NK calibrado (cuantiles 10–90 del percentil realizado por decil, como el vigente);
- **rango de nivel:** F_ref en los cuantiles 10 y 90 de C con los minutos esperados y el nivel de pts/100 (sin el ruido
  de la temporada): cuánto vale el jugador en esa liga y puesto.

**Sello** (regla de la F9, sobre pts/100 en la liga de destino): exposición acumulada frente a n*, temporadas de historial
y conectividad del par de ligas.
"""
from __future__ import annotations

import pickle

import numpy as np
import pandas as pd
from scipy import stats

from bbnorm5 import config as C
from bbnorm5.aguas_abajo import nivel_kerno as NK10
from bbnorm5.simulador51 import ensamblaje as EN
from bbnorm5.simulador51 import produccion as PR

NC_REPRODUCIDO = C.RAIZ / "experimentos" / "v5_1" / "F0" / "v40" / "anclas" / "nc_examen.csv.gz"


def _corte(anio: int) -> str:
    return f"{anio - 1}-{str(anio)[-2:]}"


def contribuciones(cfg: dict) -> tuple[pd.DataFrame, dict, dict]:
    """Casos de la F2 con draws de C (predictiva, calibrada) y de C de nivel, por temporada de destino."""
    S = cfg["ensamblaje"]["draws"]
    rng = np.random.default_rng(cfg["semilla"] + 3)
    d = EN.pits(EN.casos(cfg))
    # DT del nivel de pts/100 de la v5 (F8), en la escala del examen (el centro de la v5 fija la escala)
    d["sd_nivel"] = NK10._sd_nivel(d.assign(liga=d["liga_d"], **{f"{NK10.PP.MODELO}__q50": d["p5_q50"]}))
    partes, Cp, Cn = [], {}, {}
    for anio in sorted(d["anio"].unique()):
        t = d[d["anio"] == anio].reset_index(drop=True)
        dep = EN.dependencias(d, anio)
        s = EN.simular(t, dep, S, rng)
        sc = EN.escala_C(d, anio, S, rng, noms=("comb",))
        cp = EN._reescalar(s["C_comb"], sc["comb"])
        m_esp = s["M"].mean(axis=1, keepdims=True)
        nivel = t["pc_q50"].to_numpy(float)[:, None] + np.nan_to_num(t["sd_nivel"].to_numpy(float), nan=0.0)[:, None] * \
            rng.standard_normal((len(t), S))
        cn = m_esp / t["gm"].to_numpy(float)[:, None] * np.maximum(nivel, 0)
        t["pos_i"] = np.arange(len(t))
        partes.append(t)
        Cp[int(anio)], Cn[int(anio)] = cp, cn
    return pd.concat(partes, ignore_index=True), Cp, Cn


def sello(cfg: dict, d: pd.DataFrame) -> pd.Series:
    """Sello de la F9 para pts/100 de cada fichaje (exposición, historial y conectividad), con datos ≤ t."""
    from bbnorm5.salidas import destinos as DS
    reglas = C.cargar("configs/v5/f9.yaml")["sello"]
    b = pd.read_parquet(C.DIR_DATOS / "validacion" / "base_v5.parquet",
                        columns=["persona_v5", "anio_obj", "liga", "metrica", "temporadas_hist", "cl", "var_lambda"])
    b = b[b["metrica"] == "pts_p100"].drop_duplicates(["persona_v5", "anio_obj", "liga"])
    o = pd.read_parquet(C.DIR_DATOS / "carrera" / "observaciones.parquet", columns=["persona_v5", "temporada", "metrica", "N"])
    o = o[o["metrica"] == "pts_p100"].assign(anio=lambda x: x["temporada"].str[:4].astype(int))
    with open(C.DIR_DATOS / "ligas" / "lambda_paso2_modelos.pkl", "rb") as f:
        mods = pickle.load(f)
    nst = float(DS.n_estabilizacion()["pts_p100"])
    x = d[["persona_v5", "anio", "liga_d"]].merge(b.rename(columns={"anio_obj": "anio", "liga": "liga_d"}),
                                                    on=["persona_v5", "anio", "liga_d"], how="left")
    acum = [o.loc[(o["persona_v5"] == p) & (o["anio"] < a), "N"].sum() for p, a in zip(x["persona_v5"], x["anio"])]
    sd_entre = x["anio"].map(lambda a: float(np.std(mods[(a, "pts_p100", "encogido")]["lambda"]))
                             if (a, "pts_p100", "encogido") in mods else np.nan)
    conect = np.where(x["cl"].fillna(0) > 0, np.sqrt(x["var_lambda"].fillna(0)) / sd_entre, 0.0)
    return pd.Series(DS.sello(np.asarray(acum, float) / nst, x["temporadas_hist"].fillna(0).to_numpy(float),
                              np.nan_to_num(conect, nan=1.0), reglas), index=d.index)


def ejecutar(cfg: dict) -> dict:
    out = PR.dir_salida(cfg)
    AN, cfg_eq, roles, gm = NK10._referencias()
    d, Cp, Cn = contribuciones(cfg)
    nc = pd.read_csv(NC_REPRODUCIDO, low_memory=False, dtype={"team_d": str, "persona_id": str})
    d["corte"] = d["anio"].map(_corte)
    d["team_d"] = d["team_d"].astype(str)
    j = d.merge(nc, on=["persona_id", "liga_d", "team_d", "temporada_d", "corte"], how="inner", suffixes=("", "_nc"))
    filas = []
    for corte, g in j.groupby("corte"):
        F = AN.referencias_nc(cfg_eq, roles, corte, gm)
        a = int(g["anio"].iloc[0])
        for r in g.itertuples():
            Fr = F.get((r.liga_d, r.pos3)) or F.get((r.liga_d, None))
            if Fr is None or Fr.n < 30:
                continue
            i = int(r.pos_i)
            vp, lop, hip = AN.percentil_esperado(Fr, Cp[a][i])
            vn, lon, hin = AN.percentil_esperado(Fr, Cn[a][i])
            filas.append({"idx": r.Index, "NK51": vp, "NK51_lo80": lop, "NK51_hi80": hip,
                          "NK51_nivel": vn, "NK51_nivel_lo80": lon, "NK51_nivel_hi80": hin})
    k = j.join(pd.DataFrame(filas).set_index("idx"), how="inner")
    k["anio"] = k["corte"].str[:4].astype(int)
    cortes = sorted(k["anio"].unique())
    for v in ("NK51", "NK51_nivel"):
        x = (k.drop(columns=[c for c in k.columns if c.startswith("NC2")])
             .rename(columns={v: "X", f"{v}_lo80": "X_lo80", f"{v}_hi80": "X_hi80"})
             .pipe(lambda z: z.assign(NC2=z["X"], NC2_lo80=z["X_lo80"], NC2_hi80=z["X_hi80"])))
        x = AN.calibrar_nc(x, cortes, col="X")
        for suf in ("", "_lo80", "_hi80"):
            k[f"{v}{suf}_crudo"] = x[f"X{suf}_crudo"].to_numpy()
            k[f"{v}{suf}"] = x[f"X{suf}"].to_numpy()
    k = k[k["eval"]].copy()
    k["sello"] = sello(cfg, k.reset_index(drop=True)).to_numpy()
    k.round(3).to_csv(out / "nivel_kerno_examen.csv.gz", index=False)
    return resumir(cfg, k, AN)


def resumir(cfg: dict, k: pd.DataFrame, AN) -> dict:
    out = PR.dir_salida(cfg)
    rng = np.random.default_rng(cfg["semilla"] + 4)
    cols = ["NC1", "NK51", "NK51_nivel"]
    prueba = k[k["anio"] > k["anio"].min()]                  # calibrados con cortes anteriores
    res = {"fichajes": int(len(k)), "fichajes_prueba": int(len(prueba)), "cortes": sorted(k["corte"].unique().tolist())}
    for nom, x in (("prueba", prueba), ("todos", k)):
        r = {"spearman": NK10._spearman_boot(x, cols, cfg["bootstrap"] // 2, rng),
             "separacion": {c: AN.examen_separacion(x, c, "C_real", ["corte", "liga_d"], 10.0, 200, cfg["semilla"])
                            for c in cols},
             "cobertura80": {c: float(((x["pct_realizado"] >= x[f"{c}_lo80"]) & (x["pct_realizado"] <= x[f"{c}_hi80"])).mean())
                             for c in cols},
             "anchura80": {c: float((x[f"{c}_hi80"] - x[f"{c}_lo80"]).mean()) for c in cols},
             "error_abs": {c: float((x[c] - x["pct_realizado"]).abs().mean()) for c in cols}}
        res[nom] = r
    res["rango_nivel_crudo"] = float((k["NK51_nivel_hi80_crudo"] - k["NK51_nivel_lo80_crudo"]).mean())
    res["rango_anio_crudo"] = float((k["NK51_hi80_crudo"] - k["NK51_lo80_crudo"]).mean())
    res["por_sello"] = (prueba.assign(err=(prueba["NK51"] - prueba["pct_realizado"]).abs(),
                                      cubre=(prueba["pct_realizado"] >= prueba["NK51_lo80"]) &
                                      (prueba["pct_realizado"] <= prueba["NK51_hi80"]),
                                      ancho_nivel=prueba["NK51_nivel_hi80_crudo"] - prueba["NK51_nivel_lo80_crudo"])
                        .groupby("sello").agg(n=("err", "size"), error_abs=("err", "mean"), cobertura80=("cubre", "mean"),
                                              rango_nivel=("ancho_nivel", "mean"))
                        .assign(spearman=prueba.groupby("sello").apply(
                            lambda g: stats.spearmanr(g["NK51"], g["pct_realizado"]).statistic, include_groups=False))
                        .round(3).to_dict("index"))
    C.escribir_json({**C.metadatos(cfg), **res}, out / "meta_nivel_kerno.json")
    return res
