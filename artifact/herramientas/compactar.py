"""Compacta data/artifact antes de empaquetar (límite de 256 MB por versión del Artifact), sin perder información
que lean las páginas.

    python artifact/herramientas/compactar.py [data/artifact]

1. datos/<t>/{regular,total,playoffs}.json (tablas de 480 columnas): formato por columnas («por_columna») y cifras
   a 4 cifras significativas. La Mesa y el Atlas reconstruyen las filas al leer (porFilas).
2. normalizados/<t>/regular.json: fuera las columnas <m>_am, <m>_am_lo, <m>_am_hi, <m>_am_pctel y <m>_A_am, copias
   exactas de <m>, <m>_lo, <m>_hi, <m>_pctel y <m>_A (en la v3.1 las dos llevan la estimación final; se comprueba
   antes de quitarlas: si alguna no coincide, se conserva). Ninguna página lee las _am.
3. <t>/evaluacion_*.json: cifras a 4 cifras significativas.
4. normalizados/<t>/regular.json y normalizacion/jugadores_<t>.json: fuera las filas con menos de `MIN_NORM` minutos
   (estimación casi toda incertidumbre: prior de la CVAE); siguen completas en data/modelos/v3_1/normalizado.
Todas las cifras de las tablas: 4 cifras significativas (no decimales fijos: WS/40 ≈ 0,14 conserva sus decimales).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path


MIN_NORM = 100      # = filtro por defecto de la Mesa («Minutos mín. 100»)


def _r(o, n=4):
    """4 cifras significativas."""
    if isinstance(o, float):
        if not math.isfinite(o) or o == 0:
            return o
        return round(o, max(0, n - 1 - int(math.floor(math.log10(abs(o))))))
    if isinstance(o, list):
        return [_r(x, n) for x in o]
    if isinstance(o, dict):
        return {k: _r(v, n) for k, v in o.items()}
    return o


def _w(p: Path, d) -> None:
    p.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def tablas(p: Path) -> None:
    d = json.loads(p.read_text(encoding="utf-8"))
    if "filas" not in d:
        return
    F, n = d.pop("filas"), len(d["columnas"])
    d["por_columna"] = [[_r(f[j]) for f in F] for j in range(n)]
    _w(p, d)


def normalizados(p: Path) -> int:
    d = json.loads(p.read_text(encoding="utf-8"))
    C, F = d["columnas"], d["filas"]
    ix = {c: i for i, c in enumerate(C)}
    quitar = set()
    for c in C:
        for suf, base_suf in (("_am_pctel", "_pctel"), ("_am_lo", "_lo"), ("_am_hi", "_hi"), ("_A_am", "_A"), ("_am", "")):
            if c.endswith(suf):
                base = c[: -len(suf)] + base_suf
                if base in ix and all(f[ix[c]] == f[ix[base]] for f in F):
                    quitar.add(ix[c])
                break
    keep = [i for i in range(len(C)) if i not in quitar]
    im = ix.get("min")
    F = [f for f in F if im is None or (f[im] or 0) >= MIN_NORM]
    d["columnas"] = [C[i] for i in keep]
    d["filas"] = [[_r(f[i]) for i in keep] for f in F]
    _w(p, d)
    return len(quitar)


def main(raiz: str = "data/artifact") -> None:
    R = Path(raiz)
    for p in sorted(R.glob("20*-*/*.json")):
        if p.stem in ("regular", "total", "playoffs"):
            tablas(p)
        elif p.stem.startswith("evaluacion_"):
            _w(p, _r(json.loads(p.read_text(encoding="utf-8"))))
    for p in sorted([*R.glob("normalizados/20*-*/regular.json"), *R.glob("normalizados/20*-*/regular_v51.json")]):
        print(p, "columnas duplicadas quitadas:", normalizados(p))
    for p in sorted(R.glob("normalizacion/jugadores_*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        im = d["columnas"].index("min") if "min" in d["columnas"] else None
        d["filas"] = [[_r(x) for x in f] for f in d["filas"] if im is None or (f[im] or 0) >= MIN_NORM]
        _w(p, d)


if __name__ == "__main__":
    main(*sys.argv[1:])
