"""Capa visual del artículo (sistema de marca Cerno v1.0): tokens, CSS de impresión A4, componentes y gráficos SVG
(punto + rango, protagonista en Ink, contexto en Graphite, banda de incertidumbre Steel; sin 3D, radar ni doble eje)."""
from __future__ import annotations

import base64
import html as _h
from pathlib import Path

REC = Path(__file__).resolve().parent / "recursos"
INK, PAPER, INDEX = "#12161B", "#F3F0E8", "#F2CC2F"
G = {800: "#262C33", 700: "#3B434C", 600: "#545D67", 500: "#737B84", 400: "#9AA0A6", 300: "#C2C3BF",
     200: "#DAD7CF", 100: "#E8E5DD"}
STEEL, STEEL700, CLAY, TEAL = "#2A6FA8", "#1F4F78", "#C4552E", "#1E9670"
BANDA = "rgba(42,111,168,0.18)"


def fuentes_css(ruta: str = "fonts") -> str:
    return f"""
@font-face {{ font-family: 'Mona Sans'; src: url('{ruta}/MonaSans-Variable.woff2') format('woff2');
  font-weight: 200 900; font-stretch: 75% 125%; font-style: normal; }}
@font-face {{ font-family: 'Mona Sans'; src: url('{ruta}/MonaSans-Italic-Variable.woff2') format('woff2');
  font-weight: 200 900; font-stretch: 75% 125%; font-style: italic; }}
@font-face {{ font-family: 'Newsreader'; src: url('{ruta}/Newsreader-Variable.woff2') format('woff2');
  font-weight: 200 800; font-style: normal; }}
@font-face {{ font-family: 'Geist Mono'; src: url('{ruta}/GeistMono-Variable.woff2') format('woff2');
  font-weight: 100 900; }}
"""


def logo(nombre: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode((REC / f"logo_{nombre}.svg").read_bytes()).decode()


CSS = f"""
@page {{ size: A4; margin: 24mm 18mm 22mm 18mm; }}
@page cover {{ margin: 0; }}
html {{ font-family: 'Mona Sans'; font-size: 9.5pt; line-height: 14pt; color: {INK}; }}
body {{ margin: 0; }}
.portada {{ page: cover; width: 210mm; height: 297mm; background: {INK}; color: {PAPER}; position: relative;
  break-after: page; overflow: hidden; }}
.portada .logo {{ position: absolute; left: 18mm; top: 18mm; width: 52mm; }}
.portada .ceja {{ position: absolute; left: 18mm; top: 92mm; }}
.portada h1 {{ position: absolute; left: 18mm; right: 22mm; top: 102mm; margin: 0; font-weight: 620;
  font-size: 34pt; line-height: 36pt; letter-spacing: -0.03em; }}
.portada .sub {{ position: absolute; left: 18mm; right: 30mm; top: 178mm; font-family: 'Newsreader'; font-size: 13pt;
  line-height: 18pt; color: {G[300]}; }}
.portada .firma {{ position: absolute; right: 18mm; bottom: 26mm; text-align: right; }}
.portada .escala {{ position: absolute; left: 18mm; bottom: 18mm; }}
.contra {{ page: cover; width: 210mm; height: 297mm; background: {INK}; color: {PAPER}; position: relative;
  break-before: page; }}
.contra img {{ position: absolute; left: 50%; top: 40%; width: 46mm; transform: translate(-50%, -50%); }}
.contra .claim {{ position: absolute; width: 100%; top: 58%; text-align: center; font-weight: 620; font-size: 20pt; }}
.contra .fine {{ position: absolute; width: 100%; bottom: 20mm; text-align: center; }}
.ceja, .etq, th {{ font-family: 'Geist Mono'; font-weight: 500; font-size: 6.6pt; letter-spacing: .08em;
  text-transform: uppercase; }}
.portada .ceja, .contra .fine, .portada .firma {{ color: {G[300]}; }}
.sub-index {{ background: linear-gradient(transparent 12%, {INDEX} 12%, {INDEX} 92%, transparent 92%);
  box-decoration-break: clone; -webkit-box-decoration-break: clone; color: {INK}; padding: 0 2pt; }}
section.sec {{ break-before: page; }}
.sec-cab {{ border-top: 1.2pt solid {INK}; padding-top: 5pt; display: flex; justify-content: space-between;
  align-items: flex-start; margin-bottom: 8pt; }}
.sec-cab .ceja {{ color: {G[600]}; }}
.sec-cab .num {{ font-weight: 250; font-size: 46pt; line-height: 40pt; color: {G[200]}; }}
h2 {{ font-weight: 620; font-size: 21pt; line-height: 23pt; letter-spacing: -0.022em; margin: 2pt 0 8pt;
  break-after: avoid; }}
h3 {{ font-weight: 620; font-size: 11.5pt; line-height: 14pt; margin: 12pt 0 4pt; break-after: avoid; }}
.entradilla {{ font-family: 'Newsreader'; font-size: 12.5pt; line-height: 16.5pt; color: {G[700]};
  margin: 0 0 10pt; }}
p {{ margin: 0 0 6pt; }} ul, ol {{ margin: 0 0 6pt 12pt; padding: 0; }} li {{ margin-bottom: 2pt; }}
.mono, .num-c {{ font-family: 'Geist Mono'; font-variant-numeric: tabular-nums; }}
table {{ width: 100%; border-collapse: collapse; margin: 4pt 0 10pt; font-size: 8.3pt; line-height: 11pt;
  break-inside: avoid; }}
th {{ text-align: left; color: {G[600]}; border-bottom: 0.9pt solid {INK}; padding: 3pt 4pt; }}
td {{ border-bottom: 0.5pt solid {G[300]}; padding: 2.6pt 4pt; vertical-align: top; }}
td.r, th.r {{ text-align: right; font-family: 'Geist Mono'; white-space: nowrap; }}
tr.dest td {{ background: rgba(242,204,47,0.28); }}
.tcap {{ font-weight: 620; font-size: 9pt; margin: 8pt 0 1pt; break-after: avoid; }}
.tsub {{ font-family: 'Geist Mono'; font-size: 6.6pt; letter-spacing: .06em; text-transform: uppercase;
  color: {G[600]}; margin-bottom: 2pt; break-after: avoid; }}
figure {{ margin: 6pt 0 10pt; break-inside: avoid; }}
figcaption {{ font-family: 'Geist Mono'; font-size: 6.4pt; letter-spacing: .04em; color: {G[600]}; margin-top: 2pt; }}
.tarjetas {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10pt; margin: 6pt 0 10pt; }}
.tarjeta {{ border-top: 0.9pt solid {INK}; padding-top: 4pt; break-inside: avoid; }}
.tarjeta .etq {{ color: {G[600]}; }} .tarjeta .cifra {{ font-weight: 620; font-size: 17pt; line-height: 20pt; }}
.tarjeta .rango {{ font-family: 'Geist Mono'; font-size: 7.4pt; color: {G[600]}; }}
.tarjeta p {{ font-size: 8.4pt; line-height: 11.5pt; color: {G[700]}; margin: 2pt 0 0; }}
.indice-linea {{ border-left: 2pt solid {INK}; padding-left: 8pt; margin: 6pt 0 10pt; break-inside: avoid; }}
.llamada {{ background: {INK}; color: {PAPER}; padding: 9pt 11pt; margin: 8pt 0 10pt; break-inside: avoid; }}
.llamada .etq {{ color: {INDEX}; border: 0.6pt solid {INDEX}; padding: 1pt 4pt; display: inline-block;
  margin-bottom: 4pt; }}
.ev {{ font-family: 'Geist Mono'; font-size: 6.2pt; letter-spacing: .06em; padding: 0 3pt; margin-right: 3pt;
  border: 0.6pt solid; display: inline-block; line-height: 9pt; vertical-align: 1pt; }}
.ev.dato {{ border-color: {STEEL}; color: {STEEL700}; }} .ev.lectura {{ border-color: {G[500]}; color: {G[700]}; }}
.ev.hipotesis {{ border-color: {G[400]}; border-style: dashed; color: {G[700]}; }}
.indice td {{ font-size: 9.5pt; padding: 4pt 4pt; }} .indice td.n {{ font-family: 'Geist Mono'; width: 18pt; }}
.indice td.t {{ font-weight: 620; }}
.eq {{ font-family: 'Geist Mono'; font-size: 7.8pt; line-height: 11pt; background: {G[100]}; padding: 5pt 7pt;
  margin: 4pt 0 8pt; white-space: pre-wrap; break-inside: avoid; }}
.dos {{ columns: 2; column-gap: 16pt; }}
.refs li {{ font-size: 8pt; line-height: 11pt; }}
"""


def esc(x) -> str:
    return _h.escape(str(x))


def n(x, d: int = 2, signo: bool = False, pct: bool = False) -> str:
    """Cifra con coma decimal (y espacio antes de %)."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "–"
    if x != x:
        return "–"
    if pct:
        x *= 100
    s = f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if signo and x > 0:
        s = "+" + s
    return s + (" %" if pct else "")


def rango(c, lo, hi, d: int = 2, pct: bool = False, signo: bool = False) -> str:
    return f'{n(c, d, signo, pct)} <span class="mono">[{n(lo, d, signo, pct)}, {n(hi, d, signo, pct)}]</span>'


def tabla(cab: list[str], filas: list[list], num: set[int] | None = None, dest: set[int] | None = None) -> str:
    num, dest = num or set(), dest or set()
    th = "".join(f'<th class="{"r" if i in num else ""}">{c}</th>' for i, c in enumerate(cab))
    tr = "".join(f'<tr class="{"dest" if k in dest else ""}">' +
                 "".join(f'<td class="{"r" if i in num else ""}">{v}</td>' for i, v in enumerate(f)) + "</tr>"
                 for k, f in enumerate(filas))
    return f"<table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>"


def ev(tipo: str) -> str:
    return f'<span class="ev {tipo.lower()}">{ {"dato": "DATO", "lectura": "LECTURA", "hipotesis": "HIPÓTESIS"}[tipo] }</span>'


# ------------------------------------------------------------------------------------------ gráficos SVG
def grafico_rangos(filas: list[dict], titulo: str, subtitulo: str, fuente: str, ancho: float = 480,
                   cero: float | None = 0.0, margen: float | None = None, fmt=lambda v: n(v, 2)) -> str:
    """Punto + rango por fila (dict: etiqueta, c, lo, hi, protagonista). Eje desde los datos, con línea de
    referencia en `cero` y, si se da, la de `margen` (no inferioridad) en discontinua."""
    alto_f = 15
    izq, der, arr = 128, 18, 18
    h = arr + alto_f * len(filas) + 26
    vals = [v for f in filas for v in (f["lo"], f["hi"], f["c"]) if v == v] + \
        ([cero] if cero is not None else []) + ([margen] if margen is not None else [])
    lo_, hi_ = min(vals), max(vals)
    pad = 0.08 * (hi_ - lo_ or 1)
    lo_, hi_ = lo_ - pad, hi_ + pad
    X = lambda v: izq + (ancho - izq - der) * (v - lo_) / (hi_ - lo_)  # noqa: E731
    out = [f'<svg width="100%" viewBox="0 0 {ancho} {h}" xmlns="http://www.w3.org/2000/svg" '
           f'font-family="Geist Mono" font-size="7">']
    for t in _ticks(lo_, hi_):
        out.append(f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{arr - 6}" y2="{h - 20}" stroke="{G[200]}" '
                   f'stroke-width="0.5"/><text x="{X(t):.1f}" y="{h - 9}" fill="{G[600]}" text-anchor="middle">'
                   f'{esc(fmt(t))}</text>')
    if cero is not None:
        out.append(f'<line x1="{X(cero):.1f}" x2="{X(cero):.1f}" y1="{arr - 6}" y2="{h - 20}" stroke="{G[600]}" '
                   f'stroke-width="0.8"/>')
    if margen is not None:
        out.append(f'<line x1="{X(margen):.1f}" x2="{X(margen):.1f}" y1="{arr - 6}" y2="{h - 20}" stroke="{INK}" '
                   f'stroke-width="0.8" stroke-dasharray="2 2"/>')
    for k, f in enumerate(filas):
        y = arr + alto_f * k + alto_f / 2
        col = INK if f.get("protagonista") else G[600]
        out.append(f'<text x="{izq - 6}" y="{y + 2.5:.1f}" text-anchor="end" fill="{INK}" font-family="Mona Sans" '
                   f'font-size="7.6" font-weight="{620 if f.get("protagonista") else 400}">{esc(f["etiqueta"])}</text>')
        if f["lo"] == f["lo"] and f["hi"] == f["hi"]:
            out.append(f'<rect x="{X(f["lo"]):.1f}" y="{y - 3.5:.1f}" width="{max(X(f["hi"]) - X(f["lo"]), 0.8):.1f}" '
                       f'height="7" fill="{BANDA}"/>')
        out.append(f'<rect x="{X(f["c"]) - 1:.1f}" y="{y - 4.5:.1f}" width="2" height="9" fill="{col}"/>')
        out.append(f'<text x="{ancho - 2}" y="{y + 2.5:.1f}" text-anchor="end" fill="{G[600]}">'
                   f'{esc(f.get("texto", ""))}</text>')
    out.append("</svg>")
    return (f'<figure><div class="tcap">{titulo}</div><div class="tsub">{subtitulo}</div>{"".join(out)}'
            f'<figcaption>{fuente}</figcaption></figure>')


def _ticks(lo: float, hi: float, n_: int = 5) -> list[float]:
    import math
    paso = (hi - lo) / n_
    e = 10 ** math.floor(math.log10(paso)) if paso > 0 else 1
    paso = min((m * e for m in (1, 2, 2.5, 5, 10)), key=lambda p: abs(p - paso))
    t0 = math.ceil(lo / paso) * paso
    return [round(t0 + i * paso, 10) for i in range(int((hi - t0) / paso) + 1)]


def escala_svg(pos: int = 8, color_lectura: str = INDEX, base: str = G[300]) -> str:
    marcas = []
    for k in range(17):
        h = 12 if k == pos else (8 if k % 5 == 0 else 5)
        marcas.append(f'<rect x="{9 * k}" y="{12 - h}" width="{1.8 if k == pos else 0.8}" height="{h}" '
                      f'fill="{color_lectura if k == pos else base}"/>')
    return f'<svg width="{9 * 17}" height="12">{"".join(marcas)}</svg>'
