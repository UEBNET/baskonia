"""API pública pensada para conectarse a un botón "EJECUTAR".

Todas las funciones devuelven estructuras JSON-serializables (dict / list), de modo que se
pueden exponer tal cual por HTTP (ver bbstats/server.py) o llamar desde otro código Python.
"""
from __future__ import annotations

import json
from typing import Callable

import pandas as pd

from .config import active_leagues, configured_seasons, load_config, resolve_path, season_range
from .raw_store import RawStore
from .schema import dictionary_records


def ejecutar(ligas: list[str] | None = None, temporada: str | None = None,
             config: dict | str | None = None, paralelo: bool = True,
             progreso: Callable[[str], None] | None = None) -> dict:
    """ACCIÓN PRINCIPAL del botón EJECUTAR: descarga los datos actuales de cada liga, guarda el
    JSON bruto con fecha, normaliza, calcula métricas y escribe la salida unificada.
    Si la descarga de una liga falla, se reprocesa su último bruto y se indica en el informe."""
    from .pipeline import run
    return run(ligas=ligas, temporada=temporada, descargar=True, config=config,
               paralelo=paralelo, progreso=progreso)


def ejecutar_temporadas(temporadas: list[str] | None = None, desde: str | None = None, hasta: str | None = None,
                        ligas: list[str] | None = None, config: dict | str | None = None, paralelo: bool = True,
                        progreso: Callable[[str], None] | None = None, descargar: bool = True) -> dict:
    """Descarga (o reprocesa, con descargar=False) varias temporadas: la lista `temporadas` o el rango
    `desde`..`hasta`. Sin argumentos: de `temporada_inicial` a `temporada_por_defecto` de la config.
    Es la carga histórica inicial; el botón EJECUTAR actualiza después una sola temporada."""
    from .pipeline import run_seasons
    cfg = config if isinstance(config, dict) else load_config(config)
    if not temporadas:
        if desde or hasta:
            temporadas = season_range(desde or cfg.get("temporada_inicial", hasta),
                                      hasta or cfg.get("temporada_por_defecto"))
        else:
            temporadas = configured_seasons(cfg)
    return run_seasons(temporadas, ligas=ligas, descargar=descargar, config=cfg, paralelo=paralelo,
                       progreso=progreso)


def quintetos(temporadas: list[str] | None = None, ligas: list[str] | None = None, descargar: bool = True,
              config: dict | str | None = None, progreso: Callable[[str], None] | None = None) -> dict:
    """Sólo la capa de quintetos y conexiones (jugada a jugada) para las temporadas y ligas indicadas.
    Las ejecuciones normales (ejecutar, historico, botón EJECUTAR) ya la incluyen siempre."""
    from .config import active_leagues
    from .http import HttpClient
    from .lineups.run import run_league
    cfg = config if isinstance(config, dict) else load_config(config)
    temporadas = temporadas or [cfg.get("temporada_por_defecto")]
    ligas = ligas or [l for l in active_leagues(cfg) if cfg["ligas"][l].get("pbp")]
    hcfg = cfg.get("http", {})
    factory = lambda: HttpClient(delay_s=hcfg.get("delay_s", 1.0), timeout_s=hcfg.get("timeout_s", 30),  # noqa: E731
                                 retries=hcfg.get("retries", 3), domain_delays=hcfg.get("delay_por_dominio", {}),
                                 curl_domains=tuple(hcfg.get("dominios_curl", [])))
    store = RawStore(resolve_path(cfg, "bruto"), compress=cfg.get("comprimir_bruto", False))
    progress = progreso or print
    out = {}
    for t in temporadas:
        for l in ligas:
            out[f"{l}/{t}"] = run_league(l, cfg, t, descargar, store, resolve_path(cfg, "procesado") / t, progress,
                                         factory)
    return out


def reprocesar(ligas: list[str] | None = None, temporada: str | None = None,
               config: dict | str | None = None, progreso: Callable[[str], None] | None = None) -> dict:
    """Recalcula toda la salida a partir del último JSON bruto de cada liga, sin red.
    Útil tras cambiar fórmulas, el esquema o el parser."""
    from .pipeline import run
    return run(ligas=ligas, temporada=temporada, descargar=False, config=config,
               paralelo=False, progreso=progreso)


def estado(temporada: str | None = None, config: dict | str | None = None) -> dict:
    """Estado actual: ligas configuradas, último bruto de cada una y último informe."""
    cfg = config if isinstance(config, dict) else load_config(config)
    season = temporada or cfg.get("temporada_por_defecto")
    store = RawStore(resolve_path(cfg, "bruto"))
    ligas = {}
    for liga, lcfg in cfg["ligas"].items():
        files = store.list(liga, season)
        ligas[liga] = {"nombre": lcfg.get("nombre"), "activa": lcfg.get("activa", True),
                       "adaptador": lcfg.get("adaptador"),
                       "estado_verificacion": lcfg.get("estado_verificacion"),
                       "brutos": len(files), "ultimo_bruto": str(files[-1]) if files else None}
    report_path = resolve_path(cfg, "procesado") / season / "informe_ejecucion.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else None
    return {"temporada": season, "ligas_activas": active_leagues(cfg), "ligas": ligas,
            "ultimo_informe": report}


def datos(liga: str | None = None, temporada: str | None = None, fase: str | None = None,
          config: dict | str | None = None) -> list[dict]:
    """Filas procesadas (todas las ligas o una; todas las fases o una) como lista de diccionarios."""
    df = dataframe(liga, temporada, config)
    if fase and not df.empty:
        df = df[df["fase"] == fase]
    return df.astype(object).where(df.notna(), None).to_dict("records")


def diccionario() -> list[dict]:
    """Diccionario de columnas (nombre, grupo, origen, descripción)."""
    return dictionary_records()


def dataframe(liga: str | None = None, temporada: str | None = None,
              config: dict | str | None = None) -> pd.DataFrame:
    """Datos procesados como pandas.DataFrame (para tus algoritmos)."""
    cfg = config if isinstance(config, dict) else load_config(config)
    season = temporada or cfg.get("temporada_por_defecto")
    base = resolve_path(cfg, "procesado") / season
    if not liga:
        from .pipeline import read_season
        return read_season(base)
    path = base / "ligas" / f"{liga}.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False, dtype={"player_id": str, "team_id": str, "dorsal": str,
                                                      "bn_player_id": str})
