# Artifact de análisis · v2 candidata: usabilidad, roles, nomenclatura de estilos y lectura de fichaje (29-10-2026)

Base: versión publicada 1793270587-2224 (F1 rebranding) de https://claude.ai/artifact/F4AxayFrM2d1D5JEoNiDoN.
**Estado (29-10-2026, 13:50): la v2 sustituye a la versión vigente** por decisión del CEO, en el mismo enlace
https://claude.ai/artifact/F4AxayFrM2d1D5JEoNiDoN (versión 1793278157-f2b5, 210 ficheros, capacidades `downloads` y
`sample`; se retira el conector Claude Code Remote que usaba «Ejecutar»; runtime 0.2.92). Antes de publicar se
comprobó que la versión vigente seguía siendo exactamente la base de la v2 (sin cambios que fusionar). La copia
candidata https://claude.ai/artifact/Qk58XhN8Bp2mfLkXgSHDDy queda como duplicado de revisión.

Repositorio (rama `main`, UEBNET/baskonia): `artifact/mesa-multiliga.html`, `artifact/atlas/{index.html,
simulador_v2.js,informe_v3.js}`, `artifact/quintetos/{index.html,estilos_unificados*.gz.txt}`, `artifact/empaquetar.py`
(mapa con los ficheros nuevos), `artifact/herramientas/` (generadores de estilos y test de paridad del simulador),
`bbfit/simulador.py`, `bbfit/sim_exportar.py`, `configs/simulation.yaml`, `tests/test_simulation.py`,
`docs/ux/UX-SPEC.md`, `docs/checkpoints/ARTIFACT-v2.md`, `CHANGELOG.md`.

## Decisiones del CEO aplicadas
- **Fuera el botón «Ejecutar»** (actualización de datos desde la página, bloqueado e inútil en el visor). Única baja
  de funcionalidad aprobada. La actualización sigue existiendo en Claude Code; ya no se declara el conector MCP.
- **Interfaz limpia sin perder funciones**: capa de usabilidad (`<style id="cerno-ux">` y, donde hace falta,
  `<script id="cerno-ux-js">`) en las tres aplicaciones. Solo mueve/agrupa nodos y cambia presentación; ids, `data-*`,
  opciones, claves de almacenamiento y cálculos intactos. Especificación: `UX-SPEC.md` (en el repositorio,
  `docs/ux/UX-SPEC.md`).
- **Roles**: visibles en tablas (Datos brutos y normalizados, ficha, plantillas de los simuladores, trayectoria del
  informe). Rol del simulador cuando existe (2024-25 en adelante); si no, estimado por minutos con prefijo «≈».
- **Rol asignado en las simulaciones (simulador v2.1)**: donde antes había minutos, ahora se elige el rol (Residual,
  Profundidad, Rotación, Titular, Go-to-guy). El motor calcula con ese rol minutos, rendimiento, adaptación, sinergias,
  impacto, quintetos e **Índice Fit completo** (se mantienen todas sus salidas).
- **Sin nombres VaDE**: jugadores, clubes y plantillas simuladas usan solo Pistons, Isolation, Old-School, Spacing,
  Circulación y Pintura (y sus mezclas). Los modelos estimados sobre los grupos VaDE (química de estilos, regiones y
  colores del mapa 3D) se rotulan como **«Perfil de mapa A–F»**, neutros, con aviso de que no equivalen a los estilos
  (opción 1 propuesta; pendiente de confirmación del CEO).
- **Lectura de fichaje (informe PDF v3)** con la estructura pedida y caja «Por qué este jugador» reescrita en tono
  Cerno por Claude (capacidad `sample`, a través de la página principal).

## Qué cambió
### Simulador v2.1 (`atlas/simulador_v2.js`, `bbfit/simulador.py`)
- `simular({…, rol, roles})` / `simular(…, rol=, roles=)`: con rol asignado, minutos de la franja del rol en la liga de
  destino (centro `min_rol`, dispersión 0,04 del partido, recorte a los umbrales del rol), titular si TITULAR o
  GO_TO_GUY, el resto de la plantilla reparte lo que queda (tope por jugador), probabilidad de rol 1, sin calibración
  de salida para ese jugador. `minutosEquipo(recs, club, n, roles)` igual para «Simular equipo completo».
- Constantes en `configs/simulation.yaml → rol_asignado` (exportadas en `meta.rol_asignado`; el JS usa las mismas por
  defecto). Sin rol: resultados idénticos a v2.0 (comprobado: Fit y minutos iguales).
- Tests: `tests/test_simulation.py::test_rol_asignado_condiciona_la_salida`, `::test_sin_rol_es_v20` (15/15 en verde).
- Efecto esperado: el Fit sube con el rol (componente «rol» y nivel/minutos), los minutos siguen la franja elegida y
  la plantilla sigue sumando los minutos del equipo; con muchos roles altos asignados, el resto pierde minutos.
- Limitación declarada: GO_TO_GUY cambia minutos y titularidad, no el uso del balón (el uso sigue la curva del motor).

### Atlas (`atlas/index.html`, `atlas/informe_v3.js`)
- Selector «Rol en el club» por fichaje y por jugador del equipo completo; chips de rol en plantillas.
- Estilos: grupos del mapa renombrados a «Perfil de mapa A–F»; tarjetas de estado, veredictos y reparto con el estilo
  unificado (club: el suyo; plantilla simulada: media de la pertenencia de sus jugadores ponderada por minutos). Las
  barras por perfil del mapa quedan como detalle plegable.
- Arreglo previo: fila de jugador sin cerrar en «Simular equipo completo» (tarjetas anidadas).
- Capa de usabilidad: menos recuadros, filetes superiores, columna de controles fija y limpia.
- **Informe v3**: ver más abajo.

### Lectura de fichaje (informe PDF v3)
- Bloques: portada Ink · 01 Cerno Analytics (qué es, preguntas, método en cuatro pasos sin secretos, cómo leer las
  cifras, valores) · 02 El jugador (ficha, trayectoria con rol y estilo, medias, perfil por bloques, evolución) ·
  03 Conclusiones (Índice Fit con confianza, ADAPT% con rango 90 %, minutos con el rol, impacto en el Net, lo que aporta,
  adaptación, «Por qué lo proponemos», «Si cambias su rol» con los cinco roles, «Qué nos haría cambiar de opinión») ·
  04 Ataque y tiro · 05 Defensa y rebote · 06 Contexto y conexiones (carencias del club, estilo, química, quintetos,
  a quién quita minutos, lugar en la plantilla; sin destino, su papel en el club actual) · 07 Glosario (métricas,
  roles, estilos, normalización entre ligas) · contraportada.
- **Fallo de datos corregido**: `atlas/informe/<temp>.json` conserva la numeración de `persona_id` anterior al cambio
  de la fase 2 (solo coincidía el 0,2 % de las claves → «Sin datos detallados…»). Resolución en el navegador: clave
  exacta si existe; si no, emparejamiento dentro del club-temporada por minutos (asignación voraz). Pendiente en el
  pipeline: regenerar esos ficheros con los `persona_id` actuales.
- Descarga: «Descargar PDF» (descarga directa al equipo, permiso `downloads`), «Abrir en pestaña nueva» (genera el PDF
  y lo abre) y «HTML imprimible» (PDF vectorial desde el navegador). PDF rasterizado A4 (html2canvas o SVG).
- Nota del analista: caja de texto → «Redactar en tono Cerno» (Claude reescribe en 70-130 palabras, sin inventar
  datos) → texto editable que entra en Conclusiones. Se guarda por jugador y destino en el navegador.

### Equipos y quintetos (`quintetos/index.html`) y página principal (`index.html`)
- Ver el informe de cada parte en la sección «Verificación».

## Verificación
- Simulador: paridad sin rol (JS) y tests Python 15/15.
- Informe: 9 hojas sin desbordes (comprobado por hoja), sin errores; PDF generado en el navegador (9 páginas);
  brand_lint del HTML imprimible: 0 bloqueantes, 0 avisos (los `!important` de la capa F1 dan falsos positivos de
  tipografía en el lint y se excluyen).
- Interfaz (batería de regresión): inventario de controles antes/después por vista → la única baja es el botón
  «Ejecutar» y su panel (aprobado); filas de las tablas idénticas para las mismas entradas; paridad de la página
  principal en 26 comprobaciones sin diferencias; 0 errores de consola; capturas 1440/390 en claro y oscuro revisadas;
  brand_lint sin bloqueantes nuevos respecto a la versión vigente.
- Lo que no se puede ejecutar fuera del visor: la redacción con Claude (`sample`) y la descarga directa (`downloads`)
  piden permiso al abrir la página; se comprobaron con dobles locales, no en el visor real.
- Ficheros publicados: 210 (209 de la versión vigente o nuevos + página principal), verificado con el listado del
  artifact.

## Pendientes
- Confirmar la opción de nomenclatura para los modelos VaDE (perfiles de mapa) o re-estimar la química sobre los
  estilos nuevos en el pipeline.
- Regenerar `atlas/informe/*.json` con los `persona_id` actuales (pipeline) y quitar el emparejamiento por minutos.
- Altura y nacionalidad: faltan en la mayoría de ligas en los datos; el informe solo muestra lo disponible.
- El artículo metodológico PDF conserva nombres VaDE (sin fuente editable); su descarga ya no lleva «VaDE» en el nombre.
- PDF del informe rasterizado: para texto seleccionable, «HTML imprimible» → Guardar como PDF.
- F3: selector ES/EN; F2: revisión de superlativos heredados en textos de las vistas.
