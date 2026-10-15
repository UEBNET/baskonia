"""Liga Endesa (ACB): jugada a jugada oficial de api2.acb.com (la API de live.acb.com).

  PBP:    https://api2.acb.com/api/matchdata/PlayByPlay/play-by-play?matchId=M
          plays[]: order, playType, quarter, minute/second (reloj RESTANTE), local, playerLicenseId,
          playerName, scoreHome/scoreAway, playerStats (acumuladas del jugador tras la jugada)
  Tiros:  https://api2.acb.com/api/matchdata/MatchShots/match-shots?matchId=M
          shotPoints[]: posX/posY, playType, quarter, minute, second, playerLicenseId, made, points.
          Su `id` NO coincide con `order` del PBP: se enlaza por (cuarto, minuto, segundo, jugador,
          playType), en orden de aparición (verificado: 100 % de los tiros, mismo marcador).
  Boxscore (minutos y +/- para validar, titulares, nombres): el del bruto principal
          (payload["boxscores"][M], /api/matchdata/Result/boxscores); se pide sólo si falta.

Tabla de playType (deducida de los incrementos de playerStats y del marcador):
  92 TL anotado · 96 TL fallado · 93 2 anotado · 100 mate anotado · 97 2 fallado · 533 2 fallado (mate/alley)
  94 3 anotado · 98 3 fallado · 101 reb. ofensivo · 104 reb. defensivo (sin jugador = de equipo)
  102 tapón · 105 tapón recibido · 103 robo · 106 pérdida · 107/108 asistencia (tras canasta de 2/3)
  119 asistencia a tiros libres (antes de los TL) · 109/159-166 falta cometida · 110 falta recibida
  (también 173 doble, 537, 756, 761, 783: tipos de falta vistos; otros códigos se deducen de playerStats)
  112 entra · 115 sale · 599 titular · 121/116 inicio/fin de periodo · 113 tiempo muerto · 178/179 salto
  600 marca de minuto · 122, 118, 4xx, 748 control (sin jugador)
Ids: jugador = playerLicenseId (= player.id del boxscore principal); equipo = clubId (como el adaptador).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from ...http import FetchError
from ..model import Event, Game, clock_to_seconds, elapsed, link_assists_by_adjacency
from .base import Ctx, PBPSource

API = "https://api2.acb.com"
PUBLIC_KEY = "0dd94928-6f57-4c08-a3bd-b1b2f092976e"

SHOTS = {93: (2, True), 100: (2, True), 97: (2, False), 533: (2, False), 94: (3, True), 98: (3, False)}
FTS = {92: True, 96: False}
SIMPLE = {101: "oreb", 104: "dreb", 106: "tov", 103: "stl", 102: "blk", 110: "foul_drawn", 112: "in", 115: "out"}
FOULS = {109, 159, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169, 173, 537, 756, 761, 783}
AST_FG = {107, 108}
AST_FT = 119
STARTER = 599
# códigos conocidos sin efecto en el modelo
IGNORED = {105, 113, 116, 118, 121, 122, 123, 178, 179, 600, 748, 408, 409, 410, 411, 412, 413, 414, 415, 416, 417}
# playerStats -> tipo, para códigos que no estén en la tabla
_DELTA = (("threePointersMade", "shot3m"), ("threePointersAttempted", "shot3x"), ("twoPointersMade", "shot2m"),
          ("twoPointersAttempted", "shot2x"), ("freeThrowsMade", "ftm"), ("freeThrowsAttempted", "ftx"),
          ("offRebounds", "oreb"), ("defRebounds", "dreb"), ("turnovers", "tov"), ("steals", "stl"),
          ("blocks", "blk"), ("personalFouls", "foul"), ("foulsDrawn", "foul_drawn"), ("assists", "ast"))


def _str(v) -> str | None:
    return None if v is None or v == "" else str(v)


def _club(team: dict | None) -> str | None:
    team = team or {}
    return _str(team.get("clubId") or team.get("id"))


class AcbPBP(PBPSource):
    name = "acb_live"
    version = "1.0"

    def _headers(self, ctx: Ctx) -> dict:
        return {"X-APIKEY": ctx.cfg.get("api_key", PUBLIC_KEY), "Origin": "https://live.acb.com",
                "Referer": "https://live.acb.com/", "Accept": "application/json"}

    def _get(self, ctx: Ctx, path: str, params: dict) -> Any:
        return ctx.http.get_json(f"{ctx.cfg.get('base_url', API)}{path}", params=params, headers=self._headers(ctx))

    # ------------------------------------------------------------------ partidos
    def _calendar(self, ctx: Ctx) -> dict:
        p = ctx.main_payload if isinstance(ctx.main_payload, dict) else {}
        if p.get("calendar"):
            return p["calendar"]
        comp = int(ctx.cfg.get("competicion_id", 1))
        path = "/api/seasondata/Calendar/season-calendar"
        edition = ((ctx.cfg.get("temporadas") or {}).get(ctx.season) or {}).get("edition_id") or p.get("edition_id")
        if edition is None:
            seasons = (self._get(ctx, path, {"competitionId": comp}).get("availableFilters") or {}).get("seasons") or []
            match = [s for s in seasons if s.get("seasonStartYear") == ctx.start_year]
            if not match:
                return {}
            edition = match[0]["id"]
        return self._get(ctx, path, {"competitionId": comp, "editionId": edition})

    def games(self, ctx: Ctx) -> list[dict]:
        out, seen = [], set()
        for rnd in self._calendar(ctx).get("rounds") or []:
            phase = "playoffs" if rnd.get("subphaseId") else "regular"   # igual que adapters/acb.py
            for m in rnd.get("matches") or []:
                mid = str(m["id"])
                if mid in seen:
                    continue
                seen.add(mid)
                out.append({"game_id": mid, "phase": phase, "final": m.get("matchStatus") == "FINALIZED",
                            "date": m.get("startDateTime"), "round": rnd.get("roundNumber")})
        return out

    # ------------------------------------------------------------------ descarga
    def fetch(self, ctx: Ctx, ref: dict) -> dict:
        mid = ref["game_id"]
        raw: dict[str, Any] = {"pbp": self._get(ctx, "/api/matchdata/PlayByPlay/play-by-play", {"matchId": mid})}
        try:
            raw["shots"] = self._get(ctx, "/api/matchdata/MatchShots/match-shots", {"matchId": mid})
        except FetchError as exc:
            ctx.errors.append(f"MatchShots {mid}: {exc}")
            raw["shots"] = None
        box = ((ctx.main_payload or {}).get("boxscores") or {}).get(mid) if isinstance(ctx.main_payload, dict) else None
        if not box:
            try:
                box = self._get(ctx, "/api/matchdata/Result/boxscores", {"matchId": mid})
            except FetchError as exc:
                ctx.errors.append(f"boxscores {mid}: {exc}")
                box = None
        raw["box"] = box
        return raw

    # ------------------------------------------------------------------ interpretación
    def parse(self, raw: dict, ref: dict, ctx: Ctx) -> Game:
        pbp = raw.get("pbp") or {}
        box = raw.get("box")
        if not box and isinstance(ctx.main_payload, dict):
            box = (ctx.main_payload.get("boxscores") or {}).get(ref["game_id"])
        box = box or {}
        game_min = ctx.game_min
        home, away = _club(pbp.get("homeTeam")), _club(pbp.get("awayTeam"))
        tbs = box.get("teamBoxscores") or []
        if (not home or not away) and len(tbs) == 2:
            home, away = _club(tbs[0].get("team")), _club(tbs[1].get("team"))
        g = Game(game_id=str(ref["game_id"]), phase=ref.get("phase", "regular"), teams=[home, away],
                 date=ref.get("date"),
                 coord_system="ACB MatchShots posX/posY (unidades de la fuente, ≈mm; X desde la línea de fondo "
                              "hacia el centro, Y lateral desde el eje del aro; canasta atacada en X≈0)")
        for key, tid in (("homeTeam", home), ("awayTeam", away)):
            t = pbp.get(key) or {}
            g.team_names[tid] = t.get("fullName") or t.get("shortName") or tid
        box_starters: dict[str, list[str]] = defaultdict(list)
        for tb in tbs:
            tid = _club(tb.get("team"))
            if tid and tid not in g.team_names:
                g.team_names[tid] = (tb.get("team") or {}).get("fullName")
            q0 = next((p for p in tb.get("statsByPeriods") or [] if p.get("quarter") == 0), None)
            for pl in ((q0 or {}).get("stats") or {}).get("players") or []:
                info = pl.get("player") or {}
                pid = _str(info.get("id"))
                if not pid:
                    continue
                name = info.get("nickname") or f"{info.get('firstName', '')} {info.get('lastName', '')}".strip()
                g.players[pid] = {"nombre": name, "team": tid}
                sec = clock_to_seconds(pl.get("playTime")) if pl.get("playTime") else 0.0
                pm = pl.get("plusMinus")
                g.box[pid] = {"sec": sec, "pm": float(pm) if pm is not None else None}
                if pl.get("isStarted"):
                    box_starters[tid].append(pid)

        plays = sorted(pbp.get("plays") or [], key=lambda p: p.get("order") or 0)   # estable

        # coordenadas: enlace por (cuarto, minuto, segundo, jugador, playType) en orden de aparición
        coords: dict[tuple, list] = defaultdict(list)
        shot_rows = sorted(((raw.get("shots") or {}).get("shotPoints") or []), key=lambda s: s.get("id") or 0)
        for s in shot_rows:
            coords[(s.get("quarter"), s.get("minute"), s.get("second"), _str(s.get("playerLicenseId")),
                    s.get("playType"))].append(s)

        evs: list[Event] = []
        markers: list[tuple[int, str, str]] = []
        ft_markers: list[tuple[int, str, str]] = []
        starters: dict[str, list[str]] = defaultdict(list)
        prev_stats: dict[str, dict] = {}
        unknown: dict[int, int] = defaultdict(int)
        n_xy = 0
        for i, p in enumerate(plays):
            pt = p.get("playType")
            per = int(p.get("quarter") or 1)
            rem = (p.get("minute") or 0) * 60 + (p.get("second") or 0)
            t = elapsed(per, rem, game_min)
            tm = home if p.get("local") else away
            pid = _str(p.get("playerLicenseId"))
            stats = p.get("playerStats") or {}
            delta: set[str] = set()
            if pid and stats:
                old = prev_stats.get(pid, {})
                delta = {k for k, _ in _DELTA if (stats.get(k) or 0) > (old.get(k) or 0)}
                prev_stats[pid] = stats
            if pid and pid not in g.players:
                g.players[pid] = {"nombre": p.get("playerName") or pid, "team": tm}
            kw = {"order": i, "period": per, "t": t, "team": tm, "player": pid}
            if pt == STARTER:
                if pid and pid not in starters[tm]:
                    starters[tm].append(pid)
            elif pt in SHOTS or pt in FTS:
                x = y = None
                lst = coords.get((p.get("quarter"), p.get("minute"), p.get("second"), pid, pt))
                if lst:
                    s = lst.pop(0)
                    if pt in SHOTS and not (s.get("posX") == 0 and s.get("posY") == 0):
                        x, y = s.get("posX"), s.get("posY")
                        n_xy += 1
                if pt in SHOTS:
                    v, made = SHOTS[pt]
                    evs.append(Event(kind="shot", value=v, made=made, pts=v if made else 0, x=x, y=y, **kw))
                else:
                    made = FTS[pt]
                    evs.append(Event(kind="ft", value=1, made=made, pts=1 if made else 0, **kw))
            elif pt in SIMPLE:
                if pt in (112, 115) and not pid:
                    continue
                evs.append(Event(kind=SIMPLE[pt], **kw))
            elif pt in FOULS:
                evs.append(Event(kind="foul", **kw))
            elif pt in AST_FG:
                if pid:
                    markers.append((i, tm, pid))
            elif pt == AST_FT:
                if pid:
                    ft_markers.append((i, tm, pid))
            elif pt in IGNORED:
                continue
            elif pid and delta:
                # código no catalogado: se deduce del cambio en las estadísticas del jugador
                unknown[pt] += 1
                if "threePointersAttempted" in delta:
                    made = "threePointersMade" in delta
                    evs.append(Event(kind="shot", value=3, made=made, pts=3 if made else 0, **kw))
                elif "twoPointersAttempted" in delta:
                    made = "twoPointersMade" in delta
                    evs.append(Event(kind="shot", value=2, made=made, pts=2 if made else 0, **kw))
                elif "freeThrowsAttempted" in delta:
                    made = "freeThrowsMade" in delta
                    evs.append(Event(kind="ft", value=1, made=made, pts=1 if made else 0, **kw))
                elif "assists" in delta:
                    markers.append((i, tm, pid))
                else:
                    kind = next((k for s, k in _DELTA if s in delta and k in
                                 ("oreb", "dreb", "tov", "stl", "blk", "foul", "foul_drawn")), None)
                    if kind:
                        evs.append(Event(kind=kind, **kw))
            elif pid:
                unknown[pt] += 1
        g.events = evs
        g.starters = {t: v for t, v in starters.items() if len(v) == 5} or \
            {t: v for t, v in box_starters.items() if len(v) == 5}
        g.has_shots = n_xy > 0

        left = link_assists_by_adjacency(evs, markers)
        left_ft = self._link_ft_assists(evs, ft_markers)
        n_ast = len(markers) + len(ft_markers)
        g.has_assists = n_ast > 0
        if left:
            g.notes.append(f"{left}/{n_ast} asistencias sin enlazar")
        if left_ft:
            g.notes.append(f"{left_ft} asistencias a tiros libres sin ninguno anotado (la ACB las cuenta)")
        if unknown:
            g.notes.append("playType no catalogados: " + ",".join(f"{k}x{v}" for k, v in sorted(unknown.items())))
        if not g.box:
            g.notes.append("sin boxscore: no se pueden validar minutos ni +/-")
        return g

    @staticmethod
    def _link_ft_assists(events: list[Event], ft_markers: list[tuple[int, str, str]]) -> int:
        """119 = asistencia a una falta que acaba en tiros libres: va ANTES de los TL. Se enlaza con el
        primer TL anotado posterior del mismo equipo en la misma serie (mismo instante)."""
        by_order = sorted(events, key=lambda e: e.order)
        unlinked = 0
        for order, team, player in ft_markers:
            t0 = next((e.t for e in by_order if e.order > order), None)
            linked = False
            for e in by_order:
                if e.order <= order:
                    continue
                if e.t != t0 or e.kind == "shot":
                    break
                if e.kind == "ft" and e.team == team and e.made and e.assister is None:
                    e.assister, e.ast_ft, linked = player, True, True
                    break
            unlinked += 0 if linked else 1
        return unlinked
