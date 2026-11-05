"""Tablas de la v4.0 para el Atlas (navegador): `data/artifact/atlas_v40/`.

    python -m bbequipo exportar-atlas [--salida data/artifact/atlas_v40]

jugadores_v40.json  por persona: β y sd por temporada (F1, red net), prior del perfil por temporada, y por temporada con perfil
                    la corrección aditiva h (F3, red aditiva) y los factores de pareja a = P_rᵀ z (F2-A, M_rango de rango r):
                    φ_ij = Σ_k w_k · a_ik · a_jk. Reglas de `equipo.Insumos.valor`: β de la última temporada ≤ t; si no, prior
                    del perfil de t; si no, nivel medio de los recién llegados a la liga (`nivel_nuevo`).
referencias_v40.json  F_ref (NC: liga × puesto, `anclas.referencias_nc_<t>.json`), F_mov (IM: grupo de liga, `referencia_im.json`),
                    grupos de liga (F4 y F5), calibración de la capa 4 (c, d, s0, q por grupo) y las capas de calibración de
                    las anclas ajustadas con TODOS los cortes del examen: NC crudo → percentil realizado (isotónica) con el
                    rango del 80 % condicionado al decil, e IM crudo → percentil on/off realizado (criterio `im_onoff`).
Lo que hace el navegador con estas tablas (atlas/v40.js) es la capa 4 y las anclas con los minutos del motor del Atlas
(v3.3 en JS): misma β, parejas, red aditiva, calibración y referencias que la v4.0; sólo cambian los minutos (declarado).
"""
from __future__ import annotations

import json
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from . import rapm as RP
from . import sinergia as SG
from . import conjunto as CJ
from . import equipo as EQ
from . import anclas as AN

SALIDA = C.RAIZ / "data" / "artifact" / "atlas_v40"


def _r(x, d=4):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(x) else round(x, d)


def _isotonica(x: np.ndarray, y: np.ndarray, rejilla: np.ndarray) -> list:
    from sklearn.isotonic import IsotonicRegression
    g = IsotonicRegression(y_min=0.0, y_max=100.0, out_of_bounds="clip").fit(x, y)
    return [round(float(v), 2) for v in g.predict(rejilla)]


def _rango_condicionado(x: np.ndarray, y: np.ndarray, n_bins: int = 10) -> dict:
    """Cuantiles 10 y 90 de y por decil de x (como `anclas.calibrar_nc`), interpolando deciles vacíos."""
    bordes = np.quantile(x, np.linspace(0, 1, n_bins + 1)); bordes[0], bordes[-1] = -np.inf, np.inf
    b = np.clip(np.searchsorted(bordes, x, side="right") - 1, 0, n_bins - 1)
    q10 = pd.Series([np.quantile(y[b == k], 0.10) if (b == k).sum() >= 20 else np.nan for k in range(n_bins)]).interpolate(limit_direction="both")
    q90 = pd.Series([np.quantile(y[b == k], 0.90) if (b == k).sum() >= 20 else np.nan for k in range(n_bins)]).interpolate(limit_direction="both")
    return {"bordes": [None if not np.isfinite(v) else round(float(v), 3) for v in bordes], "q10": [round(float(v), 2) for v in q10],
            "q90": [round(float(v), 2) for v in q90], "n": int(len(x))}


def jugadores(cfg: dict, progreso=print) -> dict:
    from .examen_f1 import perfiles_completo
    t0 = time.time()
    tr = RP.tramos(cfg, None, progreso=None)
    temps = sorted(tr["temporada"].unique())
    con_perfil = [t for t in temps if (C.dir_salida(cfg) / "perfiles" / f"{t}.csv.gz").exists()]
    T = RP.tabla_prior(perfiles_completo(cfg, con_perfil), cfg)
    tipo = cfg["f1"]["prior"].get("elegido") or json.loads((RP.dir_salida(cfg) / "examen" / "resumen_examen.json").read_text())["decisiones"]["prior"]["elegido"]
    pr = cfg["f1"].get("producto") or {}
    cfg_p = C.con(cfg, **{"f1.bayes_empirico.tau_rejilla": pr.get("tau_rejilla", cfg["f1"]["bayes_empirico"]["tau_rejilla"]),
                          "f1.prior.ridge_alpha_rejilla": pr.get("ridge_alpha_rejilla", cfg["f1"]["prior"]["ridge_alpha_rejilla"])}) if pr else cfg
    res = pickle.loads((C.RAIZ / "experimentos" / "v4_0" / f"producto_f1_net_{tipo}_{RP.huella_ajuste(cfg_p)}.pkl").read_bytes())
    D = RP.construir_diseno(tr, "net")
    tb = RP.tabla_beta(res, D).merge(RP.ligas_jugador(tr), on="clave", how="left")
    tb["anio"] = tb["temporada"].str[:4].astype(int)
    prior = res["priors"][0]
    g_prior = dict(zip(T["clave"], prior.predecir(T))) if prior is not None else {}
    t2 = np.atleast_1d(np.asarray(res.get("tau2", np.nan), float)).ravel()[0]
    tau = float(np.sqrt(t2)) if np.isfinite(t2) and t2 > 0 else float(np.nanmedian(tb["beta_sd"]))
    prim = tb.groupby("persona_id")["anio"].transform("min")
    nuevos = tb[(tb["anio"] == prim) & (tb["anio"] > 2020)].assign(w=lambda d: np.maximum(d["poss"], 1.0))
    nivel_nuevo = nuevos.groupby("liga_principal").apply(lambda g: float(np.average(g["beta"], weights=g["w"]))).to_dict()
    nivel_nuevo_global = float(np.mean(list(nivel_nuevo.values())))
    progreso(f"  β de {tb['persona_id'].nunique()} personas ({len(tb)} persona-temporada) · perfiles {len(T)} · τ {tau:.2f} · {time.time() - t0:.0f} s", flush=True)
    # F2-A: factores de pareja (M_rango = P diag(w) Pᵀ)
    R = SG.Rasgos(T, cfg)
    Mr = np.load(SG.dir_salida(cfg) / "M_rango.npy")
    w, P = np.linalg.eigh(Mr)
    keep = np.argsort(-np.abs(w))[: int(np.linalg.matrix_rank(Mr, tol=1e-8))]
    w, P = w[keep], P[:, keep]
    A = R.Z @ P                                             # (n perfiles × r)
    # F3: corrección aditiva h por perfil (red aditiva) y para «sin perfil»
    est = pickle.loads((CJ.dir_salida(cfg) / "redes.pkl").read_bytes())
    red = CJ.ConjuntoNet(R.Z, cfg).cargar(est["estado"], int(cfg["semilla"]))
    cero = len(R.idx)
    idx = np.arange(cero + 1)
    I = np.column_stack([idx] + [np.full(len(idx), cero)] * 9)
    h = np.asarray(red.predecir(I), float)
    h0 = float(h[cero]); h = h[:cero]
    progreso(f"  F2-A rango {len(w)} · F3 h de {cero} perfiles (sin perfil {h0:+.3f}) · {time.time() - t0:.0f} s", flush=True)
    personas: dict = {}
    for r in tb.itertuples(index=False):
        p = personas.setdefault(r.persona_id, {})
        p.setdefault("b", {})[r.temporada] = [_r(r.beta, 3), _r(r.beta_sd, 3)]
    claves = list(T["clave"])
    for k, clave in enumerate(claves):
        pid, temp = clave.rsplit("|", 1)
        p = personas.setdefault(pid, {})
        g = g_prior.get(clave)
        if g is not None and np.isfinite(g):
            p.setdefault("g", {})[temp] = _r(g, 3)
        i = R.idx.get(clave)
        if i is not None:
            p.setdefault("z", {})[temp] = [_r(h[i], 4)] + [_r(v, 4) for v in A[i]]
    return {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "tau": round(tau, 4), "nivel_nuevo": {k: round(v, 4) for k, v in nivel_nuevo.items()},
            "nivel_nuevo_global": round(nivel_nuevo_global, 4), "w": [round(float(v), 6) for v in w], "h0": round(h0, 4), "rango": len(w),
            "rasgos": R.columnas, "temporadas": temps, "n_personas": len(personas), "personas": personas}


def referencias(cfg: dict, progreso=print) -> dict:
    an = AN.dir_salida(cfg)
    ref_nc = sorted(an.glob("referencias_nc_*.json"))[-1]
    nc_ref = json.loads(ref_nc.read_text(encoding="utf-8"))
    im_ref = json.loads((an / "referencia_im.json").read_text(encoding="utf-8"))
    cal4 = json.loads((EQ.dir_salida(cfg) / "calibracion.json").read_text(encoding="utf-8"))
    rejilla = np.arange(0, 101, 1.0)
    nc = pd.read_csv(an / "nc_examen.csv.gz")
    nc = nc[nc["eval"].astype(bool) & nc["NC1_crudo"].notna() & nc["pct_realizado"].notna()]
    cal_nc = {"x": [float(v) for v in rejilla], "y": _isotonica(nc["NC1_crudo"].to_numpy(float), nc["pct_realizado"].to_numpy(float), rejilla),
              **_rango_condicionado(nc["NC1_crudo"].to_numpy(float), nc["pct_realizado"].to_numpy(float)), "cortes": sorted(int(a) for a in nc["anio"].unique())}
    im = pd.read_csv(an / "im_examen.csv.gz")
    im = im[im["IM_crudo"].notna() & im["pct_onoff"].notna()]
    cal_im = {"x": [float(v) for v in rejilla], "y": _isotonica(im["IM_crudo"].to_numpy(float), im["pct_onoff"].to_numpy(float), rejilla),
              **_rango_condicionado(im["IM_crudo"].to_numpy(float), im["pct_onoff"].to_numpy(float)), "cortes": sorted(int(a) for a in im["anio"].unique())}
    grupos_im = {l: g for g, ls in cfg["f5"]["impacto"]["referencia"]["grupos"].items() for l in ls}
    est = json.loads((an / "F5_anclas.json").read_text(encoding="utf-8")).get("estado", {})
    progreso(f"  F_ref {len(nc_ref['F_ref'])} liga×puesto ({nc_ref['temporada']}) · F_mov {list(im_ref['F_mov'])} · calibración NC con {cal_nc['n']} fichajes, IM con {cal_im['n']}", flush=True)
    return {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "temporada_ref": nc_ref["temporada"],
            "F_ref": nc_ref["F_ref"], "F_mov": {g: v["cuantiles"] | {"n": v["n"]} if False else {"n": v["n"], "cuantiles": v["cuantiles"]} for g, v in im_ref["F_mov"].items()},
            "grupo_im": grupos_im, "grupo_f4": EQ.GRUPOS_LIGA, "calibracion_f4": {"conjunto": cal4["conjunto"], "por_grupo": cal4["por_grupo"]},
            "cal_nc": cal_nc, "cal_im": cal_im, "estado": est,
            "nota": "NC: percentil esperado de C = (min/partido ÷ min del partido) × pts/100 en F_ref(liga de destino × puesto); IM: percentil esperado de "
                    "Δ̂Net = c·(T con − T sin) en F_mov(grupo de liga), ambos calibrados con los cortes del examen (nc_examen, im_examen). "
                    "Minutos del motor del Atlas (v3.3 JS), no del motor Python: aproximación declarada."}


def main(salida: str | Path = SALIDA, progreso=print) -> dict:
    cfg = C.cargar()
    out = Path(salida); out.mkdir(parents=True, exist_ok=True)
    j = jugadores(cfg, progreso)
    (out / "jugadores_v40.json").write_text(json.dumps(j, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    r = referencias(cfg, progreso)
    (out / "referencias_v40.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    progreso(f"  escrito {out} (jugadores {(out / 'jugadores_v40.json').stat().st_size / 1e6:.1f} MB)", flush=True)
    return {"personas": j["n_personas"], "F_ref": len(r["F_ref"])}
