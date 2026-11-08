"""F2-c · Familiaridad: ¿rinden más (por encima de lo aditivo) los quintetos cuyos jugadores ya compartieron pista?
Prerregistro en configs/ecosistema_v41.yaml → f2.familiaridad (08-11-2026, antes de calcular).

Por liga-temporada s (tramos del contrato v4.0, resultado y = 0,75·y_real + 0,25·y_xp de la regla F2-e):

    x_i = Σ_{parejas del local} g(f_jk) − Σ_{parejas del visitante} g(f_jk),   g(f) = log(1 + f/100)

con f_jk = posesiones que j y k compartieron en pista (mismo lado, cualquier liga) en la temporada s−1. δ se estima JUNTO al
RAPM ridge de la liga-temporada por Frisch–Waugh–Lovell:

    x̃ = x − X (XᵀWX + Λ)⁻¹ XᵀW x,   δ̂ = x̃ᵀW y / x̃ᵀW x

(Λ = λ en los jugadores, λ por validación interna con pliegues por partido como el RAPM (a) de la F0; ≈ 0 en los fijos).
IC95 robusto por partido (sándwich con los residuos de y parcializada) y agregado entre ligas-temporada por inverso de la
varianza. EMD = (1,96 + 0,84)·EE agregado: exacto para un estimador lineal (sembrar δ·x en y desplaza δ̂ en δ).
Salida: data/modelos/v4_1/impacto_pista/familiaridad.json (y por liga-temporada en familiaridad_por_lt.csv).
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from . import beneficio_xp as BX
from . import config as CE
from . import orden_sinergias as OS


def pares_previos(cfg: dict) -> dict[str, dict]:
    """{temporada s: {(p, q): posesiones compartidas en s−1}} con los tramos del contrato de todas las ligas."""
    from .impacto_pista import pares_temporada
    from .sinergia_mixta import tramos_ampliados
    tr = tramos_ampliados(cfg)
    temps = sorted(tr["temporada"].unique())
    out = {}
    for i, s in enumerate(temps[1:], start=1):
        out[s] = pares_temporada(tr[tr["temporada"] == temps[i - 1]])
    return out


def x_tramos(lt: OS.LT, pares: dict) -> np.ndarray:
    """x_i = Σ g(f) de las 10 parejas del local − Σ de las del visitante."""
    pers = np.array([k.split("|")[0] for k in lt.claves], dtype=object)
    def lado(P):
        tot = np.zeros(lt.n)
        for a in range(5):
            for b in range(a + 1, 5):
                p, q = pers[P[:, a]], pers[P[:, b]]
                lo, hi = np.where(p < q, p, q), np.where(p < q, q, p)
                tot += np.log1p(np.array([pares.get((u, v), 0.0) for u, v in zip(lo, hi)]) / 100.0)
        return tot
    return lado(lt.PA) - lado(lt.PB)


def delta_lt(lt: OS.LT, x: np.ndarray, cfg: dict) -> dict:
    alfa = float(cfg["beneficio_xp"]["resultado"].get("alfa_adoptado", 0.75))
    y = alfa * lt.y + (1 - alfa) * np.nan_to_num(lt.y_xp, nan=0.0)
    X = OS.diseno(lt)
    _, info = OS.ajustar_aditivo(lt.con_y(y), X, np.ones(lt.n, bool), "a", cfg["orden_sinergias"], semilla=1)
    G, by = OS._gram(X, y, lt.w)
    bx = np.asarray(X.T @ (lt.w * x)).ravel()
    cy, cx = OS._resolver(G, by, lt.nP, info["lambda"]), OS._resolver(G, bx, lt.nP, info["lambda"])
    xt, yt = x - X @ cx, y - X @ cy
    den = float(np.sum(lt.w * xt * x))
    if not np.isfinite(den) or den <= 0:
        return {}
    d = float(np.sum(lt.w * xt * y) / den)
    e = yt - d * xt
    sg = pd.Series(lt.w * xt * e).groupby(lt.partido).sum().to_numpy()
    ee = float(np.sqrt(np.sum(sg ** 2)) / den)
    return {"liga": lt.liga, "temporada": lt.temporada, "delta": d, "ee": ee, "tramos": int(lt.n), "lambda": info["lambda"],
            "x_media_abs": float(np.average(np.abs(x), weights=lt.w)), "frac_tramos_x_no_nulo": float(np.mean(x != 0))}


def agregar(t: pd.DataFrame) -> dict:
    t = t[np.isfinite(t["ee"]) & (t["ee"] > 0)]
    w = 1.0 / t["ee"] ** 2
    d = float(np.sum(w * t["delta"]) / w.sum())
    ee = float(1.0 / np.sqrt(w.sum()))
    q = float(np.sum(w * (t["delta"] - d) ** 2))           # heterogeneidad (Cochran)
    return {"delta": d, "ee": ee, "ic95": [d - 1.96 * ee, d + 1.96 * ee], "excluye_0": bool(abs(d) > 1.96 * ee),
            "emd_80": float((1.96 + 0.8416) * ee), "ligas_temporada": int(len(t)), "Q_cochran": q, "gl": int(len(t) - 1)}


def ejecutar(cfg: dict, progreso=print) -> dict:
    t0 = time.time()
    pp = pares_previos(cfg)
    dq = CE.RAIZ / cfg["puntos_esperados"]["salidas"]["no_versionado"] / "tramos"
    filas = []
    for s, pares in pp.items():
        if not (dq / s).exists():
            continue
        for f in sorted((dq / s).glob("*.csv.gz")):
            liga = f.name.split(".")[0]
            lt = BX._lt(cfg, s, liga)
            if lt is None or lt.n < 500 or lt.nP > int(cfg["potencia"]["trios"]["max_jugadores_lt"]):
                continue
            r = delta_lt(lt, x_tramos(lt, pares), cfg)
            if r:
                filas.append(r)
                if progreso:
                    progreso(f"  familiaridad {s} {liga}: δ {r['delta']:+.3f} ± {r['ee']:.3f} · {time.time() - t0:.0f} s", flush=True)
    T = pd.DataFrame(filas)
    elite = set(cfg["comunes"]["segmentos"]["elite_club"])
    temps = sorted(T["temporada"].unique())
    res = {"generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "definicion": cfg["f2"]["familiaridad"],
           "global": agregar(T), "elite_club": agregar(T[T["liga"].isin(elite)]),
           "hasta_temporada": {s: agregar(T[T["temporada"] <= s]) for s in temps},      # δ ≤ t para el Impacto del corte t
           "segundos": round(time.time() - t0)}
    d = CE.dir_salida(cfg, "impacto_pista")
    T.round(5).to_csv(d / "familiaridad_por_lt.csv", index=False)
    (d / "familiaridad.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return res


# =============================================================================================== robustez (POST HOC, 08-11-2026)
def _delta_x(lt: OS.LT, X, G, y: np.ndarray, x: np.ndarray, lam: float) -> tuple[float, float]:
    by = np.asarray(X.T @ (lt.w * y)).ravel()
    bx = np.asarray(X.T @ (lt.w * x)).ravel()
    cy, cx = OS._resolver(G, by, lt.nP, lam), OS._resolver(G, bx, lt.nP, lam)
    xt, yt = x - X @ cx, y - X @ cy
    den = float(np.sum(lt.w * xt * x))
    if den <= 0:
        return np.nan, np.nan
    d = float(np.sum(lt.w * xt * y) / den)
    sg = pd.Series(lt.w * xt * (yt - d * xt)).groupby(lt.partido).sum().to_numpy()
    return d, float(np.sqrt(np.sum(sg ** 2)) / den)


def robustez(cfg: dict, lambdas=(10.0, 100.0), progreso=print) -> dict:
    """[POST HOC] ¿Es δ̂ un sesgo de la contracción del ridge (los que siguen juntos suelen ser los buenos y el ridge los
    infravalora)? (i) δ con λ casi sin contracción; (ii) placebo: familiaridad FUTURA (posesiones que compartirán en s+1,
    parejas sin pasado común en s−1): si también «predice», δ̂ recoge selección y no química; (iii) las dos a la vez."""
    from .impacto_pista import pares_temporada
    from .sinergia_mixta import tramos_ampliados
    t0 = time.time()
    tr = tramos_ampliados(cfg)
    temps = sorted(tr["temporada"].unique())
    pares = {s: pares_temporada(tr[tr["temporada"] == s]) for s in temps}
    alfa = float(cfg["beneficio_xp"]["resultado"].get("alfa_adoptado", 0.75))
    dq = CE.RAIZ / cfg["puntos_esperados"]["salidas"]["no_versionado"] / "tramos"
    filas = []
    for i, s in enumerate(temps[1:-1], start=1):
        prev, fut = pares[temps[i - 1]], pares[temps[i + 1]]
        fut_nuevo = {k: v for k, v in fut.items() if k not in prev}
        for f in sorted((dq / s).glob("*.csv.gz")):
            liga = f.name.split(".")[0]
            lt = BX._lt(cfg, s, liga)
            if lt is None or lt.n < 500 or lt.nP > int(cfg["potencia"]["trios"]["max_jugadores_lt"]):
                continue
            y = alfa * lt.y + (1 - alfa) * np.nan_to_num(lt.y_xp, nan=0.0)
            X = OS.diseno(lt)
            G, _ = OS._gram(X, y, lt.w)
            _, info = OS.ajustar_aditivo(lt.con_y(y), X, np.ones(lt.n, bool), "a", cfg["orden_sinergias"], semilla=1)
            x, xf = x_tramos(lt, prev), x_tramos(lt, fut_nuevo)
            fila = {"liga": liga, "temporada": s, "lambda_cv": info["lambda"]}
            for lam in (info["lambda"],) + tuple(lambdas):
                k = "cv" if lam == info["lambda"] and lam not in lambdas else f"l{int(lam)}"
                fila[f"delta_{k}"], fila[f"ee_{k}"] = _delta_x(lt, X, G, y, x, lam)
                fila[f"placebo_{k}"], fila[f"ee_placebo_{k}"] = _delta_x(lt, X, G, y, xf, lam)
                # conjunto: x parcializada también por x_futura (FWL con las dos columnas añadidas)
                Xa = __import__("scipy.sparse", fromlist=["hstack"]).hstack([X, xf[:, None]]).tocsr()
                Ga, _ = OS._gram(Xa, y, lt.w)
                Ga[-1, -1] += 1e-6
                fila[f"conjunto_{k}"], fila[f"ee_conjunto_{k}"] = _delta_x_ext(lt, Xa, Ga, y, x, lam)
            filas.append(fila)
            if progreso:
                progreso(f"  robustez {s} {liga}: δ cv {fila['delta_cv']:+.3f} · λ10 {fila['delta_l10']:+.3f} · placebo cv "
                         f"{fila['placebo_cv']:+.3f} · conjunto {fila['conjunto_cv']:+.3f} · {time.time() - t0:.0f} s", flush=True)
    T = pd.DataFrame(filas)
    res = {"etiqueta": "POST HOC", "generado": time.strftime("%Y-%m-%dT%H:%M:%S")}
    for k in ["cv"] + [f"l{int(l)}" for l in lambdas]:
        for pref in ("delta", "placebo", "conjunto"):
            ee = "ee" if pref == "delta" else f"ee_{pref}"
            res[f"{pref}_{k}"] = agregar(T.rename(columns={f"{pref}_{k}": "delta", f"{ee}_{k}": "ee"})[["delta", "ee", "liga", "temporada"]])
    res["aleatorios_DL_cv"] = dersimonian_laird(T["delta_cv"], T["ee_cv"])
    d = CE.dir_salida(cfg, "impacto_pista")
    T.round(5).to_csv(d / "familiaridad_robustez_por_lt.csv", index=False)
    (d / "familiaridad_robustez.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return res


def _delta_x_ext(lt: OS.LT, Xa, Ga, y, x, lam) -> tuple[float, float]:
    """Como _delta_x con una columna extra sin penalizar al final del diseño (la familiaridad futura)."""
    by = np.asarray(Xa.T @ (lt.w * y)).ravel()
    bx = np.asarray(Xa.T @ (lt.w * x)).ravel()
    cy, cx = OS._resolver(Ga, by, lt.nP, lam), OS._resolver(Ga, bx, lt.nP, lam)
    xt, yt = x - Xa @ cx, y - Xa @ cy
    den = float(np.sum(lt.w * xt * x))
    if den <= 0:
        return np.nan, np.nan
    d = float(np.sum(lt.w * xt * y) / den)
    sg = pd.Series(lt.w * xt * (yt - d * xt)).groupby(lt.partido).sum().to_numpy()
    return d, float(np.sqrt(np.sum(sg ** 2)) / den)


def dersimonian_laird(d, ee) -> dict:
    d, ee = np.asarray(d, float), np.asarray(ee, float)
    ok = np.isfinite(d) & np.isfinite(ee) & (ee > 0)
    d, v = d[ok], ee[ok] ** 2
    w = 1 / v
    m = np.sum(w * d) / w.sum()
    q = np.sum(w * (d - m) ** 2)
    tau2 = max((q - (len(d) - 1)) / (w.sum() - np.sum(w ** 2) / w.sum()), 0.0)
    ws = 1 / (v + tau2)
    mr = float(np.sum(ws * d) / ws.sum())
    er = float(1 / np.sqrt(ws.sum()))
    return {"delta": mr, "ee": er, "ic95": [mr - 1.96 * er, mr + 1.96 * er], "tau": float(np.sqrt(tau2)), "k": int(len(d))}
