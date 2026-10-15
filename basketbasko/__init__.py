"""Extractor de la intranet de clubes de la Federación Vasca de Baloncesto (clubes.basketbasko.com).

La intranet es una aplicación React (plataforma de Optimal Way Consulting) que obtiene los datos de dos APIs JSON:

- ESB (`url_esb`): login del club y datos del club (`/public/club/login`, `/auth/my-club`, `/auth/my-teams`...).
- Estadísticas (`url_stats`): `/<fede>/teams/<teamUuid>/stats`, `/<fede>/players/<uuid>/teams/<teamUuid>/stats`
  y `/<fede>/matches/<matchCallUuid>/stats`.

Flujo: login → mis equipos → estadísticas de cada equipo → (jugadores de la plantilla, partidos jugados,
equipos rivales) → JSON bruto con fecha → tablas CSV/JSON normalizadas → resumen + dashboard HTML.
"""
