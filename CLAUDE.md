# CLAUDE.md — Baskonia Analytics (CERNO)

## 1. Propósito
Plataforma de análisis multiliga para dirección deportiva: extrae y normaliza estadística de 15 competiciones,
mide roles, estilos, entropía y adaptación entre ligas, y simula el encaje de un fichaje en un club (Índice Fit).
**Filosofía:** el baloncesto es colectivo; el encaje en un contexto (rol, estilo, compañeros, liga) pesa más que un
ranking individual. Todo número va con su incertidumbre. Marca visible en el artefacto: «CERNO Analytics» (antes EBATE).

## 2. Stack y comandos
Python 3.12, pandas/numpy/scipy/scikit-learn, PyYAML, MLflow (skinny, almacén local), PyTorch CPU sólo para VaDE.
Datos en ficheros (JSON gzip, CSV/CSV.gz, JSON); sin base de datos. Front: HTML/JS autocontenido (claude.ai Artifact).
**Rama de trabajo real: `claude/basketball-stats-extractor-jpas93`** (`main` está desfasado, sólo hasta PR #1).

```bash
pip install -r requirements.txt            # + requirements-dev.txt (pytest); requirements-estilos.txt (torch, VaDE)
python ejecutar.py [ligas…] [--temporada 2026-27]       # extracción incremental de UNA temporada (red)
python -m bbstats historico [--ligas …] [--desde T --hasta T] [--sin-descarga]   # carga histórica / reproceso
python -m bbstats reprocesar --temporada T  # recalcula desde brutos, sin red
python -m bbstats quintetos | entrenadores | feb | contrato --ligas feb1 feb2 feb3 | artifact [--temporada T]
python -m bbmodel crosswalk                 # identidad entre ligas → data/processed/player_id_crosswalk.csv
# Recálculo de features/modelos (orden obligatorio):
python -m bbmodel pista && python -m bbmodel ajustar && python -m bbmodel ajustar-b
python -m bbmodel amortiguar                # normalización amortiguada (--validar --variante V | --elegir)
python -m bbmodel dataset-normalizado && python -m bbmodel contexto && python -m bbmodel dataset-normalizado
python -m bbmodel interacciones && python -m bbmodel escalas
python -m bbfit roles && python -m bbfit reemplazo && python -m bbfit entropia
python -m bbfit estilos [--reusar-k] && python -m bbfit adaptacion [--rehacer]
# Simulador (fase 8):
python -m bbfit simular --jugador "Corbalan" --club "Baskonia" --liga acb
python -m bbfit pesos-simulador && python -m bbfit historico && python -m bbfit exportar-simulador
python -m bbfit backtest --fuente AB --escenario inicio        # examen temporal (≈1 h)
# Tests:
python -m pytest -q                          # suite sintética completa
node tests/js/paridad_simulador.js           # paridad Python ↔ JS del simulador
# Artefacto:
python -m bbstats artifact && python -m bbestilo exportar && python -m bbmodel mesa-quintetos
python artifact/empaquetar.py <salida>       # lotes .gz.txt → publicar con la herramienta Artifact (misma URL)
```
MLflow: `experimentos/mlruns` (NO versionado; `MLFLOW_ALLOW_FILE_STORE=true` lo fija `bbfit.registro`).

## 3. Mapa del repositorio
- `bbstats/` extracción por capas: `adapters/` (1 por fuente; `feb.py`, `fiba_web.py`, `fiba_livestats.py`…),
  `pipeline.py`, `metrics.py` (fórmulas únicas), `schema.py` (480 columnas), `raw_store.py`, `http.py`,
  `lineups/` (jugada a jugada → tramos, quintetos, RAPM, `possessions.py`), `entrenadores.py`, `contrato.py`.
- `bbmodel/` normalización entre ligas: algoritmo A (`modelo.py`, `escalas.py`, `suerte.py`), B (`algoritmo_b.py`),
  `amortiguacion.py` (capa amortiguada), `crosswalk.py`/`identidad.py`, `contexto.py`, `pista.py`, `zonas.py`.
- `bbestilo/` estilos VaDE (legado, 12 ligas), mapa 3D, química, artículo PDF, exportación del Atlas.
- `bbfit/` encaje v2: `roles.py`+`cambios.py` (BOCPD), `reemplazo.py`, `entropia.py`, `estilos_unificados.py`,
  `adaptacion.py`, `simulador.py`, `sim_insumos.py`, `validacion.py`, `sim_exportar.py`, `registro.py` (MLflow).
- `configs/*.yaml` umbrales/hiperparámetros de `bbfit` y amortiguación · `config/*.json` fuentes, alias, estilos VaDE.
- `data/raw/` brutos fechados (nunca se sobrescriben) · `data/processed/<T>/` CSV por liga, quintetos, entrenadores,
  FEB · `data/modelos/<capa>/` salidas y validaciones · `data/artifact/` (NO versionado, se regenera).
- `artifact/` páginas: `mesa-multiliga.html` (shell CERNO), `atlas/` (+`simulador_v2.js`), `quintetos/`, `empaquetar.py`.
- `docs/` `checkpoints/F1-F8.md` (informe por fase), `glosario.md`, `data_dictionary.md`, `PROJECT_STATE.md`.
- `tests/` pytest sintético (`synth.py`, `tests/data/pbp`) + `tests/js/`.

## 4. Cobertura
- 12 ligas 2020-21 → 2026-27 (en curso, datos a oct-2026): `euroleague`, `eurocup`, `acb`, `nba`, `gleague`, `lba`,
  `bbl`, `lnb`, `bcl`, `fec`, `bsl`, `gbl`. Fases `regular`/`playoffs`/`total`.
- FEB: `feb1` Primera FEB (LEB Oro) 2022-23 →; `feb2` Segunda FEB (LEB Plata) y `feb3` Tercera FEB (Liga EBA)
  2023-24 →. Grupo = atributo del partido. Antes de esas temporadas: fuera de alcance (decisión del usuario).
- Huecos: NBA/G League 2026-27 sin datos; BSL 2021-22 → 2024-25 sin fuente; BBL 2020-23 y BCL 2020-21 (parcial) sin
  cambios en el jugada a jugada; LNB 2020-21 sin jugada a jugada; FEB 2022-24 jugada a jugada en texto (sin coordenadas).

## 5. Glosario cerrado
**Roles** (`configs/roles.yaml`; minutos por partido sobre 40', MIN% = min/40; NBA/G League proporcional a 48'):
| Rol | Regla |
|---|---|
| RESIDUAL | < 5' |
| PROFUNDIDAD | 5-15' |
| ROTACIÓN | 15-22'; y 22-25' si GS% < 50 % y CLOSE% < 50 % |
| TITULAR | ≥ 25'; o 22-25' con GS% ≥ 50 % o CLOSE% ≥ 50 % (desempate del solape) |
| GO-TO-GUY | ≥ 22' + top-2 del equipo en GTI + GTI ≥ 4,0 (z medio ≥ 1) |
< 5 partidos: sin etiqueta dura, sólo vector Dirichlet (α = 2). Tramos por BOCPD (H = 1/20, confirmación 4 partidos);
un cambio de entrenador abre tramo (interinos < 3 partidos no). Grano: liga × temporada × club × entrenador × tramo.

**Estilos unificados válidos (6, K por BIC + estabilidad):** Spacing · Circulación · Isolation · Old-School · Pistons ·
Pintura. «Vértigo» y «Control» están en `configs/styles.yaml` pero **no** existen en el modelo (K = 6). Etiqueta:
«X puro» si p ≥ 0,80; «X · Y» si p₂ ≥ 0,25. Los 6 estilos VaDE (E01-E06) son otra taxonomía (legado, «estilo de mapa»).

**Métricas propias:**
- `MIN%` minutos / duración real del partido (con prórrogas). `GS%` fracción de partidos como titular.
- `CLOSE%` fracción de los minutos de cierre (últimos 5' de cada periodo ≥ 4.º, |margen| ≤ 5) que juega. `Q4_share`
  fracción del 4.º cuarto en pista.
- `% no asistido` canastas propias sin asistencia / canastas (contraído a la liga, k = 20).
- `GTI` z(USG%) + z(PIE) + z(% no asistido) + z(USG% clutch), z dentro de liga-temporada (MIN% ≥ 25 %).
- `H_rol` entropía (bits) del reparto de estados de rol por partido; `H_rol_post` versión Dirichlet con IC.
- `H_estilo` entropía (bits) del reparto de acciones (zonas de tiro, TL, AST, TOV, faltas recibidas, OREB),
  Dirichlet con prior de liga (α = 5); comparable entre ligas: `H_estilo_basico`.
- `σ_i` volatilidad intrínseca: DT partido a partido de 100·(PTS+AST)/posesiones, sin rival/minutos/compañeros,
  a 30 posesiones, contraída por liga × pos3.
- `ADAPT%` 100 · rendimiento esperado tras cambiar de liga / ŷ de la normalización (100 = lo esperado); principal = `L_rel`.
- **Índice Fit** suma aditiva de 6 componentes (nivel, rol, estilo, complementariedad, adaptación, riesgo), pesos por
  ridge sobre el éxito real de fichajes previos (0,5·z(MIN%) + 0,5·z(L) en destino); unidades = DT de ese éxito.
- `L` índice de nivel en la vara EuroLeague (DT de capacidad EuroLeague; EuroLeague = 0). Escala ±100 = 100·tanh(z/2).

## 6. Reglas no negociables
1. Capas `raw → clean → features → models → simulation → outputs`; nunca escribir en una capa anterior. Los brutos
   no se sobrescriben. (Hoy `clean` y `features` están fusionados en `data/processed`: no empeorarlo.)
2. Sin fuga temporal: validar con cortes t → t+1 entrenando sólo con ≤ t; declarar cualquier pieza ajustada con todo.
3. Incertidumbre siempre explícita (intervalos, sd, banderas de muestra pequeña); NaN nunca se imputa con 0.
4. Umbrales e hiperparámetros sólo en YAML (`configs/`); el código no fija ninguno.
5. No citar ni nombrar la fuente conceptual externa del reemplazo de rol: es formulación propia del proyecto.
6. No inventar resultados: sólo cifras que existan en `data/modelos/**/resumen.json`, `validacion*` o `docs/checkpoints`.
7. Euroleague = 0 como referencia de nivel; comparar por 100 posesiones y con duración 40'/48'.
8. No pushear a ramas no designadas; commits con mensajes claros.

## 7. Detalle
Para detalle de un componente, lee la sección correspondiente de `docs/PROJECT_STATE.md`; no leas el documento
entero si no hace falta. Informes con cifras y comandos de verificación: `docs/checkpoints/F<n>.md`.

## 8. Mantenimiento
Al cerrar cada encargo: actualizar **siempre** `docs/PROJECT_STATE.md` (historial, estado, deuda) y `CLAUDE.md`
**sólo** si cambia algo estructural (comandos, mapa, cobertura, glosario, reglas), sin pasar de ~150 líneas.
