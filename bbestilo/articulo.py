"""Artículo científico en PDF con los resultados de los estilos de juego (v2, VaDE).

    python -m bbestilo articulo [--fuentes DIR]  →  docs/articulo/estilos_de_juego_baskonia.pdf
                                                     (y copia en artifact/articulo/ para el Atlas)

Genera las figuras (figuras.py), compone el artículo en HTML con las cifras leídas de
data/modelos/estilos/ y lo imprime a PDF con Chromium sin interfaz. Si se pasa una carpeta de fuentes
(woff/ttf de Source Serif 4, IBM Plex Sans/Mono y Barlow Condensed) se incrustan; si no, se usan las del sistema.
"""
from __future__ import annotations

import html
import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from . import figuras
from .entrenar import HIPER

LIGAS = figuras.LIGAS
SALIDA = C.RAIZ / "docs" / "articulo"
NOMBRE_PDF = "estilos_de_juego_baskonia.pdf"


def n(x, d=2, signo=False):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "–"
    s = f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("+" + s) if signo and x > 0 else s


def pc(x, d=0):
    return "–" if x is None else n(100 * x, d) + " %"


def p_txt(p):
    if p is None:
        return "–"
    return "p < 0,001" if p < 0.001 else f"p = {n(p, 3)}"


def e(s):
    return html.escape(str(s))


def tabla(cab: list[str], filas: list[list], num: set[int] | None = None, cls: str = "") -> str:
    num = num or set()
    th = "".join(f'<th class="{"r" if i in num else ""}">{c}</th>' for i, c in enumerate(cab))
    tr = "".join("<tr>" + "".join(f'<td class="{"r" if i in num else ""}">{v}</td>' for i, v in enumerate(f)) + "</tr>" for f in filas)
    return f'<table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>'


def figura(src: str, n_fig: int, pie: str, ancho: str = "100%") -> str:
    return f'<figure><img src="figuras/{src}" style="width:{ancho}"><figcaption><b>Figura {n_fig}.</b> {pie}</figcaption></figure>'


CSS = """
@page { size: A4; margin: 20mm 21mm 20mm 21mm; @bottom-center { content: counter(page); font: 8.5pt 'IBM Plex Sans', sans-serif; color: #7a6450; } }
html { font-family: 'Source Serif 4', 'DejaVu Serif', Georgia, serif; font-size: 10.2pt; line-height: 1.42; color: #24190f; }
body { margin: 0; }
h1 { font-family: 'Barlow Condensed', 'Arial Narrow', sans-serif; font-size: 25pt; line-height: 1.05; margin: 0 0 6pt; letter-spacing: .01em; color: #3a2a1c; }
h2 { font-family: 'Barlow Condensed', 'Arial Narrow', sans-serif; font-size: 15.5pt; margin: 16pt 0 5pt; color: #3a2a1c; break-after: avoid; }
h3 { font-family: 'IBM Plex Sans', sans-serif; font-size: 10.2pt; margin: 11pt 0 3pt; color: #3a2a1c; break-after: avoid; }
p { margin: 0 0 6pt; text-align: justify; hyphens: auto; }
.autores { font-family: 'IBM Plex Sans', sans-serif; font-size: 9pt; color: #6b4f38; margin-bottom: 10pt; }
.resumen { background: #f9f3eb; border-left: 3pt solid #6b4f38; padding: 8pt 11pt; margin: 8pt 0 10pt; font-size: 9.6pt; }
.resumen p { margin-bottom: 4pt; }
.clave { font-family: 'IBM Plex Sans', sans-serif; font-size: 8.5pt; color: #6b4f38; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-family: 'IBM Plex Sans', sans-serif; font-size: 8pt; break-inside: avoid; }
caption, .tcap { font-family: 'IBM Plex Sans', sans-serif; font-size: 8.4pt; text-align: left; margin: 8pt 0 2pt; color: #3a2a1c; break-after: avoid; }
th { text-align: left; border-bottom: 1pt solid #3a2a1c; padding: 3pt 5pt; font-weight: 600; background: #f9f3eb; }
td { border-bottom: .5pt solid #e3d0b8; padding: 2.6pt 5pt; vertical-align: top; }
td.r, th.r { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
figure { margin: 8pt 0 10pt; break-inside: avoid; text-align: center; }
figcaption { font-family: 'IBM Plex Sans', sans-serif; font-size: 8.2pt; text-align: left; color: #3a2a1c; margin-top: 3pt; }
.eq { font-family: 'IBM Plex Mono', monospace; font-size: 8.6pt; background: #fcf9f5; border: .5pt solid #e3d0b8; padding: 5pt 8pt; margin: 4pt 0 8pt; white-space: pre-wrap; break-inside: avoid; }
code { font-family: 'IBM Plex Mono', monospace; font-size: 8.4pt; }
ul, ol { margin: 0 0 6pt 14pt; padding: 0; } li { margin-bottom: 2.5pt; text-align: justify; }
.refs li { font-size: 8.6pt; margin-bottom: 2pt; text-align: left; }
.sw { display: inline-block; width: 7pt; height: 7pt; border-radius: 50%; margin-right: 3pt; vertical-align: 0; }
.salto { break-before: page; }
"""


def _fuentes_css(fuentes: Path | None, d: Path) -> str:
    if not fuentes or not (fuentes / "fuentes.css").exists():
        return ""
    (d / "fuentes").mkdir(exist_ok=True)
    css = (fuentes / "fuentes.css").read_text()
    for f in fuentes.glob("*.woff*"):
        shutil.copy(f, d / "fuentes" / f.name)
    import re
    return re.sub(r"url\(https://fonts\.gstatic\.com/[^)]*/([^/)]+)\)", r"url(fuentes/\1)", css)


def construir(fuentes: Path | None = None, chrome: str | None = None) -> Path:
    R = C.DIR_SALIDA
    d = SALIDA
    d.mkdir(parents=True, exist_ok=True)
    trabajo = d / "_trabajo"
    trabajo.mkdir(exist_ok=True)
    F = figuras.todas(trabajo / "figuras", fuentes)
    ev = json.loads((R / "evaluacion.json").read_text(encoding="utf-8"))
    V, I = ev["vade"], ev["idec"]
    v1p = R / "v1_12estilos" / "evaluacion.json"
    V1 = json.loads(v1p.read_text(encoding="utf-8"))["vade"] if v1p.exists() else {}
    I1 = json.loads(v1p.read_text(encoding="utf-8"))["idec"] if v1p.exists() else {}
    A = json.loads((R / "analisis.json").read_text(encoding="utf-8"))
    esc_ = json.loads((R / "escalas.json").read_text(encoding="utf-8"))
    reg = json.loads((R / "vade" / "registro.json").read_text(encoding="utf-8"))
    est = pd.read_csv(R / "vade" / "estilos.csv")
    cl = pd.read_csv(R / "vade" / "clubes.csv")
    nom = {}
    p = C.RAIZ / "config" / "estilos_v2.json"
    if p.exists():
        nom = {k: v for k, v in json.loads(p.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    nombre = lambda s: nom.get(s, {}).get("nombre", s)  # noqa: E731
    sw = lambda k: f'<span class="sw" style="background:{figuras.COL[k]}"></span>'  # noqa: E731
    from .redes import RedVaDE
    n_par = sum(t.numel() for t in RedVaDE(13, HIPER["vade"]["ocultas"], 3, C.N_ESTILOS, "completa").parameters())
    ent = cl[~cl["provisional"]]
    n_cl, n_prov = len(ent), int(cl["provisional"].sum())
    hv = HIPER["vade"]
    neu, bk, ex, enc, con, lg, bar = (A["neutralizacion"], A["baskonia"], A["exito"], A["encaje"], A["continuidad"],
                                      A["ligas"], A["barrido_k"])
    cons = reg.get("consenso") or {}
    r2 = np.array(neu["r2_club"])
    top_r2 = np.argsort(-r2)[:4]
    ed, ec = enc["d_nivel~distancia"], enc["d_cuota~distancia"]
    ea = enc["d_nivel~afinidad"]
    dist_l = lg["distancias"]
    cerca = lambda l: ", ".join([f"{LIGAS[m]} ({n(v)})" for m, v in sorted(dist_l[l].items(), key=lambda x: x[1]) if m != l][:2])  # noqa: E731

    # ---------------------------------------------------------------- tablas
    t_rasgos = tabla(["Bloque", "Rasgo", "Origen", "Transf.", "R² del nivel (clubes)"],
                     [[r.bloque, e(r.nombre), e(r.origen), {"id": "—", "raiz": "√x", "log1": "log(1+x)"}[r.transf], pc(r2[k])]
                      for k, r in enumerate(C.RASGOS)], {4})
    nl = pd.DataFrame(neu["nivel_por_liga"]).set_index("liga")
    cnt = ent.groupby("liga").size()
    t_ligas = tabla(["Liga", "Clubes-temporada (2020-26)", "Nivel medio (z)", "Desv. del nivel"],
                    [[LIGAS[l], int(cnt.get(l, 0)), n(nl.loc[l, "mean"], 2, True), n(nl.loc[l, "std"])] for l in LIGAS if l in nl.index],
                    {1, 2, 3})
    t_hiper = tabla(["Hiperparámetro", "Valor"], [
        ["Arquitectura", "13 → 64 → 32 → (μ, log σ²) ∈ ℝ³; decodificador 3 → 32 → 64 → 13; GELU (aprox. tanh)"],
        ["Capa de salida", f"{C.N_ESTILOS} neuronas; mezcla gaussiana de covarianza completa, π uniforme"],
        ["Parámetros entrenables", f"{n_par:,}".replace(",", ".")],
        ["Muestras por época", "997 clubes + 23.928 plantillas remuestreadas + 12.753 jugadores (peso 0,3)"],
        ["Remuestreo de plantilla", f"minutos × Gamma({C.K_GAMMA:g}, 1/{C.K_GAMMA:g}); {C.BOOTSTRAP_POR_CLUB} por club"],
        ["Optimizador", f"Adam, tasa {hv['lr']:g} (coseno), lote {hv['lote']}, decaimiento {hv['wd']:g}"],
        ["Épocas", f"{hv['epocas_pre']} de preentreno + {hv['epocas']} + {hv['epocas_afinado']} de ajuste fino (tasa {hv['lr_afinado']:g})"],
        ["Peso del estrés MDS", f"λ = {hv['lambda_estres']:g}"],
        ["Calentamiento de β", f"0,1 → 1 en {hv['calentamiento']} épocas"],
        ["Paso M", f"amortiguación {hv['amortiguacion']:g}; suelo de varianza {pc(hv['suelo_var'])} de la varianza media; resiembra < {pc(hv['min_cuota'])}"],
        ["Semillas", ", ".join(str(s) for s in C.SEMILLAS) + "; consenso por co-asociación y enlace medio"],
        ["Neutralización", f"regresión en [1, L, L²] por rasgo; residuo reescalado a desviación 1"],
    ])
    filas_cmp = [
        ("Estilos (neuronas de salida)", 8, 8, 12, 0), ("Nivel explicado por el estilo (η²)", V["eta2_nivel"], I["eta2_nivel"], V1.get("eta2_nivel"), 3),
        ("Estilo ligado a la liga (NMI)", V["nmi_estilo_liga"], I["nmi_estilo_liga"], V1.get("nmi_estilo_liga"), 3),
        ("Pureza de liga media de los estilos", V["pureza_liga_media"], I["pureza_liga_media"], V1.get("pureza_liga_media"), 2),
        ("Equilibrio del reparto (entropía)", V["entropia_reparto"], I["entropia_reparto"], V1.get("entropia_reparto"), 3),
        ("Seguridad media de la asignación", V["salida_max_media"], I["salida_max_media"], V1.get("salida_max_media"), 2),
        ("Silueta en el mapa 3D", V["silueta_mapa"], I["silueta_mapa"], V1.get("silueta_mapa"), 3),
        ("Silueta en los 13 rasgos", V["silueta_rasgos"], I["silueta_rasgos"], V1.get("silueta_rasgos"), 3),
        ("Estabilidad de los estilos entre semillas (ARI)", V["ari_semillas_medio"], I["ari_semillas_medio"], V1.get("ari_semillas_medio"), 2),
        ("Centralidad del modelo final (ARI con semillas)", V["ari_final_semillas_medio"], I["ari_final_semillas_medio"], V1.get("ari_final_semillas_medio"), 2),
        ("Estabilidad del mapa entre semillas (r)", V["estabilidad_mapa"], I["estabilidad_mapa"], V1.get("estabilidad_mapa"), 3),
        ("Robustez al reparto de minutos", V["robustez_reparto_minutos"], I["robustez_reparto_minutos"], V1.get("robustez_reparto_minutos"), 2),
        ("Reproducibilidad temporal (ARI)", V["ari_temporal_reserva"], I["ari_temporal_reserva"], V1.get("ari_temporal_reserva"), 2),
        ("Trustworthiness (k = 10)", V["trustworthiness_k10"], I["trustworthiness_k10"], V1.get("trustworthiness_k10"), 3),
        ("Continuidad (k = 10)", V["continuidad_k10"], I["continuidad_k10"], V1.get("continuidad_k10"), 3),
        ("Spearman distancias mapa / perfil", V["spearman_distancias"], I["spearman_distancias"], V1.get("spearman_distancias"), 3),
        ("R² medio de reconstrucción", V["r2_medio"], I["r2_medio"], V1.get("r2_medio"), 2),
        ("Parejas de estilos distintas (Holm 5 %)", f'{V["diferenciacion"]["pares_distintos_holm_05"]}/{V["diferenciacion"]["pares"]}',
         f'{I["diferenciacion"]["pares_distintos_holm_05"]}/{I["diferenciacion"]["pares"]}',
         f'{V1["diferenciacion"]["pares_distintos_holm_05"]}/{V1["diferenciacion"]["pares"]}' if V1 else "–", None),
        ("Mahalanobis mínima entre estilos", V["diferenciacion"]["mahalanobis_min"], I["diferenciacion"]["mahalanobis_min"], V1.get("diferenciacion", {}).get("mahalanobis_min"), 2),
        ("Replicabilidad de perfiles 2020-23 / 2023-26", V["replicabilidad"]["correlacion_media"], I["replicabilidad"]["correlacion_media"], V1.get("replicabilidad", {}).get("correlacion_media"), 2),
        ("Persistencia del estilo (azar)", f'{pc(V["persistencia"]["mismo_estilo"])} ({pc(V["persistencia"]["por_azar"])})',
         f'{pc(I["persistencia"]["mismo_estilo"])} ({pc(I["persistencia"]["por_azar"])})',
         f'{pc(V1["persistencia"]["mismo_estilo"])} ({pc(V1["persistencia"]["por_azar"])})' if V1 else "–", None),
    ]
    t_cmp = tabla(["Métrica (997 clubes, 2020-26)", "VaDE v2", "IDEC v2", "VaDE v1"],
                  [[nm, a if d is None else n(a, d), b if d is None else n(b, d), c if d is None else n(c, d)] for nm, a, b, c, d in filas_cmp], {1, 2, 3})
    filas_est = []
    for k, r in est.iterrows():
        ligas = json.loads(r["ligas"].replace("'", '"'))
        top = ", ".join(f"{LIGAS[l]} {pc(v)}" for l, v in sorted(ligas.items(), key=lambda x: -x[1])[:2])
        filas_est.append([f'{sw(k)}<b>{e(nombre(r["estilo"]))}</b><br><span class="clave">{r["estilo"]}</span>',
                          e(nom.get(r["estilo"], {}).get("resumen", r["descriptor"])), int(r["clubes"]),
                          n(r["nivel_medio"], 2, True), top])
    t_est = tabla(["Estilo", "Rasgos que lo definen", "Clubes", "Nivel", "Ligas principales"], filas_est, {2, 3})
    filas_bk = []
    for r in bk["temporadas"]:
        k = int(r["estilo"][1:]) - 1
        filas_bk.append([r["temporada"] + ("*" if r["provisional"] else ""), LIGAS[r["liga"]], f'{sw(k)}{e(nombre(r["estilo"]))}',
                         n(r["p"]), n(r["nivel"], 2, True),
                         ", ".join(f'{e(m["club"])} ({n(m["d"])})' for m in r["mas_parecidos"][:3]),
                         n(r.get("desplazamiento")) + (f' (p{n(r.get("pct_desplazamiento"), 0)})' if r.get("desplazamiento") is not None else "")])
    t_bk = tabla(["Temp.", "Competición", "Estilo", "p", "Nivel", "Clubes más parecidos esa temporada (distancia)", "Cambio"], filas_bk, {3, 4, 6})
    t_enc = tabla(["Modelo (MCO, errores HC3)", "Coeficiente", "IC 95 %", "p", "R²"],
                  [[f"Δ nivel ~ {x}", n(m["coef"], 3, True), f'{n(m["ic95"][0], 3, True)} a {n(m["ic95"][1], 3, True)}', p_txt(m["p"]), n(m["r2"], 3)]
                   for x, m in (("distancia", ed), ("afinidad", ea), ("distancia (Δ cuota de minutos)", ec))], {1, 3, 4})
    t_ter = tabla(["Tercil de distancia", "n", "Distancia media", "Δ nivel medio", "Δ cuota de minutos"],
                  [[r["tercil"], r["n"], n(r["distancia"]), n(r["d_nivel"], 3, True), n(100 * r["d_cuota"], 1, True) + " pp"] for r in enc["por_tercil"]], {1, 2, 3, 4})
    t_con = tabla(["Cuartil de continuidad", "n", "Continuidad media", "Desplazamiento en el mapa", "Conserva el estilo"],
                  [[r["cuartil"], r["n"], pc(r["continuidad"]), n(r["desplazamiento"]), pc(r["mismo_estilo"])] for r in con["por_cuartil"]], {1, 2, 3, 4})

    # ---------------------------------------------------------------- texto
    eta_v2, eta_v1 = V["eta2_nivel"], V1.get("eta2_nivel")
    nmi_v2, nmi_v1 = V["nmi_estilo_liga"], V1.get("nmi_estilo_liga")
    sig_ex = ex["p_estilo_dado_nivel"] is not None and ex["p_estilo_dado_nivel"] < 0.05
    por_ex = sorted(ex["por_estilo"], key=lambda r: -r["resid"])
    mejor_ex, peor_ex = por_ex[0], por_ex[-1]
    sig_enc = ed["p"] < 0.05
    ultimo = {l: [r for r in bk["temporadas"] if r["liga"] == l and not r["provisional"]][-1] for l in ("euroleague", "acb")}
    hoy = date.today().strftime("%d-%m-%Y")
    pur_max = max(((l, v, r["estilo"]) for _, r in est.iterrows() for l, v in json.loads(r["ligas"].replace("'", '"')).items()), key=lambda x: x[1])
    k8 = bar["k"].index(8)
    desp_bk = [r["pct_desplazamiento"] for r in bk["temporadas"] if r.get("pct_desplazamiento") is not None and not r["provisional"]]
    signo_enc = "positivo" if ed["coef"] > 0 else "negativo"
    fig_n = iter(range(1, 20))

    cuerpo = f"""
<h1>Ocho estilos de juego independientes del nivel en ocho ligas de baloncesto</h1>
<p style="font-size:12.5pt;margin-top:-2pt;color:#6b4f38;text-align:left">Un autoencoder variacional de mezcla gaussiana con mapa tridimensional para evaluar el encaje de fichajes en Saski Baskonia</p>
<div class="autores">Dirección Deportiva · Saski Baskonia &nbsp;|&nbsp; Modelado y análisis: Claude Code (Anthropic) &nbsp;|&nbsp; {hoy} &nbsp;|&nbsp; Código: paquete <code>bbestilo</code>, rama <code>claude/bold-euler-hubmhk</code></div>

<div class="resumen">
<p><b>Resumen.</b> Se presenta un modelo que asigna a cada club, competición y temporada uno de ocho estilos de juego y lo sitúa, junto con sus jugadores, en un mapa tridimensional común. Los datos son los equivalentes EuroLeague de un estudio previo de normalización entre ligas (algoritmos A y B), agregados por minutos para {n_cl} clubes-temporada de ocho competiciones entre 2020-21 y 2025-26 (más {n_prov} de 2026-27, provisionales). Como esa vara común traslada el nivel de cada liga a las métricas de estilo, cada uno de los 13 rasgos se depura de la parte explicada por un índice de calidad; el nivel explicaba hasta el {pc(r2.max())} de algunos rasgos. El modelo es un VaDE (autoencoder variacional con previa de mezcla) de {n_par:,} parámetros con capa latente de tres neuronas (el mapa) y capa de salida de ocho (los estilos), covarianzas completas, regularización de estrés MDS, consenso de cinco semillas y ajuste fino desde el consenso.</p>
<p>Tras neutralizar, el estilo explica el {pc(eta_v2, 1)} del nivel de los clubes (frente al {pc(eta_v1, 0)} de la versión anterior) y la información compartida entre estilo y liga baja de {n(nmi_v1, 2)} a {n(nmi_v2, 2)}. Las 28 parejas de estilos difieren en pruebas de permutación con corrección de Holm, y los perfiles se replican entre 2020-23 y 2023-26 (r = {n(V["replicabilidad"]["correlacion_media"], 2)}). El mapa es estable entre redes (r = {n(V["estabilidad_mapa"], 2)}) y fiel a las distancias del perfil (trustworthiness {n(V["trustworthiness_k10"], 2)}). Como hallazgos complementarios: los criterios de información prefieren {bar["k_optimo_bic_rasgos"]} estilos y la estabilidad cae a partir de ese número, de modo que ocho es una resolución algo más fina de la que los datos respaldan con claridad; a igual nivel, {"el estilo explica una parte relevante del net rating (η² parcial " + pc(ex["eta2_parcial_estilo"], 0) + "), en buena medida por rasgos que son factores de eficiencia" if sig_ex else "el estilo no explica el net rating"}; en {enc["casos"]:,} cambios de club, parecerse al estilo del club de destino no mejora el rendimiento posterior del jugador (la asociación es pequeña y de signo {signo_enc}, {n(ed["coef"], 3, True)} por unidad de distancia); y la continuidad de la plantilla predice que el club conserve su estilo (OR = {n(con["or_mismo_estilo_por_10pp"], 2)} por cada 10 puntos). Baskonia es de los clubes que más cambian de estilo entre temporadas.</p>
<p class="clave"><b>Palabras clave:</b> baloncesto · estilo de juego · agrupamiento profundo · VaDE · autoencoder variacional · normalización entre ligas · scouting · encaje de fichajes</p>
</div>

<h2>1. Introducción</h2>
<p>La dirección deportiva necesita responder a dos preguntas que las estadísticas brutas no permiten comparar entre ligas: cómo ha jugado su equipo en cada temporada y competición, y si un jugador que se estudia encaja en esa forma de jugar o, por el contrario, añadiría a la plantilla un perfil ajeno al del resto («una oveja de cada madre»). Un estudio previo del club resolvió la comparabilidad del rendimiento individual trasladando las métricas de los jugadores de ocho ligas a la vara de la EuroLeague 2025-26 (algoritmos A, B y su media A+B). Este trabajo construye sobre esos datos un modelo de <i>estilo de juego</i> de los clubes.</p>
<p>Una primera versión (v1) entrenó dos redes, IDEC y VaDE, con doce estilos y sin tratar el nivel. Puso de manifiesto dos problemas: doce estilos fuerzan diferencias poco sustanciales, y la vara EuroLeague arrastra el nivel de cada liga a las métricas de estilo, de modo que dos o tres estilos agrupaban casi sólo a clubes NBA y la asignación compartía información con la liga (NMI = {n(nmi_v1, 2)}). La versión que aquí se describe (v2) reduce el número de estilos a ocho, neutraliza el nivel antes de entrenar y refuerza la red VaDE, que la dirección deportiva consideró la más completa.</p>
<p>Las contribuciones son: (i) un procedimiento de neutralización del nivel compatible con la normalización entre ligas y aplicable a cualquier plantilla simulada; (ii) un VaDE con covarianzas completas, regularización de estrés y consenso de semillas, con mapa 3D compartido por clubes y jugadores; (iii) una evaluación de estabilidad, fidelidad y diferenciación estadística; y (iv) análisis complementarios sobre el número de estilos, la relación del estilo con el éxito, el efecto del encaje en los fichajes y la continuidad de las plantillas.</p>

<h2>2. Datos</h2>
<h3>2.1 Fuentes, periodo y normalización previa</h3>
<p>Se usan las estadísticas de temporada regular de ocho competiciones (EuroLeague, EuroCup, Liga Endesa, NBA, G League, LBA, BBL y LNB) entre 2020-21 y 2026-27, extraídas de sus fuentes oficiales con el paquete <code>bbstats</code>. Cada jugador-liga-temporada tiene su equivalente EuroLeague por dos algoritmos del estudio de normalización: A (bayes empírico para quitar la suerte de las muestras pequeñas y un «tipo de cambio» por liga y métrica estimado por EM con 4.336 jugadores puente) y B (red neuronal multitarea que aprende un «ADN» del jugador separando nivel, liga, temporada, posición y equipo). Se usa la media A+B en la escala transformada de cada métrica, que en el examen fuera de muestra del estudio mejoró en un 20 % la predicción de los cambios de liga frente a la práctica habitual de comparar percentiles. Donde B no tiene al jugador (menos de 150 minutos o la temporada en curso) se usa A. En 2026-27, B sólo traduce cuatro filas, por lo que esa temporada se trata como provisional y no entra en el entrenamiento. Las traducciones cubren el 99-100 % de los minutos jugados en cada liga, y B el 95-97 %.</p>
<h3>2.2 Unidad de análisis y agregación</h3>
<p>La unidad es el club-competición-temporada: Baskonia EuroLeague 2025-26 y Baskonia Liga Endesa 2025-26 son dos observaciones. El vector de un club es la media de los vectores de sus jugadores ponderada por los minutos que jugaron en él, es decir, el perfil medio de los cinco jugadores en pista. La agregación es exacta y lineal en los minutos, lo que permite recalcular el club con un fichaje o con otro reparto de minutos. Los rasgos no lineales se construyen con momentos ponderados: la concentración del uso es E<sub>w</sub>[USG²]/E<sub>w</sub>[USG]² (1 = uso repartido) y las cuotas de minutos de interiores y exteriores salen de la posición estimada del estudio. El ritmo no forma parte del estudio de normalización: se añade como el z del ritmo del equipo dentro de su liga y temporada.</p>
<p class="tcap"><b>Tabla 1.</b> Los 13 rasgos de estilo, su origen, la transformación aplicada tras agregar y la parte de su varianza entre clubes que explicaba el índice de nivel antes de neutralizar.</p>
{t_rasgos}
<h3>2.3 Capa de nivel</h3>
<p>Ocho métricas normalizadas miden cuánto rinde un equipo y no cómo juega: PER, Game Score por 40', Win Shares por 40', ORtg, DRtg, puntos por 100 posesiones, TS% y eFG%. Su media de z con signo (DRtg invertido) define un índice de nivel L para cada club (z entre clubes) y para cada jugador (z entre jugadores con 150 o más minutos, ponderado por minutos). Estas métricas no entran en las redes. La Tabla 2 resume el nivel por liga: la vara común conserva las diferencias de nivel (NBA {n(nl.loc["nba", "mean"], 2, True)}, EuroLeague {n(nl.loc["euroleague", "mean"], 2, True)}, BBL {n(nl.loc["bbl", "mean"], 2, True)}), que son precisamente las que no deben confundirse con el estilo.</p>
<p class="tcap"><b>Tabla 2.</b> Clubes-temporada de entrenamiento y nivel medio por liga.</p>
{t_ligas}

<h2>3. Métodos</h2>
<h3>3.1 Neutralización del nivel</h3>
<p>Para cada rasgo transformado y estandarizado x<sub>k</sub> se ajusta, sobre los clubes de entrenamiento, una regresión en una base cuadrática del nivel y se conserva el residuo reescalado a desviación 1:</p>
<div class="eq">x̃_k = ( x_k − β₀k − β₁k · L − β₂k · L² ) / s_k ,   con β por mínimos cuadrados y s_k la desviación del residuo</div>
<p>Los jugadores tienen su propia regresión (sobre jugadores, ponderada por minutos). El nivel se recalcula para cualquier reparto de minutos (plantillas remuestreadas, fichajes simulados) antes de neutralizar. Esta operación no duplica la normalización entre ligas: la normalización pone a todos los jugadores en la misma escala, condición necesaria para que una regresión común sea válida en ocho ligas; la neutralización quita de los rasgos de estilo la parte que se predice por la calidad, sea cual sea la liga. Por el teorema de Frisch–Waugh–Lovell, los residuos son ortogonales a L y L² en la muestra de ajuste. Las diferencias entre ligas que no se deben al nivel (por ejemplo, el volumen de triples o el ritmo) se conservan.</p>
<h3>3.2 Arquitectura</h3>
<p>La red (Figura 1) es un VaDE. Un codificador de dos capas ocultas (64 y 32 neuronas, GELU) produce la media μ<sub>z</sub> y la log-varianza de una posterior gaussiana en ℝ³; μ<sub>z</sub> es el punto del club en el mapa. La previa sobre z es una mezcla de ocho gaussianas con covarianza completa, de modo que cada estilo es un elipsoide con su centro, su forma y su orientación. La capa de salida tiene ocho neuronas: la probabilidad a posteriori de cada componente, γ<sub>k</sub> = π<sub>k</sub>N(z | μ<sub>k</sub>, Σ<sub>k</sub>) / Σ<sub>j</sub> π<sub>j</sub>N(z | μ<sub>j</sub>, Σ<sub>j</sub>). El estilo asignado es la neurona de mayor salida. El decodificador (3 → 32 → 64 → 13) usa una varianza de reconstrucción común a los 13 rasgos; con una varianza por rasgo, la red de la v1 trataba como ruido rasgos difíciles como el ritmo.</p>
{figura(F["arquitectura"], next(fig_n), "Arquitectura del VaDE v2. El mapa 3D es la media de la posterior; la capa de salida es la responsabilidad de cada una de las 8 componentes de la mezcla.")}
<h3>3.3 Función de pérdida</h3>
<div class="eq">ℒ = −ELBO + λ · estrés
−ELBO = ½ Σ_j [ (x_j − x̂_j)² / σ²_x + log σ²_x ] + β [ Σ_k γ_k · ½ ( log|Σ_k| + tr(Σ_k⁻¹ diag σ²_z) + (μ_z − μ_k)ᵀ Σ_k⁻¹ (μ_z − μ_k) )
        − Σ_k γ_k log(π_k / γ_k) − ½ Σ_j (1 + log σ²_zj) ]
estrés = Σ_(i&lt;j) ( ‖z_i − z_j‖ − ‖x_i − x_j‖ )² / Σ_(i&lt;j) ‖x_i − x_j‖²     (por lote, escala fija)</div>
<p>El término de estrés de MDS métrico (Kruskal, 1964) hace que la distancia en el mapa se lea en las mismas unidades que la distancia entre perfiles de estilo (desviaciones típicas), que es lo que la dirección deportiva necesita para comparar un club con un jugador. Su peso, λ = {n(hv["lambda_estres"], 0)}, iguala el peso relativo que tiene en la red de contraste, porque el −ELBO suma sobre los 13 rasgos. β crece de 0,1 a 1 en las primeras {hv["calentamiento"]} épocas para evitar el colapso de la posterior.</p>
<h3>3.4 Entrenamiento</h3>
<p>Cada época recorre: (a) los {n_cl} clubes reales; (b) {C.BOOTSTRAP_POR_CLUB} plantillas remuestreadas por club, multiplicando los minutos de cada jugador por una Gamma({C.K_GAMMA:g}, 1/{C.K_GAMMA:g}) (coeficiente de variación del 50 %), con su nivel recalculado; y (c) los jugadores con 150 o más minutos, con peso 0,3, para que el codificador conozca la región donde caen los jugadores sin que éstos definan los estilos. Tras un preentreno como autoencoder determinista con estrés, la mezcla se inicializa por EM sobre el mapa preentrenado. Los parámetros de la red se optimizan con Adam; los de la mezcla no reciben gradiente: tras cada época se reestiman con un paso M amortiguado sobre los clubes (reales y remuestreados), con π uniforme, un suelo de varianza y resiembra de las componentes con menos del 1 % de los clubes. Este esquema evita el colapso en pocas componentes que mostró el VaDE original.</p>
<p>Se entrenan cinco redes con semillas distintas. Su partición de consenso se obtiene de la matriz de co-asociación (fracción de redes que asignan dos clubes al mismo estilo) con agrupamiento jerárquico de enlace medio (Fred y Jain, 2005). La red cuya partición más se parece al consenso (semilla {cons.get("semilla_base", "–")}) recibe una mezcla fijada en la media y la covarianza de cada grupo de consenso en su propio mapa, y se ajustan {hv["epocas_afinado"]} épocas más sólo el codificador y el decodificador, de modo que el mapa se adapta a los estilos acordados. El ARI de las semillas con el consenso fue {", ".join(n(x, 2) for x in cons.get("ari_semillas_consenso", []))}; el del modelo final, {n(cons.get("ari_final_consenso"), 2)}, y su ARI medio con las cinco semillas, {n(V["ari_final_semillas_medio"], 2)}: es más central que cualquiera de ellas por separado. Una primera variante que mantenía el paso M durante el ajuste fino se alejaba del consenso (ARI 0,57) porque la partición de consenso contenía un grupo de sólo {min(cons.get("tamanos_consenso", [0]))} clubes. Finalmente, el mapa se orienta con sus ejes principales (eje 1 = mayor varianza), con un signo determinista y una escala única, y los estilos se numeran por la posición de su centro en el eje 1. La Tabla 3 recoge los hiperparámetros.</p>
<p class="tcap"><b>Tabla 3.</b> Hiperparámetros del VaDE v2.</p>
{t_hiper}
<h3>3.5 Red de contraste y evaluación</h3>
<p>Como referencia se entrena con los mismos datos una IDEC (Guo et al., 2017): autoencoder con capa de agrupamiento de núcleo t de Student sobre ocho centroides en el mapa, con el mismo término de estrés. Se evalúa sobre los {n_cl} clubes: reparto (entropía, tamaño mínimo); seguridad de la asignación; separación (silueta en el mapa y en los rasgos); estabilidad de los estilos (ARI entre semillas) y del mapa (correlación de las distancias club-club entre semillas); robustez al reparto de minutos (40 plantillas remuestreadas por club); reproducibilidad temporal (red entrenada sin 2024-25 ni 2025-26 frente a la red completa, sobre esos clubes); fidelidad del mapa (trustworthiness y continuidad, k = 10; Venna y Kaski, 2001); diferenciación (Mahalanobis entre perfiles medios con covarianza intra-estilo común y prueba de permutación con 9.999 réplicas por pareja y corrección de Holm); replicabilidad de los perfiles entre periodos; y neutralidad (η² del nivel explicado por el estilo, NMI entre estilo y liga).</p>
<h3>3.6 Análisis complementarios</h3>
<ul>
<li><b>Número de estilos.</b> BIC e ICL (Schwarz, 1978; Biernacki et al., 2000) de mezclas gaussianas sobre los 13 rasgos sin nivel y sobre el mapa, silueta y estabilidad de k-medias por submuestreo (80 %, 10 réplicas), K = 2 a 14.</li>
<li><b>Estilo y éxito.</b> Net rating del equipo estandarizado dentro de su liga y temporada frente al estilo, comparando por F los modelos anidados net ~ L y net ~ L + estilo.</li>
<li><b>Efecto del encaje.</b> Jugadores que cambian de club entre temporadas consecutivas con 300 o más minutos en ambas. La variable explicativa es la distancia en el mapa entre el jugador (temporada t) y su club de destino en la temporada t, antes de su llegada; las respuestas, el cambio en su índice de nivel y en su cuota de minutos. Se controla por nivel inicial, edad (y su cuadrado), cambio de liga y nivel del club de destino, con errores robustos HC3 (MacKinnon y White, 1985).</li>
<li><b>Continuidad.</b> Proporción de los minutos de t+1 jugados por quienes ya estaban en t, frente al desplazamiento del club en el mapa (Spearman) y a conservar el estilo (logit).</li>
<li><b>Ligas y temporadas.</b> Tablas de contingencia estilo × liga y estilo × temporada (χ², V de Cramér) y distancias entre los centroides de liga en el mapa.</li>
</ul>

<h2>4. Resultados</h2>
<h3>4.1 Entrenamiento</h3>
<p>Las cinco redes convergieron sin colapso: el estilo más pequeño mantuvo en todas las épocas más del {pc(min(r["cuota_min"] for r in reg["registro"]), 0)} de las muestras de club (Figura 2). La partición de consenso y el ajuste fino posterior dieron un modelo final cuyos estilos tienen entre {V["tamano_min"]} y {V["tamano_max"]} clubes (entropía del reparto {n(V["entropia_reparto"], 3)}).</p>
{figura(F["entrenamiento"], next(fig_n), "Pérdida por época y cuota del estilo más pequeño y más grande durante el entrenamiento de la red base y su ajuste fino desde el consenso.", "88%")}
<h3>4.2 Neutralización del nivel</h3>
<p>El nivel explicaba una parte muy grande de varios rasgos de estilo de los clubes: {", ".join(f"{e(C.RASGOS[k].corto)} {pc(r2[k])}" for k in top_r2)} (Figura 3). Son rasgos en los que, en la vara EuroLeague, los mejores jugadores producen más (rebote, asistencias, tiros libres) o cometen menos faltas. Otros rasgos apenas dependían del nivel (ritmo, rebote ofensivo, concentración del uso, posiciones). Tras neutralizar, la correlación de todos los rasgos con L es nula por construcción, y el efecto sobre la asignación es el buscado: el estilo explica el {pc(eta_v2, 1)} de la varianza del nivel (v1: {pc(eta_v1, 0)}), la información compartida entre estilo y liga baja de {n(nmi_v1, 2)} a {n(nmi_v2, 2)}, y la pureza media de liga de los estilos pasa de {pc(V1.get("pureza_liga_media"))} a {pc(V["pureza_liga_media"])}. Ningún estilo tiene más de la mitad de sus clubes en una sola liga; el más concentrado es «{e(nombre(pur_max[2]))}», con un {pc(pur_max[1])} de clubes de la {LIGAS[pur_max[0]]}, reflejo de que la NBA, a igual nivel, juega más cerca del aro y con más tiros libres.</p>
{figura(F["neutralizacion"], next(fig_n), "Parte de la varianza entre clubes de cada rasgo de estilo explicada por el índice de nivel (regresión cuadrática) antes de neutralizar.", "82%")}
<h3>4.3 Calidad del modelo</h3>
<p>La Tabla 4 compara el VaDE v2 con la IDEC entrenada con los mismos datos y con el VaDE de la versión anterior. {"El VaDE v2 asigna con más seguridad que la IDEC" if V["salida_max_media"] > I["salida_max_media"] else "La IDEC asigna con más seguridad que el VaDE"} ({n(V["salida_max_media"], 2)} frente a {n(I["salida_max_media"], 2)}); la estabilidad del mapa entre semillas es {n(V["estabilidad_mapa"], 2)} y la de los estilos {n(V["ari_semillas_medio"], 2)} (ARI). Las 28 parejas de estilos son distintas tras la corrección de Holm y la distancia de Mahalanobis mínima entre perfiles medios es {n(V["diferenciacion"]["mahalanobis_min"], 2)} desviaciones. Estas pruebas son optimistas por construcción, porque los grupos se forman con los mismos datos; la replicabilidad entre periodos (r = {n(V["replicabilidad"]["correlacion_media"], 2)}) no lo es y es la evidencia principal de que los estilos describen algo estable. La silueta en los 13 rasgos es baja ({n(V["silueta_rasgos"], 3)}; k-medias directo, {n(ev["referencia_kmedias"]["silueta_rasgos"], 3)}): los estilos son una partición útil de un continuo, no grupos separados. El ajuste fino desde el consenso cambia separación por estabilidad: el modelo final es menos compacto en los rasgos que la IDEC, pero asigna con mucha más seguridad ({n(V["salida_max_media"], 2)}), su mapa es más estable ({n(V["estabilidad_mapa"], 2)} frente a {n(I["estabilidad_mapa"], 2)}) y es el más central respecto a sus semillas ({n(V["ari_final_semillas_medio"], 2)} frente a {n(I["ari_final_semillas_medio"], 2)}). La IDEC, en cambio, reproduce mejor la partición cuando se entrena sin las dos últimas temporadas ({n(I["ari_temporal_reserva"], 2)} frente a {n(V["ari_temporal_reserva"], 2)}).</p>
<p class="tcap"><b>Tabla 4.</b> Evaluación comparada. VaDE v1 = 12 estilos, sin neutralizar el nivel y con covarianza diagonal.</p>
{t_cmp}
<h3>4.4 Los ocho estilos</h3>
<p>La Tabla 5 y la Figura 4 describen los ocho estilos por su perfil medio (rasgos sin nivel, en desviaciones típicas frente al club medio). Los nombres son interpretativos y se han puesto a partir de esos perfiles; los identificadores E01-E08 ordenan los estilos por el eje 1 del mapa.</p>
<p class="tcap"><b>Tabla 5.</b> Los ocho estilos: rasgos que los definen, número de clubes (2020-26), nivel medio (no interviene en la asignación) y ligas con más clubes en el estilo.</p>
{t_est}
{figura(F["perfiles"], next(fig_n), "Perfil medio de cada estilo en los 13 rasgos sin nivel (desviaciones típicas frente al club medio).")}
<h3>4.5 El mapa</h3>
{figura(F["mapa"], next(fig_n), "Proyecciones del mapa 3D: clubes de 2020-21 a 2025-26 coloreados por estilo; rombos = centros de los estilos.")}
<p>La Figura 5 muestra las tres proyecciones del mapa. La fidelidad es alta: el {pc(V["trustworthiness_k10"], 0)} de la vecindad del mapa son vecinos reales en los rasgos (trustworthiness) y la correlación de Spearman entre distancias del mapa y del perfil es {n(V["spearman_distancias"], 2)}.</p>
<h3>4.6 Ligas y temporadas</h3>
<p>El estilo sigue asociado a la liga, pero de forma moderada (χ² = {n(lg["chi2_liga"], 0)}, V de Cramér = {n(lg["v_cramer_liga"], 2)}, {p_txt(lg["p_liga"])}), lo que es esperable: el reglamento y la cultura de juego de cada liga influyen en cómo se juega a igual nivel (Figura 6). Las ligas más parecidas en estilo a la EuroLeague son {cerca("euroleague")}; a la Liga Endesa, {cerca("acb")}. La asociación entre estilo y temporada es {"débil pero significativa" if lg["p_temporada"] < 0.05 else "no significativa"} (V = {n(lg["v_cramer_temporada"], 2)}, {p_txt(lg["p_temporada"])}).</p>
{figura(F["liga_estilo"], next(fig_n), "Porcentaje de los clubes de cada liga (2020-21 a 2025-26) asignados a cada estilo.", "86%")}
<h3>4.7 Saski Baskonia</h3>
<p>La Tabla 6 y la Figura 7 recogen el estilo de Baskonia en cada temporada y competición, sus tres clubes más parecidos de esa temporada en cualquier liga y el desplazamiento respecto al año anterior (con su percentil entre todos los clubes). En 2025-26, el equipo de EuroLeague se asigna a «{e(nombre(ultimo["euroleague"]["estilo"]))}» (p = {n(ultimo["euroleague"]["p"])}) y el de Liga Endesa a «{e(nombre(ultimo["acb"]["estilo"]))}» (p = {n(ultimo["acb"]["p"])}). «{e(nombre("E07"))}» es el estilo más repetido del equipo de EuroLeague. Baskonia cambia de estilo más que la mayoría de los clubes: la mediana de sus desplazamientos entre temporadas está en el percentil {n(float(np.median(desp_bk)), 0)} de todos los clubes (desplazamiento mediano de un club: {n(bk["desplazamiento_mediano_clubes"])}), coherente con una plantilla que se renueva mucho cada verano.</p>
<p class="tcap"><b>Tabla 6.</b> Baskonia por temporada. p = salida de la neurona ganadora; cambio = distancia al punto del año anterior (percentil entre todos los clubes). * provisional.</p>
{t_bk}
{figura(F["baskonia"], next(fig_n), "Trayectoria de Baskonia en el plano de los ejes 1 y 2 (EuroLeague y Liga Endesa); color del punto = estilo; rombos = centros de los estilos; gris = resto de clubes.", "78%")}
<h3>4.8 Hallazgos complementarios</h3>
<p><b>Número de estilos.</b> Sobre los 13 rasgos sin nivel, el BIC alcanza su mínimo con K = {bar["k_optimo_bic_rasgos"]} y el ICL con K = {bar["k_optimo_icl_rasgos"]}; en el mapa, el BIC lo hace con K = {bar["k_optimo_bic_mapa"]} (sesgado hacia 8, porque el mapa se entrenó con ocho componentes). La estabilidad de k-medias con K = 8 es {n(bar["estabilidad_kmedias"][bar["k"].index(8)], 2)} y la silueta {n(bar["silueta_kmedias"][bar["k"].index(8)], 3)} (Figura 8). La estabilidad es alta hasta K = 5 ({n(bar["estabilidad_kmedias"][bar["k"].index(5)], 2)}) y cae con K ≥ 6. Los datos respaldan con claridad entre cuatro y seis estilos; ocho es una resolución más fina, útil para describir matices, pero cuyas fronteras son menos estables. Un modelo de seis estilos sería la alternativa estadísticamente más defendible.</p>
{figura(F["barrido"], next(fig_n), "Barrido de K: criterios de información normalizados (izquierda) y estabilidad y silueta de k-medias (derecha). Línea de puntos: K = 8.", "92%")}
<p><b>Estilo y éxito.</b> En {ex["clubes"]} clubes con net rating, el nivel explica el {pc(ex["r2_nivel"])} del net rating estandarizado (r = {n(ex["r_nivel_net"], 2)}). Sin controlar el nivel, el estilo explica el {pc(ex["r2_estilo"], 1)} (F = {n(ex["f_estilo_sin_control"], 2)}, {p_txt(ex["p_estilo_sin_control"])}); dado el nivel, {"añade un η² parcial del " + pc(ex["eta2_parcial_estilo"], 1) + f" (F = {n(ex['f_estilo_dado_nivel'], 2)}, {p_txt(ex['p_estilo_dado_nivel'])})" if sig_ex else f"no añade información significativa (F = {n(ex['f_estilo_dado_nivel'], 2)}, {p_txt(ex['p_estilo_dado_nivel'])})"}. Esta asociación tiene una parte mecánica: varios rasgos de estilo (pérdidas, rebote, tiros libres) son los «cuatro factores» de Dean Oliver, que determinan la eficiencia. Aun así, indica que, entre equipos de igual nivel individual, la forma de jugar se asocia con ganar. El estilo con mayor net rating residual es «{e(nombre(mejor_ex["estilo"]))}» ({n(mejor_ex["resid"], 2, True)} σ ± {n(mejor_ex["ic95"], 2)}) y el de menor, «{e(nombre(peor_ex["estilo"]))}» ({n(peor_ex["resid"], 2, True)} σ ± {n(peor_ex["ic95"], 2)}) (Figura 9).</p>
{figura(F["exito"], next(fig_n), "Net rating del equipo no explicado por el nivel, por estilo (media e IC 95 %).", "72%")}
<p><b>Efecto del encaje.</b> Se identificaron {enc["casos"]:,} cambios de club con 300 o más minutos en ambas temporadas. {"La distancia de estilo entre el jugador y su destino se asocia con su cambio de nivel, pero en sentido contrario al de la hipótesis del encaje y con un tamaño muy pequeño" if (sig_enc and ed["coef"] > 0) else ("La distancia de estilo entre el jugador y su destino se asocia con su cambio de nivel" if sig_enc else "La distancia de estilo entre el jugador y su destino no se asocia de forma significativa con su cambio de nivel")} (Tabla 7): {n(ed["coef"], 3, True)} por unidad de distancia (IC 95 % {n(ed["ic95"][0], 3, True)} a {n(ed["ic95"][1], 3, True)}, {p_txt(ed["p"])}). Con la afinidad (la salida del jugador en la neurona del estilo del club) el coeficiente es {n(ea["coef"], 3, True)} ({p_txt(ea["p"])}), y sobre la cuota de minutos, {n(100 * ec["coef"], 2, True)} puntos por unidad de distancia ({p_txt(ec["p"])}). La Tabla 8 muestra que la relación no es monótona por terciles (correlación de Spearman {n(enc["spearman_distancia_dnivel"], 3)}). Parecerse al estilo del club no es, por tanto, un predictor del rendimiento individual tras el fichaje; si acaso, los jugadores que llegan a clubes de estilo distinto al suyo mejoran ligeramente más, lo que es compatible con fichajes de complementariedad (incorporar el perfil que le falta a la plantilla).</p>
<p class="tcap"><b>Tabla 7.</b> Efecto del encaje: regresiones con controles de nivel inicial, edad, edad², cambio de liga y nivel del club de destino.</p>
{t_enc}
<p class="tcap"><b>Tabla 8.</b> Cambios de club por tercil de distancia de estilo (medias sin ajustar).</p>
{t_ter}
<p><b>Continuidad de plantilla.</b> En {con["parejas"]} pares de temporadas consecutivas, la continuidad media fue {pc(con["continuidad_media"])}. Una plantilla más continua se desplaza menos en el mapa (Spearman {n(con["spearman_continuidad_desplazamiento"], 2)}, {p_txt(con["p_spearman"])}) y conserva más a menudo su estilo: cada 10 puntos de continuidad multiplican por {n(con["or_mismo_estilo_por_10pp"], 2)} la odds de conservarlo ({p_txt(con["p_logit"])}; Tabla 9).</p>
<p class="tcap"><b>Tabla 9.</b> Continuidad de plantilla, desplazamiento en el mapa y conservación del estilo, por cuartiles.</p>
{t_con}

<h2>5. Discusión</h2>
<p><b>Lo esperado y lo obtenido.</b> Se esperaba que neutralizar el nivel deshiciera los estilos «de liga» de la v1 sin destruir la estructura del estilo, y así ha sido: la asociación estilo-nivel cae a un η² de {pc(eta_v2, 1)}, la información compartida entre estilo y liga baja de {n(nmi_v1, 2)} a {n(nmi_v2, 2)}, y los perfiles siguen siendo diferenciables y replicables. Se esperaba que ocho estilos dieran asignaciones más seguras que doce: la seguridad media del VaDE sube de {n(V1.get("salida_max_media"), 2)} a {n(V["salida_max_media"], 2)}, y la estabilidad del mapa se mantiene ({n(V["estabilidad_mapa"], 2)}; v1, {n(V1.get("estabilidad_mapa"), 2)}). No se esperaba encontrar un número natural de estilos, y los criterios de información lo confirman: el estilo de juego de los clubes, medido con estos 13 rasgos, es un continuo, con una resolución estable de cuatro a seis estilos. La recomendación práctica es leer la etiqueta junto con la probabilidad de la neurona ganadora y, sobre todo, la distancia en el mapa.</p>
<p><b>Lo inesperado.</b> Dos resultados contradicen intuiciones habituales. Primero, a igual nivel individual el estilo sí se asocia con el net rating del equipo, con estilos que ganan sistemáticamente más («{e(nombre(mejor_ex["estilo"]))}») y otros que ganan menos («{e(nombre(peor_ex["estilo"]))}»). Segundo, parecerse al estilo del nuevo club no se traduce en mejor rendimiento del jugador: el encaje por similitud no es un predictor de rendimiento.</p>
<p><b>Para la dirección deportiva.</b> Neutralizar el nivel separa la pregunta «¿encaja este jugador?» de «¿es bueno este jugador?», que la capa de nivel responde aparte. Los resultados sugieren usar el mapa para tres decisiones: (i) definir y mantener una identidad de juego, ya que la continuidad de la plantilla es el principal predictor de conservar el estilo y Baskonia cambia de estilo más que la mayoría de los clubes; (ii) orientar la plantilla hacia estilos que, a igual nivel, se asocian con más net rating; y (iii) usar la distancia del jugador al club para decidir si se busca similitud (reforzar la identidad) o complementariedad (cubrir un rasgo que falta), no como predictor de su rendimiento individual, que depende del nivel.</p>

<h2>6. Dificultades encontradas</h2>
<ul>
<li><b>Mapa degenerado y colapso.</b> Sin el término de estrés, la IDEC dejaba el mapa casi en dos dimensiones y el VaDE colapsaba en dos componentes. El estrés de escala fija y el paso M con π uniforme y resiembra lo resolvieron; con estrés normalizado (invariante a la escala), la IDEC colapsó en un solo estilo porque su núcleo depende de la escala absoluta.</li>
<li><b>Rasgos tratados como ruido.</b> Con una varianza de reconstrucción por rasgo, el VaDE representaba mal el ritmo y la concentración del uso (R² 0,08 y 0,15); se pasó a una varianza común.</li>
<li><b>Potencia de las pruebas.</b> Con 999 permutaciones, la corrección de Holm sobre 66 parejas no podía declarar ninguna significativa (p mínimo 0,001 × 66); se pasó a 9.999.</li>
<li><b>Consenso degenerado.</b> La partición de consenso por enlace medio produjo un grupo de {min(cons.get("tamanos_consenso", [0]))} clubes; con paso M durante el ajuste fino, la red se alejaba del consenso. Fijar la mezcla del consenso y entrenar sólo codificador y decodificador lo resolvió.</li>
<li><b>Sesgo de nivel.</b> El más importante: la vara común trasladaba el nivel al estilo (NMI estilo-liga {n(nmi_v1, 2)} en la v1), motivo de la versión 2.</li>
<li><b>Datos.</b> La posición se estima en EuroLeague, EuroCup, LBA y parte de la G League (≈77 % de acierto); los traspasos en EuroLeague y EuroCup vienen en una fila (se asignan al último equipo); LBA y LNB cambian el identificador de equipo cada temporada (se enlazan por nombre y continuidad de plantilla); la LNB no publica totales de rivales; 2026-27 sólo tiene unas jornadas y el algoritmo A.</li>
</ul>

<h2>7. Limitaciones</h2>
<ul>
<li>Los rasgos describen al jugador en pista, no el sistema del entrenador: no hay tipos de jugada, defensas zonales, distribución de tiro por zonas ni datos de quintetos.</li>
<li>Las traducciones A+B reducen el ruido y parte del contexto de equipo; el estilo medido es el de los jugadores que el club pone en pista.</li>
<li>La neutralización es lineal-cuadrática en un índice de nivel; un nivel multidimensional podría dejar restos de asociación con aspectos concretos de la calidad.</li>
<li>El análisis del efecto del encaje es observacional: los clubes eligen a quién fichan, lo que puede sesgar la estimación en cualquier dirección.</li>
<li>El ritmo del jugador es el de su equipo; en la simulación de un fichaje se le asigna el del club destino.</li>
</ul>

<h2>8. Mejoras futuras</h2>
<ol>
<li><b>Datos de juego más finos:</b> distribución de tiro por zonas, tipos de jugada (pick and roll, aislamiento, transición), defensa por posesión y quintetos en pista, cuando estén disponibles para las ocho ligas.</li>
<li><b>Neutralización dentro de la red:</b> un VaDE condicional (decodificador condicionado al nivel) o con penalización de independencia (HSIC) entre el mapa y el nivel, en lugar de residualizar antes.</li>
<li><b>Estructura temporal y de club:</b> efectos aleatorios de club y dinámica entre temporadas (un VaDE secuencial) para separar identidad estable y cambio.</li>
<li><b>Entrenador como covariable:</b> enlazar cada club-temporada con su entrenador para medir cuánto estilo viaja con él.</li>
<li><b>Número de estilos:</b> entrenar y comparar un modelo de seis estilos, el que prefieren los criterios de información, y mezclas de proceso de Dirichlet que estimen K y su incertidumbre.</li>
<li><b>Evaluación causal del encaje:</b> emparejamiento o variables instrumentales para aislar el efecto del encaje sobre el rendimiento y los minutos.</li>
<li><b>Arquetipos de jugador:</b> una segunda red para los roles individuales y una matriz de compatibilidad rol × estilo.</li>
<li><b>Actualización continua:</b> reentrenar con cada carga de datos de la temporada en curso y calibrar las probabilidades de salida.</li>
</ol>

<h2>9. Reproducibilidad</h2>
<p>Todo el proceso es reproducible desde el repositorio: <code>python -m bbestilo entrenar</code> (entrena IDEC y VaDE, cinco semillas cada una, ≈ 45 min en 4 núcleos), <code>python -m bbestilo analisis</code>, <code>python -m bbestilo exportar</code> (datos del Atlas de Estilos) y <code>python -m bbestilo articulo</code> (este documento). La v1 se reproduce con <code>--estilos 12 --sin-neutralizar</code>. Los modelos, las semillas, la red de reserva, las tablas de clubes, jugadores y estilos y todas las métricas están en <code>data/modelos/estilos/</code>.</p>

<h2>Referencias</h2>
<ol class="refs">
<li>Biernacki, C., Celeux, G. y Govaert, G. (2000). Assessing a mixture model for clustering with the integrated completed likelihood. <i>IEEE Transactions on Pattern Analysis and Machine Intelligence</i>, 22(7), 719-725.</li>
<li>Fred, A. L. N. y Jain, A. K. (2005). Combining multiple clusterings using evidence accumulation. <i>IEEE Transactions on Pattern Analysis and Machine Intelligence</i>, 27(6), 835-850.</li>
<li>Frisch, R. y Waugh, F. V. (1933). Partial time regressions as compared with individual trends. <i>Econometrica</i>, 1(4), 387-401.</li>
<li>Guo, X., Gao, L., Liu, X. y Yin, J. (2017). Improved deep embedded clustering with local structure preservation. <i>IJCAI</i>, 1753-1759.</li>
<li>Hendrycks, D. y Gimpel, K. (2016). Gaussian Error Linear Units (GELUs). arXiv:1606.08415.</li>
<li>Holm, S. (1979). A simple sequentially rejective multiple test procedure. <i>Scandinavian Journal of Statistics</i>, 6(2), 65-70.</li>
<li>Hubert, L. y Arabie, P. (1985). Comparing partitions. <i>Journal of Classification</i>, 2, 193-218.</li>
<li>Jiang, Z., Zheng, Y., Tan, H., Tang, B. y Zhou, H. (2017). Variational Deep Embedding: an unsupervised and generative approach to clustering. <i>IJCAI</i>, 1965-1972.</li>
<li>Kingma, D. P. y Ba, J. (2015). Adam: a method for stochastic optimization. <i>ICLR</i>.</li>
<li>Kingma, D. P. y Welling, M. (2014). Auto-encoding variational Bayes. <i>ICLR</i>.</li>
<li>Kruskal, J. B. (1964). Multidimensional scaling by optimizing goodness of fit to a nonmetric hypothesis. <i>Psychometrika</i>, 29, 1-27.</li>
<li>MacKinnon, J. G. y White, H. (1985). Some heteroskedasticity-consistent covariance matrix estimators with improved finite sample properties. <i>Journal of Econometrics</i>, 29(3), 305-325.</li>
<li>Oliver, D. (2004). <i>Basketball on Paper: Rules and Tools for Performance Analysis</i>. Potomac Books.</li>
<li>Rousseeuw, P. J. (1987). Silhouettes: a graphical aid to the interpretation and validation of cluster analysis. <i>Journal of Computational and Applied Mathematics</i>, 20, 53-65.</li>
<li>Schwarz, G. (1978). Estimating the dimension of a model. <i>The Annals of Statistics</i>, 6(2), 461-464.</li>
<li>Venna, J. y Kaski, S. (2001). Neighborhood preservation in nonlinear projection methods: an experimental study. <i>ICANN</i>, 485-491.</li>
<li>Xie, J., Girshick, R. y Farhadi, A. (2016). Unsupervised deep embedding for clustering analysis. <i>ICML</i>, 478-487.</li>
<li>Saski Baskonia, Dirección Deportiva (2026). Normalización de ligas hacia la EuroLeague: algoritmos A y B. Documentación interna (<code>docs/algoritmo_A.md</code>, <code>docs/algoritmo_B.md</code>).</li>
</ol>
"""
    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Estilos de juego · Saski Baskonia</title>
<style>{_fuentes_css(fuentes, trabajo)}{CSS}</style></head><body>{cuerpo}</body></html>"""
    (trabajo / "articulo.html").write_text(doc, encoding="utf-8")
    pdf = d / NOMBRE_PDF
    chrome = chrome or _chrome()
    subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf}", "--virtual-time-budget=10000", (trabajo / "articulo.html").as_uri()],
                   check=True, capture_output=True, timeout=180)
    destino = C.RAIZ / "artifact" / "articulo"
    destino.mkdir(parents=True, exist_ok=True)
    shutil.copy(pdf, destino / NOMBRE_PDF)
    return pdf


def _chrome() -> str:
    import glob
    for c in sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")) + [shutil.which("chromium") or "",
                                                                                      shutil.which("google-chrome") or ""]:
        if c and Path(c).exists():
            return c
    raise RuntimeError("No encuentro Chromium para imprimir el PDF")
