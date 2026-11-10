"""Configuración, rutas, semillas y huellas (hashes) de la v5.0.

Una configuración YAML por fase en `configs/v5/<fase>.yaml`. Todas las salidas llevan en sus metadatos la versión, el
hash de la configuración y el hash de los datos de entrada (principio 5 del encargo).
"""
from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
DIR_CONFIGS = RAIZ / "configs" / "v5"
DIR_DATOS = RAIZ / "data" / "v5"


def cargar(ruta: str | Path) -> dict:
    """Lee el YAML de una fase (ruta absoluta o relativa a la raíz del repositorio)."""
    p = Path(ruta)
    if not p.is_absolute():
        p = RAIZ / p
    cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
    cfg["_ruta"] = str(p.relative_to(RAIZ))
    return cfg


def hash_config(cfg: dict) -> str:
    """Huella corta y estable de la configuración (sin claves internas que empiecen por «_»)."""
    limpio = {k: v for k, v in cfg.items() if not str(k).startswith("_")}
    return hashlib.sha256(json.dumps(limpio, sort_keys=True, default=str).encode()).hexdigest()[:12]


def hash_ficheros(rutas) -> str:
    """Huella del contenido de una lista de ficheros (orden por nombre). Los que no existen cuentan como ausentes."""
    h = hashlib.sha256()
    for r in sorted(Path(x) for x in rutas):
        p = r if r.is_absolute() else RAIZ / r
        h.update(str(p.relative_to(RAIZ) if p.is_relative_to(RAIZ) else p).encode())
        if p.exists():
            with open(p, "rb") as f:
                for bloque in iter(lambda: f.read(1 << 20), b""):
                    h.update(bloque)
        else:
            h.update(b"<ausente>")
    return h.hexdigest()[:16]


def dir_fase(cfg: dict) -> Path:
    """Carpeta de salida de la fase: data/v5/<salida>."""
    d = DIR_DATOS / cfg["salida"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def metadatos(cfg: dict, entradas: list | None = None, extra: dict | None = None) -> dict:
    """Bloque de metadatos que acompaña a cada salida."""
    from bbnorm5 import VERSION
    return {"version_modelo": VERSION, "fase": cfg.get("fase"), "config": cfg.get("_ruta"),
            "hash_config": hash_config(cfg),
            "hash_datos_entrada": hash_ficheros(entradas) if entradas else None,
            "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "python": platform.python_version(), **(extra or {})}


def escribir_json(obj, ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=_por_defecto), encoding="utf-8")


def _por_defecto(o):
    import numpy as np
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)
