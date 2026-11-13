"""Jugada a jugada de la Federación Vasca → eventos normalizados, boxscore por jugador y partido, tiros.

Todo nace del jugada a jugada (`getJsonWithMatchMoves`) de cada partido; el acta digital (`getJsonWithMatchStats`)
aporta lo que la cronología no tiene (titulares, valoración oficial, rebotes de equipo, coordenadas de tiro por
`eventUuid`) y sirve de CONTROL: cada conteo por jugador se compara con el acta (`validacion`).

Formato original de una jugada:
    {"idTeam": 12325 (id interno del equipo en el acta), "actorId": 186889, "actorName": "...", "actorShirtNumber": "20",
     "idMove": 97, "move": "Intento fallado de 2", "min": 9, "sec": 49 (reloj RESTANTE del periodo), "period": 1,
     "score": "0-0" (local-visitante tras la jugada), "teamAction": false, "timestamp": "20260411100150",
     "licenseId": 122651, "eventUuid": "..."}

Catálogo de acciones (idMove; textos del propio widget de la web): ver ACCIONES.

Heurísticas declaradas (no las publica la fuente, se derivan de la cronología):
  * posesión: cambia con canasta anotada (o último tiro libre anotado), rebote defensivo, pérdida/robo y fin de
    periodo; el rebote ofensivo la mantiene y marca «segunda oportunidad».
  * puntos tras pérdida: anotados en una posesión que empezó con una pérdida del rival.
  * contraataque: canasta anotada ≤ 8 s después de recuperar el balón (robo o rebote defensivo) o con la marca
    «Contraataque» de la mesa.
  * zonas de tiro: con las coordenadas del acta (porcentaje de una pista FIBA de 28 × 15 m; aro a 1,575 m de la
    línea de fondo): aro (< 1,25 m), pintura (zona restringida de 4,9 × 5,8 m), media distancia, triple de esquina
    (≤ 2,99 m desde la línea de fondo) y triple frontal.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from ..lineups.model import Event, Game

# ------------------------------------------------------------------------------------------ catálogo
FT_MADE = {92, 180}
FT_MISS = {96, 181}
FG2_MADE = {93, 95, 100}          # canasta de 2, palmeo dentro, mate
FG2_MISS = {97, 99, 533}          # fallo de 2, palmeo fuera, mate fuera
FG3_MADE = {94}
FG3_MISS = {98}
DUNK = {100}
OREB, DREB = {101}, {104}
BLK, BLKA = {102}, {105}
STL = {103}
TOV = {106}
AST = {107}
OFF_FOUL = {109}
FOUL_DRAWN = {110}
SUB_IN, SUB_OUT = {112}, {115}
TIMEOUT = {113, 118}
PERIOD_END = {116}
FASTBREAK_MARK = {117, 130, 131, 132, 133, 134, 135}
PERSONAL = {159, 160, 161, 162, 163, 164, 182, 531}
SHOOTING_FOUL = {160, 161, 162}
UNSPORTS = {165, 166, 167, 168, 169, 183}
DISQ = {170, 171, 184, 200, 548, 549, 550, 551, 563}
TECH = {172, 173, 174, 537, 538, 539}
ALTERC = {175, 552, 553, 554, 555, 556}
COACH_TECH = {176, 540, 541, 542, 543}
BENCH_TECH = {177, 544, 545, 546, 547, 559, 560, 561, 562}
JUMP_WON, JUMP_LOST = {178}, {179}
VIOLATION = {530}
PLAYER_FOULS = PERSONAL | OFF_FOUL | UNSPORTS | DISQ | TECH | ALTERC

ACCIONES = {
    92: "Canasta de 1", 93: "Canasta de 2", 94: "Canasta de 3", 95: "Palmeo Dentro", 96: "Intento fallado de 1",
    97: "Intento fallado de 2", 98: "Intento fallado de 3", 99: "Palmeo fuera", 100: "Mate", 101: "Rebote ofensivo",
    102: "Tapón", 103: "Recuperación", 104: "Rebote defensivo", 105: "Tapón recibido", 106: "Pérdida",
    107: "Asistencia", 109: "Falta en ataque", 110: "Falta recibida", 112: "Entra al campo", 113: "Tiempo muerto",
    114: "Marca de minuto", 115: "Sale del campo", 116: "Fin de período", 117: "Contrataque", 118: "Tiempo de TV",
    121: "Inicio de período", 122: "Inicio de partido", 123: "Fin de partido", 130: "Contraataque",
    159: "Personal", 160: "Personal 1 tiro libre", 161: "Personal 2 tiros libres", 162: "Personal 3 tiros libres",
    163: "Personal TL Comp", 164: "Personal sin falta de equipo", 165: "Antideportiva 1 tiro libre",
    166: "Antideportiva 2 tiros libres", 167: "Antideportiva 3 tiros libres", 168: "Antideportiva TL Comp",
    169: "Antideportiva sin falta de equipo", 170: "Descalificante", 171: "Descalificante sin falta de equipo",
    172: "Técnica", 173: "Técnica compensada", 174: "Técnica sin falta de equipo", 175: "Altercado",
    176: "Técnica entrenador/a", 177: "Técnica banquillo", 178: "Salto inicial ganado", 179: "Salto inicial perdido",
    180: "Canasta de 1", 181: "Intento fallado de 1", 182: "Falta", 183: "Antideportiva", 184: "Descalificante",
    530: "Violación", 531: "Falta", 533: "Mate fuera", 537: "Falta técnica", 538: "Falta técnica 2 tiros libres",
    539: "Falta técnica 3 tiros libres",
}


def tipo(idm: int) -> str:
    """Tipo normalizado de la acción (columna `tipo` de eventos.csv)."""
    for s, k in ((FT_MADE, "tl_anotado"), (FT_MISS, "tl_fallado"), (FG2_MADE, "t2_anotado"), (FG2_MISS, "t2_fallado"),
                 (FG3_MADE, "t3_anotado"), (FG3_MISS, "t3_fallado"), (OREB, "rebote_of"), (DREB, "rebote_def"),
                 (BLK, "tapon"), (BLKA, "tapon_recibido"), (STL, "robo"), (TOV, "perdida"), (AST, "asistencia"),
                 (OFF_FOUL, "falta_ataque"), (FOUL_DRAWN, "falta_recibida"), (SUB_IN, "entra"), (SUB_OUT, "sale"),
                 (TIMEOUT, "tiempo_muerto"), (PERIOD_END, "fin_periodo"), (FASTBREAK_MARK, "contraataque"),
                 (PERSONAL, "falta_personal"), (UNSPORTS, "falta_antideportiva"), (DISQ, "falta_descalificante"),
                 (TECH, "falta_tecnica"), (ALTERC, "altercado"), (COACH_TECH, "tecnica_entrenador"),
                 (BENCH_TECH, "tecnica_banquillo"), (JUMP_WON, "salto_ganado"), (JUMP_LOST, "salto_perdido"),
                 (VIOLATION, "violacion")):
        if idm in s:
            return k
    return "otra"


# ------------------------------------------------------------------------------------------ geometría
COURT_L, COURT_W, HOOP_X = 28.0, 15.0, 1.575


def zona_tiro(xn: float | None, yn: float | None, valor: int) -> tuple[str | None, float | None]:
    """(zona, distancia en m) a partir de las coordenadas normalizadas del acta (0-100 de la pista completa)."""
    if xn is None or yn is None:
        return None, None
    x = float(xn) / 100 * COURT_L
    y = float(yn) / 100 * COURT_W
    if x > COURT_L / 2:
        x = COURT_L - x
    dx, dy = x - HOOP_X, y - COURT_W / 2
    d = math.hypot(dx, dy)
    if valor == 3:
        return ("triple_esquina" if x <= 2.99 else "triple_frontal"), round(d, 2)
    if d < 1.25:
        return "aro", round(d, 2)
    if x <= 5.8 and abs(dy) <= 2.45:
        return "pintura", round(d, 2)
    return "media_distancia", round(d, 2)


def _period_len(acta: dict, period: int) -> float:
    lst = acta.get("periodDurationList") or []
    if period <= len(lst) and lst[period - 1]:
        return float(lst[period - 1]) * 60
    if period > 4:
        return 300.0
    return float(acta.get("periodDuration") or 10) * 60


def minutos_partido(acta: dict) -> float:
    return sum(_period_len(acta, p) for p in range(1, 5)) / 60


def _elapsed(acta: dict, period: int, rem: float) -> float:
    start = sum(_period_len(acta, p) for p in range(1, period))
    ln = _period_len(acta, period)
    return start + ln - max(0.0, min(ln, rem))


# ------------------------------------------------------------------------------------------ partido
def equipos_acta(acta: dict) -> tuple[dict, list[str]]:
    """{id interno: id de equipo de la web (idSignedTeam)} y [local, visitante] con ids de la web."""
    intern = {}
    for t in acta.get("teams") or []:
        intern[str(t.get("teamIdIntern"))] = str(t.get("teamIdExtern") or t.get("teamIdIntern"))
    order = [intern.get(str(acta.get("localId"))), intern.get(str(acta.get("visitId")))]
    if None in order:
        order = [intern[k] for k in list(intern)[:2]]
    return intern, order


def coordenadas(acta: dict) -> dict[str, tuple[float, float, int, bool]]:
    """eventUuid -> (xnormalize, ynormalize, valor, anotado) desde el acta (listas *Point de cada jugador/equipo)."""
    out = {}
    keys = {"shootingOfTwoSuccessfulPoint": (2, True), "shootingOfTwoFailedPoint": (2, False),
            "shootingOfThreeSuccessfulPoint": (3, True), "shootingOfThreeFailedPoint": (3, False)}
    for t in acta.get("teams") or []:
        for src in [t.get("data") or {}] + [p.get("data") or {} for p in t.get("players") or []]:
            for k, (v, made) in keys.items():
                for s in src.get(k) or []:
                    if s.get("eventUuid"):
                        out[s["eventUuid"]] = (s.get("xnormalize"), s.get("ynormalize"), v, made)
    return out


class PartidoPBP:
    """Resultado de procesar un partido: eventos normalizados, Game para quintetos, líneas por jugador, tiros."""

    def __init__(self) -> None:
        self.eventos: list[dict] = []
        self.tiros: list[dict] = []
        self.lineas: dict[str, dict] = {}          # pid -> estadísticas del partido (de la cronología)
        self.jugadores: dict[str, dict] = {}       # pid -> identidad (nombre, dorsal, equipo, uuid, licencia...)
        self.game: Game | None = None
        self.registra: dict[str, bool] = {}        # qué estadísticas registra la mesa en este partido
        self.notas: list[str] = []
        self.canon: dict[str, str] = {}            # actorId del acta/cronología -> id canónico del jugador


_STATS0 = ("pts fgm fga fg2m fg2a fg3m fg3a ftm fta oreb dreb reb ast stl tov blk blka pf pfd dunks fastbreaks "
           "pts_fastbreak pts_paint pts_2ndchance pts_off_tov pf_ofensivas pf_antideportivas pf_tecnicas "
           "pf_descalificantes pf_tiro tl_viajes and1 violaciones saltos_ganados "
           "fga_aro fgm_aro fga_pintura fgm_pintura fga_media fgm_media fg3a_esquina fg3m_esquina "
           "fg3a_frontal fg3m_frontal fga_con_coord dist_tiro_sum "
           "fgm_asistidos clutch_pts clutch_fga clutch_fgm clutch_fg3a clutch_fg3m clutch_fta clutch_ftm clutch_tov "
           "clutch_oreb clutch_dreb clutch_stl clutch_pf "
           "q1_pts q2_pts q3_pts q4_pts ot_pts").split()


def procesar_partido(game_id: str, fase: str, acta: dict, jugadas: list, fecha: str | None = None,
                     roster: dict | None = None) -> PartidoPBP:
    """Id canónico del jugador = `uuid` de la persona federada que trae el acta (el mismo de las fichas de equipo:
    estable entre partidos, equipos y temporadas; "fnb_…" para licencias de la Federación Navarra). Si falta: licencia
    de la temporada (cronología o ficha del equipo por nombre, `roster` = {(team_id, nombre normalizado): licencia})
    y, en último caso, "n-<equipo>-<nombre>"."""
    out = PartidoPBP()
    intern, teams = equipos_acta(acta)
    lic_actor = {str(mv.get("actorId")): str(mv["licenseId"]) for mv in jugadas
                 if mv.get("licenseId") and not mv.get("teamAction") and str(mv.get("actorId") or "0") != "0"}
    uuid_actor = {str(p.get("actorId")): p.get("uuid") for t in acta.get("teams") or [] for p in t.get("players") or []
                  if p.get("uuid")}
    canon: dict[str, str] = {}

    def cid(actor, name, tid) -> str:
        actor = str(actor)
        if actor not in canon:
            lic = lic_actor.get(actor) or (roster or {}).get((tid, norm_nombre(name)))
            canon[actor] = uuid_actor.get(actor) or (f"lic-{lic}" if lic else f"n-{tid}-{norm_nombre(name).replace(' ', '-')}")
        return canon[actor]
    for t in acta.get("teams") or []:
        for p in t.get("players") or []:
            cid(p.get("actorId"), p.get("name"), intern.get(str(t.get("teamIdIntern"))))
    for mv in jugadas:
        if str(mv.get("actorId") or "0") != "0" and not mv.get("teamAction"):
            cid(mv.get("actorId"), mv.get("actorName"), intern.get(str(mv.get("idTeam"))))
    out.canon = canon
    local, visit = teams
    coords = coordenadas(acta)
    names = {}
    starters: dict[str, list[str]] = {t: [] for t in teams}
    box = {}
    for t in acta.get("teams") or []:
        tid = intern.get(str(t.get("teamIdIntern")))
        for p in t.get("players") or []:
            pid = canon[str(p.get("actorId"))]
            names[pid] = p.get("name")
            out.jugadores[pid] = {"player_id": pid, "nombre": " ".join(str(p.get("name") or pid).split()),
                                  "dorsal": p.get("dorsal"), "team_id": tid, "acta_uuid": p.get("uuid"),
                                  "capitan": bool(p.get("captain")), "titular": bool(p.get("starting"))}
            if p.get("starting"):
                starters[tid].append(pid)
            tp = p.get("timePlayed")
            box[pid] = {"sec": float(tp) * 60 if tp is not None else None,
                        "pm": float(p["inOut"]) if p.get("inOut") is not None else None}
    # rellenar identidad desde la cronología (licencia) y jugadores que no estén en el acta
    lic = {}
    for mv in jugadas:
        pid = canon.get(str(mv.get("actorId") or ""), "")
        if not pid or mv.get("teamAction"):
            continue
        if mv.get("licenseId"):
            lic[pid] = str(mv["licenseId"])
        if pid not in out.jugadores:
            out.jugadores[pid] = {"player_id": pid, "nombre": " ".join(str(mv.get("actorName") or pid).split()),
                                  "dorsal": mv.get("actorShirtNumber"),
                                  "team_id": intern.get(str(mv.get("idTeam"))), "titular": None}
    for pid, l in lic.items():
        out.jugadores[pid]["licencia_id"] = l

    gmin = minutos_partido(acta)
    stats = defaultdict(Counter)
    team_of = {pid: j.get("team_id") for pid, j in out.jugadores.items()}
    other = {local: visit, visit: local}
    # estado de posesión
    off, origin, t_origin, second = None, "inicio", 0.0, False
    last_mark = {}            # equipo -> t de la última marca de contraataque
    score = {local: 0, visit: 0}
    lg_events: list[Event] = []
    assists_markers = []
    n = len(jugadas)
    for i, mv in enumerate(jugadas):
        idm = int(mv.get("idMove") or 0)
        per = int(mv.get("period") or 1)
        rem = float(mv.get("min") or 0) * 60 + float(mv.get("sec") or 0)
        t = _elapsed(acta, per, rem)
        tid = intern.get(str(mv.get("idTeam")))
        pid = canon.get(str(mv.get("actorId") or "")) if not mv.get("teamAction") else None
        if pid and team_of.get(pid) is None:
            team_of[pid] = tid
        margin_before = score[local] - score[visit]
        clutch = per >= 4 and rem <= 300 and abs(margin_before) <= 5
        ev = {"game_id": game_id, "fase": fase, "orden": i, "periodo": per, "reloj_s": rem, "t": round(t, 1),
              "team_id": tid, "local": tid == local if tid else None, "player_id": pid,
              "jugador": names.get(pid) or (mv.get("actorName") if pid else None), "dorsal": mv.get("actorShirtNumber") or None,
              "id_accion": idm, "accion": mv.get("move"), "tipo": tipo(idm), "marcador": mv.get("score"),
              "clutch": clutch, "event_uuid": mv.get("eventUuid"), "timestamp": mv.get("timestamp")}
        s = stats[pid] if pid else None
        value = 1 if idm in FT_MADE | FT_MISS else 2 if idm in FG2_MADE | FG2_MISS else 3 if idm in FG3_MADE | FG3_MISS else 0
        made = idm in FT_MADE | FG2_MADE | FG3_MADE
        # ------------------------------------------------ marcador y posesión
        if value and made and tid in score:
            score[tid] += value
        if tid in other:
            if idm in DREB or idm in STL:
                off, origin, t_origin, second = tid, ("perdida" if idm in STL else "rebote_def"), t, False
            elif idm in TOV:
                if off != other[tid] or origin != "perdida":
                    off, origin, t_origin, second = other[tid], "perdida", t, False
            elif idm in OREB:
                off, second = tid, True
            elif idm in FASTBREAK_MARK:
                last_mark[tid] = t
        # ------------------------------------------------ estadísticas del jugador
        if value and tid in other:
            ctx_poss = off == tid
            fb = ctx_poss and ((origin in ("perdida", "rebote_def") and t - t_origin <= 8)
                               or (t - last_mark.get(tid, -99) <= 3))
            if s is not None:
                if value == 1:
                    s["fta"] += 1
                    s["ftm"] += made
                    if clutch:
                        s["clutch_fta"] += 1
                        s["clutch_ftm"] += made
                else:
                    s["fga"] += 1
                    s["fgm"] += made
                    s[f"fg{value}a"] += 1
                    s[f"fg{value}m"] += made
                    if idm in DUNK:
                        s["dunks"] += 1
                    if clutch:
                        s["clutch_fga"] += 1
                        s["clutch_fgm"] += made
                        if value == 3:
                            s["clutch_fg3a"] += 1
                            s["clutch_fg3m"] += made
                    c = coords.get(mv.get("eventUuid") or "")
                    zona, dist = zona_tiro(c[0], c[1], value) if c else (None, None)
                    ev.update(x=c[0] if c else None, y=c[1] if c else None, zona=zona, distancia_m=dist)
                    if zona:
                        s["fga_con_coord"] += 1
                        s["dist_tiro_sum"] += dist
                        key = {"aro": "aro", "pintura": "pintura", "media_distancia": "media",
                               "triple_esquina": "esquina", "triple_frontal": "frontal"}[zona]
                        if value == 3:
                            s[f"fg3a_{key}"] += 1
                            s[f"fg3m_{key}"] += made
                        else:
                            s[f"fga_{key}"] += 1
                            s[f"fgm_{key}"] += made
                    out.tiros.append({"game_id": game_id, "fase": fase, "fecha": fecha, "periodo": per,
                                      "reloj_s": rem, "t": round(t, 1), "team_id": tid, "player_id": pid,
                                      "jugador": ev["jugador"], "valor": value, "anotado": made,
                                      "x": c[0] if c else None, "y": c[1] if c else None, "zona": zona,
                                      "distancia_m": dist, "contraataque": bool(fb), "segunda_oportunidad": bool(ctx_poss and second),
                                      "tras_perdida": bool(ctx_poss and origin == "perdida"), "clutch": clutch,
                                      "margen_previo": margin_before if tid == local else -margin_before,
                                      "event_uuid": mv.get("eventUuid")})
                if made:
                    s["pts"] += value
                    s[{1: "q1_pts", 2: "q2_pts", 3: "q3_pts", 4: "q4_pts"}.get(per, "ot_pts")] += value
                    if clutch:
                        s["clutch_pts"] += value
                    if ctx_poss and second:
                        s["pts_2ndchance"] += value
                    if ctx_poss and origin == "perdida":
                        s["pts_off_tov"] += value
                    if fb:
                        s["pts_fastbreak"] += value
                        if value > 1:
                            s["fastbreaks"] += 1
                    if value == 2 and ev.get("zona") in ("aro", "pintura"):
                        s["pts_paint"] += value
                    if value > 1:
                        nxt = jugadas[i + 1] if i + 1 < n else {}
                        if (int(nxt.get("idMove") or 0) in FT_MADE | FT_MISS and canon.get(str(nxt.get("actorId"))) == pid
                                and nxt.get("period") == mv.get("period") and nxt.get("min") == mv.get("min")
                                and nxt.get("sec") == mv.get("sec")):
                            s["and1"] += 1
            if made:
                # la posesión cambia tras canasta o tiro libre anotado, salvo que le sigan tiros libres del mismo
                # equipo (adicional o resto de la serie: cambia después del último)
                nxt = next((x for x in jugadas[i + 1:i + 6] if int(x.get("idMove") or 0) not in SUB_IN | SUB_OUT | TIMEOUT), {})
                sigue_tl = (int(nxt.get("idMove") or 0) in FT_MADE | FT_MISS
                            and intern.get(str(nxt.get("idTeam"))) == tid)
                if not sigue_tl:
                    off, origin, t_origin, second = other[tid], "canasta", t, False
        if s is not None:
            if idm in OREB:
                s["oreb"] += 1
                s["clutch_oreb"] += clutch
            elif idm in DREB:
                s["dreb"] += 1
                s["clutch_dreb"] += clutch
            elif idm in STL:
                s["stl"] += 1
                s["clutch_stl"] += clutch
            elif idm in TOV:
                s["tov"] += 1
                s["clutch_tov"] += clutch
            elif idm in BLK:
                s["blk"] += 1
            elif idm in BLKA:
                s["blka"] += 1
            elif idm in AST:
                s["ast"] += 1
            elif idm in FOUL_DRAWN:
                s["pfd"] += 1
            elif idm in VIOLATION:
                s["violaciones"] += 1
            elif idm in JUMP_WON:
                s["saltos_ganados"] += 1
            if idm in PLAYER_FOULS:
                s["pf"] += 1
                s["clutch_pf"] += clutch
                s["pf_ofensivas"] += idm in OFF_FOUL
                s["pf_antideportivas"] += idm in UNSPORTS
                s["pf_tecnicas"] += idm in TECH
                s["pf_descalificantes"] += idm in DISQ
                s["pf_tiro"] += idm in SHOOTING_FOUL
                s["tl_viajes"] += idm in SHOOTING_FOUL | {165, 166, 167, 548, 549, 550, 538, 539}
        if idm in PERIOD_END:
            off, origin, t_origin, second = None, "inicio", t, False
        out.eventos.append(ev)
        # ------------------------------------------------ evento para quintetos
        kind = None
        if value:
            kind = "ft" if value == 1 else "shot"
        elif idm in SUB_IN:
            kind = "in"
        elif idm in SUB_OUT:
            kind = "out"
        elif idm in OREB:
            kind = "oreb"
        elif idm in DREB:
            kind = "dreb"
        elif idm in TOV:
            kind = "tov"
        elif idm in STL:
            kind = "stl"
        elif idm in BLK:
            kind = "blk"
        elif idm in PLAYER_FOULS:
            kind = "foul"
        elif idm in FOUL_DRAWN:
            kind = "foul_drawn"
        elif idm in AST and pid:
            assists_markers.append((i, tid, pid))
        if kind and tid:
            lg_events.append(Event(order=i, period=per, t=t, kind=kind, team=tid, player=pid,
                                   made=made if value else None, value=value, pts=value if made else 0,
                                   x=ev.get("x"), y=ev.get("y")))
    # asistencias (si la mesa las registra) enlazadas al tiro anotado anterior del mismo equipo
    from ..lineups.model import link_assists_by_adjacency
    unl = link_assists_by_adjacency(lg_events, assists_markers) if assists_markers else 0
    for e in lg_events:
        if e.assister and e.kind == "shot":
            stats[e.player]["fgm_asistidos"] += 1
    for pid, c in stats.items():
        c["reb"] = c["oreb"] + c["dreb"]
        out.lineas[pid] = dict(c)
    # qué registra la mesa en este partido (ambos equipos a cero = no se registra; nunca 0 por defecto)
    tot = Counter()
    for c in stats.values():
        tot.update(c)
    out.registra = {"ast": tot["ast"] > 0, "blk": tot["blk"] + tot["blka"] > 0 or tot["ast"] > 0,
                    "dunks": tot["dunks"] > 0, "coords": tot["fga_con_coord"] > 0}
    if unl:
        out.notas.append(f"{unl} asistencias sin enlazar")
    g = Game(game_id=game_id, phase=fase, teams=teams,
             team_names={intern.get(str(t.get("teamIdIntern"))): t.get("name") for t in acta.get("teams") or []},
             players={pid: {"nombre": j["nombre"], "team": j.get("team_id")} for pid, j in out.jugadores.items()},
             starters={t: v for t, v in starters.items() if len(v) == 5}, events=lg_events, box=box, date=fecha,
             has_lineups=any(e.kind in ("in", "out") for e in lg_events),
             has_assists=bool(assists_markers), has_shots=bool(coords),
             coord_system="% de pista completa FIBA 28x15 (x a lo largo, y a lo ancho)")
    out.game = g
    out.game_min = gmin
    return out


# ------------------------------------------------------------------------------------------ acta
_ACTA_MAP = {"score": "pts", "shotsOfOneSuccessful": "ftm", "shotsOfOneAttempted": "fta",
             "shotsOfTwoSuccessful": "fg2m", "shotsOfTwoAttempted": "fg2a", "shotsOfThreeSuccessful": "fg3m",
             "shotsOfThreeAttempted": "fg3a", "offensiveRebound": "oreb", "defensiveRebound": "dreb",
             "rebounds": "reb", "assists": "ast", "steals": "stl", "lost": "tov", "block": "blk",
             "blockReceived": "blka", "faults": "pf", "faultReceived": "pfd", "dunk": "dunks",
             "valoration": "pir", "counterattack": "fastbreaks"}


def stats_acta(data: dict | None) -> dict:
    d = data or {}
    out = {c: float(d[k]) for k, c in _ACTA_MAP.items() if isinstance(d.get(k), (int, float))}
    if "fg2m" in out and "fg3m" in out:
        out["fgm"] = out["fg2m"] + out["fg3m"]
        out["fga"] = out.get("fg2a", 0) + out.get("fg3a", 0)
    return out


def norm_nombre(s: str | None) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()
