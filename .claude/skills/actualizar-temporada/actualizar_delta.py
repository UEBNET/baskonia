"""Actualización delta (descarga única) de la temporada en curso.

Envuelve, SIN modificarlo, el pipeline de extracción existente (`bbstats`) y lo acota a una sola
temporada (por defecto la de `config/sources.json → temporada_por_defecto`, hoy 2026-27):

  0. Foto «antes»: por liga, filas, jugadores, equipos, partidos y última fecha de partido.
  1. Descarga delta + procesado (`bbstats.api.ejecutar`): cajas, métricas, fases, jugada a jugada,
     quintetos, parejas, tríos, tiros y on/off donde la liga ya los tiene. Delta porque cada adaptador
     reutiliza el último bruto guardado y sólo pide a la web lo que falta (los adaptadores FEB, FIBA web y
     FIBA LiveStats guardan además paquetes incrementales sólo con los partidos nuevos).
  2. Entrenadores por partido y tramos club-temporada-entrenador (`bbstats.entrenadores.ejecutar`).
  3. Informes FEB (cobertura, posesiones, contrato) si entra alguna liga FEB (`bbstats.feb_informe`).
  4. JSON del Artifact para esa temporada (`bbstats.pipeline.export_artifact`, no versionado).
  5. Foto «después», comparación y comprobaciones (esquema de 480 columnas, ligas sin partidos, última
     fecha atrasada, errores de cada liga).

Salida: un informe JSON (pensado para que lo lea un botón del artifact «Cerno Analytics») en
`data/processed/<t>/informes/delta_<fecha>.json` (carpeta no versionada) y una tabla en pantalla.

    python .claude/skills/actualizar-temporada/actualizar_delta.py                      # todas las ligas
    python .claude/skills/actualizar-temporada/actualizar_delta.py --ligas feb1 feb2 feb3
    python .claude/skills/actualizar-temporada/actualizar_delta.py --sin-descarga       # sólo reprocesar
    python .claude/skills/actualizar-temporada/actualizar_delta.py --solo-informe       # sólo la foto actual

Código de salida: 0 si ninguna liga terminó en error; 1 si alguna falló; 2 si ya había otra
actualización en curso (cerrojo `data/processed/<t>/.delta.lock`).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import pandas as pd  # noqa: E402

from bbstats.config import active_leagues, load_config, resolve_path  # noqa: E402
from bbstats.schema import COLUMN_NAMES  # noqa: E402

# Ligas cuyo calendario 2026-27 empieza tarde: cero partidos antes de esa fecha no es incidencia.
INICIO_TARDIO = {"gleague": (11, 1)}
# Días sin partidos nuevos a partir de los cuales se marca la liga (en plena temporada se juega cada semana).
DIAS_ATRASO = 10

_MESES = {"ja": [1], "fe": [2], "ma": [3, 5], "ap": [4], "ju": [6, 7], "au": [8], "se": [9], "oc": [10],
          "no": [11], "de": [12]}
_DIAS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


# ============================================================================================ fechas
def fecha_partido(valor, temporada: str) -> date | None:
    """Convierte la fecha de un partido a `date`.

    Admite ISO (`2026-10-14`) y el formato recortado que hoy dejan BSL y GBL en los CSV de entrenadores
    (`Fri, 02 Oc`: día de la semana, día y dos letras del mes, sin año). El año sale de la temporada
    (agosto-diciembre → primer año; enero-julio → segundo) y, si el mes es ambiguo (Ma = marzo/mayo,
    Ju = junio/julio), decide el día de la semana."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    s = str(valor).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    m = re.match(r"^([A-Za-z]{3}),\s*(\d{1,2})\s+([A-Za-z]{2})", s)
    if not m:
        return None
    dia_sem, dia, mes2 = _DIAS.get(m[1].lower()), int(m[2]), m[3].lower()
    a1 = int(temporada[:4])
    candidatas = []
    for mes in _MESES.get(mes2, []):
        try:
            candidatas.append(date(a1 if mes >= 8 else a1 + 1, mes, dia))
        except ValueError:
            continue
    buenas = [c for c in candidatas if dia_sem is None or c.weekday() == dia_sem]
    return (buenas or candidatas or [None])[0]


# ============================================================================================ foto
def _partidos_y_fechas(proc: Path, liga: str, temporada: str) -> tuple[int | None, str | None, str]:
    """Partidos distintos y última fecha. Fuente preferente: CSV por partido (FEB, entrenadores);
    si no existen, se estiman los partidos desde `team_gp` del CSV de la liga (Σ partidos de equipo / 2)."""
    for f, col_jugado in ((proc / "feb" / f"{liga}_partidos.csv", "jugado"),
                          (proc / "entrenadores" / f"{liga}_partidos.csv", None)):
        if not f.exists():
            continue
        df = pd.read_csv(f, dtype=str)
        if df.empty:
            return 0, None, f.relative_to(proc).as_posix()
        if col_jugado and col_jugado in df.columns:
            df = df[df[col_jugado].str.lower() == "true"]
        fechas = [d for d in (fecha_partido(v, temporada) for v in df.get("fecha", [])) if d]
        return int(df["game_id"].nunique()), (max(fechas).isoformat() if fechas else None), f.relative_to(proc).as_posix()
    csv = proc / "ligas" / f"{liga}.csv"
    if csv.exists():
        df = pd.read_csv(csv, usecols=lambda c: c in ("fase", "team_id", "team_gp"))
        tot = df[df["fase"] == "total"]
        if not tot.empty and "team_gp" in tot:
            return int(round(tot.groupby("team_id")["team_gp"].max().sum() / 2)), None, "ligas (team_gp)"
    return None, None, "—"


def foto(temporada: str, ligas: list[str], cfg: dict) -> dict:
    """Estado de los datos procesados de la temporada, liga a liga (sólo lectura, sin red)."""
    proc = resolve_path(cfg, "procesado") / temporada
    out = {}
    for liga in ligas:
        csv = proc / "ligas" / f"{liga}.csv"
        d = {"filas": 0, "filas_por_fase": {}, "jugadores": 0, "equipos": 0, "partidos": 0,
             "ultima_fecha": None, "fuente_partidos": "—", "partidos_con_quintetos": 0,
             "columnas_ok": None, "fecha_extraccion": None}
        if csv.exists():
            cab = pd.read_csv(csv, nrows=0).columns.tolist()
            d["columnas_ok"] = cab == COLUMN_NAMES
            df = pd.read_csv(csv, usecols=["fase", "player_id", "team_id", "fecha_extraccion"], dtype=str)
            d["filas"] = len(df)
            d["filas_por_fase"] = df["fase"].value_counts().to_dict()
            tot = df[df["fase"] == "total"]
            d["jugadores"] = int(tot["player_id"].nunique())
            d["equipos"] = int(tot["team_id"].nunique())
            d["fecha_extraccion"] = df["fecha_extraccion"].dropna().max() if not df.empty else None
        d["partidos"], d["ultima_fecha"], d["fuente_partidos"] = _partidos_y_fechas(proc, liga, temporada)
        val = proc / "quintetos" / liga / "validacion.csv"
        if val.exists():
            v = pd.read_csv(val, usecols=lambda c: c in ("game_id", "usado_en_quintetos"))
            d["partidos_con_quintetos"] = int(v.loc[v.get("usado_en_quintetos", True) == True, "game_id"].nunique())  # noqa: E712
        out[liga] = d
    return out


# ============================================================================================ control
def incidencias(liga: str, antes: dict, despues: dict, informe_liga: dict | None, hoy: date) -> list[str]:
    inc = []
    if informe_liga:
        if informe_liga.get("estado") == "error":
            inc.append("ERROR: " + "; ".join(informe_liga.get("errores", [])[:3]))
        elif informe_liga.get("estado") == "ok_bruto_anterior":
            inc.append("descarga fallida, se reprocesó el bruto anterior: "
                       + "; ".join(informe_liga.get("errores", [])[:2]))
    if despues.get("columnas_ok") is False:
        inc.append("el CSV no tiene las 480 columnas del esquema canónico")
    if (despues.get("partidos") or 0) < (antes.get("partidos") or 0):
        inc.append(f"menos partidos que antes ({antes.get('partidos')} → {despues.get('partidos')})")
    if not despues.get("partidos"):
        tardio = INICIO_TARDIO.get(liga)
        if tardio and hoy < date(hoy.year, *tardio):
            inc.append("sin partidos (normal: el calendario empieza en noviembre)")
        else:
            inc.append("SIN PARTIDOS: revisar calendario y fuente")
    uf = despues.get("ultima_fecha")
    if uf and (hoy - date.fromisoformat(uf)).days > DIAS_ATRASO:
        inc.append(f"última fecha {uf}: más de {DIAS_ATRASO} días sin partidos nuevos")
    return inc


def _tabla(filas: list[dict]) -> str:
    cab = ["liga", "partidos antes", "partidos después", "última fecha antes", "última fecha después",
           "jugadores", "equipos", "incidencias"]
    lineas = ["| " + " | ".join(cab) + " |", "|" + "---|" * len(cab)]
    for f in filas:
        a, d = f["antes"], f["despues"]
        lineas.append("| " + " | ".join("—" if x is None else str(x) for x in (
            f["liga"], a.get("partidos"), d.get("partidos"), a.get("ultima_fecha") or "—",
            d.get("ultima_fecha") or "—", d.get("jugadores"), d.get("equipos"),
            "; ".join(f["incidencias"]) or "—")) + " |")
    return "\n".join(lineas)


# ============================================================================================ principal
def actualizar(temporada: str | None = None, ligas: list[str] | None = None, descargar: bool = True,
               entrenadores: bool = True, artifact: bool = True, solo_informe: bool = False,
               config: str | None = None, progreso=print) -> dict:
    """Ejecuta la actualización delta y devuelve el informe (dict JSON-serializable)."""
    cfg = load_config(config)
    t = temporada or cfg["temporada_por_defecto"]
    if t != cfg["temporada_por_defecto"]:
        raise ValueError(f"Esta skill sólo actualiza la temporada en curso ({cfg['temporada_por_defecto']}); "
                         f"para otras temporadas usa `python -m bbstats ejecutar --temporada {t}`")
    ligas = ligas or active_leagues(cfg)
    proc = resolve_path(cfg, "procesado") / t
    proc.mkdir(parents=True, exist_ok=True)
    hoy = datetime.now(timezone.utc).date()
    inicio = datetime.now(timezone.utc)
    informe = {"skill": "actualizar-temporada", "temporada": t, "ligas": ligas,
               "modo": "solo_informe" if solo_informe else ("delta" if descargar else "reprocesar"),
               "inicio": inicio.isoformat(), "pasos": {}}

    cerrojo = proc / ".delta.lock"
    if not solo_informe:
        try:
            fd = os.open(cerrojo, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, inicio.isoformat().encode())
            os.close(fd)
        except FileExistsError:
            informe["estado"] = "ocupado"
            informe["mensaje"] = f"Ya hay una actualización en curso (cerrojo {cerrojo})"
            return informe
    try:
        progreso(f"[delta] foto antes ({t}, {len(ligas)} ligas)")
        antes = foto(t, ligas, cfg)
        rep_ligas: dict = {}
        if not solo_informe:
            from bbstats import api
            t0 = time.monotonic()
            rep = (api.ejecutar if descargar else api.reprocesar)(ligas=ligas, temporada=t, config=cfg,
                                                                  progreso=progreso)
            rep_ligas = {l["liga"]: l for l in rep["ligas"]}
            informe["pasos"]["extraccion"] = {"segundos": round(time.monotonic() - t0, 1),
                                              "estados": {k: v["estado"] for k, v in rep_ligas.items()}}
            if entrenadores:
                from bbstats.entrenadores import ejecutar as ejecutar_entrenadores, extractor_de
                t0 = time.monotonic()
                con_lector = [l for l in ligas if extractor_de(l, cfg["ligas"][l])]
                try:
                    out = ejecutar_entrenadores(temporadas=[t], ligas=con_lector, descargar=descargar, config=cfg,
                                                progreso=progreso)
                    informe["pasos"]["entrenadores"] = {"segundos": round(time.monotonic() - t0, 1),
                                                        "estados": {k: v.get("estado") for k, v in out.items()}}
                except Exception as exc:  # noqa: BLE001 - se informa; no invalida la extracción
                    informe["pasos"]["entrenadores"] = {"error": f"{type(exc).__name__}: {exc}"}
            feb = [l for l in ligas if l in ("feb1", "feb2", "feb3")]
            if feb:
                from bbstats import feb_informe
                try:
                    feb_informe.ejecutar(ligas=feb, temporadas=[t], config=cfg, progreso=progreso)
                    informe["pasos"]["feb_informes"] = {"ligas": feb}
                except Exception as exc:  # noqa: BLE001
                    informe["pasos"]["feb_informes"] = {"error": f"{type(exc).__name__}: {exc}"}
            if artifact:
                from bbstats.pipeline import export_artifact
                try:
                    files = export_artifact(resolve_path(cfg, "procesado"), t, RAIZ / "data" / "artifact")
                    informe["pasos"]["artifact"] = {"ficheros": len(list(files))}
                except Exception as exc:  # noqa: BLE001
                    informe["pasos"]["artifact"] = {"error": f"{type(exc).__name__}: {exc}"}
        progreso("[delta] foto después")
        despues = foto(t, ligas, cfg)
        filas = []
        for l in ligas:
            filas.append({"liga": l, "antes": antes[l], "despues": despues[l],
                          "partidos_nuevos": (despues[l]["partidos"] or 0) - (antes[l]["partidos"] or 0),
                          "estado": rep_ligas.get(l, {}).get("estado"),
                          "incidencias": incidencias(l, antes[l], despues[l], rep_ligas.get(l), hoy)})
        informe["resultado"] = filas
        informe["tabla_md"] = _tabla(filas)
        informe["estado"] = "error_parcial" if any(f["estado"] == "error" for f in filas) else "ok"
        informe["fin"] = datetime.now(timezone.utc).isoformat()
        hist = proc / "informes"
        hist.mkdir(exist_ok=True)
        ruta = hist / f"delta_{inicio.strftime('%Y%m%dT%H%M%SZ')}.json"
        ruta.write_text(json.dumps(informe, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        informe["ruta_informe"] = str(ruta.relative_to(RAIZ))
        return informe
    finally:
        if not solo_informe:
            cerrojo.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Actualización delta de la temporada en curso (todas las ligas)")
    ap.add_argument("--temporada", help="Sólo se admite la temporada en curso (por defecto, la de la config)")
    ap.add_argument("--ligas", nargs="*", help="Códigos de liga (por defecto, todas las activas)")
    ap.add_argument("--sin-descarga", action="store_true", help="Reprocesar los brutos guardados, sin red")
    ap.add_argument("--sin-entrenadores", action="store_true", help="No recalcular entrenadores")
    ap.add_argument("--sin-artifact", action="store_true", help="No regenerar data/artifact/<t>/")
    ap.add_argument("--solo-informe", action="store_true", help="Sólo la foto actual, sin descargar ni procesar")
    ap.add_argument("--json", action="store_true", help="Imprimir el informe completo en JSON")
    ap.add_argument("--config")
    a = ap.parse_args(argv)
    inf = actualizar(temporada=a.temporada, ligas=a.ligas or None, descargar=not a.sin_descarga,
                     entrenadores=not a.sin_entrenadores, artifact=not a.sin_artifact,
                     solo_informe=a.solo_informe, config=a.config)
    if inf.get("estado") == "ocupado":
        print(inf["mensaje"])
        return 2
    print(json.dumps(inf, ensure_ascii=False, indent=1, default=str) if a.json else inf["tabla_md"])
    print(f"\nEstado: {inf['estado']} · informe: {inf.get('ruta_informe')}")
    return 1 if inf["estado"] == "error_parcial" else 0


if __name__ == "__main__":
    sys.exit(main())
