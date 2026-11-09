Recalibración mensual de la temporada 2026-27 del artifact Kerno Analytics (https://claude.ai/artifact/A7rufkL84rvRFcUBFBxFbC): reentrena lo que el botón «Actualizar 2026-27» aplica congelado (redes CVAE de la normalización v3.2 y modelo de equipo v4.0) y republica. Sólo cambia la temporada 2026-27; el histórico se restaura desde Git automáticamente. No toques la rama main ni el código.

1. Repositorio: add_repo (servidor claude-code-remote; cárgalo con ToolSearch si hace falta) con owner="uebnet", repo="baskonia", access="push". Clon ligero:
   git clone --depth 1 --filter=blob:none --sparse --branch claude/gallant-pascal-49bx9o https://github.com/uebnet/baskonia
   cd baskonia && git sparse-checkout set --no-cone '/*' '!/data/raw/*/2020-21/' '!/data/raw/*/2021-22/' '!/data/raw/*/2022-23/' '!/data/raw/*/2023-24/' '!/data/raw/*/2024-25/' '!/data/raw/*/2025-26/'
   Lee docs/actualizacion_2026-27.md §4 y .claude/skills/actualizar-temporada/SKILL.md.
2. python -m pip install -q -r requirements.txt -r requirements-v3.txt -r requirements-estilos.txt --extra-index-url https://download.pytorch.org/whl/cpu
3. Lánzalo desacoplado (2,5-4 h; una tarea de Bash en segundo plano se corta a las 2 h, así que no la uses para esto):
   PYTHONPATH=. MLFLOW_DISABLE_AGENT_HINT=1 setsid nohup python -m bbactualiza.recalibrar > /tmp/recal.log 2>&1 < /dev/null & disown
   Espera con Monitor (re-ármalo cada 30 min) a que termine: while pgrep -f "[b]bactualiza.recalibrar" >/dev/null; do sleep 60; done
   El resultado queda en data/modelos/actualizacion/ultima_recalibracion.json («estado» ok o error, y cada paso).
   Si el proceso muere sin escribir ese fichero, relánzalo igual: las redes y las traducciones ya calculadas están en
   caché (experimentos/v3) y se retoma donde se quedó.
4. Git: git add -A data artifact/quintetos; commit «Recalibración mensual 2026-27 (<fecha UTC>)»; git pull --rebase origin claude/gallant-pascal-49bx9o; git push origin claude/gallant-pascal-49bx9o (reintentos 2, 4, 8, 16 s si es la red). Nunca subas publicacion/.
5. Si los tres pasos acabaron en ok: Artifact «read» de la URL (lee entera la página guardada, sin modificarla), «list» con scope «files», y «publish» con url = la del artifact, file_path = la página guardada y files = el contenido de publicacion/lote0.json. No pases capabilities. Si algún paso falló, NO publiques.
6. Resumen breve: estado y segundos de cada paso (cvae, v40, boton), ficheros publicados y commit.
