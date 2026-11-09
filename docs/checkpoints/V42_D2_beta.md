# Checkpoint V42_D2_beta — CERNO v4.2 · D2 · β RAPM con historial del jugador

Fecha: 09-11-2026. Prerregistro: `configs/v42.yaml → motor_v42.piezas.beta_v42` y `motor_v42.examen_beta` (no se ha
tocado). Código: `bbequipo/v42/beta.py` (reutiliza el filtro de D1, `bbequipo/v42/historial.py`). Salidas:
`data/modelos/v4_2/beta/`. No se ha sobrescrito nada de la v4.0 ni de la v4.1.

Etiquetas: **[DATO]** medido con el comando del §6; **[LECTURA]** interpretación; **[SUPUESTO]**; **[POST HOC]**;
**[DECISIÓN]**.

---

## 0. Resumen

1. **[DATO] El β v4.0 no agrega temporadas.** Es un β por persona-temporada. El único puente entre temporadas es un rasgo
   del prior g(x̃): el RAPM normalizado v3.2 de la temporada anterior (`orapm_th`, `drapm_th` de t−1;
   `f1.prior.rasgos_temporada_anterior`). Por eso se compara el **β v4.0 de t** con el **β v4.2**, que aplica un Kalman
   explícito sobre los β v4.0 de cada temporada ≤ t.
2. **[DATO] (a) Spearman con el on/off realizado de t+1:** 0,182 para v4.0 y 0,172 para v4.2. Diferencia −0,011,
   IC95 [−0,019; −0,003]. **Pasa la no inferioridad** (umbral −0,02), aunque por poco. Ojo: el IC excluye 0, así que
   **ordena algo peor**.
3. **[DATO] (b) MAE frente al β de t+1:** 2,227 para v4.0 y 2,193 para v4.2 pts/100. Diferencia −0,034, IC95
   [−0,060; −0,006]. **Pasa.**
4. **[DECISIÓN] Formalmente pasa:** según la regla, el β v4.2 sustituye al β v4.0 en la capa 1. **[LECTURA]** El
   resultado es frágil (§3), y lo que no ha pasado su propio examen no se propaga a IMPACTO (§4).
5. **[DATO] Intervalos:**
   - El intervalo del 80 % del nivel en t es más estrecho: la razón mediana de anchuras v4.2/v4.0 es **0,94**.
   - El predictivo del 80 % de β_{t+1} sobrecubre: **0,887** de cobertura. Tras la recalibración conformal con 2021 baja
     a 0,815 y mide 7,33 pts/100, más ancho que el predictivo v4.0 equivalente (6,98).

## 1. Qué se ha construido

- **Observaciones (sin fuga).** En el corte t se usan los β y `beta_sd` del ajuste v4.0 del propio corte
  (`data/modelos/v4_0/rapm_multiliga/examen/beta_corte_<t>.csv.gz`). Ese ajuste usa tramos, prior y τ con temporadas
  ≤ t. Cada observación es y_s = β̂_s, con varianza c·sd²_s.
- **Estado.** Paseo aleatorio θ_s = θ_{s−1} + η, con η ~ N(0, τ²) por año. Un hueco de k años suma k·τ².
- **Previa de la primera temporada.** N(μ_pos, σ²_pos) por pos3, con la posición del perfil v4.0 de esa temporada.
  [SUPUESTO] No se usa g(x̃) como previa porque el β observado ya lo lleva dentro (peso medio del prior ≈ 0,93); usarlo
  lo contaría dos veces.
- **Parámetros.** τ² y c se estiman por máxima verosimilitud de las innovaciones un paso adelante, con las temporadas
  ≤ t de cada corte. El valor filtrado en s sólo usa temporadas ≤ s.

| corte | τ² | c | temporadas por persona (media) |
|---|---|---|---|
| 2021 (calibra) | 1,85 | 1,65 | 1,45 |
| 2022 | 0,57 | 1,68 | 1,95 |
| 2023 | 2,11 | 1,67 | 1,90 |
| 2024 | 2,91 | 1,72 | 2,34 |

[LECTURA] c ≈ 1,7 > 1: la sd de Hutchinson del β v4.0 se queda corta como ruido de observación entre temporadas. τ²
no es estable entre cortes.

## 2. Examen prerregistrado (cortes de decisión 2022–2024)

**[SUPUESTO] Cómo se ha concretado el prerregistro.** Se fijó antes de ejecutar el examen. El nivel de β sí se miró
antes de fijarlo, sin mirar ningún dato de t+1.

- **(a) Spearman.**
  - Filas: jugador-equipo de t+1 con ≥ 300 min y `net_rtg_aj_onoff` (el realizado de F2 v4.1).
  - Predictor: percentil dentro de (liga, temporada t+1), porque β lleva el nivel de la liga y el on/off es relativo al
    equipo.
  - Bootstrap: por equipo-temporada, como en F2 v4.1.
- **(b) MAE.**
  - Población: personas con β en t y en t+1 y ≥ 300 min (perfil v4.0, todas sus ligas) en las dos temporadas.
  - Objetivo: el β v4.0 publicado de t+1 (`rapm_multiliga/<t+1>.csv.gz`).
  - Bootstrap: por persona.
  - Alineación de escala: cada predictor se pasa a la escala del objetivo con a + b·β, ajustado en la temporada t. La
    misma transformación se aplica a los dos predictores.
  - Por qué hace falta alinear [DATO]: el nivel global de β no está identificado por los tramos y cambia entre ajustes.
    Por ejemplo, la media de 2022-23 es −0,10 en el corte 2022 y +3,78 en el producto. Sin alinear, el MAE mediría ese
    desfase y no el método.
- B = 2000 en los dos bootstraps.

| corte | n Spearman | ρ v4.0 | ρ v4.2 | Δρ IC95 | n MAE | MAE v4.0 | MAE v4.2 | ΔMAE IC95 | cob. 80 % v4.2 |
|---|---|---|---|---|---|---|---|---|---|
| 2021 (calibra) | 1883 | 0,194 | 0,197 | [−0,007; 0,013] | 1440 | 2,009 | 2,086 | +0,077 [0,033; 0,122] | 0,882 |
| 2022 | 2140 | 0,194 | 0,178 | [−0,034; 0,001] | 1645 | 1,964 | 2,040 | +0,076 [0,020; 0,130] | 0,872 |
| 2023 | 3027 | 0,184 | 0,171 | [−0,025; −0,001] | 2352 | 2,431 | 2,306 | −0,125 [−0,170; −0,080] | 0,887 |
| 2024 | 3076 | 0,173 | 0,169 | [−0,017; 0,009] | 2356 | 2,206 | 2,187 | −0,019 [−0,058; 0,024] | 0,898 |
| **conjunto 2022–24** | 8243 | **0,182** | **0,172** | **−0,011 [−0,019; −0,003]** | 6353 | **2,227** | **2,193** | **−0,034 [−0,060; −0,006]** | **0,887** |

**Intervalos (conjunto, informados):**
- Intervalo del 80 % del nivel en t: v4.2 (2·z80·√P_t) mide 4,53 pts/100 y v4.0 (2·z80·sd_t) mide 4,86. La razón
  mediana es **0,94**.
- Cobertura de β_{t+1}:
  - v4.2 predictivo, m_t ± z80·√(P_t + τ² + c·sd²_{t+1}): **0,887**, por encima de [0,75; 0,85].
  - v4.0 tal como se muestra, β_t ± z80·sd_t: 0,623.
  - v4.0 predictivo, β_t ± z80·√(sd²_t + sd²_{t+1}): 0,789.
- Recalibración conformal con 2021 (`motor_v42.recalibracion`):
  - v4.2: k = 0,83, cobertura 0,815 (0,796 / 0,819 / 0,824 por corte), anchura mediana 7,33.
  - v4.0 predictivo: k = 1,03, cobertura 0,803, anchura 6,98.
  - **[LECTURA]** Con cobertura honesta, el predictivo de β_{t+1} **no** es más estrecho con la v4.2. Lo único más
    estrecho es el rango del nivel.

## 3. Sensibilidades (informadas; no deciden)

| variante | Δρ IC95 | ΔMAE IC95 |
|---|---|---|
| Bootstrap del Spearman por persona | −0,011 [−0,018; −0,003] | — |
| MAE sin alinear la escala | — | +0,123 [+0,093; +0,153] (v4.2 peor; mide el desfase entre ajustes) |
| Objetivo = β del ajuste del corte t+1 (sólo 2022–2023) | — | −0,009 [−0,043; +0,025] (no pasa) |
| Esquema «producto»: Kalman sobre el β publicado (fuga leve por hiperparámetros globales) | −0,014 [−0,022; −0,005] (no pasa a) | +0,012 [−0,016; +0,042] (no pasa b) |

Además, con el β crudo (sin percentil de liga) el ρ queda en 0,071 (v4.0) y 0,062 (v4.2).

**[LECTURA]** La mejora del MAE depende de un solo corte (2023) y de la especificación: en 2022 la v4.2 empeora con
IC95 que excluye 0, y ninguna sensibilidad pasa (b). El orden frente al on/off realizado empeora de forma pequeña pero
consistente: el filtro arrastra temporadas antiguas cuando el jugador cambia de verdad.

## 4. Decisión y consecuencias

- **[DECISIÓN] El β v4.2 pasa el examen prerregistrado** en la especificación principal, (a) y (b). Por la regla de
  versión de `configs/v42.yaml`, sustituye al β v4.0 como β de la capa 1. Se informa de su fragilidad (§3).
- **[DATO] NIVEL KERNO no usa β:** es el percentil de la contribución del motor v3.3 (`anclas.nivel_cerno_examen`).
  D2-β **no lo cambia**. Sólo cambiaría con `entradas_motor_v42` (otra pieza de D2).
- **[LECTURA] Estimación para IMPACTO**, sin reconstruirlo. IMPACTO (capa 4 v4.0) y el Impacto en pista (v4.1) toman el
  «β más reciente ≤ t» con `Insumos.valor` (`bbequipo/equipo.py`, `bbequipo/ecosistema/impacto_pista.py`). Con β v4.2:
  - El componente β del percentil se mueve poco. Spearman entre percentiles v4.0 y v4.2 dentro de liga: 0,933.
    Cambio mediano de 3,9 puntos de percentil; p90 de 17,2; el 24 % de los jugadores se mueve más de 10 puntos.
  - La sd de β baja un 6 % (mediana).
  - La monotonía del β solo frente al on/off baja unos 0,011. Como el aditivo p·β es el término dominante del Δ̂Net, lo
    esperable es un IMPACTO con un Spearman ligeramente **menor**, no mayor que el 0,149 de referencia.
  - **Recomendación:** no propagar β v4.2 a IMPACTO salvo que pase el examen de IMPACTO.
- **Qué haría falta para reconstruir IMPACTO:**
  1. Escribir m_t y √P_t (+ τ²·hueco para quien no juega en t) con el esquema de `beta_corte_<t>` (2021–2024) y por
     temporada para el producto, en `data/modelos/v4_2/beta/`.
  2. Añadir a `Insumos` (equipo.py e impacto_pista.py) la ruta del β por configuración; hoy está fija a
     `rapm_multiliga`.
  3. Volver a ejecutar F4 (calibración c_cal), el examen IM de F5 (Monte Carlo de 200 simulaciones por fichaje: horas
     por corte) y el F2 de la v4.1.
  4. Volver a exportar el campo `b` del atlas.
  - Coste estimado: medio día de cálculo y una tarde de código, más el examen de IMPACTO como puerta.

## 5. Dudas

- La concreción del objetivo del MAE (β publicado de t+1 con alineación lineal) es mía, no está escrita en el
  prerregistro. Las variantes razonables que no la usan no pasan (b).
- El β v4.0 de cada temporada ya contiene el RAPM de t−1 en su prior, así que las observaciones del Kalman no son
  independientes. El c ≈ 1,7 absorbe parte de eso, pero no lo modela.
- La cobertura predictiva sin recalibrar (0,887) queda fuera de [0,75; 0,85]. Para el β el prerregistro no la exige,
  pero haría falta el conformal de 2021 antes de mostrar rangos.

## 6. Cómo reproducir

```
python -m bbequipo.v42.beta        # ≈ 1 min; escribe data/modelos/v4_2/beta/examen_d2_beta.json, filas_mae.csv.gz, filas_spearman.csv.gz
```

Semilla 20261109 (+ corte / + índice de la prueba).
Insumos (sólo lectura):
- `data/modelos/v4_0/rapm_multiliga/examen/beta_corte_<t>.csv.gz`
- `data/modelos/v4_0/rapm_multiliga/<temporada>.csv.gz`
- `data/modelos/v4_0/perfiles/<temporada>.csv.gz`
- `data/modelos/roles/player_role_season.csv.gz`
