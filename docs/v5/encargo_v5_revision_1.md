# Encargo v5.0 · Revisión 1 · Normalización + proyección en contexto

Versión del encargo: **1.2** (10-11-2026). Sustituye a la 1.1 donde la contradiga; lo demás sigue vigente: principios,
puertas, plantilla de informe y etiquetas de evidencia.

Aprobada por el usuario el 10-11-2026: «Sí al cambio de enfoque, manteniendo los nombres de estilos actuales.
Actualiza el encargo y arranca F2».

## 1. Por qué cambia

La F1 (`docs/v5/01_auditoria_varianza.md`) midió de dónde sale la incertidumbre de la temporada siguiente de un
jugador. Medianas de las 33 métricas, en la liga de destino:

| Fuente | Fracción | ¿Reducible? |
|---|---|---|
| Suerte de la muestra (racha dados los minutos) | 49 % | No |
| Contexto: rol, compañeros, entrenador, encaje en la liga | 22 % | **Sí, modelándolo** |
| Duda sobre el nivel del jugador | 21 % | **Sí**, con historial y mejor medida |
| Traducción entre ligas | ~1 % | Poco (afecta al centro, no a la anchura) |

El enfoque 1.1 invertía sobre todo en el nivel (normalización). El usuario pide, además, **predecir la temporada
siguiente del jugador en su nuevo contexto**:
- con todas sus temporadas representativas;
- con el efecto de la nueva liga sobre su producción estadística;
- con el estilo de sus compañeros (no química de pareja, que la v4.0 y la v4.1 mostraron que no se mide);
- con el estilo de la liga.

## 2. Objetivo revisado

Un único modelo probabilístico, **«jugador en su nuevo contexto»**, estimado con **todas las transiciones de una
temporada a la siguiente** de todos los jugadores desde 2020-21, cambien o no de liga.

Entrega tres objetos con nombre propio:

1. **Nivel:** cuánto vale el jugador, en la vara de cualquier liga. Es el objeto de la versión 1.1.
2. **Proyección en contexto:** qué producirá por posesión y por minuto la temporada siguiente en un equipo y una liga
   concretos, con sus compañeros y su rol. Es un intervalo predictivo de la producción por posesión.
3. **Proyección por partido:** la proyección en contexto combinada con los minutos del motor v3.3 (o fijados por el
   analista). Es un intervalo predictivo de la producción por partido.

### Piezas del modelo

1. **Perfil del jugador con todas sus temporadas representativas.** El peso de cada temporada lo aprende el modelo por
   métrica: depende de la antigüedad, la edad, el cambio de rol y el cambio de liga.
   - No se usan como observaciones medias a posteriori ya contraídas (lección de la F1, §4.3).
   - Se usan los conteos brutos con su exposición real.
2. **Efecto de la liga de destino según el tipo de jugador.** λ ya no es un desplazamiento igual para todos: cambia
   con el perfil latente del jugador (contracción jerárquica hacia el efecto común).
3. **Estilo de la liga:** variables continuas por liga-temporada (ritmo, 3PAr, FTr, rebote ofensivo, pérdidas, % de
   canastas asistidas, % de tiros en el aro…) y el reparto de sus equipos entre los seis estilos unificados.
4. **Estilo de los compañeros:** la composición de estilos y rasgos de los compañeros, ponderada por minutos
   compartidos. Entra en el modelo con contracción fuerte hacia «sin efecto», para no vender ruido como sinergia.
5. **Minutos y rol:** motor v3.3, que se conserva. El rol de las altas lo fija el analista (decisión 1 del CEO en la
   v4.1).

### Nombres de estilo (sin cambios)

- **Estilos unificados** (jugador y equipo, frente a su propia liga; `configs/styles.yaml`): **Spacing, Circulación,
  Isolation, Old-School, Pistons, Pintura**.
- **Estilos del mapa del Atlas** (VaDE; `config/estilos.json`): **Creación individual, Exterior y presión, Lejos del
  aro** y los demás de ese fichero.
- No se crean nombres nuevos.
- El estilo de una liga se describe con su reparto entre los seis estilos unificados y con rasgos medibles, sin
  etiqueta propia.

## 3. Mapa de fases revisado

| Fase | Versión 1.1 | Versión 1.2 (cambios en **negrita**) |
|---|---|---|
| F2 | Contrato, entidades, puentes intra e inter, enfrentamientos europeos | Lo mismo, más: **caja por partido derivada de los brutos** (rebotes, pérdidas, robos, tapones y faltas por jugador y partido, capa derivada sin tocar la extracción); **estilo de liga y de equipo por temporada**; **contexto de compañeros por jugador-equipo-temporada** (minutos compartidos y su composición de estilos) |
| F3 | Verosimilitudes por familia | Sin cambios |
| F4 | Carrera y edad | **Peso aprendido de cada temporada pasada** por métrica (antigüedad, edad, cambio de rol, cambio de liga). Línea base obligatoria: v4.2 D1 en su examen **y** examen de nivel por simulación (F1 §4.3) |
| F5 | Modelo factorial | Sin cambios; el perfil latente alimenta los efectos heterogéneos de la F6 |
| F6 | Ligas: λ conjunta, dinámica, puentes | **«Ligas y contexto»**: λ por tipo de jugador (perfil latente), estilo de liga y estilo de compañeros como contexto, todo jerárquico y contraído. Consistencia de ciclo para el componente común de λ |
| F7 | Selección | Sin cambios |
| F8 | Validación | Examen principal nuevo: **producción de la temporada siguiente de fichajes reales con su equipo real** (banco V32_corte, ~4.956 fichajes), frente al motor v3.3 y la v4.2. Más el examen de nivel por simulación (SBC) y el resto del protocolo 1.1 |
| F9 | Contrato de salida | Tres objetos: nivel, proyección en contexto y proyección por partido, con nombre en la interfaz. Sello de fiabilidad por objeto |
| F10 | Estudio de viabilidad aguas abajo | **Prototipo funcional** de la proyección en contexto conectado al motor de minutos, sin tocar el simulador publicado hasta que pase su examen. Más el estudio de NK₁/NK₂, Impacto y Landing de la 1.1 |
| F10-B | — | **Plan B condicional** (§5) |
| F11 | Documentación y cierre | Sin cambios |

## 4. Criterios de éxito añadidos (además de los de la 1.1)

| # | Criterio |
|---|---|
| 9 | La proyección en contexto (por posesión) mejora el CRPS del motor v3.3 en la producción de la temporada siguiente de fichajes reales, con el intervalo de la diferencia (bootstrap por jugador) que no cruce 0, en la mayoría de las métricas de producción. Cobertura del 80 % en [0,76, 0,84] |
| 10 | **Anchura del intervalo predictivo** frente a la v3.3, con la misma cobertura. Objetivos orientativos, que la F1 da como alcanzables: −20 % a −25 % en uso, rebote, tapones, robos, % de canastas asistidas y valoración global; menos del −10 % en porcentajes de tiro. Si no se alcanzan, se explica con la descomposición de la F1 |
| 11 | Los efectos de **estilo de liga** y **estilo de compañeros** sólo se publican si mejoran el examen del criterio 9 frente al mismo modelo sin ellos (navaja con IC). Si no, quedan documentados y apagados |

## 5. Plan B: producción por minuto con minutaje como entrada (condicional)

**Cuándo se evalúa.** Sólo si, tras la F8, la proyección por partido no cumple el criterio 9 **porque** el error de
minutos domina. Por ejemplo, si con los minutos reales de t+1 (rol oráculo) el modelo sí lo cumpliera.

**Qué es.**
- Se publica la producción **por minuto** (o por posesión) del jugador en su contexto.
- Los minutos los fija el analista o el escenario, en lugar de predecirse.
- La producción por partido es entonces producción por minuto × minutos dados.

**Limitaciones declaradas.**
- No recoge la fatiga ni el efecto de las rachas.
- Tampoco recoge el cambio de eficiencia con el volumen (la curva uso-eficiencia de la fase 4 sólo cubre una parte).
- Por eso es un enfoque **secundario**.

**Requisito previo.** Una auditoría con pruebas (informe propio) que cuantifique, con datos:
1. cuánto error añade suponer la producción por minuto constante frente a la observada por tramos de minutos, por
   métrica;
2. cuánto pesan la fatiga (rendimiento por cuartos y por minutos acumulados) y las rachas en el error;
3. la decisión, con criterios fijados antes de ver los resultados.

## 6. Decisiones del usuario registradas y pendientes

**Registradas:**
- Rama `claude/sweet-turing-5ti6hi` desde `claude/encargo-v41-ecosistema`; PR por fase mayor.
- Código en `bbnorm5/`.
- Niveles de intervalo: 50, 80 y 95 %.
- Migración Cerno → Kerno como tarea aparte.
- Dependencias autorizadas.
- v4.2 D1 como tercera línea base.
- Corrección de `vara.json` aplicada.
- Cortes 2023-2024 reutilizables con sesgo declarado; examen confirmatorio 2025-26 → 2026-27.
- Cambio de enfoque a esta revisión.

**Pendientes** (no bloquean la F2):
1. **Ampliar la extracción hacia atrás** (p. ej. 2015-16) en las ligas que lo permiten. Sin respuesta: **se trabaja
   con 2020-21 en adelante** y en la F6 se medirá cuánto ganaría la estimación de los efectos por tipo de jugador y
   estilo con más temporadas, antes de proponerlo con cifras.
2. Expectativas de estrechamiento (criterio 10): se toman como objetivos orientativos, no como compromiso.
3. Pendientes del informe F1 §11:
   - el texto del intervalo en el artifact;
   - una nota sobre la lectura de la D1;
   - el listón de la F4. Queda incorporado a esta revisión; el usuario puede revertirlo.
