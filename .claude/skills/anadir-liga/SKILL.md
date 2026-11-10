---
name: anadir-liga
description: Incorpora una liga nueva a todo el sistema Kerno (extracción, histórico 2020-21 en adelante, normalización v3.2, simulador v3.3, modelo de equipo v4.0, capas v4.1 y v4.2, Atlas, Equipos y quintetos) y la publica en los tres artifacts de Kerno Analytics (Jugadores https://claude.ai/artifact/A7rufkL84rvRFcUBFBxFbC, Equipos https://claude.ai/artifact/SXFgQ6CpytxT3ZZupcEFcj y Metodología https://claude.ai/artifact/T83MBGZk5untACmegadfNn), de modo que a partir de entonces el botón «Actualizar 2026-27» y la recalibración mensual la traten como una más. Úsala cuando pidan «añadir la liga X», «incorporar una competición», «ampliar a N ligas» o «meter la liga X en Kerno».
---

# Añadir una liga

El botón «Actualizar 2026-27» (skill `actualizar-temporada`) **no reajusta modelos**: aplica los ya ajustados a la
temporada en curso. Ninguno de esos modelos conoce una liga nueva (su nivel frente a la EuroLeague, su enlace en la
normalización, su lugar en las redes CVAE, en el simulador, en los estilos o en la v4.0). Por eso añadir una liga es
un trabajo **de una sola vez y en dos mitades**:

1. **Datos**: fuente, histórico 2020-21 → temporada en curso, listas de ligas del código.
2. **Reajuste global**: toda la cadena de modelos con la liga dentro (la misma que la ampliación a 20 ligas del
   31-10-2026 y la reconstrucción de identidades del 03-11-2026, más las capas v4.1 y v4.2), congelados nuevos para el
   botón y publicación completa de los tres artifacts.

**Tres artifacts (v4.2, 09-11-2026).** Kerno Analytics está dividido por secciones (docs/checkpoints/V42_sitios.md):

| Sitio | URL | Qué publica |
|---|---|---|
| Jugadores | https://claude.ai/artifact/A7rufkL84rvRFcUBFBxFbC (lleva el botón) | Tu equipo hoy, Mercado, Evaluación, Decisión, Modelo de equipo |
| Equipos | https://claude.ai/artifact/SXFgQ6CpytxT3ZZupcEFcj | Tu equipo hoy y 01 Diagnóstico (quintetos, parejas y tríos, Impacto en pista, Informe de equipo…) |
| Metodología | https://claude.ai/artifact/T83MBGZk5untACmegadfNn | Método (evaluación y normalización de ligas, claves del estilo, guía) |

Los tres salen de la misma fuente, `artifact/kerno/` (página `index.html`, `clasico.html`, `atlas/`, `quintetos/`,
`v40/`), y cada uno publica sólo las rutas de su manifiesto `artifact/kerno/sitios/<sitio>.json`. La página de cada
sitio es `artifact/kerno/index.html` con su `<title>`; el interruptor `sitio.json` (de `sitios/sitio_<sitio>.json`) no
cambia al añadir una liga. `artifact/kerno.html`, `artifact/atlas/` y `artifact/quintetos/` son copias anteriores: no
se publican.

Después no hay que tocar el botón: `actualizar_delta.py` descarga todas las ligas `activa: true` de
`config/sources.json`, y la recalibración mensual reentrena con todas las ligas que haya en los datos.

Precedente que hay que leer antes de empezar: `docs/fuentes_ligas_nuevas.md` (CBA, BNXT, NCAA, NBL y VTB: fuentes,
alcance, identidad, cambios de modelo y resultados; §9 Liga U, la última, añadida el 09-11-2026 con la plataforma FEB),
`decisiones/ligau.md` (ejemplo completo de las decisiones de la Fase 0 y de la cobertura) y
`docs/actualizacion_2026-27.md` (cómo trabaja el botón).

**Ligas en el sistema (09-11-2026): 21.** euroleague, eurocup, acb, nba, gleague, lba, bbl, lnb, bcl, fec, bsl, gbl,
feb1, feb2, feb3, nbl, bnxt, ncaa, vtb, cba y **ligau** (Liga U de la ACB, sub-22, temporadas 2025-26 y 2026-27; la
2026-27 se actualiza con el botón como las demás).

## Reglas

* **Rama**: todo en la rama de desarrollo de la sesión; lo que tiene que llegar al botón, en la suya,
  `claude/jolly-thompson-qczxl4` (la que clonan la Routine y la recalibración mensual). Nunca `main`.
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
   | FEB (`baloncestoenvivo.feb.es` + `intrafeb.feb.es`; competición `g` del menú de la web) | `feb` | Primera (`g=1`), Segunda (`g=2`) y Tercera FEB (`g=3`), Liga U de la ACB (`g=74`, `slug: ligau`) |
   | Basketball-Reference | `bref_nba` | NBA (G League con su propio adaptador) |

   Copia la entrada de una liga del mismo adaptador y cambia identificadores, temporadas, `minutos_partido` y
   `estado_verificacion` («pendiente» hasta la Fase 2).

   Antes de escribir un adaptador, mira si la web oficial de la liga enlaza ids de partido de una plataforma conocida:
   la Liga U (ligau.com, web propia sobre Supabase) enlaza ids de partido FEB (2.5 millones, los mismos que
   `baloncestoenvivo.feb.es/partido/<id>`), y el menú de esa página da su `g` y su `slug`. Así se evitó leer el backend
   de ligau.com, que exige una clave del código de su web. Si la liga usa la plataforma FEB, añádela además a las listas
   del sistema FEB: `FEB` en `bbstats/feb_informe.py` y `bbmodel/crosswalk.py` (el id de persona FEB es común a todas
   sus competiciones: mismo id = misma persona), `bbmodel/nombres.py`, `scripts/feb_nombres_web.py`, `bbfit/adaptacion.py`
   (nacionalidad de la plantilla) y `actualizar_delta.py` (informes FEB del botón).

   **Red del entorno**: el entorno de la sesión tiene una lista de hosts permitidos. Si la descarga falla con
   `CONNECT tunnel failed, response 403`, propón añadir los hosts de la fuente con `update_environment` (FEB:
   `baloncestoenvivo.feb.es` e `intrafeb.feb.es`). El proxy sólo cursa HTTPS: una redirección a `http://` falla
   (`Equipo.aspx?i=` de la FEB redirigía a `http://…/equipo/<id>`; el adaptador pide ya `/equipo/<id>` por HTTPS).
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

Las conocidas (11-2026; con `ligau` como plantilla si la liga nueva es de la FEB: `git grep -n -w ligau`): nombres en
`bbmodel/dataset_normalizado.py`, `bbmodel/mesa_quintetos.py`, `bbestilo/figuras.py`, `bbestilo/articulo.py` y
`cerno_articulo/datos.py`; identidad en `bbmodel/crosswalk.py` e `bbmodel/identidad.py` (`NACIONALES`: concurrencia con
las copas europeas); pares de validación en `bbmodel/amortiguacion.py`; `LIGAS_POCOS_PUENTES` en
`bbmodel/auditoria_puentes.py`; `club_clave` en `configs/reemplazo.yaml`; partidos por temporada en
`configs/simulation_v3*.yaml`, `simulation_v40.yaml` y `simulation_v42.yaml` (`partidos_temporada`); orden en `bbmodel/evaluacion_ligas.py` y
`bbmodel/mesa_normalizacion.py`; escalones en `configs/normalization*.yaml`; país en `configs/adaptacion.yaml`; minutos
por defecto en `configs/simulation_v33.yaml`; grupos de la v4.0 en `bbequipo/equipo.py` y `configs/equipo_v40.yaml`;
coordenadas de tiro en `bbmodel/zonas.py`; ids de equipo inestables en `bbestilo/datos.py` y
`bbfit/estilos_unificados.py` (si la fuente renumera equipos cada temporada). Las páginas del artifact (Fase 7) tienen
sus propias listas (`LIGA_ORD`/`LIGA_N` en `artifact/kerno/index.html` y `v40/index.html`; `LEAGUES`, `VARA_NOMBRES` y
`LEAGUE_ABBR` en `clasico.html`; `LIGAS_INFO` en
`artifact/kerno/atlas/index.html` y `artifact/kerno/quintetos/index.html`; búscalas con
`git grep -n -w bnxt -- artifact/kerno`).

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
5. **Capas v4.1 y v4.2**: producto v4.1 (`bbequipo.ecosistema producto`: Landing v3.1, sellos, i18n →
   `artifact/kerno/atlas/v41/producto.json`), historial del jugador v4.2 (`bbequipo.v42 historial-exportar` →
   `artifact/kerno/atlas/v42/historial/`) y tríos, parejas y sinergia v4.2 de todas las temporadas
   (`bbequipo.v42.unidades exportar` + `bbequipo.v42.unidades_artifact` → `data/modelos/v4_2/unidades/`,
   `artifact/kerno/quintetos/datos_v42/`). Se conservan las decisiones prerregistradas (qué métricas pasaron D1 y qué
   tipos D3; `configs/v42.yaml`) y los parámetros se reajustan con las temporadas cerradas. Las estimaciones D3
   anteriores se apartan a `experimentos/v42_unidades_antes_liga/` (`exportar` no sobrescribe). Los exámenes v4.2
   (`historial-examen`, `unidades examen`) no van en la cadena: ejecútalos si el usuario quiere saber si las decisiones
   siguen en pie con la liga nueva.

```
setsid nohup .claude/skills/anadir-liga/cadena.sh > experimentos/cadena_liga.log 2>&1 < /dev/null & disown
```

Espera con Monitor (`while pgrep -f "[c]adena.sh" >/dev/null; do sleep 120; done`, re-armado cada 30 min) y vigila
`experimentos/cadena_liga.log` (cada paso empieza con `===` y la hora). Si un paso falla, corrige y relanza el mismo
comando: los pasos hechos se saltan. La cadena **renombra** las cachés anteriores (`experimentos/v3_antes_id_<fecha>`,
`cache_*_antes_id_<fecha>`, varios GB): bórralas al terminar si falta disco. Son varias horas (redes CVAE ≈ 37 min con 4 procesos; exámenes del simulador y
de la v4.0, lo más largo).

**Incidencias conocidas (Liga U, 10-11-2026):**
* `bbfit estilos --reusar-k` no reutiliza la tabla de K si cambia la población (una liga más): la regla puede elegir
  otro K y entonces la adaptación falla (`KeyError: p_pistons`). `configs/styles.yaml → mezcla.k_fijo: 6` conserva la
  taxonomía vigente; si se quiere revisar el número de estilos, es una decisión aparte con el usuario.
* `bbequipo rapm-producto` llega a ≈ 14 GB de memoria con 21 ligas: en una máquina de 15 GB, añade antes un fichero de
  intercambio (`fallocate -l 12G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile`).
* Si el contenedor se reinicia, relanza `cadena.sh`: retoma en el paso que quedó a medias.
* Antes de publicar, otra sesión puede haber publicado cambios (p. ej. la lectura de fichaje): compara las páginas
  y los `.js` publicados con `artifact/kerno/` justo antes de la Fase 7 y fusiona la rama del botón.

Los exámenes prerregistrados de la v4.0 (`bbequipo rapm-examen`, `sinergia-examen`, `conjunto-examen`,
`equipo-examen`, `anclas-examen`) no van en la cadena: las decisiones vigentes se conservan. Ejecútalos si el
usuario quiere saber cómo rinde la v4.0 con la liga nueva (recomendable si la liga es grande o muy distinta).

## Fase 5 · El botón con la liga nueva

```
PYTHONPATH=. python -m pytest -q tests/test_bbactualiza.py
PYTHONPATH=. MLFLOW_DISABLE_AGENT_HINT=1 setsid nohup python -m bbactualiza --sin-descarga --forzar --json > /tmp/act.json 2> /tmp/act.log < /dev/null & disown
```

Tiene que acabar en `ok` y la liga tiene que aparecer en `data/artifact/2026-27/indice.json`. El botón deja además
`publicacion/sitios.json` y `publicacion/lote_<sitio>_<n>.json` (el parche de 2026-27 repartido entre los tres
artifacts); en la Fase 7 no se publican sueltos: `publicacion/lote0.json` entra como `--parche` de la publicación
completa. Si la temporada en curso
de la liga aún no ha empezado, márcala como la NCAA (`sin_datos: true` en esa temporada) hasta que empiece.

## Fase 6 · Verificación (antes de publicar)

* **Nivel de la liga** (algoritmo A): puentes, nivel PER frente a la EuroLeague y su error típico
  (`data/modelos/algoritmo_A/`; `python -m bbmodel auditoria-puentes`). Regla fijada de antemano: **nivel provisional**
  si tiene < 50 puentes o error típico del nivel PER > 0,25 σ (la Mesa lo marca sola).
* **Simulador**: auditorías con 0 fallos, paridad Python/navegador (`tests/js/paridad_simulador.js`, ya en la cadena),
  y examen por segmentos (con origen o destino en la liga nueva frente al resto), como en `docs/fuentes_ligas_nuevas.md` §7.
* **Cambio en las demás ligas**: compara niveles (`data/modelos/algoritmo_A/`) y el normalizado v3.2 de 2025-26
  antes/después (`git diff --stat data/modelos`, y medias por liga). Explícaselo al usuario.
* **Capas v4.2**: parámetros D1 (`data/modelos/v4_2/historial/`, τ² y c por métrica) y D3
  (`data/modelos/v4_2/unidades/parametros_v42.json`) antes/después, y Net v4.2 de tríos y parejas de 2025-26 de las
  demás ligas frente a `experimentos/v42_unidades_antes_liga/` (diferencia media y máxima).
* Escribe los resultados en `decisiones/<codigo>.md` y una sección nueva en `docs/fuentes_ligas_nuevas.md`.

## Fase 7 · Publicación en los tres artifacts

Cambian todas las temporadas, así que se publica **completo** (no el parche del botón), sitio por sitio.

1. **Páginas primero, en el repositorio.** Para cada página y código compartido (`index.html`, `clasico.html`,
   `atlas/index.html`, `atlas/*.js`, `quintetos/index.html`, `v40/index.html`): `read` con `path` de la versión
   publicada en Jugadores (Equipos y Metodología si sólo la publican ellos: `quintetos/index.html`) y compárala con
   `artifact/kerno/<ruta>` (en `index.html`, todo salvo el `<title>`). Si la publicada tiene cambios que el repositorio
   no tiene, llévalos antes al repositorio. Después añade la liga a sus listas (`LIGA_ORD`/`LIGA_N`, `LIGAS_INFO`) **en
   `artifact/kerno/`** y comprueba en Playwright (1440 y 390 px, claro y oscuro) que no hay errores de JavaScript.
2. **Datos**: `python3 artifact/empaquetar.py experimentos/v33_artifact/_publicacion experimentos/v33_artifact` (la
   cadena ya lo hace) deja `lote0.json … loteN.json` con los datos de todas las temporadas.
3. **Reparto entre los tres sitios**:
   ```
   PYTHONPATH=. python -m bbactualiza.sitios --publicacion publicacion_completa \
       --completo experimentos/v33_artifact/_publicacion/lote*.json --parche publicacion/lote0.json
   ```
   Toma los datos de esos lotes (sin borrados ni páginas ni `.js`: los de `artifact/atlas` y `artifact/quintetos` son
   anteriores), las páginas, el código y los datos v4.1/v4.2 de `artifact/kerno/` (comprime los `.json` que se publican
   como `.gz.txt`), y el parche del botón al final (lleva `datos/actualizacion.json` y los ficheros de la v4.0 que
   `empaquetar.py` no incluye). Escribe `publicacion_completa/sitios.json`, `lote_<sitio>_<n>.json` (≤ 58 MB y ≤ 250
   ficheros cada uno) y la página de cada sitio en `publicacion_completa/paginas/<sitio>/index.html`. Las rutas de la
   liga nueva van a los sitios que publican sus hermanas (alineaciones y v4.2 en Equipos y Metodología, `.extras` sólo
   en Equipos…) y quedan anotadas en los manifiestos. Revisa `sin_sitio` (no se publica: decide con el usuario a qué
   sitio va) y que Jugadores no reciba nada de `quintetos/`.
4. **Cabe**: cada versión admite 256 MiB y 511 ficheros. Con el `list` de cada sitio (paso 5) suma los tamaños de lo
   que no se sustituye y los de sus lotes; si un sitio no cabe, compacta (`artifact/herramientas/compactar.py`) o
   pregunta al usuario qué sale de ese sitio (precedente: docs/checkpoints/V42_sitios.md §3). Nunca muevas datos de un
   sitio a otro sin decírselo.
5. Con la herramienta Artifact, **para cada sitio** (Jugadores, Equipos, Metodología): `read` de su URL (lee la
   página entera), `list` con `scope: "files"`, y un `publish` por cada lote suyo con `url` = la de ese sitio,
   `file_path` = `publicacion_completa/paginas/<sitio>/index.html` y `files` = el lote. Sin `capabilities` (Jugadores
   conserva `mcp` del botón; Equipos y Metodología, `downloads` y `sample`). Nunca publiques el lote de un sitio en la
   URL de otro.
6. Límite conocido: `atlas/v40/clubes_v40.json` y `atlas/v40/mapa_personas.json` no se generan en este repositorio
   (`docs/actualizacion_2026-27.md` §5): la liga nueva no estará en ellos y la página calcula su Net v4.0 en vivo.

## Fase 8 · Cierre

* `CHANGELOG.md` (entrada con la liga, decisiones, niveles y resultados del examen), `docs/fuentes_ligas_nuevas.md`,
  `docs/actualizacion_2026-27.md` (número de ligas), `decisiones/<codigo>.md`.
* `docs/checkpoints/V42_sitios.md` (ficheros y MB por sitio tras la liga) y los manifiestos `artifact/kerno/sitios/`.
* Commit y push a la rama (los datos de modelos, `artifact/kerno/` y los manifiestos versionados; nunca
  `publicacion/`, `publicacion_completa/` ni cachés de `experimentos/`).
* Resumen al usuario: cobertura de la fuente, nivel y si es provisional, cuánto cambiaron las demás ligas, examen
  del simulador por segmentos, cambios en las capas v4.2, versión publicada de cada uno de los tres artifacts y que
  el botón ya la incluye desde la siguiente pulsación.
