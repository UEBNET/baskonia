# Extracción periódica de la intranet de clubes de Basket Basko

Módulo `basketbasko/`: entra en **clubes.basketbasko.com** con el usuario del club, descarga las estadísticas
de los equipos, jugadores y partidos y genera tablas, un resumen y un dashboard HTML. Se puede ejecutar a mano
o de forma periódica con GitHub Actions.

## 1. Cómo funciona la intranet (analizado sobre el código público de la web)

`clubes.basketbasko.com` es una aplicación React de la plataforma de **Optimal Way Consulting** (la misma que usan
otras federaciones). La página no contiene datos: el navegador los pide a dos APIs JSON. El extractor hace esas
mismas llamadas, así que no hace falta "rascar" HTML ni manejar un navegador.

| Paso | Petición | Para qué |
|---|---|---|
| Login | `POST https://esb.optimalwayconsulting.com/esf/1/<clave>/public/club/login` `{username, password}` | devuelve el token (JWT) en la cabecera `Authorization` |
| Club | `GET <esb>/auth/my-club` | datos del club |
| Equipos | `GET <esb>/auth/my-teams` (o `/auth/my-teams/season/<id>`) | equipos del club → `teamUuid` |
| Equipo | `GET https://msstats.optimalwayconsulting.com/v1/esf/teams/<teamUuid>/stats` | totales y medias de la temporada, partidos (`games`), plantilla (`roster`), quintetos |
| Jugador | `GET <stats>/esf/players/<uuid>/teams/<teamUuid>/stats` | detalle del jugador: partido a partido, tiros, avanzadas |
| Partido | `GET <stats>/esf/matches/<matchCallUuid>/stats?currentSeason=true` | acta estadística del partido |

Todas las peticiones llevan el token en la cabecera `Authorization`. Si caduca, la API responde
`ERRORCODEx0004` (o 401/403) y el extractor vuelve a hacer login una vez.

Las estadísticas vienen en tres bloques: `accumulated` (conteos: t1m/t1a, t2m/t2a, t3m/t3a, rebotes, asistencias,
recuperaciones, pérdidas, tapones, faltas, valoración `pir`, `plusMinus`…), `computed` (porcentajes y derivados) y
`advanced` (`offRtg`, `defRtg`, `netRtg`, `efgPer`, `tsPer`, `usgPer`, `pace`, `astPer`…).

## 2. Extracción controlada, paso a paso

### Paso 0 · Permiso
Usa **tu** usuario de club y descarga sólo lo que tu usuario puede ver. Antes de automatizarlo, confirma con la
Federación (o revisa las condiciones de uso del portal) que el uso automatizado de tu acceso está permitido.
Los datos incluyen **personas federadas, muchas menores de edad** (RGPD/LOPDGDD): guárdalos en sitios privados y
publica sólo agregados.

### Paso 1 · Instalar y poner las credenciales (nunca en el código)
```bash
pip install -r requirements.txt
export BB_USUARIO='usuario-del-club'
export BB_PASSWORD='contraseña'
```

### Paso 2 · Explorar (pocas peticiones, sin rastreo)
```bash
python -m basketbasko explorar
```
Hace login y pide: tu club, tus equipos, las estadísticas de **un** equipo, de **un** jugador y de **un** partido
(≈6 peticiones). Guarda las respuestas en `data/basketbasko/explorar/` y un esqueleto de claves en
`_estructura.json`. **Revisa aquí que están los datos que quieres** para el dashboard.

Si `equipos_detectados` sale vacío, abre `mis_equipos.json`, localiza los identificadores de tus equipos y ponlos
en `config/basketbasko.json` → `"equipos": ["uuid-1", "uuid-2"]`.

### Paso 3 · Extracción completa
```bash
python -m basketbasko extraer             # equipos propios + jugadores + partidos
python -m basketbasko extraer --rivales   # además, los equipos rivales (si tu usuario tiene acceso)
python -m basketbasko procesar            # rehace tablas y dashboard desde el último bruto, sin conectarse
```
Controles en `config/basketbasko.json`:

| Clave | Por defecto | Efecto |
|---|---|---|
| `pausa_s` | 1.5 | segundos entre peticiones (cortesía con el servidor) |
| `max_peticiones` | 1500 | tope duro por ejecución; al llegar se para y queda anotado en los avisos |
| `temporada_id` | null | temporada concreta (si no, la que devuelve el portal por defecto) |
| `equipos` | [] | `teamUuid` añadidos a mano |
| `incluir_jugadores` / `incluir_partidos` / `incluir_rivales` | true / true / false | profundidad del rastreo |

Los partidos ya descargados se guardan en `data/basketbasko/cache/partidos/` y **no se vuelven a pedir**:
las ejecuciones periódicas sólo piden lo nuevo (≈ 1 petición por equipo y jugador + los partidos nuevos).

### Paso 4 · Programarlo (GitHub Actions)
1. Repositorio → *Settings → Secrets and variables → Actions → Secrets*: crea `BB_USUARIO` y `BB_PASSWORD`.
2. El workflow `.github/workflows/basketbasko.yml` se ejecuta **lunes y jueves a las 05:17 UTC** y también a mano
   (*Actions → Intranet Basket Basko → Run workflow*). Para cambiar la frecuencia edita la línea `cron`.
3. Cada ejecución deja el resultado como *artifact* descargable (30 días).
4. Si quieres que el dashboard se alimente desde el propio repositorio, crea la variable `BB_PUBLICAR = true`
   (*Variables*): el workflow hará commit de `data/basketbasko/processed/`. **Hazlo sólo con el repositorio privado.**

Los brutos, la caché y las muestras están en `.gitignore` (datos personales).

## 3. Qué se genera (`data/basketbasko/processed/`)

| Fichero | Contenido |
|---|---|
| `equipos.csv/.json` | 1 fila por equipo: totales (`tot_*`), medias (`avg_*`) y las del rival (`rival_tot_*`, `rival_avg_*`) |
| `jugadores.csv/.json` | 1 fila por jugador-equipo: totales y medias (+ `det_tot_*` del detalle del jugador) |
| `partidos.csv/.json` | 1 fila por partido de cada equipo: rival, local/visitante, resultado, estadísticas propias y del rival |
| `boxscores.csv/.json` | filas jugador/equipo de cada acta de partido |
| `resumen.json` | indicadores del club y de cada equipo: PJ, G/P, puntos a favor/en contra, máximos anotadores, mejor valoración |
| `historico.csv` | una fila por ejecución y equipo, para ver la evolución temporada a temporada |
| `dashboard.html` | dashboard autocontenido (abre con doble clic): KPIs, tarjeta por equipo, tabla de jugadores ordenable y filtrable |

Ningún campo de la API se descarta: si la Federación añade estadísticas nuevas aparecen como columnas nuevas.

## 4. Dashboard: opciones

- **Incluido**: `dashboard.html`, se regenera en cada ejecución.
- **Herramientas BI** (Looker Studio, Power BI, Metabase): conectarlas a los CSV de `processed/`
  (p.ej. publicados en un Google Drive o en el repositorio privado).
- **Página propia** que lea `resumen.json` y `jugadores.json`.

## 5. Problemas frecuentes

| Síntoma | Causa / solución |
|---|---|
| `Login rechazado` | usuario/contraseña incorrectos, o la cuenta exige otro tipo de acceso (p.ej. el login por enlace desde la web de la federación). Comprueba que entras en la web con esas credenciales. |
| `Sin permiso para …/teams/<uuid>/stats` | tu usuario no tiene acceso a las estadísticas de ese equipo (típico con rivales). Queda en avisos y el resto sigue. |
| `Límite de N peticiones alcanzado` | sube `max_peticiones` o reduce el alcance (`incluir_rivales: false`). |
| Cambia la web | si Optimal Way cambia la clave de la URL `esb` o la federación (`esf`), actualízalas en `config/basketbasko.json` (están en `https://clubes.basketbasko.com/main.js`, variables `REACT_APP_URL_ESB` / `REACT_APP_FEDE`). |

## 6. Estado de la verificación

Verificado sin credenciales: la web, las rutas y el mecanismo de login/token (a partir del código JavaScript del
portal) y que la API responde con el error de "sin token" esperado. **No verificado**: el contenido real de las
respuestas autenticadas. Los nombres de campo del procesado proceden del código del portal y los tests usan una API
simulada con ese formato; el primer `explorar` con tus credenciales es el que lo confirma.
