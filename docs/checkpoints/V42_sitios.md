# Checkpoint V42_sitios — Kerno Analytics en tres artifacts (Jugadores · Equipos · Metodología)

Fecha: 09-11-2026. Decisión del CEO: el artifact único llegó al límite de 256 MiB por versión (267 MB publicados en la
versión 1794228781-5e60, más los tríos y parejas v4.2 de 2020-21 a 2024-25). El producto se separa en tres artifacts por
sección, **con los mismos ficheros fuente** y un interruptor de sitio (`sitio.json`).

## 1. Qué va en cada sitio

| Sitio | Artifact | Vistas propias | Portada |
|---|---|---|---|
| **Jugadores** | el actual (`https://claude.ai/artifact/A7rufkL84rvRFcUBFBxFbC`, conserva la URL) | Tu equipo hoy · 02 Mercado · 03 Evaluación · 04 Decisión · 05 Modelo de equipo | Tu equipo hoy |
| **Equipos** | nuevo | Tu equipo hoy · 01 Diagnóstico (Evaluación, Rotación, Quintetos, Parejas y tríos, Conexiones, Impacto en pista, La liga, Informe de equipo) | Tu equipo hoy |
| **Metodología** | nuevo | Método (Cómo leer los datos, Evaluación de ligas, Normalización de ligas, Claves del estilo, Guía de conceptos) | Cómo leer los datos |

«Tu equipo hoy» está en Jugadores y en Equipos: no añade datos a Equipos (usa la temporada normalizada, el simulador y
la v4.0, que Equipos ya publica para el portal y el Informe de equipo). En Metodología aparece como enlace a Jugadores.

## 2. Cómo funciona el interruptor

- Cada artifact publica `sitio.json` = `{"sitio": "jugadores"|"equipos"|"metodologia", "urls": {"jugadores": "…", "equipos": "…", "metodologia": "…"}}`.
  Las fuentes están en `artifact/kerno/sitios/sitio_<sitio>.json` (se publican con la ruta `sitio.json`). Sin `sitio.json`, la
  página se comporta como Jugadores.
- `index.html` lo lee antes de pintar el raíl (`cargarSitio`). Cada sección de `NAV` lleva `en: [sitios]`. El raíl muestra
  arriba «Kerno Analytics · <sitio>», después las secciones propias y, bajo «En otros sitios de Kerno Analytics», las de
  los otros dos: cada herramienta es un enlace normal (`target="_blank"`) a `<url del sitio>#<vista>&club=<liga>|<id>&temp=<t>`
  con la etiqueta «en Equipos» y la flecha dibujada `.k-arrow` (sin glifos de flecha en el texto). Si la URL de ese sitio está
  vacía, la herramienta sale atenuada, sin enlace, y el pie del raíl lo explica.
- Cabecera: la segunda línea del producto dice «KERNO ANALYTICS · <SITIO>»; el título de la pestaña, «Kerno Analytics · <Sitio>»
  (o «<herramienta> · Kerno Analytics · <Sitio>»). El botón Inicio y el logotipo van a la portada del sitio.
- Los saltos desde dentro de una vista a una herramienta de otro sitio (p. ej. «Revisar la rotación» en Tu equipo hoy,
  «Impacto en pista» en la ficha, un jugador buscado desde Equipos, «Ver quintetos y conexiones» en Datos de jugadores) abren
  ese artifact en una pestaña nueva con el club, la temporada, la ficha (`f=`) y los parámetros de la herramienta (`q.t`, `q.l`,
  `q.e`, `q.j`…). El sitio de destino los aplica al arrancar. No se ha añadido ni quitado ningún control dentro de las vistas.
- `clasico.html` recibe `?sitio=` del portal: no carga `datos/<t>/<fase>.json` ni el rol del simulador fuera de Jugadores,
  no restaura al arrancar una herramienta de otro sitio y, en Jugadores, «Ver quintetos y conexiones» pide al portal abrir
  Equipos (`cernoFuera`). Su barra propia (solo visible fuera del portal) oculta las herramientas de otro sitio. Sin
  `?sitio=`, todo igual que antes.
- Cada artifact tiene su propio almacenamiento local: lista corta, ajustes y contexto se guardan por sitio (el contexto viaja
  en los enlaces).

## 3. Manifiestos

`artifact/kerno/sitios/<sitio>.json` = `{sitio, pagina, sitio_json, n_ficheros, mb_estimados, ficheros, notas}` con las rutas
publicadas exactas. Tamaños: los de la versión publicada 1794228781-5e60 y, para `quintetos/datos_v42/`, los del árbol local
(incluye las temporadas 2020-21 a 2024-25 que aún no estaban publicadas).

| Sitio | Ficheros | MB | MiB | Lo grande |
|---|---|---|---|---|
| Jugadores | 127 | 163,9 | 156,3 | datos/<t>/ 70,2 · normalizados 34,7 · atlas/informe 29,3 · atlas/estilos 13,3 · simulador 5,9 |
| Equipos | 362 | 169,7 | 161,9 | quintetos/datos/<t> 75,6 · normalizados 34,7 · atlas/informe 29,3 · atlas/estilos 10,5 · simulador 5,9 · datos_v42 3,4 |
| Metodología | 350 | 167,3 | 159,6 | quintetos/datos/<t> 75,2 · normalizados 34,7 · evaluaciones 14,2 · normalizacion 10,5 · atlas/estilos 10,5 · simulador 5,9 |

Los tres por debajo de 230 MB. Comunes a los tres: `index.html`, `sitio.json`, `kerno/*`, `clasico.html`,
`datos/normalizados/*` y `atlas/v42/historial/*` (el portal arranca con la temporada normalizada para el selector de club),
`datos/actualizacion.json`, `quintetos/datos/{indice.json,equipos.gz.txt}`, `quintetos/estilos_unificados_clubes.gz.txt`
(banquillo), los índices pequeños de `datos/` y la base del Atlas (estilos meta/clubes/jugadores, simulador, v40, v41).

- **Jugadores ya no necesita** `quintetos/index.html`, `quintetos/datos/<t>/*`, `quintetos/datos_v42/*` ni
  `quintetos/estilos_unificados.gz.txt`. El único uso que quedaba era «Ver quintetos y conexiones» del panel de Datos de
  jugadores, que ahora abre Equipos en el jugador. `jugadores.json` trae `borrar_al_republicar`: 214 rutas (104,3 MB) que
  hay que quitar (`null`) al republicar el artifact actual, porque una publicación conserva los ficheros que no se pasan.
- **Metodología · Guía de conceptos** es la pestaña «Aprende» de la página de quintetos: sus ejemplos se calculan en directo
  con el equipo elegido, así que necesita los ficheros de quintetos (~80 MB duplicados con Equipos). Alternativa más ligera
  (no aplicada): publicar en Metodología solo las alineaciones de una temporada cerrada y la en curso (~27 MB) y fijar allí
  la liga y la temporada de la guía; o dejar la Guía como enlace a Equipos.
- `atlas/estilos/brutos` solo va en Jugadores (Simular plantilla); el Atlas lo precarga en segundo plano y tolera que falte.

## 4. Cómo republicar cada sitio

Límites por publicación: 255 ficheros y 64 MB (varias publicaciones a la misma URL suman ficheros; una versión admite 511
ficheros y 256 MiB). Equipos y Metodología necesitan al menos tres lotes cada uno.

1. **Jugadores** (URL actual): publicar `index.html` y los `ficheros` de `sitios/jugadores.json`, con `sitio.json` desde
   `sitios/sitio_jugadores.json`, y `null` para cada ruta de `borrar_al_republicar` en el mismo lote o en el último.
2. **Equipos**: crear el artifact con `index.html`, `sitio.json` = `sitios/sitio_equipos.json` y los `ficheros` de
   `sitios/equipos.json` (en lotes). Capacidades: `downloads` y `sample` (PDF y redacción del Informe de equipo) y `mcp`
   («Claude Code Remote»: get_trigger, fire_trigger) para el botón de actualización de la cabecera.
3. **Metodología**: igual con `sitios/metodologia.json` y `sitio_metodologia.json`. Capacidades: `downloads` (artículo PDF de
   Claves del estilo) y `mcp` (botón de actualización).
4. Con las tres URL conocidas, rellenar `urls` en los tres `sitio_<sitio>.json` y republicar solo `sitio.json` en cada uno.

La skill `actualizar-temporada` republica hoy un único artifact: hay que repartir sus ficheros de 2026-27 según estos
manifiestos (normalizados y historial en los tres; `datos/2026-27/*` en Jugadores, salvo `evaluacion_*` en Metodología;
`quintetos/datos/2026-27/*` y `datos_v42/2026-27/*` en Equipos y Metodología; `atlas/informe/2026-27` en Jugadores y Equipos).

## 5. Pruebas locales

Playwright sobre la copia de `kerno_cand` (http://localhost:8766/) con cinco variantes de `sitio.json` (sin fichero,
Jugadores, Equipos y Metodología con URL, Equipos sin URL), a 1280 y 390 px: raíl filtrado, enlaces a otros sitios bien
formados, portada de cada sitio, título, sin errores JS (salvo 404 de datos que la copia no tiene), sin scroll horizontal
(también con el raíl abierto en móvil), sin flechas de texto en el raíl y sin peticiones a ficheros de otro sitio al recorrer
las vistas de cada uno. Scripts en línea de `index.html` y `clasico.html`: todos compilan.
