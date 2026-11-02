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

## 2. Cambios (decididos con el usuario el 02-11-2026)

- **A1 · pasos que se pueden apagar** (`pasos`):
  - redistribución del uso (suma fija);
  - curva uso-eficiencia β;
  - efecto de la calidad de compañeros b;
  - adaptación;
  - ruido personal y de muestreo.

  *Regla de la navaja:* el paso se quita si quitarlo no empeora de forma significativa (intervalo del 90 % bootstrap
  por club de destino, pareado) el error de pts/100 ni el de TS%, ni el de minutos ni el acierto de rol. El ruido
  personal solo forma los intervalos, así que además se exige que no empeore la puntuación de intervalo del 90 %
  (Winkler) tras la recalibración A4.
- **A3 · factores sobre el TS%.** TS' = TS + k_β·β·ΔUSG + k_c·b·ΔL̄. La rejilla k ∈ {0; 0,25; 0,5; 0,75; 1} se calcula
  sobre las MISMAS simulaciones de cada fichaje (mismos minutos, uso y ruido), así que todas las combinaciones salen
  de una sola ejecución. k = 0 equivale a apagar el paso (A1).
- **A2 · producción del Atlas.** Es la producción de la línea base «a»: valor normalizado + contexto con β si es
  claro, traducido con el tipo de cambio lineal. Los minutos y el rol siguen siendo los del motor.
- **A2 frente a A3.** Gana el de menor media de MAE_pts/MAE_pts(v3.1) y MAE_TS/MAE_TS(v3.1). En caso de empate, el
  motor.
- **A4 · recalibración conforme** de los intervalos del 50 % y del 90 % de producción y minutos:
  - factor por métrica × grupo de destino (a la EuroLeague, FEB, NBA/G League, resto), si el grupo tiene ≥ 30 casos;
    si no, el de la métrica;
  - el factor es el que habría cubierto lo nominal en los cortes anteriores;
  - para la producción sin intervalo propio (A2), la semiamplitud es el cuantil del error absoluto.
- **Vara de destino.** Con `destino.vara: destino`, la incertidumbre de la traducción usa la varianza propia del
  jugador más Var(δ_o − δ_d), con la covarianza conjunta de los niveles (docs/normalizacion_v32.md §5). En la v3.1 se
  sumaban las dos varianzas frente a la EuroLeague. La liga de destino queda a 0.
- **Capacidad de los jugadores.** Viene de la normalización v3.2 (fuente «V32»: mismas constantes lineales que la
  v3.1, recalculadas sobre la v3.2).

## 3. Cortes anidados

- Lo que se aplica en el corte t (2021-22 … 2024-25) se decide con los cortes anteriores. El primero usa la v3.1 tal
  cual.
- La decisión final, la del simulador publicado, usa todos los cortes. Se escribe en `decisiones_v32.json` y se fija
  en la configuración: `pasos`, `factor_ajustes_ts`, `v32.produccion_publicada` y `v32.aplicar_recalibracion`.
- Limitación: si se quitan los dos pasos con ejecución propia (uso y adaptación), el examen no tiene la combinación y
  usa la del primero.

## 4. Resultados

*(se completan al terminar el examen)*
