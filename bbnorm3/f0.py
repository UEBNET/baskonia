"""Línea base F0: los niveles del grafo amortiguado actual (bbmodel/amortiguacion.py, variante elegida) con su
COVARIANZA COMPLETA.

El amortiguado de la v2 calcula el intervalo de una traducción a → b sumando las varianzas marginales de los dos
niveles, var(δ_a) + var(δ_b), lo que cuenta dos veces la incertidumbre del camino de puentes que comparten (defecto 1
del encargo). F0 usa la misma predicción puntual pero con Var(δ_b − δ_a) = Σ_aa + Σ_bb − 2Σ_ab, tomando Σ de la
posterior conjunta de la contracción jerárquica (`contraccion_jerarquica(...)["cov"]`). Mismo examen sin fuga.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from bbmodel import amortiguacion as AM
from bbmodel.metricas import CATALOGO, EXPOSICIONES, transformar

from .prediccion import Z80


def predecir_f0(tabla: pd.DataFrame, anio: int, params: dict, ajuste: dict) -> pd.DataFrame:
    from bbmodel import enlace as E, modelo, validacion
    c = validacion.casos(tabla, anio)
    temp_t = f"{anio}-{str(anio + 1)[-2:]}"
    filas = []
    for col in ajuste["resultados"]:
        p = params["metricas"][col]
        e, s1, m = p["enlace"], p["suerte"], CATALOGO[col]
        z = params["_z"][col]
        r = ajuste["resultados"][col]
        est, ch, nodos_g, ref_nodos = r["estado"], r["contraccion"], r["nodos_g"], r["ref_nodos"]
        cov = ch["cov"]

        def kg(nodo):
            if nodo in ref_nodos or nodo.startswith(ajuste["ref"] + ":"):
                return 0
            return nodos_g.index(nodo) if nodo in nodos_g else None

        for _, x in c.iterrows():
            lo, ld, pos = x["liga_o"], x["liga_d"], x["pos3_o"]
            y_real = x[f"{col}_d"]
            if not isinstance(pos, str) or lo not in e["m"] or ld not in e["m"] or not np.isfinite(y_real):
                continue
            zo, vo = z.loc[x["index_o"], ["z_obs", "v_obs"]]
            if not np.isfinite(zo):
                continue
            mu_d, tau_d = modelo._entorno(s1, ld, temp_t, pos)
            if not np.isfinite(mu_d):
                continue
            no, nd = f"{lo}:{x['temporada_o']}", f"{ld}:{temp_t}"
            ko, kd = kg(no), kg(nd)
            if ko is None or kd is None:
                continue
            th, vth = AM.theta(ajuste, col, lo, no, np.array([zo]), np.array([vo]))
            dv_o = est.delta_var[est.idx[no]] if no in est.idx and lo != ajuste["ref"] else 0.0
            edad = x["anio_o"] - x["anio_nac_o"]
            th1 = th[0] + e["deriva"].get(E.tramo_edad(edad), 0.0)
            v_jug = vth[0] - dv_o + e["eta2"]            # parte del jugador (sin la del nivel de origen)
            if ld == ajuste["ref"]:
                dl_d, lam_d, F_d = 0.0, 1.0, AM.Mapeo()
            else:
                dl_d, lam_d = est.delta[est.idx[nd]], est.lam.get(ld, 1.0)
                F_d = est.F.get(ld) or AM.Mapeo()
            v_par = cov[ko, ko] + cov[kd, kd] - 2 * cov[ko, kd]   # Σ_oo + Σ_dd − 2Σ_od (0 en la referencia)
            s_d = e["s"][ld]
            u = (th1 - dl_d) / lam_d
            xd = F_d.inversa(np.array([u]))[0]
            if not np.isfinite(xd):
                continue
            zd = xd / s_d
            der = lam_d * s_d * float(F_d.derivada(np.array([xd]))[0])
            vzd = (v_jug + max(v_par, 0.0)) / max(der, 1e-3) ** 2
            n_d = x.get(f"{EXPOSICIONES[m.exposicion]}_d", np.nan)
            ruido = s1["sigma2"].get(ld, s1["sigma2"].get("todas", np.nan)) / (n_d * tau_d ** 2) \
                if np.isfinite(n_d) and n_d > 0 else 0
            sd = np.sqrt(vzd + e["psi"][ld] + ruido)
            y_t = float(transformar(y_real, m.transf))
            filas.append({"metrica": col, "anio": anio, "nombre": x["nombre_o"], "liga_o": lo, "liga_d": ld,
                          "real": y_real, "dentro_80_F0": bool(abs(y_t - (mu_d + tau_d * zd)) <= Z80 * tau_d * sd),
                          "sd_par_completa": float(np.sqrt(max(v_par, 0))),
                          "sd_par_marginal": float(np.sqrt(max(cov[ko, ko] + cov[kd, kd], 0)))})
    return pd.DataFrame(filas)


def f0_corte(tabla: pd.DataFrame, anio: int, bootstrap: int = 10) -> pd.DataFrame:
    from bbmodel import modelo
    cfg = AM.config()
    op = AM.opciones_variante(cfg, cfg.get("variante", "sin_mapeo"))
    p = modelo.ajustar(tabla, hasta_anio=anio, n_boot=bootstrap, progreso=None)
    aj = AM.ajustar(tabla[tabla["anio"] <= anio], p, cfg, hasta_anio=None, progreso=None, **op)
    aj["hasta_anio"] = anio
    return predecir_f0(tabla, anio, p, aj)
