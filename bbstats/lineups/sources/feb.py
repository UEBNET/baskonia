"""Competiciones FEB (Primera, Segunda y Tercera FEB): jugada a jugada de KeyFacts (intrafeb.feb.es).

No hace peticiones: el adaptador principal (bbstats/adapters/feb.py) guarda en su bruto, por partido, el JSON
de KeyFacts (jugada a jugada + boxscore en directo) y, en el formato antiguo, el BoxScore oficial.

Dos formatos (PLAYBYPLAY.LINES, orden DESCENDENTE de `num`; se ordena ascendente):

  estructurado (2024-25 en adelante)
    action   shoot (logParam4 = anotado 1/0, logParam6 = valor 2/3, Position "x|y" en % de la pista completa),
             fthrow (logParam4 = anotado), rebound (idPlayer vacío = rebote de equipo), assist (línea aparte, justo
             después de la canasta), foul (logParam4 = licencia del jugador que la recibe; "Entrenador"/"Banquillo"
             sin jugador), lose (pérdida; "Equipo" sin jugador), recovery (robo), blockshot (tapón), subst
             ("Entra a pista" / "Sale de pista"), timeout, period
    idPlayer = id de persona (el del boxscore), idLicense = licencia de esa temporada, quarter, time = reloj
    RESTANTE "MM:SS".
  texto (2020-21 a 2023-24): sólo `text`, `team` (1 local / 2 visitante, el del primer actor), quarter, time,
    scoreA/scoreB. Cada línea encadena acciones "NOMBRE: acción" separadas por comas, p.ej.
      "(EQUIPO) J. PEREZ: 3Pts Tiro FALLADO, A. LOPEZ:  (TotReb. 2)"
      "(EQUIPO) M. DELAS: Tiro en suspensión ANOTADO (3 Pts), J. JAWORSKI: Asistencias (3 As)"
      "(EQUIPO) Sustitución: (Entra) A. MARTINEZ DE LA ORDEN"
    Los nombres ("J. JAWORSKI") se emparejan con los del boxscore oficial de cada equipo (mismo formato).
    Valor de las canastas: "3Pts Tiro" = triple; "Tiro en suspensión", "Mate" o sin tipo = de 2, salvo que el
    acumulado de puntos del jugador "(N Pts)" suba 3. Rebote ofensivo/defensivo por el equipo del último fallo.
    Sin coordenadas de tiro. Los rebotes sin nombre (de equipo) se ignoran (no se sabe de qué equipo son).

En los dos formatos el quinteto inicial se anota como cinco "Entra" antes de "Comienzo del Cuarto 1": esas
entradas se descartan y fijan los titulares (con los titulares del boxscore, `inn`, de respaldo).
Ids: jugador = id de persona FEB, equipo = id de inscripción de la temporada (como ligas/<liga>.csv).
"""
from __future__ import annotations

import re
import unicodedata

from ...adapters.feb import box_teams, header, is_final, pbp_format, pbp_lines
from ...utils import to_float
from ..model import Event, Game, clock_to_seconds, elapsed, link_assists_by_adjacency
from .base import Ctx, PBPSource

SIMPLE = {"recovery": "stl", "blockshot": "blk", "lose": "tov"}
COORDS = "FEB x/y 0-100 (% de la pista completa, dos canastas; Position 'x|y')"


def _games_of(payload) -> dict:
    return (payload or {}).get("games") or {} if isinstance(payload, dict) else {}


def norm_name(s) -> str:
    """"M. N´GUESSAN " -> "M NGUESSAN": mayúsculas sin acentos ni signos."""
    s = str(s or "").replace("´", "").replace("'", "").replace("’", "")
    s = unicodedata.normalize("NFKD", s.upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^A-Z0-9 ]+", " ", s.replace("´", "").replace("'", "")).split())


def game_refs(payload: dict) -> list[dict]:
    """Partidos del bruto principal con datos y fase regular/playoffs (para la capa de quintetos)."""
    cal = (payload or {}).get("calendario") or {}
    grupos, meta = cal.get("grupos") or {}, cal.get("partidos") or {}
    out = []
    for gid, doc in _games_of(payload).items():
        if not isinstance(doc, dict) or doc.get("sin_datos") or not header(doc):
            continue
        m = meta.get(gid) or {}
        ph = (grupos.get(m.get("grupo")) or {}).get("fase", "regular") if m else "regular"
        if ph not in ("regular", "playoffs"):
            continue
        teams = header(doc).get("TEAM") or []
        out.append({"game_id": gid, "phase": ph, "final": is_final(doc), "date": m.get("fecha"),
                    "grupo": m.get("grupo"), "teams": [str(t.get("id")) for t in teams],
                    "team_names": {str(t.get("id")): " ".join(str(t.get("name") or "").split()) for t in teams}})
    return sorted(out, key=lambda r: int(r["game_id"]))


# ---------------------------------------------------------------------------------- formato texto
_ACTOR = re.compile(r"(?:^|,)\s*([A-ZÁÉÍÓÚÑÜÇ]\.\s?[^:,()]*?)\s*:")
_SUB = re.compile(r"Sustituci[oó]n:\s*\((Entra|Sale)\)\s*(.+?)\s*$")
_PTS = re.compile(r"\((\d+) Pts\)")


def text_clauses(text: str) -> tuple[str | None, list[tuple[str | None, str]]]:
    """"(EQUIPO) A: acción, B: acción" -> ("EQUIPO", [("A", "acción"), ("B", "acción")]).
    Las acciones sin actor (rebote de equipo, pérdidas de equipo, banquillo) quedan con actor None."""
    m = re.match(r"\s*\(([^)]*)\)\s*(.*)$", text or "", re.S)
    team, body = (m.group(1).strip(), m.group(2)) if m else (None, text or "")
    sub = _SUB.search(body)
    if sub:
        return team, [(sub.group(2), "Entra" if sub.group(1) == "Entra" else "Sale")]
    marks = list(_ACTOR.finditer(body))
    out: list[tuple[str | None, str]] = []
    pre = body[:marks[0].start()] if marks else body
    if pre.strip(" ,"):
        out.append((None, pre.strip(" ,")))
    for i, mk in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        act = body[mk.end():end].strip(" ,")
        # una acción sin actor pegada detrás (",  (TotReb. 26)") se separa
        tail = re.search(r",\s*(\(TotReb\. \d+\))\s*$", act)
        if tail and act[:tail.start()].strip(" ,"):
            out.append((mk.group(1).strip(), act[:tail.start()].strip(" ,")))
            out.append((None, tail.group(1)))
            continue
        out.append((mk.group(1).strip(), act))
    return team, out


class FebPBP(PBPSource):
    name = "feb"
    version = "1.0"
    uses_main_raw = True

    def games(self, ctx: Ctx) -> list[dict]:
        return game_refs(ctx.main_payload if isinstance(ctx.main_payload, dict) else {})

    def fetch(self, ctx: Ctx, ref: dict) -> dict:
        doc = _games_of(ctx.main_payload).get(str(ref["game_id"]))
        if not doc:
            raise ValueError("partido ausente del bruto principal")
        return {"data": doc}

    # ------------------------------------------------------------------ común
    def _base(self, doc: dict, ref: dict) -> tuple[Game, dict]:
        h = header(doc)
        tids = [str(t.get("id")) for t in h.get("TEAM") or []] or list(ref.get("teams") or [])
        g = Game(game_id=str(ref["game_id"]), phase=ref.get("phase", "regular"), teams=tids, date=ref.get("date"),
                 coord_system=COORDS)
        g.team_names = {str(t.get("id")): " ".join(str(t.get("name") or "").split()) for t in h.get("TEAM") or []}
        names: dict[str, dict[str, str]] = {t: {} for t in tids}
        for t in box_teams(doc):
            tid = str(t.get("id"))
            st = []
            for p in t.get("PLAYER") or []:
                pid = str(p.get("id"))
                g.players[pid] = {"nombre": " ".join(str(p.get("name") or pid).split()), "team": tid}
                sec = to_float(p.get("min"))
                g.box[pid] = {"sec": sec if sec else (None if sec is None else 0.0),
                              "pm": to_float(p.get("pllss"))}
                if str(p.get("inn")) == "1":
                    st.append(pid)
                names.setdefault(tid, {})[norm_name(p.get("name"))] = pid
            g.starters[tid] = st if len(st) == 5 else []
        if not any(b.get("pm") for b in g.box.values()):      # +/- no registrado (todo 0): no se valida con él
            for b in g.box.values():
                b["pm"] = None
        return g, names

    def parse(self, raw: dict, ref: dict, ctx: Ctx) -> Game:
        doc = raw.get("data") or {}
        g, names = self._base(doc, ref)
        lines = sorted((ln for ln in pbp_lines(doc) if not ln.get("deleted")),
                       key=lambda ln: int(to_float(ln.get("num")) or 0))
        fmt = pbp_format(doc)
        if fmt == "estructurado":
            self._structured(g, lines, ctx)
        elif fmt == "texto":
            self._text(g, lines, names, ctx)
        if not g.events:
            g.has_lineups = g.has_assists = g.has_shots = False
            g.notes.append("la fuente no tiene jugada a jugada de este partido")
        elif not any(e.kind in ("in", "out") for e in g.events):
            g.has_lineups = False
            g.notes.append("jugada a jugada sin cambios: sólo tiros y asistencias")
        g.notes.append(f"formato {fmt or 'sin jugada a jugada'}")
        return g

    @staticmethod
    def _pre_start(lines: list[dict]) -> int:
        """Índice de la línea "Comienzo del Cuarto 1" (las entradas anteriores son el quinteto inicial)."""
        for i, ln in enumerate(lines):
            if ln.get("action") == "period" or re.match(r"\s*Comienzo del Cuarto", ln.get("text") or ""):
                return i
            if ln.get("action") not in (None, "", "subst") or (not ln.get("action") and "Sustituci" not in (ln.get("text") or "")):
                return i
        return 0

    def _starters_from(self, g: Game, pre: list[tuple[str, str]]) -> None:
        by_team: dict[str, list[str]] = {}
        for tid, pid in pre:
            by_team.setdefault(tid, []).append(pid)
        for tid in g.teams:
            st = list(dict.fromkeys(by_team.get(tid, [])))
            if len(st) == 5:
                g.starters[tid] = st

    # ------------------------------------------------------------------ estructurado
    def _structured(self, g: Game, lines: list[dict], ctx: Ctx) -> None:
        tidx = {"1": g.teams[0] if g.teams else None, "2": g.teams[1] if len(g.teams) > 1 else None}
        lic = {str(ln["idLicense"]): str(ln["idPlayer"]) for ln in lines if ln.get("idLicense") and ln.get("idPlayer")}
        start = self._pre_start(lines)
        pre = []
        evs: list[Event] = []
        assists: list[tuple[int, str, str]] = []
        last_miss_team = None
        for order, ln in enumerate(lines, 1):
            act = ln.get("action")
            team = str(ln.get("idTeam")) if ln.get("idTeam") else tidx.get(str(ln.get("team") or ""))
            pid = str(ln["idPlayer"]) if ln.get("idPlayer") else None
            if order - 1 < start:
                if act == "subst" and pid and "Entra" in (ln.get("text") or ""):
                    pre.append((team, pid))
                continue
            per = int(to_float(ln.get("quarter")) or 1)
            t = elapsed(per, clock_to_seconds(ln.get("time")), ctx.game_min)
            kw = {"order": order, "period": per, "t": t, "team": team, "player": pid}
            p4 = str(ln.get("logParam4") or "")
            e = None
            if act == "shoot" and team:
                v = 3 if str(ln.get("logParam6")) == "3" else 2
                made = p4 == "1"
                x = y = None
                pos = str(ln.get("Position") or "")
                if "|" in pos:
                    x, y = (to_float(c) for c in pos.split("|")[:2])
                e = Event(kind="shot", value=v, made=made, pts=v if made else 0, x=x, y=y, **kw)
                last_miss_team = None if made else team
            elif act == "fthrow" and team:
                made = p4 == "1"
                e = Event(kind="ft", value=1, made=made, pts=1 if made else 0, **kw)
                last_miss_team = None if made else team
            elif act == "rebound" and team:
                e = Event(kind="oreb" if last_miss_team == team else "dreb", **kw)
                last_miss_team = None
            elif act == "assist" and pid and team:
                assists.append((order, team, pid))
            elif act == "subst" and pid and team:
                txt = ln.get("text") or ""
                e = Event(kind="in" if "Entra" in txt else "out", **kw) if ("Entra" in txt or "Sale" in txt) else None
            elif act in SIMPLE and team:
                e = Event(kind=SIMPLE[act], **kw)
                if act == "lose":
                    last_miss_team = None
            elif act == "foul" and team:
                e = Event(kind="foul", **kw)
                drawn = lic.get(p4)
                if drawn and g.players.get(drawn):
                    evs.append(e)
                    e = Event(kind="foul_drawn", order=order, period=per, t=t,
                              team=g.players[drawn]["team"], player=drawn)
            if e is not None:
                evs.append(e)
        self._starters_from(g, pre)
        g.events = evs
        left = link_assists_by_adjacency(evs, assists)
        g.has_assists = bool(assists)
        g.has_shots = any(e.x is not None for e in evs if e.kind == "shot")
        if left:
            g.notes.append(f"{left}/{len(assists)} asistencias sin enlazar")

    # ------------------------------------------------------------------ texto
    def _text(self, g: Game, lines: list[dict], names: dict, ctx: Ctx) -> None:
        tidx = {"1": g.teams[0] if g.teams else None, "2": g.teams[1] if len(g.teams) > 1 else None}
        other = {tidx["1"]: tidx["2"], tidx["2"]: tidx["1"]}
        unknown: set[str] = set()

        def who(name: str, team: str | None, prefer_other: bool = False) -> tuple[str | None, str | None]:
            k = norm_name(name)
            first = [other.get(team), team] if prefer_other else [team, other.get(team)]
            for tm in first:
                if tm and k in names.get(tm, {}):
                    return tm, names[tm][k]
            # apellido con espacios distintos o nombre de pila abreviado de otra forma
            for tm in first:
                for nk, pid in (names.get(tm) or {}).items():
                    if nk.replace(" ", "") == k.replace(" ", ""):
                        return tm, pid
            unknown.add(name.strip())
            return None, None

        start = self._pre_start(lines)
        pre = []
        evs: list[Event] = []
        pts_acc: dict[str, int] = {}
        last_miss_team = None
        n = 0
        for idx, ln in enumerate(lines):
            line_team = tidx.get(str(ln.get("team") or ""))
            _, clauses = text_clauses(ln.get("text") or "")
            per = int(to_float(ln.get("quarter")) or 1)
            t = elapsed(per, clock_to_seconds(ln.get("time")), ctx.game_min)
            if idx < start:
                for actor, act in clauses:
                    if act == "Entra" and actor:
                        tm, pid = who(actor, line_team)
                        if pid:
                            pre.append((tm, pid))
                continue
            last_made: Event | None = None
            for actor, act in clauses:
                n += 1
                kw = {"order": n, "period": per, "t": t}
                if act in ("Entra", "Sale"):
                    tm, pid = who(actor, line_team)
                    if pid:
                        evs.append(Event(kind="in" if act == "Entra" else "out", team=tm, player=pid, **kw))
                    continue
                if actor is None:
                    if re.match(r"P[ée]rdidas \(\d+\)", act) and line_team:
                        evs.append(Event(kind="tov", team=line_team, **kw))
                    elif "Coach/Bench" in act and line_team:
                        evs.append(Event(kind="foul", team=line_team, **kw))
                    continue      # rebote de equipo sin nombre: equipo desconocido
                is_reb = "TotReb" in act and not re.search(r"ANOTADO|FALLADO", act)
                is_def = bool(re.search(r"Robo|Bloqueo", act))
                tm, pid = who(actor, line_team, prefer_other=is_def)
                if tm is None:
                    continue
                kw.update(team=tm, player=pid)
                pm = _PTS.search(act)
                if re.search(r"Tiros? libres?", act):
                    made = "ANOTADO" in act
                    evs.append(Event(kind="ft", value=1, made=made, pts=1 if made else 0, **kw))
                    last_miss_team = None if made else tm
                    if pm:
                        pts_acc[pid] = int(pm.group(1))
                    if made:
                        last_made = evs[-1]
                elif re.search(r"ANOTADO|FALLADO", act):
                    made = "ANOTADO" in act
                    v = 3 if re.search(r"3\s*Pts Tiro", act) else 2
                    if made and pm:
                        delta = int(pm.group(1)) - pts_acc.get(pid, 0)
                        if delta in (2, 3):
                            v = delta
                    if pm:
                        pts_acc[pid] = int(pm.group(1))
                    e = Event(kind="shot", value=v, made=made, pts=v if made else 0, **kw)
                    evs.append(e)
                    last_miss_team = None if made else tm
                    last_made = e if made else None
                elif is_reb:
                    evs.append(Event(kind="oreb" if last_miss_team == tm else "dreb", **kw))
                    last_miss_team = None
                elif "Asistencia" in act:
                    if last_made is not None and last_made.team == tm and last_made.assister is None \
                            and last_made.player != pid:
                        last_made.assister = pid
                        last_made.ast_ft = last_made.kind == "ft"
                elif "Pérdida" in act or "Perdida" in act:
                    evs.append(Event(kind="tov", **kw))
                    last_miss_team = None
                elif "Robo" in act:
                    evs.append(Event(kind="stl", **kw))
                elif "Bloqueo" in act or "Tapón" in act:
                    evs.append(Event(kind="blk", **kw))
                elif re.search(r"Personal|Antideportiva|T[ée]cnica|Descalificante|Ofensiva|Falta", act):
                    evs.append(Event(kind="foul", **kw))
        self._starters_from(g, pre)
        g.events = evs
        g.has_assists = any(e.assister for e in evs)
        g.has_shots = False
        if unknown:
            g.notes.append(f"{len(unknown)} nombres sin emparejar con el boxscore: {sorted(unknown)[:5]}")


def docs_principal(main_payload, game_id: str) -> dict | None:
    """Documento del partido sacado del bruto principal (para el registro de entrenadores)."""
    doc = _games_of(main_payload).get(str(game_id))
    return {"data": doc} if doc else None
