# Lectura de fichaje (informe A4 del Atlas) · v3.1 → v3.3 · 29-10-2026

Publicada en el artifact vigente (versión 1793286109-fca7). Fichero: `artifact/atlas/informe_v3.js`; el resto del
artifact, el motor (`simulador_v2.js`) y los datos no cambian. Decisiones del CEO del 29-10-2026, cambios definitivos.

## Qué cambia
### v3.1 · contenido y composición
- 01: «Basketball judgment, model rigor» → «Este análisis no sustituye en ningún caso el scouting en pista y humano,
  solo lo complementa con rigor matemático y científico.»
- Títulos por facetas desde 02: Trayectoria, roles y perfil de juego · Veredicto, adaptación y rol · Anotación, tiro y
  creación · Defensa, rebote y confianza del entrenador · Carencias del equipo y encaje de estilo · Sinergias de pareja
  con la plantilla · Impacto en la plantilla y en sus compañeros · Términos, escalas y ligas. La conclusión pasa a la
  entradilla (decisión del CEO por encima de la regla de marca «titulares que concluyen»).
- 02: panel Ink central «Su perfil en una mirada».
- 03: «Por qué lo proponemos» primero; curva ADAPT% con eje ajustado, pérdida sombreada y cifras; «Qué nos haría
  cambiar de opinión» en la columna izquierda.
- 04/05: entradilla con datos y cifras clave (valor traducido, percentil y rango del percentil al 90 %). 04: fuera
  «Qué produce hoy por cada 25 minutos»; «Su ataque con el rol asignado» con 9 métricas; mapa de tiro mayor.
- 06 (tres páginas, sin «Conexiones: con quién jugaría»): carencias, estilos sin/con/referencia, KPIs del equipo y sus
  números en esta plantilla · sinergia de pareja con cada compañero y quinteto principal con él (RAPM-EL + química) ·
  minutos sin/con por jugador y por puesto, lugar en la plantilla y cambio previsto en ORtg/DRtg/TS%/RAPM de los
  compañeros. Plantilla del simulador emparejada con el Atlas por `liga|temporada|pid`; funciones de «Simular equipo
  completo» (`sinJ`, `partes`, `quinteto`, `quimicaPlantilla`, `devDestino`, `proyectar`).
- Clasificaciones en columna; percentil con una sola forma («percentil N»; en bloques, media de percentiles).

### v3.2 · títulos y plantilla elegida
- Títulos de sección en Index (#F2CC2F) sobre banda Ink: contraste 11,6:1.
- Controles del informe: «Compañeros en el club de destino». Casillas con la plantilla del simulador para quitar bajas
  y buscador para añadir jugadores (fichas del simulador, temporada más reciente). Se guarda por club y temporada de
  destino en `st.inf.plant["club:temporada"] = { fuera: [persona], extra: [id] }`. La simulación (`bajas`, `extras`
  del motor v2.1), «Si cambias su rol» y la sección 06 usan esa plantilla; lugar en la plantilla, nivel medio por
  minutos y química se calculan con esos compañeros; el informe rotula la plantilla considerada.

### v3.3 · adaptación
- El motor modela la forma partido a partido como f(g) = (1 + D·φ(g)) / (1 + D·w̄), φ(g) = exp(−g/κ); el signo de D
  (prior del cambio de liga) decide si el jugador arranca por debajo y recupera (D < 0) o arranca arriba y baja
  (D > 0). El texto miraba solo el ADAPT% de temporada y decía siempre «perdería un poco al principio»; ahora describe
  la forma de la curva (primer partido frente a final). «Mitad del ajuste» → «mitad del cambio».

## Verificación
- `artifact/herramientas/prueba_informe.py` sobre una copia local de la versión publicada: Parker → Baskonia (rol
  Rotación, con nota y con plantilla modificada), Parker sin destino y Hezonja → Baskonia. Ninguna hoja se desborda;
  PDF generado por la ruta del botón «Descargar PDF» (11 páginas con destino, 9 sin él).
- Controles del selector revisados a 1440 px (claro) y 390 px (oscuro), sin scroll horizontal; sin errores de consola
  propios (solo el CDN de Plotly, bloqueado en el entorno de prueba).
- brand_lint del HTML imprimible: sin bloqueantes nuevos (6 falsos positivos por `!important`, ya existentes).

## Hallazgo a validar (HIPÓTESIS)
En todos los cambios de liga probados hacia la Euroliga (ACB, LNB, GBL, LBA, BBL, BSL, G League, NBA) la curva arranca
por encima del nivel de temporada y baja: D_forma_media > 0 en esos priors. Puede ser un efecto real de llegada o un
artefacto de selección (siguen teniendo minutos los que empiezan bien). Pendiente de contrastar con los datos de la
fase 7 (`adaptacion/`) antes de usarlo como argumento en una lectura.

## Pendientes
- Química por pareja, quinteto y cambios en los compañeros sin rango: el modelo no lo publica.
- Fusionar `artifact-v2-candidata` en `main` (la v2 está publicada pero `main` sigue en la versión anterior).
