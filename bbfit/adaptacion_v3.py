"""Adaptación v3: ADAPT% como curva ASCENDENTE hacia el nivel adaptado (corrige la forma de la fase 7 / v2).

Qué estaba mal en la v2 (docs/adaptacion_v3.md): la trayectoria del simulador era
    T(g) = (1 + c·Δ_temp) · (1 + D·e^(−g/κ)) / (1 + D·w̄)
con Δ_temp = efecto de NIVEL de la temporada frente a lo esperado tras la normalización (positivo en el 68 % de las
celdas: los que cambian de liga rinden algo más de lo que traduce la normalización) y D = hueco inicial NETO del
«arranque de temporada» de los que siguen en su equipo (casi siempre ≥ 0). Resultado: curvas que empiezan por encima
y bajan (convexas, descendentes), lo contrario de lo que significa «adaptarse».

Definición v3 (la del CEO): la adaptación es la fracción del nivel ADAPTADO que el jugador rinde en el partido g de
su nueva liga:
    ADAPT%(g) = 100 · (1 + D·e^(−g/κ)),   D ≤ 0
empieza por debajo del 100 % (p. ej. 95 %) y sube hasta el 100 % cuando el jugador está establecido. D y κ salen de la
curva BRUTA dentro de jugador de los traspasos (bbfit.adaptacion.ajustar_curvas, población «traspasos_bruto»: su
propio arranque en la liga nueva, sin restar el de los que se quedan), contraída hacia el global por grupo
(bayes empírico) y acotada a D ≤ 0 (un D > 0 significaría empezar por ENCIMA del nivel adaptado: no es adaptación).
El nivel lo pone la normalización v3.1, validada directamente sobre el rendimiento real de quienes cambian de liga;
el efecto Δ_temp deja de llamarse «adaptación» y no se aplica.

Forma de la tabla para el motor (Python y JS, sin cambiar su código):
    delta_temporada = D · w̄_G   sólo en la métrica L_rel (la ADAPT% mostrada; w̄_G = media de e^(−g/κ) en los G
                                partidos de la liga de destino); 0 en la producción y en L, que ya salen de la v3.1
                                (su promedio de temporada incluye el arranque: aplicarlo otra vez lo contaría dos veces)
    D_forma = D,  κ_forma = κ,  delta_media = D,  kappa_media = κ  (interfaz 1 + δ·e^(−g/κ) también ascendente)
con contracción 1 (configs/simulation_v3.yaml): el motor calcula curva(g) = (1 + D·w̄)·(1 + D·φ_g)/(1 + D·w̄) =
1 + D·φ_g, ADAPT% de la temporada = 100·(1 + D·w̄) ≤ 100 y de los N primeros = media de 100·(1 + D·φ_g).

    python -m bbfit adaptacion-v3   → data/modelos/adaptacion/v3/{adaptation_priors.csv, curvas_v3.csv, resumen.json}
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .config import DIR_MOD, RAIZ, cargar

DIR_V3 = DIR_MOD / "adaptacion" / "v3"
Z90 = 1.6448536269514722


def _se(lo, hi) -> float:
    return float((hi - lo) / (2 * Z90)) if np.isfinite(lo) and np.isfinite(hi) and hi > lo else np.nan


def curvas_ascendentes(curvas: pd.DataFrame, perfil: str = "grupo_nacionalidad") -> pd.DataFrame:
    """D y κ por serie y grupo de la curva bruta de los traspasos, contraídos hacia el global y con D ≤ 0."""
    filas = []
    for serie, c in curvas[curvas["poblacion"] == "traspasos_bruto"].groupby("serie"):
        g0 = c[c["perfil"] == "global=global"].iloc[0]
        Dg, kg = float(g0["D"]), float(g0["kappa"])
        grp = c[c["perfil"].str.startswith(perfil + "=")].copy()
        grp["se_D"] = [_se(a, b) for a, b in zip(grp["D_lo"], grp["D_hi"])]
        grp["se_lk"] = [_se(np.log(a), np.log(b)) for a, b in zip(grp["kappa_lo"], grp["kappa_hi"])]
        # varianza entre grupos (momentos), con suelo: cuánto se parecen los grupos de verdad
        tau2_D = max(float(np.var(grp["D"]) - np.nanmean(grp["se_D"] ** 2)), 0.02 ** 2)
        tau2_k = max(float(np.var(np.log(grp["kappa"])) - np.nanmean(grp["se_lk"] ** 2)), 0.25 ** 2)
        filas.append({"serie": serie, "grupo": "global", "n_jugadores": int(g0["n_jugadores"]), "D_bruto": Dg,
                      "kappa_bruto": kg, "D": min(Dg, 0.0), "kappa": kg, "D_sd": _se(g0["D_lo"], g0["D_hi"]),
                      "acotado": Dg > 0})
        for _, r in grp.iterrows():
            wD = 1 / r["se_D"] ** 2 if np.isfinite(r["se_D"]) and r["se_D"] > 0 else 0.0
            D = (wD * r["D"] + Dg / tau2_D) / (wD + 1 / tau2_D)
            wk = 1 / r["se_lk"] ** 2 if np.isfinite(r["se_lk"]) and r["se_lk"] > 0 else 0.0
            lk = (wk * np.log(r["kappa"]) + np.log(kg) / tau2_k) / (wk + 1 / tau2_k)
            filas.append({"serie": serie, "grupo": r["perfil"].split("=", 1)[1], "n_jugadores": int(r["n_jugadores"]),
                          "D_bruto": float(r["D"]), "kappa_bruto": float(r["kappa"]), "D": min(float(D), 0.0),
                          "kappa": float(np.exp(lk)), "D_sd": float(np.sqrt(1 / (wD + 1 / tau2_D))), "acotado": D > 0})
    return pd.DataFrame(filas)


def wbar(kappa: float, G: int) -> float:
    g = np.arange(max(int(G), 1))
    return float(np.exp(-g / kappa).mean()) if np.isfinite(kappa) and kappa > 0 else 0.0


def tabla_priors(priors_v2: pd.DataFrame, cv: pd.DataFrame, partidos: dict) -> pd.DataFrame:
    """Misma tabla (mismas claves y niveles de reserva) que la v2 con las columnas de adaptación redefinidas."""
    t = priors_v2.copy()
    idx = {(r.serie, r.grupo): r for r in cv.itertuples()}
    D, K, Dsd = [], [], []
    for s, gcur in zip(t["serie_curva"], t["grupo_curva"]):
        r = idx.get((s, gcur)) or idx.get((s, "global"))
        D.append(r.D); K.append(r.kappa); Dsd.append(r.D_sd)
    t["D_forma_media"], t["kappa_forma_media"] = D, K
    t["kappa_forma_lo"], t["kappa_forma_hi"] = np.nan, np.nan
    G = [partidos.get(l, partidos["defecto"]) if isinstance(l, str) and l != "*" else partidos["defecto"]
         for l in t["liga_destino"]]
    wb = np.array([wbar(k, g) for k, g in zip(K, G)])
    # media de la temporada frente al nivel adaptado. Sólo en L_rel (la ADAPT% que se muestra): la producción y L ya
    # salen de la v3.1, que predice el promedio de temporada de quien cambia de liga (con su arranque incluido); aplicarles
    # también 1 + D·w̄ contaría dos veces el arranque. En el resto de métricas el factor de temporada es 1.
    solo_adapt = (t["metrica"] == "L_rel").to_numpy() if "metrica" in t else np.ones(len(t), bool)
    t["delta_temporada_media"] = np.where(solo_adapt, np.array(D) * wb, 0.0)
    t["delta_temporada_sd"] = np.where(solo_adapt, np.array(Dsd) * wb, 0.0)
    t["delta_temporada_lo"] = t["delta_temporada_media"] - Z90 * t["delta_temporada_sd"]
    t["delta_temporada_hi"] = np.minimum(t["delta_temporada_media"] + Z90 * t["delta_temporada_sd"], 0.0)
    t["p_delta_temporada_negativo"] = np.where(solo_adapt & (np.array(D) < 0), 1.0, 0.0)
    t["delta_media"], t["delta_sd"] = D, Dsd                          # interfaz 1 + δ·e^(−g/κ), δ ≤ 0
    t["delta_lo"] = t["delta_media"] - Z90 * t["delta_sd"]
    t["delta_hi"] = np.minimum(t["delta_media"] + Z90 * t["delta_sd"], 0.0)
    t["kappa_media"], t["kappa_sd"] = K, np.nan
    t["kappa_lo"], t["kappa_hi"] = np.nan, np.nan
    t["partidos_50"] = np.array(K) * np.log(2)
    t["partidos_90"] = np.array(K) * np.log(10)
    t["partidos_1a_temporada"] = G
    t["contraccion_par"] = np.nan
    return t


def main() -> dict:
    sim = cargar("simulation")
    if "salida_v3" not in sim["adaptacion"] and sim.get("carpeta", "v2") == "v2":
        sim = cargar("simulation_v3")                # sin CERNO_SIMULADOR: la v3 (como hasta ahora)
    partidos = dict(sim["adaptacion"]["partidos_temporada"])
    ca = sim["adaptacion"]
    curvas = pd.read_csv(RAIZ / ca.get("curvas_fase7", "data/modelos/adaptacion/curvas.csv"))
    cv = curvas_ascendentes(curvas)
    pr = tabla_priors(pd.read_csv(RAIZ / ca.get("priors_fase7", "data/modelos/adaptacion/adaptation_priors.csv")), cv,
                      partidos)
    dv = RAIZ / ca["salida_v3"] if ca.get("salida_v3") else DIR_V3
    dv.mkdir(parents=True, exist_ok=True)
    cv.round(5).to_csv(dv / "curvas_v3.csv", index=False)
    pr.round(5).to_csv(dv / "adaptation_priors.csv", index=False)
    N = int(sim["adaptacion"]["primeros_partidos"])
    ejemplo = {}
    for r in cv[cv["serie"] == "prod_p100"].itertuples():
        g = np.arange(N)
        ejemplo[r.grupo] = {"D": round(r.D, 4), "kappa": round(r.kappa, 2),
                            "adapt_partido_1": round(100 * (1 + r.D), 1),
                            "adapt_primeros_10": round(100 * float(np.mean(1 + r.D * np.exp(-g / r.kappa))), 1),
                            "adapt_temporada_34": round(100 * (1 + r.D * wbar(r.kappa, 34)), 1),
                            "partidos_90": round(r.kappa * np.log(10), 1), "acotado_a_0": bool(r.acotado)}
    res = {"definicion": "ADAPT%(g) = 100·(1 + D·e^(−g/κ)), D ≤ 0: fracción del nivel adaptado en el partido g",
           "fuente": "curva bruta dentro de jugador de los traspasos (data/modelos/adaptacion/curvas.csv), contraída "
                     "hacia el global por grupo de nacionalidad",
           "grupos_acotados_a_0": int(cv["acotado"].sum()), "grupos": int(len(cv)),
           "L_rel_prod_p100": ejemplo}
    (dv / "resumen.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res["L_rel_prod_p100"], ensure_ascii=False, indent=1))
    return res
