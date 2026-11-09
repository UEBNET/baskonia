"""Recalibración mensual de la temporada en curso: lo que el botón no puede hacer con parámetros congelados.

    python -m bbactualiza.recalibrar                     # todo (≈ 2,5-4 h con 4 núcleos)
    python -m bbactualiza.recalibrar --pasos cvae boton  # sólo la normalización CVAE y la publicación

Pasos (cada uno se puede lanzar suelto con --pasos):

1. ``cvae``  — reentrena las 20 redes CVAE de la normalización v3.2 con los datos actuales (en paralelo, 4 procesos ×
   1 hilo, ≈ 40 min) y recalcula la combinación v3.2 (`bbnorm3 ajustar-combinada`). Así los jugadores nuevos de
   2026-27 (que el botón deja con «sólo v2») reciben su valor CVAE y los demás lo ponen al día con sus partidos.
2. ``v40``   — modelo de equipo v4.0 para 2026-27: contrato de datos, perfiles 2026-27 (con la latente de las redes del
   paso 1), RAPM de producto, capa 4 (Net̂ de las plantillas), anclas y tablas del Atlas; regenera
   `v40/equipos_2026-27.json` (unión documentada en artifact/v40/README.md).
3. ``boton`` — `python -m bbactualiza --sin-descarga --forzar` desde el contexto hasta la publicación, para que el
   artifact recoja lo anterior (sin volver a descargar).

**El histórico no cambia**: estas órdenes reescriben ficheros de todas las temporadas; al terminar cada paso se
devuelven a su versión de Git todos los ficheros versionados de `data/modelos/` que hayan cambiado salvo los de la
temporada en curso (rutas con «2026-27») y los que el paso declara como propios de la temporada en curso.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import TEMPORADA

RAIZ = Path(__file__).resolve().parent.parent
N32 = "configs/normalization_v32.yaml"
ENV = {**os.environ, "PYTHONPATH": str(RAIZ), "MLFLOW_DISABLE_AGENT_HINT": "1", "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS", "4")}

# ficheros globales que un paso puede actualizar además de los de la temporada en curso
PROPIOS = {
    "cvae": [],
    "v40": ["data/modelos/v4_0/equipo/calibracion.json", "data/modelos/v4_0/equipo/anclas/referencia_im.json",
            "data/modelos/v4_0/equipo/anclas/F5_anclas.json", "data/modelos/v4_0/equipo/F4_equipo.json",
            "data/modelos/v4_0/contrato/*", "data/modelos/v4_0/perfiles/meta.json"],
    "boton": ["*"],          # el botón ya sólo escribe la temporada en curso (bbactualiza.capas.empalmar)
}


def _sh(*cmd: str, env: dict | None = None) -> None:
    print("$", " ".join(cmd), flush=True)
    subprocess.run(list(cmd), cwd=RAIZ, env=env or ENV, check=True)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, check=True).stdout


def restaurar_historico(propios: list[str], temporada: str = TEMPORADA) -> list[str]:
    """Devuelve a su versión de Git los ficheros versionados de data/modelos que han cambiado y no son de la temporada en
    curso ni propios del paso. Devuelve la lista de ficheros restaurados."""
    cambiados = [l for l in _git("diff", "--name-only", "--", "data/modelos").splitlines() if l]
    volver = [f for f in cambiados if temporada not in f and not any(fnmatch.fnmatch(f, p) for p in propios)]
    for i in range(0, len(volver), 200):
        _git("checkout", "--", *volver[i:i + 200])
    return volver


# ============================================================================================ pasos
def p_cvae() -> None:
    codigo = f"""
from bbnorm3 import config as C, ablacion
from bbmodel import modelo as A
cfg = C.cargar(C.RAIZ / '{N32}')
t = A.preparar()[0]
f = ablacion.guardar_tabla(t, cfg)
ablacion.entrenar([(cfg, None, s) for s in cfg['semillas']], cfg, f)
"""
    _sh(sys.executable, "-c", codigo)                     # redes en paralelo (caché experimentos/v3)
    _sh(sys.executable, "-m", "bbnorm3", "--config", N32, "ajustar-combinada")


def p_v40() -> None:
    import shutil
    meta = RAIZ / "data/modelos/v4_0/perfiles/meta.json"
    copia = meta.read_text(encoding="utf-8") if meta.exists() else None
    _sh(sys.executable, "-m", "bbequipo", "contrato")
    _sh(sys.executable, "-m", "bbequipo", "perfiles", "--temporadas", TEMPORADA)
    if copia:                                             # perfiles reescribe meta.json sólo con la temporada pedida
        nuevo = json.loads(meta.read_text(encoding="utf-8"))
        viejo = json.loads(copia)
        if isinstance(viejo.get("temporadas"), dict) and isinstance(nuevo.get("temporadas"), dict):
            viejo["temporadas"].update(nuevo["temporadas"])
            meta.write_text(json.dumps(viejo, ensure_ascii=False, indent=1), encoding="utf-8")
    for orden in ("rapm-producto", "equipo-producto", "anclas-producto"):
        _sh(sys.executable, "-m", "bbequipo", orden)
    sal = RAIZ / "data/artifact/atlas_v40"
    shutil.rmtree(sal, ignore_errors=True)
    _sh(sys.executable, "-m", "bbequipo", "exportar-atlas", "--salida", str(sal))
    equipos_v40()


def equipos_v40(temporada: str = TEMPORADA) -> Path:
    """v40/equipos_<t>.json de la página del modelo de equipo (unión de artifact/v40/README.md)."""
    import numpy as np
    import pandas as pd
    e = pd.read_csv(RAIZ / f"data/modelos/v4_0/equipo/equipos_{temporada}.csv.gz", dtype={"team_id": str})
    cal = json.loads((RAIZ / "data/modelos/v4_0/equipo/calibracion.json").read_text(encoding="utf-8"))
    nombres = {}
    for f in (RAIZ / "data/processed" / temporada / "ligas").glob("*.csv"):
        d = pd.read_csv(f, usecols=["liga", "team_id", "equipo"], dtype=str).dropna()
        nombres.update({(r.liga, r.team_id): r.equipo for r in d.drop_duplicates(["liga", "team_id"]).itertuples()})
    e["equipo"] = [nombres.get((l, t)) for l, t in zip(e["liga"], e["team_id"])]
    e["puesto"] = e.groupby("liga")["net_proyectado_relativo"].rank(ascending=False, method="first").astype(int)
    e["n_liga"] = e.groupby("liga")["team_id"].transform("count")
    ints = {g: v["intervalo"] for g, v in cal.get("por_grupo", {}).items()}
    def banda(r):
        i = ints.get(r.grupo, cal["conjunto"]["intervalo"])
        return i["q"] * np.sqrt((r.c_cal * r.T_sd) ** 2 + i["s0"] ** 2)
    b = e.apply(banda, axis=1)
    e["lo80"], e["hi80"] = (e["net_proyectado_relativo"] - b).round(2), (e["net_proyectado_relativo"] + b).round(2)
    cols = ["liga", "temporada", "team_id", "equipo", "T", "T_sd", "T_centrada", "net_proyectado_relativo", "T_aditivo",
            "T_phi", "T_h", "n_plantilla", "n_sin_beta", "c_cal", "puesto", "n_liga", "lo80", "hi80", "grupo"]
    e = e.sort_values(["liga", "puesto"])[cols]
    filas = [[None if (isinstance(v, float) and not np.isfinite(v)) else (v.item() if hasattr(v, "item") else v)
              for v in r] for r in e.itertuples(index=False)]
    sal = RAIZ / "data/artifact/v40"
    sal.mkdir(parents=True, exist_ok=True)
    (sal / f"equipos_{temporada}.json").write_text(json.dumps({"columnas": cols, "filas": filas}, ensure_ascii=False,
                                                              separators=(",", ":")), encoding="utf-8")
    (sal / "calibracion.json").write_text(json.dumps(cal, ensure_ascii=False), encoding="utf-8")
    return sal / f"equipos_{temporada}.json"


def p_boton() -> None:
    _sh(sys.executable, "-m", "bbactualiza", "--sin-descarga", "--forzar", "--pasos", "contexto", "roles", "entropia",
        "estilos", "simulador", "artifact", "publicacion")


PASOS = {"cvae": p_cvae, "v40": p_v40, "boton": p_boton}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m bbactualiza.recalibrar")
    ap.add_argument("--pasos", nargs="*", choices=list(PASOS), default=list(PASOS))
    ap.add_argument("--permitir-cambios", action="store_true",
                    help="arranca aunque data/modelos tenga cambios sin subir (se podrían revertir: no recomendado)")
    a = ap.parse_args(argv)
    if not a.permitir_cambios and _git("diff", "--name-only", "--", "data/modelos").strip():
        print("data/modelos tiene cambios sin subir: la recalibración restaura el histórico desde Git y los revertiría. "
              "Sube o descarta esos cambios antes (o usa --permitir-cambios).", file=sys.stderr)
        return 2
    inf = {"inicio": datetime.now(timezone.utc).isoformat(timespec="seconds"), "pasos": {}, "estado": "ok"}
    for n in [p for p in PASOS if p in a.pasos]:
        t0 = time.time()
        try:
            PASOS[n]()
            vueltos = restaurar_historico(PROPIOS[n])
            inf["pasos"][n] = {"estado": "ok", "segundos": round(time.time() - t0), "restaurados": len(vueltos)}
        except Exception as e:  # noqa: BLE001
            restaurar_historico(PROPIOS[n])
            inf["pasos"][n] = {"estado": "error", "segundos": round(time.time() - t0), "error": f"{type(e).__name__}: {e}"}
            inf["estado"] = "error"
            break
        print(f"--- {n}: {inf['pasos'][n]}", flush=True)
    inf["fin"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    d = RAIZ / "data/modelos/actualizacion"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ultima_recalibracion.json").write_text(json.dumps(inf, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(inf, ensure_ascii=False, indent=1))
    return 0 if inf["estado"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
