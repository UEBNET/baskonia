"""Prepara la publicación del Artifact «Mesa Multiliga Baskonia» en lotes.

    python artifact/empaquetar.py <carpeta_salida> [<origen de datos>]

* Origen de datos (por defecto data/artifact): carpeta con atlas/, quintetos/datos/, simulador/ y los datos de la Mesa
  (<temporada>/, normalizados/, normalizacion/, temporadas.json…), en la raíz o en <origen>/datos/ (la estructura de
  experimentos/v33_artifact, la que deja scripts/rehacer_identidades.sh).
* Publicado → origen: index.html = artifact/mesa-multiliga.html; atlas/, quintetos/ (páginas) y sus datos
  (atlas/simulador/ = <origen>/simulador/, insumos del simulador v3.3, y atlas/simulador.js, su motor v3.3;
  atlas/simulador_v2.js, el motor v2.1 anterior, se marca para borrar;
  atlas/informe_v3.js = lectura de fichaje en PDF; quintetos/estilos_unificados*.gz.txt = estilos de la taxonomía nueva);
  datos/ = <origen>/{<temporada>/, normalizados/, normalizacion/, temporadas.json, diccionario_columnas.json}.
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
DA = RAIZ / "data" / "artifact"          # origen de los datos (main: segundo argumento)
DD = DA                                  # datos de la Mesa (DA o DA/datos)
RETIRADOS = ["atlas/simulador_v2.js"]    # rutas publicadas que ya no se usan (se borran en el último lote)
UMBRAL = 256 * 1024
MAX_LOTE, MAX_FICHEROS = 58e6, 250


def _gzip(b: bytes) -> bytes:
    """gzip estándar (lo descomprime DecompressionStream); con zopfli, si está instalado, ≈ 4 % más pequeño (20 ligas:
    la versión del Artifact no puede pasar de 256 MB)."""
    try:
        import zopfli.gzip as zg
        return zg.compress(b, numiterations=1)
    except ImportError:
        return gzip.compress(b, 9)


def mapa() -> dict[str, Path]:
    # (el Atlas enlaza atlas/articulo/estilos_de_juego_vade.pdf, ya publicado: no se vuelve a subir)
    m = {"atlas/index.html": RAIZ / "artifact/atlas/index.html",
         "quintetos/index.html": RAIZ / "artifact/quintetos/index.html"}
    for p in sorted((DA / "atlas" / "estilos").glob("*.json")):
        m[f"atlas/estilos/{p.name}"] = p
    for p in sorted((DA / "atlas" / "informe").glob("*.json")):      # lectura de fichaje (bbestilo informe)
        m[f"atlas/informe/{p.name}"] = p
    m["atlas/simulador.js"] = RAIZ / "artifact/atlas/simulador.js"              # motor del simulador de encaje v3.3
    m["atlas/informe_v3.js"] = RAIZ / "artifact/atlas/informe_v3.js"            # lectura de fichaje (informe PDF v3)
    m["atlas/informe_equipo.js"] = RAIZ / "artifact/atlas/informe_equipo.js"    # informe de equipo (PDF)
    # estilos unificados para Equipos y quintetos (generados con artifact/herramientas/gen_eu_*.py)
    for nombre in ("estilos_unificados.gz.txt", "estilos_unificados_clubes.gz.txt"):
        m[f"quintetos/{nombre}"] = RAIZ / "artifact/quintetos" / nombre
    for p in sorted((DA / "simulador").glob("*.json")):
        if p.name != "paridad.json":
            m[f"atlas/simulador/{p.name}"] = p
    for p in sorted((DA / "quintetos" / "datos").rglob("*")):
        if p.is_file():
            m[f"quintetos/datos/{p.relative_to(DA / 'quintetos' / 'datos').as_posix()}"] = p
    for nombre in ("temporadas.json", "diccionario_columnas.json"):
        if (DD / nombre).exists():
            m[f"datos/{nombre}"] = DD / nombre
    for p in sorted(DD.rglob("*.json")):
        rel = p.relative_to(DD).as_posix()
        if p.name == "evaluacion_playoffs.json":
            continue    # 20 ligas: no cabe en los 256 MB de una versión; la fase de playoffs tiene pocos jugadores por
            #             liga (la evaluación de regular y total se publica entera; la página ya lo trata como en 2026-27)
        if rel.split("/")[0][:2] == "20" or rel.startswith(("normalizados/", "normalizacion/")):
            m[f"datos/{rel}"] = p
    return m


def main(salida: str, origen: str | None = None) -> None:
    global DA, DD
    if origen:
        DA = Path(origen).resolve()
    DD = DA / "datos" if (DA / "datos" / "temporadas.json").exists() else DA
    out = Path(salida)
    comp = out / "comprimidos"
    comp.mkdir(parents=True, exist_ok=True)
    final: dict[str, Path] = {}
    borrar = []
    for pub, src in mapa().items():
        if src.suffix == ".json":
            dst = comp / (pub.replace("/", "__") + ".gz.txt")
            if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
                dst.write_bytes(base64.b64encode(_gzip(src.read_bytes())))
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
    for k in borrar + RETIRADOS:
        lotes[-1][k] = None
    for i, l in enumerate(lotes):
        (out / f"lote{i}.json").write_text(json.dumps(l, ensure_ascii=False), encoding="utf-8")
    print(f"{len(final)} ficheros, {sum(tam) / 1e6:.1f} MB en {len(lotes)} lotes: "
          + ", ".join(f"{t / 1e6:.1f}" for t in tam) + f" MB; {len(borrar)} rutas .json antiguas a borrar")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "publicacion", sys.argv[2] if len(sys.argv) > 2 else None)
