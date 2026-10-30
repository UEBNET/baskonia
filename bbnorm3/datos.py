"""Capa de medida de la v3: de la tabla jugador-liga-temporada a matrices para la CVAE.

Reutiliza, sin cambiarla, la capa de medida del proyecto (no es el algoritmo A, es preprocesado):
  * `bbmodel.modelo.preparar()`  identidades (persona_id, crosswalk 0,75) y posición pos3 (E/A/I);
  * `bbmodel.suerte`             transformación de cada métrica y ruido de muestra σ²/n;
  * `bbmodel.metricas`           las 33 métricas (25 de caja + 8 de pista).

Notación: fila r = (persona i, competición-temporada c = (l, t), posición p, equipo e).
  y_{r,m}  métrica m transformada y estandarizada globalmente: (T(x) − c_m) / s_m
  v_{r,m}  ruido de muestra conocido en esas unidades: σ²_{l,m} / (n_{r,m} · s_m²)
  M_{r,m}  1 si hay dato (p. ej. la LNB no tiene totales de rival; las FEB antiguas no tienen pista)

Sin fuga: con `hasta_anio = t` sólo se usan temporadas ≤ t para estimar σ², c_m, s_m, la ponderación de
selección y todo lo demás. Las filas de t + 1 se pueden codificar después con `matrices_filas` usando la
escala del ajuste.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from bbmodel import enlace, suerte
from bbmodel.metricas import CATALOGO, EXPOSICIONES

METRICAS = list(CATALOGO)
# métricas de nivel (las mismas de configs/normalization.yaml → transferibilidad.metricas_nivel); DRtg con signo −
METRICAS_NIVEL = {"per": 1, "game_score_p40": 1, "ws_per_40": 1, "ortg": 1, "drtg": -1, "pts_p100": 1,
                  "ts_pct": 1, "efg_pct": 1}
POSICIONES = ["E", "A", "I"]


@dataclass
class Escala:
    """Estandarización y ruido por métrica (estimados con las filas de entrenamiento)."""
    c: dict = field(default_factory=dict)          # media global de T(x) (filas con ≥ 300 min)
    s: dict = field(default_factory=dict)          # desviación típica global de T(x)
    sigma2: dict = field(default_factory=dict)     # σ² por liga (o "todas" si la exposición son tiros)
    recorte: dict = field(default_factory=dict)    # límites del recorte de valores imposibles

    def sigma2_de(self, col: str, ligas) -> np.ndarray:
        s2 = self.sigma2[col]
        return np.array([s2.get(l, s2.get("todas", np.nan)) for l in ligas], float)


def ajustar_escala(t: pd.DataFrame, min_escala: float) -> tuple[Escala, dict]:
    """σ² (paso 1 del A, método de momentos) y estandarización global de cada métrica. Devuelve también los z
    dentro de liga-temporada-posición (z_obs, v_obs) que usa la ponderación de selección."""
    esc, zs = Escala(), {}
    for col in METRICAS:
        z, p1 = suerte.ajustar_metrica(t, col)
        zs[col] = z
        esc.sigma2[col] = p1["sigma2"]
        m = CATALOGO[col]
        y = suerte.valor_y_exposicion(t, col)[0]
        ref = np.isfinite(y) & (t["min"].to_numpy(float) >= min_escala)
        esc.c[col] = float(np.mean(y[ref]))
        esc.s[col] = float(np.std(y[ref]))
        exp_ok = pd.to_numeric(t[EXPOSICIONES[m.exposicion]], errors="coerce").to_numpy(float) \
            >= suerte.MIN_EXPOSICION_AJUSTE[m.exposicion]
        r = y[np.isfinite(y) & exp_ok]
        lo, hi = np.quantile(r, [0.005, 0.995]) if len(r) else (-np.inf, np.inf)
        esc.recorte[col] = (float(lo - 0.25 * (hi - lo)), float(hi + 0.25 * (hi - lo)))
    return esc, zs


def matrices_filas(t: pd.DataFrame, esc: Escala) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Y, M, V (filas × 33) de cualquier conjunto de filas con la escala de un ajuste (sin reestimar nada)."""
    from bbmodel.metricas import transformar
    N = len(t)
    Y = np.zeros((N, len(METRICAS)), np.float32)
    M = np.zeros_like(Y)
    V = np.ones_like(Y)
    ligas = t["liga"].to_numpy()
    for k, col in enumerate(METRICAS):
        m = CATALOGO[col]
        y = transformar(pd.to_numeric(t[col], errors="coerce"), m.transf)
        lo, hi = esc.recorte[col]
        y = np.clip(y, lo, hi)
        n = pd.to_numeric(t[EXPOSICIONES[m.exposicion]], errors="coerce").to_numpy(float)
        s2 = esc.sigma2_de(col, ligas)
        ok = np.isfinite(y) & np.isfinite(n) & (n > 0) & np.isfinite(s2)
        Y[ok, k] = (y[ok] - esc.c[col]) / esc.s[col]
        V[ok, k] = s2[ok] / n[ok] / esc.s[col] ** 2
        M[ok, k] = 1.0
    V = np.clip(V, 1e-4, 25.0)
    return Y, M, V


@dataclass
class Datos:
    """Todo lo que necesita la CVAE para un ajuste (un corte temporal)."""
    t: pd.DataFrame                    # filas de entrenamiento (índice 0..N-1); columna `idx_tabla` = índice original
    Y: np.ndarray
    M: np.ndarray
    V: np.ndarray
    esc: Escala
    ligas: list
    comps: list                        # "liga|temporada"
    grupos: list                       # "liga|temporada|pos"
    equipos: list
    ps: list                           # "persona|anio"
    tramos: list
    idx: dict                          # códigos por fila: liga, comp, grupo, equipo, ps, pos, persona_id
    personas: list
    ps_comp_principal: np.ndarray      # competición con más minutos de cada persona-temporada
    ps_tramo: np.ndarray
    ps_persona: np.ndarray             # persona (índice en `personas`) de cada persona-temporada
    transiciones: np.ndarray           # (a, b) persona-temporada t → t+1 de la misma persona
    peso_ps: np.ndarray                # ponderación de selección (IPW) de cada persona-temporada
    peso_prior: np.ndarray             # peso del prior por nivel de cada persona-temporada (1 o 1/temporadas)
    info_ipw: dict
    comp_liga: np.ndarray              # liga de cada competición-temporada
    comp_anio: np.ndarray
    escalon_de_liga: dict
    hasta_anio: int | None


def _nivel(t: pd.DataFrame, zs: dict) -> pd.Series:
    """Nivel de cada fila en su liga (media con signo de z sin suerte en las métricas de nivel)."""
    cols = []
    for col, signo in METRICAS_NIVEL.items():
        z = zs[col].reindex(t.index)
        cols.append(signo * z["z_obs"] / (1 + z["v_obs"]))
    return pd.concat(cols, axis=1).mean(axis=1)


def indicador_puente(t: pd.DataFrame, min_minutos: float) -> np.ndarray:
    """Fila de una persona con ≥ min_minutos en otra competición la misma temporada o en la siguiente/anterior."""
    f = t[t["min"] >= min_minutos][["persona_id", "anio", "liga"]]
    clave = set(zip(f["persona_id"], f["anio"], f["liga"]))
    por_pa = f.groupby(["persona_id", "anio"])["liga"].agg(set).to_dict()
    out = np.zeros(len(t), bool)
    for k, (p, a, l, mn) in enumerate(zip(t["persona_id"], t["anio"], t["liga"], t["min"])):
        if mn < min_minutos or (p, a, l) not in clave:
            continue
        for aa in (a - 1, a, a + 1):
            otras = por_pa.get((p, aa), set()) - {l}
            if otras:
                out[k] = True
                break
    return out


def construir(tabla: pd.DataFrame, cfg: dict, hasta_anio: int | None = None) -> Datos:
    from bbmodel.amortiguacion import pesos_ipw
    dcfg = cfg["datos"]
    base = tabla if hasta_anio is None else tabla[tabla["anio"] <= hasta_anio]
    base = base[base["pos3"].notna()]
    esc, zs = ajustar_escala(base, dcfg["min_minutos_escala"])
    t = base[base["min"] >= dcfg["min_minutos"]].copy()
    t["idx_tabla"] = t.index
    Y, M, V = matrices_filas(t, esc)
    t = t.reset_index(drop=True)
    t["comp"] = t["liga"] + "|" + t["temporada"]
    t["grupo"] = t["comp"] + "|" + t["pos3"]
    t["equipo"] = t["comp"] + "|" + t["team_id"].astype(str)
    t["ps"] = t["persona_id"].astype(str) + "|" + t["anio"].astype(str)
    t["tramo"] = (t["anio"] - t["anio_nac"]).map(enlace.tramo_edad)
    cod, uniq = {}, {}
    for c in ("liga", "comp", "grupo", "equipo", "ps", "tramo", "persona_id"):
        codes, u = pd.factorize(t[c], sort=True)
        cod[c], uniq[c] = codes.astype(np.int64), list(u)
    cod["pos"] = t["pos3"].map({p: i for i, p in enumerate(POSICIONES)}).to_numpy(np.int64)
    # persona-temporada: competición principal (más minutos) y tramo de edad
    nps = len(uniq["ps"])
    orden = np.argsort(t["min"].to_numpy())             # el último que escribe es el de más minutos
    ps_comp = np.zeros(nps, np.int64)
    ps_comp[cod["ps"][orden]] = cod["comp"][orden]
    ps_tramo = np.zeros(nps, np.int64)
    ps_tramo[cod["ps"]] = cod["tramo"]
    ps_persona = np.zeros(nps, np.int64)
    ps_persona[cod["ps"]] = cod["persona_id"]
    # transiciones t → t+1 de la misma persona
    pa = pd.DataFrame({"ps": uniq["ps"]})
    pa["persona"] = pa["ps"].str.rsplit("|", n=1).str[0]
    pa["anio"] = pa["ps"].str.rsplit("|", n=1).str[1].astype(int)
    pa["i"] = np.arange(nps)
    sig = pa.assign(anio=pa["anio"] - 1)[["persona", "anio", "i"]].rename(columns={"i": "j"})
    tr = pa.merge(sig, on=["persona", "anio"])
    transiciones = tr[["i", "j"]].to_numpy(np.int64)
    # prior por nivel: una vez por persona-temporada o repartido entre sus temporadas (una vez por persona)
    if cfg["prior"].get("prior_por_persona", False):
        peso_prior = 1.0 / pa.groupby("persona")["i"].transform("size").to_numpy(float)
    else:
        peso_prior = np.ones(nps)
    # ponderación de selección (logit de «ser puente» de bbmodel/amortiguacion.py)
    peso_ps = np.ones(nps)
    info_ipw = {"ipw": False}
    if cfg["entrenamiento"].get("ipw", True):
        puente = indicador_puente(t, dcfg["min_minutos_puente"])
        f = pd.DataFrame({"nivel": _nivel(base, zs).reindex(t["idx_tabla"]).to_numpy(),
                          "edad": (t["anio"] - t["anio_nac"]).to_numpy(float), "min": t["min"].to_numpy(float),
                          "liga": t["liga"].to_numpy(), "temporada": t["temporada"].to_numpy()})
        w, info_ipw = pesos_ipw(f, puente, recorte=tuple(cfg["entrenamiento"]["recorte_ipw"]))
        w = np.where(puente, w, 1.0)
        acc = np.zeros(nps); cnt = np.zeros(nps)
        np.add.at(acc, cod["ps"], w); np.add.at(cnt, cod["ps"], 1)
        peso_ps = acc / np.maximum(cnt, 1)
    comps = uniq["comp"]
    comp_liga = np.array([uniq["liga"].index(c.split("|")[0]) for c in comps], np.int64)
    comp_anio = np.array([int(c.split("|")[1][:4]) for c in comps], np.int64)
    escalon = {l: e for e, ls in cfg["escalones"].items() for l in ls}
    return Datos(t=t, Y=Y, M=M, V=V, esc=esc, ligas=uniq["liga"], comps=comps, grupos=uniq["grupo"],
                 equipos=uniq["equipo"], ps=uniq["ps"], personas=uniq["persona_id"], tramos=uniq["tramo"], idx=cod, ps_comp_principal=ps_comp,
                 ps_tramo=ps_tramo, ps_persona=ps_persona, transiciones=transiciones, peso_ps=peso_ps, peso_prior=peso_prior, info_ipw=info_ipw,
                 comp_liga=comp_liga, comp_anio=comp_anio, escalon_de_liga=escalon, hasta_anio=hasta_anio)
