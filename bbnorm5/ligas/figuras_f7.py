"""F7 · Figuras del informe 07_seleccion_paso2 (marca Kerno v2.0)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from bbnorm5 import config as C
from bbnorm5.diagnostico.figuras import CLAY, LAKE, RACING, S400, _cabecera, _guardar, estilo
from bbnorm5.medida.figuras import NOM

PIE = "Datos públicos · 20 ligas, temporada regular 2020-21 a 2025-26 · Kerno Analytics · v5.0 F7"
DIR = C.DIR_DATOS / "ligas"
ETQ = {"paso1": "Sólo puentes de la misma temporada", "crudo": "+ traspasos, temporada previa en bruto",
       "encogido": "+ traspasos, nivel encogido (F4)", "encogido_ipw": "+ encogido + IPW",
       "encogido_heckman": "+ encogido + Heckman"}


def fig_sesgo(cfg):
    plt, F = estilo()
    c = pd.read_parquet(DIR / "seleccion_casos.parquet", columns=["variante", "direccion", "persona_v5", "z"])
    fig, ax = plt.subplots(figsize=(9.0, 5.0))
    fig.subplots_adjust(left=0.33, right=0.97, top=0.80, bottom=0.13)
    vs = list(ETQ)
    y = np.arange(len(vs))[::-1]
    for d, col, off in (("sube", RACING, 0.15), ("baja", CLAY, -0.15)):
        for yi, v in zip(y, vs):
            x = c[(c["variante"] == v) & (c["direccion"] == d)]
            g = x.groupby("persona_v5")["z"].mean()
            m, ee = x["z"].mean(), g.std() / np.sqrt(len(g))
            ax.hlines(yi + off, m - 1.96 * ee, m + 1.96 * ee, color=col, lw=3, alpha=0.4)
            ax.plot(m, yi + off, "o", color=col, ms=6, label=("Sube de liga" if d == "sube" else "Baja de liga") if yi == y[0] else None)
    ax.axvline(0, color=S400, lw=1)
    ax.set_yticks(y, [ETQ[v] for v in vs])
    ax.set_xlabel("Residuo medio de la temporada tras el traspaso (en DT predictivas; IC 95 %)")
    ax.legend(loc="lower right", fontsize=8)
    ax.xaxis.set_major_formatter(lambda v, p: f"{v:+.3f}".replace(".", ","))
    _cabecera(fig, ax, F, "El sesgo por traspaso es pequeño (< 0,1 DT); el nivel encogido lo reduce y Heckman lo anula al subir",
              "Cambios de liga 2023-24 a 2025-26 · positivo: rinde más de lo previsto", PIE)
    return _guardar(fig, "f7_sesgo_direccion", cfg)


def fig_precision(cfg):
    plt, F = estilo()
    l = pd.read_csv(DIR / "lambda_paso2.csv")
    l = l[l["corte"] == l["corte"].max()]
    a = l[l["variante"] == "paso1"].set_index(["metrica", "liga"])["sd"]
    b = l[l["variante"] == "encogido"].set_index(["metrica", "liga"])["sd"]
    r = (b / a).replace([np.inf], np.nan).dropna().groupby(level="liga").median().sort_values()
    fig, ax = plt.subplots(figsize=(8.6, 5.6))
    fig.subplots_adjust(left=0.15, right=0.97, top=0.82, bottom=0.11)
    yy = np.arange(len(r))
    ax.barh(yy, r.values, color=[RACING if v < 0.5 else LAKE for v in r.values], height=0.6)
    ax.set_yticks(yy, r.index)
    ax.axvline(1, color=S400, lw=1)
    ax.xaxis.set_major_formatter(lambda v, p: f"{v:.1f}".replace(".", ","))
    ax.set_xlabel("DT del efecto de liga con traspasos ÷ DT sólo con puentes de la misma temporada (mediana de las 14 métricas)")
    _cabecera(fig, ax, F, "Los traspasos entre temporadas identifican a la NCAA y a las FEB",
              "Precisión del efecto de liga · paso 2 (encogido) frente al paso 1 · corte 2025-26", PIE)
    return _guardar(fig, "f7_precision_ligas", cfg)


def fig_traduccion(cfg):
    """Traducción desde la ACB (2025-26): paso 1 (F6.1) frente a paso 2 (F7, publicada), media y rango del 80 %."""
    plt, F = estilo()
    t2 = pd.read_csv(DIR / "traduccion_acb_legible_paso2_2025-26.csv")
    t1 = pd.read_csv(DIR / "traduccion_acb_legible_2025-26.csv")
    mets = ["pts_p100", "usg_pct", "ast_pct", "dreb_pct"]
    orden = t2[t2["metrica"] == "pts_p100"].sort_values("media")["hacia"].tolist()
    fig, axs = plt.subplots(1, 4, figsize=(11.0, 5.8), sharey=True)
    fig.subplots_adjust(left=0.11, right=0.98, top=0.80, bottom=0.11, wspace=0.08)
    y = np.arange(len(orden))
    for ax, m in zip(axs, mets):
        ax.axvline(0, color=S400, lw=1)
        for t, col, off, et in ((t1, S400, -0.17, "Paso 1 · puentes de la misma temporada"),
                                (t2, RACING, 0.17, "Paso 2 · + traspasos (publicada)")):
            x = t[t["metrica"] == m].set_index("hacia").reindex(orden)
            ax.hlines(y + off, x["q10"], x["q90"], color=col, lw=3, alpha=0.4)
            ax.plot(x["media"], y + off, "o", color=col, ms=4.5, label=et if m == mets[-1] else None)
        ax.set_title(NOM[m] + " (puntos)", fontsize=9.5, loc="left", fontfamily=F["titulo"])
        ax.xaxis.set_major_formatter(lambda v, p: f"{v:+.0f}")
    axs[0].set_yticks(y, orden)
    axs[3].legend(loc="lower right", fontsize=7.5)
    _cabecera(fig, axs[0], F, "Con los traspasos, la NCAA y las FEB dejan de ser una incógnita",
              "Efecto de pasar de la ACB a cada competición · 2025-26 · media y rango del 80 % · NUTS, bloques reagrupados", PIE)
    return _guardar(fig, "f7_traduccion_paso2", cfg)


def todas(cfg) -> dict:
    return {"figuras": [str(f.relative_to(C.RAIZ)) for f in (fig_sesgo(cfg), fig_precision(cfg), fig_traduccion(cfg))]}
