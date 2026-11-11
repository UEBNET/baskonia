"""Genera las páginas de los tres artifacts de Kerno Analytics a partir de artifact/kerno.html.

Los tres sitios (Jugadores, Equipos, Metodología) publican la misma página; sitio.json dice a cada una qué sitio es.
Sólo cambian dos cosas:
  - el <title> de cada artifact;
  - el botón «Actualizar 2026-27» (CSS, botón, panel y script kerno-upd-js) sólo existe en Jugadores, el único artifact
    con la capacidad mcp (conector Claude Code Remote) y el único que republica la actualización de la temporada.

    python3 artifact/kerno_sitios.py            # escribe artifact/kerno-equipos.html y artifact/kerno-metodologia.html
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
FUENTE = RAIZ / "kerno.html"  # Jugadores (https://claude.ai/artifact/A7rufkL84rvRFcUBFBxFbC), con el botón
SITIOS = {
    "equipos": ("Kerno Analytics · Equipos", RAIZ / "kerno-equipos.html"),  # https://claude.ai/artifact/SXFgQ6CpytxT3ZZupcEFcj
    "metodologia": ("Kerno Analytics · Metodología", RAIZ / "kerno-metodologia.html"),  # https://claude.ai/artifact/T83MBGZk5untACmegadfNn
}
# trozos del botón «Actualizar 2026-27»: (patrón, cuántas veces debe aparecer)
BOTON = [
    (r"/\* botón «Actualizar 2026-27».*?#updPop \.upd-ult:empty \{ display: none; \}\n", 1),  # CSS
    (r"[ \t]*<div class=\"ctx-f\"><span class=\"label\">Datos 2026-27</span><button[^\n]*id=\"updBtn\"[^\n]*\n", 1),  # botón
    (r"[ \t]*<div class=\"pop\" id=\"updPop\".*?\n(?=[ \t]*<div class=\"pop\" id=\"setPop\")", 1),  # panel
    (r"<script id=\"kerno-upd-js\">.*?</script>\n", 1),  # script
]


def sin_boton(html: str) -> str:
    for pat, n in BOTON:
        html, k = re.subn(pat, "", html, flags=re.S)
        if k != n:
            raise SystemExit(f"kerno_sitios: el patrón del botón aparece {k} veces (se esperaban {n}): {pat[:60]}")
    if "updBtn" in html or "kerno-upd-js" in html:
        raise SystemExit("kerno_sitios: quedan restos del botón")
    return html


def main() -> None:
    fuente = FUENTE.read_text(encoding="utf-8")
    if fuente.count("<title>Kerno Analytics</title>") != 1:
        raise SystemExit("kerno_sitios: artifact/kerno.html debe llevar <title>Kerno Analytics</title>")
    base = sin_boton(fuente)
    for titulo, salida in SITIOS.values():
        salida.write_text(base.replace("<title>Kerno Analytics</title>", f"<title>{titulo}</title>", 1), encoding="utf-8")
        print(f"{salida.relative_to(RAIZ.parent)} · {titulo}")


if __name__ == "__main__":
    main()
