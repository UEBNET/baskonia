"""F5 · Figuras del informe 05_capa_latente (marca Kerno v2.0)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from bbnorm5 import config as C
from bbnorm5.diagnostico.figuras import BANDA, CHALK, CLAY, INK, LAKE, RACING, S400, _cabecera, _guardar, estilo
from bbnorm5.medida.figuras import NOM

PIE = "Datos públicos · 20 ligas, temporada regular 2020-21 a 2025-26 · Kerno Analytics · v5.0 F5"


def _dir():
    from bbnorm5.f5 import DIR
    return DIR


def fig_seleccion(cfg):
    plt, F = estilo()
    s = pd.read_csv(_dir() / "seleccion_k.csv", index_col=0)
    s["K"] = s.index.str.extract(r"K(\d+)_")[0].astype(int).to_numpy()
    s = s.sort_values("K")
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    fig.subplots_adjust(left=0.11, right=0.97, top=0.78, bottom=0.14)
    ax.errorbar(s["K"], s["rel"], yerr=s["ee"], fmt="o-", color=RACING, ms=6, capsize=3)
    el = s[s["elegido"]]
    ax.plot(el["K"], el["rel"], "o", ms=12, mfc="none", mec=CLAY, mew=2)
    ax.set_xticks(s["K"])
    ax.set_xlabel("Número de factores K (0 = métricas independientes, como la F4)")
    ax.set_ylabel("CRPS relativo a K = 0")
    ax.yaxis.set_major_formatter(lambda v, p: f"{v:.3f}".replace(".", ","))
    _cabecera(fig, ax, F, f"Compartir información entre métricas reduce el error; se elige K = {int(el['K'].iloc[0])}",
              "Selección de K · corte 2024-25 · misma liga · regla fijada antes de ver los resultados", PIE)
    return _guardar(fig, "f5_seleccion_k", cfg)


def fig_cargas(cfg):
    plt, F = estilo()
    c = pd.read_csv(_dir() / "cargas_correlacion.csv", index_col=0)
    c = c.loc[[m for m in NOM if m in c.index]]
    fig, ax = plt.subplots(figsize=(8.6, 7.0))
    fig.subplots_adjust(left=0.14, right=0.92, top=0.84, bottom=0.08)
    from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
    cm = LinearSegmentedColormap.from_list("k", [CLAY, CHALK, RACING])
    im = ax.imshow(c.values, cmap=cm, norm=TwoSlopeNorm(0, -1, 1), aspect="auto")
    for i in range(c.shape[0]):
        for j in range(c.shape[1]):
            v = c.values[i, j]
            ax.text(j, i, f"{v:.2f}".replace(".", ","), ha="center", va="center", fontsize=7.5, fontfamily=F["dato"],
                    color=CHALK if abs(v) > 0.55 else INK)
    ax.set_xticks(range(c.shape[1]), [x if x != "especifica" else "Específica" for x in c.columns])
    ax.set_yticks(range(c.shape[0]), [NOM[m] for m in c.index])
    ax.grid(False)
    fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    _cabecera(fig, ax, F, "Qué mide cada factor: correlación de cada métrica con los factores (varimax)",
              "Cargas rotadas divididas por la DT de la capacidad · «específica»: lo que la métrica no comparte", PIE)
    return _guardar(fig, "f5_cargas", cfg)


def fig_anchura(cfg):
    plt, F = estilo()
    r = pd.read_csv(_dir() / "examen_por_metrica.csv")
    K = int(pd.read_csv(_dir() / "seleccion_k.csv", index_col=0).query("elegido").index[0][1:].split("_")[0])
    a = r.pivot(index="metrica", columns="modelo", values="ancho_nivel80")
    cv = r.pivot(index="metrica", columns="modelo", values="cob80")
    red = (1 - a[f"K{K}_corr"] / a["K0_corr"]).sort_values()
    fig, axs = plt.subplots(1, 2, figsize=(10.2, 6.2), sharey=True)
    fig.subplots_adjust(left=0.12, right=0.98, top=0.80, bottom=0.10, wspace=0.08)
    y = np.arange(len(red))
    axs[0].barh(y, red.values, color=RACING, height=0.6)
    axs[0].set_yticks(y, [NOM[m] for m in red.index])
    axs[0].xaxis.set_major_formatter(lambda v, p: f"{v * 100:.0f} %")
    axs[0].set_title("Estrechamiento del intervalo del nivel", fontsize=9.5, loc="left", fontfamily=F["titulo"])
    axs[1].axvspan(0.76, 0.84, color=BANDA)
    axs[1].plot(cv.loc[red.index, "K0_corr"], y, "o", color=S400, ms=5, label="K = 0 (métricas independientes)")
    axs[1].plot(cv.loc[red.index, f"K{K}_corr"], y, "o", color=RACING, ms=6, label=f"K = {K}")
    axs[1].xaxis.set_major_formatter(lambda v, p: f"{v * 100:.0f} %")
    axs[1].set_title("Cobertura del 80 % de la producción", fontsize=9.5, loc="left", fontfamily=F["titulo"])
    axs[1].legend(fontsize=7.5, loc="lower left")
    _cabecera(fig, axs[0], F, f"Con K = {K} el nivel de cada métrica se estrecha y la cobertura se mantiene",
              "Examen fuera de tiempo 2023-24 a 2025-26 · frente a las mismas métricas estimadas aisladamente", PIE)
    return _guardar(fig, "f5_anchura_nivel", cfg)


def todas(cfg) -> dict:
    fs = [fig_seleccion(cfg), fig_cargas(cfg), fig_anchura(cfg)]
    return {"figuras": [str(f.relative_to(C.RAIZ)) for f in fs]}
