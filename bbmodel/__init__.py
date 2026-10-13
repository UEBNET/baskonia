"""bbmodel — modelos de evaluación de jugadores sobre los datos de `bbstats`.

Algoritmo A («traductor por puestos + tipo de cambio»): lleva las métricas de un jugador de
cualquier liga a su equivalente en la liga de referencia (EuroLeague), separando el ENTORNO
(cómo se juega en cada liga) del NIVEL (lo difícil que es), con intervalos de incertidumbre.

Módulos, en el orden en que se usan:
    datos        carga los CSV de data/processed y monta la tabla jugador-liga-temporada
    identidad    reconoce al mismo jugador en distintas ligas y temporadas (persona_id)
    posicion     asigna a cada jugador un grupo de posición (exterior / alero / interior)
    metricas     catálogo de métricas: transformación, exposición y sentido de cada una
    suerte       paso 1: quita el ruido de muestras pequeñas (bayes empírico)
    enlace       paso 3: estima el «tipo de cambio» entre ligas con jugadores puente (EM)
    traductor    paso 4: traduce cada jugador a la EuroLeague con intervalos
    validacion   comprueba el algoritmo prediciendo cambios de liga reales
    evaluacion_ligas  cálculo de la pestaña «Evaluación de ligas» de la Mesa

Uso: python -m bbmodel --help
Documentación: docs/algoritmo_A.md
"""

__version__ = "0.1.0"
