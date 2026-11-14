"""F4 · Capa de carrera (encargo v5.0 §8 y revisión 1.2): ejecuta los pasos en orden.

    python -m bbnorm5.f4 --config configs/v5/f4.yaml
    python -m bbnorm5.f4 --config configs/v5/f4.yaml --pasos examen

Pasos:
- datos: series por persona, temporada y métrica desde la capa de medida (bbnorm5/carrera/datos.py)
- examen: examen fuera de tiempo de las variantes (bbnorm5/carrera/examen.py, modelo.py)
- experimento_obs: observación por logit empírico frente a posterior F3 ÷ prior (descartada)
- final: selección de la variante (regla fijada en la configuración) y ajuste con todas las temporadas: hiperparámetros,
  curvas de edad con bandas y nivel de carrera filtrado de cada persona-temporada
- proyeccion: nivel de carrera proyectado y producción esperada para la temporada siguiente, por separado
- simulacion: examen de nivel por simulación con el diseño real (recuperación de parámetros y cobertura del nivel)
- figuras
"""
from __future__ import annotations

import argparse
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from bbnorm5 import config as C


def _examen_metrica(args):
    import os
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    from bbnorm5.carrera import datos as CD
    from bbnorm5.carrera import examen as EX
    from bbnorm5.medida import datos as DM
    met, cfg = args
    o = CD.cargar()
    o = o[o["metrica"] == met]
    h = pd.read_csv(DM.DIR / "hiperparametros.csv")
    casos = pd.read_parquet(DM.DIR / "validacion_casos.parquet", filters=[("metrica", "==", met)])
    EX.MIN_MINUTOS = cfg["examen"]["min_minutos"]
    cs, hs = [], []
    for anio in cfg["examen"]["cortes"]:
        c, hp = EX.corte(o, CD._hiper_preferido(h), casos, h, met, anio, cfg["semilla"], cfg["examen"]["variantes"])
        cs.append(c)
        hs += hp
        print(f"  {met} {anio}: {len(c)} casos", flush=True)
    return pd.concat(cs, ignore_index=True), pd.DataFrame(hs)


def examen(cfg: dict) -> dict:
    from bbnorm5.carrera import datos as CD
    from bbnorm5.carrera import examen as EX
    from bbnorm5.medida import datos as DM
    mets = list(DM.METRICAS)
    with ProcessPoolExecutor(cfg["examen"]["procesos"]) as ex:
        res = list(ex.map(_examen_metrica, [(m, cfg) for m in mets]))
    casos = pd.concat([r[0] for r in res], ignore_index=True)
    hip = pd.concat([r[1] for r in res], ignore_index=True)
    casos["hist"] = pd.cut(casos["temporadas_hist"], [0, 1, 2, 3, 4, 10], labels=["1", "2", "3", "4", "5+"])
    casos.to_parquet(CD.DIR / "examen_casos.parquet")
    hip.to_csv(CD.DIR / "examen_hiperparametros.csv", index=False)
    for nom, por in {"metrica": ["metrica", "modelo"], "historial": ["metrica", "modelo", "hist"],
                     "cambio_liga": ["metrica", "modelo", "cambio_liga"], "corte": ["anio", "metrica", "modelo"],
                     "global_historial": ["modelo", "hist"]}.items():
        EX.resumen(casos, por).to_csv(CD.DIR / f"examen_por_{nom}.csv", index=False)
    return {"casos": len(casos), "metricas": len(mets)}


def experimento_obs(cfg: dict) -> dict:
    """Experimento: observación de la temporada por logit empírico (por defecto) o por la posterior F3 ÷ prior."""
    from bbnorm5.carrera import datos as CD
    from bbnorm5.carrera import examen as EX
    from bbnorm5.medida import datos as DM
    d = DM.cargar()
    h = pd.read_csv(DM.DIR / "hiperparametros.csv")
    post = pd.read_parquet(DM.DIR / "posteriores.parquet")
    nac = CD.nacimiento_persona(cfg["temporadas"])
    casos = pd.read_parquet(DM.DIR / "validacion_casos.parquet")
    res = []
    for met in cfg["experimento_obs"]["metricas"]:
        for modo in ("empirica", "posterior"):
            o = CD.observaciones(d, met, h, post, nac, modo)
            c, _ = EX.corte(o, CD._hiper_preferido(h), casos[casos["metrica"] == met], h, met,
                            cfg["experimento_obs"]["corte"], cfg["semilla"], ["solo_ultima", "completo",
                                                                              "completo_solo_ultima"])
            res.append(EX.resumen(c, ["modelo"]).assign(metrica=met, modo=modo))
    r = pd.concat(res, ignore_index=True)
    r.to_csv(CD.DIR / "experimento_observacion.csv", index=False)
    return {"filas": len(r)}


def seleccion(cfg: dict) -> tuple[str, pd.DataFrame]:
    """Regla de la configuración: cobertura 80 % en rango en la mayoría de métricas; menor CRPS relativo medio (frente
    a `solo_ultima`); a igualdad dentro de 1 EE (bootstrap por persona), la más simple."""
    from bbnorm5.carrera import datos as CD
    c = pd.read_parquet(CD.DIR / "examen_casos.parquet")
    c = c[c["cambio_liga"] == 0]       # el criterio principal: misma liga (el cambio de liga es la F6)
    base = c[c["modelo"] == "solo_ultima"].set_index(["metrica", "anio", "persona_v5"])["crps"]
    c = c.join(base.rename("crps_base"), on=["metrica", "anio", "persona_v5"])
    c["rel"] = c["crps"] / c.groupby("metrica")["crps_base"].transform("mean")
    c["cob80"] = (np.abs(c["pit"] - 0.5) <= 0.4).astype(float)
    t = c.groupby(["modelo", "metrica"]).agg(rel=("rel", "mean"), cob80=("cob80", "mean")).reset_index()
    s = t.groupby("modelo").agg(rel=("rel", "mean"), en_rango=("cob80", lambda x: ((x >= 0.76) & (x <= 0.84)).mean()))
    rng = np.random.default_rng(cfg["semilla"])
    p = c.pivot_table(index=["metrica", "anio", "persona_v5"], columns="modelo", values="rel")
    boots = np.array([p.iloc[rng.integers(0, len(p), len(p))].mean().to_numpy() for _ in range(200)])
    s["ee"] = pd.Series(boots.std(axis=0), index=p.columns)
    ok = s[s["en_rango"] > 0.5]
    mejor = ok["rel"].idxmin()
    for m in cfg["seleccion"]["orden_simplicidad"]:
        if m in ok.index and ok.loc[m, "rel"] <= ok.loc[mejor, "rel"] + ok.loc[mejor, "ee"]:
            elegido = m
            break
    s["elegido"] = s.index == elegido
    s.to_csv(CD.DIR / "seleccion.csv")
    return elegido, s


def final(cfg: dict) -> dict:
    from bbnorm5.carrera import datos as CD
    from bbnorm5.carrera import modelo as MOD
    from bbnorm5.medida import datos as DM
    elegido, s = seleccion(cfg)
    o = CD.cargar()
    h = CD._hiper_preferido(pd.read_csv(DM.DIR / "hiperparametros.csv"))
    hip, curvas, niveles, pesos, modelos = [], [], [], [], {}
    var_aj = elegido if elegido in MOD.VARIANTES else "completo"
    for met in DM.METRICAS:
        x = o[o["metrica"] == met]
        M = MOD.matrices(x)
        tau0 = float(h[h["metrica"] == met]["sigma"].median())
        mod = MOD.ajustar(M, var_aj, tau0, con_hessiana=True)
        hip.append({"metrica": met, "variante": var_aj, **{k: mod["th"].get(k, np.nan) for k in MOD.PARAMS},
                    "logL": mod["logL"], "convergio": mod["convergio"],
                    **{f"se_{k}": float(np.sqrt(max(mod["cov"][i, i], 0))) for i, k in enumerate(mod["libres"])}})
        con_edad = mod if MOD.VARIANTES[var_aj][1] else MOD.ajustar(M, "completo", tau0, con_hessiana=True)
        curvas.append(MOD.curva_edad(con_edad).assign(metrica=met, variante=con_edad["variante"]))
        vt = float(x.loc[x["min_temp"] >= 300, "v"].median())
        for esc, cl, cr in (("misma liga y rol", False, False), ("cambio de liga en la última", True, False),
                            ("cambio de rol en la última", False, True)):
            w = MOD.pesos_temporadas(mod, vt, 4, cambio_liga_ultimo=cl, cambio_rol_ultimo=cr)
            pesos.append({"metrica": met, "escenario": esc, "v_tipica": vt, "peso_t-4": w[0], "peso_t-3": w[1],
                          "peso_t-2": w[2], "peso_t-1": w[3], "peso_prior": 1 - w.sum()})
        _, out = MOD.filtrar(M, mod["th"], mod["beta"])
        modelos[met] = {"variante": mod["variante"], "th": dict(mod["th"]), "beta": np.asarray(mod["beta"])}
        pid, j = M["fila"]
        niveles.append(x.sort_values(["persona_v5", "anio"]).reset_index(drop=True)[
            ["persona_v5", "liga", "temporada", "rol", "edad", "y", "v", "mu"]].assign(
            metrica=met, nivel_carrera=out["a"][pid, j], var_nivel_carrera=out["P"][pid, j]))
        print(f"  {met}: σ_η {np.exp(mod['th'].get('log_s_eta', -np.inf)):.3f}, σ_u {np.exp(mod['th'].get('log_s_u', -np.inf)):.3f}",
              flush=True)
    pd.DataFrame(hip).to_csv(CD.DIR / "hiperparametros.csv", index=False)
    pd.concat(curvas).to_csv(CD.DIR / "curvas_edad.csv", index=False)
    pd.DataFrame(pesos).to_csv(CD.DIR / "pesos_temporadas.csv", index=False)
    pd.concat(niveles).to_parquet(CD.DIR / "niveles_carrera.parquet")
    # v5.1 F6: parámetros congelados (θ y β de la curva de edad) para el proceso paralelo de la temporada en curso
    import pickle
    (CD.DIR / "modelos_final.pkl").write_bytes(pickle.dumps(modelos))
    return {"variante_elegida": elegido, "variante_ajustada": var_aj}


def proyeccion(cfg: dict) -> dict:
    """Decisión 3 de la puerta F4: nivel de carrera proyectado y producción esperada, por separado."""
    from bbnorm5.carrera import datos as CD
    from bbnorm5.carrera import modelo as MOD
    from bbnorm5.carrera import proyeccion as PR
    from bbnorm5.medida import datos as DM
    o = CD.cargar()
    hall = pd.read_csv(DM.DIR / "hiperparametros.csv")
    h = CD._hiper_preferido(hall)
    hip = pd.read_csv(CD.DIR / "hiperparametros.csv").set_index("metrica")
    anio = int(cfg["temporadas"][-1][:4]) + 1
    rng = np.random.default_rng(cfg["semilla"])
    res = []
    for met in DM.METRICAS:
        x = o[o["metrica"] == met]
        tau0 = float(h[h["metrica"] == met]["sigma"].median())
        mod = MOD.ajustar(MOD.matrices(x), hip.loc[met, "variante"], tau0)
        res.append(PR.proyectar(x, mod, h, met, anio, rng))
    r = pd.concat(res, ignore_index=True)
    r.to_parquet(CD.DIR / f"proyeccion_{anio}_{str(anio + 1)[2:]}.parquet")
    return {"filas": len(r), "personas": int(r["persona_v5"].nunique()), "temporada": f"{anio}-{str(anio + 1)[2:]}"}


def simulacion(cfg: dict) -> dict:
    from bbnorm5.carrera import datos as CD
    from bbnorm5.carrera import modelo as MOD
    from bbnorm5.medida import datos as DM
    o = CD.cargar()
    hip = pd.read_csv(CD.DIR / "hiperparametros.csv").set_index("metrica")
    h = CD._hiper_preferido(pd.read_csv(DM.DIR / "hiperparametros.csv"))
    rng = np.random.default_rng(cfg["semilla"])
    filas = []
    for met in DM.METRICAS:
        M = MOD.matrices(o[o["metrica"] == met])
        var = hip.loc[met, "variante"]
        tau0 = float(h[h["metrica"] == met]["sigma"].median())
        verdad = MOD.ajustar(M, var, tau0)          # parámetros «verdaderos» = los ajustados con los datos reales
        Sm = MOD.simular(M, verdad, rng)
        rec = MOD.ajustar(Sm, var, tau0)
        _, out = MOD.filtrar(Sm, rec["th"], rec["beta"])
        z = (Sm["a_verdadero"] - out["a"]) / np.sqrt(out["P"])
        m = Sm["mask"]
        hist = np.cumsum(m, axis=1)
        for k in (1, 2, 3, 4, 5):
            sel = m & ((hist == k) if k < 5 else (hist >= 5))
            filas.append({"metrica": met, "historial": str(k) if k < 5 else "5+", "celdas": int(sel.sum()),
                          "cob80_nivel": float((np.abs(z[sel]) <= 1.2816).mean()),
                          "sd_nivel_mediana": float(np.median(np.sqrt(out["P"][sel])))})
        for kk in ("log_s_eta", "log_s_u", "log_tau0"):
            if kk in verdad["th"]:
                filas.append({"metrica": met, "parametro": kk.replace("log_", ""),
                              "verdadero": float(np.exp(verdad["th"][kk])), "recuperado": float(np.exp(rec["th"][kk]))})
        print(f"  {met}: simulación hecha", flush=True)
    r = pd.DataFrame(filas)
    r.to_csv(CD.DIR / "examen_simulacion.csv", index=False)
    return {"filas": len(r)}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bbnorm5.f4")
    ap.add_argument("--config", default="configs/v5/f4.yaml")
    ap.add_argument("--pasos", nargs="*")
    a = ap.parse_args(argv)
    cfg = C.cargar(a.config)
    from bbnorm5.carrera import datos as CD
    resumen = {}
    for paso in (a.pasos or cfg["pasos"]):
        t0 = time.time()
        print(f"== {paso}", flush=True)
        if paso == "datos":
            o = CD.construir(cfg["temporadas"])
            out = {"observaciones": len(o), "personas": int(o["persona_v5"].nunique()),
                   "con_edad": float(o["edad"].notna().mean())}
        elif paso == "examen":
            out = examen(cfg)
        elif paso == "experimento_obs":
            out = experimento_obs(cfg)
        elif paso == "final":
            out = final(cfg)
        elif paso == "proyeccion":
            out = proyeccion(cfg)
        elif paso == "simulacion":
            out = simulacion(cfg)
        elif paso == "figuras":
            from bbnorm5.carrera import figuras
            out = figuras.todas(cfg)
        else:
            raise ValueError(paso)
        out["tiempo_s"] = round(time.time() - t0)
        resumen[paso] = out
        print(out, flush=True)
        C.escribir_json({**C.metadatos(cfg, [CD.DIR / "observaciones.parquet"], {"paso": paso}), **out},
                        CD.DIR / f"meta_{paso}.json")
    from bbfit.registro import experimento
    with experimento("v5_f4_carrera", "+".join(resumen), params={"config": cfg["_ruta"]}, semilla=cfg["semilla"]) as run:
        run.metricas({f"{p}_tiempo_s": v["tiempo_s"] for p, v in resumen.items()})
    return resumen


if __name__ == "__main__":
    main()
