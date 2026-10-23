"""Fase 8 — simulador de encaje (fit-in) v2.

El usuario elige SÓLO jugador + club de destino (+ escenario de plantilla opcional: quién no está). No se teclean
minutos: el rol y los minutos son endógenos. Cada iteración Monte Carlo (semilla fija) recorre:

1. Nivel latente traducido al destino (normalización amortiguada): capacidad θ_m (DT de la vara EuroLeague) de cada
   métrica con su desviación (`<m>_am`, `_am_lo/_hi`), deriva por edad, nivel δ de la competición de destino con su
   incertidumbre acumulada (league_offsets) y desviación de temporada ψ:
       z_d = (θ + deriva + sd·ε₁ − (δ_d + sd_δ·ε₂)) / s_d + √ψ_d·ε₃,   valor = T⁻¹(μ_d,pos + τ_d,pos·z_d)
2. Adaptación (fase 7, bbfit.adaptacion.prior/curva): factor 1 + Δ·exp(−g/κ) por partido; la producción de la
   temporada se multiplica por su media en los partidos que juega; ADAPT% = 100 × esa media.
3. Rol y minutos endógenos: bbfit.reemplazo.asignar_minutos (Plackett-Luce) sobre la plantilla de destino con el
   fichaje; utilidad u_i = Σ_k w_k·x_ik (nivel L, minutos previos en el club o fuera, nuevo, encaje posicional y de
   estilo, edad; w por máxima verosimilitud de las rotaciones reales, bbfit.validacion), restricciones de posición,
   tamaño de rotación y curva de reparto del entrenador de destino (su historial). GO-TO-GUY = TITULAR por minutos
   y top-2 del equipo en el GTI proyectado (el GTI de origen corregido por el cambio de uso).
4. Uso: Σ_i min_i·USG_i = 20·Σ min (suma fija); cada jugador lleva su uso natural traducido y el desajuste se
   reparte a prorrata (amortiguado). Curva uso-eficiencia: TS' = TS + β·ΔUSG con β ~ N(β_pos3, sd) (IV, fase 4) y
   P100' = P100·(USG'/USG)·(TS'/TS).
5. Calidad de compañeros: L̄ = media de L de los compañeros ponderada por sus minutos simulados; TS += b·(L̄ − L̄_origen)
   (coeficiente de bbfit.reemplazo.efecto_companeros, muestreado de su intervalo).
6. Estilo: distancia (Jensen-Shannon) entre el vector de estilo unificado del jugador y el del equipo, complementariedad
   (cubre un hueco de estilo frente a la composición típica de los equipos de ese estilo) y efecto en la entropía del
   reparto de uso y de la red de pases del equipo. Entra en la utilidad de minutos (encaje de estilo) y en el Fit.
7. Ruido personal: σ_i (volatilidad, fase 5) para pts/100 y ruido de muestreo del A para el resto, según las
   posesiones simuladas.
8. Ritmo y competición: por partido = por 100 × posesiones del club de destino en sus minutos.

Salidas: reparto de roles y minutos esperados, producción por 100 y por partido con intervalos del 50 % y 90 %, índice
Fit descompuesto de forma aditiva (nivel, rol, estilo, complementariedad, adaptación, riesgo), impacto en el Net del
equipo y quintetos más probables, curva de adaptación y ADAPT% esperado, avisos automáticos.
Configuración: configs/simulation.yaml. Insumos: bbfit/sim_insumos.py. Validación: bbfit/validacion.py.
"""
from __future__ import annotations

import json
import math
import pickle
import zlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import sim_insumos as SI
from .config import DIR_MOD, cargar
from .roles import ROLES, clasificar

DIR_SIM = DIR_MOD / "simulador" / "v2"
IDX_ROL = {r: i for i, r in enumerate(ROLES)}
ADAPT_METRICA = {"pts_p100": "pts_p100", "ts_pct": "ts_pct", "usg_pct": "usg_pct", "ast_pct": "ast_pct",
                 "oreb_p100": "reb_p100", "dreb_p100": "reb_p100"}
RASGOS_UTIL = ["L", "lmin_club", "lmin_fuera", "nuevo", "sin_dato", "encaje_pos", "encaje_estilo", "edad_c", "edad_c2"]


def cfg_sim() -> dict:
    return cargar("simulation")


def minutos_partido(liga: str) -> float:
    m = cargar("roles")["partido"]["minutos_reglamentarios"]
    return float(m.get(liga, m["defecto"]))


def _f(x) -> float:
    """Número o NaN (None, texto o vacío → NaN)."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return float("nan")
    return x


def _logit(p, lo=0.02, hi=0.98):
    p = np.clip(np.asarray(p, float), lo, hi)
    return np.log(p / (1 - p))


def _js(p, q) -> float:
    """Divergencia de Jensen-Shannon (bits, 0-1) entre dos repartos."""
    p, q = np.asarray(p, float), np.asarray(q, float)
    if not (np.isfinite(p).all() and np.isfinite(q).all()) or p.sum() <= 0 or q.sum() <= 0:
        return np.nan
    p, q = p / p.sum(), q / q.sum()
    m = (p + q) / 2
    kl = lambda a, b: float(np.sum(np.where(a > 0, a * np.log2(np.maximum(a, 1e-12) / np.maximum(b, 1e-12)), 0)))  # noqa: E731
    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


def _entropia_norm(w) -> float:
    w = np.asarray(w, float)
    w = w[np.isfinite(w) & (w > 0)]
    if len(w) < 2:
        return 0.0
    p = w / w.sum()
    return float(-(p * np.log2(p)).sum() / np.log2(len(p)))


# =============================================================================================== corte
@dataclass
class Corte:
    """Insumos de una temporada t (para simular t → t+1)."""
    temp: str
    fuente: str
    reg: pd.DataFrame
    eq: pd.DataFrame
    trad: dict
    mod: dict
    ref: dict
    cfg: dict
    w_util: dict = field(default_factory=dict)
    fit: dict | None = None
    calib: dict = field(default_factory=dict)

    def __post_init__(self):
        p = self.reg[self.reg["principal"]]
        self.prin = p.set_index("persona_id")
        self.club_de = {}
        for r in self.reg[["persona_id", "club"]].itertuples(index=False):
            self.club_de.setdefault(r.persona_id, set()).add(r.club)
        self.por_club = {k: g for k, g in self.reg.groupby("club")}


_CORTES: dict = {}


def cargar_corte(temp: str, fuente: str | None = None, cfg: dict | None = None, pesos: str | Path | None = None) -> Corte:
    """Insumos de la temporada `temp` con la fuente de θ indicada (AB, A o A_corte). Caché en memoria y en disco."""
    cfg = cfg or cfg_sim()
    fuente = fuente or cfg["normalizacion"]["fuente"]
    k = (temp, fuente)
    if k in _CORTES:
        c = _CORTES[k]
    else:
        dest = SI.DIR_CACHE / f"corte_{temp}_{fuente}.pkl"
        if dest.exists():
            reg, eq, trad = pickle.loads(dest.read_bytes())
        else:
            mets = SI.metricas_traduccion(cfg)
            if fuente == "A_corte":
                nh = SI.normalizacion_hasta(SI.anio(temp), mets)
                theta, trad = nh["theta"], nh["traduccion"]
            else:
                trad = SI.traduccion_completa(mets)
                theta = SI.theta_completa(fuente, mets, trad)
            reg = SI.registros_temporada(temp, theta, trad["constantes"], cfg)
            eq = SI.equipos_temporada(temp, reg)
            reg = reg.merge(eq[["liga", "team_id", "club"]], on=["liga", "team_id"], how="left")
            reg["club"] = reg["club"].fillna(reg["liga"] + "|" + reg["team_id"].astype(str))
            SI.DIR_CACHE.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(pickle.dumps((reg, eq, trad)))
        mod = SI.modelos_hasta(temp, cfg)
        ref = referencias(reg, eq, temp)
        c = Corte(temp, fuente, reg, eq, trad, mod, ref, cfg)
        _CORTES[k] = c
    pesos_def = DIR_SIM / "pesos.json"
    ruta = Path(pesos) if pesos else pesos_def
    if not c.w_util:
        c.w_util = dict(cfg["utilidad"]["inicial"])
    if ruta.exists() and pesos is not False:
        P = json.loads(ruta.read_text(encoding="utf-8"))
        c.w_util = P.get("utilidad", c.w_util)
        c.fit = P.get("fit")
        c.calib = P.get("calibracion", {})
    return c


def referencias(reg: pd.DataFrame, eq: pd.DataFrame, temp: str) -> dict:
    """Referencias de la temporada t por liga: uso (USG% de caja) de los jugadores de rotación, L de banquillo, reparto
    de minutos por posición, σ_i típica, composición de estilos de las plantillas según el estilo del equipo."""
    out = {"uso": {}, "banquillo": {}, "pos": {}, "sigma": {}, "sigma_p80": {}, "estilo_objetivo": {}, "ritmo": {}}
    ids = SI.estilos_ids()
    pc = [f"eu_{i}" for i in ids]
    for liga, g in reg.groupby("liga"):
        rot = g[(g["min_pct"] >= 0.25) & (g["gp"] >= 5)]
        u = pd.to_numeric(rot.get("usg_pct_obs"), errors="coerce").dropna()
        out["uso"][liga] = (float(u.mean()), float(u.std())) if len(u) > 5 else (20.0, 5.0)
        b = g[(g["min_total"] < 300) & g["L"].notna()]
        out["banquillo"][liga] = float(np.average(b["L"], weights=b["min_total"])) if len(b) else float(g["L"].quantile(0.2))
        pos = g.dropna(subset=["pos3"]).groupby("pos3")["min_total"].sum()
        out["pos"][liga] = (pos / pos.sum()).to_dict() if pos.sum() > 0 else {"E": 0.45, "A": 0.2, "I": 0.35}
        s = g["sigma"].dropna()
        out["sigma"][liga] = float(s.median()) if len(s) else np.nan
        out["sigma_p80"][liga] = float(s.quantile(0.8)) if len(s) else np.nan
        e = eq[eq["liga"] == liga]
        out["ritmo"][liga] = float(pd.to_numeric(e.get("lg_pace"), errors="coerce").median()) if len(e) else np.nan
    # composición de estilos de las plantillas por estilo del equipo (minutos de jugadores ≥ 100 min)
    j = reg[reg["min_total"] >= 100].dropna(subset=pc)
    comp = []
    for (liga, team), g in j.groupby(["liga", "team_id"]):
        w = g["min_total"].to_numpy(float)
        comp.append({"liga": liga, "team_id": team, **dict(zip(ids, (g[pc].to_numpy(float) * w[:, None]).sum(0) / w.sum()))})
    comp = pd.DataFrame(comp)
    if len(comp):
        comp = comp.merge(eq[["liga", "team_id", "eu"]], on=["liga", "team_id"], how="left")
        tot = comp[ids].mean().to_numpy(float)
        for k_, g in comp.dropna(subset=["eu"]).groupby("eu"):
            out["estilo_objetivo"][k_] = g[ids].mean().to_numpy(float).tolist() if len(g) >= 5 else tot.tolist()
        out["estilo_objetivo"]["_todos"] = tot.tolist()
    return out


# =============================================================================================== traducción
def _tramo(edad) -> str:
    return SI._tramo_edad(edad)


def traducir(c: Corte, fila: pd.Series | dict, liga_d: str, metricas: list[str], z1=None, z2=None, rng=None,
             n: int = 1) -> dict:
    """Valor «verdadero» de cada métrica en la liga de destino (unidades de esa liga). Con z1/z2/rng: n muestras
    (ε₁ común a todas las métricas: incertidumbre del jugador y de su liga; ε₂ común: nivel del destino; ε₃ propio)."""
    from bbmodel.metricas import destransformar
    const, nodos = c.trad["constantes"], c.trad["nodos"]
    pos = fila.get("pos3") if isinstance(fila.get("pos3"), str) else "A"
    edad = fila.get("edad")
    out = {}
    for m in metricas:
        if m not in const or f"{m}_th" not in fila:
            continue
        k = const[m]
        th, sd = float(fila.get(f"{m}_th", np.nan)), float(fila.get(f"{m}_thsd", np.nan))
        if not np.isfinite(th) or liga_d not in k["s"]:
            out[m] = np.full(n, np.nan) if n > 1 or z1 is not None else np.nan
            continue
        sd = sd if np.isfinite(sd) else 0.5
        der = k["deriva"].get(_tramo(edad), 0.0) if edad is not None and np.isfinite(edad) else k["deriva"].get("s/d", 0.0)
        d_d, v_d = SI._nodo(nodos.get(m, {}), liga_d, c.temp)
        if not np.isfinite(d_d):
            d_d, v_d = k["m"].get(liga_d, 0.0), 0.05
        mu, tau = SI.entorno(k, liga_d, c.temp, pos)
        s_d, psi = k["s"][liga_d], k["psi"].get(liga_d, 0.0)
        if z1 is None:
            zd = (th + der - d_d) / s_d
        else:
            e3 = rng.standard_normal(n)
            zd = (th + der + sd * z1 - (d_d + math.sqrt(max(v_d, 0)) * z2)) / s_d + math.sqrt(max(psi, 0)) * e3
        out[m] = destransformar(mu + tau * zd, k["transf"])
        out[f"_{m}_z"] = zd
        out[f"_{m}_mu"], out[f"_{m}_tau"] = mu, tau
    return out


def ruido_muestreo(c: Corte, m: str, liga_d: str, valor, exposicion, rng) -> np.ndarray:
    """Ruido de muestreo de la temporada observada (paso 1 del A: σ²/n en la escala transformada)."""
    from bbmodel.metricas import destransformar, transformar
    k = c.trad["constantes"][m]
    s2 = k["sigma2"].get(liga_d, k["sigma2"].get("todas", np.nan))
    pos_tau = [np.sqrt(v) for kk, v in k["tau2"].items() if kk.startswith(liga_d + "|")]
    if not np.isfinite(s2):
        return np.asarray(valor, float)
    y = transformar(valor, k["transf"])
    n = np.maximum(np.asarray(exposicion, float), 1.0)
    y = y + rng.standard_normal(len(y)) * np.sqrt(s2 / n)
    return destransformar(y, k["transf"])


# =============================================================================================== plantilla
def jugador_insumos(c: Corte, persona_id: str, registro: dict | None = None) -> dict | None:
    """Insumos de origen de una persona (su registro principal en t, o el registro dado)."""
    if registro is not None:
        return dict(registro)
    if persona_id not in c.prin.index:
        return None
    r = c.prin.loc[persona_id]
    if isinstance(r, pd.DataFrame):
        r = r.iloc[0]
    d = r.to_dict()
    d["persona_id"] = persona_id
    return d


def plantilla(c: Corte, club_d: str, liga_d: str, miembros: list[tuple[str, float]], excluir: set | None = None) -> pd.DataFrame:
    """Plantilla de destino: [(persona_id, presencia)] → filas con los rasgos de la utilidad y lo que necesita la
    simulación (L, uso natural traducido, GTI, estilo, RAPM). Los compañeros sin registro en t entran con el L de
    banquillo de la liga de destino y la marca sin_dato."""
    cfg = c.cfg
    pc = cfg["plantilla"]
    ids = SI.estilos_ids()
    filas = []
    excluir = excluir or set()
    for pid, pres in miembros:
        if pid in excluir:
            continue
        f = {"persona_id": pid, "presencia": float(pres)}
        r = jugador_insumos(c, pid)
        club_rec = c.por_club.get(club_d)
        rc = None
        if club_rec is not None:
            x = club_rec[club_rec["persona_id"] == pid]
            if len(x):
                rc = x.sort_values("min_total").iloc[-1]
        if r is None:
            f.update({"nombre": None, "pos3": None, "L": c.ref["banquillo"].get(liga_d, -0.5), "L_sd": pc["sd_sin_dato"],
                      "sin_dato": 1.0, "nuevo": 1.0, "lmin_club": 0.0, "lmin_fuera": 0.0, "edad": np.nan})
        else:
            f.update({k: r.get(k) for k in ("nombre", "pos3", "edad", "L", "L_sd", "gti", "z_usg", "liga", "sigma",
                                             "rapm_am", "usg_pct_obs", "rol_mas_probable", "min_pct")})
            Lr = _f(r.get("L"))
            f["L"] = Lr if np.isfinite(Lr) else c.ref["banquillo"].get(liga_d, -0.5)
            f["L_sd"] = _f(r.get("L_sd")) if np.isfinite(_f(r.get("L_sd"))) else pc["sd_sin_dato"]
            f["sin_dato"] = 0.0 if np.isfinite(Lr) else 1.0
            f["nuevo"] = 0.0 if rc is not None else 1.0
            mp = _f(rc["min_pct"]) if rc is not None else _f(r.get("min_pct"))
            lm = float(_logit(mp if np.isfinite(mp) else cfg["utilidad"]["min_previo_defecto"]))
            f["lmin_club"] = lm if rc is not None else 0.0
            f["lmin_fuera"] = 0.0 if rc is not None else lm
            f["_reg"] = r
            for i in ids:
                f[f"eu_{i}"] = r.get(f"eu_{i}")
        filas.append(f)
    p = pd.DataFrame(filas)
    if p.empty:
        return p
    p["edad_c"] = ((pd.to_numeric(p["edad"], errors="coerce") - 27) / 5).fillna(0)
    p["edad_c2"] = p["edad_c"] ** 2
    p = encajes(c, p, liga_d)
    return p


def encajes(c: Corte, p: pd.DataFrame, liga_d: str, team_eu: str | None = None) -> pd.DataFrame:
    """Encaje posicional (hueco de minutos de su posición frente al reparto típico de la liga, sin él) y de estilo
    (Σ_k p_ik·hueco_k: lo que le falta a la plantilla, sin él, frente a la composición típica de los equipos de su estilo)."""
    ids = SI.estilos_ids()
    pc = [f"eu_{i}" for i in ids]
    w = np.exp(np.clip(p["lmin_club"].fillna(0) + p["lmin_fuera"].fillna(0), -6, 6)).to_numpy(float)
    w = w * (1 + 0.5 * np.tanh(p["L"].fillna(0).to_numpy(float)))
    tipico = c.ref["pos"].get(liga_d, {"E": 0.45, "A": 0.2, "I": 0.35})
    pos = p["pos3"].to_numpy(object)
    enc = np.zeros(len(p))
    tot = w.sum()
    for i in range(len(p)):
        if not isinstance(pos[i], str):
            continue
        sin = tot - w[i]
        cuota = (w[(pos == pos[i])].sum() - w[i]) / sin if sin > 0 else 0
        enc[i] = tipico.get(pos[i], 0.3) - cuota
    p["encaje_pos"] = enc
    for col in pc:
        if col not in p:
            p[col] = np.nan
    P = p[pc].to_numpy(float)
    ok = np.isfinite(P).all(1)
    obj = np.array(c.ref["estilo_objetivo"].get(team_eu, c.ref["estilo_objetivo"].get("_todos", [1 / 6] * 6)), float)
    est = np.zeros(len(p))
    if ok.any():
        W = w * ok
        S = (np.nan_to_num(P) * W[:, None]).sum(0)
        for i in np.where(ok)[0]:
            sw = W.sum() - W[i]
            comp = (S - P[i] * W[i]) / sw if sw > 0 else obj
            est[i] = float(P[i] @ (obj - comp))
    p["encaje_estilo"] = est
    return p


def utilidad(c: Corte, p: pd.DataFrame) -> np.ndarray:
    w = c.w_util
    return sum(float(w.get(k, 0.0)) * pd.to_numeric(p[k], errors="coerce").fillna(0).to_numpy(float)
               for k in RASGOS_UTIL if k in p)


def tendencia(c: Corte, entrenador: str | None, liga: str) -> tuple[float, float, np.ndarray]:
    """(rotación media, sd, curva de reparto por rango) del entrenador (contraída hacia su liga) o de la liga."""
    te = c.mod["tendencias"]
    idx = te.set_index("entrenador_id")
    fila = None
    if isinstance(entrenador, str) and entrenador in idx.index:
        fila = idx.loc[entrenador]
    if fila is None and f"__liga__:{liga}" in idx.index:
        fila = idx.loc[f"__liga__:{liga}"]
    if fila is None:
        return 9.0, 1.0, np.linspace(1, 0.2, 12)
    if isinstance(fila, pd.DataFrame):
        fila = fila.iloc[0]
    curva = np.array([fila.get(f"cuota_r{k}_contraido", np.nan) for k in range(1, 13)], float)
    curva = np.where(np.isfinite(curva), curva, 0.0)
    extra = float(c.calib.get("rotacion_extra", 1.0))
    f_sd = float(c.calib.get("rotacion_sd_factor", 1.0))
    return float(fila["rotacion_contraido"]) + extra, f_sd * float(fila.get("rotacion_sd", 1.0) or 1.0), curva


def entrenador_equipo(c: Corte, liga: str, team_id: str, eq_dest: pd.DataFrame | None = None) -> str | None:
    e = eq_dest if eq_dest is not None else c.eq
    x = e[(e["liga"] == liga) & (e["team_id"].astype(str) == str(team_id))]
    if len(x) and isinstance(x["entrenador"].iloc[0], str):
        return x["entrenador"].iloc[0]
    return None


# =============================================================================================== simulación
def _uso_natural(c: Corte, fila: dict, liga_d: str) -> tuple[float, float]:
    """USG% y TS% esperados del jugador en la liga de destino (traducción a su media)."""
    if fila is None:
        return np.nan, np.nan
    t = traducir(c, fila, liga_d, ["usg_pct", "ts_pct"])
    return float(t.get("usg_pct", np.nan)), float(t.get("ts_pct", np.nan))


def _gti_proyectado(gti0, usg_nuevo, usg0, ref_d, ref_o, peso):
    z1 = (usg_nuevo - ref_d[0]) / ref_d[1]
    z0 = (usg0 - ref_o[0]) / ref_o[1]
    return gti0 + peso * (z1 - z0)


def simular(c: Corte, persona_id: str, liga_d: str, team_d: str, miembros: list[tuple[str, float]],
            entrenador: str | None = None, ritmo: float | None = None, team_eu: str | None = None,
            team_eu_probs: list | None = None, n_sim: int | None = None, semilla: int | None = None,
            registro: dict | None = None, detalle: bool = True, adaptacion_ruta=None, sin_adaptacion: bool = False,
            club_t: str | None = None) -> dict:
    """Simula el fichaje de `persona_id` (insumos de la temporada c.temp) por el club (liga_d, team_d) en t+1, con la
    plantilla `miembros` [(persona_id, presencia)] (sin el fichaje). `club_t` = clave del mismo club en la temporada
    base (para saber quién ya estaba y con cuántos minutos); por defecto, el de (liga_d, team_d) en t.
    Devuelve un dict con todas las salidas (semilla determinista por jugador-club)."""
    from . import adaptacion as AD
    from . import reemplazo as RE
    cfg = c.cfg
    n_sim = int(n_sim or cfg["simulaciones"])
    semilla = int(cfg["semilla"] if semilla is None else semilla)
    rng = np.random.default_rng([semilla, zlib.crc32(f"{persona_id}|{liga_d}|{team_d}".encode())])
    fila = jugador_insumos(c, persona_id, registro)
    if fila is None:
        return {"error": "sin insumos del jugador en la temporada base"}
    club_d = club_t or _club_clave(c, liga_d, team_d)
    gm = minutos_partido(liga_d)
    total = 5 * gm
    mets = list(cfg["produccion"]["metricas"])
    # ---------------------------------------------------------------- 1. nivel latente traducido (Monte Carlo)
    z1, z2 = rng.standard_normal(n_sim), rng.standard_normal(n_sim)
    tr = traducir(c, fila, liga_d, mets + ["rapm"], z1, z2, rng, n_sim)
    tr0 = traducir(c, fila, liga_d, mets + ["rapm"])
    L0 = _f(fila.get("L")) if np.isfinite(_f(fila.get("L"))) else c.ref["banquillo"].get(liga_d, -0.5)
    Lsd = _f(fila.get("L_sd")) if np.isfinite(_f(fila.get("L_sd"))) else 0.4
    L_s = L0 + Lsd * z1
    # ---------------------------------------------------------------- 2. adaptación (prior + curva)
    lo = fila.get("liga")
    grupo = AD.grupo_nacionalidad(fila.get("nacionalidad"), lo, liga_d)
    pos3 = fila.get("pos3") if isinstance(fila.get("pos3"), str) else "A"
    G = int(cfg["adaptacion"]["partidos_temporada"].get(liga_d, cfg["adaptacion"]["partidos_temporada"]["defecto"]))
    priors = {}
    for mp in set(ADAPT_METRICA.values()) | {"L"}:
        try:
            pr = AD.prior(lo, liga_d, grupo, pos3, mp, ruta=adaptacion_ruta) if not sin_adaptacion else AD._defecto("desactivado")
        except Exception:  # noqa: BLE001
            pr = {"delta_media": 0.0, "delta_sd": cfg["adaptacion"]["sd_sin_prior"], "kappa_media": np.nan,
                  "kappa_sd": np.nan, "n": 0, "nivel_fallback": "error"}
        if sin_adaptacion:
            pr = {**pr, "delta_media": 0.0, "delta_sd": 0.0}
        priors[mp] = pr
    g_juega = np.arange(G)
    fact = {}
    for mp, pr in priors.items():
        d_s = pr["delta_media"] + pr["delta_sd"] * rng.standard_normal(n_sim)
        k_s = np.abs(pr["kappa_media"] + (pr["kappa_sd"] if np.isfinite(pr["kappa_sd"]) else 0) * rng.standard_normal(n_sim)) \
            if np.isfinite(pr["kappa_media"]) else np.full(n_sim, np.nan)
        Fm = AD.curva(g_juega[None, :], d_s[:, None], k_s[:, None])
        fact[mp] = {"temporada": Fm.mean(1), "primeros": Fm[:, :int(cfg["adaptacion"]["primeros_partidos"])].mean(1),
                    "curva": Fm}
    # ΔL por adaptación: cociente relativo sobre las métricas de nivel → desplazamiento de L
    kL = _k_nivel(fila)
    L_eff = L_s + (fact["L"]["temporada"] - 1) * kL
    # ---------------------------------------------------------------- 3. plantilla, utilidad y minutos endógenos
    P = plantilla(c, club_d, liga_d, [m for m in miembros if m[0] != persona_id] + [(persona_id, 1.0)])
    # el fichaje puede no estar en el registro principal que se pidió (registro explícito)
    i_f = int(np.where(P["persona_id"].to_numpy() == persona_id)[0][-1])
    if registro is not None:
        P.loc[i_f, ["L", "L_sd", "pos3", "edad"]] = [L0, Lsd, fila.get("pos3"), fila.get("edad")]
        lm = float(_logit(fila.get("min_pct", 0.25)))
        P.loc[i_f, ["lmin_club", "lmin_fuera", "nuevo", "sin_dato"]] = [0.0, lm, 1.0, 0.0]
    P = encajes(c, P, liga_d, team_eu)
    P = _recortar(P, cfg["plantilla"]["max_jugadores"], i_f)
    i_f = int(np.where(P["persona_id"].to_numpy() == persona_id)[0][-1])
    k_u = float(c.calib.get("escala_utilidad", 1.0))
    u = k_u * utilidad(c, P)
    U = np.repeat(u[None, :], n_sim, 0)
    U[:, i_f] += k_u * float(c.w_util.get("L", 0)) * (L_eff - L0)
    rot, rot_sd, curva = tendencia(c, entrenador, liga_d)
    rcfg = {**cargar("reemplazo"), "asignacion": {**cargar("reemplazo")["asignacion"], "temperatura": 1.0, "encaje_peso": 0.0}}
    pres = P["presencia"].to_numpy(float).copy()
    pres[i_f] = 1.0
    plant = pd.DataFrame({"player_id": P["persona_id"], "nivel": u, "pos3": P["pos3"]})
    _, M = RE.asignar_minutos(plant, total_min=total, minutos_partido=gm, rotacion_media=rot, rotacion_sd=rot_sd,
                              curva=curva, n_sim=n_sim, semilla=int(rng.integers(2 ** 31)), cfg=rcfg,
                              devolver_simulaciones=True, niveles_sim=U, presencia=pres)
    # sin el fichaje (para el impacto en el equipo)
    sin = np.arange(len(P)) != i_f
    n0 = max(200, n_sim // 2)
    if sin.sum() >= 5:
        _, M0 = RE.asignar_minutos(plant[sin].reset_index(drop=True), total_min=total, minutos_partido=gm,
                                   rotacion_media=rot, rotacion_sd=rot_sd, curva=curva, n_sim=n0,
                                   semilla=int(rng.integers(2 ** 31)), cfg=rcfg, devolver_simulaciones=True,
                                   presencia=pres[sin])
    else:
        M0 = None
    T5 = _top5(M)
    # minutos del fichaje: fuera de la rotación → minutos residuales de su liga (cuando juega)
    m_f = M[:, i_f].copy()
    resid = float(c.mod["min_rol"].get((liga_d, "RESIDUAL"), c.mod["min_rol_global"].get("RESIDUAL", 0.06))) * gm
    fuera_rot = m_f <= 0
    m_f[fuera_rot] = resid * (0.5 + rng.random(fuera_rot.sum()))
    # ---------------------------------------------------------------- 4. uso: suma fija y curva uso-eficiencia
    usg_nat = np.zeros(len(P))
    usg0 = np.zeros(len(P))
    ref_d = c.ref["uso"].get(liga_d, (20.0, 5.0))
    gti0 = np.full(len(P), np.nan)
    ref_o = []
    for i, r in P.iterrows():
        rr = r.get("_reg")
        if i == i_f:
            usg_nat[i] = _f(tr0.get("usg_pct"))
            usg0[i] = _f(fila.get("usg_pct_obs"))
            gti0[i] = _f(fila.get("gti"))
            ref_o.append(c.ref["uso"].get(lo, ref_d))
            continue
        if isinstance(rr, dict):
            usg_nat[i] = _uso_natural(c, rr, liga_d)[0]
            usg0[i] = _f(rr.get("usg_pct_obs"))
            gti0[i] = _f(rr.get("gti"))
            ref_o.append(c.ref["uso"].get(rr.get("liga"), ref_d))
        else:
            usg_nat[i], usg0[i] = np.nan, np.nan
            ref_o.append(ref_d)
    usg_nat = np.clip(np.where(np.isfinite(usg_nat), usg_nat, ref_d[0] - 0.5 * ref_d[1]), 5, 45)
    usg0 = np.where(np.isfinite(usg0), usg0, usg_nat)
    # USG del fichaje en cada simulación (su traducción con incertidumbre × adaptación)
    usg_f_s = np.asarray(tr.get("usg_pct", np.full(n_sim, usg_nat[i_f])), float) * fact["usg_pct"]["temporada"]
    USG = np.repeat(usg_nat[None, :], n_sim, 0)
    USG[:, i_f] = np.where(np.isfinite(usg_f_s), usg_f_s, usg_nat[i_f])
    objetivo = float(cfg["produccion"]["usg_medio_pista"]) * M.sum(1)
    actual = (M * USG).sum(1)
    f_uso = np.where(actual > 0, objetivo / actual, 1.0)
    f_uso = 1 + float(cfg["produccion"]["amortiguar_uso"]) * (f_uso - 1)
    USG2 = USG * f_uso[:, None]
    d_usg = USG2[:, i_f] - USG[:, i_f]
    beta_m, beta_sd = c.mod["beta_uso"].get(pos3, c.mod["beta_uso"].get("todos", (-0.08, 0.1)))
    beta_s = beta_m + beta_sd * rng.standard_normal(n_sim)
    # GO-TO-GUY: GTI proyectado y top-2 del equipo
    gc = cfg["rol_go_to_guy"]
    GTI = np.full((n_sim, len(P)), -np.inf)
    for i in range(len(P)):
        if np.isfinite(gti0[i]):
            GTI[:, i] = _gti_proyectado(gti0[i], USG2[:, i], usg0[i], ref_d, ref_o[i], float(gc["peso_uso"]))
    elig = (M / gm) >= 0.25
    GTIe = np.where(elig, GTI, -np.inf)
    rango = (-GTIe).argsort(1).argsort(1)
    es_gtg = (rango < int(gc["top_equipo"])) & (GTI >= float(gc["umbral_gti"])) & ((M / gm) >= float(gc["min_minutos_pct"]))
    # ---------------------------------------------------------------- 5. calidad de compañeros
    Lp = P["L"].to_numpy(float)
    Wm = M.copy()
    Wm[:, i_f] = 0
    Lbar = (Wm * Lp[None, :]).sum(1) / np.maximum(Wm.sum(1), 1e-9)
    ctx_o = _ctx_origen(c, fila)
    dL = Lbar - ctx_o if np.isfinite(ctx_o) else np.zeros(n_sim)
    b_ts, b_ts_sd = c.mod["companeros"].get("ts_pct", (0.0, 0.0))
    b_s = b_ts + b_ts_sd * rng.standard_normal(n_sim)
    # ---------------------------------------------------------------- producción (pasos 2, 4, 5, 7, 8)
    prod = {}
    for m in mets:
        v = np.asarray(tr.get(m, np.full(n_sim, np.nan)), float)
        am = ADAPT_METRICA.get(m)
        if am:
            v = v * fact[am]["temporada"]
        prod[m] = v
    ts_b = prod.get("ts_pct", np.full(n_sim, np.nan))
    usg_b = USG[:, i_f]
    ts2 = np.clip(ts_b + beta_s * d_usg + b_s * dL, cfg["produccion"]["ts_min"], cfg["produccion"]["ts_max"])
    prod["ts_pct"] = ts2
    prod["usg_pct"] = USG2[:, i_f]
    if "pts_p100" in prod:
        with np.errstate(invalid="ignore", divide="ignore"):
            prod["pts_p100"] = prod["pts_p100"] * (USG2[:, i_f] / usg_b) * (ts2 / ts_b)
    ritmo = ritmo if ritmo is not None and np.isfinite(ritmo) else c.ref["ritmo"].get(liga_d, 72.0)
    disp = float(c.calib.get("disponibilidad", 0.85))
    poss = m_f / gm * ritmo * G * disp
    sig = fila.get("sigma")
    sig = sig if sig is not None and np.isfinite(sig) else c.ref["sigma"].get(liga_d, 12.0)
    obs = {}
    for m in mets:
        v = prod[m]
        if m == "pts_p100" and np.isfinite(sig):
            obs[m] = np.clip(v + sig * np.sqrt(30.0 / np.maximum(poss, 5)) * rng.standard_normal(n_sim), 0, None)
        else:
            k = c.trad["constantes"].get(m, {})
            ex = poss * (USG2[:, i_f] / 100 if k.get("exposicion") in ("tsa", "fga", "fg2a", "fg3a") else 1.0)
            obs[m] = ruido_muestreo(c, m, liga_d, v, ex, rng) if m in c.trad["constantes"] else v
    # ---------------------------------------------------------------- roles
    mp_s = m_f / gm
    gs = T5[:, i_f].astype(float)
    rol_s = clasificar(mp_s, gs, np.full(n_sim, np.nan), es_gtg[:, i_f], cargar("roles"))
    p_rol = {r: float(np.mean(rol_s == r)) for r in ROLES}
    # ---------------------------------------------------------------- salida
    q = lambda v, a: float(np.nanquantile(v, a)) if np.isfinite(v).any() else None  # noqa: E731
    lv = [float(x) for x in cfg["intervalos"]]

    def resumen(v):
        v = np.asarray(v, float)
        d = {"media": float(np.nanmean(v)) if np.isfinite(v).any() else None, "mediana": q(v, 0.5)}
        for a in lv:
            d[f"lo{int(a * 100)}"], d[f"hi{int(a * 100)}"] = q(v, (1 - a) / 2), q(v, 1 - (1 - a) / 2)
        return d

    res = {"persona_id": persona_id, "nombre": fila.get("nombre"), "liga_origen": lo, "team_origen": fila.get("team_id"),
           "temporada_base": c.temp, "liga_destino": liga_d, "team_destino": str(team_d), "grupo_nacionalidad": grupo,
           "pos3": pos3, "n_sim": n_sim, "semilla": semilla, "fuente": c.fuente, "version": cfg["version"],
           "roles": p_rol, "rol_esperado": max(p_rol, key=p_rol.get),
           "indice_rol": float(sum(IDX_ROL[r] * p for r, p in p_rol.items())),
           "minutos": resumen(m_f), "min_pct": resumen(mp_s), "p_titular": float(gs.mean()),
           "produccion_p100": {m: resumen(obs[m]) for m in mets},
           "produccion_esperada": {m: float(np.nanmean(prod[m])) for m in mets},
           "traduccion_media": {m: (float(tr0[m]) if np.isfinite(tr0.get(m, np.nan)) else None) for m in mets},
           "por_partido": _por_partido(cfg, obs, m_f, gm, ritmo, resumen),
           "L": float(L0), "L_sd": float(Lsd), "L_efectivo": float(np.mean(L_eff)),
           "uso": {"natural": float(usg_nat[i_f]), "factor_equipo": float(np.mean(f_uso)), "d_usg": float(np.mean(d_usg))},
           "companeros": {"L_bar": float(np.mean(Lbar)), "L_origen": ctx_o if np.isfinite(ctx_o) else None,
                          "efecto_ts": float(np.mean(b_s * dL))},
           "ritmo_destino": float(ritmo)}
    # adaptación
    pa = priors.get("pts_p100", priors["L"])
    res["adaptacion"] = {"prior": {k: _num(v) for k, v in pa.items()}, "prior_L": {k: _num(v) for k, v in priors["L"].items()},
                         "adapt_pct_temporada": resumen(100 * fact["pts_p100"]["temporada"]),
                         "adapt_pct_primeros": resumen(100 * fact["pts_p100"]["primeros"]),
                         "primeros_partidos": int(cfg["adaptacion"]["primeros_partidos"]), "partidos_temporada": G,
                         "curva": [[int(g), float(np.mean(fact["pts_p100"]["curva"][:, g])),
                                    float(np.quantile(fact["pts_p100"]["curva"][:, g], 0.05)),
                                    float(np.quantile(fact["pts_p100"]["curva"][:, g], 0.95))]
                                   for g in range(0, min(G, 40))],
                         "partidos_50": AD.partidos_hasta(0.5, pa["kappa_media"]) if np.isfinite(pa["kappa_media"]) else None,
                         "partidos_90": AD.partidos_hasta(0.9, pa["kappa_media"]) if np.isfinite(pa["kappa_media"]) else None}
    # estilo, complementariedad y entropías
    res["estilo"] = estilo_y_complementariedad(c, P, i_f, M, M0, usg_nat, team_eu, team_eu_probs)
    # impacto en el equipo y quintetos
    res["equipo"] = impacto_equipo(c, P, i_f, M, M0, liga_d, total)
    # componentes del Fit (crudos) e índice
    res["componentes_crudos"] = componentes(c, res, fila, P, i_f, M, liga_d)
    res["fit"] = indice_fit(c, res["componentes_crudos"])
    res["avisos"] = avisos(c, res, fila, liga_d)
    if detalle:
        res["plantilla"] = _plantilla_salida(P, M, i_f, gm, rol_s)
    return res


def _num(v):
    try:
        v = float(v)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return v


def _club_clave(c: Corte, liga: str, team: str) -> str:
    x = c.eq[(c.eq["liga"] == liga) & (c.eq["team_id"].astype(str) == str(team))]
    return x["club"].iloc[0] if len(x) else f"{liga}|{team}"


def _recortar(P: pd.DataFrame, nmax: int, i_f: int) -> pd.DataFrame:
    if len(P) <= nmax:
        return P.reset_index(drop=True)
    orden = (P["presencia"].fillna(0) * 10 + P["lmin_club"].fillna(0) + P["lmin_fuera"].fillna(0)).to_numpy(float).copy()
    orden[i_f] = np.inf
    keep = np.argsort(-orden)[:nmax]
    return P.iloc[sorted(keep)].reset_index(drop=True)


def _top5(M: np.ndarray) -> np.ndarray:
    T = np.zeros(M.shape, bool)
    idx = np.argsort(-M, axis=1)[:, :5]
    np.put_along_axis(T, idx, True, axis=1)
    T &= M > 0
    return T


def _k_nivel(fila: dict) -> float:
    """dL/d(factor): ΔL ≈ (f − 1)·media_m(v_m/sd_m) sobre las métricas de nivel (vara EuroLeague)."""
    from bbmodel.contexto import NIVEL
    esc = SI.escala_nivel()
    v = [abs(float(fila.get(f"{m}_am", np.nan))) / esc[m][1] for m in NIVEL if np.isfinite(fila.get(f"{m}_am", np.nan))]
    return float(np.mean(v)) if v else 3.0


def _ctx_origen(c: Corte, fila: dict) -> float:
    """Calidad de los compañeros en origen: L medio de su equipo ponderado por minutos, sin él (misma definición que
    L̄ en destino)."""
    if not hasattr(c, "_ctx_eq"):
        g = c.reg.dropna(subset=["L"])
        c._ctx_eq = g.assign(wl=g["L"] * g["min_total"]).groupby(["liga", "team_id"])[["wl", "min_total"]].sum()
    k = (fila.get("liga"), fila.get("team_id"))
    if k not in c._ctx_eq.index:
        return np.nan
    wl, mt = c._ctx_eq.loc[k]
    Lf, mf = _f(fila.get("L")), _f(fila.get("min_total"))
    if np.isfinite(Lf) and np.isfinite(mf):
        wl, mt = wl - Lf * mf, mt - mf
    return float(wl / mt) if mt > 0 else np.nan


def _por_partido(cfg, obs, m_f, gm, ritmo, resumen) -> dict:
    poss_pg = m_f / gm * ritmo
    out = {"posesiones": resumen(poss_pg)}
    for k, m in cfg["produccion"]["por_partido"].items():
        ms = m if isinstance(m, list) else [m]
        if not all(x in obs for x in ms):
            continue
        v = sum(obs[x] for x in ms) * poss_pg / 100
        out[k] = resumen(v)
    return out


def estilo_y_complementariedad(c: Corte, P: pd.DataFrame, i_f: int, M, M0, usg_nat, team_eu, team_eu_probs) -> dict:
    ids = SI.estilos_ids()
    pc = [f"eu_{i}" for i in ids]
    pf = P.loc[i_f, pc].to_numpy(float) if all(x in P for x in pc) else np.full(len(ids), np.nan)
    wm = M.mean(0)
    Pm = P[pc].to_numpy(float)
    ok = np.isfinite(Pm).all(1)
    comp_con = (np.nan_to_num(Pm[ok]) * wm[ok, None]).sum(0) / max(wm[ok].sum(), 1e-9) if ok.any() else np.full(len(ids), np.nan)
    sin = np.arange(len(P)) != i_f
    if M0 is not None and ok[sin].any():
        w0 = M0.mean(0)
        P0 = Pm[sin]
        ok0 = ok[sin]
        comp_sin = (np.nan_to_num(P0[ok0]) * w0[ok0, None]).sum(0) / max(w0[ok0].sum(), 1e-9)
    else:
        comp_sin = comp_con
    tp = np.asarray(team_eu_probs, float) if team_eu_probs is not None else comp_sin
    obj = np.array(c.ref["estilo_objetivo"].get(team_eu, c.ref["estilo_objetivo"].get("_todos", [1 / 6] * 6)), float)
    dist = _js(pf, tp) if np.isfinite(pf).all() else np.nan
    hueco = obj - comp_sin
    compl = float(pf @ hueco) if np.isfinite(pf).all() else np.nan
    # entropía del reparto de uso (con y sin el fichaje) y de la red de pases (cuotas de asistencias ∝ min·AST%)
    h_con = _entropia_norm(wm * usg_nat)
    h_sin = _entropia_norm(M0.mean(0) * usg_nat[sin]) if M0 is not None else h_con
    ast = np.array([((r.get("_reg") or {}).get("ast_pct_obs", np.nan) if isinstance(r.get("_reg"), dict) else np.nan)
                    for _, r in P.iterrows()], float)
    ast = np.where(np.isfinite(ast), ast, np.nanmedian(ast) if np.isfinite(ast).any() else 10.0)
    hp_con = _entropia_norm(wm * ast)
    hp_sin = _entropia_norm((M0.mean(0) if M0 is not None else wm[sin]) * ast[sin]) if sin.any() else hp_con
    return {"jugador": _lista(pf), "equipo": _lista(tp), "composicion_sin": _lista(comp_sin), "composicion_con": _lista(comp_con),
            "objetivo": _lista(obj), "distancia_js": _num(dist), "complementariedad": _num(compl),
            "hueco_cubierto": ids[int(np.nanargmax(np.where(np.isfinite(pf), pf, -1) * hueco))] if np.isfinite(pf).all() else None,
            "d_entropia_uso": float(h_con - h_sin), "d_entropia_pases": float(hp_con - hp_sin),
            "entropia_uso": [float(h_sin), float(h_con)], "entropia_pases": [float(hp_sin), float(hp_con)],
            "estilo_equipo": team_eu, "ids": ids}


def _lista(v, d=4):
    return [None if not np.isfinite(x) else round(float(x), d) for x in np.asarray(v, float)]


def _rapm_destino(c: Corte, P: pd.DataFrame, i: int, liga_d: str) -> float:
    r = P.loc[i, "_reg"] if "_reg" in P else None
    if not isinstance(r, dict):
        return 0.0
    t = traducir(c, r, liga_d, ["rapm"])
    v = t.get("rapm", np.nan)
    if not np.isfinite(v):
        v = r.get("rapm_am", np.nan)
    return float(v) if np.isfinite(v) else 0.0


def impacto_equipo(c: Corte, P: pd.DataFrame, i_f: int, M, M0, liga_d: str, total: float) -> dict:
    rap = np.array([_rapm_destino(c, P, i, liga_d) for i in range(len(P))])
    net_con = 5 * (M * rap[None, :]).sum(1) / total
    sin = np.arange(len(P)) != i_f
    net_sin = 5 * (M0 * rap[sin][None, :]).sum(1) / total if M0 is not None else np.full(1, np.nan)
    # quintetos más probables (5 de más minutos en cada simulación)
    idx = np.sort(np.argsort(-M, axis=1)[:, :5], axis=1)
    cnt = Counter(map(tuple, idx))
    tops = []
    for q5, n in cnt.most_common(3):
        tops.append({"jugadores": [str(P.loc[i, "persona_id"]) for i in q5],
                     "nombres": [P.loc[i, "nombre"] if isinstance(P.loc[i, "nombre"], str) else "s/d" for i in q5],
                     "prob": n / len(idx), "con_fichaje": bool(i_f in q5), "net": float(rap[list(q5)].sum())})
    return {"net_con": float(np.mean(net_con)), "net_sin": float(np.nanmean(net_sin)),
            "d_net": float(np.mean(net_con) - np.nanmean(net_sin)),
            "d_net_lo90": float(np.quantile(net_con, 0.05) - np.nanmean(net_sin)),
            "d_net_hi90": float(np.quantile(net_con, 0.95) - np.nanmean(net_sin)),
            "rapm_fichaje": float(rap[i_f]), "quintetos": tops, "unidad": "pts/100 (escala de la liga de destino)"}


# =============================================================================================== Fit
COMPONENTES = {"nivel": ["nivel"], "rol": ["rol"], "estilo": ["estilo"],
               "complementariedad": ["complementariedad", "entropia"], "adaptacion": ["adaptacion"],
               "riesgo": ["volatilidad", "incertidumbre", "h_rol"]}


def componentes(c: Corte, res: dict, fila: dict, P: pd.DataFrame, i_f: int, M, liga_d: str) -> dict:
    """Rasgos crudos de cada componente del Fit (sin pesos)."""
    Lp = P["L"].to_numpy(float)
    w = M.mean(0).copy()
    w[i_f] = 0
    Lt = float((w * Lp).sum() / max(w.sum(), 1e-9))
    sig = fila.get("sigma")
    sig_ref = c.ref["sigma"].get(liga_d, np.nan)
    hr = fila.get("H_rol_post", fila.get("H_rol", np.nan))
    e = res["estilo"]
    return {"nivel": res["L_efectivo"] - Lt, "rol": res["indice_rol"],
            "estilo": -(e["distancia_js"] if e["distancia_js"] is not None else 0.25),
            "complementariedad": e["complementariedad"] if e["complementariedad"] is not None else 0.0,
            "entropia": e["d_entropia_uso"] + e["d_entropia_pases"],
            "adaptacion": (res["adaptacion"]["adapt_pct_temporada"]["media"] or 100.0) - 100.0,
            "volatilidad": -((sig / sig_ref - 1) if sig is not None and np.isfinite(sig) and np.isfinite(sig_ref) else 0.0),
            "incertidumbre": -float(res["L_sd"]), "h_rol": -(float(hr) if hr is not None and np.isfinite(hr) else 1.2)}


def indice_fit(c: Corte, x: dict) -> dict:
    """Fit = b₀ + Σ_f w_f·(x_f − media_f)/sd_f; cada componente suma las contribuciones de sus rasgos (exacto).
    Pesos por regresión ridge del «éxito» real en los cortes de entrenamiento (bbfit.validacion.ajustar_fit)."""
    F = c.fit
    if not F:
        return {"total": None, "componentes": {k: None for k in COMPONENTES}, "nota": "sin pesos ajustados"}
    contrib = {}
    for f, v in x.items():
        if f not in F["w"]:
            continue
        sd = F["sd"][f] or 1.0
        contrib[f] = float(F["w"][f] * ((v if v is not None and np.isfinite(v) else F["media"][f]) - F["media"][f]) / sd)
    comp = {k: float(sum(contrib.get(f, 0.0) for f in fs)) for k, fs in COMPONENTES.items()}
    tot = float(F["b0"] + sum(comp.values()))
    return {"total": tot, "base": float(F["b0"]), "componentes": comp, "rasgos": contrib,
            "unidad": "DT del éxito (0,5·z minutos + 0,5·z nivel en la liga de destino)"}


def avisos(c: Corte, res: dict, fila: dict, liga_d: str) -> list[dict]:
    a = c.cfg["avisos"]
    out = []
    if (fila.get("min_total") or 0) < a["muestra_pequena_min"] or (fila.get("gp") or 0) < a["muestra_pequena_partidos"]:
        out.append({"tipo": "muestra_pequena", "texto": f"Muestra pequeña en origen ({int(fila.get('min_total') or 0)}' en "
                                                      f"{int(fila.get('gp') or 0)} partidos)."})
    sdp = fila.get("pts_p100_thsd")
    lo = fila.get("liga")
    d_o = _nivel_liga(c, lo)
    d_d = _nivel_liga(c, liga_d)
    if np.isfinite(d_o) and np.isfinite(d_d) and abs(d_d - d_o) > a["distancia_liga_alta"]:
        out.append({"tipo": "liga_lejana", "texto": f"Salto de nivel grande entre ligas ({d_d - d_o:+.2f} DT)."})
    if sdp is not None and np.isfinite(sdp) and sdp > a["incertidumbre_alta_sd"] or res["L_sd"] > a["incertidumbre_alta_sd"]:
        out.append({"tipo": "incertidumbre_alta", "texto": "Incertidumbre alta en su nivel traducido."})
    ro = fila.get("rol_mas_probable")
    if isinstance(ro, str) and ro in IDX_ROL and abs(res["indice_rol"] - IDX_ROL[ro]) >= a["cambio_rol"]:
        out.append({"tipo": "cambio_rol", "texto": f"Rol muy distinto al de origen ({ro} → {res['rol_esperado']})."})
    sig, p80 = fila.get("sigma"), c.ref["sigma_p80"].get(liga_d, np.nan)
    if sig is not None and np.isfinite(sig) and np.isfinite(p80) and sig > p80:
        out.append({"tipo": "volatilidad_alta", "texto": "Rendimiento muy variable partido a partido (σ alta)."})
    nf = res["adaptacion"]["prior"].get("nivel_fallback")
    if nf in ("sin_datos", "error", "global") or (res["adaptacion"]["prior"].get("n") or 0) < 8:
        out.append({"tipo": "adaptacion_generica", "texto": "Adaptación estimada con poca información propia de ese cambio de liga."})
    return out


def _nivel_liga(c: Corte, liga) -> float:
    from bbmodel.contexto import NIVEL
    vals = []
    for m in NIVEL:
        d, _ = SI._nodo(c.trad["nodos"].get(m, {}), liga, c.temp) if isinstance(liga, str) else (np.nan, np.nan)
        if np.isfinite(d):
            vals.append(NIVEL[m] * d)
    return float(np.median(vals)) if vals else np.nan


def _plantilla_salida(P, M, i_f, gm, rol_s) -> list[dict]:
    out = []
    for i in range(len(P)):
        out.append({"persona_id": str(P.loc[i, "persona_id"]), "nombre": P.loc[i, "nombre"] if isinstance(P.loc[i, "nombre"], str) else None,
                    "pos3": P.loc[i, "pos3"] if isinstance(P.loc[i, "pos3"], str) else None,
                    "L": _num(P.loc[i, "L"]), "minutos": float(M[:, i].mean()), "fichaje": bool(i == i_f)})
    return sorted(out, key=lambda d: -d["minutos"])


# =============================================================================================== escenarios
def miembros_reales(roles_t1: pd.DataFrame, liga: str, team: str, min_pres: float) -> list[tuple[str, float]]:
    """Plantilla real de t+1 (sólo pertenencia y presencia: quién estuvo y en qué parte de la temporada)."""
    g = roles_t1[(roles_t1["liga"] == liga) & (roles_t1["team_id"].astype(str) == str(team))]
    g = g[g["presencia"] >= min_pres]
    return [(p, float(x)) for p, x in zip(g["persona_id"], g["presencia"])]


def miembros_actuales(c: Corte, club: str) -> list[tuple[str, float]]:
    """Plantilla de la temporada base (t) del club: los que jugaron en él, con su presencia."""
    g = c.por_club.get(club)
    if g is None:
        return []
    g = g.sort_values("min_total", ascending=False).drop_duplicates("persona_id")
    return [(p, float(x) if np.isfinite(x) else 1.0) for p, x in zip(g["persona_id"], g["presencia"])]


# =============================================================================================== CLI
def buscar_persona(c: Corte, texto: str) -> list[tuple[str, str, str]]:
    from .datos import _sin_acentos
    q = _sin_acentos(texto).split()
    r = c.reg[c.reg["principal"]]
    n = r["nombre"].fillna("").map(_sin_acentos)
    ok = n.map(lambda s: all(t in s for t in q))
    x = r[ok].sort_values("min_total", ascending=False)
    return list(zip(x["persona_id"], x["nombre"], x["liga"] + " " + x["team_id"].astype(str)))


def buscar_club(c: Corte, texto: str, eq: pd.DataFrame | None = None) -> list[tuple[str, str, str]]:
    from .datos import _sin_acentos
    e = eq if eq is not None else c.eq
    q = _sin_acentos(texto).split()
    n = e["equipo"].fillna("").map(_sin_acentos)
    x = e[n.map(lambda s: all(t in s for t in q))]
    return list(zip(x["liga"], x["team_id"].astype(str), x["equipo"]))


def simular_cli(jugador: str, club: str, temporada: str | None = None, liga: str | None = None, bajas: list[str] | None = None,
                n_sim: int | None = None, salida: str | None = None) -> dict:
    """python -m bbfit simular --jugador «nombre» --club «nombre» [--liga acb] [--temporada 2025-26] [--bajas …]"""
    cfg = cfg_sim()
    temp = temporada or cfg["exportar"]["temporada_base"]
    c = cargar_corte(temp)
    pj = buscar_persona(c, jugador)
    if not pj:
        raise SystemExit(f"jugador no encontrado en {temp}: {jugador}")
    persona = pj[0][0]
    # club de destino: su plantilla más reciente (t+1 si existe, si no t)
    t1 = SI.siguiente(temp)
    roles = SI._leer_roles_temporada()
    eq_t1 = roles[roles["temporada"] == t1][["liga", "team_id"]].drop_duplicates()
    cand = [x for x in buscar_club(c, club) if liga is None or x[0] == liga]
    if not cand:
        raise SystemExit(f"club no encontrado: {club}")
    liga_d, team_d, nombre_club = cand[0]
    club_k = _club_clave(c, liga_d, team_d)
    r1 = roles[(roles["temporada"] == t1) & (roles["liga"] == liga_d) & (roles["team_id"] == team_d)]
    if len(r1):
        miembros = miembros_reales(roles[roles["temporada"] == t1], liga_d, team_d, cfg["plantilla"]["minimo_presencia"])
        escenario = f"plantilla {t1}"
    else:
        miembros = miembros_actuales(c, club_k)
        escenario = f"plantilla {temp}"
    bajas_ids = set()
    for b in bajas or []:
        bb = buscar_persona(c, b)
        if bb:
            bajas_ids.add(bb[0][0])
    miembros = [m for m in miembros if m[0] not in bajas_ids]
    e = c.eq[(c.eq["liga"] == liga_d) & (c.eq["team_id"] == team_d)]
    ent = entrenador_equipo(c, liga_d, team_d)
    r = simular(c, persona, liga_d, team_d, miembros, entrenador=ent,
                ritmo=float(e["team_pace"].iloc[0]) if len(e) and np.isfinite(e["team_pace"].iloc[0]) else None,
                team_eu=e["eu"].iloc[0] if len(e) else None,
                team_eu_probs=e[[f"eu_{i}" for i in SI.estilos_ids()]].iloc[0].to_numpy(float).tolist() if len(e) else None,
                n_sim=n_sim)
    r["club_destino"], r["escenario"] = nombre_club, escenario
    if salida:
        Path(salida).write_text(json.dumps(r, ensure_ascii=False, indent=1, default=_num), encoding="utf-8")
    return r


def texto_resumen(r: dict) -> str:
    if "error" in r:
        return r["error"]
    m = r["minutos"]
    p = r["produccion_p100"]["pts_p100"]
    roles = " · ".join(f"{k} {100 * v:.0f}%" for k, v in r["roles"].items())
    fit = r["fit"]
    comp = ", ".join(f"{k} {v:+.2f}" for k, v in (fit.get("componentes") or {}).items() if v is not None)
    av = "; ".join(a["texto"] for a in r["avisos"]) or "ninguno"
    ad = r["adaptacion"]
    return (f"{r['nombre']} → {r.get('club_destino', r['team_destino'])} ({r['liga_destino']}, {r.get('escenario', '')})\n"
            f"  Roles: {roles}\n"
            f"  Minutos por partido: {m['media']:.1f} (50 %: {m['lo50']:.1f}–{m['hi50']:.1f}; 90 %: {m['lo90']:.1f}–{m['hi90']:.1f})\n"
            f"  Puntos/100: {p['media']:.1f} (50 %: {p['lo50']:.1f}–{p['hi50']:.1f}; 90 %: {p['lo90']:.1f}–{p['hi90']:.1f})\n"
            f"  Puntos por partido: {r['por_partido']['pts']['media']:.1f} · ADAPT% temporada "
            f"{ad['adapt_pct_temporada']['media']:.1f} (primeros {ad['primeros_partidos']}: {ad['adapt_pct_primeros']['media']:.1f})\n"
            f"  Fit: {fit['total'] if fit['total'] is None else round(fit['total'], 2)} [{comp}]\n"
            f"  Impacto en el Net del equipo: {r['equipo']['d_net']:+.2f} pts/100\n"
            f"  Avisos: {av}")
