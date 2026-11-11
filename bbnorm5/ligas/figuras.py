"""F6 · Figuras del informe 06_ligas_contexto (marca Kerno v2.0)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from bbnorm5 import config as C
from bbnorm5.diagnostico.figuras import BANDA, CLAY, INK, LAKE, RACING, S400, _cabecera, _guardar, estilo
from bbnorm5.medida.figuras import NOM

PIE = "Datos públicos · 20 ligas, temporada regular 2020-21 a 2025-26 · Kerno Analytics · v5.0 F6"
DIR = C.DIR_DATOS / "ligas"


def fig_traduccion(cfg):
    plt, F = estilo()
    t = pd.read_csv(DIR / "traduccion_acb_legible_2025-26.csv")
    mets = ["pts_p100", "usg_pct", "ast_pct", "dreb_pct"]
    orden = t[t["metrica"] == "pts_p100"].sort_values("media")["hacia"].tolist()
    fig, axs = plt.subplots(1, 4, figsize=(11.0, 5.8), sharey=True)
    fig.subplots_adjust(left=0.11, right=0.98, top=0.80, bottom=0.11, wspace=0.08)
    y = np.arange(len(orden))
    for ax, m in zip(axs, mets):
        x = t[t["metrica"] == m].set_index("hacia").loc[orden]
        ax.axvline(0, color=S400, lw=1)
        ax.hlines(y, x["q10"], x["q90"], color=RACING, lw=3, alpha=0.35)
        ax.plot(x["media"], y, "o", color=RACING, ms=5)
        ax.set_title(NOM[m] + " (puntos)", fontsize=9.5, loc="left", fontfamily=F["titulo"])
        ax.xaxis.set_major_formatter(lambda v, p: f"{v:+.0f}")
    axs[0].set_yticks(y, orden)
    _cabecera(fig, axs[0], F, "Qué le pasa al mismo jugador al pasar de la ACB a otra competición",
              "Efecto de liga (puentes intra-temporada, NUTS) · 2025-26 · media y rango del 80 % · en la tasa media de la ACB", PIE)
    return _guardar(fig, "f6_traduccion_desde_acb", cfg)


def fig_grafo(cfg):
    plt, F = estilo()
    g = pd.read_csv(DIR / "grafo_diagnostico.csv")
    g = g[g["liga"] != "acb"]
    fig, ax = plt.subplots(figsize=(8.6, 5.4))
    fig.subplots_adjust(left=0.11, right=0.97, top=0.82, bottom=0.13)
    ax.scatter(g["puentes"], g["ancho80_lambda_std"], s=40, color=RACING)
    for _, r in g.iterrows():
        ax.annotate(r["liga"], (r["puentes"], r["ancho80_lambda_std"]), xytext=(4, 3), textcoords="offset points",
                    fontsize=7.5, color=INK, fontfamily=F["dato"])
    ax.set_xscale("log")
    ax.set_xlabel("Puentes intra-temporada (escala log)")
    ax.set_ylabel("Anchura del 80 % del efecto de liga (DT de las diferencias)")
    ax.set_xticks([5, 10, 20, 50, 100, 200, 500, 1000])
    ax.xaxis.set_major_formatter(lambda v, p: f"{v:.0f}".replace("1000", "1.000"))
    ax.xaxis.set_minor_formatter(lambda v, p: "")
    _cabecera(fig, ax, F, "NCAA, las FEB, la CBA y la NBL apenas tienen puentes en la misma temporada",
              "Anchura del efecto de liga frente al número de puentes · mediana de las 14 métricas · 2025-26", PIE)
    return _guardar(fig, "f6_grafo_anchura", cfg)


def fig_navaja(cfg):
    plt, F = estilo()
    n = pd.read_csv(DIR / "navaja_contexto.csv")
    sel = [("liga", "base_F4", "Traducción entre ligas (completa)"), ("liga+peso", "base_F4", "Traducción con peso aprendido"),
           ("liga+volumen", "liga", "+ volumen–eficiencia"), ("liga+companeros", "liga", "+ estilo de compañeros"),
           ("liga+tipo", "liga", "+ tipo de jugador × cambio de liga"), ("liga+estilo_liga", "liga", "+ estilo de liga × tipo"),
           ("liga+peso+todos+recal", "base_F4", "Modelo final frente a la F4")]
    fig, axs = plt.subplots(1, 2, figsize=(10.4, 5.0), sharey=True)
    fig.subplots_adjust(left=0.30, right=0.98, top=0.80, bottom=0.13, wspace=0.06)
    y = np.arange(len(sel))[::-1]
    for ax, sub in zip(axs, ("todos", "cambio de liga")):
        x = n[n["casos"] == sub].set_index(["modelo", "frente_a"])
        for yi, (m, f, et) in zip(y, sel):
            r = x.loc[(m, f)]
            col = RACING if r["supera_navaja"] else S400
            ax.hlines(yi, -r["ic95_hi"] * 100, -r["ic95_lo"] * 100, color=col, lw=3, alpha=0.5)
            ax.plot(-r["dif_crps_rel"] * 100, yi, "o", color=col, ms=6)
        ax.axvline(0, color=CLAY, lw=1)
        ax.set_title("Todas las predicciones" if sub == "todos" else "Sólo cambios de liga", fontsize=9.5, loc="left",
                     fontfamily=F["titulo"])
        ax.xaxis.set_major_formatter(lambda v, p: f"{v:.1f} %".replace(".", ","))
        ax.set_xlabel("Reducción del CRPS (IC 95 %)")
    axs[0].set_yticks(y, [s[2] for s in sel])
    _cabecera(fig, axs[0], F, "Todos los bloques superan la navaja en conjunto; el modelo final reduce un 7,5 % el error al cambiar de liga",
              "Examen fuera de tiempo 2024-25 y 2025-26 · bloques frente a la traducción sola; final frente a la F4", PIE)
    return _guardar(fig, "f6_navaja", cfg)


def todas(cfg) -> dict:
    return {"figuras": [str(f.relative_to(C.RAIZ)) for f in (fig_traduccion(cfg), fig_grafo(cfg), fig_navaja(cfg))]}
