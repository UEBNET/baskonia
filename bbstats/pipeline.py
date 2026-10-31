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
from .config import active_leagues, load_config, minutos_partido, resolve_path, update_league_config
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
    quintetos: dict = field(default_factory=dict)
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
    game_min = minutos_partido(lcfg, season)
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


def _write_frame(df: pd.DataFrame, path_noext: Path, csv: bool = True, json_: bool = False) -> None:
    """CSV (todas las columnas, números redondeados a 4 decimales) y, si se pide, JSON columnar
    compacto {"columnas": [...], "filas": [[...], ...]} (sólo para el Artifact, no se versiona)."""
    path_noext.parent.mkdir(parents=True, exist_ok=True)
    if csv:
        out = df.copy()
        num = out.select_dtypes(include="number").columns
        out[num] = out[num].round(4)
        out.to_csv(path_noext.with_suffix(".csv"), index=False, encoding="utf-8", float_format="%.10g")
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
    first = lcfg.get("temporada_inicial")
    if first and int(season[:4]) < int(str(first)[:4]):
        # temporada anterior a la primera de la liga (alcance decidido por el usuario): ni se descarga ni se procesa
        res.estado = "fuera_de_alcance"
        res.notas.append(f"{liga}: temporada {season} fuera de alcance (primera temporada de la liga: {first})")
        return res, None
    adapter = build_adapter(liga, lcfg)
    payload: Any = None
    meta: dict = {}
    raw_path: Path | None = None
    try:
        if download:
            prev_path, prev_doc = store.load_season(liga, season)
            prev_payload = prev_doc["payload"] if prev_doc else None
            http = http_factory()
            adapter.store = store   # adaptadores incrementales: guardan paquetes parciales durante la descarga
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
                if (isinstance(payload, dict) and payload.get("incremental") and not payload.get("games")
                        and prev_path is not None and not adapter.config_updates):
                    # bruto incremental sin partidos nuevos: no se guarda un paquete vacío
                    raw_path = prev_path
                    res.notas.append("sin partidos nuevos: se reutiliza el bruto anterior")
                else:
                    raw_path = store.save(liga, season, meta, payload)
                if isinstance(payload, dict) and payload.get("incremental"):
                    payload = store.load_season(liga, season)[1]["payload"]   # todos los paquetes
                res.estado = "ok"
                if adapter.config_updates:
                    saved = update_league_config(cfg, liga, adapter.config_updates)
                    res.notas.append(f"Config actualizada{' (sources.json)' if saved else ''}: "
                                     f"{json.dumps(adapter.config_updates, ensure_ascii=False)}")
                    progress(f"[{liga}] guardado en config: {adapter.config_updates}")
                progress(f"[{liga}] bruto guardado en {raw_path}")
            except NoDataYet:
                raise
            except Exception as exc:  # noqa: BLE001 - se informa y se intenta con el último bruto
                if prev_path is None:
                    raise
                res.errores.append(f"Descarga fallida: {exc}")
                progress(f"[{liga}] descarga fallida; se reprocesa el último bruto disponible")
                raw_path, payload = prev_path, prev_payload
                meta = prev_doc["meta"]
                res.estado = "ok_bruto_anterior"
            res.errores.extend(adapter.errors)
        else:
            raw_path, doc = store.load_season(liga, season)
            if raw_path is None:
                raise NoDataYet(f"No hay JSON bruto para {liga} {season} (ejecuta primero con descarga)")
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
        _write_frame(df, out)
        res.archivo_salida = str(out.with_suffix(".csv"))
        comp = _completeness(df)
        res.columnas_con_datos = int((comp > 0).sum())
        res.columnas_vacias = [c for c in COLUMN_NAMES if comp.get(c, 0) == 0]
        progress(f"[{liga}] {res.jugadores} jugadores, {res.columnas_con_datos}/{len(COLUMN_NAMES)} columnas con datos")
        res.quintetos = _run_lineups(liga, cfg, season, download, store, out_dir, progress, http_factory)
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


def _run_lineups(liga: str, cfg: dict, season: str, download: bool, store: RawStore, out_dir: Path,
                 progress: Progress, http_factory: Callable[[], HttpClient]) -> dict:
    """Capa de quintetos y conexiones (bbstats/lineups). Nunca hace fallar la liga: los errores se informan."""
    try:
        from .lineups.run import run_league
        return run_league(liga, cfg, season, download, store, out_dir, progress, http_factory)
    except Exception as exc:  # noqa: BLE001
        log.debug(traceback.format_exc())
        progress(f"[{liga}] quintetos: ERROR {type(exc).__name__}: {exc}")
        return {"estado": "error", "errores": [f"{type(exc).__name__}: {exc}"]}


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
    write_seasons_index(resolve_path(cfg, "procesado"))
    return report


def run_seasons(temporadas: list[str], ligas: list[str] | None = None, descargar: bool = True,
                config: dict | str | None = None, paralelo: bool = True, progreso: Progress | None = None,
                http_factory: Callable[[], HttpClient] | None = None) -> dict:
    """Ejecuta `run` para varias temporadas, una tras otra, compartiendo la misma config en memoria
    (así lo descubierto en una temporada, como las semillas de la BBL, sirve para la siguiente)."""
    cfg = config if isinstance(config, dict) else load_config(config)
    progress = progreso or (lambda m: log.info(m))
    reports = []
    for season in temporadas:
        progress(f"===== Temporada {season} =====")
        reports.append(run(ligas=ligas, temporada=season, descargar=descargar, config=cfg, paralelo=paralelo,
                           progreso=progress, http_factory=http_factory))
    return {"temporadas": temporadas, "informes": reports}


def write_seasons_index(processed_root: Path) -> Path:
    """data/processed/temporadas.json: temporadas con datos procesados (más reciente primero) y,
    por cada una, ligas, filas por fase y fecha de la última extracción. Lo usa el Artifact para
    construir el selector de temporada."""
    seasons = []
    for d in sorted((p for p in processed_root.glob("*-*") if p.is_dir()), reverse=True):
        idx_path = d / "indice.json"
        if not idx_path.exists():
            continue
        idx = json.loads(idx_path.read_text(encoding="utf-8"))
        seasons.append({"temporada": d.name, "generado": idx.get("generado"),
                        "fases": idx.get("fases_con_datos") or [f for f in PHASES if f in idx.get("archivos", {})],
                        "ligas": {k: v.get("fases", {}) for k, v in idx.get("ligas", {}).items()}})
    out = processed_root / "temporadas.json"
    processed_root.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"generado": utc_now().isoformat(), "temporadas": seasons}, ensure_ascii=False,
                              indent=2), encoding="utf-8")
    return out


def read_season(out_dir: Path) -> pd.DataFrame:
    """Todas las ligas de una temporada (une los CSV de data/processed/<temporada>/ligas/)."""
    files = sorted((out_dir / "ligas").glob("*.csv")) if (out_dir / "ligas").exists() else []
    frames = [pd.read_csv(f, dtype={"player_id": str, "team_id": str, "dorsal": str, "bn_player_id": str},
                          low_memory=False) for f in files]
    frames = [f for f in frames if not f.empty]
    return finalize_columns(pd.concat(frames, ignore_index=True)) if frames else pd.DataFrame()


def write_combined(out_dir: Path, season: str | None = None) -> Path | None:
    """Índice de la temporada (ligas, filas por fase, fecha de extracción), diccionario de columnas y
    completitud a partir del último CSV de cada liga (aunque hoy alguna falle). Los datos se guardan
    sólo como CSV, uno por liga: data/processed/<temporada>/ligas/<liga>.csv."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(dictionary_records()).to_csv(out_dir / "diccionario_columnas.csv", index=False, encoding="utf-8")
    df = read_season(out_dir)
    if df.empty:
        return None
    index = {"temporada": season or df["temporada"].iloc[0], "generado": utc_now().isoformat(),
             "fases": PHASES, "fases_con_datos": [f for f in PHASES if (df["fase"] == f).any()], "ligas": {},
             "formato": "CSV por liga (ligas/<liga>.csv), 1 fila = jugador-equipo-fase",
             "archivos": {"diccionario": "diccionario_columnas.csv", "completitud": "completitud.csv"}}
    for (liga, phase), g in df.groupby(["liga", "fase"]):
        entry = index["ligas"].setdefault(liga, {"nombre": g["liga_nombre"].iloc[0], "archivo": f"ligas/{liga}.csv",
                                                 "fecha_extraccion": g["fecha_extraccion"].iloc[0], "fases": {}})
        entry["fases"][phase] = int(len(g))
    (out_dir / "indice.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    comp = pd.DataFrame({f"{liga}|{phase}": _completeness(g) for (liga, phase), g in df.groupby(["liga", "fase"])})
    comp.index.name = "columna"
    comp.to_csv(out_dir / "completitud.csv", encoding="utf-8")
    return out_dir / "ligas"


# Columnas de pista (capa de quintetos) que se añaden a los JSON del Artifact: (columna, origen, descripción)
PISTA_ARTIFACT = [
    ("q_min_on", "min_on", "Minutos en pista según el jugada a jugada"),
    ("q_net_on", "net_rtg_on", "Net del equipo con él en pista (por 100 posesiones)"),
    ("q_net_off", "net_rtg_off", "Net del equipo con él en el banquillo"),
    ("q_onoff", "net_rtg_onoff", "On − Off del Net"),
    ("q_onoff_aj", "net_rtg_aj_onoff", "On − Off del Net ajustado por muestra"),
    ("q_onoff_suerte", "net_rtg_suerte_onoff", "On − Off del Net ajustado por suerte (triple y TL del rival a la media)"),
    ("q_onoff_sin_basura", "net_rtg_onoff_sin_basura", "On − Off del Net sin minutos de la basura"),
    ("q_rapm", "rapm", "RAPM: impacto en pista por 100 posesiones, aislado de compañeros y rivales (unidades de su liga)"),
    ("q_orapm", "orapm", "RAPM ofensivo"),
    ("q_drapm", "drapm", "RAPM defensivo (> 0 = mejor defensa)"),
    ("q_titular", "titular_partidos", "Partidos en el quinteto inicial"),
    ("q_cierra", "cierra_partidos", "Partidos en pista en el último tramo"),
    ("q_relevos_pp", "relevos_por_partido", "Entradas a pista por partido"),
    ("q_min_relevo", "min_por_relevo", "Minutos por entrada a pista"),
    ("q_pct_min_q4", "pct_min_q4", "% de sus minutos en el último cuarto"),
    ("q_clutch_min", "clutch_min", "Minutos en clutch (últimos 5 minutos, ±5 puntos)"),
    ("q_clutch_net", "clutch_net_rtg", "Net en clutch"),
    ("q_basura_min", "basura_min", "Minutos de la basura"),
    ("q_quintetos", "quintetos_distintos", "Quintetos distintos en los que ha jugado"),
    ("q_pct_asistidas", "pct_canastas_asistidas", "% de sus canastas que fueron asistidas"),
    ("q_socios", "socios_asistencia", "Compañeros distintos a los que asiste"),
    ("q_hhi_asist", "hhi_asistencias", "Concentración de sus asistencias (HHI 0-10.000)"),
    ("q_pagerank", "pagerank_asistencias", "Centralidad en la red de pases de su equipo (PageRank)"),
]
ZONAS_ARTIFACT = [("aro", "en el aro (< 1,8 m)"), ("corta", "cortos (1,8-4,25 m)"), ("media", "de media distancia"),
                  ("t3_esquina", "triples de esquina"), ("t3_frontal", "triples frontales")]


def pista_artifact(df: pd.DataFrame, processed_root: Path, season: str) -> pd.DataFrame:
    """Añade a las filas jugador-equipo-fase las columnas q_* de la capa de quintetos (on/off, RAPM, rotación,
    red de pases) y, en temporada regular, el perfil de tiro por zonas y el contexto de nivel (data/modelos)."""
    frames = []
    for p in sorted((processed_root / season / "quintetos").glob("*/jugadores.csv")):
        j = pd.read_csv(p, dtype={"team_id": str, "player_id": str})
        frames.append(j[["liga", "fase", "team_id", "player_id"] + [o for _, o, _ in PISTA_ARTIFACT]])
    if not frames:
        return df
    q = pd.concat(frames, ignore_index=True).rename(columns={o: c for c, o, _ in PISTA_ARTIFACT})
    out = df.copy()
    out["_tid"] = out["team_id"].astype(str)
    out["_pid"] = out["player_id"].astype(str)
    m = out.merge(q.rename(columns={"team_id": "_tid", "player_id": "_pid"}), on=["liga", "fase", "_tid", "_pid"], how="left")
    # traspasados con una fila «A;B» (EuroLeague/EuroCup): la fila de pista de su equipo con más minutos
    tr = m["_tid"].str.contains(";", na=False).to_numpy()
    if tr.any():
        qq = q.sort_values("q_min_on", ascending=False).drop_duplicates(["liga", "fase", "player_id"])
        k = m.loc[tr, ["liga", "fase", "_pid"]].merge(qq.rename(columns={"player_id": "_pid"}), on=["liga", "fase", "_pid"], how="left")
        for c, _, _ in PISTA_ARTIFACT:
            m.loc[tr, c] = k[c].to_numpy()
    modelos = processed_root.parent / "modelos"
    pz = modelos / "pista" / f"{season}.csv"
    if pz.exists():
        z = pd.read_csv(pz, dtype={"team_id": str, "player_id": str})
        g = z.groupby(["liga", "player_id"])[[f"fga_{n}" for n, _ in ZONAS_ARTIFACT] + ["fga_pbp"]].sum()
        for n, _ in ZONAS_ARTIFACT:
            g[f"q_pct_{n}"] = 100 * g[f"fga_{n}"] / g["fga_pbp"].where(g["fga_pbp"] > 0)
        g = g[[f"q_pct_{n}" for n, _ in ZONAS_ARTIFACT]].reset_index().rename(columns={"player_id": "_pid"})
        g["fase"] = "regular"
        m = m.merge(g, on=["liga", "fase", "_pid"], how="left")
    return m.drop(columns=["_tid", "_pid"])


def pista_diccionario() -> list[dict]:
    out = [{"columna": c, "grupo": "pista", "origen": "jugada a jugada", "descripcion": d} for c, _, d in PISTA_ARTIFACT]
    out += [{"columna": f"q_pct_{n}", "grupo": "pista", "origen": "jugada a jugada",
             "descripcion": f"% de sus tiros de campo {d} (temporada regular)"} for n, d in ZONAS_ARTIFACT]
    return out


def export_artifact(processed_root: Path, season: str, out_root: Path) -> list[Path]:
    """Genera los ficheros que lee el Artifact (no se versionan): <out_root>/<temporada>/<fase>.json
    (JSON columnar), <out_root>/<temporada>/indice.json, <out_root>/diccionario_columnas.json y
    <out_root>/temporadas.json."""
    src = processed_root / season
    df = read_season(src)
    if df.empty:
        raise FileNotFoundError(f"No hay CSV procesados en {src / 'ligas'}")
    df = pista_artifact(df, processed_root, season)
    dst = out_root / season
    dst.mkdir(parents=True, exist_ok=True)
    written = []
    for phase in PHASES:
        sub = df[df["fase"] == phase]
        if len(sub):
            write_columnar_json(sub, dst / f"{phase}.json")
            written.append(dst / f"{phase}.json")
    idx = json.loads((src / "indice.json").read_text(encoding="utf-8"))
    idx["archivos"] = {**idx.get("archivos", {}), **{f: f"{f}.json" for f in idx.get("fases_con_datos", [])}}
    (dst / "indice.json").write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_root / "diccionario_columnas.json").write_text(json.dumps(dictionary_records() + pista_diccionario(), ensure_ascii=False),
                                                        encoding="utf-8")
    seasons = processed_root / "temporadas.json"
    if seasons.exists():
        (out_root / "temporadas.json").write_text(seasons.read_text(encoding="utf-8"), encoding="utf-8")
    return written + [dst / "indice.json", out_root / "diccionario_columnas.json", out_root / "temporadas.json"]
