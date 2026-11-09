---
name: actualizar-temporada
description: Backend del botón «Actualizar 2026-27» del artifact Cerno Analytics (https://claude.ai/artifact/F4AxayFrM2d1D5JEoNiDoN). Descarga sólo los partidos nuevos de la temporada en curso en las 20 ligas, aplica a esa temporada los modelos ya ajustados (normalización v3.2, contexto, roles, estilos, simulador v3.3) sin reajustar ni tocar el histórico, sube los datos a Git y republica en el artifact sólo los ficheros que cambian. Úsala cuando la lance la Routine «Actualizar 2026-27 · Cerno» o cuando pidan «actualizar los datos de la temporada», «pulsar el botón de actualización» o «poner al día 2026-27».
---

# Actualizar la temporada en curso (botón del artifact)

El botón del artifact lanza la Routine **«Actualizar 2026-27 · Cerno»**, y la Routine abre una sesión de Claude Code que
sigue esta skill. Todo el cálculo lo hace un único programa, `python -m bbactualiza` (paquete `bbactualiza/`), así
que la sesión sólo prepara el entorno, lanza el programa, sube los datos y publica.

**Regla de oro: sólo cambia la temporada en curso (2026-27).** El histórico 2020-21 … 2025-26 es estático: los
ficheros que guardan todas las temporadas se reescriben sustituyendo sólo las filas de 2026-27 (`bbactualiza.capas.empalmar`),
y el resto de líneas queda byte a byte igual.

## Pasos de la sesión (Routine)

1. **Repositorio**: `add_repo` (owner `uebnet`, repo `baskonia`, access `push`) y clon ligero de la rama de trabajo
   (sin el historial y sin los brutos de temporadas pasadas, que no se usan):
   ```bash
   git clone --depth 1 --filter=blob:none --sparse --branch claude/gallant-pascal-49bx9o https://github.com/uebnet/baskonia
   cd baskonia && git sparse-checkout set --no-cone '/*' '!/data/raw/*/' '/data/raw/*/2026-27/'
   ```
2. **Dependencias** (≈ 1 min si el entorno no las trae ya):
   `pip install -r requirements.txt -r requirements-v3.txt -r requirements-estilos.txt --extra-index-url https://download.pytorch.org/whl/cpu`
3. **Actualización** (en segundo plano; espera a que termine):
   `PYTHONPATH=. python -m bbactualiza --json > actualizacion.json 2> actualizacion.log`
   * Código 0: `estado` = `ok` (hay ficheros que publicar) o `sin_cambios` (no hay partidos nuevos: no se
     recalcula ni se publica nada; termina aquí tras subir los brutos nuevos, si los hay).
   * Código 1: un paso falló. **No publiques**; resume el error (`pasos.<paso>.error`) y termina.
   * Código 2: ya había otra actualización en curso.
4. **Git**: `git add -A data/ config/sources.json artifact/quintetos/*.gz.txt` (nunca `publicacion/`), commit
   «Actualización 2026-27 (<fecha>)», `git pull --rebase` y `git push origin claude/gallant-pascal-49bx9o`
   (reintentos con espera si es la red; si da 403, vuelve a llamar a `add_repo` con `push`).
5. **Artifact** (sólo si `estado` = `ok`): con la herramienta Artifact,
   * `action: "read"` de la URL (guarda la página publicada; léela entera, es obligatorio antes de publicar);
   * `action: "list"`, `scope: "files"` de la URL (rutas que se van a sustituir);
   * `action: "publish"` con `url` = la del artifact, `file_path` = la página guardada **sin cambios** y `files` =
     el contenido de `publicacion/lote0.json` (ruta publicada → fichero local). No pases `capabilities` (se conservan).
6. **Resumen** para el usuario: estado por liga (partidos nuevos), segundos por paso, ficheros publicados, commit.

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
| `publicacion` | lote único con sólo las rutas que dependen de 2026-27 (`.gz.txt` = gzip en base64) | `publicacion/lote0.json` |

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
* No se toca el código de las capas (`bbmodel/`, `bbnorm3/`, `bbfit/`…): `bbactualiza` sólo las llama.
* Si una liga falla en la descarga, se sigue con las demás (queda `ok_bruto_anterior` en el informe).
