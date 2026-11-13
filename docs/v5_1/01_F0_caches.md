# v5.1 · F0 · Cachés regeneradas y exámenes vigentes reproducidos

Fecha: 13-11-2026 · Kerno Analytics · encargo v5.1 (`docs/v5_1/00_encargo_v5_1.md`).

**Guiones.** `scripts/v5_1/F0/`.
- Todos escriben sólo en `experimentos/`, que Git ignora.
- La configuración del simulador se pone en estado de examen **sólo en memoria**. `bbfit.v32.config_examen`
  reescribiría el YAML versionado.
- Las carpetas de salida de `bbequipo/equipo.py` y `bbequipo/anclas.py` se redirigen a `experimentos/v5_1/F0/v40/`.

**Comparación.** `data/v5_1/F0/reproduccion_examenes.json`.

Etiquetas: **DATO**, **LECTURA**, **SUPUESTO**, **RIESGO**, **VERIFICAR**.

---

## Informe de auditoría · v5.1 · Fase F0 · Cachés y contrato

### Resumen ejecutivo

**Las piezas del producto que la v5.1 va a tocar se pueden volver a calcular, y dan lo mismo que lo publicado.**
- **Cachés:** se han regenerado todas las ausentes. Son 80 redes CVAE por corte, el algoritmo A hasta 2021–2023, las
  cachés del simulador por corte y las del RAPM multiliga de la v4.0.
- **Exámenes:** los cuatro vigentes se reproducen con diferencias dentro del ruido. Son el de fichajes del simulador,
  el ΔNet de equipo (F4), el Nivel Kerno y el Impacto.
- **Puertas:** las mismas que en lo publicado (pasan F4 y Nivel Kerno; el Impacto sigue sin pasar la suya literal).

Cualquier cambio en las fases siguientes podrá atribuirse a la v5 y no a la reconstrucción.

---

## 1. Qué se hizo

| Paso | Qué | Dónde | Tiempo |
|---|---|---|---|
| 1 | 79 redes CVAE de los cortes 2021–2024 (20 semillas; ya había 1) | `experimentos/v3/h<año>_d2592cc9db_s<semilla>.pt` | 68 min |
| 2 | Algoritmo A ajustado hasta 2021, 2022 y 2023 (2024 ya estaba) | `experimentos/cache_normalizacion/` | 6–9 min cada uno, en paralelo |
| 3 | Dataset del simulador, cortes V32 (2020-21 a 2025-26) y V32_corte (2021-22 a 2024-25) | `experimentos/cache_simulador_v3_2/` | 9 + 34 min |
| 4 | Examen de fichajes del simulador: V32, V32_corte y V32_corte sin adaptación (para NK₂) | `experimentos/v5_1/F0/validacion/` | 21 + 16 + 15 min |
| 5 | RAPM multiliga: tramos y ajustes F1 por corte | `experimentos/v4_0/` | 5–46 min por corte; 2024: §4 |
| 6 | Examen de equipo F4, Nivel Kerno e Impacto | `experimentos/v5_1/F0/v40/` | 13 min |

**Órdenes descartadas:** reescriben ficheros versionados de `data/` o `configs/`.
- `bbmodel amortiguar --validar`;
- `bbfit backtest`, `v32-decidir`, `v33-decidir` e `historico`;
- `bbequipo rapm-producto`, `equipo-examen` y `anclas-examen`;
- `v32.config_examen`.

## 2. Resultados (DATO)

### 2.1 Simulador v3.2: examen de fichajes (escenario «inicio», con adaptación)

| Medida | V32 publicado | V32 reproducido | V32_corte publicado | V32_corte reproducido |
|---|---|---|---|---|
| Fichajes con minutos | 6.027 | 6.031 | 6.027 | 6.031 |
| MAE de minutos | 4,859 | 4,849 | 4,871 | 4,862 |
| Acierto de rol | 0,428 | 0,434 | 0,427 | 0,434 |
| Log-loss de rol | 1,257 | 1,256 | 1,264 | 1,263 |
| MAE pts/100 | 3,856 | 3,852 | 3,852 | 3,855 |
| Cobertura del 50 % pts/100 | 0,463 | 0,459 | 0,422 | 0,421 |
| Cobertura del 90 % pts/100 | 0,863 | 0,857 | 0,836 | 0,826 |
| MAE TS% | 5,969 | 5,960 | 5,242 | 5,223 |

### 2.2 Modelo de equipo v4.0: examen F4 (ΔNet de la temporada siguiente; cortes de decisión 2022–2024)

| Medida | Publicado | Reproducido |
|---|---|---|
| Transiciones | 933 | 933 |
| MAE del modelo | 4,058 | 4,037 |
| MAE de la persistencia | 4,895 | 4,895 |
| MAE aditivo | 4,055 | 4,040 |
| MAE GBM directo | 4,227 | 4,170 |
| Cobertura del 80 % | 0,765 | 0,763 |
| IC 95 % de la mejora frente a la persistencia | [−1,02, −0,65] | [−1,05, −0,67] |
| Puerta | pasa | pasa |

### 2.3 Nivel Kerno y Impacto

| Medida | Publicado | Reproducido |
|---|---|---|
| Nivel Kerno · fichajes | 4.560 | 4.564 |
| Nivel Kerno · separación (NK ≥ +10 → C mayor) | 70,9 % | 70,9 % |
| Nivel Kerno · cobertura del 80 % | 0,782 | 0,782 |
| Nivel Kerno · anchura del 80 % | 70,2 | 69,9 |
| Nivel Kerno · correlación NK₁–NK₂ | 0,979 | 0,978 |
| Nivel Kerno · puerta | pasa | pasa |
| Impacto · correlación de rangos con el on/off de t+1 | 0,149 [0,117, 0,184] | 0,141 [0,110, 0,174] |
| Impacto · por paquete (ΔNet del equipo) | 0,128 | 0,134 |
| Impacto · puerta | no pasa | no pasa |

## 3. Interpretación (LECTURA)

1. **La maquinaria es la misma.** Todas las diferencias son del orden del ruido de entrenamiento:
   - las redes reentrenadas no son idénticas bit a bit;
   - hay 4 fichajes más por los datos añadidos desde la publicación.

   Ninguna cambia una conclusión ni una puerta.
2. **Las mayores diferencias:**
   - cobertura del 90 % de pts/100 en la V32_corte: −1,0 punto;
   - correlación del Impacto con el on/off: −0,008, con IC que se solapan casi por completo.

   Son la referencia de ruido contra la que se medirán las ganancias de la v5 en las fases siguientes.
3. **Los exámenes de la v5.1 se compararán con estas cifras reproducidas,** no con las publicadas: mismas cachés y
   mismos datos, sólo cambia la v5.

## 4. Supuestos y desviaciones (SUPUESTO)

1. **Ajuste F1 del corte 2024 con la rejilla reducida.** τ ∈ {1, 2, 3} y α = 1, la que usa el producto
   (`configs/equipo_v40.yaml:128-129`).
   - **Por qué:** con la rejilla completa (8 τ × 3 α) dos intentos se cortaron al llegar al límite de 2 h de las
     tareas de fondo.
   - **Elige lo mismo:** τ* = 1, α* = 1 en el bayes empírico, y τ* = 2 tras el GBM, como los cuatro cortes publicados
     y como el primer paso de la rejilla completa en 2024. σ = 187,6 frente a 187,4 publicado.
   - Se guarda con la huella de la configuración completa y una nota al lado (`ajuste_f1_2024_gbm_*.nota.json`).
2. **Tramos del RAPM:** 971.286 frente a 960.245 en la publicación, porque 2026-27 tiene más partidos. Los cortes de
   examen (≤ 2024) no cambian.

## 5. Riesgos y verificaciones pendientes (RIESGO · VERIFICAR)

1. **RIESGO · cachés en un contenedor efímero.** `experimentos/` no está en Git; si la sesión se reinicia en un
   contenedor nuevo, hay que regenerarlas (≈ 3 h con los guiones de `scripts/v5_1/F0/`).
2. **VERIFICAR · cachés de la v3.3** (`cache_simulador_v3_3`): no hacen falta para ningún examen; se regeneran en la F6
   si el histórico de la v3.3 se rehace.

## 6. Verificación de no regresión

- `git status` limpio tras todos los pasos. Ningún fichero de `data/`, `configs/` ni de los artifacts cambió.
- Los exámenes publicados se leyeron sin modificarlos.

## 7. Siguiente fase

**F1 · Versión combinada** (`docs/v5_1/00_encargo_v5_1.md` §2):
- mezcla de cuantiles v5 y v3.2 por métrica con pesos fijados fuera de muestra;
- las 26 métricas, incluidas las tres zonas;
- formato de la v3.2 y draws combinados;
- examen de la F1 y de fichajes reales en cortes no usados para los pesos.

Esperando GO.
