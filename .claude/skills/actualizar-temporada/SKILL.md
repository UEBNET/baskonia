---
name: actualizar-temporada
description: Backend del botón «Actualizar 2026-27» de Kerno Analytics, que desde la v4.2 son tres artifacts (Jugadores https://claude.ai/artifact/A7rufkL84rvRFcUBFBxFbC, Equipos https://claude.ai/artifact/SXFgQ6CpytxT3ZZupcEFcj y Metodología https://claude.ai/artifact/T83MBGZk5untACmegadfNn). Descarga sólo los partidos nuevos de la temporada en curso en las 21 ligas (con la Liga U de la ACB desde el 09-11-2026), aplica a esa temporada los modelos ya ajustados (normalización v3.2, contexto, roles, estilos, simulador v3.3, tríos y parejas v4.2) sin reajustar ni tocar el histórico, sube los datos a Git y republica en cada artifact sólo los ficheros suyos que cambian. Úsala cuando la lance la Routine «Actualizar 2026-27 · Kerno» o cuando pidan «actualizar los datos de la temporada», «pulsar el botón de actualización» o «poner al día 2026-27».
---

# Actualizar la temporada en curso (botón del artifact)

El botón del artifact lanza la Routine **«Actualizar 2026-27 · Kerno»**, y la Routine abre una sesión de Claude Code que
sigue esta skill. Todo el cálculo lo hace un único programa, `python -m bbactualiza` (paquete `bbactualiza/`), así
que la sesión sólo prepara el entorno, lanza el programa, sube los datos y publica.

**Tres artifacts (v4.2, 09-11-2026).** El producto se dividió por secciones en tres artifacts con los mismos ficheros
fuente (docs/checkpoints/V42_sitios.md):
   * Jugadores · https://claude.ai/artifact/A7rufkL84rvRFcUBFBxFbC (lleva el botón)
   * Equipos · https://claude.ai/artifact/SXFgQ6CpytxT3ZZupcEFcj
   * Metodología · https://claude.ai/artifact/T83MBGZk5untACmegadfNn

Cada uno publica sólo las rutas de su manifiesto (`artifact/kerno/sitios/<sitio>.json`). El programa reparte el lote de
la actualización entre los tres (`bbactualiza.sitios`): `publicacion/sitios.json` dice, para cada sitio, su URL y sus
lotes `publicacion/lote_<sitio>_<n>.json` (cada uno cabe en una publicación: ≤ 58 MB y ≤ 250 ficheros). Jugadores ya no
publica los quintetos: el reparto nunca le devuelve una ruta de `borrar_al_republicar`.

**Regla de oro: sólo cambia la temporada en curso (2026-27).** El histórico 2020-21 … 2025-26 es estático: los
ficheros que guardan todas las temporadas se reescriben sustituyendo sólo las filas de 2026-27 (`bbactualiza.capas.empalmar`),
y el resto de líneas queda byte a byte igual.

## Pasos de la sesión (Routine)

1. **Repositorio**: `add_repo` (owner `uebnet`, repo `baskonia`, access `push`) y clon ligero de la rama de trabajo
   (sin el historial y sin los brutos de temporadas pasadas, que no se usan):
   ```bash
   git clone --depth 1 --filter=blob:none --sparse --branch claude/jolly-thompson-qczxl4 https://github.com/uebnet/baskonia
   cd baskonia && git sparse-checkout set --no-cone '/*' '!/data/raw/*/2020-21/' '!/data/raw/*/2021-22/' '!/data/raw/*/2022-23/' '!/data/raw/*/2023-24/' '!/data/raw/*/2024-25/' '!/data/raw/*/2025-26/'
   ```
   **Ligas (09-11-2026): 21**, todas las `activa: true` de `config/sources.json`. La Liga U de la ACB (`ligau`, sub-22,
   desde 2025-26) se descarga con el adaptador FEB (competición `g=74`): necesita en la red del entorno los mismos hosts
   que las FEB (`baloncestoenvivo.feb.es`, `intrafeb.feb.es`). Si una liga falla con `CONNECT tunnel failed, response
   403`, el host no está permitido en ese entorno: el programa sigue con el bruto anterior y lo anota en el informe.
2. **Dependencias** (≈ 1 min si el entorno no las trae ya):
   `python -m pip install -r requirements.txt -r requirements-v3.txt -r requirements-estilos.txt --extra-index-url https://download.pytorch.org/whl/cpu`
3. **Actualización** (30-90 min), desacoplada para que no la corte el límite de las tareas de Bash en segundo plano
   (30 min por defecto, 2 h como máximo):
   `PYTHONPATH=. MLFLOW_DISABLE_AGENT_HINT=1 setsid nohup python -m bbactualiza --json > /tmp/actualizacion.json 2> /tmp/actualizacion.log < /dev/null & disown`
   y espera con Monitor a que acabe (`while pgrep -f "[p]ython -m bbactualiza" >/dev/null; do sleep 30; done`).
   * Código 0: `estado` = `ok` (hay ficheros que publicar) o `sin_cambios` (no hay partidos nuevos: no se
     recalcula ni se publica nada; termina aquí tras subir los brutos nuevos, si los hay).
   * Código 1: un paso falló. **No publiques**; resume el error (`pasos.<paso>.error`) y termina.
   * Código 2: ya había otra actualización en curso.
4. **Git**: `git add -A data/ config/sources.json artifact/quintetos/*.gz.txt artifact/kerno/quintetos/datos_v42 artifact/kerno/sitios`
   (nunca `publicacion/`), commit «Actualización 2026-27 (<fecha>)», `git pull --rebase` y `git push origin claude/jolly-thompson-qczxl4`
   (reintentos con espera si es la red; si da 403, vuelve a llamar a `add_repo` con `push`).
5. **Artifacts** (sólo si `estado` = `ok`): lee `publicacion/sitios.json` y, **para cada sitio en este orden — Jugadores,
   Equipos, Metodología —** con la herramienta Artifact:
   * `action: "read"` de su URL (guarda la página publicada; léela entera, es obligatorio antes de publicar, y no la
     modifiques: cada artifact tiene su propia página, con su título y su `sitio.json`);
   * `action: "list"`, `scope: "files"` de esa URL (rutas que se van a sustituir);
   * por cada lote de `lotes` (normalmente uno): `action: "publish"` con `url` = la de ese sitio, `file_path` = su página
     guardada **sin cambios** y `files` = el contenido del lote (ruta publicada → fichero local). No pases
     `capabilities` ni `contract` (se conservan: Jugadores tiene `mcp` para el botón; Equipos y Metodología, `downloads`
     y `sample`).
   Nunca publiques el lote de un sitio en la URL de otro. Si la publicación de un sitio falla, sigue con los demás y
   dilo en el resumen. Si `sin_sitio` no está vacío, esas rutas no se publican: nómbralas en el resumen. Las
   `rutas_nuevas` (p. ej. la primera vez que una liga tiene alineaciones en la temporada) ya van en los lotes de los
   sitios que publican sus hermanas y quedan anotadas en los manifiestos (se suben en el paso 4).
6. **Resumen** para el usuario: estado por liga (partidos nuevos), segundos por paso, ficheros publicados **por
   artifact** (y versión resultante), rutas nuevas o sin sitio, commit.

## Qué calcula `python -m bbactualiza`

| Paso | Qué hace | Qué escribe (sólo 2026-27) |
|---|---|---|
| `descarga` | descarga delta (`actualizar_delta.py`): cada liga pide sólo los partidos que faltan; si una web falla se reprocesa su último bruto | `data/raw/<liga>/2026-27/`, `data/processed/2026-27/` |
| — | **huella** de los datos procesados: si no ha cambiado desde la última actualización, para aquí (`sin_cambios`) | |
| `pista` | zonas de tiro y on/off, interacciones, nacionalidades | `pista/2026-27.csv`, `interacciones/efectos_2026-27`, filas 2026-27 de `nacionalidades.csv` |
| `normalizacion` | A con σ², τ², enlace congelados (μ del entorno recentrado), amortiguada con los δ y λ guardados, B vigente, ids de persona estables, v2 y **v3.2 incremental** (CVAE congelada de la última recalibración + v2 al día, con los pesos por métrica del examen) | traducciones A/B/amortiguada, `normalizado/2026-27.csv`, `v3_2/normalizado/2026-27.csv.gz` |
| `contexto` | contexto de nivel con la escala fija 2020-26 y segunda pasada del dataset normalizado | `contexto/2026-27.csv`, filas 2026-27 de `por_jugador_liga.csv` |
| `roles` | roles por minutos y tramos (reglas y BOCPD) | filas 2026-27 de `roles/*` |
| `entropia`, `estilos` | entropía y volatilidad; estilos unificados con la mezcla ajustada en 2020-26 (semilla fija) | `entropia/`, `estilos_unificados/` |
| `simulador` | dataset del simulador v3.3 y exportación al navegador con los pesos congelados | `data/artifact/simulador/` |
| `artifact` | tablas de datos, nacionalidades, evaluación de ligas, normalizados v3.2, Atlas (estilos e informe), quintetos | `data/artifact/` (no versionado) |
| `v42` | tríos, parejas y sinergia v4.2 de la temporada con los parámetros congelados (`bbequipo.v42.actualizar`; el filtro es causal, las temporadas cerradas no cambian). La previa del historial de jugador v4.2 sólo depende de temporadas cerradas: no se toca | filas 2026-27 de `data/modelos/v4_2/unidades/*_v42.csv.gz`, `artifact/kerno/quintetos/datos_v42/2026-27/`, su `indice.json` |
| `publicacion` | lote con sólo las rutas que dependen de 2026-27 (`.gz.txt` = gzip en base64), repartido entre los tres artifacts | `publicacion/lote0.json`, `lote_<sitio>_<n>.json`, `sitios.json` |

Opciones: `--sin-descarga` (reprocesa sin red), `--pasos …` (sólo algunos), `--forzar` (recalcula aunque no haya
partidos nuevos), `--ligas …` (descarga sólo esas ligas). El último informe queda versionado en
`data/modelos/actualizacion/ultima.json` (huella, tiempos por paso, estado de cada liga).

## Qué NO hace el botón (recalibración mensual)

Lo que exige reajustar modelos no cabe en una pulsación rápida y va en la tarea programada mensual
(`python -m bbactualiza.recalibrar`, ver `docs/actualizacion_2026-27.md`): reentrenar las 20 redes CVAE de la
normalización v3.2 (los jugadores nuevos de 2026-27 tienen entretanto sólo la v2), el RAPM y los perfiles del modelo
de equipo v4.0 (`atlas/v40/`, `v40/`) y los pesos del simulador.

## Reglas

* Sólo la temporada en curso; nunca `main`; nunca se publica si un paso falla.
* Cada artifact recibe sólo sus lotes y se republica con **su** página leída en ese momento, sin cambios.
* No se toca el código de las capas (`bbmodel/`, `bbnorm3/`, `bbfit/`…): `bbactualiza` sólo las llama.
* Si una liga falla en la descarga, se sigue con las demás (queda `ok_bruto_anterior` en el informe).
