# Corrección de identidades y nombres canónicos (03-11-2026)

## 1. Qué fallaba

La auditoría de identidades del simulador v3.2 (`bbfit auditar`) encontró 7 personas de 19.328 con nombres
incompatibles. Al revisarlas:

**Cinco son errores reales**, todos de BNXT y GBL (FIBA LiveStats):

| Persona | Mezcla |
|---|---|
| P003025 | Stefan Pot / Maarten Vandenbossche |
| P004567 | Vic De Wilde / Evert Vaneyk |
| P004898 | Paolo Marinelli / Mathias Ciccioni |
| P005255 | Liam Van Der Schalie / Boris Borst |
| P006972 | Tunde Fasasi / Joe Thomasson |

**Causa.** El `data.json` de FIBA LiveStats no trae el id de la persona, así que el id se construye con el nombre
internacional. Algunos clubes reutilizan la ficha de otro jugador y solo reescriben el nombre local. Resultado: el
partido se suma al jugador de la ficha, con el nombre de otro.

**Dos son la misma persona**, y no se separan:
- Yauheni Beliankou / Evgeniy Belyankov: es una transliteración.
- S. TRAORE / T. SEKOU MOUSSA en la Tercera FEB: tienen el mismo id de persona de la FEB.

## 2. Corrección

### Adaptador (`bbstats/adapters/fiba_livestats.py`)

- **Clave del jugador.** Si el nombre local (nombre y apellido) está en alfabeto latino y no comparte ninguna
  palabra con el internacional, ni se le parece, la clave sale del nombre local, que es el que se muestra.
- **Nombre y apellido invertidos.** Quien solo tiene el nombre y el apellido invertidos conserva su clave.
- **Alias.** Tres alias cubren nombres locales tecleados al revés en un solo partido.
- **Nombre visible.** Si el nombre local no es latino (GBL, en griego), se usa el internacional.

**Efecto.** Cambian 27 apariciones de un partido (25 en BNXT y 2 en la GBL), casi todas de un partido atribuido a
otro jugador. Por ejemplo, un partido de Bart Bijnsdorp sumado a Bryce Smith. En BSL, CBA, NCAA, NBL y VTB no
cambia ninguna clave.

**Reproceso.** BNXT y GBL se reprocesaron sin red: `bbstats historico --ligas bnxt gbl --sin-descarga`.

### Crosswalk (`bbmodel/crosswalk.py`)

`ids_estables` conserva el `persona_id` que tenía la mayoría de los nodos de cada grupo. Los grupos nuevos o separados
reciben ids nuevos.

**Resultado:**
- Ningún nodo existente cambia de persona.
- Hay 7 nodos nuevos y desaparecen 3 (ids que solo existían por el error).
- Las cinco mezclas quedan separadas.
- Joe Thomasson se une a su ficha principal.
- Jordan Harris (BNXT ↔ BBL/LBA) y James Young conservan sus enlaces.

### Revisión manual de puentes (§13)

| | |
|---|---|
| Muestra revisada | 100/100 correctos |
| Cota inferior de Clopper-Pearson al 95 % | 0,964 ≥ 0,95 |
| Umbral de fusión | No cambia |
| Fichero | `data/modelos/v3_2/auditoria_puentes/evaluacion.json` |

## 3. Nombres canónicos «Nombre Apellido(s)»

`python -m bbmodel nombres` genera `data/processed/nombres_canonicos.csv`, con una forma por persona. Reglas en
`bbmodel/nombres.py`:

1. «APELLIDO, NOMBRE» se pasa a «Nombre Apellido».
2. Entre las variantes de una persona se prefiere la completa (sin inicial) con más minutos.
3. Mejor la que no está toda en mayúsculas y lleva tildes. Si todas están en mayúsculas, se capitaliza y se
   recuperan las tildes de otras variantes. Las partículas de/del/van/der… van en minúscula; también se tratan Mc,
   O', los guiones y los números romanos.
4. Cuando la fuente da dos apellidos (FEB), se conservan.
5. Solo griego o cirílico: se transliteran.

Los nombres canónicos se aplican **solo al exportar** los datos del artifact (temporadas, normalizados, simulador,
Atlas de estilos y estilos unificados). La identidad (crosswalk, ids «n:nombre» de la BBL) sigue usando el nombre de
la fuente.

**Límite.** 2.990 personas solo aparecen con inicial en todas sus fuentes. Casi todas son de las actas de la FEB
(Tercera FEB 2.026, Segunda 269, Primera 198) o de la CBA (217). La FEB solo da el nombre completo en la plantilla
de la web del equipo, que falta en muchos equipos de Tercera FEB. Estas personas quedan como «J. Bocca».

## 4. Cadena

`scripts/rehacer_identidades.sh` rehace en el repositorio:
- las capas v2, las de encaje y la adaptación;
- las líneas base de la v2 en los cortes 2021-2024;
- la normalización v3.2 (sin repetir la ablación);
- los simuladores v3.2 y v3.3;
- los datos del artifact, que se dejan en `experimentos/v33_artifact/` sin publicar.

La v3.1 no se toca. La adaptación de fase 7 de la v3.2/v3.3 pasa a `data/modelos/adaptacion/v3_2/fase7/`.
