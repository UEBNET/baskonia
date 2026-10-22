"""Reconstrucción de posesiones a partir del jugada a jugada (modelo común de eventos, válido para todas las ligas).

El resto de la capa de quintetos NO numera posesiones: estima las de cada tramo con la fórmula de caja
FGA − OREB + TOV + coef·FTA (stints/metrics). Este módulo cuenta posesiones REALES evento a evento y asigna
un `possession_id` (contador por partido) a cada evento, para comparar con la estimación.

Una posesión del equipo X termina con:
  * canasta de campo anotada de X (salvo «2+1»: si el siguiente evento relevante es un tiro libre de X en el
    mismo segundo, la posesión termina con esa tanda de tiros libres);
  * pérdida de X;
  * rebote defensivo del rival tras un fallo de X (de campo o del último tiro libre);
  * último tiro libre ANOTADO de una tanda de X (tanda = tiros libres seguidos de X en el mismo segundo).
Si tras un fallo de X actúa el rival (tiro, tiro libre o pérdida) sin rebote anotado, se supone un rebote
defensivo implícito (algunas fuentes, como el jugada a jugada en texto de la FEB 2020-24, omiten rebotes).
Al acabar un periodo, un fallo sin rebote cierra la posesión del que tiró (como la fórmula de caja: cada FGA
cuenta salvo que haya OREB). No se cuentan las posesiones que acaban por fin de periodo sin tiro ni pérdida, y un
tiro libre técnico anotado cuenta como fin de posesión (sesgo pequeño, documentado).
Eventos relevantes: shot, ft, oreb, dreb, tov (cambios, faltas, robos y tapones no cambian la posesión por sí
mismos: el robo va siempre con la pérdida del rival).
"""
from __future__ import annotations

from collections import Counter

from .model import Event

RELEVANT = {"shot", "ft", "oreb", "dreb", "tov"}


def count_possessions(events: list[Event], teams: list[str]) -> tuple[Counter, dict[int, int]]:
    """Devuelve (posesiones por equipo, {order del evento: possession_id}).

    possession_id empieza en 1 y aumenta cada vez que termina una posesión; los eventos entre dos finales
    comparten id."""
    evs = sorted((e for e in events if e.kind in RELEVANT and e.team in teams), key=lambda e: e.order)
    n = Counter()
    pid_of: dict[int, int] = {}
    current = 1
    last_miss_team: str | None = None
    pending: tuple[str, float] | None = None       # canasta anotada a la espera de un posible 2+1

    def end(team: str) -> None:
        nonlocal current
        n[team] += 1
        current += 1

    period = evs[0].period if evs else None
    for i, e in enumerate(evs):
        if e.period != period:
            # fin de periodo: un fallo sin rebote (último tiro) cierra la posesión del que tiró, como en la
            # fórmula de caja (cada FGA cuenta salvo que haya OREB)
            if pending is None and last_miss_team is not None:
                end(last_miss_team)
            last_miss_team = None
            period = e.period
        if pending is not None:
            team_p, t_p = pending
            pending = None
            if not (e.kind == "ft" and e.team == team_p and abs(e.t - t_p) <= 1.0):
                end(team_p)
        if last_miss_team is not None and e.team != last_miss_team and e.kind in ("shot", "ft", "tov"):
            # el rival actúa tras un fallo sin rebote anotado: rebote defensivo implícito (la fuente lo omitió)
            end(last_miss_team)
            last_miss_team = None
        pid_of[e.order] = current
        if e.kind == "shot":
            if e.made:
                pending = (e.team, e.t)
                last_miss_team = None
            else:
                last_miss_team = e.team
        elif e.kind == "ft":
            nxt = evs[i + 1] if i + 1 < len(evs) else None
            last_of_trip = not (nxt is not None and nxt.kind == "ft" and nxt.team == e.team and abs(nxt.t - e.t) <= 1.0)
            if last_of_trip:
                if e.made:
                    end(e.team)
                    last_miss_team = None
                else:
                    last_miss_team = e.team
        elif e.kind == "tov":
            end(e.team)
            last_miss_team = None
        elif e.kind == "dreb":
            if last_miss_team is not None and last_miss_team != e.team:
                end(last_miss_team)
            last_miss_team = None
        elif e.kind == "oreb":
            last_miss_team = None
    if pending is not None:
        end(pending[0])
    elif last_miss_team is not None:
        end(last_miss_team)
    return n, pid_of


def box_possessions(fga: float, fta: float, oreb: float, tov: float, coef: float = 0.44) -> float:
    """Estimación de caja de las posesiones de un equipo: FGA + coef·FTA − OREB + TOV."""
    return fga + coef * fta - oreb + tov
