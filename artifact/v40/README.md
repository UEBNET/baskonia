# Modelo de equipo v4.0 · página del artifact

`index.html` es la página propia de la sección «Modelo de equipo v4.0», publicada en `v40/` dentro de los dos artifacts de
Cerno Analytics (la página clásica, área «Modelo v4.0», y el panel v2.0, sección «05 · Modelo de equipo»). Se integra por
`<iframe>` con `?embed=1` (oculta su cabecera) y `#resumen | #anclas | #equipos | #metodo`; recibe `{irV40: vista}` por
`postMessage`, lee el tema (`mm.theme`) y el club (`cerno.ctx`) del almacenamiento local de la página principal y publica su
altura con `{atlasAlto}`.

Datos (`datos/`, publicados como `v40/*`), derivados de `data/modelos/v4_0/` al cierre del encargo (05-11-2026):

| Archivo | Origen |
|---|---|
| `resumen.json` | puertas F1–F5 y A5 (`docs/checkpoints/V40_F*.md`), `equipo/examen/` (F4 por grupo y corte), `equipo/anclas/` (NC e IM: separación, deciles, cobertura, complemento), `equipo/a5/resumen_a5.json`, límites declarados |
| `fichajes.json.gz.txt` | `equipo/anclas/nc_examen.csv.gz` ⋈ `equipo/anclas/im_examen.csv.gz` (fichajes de decisión 2022-23 a 2025-26) con nombre y equipo de los perfiles; columnas por columna, gzip + base64 |
| `equipos_2026-27.json` | `equipo/equipos_2026-27.csv.gz` + nombre del equipo; `lo80/hi80` = Net ± q·√((c·T_sd)² + s0²) con (s0, q) del grupo de liga en `calibracion.json` |
| `calibracion.json` | `equipo/calibracion.json` (capa 4 en producción) |

Cifras sin NaN (se escriben como `null`). Para regenerar tras un recálculo, repetir las uniones anteriores y volver a publicar
los cinco archivos en ambos artifacts.
