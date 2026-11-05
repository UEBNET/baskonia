# CERNO v4.0 · Modelo de equipo y métricas ancla

> Encargo: `ENCARGO · CERNO v4.0`, revisión 1.2 (04-11-2026). Configuración única: `configs/equipo_v40.yaml`.
> Código: `bbequipo/`. Salidas: `data/modelos/v4_0/`. Checkpoints: `docs/checkpoints/V40_F<k>.md`.
> **CERNO v4.0 = normalización v3.2 + simulador v3.3 + modelo de equipo (capas 1-4) + métricas ancla (capa 5).**
> Nada de `v3_1*`, `v3_2`, `v3_3` ni `simulador/v2|v3*` se modifica ni se borra: la v4.0 **añade**.

Este documento crece fase a fase. Cada sección lleva las etiquetas del proyecto: **[DATO]** medido en los ficheros,
**[LECTURA]** interpretación, **[HIPÓTESIS]** supuesto declarado, **[POST HOC]** decisión tomada tras ver resultados.

## 0. Pirámide de capas

```
Capa 0  Perfiles comparables entre ligas (v3.2: u ∈ ℝ⁴, θ/v_j, estilos, rol, edad)   F0  ← esta entrega
Capa 1  Valor aditivo en pista: RAPM multiliga con prior del perfil                   F1 (+F1-D)
Capa 2  Sinergia de pares φ(x̃_i, x̃_j) + efectos dirigidos X→Y                       F2
Capa 3  Función de conjunto (residuo del quinteto completo), condicional              F3
Capa 4  Composición: rotaciones v3.3 + A5 + Monte Carlo → Δ de equipo con rango       F4
Capa 5  NIVEL CERNO e IMPACTO en [0, 100], con descomposición explicativa             F5
```

Principios (encargo §2): ancla aditiva y aprendizaje residual; la sinergia se predice por perfiles, nunca por historia
compartida; sin fuga (perfiles ≤ t); prerregistro (§11 congelado en `criterios` del YAML); reproducibilidad (semillas,
YAML único, MLflow `equipo_v40`, tests sintéticos); nada se presenta sin ejecutarse; puertas de fase con aprobación del
CEO; un índice [0, 100] es un percentil esperado calibrado, no una suma de pesos; la no linealidad se estima.

## 1. F0 · Perfil ampliado x̃ (capa 0)

### 1.1 Definición

Una fila por **jugador-liga-temporada** (clave `liga, temporada, player_id`; `persona_id` del crosswalk cruza ligas y
temporadas; `persona_norm` es el id entero de la normalización, sólo para unir con el latente):

```
x̃_i = [ u_i ∈ ℝ⁴ (media y sd) · p_i^estilo ∈ Δ⁶ · θ de 16 rasgos (DT EuroLeague) con su varianza propia v_j
        · rol (más probable, probabilidades de los 5 roles, índice ordinal esperado, MIN%, GS%, H_rol) · edad y pos3 ]
```

| Bloque | Columnas | Procedencia | Ajuste |
|---|---|---|---|
| Latente | `u1…u4`, `u1_sd…u4_sd` (absoluta), `u1_sd_rel…u4_sd_rel` (relativa a su competición), `u_fuente`, `u_discrepancia_redes` | posterior conjunta de las 20 redes CVAE de la configuración final de la v3.2 (K = 4) | completo (producto) / ≤ t (cortes) |
| Estilos | `p_circulacion, p_pintura, p_spacing, p_old_school, p_pistons, p_isolation`, `estilo`, `estilo_p`, `estilo_fiable` | `estilos_unificados/jugadores.csv.gz` (nivel temporada) | todas las temporadas **[HIPÓTESIS declarada]** |
| Rasgos | `<m>_th`, `<m>_vj` para `usg_pct, ast_pct, tov_pct, fg3a_rate, fta_rate, pct_aro, pct_corta, pct_media, pct_t3_esquina, pct_asistidas, oreb_pct, dreb_pct, stl_pct, blk_pct, orapm, drapm` | `v3_2/destino/capacidad/<t>.csv.gz` (completo) · normalización v3.2 ≤ t, fuente `V32_corte` (cortes) | completo / ≤ t |
| Rol | `rol_mas_probable`, `rol_indice`, `rol_indice_esperado`, `p_RESIDUAL…p_GO_TO_GUY`, `min_pct`, `gs_pct`, `H_rol`, `rol_fuente` | `roles/player_role_season.csv.gz` | por temporada (sin fuga) |
| Identidad | `persona_id`, `persona_norm`, `team_id`, `pos3`, `edad`, `tramo_edad`, `min` | normalización v3.2 + crosswalk | — |
| Contraste | `rapm_obs`, `orapm_obs`, `drapm_obs`, `poss_on_obs` | `pista/<t>.csv` | **no forma parte de x̃**: sirve a F1 y F1-D |
| Avisos | `avisos`, `completo` | — | — |

**pts/100 y TS% no entran en x̃**: son lo que las capas 1-5 predicen. La lista de rasgos es la del §5.1 del encargo y
está fijada en `perfil.rasgos` del YAML antes de entrenar nada.

**Nada se imputa con 0.** Un bloque ausente queda `NaN` y deja su aviso: `sin_latente`, `latente_codificador`,
`sin_estilo`, `sin_rol`, `sin_rapm`, `sin_theta`, `sin_persona_crosswalk`, `muestra_corta` (< 100 min),
`red_discrepante` (sd entre redes del latente > 0,5 DT). `completo` = sin más avisos que `muestra_corta` o
`latente_codificador`.

### 1.2 El latente u: posterior conjunta y alineamiento del ensemble

- Para las personas-temporada del ajuste (≥ 100 min) u es la media de la **posterior conjunta** de la v3.2
  (`bbnorm3.niveles.posterior`: latentes y niveles resueltos juntos) y su varianza es la diagonal de Q⁻¹ en esas
  coordenadas (exacta dado el modelo de medida).
- Dos incertidumbres: `u_sd` es la DT a posteriori absoluta e incluye la del nivel μ_c de la competición (común a sus
  jugadores; ≈ 0,67 frente a una dispersión de medias de 0,13–0,20); `u_sd_rel` es la DT de u − μ_c (0,03–0,04), la que
  compara jugadores dentro de una liga. Ambas exactas por complemento de Schur (`PosteriorRapida`).
- Filas fuera del ajuste (< 100 min, o posición sin estimar) usan el **codificador** de cada red combinado con el prior
  N(μ_c, s_l²) de su competición, con Var(μ_c) y, si la competición-temporada no está en el ajuste, el nivel de la
  última temporada de esa liga más el paso κ² (`u_fuente = codificador_nivel_temporada_anterior`). Es el mismo
  tratamiento de `bbnorm3.exportar.traducir_filas`.
- **Alineamiento [decisión técnica de F0].** El espacio latente de cada red del ensemble es arbitrario: está
  identificado sólo hasta una transformación afín, que el decodificador absorbe, de modo que promediar las 20 redes
  «en crudo» no tiene sentido. Cada red k se alinea con la red de referencia (semilla 0) por mínimos cuadrados afines
  (ũ = A_k u + b_k, ajustados sobre las ≈ 30.000 personas-temporada del ajuste), y después se promedia:
  u = media_k(ũ_k); sd² = media_k Var(ũ_k) + Var_k(ũ_k) (dentro de cada red + entre redes). Se publica el R² del
  alineamiento por red y dimensión en `perfiles/meta.json`; una red con R² medio < 0,90 queda señalada. El
  alineamiento no cambia nada de la v3.2 (sus salidas usan cada red por separado); sólo define las coordenadas en que
  las capas 1-3 leen el latente.
- Los pesos B2 de la mezcla en el corte t son los que ese corte había decidido (0,5 en todas las métricas en 2023 y 2024;
  sin decisión en 2021 y 2022 → 0,5): el RAPM del corte mezcla v2 y red, mientras que el ajuste completo usa la red sola.
- Las coordenadas de los perfiles de corte (≤ t) son las de su propio ensemble ≤ t: las capas que se examinen en el
  corte t se entrenan y evalúan con esas coordenadas, nunca con las del ajuste completo.

### 1.3 Perfiles por corte (exámenes sin fuga)

`perfiles/corte_<t>/<temporada>.csv.gz` para t ∈ {2021, 2022, 2023, 2024} y todas las temporadas ≤ t:
- latente del ensemble ≤ t (las mismas redes por corte que el examen de la v3.2, `experimentos/v3/`);
- θ/v_j con la **fuente `V32_corte`** del simulador generalizada a cualquier temporada ≤ t (`bbequipo.perfiles.theta_corte`):
  v2 ≤ t (algoritmo A ajustado ≤ t y amortiguación ≤ t, `bbfit.sim_insumos.normalizacion_hasta`) mezclada con la CVAE
  ≤ t traducida a la vara EuroLeague de la temporada t, pesos B2 del corte (0,5 si el corte no decidió), salvaguardas
  de la v3.2 (liga con < 2 temporadas, redes que discrepan) y constantes del sustituto lineal del corte; donde falta la
  v2 ≤ t (fila o métrica sin enlace del A) se usa la red sola y donde falta la CVAE sólo la v2, como hace
  `bbnorm3.combinacion.ajustar_combinada`; varianza propia v_j = max(sd² − Var(δ_o), 0,1·sd²) como en `destino`;
- rol, estilos, edad y pista: por temporada (no cambian con el corte).
Regla de uso en las fases siguientes: en el examen del corte t, la fila de la temporada s ≤ t toma el perfil de
`corte_<t>/`. Cualquier otro uso del ajuste completo en un examen es fuga y se declara.

### 1.4 Contrato de datos (encargo §3; `bbequipo/contrato.py`, `data/modelos/v4_0/contrato/`)

Reglas fijadas en F0, antes de entrenar F1 (`contrato` del YAML):

| Regla | Valor | Motivo |
|---|---|---|
| Tramos de basura | **fuera** | fijado en el encargo |
| Clutch | **covariable** del tramo | fijado en el encargo |
| Exposición | **posesiones** del tramo = media de los dos lados de fga + 0,44·fta − oreb + tov | ε_s ~ N(0, σ²/n_s) |
| Localía | h_s = 1 para `team_a` (local; `bbstats.lineups`: `teams = [local, visitante]`) | covariable de F1 |
| Quintetos | sólo 5 contra 5 (`n_a = n_b = 5`) | el modelo es aditivo en 10 jugadores |
| Fases | regular y playoffs, con indicador | — |
| Posesiones mínimas por tramo | 0,5 | tramos vacíos fuera |
| Cobertura | liga-temporada con < 50 % de partidos con quintetos (`validacion.csv → usado_en_quintetos`) → **excluida** de F1-F3; entre 50 y 90 % → incluida **con aviso**; < 4 tramos por partido → excluida | pondera (por posesiones) o excluye, decidido aquí |

Resultado del inventario **[DATO, 04-11-2026, datos al 29-10]**: 115 liga-temporadas con tramos (2020-21 → 2026-27 en
curso); 99 incluidas, 12 con aviso, 4 excluidas (BCL 2020-21 41 %, VTB 2021-22 49 %, CBA 2024-25 32 %, NCAA 2024-25
27 % de partidos con quintetos); 1.152.179 tramos válidos y ≈ 2,99 M de posesiones incluidas en 38.679 partidos.
Mediana de posesiones por quinteto 3-5 (≈ 7,8 puntos de error de muestreo en el ORtg/100 de un quinteto de 200
posesiones → **nada se aprende en crudo**: primero lo aditivo, cada capa el residuo). Los huecos declarados en el
encargo se comprueban en `contrato_datos.json → huecos_declarados_comprobados`: NCAA 2020-23, BBL 2020-23, LNB 2020-21 y
VTB 2020-21 no tienen fichero de tramos (fuera por construcción); la CBA entra con aviso salvo 2024-25 (excluida); la
CBA no tiene coordenadas de tiro en ninguna temporada (`con_coordenadas = 0`), lo que no afecta a F1-F3 (no usan
coordenadas) y sí a los rasgos de zona, que ya llegan normalizados por la v3.2.

### 1.5 Límites declarados de la capa 0

- Las pertenencias de estilo se ajustaron con todas las temporadas (modelo no supervisado de la fase 6). En los exámenes
  de las capas 1-4 son una fuente menor de fuga que se declara y no se corrige en F0 **[HIPÓTESIS]**.
- Los corredores débiles de la v3.2 (Segunda → Tercera FEB, G League ↔ NBA, NCAA → NBA) arrastran su aviso hasta las
  anclas (condición (ii) del veredicto de aptitud del encargo §0.6).
- El latente de quien juega poco viene del codificador (más incertidumbre); la capa 1 lo sabe por `u_fuente` y por
  su sd. El sesgo heredado con quien acaba jugando poco (v3.3) se trata en F4 (§9.2 del encargo).

## 2. F1 · RAPM multiliga con prior del perfil (capa 1)

Orden del CEO: 04-11-2026, tras aprobar la puerta de la F0. Código: `bbequipo/rapm.py` (modelo), `bbequipo/examen_f1.py`
(examen, D2, F1-D). Checkpoint: `docs/checkpoints/V40_F1.md`.

### 2.1 Modelo

```
y_s = c_{ℓ,t} + κ·clutch_s + π·playoffs_s + Σ_{i∈A_s} β_i − Σ_{j∈B_s} β_j + ε_s,   ε_s ~ N(0, σ²/n_s)
β_i = g(x̃_i) + δ_i,   g(x̃_i) = γ₀ + γᵀ z_i,   δ_i ~ N(0, τ²)
```

- Tramo s: quintetos A (equipo local) y B (visitante) con 5 contra 5, n_s posesiones (contrato), y_s = 100·(pts_A − pts_B)/n_s.
  Como A es siempre el local, c_{ℓ,t} es la ventaja local de la liga-temporada (h_s y c_{ℓ,t} del encargo coinciden).
- β por **persona-temporada** (crosswalk): quien juega dos ligas la misma temporada tiene un solo β informado por las dos
  (puente en pista). Dentro de una liga, Σβ no es identificable con diferenciales: el nivel entre ligas lo pone el prior
  **[HIPÓTESIS declarada en el encargo]**.
- Prior g(x̃): lineal en los rasgos estandarizados del perfil ampliado (latente u, estilos, θ de caja y de pista, rol,
  edad, posición, máscara de bloques con dato) **estimado conjuntamente con β** (γ y δ en el mismo sistema de mínimos
  cuadrados penalizados, LSQR). Estimar γ a la vez evita la atenuación de la alternativa iterativa (regresar β̂ encogidos
  sobre x̃ y repetir), que con la poca información por jugador de un RAPM se queda donde empieza. Candidato alternativo
  (GBM por retroajuste) comparado en el corte de selección.
- τ² (dispersión de β alrededor de g) y α (precisión a priori de γ) por **máxima verosimilitud marginal** en una rejilla,
  con σ² del residuo; dos ciclos. Varianza de β: diagonal de (AᵀA)⁻¹ por sondas de Hutchinson (32).
- Descomposición O/D: dos filas por tramo (ataque de A frente a defensa de B y viceversa), β^O y β^D con el mismo prior.

### 2.2 Decisiones tomadas en el corte de calibración 2021 [DECISIÓN, antes de los cortes de decisión]

El corte 2021 → 2022-23 es, por prerregistro, el que calibra. Se usó para fijar la maquinaria, no para juzgarla:

1. **Mínimo de 1 posesión por tramo** (contrato, antes 0,5). Con 0,5–0,75 posesiones estimadas la varianza del diferencial
   por posesión es 18 frente a 3–5 en el resto (artefacto del estimador fga + 0,44·fta − oreb + tov): el 11 % de los tramos
   acaparaba el 32 % de la pérdida ponderada. Quedan 960.245 tramos válidos (antes 1.152.179).
2. **El RAPM normalizado de la misma temporada no entra en el prior** (`orapm_th`, `drapm_th` fuera de g). Es circular: son
   los propios tramos que F1 ajusta. Con ellos, el prior se sobredispersaba (DT 4,8 pts/100 dentro de liga) y predecía el
   margen de 2022-23 peor que la sola ventaja local (15,94 frente a 15,90); sin ellos, 15,14, al nivel del RAPM traducido
   de la v3.2 (15,13). El resto de rasgos de x̃ se mantiene; `orapm_th`/`drapm_th` siguen en el perfil para F2–F3.
3. **El RAPM normalizado de la temporada anterior sí entra** (`orapm_th_prev`, `drapm_th_prev`, con máscara): información
   legítima del pasado del jugador, que respeta el espíritu del §5.1 sin circularidad.
4. Estimación de τ: se examinaron momentos con varianza diagonal (colapsa τ) y validación cruzada por partido (curva plana)
   antes de fijar la verosimilitud marginal conjunta.

### 2.3 Examen prerregistrado (§11.1) y comprobaciones D2

Ver `docs/checkpoints/V40_F1.md`: margen por partido de t+1 frente a (a) interceptos liga-equipo-temporada, (b) RAPM
traducido de la v3.2 (`rapm_am`, el «L actual» del impacto) y (c) sólo ventaja local; test-retest; correlación prior–β de
los fichajes; D2 (sensibilidad a la red de referencia del latente y ablación del latente) en el corte 2022; F1-D.

## 3. F2 · Sinergia de pares (F2-A) y efectos dirigidos sobre compañeros (F2-B) (capa 2)

Orden del CEO: 04-11-2026, tras aprobar la puerta de la F1. Código: `bbequipo/sinergia.py`, `bbequipo/dirigidos.py`,
`bbequipo/examen_f2.py`. Checkpoint: `docs/checkpoints/V40_F2.md`. Salidas: `data/modelos/v4_0/sinergia/`.

### 3.1 F2-A · Sinergia simétrica de pares

```
y_s = [F1] + Σ_{(i,j)∈A_s} φ(i,j) − Σ_{(i,j)∈B_s} φ(i,j) + ε_s,     φ(i,j) = z_iᵀ M_r z_j + ψ_ij
```

- z_i: los 44 rasgos estandarizados del perfil ampliado (las columnas del prior de F1: sin el RAPM de la misma temporada);
  sin perfil → z = 0 → φ = 0. β de F1 congelados: F2 aprende el **residuo**.
- M simétrica 44 × 44. La suma de las 10 parejas de un quinteto es ⟨M, Q⟩ con Q = ((Σz)(Σz)ᵀ − Σzzᵀ)/2, así que por tramo
  u_s = vec(Q_A − Q_B) y el modelo es lineal en vec(M): ridge exacto (autovalores del Gram 990 × 990) con λ por
  verosimilitud marginal. Proyección de rango r por autovectores de mayor |autovalor|; r elegido en el corte de selección
  2021 (menor error de pareja nueva; a igualdad, el menor): **r = 4**.
- ψ_ij ~ N(0, κ²): efecto propio de cada pareja observada, ridge disperso sobre indicadores de pareja sobre el residuo tras
  M; κ por validación cruzada por partido con la línea base ψ = 0 como candidato. Sólo en el producto (compañeros con
  historia, F4); una **pareja nueva se predice sólo por perfiles** (φ̂ = z_iᵀ M_r z_j).
- Examen §11.2 (`examen_f2.py`): parejas de t+1 con ≥ 100 posesiones juntas que no compartieron tramo en ≤ t; reducción
  del MSE ponderado por pareja del residuo de F1 al restar φ̂; IC95 por bootstrap de equipos-temporada. Resultado: pasa en
  los tres cortes de decisión con magnitud despreciable (reducción ≈ 0,001 % del error; DT de φ̂ 0,03–0,17 pts/100 por
  pareja). El diagnóstico de λ muestra que sin contracción los perfiles explican el 0,3 % del residuo en muestra y empeoran
  las parejas nuevas: la sinergia predecible por perfiles es de segundo orden [LECTURA].

### 3.2 F2-B · Efectos dirigidos X → Y

```
d_k(X → Y) = m_k(z_X, z_Y) + ε,   k ∈ {cuota de tiro, eFG%, % asistidas, % en el aro, pts/100}
```

- Dato: `data/modelos/interacciones/` (v3.x): por pareja de compañeros X, Y de un equipo-temporada, la diferencia de la
  métrica k de Y con X en pista frente a sin X, con las posesiones de cada lado. Parejas con ≥ 100 posesiones juntas.
- Rasgos [z_X, z_Y, z_X ⊙ z_Y]; candidatos ridge y GBM por efecto (elegido en el corte de selección 2022: GBM en los
  cinco); peso n_ef = 1/(1/n_con + 1/n_sin); intervalos del 80 % conformales (cuantiles del residuo fuera de muestra del
  corte anterior, por cinco tramos de peso).
- Examen §11.2: MAE ponderado en t+1 frente a Δ = 0 y frente a la media de liga de t, con IC95 por bootstrap de
  equipos-temporada, en los tres cortes de decisión; cobertura del 80 % en [0,75, 0,85]. Se publican los efectos que pasan
  en los tres cortes: **cuota de tiro, % asistidas y pts/100**; eFG% y % en el aro quedan como ablación negativa.
- Producto: `dirigidos/modelos.pkl` (un GBM por efecto publicado + calibración), `dirigidos/efectos_<t>.csv.gz` (pareja
  observada: real, predicho e intervalo del 80 %) y `dirigidos.predecir` para parejas nuevas (F4). Las cuotas de tiro de
  un quinteto se renormalizan al 100 % al aplicarlas.

### 3.3 Qué se lleva la capa 4

`sinergia/W_sinergia.json` (M_r, medias y DT de los rasgos, fórmula) y `sinergia/psi.csv.gz` para el término de sinergia;
`dirigidos/modelos.pkl` para los efectos sobre compañeros. Ambos operan sobre β de F1 congelados.

## 4. F3 · Función de conjunto (capa 3, condicional)

Orden del CEO: 04-11-2026, tras aprobar la puerta de la F2 («opción (a)»: ejecutar F3 como examen acotado con la regla dura
§11.3). Código: `bbequipo/conjunto.py`. Checkpoint: `docs/checkpoints/V40_F3.md`. Salidas: `data/modelos/v4_0/conjunto/`.

### 4.1 Modelo

```
y_s = [F1] + [F2: Σφ_A − Σφ_B] + g(S_A) − g(S_B) + ε_s,      g(S) = ρ( Σ_{i∈S} ϕ(z_i) )
```

- z_i: los 44 rasgos estandarizados del perfil (los de F2; sin perfil → 0). β de F1 y M_r de F2 congelados: F3 aprende el
  residuo del quinteto completo.
- Deep sets: ϕ (44 → 16 → 16) por jugador, suma sobre los cinco (invariante a permutaciones), ρ (16 → 16 → 1). 1.300
  parámetros; AdamW con decaimiento de pesos 0,01, 2.000 pasos de 8.192 tramos, pérdida cuadrática ponderada por
  posesiones; 5 semillas promediadas (la red individual es inestable: en el corte 2024 dos de cinco empeoran por separado).
- Examen §11.3 (`conjunto.examen_corte`): quintetos no vistos de t+1 (conjunto de cinco personas ausente de los tramos ≤ t;
  son el 99 % de los tramos de t+1), perfiles de la temporada t; cociente RMSE(F1+F2+F3)/RMSE(F1+F2) con IC95 por bootstrap
  de partidos; se publica sólo si el IC95 superior < 1 en los tres cortes de decisión.
- Resultado: pasa en los tres cortes (cocientes 0,99926 / 0,99933 / 0,99951, IC95 superiores < 0,9997). Reducción del RMSE
  por tramo 0,05–0,07 %; g tiene una señal común de ≈ 2,8 pts/100 en la diferencia entre dos quintetos (DT total 3–4, de la
  que 1,6–3,1 es desacuerdo entre semillas), calibrada. Ablación con ρ lineal (g aditiva por jugador) y diagnóstico de qué
  agregados del quinteto explican g: ver el checkpoint.

### 4.2 Decisión y qué se lleva la capa 4

Puerta aprobada por el CEO (05-11-2026) con la **variante aditiva** (ρ lineal, `f3.rho_lineal: true`): g(S) = Σ_i h(z_i),
«capa 3 reducida: corrección no lineal por jugador». La ablación mostró que la red completa y la aditiva pasan igual el
§11.3; se elige la simple [DECISIÓN post hoc por parsimonia]. `conjunto/redes.pkl` (estado de las cinco redes y los
rasgos) y `conjunto/F3_conjunto.json`; `ConjuntoNet.cargar` y `predecir` devuelven g(S_A) − g(S_B) para cualquier par de
quintetos con perfiles (sin perfil → z = 0). Hallazgo que F4 incorpora: los jugadores en su primera temporada tienen β
1,3 pts/100 por debajo de la media de su liga; a quien no tiene perfil ni β se le imputa ese nivel, no la media.

## 5. F4 · Composición, Δ de equipo y A5 (capa 4)

Orden del CEO: 05-11-2026, con la puerta de la F3 (opción b). Código: `bbequipo/equipo.py`, `bbequipo/a5.py`. Checkpoint:
`docs/checkpoints/V40_F4.md`. Salidas: `data/modelos/v4_0/equipo/`.

### 5.1 Modelo de equipo

```
T(R) = E_{S ~ P(·|R)}[ f(S) ],   f(S) = Σ_{i∈S} β_i + Σ_{i<j∈S} φ_ij + Σ_{i∈S} h(z_i)
Net̂(R) = T(R) − media de la liga-temporada;   Δ̂Net = Net̂(R'_{t+1}) − Net̂(R_t)
```

- P(S | R) a través de las cuotas de posesiones p_i (minutos / minutos de un puesto; Σ p_i = 5): observadas en t, proyectadas
  en t+1 con el motor de minutos de la v3.3 (`bbfit.simulador.plantilla/utilidad/tendencia` + `bbfit.reemplazo.asignar_minutos`:
  Plackett-Luce sobre nivel × encaje, rotación del entrenador, mínimos por posición), con los pesos de la utilidad ajustados
  sólo con temporadas ≤ t (`equipo.pesos_pl`). Lo aditivo (β, h) es exacto en las cuotas; el término de parejas usa
  P(i, j) ≈ p_i p_j renormalizado a 10 parejas.
- Incertidumbre: β ~ N(β̂, sd) por jugador y simulación; minutos por simulación del motor; φ y h fijos. Intervalos del 80 %
  del Monte Carlo ensanchados con los residuos de los cortes anteriores (conformal).
- Jugador de t+1 sin β ≤ t: prior del perfil; sin perfil: nivel de «jugador nuevo» de su liga (media de β de los jugadores
  en su primera temporada, ≤ t).
- Examen §11.4 (`equipo.main`): transiciones reales equipo-temporada del libro de roles (mismo club y liga), plantilla
  real de t+1, todo lo demás ≤ t; líneas base persistencia, aditivo F1 y GBM directo (cortes anteriores); MAE de ΔNet,
  Spearman, cobertura del 80 %, por grupo de liga y global; sesgo por tercil de minutos proyectados de las altas; diagnóstico
  con minutos reales de t+1 (oráculo).

### 5.2 A5 · Producción no lineal en minutos y rol

```
y_real − ŷ = s(Δmin) + c·Δrol + δ[rol_o → rol_d] + (carga: minutos de destino por encima de 30') + ε
```

Generaliza B9 (Δy = b·Δmin + c·Δrol) con la misma maquinaria del examen v3.2/v3.3 (fuente V32_corte, cortes anidados,
escenario «rol asignado»): spline lineal a trozos de Δmin con 3 nudos (cuantiles 0,25/0,5/0,75), matriz 5 × 5 de desviaciones
por par de roles contraída hacia la recta por Bayes empírico (τ² por momentos), covariable de carga si el diagnóstico
dentro de jugador es estable. Puerta §11.6 frente a B9 lineal reajustado con los mismos insumos: pasa (pts/100 −2,3 %, TS%
−2,2 %, IC90 < 0; contracción efectiva). Se publica A5 con carga en ocho métricas y B9 en OREB/100 (regla por métrica).

## 6. F5

Pendiente de la orden del CEO. Hiperparámetros, salidas y criterios prerregistrados en `configs/equipo_v40.yaml` (`f5`,
`criterios`).
