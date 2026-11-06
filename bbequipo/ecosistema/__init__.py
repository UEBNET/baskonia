"""CERNO v4.1 · capa E (ecosistema del club): altas, bajas e impacto cruzado (docs/encargos/v4.1_ecosistema.md).

La capa E se apoya ENCIMA de la capa 4 de la v4.0 y consume, sin modificarlos, la normalización v3.2, el motor de minutos
v3.3 y las capas 1–5 de la v4.0 (β, φ, efectos dirigidos, h, capa 4, A5, NIVEL CERNO, IMPACTO). Configuración única:
configs/ecosistema_v41.yaml. Salidas: data/modelos/v4_1/.

Módulos (F0):
    orden_sinergias   prueba de orden de las sinergias (pareja, trío, quinteto) sobre tercios de partidos (§2.2)
    benchmark         benchmark de decisión sobre la v4.0 real (sustituye al informe que evaluó la rama main)
    ausencias         auditoría de ausencias para el banco V-AUS (§5.4)
    inventario        residuos de «Índice Fit» y «ADAPT» y referencias fijas a club y temporada (sólo inventario)
"""
