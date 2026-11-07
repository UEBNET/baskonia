"""Examen de la F1 (criterios prerregistrados §6.1, `criterios.f1`) sobre equipos REALES de la temporada base.

Batería por equipo (todos los de EuroLeague + EuroCup + ACB y una muestra al azar del resto):
  1. una alta sin rol fijado (modo paridad): Δ̂Net frente a `Equipo.delta` de la capa 4 v4.0 con la misma semilla;
  2. una alta con rol TITULAR + una baja;
  3. dos altas (TITULAR y ROTACION) + dos bajas: Shapley exacto (|M| = 4);
  4. tres bajas + dos altas: Shapley por permutaciones (|M| = 5), con su error Monte Carlo.
Criterios: paridad ≤ 0,01 pts/100; restricciones físicas en el 100 % de los escenarios (Σ minutos exacta, minutos en
[0, duración], uso que suma el 100 %); Σ Shapley + diferencia de la base + regresión = Δ total con tolerancia numérica.
Las altas son jugadores reales de otros equipos de la misma liga (al azar con semilla); las bajas, los de más minutos.

Salidas: data/modelos/v4_1/escenarios/{examen_f1.json, examen_f1_escenarios.csv}.
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from . import config as CE
from .escenarios import Ecosistema


def _net_actual(temp: str, liga: str, team: str) -> float:
    p = CE.RAIZ / "data" / "processed" / temp / "quintetos" / liga / "equipos.csv"
    if not p.exists():
        return 0.0
    e = pd.read_csv(p)
    e = e[(e["fase"] == "regular") & (e["team_id"].astype(str) == str(team))]
    return float(e["net_rtg_aj"].iloc[0]) if len(e) and np.isfinite(e["net_rtg_aj"].iloc[0]) else 0.0


def ejecutar(cfg: dict, progreso=print) -> dict:
    ce = cfg["f1"]["examen"]
    temp = ce["temporada_base"]
    n_sim = int(ce["simulaciones"])
    crit = cfg["criterios"]["f1"]
    elite = set(cfg["comunes"]["segmentos"]["elite_club"])
    t0 = time.time()
    E = Ecosistema(cfg, temp, progreso=progreso)
    eq = E.eq
    r = eq.roles[eq.roles["temporada"] == temp].copy()
    r["team_id"] = r["team_id"].astype(str)
    eqs = r.groupby(["liga", "team_id"]).size().reset_index(name="n")
    eqs = eqs[eqs["n"] >= 10]
    rng = np.random.default_rng(CE.semilla(cfg, "examen_f1"))
    el = eqs[eqs["liga"].isin(elite)]
    otros = eqs[~eqs["liga"].isin(elite)]
    otros = otros.iloc[rng.permutation(len(otros))[: int(ce["muestra_resto"])]]
    lista = pd.concat([el, otros], ignore_index=True)
    filas = []
    for i, (liga, team) in enumerate(zip(lista["liga"], lista["team_id"])):
        g = r[(r["liga"] == liga) & (r["team_id"] == team)].sort_values("min_total", ascending=False)
        plant = [(p, float(x)) for p, x in zip(g["persona_id"], g["presencia"])]
        cand = r[(r["liga"] == liga) & (r["team_id"] != team) & (r["min_total"] > 300)]["persona_id"].drop_duplicates()
        cand = [p for p in cand if p not in set(g["persona_id"])]
        if len(cand) < 2:
            continue
        a1, a2 = list(rng.choice(cand, 2, replace=False))
        b = list(g["persona_id"].iloc[:3])
        net = _net_actual(temp, liga, team)
        sem = int(rng.integers(0, 10 ** 6))
        escs = [("1_alta_paridad", [(a1, None)], []), ("2_alta_rol_y_baja", [(a1, "TITULAR")], b[:1]),
                ("3_cuatro_movimientos", [(a1, "TITULAR"), (a2, "ROTACION")], b[:2]),
                ("4_cinco_movimientos", [(a1, "TITULAR"), (a2, "ROTACION")], b[:3])]
        for nombre, altas, bajas in escs:
            try:
                t1 = time.time()
                s = E.simular(liga, team, plant, altas, bajas, net, n_sim=n_sim, semilla=sem, paridad_capa4=(nombre == "1_alta_paridad"))
                fila = {"liga": liga, "team_id": team, "escenario": nombre, "movimientos": len(altas) + len(bajas),
                        "segundos": round(time.time() - t1, 2), "delta_net": s["equipo"]["delta_net"],
                        "lo80": s["equipo"]["lo80"], "hi80": s["equipo"]["hi80"], **s["control"],
                        "error_mc_shapley_max": float(s["atribucion_equipo"]["error_mc"].max()) if len(s["atribucion_equipo"]) else 0.0}
                if nombre == "1_alta_paridad":
                    ref = eq.delta(liga, team, plant, [a1], [], net, n_sim=n_sim, semilla=sem)
                    fila["paridad_dif"] = float(s["equipo"]["delta_net"] - ref["delta_net"])
                    if abs(fila["paridad_dif"]) > 1e-12:            # diagnóstico: ¿la diferencia es sólo la corrección P5?
                        s0 = E.simular(liga, team, plant, altas, bajas, net, n_sim=n_sim, semilla=sem, paridad_capa4=True,
                                       aplicar_p5=False)
                        fila["paridad_dif_sin_p5"] = float(s0["equipo"]["delta_net"] - ref["delta_net"])
                        fila["capa4_sims_sin_todos_los_minutos"] = float(
                            np.mean([(abs(e["M"].sum(1) - 5 * e["gm"]) > 1e-6).mean() for e in [E.escenario(
                                liga, team, plant, {}, n_sim, sem, aplicar_p5=False)]]))
                filas.append(fila)
            except Exception as ex:  # noqa: BLE001
                filas.append({"liga": liga, "team_id": team, "escenario": nombre, "error": str(ex)[:200]})
        if progreso:
            progreso(f"  F1 examen {i + 1}/{len(lista)} {liga} {team} · {time.time() - t0:.0f} s", flush=True)
    D = pd.DataFrame(filas)
    ok = D[D.get("error").isna()] if "error" in D else D
    tol_id = float(crit["shapley_suma_delta_tolerancia"])
    fis = (ok["suma_minutos_max_desvio"] < 1e-6) & (ok["minutos_fuera_de_limites"] == 0) & (ok["uso_desvio_max"] < 1e-6)
    par = ok["paridad_dif"].dropna().abs()
    res = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "temporada_base": temp, "n_sim": n_sim,
           "equipos": int(lista.shape[0]), "escenarios": int(len(D)), "errores": int(D["error"].notna().sum()) if "error" in D else 0,
           "paridad": {"n": int(len(par)), "max_abs_dif": float(par.max()) if len(par) else None,
                       "exacta": int((par <= 1e-12).sum()),
                       "max_abs_dif_sin_p5": float(ok["paridad_dif_sin_p5"].abs().max()) if "paridad_dif_sin_p5" in ok else 0.0,
                       "casos_corregidos_por_p5": ok.loc[ok.get("paridad_dif_sin_p5", pd.Series(dtype=float)).notna(),
                                                         ["liga", "team_id", "paridad_dif", "capa4_sims_sin_todos_los_minutos"]].to_dict("records")
                       if "paridad_dif_sin_p5" in ok else [],
                       "tolerancia": float(crit["paridad_capa4_pts100"]),
                       "cumple": bool(len(par) and par.max() <= float(crit["paridad_capa4_pts100"]))},
           "restricciones_fisicas": {"frac_escenarios_ok": float(fis.mean()), "cumple": bool(fis.mean() == 1.0)},
           "shapley": {"max_abs_identidad": float(ok["identidad_contable"].abs().max()), "tolerancia": tol_id,
                       "cumple": bool(ok["identidad_contable"].abs().max() <= tol_id),
                       "error_mc_permutaciones_mediana": float(ok.loc[ok["movimientos"] > 4, "error_mc_shapley_max"].median())
                       if (ok["movimientos"] > 4).any() else None},
           "tiempo_por_escenario_mediana_s": {k: float(v) for k, v in ok.groupby("escenario")["segundos"].median().items()},
           "segundos": round(time.time() - t0)}
    res["puerta_6_1"] = bool(res["paridad"]["cumple"] and res["restricciones_fisicas"]["cumple"] and res["shapley"]["cumple"]
                             and res["errores"] == 0)
    # lectura de la paridad con P5 (aprobada después de congelar §6.1): exacta sin la corrección física ⇒ la diferencia
    # es la corrección, no un error de la capa E
    res["paridad"]["cumple_salvo_correccion_p5"] = bool(res["paridad"]["max_abs_dif_sin_p5"] <= float(crit["paridad_capa4_pts100"]))
    d = CE.dir_salida(cfg, "escenarios")
    D.to_csv(d / "examen_f1_escenarios.csv", index=False, float_format="%.6g")
    (d / "examen_f1.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return res
