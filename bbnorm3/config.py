"""configs/normalization_v3.yaml (v3.0), configs/normalization_v31.yaml (v3.1) y configs/version.yaml."""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
DIR_SALIDA = RAIZ / "data" / "modelos" / "v3"


def cargar(ruta: Path | None = None) -> dict:
    p = ruta or RAIZ / "configs" / "normalization_v3.yaml"
    return yaml.safe_load(Path(p).read_text(encoding="utf-8"))


def dir_salida(cfg: dict) -> Path:
    """Carpeta de salida de una versión (v3.0: data/modelos/v3; v3.1: data/modelos/v3_1)."""
    return RAIZ / cfg.get("salida", "data/modelos/v3")


def con(cfg: dict, **cambios) -> dict:
    """Copia de la configuración con cambios por ruta «seccion.clave» (p. ej. con(cfg, **{"latente.K": 4}))."""
    out = copy.deepcopy(cfg)
    for k, v in cambios.items():
        d = out
        *ruta, ult = k.split(".")
        for r in ruta:
            d = d[r]
        d[ult] = v
    return out


def version_activa() -> str:
    p = RAIZ / "configs" / "version.yaml"
    if not p.exists():
        return "v1"
    return str((yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("version_activa", "v1"))
