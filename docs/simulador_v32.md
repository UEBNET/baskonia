# Simulador de encaje v3.2

> Configuración: `configs/simulation_v32.yaml` (se activa con `CERNO_SIMULADOR=v32`) · resultados:
> `data/modelos/simulador/v3_2/` · código: `bbfit/simulador.py` (motor), `bbfit/v32.py` (decisiones A1-A4) y
> `bbfit/b7_b9.py` (evaluación de B7 y B9). El simulador v3.1 (`configs/simulation_v31.yaml`,
> `data/modelos/simulador/v3_1/`) no cambia.

## 1. Punto de partida

En el examen de la v3.1 con 20 ligas (2021-22 → 2024-25, 6.028 fichajes), el motor ganaba claramente en minutos y
rol. En producción perdía frente a la línea base del Atlas:

| | Motor v3.1 | Atlas (a) | Simple (b) |
|---|---|---|---|
| Error medio de minutos | **4,87** | 6,28 | 5,91 |
| Acierto de rol | **43 %** | 39 % | 39 % |
| Error medio de pts/100 | 3,91 | **3,80** | 3,97 |
| Error medio de TS% | 5,89 | **5,18** | 5,51 |

## 2. Cambios

Las reglas son las de los criterios matemáticos del 02-11-2026, aprobados por el usuario antes de ver resultados.
Sustituyen a las del primer plan del mismo día.

- **§1 · Examen sin fuga.** La fuente «V32» lee la normalización ajustada con todas las temporadas, así que el insumo
  de origen ya contiene parte de lo que se quiere predecir. La fuente nueva **«V32_corte»**
  (`sim_insumos.normalizacion_hasta_v32`) mezcla, para cada corte t y con los pesos B2 de ese corte:
  - la CVAE de la configuración final entrenada con ≤ t (20 redes);
  - la v2 ≤ t, que es el A amortiguado reajustado con ≤ t (no hay traducciones del B por corte);
  - con sus propias constantes lineales.

  Reglas de uso:
  - A4 y toda cifra absoluta: solo con V32_corte.
  - A1, A3 y A2: con las dos fuentes; si no coinciden, manda V32_corte.
  - Los pesos de utilidad y calibración son los de la ejecución V32 (`--pesos-de`).
- **§2 · A1, pasos que se pueden apagar** (redistribución del uso, uso-eficiencia, compañeros, adaptación, ruido
  personal), por **no inferioridad** con Δ = MAE_sin/MAE_con − 1 e IC del 90 % por club de destino × corte, pareado.
  Se quita el paso si se cumple todo esto:
  - Δ_pts y Δ_TS < +0,5 %;
  - Δ_min < +1 % y la pérdida de acierto de rol > −0,5 pp;
  - Δ < +1 % en USG%, AST% y TOV%;
  - Δ_pts puntual con destino EuroLeague < +2 %;
  - para el ruido personal, el Winkler del 80 % de pts/100 con recalibración anidada < +1 %;
  - la contribución C en P_all < +1 %.

  Si algo empeora de forma significativa, se conserva. Si no se cumple todo pero nada empeora, es «indeterminado» y se
  conserva. Si se quitan los dos pasos que tienen ejecución propia, hace falta la ejecución combinada; sin ella, se
  quita solo el de menor Δ_pts.
- **§3 · A3, factores sobre el TS%.** TS' = TS + k_β·β·ΔUSG + k_c·b·ΔL̄, con k en {0; 0,25; 0,5; 0,75; 1}², calculado
  sobre las mismas simulaciones.
  - Criterio: J(k) = media de MAE_pts y MAE_TS relativos.
  - Regla de 1 error típico: K₁ = {J(k) − J(k*) ≤ SE}. Dentro de K₁ se elige el de menor k_β + k_c (**parsimonia**,
    decisión del usuario) que además no empeore C más de un +1 %.
- **§4 · A2, producción del Atlas,** frente a A3, con
  J_ω = 0,30·pts + 0,30·TS + 0,15·USG + 0,15·AST + 0,10·TOV (MAE relativos). A2 solo si se cumplen las tres cosas:
  - IC90,sup[J_ω(A2) − J_ω(A3)] < 0;
  - Δ_pts con destino EuroLeague < +2 %;
  - C no empeora más de un +1 %.
- **§5 · A4, recalibración conforme** de los intervalos del 50, 80 y 90 % (producción, minutos y C):
  - las dos colas por separado, con cuantiles con signo;
  - pesos por recencia ρ^(t−1−s), con ρ = 0,5;
  - cuantil ponderado con corrección de muestra finita;
  - contracción por grupos: f_g = (n_g f̂_g + 30 f̂_padre)/(n_g + 30), de destino (4 grupos) a destino × origen
    {FEB3, NCAA, resto} si n ≥ 15;
  - aceptación: |Cob − α| ≤ 2√(α(1−α)/n) + 0,02 por métrica y grupo de destino con n ≥ 100.
- **§6 · Poblaciones.**
  - P_all: ≥ 5 partidos. Ahí se mide la contribución C = (min/partido ÷ minutos del partido)·pts/100 (0 si < 50 min),
    por Monte Carlo del propio motor.
  - P_300: deciden A1-A4.
  - P_50-300: error tipificado con la varianza predictiva del valor observado.
- **§7 · Métricas de decisión** (solo informe):
  - Spearman entre Ĉ y C por liga de destino × corte (≥ 10 fichajes);
  - decil superior;
  - Brier y fiabilidad de P(C ≥ p75 de la liga de destino);
  - siempre por grupo y por corte.
- **§16.**
  - Línea base fuerte de minutos con gradient boosting (HistGradientBoosting de scikit-learn; LightGBM no está
    instalado).
  - B7 indica un límite estructural del motor solo si mejora el MAE de pts/100 > 5 % con significación.
  - B9 se abre si corr(e_min, e_pts) > 0,3 o si la cota del oráculo baja el MAE de pts/100 > 3 %.
  - El rol ordinal (C1) queda como trabajo futuro.
- **Vara de destino.** Con `destino.vara: destino`, la incertidumbre de la traducción usa la varianza propia del
  jugador y la DT por par de la mezcla (docs/normalizacion_v32.md §5). La liga de destino queda a 0.
- **Capacidad de los jugadores.** Viene de la normalización v3.2: fuentes «V32» y «V32_corte».

## 3. Cortes anidados

- Lo que se aplica en el corte t (2021-22 … 2024-25) se decide con los cortes anteriores. El primero usa el motor
  v3.1 tal cual.
- La decisión final, la del simulador publicado, usa todos los cortes. Se escribe en `decisiones_v32.json` y se fija
  en la configuración: `pasos`, `factor_ajustes_ts`, `v32.produccion_publicada` y `v32.aplicar_recalibracion`.

## 4. Resultados

Examen 2021-22 → 2024-25: 6.028 fichajes, de los que 4.525 tienen ≥ 300 minutos en destino. Datos en
`data/modelos/simulador/v3_2/decisiones_v32.json`; examen por fuente en `validacion/<etiqueta>/`.

**Cifras con las identidades corregidas** (03/04-11-2026, `docs/identidades_20261103.md`). El examen se repitió
entero, con el motor completo (`v32.config_examen`): las decisiones son las mismas que antes de la corrección y las
cifras apenas cambian.

### 4.1 Las dos fuentes, con el motor completo

| Fuente | Minutos | Rol | pts/100 | TS% | Cobertura 90 % pts/100 |
|---|---|---|---|---|---|
| V32 (con fuga) | 4,86 | 42,8 % | 3,86 | 5,97 | 0,863 |
| **V32_corte (sin fuga)** | 4,87 | 42,7 % | 3,85 | 5,24 | 0,836 |

**Lectura sobre la fuga**
- Quitar la fuga baja la cobertura, como se esperaba: los intervalos con fuga eran optimistas.
- El error de TS% mejora sin fuga. La explicación probable es que la parte v2 por corte no lleva el algoritmo B y
  que las constantes de traducción son las del propio corte. Queda como pregunta abierta para el examen limpio.

### 4.2 Decisiones finales (las dos fuentes coinciden)

Δ = MAE sin el paso / MAE con él − 1; IC del 90 % por club.

| Paso | Efecto de quitarlo | Decisión |
|---|---|---|
| Curva uso-eficiencia (k_β) | pts −0,10 % [−0,14, −0,06]; TS −0,38 % [−0,46, −0,31] | **Se quita** (k_β = 0) |
| Efecto compañeros (k_c) | pts −2,76 % [−3,17, −2,36]; TS −5,56 % [−6,33, −4,83]; C −1,0 % | **Se quita** (k_c = 0) |
| Redistribución del uso | pts **+2,72 %** [+2,20, +3,21]; USG +2,1 %; C +1,0 % | Se conserva |
| Adaptación | Sin diferencias significativas | Indeterminado: se conserva |
| Ruido personal | Winkler del 80 % **+12,1 %** [+11,1, +13,2] | Indeterminado: se conserva |

- **A3.** Con los dos pasos quitados, la rejilla queda en k = (0, 0).
- **A2.** La producción del Atlas mejora J_ω −0,9 % [IC 90 % −1,9, −0,03], también con destino EuroLeague (−4,3 %), y
  cumple §6c. **Se publica la producción del Atlas**, con los minutos y el rol del motor.

### 4.3 Examen anidado sin fuga: motor v3.1 frente a v3.2

En cada corte se aplica lo decidido con los cortes anteriores; el primero usa el motor tal cual.

| Medida | Motor v3.1 | v3.2 |
|---|---|---|
| Error medio de minutos | 4,87 | 4,87 |
| Acierto de rol | 42,7 % | 42,7 % |
| Error medio de pts/100 | 3,85 | **3,81** |
| Error medio de TS% | 5,24 | **4,98** |
| Error medio de AST% | 4,26 | **4,20** |
| Error medio de la contribución C (P_all) | 4,65 | **4,50** |
| Sesgo de C (Ĉ − C) | −2,47 | −2,17 |
| Cobertura 50 / 80 / 90 % de pts/100 | 0,42 / 0,72 / 0,84 | **0,50 / 0,80 / 0,90** |
| Cobertura 80 / 90 % de minutos | 0,92 / 0,97 | **0,83 / 0,93** |
| Winkler del 80 % de pts/100 | 17,97 | **17,39** |

**§5e, aceptación de la recalibración**
- pts/100 cumple en los tres niveles y en los cuatro grupos de destino.
- En minutos, el 50 % queda ancho (cobertura 0,57) y el 80 % de NBA/G League sale 0,84. Es decir, los intervalos de
  minutos todavía son algo conservadores.

**§6a, banda de 50-300 minutos (1.445 casos)**
- Error tipificado medio de pts/100: −0,30 (DT 0,87); de TS%: −0,16.
- Sobrestimamos a quien acaba jugando poco, como anticipaba el documento de criterios.
- La cobertura predictiva del 80 % es 0,84-0,86.

**§7, métricas de decisión**
- Spearman medio entre Ĉ y C por liga de destino × corte: 0,47 [IC 90 % 0,45, 0,50] en 69 grupos (motor v3.1: 0,44).
- Decil superior: error medio de C 6,21, con un sesgo de −3,85.
- Brier de P(cuartil superior) 0,177, frente a 0,234 sin modelo.

### 4.4 B7, B9 y la línea base de minutos (examen sin fuga)

**B7, gradient boosting supervisado**
- pts/100 3,76 frente a 3,89 del motor: −3,2 % [IC 90 % −4,5, −1,8].
- No llega al −5 % exigido, así que el límite está en el ruido, no en la estructura del motor.
- La red pequeña (MLP) queda peor: +3,3 %.

**B9, minutos y producción juntos**
- Correlación entre el error de minutos y el de pts/100: 0,35. Cota del oráculo: −7,7 %.
- Se cumplen las dos condiciones de apertura, así que **la regla dice abrir B9**.
- El usuario lo aprobó el 03-11-2026: **simulador v3.3** (`docs/simulador_v33.md`).

**Línea base de minutos**
- El gradient boosting predice mejor los minutos que la utilidad de Plackett-Luce: 4,68 frente a 4,86.
- Motor − GBM = +0,18 [+0,11, +0,27]. El motor no gana con claridad.
- El usuario aprobó llevarlo al simulador v3.3, donde el examen elige entre motor, GBM y la mezcla de los dos.
