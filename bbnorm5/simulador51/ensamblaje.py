"""v5.1 F2 · Ensamblaje de la contribución por partido con la producción combinada (F10 §1.2, ahora con la v5.1).

C = M / gm × P: M, minutos por partido del motor v3.3 (examen V32_corte reproducido en la F0); P, pts/100 de la
producción combinada de produccion.py (siete cuantiles del 5 % al 95 %). Dependencias, estimadas sólo con temporadas
anteriores (PIT de los observados):
- ρ entre minutos y producción del mismo jugador (la v3.3 supone ρ = 1);
- factor común de los compañeros del mismo equipo (minutos y producción);
- factor común de la liga y temporada de destino en la producción (la innovación de λ de t+1 que la F10 no propagaba).

Examen frente a la contribución publicada de la v3.3 (reproducida) y a la v3.3 ensamblada igual: jugador, suma de los
fichajes de cada equipo y grupos de cinco fichajes a la misma liga y temporada.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from bbnorm5 import config as C
from bbnorm5.aguas_abajo import por_partido as PP
from bbnorm5.simulador51 import produccion as PR
from bbnorm5.validacion import fichajes as VF

P_NIV = np.array([p for _, p, _ in PR.NIV])
Q5 = [q for _, _, q in PR.NIV]


def casos(cfg: dict) -> pd.DataFrame:
    import json
    out = PR.dir_salida(cfg)
    w = json.loads((out / "meta_produccion.json").read_text())["pesos"]
    pc = pd.read_parquet(out / "produccion_casos.parquet")
    pc = pc[pc["metrica"] == "pts_p100"].copy()
    wpts = float(w["pts_p100"])
    lv = {50: ("q25", "q75"), 80: ("q10", "q90"), 90: ("q5", "q95")}
    # cuantiles de la v5 y de la v3.3 en los siete niveles; combinada = w·v5 + (1 − w)·v3.3
    for s, p, q in PR.NIV:
        a = next((f"v5__lo{k}" for k, (lo, hi) in lv.items() if lo == q), None) or \
            next((f"v5__hi{k}" for k, (lo, hi) in lv.items() if hi == q), "v5__q50")
        b = {"lo90": "v3.2__lo90", "lo80": "v3.2__lo80", "lo50": "v3.2__lo50", "pred": "v3.2__q50", "hi50": "v3.2__hi50",
             "hi80": "v3.2__hi80", "hi90": "v3.2__hi90"}[s]
        pc[f"p5_{q}"], pc[f"p33_{q}"] = pc[a], pc[b]
        pc[f"pc_{q}"] = wpts * pc[a] + (1 - wpts) * pc[b]
    ex = pd.read_csv(C.RAIZ / cfg["reproducido"] / "V32_corte_inicio_adapt" / "predicciones.csv.gz", low_memory=False,
                     dtype={"persona_id": str, "team_d": str},
                     usecols=["persona_id", "liga_d", "team_d", "temporada_d", "min_real", "min_pct_real", "C_real"] +
                     [f"v_min_{s}" for s, _ in PP.Q_V33] + [f"v_C_{s}" for s, _ in PP.Q_V33])
    per = pd.read_csv(C.DIR_DATOS / "limpios" / "entidades" / "personas_v5.csv", dtype=str)
    mp = per.groupby("persona_crosswalk")["persona_v5"].agg(lambda s: s.mode().iloc[0])
    ex["persona_v5"] = ex["persona_id"].map(mp)
    pc["team_d"] = pc["team_d"].astype(str)
    d = pc.merge(ex, on=["persona_v5", "liga_d", "team_d", "temporada_d"], how="inner").drop_duplicates(
        ["persona_v5", "liga_d", "team_d", "temporada_d"])
    d["gm"] = (d["min_real"] / d["min_pct_real"]).replace([np.inf, -np.inf], np.nan)
    d["gm"] = d.groupby("liga_d")["gm"].transform("median").round()
    return d[np.isfinite(d["gm"]) & np.isfinite(d["C_real"])].reset_index(drop=True)


def _m(d, pre):
    return d[[f"{pre}_{q}" for q in Q5]].to_numpy(float)


def pits(d: pd.DataFrame) -> pd.DataFrame:
    pm = np.array([p for _, p in PP.Q_V33])
    vm = d[[f"v_min_{s}" for s, _ in PP.Q_V33]].to_numpy(float)
    return d.assign(z_m=stats.norm.ppf(PP.cdf(d["min_real"].to_numpy(float), pm, vm)),
                    z_p=stats.norm.ppf(PP.cdf(d["real"].to_numpy(float), P_NIV, _m(d, "pc"))))


def _min_escalados(d: pd.DataFrame, s: float) -> np.ndarray:
    """Cuantiles de minutos del motor con la dispersión alrededor de la mediana multiplicada por s (recalibración)."""
    vm = d[[f"v_min_{q}" for q, _ in PP.Q_V33]].to_numpy(float)
    med = d["v_min_pred"].to_numpy(float)[:, None]
    return np.maximum(med + s * (vm - med), 0.0)


def escala_minutos(a: pd.DataFrame) -> float:
    """Factor s ∈ [0,3; 1,5] con el que la banda del 80 % de los minutos cubre el 80 % en `a` (temporadas anteriores):
    la predictiva de minutos del motor es ancha en quien acaba jugando ≥ 300 min (F10 §2.1)."""
    i_lo, i_hi = [q for q, _ in PP.Q_V33].index("lo80"), [q for q, _ in PP.Q_V33].index("hi80")
    y = a["min_real"].to_numpy(float)
    rej = np.round(np.arange(0.3, 1.51, 0.05), 2)
    cob = []
    for s_ in rej:
        v = _min_escalados(a, s_)
        cob.append(np.mean((y >= v[:, i_lo]) & (y <= v[:, i_hi])))
    return float(rej[int(np.argmin(np.abs(np.array(cob) - 0.8)))])


def dependencias(z: pd.DataFrame, anio: int) -> dict:
    a = z[z["anio"] < anio]
    if len(a) < 200:
        return {"rho_mp": 0.0, "eq_m": 0.0, "eq_p": 0.0, "liga_p": 0.0, "escala_min": 1.0, "n": int(len(a))}
    return {"escala_min": escala_minutos(a), "rho_mp": float(np.corrcoef(a["z_m"], a["z_p"])[0, 1]),
            "eq_m": PP._corr_companeros(a, ["temporada_d", "liga_d", "team_d"], "z_m"),
            "eq_p": PP._corr_companeros(a, ["temporada_d", "liga_d", "team_d"], "z_p"),
            "liga_p": PP._corr_companeros(a, ["temporada_d", "liga_d"], "z_p"), "n": int(len(a))}


def simular(d: pd.DataFrame, dep: dict, S: int, rng, rho_mp: float | None = None, companeros: bool = True,
            liga: bool = True, recalibrar: bool = True) -> dict:
    """Draws (n, S) de M y de C con la producción combinada, la v5, la v3.3 ensamblada y la C publicada de la v3.3."""
    pm = np.array([p for _, p in PP.Q_V33])
    vm = _min_escalados(d, dep.get("escala_min", 1.0) if recalibrar else 1.0)
    vc = d[[f"v_C_{s}" for s, _ in PP.Q_V33]].to_numpy(float)
    n = len(d)
    r = dep["rho_mp"] if rho_mp is None else rho_mp
    eq = d.groupby(["temporada_d", "liga_d", "team_d"]).ngroup().to_numpy()
    lg = d.groupby(["temporada_d", "liga_d"]).ngroup().to_numpy()
    a_m = max(dep["eq_m"], 0.0) if companeros else 0.0
    a_pe = max(dep["eq_p"], 0.0) if companeros else 0.0
    a_pl = max(dep["liga_p"], 0.0) if liga else 0.0
    e1, e2 = rng.standard_normal((n, S)), rng.standard_normal((n, S))
    fm = rng.standard_normal((eq.max() + 1, S))[eq]
    fpe = rng.standard_normal((eq.max() + 1, S))[eq]
    fpl = rng.standard_normal((lg.max() + 1, S))[lg]
    zp = np.sqrt(max(1 - a_pe - a_pl, 0.05)) * e1 + np.sqrt(a_pe) * fpe + np.sqrt(a_pl) * fpl
    zm = np.sqrt(1 - a_m) * (r * e1 + np.sqrt(max(1 - r ** 2, 0)) * e2) + np.sqrt(a_m) * fm
    U = stats.norm.cdf(zp)
    M = PP.cuantil(stats.norm.cdf(zm), pm, vm)
    gm = d["gm"].to_numpy(float)[:, None]
    out = {"M": M}
    for nom, pre in (("comb", "pc"), ("v5", "p5"), ("v33e", "p33")):
        P = PP.cuantil(U, P_NIV, _m(d, pre))
        out[f"P_{nom}"], out[f"C_{nom}"] = P, M / gm * P
    out["C_v33"] = PP.cuantil(rng.uniform(0, 1, (n, S)), pm, vc)
    return out


def _reescalar(D: np.ndarray, s_: float) -> np.ndarray:
    med = np.median(D, axis=1, keepdims=True)
    return np.maximum(med + s_ * (D - med), 0.0)


def escala_C(d: pd.DataFrame, anio: int, S: int, rng, noms=("comb", "v5", "v33e")) -> dict:
    """Factor de anchura de la contribución por versión, fijado con la temporada anterior (sus dependencias, con las
    anteriores a ella): la banda del 80 % de C debe cubrir el 80 % (los minutos y la producción ya calibrados por
    separado cubren de más al multiplicarse)."""
    prev = d[d["anio"] == anio - 1].reset_index(drop=True)
    if len(prev) < 200:
        return {n: 1.0 for n in noms}
    s = simular(prev, dependencias(d, anio - 1), S, rng)
    y = prev["C_real"].to_numpy(float)[:, None]
    rej = np.round(np.arange(0.5, 1.21, 0.025), 3)
    out = {}
    for n in noms:
        cob = []
        for s_ in rej:
            q = np.quantile(_reescalar(s[f"C_{n}"], s_), [0.1, 0.9], axis=1)
            cob.append(np.mean((y[:, 0] >= q[0]) & (y[:, 0] <= q[1])))
        out[n] = float(rej[int(np.argmin(np.abs(np.array(cob) - 0.8)))])
    return out


def ejecutar(cfg: dict) -> dict:
    E = cfg["ensamblaje"]
    out = PR.dir_salida(cfg)
    rng = np.random.default_rng(cfg["semilla"] + 1)
    d = pits(casos(cfg))
    jug, eqp, cinco, deps = [], [], [], {}
    for anio in [a for a in sorted(d["anio"].unique()) if a in cfg["prueba"]]:
        t = d[d["anio"] == anio].reset_index(drop=True)
        dep = dependencias(d, anio)
        deps[int(anio)] = dep
        s = simular(t, dep, E["draws"], rng)
        sc = escala_C(d, anio, E["draws"], rng)
        dep["escala_C"] = sc
        f = t[["persona_v5", "anio", "liga_d", "team_d", "temporada_d", "C_real"]].copy()
        for nom in ("comb", "v5", "v33e"):
            f = f.join(PP.puntuar(t["C_real"].to_numpy(float), s[f"C_{nom}"])[["wis", "cubre80"]]
                       .add_suffix(f"_{nom}_sin_escala_C"))
            s[f"C_{nom}"] = _reescalar(s[f"C_{nom}"], sc[nom])
        for nom in ("comb", "v5", "v33e", "v33"):
            f = f.join(PP.puntuar(t["C_real"].to_numpy(float), s[f"C_{nom}"]).add_suffix(f"_{nom}"))
        s1 = simular(t, dep, E["draws"], rng, rho_mp=1.0)
        f = f.join(PP.puntuar(t["C_real"].to_numpy(float), s1["C_comb"])[["wis", "cubre80"]].add_suffix("_comb_rho1"))
        s0 = simular(t, dep, E["draws"], rng, recalibrar=False)
        f = f.join(PP.puntuar(t["C_real"].to_numpy(float), s0["C_comb"])[["wis", "cubre80"]].add_suffix("_comb_sin_recal"))
        vm = _min_escalados(t, dep["escala_min"])
        f["cubre80_min"] = (t["min_real"] >= vm[:, 1]) & (t["min_real"] <= vm[:, 5])
        vm0 = _min_escalados(t, 1.0)
        f["cubre80_min_sin_recal"] = (t["min_real"] >= vm0[:, 1]) & (t["min_real"] <= vm0[:, 5])
        jug.append(f)
        # equipo: suma de C de los fichajes del mismo equipo (≥ 2)
        g = t.groupby(["temporada_d", "liga_d", "team_d"]).ngroup().to_numpy()
        n_g = np.bincount(g)
        ok = n_g >= 2
        si = simular(t, dep, E["draws"], rng, companeros=False, liga=False)
        for nom in ("comb", "v5", "v33e"):
            si[f"C_{nom}"] = _reescalar(si[f"C_{nom}"], sc[nom])
        for nom_dep, ss in (("dependencias", s), ("independientes", si)):
            for nom in ("comb", "v33e", "v33"):
                if nom == "v33" and nom_dep == "dependencias":
                    continue
                Ssum = np.zeros((n_g.size, ss[f"C_{nom}"].shape[1]))
                np.add.at(Ssum, g, ss[f"C_{nom}"])
                y = np.bincount(g, t["C_real"].to_numpy(float))
                r = PP.puntuar(y[ok], Ssum[ok]).assign(anio=anio, modelo=f"{nom}_{nom_dep}", n=n_g[ok])
                eqp.append(r)
        # grupos de cinco fichajes a la misma liga y temporada: media de pts/100
        tt = t.iloc[rng.permutation(len(t))].reset_index(drop=True)
        k = tt.groupby(["temporada_d", "liga_d"]).cumcount() // 5
        grp = (tt["temporada_d"] + "|" + tt["liga_d"] + "|" + k.astype(str)).to_numpy()
        tam = pd.Series(grp).map(pd.Series(grp).value_counts()).to_numpy()
        tt, grp = tt[tam == 5].reset_index(drop=True), grp[tam == 5]
        gi = pd.factorize(grp)[0]
        ym = np.bincount(gi, tt["real"].to_numpy(float)) / 5
        for nom_dep, liga in (("liga_comun", True), ("independientes", False)):
            ss = simular(tt, dep, E["draws"], rng, companeros=False, liga=liga)
            for nom in ("comb", "v33e"):
                Sm = np.zeros((gi.max() + 1, ss[f"P_{nom}"].shape[1]))
                np.add.at(Sm, gi, ss[f"P_{nom}"] / 5)
                cinco.append(PP.puntuar(ym, Sm).assign(anio=anio, modelo=f"{nom}_{nom_dep}"))
    J, Eq, Q = pd.concat(jug, ignore_index=True), pd.concat(eqp, ignore_index=True), pd.concat(cinco, ignore_index=True)
    rb = np.random.default_rng(cfg["semilla"] + 2)
    res_j = {}
    for nom in ("comb", "v5", "v33e", "comb_rho1", "comb_sin_recal", "comb_sin_escala_C"):
        r, lo, hi = VF._boot_ratio(J["persona_v5"].to_numpy(), J[f"wis_{nom}"].to_numpy(float),
                                   J["wis_v33"].to_numpy(float), cfg["bootstrap"], rb)
        r2, lo2, hi2 = VF._boot_ratio(J["persona_v5"].to_numpy(), J[f"wis_{nom}"].to_numpy(float),
                                      J["wis_v33e"].to_numpy(float), cfg["bootstrap"], rb)
        res_j[nom] = {"frente_C_v33": r, "ic": [lo, hi], "frente_v33e": r2, "ic_v33e": [lo2, hi2],
                      "cobertura80": float(J[f"cubre80_{nom}"].mean())}
    res_j["v33"] = {"cobertura80": float(J["cubre80_v33"].mean())}
    res_j["minutos"] = {"cobertura80_recalibrados": float(J["cubre80_min"].mean()),
                        "cobertura80_motor": float(J["cubre80_min_sin_recal"].mean())}
    res_e = Eq.groupby("modelo").agg(equipos=("wis", "size"), wis=("wis", "mean"), cobertura50=("cubre50", "mean"),
                                     cobertura80=("cubre80", "mean")).round(4).to_dict("index")
    res_q = Q.groupby("modelo").agg(grupos=("wis", "size"), wis=("wis", "mean"), cobertura50=("cubre50", "mean"),
                                    cobertura80=("cubre80", "mean"), ancho80=("ancho80", "median")).round(4).to_dict("index")
    J.to_parquet(out / "ensamblaje_jugador.parquet")
    Eq.to_csv(out / "ensamblaje_equipo.csv", index=False)
    Q.to_csv(out / "ensamblaje_cinco.csv", index=False)
    res = {"casos": int(len(J)), "personas": int(J["persona_v5"].nunique()), "dependencias": deps,
           "jugador": res_j, "equipo": res_e, "cinco": res_q}
    C.escribir_json({**C.metadatos(cfg), **res}, out / "meta_ensamblaje.json")
    return res
