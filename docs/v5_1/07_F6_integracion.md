# v5.1 · F6 · Integración y publicación (primera entrega: tablas)

Fecha: 14-11-2026 · Kerno Analytics · encargo v5.1 (`docs/v5_1/00_encargo_v5_1.md`), con las decisiones de la puerta:

| Decisión | Respuesta |
|---|---|
| Alcance | Por entregas. Esta entrega: tablas combinadas con selector en los tres artifacts, ensayo privado y GO. La segunda: simulador y Nivel Kerno v5.1 en el motor del navegador |
| Vara | Publicar `vara_v51.json` (la traducción de la v5 entre ligas) |
| Versión por defecto | v5.1 |
| 2026-27 | El proceso paralelo de la temporada en curso, antes de publicar |

**Código.**
- En esta rama:
  - `bbnorm5/simulador51/incremental.py` (proceso paralelo);
  - `bbnorm5/simulador51/kit.py` (kit para producción);
  - `bbnorm5/salidas/producto51.py` (componente v5, combinación y vara).
- En la rama de producción (`claude/v51-produccion`, sin subir hasta tu permiso):
  - `bbactualiza/normalizacion51.py`;
  - pasos del botón y de la recalibración;
  - portal (`artifact/kerno/index.html`, `clasico.html`);
  - skills.

  El parche y el guion para reconstruirla están en `docs/v5_1/produccion/`.

**Salidas.**
- `data/v5_1/incremental/2026-27/`;
- `data/v5_1/producto/`;
- `data/v5_1/kit/`.

**Tests.**
- `tests/v5_1/test_simulador51.py` (proceso paralelo);
- `tests/v5_1/test_producto51.py`;
- en producción, `tests/js/v51_normalizacion.js` (navegador).

```bash
python -m bbnorm5.v51 --pasos incremental producto kit        # en esta rama, ≈ 1 min
PYTHONPATH=. python -m bbactualiza.normalizacion51            # en producción: 2026-27 con sus datos, ≈ 2 min
PYTHONPATH=. python -m bbactualiza.normalizacion51 --todas    # en producción: regular_v51.json de todas las temporadas
```

Etiquetas: **DATO**, **LECTURA**, **SUPUESTO**, **RIESGO**, **VERIFICAR**.

---

## Resumen

1. **Proceso paralelo de 2026-27.** Aplica la v5 a la temporada en curso con los modelos congelados, como hace la v3.2
   con su CVAE: medida, carrera y traducción entre ligas.
   - El filtro congelado reproduce exactamente los niveles de 2025-26 (diferencia 0,0 en 39.947 filas).
   - En producción, 2026-27 tiene 5.738 de 7.172 filas con v5 y 58 personas nuevas.
   - Tarda 2 minutos dentro del botón.
2. **La combinación se hace en producción, sobre la v3.2 vigente.** La v3.2 de producción se reajustó con la Liga U y
   difiere de la de esta rama en casi todas las filas (correlación ≥ 0,996; unos 5 % del ancho del intervalo). Por eso:
   - se publica el componente v5;
   - w·v5 + (1 − w)·v3.2 se calcula al publicar, con las w de la F1;
   - la recalibración mensual de la v3.2 entra sola en la v5.1.
3. **Tablas `regular_v51.json`.**
   - Mismas filas y columnas que `regular.json`, más dos máscaras.
   - Donde no hay v5 (Liga U, por ejemplo), son idénticas a la v3.2: 0 celdas distintas.
   - Ocupan lo mismo que las vigentes: 36,2 MB comprimidos en las 7 temporadas, frente a 36,4.
4. **Portal.**
   - Selector «Normalización» en Ajustes, con v5.1 por defecto.
   - En v5.1 no se aplica el historial v4.2: la v5 ya lleva la carrera.
   - Vara de la v5 mezclada con la de la v3.2. Sus valores coinciden con la referencia en Python hasta el último decimal.
5. **Pendiente de tu GO** (§6): subir la rama de integración y publicar en los tres artifacts tras el ensayo privado.

---

## 1. Proceso paralelo de la temporada en curso (DATO)

| Paso | Qué hace | Congelado |
|---|---|---|
| Caja y zonas | Caja por partido de 2026-27 desde los brutos (F2 de la v5) y zonas y % asistidas (F9 bis) | — |
| Personas | Las conocidas, por su id de fuente; las nuevas, por su persona del crosswalk si ya existe en la v5; si no, una persona nueva | — |
| Medida (F3) | Media de cada rol, dispersión y σ de cada liga | Los de 2025-26 |
| Carrera (F4) | Filtro de Kalman sobre toda la serie de cada persona; se toma 2026-27 | θ y β (`carrera/modelos_final.pkl`) |
| Traducción | Equivalente EuroLeague 2025-26 | λ de 2026-27 = λ de 2025-26 más la varianza de la innovación de un año |
| Combinada | w·v5 + (1 − w)·v3.2 | Las w de la F1 |

**Comprobaciones.**
- **Esta rama** (sus datos de 2026-27):
  - 6.965 filas, el 81 % combinadas (en 2025-26, también el 81 %);
  - medias y medianas en línea con las de 2025-26;
  - 90 personas nuevas.
- **Kit:** con los 38,9 MB del kit (frente a los 2,9 GB de `data/v5/`) el resultado es idéntico, también rehaciendo la
  caja desde los brutos.
- **Producción** (sus datos de 2026-27, más nuevos): 7.172 filas, 5.738 con v5, 58 personas nuevas.

**SUPUESTO · λ de la temporada en curso.** La NUTS del paso 2 no tiene 2026-27. Se usa el λ de 2025-26 con la varianza
de un año de cambio añadida: la mediana entre ligas de E[(λ_2025-26 − λ_2024-25)²] en los draws. El intervalo es algo más
ancho, sin cambiar el centro. Se revisa cuando la v5 se reajuste con 2026-27 cerrada.

## 2. Producto para el artifact (DATO)

- **Componente v5** (`data/v5_1/producto/superposicion/<t>.csv.gz`, 9,5 MB en 7 temporadas): `<m>_v5`, `<m>_v5_lo`
  y `<m>_v5_hi` de las 25 métricas del esquema v1 que la v5.1 cambia.
- **Combinación** (`producto51.aplicar`), sobre la v3.2 vigente:
  - centro e intervalo del 80 % = w·v5 + (1 − w)·v3.2 donde están las dos, sólo v5 donde no hay v3.2, la v3.2 en el resto;
  - percentil recalculado frente a la EuroLeague de su posición;
  - `fuente_norm` = «V5.1» o «V3.2»;
  - máscaras `v51_comb` y `v51_solo`, con un bit por métrica.

  Sobre la v3.2 de esta rama reproduce la combinada de la F1:
  - valores con diferencia < 0,002;
  - percentiles con un puesto como mucho, por empates de redondeo.
- **`vara_v51.json`** (396 KB): para cada una de las 18 métricas con λ propio,
  - Δ_d = E[λ(EuroLeague, 2025-26) − λ(d, 2025-26)];
  - la DT de λ(d, 2025-26) − λ(origen, t) por nodo (con 2026-27);
  - la w de la combinada.

### 2.1 Vara de la v5.1 en el portal

Para expresar un equivalente EuroLeague en la liga de tu club:
- **v5:** desplazamiento en la escala del enlace, η_d = η_EL − Δ_d. Cada cola del intervalo se trata como en la v3.2,
  con la DT por par de nodos.
- **Métrica combinada:** valor en la vara = w·(conversión v5) + (1 − w)·(conversión v3.2), con percentil frente al
  jugador medio de su posición en la vara.
- **Métricas derivadas** (TS%, eFG%, por 100, STL%): sin Δ propio, se convierten con la v3.2.

**SUPUESTO.** Se convierte el valor combinado con las dos traducciones, no cada componente con la suya: la tabla v1 no
lleva los componentes. Con la vara en la EuroLeague el resultado es exacto.

**LECTURA · las dos varas no siempre van en el mismo sentido.** Un 34,7 % de triple de EuroLeague expresado en la
Primera FEB:
- con la v5 da 35,4 %: la v5 mide qué tiraría ese jugador allí, con los jugadores que cambian de liga;
- con la v3.2 da 31,5 %: la v3.2 lo coloca en la distribución de capacidad de la liga.

La v5.1 los combina con la w de la métrica (0,34 en el triple), sin elegir entre los dos. **VERIFICAR** en la ficha de
algunos casos durante el ensayo.

| Métrica | Liga | v5 | v3.2 |
|---|---|---|---|
| Pts/100 (18,0 EL) | NBA | 11,6 | 16,6 |
| Pts/100 | Primera FEB | 22,4 | 21,6 |
| AST% (15,0 EL) | BBL | 17,1 | 12,9 |
| USG% (20,0 EL) | NBA | 14,2 | 18,2 |

## 3. Portal (cambios en la rama de producción)

| Página | Cambio |
|---|---|
| `index.html` (Jugadores, Equipos y Metodología) | Selector «Normalización · v5.1 / v3.2» en Ajustes, con v5.1 por defecto. Se guarda en `localStorage` (`kerno.norm`) y la página se recarga al cambiar, para que ninguna caché mezcle versiones. `temporada()` carga `regular_v51.json` y, si falta, la v3.2. Sin `historialV42` en la v5.1. `convVara` mezcla las dos varas. El pie y Metodología dicen qué versión se ve |
| `clasico.html` | «Datos normalizados» lee la misma elección. `convertirVara` mezcla las dos varas por fila. La ficha explica «V5.1» (las columnas A y B siguen siendo de la v3.2) |
| Atlas, simulador, Nivel Kerno, Impacto | Sin cambios en esta entrega: siguen con la v3.2 (segunda entrega) |

**Prueba en el navegador** (`tests/js/v51_normalizacion.js`, Chromium con un sitio local):
- la v5.1 carga por defecto con sus máscaras;
- la vara de la v5 coincide con `producto51.convertir` (35,42476512511429 en los dos);
- la mezcla con w = 0,342 da el valor esperado;
- TS% sólo usa la v3.2;
- el selector cambia a la v3.2 y vuelve el historial v4.2;
- la vista clásica carga la v5.1;
- sin errores de página.

## 4. Botón, recalibración y publicación (rama de producción)

1. **Paso `normalizacion_v51`** tras `roles`: necesita la v3.2 final del contexto y los partidos por jugador de las ligas
   agregadas. Escribe el componente v5 de 2026-27, que es lo único que se versiona; los intermedios van a carpetas
   ignoradas.
2. **Subpaso `normalizados_v51`** del artifact: combina con la v3.2 recién calculada. Escribe `regular_v51.json` y
   `vara_v51.json`, que `compactar` también reduce.
3. **Reparto entre sitios.** Las rutas nuevas (`datos/normalizados/<t>/regular_v51.json.gz.txt`, `vara_v51.json.gz.txt`)
   van solas a los tres artifacts como hermanas de `regular.json.gz.txt` y quedan en los manifiestos.
4. **Tamaño:** unos 36 MB más por sitio. Jugadores, Equipos y Metodología quedan entre 190 y 200 MiB (límite 256).
5. **Recalibración mensual.** Pasa por el paso v5.1 con los modelos de la v5 congelados y combina con la v3.2
   reentrenada. La v5 se reajusta aparte, una vez al año, con la temporada cerrada.
6. **Skills:** `actualizar-temporada` documenta el paso; `anadir-liga` indica que una liga nueva queda con la v3.2 en la
   v5.1 hasta el reajuste de la v5.
7. **Dependencias:** `pyarrow` en `requirements-v3.txt`, que el botón ya instala. La cadena no usa JAX ni NumPyro.

## 5. Verificación de no regresión

- **Tablas:** `regular.json`, la vara y las demás tablas no cambian. `regular_v51.json` es un fichero aparte.
- **Portal en v3.2:** carga lo mismo que hoy, con el historial v4.2.
- **Tests de producción:** 334 pasan y 1 falla. El que falla
  (`test_equipo_v40.py::test_traducir_corte_reproduce_traducir_filas`) pide una caché de `experimentos/` no versionada
  y falla igual en la rama de producción sin tocar.
- **Tests de esta rama:** `tests/v5_1/` (13).
- **Histórico:** sólo se publica el componente v5 ya versionado; la v3.2 histórica no se toca.

## 6. Qué falta para publicar (puerta)

1. **Ensayo privado.** Copia privada del artifact Jugadores con las páginas nuevas y los ficheros v5.1. Se comprueba:
   - carga y selector;
   - vara en varias ligas;
   - ficha clásica;
   - tamaños.
2. **Permiso para subir `claude/v51-produccion`** (desde `claude/jolly-thompson-qczxl4`) y abrir el PR a la rama de
   producción.
3. **GO para publicar en los tres artifacts**, uno detrás de otro.
4. **Segunda entrega:** simulador y Nivel Kerno v5.1 en el motor del navegador.
