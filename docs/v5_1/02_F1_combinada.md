# v5.1 · F1 · Versión combinada v5 / v3.2

Fecha: 13-11-2026 · Kerno Analytics · encargo v5.1 (`docs/v5_1/00_encargo_v5_1.md`).

**Código**
- `bbnorm5/salidas/combinada.py`: pesos, examen y generación.
- `bbnorm5/salidas/formato_v32.py`: `normalizado(..., dir_salida, pesos)` y `combinar`.
- `bbnorm5/v51.py`.

**Configuración.** `configs/v5_1/f1.yaml`, con la regla de pesos y la de publicación fijadas antes del examen.

**Salidas.** `data/v5_1/salidas/combinada/`.

**Tests.** `tests/v5_1/test_combinada.py` (3).

```bash
python -m bbnorm5.v51 --config configs/v5_1/f1.yaml --pasos examen generar      # ≈ 2 min
```

Etiquetas: **DATO**, **LECTURA**, **SUPUESTO**, **RIESGO**, **VERIFICAR**.

---

## Informe de auditoría · v5.1 · Fase F1 · Versión combinada

### Resumen ejecutivo

**La versión combinada cumple su regla de publicación y queda lista para el artifact.**
- En el examen de la F1, fuera de muestra:
  - −2,9 % de error (WIS) frente a la v3.2 publicada [IC 95 % −3,5 %, −2,3 %];
  - −4,6 % frente a la v5 sola;
  - cobertura del 80 % en 0,803.
- Mejora o empata en 19 de 20 métricas. La excepción es BLK% (+1,1 %).
- Las tablas por temporada tienen el formato exacto de la v3.2, con las 26 métricas, incluidas las tres zonas que la F9
  dejaba en la v3.2.
- La v5 y la v3.2 se conservan en columnas propias.

---

## 1. Qué se hizo

1. **Mezcla.** En cada métrica, Q_comb(u) = w·Q_v5(u) + (1 − w)·Q_v3.2(u). Es un promedio de cuantiles: el centro y
   los extremos del 80 % se mezclan con el mismo peso.
2. **Pesos (regla fijada antes).**
   - ŵ minimiza el WIS del examen de la F1 en la rejilla {0; 0,1; …; 1}.
   - Se contrae hacia la mezcla al 50 % según el número de casos: w = 0,5 + n/(n + 300)·(ŵ − 0,5).
   - Las métricas sin examen (faltas) usan 0,5.
   - Las variantes por 100 posesiones heredan el peso de su métrica base.
3. **Examen fuera de muestra.** Cada corte de prueba (2023, 2024) fija los pesos sólo con los anteriores. 12.669 casos
   y 789 personas en 20 métricas, las 19 modeladas y las derivadas TS% y eFG%.
4. **Publicación.** Pesos con todos los cortes; `formato_v32.normalizado` con `pesos`.
   - En cada fila y métrica con v5 y v3.2: centro, `_lo` y `_hi` combinados; percentil recalculado frente a la
     EuroLeague de su puesto.
   - Columnas nuevas: `fuente_<m>` = COMB, `peso_v5_<m>`, la v5 en `<m>_v5*` y la v3.2 en `<m>_v32*`.
   - Sin v3.2 queda la v5 (faltas y unas 118 filas por temporada); sin v5 queda la v3.2.

## 2. Resultados (DATO)

### 2.1 Examen de la F1 (2023 y 2024, pesos con los cortes anteriores)

| Versión | WIS frente a la v3.2 | IC 95 % | WIS frente a la v5 | Cobertura 80 % |
|---|---|---|---|---|
| v3.2 publicada | 0 | — | −1,8 % | 0,809 |
| v5 publicada | +1,8 % | [+0,6, +3,0] | 0 | 0,761 |
| **Combinada (regla)** | **−2,9 %** | **[−3,5, −2,3]** | **−4,6 %** | **0,803** |
| Mezcla al 50 % (sin ajustar) | −2,9 % | [−3,5, −2,3] | −4,6 % | 0,802 |

**Decisión** (regla de `f1.yaml`): mejora a la v3.2 con IC < 0 **y** cobertura en [0,76, 0,84] → **se publica**.

### 2.2 Por métrica (frente a la v3.2; cobertura del 80 % de la combinada)

| Métrica | Peso v5 publicado | v5 | Combinada | Cobertura |
|---|---|---|---|---|
| Pts/100 | 0,58 | −13,2 % | −10,8 % | 0,84 |
| USG% | 0,58 | −3,7 % | −6,1 % | 0,81 |
| AST% | 0,57 | −3,0 % | −5,0 % | 0,85 |
| DREB% | 0,50 | −2,5 % | −4,8 % | 0,79 |
| FTr | 0,58 | −3,5 % | −4,9 % | 0,82 |
| % asistidas | 0,50 | −3,0 % | −4,5 % | 0,83 |
| TS% | 0,58 | −0,5 % | −4,4 % | 0,81 |
| 3PAr | 0,50 | −0,7 % | −4,1 % | 0,83 |
| TL% | 0,50 | −0,3 % | −3,5 % | 0,80 |
| eFG% | 0,50 | +1,9 % | −3,3 % | 0,80 |
| TOV% | 0,42 | +0,9 % | −3,3 % | 0,82 |
| T2% | 0,42 | +3,7 % | −1,8 % | 0,80 |
| OREB% | 0,44 | +2,6 % | −1,8 % | 0,81 |
| % tiros cortos | 0,42 | +2,7 % | −1,7 % | 0,81 |
| % en el aro | 0,42 | +4,3 % | −1,5 % | 0,86 |
| Robos/100 | 0,41 | +3,5 % | −1,3 % | 0,78 |
| % triple de esquina | 0,35 | +8,8 % | −1,1 % | **0,73** |
| % media distancia | 0,27 | +6,4 % | −0,8 % | 0,78 |
| T3% | 0,34 | +8,5 % | −0,1 % | 0,80 |
| BLK% | 0,36 | +10,7 % | **+1,1 %** | **0,69** |

### 2.3 Tablas publicadas (`normalizado/<t>.csv.gz`)

- 6 temporadas, 45.670 filas, 121 MB. 2024-25: 9.264 filas, como la v3.2, y 1.178 columnas; no falta ninguna de la v3.2.
- **Origen de las filas en 2024-25:** 7.538 combinadas; 1.608 sólo v3.2 (sin nivel de la v5: pocos minutos o segunda
  liga, F9 §2.5); 118 sólo v5.
- **Anchura mediana del intervalo de nivel del 80 %** (equivalente EuroLeague 2025-26), filas combinadas de 2024-25:

| Métrica | Combinada | v3.2 | v5 |
|---|---|---|---|
| Pts/100 | 6,49 | 6,37 | 6,97 |
| T2% | 8,37 | 8,10 | 8,56 |
| T3% | 6,75 | 6,83 | 6,65 |
| USG% | 4,90 | 4,80 | 5,16 |
| AST% | 5,56 | 5,99 | 5,15 |
| TS% | 6,97 | 7,43 | 6,41 |
| % en el aro | 14,06 | 13,45 | 14,75 |

- **Comprobaciones:**
  - la mezcla reproduce w·v5 + (1 − w)·v3.2 con error < 10⁻⁴ (redondeo);
  - el centro queda dentro de su intervalo en el 100 % de las filas;
  - los percentiles quedan en [0, 100].

## 3. Interpretación (LECTURA)

1. **Combinar gana porque las dos versiones se equivocan en sitios distintos.** La v3.2 viene de la CVAE con todas las
   métricas a la vez y la v5 de la carrera por métrica con traducción entre ligas. Ninguna versión sola llega al −2,9 %.
2. **La regla acaba muy cerca del 50 %.** La contracción hace su trabajo: ninguna métrica tiene casos suficientes para
   alejarse mucho. La v5 pesa más donde ya ganaba (uso, creación, pts/100) y menos en tiro y zonas, donde perdía.
3. **Las zonas vuelven a publicarse con la v5 dentro y ya no pierden frente a la v3.2.** La v5 sola perdía entre un
   4 % y un 9 %, lo que llevó a dejarlas en la v3.2 en la F9. Combinadas, ganan entre un 0,8 % y un 1,7 %. La
   decisión 2 de la F9 queda superada.
4. **BLK% y el triple de esquina siguen cubriendo de menos** (0,69 y 0,73). Lo heredan de la v5 en sucesos raros, ya
   señalado en la F8 y la F9.

## 4. Supuestos (SUPUESTO)

1. **Mismos pesos para el predictivo y el nivel.** Se examinan con el predictivo (temporada siguiente, examen de la F1)
   y se aplican igual a los intervalos de nivel de las tablas. Para el nivel no hay examen directo, porque el nivel no
   se observa.
2. **Promedio de cuantiles** (Vincent) y no mezcla de distribuciones. Mantiene la forma y la anchura entre las dos, y
   no ensancha por la discrepancia entre versiones.
3. **El percentil se recalcula** con el centro combinado, frente a la EuroLeague del mismo puesto (como la v3.2).

## 5. Riesgos y verificaciones pendientes (RIESGO · VERIFICAR)

1. **RIESGO · infracobertura en BLK% y triple de esquina.** Propuesta para la F2: recalibrar su anchura con los cortes
   anteriores, como en la F9 por grupo.
2. **VERIFICAR · draws y destinos combinados.** Esta fase combina las tablas normalizadas (equivalente EuroLeague). La
   proyección por liga de destino y sus draws se combinan en la F2, con la producción del simulador. El examen de
   fichajes de la F10 bis da ahí −8,2 % frente a la v3.3.
3. **RIESGO · volumen.** 121 MB más en el repositorio. Las tablas del artifact (F6) sólo necesitan las columnas del
   esquema v1.

## 6. Verificación de no regresión

- `formato_v32.normalizado` sin `pesos` ni `dir_salida` se comporta igual que antes (tests de la F9 en verde).
- Nada de la v1, la v3.2, la v3.3, la v4.x ni de los artifacts cambia.
- Suite completa: **391 passed**.

## 7. Siguiente fase

**F2 · Simulador** (`00_encargo_v5_1.md` §2):
- producción con draws combinados por liga de destino;
- ensamblaje con dependencia estimada (minutos–producción, métricas, compañeros, liga-temporada);
- índice L sin las métricas que faltan;
- reentrenar el GBM de minutos;
- examen V32_corte por jugador y por equipo frente a lo reproducido en la F0.

Esperando GO.
