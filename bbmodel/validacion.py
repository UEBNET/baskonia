"""Validación: ¿predice el algoritmo A cómo rinde un jugador al cambiar de liga?

Examen honesto (sin mirar el futuro):
  1. Se ajusta el modelo SÓLO con temporadas hasta t.
  2. Se toman los jugadores que cambiaron de liga entre t y t+1 (jugaban en l, pasan a l' sin
     haber jugado en l' en t), con 300+ minutos en ambas.
  3. Se predice su métrica en l' en t+1 y se compara con lo que realmente hicieron.

Tres predictores:
  * «mismo número»: se supone que repite el valor de su liga de origen.
  * «mismo percentil»: se supone que ocupa en l' el mismo puesto relativo (z sin suerte) que en l.
    Es lo que hace casi todo el mundo (normalizar dentro de cada liga).
  * «algoritmo A»: tipo de cambio + edad + quitar suerte y contexto.
El entorno de la liga de destino se toma de la temporada t (el futuro no se conoce).

Métricas del examen: error absoluto medio (MAE) en unidades reales, mejora de error cuadrático
frente a «mismo percentil», y cobertura del intervalo del 80 % (debería contener ~80 % de los casos).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from . import enlace, modelo
from .metricas import CATALOGO, EXPOSICIONES, destransformar, transformar

MIN_MIN = 300


def casos(t: pd.DataFrame, anio: int) -> pd.DataFrame:
    """Parejas (origen t, destino t+1) de jugadores que cambian de liga."""
    a = t[(t["anio"] == anio) & (t["min"] >= MIN_MIN)]
    b = t[(t["anio"] == anio + 1) & (t["min"] >= MIN_MIN)]
    origen = a.sort_values("min", ascending=False).drop_duplicates("persona_id")
    ligas_t = a.groupby("persona_id")["liga"].agg(set)
    destino = b[~b.apply(lambda r: r["liga"] in ligas_t.get(r["persona_id"], set()), axis=1)]
    destino = destino.sort_values("min", ascending=False).drop_duplicates("persona_id")
    return origen.reset_index().merge(destino.reset_index(), on="persona_id", suffixes=("_o", "_d"))


def evaluar(t: pd.DataFrame, anio: int, params: dict) -> pd.DataFrame:
    c = casos(t, anio)
    filas = []
    for col, p in params["metricas"].items():
        m = CATALOGO[col]
        e = p["enlace"]; s1 = p["suerte"]
        z = params["_z"][col]
        for _, r in c.iterrows():
            lo, ld, pos = r["liga_o"], r["liga_d"], r["pos3_o"]
            y_real = r[f"{col}_d"]
            if not isinstance(pos, str) or lo not in e["m"] or ld not in e["m"] or not np.isfinite(y_real):
                continue
            zo, vo = z.loc[r["index_o"], ["z_obs", "v_obs"]]
            if not np.isfinite(zo):
                continue
            temp_t = f"{anio}-{str(anio + 1)[-2:]}"
            mu_d, tau_d = modelo._entorno(s1, ld, temp_t, pos)
            if not np.isfinite(mu_d):
                continue
            # predictor 1: mismo número
            p_num = r[f"{col}_o"]
            # predictor 2: mismo percentil (z sin suerte en su liga)
            z_pct = zo / (1 + vo)
            p_pct = destransformar(mu_d + tau_d * z_pct, m.transf)
            # predictor 3: algoritmo A
            a, va = modelo.capacidad(zo, vo, lo, e)
            edad = r["anio_o"] - r["anio_nac_o"]
            a1 = a + e["deriva"].get(enlace.tramo_edad(edad), 0.0)
            va1 = va + e["eta2"]
            zd = (a1 - e["m"][ld]) / e["s"][ld]
            vzd = va1 / e["s"][ld] ** 2
            p_a = destransformar(mu_d + tau_d * zd, m.transf)
            # intervalo del 80 % para el valor OBSERVADO (incluye su ruido de muestra y contexto)
            n_d = r[f"{EXPOSICIONES[m.exposicion]}_d"] if f"{EXPOSICIONES[m.exposicion]}_d" in r else np.nan
            ruido = s1["sigma2"].get(ld, s1["sigma2"].get("todas", np.nan)) / (n_d * tau_d ** 2) if np.isfinite(n_d) and n_d > 0 else 0
            sd = np.sqrt(vzd + e["psi"][ld] + ruido)
            y_t = float(transformar(y_real, m.transf))
            dentro = abs(y_t - (mu_d + tau_d * zd)) <= modelo.Z80 * tau_d * sd
            filas.append({"metrica": col, "anio": anio, "persona_id": r["persona_id"], "nombre": r["nombre_o"],
                          "liga_o": lo, "liga_d": ld, "real": y_real, "mismo_numero": p_num, "mismo_percentil": p_pct,
                          "algoritmo_A": p_a, "dentro_80": dentro})
    return pd.DataFrame(filas)


def resumir(res: pd.DataFrame) -> pd.DataFrame:
    out = []
    for (col), g in res.groupby("metrica"):
        e = {k: np.abs(g[k] - g["real"]) for k in ("mismo_numero", "mismo_percentil", "algoritmo_A")}
        mse = {k: float(np.mean(v ** 2)) for k, v in e.items()}
        out.append({"metrica": col, "nombre": CATALOGO[col].nombre, "casos": len(g),
                    "mae_mismo_numero": float(e["mismo_numero"].mean()), "mae_mismo_percentil": float(e["mismo_percentil"].mean()),
                    "mae_algoritmo_A": float(e["algoritmo_A"].mean()),
                    "mejora_vs_percentil_%": 100 * (1 - mse["algoritmo_A"] / mse["mismo_percentil"]),
                    "mejora_vs_numero_%": 100 * (1 - mse["algoritmo_A"] / mse["mismo_numero"]),
                    "cobertura_80": float(g["dentro_80"].mean())})
    return pd.DataFrame(out)
