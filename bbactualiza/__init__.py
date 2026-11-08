"""Actualización rápida de la temporada en curso (2026-27) con los modelos CONGELADOS.

Backend del botón «Actualizar 2026-27» del artifact (skill `.claude/skills/actualizar-temporada`). Tras la descarga
delta de los partidos nuevos, aplica a esa temporada los parámetros ya ajustados de cada capa —sin reajustar nada y
sin tocar las temporadas anteriores— y deja en una carpeta de publicación sólo los ficheros del artifact que cambian.

    python -m bbactualiza                       # descarga delta + capas + ficheros del artifact
    python -m bbactualiza --sin-descarga        # sólo capas y artifact con los datos ya descargados
    python -m bbactualiza --pasos normalizacion simulador

Las capas que sí se reajustan (redes CVAE de la normalización v3.2, RAPM de la v4.0, pesos del simulador…) se
rehacen en la recalibración mensual (`python -m bbactualiza.recalibrar`, ver docs/actualizacion_2026-27.md).
"""
TEMPORADA = "2026-27"
