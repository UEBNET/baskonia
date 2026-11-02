"""PDF A4 de marca Cerno (receta del sistema de marca v1.0, §8.1): HTML + CSS impreso con Chromium (Playwright de Node,
preinstalado) y una capa base de página completa con el fondo Paper a sangre, la cabecera de confidencialidad con la
sección de cada página y la escala del pie con la posición de la página. Dos pasadas para el índice.

    construir_pdf(html: Path, salida: Path, titulo: str) -> dict
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

INK, PAPER, G600, G300 = "#12161B", "#F3F0E8", "#545D67", "#C2C3BF"
RE_SECCION = re.compile(r"Sección\s+(\d{2})\s*·\s*([^\n]+)", re.I)

_JS = r"""
const { chromium } = require('playwright');
(async () => {
  const [entrada, salida] = process.argv.slice(2);
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.goto('file://' + entrada, { waitUntil: 'networkidle' });
  await p.evaluate(async () => { await document.fonts.ready; });
  await p.pdf({ path: salida, printBackground: true, preferCSSPageSize: true });
  const fuentes = await p.evaluate(() => [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family));
  console.log(JSON.stringify({ fuentes: [...new Set(fuentes)] }));
  await b.close();
})();
"""


def _chromium_pdf(html: Path, pdf: Path) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(_JS)
        js = f.name
    r = subprocess.run(["node", js, str(html.resolve()), str(pdf.resolve())], capture_output=True, text=True,
                       timeout=600)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-2000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


def secciones_por_pagina(pdf: Path) -> list[tuple[str, str] | None]:
    """(número, nombre) de la sección vigente en cada página (marcador «Sección NN · Nombre» de la ceja)."""
    from pypdf import PdfReader
    actual, out = None, []
    for pg in PdfReader(str(pdf)).pages:
        m = RE_SECCION.search(pg.extract_text() or "")
        if m:
            actual = (m.group(1), m.group(2).strip())
        out.append(actual)
    return out


def _escala(pos: int, n: int = 17) -> str:
    marcas = []
    for k in range(n):
        x = 6 * k
        mayor = k % 5 == 0
        h = 9 if k == pos else (6 if mayor else 4)
        w = 1.4 if k == pos else 0.6
        marcas.append(f'<rect x="{x}" y="{10 - h}" width="{w}" height="{h}" fill="{INK if k == pos else G600}"/>')
    return f'<svg width="{6 * n}" height="10" viewBox="0 0 {6 * n} 10">{"".join(marcas)}</svg>'


def _base_html(n_pag: int, portadas: set[int], titulo: str, secciones: list, fuentes_css: str) -> str:
    pags = []
    for i in range(n_pag):
        if i in portadas:
            pags.append('<div class="pg vacia"></div>')
            continue
        s = secciones[i]
        der = f"{s[0]} · {s[1].upper()}" if s else ""
        pos = round(16 * i / max(n_pag - 1, 1))
        pags.append(f'<div class="pg"><div class="cab"><span>CERNO ANALYTICS — {titulo.upper()} · CONFIDENCIAL</span>'
                    f'<span>{der}</span></div><div class="pie">{_escala(pos)}<span>{i + 1:02d} / {n_pag:02d}</span>'
                    f'</div></div>')
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{fuentes_css}
@page {{ size: A4; margin: 0 }}
html, body {{ margin: 0; padding: 0; }}
.pg {{ width: 210mm; height: 297mm; background: {PAPER}; position: relative; break-after: page; overflow: hidden; }}
.pg.vacia {{ background: transparent; }}
.cab, .pie {{ position: absolute; left: 18mm; right: 18mm; display: flex; justify-content: space-between;
  align-items: center; font-family: 'Geist Mono'; font-weight: 500; font-size: 6.4pt; letter-spacing: .08em;
  color: {G600}; text-transform: uppercase; }}
.cab {{ top: 11mm; }} .pie {{ bottom: 11mm; }}
</style></head><body>{''.join(pags)}</body></html>"""


def construir_pdf(html: Path, salida: Path, titulo: str, fuentes_css: str, portadas: set[int] | None = None,
                  rellenar_indice=None) -> dict:
    """Dos pasadas: render → páginas de inicio de cada sección → `rellenar_indice(mapa)` reescribe el HTML →
    re-render (se comprueba que no cambia) → capa base Paper con cabecera y escala → fusión con pypdf."""
    from pypdf import PdfReader, PdfWriter
    html, salida = Path(html), Path(salida)
    tmp = salida.with_suffix(".cuerpo.pdf")
    info = _chromium_pdf(html, tmp)
    mapa = {}
    for i, s in enumerate(secciones_por_pagina(tmp)):
        if s and s[0] not in mapa:
            mapa[s[0]] = i + 1
    if rellenar_indice is not None:
        rellenar_indice(mapa)
        info = _chromium_pdf(html, tmp)
        mapa2 = {}
        for i, s in enumerate(secciones_por_pagina(tmp)):
            if s and s[0] not in mapa2:
                mapa2[s[0]] = i + 1
        if mapa2 != mapa:                     # el índice cambió la paginación: una tercera pasada
            rellenar_indice(mapa2)
            info = _chromium_pdf(html, tmp)
            mapa = mapa2
    cuerpo = PdfReader(str(tmp))
    n = len(cuerpo.pages)
    port = set(portadas or {0, n - 1})
    secs = secciones_por_pagina(tmp)
    base_html = html.with_name("_base.html")
    base_html.write_text(_base_html(n, port, titulo, secs, fuentes_css), encoding="utf-8")
    base_pdf = salida.with_suffix(".base.pdf")
    _chromium_pdf(base_html, base_pdf)
    base = PdfReader(str(base_pdf))
    w = PdfWriter()
    for i in range(n):
        pg = base.pages[i]
        pg.merge_page(cuerpo.pages[i])
        w.add_page(pg)
    w.add_metadata({"/Title": titulo, "/Author": "Cerno Analytics", "/Subject": "Confidencial"})
    with open(salida, "wb") as f:
        w.write(f)
    for p in (tmp, base_pdf, base_html):
        p.unlink(missing_ok=True)
    return {"paginas": n, "secciones": mapa, "fuentes_cargadas": info.get("fuentes")}
