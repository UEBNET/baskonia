"""Capa Federación Vasca de Baloncesto (ESF · Euskal Saskibaloi Federazioa · basketbasko.com).

Arquitectura por capas (ver docs/BASKO.md):
  1. Extractores por fuente  → bbstats/esf/extractor.py  (un adaptador por liga, configurado en config/basko.json)
  2. Almacén bruto           → data/basko/raw/<liga>/<temporada>/<liga>_<temporada>_<fecha>.json.gz (sin tocar)
  3. Normalización y métricas → bbstats/esf/eventos.py (jugada a jugada), bbstats/esf/construir.py (tablas)
  4. Salida unificada        → data/basko/processed/<temporada>/... (mismas columnas en todas las ligas)
  5. Ejecución bajo demanda  → python ejecutar_basko.py  |  python -m bbstats.esf ejecutar
"""
__version__ = "1.0.0"
