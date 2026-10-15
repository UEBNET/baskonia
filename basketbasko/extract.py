"""Rastreo controlado: login → equipos del club → estadísticas de equipo, jugadores, partidos y rivales.

Todo lo descargado se guarda SIN TOCAR en un JSON comprimido con fecha (`raw/<fecha>.json.gz`), para poder
reprocesar sin volver a conectarse. Las estadísticas de partidos ya jugados no cambian: se guardan en
`cache/partidos/` y no se vuelven a pedir en ejecuciones siguientes.
"""
from __future__ import annotations

import gzip
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .client import ApiError, BasketBaskoClient

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "basketbasko.json"


def load_config(path: str | Path | None = None) -> dict:
    cfg = json.loads(Path(path or CONFIG).read_text(encoding="utf-8"))
    cfg["directorio_datos"] = str((ROOT / cfg.get("directorio_datos", "data/basketbasko")).resolve())
    return cfg


def explorar(client: BasketBaskoClient, salida: Path) -> dict:
    """Paso 1 de la extracción controlada: descarga una muestra mínima y documenta su estructura.

    Guarda las respuestas en `salida/` y devuelve un resumen de claves para validar que los datos
    que interesan están ahí antes de lanzar el rastreo completo.
    """
    salida.mkdir(parents=True, exist_ok=True)
    muestras: dict[str, Any] = {"login": client.login()}
    for nombre, path in (("mi_club", "/auth/my-club"), ("mis_equipos", "/auth/my-teams")):
        muestras[nombre] = _safe(lambda p=path: client.esb(p))
    equipos = find_teams(muestras["mis_equipos"])
    if equipos:
        uuid = equipos[0]["uuid"]
        muestras["stats_equipo"] = _safe(lambda: client.stats(f"/teams/{uuid}/stats"))
        roster = (muestras["stats_equipo"] or {}).get("roster") or [] if isinstance(muestras["stats_equipo"], dict) else []
        if roster and roster[0].get("uuid"):
            muestras["stats_jugador"] = _safe(lambda: client.stats(f"/players/{roster[0]['uuid']}/teams/{uuid}/stats"))
        games = (muestras["stats_equipo"] or {}).get("games") or [] if isinstance(muestras["stats_equipo"], dict) else []
        mc = next((g.get("matchCallUuid") for g in games if g.get("matchCallUuid")), None)
        if mc:
            muestras["stats_partido"] = _safe(lambda: client.stats(f"/matches/{mc}/stats?currentSeason=true"))
    resumen = {}
    for nombre, data in muestras.items():
        (salida / f"{nombre}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        resumen[nombre] = describe(data)
    resumen["equipos_detectados"] = equipos
    resumen["peticiones"] = client.peticiones
    (salida / "_estructura.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    return resumen


def extraer(client: BasketBaskoClient, cfg: dict, progreso: Callable[[str], None] = print) -> Path:
    """Rastreo completo según la configuración. Devuelve la ruta del JSON bruto generado."""
    base = Path(cfg["directorio_datos"])
    cache_partidos = base / "cache" / "partidos"
    cache_partidos.mkdir(parents=True, exist_ok=True)
    fecha = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bruto: dict[str, Any] = {"meta": {"fecha": fecha, "errores": []}, "club": None, "mis_equipos": None,
                             "equipos": {}, "jugadores": {}, "partidos": {}}
    errores = bruto["meta"]["errores"]

    def intentar(desc: str, fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except ApiError as exc:
            errores.append(f"{desc}: {exc}")
            log.warning("%s: %s", desc, exc)
            return None

    client.login()
    bruto["club"] = intentar("mi club", lambda: client.esb("/auth/my-club"))
    temporada = cfg.get("temporada_id")
    path_eq = f"/auth/my-teams/season/{temporada}" if temporada else "/auth/my-teams"
    bruto["mis_equipos"] = intentar("mis equipos", lambda: client.esb(path_eq))

    propios = {t["uuid"]: t for t in find_teams(bruto["mis_equipos"])}
    for uuid in cfg.get("equipos") or []:          # equipos añadidos a mano en la configuración
        propios.setdefault(uuid, {"uuid": uuid, "nombre": None})
    progreso(f"Equipos propios: {len(propios)}")

    cola = list(propios)
    vistos: set[str] = set()
    while cola:
        uuid = cola.pop(0)
        if uuid in vistos:
            continue
        vistos.add(uuid)
        data = intentar(f"equipo {uuid}", lambda: client.stats(f"/teams/{uuid}/stats"))
        if not isinstance(data, dict):
            continue
        es_propio = uuid in propios
        bruto["equipos"][uuid] = {"propio": es_propio, "stats": data}
        progreso(f"  equipo {team_name(data) or uuid}: {len(data.get('roster') or [])} jugadores, "
                 f"{len(data.get('games') or [])} partidos")
        if cfg.get("incluir_jugadores", True):
            for p in data.get("roster") or []:
                pid = p.get("uuid")
                if pid and es_propio:
                    bruto["jugadores"][f"{pid}:{uuid}"] = intentar(
                        f"jugador {pid}", lambda pid=pid: client.stats(f"/players/{pid}/teams/{uuid}/stats"))
        for g in data.get("games") or []:
            mc = g.get("matchCallUuid")
            if cfg.get("incluir_partidos", True) and mc and mc not in bruto["partidos"] and es_propio:
                cached = cache_partidos / f"{mc}.json"
                if cached.exists():
                    bruto["partidos"][mc] = json.loads(cached.read_text(encoding="utf-8"))
                else:
                    stats = intentar(f"partido {mc}", lambda mc=mc: client.stats(f"/matches/{mc}/stats?currentSeason=true"))
                    if stats:
                        bruto["partidos"][mc] = stats
                        cached.write_text(json.dumps(stats, ensure_ascii=False), encoding="utf-8")
            rival = (g.get("opponent") or {}).get("uuid")
            if cfg.get("incluir_rivales") and rival and rival not in vistos and es_propio:
                cola.append(rival)

    bruto["meta"]["peticiones"] = client.peticiones
    raw_dir = base / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out = raw_dir / f"intranet_{fecha}.json.gz"
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        json.dump(bruto, fh, ensure_ascii=False)
    progreso(f"Bruto guardado en {out} ({client.peticiones} peticiones, {len(errores)} errores)")
    return out


def ultimo_bruto(cfg: dict) -> Path | None:
    files = sorted((Path(cfg["directorio_datos"]) / "raw").glob("intranet_*.json.gz"))
    return files[-1] if files else None


def leer_bruto(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------- utilidades
def find_teams(data: Any) -> list[dict]:
    """Localiza los equipos en la respuesta de `my-teams`, sea cual sea su anidamiento.

    Se aceptan objetos con `teamUuid`, o con `uuid` + algún campo de nombre/categoría.
    """
    found: dict[str, dict] = {}
    for obj in _walk(data):
        uuid = obj.get("teamUuid") or (obj.get("uuid") if _looks_like_team(obj) else None)
        if isinstance(uuid, str) and uuid and uuid not in found:
            found[uuid] = {"uuid": uuid,
                           "nombre": obj.get("teamName") or obj.get("name") or obj.get("nombre"),
                           "categoria": _name(obj.get("category") or obj.get("categoryName")),
                           "competicion": _name(obj.get("competition") or obj.get("competitionName"))}
    return list(found.values())


def _looks_like_team(obj: dict) -> bool:
    keys = {k.lower() for k in obj}
    return bool(keys & {"teamname", "category", "categoryname", "competition", "gender"}) \
        and bool(keys & {"name", "teamname"})


def _name(v: Any) -> Any:
    return v.get("name") if isinstance(v, dict) else v


def _walk(data: Any) -> Iterable[dict]:
    if isinstance(data, dict):
        yield data
        for v in data.values():
            yield from _walk(v)
    elif isinstance(data, list):
        for v in data:
            yield from _walk(v)


def team_name(stats: dict) -> str | None:
    h = stats.get("header") or {}
    t = h.get("team") if isinstance(h.get("team"), dict) else h
    return t.get("name") if isinstance(t, dict) else None


def describe(data: Any, depth: int = 0, max_depth: int = 4) -> Any:
    """Esqueleto de una respuesta JSON: claves y tipos (listas: primer elemento y longitud)."""
    if depth >= max_depth:
        return type(data).__name__
    if isinstance(data, dict):
        return {k: describe(v, depth + 1, max_depth) for k, v in list(data.items())[:60]}
    if isinstance(data, list):
        return [f"lista[{len(data)}]", describe(data[0], depth + 1, max_depth)] if data else "lista[0]"
    return type(data).__name__


def _safe(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except ApiError as exc:
        return {"_error": str(exc)}
