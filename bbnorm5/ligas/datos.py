"""F6.1 · Datos de la capa de ligas: diferencias de cada puente intra-temporada por métrica.

Un puente intra-temporada es la misma persona, la misma temporada, en dos competiciones (F2): mismo club en Europa y en
su liga, NBA ↔ G League, o traspaso a mitad de temporada. Para cada métrica m y puente p (ligas a y b):

    d_pm = enlace(tasa_b) − enlace(tasa_a)              (escala del enlace absoluta, sin restar la media de la liga)
    var(d_pm) = v_a + v_b                               (muestreo de cada lado: binomial con la sobredispersión de la
                                                         F3, Poisson·(1+δ) o φ/N; la tasa de la varianza se encoge
                                                         hacia la media de su liga-temporada con n*)
    Δx_p = contexto b − contexto a: log(min/partido), % de titularidades, calidad del rival (margen medio del rival,
           /10) y ritmo en pista (posesiones del equipo por 40 min, en log)

La capacidad del jugador esa temporada se cancela en la diferencia: queda el efecto de liga (λ_b − λ_a), el del
contexto y el ruido.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import special

from bbnorm5 import config as C
from bbnorm5.medida import datos as DM

DIR = C.DIR_DATOS / "ligas"
CONTEXTO = ["d_log_min_pp", "d_titular", "d_rival", "d_log_ritmo"]


def _lado(pi: pd.DataFrame, s: str, metrica: str, h: pd.DataFrame) -> pd.DataFrame:
    fam, kc, nc, _ = DM.METRICAS[metrica]
    K = pi[f"{kc}_{s}"].to_numpy(float)
    N = pi[f"{nc}_{s}"].to_numpy(float)
    G = pi[f"partidos_{s}"].to_numpy(float)
    hh = h[h["metrica"] == metrica].set_index(["liga", "temporada"])
    idx = pd.MultiIndex.from_arrays([pi[f"liga_{s}"], pi["temporada"]])
    disp = hh["disp"].reindex(idx).to_numpy(float)
    t_lig = hh["tasa_media"].reindex(idx).to_numpy(float)
    n_est = hh["n_estab"].reindex(idx).to_numpy(float)
    if fam == "binomial":
        N = np.maximum(N, K)
        pt = (K + n_est * t_lig) / (N + n_est)
        infl = 1 + disp * np.maximum(N / np.maximum(G, 1) - 1, 0)
        y = special.logit((K + 0.5) / (N + 1))
        v = infl / (N * pt * (1 - pt))
    elif fam == "poisson":
        lt = (K + n_est * t_lig) / (N + n_est)
        y = np.log((K + 0.5) / N)
        v = (1 + disp) / (N * lt)
    else:
        y = K / N
        v = disp / N
    return pd.DataFrame({"y": y, "v": v, "N": N})


def _con_pista(pi: pd.DataFrame) -> pd.DataFrame:
    """F9 bis: añade a cada lado del puente los conteos de jugada a jugada (zonas y asistidas) de la capa de medida,
    sumados por persona, liga y temporada (temporada regular, como el resto de la medida)."""
    cols = sorted({c for _, k, n, _ in DM.METRICAS_PBP.values() for c in (k, n)})
    if all(f"{c}_a" in pi.columns for c in cols):
        return pi
    d = pd.read_parquet(DM.DIR / "partidos.parquet", columns=["persona_v5", "liga", "temporada"] + cols)
    s = d.groupby(["persona_v5", "liga", "temporada"])[cols].sum(min_count=1).reset_index()
    for lado in ("a", "b"):
        pi = pi.merge(s.rename(columns={"liga": f"liga_{lado}", **{c: f"{c}_{lado}" for c in cols}}),
                      on=["persona_v5", f"liga_{lado}", "temporada"], how="left")
    return pi


def pares(temporadas: list[str], min_minutos: float = 50.0) -> pd.DataFrame:
    """Tabla larga: una fila por puente y métrica."""
    pi = pd.read_parquet(C.DIR_DATOS / "puentes" / "puentes_intra.parquet")
    pi = pi[pi["temporada"].isin(temporadas) & (pi["min_a"] >= min_minutos) & (pi["min_b"] >= min_minutos)].reset_index(drop=True)
    pi = _con_pista(pi)
    h = pd.read_csv(DM.DIR / "hiperparametros.csv")
    h = h[h["datos"] == "temporada"].sort_values("modelo").drop_duplicates(["liga", "temporada", "metrica"], keep="last")
    ctx = pd.DataFrame({
        "d_log_min_pp": np.log(pi["min_pp_b"] / pi["min_pp_a"]),
        "d_titular": pi["pct_titular_b"] - pi["pct_titular_a"],
        "d_rival": (pi["rival_margen_b"] - pi["rival_margen_a"]) / 10,
        "d_log_ritmo": np.log((pi["poss_on_b"] / pi["min_b"]) / (pi["poss_on_a"] / pi["min_a"])),
    }).fillna(0.0)
    filas = []
    for met in DM.METRICAS:
        a, b = _lado(pi, "a", met, h), _lado(pi, "b", met, h)
        x = pd.DataFrame({"puente": np.arange(len(pi)), "persona_v5": pi["persona_v5"], "temporada": pi["temporada"],
                          "liga_a": pi["liga_a"], "liga_b": pi["liga_b"], "tipo": pi["tipo"], "metrica": met,
                          "d": b["y"] - a["y"], "var": a["v"] + b["v"], "N_a": a["N"], "N_b": b["N"]})
        x = pd.concat([x, ctx], axis=1)
        ok = np.isfinite(x["d"]) & np.isfinite(x["var"]) & (x["var"] > 0) & (x["N_a"] > 0) & (x["N_b"] > 0)
        filas.append(x[ok])
    out = pd.concat(filas, ignore_index=True)
    DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(DIR / "pares_intra.parquet")
    return out


def fuerza_enfrentamientos() -> pd.DataFrame:
    """Fuerza por liga y temporada de los partidos europeos (F2), en puntos de margen frente a la ACB."""
    f = pd.read_csv(C.DIR_DATOS / "limpios" / "enfrentamientos" / "fuerza_ligas.csv")
    f["liga"] = f["liga"].str.replace("sin_liga_", "", regex=False)
    return f
