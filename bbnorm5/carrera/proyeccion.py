"""F4 · Proyección a la temporada siguiente, con dos objetos publicados por separado (decisión 3 de la puerta F4):

1. **Nivel de carrera proyectado**: la capacidad persistente del jugador en su liga y rol para la temporada siguiente
   (sin el ruido de muestreo de esa temporada ni su transitorio). Es el intervalo que se estrecha con el historial.
2. **Producción esperada**: lo que registrará en la temporada siguiente **dado un volumen**, con el transitorio de la
   temporada y el azar de las oportunidades. Es más ancha por naturaleza. El volumen por defecto es el de su última
   temporada (`volumen_supuesto`); el volumen y el rol reales se proyectan en las capas de contexto (F6–F7).

Sólo se proyecta a quien jugó alguna de las dos últimas temporadas. Supuesto de esta fase: misma liga y rol que en su última temporada; la media del rol es la de la última temporada
disponible de esa liga (la F6 añade el cambio de liga).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import special

from bbnorm5.carrera import examen as EX
from bbnorm5.carrera import modelo as MOD
from bbnorm5.medida import datos as DM
from bbnorm5.medida import eb

S = 1000


def proyectar(o: pd.DataFrame, mod: dict, h: pd.DataFrame, metrica: str, anio: int, rng) -> pd.DataFrame:
    fam = DM.METRICAS[metrica][0]
    M = MOD.matrices(o)
    ult = o.sort_values("anio").drop_duplicates("persona_v5", keep="last")
    ult = ult[ult["anio"] >= anio - 2]          # sólo jugadores con temporada en las dos últimas
    obj = ult[["persona_v5", "liga", "rol", "edad", "anio", "K", "N", "N2g", "temporada"]].copy()
    obj["gap"] = (anio - obj["anio"]).astype(float)
    obj["edad"] = obj["edad"] + obj["gap"]
    obj["cl"], obj["cr"], obj["dmu"] = 0.0, 0.0, 0.0
    obj = obj.merge(EX._liga_previa(h, metrica, anio), on=["liga", "rol"])
    p = MOD.predecir(M, mod, obj)
    inv = {"binomial": special.expit, "poisson": np.exp}.get(fam, lambda z: z)
    n = len(p)
    z = rng.standard_normal((n, S))
    eta_nivel = (p["mu_prev"] + p["m_nivel"]).to_numpy()[:, None] + np.sqrt(p["v_nivel"].to_numpy())[:, None] * z
    sd_u = np.sqrt(np.maximum(p["v_y_sin_muestreo"] - p["v_nivel"], 0)).to_numpy()[:, None]
    tasa_nivel = inv(eta_nivel)
    tasa = inv(eta_nivel + sd_u * rng.standard_normal((n, S)))
    N = p["N"].to_numpy(float)
    Nr = np.maximum(np.round(N), 1.0) if fam == "binomial" else N
    disp = p["disp_prev"].to_numpy(float)
    if fam == "normal":
        Ks = tasa * Nr[:, None] + np.sqrt(disp[:, None] * Nr[:, None]) * rng.standard_normal(tasa.shape)
    else:
        Ks = eb.muestras_conteo(tasa, Nr, p["N2g"].to_numpy(float), fam, disp, rng)
    prod = Ks / Nr[:, None]
    qn = np.quantile(tasa_nivel, [0.1, 0.5, 0.9], axis=1)
    qp = np.quantile(prod, [0.1, 0.5, 0.9], axis=1)
    return pd.DataFrame({
        "persona_v5": p["persona_v5"], "metrica": metrica, "temporada_objetivo": f"{anio}-{str(anio + 1)[2:]}",
        "liga": p["liga"], "rol": p["rol"], "ultima_temporada": p["temporada"], "temporadas_hist": p["temporadas_hist"],
        "edad": p["edad"],
        "nivel_media": tasa_nivel.mean(axis=1), "nivel_q10": qn[0], "nivel_q50": qn[1], "nivel_q90": qn[2],
        "volumen_supuesto": N, "produccion_media": prod.mean(axis=1),
        "produccion_q10": qp[0], "produccion_q50": qp[1], "produccion_q90": qp[2]})
