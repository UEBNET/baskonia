"""Figuras del artículo (matplotlib), a partir de los resultados guardados en data/modelos/estilos/ (modelo final)
y data/modelos/estilos/historial/ (iteraciones anteriores)."""
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

# Paleta categórica (orden fijo; validada: CVD en la banda 6-8 sólo con apoyo de forma o etiqueta directa).
# Los 6 estilos usan las 6 primeras; las 8 ligas, las 8.
COL = ["#2a78d6", "#e0662c", "#0f8a6a", "#b98500", "#c94f86", "#6a4fd0", "#5b8c12", "#a33a2e"]
MARC = ["o", "s", "D", "^", "v", "P", "X", "*"]
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
# secuencial de un solo tono (kraft → nogal), de blanco (0) a oscuro
SEQ = LinearSegmentedColormap.from_list("kraft", ["#ffffff", "#efe0cd", "#c9ad8c", "#8f6b4a", "#3a2a1c"])
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
    caja(66, 22, 33, 11, f"Capa de salida: {C.N_ESTILOS} neuronas", "γ_k = π_k N_k(z) / Σ_j π_j N_j(z)", fc=KRAFT, fs=8)
    caja(66, 3, 33, 13, "Decodificador", "3 → 32 → 64 → 13", fs=8)
    for a, b in [((10.5, 18.5), (14, 18.5)), ((23, 18.5), (26.5, 18.5)), ((35.5, 20), (39.5, 25)), ((35.5, 17), (39.5, 11)),
                 ((49.5, 26), (53.5, 20)), ((49.5, 11), (53.5, 16)), ((61.5, 20.5), (66, 27)), ((61.5, 16.5), (66, 10))]:
        flecha(*a, *b)
    ax.text(50, 34.5, f"VaDE: codificador variacional, previa de mezcla de {C.N_ESTILOS} gaussianas de covarianza completa en un mapa de 3 dimensiones",
            ha="center", fontsize=7.5, color=MUTED)
    return _guardar(fig, d / "fig_arquitectura.png")


def mapa(d: Path, clubes: pd.DataFrame, estilos: pd.DataFrame, nombres: dict) -> str:
    fig, axs = plt.subplots(1, 3, figsize=(7.2, 2.6))
    ent = clubes[~clubes["provisional"]]
    for ax, (i, j) in zip(axs, [(0, 1), (0, 2), (1, 2)]):
        a, b = "xyz"[i], "xyz"[j]
        for k in range(len(estilos)):
            s = ent[ent["e"] == k]
            ax.scatter(s[a], s[b], s=4, color=COL[k], alpha=0.65, linewidths=0, marker=MARC[k])
        for k, r in estilos.iterrows():
            ax.scatter(r[a], r[b], s=36, color=COL[k], edgecolors=INK, linewidths=0.8, marker="D", zorder=3)
        ax.set_xlabel(f"Eje {i + 1}")
        ax.set_ylabel(f"Eje {j + 1}")
        ax.set_aspect("equal", adjustable="datalim")
    hs = [plt.Line2D([], [], marker=MARC[k], ls="", color=COL[k], label=nombres.get(estilos.iloc[k]["estilo"], estilos.iloc[k]["estilo"])) for k in range(len(estilos))]
    fig.legend(handles=hs, loc="lower center", ncol=3, frameon=False, fontsize=7, bbox_to_anchor=(0.5, -0.16))
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
    im = ax.imshow(M, cmap=SEQ, vmin=0, vmax=max(45, M.max()), aspect="auto")
    ax.set_xticks(range(len(est)), nombres, rotation=30, ha="right")
    ax.set_yticks(range(len(ligas)), [LIGAS[l] for l in ligas])
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            ax.text(j, i, f"{M[i, j]:.0f}", ha="center", va="center", fontsize=7, color="white" if M[i, j] > 0.6 * max(45, M.max()) else INK)
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
    ax[0].axvline(C.N_ESTILOS, color=MUTED, ls=":", lw=1)
    ax[0].set_xlabel("K")
    ax[0].set_ylabel("criterio normalizado (menos = mejor)")
    ax[0].legend(frameon=False, fontsize=6.5)
    ax[1].plot(k, b["estabilidad_kmedias"], marker="o", ms=2.5, color=INK, label="estabilidad (ARI submuestreo)")
    ax[1].plot(k, b["silueta_kmedias"], marker="s", ms=2.5, color="#e0662c", label="silueta")
    ax[1].axvline(C.N_ESTILOS, color=MUTED, ls=":", lw=1)
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


# ---------------------------------------------------------------- iteraciones del modelo
ITER = [("v1_12estilos", "vade", "v1 VaDE 12"), ("v1_12estilos", "idec", "v1 IDEC 12"), ("v2_8estilos", "vade", "v2 VaDE 8"),
        ("v2_8estilos", "idec", "v2 IDEC 8"), ("v3_6estilos", "vade", "v3 VaDE 6"), ("", "vade", "Final VaDE 6")]


def _ev_iter(carpeta: str, red: str) -> dict | None:
    p = (C.DIR_SALIDA / "historial" / carpeta if carpeta else C.DIR_SALIDA) / "evaluacion.json"
    return json.loads(p.read_text(encoding="utf-8")).get(red) if p.exists() else None


def iteraciones(d: Path) -> str:
    """Métricas clave por iteración (pequeños múltiplos; VaDE unido por línea, IDEC en hueco)."""
    met = [("eta2_nivel", "η² nivel ← estilo", "menos es mejor"), ("nmi_estilo_liga", "NMI estilo-liga", "menos es mejor"),
           ("salida_max_media", "Seguridad de la asignación", ""), ("ari_semillas_medio", "ARI entre semillas", ""),
           ("estabilidad_mapa", "Estabilidad del mapa (r)", ""), ("ari_temporal_reserva", "Reproducibilidad temporal (ARI)", ""),
           ("robustez_reparto_minutos", "Robustez al reparto de minutos", ""), ("silueta_rasgos", "Silueta en los 13 rasgos", "")]
    evs = [(_ev_iter(c, r), r, lab) for c, r, lab in ITER]
    evs = [x for x in evs if x[0] is not None]
    fig, axs = plt.subplots(2, 4, figsize=(7.2, 3.6), sharex=True)
    xs = np.arange(len(evs))
    for ax, (k, tit, sub) in zip(axs.ravel(), met):
        v = [ev.get(k) for ev, _, _ in evs]
        iv = [i for i, (_, r, _) in enumerate(evs) if r == "vade"]
        ax.plot([xs[i] for i in iv], [v[i] for i in iv], color=INK, lw=1.2, zorder=2)
        for i, (ev, r, lab) in enumerate(evs):
            fin = lab.startswith("Final")
            ax.scatter(xs[i], v[i], s=34 if fin else 22, zorder=3, marker="o",
                       facecolor=("#2f7a4c" if fin else INK) if r == "vade" else "white", edgecolor="#2f7a4c" if fin else INK, lw=1.1)
        ax.set_title(tit + (f"\n({sub})" if sub else ""), fontsize=7.6)
        ax.grid(axis="y", color=LINE, lw=0.5)
        ax.tick_params(labelsize=6.5)
        lo, hi = min(v), max(v)
        ax.set_ylim(lo - 0.12 * (hi - lo + 1e-9), hi + 0.18 * (hi - lo + 1e-9))
        ax.annotate(f"{v[-1]:.2f}".replace(".", ","), (xs[-1], v[-1]), xytext=(0, 5), textcoords="offset points", ha="center", fontsize=6.5, color="#2f7a4c")
    for ax in axs[1]:
        ax.set_xticks(xs, [lab for _, _, lab in evs], rotation=55, ha="right", fontsize=6.5)
    fig.tight_layout(h_pad=0.6, w_pad=0.6)
    return _guardar(fig, d / "fig_iteraciones.png")


def mapas_iteraciones(d: Path) -> str:
    """Plano de los ejes 1-2 en v1, v2 y el modelo final, con los clubes coloreados por LIGA: en la v1 las ligas
    ocupan regiones propias (el nivel y la liga dominaban el mapa); tras neutralizar, se mezclan."""
    paneles = [("v1_12estilos", "v1 · 12 estilos, sin neutralizar"), ("v2_8estilos", "v2 · 8 estilos, nivel neutralizado"),
               ("", f"Final · {C.N_ESTILOS} estilos")]
    fig, axs = plt.subplots(1, 3, figsize=(7.2, 2.7))
    ligas = list(LIGAS)
    for ax, (carpeta, tit) in zip(axs, paneles):
        p = (C.DIR_SALIDA / "historial" / carpeta if carpeta else C.DIR_SALIDA) / "vade" / "clubes.csv"
        if not p.exists():
            ax.axis("off")
            continue
        c = pd.read_csv(p)
        c = c[~c["provisional"]]
        for k, l in enumerate(ligas):
            s = c[c["liga"] == l]
            ax.scatter(s["x"], s["y"], s=3.5, color=COL[k], marker=MARC[k], alpha=0.7, linewidths=0)
        ax.set_title(tit, fontsize=7.8)
        ax.set_xlabel("Eje 1", fontsize=7)
        ax.set_ylabel("Eje 2", fontsize=7)
        ax.tick_params(labelsize=6)
        ax.set_aspect("equal", adjustable="datalim")
    hs = [plt.Line2D([], [], marker=MARC[k], ls="", color=COL[k], label=LIGAS[l]) for k, l in enumerate(ligas)]
    fig.legend(handles=hs, loc="lower center", ncol=8, frameon=False, fontsize=6.5, bbox_to_anchor=(0.5, -0.06), handletextpad=0.2, columnspacing=0.8)
    fig.tight_layout()
    return _guardar(fig, d / "fig_mapas_iteraciones.png")


def correspondencia(d: Path, nombres: dict) -> str | None:
    """Clubes de cada estilo de la v2 (8) en cada estilo del modelo final."""
    p8 = C.DIR_SALIDA / "historial" / "v2_8estilos" / "vade" / "clubes.csv"
    if not p8.exists():
        return None
    n8 = json.loads((C.DIR_SALIDA / "historial" / "v2_8estilos" / "nombres.json").read_text(encoding="utf-8"))
    a = pd.read_csv(p8)[["clave", "estilo", "provisional"]]
    b = pd.read_csv(C.DIR_SALIDA / "vade" / "clubes.csv")[["clave", "estilo"]]
    m = a[~a["provisional"]].merge(b, on="clave", suffixes=("_8", "_f"))
    tab = pd.crosstab(m["estilo_8"], m["estilo_f"])
    M = tab.to_numpy()
    fig, ax = plt.subplots(figsize=(6.0, 3.0))
    ax.imshow(M, cmap=SEQ, vmin=0, vmax=M.max(), aspect="auto")
    ax.set_xticks(range(M.shape[1]), [nombres.get(e, e) for e in tab.columns], rotation=25, ha="right", fontsize=7)
    ax.set_yticks(range(M.shape[0]), [n8.get(e, {}).get("nombre", e) for e in tab.index], fontsize=7)
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            if M[i, j]:
                ax.text(j, i, str(M[i, j]), ha="center", va="center", fontsize=6.8, color="white" if M[i, j] > 0.55 * M.max() else INK)
    ax.set_xlabel(f"Modelo final ({C.N_ESTILOS} estilos)", fontsize=7.5)
    ax.set_ylabel("v2 (8 estilos)", fontsize=7.5)
    ax.spines[:].set_visible(False)
    return _guardar(fig, d / "fig_correspondencia.png")


def ari_semillas(d: Path, ev: dict, semillas: list[int], cons: dict) -> str:
    A = np.array(ev["ari_matriz"])
    fig, ax = plt.subplots(1, 2, figsize=(7.0, 2.6), gridspec_kw={"width_ratios": [1.15, 1]})
    im = ax[0].imshow(A, cmap=SEQ, vmin=0, vmax=1)
    ax[0].set_xticks(range(len(semillas)), semillas, rotation=90, fontsize=6.5)
    ax[0].set_yticks(range(len(semillas)), semillas, fontsize=6.5)
    for i in range(len(A)):
        for j in range(len(A)):
            if i != j:
                ax[0].text(j, i, f"{A[i, j]:.2f}"[1:] if A[i, j] < 1 else "1", ha="center", va="center", fontsize=5.2,
                           color="white" if A[i, j] > 0.6 else INK)
    ax[0].set_title("ARI entre las particiones de cada semilla", fontsize=7.8)
    ax[0].spines[:].set_visible(False)
    fig.colorbar(im, ax=ax[0], fraction=0.045, pad=0.02).ax.tick_params(labelsize=6)
    a_c = cons.get("ari_semillas_consenso") or []
    a_f = cons.get("ari_final_semillas") or []
    y = np.arange(len(a_c))
    ax[1].barh(y - 0.18, a_c, height=0.34, color=INK, label="semilla ↔ consenso")
    if len(a_f) == len(a_c):
        ax[1].barh(y + 0.18, a_f, height=0.34, color="#c9ad8c", label="semilla ↔ modelo final")
    ax[1].set_yticks(y, semillas[: len(a_c)], fontsize=6.5)
    ax[1].invert_yaxis()
    ax[1].set_xlim(0, 1)
    ax[1].axvline(cons.get("ari_final_consenso", np.nan), color="#2f7a4c", lw=1.2, ls="--")
    ax[1].text(cons.get("ari_final_consenso", 0), -0.9, " modelo final ↔ consenso", color="#2f7a4c", fontsize=6.3, va="bottom")
    ax[1].set_xlabel("ARI", fontsize=7)
    ax[1].legend(frameon=False, fontsize=6.3, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2)
    ax[1].tick_params(labelsize=6.5)
    fig.tight_layout()
    return _guardar(fig, d / "fig_ari_semillas.png")


def simulacion(d: Path, ej: dict, estilos: pd.DataFrame, nombres: dict) -> str:
    """Ejemplo de simulación de varios fichajes: plantilla en el plano 1-2 y salida de la red antes y después."""
    fig, ax = plt.subplots(1, 2, figsize=(7.2, 2.9), gridspec_kw={"width_ratios": [1.25, 1]})
    a = ax[0]
    for k, r in estilos.iterrows():
        a.scatter(r["x"], r["y"], s=26, color=COL[k], edgecolors=INK, linewidths=0.6, marker="D", zorder=2)
        a.annotate(nombres.get(r["estilo"], r["estilo"]), (r["x"], r["y"]), xytext=(3, -8), textcoords="offset points", fontsize=5.6, color=MUTED)
    for p in ej["plantilla"]:
        a.scatter(p["xyz"][0], p["xyz"][1], s=8 + p["min"] / 40, facecolor="none", edgecolor=COL[p["e"]], lw=1, zorder=3)
    for p in ej["bajas"]:
        a.scatter(p["xyz"][0], p["xyz"][1], s=30, marker="x", color=MUTED, lw=1.2, zorder=4)
        a.annotate(f"baja: {p['nombre']}", (p["xyz"][0], p["xyz"][1]), xytext=(5, -9), textcoords="offset points", fontsize=6, color=MUTED)
    for n_, p in enumerate(ej["fichajes"], 1):
        a.scatter(p["xyz"][0], p["xyz"][1], s=42, marker="D", color=COL[p["e"]], edgecolors=INK, lw=1, zorder=5)
        a.annotate(f"{n_}. {p['nombre']}", (p["xyz"][0], p["xyz"][1]), xytext=(6, 4), textcoords="offset points", fontsize=6.5, color=INK,
                   bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none", "alpha": 0.85})
    x0, x1 = ej["antes"]["xyz"], ej["despues"]["xyz"]
    a.scatter(x0[0], x0[1], s=60, marker="s", color=INK, zorder=6)
    a.scatter(x1[0], x1[1], s=70, marker="D", color="#a15c07", zorder=6)
    a.add_patch(FancyArrowPatch((x0[0], x0[1]), (x1[0], x1[1]), arrowstyle="-|>", mutation_scale=9, color="#a15c07", lw=1.6, zorder=6))
    a.annotate("club hoy", (x0[0], x0[1]), xytext=(-34, 6), textcoords="offset points", fontsize=6.5,
               bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none", "alpha": 0.85})
    a.annotate("con el escenario", (x1[0], x1[1]), xytext=(6, -11), textcoords="offset points", fontsize=6.5, color="#a15c07",
               bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none", "alpha": 0.85})
    a.set_xlabel("Eje 1", fontsize=7)
    a.set_ylabel("Eje 2", fontsize=7)
    a.tick_params(labelsize=6)
    b = ax[1]
    y = np.arange(len(estilos))
    b.barh(y - 0.19, ej["antes"]["p"], height=0.36, color="#c9ad8c", label="hoy")
    b.barh(y + 0.19, ej["despues"]["p"], height=0.36, color="#a15c07", label="con el escenario")
    b.set_yticks(y, [nombres.get(e, e) for e in estilos["estilo"]], fontsize=6.8)
    for k, t in enumerate(b.get_yticklabels()):
        t.set_color(COL[k])
    b.invert_yaxis()
    b.set_xlim(0, 1)
    b.set_xlabel("salida de la neurona (probabilidad del estilo)", fontsize=7)
    b.legend(frameon=False, fontsize=6.5, loc="lower right")
    b.tick_params(labelsize=6.5)
    fig.tight_layout()
    return _guardar(fig, d / "fig_simulacion.png")


def todas(d: Path, fuentes: Path | None = None, ejemplo: dict | None = None) -> dict:
    estilo_mpl(fuentes)
    d.mkdir(parents=True, exist_ok=True)
    R = C.DIR_SALIDA
    an = json.loads((R / "analisis.json").read_text(encoding="utf-8"))
    ev = json.loads((R / "evaluacion.json").read_text(encoding="utf-8"))["vade"]
    est = pd.read_csv(R / "vade" / "estilos.csv")
    cl = pd.read_csv(R / "vade" / "clubes.csv")
    cl["e"] = cl["estilo"].str[1:].astype(int) - 1
    nombres = {}
    p = C.RAIZ / "config" / "estilos.json"
    if p.exists():
        nombres = {k: v["nombre"] for k, v in json.loads(p.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    claves = json.loads(C.CLUBES.read_text(encoding="utf-8"))["baskonia"]["claves"]
    reg = json.loads((R / "vade" / "registro.json").read_text(encoding="utf-8"))
    out = {"arquitectura": arquitectura(d), "mapa": mapa(d, cl, est, nombres), "perfiles": perfiles(d, est, nombres),
           "liga_estilo": liga_estilo(d, an["ligas"]["liga_x_estilo"], [nombres.get(e, e) for e in est["estilo"]]),
           "neutralizacion": neutralizacion(d, an["neutralizacion"]), "barrido": barrido(d, an["barrido_k"]),
           "exito": exito(d, an["exito"], nombres), "baskonia": baskonia(d, cl, est, claves),
           "entrenamiento": entrenamiento(d, reg), "iteraciones": iteraciones(d), "mapas_iter": mapas_iteraciones(d),
           "correspondencia": correspondencia(d, nombres),
           "ari_semillas": ari_semillas(d, ev, ev["semillas"], reg.get("consenso") or {})}
    if ejemplo:
        out["simulacion"] = simulacion(d, ejemplo, est, nombres)
    return out
