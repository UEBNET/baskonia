# F9 · Contrato de salida de la v5 y sello de fiabilidad (encargo v5.0 §13), con la ampliación F9 bis

Fecha: 12-11-2026 · Kerno Analytics · normalización cruzada v5.0.

**Código**
- `bbnorm5/salidas/destinos.py`: salidas por persona, métrica y liga de destino; umbrales; sello; derivadas.
- `bbnorm5/salidas/derivadas.py`: TS%, eFG% y variantes «por 100».
- `bbnorm5/salidas/formato_v32.py`: formato que lee el artifact.
- `bbnorm5/salidas/diccionario.py`: diccionario y glosario.
- `bbnorm5/validacion/recalibracion.py`: decisión 4 de la F8.
- `bbnorm5/datos/pista_partido.py`: zonas y asistidas por partido (F9 bis).
- `bbnorm5/f9.py`.

**Configuración.** `configs/v5/f9.yaml` (semilla 20261117; regla del sello fijada antes de ver las salidas).

**Salidas.** En `data/v5/salidas/`.

**Tests.** `tests/normalizacion_v5/test_salidas_f9.py`.

```bash
# salidas por liga de destino, repartidas entre procesos (≈ 1 h con dos procesos)
python -m bbnorm5.f9 --config configs/v5/f9.yaml --pasos destinos --metricas <métricas> --parte <k>
python -m bbnorm5.f9 --config configs/v5/f9.yaml --pasos unir_destinos formato_v32 diccionario
```

Etiquetas: **DATO**, **LECTURA**, **SUPUESTO**, **RIESGO**, **VERIFICAR**.

---

## Informe de auditoría · Fase F9 · Contrato de salida

### Resumen ejecutivo

1. **Salidas listas por jugador, métrica y cada liga de destino posible.**
   - Proyección a 2026-27: 11.246 jugadores × 20 ligas × 26 métricas = 5,5 millones de filas.
   - Por cada fila:
     - **nivel** (intervalos del 50 y 80 %);
     - **predictivo** de la temporada siguiente (50, 80 y 95 %);
     - **traducción** Δλ;
     - **probabilidades de umbral** (percentiles 25, 50 y 75 de la liga × rol);
     - **sello de fiabilidad**.
   - Los **draws** van aparte: 500 por jugador y métrica en su liga actual.
   - Metadatos por fichero: versión, hash de configuración y de datos, fecha y temporadas.
2. **F9 bis: de 14 a 26 de las 33 métricas de la v3.2.**
   - Se modelan 5 nuevas como las 14: % en el aro, cortos, media distancia, triples de esquina y % asistidas.
   - Se derivan 7: TS%, eFG%, OREB/100, DREB/100, BLK/100, STL% y PF/100.
   - Quedan en la v3.2 los índices globales (PER, Game Score, WS/40, ORtg, DRtg) y el RAPM.
3. **Las métricas nuevas están calibradas en sus capas**: cobertura del 80 % de 0,79 a 0,81 en la medida (F3), la
   carrera (F4) y la simulación del nivel.
   - **Frente a la v3.2, en el examen de la F1, la v5 pierde en tres zonas:** aro (+4,0 %), media distancia (+8,1 %) y
     triple de esquina (+8,3 %), las tres con IC que no cruza 0.
   - Empata en cortos, % asistidas, TS% y eFG%.
4. **Recalibración por métrica y grupo de ligas (decisión 4): adoptada por el criterio fijado.**
   - Fichajes: −0,53 %, IC −0,73 % a −0,33 %.
   - Protocolo de la F1: −0,19 %, IC −0,39 % a +0,03 %; no empeora.
   - Lleva 16 de 19 métricas a la cobertura en rango, pero **infracubre** en BLK%, triple de esquina y media distancia
     (0,70–0,72 en todos los casos; 0,64–0,70 entre quienes cambian de liga).
5. **El sello ordena la incertidumbre** dentro de cada métrica: anchura del predictivo relativa a la mediana de la
   métrica de 0,88 (alta), 0,94 (media) y 1,50 (baja).
6. **Formato para el artifact sin modificarlo.** El CSV de cada temporada tiene las mismas filas y columnas que el de la
   v3.2 (equivalente EuroLeague 2025-26), con la v5 en las 26 métricas y la v3.2 conservada en `<m>_v32`. Activarlo es
   cambiar la carpeta de origen (§6).
7. **Pendiente para cerrar la publicación:**
   - la NUTS del paso 2 de los bloques volumen_papel y zonas, y repetir el de tiro (R̂ 1,03 en la DT base de TL%);
   - después, el formato v3.2 (usa esa traducción) y el criterio 4.

---

## 1. Qué se hizo

### 1.1 Recalibración por métrica y grupo de ligas (decisión 4 de la F8; `validacion/recalibracion.py`)

- **Método.** Igual que la v3.2 (`bbnorm3/examen.py`):
  - con los casos de la temporada objetivo anterior (T − 1) se mide e = |y − mediana| / semiancho del 80 %;
  - k = cuantil 80 % de e por métrica × (el del grupo / el global);
  - todos los cuantiles se reescalan alrededor de la mediana.
- **Grupos.** Los de la v3.2 (hacia la EuroLeague, FEB, NBA/G League, resto de Europa) más «misma liga», porque la v5
  también predice a quien no cambia.
- **Criterio, fijado antes de ver resultados:** mejora del WIS del examen de fichajes con IC por jugadores entero bajo 0
  y sin empeoramiento significativo en el protocolo de la F1.
- **Datos de calibración.** Para el primer año de prueba (2023-24) hizo falta la temporada 2022-23
  (`predicciones_v5_2022.parquet`, mismo código).

### 1.2 Salidas por liga de destino (`salidas/destinos.py`)

Para cada persona que jugó en 2024-25 o 2025-26 y cada liga de destino L, la fila de 2026-27 se construye como en el
examen de la F8, con L supuesta:

1. **Carrera (F4).** Nivel filtrado hasta su última temporada, proyectado con la edad, el hueco, el cambio de liga y la
   media del rol en L.
2. **Traducción.** Δλ del GLS del paso 2 (encogido) con todas las temporadas: el mismo estimador validado en la F8.
3. **Contexto publicado, ex ante:**
   - peso de la liga, tipo de jugador y compañeros, sin volumen ni estilo de liga;
   - rol en L desconocido (mezcla de transiciones) y exposición desconocida;
   - compañeros: el equipo medio de L frente a su equipo anterior.
4. **Recalibración por métrica y grupo**, con los factores estimados en los casos de 2025-26.
5. **Resúmenes.**
   - Nivel: cuantiles 10, 25, 50, 75 y 90.
   - Predictivo: 2,5, 10, 25, 50, 75, 90 y 97,5.
   - Traducción: media, DT y 10/90 en la escala del enlace, más el efecto en la mediana del nivel frente a quedarse en
     su liga.
   - P(nivel > u_k): u_k son los percentiles 25, 50 y 75 de la tasa observada en L × rol (≥ 300 min, tres temporadas);
     se usa la liga entera si L no tiene ese rol.
   - Probabilidades de cada rol y sello.

### 1.3 Sello de fiabilidad (regla fijada antes de ver las salidas; glosario)

| Sello | Regla |
|---|---|
| **Alta** | exposición acumulada ≥ 3 × n* de la métrica, ≥ 2 temporadas de historial y DT de Δλ ≤ 0,25 DT de λ entre ligas (0 si sigue en su liga) |
| **Baja** | exposición < 1 × n*, o DT de Δλ > 0,5 DT de λ entre ligas |
| **Media** | el resto |

n* son las oportunidades con fiabilidad de una temporada 0,5 (F3; mediana de ligas y temporadas).

### 1.4 F9 bis: de 14 a 26 métricas (decisión del usuario: puntos 1 a 3)

- **Zonas de tiro y % asistidas** (`datos/pista_partido.py`).
  - Tiros de jugada a jugada por jugador y **partido**, con la clasificación de zonas de la v3.2 (`bbmodel.zonas`).
  - Cinco métricas binomiales nuevas en la misma cadena:
    - medida (F3);
    - carrera (F4);
    - puentes y GLS (F6–F7);
    - bloque nuevo «zonas» de la NUTS del paso 2;
    - examen (F8);
    - salidas.
  - La capa latente (F5) conserva las 14 métricas base, así que sus perfiles no cambian.
  - **Control de calidad:** zonas sólo con ≥ 2.000 tiros con zona en la liga-temporada y ≥ 5 % en el aro. Queda fuera
    FEB1 2023-24: 116 tiros con zona y 0 % en el aro, igual en la v3.2. La CBA no tiene coordenadas: sólo % asistidas.
  - Las canastas de la jugada a jugada coinciden con las de la caja en todas las ligas salvo la CBA (51 %) y la NCAA
    (98 %).
- **TS% y eFG%** (`salidas/derivadas.py`).
  - Fórmulas exactas desde T2%, T3%, TL%, 3PAr y FTr.
  - Incertidumbre con draws conjuntos: marginales desde los cuantiles de cada componente y correlación de las capacidades
    de la F5.
- **Variantes «por 100».**
  - OREB/100, DREB/100 y BLK/100: tasa de la v5 × oportunidades por posesión de la liga.
  - STL% y STL/100: la tasa de la v5, que ya es por posesión.
  - PF/100: faltas por minuto × minutos por posesión.

### 1.5 Formato del artifact, draws, diccionario y glosario

- **`formato_v32/normalizado/<temporada>.csv.gz`.** Mismas filas y columnas que `data/modelos/v3_2/normalizado/<t>`.
  - En las 26 métricas de la v5, `<m>`, `_lo`, `_hi` y `_pctel` pasan a ser el equivalente EuroLeague 2025-26 de la v5,
    como en la v3.2:
    - nivel de la temporada en su liga + λ(EuroLeague, 2025-26) − λ(liga, t) de la traducción publicada;
    - percentil entre los jugadores de la EuroLeague de su posición.
  - Columnas añadidas: `<m>_v32*` (la v3.2 conservada), `<m>_nivel_liga`, `<m>_lo50`/`_hi50`, `<m>_obs_v5` y
    `fuente_<m>`.
- **`formato_v32/destinos/2026-27/<liga>.csv.gz`.** Una fila por jugador con, por métrica:
  - nivel y predictivo (mediana y 80 %);
  - P(nivel > mediana) y sello.
- **`2026-27/draws_liga_actual.parquet`.** 500 draws del nivel y del predictivo por jugador y métrica en su liga actual.
  No se versiona (637 MB); se regenera.
- **Diccionario y glosario.** `diccionario_columnas_v5.json` (433 columnas: ES, EN, unidades y fichero) y
  `glosario_v5.json` (9 términos ES/EN: nivel, predictivo, traducción, probabilidad de umbral, sello, punto de
  estabilización, puente intra-temporada, métrica derivada, ex ante).
  - Son ficheros hermanos: no se tocan `diccionario_columnas.json` ni `docs/glosario.md`.

---

## 2. Resultados (DATO)

### 2.1 Recalibración (`recalibracion_examen.csv`, `recalibracion_factores.csv`)

| Examen | Recalibrada frente a sin recalibrar | IC 95 % | Cobertura del 80 %: sin → con |
|---|---|---|---|
| Fichajes (criterio 9) | **−0,53 %** | −0,73 % a −0,33 % | 0,833 → 0,778 |
| Protocolo F1 (19 métricas) | −0,19 % | −0,39 % a +0,03 % | 0,806 → 0,759 |

Factores con la temporada 2025-26:
- Global 0,92.
- Por grupo: misma liga 1,00; EuroLeague 1,06; NBA/G League 1,06; FEB 0,94; resto de Europa 1,00.
- Por métrica, de 0,75 (BLK%) a 1,04 (T2%).

Las métricas con más sobrecobertura se estrechan más: BLK% 0,75, media distancia 0,78, triple de esquina 0,82.

**Cobertura del predictivo por métrica (criterio 1):** en rango en 12 de 19 sin recalibrar y 16 de 19 con ella. Las
tres que quedan fuera infracubren con la recalibración (BLK% 0,70, triple de esquina 0,70, media distancia 0,72), y
más entre quienes cambian de liga:

| Métrica | Cobertura recalibrada (cambios de liga) |
|---|---|
| BLK% | 0,64 |
| Triple de esquina | 0,67 |
| Media distancia | 0,70 |

**LECTURA.** Son métricas discretas con muchos ceros. El factor por métrica, estimado con todos los casos (la mayoría
siguen en su liga), es demasiado estrecho para quien cambia. **RIESGO** (§9).

### 2.2 Métricas nuevas en sus capas

| Métrica | Medida F3: cob. 80 | Carrera F4: cob. 80 | Nivel simulado: cob. 80 | Nivel v5 / v3.2 (ancho) |
|---|---|---|---|---|
| % en el aro | 0,807 | 0,793 | 0,795–0,812 | 0,69 |
| % cortos | 0,805 | 0,814 | 0,793–0,815 | 0,72 |
| % media distancia | 0,800 | 0,830 | 0,787–0,804 | 0,67 |
| % triple de esquina | 0,793 | 0,817 | 0,791–0,810 | 0,72 |
| % asistidas | 0,806 | 0,794 | 0,795–0,805 | 0,60 |

- Medida: modelo jerárquico con σ por rol y deriva, como las 14.
- Nivel: el intervalo del nivel es un 28–40 % más estrecho que el publicado por la v3.2.
- LOLO de λ en las zonas: cobertura 0,70 sin los puentes de la misma temporada y 0,76 sin traspasos. Más baja que en las
  14 (0,80).
- Las 14 métricas base no cambian en la F3 (diferencia 0 en todos los hiperparámetros) y apenas en la F4 (nivel: máximo
  0,004 en la escala del enlace).

### 2.3 Protocolo de la F1 con las métricas nuevas y derivadas (`protocolo_f1_publicada.csv`)

| Métrica | Casos | v5 frente a v3.2 | IC 95 % | Cob. 80 v5 | Cob. 80 v3.2 |
|---|---|---|---|---|---|
| % en el aro | 963 | **+4,0 %** | +0,7 % a +7,7 % | 0,812 | 0,836 |
| % cortos | 947 | +2,9 % | −0,4 % a +5,9 % | 0,829 | 0,808 |
| % media distancia | 957 | **+8,1 %** | +5,0 % a +11,4 % | 0,813 | 0,829 |
| % triple de esquina | 951 | **+8,3 %** | +4,2 % a +12,6 % | 0,833 | 0,792 |
| % asistidas | 1.129 | 0,0 % | −2,7 % a +2,9 % | 0,795 | 0,797 |
| eFG% (derivada) | 1.143 | +1,3 % | −2,2 % a +4,5 % | 0,773 | 0,829 |
| TS% (derivada) | 937 | −0,3 % | −3,8 % a +3,5 % | 0,799 | 0,827 |
| **Global (19 métricas + 2 derivadas)** | 17.504 | **+2,4 %** | +1,4 % a +3,4 % | 0,806 | 0,809 |

- El examen de fichajes frente a la v3.3 no cambia: −7,6 %, IC −8,7 % a −6,4 %; sólo incluye las 5 métricas comunes.
- Mediana menos observado en eFG%: +0,5 puntos la v5 y −0,7 la v3.2. En TS%: +0,2 y −0,9.

### 2.4 Salidas (`2026-27/destinos.parquet`, `meta.json`)

- **Volumen.** 5.515.272 filas, 11.246 jugadores, 20 ligas de destino, 19 métricas modeladas y 7 derivadas.
- **Sello:**

| Escenario | Alta | Media | Baja |
|---|---|---|---|
| Sigue en su liga | 46,6 % | 23,3 % | 30,1 % |
| Cambia de liga | 23,6 % | 31,5 % | 44,9 % |

- **Anchura relativa a la mediana de cada métrica:**

| Sello | Nivel | Predictivo |
|---|---|---|
| Alta | 0,91 | 0,88 |
| Media | 0,97 | 0,94 |
| Baja | 1,15 | 1,50 |

- **Probabilidades de umbral (criterio 5, ahora con 19 métricas).** Error de calibración 0,014–0,030 según el umbral.
  - Peores: triple de esquina en el percentil 25 (0,106, casi sin habilidad: 0,04) y media distancia en el 75 (0,081).

### 2.5 Formato para el artifact (`formato_v32/`; versión provisional hasta la traducción definitiva)

- **Normalizado por temporada.** 6 temporadas, 111 MB; 2024-25: 9.264 filas, como la v3.2, y 1.075 columnas (879 de
  la v3.2 + 196 nuevas). No falta ninguna columna de la v3.2.
- **Cobertura de la v5:** 7.656 filas con alguna métrica de la v5 (`fuente_norm` = «V5+V3.2»); 1.608 sólo con la v3.2,
  porque no tienen persona v5.
- **Destinos.** 20 ligas, 119 MB.
- **v5 frente a v3.2 en las mismas filas** (2024-25, equivalente EuroLeague 2025-26):

| Métrica | Filas | Correlación | Mediana v5 | Mediana v3.2 | Ancho 80 % v5 | Ancho 80 % v3.2 |
|---|---|---|---|---|---|---|
| Pts/100 | 7.538 | 0,95 | 14,8 | 15,4 | 7,0 | 6,4 |
| T2% | 7.216 | 0,87 | 49,6 | 48,9 | 8,6 | 8,1 |
| T3% | 6.748 | 0,82 | 32,1 | 30,0 | 6,6 | 6,8 |
| USG% | 7.538 | 0,95 | 15,9 | 15,2 | 5,2 | 4,8 |
| AST% | 7.531 | 0,94 | 8,7 | 8,6 | 5,2 | 6,0 |
| % en el aro | 6.859 | 0,94 | 28,7 | 26,3 | 14,8 | 13,5 |
| % media distancia | 6.859 | 0,83 | 5,9 | 5,4 | 5,6 | 6,2 |
| % triple de esquina | 6.859 | 0,80 | 5,4 | 4,9 | 5,9 | 5,1 |
| % asistidas | 7.015 | 0,91 | 61,9 | 64,0 | 15,6 | 17,9 |
| eFG% | 6.168 | 0,89 | 50,1 | 48,5 | 6,5 | 7,6 |
| TS% | 6.168 | 0,91 | 53,3 | 51,8 | 6,4 | 7,4 |
| OREB/100 | 7.538 | 0,96 | 1,86 | 1,86 | 1,12 | 1,17 |
| BLK/100 | 7.538 | 0,93 | 0,42 | 0,24 | 0,42 | 0,40 |
| STL% | 7.538 | 0,80 | 1,60 | 1,41 | 0,74 | 0,70 |
| PF/100 | 7.538 | 0,88 | 7,2 | 7,0 | 2,7 | 2,5 |

**LECTURA.**
- Las dos versiones ordenan a los jugadores de forma parecida (correlación 0,80–0,96).
- El ancho del 80 % en esta tabla es el **equivalente EuroLeague**: suma la incertidumbre del nivel y la de la
  traducción. Por eso es parecido al de la v3.2, aunque el nivel en su liga sea un 40 % más estrecho (§2.2).
- **BLK% (y BLK/100):** la mediana del nivel de la v5 (1,0 % en su liga) supera la del observado (0,6 %), sobre todo
  en los exteriores (0,53 frente a 0,22).
  - El encogimiento en la escala logit hacia la media del rol sube a quien tiene pocos tapones: un suceso raro, con
    muchos ceros.
  - En el examen fuera de muestra, el predictivo queda algo alto en BLK% y en media distancia (PIT medio 0,44 y 0,43).
    **VERIFICAR** (§6).

---

## 3. Cómo activar la v5 en el artifact (sin modificarlo ahora)

1. **Tablas normalizadas** (Mesa, explorador de normalización, Tabla de datos).
   - Las genera `bbactualiza/artefacto.py::normalizados()`, que lee `data/modelos/v3_2/normalizado/<t>.csv.gz` y se
     queda con las columnas del dataset v1.
   - Para activar la v5 basta con que lea `data/v5/salidas/formato_v32/normalizado/<t>.csv.gz`. Tiene las mismas
     columnas, más las nuevas, que esa función descarta.
   - Recomendación: un selector «Normalización: v3.2 / v5» que elija la carpeta, y `fuente_norm` = «V5+V3.2» en lugar de
     fijar «V3.2».
   - Por métrica, `fuente_<m>` dice de qué versión viene cada valor. Los índices globales y el RAPM siguen en la v3.2.
2. **Proyección por liga de destino** (nuevo).
   - `formato_v32/destinos/<temporada>/<liga>.csv.gz`, que hoy no consume ninguna vista.
   - Necesita una vista o un filtro nuevo; es una funcionalidad añadida, no una sustitución.
3. **Rama.** La v5 vive en `claude/sweet-turing-5ti6hi` y producción en `claude/jolly-thompson-qczxl4`: hay que
   fusionar antes de activar.
4. **No se elimina nada de la v3.2.** Volver atrás es devolver el selector a «v3.2».

---

## 4. Interpretación (LECTURA)

1. **Las salidas son las del contrato del encargo.** Separan lo que el producto necesita mostrar:
   - capacidad (nivel, estrecho);
   - expectativa de la temporada siguiente (predictivo, ancho);
   - efecto del cambio de liga (traducción);
   - probabilidad de estar por encima de la referencia de la liga (umbrales);
   - cuánto fiarse (sello).
2. **El sello hace lo que debe:** «baja» marca a quien tiene poca exposición o cambia a una liga mal conectada, y ahí el
   predictivo es un 50 % más ancho.
3. **En las zonas, la v5 mide bien pero traduce peor que la v3.2.**
   - Su nivel es más estrecho y está calibrado.
   - En los cambios de liga pierde en aro, media distancia y triple de esquina. Esas zonas dependen del sistema y de la
     calibración de coordenadas de cada liga, que λ sólo recoge como un desplazamiento.
   - La CVAE de la v3.2 comparte información entre métricas y aprende el cambio de perfil de tiro.
4. **TS% y eFG% derivadas empatan con la v3.2**, con un intervalo algo estrecho en eFG% (0,77 frente a 0,83).

## 5. Supuestos (SUPUESTO)

1. **La correlación del predictivo es la de las capacidades (F5)** en TS% y eFG%. Si el ruido de temporada de los
   componentes estuviera menos correlacionado, el intervalo derivado sería algo más estrecho de lo debido. Coincide con
   la cobertura de eFG% de 0,77.
2. **Las variantes por 100 usan la razón de la liga, no la del jugador.** Un jugador en un quinteto de ritmo atípico se
   desviaría. Es una conversión de unidades, no un modelo.
3. **Compañeros: equipo medio de la liga de destino.** El escenario con un equipo concreto es el de la proyección
   condicionada.
4. **Umbrales por rol de la última temporada.** Si cambia de rol en la liga de destino, la referencia sería otra.

## 6. Riesgos y verificaciones pendientes (RIESGO · VERIFICAR)

1. **RIESGO · recalibración en métricas discretas:** BLK%, triple de esquina y media distancia infracubren (0,70–0,72;
   0,64–0,70 al cambiar de liga). El criterio fijado se cumple en el agregado.
   - **Propuesta:** excluir de la recalibración las métricas donde empeora la cobertura de los cambios de liga. Es un
     cambio posterior a ver los resultados y se trata como tal.
2. **RIESGO · zonas frente a la v3.2:** pierde un 4–8 % en aro, media distancia y triple de esquina.
   - **Opción:** publicar esas tres zonas con la v3.2 en el híbrido (`fuente_<m>` = V3.2) hasta mejorarlas.
3. **VERIFICAR · sesgo al alza en BLK% y media distancia:** PIT medio 0,44 y 0,43; el 52 % y el 56 % de los
   observados quedan por debajo de la mediana predicha. Revisar el prior del rol en métricas raras (F3) antes de
   activarlas.
4. **VERIFICAR · TS% y eFG% sin probabilidades de umbral propias:** faltan los percentiles de la liga × rol de esas dos
   métricas.
5. **VERIFICAR · NUTS del paso 2:** zonas hecha; volumen_papel en curso; tiro por repetir. El formato v3.2 y el criterio 4
   esperan a la traducción publicada completa.
6. **RIESGO · volumen:** el parquet completo (656 MB) y los draws (637 MB) no se versionan; se regeneran con la orden de
   la cabecera.

## 7. Diagnósticos de inferencia

- **Salidas:** 400 draws por exposición × 4 exposiciones por caso; semilla por métrica (`20261117 + crc32`); 3.000 casos
  por trozo; dos procesos (54 y 58 min).
- **NUTS del paso 2 con las identidades revisadas:**

| Bloque | Estado | R̂ máx. | ESS mín. (centro / colas) | Divergencias |
|---|---|---|---|---|
| defensa_cuidado | Hecho | 1,01 | 793 / 434 | 3 en 3.000 |
| tiro | Por repetir con 1.500 + 1.500 draws por cadena | 1,03 (DT base de TL%) | 210 / 89 | 0 |
| zonas | Hecho | 1,01 | 371 / 580 | 0 |
| volumen_papel | En curso | | | |

## 8. Verificación de no regresión

- Nada de la v1, la v3.2, la v3.3 ni la v4.x cambia: los formatos se escriben en `data/v5/salidas/`.
- Diccionario y glosario van en ficheros hermanos.
- Las 14 métricas base de la F3 son idénticas tras añadir las 5 nuevas. La F5 no se toca.
- **Decisión 5 (republicar capas corregidas).** Publicarlas desde esta rama habría deshecho en los artifacts la Liga U y
  la actualización del 10-11 de producción. Por decisión del usuario se abrió
  [UEBNET/baskonia#7](https://github.com/UEBNET/baskonia/pull/7) hacia `claude/jolly-thompson-qczxl4`:
  - sólo las dos correcciones de código, con sus tests;
  - los pasos para regenerar y republicar allí con las 21 ligas.
- Tests: 6 nuevos en `test_salidas_f9.py` (sello, grupos, factores de recalibración, umbrales, derivadas, por 100) y 1
  en `test_validacion_f8.py` (alineación de factores).
- Suite completa en verde: **380 passed**.

## 9. Riesgos detectados y decisiones que requieren al usuario

1. **Activación de la v5 en los artifacts:**
   - **(A)** tras la F9, con el selector y el híbrido por métrica (§3);
   - **(B)** esperar a la F10.
2. **Zonas en las que la v5 pierde frente a la v3.2** (aro, media distancia, triple de esquina): ¿se publican con la v5 o
   con la v3.2 hasta mejorarlas?
3. **Recalibración en métricas discretas** (BLK%, triple de esquina, media distancia): ¿se mantiene en todas (criterio
   fijado) o se excluye donde infracubre a quien cambia de liga?
4. **PR [UEBNET/baskonia#7](https://github.com/UEBNET/baskonia/pull/7)** a producción: revisión y fusión, y después la
   regeneración con 21 ligas.

## 9 bis. Decisiones del usuario (12-11-2026)

1. **Activación (B):** la v5 **no** se activa en los artifacts hasta la F10. El formato queda preparado.
2. **Zonas de aro, media distancia y triple de esquina:** en el formato publicado se quedan con la **v3.2**
   (`publicar_con_v32` en `configs/v5/f9.yaml`).
   - La v5 las sigue calculando en `destinos.parquet` para seguir mejorándolas.
   - Del formato publicado salen 23 de las 26 métricas: 16 modeladas (tiros cortos y % asistidas incluidos) y las 7
     derivadas.
3. **Recalibración:** se mantiene en todas las métricas, también en BLK%, triple de esquina y media distancia, por el
   criterio fijado.
4. **PR [UEBNET/baskonia#7](https://github.com/UEBNET/baskonia/pull/7): fusionada** en `claude/jolly-thompson-qczxl4`
   (`fd0bf66`).
   - La sesión de producción que regenera con las 21 ligas y republica **no se pudo lanzar desde aquí**: el control de
     permisos la bloqueó como despliegue a producción.
   - Instrucciones listas para lanzarla: `docs/v5/operaciones/regeneracion_produccion_pr7.md`.

## 10. Siguiente fase propuesta y ajuste de inversión

**F10 · Estudio de viabilidad aguas abajo:**
- simulador v3.3 y v4.0 con draws de la v5;
- Nivel Kerno desde el intervalo de nivel;
- Impacto y RAPM;
- Landing.

Sin NUTS nuevas, salvo las del paso 2 pendientes de la F9.

Esperando GO.
