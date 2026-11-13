# v5.1 · F3 · Nivel Kerno con la contribución de la v5.1

Fecha: 13-11-2026 · Kerno Analytics · encargo v5.1 (`docs/v5_1/00_encargo_v5_1.md`).

**Código.** `bbnorm5/simulador51/nivel_kerno.py`. La referencia F_ref, la calibración isotónica y el examen son los de
`bbequipo/anclas.py`, leídos sin modificarlo.

**Salidas.** `data/v5_1/simulador/nivel_kerno_examen.csv.gz` y `meta_nivel_kerno.json`.

```bash
python -m bbnorm5.v51 --config configs/v5_1/f2.yaml --pasos nivel_kerno      # ≈ 3 min, con las cachés de la F0
```

Etiquetas: **DATO**, **LECTURA**, **SUPUESTO**, **RIESGO**, **VERIFICAR**.

---

## Informe de auditoría · v5.1 · Fase F3 · Nivel Kerno

### Resumen ejecutivo

**El Nivel Kerno calculado con la contribución de la v5.1 sustituye al vigente: mejora todo su examen.**

Datos de los cortes 2023-24 y 2024-25, calibrados sólo con cortes anteriores (2.275 fichajes):
- **Correlación de rangos con el percentil realizado:** 0,562 frente a 0,452 (+0,110 [IC 95 % +0,089, +0,129]).
- **Separación de pares:** 73,3 % frente a 69,3 %.
- **Error absoluto medio:** 19,3 puntos frente a 21,6.
- **Rango del 80 %:** 60 puntos frente a 71, con cobertura de 0,79 frente a 0,83.
- **Sello:** distingue bien la fiabilidad alta (error 17,0, correlación 0,66), pero no ordena media y baja entre sí.

---

## 1. Qué se hizo

1. **Contribución.** C = minutos del motor (recalibrados) × pts/100 combinados, con las dependencias y la calibración
   final de la F2. 2.000 draws por fichaje.
2. **NK** = 100·E[F_ref(C)]: F_ref es la del vigente (liga de destino × puesto, 3 temporadas ≤ t, ponderada por
   minutos). La calibración isotónica (NK crudo → percentil realizado) usa los cortes anteriores; el primero se calibra
   con el suyo y queda fuera del examen.
3. **Tres lecturas:**
   - **número frontal:** el NK predictivo calibrado;
   - **rango del año:** cuantiles 10–90 del percentil realizado por decil de NK, como el vigente;
   - **rango de nivel:** F_ref en los cuantiles 10 y 90 de C con los minutos esperados y el **nivel** de pts/100, sin
     el ruido de la temporada. El centro es el de la producción combinada y la anchura, la del nivel de la v5.
4. **Sello** de la F9 sobre pts/100 en la liga de destino, con datos ≤ t: exposición acumulada frente a n*, temporadas
   de historial y conectividad del par de ligas.
5. **Comparación** con el NK vigente reproducido en la F0, en los mismos fichajes (2.952 en los tres cortes; 2.275 en la
   prueba).

## 2. Resultados (DATO)

### 2.1 Examen (prueba: cortes 2023-24 y 2024-25)

| Medida | NK vigente (reproducido) | NK v5.1 predictivo | NK v5.1 de nivel |
|---|---|---|---|
| Correlación de rangos con el percentil realizado | 0,452 [0,415, 0,486] | **0,562** [0,530, 0,594] | 0,556 [0,523, 0,589] |
| Diferencia con el vigente | — | **+0,110** [+0,089, +0,129] | +0,104 [+0,082, +0,126] |
| Separación (NK ≥ +10 → C mayor) | 69,3 % [66,8, 71,7] | **73,3 %** [71,0, 75,2] | 73,7 % [71,4, 75,7] |
| Cobertura del rango del 80 % | 0,828 | **0,793** | 0,796 |
| Anchura del rango del 80 % | 71,2 | **59,9** | 61,4 |
| Error absoluto medio | 21,6 | **19,3** | 19,4 |

Con los tres cortes (2.952 fichajes): correlación 0,580 frente a 0,480 y separación 73,7 % frente a 69,9 %.

**Rangos sin calibrar** (en F_ref):
- rango de nivel: 30 puntos de media;
- rango del año: 67.

### 2.2 Por sello (prueba)

| Sello | Fichajes | Error absoluto | Correlación de rangos | Cobertura 80 % | Rango de nivel |
|---|---|---|---|---|---|
| Alta | 590 | **17,0** | **0,66** | 0,85 | **22** |
| Media | 1.001 | 20,5 | 0,48 | 0,77 | 34 |
| Baja | 684 | 19,6 | 0,54 | 0,78 | 34 |

**Decisión** (encargo v5.1 §3.2): mejora su propio examen con IC que no cruza 0 y la cobertura no empeora: 0,79, más
cerca de 0,80 que 0,83. → **Sustituye al vigente.**

## 3. Interpretación (LECTURA)

1. **La mejora del NK es la de la contribución.** Con la misma referencia y calibración, ordenar mejor la contribución
   por partido es ordenar mejor el NK. Respecto a la F10 (+0,10) se mantiene, ahora con la producción combinada
   publicable y el ensamblaje calibrado.
2. **El NK de nivel ordena casi igual que el predictivo** (0,556 frente a 0,562). Puede acompañar al número frontal sin
   contradecirlo. Su rango (30 puntos) dice cuánto vale el jugador. El rango del año (60 calibrado) dice lo que puede
   pasar esa temporada, sobre todo por los minutos.
3. **El sello alto funciona.** Separa a los jugadores con mucha exposición y conexión de ligas buena: menos error, mejor
   orden y la mitad de rango de nivel. Entre media y baja no hay diferencia. La regla de la baja (poca exposición o mala
   conectividad) no captura lo que más pesa aquí, que son los minutos. **VERIFICAR** antes de publicar tres niveles: el
   sello del NK podría ser de dos niveles (alta / resto), o añadir la incertidumbre de los minutos.

## 4. Supuestos (SUPUESTO)

1. **F_ref, puesto y calibración** son los del NK vigente. Sólo cambia la contribución.
2. **El rango de nivel** usa la anchura del nivel de pts/100 de la v5. La v3.3 no publica nivel de producción en
   destino.
3. **El sello** usa la regla de la F9 sobre pts/100, la métrica de la contribución.

## 5. Riesgos y verificaciones pendientes (RIESGO · VERIFICAR)

1. **VERIFICAR · sello de tres niveles** en el NK (§3.3).
2. **RIESGO · población.** El examen usa fichajes con 300 min o más en destino, como el vigente con su `eval`. El producto
   publica NK para todos: la calibración isotónica del vigente ya absorbe la diferencia (F5 de la v4.0) y se mantiene.
3. **NK₂ (sin adaptación) y la Landing** se rehacen en la F5 con los efectos de la primera y la segunda temporada.

## 6. Verificación de no regresión

- `bbequipo/anclas.py` se lee sin modificarlo.
- Nada de `data/modelos/` ni de los artifacts cambia.
- Suite: los tests de `tests/v5_1/` pasan (6).

## 7. Siguiente fase

**F4 · Impacto:**
- prior del RAPM multiliga con el perfil de nivel y la traducción de la v5;
- interceptos de liga desde los puentes;
- Impacto con rango propagado;
- examen del IMPACTO vigente reproducido en la F0 (correlación con el on/off de t+1, 0,141) y RAPM de t+1 en quien
  cambia de liga.

Esperando GO.
