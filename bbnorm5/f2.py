"""F2 · Capa de datos (encargo v5.0 §6 y revisión 1.2): ejecuta los pasos en orden.

    python -m bbnorm5.f2 --config configs/v5/f2.yaml                   # todos los pasos
    python -m bbnorm5.f2 --config configs/v5/f2.yaml --pasos puentes contexto

Pasos:
- caja · caja_agregados: caja jugador-partido desde los brutos (bbnorm5/datos/caja_partido*.py)
- entidades: personas v5 (bbnorm5/datos/entidades.py)
- enfrentamientos: club ↔ liga doméstica y fuerza de ligas (bbnorm5/datos/enfrentamientos.py)
- puentes: unidades, puentes intra e inter, grafo (bbnorm5/datos/puentes.py)
- contexto: estilo de liga, de equipo y de compañeros (bbnorm5/datos/estilos_contexto.py)
- contrato: validación (bbnorm5/datos/contrato.py)
"""
from __future__ import annotations

import argparse
import json
import time

from bbnorm5 import config as C


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bbnorm5.f2")
    ap.add_argument("--config", default="configs/v5/f2.yaml")
    ap.add_argument("--pasos", nargs="*")
    a = ap.parse_args(argv)
    cfg = C.cargar(a.config)
    T = cfg["temporadas"]
    resumen = {}
    for paso in (a.pasos or cfg["pasos"]):
        t0 = time.time()
        print(f"== {paso}", flush=True)
        if paso == "caja":
            from bbnorm5.datos import caja_partido as K
            r = K.construir(cfg, K.LIGAS_BOX, T)
            r.to_csv(C.DIR_DATOS / "limpios" / "caja_partido" / "resumen_box.csv", index=False)
            out = {"ligas_temporada": int((r["estado"] == "ok").sum())}
        elif paso == "caja_agregados":
            from bbnorm5.datos import caja_partido_agregados as K
            r = K.construir(K.LIGAS_AGREGADOS, T)
            r.to_csv(C.DIR_DATOS / "limpios" / "caja_partido" / "resumen_agregados.csv", index=False)
            out = {"ligas_temporada": int((r["estado"] == "ok").sum())}
        elif paso == "entidades":
            from bbnorm5.datos import entidades as N
            out = N.resolver(T)
        elif paso == "enfrentamientos":
            from bbnorm5.datos import enfrentamientos as E
            out = E.construir(T)
        elif paso == "puentes":
            from bbnorm5.datos import puentes as P
            out = P.construir(T)
        elif paso == "contexto":
            from bbnorm5.datos import estilos_contexto as X
            out = X.construir(T)
        elif paso == "contrato":
            from bbnorm5.datos import contrato as K
            r = K.validar(T)
            out = {"tablas": r.groupby("tabla")["validas"].mean().round(4).to_dict()}
        else:
            raise SystemExit(f"paso desconocido: {paso}")
        resumen[paso] = {**out, "tiempo_s": round(time.time() - t0)}
        print(json.dumps({paso: resumen[paso]}, ensure_ascii=False, default=str), flush=True)
    C.escribir_json({"resumen": resumen, "meta": C.metadatos(cfg)}, C.DIR_DATOS / "f2_ejecucion.json")


if __name__ == "__main__":
    main()
