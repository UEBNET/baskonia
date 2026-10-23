"""Lectura de configs/*.yaml (umbrales e hiperparámetros) con caché."""
from __future__ import annotations

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
    p = DIR_CONFIGS / f"{nombre}.yaml"
    if not p.exists():
        raise FileNotFoundError(f"falta {p}")
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
