"""VTB United League (Rusia): Infobasket (org.infobasket.su), el backend que usa vtb-league.com, partido a partido.

    https://org.infobasket.su/Comp/GetSeasonsForTag?tag=vtb                 temporadas -> CompID
    https://org.infobasket.su/Widget/CompIssue/<CompID>?format=json         árbol de fases (Children)
    https://org.infobasket.su/Comp/GetCalendar/?comps=<CompID>&format=json  calendario de una fase
    https://org.infobasket.su/Widget/GetOnline/<GameID>?format=json&lang=en partido: boxscore + jugada a jugada

Fases: los hijos directos de la temporada en CompIssue. Los nodos CompType 10 (Playoff, Play-in) son "playoffs"
(el play-in cuenta como playoffs, igual que en la EuroLeague): cuartos, semifinales, final y tercer puesto. El
resto (Round Robin / Regular season / First stage / Second stage) es la regular. "Final standing" no tiene
partidos. La Copa (WINLINE Basket Cup) y la Supercopa son otro tag de Infobasket y no aparecen aquí.
Si CompIssue falla, se pide el calendario de la temporada entera y la fase se deduce del nombre (CompNameEn).

El partido (GetOnline) trae:
  GameTeams[2]   totales, Players[] (PersonID, nombres En/Ru, Seconds, Goal/Shot 1-2-3, Off/DefRebound, Assist,
                 Steal, Blocks, Turnover, Foul, OpponentFoul, PlusMinus, IsStart; null = 0) y Coaches[] (principal =
                 PosID 1000; el campo Coach a veces es un ayudante)
  OnlineStarts[] StartID -> TeamNumber, StartType (1 jugador, 3 entrenador, 0 equipo, 4 oficial), PersonID
  OnlinePlays[]  PlayID, PlayPeriod, PlaySecond (DÉCIMAS transcurridas del periodo), StartID, ParentPlayID,
                 PlayTypeID, PlayX/PlayY (dm desde el aro atacado: X lateral, Y hacia el centro), SysStatus
                 Cada jugada «madre» (tiro, falta, pérdida, cambio, inicio/fin de periodo) lleva sus hijas
                 (asistencia, rebote, tapón, robo, entradas/salidas, tiros libres concedidos) con el mismo
                 instante, ordenadas por PlaySortOrder.
2020-21 y 2021-22 hasta el 07-03-2022 no tienen OnlinePlays (sólo boxscore).

Este adaptador lo traduce al formato del data.json de FIBA LiveStats (`to_fls`) y reutiliza íntegro el
adaptador y el jugada a jugada de la BSL/GBL. Los ids de jugador son los PersonID de Infobasket (estables entre
temporadas). Los nombres van en alfabeto latino (lang=en) y los equipos en inglés.

Bruto: de cada partido se guardan, sin transformar, sólo las claves con datos de juego (`CLAVES`); vídeo,
televisión y uniformes se descartan. Bruto INCREMENTAL: cada ejecución guarda sólo los partidos nuevos.
"""
from __future__ import annotations

import math
import re
from typing import Any

from ..http import FetchError, HttpClient
from .base import AdapterError, NoDataYet
from .fiba_livestats import FibaLiveStatsAdapter, _is_final

API = "https://org.infobasket.su"
SEASONS_URL = API + "/Comp/GetSeasonsForTag?tag={tag}"
ISSUE_URL = API + "/Widget/CompIssue/{comp}?format=json"
CAL_URL = API + "/Comp/GetCalendar/?comps={comp}&format=json"
GAME_URL = API + "/Widget/GetOnline/{gid}?format=json&lang=en"
HEADERS = {"Origin": "https://vtb-league.com", "Referer": "https://vtb-league.com/", "Accept": "application/json"}
CLAVES = ("GameStatus", "MaxPeriod", "GameDate", "GameTime", "GameTimeMsk", "IsOnline", "Online", "OnlineStarts",
          "OnlinePlays", "OnlinePeriods", "GameTeams", "CompID", "LeagueID", "CompNameRu", "CompNameEn",
          "LeagueNameEn")

# Infobasket (GameTeams.Players / GameTeams) -> data.json de FIBA LiveStats (map_counting los entiende)
STAT = {"Points": "sPoints", "Goal2": "sTwoPointersMade", "Shot2": "sTwoPointersAttempted",
        "Goal3": "sThreePointersMade", "Shot3": "sThreePointersAttempted", "Goal1": "sFreeThrowsMade",
        "Shot1": "sFreeThrowsAttempted", "OffRebound": "sReboundsOffensive", "DefRebound": "sReboundsDefensive",
        "Rebound": "sReboundsTotal", "Assist": "sAssists", "Steal": "sSteals", "Blocks": "sBlocks",
        "Turnover": "sTurnovers", "Foul": "sFoulsPersonal", "OpponentFoul": "sFoulsOn"}

# PlayTypeID (tabla del widget de vtb-league.com, assets/rfb/widgets.bundle.min.js)
MADE = {1: "freethrow", 2: "2pt", 3: "3pt"}
MISS = {4: "freethrow", 5: "2pt", 6: "3pt"}
SUB, IN, OUT, START, FINISH, TIMEOUT = 7, 8, 9, 21, 22, 23
TURNOVER = {10: "", 11: "badpass", 12: "travel", 13: "outofbounds", 14: "backcourt", 15: "doubledribble",
            16: "3sec", 17: "5sec", 18: "8sec", 19: "shotclock", 20: "ballhandling"}
ASSIST, STEAL, BLOCK, REBOUND = 25, 26, 27, 28
FOUL = {40: "personal", 41: "unsportsmanlike", 42: "technical", 43: "disqualifying", 44: "coachTechnical",
        45: "benchTechnical", 46: "fighting"}
OFFENSIVE = 47                       # hija de una falta: falta en ataque
AWARD = {50, 51, 52, 53}             # hija de una falta: saque / 1, 2 o 3 tiros libres (StartID = el que la recibe)
DRAWN_FROM = {40, 41, 43}            # faltas con jugador objeto de la falta (las técnicas no)
REGULAR_PHASE = re.compile(r"round robin|regular|stage|этап|регуляр", re.IGNORECASE)


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _mmss(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 60:02d}:{sec % 60:02d}"


def _phase_by_name(name: str | None) -> str:
    return "regular" if REGULAR_PHASE.search(str(name or "")) else "playoffs"


def _date(g: dict) -> str | None:
    """'28.09.2025' -> '2025-09-28'."""
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", str(g.get("GameDate") or ""))
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def _name(p: dict) -> tuple[str, str]:
    return (p.get("FirstNameEn") or p.get("FirstNameRu") or "").strip(), \
           (p.get("LastNameEn") or p.get("LastNameRu") or "").strip()


def _head_coach(t: dict) -> dict:
    """Entrenador principal: el de Coaches con PosID 1000 (los ayudantes llevan 1001) o, si no, el número 1.
    El campo `Coach` NO sirve: en algunos partidos trae a un ayudante."""
    cs = [c for c in t.get("Coaches") or [] if isinstance(c, dict)]
    for c in cs:
        if _int(c.get("PosID")) == 1000:
            return c
    for c in cs:
        if _int(c.get("PlayerNumber")) == 1:
            return c
    return t.get("Coach") or (cs[0] if cs else {})


def _ordered(plays: list[dict], subs_after: bool = False) -> list[dict]:
    """Orden real: jugadas madre por (periodo, instante, PlayID), cada una seguida de sus hijas por PlaySortOrder.
    (El PlayID es el orden de anotación: dentro del mismo instante es el orden real -falta, 1.er TL, cambio,
    2.º TL-; entre instantes no lo es del todo, porque las correcciones del reloj se anotan después.)"""
    plays = [p for p in plays if isinstance(p, dict) and _int(p.get("SysStatus"), 1) == 1]
    ids = {p.get("PlayID") for p in plays}
    kids: dict[Any, list[dict]] = {}
    roots = []
    for p in plays:
        par = p.get("ParentPlayID")
        if par is not None and par in ids:
            kids.setdefault(par, []).append(p)
        else:
            roots.append(p)
    roots.sort(key=lambda p: (_int(p.get("PlayPeriod")), _int(p.get("PlaySecond")), _int(p.get("PlayID"))))
    if subs_after:
        roots = _subs_after_actions(roots, kids)
    out = []
    for r in roots:
        out.append(r)
        out.extend(sorted(kids.get(r.get("PlayID"), []),
                          key=lambda p: (_int(p.get("PlaySortOrder")), _int(p.get("PlayID")))))
    return out


def _subs_after_actions(roots: list[dict], kids: dict) -> list[dict]:
    """Dentro de un mismo instante, un cambio anotado ANTES de una acción del jugador que sale (típico: el
    cambio se teclea antes de los tiros libres que aún lanza el que sale) se mueve detrás de su última acción en
    ese instante. Si no, ese jugador quedaría «actuando fuera de pista»."""
    def actors(r: dict) -> set:
        return {r.get("StartID")} | {c.get("StartID") for c in kids.get(r.get("PlayID"), [])}

    out: list[dict] = []
    i = 0
    while i < len(roots):
        j = i
        inst = (roots[i].get("PlayPeriod"), roots[i].get("PlaySecond"))
        while j < len(roots) and (roots[j].get("PlayPeriod"), roots[j].get("PlaySecond")) == inst:
            j += 1
        grp = roots[i:j]
        for _ in range(len(grp)):
            moved = False
            for a, r in enumerate(grp):
                if _int(r.get("PlayTypeID")) != SUB:
                    continue
                outs = {c.get("StartID") for c in kids.get(r.get("PlayID"), []) if _int(c.get("PlayTypeID")) == OUT}
                last = None
                for b in range(a + 1, len(grp)):
                    if _int(grp[b].get("PlayTypeID")) == SUB:
                        if outs & {c.get("StartID") for c in kids.get(grp[b].get("PlayID"), [])}:
                            break           # vuelve a entrar o salir en este instante: no tocar
                        continue
                    if outs & actors(grp[b]):
                        last = b
                if last is not None:
                    grp.insert(last, grp.pop(a))
                    moved = True
                    break
            if not moved:
                break
        out.extend(grp)
        i = j
    return out


def to_fls(doc: dict, cambios_tras_acciones: bool = False) -> dict:
    """Partido de Infobasket (GetOnline) -> estructura del data.json de FIBA LiveStats (tm, pbp, shot).

    Orden de las acciones: el de anotación (ver `_ordered`). El anotador suele teclear el cambio ANTES de los
    tiros libres que todavía lanza el jugador que sale; el +/- oficial de Infobasket sigue ese orden (los puntos
    de esos tiros libres cuentan para el quinteto que entra), así que por defecto se respeta y el lanzador sale
    como «actua_fuera_de_pista» en la validación de quintetos. Con `cambios_tras_acciones` (config de la liga:
    "cambios_tras_acciones": true) ese cambio se mueve detrás de las acciones del que sale en el mismo instante:
    desaparecen esas anomalías pero el +/- deja de cuadrar con el oficial en ±1-2 puntos."""
    teams = {str(_int(t.get("TeamNumber"))): t for t in doc.get("GameTeams") or [] if isinstance(t, dict)}
    tm: dict[str, dict] = {}
    pno: dict[int, tuple[str, str]] = {}               # PersonID -> (lado, pno)
    for k in ("1", "2"):
        t = teams.get(k) or {}
        tn = t.get("TeamName") or {}
        c = _head_coach(t)
        cf, cl = _name(c)
        assist = [" ".join(_name(x)).strip() for x in t.get("Coaches") or []
                  if isinstance(x, dict) and x.get("PersonID") != c.get("PersonID")]
        tm[k] = {"name": tn.get("CompTeamNameEn") or tn.get("CompTeamNameRu"),
                 "nameInternational": tn.get("CompTeamNameEn"), "shortName": tn.get("CompTeamShortNameEn"),
                 "code": tn.get("CompTeamAbcNameEn"), "teamId": t.get("TeamID"), "score": t.get("Score"),
                 "coach": f"{cf} {cl}".strip() or None,
                 "coachDetails": ({"firstName": cf, "familyName": cl, "internationalFirstName": cf,
                                   "internationalFamilyName": cl, "personId": c.get("PersonID")} if c else {}),
                 "assistcoach1": assist[0] if assist else None, "assistcoach2": assist[1] if len(assist) > 1 else None,
                 "pl": {}, "shot": []}
        players = [p for p in t.get("Players") or [] if isinstance(p, dict)]
        has_pm = any(p.get("PlusMinus") is not None for p in players)
        for p in players:
            n = str(len(tm[k]["pl"]) + 1)
            pid = _int(p.get("PersonID"))
            pno[pid] = (k, n)
            first, last = _name(p)
            sec = _int(p.get("Seconds"))
            line = {"personId": str(pid), "firstName": first, "familyName": last,
                    "name": f"{first} {last}".strip(), "shirtNumber": p.get("DisplayNumber"),
                    "playingPosition": None, "starter": 1 if p.get("IsStart") else 0,
                    "height": p.get("Height"), "sMinutes": _mmss(sec)}
            for a, b in STAT.items():
                line[b] = p.get(a) or 0
            line["sFieldGoalsMade"] = line["sTwoPointersMade"] + line["sThreePointersMade"]
            line["sFieldGoalsAttempted"] = line["sTwoPointersAttempted"] + line["sThreePointersAttempted"]
            if has_pm:
                line["sPlusMinusPoints"] = p.get("PlusMinus") or 0
            tm[k]["pl"][n] = line
        for a, b in STAT.items():
            if t.get(a) is not None:
                tm[k]["tot_" + b] = t[a]
        if t:
            tm[k]["tot_sFieldGoalsMade"] = (t.get("Goal2") or 0) + (t.get("Goal3") or 0)
            tm[k]["tot_sFieldGoalsAttempted"] = (t.get("Shot2") or 0) + (t.get("Shot3") or 0)
            tm[k]["tot_sReboundsTeamOffensive"] = t.get("TeamOffRebound") or 0
            tm[k]["tot_sReboundsTeamDefensive"] = t.get("TeamDefRebound") or 0
            tm[k]["tot_sTurnoversTeam"] = t.get("TeamTurnover") or 0

    starts = {s.get("StartID"): s for s in doc.get("OnlineStarts") or [] if isinstance(s, dict)}

    def who(play: dict) -> tuple[str | None, int, int]:
        """(lado, pno, PersonID) del StartID de la jugada; pno 0 = equipo / entrenador."""
        s = starts.get(play.get("StartID")) or {}
        k = str(_int(s.get("TeamNumber")))
        k = k if k in ("1", "2") else None
        pid = _int(s.get("PersonID"))
        if _int(s.get("StartType")) == 1 and pid in pno:
            k2, n = pno[pid]
            return k2, int(n), pid
        return k, 0, 0

    lens = {_int(p.get("Period")): _int(p.get("Seconds")) for p in doc.get("OnlinePeriods") or []
            if isinstance(p, dict)}
    plays = _ordered(doc.get("OnlinePlays") or [], cambios_tras_acciones)
    by_id = {p.get("PlayID"): p for p in plays}
    kids: dict[Any, list[dict]] = {}
    for p in plays:
        if p.get("ParentPlayID") is not None:
            kids.setdefault(p.get("ParentPlayID"), []).append(p)
    first_five: dict[str, set] = {}
    pbp: list[dict] = []
    score = {"1": 0, "2": 0}
    on: dict[str, set] = {"1": set(), "2": set()}       # en pista (pno), para los cambios entre periodos
    blocked: dict[int, int] = {}
    last_made: dict[str, int] = {}
    pending_ast: dict[str, list[tuple[dict, int]]] = {"1": [], "2": []}   # asistencias a tiros libres

    def add(play: dict, at: str, sub: str = "", k: str | None = None, n: int = 0, **kw) -> dict:
        per = _int(play.get("PlayPeriod"), 1)
        ot = per > 4
        length = lens.get(per) or (300 if ot else 600)
        rem = math.ceil(max(0.0, length - _int(play.get("PlaySecond")) / 10.0) - 1e-9)
        e = {"actionNumber": len(pbp) + 1, "actionType": at, "subType": sub, "success": kw.pop("success", 0),
             "tno": int(k) if k else 0, "pno": n, "period": per - 4 if ot else per,
             "periodType": "OVERTIME" if ot else "REGULAR", "gt": _mmss(rem),
             "s1": score["1"], "s2": score["2"], **kw}
        pbp.append(e)
        return e

    for p in plays:
        tid = _int(p.get("PlayTypeID"))
        k, n, pid = who(p)
        parent = by_id.get(p.get("ParentPlayID")) if p.get("ParentPlayID") is not None else None
        ptid = _int(parent.get("PlayTypeID")) if parent else None
        if tid in MADE or tid in MISS:
            at = MADE.get(tid) or MISS[tid]
            made = tid in MADE
            if made and k:
                score[k] += tid
            e = add(p, at, "", k, n, success=1 if made else 0)
            if made and k:
                last_made[k] = e["actionNumber"]
                inst = (p.get("PlayPeriod"), p.get("PlaySecond"))
                pend = [x for x in pending_ast[k] if x[0] == inst]
                pending_ast[k] = []
                if at == "freethrow" and pend and pend[0][1]["pno"] != n:
                    pend[0][1]["previousAction"] = e["actionNumber"]
            x, y = p.get("PlayX"), p.get("PlayY")
            if at != "freethrow" and k and x is not None and y is not None:
                # dm desde el aro (X lateral, Y hacia el centro) -> % de la pista completa (28 x 15 m), todos
                # los tiros hacia el aro de la izquierda (Infobasket no dice en qué canasta se tiró)
                tm[k]["shot"].append({"x": round((15.75 + float(y)) * 100 / 280, 2),
                                      "y": round(50 + float(x) / 1.5, 2), "r": e["success"],
                                      "actionNumber": e["actionNumber"], "actionType": at,
                                      "tno": int(k), "pno": n, "per": e["period"], "perType": e["periodType"]})
        elif tid == ASSIST and parent is not None and k and n:
            if ptid in (2, 3):
                add(p, "assist", "", k, n, previousAction=last_made.get(k))
            elif ptid in DRAWN_FROM:
                # pase que acaba en falta: la caja lo cuenta como asistencia si se anota algún tiro libre de esa
                # falta (FIBA LiveStats: assist -> freethrow). Las «asistencias» colgadas de un tiro fallado no
                # cuentan en la caja.
                # (se anota en su sitio, junto a la falta, y se enlaza al tiro libre cuando llega; sin tiro libre
                # anotado en ese instante, se descarta)
                pending_ast[k].append(((p.get("PlayPeriod"), p.get("PlaySecond")),
                                       add(p, "assist", "", k, n, previousAction=None, _ft=True)))
        elif tid == REBOUND and parent is not None and k:
            sk, _, _ = who(parent)
            e = add(p, "rebound", "offensive" if sk == k else "defensive", k, n)
            if n == 0:
                e["qualifier"] = ["team"]
        elif tid == BLOCK and parent is not None and k:
            _, _, vic = who(parent)
            if vic:
                blocked[vic] = blocked.get(vic, 0) + 1
            add(p, "block", "", k, n)
        elif tid == STEAL and k:
            add(p, "steal", "", k, n)
        elif tid in TURNOVER and parent is None and k:
            add(p, "turnover", TURNOVER[tid], k, n)
        elif tid in FOUL and parent is None and k:
            offensive = any(_int(c.get("PlayTypeID")) == OFFENSIVE for c in kids.get(p.get("PlayID"), []))
            add(p, "foul", "offensive" if offensive and tid == 40 else FOUL[tid], k, n)
            if offensive and n:
                add(p, "turnover", "offensive", k, n)       # la caja cuenta la falta en ataque como pérdida
        elif tid in AWARD and ptid in DRAWN_FROM and n:
            add(p, "foulon", "", k, n)
        elif tid == TIMEOUT and parent is None and k:
            add(p, "timeout", "", k, 0)
        elif tid in (IN, OUT) and n and ptid == SUB:
            (on[k].add if tid == IN else on[k].discard)(n)
            add(p, "substitution", "in" if tid == IN else "out", k, n)
        elif tid == START and parent is None:
            # quinteto de salida del periodo (hijas In): cambios respecto a cómo acabó el anterior
            new = {"1": set(), "2": set()}
            for c in kids.get(p.get("PlayID"), []):
                if _int(c.get("PlayTypeID")) == IN:
                    ck, cn, _ = who(c)
                    if ck and cn:
                        new[ck].add(cn)
            add(p, "period", "start")
            if _int(p.get("PlayPeriod"), 1) > 1:
                for side in ("1", "2"):
                    if len(new[side]) != 5:
                        continue
                    for x in sorted(on[side] - new[side]):
                        add(p, "substitution", "out", side, x)
                    for x in sorted(new[side] - on[side]):
                        add(p, "substitution", "in", side, x)
            for side in ("1", "2"):
                if len(new[side]) == 5:
                    on[side] = new[side]
                    if _int(p.get("PlayPeriod"), 1) == 1:
                        first_five.setdefault(side, set(new[side]))
        elif tid == FINISH and parent is None:
            add(p, "period", "end")
    if plays:
        for k in ("1", "2"):
            for line in tm[k]["pl"].values():
                line["sBlocksReceived"] = blocked.get(_int(line["personId"]), 0)
            # titulares: IsStart si marca exactamente 5; si no, el quinteto de salida del jugada a jugada
            if sum(line["starter"] for line in tm[k]["pl"].values()) != 5 and len(first_five.get(k, ())) == 5:
                for n, line in tm[k]["pl"].items():
                    line["starter"] = 1 if int(n) in first_five[k] else 0
    # fuera las asistencias a tiro libre sin enlazar; renumeración consecutiva
    keep = [e for e in pbp if not (e.pop("_ft", False) and e.get("previousAction") is None)]
    num = {e["actionNumber"]: i for i, e in enumerate(keep, 1)}
    for e in keep:
        e["actionNumber"] = num[e["actionNumber"]]
        if e.get("previousAction") is not None:
            e["previousAction"] = num.get(e["previousAction"])
    for k in ("1", "2"):
        for sh in tm[k]["shot"]:
            sh["actionNumber"] = num.get(sh["actionNumber"])
    pbp = keep
    pbp.reverse()                       # FIBA LiveStats: orden descendente de actionNumber
    max_per = _int(doc.get("MaxPeriod"))
    return {"tm": tm, "pbp": pbp, "status": "complete" if _int(doc.get("GameStatus")) == 1 else "scheduled",
            "matchDate": _date(doc), "period": max_per - 4 if max_per > 4 else max_per,
            "periodType": "OVERTIME" if max_per > 4 else "REGULAR"}


class VTBAdapter(FibaLiveStatsAdapter):
    """Calendario y partidos de Infobasket; parse = el de FIBA LiveStats sobre la traducción `to_fls`.

    Config por temporada (`temporadas.<t>`): `comp_id` (CompID de Infobasket; si falta se busca con
    GetSeasonsForTag?tag=<tag>) y `fecha_corte` (opcional, también global, "AAAA-MM-DD"): sólo partidos jugados
    hasta ese día (hora de Moscú), incluido."""
    name = "vtb"
    version = "1.0"

    def _get(self, http: HttpClient, url: str) -> Any:
        return http.get(url, headers=HEADERS).json()

    def _comp_id(self, season: str, http: HttpClient) -> int:
        sc = self.season_cfg(season)
        if sc.get("comp_id"):
            return int(sc["comp_id"])
        rows = self._get(http, SEASONS_URL.format(tag=self.cfg.get("tag", "vtb")))
        for r in rows or []:
            if int(r.get("SeasonYear") or 0) == int(season[:4]) + 1:
                return int(r["CompID"])
        raise NoDataYet(f"vtb {season}: la temporada no está en Infobasket")

    def _phases(self, comp: int, http: HttpClient) -> list[tuple[int | None, str]]:
        """[(CompID, fase)] de los hijos directos de la temporada (None = calendario entero, fase por nombre)."""
        try:
            tree = self._get(http, ISSUE_URL.format(comp=comp))
            kids = [c for c in (tree or {}).get("Comps") or [] if isinstance(c, dict) and c.get("CompID")]
        except (FetchError, ValueError) as exc:
            self.soft_fail(f"CompIssue {comp}: {exc}; fases por el nombre de la subfase")
            kids = []
        if not kids:
            return [(None, "")]
        return [(int(c["CompID"]), "playoffs" if int(c.get("CompType") or 0) == 10 else "regular") for c in kids]

    def fetch(self, season: str, http: HttpClient, previous_payload: Any | None = None) -> Any:
        sc = self.season_cfg(season)
        corte = str(sc.get("fecha_corte") or self.cfg.get("fecha_corte") or "9999")
        prev = (previous_payload or {}).get("games", {}) if isinstance(previous_payload, dict) else {}
        try:
            comp = self._comp_id(season, http)
            fases, fechas, info = {}, {}, {}
            for cid, ph in self._phases(comp, http):
                cal = self._get(http, CAL_URL.format(comp=cid or comp))
                for g in cal or []:
                    gid = str(g.get("GameID") or "")
                    if not gid or _int(g.get("GameStatus")) != 1:
                        continue
                    d = _date(g)
                    if not d or d > corte:
                        continue
                    fases[gid] = ph or _phase_by_name(g.get("CompNameEn"))
                    fechas[gid] = d
                    info[gid] = {"subfase": g.get("CompNameEn"), "numero": g.get("GameNumber")}
        except (FetchError, ValueError) as exc:
            raise AdapterError(f"vtb {season}: calendario no disponible ({exc})") from exc
        if not fases:
            raise NoDataYet(f"vtb {season}: aún no hay partidos terminados")
        new, n_new, reused = {}, 0, 0
        block = int(self.cfg.get("partidos_por_paquete", 400))
        base = {"claves_incrementales": ["games", "fechas", "subfases"], "fases": fases}
        for gid in sorted(fases, key=lambda i: (fechas[i], int(i))):
            if gid in prev and _is_final(to_fls(prev[gid])):
                reused += 1
                continue
            try:
                d = self._get(http, GAME_URL.format(gid=gid))
            except (FetchError, ValueError) as exc:
                self.soft_fail(f"{gid}: {exc}")
                continue
            if not isinstance(d, dict) or not d.get("GameTeams"):
                self.soft_fail(f"{gid}: partido sin GameTeams")
                continue
            new[gid] = {k: d.get(k) for k in CLAVES}
            n_new += 1
            if len(new) >= block:
                self.save_partial(season, {**base, "fechas": {i: fechas[i] for i in new},
                                           "subfases": {i: info[i] for i in new}, "games": new})
                new = {}
        return {"incremental": True, **base, "comp_id": comp, "fechas": fechas, "subfases": info, "games": new,
                "reused_games": reused, "partidos_nuevos": n_new}

    def parse(self, payload: Any, season: str):
        mover = bool(self.cfg.get("cambios_tras_acciones"))
        games = {k: to_fls(v, mover) for k, v in (payload.get("games") or {}).items() if isinstance(v, dict)}
        return super().parse({**payload, "games": games}, season)
