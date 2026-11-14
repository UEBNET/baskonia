"""F4 · Figuras del informe 04_capa_carrera (marca Kerno v2.0)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from bbnorm5 import config as C
from bbnorm5.carrera import datos as CD
from bbnorm5.diagnostico.figuras import (BANDA, CHALK, CLAY, INK, LAKE, RACING, R300, S300, S400, S500, _cabecera,
                                         _guardar, estilo)
from bbnorm5.medida.figuras import NOM

PIE = "Datos públicos · 20 ligas, temporada regular 2020-21 a 2025-26 · Kerno Analytics · v5.0 F4"
ETQ = {"solo_ultima": "Sólo la última temporada, sin cambio", "deriva": "Historial · paseo aleatorio con la deriva de la F3",
       "d1": "Historial · estructura de la v4.2 D1", "completo": "Historial · modelo de carrera completo"}


def _elegido() -> str:
    s = pd.read_csv(CD.DIR / "seleccion.csv", index_col=0)
    return s.index[s["elegido"]][0]


def fig_cobertura(cfg):
    plt, F = estilo()
    r = pd.read_csv(CD.DIR / "examen_por_metrica.csv")
    el = _elegido()
    mods = [("solo_ultima", "o", S400, 5), ("deriva", "s", CLAY, 5), ("d1", "D", LAKE, 4.5), (el, "o", RACING, 6.5)]
    p = r.pivot(index="metrica", columns="modelo", values="cob80")
    orden = p[el].sort_values().index.tolist()
    fig, ax = plt.subplots(figsize=(9.2, 6.6))
    fig.subplots_adjust(left=0.13, right=0.97, top=0.86, bottom=0.10)
    y = np.arange(len(orden))
    ax.axvspan(0.76, 0.84, color=BANDA)
    ax.axvline(0.8, color=S400, lw=1, ls="--")
    for m, mk, col, ms in mods:
        ax.plot(p.loc[orden, m], y, mk, color=col, ms=ms, label=ETQ.get(m, f"Historial · {m} (elegido)") +
                (" (elegido)" if m == el and m in ETQ else ""))
    ax.set_yticks(y, [NOM[m] for m in orden])
    ax.set_xlim(0.45, 0.95)
    ax.xaxis.set_major_formatter(lambda v, p: f"{v * 100:.0f} %")
    ax.legend(loc="lower left", fontsize=7.8)
    dentro = int(((p[el] >= 0.76) & (p[el] <= 0.84)).sum())
    _cabecera(fig, ax, F, f"Con el historial y el cambio aprendido, {dentro} de {len(p)} métricas cubren el 76–84 %",
              "Cobertura del 80 % · producción de la temporada siguiente · examen fuera de tiempo 2023-24 a 2025-26", PIE)
    return _guardar(fig, "f4_cobertura80", cfg)


def fig_historial(cfg):
    plt, F = estilo()
    g = pd.read_csv(CD.DIR / "examen_por_historial.csv")
    el = _elegido()
    g = g[g["modelo"] == el]
    mets = ["t3_pct", "tl_pct", "ast_pct", "dreb_pct", "usg_pct", "pts_p100"]
    fig, axs = plt.subplots(1, 2, figsize=(10.2, 5.4))
    fig.subplots_adjust(left=0.07, right=0.98, top=0.80, bottom=0.17, wspace=0.25)
    cols = [RACING, R300, LAKE, CLAY, S500, INK]
    for m, c in zip(mets, cols):
        x = g[g["metrica"] == m].sort_values("hist")
        rel = x["ancho_nivel80"] / x["ancho_nivel80"].iloc[0]
        axs[0].plot(x["hist"].astype(str), rel, "o-", color=c, ms=4, label=NOM[m])
        axs[1].plot(x["hist"].astype(str), x["cob80"], "o-", color=c, ms=4, label=NOM[m])
    axs[0].set_title("Anchura del intervalo del nivel (1 temporada = 1)", fontsize=9.5, loc="left", fontfamily=F["titulo"])
    axs[1].set_title("Cobertura del 80 % de la producción", fontsize=9.5, loc="left", fontfamily=F["titulo"])
    axs[1].axhspan(0.76, 0.84, color=BANDA)
    axs[1].set_ylim(0.6, 1.0)
    axs[1].yaxis.set_major_formatter(lambda v, p: f"{v * 100:.0f} %")
    for ax in axs:
        ax.set_xlabel("Temporadas de historial")
    axs[0].legend(fontsize=7.5, ncol=2)
    _cabecera(fig, axs[0], F, "Cuanto más historial, más estrecho el nivel, y la cobertura se mantiene",
              "Modelo de carrera elegido · examen fuera de tiempo 2023-24 a 2025-26", PIE)
    return _guardar(fig, "f4_historial", cfg)


def fig_pesos(cfg):
    plt, F = estilo()
    w = pd.read_csv(CD.DIR / "pesos_temporadas.csv")
    w = w[w["escenario"] == "misma liga y rol"]
    mets = w.sort_values("peso_prior")["metrica"].tolist()
    fig, ax = plt.subplots(figsize=(9.2, 6.8))
    fig.subplots_adjust(left=0.13, right=0.97, top=0.80, bottom=0.08)
    cols = {"t-4": S300, "t-3": R300, "t-2": LAKE, "t-1": RACING, "prior": "#E5E7E2"}
    izq = np.zeros(len(mets))
    for k in ("t-1", "t-2", "t-3", "t-4", "prior"):
        col = "peso_prior" if k == "prior" else f"peso_{k}"
        v = w.set_index("metrica").loc[mets, col].to_numpy()
        ax.barh(np.arange(len(mets)), v, left=izq, color=cols[k], edgecolor=CHALK,
                label={"prior": "Media del rol en la liga", "t-1": "Última temporada"}.get(k, f"Temporada {k}"))
        izq += v
    ax.set_yticks(np.arange(len(mets)), [NOM[m] for m in mets])
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(lambda v, p: f"{v * 100:.0f} %")
    ax.legend(loc="lower left", fontsize=7.5, ncol=5, bbox_to_anchor=(0.0, 1.0), frameon=False)
    ax.grid(False)
    _cabecera(fig, ax, F, "Cuánto pesa cada temporada pasada en la proyección de la siguiente",
              "Jugador tipo con 4 temporadas de exposición mediana en la misma liga y rol · pesos aprendidos", PIE)
    return _guardar(fig, "f4_pesos_temporadas", cfg)


def fig_edad(cfg):
    f = CD.DIR / "curvas_edad.csv"
    if not f.exists():
        return None
    plt, F = estilo()
    c = pd.read_csv(f)
    c = c[c["rol"] == "todos"]
    mets = ["t3_pct", "tl_pct", "ast_pct", "oreb_pct", "blk_pct", "stl_p100"]
    fig, axs = plt.subplots(2, 3, figsize=(10.2, 6.0), sharex=True)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.83, bottom=0.13, wspace=0.22, hspace=0.35)
    for ax, m in zip(axs.flat, mets):
        x = c[c["metrica"] == m]
        if x.empty:
            continue
        ax.fill_between(x["edad"], x["lo80"], x["hi80"], color=BANDA, lw=0)
        ax.plot(x["edad"], x["g"], color=RACING, lw=1.8)
        ax.axhline(0, color=S400, lw=0.8)
        ax.set_title(NOM[m], fontsize=9.5, loc="left", fontfamily=F["titulo"])
    for ax in axs[1]:
        ax.set_xlabel("Edad")
    for ax in axs[:, 0]:
        ax.set_ylabel("g(edad) − g(26), escala del enlace")
    _cabecera(fig, axs[0, 0], F, "Curvas de edad: el atletismo cae antes que la puntería",
              "Efecto de la edad en la capacidad relativa (banda del 80 %) · B-spline penalizado", PIE)
    return _guardar(fig, "f4_curvas_edad", cfg)


def todas(cfg) -> dict:
    fs = [fig_cobertura(cfg), fig_historial(cfg), fig_pesos(cfg), fig_edad(cfg)]
    return {"figuras": [str(f.relative_to(C.RAIZ)) for f in fs if f is not None]}
