"""F8 · Figuras del informe 08_validacion (marca Kerno v2.0)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from bbnorm5 import config as C
from bbnorm5.diagnostico.figuras import CLAY, LAKE, RACING, S400, _cabecera, _guardar, estilo
from bbnorm5.medida.figuras import NOM

PIE = "Datos públicos · 20 ligas, temporada regular 2020-21 a 2025-26 · Kerno Analytics · v5.0 F8"
DIR = C.DIR_DATOS / "validacion"


def _pct(v, p=None):
    return f"{v * 100:+.0f} %".replace("+0 %", "0 %")


def fig_fichajes(cfg):
    """Criterio 9: WIS de la v5 publicada (ex ante) frente a la v3.3 por métrica, con IC 95 % por personas."""
    plt, F = estilo()
    t = pd.read_csv(DIR / "examen_fichajes.csv")
    m = "ex_ante_sin_estilo_liga"
    t = t.iloc[::-1].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    fig.subplots_adjust(left=0.20, right=0.97, top=0.80, bottom=0.14)
    y = np.arange(len(t))
    for yi, (_, r) in zip(y, t.iterrows()):
        col = RACING if r[f"ic_hi_{m}"] < 0 else S400
        ax.hlines(yi, r[f"ic_lo_{m}"], r[f"ic_hi_{m}"], color=col, lw=4, alpha=0.45)
        ax.plot(r[f"wis_{m}_frente_v33"], yi, "o", color=col, ms=7)
        ax.plot(r["wis_final_sin_estilo_liga_frente_v33"], yi, "|", color=CLAY, ms=12, mew=2,
                label="Condicionada al rol y al volumen de T (con fuga)" if yi == 0 else None)
    ax.axvline(0, color=S400, lw=1)
    ax.set_yticks(y, [NOM.get(v, "Todas") for v in t["metrica"]])
    ax.xaxis.set_major_formatter(_pct)
    ax.set_xlabel("WIS de la v5 ÷ WIS de la v3.3 − 1 (IC 95 % por bootstrap de personas; negativo = mejor la v5)")
    ax.legend(loc="upper right", fontsize=8)
    met = t[t["metrica"] != "todas"]
    _cabecera(fig, ax, F, f"La v5 ex ante mejora a la v3.3 en los fichajes reales en {int((met[f'ic_hi_{m}'] < 0).sum())} "
                          f"de {len(met)} métricas",
              "Temporada siguiente al fichaje · cortes 2022-23 a 2024-25 · intervalos del 50, 80 y 90 %", PIE)
    return _guardar(fig, "f8_fichajes_v33", cfg)


def fig_protocolo(cfg):
    """Protocolo de la F1: v5 publicada (ex ante) frente a la v3.2 por métrica."""
    plt, F = estilo()
    t = pd.read_csv(DIR / "protocolo_f1_publicada.csv")
    t = t[t["por"].isin(["metrica", "global"])].copy()
    t["orden"] = np.where(t["por"] == "global", -1e9, t["v5_frente_v3.2"])
    t = t.sort_values("orden", ascending=False).reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(8.6, 6.0))
    fig.subplots_adjust(left=0.20, right=0.97, top=0.83, bottom=0.11)
    y = np.arange(len(t))[::-1]
    for yi, (_, r) in zip(y, t.iterrows()):
        col = RACING if r["ic_hi_v3.2"] < 0 else (CLAY if r["ic_lo_v3.2"] > 0 else S400)
        ax.hlines(yi, r["ic_lo_v3.2"], r["ic_hi_v3.2"], color=col, lw=4, alpha=0.45)
        ax.plot(r["v5_frente_v3.2"], yi, "o", color=col, ms=7)
    ax.axvline(0, color=S400, lw=1)
    eq = {"fg2_pct": "t2_pct", "fg3_pct": "t3_pct", "ft_pct": "tl_pct", "fg3a_rate": "tpar", "fta_rate": "ftr"}
    ax.set_yticks(y, [("Todas" if r["por"] == "global" else NOM.get(eq.get(r["grupo"], r["grupo"]), r["grupo"]))
                      for _, r in t.iterrows()])
    ax.xaxis.set_major_formatter(_pct)
    ax.set_xlabel("WIS de la v5 ÷ WIS de la v3.2 − 1 (IC 95 % por personas; verde mejor la v5, teja mejor la v3.2)")
    _cabecera(fig, ax, F, "En el examen de la F1, la v5 ex ante empata o pierde con la v3.2 publicada",
              "Cambios de liga de t a t+1 con 300 min o más en ambas · cortes 2022-2024 · mismos casos", PIE)
    return _guardar(fig, "f8_protocolo_f1", cfg)


def fig_umbrales(cfg):
    """Criterio 5: diagrama de fiabilidad de P(y_T > u) para los percentiles 25, 50 y 75 de la liga × rol."""
    plt, F = estilo()
    f = pd.read_csv(DIR / "criterio5_fiabilidad.csv")
    fig, ax = plt.subplots(figsize=(6.8, 6.0))
    fig.subplots_adjust(left=0.13, right=0.96, top=0.82, bottom=0.12)
    ax.plot([0, 1], [0, 1], color=S400, lw=1)
    for u, col in ((25, LAKE), (50, RACING), (75, CLAY)):
        g = f[f["umbral"] == u]
        ax.plot(g["p_media"], g["frecuencia"], "o-", color=col, ms=5, label=f"Supera el percentil {u} de su liga y rol")
    ax.set_xlabel("Probabilidad publicada")
    ax.set_ylabel("Frecuencia observada")
    for a in (ax.xaxis, ax.yaxis):
        a.set_major_formatter(lambda v, p: f"{v:.1f}".replace(".", ","))
    ax.legend(loc="upper left", fontsize=8)
    _cabecera(fig, ax, F, "Las probabilidades de umbral están calibradas (error medio 1,4–3,0 puntos)",
              f"Predictivo publicado (ex ante) · temporadas 2023-24 a 2025-26 · "
              f"{pd.read_csv(DIR / 'criterio5_umbrales.csv')['metrica'].nunique() - 1} métricas", PIE)
    return _guardar(fig, "f8_fiabilidad_umbrales", cfg)


def fig_sbc(cfg):
    """SBC de λ: histograma del rango normalizado del λ verdadero."""
    plt, F = estilo()
    d = pd.read_csv(DIR / "sbc_lambda.csv.gz")
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    fig.subplots_adjust(left=0.11, right=0.96, top=0.80, bottom=0.14)
    ax.hist(d["u"], bins=20, range=(0, 1), color=LAKE, alpha=0.8)
    ax.axhline(len(d) / 20, color=RACING, lw=1.5)
    ax.set_xlabel("Rango normalizado del λ verdadero en su posterior (uniforme si está calibrado)")
    ax.set_ylabel("Réplicas × ligas × métricas")
    ax.xaxis.set_major_formatter(lambda v, p: f"{v:.1f}".replace(".", ","))
    _cabecera(fig, ax, F, "El estimador de λ del paso 2 está calibrado en simulación",
              f"SBC · {d['replica'].nunique()} réplicas × {d['metrica'].nunique()} métricas con el diseño real · cobertura del 80 %: "
              f"{((d['u'] > 0.1) & (d['u'] < 0.9)).mean() * 100:.1f} %".replace(".", ","), PIE)
    return _guardar(fig, "f8_sbc_lambda", cfg)


def todas(cfg):
    return {f.__name__: str(f(cfg)) for f in (fig_fichajes, fig_protocolo, fig_umbrales, fig_sbc)}
