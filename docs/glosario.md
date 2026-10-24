# Glosario para la dirección deportiva

Qué significa cada etiqueta y cada número de los modelos de encaje, dicho en lenguaje de banquillo y de despacho.
Las cifras y los ejemplos salen de los informes de fase (`docs/checkpoints/F3.md`, `F5.md`, `F6.md`, `F7.md`) y están
comprobados en los datos salvo que se diga lo contrario. La formulación matemática está en la Parte II del artículo
(`docs/articulo/estilos_de_juego_baskonia.pdf`, secciones 17-22) y el detalle de cada columna en
[`data_dictionary.md`](data_dictionary.md).

---

## 1. Roles (por minutos y peso en el equipo)

El rol describe **cuánto y cómo juega** un jugador en su equipo, no cuán bueno es. Se calcula por minutos sobre un
partido de 40' (en la NBA y la G League se usa la misma proporción de un partido de 48'). Por cada jugador-equipo-
temporada (y por cada tramo de la temporada en el que su papel cambió) hay una etiqueta y un **vector de rol**: la
fracción de sus partidos en cada rol. Con menos de 5 partidos no se da etiqueta firme, sólo el vector.

| Rol | Regla | Cómo leerlo |
|---|---|---|
| **RESIDUAL** | menos de 5' por partido | Fondo de armario: entra en la basura o por faltas/lesiones. No es una referencia de rendimiento. |
| **PROFUNDIDAD** | 5-15' | Banquillo corto: minutos de descanso de los titulares, especialista para situaciones. |
| **ROTACIÓN** | 15-22' (y 22-25' si no es titular habitual ni cierra partidos) | Rotación de confianza: sexto-noveno hombre, minutos importantes pero no estructurales. |
| **TITULAR** | 25' o más (o 22-25' si sale de titular en ≥ 50 % de los partidos o juega ≥ 50 % de los finales igualados) | Columna del equipo en minutos: sale de inicio o cierra los partidos. |
| **GO-TO-GUY** | ≥ 22', uno de los dos primeros de su equipo en GTI y GTI alto en términos absolutos | Jugador franquicia: el balón pasa por él, crea su propio tiro y asume los finales. Sale ≈ 1 por equipo. |

**GTI (índice GO-TO-GUY)**: suma de cuatro puntuaciones dentro de su liga-temporada —uso del balón (USG%), impacto
global (PIE), % de canastas propias sin asistencia y uso en los finales igualados—. GTI ≥ 4 equivale a estar, de
media, una desviación típica por encima de los jugadores importantes de su liga en esas cuatro cosas.

**Ejemplos comprobados** (F3): Jokić, Dončić y Gilgeous-Alexander son GO-TO-GUY en las seis temporadas completas de
la NBA; en EuroLeague, Larkin, Nunn, Mike James, Micic, Baldwin, Carsen Edwards o Hifi; en la ACB, Huertas de 2020-21
a 2025-26. Markus Howard es ROTACIÓN en 2022-23 (19-20' con un uso altísimo: no llega a 22') y GO-TO-GUY en 2023-24:
la regla separa **minutos** de **uso**. Vezenkov sale TITULAR (no GO-TO-GUY) en EuroLeague 2025-26 por ser el
segundo de su equipo en GTI y quedar por debajo del umbral. De los diez máximos anotadores de cada liga-temporada,
el 93 % es GO-TO-GUY o TITULAR.

**Términos asociados**

* **MIN%**: minutos jugados / duración real del partido (con prórrogas). 0,50 = media parte del partido.
* **CLOSE%**: parte de los minutos de cierre igualados (últimos 5' de cada periodo desde el 4.º con ±5 puntos) que juega.
* **Tramo de rol**: parte de la temporada con un papel estable. Un cambio de entrenador abre tramo; un cambio de rol
  a mitad de temporada se detecta con un detector bayesiano en línea (exige 4 partidos de confirmación).
* **Vacío de rol**: un compañero de su posición con muchos minutos deja de jugar (lesión, salida); explica el 43 % de
  las subidas de minutos detectadas.
* **H_rol**: entropía del reparto de sus partidos entre roles. 0 = siempre el mismo papel; alto = papel cambiante.

## 2. Reemplazo de rol

* **Volumen de rol**: minutos por partido ejercidos en cada rol (minutos × vector de rol). Lo que pierde un club al
  irse un jugador es su volumen de rol, no «un nombre».
* **Libro de rol**: cuenta exacta, de una temporada a la siguiente, de dónde sale el volumen de cada rol: lo que se va,
  lo que llega y lo que cambian los que siguen. Lo que cambian los que siguen se parte en **desplazamiento de minutos**
  (mismos papeles, más o menos minutos) y **desplazamiento de rol** (mismos minutos, otro papel).
* **Tasa de relleno**: (llegadas + desplazamientos) / salidas para un rol. 1 = se cubre todo lo que se fue; mediana en
  los roles clave 0,96. Estrategias: **externa** (fichajes; la habitual: 1.236 de 1.328 casos), **interna por minutos**
  (más minutos a quien ya tenía el papel) e **interna por rol** (subir de papel a otro). Asociación con el cambio de
  Net (no causal): interna por minutos +3,8; interna por rol −3,2; externa ≈ 0.
* **Elasticidad uso–eficiencia (β)**: cuánto cambia el acierto (TS%) por cada punto más de uso. Signo negativo (más
  balón, algo menos de acierto) pero **sin significación** con estos datos (−0,08 [−0,22, +0,08] para todos): el
  simulador usa el intervalo, no un número fijo.

## 3. Estilos unificados (mismo nombre para jugador y equipo)

Seis estilos definidos sobre 12 rasgos medidos **frente a su propia liga** (un «+1» en triple es estar en el percentil
84 de su liga). Un equipo recibe el estilo al que se parece su desviación respecto de su liga; un jugador, el
arquetipo al que se parece su perfil. Cada uno lleva su probabilidad: «puro» = probabilidad ≥ 0,80; «A · B» = estilo
principal A con una segunda componente B ≥ 0,25. Estos estilos **no son** los seis estilos VaDE del Atlas (Parte I
del artículo): aquellos comparan clubes en la vara EuroLeague sin el nivel; éstos, la forma de jugar frente a la liga
propia (coinciden poco, ARI 0,03).

| Estilo | Lectura de equipo | Lectura de jugador | Ejemplos comprobados (F6) |
|---|---|---|---|
| **Spacing** | Abre la pista: mucho triple tras pase, pocos tiros en el aro y pocos tiros libres | Tirador de recepción: espera en esquina o ala y tira tras pase; apenas bota ni pierde balones | Equipos: Golden State Warriors (NBA 25-26), Valencia Basket (EuroCup 24-25), Bakken Bears (FEC 25-26). Jugadores: Sam Hauser, Melih Mahmutoğlu, Nicolas Batum |
| **Circulación** | Juego exterior que renuncia al rebote ofensivo: mucho triple, pocos tiros en el aro; el balón circula por fuera | Conector exterior: base o escolta que pasa, tira de tres y no ataca el aro | Equipos: Legia Warszawa (BCL 25-26), Hubo Limburg United (FEC 24-25), Clínica Ponferrada (Segunda FEB 24-25); Baskonia EuroLeague 2025-26 «Circulación puro». Jugadores: Tamir Blatt, Bruno Fitipaldo, Shabazz Napier; Campazzo y Stephen Curry «Circulación puro» |
| **Isolation** | Uno contra uno: muchas canastas sin pase previo, poco triple y casi nada de rebote ofensivo | Creador con balón: fabrica su tiro y el de los demás y asume pérdidas | Equipos: MLP Academics Heidelberg (BBL 24-25), Trefl Sopot (EuroCup 24-25); Baskonia ACB 2025-26 «Isolation puro». Jugadores: Marcelinho Huertas, Kevin Durant, Shai Gilgeous-Alexander, TJ Shorts; Luka Dončić «Isolation puro» |
| **Old-School** | Estructura tradicional: ataque por dentro y segundas opciones; tira menos de tres que su liga | Interior clásico o ala-pívot de contacto: finaliza tras pase cerca del aro, rebotea y tapona | Equipos: Toronto Raptors (NBA 24-25), UNAHOTELS Reggio Emilia (LBA 24-25), Inveready Gipuzkoa (Primera FEB 24-25). Jugadores: Vitor Faverani y varios interiores FEB |
| **Pistons** | Físico y de presión: roba, hace faltas, ataca el aro y pelea el rebote ofensivo; en ataque, triple de esquina | Ala atlético de energía: defiende con robos y contacto, ataca el aro sin balón, rebotea y tira desde la esquina | Equipos: Detroit Pistons (NBA 25-26), Partizan (EuroLeague 24-25), Anwil Wloclawek (FEC 24-25), ASVEL (LNB 25-26). Jugadores: Jarred Vanderbilt, Ausar Thompson, Ron Holland |
| **Pintura** | Vive dentro: aro, línea de tiros libres y rebote ofensivo; apenas tira de tres | Pívot dominante: termina en el aro, saca faltas, captura rebotes ofensivos y protege el aro | Equipos: Nanterre 92 (BCL 24-25), Unicaja (ACB 24-25), AS Monaco (EuroLeague 25-26), Denver Nuggets (NBA 24-25). Jugadores: Walter Tavares, Tai Odiase |

**Cautelas**: «Old-School» recoge muchos equipos cercanos a la media de su liga (35 % de los equipos); el estilo de un
equipo es poco estable (cambia en el 52 % de los relevos de entrenador) y no es la suma de sus jugadores (la mezcla de
estilos de la plantilla acierta el del equipo en el 33 % de los casos). Algunas estrellas atípicas reciben etiquetas
discutibles (Jokić «Old-School», Draymond Green 2025-26 «Spacing»): leer siempre el vector de probabilidades.

## 4. Adaptación al cambio de liga: ADAPT%

* **Lo esperado (ŷ)**: lo que la normalización entre ligas predice que hará el jugador en la liga de destino si se
  comportara como el jugador puente medio.
* **ADAPT%** = rendimiento esperado tras el cambio / ŷ × 100. **100 = rinde lo esperado**; 94 = un 6 % por debajo; 105
  = un 5 % por encima. El principal es el compuesto de las 8 métricas de nivel (`adapt_pct`); hay uno por métrica
  (pts/100, TS%, USG%, AST%, rebote, PER) y para los primeros 10 partidos.
* **Lecturas comprobadas** (F7): el estadounidense en su primer año europeo rinde un 6,8 % menos de lo esperado que el
  europeo que cambia de liga (no se adapta más despacio: es un déficit de toda la primera temporada); el español que
  sube de categoría dentro de España (`nacional_mismo_pais`) queda un 3,3 % por debajo; todos los jugadores, cambien
  o no, arrancan la temporada un ~2 % por debajo y lo recuperan en 3-11 partidos.
* **Ejemplos de la interfaz** (`prior()`): Primera FEB → ACB, español, exterior: −3,4 % ± 3,1; G League → ACB,
  estadounidense, exterior: −6,6 % ± 3,3; ACB → LBA, europeo, alero: +3,0 % ± 2,9.
* **Cautela**: fuera de muestra las predicciones son demasiado extremas (hay que encogerlas hacia 100: el simulador usa
  el 55 % del Δ previsto) y el 29 % de las nacionalidades es desconocido.
* **Censura**: el que no se adapta juega menos o se va; si sólo se mirara a los que siguen jugando, la adaptación
  parecería 1-2 puntos mejor de lo que es. Los modelos corrigen ese sesgo (IPCW).

## 5. Índice Fit (simulador v2)

Número único de encaje de un jugador en un club, en desviaciones típicas del «éxito» real de los fichajes (mitad
minutos, mitad producción, medidos dentro de la liga de destino). Es la suma exacta de seis componentes, que se leen
por separado:

| Componente | Qué mide | Sube si… |
|---|---|---|
| **Nivel** | su nivel efectivo en el destino frente al de los compañeros con los que compartirá minutos | es mejor que la rotación que tendrá alrededor |
| **Rol** | el rol que se le espera en la plantilla de destino | tendrá un papel alto (TITULAR, GO-TO-GUY) |
| **Estilo** | parecido entre su estilo y el del equipo (divergencia de Jensen-Shannon, con signo negativo) | juega como juega el equipo |
| **Complementariedad** | si cubre un hueco de estilo de la plantilla y cómo cambia el reparto del uso y de la red de pases | aporta algo que falta sin desordenar el reparto |
| **Adaptación** | ADAPT% esperado − 100 | su perfil de cambio de liga se adapta bien |
| **Riesgo** | volatilidad partido a partido, incertidumbre de su nivel traducido y entropía de rol (con signo negativo) | es fiable, con mucha muestra y papel estable |

Los pesos se aprenden con fichajes reales de temporadas anteriores. [[F8: pesos de cada componente y validación del
índice; ver docs/checkpoints/F8.md]] Avisos que acompañan al Fit: muestra pequeña, salto de nivel grande,
incertidumbre alta, cambio de rol de dos o más escalones, volatilidad alta y adaptación estimada con poca información.

## 6. Medidas de entropía y concentración

| Medida | Qué dice | Cómo leerla |
|---|---|---|
| **H_estilo** (bits) | variedad de las acciones del jugador (zonas de tiro, tiros libres, asistencias, pérdidas, faltas recibidas, rebote ofensivo) | bajo = especialista (casi todo triples o casi todo aro); alto = repertorio variado. Mediana 2,80 bits sobre 10 categorías; comparar entre ligas con `H_estilo_basico` |
| **H_rol** (bits) | estabilidad del papel a lo largo de la temporada | 0 = mismo rol todos los partidos |
| **σ (volatilidad)** | variación partido a partido de su producción por posesión, una vez quitados rival, minutos y compañeros | puntos de producción por 100 posesiones en un partido de 30 posesiones; mediana 12,2; alto = irregular |
| **HHI** | concentración (de uso, tiros o minutos) en el equipo | 1/n = reparto perfectamente igual; cerca de 1 = un solo jugador. Uso: 0,090-0,123 según liga |
| **Número efectivo** (2^H) | cuántos jugadores «equivalentes» se reparten el uso o los minutos | un equipo con 14 jugadores y número efectivo 9 concentra el juego en unos 9 |
| **Entropía de la red de pases** (normalizada) | variedad de las conexiones pasador → anotador | 1 = todos se asisten con todos por igual; 0,75-0,81 típico |

## 7. Escala ±100

Una sola regla para todas las cifras de nivel e impacto del Atlas y de Quintetos: **S = 100 · tanh(z/2)**, con z =
(valor − media de la EuroLeague de esa temporada) / desviación típica de la familia de métricas.

* 0 = la media de la EuroLeague; ±46 = una desviación típica; ±76 = dos; ±91 = tres; nunca pasa de ±100 (casi lineal
  en el centro, satura en los extremos).
* Nivel (índice L de jugador, quintetos, compañeros, rivales, club): referencia = media de L de la EuroLeague de la
  temporada (ponderada por minutos), así que la media de cada liga se lee directamente en la escala.
* Impacto (net rating, on/off, RAPM, sinergia): referencia 0 y desviación típica de esa familia en la EuroLeague.

## 8. Otros términos

* **DT EuroLeague**: desviación típica de capacidad de los jugadores de la EuroLeague; unidad del nivel de las ligas
  (EuroLeague = 0; ACB −0,23; Primera FEB −1,19; Tercera FEB −3,46).
* **Índice L**: nivel compuesto de un jugador (PER, GmSc/40, WS/40, ORtg, DRtg, pts/100, TS%, eFG% en la vara
  EuroLeague).
* **Jugador puente**: el que juega ≥ 150' en dos competiciones (a la vez o en temporadas seguidas); con ellos se mide la
  distancia entre ligas. **Escalón**: grupo de ligas de nivel parecido (élite, doméstica alta, copas europeas,
  desarrollo y cada FEB).
* **Normalización amortiguada**: traducción entre ligas que suma la incertidumbre de cada paso de la cadena de puentes
  (por eso Tercera FEB tiene un intervalo casi tres veces más ancho que antes).
* **Etiquetas de confianza** de los informes: **[verificado]** medido en los datos; **[estimado]** salida de un
  modelo, con intervalo; **[supuesto]** hipótesis de trabajo.
