"""Fase 8 — validación del simulador v2: examen temporal sin fuga, baselines, bootstrap y dejar fuera una liga.

Para cada fichaje real t → t+1 se simula con insumos de la temporada t (y modelos ajustados con ≤ t) y se compara con
lo que pasó en t+1:
  * minutos por partido jugado (MAE), rol (acierto, matriz de confusión, log-loss multiclase), producción por 100
    (RMSE/MAE en unidades de la liga de destino), cobertura de los intervalos del 50 % y del 90 %;
  * por liga de origen, grupo de nacionalidad, posición, rol y distancia de nivel; dejando fuera una liga;
  * frente a (a) la lógica del simulador anterior del Atlas (producción normalizada + proyección de contexto,
    minutos = los de origen) y (b) un modelo simple (producción normalizada + rol de origen), con intervalos bootstrap
    (pareados por fichaje) de las diferencias de métricas.

Fichaje real: persona con registro en t (≥ min minutos) que en t+1 juega en un club en el que no estaba en t (club =
liga + equipo; un equipo de t+1 cuya plantilla comparte ≥ 40 % de jugadores con un equipo de t es el mismo club, aunque
cambie de id o de liga). Destino = su registro de más minutos en un club nuevo.

Escenario de plantilla (lo que sabría un director deportivo al fichar): los compañeros del club de destino en t+1 que
ya jugaban al empezar la temporada (primer partido en el primer 20 % del calendario), con presencia 1. No se usa nada
de su rendimiento en t+1. Variante «real»: todos los que pasaron por la plantilla, con su presencia.

Pesos aprendidos (utilidad Plackett-Luce, índice Fit) en orden cronológico: el corte t usa sólo cortes < t.
Ejecución reanudable (caché por corte en experimentos/cache_simulador/), salidas en data/modelos/simulador/v2/validacion/.
"""
from __future__ import annotations

import json
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import optimize, stats

from . import sim_insumos as SI
from . import simulador as S
from .config import cargar
from .roles import ROLES, clasificar

DIR_VAL = S.DIR_SIM / "validacion"
EPS = 1e-3


def cfg_sim() -> dict:
    return cargar("simulation")


# =============================================================================================== fichajes
def mapa_clubes(roles: pd.DataFrame, t: str, t1: str, umbral: float = 0.3) -> dict:
    """(liga, team_id) de t+1 → clave de club en t (el equipo de t con el que comparte ≥ umbral de la plantilla)."""
    a = roles[(roles["temporada"] == t) & (roles["presencia"] >= 0.3)]
    b = roles[(roles["temporada"] == t1) & (roles["presencia"] >= 0.3)]
    out = {}
    pa = a.groupby(["liga", "team_id"])["persona_id"].apply(set)
    idx_p = {}
    for k, ps in pa.items():
        for p in ps:
            idx_p.setdefault(p, []).append(k)
    for k, g in b.groupby(["liga", "team_id"]):
        ps = set(g["persona_id"])
        cuenta = {}
        for p in ps:
            for kk in idx_p.get(p, []):
                cuenta[kk] = cuenta.get(kk, 0) + 1
        if cuenta:
            kk, n = max(cuenta.items(), key=lambda x: x[1])
            if n >= max(3, umbral * len(ps)):  # noqa: SIM102
                out[k] = kk
    return out


def clave_club_t(c: S.Corte, liga: str, team: str) -> str:
    return S._club_clave(c, liga, team)


def club_en_t(c: S.Corte, liga: str, team: str, club_1: str | None, mapa: dict) -> str | None:
    """Clave del club de destino en la temporada base t: mismo id en la misma liga, mismo código de club (FEB) o
    plantilla continua (equipo que cambia de id o de liga: ascensos, descensos, licencias)."""
    x = c.eq[(c.eq["liga"] == liga) & (c.eq["team_id"].astype(str) == str(team))]
    if len(x):
        return x["club"].iloc[0]
    if club_1 is not None and club_1 in set(c.eq["club"]):
        return club_1
    if (liga, team) in mapa:
        return clave_club_t(c, *mapa[(liga, team)])
    return None


def fichajes(c: S.Corte, roles: pd.DataFrame, t1: str, cfg: dict, eq1: pd.DataFrame | None = None) -> pd.DataFrame:
    """Fichajes reales t → t+1 con su resultado en t+1. Sigue en su club (no es fichaje) si alguno de sus registros de
    t+1 es del mismo club: mismo id de club (o código de club FEB) o plantilla continua (mapa_clubes)."""
    v = cfg["validacion"]
    t = c.temp
    mapa = mapa_clubes(roles, t, t1)
    r1 = roles[roles["temporada"] == t1].copy()
    if eq1 is not None and "club" in eq1:
        k1 = eq1.set_index(["liga", "team_id"])["club"]
        r1["club_1"] = [k1.get((l, tm), f"{l}|{tm}") for l, tm in zip(r1["liga"], r1["team_id"])]
    else:
        r1["club_1"] = r1["liga"] + "|" + r1["team_id"].astype(str)
    r1["club_t"] = [club_en_t(c, l, tm, k, mapa) for l, tm, k in zip(r1["liga"], r1["team_id"], r1["club_1"])]
    ori = c.reg[c.reg["principal"] & (c.reg["min_total"] >= v["min_minutos_origen"])]
    filas = []
    for pid, g in r1[r1["persona_id"].isin(ori["persona_id"])].groupby("persona_id"):
        clubs_t = c.club_de.get(pid, set())
        sigue = g["club_t"].isin(clubs_t) | g["club_1"].isin(clubs_t)
        nuevos = g[~sigue]
        # si en t+1 sigue en alguno de sus clubes de t, no es un fichaje (p. ej. otra competición del mismo club)
        if len(nuevos) < len(g):
            continue
        d = nuevos.sort_values("min_total").iloc[-1]
        filas.append(d)
    if not filas:
        return pd.DataFrame()
    f = pd.DataFrame(filas)
    o = ori.set_index("persona_id")
    f["liga_o"] = f["persona_id"].map(o["liga"])
    f["team_o"] = f["persona_id"].map(o["team_id"])
    f = f.rename(columns={"liga": "liga_d", "team_id": "team_d"})
    f["temporada_o"], f["temporada_d"] = t, t1
    return f.reset_index(drop=True)


def miembros_escenario(roles_t1: pd.DataFrame, liga: str, team: str, escenario: str, cfg: dict) -> list[tuple[str, float]]:
    g = roles_t1[(roles_t1["liga"] == liga) & (roles_t1["team_id"].astype(str) == str(team))]
    if escenario == "inicio":
        ini = g["inicio_orden"] <= np.maximum(0.2 * g["g_equipo"], 3)
        g = g[ini]
        return [(p, 1.0) for p in g["persona_id"]]
    g = g[g["presencia"] >= cfg["plantilla"]["minimo_presencia"]]
    return [(p, float(x)) for p, x in zip(g["persona_id"], g["presencia"])]


# =============================================================================================== utilidad PL
def bloques_utilidad(c_prev: S.Corte, roles: pd.DataFrame, s: str, cfg: dict) -> list[dict]:
    """Equipos de la temporada s con rasgos de la temporada s−1 (corte c_prev) y su orden real de minutos (MIN%)."""
    u = cfg["utilidad"]
    rs = roles[(roles["temporada"] == s) & (roles["presencia"] >= u["min_presencia"]) & (roles["gp"] >= 3)]
    mapa = mapa_clubes(roles, c_prev.temp, s)
    out = []
    for (liga, team), g in rs.groupby(["liga", "team_id"]):
        if len(g) < u["min_jugadores_equipo"]:
            continue
        club_t = club_en_t(c_prev, liga, team, None, mapa) or f"{liga}|nuevo"
        e = c_prev.eq[c_prev.eq["club"] == club_t]
        P = S.plantilla(c_prev, club_t, liga, [(p, 1.0) for p in g["persona_id"]])
        P = S.encajes(c_prev, P, liga, e["eu"].iloc[0] if len(e) else None)
        y = g.set_index("persona_id")["min_pct"].reindex(P["persona_id"]).to_numpy(float)
        orden = np.argsort(-y)
        X = P[S.RASGOS_UTIL].apply(pd.to_numeric, errors="coerce").fillna(0).to_numpy(float)[orden]
        out.append({"liga": liga, "team": team, "X": X, "y": y[orden], "n": len(P)})
    return out


def _nll(w, bloques, l2):
    tot, grad = 0.0, np.zeros_like(w)
    for b in bloques:
        X = b["X"]
        u = X @ w
        # log Σ_{j ≥ r} exp(u_j) acumulado desde el final
        m = np.maximum.accumulate(u[::-1])[::-1]
        e = np.exp(u - u.max())
        cs = np.cumsum(e[::-1])[::-1]
        lse = np.log(cs) + u.max()
        tot -= (u - lse).sum()
        # gradiente: x_r − Σ_{j≥r} p_j x_j
        ex = e[:, None] * X
        cx = np.cumsum(ex[::-1], axis=0)[::-1] / cs[:, None]
        grad -= (X - cx).sum(0)
        del m
    tot += l2 * (w ** 2).sum()
    grad += 2 * l2 * w
    return tot, grad


def ajustar_utilidad(bloques: list[dict], cfg: dict) -> dict:
    """Pesos de la utilidad por máxima verosimilitud Plackett-Luce del orden real de minutos (con penalización L2)."""
    w0 = np.array([cfg["utilidad"]["inicial"].get(k, 0.0) for k in S.RASGOS_UTIL], float)
    if not bloques:
        return dict(zip(S.RASGOS_UTIL, w0))
    l2 = float(cfg["utilidad"]["regularizacion"]) * sum(b["n"] for b in bloques) / 100
    r = optimize.minimize(_nll, w0, args=(bloques, l2), jac=True, method="L-BFGS-B")
    return {k: float(v) for k, v in zip(S.RASGOS_UTIL, r.x)} | {"_nll_medio": float(r.fun / sum(b["n"] for b in bloques))}


def rotacion_extra(c_prev: S.Corte, roles: pd.DataFrame, s: str) -> float:
    """Jugadores con minutos de verdad (MIN% ≥ 12,5 %) por equipo menos la rotación del entrenador (≥ 10'), en s."""
    rs = roles[(roles["temporada"] == s) & (roles["presencia"] >= 0.5) & (roles["gp"] >= 5)]
    n = rs[rs["min_pct"] >= 0.125].groupby(["liga", "team_id"]).size()
    te = c_prev.mod["tendencias"]
    lig = te[te["entrenador_id"].str.startswith("__liga__:")].set_index("liga_principal")["rotacion"]
    ex = [v - lig.get(l, np.nan) for (l, _), v in n.items()]
    ex = [x for x in ex if np.isfinite(x)]
    return float(np.median(ex)) if ex else 1.0


# =============================================================================================== simulación de un corte
def _equipo_t(c: S.Corte, club_t: str | None):
    if club_t is None:
        return None
    e = c.eq[c.eq["club"] == club_t]
    return e.iloc[0] if len(e) else None


def simular_fichajes(c: S.Corte, casos: pd.DataFrame, roles_t1: pd.DataFrame, eq_t1: pd.DataFrame, cfg: dict,
                     escenario: str = "inicio", n_sim: int | None = None, progreso=print, sin_adaptacion=False,
                     adaptacion_ruta=None) -> pd.DataFrame:
    """Simulación v2 de cada fichaje del corte; una fila por fichaje con predicciones y componentes."""
    n_sim = int(n_sim or cfg["validacion"]["simulaciones"])
    ids = SI.estilos_ids()
    filas = []
    t0 = time.time()
    for k, x in enumerate(casos.itertuples(index=False)):
        mi = miembros_escenario(roles_t1, x.liga_d, x.team_d, escenario, cfg)
        et = _equipo_t(c, x.club_t)
        e1 = eq_t1[(eq_t1["liga"] == x.liga_d) & (eq_t1["team_id"] == x.team_d)]
        ent = e1["entrenador"].iloc[0] if len(e1) and isinstance(e1["entrenador"].iloc[0], str) else None
        ritmo = float(et["team_pace"]) if et is not None and np.isfinite(S._f(et.get("team_pace"))) else None
        teu = et["eu"] if et is not None and isinstance(et.get("eu"), str) else None
        tpr = [S._f(et.get(f"eu_{i}")) for i in ids] if et is not None else None
        try:
            r = S.simular(c, x.persona_id, x.liga_d, x.team_d, mi, entrenador=ent, ritmo=ritmo, team_eu=teu,
                          team_eu_probs=tpr if tpr and np.isfinite(tpr).all() else None, n_sim=n_sim, detalle=False,
                          club_t=x.club_t or f"{x.liga_d}|nuevo", sin_adaptacion=sin_adaptacion,
                          adaptacion_ruta=adaptacion_ruta)
        except Exception as exc:  # noqa: BLE001
            r = {"error": repr(exc)}
        filas.append(_fila_pred(x, r))
        if progreso and (k + 1) % 250 == 0:
            progreso(f"    {c.temp}: {k + 1}/{len(casos)} fichajes · {time.time() - t0:.0f} s")
    return pd.DataFrame(filas)


def _fila_pred(x, r: dict) -> dict:
    f = {"persona_id": x.persona_id, "liga_o": x.liga_o, "liga_d": x.liga_d, "team_d": x.team_d}
    if "error" in r:
        f["error"] = r["error"]
        return f
    for k, v in r["roles"].items():
        f[f"p_{k}"] = v
    f["min_pred"] = r["minutos"]["mediana"]          # punto = mediana (óptima para el MAE)
    f["min_media"] = r["minutos"]["media"]
    f["p_titular"] = r["p_titular"]
    for a in ("50", "90"):
        f[f"min_lo{a}"], f[f"min_hi{a}"] = r["minutos"][f"lo{a}"], r["minutos"][f"hi{a}"]
    for m, d in r["produccion_p100"].items():
        f[f"{m}_pred"] = d["media"]
        for a in ("50", "90"):
            f[f"{m}_lo{a}"], f[f"{m}_hi{a}"] = d[f"lo{a}"], d[f"hi{a}"]
    for m, v in r["traduccion_media"].items():
        f[f"{m}_trad"] = v
    f["pts_pg_pred"] = r["por_partido"]["pts"]["media"]
    f["adapt_pct"] = r["adaptacion"]["adapt_pct_temporada"]["media"]
    f["adapt_pct_primeros"] = r["adaptacion"]["adapt_pct_primeros"]["media"]
    f["adapt_nivel"] = r["adaptacion"]["prior"].get("nivel_fallback")
    f["grupo_nac"] = r["grupo_nacionalidad"]
    f["pos3"] = r["pos3"]
    f["d_net"] = r["equipo"]["d_net"]
    f["L_o"], f["L_sd"] = r["L"], r["L_sd"]
    f["indice_rol"] = r["indice_rol"]
    for k, v in r["componentes_crudos"].items():
        f[f"c_{k}"] = v
    f["avisos"] = "|".join(a["tipo"] for a in r["avisos"])
    return f


# =============================================================================================== baselines
def _tr_lineal(c: S.Corte, valor_el, pos, liga_d, m, edad):
    """EuroLeague → liga de destino con el tipo de cambio LINEAL del A (m_l, s_l): lo que haría la normalización previa."""
    from bbmodel.metricas import destransformar, transformar
    k = c.trad["constantes"].get(m)
    if k is None or not np.isfinite(valor_el) or liga_d not in k["m"]:
        return np.nan
    mu_el, tau_el = SI.entorno(k, "euroleague", "2025-26", pos)
    th = (transformar(valor_el, k["transf"]) - mu_el) / tau_el
    der = k["deriva"].get(SI._tramo_edad(edad), 0.0) if np.isfinite(edad) else 0.0
    zd = (th + der - k["m"][liga_d]) / k["s"][liga_d]
    mu, tau = SI.entorno(k, liga_d, c.temp, pos)
    return float(destransformar(mu + tau * zd, k["transf"]))


def baseline_a(c: S.Corte, x, fila: dict, Lbar_dest: float, mets: list[str], cfg: dict, sens: pd.DataFrame) -> dict:
    """(a) Atlas: producción normalizada (vara EuroLeague) + proyección de contexto con β (si es claro), expresada en la
    liga de destino con el tipo de cambio lineal; minutos = los de origen (mismo peso que tenía en su equipo)."""
    from bbmodel.metricas import destransformar, transformar
    pos = fila.get("pos3") if isinstance(fila.get("pos3"), str) else "A"
    gm = S.minutos_partido(x.liga_d)
    ctx_o = S._ctx_origen(c, fila)
    dctx = (Lbar_dest - ctx_o) if np.isfinite(Lbar_dest) and np.isfinite(ctx_o) else 0.0
    out = {}
    for m in mets:
        v = S._f(fila.get(m)) if c.fuente != "A_corte" or not np.isfinite(S._f(fila.get(f"{m}_am"))) else S._f(fila.get(f"{m}_am"))
        if not np.isfinite(v):
            v = S._f(fila.get(f"{m}_am"))
        k = c.trad["constantes"].get(m)
        if m in sens.index and k is not None and np.isfinite(v):
            b, se = sens.loc[m, "beta_comp"], sens.loc[m, "beta_comp_se"]
            if abs(b) > 2 * se:
                mu_el, tau_el = SI.entorno(k, "euroleague", "2025-26", pos)
                v = float(destransformar(transformar(v, k["transf"]) + tau_el * b * dctx, k["transf"]))
        out[f"{m}_pred"] = _tr_lineal(c, v, pos, x.liga_d, m, S._f(fila.get("edad")))
    mp = S._f(fila.get("min_pct"))
    out["min_pred"] = mp * gm if np.isfinite(mp) else np.nan
    gs = S._f(fila.get("gs_pct"))
    rol = clasificar_uno(mp, gs, fila.get("rol_mas_probable") == "GO_TO_GUY")
    pr = {r: (1 - 0.05) if r == rol else 0.05 / (len(ROLES) - 1) for r in ROLES}
    out.update({f"p_{r}": v for r, v in pr.items()})
    return out


def clasificar_uno(mp, gs, gtg) -> str:
    from .roles import clasificar
    return str(clasificar(np.array([mp]), np.array([gs]), np.array([np.nan]), np.array([bool(gtg)]), cargar("roles"))[0])


def baseline_b(c: S.Corte, x, fila: dict, mets: list[str], cfg: dict, trans: pd.DataFrame | None) -> dict:
    """(b) Simple: producción normalizada traducida al destino (amortiguada, sin uso/compañeros/adaptación), con su
    intervalo de traducción + ruido de muestreo; minutos = MIN% mediano del rol de origen en la liga de destino; rol =
    el de origen (probabilidades: matriz de transición de los fichajes de cortes anteriores)."""
    from bbmodel.metricas import destransformar
    gm = S.minutos_partido(x.liga_d)
    ro = fila.get("rol_mas_probable") if isinstance(fila.get("rol_mas_probable"), str) else "ROTACION"
    mp = c.mod["min_rol"].get((x.liga_d, ro), c.mod["min_rol_global"].get(ro, 0.4))
    out = {"min_pred": mp * gm}
    if trans is not None and ro in trans.index:
        pr = trans.loc[ro].to_dict()
    else:
        pr = {r: 0.9 if r == ro else 0.1 / (len(ROLES) - 1) for r in ROLES}
    out.update({f"p_{r}": float(pr.get(r, 0)) for r in ROLES})
    tr = S.traducir(c, fila, x.liga_d, mets)
    zq = {"50": stats.norm.ppf(0.75), "90": stats.norm.ppf(0.95)}
    ritmo = c.ref["ritmo"].get(x.liga_d, 72.0)
    G = cfg["adaptacion"]["partidos_temporada"].get(x.liga_d, cfg["adaptacion"]["partidos_temporada"]["defecto"])
    poss = mp * ritmo * G * 0.85
    for m in mets:
        v = tr.get(m, np.nan)
        out[f"{m}_pred"] = float(v) if np.isfinite(v) else np.nan
        k = c.trad["constantes"].get(m)
        if k is None or not np.isfinite(v):
            continue
        sd_th = S._f(fila.get(f"{m}_thsd"))
        d_d, v_d = SI._nodo(c.trad["nodos"].get(m, {}), x.liga_d, c.temp)
        s_d, psi = k["s"].get(x.liga_d, 1.0), k["psi"].get(x.liga_d, 0.0)
        s2 = k["sigma2"].get(x.liga_d, np.nan)
        mu, tau = tr.get(f"_{m}_mu"), tr.get(f"_{m}_tau")
        n = poss * (0.2 if k["exposicion"] in ("tsa", "fga", "fg2a", "fg3a") else 1.0)
        var_z = ((sd_th if np.isfinite(sd_th) else 0.5) ** 2 + (v_d if np.isfinite(v_d) else 0.05)) / s_d ** 2 + psi \
            + (s2 / (max(n, 1) * tau ** 2) if np.isfinite(s2) and tau else 0)
        z = tr[f"_{m}_z"]
        for a, q in zq.items():
            out[f"{m}_lo{a}"] = float(destransformar(mu + tau * (z - q * np.sqrt(var_z)), k["transf"]))
            out[f"{m}_hi{a}"] = float(destransformar(mu + tau * (z + q * np.sqrt(var_z)), k["transf"]))
    return out


def matriz_transicion(casos_prev: pd.DataFrame) -> pd.DataFrame | None:
    """P(rol en destino | rol de origen) de los fichajes de cortes anteriores (suavizado de Laplace)."""
    if casos_prev is None or casos_prev.empty:
        return None
    d = casos_prev.dropna(subset=["rol_o", "rol_real"])
    m = pd.crosstab(d["rol_o"], d["rol_real"]).reindex(index=ROLES, columns=ROLES, fill_value=0) + 1
    return m.div(m.sum(1), axis=0)


# =============================================================================================== resultado real
def resultados_reales(casos: pd.DataFrame, c1: S.Corte) -> pd.DataFrame:
    """Lo que pasó en t+1: minutos por partido jugado, MIN%, rol, producción observada (normalizado, unidades de su
    liga) y nivel L (para el éxito del Fit)."""
    r = c1.reg.set_index(["persona_id", "liga", "team_id"])
    mets = list(cfg_sim()["produccion"]["metricas"])
    filas = []
    for x in casos.itertuples(index=False):
        k = (x.persona_id, x.liga_d, x.team_d)
        f = {"persona_id": x.persona_id}
        if k in r.index:
            y = r.loc[k]
            if isinstance(y, pd.DataFrame):
                y = y.iloc[0]
            f.update({"min_real": S._f(y["min_pg"]), "min_pct_real": S._f(y["min_pct"]), "gp_real": S._f(y["gp"]),
                      "min_total_real": S._f(y["min_total"]), "rol_real": y["rol"] if isinstance(y["rol"], str) else y["rol_mas_probable"],
                      "rol_prob_real": bool(y["rol_probabilistico"]), "L_real": S._f(y["L"])})
            for m in mets:
                f[f"{m}_real"] = S._f(y.get(f"{m}_obs"))
        filas.append(f)
    return pd.DataFrame(filas)


def exito(df: pd.DataFrame, c1: S.Corte, cfg: dict) -> pd.Series:
    """Éxito real = 0,5·z(MIN%) + 0,5·z(L) dentro de la liga-temporada de destino (jugadores con ≥ 5 partidos)."""
    ref = c1.reg[c1.reg["gp"] >= 5]
    st = ref.groupby("liga").agg(mm=("min_pct", "mean"), ms=("min_pct", "std"), lm=("L", "mean"), ls=("L", "std"))
    w = cfg["encaje"]["exito"]
    zm = (df["min_pct_real"] - df["liga_d"].map(st["mm"])) / df["liga_d"].map(st["ms"])
    zl = (df["L_real"] - df["liga_d"].map(st["lm"])) / df["liga_d"].map(st["ls"])
    return w["minutos"] * zm + w.get("nivel", 0.5) * zl


# =============================================================================================== Fit
RASGOS_FIT = ["nivel", "rol", "estilo", "complementariedad", "entropia", "adaptacion", "volatilidad", "incertidumbre", "h_rol"]


def ajustar_fit(df: pd.DataFrame, cfg: dict) -> dict | None:
    """Regresión ridge del éxito real sobre los rasgos estandarizados (cortes anteriores)."""
    d = df.dropna(subset=["exito"] + [f"c_{k}" for k in RASGOS_FIT])
    if len(d) < 50:
        return None
    X = d[[f"c_{k}" for k in RASGOS_FIT]].to_numpy(float)
    mu, sd = X.mean(0), X.std(0)
    sd[sd < 1e-9] = 1.0
    Z = (X - mu) / sd
    y = d["exito"].to_numpy(float)
    lam = float(cfg["encaje"]["ridge"])
    A = Z.T @ Z + lam * np.eye(Z.shape[1])
    w = np.linalg.solve(A, Z.T @ (y - y.mean()))
    # intervalos bootstrap de los pesos (remuestreo de fichajes)
    rng = np.random.default_rng(int(cfg["semilla"]))
    bs = []
    for _ in range(200):
        i = rng.integers(0, len(y), len(y))
        Zi, yi = Z[i], y[i]
        bs.append(np.linalg.solve(Zi.T @ Zi + lam * np.eye(Z.shape[1]), Zi.T @ (yi - yi.mean())))
    bs = np.array(bs)
    r2 = 1 - np.var(y - y.mean() - Z @ w) / np.var(y)
    return {"b0": float(y.mean()), "w": dict(zip(RASGOS_FIT, w.tolist())), "media": dict(zip(RASGOS_FIT, mu.tolist())),
            "sd": dict(zip(RASGOS_FIT, sd.tolist())), "w_lo90": dict(zip(RASGOS_FIT, np.quantile(bs, 0.05, 0).tolist())),
            "w_hi90": dict(zip(RASGOS_FIT, np.quantile(bs, 0.95, 0).tolist())), "n": int(len(y)), "r2_dentro": float(r2)}


def aplicar_fit(df: pd.DataFrame, F: dict | None) -> pd.Series:
    if not F:
        return pd.Series(np.nan, index=df.index)
    tot = np.full(len(df), F["b0"])
    for k in RASGOS_FIT:
        x = pd.to_numeric(df[f"c_{k}"], errors="coerce").fillna(F["media"][k]).to_numpy(float)
        tot = tot + F["w"][k] * (x - F["media"][k]) / (F["sd"][k] or 1)
    return pd.Series(tot, index=df.index)


# =============================================================================================== orquestación
def _roles():
    return SI._leer_roles_temporada()


def preparar_corte(t: str, fuente: str, cfg: dict, roles: pd.DataFrame, progreso=print) -> dict:
    """Casos del corte t con su resultado real (caché)."""
    dest = SI.DIR_CACHE / f"casos_{t}_{fuente}.pkl"
    if dest.exists():
        return pickle.loads(dest.read_bytes())
    t1 = SI.siguiente(t)
    c = S.cargar_corte(t, fuente, pesos=False)
    c1 = S.cargar_corte(t1, "AB" if fuente.startswith("A_corte") else fuente, pesos=False)
    casos = fichajes(c, roles, t1, cfg, c1.eq)
    real = resultados_reales(casos, c1)
    casos = casos[["persona_id", "nombre", "liga_o", "team_o", "liga_d", "team_d", "club_t", "temporada_o", "temporada_d"]] \
        .merge(real, on="persona_id", how="left")
    o = c.prin
    casos["rol_o"] = casos["persona_id"].map(o["rol_mas_probable"])
    casos["min_o"] = casos["persona_id"].map(o["min_pg"])
    casos["min_pct_o"] = casos["persona_id"].map(o["min_pct"])
    casos["min_total_o"] = casos["persona_id"].map(o["min_total"])
    casos["exito"] = exito(casos, c1, cfg)
    casos["d_nivel"] = [S._nivel_liga(c, ld) - S._nivel_liga(c, lo) for lo, ld in zip(casos["liga_o"], casos["liga_d"])]
    res = {"casos": casos, "t1": t1}
    dest.write_bytes(pickle.dumps(res))
    if progreso:
        progreso(f"  corte {t}: {len(casos)} fichajes")
    return res


def entrenar_pesos(t: str, fuente: str, cfg: dict, roles: pd.DataFrame, progreso=print) -> dict:
    """Pesos de la utilidad (verosimilitud PL en las temporadas s ≤ t con rasgos de s − 1) y rotación extra (≤ t)."""
    dest = SI.DIR_CACHE / f"pesos_utilidad_{t}_{fuente}.json"
    if dest.exists():
        return json.loads(dest.read_text())
    temps = [x for x in cfg["historico"]["temporadas"] if x <= t]
    bloques, extras = [], []
    for s in temps[1:]:
        cb = SI.DIR_CACHE / f"bloques_{s}_{fuente}.pkl"
        if cb.exists():
            b = pickle.loads(cb.read_bytes())
        else:
            c_prev = S.cargar_corte(temps[temps.index(s) - 1], fuente, pesos=False)
            b = bloques_utilidad(c_prev, roles, s, cfg)
            cb.write_bytes(pickle.dumps(b))
        bloques += b
        c_prev = S.cargar_corte(temps[temps.index(s) - 1], fuente, pesos=False)
        extras.append(rotacion_extra(c_prev, roles, s))
    w = ajustar_utilidad(bloques, cfg) if bloques else dict(cfg["utilidad"]["inicial"])
    res = {"utilidad": w, "calibracion": {"rotacion_extra": float(np.median(extras)) if extras else 1.0,
                                          "disponibilidad": 0.85},
           "equipos_entrenamiento": len(bloques), "temporadas": temps[1:]}
    dest.write_text(json.dumps(res, indent=1))
    if progreso:
        progreso(f"  pesos ≤ {t}: {len(bloques)} equipos · " + ", ".join(f"{k} {v:+.2f}" for k, v in w.items() if not k.startswith("_")))
    return res


def calibrar(t: str, fuente: str, cfg: dict, roles: pd.DataFrame, pesos: dict, progreso=print) -> dict:
    """Escala de la utilidad (temperatura de Plackett-Luce) y factor de la sd de la rotación, elegidos por MAE de minutos
    (mediana) en los fichajes del corte anterior (t−1 → t: resultados ≤ t, sin fuga) con los pesos ≤ t."""
    dest = SI.DIR_CACHE / f"calib_{t}_{fuente}.json"
    if dest.exists():
        return json.loads(dest.read_text())
    temps = cfg["historico"]["temporadas"]
    base = dict(pesos["calibracion"])
    if temps.index(t) == 0:
        return base
    tp = temps[temps.index(t) - 1]
    pc = preparar_corte(tp, fuente, cfg, roles, progreso)
    casos = pc["casos"]
    casos = casos[casos["min_real"].notna() & (casos["gp_real"] >= cfg["validacion"]["min_partidos_destino"])]
    casos = casos.sample(min(len(casos), int(cfg["validacion"]["calibracion_casos"])), random_state=int(cfg["semilla"]))
    c = S.cargar_corte(tp, fuente, pesos=False)
    c.w_util, c.fit = pesos["utilidad"], None
    eq1 = S.cargar_corte(t, "AB" if fuente.startswith("A_corte") else fuente, pesos=False).eq
    r1 = roles[roles["temporada"] == t]
    filas = []
    for k_u in cfg["validacion"]["rejilla_escala"]:
        for ex in cfg["validacion"]["rejilla_rotacion_extra"]:
            f_sd = float(cfg["validacion"]["rotacion_sd_factor"])
            c.calib = {**base, "escala_utilidad": k_u, "rotacion_sd_factor": f_sd,
                       "rotacion_extra": float(base.get("rotacion_extra", 1.0)) + ex}
            v = simular_fichajes(c, casos, r1, eq1, cfg, "inicio", n_sim=int(cfg["validacion"]["calibracion_sim"]),
                                 progreso=None, sin_adaptacion=True)
            m = casos.reset_index(drop=True).join(v[["min_pred", "min_lo50", "min_hi50"] + [f"p_{r}" for r in ROLES]])
            ok = m["rol_real"].isin(ROLES)
            P = m.loc[ok, [f"p_{r}" for r in ROLES]].to_numpy(float)
            y = m.loc[ok, "rol_real"].map({r: i for i, r in enumerate(ROLES)}).to_numpy(int)
            filas.append({"escala_utilidad": k_u, "rotacion_sd_factor": f_sd, "extra_adicional": ex,
                          "mae_min": float((m["min_pred"] - m["min_real"]).abs().mean()),
                          "cob50_min": float(((m["min_real"] >= m["min_lo50"]) & (m["min_real"] <= m["min_hi50"])).mean()),
                          "logloss": float(_logloss(P, y).mean())})
    g = pd.DataFrame(filas)
    g["obj"] = g["mae_min"] / g["mae_min"].min() + g["logloss"] / g["logloss"].min()
    best = g.sort_values("obj").iloc[0]
    res = {**base, "escala_utilidad": float(best["escala_utilidad"]), "rotacion_sd_factor": float(best["rotacion_sd_factor"]),
           "rotacion_extra": float(base.get("rotacion_extra", 1.0)) + float(best["extra_adicional"]),
           "rejilla": g.round(4).to_dict("records"), "corte_calibracion": tp}
    dest.write_text(json.dumps(res, indent=1))
    if progreso:
        progreso(f"  calibración {t} (fichajes {tp}): escala {best['escala_utilidad']}, rotación +{best['extra_adicional']}"
                 f" · MAE {best['mae_min']:.2f} · log-loss {best['logloss']:.3f}")
    return res


def ejecutar_corte(t: str, fuente: str, cfg: dict, roles: pd.DataFrame, pesos: dict, fit: dict | None,
                   trans: pd.DataFrame | None, escenario: str = "inicio", progreso=print, sin_adaptacion=False,
                   etiqueta: str = "") -> pd.DataFrame:
    """Predicciones (v2, baselines a y b) de los fichajes del corte t. Caché por (corte, fuente, escenario, etiqueta)."""
    dest = SI.DIR_CACHE / f"pred_{t}_{fuente}_{escenario}{etiqueta}.pkl"
    if dest.exists():
        return pickle.loads(dest.read_bytes())
    pc = preparar_corte(t, fuente, cfg, roles, progreso)
    casos, t1 = pc["casos"], pc["t1"]
    c = S.cargar_corte(t, fuente, pesos=False)
    c.w_util, c.calib, c.fit = pesos["utilidad"], pesos["calibracion"], fit
    eq1 = S.cargar_corte(t1, "AB", pesos=False).eq if t1 <= cfg["historico"]["temporadas"][-1] else _eq_simple(roles, t1)
    r1 = roles[roles["temporada"] == t1]
    v2 = simular_fichajes(c, casos, r1, eq1, cfg, escenario, progreso=progreso, sin_adaptacion=sin_adaptacion)
    mets = list(cfg["produccion"]["metricas"])
    sens = pd.read_csv(SI.DIR_MOD / "contexto" / "sensibilidad.csv").set_index("metrica")
    A, B = [], []
    for x in casos.itertuples(index=False):
        fila = S.jugador_insumos(c, x.persona_id)
        Lbar = _lbar_destino(c, r1, x, escenario, cfg)
        A.append(baseline_a(c, x, fila, Lbar, mets, cfg, sens))
        B.append(baseline_b(c, x, fila, mets, cfg, trans))
    A, B = pd.DataFrame(A).add_prefix("a_"), pd.DataFrame(B).add_prefix("b_")
    out = pd.concat([casos.reset_index(drop=True), v2.drop(columns=["persona_id", "liga_o", "liga_d", "team_d"]).add_prefix("v_"),
                     A, B], axis=1)
    out["fuente"], out["escenario"], out["corte"] = fuente, escenario, t
    dest.write_bytes(pickle.dumps(out))
    return out


def _eq_simple(roles, t1):
    e = roles[roles["temporada"] == t1][["liga", "team_id"]].drop_duplicates()
    e["entrenador"] = None
    return e


def _lbar_destino(c: S.Corte, r1: pd.DataFrame, x, escenario: str, cfg: dict) -> float:
    """L medio de los compañeros de destino ponderado por sus minutos de t (lo que usaba el Atlas para el contexto)."""
    mi = miembros_escenario(r1, x.liga_d, x.team_d, escenario, cfg)
    num = den = 0.0
    for p, pres in mi:
        if p == x.persona_id or p not in c.prin.index:
            continue
        r = c.prin.loc[p]
        L, m = S._f(r["L"]), S._f(r["min_total"])
        if np.isfinite(L) and np.isfinite(m):
            num += L * m * pres
            den += m * pres
    return num / den if den > 0 else np.nan


# =============================================================================================== métricas
def _logloss(P: np.ndarray, y: np.ndarray) -> np.ndarray:
    P = np.clip(P, EPS, 1)
    P = P / P.sum(1, keepdims=True)
    return -np.log(P[np.arange(len(y)), y])


def errores(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Errores por fichaje y método (v2, a, b)."""
    v = cfg["validacion"]
    out = df.copy()
    ok_rol = out["rol_real"].isin(ROLES) & (out["gp_real"] >= v["min_partidos_destino"])
    y = out["rol_real"].map({r: i for i, r in enumerate(ROLES)})
    for pre in ("v", "a", "b"):
        out[f"{pre}_err_min"] = (out[f"{pre}_min_pred"] - out["min_real"]).abs()
        P = out[[f"{pre}_p_{r}" for r in ROLES]].to_numpy(float)
        okp = np.isfinite(P).all(1) & ok_rol.to_numpy()
        ll = np.full(len(out), np.nan)
        ll[okp] = _logloss(P[okp], y[okp].astype(int).to_numpy())
        out[f"{pre}_logloss"] = ll
        pred = np.array(ROLES, object)[np.nan_to_num(P, nan=-1).argmax(1)]
        if pre == "v":
            # rol puntual de v2 = regla de roles aplicada a la mediana de minutos y a P(titular); GO-TO-GUY si
            # P(GO-TO-GUY) > P(TITULAR). El arg máx. de las probabilidades se guarda aparte.
            out["v_rol_argmax"] = np.where(okp, pred, None)
            out["v_acierto_argmax"] = np.where(okp, (pred == out["rol_real"]).astype(float), np.nan)
            gm = np.where(out["liga_d"].isin(["nba", "gleague"]), 48.0, 40.0)
            pred = np.asarray(clasificar(out["v_min_pred"].to_numpy(float) / gm, out["v_p_titular"].to_numpy(float),
                                         np.full(len(out), np.nan),
                                         (out["v_p_GO_TO_GUY"] > out["v_p_TITULAR"]).to_numpy(bool), cargar("roles")), object)
        out[f"{pre}_rol_pred"] = np.where(okp, pred, None)
        out[f"{pre}_acierto"] = np.where(okp, (pred == out["rol_real"]).astype(float), np.nan)
        for m in cfg["produccion"]["metricas"]:
            if f"{pre}_{m}_pred" not in out:
                continue
            ok = out["min_total_real"] >= v["min_minutos_produccion"]
            e = out[f"{pre}_{m}_pred"] - out[f"{m}_real"]
            out[f"{pre}_err_{m}"] = np.where(ok, e, np.nan)
            for a in ("50", "90"):
                if f"{pre}_{m}_lo{a}" in out:
                    dentro = (out[f"{m}_real"] >= out[f"{pre}_{m}_lo{a}"]) & (out[f"{m}_real"] <= out[f"{pre}_{m}_hi{a}"])
                    out[f"{pre}_cob{a}_{m}"] = np.where(ok & out[f"{pre}_{m}_lo{a}"].notna(), dentro.astype(float), np.nan)
        for a in ("50", "90"):
            if f"{pre}_min_lo{a}" in out:
                dentro = (out["min_real"] >= out[f"{pre}_min_lo{a}"]) & (out["min_real"] <= out[f"{pre}_min_hi{a}"])
                out[f"{pre}_cob{a}_min"] = np.where(out["min_real"].notna() & ok_rol, dentro.astype(float), np.nan)
    out["eval_min"] = out["min_real"].notna() & ok_rol
    return out


def resumen_metricas(e: pd.DataFrame, cfg: dict, principal: str = "pts_p100") -> dict:
    r = {}
    for pre in ("v", "a", "b"):
        d = {"n_min": int(e["eval_min"].sum()),
             "mae_min": float(e.loc[e["eval_min"], f"{pre}_err_min"].mean()),
             "acierto_rol": float(e[f"{pre}_acierto"].mean()), "logloss_rol": float(e[f"{pre}_logloss"].mean())}
        for m in cfg["produccion"]["metricas"]:
            c_ = f"{pre}_err_{m}"
            if c_ in e:
                x = e[c_].dropna()
                d[f"mae_{m}"], d[f"rmse_{m}"], d[f"n_{m}"] = float(x.abs().mean()), float(np.sqrt((x ** 2).mean())), int(len(x))
                for a in ("50", "90"):
                    cc = f"{pre}_cob{a}_{m}"
                    if cc in e:
                        d[f"cob{a}_{m}"] = float(e[cc].mean())
        for a in ("50", "90"):
            cc = f"{pre}_cob{a}_min"
            if cc in e:
                d[f"cob{a}_min"] = float(e[cc].mean())
        r[pre] = d
    return r


def bootstrap_diferencias(e: pd.DataFrame, cfg: dict, B: int | None = None, cluster: str = "club") -> pd.DataFrame:
    """IC bootstrap (remuestreo por club de destino, pareado) de v2 − baseline en MAE de minutos, log-loss, acierto de rol
    y MAE/RMSE de producción (negativo = v2 mejor en errores; positivo = v2 mejor en acierto)."""
    v = cfg["validacion"]
    B = int(B or v["bootstrap"])
    rng = np.random.default_rng(int(cfg["semilla"]))
    g = (e["liga_d"] + "|" + e["team_d"].astype(str) + "|" + e["corte"].astype(str)).to_numpy()
    grupos = pd.Series(np.arange(len(e))).groupby(g).apply(list).tolist()
    met = {"mae_min": ("err_min", "eval_min", "abs"), "logloss_rol": ("logloss", None, "id"),
           "acierto_rol": ("acierto", None, "id")}
    for m in (cfg["produccion"]["principal"], "ts_pct", "usg_pct"):
        met[f"mae_{m}"] = (f"err_{m}", None, "abs")
        met[f"rmse_{m}"] = (f"err_{m}", None, "sq")
    filas = []
    for nombre, (col, filtro, tipo) in met.items():
        for base in ("a", "b"):
            if f"v_{col}" not in e or f"{base}_{col}" not in e:
                continue
            xv, xb = e[f"v_{col}"].to_numpy(float), e[f"{base}_{col}"].to_numpy(float)
            ok = np.isfinite(xv) & np.isfinite(xb)
            if filtro:
                ok &= e[filtro].to_numpy(bool)
            if ok.sum() < 20:
                continue
            f = (lambda x: np.abs(x)) if tipo == "abs" else (lambda x: x ** 2) if tipo == "sq" else (lambda x: x)

            def est(idx):
                i = idx[ok[idx]]
                a_, b_ = f(xv[i]).mean(), f(xb[i]).mean()
                if tipo == "sq":
                    return np.sqrt(a_) - np.sqrt(b_)
                return a_ - b_
            todos = np.arange(len(e))
            d0 = est(todos)
            bs = []
            for _ in range(B):
                sel = rng.integers(0, len(grupos), len(grupos))
                idx = np.concatenate([grupos[k] for k in sel])
                bs.append(est(idx))
            bs = np.array(bs)
            lo, hi = np.quantile(bs, [0.05, 0.95])
            mejor = (hi < 0) if nombre != "acierto_rol" else (lo > 0)
            peor = (lo > 0) if nombre != "acierto_rol" else (hi < 0)
            filas.append({"metrica": nombre, "baseline": base, "n": int(ok.sum()), "v2": float(f(xv[ok]).mean() ** (0.5 if tipo == "sq" else 1)),
                          "base": float(f(xb[ok]).mean() ** (0.5 if tipo == "sq" else 1)), "diferencia": float(d0),
                          "ic90_lo": float(lo), "ic90_hi": float(hi),
                          "veredicto": "v2 mejor" if mejor else ("v2 peor" if peor else "sin diferencia clara")})
    return pd.DataFrame(filas)


def segmentos(e: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Métricas por segmento: liga de origen y destino, grupo de nacionalidad, posición, rol de origen y real, distancia."""
    e = e.copy()
    e["distancia"] = pd.cut(e["d_nivel"].abs(), [-0.01, 0.2, 0.6, 10], labels=["<0,2", "0,2-0,6", ">0,6"]).astype(str)
    e["sentido"] = np.where(e["d_nivel"] > 0.1, "sube", np.where(e["d_nivel"] < -0.1, "baja", "igual"))
    e["grupo_nac"] = e["v_grupo_nac"]
    e["pos3"] = e["v_pos3"]
    m = cfg["produccion"]["principal"]
    filas = []
    for seg in ("liga_o", "liga_d", "grupo_nac", "pos3", "rol_o", "rol_real", "distancia", "sentido", "corte"):
        for val, g in e.groupby(seg):
            f = {"segmento": seg, "valor": val, "n": len(g), "n_min": int(g["eval_min"].sum())}
            for pre in ("v", "a", "b"):
                f[f"{pre}_mae_min"] = g.loc[g["eval_min"], f"{pre}_err_min"].mean()
                f[f"{pre}_acierto"] = g[f"{pre}_acierto"].mean()
                f[f"{pre}_logloss"] = g[f"{pre}_logloss"].mean()
                f[f"{pre}_mae_{m}"] = g[f"{pre}_err_{m}"].abs().mean()
            f[f"v_cob90_{m}"] = g[f"v_cob90_{m}"].mean()
            f[f"b_cob90_{m}"] = g[f"b_cob90_{m}"].mean()
            f["v_gana_min_a"] = f["v_mae_min"] < f["a_mae_min"]
            f["v_gana_min_b"] = f["v_mae_min"] < f["b_mae_min"]
            f["v_gana_rol_b"] = f["v_logloss"] < f["b_logloss"]
            f[f"v_gana_{m}_b"] = f[f"v_mae_{m}"] < f[f"b_mae_{m}"]
            filas.append(f)
    return pd.DataFrame(filas)


def confusion(e: pd.DataFrame, pre: str = "v") -> pd.DataFrame:
    d = e.dropna(subset=[f"{pre}_rol_pred"])
    d = d[d["rol_real"].isin(ROLES)]
    return pd.crosstab(d["rol_real"], d[f"{pre}_rol_pred"]).reindex(index=ROLES, columns=ROLES, fill_value=0)


def calibracion_roles(e: pd.DataFrame, bins: int = 10) -> pd.DataFrame:
    """Fiabilidad de las probabilidades de rol de v2 (todas las clases juntas)."""
    filas = []
    for r in ROLES:
        p = e[f"v_p_{r}"].to_numpy(float)
        y = (e["rol_real"] == r).to_numpy(float)
        ok = np.isfinite(p) & e["rol_real"].isin(ROLES).to_numpy()
        filas.append(pd.DataFrame({"p": p[ok], "y": y[ok]}))
    d = pd.concat(filas)
    d["bin"] = pd.cut(d["p"], np.linspace(0, 1, bins + 1), include_lowest=True)
    return d.groupby("bin", observed=True).agg(p_media=("p", "mean"), frecuencia=("y", "mean"), n=("y", "size")).reset_index()


# =============================================================================================== principal
def _etiqueta(fuente: str, escenario: str, adaptacion: bool) -> str:
    return f"{fuente.replace(':', '_')}_{escenario}{'' if not adaptacion else '_adapt'}"


def backtest(fuente: str = "AB", escenario: str = "inicio", cortes: list[str] | None = None, progreso=print,
             guardar: bool = True, adaptacion: bool = False, pesos_de: str | None = None) -> dict:
    """Examen temporal completo, cronológico y reanudable.

    adaptacion=False (por defecto): Δ de adaptación = 0. Los priors de la fase 7 se estimaron con TODOS los traspasos
    (incluidos los del examen): usarlos en el examen sería fuga; la variante adaptacion=True mide su efecto.
    pesos_de: etiqueta de otra ejecución (p. ej. «AB_inicio») cuyos pesos por corte (utilidad, calibración, Fit) se
    reutilizan: así dos fuentes de θ (A con todas las temporadas frente a A reajustado con ≤ t) sólo difieren en θ."""
    cfg = cfg_sim()
    roles = _roles()
    temps = cfg["historico"]["temporadas"]
    examen = cortes or cfg["validacion"]["cortes_examen"]
    etq = _etiqueta(fuente, escenario, adaptacion)
    t0 = time.time()
    preds, F_por_corte, P_por_corte = [], {}, {}
    if pesos_de:
        todos = list(examen)
    else:
        todos = [t for t in temps[:-1] if t <= max(examen)]
    for k, t in enumerate(todos):
        fp = SI.DIR_CACHE / f"pesos_final_{t}_{pesos_de or etq}.pkl"
        if pesos_de:
            pesos, fit, trans = pickle.loads(fp.read_bytes())
        else:
            prev = pd.concat(preds, ignore_index=True) if preds else pd.DataFrame()
            if k > 0:
                pesos = entrenar_pesos(t, fuente, cfg, roles, progreso)
                pesos = {**pesos, "calibracion": calibrar(t, fuente, cfg, roles, pesos, progreso)}
            else:
                pesos = {"utilidad": dict(cfg["utilidad"]["inicial"]),
                         "calibracion": {"rotacion_extra": 3.0, "disponibilidad": 0.85, "escala_utilidad": 1.0,
                                         "rotacion_sd_factor": float(cfg["validacion"]["rotacion_sd_factor"])}}
            fit = ajustar_fit(prev.assign(**{f"c_{r}": prev[f"v_c_{r}"] for r in RASGOS_FIT}), cfg) if len(prev) else None
            trans = matriz_transicion(prev[["rol_o", "rol_real"]]) if len(prev) else None
            fp.write_bytes(pickle.dumps((pesos, fit, trans)))
        d = ejecutar_corte(t, fuente, cfg, roles, pesos, fit, trans, escenario, progreso,
                           sin_adaptacion=not adaptacion, etiqueta="_adapt" if adaptacion else "")
        d["v_fit"] = aplicar_fit(d.assign(**{f"c_{r}": d.get(f"v_c_{r}") for r in RASGOS_FIT}), fit)
        preds.append(d)
        F_por_corte[t], P_por_corte[t] = fit, pesos
        progreso(f"corte {t} listo ({len(d)} fichajes, {time.time() - t0:.0f} s)")
    todo = pd.concat(preds, ignore_index=True)
    ex = todo[todo["corte"].isin(examen)]
    e = errores(ex, cfg)
    res = {"fuente": fuente, "escenario": escenario, "adaptacion": adaptacion, "pesos_de": pesos_de, "cortes": examen,
           "resumen": resumen_metricas(e, cfg), "resumen_por_corte": {t: resumen_metricas(g, cfg) for t, g in e.groupby("corte")},
           "pesos": {t: P_por_corte[t] for t in P_por_corte}, "fit": {t: F_por_corte[t] for t in F_por_corte},
           "acierto_rol_argmax_v2": float(e["v_acierto_argmax"].mean())}
    bt = bootstrap_diferencias(e, cfg)
    res["bootstrap"] = bt.to_dict("records")
    seg = segmentos(e, cfg)
    ok = e["v_fit"].notna() & e["exito"].notna()
    if ok.sum() > 10:
        res["fit_validacion"] = {"spearman": float(stats.spearmanr(e.loc[ok, "v_fit"], e.loc[ok, "exito"]).statistic),
                                 "n": int(ok.sum()), "pendiente": float(np.polyfit(e.loc[ok, "v_fit"], e.loc[ok, "exito"], 1)[0]),
                                 "spearman_min_origen": float(stats.spearmanr(e.loc[ok, "min_pct_o"], e.loc[ok, "exito"]).statistic),
                                 "spearman_L_origen": float(stats.spearmanr(e.loc[ok, "v_L_o"], e.loc[ok, "exito"]).statistic)}
    if guardar:
        d = DIR_VAL / etq
        d.mkdir(parents=True, exist_ok=True)
        e.to_csv(d / "predicciones.csv.gz", index=False, float_format="%.4f")
        bt.to_csv(d / "bootstrap.csv", index=False, float_format="%.4f")
        seg.to_csv(d / "segmentos.csv", index=False, float_format="%.4f")
        for pre in ("v", "a", "b"):
            confusion(e, pre).to_csv(d / f"confusion_{pre}.csv")
        calibracion_roles(e).to_csv(d / "calibracion_roles.csv", index=False, float_format="%.4f")
        (d / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    progreso(f"examen {etq} terminado en {time.time() - t0:.0f} s")
    return res


def main(fuente: str = "AB", escenario: str = "inicio", adaptacion: bool = False, pesos_de: str | None = None,
         cortes: list[str] | None = None) -> dict:
    from .registro import experimento
    cfg = cfg_sim()
    with experimento("simulador_v2", f"examen_{_etiqueta(fuente, escenario, adaptacion)}", params={
            "fuente": fuente, "escenario": escenario, "adaptacion": adaptacion, "pesos_de": pesos_de},
            semilla=cfg["semilla"]) as run:
        r = backtest(fuente, escenario, cortes, adaptacion=adaptacion, pesos_de=pesos_de)
        run.metricas({f"{p}_{k}": v for p, d in r["resumen"].items() for k, v in d.items()
                      if k in ("mae_min", "logloss_rol", "acierto_rol", "mae_pts_p100", "cob90_pts_p100")})
    return r


if __name__ == "__main__":   # python -m bbfit.validacion [fuente] [escenario] [--adaptacion]
    import sys
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    r = main(a[0] if a else "AB", a[1] if len(a) > 1 else "inicio", "--adaptacion" in sys.argv)
    print(json.dumps(r["resumen"], indent=1))
