"""Contrato de datos de los boxscores partido a partido (y su coherencia con el jugada a jugada).

Funciones puras sobre el formato estándar de partido (bbstats/adapters/boxscore.py) y sobre los eventos del
modelo común (bbstats/lineups/model.py). Las usan los tests (tests/test_contract_feb.py, con partidos
sintéticos) y el comando `python -m bbstats contrato --ligas feb1 feb2 feb3` (datos reales, resumen por liga y
temporada; ver bbstats/feb_informe.py).

Comprobaciones por partido (cada una -> True / False / None = no aplicable):
  tipos        ids de partido, equipo y jugador = texto no vacío; estadísticas numéricas o vacías (nunca texto)
  rangos       conteos >= 0; 0 <= minutos <= 40 + 5·prórrogas + 1; anotados <= intentados
  identidades  por jugador: fgm = fg2m + fg3m, fga = fg2a + fg3a, reb = oreb + dreb, pts = 2·fg2m + 3·fg3m + ftm
  nulos        ningún id vacío; % de jugadores con minutos vacíos (informativo)
  clave_unica  (game_id, team_id, player_id) sin duplicados
  minutos      Σ minutos de cada equipo ≈ 5 × duración (200 + 25 por prórroga), tolerancia ±1 min
  marcador     Σ puntos de los jugadores = puntos del equipo (cabecera)
  pbp_*        si hay jugada a jugada: puntos, FGA, FGM, rebotes de jugador y asistencias del jugada a jugada
               frente al boxscore, por equipo (tolerancias en TOL_PBP)
"""
from __future__ import annotations

from collections import Counter
from typing import Any

COUNT_KEYS = ("pts", "fgm", "fga", "fg2m", "fg2a", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "reb", "ast",
              "stl", "tov", "blk", "pf")
PAIRS = (("fgm", "fga"), ("fg2m", "fg2a"), ("fg3m", "fg3a"), ("ftm", "fta"))
TOL_PBP = {"pts": 0, "fga": 2, "fgm": 1, "reb": 3, "ast": 2}


def _num_ok(v: Any) -> bool:
    return v is None or (isinstance(v, (int, float)) and not isinstance(v, bool) and v == v)


def n_overtimes(game: dict, events: list | None = None) -> int:
    """Prórrogas: de la cabecera (`n_periodos`) o del periodo máximo del jugada a jugada."""
    n = game.get("n_periodos")
    if n is None and events:
        n = max((e.period for e in events), default=4)
    return max(0, int(n or 4) - 4)


def check_box(game: dict, events: list | None = None) -> dict:
    """Comprobaciones de contrato de un partido en formato estándar. Devuelve {check: bool|None, ...} y
    algunos valores de diagnóstico (minutos por equipo, etc.)."""
    out: dict[str, Any] = {"game_id": game.get("game_id")}
    sides = game.get("teams") or []
    ot = n_overtimes(game, events)
    max_min = 40 + 5 * ot + 1
    tipos = rangos = ident = nulos = True
    keys: Counter = Counter()
    n_pl = n_min_null = 0
    min_ok = []
    marc_ok = []
    for s in sides:
        tid = s.get("team_id")
        if not isinstance(tid, str) or not tid:
            tipos = nulos = False
        tot_min = 0.0
        have_min = True
        pts_sum = 0.0
        for p in s.get("players") or []:
            n_pl += 1
            pid = p.get("player_id")
            if not isinstance(pid, str) or not pid:
                tipos = nulos = False
            keys[(str(game.get("game_id")), str(tid), str(pid))] += 1
            for k in COUNT_KEYS + ("min",):
                v = p.get(k)
                if not _num_ok(v):
                    tipos = False
                    continue
                if v is not None and v < 0:
                    rangos = False
            m = p.get("min")
            if m is None:
                n_min_null += 1
                if any(p.get(k) for k in ("pts", "fga", "fta", "reb", "pf")):
                    have_min = False
            else:
                tot_min += m if _num_ok(m) else 0
                if _num_ok(m) and m > max_min:
                    rangos = False
            for a, b in PAIRS:
                if _num_ok(p.get(a)) and _num_ok(p.get(b)) and p.get(a) is not None and p.get(b) is not None \
                        and p[a] > p[b]:
                    rangos = False
            g = {k: p.get(k) for k in COUNT_KEYS}
            if all(_num_ok(v) for v in g.values()):
                if None not in (g["fgm"], g["fg2m"], g["fg3m"]) and g["fgm"] != g["fg2m"] + g["fg3m"]:
                    ident = False
                if None not in (g["fga"], g["fg2a"], g["fg3a"]) and g["fga"] != g["fg2a"] + g["fg3a"]:
                    ident = False
                if None not in (g["reb"], g["oreb"], g["dreb"]) and g["reb"] != g["oreb"] + g["dreb"]:
                    ident = False
                if None not in (g["pts"], g["fg2m"], g["fg3m"], g["ftm"]) and \
                        g["pts"] != 2 * g["fg2m"] + 3 * g["fg3m"] + g["ftm"]:
                    ident = False
            pts_sum += (p.get("pts") or 0) if _num_ok(p.get("pts")) else 0
        exp = 200 + 25 * ot
        min_ok.append(abs(tot_min - exp) <= 1.0 if have_min and tot_min > 0 else None)
        hp = (s.get("totals") or {}).get("pts")
        marc_ok.append(None if hp is None else abs(pts_sum - hp) < 0.5)
        out[f"min_equipo_{len(min_ok)}"] = round(tot_min, 2)
    out.update(tipos=tipos, rangos=rangos, identidades=ident, nulos=nulos,
               clave_unica=all(v == 1 for v in keys.values()),
               minutos=None if any(v is None for v in min_ok) or not min_ok else all(min_ok),
               marcador=None if any(v is None for v in marc_ok) or not marc_ok else all(marc_ok),
               pct_min_vacio=round(100 * n_min_null / n_pl, 1) if n_pl else None, prorrogas=ot,
               n_jugadores=n_pl)
    return out


def pbp_team_totals(events: list) -> dict[str, Counter]:
    """Totales por equipo del jugada a jugada: pts, fga, fgm, reb (sólo de jugador), ast."""
    tot: dict[str, Counter] = {}
    for e in events:
        if e.team is None:
            continue
        c = tot.setdefault(e.team, Counter())
        if e.kind == "shot":
            c["fga"] += 1
            if e.made:
                c["fgm"] += 1
                c["pts"] += e.pts or e.value
        elif e.kind == "ft" and e.made:
            c["pts"] += e.pts or 1
        elif e.kind in ("oreb", "dreb") and e.player:
            c["reb"] += 1
        if e.kind in ("shot", "ft") and e.made and e.assister:
            c["ast"] += 1
    return tot


def check_pbp(game: dict, events: list) -> dict:
    """Coherencia jugada a jugada ↔ boxscore por equipo: {pbp_pts, pbp_fga, pbp_fgm, pbp_reb, pbp_ast}
    (True si los dos equipos están dentro de la tolerancia) y las diferencias máximas."""
    out: dict[str, Any] = {}
    if not events:
        return {f"pbp_{k}": None for k in TOL_PBP}
    tot = pbp_team_totals(events)
    for k, tol in TOL_PBP.items():
        difs = []
        for s in game.get("teams") or []:
            box = sum((p.get(k) or 0) for p in s.get("players") or [] if _num_ok(p.get(k)))
            difs.append(abs(tot.get(s.get("team_id"), Counter())[k] - box))
        out[f"pbp_{k}"] = all(d <= tol for d in difs) if difs else None
        out[f"dif_{k}"] = max(difs) if difs else None
    return out


CHECKS = ["tipos", "rangos", "identidades", "nulos", "clave_unica", "minutos", "marcador",
          "pbp_pts", "pbp_fga", "pbp_fgm", "pbp_reb", "pbp_ast"]


def resumen(filas: list[dict]) -> dict:
    """% de partidos que pasan cada comprobación (sobre los aplicables) y nº de aplicables."""
    out: dict[str, Any] = {"partidos": len(filas)}
    for c in CHECKS:
        vals = [f.get(c) for f in filas if f.get(c) is not None]
        out[f"{c}_pct"] = round(100 * sum(bool(v) for v in vals) / len(vals), 2) if vals else None
        out[f"{c}_n"] = len(vals)
    return out
