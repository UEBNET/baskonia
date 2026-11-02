"""Línea de comandos de la normalización v3 (CVAE jerárquica).

    python -m bbnorm3 elegir-k        # corte de selección 2022-23 → 2023-24: compara K (no mira el examen)
    python -m bbnorm3 validar         # examen 2023 → 24 y 2024 → 25 (CVAE reentrenada por corte) + puerta de control
    python -m bbnorm3 f0              # línea base F0: grafo amortiguado actual con su covarianza completa
    python -m bbnorm3 lolo            # dejar fuera una liga: nivel sin sus puentes frente al nivel completo
    python -m bbnorm3 ajustar         # ajuste con todos los datos → data/modelos/v3/ (niveles, traducción cruzada…)

v3.1 (combinación v2 + CVAE corregida, configs/normalization_v31.yaml):
    python -m bbnorm3 --config configs/normalization_v31.yaml validar-combinada
    python -m bbnorm3 --config configs/normalization_v31.yaml ajustar-combinada

v3.2 (B1/B4/B6 con cortes anidados, B2, B5; configs/normalization_v32.yaml):
    python -m bbnorm3 --config configs/normalization_v32.yaml ablacion [--fase entrenar|predecir|decidir]

Las redes entrenadas se guardan en experimentos/v3/ (no versionado) para poder reanudar sin reentrenar.
"""
from __future__ import annotations

import argparse
import json
import time

from . import config as C


def _tabla():
    from bbmodel import modelo as A
    t, info = A.preparar()
    print(f"  {info['registros']} registros, {info['personas']} personas", flush=True)
    return t


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bbnorm3", description="Normalización v3: CVAE jerárquica")
    sub = ap.add_subparsers(dest="orden", required=True)
    sub.add_parser("elegir-k")
    v = sub.add_parser("validar")
    v.add_argument("--sin-f0", action="store_true", help="no recalcular el intervalo de F0 con covarianza completa")
    sub.add_parser("lolo")
    sub.add_parser("f0", help="cobertura de la línea base F0 (grafo amortiguado con covarianza completa)")
    sub.add_parser("ajustar")
    sub.add_parser("validar-combinada", help="v3.1: examen de la combinación v2 + CVAE")
    sub.add_parser("ajustar-combinada", help="v3.1/v3.2: ajuste final y dataset normalizado combinado")
    sub.add_parser("validar-v32", help="v3.2: examen anidado de la combinación con pesos por métrica (B2)")
    sub.add_parser("destino-covarianza", help="v3.2: covarianza conjunta de los niveles de la v2 (vara de destino)")
    sub.add_parser("destino", help="v3.2: capacidad y constantes para expresar todo en la vara de la liga de destino")
    ab = sub.add_parser("ablacion", help="v3.2: ablación B1/B4/B6 con cortes anidados (bbnorm3/ablacion.py)")
    ab.add_argument("--fase", default="todo", choices=["todo", "entrenar", "predecir", "decidir", "aplicar"])
    ap.add_argument("--config", help="configuración (por defecto configs/normalization_v3.yaml, la v3.0)")
    a = ap.parse_args(argv)
    cfg = C.cargar(C.RAIZ / a.config if a.config else None)
    t0 = time.time()
    print("Preparando datos (identidades y posiciones)…", flush=True)
    tabla = _tabla()
    from . import flujo
    if a.orden == "elegir-k":
        flujo.elegir_k(tabla, cfg)
    elif a.orden == "validar":
        flujo.validar(tabla, cfg, f0=not a.sin_f0)
    elif a.orden == "f0":
        flujo.f0(tabla, cfg)
    elif a.orden == "lolo":
        flujo.lolo(tabla, cfg)
    elif a.orden == "validar-combinada":
        from . import combinacion
        combinacion.validar_combinada(tabla, cfg)
    elif a.orden == "destino-covarianza":
        from . import destino
        destino.covarianza_v2(cfg, tabla)
    elif a.orden == "destino":
        from . import destino
        destino.exportar(tabla, cfg)
    elif a.orden == "ablacion":
        from . import ablacion
        if a.fase == "aplicar":
            ablacion.aplicar_decision(C.RAIZ / a.config if a.config else None)
        else:
            ablacion.main(tabla, cfg, a.fase)
    elif a.orden == "validar-v32":
        from . import combinacion
        combinacion.validar_combinada_v32(tabla, cfg)
    elif a.orden == "ajustar-combinada":
        from . import combinacion
        combinacion.ajustar_combinada(tabla, cfg)
    else:
        flujo.ajustar(tabla, cfg)
    print(json.dumps({"tiempo_s": round(time.time() - t0)}))


if __name__ == "__main__":
    main()
