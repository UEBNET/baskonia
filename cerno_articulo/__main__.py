"""Artículo científico de Cerno Analytics (versión 3.2): datos, normalización, vara de destino, estilos y simulador.

    python -m cerno_articulo [--salida docs/articulo]

Sustituye al artículo anterior (estilos de juego en ocho ligas, docs/articulo/estilos_de_juego_baskonia.pdf). Las
cifras se leen de los ficheros de resultados (cerno_articulo.datos); lo que aún no existe aparece como pendiente.
"""
from __future__ import annotations

import argparse
import shutil
from datetime import date
from pathlib import Path

from . import contenido as CT
from . import datos as DT
from . import estilo as E
from .pdf import construir_pdf

TITULO = "La lectura entre ligas · v3.2"
NOMBRE = "cerno_lectura_entre_ligas_v3_2.pdf"

REFERENCIAS = [
    "Jiang, Z. et al. (2017). Variational Deep Embedding: an unsupervised and generative approach to clustering. IJCAI.",
    "Sohn, K., Lee, H. y Yan, X. (2015). Learning structured output representation using deep conditional generative models. NeurIPS.",
    "Perez, E. et al. (2018). FiLM: visual reasoning with a general conditioning layer. AAAI.",
    "Lakshminarayanan, B., Pritzel, A. y Blundell, C. (2017). Simple and scalable predictive uncertainty estimation using deep ensembles. NeurIPS.",
    "Kim, Y. et al. (2018). Semi-amortized variational autoencoders. ICML.",
    "Lange, K., Little, R. y Taylor, J. (1989). Robust statistical modeling using the t distribution. JASA.",
    "Angelopoulos, A. y Bates, S. (2023). Conformal prediction: a gentle introduction. Foundations and Trends in ML.",
    "Romano, Y., Patterson, E. y Candès, E. (2019). Conformalized quantile regression. NeurIPS.",
    "Gneiting, T. y Raftery, A. (2007). Strictly proper scoring rules, prediction, and estimation. JASA.",
    "Wellek, S. (2010). Testing statistical hypotheses of equivalence and noninferiority. CRC Press.",
    "Hastie, T., Tibshirani, R. y Friedman, J. (2009). The elements of statistical learning (regla de 1 error típico). Springer.",
    "Sill, J. (2010). Improved NBA adjusted +/- using regularization and out-of-sample testing. MIT Sloan Sports Analytics Conference.",
    "Plackett, R. (1975). The analysis of permutations. Applied Statistics.",
    "Clopper, C. y Pearson, E. (1934). The use of confidence or fiducial limits illustrated in the case of the binomial. Biometrika.",
]


def html_articulo(R: dict, fuentes: str) -> str:
    secs = CT.todas(R)
    indice = "".join(f'<tr><td class="n">{k:02d}</td><td class="t">{E.esc(t)}</td><td class="r">__{k:02d}__</td></tr>'
                     for k, (nom, t, _) in enumerate(secs, 1))
    cuerpo = "".join(CT.seccion(k, nom, t, _entradilla(nom), c) for k, (nom, t, c) in enumerate(secs, 1))
    refs = "".join(f"<li>{E.esc(r)}</li>" for r in REFERENCIAS)
    hoy = date.today().strftime("%d-%m-%Y")
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>{TITULO}</title>
<style>{fuentes}{E.CSS}</style></head><body>
<div class="portada"><img class="logo" src="{E.logo('hn')}" alt="Cerno">
<div class="ceja">Artículo científico · 2026 · Confidencial</div>
<h1>Traducir el rendimiento entre 20 ligas con su <span class="sub-index">incertidumbre</span> declarada</h1>
<div class="sub">Normalización v3.2 y simulador de encaje v3.3: datos, métodos, exámenes fuera de muestra y decisiones
tomadas con reglas fijadas de antemano.</div>
<div class="firma ceja">Preparado por Cerno Analytics<br>{hoy}</div><div class="escala">{E.escala_svg()}</div></div>
<section><div class="sec-cab"><div><div class="ceja">Índice</div><h2>Contenido</h2></div></div>
<table class="indice">{indice}</table>
<p class="entradilla">Versión 3.2 del artículo científico de Cerno Analytics. Sustituye al artículo de estilos de juego
en ocho ligas y documenta todas las versiones de la normalización hasta la v3.2 y del simulador hasta la v3.3.</p></section>
{cuerpo}
<section class="sec"><div class="sec-cab"><div><div class="ceja">Referencias</div><h2>Referencias</h2></div></div>
<ol class="refs">{refs}</ol></section>
<div class="contra"><img src="{E.logo('vn')}" alt="Cerno"><div class="claim">Make the right read.</div>
<div class="fine ceja">Cerno Analytics · Documento confidencial</div></div></body></html>"""


ENTRADILLAS = {
    "Resumen": "Qué cambia en la v3.2, cómo se decidió y cuánto sabemos.",
    "Datos": "Veinte competiciones medidas con el mismo analizador de jugada a jugada.",
    "Normalización": "De la recta por liga a la mezcla de dos modelos que fallan distinto.",
    "Método v3.2": "Las reglas se fijaron antes de ver los resultados.",
    "Resultados v3.2": "Qué piezas se quedan, cuáles se van y con qué evidencia.",
    "Vara de destino": "La liga de destino a 0, sin tocar el centro de nadie.",
    "Estilos de juego": "Cómo juega un equipo, separado de cuánto rinde.",
    "Simulador": "Minutos, rol y producción de un fichaje en su club de destino.",
    "Simulador v3.2": "Examen sin fuga, reglas de no inferioridad y rangos recalibrados.",
    "Simulador v3.3": "Minutos con un segundo modelo y producción acoplada al rol.",
    "Evaluaciones": "Ideas que no se aplican, medidas con el mismo rigor.",
    "Límites": "Lo que podría cambiar nuestra lectura.",
    "Reproducibilidad": "Órdenes, configuraciones y semillas.",
}


def _entradilla(nom: str) -> str:
    return ENTRADILLAS.get(nom, "")


def main(salida: str = "docs/articulo") -> Path:
    raiz = DT.RAIZ
    trabajo = raiz / "experimentos" / "articulo_v32"
    if trabajo.exists():
        shutil.rmtree(trabajo)
    shutil.copytree(Path(__file__).parent / "recursos" / "fonts", trabajo / "fonts")
    R = DT.cargar()
    h = trabajo / "articulo.html"
    plantilla = html_articulo(R, E.fuentes_css("fonts"))
    h.write_text(plantilla, encoding="utf-8")

    def rellenar(mapa: dict) -> None:            # siempre desde la plantilla (las pasadas pueden repetirse)
        t = plantilla
        for k in range(1, 40):
            t = t.replace(f"__{k:02d}__", f"{mapa.get(f'{k:02d}', 0):02d}")
        h.write_text(t, encoding="utf-8")

    out = raiz / salida
    out.mkdir(parents=True, exist_ok=True)
    pdf = out / NOMBRE
    info = construir_pdf(h, pdf, TITULO, E.fuentes_css(str(trabajo / "fonts")), rellenar_indice=rellenar)
    print(info)
    return pdf


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="cerno_articulo")
    ap.add_argument("--salida", default="docs/articulo")
    main(ap.parse_args().salida)
