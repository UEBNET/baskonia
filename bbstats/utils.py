"""Utilidades comunes: parseo numérico, minutos, normalización de claves."""
from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Iterable

_NUM_RE = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_stamp(dt: datetime | None = None) -> str:
    """Sello de tiempo apto para nombres de fichero: 20251012T101500Z."""
    return (dt or utc_now()).strftime("%Y%m%dT%H%M%SZ")


def to_float(value: Any) -> float | None:
    """Convierte cualquier valor de origen a float, o None si no es numérico.

    Acepta '55.3%', '12,5', ' 7 ', 3, 3.0, True no (se descarta), '' -> None.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return None if (isinstance(value, float) and math.isnan(value)) else float(value)
    s = str(value).strip().replace("\xa0", "")
    if not s or s in {"-", "--", "—", "N/A", "n/a", "null", "None"}:
        return None
    s = s.rstrip("%").strip()
    if ":" in s:  # formato de minutos
        return parse_minutes(s)
    if _NUM_RE.match(s):
        return float(s.replace(",", "."))
    try:
        return float(s)
    except ValueError:
        return None


_ISO_DUR = re.compile(r"^PT(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?$")


def parse_minutes(value: Any) -> float | None:
    """Minutos jugados en formato decimal.

    Soporta 25.5, '25:30', '1:05:12' (h:m:s), 'PT25M30.00S' (ISO 8601) y '25'.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return None if (isinstance(value, float) and math.isnan(value)) else float(value)
    s = str(value).strip()
    if not s or s in {"-", "--", "DNP", "NJ"}:
        return None
    m = _ISO_DUR.match(s)
    if m:
        h, mi, se = (float(x) if x else 0.0 for x in m.groups())
        return h * 60 + mi + se / 60
    if ":" in s:
        parts = s.split(":")
        try:
            nums = [float(p.replace(",", ".")) for p in parts]
        except ValueError:
            return None
        if len(nums) == 2:
            return nums[0] + nums[1] / 60
        if len(nums) == 3:
            # Algunas fuentes usan h:m:s para totales de temporada (p.ej. 1:05:12)
            return nums[0] * 60 + nums[1] + nums[2] / 60
        return None
    return to_float(s)


def parse_made_attempted(value: Any) -> tuple[float | None, float | None]:
    """'5/9' -> (5, 9). Cualquier otro formato -> (None, None)."""
    if value is None:
        return None, None
    m = re.match(r"^\s*(\d+)\s*/\s*(\d+)\s*$", str(value))
    if not m:
        return None, None
    return float(m.group(1)), float(m.group(2))


def parse_sum_pair(value: Any) -> tuple[float | None, float | None]:
    """'5+2' -> (5, 2). Usado p.ej. en ACB para rebotes 'D+O'."""
    if value is None:
        return None, None
    m = re.match(r"^\s*(\d+)\s*\+\s*(\d+)\s*$", str(value))
    if not m:
        return None, None
    return float(m.group(1)), float(m.group(2))


def norm_key(key: str) -> str:
    """Normaliza una clave de origen para buscar alias: minúsculas, sin acentos ni símbolos."""
    k = unicodedata.normalize("NFKD", str(key)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9%+/]", "", k.lower())


def slugify(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


def first_present(d: dict, keys: Iterable[str]) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def flatten(d: Any, prefix: str = "", sep: str = ".") -> dict:
    """Aplana diccionarios anidados: {'player': {'team': {'code': 'BAS'}}} -> {'player.team.code': 'BAS'}."""
    out: dict = {}
    if isinstance(d, dict):
        for k, v in d.items():
            key = f"{prefix}{sep}{k}" if prefix else str(k)
            if isinstance(v, dict):
                out.update(flatten(v, key, sep))
            else:
                out[key] = v
    return out


def height_to_cm(value: Any) -> float | None:
    """'6-8' (pies-pulgadas), '2.03' (m), '203' (cm) -> cm."""
    if value is None or value == "":
        return None
    s = str(value).strip()
    m = re.match(r"^(\d)\s*[-' ]\s*(\d{1,2})\"?$", s)
    if m:
        return round((int(m.group(1)) * 12 + int(m.group(2))) * 2.54, 1)
    f = to_float(s)
    if f is None:
        return None
    if f < 3:  # metros
        return round(f * 100, 1)
    if f < 100:  # pulgadas
        return round(f * 2.54, 1)
    return f


def weight_to_kg(value: Any, unit_hint: str = "kg") -> float | None:
    f = to_float(value)
    if f is None:
        return None
    if unit_hint == "lb" or f > 160:  # >160 casi seguro libras
        return round(f * 0.45359237, 1)
    return f
