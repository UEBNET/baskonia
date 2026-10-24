"""Artículo (fase 9): el marcado mínimo de la Parte II se traduce bien a HTML (KaTeX) y a LaTeX, sin imprimir el PDF."""
import re

from bbfit import articulo as A

PERMITIDOS = set("áéíóúÁÉÍÓÚñÑüÜ«»¡¿çÇàèòìùâêôãõčćšžğşŞİıöÖäÄåøØłńśźżČĆŠŽ’ºª")


def test_html_en_linea_formula_negrita_codigo_y_marcador():
    h = A.html_en_linea(r"El **libro** $V_k = \sum_i m_i s_{ik}$ en `bbfit/reemplazo.py` [[F8: MAE]] <x>")
    assert '<span class="tex">V_k = \\sum_i m_i s_{ik}</span>' in h
    assert "<b>libro</b>" in h and "<code>bbfit/reemplazo.py</code>" in h
    assert '<span class="f8">[[F8: MAE]]</span>' in h
    assert "&lt;x&gt;" in h


def test_tex_en_linea_escapa_y_respeta_las_formulas():
    t = A.tex_en_linea(r"MIN% ≥ 25 % y λ ≈ 1 en `usg_pct` & $\mathrm{MIN\%}_{ig} \ge 0{,}25$ [[F8: rol_esperado]]")
    assert r"MIN\%" in t and r"\ensuremath{\geq}" in t and r"\ensuremath{\lambda}" in t and r"\ensuremath{\approx}" in t
    assert r"\texttt{usg\_pct}" in t and r"\&" in t
    assert r"$\mathrm{MIN\%}_{ig} \ge 0{,}25$" in t        # la fórmula no se toca
    assert r"\fochopendiente{rol\_esperado}" in t


def test_latex_completo_sin_caracteres_sin_traducir_y_entornos_equilibrados():
    bloques = A.contenido()
    tex = A.latex(bloques, {})
    raros = {ch for ch in tex if ord(ch) > 127 and ch not in PERMITIDOS}
    assert not raros, raros
    for env in ("aligned", "cases", "itemize", "enumerate", "tabular", "center", "document"):
        assert tex.count(rf"\begin{{{env}}}") == tex.count(rf"\end{{{env}}}"), env
    # ninguna fórmula lleva caracteres no ASCII (pdflatex no los compone en modo matemático)
    assert not [s for s in re.findall(r"\$[^$]*\$", tex) if any(ord(c) > 127 for c in s)]


def test_html_bloques_numera_tablas_y_omite_figuras_ausentes():
    bloques = A.contenido()
    h = A.html_bloques(bloques, {})
    n_tab = sum(1 for b in bloques if b[0] == "tab")
    assert h.count('<p class="tcap"><b>Tabla II.') == n_tab
    assert "<figure>" not in h                    # sin ficheros de figura no se emite ninguna
    assert h.count('class="texd"') == sum(1 for b in bloques if b[0] == "eq")


def test_placeholders_f8_se_listan():
    ph = A.placeholders([("p", "a [[F8: uno]] b"), ("tab", "k", "pie", ["c"], [["[[F8: dos]]"]], set())])
    assert ph == ["[[F8: dos]]", "[[F8: uno]]"]
