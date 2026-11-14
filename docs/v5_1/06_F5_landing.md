# v5.1 · F5 · Landing: primer y segundo año en una liga nueva

Fecha: 14-11-2026 · Kerno Analytics · encargo v5.1 (`docs/v5_1/00_encargo_v5_1.md`), con la ampliación del usuario
(F10 bis §13.2: adaptación de los americanos a Europa).

**Código.** `bbnorm5/simulador51/landing51.py`, sobre la Landing de la F10 (`bbnorm5/aguas_abajo/landing.py`).

**Salidas.** `data/v5_1/landing/`.

**Tests.** `tests/v5_1/test_simulador51.py` (contracción latente).

```bash
python -m bbnorm5.v51 --config configs/v5_1/f2.yaml --pasos landing      # ≈ 5 min
```

Etiquetas: **DATO**, **LECTURA**, **SUPUESTO**, **RIESGO**, **VERIFICAR**.

---

## Informe de auditoría · v5.1 · Fase F5 · Landing

### Resumen ejecutivo

**La Landing se publica como lectura, no como corrección.**
- **Contracción a través del perfil latente.** Las celdas identificables pasan de 72 a 191 de 410.
- **Americanos de NBA/G League a Europa:**
  - primer año: más uso (pts/100 +1,6, USG% +0,8) y menos tiro asistido (−6,1) y de tres (3PAr −3,9);
  - segundo año: mejora más de lo previsto (T2% +1,9 puntos, pts/100 +1,1, TOV% −0,8).
- **Como corrección de la proyección, no pasa el examen fuera de tiempo en ningún grupo.**
  - Segundo año de EE. UU. → Europa: −1,0 % [−3,1 %, +1,4 %], con 9 jugadores en la cohorte de prueba.
  - Primer año: empeora en todos, porque la traducción publicada ya lo recoge.
- **El escalón del Nivel Kerno (NK₂ − NK₁) no se valida.** El modelo prevé +4 puntos en el segundo año de los
  americanos. En los 16 que tienen segunda temporada, el percentil realizado bajó 6.
- **Por tanto,** NK₂ = NK₁ (sin escalón), y la Landing es una lectura con su rango y sello BAJA.

---

## 1. Qué se hizo

1. **δ por métrica, grupo y fase** (F10 bis):
   - **primer año:** residuo frente a la carrera con la traducción de los puentes;
   - **segundo año:** residuo en la misma liga, sin traducción;
   - en los dos, ajustados por quienes no cambian en la misma liga-temporada.

   Grupos: los 10 de la Landing vigente, con nacionalidad por persona.
2. **Contracción a través del perfil latente.**
   - En cada grupo y fase, los δ de las 14 métricas con cargas en la F5 (factores estables z2, z3 y z5) se ajustan por
     mínimos cuadrados ponderados a Λγ.
   - La desviación propia de cada métrica (τ², por momentos) decide cuánto se contrae hacia Λγ̂.
   - Zonas y % asistidas, sin cargas, se quedan con su δ.
3. **Examen de publicación** (fuera de tiempo, como en la F10 bis): δ contraído con las temporadas anteriores, aplicado a
   la proyección publicada de la siguiente.
4. **Escalón en puntos del Nivel Kerno.**
   - En los fichajes del examen de la F3: el NK del segundo año (pts/100 + δ₂ de su grupo, con los mismos minutos) menos
     el NK del primero.
   - Contraste con el percentil realizado en la segunda temporada, en la misma liga, con 300 min o más.

## 2. Resultados (DATO)

### 2.1 Identificabilidad (semiancho del IC 95 % ≤ 0,10 DT)

| Estimación | Celdas identificables (de 410) |
|---|---|
| δ directo por métrica | 72 |
| δ contraído a través del perfil latente | **191** |

### 2.2 Americanos de NBA/G League a Europa (DT del residuo, IC 95 %; en la escala de la métrica)

| Métrica | Primer año (contraído) | Segundo año (contraído) |
|---|---|---|
| Pts/100 | +0,27 [+0,12, +0,42] · +1,6 | **+0,25 [+0,06, +0,45] · +1,1** |
| USG% | +0,21 [+0,05, +0,36] · +0,8 | +0,12 [−0,08, +0,31] · +0,4 |
| T2% | −0,02 [−0,23, +0,18] | **+0,34 [+0,15, +0,53] · +1,9** |
| TOV% | +0,25 [+0,05, +0,44] · +0,8 | **−0,26 [−0,46, −0,06] · −0,8** |
| 3PAr | −0,34 [−0,49, −0,20] · −3,9 | −0,44 [−0,64, −0,24] · −3,5 |
| % canastas asistidas | −0,52 [−0,71, −0,33] · −6,1 | −0,26 [−0,54, +0,01] · −2,3 |
| AST% | +0,03 [−0,13, +0,18] | −0,01 [−0,20, +0,18] |

228 personas en el primer año y 42 en el segundo.

### 2.3 Examen de publicación (WIS con δ contraído frente a sin δ; ninguno con IC < 0)

| Grupo | Fase | Personas | WIS con δ | IC 95 % |
|---|---|---|---|---|
| EE. UU. NBA/GL → Europa | primer año | 102 | +1,2 % | [−0,2, +2,5] |
| Todas las llegadas pro de EE. UU. → Europa | primer año | 136 | +1,7 % | [+0,5, +3,0] |
| EE. UU. NBA/GL → Europa | segundo año | 9 (2025) | −1,0 % | [−3,1, +1,4] |
| Todas las llegadas pro de EE. UU. → Europa | segundo año | 16 (2025) | −0,2 % | [−3,4, +3,3] |
| NCAA → profesional | segundo año | 120 | +0,3 % | [−0,7, +1,1] |
| Europeo que cambia de liga | segundo año | 76 | +0,8 % | [+0,2, +1,4] |

### 2.4 Escalón en puntos del Nivel Kerno (crudo, F_ref)

| Grupo | Fichajes | δ₂ de pts/100 | Escalón previsto | Fichajes con 2.º año | Cambio realizado del percentil |
|---|---|---|---|---|---|
| EE. UU. NBA/GL → Europa | 102 | +1,10 | **+4,0** | 16 | **−6,1** |
| NCAA → profesional | 142 | −0,47 | −1,7 | 57 | +10,2 |
| Nacional en su país | 958 | −0,07 | −0,4 | 296 | +0,5 |
| Sin nacionalidad | 572 | +0,01 | +0,1 | 203 | +1,3 |
| Europeo que cambia de liga | 157 | +0,08 | +0,5 | 50 | −3,6 |

Correlación de rangos del NK₁ con el percentil realizado en la segunda temporada: 0,50 (919 fichajes).

## 3. Interpretación (LECTURA)

1. **La adaptación de los americanos existe en los datos y tiene forma.**
   - El primer año: cambio de papel, con más uso y más tiro propio.
   - El segundo: mejora de eficiencia (T2% y pérdidas). Coincide con la literatura externa que citaste.
   - La contracción latente la deja con IC más estrechos sin cambiar su signo.
2. **Pero no mejora ninguna predicción.** Ni el examen fuera de tiempo ni el segundo año realizado la confirman.
   - El primer año ya lo recoge la traducción publicada.
   - El segundo año tiene muy pocos casos fuera de muestra (9–16) y la única cohorte de prueba (2025) es la que no
     mostraba el efecto.
   - El cambio realizado del percentil (−6 en 16 americanos) mezcla eficiencia con minutos y con quién se queda en la
     liga.
3. **El NCAA → profesional va en el sentido contrario a lo previsto** (+10 realizado frente a −2). Sin el NCAA en los
   puentes de la misma temporada, su primer año no se identifica (F10 §2.5) y el segundo arrastra esa incertidumbre.

## 4. Decisión (regla del encargo v5.1 §3.3)

- **Ninguna proyección se corrige con δ.** Ni la producción, ni el NK, ni el simulador.
- **NK₂ = NK₁:** la Landing deja de ser un escalón entre dos números NK, que hoy es ≈ 0 en la v3.1 y no se valida en la
  v5.1.
- **La Landing se publica como lectura**, con su IC y sello BAJA, por grupo:
  - **perfil del primer año** (§2.2, primera columna);
  - **mejora esperada del segundo año** donde sea identificable (§2.2, segunda columna, para los americanos de NBA/G
    League a Europa), con la nota de la literatura externa y la de que el examen fuera de tiempo aún no la confirma.
- **Revisión** con la cohorte de 2026-27: 2,5 veces más americanos con segundo año observado.

## 5. Supuestos y riesgos

1. **SUPUESTO · escala de la contracción.** Los δ están en DT del residuo de cada métrica y las cargas en unidades
   estandarizadas del perfil latente. Para métricas estandarizadas son comparables, pero la escala relativa entre
   métricas es una aproximación.
2. **SUPUESTO · escalón con los mismos minutos.** Desplaza C en proporción al δ₂ de pts/100. No incluye cambios de rol
   ni de minutos en el segundo año.
3. **RIESGO · muestra del segundo año.** 42 americanos en total y 9–16 fuera de muestra. La lectura del segundo año
   lleva sello BAJA hasta 2026-27.

## 6. Verificación de no regresión

- Sólo lee la Landing de la F10, la F3 y los roles.
- Escribe en `data/v5_1/landing/`.
- Nada publicado cambia.

## 7. Fases que quedan

1. **F6 · Integración y publicación:**
   - selector v3.2 / v5.1 en los tres artifacts (tablas combinadas, simulador, NK, Landing como lectura);
   - botón de actualización y recalibración mensual con el proceso paralelo;
   - PR a la rama de producción y GO para publicar.
2. **F7 · Documentación y cierre** (incluye la F11 de la v5.0): CHANGELOG, artículo científico v5, guía del
   desarrollador y PR final.

Esperando GO a la F6.
