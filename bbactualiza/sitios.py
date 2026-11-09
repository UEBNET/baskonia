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


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m bbactualiza.sitios",
                                 description="reparte publicacion/lote0.json entre los tres artifacts")
    ap.add_argument("--publicacion", default=str(RAIZ / "publicacion"))
    a = ap.parse_args(argv)
    pub = Path(a.publicacion)
    r = repartir(json.loads((pub / "lote0.json").read_text(encoding="utf-8")), pub)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
