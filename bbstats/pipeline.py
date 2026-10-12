"""Orquestación: extracción -> almacén bruto -> normalización -> métricas -> salida unificada.

Sólo se descarga cuando se llama a `ejecutar()`; no hay ninguna tarea programada.
"""
from __future__ import annotations

import json
import logging
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from . import __version__
from .adapters import AdapterError, ParsedLeague, build_adapter
from .config import active_leagues, load_config, resolve_path
from .http import HttpClient
from .metrics import compute_player_metrics, finalize_columns
from .raw_store import RawStore
from .schema import COLUMN_NAMES, dictionary_records
from .utils import utc_now, utc_stamp

log = logging.getLogger(__name__)
Progress = Callable[[str], None]


@dataclass
class LeagueResult:
    liga: str
    estado: str = "pendiente"  # ok | ok_bruto_anterior | sin_datos | error
    jugadores: int = 0
    equipos: int = 0
    archivo_bruto: str | None = None
    fecha_extraccion: str | None = None
    archivo_salida: str | None = None
    columnas_con_datos: int = 0
    columnas_vacias: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    notas: list[str] = field(default_factory=list)
    duracion_s: float = 0.0


# ---------------------------------------------------------------------------------------------
def build_league_frame(parsed: ParsedLeague, liga: str, lcfg: dict, season: str,
                       meta: dict, raw_path: str | None) -> pd.DataFrame:
    players = pd.DataFrame(parsed.players)
    if players.empty:
        return finalize_columns(pd.DataFrame(columns=COLUMN_NAMES))
    for k in ("player_id", "team_id"):
        players[k] = players.get(k, pd.Series(index=players.index, dtype=object)).astype(str)
    teams = pd.DataFrame(parsed.teams)
    game_min = float(lcfg.get("minutos_partido", 40))
    df = compute_player_metrics(players, teams, game_min)
    df = df.assign(
        liga=liga, liga_nombre=lcfg.get("nombre", liga), pais=lcfg.get("pais"), temporada=season,
        fase=lcfg.get("fase", "todas"), fuente=lcfg.get("fuente") or lcfg.get("base_url"),
        fecha_extraccion=meta.get("fecha_extraccion"), archivo_bruto=raw_path,
        player_uid=liga + ":" + df["player_id"].astype(str), minutos_partido=game_min)
    # equipo: rellenar nombre desde la tabla de equipos si el jugador no lo trae
    if "equipo" in teams.columns and len(teams):
        names = teams.assign(team_id=teams["team_id"].astype(str)).set_index("team_id")["equipo"]
        df["equipo"] = df.get("equipo", pd.Series(index=df.index, dtype=object)).fillna(df["team_id"].map(names))
    df = finalize_columns(df)
    return df.sort_values(["min", "pts"], ascending=False, na_position="last").reset_index(drop=True)


def _write_frame(df: pd.DataFrame, path_noext: Path) -> None:
    path_noext.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path_noext.with_suffix(".csv"), index=False, encoding="utf-8")
    df.replace({np.nan: None}).to_json(path_noext.with_suffix(".json"), orient="records",
                                        force_ascii=False, indent=None)


def _completeness(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(0.0, index=COLUMN_NAMES)
    return (df.notna().mean() * 100).round(1)


# ---------------------------------------------------------------------------------------------
def _run_league(liga: str, cfg: dict, season: str, download: bool, store: RawStore,
                out_dir: Path, progress: Progress, http_factory: Callable[[], HttpClient]) -> tuple[LeagueResult, pd.DataFrame | None]:
    t0 = time.monotonic()
    res = LeagueResult(liga=liga)
    lcfg = cfg["ligas"][liga]
    adapter = build_adapter(liga, lcfg)
    payload: Any = None
    meta: dict = {}
    raw_path: Path | None = None
    try:
        if download:
            prev_path = store.latest(liga, season)
            prev_payload = RawStore.load(prev_path)["payload"] if prev_path else None
            http = http_factory()
            progress(f"[{liga}] descargando...")
            now = utc_now()
            try:
                payload = adapter.fetch(season, http, prev_payload)
                meta = {"liga": liga, "temporada": season, "adaptador": adapter.name,
                        "version_adaptador": adapter.version, "version_bbstats": __version__,
                        "fuente": adapter.source_url, "fecha_extraccion": now.isoformat(),
                        "fecha_extraccion_stamp": utc_stamp(now), "peticiones": http.request_log(),
                        "errores": adapter.errors}
                raw_path = store.save(liga, season, meta, payload)
                res.estado = "ok"
                progress(f"[{liga}] bruto guardado en {raw_path}")
            except Exception as exc:  # noqa: BLE001 - se informa y se intenta con el último bruto
                if prev_path is None:
                    raise
                res.errores.append(f"Descarga fallida: {exc}")
                progress(f"[{liga}] descarga fallida; se reprocesa el último bruto disponible")
                raw_path, payload = prev_path, prev_payload
                meta = RawStore.load(prev_path)["meta"]
                res.estado = "ok_bruto_anterior"
            res.errores.extend(adapter.errors)
        else:
            raw_path = store.latest(liga, season)
            if raw_path is None:
                raise AdapterError(f"No hay JSON bruto para {liga} {season}: ejecuta primero con descarga")
            doc = RawStore.load(raw_path)
            payload, meta = doc["payload"], doc["meta"]
            res.estado = "ok"
        progress(f"[{liga}] procesando {raw_path.name}")
        parsed = adapter.parse(payload, season)
        res.notas.extend(parsed.notes)
        df = build_league_frame(parsed, liga, lcfg, season, meta, str(raw_path))
        res.jugadores, res.equipos = len(df), len(parsed.teams)
        res.archivo_bruto, res.fecha_extraccion = str(raw_path), meta.get("fecha_extraccion")
        if df.empty:
            res.estado = "sin_datos"
        out = out_dir / "ligas" / liga
        _write_frame(df, out)
        res.archivo_salida = str(out.with_suffix(".csv"))
        comp = _completeness(df)
        res.columnas_con_datos = int((comp > 0).sum())
        res.columnas_vacias = [c for c in COLUMN_NAMES if comp.get(c, 0) == 0]
        progress(f"[{liga}] {res.jugadores} jugadores, {res.columnas_con_datos}/{len(COLUMN_NAMES)} columnas con datos")
        return res, df
    except Exception as exc:  # noqa: BLE001 - una liga caída no detiene al resto
        res.estado = "error"
        res.errores.append(f"{type(exc).__name__}: {exc}")
        res.errores.extend(e for e in adapter.errors if e not in res.errores)
        log.debug(traceback.format_exc())
        progress(f"[{liga}] ERROR: {exc}")
        return res, None
    finally:
        res.duracion_s = round(time.monotonic() - t0, 2)


def run(ligas: list[str] | None = None, temporada: str | None = None, descargar: bool = True,
        config: dict | str | None = None, paralelo: bool = True, progreso: Progress | None = None,
        http_factory: Callable[[], HttpClient] | None = None) -> dict:
    cfg = config if isinstance(config, dict) else load_config(config)
    season = temporada or cfg.get("temporada_por_defecto", "2025-26")
    leagues = ligas or active_leagues(cfg)
    unknown = [l for l in leagues if l not in cfg["ligas"]]
    if unknown:
        raise ValueError(f"Ligas desconocidas: {unknown}. Disponibles: {list(cfg['ligas'])}")
    progress = progreso or (lambda m: log.info(m))
    hcfg = cfg.get("http", {})
    http_factory = http_factory or (lambda: HttpClient(delay_s=hcfg.get("delay_s", 1.0),
                                                       timeout_s=hcfg.get("timeout_s", 30),
                                                       retries=hcfg.get("retries", 3)))
    store = RawStore(resolve_path(cfg, "bruto"), compress=cfg.get("comprimir_bruto", False))
    out_dir = resolve_path(cfg, "procesado") / season
    started = utc_now()

    def one(l):
        return _run_league(l, cfg, season, descargar, store, out_dir, progress, http_factory)

    if paralelo and len(leagues) > 1:
        with ThreadPoolExecutor(max_workers=min(8, len(leagues))) as ex:
            results = list(ex.map(one, leagues))
    else:
        results = [one(l) for l in leagues]

    combined_path = write_combined(out_dir)
    report = {
        "version": __version__,
        "temporada": season,
        "modo": "ejecutar" if descargar else "reprocesar",
        "inicio": started.isoformat(),
        "fin": utc_now().isoformat(),
        "salida_combinada": str(combined_path) if combined_path else None,
        "ligas": [asdict(r) for r, _ in results],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "informe_ejecucion.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    hist = out_dir / "informes"
    hist.mkdir(exist_ok=True)
    (hist / f"informe_{utc_stamp(started)}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                             encoding="utf-8")
    return report


def write_combined(out_dir: Path) -> Path | None:
    """Une el último procesado de TODAS las ligas de la temporada (aunque hoy alguna falle)."""
    files = sorted((out_dir / "ligas").glob("*.csv")) if (out_dir / "ligas").exists() else []
    out_dir.mkdir(parents=True, exist_ok=True)
    dict_df = pd.DataFrame(dictionary_records())
    dict_df.to_csv(out_dir / "diccionario_columnas.csv", index=False, encoding="utf-8")
    (out_dir / "diccionario_columnas.json").write_text(json.dumps(dictionary_records(), ensure_ascii=False, indent=1),
                                                       encoding="utf-8")
    if not files:
        return None
    frames = [pd.read_csv(f, dtype={"player_id": str, "team_id": str, "dorsal": str}, low_memory=False)
              for f in files]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return None
    df = finalize_columns(pd.concat(frames, ignore_index=True))
    _write_frame(df, out_dir / "todas_las_ligas")
    comp = pd.DataFrame({liga: _completeness(g) for liga, g in df.groupby("liga")})
    comp.index.name = "columna"
    comp.to_csv(out_dir / "completitud.csv", encoding="utf-8")
    return out_dir / "todas_las_ligas.csv"
