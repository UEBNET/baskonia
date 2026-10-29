---
name: actualizar-temporada
description: Actualización delta (descarga única) de los datos de la temporada en curso (2026-27) en todas las ligas del pipeline bbstats — cajas, métricas, jugada a jugada, quintetos, tiros, entrenadores, informes FEB y JSON del artifact — con informe antes/después por liga. Úsala cuando pidan «actualizar los datos de la temporada», «descargar los partidos nuevos de 2026-27» o lo lance el botón de actualización del artifact Cerno Analytics.
---

# Actualizar la temporada en curso (delta)

Skill de **una sola descarga** que pone al día la temporada en curso (la de
`config/sources.json → temporada_por_defecto`, hoy **2026-27**) con todo lo que el pipeline ya extrae,
sin tocar su código (`bbstats/`) ni otras temporadas.

## Qué hace, paso a paso

| Paso | Qué ejecuta | Qué produce |
|---|---|---|
| 0. Foto «antes» | lectura de `data/processed/<t>/` (sin red) | partidos, última fecha, jugadores, equipos por liga |
| 1. Descarga delta + procesado | `bbstats.api.ejecutar(temporada=t)` | brutos nuevos en `data/raw/<liga>/<t>/`, `data/processed/<t>/ligas/*.csv` (480 columnas, fases regular/playoffs/total), quintetos, parejas, tríos, tiros, on/off en `quintetos/<liga>/` |
| 2. Entrenadores | `bbstats.entrenadores.ejecutar(temporadas=[t])` | `data/processed/<t>/entrenadores/<liga>_partidos.csv` y `_tramos.csv` |
| 3. Informes FEB | `bbstats.feb_informe.ejecutar` (si entra feb1/feb2/feb3) | `data/processed/<t>/feb/` |
| 4. JSON del artifact | `bbstats.pipeline.export_artifact` | `data/artifact/<t>/` (no versionado) |
| 5. Foto «después» y control | comparación + comprobaciones | informe JSON y tabla |

**Por qué es «delta»**: cada adaptador recibe el último bruto guardado y sólo pide a la web lo que falta.
Los adaptadores FEB, FIBA web (BCL, FEC) y FIBA LiveStats (BSL, GBL) guardan paquetes **incrementales**
con sólo los partidos nuevos; si no hay partidos nuevos no se guarda nada. Si la web de una liga falla, se
reprocesa su último bruto y la liga queda marcada `ok_bruto_anterior` (no se pierde nada).

## Cómo se usa

```bash
python .claude/skills/actualizar-temporada/actualizar_delta.py                    # todas las ligas activas
python .claude/skills/actualizar-temporada/actualizar_delta.py --ligas feb1 feb2 feb3
python .claude/skills/actualizar-temporada/actualizar_delta.py --sin-descarga     # reprocesar sin red
python .claude/skills/actualizar-temporada/actualizar_delta.py --solo-informe     # sólo ver el estado actual
python .claude/skills/actualizar-temporada/actualizar_delta.py --json             # informe completo en JSON
```

Opciones: `--sin-entrenadores`, `--sin-artifact`, `--config <ruta>`. Sólo admite la temporada en curso;
para otra temporada se usa `python -m bbstats ejecutar --temporada T`.

Duración orientativa con todas las ligas: 30-90 minutos (la NBA vía Basketball-Reference va a 3,5 s por
petición; la FEB a ≥ 1 s por cortesía).

## Cómo se comprueba que funcionó

1. El código de salida es 0 (1 = alguna liga terminó en error; 2 = ya había otra actualización en curso).
2. La tabla final muestra, por liga, partidos antes → después y última fecha antes → después.
3. Columna «incidencias»: error de descarga, bruto anterior reutilizado, CSV sin las 480 columnas, menos
   partidos que antes, liga sin partidos (la G League empieza en noviembre: no es incidencia antes del 1-11)
   o última fecha con más de 10 días sin partidos nuevos.
4. El informe completo queda en `data/processed/<t>/informes/delta_<fecha>.json` (carpeta no versionada).

## Contrato para el botón del artifact (futuro)

Pensado para que un botón de «Cerno Analytics» lo lance (aún **no** existe el botón):

* Llamada en Python: `actualizar(temporada=None, ligas=None, descargar=True, entrenadores=True,
  artifact=True, solo_informe=False, progreso=callable)` → `dict` JSON-serializable.
* Campos del informe: `estado` (`ok` | `error_parcial` | `ocupado`), `temporada`, `modo`, `inicio`, `fin`,
  `pasos` (segundos y estado por paso), `resultado` (lista por liga con `antes`, `despues`,
  `partidos_nuevos`, `estado`, `incidencias`), `tabla_md`, `ruta_informe`.
* Cerrojo `data/processed/<t>/.delta.lock`: dos pulsaciones seguidas no lanzan dos descargas a la vez.
* Vías de ejecución previstas: el servidor `python -m bbstats servidor` (añadiendo un endpoint que llame a
  `actualizar`) o el workflow «EJECUTAR» de GitHub Actions.

## Reglas

* No modifica el código de `bbstats/` ni otras temporadas.
* En el repositorio, los datos actualizados se versionan sólo en una rama de datos (`datos/…`), nunca en
  `main` directamente; los ficheros > 90 MB no se suben.
* Si una fuente falla no se cambia código: se anota liga, error y qué falta, y se sigue con las demás.
