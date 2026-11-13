"""Orquestación de la capa ESF: descarga → bruto con fecha → construcción → salida unificada.

Sólo se descarga cuando se llama a `ejecutar()` (botón EJECUTAR: `python ejecutar_basko.py`). `reprocesar()`
regenera toda la salida desde los brutos, sin red (p.ej. tras cambiar una fórmula).
"""
from __future__ import annotations

import json
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from .. import __version__ as bbstats_version
from ..adapters.base import NoDataYet
from ..http import HttpClient
from ..raw_store import RawStore
from ..utils import utc_now, utc_stamp
from . import __version__
from .extractor import EsfAdapter

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "basko.json"
Progress = Callable[[str], None]


def load_config(path: str | Path | None = None) -> dict:
    return json.loads(Path(path or CONFIG).read_text(encoding="utf-8"))


def ruta(cfg: dict, clave: str) -> Path:
    p = Path(cfg["rutas"][clave])
    return p if p.is_absolute() else ROOT / p


def temporadas(cfg: dict, desde: str | None = None, hasta: str | None = None) -> list[str]:
    a = int((desde or cfg["temporada_inicial"])[:4])
    b = int((hasta or cfg["temporada_por_defecto"])[:4])
    return [f"{y}-{str(y + 1)[2:]}" for y in range(a, b + 1)]


def ligas_activas(cfg: dict) -> list[str]:
    return [k for k, v in cfg["ligas"].items() if v.get("activa", True)]


@dataclass
class Resultado:
    liga: str
    temporada: str
    estado: str = "pendiente"      # ok | ok_bruto_anterior | sin_datos | error
    partidos_calendario: int = 0
    partidos_con_acta: int = 0
    partidos_nuevos: int = 0
    filas_jugadores: int = 0
    fases: list = field(default_factory=list)
    archivo_bruto: str | None = None
    errores: list = field(default_factory=list)
    notas: list = field(default_factory=list)
    duracion_s: float = 0.0


def _http(cfg: dict) -> HttpClient:
    h = cfg.get("http", {})
    return HttpClient(delay_s=h.get("delay_s", 0.25), timeout_s=h.get("timeout_s", 60), retries=h.get("retries", 4),
                      domain_delays=h.get("delay_por_dominio", {}))


def _una(liga: str, season: str, cfg: dict, descargar: bool, procesar: bool, store: RawStore,
         progress: Progress) -> Resultado:
    t0 = time.monotonic()
    res = Resultado(liga=liga, temporada=season)
    lcfg = cfg["ligas"][liga]
    ad = EsfAdapter(liga, lcfg, cfg)
    ad.store = store
    try:
        if descargar:
            prev_path, prev_doc = store.load_season(liga, season)
            http = _http(cfg)
            now = utc_now()
            try:
                payload = ad.fetch(season, http, prev_doc["payload"] if prev_doc else None, progress)
                meta = {"liga": liga, "temporada": season, "adaptador": ad.name, "version_adaptador": ad.version,
                        "version_esf": __version__, "version_bbstats": bbstats_version, "fuente": ad.source_url,
                        "fecha_extraccion": now.isoformat(), "fecha_extraccion_stamp": utc_stamp(now),
                        "peticiones": len(http.request_log()), "errores": ad.errors}
                res.partidos_nuevos = payload.get("partidos_nuevos", 0)
                if not payload["games"] and not payload["equipos"] and prev_path is not None and not res.partidos_nuevos:
                    res.notas.append("sin partidos nuevos: se reutiliza el bruto anterior")
                    res.archivo_bruto = str(prev_path)
                else:
                    res.archivo_bruto = str(store.save(liga, season, meta, payload))
                res.estado = "ok"
            except NoDataYet:
                raise
            except Exception as exc:  # noqa: BLE001
                if prev_path is None:
                    raise
                res.errores.append(f"Descarga fallida, se usa el último bruto: {exc}")
                res.estado = "ok_bruto_anterior"
            res.errores.extend(ad.errors)
            progress(f"[{liga} {season}] bruto: {res.archivo_bruto}")
        if procesar:
            path, doc = store.load_season(liga, season)
            if path is None:
                raise NoDataYet(f"no hay bruto de {liga} {season}")
            from .construir import construir_liga, escribir_liga
            tablas = construir_liga(liga, lcfg, cfg, season, doc["payload"], doc.get("meta") or {}, str(path))
            info = escribir_liga(tablas, ruta(cfg, "procesado") / season, liga, cfg)
            res.archivo_bruto = res.archivo_bruto or str(path)
            res.partidos_calendario = info["partidos_calendario"]
            res.partidos_con_acta = info["partidos_con_acta"]
            res.filas_jugadores = info["filas_jugadores"]
            res.fases = info["fases"]
            res.notas.extend(info.get("notas", []))
            if res.estado == "pendiente":
                res.estado = "ok"
            progress(f"[{liga} {season}] {res.partidos_con_acta}/{res.partidos_calendario} partidos con acta, "
                     f"{res.filas_jugadores} filas jugador-equipo-fase")
    except NoDataYet as exc:
        res.estado = "sin_datos"
        res.notas.append(str(exc))
        progress(f"[{liga} {season}] sin datos: {exc}")
    except Exception as exc:  # noqa: BLE001 - una liga caída no detiene al resto
        res.estado = "error"
        res.errores.append(f"{type(exc).__name__}: {exc}")
        res.notas.append(traceback.format_exc()[-1500:])
        progress(f"[{liga} {season}] ERROR {type(exc).__name__}: {exc}")
    res.duracion_s = round(time.monotonic() - t0, 1)
    return res


def run(ligas: list[str] | None = None, temporadas_: list[str] | None = None, descargar: bool = True,
        procesar: bool = True, config: dict | None = None, paralelo: bool = True,
        progreso: Progress | None = None) -> dict:
    cfg = config or load_config()
    progress = progreso or print
    ligas = ligas or ligas_activas(cfg)
    unknown = [l for l in ligas if l not in cfg["ligas"]]
    if unknown:
        raise ValueError(f"Ligas desconocidas: {unknown}. Disponibles: {list(cfg['ligas'])}")
    seasons = temporadas_ or [cfg["temporada_por_defecto"]]
    store = RawStore(ruta(cfg, "bruto"), compress=True)
    started = utc_now()
    resultados: list[Resultado] = []
    for season in seasons:
        def one(l, s=season):
            return _una(l, s, cfg, descargar, procesar, store, progress)
        if paralelo and len(ligas) > 1:
            with ThreadPoolExecutor(max_workers=min(6, len(ligas))) as ex:
                rs = list(ex.map(one, ligas))
        else:
            rs = [one(l) for l in ligas]
        resultados.extend(rs)
        if procesar:
            from .construir import escribir_indice_temporada
            escribir_indice_temporada(ruta(cfg, "procesado") / season, season, cfg, [asdict(r) for r in rs])
    if procesar:
        from .construir import escribir_indice_global
        escribir_indice_global(ruta(cfg, "procesado"), cfg)
    informe = {"version": __version__, "modo": "ejecutar" if descargar else "reprocesar",
               "inicio": started.isoformat(), "fin": utc_now().isoformat(),
               "resultados": [asdict(r) for r in resultados]}
    out = ruta(cfg, "procesado")
    out.mkdir(parents=True, exist_ok=True)
    (out / "informe_ultima_ejecucion.json").write_text(json.dumps(informe, ensure_ascii=False, indent=1),
                                                       encoding="utf-8")
    return informe


def ejecutar(ligas=None, temporada=None, **kw) -> dict:
    """Botón EJECUTAR: descarga lo nuevo de la temporada (por defecto la actual) y regenera su salida."""
    return run(ligas, [temporada] if temporada else None, descargar=True, procesar=True, **kw)


def reprocesar(ligas=None, temporadas_=None, **kw) -> dict:
    """Regenera la salida desde los brutos guardados, sin red."""
    cfg = kw.pop("config", None) or load_config()
    return run(ligas, temporadas_ or temporadas(cfg), descargar=False, procesar=True, config=cfg, **kw)
