"""bbstats — extracción y normalización de estadísticas de baloncesto multi-liga.

Uso rápido:
    from bbstats import ejecutar, reprocesar, estado
    informe = ejecutar()                       # descarga todas las ligas activas y procesa
    informe = ejecutar(ligas=["acb", "euroleague"], temporada="2025-26")
    informe = reprocesar()                     # reprocesa el último JSON bruto, sin red
"""
__version__ = "1.0.0"

from .api import datos, diccionario, estado, ejecutar, reprocesar  # noqa: E402

__all__ = ["ejecutar", "reprocesar", "estado", "datos", "diccionario", "__version__"]
