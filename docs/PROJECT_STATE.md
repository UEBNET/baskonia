# Estado del proyecto — Baskonia Analytics (CERNO)

> Memoria técnica bajo demanda. Cada sección es autocontenida: lee sólo la que afecte a tu tarea.
> Estado auditado: commit `150e814` de `claude/basketball-stats-extractor-jpas93` (29-10-2026). Leyenda:
> ✅ implementado y validado · 🟡 implementado sin validar o parcial · ❌ pendiente.
> Las cifras proceden de `data/modelos/**/resumen.json`, `data/modelos/**/validacion*` y `docs/checkpoints/F*.md`
> (comprobadas contra los ficheros salvo que se indique). Nada aquí es estimación nueva.

## Índice
1. [Historial de encargos](#1-historial-de-encargos)
2. [Datos](#2-datos)
3. [Modelos](#3-modelos)
   - 3.1 [Normalización amortiguada](#31-normalización-amortiguada-entre-ligas)
   - 3.2 [Roles y changepoints](#32-roles-y-changepoints)
   - 3.3 [Reemplazo de rol](#33-reemplazo-de-rol-formulación-propia)
   - 3.4 [Entropía y volatilidad](#34-entropía-y-volatilidad)
   - 3.5 [Estilos unificados (y VaDE legado)](#35-estilos-unificados-y-vade-legado)
   - 3.6 [Adaptación entre ligas y ADAPT%](#36-adaptación-entre-ligas-y-adapt)
   - 3.7 [Simulador de encaje v2 e Índice Fit](#37-simulador-de-encaje-v2-e-índice-fit)
4. [Artefacto](#4-artefacto)
5. [Deuda técnica y siguientes pasos](#5-deuda-técnica-y-siguientes-pasos)
6. [Discrepancias con lo recordado](#6-discrepancias-con-lo-recordado)
7. [Tabla de componentes](#7-tabla-de-componentes)

---

## 1. Historial de encargos

Ramas: `claude/basketball-stats-extractor-jpas93` = rama viva (todo lo de abajo). `main` sólo contiene hasta el PR
UEBNET/baskonia#1 (12-10-2026). PR UEBNET/baskonia#2 (`claude/bold-euler-hubmhk`, estilos VaDE) sigue abierto pero
está contenido en la rama viva. `claude/fervent-pascal-1tgdwd`: extractor y panel para la intranet del club «Basket
Basko» (15-10-2026), independiente, no integrado. `Simulación` = mismo commit que `bold-euler`.

| Fecha | Encargo | Estado |
|---|---|---|
| 12-10-2026 | Extractor `bbstats` por capas, 8 ligas (EL, EC, ACB, NBA, G League, LBA, BBL, LNB), fases, esquema de 480 columnas, BasketNews, Mesa Multiliga (Artifact) y Routine EJECUTAR | ✅ |
| 12/13-10 | Histórico 2020-21 → 2026-27; semillas BBL; correcciones G League (TL único), LBA/LNB playoffs | ✅ |
| 13-10 | Algoritmo A (traducción a EuroLeague) y B (red «ADN»); pestaña Normalización | ✅ (validación con 12 ligas, no relanzada con 15) |
| 13/14-10 | Estilos VaDE (`bbestilo`): 6 estilos sin nivel, mapa 3D, simulador por media ponderada, artículo PDF | ✅ (legado) |
| 15-18-10 | Quintetos/jugada a jugada (`bbstats/lineups`), entrenadores por partido, ligas BCL/FEC/BSL/GBL, reentreno con 12 ligas | ✅ |
| 21-10 | Auditoría (`docs/AUDIT_2026-10-21.md`): línea base del proyecto multifase | ✅ |
| 22-10 | F1 FEB (Primera/Segunda/Tercera), contrato, posesiones reales, crosswalk | ✅ |
| 23-10 | F2 normalización amortiguada (15 ligas) | ✅ (no mejora el MAE puntual; mejora calibración) |
| 23-10 | F3 roles + BOCPD · F4 reemplazo de rol · F5 entropía/volatilidad | ✅ |
| 23-10 | F6 taxonomía unificada (6 estilos) | ✅ |
| 23-10 | F7 adaptación y ADAPT% | ✅ (calibración fuera de muestra con pendiente ≈ 0,55) |
| 23-26-10 | F9 documentación (diccionario, glosario); Parte II del artículo retirada por decisión del usuario | 🟡 (quedan marcadores `[[F8: …]]`) |
| 29-10 | F8 simulador v2 sin minutos manuales + examen temporal; Atlas v2 | ✅ |
| 29-10 | Rediseño publicado integrado (shell «CERNO Analytics», capa de diseño común) en Mesa, Atlas y Quintetos | 🟡 (restos de marca EBATE) |
| 29-10 | Este encargo: memoria del proyecto (`CLAUDE.md`, este fichero, `docs/RESUME_PROMPT.md`) | ✅ |

## 2. Datos

### 2.1 Fuentes y endpoints (`config/sources.json`, `bbstats/adapters/`)
| Liga | Adaptador | Fuente |
|---|---|---|
| `euroleague`, `eurocup` | `euroleague.py` | feed oficial `feeds.incrowdsports.com/provider/euroleague-feeds/v3/competitions/{E,U}/statistics/…` (agregados; playoffs = total − RS); jugada a jugada `live.euroleague.net` |
| `acb` | `acb.py` | `api2.acb.com` (calendario + boxscore por partido; clave pública de la web) |
| `nba` | `bref_nba.py` | Basketball-Reference (vía binario `curl`, 3,5 s/petición); stats.nba.com bloquea la nube |
| `gleague` | `nba.py` | `stats.gleague.nba.com/stats/*` (TL único: `tiro_libre_unico`, coef. posesión 0,79) |
| `lba` | `lba.py` | `legabasket.it/api/championships/*` |
| `bbl` | `bbl.py` | `__NEXT_DATA__` de `easycredit-bbl.de/spiele/<id>`; ids semilla en config |
| `lnb` | `lnb.py` | `api-prod.lnb.fr` con token anónimo (sin totales de rival → `calidad_contexto = parcial`) |
| `bcl`, `fec` | `fiba_web.py` | HTML Next.js de `fiba.basketball` |
| `bsl`, `gbl` | `fiba_livestats.py` | `fibalivestats.dcd.shared.geniussports.com/data/<id>/data.json` (ids localizados por barrido) |
| `feb1`, `feb2`, `feb3` | `feb.py` | calendario `baloncestoenvivo.feb.es` (postback), `intrafeb.feb.es/LiveStats.API/api/v1/{KeyFacts,BoxScore}` (token anónimo de la página), `Equipo.aspx` (plantilla y entrenador) |
| enriquecimiento | `enrich/basketnews.py` | `bn_*` on/off y ratings (sólo EL y ACB) |

### 2.2 Esquema y granularidad
- Bruto: `data/raw/<liga>/<T>/<liga>_<T>_<fecha>.json.gz` (+ `pbp_*`, `entrenadores_*`); incremental en BCL/FEC/BSL/GBL/FEB.
- Procesado: `data/processed/<T>/ligas/<liga>.csv` — 1 fila = jugador × equipo × liga × temporada × fase; 480 columnas
  (`bbstats/schema.py`: identidad, totales, por partido/36/40/100, tiro, ratios, ratings, contexto, `src_*`, `bn_*`, `rs_*`/`delta_*`).
- Jugada a jugada: `data/processed/<T>/quintetos/<liga>/{tramos,tiros}.csv.gz`, `quintetos/trios/parejas`, `jugadores.csv`
  (on/off, RAPM λ = 1500), `equipos.csv`, `asistencias.csv`, `validacion.csv`.
- Entrenadores: `data/processed/<T>/entrenadores/<liga>_{partidos,tramos}.csv`, `entrenadores.csv`, `entrenadores_cobertura.csv`.
- FEB: `data/processed/<T>/feb/<liga>_{partidos,equipos}.csv` (grupo como atributo), `feb_{cobertura,contrato,posesiones,sesgo_registro}.csv`.
- Identidad: `player_id_crosswalk.csv` (persona_id, confianza, método; umbral 0,75) y `crosswalk_revision.csv`
  (cola no aplicada). Resultado F2: 39.647 registros → 14.535 personas.
- Diccionario completo: `docs/data_dictionary.md`.

### 2.3 Contrato de datos
`bbstats/contrato.py` (`python -m bbstats contrato --ligas feb1 feb2 feb3`; **sólo FEB**). Reglas: tipos, rangos,
identidades (fgm = fg2m + fg3m…), nulos, clave única partido × equipo × jugador, Σ minutos = 200 + 25·OT ± 1, marcador,
jugada a jugada ↔ boxscore (pts, FGA, FGM, rebotes ±3, asistencias ±2). Resultado (F1): 100 % en tipos, rangos,
identidades, nulos, clave y marcador; minutos ≥ 99,5 %; coherencia PBP 100 % desde 2024-25 salvo rebotes/asistencias;
rebotes 39-66 % en 2022-24 (texto). Tests: `tests/test_contract_feb.py`.

### 2.4 Matriz de cobertura (resumen)
- 12 ligas: 2020-21 → 2026-27 (2026-27 parcial a oct-2026; NBA/G League 2026-27 sin datos). BSL 2021-22 → 2024-25 sin
  fuente. Quintetos validados ≥ 84-100 % por liga-temporada (README §12, §15).
- FEB (`feb_cobertura.csv`): feb1 2022-23 → 2026-27 (PBP 98,8-100 %); feb2 y feb3 2023-24 → 2026-27 (PBP ≥ 99,7 %);
  coordenadas sólo desde 2024-25. 8.102 partidos FEB, 6.369 jugadores (id FEB).
- Entrenador: por partido en EL/EC/ACB/LBA/BBL/NBA(LNB por fechas); **un entrenador por temporada** en FEB y G League.
- Huecos conocidos: BBL 2020-23 y BCL 2020-21 (76/152) sin cambios en el PBP; LNB 2020-21 sin PBP; EuroLeague 2021-22
  299/327 partidos; Tercera FEB 2023-24 y 2026-27 casi sin entrenador; FEB sesgo de registro en AST (0,53 AST/FGM vs 0,57-0,66).

## 3. Modelos

### 3.1 Normalización amortiguada entre ligas
**Estado:** ✅ (validada; variante en producción `sin_mapeo`).
Formulación (`docs/normalizacion_amortiguada.md`). Nivel por nodo competición-temporada con EuroLeague = 0:
$$\hat\delta=\arg\min_\delta\sum_{(a,b)}\frac{(\delta_b-\delta_a-d_{ab})^2}{\sigma^2_{ab}},\qquad \sigma^2_{ab}=\max(\sigma^2_{\text{modelo}},s^2_{ab}/n_{ab})$$
(serie: suma de varianzas; paralelo: precisión inversa). Contracción por escalón:
$\delta_{c,t}\sim\mathcal N(\mu_{e(c)},\tau^2_{e})$, $\mu_e\sim\mathcal N(0,2^2)$, τ por EM ($\tau\ge0{,}05$).
Transferibilidad: $\theta_{ref}=\mu_{orig}+\lambda(d)\,(\theta_{trad}-\mu_{orig})$, λ ∈ {constante, exponencial, logística}
elegida por error dejando fuera una liga. Selección de puentes: pesos IPW $1/\hat p(\text{puente}\mid\text{minutos, nivel})$.
Mapeo de cuantiles monótono (isotónica + PCHIP) opcional. Unidades: por 100 posesiones, 40'/48'.
Supuestos: puentes ≥ 150 min en ambas competiciones, ≥ 3 por arista; independencia entre aristas.
- Código: `bbmodel/amortiguacion.py` (`resolver_grafo`, `contraccion_jerarquica`, `ajustar_mapeo`, `elegir_lambda`,
  `pesos_ipw`, `traducir`, `predecir_cambios`, `dejar_fuera_liga`). Integra en `dataset_normalizado.py` (`<m>_am`, `_am_lo/hi`).
- Config: `configs/normalization.yaml` (`variante: sin_mapeo`, escalones, `usar_amortiguado`).
- Tests: `tests/test_normalization.py` (12).
- Validación (`data/modelos/normalizacion_amortiguada/`): λ elegida = constante (=1); error LOLO 0,2272 (const.),
  0,2284 (exp.), 0,2509 (log.). Examen temporal (722 casos/métrica): MAE amortiguado/lineal 1,006/1,000 (empate),
  cobertura IC80 0,829 → 0,841. Niveles: ACB −0,23, Primera FEB −1,19, Segunda −2,32, Tercera −3,46 (IC90 0,85-0,98).
- Limitaciones: **mapeo no lineal y λ(d) implementados pero desactivados** (empeoraban); empeora pts/100, USG%, PER;
  Primera FEB con sólo 2 puentes directos con EL; IPW sólo corrige lo observable.

### 3.2 Roles y changepoints
**Estado:** ✅.
Regla de rol sobre minutos medios m (escala 40'): RESIDUAL m < 5; PROFUNDIDAD 5 ≤ m < 15; ROTACIÓN 15 ≤ m < 22;
solape 22 ≤ m < 25 → TITULAR si GS% ≥ 0,5 ∨ CLOSE% ≥ 0,5; TITULAR m ≥ 25; GO-TO-GUY si m ≥ 22 ∧ top-2 en GTI ∧
$GTI=\sum_k z_k\ge 4$ con $k\in\{USG,PIE,\%\text{noAst},USG_{clutch}\}$. Muestra < 5 partidos:
$p_k=(n_k+\alpha\pi_k)/(n+\alpha)$, α = 2. $H_{rol}=-\sum_k p_k\log_2 p_k$.
Changepoints: BOCPD gaussiano con media desconocida sobre (MIN%, USG%), riesgo $H=1/20$; cambio si
$P(\ell_{s+4}=5\mid x_{1:s+4})\ge 0{,}5$, tramo ≥ 4 partidos; cambio de entrenador abre tramo.
- Código: `bbfit/roles.py` (`clasificar`, `estado_partido`, `gti`, `procesar_liga_temporada`, `respaldo_caja`,
  `estructura_equipos`), `bbfit/cambios.py` (`bocpd`, `segmentar`, `covariables_cambio`), `bbfit/datos.py`.
- Config: `configs/roles.yaml`. Tests: `tests/test_roles.py` (11).
- Salidas: `data/modelos/roles/player_role_spells.csv.gz` (44.416), `player_role_season.csv.gz` (40.084),
  `team_role_structure.csv` (2.496), `partidos_jugador/<T>.csv.gz`.
- Validación (`roles/resumen.json`): top-10 anotadores GO-TO-GUY o TITULAR 92,8 %; < 5' → RESIDUAL 100 %; 1,11 tramos
  por jugador-equipo-temporada; casos conocidos (Jokić, Dončić, SGA GO-TO-GUY 6 temporadas).
- Limitaciones: USG% de tiro (sin pérdidas por partido); PIE/PER de temporada repetido en tramos; respaldo de caja en
  BBL 2020-23, LNB 2020-21, BCL 2020-21; FEB/G League sin cambios de entrenador intra-temporada; 28 % de registros probabilísticos.

### 3.3 Reemplazo de rol (formulación propia)
**Estado:** ✅ (β no distinguible de 0).
$\Delta TS=\beta_i\,\Delta USG$, $\beta_i^*=w_i\hat\beta_i+(1-w_i)\beta_g$, $w_i=\tau_g^2/(\tau_g^2+se_i^2)$; β por variable
instrumental (vacío de rol del partido). Libro de rol: $V_k=\sum_i m_i s_{ik}$,
$m's'-ms=(m'-m)s+m'(s'-s)$ (exacto), relleno $R_k=(I_k+DM_k+DR_k)/D_k$. Suma fija $\sum_i min_i\,USG_i=20\sum_i min_i$.
Asignación de minutos: Plackett-Luce $u_i=(nivel_i+w\cdot encaje_i)/T$ con mínimos por pos3.
- Código: `bbfit/reemplazo.py` (`uso_eficiencia`, `iv_grupo`, `agrupamiento_parcial`, `proyectar_a_rol`, `redistribuir`,
  `libro_roles`, `transiciones`, `calidad_companeros`, `tendencias_entrenador`, `asignar_minutos`).
- Config: `configs/reemplazo.yaml`. Tests: `tests/test_reemplazo.py` (12).
- Validación (F4): β IV todos −0,076 [−0,22; +0,08]; identidad del libro error máx. 1e-13; relleno clave mediano 0,96;
  persistencia GO-TO-GUY 0,68; compañeros +1 L̄ → +3,8 TS% [3,4; 4,2] (asociación).
- Limitaciones: exclusión del instrumento supuesta; asociaciones con ΔNet no causales; BSL/GBL ids de club inestables.

### 3.4 Entropía y volatilidad
**Estado:** ✅ (descriptivo; sin validación predictiva propia).
$H_{estilo}=-\sum_c p_c\log_2p_c$, $p\sim\text{Dir}(n+\alpha\pi_{liga})$, α = 5, 400 muestras (IC90).
Volatilidad: $y_{ig}=\mu_{i,eq}+\delta_{rival}+b_1\log min+b_2\bar\mu_{comp}+e_{ig}$, $z=e\sqrt{pos/30}$,
$\log s_i^2$ contraído por liga × pos3 (bayes empírico) → $\sigma_i$. Equipo: HHI, $2^H$, entropía normalizada de la red
de pases $H/\log_2(n(n-1))$.
- Código: `bbfit/entropia.py` (`entropia_dirichlet`, `acciones`, `entropia_rol`, `volatilidad`, `equipos`).
- Config: `configs/entropia.yaml`. Tests: `tests/test_entropia.py` (6).
- Resultados (F5): mediana H_estilo 2,80 bits; σ_i mediana 12,2 (21.160 registros); red de pases 0,75-0,81.
- Limitaciones: NBA sin faltas recibidas (usar `H_estilo_basico`); σ_i mezcla ruido no modelado; FEB 2022-24 sin zonas.

### 3.5 Estilos unificados (y VaDE legado)
**Estado:** ✅ taxonomía unificada (K = 6). VaDE: ✅ legado, pendiente de eliminar en otro encargo.
12 rasgos con la misma definición para jugador y equipo, $z=\Phi^{-1}(\text{percentil})$ dentro de liga-temporada;
mezcla gaussiana de covarianza completa ajustada sobre jugadores (≥ 300 min), equipos proyectados
($p(k\mid x)$). K = mayor K ≥ 5 con ARI bootstrap ≥ 0,60 y grupo ≥ 4 %. Nombres por método húngaro contra firmas.
- Código: `bbfit/estilos_unificados.py` (`rasgos_jugador`, `rasgos_equipo`, `seleccionar_k`, `elegir`, `nombrar`,
  `asignar`, `tramos_entrenador`, `correspondencia_vade`, `campos_atlas`).
- Config: `configs/styles.yaml`. Tests: `tests/test_estilos_unificados.py` (13).
- Validación (`estilos_unificados/estilos.json`): K = 6 (BIC mínimo en K = 4); ARI jugadores 0,654; equipos proyectados
  0,523; seguridad media 0,74-0,75; acuerdo plantilla→equipo 0,33 (azar 0,21); ARI con VaDE 0,031.
- Estilos válidos: Spacing, Circulación, Isolation, Old-School, Pistons, Pintura. **«Vértigo» y «Control» siguen en el
  YAML pero no salen** (K = 6).
- **Etiquetas VaDE que siguen existiendo** (para su eliminación posterior): `config/estilos.json` (E01-E06: Creación
  individual, Exterior y presión, Lejos del aro, Pausado y seguro, Pintura física, Circulación y triple), `bbestilo/*`,
  `data/modelos/estilos/`, campos `e`/`p`/`probs` del Atlas («estilo de mapa» y mapa 3D), `artifact/estilos/*.json` y
  `artifact/mapa-estilos.html` (obsoletos, 13 rasgos), `data/modelos/simulador/v2/validacion/vade/`, adaptación (covariable
  `arquetipo` usa los unificados). Las FEB no tienen estilo VaDE.
- Limitaciones: K en el filo (5-7); Old-School absorbe el 35 % de equipos; estilo de equipo inestable (cambia en 52 % de relevos).

### 3.6 Adaptación entre ligas y ADAPT%
**Estado:** ✅ (calibración fuera de muestra imperfecta).
$\hat y=T^{-1}(\mu_{d,t,pos}+\tau_{d,pos}\,z_d)$, $z_d=(\theta+\text{deriva}\cdot años-\delta_d)/(\lambda s_d)$.
Modelo jerárquico (Gibbs, 2 cadenas × 3.000, R̂ ≤ 1,006):
$\log(y/\hat y)_i=X_i\beta+u_{par}+v_{escalón}+\varepsilon_i$, $\varepsilon_i\sim\mathcal N(0,\sigma^2/w_i)$,
$w_i=\frac{min}{min+600}\cdot IPCW_i$. Curva $y(g)=\hat y\,(1+a_i+D e^{-g/\kappa})$ con grupo de control.
$ADAPT\%=100\,e^{\bar\eta_i}$ (principal `L_rel` = media geométrica de y/ŷ de 8 métricas).
Interfaz: `prior(origen, destino, grupo_nacionalidad, pos3, metrica)` con jerarquía celda → … → global (n ≥ 8),
`grupo_nacionalidad(...)` (9 grupos), `curva(g, δ, κ)`.
- Código: `bbfit/adaptacion.py` (`identificar_traspasos`, `esperado_en_destino`, `gibbs_jerarquico`, `ajustar_curvas`,
  `pesos_ipcw`, `tabla_priors`, `predecir_adapt`, `validar_temporal`, `validar_lolo`, `calibracion`, `rellenar_adapt_pct`).
- Config: `configs/adaptacion.yaml`. Tests: `tests/test_adaptacion.py` (10).
- Salidas: `data/modelos/adaptacion/adaptation_priors.csv` (9.696 filas), `adapt_historico.csv.gz` (5.040 traspasos), etc.
- Validación (`adaptacion/resumen.json`, F7): examen sin fuga cortes 2022-24: MAE log-cociente pts/100 0,177 → 0,169
  (−5,0 %), PER −2,1 %, L_rel −0,4 %; cobertura IC80 0,81-0,83; pendiente de calibración fuera de muestra ≈ 0,55.
  EE. UU. primer año europeo vs europeo que cambia de liga: L_rel −6,8 % [−9,7; −3,8]; IPCW baja Δ 1-2 puntos.
- Limitaciones: priors ajustados con todos los traspasos (fuga respecto al examen); κ mal identificado; 29 %
  nacionalidad desconocida; sin dato de canterano; cambio de rol endógeno.

### 3.7 Simulador de encaje v2 e Índice Fit
**Estado:** ✅ validado con examen temporal (TS% peor que baselines).
Por iteración Monte Carlo (1.000; 600 en navegador): nivel traducido con ruido común
$z=(\theta+\text{deriva}+sd\,\varepsilon_1-(\delta_d+sd_\delta\varepsilon_2))/s_d+\sqrt\psi\,\varepsilon_3$; adaptación (Δ × 0,55);
rol/minutos endógenos por Plackett-Luce con utilidad aprendida por verosimilitud y tendencias del entrenador de destino;
uso de suma fija y $TS'=TS+\beta\Delta USG$, $P100'=P100\frac{USG'}{USG}\frac{TS'}{TS}$; compañeros; estilo (Jensen-Shannon) y
complementariedad; ruido σ_i; ritmo. Capa de calibración de salida con cortes previos.
$Fit=b_0+\sum_f w_f\frac{x_f-\bar x_f}{sd_f}$, agrupado en nivel, rol, estilo, complementariedad, adaptación, riesgo;
pesos ridge sobre éxito $=0{,}5\,z(MIN\%)+0{,}5\,z(L)$ en la liga-temporada de destino.
- Código: `bbfit/simulador.py` (`simular`, `traducir`, `utilidad`, `redistribuir_uso`, `estilo_y_complementariedad`,
  `impacto_equipo`, `componentes`, `indice_fit`, `avisos`, `simular_cli`), `sim_insumos.py`, `validacion.py`
  (`backtest`, `baseline_a`, `baseline_b`, `ajustar_fit`, `dejar_fuera_liga`, `historico`), `sim_exportar.py`
  (`exportar`, `paridad`), `artifact/atlas/simulador_v2.js`.
- Config: `configs/simulation.yaml`. Tests: `tests/test_simulation.py` (13), `tests/js/paridad_simulador.js`, `tests/js/atlas_simulador.js`.
- Validación (`data/modelos/simulador/v2/validacion/AB_inicio/resumen.json`; cortes 2021-22 … 2024-25, 4.512 fichajes):
  MAE minutos 4,71 (Atlas anterior 5,84; simple 5,63); acierto rol 0,443; log-loss 1,235 (2,676; 1,257); MAE pts/100
  3,78 (3,76; 3,84); MAE TS% 6,02 (**peor**: 5,79; 5,80); cobertura 50/90 % pts/100 0,47/0,88, minutos 0,65/0,97.
  Fit fuera de muestra: Spearman 0,524 con el éxito (n = 4.707), pendiente 0,97. Pesos: nivel y rol dominan; estilo,
  complementariedad y adaptación ≈ 0. Ruta sin fuga en la normalización (`A_corte_inicio`): MAE minutos 4,65.
- Salidas: `simulador/v2/historico_<T>.csv.gz` (v2.0), `pesos.json`, `validacion/<ruta>/`; navegador `data/artifact/simulador/` (no versionado).
- Limitaciones: TS% empeora; intervalos de minutos anchos y de producción estrechos; saltos > 0,6 DT malos (MAE 6,5);
  impacto Net vía RAPM traducido (orientativo); «sinergias» del simulador = quintetos más probables + ΔNet, no sinergia
  de quintetos (ésa vive en la capa Quintetos); `encaje.exito` del YAML usa clave `produccion` pero el código lee
  `nivel` con valor por defecto 0,5 (umbral fuera de YAML).

## 4. Artefacto

- **Arquitectura:** página principal `artifact/mesa-multiliga.html` (título «CERNO Analytics»; shell con áreas →
  herramientas, `EB_AREAS`) que incrusta `atlas/index.html` y `quintetos/index.html` como marcos (postMessage para
  pestañas y exportaciones). Motor del simulador en el navegador: `atlas/simulador_v2.js` (paridad con Python).
- **Datos que consume:** `data/artifact/` (no versionado): `datos/<T>/{indice,regular,playoffs,total}.json`
  (`bbstats artifact`), `datos/normalizados/`, `datos/normalizacion/` (`bbmodel dataset-normalizado`,
  `mesa-normalizacion`), `datos/<T>/evaluacion_*.json` (`bbmodel evaluacion-ligas`), `atlas/estilos/*.json`
  (`bbestilo exportar`), `atlas/simulador/*.json` (`bbfit exportar-simulador`), `quintetos/datos/<T>/<liga>.json.gz`
  (`bbmodel mesa-quintetos`).
- **Publicación:** `python artifact/empaquetar.py <salida>` → lotes `lote<N>.json` (≤ 58 MB, ≤ 250 ficheros; JSON como
  `.gz.txt` base64) → herramienta Artifact con `url` de la página. URLs: Mesa/CERNO
  https://claude.ai/artifact/F4AxayFrM2d1D5JEoNiDoN · Atlas de Estilos independiente
  https://claude.ai/artifact/D2ULCYstYh4ykwSzExUPNU. Botón EJECUTAR → Routine `trig_01VA8u4RqAzGbKy4v4bFn1mw` (conector
  Claude Code Remote; `temporada=<T> ligas=…`). También `.github/workflows/ejecutar.yml` (workflow_dispatch).
- **Pantallas (áreas → herramientas):** Jugadores (Datos brutos/normalizados, Buscar parecidos) · Equipos (Evaluación,
  Rotación, Quintetos, Parejas y tríos, Conexiones, Impacto en pista, Liga) · Estilos (Mapa y comparador 3D, Química de
  estilos) · Planificación (Simular fichajes, Simular equipo completo) · Informe (informe A4 de jugador, PDF) ·
  Metodología, solo lectura (Evaluación de ligas, Normalización de ligas, Claves del estilo, Guía de conceptos).
- **Controles actuales:** selector de temporada (de `temporadas.json`) y fase; filtros por liga, búsqueda, nacionalidad,
  edad (rango), rangos por métrica y minutos mín./máx. en Datos; sliders «Minutos mínimos en la temporada» (100-2000,
  paso 50) en los mapas; mínimo de posesiones/asistencias/minutos en Quintetos. **Simulador: ya no hay selector ni
  campos de minutos** — rol y minutos son endógenos (v2); se eligen jugador(es), club, bajas y otros fichajes.
- **Validación:** paridad Python ↔ JS 6/6 casos (F8); `tests/js/atlas_simulador.js` con la carpeta servida.
- **Limitaciones:** depende de `data/artifact/` no versionado; lógica duplicada Python/JS; texto de «Simular equipo
  completo» en el shell aún dice «reparte los minutos».

## 5. Deuda técnica y siguientes pasos
Priorizados por valor/esfuerzo (A = alto valor, bajo esfuerzo primero).

| # | Tarea | Valor | Esfuerzo |
|---|---|---|---|
| 1 | Fusionar la rama viva en `main` (y cerrar PR #2, ya contenido) | alto | bajo |
| 2 | Retirar VaDE (§3.5) y unificar Atlas/mapa con los 6 estilos unificados (encargo previsto) | alto | medio |
| 3 | Completar migración de marca EBATE → CERNO (CSS/JS, «Nivel EBATE», PDF Creator) y textos obsoletos del shell | medio | bajo |
| 4 | Corregir el TS% del simulador (ajustes de compañeros/uso empeoran; probar desactivarlos) | alto | medio |
| 5 | Calibrar ADAPT% fuera de muestra (encoger 0,55 aprendido sin fuga) y priors con ≤ t | medio | medio |
| 6 | Mover el peso `encaje.exito.nivel` al YAML; eliminar literales `"2025-26"` (18 líneas según la auditoría del 21-10) | medio | bajo |
| 7 | Rellenar marcadores `[[F8: …]]` en `docs/glosario.md` y `docs/data_dictionary.md`; quitar referencias a la «Parte II» del artículo | medio | bajo |
| 8 | Relanzar `bbmodel validar`/`validar-b` y `mesa-normalizacion` con 15 ligas | medio | medio |
| 9 | Capa `clean` explícita: `games`, `game_player_box`, `pbp_events` con `possession_id` persistidos | alto | alto |
| 10 | Revisar cola del crosswalk (5.244 parejas) y nacionalidades (29 % desconocidas) | medio | alto |
| 11 | Entrenador por partido en FEB (actas) y G League | medio | alto |
| 12 | Versionar o reproducir `data/artifact/`; compactar `.git` (≈ 1,9 GB) | medio | medio |
| 13 | Ampliar FEB a 2020-22 (bajar `temporada_inicial`) y contrato de datos a todas las ligas | bajo | medio |

## 6. Discrepancias con lo recordado
| Recordado | Encontrado en el código |
|---|---|
| FEB desde 2020-21 | Primera FEB desde 2022-23; Segunda y Tercera desde 2023-24 (decisión del usuario, 22-10-2026) |
| Entrenador por partido en todas las ligas | FEB y G League: un entrenador por equipo y temporada |
| Contrato de datos general | Sólo se ejecuta sobre FEB (`--ligas` admite sólo feb1/2/3) |
| Mapeo no lineal por cuantiles y λ(d) en uso | Implementados y validados, pero la variante elegida es `sin_mapeo` y λ = constante = 1 |
| ROTACIÓN 15-25', TITULAR +22' | ROTACIÓN 15-22' (22-25' según desempate); TITULAR ≥ 25' o solape con GS%/CLOSE% ≥ 50 % |
| 8 estilos (incl. Vértigo y Control) | 6 estilos; Vértigo y Control sólo en el YAML, sin grupo en el modelo |
| Etiquetas VaDE | Siguen existiendo (lista en §3.5) |
| `H_estilo` como entropía de estilo | Es entropía del reparto de acciones del jugador, no del vector de estilos |
| Simulador con sinergias | Quintetos más probables + ΔNet (RAPM); sinergia de quintetos sólo en la capa Quintetos |
| Selector de minutos en el artefacto | Retirado del simulador en v2; sólo sliders de minutos mínimos como filtro |
| Marca «CERNO Intelligence» | El código dice «CERNO Analytics» (título); quedan restos «EBATE»; «CERNO Intelligence» no aparece |
| Artículo científico del proyecto | `docs/articulo/estilos_de_juego_baskonia.pdf` sólo cubre VaDE/contexto/química; Parte II (fases 1-8) retirada por decisión del usuario |
| Validación en MLflow | MLflow se registra en `experimentos/` (no versionado); métricas persistidas en `data/modelos/**/resumen.json` |
| `main` como rama de referencia | `main` está desfasado; la rama viva es `claude/basketball-stats-extractor-jpas93` |
| Capas raw → clean → features… | `clean` y `features` fusionados en `data/processed` (sin tabla por partido/evento) |

**Tests:** último resultado documentado: `python -m pytest -q` → 203 passed (F8, 29-10-2026). No se ha vuelto a
ejecutar en el encargo de memoria (el entorno no tenía las dependencias instaladas).

## 7. Tabla de componentes
| Componente | Estado |
|---|---|
| Extractor EuroLeague/EuroCup (básica + avanzada, histórico 2020-21) | ✅ |
| Extractores ACB, NBA, G League, LBA, BBL, LNB, BCL, FEC, BSL, GBL | ✅ (BSL con huecos) |
| Ingesta FEB (3 ligas, grupos, alias históricos) | ✅ (desde 2022-23/2023-24) |
| Matriz de cobertura PBP FEB | ✅ |
| Posesiones reales y quintetos/tramos | ✅ |
| Resolución de entidades (crosswalk) | 🟡 (cola de revisión sin revisar) |
| Entrenador por partido | 🟡 (FEB y G League por temporada) |
| Contrato de datos y tests | 🟡 (contrato sólo FEB; tests sintéticos completos) |
| Normalización EL = 0, por 100 pos., 40'/48' | ✅ |
| Encadenamiento con varianza, partial pooling, IPW | ✅ |
| Mapeo por cuantiles y λ(d) | 🟡 (implementado, desactivado por validación) |
| Roles (5) con desempate y GTI | ✅ |
| Changepoints de rol (BOCPD) | ✅ |
| Métricas MIN%, GS%, CLOSE%, Q4_share, % no asistido, GTI, H_rol | ✅ |
| Reemplazo de rol | ✅ |
| H_estilo, σ_i, entropía de equipo y red de pases | ✅ (sin validación predictiva) |
| Taxonomía unificada | ✅ (6 estilos, no 8) |
| Vértigo, Control | ❌ (no emergen) |
| Eliminación de VaDE | ❌ (otro encargo) |
| Adaptación jerárquica, curva, IPCW, `adaptation_priors`, ADAPT% | ✅ (calibración ≈ 0,55) |
| Simulador Monte Carlo v2 e Índice Fit | ✅ (TS% peor que baselines) |
| Artefacto publicado (Mesa CERNO + Atlas + Quintetos) | ✅ |
| Marca CERNO completa | 🟡 |
| Artículo técnico | 🟡 (sólo estilos VaDE) |
