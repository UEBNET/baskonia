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

## 2. F1 … F5

Pendientes de la orden del CEO para cada fase. Los hiperparámetros, las salidas y los criterios prerregistrados de todas
ellas están ya en `configs/equipo_v40.yaml` (`f1`, `f2`, `f3`, `f4` con `a5`, `f5` y `criterios`), de modo que las
fases se ejecutan sin tocar criterios después de ver resultados.
