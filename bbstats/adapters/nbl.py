"""NBL (Australia) — API pública de nbl.com.au (la que usa su web), partido a partido.

    https://prod.rosetta.nbl.com.au/get/nbl/matches/in/season/<año>?limit=500   calendario de la temporada
    https://prod.rosetta.nbl.com.au/get/match/<uuid>/live/all                   partido: boxscore + jugada a jugada

<año> = año de inicio (NBL27 = 2026 = temporada 2026-27). El calendario da `match_type` (regular | final;
las «finals» incluyen el play-in) y `match_status`; los partidos de exhibición llegan sin `match_type` y quedan
fuera. La NBL Cup se juega dentro de la liga regular (cuenta como regular).

El partido trae el mismo modelo de datos que FIBA LiveStats (Genius Sports, proveedor de la liga): acciones
2pt/3pt/freeThrow/rebound/assist/turnover/steal/block/foul/substitution con persona, equipo, periodo, reloj
restante y coordenadas x/y en % de la pista completa. Este adaptador lo traduce al formato del data.json de
FIBA LiveStats (`to_fls`) y reutiliza íntegro el adaptador y el jugada a jugada de la BSL/GBL; los ids de
jugador son los `player.id` de la NBL (estables entre temporadas) y los de equipo los `team.id`.

Bruto: de cada partido se guardan, sin transformar, sólo las claves con datos de juego (`CLAVES`); el resto
(imágenes, patrocinio, apuestas, retransmisión) se descarta (≈ 1,2 MB → 0,3 MB por partido).
Bruto INCREMENTAL: cada ejecución guarda sólo los partidos nuevos (como fiba_livestats).
"""
from __future__ import annotations

from typing import Any

from ..http import FetchError, HttpClient
from .base import AdapterError, NoDataYet
from .fiba_livestats import FibaLiveStatsAdapter, _is_final

LIST_URL = "https://prod.rosetta.nbl.com.au/get/nbl/matches/in/season/{year}?limit=500"
MATCH_URL = "https://prod.rosetta.nbl.com.au/get/match/{mid}/live/all"
HEADERS = {"Origin": "https://nbl.com.au", "Referer": "https://nbl.com.au/", "Accept": "*/*"}
CLAVES = ("id", "external_id", "match_status", "match_type", "round", "start_time", "start_time_datetime",
          "home_score", "away_score", "current_period", "attendance", "season", "venue", "home_team", "away_team",
          "player_match_statistics", "team_match_statistics", "play_by_play")
FASE = {"regular": "regular", "final": "playoffs"}

# estadística de la NBL -> nombre del data.json de FIBA LiveStats (map_counting los entiende)
STAT = {"points": "sPoints", "field_goals_made": "sFieldGoalsMade", "field_goals_attempted": "sFieldGoalsAttempted",
        "two_points_made": "sTwoPointersMade", "two_points_attempted": "sTwoPointersAttempted",
        "three_points_made": "sThreePointersMade", "three_points_attempted": "sThreePointersAttempted",
        "free_throws_made": "sFreeThrowsMade", "free_throws_attempted": "sFreeThrowsAttempted",
        "offensive_rebounds": "sReboundsOffensive", "defensive_rebounds": "sReboundsDefensive",
        "rebounds": "sReboundsTotal", "assists": "sAssists", "steals": "sSteals", "blocks": "sBlocks",
        "turnovers": "sTurnovers", "personal_fouls": "sFoulsPersonal", "plus_minus": "sPlusMinusPoints"}
ACTION = {"2pt": "2pt", "3pt": "3pt", "freeThrow": "freethrow", "rebound": "rebound", "assist": "assist",
          "turnover": "turnover", "steal": "steal", "block": "block", "substitution": "substitution",
          "jumpBall": "jumpball", "timeOut": "timeout", "period": "period"}


def _id(x: Any) -> str | None:
    return str(x.get("id")) if isinstance(x, dict) and x.get("id") else None


def _minutes(v: Any) -> str | None:
    """'37:26' se deja; minutos decimales (algunas temporadas) -> 'MM:SS'."""
    if v is None or v == "":
        return None
    s = str(v)
    if ":" in s:
        return s
    try:
        sec = round(float(s) * 60)
    except ValueError:
        return None
    return f"{sec // 60}:{sec % 60:02d}"


def to_fls(doc: dict) -> dict:
    """Partido de la NBL -> estructura del data.json de FIBA LiveStats (tm, pbp, shot)."""
    home, away = doc.get("home_team") or {}, doc.get("away_team") or {}
    side = {_id(home): "1", _id(away): "2"}
    tm: dict[str, dict] = {}
    for k, t, sc in (("1", home, doc.get("home_score")), ("2", away, doc.get("away_score"))):
        tm[k] = {"name": t.get("name") or t.get("external_team_name"), "code": t.get("team_code"),
                 "score": sc, "pl": {}, "shot": []}
    pno: dict[str, tuple[str, str]] = {}
    for ps in doc.get("player_match_statistics") or []:
        if str(ps.get("period") or "0") not in ("0", "") or not isinstance(ps.get("player"), dict):
            continue
        k = side.get(_id(ps.get("team")))
        if k is None:
            continue
        p = ps["player"]
        pid = str(p.get("id"))
        n = str(len(tm[k]["pl"]) + 1)
        pno[pid] = (k, n)
        line = {"personId": pid, "firstName": p.get("first_name") or "", "familyName": p.get("last_name") or "",
                "name": p.get("full_name"), "shirtNumber": ps.get("jersey_number") or p.get("jersey_number"),
                "playingPosition": ps.get("playing_position") or p.get("playing_position"),
                "starter": 1 if ps.get("starter") else 0, "sMinutes": _minutes(ps.get("minutes"))}
        for a, b in STAT.items():
            if ps.get(a) is not None:
                line[b] = ps[a]
        tm[k]["pl"][n] = line
    for ts in doc.get("team_match_statistics") or []:
        k = side.get(_id(ts.get("team")))
        if k is None or str(ts.get("period") or "0") not in ("0", ""):
            continue
        for a, b in STAT.items():
            if ts.get(a) is not None and a != "plus_minus":
                tm[k]["tot_" + b] = ts[a]
    # orden del fichero = orden real de las acciones (action_id NO lo es: los cambios y las acciones del mismo
    # instante se numeran fuera de orden; ordenar por él deja jugadores «actuando fuera de pista»)
    acts = [a for a in doc.get("play_by_play") or [] if isinstance(a, dict)]
    pbp, last_made, last_miss = [], {}, {}
    drawn, blocked = {}, {}               # faltas recibidas y tapones recibidos (no vienen en la caja)
    for a in acts:
        at = a.get("action_type")
        sub = str(a.get("sub_type") or "")
        if at == "foul":
            at2 = "foulon" if sub.lower() == "drawn" else "foul"
        else:
            at2 = ACTION.get(at)
        if at2 is None:
            continue
        pid = str(a.get("personId") or _id(a.get("player")) or "")
        k = side.get(_id(a.get("team")))
        if k is None and pid in pno:
            k = pno[pid][0]
        n = pno.get(pid, (k, "0"))[1] if pid else "0"
        per = int(a.get("period") or 1)
        ot = str(a.get("period_type") or "").lower().startswith("over")
        e = {"actionNumber": len(pbp) + 1, "actionType": at2,
             "subType": sub.lower() if at2 in ("rebound", "substitution") else sub,
             "success": 1 if a.get("success") else 0, "tno": int(k) if k else 0, "pno": int(n),
             "period": per - 4 if ot and per > 4 else per, "periodType": "OVERTIME" if ot else "REGULAR",
             "gt": a.get("clock") or "00:00", "s1": a.get("score_1"), "s2": a.get("score_2")}
        if at2 == "rebound" and n == "0":
            e["qualifier"] = ["team"]
        if at2 in ("2pt", "3pt", "freethrow") and e["success"] and k:
            last_made[k] = e["actionNumber"]
        if at2 in ("2pt", "3pt") and not e["success"] and pid:
            last_miss[k] = pid
        if at2 == "foulon" and pid:
            drawn[pid] = drawn.get(pid, 0) + 1
        if at2 == "block" and k:
            victim = last_miss.get("2" if k == "1" else "1")
            if victim:
                blocked[victim] = blocked.get(victim, 0) + 1
        if at2 == "assist" and k:
            e["previousAction"] = last_made.get(k)       # la asistencia sigue a la canasta que la origina
        xy = a.get("coordinates") or {}
        if at2 in ("2pt", "3pt") and k and xy.get("x") is not None:
            tm[k]["shot"].append({"x": xy.get("x"), "y": xy.get("y"), "r": e["success"],
                                  "actionNumber": e["actionNumber"], "actionType": at2})
        pbp.append(e)
    for pid, (k, n) in pno.items():
        if acts:
            tm[k]["pl"][n]["sFoulsOn"] = drawn.get(pid, 0)
            tm[k]["pl"][n]["sBlocksReceived"] = blocked.get(pid, 0)
    pbp.reverse()                       # FIBA LiveStats: orden descendente de actionNumber
    status = str(doc.get("match_status") or "").lower()
    return {"tm": tm, "pbp": pbp, "status": "complete" if status == "complete" else status,
            "matchDate": doc.get("start_time"), "period": doc.get("current_period")}


class NBLAdapter(FibaLiveStatsAdapter):
    """Calendario y partidos de nbl.com.au; parse = el de FIBA LiveStats sobre la traducción `to_fls`.

    Config: `fecha_corte` (opcional, global o por temporada, "AAAA-MM-DD"): sólo partidos con inicio hasta ese
    día (UTC), incluido."""
    name = "nbl"
    version = "1.0"

    def _get(self, http: HttpClient, url: str) -> Any:
        resp = http.get(url, headers=HEADERS)
        return resp.json()

    def fetch(self, season: str, http: HttpClient, previous_payload: Any | None = None) -> Any:
        sc = self.season_cfg(season)
        corte = str(sc.get("fecha_corte") or self.cfg.get("fecha_corte") or "9999")
        prev = (previous_payload or {}).get("games", {}) if isinstance(previous_payload, dict) else {}
        try:
            cal = self._get(http, LIST_URL.format(year=sc["start_year"]))
        except (FetchError, ValueError) as exc:
            raise AdapterError(f"nbl {season}: calendario no disponible ({exc})") from exc
        fases, fechas = {}, {}
        for m in cal.get("data") or []:
            ph = FASE.get(str(m.get("match_type") or "").lower())
            if ph is None or str(m.get("match_status") or "").lower() != "complete":
                continue
            if str(m.get("start_time") or "")[:10] > corte:
                continue
            fases[str(m["id"])], fechas[str(m["id"])] = ph, m.get("start_time")
        if not fases:
            raise NoDataYet(f"nbl {season}: aún no hay partidos terminados")
        new, n_new, reused = {}, 0, 0
        for mid in sorted(fases, key=lambda i: fechas[i] or ""):
            if mid in prev and _is_final(to_fls(prev[mid])):
                reused += 1
                continue
            try:
                r = self._get(http, MATCH_URL.format(mid=mid))
            except (FetchError, ValueError) as exc:
                self.soft_fail(f"{mid}: {exc}")
                continue
            d = r.get("data") if isinstance(r, dict) else None
            d = d[0] if isinstance(d, list) and d else d
            if not isinstance(d, dict):
                continue
            new[mid] = {k: d.get(k) for k in CLAVES}
            n_new += 1
            if len(new) >= int(self.cfg.get("partidos_por_paquete", 400)):
                self.save_partial(season, {"claves_incrementales": ["games", "fechas"], "fases": fases,
                                           "fechas": fechas, "games": new})
                new = {}
        return {"incremental": True, "claves_incrementales": ["games", "fechas"], "fases": fases,
                "fechas": fechas, "games": new, "reused_games": reused, "partidos_nuevos": n_new}

    def parse(self, payload: Any, season: str):
        games = {k: to_fls(v) for k, v in (payload.get("games") or {}).items() if isinstance(v, dict)}
        return super().parse({**payload, "games": games}, season)
