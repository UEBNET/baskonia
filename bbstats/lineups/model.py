"""Modelo común de jugada a jugada (play-by-play) para todas las ligas.

Cada fuente (bbstats/lineups/sources/*) convierte sus datos originales de un partido en un `Game` con una
lista de `Event` en el MISMO formato. A partir de aquí todo es común: reconstrucción de tramos (quién está en
pista), quintetos, tríos, parejas, on/off, RAPM, redes de asistencias y tiros por quinteto.

Convenciones:
  * `t` = segundos transcurridos desde el inicio del partido (no el reloj restante). Usar `elapsed()`.
  * `team` y `player` son ids de la fuente en texto. Rebotes, pérdidas o faltas de equipo: `player=None`.
  * Tiros de campo: kind="shot", value=2|3, made, pts (= value si anotado). Tiros libres: kind="ft", value=1
    (en la G League un tiro libre único puede valer 2 o 3: pts lo indica), made, pts.
  * La asistencia NO es un evento aparte: la fuente la enlaza y la pone en `assister` del tiro anotado
    (o del tiro libre si la fuente asigna asistencias a tiros libres; `ast_ft=True`).
  * Cambios: kind="in"/"out" con el jugador que entra/sale. Las fuentes que dan el cambio como un único
    evento lo separan en dos (primero "out", después "in").
  * Robos "stl" (jugador que roba), tapones "blk" (jugador que tapona), faltas "foul" (comete) y
    "foul_drawn" (recibe), pérdidas "tov", rebotes "oreb"/"dreb".
  * `order` = posición en la lista original (desempata eventos con el mismo `t`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

KINDS = {"in", "out", "shot", "ft", "oreb", "dreb", "tov", "stl", "blk", "foul", "foul_drawn"}


@dataclass
class Event:
    order: int
    period: int
    t: float
    kind: str
    team: str | None = None
    player: str | None = None
    made: bool | None = None
    value: int = 0
    pts: int = 0
    assister: str | None = None
    ast_ft: bool = False
    x: float | None = None
    y: float | None = None


@dataclass
class Game:
    game_id: str
    phase: str                      # "regular" | "playoffs"
    teams: list[str]                # [local, visitante] (ids de equipo de la fuente)
    team_names: dict[str, str] = field(default_factory=dict)
    players: dict[str, dict] = field(default_factory=dict)      # pid -> {"nombre":..., "team": tid}
    starters: dict[str, list[str]] = field(default_factory=dict)  # tid -> 5 pids (vacío = inferir)
    events: list[Event] = field(default_factory=list)
    box: dict[str, dict] = field(default_factory=dict)           # pid -> {"sec": float|None, "pm": float|None}
    date: str | None = None
    has_lineups: bool = True        # False si la fuente no permite saber quién está en pista
    has_assists: bool = True
    has_shots: bool = True          # coordenadas de tiro
    coord_system: str = ""          # descripción de x/y de la fuente
    notes: list[str] = field(default_factory=list)


def period_length(period: int, game_min: float) -> float:
    """Duración (s) del periodo: cuartos de game_min/4 minutos; prórrogas de 5 minutos."""
    return game_min / 4 * 60 if period <= 4 else 300.0


def period_start(period: int, game_min: float) -> float:
    q = game_min / 4 * 60
    return q * (period - 1) if period <= 5 else 4 * q + 300.0 * (period - 5)


def elapsed(period: int, remaining_s: float | None = None, game_min: float = 40,
            elapsed_in_period_s: float | None = None) -> float:
    """Segundos desde el inicio del partido a partir del reloj restante (o transcurrido) del periodo."""
    start, length = period_start(period, game_min), period_length(period, game_min)
    if elapsed_in_period_s is not None:
        return start + max(0.0, min(length, float(elapsed_in_period_s)))
    rem = 0.0 if remaining_s is None else max(0.0, min(length, float(remaining_s)))
    return start + length - rem


def clock_to_seconds(txt: str | None) -> float | None:
    """"09:20" | "9:20" | "00:09:34" | "PT9M2.5S" -> segundos."""
    if txt is None:
        return None
    s = str(txt).strip()
    if not s:
        return None
    if s.startswith("PT"):
        import re
        m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?", s)
        if not m:
            return None
        h, mi, se = (float(g) if g else 0.0 for g in m.groups())
        return h * 3600 + mi * 60 + se
    parts = [float(p) for p in s.split(":")]
    out = 0.0
    for p in parts:
        out = out * 60 + p
    return out


def link_assists_by_adjacency(events: list[Event], assist_markers: list[tuple[int, str, str]]) -> int:
    """Enlaza asistencias dadas como eventos sueltos al tiro anotado más cercano ANTERIOR del mismo equipo.

    assist_markers: (order, team, player) de los eventos de asistencia de la fuente (no están en `events`).
    Se retrocede saltando cambios, faltas, etc.; se para si aparece un tiro del rival. Devuelve cuántas
    asistencias quedaron sin enlazar."""
    import bisect
    by_order = sorted(events, key=lambda e: e.order)
    orders = [e.order for e in by_order]
    unlinked = 0
    for order, team, player in assist_markers:
        i = bisect.bisect_left(orders, order) - 1
        linked = False
        while i >= 0:
            e = by_order[i]
            if e.kind in ("shot", "ft") and e.made and e.team == team:
                if e.assister is None and e.player != player:
                    e.assister = player
                    e.ast_ft = e.kind == "ft"
                    linked = True
                break
            if e.kind == "shot" and e.team != team:
                break
            i -= 1
        unlinked += 0 if linked else 1
    return unlinked
