# Algoritmo B — «ADN del jugador» (red neuronal multitarea)

> Código: `bbmodel/algoritmo_b.py` · Resultados: `data/modelos/algoritmo_B/` · Pestaña «Normalización de ligas» de la Mesa.
> Comandos: `python -m bbmodel ajustar-b` (5 redes × 3.000 pasos) · `python -m bbmodel validar-b` · `python -m bbmodel mesa-normalizacion`.

## 1. La idea en una frase

Cada jugador tiene un **ADN**: 8 números que describen cómo juega y cuánto vale y que **no dependen de dónde juega**.
La estadística que vemos es ese ADN *expresado* en un sitio concreto (liga, temporada, posición y equipo). Para
saber qué haría en la EuroLeague basta con expresar su ADN con la «gramática» de la EuroLeague 2025-26 y un equipo medio.

A diferencia del algoritmo A, que traduce cada métrica por separado con una recta, B aprende las **25 métricas a la
vez** y separa explícitamente **nivel, liga, temporada, posición y equipo**.

## 2. Modelo

Todas las métricas pasan antes por la misma transformación y el mismo ruido de muestra que el algoritmo A
(paso 1, `suerte.valor_y_exposicion`) y se estandarizan con los jugadores de 300+ minutos. Se usan las filas
jugador-liga-temporada con **150+ minutos** y posición conocida (E/A/I).

```
z_{i,t} = u_i + A[edad_{i,t}] + e_{i,t}                 ADN (d = 8) del jugador i en la temporada t
          u_i ~ N(m_{L(i)}, I)    m_L: ADN medio de su liga principal; m_EuroLeague = 0
          e_{i,t} ~ N(0, η² I)    cambio de un año concreto (η = 0,01)
          A[edad]                 curva de edad común; A[s/d] = 0 (edad desconocida)
h       = tanh(W1 z + c_l)                              capa oculta (32 neuronas) desplazada por la liga (FiLM)
x̂_{r,k} = b_{l,t,pos,k} + T_{equipo-temporada,k} + [(W2 + V_l) h]_k
y_{r,k} ~ N(x̂_{r,k}, v_{r,k} + ψ_{l,k})                 v = σ²/n (ruido de muestra conocido)
```

* `b_{l,t,pos}`: entorno de liga × temporada × posición (147 grupos). Normaliza ritmo, reglamento, criterio de anotación y año.
* `T_{equipo-temporada}` ~ N(0, σ²_T,k): efecto de su equipo (1.032 equipos-temporada). σ²_T se estima por bayes empírico.
* `V_l` ~ N(0, σ²_V): lectura propia de cada liga sobre la capa oculta (la misma capacidad no se traduce igual en cada liga).
* Entrenamiento: máximo a posteriori con Adam y tasa coseno; gradientes escritos a mano y comprobados numéricamente
  (error relativo de 1e-5 a 1e-9). Los ADN se aprenden directamente («auto-decoder»): para un jugador nuevo se
  reoptimiza sólo su ADN con la red congelada.
* Incertidumbre: aproximación de Laplace del ADN de cada jugador-temporada + **conjunto de 5 redes** con semillas distintas.

**Traducción.** `x_EL = b_{EL,2025-26,pos} + (W2 + V_EL)·tanh(W1 z + c_EL)` (equipo medio, T = 0), destransformada a
la escala original; percentil frente a los jugadores de EuroLeague 2025-26 de su posición.

## 3. Ajuste de hiperparámetros (sin mirar el examen)

La primera versión (d = 6, η = 0,35, 50+ minutos) **sobreajustaba**: ψ → 0, intervalos demasiado anchos
(cobertura ≈ 1,0) y perdía contra A en 23 de 25 métricas. Se ajustaron d, η y el umbral de minutos **sólo con el corte
2022-23 → 2023-24**, que no forma parte del examen. Configuración final: d = 8, H = 32, η = 0,01, 150+ minutos
(error cuadrático medio relativo a «mismo percentil» en ese corte: B 0,622, A 0,569, A+B 0,527).

También se corrigió un error de datos que afectaba a los dos algoritmos: el año de nacimiento se guardaba por liga y
no por persona, y el tramo «edad desconocida» actuaba como comodín de liga (la ACB salía por encima de la
EuroLeague). Con el año a nivel de persona, las filas ACB con edad conocida pasaron del 0 % al 64 %, y A se reajustó.

## 4. Modelo final

5 redes · 12.474 filas · 3.923 personas · 10.921 jugador-temporadas · 1.032 equipos-temporada · 147 entornos.

Hallazgos del propio ajuste, que conviene leer con honestidad:

* **σ_equipo** queda en el suelo (0,07 desviaciones) en todas las métricas salvo **DRtg (0,63)**. Con estos datos el
  efecto de equipo sólo se separa con claridad en la defensa; en el resto lo absorbe el ADN del jugador (casi ningún
  jugador cambia de equipo dentro de una temporada, así que equipo y jugador están confundidos).
* **ψ ≈ 0,0005**: la red explica casi todo lo que no es ruido de muestra. La calibración descansa en Laplace + conjunto
  y en el ruido σ²/n; la cobertura del 80 % sale entre 0,82 y 0,94 (0,61 en DRtg).
* **Curva de edad casi nula** (normas ≈ 0,015): con η pequeño, el ADN por temporada ya recoge la evolución.

## 5. Nivel de cada liga: A frente a B

Posición media en la EuroLeague (en desviaciones típicas de los jugadores EuroLeague de su posición) de los jugadores
de cada liga con 300+ minutos en 2025-26. Celda: **A / B**. En DRtg, positivo = peor defensa.

| Métrica | NBA | G League | ACB | EuroCup | LNB | LBA | BBL |
|---|---|---|---|---|---|---|---|
| PER | +0,58 / +0,82 | −0,36 / −0,52 | −0,47 / −0,39 | −0,73 / −0,58 | −0,56 / −0,92 | −0,79 / −0,79 | −0,97 / −1,30 |
| Game Score por 40' | +0,55 / +0,87 | −0,30 / −0,51 | −0,41 / −0,38 | −0,69 / −0,53 | −0,51 / −0,90 | −0,72 / −0,73 | −0,88 / −1,23 |
| Win Shares por 40' | −0,04 / +0,25 | −0,75 / −0,79 | −0,50 / −0,42 | −0,77 / −0,71 | – | −0,88 / −0,93 | −1,16 / −1,49 |
| Puntos por 100 posesiones | +0,81 / +1,01 | −0,02 / −0,18 | −0,30 / −0,29 | −0,42 / −0,24 | −0,41 / −0,58 | −0,41 / −0,39 | −0,57 / −0,72 |
| USG% | +1,03 / +1,12 | +0,22 / +0,07 | −0,14 / −0,14 | −0,21 / −0,04 | −0,16 / −0,25 | −0,17 / −0,13 | −0,33 / −0,30 |
| TS% | +0,08 / +0,04 | −0,85 / −0,73 | −0,54 / −0,42 | −0,83 / −0,64 | −0,85 / −0,98 | −0,98 / −0,76 | −1,03 / −1,24 |
| AST% | +0,06 / +0,47 | −0,47 / −0,43 | −0,13 / +0,02 | −0,33 / −0,11 | −0,31 / −0,32 | −0,31 / −0,24 | −0,43 / −0,35 |
| DREB% | +0,48 / +0,49 | +0,07 / −0,16 | −0,06 / −0,07 | −0,27 / −0,26 | – | −0,20 / −0,21 | −0,44 / −0,51 |
| BLK% | +0,59 / +0,55 | +0,43 / +0,31 | −0,11 / −0,11 | −0,18 / −0,29 | – | −0,21 / −0,14 | −0,23 / −0,33 |
| DRtg individual | −0,11 / −0,45 | +0,29 / +0,08 | +0,41 / +0,08 | +0,62 / +0,43 | – | +0,72 / +0,44 | +1,12 / +0,69 |

Dos métodos sin piezas en común dan el mismo orden y magnitudes muy parecidas (la mayor diferencia en PER es la de
la LNB, 0,36). B es algo más extremo en las colas (NBA más arriba, BBL y LNB más abajo) y separa el efecto de equipo
en DRtg, por eso sus niveles de DRtg son más moderados.

## 6. Examen fuera de muestra

Mismo examen que el A: se entrena con temporadas hasta t y se predice t+1 de los **412 jugadores (versión de 8 ligas; 722 con las 15 ligas) que cambiaron de
liga** (cortes 2023-24 → 2024-25 y 2024-25 → 2025-26; **88 llegadas a la EuroLeague**).
«Mejora» = 1 − ECM/ECM(mismo percentil), en %. **A+B** = media de A y B en la escala transformada.

| Métrica | A | B | **A+B** | Cob. 80 % A | Cob. 80 % B | Llegadas EL: A | B | **A+B** |
|---|---|---|---|---|---|---|---|---|
| AST% | +7,2 | +15,8 | **+20,0** | 85 % | 91 % | −13,1 | +14,8 | **+9,7** |
| Tapones por 100 pos. | +15,2 | +25,4 | **+29,2** | 85 % | 91 % | +24,1 | +37,3 | **+35,2** |
| BLK% | +18,4 | +20,3 | **+26,7** | 83 % | 91 % | +23,3 | +35,0 | **+33,0** |
| Rebotes defensivos por 100 pos. | +18,4 | +9,2 | **+23,2** | 86 % | 94 % | +14,9 | +24,6 | **+30,1** |
| DREB% | +18,2 | +4,4 | **+21,1** | 86 % | 94 % | +14,7 | +19,9 | **+28,6** |
| DRtg individual | +35,6 | +37,8 | **+43,9** | 83 % | 61 % | +56,1 | +55,4 | **+60,2** |
| eFG% | +5,7 | −4,3 | **+9,7** | 82 % | 93 % | −9,2 | −24,0 | **−9,2** |
| T2% | +3,5 | −3,9 | **+5,7** | 82 % | 86 % | −10,7 | −34,4 | **−15,8** |
| T3% | +2,8 | +10,4 | **+9,6** | 80 % | 88 % | +5,4 | +9,2 | **+10,0** |
| Triples / tiros de campo (3PAr) | +6,5 | −0,2 | **+15,3** | 81 % | 92 % | +6,3 | +5,0 | **+17,5** |
| TL% | +5,5 | +4,4 | **+11,3** | 89 % | 87 % | +4,2 | +10,3 | **+12,7** |
| Tiros libres / tiros de campo (FTr) | +2,0 | −4,2 | **+6,3** | 84 % | 82 % | +3,6 | +17,2 | **+21,4** |
| Game Score por 40' | +41,5 | +36,6 | **+45,7** | 84 % | 88 % | +31,0 | +40,3 | **+42,9** |
| Rebotes ofensivos por 100 pos. | +7,5 | +12,7 | **+23,3** | 84 % | 93 % | +0,3 | −8,3 | **+13,1** |
| OREB% | +1,5 | −1,2 | **+21,0** | 85 % | 93 % | −5,7 | −11,0 | **+7,2** |
| ORtg individual | +10,8 | +5,5 | **+18,8** | 85 % | 94 % | −13,8 | −16,1 | **−3,7** |
| PER | +41,4 | +35,5 | **+45,3** | 86 % | 91 % | +37,8 | +45,1 | **+49,3** |
| Faltas por 100 pos. | +12,6 | +0,9 | **+13,9** | 88 % | 89 % | +16,1 | +18,1 | **+22,0** |
| Puntos por 100 posesiones | +38,3 | +42,2 | **+46,2** | 83 % | 87 % | +29,9 | +36,9 | **+39,3** |
| Robos por 100 pos. | +1,9 | +0,2 | **+11,8** | 88 % | 94 % | +3,9 | −10,3 | **+12,8** |
| STL% | +1,6 | −0,2 | **+11,6** | 87 % | 94 % | +2,2 | −12,0 | **+11,6** |
| TOV% | +2,2 | +8,1 | **+13,2** | 84 % | 88 % | +2,9 | +19,0 | **+16,6** |
| TS% | +12,8 | +0,1 | **+15,9** | 86 % | 94 % | −2,3 | −24,0 | **−3,6** |
| USG% | +42,1 | +42,4 | **+47,5** | 80 % | 88 % | +33,0 | +22,8 | **+33,0** |
| Win Shares por 40' | +36,5 | +34,7 | **+41,9** | 87 % | 93 % | +28,7 | +46,2 | **+44,0** |

* Mediana por métrica: A +10,8 %, B +8,1 %, **A+B +20,0 %**. Llegadas a la EuroLeague: A +5,4 %, B +17,2 %, **A+B +17,5 %**.
* B gana a A en 9 de 25 métricas (14 de 25 en llegadas a la EuroLeague), sobre todo en tapones, asistencias, DRtg,
  pérdidas, T3%, uso y puntos/100. A gana en eficiencia, rebote defensivo, robos y valoraciones globales.
* **A+B gana a A en las 25 métricas** y a B en 24. Los errores de los dos métodos están poco correlacionados; por eso la
  media mejora a ambos. **Es la estimación recomendada.**
* Punto débil común: la eficiencia (TS%, eFG%, T2%, ORtg) de quien llega a la EuroLeague sigue sin mejorar al percentil.

## 7. Ficheros de salida (`data/modelos/algoritmo_B/`)

| Fichero | Contenido |
|---|---|
| `traducciones/<temporada>.csv` | Por jugador-liga-temporada y métrica: `<m>_el`, `<m>_el_lo`, `<m>_el_hi` (80 %), `<m>_pct_el`, `<m>_el_prox`, `<m>_x` |
| `nivel_por_liga.csv` | Nivel de cada liga por métrica (media y dispersión entre redes) |
| `resumen_modelo.json` | Configuración, tamaños, σ_equipo, ψ y curva de edad |
| `redes.npz` | Parámetros de las 5 redes |
| `validacion_casos.csv` | Cada predicción del examen |

La pestaña de la Mesa se alimenta de `python -m bbmodel mesa-normalizacion --salida data/artifact`, que combina A y B
y escribe `normalizacion/resumen.json` y `normalizacion/jugadores_<temporada>.json` (publicar en `datos/normalizacion/`).

## 8. Limitaciones

* Los intervalos de nivel de B (dispersión entre 5 redes) infravaloran la incertidumbre real; los de jugador usan Laplace.
* El efecto de equipo sólo se identifica bien en DRtg.
* NBA → EuroLeague es una extrapolación para las estrellas: sólo hay 67 puentes directos.
* LNB sin totales de rivales: no se traducen DRtg, WS, OREB%, DREB% ni BLK%.

## Métricas de pista (oct. 2026)

El catálogo pasa de 25 a **33 métricas**: se añaden 8 del jugada a jugada (grupo «Pista» de `bbmodel/metricas.py`;
datos de `bbmodel/pista.py`): % de tiros en el aro, cortos, de media distancia y triples de esquina (exposición:
tiros con coordenadas), % de canastas propias asistidas (exposición: canastas) y RAPM, ORAPM y DRAPM (exposición:
posesiones en pista). Examen fuera de muestra (412 cambios de liga), mejora de A+B frente a «mismo percentil»: RAPM
+46 %, ORAPM +49 %, DRAPM +40 %, zonas y asistidas +16-23 %; A+B gana a A en las 33. Las 25 métricas de caja no
cambian en A (cada métrica se ajusta aparte) y se mueven ±2 puntos en B. Detalle, contexto de nivel y química de
estilos: [`contexto_y_quimica.md`](contexto_y_quimica.md).
