"""¿Mejora el punto esperado al resultado real como variable de los tramos? (propuesta 2 aprobada por el CEO el 07-11-2026).

Por liga-temporada, con los tramos del contrato v4.0 y el resultado de tramo
    y_α = α·y + (1 − α)·y_xp        (α = 1: puntos reales; α = 0: puntos esperados; intermedios: mezcla)
se mide:
  1. ruido: varianza residual por posesión del RAPM ridge (λ por validación interna) ajustado con y_α;
  2. estabilidad: correlación ponderada de β entre dos mitades de partidos (jugadores con ≥ min_pos en las dos);
  3. validez [la prueba que decide]: β ajustado con y_α en una mitad predice el diferencial REAL (y) de los tramos de
     la otra mitad; R² fuera de muestra frente al intercepto solo, promediado en las dos direcciones.
IC95 de las diferencias frente a α = 1 por bootstrap de ligas-temporada. La regla de adopción está prerregistrada en el
YAML (beneficio_xp.regla) antes de ejecutar.

Salida: data/modelos/v4_1/puntos_esperados/beneficio.json.
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from . import config as CE
from . import orden_sinergias as OS
from . import puntos_esperados as PE


def _lt(cfg: dict, temp: str, liga: str) -> OS.LT | None:
    from .. import rapm
    d = PE.cargar_tramos(cfg, temp, liga)
    if d.empty:
        return None
    ids = pd.concat([d["quinteto_a"].astype(str).str.split("|").explode(), d["quinteto_b"].astype(str).str.split("|").explode()])
    mp = rapm._mapa_persona(liga, ids)
    conv = lambda q: tuple(f"{mp[x]}|{temp}" for x in str(q).split("|"))  # noqa: E731
    tr = pd.DataFrame({"liga": liga, "temporada": temp, "game_id": d["game_id"].to_numpy(), "team_a": d["team_a"].astype(str),
                       "team_b": d["team_b"].astype(str), "clutch": False, "playoffs": False, "poss": d["poss"].to_numpy(float),
                       "A": d["quinteto_a"].map(conv).to_numpy(), "B": d["quinteto_b"].map(conv).to_numpy(),
                       "y": (100.0 * (d["a_pts"] - d["b_pts"]) / d["poss"]).to_numpy(float)})
    lt = OS.preparar(tr, CE.semilla(cfg, f"beneficio|{liga}|{temp}"))
    lt.y_xp = d["y_xp"].to_numpy(float)
    return lt


def _ajuste(lt: OS.LT, X, filas, y, cfg_o, sem) -> np.ndarray:
    return OS.ajustar_aditivo(lt.con_y(y), X, filas, "a", cfg_o, semilla=sem)[0]


def metricas_lt(lt: OS.LT, alfas, cfg: dict) -> dict:
    co = cfg["orden_sinergias"]
    cb = cfg["beneficio_xp"]
    X = OS.diseno(lt)
    rng = np.random.default_rng(CE.semilla(cfg, f"mitades|{lt.liga}|{lt.temporada}"))
    mitad = (rng.permutation(int(lt.partido.max()) + 1) % 2).astype(bool)[lt.partido]   # dos mitades de partidos al azar
    out = {}
    w = lt.w
    for a in alfas:
        ya = a * lt.y + (1 - a) * lt.y_xp
        coef_all = _ajuste(lt, X, np.ones(lt.n, bool), ya, co, 1)
        r = ya - X @ coef_all
        ruido = float(np.sum(w * r * r) / lt.n)
        b = {}
        r2 = []
        for h in (False, True):
            f = mitad == h
            c = _ajuste(lt, X, f, ya, co, 2 + int(h))
            b[h] = c[:lt.nP]
            ev = ~f
            pred = X[ev] @ c
            yv = lt.y[ev]
            base = np.sum(w[ev] * yv) / np.sum(w[ev])
            r2.append(1 - np.sum(w[ev] * (yv - pred) ** 2) / np.sum(w[ev] * (yv - base) ** 2))
        # estabilidad: jugadores con ≥ min_pos en las dos mitades
        Xp = abs(X[:, :lt.nP])
        pos = [np.asarray(Xp[mitad == h].T @ w[mitad == h]).ravel() for h in (False, True)]
        ok = (pos[0] >= cb["min_pos_estabilidad"]) & (pos[1] >= cb["min_pos_estabilidad"])
        if ok.sum() >= 10:
            ww = np.minimum(pos[0], pos[1])[ok]
            x0, x1 = b[False][ok], b[True][ok]
            m0, m1 = np.average(x0, weights=ww), np.average(x1, weights=ww)
            cov = np.average((x0 - m0) * (x1 - m1), weights=ww)
            est = float(cov / np.sqrt(np.average((x0 - m0) ** 2, weights=ww) * np.average((x1 - m1) ** 2, weights=ww)))
        else:
            est = np.nan
        out[str(a)] = {"ruido": ruido, "estabilidad_beta": est, "r2_fuera_muestra_y_real": float(np.mean(r2)),
                       "jugadores_estabilidad": int(ok.sum())}
    return out


def ejecutar(cfg: dict, segmento: str = "global", progreso=print) -> dict:
    cb, cm = cfg["beneficio_xp"], cfg["comunes"]
    elite = set(cm["segmentos"]["elite_club"])
    alfas = [float(a) for a in cb["alfas"]]
    t0 = time.time()
    filas = []
    for temp in cb["temporadas"]:
        d = CE.RAIZ / cfg["puntos_esperados"]["salidas"]["no_versionado"] / "tramos" / temp
        for f in sorted(d.glob("*.csv.gz")) if d.exists() else []:
            liga = f.name.split(".")[0]
            if segmento == "elite_club" and liga not in elite:
                continue
            lt = _lt(cfg, temp, liga)
            if lt is None or lt.n < 500:
                continue
            m = metricas_lt(lt, alfas, cfg)
            for a, v in m.items():
                filas.append({"liga": liga, "temporada": temp, "alfa": float(a), "tramos": lt.n, **v})
            if progreso:
                progreso(f"  beneficio {temp} {liga}: " + " · ".join(
                    f"α={a}: R² {v['r2_fuera_muestra_y_real']:.4f}, est {v['estabilidad_beta']:.2f}" for a, v in m.items()) +
                    f" · {time.time() - t0:.0f} s", flush=True)
    D = pd.DataFrame(filas)
    ds = CE.dir_salida(cfg, "puntos_esperados")
    D.to_csv(ds / "beneficio_por_lt.csv", index=False, float_format="%.6g")     # antes del resumen (reanudable)
    return resumir(cfg, D)


def resumir(cfg: dict, D: pd.DataFrame) -> dict:
    cb, cm = cfg["beneficio_xp"], cfg["comunes"]
    elite = set(cm["segmentos"]["elite_club"])
    alfas = [float(a) for a in cb["alfas"]]
    rng = np.random.default_rng(int(cm["semilla_bootstrap"]))
    res = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "regla": cb["regla"], "segmentos": {}}
    for seg in ("global", "elite_club"):
        x = D if seg == "global" else D[D["liga"].isin(elite)]
        if x.empty:
            continue
        lts = sorted(set(zip(x["liga"], x["temporada"])))
        ix = pd.MultiIndex.from_tuples(lts, names=["liga", "temporada"])
        piv = {k: x.pivot_table(index=["liga", "temporada"], columns="alfa", values=k, dropna=False).reindex(ix) for k in
               ("ruido", "estabilidad_beta", "r2_fuera_muestra_y_real")}
        r = {"ligas_temporada": len(lts), "por_alfa": {}}
        idx = rng.integers(0, len(lts), size=(int(cm["bootstrap"]), len(lts)))
        for a in alfas:
            e = {}
            for k, P in piv.items():
                v = P[a].to_numpy(float)
                e[k] = float(np.nanmean(v))
                if a != 1.0:
                    dif = P[a].to_numpy(float) - P[1.0].to_numpy(float)
                    bs = np.nanmean(dif[idx], axis=1)
                    e[f"{k}_dif_frente_y_real"] = float(np.nanmean(dif))
                    e[f"{k}_dif_ic95"] = [float(np.nanquantile(bs, 0.025)), float(np.nanquantile(bs, 0.975))]
                    e[f"{k}_lt_mejor"] = int(np.nansum(dif > 0)) if k != "ruido" else int(np.nansum(dif < 0))
            r["por_alfa"][str(a)] = e
        r2 = {a: r["por_alfa"][str(a)]["r2_fuera_muestra_y_real"] for a in alfas}
        r["alfa_mejor_r2"] = max(r2, key=r2.get)
        res["segmentos"][seg] = r
    ds = CE.dir_salida(cfg, "puntos_esperados")
    (ds / "beneficio.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return res
