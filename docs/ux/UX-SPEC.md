# Cerno Analytics · Capa de usabilidad v2 (limpieza visual sin pérdida de funciones)

Objetivo del CEO: el artifact debe parecer un **dashboard corporativo premium**, mucho más limpio e intuitivo,
**sin perder ninguna funcionalidad** (filtros, selectores, parámetros de simulación, datos, cálculos, estados guardados,
rutas de archivo, mensajes entre marcos). No es un rebranding (la marca ya está aplicada en `<style id="cerno-brand">`):
es usabilidad, jerarquía y orden.

## Regla de oro (no negociable)
- **No borrar ni recrear** controles con id o `data-*` que el código use. Se pueden **mover** nodos (appendChild conserva
  los listeners), envolver en contenedores plegables, cambiar su CSS y textos de ayuda. Nunca cambiar ids, `name`,
  `data-*`, valores de `<option>`, claves de localStorage ni la lógica de cálculo.
- Si el código re-renderiza un contenedor con `innerHTML` (por id), mover el contenedor completo, nunca sus hijos.
- Cualquier cosa que se oculte por defecto debe seguir a **un clic** (plegable, popover o pestaña) y con rótulo claro.
- Sin errores nuevos en consola. Todas las vistas cargan como antes.

## Principios visuales
1. **Una jerarquía por pantalla**: título de vista (Mona 620) → banda de KPIs → contenido principal → detalle plegable.
2. **Menos cajas**: tarjetas sin sombra y sin borde completo; separación por **filete superior** (1px `var(--line-2)`)
   y aire (módulo 8 px: 16/24/32). Fondos `var(--surface)`; nada de cajas dentro de cajas dentro de cajas.
3. **Filtros en un solo sitio**: la columna de filtros de cada vista se convierte en un **panel de filtros plegable**
   (botón «Filtros» con contador de filtros activos). Dentro, cada grupo es un acordeón (`<details>`), abierto solo el
   primero o los que tienen valores no por defecto. Encima del contenido, una fila de **chips de filtros activos**
   (solo lectura o con ×, si es fácil y seguro) para saber qué se está viendo sin abrir el panel.
4. **KPIs compactos**: banda horizontal de cifras (etiqueta mono 10.5px mayúsculas G600, cifra Mona 22-26px, apoyo 11px),
   separadas por filetes verticales, sin recuadro por cifra. Máximo 5-6 por fila; en 390 px, 2 por fila.
5. **Ayudas «¿Cómo se lee?»**: plegadas por defecto como enlace discreto «¿Cómo se lee?» (summary) con el texto dentro.
   Respetan el conmutador global «Ayudas de lectura» si existe (activado = se muestran abiertas).
6. **Columnas laterales derechas** con información secundaria: pasan debajo o a un plegable «Más detalle», salvo
   que sean el control principal de la vista (p. ej. el comparador de A/B/C).
7. **Botones**: un solo primario por vista (Ink); el resto, secundarios con filete. Pestañas de segundo nivel como
   subrayado (no píldoras rellenas).
8. **Tablas**: cabecera de etiqueta mono, filas de 34-36px, cifras en Geist Mono a la derecha, cebra muy suave o ninguna,
   fila seleccionada con banda Index al 28 %. Paginación discreta abajo a la derecha.
9. **Color**: solo tokens existentes (`--ink`, `--ink-2`, `--muted`, `--faint`, `--line`, `--line-2`, `--surface`,
   `--surface-2`, `--surface-3`, `--accent`, `--good`, `--bad`, `--cn-index`…). Index (#F2CC2F) ≤ 2 % y nunca texto sobre claro.
   Tipografías: solo Mona Sans, Newsreader, Geist Mono (ya cargadas).
10. **Responsive**: 1440 px y 390 px sin scroll horizontal de página (las tablas anchas hacen scroll dentro de su caja).
    Modo claro y oscuro (`:root[data-theme="dark"]`).

## Nomenclatura
- Estilos: **solo** la taxonomía nueva: Pistons, Isolation, Old-School, Spacing, Circulación, Pintura (y sus mezclas
  «Isolation · Circulación»). Nunca nombres VaDE (Creación individual, Exterior y presión, Lejos del aro, Pausado y
  seguro, Pintura física, Circulación y triple, Exterior y riesgo, Ritmo y juego limpio, Ataque al aro) ni códigos E01–E06
  ni la palabra «VaDE» en la interfaz. Donde un modelo está estimado sobre los grupos VaDE (química de estilos, regiones
  del mapa), esos grupos se rotulan como **«Perfil de mapa A–F»** neutros.
- Roles (simulador v2.1): Residual, Profundidad, Rotación, Titular, Go-to-guy. Rol estimado por minutos: prefijo «≈ ».
- Sin superlativos ni expresiones vetadas (revolucionar, desbloquear, el mejor, mágico, garantizado…).

## Implementación
- Añadir al final de cada HTML (después de `#cerno-brand`) un `<style id="cerno-ux">` y, si hace falta, un
  `<script id="cerno-ux-js">` que solo **reorganiza** DOM existente (mover/envolver), idempotente y tolerante a que un
  elemento no exista (comprobar antes de usar).
- Documentar en comentarios al principio de cada bloque qué se movió y por qué.
