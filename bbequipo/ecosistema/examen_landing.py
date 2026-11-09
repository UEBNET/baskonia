"""K3 · Examen prerregistrado de las dos tablas de adaptación para la Landing (configs/ecosistema_v41.yaml → f4.k3_landing).

Pregunta: ¿qué tabla representa mejor el escalón de la primera temporada en la liga nueva?

Objetivo por traspaso i (cortes t = 2022, 2023, 2024; destino t+1):
    o_i = log(L_rel observado / 100)
L_rel = media geométrica de real/ŷ en las 8 métricas del índice L, con ŷ = el origen traducido por la normalización
(validacion_casos de la fase 7). o > 0: rinde por encima de lo que traduce la normalización.

Predicciones por grupo de traspaso g (el de la Landing):
    A (fase 7 rehecha, v3_2): media ponderada del grupo de log(previsto/100), con el modelo de la fase 7 ajustado sólo con
      destinos ≤ t (sin fuga);
    B (adaptación v3, v3_1): log(1 + D_g·w̄_g), la tabla del motor y de la Landing de la candidata (publicada: la fuga
      juega a su favor);
    base: 0 (sólo la normalización).

Medidas: MAE ponderado (IPCW) por corte y conjunto, con IC95 bootstrap por persona (B = 2000); representatividad por
grupo (n ≥ 30): la predicción dentro del IC80 de la media observada del grupo, y acuerdo de signo; cobertura del 80 %
(sólo A). Regla de elección y sello: el YAML.

    python -m bbequipo.ecosistema examen-landing   → data/modelos/v4_1/producto/examen_landing.json
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import yaml

from . import config as CE

Z80 = 1.2815515655446004
CORTES = (2022, 2023, 2024)
B_BOOT = 2000
N_MIN_GRUPO = 30


def casos() -> pd.DataFrame:
    """Traspasos de prueba de la fase 7 (métrica L_rel) con las predicciones de A, B y la base."""
    c = pd.read_csv(CE.RAIZ / "data/modelos/adaptacion/validacion_casos.csv.gz", dtype={"persona_id": str})
    c = c[(c["metrica"] == "L_rel") & c["corte"].isin(CORTES)].copy()
    c = c[np.isfinite(c["observado"]) & np.isfinite(c["previsto"]) & (c["observado"] > 0)]
    c["o"] = np.log(c["observado"] / 100)
    c["pA_ind"] = np.log(c["previsto"] / 100)
    c["w"] = c["w_ipcw_test"].astype(float)
    # A por grupo: media ponderada de la predicción sin fuga de la fase 7 en (corte, grupo)
    gA = c.groupby(["corte", "grupo_nacionalidad"]).apply(
        lambda d: np.average(d["pA_ind"], weights=d["w"]), include_groups=False).rename("pA")
    c = c.join(gA, on=["corte", "grupo_nacionalidad"])
    # B por grupo: la tabla del motor (v3_1), nivel global_grupo, L_rel (la que usa la Landing de la candidata)
    tB = tabla_b()
    c["pB"] = c["grupo_nacionalidad"].map(lambda g: np.log1p(tB.get(g, tB.get("global", 0.0))))
    c["p0"] = 0.0
    return c


def tabla_b() -> dict:
    sim = yaml.safe_load((CE.RAIZ / "configs" / "simulation_v33.yaml").read_text(encoding="utf-8"))
    t = pd.read_csv(CE.RAIZ / sim["adaptacion"]["priors"])
    g = t[(t["metrica"] == "L_rel") & t["nivel"].isin(["global_grupo", "global"])]
    out = {r.grupo_nacionalidad: float(r.delta_temporada_media) for r in g.itertuples() if r.nivel == "global_grupo"}
    gl = g[g["nivel"] == "global"]
    out["global"] = float(gl["delta_temporada_media"].iloc[0]) if len(gl) else 0.0
    return out


def mae(d: pd.DataFrame, col: str) -> float:
    return float(np.average(np.abs(d["o"] - d[col]), weights=d["w"]))


def boot_mae(d: pd.DataFrame, cols: list[str], semilla: int = 20261109) -> np.ndarray:
    """MAE ponderado de cada columna en B remuestreos por persona (multinomial de conglomerados)."""
    rng = np.random.default_rng(semilla)
    pid = d["persona_id"].to_numpy()
    u, inv = np.unique(pid, return_inverse=True)
    W = d["w"].to_numpy()
    E = np.column_stack([np.abs(d["o"].to_numpy() - d[c].to_numpy()) for c in cols])
    out = np.empty((B_BOOT, len(cols)))
    for b in range(B_BOOT):
        k = rng.multinomial(len(u), np.full(len(u), 1 / len(u)))[inv] * W
        out[b] = (k[:, None] * E).sum(0) / k.sum()
    return out


def _ic(x: np.ndarray) -> list[float]:
    return [float(np.quantile(x, 0.025)), float(np.quantile(x, 0.975))]


def tabla_mae(d: pd.DataFrame) -> dict:
    cols = ["pA", "pB", "p0", "pA_ind"]
    bs = boot_mae(d, cols)
    m = {k: mae(d, k) for k in cols}
    j = {c: i for i, c in enumerate(cols)}
    dif = lambda a, b: {"punto": m[a] - m[b], "ic95": _ic(bs[:, j[a]] - bs[:, j[b]])}  # noqa: E731
    return {"n": int(len(d)), "mae": m, "A_menos_B": dif("pA", "pB"), "A_menos_base": dif("pA", "p0"),
            "B_menos_base": dif("pB", "p0"), "Aind_menos_base": dif("pA_ind", "p0")}


def representatividad(d: pd.DataFrame) -> dict:
    filas = []
    for g, h in d.groupby("grupo_nacionalidad"):
        if len(h) < N_MIN_GRUPO:
            continue
        w = h["w"].to_numpy()
        mu = float(np.average(h["o"], weights=w))
        neff = w.sum() ** 2 / (w ** 2).sum()
        sd = float(np.sqrt(np.average((h["o"] - mu) ** 2, weights=w)))
        se = sd / np.sqrt(neff)
        lo, hi = mu - Z80 * se, mu + Z80 * se
        pa, pb = float(np.average(h["pA"], weights=w)), float(h["pB"].iloc[0])
        filas.append({"grupo": g, "n": int(len(h)), "observado_pct": 100 * np.expm1(mu), "ic80_pct": [100 * np.expm1(lo), 100 * np.expm1(hi)],
                      "A_pct": 100 * np.expm1(pa), "B_pct": 100 * np.expm1(pb),
                      "A_dentro": bool(lo <= pa <= hi), "B_dentro": bool(lo <= pb <= hi),
                      "A_signo": bool(np.sign(pa) == np.sign(mu)), "B_signo": bool(np.sign(pb) == np.sign(mu))})
    k = len(filas)
    return {"grupos": filas, "n_grupos": k,
            "A_dentro": sum(f["A_dentro"] for f in filas) / k if k else np.nan,
            "B_dentro": sum(f["B_dentro"] for f in filas) / k if k else np.nan,
            "A_signo": sum(f["A_signo"] for f in filas) / k if k else np.nan,
            "B_signo": sum(f["B_signo"] for f in filas) / k if k else np.nan}


def cobertura_a(d: pd.DataFrame) -> float:
    return float(np.average((d["observado"] >= d["pi_lo"]) & (d["observado"] <= d["pi_hi"]), weights=d["w"]))


def decidir(conj: dict, por_corte: dict, rep: dict) -> dict:
    ab = conj["A_menos_B"]
    if ab["ic95"][1] < 0:
        gana, motivo = "A", "MAE conjunto menor con IC95 de A − B que excluye 0"
    elif ab["ic95"][0] > 0:
        gana, motivo = "B", "MAE conjunto menor con IC95 de A − B que excluye 0"
    elif rep["A_dentro"] != rep["B_dentro"]:
        gana = "A" if rep["A_dentro"] > rep["B_dentro"] else "B"
        motivo = "IC95 de A − B incluye 0; decide la representatividad por grupo"
    else:
        gana = "A" if conj["mae"]["pA"] <= conj["mae"]["pB"] else "B"
        motivo = "empate en MAE y representatividad; decide el MAE puntual"
    k = {"A": "A_menos_base", "B": "B_menos_base"}[gana]
    cada = all(por_corte[t][k]["ic95"][1] < 0 for t in por_corte)
    sello = "ALTA" if cada else "MEDIA" if conj[k]["ic95"][1] < 0 else "BAJA"
    return {"gana": gana, "motivo": motivo, "sello": sello,
            "reajuste_B_sin_fuga_necesario": gana == "B"}


def ejecutar() -> dict:
    d = casos()
    por_corte = {int(t): tabla_mae(h) for t, h in d.groupby("corte")}
    conj = tabla_mae(d)
    rep = representatividad(d)
    res = {"prerregistro": "configs/ecosistema_v41.yaml → f4.k3_landing (commit 63cd324)",
           "objetivo": "log(L_rel observado/100) frente a ŷ de la normalización; cortes 2022–2024; IPCW; bootstrap por persona B = 2000",
           "sesgo_observado_pct": 100 * np.expm1(float(np.average(d["o"], weights=d["w"]))),
           "por_corte": por_corte, "conjunto": conj, "representatividad": rep,
           "cobertura_80_A": cobertura_a(d), "tabla_B": tabla_b()}
    res["decision"] = decidir(conj, por_corte, rep)
    sal = CE.RAIZ / "data/modelos/v4_1/producto"
    sal.mkdir(parents=True, exist_ok=True)
    (sal / "examen_landing.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return res
