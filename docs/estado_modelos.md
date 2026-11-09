# Estado de los modelos · una ficha por salida visible del producto

Revisión F0 de la v4.1 · 06-11-2026 (actualizada con la F1 el 07-11 y la F2 el 09-11) · rama de trabajo `claude/jolly-thompson-qczxl4` (base v4.0 `6fb6abd`).
Fuente única de las cifras: los checkpoints citados en cada ficha y el benchmark de decisión de la F0
(`data/modelos/v4_1/benchmark/benchmark.json`, `python -m bbequipo.ecosistema benchmark`). Etiquetas: **[DATO]** medido;
**[LECTURA]** interpretación; **[HIPÓTESIS]** supuesto; **[POST HOC]**; **[DECISIÓN]**.

**Cómo leer una ficha.**
- *Estado*: **validado** (pasó un examen prerregistrado sin fuga), **provisional** (examinado, pero con un hueco declarado:
  criterio redefinido, cobertura parcial o métrica sin examen propio) o **experimental** (sin examen todavía; no se publica
  como cifra).
- *Sello propuesto*: FIABILIDAD ALTA · MEDIA · BAJA (decisión 7 del CEO). Las reglas formales del §6.4 del encargo son para
  los **cambios** (Δ) por métrica y se aplican en la F3. Para las salidas de **nivel** que ya existen, se propone el mismo
  espíritu: **ALTA** = pasa su examen en cada corte de decisión con la cobertura del 80 % en [0,75, 0,85]; **MEDIA** = pasa en
  el agregado pero no en cada corte o segmento; **BAJA** = no pasa o no tiene examen. *Propuesta pendiente del CEO.*
- *Segmentos*: «élite» = EuroLeague + EuroCup + ACB; «global» = todas las competiciones.
- Cortes: 2021 calibra; 2022, 2023 y 2024 deciden (examen ≤ t → t+1).

---

## Resumen

| # | Salida visible | Versión | Estado | Sello propuesto | Qué hacer en la v4.1 |
|---|---|---|---|---|---|
| 1 | Minutos por partido (y uso) | v3.3 (mezcla motor + GBM) | validado | MEDIA | Recorte a [0, duración] y rangos recalibrados en la capa E (P5) |
| 2 | Producción por 100 posesiones (pts/100, TS %, USG %, AST %, rebote…) | v3.3 + A5 (v4.0) | validado | MEDIA | Sin cambios |
| 3 | Rol previsto | v3.3 | uso interno | — | Deja de ser salida (decisión 1) |
| 4 | Índice Fit | v2–v3.3 | **retirar** | — | Baja aprobada (decisión 3) |
| 5 | ADAPT % | v3.x | **retirar** | — | Baja aprobada; sustituida por «Landing» (decisión 4) |
| 6 | Landing (nueva) | adaptación v3.x por grupo | experimental | pendiente | Recalcular al 80 %; mostrar sólo si el rango excluye 0 |
| 7 | NIVEL CERNO (NC₁, NC₂) | v4.0 F5 | validado (referente) | ALTA (NC₁) | Recalcular con los compañeros del escenario |
| 8 | IMPACTO | v4.0 F5 | provisional (criterio redefinido) | MEDIA | Pasa a «Impacto en pista» (F2) |
| 9 | Net del equipo proyectado | v4.0 capa 4 | validado | ALTA | Base del motor de escenarios (F1) |
| 10 | ORtg / DRtg del equipo y Four Factors | v4.0 capa 4 | provisional / experimental | BAJA | Examinar en F1–F3 si se muestran |
| 11 | Efecto sobre compañeros (cuota de tiro, % asistidas, pts/100) | v4.0 F2-B | validado (como reparto) | MEDIA | Se examina en V-AUS (F3) |
| 12 | Sinergia de pareja por perfiles (φ) | v4.0 F2-A | validado (segundo orden) | BAJA | Entra en el Impacto en pista; nunca como «química» |
| 13 | Estilo | v3.x | descriptivo | — | Nunca se suma (decisión 9) |
| 14 | Quintetos más probables | v4.0 capa 4 | descriptivo | — | Sólo descripción de la rotación (decisión 8) |
| 15 | Avisos de la ficha | v3.3 | provisional | — | Recalibrar: el 64,5 % de las fichas lleva alguno |
| 16 | Impacto en pista | v4.1 F2 | experimental: no alcanza al IMPACTO v4.0 (0,081 frente a 0,149; V41_F2) → regla F2-a | — (EXPERIMENTAL; su cambio por altas/bajas, BAJA) | Puerta F2 (V41_F2 §10) |
| 17 | Δ por métrica de cada compañero | v4.1 F1 (motor) / F3 (sello) | calculado en F1; sin sello | — | Sello por métrica §6.4 (F3); cuota de tiro sin renormalizar (V41_F1 §5) |
| 18 | Valor de baja | v4.1 F1 / F3 | calculado en F1; sin examen | — | Examen en V-AUS (ΔNet frente a Δ = 0) |
| 19 | Atribución por movimiento (Shapley) | v4.1 F1 | validado (composición exacta: Σ = Δ a 10⁻¹⁴ en 472 escenarios) | hereda el de lo atribuido | — |
| 19b | Net del escenario (altas con rol, bajas) | v4.1 F1 | validado como composición: paridad con la capa 4 exacta en 117/118 (el otro, corrección P5) | hereda la capa 4 (ALTA) | V41_F1 |
| 19c | Rangos de minutos de la capa E | v4.1 F1 (P5) | validado: cobertura 80 %/90 % en rango en cada corte | ALTA (propuesto) | V41_F1 §3 |
| 20 | Sinergia de tríos (φ₃) | v4.1 F3-T | experimental, condicional | — | EMD > 2 pts/100 frente a una puerta de 0,10: examen no informativo; propuesta: cerrar la F3-T (V41_F0 §11.3) |
| 21 | Capa XP: punto esperado por tiro, tramo y jugador | v4.1 (xp1) | experimental (41 campos desde la F2-d); resultado de tramo 0,75·real + 0,25·esperado adoptado por regla | — (sin sello hasta examinar cada campo) | Catálogo ampliable: `docs/puntos_esperados.md` |

---

## 1 · Minutos por partido (y uso)

- **Versión**: v3.3, `minutos_publicados: mezcla` (50 % motor Plackett-Luce + 50 % GBM) con el acoplamiento B9.
  `configs/simulation_v33.yaml`, `docs/simulador_v33.md` §5.1.
- **Datos y corte**: fuente V32_corte (perfiles ≤ t); datos hasta el 29-10-2026; identidades corregidas el 04-11-2026.
- **Examen [DATO]**: anidado, cortes 2022-23 a 2024-25, 4.956 fichajes. Error medio de minutos 4,70 (v3.2: 4,87;
  diferencia −0,17 [IC90 −0,20, −0,14]). Cobertura del 50/80/90 %: 0,57 / 0,83 / 0,93.
- **Benchmark F0 [DATO]** (límites físicos):
  - *Producto v3.3* (9.066 fichas, escenario «inicio», 2021-22 a 2026-27): **1 ficha** con el extremo del 90 % por encima de la
    duración del partido (40,08 > 40); ninguna por debajo de 0. **Saturación de la cola superior**: en el 97,7 % de las fichas
    el extremo del 90 % es igual al del 80 % (diferencia < 0,5 min). Consecuencia: cobertura del 80 % 0,805 (élite 0,851)
    pero del 90 % sólo 0,872 (élite 0,920); el 7,1 % de los minutos reales queda por encima del extremo superior del 90 %.
  - *Examen por cortes de la v3.2* (5.188 fichas): 1.425 con algún extremo fuera de [0, duración] (máximo 63,8 min); son
    intervalos del examen, no del producto, pero indican que el motor no recorta.
- **Fugas conocidas**: el histórico del producto se calcula con los pesos finales (en muestra): su cobertura es optimista.
- **Estado**: validado. **Sello propuesto**: MEDIA (cobertura del 80 % en rango; la del 90 % no, por la saturación).
- **Para la v4.1** [DECISIÓN CEO 06-11-2026, P5 con workaround]: el motor v3.3 no se toca. El motor de escenarios (F1)
  recorta a [0, duración], fuerza Σ minutos = 200/240 en el 100 % de los escenarios y **recalibra sus propios rangos de
  minutos** (conformal con los cortes anteriores) para corregir la cola superior. Criterio: cobertura del 80 % en
  [0,75, 0,85] y del 90 % en [0,85, 0,95].

## 2 · Producción por 100 posesiones

- **Versión**: traducción v3.2 + B9 (v3.3) + A5 (v4.0; A5 con carga en ocho métricas, B9 lineal en OREB/100).
- **Examen [DATO]**: A5 §11.6, 3.594 fichajes (cortes 2022–2024, ≥ 300 min): MAE pts/100 3,554 (B9 3,647; −2,5 % IC90 < 0),
  TS % 4,695 (−2,2 %), USG % 2,653 (−4,0 %). Cobertura del 80 % de la contribución C: 0,79 (v3.3).
- **Benchmark F0 [DATO]**: Spearman(C predicha, C realizada) 0,467 global, 0,418 élite. Con «rol oráculo» (minutos reales de
  t+1 fijados como si los pusiera el analista): 0,892 y 0,885. **[LECTURA]** Es una cota superior: C = minutos × pts/100 y
  los minutos reales están en los dos lados. Aun así dice dónde está el error: casi todo es *cuántos minutos jugará*, no
  *cuánto produce por minuto*. Que el analista fije el rol de las altas (decisión 1) ataca exactamente esa fuente.
- **Fugas**: ninguna conocida (cortes ≤ t).
- **Estado**: validado. **Sello propuesto**: MEDIA (mejora sólida a B9, pero el error absoluto de TS % ≈ 4,7 puntos es grande
  frente a su dispersión).

## 3 · Rol previsto

- **Decisión 1 del CEO**: el rol lo fija el analista para las altas; los jugadores que ya están conservan su rol de partida.
  La predicción de rol **no es una salida del producto** (acierto de rol del examen: 42,7 %). Se conserva como insumo interno
  del motor de minutos.

## 4 · Índice Fit — retirar

- **Decisión 3 del CEO**: se elimina de toda vista, informe, tabla y texto. El código de los simuladores cerrados se conserva.
- **Inventario F0 [DATO]**: 453 apariciones de Fit/ADAPT; 89 en vistas (68 identificadores y 21 textos visibles) en 5
  ficheros del artifact (`atlas/index.html`, `atlas/informe_v3.js`, `atlas/simulador.js`, `atlas/simulador_v2.js`,
  `mesa-multiliga.html`). Detalle: `data/modelos/v4_1/inventario/fit_adapt.csv` y V41_F0 §6.

## 5 · ADAPT % — retirar (sustituido por «Landing»)

- **Decisión 3 y 4 del CEO**. Mismo inventario que la ficha 4.

## 6 · Landing (nueva)

- **Definición (decisión 4)**: el escalón entre NC₁ y NC₂, con la causa a nivel de **grupo de traspaso** (p. ej.
  «Landing · EE. UU. → Europa: −x,x % [rango 80 %]»). Sólo se muestra si el rango del grupo excluye 0; nunca un decimal
  individual.
- **Fuente**: modelo de adaptación vigente (v3.x; `data/modelos/adaptacion/v3_2/fase7/adaptation_priors.csv` por celda y
  grupo, curvas por grupo de nacionalidad de `adaptacion/v3_1/resumen.json`).
- **[DATO]** en la v4.0, NC₂ ≈ NC₁ (medias 45,3 y 45,4; correlación 0,98; V40_F5 §2). **[LECTURA]** El escalón será pequeño
  en casi todos los grupos. Es probable que, al exigir que el rango del 80 % excluya 0, la mayoría de las fichas no muestre
  Landing. Conviene que el CEO lo sepa antes de diseñar la vista.
- **Estado**: experimental. Pendiente: recalcular los rangos del grupo al 80 % (hoy están a otro nivel) y examinar su
  cobertura con los cortes (F1–F2).

## 7 · NIVEL CERNO (NC₁ titular, NC₂ al lado)

- **Versión**: v4.0 F5 (`bbequipo/anclas.py`), referente. NC = 100·E_pred[F_ref(C)], F_ref liga de destino × puesto (3
  temporadas, minutos), calibración isotónica con cortes anteriores.
- **Examen §11.5 [DATO]** (4.560 fichajes): separación 70,9 % [69,3, 72,6]; calibración por deciles ±3,6; cobertura 0,782.
  Por corte: separación 74,7 / 67,6 / 72,9 %; cobertura 0,762 / 0,773 / 0,806.
- **Benchmark F0 [DATO]**: Spearman(NC₁, percentil realizado) 0,454 [0,429, 0,479] global; **0,367 [0,301, 0,434] élite**
  (650 fichajes; cobertura 0,76). Top-10 por corte (global, ≈ 1.500 fichajes por corte): percentil realizado medio 84,2
  frente a 45,7 de todos; en el segmento élite (≈ 215 por corte) 65,1 frente a 45,2.
- **Fugas**: la calibración del corte 2021 usa su propio corte (declarado; no decide).
- **Estado**: validado. **Sello propuesto**: ALTA para NC₁ (pasa en cada corte); NC₂ hereda, con la nota de la ficha 6.
- **Límite declarado**: C son puntos; defensa y juego sin balón no entran en NC.
- **v4.1 F2-b (09-11-2026)**: NC₁/NC₂ **por escenario**: el mismo cálculo con los compañeros y roles del escenario
  (`Ecosistema.simular(..., nc=True)`); hereda el examen y el sello del NC (V41_F2 §8).

## 8 · IMPACTO (v4.0)

- **Versión**: v4.0 F5, criterio redefinido (decisión b del CEO, prerregistrado antes de ejecutar la versión calibrada).
- **Examen [DATO]**: Spearman(IM, on/off realizado) 0,149 [0,12, 0,18] frente a 0,031 del aditivo; calibración ±2,5;
  cobertura 0,787 (3.598 fichajes).
- **Benchmark F0 [DATO]**, segmento élite (484): Spearman 0,159 [0,062, 0,254] frente a 0,082 del aditivo; diferencia
  [0,002, 0,149] (excluye 0 por poco). Con el percentil on/off del grupo, la diferencia en élite incluye 0 ([−0,025, 0,118]).
  El 90 % de los IM publicados está en [42,5, 60,7]: **la escala está muy comprimida alrededor de 50**.
- **Fugas**: [POST HOC] criterio redefinido tras ver el literal (declarado en V40_F5 §6.0).
- **Estado**: provisional. **Sello propuesto**: MEDIA (pasa en global; en élite, en el límite).
- **v4.1**: iba a sustituirse por «Impacto en pista» (ficha 16) si no empeoraba esta línea base (§6.2). **No la alcanza**
  (V41_F2: 0,081 frente a 0,149; diferencia −0,068 [−0,101, −0,035]) → por la regla F2-a el IMPACTO v4.0 sigue siendo el
  ancla publicada.

## 9 · Net del equipo proyectado (capa 4)

- **Versión**: v4.0 F4: β (F1) + φ (F2-A) + h (F3) + minutos v3.3 + calibración (c, d por grupo de liga).
- **Examen §11.4 [DATO]** (933 transiciones de decisión): MAE de ΔNet 4,06 frente a 4,89 de la persistencia (IC95 de la
  diferencia −1,02 a −0,65); Spearman 0,54; cobertura 0,77 (por corte 0,79 / 0,75 / 0,76).
- **Benchmark F0 [DATO]**, élite (148): MAE 3,23 frente a 3,90 (diferencia [−1,02, −0,32]); cobertura 0,80. Con los minutos
  reales de t+1 (rol oráculo) el MAE no cambia de forma significativa (global: diferencia [−0,12, +0,00]).
- **Fugas**: la plantilla de t+1 es la real (pregunta «dado este vestuario»), declarado.
- **Estado**: validado. **Sello propuesto**: ALTA (en cada corte y en élite).

## 10 · ORtg / DRtg del equipo y Four Factors

- ORtg/DRtg salen de β^O y β^D (F1) con la misma composición; **no tienen examen propio** en la v4.0. Four Factors por
  agregación con calibración lineal, sin examen prerregistrado [HIPÓTESIS, V40_F4 §6].
- **Estado**: provisional (ORtg/DRtg) y experimental (Four Factors). **Sello propuesto**: BAJA hasta examinarlos.

## 11 · Efecto sobre compañeros (F2-B)

- **Versión**: v4.0 F2-B: efectos dirigidos X → Y publicados en cuota de tiro, % asistidas y pts/100 (cobertura 0,79–0,82);
  eFG % y % en el aro **no** son predecibles.
- **[DATO]** (V40_F5 §3.1): el subíndice «efecto sobre compañeros» tiene Spearman 0,014 con el on/off del fichaje: mide
  **reparto**, no valor neto.
- **Estado**: validado como predicción del reparto. **Sello propuesto**: MEDIA hasta pasar V-AUS (F3).

## 12 · Sinergia de pareja por perfiles (φ)

- **Versión**: v4.0 F2-A, rango 4. DT de φ̂ en parejas reales 0,17 pts/100; ψ por pareja no supera a ψ = 0.
- **Prueba de orden F0 (§2.2 reproducido)**: ver V41_F0 §4. La varianza propia de pareja que se mide en pista está
  **inflada** por el error de β, que es común a los dos tercios de medida (calibración nula), y a la vez **atenuada**,
  porque la absorben los efectos de jugador (calibración plantada).
- **Modelo mixto REML (V41_F0 §4.7)**: σ̂ = 0 en parejas, tríos y quintetos. La calibración plantada sobre datos reales
  muestra que ninguna química propia de pareja por debajo de ≈ 2–3 pts/100 es medible en pista, con ningún método. Sólo la
  química **predicha por perfiles** (φ) es utilizable.
- **Estado**: validado (segundo orden). **Sello propuesto**: BAJA como cifra propia; el producto no promete «química».

## 13 · Estilo

- Descriptivo (decisión 9): nunca se suma a NIVEL CERNO ni a IMPACTO. Las pertenencias de estilo se ajustaron con todas las
  temporadas [HIPÓTESIS declarada en la v4.0; fuga leve en los perfiles].

## 14 · Quintetos más probables

- P(S | R) de la capa 4. Decisión 8: sólo como descripción de la rotación; no son fuente de valor.

## 15 · Avisos de la ficha

- **Benchmark F0 [DATO]** (producto v3.3, 9.066 fichas): el 64,5 % lleva al menos un aviso (élite 57,3 %); 0,98 avisos por
  ficha; «incertidumbre alta» en el 43,1 % de las fichas.
- **[LECTURA]** Un aviso que aparece en dos de cada tres fichas pierde valor informativo. **Propuesta**: en la F4, que el sello
  de fiabilidad sustituya a «incertidumbre alta» y «volatilidad alta» (redundantes con el rango del 80 %), y que sólo queden
  los avisos que el sello no recoge («muestra pequeña», «liga lejana», «cambio de rol»).

## 16–20 · Salidas nuevas de la v4.1 (experimentales)

| # | Salida | Definición | Examen que la habilita | Línea base que no puede empeorar |
|---|---|---|---|---|
| 16 | Impacto en pista | v_j(R) del §3.3 (β + h + Σ π φ [+ tríos] [+ contexto]) → percentil esperado calibrado | §6.2: monotonía, calibración ±7, cobertura 80 %, contextualidad | IMPACTO v4.0 (0,149) |
| 17 | Δ por métrica de cada compañero | F2-B + motor de minutos, renormalizado | §6.4 (sello por métrica, bancos V-AUS + otro) | Δ = 0 y redistribución proporcional |
| 18 | Valor de baja | ΔNet del equipo sin el jugador, minutos redistribuidos por el motor | V-AUS frente a Δ = 0 (criterios de la capa 4) | Δ = 0 |
| 19 | Atribución (Shapley) | φ_k exacto si \|M\| ≤ 4; permutaciones con error MC declarado si no | Tests: Σ φ_k = Δ total; determinismo | — |
| 20 | Sinergia de tríos | φ_jkl por perfiles (CP de rango bajo) sobre el residuo F1 + F2 + h | §6.3: reducción de error con IC95 < 0 en los tres cortes y DT ≥ 0,10 | Motor de orden 2 |

### Ficha 16 tras la F2 (09-11-2026, V41_F2)

- **Examen §6.2 [DATO]** (las 3.598 filas del IMPACTO v4.0, cortes 2022–2024, bootstrap de equipos-temporada):
  - monotonía 0,081 frente a 0,149: **no cumple** la no inferioridad;
  - frente al aditivo +0,050 [0,024, 0,077];
  - calibración ±5,0 y cobertura 0,792;
  - élite 0,170 frente a 0,159 (informado).
- **Contextualidad [DATO]**: −0,003 [−0,039, 0,033], EMD 0,05: no cumple → el cambio por altas/bajas lleva sello BAJA.
- **Candidatos**:
  - contexto c_j: entra por la regla literal, pero [POST HOC] es un artefacto del on/off (frente al β RAPM de t+1 cae de
    0,58 a 0,13): propuesta de no adoptarlo;
  - familiaridad: no entra; [POST HOC] es selección.
- **Estado**: experimental; se muestra en el motor de escenarios con sello EXPERIMENTAL
  (`impacto_pista/referencia_impacto_pista.json`).

## 21 · Capa XP · punto esperado por tiro (nueva, 07-11-2026)

- **Versión**: xp1, con acierto por zona × liga-temporada contraído hacia su tipo y TL del tirador contraído
  (`bbequipo/ecosistema/puntos_esperados.py`). Planteamiento y catálogo: `docs/puntos_esperados.md`.
- **Datos**: 115 ligas-temporada, 2020-21 a 2026-27. Tiros con zona: mediana 99,9 %. Sin coordenadas: CBA y FEB antes de
  2024-25.
- **Comprobaciones [DATO]**:
  - xp total ≈ puntos totales;
  - tramos con los puntos reconstruidos exactos desde los tiros: ≥ 99,6 % en todas las ligas-temporada.
- **Examen [DATO]** (prerregistrado, V41_F0 §11.2): como resultado de tramo, sólo el esperado empeora la predicción del
  marcador real; la mezcla 0,75·real + 0,25·esperado la mejora (+0,0004 de R², IC95 > 0, global y élite) → **adoptada**
  para los modelos nuevos de la capa E.
- **Fugas**: ninguna (las tasas de la temporada son su instrumento de medida, no una predicción).
- **Estado**: experimental campo a campo. Cada métrica de jugador necesita su examen, con su efecto mínimo detectable,
  antes de mostrarse con sello.
- **F2-d (09-11-2026)**: on/off con los mismos tramos y sin la suerte del tiro (`net_off`, `xnet_off`, `net_onoff`,
  `xnet_onoff`; 41 campos activos). DT de xnet_onoff 5,4 frente a 8,9 del on/off real [DATO].

## Regla común desde el 07-11-2026: efecto mínimo detectable

Todo examen de F1–F3 declara su curva de potencia (efecto sembrado sobre datos reales) y su EMD antes de decidir. Si el
EMD supera el umbral de la puerta, el examen no es informativo (`configs/ecosistema_v41.yaml → potencia`). Primera
aplicación: la puerta F3-T, ficha 20.

## Cómo comprobarlo

```bash
python -m bbequipo.ecosistema benchmark        # ≈ 1,5 min: data/modelos/v4_1/benchmark/benchmark.json
python -m bbequipo.ecosistema inventario       # fit_adapt.csv y club_temporada.csv
python -m bbequipo.ecosistema impacto-pista    # F2: examen §6.2 del Impacto en pista (V41_F2)
python -m pytest tests/test_ecosistema_v41.py -q
```
