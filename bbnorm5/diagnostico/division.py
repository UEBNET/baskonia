"""F1 §5.1 · Punto de estabilización por división de muestra (partidos pares / impares).

Tabla jugador-partido `data/modelos/roles/partidos_jugador/<t>.csv.gz` (temporada regular, partidos jugados). Para cada
jugador × liga × temporada se ordenan sus partidos por fecha y se reparten en dos mitades alternas. En cada mitad h se
calcula la métrica con sus propios conteos (y_h, en la escala de trabajo T de la v1) y su exposición n_h.

Dos estimadores:
  1. Clásico: r = corr(y_1, y_2) tras quitar la media de liga-temporada-posición; fiabilidad de la temporada completa
     por Spearman-Brown ρ = 2r/(1 + r); n* = n̄_mitad (1 − r)/r.
  2. Momentos con exposición heterogénea (el que se compara con el REML): con y_h = θ + ε_h, Var(ε_h) = σ²/n_h,
        Cov(y_1, y_2) = Var(θ)                       → señal de la temporada (σ²_a + σ²_u en el REML)
        E[(y_1 − y_2)² / (1/n_1 + 1/n_2)] = σ²       → ruido por unidad de exposición
        n* = σ² / Var(θ)                              → exposición con fiabilidad 0,5 (= n*_temp del REML)

Sólo métricas que se pueden reconstruir con las columnas de la tabla jugador-partido (tiro, puntos, asistencias y
canastas asistidas). Rebote, robos, tapones, pérdidas y faltas no están por partido (dependencia D1 de la F0).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from bbmodel.metricas import CATALOGO, transformar

# métrica → (numerador, denominador = exposición, escala) con columnas de partidos_jugador
DEF = {
    "pts_p100": (lambda g: g["pts"], lambda g: g["poss_on"], 100.0),
    "ts_pct": (lambda g: g["pts"] / 2.0, lambda g: g["fga"] + 0.44 * g["fta"], 100.0),
    "efg_pct": (lambda g: g["fgm"] + 0.5 * g["fg3m"], lambda g: g["fga"], 100.0),
    "fg2_pct": (lambda g: g["fgm"] - g["fg3m"], lambda g: g["fga"] - g["fg3a"], 100.0),
    "fg3_pct": (lambda g: g["fg3m"], lambda g: g["fg3a"], 100.0),
    "ft_pct": (lambda g: g["ftm"], lambda g: g["fta"], 100.0),
    "fg3a_rate": (lambda g: g["fg3a"], lambda g: g["fga"], 100.0),
    "fta_rate": (lambda g: g["fta"], lambda g: g["fga"], 100.0),
    "pct_asistidas": (lambda g: g["fgm_asist"], lambda g: g["fgm"], 100.0),
    # AST% ≈ AST / (canastas del equipo con él en pista − las suyas); la exposición del REML son minutos
    "ast_pct": (lambda g: g["ast"], lambda g: g["team_fgm_on"] - g["fgm"], 100.0),
}
EXPOSICION_PROPIA = {"ast_pct": "min"}      # exposición con la que se expresa n* (la del catálogo)


def cargar(temporadas: list[str], raiz) -> pd.DataFrame:
    cols = ["liga", "temporada", "game_id", "fase", "player_id", "fecha", "jugo", "min", "poss_on", "pts", "fga",
            "fgm", "fg3a", "fg3m", "fta", "ftm", "ast", "fgm_asist", "team_fgm_on", "pos3"]
    fr = []
    for t in temporadas:
        f = raiz / "data" / "modelos" / "roles" / "partidos_jugador" / f"{t}.csv.gz"
        if f.exists():
            d = pd.read_csv(f, usecols=lambda c: c in cols, low_memory=False)
            fr.append(d[(d["fase"] == "regular") & (d["jugo"].astype(str).str.lower().isin(["true", "1"]))])
    d = pd.concat(fr, ignore_index=True)
    d = d[d["fecha"].notna()]
    d = d.sort_values(["liga", "temporada", "player_id", "fecha", "game_id"])
    d["mitad"] = d.groupby(["liga", "temporada", "player_id"]).cumcount() % 2
    return d


def mitades(d: pd.DataFrame, min_partidos: int) -> pd.DataFrame:
    num = ["min", "poss_on", "pts", "fga", "fgm", "fg3a", "fg3m", "fta", "ftm", "ast", "fgm_asist", "team_fgm_on"]
    g = d.groupby(["liga", "temporada", "player_id", "mitad"])
    s = g[num].sum()
    s["partidos"] = g.size()
    s["pos3"] = g["pos3"].first()
    s = s.reset_index()
    a = s[s["mitad"] == 0].drop(columns="mitad").set_index(["liga", "temporada", "player_id"])
    b = s[s["mitad"] == 1].drop(columns="mitad").set_index(["liga", "temporada", "player_id"])
    m = a.join(b, lsuffix="_1", rsuffix="_2", how="inner").reset_index()
    return m[(m["partidos_1"] >= min_partidos) & (m["partidos_2"] >= min_partidos)].reset_index(drop=True)


def estimar(m: pd.DataFrame, col: str) -> dict:
    num, den, esc = DEF[col]
    tr = CATALOGO[col].transf
    h1 = m[[c for c in m.columns if c.endswith("_1")]].rename(columns=lambda c: c[:-2])
    h2 = m[[c for c in m.columns if c.endswith("_2")]].rename(columns=lambda c: c[:-2])
    n1, n2 = den(h1).to_numpy(float), den(h2).to_numpy(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        y1 = transformar(esc * num(h1).to_numpy(float) / n1, tr)
        y2 = transformar(esc * num(h2).to_numpy(float) / n2, tr)
    ok = np.isfinite(y1) & np.isfinite(y2) & (n1 > 0) & (n2 > 0)
    x = pd.DataFrame({"g": (m["liga"] + "|" + m["temporada"] + "|" + m["pos3_1"].fillna("A"))[ok],
                      "y1": y1[ok], "y2": y2[ok], "n1": n1[ok], "n2": n2[ok]})
    # media de liga-temporada-posición (común a las dos mitades): equivale al b fijo del REML
    mu = ((x["y1"] + x["y2"]) / 2).groupby(x["g"]).transform("mean")
    e1, e2 = x["y1"] - mu, x["y2"] - mu
    r = float(np.corrcoef(e1, e2)[0, 1])
    sb = 2 * r / (1 + r)
    nh = float(np.mean((x["n1"] + x["n2"]) / 2))
    cov = float(np.mean(e1 * e2))
    s2 = float(np.mean((x["y1"] - x["y2"]) ** 2 / (1 / x["n1"] + 1 / x["n2"])))
    # n* en la exposición del catálogo si difiere (AST%: minutos); conversión por la razón media de exposiciones
    factor = 1.0
    if col in EXPOSICION_PROPIA:
        mins = (m["min_1"] + m["min_2"]).to_numpy(float)[ok]
        factor = float(np.sum(mins) / np.sum(x["n1"] + x["n2"]))
    # IC por bootstrap de jugadores (500 réplicas)
    rng = np.random.default_rng(0)
    bs = []
    idx = np.arange(len(x))
    for _ in range(500):
        k = rng.choice(idx, len(idx))
        cv = np.mean(e1.to_numpy()[k] * e2.to_numpy()[k])
        s2b = np.mean(((x["y1"] - x["y2"]) ** 2 / (1 / x["n1"] + 1 / x["n2"])).to_numpy()[k])
        bs.append(s2b / cv if cv > 0 else np.inf)
    lo, hi = np.quantile(bs, [0.1, 0.9])
    return {"metrica": col, "jugadores_temporada": int(ok.sum()), "r_mitades": r, "rho_spearman_brown": sb,
            "n_mitad_medio": nh * factor, "n_estab_clasico": (nh * (1 - r) / r) * factor if r > 0 else np.inf,
            "senal_cov": cov, "s2_ruido": s2, "n_estab_momentos": (s2 / cov) * factor if cov > 0 else np.inf,
            "n_estab_momentos_lo80": lo * factor, "n_estab_momentos_hi80": hi * factor,
            "unidad_exposicion": CATALOGO[col].exposicion}
