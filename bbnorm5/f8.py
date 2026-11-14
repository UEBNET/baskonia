"""F8 · Validación integral (encargo v5.0 §12; revisión 1.2, criterios 9–11).

    python -m bbnorm5.f8 --config configs/v5/f8.yaml

Pasos:
- base: base de la proyección en contexto con λ del paso 2 estimado sin fugas para cada año objetivo
- predicciones: predicciones fuera de tiempo de la v5 (2023-24 a 2025-26) con sus variantes
- banco: banco de fichajes reales V32_corte con la producción aplicada de la v3.3 (y el centro de la v4.2)
- fichajes: examen principal (WIS con IC por persona, cobertura, anchura, navaja de estilos)
- protocolo: protocolo de la F1 (v5 frente a v3.2, v2 y v1 en los mismos cambios de liga)
- lolo · puentes_fuera · sbc: capa de ligas (dejar fuera una liga, jugadores puente dejados fuera, SBC de λ)
- fugas: auditoría de fugas
- criterios: criterios de éxito 1–5 del encargo (§17)
- figuras: figuras del informe 08
"""
from __future__ import annotations

import argparse
import json
import time

from bbnorm5 import config as C

DIR = C.DIR_DATOS / "validacion"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bbnorm5.f8")
    ap.add_argument("--config", default="configs/v5/f8.yaml")
    ap.add_argument("--pasos", nargs="*")
    a = ap.parse_args(argv)
    cfg = C.cargar(a.config)
    DIR.mkdir(parents=True, exist_ok=True)
    resumen = {}
    for paso in (a.pasos or cfg["pasos"]):
        t0 = time.time()
        print(f"== {paso}", flush=True)
        from bbnorm5.validacion import fichajes as VF
        if paso == "base":
            out = {"filas": len(VF.base_v5(cfg))}
        elif paso == "predicciones":
            out = {"filas": len(VF.predicciones_v5(cfg))}
        elif paso == "banco":
            out = {"filas": len(VF.banco_v33())}
        elif paso == "fichajes":
            out = VF.comparar(cfg)
        elif paso == "protocolo":
            from bbnorm5.validacion import protocolo as VP
            cfg1 = C.cargar("configs/v5/f1.yaml")
            out = {"ex_ante": VP.comparar(cfg, cfg1), "condicionada": VP.comparar(cfg, cfg1, modelo="final", sufijo="_condicionada"),
                   # publicada (criterio 11: sin el bloque de estilo de liga)
                   "ex_ante_publicada": VP.comparar(cfg, cfg1, modelo="ex_ante_sin_estilo_liga", sufijo="_publicada"),
                   "condicionada_publicada": VP.comparar(cfg, cfg1, modelo="final_sin_estilo_liga",
                                                         sufijo="_condicionada_publicada")}
        elif paso in ("lolo", "puentes_fuera", "sbc"):
            from bbnorm5.validacion import ligas as VL
            cfg7 = C.cargar("configs/v5/f7.yaml")
            if paso == "lolo":
                d = VL.lolo(cfg7)
                g = d.groupby("variante")
                out = {"error_rel_mediana": g["error_rel"].median().round(3).to_dict(),
                       "cobertura80": g["cubre80"].mean().round(3).to_dict()}
            elif paso == "puentes_fuera":
                d = VL.puentes_fuera(cfg7, semilla=cfg["semilla"])
                g = d.groupby("variante")
                out = {"cobertura80": g["z"].apply(lambda z: float((z.abs() <= 1.2816).mean())).round(3).to_dict(),
                       "crps_medio": g["crps"].mean().round(4).to_dict(), "casos": int(len(d) / 2)}
            else:
                d = VL.sbc_lambda(cfg7, R=int(cfg.get("sbc", {}).get("replicas", 100)), semilla=cfg["semilla"])
                from scipy import stats
                out = {"ks_p": float(stats.kstest(d["u"], "uniform").pvalue),
                       "cobertura80": float(((d["u"] > 0.1) & (d["u"] < 0.9)).mean()), "n": int(len(d))}
        elif paso == "fugas":
            from bbnorm5.validacion import fugas as VFu
            out = VFu.ejecutar(cfg)
        elif paso == "figuras":
            from bbnorm5.validacion import figuras_f8
            out = figuras_f8.todas(cfg)
        elif paso == "criterios":
            from bbnorm5.validacion import criterios as VC
            out = VC.ejecutar(cfg, tuple(int(x) for x in cfg.get("criterios", [1, 2, 3, 4, 5])))
        else:
            raise ValueError(paso)
        out["tiempo_s"] = round(time.time() - t0)
        resumen[paso] = out
        print(json.dumps(out, default=str, ensure_ascii=False)[:3000], flush=True)
        C.escribir_json({**C.metadatos(cfg, None, {"paso": paso}), **out}, DIR / f"meta_{paso}.json")
    from bbfit.registro import experimento
    with experimento("v5_f8_validacion", "+".join(resumen), params={"config": cfg["_ruta"]}, semilla=cfg["semilla"]) as run:
        run.metricas({f"{p}_tiempo_s": v["tiempo_s"] for p, v in resumen.items()})
    return resumen


if __name__ == "__main__":
    main()
