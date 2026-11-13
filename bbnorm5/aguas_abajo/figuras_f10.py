"""F10 · Figuras del informe 10_viabilidad_aguas_abajo (marca Kerno v2.0). Títulos calculados con los datos."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from bbnorm5 import config as C
from bbnorm5.diagnostico.figuras import CLAY, LAKE, RACING, S400, _cabecera, _guardar, estilo
from bbnorm5.medida.figuras import NOM

PIE = "Datos públicos · fichajes reales de los cortes 2022-23 a 2024-25 · Kerno Analytics · v5.0 F10"
DIR = C.DIR_DATOS / "aguas_abajo"
NOM = {**NOM, "pct_aro": "% aro", "pct_corta": "% corta", "pct_media": "% media", "pct_t3_esquina": "% T3 esquina",
       "pct_asistidas": "% asistidas"}


def _n(v, d=2):
    return f"{v:.{d}f}".replace(".", ",")


def fig_nivel_kerno(cfg):
    """Correlación de rangos del Nivel Kerno con el percentil realizado: vigente, v3.3 ensamblada, v5 nivel, v5 pred."""
    plt, F = estilo()
    m = json.loads((DIR / "meta_nivel_kerno.json").read_text())
    s = m["spearman_pct_realizado"]
    filas = [("NK1 vigente", s["NC1"], S400), ("v3.3 ensamblada como la v5", s["V33E"], S400),
             ("v5 · intervalo de nivel", s["V5N"], LAKE), ("v5 · predictivo", s["V5P"], RACING)]
    fig, ax = plt.subplots(figsize=(8.2, 4.2))
    fig.subplots_adjust(left=0.30, right=0.96, top=0.78, bottom=0.16)
    for i, (et, v, col) in enumerate(filas[::-1]):
        ax.hlines(i, v["ic"][0], v["ic"][1], color=col, lw=5, alpha=0.45)
        ax.plot(v["rho"], i, "o", color=col, ms=8)
        ax.text(v["ic"][1] + 0.004, i, _n(v["rho"]), va="center", fontsize=8)
    ax.set_yticks(range(len(filas)), [f[0] for f in filas[::-1]])
    ax.set_xlabel("Correlación de rangos con el percentil realizado (IC 95 % por bootstrap de personas)")
    ax.xaxis.set_major_formatter(lambda v, p: _n(v))
    _cabecera(fig, ax, F, f"El Nivel Kerno con la v5 ordena mejor los fichajes: {_n(s['V5P']['rho'])} frente a "
                          f"{_n(s['NC1']['rho'])}",
              f"{m['fichajes']} fichajes · misma referencia liga × puesto y misma calibración · dos tercios de la mejora "
              f"son el ensamblaje", PIE)
    return _guardar(fig, "f10_nivel_kerno", cfg)


def fig_agregacion(cfg):
    """Cobertura del 80 % y anchura relativa: jugador, equipo (suma de fichajes) y grupos de cinco."""
    plt, F = estilo()
    m = json.loads((DIR / "meta_por_partido.json").read_text())
    j, e, q = m["jugador"], m["equipo"], m["cinco"]
    filas = [("Jugador · C v3.3 publicada", j["v33"]["cobertura80"], S400),
             ("Jugador · C v5", j["v5"]["cobertura80"], RACING),
             ("Equipo · v3.3, fichajes independientes", e["v33_independientes"]["cobertura80"], S400),
             ("Equipo · v5, fichajes independientes", e["v5_independientes"]["cobertura80"], LAKE),
             ("Equipo · v5, correlación entre compañeros", e["v5_companeros"]["cobertura80"], RACING),
             ("Cinco a la misma liga · v5 independientes", q["v5_independientes"]["cobertura80"], LAKE),
             ("Cinco a la misma liga · v5 con efecto de liga común", q["v5_misma_liga"]["cobertura80"], RACING)]
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    fig.subplots_adjust(left=0.40, right=0.96, top=0.80, bottom=0.14)
    ax.axvspan(0.76, 0.84, color=RACING, alpha=0.08)
    ax.axvline(0.8, color=RACING, lw=1)
    for i, (et, v, col) in enumerate(filas[::-1]):
        ax.barh(i, v, color=col, alpha=0.8, height=0.6)
        ax.text(v + 0.005, i, _n(v), va="center", fontsize=8)
    ax.set_yticks(range(len(filas)), [f[0] for f in filas[::-1]])
    ax.set_xlim(0.4, 1.0)
    ax.xaxis.set_major_formatter(lambda v, p: _n(v, 1))
    ax.set_xlabel("Cobertura de la banda del 80 % (franja: 0,76–0,84)")
    _cabecera(fig, ax, F, "Al agregar, la v5 con los minutos del motor mantiene la cobertura; la v3.3 cruda no",
              f"Contribución por partido · {e['v5_companeros']['equipos']} equipos con 2 o más fichajes · "
              f"{q['v5_misma_liga']['grupos']} grupos de cinco", PIE)
    return _guardar(fig, "f10_agregacion", cfg)


def fig_impacto(cfg):
    """Predicción del RAPM de t+1: siguen en su liga frente a cambian, por conjunto de información."""
    plt, F = estilo()
    t = pd.read_csv(DIR / "impacto_prediccion.csv")
    t = t[(t["objetivo"] == "rapm") & t["grupo"].isin(["siguen", "cambian"])]
    et = {"t": "RAPM de t", "carrera": "+ RAPM de t−1 (carrera)", "carrera_perfil": "+ perfil de nivel v5",
          "carrera_perfil_grafo": "+ traducción v5 (grafo)", "perfil": "Sólo perfil v5"}
    orden = ["t", "carrera", "carrera_perfil", "carrera_perfil_grafo", "perfil"]
    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    fig.subplots_adjust(left=0.28, right=0.96, top=0.80, bottom=0.14)
    for k, (g, col) in enumerate((("siguen", LAKE), ("cambian", CLAY))):
        x = t[t["grupo"] == g].set_index("conjunto").loc[orden]
        y = np.arange(len(orden))[::-1] + (0.18 if k == 0 else -0.18)
        ax.barh(y, x["spearman"], height=0.34, color=col, alpha=0.85,
                label=f"{'Siguen en su liga' if g == 'siguen' else 'Cambian de liga'} ({int(x['casos'].iloc[0])})")
    ax.set_yticks(np.arange(len(orden))[::-1], [et[o] for o in orden])
    ax.xaxis.set_major_formatter(lambda v, p: _n(v, 2))
    ax.set_xlabel("Correlación de rangos con el RAPM observado de t+1 (fuera de tiempo)")
    ax.set_xlim(0, max(0.5, t["spearman"].max() + 0.12))
    ax.legend(loc="upper right", fontsize=8)
    c = t[(t["grupo"] == "cambian")].set_index("conjunto")
    _cabecera(fig, ax, F, f"El RAPM no viaja entre ligas ({_n(c.loc['t', 'spearman'])}); con la v5 y su traducción, "
                          f"{_n(c.loc['carrera_perfil_grafo', 'spearman'])}",
              "RAPM por liga-temporada (ridge) · temporadas de prueba 2023-24 a 2025-26 · entrenado con las anteriores",
              "Datos públicos · jugadores con 500 posesiones o más en t y en t+1 · Kerno Analytics · v5.0 F10")
    return _guardar(fig, "f10_impacto_rapm", cfg)


def fig_landing(cfg):
    """Efecto de la primera temporada en liga nueva por métrica y grupo (DT del residuo), con identificabilidad."""
    plt, F = estilo()
    t = pd.read_csv(DIR / "landing_delta.csv")
    t = t[(t["fase"] == "primera") & (t["grupo"] != "todos")]
    grupos = ["europa", "a_euroleague", "feb", "nba_gleague"]
    eg = {"europa": "Entre ligas europeas", "a_euroleague": "A la EuroLeague", "feb": "Con las FEB",
          "nba_gleague": "Con NBA y G League"}
    mets = t.groupby("metrica")["delta"].apply(lambda s: s.abs().mean()).sort_values().index.tolist()
    M = t.pivot_table(index="metrica", columns="grupo", values="delta").loc[mets, grupos]
    S = t.pivot_table(index="metrica", columns="grupo", values="se").loc[mets, grupos]
    fig, ax = plt.subplots(figsize=(8.2, 7.2))
    fig.subplots_adjust(left=0.20, right=0.92, top=0.86, bottom=0.10)
    im = ax.imshow(M.to_numpy(), cmap="RdBu_r", vmin=-0.4, vmax=0.4, aspect="auto")
    ax.grid(False)
    for i in range(M.shape[0]):
        for k in range(M.shape[1]):
            v, s = M.iat[i, k], S.iat[i, k]
            sig = abs(v) > 1.96 * s
            oscuro = abs(v) > 0.22
            ax.text(k, i, _n(v), ha="center", va="center", fontsize=7.5, fontweight="bold" if sig else "normal",
                    color=("white" if oscuro else "black") if sig else ("#E6E9E7" if oscuro else S400))
    ax.set_xticks(range(len(grupos)), [f"{eg[g]}\nDT ±{_n(S[g].median())}" for g in grupos], fontsize=8)
    ax.set_yticks(range(len(mets)), [NOM.get(m, m) for m in mets])
    fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    n_id = int(t["identificable"].sum())
    _cabecera(fig, ax, F, f"No hay penalización general por cambiar de liga; el efecto sólo se identifica en {n_id} "
                          f"de {len(t)} celdas",
              "Primera temporada en DT del residuo · negrita: IC 95 % sin el 0 · en FEB y NBA domina la traducción",
              "Datos públicos · transiciones de 2020-21 a 2025-26 con 300 min o más · Kerno Analytics · v5.0 F10")
    return _guardar(fig, "f10_landing", cfg)


def todas(cfg):
    return {f.__name__: str(f(cfg)) for f in (fig_nivel_kerno, fig_agregacion, fig_impacto, fig_landing)}
