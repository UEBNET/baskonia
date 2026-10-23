"""bbfit: roles, entropía, reemplazo de rol, adaptación entre ligas y simulador de encaje (fit-in) v2.

Capas: raw (data/raw) → clean (data/processed) → features/modelos (data/modelos) → simulación → salidas.
Umbrales e hiperparámetros en configs/*.yaml (nada fijado en el código); experimentos en MLflow
(experimentos/mlruns, no versionado) con un resumen versionado en data/modelos/<módulo>/.
"""
