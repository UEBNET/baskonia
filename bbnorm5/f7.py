"""F7 · Sesgo de selección en los traspasos (encargo v5.0 §11) y paso 2 de la F6.

    python -m bbnorm5.f7 --config configs/v5/f7.yaml

Pasos:
- base: proyección F4 sin fugas de cada persona en cada temporada objetivo 2021-22 … 2025-26 (bbnorm5/ligas/contexto.py)
- proyeccion_paso2: la proyección en contexto (F6.2) con λ del paso 2 frente a λ del paso 1
- pares_paso2 · lambda_paso2: NUTS del paso 2 (puentes intra + traspasos, bloques reagrupados)
- resumen_paso2: diagnósticos, traducción, ciclos, compatibilidad y precisión frente al paso 1 (bbnorm5/ligas/resumen_paso2.py)
- examen: selección (multinomial: seguir / subir / bajar), λ con traspasos entre temporadas (crudo, encogido, IPW y
  Heckman) y prueba de sesgo por dirección del cambio (bbnorm5/ligas/seleccion.py)
"""
from __future__ import annotations

import argparse
import json
import time

from bbnorm5 import config as C

DIR = C.DIR_DATOS / "ligas"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bbnorm5.f7")
    ap.add_argument("--config", default="configs/v5/f7.yaml")
    ap.add_argument("--pasos", nargs="*")
    ap.add_argument("--bloques", nargs="*", help="lambda_paso2: sólo estos bloques (por defecto, todos)")
    a = ap.parse_args(argv)
    cfg = C.cargar(a.config)
    resumen = {}
    for paso in (a.pasos or cfg["pasos"]):
        t0 = time.time()
        print(f"== {paso}", flush=True)
        if paso == "base":
            from bbnorm5.ligas import contexto as LC
            x = LC.preparar(cfg, cfg["base"]["cortes"], "seleccion_base.parquet")
            out = {"filas": len(x)}
        elif paso == "examen":
            from bbnorm5.ligas import seleccion as LS
            out = LS.ejecutar(cfg)
        elif paso == "pares_paso2":
            from bbnorm5.ligas import seleccion as LS
            p = LS.pares_paso2(cfg)
            out = {"filas": len(p), "traspasos": int((p["tipo"] == "traspaso_entre_temporadas").sum())}
        elif paso == "lambda_paso2":
            from bbnorm5 import f6
            from bbnorm5.ligas import modelo as LM
            cfg6 = C.cargar("configs/v5/f6.yaml")
            bl = {k: v for k, v in LM.BLOQUES_PASO2.items() if not a.bloques or k in a.bloques}
            out = f6.lambda_intra(cfg6, bloques=bl, pares="pares_paso2.parquet", sufijo="paso2_")
        elif paso == "resumen_paso2":
            from bbnorm5.ligas import resumen_paso2 as R2
            out = R2.ejecutar(C.cargar("configs/v5/f6.yaml"))
        elif paso == "figuras":
            from bbnorm5.ligas import figuras_f7
            out = figuras_f7.todas(cfg)
        elif paso == "proyeccion_paso2":
            import numpy as np
            import pandas as pd
            from bbnorm5.ligas import seleccion as LS
            cfg6 = C.cargar("configs/v5/f6.yaml")
            c2 = LS.proyeccion_paso2(cfg6)
            c1 = pd.read_parquet(DIR / "contexto_casos.parquet")
            fin = "liga+peso+todos+recal"
            k = ["metrica", "anio", "persona_v5"]
            m = c1[c1["modelo"] == fin][k + ["crps", "pit", "cambio_liga", "liga"]].merge(
                c2[c2["modelo"] == fin][k + ["crps", "pit"]], on=k, suffixes=("_p1", "_p2"))
            m.to_parquet(DIR / "paso1_frente_paso2.parquet")
            out = {"casos": len(m)}
        else:
            raise ValueError(paso)
        out["tiempo_s"] = round(time.time() - t0)
        resumen[paso] = out
        print(json.dumps(out, default=str), flush=True)
        C.escribir_json({**C.metadatos(cfg, None, {"paso": paso}), **out}, DIR / f"meta_f7_{paso}.json")
    from bbfit.registro import experimento
    with experimento("v5_f7_seleccion", "+".join(resumen), params={"config": cfg["_ruta"]}, semilla=cfg["semilla"]) as run:
        run.metricas({f"{p}_tiempo_s": v["tiempo_s"] for p, v in resumen.items()})
    return resumen


if __name__ == "__main__":
    main()
