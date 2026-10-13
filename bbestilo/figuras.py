"""Figuras del artículo (matplotlib), a partir de los resultados guardados en data/modelos/estilos/."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

from . import config as C  # noqa: E402

COL = ["#2a78d6", "#e0662c", "#0f8a6a", "#b98500", "#c94f86", "#5b8c12", "#6a4fd0", "#a33a2e"]
INK, MUTED, LINE, KRAFT = "#3a2a1c", "#7a6450", "#e3d0b8", "#f9f3eb"
LIGAS = {"euroleague": "EuroLeague", "eurocup": "EuroCup", "acb": "Liga Endesa", "nba": "NBA", "gleague": "G League",
         "lba": "LBA", "bbl": "BBL", "lnb": "LNB"}


def estilo_mpl(fuentes: Path | None = None) -> None:
    from matplotlib import font_manager as fm
    if fuentes:
        for f in Path(fuentes).glob("*.ttf"):
            fm.fontManager.addfont(str(f))
    fam = "IBM Plex Sans" if any("IBM Plex Sans" in f.name for f in fm.fontManager.ttflist) else "DejaVu Sans"
    plt.rcParams.update({"font.family": fam, "font.size": 8.5, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                         "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK, "axes.titlesize": 9.5,
                         "axes.titleweight": "semibold", "axes.spines.top": False, "axes.spines.right": False,
                         "figure.dpi": 200, "savefig.bbox": "tight", "savefig.pad_inches": 0.04})


def _guardar(fig, ruta: Path) -> str:
    fig.savefig(ruta, facecolor="white")
    plt.close(fig)
    return ruta.name


def arquitectura(d: Path) -> str:
    fig, ax = plt.subplots(figsize=(7.0, 2.5))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 36)
    ax.axis("off")

    def caja(x, y, w, h, t, sub="", fc="white", ec=INK, fs=8.5):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.25,rounding_size=1.2", fc=fc, ec=ec, lw=1))
        ax.text(x + w / 2, y + h / 2 + (2.2 if sub else 0), t, ha="center", va="center", fontsize=fs, weight="semibold")
        if sub:
            ax.text(x + w / 2, y + h / 2 - 2.6, sub, ha="center", va="center", fontsize=fs - 1.8, color=MUTED)

    def flecha(x0, y0, x1, y1):
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=8, color=MUTED, lw=0.9))

    caja(0.5, 13, 10, 11, "x", "13 rasgos\nsin nivel")
    caja(14, 13, 9, 11, "64", "GELU")
    caja(26.5, 13, 9, 11, "32", "GELU")
    caja(39.5, 22, 10, 8, "μ_z", "mapa 3D")
    caja(39.5, 7, 10, 8, "log σ²_z", "3")
    caja(53.5, 13, 8, 11, "z", "μ + σ·ε")
    caja(66, 22, 33, 11, "Capa de salida: 8 neuronas", "γ_k = π_k N_k(z) / Σ_j π_j N_j(z)", fc=KRAFT, fs=8)
    caja(66, 3, 33, 13, "Decodificador", "3 → 32 → 64 → 13", fs=8)
    for a, b in [((10.5, 18.5), (14, 18.5)), ((23, 18.5), (26.5, 18.5)), ((35.5, 20), (39.5, 25)), ((35.5, 17), (39.5, 11)),
                 ((49.5, 26), (53.5, 20)), ((49.5, 11), (53.5, 16)), ((61.5, 20.5), (66, 27)), ((61.5, 16.5), (66, 10))]:
        flecha(*a, *b)
    ax.text(50, 34.5, "VaDE v2: codificador variacional, previa de mezcla de 8 gaussianas de covarianza completa en un mapa de 3 dimensiones",
            ha="center", fontsize=7.5, color=MUTED)
    return _guardar(fig, d / "fig_arquitectura.png")


def mapa(d: Path, clubes: pd.DataFrame, estilos: pd.DataFrame, nombres: dict) -> str:
    fig, axs = plt.subplots(1, 3, figsize=(7.2, 2.6))
    ent = clubes[~clubes["provisional"]]
    for ax, (i, j) in zip(axs, [(0, 1), (0, 2), (1, 2)]):
        a, b = "xyz"[i], "xyz"[j]
        for k in range(len(estilos)):
            s = ent[ent["e"] == k]
            ax.scatter(s[a], s[b], s=4, color=COL[k], alpha=0.65, linewidths=0)
        for k, r in estilos.iterrows():
            ax.scatter(r[a], r[b], s=36, color=COL[k], edgecolors=INK, linewidths=0.8, marker="D", zorder=3)
        ax.set_xlabel(f"Eje {i + 1}")
        ax.set_ylabel(f"Eje {j + 1}")
        ax.set_aspect("equal", adjustable="datalim")
    hs = [plt.Line2D([], [], marker="o", ls="", color=COL[k], label=nombres.get(estilos.iloc[k]["estilo"], estilos.iloc[k]["estilo"])) for k in range(len(estilos))]
    fig.legend(handles=hs, loc="lower center", ncol=4, frameon=False, fontsize=7, bbox_to_anchor=(0.5, -0.12))
    fig.tight_layout()
    return _guardar(fig, d / "fig_mapa.png")


def perfiles(d: Path, estilos: pd.DataFrame, nombres: dict) -> str:
    M = estilos[[f"z_{c}" for c in C.COLS]].to_numpy()
    fig, ax = plt.subplots(figsize=(7.0, 3.0))
    im = ax.imshow(M, cmap="BrBG_r", vmin=-1.8, vmax=1.8, aspect="auto")
    ax.set_xticks(range(len(C.COLS)), [r.corto for r in C.RASGOS], rotation=40, ha="right")
    ax.set_yticks(range(len(M)), [nombres.get(e, e) for e in estilos["estilo"]])
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            ax.text(j, i, f"{M[i, j]:+.1f}", ha="center", va="center", fontsize=6.5, color="white" if abs(M[i, j]) > 1.1 else INK)
    for k, t in enumerate(ax.get_yticklabels()):
        t.set_color(COL[k])
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01)
    cb.set_label("desv. típicas frente al club medio (sin nivel)", fontsize=7)
    ax.spines[:].set_visible(False)
    return _guardar(fig, d / "fig_perfiles.png")


def liga_estilo(d: Path, tabla: dict, nombres: list[str]) -> str:
    ligas = [l for l in LIGAS if l in tabla]
    est = sorted({e for l in ligas for e in tabla[l]})
    M = np.array([[tabla[l].get(e, 0) * 100 for e in est] for l in ligas])
    fig, ax = plt.subplots(figsize=(6.2, 2.9))
    im = ax.imshow(M, cmap="copper_r", vmin=0, vmax=max(45, M.max()), aspect="auto")
    ax.set_xticks(range(len(est)), nombres, rotation=30, ha="right")
    ax.set_yticks(range(len(ligas)), [LIGAS[l] for l in ligas])
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            ax.text(j, i, f"{M[i, j]:.0f}", ha="center", va="center", fontsize=7, color="white" if M[i, j] > 25 else INK)
    for k, t in enumerate(ax.get_xticklabels()):
        t.set_color(COL[k])
    fig.colorbar(im, ax=ax, fraction=0.03, pad=0.01).set_label("% de clubes de la liga", fontsize=7)
    ax.spines[:].set_visible(False)
    return _guardar(fig, d / "fig_liga_estilo.png")


def neutralizacion(d: Path, neu: dict) -> str:
    r2 = np.array(neu["r2_club"]) * 100
    orden = np.argsort(-r2)
    fig, ax = plt.subplots(figsize=(6.2, 2.4))
    ax.bar(range(len(r2)), r2[orden], color=[INK if r2[k] >= 30 else "#c9ad8c" for k in orden], width=0.7)
    ax.set_xticks(range(len(r2)), [C.RASGOS[k].corto for k in orden], rotation=40, ha="right")
    ax.set_ylabel("% de la varianza explicada por el nivel")
    for i, k in enumerate(orden):
        ax.text(i, r2[k] + 1.5, f"{r2[k]:.0f}", ha="center", fontsize=7)
    ax.set_ylim(0, max(r2) * 1.15)
    return _guardar(fig, d / "fig_neutralizacion.png")


def barrido(d: Path, b: dict) -> str:
    k = np.array(b["k"])
    fig, ax = plt.subplots(1, 2, figsize=(7.0, 2.3))
    for c, lab, col in (("bic_rasgos", "BIC (13 rasgos)", "#2a78d6"), ("icl_rasgos", "ICL (13 rasgos)", "#6a4fd0"), ("bic_mapa", "BIC (mapa 3D)", "#0f8a6a")):
        v = np.array(b[c])
        ax[0].plot(k, (v - v.min()) / (v.max() - v.min()), marker="o", ms=2.5, lw=1.2, color=col, label=lab)
    ax[0].axvline(8, color=MUTED, ls=":", lw=1)
    ax[0].set_xlabel("K")
    ax[0].set_ylabel("criterio normalizado (menos = mejor)")
    ax[0].legend(frameon=False, fontsize=6.5)
    ax[1].plot(k, b["estabilidad_kmedias"], marker="o", ms=2.5, color=INK, label="estabilidad (ARI submuestreo)")
    ax[1].plot(k, b["silueta_kmedias"], marker="s", ms=2.5, color="#e0662c", label="silueta")
    ax[1].axvline(8, color=MUTED, ls=":", lw=1)
    ax[1].set_xlabel("K")
    ax[1].legend(frameon=False, fontsize=6.5)
    fig.tight_layout()
    return _guardar(fig, d / "fig_barrido_k.png")


def exito(d: Path, ex: dict, nombres: dict) -> str:
    por = pd.DataFrame(ex["por_estilo"]).sort_values("estilo")
    fig, ax = plt.subplots(figsize=(5.6, 2.5))
    y = np.arange(len(por))
    for i, r in enumerate(por.itertuples()):
        k = int(r.estilo[1:]) - 1
        ax.errorbar(r.resid, i, xerr=r.ic95, fmt="o", color=COL[k], ms=5, capsize=2, lw=1.2)
    ax.axvline(0, color=MUTED, lw=0.8)
    ax.set_yticks(y, [nombres.get(e, e) for e in por["estilo"]])
    ax.invert_yaxis()
    ax.set_xlabel("net rating residual (σ), dado el nivel · IC 95 %")
    return _guardar(fig, d / "fig_exito.png")


def baskonia(d: Path, clubes: pd.DataFrame, estilos: pd.DataFrame, claves: list[str]) -> str:
    fig, ax = plt.subplots(figsize=(5.4, 3.4))
    ent = clubes[~clubes["provisional"]]
    ax.scatter(ent["x"], ent["y"], s=3, color="#d9c6ad", linewidths=0)
    for k, r in estilos.iterrows():
        ax.scatter(r["x"], r["y"], s=30, color=COL[k], edgecolors=INK, linewidths=0.6, marker="D", zorder=3)
    for clave, col, lab in zip(claves, [INK, "#a15c07"], ["EuroLeague", "Liga Endesa"]):
        s = clubes[clubes["clave_club"] == clave].sort_values("temporada")
        ax.plot(s["x"], s["y"], "-", color=col, lw=1.2, alpha=0.8, label=lab)
        ax.scatter(s["x"], s["y"], s=22, color=[COL[e] for e in s["e"]], edgecolors=col, linewidths=1.2, zorder=4)
        for r in s.itertuples():
            ax.annotate(r.temporada[2:], (r.x, r.y), xytext=(3, 3), textcoords="offset points", fontsize=6.5, color=col)
    ax.set_xlabel("Eje 1")
    ax.set_ylabel("Eje 2")
    ax.legend(frameon=False, fontsize=7)
    return _guardar(fig, d / "fig_baskonia.png")


def entrenamiento(d: Path, reg: dict) -> str:
    r = pd.DataFrame(reg["registro"])
    fig, ax = plt.subplots(1, 2, figsize=(6.6, 2.1))
    x = np.arange(len(r)) * 10
    ax[0].plot(x, r["perdida"], marker="o", ms=2.5, color=INK)
    ax[0].set_xlabel("época (cada 10; las últimas, ajuste fino)")
    ax[0].set_ylabel("pérdida por época")
    ax[1].plot(x, r["cuota_min"] * 100, marker="o", ms=2.5, color="#2a78d6", label="estilo más pequeño")
    ax[1].plot(x, r["cuota_max"] * 100, marker="o", ms=2.5, color="#e0662c", label="estilo más grande")
    ax[1].set_ylabel("% de las muestras de club")
    ax[1].set_xlabel("época")
    ax[1].legend(frameon=False, fontsize=6.5)
    fig.tight_layout()
    return _guardar(fig, d / "fig_entrenamiento.png")


def todas(d: Path, fuentes: Path | None = None) -> dict:
    estilo_mpl(fuentes)
    d.mkdir(parents=True, exist_ok=True)
    R = C.DIR_SALIDA
    an = json.loads((R / "analisis.json").read_text(encoding="utf-8"))
    est = pd.read_csv(R / "vade" / "estilos.csv")
    cl = pd.read_csv(R / "vade" / "clubes.csv")
    cl["e"] = cl["estilo"].str[1:].astype(int) - 1
    nombres = {}
    p = C.RAIZ / "config" / "estilos_v2.json"
    if p.exists():
        nombres = {k: v["nombre"] for k, v in json.loads(p.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    claves = json.loads(C.CLUBES.read_text(encoding="utf-8"))["baskonia"]["claves"]
    reg = json.loads((R / "vade" / "registro.json").read_text(encoding="utf-8"))
    return {"arquitectura": arquitectura(d), "mapa": mapa(d, cl, est, nombres), "perfiles": perfiles(d, est, nombres),
            "liga_estilo": liga_estilo(d, an["ligas"]["liga_x_estilo"], [nombres.get(e, e) for e in est["estilo"]]),
            "neutralizacion": neutralizacion(d, an["neutralizacion"]), "barrido": barrido(d, an["barrido_k"]),
            "exito": exito(d, an["exito"], nombres), "baskonia": baskonia(d, cl, est, claves),
            "entrenamiento": entrenamiento(d, reg)}
