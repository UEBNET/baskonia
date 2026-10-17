"""Almacén bruto: un JSON original por liga y temporada, con fecha, nunca modificado.

Estructura:
    data/raw/<liga>/<temporada>/<liga>_<temporada>_<YYYYmmddTHHMMSSZ>.json[.gz]

Contenido del fichero (sobre / envelope):
    {
      "meta": {liga, temporada, adaptador, version_adaptador, fuente, fecha_extraccion,
               peticiones: [...], errores: [...]},
      "payload": { ... respuestas originales de la fuente, sin transformar ... }
    }
Las respuestas HTML (p.ej. ACB) se guardan como texto dentro del payload.
"""
from __future__ import annotations

import gzip
import json
import os
import re
from pathlib import Path
from typing import Any

from .utils import utc_stamp


_SNAP_RE = re.compile(r"_(\d{8}T\d{6}Z)(?:-(\d+))?\.json")


def _snapshot_key(p: Path) -> tuple:
    m = _SNAP_RE.search(p.name)
    return (m.group(1), int(m.group(2) or 1)) if m else ("", 0)


class RawStore:
    def __init__(self, root: str | Path, compress: bool = False) -> None:
        self.root = Path(root)
        self.compress = compress

    def _dir(self, league: str, season: str) -> Path:
        return self.root / league / season

    def save(self, league: str, season: str, meta: dict, payload: Any, kind: str = "") -> Path:
        """`kind` distingue otros brutos de la misma liga y temporada en la misma carpeta
        (p.ej. "pbp" → pbp_<liga>_<temporada>_<fecha>.json.gz, jugada a jugada por partido)."""
        d = self._dir(league, season)
        d.mkdir(parents=True, exist_ok=True)
        stamp = meta.get("fecha_extraccion_stamp") or utc_stamp()
        name = f"{kind + '_' if kind else ''}{league}_{season}_{stamp}.json" + (".gz" if self.compress else "")
        path = d / name
        n = 2
        while path.exists():  # nunca sobrescribir un bruto existente
            path = d / name.replace(f"_{stamp}.", f"_{stamp}-{n}.")
            n += 1
        doc = {"meta": meta, "payload": payload}
        tmp = path.with_suffix(path.suffix + ".tmp")
        data = json.dumps(doc, ensure_ascii=False).encode("utf-8")
        if self.compress:
            data = gzip.compress(data)
        tmp.write_bytes(data)
        os.replace(tmp, path)
        try:  # protección de solo lectura (best effort)
            path.chmod(0o444)
        except OSError:
            pass
        return path

    def list(self, league: str, season: str, kind: str = "") -> list[Path]:
        d = self._dir(league, season)
        if not d.exists():
            return []
        prefix = f"{kind + '_' if kind else ''}{league}_{season}_"
        files = [p for p in d.iterdir() if p.name.startswith(prefix) and p.name.endswith((".json", ".json.gz"))]
        return sorted(files, key=_snapshot_key)

    def latest(self, league: str, season: str, kind: str = "") -> Path | None:
        files = self.list(league, season, kind)
        return files[-1] if files else None

    def load_season(self, league: str, season: str) -> tuple[Path | None, dict | None]:
        """Último bruto principal de la liga y temporada: (ruta, documento {"meta", "payload"}).

        Si el payload es INCREMENTAL (`payload["incremental"] = True`: cada paquete guarda sólo los partidos
        descargados en esa ejecución, troceado para que ningún fichero pase de ~40 MB), se unen los
        `games` de todos los paquetes incrementales de la temporada, del más antiguo al más reciente
        (un partido repetido se queda con la versión más reciente); igual con las demás claves de
        `claves_incrementales` (por defecto sólo "games"). El resto de claves son las del último."""
        files = self.list(league, season)
        if not files:
            return None, None
        doc = self.load(files[-1])
        payload = doc.get("payload")
        if not (isinstance(payload, dict) and payload.get("incremental")):
            return files[-1], doc
        keys = payload.get("claves_incrementales") or ["games"]
        acc: dict = {k: {} for k in keys}
        for p in files[:-1]:
            prev = self.load(p).get("payload")
            if isinstance(prev, dict) and prev.get("incremental"):
                for k in keys:
                    acc[k].update(prev.get(k) or {})
        for k in keys:
            acc[k].update(payload.get(k) or {})
        merged = {**payload, **acc, "paquetes": [p.name for p in files]}
        return files[-1], {"meta": doc.get("meta") or {}, "payload": merged}

    @staticmethod
    def load(path: str | Path) -> dict:
        p = Path(path)
        raw = p.read_bytes()
        if p.name.endswith(".gz"):
            raw = gzip.decompress(raw)
        return json.loads(raw.decode("utf-8"))
