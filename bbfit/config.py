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
    if nombre == "simulation" and os.environ.get("CERNO_SIMULADOR") in ("v3", "v31"):
        # simulador v3 (configs/simulation_v3.yaml) o v3.1 (configs/simulation_v31.yaml); sin la variable, la v2
        nombre = f"simulation_{os.environ['CERNO_SIMULADOR']}"
    p = DIR_CONFIGS / f"{nombre}.yaml"
    if not p.exists():
        raise FileNotFoundError(f"falta {p}")
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
