"""Carga de configuración (config/sources.json)."""
from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "sources.json"


def load_config(path: str | Path | None = None) -> dict:
    p = Path(path) if path else DEFAULT_CONFIG
    with open(p, encoding="utf-8") as fh:
        cfg = json.load(fh)
    cfg["_path"] = str(p)
    cfg["_base_dir"] = str(p.resolve().parent.parent)
    return cfg


def resolve_path(cfg: dict, key: str, base_dir: str | Path | None = None) -> Path:
    rel = cfg.get("rutas", {}).get(key, f"data/{key}")
    p = Path(rel)
    if p.is_absolute():
        return p
    return Path(base_dir or cfg.get("_base_dir") or PROJECT_ROOT) / p


def active_leagues(cfg: dict) -> list[str]:
    return [k for k, v in cfg.get("ligas", {}).items() if v.get("activa", True)]
