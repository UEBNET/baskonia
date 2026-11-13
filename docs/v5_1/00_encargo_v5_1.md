# Encargo v5.1 · La v5 en el producto: simulación, Nivel Kerno, Impacto y Landing

Versión 1.0 · 13-11-2026 · Kerno Analytics.

**Origen.**
- Puerta de la F10 de la v5.0 (`docs/v5/10_viabilidad_aguas_abajo.md` §11 y §13).
- Decisión del usuario: «Abre la v5.1, pero aplica Nivel Kerno, Impacto y Landing también en ella». La v5.2 prevista
  queda dentro de esta.

**Se mantienen los principios de la v5.0:**
- puerta con GO en cada fase;
- informe de auditoría con la plantilla del encargo §16;
- etiquetas DATO · LECTURA · SUPUESTO · RIESGO · VERIFICAR;
- nada de la v1, la v3.2, la v3.3 ni la v4.x se destruye;
- exámenes fuera de tiempo con IC por personas;
- reglas de publicación fijadas antes de ver los resultados.

## 1. Objetivo

Que el producto use la v5 donde la F10 midió que gana, con su incertidumbre y sin regresión:

| Pieza | Qué gana (F10) | Cómo se publica |
|---|---|---|
| Normalización | Mezclar v5 y v3.2 por métrica: −2,9 % en el examen de la F1 y −8,2 % en fichajes reales | Versión **combinada**, con selector en el artifact |
| Simulador | Cobertura del equipo 0,58 → 0,89; −1,5 % por jugador | Producción con draws y dependencia estimada |
| Nivel Kerno | +0,10 de correlación de rangos con el percentil realizado | NK desde la contribución ensamblada, con rango de nivel y del año |
| Impacto | 0,02 → 0,29 en quienes cambian de liga | Prior del RAPM con perfil y traducción de la v5 |
| Landing | Mejora del segundo año de los americanos en Europa; cambio de perfil del primero | Lectura propia con sello; sin corregir la proyección hasta pasar su examen |

## 2. Fases

| Fase | Contenido | Examen y puerta |
|---|---|---|
| **F0 · Cachés y contrato** | Regenerar en `experimentos/` las cachés ausentes, con la versión de la normalización en la clave: V32_corte del simulador, algoritmo A por corte, RAPM multiliga y examen F4 de la v4.0. Hashes de referencia de las salidas publicadas para la no regresión | Reproducir los exámenes vigentes (V32_corte, F4 ΔNet, NK, IMPACTO) con las cachés nuevas, con las mismas cifras |
| **F1 · Versión combinada** | Mezcla de cuantiles v5 y v3.2 por métrica con pesos fijados fuera de muestra, las 26 métricas, las tres zonas incluidas. Formato de la v3.2 y draws combinados | Examen de la F1 y fichajes reales en cortes no usados para los pesos; cobertura en [0,76, 0,84] |
| **F2 · Simulador** | Producción con draws combinados; ensamblaje con dependencia estimada (minutos–producción, métricas, compañeros, liga-temporada con la innovación de λ de t+1); índice L sin métricas que falten; reentrenar el GBM de minutos | V32_corte rehecho (por jugador y por equipo) y ΔNet de la F4. Cobertura del equipo y de grupos de cinco en rango |
| **F3 · Nivel Kerno** | NK = 100·E[F_ref(C)] con la C de la F2; número frontal predictivo; rango de nivel y rango del año; sello | Separación, correlación de rangos y cobertura frente al NK vigente, mismos fichajes |
| **F4 · Impacto** | Prior del RAPM multiliga con el perfil de nivel y la traducción de la v5; interceptos de liga desde los puentes; Impacto con rango propagado | Examen del IMPACTO v4.0 (correlación de rangos con el on/off de t+1); predicción del RAPM de t+1 en quienes cambian de liga |
| **F5 · Landing** | δ₁ (primer año) y δ₂ (segundo año) jerárquicos por grupo de la Landing vigente, contraídos a través del perfil latente; «Adaptación EE. UU. → Europa» como lectura | Examen de publicación fuera de tiempo; con la cohorte de 2026-27 si está, y si no, la lectura queda con sello BAJA |
| **F6 · Integración y publicación** | Selector v3.2 / combinada en los tres artifacts; botón de actualización y recalibración mensual con el proceso paralelo; PR a la rama de producción | No regresión (hashes), ensayo en una copia y GO para publicar |
| **F7 · Documentación y cierre** | Incluye la F11 de la v5.0: CHANGELOG, artículo científico v5, guía del desarrollador y PR final | Suite completa y auditoría global |

## 3. Reglas de publicación fijadas antes

1. **Versión combinada:** se publica si mejora a la v3.2 en el examen de la F1 y a la v3.3 en fichajes reales, con IC
   que no cruza 0, y cobertura del 80 % en [0,76, 0,84].
2. **Simulador, NK e Impacto:** sustituyen a los vigentes sólo si mejoran su propio examen con IC que no cruza 0 y sin
   peor cobertura.
3. **Landing:**
   - un efecto sólo corrige una proyección si el examen fuera de tiempo lo aprueba (IC < 0);
   - si no, se publica como lectura con su IC y sello BAJA.
4. **Nada publicado se reescribe** sin un GO explícito en la F6.

## 4. Lo que no se toca

- El motor de minutos (salvo reentrenar el GBM).
- El RAPM por liga-temporada (bbstats).
- La v3.2 publicada y su histórico.
- La extracción, sin confirmación del usuario.

## 5. Pendientes heredados

- Regeneración de producción tras UEBNET/baskonia#7 (instrucciones en
  `docs/v5/operaciones/regeneracion_produccion_pr7.md`).
- Riesgos de la F10 §7:
  - error común por liga-temporada;
  - minutos anchos;
  - mejora del segundo año con pocos casos;
  - quintetos reales.
