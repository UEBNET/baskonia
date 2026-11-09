# F0 · Descubrimiento y auditoría del repositorio (encargo v5.0)

Fecha: 09-11-2026 · Kerno Analytics · normalización cruzada v5.0
Base auditada: commit `7181094` (rama `claude/encargo-v41-ecosistema` = `claude/jolly-thompson-qczxl4`), que contiene
todo el trabajo vigente. Rama de trabajo de esta sesión: `claude/sweet-turing-5ti6hi` (avance rápido a `7181094`, sin
commits propios destruidos). Etiquetas: **DATO** (verificado, con fuente), **LECTURA**, **SUPUESTO**, **RIESGO**,
**VERIFICAR**. No se ha escrito ningún modelo ni se ha modificado nada existente.

---

## Informe de auditoría · Fase F0 · Descubrimiento

### Resumen ejecutivo

1. **La línea base no está en `main`.** `main` (`150e814`, 29-10) no contiene la v3.2, el simulador v3.3, la v4.0, la
   v4.1 ni la v4.2. Todo eso vive en `claude/encargo-v41-ecosistema`, 352 commits por delante de `main` y que contiene
   a todas las demás ramas salvo tres de documentación y datos ya fusionados. La v5 debe partir de ahí (pregunta 1).
2. **Hay una tercera línea base que el encargo no nombra: la v4.2 D1** (9-11-2026). Ya hace *pooling* temporal (filtro de
   Kalman sobre la v3.2) en 12 de 30 métricas, y midió que los rangos de una temporada de la v3.2 son **entre 2 y 5 veces
   más anchos** de lo que justifican los datos (c ≈ 0,2–0,5). La F4 de la v5 compite con ella, no sólo con la v3.2.
3. **El producto publica un intervalo de nivel, pero lo examina y lo describe como predictivo.** El rango que ve el
   usuario es de capacidad (sin ruido de temporada ni recalibración conforme). Los exámenes de la v3.2 y de la D1 miden
   la cobertura de una predictiva de t+1. Y el texto de la página dice «en 8 de cada 10 casos el valor real cae dentro».
   La hipótesis (e) del encargo se confirma en parte, pero al revés de lo esperado: el objeto publicado ya es de nivel. Lo
   que falla es su calibración y su etiqueta. F1 lo medirá.
4. **Los puentes intra-temporada existen y nadie los usa como tales.** La tabla jugador-partido
   (`data/modelos/roles/partidos_jugador/`) tiene fecha y competición: unas 430 personas por temporada juegan ≥ 150
   minutos en una competición europea y en su liga doméstica a la vez. Todos los modelos actuales agregan por
   persona-liga-temporada y tratan igual el puente intra que el traspaso.
5. **Bloqueos.** Hay errores de identidad confirmados que afectan a puentes europeos, no existe una tabla club → liga
   doméstica y la caja por partido está incompleta (faltan rebotes, pérdidas, robos, tapones y faltas). Detalle en §9.

---

## 1. Inventario del repositorio

### 1.1 Ramas [DATO: `git rev-list`, 09-11-2026]

| Rama | Último commit | Por delante / detrás de `main` | ¿Contenida en `encargo-v41-ecosistema`? |
|---|---|---|---|
| `main` | `150e814` 29-10 · artifact CERNO + simulador v2 (fase 8) | 0 / 0 | sí |
| **`claude/encargo-v41-ecosistema`** = `claude/jolly-thompson-qczxl4` | `7181094` 09-11 · skill «anadir-liga», v4.2 | 352 / 0 | — (es la cabeza) |
| `claude/gallant-pascal-49bx9o` | 09-11 · botón «Actualizar 2026-27» | 306 / 0 | sí |
| `claude/encargo-v4-f0-startup-zw1jvo` | 06-11 · v4.0 | 284 / 0 | sí |
| `claude/focused-dijkstra-mpqa3u` | 04-11 · química e impacto | 178 / 0 | sí |
| `claude/optimistic-pasteur-mlxi78` (PR #4, abierto) | 30-10 · v3.0/v3.1 CVAE | 33 / 0 | sí |
| `artifact-v2-candidata` | 29-10 · informe v3.3 | 4 / 0 | sí |
| `claude/informe-equipo-extras-v14` (PR #5, abierto) | 03-11 | 1 / 0 | sí |
| `datos/2026-27-actualizacion-20261029` (PR #3, abierto) | 29-10 | 3 / 0 | sí |
| `Simulación`, `claude/bold-euler-hubmhk` | 14-10 (PR #2 fusionado en `main`) | 30 / 50 | no (ya fusionadas por PR) |
| `claude/fervent-pascal-1tgdwd` | 15-10 · intranet de otro club | 7 / 50 | no (fuera de alcance) |
| `claude/new-session-vqxr82`, `docs/project-memory` | 29-10 · memoria del proyecto | 1 / 0 | no (sólo documentación) |

Sin etiquetas (la etiqueta `v2-snapshot-20261029` que pedía `docs/CHANGELOG_v3.md` nunca se pudo crear: HTTP 403).

### 1.2 Paquetes y versiones vigentes

| Pieza del encargo | Dónde está | Versión vigente en el producto | Documentación |
|---|---|---|---|
| Extracción | `bbstats/` (20 competiciones, 15 adaptadores, `lineups/` jugada a jugada) | — | `README.md`, `CONTEXTO_AGENTE.md` |
| Normalización «v1» (A+B) | `bbmodel/` (`modelo.py` A, `algoritmo_b.py` B, `amortiguacion.py` = v2 amortiguada) | base de la v3.2 y de la Landing | `docs/algoritmo_A.md`, `algoritmo_B.md`, `normalizacion_amortiguada.md` |
| Normalización v3.0 / v3.1 / **v3.2** | `bbnorm3/` (CVAE jerárquica + mezcla con la v2) | **v3.2** en 18 de 30 métricas | `docs/normalizacion_v3_cvae.md`, `_v31_combinada.md`, `_v32.md` |
| **Normalización v4.2 D1** (no citada en el encargo) | `bbequipo/v42/historial.py` | **v4.2** en 12 de 30 métricas (en el navegador) | `docs/checkpoints/V42_D1.md` |
| Simulador v3.3 | `bbfit/` (`simulador.py`, `v32.py`, `v33.py`, `b7_b9.py`) | **v3.3** (v4.2 D2 no pasó su examen) | `docs/simulador_v33.md` |
| Modelo de equipo v4.0 | `bbequipo/` (`perfiles`, `rapm`, `sinergia`, `conjunto`, `equipo`, `anclas`, `a5`) | v4.0 | `docs/modelo_equipo_v40.md`, `V40_F0…F5` |
| Ecosistema v4.1 | `bbequipo/ecosistema/` | v4.1 | `V41_F0…F4`, `docs/estado_modelos.md` |
| Artifact | `artifact/kerno/` (3 sitios: Jugadores, Equipos, Metodología), `artifact/kerno.html`, páginas antiguas `artifact/atlas/`, `mesa-multiliga.html` | Kerno Analytics | `V42_sitios.md`, `docs/ux/UX-SPEC.md` |
| Artículo científico | `cerno_articulo/` → `docs/articulo/cerno_lectura_entre_ligas_v3_2.pdf` | v3.2 | — |
| Actualización | `bbactualiza/` (botón «Actualizar 2026-27», recalibración mensual), `scripts/actualizar_v32.sh`, `.claude/skills/{actualizar-temporada, anadir-liga}` | — | `docs/actualizacion_2026-27.md` |
| `diccionario_columnas` | `data/processed/<t>/diccionario_columnas.csv` (y `.json` en `data/artifact/`, no versionado) | — | `docs/data_dictionary.md` |
| Glosario i18n | `data/modelos/v4_1/producto/i18n.json`, `docs/glosario.md` | — | — |
| Kit de gráficos `charts.py` | **no existe en el repositorio** | — | se usará matplotlib con los tokens Kerno |

Tamaño [DATO]: `data/` 3,6 GB versionados (`processed` ≈ 1,0 GB, `raw` ≈ 0,7 GB, `modelos`); `.git` 4,3 GB.

### 1.3 Tests y configuración

- **329 tests en verde** (`python -m pytest -q`, 95 s) [DATO]. Los dos fallos iniciales de `tests/test_cba.py` se debían a
  `pypinyin` sin instalar (está en `requirements.txt`); con la dependencia instalada pasan.
- Configuración: YAML por capa en `configs/` (`normalization*.yaml`, `simulation_v3*.yaml`, `equipo_v40.yaml`,
  `ecosistema_v41.yaml`, `v42.yaml`, `version.yaml`). Registro MLflow en `experimentos/` (no versionado).
- `configs/version.yaml` dice `version_activa: v1`, pero el producto usa la v3.2 por rutas explícitas en cada
  consumidor. **LECTURA:** el selector de versión está desconectado; la v5 no puede activarse sólo con él (§6).

### 1.4 Entorno de cómputo [DATO]

4 núcleos, 15 GB de RAM, Python 3.13, sin GPU. No están instalados `jax`, `numpyro`, `arviz`, `polars`, `duckdb`,
`pyarrow`, `optuna`, `statsmodels` ni `pandera` (pregunta 6).
**RIESGO:** «NUTS con 4 cadenas sin límite de coste» sobre el modelo conjunto (≈ 50.000 jugador-temporadas × 33
métricas × K factores + λ por liga-temporada-métrica) es probablemente inviable en esta máquina. El encargo lo prevé:
particionar por familia o bloque de métricas, nunca simplificar. Lo estimaré con cifras en F1 y F3.

---

## 2. Esquema de datos

### 2.1 Tablas [DATO]

| Tabla | Granularidad | Notas |
|---|---|---|
| `data/processed/<t>/ligas/<liga>.csv` | jugador-equipo-fase (`regular`, `playoffs`, `total`) | 480 columnas iguales en todas las ligas. En EuroLeague/EuroCup, el traspasado va en **una** fila con `team_id` «A;B» |
| `data/modelos/roles/partidos_jugador/<t>.csv.gz` | **jugador-partido** | `game_id`, `fecha`, `fase`, `team_id`, `opp_id`, `persona_id` (P…), segundos, posesiones en pista, +/−, pts, tiros de campo, triples y libres (intentos/aciertos), ast, asistidas, contexto de equipo en pista. **Sin** rebotes, pérdidas, robos, tapones ni faltas. Reconstruida desde el jugada a jugada |
| `data/processed/<t>/quintetos/<liga>/{tramos,tiros}.csv.gz` | tramo / tiro | Base del RAPM, on/off y zonas |
| `data/processed/<t>/entrenadores/<liga>_partidos.csv` | equipo-partido | Resultado, puntos, rival, local, fecha. Sin tabla para la NBL |
| `data/processed/<t>/feb/*` | partido / equipo (FEB) | — |
| `data/modelos/pista/` | jugador-equipo-temporada | Zonas, % asistidas, RAPM/ORAPM/DRAPM |
| Brutos `data/raw/<liga>/<t>/pbp_*.json.gz` y boxscores FIBA/ACB | partido | **Caja completa por partido** (rebotes, robos…), sin procesar a tabla |

### 2.2 Cobertura liga × temporada (fase regular; filas jugador-equipo / jugadores distintos) [DATO]

| Liga | 2020-21 | 2021-22 | 2022-23 | 2023-24 | 2024-25 | 2025-26 | 2026-27* |
|---|---|---|---|---|---|---|---|
| euroleague | 297/297 | 293/293 | 295/295 | 287/287 | 295/295 | 335/335 | 292/292 |
| eurocup | 342/342 | 311/311 | 306/306 | 307/307 | 300/300 | 315/315 | 419/419 |
| bcl | 467/459 | 465/457 | 491/483 | 479/473 | 482/479 | 493/487 | 436/436 |
| fec | 260/260 | 422/422 | 431/424 | 503/501 | 562/559 | 572/571 | 638/637 |
| acb | 365/355 | 325/317 | 330/318 | 318/311 | 328/320 | 339/334 | 263/263 |
| lba | 244/242 | 315/307 | 287/282 | 289/285 | 306/301 | 265/263 | 232/232 |
| bbl | 307/307 | 315/315 | 287/287 | 299/299 | 306/306 | 331/331 | 257/257 |
| lnb | 313/307 | 287/279 | 299/294 | 305/301 | 262/257 | 275/270 | 204/204 |
| bsl | 295/292 | — | — | — | — | 332/328 | 263/263 |
| gbl | 230/222 | 255/249 | 227/218 | 232/226 | 239/235 | 249/242 | 209/209 |
| vtb | 245/242 | 201/195 | 220/209 | 239/230 | 215/211 | 200/191 | 158/158 |
| bnxt | — | 354/351 | 354/348 | 364/363 | 360/359 | 353/350 | 199/199 |
| feb1 | — | — | 305/297 | 305/297 | 314/304 | 295/289 | 244/242 |
| feb2 | — | — | — | 482/466 | 490/473 | 466/449 | 353/353 |
| feb3 | — | — | — | 2391/2329 | 2452/2400 | 2523/2469 | 1911/1910 |
| nba | 626/540 | 715/605 | 609/539 | 657/572 | 654/569 | 661/582 | 459/459 |
| gleague | 246/246 | 493/493 | 471/471 | 512/512 | 510/510 | 526/526 | 0 |
| ncaa (top 50) | 813/810 | 809/807 | 794/784 | 803/803 | 804/804 | 766/766 | — |
| cba | 433/413 | 432/429 | 436/433 | 447/443 | 426/426 | 386/384 | 278/278 |
| nbl | 136/133 | 157/157 | 156/156 | 157/157 | 157/157 | 168/167 | 154/154 |

\* En curso a 09-11-2026. Dataset normalizado v3.2: 52.635 filas, 18.475 personas (enteras de `bbmodel`) [DATO].

**Huecos [DATO].**
- BSL 2021-22 a 2024-25 sin extraer.
- BNXT sin 2020-21; FEB desde 2022-23 (feb1) y 2023-24 (feb2 y feb3); NCAA sin 2026-27.
- La tabla jugador-partido falta en BBL 2020-23, CBA 2020-21 y 2024-25, BCL 2020-21, LNB 2020-21, VTB 2020-22 y NCAA salvo
  2025-26. La NBL no tiene fecha de partido.
- Copas nacionales: ninguna extraída (sólo el Showcase de la G League).

**Partidos con jugada a jugada en competiciones europeas [DATO]:**

| Competición | 2020-21 | 2021-22 | 2022-23 | 2023-24 | 2024-25 | 2025-26 | 2026-27 |
|---|---|---|---|---|---|---|---|
| EuroLeague | 326 | 299 | 328 | 330 | 330 | 399 | 95 |
| EuroCup | 182 | 186 | 194 | 193 | 192 | 193 | 93 |
| BCL | 0 | 162 | 167 | 172 | 177 | 175 | 48 |
| FEC | 30 | 156 | 165 | 160 | 180 | 182 | 118 |

Frecuencia de actualización: bajo demanda. Temporada en curso con el botón «Actualizar 2026-27» y recalibración
mensual (`bbactualiza/`).

---

## 3. Identificadores

### 3.1 Identificador de jugador por liga y entre ligas

- **Dentro de una liga:** `player_uid = <liga>:<player_id>`. Hay ids compartidos sólo dentro de una familia: EL ↔ EuroCup
  (329/329), BCL ↔ FEC (649/652) y FEB1/2/3.
- **BBL, BSL, GBL, BNXT:** ids inestables o construidos con el nombre (FIBA LiveStats no da id de persona).
- **Dos sistemas de persona [DATO]:**
  - `persona_id` = `P000123` del crosswalk (`data/processed/player_id_crosswalk.csv`: 30.233 registros, 20.423
    personas, umbral de fusión 0,75). Lo usan `bbfit`, `roles` y `v4_*`.
  - `persona_id` entero de `bbmodel.identidad` + uniones del crosswalk (52.392 registros, 18.964 personas, **84 ambiguas**
    sin enlazar). Lo usan `normalizado/` y `v3_*`.
- **Sin resolver [DATO]:**
  - Cola de revisión `crosswalk_revision.csv` con **4.305 parejas no aplicadas** (4.296 por confianza 0,50–0,70; 1.189
    son bbl–bbl).
  - El crosswalk no cubre el **3,1 %** de los ids de 2026-27 (es anterior a la última actualización).
  - 947 personas sólo con inicial (488 FEB, 217 CBA).
- Auditoría previa de 100 puentes: 100/100 correctos (Clopper-Pearson 0,964).

### 3.2 Errores de identidad confirmados en esta F0 [DATO, verificado en `player_id_crosswalk.csv`]

| Caso | Error | Efecto en puentes |
|---|---|---|
| `P002671` | **Fusión falsa**: Devin Booker de EuroLeague (n. 1991; también BBL y LBA) unido al de la NBA (n. 1996) | 6 falsos puentes EuroLeague–NBA de la misma temporada (2020-21 a 2025-26) en el sistema P… |
| Nikos Rogkavopoulos | **Separación indebida**: ACB+BCL = `P000686`, EL+EuroCup = `P006943`; la pareja no está en la cola de revisión | Puente intra-temporada ACB–EuroLeague perdido (Baskonia 2023-24 y 2024-25) |
| P000587, P000980, P002671, P007215, P007621 | Años de nacimiento incompatibles (> 1,5 años) dentro del grupo | VERIFICAR |
| P005521 | Sospechosa: Mike James (EL, n. 1990) unido a un registro NCAA 2025-26 | VERIFICAR |

**LECTURA.** La unión del crosswalk es transitiva y no comprueba la coherencia del año de nacimiento a nivel de grupo.
Según el encargo, «un puente mal resuelto es peor que ningún puente». La F2 debe auditar de forma dirigida todos los
puentes intra-temporada europeos, sin tocar el crosswalk vigente (capa derivada propia de la v5).

---

## 4. Normalización v3.2

### 4.1 Qué es [DATO: `docs/normalizacion_v32.md`, `configs/normalization_v32.yaml`, `bbnorm3/`]

La v3.2 **no es una CVAE sola**: es la **mezcla caso a caso** de la v2 (A+B amortiguado, `<m>_am`) y una CVAE jerárquica,
con peso 0,5 en todas las métricas salvo el RAPM (1,0).

- **Variable objetivo:** 33 métricas por jugador-liga-temporada (25 de caja y 8 de jugada a jugada), transformadas
  (`raiz`, `log1`, `proporcion` = asin√p, `id`) y estandarizadas, con el ruido de muestra σ²/n del paso 1 del algoritmo A.
- **CVAE (configuración final tras la ablación):**
  - latente K = 4;
  - sin FiLM, sin cabezal por liga, amortizada, verosimilitud normal;
  - factor propio persona × métrica ζ;
  - niveles μ_c por competición-temporada con paseo aleatorio (κ = 0,10) y jerarquía por escalón;
  - escala por liga fija (s = 1);
  - IPW de los puentes, penalización de ciclo, efecto equipo-temporada;
  - deep ensemble de 20 redes; pérdida ELBO (Adam, 2.500 pasos).
- **Gauge:** media ponderada de todas las competiciones. «Liga X = 0» es sólo presentación (`bbnorm3/destino.py`,
  `a_destino`); la covarianza de niveles se exporta para cualquier par.

### 4.2 Qué intervalo produce y cuál publica (respuesta a 5.4 del encargo, a confirmar con cifras en F1)

| Objeto | Qué incluye | Dónde |
|---|---|---|
| Intervalo del **examen** v3.2 | **Predictivo de t+1**: decodificado + ζ + efecto equipo + ψ + ruido σ²/n en destino, más **recalibración conforme** κ por métrica y grupo | `bbnorm3/prediccion.py:91-96`, `combinacion.py:169-186` |
| Intervalo **publicado** (`v3_2/normalizado`, columnas `<m>_lo`/`_hi`) | **Nivel/capacidad**: cuantiles 10–90 de la mezcla de dos normales (CVAE: decodificado + ζ, sin ψ ni ruido; v2: anchura F0). **Sin κ** (sólo el factor 1,063 de la Tercera FEB) | `bbnorm3/exportar.py:212-234`, `combinacion.py:316-322` |
| Intervalo que **ve el usuario** | El publicado (18 métricas) o la posterior de Kalman m ± z80·√P de la v4.2 (12 métricas), ensanchado con la vara de destino (`convVara`) | `artifact/kerno/index.html:651-656, 706-708, 855-863` |
| Texto en la página | «en 8 de cada 10 casos **el valor real cae dentro**» (lenguaje predictivo) | `artifact/kerno/index.html:1485` |

**LECTURA.**
- El objeto publicado es un intervalo de nivel, pero su cobertura sólo se ha medido como si fuera predictivo, y el texto
  lo vende como predictivo.
- La D1 midió que, usado como varianza de observación, el rango es entre 2 y 5 veces más ancho de lo necesario.
- Encaja con las hipótesis (f) (mala calibración) y (b) (ruido mal propagado), no con (e) tal como estaba formulada.
- La F1 debe medir las dos cosas por separado: la cobertura del intervalo de nivel frente al nivel latente (con un
  modelo de componentes de varianza) y la del predictivo frente a t+1.

**Anchura publicada frente a la dispersión entre jugadores** [DATO, 2025-26, ≥ 300 min; mediana de la anchura del 80 %
/ DT de los valores traducidos]: pts/100 5,49 / 8,19 · TS% 6,47 / 8,43 · T3% 5,62 / 5,95 · USG% 4,25 / 5,64 · AST%
5,31 / 8,02 · DREB% 3,14 / 3,95 · STL% 0,64 / 0,50 · BLK% 0,71 / 1,32 · PER 4,56 / 8,31 · RAPM 1,59 / 4,88.
**LECTURA:** en T3% y STL% el rango del 80 % de un jugador es tan ancho como toda la dispersión de la liga; ese rango no
separa jugadores.

### 4.3 Validación vigente [DATO: `docs/normalizacion_v32.md` §6]

- **Examen anidado:** cortes 2022-2024, 1.431 personas × corte, 33 métricas. Error frente a la v2 −3,2 % [−3,6; −2,8],
  cobertura 0,811.
- **Falla la cobertura** en 4 pares con ≥ 30 personas: Segunda → Tercera FEB 0,778, G League → NBA 0,857, NBA → G League
  0,855, NCAA → NBA 0,771.
- Los cortes 2023 y 2024 ya se miraron al diseñar la v3.1. El examen limpio previsto es 2025-26 → 2026-27, al acabar la
  temporada.
- **Disponibles para la F1 sin recalcular:**
  - `data/modelos/v3_2/validacion/casos_combinada_v32.csv.gz` (predicciones por caso) y
    `predicciones_cvae_<2021-2024>.csv.gz`;
  - líneas base v2 `lineas_base/sin_mapeo_<año>.csv.gz` y `b.csv.gz`;
  - `f0_<año>.csv.gz`.

## 5. Normalización v1 (A+B) y v2 amortiguada

| Pieza | Qué hace | Intervalo |
|---|---|---|
| A (`bbmodel/modelo.py`, `suerte.py`, `enlace.py`) | Paso 1: contracción por exposición (σ²/n, τ² por momentos). Paso 2: z dentro de liga×temporada×posición. Paso 3: tipo de cambio lineal m_l + s_l·z con EM sobre puentes y deriva por edad. Paso 4: traducción a la vara EuroLeague 2025-26 | **Credibilidad de la capacidad** (varianza posterior de z + incertidumbre de m y s por bootstrap de 20 réplicas). Se examinó contra t+1 y cubrió entre el 80 % y el 89 % |
| B (`algoritmo_b.py`) | Red multitarea («ADN» de 8 números, 5 redes) | 80 % |
| v2 amortiguada (`amortiguacion.py`) | Grafo de puentes por competición-temporada, contracción por escalón, mapeo monótono, λ(d), IPW | 80 %; F0 con la covarianza completa del grafo |

Validación de la v1 [DATO: `docs/algoritmo_A.md` §4]: 412 cambios de liga (8 ligas). Mejora frente a «mismo percentil»
en las 25 métricas; cobertura del 80 % entre el 80 % y el 89 %.

## 6. Contrato con los consumidores (lo que la v5 debe poder alimentar en F9–F10)

**Ningún consumidor lee draws.** Todos reconstruyen una normal en la escala de trabajo T a partir de (centro, q10, q90)
o de (θ, sd, v_j), con z80 = 1,2816 [DATO].

| Consumidor | Lee | Columnas | ¿Punto o distribución? |
|---|---|---|---|
| Simulador v3.3 (y v3.2, v4.0) | `v3_2/normalizado/*.csv.gz` (+ feb3 de `v3_1_20261031/base_v2`) y `v3_2/destino/covarianza/<m>.json` | `<m>_am`, `_am_lo`, `_am_hi`, `_v31_peso_cvae`, `pos3`, `min`; `cov_triangular`, `sd_par_triangular` | θ con sd sacada del intervalo; Monte Carlo propio con **z1 común a todas las métricas** (correlación perfecta) |
| Examen sin fuga del simulador (`V32_corte`) | Redes CVAE ≤ t y cachés de `experimentos/` | `_v3`, `_v3_lo`, `_v3_hi`, `_th`, `_thsd` | Ídem |
| Perfiles v4.0 (prior del RAPM, sinergia, conjunto) | `v3_2/destino/capacidad/<t>.csv.gz` | `<m>_th`, `<m>_vj` (16 rasgos) | Media + varianza; el RAPM usa **sólo la media** |
| Nivel Kerno NK₁/NK₂ (`bbequipo/anclas.py`) | Indirecto: cuantiles predictivos del simulador `v_C_{lo90…hi90}`, más una referencia empírica liga destino × puesto (3 temporadas, `roles/player_role_season`) | — | 400 muestras reconstruidas de cuantiles |
| IMPACTO v4.0, Impacto en pista v4.1 | Indirecto (motor de minutos, perfiles puntuales) | — | Punto |
| Landing | `adaptacion/v3_1/adaptation_priors.csv`; la adaptación sale de la **v2 amortiguada** (`<m>_am_a`, `_am_sd`), no de la v3.2 | — | Media ± z80·sd por grupo |
| v4.2 D1 (Kalman) | `v3_2/normalizado` (`<m>`, `_lo`, `_hi`) | La varianza de observación sale del intervalo publicado × c | Media + varianza |
| Artifact (Jugadores) | `datos/normalizados/<t>/regular.json`, `datos/normalizados/vara.json`, `atlas/v42/historial/<t>.json.gz.txt`, `atlas/simulador/*.json` | Esquema v1 (`<m>`, `_lo`, `_hi`, `_pctel`) | Punto + rango |

**Límites del artifact [DATO: `V42_sitios.md`, `bbactualiza/sitios.py`].**
- 256 MiB y 511 ficheros por versión; 64 MB y 255 ficheros por publicación.
- El artifact único ya superó el límite y se partió en 3 sitios (Jugadores ≈ 156 MiB).
- Formato `.gz.txt` (gzip en base64), 4 cifras significativas, filas con ≥ 100 min.
- **LECTURA:** publicar 500 draws por jugador-métrica en el artifact es inviable (≈ 45 M de cifras por temporada). Los
  draws de F9 tendrán que quedarse en `data/v5/` para el simulador en Python. Al navegador irán media, sd y covarianza.

**Procesos de actualización.**
- Cadena completa: `scripts/actualizar_v32.sh`.
- Temporada en curso: botón («Actualizar 2026-27»: CVAE congelada + v2 al día, sólo escribe `v3_2/normalizado/2026-27`).
- Recalibración mensual.
- **Ni el botón ni la recalibración regeneran** `destino/capacidad`, `constantes`, `covarianza`, `vara.json` ni el
  historial v4.2 [DATO]. La v5 deberá tener un proceso paralelo que se aplique sólo a la temporada en curso, con el
  histórico idéntico byte a byte.

### 6.1 Defecto encontrado en producción (fuera del alcance de la v5; requiere decisión)

**RIESGO alto · DATO.** `bbnorm3/destino.py:169-171` escribe `sd_par_triangular` en el orden de `np.tril_indices`, y
`destino.py:324` (`vara_artifact`) lo lee con `np.triu_indices`. Las DT de nivel por par que el artifact usa para
ensanchar el rango cuando la vara no es la EuroLeague quedan desordenadas.

- Ejemplo con pts/100: el par ACB 2025-26 → EuroLeague vale 0,0504 con la lectura correcta y 0,1343 con la actual; la
  diagonal ACB → ACB sale 0,1427 cuando debería ser 0.
- El centro no cambia; afecta al rango.
- Como el artifact usa por defecto **la liga del club como vara**, afecta a los rangos que se ven por defecto.
- `tests/test_v32.py:138` no lo detecta.
- El simulador en Python lee bien (`sim_insumos.py:127-162`).

El arreglo es de una línea, pero toca la v3.2 publicada (principio 1): **no lo he tocado**. Pregunta 8.

### 6.2 Otros hallazgos de contrato

- **La resta v_j = max(sd² − Var δ_o, 0,1·sd²)** se repite en 6 sitios: Python y JavaScript.
- **El motor JavaScript del Atlas suma varianzas** frente a la EuroLeague, en vez de usar v_j y la covarianza del par
  (`simulador.js:72-79`).
- **Cachés de `experimentos/` por nombre, no por versión:** riesgo de leer datos viejos al cambiar de normalización.
- **Excepciones heredadas:** la Tercera FEB se toma de la v2 en el simulador, con factor de intervalo 1,063. La Landing
  y los estilos y niveles del Atlas siguen sobre la v1/v2.

## 7. Nivel Kerno, Impacto y Landing (contrato para F10)

- **NK₁ / NK₂ [DATO: `bbequipo/anclas.py`; en código `nivel_cerno`, `NC1`, `NC2`]:**
  - Fórmula: NK = 100·E_pred[F_ref(C)], con C = (min/partido ÷ minutos de partido) × pts/100.
  - F_ref: distribución empírica ponderada por minutos de la C realizada, por **liga destino × pos3** en las 3 últimas
    temporadas ≤ t (≥ 100 min).
  - Rango: F_ref(q10)–F_ref(q90) de la predictiva del simulador, con calibración isotónica por cortes.
  - NK₂ = variante `sin_adaptacion`.
  - **No lee la normalización directamente:** sólo pts/100 traducido (vía simulador) y minutos.
  - Examen: separación 70,9 %, cobertura 0,782.
- **IMPACTO v4.0:** Δ̂Net de la capa 4 frente a F_mov. Spearman con el on/off 0,149, cobertura 0,787.
- **Impacto en pista v4.1:** experimental, no pasa (0,081 frente a 0,149).
- **Landing:** escalón NK₁ − NK₂ por grupo de traspaso con la adaptación v3.1 (decisión del CEO 09-11); la adaptación se
  estima sobre la v2 amortiguada. Sello BAJA.

## 8. Competiciones europeas y puentes

**DATO.**
- **Jugador-partido:** EuroLeague, EuroCup, BCL y FEC tienen tabla jugador-partido con fecha (tabla de §2.2).
- **Fases:** regular y playoffs separadas; la Final Four no se distingue de los playoffs, y la sede neutral no está
  marcada.
- **Club europeo ↔ club doméstico:** coherencia por `team_id` dentro de cada competición, pero **no existe tabla de
  correspondencia** (`config/clubes.json` sólo tiene a Baskonia: `euroleague:BAS` ↔ `acb:3`).
- **Correspondencia heurística (≥ 3 jugadores comunes):** se emparejan 12 de 18 equipos EuroLeague en 2024-25. Sin
  liga doméstica en el dataset: Efes y Fenerbahçe (BSL 2021-25), Žalgiris (LKL), Partizan y Crvena Zvezda (ABA),
  Maccabi (Israel).
- **Puentes intra-temporada** (personas con partidos en la regular de dos competiciones la misma temporada; entre
  paréntesis, ≥ 150 min en ambas):
  - europea–doméstica: 286 (160) en 2020-21 · 558 (300) · 564 (297) · 634 (326) · 680 (361) · **849 (429)** en 2025-26;
  - NBA–G League: 29–63 con ≥ 150 min;
  - doméstica–doméstica: 9–43.
  - 2024-25 con ≥ 150 min: acb–euroleague 35, euroleague–lnb 35, acb–bcl 34, acb–eurocup 28.
- **Cómo los usan hoy los modelos:** A, la v2 amortiguada y la CVAE agregan por persona-liga-temporada y tratan el puente
  de la misma temporada (Δ = 0) como observación de la misma θ. **Ninguno usa la exposición por competición, el rol o los
  minutos por competición ni la calidad de rival.** Es la palanca principal de la v5 (F2.4, F6 paso 1).
- **Enfrentamientos europeos** (`entrenadores/{euroleague,eurocup,bcl,fec}_partidos.csv`): 683–943 partidos por
  temporada con resultado y margen. Con la correspondencia heurística, entre el 17 % y el 70 % enfrentan a dos equipos de
  ligas domésticas cubiertas (EuroLeague 2024-25: 126 de 330).

---

## 9. Dependencias bloqueantes

| # | Dependencia | Afecta a | ¿Se resuelve con capa derivada (sin tocar el pipeline)? |
|---|---|---|---|
| D1 | **Caja jugador-partido incompleta**: sin rebotes, pérdidas, robos, tapones ni faltas en `partidos_jugador` | Puentes intra con exposición por familia (F2.4) para rebote, defensa y TOV | **Sí, en parte**: los brutos ya traen la caja por partido (EL/EuroCup `pbp_*`, FIBA, ACB). Propongo una capa derivada v5 que la lea de los brutos sin modificar `bbstats`. VERIFICAR la cobertura liga a liga en F2 |
| D2 | **Tabla club europeo → liga doméstica** inexistente | Puentes intra (emparejar equipo) y Bradley–Terry (F2.6) | Sí: tabla derivada heurística (≥ 3 jugadores comunes) + revisión manual en una tabla corregible por el usuario |
| D3 | **Errores de identidad** en puentes europeos (Booker, Rogkavopoulos, 5 grupos con nacimientos incompatibles) y crosswalk sin cubrir el 3,1 % de 2026-27 | Todos los puentes | Sí: resolución propia de la v5 con control de coherencia de grupo y revisión manual (F2.3). El crosswalk vigente no se toca |
| D4 | **Ligas domésticas de clubes europeos no extraídas** (ABA, Israel, LKL, PLK…) y **BSL 2021-22 a 2024-25** | Grafo de ligas y Bradley–Terry | **No**: requiere ampliar la extracción (principio 6). Se dejará como propuesta priorizada en F6 |
| D5 | Huecos de la tabla jugador-partido (BBL 2020-23, CBA 2020-21 y 2024-25, BCL 2020-21, LNB 2020-21, VTB 2020-22, NCAA salvo 2025-26; NBL sin fecha) | Puentes con exposición por partido en esas ligas-temporada | Parcial: se usan los agregados de temporada para esas ligas |
| D6 | Fecha de nacimiento ausente en ACB, BBL, BCL, FEC, BNXT, BSL, GBL, LBA, NBL y NCAA (en el crosswalk sólo el 46 % de las personas tiene año) | Curvas de edad (F4), modelo de selección (F7) | Parcial: se hereda por persona; el resto queda sin edad (marcado) |
| D7 | Sede neutral y Final Four sin marcar | Bradley–Terry (ventaja de campo) | Parcial: inferible por fechas y fase |
| D8 | Copas nacionales no extraídas | Puentes adicionales (pregunta 3) | No (pipeline) |
| D9 | `jax`, `numpyro`, `arviz` y otras dependencias no instaladas; 4 núcleos | F3–F8 | Instalación (pregunta 6) |

---

## 10. Supuestos (SUPUESTO)

1. **La v5 parte de `7181094` y no de `main`.** Se comprueba con la respuesta a la pregunta 1. Si se parte de `main`, la
   v5 no podría compararse con la v3.2/v4.2 publicadas ni alimentar sus consumidores.
2. **La línea base de comparación en F1 y F8 es triple:** v1 (A+B / v2 amortiguada), v3.2 y v4.2 D1 (en sus 12 métricas).
   Si el usuario sólo quiere v1 y v3.2, la F4 podría «ganar» por una mejora que ya existe en el producto.
3. **Las predicciones del examen v3.2 guardadas en el repositorio son las del procedimiento publicado.** Se comprobará en
   F1 reproduciendo dos métricas.
4. **Que la tabla jugador-partido reconstruida desde el jugada a jugada es fiable para la exposición por competición.**
   Su validación de minutos y +/- frente al boxscore oficial está en `quintetos/<liga>/validacion.csv` (91–100 % de
   partidos válidos). Se verificará en F2.

## 11. Riesgos y verificaciones pendientes (RIESGO · VERIFICAR)

- **RIESGO (cómputo).** NUTS conjunto sobre todas las métricas puede no caber en 4 núcleos y 15 GB. Habrá que bloquear por
  familia, con el coste documentado en F1/F3.
- **RIESGO (producto).** El intervalo mostrado está mal etiquetado (nivel presentado como predictivo) y, con vara ≠
  EuroLeague, mal calculado (`triu`/`tril`).
- **RIESGO (examen).** Los cortes 2023 y 2024 ya se usaron para diseñar la v3.1/v3.2, y la D1 usó 2022-2024. Cualquier
  examen de la v5 en esos cortes compite contra modelos ajustados mirándolos. El único corte limpio es 2025-26 → 2026-27
  (en curso).
- **VERIFICAR.** Cobertura de la caja por partido en los brutos de cada liga (D1); casos de identidad sospechosos (§3.2).

## 12. Diagnósticos de inferencia

No aplica (F0 no ajusta modelos).

## 13. Verificación de no regresión (línea base)

**Hashes de árbol Git** en `7181094` de las salidas que la v5 no debe cambiar [DATO]. Se recomprobarán en cada fase.

| Ruta | Hash del árbol | Ficheros |
|---|---|---|
| `data/modelos/algoritmo_A` | `f51477ee7e152c266378d8a970f2500d77b8ed36` | 11 |
| `data/modelos/algoritmo_B` | `ded2e426019646688f9300a8ebae8b1376625fca` | 11 |
| `data/modelos/normalizacion_amortiguada` | `f4028604f4d00e3bb662885a2ede7bf96ddb1eb2` | 30 |
| `data/modelos/normalizado` | `2417f6d377801eabd44c57e7641080d046b9c917` | 7 |
| `data/modelos/v3_2` | `0288df4566a8f25c023a999a1c55c1ef06c51379` | 182 |
| `data/modelos/v4_0` | `c0e54fb49c210155768bea9fd57f1bfae8ca90d3` | 114 |
| `data/modelos/v4_1` | `2c31a7fa5169469591c80f07431591d2f5d16c72` | 68 |
| `data/modelos/v4_2` | `ed6bdc7ac998e2baa294ffefbff9e68502dc0e69` | 27 |
| `data/modelos/simulador` | `62d2e78a22533e929e7ea0bf322640bceb330767` | 147 |
| `data/modelos/adaptacion` | `8f05b0732eae9d22d84b9241cf44e5f33e3774e8` | 23 |

- Tests: 329 en verde.
- Procesos de actualización: no tocados.
- Único cambio en el repositorio: `docs/v5/` (este documento y el mapa de nomenclatura).

## 14. Decisiones baratas tomadas (reversibles) y declaradas

1. **Rama.** Trabajo en `claude/sweet-turing-5ti6hi` (la rama asignada a esta sesión), avanzada a `7181094`. El encargo
   pedía `feature/v5.0-normalizacion-cruzada` desde `main`: ver pregunta 1.
2. **Ubicación del código.** Propongo `bbnorm5/` en la raíz, con las subcarpetas del encargo (`datos/`, `medida/`,
   `carrera/`, `latente/`, `ligas/`, `validacion/`, `salida/`, `diagnostico/`, `config/`). Es la convención del
   repositorio (`bbmodel`, `bbnorm3`, `bbequipo`): no hay `src/`. Orden de ejecución:
   `python -m bbnorm5.<fase> --config configs/v5/<fase>.yaml`.
   - Datos en `data/v5/…`, tests en `tests/normalizacion_v5/`, documentación en `docs/v5/`.
   - Si prefiere literalmente `src/normalizacion_v5/`, se cambia sin coste ahora.
3. **Gráficos.** Matplotlib con los tokens Kerno (no hay `charts.py` en el repositorio).

## 15. Siguiente fase propuesta y ajuste de inversión

**F1 · Auditoría de varianza y calibración** de la v1, la v3.2 y la v4.2 D1:

- **Componentes de varianza y fiabilidad.** REML por métrica sobre las tablas por jugador-liga-temporada, con los puntos
  de estabilización por dos métodos (división de muestra y componentes de varianza). La división de muestra se hará con
  la tabla jugador-partido (partidos pares e impares) donde exista.
- **Cobertura, PIT y CRPS** del objeto **publicado** (nivel) y del **examinado** (predictivo) por separado, reutilizando
  `casos_combinada_v32.csv.gz` y las líneas base guardadas.
- **Cuánto más estrecho sería un intervalo de nivel bien calibrado.**

Inversión provisional (se ajusta con los números de F1):
- F2.4 (puentes intra) y F3 (verosimilitudes con exposición real) parecen las palancas mayores.
- F4 debe justificar su valor frente a la D1, que ya existe.

Esperando GO (y respuestas a las preguntas del final del informe en el chat).
