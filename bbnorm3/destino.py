"""v3.2 · vara de DESTINO: cualquier liga a 0 (ACB = 0, BBL = 0…) cuando es la liga de destino de la comparación.

La normalización no fija ninguna liga: «EuroLeague = 0» es sólo la forma de expresar la salida. Para que el artifact
pueda expresar todo en la vara de la liga de destino d (temporada t_d) se exportan:

  1. capacidad/<temporada>.csv.gz   por fila jugador-liga-temporada y métrica m: θ (DT de la vara EuroLeague,
     v3.2) y la varianza PROPIA del jugador v_j = Var(θ) − Var(δ_o) (sin la incertidumbre del nivel de su liga de
     origen frente a la EuroLeague, que se cuenta aparte y con su covarianza);
  2. constantes.json   por métrica: transformación, escala s_l, nivel medio m_l, ψ_l, deriva por edad, μ por
     liga|temporada|posición, τ² por liga|posición y nivel δ de cada competición-temporada (las mismas constantes
     lineales que usa el simulador: bbfit.sim_insumos.traduccion_v31 sobre la v3.2);
  3. covarianza/<métrica>.json   covarianza conjunta Σ de los niveles δ de todas las competiciones-temporada
     (posterior de la contracción jerárquica del grafo de puentes de la v2, en las unidades de las constantes).

Traducción de una fila (liga o, temporada t_o) a la vara de d (bbnorm3.destino.a_destino, igual que el simulador):
    z_d   = (θ + deriva(edad) − δ_d) / s_d
    valor = T⁻¹(μ_{d,t_d,pos} + τ_{d,pos} · z_d)            (el valor que tendría en d; percentil en d = Φ(z_d))
    Var(z_d) = (v_j + Var(δ_o − δ_d)) / s_d²,   Var(δ_o − δ_d) = Σ_oo + Σ_dd − 2 Σ_od
Nivel de cualquier liga X en la vara de d («d = 0»): δ_X − δ_d, con DT √(Σ_XX + Σ_dd − 2 Σ_Xd).
Con d = EuroLeague se recupera exactamente la salida de siempre (Σ de la EuroLeague = 0).

La mezcla v2/CVAE de la v3.2 se hace en la escala de trabajo de cada métrica; como la traducción a la liga de
destino es afín en esa escala, mezclar en la vara EuroLeague o en la del destino da el mismo centro (y los intervalos
se trasladan con la misma escala): la vara de destino no cambia el valor esperado, sí la incertidumbre (covarianza)
y el recorte de soporte (rango observado de la liga de destino).

    python -m bbnorm3 --config configs/normalization_v32.yaml destino-covarianza   # paso 3 (v2, una vez)
    python -m bbnorm3 --config configs/normalization_v32.yaml destino               # pasos 1-2 (tras la v3.2)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C


def dir_destino(cfg: dict) -> Path:
    d = C.dir_salida(cfg) / "destino"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ------------------------------------------------------------------------------------------ 3. covarianza (v2)
def covarianza_v2(cfg: dict, tabla: pd.DataFrame | None = None, progreso=print) -> Path:
    """Covarianza conjunta de los niveles de la normalización amortiguada (todas las temporadas, variante elegida)."""
    from bbmodel import amortiguacion as AM
    from bbmodel import modelo
    out = dir_destino(cfg) / "covarianza_v2"
    out.mkdir(parents=True, exist_ok=True)
    if (out / "_hecho").exists():
        return out
    if tabla is None:
        tabla, _ = modelo.preparar()
    acfg = AM.config()
    variante = acfg.get("variante", "completo")
    op = AM.opciones_variante(acfg, variante)
    params = AM.cargar_parametros_A()
    aj = AM.ajustar(tabla, params, acfg, progreso=None, **op)
    for col, r in aj["resultados"].items():
        est, ng, ref = r["estado"], r["nodos_g"], r["ref_nodos"]
        cov = np.asarray(r["contraccion"]["cov"], float)
        idx = [0 if n in ref else ng.index(n) for n in est.nodos]
        S = cov[np.ix_(idx, idx)]                      # Σ en el orden de los nodos (las de la referencia: 0)
        doc = {"metrica": col, "variante": variante, "referencia": aj["ref"], "nodos": list(est.nodos),
               "delta": [float(x) for x in est.delta],
               "cov_triangular": [float(x) for x in S[np.tril_indices(len(idx))]]}
        (out / f"{col}.json").write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    (out / "_hecho").write_text(variante)
    if progreso:
        progreso(f"  covarianza v2 de {len(aj['resultados'])} métricas en {out}", flush=True)
    return out


def leer_covarianza(ruta: Path) -> tuple[list[str], np.ndarray, np.ndarray]:
    d = json.loads(Path(ruta).read_text(encoding="utf-8"))
    n = len(d["nodos"])
    S = np.zeros((n, n))
    S[np.tril_indices(n)] = d["cov_triangular"]
    S = S + S.T - np.diag(np.diag(S))
    return d["nodos"], np.asarray(d["delta"], float), S


def var_par(nodos_idx: dict, S: np.ndarray, a: str, b: str) -> float:
    """Var(δ_a − δ_b) = Σ_aa + Σ_bb − 2 Σ_ab (nodos «liga:temporada»); NaN si alguno no está en el grafo."""
    ia, ib = nodos_idx.get(a), nodos_idx.get(b)
    if ia is None or ib is None:
        return np.nan
    return float(max(S[ia, ia] + S[ib, ib] - 2 * S[ia, ib], 0.0))


# ------------------------------------------------------------------------------------------ 1-2. capacidad y constantes
def _sig(x, n=6):
    x = float(x)
    if not np.isfinite(x) or x == 0:
        return x if np.isfinite(x) else None
    return round(x, max(0, n - 1 - int(np.floor(np.log10(abs(x))))))


def soporte_destino(n: pd.DataFrame, const: dict, metricas: list[str], margen: float) -> dict:
    """Rango observado de z en cada liga (cuantiles 0,5 % y 99,5 % de los jugadores con ≥ 300 min) ± margen DT:
    el valor traducido a la vara de la liga de destino se recorta a ese soporte (v3.1: al de la EuroLeague)."""
    from bbfit.sim_insumos import entorno
    from bbmodel.metricas import transformar
    out = {}
    n = n[pd.to_numeric(n["min"], errors="coerce") >= 300]
    for m in metricas:
        if f"{m}_obs" not in n or m not in const:
            continue
        k = const[m]
        out[m] = {}
        for liga, g in n.groupby("liga"):
            z = []
            for (t, pos), h in g.groupby(["temporada", "pos3"]):
                mu, tau = entorno(k, liga, t, pos)
                if np.isfinite(mu) and np.isfinite(tau) and tau > 0:
                    z.append((transformar(pd.to_numeric(h[f"{m}_obs"], errors="coerce").to_numpy(float), k["transf"])
                              - mu) / tau)
            z = np.concatenate(z) if z else np.array([])
            z = z[np.isfinite(z)]
            if len(z) >= 30:
                out[m][liga] = [_sig(np.quantile(z, 0.005) - margen, 4), _sig(np.quantile(z, 0.995) + margen, 4)]
    return out


def exportar(tabla: pd.DataFrame, cfg: dict, progreso=print) -> Path:
    """Pasos 1-2 (tras la v3.2 y `bbfit dataset-simulador` con CERNO_SIMULADOR=v32) y la covarianza en las unidades
    de las constantes lineales de la v3.2: Σ'_ab = Σ_ab / (d_a · d_b) (d = pendiente del sustituto lineal de cada liga)."""
    import os
    if os.environ.get("CERNO_SIMULADOR") != "v32":
        raise RuntimeError("bbnorm3 destino necesita CERNO_SIMULADOR=v32 (constantes del simulador v3.2)")
    from bbfit import sim_insumos as SI
    from bbmodel.metricas import CATALOGO
    out = dir_destino(cfg)
    cov2 = covarianza_v2(cfg, tabla, progreso)
    mets = [m for m in CATALOGO if (cov2 / f"{m}.json").exists()]
    trad = SI.traduccion_v31(mets)
    const, nodos, ajuste = trad["constantes"], trad["nodos"], trad["ajuste"]
    mets = [m for m in mets if m in const]
    # 3. covarianza en unidades v3.2
    (out / "covarianza").mkdir(exist_ok=True)
    for m in mets:
        nd, _, S = leer_covarianza(cov2 / f"{m}.json")
        d = np.array([((ajuste.get(f"{m}|{x.split(':')[0]}") or {}).get("d") or 1.0) for x in nd], float)
        S2 = S / np.outer(d, d)
        doc = {"metrica": m, "unidades": "constantes lineales v3.2 (DT de la vara EuroLeague)", "nodos": nd,
               "delta": [_sig(nodos.get(m, {}).get(x, (np.nan, np.nan))[0]) for x in nd],
               "cov_triangular": [_sig(v) for v in S2[np.tril_indices(len(nd))]]}
        (out / "covarianza" / f"{m}.json").write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    # 2. constantes
    n = SI._normalizado(["pos3", "min"] + [f"{m}_obs" for m in mets])
    sop = soporte_destino(n, const, mets, float(cfg.get("destino", {}).get("margen_soporte", 0.25)))
    cdoc = {"version": cfg["version"], "temporada_vara": cfg.get("destino", {}).get("temporada", "2025-26"),
            "formula": "z_d = (θ + deriva(edad) − δ_d)/s_d; valor = T⁻¹(μ_{d,t,pos} + τ_{d,pos}·z_d); "
                       "Var(z_d) = (v_j + Σ_oo + Σ_dd − 2Σ_od)/s_d²; z_d recortado a soporte[d]",
            "metricas": {}}
    for m in mets:
        k = const[m]
        cdoc["metricas"][m] = {
            "transf": k["transf"], "sentido": k.get("sentido"), "s": {a: _sig(b) for a, b in k["s"].items()},
            "m": {a: _sig(b) for a, b in k["m"].items()}, "psi": {a: _sig(b) for a, b in k["psi"].items()},
            "deriva": {a: _sig(b) for a, b in k["deriva"].items()}, "eta2": _sig(k.get("eta2", 0.0)),
            "mu": {a: _sig(b) for a, b in k["mu"].items()}, "tau2": {a: _sig(b) for a, b in k["tau2"].items()},
            "nodos": {a: [_sig(b[0]), _sig(b[1])] for a, b in nodos.get(m, {}).items()},
            "soporte": sop.get(m, {})}
    (out / "constantes.json").write_text(json.dumps(cdoc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    # 1. capacidad
    th = SI.theta_completa("V32", mets, trad)
    base = SI._normalizado(["persona_id", "team_id", "edad", "min"])
    th = th.merge(base, on=["liga", "temporada", "player_id"], how="left")
    (out / "capacidad").mkdir(exist_ok=True)
    cols = ["persona_id", "liga", "temporada", "player_id", "team_id", "pos3", "edad", "min"] + \
        [c for m in mets for c in (f"{m}_th", f"{m}_vj")]
    for t, g in th.groupby("temporada"):
        g[[c for c in cols if c in g]].to_csv(out / "capacidad" / f"{t}.csv.gz", index=False, float_format="%.5g")
    if progreso:
        progreso(f"  vara de destino: {len(mets)} métricas, {len(th)} filas → {out}", flush=True)
    return out


def a_destino(fila: dict, m: str, liga_d: str, temp_d: str, cdoc: dict, cov: tuple[dict, np.ndarray] | None,
              temp_nivel: str | None = None) -> dict:
    """Referencia (Python) de la traducción a la vara de la liga de destino que hará el artifact: valor, z, sd de z."""
    from bbfit.sim_insumos import entorno
    from bbmodel.enlace import tramo_edad
    from bbmodel.metricas import destransformar
    k = cdoc["metricas"][m]
    th, vj = float(fila[f"{m}_th"]), float(fila[f"{m}_vj"])
    edad = fila.get("edad")
    der = k["deriva"].get(tramo_edad(edad), 0.0) if edad is not None and np.isfinite(float(edad)) else 0.0
    nd = f"{liga_d}:{temp_nivel or temp_d}"
    no = f"{fila['liga']}:{fila['temporada']}"
    d_d = 0.0 if liga_d == "euroleague" else (k["nodos"].get(nd) or [np.nan])[0]
    vp = np.nan
    if cov is not None:
        ix, S = cov
        if no in ix and nd in ix:
            vp = max(S[ix[no], ix[no]] + S[ix[nd], ix[nd]] - 2 * S[ix[no], ix[nd]], 0.0)
    s_d = k["s"][liga_d]
    z = (th + der - d_d) / s_d
    sd = np.sqrt(max(vj, 0) + (vp if np.isfinite(vp) else 0.0)) / s_d
    lo, hi = k["soporte"].get(liga_d, [-np.inf, np.inf])
    z = float(np.clip(z, lo, hi))
    mu, tau = entorno({"mu": k["mu"], "tau2": k["tau2"]}, liga_d, temp_d, fila.get("pos3") or "A")
    return {"valor": float(destransformar(mu + tau * z, k["transf"])), "z": z, "sd_z": float(sd),
            "percentil_destino": float(100 * __import__("scipy.stats").stats.norm.cdf(z))}
