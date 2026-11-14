"""F10 · Prototipo de la proyección por partido: producción de la v5 × minutos del motor v3.3 (revisión 1.2, F10).

No toca el simulador publicado. Lee las predicciones guardadas del examen de fichajes V32_corte (minutos y contribución
de la v3.3; las cachés del simulador no están en el repositorio) y las de la v5 publicada en la F8, y compara en los
mismos fichajes.

Objeto: la **contribución** C = (minutos por partido ÷ minutos del partido) × pts/100, la cantidad sobre la que se
construye el Nivel Kerno (bbequipo/anclas.py).

    C_v5 = M_v3.3 / gm × P_v5

- M: predictiva de minutos por partido del motor v3.3 (cuantiles lo90…hi90 guardados).
- P: predictiva de pts/100 de la v5 publicada (ex ante, sin estilo de liga, recalibrada; cuantiles 2,5 %…97,5 %).
- Dependencia entre M y P: cópula gaussiana con ρ estimada en los cortes anteriores (PIT de los observados). La v3.3 usa
  el mismo z para el nivel y los minutos (ρ = 1 a nivel de jugador).

Agregación (encargo §14.1):
- **equipo**: suma de C de los fichajes de un mismo equipo y temporada; los compañeros comparten traducción y compiten
  por los minutos. Correlación entre compañeros estimada en los cortes anteriores, frente a la independencia.
- **grupos de cinco**: medias de pts/100 de cinco fichajes a la misma liga y temporada (la estructura de un quinteto en
  la parte de la producción: comparten λ de destino). Con independencia y con la correlación estimada.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from bbnorm5 import config as C
from bbnorm5.validacion import fichajes as VF

V33 = C.RAIZ / "data" / "modelos" / "simulador" / "v3_2" / "validacion" / "V32_corte_inicio_adapt" / "predicciones.csv.gz"
CASOS = C.DIR_DATOS / "validacion" / "examen_fichajes_casos_recal.parquet"
MODELO = "ex_ante_sin_estilo_liga_recal"
Q_V33 = [("lo90", 0.05), ("lo80", 0.10), ("lo50", 0.25), ("pred", 0.50), ("hi50", 0.75), ("hi80", 0.90), ("hi90", 0.95)]
Q_V5 = [0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.975]
NIV = {50: (0.25, 0.75), 80: (0.10, 0.90), 90: (0.05, 0.95)}


# ------------------------------------------------------------------ funciones cuantil
def cuantil(u: np.ndarray, p: np.ndarray, v: np.ndarray, minimo: float = 0.0) -> np.ndarray:
    """Función cuantil lineal a trozos por fila (como anclas.muestras_predictivas), con colas prolongadas.
    u: (n, S) uniformes; p: niveles (k,); v: valores (n, k)."""
    v = np.maximum.accumulate(v, axis=1)
    k = np.clip(np.searchsorted(p, u, side="right") - 1, 0, len(p) - 2)       # tramo (con colas: el primero o el último)
    p0, p1 = p[k], p[k + 1]
    v0 = np.take_along_axis(v, k, axis=1)
    v1 = np.take_along_axis(v, k + 1, axis=1)
    out = v0 + (u - p0) * (v1 - v0) / np.maximum(p1 - p0, 1e-9)
    return np.maximum(out, minimo)


def cdf(y: np.ndarray, p: np.ndarray, v: np.ndarray) -> np.ndarray:
    """PIT del observado con la misma función cuantil (inversa lineal a trozos, colas lineales, recortada a (0, 1))."""
    v = np.maximum.accumulate(v, axis=1) + np.arange(v.shape[1]) * 1e-9
    out = np.empty(len(y))
    for i in range(len(y)):
        out[i] = np.interp(y[i], v[i], p, left=np.nan, right=np.nan)
        if not np.isfinite(out[i]):                                         # cola: pendiente del último tramo
            j = (0, 1) if y[i] < v[i, 0] else (-2, -1)
            pend = (p[j[1]] - p[j[0]]) / max(v[i, j[1]] - v[i, j[0]], 1e-9)
            out[i] = p[j[0] if y[i] < v[i, 0] else j[1]] + (y[i] - v[i, j[0] if y[i] < v[i, 0] else j[1]]) * pend
    return np.clip(out, 1e-3, 1 - 1e-3)


# ------------------------------------------------------------------ casos
def casos() -> pd.DataFrame:
    c = pd.read_parquet(CASOS)
    c = c[c["metrica"] == "pts_p100"].copy()
    usa = ["persona_id", "liga_d", "team_d", "temporada_d", "min_real", "min_pct_real", "gp_real", "C_real"] + \
          [f"v_min_{s}" for s, _ in Q_V33] + [f"v_C_{s}" for s, _ in Q_V33]
    v = pd.read_csv(V33, usecols=usa, low_memory=False, dtype={"persona_id": str, "team_d": str})
    c["team_d"] = c["team_d"].astype(str)
    d = c.merge(v, on=["persona_id", "liga_d", "team_d", "temporada_d"], how="inner", validate="1:1")
    d["gm"] = d["min_real"] / d["min_pct_real"]
    d = d[np.isfinite(d["gm"]) & (d["gm"] > 0)].copy()
    d["gm"] = d.groupby("liga_d")["gm"].transform("median").round()          # 40 o 48
    return d.reset_index(drop=True)


def _matrices(d: pd.DataFrame):
    pm = np.array([p for _, p in Q_V33])
    vm = d[[f"v_min_{s}" for s, _ in Q_V33]].to_numpy(float)
    vc = d[[f"v_C_{s}" for s, _ in Q_V33]].to_numpy(float)
    pp = np.array(Q_V5)
    vp = d[[f"{MODELO}__{VF._q(q)}" for q in Q_V5]].to_numpy(float)
    vp33 = d[[f"v33_{s}" for s, _ in Q_V33]].to_numpy(float)      # pts/100 publicados de la v3.3 (mismos niveles que M)
    return pm, vm, vc, pp, vp, vp33


def pits(d: pd.DataFrame) -> pd.DataFrame:
    """PIT de los minutos (v3.3) y de pts/100 (v5) observados, en escala normal."""
    pm, vm, _, pp, vp, _ = _matrices(d)
    return d.assign(z_m=stats.norm.ppf(cdf(d["min_real"].to_numpy(float), pm, vm)),
                    z_p=stats.norm.ppf(cdf(d["y"].to_numpy(float), pp, vp)))


def _corr_companeros(z: pd.DataFrame, clave: list[str], col: str) -> float:
    """Correlación intraclase de z entre miembros del mismo grupo (estimador ANOVA, acotado a [−0,5, 0,9])."""
    g = z.groupby(clave)[col]
    n = g.transform("size")
    z = z[n >= 2]
    if z.empty:
        return 0.0
    g = z.groupby(clave)[col]
    k = g.size()
    m = g.mean()
    ssb = float((k * (m - z[col].mean()) ** 2).sum())
    ssw = float(((z[col] - g.transform("mean")) ** 2).sum())
    dfb, dfw = len(k) - 1, len(z) - len(k)
    n0 = (len(z) - (k ** 2).sum() / len(z)) / max(dfb, 1)
    msb, msw = ssb / max(dfb, 1), ssw / max(dfw, 1)
    return float(np.clip((msb - msw) / (msb + (n0 - 1) * msw), -0.5, 0.9))


def dependencias(z: pd.DataFrame, anio: int) -> dict:
    """ρ(M, P) del jugador y correlaciones entre compañeros, con los cortes anteriores a `anio` (0 si no hay)."""
    a = z[z["anio"] < anio]
    if len(a) < 200:
        return {"rho_mp": 0.0, "eq_m": 0.0, "eq_p": 0.0, "liga_p": 0.0, "n": int(len(a))}
    return {"rho_mp": float(np.corrcoef(a["z_m"], a["z_p"])[0, 1]),
            "eq_m": _corr_companeros(a, ["temporada_d", "liga_d", "team_d"], "z_m"),
            "eq_p": _corr_companeros(a, ["temporada_d", "liga_d", "team_d"], "z_p"),
            "liga_p": _corr_companeros(a, ["temporada_d", "liga_d"], "z_p"), "n": int(len(a))}


# ------------------------------------------------------------------ simulación
def simular(d: pd.DataFrame, dep: dict, S: int, rng, rho_mp: float | None = None, companeros: bool = True,
            clave_p: str = "equipo") -> dict:
    """Draws (n, S) de M, P y C con la dependencia dada. `companeros`: factor común por equipo (M y P) y por liga (P)."""
    pm, vm, vc, pp, vp, vp33 = _matrices(d)
    n = len(d)
    r = dep["rho_mp"] if rho_mp is None else rho_mp
    eq = d.groupby(["temporada_d", "liga_d", "team_d"]).ngroup().to_numpy()
    lg = d.groupby(["temporada_d", "liga_d"]).ngroup().to_numpy()
    a_m = max(dep["eq_m"], 0.0) if companeros else 0.0        # los minutos compiten (ρ < 0): no cabe en un factor común
    a_p = max(dep["eq_p"] if clave_p == "equipo" else dep["liga_p"], 0.0) if companeros else 0.0
    gp = eq if clave_p == "equipo" else lg
    e1, e2 = rng.standard_normal((n, S)), rng.standard_normal((n, S))
    fm = rng.standard_normal((eq.max() + 1, S))[eq]
    fp = rng.standard_normal((gp.max() + 1, S))[gp]
    zp = np.sqrt(1 - a_p) * e1 + np.sqrt(a_p) * fp
    zm_ind = r * e1 + np.sqrt(max(1 - r ** 2, 0)) * e2           # dependencia M–P del jugador
    zm = np.sqrt(1 - a_m) * zm_ind + np.sqrt(a_m) * fm
    M = cuantil(stats.norm.cdf(zm), pm, vm)
    P = cuantil(stats.norm.cdf(zp), pp, vp)
    P33 = cuantil(stats.norm.cdf(zp), pm, vp33)
    gm = d["gm"].to_numpy(float)[:, None]
    Cv5 = M / gm * P
    Cv33 = cuantil(rng.uniform(0.0, 1.0, (n, S)), pm, vc)
    # v3.3 ensamblada: mismos minutos y misma dependencia, con los pts/100 publicados de la v3.3 (aísla la producción)
    return {"M": M, "P": P, "C_v5": Cv5, "C_v33": Cv33, "C_v33e": M / gm * P33, "P_v33": P33}


def puntuar(y: np.ndarray, draws: np.ndarray) -> pd.DataFrame:
    q = np.quantile(draws, [0.05, 0.10, 0.25, 0.5, 0.75, 0.90, 0.95], axis=1)
    lo = {90: q[0], 80: q[1], 50: q[2]}
    hi = {90: q[6], 80: q[5], 50: q[4]}
    return pd.DataFrame({"wis": VF.wis(y, q[3], lo, hi), "cubre50": (y >= q[2]) & (y <= q[4]),
                         "cubre80": (y >= q[1]) & (y <= q[5]), "ancho80": q[5] - q[1], "centro": q[3]})


def _boot(personas, a, b, B, rng):
    return VF._boot_ratio(np.asarray(personas), np.asarray(a, float), np.asarray(b, float), B, rng)


# ------------------------------------------------------------------ examen
def ejecutar(cfg: dict) -> dict:
    P = cfg["por_partido"]
    out_dir = C.dir_fase(cfg)
    rng = np.random.default_rng(cfg["semilla"])
    d = pits(casos())
    jug, eqp, cinco, deps = [], [], [], {}
    for anio in sorted(d["anio"].unique()):
        t = d[d["anio"] == anio].reset_index(drop=True)
        dep = dependencias(d, anio)
        deps[int(anio)] = dep
        # --- jugador: C con ρ estimada, con ρ = 0 y con ρ = 1 (la v3.3 comparte z entre nivel y minutos)
        base = simular(t, dep, P["draws"], rng)
        f = puntuar(t["C_real"].to_numpy(float), base["C_v5"]).add_suffix("_v5")
        f = f.join(puntuar(t["C_real"].to_numpy(float), base["C_v33"]).add_suffix("_v33"))
        f = f.join(puntuar(t["C_real"].to_numpy(float), base["C_v33e"]).add_suffix("_v33e"))
        for nom, rho in (("rho0", 0.0), ("rho1", 1.0)):
            s = simular(t, dep, P["draws"], rng, rho_mp=rho)
            f = f.join(puntuar(t["C_real"].to_numpy(float), s["C_v5"])[["wis", "cubre80"]].add_suffix(f"_v5_{nom}"))
        f = pd.concat([t[["persona_v5", "anio", "liga_d", "team_d", "temporada_d", "C_real"]], f], axis=1)
        jug.append(f)
        # --- equipo: suma de C de los fichajes del mismo equipo (≥ 2), con y sin correlación entre compañeros
        g = t.groupby(["temporada_d", "liga_d", "team_d"]).ngroup().to_numpy()
        n_g = np.bincount(g)
        sel = n_g[g] >= 2
        for nom, comp in (("independientes", False), ("companeros", True)):
            s = simular(t, dep, P["draws"], rng, companeros=comp)
            for mod, key in (("v5", "C_v5"), ("v33", "C_v33"), ("v33e", "C_v33e")):
                if mod == "v33" and comp:
                    continue                                     # la v3.3 simula cada fichaje por separado
                Ssum = np.zeros((n_g.size, s[key].shape[1]))
                np.add.at(Ssum, g, s[key])
                ysum = np.bincount(g, t["C_real"].to_numpy(float))
                ok = n_g >= 2
                r = puntuar(ysum[ok], Ssum[ok]).assign(anio=anio, modelo=f"{mod}_{nom}", n=n_g[ok],
                                                       ancho_rel=lambda x: x["ancho80"] / np.maximum(x["centro"], 1e-9))
                eqp.append(r)
            # dispersión del jugador en los mismos equipos (para la razón de agregación)
            pj = puntuar(t["C_real"].to_numpy(float)[sel], s["C_v5"][sel])
            eqp.append(pd.DataFrame({"anio": [anio], "modelo": [f"jugador_{nom}"], "n": [1],
                                     "ancho_rel": [float(np.median(pj["ancho80"] / np.maximum(pj["centro"], 1e-9)))]}))
        # --- grupos de cinco fichajes a la misma liga y temporada: media de pts/100
        orden = rng.permutation(len(t))
        tt = t.iloc[orden].reset_index(drop=True)
        k = tt.groupby(["temporada_d", "liga_d"]).cumcount() // 5
        grp = (tt["temporada_d"] + "|" + tt["liga_d"] + "|" + k.astype(str)).to_numpy()
        tam = pd.Series(grp).map(pd.Series(grp).value_counts()).to_numpy()
        tt = tt[tam == 5].reset_index(drop=True)
        grp = grp[tam == 5]
        gi = pd.factorize(grp)[0]
        for nom, comp in (("independientes", False), ("misma_liga", True)):
            s = simular(tt, dep, P["draws"], rng, companeros=comp, clave_p="liga")
            ym = np.bincount(gi, tt["y"].to_numpy(float)) / 5
            for mod, key in (("v5", "P"), ("v33", "P_v33")):
                Sm = np.zeros((gi.max() + 1, s[key].shape[1]))
                np.add.at(Sm, gi, s[key] / 5)
                r = puntuar(ym, Sm).assign(anio=anio, modelo=f"{mod}_{nom}")
                r["ancho_jugador"] = float(puntuar(tt["y"].to_numpy(float), s[key])["ancho80"].median())
                cinco.append(r)
    J = pd.concat(jug, ignore_index=True)
    E = pd.concat(eqp, ignore_index=True)
    Q = pd.concat(cinco, ignore_index=True)
    # resumen del jugador con IC por bootstrap de personas
    rb = np.random.default_rng(cfg["semilla"] + 1)
    res_j = {}
    for nom in ("v5", "v5_rho0", "v5_rho1"):
        r, lo, hi = _boot(J["persona_v5"], J[f"wis_{nom}"], J["wis_v33"], cfg["bootstrap"], rb)
        r2, lo2, hi2 = _boot(J["persona_v5"], J[f"wis_{nom}"], J["wis_v33e"], cfg["bootstrap"], rb)
        res_j[nom] = {"wis_frente_v33": r, "ic": [lo, hi], "wis_frente_v33e": r2, "ic_v33e": [lo2, hi2],
                      "cobertura80": float(J[f"cubre80_{nom}"].mean())}
    res_j["v33e"] = {"cobertura50": float(J["cubre50_v33e"].mean()), "cobertura80": float(J["cubre80_v33e"].mean()),
                     "ancho80_mediano": float(J["ancho80_v33e"].median()),
                     "sesgo_mediana": float((J["C_real"] - J["centro_v33e"]).mean())}
    res_j["v5"]["cobertura50"] = float(J["cubre50_v5"].mean())
    res_j["v33"] = {"cobertura50": float(J["cubre50_v33"].mean()), "cobertura80": float(J["cubre80_v33"].mean()),
                    "ancho80_mediano": float(J["ancho80_v33"].median())}
    res_j["v5"]["ancho80_mediano"] = float(J["ancho80_v5"].median())
    res_j["v5"]["sesgo_mediana"] = float((J["C_real"] - J["centro_v5"]).mean())
    res_j["v33"]["sesgo_mediana"] = float((J["C_real"] - J["centro_v33"]).mean())
    res_e = E[E["modelo"].str.startswith(("v5", "v33"))].groupby("modelo").agg(
        equipos=("wis", "size"), wis=("wis", "mean"), cobertura50=("cubre50", "mean"), cobertura80=("cubre80", "mean"),
        ancho_rel=("ancho_rel", "median"), fichajes_medios=("n", "mean")).to_dict("index")
    res_e["ancho_rel_jugador"] = E[E["modelo"] == "jugador_independientes"]["ancho_rel"].mean()
    res_q = Q.groupby("modelo").agg(grupos=("wis", "size"), cobertura50=("cubre50", "mean"),
                                    cobertura80=("cubre80", "mean"), ancho80=("ancho80", "median"),
                                    ancho_jugador=("ancho_jugador", "mean")).to_dict("index")
    J.to_parquet(out_dir / "por_partido_jugador.parquet")
    E.to_csv(out_dir / "por_partido_equipo.csv", index=False)
    Q.to_csv(out_dir / "por_partido_cinco.csv", index=False)
    res = {"casos": int(len(J)), "personas": int(J["persona_v5"].nunique()), "dependencias": deps,
           "jugador": res_j, "equipo": res_e, "cinco": res_q}
    C.escribir_json({**C.metadatos(cfg, [V33, CASOS]), **res}, out_dir / "meta_por_partido.json")
    return res
