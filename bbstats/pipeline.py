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
from .adapters import NoDataYet, ParsedLeague, build_adapter
from .enrich import basketnews
from .config import active_leagues, load_config, resolve_path
from .http import HttpClient
from .metrics import compute_player_metrics, finalize_columns
from .raw_store import RawStore
from .phases import PHASES, ensure_phases
from .schema import COLUMN_NAMES, PHASE_CONTEXT_METRICS, dictionary_records
from .utils import utc_now, utc_stamp

log = logging.getLogger(__name__)
Progress = Callable[[str], None]


@dataclass
class LeagueResult:
    liga: str
    estado: str = "pendiente"  # ok | ok_bruto_anterior | sin_datos | error
    jugadores: int = 0
    equipos: int = 0
    filas_por_fase: dict = field(default_factory=dict)
    archivo_bruto: str | None = None
    fecha_extraccion: str | None = None
    archivo_salida: str | None = None
    columnas_con_datos: int = 0
    columnas_vacias: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    notas: list[str] = field(default_factory=list)
    duracion_s: float = 0.0


# ---------------------------------------------------------------------------------------------
def _phase_frame(parsed: ParsedLeague, phase: str, liga: str, lcfg: dict, season: str,
                 meta: dict, raw_path: str | None) -> pd.DataFrame:
    players = pd.DataFrame(parsed.players)
    if players.empty:
        return pd.DataFrame(columns=COLUMN_NAMES)
    for k in ("player_id", "team_id"):
        players[k] = players.get(k, pd.Series(index=players.index, dtype=object)).astype(str)
    teams = pd.DataFrame(parsed.teams)
    game_min = float(lcfg.get("minutos_partido", 40))
    df = compute_player_metrics(players, teams, game_min, single_ft=bool(lcfg.get("tiro_libre_unico")),
                                coef_tl=float(lcfg.get("coef_tl_posesion", 0.4)))
    df = df.assign(
        liga=liga, liga_nombre=lcfg.get("nombre", liga), pais=lcfg.get("pais"), temporada=season,
        fase=phase, fuente=lcfg.get("fuente") or lcfg.get("base_url"),
        fecha_extraccion=meta.get("fecha_extraccion"), archivo_bruto=raw_path,
        player_uid=liga + ":" + df["player_id"].astype(str), minutos_partido=game_min)
    if "equipo" in teams.columns and len(teams):
        names = teams.assign(team_id=teams["team_id"].astype(str)).drop_duplicates("team_id").set_index("team_id")["equipo"]
        df["equipo"] = df.get("equipo", pd.Series(index=df.index, dtype=object)).fillna(df["team_id"].map(names))
    return df


def add_phase_context(df: pd.DataFrame) -> pd.DataFrame:
    """En las filas de playoffs añade el valor de temporada regular (rs_*) y la diferencia (delta_*)."""
    reg = df[df["fase"] == "regular"].drop_duplicates(["player_id", "team_id"]).set_index(["player_id", "team_id"])
    po_mask = df["fase"] == "playoffs"
    if reg.empty or not po_mask.any():
        return df
    keys = pd.MultiIndex.from_frame(df.loc[po_mask, ["player_id", "team_id"]])
    new = {}
    for m in PHASE_CONTEXT_METRICS:
        if m not in df.columns:
            continue
        rs_vals = pd.to_numeric(reg[m], errors="coerce").reindex(keys).to_numpy()
        rs_col = pd.Series(np.nan, index=df.index)
        rs_col.loc[po_mask] = rs_vals
        new[f"rs_{m}"] = rs_col
        if m != "gp":
            new[f"delta_{m}"] = pd.to_numeric(df[m], errors="coerce").where(po_mask) - rs_col
    return pd.concat([df.drop(columns=[c for c in new if c in df.columns]), pd.DataFrame(new, index=df.index)], axis=1)


def build_league_frame(parsed_by_phase: dict | ParsedLeague, liga: str, lcfg: dict, season: str,
                       meta: dict, raw_path: str | None, enrich: dict | None = None,
                       notes: list[str] | None = None) -> pd.DataFrame:
    notes = notes if notes is not None else []
    if isinstance(parsed_by_phase, ParsedLeague):
        parsed_by_phase = {"total": parsed_by_phase}
    parsed_by_phase = ensure_phases(parsed_by_phase)
    frames = []
    for phase in PHASES:
        parsed = parsed_by_phase.get(phase)
        if parsed is None:
            continue
        notes.extend(f"[{phase}] {n}" for n in parsed.notes)
        df = _phase_frame(parsed, phase, liga, lcfg, season, meta, raw_path)
        if df.empty:
            continue
        if (enrich or {}).get("basketnews"):
            df = basketnews.apply(df, enrich["basketnews"], phase, notes)
        frames.append(df)
    if not frames:
        return finalize_columns(pd.DataFrame(columns=COLUMN_NAMES))
    df = pd.concat(frames, ignore_index=True)
    df = add_phase_context(df)
    df = finalize_columns(df)
    order = {p: i for i, p in enumerate(PHASES)}
    df["_o"] = df["fase"].map(order)
    df = df.sort_values(["_o", "min", "pts"], ascending=[True, False, False], na_position="last")
    return df.drop(columns="_o").reset_index(drop=True)


def _write_frame(df: pd.DataFrame, path_noext: Path, csv: bool = True, json_: bool = True) -> None:
    """CSV (todas las columnas) y/o JSON columnar compacto: {"columnas": [...], "filas": [[...], ...]}.

    El JSON no repite los nombres de columna en cada fila y redondea a 4 decimales (mismo
    contenido, ~10 veces menos espacio): adecuado para cargarlo en un Artifact / web."""
    path_noext.parent.mkdir(parents=True, exist_ok=True)
    if csv:
        df.to_csv(path_noext.with_suffix(".csv"), index=False, encoding="utf-8", float_format="%.10g")
    if json_:
        write_columnar_json(df, path_noext.with_suffix(".json"))


def write_columnar_json(df: pd.DataFrame, path: Path) -> None:
    num = df.select_dtypes(include="number").columns
    out = df.copy()
    out[num] = out[num].round(4)
    rows = out.astype(object).where(out.notna(), None).values.tolist()
    rows = [[int(v) if isinstance(v, float) and v.is_integer() else v for v in r] for r in rows]
    path.write_text(json.dumps({"columnas": list(df.columns), "filas": rows}, ensure_ascii=False,
                               separators=(",", ":")), encoding="utf-8")


def read_columnar_json(path: Path) -> list[dict]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    cols = doc["columnas"]
    return [dict(zip(cols, r)) for r in doc["filas"]]


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
                bn_id = lcfg.get("basketnews_league_id")
                if bn_id and isinstance(payload, dict):
                    progress(f"[{liga}] enriqueciendo con BasketNews...")
                    payload["_enriquecimiento"] = {"basketnews": basketnews.fetch(
                        http, int(bn_id), int(season[:4]), adapter.errors)}
                meta = {"liga": liga, "temporada": season, "adaptador": adapter.name,
                        "version_adaptador": adapter.version, "version_bbstats": __version__,
                        "fuente": adapter.source_url, "fecha_extraccion": now.isoformat(),
                        "fecha_extraccion_stamp": utc_stamp(now), "peticiones": http.request_log(),
                        "errores": adapter.errors}
                raw_path = store.save(liga, season, meta, payload)
                res.estado = "ok"
                progress(f"[{liga}] bruto guardado en {raw_path}")
            except NoDataYet:
                raise
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
                raise NoDataYet(f"No hay JSON bruto para {liga} {season} (ejecuta primero con descarga)")
            doc = RawStore.load(raw_path)
            payload, meta = doc["payload"], doc["meta"]
            res.estado = "ok"
        progress(f"[{liga}] procesando {raw_path.name}")
        parsed = adapter.parse(payload, season)
        df = build_league_frame(parsed, liga, lcfg, season, meta, str(raw_path),
                                enrich=(payload or {}).get("_enriquecimiento") if isinstance(payload, dict) else None,
                                notes=res.notas)
        res.jugadores = int((df["fase"] == "total").sum()) if not df.empty else 0
        res.filas_por_fase = df["fase"].value_counts().to_dict() if not df.empty else {}
        res.equipos = int(df.loc[df["fase"] == "total", "team_id"].nunique()) if not df.empty else 0
        res.archivo_bruto, res.fecha_extraccion = str(raw_path), meta.get("fecha_extraccion")
        if df.empty:
            res.estado = "sin_datos"
        out = out_dir / "ligas" / liga
        _write_frame(df, out, json_=False)
        res.archivo_salida = str(out.with_suffix(".csv"))
        comp = _completeness(df)
        res.columnas_con_datos = int((comp > 0).sum())
        res.columnas_vacias = [c for c in COLUMN_NAMES if comp.get(c, 0) == 0]
        progress(f"[{liga}] {res.jugadores} jugadores, {res.columnas_con_datos}/{len(COLUMN_NAMES)} columnas con datos")
        return res, df
    except NoDataYet as exc:
        res.estado = "sin_datos"
        res.notas.append(str(exc))
        progress(f"[{liga}] sin datos todavía: {exc}")
        return res, None
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
                                                       retries=hcfg.get("retries", 3),
                                                       domain_delays=hcfg.get("delay_por_dominio", {}),
                                                       curl_domains=tuple(hcfg.get("dominios_curl", []))))
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

    combined_path = write_combined(out_dir, season)
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


def write_combined(out_dir: Path, season: str | None = None) -> Path | None:
    """Une el último procesado de TODAS las ligas de la temporada (aunque hoy alguna falle) y
    escribe también un fichero por fase (para un selector regular / playoffs / total)."""
    files = sorted((out_dir / "ligas").glob("*.csv")) if (out_dir / "ligas").exists() else []
    out_dir.mkdir(parents=True, exist_ok=True)
    dict_df = pd.DataFrame(dictionary_records())
    dict_df.to_csv(out_dir / "diccionario_columnas.csv", index=False, encoding="utf-8")
    (out_dir / "diccionario_columnas.json").write_text(json.dumps(dictionary_records(), ensure_ascii=False, indent=1),
                                                       encoding="utf-8")
    if not files:
        return None
    frames = [pd.read_csv(f, dtype={"player_id": str, "team_id": str, "dorsal": str, "bn_player_id": str},
                          low_memory=False) for f in files]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return None
    df = finalize_columns(pd.concat(frames, ignore_index=True))
    _write_frame(df, out_dir / "todas_las_ligas")
    index = {"temporada": season or (df["temporada"].iloc[0] if len(df) else None),
             "generado": utc_now().isoformat(), "fases": PHASES, "ligas": {},
             "formato_json": "columnar: {columnas: [...], filas: [[...]]}",
             "archivos": {"todas": "todas_las_ligas.json", "diccionario": "diccionario_columnas.json"}}
    for phase in PHASES:
        sub = df[df["fase"] == phase]
        if len(sub):
            _write_frame(sub, out_dir / "por_fase" / phase, csv=False)
            index["archivos"][phase] = f"por_fase/{phase}.json"
    for (liga, phase), g in df.groupby(["liga", "fase"]):
        entry = index["ligas"].setdefault(liga, {"nombre": g["liga_nombre"].iloc[0], "archivo": f"ligas/{liga}.csv",
                                                 "fecha_extraccion": g["fecha_extraccion"].iloc[0], "fases": {}})
        entry["fases"][phase] = int(len(g))
    (out_dir / "indice.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    comp = pd.DataFrame({f"{liga}|{phase}": _completeness(g) for (liga, phase), g in df.groupby(["liga", "fase"])})
    comp.index.name = "columna"
    comp.to_csv(out_dir / "completitud.csv", encoding="utf-8")
    return out_dir / "todas_las_ligas.csv"
