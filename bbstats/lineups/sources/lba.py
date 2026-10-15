"""LBA Serie A (Italia): jugada a jugada de la API pública de legabasket.it.

  PBP:  https://www.legabasket.it/api/championships/get-championships-matches-play-by-play?id=M
        pbp.actions[] (en orden DESCENDENTE): action_id, order, period, minute/seconds (TRANSCURRIDO en
        el periodo), description (italiano), team_id, player_id, x/y (0-100), linked_action_id;
        pbp.ht_id / pbp.vt_id = equipos local / visitante.
  Boxscore (titulares sf=1, segundos `sec`, plus_minus): get-championships-matches-scores-by-id, ya
        descargado por el adaptador principal (payload["scores"][M]); se pide sólo si falta.

Orden: (periodo, segundo transcurrido, order, action_id). Algunos partidos tienen alguna acción con
`order` fuera de sitio (p.ej. una canasta del 1er cuarto al final del periodo); el reloj es más fiable.
Asistencias: `linked_action_id` apunta al tiro (o a un tiro libre); en 2020-21 es nulo y se enlazan por
adyacencia (model.link_assists_by_adjacency).
Ids: jugador = player_id, equipo = team_id (= h_team_id / v_team_id del calendario, como el adaptador).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from ...http import FetchError
from ...utils import to_float
from ..model import Event, Game, elapsed, link_assists_by_adjacency
from .base import Ctx, PBPSource

API = "https://www.legabasket.it/api"
PHASE_BY_TYPE = {"RS": "regular", "PO": "playoffs"}
FINISHED = {"2"}

SHOTS = {"2 punti segnato": (2, True), "2 punti sbagliato": (2, False),
         "3 punti segnato": (3, True), "3 punti sbagliato": (3, False)}
FTS = {"Tiro libero segnato": True, "Tiro libero sbagliato": False}
SIMPLE = {"Ingresso": "in", "Uscita": "out",
          "Rimbalzo offensivo": "oreb", "Rimbalzi offensivi di squadra": "oreb",
          "Rimbalzo difensivo": "dreb", "Rimbalzi difensivi di squadra": "dreb",
          "Palla persa": "tov", "Palle perse di squadra": "tov",
          "Palla recuperata": "stl", "Palle recuperate di squadra": "stl",
          "Stoppata": "blk", "Fallo commesso": "foul", "Falli di squadra": "foul",
          "Fallo Subito": "foul_drawn"}
TEAM_LEVEL = {"Rimbalzi offensivi di squadra", "Rimbalzi difensivi di squadra", "Palle perse di squadra",
              "Palle recuperate di squadra", "Falli di squadra"}
IGNORED = {"Time Out", "Fine Tempo", "Inizio Tempo", "Stoppata subita", "Palla contesa"}


def _str(v) -> str | None:
    return None if v is None or v == "" else str(v)


class LbaPBP(PBPSource):
    name = "legabasket"
    version = "1.0"

    def _get(self, ctx: Ctx, path: str, params: dict | None = None) -> Any:
        return ctx.http.get_json(f"{ctx.cfg.get('base_url', API)}/{path}", params=params,
                                 headers={"Accept": "application/json", "Referer": "https://www.legabasket.it/"})

    # ------------------------------------------------------------------ partidos
    def _calendars(self, ctx: Ctx) -> tuple[list[dict], dict]:
        """(competiciones, {cid: {clave: documento de jornada}}) del bruto principal o, si no hay, de la API."""
        p = ctx.main_payload if isinstance(ctx.main_payload, dict) else {}
        if p.get("calendars"):
            return p.get("championships") or [], p["calendars"]
        from ...adapters.lba import LBAAdapter
        ad = LBAAdapter("lba", ctx.cfg)
        champs = ((ctx.cfg.get("temporadas") or {}).get(ctx.season) or {}).get("championships") \
            or ad._championships(ctx.http, ctx.start_year)
        cals: dict[str, dict] = {}
        for ch in champs:
            cid = ch["id"]
            first = self._get(ctx, "championships/get-championships-calendar-by-id", {"id": cid})
            filters = first.get("filters") or {}
            serials = sorted({d["event_serial"] for d in filters.get("days") or []})
            phases = [ph["id"] for ph in filters.get("phases") or []] or [None]
            cals[str(cid)] = {}
            for ph in phases:
                for serial in serials:
                    params = {"id": cid, "d": serial, **({"ph_id": ph} if ph is not None else {})}
                    try:
                        doc = self._get(ctx, "championships/get-championships-calendar-by-id", params)
                    except FetchError as exc:
                        ctx.errors.append(str(exc))
                        continue
                    cals[str(cid)][str(serial) if ph is None else f"ph{ph}-{serial}"] = doc
        return champs, cals

    def games(self, ctx: Ctx) -> list[dict]:
        champs, cals = self._calendars(ctx)
        phase_of = {str(c["id"]): PHASE_BY_TYPE.get(c.get("ctype_code"), "regular") for c in champs}
        out, seen = [], set()
        for cid, days in cals.items():
            for doc in days.values():
                for m in doc.get("matches") or []:
                    mid = str(m["id"])
                    if mid in seen:
                        continue
                    seen.add(mid)
                    out.append({"game_id": mid, "phase": phase_of.get(cid, "regular"),
                                "final": str(m.get("game_status")) in FINISHED, "date": m.get("match_datetime"),
                                "round": m.get("day_name"),
                                "teams": [_str(m.get("h_team_id")), _str(m.get("v_team_id"))],
                                "team_names": {_str(m.get("h_team_id")): m.get("h_team_name"),
                                               _str(m.get("v_team_id")): m.get("v_team_name")}})
        return out

    # ------------------------------------------------------------------ descarga
    def fetch(self, ctx: Ctx, ref: dict) -> dict:
        mid = ref["game_id"]
        raw: dict[str, Any] = {"pbp": self._get(ctx, "championships/get-championships-matches-play-by-play",
                                                {"id": mid})}
        scores = ((ctx.main_payload or {}).get("scores") or {}).get(mid) if isinstance(ctx.main_payload, dict) else None
        if not scores:
            try:
                scores = self._get(ctx, "championships/get-championships-matches-scores-by-id", {"id": mid})
            except FetchError as exc:
                ctx.errors.append(f"scores {mid}: {exc}")
                scores = None
        raw["scores"] = scores
        return raw

    # ------------------------------------------------------------------ interpretación
    def parse(self, raw: dict, ref: dict, ctx: Ctx) -> Game:
        doc = raw.get("pbp") or {}
        pbp = doc.get("pbp") or {}
        scores = raw.get("scores")
        if not scores and isinstance(ctx.main_payload, dict):
            scores = (ctx.main_payload.get("scores") or {}).get(ref["game_id"])
        sc = (scores or {}).get("scores") or {}
        ref_teams = ref.get("teams") or [None, None]
        home = _str(pbp.get("ht_id")) or ref_teams[0]
        away = _str(pbp.get("vt_id")) or ref_teams[1]
        game_min = ctx.game_min
        g = Game(game_id=str(ref["game_id"]), phase=ref.get("phase", "regular"), teams=[home, away],
                 date=ref.get("date"),
                 coord_system="legabasket x/y 0-100 (porcentaje de la pista completa, sin normalizar canasta)")
        names = ref.get("team_names") or {}
        g.team_names = {home: names.get(home) or home, away: names.get(away) or away}

        for side, tid in (("ht", home), ("vt", away)):
            st = []
            for r in (sc.get(side) or {}).get("rows") or []:
                pid = _str(r.get("player_id"))
                if not pid:
                    continue
                g.players[pid] = {"nombre": f"{r.get('player_name', '')} {str(r.get('player_surname', '')).title()}".strip(),
                                  "team": tid}
                sec = to_float(r.get("sec"))
                g.box[pid] = {"sec": sec if sec is not None else 0.0, "pm": to_float(r.get("plus_minus"))}
                if str(r.get("sf")) == "1":
                    st.append(pid)
            if len(st) == 5:
                g.starters[tid] = st

        def t_of(a: dict) -> float:
            per = int(a.get("period") or 1)
            return elapsed(per, None, game_min, elapsed_in_period_s=(a.get("minute") or 0) * 60 + (a.get("seconds") or 0))

        acts = sorted(pbp.get("actions") or [],
                      key=lambda a: (int(a.get("period") or 1), t_of(a), a.get("order") or 0, a.get("action_id") or 0))
        evs: list[Event] = []
        by_action: dict[Any, Event] = {}
        links: list[tuple[int, str, str, Any]] = []
        unknown: dict[str, int] = defaultdict(int)
        n_xy = 0
        for i, a in enumerate(acts):
            desc = (a.get("description") or "").strip()
            tm = _str(a.get("team_id"))
            pid = _str(a.get("player_id"))
            if desc in TEAM_LEVEL:
                pid = None
            if pid and pid not in g.players:
                g.players[pid] = {"nombre": f"{a.get('player_name') or ''} {a.get('player_surname') or ''}".strip() or pid,
                                  "team": tm}
            kw = {"order": i, "period": int(a.get("period") or 1), "t": t_of(a), "team": tm, "player": pid}
            e = None
            if desc in SHOTS:
                v, made = SHOTS[desc]
                x, y = a.get("x"), a.get("y")
                if x is not None and y is not None:
                    n_xy += 1
                e = Event(kind="shot", value=v, made=made, pts=v if made else 0, x=x, y=y, **kw)
            elif desc in FTS:
                made = FTS[desc]
                e = Event(kind="ft", value=1, made=made, pts=1 if made else 0, **kw)
            elif desc in SIMPLE:
                if SIMPLE[desc] in ("in", "out") and not pid:
                    continue
                e = Event(kind=SIMPLE[desc], **kw)
            elif desc == "Assist":
                if pid and tm:
                    links.append((i, tm, pid, a.get("linked_action_id")))
                continue
            elif desc not in IGNORED:
                unknown[desc] += 1
                continue
            if e is not None:
                evs.append(e)
                if a.get("action_id") is not None:
                    by_action[a["action_id"]] = e
        g.events = evs
        g.has_shots = n_xy > 0
        if not acts:
            g.has_lineups = g.has_assists = False
            g.notes.append("la fuente no tiene jugada a jugada de este partido")
            return g

        # asistencias: enlace explícito si existe, si no por adyacencia
        by_order = sorted(evs, key=lambda e: e.order)
        markers, ft_missed = [], 0
        for order, tm, pid, link in links:
            target = by_action.get(link) if link else None
            if target is not None and target.team == tm and target.kind in ("shot", "ft"):
                if target.kind == "ft" and not target.made:
                    # asistencia anotada sobre un TL fallado: el siguiente TL anotado de la misma serie
                    target = next((e for e in by_order if e.order > target.order and e.kind == "ft"
                                   and e.team == tm and e.t == target.t and e.made), None)
                if target is not None and target.made and target.assister is None and target.player != pid:
                    target.assister, target.ast_ft = pid, target.kind == "ft"
                    continue
                if target is None:
                    ft_missed += 1
                    continue
            markers.append((order, tm, pid))
        left = link_assists_by_adjacency(evs, markers) if markers else 0
        g.has_assists = bool(links)
        if left:
            g.notes.append(f"{left}/{len(links)} asistencias sin enlazar")
        if ft_missed:
            g.notes.append(f"{ft_missed} asistencias a tiros libres sin ninguno anotado")
        if unknown:
            g.notes.append("acciones no catalogadas: " + ", ".join(f"{k}x{v}" for k, v in sorted(unknown.items())))
        if g.box and all((b["sec"] or 0) % 60 == 0 for b in g.box.values()):
            g.notes.append("boxscore en minutos enteros: la validación de minutos tiene un margen de ±30 s")
        if not g.box:
            g.notes.append("sin boxscore: no se pueden validar minutos ni +/-")
        return g
