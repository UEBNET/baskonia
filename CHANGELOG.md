# Registro de cambios

## 2026-11-04 — Equipos y quintetos con su propia liga = 0 y clubes frente al club medio

Decisiones del usuario (04-11-2026). Publicado en https://claude.ai/artifact/F4AxayFrM2d1D5JEoNiDoN.

* **Clubes y plantillas: 0 = club medio de la liga de referencia** (antes, el jugador medio por minutos, que dejaba el
  club medio en torno a +10). Atlas: `enClub`/`sNivCL` y `ESC` con `HV.refClub` (media del nivel de los clubes de esa
  liga y temporada; percentil entre sus clubes) en tarjetas, mapa, comparador, simulador, equipo completo (nivel,
  ranking, aporte, plantilla) e informe de fichaje. «EuroLeague (media)» marca ahora ±0 y Baskonia 2025-26 −5.
* **Equipos y quintetos** (`artifact/quintetos/index.html`): su propia liga = 0. Jugadores, quintetos, tríos y parejas
  frente al jugador medio de su liga; equipo y plantillas (Evaluación, historial, todos los equipos, entrenadores)
  frente al club medio de su liga, con percentiles dentro de ella. Las cifras que comparan ligas entre sí («Nivel de su
  liga», franja «Ligas», columna «Nivel liga», guía de escalas) siguen con la Euroliga = 0 y lo dicen.
* Mesa: ayuda de «Liga = 0» con el alcance de cada pestaña.

## 2026-11-04 — Referencia de nivel por contexto (liga del club elegido / liga propia) y recorte a 0 ampliado

Decisiones del usuario (04-11-2026). Publicado en https://claude.ai/artifact/F4AxayFrM2d1D5JEoNiDoN.

* **Referencia de la escala ±100 por contexto** (`conVara`, `enPropia`, `refEnt` en `atlas/index.html`):
  * **Planificación** (Simular fichajes, Simular equipo completo): 0 = la liga del club elegido. Pablo Gimeno a Surne
    Bilbao: nivel −83 con ACB = 0 (antes −86 frente a la Euroliga); al Baskonia de Tercera FEB: +5 con Tercera FEB = 0.
    El ranking y el desglose del equipo completo son frente a los clubes de esa liga.
  * **Informe de fichaje (PDF)**: 0 = la liga del club de destino (sin destino, la del jugador).
  * **Estilos** (Mapa y comparador, Química de perfiles): cada equipo y cada jugador frente a su propia liga
    (tarjetas, tooltips del mapa, perfil de rasgos, química).
  * **Jugadores** (Datos normalizados, Buscar parecidos) y Metodología: la «Liga = 0» de Ajustes, como antes.
* **Recorte a 0** ampliado a tapones/100, rebotes ofensivos/100 y AST% (`RECORTE_CERO`), con la misma nota al pie, que
  ahora nombra cada métrica recortada y mide el nivel frente a la liga de destino.

## 2026-11-04 — Puntos/100 sin rangos negativos y «Simular equipo completo» siempre a 200'

Decisiones del usuario (04-11-2026). Publicado en https://claude.ai/artifact/F4AxayFrM2d1D5JEoNiDoN.

* **Puntos/100**: los extremos inferiores de sus intervalos (50/80/90 %) se recortan a 0 (`bbfit.simulador.recorte_cero`
  y `recorteCero` en `atlas/simulador.js`, marca `recorte_cero`); el centro no cambia, así que error y cobertura del
  examen tampoco. Asterisco y **nota al pie** en la tarjeta del simulador y en el informe de fichaje (`notaCero`): explica
  que el rango llegaba a 0 por una producción esperada baja con un margen de error amplio, y nombra los factores de ese
  fichaje: nivel frente a la media de la liga de destino, rol y minutos, adaptación de primera temporada, estilo (Fit) y
  tipo de traspaso (Tercera FEB, NCAA, NBA/G League, los de más error en el examen). Sólo puntos/100, como se pidió.
* **«Simular equipo completo» reparte siempre 200'** (`cuadrarRoles` en `atlas/simulador.js`; la simulación de un
  fichaje no cambia): cada jugador se mueve sólo dentro de la franja de su rol, en la misma proporción para todos,
  hasta sumar exactamente 200'. Si ni con el mínimo de cada franja se baja de 200' (sobran) o ni con el máximo se llega
  (faltan), el cuadro se pone **en rojo** y pide **cambiar a mano el rol de algún jugador** (o añadir jugadores). Antes,
  los minutos de los roles se recortaban en silencio al 90 % del partido.
* Prueba nueva: `tests/js/equipo_200.js`.

## 2026-11-04 — Atlas con liga = 0 elegible y zona de los estilos corregida · v3.3 publicada

Detalle: `docs/checkpoints/ARTIFACT-v3.3.md` (§ Atlas con liga = 0). **Publicada en la URL de siempre**
(https://claude.ai/artifact/F4AxayFrM2d1D5JEoNiDoN, versión 91, 265 ficheros), con todo lo de la entrada siguiente.

* **Liga = 0 en toda la herramienta**: selector en Ajustes de la Mesa (`#ebVara`), sincronizado con los de «Datos
  normalizados» y «Normalización de ligas» y enviado al Atlas (mensaje `{vara}` y `localStorage mm.vara`).
* **Atlas** (decisión del usuario: nivel + rasgos + normalizados; selector compartido):
  * escala ±100 de **nivel** (jugadores, clubes, plantillas, ligas) con 0 = media de L de la liga elegida en esa
    temporada (`escalas.familias.nivel.ligas`), percentiles y ranking frente a sus jugadores y clubes;
  * **RAPM-EL**: 0 = media por minutos de los jugadores de esa liga; el valor original sigue en la vara Euroliga;
  * **rasgos** y desglose por métricas frente al club medio de esa liga;
  * **métricas normalizadas** mostradas (contexto, informe de fichaje) convertidas con `vara.json` (misma fórmula que
    la Mesa); los cálculos internos (mapa, estilo, química, proyección) no cambian;
  * Net, on/off, sinergias y quintetos siguen como estaban (su 0 ya es la media de cada liga).
  Con la Euroliga elegida, las cifras son exactamente las publicadas.
* **Mapa 3D · «Zona que ocupa cada estilo»**: la descomposición de Cholesky partía de una matriz con valores de prueba
  en el triángulo superior (`[[18, 22, 27], …]`), así que cada elipsoide se estiraba decenas de unidades y aplastaba el
  mapa. Ahora parte de ceros: elipsoides de 1 desviación típica alrededor del centro de cada estilo.
* Mesa: la carga de la vara ya no cambia `st.vara` mientras lee los equivalentes EL (la pestaña «Normalización de
  ligas» podía pintarse con la Euroliga durante la carga).
* Pruebas: `tests/js/atlas_vara.js` (nueva) y `tests/js/mesa_vara.js`, `atlas_simulador.js`, `paridad_simulador.js`.

## 2026-11-04 — Artifact v3.3 (copia de revisión): datos nuevos, vara «liga = 0» y simulador v3.3 en el navegador

Detalle: `docs/checkpoints/ARTIFACT-v3.3.md`. Revisada primero en una copia (https://claude.ai/artifact/Kp7nAKMxXcy2oUSnPhhT6a)
y publicada después en la URL de siempre (entrada anterior).

* Datos de todas las pestañas con identidades corregidas, nombres «Nombre Apellido(s)» y normalización v3.2.
* Mesa: selector de vara (cualquier liga = 0) en «Datos normalizados» y en «Normalización de ligas»
  (`datos/normalizados/vara.json`, `bbnorm3.destino.vara_artifact`; conversión JS = referencia Python `desde_el`).
* Atlas: motor `atlas/simulador.js` v3.3 (minutos mezcla motor + GBM, B9 con rol asignado), con paridad 12/12 con
  Python. Sustituye a `atlas/simulador_v2.js`, que se retira del repositorio y de la publicación junto a su prueba
  (`artifact/herramientas/test_paridad_simulador.js`).
* `artifact/empaquetar.py` con origen de datos configurable; paso 8 de `scripts/rehacer_identidades.sh` (quintetos,
  escalas, equipos, estilos, compactación, paridad y lotes).
* Pruebas: `tests/js/paridad_simulador.js` (v3.3), `tests/js/atlas_simulador.js` (al día con la interfaz actual) y
  `tests/js/mesa_vara.js` (nueva).

## 2026-11-04 — Identidades corregidas, nombres canónicos y simulador v3.3

Detalle: `docs/identidades_20261103.md` y `docs/simulador_v33.md`. Cadena completa: `scripts/rehacer_identidades.sh`.

**Identidades**
* Adaptador FIBA LiveStats: si la ficha internacional es de otro jugador (nombre local latino sin ninguna palabra en
  común), la clave sale del nombre local; nombre visible latino en la GBL (antes en griego). BNXT y GBL reprocesadas.
* Crosswalk con persona_id estables: ningún nodo existente cambia de persona. Se separan las 5 identidades mezcladas
  (Pot/Vandenbossche, De Wilde/Vaneyk, Marinelli/Ciccioni, Van Der Schalie/Borst, Fasasi/Thomasson) y se reasignan
  27 apariciones de un partido atribuidas a otro jugador. Auditoría: 2 marcas de 19.330, las dos la misma persona.
* Revisión manual de los 100 puentes (§13): 100/100 correctos, cota inferior 0,964 ≥ 0,95; el umbral no cambia.

**Nombres «Nombre Apellido(s)»** (`bbmodel/nombres.py`, `data/processed/nombres_canonicos.csv`)
* Una forma por persona en todas las exportaciones del artifact: «APELLIDO, NOMBRE» → «Nombre Apellido», mayúsculas
  capitalizadas con tildes recuperadas, dos apellidos cuando la fuente los da, griego y cirílico transliterados.
* Nombres completos de la web de la FEB (`scripts/feb_nombres_web.py`): de 2.501 jugadores FEB con inicial quedan 488.
  Quedan con inicial 947 personas en total (sobre todo la CBA y la FEB sin página de equipo).

**Normalización v3.2 y simulador v3.2 rehechos con los datos corregidos** (la ablación conserva su decisión)
* Normalización: v3.2 publicada −3,2 % [−3,6, −2,8] frente a la v2 (antes −2,8 %), cobertura 0,811; red sola −2,0 %.
* Simulador v3.2: mismas decisiones (fuera uso-eficiencia y compañeros, producción del Atlas, A4); pts/100 3,85 →
  3,81, TS% 5,24 → 4,98, cobertura 80 % de pts/100 0,72 → 0,80. B7 −3,2 %; B9 sigue abierto.
* Corregido: la cadena reutilizaba salidas ya existentes (F0, predicciones de las redes, niveles, histórico) y los
  exámenes del simulador corrían con la configuración publicada; ahora se borran al empezar y
  `v32.config_examen` deja el motor completo antes de los backtests.

**Simulador v3.3** (`configs/simulation_v33.yaml`, `CERNO_SIMULADOR=v33`; la v3.2 no cambia)
* M: minutos de la **mezcla motor + GBM** (elegida por el examen): 4,87 → 4,70 min (IC 90 % −0,20, −0,14).
* B9: acoplamiento minutos-producción; con rol asignado, pts/100 −4,6 % [−5,7, −3,7] y TS% −2,2 % [−3,1, −1,5].
* Rol asignado en la configuración (faltaba en v3.1/v3.2), intervalos anidados, exportación con `meta.v33` y minutos
  del GBM por liga de destino (`jugadores.json → min_gbm`).

## 2026-11-03 — Normalización v3.2 y simulador v3.2 (versiones nuevas, la v3.1 queda intacta)

Configuraciones nuevas, que no sustituyen a las anteriores: `configs/normalization_v32.yaml` (salida
`data/modelos/v3_2/`) y `configs/simulation_v32.yaml` (`CERNO_SIMULADOR=v32`, salida `data/modelos/simulador/v3_2/`).
Criterios fijados antes de ver los resultados (documento de criterios del 02-11-2026; paquete aprobado). Detalle y
cifras: `docs/normalizacion_v32.md`, `docs/simulador_v32.md`. Cadena reanudable: `scripts/actualizar_v32.sh`.

**Normalización v3.2**
* **B1, B4, B6 · ablación** con cortes anidados 2022-2024, 5 redes por variante y regla de no inferioridad (IC95,sup
  < +0,5 %, cobertura en [0,78, 0,85], salvaguardas de ciclo y de niveles) (`python -m bbnorm3 ablacion`).
  Se quitan K = 8 (queda K = 4), la inferencia semiamortizada (B4), FiLM, el cabezal por liga y la t de Student (B6).
  Se conservan ζ, la consistencia de ciclo (salvaguarda) y la IPW (salvaguarda de niveles). La combinación de las cinco
  bajas cumple en 2023 (−1,1 %) y 2024 (−1,4 %). Las piezas siguen en el código y en `_completa`.
* **B5 · ensemble de 20 redes**; la salvaguarda de discrepancia (> 0,5 DT) no se activa en ningún caso.
* **B2 · peso de mezcla por métrica** (regla del 1 %): solo el RAPM pasa a w = 1; el resto se queda en 0,5.
* **Examen anidado**: red sola −1,4 % frente a la v2; v3.2 publicada −2,8 % [−3,2, −2,4], cobertura 0,811.
  Falla la cobertura en 4 pares (Segunda → Tercera FEB, G League ↔ NBA, NCAA → NBA): pendiente del examen limpio.
* **Vara de destino (clave)**: cualquier liga a 0. `python -m bbnorm3 destino` exporta en `data/modelos/v3_2/destino/`
  las constantes por liga de destino (δ_d, s_d), la covarianza del nivel por par (v2 con covarianza, red y mezcla con
  la cota de Cauchy-Schwarz), la capacidad de cada jugador (θ, v_j) y la marca de extrapolación, sin recortar el
  centro. §11b: la varianza propia del RAPM resta el nivel con el mismo modelo que da el valor de la fila.
* **§13** muestra de 100 puentes para revisión manual (`python -m bbmodel auditoria-puentes`) y página interactiva.

**Simulador v3.2**
* **Fuente sin fuga `V32_corte`**: normalización ajustada solo con temporadas ≤ t en cada corte.
* **A1** (pasos con no inferioridad): fuera la curva uso-eficiencia y el efecto compañeros; se conservan la
  redistribución del uso, la adaptación y el ruido personal. **A3**: la rejilla queda en k = (0, 0).
* **A2**: se publica la producción del Atlas (J_ω −1,0 %), con los minutos y el rol del motor.
* **A4**: recalibración conformal de dos colas por métrica × grupo de destino, con recencia y contracción
  (n0 = 30). Cobertura de pts/100 50/80/90 %: 0,42/0,71/0,84 → 0,50/0,80/0,90.
* Examen anidado: pts/100 3,85 → 3,81; TS% 5,24 → 4,97; contribución C 4,66 → 4,50; Spearman por liga 0,44 → 0,47.
* **B7 y B9** evaluados sin aplicarse (`python -m bbfit b7-b9`): B7 −4,7 % (no llega al −5 %); B9 cumple la regla de
  apertura y queda propuesto para una v3.3, pendiente de aprobación.
* Descartados B3 y B8 (B8 figura como trabajo futuro en el artículo).

**Artículo científico v3.2**: `docs/articulo/cerno_lectura_entre_ligas_v3_2.pdf` (`python -m cerno_articulo`)
sustituye a `docs/articulo/estilos_de_juego_baskonia.pdf`. Prerregistro del examen limpio 2026-27:
`docs/preregistro_2026-27.md`.

## 2026-11-01 — 20 ligas: CBA, BNXT, NCAA D-I (top-50), NBL y VTB

* Extracción 2020-21 → 2026-27 (corte 29-10-2026) desde el jugada a jugada, con adaptadores que traducen cada partido
  al data.json de FIBA LiveStats (`bbstats/adapters/{nbl,vtb,ncaa,cba}.py`; BNXT por configuración de FIBA LiveStats).
  Fuentes, cobertura, controles y huecos: `docs/fuentes_ligas_nuevas.md`.
* Crosswalk: regla inicial + apellido + fecha de nacimiento. Nacionalidad y fecha de nacimiento de VTB y CBA.
* Normalización v3.1 rehecha con 20 ligas (tramo de desarrollo NCAA, escalones nuevos), roles, estilos (mapa 3D con
  la taxonomía unificada), adaptación (grupo `NCAA_a_profesional`) y simulador cruzado; examen y auditorías.
* Artifact CERNO publicado en la misma URL con las 20 ligas en todas las pestañas (compactación sin pérdida).

## Lectura de fichaje v3.1 → v3.3 (29-10-2026, publicada en el enlace vigente)

Solo cambia `artifact/atlas/informe_v3.js` (versión publicada 1793286109-fca7). Detalle y verificación:
`docs/checkpoints/INFORME-v3.3.md`. Arnés de prueba nuevo: `artifact/herramientas/prueba_informe.py`.

- **v3.1 · contenido y composición**: frase nueva en «Basketball judgment, model rigor»; títulos por facetas desde la
  sección 02 (la conclusión pasa a la entradilla); panel Ink central en 02 (estilo, Nivel Cerno, impacto, punto fuerte,
  a mejorar); «Por qué lo proponemos» abre 03; curva ADAPT% con la pérdida sombreada; 04/05 sin cifras en el título y
  con cifras clave (valor + percentil + rango); 04 sin «Qué produce hoy por cada 25 minutos», 9 métricas con el rol
  asignado y mapa de tiro más grande; 06 en tres páginas (carencias y estilos · sinergias de pareja y quinteto ·
  minutos e impacto en los compañeros) sin «Conexiones»; clasificaciones en columna; «percentil N» como forma única.
- **v3.2 · títulos y plantilla**: títulos de sección en Index sobre banda Ink (contraste 11,6:1). Selector
  «Compañeros en el club de destino»: quitar jugadores y añadir otros (bajas/extras del simulador v2.1, como en
  «Simular equipo completo»), guardado por club y temporada (`st.inf.plant`). Lugar en la plantilla, nivel medio y
  química salen de esos compañeros y el informe rotula los cambios.
- **v3.3 · adaptación**: la frase de adaptación lee la forma de la curva del simulador (arranca arriba y baja, arranca
  abajo y recupera, o estable) en lugar de decir siempre «perdería un poco al principio».
- Sin cambios en el motor, los datos ni el resto del artifact.

## Artifact v2 (publicada en el enlace vigente) y simulador v2.1 (29-10-2026)

Detalle, verificación y pendientes: `docs/checkpoints/ARTIFACT-v2.md`. Especificación de la interfaz: `docs/ux/UX-SPEC.md`.

- **Simulador v2.1 (rol asignado)**: `simular(..., rol=, roles=)` en Python y `simular({rol, roles})` en JS. El club
  elige el rol (RESIDUAL, PROFUNDIDAD, ROTACION, TITULAR, GO_TO_GUY) y el motor fija los minutos en la franja del rol
  en la liga de destino, la titularidad y el reparto del resto de la plantilla; se mantienen todas las salidas del
  Índice Fit. Constantes en `configs/simulation.yaml → rol_asignado` (exportadas en `meta.rol_asignado`).
  Sin rol, resultados idénticos a v2.0 (`tests/test_simulation.py::test_sin_rol_es_v20`,
  `artifact/herramientas/test_paridad_simulador.js`).
- **Artifact**: fuera el botón «Ejecutar» (única baja aprobada); capa de usabilidad `cerno-ux` en las tres páginas
  (mueve y agrupa, no cambia ids, opciones, claves de almacenamiento ni cálculos); rol visible en las tablas; selector
  de rol en «Simular fichajes» y «Simular equipo completo»; estilos solo con la taxonomía nueva (los grupos del mapa
  se rotulan «Perfil de mapa A–F»); lectura de fichaje en PDF v3 (`artifact/atlas/informe_v3.js`) con nota del
  analista redactada por Claude.
- **Corrección**: el informe del Atlas no encontraba datos porque `atlas/informe/*.json` conserva los `persona_id`
  anteriores a la fase 2; el navegador resuelve por clave y, si falta, por minutos dentro del club-temporada.
  Pendiente en el pipeline: regenerar esos ficheros.
- `artifact/empaquetar.py` publica también `atlas/informe_v3.js` y `quintetos/estilos_unificados*.gz.txt`.

## Encaje v2 (fases 1-9, 21-10-2026 → 23-10-2026): resumen consolidado

Proyecto multifase sobre la línea base de la auditoría `docs/AUDIT_2026-10-21.md`. Cada fase tiene código, YAML en
`configs/`, tests sintéticos, registro en MLflow e informe en `docs/checkpoints/F<n>.md`.

| Fase | Qué añade | Órdenes | Salidas | Informe |
|---|---|---|---|---|
| 1 | Primera, Segunda y Tercera FEB en el esquema común; contrato de datos; posesiones reales; correspondencia de jugadores entre ligas | `bbstats historico/feb/contrato`, `bbmodel crosswalk` | `data/processed/…/feb/`, `feb_*.csv`, `player_id_crosswalk.csv` | F1 |
| 2 | Normalización amortiguada (grafo de puentes con varianza acumulada, contracción por escalón, mapeo monótono probado, λ(d) → constante, IPW); 15 ligas en `bbmodel`/`bbestilo` | `bbmodel amortiguar` | `normalizacion_amortiguada/`, columnas `<m>_am*` del dataset normalizado | F2 |
| 3 | Roles por minutos (RESIDUAL … GO-TO-GUY), GTI, vector de rol, cambios de rol (BOCPD) | `bbfit roles` | `roles/` | F3 |
| 4 | Reemplazo de rol: libro de volumen, desplazamiento de minutos / de rol, tasa de relleno, elasticidad uso–eficiencia con IV, suma fija del uso, minutos endógenos | `bbfit reemplazo` | `reemplazo/` | F4 |
| 5 | Entropía de estilo y de rol, volatilidad σ_i, entropía de equipo | `bbfit entropia` | `entropia/` | F5 |
| 6 | Taxonomía unificada de 6 estilos jugador ↔ equipo | `bbfit estilos` | `estilos_unificados/` | F6 |
| 7 | Adaptación al cambio de liga: Δ jerárquico, curva, censura IPCW, priors, ADAPT% | `bbfit adaptacion` | `adaptacion/` | F7 |
| 8 | Simulador de encaje v2 (rol y minutos endógenos, Fit descompuesto, avisos) y su validación | `bbfit simular` y órdenes de la fase 8 | `simulador/v2/`, `data/artifact/simulador/` | F8 |
| 9 | Documentación: artículo con Parte II y notación formal, LaTeX autónomo, diccionario de datos, glosario, README, contexto | `bbestilo articulo` (= `python -m bbfit.articulo`) | `docs/articulo/`, `docs/data_dictionary.md`, `docs/glosario.md` | este registro |

### Cambios incompatibles (breaking changes)

1. **Identidad de personas**: los modelos A/B usan también las uniones automáticas del crosswalk y el umbral de
   fusión pasa de 0,80 a **0,75** (fase 2, decisión del usuario): cambian `persona_id` y el número de personas
   (39.647 registros, 14.535 personas). Cualquier unión guardada por `persona_id` anterior debe rehacerse.
2. **15 ligas en los modelos**: A, B, pista, contexto, interacciones, escalas y `bbfit reemplazo` se reajustaron con
   las FEB; todos los equivalentes EuroLeague, L y percentiles cambian. `algoritmo_A/validacion.csv` sigue siendo de
   12 ligas (no se relanzó `bbmodel validar`). VaDE (Parte I) no se reentrenó con las FEB.
3. **L, contexto y escalas ±100 leen `<m>_am`** (normalización amortiguada) en vez de A+B
   (`configs/normalization.yaml → usar_amortiguado`); las columnas antiguas del dataset normalizado no cambian, pero
   `L`, `ctx_*` y las escalas sí.
4. **Corrección de σ²** en `bbmodel/suerte.py` (pendiente ≤ 0 → mediana de las demás ligas): cambia el paso 1 del A
   en BCL, NBA, FEC y Segunda FEB (p. ej. σ² de pts/100 en la BCL de 1,8·10⁻⁴ a 105,2).
5. **Cortesía HTTP compartida**: `bbstats/http.py` aplica la pausa por dominio a todos los clientes del proceso
   (antes, por cliente): las descargas en paralelo contra un mismo dominio son más lentas.
6. **Configuración YAML** (`configs/*.yaml`) para todas las capas nuevas y registro MLflow en `experimentos/`
   (no versionado; MLflow 3 necesita `MLFLOW_ALLOW_FILE_STORE=true`, que `bbfit.registro` fija).

## 2026-10-29 — Fase 8: simulador de encaje v2 (sin minutos manuales) y su validación

Añadido
* `bbfit/simulador.py` (motor Monte Carlo: nivel traducido con la normalización amortiguada, adaptación de la fase 7,
  rol y minutos endógenos con Plackett-Luce y las tendencias del entrenador, uso de suma fija y curva uso-eficiencia,
  compañeros, estilo y complementariedad, ruido personal, ritmo; Fit aditivo; impacto en el Net; quintetos; avisos),
  `bbfit/sim_insumos.py`, `bbfit/validacion.py` (examen temporal cronológico, baselines, bootstrap por club, segmentos,
  dejar fuera una liga, normalización reajustada con ≤ t), `bbfit/sim_exportar.py`, `configs/simulation.yaml`.
* Órdenes `python -m bbfit simular | backtest | pesos-simulador | historico | exportar-simulador`.
* `data/modelos/simulador/v2/` (histórico versionado v2.0, pesos, validación) y `data/artifact/simulador/` (no versionado).
* Atlas: «Simular fichajes» y «Simular equipo completo» sin campos de minutos; tarjetas v2 (roles, minutos e intervalos,
  producción por 100 y por partido, Fit descompuesto, ADAPT% y curva, impacto, quintetos, avisos); motor en
  `artifact/atlas/simulador_v2.js`; nombres de estilo unificados en tablas, fichas, leyenda y tooltips (VaDE como
  «estilo de mapa»); búsqueda de jugadores que sólo están en el simulador (FEB).
* Tests: `tests/test_simulation.py` (13), `tests/js/paridad_simulador.js`, `tests/js/atlas_simulador.js`.

Cambiado
* `bbfit/reemplazo.py::asignar_minutos`: argumentos opcionales `niveles_sim` y `presencia` (sin cambio por defecto).
* `bbestilo/exportar.py`: exporta el mapa con las competiciones del modelo VaDE guardado (12; las FEB no tienen estilo
  VaDE) y añade `tid` (clubes) y `pid` (jugadores) para enlazar con el simulador. `bbestilo/datos.construir` y
  `encaje.conjunto` aceptan `ligas`.
* `artifact/empaquetar.py`: publica `atlas/simulador_v2.js` y `atlas/simulador/*.json`.

Resultados (examen 2021-22 … 2024-25 → t+1, 4.512 fichajes): MAE de minutos 4,71 frente a 5,84 (Atlas anterior) y 5,63
(modelo simple); log-loss de rol 1,235 frente a 2,676 y 1,257; pts/100 empate con el Atlas anterior y mejor que el
simple; TS% peor que ambos. Detalle en `docs/checkpoints/F8.md`.

## 2026-10-23 — Fase 9: documentación (artículo científico descartado)

Añadido
- `docs/data_dictionary.md` (todas las tablas de `data/processed/` y `data/modelos/`), `docs/glosario.md` (roles,
  estilos y medidas para dirección deportiva); README §17-§20 (orden de ejecución de `bbfit`, `configs/*.yaml`,
  MLflow); secciones nuevas en `CONTEXTO_AGENTE.md`; este resumen consolidado.

Cambiado
- `bbestilo/figuras.py`: paleta de 15 ligas.

Retirado (26-10-2026, por decisión del usuario: el artículo científico no se actualiza)
- La Parte II del artículo (`bbfit/articulo.py`, `docs/articulo/fit_v2.tex` y figuras, recursos KaTeX y fuentes,
  `tests/test_articulo.py`); el PDF y `bbestilo/articulo.py` vuelven a su versión anterior.

## 2026-10-23 — Fase 7: adaptación al cambio de liga (`bbfit adaptacion`)

Añadido
- `bbfit/adaptacion.py` y `python -m bbfit adaptacion [--rehacer] [--sin-validacion]` (reanudable, caché en
  `experimentos/cache_adaptacion/`); hiperparámetros en `configs/adaptacion.yaml`; registro en MLflow.
- Interfaz para el simulador: `prior(liga_origen, liga_destino, grupo_nacionalidad, pos3, metrica)` con jerarquía de
  reserva celda → par → escalón de destino → global, `grupo_nacionalidad(...)` y `curva(g, delta, kappa)`.
- Identificación de 5.040 traspasos (entre temporadas, adiciones y dentro de la temporada) con el `persona_id` del
  crosswalk 0,75; ŷ = origen traducido a la escala de destino invirtiendo la normalización amortiguada; modelo
  jerárquico gaussiano (Gibbs) del log-cociente y/ŷ con efectos de pareja y escalón y covariables (nacionalidad,
  pos3, arquetipo, edad, roles, salto de nivel, estilo de equipo, entrenador); curva por partido con grupo de control;
  IPCW de la censura; ADAPT% por traspaso con examen temporal, dejando fuera una liga y calibración.
- Salidas en `data/modelos/adaptacion/` (`adaptation_priors.csv`, `adapt_historico.csv.gz`, `adapt_pct_roles.csv`,
  coeficientes, hipótesis EE. UU., curvas, censura, supervivencia, segunda temporada, validación, calibración).
- Tests sintéticos `tests/test_adaptacion.py` (10).

Resultados principales: estadounidense en su primer año europeo −6,8 % [−9,7, −3,8] de ADAPT% compuesto frente al
europeo que cambia de liga (sin adaptación más lenta detectable); sin hueco de arranque propio del que cambia de liga
(todos arrancan ~2 % abajo); el IPCW baja el Δ medio 1-2 puntos.

Detalle, resultados y riesgos: `docs/checkpoints/F7.md`.

## 2026-10-23 — Fase 6: taxonomía unificada de estilos jugador ↔ equipo

Añadido
- `bbfit/estilos_unificados.py` y `python -m bbfit estilos [--reusar-k]`: 12 rasgos con la misma definición para
  jugador y equipo (ritmo, 3PAr, triple de esquina, aro, FTr, canastas sin asistencia, AST%, rebote ofensivo,
  TOV%, robos, tapones, faltas) en z por rangos dentro de cada liga-temporada (15 ligas, incluidas las FEB);
  mezcla gaussiana ajustada sobre jugadores (≥ 300 min) con proyección de los equipos; K por BIC + estabilidad
  bootstrap → **6 estilos**: Spacing, Circulación, Isolation, Old-School, Pistons, Pintura. Estilo principal,
  secundario, vector de pertenencia y etiqueta («puro», «A · B») por equipo-temporada, jugador-etapa y tramo de
  entrenador. Registro en MLflow (experimento `estilos_unificados`).
- `configs/styles.yaml` (umbrales, regla de K, nombres, colores, definiciones y firmas de nombre).
- Salidas `data/modelos/estilos_unificados/{equipos.csv, jugadores.csv.gz, estilos.json, seleccion_k.json,
  correspondencia_vade.csv}`; correspondencia con VaDE (ARI 0,03: miden cosas distintas).
- Tests sintéticos `tests/test_estilos_unificados.py`.

Cambiado
- `bbestilo/exportar.py`: campos nuevos `eu`, `eu2`, `eu_p`, `eu_probs`, `eu_etiqueta` en clubes, etapas de
  entrenador y jugadores del Atlas, y `meta.estilos_unificados`; los campos VaDE no cambian.
- `bbfit/__main__.py`: orden `estilos`.

Detalle, resultados y riesgos: `docs/checkpoints/F6.md`.

## 2026-10-23 — Fases 3, 4 y 5: roles por minutos, reemplazo de rol y entropía (`bbfit`)

Añadido
- `python -m bbfit roles|reemplazo|entropia` (`bbfit/__main__.py`); cada ejecución queda registrada en MLflow
  (`bbfit.registro`, almacén local `experimentos/`, no versionado). Umbrales y pesos en `configs/roles.yaml`,
  `configs/reemplazo.yaml` y `configs/entropia.yaml`.
- Fase 3 (`bbfit/roles.py`, `bbfit/cambios.py`, `bbfit/datos.py`): tabla partido × jugador desde los tramos y tiros
  (`data/modelos/roles/partidos_jugador/<t>.csv.gz`, con ausencias), respaldo de caja donde no hay jugada a jugada,
  roles RESIDUAL/PROFUNDIDAD/ROTACIÓN/TITULAR/GO-TO-GUY por MIN% (40'/48'), GTI, vector de rol Dirichlet para
  muestras < 5 partidos, H_rol, cambios de rol con detección bayesiana en línea (BOCPD propio) y covariables
  (entrenador, vacío de rol, fichaje, rendimiento reciente). Salidas `player_role_spells.csv.gz`,
  `player_role_season.csv.gz`, `team_role_structure.csv` y validación.
- Fase 4 (`bbfit/reemplazo.py`): producción por rol y proyección condicionada al rol de destino; elasticidad
  uso-eficiencia con variable instrumental (vacío de rol del partido) y agrupamiento parcial por pos3; redistribución
  de suma fija; libro de minutos por rol entre temporadas (identidad exacta) con tasa de relleno, transiciones de
  rol, asociación con el cambio de Net (bootstrap, no causal); calidad de compañeros; tendencias de entrenador y
  `asignar_minutos` (Plackett-Luce con restricciones) para el simulador. Salidas en `data/modelos/reemplazo/`.
- Fase 5 (`bbfit/entropia.py`): H_estilo (zonas de tiro + acciones de caja, Dirichlet con intervalo), H_rol
  posterior, volatilidad intrínseca σ_i (residuo sin contexto, varianza por exposición, contracción jerárquica de
  log σ²) y entropía de equipo (uso, tiros, minutos, red de pases). Salidas en `data/modelos/entropia/`.
- Tests sintéticos `tests/test_roles.py`, `tests/test_reemplazo.py`, `tests/test_entropia.py` (29).

Cambiado
- `bbfit/registro.py`: permite el almacén de ficheros de MLflow 3 (`MLFLOW_ALLOW_FILE_STORE`).
- `.gitignore`: caché `data/modelos/roles/_cache/`.

Detalle, resultados y riesgos: `docs/checkpoints/F3.md`, `F4.md`, `F5.md`.

## 2026-10-23 — Fase 2: normalización con amortiguación del salto de nivel (15 ligas)

Añadido
- `bbmodel/amortiguacion.py` y `python -m bbmodel amortiguar [--validar --variante V | --elegir | --diagnostico P]`;
  configuración en `configs/normalization.yaml`. Nivel por competición-temporada encadenado por un grafo de puentes
  (mínimos cuadrados: suma de varianzas en serie, precisión inversa en paralelo), contracción bayesiana por escalón con
  la media del escalón como nodo latente (τ por EM), mapeo monótono por liga y métrica (isotónica + PCHIP), λ(d)
  elegida por error dejando fuera una liga, pesos de probabilidad inversa para la selección de los puentes, exposición
  en posesiones (40'/48'). Salidas en `data/modelos/normalizacion_amortiguada/` (`league_offsets.csv`, traducciones,
  diagnóstico antes, validación temporal y dejando fuera una liga, ejemplos de puentes reales).
- Dataset normalizado: columnas `<m>_A_am`, `<m>_am`, `<m>_am_lo/_hi`, `<m>_am_pctel` (las anteriores no cambian). L,
  contexto y escalas ±100 leen `<m>_am` (`usar_amortiguado`).
- `identidad.unir_crosswalk`: los modelos A/B usan también las uniones automáticas del crosswalk (umbral 0,75,
  decisión del usuario).
- Tests sintéticos `tests/test_normalization.py` (12).

Cambiado
- Primera, Segunda y Tercera FEB en las listas de ligas de `bbmodel` y `bbestilo`; pista, A, B, contexto,
  interacciones, escalas y `bbfit reemplazo` reajustados con las 15 ligas (VaDE no).
- Variante por defecto `sin_mapeo` (elegida con el corte 2023-24 → 2024-25): empata con el A lineal en MAE (1,006 y
  1,000) y mejora la cobertura del 80 % (0,829 → 0,841).
- Documentación: `docs/normalizacion_amortiguada.md` (nuevo); `algoritmo_A.md`, `algoritmo_B.md`,
  `datos_normalizados.md` sin las cifras de «8 ligas»; tabla §4 de `estilos_de_juego.md` con la numeración de
  `config/estilos.json`.

Corregido
- `suerte.py`: σ² no identificado (pendiente ≤ 0 de la recta varianza–exposición) → mediana de las demás ligas.
  Hallazgo 7 de la auditoría: pts/100 en la BCL tenía σ² = 1,8·10⁻⁴; afectaba también a NBA, FEC y Segunda FEB.

Detalle, resultados y riesgos: `docs/checkpoints/F2.md`.

## 2026-10-22 — Fase 1: competiciones FEB (Primera, Segunda y Tercera FEB)

Añadido
- Tres ligas nuevas en el mismo esquema y tubería: `feb1` (Primera FEB / LEB Oro), `feb2` (Segunda FEB / LEB Plata)
  y `feb3` (Tercera FEB / Liga EBA): Primera FEB 2022-23 a 2026-27, Segunda y Tercera 2023-24 a 2026-27 (alcance
  decidido por el usuario; `temporada_inicial` por liga en config). Grupo = atributo del partido.
  `config/competition_aliases.json` con los nombres históricos por temporada.
- Adaptador `bbstats/adapters/feb.py` (calendario por postback de baloncestoenvivo.feb.es, KeyFacts/BoxScore de
  intrafeb.feb.es con el token anónimo de la página pública, plantillas y entrenador de Equipo.aspx). Bruto incremental.
- Fuente de jugada a jugada `feb` (`bbstats/lineups/sources/feb.py`): formato estructurado (2024-25+, con
  coordenadas) y formato texto (hasta 2023-24, nombres emparejados con el boxscore).
- `bbstats/lineups/possessions.py`: posesiones reales evento a evento (`possession_id`), genérico para todas las ligas.
- `bbstats/contrato.py` y `python -m bbstats contrato --ligas feb1 feb2 feb3`; `python -m bbstats feb` (partidos con
  grupo, `feb_cobertura.csv`, `feb_posesiones.csv`, `feb_sesgo_registro.csv`).
- `bbmodel/crosswalk.py` y `python -m bbmodel crosswalk`: `player_id_crosswalk.csv` (confianza y método) y
  `crosswalk_revision.csv` (casos dudosos, no aplicados). Umbrales en `config/sources.json → identidad`.
- Entrenadores FEB (uno por equipo y temporada, de la página del equipo) en `bbstats/entrenadores.py`.
- Sistemas de coordenadas FEB en `bbmodel/zonas.py` (calibrados: 99,1-99,3 % de acierto 2/3).
- Tests `tests/test_contract_feb.py` (datos sintéticos).

Cambiado
- `bbstats/http.py`: la pausa por dominio es común a todos los clientes del proceso (antes, por cliente), para que
  varias ligas del mismo dominio en paralelo respeten la cortesía.
- `bbmodel/identidad.py`: las FEB cuentan como ligas nacionales (pueden coincidir con copas europeas).

Detalle, resultados y riesgos: `docs/checkpoints/F1.md`.
