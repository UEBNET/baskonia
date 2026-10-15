"""Reconstrucción de tramos (stints): intervalos en los que los 10 jugadores en pista no cambian.

Algoritmo común a todas las ligas:
  1. Quinteto inicial de cada periodo: los jugadores cuyo primer evento del periodo NO es una entrada
     (estaban en pista al empezar). Si salen exactamente 5 se usan; si no, en el primer periodo se usan
     los titulares de la fuente y en los demás el quinteto con que acabó el periodo anterior. Esto cubre las
     fuentes que no anotan los cambios entre cuartos (BBL) y las que los anotan (resto).
  2. Se recorren los eventos en el orden de la fuente (el reloj nunca retrocede). Cada grupo de cambios
     cierra el tramo en curso y abre otro.
  3. Si actúa un jugador que no está en pista, se le añade cuando faltan jugadores y se anota la anomalía.
Cada tramo acumula, por equipo, puntos y estadísticas de equipo (tiros, rebotes, pérdidas...). Con eso
se calculan después ratings, factores y +/- de cualquier combinación de jugadores.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .model import Event, Game, period_length, period_start

STAT_KEYS = ("pts", "fga", "fgm", "fg2a", "fg2m", "fg3a", "fg3m", "fta", "ftm", "oreb", "dreb", "tov",
             "stl", "blk", "ast", "pf")


@dataclass
class GameResult:
    game: Game
    segments: list[dict] = field(default_factory=list)
    shots: list[dict] = field(default_factory=list)
    assists: list[dict] = field(default_factory=list)       # pasador -> anotador por canasta asistida
    player_events: dict = field(default_factory=dict)       # pid -> Counter (fgm, fga... propios)
    seconds: Counter = field(default_factory=Counter)
    pm: Counter = field(default_factory=Counter)
    anomalies: Counter = field(default_factory=Counter)

    def validation(self) -> dict:
        g = self.game
        dif_sec = [abs(self.seconds.get(p, 0.0) - b["sec"]) for p, b in g.box.items() if b.get("sec") is not None
                   and (b["sec"] > 0 or self.seconds.get(p, 0) > 0)]
        dif_pm = [abs(self.pm.get(p, 0.0) - b["pm"]) for p, b in g.box.items() if b.get("pm") is not None
                  and (b.get("sec") or 0) > 0]
        # +/- oficial incoherente (la suma de cada equipo debe ser ±5 × la diferencia final, opuestas): algunas
        # fuentes (G League) lo publican mal; entonces sólo se validan los minutos
        tsum = Counter()
        for p, b in g.box.items():
            if b.get("pm") is not None and (g.players.get(p) or {}).get("team"):
                tsum[g.players[p]["team"]] += b["pm"]
        pm_ok = len(tsum) < 2 or (abs(sum(tsum.values())) < 0.5 and all(abs(v) % 5 < 0.5 for v in tsum.values()))
        if not pm_ok:
            dif_pm = []
        return {"game_id": g.game_id, "fase": g.phase, "tramos": len(self.segments),
                "jugadores_box": len(g.box),
                "dif_min_max_s": round(max(dif_sec), 1) if dif_sec else None,
                "dif_min_media_s": round(sum(dif_sec) / len(dif_sec), 1) if dif_sec else None,
                "dif_pm_max": max(dif_pm) if dif_pm else None,
                "jugadores_dif_pm": sum(d > 0 for d in dif_pm) if dif_pm else None,
                "anomalias": sum(self.anomalies.values()),
                "detalle_anomalias": ";".join(f"{k}={v}" for k, v in sorted(self.anomalies.items())),
                "valido": bool(g.has_lineups and (not dif_sec or max(dif_sec) <= 90)
                               and (not dif_pm or max(dif_pm) <= 3)),
                "con_quintetos": g.has_lineups, "con_asistencias": g.has_assists, "con_coordenadas": g.has_shots,
                "pm_oficial_coherente": pm_ok,
                "notas": " | ".join(g.notes + ([] if pm_ok else ["+/- oficial incoherente: validado sólo por minutos"]))}


def _empty() -> dict:
    return {k: 0 for k in STAT_KEYS}


def _add_event(st: dict, e: Event) -> None:
    k = e.kind
    if k == "shot":
        st["fga"] += 1
        st["fg3a" if e.value == 3 else "fg2a"] += 1
        if e.made:
            st["fgm"] += 1
            st["fg3m" if e.value == 3 else "fg2m"] += 1
            st["pts"] += e.pts or e.value
            if e.assister:
                st["ast"] += 1
    elif k == "ft":
        st["fta"] += 1
        if e.made:
            st["ftm"] += 1
            st["pts"] += e.pts or 1
            if e.assister:
                st["ast"] += 1
    elif k in ("oreb", "dreb", "tov", "stl", "blk"):
        st[k] += 1
    elif k == "foul":
        st["pf"] += 1


def _period_starters(evs: list[Event], teams: list[str]) -> dict[str, list[str]]:
    first: dict[str, dict[str, str]] = {t: {} for t in teams}
    for e in evs:
        if e.player is None or e.team not in first:
            continue
        if e.player not in first[e.team]:
            first[e.team][e.player] = e.kind
    return {t: [p for p, k in first[t].items() if k != "in"] for t in teams}


def _garbage(period: int, frac_left: float, margin: int, starters_on: int) -> bool:
    """Minutos de la basura (criterio de Cleaning the Glass escalado a la duración del periodo): último cuarto,
    como mucho 2 titulares en pista entre los dos equipos y diferencia >= 25 en el primer cuarto del periodo
    (12:00-9:00 en la NBA), >= 20 en el segundo (9:00-6:00) y >= 10 en la segunda mitad (< 6:00)."""
    if period != 4 or starters_on > 2:
        return False
    m = abs(margin)
    return m >= 25 if frac_left > 0.75 else (m >= 20 if frac_left > 0.5 else m >= 10)


def build(game: Game, game_min: float = 40) -> GameResult:
    res = GameResult(game=game)
    teams = list(game.teams)
    if len(teams) != 2:
        res.anomalies["equipos"] += 1
        return res
    a, b = teams
    evs = sorted(game.events, key=lambda e: e.order)
    by_period: dict[int, list[Event]] = defaultdict(list)
    for e in evs:
        by_period[e.period].append(e)
    score = {a: 0, b: 0}
    on = {t: set() for t in teams}
    last_t = 0.0
    first_five: dict[str, set] = {a: set(), b: set()}   # titulares reales: quinteto al empezar el partido

    # tiros y asistencias (no dependen de saber quién está en pista)
    def lineup_of(t: str) -> str:
        return "|".join(sorted(on[t])) if game.has_lineups else ""

    for per in sorted(by_period):
        pevs = by_period[per]
        p0 = period_start(per, game_min)
        p1 = p0 + period_length(per, game_min)
        if game.has_lineups:
            cand = _period_starters(pevs, teams)
            for t in teams:
                if len(cand[t]) == 5:
                    on[t] = set(cand[t])
                elif per == min(by_period) and len(game.starters.get(t, [])) == 5:
                    on[t] = set(game.starters[t])
                    res.anomalies["quinteto_inicial_de_titulares"] += 1
                elif per != min(by_period):
                    res.anomalies["quinteto_periodo_arrastrado"] += 1
                else:
                    on[t] = set(cand[t][:5])
                    res.anomalies["quinteto_inicial_incompleto"] += 1
            if per == min(by_period):
                first_five.update({t: set(on[t]) for t in teams})
        seg = {"t0": p0, "st": {a: _empty(), b: _empty()}, "margin": score[a] - score[b]}
        last_t = max(last_t, p0)

        def close(t_end: float) -> None:
            sec = max(0.0, t_end - seg["t0"])
            if sec <= 0 and not any(seg["st"][a].values()) and not any(seg["st"][b].values()):
                return
            if not game.has_lineups:
                return
            la, lb = sorted(on[a]), sorted(on[b])
            rem = p1 - seg["t0"]
            clutch = per >= 4 and rem <= 300 and abs(seg["margin"]) <= 5
            basura = _garbage(per, rem / period_length(per, game_min), seg["margin"],
                              len(set(la) & first_five[a]) + len(set(lb) & first_five[b]))
            res.segments.append({"game_id": game.game_id, "fase": game.phase, "periodo": per,
                                 "t0": round(seg["t0"], 1), "t1": round(t_end, 1), "sec": round(sec, 1),
                                 "team_a": a, "team_b": b, "quinteto_a": "|".join(la), "quinteto_b": "|".join(lb),
                                 "n_a": len(la), "n_b": len(lb), "margen_inicio": seg["margin"], "clutch": clutch,
                                 "basura": basura,
                                 **{f"a_{k}": v for k, v in seg["st"][a].items()},
                                 **{f"b_{k}": v for k, v in seg["st"][b].items()}})
            for p in la:
                res.seconds[p] += sec
                res.pm[p] += seg["st"][a]["pts"] - seg["st"][b]["pts"]
            for p in lb:
                res.seconds[p] += sec
                res.pm[p] += seg["st"][b]["pts"] - seg["st"][a]["pts"]

        in_subs = False
        for e in pevs:
            t = min(max(e.t, last_t), p1)
            last_t = t
            if e.kind in ("in", "out"):
                if not game.has_lineups or e.team not in on or e.player is None:
                    continue
                if not in_subs:
                    close(t)
                    seg = {"t0": t, "st": {a: _empty(), b: _empty()}, "margin": score[a] - score[b]}
                    in_subs = True
                if e.kind == "in":
                    on[e.team].add(e.player)
                else:
                    if e.player not in on[e.team]:
                        res.anomalies["sale_sin_estar"] += 1
                    on[e.team].discard(e.player)
                continue
            if in_subs:
                in_subs = False
                for tt in teams:
                    if len(on[tt]) != 5:
                        res.anomalies[f"no_cinco_{len(on[tt])}"] += 1
            if e.team not in score:
                continue
            if game.has_lineups and e.player and e.kind != "foul_drawn" and e.player not in on[e.team]:
                if len(on[e.team]) < 5:
                    on[e.team].add(e.player)
                    res.anomalies["añadido_por_actuar"] += 1
                else:
                    res.anomalies["actua_fuera_de_pista"] += 1
            _add_event(seg["st"][e.team], e)
            if e.player:
                pc = res.player_events.setdefault(e.player, Counter())
                pc[e.kind + ("_made" if e.made else "")] += 1
            if e.kind in ("shot", "ft"):
                opp = b if e.team == a else a
                res.shots.append({"game_id": game.game_id, "fase": game.phase, "periodo": per, "t": round(t, 1),
                                  "team_id": e.team, "player_id": e.player, "tipo": "TL" if e.kind == "ft" else f"T{e.value}",
                                  "anotado": bool(e.made), "puntos": (e.pts or e.value) if e.made else 0,
                                  "asistente_id": e.assister, "x": e.x, "y": e.y,
                                  "quinteto": lineup_of(e.team), "quinteto_rival": lineup_of(opp),
                                  "margen_previo": score[e.team] - score[opp]})
                if e.made and e.assister:
                    res.assists.append({"game_id": game.game_id, "fase": game.phase, "team_id": e.team,
                                        "pasador_id": e.assister, "receptor_id": e.player,
                                        "tipo": "TL" if e.kind == "ft" else f"T{e.value}", "puntos": e.pts or e.value})
                if e.made:
                    score[e.team] += e.pts or (e.value if e.kind == "shot" else 1)
        close(p1)
    return res
