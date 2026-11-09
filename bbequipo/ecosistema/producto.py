"""F4 · tablas de producto de la v4.1 para el artifact Kerno (orden del CEO del 09-11-2026, marca Kerno).

  landing   Landing por grupo de traspaso (encargo §1.4): efecto de TEMPORADA de la adaptación del modelo vigente del motor
            v3.3 (`configs/simulation_v33.yaml → adaptacion.priors`, métrica L_rel = la del antiguo ADAPT %), recalculado al
            80 %: [μ − z₈₀·σ, mín(μ + z₈₀·σ, 0)] (el modelo acota δ ≤ 0). Se muestra sólo si el rango excluye 0; nunca un
            valor individual: la causa es el grupo de traspaso.
  sellos    Confianza (alta · moderada · baja; decisión del CEO del 09-11-2026) de cada salida visible, con su estado:
            «aprobado» (puertas F3) o «propuesto» (fichas de docs/estado_modelos.md pendientes de confirmar en la puerta F4).
  i18n      Glosario ES/EN de los términos nuevos (encargo F4: textos desde el diccionario i18n).

Salidas: data/modelos/v4_1/producto/{landing,sellos,i18n}.json y artifact/kerno/atlas/v41/producto.json (los tres juntos).
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from . import config as CE

Z80 = 1.2815515655446004

GRUPOS = {   # grupo de traspaso (bbfit.adaptacion.grupo_nacionalidad) → nombre corto ES / EN (la flecha la dibuja la página)
    "EEUU_a_Europa": (["EE. UU.", "Europa"], ["US", "Europe"]),
    "NCAA_a_profesional": (["NCAA", "profesional"], ["NCAA", "pro"]),
    "otro_desde_EEUU": (["EE. UU. (no estadounidense)", "Europa"], ["US (non-American)", "Europe"]),
    "hacia_EEUU": (["Europa", "EE. UU."], ["Europe", "US"]),
    "intra_EEUU": (["EE. UU.", "EE. UU."], ["US", "US"]),
    "nacional_mismo_pais": (["liga nacional", "otra liga de su país"], ["home league", "another home league"]),
    "extranjero_mismo_pais": (["extranjero", "otra liga del mismo país"], ["foreign", "same-country league"]),
    "europeo_cambia_liga": (["europeo", "otra liga europea"], ["European", "another European league"]),
    "extranjero_cambia_pais": (["extranjero", "otro país"], ["foreign", "another country"]),
    "desconocido": (["traspaso sin nacionalidad registrada", ""], ["transfer without recorded nationality", ""]),
}


def landing(cfg: dict) -> dict:
    import yaml
    sim = yaml.safe_load((CE.RAIZ / "configs" / "simulation_v33.yaml").read_text(encoding="utf-8"))
    ruta = sim["adaptacion"]["priors"]
    t = pd.read_csv(CE.RAIZ / ruta)
    g = t[(t["nivel"] == "global_grupo") & (t["metrica"] == "L_rel")]
    out = {}
    for r in g.itertuples():
        mu, sd = float(r.delta_temporada_media), float(r.delta_temporada_sd)
        lo, hi = mu - Z80 * sd, min(mu + Z80 * sd, 0.0)
        es, en = GRUPOS.get(r.grupo_nacionalidad, ([r.grupo_nacionalidad, ""], [r.grupo_nacionalidad, ""]))
        out[r.grupo_nacionalidad] = {"pct": round(100 * mu, 1), "lo80": round(100 * lo, 1), "hi80": round(100 * hi, 1),
                                     "n": int(r.n), "mostrar": bool(hi < 0 and sd > 0), "es": es, "en": en}
    return {"definicion": "Landing = efecto de temporada de la adaptación al cambio de liga del grupo de traspaso, en % del "
                          "nivel esperado tras la normalización; rango del 80 %. Explica el escalón entre NC₁ (con adaptación) "
                          "y NC₂ (sin ella). Se muestra sólo si el rango excluye 0.",
            "fuente": ruta, "metrica": "L_rel", "grupos": out}


SELLOS = [   # (clave, salida visible, sello del examen, estado, fuente)
    ("minutos", "Minutos por partido", "MEDIA", "propuesto", "estado_modelos ficha 1"),
    ("minutos_rango", "Rango de minutos (capa E, P5)", "ALTA", "propuesto", "V41_F1 §3; estado_modelos 19c"),
    ("produccion", "Producción por 100 posesiones", "MEDIA", "propuesto", "estado_modelos ficha 2"),
    ("nivel_kerno", "NIVEL KERNO (NC₁, NC₂ y por escenario)", "ALTA", "propuesto", "V40_F5 §11.5; estado_modelos ficha 7"),
    ("impacto", "IMPACTO", "MEDIA", "propuesto", "V40_F5; estado_modelos ficha 8"),
    ("net_equipo", "Net del equipo proyectado (y del escenario)", "ALTA", "propuesto", "V40_F4; estado_modelos 9 y 19b"),
    ("coste_ausencia", "Coste de su ausencia", "MEDIA", "aprobado", "V41_F3 §3 y §7.1 (H2)"),
    ("delta_companeros", "Cambio por compañero (minutos, uso, cuota de tiro, % asistidas, pts/100)", "BAJA", "aprobado", "V41_F3 §2 y §7.1 (H1)"),
    ("landing", "Landing", "BAJA", "propuesto", "sin examen propio en la v4.1 (modelo de adaptación v3.x)"),
    ("efecto_companeros", "Efecto sobre compañeros (F2-B)", "MEDIA", "propuesto", "estado_modelos ficha 11"),
    ("ortg_drtg", "ORtg / DRtg del equipo", "BAJA", "propuesto", "estado_modelos ficha 10"),
]
NIVEL = {"ALTA": ("alta", "high"), "MEDIA": ("moderada", "moderate"), "BAJA": ("baja", "low")}


def sellos(cfg: dict) -> dict:
    return {k: {"salida": s, "sello_examen": n, "confianza_es": NIVEL[n][0], "confianza_en": NIVEL[n][1], "estado": e,
                "fuente": f, "segmentos": {"ALTA": 3, "MEDIA": 2, "BAJA": 1}[n]} for k, s, n, e, f in SELLOS}


def i18n(cfg: dict) -> dict:
    return {
        "es": {"landing": "Landing", "landing_def": "Lo que suele costar el cambio de liga a su grupo de traspaso durante la temporada",
               "confianza": "confianza", "confianza_alta": "confianza alta", "confianza_moderada": "confianza moderada",
               "confianza_baja": "confianza baja", "sin_cambio": "sin cambio apreciable",
               "coste_ausencia": "Coste de su ausencia",
               "coste_ausencia_def": "Lo que cae el Net del equipo sin él, con sus minutos repartidos por el motor",
               "nc_escenario": "NIVEL KERNO en este escenario", "cambio_companeros": "Cambio en cada compañero",
               "cambio_companeros_def": "Minutos y uso de cada compañero con los movimientos del escenario frente a sin ellos",
               "rango80": "rango 80 %", "escenario": "Escenario", "alta": "alta", "baja_mov": "baja",
               "net_escenario": "Net del equipo en el escenario", "antes": "antes", "despues": "después",
               "reparto_total": "El motor acierta cuántos minutos se liberan, no quién los absorbe"},
        "en": {"landing": "Landing", "landing_def": "What the league move usually costs his transfer group over the season",
               "confianza": "confidence", "confianza_alta": "high confidence", "confianza_moderada": "moderate confidence",
               "confianza_baja": "low confidence", "sin_cambio": "no measurable change",
               "coste_ausencia": "Cost of his absence",
               "coste_ausencia_def": "How much the team's Net drops without him, with his minutes redistributed by the engine",
               "nc_escenario": "KERNO LEVEL in this scenario", "cambio_companeros": "Change for each teammate",
               "cambio_companeros_def": "Minutes and usage of each teammate with the scenario's moves versus without them",
               "rango80": "80% range", "escenario": "Scenario", "alta": "signing", "baja_mov": "departure",
               "net_escenario": "Team Net in the scenario", "antes": "before", "despues": "after",
               "reparto_total": "The engine gets the total minutes freed right, not who absorbs them"},
    }


def exportar(cfg: dict) -> dict:
    d = CE.dir_salida(cfg, "producto")
    res = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "landing": landing(cfg),
           "sellos": sellos(cfg), "i18n": i18n(cfg)}
    for k in ("landing", "sellos", "i18n"):
        (d / f"{k}.json").write_text(json.dumps(res[k], ensure_ascii=False, indent=1), encoding="utf-8")
    a = CE.RAIZ / "artifact" / "kerno" / "atlas" / "v41"
    a.mkdir(parents=True, exist_ok=True)
    (a / "producto.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return res
