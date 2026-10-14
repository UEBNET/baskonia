"""bbestilo: estilos de juego de los clubes por temporada con una red neuronal VaDE.

Sobre los datos NORMALIZADOS del proyecto (equivalentes EuroLeague de los algoritmos A y B de
bbmodel, combinados A+B) se construye un perfil de estilo por jugador y por club-competición-
temporada, se le quita la parte que explica el nivel y una red VaDE (autoencoder variacional con
previa de mezcla de 6 gaussianas) da un mapa 3D y una capa de salida de 6 neuronas (una por estilo).
Incluye la simulación de fichajes y bajas (encaje.py) y el buscador de parecidos (similares.py).

Documentación: docs/estilos_de_juego.md · CLI: python -m bbestilo --help
"""
