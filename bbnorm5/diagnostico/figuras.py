"""F1 · Figuras del informe con el sistema de marca Kerno v2.0 (matplotlib, PNG).

Reglas aplicadas: protagonista en Racing #0F2E25, contexto en Sage, latón profundo #8A6B35 sólo para la lectura (una
por figura), banda de incertidumbre rgba(15,46,37,0.14), punto + rango, sin radar, sin 3D, sin doble eje, etiquetas
en color de texto. Tipografías: Mona Sans (texto) y Geist Mono (datos), instanciadas desde las fuentes del repositorio
(cerno_articulo/recursos/fonts/*.woff2) en experimentos/v5/fuentes/ (no versionado; se regeneran si faltan).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from bbnorm5 import config as C

RACING, CHALK, INK, BRASS_DEEP = "#0F2E25", "#F3F4F0", "#0C1210", "#8A6B35"
S200, S300, S400, S500, S600, S700 = "#CFD5D0", "#B2BAB5", "#8F9993", "#707B75", "#56625C", "#3F4B45"
R300, R600, R100 = "#7FA597", "#2C5C4C", "#DCE7E2"
LAKE, CLAY, JADE, VIOLET = "#2B6FBF", "#D35C2A", "#12997A", "#6550CC"
BANDA = (15 / 255, 46 / 255, 37 / 255, 0.14)
DIR_FUENTES = C.RAIZ / "experimentos" / "v5" / "fuentes"
NOMBRES = {"pts_p100": "Pts/100", "ts_pct": "TS%", "efg_pct": "eFG%", "fg2_pct": "T2%", "fg3_pct": "T3%", "ft_pct": "TL%",
           "fg3a_rate": "3PAr", "fta_rate": "FTr", "usg_pct": "USG%", "ast_pct": "AST%", "tov_pct": "TOV%",
           "oreb_pct": "OREB%", "dreb_pct": "DREB%", "oreb_p100": "OREB/100", "dreb_p100": "DREB/100",
           "stl_pct": "STL%", "blk_pct": "BLK%", "stl_p100": "STL/100", "blk_p100": "BLK/100", "pf_p100": "Faltas/100",
           "drtg": "DRtg", "per": "PER", "ortg": "ORtg", "game_score_p40": "GmSc/40", "ws_per_40": "WS/40",
           "pct_aro": "% aro", "pct_corta": "% corta", "pct_media": "% media", "pct_t3_esquina": "% T3 esquina",
           "pct_asistidas": "% asistidas", "rapm": "RAPM", "orapm": "ORAPM", "drapm": "DRAPM"}


def _fuentes():
    """Instancias estáticas de Mona Sans (420, 620) y Geist Mono (450) para matplotlib."""
    import matplotlib.font_manager as fm
    if not (DIR_FUENTES / "MonaSans-420.ttf").exists():
        from fontTools.ttLib import TTFont
        from fontTools.varLib.instancer import instantiateVariableFont
        DIR_FUENTES.mkdir(parents=True, exist_ok=True)
        src = C.RAIZ / "cerno_articulo" / "recursos" / "fonts"
        for nombre, f, pesos in (("MonaSans", "MonaSans-Variable.woff2", (420, 620)),
                                 ("GeistMono", "GeistMono-Variable.woff2", (450, 500))):
            for w in pesos:
                t = TTFont(src / f)
                t.flavor = None
                loc = {"wght": w, **({"wdth": 96} if "wdth" in {a.axisTag for a in t["fvar"].axes} else {})}
                inst = instantiateVariableFont(t, loc)
                for rec in inst["name"].names:
                    if rec.nameID in (1, 4, 16):
                        rec.string = f"{nombre} {w}"
                inst.save(DIR_FUENTES / f"{nombre}-{w}.ttf")
    for p in DIR_FUENTES.glob("*.ttf"):
        fm.fontManager.addfont(str(p))
    return {"texto": "MonaSans 420", "titulo": "MonaSans 620", "dato": "GeistMono 450"}


def estilo():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    F = _fuentes()
    plt.rcParams.update({
        "font.family": F["texto"], "font.size": 9.5, "axes.titlesize": 12.5, "axes.titleweight": "normal",
        "figure.facecolor": CHALK, "axes.facecolor": CHALK, "savefig.facecolor": CHALK,
        "axes.edgecolor": S300, "axes.labelcolor": S600, "xtick.color": S600, "ytick.color": S700,
        "axes.grid": True, "grid.color": S200, "grid.linewidth": 0.6, "axes.axisbelow": True,
        "axes.spines.top": False, "axes.spines.right": False, "text.color": INK, "legend.frameon": False})
    return plt, F


def _cabecera(fig, ax, F, titulo: str, sub: str, pie: str):
    fig.text(0.012, 0.975, titulo, fontfamily=F["titulo"], fontsize=13, color=INK, va="top")
    fig.text(0.012, 0.925, sub.upper(), fontfamily=F["dato"], fontsize=7.5, color=S600, va="top")
    fig.text(0.012, 0.012, pie, fontfamily=F["dato"], fontsize=6.8, color=S600, va="bottom")
    for lab in ax.get_xticklabels():
        lab.set_fontfamily(F["dato"])


def _guardar(fig, nombre: str, cfg: dict):
    d = C.RAIZ / "docs" / "v5" / "figuras"
    d.mkdir(parents=True, exist_ok=True)
    fig.savefig(d / f"{nombre}.png", dpi=160)
    import matplotlib.pyplot as plt
    plt.close(fig)
    return d / f"{nombre}.png"


PIE = "Datos públicos · 20 ligas, temporada regular 2020-21 a 2025-26 · Kerno Analytics · v5.0 F1"


# --------------------------------------------------------------------------------------------- §5.1 varianza
def fig_varianza(cfg):
    plt, F = estilo()
    comp = pd.read_csv(C.dir_fase(cfg) / "varianza" / "componentes.csv")
    comp = comp.sort_values("prop_ruido_muestra")
    partes = [("prop_jugador", "Jugador (estable)", RACING), ("prop_temporada_jugador", "Jugador × temporada", R300),
              ("prop_liga_temporada", "Liga × temporada", S300), ("prop_ruido_muestra", "Ruido de muestra", CLAY)]
    fig, ax = plt.subplots(figsize=(9.2, 9.6))
    fig.subplots_adjust(left=0.16, right=0.97, top=0.86, bottom=0.08)
    y = np.arange(len(comp))
    izq = np.zeros(len(comp))
    for col, et, colr in partes:
        ax.barh(y, comp[col], left=izq, color=colr, height=0.72, label=et)
        izq += comp[col].to_numpy()
    ax.set_yticks(y, [NOMBRES.get(m, m) for m in comp["metrica"]])
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(lambda v, p: f"{v * 100:.0f} %")
    ax.legend(loc="lower center", bbox_to_anchor=(0.45, 1.0), ncol=4, fontsize=8.2)
    peor = comp.iloc[-1]
    _cabecera(fig, ax, F, f"En {(comp['prop_ruido_muestra'] > 0.25).sum()} de {len(comp)} métricas el ruido de muestra "
                          f"supera el 25 % de la varianza de una temporada",
              "Proporción de la varianza por componente · REML · exposición media de cada métrica", PIE)
    return _guardar(fig, "f1_descomposicion_varianza", cfg)


def fig_estabilizacion(cfg):
    plt, F = estilo()
    comp = pd.read_csv(C.dir_fase(cfg) / "varianza" / "componentes.csv").set_index("metrica")
    div = pd.read_csv(C.dir_fase(cfg) / "varianza" / "division_muestra.csv").set_index("metrica")
    m = [x for x in div.index if x in comp.index]
    m = sorted(m, key=lambda x: comp.loc[x, "n_estab_temp"])
    fig, ax = plt.subplots(figsize=(9.2, 5.4))
    fig.subplots_adjust(left=0.21, right=0.97, top=0.83, bottom=0.14)
    y = np.arange(len(m))
    lo, hi = div.loc[m, "n_estab_momentos_lo80"], div.loc[m, "n_estab_momentos_hi80"]
    ax.hlines(y - 0.15, lo, hi, color=BANDA, linewidth=7)
    ax.plot(div.loc[m, "n_estab_momentos"], y - 0.15, "o", color=S500, ms=5, label="División de muestra (momentos) · rango 80 %")
    ax.plot(comp.loc[m, "n_estab_temp"], y + 0.15, "o", color=RACING, ms=6, label="Componentes de varianza (REML)")
    ax.set_xscale("log")
    ax.set_xticks([5, 10, 20, 50, 100, 200, 500])
    ax.xaxis.set_major_formatter(lambda v, p: f"{v:.0f}")
    ax.xaxis.set_minor_formatter(lambda v, p: "")
    ax.set_yticks(y, [f"{NOMBRES.get(x, x)} · {div.loc[x, 'unidad_exposicion']}" for x in m])
    ax.legend(loc="lower right", fontsize=8)
    ax.set_xlabel("Exposición con fiabilidad 0,5 (n*), escala logarítmica")
    _cabecera(fig, ax, F, "Los dos métodos coinciden en el orden: el uso del triple se lee en 7 tiros; el T3% necesita cientos",
              "Punto de estabilización n* de una temporada · unidades de exposición propias de cada métrica", PIE)
    return _guardar(fig, "f1_estabilizacion", cfg)


# --------------------------------------------------------------------------------------------- §5.2 incertidumbre
def fig_incertidumbre(cfg):
    plt, F = estilo()
    r = pd.read_csv(C.dir_fase(cfg) / "incertidumbre" / "descomposicion_metrica.csv").set_index("metrica")
    r = r.sort_values("frac_temporada")
    fig, ax = plt.subplots(figsize=(9.2, 9.0))
    fig.subplots_adjust(left=0.16, right=0.97, top=0.86, bottom=0.08)
    y = np.arange(len(r))
    izq = np.zeros(len(r))
    for col, et, colr in (("frac_jugador", "Nivel del jugador", RACING), ("frac_traduccion", "Factor de traducción", LAKE),
                          ("frac_temporada", "Residual de temporada (contexto, muestra y cambio)", CLAY)):
        ax.barh(y, r[col], left=izq, color=colr, height=0.72, label=et)
        izq += r[col].to_numpy()
    ax.set_yticks(y, [NOMBRES.get(m, m) for m in r.index])
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(lambda v, p: f"{v * 100:.0f} %")
    ax.legend(loc="lower center", bbox_to_anchor=(0.45, 1.0), ncol=3, fontsize=8.2)
    med = r["frac_traduccion"].median()
    _cabecera(fig, ax, F, f"El factor de traducción es sólo el {med * 100:.0f} % de la varianza predictiva (mediana)",
              "Fracción de la varianza predictiva de la temporada siguiente · v3.2 · 2025-26 · mediana por pares de ligas", PIE)
    return _guardar(fig, "f1_descomposicion_incertidumbre", cfg)


# --------------------------------------------------------------------------------------------- §5.3 calibración
def fig_fiabilidad(cfg):
    plt, F = estilo()
    mv = pd.read_csv(C.dir_fase(cfg) / "calibracion" / "movimientos_resumen.csv")
    hi = pd.read_csv(C.dir_fase(cfg) / "calibracion" / "historial_resumen.csv")
    g = pd.concat([mv[mv["por"] == "global"], hi[hi["por"] == "global"]]).set_index("modelo")
    series = [("v3.2 publicada (predictiva recalibrada)", "v3.2 · examen de cambios de liga (recalibrada)", RACING, "o"),
              ("v3.2 sin recalibrar", "v3.2 · sin recalibrar", R300, "o"),
              ("v2 = A+B amortiguado (intervalo F0, de nivel)", "v1/v2 · A+B amortiguado (F0)", S500, "s"),
              ("v4.2 D1 (Kalman)", "v4.2 D1 · historial (Kalman)", LAKE, "D"),
              ("v3.2 publicada (nivel t ⊕ nivel t+1)", "v3.2 · intervalo publicado (nivel t y t+1)", CLAY, "^")]
    nom = np.array([0.5, 0.8, 0.95])
    fig, ax = plt.subplots(figsize=(7.6, 6.4))
    fig.subplots_adjust(left=0.12, right=0.97, top=0.84, bottom=0.12)
    ax.plot([0.4, 1], [0.4, 1], color=S400, lw=1, ls="--")
    ax.fill_between([0.76, 0.84], [0.76, 0.76], [0.84, 0.84], color=BANDA)
    for k, et, c, mk in series:
        if k in g.index:
            emp = g.loc[k, ["cob50", "cob80", "cob95"]].to_numpy(float)
            ax.plot(nom, emp, marker=mk, color=c, lw=1.6, ms=6, label=et)
    ax.set_xlim(0.4, 1.0)
    ax.set_ylim(0.4, 1.0)
    ax.set_xlabel("Cobertura nominal")
    ax.set_ylabel("Cobertura empírica")
    ax.legend(loc="lower right", fontsize=7.8)
    c = g.loc["v3.2 publicada (nivel t ⊕ nivel t+1)", "cob80"] if "v3.2 publicada (nivel t ⊕ nivel t+1)" in g.index else np.nan
    _cabecera(fig, ax, F, f"Los predictivos están calibrados; el {c * 100:.0f} % del intervalo publicado no prueba que sea ancho",
              "Fiabilidad · fuera de tiempo, cortes 2022–2024 · recuadro: objetivo 76–84 % · ver la simulación del §4.3", PIE)
    return _guardar(fig, "f1_fiabilidad", cfg)


def fig_cob80_metrica(cfg):
    plt, F = estilo()
    mv = pd.read_csv(C.dir_fase(cfg) / "calibracion" / "movimientos_resumen.csv")
    hi = pd.read_csv(C.dir_fase(cfg) / "calibracion" / "historial_resumen.csv")
    a = mv[(mv["por"] == "metrica") & (mv["modelo"] == "v3.2 publicada (predictiva recalibrada)")].set_index("grupo")["cob80"]
    b = hi[(hi["por"] == "metrica") & (hi["modelo"] == "v3.2 publicada (nivel t ⊕ nivel t+1)")].set_index("grupo")["cob80"]
    c4 = hi[(hi["por"] == "metrica") & (hi["modelo"] == "v4.2 D1 (Kalman)")].set_index("grupo")["cob80"]
    m = sorted(set(a.index) | set(b.index), key=lambda x: b.get(x, a.get(x, 0)))
    fig, ax = plt.subplots(figsize=(9.2, 9.0))
    fig.subplots_adjust(left=0.16, right=0.97, top=0.88, bottom=0.08)
    y = np.arange(len(m))
    ax.axvspan(0.72, 0.88, color=BANDA)
    ax.axvline(0.8, color=S400, lw=1, ls="--")
    ax.plot([a.get(x, np.nan) for x in m], y, "o", color=RACING, ms=5.5, label="v3.2 · examen de cambios de liga (predictiva recalibrada)")
    ax.plot([c4.get(x, np.nan) for x in m], y, "D", color=LAKE, ms=4.5, label="v4.2 D1 · historial")
    ax.plot([b.get(x, np.nan) for x in m], y, "^", color=CLAY, ms=5.5, label="v3.2 · intervalo publicado (nivel t y t+1)")
    ax.set_yticks(y, [NOMBRES.get(x, x) for x in m])
    ax.set_xlim(0.55, 1.0)
    ax.xaxis.set_major_formatter(lambda v, p: f"{v * 100:.0f} %")
    ax.legend(loc="lower left", fontsize=8)
    n_inf = int((b > 0.88).sum())
    _cabecera(fig, ax, F, f"El intervalo publicado sobrecubre en {n_inf} de {len(b)} métricas; en parte es mecánico (§4.3)",
              "Cobertura empírica del intervalo nominal del 80 % · banda: 72–88 % (regla de interpretación §5.3)", PIE)
    return _guardar(fig, "f1_cobertura80_metrica", cfg)


def fig_pit(cfg):
    plt, F = estilo()
    p = pd.read_csv(C.dir_fase(cfg) / "calibracion" / "movimientos_pit.csv.gz")
    fig, axs = plt.subplots(1, 3, figsize=(10.2, 3.9), sharey=True)
    fig.subplots_adjust(left=0.07, right=0.98, top=0.70, bottom=0.17, wspace=0.08)
    for ax, col, et in zip(axs, ("pit_v32", "pit_v32_sin_recal", "pit_v2"),
                           ("v3.2 recalibrada", "v3.2 sin recalibrar", "v1/v2 · A+B amortiguado (F0)")):
        x = p[col].dropna()
        ax.hist(x, bins=np.linspace(0, 1, 11), weights=np.full(len(x), 10 / len(x)), color=RACING, edgecolor=CHALK)
        ax.axhline(1.0, color=S500, lw=1, ls="--")
        ax.set_title(et, fontsize=9.5, color=INK, loc="left", fontfamily=F["titulo"])
        ax.set_xlabel("PIT")
    axs[0].set_ylabel("Densidad (uniforme = 1)")
    _cabecera(fig, axs[0], F, "Sin recalibrar, la v3.2 es algo ancha; la v1/v2 además se queda corta (sesgo)",
              "Histograma PIT · examen fuera de tiempo, cambios de liga, cortes 2022–2024 · 33 métricas", PIE)
    return _guardar(fig, "f1_pit", cfg)


# --------------------------------------------------------------------------------------------- §5.4 nivel
def fig_nivel(cfg):
    plt, F = estilo()
    r = pd.read_csv(C.dir_fase(cfg) / "nivel" / "nivel_frente_publicado.csv").set_index("metrica")
    r = r.sort_values("razon_1temp")
    fig, ax = plt.subplots(figsize=(9.2, 8.6))
    fig.subplots_adjust(left=0.16, right=0.97, top=0.86, bottom=0.09)
    y = np.arange(len(r))
    ax.axvline(1.0, color=S400, lw=1, ls="--")
    ax.hlines(y, r["razon_historial"], r["razon_1temp"], color=BANDA, lw=6)
    ax.plot(r["razon_1temp"], y, "o", color=RACING, ms=6, label="Credibilidad con una temporada")
    ax.plot(r["razon_historial"], y, "D", color=LAKE, ms=5, label="Credibilidad con su historial hasta t")
    ax.set_yticks(y, [NOMBRES.get(m, m) for m in r.index])
    ax.set_xlabel("DT de credibilidad del nivel / DT propia publicada (v3.2)")
    ax.legend(loc="lower center", bbox_to_anchor=(0.45, 1.0), ncol=2, fontsize=8.2)
    n_mas = int((r["razon_1temp"] > 1).sum())
    _cabecera(fig, ax, F, f"En {n_mas} de {len(r)} métricas la DT publicada ya es más estrecha que la de una métrica aislada",
              "DT de credibilidad del nivel (componentes de varianza) / DT propia publicada (v3.2) · 2025-26 · 300+ minutos", PIE)
    return _guardar(fig, "f1_nivel_frente_publicado", cfg)


def todas(cfg):
    rutas = []
    for f in (fig_varianza, fig_estabilizacion, fig_incertidumbre, fig_fiabilidad, fig_cob80_metrica, fig_pit, fig_nivel):
        try:
            rutas.append(f(cfg))
            print(f"  {rutas[-1].relative_to(C.RAIZ)}", flush=True)
        except FileNotFoundError as e:
            print(f"  {f.__name__}: falta {e.filename}", flush=True)
    return rutas
