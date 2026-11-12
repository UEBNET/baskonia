# Regeneración en producción tras la PR #7 (instrucciones para una sesión de producción)

Lánzalo como sesión nueva de Claude Code (o como ejecución manual de la tarea programada de recalibración, con estos
pasos añadidos). Rama: `claude/jolly-thompson-qczxl4`; nunca `main`.

Contexto: se fusionó UEBNET/baskonia#7, que corrige:
- la fecha de los partidos de BNXT, BSL y GBL en `bbstats/entrenadores.py`;
- la lectura de la DT por par en `bbnorm3/destino.py` (`vara.json`).

Hay que regenerar las capas que dependen de esas correcciones, con las 21 ligas, y republicar los tres artifacts.

1. **Repositorio.** Clon ligero como en `.claude/skills/actualizar-temporada/recalibracion_prompt.md`, paso 1. Comprueba
   que el último commit es la fusión de la PR #7 (`fd0bf66`) o posterior.
2. **Dependencias**, como en ese mismo prompt, paso 2.
3. **Capas que leen los tramos de entrenador**, sin descarga:
   - `python -m bbfit roles`
   - `python -m bbfit reemplazo`
   - `python -m bbestilo entrenadores`

   Los cambios deben concentrarse en BNXT, BSL y GBL, en 2026-27 y en las tablas agregadas. Si cambian mucho otras ligas,
   para. Commit y push.
4. **Modelos congelados del simulador v3.3**, con `CERNO_SIMULADOR=v33`:
   - borra de `bbfit.sim_insumos.DIR_CACHE` los ficheros `modelos_hasta_2024-25.pkl` y `modelos_hasta_2025-26.pkl`;
   - rehazlos con `python -c "from bbfit import sim_insumos as SI; [SI.modelos_hasta(t) for t in ('2024-25','2025-26')]"`;
   - cópialos a `data/modelos/simulador/v3_3/congelado/`.

   Commit y push.
5. **`vara.json`.** `python -m pytest -q tests/test_v32.py`, y comprobar que el fichero publicado tras la Liga U refleja
   la lectura corregida. Si no, regenerarlo (CHANGELOG del 09-11).
6. **Recalibración completa**, desacoplada como en `recalibracion_prompt.md`, paso 3:
   `python -m bbactualiza.recalibrar`. Hace falta la completa porque la v4.0 usa el RAPM y la latente CVAE, que no están
   en Git.
7. **Git y publicación** como en `recalibracion_prompt.md`, pasos 4 y 5. Si algún paso falló, no publiques.
8. **Resumen:**
   - cambios por capa;
   - tiempos;
   - ficheros publicados por artifact;
   - commits.
