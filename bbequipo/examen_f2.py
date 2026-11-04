"""F2 · examen prerregistrado §11.2.

F2-A (parejas nuevas): en el corte t se ajusta M sobre los tramos ≤ t (perfiles de corte_<t>, β de F1 del corte) y se
evalúa en t+1 sobre las PAREJAS NUEVAS (misma parte del tramo, primera coocurrencia en t+1, ≥ min posesiones juntas):
  * nivel de pareja: R_ij = Σ_s n_s r_s / Σ_s n_s (residuo de F1 en los tramos en que comparten lado, con signo del lado)
    frente a φ̂_ij = z_iᵀ M_r z_j; error ponderado por posesiones de (R_ij − 0)² y (R_ij − φ̂_ij)²; IC95 del cociente por
    bootstrap de parejas. Regla: φ se publica si IC95,sup(MSE_φ/MSE_F1 − 1) < 0.
  * nivel de tramo (informativo): error de F1 frente a F1 + Σφ sobre los tramos de t+1 con alguna pareja nueva.
  El rango r se elige en el corte de selección 2022 (el de menor error de pareja; a igualdad, el menor).
Salidas: data/modelos/v4_0/sinergia/examen/.
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from . import config as C
from . import examen_f1 as EX
from . import rapm as RP
from . import sinergia as SG


def parejas_observadas(tr: pd.DataFrame) -> set:
    out = set()
    for q in tr["A"]:
        for a in range(5):
            for b in range(a + 1, 5):
                out.add((q[a], q[b]) if q[a] < q[b] else (q[b], q[a]))
    for q in tr["B"]:
        for a in range(5):
            for b in range(a + 1, 5):
                out.add((q[a], q[b]) if q[a] < q[b] else (q[b], q[a]))
    return out


def residuo_parejas(tr1: pd.DataFrame, r: np.ndarray, w: np.ndarray, vistas: set) -> pd.DataFrame:
    """R_ij y posesiones de cada pareja NUEVA de t+1 (persona-temporada), con signo del lado."""
    acc, pos = {}, {}
    for s, row in enumerate(tr1.itertuples()):
        for sign, q in ((1.0, row.A), (-1.0, row.B)):
            for a in range(5):
                for b in range(a + 1, 5):
                    k = (q[a], q[b]) if q[a] < q[b] else (q[b], q[a])
                    kp = (k[0].rsplit("|", 1)[0], k[1].rsplit("|", 1)[0])
                    if kp in vistas:
                        continue
                    acc[k] = acc.get(k, 0.0) + w[s] * sign * r[s]
                    pos[k] = pos.get(k, 0.0) + w[s]
    return pd.DataFrame({"i": [k[0] for k in acc], "j": [k[1] for k in acc], "R": [acc[k] / pos[k] for k in acc],
                         "poss": [pos[k] for k in acc]})


def examen_corte(cfg: dict, a: int, tr_all: pd.DataFrame, rangos: list, progreso=print) -> dict:
    f2 = cfg["f2"]["sinergia"]
    t0 = time.time()
    aj = EX.ajuste_corte(cfg, a, tr_all, "gbm", progreso=None)       # prior elegido en F1
    R = SG.Rasgos(aj["T"], cfg)
    tr = tr_all[tr_all["anio"] <= a].reset_index(drop=True)
    fit = SG.ajustar(cfg, aj, tr, R, progreso=progreso)
    tr1 = tr_all[tr_all["anio"] == a + 1].reset_index(drop=True)
    out = {"corte": a, "lambda": fit["lambda"], "log_marginal": fit["log_marginal"], "p": R.p, "tramos_ajuste": int(len(tr)),
           "autovalores_abs_mayores": np.sort(np.abs(fit["autovalores_M"]))[::-1][:8].tolist(), "rangos": {}}
    if tr1.empty:
        return out
    # residuo de F1 en t+1 con β_t (persona-temporada t: claves de t+1 no están en β → prior/media de liga, como en §11.1)
    mu1, nuevos = SG.mu_f1(cfg, aj, tr1)
    r1 = tr1["y"].to_numpy(float) - mu1
    w1 = tr1["poss"].to_numpy(float)
    vistas = {(k[0].rsplit("|", 1)[0], k[1].rsplit("|", 1)[0]) for k in parejas_observadas(tr)}
    par = residuo_parejas(tr1, r1, w1, vistas)
    par = par[par["poss"] >= float(f2["min_posesiones_pareja_validacion"])].reset_index(drop=True)
    # z de t+1: el perfil de la persona en la temporada t (≤ t; sin perfil → 0 → φ̂ = 0, se cuenta)
    temp_t = f"{a}-{str(a + 1)[-2:]}"
    zi = R.de([k.rsplit("|", 1)[0] + "|" + temp_t for k in par["i"]])
    zj = R.de([k.rsplit("|", 1)[0] + "|" + temp_t for k in par["j"]])
    con_perfil = (np.abs(zi).sum(1) > 0) & (np.abs(zj).sum(1) > 0)
    B, sem = int(cfg["criterios"]["comunes"]["bootstrap"]), int(cfg["criterios"]["comunes"]["semilla_bootstrap"])
    rng = np.random.default_rng(sem)
    wpar = par["poss"].to_numpy(float); Rp = par["R"].to_numpy(float)
    e0 = wpar * Rp ** 2
    out["parejas_nuevas"] = int(len(par)); out["parejas_con_perfil"] = int(con_perfil.sum())
    out["mse_f1_pareja"] = float(e0.sum() / wpar.sum())
    nuevos_par = set(zip(par["i"], par["j"]))
    tiene = np.array([any(((q[x], q[y]) if q[x] < q[y] else (q[y], q[x])) in nuevos_par for q in (row.A, row.B)
                          for x in range(5) for y in range(x + 1, 5)) for row in tr1.itertuples()])
    out["tramos_con_pareja_nueva"] = int(tiene.sum())
    for rk in rangos:
        r_ = None if rk in ("completa", None) else int(rk)
        Mr, _ = SG.truncar(fit["M"], r_)
        phi = SG.phi_pareja(Mr, zi, zj)
        e1 = wpar * (Rp - phi) ** 2
        ratios = []
        for _ in range(B):
            ii = rng.integers(0, len(par), len(par)); ratios.append(e1[ii].sum() / e0[ii].sum() - 1)
        res = {"mse_phi_pareja": float(e1.sum() / wpar.sum()), "delta": float(e1.sum() / e0.sum() - 1),
               "ic95": [float(np.quantile(ratios, 0.025)), float(np.quantile(ratios, 0.975))],
               "sd_phi": float(np.std(phi)), "corr_phi_R": float(np.corrcoef(phi, Rp)[0, 1]) if np.std(phi) > 0 else 0.0}
        # nivel de tramo: tramos de t+1 con alguna pareja nueva
        m = Mr[np.triu_indices(R.p)]
        e_tr0, e_tr1 = 0.0, 0.0
        for idx, U in SG.rasgos_tramos(tr1, R):
            pred = U @ m
            sel = tiene[idx]
            e_tr0 += float(np.sum(w1[idx][sel] * r1[idx][sel] ** 2)); e_tr1 += float(np.sum(w1[idx][sel] * (r1[idx][sel] - pred[sel]) ** 2))
        res["tramo_delta"] = float(e_tr1 / e_tr0 - 1) if e_tr0 > 0 else None
        out["rangos"][str(rk)] = res
        if progreso:
            progreso(f"    corte {a} rango {rk}: parejas nuevas {len(par)} · Δ pareja {res['delta']:+.4f} {np.round(res['ic95'], 4).tolist()} · "
                     f"sd φ {res['sd_phi']:.3f} · corr(φ, R) {res['corr_phi_R']:+.3f} · Δ tramo {res['tramo_delta']}", flush=True)
    out["tiempo_s"] = round(time.time() - t0)
    return out, fit


def main(cfg: dict, progreso=print) -> dict:
    from bbfit.registro import experimento
    t0 = time.time()
    out_dir = SG.dir_salida(cfg) / "examen"; out_dir.mkdir(parents=True, exist_ok=True)
    tr_all = RP.tramos(cfg, None, progreso)
    cortes = [int(a) for a in cfg["criterios"]["comunes"]["cortes"]]
    sel = int(cfg["f1"]["comprobaciones_d2"]["corte"])
    rangos = list(cfg["f2"]["sinergia"]["r_candidatos"])
    resultado = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "cortes": {}}
    with experimento(cfg["mlflow"], "F2A_examen", params={"cortes": cortes, "rangos": rangos}):
        for a in cortes:
            r, fit = examen_corte(cfg, a, tr_all, rangos, progreso)
            resultado["cortes"][a] = r
            np.save(out_dir / f"M_corte_{a}.npy", fit["M"])
        # elección del rango en el corte de selección: menor error de pareja; a igualdad (< 0,1 %), el menor rango
        rs = resultado["cortes"][sel]["rangos"]
        mejor = min(rs, key=lambda k: rs[k]["mse_phi_pareja"])
        for k in [str(x) for x in rangos]:
            if rs[k]["mse_phi_pareja"] <= rs[mejor]["mse_phi_pareja"] * 1.001:
                mejor = k; break
        resultado["decisiones"] = {"rango": mejor, "regla": "menor error de pareja nueva en el corte de selección; a igualdad (0,1 %), el menor rango"}
        dec = [a for a in cortes if a != int(cfg["criterios"]["comunes"]["corte_calibracion"]) and "rangos" in resultado["cortes"][a]]
        deltas = [resultado["cortes"][a]["rangos"][mejor] for a in dec]
        resultado["puerta_11_2_parejas"] = {"cortes": dec, "delta_por_corte": [d["delta"] for d in deltas],
                                            "ic95_por_corte": [d["ic95"] for d in deltas],
                                            "pasa_en_todos": bool(all(d["ic95"][1] < 0 for d in deltas)),
                                            "pasa_en_alguno": bool(any(d["ic95"][1] < 0 for d in deltas))}
        resultado["tiempo_s"] = round(time.time() - t0)
        (out_dir / "resumen_examen_f2a.json").write_text(json.dumps(resultado, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    if progreso:
        progreso(f"  examen F2-A: rango {mejor} · {resultado['puerta_11_2_parejas']} · {resultado['tiempo_s']} s", flush=True)
    return resultado


def diagnostico_lambda(cfg: dict, a: int, lambdas: list[float], progreso=print) -> dict:
    """Diagnóstico (corte de calibración): ¿hay señal de sinergia por perfiles con λ menores que el que elige la
    verosimilitud marginal? Para cada λ, M forzada y el mismo examen de parejas nuevas en t+1."""
    f2 = cfg["f2"]["sinergia"]
    tr_all = RP.tramos(cfg, None, progreso=None)
    aj = EX.ajuste_corte(cfg, a, tr_all, "gbm", progreso=None)
    R = SG.Rasgos(aj["T"], cfg)
    tr = tr_all[tr_all["anio"] <= a].reset_index(drop=True)
    mu, _ = SG.mu_f1(cfg, aj, tr)
    r = tr["y"].to_numpy(float) - mu; w = tr["poss"].to_numpy(float)
    sigma2 = float(aj["res"]["sigma2"])
    G, b, rr = SG.acumular(tr, R, r, w)
    g, V = np.linalg.eigh(G); g = np.maximum(g, 0); bv = V.T @ b
    tr1 = tr_all[tr_all["anio"] == a + 1].reset_index(drop=True)
    mu1, _ = SG.mu_f1(cfg, aj, tr1)
    r1 = tr1["y"].to_numpy(float) - mu1; w1 = tr1["poss"].to_numpy(float)
    vistas = {(k[0].rsplit("|", 1)[0], k[1].rsplit("|", 1)[0]) for k in parejas_observadas(tr)}
    par = residuo_parejas(tr1, r1, w1, vistas)
    par = par[par["poss"] >= float(f2["min_posesiones_pareja_validacion"])].reset_index(drop=True)
    temp_t = f"{a}-{str(a + 1)[-2:]}"
    zi = R.de([k.rsplit("|", 1)[0] + "|" + temp_t for k in par["i"]]); zj = R.de([k.rsplit("|", 1)[0] + "|" + temp_t for k in par["j"]])
    wpar, Rp = par["poss"].to_numpy(float), par["R"].to_numpy(float)
    e0 = float(np.sum(wpar * Rp ** 2))
    rng = np.random.default_rng(int(cfg["criterios"]["comunes"]["semilla_bootstrap"]))
    out = {"corte": a, "parejas_nuevas": int(len(par)), "lambdas": {}}
    for lam in lambdas:
        m = V @ (bv / sigma2 / (g / sigma2 + lam))
        M = SG.vec_a_matriz(m, R.p)
        phi = SG.phi_pareja(M, zi, zj)
        e1 = wpar * (Rp - phi) ** 2
        ratios = [e1[ii].sum() / (wpar[ii] * Rp[ii] ** 2).sum() - 1 for ii in (rng.integers(0, len(par), len(par)) for _ in range(500))]
        # error en muestra (ajuste) para ver el sobreajuste
        e_in = 0.0
        for idx, U in SG.rasgos_tramos(tr, R):
            e_in += float(np.sum(w[idx] * (r[idx] - U @ m) ** 2))
        out["lambdas"][str(lam)] = {"delta_pareja_nueva": float(e1.sum() / e0 - 1), "ic95": [float(np.quantile(ratios, 0.025)), float(np.quantile(ratios, 0.975))],
                                    "sd_phi": float(np.std(phi)), "corr_phi_R": float(np.corrcoef(phi, Rp)[0, 1]) if np.std(phi) > 0 else 0.0,
                                    "reduccion_en_muestra_pct": float(100 * (1 - e_in / float(np.sum(w * r ** 2))))}
        if progreso:
            d = out["lambdas"][str(lam)]
            progreso(f"    λ = {lam}: en muestra −{d['reduccion_en_muestra_pct']:.3f} % · parejas nuevas Δ {d['delta_pareja_nueva']:+.4f} {np.round(d['ic95'], 4).tolist()} · sd φ {d['sd_phi']:.3f} · corr {d['corr_phi_R']:+.3f}", flush=True)
    return out
