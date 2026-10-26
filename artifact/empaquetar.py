"""Prepara la publicación del Artifact «Mesa Multiliga Baskonia» en lotes.

    python artifact/empaquetar.py <carpeta_salida>

* Publicado → origen: index.html = artifact/mesa-multiliga.html; atlas/, quintetos/ (páginas) y sus datos
  (atlas/simulador/ = data/artifact/simulador/, insumos del simulador v2, y atlas/simulador_v2.js, su motor);
  datos/ = data/artifact/{<temporada>/, normalizados/, normalizacion/, temporadas.json, diccionario_columnas.json}.
* Cada JSON se publica comprimido como <ruta>.gz.txt (los de menos de 256 KB, también en claro) (gzip en base64: el Artifact sólo sirve
  tipos de texto y una versión admite 256 MB); las páginas leen primero esa versión (cargarJSON) y si no
  existe, el .json. La ruta .json antigua se marca para borrar (null) en el último lote.
* Escribe <carpeta_salida>/lote<N>.json (≤ 58 MB y ≤ 250 ficheros por lote) con el mapa de ficheros.
"""
from __future__ import annotations

import base64
import gzip
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DA = RAIZ / "data" / "artifact"
UMBRAL = 256 * 1024
MAX_LOTE, MAX_FICHEROS = 58e6, 250


def mapa() -> dict[str, Path]:
    m = {"atlas/index.html": RAIZ / "artifact/atlas/index.html",
         "quintetos/index.html": RAIZ / "artifact/quintetos/index.html",
         "atlas/articulo/estilos_de_juego_baskonia.pdf": RAIZ / "docs/articulo/estilos_de_juego_baskonia.pdf"}
    for p in sorted((DA / "atlas" / "estilos").glob("*.json")):
        m[f"atlas/estilos/{p.name}"] = p
    m["atlas/simulador_v2.js"] = RAIZ / "artifact/atlas/simulador_v2.js"        # motor del simulador de encaje v2
    for p in sorted((DA / "simulador").glob("*.json")):
        if p.name != "paridad.json":
            m[f"atlas/simulador/{p.name}"] = p
    for p in sorted((DA / "quintetos" / "datos").rglob("*")):
        if p.is_file():
            m[f"quintetos/datos/{p.relative_to(DA / 'quintetos' / 'datos').as_posix()}"] = p
    for nombre in ("temporadas.json", "diccionario_columnas.json"):
        if (DA / nombre).exists():
            m[f"datos/{nombre}"] = DA / nombre
    for p in sorted(DA.rglob("*.json")):
        rel = p.relative_to(DA).as_posix()
        if rel.split("/")[0][:2] == "20" or rel.startswith(("normalizados/", "normalizacion/")):
            m[f"datos/{rel}"] = p
    return m


def main(salida: str) -> None:
    out = Path(salida)
    comp = out / "comprimidos"
    comp.mkdir(parents=True, exist_ok=True)
    final: dict[str, Path] = {}
    borrar = []
    for pub, src in mapa().items():
        if src.suffix == ".json":
            dst = comp / (pub.replace("/", "__") + ".gz.txt")
            if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
                dst.write_bytes(base64.b64encode(gzip.compress(src.read_bytes(), 9)))
            final[pub + ".gz.txt"] = dst
            if src.stat().st_size > UMBRAL:
                borrar.append(pub)
            else:               # los pequeños también en claro (páginas que los leen sin cargarJSON)
                final[pub] = src
        else:
            final[pub] = src
    # páginas e índices primero (la página no se rompe a mitad de la publicación)
    orden = sorted(final, key=lambda k: (not k.endswith(("index.html", "indice.json", "temporadas.json")), k))
    lotes, tam = [{}], [0.0]
    for k in orden:
        s = final[k].stat().st_size
        if tam[-1] + s > MAX_LOTE or len(lotes[-1]) >= MAX_FICHEROS:
            lotes.append({}); tam.append(0.0)
        lotes[-1][k] = str(final[k])
        tam[-1] += s
    for k in borrar:
        lotes[-1][k] = None
    for i, l in enumerate(lotes):
        (out / f"lote{i}.json").write_text(json.dumps(l, ensure_ascii=False), encoding="utf-8")
    print(f"{len(final)} ficheros, {sum(tam) / 1e6:.1f} MB en {len(lotes)} lotes: "
          + ", ".join(f"{t / 1e6:.1f}" for t in tam) + f" MB; {len(borrar)} rutas .json antiguas a borrar")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "publicacion")
