"""F8 · Protocolo de la F1 sobre la v5 (encargo §12): mismo examen de cambios de liga que la F1 (cortes 2022–2024,
t → t+1, ≥ 300 min en ambas ligas), con la v5, la v3.2 publicada (predictiva recalibrada), la v2 (A+B amortiguado) y
la v1 (algoritmo A, punto), **en los mismos casos y contra el mismo valor observado**.

- Casos de la F1: `casos_combinada_v32.csv.gz`. La persona de la v3.2 es un índice interno del repositorio de
  entonces; se enlaza con la persona v5 por nombre normalizado + liga + temporada de origen (único en el 99,3 %).
- Métricas comunes (13): T2%, T3%, TL%, 3PAr, FTr, OREB%, DREB%, AST%, TOV%, BLK%, STL/100, pts/100 y USG%. PF/100 de la
  v3.2 y PF/40 de la v5 no son la misma métrica.
- Escala: la de la métrica (la v3.2 se pasa de su escala z a la original con su propia transformación, recuperada de
  real_z, como en la F1).
- Se exige que el observado de la v3.2 y el de la v5 coincidan (mismo registro).
- Puntuación: WIS con intervalos del 50, 80 y 90 % (regla propia, ≈ 0,8 × CRPS; para un punto es el error absoluto). Además
  cobertura del 50, 80 y 95 %, MAE y RMSE; PIT de la v5.
- Diferencia v5 frente a v3.2 por métrica, liga de origen, liga de destino, puesto y tramo de minutos en destino, con
  IC 95 % por bootstrap de personas: sólo es mejora lo que no cruza 0.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from bbnorm5 import config as C
from bbnorm5.datos.entidades import normalizar
from bbnorm5.validacion import fichajes as VF

DIR = VF.DIR
EQ = {"fg2_pct": "t2_pct", "fg3_pct": "t3_pct", "ft_pct": "tl_pct", "fg3a_rate": "tpar", "fta_rate": "ftr",
      "oreb_pct": "oreb_pct", "dreb_pct": "dreb_pct", "ast_pct": "ast_pct", "tov_pct": "tov_pct", "blk_pct": "blk_pct",
      "stl_p100": "stl_p100", "pts_p100": "pts_p100", "usg_pct": "usg_pct"}
MODELOS_V32 = {"v3.2": ("v3_centro_z", "sd_v32c"), "v2": ("v2_centro_z", "v2_sd_z"), "v1": ("algoritmo_A_z", None)}
NIV = {50: 0.25, 80: 0.10, 90: 0.05, 95: 0.025}


def _personas_por_nombre() -> pd.Series:
    cw = pd.read_csv(C.RAIZ / "data" / "processed" / "player_id_crosswalk.csv", dtype=str)
    per = pd.read_csv(C.DIR_DATOS / "limpios" / "entidades" / "personas_v5.csv", dtype=str)
    n = cw.merge(per[["fuente_liga", "fuente_id", "persona_v5"]], on=["fuente_liga", "fuente_id"])
    n = n.assign(temporada=n["temporadas"].str.split(",")).explode("temporada")
    n["nn"] = n["nombre"].map(normalizar)
    g = n.groupby(["fuente_liga", "temporada", "nn"])["persona_v5"].agg(lambda s: tuple(sorted(set(s))))
    return g[g.map(len) == 1].map(lambda t: t[0])


def casos_v32(cfg1: dict) -> pd.DataFrame:
    """Casos de la F1 con la persona v5 y los cuantiles de cada modelo en la escala original de la métrica."""
    from bbmodel.metricas import CATALOGO, destransformar
    from bbnorm5.diagnostico import pasos_f1 as P1
    c = P1.casos_movimientos(cfg1)
    c = c[c["metrica"].isin(EQ)].copy()
    c["sd_v32c"] = c["v3_sd_z"] * c["kappa"]
    esc = P1._escala_metrica(c)
    idx = _personas_por_nombre()
    t_o = c["anio"].map(lambda a: f"{a}-{str(a + 1)[2:]}")
    c["persona_v5"] = [idx.get((l, t, normalizar(nm))) for l, t, nm in zip(c["liga_o"], t_o, c["nombre"])]
    c["met5"] = c["metrica"].map(EQ)
    c["anio_obj"] = c["anio"] + 1
    for mod, (mu, sd) in MODELOS_V32.items():
        cs = np.array([esc[m][0] for m in c["metrica"]])
        ss = np.array([esc[m][1] for m in c["metrica"]])
        tr = [CATALOGO[m].transf for m in c["metrica"]]
        m_ = c[mu].to_numpy(float)
        s_ = c[sd].to_numpy(float) if sd else np.zeros(len(c))

        def a_original(z):
            v = cs + ss * z
            out = np.empty(len(v))
            for t in set(tr):
                k = np.array([x == t for x in tr])
                out[k] = destransformar(v[k], t)
            return out
        c[f"{mod}__q50"] = a_original(m_)
        for a, al in NIV.items():
            zq = stats.norm.ppf(al)
            c[f"{mod}__lo{a}"] = a_original(m_ + zq * s_)
            c[f"{mod}__hi{a}"] = a_original(m_ - zq * s_)
    return c


def comparar(cfg: dict, cfg1: dict, p: pd.DataFrame | None = None, modelo: str = "ex_ante", sufijo: str = "") -> dict:
    """`modelo`: la v5 ex ante (rol de T desconocido, sin volumen, exposición anterior; la comparable) o la
    condicionada al rol y al volumen de T («final»)."""
    p = pd.read_parquet(DIR / "predicciones_v5.parquet") if p is None else p
    c = casos_v32(cfg1)
    n0 = len(c)
    pv = p[p["modelo"] == modelo]
    c = c.merge(pv, left_on=["persona_v5", "liga_d", "anio_obj", "met5"],
                right_on=["persona_v5", "liga", "anio", "metrica"], suffixes=("", "_v5"), how="inner")
    # escala de la v5 frente a la de la v3.2 (1 o 100 según la métrica) y mismo registro
    k = c.groupby("metrica")[["real", "obs"]].apply(lambda g: 10 ** np.round(np.log10(np.nanmedian(g["real"] / g["obs"].replace(0, np.nan)))))
    c["k"] = c["metrica"].map(k)
    tol = np.maximum(0.01 * np.abs(c["real"]), 0.02 * c["k"] / 100)
    c = c[np.isfinite(c["real"]) & (np.abs(c["real"] - c["k"] * c["obs"]) <= tol)].copy()
    for q in VF.CUANTILES:
        c[f"v5__{VF._q(q)}"] = c[VF._q(q)] * c["k"]
    c["v5__q50"] = c["q50"] * c["k"]
    for a, al in NIV.items():
        c[f"v5__lo{a}"] = c[VF._q(al)] * c["k"]
        c[f"v5__hi{a}"] = c[VF._q(1 - al)] * c["k"]
    y = c["real"].to_numpy(float)
    mods = ["v5"] + list(MODELOS_V32)
    for mod in mods:
        c[f"wis_{mod}"] = VF.wis(y, c[f"{mod}__q50"], {a: c[f"{mod}__lo{a}"] for a in (50, 80, 90)},
                                 {a: c[f"{mod}__hi{a}"] for a in (50, 80, 90)})
    c["tramo_min_d"] = pd.cut(c["min_d"], [0, 600, 1200, np.inf], labels=["300-600", "600-1200", "≥1200"]).astype(str)
    c.to_parquet(DIR / f"protocolo_f1_casos{sufijo}.parquet")
    rng = np.random.default_rng(cfg["semilla"])
    B = int(cfg["examen"].get("bootstrap", 1000))
    filas = []
    for por in ("global", "metrica", "liga_o", "liga_d", "pos3", "tramo_min_d", "anio"):
        grupos = [("todo", c)] if por == "global" else list(c.groupby(por))
        for g_, g in grupos:
            if len(g) < 30:
                continue
            esc_m = g.groupby("metrica")["wis_v3.2"].transform("mean").to_numpy()      # cada métrica pesa igual
            fila = {"por": por, "grupo": g_, "casos": len(g), "personas": g["persona_v5"].nunique()}
            yy = g["real"].to_numpy(float)
            for mod in mods:
                fila[f"wis_{mod}"] = float(g[f"wis_{mod}"].mean())
                fila[f"mae_{mod}"] = float(np.mean(np.abs(yy - g[f"{mod}__q50"])))
                if mod != "v1":
                    for a in (50, 80, 95):
                        fila[f"cob{a}_{mod}"] = float(((yy >= g[f"{mod}__lo{a}"]) & (yy <= g[f"{mod}__hi{a}"])).mean())
            for ref in ("v3.2", "v2", "v1"):
                r, lo, hi = VF._boot_ratio(g["persona_v5"].to_numpy(), g["wis_v5"].to_numpy() / esc_m,
                                           g[f"wis_{ref}"].to_numpy() / esc_m, B, rng)
                fila[f"v5_frente_{ref}"], fila[f"ic_lo_{ref}"], fila[f"ic_hi_{ref}"] = r, lo, hi
                fila[f"mejora_{ref}"] = hi < 0
            filas.append(fila)
    t = pd.DataFrame(filas)
    t.to_csv(DIR / f"protocolo_f1{sufijo}.csv", index=False)
    c[["metrica", "anio", "pit"]].to_csv(DIR / f"protocolo_f1_pit{sufijo}.csv.gz", index=False)
    glob = t[t["por"] == "global"].iloc[0].to_dict()
    return {"casos_f1": int(n0), "casos_comunes": int(len(c)), "personas": int(c["persona_v5"].nunique()),
            "global": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in glob.items()},
            "metricas_mejora_v32": int(t[(t["por"] == "metrica")]["mejora_v3.2"].sum()),
            "metricas": int((t["por"] == "metrica").sum())}
