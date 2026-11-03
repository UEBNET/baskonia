"""Simulador v3.2 · decisiones A1-A4 con cortes anidados sobre el examen temporal (bbfit/validacion.py), con los
criterios matemáticos del 02-11-2026 (docs/simulador_v32.md), aprobados por el usuario ANTES de ver resultados.

Entradas: data/modelos/simulador/v3_2/validacion/<etiqueta>/predicciones.csv.gz de las dos fuentes de capacidad:
  * «V32»        normalización v3.2 ajustada con todas las temporadas (con fuga en el examen);
  * «V32_corte»  normalización v3.2 ajustada sólo con ≤ t (sin fuga, §1);
y, para cada una, la ejecución completa (que guarda la rejilla A3 sobre las mismas simulaciones, la producción sin
ruido personal y la contribución C) y las ejecuciones con un paso apagado (CERNO_SIM_VARIANTE=sin_<paso>).

§1  A4 y toda cifra absoluta: sólo V32_corte. A1, A3 y A2 (decisiones relativas) se calculan con las dos fuentes; la
    decisión se acepta si coincide; si no, manda V32_corte.
§2  A1 · no inferioridad (Δ = MAE_sin/MAE_con − 1, IC 90 % bootstrap por club de destino × corte, pareado). Se QUITA
    el paso si: IC90,sup(Δ_pts) y IC90,sup(Δ_TS) < +0,5 %; IC90,sup(Δ_min) < +1 % e IC90,inf(acierto_sin − acierto_con)
    > −0,5 pp; IC90,sup(Δ) < +1 % en USG%, AST% y TOV%; Δ_pts puntual con destino EuroLeague < +2 %; (ruido personal)
    IC90,sup(ΔR del Winkler del 80 % de pts/100, recalibración anidada) < +1 %; y (§6c) IC90,sup(ΔR del MAE de C en
    P_all) < +1 %. Si algo empeora de forma significativa → se CONSERVA; si no se cumple todo pero nada empeora →
    «indeterminado» (se conserva). Si se quitan los dos pasos con ejecución propia hace falta la ejecución combinada.
§3  A3 · regla de 1 error típico: K₁ = {k : J(k) − J(k*) ≤ SE_boot(J(k) − J(k*))}; dentro de K₁, el de menor
    k_β + k_c (parsimonia, decisión del usuario), que además cumpla §6c.
§4  A2 frente a A3 · J_ω = Σ ω_m MAE_m/MAE_m(v3.1), ω = pts 0,30, TS 0,30, USG 0,15, AST 0,15, TOV 0,10. A2 si
    IC90,sup[J_ω(A2) − J_ω(A3)] < 0, Δ_pts(A2 frente a A3 | destino EuroLeague) < +2 % y cumple §6c.
§5  A4 · niveles 50, 80 y 90 %; dos colas por separado (cuantiles con signo); pesos por recencia ρ^(t−1−s) con
    ρ = 0,5 y cuantil ponderado con corrección de muestra finita (nivel ⌈(n_w + 1)q⌉/n_w, n_w = (Σw)²/Σw²); grupos con
    contracción f_g = (n_g f̂_g + n₀ f̂_padre)/(n_g + n₀), n₀ = 30: destino (4) → destino × origen {FEB3, NCAA, resto}
    si n ≥ 15; aceptación |Cob − α| ≤ 2√(α(1−α)/n) + 0,02 por métrica y grupo de destino con n ≥ 100.
§6  poblaciones: P_all (≥ 5 partidos), P_300 (≥ 300 min; deciden A1-A4), P_50-300 (error tipificado con el ruido de
    muestra) y la contribución C = (min/partido ÷ minutos del partido) · pts/100 en P_all.
§7  informe: Spearman por liga de destino × corte, decil superior, Brier y fiabilidad de P(C ≥ p75 de la liga).

    CERNO_SIMULADOR=v32 python -m bbfit v32-decidir
"""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd

from . import validacion as V
from .config import cargar

NIVELES = ("50", "80", "90")
Q = {"50": 0.5, "80": 0.8, "90": 0.9}
SECUNDARIAS = ["usg_pct", "ast_pct", "tov_pct"]
FUENTES = ("V32", "V32_corte")


def cfg() -> dict:
    return cargar("simulation")


def grupo_destino(liga_o: pd.Series, liga_d: pd.Series) -> pd.Series:
    from bbnorm3.examen import grupo
    return grupo(liga_o.astype(str).reset_index(drop=True), liga_d.astype(str).reset_index(drop=True))


def grupo_origen(liga_o: pd.Series) -> pd.Series:
    lo = liga_o.astype(str).reset_index(drop=True)
    return pd.Series(np.where(lo == "feb3", "feb3", np.where(lo == "ncaa", "ncaa", "resto")))


def ok_produccion(e: pd.DataFrame) -> np.ndarray:
    return (e["min_total_real"] >= cfg()["validacion"]["min_minutos_produccion"]).to_numpy(bool)


def _gm(e: pd.DataFrame) -> np.ndarray:
    from .simulador import minutos_partido
    return np.array([minutos_partido(l) for l in e["liga_d"]], float)


# ------------------------------------------------------------------------------------------ candidatos
def _k(x: float) -> str:
    return repr(float(x))


def _niv(e: pd.DataFrame, pre: str) -> list[str]:
    return [a for a in NIVELES if f"{pre}_lo{a}" in e]


def produccion(e: pd.DataFrame, metodo: str, kb: float = 1.0, kc: float = 1.0, sin_ruido: bool = False) -> dict:
    """{métrica: DataFrame(pred, lo50, hi50, lo80, hi80, lo90, hi90)} de un método de producción, y «C»."""
    mets = cfg()["produccion"]["metricas"]
    out = {}
    for m in mets:
        if metodo == "atlas":
            out[m] = pd.DataFrame({"pred": e[f"a_{m}_pred"].to_numpy(float),
                                   **{f"{s}{a}": np.nan for a in NIVELES for s in ("lo", "hi")}})
            continue
        if m in ("pts_p100", "ts_pct") and f"v_g{_k(kb)}_{_k(kc)}_{m}_pred" in e:
            pre = f"v_g{_k(kb)}_{_k(kc)}_{m}" + ("_motor" if sin_ruido else "")
        else:
            pre = f"v_{m}" + ("_motor" if sin_ruido else "")
        out[m] = pd.DataFrame({"pred": e[f"{pre}_pred"].to_numpy(float),
                               **{f"{s}{a}": (e[f"{pre}_{s}{a}"].to_numpy(float) if f"{pre}_{s}{a}" in e else np.nan)
                                  for a in NIVELES for s in ("lo", "hi")}})
    # contribución C (§6): la del motor con esos factores; con A2, minutos del motor × pts/100 del Atlas
    if metodo == "atlas":
        c = e["v_min_media"].to_numpy(float) / _gm(e) * e["a_pts_p100_pred"].to_numpy(float)
    elif f"v_g{_k(kb)}_{_k(kc)}_contribucion_pred" in e:
        c = e[f"v_g{_k(kb)}_{_k(kc)}_contribucion_pred"].to_numpy(float)
    else:
        c = e["v_C_pred"].to_numpy(float) if "v_C_pred" in e else np.full(len(e), np.nan)
    out["C"] = pd.DataFrame({"pred": c, **{f"{s}{a}": (e[f"v_C_{s}{a}"].to_numpy(float) if f"v_C_{s}{a}" in e
                                                       and metodo != "atlas" else np.nan)
                                         for a in NIVELES for s in ("lo", "hi")}})
    return out


def minutos(e: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"pred": e["v_min_pred"].to_numpy(float),
                         **{f"{s}{a}": (e[f"v_min_{s}{a}"].to_numpy(float) if f"v_min_{s}{a}" in e else np.nan)
                            for a in NIVELES for s in ("lo", "hi")}})


# ------------------------------------------------------------------------------------------ A4 (§5)
def _cuantil_ponderado(x: np.ndarray, w: np.ndarray, q: float) -> float:
    ok = np.isfinite(x) & (w > 0)
    x, w = x[ok], w[ok]
    if len(x) == 0:
        return np.nan
    nw = w.sum() ** 2 / (w ** 2).sum()
    q = min(math.ceil((nw + 1) * q) / nw, 1.0)          # corrección de muestra finita
    o = np.argsort(x)
    cw = np.cumsum(w[o]) / w.sum()
    return float(x[o][min(np.searchsorted(cw, q), len(x) - 1)])


def pesos_recencia(cortes_prev: pd.Series, corte_obj: str, cortes: list[str], rho: float) -> np.ndarray:
    """w_s = ρ^(t−1−s): el corte inmediatamente anterior pesa 1."""
    it = cortes.index(corte_obj) if corte_obj in cortes else len(cortes)
    return np.array([rho ** (it - 1 - cortes.index(s)) for s in cortes_prev], float)


def ajustar_recalibracion(pred: pd.DataFrame, y: np.ndarray, ok: np.ndarray, gd: pd.Series, go: pd.Series,
                          w: np.ndarray, c: dict) -> dict:
    """Factores de dos colas (o semiamplitudes con signo si no hay intervalo) por nivel, con contracción por grupos."""
    rc = c["v32"]["recalibracion"]
    n0, mmin = float(rc.get("n0", 30)), int(rc.get("min_casos_origen", 15))
    out = {}
    cc = pred["pred"].to_numpy(float)
    for a in NIVELES:
        lo, hi = pred[f"lo{a}"].to_numpy(float), pred[f"hi{a}"].to_numpy(float)
        sin_iv = not np.isfinite(lo[ok]).any()
        q = (1 + Q[a]) / 2
        with np.errstate(divide="ignore", invalid="ignore"):
            if sin_iv:
                rm, rp = cc - y, y - cc                        # semiamplitudes con signo
            else:
                rm, rp = (cc - y) / np.maximum(cc - lo, 1e-9), (y - cc) / np.maximum(hi - cc, 1e-9)
        v = ok & np.isfinite(rm) & np.isfinite(rp)
        if v.sum() < 10:
            out[a] = None
            continue
        g, o = gd.to_numpy(), go.to_numpy()
        d = {"tipo": "semiamplitud" if sin_iv else "escala"}
        for lado, r in (("menos", rm), ("mas", rp)):
            glob = _cuantil_ponderado(r[v], w[v], q)
            grupos, cruce = {}, {}
            for k in np.unique(g[v]):
                s = v & (g == k)
                fk = _cuantil_ponderado(r[s], w[s], q)
                fd = (s.sum() * fk + n0 * glob) / (s.sum() + n0)
                grupos[str(k)] = fd
                for oo in np.unique(o[s]):
                    so = s & (o == oo)
                    if so.sum() >= mmin:
                        fo = _cuantil_ponderado(r[so], w[so], q)
                        cruce[f"{k}|{oo}"] = (so.sum() * fo + n0 * fd) / (so.sum() + n0)
            d[lado] = {"global": glob, "grupo": grupos, "grupo_origen": cruce}
        out[a] = d
    return out


def aplicar_recalibracion(pred: pd.DataFrame, fac: dict, gd: pd.Series, go: pd.Series) -> pd.DataFrame:
    p = pred.copy()
    c_ = p["pred"].to_numpy(float)
    clave = (gd.astype(str) + "|" + go.astype(str)).to_numpy()
    for a in NIVELES:
        d = fac.get(a) if fac else None
        if not d:
            continue
        f = {}
        for lado in ("menos", "mas"):
            x = d[lado]
            f[lado] = np.array([x["grupo_origen"].get(k, x["grupo"].get(g_, x["global"]))
                                for k, g_ in zip(clave, gd.astype(str))], float)
        if d["tipo"] == "semiamplitud":
            p[f"lo{a}"], p[f"hi{a}"] = c_ - f["menos"], c_ + f["mas"]
        else:
            p[f"lo{a}"] = c_ - f["menos"] * (c_ - p[f"lo{a}"].to_numpy(float))
            p[f"hi{a}"] = c_ + f["mas"] * (p[f"hi{a}"].to_numpy(float) - c_)
    return p


def aceptacion(y, p: pd.DataFrame, ok: np.ndarray, gd: pd.Series) -> dict:
    """§5e · |Cob − α| ≤ 2√(α(1−α)/n) + 0,02, global y por grupo de destino con n ≥ 100."""
    out = {}
    for a in NIVELES:
        lo, hi = p[f"lo{a}"].to_numpy(float), p[f"hi{a}"].to_numpy(float)
        s = ok & np.isfinite(lo) & np.isfinite(y)
        if not s.any():
            continue
        al = Q[a]
        dentro = (y >= lo) & (y <= hi)
        fila = {}
        for nom, sel in [("global", s)] + [(str(k), s & (gd.to_numpy() == k)) for k in np.unique(gd)]:
            n = int(sel.sum())
            if n >= (1 if nom == "global" else 100):
                cob = float(dentro[sel].mean())
                fila[nom] = {"n": n, "cobertura": cob, "acepta": abs(cob - al) <= 2 * math.sqrt(al * (1 - al) / n) + 0.02}
        out[a] = fila
    return out


# ------------------------------------------------------------------------------------------ medidas y bootstrap
def winkler(y, lo, hi, alfa):
    return (hi - lo) + (2 / alfa) * np.maximum(lo - y, 0) + (2 / alfa) * np.maximum(y - hi, 0)


def _clubes(e: pd.DataFrame) -> np.ndarray:
    g = (e["liga_d"].astype(str) + "|" + e["team_d"].astype(str) + "|" + e["corte"].astype(str)).to_numpy()
    return pd.factorize(g)[0]


def boot_cociente(e, xa, xb, ok, B, semilla, nivel=0.9):
    """ΔR = Σxa/Σxb − 1 (pareado) con IC por remuestreo de clubes de destino × corte."""
    ok = ok & np.isfinite(xa) & np.isfinite(xb)
    cl = _clubes(e)
    nc = cl.max() + 1
    sa = np.bincount(cl[ok], xa[ok], nc)
    sb = np.bincount(cl[ok], xb[ok], nc)
    d0 = float(sa.sum() / sb.sum() - 1)
    rng = np.random.default_rng(semilla)
    bs = np.empty(B)
    for i in range(B):
        w = np.bincount(rng.integers(0, nc, nc), minlength=nc)
        bs[i] = (w @ sa) / (w @ sb) - 1
    a = (1 - nivel) / 2
    lo, hi = np.quantile(bs, [a, 1 - a])
    return d0, float(lo), float(hi)


def boot_diferencia(e, xa, xb, ok, B, semilla, nivel=0.9):
    ok = ok & np.isfinite(xa) & np.isfinite(xb)
    cl = _clubes(e)
    nc = cl.max() + 1
    sd = np.bincount(cl[ok], xa[ok] - xb[ok], nc)
    n = np.bincount(cl[ok], minlength=nc).astype(float)
    d0 = float(sd.sum() / n.sum())
    rng = np.random.default_rng(semilla)
    bs = np.empty(B)
    for i in range(B):
        w = np.bincount(rng.integers(0, nc, nc), minlength=nc)
        bs[i] = (w @ sd) / max(w @ n, 1)
    a = (1 - nivel) / 2
    lo, hi = np.quantile(bs, [a, 1 - a])
    return d0, float(lo), float(hi)


def _err(e, prod, m):
    y = e["C_real"].to_numpy(float) if m == "C" else e[f"{m}_real"].to_numpy(float)
    return np.abs(prod[m]["pred"].to_numpy(float) - y)


def J(e, prod, ref, pesos: dict) -> float:
    ok = ok_produccion(e)
    r = 0.0
    for m, w in pesos.items():
        a, b = _err(e, prod, m), _err(e, ref, m)
        s = ok & np.isfinite(a) & np.isfinite(b)
        r += w * a[s].mean() / b[s].mean()
    return float(r / sum(pesos.values()))


def boot_J(e, prod_a, prod_b, ref, pesos, B, semilla):
    """Diferencia J(a) − J(b) y su DT/IC 90 % bootstrap por club."""
    ok = ok_produccion(e)
    cl = _clubes(e)
    nc = cl.max() + 1
    S = {}
    for m in pesos:
        ea, eb, er = _err(e, prod_a, m), _err(e, prod_b, m), _err(e, ref, m)
        s = ok & np.isfinite(ea) & np.isfinite(eb) & np.isfinite(er)
        S[m] = (np.bincount(cl[s], ea[s], nc), np.bincount(cl[s], eb[s], nc), np.bincount(cl[s], er[s], nc))
    def jdiff(w):
        return sum(pw * ((w @ S[m][0]) - (w @ S[m][1])) / (w @ S[m][2]) for m, pw in pesos.items()) / sum(pesos.values())
    d0 = jdiff(np.ones(nc))
    rng = np.random.default_rng(semilla)
    bs = np.array([jdiff(np.bincount(rng.integers(0, nc, nc), minlength=nc)) for _ in range(B)])
    return float(d0), float(bs.std()), [float(x) for x in np.quantile(bs, [0.05, 0.95])]


# ------------------------------------------------------------------------------------------ A1 (§2)
def comparar_paso(e_var, e_base, prod_var, prod_base, c, winkler_iv=None) -> dict:
    v, mg = c["validacion"], c["v32"]["margenes"]
    B, sem = int(v["bootstrap"]), int(c["semilla"])
    clave = ["persona_id", "corte", "liga_d", "team_d"]
    j = e_base[clave].reset_index().merge(e_var[clave].reset_index().rename(columns={"index": "iv"}), on=clave)
    ib, iv = j["index"].to_numpy(), j["iv"].to_numpy()
    eb = e_base.iloc[ib].reset_index(drop=True)
    ev = e_var.iloc[iv].reset_index(drop=True)
    okp = ok_produccion(eb)
    res, peor, todo = {}, False, True

    def rel(nombre, xa, xb, ok, margen):
        nonlocal peor, todo
        d, lo, hi = boot_cociente(eb, xa, xb, ok, B, sem)
        cumple = hi < margen
        res[nombre] = {"delta": d, "ic90": [lo, hi], "margen": margen, "cumple": bool(cumple), "peor": bool(lo > 0)}
        peor |= lo > 0 and nombre in ("pts_p100", "ts_pct", "min")
        todo &= cumple

    for m in ("pts_p100", "ts_pct"):
        rel(m, _err(ev, {m: prod_var[m].iloc[iv].reset_index(drop=True)}, m),
            _err(eb, {m: prod_base[m].iloc[ib].reset_index(drop=True)}, m), okp, float(mg[m.split("_")[0]]))
    okm = eb["eval_min"].to_numpy(bool)
    rel("min", ev["v_err_min"].to_numpy(float), eb["v_err_min"].to_numpy(float), okm, float(mg["min"]))
    d, lo, hi = boot_diferencia(eb, ev["v_acierto"].to_numpy(float), eb["v_acierto"].to_numpy(float),
                                np.ones(len(eb), bool), B, sem)
    res["acierto_rol"] = {"diferencia": d, "ic90": [lo, hi], "cumple": bool(lo > -float(mg["rol_pp"])),
                          "peor": bool(hi < 0)}
    peor |= hi < 0
    todo &= lo > -float(mg["rol_pp"])
    for m in SECUNDARIAS:
        rel(m, _err(ev, {m: prod_var[m].iloc[iv].reset_index(drop=True)}, m),
            _err(eb, {m: prod_base[m].iloc[ib].reset_index(drop=True)}, m), okp, float(mg["secundarias"]))
    # segmento EuroLeague (estimación puntual)
    el = (eb["liga_d"] == "euroleague").to_numpy() & okp
    if el.sum() >= 20:
        a = _err(ev, {"pts_p100": prod_var["pts_p100"].iloc[iv].reset_index(drop=True)}, "pts_p100")[el]
        b = _err(eb, {"pts_p100": prod_base["pts_p100"].iloc[ib].reset_index(drop=True)}, "pts_p100")[el]
        dl = float(np.nanmean(a) / np.nanmean(b) - 1)
        res["pts_p100_euroleague"] = {"delta": dl, "n": int(el.sum()), "cumple": dl < float(mg["euroleague"])}
        todo &= dl < float(mg["euroleague"])
    # §6c · contribución C en P_all
    okc = okm & np.isfinite(eb["C_real"].to_numpy(float))
    rel("C", np.abs(prod_var["C"]["pred"].to_numpy(float)[iv] - ev["C_real"].to_numpy(float)),
        np.abs(prod_base["C"]["pred"].to_numpy(float)[ib] - eb["C_real"].to_numpy(float)), okc, float(mg["contribucion"]))
    if winkler_iv is not None:            # ruido personal: Winkler del 80 % con recalibración anidada
        (lo_v, hi_v), (lo_b, hi_b) = winkler_iv
        y = eb["pts_p100_real"].to_numpy(float)
        rel("winkler80_pts", winkler(y, lo_v[ib], hi_v[ib], 0.2), winkler(y, lo_b[ib], hi_b[ib], 0.2), okp,
            float(mg["winkler"]))
    res["estado"] = "quitar" if (todo and not peor) else ("conservar" if peor else "indeterminado")
    res["quitar"] = res["estado"] == "quitar"
    res["casos"] = int(len(j))
    return res


# ------------------------------------------------------------------------------------------ decisión
def _sel(e, cortes):
    return e[e["corte"].isin(cortes)].reset_index(drop=True)


def _recal_anidada(e: pd.DataFrame, prod_fn, metrica: str, c: dict):
    """Intervalos de `metrica` con A4 ajustada, para cada corte de `e`, sólo con los cortes anteriores."""
    cortes = sorted(e["corte"].unique())
    rho = float(c["v32"]["recalibracion"].get("rho", 0.5))
    lo = np.full(len(e), np.nan)
    hi = np.full(len(e), np.nan)
    p_all = prod_fn(e)[metrica]
    gd, go = grupo_destino(e["liga_o"], e["liga_d"]), grupo_origen(e["liga_o"])
    y = e[f"{metrica}_real"].to_numpy(float)
    ok = ok_produccion(e)
    for k, t in enumerate(cortes):
        st = (e["corte"] == t).to_numpy()
        if k == 0:
            lo[st], hi[st] = p_all["lo80"].to_numpy(float)[st], p_all["hi80"].to_numpy(float)[st]
            continue
        sp = e["corte"].isin(cortes[:k]).to_numpy()
        w = pesos_recencia(e.loc[sp, "corte"], t, cortes, rho)
        f = ajustar_recalibracion(p_all[sp].reset_index(drop=True), y[sp], ok[sp], gd[sp].reset_index(drop=True),
                                  go[sp].reset_index(drop=True), w, c)
        q = aplicar_recalibracion(p_all[st].reset_index(drop=True), f, gd[st].reset_index(drop=True),
                                  go[st].reset_index(drop=True))
        lo[st], hi[st] = q["lo80"].to_numpy(float), q["hi80"].to_numpy(float)
    return lo, hi


def decidir(E: dict, cortes: list[str], c: dict) -> dict:
    """A1 → A3 → A2 con los cortes `cortes` y una fuente (E: etiqueta de ejecución → predicciones)."""
    v = c["validacion"]
    B, sem = int(v["bootstrap"]), int(c["semilla"])
    ef = _sel(E["completo"], cortes)
    base = produccion(ef, "motor")
    dec = {"cortes": cortes, "pasos": {}}
    for paso in ("redistribuir_uso", "adaptacion"):
        if f"sin_{paso}" in E:
            ev = _sel(E[f"sin_{paso}"], cortes)
            dec["pasos"][paso] = comparar_paso(ev, ef, produccion(ev, "motor"), base, c)
    dec["pasos"]["uso_eficiencia"] = comparar_paso(ef, ef, produccion(ef, "motor", 0.0, 1.0), base, c)
    dec["pasos"]["companeros"] = comparar_paso(ef, ef, produccion(ef, "motor", 1.0, 0.0), base, c)
    if len(cortes) >= 2:      # ruido personal: Winkler 80 % con recalibración anidada (necesita ≥ 2 cortes)
        iv_sin = _recal_anidada(ef, lambda x: produccion(x, "motor", sin_ruido=True), "pts_p100", c)
        iv_con = _recal_anidada(ef, lambda x: produccion(x, "motor"), "pts_p100", c)
        dec["pasos"]["ruido_personal"] = comparar_paso(ef, ef, produccion(ef, "motor", sin_ruido=True), base, c,
                                                       winkler_iv=(iv_sin, iv_con))
    quitar = [p for p, x in dec["pasos"].items() if x["quitar"]]
    if "redistribuir_uso" in quitar and "adaptacion" in quitar and "sin_redistribuir_uso+sin_adaptacion" not in E:
        # sin la ejecución combinada no se publica la combinación: se quita sólo el de menor Δ_pts
        d1, d2 = (dec["pasos"][p]["pts_p100"]["delta"] for p in ("redistribuir_uso", "adaptacion"))
        quitar.remove("adaptacion" if d1 <= d2 else "redistribuir_uso")
        dec["falta_combinacion"] = True
    dec["quitar"] = quitar
    # A3 · regla de 1 error típico con parsimonia
    grid = [float(x) for x in c["produccion"]["rejilla_ajustes_ts"]]
    kbs = [0.0] if "uso_eficiencia" in quitar else grid
    kcs = [0.0] if "companeros" in quitar else grid
    pes2 = {m: 0.5 for m in c["v32"]["criterio_a3"]}
    tabla = {(kb, kc): J(ef, produccion(ef, "motor", kb, kc), base, pes2) for kb in kbs for kc in kcs}
    kstar = min(tabla, key=tabla.get)
    pk = produccion(ef, "motor", *kstar)
    adm = []
    for k_, j_ in tabla.items():
        d0, sd, _ = boot_J(ef, produccion(ef, "motor", *k_), pk, base, pes2, min(B, 500), sem)
        if d0 <= sd:
            adm.append((sum(k_), j_, k_))
    adm.sort()
    elegido, motivo = kstar, "minimo"
    for _, _, k_ in adm:           # parsimonia dentro de K₁, cumpliendo §6c (contribución C)
        pc = produccion(ef, "motor", *k_)
        okc = ef["eval_min"].to_numpy(bool) & np.isfinite(ef["C_real"].to_numpy(float))
        _, _, hi = boot_cociente(ef, _err(ef, pc, "C"), _err(ef, base, "C"), okc, min(B, 500), sem)
        if hi < float(c["v32"]["margenes"]["contribucion"]):
            elegido, motivo = k_, "parsimonia_en_K1"
            break
    dec["A3"] = {"rejilla": {f"{a}|{b}": x for (a, b), x in tabla.items()}, "k_estrella": list(kstar),
                 "K1": [list(k_) for _, _, k_ in adm], "k_beta": elegido[0], "k_comp": elegido[1], "motivo": motivo,
                 "J": tabla[elegido]}
    # A2 frente a A3 (§4)
    pw = dict(zip(c["v32"]["criterio_produccion"]["metricas"], c["v32"]["criterio_produccion"]["pesos"]))
    p3 = produccion(ef, "motor", elegido[0], elegido[1], sin_ruido="ruido_personal" in quitar)
    p2 = produccion(ef, "atlas")
    d0, sd, ic = boot_J(ef, p2, p3, base, pw, B, sem)
    okp = ok_produccion(ef)
    el = (ef["liga_d"] == "euroleague").to_numpy() & okp
    del_el = float(np.nanmean(_err(ef, p2, "pts_p100")[el]) / np.nanmean(_err(ef, p3, "pts_p100")[el]) - 1) \
        if el.sum() >= 20 else np.nan
    okc = ef["eval_min"].to_numpy(bool) & np.isfinite(ef["C_real"].to_numpy(float))
    _, _, hic = boot_cociente(ef, _err(ef, p2, "C"), _err(ef, base, "C"), okc, min(B, 500), sem)
    a2 = ic[1] < 0 and (not np.isfinite(del_el) or del_el < float(c["v32"]["margenes"]["euroleague"])) \
        and hic < float(c["v32"]["margenes"]["contribucion"])
    dec["A2"] = {"J_omega_A2_menos_A3": d0, "sd": sd, "ic90": ic, "delta_pts_euroleague": del_el,
                 "C_ic90_sup": hic, "elegida": bool(a2)}
    dec["produccion"] = "atlas" if a2 else "motor"
    return dec


def resumen_decision(d: dict) -> tuple:
    return (tuple(sorted(d["quitar"])), d["A3"]["k_beta"], d["A3"]["k_comp"], d["produccion"])


def decidir_dos_fuentes(EE: dict, cortes: list[str], c: dict) -> dict:
    """§1c · las decisiones relativas se calculan con las dos fuentes; si no coinciden, manda V32_corte."""
    ds = {f: decidir(EE[f], cortes, c) for f in FUENTES if f in EE}
    final = ds.get("V32_corte") or ds.get("V32")
    out = dict(final)
    out["por_fuente"] = {f: {"quitar": d["quitar"], "k": [d["A3"]["k_beta"], d["A3"]["k_comp"]],
                             "produccion": d["produccion"]} for f, d in ds.items()}
    out["coinciden"] = len({resumen_decision(d) for d in ds.values()}) == 1
    out["fuente_que_decide"] = "las dos (coinciden)" if out["coinciden"] else "V32_corte"
    return out


# ------------------------------------------------------------------------------------------ aplicar y medir
def aplicar(e: pd.DataFrame, E: dict, dec: dict | None, prev: pd.DataFrame | None, c: dict, corte_obj: str,
            cortes: list[str]) -> dict:
    if dec is None:
        prod, mins, src = produccion(e, "motor"), minutos(e), e
    else:
        quitar = dec["quitar"]
        src = e
        clave = "+".join(f"sin_{p}" for p in ("redistribuir_uso", "adaptacion") if p in quitar)
        if clave and clave in E:
            x = E[clave]
            src = x[x["corte"].isin(e["corte"].unique())].reset_index(drop=True)
        prod = produccion(src, dec["produccion"], dec["A3"]["k_beta"], dec["A3"]["k_comp"],
                          sin_ruido="ruido_personal" in quitar)
        mins = minutos(src)
    out = {"e": src, "prod": prod, "min": mins}
    if dec is not None and prev is not None and len(prev):
        pp = aplicar(prev, E, dec, None, c, corte_obj, cortes)
        w = pesos_recencia(pp["e"]["corte"], corte_obj, cortes, float(c["v32"]["recalibracion"].get("rho", 0.5)))
        gdp, gop = grupo_destino(pp["e"]["liga_o"], pp["e"]["liga_d"]), grupo_origen(pp["e"]["liga_o"])
        gd, go = grupo_destino(src["liga_o"], src["liga_d"]), grupo_origen(src["liga_o"])
        okp = ok_produccion(pp["e"])
        fac = {}
        for m, p in pp["prod"].items():
            yy = pp["e"]["C_real"].to_numpy(float) if m == "C" else pp["e"][f"{m}_real"].to_numpy(float)
            okm = pp["e"]["eval_min"].to_numpy(bool) if m == "C" else okp
            fac[m] = ajustar_recalibracion(p, yy, okm, gdp, gop, w, c)
            out["prod"][m] = aplicar_recalibracion(out["prod"][m], fac[m], gd, go)
        fac["min"] = ajustar_recalibracion(pp["min"], pp["e"]["min_real"].to_numpy(float),
                                           pp["e"]["eval_min"].to_numpy(bool), gdp, gop, w, c)
        out["min"] = aplicar_recalibracion(out["min"], fac["min"], gd, go)
        out["recalibracion"] = fac
    return out


def medidas(r: dict, c: dict, constantes: dict | None = None) -> dict:
    e = r["e"]
    ok = ok_produccion(e)
    gd = grupo_destino(e["liga_o"], e["liga_d"])
    em = e["eval_min"].to_numpy(bool)
    d = {"n": int(len(e)), "n_300": int(ok.sum()),
         "mae_min": float(np.nanmean(np.abs(r["min"]["pred"] - e["min_real"]).to_numpy()[em])),
         "acierto_rol": float(e["v_acierto"].mean())}
    y = e["min_real"].to_numpy(float)
    d["aceptacion_min"] = aceptacion(y, r["min"], em, gd)
    for a in NIVELES:
        lo, hi = r["min"][f"lo{a}"].to_numpy(float), r["min"][f"hi{a}"].to_numpy(float)
        if np.isfinite(lo[em]).any():
            d[f"cob{a}_min"] = float(((y >= lo) & (y <= hi))[em].mean())
    for m, p in r["prod"].items():
        yv = e["C_real"].to_numpy(float) if m == "C" else e[f"{m}_real"].to_numpy(float)
        s = (em if m == "C" else ok) & np.isfinite(yv) & np.isfinite(p["pred"].to_numpy(float))
        d[f"mae_{m}"] = float(np.abs(p["pred"] - yv)[s].mean())
        if m == "C":
            d["sesgo_C"] = float((p["pred"] - yv)[s].mean())
        for a in NIVELES:
            lo, hi = p[f"lo{a}"].to_numpy(float), p[f"hi{a}"].to_numpy(float)
            if np.isfinite(lo[s]).any():
                d[f"cob{a}_{m}"] = float(((yv >= lo) & (yv <= hi))[s].mean())
                d[f"winkler{a}_{m}"] = float(winkler(yv, lo, hi, 1 - Q[a])[s].mean())
        if m in ("pts_p100", "ts_pct"):
            d[f"aceptacion_{m}"] = aceptacion(yv, p, ok, gd)
    d["banda_50_300"] = banda_50_300(r, c, constantes)
    d["decision"] = metricas_decision(r)
    return d


def banda_50_300(r: dict, c: dict, constantes: dict | None) -> dict:
    """§6a · fichajes con 50-300 min: error tipificado con la varianza predictiva del valor OBSERVADO
    (Var_pred + σ²_m/n_i en la escala de trabajo). n_i ≈ posesiones (1,8 por minuto) o tiros (posesiones · USG)."""
    from bbmodel.metricas import transformar
    e = r["e"]
    mt = pd.to_numeric(e["min_total_real"], errors="coerce").to_numpy(float)
    s = (mt >= 50) & (mt < 300)
    out = {"n": int(s.sum())}
    if not s.any() or not constantes:
        return out
    for m in ("pts_p100", "ts_pct"):
        k = constantes.get(m)
        if k is None:
            continue
        p = r["prod"][m]
        y, yh = e[f"{m}_real"].to_numpy(float), p["pred"].to_numpy(float)
        lo, hi = p["lo80"].to_numpy(float), p["hi80"].to_numpy(float)
        Ty, Th = transformar(y, k["transf"]), transformar(yh, k["transf"])
        vp = ((transformar(hi, k["transf"]) - transformar(lo, k["transf"])) / (2 * 1.2816)) ** 2
        poss = 1.8 * mt
        n_i = poss * (np.clip(e["v_usg_pct_pred"].to_numpy(float), 5, 45) / 100 if k["exposicion"] in ("tsa", "fga")
                      else 1.0)
        s2 = np.array([k["sigma2"].get(l, k["sigma2"].get("todas", np.nan)) for l in e["liga_d"]], float)
        z = (Ty - Th) / np.sqrt(vp + s2 / np.maximum(n_i, 1))
        ok = s & np.isfinite(z)
        cob = np.abs(z[ok]) <= 1.2816
        out[m] = {"n": int(ok.sum()), "z_media": float(z[ok].mean()), "z_dt": float(z[ok].std()),
                  "cob80_predictiva_observada": float(cob.mean())}
    return out


def metricas_decision(r: dict) -> dict:
    """§7 · orden de candidatos (Spearman por liga de destino × corte con ≥ 10 fichajes), decil superior y Brier de
    P(C ≥ p75 de la liga de destino)."""
    from scipy.stats import spearmanr
    e = r["e"]
    em = e["eval_min"].to_numpy(bool)
    C, Ch = e["C_real"].to_numpy(float), r["prod"]["C"]["pred"].to_numpy(float)
    filas, top = [], []
    for (l, t), g in e[em].groupby(["liga_d", "corte"]):
        ix = g.index.to_numpy()
        ix = ix[np.isfinite(Ch[ix]) & np.isfinite(C[ix])]
        if len(ix) >= 10:
            rho = spearmanr(Ch[ix], C[ix]).statistic
            if np.isfinite(rho):              # un grupo con C constante (todos 0) no ordena nada
                filas.append((len(ix), rho, l, t))
            q = np.quantile(Ch[ix], 0.9)
            sel = ix[Ch[ix] >= q]
            top.append(np.c_[Ch[sel] - C[sel]])
    out = {}
    if filas:
        n = np.array([f[0] for f in filas], float)
        rho = np.array([f[1] for f in filas], float)
        rng = np.random.default_rng(0)
        bs = [np.average(rho[i], weights=n[i]) for i in (rng.integers(0, len(n), len(n)) for _ in range(1000))]
        out["spearman_medio"] = float(np.average(rho, weights=n))
        out["spearman_ic90"] = [float(x) for x in np.quantile(bs, [0.05, 0.95])]
        out["pools"] = len(filas)
        T = np.concatenate(top)[:, 0]
        out["decil_superior"] = {"n": int(len(T)), "mae": float(np.abs(T).mean()), "sesgo": float(T.mean())}
    if "v_C_p_top25" in e:
        p = pd.to_numeric(e["v_C_p_top25"], errors="coerce").to_numpy(float)
        c75 = pd.to_numeric(e["v_C_c75"], errors="coerce").to_numpy(float)
        ok = em & np.isfinite(p) & np.isfinite(c75)
        yb = (C >= c75).astype(float)
        out["brier"] = float(((p - yb) ** 2)[ok].mean())
        out["base_brier"] = float(((yb[ok].mean() - yb) ** 2)[ok].mean())
        dec = pd.qcut(pd.Series(p[ok]).rank(method="first"), 10, labels=False)
        out["fiabilidad"] = [{"p_media": float(p[ok][dec == k].mean()), "frecuencia": float(yb[ok][dec == k].mean())}
                             for k in range(10)]
    return out


def cargar_ejecuciones(c: dict) -> dict:
    _, esc, ad = V.ruta_produccion(c)
    EE = {}
    for f in FUENTES:
        etq = V._etiqueta(f, esc, ad)
        p = V.DIR_VAL / etq / "predicciones.csv.gz"
        if not p.exists():
            continue
        E = {"completo": pd.read_csv(p, low_memory=False)}
        for var in c["v32"]["variantes_motor"] + ["sin_redistribuir_uso+sin_adaptacion"]:
            q = V.DIR_VAL / f"{etq}_{var}" / "predicciones.csv.gz"
            if q.exists():
                E[var] = pd.read_csv(q, low_memory=False)
        for k in list(E):
            E[k] = E[k][E[k]["error"].isna()].reset_index(drop=True) if "error" in E[k] else E[k]
        EE[f] = E
    return EE


def main(progreso=print) -> dict:
    from . import sim_insumos as SI
    c = cfg()
    EE = cargar_ejecuciones(c)
    if "V32_corte" not in EE and progreso:
        progreso("  (falta la ejecución sin fuga V32_corte: las cifras absolutas no son publicables)")
    fabs = "V32_corte" if "V32_corte" in EE else "V32"
    E = EE[fabs]
    try:
        const = SI.traduccion("V32", SI.metricas_traduccion(c))["constantes"]
    except Exception:  # noqa: BLE001
        const = None
    cortes = sorted(E["completo"]["corte"].unique())
    informe = {"fuente_cifras_absolutas": fabs, "fuentes": list(EE), "cortes": cortes, "anidado": {}, "examen": {},
               "criterios": "docs/simulador_v32.md §2 (criterios matemáticos del 02-11-2026)"}
    f32, f31 = [], []
    for k, t in enumerate(cortes):
        e_t = E["completo"][E["completo"]["corte"] == t].reset_index(drop=True)
        prev_c = cortes[:k]
        dec = decidir_dos_fuentes(EE, prev_c, c) if prev_c else None
        prev = E["completo"][E["completo"]["corte"].isin(prev_c)].reset_index(drop=True) if prev_c else None
        informe["anidado"][t] = {"decision_con": prev_c, "decision": dec}
        r32 = aplicar(e_t, E, dec, prev, c, t, cortes)
        r31 = aplicar(e_t, E, None, None, c, t, cortes)
        informe["examen"][t] = {"v3.2": medidas(r32, c, const), "v3.1_motor": medidas(r31, c, const)}
        f32.append(r32), f31.append(r31)
        if progreso:
            progreso(f"  corte {t}: decisión con {prev_c or 'ninguno (motor v3.1)'}"
                     + ("" if dec is None else f" → quitar {dec['quitar']}, k = ({dec['A3']['k_beta']}, "
                                               f"{dec['A3']['k_comp']}), producción {dec['produccion']}"), flush=True)

    def unir(fs):
        e = pd.concat([f["e"] for f in fs], ignore_index=True)
        return {"e": e, "prod": {m: pd.concat([f["prod"][m] for f in fs], ignore_index=True) for m in fs[0]["prod"]},
                "min": pd.concat([f["min"] for f in fs], ignore_index=True)}
    informe["examen"]["total"] = {"v3.2": medidas(unir(f32), c, const), "v3.1_motor": medidas(unir(f31), c, const)}
    final = decidir_dos_fuentes(EE, cortes, c)
    informe["final"] = final
    rf = aplicar(E["completo"], E, final, E["completo"], c, "final", cortes + ["final"])
    informe["recalibracion_final"] = rf.get("recalibracion")
    d = V.DIR_VAL.parent
    (d / "decisiones_v32.json").write_text(json.dumps(informe, indent=1, ensure_ascii=False, default=float),
                                           encoding="utf-8")
    if progreso:
        tot = informe["examen"]["total"]
        progreso(json.dumps({"final": {k: final[k] for k in ("quitar", "produccion", "coinciden")}, "A3": final["A3"],
                             "v3.2": {k: v for k, v in tot["v3.2"].items() if k.startswith(("mae", "cob"))},
                             "v3.1": {k: v for k, v in tot["v3.1_motor"].items() if k.startswith(("mae", "cob"))}},
                            indent=1, default=float), flush=True)
    return informe


def aplicar_config(ruta=None, progreso=print) -> dict:
    """Escribe en configs/simulation_v32.yaml las decisiones FINALES (decisiones_v32.json): pasos quitados, factores
    (k_β, k_c), producción publicada y recalibración A4 activa. Sólo para el simulador publicado (histórico y
    exportación): el examen ya está hecho."""
    import re
    from .config import DIR_CONFIGS
    ruta = ruta or DIR_CONFIGS / "simulation_v32.yaml"
    d = json.loads((V.DIR_VAL.parent / "decisiones_v32.json").read_text(encoding="utf-8"))["final"]
    t = ruta.read_text(encoding="utf-8")
    for paso in ("redistribuir_uso", "uso_eficiencia", "companeros", "adaptacion", "ruido_personal"):
        t = re.sub(rf"^(  {paso}: )(true|false)", rf"\g<1>{'false' if paso in d['quitar'] else 'true'}", t, flags=re.M)
    t = re.sub(r"^(  factor_ajustes_ts: )\[[^\]]*\]", rf"\g<1>[{d['A3']['k_beta']}, {d['A3']['k_comp']}]", t,
               flags=re.M)
    t = re.sub(r"^(  produccion_publicada: )\w+", rf"\g<1>{d['produccion']}", t, flags=re.M)
    t = re.sub(r"^(  aplicar_recalibracion: )\w+", r"\g<1>true", t, flags=re.M)
    ruta.write_text(t, encoding="utf-8")
    out = {"quitar": d["quitar"], "k": [d["A3"]["k_beta"], d["A3"]["k_comp"]], "produccion": d["produccion"]}
    if progreso:
        progreso(f"  simulador v3.2 publicado: {out}", flush=True)
    return out
