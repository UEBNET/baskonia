"""v3.2 · B1 (ablación de la CVAE), B4 (inferencia semiamortizada) y B6 (t de Student) con cortes anidados.

Variantes: la CVAE completa (configs/normalization_v32.yaml) y, por cada pieza de `ablacion.piezas`, la misma CVAE sin
esa pieza («sin_<pieza>»). Cada variante se entrena con las `ablacion.semillas` primeras semillas en cada corte de
`ablacion.cortes` (ajuste con ≤ t, predicción de los cambios de liga t → t+1, mismos casos que el examen de la v3.1).

Regla de la navaja (fijada de antemano, decisión del usuario del 02-11-2026): la pieza se QUITA si quitarla no empeora
de forma significativa, es decir, si el IC 95 % bootstrap (remuestreo por persona × corte) de MAE_sin / MAE_con − 1
(media de las 33 métricas) tiene el extremo inferior ≤ 0 Y la cobertura media del 80 % recalibrada de la variante sin
la pieza sigue en `validacion.cobertura_objetivo`. Se compara la CVAE SOLA (sin mezclar con la v2), para medir la red.

Cortes anidados: la decisión que se aplica en el corte t se toma con los cortes de decisión < t (la del 2023, con el
2022; la del 2024, con 2022 + 2023; la final, con los tres). El corte 2021 sólo recalibra los intervalos del 2022.

    python -m bbnorm3 --config configs/normalization_v32.yaml ablacion             # entrenar + predecir + decidir
    python -m bbnorm3 --config configs/normalization_v32.yaml ablacion --fase entrenar
"""
from __future__ import annotations

import json
import os
import pickle
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from . import examen

PIEZA_INFERENCIA = "refinado"        # pieza que sólo cambia la inferencia (mismas redes que la completa)


def dir_ablacion(cfg: dict) -> Path:
    d = C.dir_salida(cfg) / "validacion" / "ablacion"
    d.mkdir(parents=True, exist_ok=True)
    return d


def variantes(cfg: dict, quitar: list[str] | None = None) -> dict[str, dict]:
    """{"completa": cfg, "sin_<pieza>": cfg sin la pieza}. Con `quitar`, la base ya no tiene esas piezas."""
    base = configuracion_sin(cfg, quitar or [])
    out = {"completa": base}
    for p, cambios in cfg["ablacion"]["piezas"].items():
        if p not in (quitar or []):
            out[f"sin_{p}"] = C.con(base, **cambios)
    return out


def configuracion_sin(cfg: dict, piezas: list[str]) -> dict:
    cambios = {}
    for p in piezas:
        cambios.update(cfg["ablacion"]["piezas"][p])
    return C.con(cfg, **cambios) if cambios else cfg


def _ruta_red(cfg_v: dict, anio, semilla: int) -> Path:
    from .flujo import DIR_CACHE, _huella
    return DIR_CACHE / f"h{anio}_{_huella(cfg_v)}_s{semilla}.pt"


def _tabla_cache(cfg: dict) -> Path:
    from .flujo import DIR_CACHE
    DIR_CACHE.mkdir(parents=True, exist_ok=True)
    return DIR_CACHE / "tabla_v32.pkl"


def guardar_tabla(tabla: pd.DataFrame, cfg: dict) -> Path:
    f = _tabla_cache(cfg)
    if not f.exists():
        f.write_bytes(pickle.dumps(tabla))
    return f


# ------------------------------------------------------------------------------------------ procesos (1 hilo cada uno)
def _hilos(n: int) -> None:
    os.environ["OMP_NUM_THREADS"] = str(n)
    import torch
    torch.set_num_threads(n)
    try:
        from threadpoolctl import threadpool_limits
        threadpool_limits(n)
    except Exception:  # noqa: BLE001
        pass


def _entrenar_uno(args) -> str:
    f_tabla, cfg_v, anio, semilla, ruta, hilos = args
    _hilos(hilos)
    import torch
    from . import datos, modelo
    if Path(ruta).exists():
        return f"{Path(ruta).name} (ya estaba)"
    tabla = pickle.loads(Path(f_tabla).read_bytes())
    t0 = time.time()
    D = datos.construir(tabla, cfg_v, hasta_anio=None if anio is None else int(anio))
    m = modelo.entrenar(D, cfg_v, int(semilla), progreso=None)
    tmp = Path(str(ruta) + ".tmp")
    torch.save(m.state_dict(), tmp)
    tmp.replace(ruta)
    return f"{Path(ruta).name} {time.time() - t0:.0f} s"


def entrenar(tareas: list[tuple[dict, object, int]], cfg: dict, f_tabla: Path, progreso=print) -> None:
    """Entrena en paralelo (procesos × 1 hilo) las redes (cfg_v, corte, semilla) que falten."""
    a = cfg["ablacion"]
    pend = []
    for cfg_v, anio, s in tareas:
        r = _ruta_red(cfg_v, anio, s)
        if not r.exists() and r not in [p[4] for p in pend]:
            pend.append((str(f_tabla), cfg_v, anio, s, r, int(a.get("hilos", 1))))
    # los cortes grandes primero (reparten mejor la carga al final)
    pend.sort(key=lambda p: -(9999 if p[2] is None else int(p[2])))
    if progreso:
        progreso(f"  {len(pend)} redes por entrenar ({len(tareas)} pedidas)", flush=True)
    if not pend:
        return
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=int(a.get("procesos", 4))) as ex:
        fut = [ex.submit(_entrenar_uno, p) for p in pend]
        for k, f in enumerate(as_completed(fut), 1):
            msg = f.result()
            if progreso:
                progreso(f"  [{k}/{len(pend)}] {msg} · {time.time() - t0:.0f} s", flush=True)


def _predecir_uno(args) -> str:
    f_tabla, cfg_v, nombre, anio, semillas, destino, hilos, *resto = args
    con_salv = resto[0] if resto else True
    _hilos(hilos)
    if Path(destino).exists():
        return f"{Path(destino).name} (ya estaba)"
    from . import flujo, prediccion
    tabla = pickle.loads(Path(f_tabla).read_bytes())
    t0 = time.time()
    D, cj = flujo.conjunto(tabla, cfg_v, int(anio), semillas=semillas, progreso=None)
    r = prediccion.predecir_cambios(cj, D, tabla, int(anio), cfg_v)
    r = r.assign(variante=nombre)
    r.round(5).to_csv(str(destino) + ".tmp.csv.gz", index=False)
    Path(str(destino) + ".tmp.csv.gz").replace(destino)
    # salvaguardas de §8c (ciclo y niveles), con las mismas redes; y la escala del corte (para la mezcla)
    if con_salv:
        sv = salvaguardas(cj, D, cfg_v, int(anio))
        Path(str(destino).replace(".csv.gz", "_salvaguardas.json")).write_text(json.dumps(sv, default=float))
    f_esc = Path(destino).parent / f"escala_{anio}.pkl"
    if not f_esc.exists():
        f_esc.write_bytes(pickle.dumps(D.esc))
    return f"{Path(destino).name} {len(r)} filas {time.time() - t0:.0f} s"


def salvaguardas(cj, D, cfg_v: dict, anio: int, n_triangulos: int = 60) -> dict:
    """§8c · ciclo: residuo medio |R_abc,m| (DT de la escala de trabajo) en una muestra FIJA de triángulos de
    competiciones de la última temporada del corte, con la primera red; triángulos con max_m |R| > umbral.
    Niveles: δ_c por métrica (vara de la EuroLeague del corte) y su DT a posteriori (media de las redes y varianza
    entre redes) para comparar variantes."""
    from . import traduccion
    from .datos import METRICAS
    temp = f"{anio}-{str(anio + 1)[-2:]}"
    comps = [k for k, c in enumerate(D.comps) if c.endswith("|" + temp)]
    rng = np.random.default_rng(anio)
    tri = set()
    while len(tri) < min(n_triangulos, max(len(comps) * (len(comps) - 1) * (len(comps) - 2) // 6, 1)):
        tri.add(tuple(sorted(rng.choice(comps, 3, replace=False).tolist())))
    m0, P0 = cj[0]
    umbral = float(cfg_v["ablacion"].get("salvaguardas", {}).get("ciclo_umbral_dt", 0.5))
    R = np.array([traduccion.residuo_ciclo(m0, P0, D, t, n=300) for t in sorted(tri)])
    ref = D.comps.index(f"euroleague|{temp}") if f"euroleague|{temp}" in D.comps else 0
    deltas, varis = [], []
    for m, P in cj:
        d, J = traduccion.niveles(m, P, D, ref)
        cov = P.cov_mu()
        deltas.append(d)
        varis.append(np.array([traduccion.covarianza_niveles(J, cov, ref, c, c) for c in range(len(D.comps))]))
    dl, vr = np.mean(deltas, 0), np.mean(varis, 0) + np.var(deltas, 0)
    idx = [METRICAS.index(x) for x in ("pts_p100", "ts_pct", "per", "rapm")]
    return {"ciclo_medio": float(np.abs(R).mean()), "ciclo_triangulos_altos": int((np.abs(R).max(1) > umbral).sum()),
            "ciclo_triangulos": len(tri), "comps": list(D.comps),
            "niveles": {METRICAS[k]: {"delta": dl[:, k].tolist(), "sd": np.sqrt(np.maximum(vr[:, k], 0)).tolist()}
                        for k in idx},
            "nu": cj[0][0].nu().detach().numpy().tolist() if getattr(cj[0][0], "student", False) else None}


def ruta_pred(cfg: dict, nombre: str, anio: int, n_semillas: int) -> Path:
    return dir_ablacion(cfg) / f"pred_{nombre}_{anio}_n{n_semillas}.csv.gz"


def predecir(trabajos: list[tuple[str, dict, int]], cfg: dict, f_tabla: Path, n_semillas: int, progreso=print,
             salvaguardas_: bool = True, procesos: int | None = None) -> None:
    a = cfg["ablacion"]
    sem = list(cfg["semillas"][:n_semillas])
    pend = []
    for nombre, cfg_v, anio in trabajos:
        dst = ruta_pred(cfg, nombre, anio, n_semillas)
        if not dst.exists():
            pend.append((str(f_tabla), cfg_v, nombre, anio, sem, dst, int(a.get("hilos", 1)), salvaguardas_))
    if not pend:
        return
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=int(procesos or a.get("procesos", 4))) as ex:
        fut = [ex.submit(_predecir_uno, p) for p in pend]
        for k, f in enumerate(as_completed(fut), 1):
            msg = f.result()
            if progreso:
                progreso(f"  predicción [{k}/{len(pend)}] {msg} · {time.time() - t0:.0f} s", flush=True)


# ------------------------------------------------------------------------------------------ evaluación (§8)
FAMILIAS = {   # §8a · media por familias (primero dentro de cada familia, luego entre familias)
    "tiro": ["ts_pct", "efg_pct", "fg2_pct", "fg3_pct", "ft_pct", "ortg"],
    "uso_creacion": ["usg_pct", "ast_pct", "tov_pct", "fta_rate", "fg3a_rate"],
    "rebote": ["oreb_p100", "oreb_pct", "dreb_p100", "dreb_pct"],
    "defensa": ["stl_p100", "stl_pct", "blk_p100", "blk_pct", "pf_p100", "drtg"],
    "impacto": ["rapm", "orapm", "drapm"],
    "perfil_tiro": ["pct_aro", "pct_corta", "pct_media", "pct_t3_esquina", "pct_asistidas"],
    "global": ["pts_p100", "per", "game_score_p40", "ws_per_40"],
}
CLAVE_PRED = ["metrica", "anio", "persona_id", "liga_o", "liga_d", "real_r"]


def cargar_pred(cfg: dict, nombre: str, anio: int, n_semillas: int) -> pd.DataFrame:
    r = pd.read_csv(ruta_pred(cfg, nombre, anio, n_semillas))
    return r.assign(real_r=r["real"].round(3))


def _salv(cfg: dict, nombre: str, anio: int, n: int) -> dict:
    f = Path(str(ruta_pred(cfg, nombre, anio, n)).replace(".csv.gz", "_salvaguardas.json"))
    return json.loads(f.read_text()) if f.exists() else {}


def mezcla_corte(tabla: pd.DataFrame, cfg: dict, nombre: str, anio: int, n: int) -> pd.DataFrame:
    """CVAE de la variante + v2 en la escala de trabajo (componentes) para mezclar con peso fijo 0,5 (§8a)."""
    from . import combinacion
    esc = pickle.loads((dir_ablacion(cfg) / f"escala_{anio}.pkl").read_bytes())
    j = combinacion.componentes_desde(cargar_pred(cfg, nombre, anio, n), esc, tabla, cfg, anio)
    j.attrs["esc"] = esc
    return j


def _cfg_mezcla(cfg: dict) -> dict:
    return C.con(cfg, **{"combinacion.peso_v3": 0.5, "combinacion.peso_por_metrica": False})


def mezcla_calibrada(tabla: pd.DataFrame, cfg: dict, nombre: str, anios: list[int], n: int) -> pd.DataFrame:
    """Mezcla 0,5 de la variante en los cortes `anios`, recalibrada con el corte anterior de la MISMA variante."""
    from . import combinacion
    v = cfg["validacion"]
    cm = _cfg_mezcla(cfg)
    out = []
    for a in anios:
        cal = combinacion.combinar(mezcla_corte(tabla, cfg, nombre, a - 1, n), cm, None)
        fac = examen.factores_calibracion(cal, int(v["min_casos_grupo"]))
        j = mezcla_corte(tabla, cfg, nombre, a, n)
        r = examen.aplicar_calibracion(combinacion.combinar(j, cm, None), fac)
        r.attrs["esc"] = j.attrs["esc"]
        out.append(r)
    r = pd.concat(out, ignore_index=True)
    r.attrs["esc"] = out[-1].attrs["esc"]
    return r


def _tabla_bootstrap(con: pd.DataFrame, sin: pd.DataFrame):
    """Filas comunes a las dos variantes y arrays para el bootstrap de personas y semillas."""
    from bbmodel.metricas import CATALOGO
    clave = CLAVE_PRED
    a = con.drop_duplicates(clave, keep=False)
    b = sin.drop_duplicates(clave, keep=False)
    cz = [c for c in a.columns if c.startswith("cz_")]
    j = a[clave + ["real", "v2_centro_z", "peso_cvae"] + cz].merge(
        b[clave + ["peso_cvae"] + cz], on=clave, suffixes=("_con", "_sin"))
    met = sorted(j["metrica"].unique())
    mi = j["metrica"].map({m: i for i, m in enumerate(met)}).to_numpy()
    unidad = (j["persona_id"].astype(str) + "|" + j["anio"].astype(str))
    ui = pd.factorize(unidad)[0]
    return j, met, mi, ui, [c.replace("_con", "") for c in j.columns if c.startswith("cz_") and c.endswith("_con")]


def _valor(z, met_idx, met, esc):
    from bbmodel.metricas import CATALOGO, destransformar
    out = np.empty_like(z)
    for k, m in enumerate(met):
        s = met_idx == k
        out[s] = destransformar(esc.c[m] + esc.s[m] * z[s], CATALOGO[m].transf)
    return out


def _mae_familias(err_con, err_sin, mi, met, w_filas):
    """MAE_F(sin)/MAE_F(con) − 1 con la media por familias de los cocientes por métrica."""
    nm = len(met)
    sc = np.bincount(mi, weights=w_filas * err_con, minlength=nm)
    ss = np.bincount(mi, weights=w_filas * err_sin, minlength=nm)
    rat = {m: ss[k] / sc[k] for k, m in enumerate(met) if sc[k] > 0}
    fams = [np.mean([rat[m] for m in ms if m in rat]) for ms in FAMILIAS.values() if any(m in rat for m in ms)]
    return float(np.mean(fams) - 1.0), rat


def comparar(con: pd.DataFrame, sin: pd.DataFrame, cfg: dict) -> dict:
    """§8 · Δ_P^mix con IC 95 % por bootstrap anidado (personas × corte y, por separado para «con» y «sin», las 5
    semillas con reemplazo), y la cobertura recalibrada de la mezcla sin la pieza."""
    v = cfg["validacion"]
    esc = con.attrs["esc"]
    j, met, mi, ui, czs = _tabla_bootstrap(con, sin)
    y = j["real"].to_numpy(float)
    c2 = j["v2_centro_z"].fillna(0).to_numpy(float)
    wc, ws = j["peso_cvae_con"].to_numpy(float), j["peso_cvae_sin"].to_numpy(float)
    Zc = np.stack([j[f"{c}_con"].to_numpy(float) for c in czs], 1)
    Zs = np.stack([j[f"{c}_sin"].to_numpy(float) for c in czs], 1)

    def errores(selc, sels):
        zc = wc * Zc[:, selc].mean(1) + (1 - wc) * c2
        zs = ws * Zs[:, sels].mean(1) + (1 - ws) * c2
        return np.abs(_valor(zc, mi, met, esc) - y), np.abs(_valor(zs, mi, met, esc) - y)

    todas = np.arange(len(czs))
    ec, es = errores(todas, todas)
    est, rat = _mae_familias(ec, es, mi, met, np.ones(len(y)))
    B = int(cfg["ablacion"].get("bootstrap", 1000))
    rng = np.random.default_rng(int(v["semilla_bootstrap"]))
    nu = ui.max() + 1
    vals = np.empty(B)
    for b in range(B):
        wu = np.bincount(rng.integers(0, nu, nu), minlength=nu).astype(float)
        if cfg["ablacion"].get("bootstrap_semillas", True):
            ec_b, es_b = errores(rng.integers(0, len(czs), len(czs)), rng.integers(0, len(czs), len(czs)))
        else:
            ec_b, es_b = ec, es
        vals[b] = _mae_familias(ec_b, es_b, mi, met, wu[ui])[0]
    lo, hi = np.quantile(vals, [0.025, 0.975])
    cob = float(sin.drop_duplicates(CLAVE_PRED, keep=False)["dentro_80_v3c"].mean())
    return {"casos": int(len(j)), "delta_mezcla": est, "ic95": [float(lo), float(hi)], "cobertura80_sin": cob,
            "cobertura80_con": float(con.drop_duplicates(CLAVE_PRED, keep=False)["dentro_80_v3c"].mean()),
            "cociente_por_metrica": {m: float(r) for m, r in rat.items()}}


def regla(res: dict, pieza: str, s_con: list[dict], s_sin: list[dict], cfg: dict) -> dict:
    """§8c-d · QUITAR si IC95,sup(Δ) < margen, cobertura en rango y salvaguardas; CONSERVAR si IC95,inf > 0; si no,
    «indeterminada» (se conserva)."""
    a = cfg["ablacion"]
    sv = a.get("salvaguardas", {})
    lo, hi = cfg["validacion"]["cobertura_objetivo"]
    margen = float(a.get("margen", 0.005))
    # ciclo (todas las piezas): media de los cortes usados
    cc = np.mean([x["ciclo_medio"] for x in s_con if x]) if any(s_con) else np.nan
    cs = np.mean([x["ciclo_medio"] for x in s_sin if x]) if any(s_sin) else np.nan
    tc = sum(x.get("ciclo_triangulos_altos", 0) for x in s_con if x)
    ts = sum(x.get("ciclo_triangulos_altos", 0) for x in s_sin if x)
    ciclo_ok = bool(np.isfinite(cs) and cs <= float(sv.get("ciclo_ratio", 1.25)) * cc and ts <= tc)
    # niveles: max_c |δ_sin − δ_con| / sd_con en pts, TS%, PER y RAPM (obligatoria para la IPW)
    mov = []
    for x, z in zip(s_con, s_sin):
        if not x or not z:
            continue
        for m, d in x["niveles"].items():
            dc, sc = np.array(d["delta"]), np.array(d["sd"])
            ds = np.array(z["niveles"][m]["delta"])
            ok = sc > 0
            mov.append(float(np.max(np.abs(ds[ok] - dc[ok]) / sc[ok])))
    niveles_max = max(mov) if mov else np.nan
    niveles_ok = bool(not np.isfinite(niveles_max) or niveles_max <= float(sv.get("niveles_sd", 1.0)))
    exige_niveles = pieza in a.get("salvaguarda_niveles_obligatoria", ["ipw"])
    quitar = (res["ic95"][1] < margen and lo <= res["cobertura80_sin"] <= hi and ciclo_ok
              and (niveles_ok or not exige_niveles))
    estado = "quitar" if quitar else ("conservar" if res["ic95"][0] > 0 else "indeterminada")
    return {**res, "ciclo_con": cc, "ciclo_sin": cs, "ciclo_altos_con": tc, "ciclo_altos_sin": ts,
            "ciclo_ok": ciclo_ok, "niveles_max_sd": niveles_max, "niveles_ok": niveles_ok, "estado": estado,
            "quitar": quitar}


def decidir(tabla: pd.DataFrame, cfg: dict, anios: list[int], n_semillas: int, base: str = "completa",
            nombres: dict[str, str] | None = None) -> dict:
    """Decisión pieza a pieza con los cortes `anios` (todas las piezas frente a la misma base)."""
    con = mezcla_calibrada(tabla, cfg, base, anios, n_semillas)
    s_con = [_salv(cfg, base, a, n_semillas) for a in anios]
    res = {}
    for p in cfg["ablacion"]["piezas"]:
        nombre = (nombres or {}).get(p, f"sin_{p}")
        try:
            sin = mezcla_calibrada(tabla, cfg, nombre, anios, n_semillas)
        except FileNotFoundError:
            continue
        s_sin = [_salv(cfg, nombre, a, n_semillas) for a in anios]
        res[p] = regla(comparar(con, sin, cfg), p, s_con, s_sin, cfg)
        if p == PIEZA_INFERENCIA:           # B4 por tramos de minutos de origen (§10)
            res[p]["por_tramo_min_origen"] = por_tramo(con, sin)
    return res


def por_tramo(con: pd.DataFrame, sin: pd.DataFrame) -> dict:
    """ΔR (sin/con − 1, media de métricas) por tramo de minutos de origen {100-300, 300-800, > 800}."""
    a = con.drop_duplicates(CLAVE_PRED, keep=False)
    b = sin.drop_duplicates(CLAVE_PRED, keep=False)
    j = a[CLAVE_PRED + ["real", "v3", "min_o"]].merge(b[CLAVE_PRED + ["v3"]], on=CLAVE_PRED, suffixes=("_con", "_sin"))
    out = {}
    for nom, (l, h) in {"100-300": (100, 300), "300-800": (300, 800), ">800": (800, 1e9)}.items():
        g = j[(j["min_o"] >= l) & (j["min_o"] < h)]
        if len(g):
            r = g.assign(ec=(g["v3_con"] - g["real"]).abs(), es=(g["v3_sin"] - g["real"]).abs()).groupby("metrica")
            out[nom] = {"casos": int(len(g)), "delta": float((r["es"].mean() / r["ec"].mean()).mean() - 1)}
    return out


def aplicar_decision(ruta_cfg: Path | None = None, progreso=print) -> list[str]:
    """Escribe en la configuración (`ablacion.quitadas`) las piezas que la decisión FINAL de la ablación quita."""
    import re
    ruta = Path(ruta_cfg or C.RAIZ / "configs" / "normalization_v32.yaml")
    cfg = C.cargar(ruta)
    cfg = cfg.get("_completa", cfg)
    d = json.loads((dir_ablacion(cfg) / "decisiones.json").read_text(encoding="utf-8"))
    final = [x for x in d["decisiones"].values() if x["aplica_en"] == "final"][0]["quitar"]
    t = ruta.read_text(encoding="utf-8")
    linea = f"  quitadas: {json.dumps(sorted(final))}   # decisión final de la ablación (validacion/ablacion/decisiones.json)"
    if re.search(r"^  quitadas:.*$", t, flags=re.M):
        t = re.sub(r"^  quitadas:.*$", linea, t, flags=re.M)
    else:
        t = t.replace("ablacion:                       # B1 + B4 + B6 (bbnorm3/ablacion.py)\n",
                      "ablacion:                       # B1 + B4 + B6 (bbnorm3/ablacion.py)\n" + linea + "\n")
    ruta.write_text(t, encoding="utf-8")
    if progreso:
        progreso(f"  configuración final de la v3.2: sin {final or 'ninguna pieza'}", flush=True)
    return final


def main(tabla: pd.DataFrame, cfg: dict, fase: str = "todo", progreso=print) -> dict:
    cfg = cfg.get("_completa", cfg)            # la ablación compara siempre con la configuración completa
    a = cfg["ablacion"]
    n = int(a["semillas"])
    sem = list(cfg["semillas"][:n])
    cortes = [int(x) for x in a["cortes"]]
    dec = [int(x) for x in a["cortes_decision"]]
    f_tabla = guardar_tabla(tabla, cfg)
    V = variantes(cfg)
    redes = {k: v for k, v in V.items() if k != f"sin_{PIEZA_INFERENCIA}"}   # «sin refinado» = mismas redes
    if fase in ("todo", "entrenar"):
        entrenar([(cv, an, s) for cv in redes.values() for an in cortes for s in sem], cfg, f_tabla, progreso)
    if fase in ("todo", "predecir"):
        predecir([(k, cv, an) for k, cv in V.items() for an in cortes], cfg, f_tabla, n, progreso)
    if fase not in ("todo", "decidir"):
        return {}
    informe = {"regla": ("§8 (criterios del 02-11-2026): mezcla con peso 0,5 y media por familias; QUITAR si "
                         f"IC95,sup(Δ) < {a.get('margen', 0.005):+.1%}, cobertura recalibrada sin la pieza en "
                         f"{cfg['validacion']['cobertura_objetivo']} y salvaguardas de ciclo (todas) y niveles (IPW); "
                         "CONSERVAR si IC95,inf > 0; si no, indeterminada (se conserva)"),
               "redes_por_variante": n, "decisiones": {}}
    for k, t in enumerate(dec):
        usados = [x for x in dec if x <= t]
        d = decidir(tabla, cfg, usados, n)
        quitar = [p for p, x in d.items() if x["quitar"]]
        sig = dec[k + 1] if k + 1 < len(dec) else None
        paso = {"aplica_en": sig or "final", "piezas": d, "quitar": quitar}
        if len(quitar) >= 2:          # §8e · la combinación debe cumplir la regla frente a la completa
            paso["combinacion"] = combinacion_valida(tabla, cfg, quitar, d, [sig] if sig else usados, f_tabla, n,
                                                     progreso)
            paso["quitar"] = paso["combinacion"]["quitar_final"]
        informe["decisiones"][f"con_{'+'.join(map(str, usados))}"] = paso
        (dir_ablacion(cfg) / "decisiones.json").write_text(
            json.dumps(informe, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    for k, x in informe["decisiones"].items():
        progreso(f"{k} → aplica en {x['aplica_en']}: quitar {x['quitar']}", flush=True)
        for p, y in x["piezas"].items():
            progreso(f"    {p:13s} Δmezcla = {100 * y['delta_mezcla']:+.2f} % IC95 [{100 * y['ic95'][0]:+.2f}, "
                     f"{100 * y['ic95'][1]:+.2f}] cob {y['cobertura80_sin']:.3f} ciclo {y['ciclo_sin']:.3f}/"
                     f"{y['ciclo_con']:.3f} niveles {y['niveles_max_sd']:.2f} → {y['estado']}", flush=True)
    return informe


def combinacion_valida(tabla, cfg: dict, quitar: list[str], d: dict, cortes: list[int], f_tabla, n: int,
                       progreso=print) -> dict:
    """§8e · entrena la configuración sin todas las piezas `quitar` (n redes) en `cortes` (y su corte de calibración)
    y la compara con la completa con la misma regla; si no la cumple, reincorpora las piezas una a una empezando por
    la de MAYOR Δ (la de evidencia más débil para quitarla) hasta que la cumpla."""
    sem = list(cfg["semillas"][:n])
    hist = []
    q = sorted(quitar, key=lambda p: d[p]["delta_mezcla"])
    while len(q) >= 2:
        nombre = "sin_" + "+".join(sorted(q))
        cv = configuracion_sin(cfg, q)
        necesarios = sorted(set(cortes) | {c - 1 for c in cortes})
        redes = [(cv, a, s) for a in necesarios for s in sem]
        if PIEZA_INFERENCIA in q and len(q) == 1:
            redes = []
        entrenar(redes, cfg, f_tabla, progreso)
        predecir([(nombre, cv, a) for a in necesarios], cfg, f_tabla, n, progreso)
        con = mezcla_calibrada(tabla, cfg, "completa", cortes, n)
        sin = mezcla_calibrada(tabla, cfg, nombre, cortes, n)
        r = regla(comparar(con, sin, cfg), "+".join(q), [_salv(cfg, "completa", a, n) for a in cortes],
                  [_salv(cfg, nombre, a, n) for a in cortes], cfg)
        hist.append({"piezas": list(q), **{k: r[k] for k in ("delta_mezcla", "ic95", "cobertura80_sin", "estado")}})
        if r["quitar"]:
            return {"historial": hist, "quitar_final": list(q)}
        q = q[:-1]          # reincorpora la de mayor Δ
    return {"historial": hist, "quitar_final": list(q)}
