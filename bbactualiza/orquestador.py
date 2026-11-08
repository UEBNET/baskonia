"""Orden de la actualización rápida de la temporada en curso, con tiempos por paso e informe.

Cada paso es independiente y se puede lanzar solo (`--pasos`). Si los datos procesados de la temporada no han cambiado
desde la última actualización (huella de los CSV), el posproceso se salta entero: la pulsación cuesta sólo la descarga.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from . import TEMPORADA

RAIZ = Path(__file__).resolve().parent.parent
ESTADO = RAIZ / "data" / "modelos" / "actualizacion"
SKILL = RAIZ / ".claude" / "skills" / "actualizar-temporada" / "actualizar_delta.py"


def _delta():
    spec = importlib.util.spec_from_file_location("actualizar_delta", SKILL)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


VOLATILES = ("fecha_extraccion", "archivo_bruto", "generado")


def huella(temporada: str = TEMPORADA) -> str:
    """Huella de los datos procesados de la temporada (tablas por liga y jugada a jugada), sin las columnas que cambian
    en cada descarga aunque no haya partidos nuevos (fecha de extracción y nombre del bruto)."""
    import pandas as pd
    h = hashlib.sha256()
    base = RAIZ / "data" / "processed" / temporada
    for p in sorted(list(base.glob("ligas/*.csv")) + list(base.glob("quintetos/*/*.csv*"))):
        h.update(p.relative_to(base).as_posix().encode())
        d = pd.read_csv(p, dtype=str, keep_default_na=False, low_memory=False)
        d = d.drop(columns=[c for c in VOLATILES if c in d.columns])
        h.update(hashlib.sha256(d.to_csv(index=False).encode()).digest())
    return h.hexdigest()


# ============================================================================================ pasos
def p_descarga(ctx: dict) -> dict:
    r = _delta().actualizar(temporada=ctx["temporada"], ligas=ctx.get("ligas"), descargar=not ctx["sin_descarga"],
                            entrenadores=True, artifact=False, progreso=ctx["log"])
    return {"estado": r.get("estado"), "ligas": {x["liga"]: {"estado": x.get("estado"),
                                                             "partidos_nuevos": x.get("partidos_nuevos"),
                                                             "incidencias": x.get("incidencias")}
                                                for x in r.get("resultado", [])}}


def p_pista(ctx):
    from . import capas
    return {"filas_pista": capas.pista(ctx["temporada"]), "filas_interacciones": capas.interacciones(ctx["temporada"]),
            "filas_nacionalidades": capas.nacionalidades(ctx["temporada"])}


def p_normalizacion(ctx):
    from . import normalizacion
    return normalizacion.ejecutar(ctx["temporada"], progreso=ctx["log"])


def p_contexto(ctx):
    """Contexto de nivel con la normalización nueva y segunda pasada del dataset normalizado (dependencia circular,
    como en scripts/actualizar_20ligas.sh: normalizado → contexto → normalizado)."""
    from . import capas, normalizacion
    from bbmodel import dataset_normalizado as DN
    n = capas.contexto(ctx["temporada"])
    v1 = DN.construir(ctx["temporada"])
    v1.to_csv(normalizacion.DIR_V1 / f"{ctx['temporada']}.csv", index=False, float_format="%.4f")
    t = normalizacion.tabla()
    normalizacion.v32_incremental(ctx["temporada"], normalizacion.temporadas_por_liga(t, ctx["temporada"]))
    return {"filas_contexto": n}


def p_roles(ctx):
    from . import capas
    return {"filas_roles": capas.roles(ctx["temporada"])}


def p_entropia(ctx):
    from . import capas
    capas.entropia()
    return {}


def p_estilos(ctx):
    from . import capas
    r = capas.estilos()
    return {"k": r.get("k") if isinstance(r, dict) else None}


def p_simulador(ctx):
    from . import artefacto, capas
    r = capas.simulador(artefacto.DA / "simulador")
    return {"clubes": len(r.get("clubes", [])) if isinstance(r, dict) and isinstance(r.get("clubes"), list) else None}


def p_artifact(ctx):
    from . import artefacto as A
    t = ctx["temporada"]
    A.tablas(t)
    A.nacionalidades_json(t)
    A.evaluacion(t)
    A.normalizados(t)
    A.compactar()
    A.atlas_estilos()
    A.informe(t)
    A.quintetos(t)
    return {}


def p_publicacion(ctx):
    """Resumen público de la actualización (datos/actualizacion.json, lo lee el botón) y lote de publicación."""
    from . import artefacto
    inf, previa = ctx["inf"], ctx.get("previa") or {}
    ligas = (inf["pasos"].get("descarga") or {}).get("ligas") or previa.get("ligas_publicas") or {}
    resumen = {"temporada": ctx["temporada"], "fin": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "inicio": inf["inicio"], "ligas": {l: {"estado": v.get("estado"), "partidos_nuevos": v.get("partidos_nuevos")}
                                                  for l, v in ligas.items()},
               "pasos": {n: p.get("segundos") for n, p in inf["pasos"].items()}}
    inf["ligas_publicas"] = resumen["ligas"]
    (artefacto.DA / "actualizacion.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    return artefacto.empaquetar(ctx["publicacion"], ctx["temporada"])


PASOS = [("descarga", p_descarga), ("pista", p_pista), ("normalizacion", p_normalizacion), ("contexto", p_contexto),
         ("roles", p_roles), ("entropia", p_entropia), ("estilos", p_estilos), ("simulador", p_simulador),
         ("artifact", p_artifact), ("publicacion", p_publicacion)]
NOMBRES = [n for n, _ in PASOS]


# ============================================================================================ ejecución
def ejecutar(temporada: str = TEMPORADA, pasos: list[str] | None = None, sin_descarga: bool = False,
             forzar: bool = False, ligas: list[str] | None = None, publicacion: str | Path | None = None,
             log=print) -> dict:
    os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
    ESTADO.mkdir(parents=True, exist_ok=True)
    cerrojo = ESTADO / ".en_curso"
    if cerrojo.exists() and time.time() - cerrojo.stat().st_mtime < 3 * 3600:
        return {"estado": "ocupado", "mensaje": f"otra actualización en curso desde {cerrojo.read_text()}"}
    cerrojo.write_text(datetime.now(timezone.utc).isoformat(timespec="seconds"))
    pasos = pasos or NOMBRES
    publicacion = Path(publicacion or RAIZ / "publicacion")
    ctx = {"temporada": temporada, "sin_descarga": sin_descarga, "ligas": ligas, "publicacion": publicacion, "log": log}
    inf = {"temporada": temporada, "inicio": datetime.now(timezone.utc).isoformat(timespec="seconds"), "pasos": {},
           "estado": "ok"}
    previa = json.loads((ESTADO / "ultima.json").read_text(encoding="utf-8")) if (ESTADO / "ultima.json").exists() else {}
    ctx["inf"], ctx["previa"] = inf, previa
    t_total = time.time()
    try:
        for nombre, f in PASOS:
            if nombre not in pasos:
                continue
            if nombre == "pista":           # tras la descarga: ¿hay algo nuevo que procesar?
                inf["huella"] = huella(temporada)
                if not forzar and inf["huella"] == previa.get("huella") and "descarga" in pasos:
                    log("Sin partidos nuevos desde la última actualización: no hace falta recalcular ni publicar.")
                    inf["estado"] = "sin_cambios"
                    break
            log(f"=== {datetime.now().strftime('%H:%M:%S')} {nombre}")
            t0 = time.time()
            try:
                res = f(ctx) or {}
                inf["pasos"][nombre] = {"estado": "ok", "segundos": round(time.time() - t0), **res}
            except Exception as e:  # noqa: BLE001 — se informa y se detiene: un paso a medias no se publica
                inf["pasos"][nombre] = {"estado": "error", "segundos": round(time.time() - t0),
                                        "error": f"{type(e).__name__}: {e}", "traza": traceback.format_exc()[-2000:]}
                inf["estado"] = "error"
                log(f"ERROR en {nombre}: {e}")
                break
            log(f"    {nombre}: {inf['pasos'][nombre]['segundos']} s")
    finally:
        cerrojo.unlink(missing_ok=True)
    inf["fin"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    inf["segundos"] = round(time.time() - t_total)
    if inf["estado"] == "ok" and "huella" not in inf:
        inf["huella"] = huella(temporada)
    if inf["estado"] in ("ok", "sin_cambios"):
        guardar = {k: v for k, v in inf.items()}
        for p in guardar["pasos"].values():
            p.pop("traza", None)
        if inf["estado"] == "sin_cambios":
            guardar = {**previa, "ultima_comprobacion": inf["fin"], "pasos_ultima_comprobacion": inf["pasos"]}
        (ESTADO / "ultima.json").write_text(json.dumps(guardar, ensure_ascii=False, indent=1, default=str),
                                             encoding="utf-8")
    return inf


def tabla_md(inf: dict) -> str:
    filas = ["| Paso | Estado | Segundos |", "|---|---|---|"]
    for n, p in inf.get("pasos", {}).items():
        filas.append(f"| {n} | {p.get('estado')} | {p.get('segundos')} |")
    filas.append(f"| **total** | **{inf.get('estado')}** | **{inf.get('segundos')}** |")
    return "\n".join(filas)
