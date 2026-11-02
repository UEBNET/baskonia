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

*(se completan al terminar el examen)*
