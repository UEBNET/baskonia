# Actualización de la temporada 2026-27 desde el artifact (botón + skill)

Botón **«Actualizar 2026-27»** en la cabecera del artifact Cerno Analytics
(https://claude.ai/artifact/F4AxayFrM2d1D5JEoNiDoN) → Routine **«Actualizar 2026-27 · Cerno»** → sesión de Claude Code
que sigue la skill `.claude/skills/actualizar-temporada` → `python -m bbactualiza` (paquete `bbactualiza/`) → Git
(rama `claude/gallant-pascal-49bx9o`) y republicación del artifact con sólo los ficheros que cambian.

```
artifact (navegador)            Routine (sesión nueva)                         repositorio / artifact
───────────────────            ────────────────────────                       ─────────────────────
[Actualizar 2026-27] ─mcp──▶  fire_trigger ─▶ clon ligero + pip ─▶ python -m bbactualiza ─▶ git push (datos 2026-27)
   estado ◀──── get_trigger                                        └─▶ publicacion/lote0.json ─▶ Artifact publish (parche)
```

## 1. Principios

1. **Sólo la temporada en curso.** El histórico 2020-21 … 2025-26 es estático: ningún fichero suyo se reescribe con
   contenido distinto. Los ficheros que guardan todas las temporadas se empalman (`bbactualiza.capas.empalmar`): las
   filas de 2026-27 se sustituyen en su sitio y el resto de líneas se reescribe con su mismo texto (prueba en
   `tests/test_bbactualiza.py`).
2. **Modelos congelados.** El botón aplica los parámetros ya ajustados; no reajusta ningún modelo. Lo que no se puede
   aplicar sin reajustar se hace en la recalibración mensual (§4).
3. **Si no hay partidos nuevos no se hace nada más.** Tras la descarga se calcula la huella de los datos procesados
   de 2026-27; si coincide con la de la última actualización, el posproceso y la publicación se saltan.
4. **Si un paso falla no se publica.** El informe dice qué paso y por qué; los datos publicados siguen siendo los
   anteriores.

## 2. Qué hace cada paso

| Paso | Código | Modelo congelado que aplica | Escribe (sólo 2026-27) |
|---|---|---|---|
| descarga | `.claude/skills/actualizar-temporada/actualizar_delta.py` | — (descarga delta: cada liga pide sólo lo que falta; respaldo con el último bruto) | `data/raw/*/2026-27`, `data/processed/2026-27` (tablas, quintetos, entrenadores) |
| pista | `capas.pista`, `capas.interacciones`, `capas.nacionalidades` | calibración de zonas por liga-temporada (la del resto de temporadas se conserva) | `pista/2026-27.csv`, `interacciones/efectos_2026-27`, filas de `nacionalidades.csv` |
| normalizacion | `normalizacion.py` | **A**: σ², τ² y enlace (m, s, ψ…) de `algoritmo_A/parametros.json`; el entorno μ de cada liga-temporada-posición se recentra con los partidos nuevos (media ponderada con los σ², τ² guardados). **Amortiguada**: δ y λ de `league_offsets.csv` (variante `sin_mapeo`). **B**: se conservan sus filas de jugadores sin minutos nuevos. **v3.2**: CVAE congelada de cada jugador (última recalibración) + v2 al día, mezcladas con los pesos por métrica del examen (`examen_v32.json`) y las mismas salvaguardas que `bbnorm3.combinacion`; jugador sin valor CVAE → sólo v2 (`fuente_v3 = v2_incremental`). **Identidades**: `persona_id` estable (mapa a los ids de los ficheros congelados) | traducciones A/B/amortiguada, `normalizado/2026-27.csv`, `v3_2/normalizado/2026-27.csv.gz` |
| contexto | `capas.contexto` | escala de nivel fija 2020-26 (sin la regresión de sensibilidad, que es un ajuste) + 2.ª pasada del dataset normalizado | `contexto/2026-27.csv`, filas de `por_jugador_liga.csv` |
| roles | `capas.roles` | reglas por minutos y BOCPD por jugador (`configs/roles.yaml`) | filas de `roles/*`, `partidos_jugador/2026-27` |
| entropia | `bbfit.entropia` | categorías y priors de `configs/entropia.yaml` | `entropia/` |
| estilos | `bbfit.estilos_unificados --reusar-k` | mezcla ajustada sólo con 2020-26 y semilla fija (= la guardada); 2026-27 se asigna | `estilos_unificados/` |
| simulador | `bbfit.sim_insumos.dataset_simulador` + `bbfit.sim_exportar.exportar` (v3.3) | pesos, GBM de minutos, B9 y adaptación guardados | `data/artifact/simulador/` |
| artifact | `artefacto.py` | — | tablas de datos, nacionalidades, evaluación de ligas, normalizados v3.2, Atlas (estilos, lectura de fichaje 2026-27), quintetos y estilos unificados |
| publicacion | `artefacto.empaquetar` | — | `publicacion/lote0.json` (parche: sólo rutas que dependen de 2026-27) y `datos/actualizacion.json` |

**Validación del atajo del A.** Con el μ guardado, aplicado a 2025-26, reproduce las traducciones del A versionadas:
error medio 0,0001 en pts/100 (máximo 0,08, en filas de pocos minutos) cuando la posición asignada coincide. Las
diferencias en la posición vienen de que `posicion.consolidar_por_persona` usa todas las temporadas de cada persona.

## 3. Tiempos

Ejecución real del 8-11-2026 (dos semanas de partidos, 4 núcleos):

TIEMPOS_PLACEHOLDER

## 4. Recalibración mensual

`python -m bbactualiza.recalibrar` (tarea programada mensual «Recalibración mensual 2026-27 · Cerno»):

1. `cvae` — reentrena las 20 redes CVAE de la v3.2 (4 procesos, ≈ 40 min) y recalcula la combinación: los jugadores
   nuevos reciben valor CVAE y los demás lo ponen al día.
2. `v40` — perfiles 2026-27, RAPM de producto, capa 4, anclas y tablas del Atlas v4.0, y `v40/equipos_2026-27.json`.
3. `boton` — `python -m bbactualiza --sin-descarga --forzar` desde el contexto hasta la publicación.

Tras cada paso, `restaurar_historico` devuelve a su versión de Git todo fichero versionado de `data/modelos/` que haya
cambiado y no sea de la temporada en curso (ni propio del paso), así que el histórico tampoco cambia aquí. Exige el
árbol de `data/modelos/` limpio al empezar.

## 5. Límites conocidos

* **Modelo de equipo v4.0** (`atlas/v40/`, `v40/`): necesita el RAPM completo y la latente de la CVAE, que no están en
  Git (`experimentos/`); sólo se pone al día en la recalibración. Entretanto el navegador usa, para los jugadores
  nuevos, el prior de su perfil o el nivel de recién llegado de su liga.
* **CVAE de 2026-27**: la de la última recalibración (los jugadores nuevos tienen sólo la v2 hasta la siguiente).
* **Fuentes**: la descarga depende de las webs de cada liga. Una liga que falla se reprocesa con su último bruto
  (`ok_bruto_anterior`) y queda anotada. NCAA 2026-27 está marcada `sin_datos` en `config/sources.json` hasta que se
  quite la marca.
* **Lectura de la página**: la Routine debe leer entera la página publicada antes de republicarla (≈ 440 KB). Separar
  estilos y scripts en ficheros aparte la reduciría a ≈ 70 KB por pulsación (pendiente de decidir, afecta a cómo
  editan la página otras sesiones).
* `quintetos/datos/indice.json` y los estilos unificados de Equipos y quintetos se regeneran enteros (contienen todas
  las temporadas); su contenido histórico es el mismo.
