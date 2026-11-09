# Registro de cambios

## 2026-11-09 — CERNO v4.1 · F2 Impacto en pista y candidatos de química (puerta pendiente del CEO)

Detalle: `docs/checkpoints/V41_F2.md`. Puerta F1 aprobada el 08-11-2026 (E1, E2 y E5); F2-a con la opción (a).

* **Impacto en pista** (`bbequipo/ecosistema/impacto_pista.py`, `examen_impacto.py`).
  * Definición: v_j = β + h + Σ π φ → percentil esperado del grupo de liga → isotónica con los cortes anteriores.
  * Los cuatro cortes se calcularon sin fuga.
  * **Examen §6.2** (las 3.598 filas del IMPACTO v4.0):
    * monotonía 0,081 frente a 0,149: no cumple la no inferioridad;
    * frente al aditivo +0,050 [0,024; 0,077];
    * calibración ±5,0 y cobertura 0,792.
    * **Regla F2-a aplicada:** el IMPACTO v4.0 sigue como ancla; el Impacto en pista queda EXPERIMENTAL.
  * Contextualidad −0,003 [−0,039; 0,033]: el cambio por altas y bajas lleva sello BAJA.
* **Candidatos:**
  * contexto c_j: entra por la regla literal (+0,080); [POST HOC] es la mecánica del on/off (frente al β RAPM de t+1 cae
    de 0,58 a 0,13): propuesta de no adoptarlo;
  * familiaridad (`familiaridad.py`): δ +0,38 [0,35; 0,41], pero no mejora la monotonía. [POST HOC] El placebo de
    familiaridad futura da +0,47 y sin contracción δ ≈ 0: es selección.
* **F2-d:** campos `net_off`, `xnet_off`, `net_onoff` y `xnet_onoff` en la capa XP (41 activos).
* **F2-b:** NC₁/NC₂ por escenario e Impacto en pista antes/después en `Ecosistema.simular`.
* **Opción (a):** regeneradas en `experimentos/` (no versionado) las cachés ≤ t de los cortes 2021–2024: el A, 80 redes
  CVAE v3.2, la normalización «V32_corte» y los pesos del motor.
* CLI: `impacto-pista`, `familiaridad`, `xp-onoff`. 7 tests nuevos (33 en `tests/test_ecosistema_v41.py`).

## 2026-11-07 — CERNO v4.1 · F1 Motor de escenarios (puerta pendiente del CEO)

Detalle: `docs/checkpoints/V41_F1.md`.

* **Motor de escenarios** (`bbequipo/ecosistema/escenarios.py`), con la API del encargo
  `simular(R, altas=[(id, rol)], bajas=[id])`.
  * Minutos del motor v3.3 con el rol fijado de las altas (`forzar_roles`), recorte y Σ exacta (P5).
  * Uso con suma fija al 100 % y Net de la capa 4 calibrado, con su descomposición: valor directo, minutos desplazados,
    φ, h, regresión a la media y reparto ataque/defensa experimental.
  * Impacto cruzado F2-B por compañero, Shapley exacto (≤ 4 movimientos) o por permutaciones, química entre altas y
    Valor de baja. Ninguna capa cerrada se modifica.
* **Rangos de minutos recalibrados** (P5, `minutos_cal.py`): cobertura del 80 % entre 0,785 y 0,800 y del 90 % entre
  0,881 y 0,890 en cada corte de decisión. El motor sin recalibrar cubría 0,92 / 0,96.
* **Examen §6.1** (`examen_escenarios.py`; 118 equipos reales, 472 escenarios):
  * restricciones físicas en el 100 %;
  * Shapley = Δ a 10⁻¹⁴;
  * paridad con la capa 4 exacta en 117 de 118. El restante difiere en 0,012 por la corrección P5 de un fallo físico
    del motor v3.3; sin P5, exacta en los 118.
* CLI: `escenario`, `escenarios-examen`, `minutos-calibrar`. 5 tests nuevos (26 en `tests/test_ecosistema_v41.py`).
* Regenerados en `experimentos/` (no versionado) el ajuste producto F1 de la v4.0 (reproduce los β publicados al
  0,00005) y el dataset del simulador.

## 2026-11-07 — CERNO v4.1 · puerta F0 APROBADA por el CEO

* Decisiones A, B, C y D (`docs/checkpoints/V41_F0.md` §9.1):
  * A: puerta F0 aprobada y arranque de la F1 (motor de escenarios).
  * B: F3-T cerrada sin ejecutar; el motor queda en orden 2.
  * C: subpaquete `bbequipo/ecosistema/` aprobado.
  * D: rama `claude/encargo-v41-ecosistema` creada.

## 2026-11-07 — CERNO v4.1 · F0: mejoras del procedimiento (capa XP, efecto mínimo detectable, entorno)

Aprobadas por el CEO (propuestas 1 y 2, y el cambio de entorno). Detalle: `docs/checkpoints/V41_F0.md` §11.

* **Capa XP · punto esperado por tiro** (`bbequipo/ecosistema/puntos_esperados.py`, `docs/puntos_esperados.md`).
  * Modelo xp1: acierto por zona × liga-temporada, contraído hacia su tipo; TL del tirador contraído.
  * Granos tiro → tramo → jugador, con un **catálogo ampliable** en `configs/ecosistema_v41.yaml → puntos_esperados.catalogo`:
    37 campos activos y 6 propuestos, registrados con `@campo`. Un test exige que catálogo y código coincidan.
  * 115 ligas-temporada; tramos con los puntos reconstruidos exactos desde los tiros ≥ 99,6 %.
* **Prueba de beneficio prerregistrada** (`beneficio_xp.py`).
  * Sólo el punto esperado empeora la predicción del marcador real.
  * La mezcla 0,75·real + 0,25·esperado la mejora (R² +0,0004, IC95 > 0, en el global y en el segmento élite) y queda
    adoptada por regla para los modelos nuevos de la capa E.
* **Efecto mínimo detectable obligatorio** (`potencia.py`, `configs → potencia`).
  * Primera aplicación, la puerta F3-T: incluso en versión optimista, la sinergia de trío por perfiles no se detecta
    por debajo de ≈ 2 pts/100 (potencia 0 hasta 1 pt/100; 0,55 a 2), frente al 0,10 que exige la puerta.
  * El criterio «DT ≥ 0,10» lo cumple el ruido (DT ≈ 0,83 sin sembrar nada).
  * Propuesta: cerrar la F3-T.
* **Entorno personal «baskonia (modelado)»**: dependencias, PyTorch CPU y caché al arrancar. CHOLMOD se descartó tras
  medirlo: es más lento que la Cholesky densa en este problema.
* CLI: `puntos-esperados`, `beneficio-xp`, `potencia-trios`. 5 tests nuevos (21 en `tests/test_ecosistema_v41.py`).

## 2026-11-06 (tarde) — CERNO v4.1 · F0: decisiones del CEO y modelo mixto de sinergias

* **Decisiones del CEO aplicadas y criterios congelados** (`configs/ecosistema_v41.yaml → criterios.estado:
  congelado_06-11-2026`):
  * P1: rotación ≥ 7,5 % de los minutos del equipo.
  * P2: ausencia y decisión técnica no se separan.
  * P3: bancos V-AUS (17.061 partidos con un único ausente; 2.462 en élite) y V-AUS-M (4.693).
  * P4: contraparte del Impacto en pista = on/off ajustado bruto.
  * P5, con workaround: la capa E recorta y recalibra sus propios rangos de minutos sin tocar el motor v3.3.
* **Modelo mixto REML** (`bbequipo/ecosistema/sinergia_mixta.py`): jugadores y unidades estimados a la vez, con intervalos
  de perfil y de bootstrap y contraste en la frontera.
  * La calibración plantada sobre datos reales reveló que el modelo de ruido de la v4.0 (σ²/posesiones, tramos
    independientes) sesgaba la química hacia 0. Se añade un modelo de ruido ampliado: estado del marcador y varianza
    1/n + c/n².
  * Resultado: σ̂ = 0 en parejas, tríos y quintetos.
  * Ni el modelo mixto ni la prueba predictiva detectan una química de pareja sembrada de σ = 2 pts/100: la química
    propia no es medible en pista por debajo de ≈ 2–3 pts/100. La «DT ≈ 1,3» del §2.2 no está respaldada; el producto
    se apoya sólo en la química por perfiles (φ).
* `orden_sinergias.potencia_predictiva`: potencia de la prueba predictiva con química sembrada.
* 4 tests nuevos (16 en total en `tests/test_ecosistema_v41.py`).

## 2026-11-06 — CERNO v4.1 · F0 Cimientos del ecosistema del club (puerta pendiente del CEO)

Encargo `docs/encargos/v4.1_ecosistema.md` (rev. 1.0). Base: v4.0 cerrada (`6fb6abd`), verificada: `V40_F5` aprobada y
`tests/test_equipo_v40.py` en verde. Detalle: `docs/checkpoints/V41_F0.md`. La v4.1 **añade**: no se ha modificado nada de la
v3.2, la v3.3, la v4.0 ni el pipeline de extracción; Fit y ADAPT sólo se inventarían.

* **Subpaquete `bbequipo/ecosistema/`** (capa E) con su configuración única `configs/ecosistema_v41.yaml` (hiperparámetros
  F0–F4, semillas, criterios §6 transcritos para su congelación y propuestas P1–P5 sin aplicar), CLI
  `python -m bbequipo.ecosistema …`, MLflow `ecosistema_v41` y 12 tests sintéticos (`tests/test_ecosistema_v41.py`).
* **Prueba de orden de sinergias (§2.2) reproducida** (`orden_sinergias.py`; 930.185 tramos, 93 ligas-temporada) en dos
  versiones: (a) RAPM ridge y (b) β de F1. Pareja y trío del §2.2 reproducidos (1,59 y 0,97 frente a 1,66 y 0,82). Se añaden
  una calibración nula (sesgo por el error de β común a los tercios: ≈ 75 % de la varianza de pareja) y una plantada (factor de
  atenuación de la medida «propia», k ≈ 0,3), y un control de jugadores en la prueba predictiva. Con β de F1 no hay estructura
  propia de pareja ni de trío, y los efectos de unidad no mejoran la predicción. Quintetos más usados: parte propia estable no
  atribuible a química (discrepancia con el §2.2, investigada).
* **Benchmark de decisión sobre la v4.0 real** (`benchmark.py`), que sustituye al informe sobre `main`: NC (Spearman 0,454
  global, 0,367 élite; top-k; rol oráculo), IMPACTO (0,149; élite 0,159 con ventaja sobre el aditivo en el límite), ΔNet
  (MAE 4,06 / élite 3,23), límites físicos de los minutos v3.3 (1 ficha > 40'; cola superior saturada), avisos (64,5 % de las
  fichas) y backtest agregado del club cliente.
* **Auditoría de ausencias** (`ausencias.py`): el umbral literal del §5.4 deja 116 partidos (V-AUS inviable); al 7,5 %, 17.061.
  El acta no está en los datos procesados (ausencia y decisión técnica no se distinguen).
* **Inventarios** (`inventario.py`): Fit/ADAPT (453 apariciones; 89 en 5 ficheros de vista) y referencias fijas a club y
  temporada, con su propuesta.
* **`docs/estado_modelos.md`**: una ficha por salida visible (v3.3, v4.0 y v4.1) con examen, fugas, estado y sello propuesto.
* README §18, §19 y §21 actualizados.

## 2026-11-05 — CERNO v4.0 · ENCARGO CERRADO (puerta F5 aprobada por el CEO)

F0–F5 completadas con sus puertas (`docs/checkpoints/V40_F0.md` … `V40_F5.md`), modelo documentado en
`docs/modelo_equipo_v40.md`, productos en `data/modelos/v4_0/` (perfiles, contrato, rapm_multiliga, sinergia, conjunto, equipo,
equipo/a5, equipo/anclas) y `configs/simulation_v40.yaml`. Nada de la v3.2/v3.3 cambió. Pendientes fuera del encargo: integración
en el flujo del simulador v4.0 y el artifact; examen limpio 2025-26 → 2026-27 antes de comunicar cifras de acierto.

* **Informes con la v4.0 (05-11-2026, decisión del CEO)**: lectura de fichaje e informe de equipo con NIVEL CERNO e IMPACTO
  como cifras principales de 02 y 03 (hoja propia de anclas en la lectura; Net proyectado y anclas por jugador en el informe de
  equipo), vara de la liga del club de destino en toda la lectura, cálculo en el navegador (`artifact/atlas/v40.js` sobre el motor
  v3.3 del Atlas, importado del artifact publicado) con las tablas de `python -m bbequipo exportar-atlas`. Detalle:
  `docs/checkpoints/ARTIFACT-v40-informes.md`.
* **Artifacts actualizados (05-11-2026)**: nueva sección «Modelo de equipo v4.0» en la página clásica (área «Modelo v4.0»:
  resumen y puertas, Nivel Cerno e Impacto, equipos 2026-27, método y límites) y en el panel v2.0 (sección «05 · Modelo de
  equipo»). Página propia `artifact/v40/index.html` (marca Cerno, claro/oscuro, punto + rango del 80 % en toda estimación) con
  sus datos en `artifact/v40/datos/` (ver `artifact/v40/README.md`). Las lecturas vienen de los exámenes históricos y de la
  proyección de plantillas 2026-27; la capa 4 y las anclas no corren aún dentro del simulador de la página.

## 2026-11-05 — CERNO v4.0 · F5: anclas NIVEL CERNO e IMPACTO en [0, 100]

Detalle: `docs/checkpoints/V40_F5.md`, `docs/modelo_equipo_v40.md` §6. Puerta F4 aprobada por el CEO y orden de arrancar F5.

* **Definiciones operativas** (`bbequipo/anclas.py`, encargo §10): NC = 100·E_pred[F_ref(C)] con C la contribución del motor
  (minutos × pts/100) y F_ref liga de destino × puesto (3 temporadas, minutos); IM = 100·E_pred[F_mov(Δ̂Net)] con Δ̂Net el Δ
  contrafactual de la capa 4 (plantilla real de t+1 con y sin el jugador, calibración c de F4) y F_mov los fichajes reales del
  mismo grupo de liga. Esperanzas sobre la predictiva completa (la incertidumbre empuja a 50).
* **NC** (4560 fichajes de decisión): el percentil crudo subestima ≈ 10 puntos a quienes llegan a jugar (selección del examen);
  capa de calibración isotónica + rango condicionado con cortes anteriores (decisión en el corte 2021). **Pasa §11.5**: separación
  70,9 % [69,3, 72,6], calibración por deciles (desvío máx. 3,6), cobertura 0,782. NC₂ ≈ NC₁ (la adaptación del
  motor v3.2 apenas mueve C).
* **IM** (3367 fichajes, 840 equipos; Δ̂ contrafactual con 200 simulaciones por fichaje): monotonía frente al ΔNet del equipo
  pasa (0,054 ≥ 0,022, IC95 > 0) pero la calibración literal no (el ΔNet realizado es del equipo). Frente al
  on/off realizado del fichaje [POST HOC]: Spearman 0,161 frente a 0,031 del aditivo (IC95 de la diferencia > 0), calibrado en 9 de 10
  deciles. **Puerta de IM no cumplida en su forma literal**; presentada al CEO con tres opciones.
* **Producto**: `anclas/referencias_nc_2026-27.json`, `anclas/referencia_im.json`, `anclas.nivel_cerno`, `anclas.impacto`.
* **Puerta (CEO, 05-11-2026): opción (b) y, mientras, (a).** NC referente. El examen de IM se redefine frente al Net on/off
  realizado del fichaje (prerregistrado en `criterios.f5.im_onoff` antes de ejecutar la versión calibrada; el diagnóstico sin
  calibrar ya visto queda declarado) con calibración isotónica como la de NC: Spearman 0,149 [0,12, 0,18] frente a 0,031 del
  aditivo (IC95 de la diferencia > 0), calibración por deciles (desvío máx. 2,5), cobertura 0,787 → **IM referente**. Complemento
  ordenado por el CEO con los efectos sobre compañeros de F2-B (modelos por corte ≤ t, agregados con las cuotas proyectadas):
  la variante IM+comp no mejora a IM (diferencia 0,003 [-0,02, 0,02]) y no se adopta; el «efecto sobre compañeros» se publica como
  subíndice aparte (redistribución, no valor neto; Spearman con el on/off 0,014). No solapa con NC.

## 2026-11-05 — CERNO v4.0 · F4: composición, Δ de equipo (capa 4) y A5

Detalle: `docs/checkpoints/V40_F4.md`, `docs/modelo_equipo_v40.md` §5. Puerta F3 aprobada por el CEO (opción b) y orden de
arrancar F4 el 05-11-2026.

* **Capa 4** (`bbequipo/equipo.py`): T(R) = E_S[Σβ + Σφ + Σh] con las cuotas de posesiones de la plantilla (observadas en t,
  proyectadas en t+1 con el motor Plackett-Luce de la v3.3 y pesos ≤ t); Net̂ centrado en la liga; Δ̂Net = Net̂_{t+1} − Net̂_t;
  β ~ N(β̂, sd) y minutos por Monte Carlo; jugador sin β ni perfil → nivel de «jugador nuevo» de su liga (F3 c).
* **Examen §11.4** (1149 transiciones reales equipo-temporada t → t+1 en 18 ligas; libro de roles + LBA/LNB/BSL enlazadas por
  plantilla; filtro del contrato D6 en la temporada de partida). Cortes de decisión (n = 933): **MAE 4,06** frente a
  **4,89** de persistencia (IC95 de la diferencia -1,02 a -0,65), aditivo F1 4,05, GBM directo 4,23 (IC95 ≠ 0),
  minutos reales de t+1 4,00; Spearman 0,54; cobertura del 80 % 0,77. **Puerta cumplida.** Por grupo: NBA 3,15 / 4,07,
  Europa top 3,23 / 3,90, FEB 4,61 / 5,78, Europa media 4,14 / 4,75, Europa menor 4,81 / 5,38, EE. UU. menor 3,30 / 3,92.
* **Decisiones en el corte de calibración 2021**: capa de calibración Net̂_{t+1} = c·T1' + d·Net_t (c ≈ 0,3–0,4, d ≈ 0,3–0,4; por
  grupo de liga con ≥ 40 transiciones previas): sin ella la proyección es peor que la persistencia; intervalos conformales con
  escala MC + ruido irreducible por grupo; capa de sesgo por tercil de minutos de las altas (§9.2) activada por regla.
* **Lectura**: la capa 4 es β + minutos + calibración; φ (F2) y h (F3) no mueven el Net de equipo de forma medible (sinergia
  sobre aditivo ≈ 0 %: hipótesis del encargo no confirmada); los minutos no son el cuello de botella.
* **A5** (`bbequipo/a5.py`, §9.6): spline de Δmin (3 nudos), matriz 5 × 5 de transición de rol contraída a la recta B9 (Bayes
  empírico), covariable de carga (adoptada por mejora significativa, pequeña y no causal). Examen §11.6 (3.594 fichajes, cortes
  anidados v3.2): pts/100 −2,5 % y TS% −2,2 % frente a B9 lineal (IC90 < 0); **pasa**. Publicado por métrica: A5 en ocho, B9
  en OREB/100.
* **Producto**: `equipo/calibracion.json`, `equipo/equipos_<t>.csv.gz`, clase `equipo.Equipo` (fuerza y Δ̂ de un cambio de
  plantilla con intervalo del 80 %), `equipo/a5/coeficientes_producto_a5.json` y `a5.aplicar`; `configs/simulation_v40.yaml`
  (v3.3 + bloque `v40`) y `CERNO_SIMULADOR=v40` aceptado (cambio aditivo en `bbfit/config.py`; la v3.3 no cambia).
* Pendiente declarado: integrar la capa 4 y A5 dentro de `simular()` bajo v40 y la paridad JS (encargo del artifact, §9.4);
  Four Factors de equipo por agregación sin examen.

## 2026-11-04 — CERNO v4.0 · F3: función de conjunto (examen acotado, puerta dura §11.3)

Detalle: `docs/checkpoints/V40_F3.md`, `docs/modelo_equipo_v40.md` §4. Puerta F2 aprobada por el CEO con la orden de ejecutar
F3 como examen acotado («opción (a)»).

* **Modelo** (`bbequipo/conjunto.py`): deep sets g(S) = ρ(Σ_i ϕ(z_i)) sobre el residuo de F1 + F2 (β y M_r congelados);
  ϕ 44→16→16, ρ 16→16→1, AdamW, 5 semillas promediadas. Examen §11.3 en quintetos no vistos de t+1 (99 % de los tramos) con
  IC95 por bootstrap de partidos.
* **Resultado**: **pasa** en los tres cortes de decisión (cocientes 0,99926 / 0,99933 / 0,99951; IC95 superiores < 1).
  Reducción del RMSE por tramo 0,05–0,07 %; señal común de g ≈ 2,8 pts/100 en la diferencia entre quintetos, calibrada.
* **Ablación aditiva [POST HOC]** (ρ lineal, g = Σ h(z_i)): gana lo mismo (0,99921 / 0,99942 / 0,99942). **Diagnóstico**:
  g es una corrección por jugador, dominada por el nº de jugadores sin perfil donde la cobertura es baja (corte 2022:
  R² 0,94 con los agregados; +2,4 pts/100 por jugador con perfil). Los jugadores en su primera temporada tienen β 1,3 pts/100
  por debajo de la media de su liga (−4,1 en Euroliga): F1 les imputa la media y F3 lo corrige.
* **Lectura**: no hay estructura de quinteto más allá de lo aditivo con estos datos («la red más simple gana»).
* **Puerta (CEO, 05-11-2026): opción (b)**: se publica la variante aditiva g(S) = Σ_i h(z_i) como «capa 3 reducida:
  corrección no lineal por jugador» (`f3.rho_lineal: true`; decisión post hoc por parsimonia, declarada); la imputación de
  nivel de jugador nuevo por liga se lleva a F4. Orden de arrancar F4.
* Salidas: `data/modelos/v4_0/conjunto/examen/` (resumen, redes por corte, ablación, diagnósticos) y producto en
  `conjunto/` (`redes.pkl`, `F3_conjunto.json` con `variante`).

## 2026-11-04 — CERNO v4.0 · F2: sinergia de pares y efectos dirigidos sobre compañeros

Detalle: `docs/checkpoints/V40_F2.md`, `docs/modelo_equipo_v40.md` §3. Puerta F1 aprobada por el CEO y orden de arrancar
F2 el 04-11-2026. β de F1 congelados; F2 aprende el residuo.

* **F2-A sinergia** (`bbequipo/sinergia.py`): φ(i,j) = z_iᵀ M_r z_j con los 44 rasgos estandarizados del perfil; ridge
  exacto sobre vec(M) (la suma de las 10 parejas de un quinteto es ⟨M, Q⟩) con λ por verosimilitud marginal; rango r = 4
  elegido en el corte de selección 2021; ψ por pareja observada con κ por validación cruzada (línea base ψ = 0 incluida).
  Examen §11.2 de parejas nuevas (`bbequipo/examen_f2.py`, cortes 2022–2024): **pasa formalmente** (IC95 de la reducción
  del error < 0 en los tres cortes) **con magnitud despreciable** (≈ 0,001 % del error; DT de φ̂ 0,03–0,17 pts/100 por
  pareja). Diagnóstico de λ: sin contracción los perfiles explican el 0,3 % del residuo en muestra y empeoran las parejas
  nuevas. La expectativa del encargo «sinergia 2–5 % sobre lo aditivo» queda anotada como hipótesis no confirmada.
* **F2-B efectos dirigidos** (`bbequipo/dirigidos.py`): d_k(X → Y) = GBM([z_X, z_Y, z_X ⊙ z_Y]) con peso n_ef, intervalos
  del 80 % conformales por tramos de peso. Examen §11.2 (tres cortes, 22–34 mil parejas por corte): **se publican cuota de
  tiro (−5 a −7 % de MAE frente a Δ = 0), % asistidas (−2 a −4 %) y pts/100 (−3 a −4 %)**, con cobertura 0,79–0,82; eFG% y
  % en el aro no pasan (ablación negativa). Producto: 249.094 parejas con efecto real, predicho e intervalo
  (`sinergia/dirigidos/efectos_<t>.csv.gz`), modelos y calibración (`modelos.pkl`, `resumen_producto.json`).
* Salidas F2-A: `sinergia/{M_completa.npy, M_rango.npy, W_sinergia.json, psi.csv.gz, examen/}`. **ψ no se publica**: la validación cruzada por partido elige la línea base ψ = 0 (11.526 frente a 11.528 con κ = 0,5); `psi.csv.gz` vacío.

## 2026-11-04 — CERNO v4.0 · F1: RAPM multiliga con prior del perfil (+ F1-D)

Detalle: `docs/checkpoints/V40_F1.md`, `docs/modelo_equipo_v40.md` §2. Puerta F0 aprobada por el CEO (D1–D8; D2 con
dos comprobaciones) y orden de arrancar F1 el 04-11-2026.

* **Modelo** (`bbequipo/rapm.py`): y_s = c_{ℓ,t} + clutch + playoffs + Σβ_A − Σβ_B, ε ~ N(0, σ²/n_s); β por
  persona-temporada = prior lineal del perfil (γ estimado CONJUNTAMENTE con β, LSQR) + desviación N(0, τ²); τ y α por
  verosimilitud marginal exacta (log-determinante disperso); candidato GBM por retroajuste; descomposición O/D; varianza
  de β por sondas de Hutchinson.
* **Corte de calibración 2021** (decisiones antes de los cortes de decisión): contrato con ≥ 1 posesión por tramo (los
  tramos de 0,5–0,75 posesiones, el 11 %, acaparaban el 32 % de la pérdida); el RAPM normalizado de la MISMA temporada no
  entra en el prior (circular); entra el de la temporada anterior; momentos y validación cruzada descartados para τ.
* **Examen prerregistrado §11.1** (`bbequipo/examen_f1.py`, cortes 2021–2024, 24.057 partidos de decisión): RMSE del
  margen por partido de t+1 **14,50** frente a 15,45 (interceptos de equipo), **14,68** (RAPM traducido v3.2, el del
  impacto actual), 15,14 (RAPM crudo de liga) y 15,69 (sólo ventaja local); diferencias con IC95 que excluyen el 0:
  −0,95, **−0,18** [−0,26, −0,09], −0,64 y −1,19. Fichajes: corr(prior, β en destino) 0,55 / 0,70 / 0,78 (IC95 > 0).
  Prior elegido: **GBM** (−9,3 % de error frente al ridge, IC95 [−12,8, −5,8]).
* **D2 cerrada**: sensibilidad a la red de referencia del latente −0,02 % (umbral 0,5 %); ablación del latente +3,5 %
  [−0,9, +7,9]: indeterminada, se conserva.
* Corrección declarada: la primera lectura imputaba 0 a los jugadores sin RAPM en las líneas base y hacía parecer roto
  el RAPM traducido en la Tercera FEB (nivel −11 pts/100); corregido a la media de liga.
* Test-retest: corr(β_t, β_{t+1}) 0,84 de media frente a 0,32 del RAPM de liga. F1-D: arrastre del Net del equipo
  sobre el RAPM de origen 0,085 pts por punto (0,17 en quienes juegan 800–1.500 min); con β de F1, 0,057.
* Salidas: `data/modelos/v4_0/rapm_multiliga/` (40.597 personas-temporada con β, sd, prior, peso del prior y O/D;
  `g_prior.json`; `examen/`; `f1d_contaminacion.json`).

## 2026-11-04 — CERNO v4.0 · F0 (preparación): perfil ampliado, contrato de datos y configuración única

Encargo v4.0 (rev. 1.2); detalle en `docs/checkpoints/V40_F0.md` y `docs/modelo_equipo_v40.md`. La v4.0 **añade**
(`bbequipo/`, `configs/equipo_v40.yaml`, `data/modelos/v4_0/`); nada de la v3.2/v3.3 cambia. Rama rebasada sobre
`claude/focused-dijkstra-mpqa3u` (v3.2/v3.3 cerradas), que `main` no contenía.

* **`configs/equipo_v40.yaml`**: todos los hiperparámetros de F0–F5 y A5 y los criterios de aceptación del §11
  (prerregistrados, congelados antes de ver resultados); decisiones del CEO del §10.4 copiadas en `f5`.
* **Perfil ampliado x̃** (`bbequipo/perfiles.py` → `data/modelos/v4_0/perfiles/<t>.csv.gz`, 52.392 filas, 2020-21 →
  2026-27): latente u ∈ ℝ⁴ (media y DT) de la posterior conjunta de las 20 redes de la v3.2 final, alineadas afínmente
  antes de promediar (R² medio 0,991, mínimo 0,929); pertenencias a los 6 estilos; θ y varianza propia de 16 rasgos
  (`destino/capacidad`); rol (probabilidades, índice esperado, MIN%, GS%, H_rol); edad y posición; RAPM observado como
  contraste. Nada se imputa con 0: avisos por bloque ausente. Para ≥ 300 min, completo en latente, estilos, θ de caja
  y rol en todas las temporadas cerradas; la Tercera FEB 2023-24 no tiene los rasgos de pista (PBP sin coordenadas).
* **Perfiles por corte** ≤ t (`perfiles/corte_<t>/`, t = 2021…2024) para los exámenes sin fuga: latente del ensemble
  ≤ t y θ de la fuente `V32_corte` generalizada a cualquier temporada ≤ t (`theta_corte`, `traducir_corte`; donde falta
  la v2 ≤ t, la red sola, como la combinación v3.2). Exportados los cuatro cortes (34.820 / 25.912 / 17.087 / 11.096
  filas); cadena reanudable `scripts/perfiles_v40.sh`.
* **Varianzas exactas de la posterior conjunta por complemento de Schur** (`PosteriorRapida`): Var(u), Var(μ) y
  Cov(u, μ) de todas las variables en ≈ 1,5 min por red (la vía directa costaba 15 min), error relativo < 3·10⁻⁹.
* **Redes CVAE reentrenadas** (la caché `experimentos/v3` no está versionada): misma configuración y semillas de la
  v3.2 final; coherencia con `v3_2/niveles.csv`: correlación 0,99995, diferencia mediana 0,004 DT (0,05 DT de la
  incertidumbre publicada).
* **Contrato de datos** (`bbequipo/contrato.py` → `data/modelos/v4_0/contrato/`): 115 liga-temporadas con tramos;
  basura fuera, clutch covariable, exposición = posesiones, localía h_s (team_a = local), 5 contra 5; 99 incluidas, 12
  con aviso, 4 excluidas (< 50 % de partidos con quintetos); 1.152.179 tramos válidos, ≈ 2,99 M de posesiones;
  mediana de 3-5 posesiones por quinteto.
* `tests/test_equipo_v40.py` (9, sintéticos); diccionario de datos (tablas `v4_0/`); MLflow `equipo_v40`.

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
