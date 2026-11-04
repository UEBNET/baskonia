"""Cifras del artículo, leídas de los ficheros de resultados versionados (nada se escribe a mano si existe el dato)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
MOD = RAIZ / "data" / "modelos"

NOMBRES = {"euroleague": "EuroLeague", "eurocup": "EuroCup", "acb": "ACB", "nba": "NBA", "gleague": "G League",
           "lba": "LBA", "bbl": "BBL", "lnb": "LNB", "bcl": "BCL", "fec": "FIBA Europe Cup", "bsl": "BSL",
           "gbl": "GBL", "feb1": "Primera FEB", "feb2": "Segunda FEB", "feb3": "Tercera FEB", "cba": "CBA",
           "bnxt": "BNXT", "ncaa": "NCAA (top-50)", "nbl": "NBL", "vtb": "VTB"}
PIEZAS = {"ciclo": "Consistencia de ciclo", "film": "FiLM por liga", "cabezal_liga": "Cabezal por liga",
          "unicidad": "Factor propio ζ", "ipw": "Reponderación de puentes (IPW)", "K8": "Latente K = 8 (frente a 4)",
          "student": "t de Student (B6)", "refinado": "Inferencia semiamortizada (B4)"}


def _json(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def cargar() -> dict:
    R = {}
    v32 = MOD / "v3_2"
    R["ablacion"] = _json(v32 / "validacion" / "ablacion" / "decisiones.json")
    R["examen_v32"] = _json(v32 / "validacion" / "examen_v32.json")
    R["examen_v31_15"] = _json(MOD / "v3_1" / "validacion" / "examen_v31.json")
    R["resumen_v32"] = _json(v32 / "resumen.json")
    R["combinada_v32"] = _json(v32 / "resumen_combinada.json")
    R["sim_v32"] = _json(MOD / "simulador" / "v3_2" / "decisiones_v32.json")
    R["sim_v31"] = _json(MOD / "simulador" / "v3_1" / "validacion" / "V31_inicio_adapt" / "resumen.json")
    b7 = sorted((MOD / "simulador" / "v3_2").glob("evaluacion_b7_b9_*corte*.json")) or \
        sorted((MOD / "simulador" / "v3_2").glob("evaluacion_b7_b9_*.json"))
    R["b7b9"] = _json(b7[-1]) if b7 else None
    f = v32 / "destino" / "reduccion_varianza_pares.csv"
    R["pares"] = pd.read_csv(f) if f.exists() else None
    R["constantes_destino"] = _json(v32 / "destino" / "constantes.json")
    f = (v32 if (v32 / "niveles.csv").exists() else MOD / "v3_1") / "niveles.csv"
    R["niveles"] = pd.read_csv(f)
    R["niveles_fuente"] = f.parent.name
    R["puentes"] = pd.read_csv((v32 if (v32 / "puentes.csv").exists() else MOD / "v3_1") / "puentes.csv")
    R["ciclo"] = pd.read_csv(MOD / "v3_1" / "ciclo.csv")
    R["estilos"] = _json(MOD / "estilos_unificados" / "estilos.json")
    R["auditoria"] = (v32 / "auditoria_puentes" / "muestra_puentes.csv").exists()
    R["auditoria_identidades"] = _json(MOD / "simulador" / "v3_3" / "auditoria.json") or \
        _json(MOD / "simulador" / "v3_2" / "auditoria.json")
    R["evaluacion_puentes"] = _json(v32 / "auditoria_puentes" / "evaluacion.json")
    R["sim_v33"] = _json(MOD / "simulador" / "v3_3" / "decisiones_v33.json")
    return R


def niveles_liga(R: dict, metrica: str = "per", temporada: str = "2025-26") -> pd.DataFrame:
    """Nivel de cada liga (gauge = media ponderada) en la temporada dada, con su DT y sus puentes."""
    d = R["niveles"]
    d = d[(d["metrica"] == metrica) & (d["temporada"] == temporada)]
    return d.sort_values("nivel_gauge_media", ascending=False)


def ciclo_resumen(R: dict) -> dict:
    c = R["ciclo"]
    r = c[[x for x in c.columns if x.startswith("res_")]].abs()
    return {"triangulos": int(len(c)), "medio": float(r.to_numpy().mean()), "max_pts": float(c["res_pts_p100"].abs().max()),
            "max_ts": float(c["res_ts_pct"].abs().max()), "altos": int((r.max(axis=1) > 0.5).sum())}
