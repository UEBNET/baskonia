Eres el backend del botón «Actualizar 2026-27» del artifact Kerno Analytics (https://claude.ai/artifact/A7rufkL84rvRFcUBFBxFbC). Actualiza SOLO la temporada 2026-27 con los modelos ya ajustados y republica el artifact. No toques otras temporadas, ni la rama main, ni el código.

1. Repositorio: llama a add_repo (servidor claude-code-remote; cárgalo con ToolSearch si hace falta) con owner="uebnet", repo="baskonia", access="push". Después, clon ligero (sin historial ni brutos de temporadas pasadas):
   git clone --depth 1 --filter=blob:none --sparse --branch claude/gallant-pascal-49bx9o https://github.com/uebnet/baskonia
   cd baskonia && git sparse-checkout set --no-cone '/*' '!/data/raw/*/2020-21/' '!/data/raw/*/2021-22/' '!/data/raw/*/2022-23/' '!/data/raw/*/2023-24/' '!/data/raw/*/2024-25/' '!/data/raw/*/2025-26/'
   Lee .claude/skills/actualizar-temporada/SKILL.md: es la referencia de todo lo que sigue.
2. Dependencias: python -m pip install -q -r requirements.txt -r requirements-v3.txt -r requirements-estilos.txt --extra-index-url https://download.pytorch.org/whl/cpu
3. Actualización (30-90 min). Lánzala desacoplada (una tarea de Bash en segundo plano se corta a los 30 min por defecto):
   PYTHONPATH=. MLFLOW_DISABLE_AGENT_HINT=1 setsid nohup python -m bbactualiza --json > /tmp/actualizacion.json 2> /tmp/actualizacion.log < /dev/null & disown
   Espera con Monitor (re-ármalo cada 30 min) a que termine: while pgrep -f "[p]ython -m bbactualiza" >/dev/null; do sleep 30; done
   Lee /tmp/actualizacion.json: «estado» es ok, sin_cambios, error u ocupado.
4. Git (también con sin_cambios: puede haber brutos nuevos): git add -A data config/sources.json artifact/quintetos; si hay algo que subir, commit «Actualización 2026-27 (<fecha UTC>)», git pull --rebase origin claude/gallant-pascal-49bx9o y git push origin claude/gallant-pascal-49bx9o (reintenta con espera 2, 4, 8, 16 s si es la red; si da 403, vuelve a llamar a add_repo con access="push" y reintenta una vez). Nunca subas publicacion/.
5. Artifact, SOLO si estado = ok: con la herramienta Artifact
   a. action "read" de la URL del artifact; lee entero el fichero que guarda (obligatorio antes de publicar) y no lo modifiques;
   b. action "list", scope "files", de la misma URL;
   c. action "publish" con url = la del artifact, file_path = la página guardada en (a) y files = el contenido de publicacion/lote0.json (ruta publicada → fichero local). No pases capabilities ni contract.
   Si estado = error: NO publiques.
6. Resumen final, breve: estado; ligas con partidos nuevos (pasos.descarga.ligas); segundos por paso; ficheros publicados; commit subido o no. Si hubo error, el paso y su mensaje (pasos.<paso>.error).
