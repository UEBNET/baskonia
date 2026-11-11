"""F6 · Ligas y contexto (encargo v5.0 §10 y revisión 1.2).

    python -m bbnorm5.f6 --config configs/v5/f6.yaml --pasos pares lambda_intra resumen_intra

Pasos de la F6.1 (efectos de liga con puentes intra-temporada):
- pares: diferencias de cada puente por métrica (bbnorm5/ligas/datos.py)
- lambda_intra: NUTS por bloques de métricas, con y sin el prior de fuerza por enfrentamientos (bbnorm5/ligas/modelo.py)
- contexto: F6.2, proyección en contexto con examen fuera de tiempo y navaja por bloques (bbnorm5/ligas/contexto.py)
- resumen_intra: diagnósticos, matriz de traducción, ciclos (conjunta frente a pares independientes) y grafo
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd

from bbnorm5 import config as C

DIR = C.DIR_DATOS / "ligas"


def lambda_intra(cfg: dict, bloques: dict | None = None, pares: str = "pares_intra.parquet", sufijo: str = "") -> dict:
    import arviz as az
    from bbnorm5.ligas import modelo as LM
    p = pd.read_parquet(DIR / pares)
    out = {}
    for bloque, mets in (bloques or LM.BLOQUES).items():
        for fz in ([False, True] if (bloque in cfg["nuts"]["bloques_con_fuerza"] and not sufijo) else [False]):
            nombre = f"{sufijo}{bloque}{'_fuerza' if fz else ''}"
            t0 = time.time()
            I = LM.indices(p, cfg["temporadas"], mets)
            mc = LM.ajustar(I, cfg, fz)
            s = mc.get_samples(group_by_chain=True)
            lam = np.asarray(s["lambda"])                         # cadenas × draws × L × T × M
            e = mc.get_extra_fields(group_by_chain=True)
            idata = az.from_dict(posterior={k: np.asarray(v) for k, v in s.items()
                                            if k in ("lambda", "s_base", "s_rw", "s_c", "s_inter", "beta", "gamma_fuerza")})
            sm = az.summary(idata, var_names=[v for v in ("s_base", "s_rw", "s_c", "s_inter", "beta", "gamma_fuerza")
                                              if v in idata.posterior])
            sl = az.summary(idata, var_names=["lambda"])
            sl = sl[sl["sd"] > 1e-12]                              # fuera la referencia (≡ 0)
            np.savez_compressed(DIR / f"lambda_{nombre}.npz", lam=lam.reshape(-1, *lam.shape[2:]),
                                ligas=np.array(I["ligas"]), temporadas=np.array(I["temporadas"]),
                                metricas=np.array(I["metricas"]), escala=I["escala"])
            pd.concat([sm.assign(grupo="hiper"), sl.assign(grupo="lambda")]).to_csv(DIR / f"diagnosticos_{nombre}.csv")
            out[nombre] = {"rhat_max": float(pd.concat([sm, sl])["r_hat"].max()),
                           "ess_bulk_min": float(pd.concat([sm, sl])["ess_bulk"].min()),
                           "ess_tail_min": float(pd.concat([sm, sl])["ess_tail"].min()),
                           "divergencias": int(np.asarray(e["diverging"]).sum()),
                           "pasos_medios": float(np.asarray(e["num_steps"]).mean()),
                           "tiempo_s": round(time.time() - t0)}
            print(f"  {nombre}: {out[nombre]}", flush=True)
            C.escribir_json(out, DIR / f"lambda_{sufijo}diagnosticos.json" if sufijo else DIR / "lambda_intra_diagnosticos.json")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bbnorm5.f6")
    ap.add_argument("--config", default="configs/v5/f6.yaml")
    ap.add_argument("--pasos", nargs="*")
    a = ap.parse_args(argv)
    cfg = C.cargar(a.config)
    resumen = {}
    for paso in (a.pasos or cfg["pasos"]):
        t0 = time.time()
        print(f"== {paso}", flush=True)
        if paso == "pares":
            from bbnorm5.ligas import datos as LD
            p = LD.pares(cfg["temporadas"], cfg["pares"]["min_minutos"])
            out = {"filas": len(p), "puentes": int(p["puente"].nunique())}
        elif paso == "lambda_intra":
            out = lambda_intra(cfg)
        elif paso == "contexto":
            from bbnorm5.ligas import contexto as LC
            if not (DIR / "contexto_base.parquet").exists():
                LC.preparar(cfg)
            c = LC.examen(cfg)
            nv = LC.navaja(c, cfg["semilla"])
            nv.to_csv(DIR / "navaja_contexto.csv", index=False)
            r = c.assign(c80=(np.abs(c["pit"] - 0.5) <= 0.4)).groupby(["modelo"]).agg(
                cob80=("c80", "mean"), crps=("crps", "mean"))
            r.to_csv(DIR / "contexto_resumen.csv")
            out = {"casos": len(c), "superan_navaja": nv.loc[nv["supera_navaja"], "modelo"].unique().tolist()}
        elif paso == "figuras":
            from bbnorm5.ligas import figuras as LF
            out = LF.todas(cfg)
        elif paso == "resumen_intra":
            from bbnorm5.ligas import resumen as LR
            out = LR.intra(cfg)
        else:
            raise ValueError(paso)
        out["tiempo_s"] = round(time.time() - t0)
        resumen[paso] = out
        print(json.dumps(out, default=str), flush=True)
        C.escribir_json({**C.metadatos(cfg, None, {"paso": paso}), **out}, DIR / f"meta_{paso}.json")
    from bbfit.registro import experimento
    with experimento("v5_f6_ligas", "+".join(resumen), params={"config": cfg["_ruta"]}, semilla=cfg["semilla"]) as run:
        run.metricas({f"{p}_tiempo_s": v["tiempo_s"] for p, v in resumen.items()})
    return resumen


if __name__ == "__main__":
    main()
