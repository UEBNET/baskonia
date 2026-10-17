"""Datos de la pestaña «Normalización de ligas» de la Mesa (algoritmos A y B).

Lee data/modelos/algoritmo_A y algoritmo_B y escribe en <salida> (por defecto data/artifact,
que el Artifact publica como datos/):
    normalizacion/resumen.json             nivel de cada liga, equivalencias de percentil, qué
                                           esperar al importar, validación y puentes
    (normalizacion/jugadores_<temp>.json, el explorador, lo escribe bbmodel.dataset_normalizado)
Uso: python -m bbmodel mesa-normalizacion
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from .metricas import CATALOGO, destransformar, transformar

RAIZ = Path(__file__).resolve().parent.parent
DA = RAIZ / "data" / "modelos" / "algoritmo_A"
DB = RAIZ / "data" / "modelos" / "algoritmo_B"
LIGAS = ["nba", "gleague", "acb", "eurocup", "lba", "bbl", "lnb", "bcl", "fec", "bsl", "gbl", "euroleague"]
CLAVE = ["per", "game_score_p40", "ws_per_40", "pts_p100", "usg_pct", "ts_pct", "efg_pct", "fg3_pct", "fg3a_rate",
         "fta_rate", "ast_pct", "tov_pct", "oreb_pct", "dreb_pct", "stl_pct", "blk_pct", "drtg"]
EXPLORADOR = ["per", "game_score_p40", "pts_p100", "usg_pct", "ts_pct", "fg3_pct", "ast_pct", "tov_pct", "dreb_pct",
              "oreb_pct", "stl_pct", "blk_pct", "drtg", "ws_per_40"]
PCTS = [10, 25, 50, 75, 90, 97]
Z80 = norm.ppf(0.9)


def r(x, d=3):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(x) else round(x, d)


def combinar(a, b, col: str):
    """Estimación A+B: media de ambas en la escala transformada de la métrica (donde el error es
    aproximadamente simétrico), devuelta en unidades reales."""
    tr = CATALOGO[col].transf
    return destransformar((transformar(a, tr) + transformar(b, tr)) / 2, tr)


def _pct_en_liga(df: pd.DataFrame, col: str) -> pd.Series:
    """Percentil (0-100) del valor observado dentro de su liga y posición (sentido «más = más»)."""
    return df.groupby(["liga", "pos3"])[col].rank(pct=True) * 100


def construir(temporada: str = "2025-26", min_min: float = 300) -> tuple[dict, dict]:
    tc = pd.read_csv(DA / "tipo_de_cambio.csv")
    pa = json.loads((DA / "parametros.json").read_text(encoding="utf-8"))
    nb = pd.read_csv(DB / "nivel_por_liga.csv")
    resumen_b = json.loads((DB / "resumen_modelo.json").read_text(encoding="utf-8"))
    TA = {t.stem: pd.read_csv(t, low_memory=False) for t in sorted((DA / "traducciones").glob("*.csv"))}
    TB = {t.stem: pd.read_csv(t, low_memory=False) for t in sorted((DB / "traducciones").glob("*.csv"))}

    metricas = [{"col": c, "nombre": CATALOGO[c].nombre, "grupo": CATALOGO[c].grupo, "sentido": CATALOGO[c].sentido}
                for c in CATALOGO]
    out = {"temporada_ref": temporada, "ligas": LIGAS, "metricas": metricas, "clave": CLAVE,
           "A": {"nivel": {}, "deriva": {}}, "B": {"nivel": {}, "modelo": resumen_b}, "equivalencias": {},
           "importar": {}, "validacion": {}, "info": pa.get("info", {})}
    for col in CATALOGO:
        g = tc[tc.metrica == col].set_index("liga")
        out["A"]["nivel"][col] = {l: [r(g.loc[l, "m"]), r(g.loc[l, "m_se"]), r(g.loc[l, "s"]), r(g.loc[l, "s_se"]),
                                      int(g.loc[l, "puentes"])] for l in g.index}
        out["A"]["deriva"][col] = {k: r(v) for k, v in pa["metricas"][col]["enlace"]["deriva"].items()}
        h = nb[nb.metrica == col].set_index("liga")
        out["B"]["nivel"][col] = {l: [r(h.loc[l, "nivel"]), r(h.loc[l, "nivel_se"])] for l in h.index}

    # ---- equivalencias de percentil y «qué esperar al importar» (temporada de referencia)
    a = TA[temporada]; b = TB[temporada]
    clave = ["persona_id", "liga", "temporada"]
    m = a.merge(b[clave + [f"{c}_{s}" for c in CATALOGO for s in ("el", "pct_el")]], on=clave, how="inner",
                suffixes=("_A", "_B"))
    m = m[m["min"] >= min_min].copy()
    for col in CATALOGO:
        m[f"{col}_el_AB"] = combinar(m[f"{col}_el_A"], m[f"{col}_el_B"], col)
        m[f"{col}_pct_el_AB"] = (m[f"{col}_pct_el_A"] + m[f"{col}_pct_el_B"]) / 2
    # «importables»: el 20 % mejor de su liga por Game Score/40 observado, entre los que juegan de verdad
    # (minutos ≥ la mitad del percentil 90 de minutos de su liga: ≈ 380-530 en las ligas europeas y la
    # G League, ≈ 1.130 en la NBA y ≈ 230 en la EuroCup, cuya fase regular es corta)
    umbral = m.groupby("liga")["min"].transform(lambda x: 0.5 * x.quantile(0.9))
    m["gs_pct_liga"] = m.groupby("liga")["game_score_p40"].rank(pct=True)
    top = (m["gs_pct_liga"] >= 0.8) & (m["min"] >= umbral)
    out["umbral_importables"] = {l: r(v, 0) for l, v in m.groupby("liga")["min"].quantile(0.9).mul(0.5).items()}
    for col in CATALOGO:
        m[f"{col}_pct_liga"] = _pct_en_liga(m, col)
        eq, imp = {}, {}
        for liga in LIGAS:
            s = m["liga"] == liga
            if s.sum() < 15 or m.loc[s, col].isna().all():
                continue
            fila = {}
            for alg, cpct in (("A", f"{col}_pct_el_A"), ("B", f"{col}_pct_el_B"), ("AB", f"{col}_pct_el_AB")):
                vals = []
                for p in PCTS:
                    w = s & (m[f"{col}_pct_liga"] - p).abs().le(7.5) & m[cpct].notna()
                    vals.append(r(m.loc[w, cpct].median(), 1) if w.sum() >= 3 else None)
                fila[alg] = vals
            eq[liga] = fila
            def med(x):
                return r(np.nanmedian(x), 3) if np.isfinite(x).any() else None
            imp[liga] = {"n": int(s.sum()), "n_top": int((s & top).sum()),
                         "obs": med(m.loc[s, col].to_numpy(float)), "A": med(m.loc[s, f"{col}_el_A"].to_numpy(float)),
                         "B": med(m.loc[s, f"{col}_el_B"].to_numpy(float)),
                         "obs_top": med(m.loc[s & top, col].to_numpy(float)),
                         "A_top": med(m.loc[s & top, f"{col}_el_A"].to_numpy(float)),
                         "B_top": med(m.loc[s & top, f"{col}_el_B"].to_numpy(float)),
                         "AB": med(m.loc[s, f"{col}_el_AB"].to_numpy(float)),
                         "AB_top": med(m.loc[s & top, f"{col}_el_AB"].to_numpy(float)),
                         "pctAB_top": med(m.loc[s & top, f"{col}_pct_el_AB"].to_numpy(float)),
                         "pctA_top": med(m.loc[s & top, f"{col}_pct_el_A"].to_numpy(float)),
                         "pctB_top": med(m.loc[s & top, f"{col}_pct_el_B"].to_numpy(float))}
        out["equivalencias"][col] = eq
        out["importar"][col] = imp

    # ---- validación (mismos casos para A y B)
    va = pd.read_csv(DA / "validacion_casos.csv")
    vb = pd.read_csv(DB / "validacion_casos.csv")
    vb["dentro_80_B"] = (vb["y_real"] - vb["x_pred"]).abs() <= Z80 * np.sqrt(vb["v_pred"] + vb["v_real"].fillna(0))
    v = va.merge(vb[["metrica", "anio", "persona_id", "algoritmo_B", "dentro_80_B"]], on=["metrica", "anio", "persona_id"])
    v = v.dropna(subset=["real", "algoritmo_A", "algoritmo_B", "mismo_percentil"])
    v["algoritmo_AB"] = np.nan
    for col in v["metrica"].unique():
        s_ = v["metrica"] == col
        v.loc[s_, "algoritmo_AB"] = combinar(v.loc[s_, "algoritmo_A"], v.loc[s_, "algoritmo_B"], col)
    def bloque(g):
        e = {k: (g[k] - g["real"]) for k in ("mismo_numero", "mismo_percentil", "algoritmo_A", "algoritmo_B", "algoritmo_AB")}
        mse = {k: float(np.mean(x ** 2)) for k, x in e.items()}
        return {"casos": int(len(g)), **{f"mae_{k}": r(np.mean(np.abs(x))) for k, x in e.items()},
                "mejora_A": r(100 * (1 - mse["algoritmo_A"] / mse["mismo_percentil"]), 1),
                "mejora_B": r(100 * (1 - mse["algoritmo_B"] / mse["mismo_percentil"]), 1),
                "mejora_AB": r(100 * (1 - mse["algoritmo_AB"] / mse["mismo_percentil"]), 1),
                "mejora_B_vs_A": r(100 * (1 - mse["algoritmo_B"] / mse["algoritmo_A"]), 1),
                "mejora_AB_vs_A": r(100 * (1 - mse["algoritmo_AB"] / mse["algoritmo_A"]), 1),
                "cob_A": r(g["dentro_80"].mean(), 3), "cob_B": r(g["dentro_80_B"].mean(), 3)}
    for col, g in v.groupby("metrica"):
        out["validacion"][col] = {"todos": bloque(g)}
        e = g[g["liga_d"] == "euroleague"]
        if len(e) >= 15:
            out["validacion"][col]["a_euroleague"] = bloque(e)
    out["validacion_n_jugadores"] = int(v.drop_duplicates(["anio", "persona_id"]).shape[0])
    out["validacion_n_a_euroleague"] = int(v[v.liga_d == "euroleague"].drop_duplicates(["anio", "persona_id"]).shape[0])

    # ---- puentes
    out["puentes"] = pa.get("info", {}).get("puentes", [])

    # ---- explorador (temporadas de referencia y en curso)
    jug = {}
    for temp in sorted(set(TA) & set(TB))[-2:]:
        a, b = TA[temp], TB[temp]
        j = a.merge(b[clave + [f"{c}_{s}" for c in EXPLORADOR for s in ("el", "el_lo", "el_hi", "pct_el")]],
                    on=clave, how="left", suffixes=("_A", "_B"))
        j = j[j["min"] >= 100]
        cols = ["nombre", "equipo", "liga", "pos3", "pos3_estimada", "anio_nac", "gp", "min"]
        for c in EXPLORADOR:
            j[f"{c}_el_AB"] = combinar(j[f"{c}_el_A"], j[f"{c}_el_B"], c)
            j[f"{c}_pct_el_AB"] = (j[f"{c}_pct_el_A"] + j[f"{c}_pct_el_B"]) / 2
            cols += [c, f"{c}_el_A", f"{c}_el_lo_A", f"{c}_el_hi_A", f"{c}_pct_el_A", f"{c}_el_B", f"{c}_el_lo_B",
                     f"{c}_el_hi_B", f"{c}_pct_el_B", f"{c}_el_AB", f"{c}_pct_el_AB"]
        rows = []
        for vals in j[cols].itertuples(index=False):
            rows.append([(None if (isinstance(x, float) and not np.isfinite(x)) else (round(x, 2) if isinstance(x, float) else x))
                         for x in vals])
        jug[temp] = {"columnas": cols, "filas": rows}
    return out, jug


def main(salida: str = "data/artifact"):
    """Escribe resumen.json. Los jugadores del explorador (jugadores_<temp>.json, todas las temporadas y todos los
    jugadores, A+B con A de respaldo) los escribe `python -m bbmodel dataset-normalizado`."""
    out, _ = construir()
    out["contexto"] = bloque_contexto()
    d = Path(salida) / "normalizacion"
    d.mkdir(parents=True, exist_ok=True)
    (d / "resumen.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("escrito", d / "resumen.json", "· explorador: python -m bbmodel dataset-normalizado")


def bloque_contexto() -> dict | None:
    """Contexto de nivel (bbmodel/contexto.py) para la pestaña: sensibilidad de cada métrica al nivel de los
    compañeros y de los rivales, y nivel medio de jugadores, compañeros y rivales por liga y temporada."""
    raiz = Path(__file__).resolve().parent.parent / "data" / "modelos" / "contexto"
    if not (raiz / "sensibilidad.csv").exists():
        return None
    sens = pd.read_csv(raiz / "sensibilidad.csv")
    pj = pd.read_csv(raiz / "por_jugador_liga.csv")
    pj = pj[pj["min"] >= 300]
    liga = []
    for (l, t), g in pj.groupby(["liga", "temporada"]):
        w = g["min"].to_numpy(float)
        f = lambda c: r(float(np.average(g[c].fillna(g[c].mean()), weights=w)), 3) if g[c].notna().any() else None  # noqa: E731
        liga.append({"liga": l, "temporada": t, "jugadores": int(len(g)), "L": f("L"), "ctx_comp": f("ctx_comp"),
                     "ctx_riv": f("ctx_riv"), "ctx_plantilla": f("ctx_plantilla")})
    return {"sensibilidad": [{k: (r(v, 4) if isinstance(v, (float, np.floating)) else v) for k, v in x.items()}
                             for x in sens.to_dict("records")],
            "por_liga": liga,
            "nota": "β = cambio de la capacidad en la vara EuroLeague (desviaciones típicas de los jugadores de EuroLeague de "
                    "su posición) por cada unidad de nivel medio de los compañeros (contexto de plantilla) y de los rivales, "
                    "dentro de la misma persona (efecto fijo). El nivel L es el índice del Atlas (0 = jugador medio)."}
