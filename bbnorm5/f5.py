"""F5 · Capa latente (encargo v5.0 §9): ejecuta los pasos en orden.

    python -m bbnorm5.f5 --config configs/v5/f5.yaml
    python -m bbnorm5.f5 --config configs/v5/f5.yaml --pasos seleccion_k

Pasos:
- seleccion_k: K ∈ {0, 3, 5, 6, 8} en un corte (regla fijada en la configuración)
- residuo: experimento del residuo de la temporada correlacionado entre métricas (K = 0 y K elegido)
- examen: K elegido (cambios correlacionados y diagonales) frente a K = 0, en los tres cortes
- final: ajuste con todas las temporadas, cargas rotadas (varimax) y alineadas con `cargas_referencia.csv` (orden y
  signo de los factores), estabilidad entre submuestras y cortes, perfil latente z de cada persona-temporada y sesgo
  por rol
- alinear: aplica esa alineación a la salida ya guardada de `final`, sin repetir el ajuste
- neuronal: alternativa neuronal frente al factorial (criterio: mejora con IC que no cruce 0 y sin peor calibración)
- figuras
"""
from __future__ import annotations

import argparse
import json
import pickle
import time

import numpy as np
import pandas as pd

from bbnorm5 import config as C

DIR = C.DIR_DATOS / "latente"


def _crps_relativo(c: pd.DataFrame, base: str, semilla: int) -> pd.DataFrame:
    c = c[c["cambio_liga"] == 0].copy()
    b = c[c["modelo"] == base].set_index(["metrica", "anio", "persona_v5"])["crps"]
    c = c.join(b.rename("crps_base"), on=["metrica", "anio", "persona_v5"])
    c["rel"] = c["crps"] / c.groupby("metrica")["crps_base"].transform("mean")
    c["cob80"] = (np.abs(c["pit"] - 0.5) <= 0.4).astype(float)
    t = c.groupby(["modelo", "metrica"]).agg(rel=("rel", "mean"), cob80=("cob80", "mean")).reset_index()
    s = t.groupby("modelo").agg(rel=("rel", "mean"), en_rango=("cob80", lambda x: ((x >= 0.76) & (x <= 0.84)).mean()))
    p = c.pivot_table(index=["metrica", "anio", "persona_v5"], columns="modelo", values="rel")
    rng = np.random.default_rng(semilla)
    boots = np.array([p.iloc[rng.integers(0, len(p), len(p))].mean().to_numpy() for _ in range(200)])
    s["ee"] = pd.Series(boots.std(axis=0), index=p.columns)
    # EE de la diferencia frente a cada modelo (pareada)
    return s


def seleccion_k(cfg: dict) -> dict:
    from bbnorm5.carrera import datos as CD
    from bbnorm5.latente import examen as LX
    from bbnorm5.medida import datos as DM
    o = CD.cargar()
    h = pd.read_csv(DM.DIR / "hiperparametros.csv")
    var = [(k, "corr") for k in cfg["seleccion_k"]["K"]]
    c, mods = LX.corte(o, h, cfg["seleccion_k"]["corte"], var, cfg["semilla"], cfg["ajuste"]["submuestra_personas"],
                       cfg["ajuste"]["maxiter"])
    DIR.mkdir(parents=True, exist_ok=True)
    c.to_parquet(DIR / "seleccion_k_casos.parquet")
    s = _crps_relativo(c, "K0_corr", cfg["semilla"])
    s["logL"] = [mods[(int(m[1:].split("_")[0]), "corr")]["logL"] for m in s.index]
    s["n_par"] = [mods[(int(m[1:].split("_")[0]), "corr")]["n_par"] for m in s.index]
    s["convergio"] = [mods[(int(m[1:].split("_")[0]), "corr")]["convergio"] for m in s.index]
    s["BIC"] = -2 * s["logL"] + s["n_par"] * np.log(cfg["ajuste"]["submuestra_personas"])
    cand = s.loc[[f"K{k}_corr" for k in (5, 6, 8) if f"K{k}_corr" in s.index]]
    mejor = cand["rel"].idxmin()
    elegido = mejor
    for m in sorted(cand.index, key=lambda z: int(z[1:].split("_")[0])):
        if cand.loc[m, "rel"] <= cand.loc[mejor, "rel"] + cand.loc[mejor, "ee"]:
            elegido = m
            break
    s["elegido"] = s.index == elegido
    s.to_csv(DIR / "seleccion_k.csv")
    with open(DIR / "seleccion_k_modelos.pkl", "wb") as f:
        pickle.dump({k: {kk: v[kk] for kk in ("K", "cambios", "x", "L", "psi", "logL")} for k, v in mods.items()}, f)
    return {"K_elegido": int(elegido[1:].split("_")[0])}


def residuo(cfg: dict) -> dict:
    """Experimento (tras la selección de K): residuo de la temporada correlacionado entre métricas (k_residuo factores),
    con K = 0 y con el K elegido, en el mismo corte que la selección."""
    from bbnorm5.carrera import datos as CD
    from bbnorm5.latente import examen as LX
    from bbnorm5.medida import datos as DM
    o = CD.cargar()
    h = pd.read_csv(DM.DIR / "hiperparametros.csv")
    kr = cfg["ajuste"]["k_residuo"]
    c, m = LX.corte(o, h, cfg["seleccion_k"]["corte"], [(0, "corr", kr), (_k_elegido(), "corr", kr)], cfg["semilla"],
                    cfg["ajuste"]["submuestra_personas"], cfg["ajuste"]["maxiter"])
    c.to_parquet(DIR / "residuo_casos.parquet")
    with open(DIR / "residuo_modelos.pkl", "wb") as f:
        pickle.dump({k: {kk: v[kk] for kk in ("K", "kr", "L", "psi", "Lr", "logL")} for k, v in m.items()}, f)
    return {k[0]: v["logL"] for k, v in m.items()}


def _k_elegido() -> int:
    s = pd.read_csv(DIR / "seleccion_k.csv", index_col=0)
    return int(s.index[s["elegido"]][0][1:].split("_")[0])


def examen(cfg: dict) -> dict:
    from bbnorm5.carrera import datos as CD
    from bbnorm5.carrera import examen as EX
    from bbnorm5.latente import examen as LX
    from bbnorm5.medida import datos as DM
    o = CD.cargar()
    h = pd.read_csv(DM.DIR / "hiperparametros.csv")
    K = _k_elegido()
    cs, mods = [], {}
    for anio in cfg["examen"]["cortes"]:
        kr = cfg["ajuste"]["k_residuo"]
        c, m = LX.corte(o, h, anio, [(0, "corr", 0), (K, "corr", kr), (K, "diag", kr)], cfg["semilla"],
                        cfg["ajuste"]["submuestra_personas"], cfg["ajuste"]["maxiter"])
        cs.append(c)
        mods[anio] = {k: {kk: v[kk] for kk in ("K", "kr", "cambios", "L", "psi", "Lr", "logL")} for k, v in m.items()}
    c = pd.concat(cs, ignore_index=True)
    c["hist"] = pd.cut(c["temporadas_hist"], [0, 1, 2, 3, 4, 10], labels=["1", "2", "3", "4", "5+"])
    c.to_parquet(DIR / "examen_casos.parquet")
    with open(DIR / "examen_modelos.pkl", "wb") as f:
        pickle.dump(mods, f)
    for nom, por in {"metrica": ["metrica", "modelo"], "historial": ["metrica", "modelo", "hist"],
                     "rol": ["metrica", "modelo", "rol"], "cambio_liga": ["metrica", "modelo", "cambio_liga"],
                     "global_historial": ["modelo", "hist"]}.items():
        EX.resumen(c, por).to_csv(DIR / f"examen_por_{nom}.csv", index=False)
    s = _crps_relativo(c, "K0_corr", cfg["semilla"])
    s.to_csv(DIR / "examen_resumen.csv")
    return {"casos": len(c), "K": K}


def final(cfg: dict) -> dict:
    from bbnorm5.carrera import datos as CD
    from bbnorm5.latente import examen as LX
    from bbnorm5.latente import modelo as ML
    from bbnorm5.medida import datos as DM
    o = CD.cargar()
    h = CD._hiper_preferido(pd.read_csv(DM.DIR / "hiperparametros.csv"))
    K = _k_elegido()
    f4 = LX.f4_por_metrica(o, h, None)
    S = ML.matrices(o, f4)
    mods = []
    for sem in range(cfg["final"]["semillas_estabilidad"]):
        Ssub = ML.submuestra(S, cfg["ajuste"]["submuestra_personas"], np.random.default_rng(cfg["semilla"] + 100 + sem))
        mods.append(ML.ajustar(Ssub, K, "corr", maxiter=cfg["ajuste"]["maxiter"], kr=cfg["ajuste"]["k_residuo"]))
        print(f"  semilla {sem}: logL {mods[-1]['logL']:.1f}", flush=True)
    i_mejor = int(np.argmax([m["logL"] for m in mods]))    # (list.index comparaba diccionarios con arrays)
    mod = mods[i_mejor]
    # refina el mejor (arranque en caliente) para acercarlo a la convergencia
    Ssub = ML.submuestra(S, cfg["ajuste"]["submuestra_personas"],
                         np.random.default_rng(cfg["semilla"] + 100 + i_mejor))
    mod = ML.ajustar(Ssub, K, "corr", x0=mod["x"], maxiter=cfg["ajuste"]["maxiter"], kr=cfg["ajuste"]["k_residuo"])
    print(f"  refinado: logL {mod['logL']:.1f}, convergió {mod['convergio']}", flush=True)
    Lr, R = ML.varimax(mod["L"])
    # orden y signo de los factores fijados por las cargas de referencia (las que interpreta el informe 05)
    ref = DIR / "cargas_referencia.csv"
    if ref.exists():
        P = ML.alinear(Lr, pd.read_csv(ref, index_col=0).loc[ML.METRICAS].to_numpy(float))
        Lr, R = Lr @ P, R @ P
    cargas = pd.DataFrame(Lr, index=ML.METRICAS, columns=[f"F{k + 1}" for k in range(K)])
    # escala comparable: carga / DT de la capacidad de la métrica (correlación métrica-factor)
    sd = np.sqrt(np.diag(mod["L"] @ mod["L"].T + np.diag(mod["psi"])))
    corr = cargas.div(sd, axis=0)
    corr["especifica"] = np.sqrt(mod["psi"]) / sd
    cargas.to_csv(DIR / "cargas_varimax.csv")
    corr.to_csv(DIR / "cargas_correlacion.csv")
    # estabilidad: entre submuestras y frente a los ajustes de los cortes del examen
    est = []
    for i, m in enumerate(mods):
        cg = ML.congruencia(Lr, ML.varimax(m["L"])[0])
        est.append({"comparacion": f"submuestra {i}", **{f"F{k + 1}": cg[k] for k in range(K)}})
    try:
        with open(DIR / "examen_modelos.pkl", "rb") as f:
            em = pickle.load(f)
        for anio, d in em.items():
            m = d.get((K, "corr", cfg["ajuste"]["k_residuo"]))
            if m is not None:
                cg = ML.congruencia(Lr, ML.varimax(m["L"])[0])
                est.append({"comparacion": f"corte {anio}", **{f"F{k + 1}": cg[k] for k in range(K)}})
    except FileNotFoundError:
        pass
    pd.DataFrame(est).to_csv(DIR / "estabilidad_cargas.csv", index=False)
    # perfil latente con la rotación varimax
    z = ML.puntuaciones(S, mod)
    zc = [f"z{k + 1}" for k in range(K)]
    z[zc] = z[zc].to_numpy() @ R
    z.to_parquet(DIR / "perfiles_latentes.parquet")
    with open(DIR / "modelo_final.pkl", "wb") as f:
        pickle.dump({"K": K, "kr": mod["kr"], "L": mod["L"], "psi": mod["psi"], "Lr": mod["Lr"], "R": R,
                     "cambios": "corr", "logL": mod["logL"], "convergio": mod["convergio"], "metricas": ML.METRICAS}, f)
    Cr = np.asarray(ML._corr_residuo(mod["Lr"])) if mod["Lr"] is not None else np.eye(len(ML.METRICAS))
    pd.DataFrame(Cr, index=ML.METRICAS, columns=ML.METRICAS).to_csv(DIR / "correlacion_residuo_temporada.csv")
    Sig0 = mod["L"] @ mod["L"].T + np.diag(mod["psi"])
    pd.DataFrame(Sig0 / np.outer(sd, sd), index=ML.METRICAS, columns=ML.METRICAS).to_csv(DIR / "correlacion_capacidades.csv")
    return {"K": K, "logL": mod["logL"], "congruencia_min": float(pd.DataFrame(est).drop(columns="comparacion").min().min())}


def alinear(cfg: dict) -> dict:
    """Aplica a la salida ya guardada de `final` la alineación con las cargas de referencia (la misma que hace `final`
    desde la F8): permuta y cambia de signo las columnas de cargas, estabilidad, perfiles y la rotación guardada. Evita
    repetir el ajuste (determinista) cuando sólo cambia el orden de los factores."""
    from bbnorm5.latente import modelo as ML
    car = pd.read_csv(DIR / "cargas_varimax.csv", index_col=0)
    ref = pd.read_csv(DIR / "cargas_referencia.csv", index_col=0).loc[car.index]
    P = ML.alinear(car.to_numpy(float), ref.to_numpy(float))
    if np.allclose(P, np.eye(len(P))):
        return {"permutacion": "identidad"}
    fs = list(car.columns)
    zc = [f"z{k + 1}" for k in range(len(fs))]
    pd.DataFrame(car.to_numpy(float) @ P, index=car.index, columns=fs).to_csv(DIR / "cargas_varimax.csv")
    cc = pd.read_csv(DIR / "cargas_correlacion.csv", index_col=0)
    cc[fs] = cc[fs].to_numpy(float) @ P
    cc.to_csv(DIR / "cargas_correlacion.csv")
    es = pd.read_csv(DIR / "estabilidad_cargas.csv")
    es[fs] = es[fs].to_numpy(float) @ np.abs(P)
    es.to_csv(DIR / "estabilidad_cargas.csv", index=False)
    z = pd.read_parquet(DIR / "perfiles_latentes.parquet")
    z[zc] = z[zc].to_numpy(float) @ P
    z.to_parquet(DIR / "perfiles_latentes.parquet")
    with open(DIR / "modelo_final.pkl", "rb") as f:
        m = pickle.load(f)
    m["R"] = m["R"] @ P
    with open(DIR / "modelo_final.pkl", "wb") as f:
        pickle.dump(m, f)
    orden = {fs[j]: fs[i] for j, i in zip(*np.nonzero(P))}
    return {"permutacion": orden, "signos": [float(P[j, i]) for j, i in zip(*np.nonzero(P))]}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bbnorm5.f5")
    ap.add_argument("--config", default="configs/v5/f5.yaml")
    ap.add_argument("--pasos", nargs="*")
    a = ap.parse_args(argv)
    cfg = C.cargar(a.config)
    resumen = {}
    for paso in (a.pasos or cfg["pasos"]):
        t0 = time.time()
        print(f"== {paso}", flush=True)
        if paso == "seleccion_k":
            out = seleccion_k(cfg)
        elif paso == "alinear":
            out = alinear(cfg)
        elif paso == "residuo":
            out = residuo(cfg)
        elif paso == "examen":
            out = examen(cfg)
        elif paso == "final":
            out = final(cfg)
        elif paso == "neuronal":
            from bbnorm5.latente import neuronal
            out = neuronal.ejecutar(cfg)
        elif paso == "figuras":
            from bbnorm5.latente import figuras
            out = figuras.todas(cfg)
        else:
            raise ValueError(paso)
        out["tiempo_s"] = round(time.time() - t0)
        resumen[paso] = out
        print(json.dumps(out, default=str), flush=True)
        C.escribir_json({**C.metadatos(cfg, [C.DIR_DATOS / "carrera" / "observaciones.parquet"], {"paso": paso}), **out},
                        DIR / f"meta_{paso}.json")
    from bbfit.registro import experimento
    with experimento("v5_f5_latente", "+".join(resumen), params={"config": cfg["_ruta"]}, semilla=cfg["semilla"]) as run:
        run.metricas({f"{p}_tiempo_s": v["tiempo_s"] for p, v in resumen.items()})
    return resumen


if __name__ == "__main__":
    main()
