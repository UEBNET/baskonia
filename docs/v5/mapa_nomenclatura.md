# Mapa de nomenclatura Cerno → Kerno (F0.8 del encargo v5.0)

Fecha: 09-11-2026 · commit base `7181094` (rama `claude/encargo-v41-ecosistema`).
Alcance: **inventario sin renombrar nada** (principio 1 del encargo). La migración se propone como tarea aparte
(pregunta 5 de la F0).

Método [DATO]: `git grep -I -i cerno` fuera de `data/` (117 ficheros) y búsqueda de `NC1/NC2/nc_*`. Recuento de
apariciones como palabra completa: `Cerno` 152, `CERNO` 109, `cerno` 129. En `data/` sólo aparece en tres ficheros
JSON/CSV de metadatos (`v4_0/equipo/anclas/F5_anclas.json`, `v4_1/benchmark/benchmark.json`,
`v4_1/inventario/club_temporada.csv`).

Ficheros afectados por carpeta: `artifact/` 26 · `docs/` 33 · `bbequipo/` 16 · `configs/` 9 · `bbfit/` 7 ·
`cerno_articulo/` 7 · `scripts/` 7 · `tests/` 4 · `bbactualiza/`, `bbestilo/`, `bbnorm3/`, `.claude/`, `CHANGELOG.md`,
`CONTEXTO_AGENTE.md`, `README.md`, `requirements-dev.txt` 1 cada uno.

## 1. Identificadores de código (riesgo de rotura si se renombran)

| Identificador actual | Tipo | Apariciones | Dónde (muestra) | Equivalente Kerno propuesto | Riesgo de la migración |
|---|---|---|---|---|---|
| `CERNO_SIMULADOR` | variable de entorno | 77 | `bbfit/config.py`, `artifact/atlas/index.html`, `artifact/atlas/simulador.js`, `artifact/kerno/atlas/index.html`, `CHANGELOG.md` | `KERNO_SIMULADOR` (aceptar ambas durante la transición) | Alto: la leen los scripts de actualización y las Routines |
| `CERNO_SIM_VARIANTE` | variable de entorno | 7 | `bbfit/__main__.py`, `bbfit/config.py`, `bbfit/v32.py`, `scripts/actualizar_v32.sh` | `KERNO_SIM_VARIANTE` | Alto (igual) |
| `CernoV40` | objeto JS global | 56 | `artifact/atlas/v40.js`, `informe_v3.js`, `informe_equipo.js`, `atlas/index.html` | `KernoV40` | Medio: global del navegador, publicado en artifacts |
| `CernoInformeV3`, `CernoInformeEquipo` | objetos JS | 4 / 6 | `artifact/atlas/informe_*.js`, `artifact/kerno/atlas/*` | `KernoInformeV3`, `KernoInformeEquipo` | Medio |
| `cernoSample`, `cernoSampleRes` | funciones JS | 9 / 7 | `artifact/atlas/informe_*.js` | `kernoSample`, `kernoSampleRes` | Bajo |
| `nivel_cerno` | clave de configuración / columna | 11 | `bbequipo/anclas.py`, `bbequipo/ecosistema/escenarios.py`, `configs/equipo_v40.yaml` | `nivel_kerno` | Alto: clave de YAML y de salidas |
| `nivel_cerno_examen`, `nivel_cerno_por_escenario`, `A_nivel_cerno` | claves / funciones | 4 / 1 / 2 | `bbequipo/anclas.py`, `bbequipo/__main__.py`, `configs/ecosistema_v41.yaml`, `bbequipo/ecosistema/benchmark.py` | `nivel_kerno_examen`, `nivel_kerno_por_escenario`, `A_nivel_kerno` | Medio |
| `NC1`, `NC2`, `nc1`, `nc2` | columnas / variables | 17 / 6 / 7 / 4 | `bbequipo/anclas.py`, `bbequipo/ecosistema/escenarios.py`, `artifact/kerno/atlas/v41/ecosistema.js`, `docs/data_dictionary.md` | `NK1`, `NK2` (en textos NK₁, NK₂) | Alto: columnas que lee el artifact |
| `nc_examen`, `nc_escenario`, `nc_ref`, `nc_separacion`, `nc_calibrado_con`, `nc_calibracion_deciles_tolerancia`, `nc_e`, `nc_a` | claves / columnas | 11 / 7 / 4 / 3 / 3 / 6 / 4 / 2 | `bbequipo/anclas.py`, `bbequipo/exportar_atlas.py`, `configs/equipo_v40.yaml`, `artifact/kerno/atlas/v41/producto.json` | prefijo `nk_` | Medio-alto |
| `cerno_articulo/` | paquete Python | 10 | `cerno_articulo/*.py`, `README.md`, `CHANGELOG.md` | `kerno_articulo/` | Medio (CLI `python -m cerno_articulo`) |
| `cerno_20ligas`, `cerno_v31` | rutas temporales en scripts | 3 / 2 | `scripts/actualizar_20ligas.sh`, `scripts/importar_20ligas.sh`, `scripts/actualizar_v31.sh` | `kerno_20ligas`, `kerno_v31` | Bajo |
| `bCerno`, `CERNO_Benchmark` | lint de marca / etiqueta | 1 / 2 | `artifact/herramientas/lint_marca_v41.py`, `bbequipo/ecosistema/benchmark.py` | — (el lint ya busca «Cerno» para prohibirlo) / `KERNO_Benchmark` | Bajo |

## 2. Ficheros cuyo nombre contiene «cerno»

| Ruta | Equivalente propuesto |
|---|---|
| `cerno_articulo/` (6 módulos, fuentes y logos `recursos/logo_*.svg`) | `kerno_articulo/` (los logos deben sustituirse por los de Kerno v2.0) |
| `docs/articulo/cerno_lectura_entre_ligas_v3_2.pdf` | Se conserva (documento histórico v3.2); el artículo v5 será `kerno_lectura_entre_ligas_v5.pdf` |

## 3. Textos visibles (producto)

| Texto | Dónde | Equivalente | Nota |
|---|---|---|---|
| «NIVEL CERNO», «Nivel Cerno» | `artifact/atlas/*`, `artifact/v40/index.html`, `artifact/mesa-multiliga.html`, `docs/*` | «Nivel Kerno» (NK₁, NK₂) | En `artifact/kerno/v40/index.html:256` ya se sustituye en tiempo de ejecución (`replace(/NIVEL CERNO/g, "Nivel Kerno")`) |
| «Cerno Analytics», «CERNO Analytics» | `artifact/mesa-multiliga.html`, `artifact/atlas/index.html`, `artifact/quintetos/index.html`, `CHANGELOG.md` | «Kerno Analytics» / «KERNO» sólo en etiquetas Geist Mono | Las páginas antiguas (no `artifact/kerno/`) siguen con la marca anterior |
| «Cerno» en documentación | 33 ficheros de `docs/` (checkpoints, encargos, modelo_equipo_v40, data_dictionary, glosario, ux) | «Kerno» en lo nuevo | Los documentos históricos se dejan como están (registro) |

## 4. Regla aplicada en la v5

Todo lo nuevo de la v5 (`src/normalizacion_v5/`, `configs/v5/`, `data/v5/`, `docs/v5/`) usa **Kerno** y **NK₁/NK₂**.
Cuando la v5 necesite leer un identificador antiguo (p. ej. `nivel_cerno` en F10), lo hará a través de una tabla de
equivalencias en código (`salida/nomenclatura.py`, por crear en F9), sin renombrar el original.

## 5. Propuesta de migración (tarea aparte, pendiente de decisión)

1. Variables de entorno y claves de YAML: aceptar ambos nombres durante una versión (lectura con alias) y avisar del
   nombre antiguo.
2. Columnas `NC1/NC2/nc_*`: escribir las dos columnas (antigua y nueva) durante una versión; el artifact pasa a leer
   la nueva; después se retira la antigua.
3. Objetos JS globales: alias `window.KernoV40 = window.CernoV40` y migración del código que los usa.
4. Paquete `cerno_articulo` → `kerno_articulo` con un módulo de compatibilidad.
5. Documentación histórica: no se toca.
