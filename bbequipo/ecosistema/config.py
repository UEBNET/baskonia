"""configs/ecosistema_v41.yaml: única fuente de hiperparámetros de la v4.1 (el código no fija ninguno)."""
from __future__ import annotations

import copy
import zlib
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
RUTA_CFG = RAIZ / "configs" / "ecosistema_v41.yaml"


def cargar(ruta: Path | None = None) -> dict:
    return yaml.safe_load(Path(ruta or RUTA_CFG).read_text(encoding="utf-8"))


def cargar_v40(cfg: dict) -> dict:
    """Configuración cerrada de la v4.0 (sólo lectura)."""
    from .. import config as C40
    return C40.cargar(RAIZ / cfg["base"]["config_v40"])


def dir_salida(cfg: dict, *sub: str) -> Path:
    d = RAIZ / cfg.get("salida", "data/modelos/v4_1")
    for s in sub:
        d = d / s
    d.mkdir(parents=True, exist_ok=True)
    return d


def semilla(cfg: dict, clave: str) -> int:
    """Semilla derivada y estable: semilla general + crc32 de la clave (liga|temporada, bloque…)."""
    return (int(cfg["semilla"]) + zlib.crc32(clave.encode("utf-8"))) % (2 ** 32)


def con(cfg: dict, **cambios) -> dict:
    out = copy.deepcopy(cfg)
    for k, v in cambios.items():
        d = out
        *partes, ult = k.split(".")
        for r in partes:
            d = d.setdefault(r, {})
        d[ult] = v
    return out
