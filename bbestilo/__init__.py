"""bbestilo: estilos de juego de los clubes por temporada con dos redes neuronales.

Sobre los datos NORMALIZADOS del proyecto (equivalentes EuroLeague de los algoritmos A y B de
bbmodel, combinados A+B) se construye un perfil de estilo por jugador y por club-competición-
temporada, y dos redes con una capa de salida de 12 neuronas (una por estilo) y un mapa 3D:

    red 1  IDEC  autoencoder profundo con capa de agrupamiento (núcleo t de Student)
    red 2  VaDE  autoencoder variacional con previa de mezcla de 12 gaussianas

Documentación: docs/estilos_de_juego.md · CLI: python -m bbestilo --help
"""
