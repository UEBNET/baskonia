---
name: anadir-liga
description: Incorpora una liga nueva a todo el sistema Kerno (extracción, histórico 2020-21 en adelante, normalización v3.2, simulador v3.3, modelo de equipo v4.0, Atlas, Equipos y quintetos) y la publica en el artifact Kerno Analytics (https://claude.ai/artifact/A7rufkL84rvRFcUBFBxFbC), de modo que a partir de entonces el botón «Actualizar 2026-27» y la recalibración mensual la traten como una más. Úsala cuando pidan «añadir la liga X», «incorporar una competición», «ampliar a N ligas» o «meter la liga X en Kerno».
---

# Añadir una liga

El botón «Actualizar 2026-27» (skill `actualizar-temporada`) **no reajusta modelos**: aplica los ya ajustados a la
temporada en curso. Ninguno de esos modelos conoce una liga nueva (su nivel frente a la EuroLeague, su enlace en la
normalización, su lugar en las redes CVAE, en el simulador, en los estilos o en la v4.0). Por eso añadir una liga es
un trabajo **de una sola vez y en dos mitades**:

1. **Datos**: fuente, histórico 2020-21 → temporada en curso, listas de ligas del código.
2. **Reajuste global**: toda la cadena de modelos con la liga dentro (la misma que la ampliación a 20 ligas del
   31-10-2026 y la reconstrucción de identidades del 03-11-2026), congelados nuevos para el botón y publicación completa.

Después no hay que tocar el botón: `actualizar_delta.py` descarga todas las ligas `activa: true` de
`config/sources.json`, y la recalibración mensual reentrena con todas las ligas que haya en los datos.

Precedente que hay que leer antes de empezar: `docs/fuentes_ligas_nuevas.md` (CBA, BNXT, NCAA, NBL y VTB: fuentes,
alcance, identidad, cambios de modelo y resultados) y `docs/actualizacion_2026-27.md` (cómo trabaja el botón).

## Reglas

* **Rama**: todo en la rama de desarrollo de la sesión (la del botón es `claude/gallant-pascal-49bx9o`). Nunca `main`.
* **Decisiones antes de mirar resultados.** El escalón de contracción, el grupo de la v4.0, qué es regular y qué
  playoffs, y el alcance (temporadas, equipos) se fijan **antes** de ajustar y se anotan en
  `decisiones/<codigo>.md` (plantilla en `decisiones/plantilla.md`). No se cambian tras ver el nivel resultante.
* **Fuentes**: jugada a jugada siempre que exista (boxscore sólo como último recurso). No se extraen claves ni
  secretos del código de una web, ni se usan APIs que exijan autorización sin el permiso del usuario (precedente:
  `bnxt.sportpress.info`, `data-server.cbaleague.com`, API interna de ncaa.com).
* **El histórico de las demás ligas cambia** (los modelos se reajustan con una liga más). Es la única excepción a
  «el histórico es estático» y hay que decírselo al usuario con las diferencias medidas (Fase 6).
* **Procesos largos desacoplados**: una tarea de Bash en segundo plano se corta a los 30 min (2 h como máximo).
  La cadena (horas) se lanza con `setsid nohup … &` y se espera con Monitor; es reanudable por pasos.

## Fase 0 · Decisiones con el usuario

Pregunta (AskUserQuestion) lo que no esté claro y anótalo en `decisiones/<codigo>.md`:

| Decisión | Ejemplos del precedente | Dónde acaba |
|---|---|---|
| Código (minúsculas, sin espacios) y nombre | `bnxt` · «BNXT League» | `config/sources.json`, nombres en el código y las páginas |
| Temporadas | BNXT desde 2021-22 (no existía antes) | `config/sources.json` |
| Fases: qué es regular y qué playoffs; qué queda fuera (copas, supercopas, amistosos) | VTB: play-in con playoffs; Copa fuera | adaptador |
| Alcance si la liga es enorme | NCAA: 50 mejores universidades por temporada (T-Rank de Torvik) | `config/sources.json` |
| Minutos por partido (y si cambian por temporada) | CBA 48' hasta 2024-25, 40' desde 2025-26 | `config/sources.json` |
| Escalón de contracción de la normalización | `domestica_media: [bnxt, cba]`; NCAA escalón propio | `configs/normalization.yaml` y `configs/normalization_v32.yaml` |
| País de referencia para la adaptación | `bnxt: BE` | `configs/adaptacion.yaml` |
| Grupo de la v4.0 (calibración F4 e IMPACTO) | `bnxt: europa_menor` | `bbequipo/equipo.py`, `configs/equipo_v40.yaml` |
| Sistema de coordenadas de tiro | FIBA, metros o pies, campo completo | `bbmodel/zonas.py` |

## Fase 1 · Fuente y adaptador

1. ¿La liga publica en una plataforma que ya leemos? Entonces basta una entrada en `config/sources.json → ligas`:

   | Plataforma | `adaptador` | Ligas que ya lo usan |
   |---|---|---|
   | FIBA LiveStats (`/data/<id>/data.json`) | `fiba_livestats` | BSL, GBL, BNXT |
   | Web de FIBA (competiciones FIBA) | `fiba_web` | BCL, FIBA Europe Cup |
   | Feed de la EuroLeague | `euroleague` | EuroLeague, EuroCup |
   | FEB | `feb` | Primera, Segunda y Tercera FEB |
   | Basketball-Reference | `bref_nba` | NBA (G League con su propio adaptador) |

   Copia la entrada de una liga del mismo adaptador y cambia identificadores, temporadas, `minutos_partido` y
   `estado_verificacion` («pendiente» hasta la Fase 2).
2. Si no, escribe `bbstats/adapters/<codigo>.py` con el patrón de las cinco últimas ligas: **traducir cada partido al
   formato del data.json de FIBA LiveStats (`to_fls`)** y reutilizar `bbstats/adapters/fiba_livestats.py` y
   `bbstats/lineups/sources/fiba_livestats.py` (boxscore, fases, quintetos, tramos, RAPM, tiros y entrenadores salen del
   mismo código). Modelos: `adapters/vtb.py` (API JSON), `adapters/cba.py` (dos fuentes combinadas), `adapters/nbl.py`
   (complemento con FIBA LiveStats). Regístralo en `bbstats/adapters/__init__.py` y, si tiene jugada a jugada propio,
   en `bbstats/lineups/run.py`. Entrenadores: `bbstats/entrenadores.py`.
3. Identidad: ids de persona estables si la fuente los da; si no, nombre normalizado (como BSL/GBL/BNXT). Si los
   nombres vienen en otro alfabeto o abreviados, revisa las reglas del crosswalk (`bbmodel/crosswalk.py`; precedente:
   inicial + apellido + fecha de nacimiento para la CBA).
4. Prueba con **una temporada** antes del histórico:
   `PYTHONPATH=. python -m bbstats ejecutar --temporada 2025-26 --ligas <codigo>` y revisa
   `data/processed/2025-26/informe_ejecucion.json`, los partidos frente al calendario oficial, y la validación de
   quintetos (`quintetos/<codigo>/validacion.csv`: minutos y +/- del jugada a jugada frente al boxscore; ≥ 90 % es lo
   habitual). `python -m bbstats contrato` comprueba tipos, rangos, nulos, claves y minutos.

## Fase 2 · Histórico

```
PYTHONPATH=. setsid nohup python -m bbstats historico --desde 2020-21 --hasta 2026-27 --ligas <codigo> > /tmp/hist.log 2>&1 < /dev/null & disown
PYTHONPATH=. python -m bbstats entrenadores --temporada 2020-21 2021-22 2022-23 2023-24 2024-25 2025-26 2026-27 --ligas <codigo>
```

`historico` incluye quintetos y conexiones. Revisa cada `data/processed/<t>/informe_ejecucion.json` y deja la cobertura
(jugada a jugada sí/no por temporada, partidos frente a los oficiales) en `decisiones/<codigo>.md`. Marca
`estado_verificacion` en `config/sources.json`. **Commit** de `config/`, `bbstats/` y `data/raw|processed` de la liga.

## Fase 3 · Listas de ligas en el código

Hay listas explícitas de ligas en el código y en las páginas. Encuéntralas con una liga parecida como plantilla:

```
git grep -n -w bnxt -- ':!data' ':!experimentos' ':!docs' ':!tests'
```

Las conocidas (11-2026): nombres en `bbmodel/dataset_normalizado.py`; orden en `bbmodel/evaluacion_ligas.py` y
`bbmodel/mesa_normalizacion.py`; escalones en `configs/normalization*.yaml`; país en `configs/adaptacion.yaml`; minutos
por defecto en `configs/simulation_v33.yaml`; grupos de la v4.0 en `bbequipo/equipo.py` y `configs/equipo_v40.yaml`;
coordenadas de tiro en `bbmodel/zonas.py`; ids de equipo inestables en `bbestilo/datos.py` y
`bbfit/estilos_unificados.py` (si la fuente renumera equipos cada temporada). Las páginas del artifact (Fase 7) tienen
sus propias listas (`LIGA_ORD`/`LIGA_N` en Kerno, `LIGAS_INFO` en el Atlas y en Quintetos).

Ejecuta los tests: `PYTHONPATH=. python -m pytest -q tests` (≈ 1,5 min).

## Fase 4 · Reajuste global de los modelos

`cadena.sh` (en esta carpeta) encadena, en este orden y reanudable por pasos (marcas en `experimentos/.pasos_liga/`):

1. `bbmodel crosswalk` (personas de la liga nueva; los `persona_id` existentes se conservan).
2. `scripts/rehacer_identidades.sh` desde cero: capas v2 (A, B, amortiguada, dataset, contexto, interacciones),
   roles, reemplazo, entropía, estilos, adaptación, líneas base, **normalización v3.2** (20 redes CVAE, examen B2,
   ajuste final, vara de destino), **simulador v3.2 y v3.3** (exámenes, decisiones, histórico, exportación, auditoría),
   datos del artifact, Equipos y quintetos, compactación y lotes en `experimentos/v33_artifact/`. Aparta antes las
   cachés que dependen de los datos (redes incluidas: hay que reentrenarlas con la liga nueva).
3. **Modelo de equipo v4.0** (productos): contrato, perfiles, RAPM multiliga, sinergias, efectos dirigidos, función de
   conjunto, A5, equipo, anclas, exportación del Atlas v4.0 y `v40/equipos_<temporada>.json`.
4. **Congelados del botón**: `modelos_hasta_2024-25.pkl` y `modelos_hasta_2025-26.pkl` del simulador v3.3
   (`data/modelos/simulador/v3_3/congelado/`), que el botón reutiliza en vez de reajustarlos.

```
setsid nohup .claude/skills/anadir-liga/cadena.sh > experimentos/cadena_liga.log 2>&1 < /dev/null & disown
```

Espera con Monitor (`while pgrep -f "[c]adena.sh" >/dev/null; do sleep 120; done`, re-armado cada 30 min) y vigila
`experimentos/cadena_liga.log` (cada paso empieza con `===` y la hora). Si un paso falla, corrige y relanza el mismo
comando: los pasos hechos se saltan. La cadena **renombra** las cachés anteriores (`experimentos/v3_antes_id_<fecha>`,
`cache_*_antes_id_<fecha>`, varios GB): bórralas al terminar si falta disco. Son varias horas (redes CVAE ≈ 37 min con 4 procesos; exámenes del simulador y
de la v4.0, lo más largo).

Los exámenes prerregistrados de la v4.0 (`bbequipo rapm-examen`, `sinergia-examen`, `conjunto-examen`,
`equipo-examen`, `anclas-examen`) no van en la cadena: las decisiones vigentes se conservan. Ejecútalos si el
usuario quiere saber cómo rinde la v4.0 con la liga nueva (recomendable si la liga es grande o muy distinta).

## Fase 5 · El botón con la liga nueva

```
PYTHONPATH=. python -m pytest -q tests/test_bbactualiza.py
PYTHONPATH=. MLFLOW_DISABLE_AGENT_HINT=1 setsid nohup python -m bbactualiza --sin-descarga --forzar --json > /tmp/act.json 2> /tmp/act.log < /dev/null & disown
```

Tiene que acabar en `ok` y la liga tiene que aparecer en `data/artifact/2026-27/indice.json`. Si la temporada en curso
de la liga aún no ha empezado, márcala como la NCAA (`sin_datos: true` en esa temporada) hasta que empiece.

## Fase 6 · Verificación (antes de publicar)

* **Nivel de la liga** (algoritmo A): puentes, nivel PER frente a la EuroLeague y su error típico
  (`data/modelos/algoritmo_A/`; `python -m bbmodel auditoria-puentes`). Regla fijada de antemano: **nivel provisional**
  si tiene < 50 puentes o error típico del nivel PER > 0,25 σ (la Mesa lo marca sola).
* **Simulador**: auditorías con 0 fallos, paridad Python/navegador (`tests/js/paridad_simulador.js`, ya en la cadena),
  y examen por segmentos (con origen o destino en la liga nueva frente al resto), como en `docs/fuentes_ligas_nuevas.md` §7.
* **Cambio en las demás ligas**: compara niveles (`data/modelos/algoritmo_A/`) y el normalizado v3.2 de 2025-26
  antes/después (`git diff --stat data/modelos`, y medias por liga). Explícaselo al usuario.
* Escribe los resultados en `decisiones/<codigo>.md` y una sección nueva en `docs/fuentes_ligas_nuevas.md`.

## Fase 7 · Publicación en Kerno

Cambian todas las temporadas, así que se publica **completo** (no el parche del botón):

1. `python3 artifact/empaquetar.py experimentos/v33_artifact/_publicacion experimentos/v33_artifact` (la cadena ya
   lo hace) deja `lote0.json … loteN.json` (≤ 58 MB y ≤ 250 ficheros cada uno; la versión no puede pasar de 256 MB:
   si no cabe, `artifact/herramientas/compactar.py` y el documento §8 del precedente).
2. **Quita de los lotes las páginas** (`atlas/index.html`, `quintetos/index.html` y cualquier `.html`): las publicadas
   en Kerno son más nuevas que las del repositorio. Las páginas se tocan aparte (punto 4).
3. Con la herramienta Artifact: `read` de https://claude.ai/artifact/A7rufkL84rvRFcUBFBxFbC (lee la página entera),
   `list` con `scope: "files"`, y un `publish` por lote con `url` = la de Kerno, `file_path` = la página guardada sin
   cambios y `files` = el lote. Sin `capabilities` (se conservan las de la página, `mcp` del botón incluido).
   **El último lote es `publicacion/lote0.json` de la Fase 5** (el parche del botón): lleva `datos/actualizacion.json`
   y los ficheros de la v4.0 (`atlas/v40/jugadores_v40`, `referencias_v40`, `v40/equipos_<t>.json`,
   `v40/calibracion.json`), que `artifact/empaquetar.py` no incluye.
4. Páginas: para cada una (`index.html` = la app Kerno, `clasico.html`, `atlas/index.html`, `quintetos/index.html`,
   `v40/index.html`) lee la versión publicada (`read` con `path`), añade la liga a sus listas (`LIGA_ORD`/`LIGA_N`,
   `LIGAS_INFO`) y publícala; guarda la copia en el repositorio (`artifact/kerno.html` para `index.html`).
   Comprueba en Playwright (1440 y 390 px, claro y oscuro) que no hay errores de JavaScript.
5. Límite conocido: `atlas/v40/clubes_v40.json` y `atlas/v40/mapa_personas.json` no se generan en este repositorio
   (`docs/actualizacion_2026-27.md` §5): la liga nueva no estará en ellos y la página calcula su Net v4.0 en vivo.

## Fase 8 · Cierre

* `CHANGELOG.md` (entrada con la liga, decisiones, niveles y resultados del examen), `docs/fuentes_ligas_nuevas.md`,
  `docs/actualizacion_2026-27.md` (número de ligas), `decisiones/<codigo>.md`.
* Commit y push a la rama (los datos de modelos y del artifact versionados; nunca `publicacion/` ni cachés de
  `experimentos/`).
* Resumen al usuario: cobertura de la fuente, nivel y si es provisional, cuánto cambiaron las demás ligas, examen
  del simulador por segmentos, versión publicada y que el botón ya la incluye desde la siguiente pulsación.
