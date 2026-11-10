# Liga ligau · Liga U (ACB)

Fecha de las decisiones: 09-11-2026 (antes de ajustar ningún modelo). Etiquetas: **DECISIÓN** (fijada de antemano),
**DATO** (medido), **HUECO** (lo que la fuente no da).

La Liga U es la competición sub-22 que organiza la ACB desde 2025-26, reservada a jugadores españoles U22 de los
equipos vinculados a los clubes de la Liga Endesa (Barça Atlètic, UCAM Murcia CAR…). Web oficial: ligau.com.

## 1. Decisiones (Fase 0)

| Decisión | Valor | Motivo |
|---|---|---|
| Código y nombre | `ligau` · «Liga U (ACB)» (corto: «Liga U») | **DECISIÓN** |
| Temporadas | 2025-26 (primera edición) y 2026-27 (en curso; entra en el botón) | **DECISIÓN del usuario** (09-11-2026); la liga no existía antes |
| Fuente | la misma que las FEB (adaptador `feb`): `baloncestoenvivo.feb.es` competición `g=74` (`nm=ligau`) + `intrafeb.feb.es/LiveStats.API` (KeyFacts con jugada a jugada y BoxScore) | **DECISIÓN del usuario**: «la misma app que para las Ligas FEB». ligau.com enlaza los mismos ids de partido FEB. Descartado: el backend propio de ligau.com (exigiría sacar una clave del código de su web) |
| Regular / playoffs / fuera | Reglas FEB (`fases_grupo`): «LIGA REGULAR GRUPO A/B» y «2ª FASE Grupo A/B» = regular; «PLAY-OUT» (cruces de acceso a los playoffs), «PLAY-OFFS 1/8 … Final» y «3º-4º» = playoffs; copas y permanencia fuera | **DECISIÓN**: el play-out es un cruce de acceso a las eliminatorias (como el play-in de la VTB o la EuroLeague) |
| Alcance | todos los equipos y partidos | liga pequeña |
| Minutos por partido | 40 | reglas FIBA |
| Escalón de contracción | escalón propio `ligau: [ligau]` (`configs/normalization.yaml` y `normalization_v32.yaml`) | **DECISIÓN**: liga de formación sub-22, no comparable a ningún escalón existente (cada FEB tiene también el suyo) |
| País de referencia (adaptación) | `ES` | jugadores españoles |
| Grupo de la v4.0 (F4 / IMPACTO) | `feb` (`bbequipo/equipo.py`); grupo de referencia IMPACTO `resto` (`configs/equipo_v40.yaml`) | **DECISIÓN**: competición nacional española por debajo de la ACB, como las FEB |
| Sistema de coordenadas de tiro | el de las FEB (KeyFacts `Position` = "x|y", % de la pista completa) | misma plataforma |
| Identidad | id de persona FEB (común a Primera, Segunda y Tercera FEB y Liga U): mismo id = misma persona en el crosswalk; Liga U concurrente con ACB y FEB (doble licencia) | `bbmodel/crosswalk.py` (`FEB`), `bbmodel/identidad.py` (`NACIONALES`) |
| Ids de equipo | inestables (inscripción FEB de cada temporada), como las FEB | `bbestilo/datos.py`, `configs/reemplazo.yaml` (`equipo_codigo`) |

Cambio técnico necesario (no de modelo): la página de equipo se pide como `/equipo/<id>` (antes `Equipo.aspx?i=<id>`,
que redirige a `http://`, no permitido en el entorno de la sesión). Afecta igual a las FEB y al botón.

## 2. Fuente (Fase 1)

`baloncestoenvivo.feb.es/resultados/ligau/74/<año>` (grupos y jornadas), `intrafeb.feb.es/LiveStats.API/api/v1/KeyFacts/<id>`
y `BoxScore/<id>` con el token anónimo que la página pública entrega a cualquier visitante (igual que las FEB), y la
plantilla de `baloncestoenvivo.feb.es/equipo/<id>` (fecha de nacimiento, nacionalidad, entrenador).
Grupos de 2025-26 en la web: LIGA REGULAR GRUPO "A"/"B", 2ª FASE Grupo "A"/"B", PLAY-OUT 2ºB-7ºA y 6ºA-3ºB,
PLAY-OFFS 1/8, 1/4, 1/2, 3º-4º y Final. 2026-27 (al 09-11-2026): LIGA REGULAR GRUPO "A"/"B".

## 3. Cobertura del histórico (Fase 2) [DATO]

Calendario de la web FEB = calendario oficial (ligau.com enlaza los mismos partidos). Jugada a jugada estructurado (con
ids, cambios y coordenadas) en todos los partidos.

| Temporada | Partidos regular (encontrados / oficiales) | Playoffs | Jugada a jugada | Quintetos válidos |
|---|---|---|---|---|
| 2025-26 | 196 / 196 (liga regular A 56 + B 42; 2ª fase A 56 + B 42) | 10 / 10 (play-out 2, 1/8 2, 1/4 2, 1/2 2, 3.º-4.º 1, final 1) | 206 / 206 | 205 / 206 (99,0 %) |
| 2026-27 (al 09-11-2026) | 42 / 42 jugados (84 en el calendario de la liga regular, jornadas 1-7 de 14) | — | 42 / 42 | 41 / 42 (95,2 % de partidos con cambios validados) |

* Jugadores: 261 (2025-26) y 207 (2026-27); 16 y 14 equipos. Nombre completo y fecha de nacimiento en el 95 % (plantilla
  de la web); el 5 % restante sólo con inicial en el acta (**HUECO**).
* Entrenadores: 2025-26 59 % de los partidos (la página de equipo de la temporada pasada no siempre conserva el
  entrenador; **HUECO**), 2026-27 100 %.
* Posesiones: el recuento del jugada a jugada coincide con la estimación del boxscore (diferencia media −1,2 por partido).

## 4. Resultados (Fase 6) [DATO]

* **Nivel A** (PER, DT de la EuroLeague, 2025-26): **−2,97 ± 0,10**, 83 puentes → **no provisional** (regla: < 50
  puentes o error > 0,25). Entre la Segunda FEB (−1,81) y la Tercera FEB (−3,15). pts/100 −2,77; TS% −2,58.
* **Identidad:** 214 de las 347 personas de la Liga U tienen otra liga (Tercera FEB 183, ACB 57, Segunda FEB 38,
  BCL 18, Primera FEB 15, FEC 14, EuroCup 12, EuroLeague 5…).
* **Estilos:** con la Liga U en la población la regla de selección de K daría 7 estilos; se fija K = 6 (taxonomía
  vigente, `configs/styles.yaml → mezcla.k_fijo`). El 97 % de los equipos conserva su estilo principal (ARI 0,94).
  Liga U 2025-26/26-27: old school 10, spacing 8, circulación 7, pistons 2, pintura 2.
* **Simulador:** auditorías v3.2 y v3.3 sin fallos; paridad Python/navegador dentro de tolerancia. Examen (destino
  2025-26): 30 fichajes hacia la Liga U (17 desde la Tercera FEB, 9 desde la Segunda): MAE de minutos 5,5 (resto
  5,0) y de pts/100 6,1 (resto 4,2). En el examen sin fuga (corte ≤ 2024-25) la Liga U no existe aún: sin
  predicción de producción para ella (correcto). El resto del examen no cambia (MAE minutos 4,99; pts/100 4,30).
* **Cambio en las demás ligas:** niveles A, |Δ| PER ≤ 0,11 (FEC −0,11; ACB −0,01). Normalizado v3.2 de 2025-26: |Δ|
  medio 0,51 PER (DT 7,8), 0,43 pts/100; por liga, ACB −0,86 PER de media, Tercera FEB +0,84, Segunda +0,60,
  Primera +0,37; las demás, |media| < 0,3.
* **Capas v4.2:** parámetros D3 prácticamente iguales (p. ej. tríos τ² 19,384 → 19,385); Net v4.2 de tríos y
  parejas de 2025-26 de las demás ligas: diferencia máxima 0,0006 pts/100.
* **Botón:** `bbactualiza --sin-descarga --forzar` → `ok`; la Liga U aparece en `data/artifact/2026-27/indice.json`.
* **Incidencias:** reinicio del contenedor durante la normalización v3.2 (se reanudó por pasos) y falta de memoria
  en `bbequipo rapm-producto` (pico ≈ 14 GB de 15): se añadió un fichero de intercambio de 12 GB (`/swapfile`).

## 5. Publicación (Fase 7) [DATO]

Publicación completa (10-11-2026): Jugadores versión 36 (3 lotes), Equipos versión 12 (4 lotes), Metodología
versión 11 (3 lotes). Quintetos y tríos/parejas v4.2 de la Liga U (2025-26 y 2026-27) en Equipos y Metodología.
Antes se incorporaron al repositorio las versiones publicadas de `atlas/informe_v3.js` e `informe_equipo.js`.
