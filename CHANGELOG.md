# Registro de cambios

## Encaje v2 (fases 1-9, 21-10-2026 → 23-10-2026): resumen consolidado

Proyecto multifase sobre la línea base de la auditoría `docs/AUDIT_2026-10-21.md`. Cada fase tiene código, YAML en
`configs/`, tests sintéticos, registro en MLflow e informe en `docs/checkpoints/F<n>.md`.

| Fase | Qué añade | Órdenes | Salidas | Informe |
|---|---|---|---|---|
| 1 | Primera, Segunda y Tercera FEB en el esquema común; contrato de datos; posesiones reales; correspondencia de jugadores entre ligas | `bbstats historico/feb/contrato`, `bbmodel crosswalk` | `data/processed/…/feb/`, `feb_*.csv`, `player_id_crosswalk.csv` | F1 |
| 2 | Normalización amortiguada (grafo de puentes con varianza acumulada, contracción por escalón, mapeo monótono probado, λ(d) → constante, IPW); 15 ligas en `bbmodel`/`bbestilo` | `bbmodel amortiguar` | `normalizacion_amortiguada/`, columnas `<m>_am*` del dataset normalizado | F2 |
| 3 | Roles por minutos (RESIDUAL … GO-TO-GUY), GTI, vector de rol, cambios de rol (BOCPD) | `bbfit roles` | `roles/` | F3 |
| 4 | Reemplazo de rol: libro de volumen, desplazamiento de minutos / de rol, tasa de relleno, elasticidad uso–eficiencia con IV, suma fija del uso, minutos endógenos | `bbfit reemplazo` | `reemplazo/` | F4 |
| 5 | Entropía de estilo y de rol, volatilidad σ_i, entropía de equipo | `bbfit entropia` | `entropia/` | F5 |
| 6 | Taxonomía unificada de 6 estilos jugador ↔ equipo | `bbfit estilos` | `estilos_unificados/` | F6 |
| 7 | Adaptación al cambio de liga: Δ jerárquico, curva, censura IPCW, priors, ADAPT% | `bbfit adaptacion` | `adaptacion/` | F7 |
| 8 | Simulador de encaje v2 (rol y minutos endógenos, Fit descompuesto, avisos) y su validación | `bbfit simular` y órdenes de la fase 8 | `simulador/v2/`, `data/artifact/simulador/` | F8 |
| 9 | Documentación: artículo con Parte II y notación formal, LaTeX autónomo, diccionario de datos, glosario, README, contexto | `bbestilo articulo` (= `python -m bbfit.articulo`) | `docs/articulo/`, `docs/data_dictionary.md`, `docs/glosario.md` | este registro |

### Cambios incompatibles (breaking changes)

1. **Identidad de personas**: los modelos A/B usan también las uniones automáticas del crosswalk y el umbral de
   fusión pasa de 0,80 a **0,75** (fase 2, decisión del usuario): cambian `persona_id` y el número de personas
   (39.647 registros, 14.535 personas). Cualquier unión guardada por `persona_id` anterior debe rehacerse.
2. **15 ligas en los modelos**: A, B, pista, contexto, interacciones, escalas y `bbfit reemplazo` se reajustaron con
   las FEB; todos los equivalentes EuroLeague, L y percentiles cambian. `algoritmo_A/validacion.csv` sigue siendo de
   12 ligas (no se relanzó `bbmodel validar`). VaDE (Parte I) no se reentrenó con las FEB.
3. **L, contexto y escalas ±100 leen `<m>_am`** (normalización amortiguada) en vez de A+B
   (`configs/normalization.yaml → usar_amortiguado`); las columnas antiguas del dataset normalizado no cambian, pero
   `L`, `ctx_*` y las escalas sí.
4. **Corrección de σ²** en `bbmodel/suerte.py` (pendiente ≤ 0 → mediana de las demás ligas): cambia el paso 1 del A
   en BCL, NBA, FEC y Segunda FEB (p. ej. σ² de pts/100 en la BCL de 1,8·10⁻⁴ a 105,2).
5. **Cortesía HTTP compartida**: `bbstats/http.py` aplica la pausa por dominio a todos los clientes del proceso
   (antes, por cliente): las descargas en paralelo contra un mismo dominio son más lentas.
6. **Configuración YAML** (`configs/*.yaml`) para todas las capas nuevas y registro MLflow en `experimentos/`
   (no versionado; MLflow 3 necesita `MLFLOW_ALLOW_FILE_STORE=true`, que `bbfit.registro` fija).

## 2026-10-29 — Fase 8: simulador de encaje v2 (sin minutos manuales) y su validación

Añadido
* `bbfit/simulador.py` (motor Monte Carlo: nivel traducido con la normalización amortiguada, adaptación de la fase 7,
  rol y minutos endógenos con Plackett-Luce y las tendencias del entrenador, uso de suma fija y curva uso-eficiencia,
  compañeros, estilo y complementariedad, ruido personal, ritmo; Fit aditivo; impacto en el Net; quintetos; avisos),
  `bbfit/sim_insumos.py`, `bbfit/validacion.py` (examen temporal cronológico, baselines, bootstrap por club, segmentos,
  dejar fuera una liga, normalización reajustada con ≤ t), `bbfit/sim_exportar.py`, `configs/simulation.yaml`.
* Órdenes `python -m bbfit simular | backtest | pesos-simulador | historico | exportar-simulador`.
* `data/modelos/simulador/v2/` (histórico versionado v2.0, pesos, validación) y `data/artifact/simulador/` (no versionado).
* Atlas: «Simular fichajes» y «Simular equipo completo» sin campos de minutos; tarjetas v2 (roles, minutos e intervalos,
  producción por 100 y por partido, Fit descompuesto, ADAPT% y curva, impacto, quintetos, avisos); motor en
  `artifact/atlas/simulador_v2.js`; nombres de estilo unificados en tablas, fichas, leyenda y tooltips (VaDE como
  «estilo de mapa»); búsqueda de jugadores que sólo están en el simulador (FEB).
* Tests: `tests/test_simulation.py` (13), `tests/js/paridad_simulador.js`, `tests/js/atlas_simulador.js`.

Cambiado
* `bbfit/reemplazo.py::asignar_minutos`: argumentos opcionales `niveles_sim` y `presencia` (sin cambio por defecto).
* `bbestilo/exportar.py`: exporta el mapa con las competiciones del modelo VaDE guardado (12; las FEB no tienen estilo
  VaDE) y añade `tid` (clubes) y `pid` (jugadores) para enlazar con el simulador. `bbestilo/datos.construir` y
  `encaje.conjunto` aceptan `ligas`.
* `artifact/empaquetar.py`: publica `atlas/simulador_v2.js` y `atlas/simulador/*.json`.

Resultados (examen 2021-22 … 2024-25 → t+1, 4.512 fichajes): MAE de minutos 4,71 frente a 5,84 (Atlas anterior) y 5,63
(modelo simple); log-loss de rol 1,235 frente a 2,676 y 1,257; pts/100 empate con el Atlas anterior y mejor que el
simple; TS% peor que ambos. Detalle en `docs/checkpoints/F8.md`.

## 2026-10-23 — Fase 9: documentación (artículo científico descartado)

Añadido
- `docs/data_dictionary.md` (todas las tablas de `data/processed/` y `data/modelos/`), `docs/glosario.md` (roles,
  estilos y medidas para dirección deportiva); README §17-§20 (orden de ejecución de `bbfit`, `configs/*.yaml`,
  MLflow); secciones nuevas en `CONTEXTO_AGENTE.md`; este resumen consolidado.

Cambiado
- `bbestilo/figuras.py`: paleta de 15 ligas.

Retirado (26-10-2026, por decisión del usuario: el artículo científico no se actualiza)
- La Parte II del artículo (`bbfit/articulo.py`, `docs/articulo/fit_v2.tex` y figuras, recursos KaTeX y fuentes,
  `tests/test_articulo.py`); el PDF y `bbestilo/articulo.py` vuelven a su versión anterior.

## 2026-10-23 — Fase 7: adaptación al cambio de liga (`bbfit adaptacion`)

Añadido
- `bbfit/adaptacion.py` y `python -m bbfit adaptacion [--rehacer] [--sin-validacion]` (reanudable, caché en
  `experimentos/cache_adaptacion/`); hiperparámetros en `configs/adaptacion.yaml`; registro en MLflow.
- Interfaz para el simulador: `prior(liga_origen, liga_destino, grupo_nacionalidad, pos3, metrica)` con jerarquía de
  reserva celda → par → escalón de destino → global, `grupo_nacionalidad(...)` y `curva(g, delta, kappa)`.
- Identificación de 5.040 traspasos (entre temporadas, adiciones y dentro de la temporada) con el `persona_id` del
  crosswalk 0,75; ŷ = origen traducido a la escala de destino invirtiendo la normalización amortiguada; modelo
  jerárquico gaussiano (Gibbs) del log-cociente y/ŷ con efectos de pareja y escalón y covariables (nacionalidad,
  pos3, arquetipo, edad, roles, salto de nivel, estilo de equipo, entrenador); curva por partido con grupo de control;
  IPCW de la censura; ADAPT% por traspaso con examen temporal, dejando fuera una liga y calibración.
- Salidas en `data/modelos/adaptacion/` (`adaptation_priors.csv`, `adapt_historico.csv.gz`, `adapt_pct_roles.csv`,
  coeficientes, hipótesis EE. UU., curvas, censura, supervivencia, segunda temporada, validación, calibración).
- Tests sintéticos `tests/test_adaptacion.py` (10).

Resultados principales: estadounidense en su primer año europeo −6,8 % [−9,7, −3,8] de ADAPT% compuesto frente al
europeo que cambia de liga (sin adaptación más lenta detectable); sin hueco de arranque propio del que cambia de liga
(todos arrancan ~2 % abajo); el IPCW baja el Δ medio 1-2 puntos.

Detalle, resultados y riesgos: `docs/checkpoints/F7.md`.

## 2026-10-23 — Fase 6: taxonomía unificada de estilos jugador ↔ equipo

Añadido
- `bbfit/estilos_unificados.py` y `python -m bbfit estilos [--reusar-k]`: 12 rasgos con la misma definición para
  jugador y equipo (ritmo, 3PAr, triple de esquina, aro, FTr, canastas sin asistencia, AST%, rebote ofensivo,
  TOV%, robos, tapones, faltas) en z por rangos dentro de cada liga-temporada (15 ligas, incluidas las FEB);
  mezcla gaussiana ajustada sobre jugadores (≥ 300 min) con proyección de los equipos; K por BIC + estabilidad
  bootstrap → **6 estilos**: Spacing, Circulación, Isolation, Old-School, Pistons, Pintura. Estilo principal,
  secundario, vector de pertenencia y etiqueta («puro», «A · B») por equipo-temporada, jugador-etapa y tramo de
  entrenador. Registro en MLflow (experimento `estilos_unificados`).
- `configs/styles.yaml` (umbrales, regla de K, nombres, colores, definiciones y firmas de nombre).
- Salidas `data/modelos/estilos_unificados/{equipos.csv, jugadores.csv.gz, estilos.json, seleccion_k.json,
  correspondencia_vade.csv}`; correspondencia con VaDE (ARI 0,03: miden cosas distintas).
- Tests sintéticos `tests/test_estilos_unificados.py`.

Cambiado
- `bbestilo/exportar.py`: campos nuevos `eu`, `eu2`, `eu_p`, `eu_probs`, `eu_etiqueta` en clubes, etapas de
  entrenador y jugadores del Atlas, y `meta.estilos_unificados`; los campos VaDE no cambian.
- `bbfit/__main__.py`: orden `estilos`.

Detalle, resultados y riesgos: `docs/checkpoints/F6.md`.

## 2026-10-23 — Fases 3, 4 y 5: roles por minutos, reemplazo de rol y entropía (`bbfit`)

Añadido
- `python -m bbfit roles|reemplazo|entropia` (`bbfit/__main__.py`); cada ejecución queda registrada en MLflow
  (`bbfit.registro`, almacén local `experimentos/`, no versionado). Umbrales y pesos en `configs/roles.yaml`,
  `configs/reemplazo.yaml` y `configs/entropia.yaml`.
- Fase 3 (`bbfit/roles.py`, `bbfit/cambios.py`, `bbfit/datos.py`): tabla partido × jugador desde los tramos y tiros
  (`data/modelos/roles/partidos_jugador/<t>.csv.gz`, con ausencias), respaldo de caja donde no hay jugada a jugada,
  roles RESIDUAL/PROFUNDIDAD/ROTACIÓN/TITULAR/GO-TO-GUY por MIN% (40'/48'), GTI, vector de rol Dirichlet para
  muestras < 5 partidos, H_rol, cambios de rol con detección bayesiana en línea (BOCPD propio) y covariables
  (entrenador, vacío de rol, fichaje, rendimiento reciente). Salidas `player_role_spells.csv.gz`,
  `player_role_season.csv.gz`, `team_role_structure.csv` y validación.
- Fase 4 (`bbfit/reemplazo.py`): producción por rol y proyección condicionada al rol de destino; elasticidad
  uso-eficiencia con variable instrumental (vacío de rol del partido) y agrupamiento parcial por pos3; redistribución
  de suma fija; libro de minutos por rol entre temporadas (identidad exacta) con tasa de relleno, transiciones de
  rol, asociación con el cambio de Net (bootstrap, no causal); calidad de compañeros; tendencias de entrenador y
  `asignar_minutos` (Plackett-Luce con restricciones) para el simulador. Salidas en `data/modelos/reemplazo/`.
- Fase 5 (`bbfit/entropia.py`): H_estilo (zonas de tiro + acciones de caja, Dirichlet con intervalo), H_rol
  posterior, volatilidad intrínseca σ_i (residuo sin contexto, varianza por exposición, contracción jerárquica de
  log σ²) y entropía de equipo (uso, tiros, minutos, red de pases). Salidas en `data/modelos/entropia/`.
- Tests sintéticos `tests/test_roles.py`, `tests/test_reemplazo.py`, `tests/test_entropia.py` (29).

Cambiado
- `bbfit/registro.py`: permite el almacén de ficheros de MLflow 3 (`MLFLOW_ALLOW_FILE_STORE`).
- `.gitignore`: caché `data/modelos/roles/_cache/`.

Detalle, resultados y riesgos: `docs/checkpoints/F3.md`, `F4.md`, `F5.md`.

## 2026-10-23 — Fase 2: normalización con amortiguación del salto de nivel (15 ligas)

Añadido
- `bbmodel/amortiguacion.py` y `python -m bbmodel amortiguar [--validar --variante V | --elegir | --diagnostico P]`;
  configuración en `configs/normalization.yaml`. Nivel por competición-temporada encadenado por un grafo de puentes
  (mínimos cuadrados: suma de varianzas en serie, precisión inversa en paralelo), contracción bayesiana por escalón con
  la media del escalón como nodo latente (τ por EM), mapeo monótono por liga y métrica (isotónica + PCHIP), λ(d)
  elegida por error dejando fuera una liga, pesos de probabilidad inversa para la selección de los puentes, exposición
  en posesiones (40'/48'). Salidas en `data/modelos/normalizacion_amortiguada/` (`league_offsets.csv`, traducciones,
  diagnóstico antes, validación temporal y dejando fuera una liga, ejemplos de puentes reales).
- Dataset normalizado: columnas `<m>_A_am`, `<m>_am`, `<m>_am_lo/_hi`, `<m>_am_pctel` (las anteriores no cambian). L,
  contexto y escalas ±100 leen `<m>_am` (`usar_amortiguado`).
- `identidad.unir_crosswalk`: los modelos A/B usan también las uniones automáticas del crosswalk (umbral 0,75,
  decisión del usuario).
- Tests sintéticos `tests/test_normalization.py` (12).

Cambiado
- Primera, Segunda y Tercera FEB en las listas de ligas de `bbmodel` y `bbestilo`; pista, A, B, contexto,
  interacciones, escalas y `bbfit reemplazo` reajustados con las 15 ligas (VaDE no).
- Variante por defecto `sin_mapeo` (elegida con el corte 2023-24 → 2024-25): empata con el A lineal en MAE (1,006 y
  1,000) y mejora la cobertura del 80 % (0,829 → 0,841).
- Documentación: `docs/normalizacion_amortiguada.md` (nuevo); `algoritmo_A.md`, `algoritmo_B.md`,
  `datos_normalizados.md` sin las cifras de «8 ligas»; tabla §4 de `estilos_de_juego.md` con la numeración de
  `config/estilos.json`.

Corregido
- `suerte.py`: σ² no identificado (pendiente ≤ 0 de la recta varianza–exposición) → mediana de las demás ligas.
  Hallazgo 7 de la auditoría: pts/100 en la BCL tenía σ² = 1,8·10⁻⁴; afectaba también a NBA, FEC y Segunda FEB.

Detalle, resultados y riesgos: `docs/checkpoints/F2.md`.

## 2026-10-22 — Fase 1: competiciones FEB (Primera, Segunda y Tercera FEB)

Añadido
- Tres ligas nuevas en el mismo esquema y tubería: `feb1` (Primera FEB / LEB Oro), `feb2` (Segunda FEB / LEB Plata)
  y `feb3` (Tercera FEB / Liga EBA): Primera FEB 2022-23 a 2026-27, Segunda y Tercera 2023-24 a 2026-27 (alcance
  decidido por el usuario; `temporada_inicial` por liga en config). Grupo = atributo del partido.
  `config/competition_aliases.json` con los nombres históricos por temporada.
- Adaptador `bbstats/adapters/feb.py` (calendario por postback de baloncestoenvivo.feb.es, KeyFacts/BoxScore de
  intrafeb.feb.es con el token anónimo de la página pública, plantillas y entrenador de Equipo.aspx). Bruto incremental.
- Fuente de jugada a jugada `feb` (`bbstats/lineups/sources/feb.py`): formato estructurado (2024-25+, con
  coordenadas) y formato texto (hasta 2023-24, nombres emparejados con el boxscore).
- `bbstats/lineups/possessions.py`: posesiones reales evento a evento (`possession_id`), genérico para todas las ligas.
- `bbstats/contrato.py` y `python -m bbstats contrato --ligas feb1 feb2 feb3`; `python -m bbstats feb` (partidos con
  grupo, `feb_cobertura.csv`, `feb_posesiones.csv`, `feb_sesgo_registro.csv`).
- `bbmodel/crosswalk.py` y `python -m bbmodel crosswalk`: `player_id_crosswalk.csv` (confianza y método) y
  `crosswalk_revision.csv` (casos dudosos, no aplicados). Umbrales en `config/sources.json → identidad`.
- Entrenadores FEB (uno por equipo y temporada, de la página del equipo) en `bbstats/entrenadores.py`.
- Sistemas de coordenadas FEB en `bbmodel/zonas.py` (calibrados: 99,1-99,3 % de acierto 2/3).
- Tests `tests/test_contract_feb.py` (datos sintéticos).

Cambiado
- `bbstats/http.py`: la pausa por dominio es común a todos los clientes del proceso (antes, por cliente), para que
  varias ligas del mismo dominio en paralelo respeten la cortesía.
- `bbmodel/identidad.py`: las FEB cuentan como ligas nacionales (pueden coincidir con copas europeas).

Detalle, resultados y riesgos: `docs/checkpoints/F1.md`.
