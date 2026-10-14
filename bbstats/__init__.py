"""bbstats — extracción y normalización de estadísticas de baloncesto multi-liga.

Uso rápido:
    from bbstats import ejecutar, reprocesar, estado
    informe = ejecutar()                       # descarga todas las ligas activas y procesa
    informe = ejecutar(ligas=["acb", "euroleague"], temporada="2025-26")
    informe = reprocesar()                     # reprocesa el último JSON bruto, sin red
    informes = ejecutar_temporadas()           # carga histórica: temporada_inicial .. temporada_por_defecto
"""
__version__ = "1.1.0"

from .api import datos, diccionario, estado, ejecutar, ejecutar_temporadas, reprocesar  # noqa: E402

__all__ = ["ejecutar", "ejecutar_temporadas", "reprocesar", "estado", "datos", "diccionario", "__version__"]
