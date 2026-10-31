"""Carga de configuración (config/sources.json)."""
from __future__ import annotations

import json
import threading
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


def minutos_partido(lcfg: dict, season: str | None = None) -> float:
    """Duración reglamentaria del partido: `temporadas.<t>.minutos_partido` si existe (p.ej. la CBA, 48' hasta
    2024-25 y 40' desde 2025-26) y si no `minutos_partido` de la liga (40 por defecto)."""
    sc = ((lcfg or {}).get("temporadas") or {}).get(season or "") or {}
    return float(sc.get("minutos_partido") or (lcfg or {}).get("minutos_partido") or 40)


def season_label(start_year: int) -> str:
    """2020 -> '2020-21'."""
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def season_range(desde: str, hasta: str) -> list[str]:
    """Temporadas entre `desde` y `hasta` (ambas incluidas), de la más reciente a la más antigua.

    Se recorren de nueva a antigua porque algunas fuentes (BBL) usan los ids de la temporada
    posterior para localizar los de la anterior."""
    a, b = int(desde[:4]), int(hasta[:4])
    if a > b:
        a, b = b, a
    return [season_label(y) for y in range(b, a - 1, -1)]


def configured_seasons(cfg: dict) -> list[str]:
    """Temporadas del proyecto: de `temporada_inicial` a `temporada_por_defecto` (más reciente primero)."""
    last = cfg.get("temporada_por_defecto", "2025-26")
    return season_range(cfg.get("temporada_inicial", last), last)


_SAVE_LOCK = threading.Lock()


def _deep_merge(dst: dict, src: dict) -> None:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v


def update_league_config(cfg: dict, liga: str, updates: dict) -> bool:
    """Aplica `updates` a la config de una liga en memoria y, si la config viene de un fichero,
    lo guarda también en ese fichero (sources.json), releyéndolo para no pisar otros cambios.
    Devuelve True si se escribió en disco."""
    with _SAVE_LOCK:
        _deep_merge(cfg.setdefault("ligas", {}).setdefault(liga, {}), updates)
        path = cfg.get("_path")
        if not path or not cfg.get("guardar_descubrimientos", True):
            return False
        p = Path(path)
        on_disk = json.loads(p.read_text(encoding="utf-8"))
        _deep_merge(on_disk.setdefault("ligas", {}).setdefault(liga, {}), updates)
        p.write_text(json.dumps(on_disk, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return True
