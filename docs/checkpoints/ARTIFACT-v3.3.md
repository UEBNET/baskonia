# Artifact · datos con identidades corregidas, normalización v3.2 con vara elegible y simulador v3.3 (04-11-2026)

**Estado (04-11-2026): publicada en la URL de siempre** por indicación del usuario, tras añadir al Atlas la liga = 0
elegible y corregir la «Zona que ocupa cada estilo» del mapa 3D. Antes de publicar se comprobó que la versión vigente
(1793709008-72df) era idéntica a la integrada en Git (`f539a39`): no había cambios externos que fusionar.

| | |
|---|---|
| Publicada | https://claude.ai/artifact/F4AxayFrM2d1D5JEoNiDoN (versión 91, 1793784482-11a0, 265 ficheros, capacidades `downloads` y `sample`, runtime 0.2.92); la anterior, 1793709008-72df, queda en su historial |
| Copia de revisión | https://claude.ai/artifact/Kp7nAKMxXcy2oUSnPhhT6a (versión 1793782011-0fa0; sin el Atlas con liga = 0 ni la corrección del mapa; queda como duplicado de revisión) |
| Alcance aprobado | Datos + motor v3.3 + liga a 0; informe de equipo integrado en esta rama; copia de revisión primero |
| Origen de los datos | `experimentos/v33_artifact/` (no versionado), generado por `scripts/rehacer_identidades.sh` (pasos 7 y 8) |
| Lotes | `python artifact/empaquetar.py experimentos/v33_artifact/_publicacion experimentos/v33_artifact` → `lote0…4.json` |

## Qué cambia frente a la versión vigente

**Datos (todas las pestañas).**
- Identidades corregidas (BNXT y GBL reprocesadas, crosswalk con persona_id estables): `docs/identidades_20261103.md`.
- Nombres canónicos «Nombre Apellido(s)» en la Mesa, el Atlas, Quintetos y el simulador (`bbmodel/nombres.py`). Los
  miembros de una plantilla sin registro ni nombre canónico también se escriben así (un caso: «MAJAUSKAS, AURIMAS» →
  «Aurimas Majauskas»).
- Normalización v3.2 (`data/modelos/v3_2/normalizado`) en «Datos normalizados», «Normalización de ligas» y el Atlas.
- Evaluación de equipos de Quintetos, escalas ±100, estilos unificados de Quintetos y extras del informe de equipo,
  regenerados con estos datos. El generador de estilos unificados ignora ahora los ficheros `.extras`.

**Liga a 0 (vara elegible).**
- `datos/normalizados/vara.json` (`bbnorm3.destino.vara_artifact`): constantes por métrica para expresar el
  equivalente EuroLeague en la vara de cualquier liga:
  - z_EL = (T(v) − μ_EL,pos)/τ_EL,pos; z_d = (z_EL − δ_d)/s_d; valor = T⁻¹(μ_d + τ_d·z_d);
  - cada cola del intervalo del 80 %: v_j = sd_EL² − sd_par(o,EL)² (≥ 10 % de sd_EL²) y
    sd_d² = (v_j + sd_par(o,d)²)/s_d² + (distancia fuera del soporte)².
- Mesa · «Datos normalizados»: selector «Vara (esta liga = 0)». Con la EuroLeague se muestran los valores publicados.
- «Normalización de ligas»: la vara es la fila de referencia, la EuroLeague entra en el ranking y los niveles y
  distancias se miden respecto a la vara. Las conclusiones redactadas frente a la EuroLeague se ocultan con otra vara.
- Comprobado: conversión JS = referencia Python `desde_el` (diferencia máxima 2·10⁻¹⁴ en 40 jugadores × 3 ligas ×
  3 métricas); prueba en navegador `tests/js/mesa_vara.js` en verde.

**Simulador de encaje v3.3 en el navegador** (`atlas/simulador.js`, sustituye a `atlas/simulador_v2.js`).
- Minutos publicados: mezcla 50/50 del motor y el GBM (`min_gbm` por registro y liga de destino); intervalos
  desplazados, recortados y recalibrados.
- B9 con rol asignado: Δy = b·Δmin + c·Δrol sobre la producción del Atlas.
- Producción del Atlas con contexto y recalibración A4 de dos colas, como en la v3.2 publicada.
- Paridad con Python: 12/12 casos dentro de tolerancia (`tests/js/paridad_simulador.js`), con rol libre, ROTACION y
  TITULAR. Corregido durante la paridad: sin edad conocida, la producción del Atlas no aplica deriva (como Python).
- Etiquetas visibles «simulador v3.3»; prueba del Atlas en navegador `tests/js/atlas_simulador.js` en verde.

## Atlas con liga = 0 y zona de los estilos (petición del 04-11-2026, tras la revisión)

- Alcance aprobado: nivel + rasgos + normalizados en el Atlas; selector compartido con la Mesa.
- Selector «Liga = 0» en Ajustes de la Mesa; los de «Datos normalizados» y «Normalización de ligas» son el mismo.
- `ESC` (bloque de escalas del Atlas): `setVara(liga, ganchos)`. Familias que siguen a la vara: `nivel`, `rapm`,
  `orapm`, `drapm`. Nivel: referencia = media de L de la liga en la temporada (`familias.nivel.ligas`; sin dato,
  referencia Euroliga + diferencia media). RAPM: media por minutos del RAPM-EL de sus jugadores. Percentiles: sobre
  sus jugadores (nivel con `muestra`, RAPM con la muestra de RAPM). El resto de familias no cambia.
- Rasgos: media de los clubes de la liga en la temporada (`XREF.por`). Ranking y desglose de «Simular equipo
  completo»: clubes de la liga en la última temporada completa.
- Métricas normalizadas mostradas: `enVara` (valor central de `desde_el`) en las tablas de contexto, el ejemplo de
  Claves y el informe de fichaje; el RAPM-EL se muestra siempre en la vara Euroliga.
- No cambian: Net, on/off, sinergias, quintetos, comparaciones del informe con los jugadores de la Euroliga de su
  puesto y la página de Quintetos (Equipos), que mantiene su escala.
- Mapa 3D: corregida la «Zona que ocupa cada estilo» (Cholesky con valores de prueba en el triángulo superior).
- Pruebas en verde: `tests/js/atlas_vara.js`, `mesa_vara.js`, `atlas_simulador.js`, `paridad_simulador.js`.

## Puntos/100 y 200 minutos (petición del 04-11-2026)

- Puntos/100: extremos inferiores recortados a 0 en Python y JS, con asterisco y nota al pie que nombra los factores
  del caso (nivel, rol y minutos, adaptación, estilo, tipo de traspaso). Ejemplo: Pablo Gimeno (Tercera FEB) a la NBA
  como Profundidad: 3,6 pts/100, rango 90 % 0–13,2; pesan nivel −86 frente a +15 de la NBA, 12,6' por partido,
  adaptación 94 % y traspaso desde la Tercera FEB.
- Tapones/100, rebotes ofensivos/100 y AST%: mismo recorte (decisión del usuario, 04-11-2026).
- «Simular equipo completo» siempre a 200' dentro de las franjas de rol (decisión: ajuste en la franja); rojo y cambio
  de rol a mano cuando no cabe. Con una plantilla real de 15 jugadores y los roles estimados por defecto sobran 33'
  (el cuadro sale en rojo hasta ajustar roles); con 5 titulares, 4 de rotación y 6 de profundidad cuadra en 200'.

## Referencia por contexto (petición del 04-11-2026)

- Planificación e informe de fichaje: 0 = la liga del club elegido (destino). Estilos: cada equipo y jugador frente a su
  propia liga. Jugadores y Metodología: la «Liga = 0» de Ajustes. Equipos y quintetos (página de Quintetos) no cambia.
- Recorte a 0 también en tapones/100, rebotes ofensivos/100 y AST%.
- Observado (sin cambiar): en la escala de nivel el 0 es el jugador medio de la liga (por minutos); el «club medio»
  de una liga queda algo por encima (EuroLeague media +10), porque el nivel de club se lee como L equivalente.

## Lo que no cambia (para tu decisión)

- «Simular equipo completo» reparte con el motor y las franjas de rol, sin la mezcla GBM (la mezcla es una predicción
  por fichaje y no suma 200' por equipo).
- Los nombres de club conservan el formato de la fuente (p. ej. «SILBÖ SAN PABLO BURGOS»): la unificación pedida era
  de jugadores.

## Publicación

Cinco lotes (`lote0…4`, versiones 87-91) en https://claude.ai/artifact/F4AxayFrM2d1D5JEoNiDoN; `atlas/simulador_v2.js`
borrado en el último. Las fuentes y el PDF del artículo de estilos ya estaban publicados. Para volver a publicar:
`python artifact/empaquetar.py <salida> experimentos/v33_artifact` y los lotes con la herramienta Artifact (`url` = la de
siempre).
