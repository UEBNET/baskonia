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
    # 3. covarianza en unidades v3.2 y DT por par de la MEZCLA (§11a, cota de Cauchy-Schwarz):
    #    sd_mix(δ_o − δ_d) = w_m · sd_CVAE(δ_o − δ_d) + (1 − w_m) · sd_v2(δ_o − δ_d)
    (out / "covarianza").mkdir(exist_ok=True)
    w_met = _pesos_mezcla(cfg)
    sd_cvae = pares_cvae(tabla, cfg, mets, progreso)
    tabla_pares = []
    for m in mets:
        nd, _, S = leer_covarianza(cov2 / f"{m}.json")
        d = np.array([((ajuste.get(f"{m}|{x.split(':')[0]}") or {}).get("d") or 1.0) for x in nd], float)
        S2 = S / np.outer(d, d)
        dg = np.diag(S2)
        sd_v2 = np.sqrt(np.maximum(dg[:, None] + dg[None, :] - 2 * S2, 0))
        w = float(w_met.get(m, cfg["combinacion"]["peso_v3"]))
        sc = sd_cvae.get(m)
        if sc is not None:
            ix = {c.replace("|", ":"): k for k, c in enumerate(sc["comps"])}
            pos = [ix.get(x) for x in nd]
            M = np.full((len(nd), len(nd)), np.nan)
            ok = [k for k, q in enumerate(pos) if q is not None]
            qq = [pos[k] for k in ok]
            M[np.ix_(ok, ok)] = sc["sd"][np.ix_(qq, qq)]
            sd_mix = np.where(np.isfinite(M), w * M + (1 - w) * sd_v2, sd_v2)
        else:
            sd_mix = sd_v2
        doc = {"metrica": m, "unidades": "constantes lineales v3.2 (DT de la vara EuroLeague)", "nodos": nd,
               "peso_cvae": w, "delta": [_sig(nodos.get(m, {}).get(x, (np.nan, np.nan))[0]) for x in nd],
               "cov_triangular": [_sig(v) for v in S2[np.tril_indices(len(nd))]],
               "sd_par_triangular": [_sig(v) for v in sd_mix[np.tril_indices(len(nd))]],
               "sd_red_triangular": ([_sig(v) if np.isfinite(v) else None for v in M[np.tril_indices(len(nd))]]
                                     if sc is not None else None)}
        (out / "covarianza" / f"{m}.json").write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
        if m in ("pts_p100", "ts_pct"):     # §11d · tabla de la reducción de varianza por par (2025-26)
            ix = {x: k for k, x in enumerate(nd)}
            ligas = sorted({x.split(":")[0] for x in nd if x.endswith(":2025-26")})
            for a_ in ligas:
                for b_ in ligas:
                    if a_ < b_ and f"{a_}:2025-26" in ix and f"{b_}:2025-26" in ix:
                        ia, ib = ix[f"{a_}:2025-26"], ix[f"{b_}:2025-26"]
                        tabla_pares.append({"metrica": m, "a": a_, "b": b_,
                                            "sd_marginales_sumadas": float(np.sqrt(dg[ia] + dg[ib])),
                                            "sd_par_v2": float(sd_v2[ia, ib]), "sd_par_mezcla": float(sd_mix[ia, ib])})
    pd.DataFrame(tabla_pares).round(5).to_csv(out / "reduccion_varianza_pares.csv", index=False)
    # 2. constantes
    n = SI._normalizado(["pos3", "min"] + [f"{m}_obs" for m in mets])
    sop = soporte_destino(n, const, mets, float(cfg.get("destino", {}).get("margen_soporte", 0.25)))
    cdoc = {"version": cfg["version"], "temporada_vara": cfg.get("destino", {}).get("temporada", "2025-26"),
            "formula": "z_d = (θ + deriva(edad) − δ_d)/s_d (sin recortar); valor = T⁻¹(μ_{d,t,pos} + τ_{d,pos}·z_d); "
                       "Var(z_d) = (v_j + sd_par[o,d]²)/s_d² + (z_d − clip(z_d, soporte[d]))²; "
                       "extrapolación si z_d está fuera de soporte[d]",
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
    neg = {}
    for m in mets:          # §11b · filas con Var(θ) − Var(δ_o) < 0 (el código deja como mínimo el 10 % de Var(θ))
        if f"{m}_thsd" in th:
            s2 = th[f"{m}_thsd"].to_numpy(float) ** 2
            vo = np.array([SI._nodo(nodos.get(m, {}), lg, tp)[1] for lg, tp in zip(th["liga"], th["temporada"])])
            ok = np.isfinite(s2) & np.isfinite(vo)
            neg[m] = float(np.mean(s2[ok] < vo[ok])) if ok.any() else None
    cdoc["v_j_negativa_fraccion"] = neg                         # con la varianza de nivel de la v2
    cdoc["v_j_negativa_tras_11b"] = th.attrs.get("vj_negativa")  # §11b: con la del mismo modelo que la fila
    (out / "constantes.json").write_text(json.dumps(cdoc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
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
        ix, S = cov[0], cov[1]
        if no in ix and nd in ix:
            if len(cov) > 2 and cov[2] is not None:          # DT por par de la mezcla (§11a)
                vp = float(cov[2][ix[no], ix[nd]]) ** 2
            else:
                vp = max(S[ix[no], ix[no]] + S[ix[nd], ix[nd]] - 2 * S[ix[no], ix[nd]], 0.0)
    s_d = k["s"][liga_d]
    z = (th + der - d_d) / s_d
    sd = np.sqrt(max(vj, 0) + (vp if np.isfinite(vp) else 0.0)) / s_d
    lo, hi = k["soporte"].get(liga_d, [-np.inf, np.inf])
    zc = float(np.clip(z, lo, hi))                  # §11c · sin recortar el centro: la distancia entra como varianza
    sd_ext = float(np.sqrt(sd ** 2 + (z - zc) ** 2))
    mu, tau = entorno({"mu": k["mu"], "tau2": k["tau2"]}, liga_d, temp_d, fila.get("pos3") or "A")
    return {"valor": float(destransformar(mu + tau * z, k["transf"])), "z": float(z), "sd_z": sd_ext,
            "sd_z_sin_extrapolacion": float(sd), "extrapolacion": bool(z != zc),
            "percentil_destino": float(100 * __import__("scipy.stats").stats.norm.cdf(z))}


def _pesos_mezcla(cfg: dict) -> dict:
    """Peso final de la CVAE por métrica (B2, examen_v32.json); vacío si aún no existe."""
    f = C.dir_salida(cfg) / "validacion" / "examen_v32.json"
    return json.loads(f.read_text(encoding="utf-8")).get("pesos_finales", {}) if f.exists() else {}


def pares_cvae(tabla: pd.DataFrame, cfg: dict, mets: list[str], progreso=print) -> dict:
    """DT de δ_a − δ_b de la CVAE (todas las redes del ajuste final) por métrica y par de competiciones, en la vara
    de la EuroLeague 2025-26: Var = media de las redes de J_a Σ̃_aa J_aᵀ + J_b Σ̃_bb J_bᵀ − 2 J_a Σ̃_ab J_bᵀ más la
    varianza entre redes de la diferencia de niveles."""
    from . import flujo, traduccion
    from .datos import METRICAS
    D, cj = flujo.conjunto(tabla, cfg, None, progreso=None)
    ref = D.comps.index("euroleague|2025-26")
    nC = len(D.comps)
    acc_v, acc_d, acc_d2 = {}, {}, {}
    for m_, P in cj:
        delta, J = traduccion.niveles(m_, P, D, ref)
        cov = P.cov_mu()                                      # (K, nC, nC)
        St = cov - cov[:, :, [ref]] - cov[:, [ref], :] + cov[:, ref, ref][:, None, None]
        dg = np.einsum("kaa->ka", St)
        for m in mets:
            if m not in METRICAS:
                continue
            k = METRICAS.index(m)
            A = J[:, k, :]                                    # (nC, K)
            a2 = (A ** 2 * dg.T).sum(1)
            V = a2[:, None] + a2[None, :] - 2 * np.einsum("ak,bk,kab->ab", A, A, St)
            dd = delta[:, k][:, None] - delta[:, k][None, :]
            acc_v[m] = acc_v.get(m, 0) + V
            acc_d[m] = acc_d.get(m, 0) + dd
            acc_d2[m] = acc_d2.get(m, 0) + dd ** 2
    n = len(cj)
    out = {}
    for m in acc_v:
        var = acc_v[m] / n + np.maximum(acc_d2[m] / n - (acc_d[m] / n) ** 2, 0)
        out[m] = {"comps": list(D.comps), "sd": np.sqrt(np.maximum(var, 0))}
    if progreso:
        progreso(f"  DT por par de niveles de la CVAE: {len(out)} métricas × {nC} competiciones", flush=True)
    return out


# ================================================================================================== artifact · vara
Z80 = 1.2815515655446004


def _simetrica_tril(v, n: int) -> np.ndarray:
    """Matriz simétrica n × n a partir de su triangular inferior en el orden de np.tril_indices (el de la escritura,
    más arriba en este módulo, y el de la lectura de bbfit.sim_insumos.covarianza_destino); None → NaN."""
    X = np.zeros((n, n))
    X[np.tril_indices(n)] = [np.nan if x is None else x for x in v]
    return X + X.T - np.diag(np.diag(X))


def sd_par_matriz(cv: dict) -> np.ndarray:
    """DT del nivel de cada par de nodos, sd(δ_a − δ_b), de un fichero covarianza/<m>.json.
    Usa `sd_par_triangular` (mezcla con la cota de Cauchy-Schwarz); donde falta, √(Σ_aa + Σ_bb − 2Σ_ab) con
    `cov_triangular` (igual que bbfit.sim_insumos.var_par). Corrige la lectura anterior, que usaba np.triu_indices
    sobre datos escritos con np.tril_indices (DT desordenadas y diagonal ≠ 0) y, sin `sd_par_triangular`, tomaba
    covarianzas por desviaciones típicas."""
    n = len(cv["nodos"])
    S = _simetrica_tril(cv["cov_triangular"], n)
    d = np.diag(S)
    desde_cov = np.sqrt(np.maximum(d[:, None] + d[None, :] - 2 * S, 0.0))
    if cv.get("sd_par_triangular") is None:
        return desde_cov
    P = _simetrica_tril(cv["sd_par_triangular"], n)
    return np.where(np.isfinite(P), P, desde_cov)


def vara_artifact(dir_dest: Path | None = None, temp: str = "2025-26") -> dict:
    """Constantes para que el artifact exprese los equivalentes EuroLeague de «Datos Normalizados» en la vara de
    cualquier liga (liga elegida = 0). Por métrica: transformación, s y δ de cada liga en `temp` (EuroLeague: s = 1,
    δ = 0), μ por liga|posición en `temp`, τ por liga|posición, soporte y la DT del nivel de cada par
    (nodo de origen liga:temporada → liga de destino en `temp`, mezcla con la cota de Cauchy-Schwarz). Ver desde_el()."""
    from bbfit.sim_insumos import entorno
    dd = dir_dest or (C.RAIZ / "data" / "modelos" / "v3_2" / "destino")
    const = json.loads((dd / "constantes.json").read_text(encoding="utf-8"))
    ligas = sorted({lg for k in const["metricas"].values() for lg in k["s"]})
    out = {"temporada": temp, "z80": Z80, "ligas": ligas, "metricas": {}}
    for m, k in const["metricas"].items():
        f = dd / "covarianza" / f"{m}.json"
        sp = {}
        if f.exists():
            cv = json.loads(f.read_text(encoding="utf-8"))
            nod = cv["nodos"]
            T = sd_par_matriz(cv)
            ix = {x: i for i, x in enumerate(nod)}
            for o in nod:
                sp[o] = [_sig(T[ix[o], ix[f"{d}:{temp}"]], 4) if f"{d}:{temp}" in ix else None for d in ligas]
        mu, tau = {}, {}
        for lg in ligas:
            for p in "EAI":
                a, b = entorno({"mu": k["mu"], "tau2": k["tau2"]}, lg, temp, p)
                mu[f"{lg}|{p}"], tau[f"{lg}|{p}"] = _sig(a, 6), _sig(b, 6)
        out["metricas"][m] = {
            "transf": k["transf"], "sentido": k.get("sentido"),
            "s": {lg: _sig(1.0 if lg == "euroleague" else k["s"].get(lg, np.nan), 6) for lg in ligas},
            "delta": {lg: (0.0 if lg == "euroleague" else _sig((k["nodos"].get(f"{lg}:{temp}") or [np.nan])[0], 6))
                      for lg in ligas},
            "mu": mu, "tau": tau, "soporte": k.get("soporte", {}), "sp": sp}
    return out


def desde_el(v, lo, hi, m: str, liga_o: str, temp_o: str, pos: str, liga_d: str, vd: dict) -> dict:
    """Referencia (Python) de la conversión que hace el artifact: equivalente EuroLeague (con su intervalo del 80 %)
    → misma capacidad en la vara de `liga_d`. z_EL = (T(v) − μ_EL)/τ_EL = θ + deriva; z_d = (z_EL − δ_d)/s_d.
    Cada cola del intervalo: v_j = sd_EL² − sd_par(o, EL)² (como mínimo el 10 % de sd_EL²), sd_d² = (v_j + sd_par(o, d)²)/s_d²
    (+ la distancia fuera del soporte de la liga de destino al cuadrado). Con liga_d = euroleague devuelve v, lo, hi."""
    from bbmodel.metricas import destransformar, transformar
    k = vd["metricas"][m]
    p = pos if pos in ("E", "A", "I") else "A"
    tf = k["transf"]
    mu_e, tau_e = k["mu"][f"euroleague|{p}"], k["tau"][f"euroleague|{p}"]
    mu_d, tau_d = k["mu"][f"{liga_d}|{p}"], k["tau"][f"{liga_d}|{p}"]
    s_d, d_d = k["s"][liga_d], k["delta"][liga_d]
    z = lambda x: (float(transformar(x, tf)) - mu_e) / tau_e  # noqa: E731
    ze = z(v)
    zd = (ze - d_d) / s_d
    nodo = f"{liga_o}:{temp_o}"
    if nodo not in k["sp"]:                                   # temporada sin nodo (2026-27): la última de su liga
        cand = sorted(x for x in k["sp"] if x.startswith(f"{liga_o}:"))
        nodo = cand[-1] if cand else None
    ligas = vd["ligas"]
    sp = k["sp"].get(nodo) if nodo else None
    sp_e = (sp[ligas.index("euroleague")] if sp else None) or 0.0
    sp_d = (sp[ligas.index(liga_d)] if sp else None) or 0.0
    lo_s, hi_s = k["soporte"].get(liga_d, [-np.inf, np.inf])
    ext = zd - float(np.clip(zd, lo_s, hi_s))
    out = {"valor": float(destransformar(mu_d + tau_d * zd, tf)), "z": zd, "extrapolacion": bool(ext != 0)}
    for lado, x, sg in (("lo", lo, -1), ("hi", hi, 1)):
        if x is None or not np.isfinite(x):
            out[lado] = None
            continue
        sd_e = abs(ze - z(x)) / vd["z80"]
        vj = max(sd_e ** 2 - sp_e ** 2, 0.1 * sd_e ** 2)
        sd_d = np.sqrt((vj + sp_d ** 2) / s_d ** 2 + ext ** 2)
        out[lado] = float(destransformar(mu_d + tau_d * (zd + sg * vd["z80"] * sd_d), tf))
    return out
