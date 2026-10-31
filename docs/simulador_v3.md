# Simulador de encaje v3 y adaptación ascendente (ADAPT% v3)

**Código:** `bbfit/adaptacion_v3.py` (nuevo), `configs/simulation_v3.yaml` (nuevo); el motor es el de la v2
(`bbfit/simulador.py`, `artifact/atlas/simulador_v2.js` y el v2.1 publicado), **sin cambios**.
**Salidas:** `data/modelos/adaptacion/v3/`, `data/modelos/simulador/v3/`. La v2 queda intacta.

```bash
python -m bbfit adaptacion-v3                                   # priors de adaptación v3 (curva ascendente)
CERNO_SIMULADOR=v3 python -m bbfit exportar-simulador           # datos del motor del artifact con v3.1 + adaptación v3
CERNO_SIMULADOR=v3 python -m bbfit simular --jugador «…» --club «…»
python -m bbestilo exportar --salida <carpeta> --todas-las-ligas   # Atlas con las FEB (ver §4)
python -m bbnorm3.artifact --salida <carpeta>                    # «Datos Normalizados» y explorador con la v3.1
```

## 1. Qué cambia frente a la v2

| Pieza | v2 | v3 |
|---|---|---|
| Capacidad de cada jugador (θ) | `<m>_am` del dataset normalizado v1 (A+B amortiguado) | `<m>_am` del dataset **v3.1** (v2 + CVAE corregida; fuente `V31`) |
| Adaptación | curva que podía **bajar** (ver §2) | curva **ascendente** hacia el nivel adaptado (§3) |
| Partidos por temporada en destino | valor por defecto (34) para FEB1, FEB2, ACB, LBA… | partidos reales de 2025-26 (FEB1 32, FEB2 26, LBA 28, LNB 30, BSL 30, GBL 24…) |
| Contracción de la adaptación | 0,55 (calibración de Δ de la fase 7) | 1 (la forma se mide directamente; no hay Δ de nivel) |
| Pesos de utilidad, calibración y Fit | ajustados con el examen v2 | **los mismos** (copiados; no se han reentrenado, ver §5) |

## 2. Por qué la ADAPT% de la v2 bajaba [DATO + LECTURA]
La trayectoria de la v2 era `T(g) = (1 + c·Δ_temp) · (1 + D·e^(−g/κ)) / (1 + D·w̄)`:
* **Δ_temp** = cuánto rinde en su temporada quien cambia de liga frente a lo que traduce la normalización. Sale
  positivo en el 68 % de las celdas (mediana +2,7 %): es un **sesgo de nivel**, no adaptación.
* **D** = hueco inicial dentro del jugador **neto** del «arranque de temporada» de los que siguen en su equipo:
  +0,9 % a nivel global. Neto de ese arranque, los traspasos no arrancan peor, y la curva empieza por encima de 100
  y baja.
* κ de la interfaz ~340 partidos: un efecto casi plano que no se cierra nunca.

Por eso la curva era convexa y descendente: daba a entender que el jugador rinde peor a medida que avanzan los
partidos, justo lo contrario de lo que significa adaptarse.

## 3. Definición v3 [decisión del CEO]
**ADAPT%(g) = 100 · (1 + D·e^(−g/κ)), con D ≤ 0**: qué fracción de su nivel **ya adaptado** rinde el jugador en el
partido g de su nueva liga. Empieza por debajo de 100 y sube hasta 100 cuando está establecido.
* D y κ salen de la curva **bruta** dentro de jugador de los traspasos: su propio arranque en la liga nueva, sin
  restar el de los que se quedan. Origen: `data/modelos/adaptacion/curvas.csv`, población «traspasos_bruto».
* Por grupo de nacionalidad, contraídos hacia el global (bayes empírico).
* Acotados a D ≤ 0: empezar por encima del nivel adaptado no es adaptación.
* El **nivel** lo pone la normalización v3.1, validada directamente sobre el rendimiento real de quienes cambian de
  liga. El antiguo Δ de nivel ya no se aplica.

Resultados (`data/modelos/adaptacion/v3/`, índice de producción) [DATO]:

| Grupo | Partido 1 | 10 primeros | Temporada (34) | 90 % del hueco cerrado en |
|---|---|---|---|---|
| Global | 95,6 % | 99,0 % | 99,7 % | 3,8 partidos |
| De NBA a G League o al revés | 93,5 % | 98,3 % | 99,5 % | 4,9 |
| Hacia EE. UU. | 94,6 % | 98,6 % | 99,6 % | 4,5 |
| Nacional en su país (p. ej. Primera FEB → ACB) | 96,7 % | 99,2 % | 99,8 % | 4,3 |

* Puntos y TS% también ascienden.
* El uso (USG) no muestra hueco, así que queda en 100 % (acotado).
* La v3 no confirma el «90 % → 100 %» del ejemplo: los datos dicen que el primer partido está entre un 93 % y un
  98 % del nivel adaptado y que la adaptación casi se completa en 4-6 partidos.

**Cómo lo calcula el motor sin tocar su código.** La tabla de priors v3 lleva `delta_temporada = D·w̄_G`,
`D_forma = D` y `κ_forma = κ`, con contracción 1. El motor calcula
`curva(g) = (1 + D·w̄)·(1 + D·φ_g)/(1 + D·w̄) = 1 + D·φ_g`, la ADAPT% de la temporada (`100·(1 + D·w̄)` ≤ 100) y la
de los N primeros partidos (la media de la curva). Comprobado con el motor publicado (v2.1). Ejemplo: Matulionis →
Burgos, partido 1 95,6 %, partido 3 98,7 %, partido 6 99,8 %, desde el 9 100 %.

**Limitación.** La producción de la temporada se multiplica por `1 + D·w̄` (≈ −0,2 % a −0,5 %). La v3.1 ya predice el
promedio de temporada de quien cambia de liga, así que este pequeño descuento se cuenta dos veces. Es del orden de
décimas y se acepta para no tocar el motor.

## 4. Las FEB en el simulador [DATO]
* Los **datos** del simulador ya incluían las FEB, como destino (35 clubes de Primera, 56 de Segunda y 277 de Tercera
  en las dos temporadas base) y como origen (514, 722 y 3.607 registros).
* La **página** construye la lista de ligas («Tu club») y el buscador de fichajes a partir de los datos del Atlas de
  estilos (`atlas/estilos/*.json`). Esos datos se exportaban sólo con las 12 ligas con que se entrenó la red VaDE
  (comentario en el código: «las FEB no tienen estilo VaDE hasta que se reentrene la red»). Por eso **las FEB no
  aparecían en el simulador**.
* Arreglo, sólo de datos (sin tocar la página): `bbestilo exportar --todas-las-ligas` exporta las 15 ligas. Las FEB
  se **proyectan** con las escalas, el índice de nivel y el neutralizador de las 12 ligas de la red
  (`conjunto_proyectado`), así que la red las ubica en el mapa sin reentrenarse. Su estilo unificado (fase 6) sí se
  ajustó con ellas.
* Limitación: el mapa VaDE de las FEB es una proyección, no un reentrenamiento. Los estilos oficiales de la v3 son
  los unificados.

## 5. Lo que no se ha rehecho
* **Pesos de utilidad, calibración y Fit**: son los de la v2. Reentrenarlos exige el examen completo del simulador
  (`pesos-simulador`, `backtest`), que no se ha ejecutado. El componente «adaptación» del Fit ahora vale entre −5 y 0
  (antes, alrededor de +2) y su peso es el ajustado con la v2.
* **Traducción a la liga de destino**: el motor sigue usando las constantes de la normalización amortiguada (δ, s, ψ
  por liga) para expresar la capacidad v3.1 en la liga de destino. Un sustituto lineal de la v3.1 y la covarianza por
  pares en el motor quedan propuestos (v3.2).
* **Candidatos de 2026-27**: salen de la fase de roles (`data/modelos/roles`), calculada con los datos hasta el 14-10.
  Para incluir los partidos nuevos hay que rehacer `python -m bbfit roles --temporadas 2026-27`.
* **Histórico de fichajes v3** (`historico`): no regenerado.
