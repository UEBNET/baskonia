# Kerno Analytics · Resumen ejecutivo del proyecto a 9-11-2026 (CERNO v4.2)

Para el CEO. Cada pieza lleva su **versión vigente** (la que está en el producto), lo que se intentó en la v4.2 y la
decisión. La regla de la v4.2 fue la misma en todo: cada pieza nueva se examinaba con un criterio fijado antes de calcular
(`configs/v42.yaml`, commit `d606f47`). Sólo entraba si mejoraba lo vigente; si no, se mantiene la versión anterior.

Etiquetas: **[DATO]** medido; **[LECTURA]** interpretación; **[DECISIÓN]** tomada por ti o por la regla fijada.

---

## 1. En una página

| Bloque | Versión vigente | Qué cambió en la v4.2 | Estado |
|---|---|---|---|
| Normalización de ligas (métricas del jugador) | **v4.2** en 12 de 30 métricas · v3.2 en 18 | Historial del jugador (filtro de Kalman sobre sus temporadas) | 12 pasan; rango del 80 % entre un 45 % y un 70 % más estrecho, sin perder cobertura |
| Motor de minutos y producción (simulador) | **v3.3** | Motor alimentado con el historial | **No pasa** (rebote ofensivo y tapones empeoran): sigue la v3.3 |
| Adaptación al cambio de liga (Landing) | **v3.1** (la del motor) | — | Tu decisión: la Landing mide lo que pierde en su 1.ª temporada frente a su nivel adaptado |
| Modelo de equipo (β RAPM, Net, NIVEL KERNO, IMPACTO) | **v4.0** | β con historial | Pasa por la regla con poco margen, pero ordena peor y no estrecha el rango: versionado, **no propagado** |
| Ecosistema del club (escenarios, Shapley, Coste de su ausencia) | **v4.1** | — | En el producto |
| Tríos, parejas y sinergia de pareja | **v4.2** | Contracción hacia lo que esperan sus jugadores y su historial | Pasan; quintetos sin potencia (siguen en la versión anterior) |
| Presentación de rangos | **v4.2 · C** | Valor + confianza en tablas y listas; rango en la ficha y al pasar el ratón | En el producto |
| Escala de índices | **0–100** (v4.1 K4) | — | 50 = referencia; los cambios, en puntos con signo |
| Artefacto visual | **Kerno Analytics** en tres artifacts (Jugadores, Equipos, Metodología) | División por espacio (256 MiB por versión) | Ver §7 |

---

## 2. Normalización de ligas: llevar a todos a la misma vara

- **v2 · A+B amortiguado.** Dos algoritmos de traducción entre ligas (A, por puentes de jugadores; B, por modelo), combinados
  y amortiguados. Es la base común.
- **v3.1 / v3.2 · CVAE jerárquica + A+B.** Red generativa por liga y temporada combinada con la v2. La v3.2 corrigió las
  identidades de jugadores (03-11). **Sigue siendo la base de todo el producto.** Equivalente EuroLeague con rango del
  80 % por temporada. Docs: `docs/normalizacion_v32.md`.
- **v4.2 · historial del jugador (nuevo).** Combina las temporadas del jugador hasta t: un filtro de Kalman con un paseo
  aleatorio entre temporadas y la varianza de cada temporada sacada de su propio rango. Examen sin fuga, prediciendo la
  temporada siguiente en 2022, 2023 y 2024.
  - **[DATO] Pasan a v4.2 12 de 30 métricas:**
    - uso, pérdidas, robos (% y por 100), tapones (% y por 100) y canastas asistidas, con sello ALTA;
    - puntos/100, proporción de triples y rebote ofensivo %, con sello MEDIA;
    - rebote ofensivo/100, con sello ALTA;
    - rebote defensivo %, por una variante centrada por temporada (POST HOC) a la que sólo se le admitía el sello ALTA.
  - **[DATO] Se quedan en v3.2 las otras 18:** TS%, eFG%, % de tiro, ratings, PER, WS, AST% y zonas de tiro. Con historial
    predicen peor, porque cambian con el entorno.
  - **[DATO]** Los rangos de una temporada de la v3.2 eran entre 2 y 5 veces más anchos de lo que justifican los datos. En
    las 12 métricas, el rango del 80 % se estrecha entre un 45 % y un 70 % y la cobertura sigue en 0,79–0,84.
  - **En el producto:** el navegador combina la previa de las temporadas cerradas con la temporada cargada, así que la
    temporada en curso se actualiza sola con la rutina mensual.
  - **Ejemplo («Por necesidad», Juwan Morgan, «Creador»):** pasa de 80 [51–95] a 75 [57–84].
  - Doc: `docs/checkpoints/V42_D1.md`.

## 3. Simulador / motor de minutos y producción

- **v3.1 → v3.2:**
  - pasos del motor que se pueden apagar;
  - factores de uso y eficiencia;
  - producción alternativa del Atlas;
  - recalibración conforme (conformal) de los intervalos del 50 % y del 90 %.
- **v3.3 (vigente).**
  - Minutos con la mezcla motor + gradient boosting.
  - Minutos y producción acoplados en el Monte Carlo.
  - Rangos de minutos recalibrados en la capa E de la v4.1 (P5), con cobertura del 80 % y del 90 % en rango.
- **v4.2 · motor con historial: [DECISIÓN] no pasa; sigue la v3.3.**
  - Mismo examen que decidió la v3.3: 6.322 fichajes en cortes anidados, 400 simulaciones por fichaje.
  - El rebote ofensivo/100 empeora (+3,3 % de MAE) y los tapones también (+1,8 %).
  - En uso no se puede descartar que empeore más allá del margen.
  - Tras recalibrar, los rangos no se estrechan (ratio 0,99–1,09).
  - [LECTURA] El daño se concentra en 2023-24, el corte que usa la producción del Atlas, la misma que la v3.3 publicada.
  - Doc: `docs/checkpoints/V42_D2_motor.md`. Queda versionado: `configs/simulation_v42.yaml` y `CERNO_SIMULADOR=v42`.

## 4. Adaptación al cambio de liga · Landing

- **Vigente:** la tabla de adaptación v3.1, la del motor. **[DECISIÓN CEO]** La Landing mide lo que pierde el jugador en
  su primera temporada por el coste de adaptación, frente al nivel que alcanza una vez adaptado.
- Ejemplos: NCAA → profesional −11,6 % [−15,0; −8,1]; EE. UU. → Europa −4,6 % [−8,1; −1,0].
- Confianza baja: le falta un examen frente a su propia definición. El examen K3 midió otra cosa (frente a la
  normalización) y queda como dato.
- Doc: `docs/checkpoints/V41_F4.md` §8.2 y §8.6.

## 5. Modelo de equipo (v4.0) y ecosistema del club (v4.1)

- **v4.0, vigente.** Cinco capas:
  1. β RAPM multiliga con prior del perfil → **RAPM proyectado**;
  2. sinergia de pareja por perfiles φ;
  3. corrección no lineal h;
  4. Net del equipo proyectado (calibrado; confianza alta);
  5. anclas **NIVEL KERNO** (confianza alta) e **IMPACTO** (moderada).

  Doc: `docs/modelo_equipo_v40.md`.
- **β v4.2 (historial), [DECISIÓN] versionado pero no propagado.**
  - Pasa la regla formal (MAE −0,034 [−0,060; −0,006]), pero sólo por un año.
  - Ordena algo peor el on/off real: −0,011 [−0,019; −0,003].
  - Tras recalibrar, su rango no es más estrecho.
  - No cambia el RAPM que ve el usuario ni el IMPACTO, que tendría que pasar su propio examen; el estimado apunta a
    empeorar.

  Doc: `docs/checkpoints/V42_D2_beta.md`.
- **v4.1 · ecosistema, vigente:**
  - escenarios de altas (rol fijado) y bajas, con Shapley exacto por movimiento;
  - **Coste de su ausencia** (confianza moderada);
  - cambio por compañero (confianza baja: lo que mueve una baja en cada compañero está por debajo del ruido);
  - NIVEL KERNO por escenario;
  - «Impacto en pista» EXPERIMENTAL, que no se muestra;
  - capa XP de puntos esperados.

  Docs: `docs/checkpoints/V41_F0…F4.md`.

## 6. Rangos e intervalos de confianza: dónde estamos

- **Todo valor del modelo lleva rango del 80 %** y **confianza alta · moderada · baja**, que sale de su examen con datos
  reales, nunca del criterio del modelo.
- **Se estrechan honestamente (v4.2):**
  - las 12 métricas con historial (entre un 45 % y un 70 % menos de ancho, misma cobertura);
  - tríos y parejas, con cobertura 0,78–0,80.
- **No se pudieron estrechar sin perder cobertura:** el motor (minutos y producción), el β y, por tanto, el NIVEL KERNO y
  el IMPACTO.
  - [LECTURA] Sus rangos son de predicción de la temporada que viene: buena parte de la anchura es ruido real (rol,
    minutos, la propia temporada).
- **Presentación (C):**
  - tablas y listas: valor + medidor de confianza (por terciles de anchura en su familia);
  - el rango completo, en la ficha y al pasar el ratón.
- **El «ajuste» de «Por necesidad»** sigue sumando los extremos de cada métrica como si fallaran a la vez, lo que lo hace
  prudente. Corregirlo con la correlación real entre métricas (opción A) estrecharía más; queda propuesto.

## 7. Artefacto visual

- **Marca Kerno v2.0:**
  - colores Racing, Chalk, Ink y Brass;
  - tipografías Bombardier, Mona Sans y Geist Mono;
  - sin Fit ni ADAPT;
  - escala 0–100 en todos los índices;
  - «RAPM proyectado»;
  - Landing, confianza y panel del ecosistema.
- **Publicado:**
  - https://claude.ai/artifact/A7rufkL84rvRFcUBFBxFbC, versiones 23–26;
  - capacidad `mcp` del botón de actualizar conservada;
  - rutina mensual de datos de 2026-27.
- **Límite de espacio:** 256 MiB por versión. El artifact estaba a menos de 1 MB del límite, así que se divide en tres por
  secciones (**[DECISIÓN CEO]**):
  - **Jugadores** (el actual): Mercado, Evaluación, Decisión y Modelo de equipo;
  - **Equipos** (nuevo): todo el 01 Diagnóstico;
  - **Metodología** (nuevo): todo el Método.

  Mismo código con un interruptor de sitio. Las secciones de otro sitio son enlaces. Doc: `docs/checkpoints/V42_sitios.md`.

## 8. Decisiones y riesgos abiertos

1. **Ajuste de «Por necesidad»:** aplicar la opción A (correlación real entre métricas) para estrecharlo más.
2. **Landing:** examinarla frente a su propia definición (primera temporada frente a nivel adaptado) para darle una
   confianza mejor que baja.
3. **IMPACTO con β v4.2:** no lo propongo; el estimado apunta a empeorar.
4. **Tríos y parejas de 2026-27:** su fichero v4.2 es una foto. Hay que reexportarlo tras cada actualización mensual (o
   pasar la combinación al navegador, como en las métricas).
5. **Rutina mensual y los tres artifacts:** la actualización de datos debe publicar en el artifact que corresponda a cada
   fichero.
6. **Pendientes de marca** (de antes): estado legal del nombre, licencia de Bombardier y dominio.

## 9. Dónde está todo en Git

- Ramas: `claude/jolly-thompson-qczxl4` y `claude/encargo-v41-ecosistema`.
- v4.2:
  - prerregistro: `configs/v42.yaml`;
  - código: `bbequipo/v42/` (`historial.py`, `beta.py`, `motor.py`, `unidades.py`, `unidades_artifact.py`);
  - salidas: `data/modelos/v4_2/`;
  - checkpoints: `docs/checkpoints/V42_*.md`;
  - tests: `tests/test_v42.py`.
- Estado de cada salida visible: `docs/estado_modelos.md`. Registro: `CHANGELOG.md`.
