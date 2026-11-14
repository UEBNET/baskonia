"""F1 · «Dejar fuera una liga» (LOLO) de las normalizaciones vigentes, con la salida redirigida a data/v5/.

No modifica ni sobrescribe nada de la v2 ni de la v3.2: llama a sus propias funciones de LOLO con la carpeta de salida
cambiada (las cachés de redes y parámetros van a experimentos/, no versionado).

    python -m bbnorm5.diagnostico.lolo --config configs/v5/f1.yaml v32   # CVAE v3.2, 1 semilla, corte 2024
    python -m bbnorm5.diagnostico.lolo --config configs/v5/f1.yaml v2    # v2 amortiguada (A + grafo), corte 2024

Definición (la del repositorio): para cada liga se quitan todos sus puentes; su nivel sale sólo de la jerarquía/escalón
y se compara con el nivel estimado con todos los datos (error y cobertura del intervalo).
"""
from __future__ import annotations

import argparse
import json
import time

from bbnorm5 import config as C


def lolo_v32(cfg: dict) -> None:
    from bbmodel import modelo as A
    from bbnorm3 import config as C3, flujo
    c3 = C3.cargar(C.RAIZ / cfg["v32"]["config"])
    c3["salida"] = str((C.dir_fase(cfg) / "lolo_v32").relative_to(C.RAIZ))     # redirección: data/v5/f1/lolo_v32
    tabla, info = A.preparar()
    print(f"  tabla: {info['registros']} registros, {info['personas']} personas", flush=True)
    t0 = time.time()
    flujo.lolo(tabla, c3)
    meta = C.metadatos(cfg, extra={"procedimiento": "bbnorm3.flujo.lolo (1 semilla, corte = max(validacion.anios))",
                                   "config_v32": cfg["v32"]["config"], "tiempo_s": round(time.time() - t0)})
    C.escribir_json(meta, C.dir_fase(cfg) / "lolo_v32" / "meta.json")


def lolo_v2(cfg: dict) -> None:
    from bbmodel import amortiguacion as AM, modelo as A
    acfg = AM.config()
    acfg.setdefault("validacion", {})["anios"] = [int(cfg["lolo"]["anio"])]
    sal = C.dir_fase(cfg) / "lolo_v2"
    sal.mkdir(parents=True, exist_ok=True)
    tabla, info = A.preparar()
    print(f"  tabla: {info['registros']} registros, {info['personas']} personas", flush=True)
    t0 = time.time()
    AM._validar(tabla, acfg, sal, acfg.get("variante", "completo"))
    C.escribir_json(C.metadatos(cfg, extra={"procedimiento": "bbmodel.amortiguacion._validar + dejar_fuera_liga",
                                            "tiempo_s": round(time.time() - t0)}), sal / "meta.json")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bbnorm5.diagnostico.lolo")
    ap.add_argument("--config", default="configs/v5/f1.yaml")
    ap.add_argument("modelo", choices=["v32", "v2"])
    a = ap.parse_args(argv)
    cfg = C.cargar(a.config)
    (lolo_v32 if a.modelo == "v32" else lolo_v2)(cfg)
    print(json.dumps({"hecho": a.modelo}))


if __name__ == "__main__":
    main()
