"""Reparto de la publicación incremental entre los tres artifacts de Kerno Analytics (v4.2).

Desde el 09-11-2026 el producto son tres artifacts con los mismos ficheros fuente (docs/checkpoints/V42_sitios.md):

    jugadores    https://claude.ai/artifact/A7rufkL84rvRFcUBFBxFbC   (la URL de siempre; lleva el botón)
    equipos      https://claude.ai/artifact/SXFgQ6CpytxT3ZZupcEFcj
    metodologia  https://claude.ai/artifact/T83MBGZk5untACmegadfNn

Cada uno publica sólo las rutas de su manifiesto (`artifact/kerno/sitios/<sitio>.json`, lista `ficheros`). El lote único
de la actualización (`lote0.json`, ruta publicada → fichero local) se reparte así:

1. una ruta que está en el manifiesto de un sitio va a ese sitio (una ruta común va a los que la tengan);
2. una ruta nueva (p. ej. la primera vez que una liga tiene alineaciones en la temporada) va a los sitios que publican
   rutas «hermanas»: misma carpeta, mismo tipo (`.gz.txt` o en claro) y misma clase (`.extras` o no);
3. el duplicado en claro de un JSON cuya versión `.gz.txt` va en el lote no se publica si ningún manifiesto lo lista
   (los sitios leen la versión comprimida);
4. lo demás queda en `sin_sitio` y se informa (no se publica).

Las rutas nuevas del punto 2 se anotan en los manifiestos (`anotar_nuevas`), que la sesión sube a Git con los datos.

Nunca se reintroduce una ruta de `borrar_al_republicar` (Jugadores dejó de publicar los quintetos).

Cada sitio se trocea en lotes de ≤ 58 MB y ≤ 250 ficheros (límites de una publicación: 64 MB y 255 ficheros) y se
escriben `lote_<sitio>_<n>.json` y `sitios.json` (resumen: URL, lotes, ficheros, MB, rutas nuevas y sin sitio).
"""
from __future__ import annotations

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MANIFIESTOS = RAIZ / "artifact" / "kerno" / "sitios"
SITIOS = ("jugadores", "equipos", "metodologia")
MAX_LOTE, MAX_FICHEROS = 58e6, 250


def manifiestos(carpeta: Path = MANIFIESTOS) -> dict[str, dict]:
    out = {}
    for s in SITIOS:
        m = json.loads((carpeta / f"{s}.json").read_text(encoding="utf-8"))
        url = json.loads((carpeta / f"sitio_{s}.json").read_text(encoding="utf-8"))["urls"][s]
        out[s] = {"url": url, "ficheros": set(m["ficheros"]), "borrar": set(m.get("borrar_al_republicar") or [])}
    return out


def _clase(ruta: str) -> tuple[str, bool, bool]:
    carpeta, _, nombre = ruta.rpartition("/")
    return carpeta, nombre.endswith(".gz.txt"), ".extras." in nombre


def destinos(ruta: str, lote: dict, man: dict[str, dict]) -> tuple[list[str], str]:
    """(sitios, motivo) de una ruta publicada; motivo ∈ manifiesto, hermanas, duplicado_en_claro, sin_sitio."""
    en = [s for s in SITIOS if ruta in man[s]["ficheros"]]
    if en:
        return en, "manifiesto"
    if ruta.endswith(".json") and ruta + ".gz.txt" in lote:
        return [], "duplicado_en_claro"
    c = _clase(ruta)
    en = [s for s in SITIOS if ruta not in man[s]["borrar"]
          and any(_clase(r) == c for r in man[s]["ficheros"])]
    return (en, "hermanas") if en else ([], "sin_sitio")


def trocear(rutas: dict[str, str], max_mb: float = MAX_LOTE, max_n: int = MAX_FICHEROS) -> list[dict[str, str]]:
    lotes, tam = [{}], [0]
    for k, v in rutas.items():
        s = Path(v).stat().st_size if v else 0
        if lotes[-1] and (tam[-1] + s > max_mb or len(lotes[-1]) >= max_n):
            lotes.append({}), tam.append(0)
        lotes[-1][k] = v
        tam[-1] += s
    return [l for l in lotes if l]


def anotar_nuevas(nuevas: dict[str, list[str]], carpeta: Path = MANIFIESTOS) -> None:
    """Añade las rutas nuevas a los manifiestos de sus sitios (para que una republicación completa las incluya)."""
    for s in SITIOS:
        rutas = [r for r, en in nuevas.items() if s in en]
        if not rutas:
            continue
        f = carpeta / f"{s}.json"
        m = json.loads(f.read_text(encoding="utf-8"))
        m["ficheros"] = sorted(set(m["ficheros"]) | set(rutas))
        m["n_ficheros"] = len(m["ficheros"])
        f.write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def repartir(lote: dict[str, str], salida: Path, carpeta: Path = MANIFIESTOS, anotar: bool = True) -> dict:
    """Escribe lote_<sitio>_<n>.json y sitios.json en `salida`; devuelve el resumen. Con `anotar`, las rutas nuevas
    asignadas por sus hermanas pasan a los manifiestos."""
    salida = Path(salida)
    for f in salida.glob("lote_*_*.json"):
        f.unlink()
    man = manifiestos(carpeta)
    por_sitio: dict[str, dict[str, str]] = {s: {} for s in SITIOS}
    nuevas, sin_sitio, claro = {}, [], []
    for ruta, local in lote.items():
        en, motivo = destinos(ruta, lote, man)
        for s in en:
            por_sitio[s][ruta] = local
        if motivo == "hermanas":
            nuevas[ruta] = en
        elif motivo == "sin_sitio":
            sin_sitio.append(ruta)
        elif motivo == "duplicado_en_claro":
            claro.append(ruta)
    resumen = {"sitios": {}, "rutas_nuevas": nuevas, "sin_sitio": sin_sitio, "duplicados_en_claro_omitidos": len(claro)}
    for s in SITIOS:
        trozos = trocear(por_sitio[s])
        nombres = []
        for i, t in enumerate(trozos):
            p = salida / f"lote_{s}_{i}.json"
            p.write_text(json.dumps(t, ensure_ascii=False, indent=0), encoding="utf-8")
            nombres.append(str(p))
        tam = sum(Path(v).stat().st_size for v in por_sitio[s].values() if v)
        resumen["sitios"][s] = {"url": man[s]["url"], "ficheros": len(por_sitio[s]), "mb": round(tam / 1e6, 1),
                                "lotes": nombres}
    (salida / "sitios.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    if anotar and nuevas:
        anotar_nuevas(nuevas, carpeta)
    return resumen


# ============================================================================================ publicación completa
FUENTE = RAIZ / "artifact" / "kerno"           # fuente de las páginas, el código y los datos v4.1/v4.2 de los tres sitios
NOMBRES = {"jugadores": "Jugadores", "equipos": "Equipos", "metodologia": "Metodología"}
NO_FUENTE = ("index.html", "README.md", "sitio.json")       # página propia de cada sitio, documentación, interruptor


def pagina(sitio: str, salida: Path) -> Path:
    """Página de un sitio: artifact/kerno/index.html con su <title> («Kerno Analytics · Equipos»; Jugadores, sin sufijo)."""
    import re
    html = (FUENTE / "index.html").read_text(encoding="utf-8")
    titulo = "Kerno Analytics" if sitio == "jugadores" else f"Kerno Analytics · {NOMBRES[sitio]}"
    html, n = re.subn(r"<title>[^<]*</title>", f"<title>{titulo}</title>", html, count=1)
    if n != 1:
        raise ValueError("artifact/kerno/index.html sin <title>")
    dest = Path(salida) / "paginas" / sitio / "index.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html, encoding="utf-8")
    return dest


def completo(lotes: list[Path], salida: Path, parche: Path | None = None, carpeta: Path = MANIFIESTOS) -> dict:
    """Republicación completa de los tres sitios (p. ej. tras añadir una liga: cambian todas las temporadas).

    * Datos: la unión de los lotes de `artifact/empaquetar.py` (sin borrados `null`, sin páginas `.html` ni código
      `.js`: las copias de artifact/atlas y artifact/quintetos son anteriores a las de artifact/kerno).
    * Páginas, código y datos v4.1/v4.2: todo `artifact/kerno/` salvo la página propia de cada sitio, `sitio.json`,
      `sitios/`, `kerno/` (marca, no cambia) y README. Un `.json` cuyo `.json.gz.txt` está en algún manifiesto se
      comprime aquí (gzip en base64).
    * `parche` (publicacion/lote0.json del botón, opcional) va el último y manda.
    Reparte con `repartir` (lotes por sitio y sitios.json) y escribe la página de cada sitio en `paginas/<sitio>/`."""
    import base64
    import gzip
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    man = manifiestos(carpeta)
    en_alguno = set().union(*(m["ficheros"] for m in man.values()))
    total: dict[str, str] = {}
    for f in lotes:
        for k, v in json.loads(Path(f).read_text(encoding="utf-8")).items():
            if v is None or k.endswith((".html", ".js")):
                continue
            total[k] = v
    comp = salida / "comprimidos"
    comp.mkdir(exist_ok=True)
    for f in sorted(FUENTE.rglob("*")):
        rel = f.relative_to(FUENTE).as_posix()
        if not f.is_file() or rel in NO_FUENTE or rel.startswith(("sitios/", "kerno/")):
            continue
        total[rel] = str(f)
        if rel.endswith(".json") and rel + ".gz.txt" in en_alguno:
            g = comp / (rel.replace("/", "__") + ".gz.txt")
            g.write_bytes(base64.b64encode(gzip.compress(f.read_bytes(), 9, mtime=0)))
            total[rel + ".gz.txt"] = str(g)
    if parche and Path(parche).exists():
        total.update({k: v for k, v in json.loads(Path(parche).read_text(encoding="utf-8")).items() if v is not None})
    (salida / "lote_completo.json").write_text(json.dumps(total, ensure_ascii=False, indent=0), encoding="utf-8")
    r = repartir(total, salida, carpeta)
    for s in SITIOS:
        r["sitios"][s]["pagina"] = str(pagina(s, salida))
    (salida / "sitios.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    return r


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m bbactualiza.sitios",
                                 description="reparte una publicación entre los tres artifacts de Kerno")
    ap.add_argument("--publicacion", default=str(RAIZ / "publicacion"),
                    help="carpeta del botón (lee lote0.json) o, con --completo, carpeta de salida")
    ap.add_argument("--completo", nargs="*", default=None, metavar="LOTE",
                    help="republicación completa: lotes de artifact/empaquetar.py (lote*.json)")
    ap.add_argument("--parche", default=None, help="con --completo: lote0.json del botón, que va el último")
    a = ap.parse_args(argv)
    pub = Path(a.publicacion)
    if a.completo is not None:
        r = completo([Path(x) for x in a.completo], pub, Path(a.parche) if a.parche else None)
    else:
        r = repartir(json.loads((pub / "lote0.json").read_text(encoding="utf-8")), pub)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
