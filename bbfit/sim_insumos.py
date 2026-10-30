"""Fase 8 — insumos del simulador de encaje v2 (bbfit/simulador.py) por «corte» temporal.

Un corte t reúne todo lo que el simulador necesita para simular un fichaje t → t+1 SIN mirar t+1:

* `jugadores`  un registro por persona en la temporada t (su equipo principal): capacidad latente θ (DT de la vara
               EuroLeague) y su desviación para cada métrica de producción, índice de nivel L, minutos y rol de
               origen, uso, σ_i (volatilidad), H_rol, pertenencias de estilo unificado, RAPM-EL, nacionalidad…
* `equipos`    equipo-temporada t: plantilla (personas y presencia), ritmo, estilo unificado, entropías, Net,
               entrenador principal.
* `traduccion` constantes de la normalización amortiguada (por métrica): nivel δ de cada competición-temporada y su
               varianza, escala s, ψ, deriva por edad, μ/τ por liga-temporada-posición y σ² de ruido.
* `modelos`    piezas ajustadas con datos ≤ t: tendencias de entrenador, β uso-eficiencia por pos3, efecto de la
               calidad de compañeros.

Dos fuentes de la capacidad θ (configs/simulation.yaml → normalizacion):
* «AB»  (por defecto, producción): `<m>_am` del dataset normalizado (A+B amortiguado, vara EuroLeague 2025-26) con su
        intervalo `_am_lo/_hi`; θ = (T(v) − μ_EL,pos)/τ_EL,pos. Ajustado con TODAS las temporadas (fuga en el examen).
* «A_corte» (examen sin fuga, cortes 2023 y 2024): algoritmo A ajustado con temporadas ≤ t (caché de la validación de la
        fase 2, experimentos/cache_normalizacion/A_hasta_<año>.pkl) + amortiguación reajustada con ≤ t.
* «A»   capacidad amortiguada del A con todas las temporadas (`_am_a`, `_am_sd`): sirve para medir la fuga
        comparándola con «A_corte» en los mismos cortes.
* «V31» (simulador v3, configs/simulation_v3.yaml): igual que «AB» pero leyendo el dataset normalizado v3.1
        (combinación v2 + CVAE corregida; carpeta en normalizacion.dir) y con las constantes de traducción a la liga
        de destino de la v3.1 (traduccion_v31: sustituto lineal ajustado sobre el propio dataset).
* «V31A» (diagnóstico): θ de la v3.1 con las constantes de la normalización amortiguada (lo que hacía la v3.0).
Caché: experimentos/cache_simulador/ (no versionado; se regenera).
"""
from __future__ import annotations

import json
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import datos as D
from .config import DIR_MOD, RAIZ, cargar
from .roles import ROLES

# caché propia por versión del simulador (v2: cache_simulador; v3: cache_simulador_v3): las dos usan los mismos nombres
# de fichero por corte y fuente, y la v3 lee otros insumos (dataset v3.1, constantes v3.1, datos al 29-10)
_CARPETA = cargar("simulation").get("carpeta", "v2")
DIR_CACHE = RAIZ / "experimentos" / ("cache_simulador" if _CARPETA == "v2" else f"cache_simulador_{_CARPETA}")
DIR_NORM = DIR_MOD / "normalizado"
DIR_AM = DIR_MOD / "normalizacion_amortiguada"


def cfg_sim() -> dict:
    return cargar("simulation")


def anio(temp: str) -> int:
    return int(str(temp)[:4])


def temp_de(a: int) -> str:
    return f"{a}-{str(a + 1)[-2:]}"


def siguiente(temp: str) -> str:
    return temp_de(anio(temp) + 1)


def _tramo_edad(edad) -> str:
    from bbmodel.enlace import tramo_edad
    return tramo_edad(edad)


# =============================================================================================== traducción
def constantes_A(params: dict, metricas: list[str]) -> dict:
    """Constantes del algoritmo A por métrica (escala s, ψ, deriva, μ/τ de liga-temporada-posición, σ²)."""
    from bbmodel.metricas import CATALOGO
    out = {}
    for m in metricas:
        if m not in params["metricas"]:
            continue
        p = params["metricas"][m]
        e, s1 = p["enlace"], p["suerte"]
        out[m] = {"transf": CATALOGO[m].transf, "sentido": int(CATALOGO[m].sentido),
                  "exposicion": CATALOGO[m].exposicion,
                  "s": {k: float(v) for k, v in e["s"].items()}, "psi": {k: float(v) for k, v in e["psi"].items()},
                  "m": {k: float(v) for k, v in e["m"].items()},
                  "deriva": {k: float(v) for k, v in e["deriva"].items()}, "eta2": float(e.get("eta2", 0.0)),
                  "mu": {k: float(v) for k, v in s1["mu"].items()}, "tau2": {k: float(v) for k, v in s1["tau2"].items()},
                  "sigma2": {k: float(v) for k, v in s1["sigma2"].items()}}
    return out


def nodos_offsets(off: pd.DataFrame, metricas: list[str]) -> dict:
    """{métrica: {"liga:temporada": (δ, var)}} desde league_offsets.csv (o tabla equivalente)."""
    out = {}
    for m, g in off[off["metrica"].isin(metricas)].groupby("metrica"):
        out[m] = {f"{r.competicion}:{r.temporada}": (float(r.media), float(r.sd) ** 2 if np.isfinite(r.sd) else 0.0)
                  for r in g.itertuples()}
    return out


def _nodo(nodos: dict, liga: str, temp: str, ref: str = "euroleague") -> tuple[float, float]:
    """Nivel (δ, var) de una competición-temporada; si no existe, media de las temporadas de la liga (var + media)."""
    if liga == ref:
        return 0.0, 0.0
    k = f"{liga}:{temp}"
    if k in nodos:
        return nodos[k]
    vs = [v for n, v in nodos.items() if n.startswith(liga + ":")]
    if not vs:
        return np.nan, np.nan
    d = np.array([v[0] for v in vs])
    return float(d.mean()), float(np.mean([v[1] for v in vs]) + d.var())


def entorno(c: dict, liga: str, temp: str, pos: str) -> tuple[float, float]:
    """(μ, τ) del grupo liga-temporada-posición en la escala transformada (temporada más cercana si falta)."""
    mu = c["mu"].get(f"{liga}|{temp}|{pos}")
    if mu is None:
        cand = sorted(k for k in c["mu"] if k.startswith(f"{liga}|") and k.endswith(f"|{pos}"))
        if not cand:
            return np.nan, np.nan
        prev = [k for k in cand if k.split("|")[1] <= temp]
        mu = c["mu"][(prev or cand)[-1]]
    t2 = c["tau2"].get(f"{liga}|{pos}", np.nan)
    return float(mu), float(np.sqrt(t2)) if np.isfinite(t2) else np.nan


def theta_desde_valor(v, lo, hi, c: dict, pos: str, temp_ref: str = "2025-26", z80: float = 1.2815515655446004):
    """Valor en la vara EuroLeague (<m>_am, con su intervalo del 80 %) → capacidad θ en DT y su desviación."""
    from bbmodel.metricas import transformar
    mu, tau = entorno(c, "euroleague", temp_ref, pos)
    if not np.isfinite(mu) or not tau:
        return np.nan, np.nan
    tv = transformar(v, c["transf"])
    th = (tv - mu) / tau
    sd = (transformar(hi, c["transf"]) - transformar(lo, c["transf"])) / (2 * z80 * tau)
    return th, np.abs(sd)


# =============================================================================================== normalización ≤ t
METRICAS_NIVEL = ["per", "game_score_p40", "ws_per_40", "ortg", "drtg", "pts_p100", "ts_pct", "efg_pct"]


def metricas_traduccion(cfg: dict | None = None) -> list[str]:
    cfg = cfg or cfg_sim()
    return list(dict.fromkeys(METRICAS_NIVEL + list(cfg["produccion"]["metricas"]) + ["rapm"]))


def normalizacion_hasta(anio_corte: int, metricas: list[str] | None = None, progreso=print) -> dict:
    """Amortiguación reajustada con temporadas ≤ anio_corte sobre el A ajustado con ≤ anio_corte (caché de la fase 2).
    Devuelve {"theta": DataFrame liga, temporada, player_id, pos3 + <m>_th/<m>_thsd, "traduccion": {...}}.
    Caché en experimentos/cache_simulador/norm_hasta_<año>.pkl."""
    from bbmodel import amortiguacion as AM
    from bbmodel import modelo
    DIR_CACHE.mkdir(parents=True, exist_ok=True)
    dest = DIR_CACHE / f"norm_hasta_{anio_corte}.pkl"
    if dest.exists():
        return pickle.loads(dest.read_bytes())
    pa = RAIZ / "experimentos" / "cache_normalizacion" / f"A_hasta_{anio_corte}.pkl"
    if not pa.exists():
        raise FileNotFoundError(f"falta {pa}: ejecute antes `python -m bbmodel amortiguar --validar`")
    metricas = metricas or metricas_traduccion()
    t0 = time.time()
    tabla, _ = modelo.preparar()
    p = pickle.loads(pa.read_bytes())
    p = {**p, "metricas": {m: v for m, v in p["metricas"].items() if m in metricas}}
    p.pop("_z", None)          # z de la tabla de entonces: se recalculan con la tabla actual (deterministas)
    cfg = AM.config()
    op = AM.opciones_variante(cfg)
    base = tabla[tabla["anio"] <= anio_corte]
    aj = AM.ajustar(base, p, cfg, hasta_anio=None, progreso=progreso, metricas=list(p["metricas"]), **op)
    aj["hasta_anio"] = anio_corte
    tr = AM.traducir(base, p, aj)
    th = tr[["liga", "temporada", "player_id"]].copy()
    for m in p["metricas"]:
        if f"{m}_am_a" in tr:
            th[f"{m}_th"] = tr[f"{m}_am_a"].to_numpy()
            th[f"{m}_thsd"] = tr[f"{m}_am_sd"].to_numpy()
            th[f"{m}_am"] = tr[f"{m}_am"].to_numpy()
    th["pos3"] = base["pos3"].to_numpy()
    const = constantes_A(p, list(p["metricas"]))
    completar_am(th, const)
    off = AM.tabla_offsets(aj, p)
    nod = nodos_offsets(off, list(p["metricas"]))
    res = {"theta": th, "traduccion": {"constantes": const, "nodos": nod, "fuente": f"A_corte_{anio_corte}"},
           "tiempo_s": round(time.time() - t0)}
    dest.write_bytes(pickle.dumps(res))
    if progreso:
        progreso(f"normalización ≤ {anio_corte}: {len(th)} filas, {time.time() - t0:.0f} s")
    return res


def completar_am(th: pd.DataFrame, const: dict, temp_ref: str = "2025-26") -> None:
    """<m>_am (vara EuroLeague) desde θ con μ/τ de la EuroLeague de la temporada de referencia o, si el ajuste no la
    tiene (A ajustado con ≤ t), de la más cercana anterior (bbmodel.amortiguacion.traducir dejaría NaN)."""
    from bbmodel.metricas import destransformar
    for m, k in const.items():
        if f"{m}_th" not in th:
            continue
        v = np.full(len(th), np.nan)
        for pos in ("E", "A", "I"):
            s_ = (th["pos3"] == pos).to_numpy()
            mu, tau = entorno(k, "euroleague", temp_ref, pos)
            if s_.any() and np.isfinite(mu):
                v[s_] = destransformar(mu + tau * th.loc[s_, f"{m}_th"].to_numpy(float), k["transf"])
        if f"{m}_am" not in th or th[f"{m}_am"].isna().all():
            th[f"{m}_am"] = v


def traduccion_completa(metricas: list[str] | None = None) -> dict:
    """Constantes con TODAS las temporadas: A (parametros.json) + niveles amortiguados (league_offsets.csv)."""
    from bbmodel.amortiguacion import cargar_parametros_A
    metricas = metricas or metricas_traduccion()
    p = cargar_parametros_A()
    off = pd.read_csv(DIR_AM / "league_offsets.csv")
    return {"constantes": constantes_A(p, metricas), "nodos": nodos_offsets(off, metricas), "fuente": "completa"}


def theta_completa(fuente: str, metricas: list[str], trad: dict) -> pd.DataFrame:
    """θ por jugador-liga-temporada con todas las temporadas: «AB» desde <m>_am (normalizado) o «A» desde
    traducciones amortiguadas (<m>_am_a, <m>_am_sd)."""
    DIR_CACHE.mkdir(parents=True, exist_ok=True)
    dest = DIR_CACHE / f"theta_{fuente}.pkl"
    if dest.exists():
        return pickle.loads(dest.read_bytes())
    partes = []
    if fuente == "A":
        for p in sorted((DIR_AM / "traducciones").glob("*.csv")):
            cols = ["liga", "temporada", "player_id"] + [c for m in metricas for c in (f"{m}_am_a", f"{m}_am_sd", f"{m}_am")]
            t = pd.read_csv(p, dtype={"player_id": str}, usecols=lambda c: c in cols)
            for m in metricas:
                if f"{m}_am_a" in t:
                    t = t.rename(columns={f"{m}_am_a": f"{m}_th", f"{m}_am_sd": f"{m}_thsd"})
            partes.append(t)
        th = pd.concat(partes, ignore_index=True)
        pos = _normalizado(["pos3"])
        th = th.merge(pos, on=["liga", "temporada", "player_id"], how="left")
    else:
        cols = ["pos3"] + [c for m in metricas for c in (f"{m}_am", f"{m}_am_lo", f"{m}_am_hi")]
        n = _normalizado(cols)
        th = n[["liga", "temporada", "player_id", "pos3"]].copy()
        c = trad["constantes"]
        for m in metricas:
            if m not in c or f"{m}_am" not in n:
                continue
            v, lo, hi = n[f"{m}_am"].to_numpy(float), n[f"{m}_am_lo"].to_numpy(float), n[f"{m}_am_hi"].to_numpy(float)
            t_, s_ = np.full(len(n), np.nan), np.full(len(n), np.nan)
            for pos in ("E", "A", "I"):
                k = (n["pos3"] == pos).to_numpy()
                if k.any():
                    t_[k], s_[k] = theta_desde_valor(v[k], lo[k], hi[k], c[m], pos)
            th[f"{m}_th"], th[f"{m}_thsd"] = t_, s_
            th[f"{m}_am"] = v
    dest.write_bytes(pickle.dumps(th))
    return th


def _dir_norm() -> tuple[Path, str]:
    """Dataset normalizado de la fuente activa: «V31» (simulador v3) = normalizacion.dir de la configuración (por defecto
    data/modelos/v3_1/normalizado/<t>.csv.gz, mismo esquema que el v1: sus <m>_am llevan la v3.1 y <m>_am_v1 el A+B
    amortiguado); resto = data/modelos/normalizado/<t>.csv."""
    n = cfg_sim()["normalizacion"]
    if str(n["fuente"]).startswith("V31"):
        return RAIZ / n.get("dir", "data/modelos/v3_1/normalizado"), ".csv.gz"
    return DIR_NORM, ".csv"


def dataset_simulador(progreso=print) -> Path:
    """Dataset normalizado que lee el simulador v3.1 (normalizacion.dir): el de la v3.1 (normalizacion.origen_v31) con
    las filas de las ligas de normalizacion.ligas_v2 (la Tercera FEB) tomadas del A+B amortiguado
    (normalizacion.origen_v2: estimación final, intervalos y percentiles de cada métrica). Motivo (examen completo del
    simulador, decisión post hoc): en la Tercera FEB la v3.1 usa sólo la CVAE (peso 1, ajuste por conocimiento), que
    comprime las diferencias entre jugadores de esa liga; en los fichajes con destino la Tercera FEB (casi todos desde
    ella misma) el error de pts/100 subía de 4,39 a 5,09 y la cobertura del 90 % bajaba de 0,81 a 0,54.
    Con estas filas iguales a la v2, traduccion_v31 deja en la Tercera FEB las constantes amortiguadas (θ_v31 = θ_v2)."""
    from bbmodel.dataset_normalizado import METRICAS
    n = cfg_sim()["normalizacion"]
    o31, o2, dest = RAIZ / n["origen_v31"], RAIZ / n["origen_v2"], RAIZ / n["dir"]
    ligas = list(n.get("ligas_v2", []))
    dest.mkdir(parents=True, exist_ok=True)
    clave = ["liga", "temporada", "player_id", "team_id"]
    sufijos = ["", "_lo", "_hi", "_pctel", "_am", "_am_lo", "_am_hi", "_am_pctel"]
    for f in sorted(o31.glob("*.csv.gz")):
        temp = f.name[:7]
        d = pd.read_csv(f, dtype={"player_id": str, "team_id": str}, low_memory=False)
        p2 = o2 / f"{temp}.csv.gz"
        p2 = p2 if p2.exists() else o2 / f"{temp}.csv"
        cambiadas = 0
        if ligas and p2.exists():
            v2 = pd.read_csv(p2, dtype={"player_id": str, "team_id": str}, low_memory=False)
            v2 = v2[v2["liga"].isin(ligas)].drop_duplicates(clave, keep=False)
            cols = [f"{m}{x}" for m in METRICAS for x in sufijos if f"{m}{x}" in d and f"{m}{x}" in v2]
            idx = d[clave].reset_index().merge(v2[clave].reset_index().rename(columns={"index": "i2"}), on=clave)
            if len(idx):
                d.loc[idx["index"].to_numpy(), cols] = v2.loc[idx["i2"].to_numpy(), cols].to_numpy()
                d.loc[idx["index"].to_numpy(), "fuente_norm"] = "A+B (Tercera FEB en el simulador)"
                cambiadas = len(idx)
        d.to_csv(dest / f.name, index=False)
        if progreso:
            progreso(f"  dataset del simulador {temp}: {len(d)} filas, {cambiadas} con la v2 ({', '.join(ligas)})")
    return dest


def traduccion(fuente: str, metricas: list[str] | None = None) -> dict:
    """Constantes de traducción a la liga de destino según la fuente de θ: «V31» = las de la v3.1 (traduccion_v31);
    el resto (AB, A y «V31A», diagnóstico) = las de la normalización amortiguada (traduccion_completa)."""
    return traduccion_v31(metricas) if fuente == "V31" else traduccion_completa(metricas)


def traduccion_v31(metricas: list[str] | None = None, progreso=print) -> dict:
    """Constantes de traducción coherentes con la v3.1 (sustituto lineal), sin tocar el motor.

    El motor traduce la capacidad θ (DT de la vara EuroLeague) a la liga de destino d con z_d = (θ − δ_d)/s_d
    (valor = T⁻¹(μ_d + τ_d·z_d)); con las constantes amortiguadas (δ, s) es la inversa de la v2 (θ_v2 ≈ δ + s·z), ya
    validada en el examen de la fase 8. Para una θ de la v3.1 se predice primero su equivalente en la escala v2 de esa
    liga, E[θ_v2 | θ_v31] = c_lt + d_l·θ_v31, ajustado con los mismos jugadores de la liga (las dos columnas del dataset
    v3.1: <m>_am y <m>_am_v1; ≥ min_minutos; pendiente d_l común a sus temporadas, intercepto c_lt por temporada).
    Es la regresión en el sentido de la predicción: donde la v3.1 y la v2 se parecen poco (Tercera FEB), d_l es pequeña
    y la traducción se acerca a la media de la liga en vez de exagerar las diferencias. Componiendo:
        z_d = (c_lt + d_l·θ − δ_lt)/s_l   ⇒   δ'_lt = (δ_lt − c_lt)/d_l,   s'_l = s_l/d_l,   m'_l = (m_l − c̄_l)/d_l
    con la misma varianza de nivel, ψ, deriva, μ/τ y σ² que la v2 (propiedades de los datos de cada liga, no del
    modelo de normalización). La EuroLeague (vara) no se toca: el motor fija su δ en 0. Donde la relación v3.1–v2 no
    es lineal (correlación < traduccion.r_minima: sólo la Tercera FEB) se conservan las constantes amortiguadas.
    Caché: traduccion_v31.pkl (en la caché de la versión)."""
    DIR_CACHE.mkdir(parents=True, exist_ok=True)
    dest = DIR_CACHE / "traduccion_v31.pkl"
    if dest.exists():
        return pickle.loads(dest.read_bytes())
    metricas = metricas or metricas_traduccion()
    base = traduccion_completa(metricas)
    const, nodos = base["constantes"], base["nodos"]
    cfg_t = cfg_sim().get("traduccion", {})
    min_min = float(cfg_t.get("min_minutos", 400))
    min_filas = int(cfg_t.get("min_filas_liga", 30))
    d_min = float(cfg_t.get("pendiente_minima", 0.1))      # evita s' infinita si una liga no tuviera relación alguna
    r_min = float(cfg_t.get("r_minima", 0.0))               # correlación v3.1–v2 mínima para usar el sustituto lineal
    cols = ["pos3", "min"] + [c for m in metricas for c in (f"{m}_am", f"{m}_am_v1")]
    n = _normalizado(cols)
    n = n[pd.to_numeric(n["min"], errors="coerce") >= min_min]
    ajuste = {}
    for m in metricas:
        if m not in const or f"{m}_am_v1" not in n:
            continue
        k = const[m]
        t31, t2 = np.full(len(n), np.nan), np.full(len(n), np.nan)
        for pos in ("E", "A", "I"):
            s_ = (n["pos3"] == pos).to_numpy()
            if s_.any():
                v31 = n.loc[s_, f"{m}_am"].to_numpy(float)
                v2 = n.loc[s_, f"{m}_am_v1"].to_numpy(float)
                t31[s_] = theta_desde_valor(v31, v31, v31, k, pos)[0]
                t2[s_] = theta_desde_valor(v2, v2, v2, k, pos)[0]
        d = pd.DataFrame({"liga": n["liga"].to_numpy(), "temporada": n["temporada"].to_numpy(), "t31": t31, "t2": t2})
        d = d[np.isfinite(d["t31"]) & np.isfinite(d["t2"])]
        nod_m, s_m, m_m = dict(nodos.get(m, {})), dict(k["s"]), dict(k["m"])
        for liga, g in d.groupby("liga"):
            if liga == "euroleague" or len(g) < min_filas:
                continue
            # E[θ_v2 | θ_v31]: pendiente común (dentro de cada temporada) e interceptos por temporada
            y = g["t2"] - g.groupby("temporada")["t2"].transform("mean")
            x = g["t31"] - g.groupby("temporada")["t31"].transform("mean")
            dd = float((x * y).sum() / (x * x).sum()) if (x * x).sum() > 0 else 1.0
            r = float(np.corrcoef(x, y)[0, 1]) if len(g) > 2 else np.nan
            if not (r >= r_min):
                # relación no lineal entre la v3.1 y la v2 en esa liga-métrica (Tercera FEB): el sustituto lineal no
                # representa a la v3.1 y se conservan las constantes amortiguadas
                ajuste[f"{m}|{liga}"] = {"d": None, "c_medio": None, "r": round(r, 3), "n": int(len(g)),
                                         "constantes": "amortiguadas"}
                continue
            dd = max(dd, d_min)
            c_t = (g.groupby("temporada")["t2"].mean() - dd * g.groupby("temporada")["t31"].mean()).to_dict()
            c_bar = float(np.average(list(c_t.values()), weights=g.groupby("temporada").size().reindex(list(c_t)).to_numpy()))
            for key, (dl, vl) in list(nod_m.items()):
                lg, temp = key.split(":", 1)
                if lg == liga:
                    nod_m[key] = ((dl - c_t.get(temp, c_bar)) / dd, vl / dd ** 2)
            if liga in s_m:
                s_m[liga] = s_m[liga] / dd
            if liga in m_m:
                m_m[liga] = (m_m[liga] - c_bar) / dd
            ajuste[f"{m}|{liga}"] = {"d": round(dd, 4), "c_medio": round(c_bar, 4), "r": round(r, 3), "n": int(len(g)),
                                     "constantes": "v31"}
        nodos[m] = nod_m
        const[m] = {**k, "s": s_m, "m": m_m}
    res = {"constantes": const, "nodos": nodos, "fuente": "v31_lineal", "ajuste": ajuste}
    dest.write_bytes(pickle.dumps(res))
    if progreso:
        ds = np.array([v["d"] for v in ajuste.values() if v["d"] is not None])
        progreso(f"traducción v3.1: {len(ajuste)} métrica-liga, pendiente d mediana {np.median(ds):.3f} "
                 f"(p10 {np.quantile(ds, 0.1):.3f}, p90 {np.quantile(ds, 0.9):.3f})")
    return res


def _normalizado(cols: list[str]) -> pd.DataFrame:
    fr = []
    base = ["liga", "temporada", "player_id"]
    d, ext = _dir_norm()
    for p in sorted(d.glob(f"*{ext}")):
        fr.append(pd.read_csv(p, dtype={"player_id": str}, usecols=lambda c: c in base + cols, low_memory=False))
    n = pd.concat(fr, ignore_index=True)
    return n.drop_duplicates(base)


# =============================================================================================== registros
ESTILOS_IDS = None


def estilos_ids() -> list[str]:
    """Ids de los estilos unificados en el orden de estilos.json (el mismo que usa el Atlas en eu_probs)."""
    global ESTILOS_IDS
    if ESTILOS_IDS is None:
        doc = json.loads((DIR_MOD / "estilos_unificados" / "estilos.json").read_text(encoding="utf-8"))
        ESTILOS_IDS = [e["id"] for e in doc["estilos"]]
    return ESTILOS_IDS


def escala_nivel() -> dict:
    return json.loads((DIR_MOD / "contexto" / "escala_nivel.json").read_text(encoding="utf-8"))


def indice_L(df: pd.DataFrame, sufijo: str = "_am") -> np.ndarray:
    """Índice de nivel L (bbmodel.contexto.indice_nivel) con los valores <m><sufijo> de las 8 métricas de nivel."""
    from bbmodel.contexto import NIVEL
    esc = escala_nivel()
    Z = np.column_stack([NIVEL[c] * (pd.to_numeric(df.get(f"{c}{sufijo}"), errors="coerce").to_numpy(float) - esc[c][0])
                         / esc[c][1] for c in NIVEL])
    ok = np.isfinite(Z)
    n = ok.sum(1)
    return np.where(n > 0, np.where(ok, Z, 0).sum(1) / np.maximum(n, 1), np.nan)


def L_intervalo(df: pd.DataFrame, const: dict, temp_ref: str = "2025-26", z80: float = 1.2815515655446004) -> np.ndarray:
    """Desviación de L: se mueven a la vez las 8 métricas de nivel ±z80·sd de su θ (incertidumbres muy correlacionadas:
    el nivel de la liga de origen es común) y sd_L = (L_alto − L_bajo)/(2·z80)."""
    from bbmodel.contexto import NIVEL
    from bbmodel.metricas import destransformar
    alto, bajo = {}, {}
    pos = df["pos3"].astype(object).to_numpy()
    for c, sgn in NIVEL.items():
        if c not in const or f"{c}_th" not in df:
            continue
        th = df[f"{c}_th"].to_numpy(float)
        sd = df[f"{c}_thsd"].to_numpy(float)
        mu = np.array([entorno(const[c], "euroleague", temp_ref, p)[0] if isinstance(p, str) else np.nan for p in pos])
        tau = np.array([entorno(const[c], "euroleague", temp_ref, p)[1] if isinstance(p, str) else np.nan for p in pos])
        hi = destransformar(mu + tau * (th + sgn * z80 * sd), const[c]["transf"])
        lo = destransformar(mu + tau * (th - sgn * z80 * sd), const[c]["transf"])
        alto[f"{c}_x"], bajo[f"{c}_x"] = hi, lo
    if not alto:
        return np.full(len(df), np.nan)
    Lh = indice_L(pd.DataFrame(alto), "_x")
    Ll = indice_L(pd.DataFrame(bajo), "_x")
    return np.abs(Lh - Ll) / (2 * z80)


def _bool(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().isin(["true", "1", "1.0"])


def _leer_roles_temporada() -> pd.DataFrame:
    p = DIR_CACHE / "roles_temporada.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    t = pd.read_csv(DIR_MOD / "roles" / "player_role_season.csv.gz", dtype={"team_id": str, "player_id": str, "persona_id": str},
                    low_memory=False)
    t["rol_probabilistico"] = _bool(t["rol_probabilistico"])
    t = t[t["min_total"].notna() & (t["min_total"] > 0)].copy()
    g = t.groupby(["liga", "temporada", "team_id"])["fin_orden"].transform("max")
    t["g_equipo"] = g
    t["presencia"] = ((t["fin_orden"] - t["inicio_orden"] + 1) / g).clip(0, 1)
    DIR_CACHE.mkdir(parents=True, exist_ok=True)
    p.write_bytes(pickle.dumps(t))
    return t


def _equipo_ligas(temp: str) -> pd.DataFrame:
    """Equipo-temporada (fase regular) desde ligas/<liga>.csv: nombre, código de club, ritmo, Net, partidos."""
    fr = []
    for liga in D.ligas_temporada(temp):
        d = D.ligas(liga, temp)
        if d.empty:
            continue
        d = d[d["fase"] == "regular"]
        cols = [c for c in ("team_id", "equipo", "equipo_codigo", "team_pace", "lg_pace", "team_netrtg", "team_gp",
                            "team_ortg", "team_drtg") if c in d]
        e = d[cols].drop_duplicates("team_id").copy()
        e["liga"], e["temporada"] = liga, temp
        fr.append(e)
    return pd.concat(fr, ignore_index=True) if fr else pd.DataFrame()


def registros_temporada(temp: str, theta: pd.DataFrame, const: dict, cfg: dict | None = None) -> pd.DataFrame:
    """Un registro por jugador-equipo-liga en la temporada `temp` con todo lo que el simulador lee de él.
    `principal` marca el registro de más minutos de cada persona (el que se usa como origen o como compañero)."""
    cfg = cfg or cfg_sim()
    r = _leer_roles_temporada()
    r = r[r["temporada"] == temp].copy()
    cols = ["liga", "temporada", "team_id", "player_id", "persona_id", "nombre", "pos3", "fuente", "gp", "g_equipo",
            "presencia", "min_total", "min_pg", "min_pct", "gs_pct", "close_pct", "rol", "rol_mas_probable",
            "rol_probabilistico", "usg_pct", "ts_pct", "pts", "poss_on", "pie", "gti", "z_usg", "z_pie",
            "z_no_asistidas", "z_usg_clutch", "H_rol", "edad", "entrenador_id", "ast_pct", "pct_no_asistidas"] \
        + [f"p_{k}" for k in ROLES]
    r = r[[c for c in cols if c in r]].rename(columns={"usg_pct": "usg_tiro", "ts_pct": "ts_tiro", "ast_pct": "ast_tiro"})
    r["pts_100_obs"] = 100 * r["pts"] / r["poss_on"].replace(0, np.nan)
    # capacidad θ y valores en la vara EuroLeague
    th = theta[theta["temporada"] == temp].drop(columns=["temporada"]).drop_duplicates(["liga", "player_id"])
    th = th.rename(columns={"pos3": "pos3_norm"})
    r = r.merge(th, on=["liga", "player_id"], how="left")
    r["pos3"] = r["pos3"].where(r["pos3"].isin(["E", "A", "I"]), r.get("pos3_norm"))
    # valores observados y normalizados sin amortiguar (baselines) y nacionalidad/edad
    mets = list(cfg["produccion"]["metricas"]) + ["rapm"]
    nc = ["nacionalidad", "anio_nac", "edad", "min"] + [f"{m}_obs" for m in mets] + [f"{m}{k}" for m in mets for k in ("", "_lo", "_hi")] \
        + ["ctx_plantilla_dev", "ctx_comp"]
    n = _normalizado_temp(temp, nc)
    n = n.rename(columns={"edad": "edad_norm", "min": "min_norm"})
    r = r.merge(n.drop(columns=["temporada"]), on=["liga", "player_id"], how="left")
    r["edad"] = r["edad"].fillna(r["edad_norm"]).fillna(anio(temp) - r["anio_nac"])
    nat = _nacionalidades()
    r = r.merge(nat[nat["temporada"] == temp][["liga", "player_id", "nac2"]], on=["liga", "player_id"], how="left")
    r["nacionalidad"] = r["nacionalidad"].where(r["nacionalidad"].notna(), r["nac2"])
    r = r.drop(columns=["nac2"])
    # nivel L (vara EuroLeague, amortiguado) y su incertidumbre
    r["L"] = indice_L(r, "_am")
    r["L_sd"] = L_intervalo(r, const)
    # volatilidad y entropías (fase 5)
    e = pd.read_csv(DIR_MOD / "entropia" / "jugadores.csv.gz", dtype={"team_id": str, "player_id": str},
                    usecols=["liga", "temporada", "team_id", "player_id", "sigma", "sigma_lo", "sigma_hi", "H_rol_post",
                             "H_estilo_norm", "H_estilo_basico_norm"])
    e = e[e["temporada"] == temp].drop(columns=["temporada"]).drop_duplicates(["liga", "team_id", "player_id"])
    r = r.merge(e, on=["liga", "team_id", "player_id"], how="left")
    # estilo unificado (fase 6)
    ids = estilos_ids()
    pc = [f"p_{i}" for i in ids]
    j = pd.read_csv(DIR_MOD / "estilos_unificados" / "jugadores.csv.gz", dtype={"team_id": str, "player_id": str},
                    usecols=["liga", "temporada", "team_id", "player_id", "nivel", "estilo", "p_estilo", "etiqueta",
                             "fiable"] + pc)
    j = j[(j["temporada"] == temp) & (j["nivel"] == "temporada")].drop(columns=["temporada", "nivel"])
    j = j.drop_duplicates(["liga", "team_id", "player_id"]).rename(columns={c: f"eu_{c[2:]}" for c in pc} | {
        "estilo": "eu", "p_estilo": "eu_p", "etiqueta": "eu_etiqueta", "fiable": "eu_fiable"})
    r = r.merge(j, on=["liga", "team_id", "player_id"], how="left")
    # principal por persona
    r = r.sort_values("min_total", ascending=False)
    r["principal"] = ~r.duplicated("persona_id")
    return r.reset_index(drop=True)


def _normalizado_temp(temp: str, cols: list[str]) -> pd.DataFrame:
    d, ext = _dir_norm()
    p = d / f"{temp}{ext}"
    cab = pd.read_csv(p, nrows=0).columns
    base = ["liga", "temporada", "player_id"]
    n = pd.read_csv(p, dtype={"player_id": str}, usecols=[c for c in base + cols if c in cab], low_memory=False)
    return n.drop_duplicates(["liga", "player_id"])


def _nacionalidades() -> pd.DataFrame:
    n = pd.read_csv(DIR_MOD / "nacionalidades.csv", dtype=str)
    n = n.rename(columns={"nacionalidad": "nac2"})
    return n[["liga", "temporada", "player_id", "nac2"]].drop_duplicates(["liga", "temporada", "player_id"])


def equipos_temporada(temp: str, reg: pd.DataFrame) -> pd.DataFrame:
    """Equipo-temporada: nombre, código de club, partidos, ritmo, Net, estilo unificado, entropías, entrenador."""
    e = _equipo_ligas(temp)
    g = reg.groupby(["liga", "team_id"]).agg(g_equipo=("g_equipo", "max"), jugadores=("persona_id", "nunique"),
                                             min_equipo=("min_total", "sum")).reset_index()
    e = g.merge(e.drop(columns=["temporada"]), on=["liga", "team_id"], how="left") if len(e) else g
    e["temporada"] = temp
    ids = estilos_ids()
    pc = [f"p_{i}" for i in ids]
    s = pd.read_csv(DIR_MOD / "estilos_unificados" / "equipos.csv", dtype={"team_id": str})
    s = s[(s["temporada"] == temp) & (s["nivel"] == "temporada")]
    s = s[["liga", "team_id", "estilo", "p_estilo", "etiqueta"] + pc].drop_duplicates(["liga", "team_id"])
    s = s.rename(columns={c: f"eu_{c[2:]}" for c in pc} | {"estilo": "eu", "p_estilo": "eu_p", "etiqueta": "eu_etiqueta"})
    e = e.merge(s, on=["liga", "team_id"], how="left")
    h = pd.read_csv(DIR_MOD / "entropia" / "equipos.csv", dtype={"team_id": str})
    h = h[h["temporada"] == temp][["liga", "team_id", "H_uso_norm", "H_red_pases_norm", "H_minutos_norm", "hhi_uso"]]
    e = e.merge(h.drop_duplicates(["liga", "team_id"]), on=["liga", "team_id"], how="left")
    ts = pd.read_csv(DIR_MOD / "roles" / "team_role_structure.csv", dtype={"team_id": str, "entrenador_principal": str})
    ts = ts[ts["temporada"] == temp][["liga", "team_id", "entrenador_principal", "rotacion"]]
    e = e.merge(ts.drop_duplicates(["liga", "team_id"]), on=["liga", "team_id"], how="left")
    # entrenador modal de los registros si la estructura no lo trae
    modal = reg.dropna(subset=["entrenador_id"]).groupby(["liga", "team_id"])["entrenador_id"] \
        .agg(lambda x: x.mode().iat[0]) if reg["entrenador_id"].notna().any() else pd.Series(dtype=str)
    e["entrenador"] = e["entrenador_principal"].where(e["entrenador_principal"].notna(),
                                                      pd.Series([modal.get((a, b)) for a, b in zip(e["liga"], e["team_id"])],
                                                                index=e.index))
    e["club"] = np.where(e["liga"].str.startswith("feb") & e.get("equipo_codigo", pd.Series(index=e.index)).notna(),
                         e["liga"] + "|" + e.get("equipo_codigo", pd.Series(index=e.index)).astype(str),
                         e["liga"] + "|" + e["team_id"].astype(str))
    return e


# =============================================================================================== modelos ≤ t
def _partidos_jugador() -> pd.DataFrame:
    p = DIR_CACHE / "partidos_jugador.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    cols = ["liga", "temporada", "game_id", "team_id", "player_id", "persona_id", "pos3", "jugo", "sec", "dur_s",
            "min_pct", "fga", "fta", "coef_tl", "usg_tiro", "ts_pct", "entrenador_id"]
    partes = [pd.read_csv(f, usecols=cols, dtype={"team_id": str, "player_id": str, "game_id": str, "persona_id": str,
                                                  "entrenador_id": str}, low_memory=False)
              for f in sorted((DIR_MOD / "roles" / "partidos_jugador").glob("*.csv.gz"))]
    pj = pd.concat(partes, ignore_index=True)
    pj["jugo"] = _bool(pj["jugo"])
    DIR_CACHE.mkdir(parents=True, exist_ok=True)
    p.write_bytes(pickle.dumps(pj))
    return pj


def modelos_hasta(temp: str, cfg: dict | None = None) -> dict:
    """Piezas ajustadas con temporadas ≤ temp: tendencias de entrenador, β uso-eficiencia (IV) por pos3, efecto de la
    calidad de compañeros, minutos medianos por rol y liga, referencias de uso por liga. Caché por temporada."""
    from . import reemplazo as RE
    cfg = cfg or cfg_sim()
    dest = DIR_CACHE / f"modelos_hasta_{temp}.pkl"
    if dest.exists():
        return pickle.loads(dest.read_bytes())
    t0 = time.time()
    rcfg = cargar("reemplazo")
    pj = _partidos_jugador()
    pj = pj[pj["temporada"] <= temp]
    tend = RE.tendencias_entrenador(pj, rcfg)
    # β uso-eficiencia con el instrumento de vacío de rol (mismo cálculo que bbfit.reemplazo.uso_eficiencia)
    c = rcfg["uso_eficiencia"]
    z = RE.instrumento_vacio(pj, float(c["vacio_min_pct_rotacion"]))
    g = pj[pj["jugo"]].copy()
    g["z_vacio"] = z[g.index].to_numpy()
    g["tsa"] = g["fga"] + g["coef_tl"] * g["fta"]
    g = g[g["tsa"] >= c["min_intentos_partido"]]
    g["grupo_intra"] = g["liga"] + "|" + g["temporada"] + "|" + g["team_id"].astype(str) + "|" + g["persona_id"]
    g["pos3_p"] = g["pos3"].fillna("NA")
    beta = RE.iv_grupo(g, "ts_pct", "usg_tiro", "z_vacio", "tsa", "grupo_intra", "pos3_p", int(c["bootstrap_grupo"]),
                       int(rcfg["semilla"]), float(c["nivel_intervalo"]))
    beta = {r["pos3_p"]: (float(r["beta_iv"]), float(r["beta_iv_sd"])) for r in beta.to_dict("records")}
    # calidad de compañeros (asociación dentro de jugador)
    cc = pd.read_csv(DIR_MOD / "reemplazo" / "calidad_companeros.csv.gz", dtype={"team_id": str, "player_id": str,
                                                                               "persona_id": str})
    ef = RE.efecto_companeros(cc[cc["temporada"] <= temp], int(rcfg["semilla"]), B=200)
    comp = {r["produccion"]: (float(r["pendiente_por_unidad_L"]), float((r["ic_hi"] - r["ic_lo"]) / (2 * 1.6449)))
            for r in ef.to_dict("records")}
    # minutos (MIN%) medianos por liga y rol, y referencia de uso (USG% de caja) por liga-temporada
    rs = _leer_roles_temporada()
    rs = rs[(rs["temporada"] <= temp) & ~rs["rol_probabilistico"]]
    min_rol = rs.groupby(["liga", "rol"])["min_pct"].median().to_dict()
    min_rol_global = rs.groupby("rol")["min_pct"].median().to_dict()
    res = {"temporada": temp, "tendencias": tend, "beta_uso": beta, "companeros": comp, "min_rol": min_rol,
           "min_rol_global": min_rol_global, "tiempo_s": round(time.time() - t0)}
    dest.write_bytes(pickle.dumps(res))
    return res


# =============================================================================================== main (trabajo largo)
if __name__ == "__main__":     # python -m bbfit.sim_insumos <año> …  (normalización ≤ t en segundo plano)
    import sys
    for a in sys.argv[1:] or ["2023", "2024"]:
        normalizacion_hasta(int(a))
