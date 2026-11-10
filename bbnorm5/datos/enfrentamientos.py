"""F2 §6.6 · Club ↔ liga doméstica y fuerza de ligas por enfrentamientos europeos (sin usar jugadores).

1. **Club europeo → club y liga doméstica, por temporada** (`clubes_europeos.csv`):
   - un equipo de EuroLeague, EuroCup, BCL o FEC y un equipo de una liga doméstica que comparten ≥ 3 personas esa
     temporada son el mismo club (`entidades.pares_de_clubes`);
   - si hay varios, gana el de más personas compartidas;
   - confianza: alta con ≥ 5, media con 3–4;
   - las correcciones del usuario en `correcciones_clubes.csv` (columnas temporada, liga_eur, team_eur, liga_dom,
     team_dom) prevalecen.
2. **Partidos europeos** (`partidos.parquet`): `data/processed/<t>/entrenadores/<comp>_partidos.csv`, una fila por
   partido (local, visitante, margen) con la liga doméstica de cada equipo.
3. **Modelo de comparación por pares con margen** (Thurstone-Mosteller gaussiano, la versión con margen del
   Bradley-Terry), por temporada:
       margen_g = (s_local − s_visitante) + h + ε,   ε ~ N(0, σ²)
       s_equipo = L_{liga doméstica} + u_equipo,      u ~ N(0, τ²)
   - L: fuerza de cada liga doméstica (efecto fijo; ACB = 0 como referencia de presentación);
   - u: desviación propia del equipo, contraída;
   - h: ventaja de campo.
   τ² se elige por verosimilitud marginal en una rejilla.
   Los equipos sin liga doméstica en los datos (ABA, Israel, LKL…) entran con L = «sin_liga_<competición>», para que
   sus partidos informen a sus rivales sin contaminar ninguna liga.
   **Sin fuga**: la fuerza de la temporada t sólo usa partidos de la temporada t.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from bbnorm5 import config as C

COMPS = ["euroleague", "eurocup", "bcl", "fec"]
DOMESTICAS = ["acb", "lba", "bbl", "lnb", "bsl", "gbl", "vtb", "bnxt", "feb1", "feb2", "feb3", "cba", "nbl"]
DIR = C.DIR_DATOS / "limpios" / "enfrentamientos"


def clubes_europeos(pares: pd.DataFrame) -> pd.DataFrame:
    p = pares.copy()
    # orientar: liga_eur en la competición europea, liga_dom en la doméstica
    filas = []
    for r in p.itertuples(index=False):
        for (le, te, ld, td) in ((r.liga_a, r.team_a, r.liga_b, r.team_b), (r.liga_b, r.team_b, r.liga_a, r.team_a)):
            if le in COMPS and ld in DOMESTICAS:
                filas.append({"temporada": r.temporada, "liga_eur": le, "team_eur": str(te), "liga_dom": ld,
                              "team_dom": str(td), "compartidos": r.compartidos})
    c = pd.DataFrame(filas)
    if c.empty:
        return c
    c = c.sort_values("compartidos", ascending=False).drop_duplicates(["temporada", "liga_eur", "team_eur"])
    c["confianza"] = np.where(c["compartidos"] >= 5, "alta", "media")
    c["origen"] = "automatico"
    corr = DIR / "correcciones_clubes.csv"
    if corr.exists():
        k = pd.read_csv(corr, dtype=str)
        c = pd.concat([k.assign(origen="usuario", confianza="usuario"),
                       c[~c.set_index(["temporada", "liga_eur", "team_eur"]).index.isin(
                           k.set_index(["temporada", "liga_eur", "team_eur"]).index)]], ignore_index=True)
    return c.sort_values(["temporada", "liga_eur", "team_eur"]).reset_index(drop=True)


def partidos(temporadas: list[str], clubes: pd.DataFrame) -> pd.DataFrame:
    fr = []
    for t in temporadas:
        for comp in COMPS:
            f = C.RAIZ / "data" / "processed" / t / "entrenadores" / f"{comp}_partidos.csv"
            if not f.exists():
                continue
            d = pd.read_csv(f, dtype={"equipo_id": str, "rival_id": str, "game_id": str})
            d = d[d["local"].astype(str).isin(["1", "True", "true"])]
            fr.append(d.assign(competicion=comp, temporada=t))
    d = pd.concat(fr, ignore_index=True)
    mapa = {(r.temporada, r.liga_eur, r.team_eur): r.liga_dom for r in clubes.itertuples(index=False)}
    d["liga_local"] = [mapa.get((t, c, e), f"sin_liga_{c}") for t, c, e in zip(d["temporada"], d["competicion"], d["equipo_id"])]
    d["liga_visitante"] = [mapa.get((t, c, e), f"sin_liga_{c}") for t, c, e in zip(d["temporada"], d["competicion"], d["rival_id"])]
    d["margen"] = pd.to_numeric(d["puntos"], errors="coerce") - pd.to_numeric(d["puntos_rival"], errors="coerce")
    cols = ["temporada", "competicion", "game_id", "fecha", "fase", "equipo_id", "equipo", "rival_id", "liga_local",
            "liga_visitante", "puntos", "puntos_rival", "margen"]
    return d[[c for c in cols if c in d]].rename(columns={"equipo_id": "local_id", "equipo": "local", "rival_id": "visitante_id"})


def ajustar_temporada(g: pd.DataFrame, referencia: str = "acb", rejilla=np.geomspace(0.002, 5, 45)) -> dict:
    """GLS del modelo de pares con margen; τ² por verosimilitud marginal. Devuelve fuerzas de liga con su DT."""
    g = g.dropna(subset=["margen"])
    equipos = sorted(set(g["local_id"]) | set(g["visitante_id"]))
    liga_de = {}
    for e, l in zip(g["local_id"], g["liga_local"]):
        liga_de[e] = l
    for e, l in zip(g["visitante_id"], g["liga_visitante"]):
        liga_de.setdefault(e, l)
    ligas = sorted(set(liga_de.values()))
    if referencia not in ligas:
        referencia = max(ligas, key=lambda l: sum(v == l for v in liga_de.values()))
    li = [l for l in ligas if l != referencia]
    ie, il = {e: k for k, e in enumerate(equipos)}, {l: k for k, l in enumerate(li)}
    n = len(g)
    Z = np.zeros((n, len(equipos)))
    X = np.zeros((n, len(li) + 1))
    X[:, -1] = 1.0                                       # ventaja de campo
    for k, (a, b) in enumerate(zip(g["local_id"], g["visitante_id"])):
        Z[k, ie[a]] += 1
        Z[k, ie[b]] -= 1
        if liga_de[a] in il:
            X[k, il[liga_de[a]]] += 1
        if liga_de[b] in il:
            X[k, il[liga_de[b]]] -= 1
    y = g["margen"].to_numpy(float)
    mejor = None
    for lam in rejilla:                                  # lam = τ²/σ²; V = σ²(I + lam ZZ')
        V0 = np.eye(n) + lam * Z @ Z.T
        Vi = np.linalg.inv(V0)
        XtVX = X.T @ Vi @ X
        beta = np.linalg.solve(XtVX, X.T @ Vi @ y)
        r = y - X @ beta
        s2 = float(r @ Vi @ r) / (n - X.shape[1])
        ll = -0.5 * (n * np.log(s2) + np.linalg.slogdet(V0)[1] + np.linalg.slogdet(XtVX / s2)[1] + n - X.shape[1])
        if mejor is None or ll > mejor[0]:
            mejor = (ll, lam, beta, s2, np.linalg.inv(XtVX) * s2)
    ll, lam, beta, s2, cov = mejor
    filas = [{"liga": referencia, "fuerza": 0.0, "sd": 0.0}] + \
        [{"liga": l, "fuerza": float(beta[il[l]]), "sd": float(np.sqrt(cov[il[l], il[l]]))} for l in li]
    f = pd.DataFrame(filas)
    f["equipos"] = f["liga"].map(pd.Series(list(liga_de.values())).value_counts()).fillna(0).astype(int)
    f["partidos"] = [int(((g["liga_local"] == l) | (g["liga_visitante"] == l)).sum()) for l in f["liga"]]
    return {"ligas": f, "ventaja_campo": float(beta[-1]), "sd_ventaja": float(np.sqrt(cov[-1, -1])),
            "sigma": float(np.sqrt(s2)), "tau": float(np.sqrt(lam * s2)), "partidos": int(n), "referencia": referencia}


def construir(temporadas: list[str]) -> dict:
    DIR.mkdir(parents=True, exist_ok=True)
    pares = pd.read_csv(C.DIR_DATOS / "limpios" / "entidades" / "pares_de_clubes.csv", dtype=str)
    pares["compartidos"] = pares["compartidos"].astype(int)
    cl = clubes_europeos(pares)
    cl.to_csv(DIR / "clubes_europeos.csv", index=False)
    p = partidos(temporadas, cl)
    p.to_parquet(DIR / "partidos.parquet", index=False)
    fuerzas, params = [], []
    for t, g in p.groupby("temporada"):
        r = ajustar_temporada(g)
        fuerzas.append(r["ligas"].assign(temporada=t))
        params.append({"temporada": t, **{k: v for k, v in r.items() if k != "ligas"}})
        print(f"  {t}: {r['partidos']} partidos · campo {r['ventaja_campo']:.2f} · σ {r['sigma']:.1f} · τ {r['tau']:.1f}",
              flush=True)
    F = pd.concat(fuerzas, ignore_index=True)
    F.to_csv(DIR / "fuerza_ligas.csv", index=False)
    pd.DataFrame(params).to_csv(DIR / "parametros.csv", index=False)
    cob = p.assign(ambos=~p["liga_local"].str.startswith("sin_liga") & ~p["liga_visitante"].str.startswith("sin_liga"),
                   distintas=lambda x: x["liga_local"] != x["liga_visitante"])
    resumen = cob.groupby(["temporada", "competicion"]).agg(partidos=("game_id", "count"), con_dos_ligas=("ambos", "mean"),
                                                             entre_ligas_distintas=("distintas", "mean")).reset_index()
    resumen.to_csv(DIR / "cobertura.csv", index=False)
    return {"clubes": int(len(cl)), "partidos": int(len(p))}
