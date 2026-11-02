"""Simulador v3.2 · decisiones A1-A4 con cortes anidados sobre el examen temporal (bbfit/validacion.py).

Entradas (data/modelos/simulador/v3_2/validacion/<etiqueta>/predicciones.csv.gz):
  * la ejecución completa del motor (V32_inicio_adapt), que guarda además la rejilla A3 de factores (k_β, k_c) sobre
    las mismas simulaciones (columnas v_g<kβ>_<kc>_<m>_*) y la producción sin ruido personal (v_<m>_motor_*);
  * las ejecuciones con un paso apagado (CERNO_SIM_VARIANTE=sin_<paso>, con los pesos de la completa).

Decisiones (fijadas de antemano por el usuario el 02-11-2026; configs/simulation_v32.yaml → v32):
  A1  regla de la navaja por paso: se QUITA si quitarlo no empeora de forma significativa (IC 90 % bootstrap por club
      de destino, pareado) el error de pts/100 ni el de TS%, ni el error de minutos ni el acierto de rol. El paso
      «ruido personal» sólo forma los intervalos: además se exige que no empeore la puntuación de intervalo del 90 %
      (Winkler) tras la recalibración A4. «Curva uso-eficiencia» y «compañeros» = factores k_β = 0 y k_c = 0 de A3.
  A3  factores (k_β, k_c) de la rejilla, para los pasos que A1 conserva: mínimo del criterio de producción.
  A2  producción del Atlas (la de la línea base «a»: producción normalizada + contexto, traducida con el tipo de
      cambio lineal) con los minutos y el rol del motor. Se elige A2 o A3 por el criterio de producción:
      media de MAE_pts/MAE_pts(v3.1) y MAE_TS/MAE_TS(v3.1) (menor = mejor); a igualdad, el motor (A3).
  A4  recalibración conforme de los intervalos del 50 % y del 90 % (producción y minutos): factor de escala por
      métrica × grupo de destino (a la EuroLeague, FEB, NBA/G League, resto) si el grupo tiene ≥ 30 casos en los
      cortes anteriores; si no, el de la métrica. Producción sin intervalo propio (A2): semiamplitud = cuantil del
      error absoluto de los cortes anteriores (mismo esquema de grupos).
Cortes anidados: lo que se aplica al corte t se decide con los cortes < t (el primero usa la v3.1 tal cual); la
decisión final (la que usa el simulador publicado) se toma con todos los cortes.

    CERNO_SIMULADOR=v32 python -m bbfit v32-decidir
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import validacion as V
from .config import cargar

PASOS = ["redistribuir_uso", "uso_eficiencia", "companeros", "adaptacion", "ruido_personal"]
NIVELES = ("50", "90")
Q = {"50": 0.5, "90": 0.9}


def cfg() -> dict:
    return cargar("simulation")


def grupo_destino(liga_o: pd.Series, liga_d: pd.Series) -> pd.Series:
    from bbnorm3.examen import grupo
    return grupo(liga_o.astype(str), liga_d.astype(str))


def cargar_pred(etiqueta: str) -> pd.DataFrame:
    return pd.read_csv(V.DIR_VAL / etiqueta / "predicciones.csv.gz", low_memory=False)


# ------------------------------------------------------------------------------------------ candidatos de producción
def _k(x: float) -> str:
    return repr(float(x))


def produccion(e: pd.DataFrame, metodo: str, kb: float = 1.0, kc: float = 1.0, sin_ruido: bool = False) -> dict:
    """{métrica: DataFrame(pred, lo50, hi50, lo90, hi90)} de un método de producción."""
    mets = cfg()["produccion"]["metricas"]
    out = {}
    for m in mets:
        if metodo == "atlas":
            p = e[f"a_{m}_pred"].to_numpy(float)
            out[m] = pd.DataFrame({"pred": p, **{f"{s}{a}": np.nan for a in NIVELES for s in ("lo", "hi")}})
            continue
        if m in ("pts_p100", "ts_pct") and f"v_g{_k(kb)}_{_k(kc)}_{m}_pred" in e:
            pre = f"v_g{_k(kb)}_{_k(kc)}_{m}" + ("_motor" if sin_ruido else "")
        else:
            pre = f"v_{m}" + ("_motor" if sin_ruido else "")
        out[m] = pd.DataFrame({"pred": e[f"{pre}_pred"].to_numpy(float),
                               **{f"{s}{a}": e[f"{pre}_{s}{a}"].to_numpy(float) for a in NIVELES for s in ("lo", "hi")}})
    return out


def minutos(e: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"pred": e["v_min_pred"].to_numpy(float),
                         **{f"{s}{a}": e[f"v_min_{s}{a}"].to_numpy(float) for a in NIVELES for s in ("lo", "hi")}})


def ok_produccion(e: pd.DataFrame) -> np.ndarray:
    return (e["min_total_real"] >= cfg()["validacion"]["min_minutos_produccion"]).to_numpy(bool)


# ------------------------------------------------------------------------------------------ A4 recalibración conforme
def _escala_necesaria(y, c, lo, hi):
    """Factor s que hace que [c − s(c − lo), c + s(hi − c)] contenga y."""
    with np.errstate(divide="ignore", invalid="ignore"):
        abajo = np.where(y < c, (c - y) / np.maximum(c - lo, 1e-9), 0.0)
        arriba = np.where(y > c, (y - c) / np.maximum(hi - c, 1e-9), 0.0)
    return np.maximum(abajo, arriba)


def ajustar_recalibracion(prev: pd.DataFrame, pred: pd.DataFrame, y: np.ndarray, ok: np.ndarray, grupos: pd.Series,
                          min_casos: int) -> dict:
    """Factores (o semiamplitudes si no hay intervalo) por nivel: global de la métrica y por grupo de destino."""
    out = {}
    for a in NIVELES:
        c, lo, hi = pred["pred"].to_numpy(float), pred[f"lo{a}"].to_numpy(float), pred[f"hi{a}"].to_numpy(float)
        sin_iv = not np.isfinite(lo[ok]).any()
        r = np.abs(y - c) if sin_iv else _escala_necesaria(y, c, lo, hi)
        v = ok & np.isfinite(r)
        if v.sum() < 10:
            out[a] = None
            continue
        g = grupos.to_numpy()
        d = {"tipo": "semiamplitud" if sin_iv else "escala", "global": float(np.quantile(r[v], Q[a])),
             "grupo": {}}
        for k in np.unique(g[v]):
            s = v & (g == k)
            if s.sum() >= min_casos:
                d["grupo"][str(k)] = float(np.quantile(r[s], Q[a]))
        out[a] = d
    return out


def aplicar_recalibracion(pred: pd.DataFrame, fac: dict, grupos: pd.Series) -> pd.DataFrame:
    p = pred.copy()
    for a in NIVELES:
        d = fac.get(a) if fac else None
        if not d:
            continue
        f = grupos.map(d["grupo"]).fillna(d["global"]).to_numpy(float)
        c = p["pred"].to_numpy(float)
        if d["tipo"] == "semiamplitud":
            p[f"lo{a}"], p[f"hi{a}"] = c - f, c + f
        else:
            p[f"lo{a}"] = c - f * (c - p[f"lo{a}"].to_numpy(float))
            p[f"hi{a}"] = c + f * (p[f"hi{a}"].to_numpy(float) - c)
    return p


# ------------------------------------------------------------------------------------------ medidas
def winkler(y, lo, hi, alfa):
    return (hi - lo) + (2 / alfa) * np.maximum(lo - y, 0) + (2 / alfa) * np.maximum(y - hi, 0)


def _clubes(e: pd.DataFrame) -> list[np.ndarray]:
    g = (e["liga_d"].astype(str) + "|" + e["team_d"].astype(str) + "|" + e["corte"].astype(str)).to_numpy()
    return [np.asarray(ix) for ix in pd.Series(np.arange(len(e))).groupby(g).apply(list).tolist()]


def boot_diferencia(e: pd.DataFrame, x_var: np.ndarray, x_base: np.ndarray, ok: np.ndarray, B: int, semilla: int):
    """(media de x_var − media de x_base, IC 90 %) remuestreando clubes de destino (pareado)."""
    grupos = _clubes(e)
    ok = ok & np.isfinite(x_var) & np.isfinite(x_base)
    d0 = float(x_var[ok].mean() - x_base[ok].mean())
    rng = np.random.default_rng(semilla)
    bs = np.empty(B)
    for i in range(B):
        idx = np.concatenate([grupos[k] for k in rng.integers(0, len(grupos), len(grupos))])
        idx = idx[ok[idx]]
        bs[i] = x_var[idx].mean() - x_base[idx].mean()
    lo, hi = np.quantile(bs, [0.05, 0.95])
    return d0, float(lo), float(hi)


def criterio(e: pd.DataFrame, prod: dict, ref: dict) -> float:
    """Media de MAE_m / MAE_m(ref) en las métricas del criterio (pts/100 y TS%)."""
    ok = ok_produccion(e)
    r = []
    for m in cfg()["v32"]["criterio_produccion"]:
        y = e[f"{m}_real"].to_numpy(float)
        a = np.abs(prod[m]["pred"].to_numpy(float) - y)
        b = np.abs(ref[m]["pred"].to_numpy(float) - y)
        s = ok & np.isfinite(a) & np.isfinite(b)
        r.append(a[s].mean() / b[s].mean())
    return float(np.mean(r))


# ------------------------------------------------------------------------------------------ A1
def comparar_paso(e_var: pd.DataFrame, e_base: pd.DataFrame, prod_var: dict, prod_base: dict, c: dict,
                  intervalos: tuple | None = None) -> dict:
    """Navaja: ¿quitar el paso empeora significativamente pts/100, TS%, minutos o acierto de rol? (IC 90 % por club)."""
    v = c["validacion"]
    B, sem = int(v["bootstrap"]), int(c["semilla"])
    clave = ["persona_id", "corte", "liga_d", "team_d"]
    j = e_base[clave].reset_index().merge(e_var[clave].reset_index().rename(columns={"index": "iv"}), on=clave)
    ib, iv = j["index"].to_numpy(), j["iv"].to_numpy()
    eb = e_base.iloc[ib].reset_index(drop=True)
    res, peor = {}, False
    okp = ok_produccion(eb)
    for m in c["v32"]["criterio_produccion"]:
        y = eb[f"{m}_real"].to_numpy(float)
        xa = np.abs(prod_var[m]["pred"].to_numpy(float)[iv] - y)
        xb = np.abs(prod_base[m]["pred"].to_numpy(float)[ib] - y)
        d, lo, hi = boot_diferencia(eb, xa, xb, okp, B, sem)
        res[f"mae_{m}"] = {"diferencia": d, "ic90": [lo, hi], "peor": lo > 0}
        peor |= lo > 0
    okm = eb["eval_min"].to_numpy(bool)
    for nombre, col, signo in (("mae_min", "v_err_min", 1), ("acierto_rol", "v_acierto", -1)):
        xa = e_var[col].to_numpy(float)[iv]
        xb = e_base[col].to_numpy(float)[ib]
        d, lo, hi = boot_diferencia(eb, xa, xb, okm if nombre == "mae_min" else np.isfinite(xa), B, sem)
        p = (lo > 0) if signo > 0 else (hi < 0)
        res[nombre] = {"diferencia": d, "ic90": [lo, hi], "peor": bool(p)}
        peor |= p
    if intervalos is not None:          # paso que sólo forma intervalos: puntuación de Winkler del 90 % tras A4
        (lo_v, hi_v), (lo_b, hi_b), m = intervalos
        y = eb[f"{m}_real"].to_numpy(float)
        xa, xb = winkler(y, lo_v[iv], hi_v[iv], 0.1), winkler(y, lo_b[ib], hi_b[ib], 0.1)
        d, lo, hi = boot_diferencia(eb, xa, xb, okp, B, sem)
        res[f"winkler90_{m}"] = {"diferencia": d, "ic90": [lo, hi], "peor": lo > 0}
        peor |= lo > 0
    res["quitar"] = not peor
    res["casos"] = int(len(j))
    return res


# ------------------------------------------------------------------------------------------ decisión con unos cortes
def decidir(E: dict[str, pd.DataFrame], cortes: list[str], c: dict) -> dict:
    """Decisiones A1 → A3 → A2 con los cortes `cortes` (E: etiqueta de ejecución → predicciones)."""
    full = E["completo"]
    sel = lambda e: e[e["corte"].isin(cortes)].reset_index(drop=True)  # noqa: E731
    ef = sel(full)
    base = produccion(ef, "motor")
    dec = {"cortes": cortes, "pasos": {}}
    # A1 · pasos con ejecución propia
    for paso in ("redistribuir_uso", "adaptacion"):
        k = f"sin_{paso}"
        if k in E:
            ev = sel(E[k])
            dec["pasos"][paso] = comparar_paso(ev, ef, produccion(ev, "motor"), base, c)
    # A1 · curva uso-eficiencia y compañeros = factor 0 de la rejilla (mismas simulaciones)
    dec["pasos"]["uso_eficiencia"] = comparar_paso(ef, ef, produccion(ef, "motor", 0.0, 1.0), base, c)
    dec["pasos"]["companeros"] = comparar_paso(ef, ef, produccion(ef, "motor", 1.0, 0.0), base, c)
    # A1 · ruido personal: intervalos sin él frente a con él, los dos recalibrados (A4) dentro de estos cortes
    m = c["produccion"]["principal"]
    g = grupo_destino(ef["liga_o"], ef["liga_d"])
    y, ok = ef[f"{m}_real"].to_numpy(float), ok_produccion(ef)
    iv = []
    for sr in (True, False):
        p = produccion(ef, "motor", sin_ruido=sr)[m]
        f = ajustar_recalibracion(None, p, y, ok, g, int(c["v32"]["recalibracion"]["min_casos_grupo"]))
        p = aplicar_recalibracion(p, f, g)
        iv.append((p["lo90"].to_numpy(float), p["hi90"].to_numpy(float)))
    dec["pasos"]["ruido_personal"] = comparar_paso(ef, ef, produccion(ef, "motor", sin_ruido=True), base, c,
                                                   intervalos=(iv[0], iv[1], m))
    quitar = [p for p, x in dec["pasos"].items() if x["quitar"]]
    dec["quitar"] = quitar
    # A3 · factores para los pasos conservados (los quitados quedan a 0)
    grid = [float(x) for x in c["produccion"]["rejilla_ajustes_ts"]]
    kbs = [0.0] if "uso_eficiencia" in quitar else grid
    kcs = [0.0] if "companeros" in quitar else grid
    tabla = {f"{kb}|{kc}": criterio(ef, produccion(ef, "motor", kb, kc), base) for kb in kbs for kc in kcs}
    mejor = min(tabla, key=lambda k: (round(tabla[k], 6), -sum(map(float, k.split("|")))))
    dec["A3"] = {"rejilla": tabla, "k_beta": float(mejor.split("|")[0]), "k_comp": float(mejor.split("|")[1]),
                 "criterio": tabla[mejor]}
    # A2 frente a A3
    crit_a2 = criterio(ef, produccion(ef, "atlas"), base)
    dec["A2"] = {"criterio": crit_a2}
    dec["produccion"] = "atlas" if crit_a2 < dec["A3"]["criterio"] else "motor"
    return dec


# ------------------------------------------------------------------------------------------ examen anidado
def aplicar(e: pd.DataFrame, E: dict, dec: dict | None, prev: pd.DataFrame | None, c: dict) -> dict:
    """Producción y minutos del corte con las decisiones `dec` (None = v3.1) y la recalibración A4 con `prev`."""
    if dec is None:
        prod, mins = produccion(e, "motor"), minutos(e)
        variante = "v3.1"
    else:
        # un paso con ejecución propia que se quita: se usan las predicciones de esa ejecución (si se quita más de
        # uno, la del primero: el examen no tiene la combinación; se informa como limitación)
        src = e
        for paso in ("redistribuir_uso", "adaptacion"):
            if paso in dec["quitar"] and f"sin_{paso}" in E:
                x = E[f"sin_{paso}"]
                src = x[x["corte"].isin(e["corte"].unique())].reset_index(drop=True)
                break
        sr = "ruido_personal" in dec["quitar"]
        prod = produccion(src, dec["produccion"], dec["A3"]["k_beta"], dec["A3"]["k_comp"], sin_ruido=sr)
        mins = minutos(src)
        e = src
        variante = "v3.2"
    out = {"e": e, "prod": prod, "min": mins, "variante": variante}
    if dec is not None and prev is not None and len(prev):
        # A4 con los cortes anteriores, con el MISMO método aplicado a ellos
        pp = aplicar(prev, E, dec, None, c)
        gp = grupo_destino(pp["e"]["liga_o"], pp["e"]["liga_d"])
        g = grupo_destino(e["liga_o"], e["liga_d"])
        mc = int(c["v32"]["recalibracion"]["min_casos_grupo"])
        fac = {}
        okp = ok_produccion(pp["e"])
        for m, p in pp["prod"].items():
            fac[m] = ajustar_recalibracion(None, p, pp["e"][f"{m}_real"].to_numpy(float), okp, gp, mc)
            out["prod"][m] = aplicar_recalibracion(out["prod"][m], fac[m], g)
        fac["min"] = ajustar_recalibracion(None, pp["min"], pp["e"]["min_real"].to_numpy(float),
                                           pp["e"]["eval_min"].to_numpy(bool), gp, mc)
        out["min"] = aplicar_recalibracion(out["min"], fac["min"], g)
        out["recalibracion"] = fac
    return out


def medidas(r: dict, c: dict) -> dict:
    e = r["e"]
    ok = ok_produccion(e)
    d = {"n": int(len(e)), "mae_min": float(np.nanmean(np.abs(r["min"]["pred"] - e["min_real"])[e["eval_min"]])),
         "acierto_rol": float(e["v_acierto"].mean())}
    for a in NIVELES:
        y = e["min_real"].to_numpy(float)
        s = e["eval_min"].to_numpy(bool)
        d[f"cob{a}_min"] = float(((y >= r["min"][f"lo{a}"]) & (y <= r["min"][f"hi{a}"]))[s].mean())
    for m, p in r["prod"].items():
        y = e[f"{m}_real"].to_numpy(float)
        s = ok & np.isfinite(y) & np.isfinite(p["pred"].to_numpy(float))
        d[f"mae_{m}"] = float(np.abs(p["pred"] - y)[s].mean())
        for a in NIVELES:
            lo, hi = p[f"lo{a}"].to_numpy(float), p[f"hi{a}"].to_numpy(float)
            if np.isfinite(lo[s]).any():
                d[f"cob{a}_{m}"] = float(((y >= lo) & (y <= hi))[s].mean())
                d[f"winkler{a}_{m}"] = float(winkler(y, lo, hi, 1 - Q[a])[s].mean())
    return d


def main(progreso=print) -> dict:
    c = cfg()
    fuente, esc, ad = V.ruta_produccion(c)
    etq = V._etiqueta(fuente, esc, ad)
    E = {"completo": cargar_pred(etq)}
    for var in c["v32"]["variantes_motor"]:
        f = V.DIR_VAL / f"{etq}_{var}" / "predicciones.csv.gz"
        if f.exists():
            E[var] = pd.read_csv(f, low_memory=False)
        elif progreso:
            progreso(f"  (falta la ejecución {etq}_{var}: el paso se evalúa sólo si existe)")
    cortes = sorted(E["completo"]["corte"].unique())
    informe = {"etiqueta": etq, "cortes": cortes, "anidado": {}, "examen": {}}
    filas_v32, filas_v31 = [], []
    for k, t in enumerate(cortes):
        e_t = E["completo"][E["completo"]["corte"] == t].reset_index(drop=True)
        prev_c = cortes[:k]
        dec = decidir(E, prev_c, c) if prev_c else None
        prev = E["completo"][E["completo"]["corte"].isin(prev_c)].reset_index(drop=True) if prev_c else None
        informe["anidado"][t] = {"decision_con": prev_c, "decision": dec}
        r32 = aplicar(e_t, E, dec, prev, c)
        r31 = aplicar(e_t, E, None, None, c)
        informe["examen"][t] = {"v3.2": medidas(r32, c), "v3.1": medidas(r31, c)}
        filas_v32.append(r32), filas_v31.append(r31)
        if progreso:
            progreso(f"  corte {t}: decisión con {prev_c or 'ninguno (v3.1)'} → "
                     f"{'' if dec is None else ('quitar ' + str(dec['quitar']) + ', producción ' + dec['produccion'] + ', k ' + str((dec['A3']['k_beta'], dec['A3']['k_comp'])))}")
    # total del examen anidado (unión de cortes)
    def unir(fs):
        e = pd.concat([f["e"] for f in fs], ignore_index=True)
        prod = {m: pd.concat([f["prod"][m] for f in fs], ignore_index=True) for m in fs[0]["prod"]}
        return {"e": e, "prod": prod, "min": pd.concat([f["min"] for f in fs], ignore_index=True)}
    informe["examen"]["total"] = {"v3.2": medidas(unir(filas_v32), c), "v3.1": medidas(unir(filas_v31), c)}
    # decisión final (todos los cortes) y recalibración final para el simulador publicado
    final = decidir(E, cortes, c)
    informe["final"] = final
    rf = aplicar(E["completo"], E, final, E["completo"], c)
    informe["recalibracion_final"] = rf.get("recalibracion")
    d = V.DIR_VAL.parent
    (d / "decisiones_v32.json").write_text(json.dumps(informe, indent=1, ensure_ascii=False, default=float),
                                           encoding="utf-8")
    if progreso:
        progreso(json.dumps({"final": {k: final[k] for k in ("quitar", "produccion")}, "A3": final["A3"],
                             "total": informe["examen"]["total"]}, indent=1, default=float))
    return informe
