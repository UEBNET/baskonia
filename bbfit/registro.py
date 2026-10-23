"""Registro de experimentos en MLflow (almacén local experimentos/mlruns) con semilla y configuración.

Uso:
    with experimento("roles", "reglas_v1", params={...}) as run:
        run.metricas({"acierto": 0.93})
        run.artefacto("data/modelos/roles/resumen.json")
Si MLflow no está instalado, el registro se degrada a un JSON en experimentos/registro_local.jsonl (no falla).
"""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

from .config import RAIZ

DIR_EXP = RAIZ / "experimentos"


class _Run:
    def __init__(self, mlflow=None, local: dict | None = None):
        self._m, self._local = mlflow, local

    def metricas(self, d: dict) -> None:
        d = {k: float(v) for k, v in d.items() if v is not None}
        if self._m:
            self._m.log_metrics(d)
        else:
            self._local.setdefault("metricas", {}).update(d)

    def artefacto(self, ruta) -> None:
        if self._m and Path(ruta).exists():
            self._m.log_artifact(str(ruta))


@contextmanager
def experimento(nombre: str, run: str, params: dict | None = None, semilla: int | None = None):
    params = {**(params or {}), **({"semilla": semilla} if semilla is not None else {})}
    try:
        # almacén de ficheros local (experimentos/mlruns): MLflow 3 lo exige explícitamente
        os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
        import mlflow
        DIR_EXP.mkdir(exist_ok=True)
        mlflow.set_tracking_uri((DIR_EXP / "mlruns").as_uri())
        mlflow.set_experiment(nombre)
        with mlflow.start_run(run_name=run):
            if params:
                mlflow.log_params({k: str(v)[:500] for k, v in params.items()})
            yield _Run(mlflow=mlflow)
    except ImportError:
        local = {"experimento": nombre, "run": run, "params": params, "inicio": time.time()}
        yield _Run(local=local)
        DIR_EXP.mkdir(exist_ok=True)
        with open(DIR_EXP / "registro_local.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(local, ensure_ascii=False, default=str) + "\n")
