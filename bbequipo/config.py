"""configs/equipo_v40.yaml: la única fuente de hiperparámetros de la v4.0 (el código no fija ninguno)."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
RUTA_CFG = RAIZ / "configs" / "equipo_v40.yaml"


def cargar(ruta: Path | None = None) -> dict:
    p = Path(ruta) if ruta else RUTA_CFG
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def dir_salida(cfg: dict) -> Path:
    return RAIZ / cfg.get("salida", "data/modelos/v4_0")


def ruta(cfg: dict, clave: str, **fmt) -> Path:
    """Ruta de un insumo (`insumos.<clave>`), relativa a la raíz del repositorio."""
    v = cfg["insumos"][clave]
    return RAIZ / (v.format(**fmt) if fmt else v)


def con(cfg: dict, **cambios) -> dict:
    """Copia con cambios por ruta «seccion.clave» (p. ej. con(cfg, **{"perfil.latente.K": 3}))."""
    out = copy.deepcopy(cfg)
    for k, v in cambios.items():
        d = out
        *partes, ult = k.split(".")
        for r in partes:
            d = d.setdefault(r, {})
        d[ult] = v
    return out


def huella(cfg: dict, secciones: tuple[str, ...] = ("perfil", "contrato", "insumos")) -> str:
    """SHA-1 corto de las secciones que determinan una salida (queda en su meta.json)."""
    sub = {k: cfg.get(k) for k in secciones}
    return hashlib.sha1(json.dumps(sub, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()[:10]
