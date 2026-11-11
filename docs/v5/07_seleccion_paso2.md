# F7 · Sesgo de selección en los traspasos y paso 2 de los efectos de liga (encargo v5.0 §11, revisión 1.2)

Fecha: 11-11-2026 · Kerno Analytics · normalización cruzada v5.0.
Código: `bbnorm5/ligas/seleccion.py`, `bbnorm5/ligas/resumen_paso2.py`, `bbnorm5/ligas/figuras_f7.py`, `bbnorm5/f7.py`.
Configuración: `configs/v5/f7.yaml` (la NUTS usa la de la F6, `configs/v5/f6.yaml`). Datos: `data/v5/ligas/`.
Figuras: `docs/v5/figuras/f7_sesgo_direccion.png`, `f7_precision_ligas.png`, `f7_traduccion_paso2.png`. Tests: `tests/normalizacion_v5/test_seleccion_f7.py`.

```bash
python -m bbnorm5.f7 --config configs/v5/f7.yaml --pasos base examen proyeccion_paso2 figuras   # ~5 min
python -m bbnorm5.f7 --config configs/v5/f7.yaml --pasos pares_paso2 lambda_paso2 resumen_paso2  # NUTS (~2 h con la verosimilitud por trozos)
```

Etiquetas: **DATO**, **LECTURA**, **SUPUESTO**, **RIESGO**, **VERIFICAR**.

---

## Informe de auditoría · Fase F7 · Selección en los traspasos y paso 2

### Resumen ejecutivo

1. **El sesgo de selección en los traspasos existe, pero es pequeño.**
   - Quien sube de liga rinde algo más de lo previsto y quien baja, algo menos.
   - Con el nivel encogido de la F4 como punto de partida, el sesgo es **+0,048 DT al subir** y **−0,029 DT al bajar**
     (error estándar ≈ 0,009).
   - Con la temporada previa en bruto, el sesgo al subir casi se duplica (+0,085 DT): es la regresión a la media.
2. **Se adopta la variante «encogido»: traspasos con el nivel encogido de la F4 como origen, sin IPW ni Heckman.**
   - Es la de menor error de las cinco en los cambios de liga (CRPS), y las otras tres correcciones son
     significativamente peores que ella (IC que no cruzan 0).
   - IPW no mueve el sesgo.
   - Heckman lo traslada de las subidas a las bajadas (+0,016 / −0,044) y empeora el CRPS un 0,13 %.
3. **Los traspasos entre temporadas identifican a las ligas mal conectadas** (GLS sin fugas del examen, frente al GLS
   sólo con puentes intra; la NUTS, en el punto 5).
   - La DT del efecto de liga cae a un **12 % en la NCAA** (de 6 puentes de la misma temporada a 713 traspasos).
   - Cae al 33–41 % en las FEB, al 36–39 % en NBA y G League, al 43–47 % en CBA y NBL y al 65–74 % en Europa.
4. **La proyección en contexto (F6.2) con los λ del paso 2 mejora** un 1,6 % en los cambios de liga (IC −1,9 % a
   −1,3 %), sin cambio en quien sigue en su liga.
   - Al ir a la NBA o a la G League, −5,2 % (IC −6,1 % a −4,4 %).
   - Cobertura del 80 % en los cambios de liga: 78,6 % (antes 78,0 %).
5. **NUTS del paso 2 con los bloques reagrupados (decisión del usuario):** 0 divergencias en dos bloques y 1 en 3.000
   draws en el tercero, R̂ ≤ 1,01 y ESS ≥ 425.
   - Es la **matriz de traducción que se publica** (`traduccion_paso2_2025-26.csv.gz`).
   - Frente a la F6.1, la DT del efecto de liga cae al **34 % en la NCAA**, al 45–46 % en las FEB, al 50–56 % en NBA y
     G League y al 85–97 % en Europa (mediana de las 14 métricas).
   - Es compatible con la F6.1: mediana de |z| 0,54; un 3,4 % de los pares liga–métrica supera |z| > 2.
   - Con los bloques reagrupados, pts/100 y USG% se mueven casi a la par entre ligas (correlación 0,99).
   - **Corrección técnica:** el gradiente de la NUTS era ~80 veces más lento por encima de ~40.000 filas (XLA en CPU).
     Se evalúa la verosimilitud por trozos, con resultado idéntico (§4.1).

---

## 1. Qué se hizo

### 1.1 El problema

Un jugador que sube de liga suele hacerlo tras una buena temporada, y una parte de esa temporada es suerte. Si se toma
esa temporada como su nivel, en la liga nueva rinde menos de lo esperado (regresión a la media). Entonces el efecto de
liga sale sesgado: la liga de destino parece más difícil de lo que es.

En la F6, λ se estimó sólo con **puentes de la misma temporada**: el mismo jugador en dos competiciones a la vez. No
tienen ese problema, pero casi no existen para la NCAA (6), las FEB (39–73), la CBA (47) o la NBL (54). Los
**traspasos entre temporadas** sí abundan (4.708 en total; 713 con la NCAA, 252–368 con cada FEB), pero arrastran la
selección. La F7 mide ese sesgo y elige cómo usar los traspasos sin él.

### 1.2 Datos (`seleccion_base.parquet`)

- **Base:** cada persona con una temporada objetivo T (2021-22 a 2025-26) y una temporada previa. Viene de la proyección
  F4 sin fugas: sólo usa lo anterior a T.
- **Para cada una:**
  - su nivel encogido de la F4, es decir, la media de su rol en la liga de origen más su posición relativa;
  - su última temporada observada en bruto;
  - su temporada T observada.
- **Dirección del cambio:**
  - la fuerza de cada liga es −λ de puntos por 100 posesiones de la F6.1 (en una liga más fuerte el mismo jugador
    anota menos);
  - **sube** si la fuerza del destino supera a la del origen en más de 0,5 puntos por 100, **baja** si es al revés, y
    si no es un cambio **lateral**.
- **Examen fuera de tiempo:** cortes 2023-24, 2024-25 y 2025-26. Todo (selección y λ) se estima con lo anterior al
  corte y se prueba en el corte.

  | Corte | Suben | Bajan | Laterales |
  |---|---|---|---|
  | 2023-24 | 230 | 485 | 184 |
  | 2024-25 | 398 | 509 | 160 |
  | 2025-26 | 476 | 591 | 228 |

### 1.3 Modelo de selección

- **Logística multinomial** (sigue / sube / baja / lateral). Variables:
  - la temporada previa: posición relativa en puntos, uso, asistencias, T3% y rebote defensivo;
  - minutos, edad, número de temporadas, rol y liga de origen.
- **Probit de subir y probit de bajar**, por máxima verosimilitud en `scipy` (gradiente exacto). De ellos sale el
  término de Mills de Heckman.
- **Pesos IPW:** P(dirección) / P(dirección | x), estabilizados y recortados en los percentiles 1 y 99.

### 1.4 Cinco formas de estimar λ (GLS por métrica, `gls_paso2`)

Todas usan los puentes de la misma temporada con su contexto (como la F6.1). Cambia lo que se añade:

| Variante | Qué añade | Diferencia de cada traspaso |
|---|---|---|
| `paso1` | Nada (es la F6.1) | — |
| `crudo` | Traspasos | Temporada T − temporada previa en bruto |
| `encogido` | Traspasos | Temporada T − (media del rol en origen + nivel encogido F4) |
| `encogido_ipw` | Traspasos con peso IPW | Igual que `encogido` |
| `encogido_heckman` | Traspasos + término de Mills de subir y de bajar | Igual que `encogido` |

- La varianza de cada traspaso es la de la temporada T más la de la proyección F4 (sin muestreo), más una varianza
  extra común estimada por momentos.
- **Prior débil de λ:** N(0, (2 DT de todas las diferencias)²).
  - **Corrección en esta fase:** antes la escala salía sólo de los puentes intra. En un test sin varianza intra el prior
    quedaba infinito; ahora sale de todas las diferencias, con un suelo de 10⁻³.
  - Se rehízo el examen. Las cifras de este informe son las nuevas.

### 1.5 La prueba del encargo (§11)

Para quien cambia de liga en el corte, se calcula el residuo de su temporada T predicha con λ de cada variante, en DT
predictivas (z), y se agrupa por dirección. **Si no hay sesgo, debe ser ≈ 0 tanto al subir como al bajar.**

### 1.6 Paso 2 en NUTS con los bloques reagrupados (decisión del usuario)

- **Modelo:** el mismo de la F6.1 (`bbnorm5/ligas/modelo.py`: paseo aleatorio entre temporadas, LKJ(2) entre métricas,
  contexto, todo no centrado), con dos cambios:
  1. **Datos:** puentes de la misma temporada (5.412) + traspasos entre temporadas con el nivel encogido (4.708). En un
     traspaso, la liga de origen se evalúa en su temporada (λ_{b,T} − λ_{a,T−1}), y tiene **su propia varianza extra**
     (`s_inter`), separada de la de los puentes intra.
  2. **Bloques reagrupados** por la correlación de λ entre métricas que mostró la F6.1 (pts–USG 0,95–0,98):
     - **volumen y papel:** pts/100, USG%, AST%, DREB%, OREB%;
     - **tiro:** T2%, T3%, TL%, 3PAr, FTr;
     - **defensa y cuidado:** BLK%, STL/100, PF/40, TOV%.
- **Uso:** es la **matriz de traducción que se publica**. La proyección en contexto usa el GLS por corte, sin fugas
  (§3), igual que en la F6.

---

## 2. Resultados de la selección (DATO)

### 2.1 Modelo de selección (`seleccion_diagnostico.json`)

| Corte | AUC subir | AUC bajar | Pesos IPW (p1–p99) |
|---|---|---|---|
| 2023-24 | 0,887 | 0,748 | 0,09–3,5 |
| 2024-25 | 0,876 | 0,753 | 0,09–3,6 |
| 2025-26 | 0,862 | 0,771 | 0,09–4,5 |

- **LECTURA:** subir es muy predecible a partir de la temporada previa, la edad y la liga. Bajar lo es menos.
- Con pesos tan acotados, IPW apenas puede cambiar nada: lo que predice la selección ya lo explica el nivel encogido.

### 2.2 Sesgo por dirección (`sesgo_por_direccion.csv`; figura `f7_sesgo_direccion.png`)

z medio de la temporada tras el traspaso (positivo: rinde más de lo previsto). Error estándar por persona ≈ 0,009 al
subir (1.066 personas) y ≈ 0,008 al bajar (1.498).

| Variante | Suben | Bajan | Laterales |
|---|---|---|---|
| `paso1` (sólo puentes intra) | +0,063 | −0,049 | +0,011 |
| `crudo` | +0,085 | −0,039 | +0,004 |
| **`encogido`** | **+0,048** | **−0,029** | +0,002 |
| `encogido_ipw` | +0,053 | −0,032 | +0,007 |
| `encogido_heckman` | +0,016 | −0,044 | +0,001 |

- **Todos los sesgos son < 0,1 DT.** Para un jugador con un intervalo del 80 % de ±5 puntos por 100, 0,05 DT es
  ~0,2 puntos.
- **El signo es el contrario al que se temía en λ:** quien sube rinde **más** de lo previsto, no menos.
  - **LECTURA:** la regresión a la media ya está descontada por la F4.
  - Lo que queda es selección en lo no observado: el club que ficha ve cosas que no están en la caja (estado físico,
    encaje, entrenamientos).
- **`crudo` frente a `encogido`** muestra la regresión a la media a la vista: usar la temporada previa en bruto añade
  +0,037 DT al sesgo de las subidas.

**Por corte** (z medio ± error estándar):

| Variante | Dirección | 2023-24 | 2024-25 | 2025-26 |
|---|---|---|---|---|
| `paso1` | Suben | +0,013 ± 0,018 | +0,054 ± 0,015 | +0,094 ± 0,013 |
| `paso1` | Bajan | −0,030 ± 0,013 | −0,090 ± 0,014 | −0,028 ± 0,013 |
| **`encogido`** | Suben | +0,012 ± 0,018 | +0,060 ± 0,015 | +0,055 ± 0,013 |
| **`encogido`** | Bajan | −0,013 ± 0,014 | −0,047 ± 0,014 | −0,027 ± 0,013 |
| `encogido_heckman` | Suben | −0,016 ± 0,018 | +0,034 ± 0,015 | +0,016 ± 0,013 |
| `encogido_heckman` | Bajan | −0,025 ± 0,014 | −0,064 ± 0,014 | −0,043 ± 0,013 |

- En 2023-24 el sesgo de `encogido` no se distingue de 0. En 2024-25 y 2025-26 es +0,06 al subir.
- `encogido` es la variante más estable entre cortes en las bajadas. En `paso1` el sesgo al subir crece de corte en
  corte: los puentes intra solos no bastan para las ligas a las que más se sube.

### 2.3 ¿Qué variante? Error y cobertura (`seleccion_variantes.csv`)

CRPS de los cambios de liga de los tres cortes, IC 95 % por bootstrap de personas:

| Variante | CRPS frente a `paso1` | CRPS frente a `encogido` | Cobertura 80 % |
|---|---|---|---|
| `paso1` | — | +5,5 % (+5,1 a +6,0) | 83,5 % |
| `crudo` | −4,8 % (−5,2 a −4,5) | +0,41 % (+0,33 a +0,50) | 84,0 % |
| **`encogido`** | **−5,2 % (−5,6 a −4,9)** | — | 84,2 % |
| `encogido_ipw` | −5,1 % (−5,5 a −4,7) | +0,19 % (+0,14 a +0,24) | 84,2 % |
| `encogido_heckman` | −5,1 % (−5,5 a −4,8) | +0,13 % (+0,06 a +0,22) | 84,2 % |

- **DATO:** añadir los traspasos reduce el error un 5,2 % en los cambios de liga. `encogido` es la mejor variante y las
  otras tres son significativamente peores.
- La cobertura del 80 % es alta (84 %) en todas porque este examen no lleva la recalibración de varianza de la F6.2. En
  la proyección en contexto (§3) la cobertura vuelve a su sitio.
- **Por qué no Heckman, aunque baja el sesgo de las subidas:**
  - sólo lo traslada a las bajadas (−0,044, peor que −0,029);
  - empeora el error;
  - y se identifica sólo por la no linealidad del probit: no hay ninguna variable que mueva la decisión de cambiar de
    liga sin mover el rendimiento.
- **Por qué no IPW:** los pesos son estrechos (§2.1). No cambia el sesgo y añade varianza.

### 2.4 Precisión de λ (`lambda_paso2.csv`; figura `f7_precision_ligas.png`)

DT de λ con traspasos ÷ DT sólo con puentes intra (GLS, corte 2025-26, mediana de las 14 métricas):

| Liga | Ratio | | Liga | Ratio |
|---|---|---|---|---|
| NCAA | 0,12 | | VTB | 0,65 |
| Primera FEB | 0,33 | | BNXT | 0,66 |
| G League | 0,36 | | BSL | 0,68 |
| NBA | 0,39 | | BBL, FEC, LBA, LNB | 0,69 |
| Segunda y Tercera FEB | 0,41 | | EuroLeague, GBL | 0,72 |
| NBL | 0,43 | | EuroCup | 0,73 |
| CBA | 0,47 | | BCL | 0,74 |

**Compatibilidad con el paso 1:** |z| de la diferencia de λ entre paso 1 y paso 2 por liga y métrica: mediana 0,62,
percentil 90 1,67, máximo 3,6. Un 6,4 % supera |z| > 2.
- La métrica que más se separa es PF/40 (mediana |z| 1,63). **LECTURA:** al cambiar de equipo cambian el papel y los
  minutos, y las faltas por 40 minutos dependen de ambos más que en un puente de la misma temporada.
- En el resto, la mediana de |z| está entre 0,24 (USG%) y 0,77 (pts/100).

## 3. Proyección en contexto con λ del paso 2 (DATO; `paso1_frente_paso2.parquet`)

Es el modelo final de la F6.2 (`liga+peso+todos+recal`), con λ del GLS `encogido` por corte en lugar de λ sólo con
puentes intra. Examen 2024-25 y 2025-26: 134.006 predicciones. IC 95 % por bootstrap de personas.

| Casos | CRPS paso 2 frente a paso 1 | Cobertura 80 % paso 1 → paso 2 | Personas |
|---|---|---|---|
| Todos | −0,4 % (−0,5 a −0,4) | 80,3 % → 80,4 % | 6.261 |
| Siguen en su liga | 0,0 % (−0,1 a 0,0) | 81,1 % → 81,0 % | 5.181 |
| **Cambian de liga** | **−1,6 % (−1,9 a −1,3)** | 78,0 % → 78,6 % | 1.996 |
| … a la NBA o la G League | −5,2 % (−6,1 a −4,4) | 76,3 % → 75,7 % | 397 |
| … a una FEB | −1,3 % (−1,8 a −0,8) | 76,7 % → 77,7 % | 402 |
| … a la ACB | −1,1 % (−1,9 a −0,3) | 78,7 % → 79,6 % | 159 |
| … a la EuroLeague o la EuroCup | −0,6 % (−1,1 a 0,0) | 78,1 % → 79,3 % | 280 |
| … a la CBA o la NBL | −1,1 % (−2,8 a +0,7) | 74,9 % → 75,7 % | 85 |
| … a la NCAA | −2,1 % (−5,0 a +0,7) | 72,7 % → 72,0 % | 33 |

- **LECTURA:**
  - La mejora se concentra donde λ era más incierto.
  - La NCAA como destino casi no existe (33 personas, sobre todo jugadores jóvenes que vuelven a la universidad); su
    valor está como **origen**, que es lo que mide la precisión de λ (§2.4).
  - La cobertura en NBA y G League sigue baja (75,7 %): ahí falta varianza de papel (los minutos cambian mucho), no
    efecto de liga.

## 4. NUTS del paso 2 (DATO)

### 4.1 Diagnósticos (`lambda_paso2_diagnosticos.json`, `diagnosticos_paso2_<bloque>.csv`)

| Bloque | Filas | R̂ máx. | ESS bulk mín. | ESS tail mín. | Divergencias | Pasos medios | Tiempo |
|---|---|---|---|---|---|---|---|
| Volumen y papel (pts, USG, AST, DREB, OREB) | 50.571 | 1,01 | 774 | 915 | 0 | 127 | 3 h 54 min* |
| Tiro (T2, T3, TL, 3PAr, FTr) | 49.239 | 1,01 | 425 | 495 | 0 | 127 | 54 min |
| Defensa y cuidado (BLK, STL, PF, TOV) | 40.464 | 1,01 | 814 | 936 | 1 | 127 | 39 min |

4 cadenas × 750 de calentamiento + 750 muestras; `target_accept` 0,9; profundidad máxima 10 (la configuración de la
F6).

- **\* Corrección técnica.** El primer bloque se ajustó antes de detectar el problema; el bloque de tiro se perdió en un
  reinicio del contenedor tras 5,5 h.
  - **Causa:** por encima de ~40.000 filas, XLA en CPU pasa a una estrategia del gradiente de los *gather* ~100 veces
    más lenta (980 ms por gradiente frente a 7–12 ms).
  - **Solución:** la verosimilitud se evalúa por trozos de 8.192 filas (`modelo.TROZO`), sumando las
    log-verosimilitudes. La log-densidad coincide con la de antes hasta 10⁻¹⁶ en los tres bloques.
  - **No cambia la F6:** el modelo es idéntico y sus bloques tienen menos filas.
- **La divergencia del bloque de defensa** es 1 de 3.000 draws. Con R̂ y ESS en rango no se reajusta.
  **VERIFICAR** en la recalibración si se repite.
- **Varianza extra de los traspasos (`s_inter`):** 0,02–0,07 en DT estandarizadas, frente a 0,02–0,47 de los puentes
  intra (`s_c`).
  - **LECTURA:** el traspaso, con la varianza de la proyección F4, no necesita apenas ruido añadido. La incertidumbre de
    la F4 está bien medida.
  - Los puentes intra sí lo necesitan: el mismo jugador tiene papeles distintos en dos competiciones a la vez (sobre
    todo en volumen: 0,25–0,47).

### 4.2 Matriz de traducción publicada (`traduccion_paso2_2025-26.csv.gz`; figura `f7_traduccion_paso2.png`)

Del mismo jugador al pasar de la ACB a cada competición, 2025-26, en puntos de la tasa media de la ACB; media y rango
del 80 % (`traduccion_acb_legible_paso2_2025-26.csv`):

| Hacia | Pts/100 | USG% | AST% | T2% | T3% | DREB% | TOV% |
|---|---|---|---|---|---|---|---|
| EuroLeague | −1,4 (−1,7 a −1,2) | −0,5 (−0,7 a −0,3) | +0,7 (+0,4 a +1,0) | −0,1 (−0,7 a +0,4) | +0,3 (−0,2 a +0,7) | +1,2 (+1,0 a +1,4) | +0,3 (+0,1 a +0,6) |
| EuroCup | +0,1 (−0,2 a +0,5) | +0,2 (0,0 a +0,4) | +2,8 (+2,5 a +3,2) | +1,8 (+1,2 a +2,5) | +0,3 (−0,3 a +0,9) | +2,3 (+2,0 a +2,5) | +1,4 (+1,1 a +1,8) |
| BCL | +0,7 (+0,4 a +1,0) | +0,3 (0,0 a +0,5) | +3,9 (+3,4 a +4,3) | +0,3 (−0,4 a +1,0) | +1,0 (+0,4 a +1,6) | +0,7 (+0,4 a +0,9) | +0,9 (+0,6 a +1,3) |
| LBA | +0,8 (+0,4 a +1,1) | +0,2 (−0,1 a +0,4) | +1,7 (+1,3 a +2,1) | +1,5 (+0,8 a +2,2) | +0,9 (+0,3 a +1,6) | +1,3 (+1,0 a +1,5) | 0,0 (−0,4 a +0,3) |
| NBA | −7,8 (−8,2 a −7,3) | −6,3 (−6,6 a −6,0) | −0,1 (−0,6 a +0,3) | −0,4 (−1,2 a +0,4) | +0,3 (−0,4 a +1,0) | +0,3 (0,0 a +0,6) | −0,9 (−1,3 a −0,5) |
| G League | −1,2 (−1,6 a −0,8) | −1,9 (−2,2 a −1,6) | +3,5 (+3,1 a +4,1) | +1,9 (+1,2 a +2,6) | +1,0 (+0,5 a +1,6) | +2,0 (+1,7 a +2,3) | +0,1 (−0,2 a +0,5) |
| Primera FEB | +3,0 (+2,3 a +3,6) | +2,1 (+1,7 a +2,6) | +2,8 (+2,0 a +3,6) | −0,2 (−1,2 a +0,8) | +1,0 (+0,2 a +1,8) | +2,3 (+1,8 a +2,8) | −0,5 (−1,0 a 0,0) |
| Segunda FEB | +5,0 (+4,3 a +5,8) | +3,8 (+3,2 a +4,3) | +4,6 (+3,5 a +5,6) | +0,2 (−0,9 a +1,4) | +0,2 (−0,7 a +1,1) | +2,9 (+2,3 a +3,5) | −1,4 (−2,0 a −0,9) |
| NCAA | −0,1 (−0,7 a +0,5) | −0,7 (−1,1 a −0,3) | +2,5 (+1,8 a +3,2) | +0,8 (−0,3 a +2,0) | +0,8 (−0,1 a +1,7) | +1,2 (+0,8 a +1,6) | −0,3 (−0,8 a +0,3) |

**Cambios frente a la F6.1 que importan:**
- **NCAA, puntos:** de −2,1 (−4,5 a +0,1) a −0,1 (−0,7 a +0,5). Un jugador de nivel ACB anotaría en la NCAA lo mismo
  por posesión, pero con menos uso (−0,7) y más asistencias (+2,5).
- **NBA, puntos:** de −6,4 (−7,1 a −5,6) a −7,8 (−8,2 a −7,3). Es el mayor desplazamiento (|z| ≈ 2).
  - **LECTURA:** los puentes intra de la NBA son casi todos NBA–G League (contratos dual). Los traspasos añaden el salto
    directo Europa → NBA, que es más duro.
- **FEB, asistencias:** de +6,3 (+4,3 a +8,5) y +6,8 (+4,3 a +9,5) a +2,8 y +4,6. La F6.1 tenía 39–73 puentes; los
  traspasos acotan el efecto.
- **NCAA, asistencias:** de −1,1 (−3,1 a +1,3) a +2,5 (+1,8 a +3,2).

### 4.3 Ciclos (`ciclos_paso2.csv`)

- **Estimación conjunta:** residuo máximo de los triángulos 1,1·10⁻¹⁶ (coherente por construcción).
- **Por pares independientes (sólo puentes intra):** mediana |r| 0,11, igual que en la F6.1. Es la incoherencia que
  evita la estimación conjunta.

### 4.4 Precisión y compatibilidad frente a la F6.1 (`paso2_frente_paso1_nuts.csv`)

DT de λ del paso 2 ÷ DT de la F6.1 (NUTS frente a NUTS, 2025-26, mediana de las 14 métricas):

| Liga | Ratio | | Liga | Ratio |
|---|---|---|---|---|
| NCAA | 0,34 | | BSL | 0,73 |
| Primera, Segunda y Tercera FEB | 0,45–0,46 | | VTB | 0,77 |
| G League | 0,50 | | BNXT | 0,81 |
| NBA | 0,56 | | BBL, LNB | 0,85–0,89 |
| NBL, CBA | 0,68 | | EuroLeague, GBL, FEC, LBA | 0,90–0,91 |
| | | | EuroCup, BCL | 0,95–0,97 |

- Las ganancias son menores que en el GLS (§2.4) porque la NUTS de la F6.1 ya tomaba prestada información entre
  temporadas y entre métricas.
- **Compatibilidad:** mediana de |z| 0,54, percentil 90 1,62. Un 3,4 % supera |z| > 2 (lo esperable por azar es ~4,6 %).
  - Los mayores: PF/40 en la NCAA (z −3,0) y en la NBA (+2,6), 3PAr en la NBA (+2,7), USG% en la BNXT (+3,0).
  - PF/40 vuelve a aparecer (§7, riesgo 2).

### 4.5 ¿Sirvió reagrupar los bloques? (`correlacion_metricas_paso2.csv`)

Correlación entre métricas de los efectos de liga (entre ligas, 2025-26, media sobre draws):

| Par | F6.1 (bloque) | Paso 2 (bloque) |
|---|---|---|
| pts/100 – USG% | 0,95 (distintos) | **0,99** (volumen y papel) |
| pts/100 – AST% | 0,86 (distintos) | 0,83 (volumen y papel) |
| pts/100 – DREB% | 0,75 (distintos) | 0,80 (volumen y papel) |
| pts/100 – OREB% | 0,64 (distintos) | 0,64 (volumen y papel) |
| PF/40 – TOV% | 0,47 (distintos) | 0,69 (defensa y cuidado) |
| BLK% – STL/100 | 0,71 (mismo) | 0,41 (mismo) |

- **LECTURA:** las correlaciones que motivaron el cambio se confirman dentro del bloque. pts/100 y USG% son casi el
  mismo efecto de liga: una liga que quita uso quita puntos en la misma proporción.
- **Lo que no se puede separar:** la ganancia de precisión de §4.4 mezcla dos cosas, los traspasos y el reagrupamiento.
  Separarlas exigiría ajustar el paso 1 con los bloques nuevos (~2 h). No cambia ninguna decisión, así que no se hizo.
- **Dónde se nota más el reagrupamiento:** en las ligas mal conectadas. Por ejemplo, en la NCAA y las FEB el rango de
  AST% y DREB% se estrecha a la par que el de pts/100.

## 5. Interpretación (LECTURA)

1. **La F4 ya hace casi todo el trabajo contra la regresión a la media.** El nivel encogido descuenta la suerte de la
   temporada previa. Lo que queda (+0,05 DT al subir) es selección en lo que no se ve en la caja, y es pequeño.
2. **El signo importa para el producto.** Un jugador que sube rinde ligeramente por encima de su traducción. La
   proyección no lo penaliza de más; si acaso, se queda corta por 0,2 puntos por 100.
3. **Los traspasos son la única vía para la NCAA y las FEB, y funcionan.** Pasan de ligas casi sin identificar a
   precisiones comparables a las europeas.
4. **No hace falta un modelo de selección explícito en producción.** IPW y Heckman no mejoran el error. El modelo de
   selección queda como **diagnóstico** (§2.1–2.2), que se repite en cada recalibración.

## 6. Supuestos (SUPUESTO)

1. **El nivel encogido de la F4 es insesgado dentro de la liga de origen.** La F4 lo validó con cobertura 80,3 % y
   sesgo por rol tras la corrección del cambio de rol.
2. **La selección en lo no observado es la misma en todas las ligas.** Con 1.066 subidas en tres cortes no hay
   potencia para estimarla por liga.
3. **Dirección por la fuerza de pts/100.** Una liga puede ser «más fuerte» en anotación y no en rebote. La dirección
   sólo se usa para la prueba y la selección, no para λ.
4. **Traspasos en el mismo modelo que los puentes intra,** con varianza extra propia (`s_inter` en la NUTS; por
   momentos en el GLS).

## 7. Riesgos y verificaciones pendientes (RIESGO · VERIFICAR)

1. **RIESGO · NBA y G League:** cobertura del 75,7 % al ir a ellas. **VERIFICAR (F8):** varianza de papel por cambio de
   minutos al cambiar de liga.
2. **RIESGO · PF/40:** la incompatibilidad entre paso 1 y paso 2 (mediana |z| 1,63) puede ser de papel y no de liga.
   **VERIFICAR (F8):** PF/40 con los minutos por partido como contexto en los traspasos.
3. **RIESGO · selección dependiente del tiempo:** el sesgo al subir de `encogido` es ≈ 0 en 2023-24 y +0,06 en 2024-25
   y 2025-26 (§2.2). Tres cortes no bastan para saber si crece. **VERIFICAR:** repetir la prueba por dirección en cada
   recalibración mensual; si supera 0,1 DT al subir, reabrir Heckman o un desplazamiento por dirección.
4. **VERIFICAR:** la sobrecobertura del examen GLS (84 %) desaparece en la proyección en contexto; confirmarlo en la F8
   con la proyección completa.

## 8. Diagnósticos de inferencia

- **NUTS del paso 2:** §4.
- **GLS por métrica:** solución cerrada con la varianza extra por momentos (≤ 10 iteraciones).
- **Probit:** L-BFGS-B con gradiente exacto; test de recuperación de coeficientes.
- **Semillas:** F7 20261115; la NUTS usa la de la F6 (20261114). Bootstrap con la semilla de la fase. MLflow
  `v5_f7_seleccion`.

## 9. Verificación de no regresión

- **Rutas.** Nada fuera de `bbnorm5/`, `configs/v5/`, `data/v5/`, `docs/v5/` y `tests/normalizacion_v5/`.
- **Sin cambios** en las fases anteriores. La F6.1 publicada sigue en `lambda_<bloque>.npz` y `traduccion_2025-26.csv.gz`;
  el paso 2 va en `lambda_paso2_<bloque>.npz` y `traduccion_paso2_2025-26.csv.gz`.
- **No versionado:** `seleccion_base.parquet`, `seleccion_casos.parquet`, `paso1_frente_paso2.parquet` y
  `contexto_*_paso2.parquet` (regenerables).
- **Tests:** 4 nuevos en `test_seleccion_f7.py`:
  - recuperación del probit;
  - regresión a la media simulada (`crudo` sesgado, `encogido` no);
  - orden por CRPS de `comparar_variantes`;
  - correlación entre métricas y compatibilidad de `resumen_paso2`.

  Suite completa en verde: **368 passed**.

## 10. Riesgos detectados y decisiones que requieren al usuario

1. **¿Se adopta la variante `encogido` (traspasos con el nivel encogido de la F4, sin IPW ni Heckman) para λ?** Es la de
   menor error. El modelo de selección queda como diagnóstico en cada recalibración.
2. **¿Se publica la traducción del paso 2 (NUTS, bloques reagrupados) en lugar de la de la F6.1?**
   - Es compatible con ella y mucho más precisa en NCAA, FEB, NBA y G League.
   - El mayor cambio de lectura es el salto ACB → NBA en puntos: −7,8 en lugar de −6,4.
   - La F6.1 queda guardada (`traduccion_2025-26.csv.gz`), no se destruye.
3. **¿Se adopta la proyección en contexto con λ del paso 2** (−1,6 % de error en los cambios de liga, §3) como la
   versión que entra en el examen de la F8?
4. **Pendientes de antes, sin cambios:**
   - regenerar las capas afectadas por la corrección de fechas de los entrenadores;
   - revisar los 134 candidatos de identidad;
   - ampliación de la extracción (ABA, Israel, LKL, BSL 2021-25). La F6 mostró que no ayuda a las ligas mal conectadas;
     la F7 lo confirma, porque esas ligas se identifican con los traspasos.

## 11. Siguiente fase propuesta y ajuste de inversión

**F8 · Validación** (revisión 1.2, criterio 9):
- **Examen principal:** producción de la temporada siguiente de fichajes reales con su equipo real (banco V32_corte,
  ~4.956 fichajes), frente al motor v3.3 y la v4.2.
- Más el examen de nivel por simulación (SBC) y el resto del protocolo 1.1.
- **Criterio 10:** anchura del intervalo frente a la v3.3 con la misma cobertura.
- **Criterio 11:** navaja para el estilo de liga y de compañeros en ese examen.
- **Pendientes que se resuelven en la F8:**
  - sobrecobertura de BLK% (decisión de la F4);
  - cobertura al ir a la NBA y la G League (75,7 %);
  - PF/40 en los traspasos.

**Inversión: alta.** Es el examen que decide si la v5 sustituye al motor publicado. Usa todo lo construido de la F3 a la
F7, sin modelos nuevos.

**Esperando GO.**
