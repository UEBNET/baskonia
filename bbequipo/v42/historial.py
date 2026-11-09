"""D1 · normalización v4.2: el nivel de cada métrica del jugador combinando sus temporadas ≤ t (configs/v42.yaml).

Modelo por métrica, en su escala de trabajo T (bbmodel.metricas.transformar):
    observación de la temporada s (una o varias ligas):  y = T(valor v3.2),  var = c·v,  v = ((T(hi) − T(lo)) / (2·z80))²
    estado:  θ_s = θ_{s−1} + η,  η ~ N(0, τ²) por año (paseo aleatorio; un hueco de k años suma k·τ²)
    previa de la primera temporada:  N(μ_pos, σ²_pos) por posición
τ² y c por máxima verosimilitud de las innovaciones un paso adelante (temporadas ≤ t). μ_pos y σ²_pos por momentos.

Examen (prerregistrado): predecir la observación de t+1 con (a) la temporada t sola (v3.2, lo que muestra el producto) y
(b) el nivel filtrado en t (v4.2). MAE en desviaciones típicas de la métrica, IC95 bootstrap por persona, cobertura del 80 %.

    python -m bbequipo.v42 historial-examen      → data/modelos/v4_2/normalizacion/examen_d1.json
    python -m bbequipo.v42 historial-exportar    → previas por temporada para el artifact (atlas/v42/historial/<t>.json.gz.txt)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.optimize import minimize

from bbmodel.metricas import CATALOGO, destransformar, transformar

RAIZ = Path(__file__).resolve().parents[2]
CFG = yaml.safe_load((RAIZ / "configs" / "v42.yaml").read_text(encoding="utf-8"))
Z80 = float(CFG["z80"])
DIR_NORM = RAIZ / "data" / "modelos" / "v3_2" / "normalizado"
SALIDA = RAIZ / "data" / "modelos" / "v4_2" / "normalizacion"
METRICAS = [m for m in CATALOGO if m not in ("rapm", "orapm", "drapm")]
POS = ("E", "A", "I")
MIN_EXAMEN = 300.0


# ------------------------------------------------------------------------------------------------------------ datos
def cargar(temporadas: list[str] | None = None) -> pd.DataFrame:
    temporadas = temporadas or CFG["temporadas"]
    cols = {"persona_id", "liga", "temporada", "pos3", "min"} | {f"{m}{s}" for m in METRICAS for s in ("", "_lo", "_hi")}
    fr = []
    for t in temporadas:
        f = DIR_NORM / f"{t}.csv.gz"
        if f.exists():
            fr.append(pd.read_csv(f, usecols=lambda c: c in cols, low_memory=False))
    d = pd.concat(fr, ignore_index=True)
    d = d[pd.to_numeric(d["persona_id"], errors="coerce").notna()].copy()
    d["persona_id"] = d["persona_id"].astype(float).astype(int)
    d["anio"] = d["temporada"].str[:4].astype(int)
    d["pos3"] = d["pos3"].where(d["pos3"].isin(POS), "A")
    return d


def centrar(o: pd.DataFrame) -> pd.DataFrame:
    """[POST HOC D1-c] Media de cada temporada (ponderada por minutos, jugadores con ≥ 100 min): el filtro trabaja con la
    desviación del jugador frente a su temporada, así el desplazamiento de las medias año a año no se arrastra."""
    o = o.copy()
    b = o[o["min"] >= 100]
    mu = b.groupby("anio").apply(lambda h: np.average(h["y"], weights=h["min"]), include_groups=False)
    o["mu_anio"] = o["anio"].map(mu).fillna(float(np.average(b["y"], weights=b["min"])))
    o["y"] = o["y"] - o["mu_anio"]
    return o


def observaciones(d: pd.DataFrame, m: str) -> pd.DataFrame:
    """Una fila por persona-año: ȳ (media ponderada por precisión de sus ligas), v̄, minutos y posición."""
    tr = CATALOGO[m].transf
    y = transformar(d[m].to_numpy(float), tr)
    lo, hi = transformar(d[f"{m}_lo"].to_numpy(float), tr), transformar(d[f"{m}_hi"].to_numpy(float), tr)
    v = ((hi - lo) / (2 * Z80)) ** 2
    ok = np.isfinite(y) & np.isfinite(v) & (v > 0)
    x = pd.DataFrame({"persona_id": d["persona_id"].to_numpy()[ok], "anio": d["anio"].to_numpy()[ok], "y": y[ok],
                      "w": 1 / v[ok], "min": d["min"].fillna(0).to_numpy()[ok], "pos3": d["pos3"].to_numpy()[ok]})
    x["wy"] = x["w"] * x["y"]
    g = x.sort_values("min").groupby(["persona_id", "anio"])
    o = g.agg(w=("w", "sum"), wy=("wy", "sum"), min=("min", "sum"), pos3=("pos3", "last")).reset_index()
    o["y"] = o["wy"] / o["w"]
    o["v"] = 1 / o["w"]
    return o[["persona_id", "anio", "y", "v", "min", "pos3"]].sort_values(["persona_id", "anio"]).reset_index(drop=True)


# ------------------------------------------------------------------------------------------------------------ filtro
def previa_pos(o: pd.DataFrame, c: float) -> dict:
    out = {}
    for p in POS:
        s = o[o["pos3"] == p]
        if len(s) < 30:
            s = o
        mu, var = float(s["y"].mean()), float(s["y"].var())
        out[p] = (mu, max(var - c * float(s["v"].mean()), 0.05 * var))
    return out


def filtrar(o: pd.DataFrame, tau2: float, c: float, pp: dict) -> pd.DataFrame:
    """Kalman hacia delante por persona. Añade m_pred, P_pred (antes de ver el año) y m, P (después)."""
    o = o.sort_values(["persona_id", "anio"]).reset_index(drop=True)
    pid, an = o["persona_id"].to_numpy(), o["anio"].to_numpy()
    nuevo = np.r_[True, pid[1:] != pid[:-1]]
    gap = np.r_[0, np.diff(an)]
    y, v = o["y"].to_numpy(), c * o["v"].to_numpy()
    mu0 = o["pos3"].map(lambda p: pp[p][0]).to_numpy()
    s0 = o["pos3"].map(lambda p: pp[p][1]).to_numpy()
    n = len(o)
    mp, Pp, m, P = (np.empty(n) for _ in range(4))
    for i in range(n):                                # ~40k persona-año por métrica: bucle simple, rápido en la práctica
        if nuevo[i]:
            mp[i], Pp[i] = mu0[i], s0[i]
        else:
            mp[i], Pp[i] = m[i - 1], P[i - 1] + tau2 * gap[i]
        k = Pp[i] / (Pp[i] + v[i])
        m[i] = mp[i] + k * (y[i] - mp[i])
        P[i] = (1 - k) * Pp[i]
    o["m_pred"], o["P_pred"], o["m"], o["P"] = mp, Pp, m, P
    return o


def _nll(par, o, ini):
    tau2, c = np.exp(par)
    pp = previa_pos(o, c)
    f = filtrar(o, tau2, c, pp)
    S = f["P_pred"] + c * f["v"]
    r = f["y"] - f["m_pred"]
    sel = ~np.r_[True, f["persona_id"].to_numpy()[1:] != f["persona_id"].to_numpy()[:-1]]   # innovaciones con historial
    return float(0.5 * np.sum(np.log(S[sel]) + r[sel] ** 2 / S[sel]))


def ajustar(o: pd.DataFrame, suelo_tau: float = 0.0) -> dict:
    """τ² y c por máxima verosimilitud (innovaciones de personas con temporada previa). suelo_tau (POST HOC D1-c): τ² ≥
    suelo·var(y), para que el filtro nunca congele el nivel del jugador."""
    var = float(o["y"].var())
    x0 = np.log([0.1 * var, 1.0])
    r = minimize(_nll, x0, args=(o, None), method="Nelder-Mead", options={"xatol": 1e-3, "fatol": 1e-2, "maxiter": 120})
    tau2, c = map(float, np.exp(r.x))
    tau2 = max(tau2, suelo_tau * var)
    return {"tau2": tau2, "c": c, "pp": previa_pos(o, c), "var_y": var, "nll": float(r.fun)}


# ------------------------------------------------------------------------------------------------------------ examen
SUELO_TAU_C = 0.01                                     # POST HOC D1-c


def examen_metrica(d: pd.DataFrame, m: str, rng: np.random.Generator, centrado: bool = False) -> dict:
    o_all = observaciones(d, m)
    filas, cortes = [], {}
    for t in [CFG["cortes"]["calibracion"]] + CFG["cortes"]["decision"]:
        tr = o_all[o_all["anio"] <= t]
        if centrado:
            tc = centrar(tr)
            par = ajustar(tc, SUELO_TAU_C)
            f = filtrar(tc, par["tau2"], par["c"], par["pp"])
            f["m"] = f["m"] + f["mu_anio"]                 # predicción de t+1: media de t + desviación filtrada
        else:
            par = ajustar(tr)
            f = filtrar(tr, par["tau2"], par["c"], par["pp"])
        en_t = f[(f["anio"] == t) & (f["min"] >= MIN_EXAMEN)].set_index("persona_id")
        sig = o_all[(o_all["anio"] == t + 1) & (o_all["min"] >= MIN_EXAMEN)].set_index("persona_id")
        comun = en_t.index.intersection(sig.index)
        a, b = en_t.loc[comun], sig.loc[comun]
        sd = float(np.sqrt(par["var_y"]))
        e32 = np.abs(b["y"] - a["y"]) / sd
        e42 = np.abs(b["y"] - a["m"]) / sd
        S = a["P"] + par["tau2"] + par["c"] * b["v"]
        cub = np.abs(b["y"] - a["m"]) <= Z80 * np.sqrt(S)
        cortes[t] = {"n": int(len(comun)), "tau2": par["tau2"], "c": par["c"]}
        filas.append(pd.DataFrame({"corte": t, "persona_id": comun, "e32": e32.to_numpy(), "e42": e42.to_numpy(),
                                   "cub": cub.to_numpy(), "ancho42": 2 * Z80 * np.sqrt(a["P"]).to_numpy() / sd,
                                   "ancho32": 2 * Z80 * np.sqrt(a["v"]).to_numpy() / sd}))
    F = pd.concat(filas, ignore_index=True)

    def dif(h):
        u, inv = np.unique(h["persona_id"].to_numpy(), return_inverse=True)
        dd = (h["e42"] - h["e32"]).to_numpy()
        bs = np.empty(CFG["bootstrap"]["B"])
        for i in range(len(bs)):
            k = rng.multinomial(len(u), np.full(len(u), 1 / len(u)))[inv]
            bs[i] = (k * dd).sum() / k.sum()
        return {"punto": float(dd.mean()), "ic95": [float(np.quantile(bs, .025)), float(np.quantile(bs, .975))],
                "mae32": float(h["e32"].mean()), "mae42": float(h["e42"].mean())}

    dec = F[F["corte"].isin(CFG["cortes"]["decision"])]
    res = {"cortes": {int(t): {**cortes[t], **dif(F[F["corte"] == t]), "cobertura_80": float(F[F["corte"] == t]["cub"].mean())}
                      for t in cortes},
           "conjunto": {**dif(dec), "cobertura_80": float(dec["cub"].mean()), "n": int(len(dec)),
                        "anchura_mediana_42": float(dec["ancho42"].median()), "anchura_mediana_32": float(dec["ancho32"].median())}}
    cada = all(res["cortes"][t]["ic95"][1] < 0 for t in CFG["cortes"]["decision"])
    cob_ok = 0.75 <= res["conjunto"]["cobertura_80"] <= 0.85
    mejora = res["conjunto"]["ic95"][1] < 0
    res["sello"] = "ALTA" if (cada and cob_ok) else "MEDIA" if (mejora and cob_ok) else "BAJA"
    res["version"] = "v4.2" if res["sello"] in ("ALTA", "MEDIA") else "v3.2"
    return res


def examen(centrado: bool = False) -> dict:
    d = cargar([t for t in CFG["temporadas"] if int(t[:4]) <= max(CFG["cortes"]["decision"]) + 1])
    rng = np.random.default_rng(20261109)
    out = {}
    for m in METRICAS:
        out[m] = examen_metrica(d, m, rng, centrado)
        print(f"  {m:16s} {out[m]['sello']:5s} Δ {out[m]['conjunto']['punto']:+.3f} {out[m]['conjunto']['ic95']} "
              f"cob {out[m]['conjunto']['cobertura_80']:.3f} ancho {out[m]['conjunto']['anchura_mediana_42']:.2f}/"
              f"{out[m]['conjunto']['anchura_mediana_32']:.2f}", flush=True)
    SALIDA.mkdir(parents=True, exist_ok=True)
    res = {"prerregistro": "configs/v42.yaml → normalizacion_v42 (commit d606f47)", "metricas": out,
           "resumen": {s: sorted(k for k, v in out.items() if v["sello"] == s) for s in ("ALTA", "MEDIA", "BAJA")}}
    if centrado:
        res["prerregistro"] = "POST HOC D1-c (centrado por temporada y τ² ≥ 0,01·var): se adopta sólo con sello ALTA"
    (SALIDA / ("examen_d1c_post_hoc.json" if centrado else "examen_d1.json")).write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return res


# ------------------------------------------------------------------------------------------------------------ producto
def exportar(destino: Path | None = None) -> dict:
    """Previas por temporada (estado del filtro ANTES de ver la temporada t, con temporadas ≤ t−1) y parámetros, para que
    el navegador combine la previa con las filas de la temporada cargada (la en curso se actualiza sola)."""
    ex = json.loads((SALIDA / "examen_d1.json").read_text(encoding="utf-8"))
    pasan = [m for m, v in ex["metricas"].items() if v["version"] == "v4.2"]
    d = cargar()
    cerradas = [int(t[:4]) for t in CFG["temporadas"]][:-1]           # la en curso no entra en el ajuste
    par, filt = {}, {}
    for m in pasan:
        o = observaciones(d, m)
        oc = o[o["anio"].isin(cerradas)]
        p = ajustar(oc)
        par[m] = {"tau2": p["tau2"], "c": p["c"], "transf": CATALOGO[m].transf, "pos": {k: list(v) for k, v in p["pp"].items()}}
        filt[m] = filtrar(oc, p["tau2"], p["c"], p["pp"])
    destino = destino or (RAIZ / "artifact" / "kerno" / "atlas" / "v42" / "historial")
    destino.mkdir(parents=True, exist_ok=True)
    import base64
    import gzip
    for t in CFG["temporadas"]:
        a = int(t[:4])
        prev = {}
        for m in pasan:
            f = filt[m][filt[m]["anio"] < a]
            u = f.groupby("persona_id").tail(1)
            Pp = u["P"] + par[m]["tau2"] * (a - u["anio"])
            prev[m] = dict(zip(u["persona_id"].astype(int).astype(str), zip(np.round(u["m"], 5).tolist(), np.round(Pp, 6).tolist())))
        personas = sorted(set().union(*[set(v) for v in prev.values()])) if prev else []
        doc = {"version": "v4.2", "temporada": t, "metricas": pasan, "parametros": par,
               "previa": {p: [prev[m].get(p) for m in pasan] for p in personas}}
        raw = json.dumps(doc, separators=(",", ":")).encode()
        (destino / f"{t}.json.gz.txt").write_text(base64.b64encode(gzip.compress(raw, mtime=0)).decode())
        (SALIDA / f"previa_{t}.json").write_text(json.dumps({"temporada": t, "personas": len(personas), "metricas": pasan}))
    return {"metricas": pasan, "parametros": par}
