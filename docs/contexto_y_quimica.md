# Jugada a jugada en los modelos: zonas de tiro, contexto de nivel y química de estilos

> Código: `bbmodel/zonas.py`, `bbmodel/pista.py`, `bbmodel/contexto.py`, `bbmodel/interacciones.py`,
> `bbestilo/quimica.py` · Resultados: `data/modelos/pista/`, `data/modelos/contexto/`, `data/modelos/interacciones/`,
> `data/modelos/estilos/interacciones.json` · En la Mesa: pestaña «Quintetos y conexiones», vistas «Pista» y
> «Contexto de nivel», subpestaña «Contexto de nivel» de la Normalización de ligas y Atlas de Estilos.

```bash
python -m bbmodel pista            # zonas de tiro, canastas asistidas y RAPM por jugador-equipo (≈ 1 min)
python -m bbmodel ajustar          # algoritmo A con las 33 métricas (≈ 13 min)
python -m bbmodel ajustar-b        # algoritmo B (≈ 11 min; un hilo de BLAS)
python -m bbmodel dataset-normalizado
python -m bbmodel contexto         # contexto de nivel y sensibilidad de cada métrica (≈ 2 min)
python -m bbmodel interacciones    # efectos X → Y entre compañeros (≈ 7 min)
python -m bbestilo barrido         # número de estilos antes de entrenar
python -m bbestilo entrenar        # VaDE con 17 rasgos (≈ 60 min en 4 núcleos)
python -m bbestilo analisis && python -m bbestilo quimica && python -m bbestilo exportar --salida data/artifact/atlas/estilos
python -m bbmodel mesa-quintetos   # datos de la pestaña «Quintetos y conexiones»
```

## 1. Zonas de tiro con coordenadas de 8 fuentes distintas

Cada fuente publica las coordenadas de los tiros en su propio sistema: centímetros desde el aro (EuroLeague,
EuroCup), décimas de pie desde el aro (NBA, G League), milímetros con los ejes cambiados (ACB), porcentaje de la
pista completa con dos canastas (LBA, LNB) o unidades propias (BBL). `zonas.py` ajusta, por liga y temporada, la
posición del aro y la escala para que la línea de triple oficial (FIBA: arco de 6,75 m y esquinas a 6,60 m; NBA:
7,24 m y 6,71 m) separe lo mejor posible los tiros que la propia fuente anota como de 2 y de 3. Acierto de la
separación en las 53 ligas-temporada con tiros: **99-100 %** (`data/modelos/pista/calibracion.json`). Zonas: aro
(< 1,8 m), corta (1,8-4,25 m), media distancia, triple de esquina y triple frontal. Acierto medio en el aro:
62-68 % según la liga.

## 2. Métricas de pista en la normalización (algoritmos A y B)

Ocho métricas nuevas en el catálogo (`bbmodel/metricas.py`, grupo «Pista»), traducidas a la EuroLeague 2025-26 igual
que las 25 de caja: % de tiros en el aro, cortos, de media distancia y triples de esquina, % de canastas propias
asistidas, y RAPM, ORAPM y DRAPM (exposición: posesiones en pista). Examen fuera de muestra (412 cambios de liga),
mejora frente a «mismo percentil»: RAPM +46 % (A+B), ORAPM +49 %, DRAPM +40 %, zonas y asistidas +16-23 %. Las 25
métricas de caja no cambian en A (cada métrica se ajusta por separado) y se mueven ±2 puntos en B. Donde no hay
jugada a jugada observado (LNB 2020-21; RAPM de la BBL 2020-23) el valor combinado queda en blanco; la estimación de
la red B se conserva aparte (`<m>_B`).

Tipo de cambio del RAPM: el jugador medio de cada liga vale en la EuroLeague NBA +0,03, ACB −0,30, EuroCup −0,39,
LNB −0,43, LBA −0,46, G League −0,58 y BBL −0,71 desviaciones típicas de impacto (300-1.000 puentes por liga).

## 3. Contexto de nivel: con quién y contra quién juega cada uno

No es lo mismo promediar 15 puntos al lado del MVP de la EuroLeague que en un equipo de la BBL.

* **Nivel L** de cada jugador-liga-temporada: el índice del Atlas (media de los z con signo de PER, Game Score/40,
  WS/40, ORtg, DRtg, puntos/100, TS% y eFG% normalizados A+B; 0 = jugador medio de la vara común). Orden de las ligas
  por nivel medio: NBA > EuroLeague > ACB > G League > EuroCup > LNB > LBA > BBL.
* **Contexto en pista** (tramos del jugada a jugada): media de L de sus 4 compañeros y de los 5 rivales en cada
  tramo, ponderada por segundos. **Contexto de plantilla**: media de L de sus compañeros ponderada por minutos (existe
  en todas las ligas y temporadas). Desviación = contexto − el de un jugador medio de su liga y temporada.
* **Sensibilidad β** de cada métrica (`data/modelos/contexto/sensibilidad.csv`): regresión con efecto fijo de persona
  (el mismo jugador en distintos entornos) de su capacidad en la vara EuroLeague sobre la desviación del contexto de
  plantilla y la de rivales, con tramos de edad; bootstrap de personas. Se usa el contexto de plantilla y no el de
  pista porque el de pista mezcla el rol (quien mejora pasa a jugar con los titulares).

| Métrica | β por unidad de nivel de los compañeros | Lectura |
|---|---|---|
| USG% | −0,40 | con mejores compañeros, menos uso |
| AST% | −0,35 | reparte menos |
| Puntos/100 | −0,28 | anota menos |
| DRtg individual | −0,85 | mejor DRtg (la defensa de equipo se reparte) |
| WS/40 | +0,43 | más éxito colectivo atribuido |
| % canastas asistidas | +0,31 | más canastas de pase |
| % triples de esquina | +0,33 | rol de tirador |
| % media distancia | −0,18 | menos tiro propio |
| RAPM | +0,40 | parte es contexto que el RAPM no aísla del todo (contracción ridge) |

Uso: el dataset normalizado incluye `<m>_ctx` (con compañeros de nivel medio) en las 27 métricas con efecto claro
(|β| > 2 errores típicos), y el Atlas proyecta a cualquier jugador al contexto de una plantilla de la EuroLeague:
`x_destino = T⁻¹(T(x) + τ_pos · β · Δ)`, Δ = desviación del contexto en el destino − la de su equipo de origen.

## 4. Efectos entre compañeros (X → Y)

Para cada pareja de compañeros, con Y en pista se compara a Y cuando X está en pista y cuando no: cuota de tiro (sus
tiros de campo / los del equipo), eFG%, % de canastas asistidas, % de tiros en el aro y puntos por 100 posesiones,
con el número de tiros en cada situación. 122.322 parejas dirigidas con 60+ minutos juntos (temporada regular, 8
ligas, 7 temporadas). Son asociaciones en pista, no pruebas causales: quién juega con quién lo decide el entrenador.

## 5. Química de estilos (estilo × estilo, a igual nivel)

Con la probabilidad de estilo de cada jugador (VaDE de 17 rasgos) y su nivel L, regresión ponderada de cada efecto
sobre p_X ⊗ p_Y con el nivel de X, el de Y y su interacción como controles; errores por bootstrap de equipos-temporada
(`bbestilo/quimica.py` → `interacciones.json`):

    Δ_Y = p_X · M · p_Y + β_X·(L_X − c) + β_Y·(L_Y − c) + (L_X − c)·(γ · p_Y)

* **Efecto del nivel del compañero («efecto MVP»)**: un compañero una unidad de nivel mejor baja la cuota de tiro de Y
  (−0,77 puntos) y sus puntos/100 (−0,76), pero sube su eFG% (+0,40) y su % de canastas asistidas (+1,33).
* **Por estilo**: los compañeros de «Creación individual» quitan tiros al resto; los de «Circulación y triple» y
  «Pintura física» los dan; la «Pintura física» baja el eFG% de los demás (menos espacio); «Creación individual» y
  «Exterior y presión» suben las canastas asistidas de sus compañeros.
* **Sinergia de pareja** (net de la pareja frente a lo esperado por el RAPM de los 10 en pista, simétrica):
  dos «Circulación y triple» +1,0 puntos/100, «Exterior y presión» + «Circulación y triple» +0,9, dos «Creación
  individual» −1,0; a más nivel conjunto, más sinergia (+0,47 por unidad).

## 6. Limitaciones

Asociaciones, no causas (selección de minutos y rivales); el RAPM de una temporada es ruidoso y arrastra parte del
contexto; las zonas dependen de la calidad de las coordenadas de cada fuente (calibración ≥ 99 %); el contexto se
mide con un índice de nivel de caja; sin quintetos en BBL 2020-23 (sólo tiros y asistencias) ni jugada a jugada en
LNB 2020-21; NBA y G League 2026-27 sin empezar.
