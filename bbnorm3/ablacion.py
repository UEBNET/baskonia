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
    f_tabla, cfg_v, nombre, anio, semillas, destino, hilos = args
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
    return f"{Path(destino).name} {len(r)} filas {time.time() - t0:.0f} s"


def ruta_pred(cfg: dict, nombre: str, anio: int, n_semillas: int) -> Path:
    return dir_ablacion(cfg) / f"pred_{nombre}_{anio}_n{n_semillas}.csv.gz"


def predecir(trabajos: list[tuple[str, dict, int]], cfg: dict, f_tabla: Path, n_semillas: int, progreso=print) -> None:
    a = cfg["ablacion"]
    sem = list(cfg["semillas"][:n_semillas])
    pend = []
    for nombre, cfg_v, anio in trabajos:
        dst = ruta_pred(cfg, nombre, anio, n_semillas)
        if not dst.exists():
            pend.append((str(f_tabla), cfg_v, nombre, anio, sem, dst, int(a.get("hilos", 1))))
    if not pend:
        return
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=int(a.get("procesos", 4))) as ex:
        fut = [ex.submit(_predecir_uno, p) for p in pend]
        for k, f in enumerate(as_completed(fut), 1):
            msg = f.result()
            if progreso:
                progreso(f"  predicción [{k}/{len(pend)}] {msg} · {time.time() - t0:.0f} s", flush=True)


# ------------------------------------------------------------------------------------------ evaluación
def cargar_pred(cfg: dict, nombre: str, anio: int, n_semillas: int) -> pd.DataFrame:
    return pd.read_csv(ruta_pred(cfg, nombre, anio, n_semillas))


def calibradas(cfg: dict, nombre: str, anios: list[int], n_semillas: int) -> pd.DataFrame:
    """Predicciones de la variante en los cortes `anios`, recalibradas con el corte anterior de la MISMA variante."""
    v = cfg["validacion"]
    out = []
    for a in anios:
        cal = cargar_pred(cfg, nombre, a - 1, n_semillas)
        fac = examen.factores_calibracion(cal, int(v["min_casos_grupo"]))
        out.append(examen.aplicar_calibracion(cargar_pred(cfg, nombre, a, n_semillas), fac))
    r = pd.concat(out, ignore_index=True)
    return r.assign(real_r=r["real"].round(3))


CLAVE_PRED = ["metrica", "anio", "persona_id", "liga_o", "liga_d", "real_r"]


def comparar(con: pd.DataFrame, sin: pd.DataFrame, cfg: dict) -> dict:
    """MAE_sin / MAE_con − 1 (media de métricas) con IC 95 % bootstrap por persona y cobertura de la variante sin."""
    v = cfg["validacion"]
    a = con.drop_duplicates(CLAVE_PRED, keep=False)
    b = sin.drop_duplicates(CLAVE_PRED, keep=False)
    j = a[CLAVE_PRED + ["real", "v3"]].merge(b[CLAVE_PRED + ["v3", "dentro_80_v3c"]], on=CLAVE_PRED,
                                             suffixes=("_con", "_sin"))
    bs = examen.bootstrap_persona(j, "v3_sin", "v3_con", int(v["bootstrap"]), int(v["semilla_bootstrap"]))
    lo, hi = v["cobertura_objetivo"]
    cob = float(j["dentro_80_v3c"].mean())
    quitar = bool(bs["ic95"][0] <= 0 and lo <= cob <= hi)
    return {"casos": int(len(j)), "mae_rel_sin_frente_con": bs["estimacion"], "ic95": bs["ic95"],
            "cobertura80_sin": cob, "cobertura80_con": float(a["dentro_80_v3c"].mean()), "quitar": quitar}


def decidir(cfg: dict, anios: list[int], n_semillas: int, base: str = "completa",
            nombres: dict[str, str] | None = None) -> dict:
    """Decisión pieza a pieza con los cortes `anios` (todas las piezas frente a la misma base)."""
    con = calibradas(cfg, base, anios, n_semillas)
    res = {}
    for p in cfg["ablacion"]["piezas"]:
        nombre = (nombres or {}).get(p, f"sin_{p}")
        try:
            sin = calibradas(cfg, nombre, anios, n_semillas)
        except FileNotFoundError:
            continue
        res[p] = comparar(con, sin, cfg)
    return res


def main(tabla: pd.DataFrame, cfg: dict, fase: str = "todo", progreso=print) -> dict:
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
    informe = {"regla": "quitar la pieza si el IC 95 % de MAE_sin/MAE_con − 1 tiene extremo inferior ≤ 0 y la "
                        f"cobertura recalibrada sin ella sigue en {cfg['validacion']['cobertura_objetivo']}",
               "redes_por_variante": n, "decisiones": {}}
    for k, t in enumerate(dec):
        usados = [x for x in dec if x <= t]
        d = decidir(cfg, usados, n)
        informe["decisiones"][f"con_{'+'.join(map(str, usados))}"] = {
            "aplica_en": dec[k + 1] if k + 1 < len(dec) else "final",
            "piezas": d, "quitar": [p for p, x in d.items() if x["quitar"]]}
    (dir_ablacion(cfg) / "decisiones.json").write_text(json.dumps(informe, indent=1, ensure_ascii=False, default=float),
                                                       encoding="utf-8")
    for k, x in informe["decisiones"].items():
        progreso(f"{k} → aplica en {x['aplica_en']}: quitar {x['quitar']}", flush=True)
        for p, y in x["piezas"].items():
            progreso(f"    {p:13s} sin/con − 1 = {100 * y['mae_rel_sin_frente_con']:+.2f} % "
                     f"IC95 [{100 * y['ic95'][0]:+.2f}, {100 * y['ic95'][1]:+.2f}] cob {y['cobertura80_sin']:.3f}"
                     f" → {'quitar' if y['quitar'] else 'conservar'}", flush=True)
    return informe
