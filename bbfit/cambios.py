"""Cambios de rol dentro de una temporada: detección bayesiana en línea de puntos de cambio (BOCPD).

Modelo (implementación propia, numpy):
  * La serie de un jugador en un equipo y temporada es x_t = (MIN%_t, USG%_t), un partido por t. Dentro de un
    tramo, x_t,d ~ N(μ_d, σ_d²) con media μ_d desconocida (a priori N(μ0_d, v0_d)) y ruido σ_d² conocido
    (estimado por liga-temporada como la varianza partido a partido dentro de jugador, con suelo en YAML).
    Las dimensiones son independientes; un USG% ausente (pocos minutos) sólo omite su término.
  * Longitud del tramo en curso ℓ_t (partidos desde el último cambio, incluido t). Riesgo constante
    H = 1/λ: P(ℓ_t = 1) ∝ H·Σ_k P(ℓ_{t-1}=k)·p₀(x_t);  P(ℓ_t = k+1) ∝ (1−H)·P(ℓ_{t-1}=k)·p_k(x_t),
    con p_k la predictiva N(m_k, v_k + σ²) del tramo de longitud k (actualización conjugada normal-normal).
  * Probabilidad de que empiece un tramo en el partido s, confirmada con L partidos posteriores:
    π_s = P(ℓ_{s+L} = L+1 | x_{1..s+L})  (o con los partidos que queden si la serie acaba antes).
  * Cambios: máximos de π_s por encima del umbral, separados al menos `tramo_minimo` partidos entre sí y de
    los extremos. Todos los parámetros en configs/roles.yaml (bloque `cambios`).

Covariables de cada cambio (`covariables_cambio`): cambio de entrenador cerca, vacío de rol (un compañero de su
misma pos3 con muchos minutos deja de jugar), llegada de un fichaje a su posición y rendimiento reciente.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def bocpd(X: np.ndarray, mu0: np.ndarray, v0: np.ndarray, s2: np.ndarray, hazard: float) -> np.ndarray:
    """Matriz P[t, ℓ-1] = P(ℓ_t = ℓ | x_1..t), t = 0..T-1 (filas suman 1). X: (T, D) con NaN = no observado."""
    X = np.asarray(X, float)
    if X.ndim == 1:
        X = X[:, None]
    T, D = X.shape
    mu0, v0, s2 = (np.asarray(a, float).reshape(D) for a in (mu0, v0, s2))
    P = np.zeros((T, T))
    if T == 0:
        return P
    # estadísticos suficientes por longitud de tramo (índice k-1 = tramo de k partidos)
    n = np.zeros((0, D))
    s = np.zeros((0, D))

    def logpred(nk, sk, x):
        vpost = 1.0 / (1.0 / v0 + nk / s2)
        mpost = vpost * (mu0 / v0 + sk / s2)
        var = vpost + s2
        obs = ~np.isnan(x)
        lp = -0.5 * (np.log(2 * np.pi * var) + (x - mpost) ** 2 / var)
        return np.where(obs, lp, 0.0).sum(axis=-1)

    prev = np.zeros(0)
    for t in range(T):
        x = X[t]
        lp0 = logpred(np.zeros(D), np.zeros(D), x)
        if t == 0:
            logw = np.array([lp0])
        else:
            lgrow = np.log1p(-hazard) + np.log(np.maximum(prev, 1e-300)) + logpred(n, s, x)
            lnew = np.log(hazard) + lp0          # Σ prev = 1
            logw = np.concatenate([[lnew], lgrow])
        logw -= logw.max()
        w = np.exp(logw)
        w /= w.sum()
        P[t, : t + 1] = w
        xo = np.where(np.isnan(x), 0.0, x)
        oo = (~np.isnan(x)).astype(float)
        n = np.vstack([oo[None, :], n + oo]) if t else oo[None, :]
        s = np.vstack([xo[None, :], s + xo]) if t else xo[None, :]
        prev = w
    return P


def prob_inicio(P: np.ndarray, retardo: int) -> np.ndarray:
    """π_s = probabilidad de que un tramo empiece en s (s >= 1), confirmada con `retardo` partidos."""
    T = P.shape[0]
    pi = np.zeros(T)
    for s_ in range(1, T):
        u = min(s_ + retardo, T - 1)
        pi[s_] = P[u, u - s_]
    return pi


def segmentar(X: np.ndarray, mu0, v0, s2, cfg: dict) -> tuple[list[tuple[int, int]], np.ndarray]:
    """Tramos [(inicio, fin_inclusive)] y vector π. cfg = bloque `cambios` de roles.yaml."""
    X = np.asarray(X, float)
    if X.ndim == 1:
        X = X[:, None]
    T = len(X)
    if T == 0:
        return [], np.zeros(0)
    P = bocpd(X, mu0, v0, s2, 1.0 / float(cfg["hazard_lambda"]))
    pi = prob_inicio(P, int(cfg["retardo"]))
    m = int(cfg["tramo_minimo"])
    cand = [i for i in np.argsort(-pi) if pi[i] >= float(cfg["umbral_prob"]) and m <= i <= T - m]
    elegidos: list[int] = []
    for i in cand:
        if all(abs(i - j) >= m for j in elegidos):
            elegidos.append(int(i))
    cortes = [0] + sorted(elegidos) + [T]
    return [(cortes[k], cortes[k + 1] - 1) for k in range(len(cortes) - 1)], pi


# ----------------------------------------------------------------------------------------- covariables

def covariables_cambio(equipo: pd.DataFrame, jugador: str, orden_cambio: int, pos3: str | None,
                       cfg: dict) -> dict:
    """Covariables de un cambio del jugador en el partido nº `orden_cambio` de su equipo.

    equipo: tabla partido-jugador de ESE equipo y temporada (incluidas ausencias, min_pct = 0, jugo = False),
    columnas: orden_equipo, player_id, pos3, min_pct, jugo, entrenador_id, ts_pct, pm, sec.
    """
    k = int(cfg["ventana_covariables"])
    antes = equipo[(equipo["orden_equipo"] < orden_cambio) & (equipo["orden_equipo"] >= orden_cambio - k)]
    despues = equipo[(equipo["orden_equipo"] >= orden_cambio) & (equipo["orden_equipo"] < orden_cambio + k)]
    out: dict = {}
    # 1) entrenador: ¿cambia en la ventana?
    ent = equipo.drop_duplicates("orden_equipo").set_index("orden_equipo")["entrenador_id"].sort_index()
    va = ent[(ent.index >= orden_cambio - k) & (ent.index < orden_cambio + k)].dropna()
    out["cov_cambio_entrenador"] = bool(va.nunique() > 1)
    # 2) vacío de rol: compañero de su pos3 con MIN% alto antes que deja de jugar después
    vac = []
    if pos3 is not None and isinstance(pos3, str):
        comp = antes[(antes["player_id"] != jugador) & (antes["pos3"] == pos3)]
        media = comp.groupby("player_id")["min_pct"].mean()
        for pid in media[media >= float(cfg["vacio_min_pct"])].index:
            d = despues[despues["player_id"] == pid]
            n_equipo = despues["orden_equipo"].nunique()
            jugados = int(d["jugo"].sum()) if len(d) else 0
            if n_equipo and (n_equipo - jugados) / n_equipo >= float(cfg["vacio_ausencia"]):
                vac.append(pid)
    out["cov_vacio_rol"] = bool(vac)
    out["cov_vacio_rol_ids"] = ";".join(vac)
    # 3) fichaje en su posición: compañero de su pos3 que debuta en la ventana con el equipo ya en marcha
    fich = []
    if pos3 is not None and isinstance(pos3, str):
        debut = equipo[equipo["jugo"]].groupby("player_id")["orden_equipo"].min()
        cand = debut[(debut >= orden_cambio - k) & (debut < orden_cambio + k)
                     & (debut > int(cfg["fichaje_partidos_previos"]))]
        for pid in cand.index:
            if pid == jugador:
                continue
            fila = equipo[(equipo["player_id"] == pid)]
            if fila["pos3"].iloc[0] == pos3 and fila.loc[fila["jugo"], "min_pct"].mean() >= float(cfg["fichaje_min_pct"]):
                fich.append(pid)
    out["cov_fichaje_posicion"] = bool(fich)
    out["cov_fichaje_ids"] = ";".join(fich)
    # 4) rendimiento reciente del jugador: TS% y +/- por 40 de los k partidos previos frente a su media previa
    yo = equipo[(equipo["player_id"] == jugador) & equipo["jugo"]]
    prev_k = yo[(yo["orden_equipo"] < orden_cambio) & (yo["orden_equipo"] >= orden_cambio - k)]
    prev_all = yo[yo["orden_equipo"] < orden_cambio]

    def ts(d):
        den = 2 * (d["fga"].sum() + d["coef_tl"].iloc[0] * d["fta"].sum()) if len(d) else 0
        return 100 * d["pts"].sum() / den if den else np.nan

    def pm40(d):
        sec = d["sec"].sum()
        return 40 * 60 * d["pm"].sum() / sec if sec else np.nan

    out["cov_ts_reciente"] = ts(prev_k)
    out["cov_ts_dif_reciente"] = ts(prev_k) - ts(prev_all) if len(prev_all) > len(prev_k) else np.nan
    out["cov_pm40_reciente"] = pm40(prev_k)
    out["cov_pm40_dif_reciente"] = pm40(prev_k) - pm40(prev_all) if len(prev_all) > len(prev_k) else np.nan
    return out
