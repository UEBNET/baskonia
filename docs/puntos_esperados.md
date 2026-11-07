# Capa XP · Puntos esperados por tiro — planteamiento

Versión del modelo: **xp1**. Orden del CEO del 07-11-2026: «calcular el punto esperado por tiro de cada jugador, dejarlo
explícito en el planteamiento, de modo que se puedan añadir campos y métricas asociadas a lo largo del proyecto».

| | |
|---|---|
| Código | `bbequipo/ecosistema/puntos_esperados.py` (cálculo y registro de campos) · `beneficio_xp.py` (prueba de beneficio) |
| Configuración y catálogo | `configs/ecosistema_v41.yaml → puntos_esperados` (y `beneficio_xp`) |
| Orden | `python -m bbequipo.ecosistema puntos-esperados [--temporadas T …] [--ligas L …]` |
| Salidas versionadas | `data/modelos/v4_1/puntos_esperados/`: `modelo_<t>.csv`, `jugadores_<t>.csv.gz`, `calidad.json`, `catalogo.json`, `beneficio.json` |
| Salidas no versionadas | `experimentos/v4_1/puntos_esperados/{tiros,tramos}/<t>/<liga>.csv.gz` (≈ 9 M de tiros; se regeneran en minutos) |
| Tests | `tests/test_ecosistema_v41.py` (catálogo ↔ código, emparejamiento con tramos, contracción) |

---

## 1. Qué es y para qué sirve

El **punto esperado (xp)** de un tiro es lo que vale **de media** un tiro así en esa liga y temporada:

> xp = probabilidad de anotarlo × su valor (2, 3 o 1)

Un triple frontal que anota un jugador vale 3 puntos reales, pero su xp es ≈ 1,05 en ACB 2024-25 (3 × 0,35). La
diferencia, puntos − xp, es el **acierto sobre lo esperado**: una mezcla de habilidad para anotar y de suerte.

Tiene dos usos en CERNO:

1. **Medir con menos ruido.** El diferencial de un tramo con puntos reales lleva dentro la suerte de cada tiro. Con
   puntos esperados esa suerte desaparece. En ACB 2024-25, la varianza por tramo baja al **41 %**. Todo lo que se apoya en
   tramos (valor de cada jugador, química, Net de equipo, Valor de baja) puede medirse con más precisión.
   - **Límite:** también desaparece la habilidad real para anotar por encima de lo esperado.
   - Por eso **no se adopta a ciegas**: la prueba de beneficio (§5) decide, con una regla fijada antes de mirar.
2. **Describir al jugador con métricas nuevas y explícitas.** Calidad de los tiros que elige, acierto sobre lo esperado
   (con cuánto de eso es fiable), mezcla de zonas y Net en pista sin la suerte del tiro. El catálogo crece a lo largo del
   proyecto (§4).

## 2. El modelo xp1 (deliberadamente simple y auditable)

**Tiros de campo.**
- p(anota | zona, liga-temporada).
- Zonas (`bbmodel/zonas.py`, por distancia al aro y geometría de la línea): **aro** (< 1,8 m), **corta** (1,8–4,25 m),
  **media** (hasta la línea), **triple de esquina** y **triple frontal**.
- Las coordenadas de cada fuente se convierten a metros con la calibración de `data/modelos/pista/calibracion.json` (122
  ligas-temporada, todas con ≥ 95 % de acierto al separar dos y triples).
- Un tiro sin coordenadas, o de una liga-temporada con calibración pobre, va a **sin_zona** y recibe la tasa de su tipo
  (T2 o T3). Ejemplo: la CBA no tiene coordenadas.
- La tasa de una zona se **contrae** hacia la de su tipo: p_z = (anotados_z + 200·p_tipo)/(intentos_z + 200). Con pocos
  intentos manda el tipo; con miles, la zona.

**Tiros libres.** TL% del **tirador**, contraído hacia la liga: (anotados + 50·p_liga)/(intentos + 50). El tiro libre es
sobre todo habilidad, así que se usa la del propio tirador; con pocos intentos, la de la liga. Configurable:
`tl_modelo: liga`.

**Sin fuga.** La tasa de una liga-temporada es el **instrumento de medida** de esa temporada (contexto), no una
predicción. Medir la temporada t con las tasas de t no introduce información del futuro en un examen ≤ t → t+1.

**Comprobaciones** (`calidad.json`, por liga-temporada):
- xp total frente a puntos totales: cociente ≈ 1,000;
- fracción de tiros de campo con zona;
- fracción de tiros emparejados con su tramo: 1,000 en ACB;
- fracción de tramos cuyos puntos se reconstruyen exactos desde los tiros: 100 % en ACB y NBA 2024-25.

## 3. Tres granos, una sola tubería

```
tiro (una fila por tiro de campo o TL)
  └─► tramo (una fila por tramo de quinteto del contrato v4.0: xp_a, xp_b, y_xp)
        └─► jugador (liga × temporada × equipo × jugador: sus tiros + su presencia en pista)
```

- **Tiro → tramo.** Mismo partido, mismo quinteto atacante y rival, y el instante del tiro dentro del tramo. Un tiro
  justo en el cambio pertenece al tramo que termina en ese instante. Con esa regla se reproducen exactos los puntos del
  100 % de los tramos de ACB y NBA, frente al 99,5–99,8 % con la contraria.
- **Tramo → jugador (en pista).** Cada tramo suma sus posesiones, el xp a favor y en contra, y los puntos reales a los 10
  jugadores en pista.

## 4. El catálogo de campos (cómo ampliarlo)

Todo campo vive declarado en `configs/ecosistema_v41.yaml → puntos_esperados.catalogo`, con cinco datos:

```yaml
nombre_del_campo: {grano: jugador, unidad: pts/100, estado: experimental, def: "definición en una frase"}
```

- **grano**: `tiro` · `tramo` · `jugador`.
- **estado**:
  - `validado`: pasó un examen prerregistrado; puede mostrarse con sello;
  - `experimental`: se calcula, pero sin examen; no se muestra como cifra del producto;
  - `propuesto`: sólo declarado, sin código; sirve de hoja de ruta.

**Para añadir un campo** (tres pasos, ningún otro fichero que tocar):
1. Declararlo en el catálogo con `estado: propuesto`, o `experimental` si ya se implementa.
2. Implementarlo en `puntos_esperados.py` con el registro:
   ```python
   @campo("jugador", "nombre_del_campo")
   def _f(A): return ...          # A = tabla agregada por jugador (sumas de tiros, xp, zonas y presencia en pista)
   ```
   Si necesita una suma nueva por jugador, se añade en `agregar_jugadores`.
3. Ejecutar los tests: `test_catalogo_xp_y_codigo_coinciden` falla si un campo no propuesto no tiene función o si hay una
   función sin entrada en el catálogo. El fichero `jugadores_<t>.csv.gz` incluye automáticamente todo campo activo.

Para pasar un campo a `validado`: examen prerregistrado en el YAML, con su efecto mínimo detectable (§6) y su
checkpoint.

### Campos actuales (xp1)

| Grano | Campos | Estado |
|---|---|---|
| tiro | `zona`, `dist_m`, `p_acierto`, `xp`, `residuo_tiro`, `asistido` | experimental |
| tramo | `xp_a`, `xp_b`, `pts_tiros_a`, `pts_tiros_b`, `y_xp` | experimental |
| jugador · volumen | `tiros_campo`, `tiros_libres`, `intentos_ts`, `puntos_tiro`, `xp_campo`, `xp_libres`, `xp_total` | experimental |
| jugador · eficiencia | `pps` (real), `xpps` (esperado), `calidad_seleccion`, `acierto_sobre_esperado`, `acierto_sobre_esperado_campo` | experimental |
| jugador · fiabilidad | `acierto_sobre_esperado_contraido`, `fiabilidad_acierto` (bayes empírico por liga-temporada), `tl_pct_contraido` | experimental |
| jugador · zonas | `pct_tc_aro`, `pct_tc_corta`, `pct_tc_media`, `pct_tc_t3_esquina`, `pct_tc_t3_frontal`, `pct_tc_sin_zona` | experimental |
| jugador · en pista | `poss_on`, `xortg_on`, `xdrtg_on`, `xnet_on` (sin la suerte del tiro), `net_on` (real, referencia) | experimental |

### Hoja de ruta (propuestos)

| Campo | Grano | Para qué | Qué falta |
|---|---|---|---|
| `xnet_onoff` | jugador | on/off sin suerte de tiro: contraparte realizada de menos ruido para el Impacto en pista (F2) | el Net del equipo sin él con xp (sumar tramos sin el jugador) |
| `xp_permitido_defensor` | jugador | defensa por zonas (protección del aro, defensa del triple) | xp del rival con él en pista, por zona |
| `xp_creado_asistencias` | jugador | creación de tiros para los demás | asistencias de tiros fallados o un modelo de pase (la fuente sólo registra las de los anotados) |
| `xp_distancia_continua` | tiro | xp2: acierto como función continua de distancia y ángulo | spline por liga-temporada y examen frente a xp1 |
| `xp_contexto` | tiro | xp2: asistencia, marcador, cuarto, tiempo restante | modelo y examen frente a xp1 |
| `xp_rebote_ofensivo` | tiro | valor esperado de la segunda oportunidad | modelo de rebote ofensivo esperado |

## 5. Prueba de beneficio (prerregistrada)

`bbequipo/ecosistema/beneficio_xp.py`, regla en `beneficio_xp.regla`.

**Qué se compara.** Por liga-temporada, el resultado de tramo y_α = α·y_real + (1 − α)·y_xp, con α ∈ {0, 0,25, 0,5, 0,75,
1}, en tres medidas:
1. ruido residual;
2. estabilidad del β de los jugadores entre dos mitades de partidos;
3. **R² fuera de muestra del diferencial REAL**: es la que decide.

**Regla.** Se adopta un α < 1 para los modelos **nuevos** de la capa E sólo si mejora el R² del diferencial real con
IC95 > 0 en el global y no empeora en el segmento élite. Los modelos cerrados de la v4.0 no se reajustan.

**Resultado** (V41_F0 §11.2, 07-11-2026). 97 ligas-temporada:
- el punto esperado puro predice **peor** el diferencial real (R² −0,0038 [−0,0047; −0,0029]), porque quita también la
  habilidad de anotar;
- la mezcla **α = 0,75** mejora en el global (+0,0004 [+0,0002; +0,0006]) y en el segmento élite (+0,0004 [+0,0001;
  +0,0007]).

**Adoptada por la regla:** resultado de tramo de los modelos nuevos de la capa E = 0,75·y_real + 0,25·y_xp
(`puntos_esperados.resultado_tramo_capa_e`).

## 6. Límites declarados

- **xp1 sólo mira zona y tipo.** No ve al defensor, el tipo de tiro (tras bote, recepción, tras rebote), el tiempo de
  posesión ni el marcador. Las versiones xp2 (propuestas) lo abordarán con examen.
- **El «acierto sobre lo esperado» mezcla habilidad y suerte.** La versión contraída y su fiabilidad dicen cuánto es
  señal: un tirador con 430 tiros de campo tiene una fiabilidad ≈ 0,6 en ACB 2024-25.
- **Ligas sin coordenadas** (CBA y algunos partidos de otras): todo es sin_zona, y el xp sólo distingue dos de triples.
  `frac_tc_con_zona` lo dice por liga-temporada.
- **Las asistencias** sólo se registran en canastas anotadas: `asistido` no sirve para estimar la calidad de los pases.
