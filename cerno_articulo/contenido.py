"""Texto del artículo: métodos fijos y resultados leídos de los ficheros (cerno_articulo.datos)."""
from __future__ import annotations

import numpy as np

from . import datos as DT
from .estilo import esc, ev, grafico_rangos, n, rango, tabla

FUENTE = "Datos públicos (fuentes oficiales de cada liga, FIBA LiveStats, ESPN, Infobasket, QQ/Sina) · Cerno Analytics · 02-11-2026"


def seccion(k: int, nombre: str, titulo: str, entradilla: str, cuerpo: str) -> str:
    return (f'<section class="sec"><div class="sec-cab"><div><div class="ceja">Sección {k:02d} · {nombre}</div>'
            f'<h2>{titulo}</h2></div><div class="num">{k:02d}</div></div><p class="entradilla">{entradilla}</p>'
            f'{cuerpo}</section>')


def _pendiente(que: str) -> str:
    return f'<p>{ev("hipotesis")}Resultado pendiente: {esc(que)} se completará cuando termine el cálculo.</p>'


# ================================================================================================== 01 resumen
def resumen(R: dict) -> tuple[str, str, str]:
    ab, ex, sim = R["ablacion"], R["examen_v32"], R["sim_v32"]
    tarjetas = []
    if ex:
        p = ex["combinada_b2_con_conocimiento_feb3"]["criterio_1_mae"]
        tarjetas.append(("Normalización v3.2 frente a la v2", rango(p["estimacion"], *p["ic95"], 1, pct=True, signo=True),
                         "Error medio relativo en las 33 métricas · IC 95 % · cambios de liga 2023-24 → 2025-26."))
    if sim:
        t = sim["examen"]["total"]
        tarjetas.append(("Error de pts/100 del simulador", f'{n(t["v3.2"]["mae_pts_p100"])} <span class="mono">'
                         f'(v3.1: {n(t["v3.1_motor"]["mae_pts_p100"])})</span>',
                         "Examen sin fuga, cortes anidados 2021-22 → 2024-25."))
        tarjetas.append(("Cobertura del 80 % en pts/100", f'{n(t["v3.2"].get("cob80_pts_p100"), 3)}',
                         "Recalibración conforme de dos colas con los cortes anteriores."))
    if not tarjetas:
        tarjetas = [("Estado", "en cálculo", "Las cifras de la v3.2 se completan al terminar la cadena.")]
    tj = "".join(f'<div class="tarjeta"><div class="etq">{a}</div><div class="cifra">{b}</div><p>{c}</p></div>'
                 for a, b, c in tarjetas)
    cuerpo = f"""<div class="tarjetas">{tj}</div>
<p>Este artículo documenta la lectura entre ligas de Cerno Analytics en su versión 3.2: cómo se traduce el rendimiento
de un jugador entre 20 competiciones y cómo se simula su encaje en un club de destino. Sustituye al artículo anterior,
que solo trataba los estilos de juego en ocho ligas, y recoge todas las versiones intermedias: los algoritmos A y B,
la normalización amortiguada (v2), la red jerárquica (v3.0), la mezcla de ambas (v3.1) y los cambios de la v3.2.</p>
<p>Tres ideas atraviesan el documento. Primera: <b>ningún modelo se publica sin un examen fuera de muestra</b>, con
cambios de liga reales y con las reglas de decisión fijadas antes de ver los resultados. Segunda: <b>cada cifra lleva su
rango</b> y las reglas de recalibración buscan que el intervalo del 80 % cubra de verdad un 80 %. Tercera: <b>la vara
puede ser cualquier liga</b>: la EuroLeague es solo una forma de expresar la salida, y la v3.2 deja preparados los
datos para poner a 0 la liga de destino de cada comparación.</p>
<div class="indice-linea"><div class="etq">Lectura</div><p>{_lectura_resumen(R)}</p></div>"""
    return ("Resumen", "La v3.2 decide cada pieza con un examen anidado y declara cuánto sabe", cuerpo)


def _lectura_resumen(R: dict) -> str:
    ab, ex, sim = R["ablacion"], R["examen_v32"], R["sim_v32"]
    if not (ab and ex and sim):
        return "Las conclusiones de la v3.2 se escriben al terminar el cálculo; el método está fijado y documentado."
    fin = [x for x in ab["decisiones"].values() if x["aplica_en"] == "final"][0]
    q = fin["quitar"]
    p = ex["combinada_b2_con_conocimiento_feb3"]["criterio_1_mae"]
    f = sim["final"]
    return (f"La ablación quita {len(q)} pieza{'s' if len(q) != 1 else ''} de la red "
            f"({', '.join(DT.PIEZAS.get(x, x) for x in q) or 'ninguna'}). La normalización v3.2 queda "
            f"{n(abs(p['estimacion']), 1, pct=True)} {'por debajo' if p['estimacion'] < 0 else 'por encima'} del error de "
            f"la v2 [IC 95 % {n(p['ic95'][0], 1, pct=True, signo=True)} a {n(p['ic95'][1], 1, pct=True, signo=True)}]. "
            f"El simulador publicado {'quita ' + ', '.join(f['quitar']) if f['quitar'] else 'conserva todos los pasos'}, "
            f"usa la producción del {'Atlas' if f['produccion'] == 'atlas' else 'motor'} y aplica la recalibración de "
            f"dos colas.")


# ================================================================================================== 02 datos
def datos_seccion(R: dict) -> tuple[str, str, str]:
    pu = R["puentes"]
    filas = [["EuroLeague, EuroCup", "Euroleague Basketball", "2020-21 → 2026-27", "Jugada a jugada propia"],
             ["ACB, LBA, BBL, LNB, BSL, GBL", "Webs oficiales y FIBA LiveStats", "2020-21 → 2026-27", "Jugada a jugada"],
             ["BCL, FIBA Europe Cup", "fiba.basketball", "2020-21 → 2026-27", "Jugada a jugada"],
             ["NBA, G League", "Datos oficiales de la liga", "2020-21 → 2026-27", "Jugada a jugada"],
             ["Primera, Segunda y Tercera FEB", "FEB (actas y jugada a jugada)", "2022-23 / 2023-24 → 2026-27", "Jugada a jugada"],
             ["NBL (Australia)", "nbl.com.au; FIBA LiveStats en 2023-24", "2020-21 → 2026-27", "Quintetos 94-98 % (2023-24: 66 %)"],
             ["VTB United League", "Infobasket", "2020-21 → 2026-27", "Jugada a jugada desde 11-03-2022; 97-100 %"],
             ["BNXT League", "FIBA LiveStats", "2021-22 → 2026-27", "Temporada regular 97-100 %"],
             ["CBA", "QQ + Sina", "2020-21 → 2026-27", "Quintetos 61-93 %; sin coordenadas de tiro"],
             ["NCAA D-I (top-50 T-Rank)", "ESPN", "2020-21 → 2025-26", "Cambios solo en 2024-25 y 2025-26 (97 %)"]]
    top = pu.sort_values("personas", ascending=False).head(8)
    cuerpo = f"""<p>La base es la temporada regular de 20 competiciones de 2020-21 a 2026-27, con datos hasta el
29-10-2026. Cada partido se traduce al formato de FIBA LiveStats y pasa por el mismo analizador, de modo que los
quintetos, el +/- y las métricas de pista se calculan igual en todas las ligas. La validación de quintetos compara
minutos y +/- reconstruidos con los oficiales; el boxscore solo se usa como último recurso, cuando no existe jugada a
jugada.</p>
<div class="tcap">Las 20 competiciones y su cobertura de jugada a jugada</div>
<div class="tsub">Fuente · temporadas · validación de quintetos frente al boxscore oficial</div>
{tabla(["Competición", "Fuente", "Temporadas", "Jugada a jugada"], filas)}
<h3>Identidad de los jugadores</h3>
<p>Las fuentes no comparten identificadores. El crosswalk une registros por nombre normalizado, inicial + apellido y
fecha de nacimiento completa, trayectoria contigua y club común, con un umbral de confianza de 0,75. La regla de
inicial + apellido + fecha de nacimiento llevó la CBA de 3 a 88 jugadores puente. {ev("dato")}Los pares de ligas con
más personas en común son {", ".join(f"{DT.NOMBRES.get(r.liga_a, r.liga_a)}–{DT.NOMBRES.get(r.liga_b, r.liga_b)} "
f"({r.personas})" for r in top.itertuples())}.</p>
<p>{ev("lectura")}Los puentes son la materia prima de la normalización: el nivel de una liga se mide con los jugadores
que han jugado en ella y en otra. Por eso se audita su identidad (sección 11): {"hay preparada una muestra de 100 "
"jugadores puente de las ligas con pocos puentes para revisión manual" if R["auditoria"] else "pendiente"}.</p>"""
    return ("Datos", "Veinte ligas comparables porque se miden igual, jugada a jugada", cuerpo)


# ================================================================================================== 03 normalización previa
def normalizacion_previa(R: dict) -> tuple[str, str, str]:
    ex = R["examen_v31_15"]
    v31 = ""
    if ex:
        a, b = ex["cvae_sola"]["criterio_1_mae"], ex["combinada_regla_fija"]["criterio_1_mae"]
        v31 = (f"<p>{ev('dato')}En el examen de la v3.1 (15 ligas, cortes 2023 y 2024), la red sola quedó "
               f"{rango(a['estimacion'], *a['ic95'], 1, pct=True, signo=True)} frente a la v2, y la mezcla al 50 % "
               f"{rango(b['estimacion'], *b['ic95'], 1, pct=True, signo=True)}. La mezcla gana porque los dos modelos "
               f"fallan de forma distinta.</p>")
    cuerpo = f"""<p>Un número de una liga mezcla tres cosas: el jugador, el entorno de su liga (ritmo, reglamento, criterio
del estadístico) y el nivel de la liga. Todas las versiones separan esas tres partes; cambian en cómo estiman el
nivel y en cuánta estructura imponen.</p>
<h3>Algoritmo A: puesto en la liga y tipo de cambio</h3>
<p>Quita la suerte de las muestras pequeñas (contracción empírica con el ruido de muestra σ²/n), coloca al jugador en
su liga, temporada y posición (z) y aplica una recta por liga, a = m_l + s_l·z, aprendida de los jugadores puente. Es
un cambio de divisas: el puesto dice cuántos dólares tiene el jugador y el tipo de cambio, cuántos euros vale un
dólar.</p>
<h3>Algoritmo B: un ADN de 8 dimensiones</h3>
<p>Una red multitarea aprende a la vez las 25 métricas de caja: cada jugador tiene un vector latente que no depende de
dónde juega y la estadística observada es ese vector expresado en una liga, temporada, posición y equipo concretos.</p>
<h3>v2: normalización amortiguada</h3>
<p>Sustituye la recta del A por seis piezas: un grafo de competiciones-temporada unido por puentes (el nivel de cada
nodo por mínimos cuadrados, como resistencias en serie y en paralelo), contracción bayesiana por escalón de liga,
mapeo monótono, compresión de las colas en los saltos largos, reponderación de la selección de puentes y covarianza
completa del grafo. El dataset publicado (<span class="mono">&lt;m&gt;_am</span>) promedia A y B amortiguados.</p>
<h3>v3.0 y v3.1: la red jerárquica y la mezcla</h3>
<p>La v3.0 es una CVAE jerárquica: un latente absoluto por persona y temporada, niveles por competición con un paseo
aleatorio entre temporadas y una jerarquía de escalones, un codificador amortizado que combina las filas de cada
persona por producto de expertos y un decodificador con ajustes por liga (FiLM) y cabezales propios. La posterior de
los niveles es conjunta, de modo que la varianza de una traducción usa Var(δ_b − δ_a) = Σ_aa + Σ_bb − 2Σ_ab.
No pasó su puerta de control. La v3.1 fijó la escala latente por liga y mezcla la red con la v2 caso a caso, con peso
0,5 y salvaguardas.</p>
{v31}
<div class="eq">ŷ = b(l,t,p) + T(equipo) + L·r + (W2 + V_l)·[γ_l ⊙ tanh(W1 r + c1) + β_l] + ζ_i
r = (u_it − μ_c) / s_l          u_(i,t+1) − u_it − d(edad) ~ N(0, η²),  η = 0,08
centro_v3.1 = w · CVAE + (1 − w) · v2,   w = 0,5 (0 con las salvaguardas)</div>"""
    return ("Normalización", "Cada versión separa jugador, entorno y nivel; la mezcla gana porque sus errores difieren",
            cuerpo)


# ================================================================================================== 04 método v3.2
def metodo_v32(R: dict) -> tuple[str, str, str]:
    filas = [["B1", "Ablación de la red: ciclo, FiLM, cabezal por liga, ζ, IPW, K", "No inferioridad +0,5 % (IC 95 %), salvaguardas"],
             ["B2", "Peso de la red en la mezcla por métrica", "Mejora ≥ 1 % demostrada (IC 95 %); si no, 0,5"],
             ["B4", "Inferencia semiamortizada (200 pasos)", "Misma regla que B1"],
             ["B5", "20 redes en el conjunto (antes 5)", "Se aplica siempre"],
             ["B6", "Verosimilitud t de Student, ν por métrica", "Misma regla que B1"],
             ["B3", "Decodificar en la liga de destino", "Descartada por el usuario"],
             ["B8", "Modelo secuencial de trayectorias", "Descartada; trabajo futuro"]]
    cuerpo = f"""<p>La v3.2 conserva la arquitectura de la v3.1 y somete cada pieza a una regla fijada antes de ver los
resultados. Las reglas se endurecieron el 02-11-2026 con un documento de criterios matemáticos, aprobado también antes
de ver ningún resultado.</p>
{tabla(["Código", "Cambio", "Regla de decisión"], filas)}
<h3>Cortes anidados</h3>
<p>Se ajusta con las temporadas hasta t y se predicen los cambios de liga de t a t+1 (≥ 300 minutos en las dos). El
corte 2021 solo recalibra los intervalos del 2022; la decisión que se aplica en 2023 usa el corte 2022; la de 2024,
los cortes 2022 y 2023; la final, los tres. {ev("lectura")}Los cortes 2023 y 2024 ya se miraron al diseñar la v3.1:
el examen limpio será 2025-26 → 2026-27, prerregistrado.</p>
<h3>Regla de la ablación (B1, B4, B6)</h3>
<ul><li>Se evalúa la <b>mezcla</b> con peso fijo 0,5, no la red sola: lo que se publica es la mezcla.</li>
<li>Δ_P = MAE_F(sin P)/MAE_F(con P) − 1, con la media por <b>familias</b> de métricas (tiro, uso y creación, rebote,
defensa, impacto, perfil de tiro, global), para que las seis métricas de tiro no pesen seis veces.</li>
<li>IC 95 % por bootstrap anidado: personas × corte y, por separado para «con» y «sin», las 5 semillas con reemplazo.</li>
<li>Se quita P si IC95,sup(Δ_P) &lt; +0,5 %, la cobertura del 80 % recalibrada sigue en [0,78; 0,85] y pasan las
salvaguardas de ciclo (todas las piezas) y de niveles (obligatoria para la IPW: ningún nivel se mueve más de una DT).
Si IC95,inf &gt; 0 se conserva; entre medias, se conserva como indeterminada.</li></ul>
<h3>t de Student y semiamortización</h3>
<div class="eq">log p(y | ŷ, σ²) = log Γ((ν+1)/2) − log Γ(ν/2) − ½ log(νπσ²) − (ν+1)/2 · log(1 + (y − ŷ)²/(νσ²))
ν_m = 3 + 27 · sigmoide(θ_m)        Fisher del experto: (ν + 1)/((ν + 3)·σ²)</div>
<p>{ev("lectura")}Con la t, la posterior conjunta de los niveles deja de ser exacta: es una aproximación de
Laplace con la información de Fisher. Los intervalos salen de cuantiles Monte Carlo de la mezcla de muestras.</p>"""
    return ("Método v3.2", "Cada pieza de la red se queda solo si quitarla empeora el examen", cuerpo)


# ================================================================================================== 05 resultados v3.2
def resultados_v32(R: dict) -> tuple[str, str, str]:
    ab, ex = R["ablacion"], R["examen_v32"]
    if not ab:
        return ("Resultados v3.2", "Resultados de la normalización v3.2", _pendiente("la ablación"))
    partes = []
    for k, d in ab["decisiones"].items():
        filas = [{"etiqueta": DT.PIEZAS.get(p, p), "c": 100 * x["delta_mezcla"], "lo": 100 * x["ic95"][0],
                  "hi": 100 * x["ic95"][1], "protagonista": x["quitar"],
                  "texto": x["estado"]} for p, x in d["piezas"].items()]
        partes.append(grafico_rangos(filas, f"Ablación con los cortes {k.replace('con_', '').replace('+', ', ')}",
                                     "Δ = MAE sin la pieza / MAE con ella − 1 · % · IC 95 % · margen +0,5 %",
                                     "Examen anidado · mezcla 0,5 · 5 redes por variante", cero=0.0, margen=0.5,
                                     fmt=lambda v: n(v, 1)))
    cuerpo = "".join(partes[-1:])
    tabla_dec = tabla(["Decisión con", "Se aplica en", "Piezas que se quitan"],
                      [[k.replace("con_", "").replace("+", ", "), str(d["aplica_en"]),
                        ", ".join(DT.PIEZAS.get(p, p) for p in d["quitar"]) or "ninguna"]
                       for k, d in ab["decisiones"].items()])
    cuerpo += tabla_dec
    if ex:
        p = ex["combinada_b2_con_conocimiento_feb3"]
        fj = ex.get("pesos_detalle_final", {})
        cuerpo += f"""<h3>Peso por métrica (B2)</h3>
<p>{ev("dato")}{fj.get("hacia_cvae", 0)} métricas se apartan de 0,5 hacia la red y {fj.get("hacia_v2", 0)} hacia la
v2; el resto queda en 0,5 porque su mejora no supera el 1 % con significación.</p>
<h3>Examen de la v3.2</h3>
{tabla(["Variante", "Error medio frente a la v2", "Cobertura 80 %"],
       [[nom, rango(x["criterio_1_mae"]["estimacion"], *x["criterio_1_mae"]["ic95"], 1, pct=True, signo=True),
         n(x["criterio_2_cobertura"]["cobertura_media"], 3)]
        for nom, x in (("Red sola", ex["cvae_sola"]), ("Mezcla 0,5", ex["combinada_peso_fijo_0_5"]),
                       ("Mezcla con B2 anidado", ex["combinada_b2_anidada"]),
                       ("v3.2 publicada (con la Tercera FEB)", p))], {1, 2}, {3})}
<p>{_rapm_texto(ex)}</p>{_nu_texto(ex)}"""
    return ("Resultados v3.2", "La ablación decide con evidencia; lo indeterminado se conserva", cuerpo)


def _rapm_texto(ex: dict) -> str:
    r = (ex or {}).get("rapm_exposicion") or {}
    if "rapm" not in r:
        return ""
    x = r["rapm"]
    return (f"{ev('dato')}RAPM: la ganancia frente a la v2 es {n(x['ganancia_total'], 1, pct=True, signo=True)} en "
            f"todos los casos y {n(x['ganancia_exposicion_alta'], 1, pct=True, signo=True)} con exposición alta. "
            f"{'Se comunica como impacto en pista.' if x['comunicar_como_impacto'] else 'No se comunica como impacto en pista: buena parte de la mejora es acertar el encogimiento del ridge.'}")


def _nu_texto(ex: dict) -> str:
    nu = (ex or {}).get("nu_por_metrica")
    if not nu:
        return ""
    v = nu["nu"]
    return (f"<p>{ev('dato')}Grados de libertad de la t: mediana {n(np.median(list(v.values())), 1)} "
            f"(de {n(min(v.values()), 1)} a {n(max(v.values()), 1)}). "
            f"{'En el límite inferior: ' + ', '.join(nu['en_limite_inferior']) + '.' if nu['en_limite_inferior'] else 'Ninguna métrica toca el límite inferior.'}</p>")


# ================================================================================================== 06 vara de destino
def vara_destino(R: dict) -> tuple[str, str, str]:
    niv = DT.niveles_liga(R, "per")
    ref = niv[niv["competicion"] == "euroleague"]["nivel_gauge_media"]
    r0 = float(ref.iloc[0]) if len(ref) else 0.0
    filas = [{"etiqueta": DT.NOMBRES.get(r.competicion, r.competicion), "c": r.nivel_gauge_media - r0,
              "lo": r.lo80_gauge_media - r0, "hi": r.hi80_gauge_media - r0,
              "protagonista": r.competicion in ("acb",), "texto": n(r.nivel_gauge_media - r0, 2, signo=True)}
             for r in niv.itertuples()]
    graf = grafico_rangos(filas, "Nivel de cada liga en PER con la EuroLeague a 0 (2025-26)",
                          f"DT de capacidad · intervalo del 80 % · normalización {R['niveles_fuente'].replace('_', '.')}",
                          FUENTE, cero=0.0, fmt=lambda v: n(v, 1))
    pares = ""
    if R["pares"] is not None:
        p = R["pares"]
        sel = p[(p["a"] == "acb") | (p["b"] == "acb")].head(8)
        pares = tabla(["Métrica", "Par", "DT sumando marginales", "DT del par (v2)", "DT del par (mezcla)"],
                      [[r.metrica, f"{DT.NOMBRES.get(r.a, r.a)}–{DT.NOMBRES.get(r.b, r.b)}", n(r.sd_marginales_sumadas, 3),
                        n(r.sd_par_v2, 3), n(r.sd_par_mezcla, 3)] for r in sel.itertuples()], {2, 3, 4})
    ci = DT.ciclo_resumen(R)
    cuerpo = f"""<p>La normalización no fija ninguna liga: el gauge es la media ponderada de todas las competiciones.
«EuroLeague = 0» es solo una forma de expresar la salida. La v3.2 exporta lo necesario para que el artifact exprese
cualquier comparación en la vara de la liga de destino: la capacidad de cada jugador sin la incertidumbre del nivel
de su liga, las constantes de traducción y la covarianza conjunta de los niveles.</p>
<div class="eq">z_d = (θ + deriva(edad) − δ_d) / s_d          valor en d = T⁻¹(μ_d,t,pos + τ_d,pos · z_d)
Var(z_d) = (v_j + sd_par(o, d)²) / s_d² + (z_d − clip(z_d, soporte_d))²
sd_par = w · sd_red(δ_o − δ_d) + (1 − w) · sd_v2(δ_o − δ_d)      (cota de Cauchy-Schwarz)</div>
{graf}
<div class="indice-linea"><div class="etq">Qué cambia y qué no</div><p>Poner la liga de destino a 0 no mueve el valor
esperado de ningún jugador: la traducción es afín en la escala de trabajo. Cambia la incertidumbre, que pasa a usar la
covarianza del par de ligas en vez de sumar dos varianzas frente a la EuroLeague, y el recorte de soporte, que ahora es
el de la liga de destino y solo marca la extrapolación.</p></div>
{pares}
<p>{ev("dato")}El nivel de la liga pesa poco en la incertidumbre de un jugador: entre el 2 y el 4 % de la varianza
total (mediana), y las filas en las que restar esa parte daría un valor negativo son menos del 0,05 %. {ev("dato")}
Las traducciones publicadas son lineales y tienen residuo de ciclo exactamente 0. El residuo de la red al codificar y
decodificar es de {n(ci["medio"], 3)} DT de media ({ci["triangulos"]} triángulos; máximo {n(ci["max_pts"], 2)} en
pts/100 y {n(ci["max_ts"], 2)} en TS%; {ci["altos"]} por encima de 0,5 DT): se usa como salvaguarda de la ablación,
no se publica.</p>"""
    return ("Vara de destino", "Cualquier liga puede ser la vara sin mover el centro de ningún jugador", cuerpo)


# ================================================================================================== 07 estilos
def estilos(R: dict) -> tuple[str, str, str]:
    cuerpo = """<p>Los estilos de juego describen <i>cómo</i> juega un equipo o un jugador, separados de <i>cuánto</i> rinde.
El modelo de estilos (VaDE, 6 estilos con 17 rasgos: 13 de caja y 4 de jugada a jugada) se entrena con los rasgos
neutralizados por nivel, de modo que un equipo de Tercera FEB y uno de EuroLeague pueden compartir estilo. Las
iteraciones anteriores (12, 8 y 6 estilos; VaDE frente a IDEC) se conservan en el historial del modelo.</p>
<h3>Mapa unificado de jugadores y equipos</h3>
<p>El mapa 3D del Atlas proyecta jugadores y clubes con un análisis discriminante (LDA) sobre los mismos seis estilos:
Spacing, Old-School, Circulación, Pistons, Isolation y Pintura. {dato}La LDA clasifica bien el 81 % de los jugadores; el
primer eje (pintura frente a exterior) explica el 64 % de la separación, el segundo (autocreación frente a asistencia)
el 29 % y el tercero (esquina y robos) el 5 %. Los clubes se reparten así: Spacing 176, Old-School 154, Circulación 133,
Pistons 46, Isolation 36 y Pintura 17. La NCAA entra como grupo propio en la adaptación al cambio de liga.</p>
<p>{lect}El estilo entra en el simulador como encaje con el equipo de destino (distancia de Jensen-Shannon entre el
vector de estilo del jugador y el del equipo) y como complementariedad con la plantilla.</p>""".format(
        dato=ev("dato"), lect=ev("lectura"))
    return ("Estilos de juego", "Seis estilos independientes del nivel ordenan a jugadores y clubes", cuerpo)


# ================================================================================================== 08 simulador
def simulador(R: dict) -> tuple[str, str, str]:
    s31 = R["sim_v31"]
    tab = ""
    if s31:
        r = s31["resumen"]
        fil = []
        for k, nom in (("mae_min", "Error medio de minutos"), ("acierto_rol", "Acierto de rol"),
                       ("mae_pts_p100", "Error medio de pts/100"), ("mae_ts_pct", "Error medio de TS%")):
            fil.append([nom] + [n(r[x][k], 2) for x in ("v", "a", "b")])
        tab = tabla(["Medida (v3.1)", "Motor", "Atlas (a)", "Simple (b)"], fil, {1, 2, 3})
    cuerpo = f"""<p>El simulador responde a una pregunta: si este jugador ficha por este club, cuántos minutos jugará, con
qué rol y con qué producción. Quien simula elige solo jugador y club; el rol y los minutos son endógenos. Cada
iteración Monte Carlo recorre ocho pasos.</p>
<ol><li>Capacidad traducida a la liga de destino con su incertidumbre (normalización).</li>
<li>Adaptación al cambio de liga (curva por partidos, priors por grupo de origen, incluido NCAA → profesional).</li>
<li>Minutos y rol por una utilidad de Plackett-Luce sobre la plantilla, aprendida de rotaciones reales.</li>
<li>Uso con suma fija en pista y curva uso-eficiencia.</li><li>Calidad de compañeros.</li>
<li>Estilo y complementariedad.</li><li>Ruido personal y de muestreo.</li><li>Ritmo del club de destino.</li></ol>
<h3>El examen de la v3.1 marcó el camino</h3>
<p>{ev("dato")}Con 6.028 fichajes reales (2021-22 → 2024-25), el motor ganaba con claridad en minutos y rol, pero
perdía en producción frente a la lógica más simple del Atlas:</p>{tab}
<p>{ev("lectura")}Los pasos que ajustan la producción después de los minutos añadían ruido, sobre todo al TS%. La v3.2
somete cada paso a una regla de no inferioridad y deja que el examen elija entre producción del motor y del Atlas.</p>"""
    return ("Simulador", "El motor acierta minutos y rol; la producción pedía menos mecanismo", cuerpo)


# ================================================================================================== 09 simulador v3.2
def simulador_v32(R: dict) -> tuple[str, str, str]:
    s = R["sim_v32"]
    metodo = f"""<h3>Examen sin fuga</h3><p>{ev("lectura")}La normalización ajustada con todas las temporadas incluye la de
destino: con el paso aleatorio η = 0,08, la temporada t+1 pesa en el latente de t. La fuente «V32_corte» reajusta la
normalización con ≤ t en cada corte. Las cifras absolutas y la recalibración salen solo de esa fuente; las decisiones
relativas se toman con las dos y, si no coinciden, manda la que no tiene fuga.</p>
<h3>Reglas fijadas antes del examen</h3>
<ul><li><b>A1</b> (pasos del motor): no inferioridad con márgenes de +0,5 % en pts/100 y TS%, +1 % en minutos,
métricas secundarias y contribución, −0,5 pp en acierto de rol y +2 % con destino EuroLeague.</li>
<li><b>A3</b> (factores sobre el TS%): regla de 1 error típico y, dentro, la opción más simple.</li>
<li><b>A2</b> (producción del Atlas): solo si mejora de forma significativa el criterio ponderado de cinco métricas.</li>
<li><b>A4</b> (recalibración): dos colas, pesos por recencia (ρ = 0,5), contracción por grupos de destino y origen,
niveles del 50, 80 y 90 %.</li>
<li><b>Contribución</b> C = (minutos/partido ÷ minutos del partido) · pts/100, para no evaluar solo a quien juega mucho.</li></ul>"""
    if not s:
        return ("Simulador v3.2", "Resultados del simulador v3.2", metodo + _pendiente("el examen del simulador"))
    t = s["examen"]["total"]
    fil = []
    for k, nom in (("mae_min", "Error medio de minutos"), ("acierto_rol", "Acierto de rol"),
                   ("mae_pts_p100", "Error medio de pts/100"), ("mae_ts_pct", "Error medio de TS%"),
                   ("mae_C", "Error medio de la contribución C"), ("cob80_pts_p100", "Cobertura 80 % pts/100"),
                   ("cob90_min", "Cobertura 90 % minutos")):
        fil.append([nom, n(t["v3.1_motor"].get(k), 3), n(t["v3.2"].get(k), 3)])
    f = s["final"]
    dec = (f"<p>{ev('dato')}Decisión final ({'las dos fuentes coinciden' if f.get('coinciden') else 'manda la fuente sin fuga'}): "
           f"{'se quitan ' + ', '.join(f['quitar']) if f['quitar'] else 'se conservan todos los pasos'}; factores "
           f"k_β = {n(f['A3']['k_beta'], 2)} y k_c = {n(f['A3']['k_comp'], 2)}; producción del "
           f"{'Atlas' if f['produccion'] == 'atlas' else 'motor'}.</p>")
    dm = t["v3.2"].get("decision", {})
    extra = ""
    if dm.get("spearman_medio") is not None:
        extra = (f"<p>{ev('dato')}Orden de candidatos: Spearman medio entre la contribución prevista y la real por liga "
                 f"de destino × corte {rango(dm['spearman_medio'], *dm['spearman_ic90'], 2)} (IC 90 %, {dm['pools']} "
                 f"grupos). Brier de P(cuartil superior): {n(dm.get('brier'), 3)} (referencia sin modelo "
                 f"{n(dm.get('base_brier'), 3)}).</p>")
    cuerpo = metodo + f"""<h3>Resultados</h3>
{tabla(["Medida (examen sin fuga)", "Motor v3.1", "v3.2"], fil, {1, 2}, {2})}{dec}{extra}"""
    return ("Simulador v3.2", "Menos mecanismo en la producción y rangos que cubren lo que dicen", cuerpo)


# ================================================================================================== 10 B7, B9, B3, B8
def evaluaciones(R: dict) -> tuple[str, str, str]:
    b = R["b7b9"]
    res = _pendiente("la evaluación de B7 y B9")
    if b:
        b7, b9 = b["B7"]["pts_p100"], b["B9"]["pts_p100"]
        res = f"""<p>{ev("dato")}B7 (gradient boosting supervisado sobre los fichajes, cortes anidados): error de pts/100
{n(b7["mae_gbm"], 2)} frente a {n(b7["mae_motor"], 2)} del motor ({n(b7["mejora_gbm_frente_motor_%"], 1, signo=True)} %,
IC 90 % {n(b7.get("ic90_inf_%"), 1, signo=True)} a {n(b7.get("ic90_sup_%"), 1, signo=True)} %). Veredicto:
{"el límite está en la estructura del motor" if b["veredicto_B7"]["limite_en_la_estructura"] else "el límite está en el ruido, no en la estructura"}.</p>
<p>{ev("dato")}B9 (minutos y producción en un solo modelo): correlación entre el error de minutos y el de pts/100
{n(b9["correlacion_error_min_error_prod"], 2)}; cota del oráculo {n(b9["cota_mejora_%"], 1, signo=True)} %.
{"Se abre B9." if b["veredicto_B9"]["abrir_B9"] else "No compensa abrir B9."}</p>
<p>{ev("dato")}Línea base de minutos con gradient boosting: {n(b["minutos_gbm"]["mae_gbm"], 2)} frente a
{n(b["minutos_gbm"]["mae_motor"], 2)} del motor ({"el motor gana con claridad" if b["minutos_gbm"]["motor_gana_claramente"] else "sin ventaja clara del motor"}).</p>"""
    cuerpo = f"""<p>Dos ideas más ambiciosas se evaluaron sin cambiar el simulador, con umbrales fijados de antemano: un
modelo supervisado directo sobre los fichajes (B7) y un modelo conjunto de minutos y producción (B9).</p>{res}
<h3>Descartadas</h3>
<p><b>B3</b> (decodificar con la red de la liga de destino) se descartó por decisión del usuario: la red sola es peor
que la v2 y la traducción publicada sigue siendo lineal. <b>B8</b> (modelo secuencial de trayectorias, GRU o
transformer) queda como trabajo futuro: con 2-3 temporadas por jugador, su coste no se justifica hoy; con más
temporadas acumuladas, permitiría modelar la forma de la curva de desarrollo en lugar de una deriva por tramo de
edad.</p>"""
    return ("Evaluaciones", "Lo que no se aplica también se mide, con umbrales fijados antes", cuerpo)


# ================================================================================================== 11 límites
def limites(R: dict) -> tuple[str, str, str]:
    cuerpo = f"""<ul>
<li>{ev("lectura")}<b>Examen limpio pendiente.</b> Los cortes 2023 y 2024 ya se habían mirado; las cifras son
orientativas hasta el examen 2025-26 → 2026-27, prerregistrado con las huellas SHA-256 de las configuraciones.</li>
<li>{ev("dato")}<b>Cobertura desigual de jugada a jugada.</b> NCAA sin cambios de quinteto hasta 2023-24; CBA sin
coordenadas de tiro y con quintetos del 61-93 %; VTB sin jugada a jugada antes de marzo de 2022.</li>
<li>{ev("hipotesis")}<b>Identidad de los puentes.</b> Una fusión errónea mueve niveles enteros. La auditoría de 100
puentes exige una precisión con cota inferior de Clopper-Pearson ≥ 0,95; si no se cumple, se sube el umbral de fusión
a 0,85.</li>
<li>{ev("lectura")}<b>Fuga en los pesos del simulador.</b> La fuente sin fuga reajusta la normalización por corte, pero
los pesos de utilidad y calibración se aprenden con la fuente completa.</li>
<li>{ev("lectura")}<b>Rol ordinal (C1)</b> y <b>B8</b> quedan como trabajo futuro.</li></ul>"""
    return ("Límites", "Dónde termina lo que sabemos", cuerpo)


# ================================================================================================== 12 reproducibilidad
def reproducibilidad(R: dict) -> tuple[str, str, str]:
    cuerpo = """<div class="eq">scripts/actualizar_20ligas.sh        datos de las 20 ligas y capas v2/v3.1
scripts/actualizar_v32.sh            normalización v3.2 + simulador v3.2 (reanudable)
python -m bbnorm3 --config configs/normalization_v32.yaml ablacion | validar-v32 | ajustar-combinada | destino
CERNO_SIMULADOR=v32 python -m bbfit backtest --fuente V32_corte … | v32-decidir | b7-b9 | v32-aplicar
python -m bbmodel auditoria-puentes [--evaluar]
python -m cerno_articulo              este documento</div>
<p>Todas las semillas son fijas. La v3.1 (configs/normalization_v31.yaml, data/modelos/v3_1,
data/modelos/simulador/v3_1) no cambia: la v3.2 vive en sus propias carpetas.</p>"""
    return ("Reproducibilidad", "Todo se reconstruye con dos órdenes y semillas fijas", cuerpo)


def todas(R: dict) -> list[tuple[str, str, str]]:
    return [resumen(R), datos_seccion(R), normalizacion_previa(R), metodo_v32(R), resultados_v32(R), vara_destino(R),
            estilos(R), simulador(R), simulador_v32(R), evaluaciones(R), limites(R), reproducibilidad(R)]
