"""Lectura de configs/*.yaml (umbrales e hiperparámetros) con caché."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
DIR_CONFIGS = RAIZ / "configs"
DIR_PROC = RAIZ / "data" / "processed"
DIR_MOD = RAIZ / "data" / "modelos"


@lru_cache(maxsize=None)
def cargar(nombre: str) -> dict:
    """configs/<nombre>.yaml como diccionario (KeyError claro si falta)."""
    if nombre == "simulation" and os.environ.get("CERNO_SIMULADOR") in ("v3", "v31", "v32", "v33", "v40", "v42"):
        # simulador v3 (configs/simulation_v3.yaml) o v3.1 (configs/simulation_v31.yaml); sin la variable, la v2
        # (v42: CERNO v4.2 · D2, configs/simulation_v42.yaml; la v3.3 y las demás no cambian)
        nombre = f"simulation_{os.environ['CERNO_SIMULADOR']}"
    p = DIR_CONFIGS / f"{nombre}.yaml"
    if not p.exists():
        raise FileNotFoundError(f"falta {p}")
    d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    var = os.environ.get("CERNO_SIM_VARIANTE")
    if nombre.startswith("simulation") and var:
        # v3.2 · A1: examen con un paso del motor apagado («sin_<paso>»); la etiqueta separa sus cachés y resultados
        pasos = {**(d.get("pasos") or {})}
        for parte in var.split("+"):                 # «sin_a+sin_b»: combinación de pasos apagados (§2)
            paso = parte.removeprefix("sin_")
            if paso not in pasos:
                raise KeyError(f"CERNO_SIM_VARIANTE={var}: el paso «{paso}» no está en pasos")
            pasos[paso] = False
        d["pasos"] = pasos
        d["variante"] = var
    return d
