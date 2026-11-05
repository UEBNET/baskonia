# Artifact · informes con la v4.0 (05-11-2026)

Decisión del CEO (05-11-2026): los dos informes del Atlas (lectura de fichaje e informe de equipo) muestran la información
de la v4.0; las anclas NIVEL CERNO e IMPACTO sustituyen al «Nivel Cerno ±100» y al «Impacto en pista (RAPM)» como cifras
principales de 02 y 03; toda la lectura de fichaje usa la vara de la liga del club de destino (ya publicada el 04-11-2026);
el informe de equipo añade el Net proyectado de la plantilla y las anclas de cada jugador; las anclas se calculan en el
navegador con el motor de minutos del Atlas (v3.3 en JS), aproximación declarada en los glosarios.

## Qué hay (fuentes en `artifact/atlas/`, publicadas en `atlas/` de los dos artifacts)

- `simulador.js` (motor v3.3 importado del artifact publicado, que iba por delante del repo): `simular()` y `minutosEquipo()`
  exponen ahora `_mc` (minutos por simulación con y sin el fichaje, personas, pts/100 observados) para la capa 4.
- `v40.js` (nuevo): `CernoV40.cargar / anclasFichaje / ligaT / netEquipo / ligaNet / anclasPlantilla`. Misma β (F1), parejas
  (F2-A, rango 4), red aditiva (F3), calibración c y (s0, q) por grupo (F4) y referencias F_ref / F_mov con las capas de
  calibración de las anclas (F5) que la v4.0 en Python; los minutos salen del motor del Atlas.
- `v40/jugadores_v40.json.gz.txt` y `v40/referencias_v40.json.gz.txt`: tablas de `python -m bbequipo exportar-atlas`
  (`bbequipo/exportar_atlas.py`): 22 967 personas (β y sd por temporada, prior del perfil, h y factores de pareja por
  temporada con perfil), F_ref 80 liga×puesto (2026-27), F_mov por grupo, calibraciones NC (5 495 fichajes) e IM (4 362).
- `informe_v3.js` (lectura de fichaje): 01 «cómo leer» con las anclas; 02 panel Ink con Nivel Cerno e Impacto (rango 80 %);
  hoja nueva «Nivel Cerno e Impacto: las dos anclas» (cifras grandes con su rango y escala 0–100, producción esperada C,
  Net del equipo con él, valor propio β, referencia, «Si cambias su rol» con NC/IM por rol, cómo se calculan y nota del motor);
  03 KPIs con las anclas como índices, Net del equipo con él de la capa 4 (rango 80 %); sin destino, las anclas se calculan en
  su club actual con su propia plantilla; glosario en dos hojas con las definiciones nuevas. El ±100 pasa a «Nivel por minutos».
- `informe_equipo.js` (informe de equipo): 02 con el Net proyectado (puesto, rango 80 %) en mosaico y panel Ink; segunda hoja de
  02 con Nivel Cerno e Impacto en cada tarjeta y dos gráficos de puntos con rango (NC e IM por jugador) en lugar de las
  barras ±100 y RAPM; 03 con el Net proyectado como primer índice y el gráfico «lo que proyectan las plantillas de la liga»
  (punto y rango de los 20 equipos, el club destacado) en lugar del mapa; glosario. Si el club no está en el simulador
  (ligas sin plantilla), el informe sale como antes.
- `index.html` (Atlas, importado del publicado): carga `v40.js` y las tablas al cargar el simulador.

## Verificación (Playwright, servidor local con los datos del artifact)

- Lectura de fichaje: Jaime Fernández 2025-26 → Baskonia 2026-27 (titular): NC 60 [17–94], IM 54 [13–93], Net +1,0 [−4,5, +6,6];
  → Valencia Basket 2026-27 (go-to-guy): NC 66, IM 56; → Milano 2025-26 (rotación): NC 61, IM 51; sin destino (en Tenerife):
  NC 66, IM 53. 14 hojas, sin desbordes, sin errores de consola.
- Informe de equipo: Baskonia 2026-27: Net proyectado −2,6 [−7,6, +2,4], 18.º de 20 (producto Python v3.3: −2,9 [−8,1, +2,2],
  17.º); anclas de los 13 jugadores; 14 hojas, sin desbordes, sin errores.
- Coste en el navegador: lectura ≈ 0,2 s por escenario; informe de equipo ≈ 1 s (liga completa + 13 bajas simuladas).

## Límites

- Los minutos son los del motor del Atlas (v3.3 JS); el examen §11.4–11.5 se hizo con el motor en servidor. Mismas β, parejas,
  red aditiva, calibración y referencias. Las cifras de acierto siguen siendo las del examen, no de esta integración.
- El subíndice de compañeros (F2-B) no se calcula en el navegador.
- El Índice Fit no lo publica el motor v3.3 (meta.fit vacío): la lectura lo omite cuando no existe.
