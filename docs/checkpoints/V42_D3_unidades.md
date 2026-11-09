# Checkpoint V42_D3 — CERNO v4.2 · D3 unidades (quintetos, tríos, parejas y sinergia de pareja)

Fecha: 09-11-2026. Prerregistro: `configs/v42.yaml → unidades_v42` (commit d606f47, escrito antes de calcular).
Código: `bbequipo/v42/unidades.py`. Salidas: `data/modelos/v4_2/unidades/`.
Etiquetas: **[DATO]** medido; **[LECTURA]** interpretación; **[SUPUESTO]** decisión de diseño; **[POST HOC]** no prerregistrado.

## 0. Resumen

| Unidad | n (2022–24) | MAE vigente | MAE v4.2 | Δ [IC95] | Cobertura 80 % | EMD | Decisión |
|---|---|---|---|---|---|---|---|
| Quintetos | 61 | 10,19 | 9,59 | −0,59 [−1,35; 0,17] | 0,721 | 1,08 | **se queda la vigente** |
| Tríos | 7.781 | 10,31 | 9,71 | −0,60 [−0,71; −0,48] | 0,802 | 0,16 | **v4.2** |
| Parejas | 12.096 | 9,05 | 8,60 | −0,45 [−0,52; −0,37] | 0,792 | 0,10 | **v4.2** |
| Sinergia de pareja | 12.096 | 10,08 | 7,16 | −2,92 [−3,06; −2,77] | 0,777 | 0,21 | **v4.2** |

[DATO] MAE en puntos por 100 posesiones frente al Net bruto de t+1; IC95 bootstrap por equipo-temporada (B = 2000); EMD =
efecto mínimo detectable (2,8 × error típico bootstrap: 80 % de potencia, α = 0,05).
[LECTURA] Los quintetos fallan por falta de potencia y por cobertura (0,72): sólo 61 quintetos repiten con ≥ 100
posesiones en t y en t+1 en los tres cortes (31 equipos-temporada); el EMD (1,08) es casi el doble del efecto observado.
El examen de quintetos **no tiene potencia** para detectar una mejora del tamaño de la de tríos y parejas.

## 1. Fuentes [DATO]

- `data/processed/<temporada>/quintetos/<liga>/{quintetos,trios,parejas}.csv.gz`, fase `total`, 2020-21 a 2026-27,
  20 ligas (las salidas de `bbstats/lineups`; la Mesa las empaqueta con `bbmodel/mesa_quintetos.py`).
- Versión vigente = `net_rtg_aj` (ORtg y DRtg contraídos hacia el PPP de la liga con k = 300 posesiones;
  `bbstats/lineups/metrics.py`) y, para la sinergia, `sinergia` (WOWY: Net(A+B) − [Net(A sin B) + Net(B sin A) − Net(ninguno)]).
- Lo esperado por los jugadores = `net_esperado` (Σ RAPM propios − Σ RAPM rivales de la temporada, por posesiones).
- Filas unidad-temporada: quintetos 630.192 (48.678 con ≥ 50 posesiones), tríos 968.682 (479.559), parejas 318.708 (234.358).
- Repiten con ≥ 100 posesiones en t y t+1: quintetos 19/29/30/18/13 (t = 2020…2024); tríos 1.390/2.150/2.471/2.840/2.470;
  parejas 1.891/3.091/3.266/4.616/4.214.

## 2. Modelo v4.2 [SUPUESTO]

Kalman por unidad (misma liga y mismos jugadores; la clave no incluye el equipo):
- observación de la temporada s: Net bruto, varianza c·10⁴/posesiones;
- estado: Net verdadero, paseo aleatorio entre temporadas (τ² por año);
- previa de la primera temporada: N(a + b·net_esperado_s, σ0²);
- sinergia de pareja: previa N(a, σ0²); varianza c·10⁴·Σ p/(p+300)² sobre juntos, A sin B, B sin A y ninguno.

a, b, σ0², τ², c por máxima verosimilitud de las innovaciones un paso adelante **de las filas con historial** (predicción
de s con lo visto ≤ s−1), filas ≥ 50 posesiones, temporadas ≤ t. Predicción de t+1 = nivel filtrado en t. Intervalo
predictivo del 80 %: θ̂_t ± κ·z80·√(P_t + τ² + c·10⁴/poss_{t+1}); κ calibrado en el corte 2021 (cuantil 0,80 de |e|/sd:
quintetos 0,755, tríos 0,918, parejas 0,975, sinergia 0,877) y aplicado tal cual a 2022–2024.

Decisiones tomadas mirando **sólo el corte de calibración (2021)**, antes de calcular los cortes de decisión:
1. Primer diseño descartado: la previa a + b·net_esperado_s en todas las temporadas y verosimilitud con todas las
   innovaciones. Daba b > 1 y σ0² → 0: el `net_esperado` de la misma temporada sale del mismo RAPM y «explica» el ruido
   (fuga dentro de la temporada). Por eso la verosimilitud usa sólo predicciones fuera de muestra.
2. Suelo de 50 posesiones para entrar en el filtro (colas imposibles con 25: un quinteto a −395 con 56 posesiones).
3. Los quintetos tienen 37 filas con historial en el corte 2021 y la verosimilitud degenera (σ0² = τ² = 0, c ≈ 27).
   Toman los hiperparámetros de los tríos del mismo corte.

## 3. Decisión

- **Tríos, parejas y sinergia de pareja: pasa la v4.2** (MAE mejor con IC95 que excluye 0 en el conjunto; cobertura en
  [0,75; 0,85]). También mejoran en cada corte por separado [DATO, `examen_d3.json → cortes`].
- **Quintetos: se mantiene la vigente** (Net corregido por muestra, k = 300), como manda `si_no_pasa`. Hay que informar
  al CEO de que el examen no tenía potencia.

## 4. Lo que hay detrás de la mejora [POST HOC]

Cortes 2022–2024 en conjunto (cálculo aparte con `cargar`, `hiperparametros` y `filtrar` del módulo; no está en el examen):
- **Sinergia de pareja:** la correlación entre la sinergia de t y la de t+1 es 0,012. La v4.2 la contrae casi entera
  hacia −0,4 (MAE 7,16, igual que predecir 0). [LECTURA] La sinergia WOWY de una temporada no se repite; la v4.2
  «pasa» porque dice honestamente que no hay señal, no porque la encuentre.
- **Tríos y parejas:** lo esperado por sus jugadores (a + b·net_esperado_t), sin el Net propio ni el historial, da casi el
  mismo MAE (tríos 9,66 frente a 9,71; parejas 8,59 frente a 8,60). Con historial la mejora es parecida a sin historial
  (tríos −0,51 frente a −0,62; parejas −0,40 frente a −0,47). Con los parámetros finales, una pareja con 557 posesiones
  pesa su temporada un 9 %. [LECTURA] La ganancia viene de contraer hacia lo que predice el RAPM de sus jugadores, no
  de la «memoria» de la unidad. La v4.2 de tríos y parejas es, en la práctica, «Net esperado por sus jugadores, calibrado».
- `net_esperado` usa el RAPM de la misma temporada t, que también ve las posesiones de la unidad. No hay fuga hacia t+1,
  pero el «esperado» no es independiente de lo observado en t.

## 5. Formato para el exportador (sólo los tipos que pasan)

- `data/modelos/v4_2/unidades/{trios,parejas,sinergia_pareja}_v42.csv.gz`: una fila por unidad-temporada con ≥ 50
  posesiones, fase total, 2020-21 a 2026-27. Columnas:
  - `liga, temporada, team_id, unidad`: `unidad` son los ids de jugador ordenados y unidos por «|», el mismo formato
    que la columna `unidad` de bbstats;
  - `poss`;
  - `observado`: Net bruto, o sinergia para `sinergia_pareja`;
  - `vigente_v41`: `net_rtg_aj` o `sinergia`;
  - `esperado_jugadores`: a + b·net_esperado;
  - `v42, v42_lo, v42_hi`: nivel y rango del 80 % del nivel, θ ± z80·√P, con temporadas ≤ s;
  - `previa_m, previa_sd`: estado antes de ver la temporada;
  - `temporadas_previas`;
  - `peso_temporada`: ganancia de Kalman, el peso de la propia temporada.
- `parametros_v42.json`: a, b, σ0², τ², c y κ ajustados con las temporadas cerradas (2020–2025).
- Para la temporada en curso, el navegador puede actualizar con los datos cargados. Con la previa (`previa_m`, `previa_sd`;
  si la unidad es nueva, a + b·net_esperado y σ0) y la observación y (varianza c·10⁴/poss):
  m = previa_m + g·(y − previa_m), con g = P⁻/(P⁻ + c·10⁴/poss).
  [SUPUESTO] El rango del nivel no lleva κ: el examen valida el intervalo predictivo de t+1, no el del nivel.
- Tamaño: unos 24 MB. Para el artifact convendría filtrar a lo que ya muestra la Mesa (los 20 tríos con más minutos
  por equipo y parejas con 40 minutos o más).

## 6. Cómo reproducir

```
PYTHONPATH=. python -m bbequipo.v42.unidades examen      # → examen_d3.json (≈ 1,5 min; no sobrescribe)
PYTHONPATH=. python -m bbequipo.v42.unidades exportar    # → <tipo>_v42.csv.gz y parametros_v42.json (≈ 1 min)
```
Semilla del bootstrap 20261109. `bbequipo/v42/__main__.py` no se ha tocado: es de D1.

## 7. Dudas abiertas

- La identidad de unidad entre temporadas depende de que los ids de jugador sean estables en cada liga. Las ligas FEB y
  NCAA no se han comprobado.
- Con más datos cambian bastante los hiperparámetros: los tríos tienen σ0² entre 0 y 9,5 y τ² entre 19 y 51 según el corte. Conviene
  reajustarlos con cada temporada cerrada.
- Si el CEO quiere quintetos con historial, harían falta más temporadas o un modelo jerárquico que los ligue a sus
  tríos y parejas. Esto no estaba prerregistrado.
