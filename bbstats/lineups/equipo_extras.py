"""Extras de equipo a partir del jugada a jugada: tiempos muertos, quintetos iniciales y posesiones defensivas.

Lee los mismos brutos que la capa de quintetos (bbstats/lineups/run.py), interpreta cada partido con su fuente
(modelo común de eventos) y escribe, por liga y temporada:

    data/processed/<temporada>/quintetos/<liga>/equipo_extras.json

con un bloque por equipo y fase (regular, playoffs, total):

  tiempos_muertos   pedidos por el equipo (no los oficiales). Por cada uno: cuarto y reloj, marcador, parcial de
                    los 120 s anteriores y de los 120 s siguientes (puntos propios − del rival) y puntos de la
                    primera posesión propia que empieza después (ATO, «after time-out»). Agregados: por partido,
                    por cuarto, en los 2 últimos minutos, tras un parcial en contra de 6 o más, cambio del parcial
                    (después − antes) y puntos por posesión ATO frente a los del resto de posesiones del equipo.
  quintetos_iniciales  quinteto que empieza cada partido (el que reconstruye stints.build) → partidos y victorias.
  defensa           posesiones del rival (bbstats/lineups/possessions.py) y cómo acaban: «stop» = posesión del
                    rival sin puntos. Stops por robo, por otra pérdida, por tapón (fallo con tapón del equipo
                    en la posesión) y por fallo sin tapón; posesiones del rival con rebote ofensivo y cuántas
                    acaban en stop; puntos encajados por posesión.
  ataque            posesiones propias y puntos por posesión (referencia para el ATO).

Uso:  python -m bbstats.lineups.equipo_extras --temporadas 2025-26 2026-27 [--ligas euroleague acb ...]
No descarga nada ni cambia las salidas de quintetos: sólo lee data/raw y escribe equipo_extras.json.
"""
from __future__ import annotations

import argparse
import bisect
import json
import logging
from collections import Counter, defaultdict
from pathlib import Path

from ..raw_store import RawStore
from .model import Game, period_length, period_start
from .possessions import count_possessions
from .run import load_games, make_source
from .sources.base import Ctx
from .stints import build

log = logging.getLogger(__name__)
RAIZ = Path(__file__).resolve().parents[2]
VENTANA_S = 120.0          # parcial antes y después de un tiempo muerto
RACHA = 6                  # parcial en contra que cuenta como «racha» del rival
FASES = ("regular", "playoffs")


def _pts(e) -> int:
    return (e.pts or (e.value if e.kind == "shot" else 1)) if e.made and e.kind in ("shot", "ft") else 0


def analizar_partido(g: Game, game_min: float) -> dict | None:
    """Datos por equipo de un partido (None si no hay dos equipos o no hay eventos)."""
    if len(g.teams) != 2 or not g.events:
        return None
    a, b = g.teams
    rival = {a: b, b: a}
    evs = sorted(g.events, key=lambda e: e.order)
    res = build(g, game_min)
    # marcador a lo largo del partido: (t, order, puntos de a, puntos de b) tras cada evento que anota
    score = {a: 0, b: 0}
    marcas: list[tuple[float, int, int, int]] = [(0.0, -1, 0, 0)]
    for e in evs:
        p = _pts(e)
        if p and e.team in score:
            score[e.team] += p
            marcas.append((e.t, e.order, score[a], score[b]))
    ts = [m[0] for m in marcas]
    ords = [m[1] for m in marcas]

    def marcador_en(t: float) -> tuple[int, int]:
        """Marcador tras todos los eventos con reloj <= t."""
        i = bisect.bisect_right(ts, t) - 1
        return marcas[max(i, 0)][2], marcas[max(i, 0)][3]

    def marcador_antes_de(order: int) -> tuple[int, int]:
        """Marcador justo antes del evento `order` (lo anotado en el mismo segundo después no cuenta)."""
        i = bisect.bisect_left(ords, order) - 1
        return marcas[max(i, 0)][2], marcas[max(i, 0)][3]

    # posesiones: dueño = equipo del primer tiro, tiro libre, pérdida o rebote ofensivo de la posesión
    n_pos, pid_of = count_possessions(evs, list(g.teams))
    pos: dict[int, dict] = {}
    for e in evs:
        pid = pid_of.get(e.order)
        if pid is None:
            continue
        d = pos.setdefault(pid, {"dueño": None, "pts": 0, "o0": e.order, "o1": e.order, "t0": e.t, "t1": e.t,
                             "fin": None, "oreb": False})
        d["o1"], d["t1"] = e.order, e.t
        if d["dueño"] is None and e.kind in ("shot", "ft", "tov", "oreb"):
            d["dueño"] = e.team
        if e.kind == "oreb":
            d["oreb"] = True
        d["fin"] = e
    for e in evs:
        pid = pid_of.get(e.order)
        if pid is not None and pid in pos and pos[pid]["dueño"] == e.team:
            pos[pid]["pts"] += _pts(e)
    # robos y tapones no son eventos de posesión: robo = pérdida emparejada con un robo del rival (el más cercano
    # en el reloj, ±3 s: la Euroliga anota el robo hasta 3 s antes o después; cada robo se usa una vez);
    # tapón = tapón del rival entre el primer y el último evento de la posesión (±1 s)
    stl = defaultdict(list)
    blk = defaultdict(list)
    for e in evs:
        if e.kind == "stl" and e.team:
            stl[e.team].append(e.t)
        elif e.kind == "blk" and e.team:
            blk[e.team].append(e.t)
    usados: set = set()
    for d in sorted(pos.values(), key=lambda d: d["o1"]):
        r = rival.get(d["dueño"])
        if r is None:
            continue
        f = d["fin"]
        if f is not None and f.kind == "tov":
            cand = [(abs(x - f.t), i) for i, x in enumerate(stl[r]) if (r, i) not in usados and abs(x - f.t) <= 3.0]
            if cand:
                usados.add((r, min(cand)[1]))
                d["stl"] = True
        if any(d["t0"] - 1.0 <= x <= d["t1"] + 1.0 for x in blk[r]):
            d["blk"] = True
    out: dict[str, dict] = {}
    for t in g.teams:
        o = rival[t]
        dfn = Counter()
        for d in pos.values():
            if d["dueño"] == o:
                dfn["pos"] += 1
                dfn["pts"] += d["pts"]
                if d["oreb"]:
                    dfn["pos_oreb"] += 1
                if d["pts"] == 0:
                    dfn["stops"] += 1
                    f = d["fin"]
                    if f is not None and f.kind == "tov":
                        dfn["stop_robo" if d.get("stl") else "stop_perdida"] += 1
                    elif d.get("blk"):
                        dfn["stop_tapon"] += 1
                    else:
                        dfn["stop_fallo"] += 1
                    if d["oreb"]:
                        dfn["stop_tras_oreb"] += 1
            elif d["dueño"] == t:
                dfn["of_pos"] += 1
                dfn["of_pts"] += d["pts"]
        out[t] = {"defensa": dict(dfn), "tiempos_muertos": [], "gana": None, "quinteto_inicial": None}
    fin = score
    for t in g.teams:
        out[t]["gana"] = fin[t] > fin[rival[t]] if fin[t] != fin[rival[t]] else None
        q = res.first_five.get(t) if g.has_lineups else None
        out[t]["quinteto_inicial"] = "|".join(q) if q and len(q) == 5 else None
    # tiempos muertos
    propias = sorted((d["o0"], d["t0"], d["pts"], d["dueño"]) for d in pos.values() if d["dueño"] is not None)
    for e in evs:
        if e.kind != "timeout" or e.team not in rival:
            continue
        t, o = e.team, rival[e.team]
        idx = {a: 0, b: 1}
        sa = marcador_antes_de(e.order)
        ant = marcador_en(max(0.0, e.t - VENTANA_S))
        fin_p = period_start(e.period, game_min) + period_length(e.period, game_min)
        fin_v = min(e.t + VENTANA_S, fin_p) if e.period >= 4 else e.t + VENTANA_S
        des = marcador_en(fin_v)
        pre = (sa[idx[t]] - ant[idx[t]]) - (sa[idx[o]] - ant[idx[o]])
        post = (des[idx[t]] - sa[idx[t]]) - (des[idx[o]] - sa[idx[o]])
        rem = period_start(e.period, game_min) + period_length(e.period, game_min) - e.t
        ato = next((p for p in propias if p[0] > e.order and p[3] == t), None)
        out[t]["tiempos_muertos"].append({
            "periodo": e.period, "restante_s": round(rem, 1), "margen": sa[idx[t]] - sa[idx[o]], "parcial_antes": pre,
            "parcial_despues": post, "ventana_despues_s": round(fin_v - e.t, 1),
            "ato_pts": ato[2] if ato is not None and ato[1] - e.t <= 30 else None})
    return out


def _agregar(partidos: list[tuple[str, str, dict, bool]]) -> dict:
    """partidos: (fase, game_id, datos del equipo, partido con algún tiempo muerto registrado)."""
    acc = {}
    for fase_obj in (*FASES, "total"):
        sel = [(gid, d, con_to) for f, gid, d, con_to in partidos if fase_obj == "total" or f == fase_obj]
        if not sel:
            continue
        dfn = Counter()
        for _, d, _ in sel:
            dfn.update(d["defensa"])
        tos = [x for _, d, con in sel if con for x in d["tiempos_muertos"]]
        n_con = sum(1 for _, _, con in sel if con)
        por_cuarto = Counter(min(x["periodo"], 5) for x in tos)
        racha = [x for x in tos if x["parcial_antes"] <= -RACHA]
        ato = [x["ato_pts"] for x in tos if x["ato_pts"] is not None]
        post = [x["parcial_despues"] for x in tos if x["ventana_despues_s"] >= 60]
        q_ini = Counter()
        q_gana = Counter()
        for _, d, _ in sel:
            q = d["quinteto_inicial"]
            if q:
                q_ini[q] += 1
                q_gana[q] += 1 if d["gana"] else 0
        media = lambda v: round(sum(v) / len(v), 2) if v else None  # noqa: E731
        acc[fase_obj] = {
            "partidos": len(sel),
            "tiempos_muertos": {
                "partidos_con_registro": n_con, "n": len(tos),
                "por_partido": round(len(tos) / n_con, 2) if n_con else None,
                "por_cuarto": [por_cuarto.get(i, 0) for i in (1, 2, 3, 4, 5)],
                "ultimos_2min": sum(1 for x in tos if x["periodo"] >= 4 and x["restante_s"] <= 120),
                "parcial_antes_medio": media([x["parcial_antes"] for x in tos]),
                "parcial_despues_medio": media([x["parcial_despues"] for x in tos if x["ventana_despues_s"] >= 60]),
                "tras_racha": len(racha),
                "racha_cortada": sum(1 for x in racha if x["parcial_despues"] >= 0 and x["ventana_despues_s"] >= 60),
                "racha_con_ventana": sum(1 for x in racha if x["ventana_despues_s"] >= 60),
                "racha_parcial_despues_medio": media([x["parcial_despues"] for x in racha if x["ventana_despues_s"] >= 60]),
                "ato_n": len(ato), "ato_pts": sum(ato), "ato_pts2": sum(x * x for x in ato),
                # sumas para el intervalo del parcial posterior (tiempos muertos con 60 s o más de ventana)
                "post_n": len(post), "post_s": sum(post), "post_s2": sum(x * x for x in post),
                "margen_medio": media([x["margen"] for x in tos]),
                "con_ventaja": sum(1 for x in tos if x["margen"] > 0),
                "con_desventaja": sum(1 for x in tos if x["margen"] < 0)},
            "defensa": dict(dfn),
            "quintetos_iniciales": [{"unidad": q, "partidos": n, "victorias": q_gana[q]}
                                    for q, n in q_ini.most_common()],
        }
    return acc


def run_liga(liga: str, season: str, cfg: dict, store: RawStore) -> dict | None:
    lcfg = cfg["ligas"][liga]
    if not lcfg.get("pbp"):
        return None
    src = make_source(lcfg["pbp"])
    _, main_doc = store.load_season(liga, season)
    ctx = Ctx(league=liga, season=season, cfg=lcfg, main_payload=main_doc["payload"] if main_doc else None)
    stored, _ = load_games(store, liga, season)
    if src.uses_main_raw:
        for ref in (src.games(ctx) if main_doc else []):
            if ref.get("final") and str(ref["game_id"]) not in stored:
                try:
                    stored[str(ref["game_id"])] = {"ref": ref, "docs": src.fetch(ctx, ref)}
                except Exception as exc:  # noqa: BLE001
                    ctx.errors.append(f"{ref['game_id']}: {type(exc).__name__}: {exc}")
    if not stored:
        return None
    por_equipo: dict[str, list] = defaultdict(list)
    nombres: dict[str, str] = {}
    n_part = n_to = 0
    errores = []
    for gid, item in stored.items():
        try:
            g = src.parse(item["docs"], item["ref"], ctx)
            datos = analizar_partido(g, ctx.game_min)
        except Exception as exc:  # noqa: BLE001 - un partido raro no detiene el resto
            errores.append(f"{gid}: {type(exc).__name__}: {exc}")
            continue
        if not datos:
            continue
        n_part += 1
        con_to = any(e.kind == "timeout" for e in g.events)
        n_to += con_to
        nombres.update({t: n for t, n in g.team_names.items() if n})
        for t, d in datos.items():
            por_equipo[t].append((g.phase if g.phase in FASES else "regular", gid, d, con_to))
    return {"liga": liga, "temporada": season, "partidos": n_part, "partidos_con_tiempos_muertos": n_to,
            "ventana_s": VENTANA_S, "racha": RACHA, "errores": errores[:50],
            "equipos": {t: {"equipo": nombres.get(t, t), **_agregar(v)} for t, v in sorted(por_equipo.items())}}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--temporadas", nargs="+", required=True)
    ap.add_argument("--ligas", nargs="*")
    ap.add_argument("--raw", default=str(RAIZ / "data" / "raw"))
    ap.add_argument("--salida", default=str(RAIZ / "data" / "processed"))
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = json.loads((RAIZ / "config" / "sources.json").read_text(encoding="utf-8"))
    store = RawStore(Path(args.raw))
    ligas = args.ligas or [k for k, v in cfg["ligas"].items() if v.get("pbp")]
    for season in args.temporadas:
        for liga in ligas:
            r = run_liga(liga, season, cfg, store)
            if not r:
                log.info("[%s %s] sin jugada a jugada", liga, season)
                continue
            d = Path(args.salida) / season / "quintetos" / liga
            d.mkdir(parents=True, exist_ok=True)
            (d / "equipo_extras.json").write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
            log.info("[%s %s] %d partidos (%d con tiempos muertos), %d equipos%s", liga, season, r["partidos"],
                     r["partidos_con_tiempos_muertos"], len(r["equipos"]),
                     f", {len(r['errores'])} errores" if r["errores"] else "")


if __name__ == "__main__":
    main()
