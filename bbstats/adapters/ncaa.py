"""NCAA Division I masculina — API pública de ESPN (la que usa espn.com), limitada al top-50 de cada temporada.

    https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/
        teams/<id>/schedule?season=<año>&seasontype=2|3   calendario del equipo (2 = regular, 3 = postemporada)
        teams/<id>/roster?season=<año>                    plantilla (altura) y entrenador principal
        summary?event=<id>                                partido: boxscore + jugada a jugada + cabecera

<año> = año de FIN de temporada (2025-26 = 2026). ESPN no da todo el país: el alcance es la lista
`temporadas.<t>.top50` de la config ([{espn_id, nombre, rank}], T-Rank final de barttorvik.com). Se
descargan TODOS los partidos de esos equipos (también contra rivales de fuera del top-50 o de fuera de la
D-I: así los totales de equipo y de rival son completos); un partido entre dos top-50 se descarga una vez.
En el parse sólo quedan las filas de jugador y de equipo de los top-50 (los rivales cuentan en opp_*).

Fases (del calendario):
  regular   seasontype 2: liga regular, torneos de inicio de temporada (MTE) y torneos de conferencia
  playoffs  seasontype 3 con notes "Men's Basketball Championship - …" (torneo NCAA, First Four incluido)
  excluida  resto de seasontype 3 (NIT, CBI, College Basketball Crown…): no se descarga

El partido se traduce al formato del data.json de FIBA LiveStats (`to_fls`) y se reutilizan el parse de
boxscores (parse_fiba_game + aggregate_by_phase) y el jugada a jugada de la BSL/GBL. Ids: jugador = athlete
id de ESPN, equipo = team id de ESPN (nombre visible: displayName).

Partido de 2 mitades de 20': cada mitad se traduce como dos «cuartos» de 10' (1.ª mitad 20:00-10:00 =
periodo 1, 10:00-0:00 = periodo 2; 2.ª mitad = periodos 3 y 4) para que el tiempo transcurrido del modelo
común (cuartos de minutos_partido/4) salga exacto; las prórrogas (5') van como OVERTIME 1, 2…

Huecos de la fuente: ESPN sólo trae sustituciones desde 2024-25 (parte de los partidos) y en todos los de
2025-26; sin cambios el partido entra con boxscore, tiros y asistencias pero no en quintetos. Las coordenadas
reales de tiro faltan en la mayoría de partidos anteriores a 2025 ((25, 0) = relleno, se descarta). Minutos
enteros, sin +/- ni faltas recibidas. Bruto INCREMENTAL (como fiba_livestats).
"""
from __future__ import annotations

import re
from typing import Any

from ..http import FetchError, HttpClient
from ..utils import to_float
from .base import AdapterError, NoDataYet
from .boxscore import aggregate_by_phase
from .fiba_livestats import FibaLiveStatsAdapter, _is_final, parse_fiba_game

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball"
SCHED_URL = BASE + "/teams/{tid}/schedule?season={year}&seasontype={st}"
ROSTER_URL = BASE + "/teams/{tid}/roster?season={year}"
SUMMARY_URL = BASE + "/summary?event={gid}"
CLAVES = ("boxscore", "plays", "header", "gameInfo", "format")
NCAA_TOURNEY = "men's basketball championship"

# boxscore de ESPN (keys) -> data.json de FIBA LiveStats; "a-b" = anotados-intentados
_BOX = {"points": "sPoints", "rebounds": "sReboundsTotal", "assists": "sAssists", "turnovers": "sTurnovers",
        "steals": "sSteals", "blocks": "sBlocks", "offensiveRebounds": "sReboundsOffensive",
        "defensiveRebounds": "sReboundsDefensive", "fouls": "sFoulsPersonal"}
_PAIRS = {"fieldGoalsMade-fieldGoalsAttempted": ("sFieldGoalsMade", "sFieldGoalsAttempted"),
          "threePointFieldGoalsMade-threePointFieldGoalsAttempted": ("sThreePointersMade", "sThreePointersAttempted"),
          "freeThrowsMade-freeThrowsAttempted": ("sFreeThrowsMade", "sFreeThrowsAttempted")}
_TEAM = {"totalRebounds": "sReboundsTotal", "offensiveRebounds": "sReboundsOffensive",
         "defensiveRebounds": "sReboundsDefensive", "assists": "sAssists", "steals": "sSteals", "blocks": "sBlocks",
         "totalTurnovers": "sTurnovers", "fouls": "sFoulsPersonal", "pointsInPaint": "sPointsInThePaint",
         "fastBreakPoints": "sPointsFastBreak", "turnoverPoints": "sPointsFromTurnovers"}


def espn_year(season: str) -> int:
    """'2025-26' -> 2026 (ESPN numera la temporada por el año en que acaba)."""
    return int(season[:4]) + 1


def phase_of(seasontype: Any, notes: str) -> str | None:
    """Fase de un partido del calendario: regular | playoffs | excluida | None (pretemporada/otros)."""
    st = str(seasontype)
    if st == "2":
        return "regular"
    if st == "3":
        return "playoffs" if NCAA_TOURNEY in (notes or "").lower() else "excluida"
    return None


def _split(v: Any) -> tuple[float | None, float | None]:
    m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", str(v or ""))
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)


def _stats_line(keys: list, vals: list) -> dict:
    out: dict[str, Any] = {}
    rec = dict(zip(keys or [], vals or []))
    for k, v in rec.items():
        if k in _BOX and to_float(v) is not None:
            out[_BOX[k]] = to_float(v)
        elif k in _PAIRS:
            m, a = _split(v)
            if m is not None:
                out[_PAIRS[k][0]], out[_PAIRS[k][1]] = m, a
    if "sFieldGoalsMade" in out and "sThreePointersMade" in out:
        out["sTwoPointersMade"] = out["sFieldGoalsMade"] - out["sThreePointersMade"]
        out["sTwoPointersAttempted"] = out["sFieldGoalsAttempted"] - out["sThreePointersAttempted"]
    return out


def _real_xy(c: Any) -> tuple[float, float] | None:
    """Coordenada de ESPN (pies; x lateral 0-50, y a lo largo desde el aro, media pista) -> % de la pista
    COMPLETA como FIBA LiveStats (x a lo largo 0-100 = 94 pies, aro izquierdo a 5,25 pies; y lateral 0-100 =
    50 pies). Todos los tiros se llevan al aro izquierdo. (25, 0) es el relleno de ESPN: None."""
    if not isinstance(c, dict):
        return None
    x, y = to_float(c.get("x")), to_float(c.get("y"))
    if x is None or y is None or (x == 25 and y == 0) or not (0 <= x <= 50) or not (-6 <= y <= 89):
        return None
    return round((5.25 + y) / 94 * 100, 2), round(x / 50 * 100, 2)


def _period_clock(per: int, clock: Any) -> tuple[int, str, str]:
    """(periodo, periodType, reloj restante) en «cuartos» de 10' a partir de la mitad de 20' de ESPN."""
    s = str(clock or "0:00").strip()
    parts = [to_float(p) or 0.0 for p in s.split(":")] if s else [0.0]
    rem = 0.0
    for p in parts:
        rem = rem * 60 + p
    if per >= 3:
        return per - 2, "OVERTIME", _mmss(rem)
    q = 2 * per - 1 if rem > 600 else 2 * per
    return q, "REGULAR", _mmss(rem - 600 if rem > 600 else rem)


def _mmss(sec: float) -> str:
    m, s = divmod(max(0.0, sec), 60)
    return f"{int(m):02d}:{s:05.2f}" if s != int(s) else f"{int(m):02d}:{int(s):02d}"


def _coach(roster: dict | None) -> dict:
    c = (roster or {}).get("coach")
    c = c[0] if isinstance(c, list) and c else c
    if not isinstance(c, dict):
        return {}
    first, last = c.get("firstName") or "", c.get("lastName") or ""
    return {"coach": f"{first} {last}".strip() or None,
            "coachDetails": {"firstName": first, "familyName": last, "personId": c.get("id")}}


def to_fls(doc: dict, rosters: dict | None = None) -> dict:
    """summary de ESPN -> estructura del data.json de FIBA LiveStats (tm, pbp, shot). `rosters` =
    {team_id: plantilla de ESPN} (entrenador y altura; sólo de los equipos top-50)."""
    rosters = rosters or {}
    comp = (((doc.get("header") or {}).get("competitions") or [{}])[0]) or {}
    comps = {str(c.get("id")): c for c in comp.get("competitors") or []}
    order = sorted(comps, key=lambda t: 0 if comps[t].get("homeAway") == "home" else 1)
    box_t = {str((t.get("team") or {}).get("id")): t for t in (doc.get("boxscore") or {}).get("teams") or []}
    box_p = {str((t.get("team") or {}).get("id")): t for t in (doc.get("boxscore") or {}).get("players") or []}
    if not order:
        order = list(box_t)[::-1]
    side = {tid: str(i + 1) for i, tid in enumerate(order[:2])}
    tm: dict[str, dict] = {}
    pno: dict[str, tuple[str, str]] = {}
    for tid, k in side.items():
        c = comps.get(tid) or {}
        team = c.get("team") or (box_t.get(tid) or {}).get("team") or {}
        heights = {str(a.get("id")): a.get("height") for a in (rosters.get(tid) or {}).get("athletes") or []}
        t = {"teamId": tid, "name": team.get("displayName") or team.get("location"),
             "code": team.get("abbreviation"), "score": to_float(c.get("score")), "pl": {}, "shot": [],
             **_coach(rosters.get(tid))}
        for s in (box_t.get(tid) or {}).get("statistics") or []:
            nm, v = s.get("name"), s.get("displayValue")
            if nm in _PAIRS:
                m, a = _split(v)
                if m is not None:
                    t["tot_" + _PAIRS[nm][0]], t["tot_" + _PAIRS[nm][1]] = m, a
            elif nm in _TEAM and to_float(v) is not None:
                t["tot_" + _TEAM[nm]] = to_float(v)
        if "tot_sFieldGoalsMade" in t and "tot_sThreePointersMade" in t:
            t["tot_sTwoPointersMade"] = t["tot_sFieldGoalsMade"] - t["tot_sThreePointersMade"]
            t["tot_sTwoPointersAttempted"] = t["tot_sFieldGoalsAttempted"] - t["tot_sThreePointersAttempted"]
        if t["score"] is not None:
            t["tot_sPoints"] = t["score"]
        for st in (box_p.get(tid) or {}).get("statistics") or []:
            for a in st.get("athletes") or []:
                ath = a.get("athlete") or {}
                pid = str(ath.get("id") or "")
                if not pid or pid in pno:
                    continue
                n = str(len(t["pl"]) + 1)
                pno[pid] = (k, n)
                vals = a.get("stats") or []
                line = {"personId": pid, "firstName": "", "familyName": "", "name": ath.get("displayName"),
                        "shirtNumber": ath.get("jersey"),
                        "playingPosition": (ath.get("position") or {}).get("abbreviation"),
                        "starter": 1 if a.get("starter") else 0, "height": heights.get(pid)}
                if vals:
                    line.update(_stats_line(st.get("keys") or [], vals))
                    mins = to_float(dict(zip(st.get("keys") or [], vals)).get("minutes"))
                    line["sMinutes"] = f"{int(mins)}:00" if mins is not None else None
                else:
                    line["sMinutes"] = "0:00"          # no jugó (didNotPlay)
                t["pl"][n] = line
        tm[k] = t
    plays = [p for p in doc.get("plays") or [] if isinstance(p, dict)]
    pbp: list[dict] = []
    last_made: dict[str, int] = {}
    last_miss: dict[str, str] = {}
    blocked: dict[str, int] = {}

    def add(at: str, k: str | None, pid: str | None, base: dict, **kw) -> dict:
        n = pno.get(pid, (k, "0"))[1] if pid else "0"
        e = {**base, "actionNumber": len(pbp) + 1, "actionType": at, "tno": int(k) if k else 0, "pno": int(n),
             **kw}
        pbp.append(e)
        return e

    for p in plays:
        tt = str((p.get("type") or {}).get("text") or "")
        parts = [str((x.get("athlete") or {}).get("id")) for x in p.get("participants") or []
                 if (x.get("athlete") or {}).get("id")]
        pid = parts[0] if parts else None
        k = side.get(str((p.get("team") or {}).get("id")))
        if pid in pno:
            k = pno[pid][0]
        per, ptype, gt = _period_clock(int(to_float((p.get("period") or {}).get("number")) or 1),
                                       (p.get("clock") or {}).get("displayValue"))
        base = {"period": per, "periodType": ptype, "gt": gt, "s1": p.get("homeScore"), "s2": p.get("awayScore")}
        made = bool(p.get("scoringPlay"))
        if p.get("shootingPlay") and "freethrow" in tt.lower().replace(" ", ""):
            e = add("freethrow", k, pid, base, success=1 if made else 0, subType="")
            if made and k:
                last_made[k] = e["actionNumber"]
        elif p.get("shootingPlay"):
            v = int(to_float(p.get("pointsAttempted")) or to_float(p.get("scoreValue")) or 2)
            if v not in (2, 3):
                v = 3 if "three point" in str(p.get("text") or "").lower() else 2
            at = "3pt" if v == 3 else "2pt"
            e = add(at, k, pid, base, success=1 if made else 0, subType=tt)
            xy = _real_xy(p.get("coordinate"))
            if xy and k:
                tm[k]["shot"].append({"x": xy[0], "y": xy[1], "r": e["success"], "actionNumber": e["actionNumber"],
                                      "actionType": at})
            if made and k:
                last_made[k] = e["actionNumber"]
                if len(parts) > 1:                  # participants = [anotador, asistente]
                    add("assist", k, parts[1], base, success=0, subType="", previousAction=e["actionNumber"])
            elif pid and k:
                last_miss[k] = pid
        elif tt in ("Offensive Rebound", "Defensive Rebound"):
            e = add("rebound", k, pid, base, success=0, subType="offensive" if tt.startswith("Off") else "defensive")
            if not pid:
                e["qualifier"] = ["team"]
        elif tt == "Substitution" and pid:
            txt = str(p.get("text") or "").lower()
            sub = "in" if "subbing in" in txt else ("out" if "subbing out" in txt else None)
            if sub:
                add("substitution", k, pid, base, success=0, subType=sub)
        elif "turnover" in tt.lower():
            add("turnover", k, pid, base, success=0, subType=tt)
        elif tt == "Steal":
            add("steal", k, pid, base, success=0, subType="")
        elif tt == "Block Shot":
            add("block", k, pid, base, success=0, subType="")
            if k:
                victim = last_miss.get("2" if k == "1" else "1")
                if victim:
                    blocked[victim] = blocked.get(victim, 0) + 1
        elif "foul" in tt.lower():
            add("foul", k, pid, base, success=0, subType=tt)
        elif tt == "Jumpball":
            add("jumpball", k, pid, base, success=0, subType="")
        elif "timeout" in tt.lower().replace(" ", ""):
            add("timeout", k, None, base, success=0, subType=tt)
        elif tt == "End Period":
            add("period", None, None, base, success=0, subType="end")
        elif tt == "End Game":
            add("game", None, None, base, success=0, subType="end")
    if plays:
        for pid, (k, n) in pno.items():
            tm[k]["pl"][n]["sBlocksReceived"] = blocked.get(pid, 0)
    pbp.reverse()                       # FIBA LiveStats: orden descendente de actionNumber
    status = ((comp.get("status") or {}).get("type") or {})
    return {"tm": tm, "pbp": pbp, "status": "complete" if status.get("completed") else str(status.get("name") or ""),
            "matchDate": comp.get("date"), "period": None}


def top50_ids(sc: dict) -> list[str]:
    return [str(t["espn_id"]) for t in sc.get("top50") or [] if t.get("espn_id")]


class NCAAAdapter(FibaLiveStatsAdapter):
    """Partidos del top-50 de la temporada en la API de ESPN; parse = boxscores de FIBA LiveStats sobre la
    traducción `to_fls`.

    Config por temporada: `top50` [{espn_id, nombre, rank}] (obligatorio), `sin_datos` + `motivo` (temporada
    sin partidos: NoDataYet sin peticiones), `fecha_corte` "AAAA-MM-DD" (opcional)."""
    name = "ncaa"
    version = "1.0"

    def _get(self, http: HttpClient, url: str) -> Any:
        return http.get(url).json()

    def fetch(self, season: str, http: HttpClient, previous_payload: Any | None = None) -> Any:
        sc = self.season_cfg(season)
        if sc.get("sin_datos"):
            raise NoDataYet(f"ncaa {season}: {sc.get('motivo') or 'sin partidos todavía'}")
        top = top50_ids(sc)
        if not top:
            raise AdapterError(f"ncaa {season}: falta temporadas.{season}.top50 en la config")
        year = espn_year(season)
        corte = str(sc.get("fecha_corte") or self.cfg.get("fecha_corte") or "9999")
        prev = previous_payload if isinstance(previous_payload, dict) else {}
        prev_games, prev_eq = prev.get("games") or {}, prev.get("equipos") or {}
        fases, fechas, notas = {}, {}, {}
        for tid in top:
            for st in (2, 3):
                try:
                    cal = self._get(http, SCHED_URL.format(tid=tid, year=year, st=st))
                except (FetchError, ValueError) as exc:
                    self.soft_fail(f"calendario {tid} st={st}: {exc}")
                    continue
                for e in cal.get("events") or []:
                    c = (e.get("competitions") or [{}])[0]
                    if not ((c.get("status") or {}).get("type") or {}).get("completed"):
                        continue
                    if str(e.get("date") or "")[:10] > corte:
                        continue
                    nt = " | ".join(n.get("headline") or "" for n in c.get("notes") or [])
                    ph = phase_of(((e.get("seasonType") or {}).get("type")) or st, nt)
                    if ph is None:
                        continue
                    gid = str(e["id"])
                    fases[gid], fechas[gid], notas[gid] = ph, e.get("date"), nt
        if not fases:
            raise NoDataYet(f"ncaa {season}: aún no hay partidos terminados del top-50")
        equipos = {}
        for tid in top:
            if tid in prev_eq and not sc.get("en_curso"):
                continue
            try:
                r = self._get(http, ROSTER_URL.format(tid=tid, year=year))
            except (FetchError, ValueError) as exc:
                self.soft_fail(f"plantilla {tid}: {exc}")
                continue
            equipos[tid] = {"coach": r.get("coach"), "season": r.get("season"),
                            "team": {k: (r.get("team") or {}).get(k) for k in ("id", "displayName", "abbreviation")},
                            "athletes": [{k: a.get(k) for k in ("id", "displayName", "height", "weight", "jersey")}
                                         for a in r.get("athletes") or []]}
        block = int(self.cfg.get("partidos_por_paquete", 400))
        keys = ["games", "fechas", "fases", "notas", "equipos"]
        new, n_new, reused = {}, 0, 0
        for gid in sorted(fases, key=lambda g: fechas[g] or ""):
            if fases[gid] == "excluida":
                continue
            if gid in prev_games and _is_final(to_fls(prev_games[gid])):
                reused += 1
                continue
            try:
                d = self._get(http, SUMMARY_URL.format(gid=gid))
            except (FetchError, ValueError) as exc:
                self.soft_fail(f"{gid}: {exc}")
                continue
            if not isinstance(d, dict) or not d.get("boxscore"):
                self.soft_fail(f"{gid}: summary sin boxscore")
                continue
            new[gid] = {k: d.get(k) for k in CLAVES}
            n_new += 1
            if len(new) >= block:
                self.save_partial(season, {"claves_incrementales": keys, "fases": fases, "fechas": fechas,
                                           "notas": notas, "equipos": equipos, "top50": top, "games": new})
                new, equipos = {}, {}
        return {"incremental": True, "claves_incrementales": keys, "fases": fases, "fechas": fechas, "notas": notas,
                "equipos": equipos, "top50": top, "games": new, "reused_games": reused, "partidos_nuevos": n_new}

    def parse(self, payload: Any, season: str):
        top = set(top50_ids(self.season_cfg(season)) or payload.get("top50") or [])
        fases = payload.get("fases") or {}
        rosters = payload.get("equipos") or {}
        games, sin_fase = [], 0
        for gid in sorted(payload.get("games") or {}, key=lambda g: (payload.get("fechas") or {}).get(g) or ""):
            raw = payload["games"][gid]
            ph = fases.get(gid)
            if not isinstance(raw, dict) or ph not in ("regular", "playoffs"):
                sin_fase += ph is None
                continue
            doc = to_fls(raw, rosters)
            tm = doc["tm"]
            teams = tuple((tm[k]["teamId"], tm[k]["name"]) if k in tm else None for k in ("1", "2"))
            g = parse_fiba_game(gid, doc, ph, teams)
            g["date"] = (payload.get("fechas") or {}).get(gid) or g.get("date")
            games.append(g)
        if not games:
            raise AdapterError("ncaa: el bruto no contiene partidos")
        n_both = sum(1 for g in games if all(s["team_id"] in top for s in g["teams"]))
        out = aggregate_by_phase(games, [f"{len(games)} partidos ESPN de equipos top-50 ({n_both} entre dos top-50); "
                                         f"filas sólo de los {len(top)} equipos top-50 (rivales en opp_*); "
                                         f"{payload.get('reused_games', 0)} reutilizados"])
        for pl in out.values():          # sólo jugadores y equipos del top-50 (los rivales ya están en opp_*)
            pl.players = [p for p in pl.players if p["team_id"] in top]
            pl.teams = [t for t in pl.teams if t["team_id"] in top]
        return out
