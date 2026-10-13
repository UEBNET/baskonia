"""Algoritmo A completo: preparar datos, ajustar los pasos 1 y 3, y traducir (paso 4).

Flujo:
    tabla   = preparar()                      # jugador-liga-temporada + persona_id + posición
    params  = ajustar(tabla)                  # paso 1 (suerte) y paso 3 (tipo de cambio), por métrica
    salida  = traducir(tabla, params)         # equivalente EuroLeague de cada jugador y métrica

Paso 2 (el puesto del jugador en su liga) no tiene parámetros propios: es la estandarización z del
paso 1, que mide a cada jugador frente a los de su misma posición, liga y temporada.

Paso 4, para un jugador de la liga l y una métrica:
  1. Su z en su liga, sin suerte y sin contexto:
        z* = z_obs / (1 + v + ψ_l)          varianza  (v + ψ_l) / (1 + v + ψ_l)
     (v = ruido de muestra; ψ_l = parte de su número que es contexto de su equipo y rol).
  2. Su capacidad en la vara EuroLeague:   a = m_l + s_l · z*
     con incertidumbre que suma la suya propia y la de los parámetros m_l y s_l (bootstrap).
  3. Su valor en la EuroLeague de referencia (por defecto 2025-26), en su posición:
        valor = μ_EL,pos + τ_EL,pos · a    (y se deshace la transformación de la métrica)
     y su percentil entre los jugadores de EuroLeague de su posición: Φ(a).
  4. Proyección a la temporada siguiente: a + d(edad), con la varianza extra η².
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from . import datos, enlace, identidad, posicion, suerte
from .metricas import CATALOGO, destransformar

RAIZ = Path(__file__).resolve().parent.parent
DIR_SALIDA = RAIZ / "data" / "modelos" / "algoritmo_A"
REFERENCIA = enlace.REFERENCIA
TEMPORADA_REF = "2025-26"
MIN_MINUTOS_ENLACE = 150
Z80 = norm.ppf(0.9)  # intervalo central del 80 %


def preparar(temporadas: list[str] | None = None) -> tuple[pd.DataFrame, dict]:
    t = datos.cargar("regular", temporadas)
    t, ambiguos = identidad.resolver(t)
    t, info_pos = posicion.asignar(t)
    t = posicion.consolidar_por_persona(t)
    info = {"registros": len(t), "personas": int(t["persona_id"].nunique()), "identidades_ambiguas": len(ambiguos),
            "posicion": info_pos, "puentes": identidad.puentes(t).to_dict("records")}
    return t, info


def ajustar(t: pd.DataFrame, hasta_anio: int | None = None, metricas: list[str] | None = None,
            n_boot: int = 20, progreso=print) -> dict:
    """Ajusta los pasos 1 y 3 con las temporadas que empiezan en `hasta_anio` o antes."""
    base = t if hasta_anio is None else t[t["anio"] <= hasta_anio]
    params = {"hasta_anio": hasta_anio, "metricas": {}, "_z": {}}  # _z: z de cada fila (no se guarda en JSON)
    for col in (metricas or list(CATALOGO)):
        z, p1 = suerte.ajustar_metrica(base, col)
        obs = base[["persona_id", "liga", "anio", "anio_nac", "min"]].join(z[["z_obs", "v_obs"]])
        obs = obs.rename(columns={"z_obs": "z", "v_obs": "v"})
        obs = obs[(obs["min"] >= MIN_MINUTOS_ENLACE) & obs["z"].notna()]
        try:
            p3 = enlace.ajustar_metrica(obs, n_boot=n_boot)
        except ValueError as exc:
            progreso(f"  {col}: sin enlace ({exc})")
            continue
        params["metricas"][col] = {"suerte": p1, "enlace": p3}
        params["_z"][col] = z
        if progreso:
            progreso(f"  {col}: {p3['unidades']} unidades de enlace, {p3['iteraciones']} iteraciones")
    return params


def _entorno(p1: dict, liga: str, temporada: str, pos: str) -> tuple[float, float]:
    """(μ, τ) del grupo liga-temporada-posición en la escala transformada."""
    return p1["mu"].get(f"{liga}|{temporada}|{pos}", np.nan), float(np.sqrt(p1["tau2"].get(f"{liga}|{pos}", np.nan)))


def capacidad(z_obs, v_obs, liga: str, p3: dict):
    """Pasos 4.1 y 4.2: capacidad en la vara EuroLeague (media y varianza)."""
    psi = p3["psi"].get(liga, np.nan)
    m, s = p3["m"].get(liga, np.nan), p3["s"].get(liga, np.nan)
    z_est = z_obs / (1 + v_obs + psi)
    v_est = (v_obs + psi) / (1 + v_obs + psi)
    a = m + s * z_est
    va = (s ** 2 * v_est + p3["m_se"].get(liga, 0) ** 2 + z_est ** 2 * p3["s_se"].get(liga, 0) ** 2
          + 2 * z_est * p3["cov_ms"].get(liga, 0))
    return a, va


def traducir(t: pd.DataFrame, params: dict, temporada_ref: str = TEMPORADA_REF) -> pd.DataFrame:
    """Equivalente EuroLeague de cada jugador-liga-temporada y métrica."""
    out = t[["persona_id", "liga", "temporada", "anio", "player_id", "nombre", "equipo", "pos3", "pos3_estimada",
             "anio_nac", "gp", "min"]].copy()
    edad = (t["anio"] - t["anio_nac"]).to_numpy()
    tramos = pd.Series(edad).map(enlace.tramo_edad).to_numpy()
    nuevas = {}
    for col, p in params["metricas"].items():
        m = CATALOGO[col]
        z = params["_z"][col].reindex(t.index)
        z_obs = z["z_obs"].to_numpy(float); v_obs = z["v_obs"].to_numpy(float)
        a = np.full(len(t), np.nan); va = np.full(len(t), np.nan)
        for liga in t["liga"].unique():
            s = (t["liga"] == liga).to_numpy()
            if liga in p["enlace"]["m"]:
                a[s], va[s] = capacidad(z_obs[s], v_obs[s], liga, p["enlace"])
        mu = np.array([_entorno(p["suerte"], REFERENCIA, temporada_ref, g)[0] if isinstance(g, str) else np.nan for g in t["pos3"]])
        tau = np.array([_entorno(p["suerte"], REFERENCIA, temporada_ref, g)[1] if isinstance(g, str) else np.nan for g in t["pos3"]])
        sd = np.sqrt(va)
        nuevas[f"{col}"] = t[col].to_numpy(float)
        nuevas[f"{col}_el"] = destransformar(mu + tau * a, m.transf)
        nuevas[f"{col}_el_lo"] = destransformar(mu + tau * (a - Z80 * sd), m.transf)
        nuevas[f"{col}_el_hi"] = destransformar(mu + tau * (a + Z80 * sd), m.transf)
        nuevas[f"{col}_pct_el"] = 100 * norm.cdf(a)
        d = np.array([p["enlace"]["deriva"].get(tr, 0.0) for tr in tramos])
        nuevas[f"{col}_el_prox"] = destransformar(mu + tau * (a + d), m.transf)
        nuevas[f"{col}_a"] = a
        nuevas[f"{col}_a_sd"] = sd
    return pd.concat([out.reset_index(drop=True), pd.DataFrame(nuevas)], axis=1)


def resumen_parametros(params: dict) -> pd.DataFrame:
    """Tabla legible del tipo de cambio: una fila por métrica y liga."""
    filas = []
    for col, p in params["metricas"].items():
        e = p["enlace"]
        for liga in e["ligas"]:
            filas.append({"metrica": col, "nombre": CATALOGO[col].nombre, "liga": liga,
                          "m": e["m"][liga], "m_se": e["m_se"].get(liga), "s": e["s"][liga], "s_se": e["s_se"].get(liga),
                          "psi": e["psi"][liga], "puentes": e["puentes_por_liga"].get(liga, 0)})
    return pd.DataFrame(filas)


def guardar(params: dict, info: dict, traducciones: pd.DataFrame, dir_salida: Path = DIR_SALIDA) -> None:
    dir_salida = Path(dir_salida)
    (dir_salida / "traducciones").mkdir(parents=True, exist_ok=True)
    with open(dir_salida / "parametros.json", "w", encoding="utf-8") as fh:
        json.dump({"info": info, **{k: v for k, v in params.items() if not k.startswith("_")}}, fh,
                  ensure_ascii=False, indent=1, default=float)
    resumen_parametros(params).round(4).to_csv(dir_salida / "tipo_de_cambio.csv", index=False)
    for temp, g in traducciones.groupby("temporada"):
        g.round(4).to_csv(dir_salida / "traducciones" / f"{temp}.csv", index=False)
