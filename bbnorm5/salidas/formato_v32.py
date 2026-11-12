"""F9 · Salidas de la v5 en el formato que consume el artifact (el de la v3.2), para activarla como fuente alternativa
sin tocar el artifact (encargo §13: «columnas adicionales, nunca menos»).

1. **Por temporada** (`formato_v32/normalizado/<temporada>.csv.gz`). Mismas filas, columnas, nombres y unidades que
   `data/modelos/v3_2/normalizado/<temporada>.csv.gz`:
   - en las 13 métricas que modela la v5, `<m>`, `<m>_lo`, `<m>_hi` y `<m>_pctel` pasan a ser, como en la v3.2, el
     **equivalente EuroLeague 2025-26** con la v5: nivel de la temporada en su liga (F4) + λ(EuroLeague, 2025-26) −
     λ(liga, temporada) de la traducción publicada (NUTS del paso 2); intervalo del 80 % con la varianza del nivel y la
     de la traducción; percentil entre los jugadores de la EuroLeague de su posición esa temporada;
   - `<m>_nivel_liga`: el nivel de la v5 en su propia liga;
   - el valor de la v3.2 se conserva en `<m>_v32`, `<m>_v32_lo` y `<m>_v32_hi`;
   - más columnas nuevas: `<m>_lo50` / `<m>_hi50` (intervalo del 50 %), `<m>_obs_v5` y `fuente_<m>` («V5» o «V3.2»);
   - las métricas que la v5 no modela (TS%, eFG%, PER, RAPM…) quedan con la v3.2;
   - PF/40 de la v5 va aparte (`pf_p40*`): no es la PF/100 de la v3.2.
2. **Por liga de destino** (`formato_v32/destinos/<temporada objetivo>/<liga>.csv.gz`). Una fila por jugador y, por
   cada métrica:
   - nivel en la liga de destino: mediana e intervalo del 80 %;
   - predictivo de la temporada objetivo: mediana e intervalo del 80 %;
   - P(nivel > percentil 50 de la liga y su rol) y sello de fiabilidad.

Unidades: las de la v3.2 (porcentajes y por 100 posesiones). El factor de cada métrica se mide comparando los
observados de las dos versiones en las mismas filas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import special, stats

from bbnorm5 import config as C
from bbnorm5.medida import datos as DM

DIR = C.DIR_DATOS / "salidas" / "formato_v32"
V32 = C.RAIZ / "data" / "modelos" / "v3_2" / "normalizado"
A_V32 = {"t2_pct": "fg2_pct", "t3_pct": "fg3_pct", "tl_pct": "ft_pct", "tpar": "fg3a_rate", "ftr": "fta_rate",
         "oreb_pct": "oreb_pct", "dreb_pct": "dreb_pct", "ast_pct": "ast_pct", "tov_pct": "tov_pct",
         "blk_pct": "blk_pct", "stl_p100": "stl_p100", "pts_p100": "pts_p100", "usg_pct": "usg_pct", "pf_p40": "pf_p40"}
Z = {80: stats.norm.ppf(0.9), 50: stats.norm.ppf(0.75)}
VARA = ("euroleague", "2025-26")      # como la v3.2: equivalente EuroLeague 2025-26


def _inv(fam: str):
    return {"binomial": special.expit, "poisson": np.exp}.get(fam, lambda z: z)


def _personas() -> pd.DataFrame:
    per = pd.read_csv(C.DIR_DATOS / "limpios" / "entidades" / "personas_v5.csv", dtype=str)
    return per.rename(columns={"fuente_liga": "liga", "fuente_id": "player_id"})[["liga", "player_id", "persona_v5"]]


def factores_unidad(niv: pd.DataFrame, obs: pd.DataFrame) -> dict:
    """Factor v3.2 / v5 por métrica (potencia de 10 de la mediana de los observados en las mismas filas)."""
    per = _personas()
    k = {}
    for t in sorted(niv["temporada"].unique())[-2:]:
        v = pd.read_csv(V32 / f"{t}.csv.gz", low_memory=False, dtype={"player_id": str})
        v = v.merge(per, on=["liga", "player_id"], how="inner")
        for m5, m3 in A_V32.items():
            if f"{m3}_obs" not in v:
                continue
            o = obs[(obs["metrica"] == m5) & (obs["temporada"] == t)][["persona_v5", "liga", "tasa"]]
            j = v[["persona_v5", "liga", f"{m3}_obs"]].merge(o, on=["persona_v5", "liga"])
            r = (j[f"{m3}_obs"] / j["tasa"]).replace([np.inf, -np.inf], np.nan).dropna()
            if len(r) > 50:
                k.setdefault(m5, []).append(float(10 ** np.round(np.log10(r.median()))))
    out = {m: float(np.median(v)) for m, v in k.items()}
    out["pf_p40"] = 40.0          # la tasa de la v5 es por minuto; la columna es por 40 minutos
    return out


def _traduccion(z: dict, ligas: np.ndarray, t: str) -> tuple[np.ndarray, np.ndarray]:
    """Media y varianza de λ(EuroLeague, temporada de la vara) − λ(liga, t) con los draws de la NUTS del paso 2."""
    il = {l: i for i, l in enumerate(z["ligas"])}
    it = {tt: i for i, tt in enumerate(z["temporadas"])}
    m, v = np.full(len(ligas), np.nan), np.full(len(ligas), np.nan)
    if t not in it or VARA[0] not in il or VARA[1] not in it:
        return m, v
    ref = z["lam"][:, il[VARA[0]], it[VARA[1]]]
    for l in set(ligas):
        if l in il:
            d = ref - z["lam"][:, il[l], it[t]]
            k = ligas == l
            m[k], v[k] = float(d.mean()), float(d.var())
    return m, v


def _pctel(c: np.ndarray, v: pd.DataFrame) -> np.ndarray:
    """Percentil entre los jugadores de la EuroLeague de la misma posición (pos3) de esa temporada, como la v3.2."""
    out = np.full(len(c), np.nan)
    pos = v["pos3"].astype(str).to_numpy()
    ref = (v["liga"] == VARA[0]).to_numpy() & np.isfinite(c)
    for p in set(pos):
        r = np.sort(c[ref & (pos == p)])
        sel = (pos == p) & np.isfinite(c)
        if len(r):
            out[sel] = 100 * np.searchsorted(r, c[sel], side="right") / len(r)
    return out


def normalizado(niv: pd.DataFrame, obs: pd.DataFrame, k: dict) -> list:
    from bbnorm5.ligas import modelo as LM
    from bbnorm5.ligas import resumen_paso2 as LR2
    lam = LR2.cargar(LM.BLOQUES_PASO2, "paso2_")
    per = _personas()
    escritos = []
    (DIR / "normalizado").mkdir(parents=True, exist_ok=True)
    for t in sorted(niv["temporada"].unique()):
        f = V32 / f"{t}.csv.gz"
        if not f.exists():
            continue
        v = pd.read_csv(f, low_memory=False, dtype={"player_id": str})
        n0, c0 = len(v), list(v.columns)
        v = v.merge(per, on=["liga", "player_id"], how="left")
        nt = niv[niv["temporada"] == t]
        nuevas = {}
        for m5, m3 in A_V32.items():
            fam = DM.METRICAS[m5][0]
            inv = _inv(fam)
            g = nt[nt["metrica"] == m5].drop_duplicates(["persona_v5", "liga"])
            eta_liga = (g["mu"] + g["nivel_carrera"]).to_numpy(float)
            # equivalente EuroLeague de la temporada de la vara (como la v3.2): + λ(EuroLeague, vara) − λ(liga, t)
            dm, dv = _traduccion(lam[m5], g["liga"].to_numpy(), t)
            eta = eta_liga + dm
            sd = np.sqrt(g["var_nivel_carrera"].to_numpy(float) + dv)
            val = pd.DataFrame({"persona_v5": g["persona_v5"].to_numpy(), "liga": g["liga"].to_numpy(),
                                "nivel_liga": inv(eta_liga) * k[m5],
                                "c": inv(eta) * k[m5], "lo": inv(eta - Z[80] * sd) * k[m5],
                                "hi": inv(eta + Z[80] * sd) * k[m5], "lo50": inv(eta - Z[50] * sd) * k[m5],
                                "hi50": inv(eta + Z[50] * sd) * k[m5]})
            o = obs[(obs["metrica"] == m5) & (obs["temporada"] == t)][["persona_v5", "liga", "tasa"]]
            val = val.merge(o.assign(tasa=o["tasa"] * k[m5]), on=["persona_v5", "liga"], how="left")
            j = v[["persona_v5", "liga"]].merge(val, on=["persona_v5", "liga"], how="left")
            hay = j["c"].notna().to_numpy()
            if m3 in v.columns and m5 != "pf_p40":
                for s_ in ("", "_lo", "_hi"):
                    nuevas[f"{m3}_v32{s_}"] = v[f"{m3}{s_}"].to_numpy()
                v[m3] = np.where(hay, j["c"], v[m3])
                v[f"{m3}_lo"] = np.where(hay, j["lo"], v[f"{m3}_lo"])
                v[f"{m3}_hi"] = np.where(hay, j["hi"], v[f"{m3}_hi"])
                v[f"{m3}_pctel"] = np.where(hay, _pctel(j["c"].to_numpy(float), v), v[f"{m3}_pctel"])
            else:
                nuevas[m3], nuevas[f"{m3}_lo"], nuevas[f"{m3}_hi"] = j["c"].to_numpy(), j["lo"].to_numpy(), j["hi"].to_numpy()
                nuevas[f"{m3}_pctel"] = _pctel(j["c"].to_numpy(float), v)
            nuevas[f"{m3}_nivel_liga"] = j["nivel_liga"].to_numpy()
            nuevas[f"{m3}_lo50"], nuevas[f"{m3}_hi50"] = j["lo50"].to_numpy(), j["hi50"].to_numpy()
            nuevas[f"{m3}_obs_v5"] = j["tasa"].to_numpy()
            nuevas[f"fuente_{m3}"] = np.where(hay, "V5", "V3.2")
        v = pd.concat([v, pd.DataFrame(nuevas, index=v.index)], axis=1)
        v["fuente_norm"] = np.where(v[[f"fuente_{m3}" for m3 in A_V32.values()]].eq("V5").any(axis=1), "V5+V3.2",
                                    v["fuente_norm"])
        assert len(v) == n0 and all(c in v.columns for c in c0), "el formato de la v3.2 no se conserva"
        num = v.select_dtypes("number").columns
        v[num] = v[num].round(4)
        v.to_csv(DIR / "normalizado" / f"{t}.csv.gz", index=False, compression="gzip")
        escritos.append({"temporada": t, "filas": len(v), "con_v5": int((v["persona_v5"].notna()).sum())})
    return escritos


def destinos(d: pd.DataFrame, k: dict) -> list:
    per = pd.read_csv(C.DIR_DATOS / "limpios" / "entidades" / "personas_v5.csv", dtype=str)
    cw = per.drop_duplicates("persona_v5").set_index("persona_v5")["persona_crosswalk"]
    t = d["temporada_objetivo"].iloc[0]
    sal = DIR / "destinos" / t
    sal.mkdir(parents=True, exist_ok=True)
    escritos = []
    for liga, g in d.groupby("liga_destino"):
        base = g.drop_duplicates("persona_v5")[["persona_v5", "liga_origen", "temporada_ult", "rol_ult", "edad"]]
        base.insert(1, "persona_id", base["persona_v5"].map(cw).to_numpy())
        base.insert(0, "liga_destino", liga)
        base = base.set_index("persona_v5")
        for m5, m3 in A_V32.items():
            x = g[g["metrica"] == m5].set_index("persona_v5")
            kk = k[m5]
            cols = {f"{m3}_nivel": x["nivel_q50"] * kk, f"{m3}_nivel_lo": x["nivel_q10"] * kk,
                    f"{m3}_nivel_hi": x["nivel_q90"] * kk, f"{m3}_pred": x["pred_q50"] * kk,
                    f"{m3}_pred_lo": x["pred_q10"] * kk, f"{m3}_pred_hi": x["pred_q90"] * kk,
                    f"{m3}_p_supera_p50": x["p_supera_p50"], f"{m3}_sello": x["sello"]}
            base = base.join(pd.DataFrame(cols))
        base = base.reset_index()
        num = base.select_dtypes("number").columns
        base[num] = base[num].round(4)
        base.to_csv(sal / f"{liga}.csv.gz", index=False, compression="gzip")
        escritos.append({"liga": liga, "filas": len(base)})
    return escritos


def generar(cfg: dict) -> dict:
    niv = pd.read_parquet(C.DIR_DATOS / "carrera" / "niveles_carrera.parquet")
    o = pd.read_parquet(C.DIR_DATOS / "carrera" / "observaciones.parquet",
                        columns=["persona_v5", "liga", "temporada", "metrica", "K", "N"])
    o = o[o["N"] > 0].assign(tasa=lambda x: x["K"] / x["N"])
    o = o.groupby(["persona_v5", "liga", "temporada", "metrica"], as_index=False)["tasa"].mean()
    k = factores_unidad(niv, o)
    n = normalizado(niv, o, k)
    anio = int(cfg["anio_objetivo"])
    temp_obj = f"{anio}-{str(anio + 1)[2:]}"
    d = pd.read_parquet(C.DIR_DATOS / "salidas" / temp_obj / "destinos.parquet")
    e = destinos(d, k)
    meta = {**C.metadatos(cfg, None, {"paso": "formato_v32"}), "factor_unidades": k, "normalizado": n,
            "destinos": e, "metricas_v5": A_V32}
    C.escribir_json(meta, DIR / "meta.json")
    return {"factor_unidades": k, "temporadas": len(n), "ligas_destino": len(e)}
