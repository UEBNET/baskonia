"""F3.2 · Ajuste por liga-temporada y validación decisiva: ajustar con la primera mitad de los partidos de cada
jugador (por fecha) y predecir la segunda.

Modelos comparados (por métrica):
- `crudo`: la tasa observada en la primera mitad, sin encoger, como si fuera la verdadera (sólo ruido binomial o de
  Poisson en la segunda mitad). Es la referencia ingenua.
- `jer`: jerárquico con media por rol, sin sobredispersión dentro de jugador.
- `jer_sd`: jerárquico con la sobredispersión dentro de jugador estimada por momentos en la primera mitad.
- Familia normal: un solo modelo (`jer`), cuya φ ya es la varianza dentro de jugador entre partidos.

Se condiciona en las oportunidades de la segunda mitad (cuántos tiros, rebotes disponibles…): la capa de medida
responde «dado el volumen, cuánto acierta»; el volumen y el rol son otra capa (F6–F7).

Evaluación (unidades con ≥ 3 partidos y ≥ 50 minutos en cada mitad): PIT aleatorizado (discretas), cobertura de los
intervalos centrales del 50, 80 y 95 % (|PIT − 0,5| ≤ nivel/2) y CRPS de la tasa de la segunda mitad.
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

from bbnorm5.medida import datos as D
from bbnorm5.medida import eb

S = 400
MIN_UNIDADES = 30
EVAL_MIN_PARTIDOS = 3
EVAL_MIN_MINUTOS = 50.0


def _semilla(base: int, *claves) -> int:
    return (base + zlib.crc32("|".join(map(str, claves)).encode())) % (2 ** 32)


def _hiper(m: dict, u: pd.DataFrame, **extra) -> dict:
    nr = len(m["roles"])
    if m["familia"] == "normal":
        h = {"sigma": m["tau2"] ** 0.5, "disp": m["phi"], "logL": m["logL"],
             "n_estab": m["phi"] / m["tau2"], "tasa_media": float(u["K"].sum() / u["N"].sum())}
        mus = dict(zip(m["roles"], m["mu"]))
    else:
        h = {**eb.puntos_estabilizacion(m, u), "disp": m["disp"], "logL": m["logL"]}
        mus = dict(zip(m["roles"], m["par"][:nr]))
    return {**extra, **h, "unidades": len(u), **{f"mu_{r}": mus.get(r, np.nan) for r in eb.ROLES}}


def _ajustes(u: pd.DataFrame, familia: str) -> dict:
    if familia == "normal":
        return {"jer": eb.ajustar_normal(u)}
    return {"jer": eb.ajustar(u, familia, False), "jer_sd": eb.ajustar(u, familia, True)}


def liga_temporada(d: pd.DataFrame, liga: str, temporada: str, semilla: int, metricas=None):
    """Devuelve (casos de validación por unidad, hiperparámetros, posteriores de la temporada completa)."""
    casos, hiper, post = [], [], []
    minutos = d.groupby(D.CLAVE + ["mitad"]).agg(min=("min", "sum"), G=("game_id", "nunique")).unstack("mitad")
    minutos.columns = [f"{a}{b}" for a, b in minutos.columns]
    for met in (metricas or D.METRICAS):
        fam = D.METRICAS[met][0]
        rng = np.random.default_rng(_semilla(semilla, liga, temporada, met))
        u1 = D.unidad_metrica(d, met, 1)
        if len(u1) < MIN_UNIDADES:
            continue
        # ---- validación: primera mitad → segunda
        u2 = D.unidad_metrica(d, met, 2)
        mods = _ajustes(u1, fam)
        for nom, m in mods.items():
            hiper.append(_hiper(m, u1, liga=liga, temporada=temporada, metrica=met, modelo=nom, datos="mitad1"))
        ev = u1.reset_index().merge(u2[D.CLAVE + ["K", "N", "N2g"]], on=D.CLAVE, suffixes=("", "_2"))
        ev = ev.merge(minutos, left_on=D.CLAVE, right_index=True)
        ev = ev[(ev["G1"] >= EVAL_MIN_PARTIDOS) & (ev["G2"] >= EVAL_MIN_PARTIDOS) & (ev["min1"] >= EVAL_MIN_MINUTOS)
                & (ev["min2"] >= EVAL_MIN_MINUTOS) & (ev["N_2"] > 0)]
        if len(ev) == 0:
            continue
        fila = ev["index"].to_numpy()
        N2 = ev["N_2"].to_numpy(float)
        N2r = np.maximum(np.round(N2), ev["K_2"].to_numpy()) if fam == "binomial" else N2
        y = ev["K_2"].to_numpy(float) / N2r
        base = ev[D.CLAVE + ["rol", "K", "N", "G1", "G2", "min1", "min2", "K_2", "N_2"]].reset_index(drop=True)
        cand = dict(mods)
        cand["crudo"] = None
        for nom, m in cand.items():
            if nom == "crudo":
                t1 = (ev["K"] / ev["N"]).to_numpy(float)
                tasa = np.repeat(t1[:, None], S, axis=1)
                disp = 0.0
                phi = mods["jer"]["phi"] if fam == "normal" else 0.0
            else:
                if fam == "normal":
                    sub = {**m, "m_post": m["m_post"][fila], "v_post": m["v_post"][fila]}
                    tasa = eb.muestras_tasa(sub, S, rng)
                    phi = m["phi"]
                    disp = 0.0
                else:
                    tasa = eb.muestras_tasa({**m, "W": m["W"][fila]}, S, rng)
                    disp, phi = m["disp"], 0.0
            K2 = eb.muestras_conteo(tasa, N2r if fam == "binomial" else N2, ev["N2g_2"].to_numpy(float), fam, disp,
                                    rng, phi)
            r = eb.evaluar(K2 / N2r[:, None], y, fam != "normal", rng)
            casos.append(base.assign(metrica=met, modelo=nom, pred_media=(K2 / N2r[:, None]).mean(axis=1), obs=y,
                                     pit=r["pit"].to_numpy(), crps=r["crps"].to_numpy()))
        # ---- temporada completa: hiperparámetros y posterior de cada unidad
        u = D.unidad_metrica(d, met, None)
        for nom, m in _ajustes(u, fam).items():
            hiper.append(_hiper(m, u, liga=liga, temporada=temporada, metrica=met, modelo=nom, datos="temporada"))
            if fam == "normal":
                ps = pd.DataFrame({"media": m["m_post"], "sd": np.sqrt(m["v_post"])})
                ps["q10"], ps["q50"], ps["q90"] = (ps["media"] + z * ps["sd"] for z in (-1.2815515655, 0, 1.2815515655))
            else:
                ps = eb.resumen_posterior(m)
            post.append(pd.concat([u[D.CLAVE + ["rol", "K", "N", "G"]].reset_index(drop=True), ps], axis=1)
                        .assign(metrica=met, modelo=nom, obs=u["K"].to_numpy() / u["N"].to_numpy()))
    cat = lambda x: pd.concat(x, ignore_index=True) if x else pd.DataFrame()
    return cat(casos), pd.DataFrame(hiper), cat(post)


def resumen(casos: pd.DataFrame, por: list[str]) -> pd.DataFrame:
    c = casos.copy()
    for a in (50, 80, 95):
        c[f"cob{a}"] = (np.abs(c["pit"] - 0.5) <= a / 200).astype(float)
    g = c.groupby(por)
    r = g.agg(casos=("pit", "size"), cob50=("cob50", "mean"), cob80=("cob80", "mean"), cob95=("cob95", "mean"),
              crps=("crps", "mean"), pit_media=("pit", "mean")).reset_index()
    return r
