"""Capa de quintetos y conexiones: descarga incremental del jugada a jugada, tramos y métricas.

Para cada liga y temporada:
  1. Lee los paquetes brutos ya guardados: data/raw/<liga>/<temporada>/pbp_<liga>_<temporada>_<fecha>.json.gz
     (cada paquete contiene sólo los partidos descargados en esa ejecución; nunca se sobrescriben).
  2. Si hay descarga, pide a la fuente la lista de partidos y descarga los terminados que falten.
  3. Interpreta todos los partidos (modelo común), reconstruye tramos y valida contra el boxscore oficial.
  4. Escribe data/processed/<temporada>/quintetos/<liga>/: quintetos, trios, parejas, jugadores (on/off,
     clutch, basura, rotación, RAPM, red de asistencias), asistencias (pasador → anotador), equipos (estructura
     de quintetos y rotación), validacion (CSV) y tramos y tiros
     (CSV comprimido), más *_oficial.csv cuando la fuente publica tablas oficiales (NBA, G League).
"""
from __future__ import annotations

import importlib
import logging
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from .. import __version__
from ..http import HttpClient
from ..raw_store import RawStore
from ..utils import utc_now, utc_stamp
from . import metrics as M
from .schema import ASSIST_COLS, LINEUP_COLS, PAIR_COLS, PLAYER_COLS, SHOT_COLS, TEAM_COLS, TRIO_COLS
from .sources.base import Ctx, PBPSource
from .stints import build

log = logging.getLogger(__name__)

SOURCES = {
    "euroleague_live": ("euroleague", "EuroleaguePBP"),
    "acb": ("acb", "AcbPBP"),
    "lba": ("lba", "LbaPBP"),
    "bbl": ("bbl", "BblPBP"),
    "lnb": ("lnb", "LnbPBP"),
    "gleague_stats": ("nba_stats", "GLeaguePBP"),
    "nba_stats": ("nba_stats", "NbaPBP"),
    "fiba_web": ("fiba_web", "FibaWebPBP"),
    "fiba_livestats": ("fiba_livestats", "FibaLiveStatsPBP"),
}


def make_source(name: str) -> PBPSource:
    mod, cls = SOURCES[name]
    return getattr(importlib.import_module(f"bbstats.lineups.sources.{mod}"), cls)()


def load_games(store: RawStore, liga: str, season: str) -> tuple[dict, dict]:
    """Une todos los paquetes pbp de la temporada: {game_id: {"ref", "docs"}} y tablas oficiales (la última)."""
    games, official = {}, {}
    for path in store.list(liga, season, kind="pbp"):
        payload = RawStore.load(path)["payload"]
        games.update(payload.get("games") or {})
        if payload.get("oficial"):
            official = payload["oficial"]
    return games, official


def run_league(liga: str, cfg: dict, season: str, download: bool, store: RawStore, out_dir: Path,
               progress: Callable[[str], None], http_factory: Callable[[], HttpClient]) -> dict:
    lcfg = cfg["ligas"][liga]
    qcfg = {**(cfg.get("quintetos") or {}), **(lcfg.get("quintetos") or {})}
    rep: dict[str, Any] = {"estado": "desactivado", "partidos": 0, "partidos_nuevos": 0, "errores": []}
    src_name = lcfg.get("pbp")
    if not src_name or not qcfg.get("activo", True):
        return rep
    src = make_source(src_name)
    main_path, main_doc = store.load_season(liga, season)
    main_payload = main_doc["payload"] if main_doc else None
    ctx = Ctx(league=liga, season=season, cfg=lcfg, main_payload=main_payload)
    stored, official = load_games(store, liga, season)
    if src.uses_main_raw:
        # el jugada a jugada viene en el bruto principal (se actualiza con la ejecución normal de la liga)
        download = False
        for ref in (src.games(ctx) if main_payload else []):
            if ref.get("final") and str(ref["game_id"]) not in stored:
                try:
                    stored[str(ref["game_id"])] = {"ref": ref, "docs": src.fetch(ctx, ref)}
                except Exception as exc:  # noqa: BLE001
                    ctx.errors.append(f"{ref['game_id']}: {type(exc).__name__}: {exc}")
    if download:
        ctx.http = http_factory()
        new: dict[str, dict] = {}
        n_new = 0
        block = int(qcfg.get("guardar_cada_partidos", 150))

        def flush(off_raw: dict | None = None) -> None:
            """Guarda los partidos pendientes (y las tablas oficiales) en un paquete nuevo: si la ejecución se
            corta, lo ya descargado no se pierde y la siguiente sólo pide lo que falte."""
            nonlocal new, official
            if not new and not off_raw:
                return
            now = utc_now()
            meta = {"liga": liga, "temporada": season, "tipo": "pbp", "fuente": src.name,
                    "version_fuente": src.version, "version_bbstats": __version__,
                    "fecha_extraccion": now.isoformat(), "fecha_extraccion_stamp": utc_stamp(now),
                    "partidos": sorted(new), "peticiones": len(ctx.http.request_log()), "errores": ctx.errors}
            path = store.save(liga, season, meta, {"games": new, "oficial": off_raw or {}}, kind="pbp")
            progress(f"[{liga}] quintetos: bruto guardado en {path.name} ({len(new)} partidos)")
            stored.update(new)
            new = {}
            if off_raw:
                official = off_raw

        try:
            refs = src.games(ctx)
            todo = [r for r in refs if r.get("final") and str(r["game_id"]) not in stored]
            limit = qcfg.get("max_partidos_por_ejecucion")
            if limit:
                todo = todo[: int(limit)]
            progress(f"[{liga}] quintetos: {len(refs)} partidos en la fuente, {len(todo)} nuevos por descargar")
            for i, ref in enumerate(todo, 1):
                try:
                    new[str(ref["game_id"])] = {"ref": ref, "docs": src.fetch(ctx, ref)}
                    n_new += 1
                except Exception as exc:  # noqa: BLE001 - un partido caído no detiene el resto
                    ctx.errors.append(f"{ref['game_id']}: {type(exc).__name__}: {exc}")
                if i % 50 == 0:
                    progress(f"[{liga}] quintetos: {i}/{len(todo)} partidos descargados")
                if block and len(new) >= block:
                    flush()
            # tablas oficiales: sólo si la temporada ya tiene partidos (y se refrescan cuando llegan nuevos)
            off_raw = src.official(ctx) if (n_new or stored or new) and (n_new or not official) else {}
        except Exception as exc:  # noqa: BLE001
            ctx.errors.append(f"Lista de partidos: {type(exc).__name__}: {exc}")
            off_raw = {}
        flush(off_raw)
        rep["partidos_nuevos"] = n_new
    rep["errores"] = list(ctx.errors)
    if not stored:
        rep["estado"] = "sin_datos"
        return rep
    results, names, teams = [], {}, {}
    for gid, item in stored.items():
        try:
            game = src.parse(item["docs"], item["ref"], ctx)
        except Exception as exc:  # noqa: BLE001
            rep["errores"].append(f"parse {gid}: {type(exc).__name__}: {exc}")
            continue
        results.append(build(game, ctx.game_min))
        names.update({p: v.get("nombre") for p, v in game.players.items()})
        teams.update({t: n for t, n in game.team_names.items() if n})
    rep["partidos"] = len(results)
    written = write_outputs(liga, season, results, official, src, ctx, names, teams, out_dir / "quintetos" / liga,
                            cfg, lcfg)
    rep.update(written)
    rep["estado"] = "ok" if results else "sin_datos"
    if rep.get("partidos_con_quintetos"):
        progress(f"[{liga}] quintetos: {rep['partidos']} partidos, {rep.get('quintetos', 0)} quintetos, "
                 f"{rep.get('validos_pct', 0)} % de los partidos con cambios validados")
    else:
        progress(f"[{liga}] quintetos: {rep['partidos']} partidos sin cambios en la fuente (sólo tiros y asistencias)")
    return rep


def _round(df: pd.DataFrame) -> pd.DataFrame:
    num = df.select_dtypes(include="number").columns
    df[num] = df[num].round(4)
    return df


def _write(df: pd.DataFrame, cols: list, path: Path) -> None:
    """CSV (comprimido si el nombre acaba en .gz: quintetos, tríos y parejas, las tablas grandes)."""
    names = [c if isinstance(c, str) else c[0] for c in cols]
    out = df.reindex(columns=names) if not df.empty else pd.DataFrame(columns=names)
    path.parent.mkdir(parents=True, exist_ok=True)
    _round(out).to_csv(path, index=False, encoding="utf-8", float_format="%.10g")
    other = path.with_suffix("") if path.suffix == ".gz" else path.with_name(path.name + ".gz")
    other.unlink(missing_ok=True)   # sin restos del formato anterior


def write_outputs(liga: str, season: str, results: list, official: dict, src: PBPSource, ctx: Ctx,
                  names: dict, teams: dict, out: Path, cfg: dict, lcfg: dict) -> dict:
    qcfg = {**(cfg.get("quintetos") or {}), **(lcfg.get("quintetos") or {})}
    k = float(qcfg.get("contraccion_posesiones", 300))
    lam = float(qcfg.get("rapm_lambda", 1500))
    coef = float(lcfg.get("coef_tl_posesion", 0.4)) + 0.04
    game_min = float(lcfg.get("minutos_partido", 40))
    max_dif = float(qcfg.get("excluir_si_dif_min_s", 120))
    vals = [r.validation() for r in results]
    usable = []
    for r, v in zip(results, vals):
        ok = v["con_quintetos"] and (v["dif_min_max_s"] is None or v["dif_min_max_s"] <= max_dif)
        v["usado_en_quintetos"] = bool(ok)
        if ok:
            usable.append(r)
    seg = pd.DataFrame([s for r in usable for s in r.segments])
    shots = pd.DataFrame([s for r in results for s in r.shots])
    assists = pd.DataFrame([a for r in results for a in r.assists])
    val = pd.DataFrame(vals)
    fgm = Counter()
    for r in results:
        for p, c in r.player_events.items():
            fgm[p] += c.get("shot_made", 0)
    fgm = pd.Series(fgm, dtype=float)
    rows_all = M.team_rows(seg) if not seg.empty else pd.DataFrame()
    nm = lambda ids: " / ".join(names.get(p) or p for p in ids.split("|"))  # noqa: E731
    tables = {"quintetos": [], "trios": [], "parejas": [], "jugadores": [], "asistencias": [], "equipos": []}
    for fase in M.PHASES:
        rows = rows_all if fase == "total" or rows_all.empty else rows_all[rows_all["fase"] == fase]
        ast_f = assists if fase == "total" or assists.empty else assists[assists["fase"] == fase]
        if rows.empty and ast_f.empty:
            continue
        ident = {"liga": liga, "temporada": season, "fase": fase}
        pair = q5 = q3 = pd.DataFrame()
        if not rows.empty:
            lg = M.league_context(rows, coef)
            rp = M.rapm(rows, coef, lam)
            rmap = rp.set_index("player_id")["rapm"] if not rp.empty else pd.Series(dtype=float)
            q5 = M.unit_table(rows, 5, lg, game_min, coef, k)
            if not q5.empty:
                q5["rapm_suma"] = q5["unidad"].map(lambda u: sum(rmap.get(p, np.nan) for p in u.split("|")))
                exp = M.expected_net(rows, rmap, coef)
                q5 = q5.merge(exp, on=["team_id", "unidad"], how="left")
                w = q5["poss"] / (q5["poss"] + k)
                q5["sinergia"] = w * (q5["net_rtg"] - q5["net_esperado"])
            q3 = M.unit_table(rows, 3, lg, game_min, coef, k)
            pair = M.unit_table(rows, 2, lg, game_min, coef, k)
            for size, t in ((3, q3), (2, pair)):
                if not t.empty:
                    exp = M.expected_net(rows, rmap, coef, size).set_index(["team_id", "unidad"])["net_esperado"]
                    t["net_esperado"] = exp.reindex(pd.MultiIndex.from_frame(t[["team_id", "unidad"]])).values
                    t["sinergia_rapm"] = t["poss"] / (t["poss"] + k) * (t["net_rtg"] - t["net_esperado"])
            sums_on = M.on_sums(rows)
            if not pair.empty:
                pair = pd.concat([pair, M.wowy_pairs(rows, pair, sums_on, lg, game_min, coef, k)], axis=1)
                ab = pair["unidad"].str.split("|", expand=True)
                pair["jugador_a_id"], pair["jugador_b_id"] = ab[0], ab[1]
                pair["jugador_a"] = ab[0].map(lambda p: names.get(p) or p)
                pair["jugador_b"] = ab[1].map(lambda p: names.get(p) or p)
                on_min = sums_on.set_index(["team_id", "player_id"])["sec"] / 60
                for x, y_ in (("a", ab[0]), ("b", ab[1])):
                    pm_ = on_min.reindex(pd.MultiIndex.from_arrays([pair["team_id"], y_])).values
                    pair[f"pct_min_{x}_con_{'b' if x == 'a' else 'a'}"] = 100 * M._div(pair["min"], pm_)
            pl = M.onoff_table(rows, lg, game_min, coef, k)
            if not rp.empty and not pl.empty:
                pl = pl.merge(rp, on="player_id", how="left")
            rot = M.rotation_table(rows)
            if not rot.empty and not pl.empty:
                pl = pl.merge(rot, on=["team_id", "player_id"], how="left")
        else:
            pl = pd.DataFrame()
        con, net = M.assist_tables(ast_f, fgm, pair[["team_id", "unidad", "min"]] if not pair.empty else pd.DataFrame())
        if not net.empty:
            pl = net if pl.empty else pl.merge(net, on=["team_id", "player_id"], how="outer")
        if not pl.empty:
            pl = pl.copy().assign(**ident, equipo=pl["team_id"].map(lambda x: teams.get(x, x)),
                           nombre=pl["player_id"].map(lambda p: names.get(p) or p))
            tables["jugadores"].append(pl)
        if not con.empty:
            if not pair.empty:
                cnt = con.set_index(["team_id", "pasador_id", "receptor_id"])["ast"]
                pair["ast_a_a_b"] = [cnt.get((t, a, b), 0) for t, a, b in zip(pair["team_id"], pair["jugador_a_id"], pair["jugador_b_id"])]
                pair["ast_b_a_a"] = [cnt.get((t, b, a), 0) for t, a, b in zip(pair["team_id"], pair["jugador_a_id"], pair["jugador_b_id"])]
                pair["ast_por40_juntos"] = 40 * M._div(pair["ast_a_a_b"] + pair["ast_b_a_a"], pair["min"])
            con = con.assign(**ident, equipo=con["team_id"].map(lambda x: teams.get(x, x)),
                             pasador=con["pasador_id"].map(lambda p: names.get(p) or p),
                             receptor=con["receptor_id"].map(lambda p: names.get(p) or p))
            tables["asistencias"].append(con)
        if not rows.empty:
            eq = M.team_table(rows, q5, pl, lg, game_min, coef, k, names)
            if not eq.empty:
                tables["equipos"].append(eq.assign(**ident, equipo=eq["team_id"].map(lambda x: teams.get(x, x))))
        for name, t in (("quintetos", q5), ("trios", q3), ("parejas", pair)):
            if not t.empty:
                tables[name].append(t.assign(**ident, equipo=t["team_id"].map(lambda x: teams.get(x, x)),
                                             jugadores=t["unidad"].map(nm)))
    cat = {k_: (pd.concat(v, ignore_index=True) if v else pd.DataFrame()) for k_, v in tables.items()}
    _write(cat["quintetos"].sort_values(["fase", "min"], ascending=[True, False]) if not cat["quintetos"].empty else cat["quintetos"],
           LINEUP_COLS, out / "quintetos.csv.gz")
    _write(cat["trios"], TRIO_COLS, out / "trios.csv.gz")
    _write(cat["parejas"], PAIR_COLS, out / "parejas.csv.gz")
    _write(cat["jugadores"], PLAYER_COLS, out / "jugadores.csv")
    _write(cat["asistencias"], ASSIST_COLS, out / "asistencias.csv")
    _write(cat["equipos"], TEAM_COLS, out / "equipos.csv")
    val.to_csv(out / "validacion.csv", index=False, encoding="utf-8")
    if not seg.empty:
        _round(seg.assign(liga=liga, temporada=season)).to_csv(out / "tramos.csv.gz", index=False, encoding="utf-8",
                                                                float_format="%.10g", compression="gzip")
    if not shots.empty:
        shots = shots.assign(liga=liga, temporada=season, nombre=shots["player_id"].map(lambda p: names.get(p) or p),
                             asistente=shots["asistente_id"].map(lambda p: names.get(p) if p else None))
        shots.reindex(columns=SHOT_COLS).to_csv(out / "tiros.csv.gz", index=False, encoding="utf-8", compression="gzip")
    for name, rows in (src.parse_official(official, ctx) if official else {}).items():
        if rows:
            pd.DataFrame(rows).assign(liga=liga, temporada=season).to_csv(out / f"{name}_oficial.csv", index=False,
                                                                          encoding="utf-8")
    ok = val.loc[val["con_quintetos"].astype(bool), "valido"].mean() * 100 if not val.empty and val["con_quintetos"].any() else 0
    return {"quintetos": int((cat["quintetos"]["fase"] == "total").sum()) if not cat["quintetos"].empty else 0,
            "parejas": int((cat["parejas"]["fase"] == "total").sum()) if not cat["parejas"].empty else 0,
            "validos_pct": round(float(ok), 1),
            "partidos_con_quintetos": int(val["con_quintetos"].sum()) if not val.empty else 0,
            "directorio": str(out)}
