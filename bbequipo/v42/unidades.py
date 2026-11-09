"""D3 · unidades v4.2: Net de quintetos, tríos y parejas (y sinergia de pareja) con historial (configs/v42.yaml).

Vigente (v4.1): el Net de la temporada t «corregido por muestra» (net_rtg_aj de bbstats/lineups/metrics.py: ORtg y DRtg
contraídos hacia el PPP de la liga con k = 300 posesiones) y, para la pareja, la sinergia WOWY publicada (`sinergia`).

v4.2: filtro de Kalman por unidad (misma unidad = misma liga y mismos jugadores) sobre sus temporadas ≤ t:
    observación de la temporada s:   y_s = Net bruto de la unidad,  var = c · 10⁴ / posesiones
    estado:                          θ_s = μ_s + δ_s,  μ_s = a + b · net_esperado_s  (lo que predicen sus jugadores:
                                     Σ RAPM propios − Σ RAPM rivales de la temporada s, columna net_esperado)
                                     δ_s = δ_{s−1} + η,  η ~ N(0, τ²) por año (un hueco de k años suma k·τ²)
    previa de la primera temporada:  δ ~ N(0, σ0²)
    sinergia de pareja:              y_s = sinergia WOWY, μ_s = a (b = 0), var = c · 10⁴ · Σ_x p_x / (p_x + 300)²
                                     sobre las cuatro situaciones (juntos, A sin B, B sin A, ninguno; p_x = posesiones)
a, b, σ0², τ², c por máxima verosimilitud de las innovaciones un paso adelante (todas las filas ≥ 25 posesiones, ≤ t).
Predicción de t+1: θ̂_t = μ_t + δ̂_t; intervalo predictivo del 80 %: θ̂_t ± κ·z80·√(P_t + τ² + c·R_{t+1}),
κ calibrado en el corte 2021 (conformal: cuantil 0,80 de |e|/sd) y aplicado sin tocar a 2022–2024.

Examen prerregistrado (unidades_v42.examen): objetivo = Net bruto de t+1 (unidades con ≥ 100 posesiones en t y en t+1);
MAE v4.2 frente a la vigente; IC95 bootstrap por equipo-temporada (B = 2000); conjunto de los cortes 2022–2024.

    python -m bbequipo.v42.unidades examen     → data/modelos/v4_2/unidades/examen_d3.json
    python -m bbequipo.v42.unidades exportar   → data/modelos/v4_2/unidades/<tipo>_v42.csv.gz (sólo tipos que pasan)
"""
from __future__ import annotations

import argparse
import glob
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.optimize import minimize

RAIZ = Path(__file__).resolve().parents[2]
CFG = yaml.safe_load((RAIZ / "configs" / "v42.yaml").read_text(encoding="utf-8"))
Z80 = float(CFG["z80"])
DIR_PROC = RAIZ / "data" / "processed"
SALIDA = RAIZ / "data" / "modelos" / "v4_2" / "unidades"
K_VIGENTE = 300.0          # contracción vigente (bbstats: contraccion_posesiones)
MIN_POSS_AJUSTE = 25.0     # filas que entran en el filtro y en la verosimilitud
MIN_POSS_EXAMEN = 100.0    # prerregistro
TIPOS = {"quintetos": "quintetos", "trios": "trios", "parejas": "parejas", "sinergia_pareja": "parejas"}


# ------------------------------------------------------------------------------------------------------------ datos
def cargar(tipo: str) -> pd.DataFrame:
    """Una fila por unidad-temporada (fase total): clave liga|unidad, año, y (observación), R (varianza unitaria del
    ruido, en (puntos/100)² por unidad de c), ne (Net esperado por los jugadores), vigente (lo que muestra hoy)."""
    fich = TIPOS[tipo]
    fr = []
    for f in sorted(glob.glob(str(DIR_PROC / "*" / "quintetos" / "*" / f"{fich}.csv.gz"))):
        temporada, liga = Path(f).parts[-4], Path(f).parts[-2]
        if temporada not in CFG["temporadas"]:
            continue
        try:
            d = pd.read_csv(f, low_memory=False)
        except Exception:                                  # noqa: BLE001 — fichero vacío o corrupto: se informa
            print(f"  aviso: no se puede leer {f}")
            continue
        if d.empty or "fase" not in d:
            continue
        d = d[d["fase"] == "total"].copy()
        d["liga"], d["temporada"] = liga, temporada
        fr.append(d)
    d = pd.concat(fr, ignore_index=True)
    d["anio"] = d["temporada"].str[:4].astype(int)
    d["unidad"] = d["unidad"].astype(str).map(lambda s: "|".join(sorted(s.split("|"))))
    d["poss"] = pd.to_numeric(d["poss"], errors="coerce")
    d = d[d["poss"] > 0]
    if tipo == "sinergia_pareja":
        ppm = d["poss"] / d["min"].where(d["min"] > 0)
        comp = [d["poss"]] + [d[c].clip(lower=0) * ppm for c in ("min_a_sin_b", "min_b_sin_a", "min_ninguno")]
        d["R"] = 1e4 * sum(p.fillna(0) / (p.fillna(0) + K_VIGENTE) ** 2 for p in comp)
        d["y"], d["vigente"], d["ne"] = d["sinergia"], d["sinergia"], 0.0
    else:
        d["R"] = 1e4 / d["poss"]
        d["y"], d["vigente"] = d["net_rtg"], d["net_rtg_aj"]
        d["ne"] = pd.to_numeric(d.get("net_esperado"), errors="coerce")
    d["ne_falta"] = d["ne"].isna()
    d["ne"] = d["ne"].fillna(0.0)
    d["clave"] = d["liga"] + ":" + d["unidad"]
    d = d[np.isfinite(d["y"]) & np.isfinite(d["R"])]
    # una unidad en dos equipos la misma temporada (traspaso conjunto): se queda la fila con más posesiones
    d = d.sort_values("poss").groupby(["clave", "anio"]).tail(1)
    cols = ["clave", "liga", "unidad", "team_id", "temporada", "anio", "poss", "y", "R", "ne", "ne_falta", "vigente"]
    return d[cols].sort_values(["clave", "anio"]).reset_index(drop=True)


# ------------------------------------------------------------------------------------------------------------ filtro
def _estructura(o: pd.DataFrame) -> dict:
    cl = o["clave"].to_numpy()
    nuevo = np.r_[True, cl[1:] != cl[:-1]]
    paso = o.groupby("clave").cumcount().to_numpy()
    gap = np.r_[0, np.diff(o["anio"].to_numpy())]
    return {"nuevo": nuevo, "paso": paso, "gap": np.where(nuevo, 0, gap),
            "por_paso": [np.flatnonzero(paso == k) for k in range(int(paso.max()) + 1)]}


def filtrar(o: pd.DataFrame, par: dict, est: dict | None = None) -> dict:
    """Kalman hacia delante por unidad, vectorizado por «paso» (n.º de temporada de la unidad). o ordenado clave, año.
    Estado θ = Net verdadero de la unidad; previa de la primera temporada N(a + b·net_esperado, σ0²)."""
    est = est or _estructura(o)
    y, R, ne = o["y"].to_numpy(float), o["R"].to_numpy(float), o["ne"].to_numpy(float)
    mu = par["a"] + par["b"] * ne
    n = len(o)
    mp, Pp, m, P = (np.empty(n) for _ in range(4))
    for k, i in enumerate(est["por_paso"]):
        if k == 0:
            mp[i], Pp[i] = mu[i], par["s0"]
        else:
            mp[i], Pp[i] = m[i - 1], P[i - 1] + par["tau2"] * est["gap"][i]
        S = Pp[i] + par["c"] * R[i]
        g = Pp[i] / S
        m[i] = mp[i] + g * (y[i] - mp[i])
        P[i] = (1 - g) * Pp[i]
    return {"mu": mu, "m_pred": mp, "P_pred": Pp, "theta": m, "P": P, "S": Pp + par["c"] * R, "innov": y - mp}


def _desempaquetar(x, con_b: bool) -> dict:
    a, b, ls0, lt, lc = (x[0], x[1], x[2], x[3], x[4]) if con_b else (x[0], 0.0, x[1], x[2], x[3])
    return {"a": float(a), "b": float(b), "s0": float(np.exp(ls0)), "tau2": float(np.exp(lt)), "c": float(np.exp(lc))}


def ajustar(o: pd.DataFrame, con_b: bool = True) -> dict:
    est = _estructura(o)
    hist = ~est["nuevo"]

    def nll(x):
        f = filtrar(o, _desempaquetar(x, con_b), est)
        S, r = f["S"][hist], f["innov"][hist]                  # sólo predicciones fuera de muestra (con historial)
        return float(0.5 * np.sum(np.log(S) + r ** 2 / S))

    var = float(o["y"].var())
    x0 = ([float(o["y"].mean()), 0.8] if con_b else [float(o["y"].mean())]) + list(np.log([0.2 * var / 4, 0.2 * var / 4, 2.0]))
    r = minimize(nll, np.array(x0), method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-3, "maxiter": 4000, "maxfev": 4000})
    par = _desempaquetar(r.x, con_b)
    par.update({"nll": float(r.fun), "n_filas": int(len(o)), "convergio": bool(r.success)})
    return par


# ------------------------------------------------------------------------------------------------------------ examen
def _boot(h: pd.DataFrame, rng: np.random.Generator, B: int) -> dict:
    u, inv = np.unique(h["cluster"].to_numpy(), return_inverse=True)
    dd = (h["e42"] - h["evig"]).to_numpy()
    bs = np.empty(B)
    for i in range(B):
        k = rng.multinomial(len(u), np.full(len(u), 1 / len(u)))[inv]
        bs[i] = (k * dd).sum() / k.sum()
    se = float(bs.std(ddof=1))
    return {"n": int(len(h)), "clusters_equipo_temporada": int(len(u)), "mae_vigente": float(h["evig"].mean()),
            "mae_v42": float(h["e42"].mean()), "dif": float(dd.mean()),
            "ic95": [float(np.quantile(bs, .025)), float(np.quantile(bs, .975))], "se_boot": se,
            "efecto_minimo_detectable": float(2.8 * se),   # 80 % de potencia, α = 0,05 bilateral
            "cobertura_80_v42": float(h["cub"].mean()), "cobertura_80_sin_recalibrar": float(h["cub1"].mean()),
            "n_con_historial": int(h["hist"].sum()),
            "anchura80_mediana_nivel_v42": float(h["ancho_nivel"].median())}


def examen_tipo(tipo: str, rng: np.random.Generator) -> dict:
    con_b = tipo != "sinergia_pareja"
    todo = cargar(tipo)
    base = todo[todo["poss"] >= MIN_POSS_AJUSTE].reset_index(drop=True)
    cal, dec = CFG["cortes"]["calibracion"], CFG["cortes"]["decision"]
    filas, cortes, kappa = [], {}, None
    for t in [cal] + dec:
        tr = base[base["anio"] <= t].reset_index(drop=True)
        par = ajustar(tr, con_b)
        f = filtrar(tr, par)
        tr = tr.assign(theta=f["theta"], P=f["P"], hist=~_estructura(tr)["nuevo"])
        a = tr[(tr["anio"] == t) & (tr["poss"] >= MIN_POSS_EXAMEN)].set_index("clave")
        b = todo[(todo["anio"] == t + 1) & (todo["poss"] >= MIN_POSS_EXAMEN)].set_index("clave")
        comun = a.index.intersection(b.index)
        a, b = a.loc[comun], b.loc[comun]
        sd = np.sqrt(a["P"] + par["tau2"] + par["c"] * b["R"])
        e = (b["y"] - a["theta"]).to_numpy()
        if t == cal:
            kappa = float(np.quantile(np.abs(e) / sd.to_numpy(), 0.80) / Z80) if len(e) else 1.0
        F = pd.DataFrame({"corte": t, "clave": comun, "cluster": a["liga"] + "|" + a["team_id"].astype(str) + f"|{t}",
                          "evig": np.abs(b["y"] - a["vigente"]).to_numpy(), "e42": np.abs(e),
                          "ebruto": np.abs(b["y"] - a["y"]).to_numpy(),
                          "cub": np.abs(e) <= kappa * Z80 * sd.to_numpy(), "cub1": np.abs(e) <= Z80 * sd.to_numpy(),
                          "hist": a["hist"].to_numpy(), "ancho_nivel": 2 * Z80 * np.sqrt(a["P"]).to_numpy()})
        filas.append(F)
        cortes[t] = {"parametros": dict(par), "filas_con_historial_ajuste": int((~_estructura(tr)["nuevo"]).sum()),
                     "unidades_t_100": int(((tr["anio"] == t) & (tr["poss"] >= MIN_POSS_EXAMEN)).sum()),
                     "repiten_t1_100": int(len(comun))}
        print(f"  {tipo:16s} t={t} n={len(comun):5d} a={par['a']:+.2f} b={par['b']:.2f} σ0={np.sqrt(par['s0']):.2f} "
              f"τ={np.sqrt(par['tau2']):.2f} c={par['c']:.2f}", flush=True)
    F = pd.concat(filas, ignore_index=True)
    B = int(CFG["bootstrap"]["B"])
    res = {"kappa_calibrado_2021": kappa, "cortes": {}}
    for t in [cal] + dec:
        h = F[F["corte"] == t]
        res["cortes"][int(t)] = {**cortes[t], **(_boot(h, rng, B) if len(h) else {"n": 0})}
    D = F[F["corte"].isin(dec)]
    res["conjunto"] = _boot(D, rng, B) if len(D) else {"n": 0}
    res["conjunto"]["mae_bruto_t"] = float(D["ebruto"].mean()) if len(D) else None
    for nombre, sub in (("con_historial", D[D["hist"]]), ("sin_historial", D[~D["hist"]])):
        res["conjunto"][nombre] = ({"n": int(len(sub)), "mae_vigente": float(sub["evig"].mean()),
                                    "mae_v42": float(sub["e42"].mean()), "cobertura_80_v42": float(sub["cub"].mean())}
                                   if len(sub) else {"n": 0})
    c = res["conjunto"]
    mejora = c.get("n", 0) > 0 and c["ic95"][1] < 0
    cob_ok = c.get("n", 0) > 0 and 0.75 <= c["cobertura_80_v42"] <= 0.85
    res["criterio"] = {"mejora_mae_ic95_excluye_0": bool(mejora), "cobertura_en_rango": bool(cob_ok)}
    res["pasa"] = bool(mejora and cob_ok)
    res["version"] = "v4.2" if res["pasa"] else "vigente (v4.1: temporada t corregida por muestra, k = 300)"
    return res


def examen(tipos: list[str] | None = None) -> dict:
    rng = np.random.default_rng(20261109)
    out = {}
    for tipo in tipos or list(TIPOS):
        out[tipo] = examen_tipo(tipo, rng)
        c = out[tipo]["conjunto"]
        print(f"  {tipo:16s} PASA={out[tipo]['pasa']} n={c['n']} MAE vig {c['mae_vigente']:.2f} v42 {c['mae_v42']:.2f} "
              f"Δ {c['dif']:+.2f} {np.round(c['ic95'], 2)} cob {c['cobertura_80_v42']:.3f} "
              f"(sin recal. {c['cobertura_80_sin_recalibrar']:.3f}) EMD {c['efecto_minimo_detectable']:.2f}", flush=True)
    SALIDA.mkdir(parents=True, exist_ok=True)
    res = {"prerregistro": "configs/v42.yaml → unidades_v42 (commit d606f47)",
           "objetivo": "Net bruto de t+1 (sinergia WOWY de t+1 para sinergia_pareja); unidades ≥ 100 posesiones en t y t+1",
           "vigente": "net_rtg_aj de t (k = 300) / sinergia de t", "bootstrap": {"B": CFG["bootstrap"]["B"],
                                                                                "unidad": "equipo-temporada (liga|team_id|t)"},
           "tipos": out, "decision": {k: v["version"] for k, v in out.items()}}
    f = SALIDA / "examen_d3.json"
    if f.exists():
        raise FileExistsError(f"{f} ya existe: no se sobrescribe (bórralo a mano si quieres rehacerlo)")
    f.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return res


# ------------------------------------------------------------------------------------------------------------ producto
def exportar() -> dict:
    """Para los tipos que pasan: estimación v4.2 por unidad y temporada (valor y rango del 80 % del nivel θ_s, con
    temporadas ≤ s) y parámetros ajustados con las temporadas cerradas. Formato en docs/checkpoints/V42_D3_unidades.md."""
    ex = json.loads((SALIDA / "examen_d3.json").read_text(encoding="utf-8"))
    pasan = [k for k, v in ex["tipos"].items() if v["pasa"]]
    cerradas = [int(t[:4]) for t in CFG["temporadas"]][:-1]
    params = {}
    for tipo in pasan:
        todo = cargar(tipo)
        base = todo[todo["poss"] >= MIN_POSS_AJUSTE].reset_index(drop=True)
        par = ajustar(base[base["anio"].isin(cerradas)].reset_index(drop=True), tipo != "sinergia_pareja")
        f = filtrar(base, par)
        est = _estructura(base)
        out = base.assign(v42=f["theta"], v42_lo=f["theta"] - Z80 * np.sqrt(f["P"]), v42_hi=f["theta"] + Z80 * np.sqrt(f["P"]),
                          esperado_jugadores=f["mu"], temporadas_previas=est["paso"],
                          peso_temporada=1 - f["P"] / np.maximum(f["P_pred"], 1e-12))
        cols = ["liga", "temporada", "team_id", "unidad", "poss", "y", "vigente", "esperado_jugadores", "v42", "v42_lo",
                "v42_hi", "temporadas_previas", "peso_temporada"]
        out = out[cols].rename(columns={"y": "observado", "vigente": "vigente_v41"})
        dest = SALIDA / f"{tipo}_v42.csv.gz"
        if dest.exists():
            raise FileExistsError(f"{dest} ya existe: no se sobrescribe")
        out.round(4).to_csv(dest, index=False)
        params[tipo] = {k: v for k, v in par.items()} | {"kappa_80": ex["tipos"][tipo]["kappa_calibrado_2021"]}
    if pasan:
        (SALIDA / "parametros_v42.json").write_text(json.dumps(params, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"pasan": pasan, "parametros": params}


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m bbequipo.v42.unidades")
    ap.add_argument("orden", choices=["examen", "exportar"])
    ap.add_argument("--tipos", nargs="*", default=None, choices=list(TIPOS))
    a = ap.parse_args()
    t0 = time.time()
    r = examen(a.tipos) if a.orden == "examen" else exportar()
    print(json.dumps(r["decision"] if a.orden == "examen" else r["pasan"], ensure_ascii=False))
    print(f"hecho en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
