Recalibración mensual de la temporada 2026-27 de Kerno Analytics (tres artifacts: Jugadores https://claude.ai/artifact/A7rufkL84rvRFcUBFBxFbC, Equipos https://claude.ai/artifact/SXFgQ6CpytxT3ZZupcEFcj y Metodología https://claude.ai/artifact/T83MBGZk5untACmegadfNn): reentrena lo que el botón «Actualizar 2026-27» aplica congelado (redes CVAE de la normalización v3.2 y modelo de equipo v4.0) y republica. Sólo cambia la temporada 2026-27; el histórico se restaura desde Git automáticamente. No toques la rama main ni el código.

1. Repositorio: add_repo (servidor claude-code-remote; cárgalo con ToolSearch si hace falta) con owner="uebnet", repo="baskonia", access="push". Clon ligero:
   git clone --depth 1 --filter=blob:none --sparse --branch claude/jolly-thompson-qczxl4 https://github.com/uebnet/baskonia
   cd baskonia && git sparse-checkout set --no-cone '/*' '!/data/raw/*/2020-21/' '!/data/raw/*/2021-22/' '!/data/raw/*/2022-23/' '!/data/raw/*/2023-24/' '!/data/raw/*/2024-25/' '!/data/raw/*/2025-26/'
   Lee .claude/skills/actualizar-temporada/recalibracion_prompt.md (versión vigente de estas instrucciones; si difiere de este texto, manda el del repositorio), docs/actualizacion_2026-27.md §4 y la SKILL.md de esa carpeta.
2. Dependencias (con python -m pip: pip y python pueden ser intérpretes distintos): python -m pip install -q -r requirements.txt -r requirements-v3.txt -r requirements-estilos.txt --extra-index-url https://download.pytorch.org/whl/cpu
3. Lánzalo desacoplado (2,5-4 h; una tarea de Bash en segundo plano se corta a las 2 h, así que no la uses para esto):
   PYTHONPATH=. MLFLOW_DISABLE_AGENT_HINT=1 setsid nohup python -m bbactualiza.recalibrar > /tmp/recal.log 2>&1 < /dev/null & disown
   Espera con Monitor (re-ármalo cada 30 min) a que termine: while pgrep -f "[b]bactualiza.recalibrar" >/dev/null; do sleep 60; done
   El resultado queda en data/modelos/actualizacion/ultima_recalibracion.json («estado» ok o error, y cada paso).
   Si el proceso muere sin escribir ese fichero, relánzalo igual: las redes y las traducciones ya calculadas están en
   caché (experimentos/v3) y se retoma donde se quedó.
4. Git: git add -A data artifact/quintetos artifact/kerno/quintetos/datos_v42 artifact/kerno/sitios; commit «Recalibración mensual 2026-27 (<fecha UTC>)»; git pull --rebase origin claude/jolly-thompson-qczxl4; git push origin claude/jolly-thompson-qczxl4 (reintentos 2, 4, 8, 16 s si es la red). Nunca subas publicacion/.
5. Si los tres pasos acabaron en ok: lee publicacion/sitios.json y, para cada sitio (jugadores, equipos, metodologia), Artifact «read» de SU url (lee entera la página guardada, sin modificarla), «list» con scope «files», y un «publish» por cada lote suyo (publicacion/lote_<sitio>_<n>.json) con url = la de ese sitio, file_path = su página guardada y files = el contenido del lote. No pases capabilities. Nunca publiques el lote de un sitio en la url de otro. Si algún paso falló, NO publiques.
6. Resumen breve: estado y segundos de cada paso (cvae, v40, boton), ficheros publicados por artifact y commit.
