"""Fase 7 — adaptación al cambio de liga (jugadores puente).

INTERFAZ PARA EL SIMULADOR (fase 8). Estable: no cambiar firmas ni claves.

    prior(liga_origen, liga_destino, grupo_nacionalidad, pos3, metrica="L")
        -> dict(delta_media, delta_sd, kappa_media, kappa_sd, n, nivel_fallback)
    grupo_nacionalidad(nacionalidad, liga_origen, liga_destino) -> str
    curva(g, delta, kappa) -> factor = 1 + delta·exp(−g/κ)

Convenio (docs/checkpoints/F7.md):
  * delta es un efecto RELATIVO (fracción) frente a lo esperado tras la normalización amortiguada (ŷ, el valor de
    origen traducido a la escala de la liga de destino): delta = −0,08 → en el partido g = 0 rinde al 92 % de ŷ.
    Negativo = penalización. El factor tiende a 1 (= ŷ) cuando g ≫ κ.
  * kappa en partidos jugados en la liga nueva: el 50 % del hueco se cierra en κ·ln 2 partidos y el 90 % en κ·ln 10.
  * metrica: pts_p100, ts_pct, usg_pct, ast_pct, reb_p100, per o L (índice de nivel compuesto).
  * nivel_fallback: celda (par + grupo + pos3) → par_grupo → par → escalon_grupo → escalon (escalón de la liga de
    destino) → global_grupo → global; «sin_datos» si aún no existe la tabla (valores por defecto del YAML).

Esta primera versión es compatible con la interfaz (stub): si data/modelos/adaptacion/adaptation_priors.csv no
existe, prior() devuelve los valores por defecto de configs/adaptacion.yaml.
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DIR_MOD, cargar

DIR_SALIDA = DIR_MOD / "adaptacion"
FICHERO_PRIORS = DIR_SALIDA / "adaptation_priors.csv"
METRICAS_PRIOR = ("pts_p100", "ts_pct", "usg_pct", "ast_pct", "reb_p100", "per", "L")
COMODIN = "*"


def cfg() -> dict:
    return cargar("adaptacion")


# ============================================================================================ interfaz: curva
def curva(g, delta, kappa):
    """Factor multiplicativo sobre lo esperado tras la normalización en el partido g (0, 1, 2…) de la liga nueva:
    1 + delta·exp(−g/κ). Acepta escalares o arrays (numpy difunde). κ ≤ 0 o no finito → sin curva (factor 1 + delta
    en g = 0 y 1 después, el límite κ → 0)."""
    g = np.asarray(g, dtype=float)
    delta = np.asarray(delta, dtype=float)
    kappa = np.asarray(kappa, dtype=float)
    k_ok = np.isfinite(kappa) & (kappa > 0)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        dec = np.where(k_ok, np.exp(-np.clip(g, 0, None) / np.where(k_ok, kappa, 1.0)), np.where(g <= 0, 1.0, 0.0))
    f = 1.0 + delta * dec
    return float(f) if np.ndim(f) == 0 else f


def partidos_hasta(fraccion: float, kappa: float) -> float:
    """Partidos para cerrar una fracción del hueco: exp(−g/κ) = 1 − fracción → g = −κ·ln(1 − fracción)."""
    if not (0 < fraccion < 1) or not np.isfinite(kappa):
        return float("nan")
    return float(-kappa * math.log(1 - fraccion))


# ============================================================================================ interfaz: grupo
def _isos(nacionalidad) -> list[str]:
    """Códigos ISO alfa-2 de un texto de nacionalidad («US», «Estados Unidos», «Alemania / Estados Unidos», «DE|US»)."""
    if nacionalidad is None or (isinstance(nacionalidad, float) and math.isnan(nacionalidad)):
        return []
    try:
        from bbmodel.nacionalidad import codigo
    except Exception:  # noqa: BLE001
        codigo = None
    out = []
    for parte in str(nacionalidad).replace("|", "/").split("/"):
        p = parte.strip()
        if not p:
            continue
        c = codigo(p) if codigo else None
        if c is None and len(p) == 2 and p.isalpha():
            c = p.upper()
        if c is None and p.upper() in ("USA", "EEUU", "EE. UU.", "EE.UU."):
            c = "US"
        if c and c not in out:
            out.append(c)
    return out


def grupo_nacionalidad(nacionalidad, liga_origen: str, liga_destino: str) -> str:
    """Grupo de nacionalidad / origen formativo de un traspaso liga_origen → liga_destino (configs/adaptacion.yaml).

    EEUU_a_Europa · otro_desde_EEUU · hacia_EEUU · intra_EEUU · nacional_mismo_pais · extranjero_mismo_pais ·
    europeo_cambia_liga · extranjero_cambia_pais · desconocido. Sin nacionalidad → «desconocido» salvo en los grupos
    que sólo dependen de las ligas (hacia_EEUU, intra_EEUU). Las copas europeas no tienen país (EUR): entrar o salir de
    una copa cuenta como cambio de competición europea."""
    c = cfg()
    paises = c["paises_liga"]
    europa = set(c["paises_europeos"])
    po, pd_ = paises.get(str(liga_origen)), paises.get(str(liga_destino))
    us_o, us_d = po == "US", pd_ == "US"
    if us_o and us_d:
        return "intra_EEUU"
    if us_d:
        return "hacia_EEUU"
    nats = _isos(nacionalidad)
    if not nats:
        return "desconocido"
    if us_o:
        return "EEUU_a_Europa" if "US" in nats else "otro_desde_EEUU"
    if po is not None and po == pd_ and po != "EUR":
        return "nacional_mismo_pais" if po in nats else "extranjero_mismo_pais"
    if any(n in europa for n in nats):
        return "europeo_cambia_liga"
    return "extranjero_cambia_pais"


# ============================================================================================ interfaz: prior
def escalon_de(liga: str) -> str | None:
    """Escalón de nivel de una liga (configs/normalization.yaml → escalones)."""
    for k, ligas in (cargar("normalization").get("escalones") or {}).items():
        if liga in ligas:
            return k
    return None


@lru_cache(maxsize=4)
def _tabla_priors(ruta: str, mtime: float) -> pd.DataFrame:  # mtime en la clave: se relee si cambia el fichero
    return pd.read_csv(ruta, dtype={"liga_origen": str, "liga_destino": str, "grupo_nacionalidad": str, "pos3": str,
                                    "escalon_destino": str, "metrica": str, "nivel": str})


def cargar_priors(ruta: Path | None = None) -> pd.DataFrame | None:
    p = Path(ruta or FICHERO_PRIORS)
    if not p.exists():
        return None
    return _tabla_priors(str(p), p.stat().st_mtime)


def _defecto(nivel: str = "sin_datos") -> dict:
    pr = cfg()["priors"]
    return {"delta_media": 0.0, "delta_sd": float(pr["delta_sd_defecto"]), "kappa_media": float(pr["kappa_defecto"]),
            "kappa_sd": float(pr["kappa_sd_defecto"]), "n": 0, "nivel_fallback": nivel}


def prior(liga_origen: str, liga_destino: str, grupo_nacionalidad: str, pos3: str, metrica: str = "L",
          ruta: Path | None = None) -> dict:
    """Prior de adaptación para un traspaso: dict(delta_media, delta_sd, kappa_media, kappa_sd, n, nivel_fallback).

    Busca en adaptation_priors.csv del nivel más fino al más grueso y usa el primero con n ≥ priors.n_min_celda
    (el nivel global se usa siempre que exista). Las estimaciones de cada nivel ya están contraídas hacia el nivel
    superior (modelo jerárquico), así que la reserva sólo decide cuánta información propia hay."""
    if metrica not in METRICAS_PRIOR:
        raise ValueError(f"métrica desconocida: {metrica!r} (válidas: {', '.join(METRICAS_PRIOR)})")
    t = cargar_priors(ruta)
    if t is None or t.empty:
        return _defecto()
    t = t[t["metrica"] == metrica]
    if t.empty:
        return _defecto()
    n_min = int(cfg()["priors"]["n_min_celda"])
    esc = escalon_de(liga_destino) or COMODIN
    lo, ld, gr, p3 = str(liga_origen), str(liga_destino), str(grupo_nacionalidad), str(pos3)
    claves = [("celda", lo, ld, gr, p3), ("par_grupo", lo, ld, gr, COMODIN), ("par", lo, ld, COMODIN, COMODIN),
              ("escalon_grupo", COMODIN, COMODIN, gr, COMODIN), ("escalon", COMODIN, COMODIN, COMODIN, COMODIN),
              ("global_grupo", COMODIN, COMODIN, gr, COMODIN), ("global", COMODIN, COMODIN, COMODIN, COMODIN)]
    for nivel, a, b, c_, d in claves:
        s = t[(t["nivel"] == nivel) & (t["liga_origen"] == a) & (t["liga_destino"] == b)
              & (t["grupo_nacionalidad"] == c_) & (t["pos3"] == d)]
        if nivel.startswith("escalon"):
            s = s[s["escalon_destino"] == esc]
        if s.empty:
            continue
        r = s.iloc[0]
        if int(r["n"]) < n_min and nivel != "global":
            continue
        return {"delta_media": float(r["delta_media"]), "delta_sd": float(r["delta_sd"]),
                "kappa_media": float(r["kappa_media"]), "kappa_sd": float(r["kappa_sd"]), "n": int(r["n"]),
                "nivel_fallback": nivel}
    return _defecto()
