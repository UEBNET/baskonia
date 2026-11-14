"""F3 · Figuras del informe 03_capa_medida (marca Kerno v2.0, mismas reglas que la F1)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from bbnorm5 import config as C
from bbnorm5.diagnostico.figuras import (BANDA, BRASS_DEEP, CHALK, CLAY, INK, LAKE, RACING, S200, S400, S500, S600,
                                         _cabecera, _guardar, estilo)
from bbnorm5.medida import datos as D

PIE = "Datos públicos · 20 ligas, temporada regular 2020-21 a 2025-26 · Kerno Analytics · v5.0 F3"
NOM = {"t2_pct": "T2%", "t3_pct": "T3%", "tl_pct": "TL%", "tpar": "3PAr", "oreb_pct": "OREB%", "dreb_pct": "DREB%",
       "ast_pct": "AST%", "tov_pct": "TOV%", "blk_pct": "BLK%", "stl_p100": "Robos/100", "pf_p40": "Faltas/40",
       "ftr": "FTr", "pts_p100": "Pts/100", "usg_pct": "USG%"}
ETQ = {"crudo": "Tasa de la primera mitad, sin encoger", "jer": "Jerárquico por rol",
       "jer_sd": "Jerárquico + sobredispersión entre partidos", "base": "Jerárquico (+ sobredispersión)",
       "pref": "… + deriva entre mitades (preferido)"}


def preferido(r: pd.DataFrame) -> pd.Series:
    """Modelo preferido por métrica: con deriva entre mitades (jer_sd_d; jer_d en la familia normal)."""
    x = r[r["modelo"].str.endswith("_d")]
    return x.drop_duplicates("metrica").set_index("metrica")["modelo"]


def base(r: pd.DataFrame) -> pd.Series:
    """Jerárquico sin deriva: jer_sd (binomial y Poisson) o jer (normal)."""
    x = r[r["modelo"].isin(["jer", "jer_sd"])].sort_values("modelo")
    return x.drop_duplicates("metrica", keep="last").set_index("metrica")["modelo"]


def fig_cobertura(cfg):
    plt, F = estilo()
    r = pd.read_csv(D.DIR / "validacion_por_metrica.csv")
    pref = preferido(r)
    orden = r[r["modelo"] == "crudo"].sort_values("cob80")["metrica"].tolist()
    fig, ax = plt.subplots(figsize=(9.2, 6.6))
    fig.subplots_adjust(left=0.13, right=0.97, top=0.86, bottom=0.10)
    y = np.arange(len(orden))
    ax.axvspan(0.76, 0.84, color=BANDA)
    ax.axvline(0.8, color=S400, lw=1, ls="--")
    c80 = r.set_index(["metrica", "modelo"])["cob80"]
    bs = base(r)
    for nom, mods, mk, col, ms in (("crudo", {m: "crudo" for m in orden}, "o", S400, 5.5), ("base", bs, "D", LAKE, 4.5),
                                   ("pref", pref, "o", RACING, 6.0)):
        ax.plot([c80.get((m, mods.get(m)), np.nan) for m in orden], y, mk, color=col, ms=ms, label=ETQ[nom])
    ax.set_yticks(y, [NOM[m] for m in orden])
    ax.set_xlim(0.4, 1.0)
    ax.xaxis.set_major_formatter(lambda v, p: f"{v * 100:.0f} %")
    ax.legend(loc="center right", fontsize=8)
    c = r.set_index(["metrica", "modelo"])["cob80"]
    dentro = sum(0.76 <= c[(m, pref[m])] <= 0.84 for m in pref.index)
    cr = r[r["modelo"] == "crudo"]["cob80"]
    _cabecera(fig, ax, F, f"Con encogimiento y deriva, {dentro} de {len(pref)} métricas cubren el 76–84 %; "
              f"la tasa cruda, {cr.min() * 100:.0f}–{cr.max() * 100:.0f} %",
              "Cobertura del intervalo del 80 % al predecir la 2.ª mitad de cada jugador · banda objetivo 76–84 %", PIE)
    return _guardar(fig, "f3_cobertura80", cfg)


def fig_crps(cfg):
    plt, F = estilo()
    r = pd.read_csv(D.DIR / "validacion_por_metrica.csv")
    pref = preferido(r)
    cr = r[r["modelo"] == "crudo"].set_index("metrica")["crps"]
    g = pd.Series({m: 1 - r[(r.metrica == m) & (r.modelo == pref[m])]["crps"].iloc[0] / cr[m] for m in pref.index})
    g = g.sort_values()
    fig, ax = plt.subplots(figsize=(9.2, 6.2))
    fig.subplots_adjust(left=0.13, right=0.97, top=0.86, bottom=0.10)
    y = np.arange(len(g))
    ax.barh(y, g.values, color=RACING, height=0.6)
    for yi, v in zip(y, g.values):
        ax.text(v + 0.004, yi, f"{v * 100:.0f} %".replace(".", ","), va="center", fontsize=8, color=INK,
                fontfamily=F["dato"])
    ax.set_yticks(y, [NOM[m] for m in g.index])
    ax.xaxis.set_major_formatter(lambda v, p: f"{v * 100:.0f} %")
    ax.set_xlim(0, max(0.45, g.max() + 0.05))
    _cabecera(fig, ax, F, f"El modelo de medida reduce el error de predicción entre un {g.min() * 100:.0f} y un "
              f"{g.max() * 100:.0f} %",
              "Reducción del CRPS de la 2.ª mitad frente a la tasa cruda de la 1.ª · modelo preferido de cada métrica", PIE)
    return _guardar(fig, "f3_crps", cfg)


def fig_pit(cfg):
    plt, F = estilo()
    c = pd.read_parquet(D.DIR / "validacion_casos.parquet", columns=["metrica", "modelo", "pit"])
    mets = ["t3_pct", "ast_pct", "ftr"]
    fig, axs = plt.subplots(2, 3, figsize=(10.2, 6.0), sharey=True)
    fig.subplots_adjust(left=0.07, right=0.98, top=0.83, bottom=0.14, wspace=0.08, hspace=0.45)
    for j, m in enumerate(mets):
        for i, mod in enumerate(("crudo", "jer_sd_d")):
            ax = axs[i, j]
            x = c[(c.metrica == m) & (c.modelo == mod)]["pit"]
            ax.hist(x, bins=np.linspace(0, 1, 11), weights=np.full(len(x), 10 / len(x)),
                    color=RACING if mod != "crudo" else S400, edgecolor=CHALK)
            ax.axhline(1.0, color=S500, lw=1, ls="--")
            ax.set_title(f"{NOM[m]} · {'cruda' if mod == 'crudo' else 'modelo preferido'}", fontsize=9,
                         color=INK, loc="left", fontfamily=F["titulo"])
    for ax in axs[:, 0]:
        ax.set_ylabel("Densidad (uniforme = 1)")
    for ax in axs[1]:
        ax.set_xlabel("PIT")
    _cabecera(fig, axs[0, 0], F, "La tasa cruda es demasiado segura (forma de U); el modelo preferido es casi plano",
              "Histograma PIT de la 2.ª mitad · todas las ligas-temporada 2020-21 a 2025-26", PIE)
    return _guardar(fig, "f3_pit", cfg)


def fig_estabilizacion(cfg):
    """n* implícito del modelo (mediana entre ligas-temporada) frente a los dos n* de la F1."""
    plt, F = estilo()
    h = pd.read_csv(D.DIR / "hiperparametros.csv")
    h = h[(h["datos"] == "temporada")]
    pref = h.sort_values("modelo").drop_duplicates(["liga", "temporada", "metrica"], keep="last")
    med = pref.groupby("metrica")["n_estab"].agg(["median", lambda s: s.quantile(0.25), lambda s: s.quantile(0.75)])
    med.columns = ["med", "q25", "q75"]
    f1 = pd.read_csv(C.DIR_DATOS / "f1" / "varianza" / "componentes.csv").set_index("metrica")
    f1d = pd.read_csv(C.DIR_DATOS / "f1" / "varianza" / "division_muestra.csv").set_index("metrica")
    # sólo donde la F1 mide en las mismas oportunidades (en el resto la F1 usaba minutos o posesiones)
    eq = {"t2_pct": "fg2_pct", "t3_pct": "fg3_pct", "tl_pct": "ft_pct", "tpar": "fg3a_rate", "ftr": "fta_rate",
          "pts_p100": "pts_p100", "tov_pct": "tov_pct"}
    med = med.sort_values("med")
    fig, ax = plt.subplots(figsize=(9.2, 6.6))
    fig.subplots_adjust(left=0.13, right=0.97, top=0.86, bottom=0.11)
    y = np.arange(len(med))
    ax.hlines(y, med["q25"], med["q75"], color=RACING, lw=3, alpha=0.35)
    ax.plot(med["med"], y, "o", color=RACING, ms=6, label="F3 · modelo de medida (mediana y rango intercuartílico entre ligas-temporada)")
    a = [f1["n_estab_temp"].get(eq.get(m), np.nan) for m in med.index]
    b = [f1d["n_estab_momentos"].get(eq.get(m), np.nan) for m in med.index]
    ax.plot(a, y, "D", color=LAKE, ms=4.5, label="F1 · REML (cota superior; sólo con las mismas oportunidades)")
    ax.plot(b, y, "^", color=CLAY, ms=5, label="F1 · división de muestra (cota inferior)")
    ax.set_xscale("log")
    ax.set_xticks([2, 5, 10, 20, 50, 100, 200, 500, 1000])
    ax.xaxis.set_major_formatter(lambda v, p: f"{v:.0f}".replace("1000", "1.000"))
    ax.xaxis.set_minor_formatter(lambda v, p: "")
    ax.set_yticks(y, [NOM[m] for m in med.index])
    ax.set_xlabel("Oportunidades para fiabilidad 0,5 en una temporada (escala log)")
    ax.legend(loc="lower right", fontsize=7.6)
    _cabecera(fig, ax, F, "Cuánto hay que ver a un jugador para que la mitad de lo visto sea señal",
              "Punto de estabilización n* implícito en el modelo, en las oportunidades de cada métrica", PIE)
    return _guardar(fig, "f3_estabilizacion", cfg)


def fig_cobertura_ligas(cfg):
    plt, F = estilo()
    r = pd.read_csv(D.DIR / "validacion_por_liga.csv")
    pref = preferido(pd.read_csv(D.DIR / "validacion_por_metrica.csv"))
    r = r[[mod == pref.get(m) for m, mod in zip(r["metrica"], r["modelo"])]]
    t = r.pivot(index="liga", columns="metrica", values="cob80")
    t = t.loc[t.mean(axis=1).sort_values().index, [m for m in NOM if m in t.columns]]
    fig, ax = plt.subplots(figsize=(10.2, 7.0))
    fig.subplots_adjust(left=0.10, right=0.93, top=0.86, bottom=0.10)
    from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
    cm = LinearSegmentedColormap.from_list("k", [CLAY, CHALK, RACING])
    im = ax.imshow(t.values, cmap=cm, norm=TwoSlopeNorm(0.8, 0.6, 1.0), aspect="auto")
    for i in range(t.shape[0]):
        for j in range(t.shape[1]):
            v = t.values[i, j]
            if np.isfinite(v):
                ax.text(j, i, f"{v * 100:.0f}", ha="center", va="center", fontsize=7, fontfamily=F["dato"],
                        color=CHALK if abs(v - 0.8) > 0.12 else INK)
    ax.set_xticks(range(t.shape[1]), [NOM[m] for m in t.columns], rotation=45, ha="right")
    ax.set_yticks(range(t.shape[0]), t.index)
    ax.grid(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cb.ax.yaxis.set_major_formatter(lambda v, p: f"{v * 100:.0f} %")
    fuera = int(((t < 0.76) | (t > 0.84)).sum().sum())
    _cabecera(fig, ax, F, f"Por liga, {fuera} de {int(t.notna().sum().sum())} casillas quedan fuera de 76–84 %",
              "Cobertura del 80 % por liga y métrica · modelo preferido · 2.ª mitad desde la 1.ª", PIE)
    return _guardar(fig, "f3_cobertura_ligas", cfg)


def todas(cfg) -> dict:
    fs = [fig_cobertura(cfg), fig_crps(cfg), fig_pit(cfg), fig_estabilizacion(cfg), fig_cobertura_ligas(cfg)]
    return {"figuras": [str(f.relative_to(C.RAIZ)) for f in fs]}
