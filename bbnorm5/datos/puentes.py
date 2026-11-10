"""F2 §6.1, §6.4 y §6.5 · Unidad de análisis v5, puentes intra-temporada y entre temporadas, grafo de ligas.

**Unidad** (`unidades.parquet`): persona_v5 × equipo × competición × temporada × fase, desde la caja jugador-partido
v5. Lleva:
- conteos de la caja;
- partidos, titularidades y minutos;
- exposición por familia de métrica:
  - posesiones en pista ≈ (min / (min de equipo / 5)) × posesiones del equipo;
  - oportunidades de rebote ofensivo y defensivo en pista;
  - tiros de campo y libres;
  - jugadas (TC + 0,44·TL + pérdidas);
- rol: minutos por partido, % de titularidades y cuota de los minutos del equipo;
- calidad media del rival: margen medio por partido del rival en esa competición, ponderado por los partidos que
  jugó contra él.

**Puentes intra-temporada** (`puentes_intra.parquet`): pares de unidades de la misma persona y temporada, fase
regular, en dos competiciones distintas.

| Tipo | Definición |
|---|---|
| `mismo_club` | El mismo club en una competición europea y en su liga doméstica (`clubes_europeos.csv`) o en dos competiciones europeas. Es la diferencia más limpia: mismo vestuario, mismo entrenador |
| `nba_gleague` | Contrato doble NBA ↔ G League |
| `traspaso_temporada` | Equipos distintos de dos competiciones la misma temporada (cambio a mitad de temporada) |

**Puentes entre temporadas** (`puentes_inter.parquet`): persona cuya liga principal (la de más minutos de la
temporada regular) cambia de t a t+1, con ≥ 150 min en ambas.
- Lleva la edad, el cambio de minutos por partido y de rol (titularidad, cuota de minutos) y la temporada previa
  completa.
- Es la población del modelo de selección (F7).

**Grafo** (`grafo_ligas.csv` y la figura):
- nodos: competiciones;
- aristas: personas puente de la misma temporada con ≥ 150 min en ambas, ponderadas por exposición (suma de la media
  armónica de minutos).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from bbnorm5 import config as C

DIR = C.DIR_DATOS / "puentes"
EUROPEAS = {"euroleague", "eurocup", "bcl", "fec"}
PIE_F2 = "Datos públicos · 20 competiciones, 2020-21 a 2026-27 (en curso) · Kerno Analytics · v5.0 F2"
NUM = ["min", "pts", "fgm", "fga", "fg2m", "fg2a", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "reb", "ast", "stl",
       "tov", "blk", "pf"]


def caja(temporadas: list[str]) -> pd.DataFrame:
    fr = []
    for t in temporadas:
        for f in sorted((C.DIR_DATOS / "limpios" / "caja_partido" / t).glob("*.parquet")):
            d = pd.read_parquet(f)
            d = d[d["jugo"] & d["player_id"].notna()].copy()
            cols = ["liga", "temporada", "game_id", "fecha", "fase", "team_id", "opp_id", "player_id", "starter"] + \
                   [c for c in NUM if c in d] + [f"team_{c}" for c in NUM if f"team_{c}" in d] + \
                   [f"opp_{c}" for c in NUM if f"opp_{c}" in d]
            fr.append(d[[c for c in cols if c in d]])
    d = pd.concat(fr, ignore_index=True)
    for c in ("team_id", "opp_id", "player_id"):
        d[c] = d[c].astype(str)
    return d


def _posesiones(fga, oreb, tov, fta):
    return fga - oreb + tov + 0.44 * fta


def unidades(d: pd.DataFrame, personas: pd.DataFrame) -> pd.DataFrame:
    p = personas.set_index(["fuente_liga", "fuente_id"])["persona_v5"]
    d = d.copy()
    d["persona_v5"] = [p.get((l, i)) for l, i in zip(d["liga"], d["player_id"])]
    d = d.dropna(subset=["persona_v5"])
    tm = d["team_min"].where(d["team_min"] > 0)
    d["frac"] = (d["min"] / (tm / 5)).clip(0, 1)
    d["poss_on"] = d["frac"] * _posesiones(d["team_fga"], d["team_oreb"], d["team_tov"], d["team_fta"])
    d["oreb_op"] = d["frac"] * (d["team_oreb"] + d["opp_dreb"])
    d["dreb_op"] = d["frac"] * (d["team_dreb"] + d["opp_oreb"])
    d["plays"] = d["fga"] + 0.44 * d["fta"] + d["tov"]
    d["titular"] = d["starter"].astype(str).str.lower().isin(["true", "1"])
    d["margen_eq"] = d["team_pts"] - d["opp_pts"]
    # calidad del rival: margen medio del rival en la competición-temporada-fase
    eqm = d.drop_duplicates(["liga", "temporada", "fase", "game_id", "team_id"]).groupby(
        ["liga", "temporada", "fase", "team_id"])["margen_eq"].mean().rename("margen_rival")
    d = d.merge(eqm, left_on=["liga", "temporada", "fase", "opp_id"], right_index=True, how="left")
    clave = ["persona_v5", "liga", "temporada", "fase", "team_id"]
    agg = {c: "sum" for c in NUM + ["poss_on", "oreb_op", "dreb_op", "plays"] if c in d}
    u = d.groupby(clave).agg({**agg, "game_id": "nunique", "titular": "mean", "margen_rival": "mean",
                              "team_min": "sum", "player_id": "first"}).reset_index()
    u = u.rename(columns={"game_id": "partidos", "titular": "pct_titular", "margen_rival": "rival_margen"})
    u["min_pp"] = u["min"] / u["partidos"]
    u["cuota_min"] = u["min"] / (u["team_min"] / 5)
    u["anio"] = u["temporada"].str[:4].astype(int)
    return u.drop(columns="team_min")


def puentes_intra(u: pd.DataFrame, clubes: pd.DataFrame, min_min: float = 0.0) -> pd.DataFrame:
    r = u[(u["fase"] == "regular") & (u["min"] > min_min)]
    a = r.merge(r, on=["persona_v5", "temporada"], suffixes=("_a", "_b"))
    a = a[a["liga_a"] < a["liga_b"]]
    club = {(t, le, te): (ld, td) for t, le, te, ld, td in
            zip(clubes["temporada"], clubes["liga_eur"], clubes["team_eur"].astype(str), clubes["liga_dom"], clubes["team_dom"].astype(str))}

    def tipo(x):
        if {x.liga_a, x.liga_b} == {"nba", "gleague"}:
            return "nba_gleague"
        for (le, te, ld, td) in ((x.liga_a, x.team_id_a, x.liga_b, x.team_id_b), (x.liga_b, x.team_id_b, x.liga_a, x.team_id_a)):
            if club.get((x.temporada, le, te)) == (ld, td):
                return "mismo_club"
        if x.liga_a in EUROPEAS and x.liga_b in EUROPEAS:
            return "mismo_club_europeo?"
        return "traspaso_temporada"
    a["tipo"] = [tipo(x) for x in a.itertuples(index=False)]
    a["min_armonica"] = 2 / (1 / a["min_a"] + 1 / a["min_b"])
    return a


def puentes_inter(u: pd.DataFrame, nac_persona: pd.Series, min_min: float = 150.0) -> pd.DataFrame:
    r = u[u["fase"] == "regular"]
    prin = r.sort_values("min", ascending=False).drop_duplicates(["persona_v5", "anio"])
    prin = prin[prin["min"] >= min_min]
    sig = prin.assign(anio=prin["anio"] - 1)
    x = prin.merge(sig, on=["persona_v5", "anio"], suffixes=("_t", "_t1"))
    x = x[x["liga_t"] != x["liga_t1"]].copy()
    x["edad_t"] = x["anio"] - x["persona_v5"].map(nac_persona)
    x["d_min_pp"] = x["min_pp_t1"] - x["min_pp_t"]
    x["d_cuota_min"] = x["cuota_min_t1"] - x["cuota_min_t"]
    x["d_titular"] = x["pct_titular_t1"] - x["pct_titular_t"]
    return x


def grafo(pi: pd.DataFrame, min_min: float = 150.0) -> pd.DataFrame:
    g = pi[(pi["min_a"] >= min_min) & (pi["min_b"] >= min_min)]
    return g.groupby(["liga_a", "liga_b"]).agg(personas=("persona_v5", "nunique"), puentes=("persona_v5", "size"),
                                                exposicion=("min_armonica", "sum"),
                                                mismo_club=("tipo", lambda s: int((s == "mismo_club").sum()))).reset_index()


POSICIONES = {  # disposición fija y legible: Europa en el centro, domésticas arriba, resto abajo
    "euroleague": (-1.5, 0.0), "eurocup": (-0.5, 0.0), "bcl": (0.5, 0.0), "fec": (1.5, 0.0),
    "acb": (-3.2, 1.6), "lba": (-2.1, 1.9), "lnb": (-1.0, 2.1), "bbl": (0.1, 2.1), "gbl": (1.2, 1.9),
    "bsl": (2.3, 1.6), "vtb": (3.3, 1.1), "bnxt": (3.4, 0.0),
    "nba": (-3.4, -1.5), "gleague": (-2.2, -2.1), "ncaa": (-1.0, -2.4), "cba": (2.2, -2.0), "nbl": (3.3, -1.4),
    "feb1": (-3.8, 0.0), "feb2": (-4.6, -0.6), "feb3": (-4.6, 0.6)}


def dibujar_grafo(G: pd.DataFrame, ruta, pie: str = "") -> None:
    from bbnorm5.diagnostico import figuras as F
    plt, fu = F.estilo()
    fig, ax = plt.subplots(figsize=(10.4, 7.4))
    fig.subplots_adjust(left=0.02, right=0.98, top=0.86, bottom=0.07)
    ax.axis("off")
    ax.set_xlim(-5.2, 4.0)
    ax.set_ylim(-2.9, 2.6)
    g = G[G["personas"] >= 3]
    wmax = g["exposicion"].max()
    for r in g.sort_values("exposicion").itertuples(index=False):
        (xa, ya), (xb, yb) = POSICIONES[r.liga_a], POSICIONES[r.liga_b]
        w = r.exposicion / wmax
        ax.plot([xa, xb], [ya, yb], color=F.R600 if w > 0.08 else F.S300, lw=0.5 + 9 * w, alpha=0.9, zorder=1,
                solid_capstyle="butt")
    grado = pd.concat([G.rename(columns={"liga_a": "l"})[["l", "exposicion"]],
                       G.rename(columns={"liga_b": "l"})[["l", "exposicion"]]]).groupby("l")["exposicion"].sum()
    for n, (x, y) in POSICIONES.items():
        if n not in grado:
            continue
        eur = n in EUROPEAS
        ax.scatter([x], [y], s=180 + 1100 * grado[n] / grado.max(), color=F.CHALK if eur else F.RACING,
                   edgecolor=F.RACING, linewidth=1.8, zorder=2)
        ax.text(x, y - 0.27, n.upper(), ha="center", va="top", fontfamily=fu["dato"], fontsize=8.2, color=F.INK, zorder=3,
                bbox=dict(boxstyle="round,pad=0.15", fc=F.CHALK, ec="none", alpha=0.85))
    debil = list(grado.sort_values().index[:5])
    F._cabecera(fig, ax, fu, "Las copas europeas atan las ligas domésticas; NCAA, FEB, CBA y NBL cuelgan de pocas aristas",
                f"Puentes de la misma temporada con 150+ min en ambas · grosor: minutos (media armónica) · aristas con 3+ personas · "
                f"menos conectadas: {', '.join(x.upper() for x in debil)}", pie)
    fig.savefig(ruta, dpi=160)
    plt.close(fig)


def construir(temporadas: list[str]) -> dict:
    from bbnorm5.datos import entidades as N
    DIR.mkdir(parents=True, exist_ok=True)
    personas = pd.read_csv(C.DIR_DATOS / "limpios" / "entidades" / "personas_v5.csv", dtype=str)
    clubes = pd.read_csv(C.DIR_DATOS / "limpios" / "enfrentamientos" / "clubes_europeos.csv", dtype=str)
    d = caja(temporadas)
    u = unidades(d, personas)
    u.to_parquet(DIR / "unidades.parquet", index=False, compression="zstd")
    # nacimiento por persona_v5 (mediana de sus nodos)
    cw = pd.read_csv(C.RAIZ / "data" / "processed" / "player_id_crosswalk.csv", dtype=str)
    nac = N.evidencia_nacimiento(cw, N.filas_procesadas(temporadas))
    pm = personas.set_index(["fuente_liga", "fuente_id"])["persona_v5"]
    nac_p = pd.Series({pm.get(k): v for k, v in nac.items() if np.isfinite(v) and pm.get(k) is not None})
    nac_p = nac_p.groupby(level=0).median()
    pi = puentes_intra(u, clubes)
    pi.to_parquet(DIR / "puentes_intra.parquet", index=False, compression="zstd")
    pe = puentes_inter(u, nac_p)
    pe.to_parquet(DIR / "puentes_inter.parquet", index=False, compression="zstd")
    G = grafo(pi)
    G.to_csv(DIR / "grafo_ligas.csv", index=False)
    dibujar_grafo(G, C.RAIZ / "docs" / "v5" / "figuras" / "f2_grafo_ligas.png", PIE_F2)
    return {"unidades": int(len(u)), "personas": int(u["persona_v5"].nunique()), "puentes_intra": int(len(pi)),
            "puentes_inter": int(len(pe)), "aristas": int(len(G))}
