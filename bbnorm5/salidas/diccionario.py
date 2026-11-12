"""F9 · Diccionario de columnas de las salidas v5 y glosario ES/EN de los términos nuevos (encargo §13).

Ficheros hermanos de los existentes (no se tocan `diccionario_columnas.json` ni `docs/glosario.md`):
`data/v5/salidas/diccionario_columnas_v5.json` y `data/v5/salidas/glosario_v5.json`. Mismos campos que el diccionario
vigente (`columna`, `grupo`, `origen`, `descripcion`) más `descripcion_en`, `unidades` y `fichero`.
"""
from __future__ import annotations

from bbnorm5 import config as C
from bbnorm5.salidas import formato_v32 as F

DIR = C.DIR_DATOS / "salidas"
ORIGEN = "normalización v5"


def _c(columna, grupo, es, en, unidades="", fichero="destinos.parquet"):
    return {"columna": columna, "grupo": grupo, "origen": ORIGEN, "descripcion": es, "descripcion_en": en,
            "unidades": unidades, "fichero": fichero}


def columnas_destinos() -> list[dict]:
    t = "tasa de la métrica (fracción por oportunidad)"
    out = [
        _c("persona_v5", "identidad", "Persona de la v5 (P + 6 dígitos)", "v5 person id"),
        _c("metrica", "identidad", "Métrica (14 de la v5)", "Metric (14 in v5)"),
        _c("temporada_objetivo", "identidad", "Temporada proyectada", "Projected season"),
        _c("liga_origen", "origen", "Liga de su última temporada", "League of the last season played"),
        _c("temporada_ult", "origen", "Última temporada observada", "Last observed season"),
        _c("rol_ult", "origen", "Rol de la última temporada (E exterior, A mixto, I interior, X sin roles)",
           "Last season's role (E perimeter, A hybrid, I interior, X no roles)"),
        _c("edad", "origen", "Edad en la temporada proyectada", "Age in the projected season", "años"),
        _c("temporadas_hist", "origen", "Temporadas de historial usadas", "Seasons of history used"),
        _c("N_ult", "origen", "Oportunidades de la última temporada", "Opportunities in the last season"),
        _c("liga_destino", "destino", "Liga de destino supuesta", "Assumed destination league"),
        _c("cambio_liga", "destino", "1 si la liga de destino no es la de origen", "1 if destination differs from origin"),
    ]
    for q, n in (("q10", "10"), ("q25", "25"), ("q50", "50 (mediana)"), ("q75", "75"), ("q90", "90")):
        out.append(_c(f"nivel_{q}", "nivel",
                      f"**Nivel** en la liga de destino: percentil {n} de la capacidad persistente (sin ruido de temporada)",
                      f"**Level** in the destination league: {n.replace(' (mediana)', ' (median)')}th percentile of "
                      "persistent ability (no season noise)", t))
    out.append(_c("nivel_media", "nivel", "Media del nivel", "Mean level", t))
    for q, n in (("q2_5", "2,5"), ("q10", "10"), ("q25", "25"), ("q50", "50 (mediana)"), ("q75", "75"), ("q90", "90"),
                 ("q97_5", "97,5")):
        out.append(_c(f"pred_{q}", "predictivo",
                      f"**Predictivo** de la temporada objetivo: percentil {n} de lo que registrará (con ruido de temporada y de "
                      "muestreo, rol y minutos desconocidos; recalibrado por métrica y grupo de ligas)",
                      f"**Predictive** for the target season: {n.replace(',', '.').replace(' (mediana)', ' (median)')}th "
                      "percentile of what will be recorded (season and sampling noise, unknown role and minutes; "
                      "recalibrated by metric and league group)", t))
    out += [
        _c("pred_media", "predictivo", "Media del predictivo", "Mean of the predictive", t),
        _c("factor_recal_grupo", "predictivo", "Factor de anchura del predictivo (métrica × grupo de ligas, corte anterior)",
           "Predictive width factor (metric × league group, previous season)"),
        _c("traduccion_media", "traduccion", "**Traducción** λ_destino − λ_origen (media), escala del enlace",
           "**Translation** λ_destination − λ_origin (mean), link scale", "logit / log / identidad"),
        _c("traduccion_dt", "traduccion", "DT de la traducción", "SD of the translation", "escala del enlace"),
        _c("traduccion_q10", "traduccion", "Percentil 10 de la traducción", "10th percentile of the translation", "escala del enlace"),
        _c("traduccion_q90", "traduccion", "Percentil 90 de la traducción", "90th percentile of the translation", "escala del enlace"),
        _c("traduccion_efecto_nivel", "traduccion",
           "Efecto del cambio en la mediana del nivel frente a quedarse en su liga (incluye tipo de jugador y compañeros)",
           "Effect of the move on the median level versus staying (includes player type and team-mates)", t),
    ]
    for u in (25, 50, 75):
        out.append(_c(f"umbral_p{u}", "umbral", f"Umbral: percentil {u} de la tasa observada en la liga de destino × rol "
                      "(≥ 300 min, tres temporadas anteriores)",
                      f"Threshold: {u}th percentile of the observed rate in destination league × role "
                      "(≥ 300 min, previous three seasons)", t))
        out.append(_c(f"p_supera_p{u}", "umbral", f"**Probabilidad de umbral** P(nivel > percentil {u})",
                      f"**Threshold probability** P(level > {u}th percentile)", "probabilidad"))
    out += [
        _c("umbral_referencia", "umbral", "Rol cuyos percentiles se usan (o «todos» si la liga no tiene ese rol)",
           "Role whose percentiles are used ('todos' if the league lacks that role)"),
        _c("p_rol_E", "rol", "Probabilidad de jugar de exterior en la liga de destino", "Probability of a perimeter role", "probabilidad"),
        _c("p_rol_A", "rol", "Probabilidad de rol mixto", "Probability of a hybrid role", "probabilidad"),
        _c("p_rol_I", "rol", "Probabilidad de rol interior", "Probability of an interior role", "probabilidad"),
        _c("p_rol_X", "rol", "Probabilidad de liga sin reparto de roles", "Probability of a league without roles", "probabilidad"),
        _c("exposicion_acumulada", "sello", "Oportunidades acumuladas en todo el historial", "Cumulative opportunities"),
        _c("exposicion_relativa", "sello", "Exposición acumulada / punto de estabilización n* de la métrica",
           "Cumulative exposure / stabilisation point n* of the metric"),
        _c("conectividad", "sello", "DT de la traducción en DT de λ entre ligas (0 si no cambia de liga)",
           "Translation SD in units of the between-league SD of λ (0 if no move)"),
        _c("sello", "sello", "**Sello de fiabilidad**: alta, media o baja (regla en el glosario)",
           "**Reliability seal**: high, medium or low (rule in the glossary)"),
    ]
    return out


def columnas_formato_v32(excluir: tuple = ()) -> list[dict]:
    out = []
    for m5, m3 in F.A_V32.items():
        if m5 in excluir:
            continue
        f = "formato_v32/normalizado/<temporada>.csv.gz"
        u = "unidades de la v3.2"
        if m5 != "pf_p40":
            out += [
                _c(m3, "v5", f"{m3}: **nivel v5** de la temporada en su liga (mediana) si `fuente_{m3}` = V5; si no, la v3.2",
                   f"{m3}: **v5 level** of the season in own league (median) if source is V5; otherwise v3.2", u, f),
                _c(f"{m3}_lo", "v5", "Extremo inferior del intervalo del 80 % del nivel", "Lower end of the 80% level interval", u, f),
                _c(f"{m3}_hi", "v5", "Extremo superior del intervalo del 80 % del nivel", "Upper end of the 80% level interval", u, f),
                _c(f"{m3}_pctel", "v5", "Percentil del nivel en su liga y temporada", "Percentile of the level in league and season", "0–100", f),
                _c(f"{m3}_v32", "v3.2", "Valor publicado por la v3.2 (conservado)", "Value published by v3.2 (kept)", u, f),
                _c(f"{m3}_v32_lo", "v3.2", "Extremo inferior de la v3.2", "v3.2 lower end", u, f),
                _c(f"{m3}_v32_hi", "v3.2", "Extremo superior de la v3.2", "v3.2 upper end", u, f),
            ]
        else:
            out += [_c(m3, "v5", "Faltas personales por 40 minutos: nivel v5 (no es la PF/100 de la v3.2)",
                       "Personal fouls per 40 minutes: v5 level (not v3.2's PF/100)", "por 40 min", f),
                    _c(f"{m3}_lo", "v5", "Extremo inferior del 80 %", "Lower end of 80%", "por 40 min", f),
                    _c(f"{m3}_hi", "v5", "Extremo superior del 80 %", "Upper end of 80%", "por 40 min", f),
                    _c(f"{m3}_pctel", "v5", "Percentil en su liga", "Percentile in league", "0–100", f)]
        out += [_c(f"{m3}_lo50", "v5", "Extremo inferior del intervalo del 50 % del nivel", "Lower end of the 50% level interval", u, f),
                _c(f"{m3}_hi50", "v5", "Extremo superior del intervalo del 50 % del nivel", "Upper end of the 50% level interval", u, f),
                _c(f"{m3}_obs_v5", "v5", "Observado de la temporada según la v5", "Season observed value per v5", u, f),
                _c(f"fuente_{m3}", "v5", "V5 si la fila tiene nivel v5; V3.2 si no", "V5 if the row has a v5 level; V3.2 otherwise", "", f)]
        g = "formato_v32/destinos/<temporada>/<liga>.csv.gz"
        out += [_c(f"{m3}_nivel", "destino", "Nivel en la liga de destino (mediana)", "Level in destination league (median)", u, g),
                _c(f"{m3}_nivel_lo", "destino", "Nivel: percentil 10", "Level: 10th percentile", u, g),
                _c(f"{m3}_nivel_hi", "destino", "Nivel: percentil 90", "Level: 90th percentile", u, g),
                _c(f"{m3}_pred", "destino", "Predictivo de la temporada objetivo (mediana)", "Target-season predictive (median)", u, g),
                _c(f"{m3}_pred_lo", "destino", "Predictivo: percentil 10", "Predictive: 10th percentile", u, g),
                _c(f"{m3}_pred_hi", "destino", "Predictivo: percentil 90", "Predictive: 90th percentile", u, g),
                _c(f"{m3}_p_supera_p50", "destino", "P(nivel > mediana de la liga de destino × rol)",
                   "P(level > median of destination league × role)", "probabilidad", g),
                _c(f"{m3}_sello", "destino", "Sello de fiabilidad", "Reliability seal", "", g)]
    # F9 bis: derivadas (TS%, eFG% y variantes por 100 posesiones), mismas columnas que las demás
    f = "formato_v32/normalizado/<temporada>.csv.gz"
    g = "formato_v32/destinos/<temporada>/<liga>.csv.gz"
    deriv = {"efg_pct": ("eFG% derivado de T2%, T3% y 3PAr de la v5 (draws conjuntos con la correlación de la F5)",
                         "eFG% derived from v5 T2%, T3% and 3PAr (joint draws with the F5 correlation)"),
             "ts_pct": ("TS% derivado de T2%, T3%, TL%, 3PAr y FTr de la v5 (draws conjuntos)",
                        "TS% derived from v5 T2%, T3%, FT%, 3PAr and FTr (joint draws)"),
             "oreb_p100": ("OREB/100 = OREB% de la v5 × rebotes disponibles por posesión de la liga × 100",
                           "OREB/100 = v5 OREB% × league rebound chances per possession × 100"),
             "dreb_p100": ("DREB/100 = DREB% de la v5 × rebotes disponibles por posesión de la liga × 100",
                           "DREB/100 = v5 DREB% × league rebound chances per possession × 100"),
             "blk_p100": ("BLK/100 = BLK% de la v5 × tiros de dos del rival por posesión de la liga × 100",
                          "BLK/100 = v5 BLK% × league opponent 2PA per possession × 100"),
             "stl_pct": ("STL% = robos por posesión del rival de la v5 × 100", "STL% = v5 steals per opponent possession × 100"),
             "pf_p100": ("PF/100 = faltas por minuto de la v5 × minutos por posesión de la liga × 100",
                         "PF/100 = v5 fouls per minute × league minutes per possession × 100")}
    for m3, (es, en) in deriv.items():
        out += [_c(m3, "v5 derivada", es + "; si `fuente` = V5", en + "; if source is V5", "unidades de la v3.2", f),
                _c(f"{m3}_v32", "v3.2", "Valor publicado por la v3.2 (conservado)", "Value published by v3.2 (kept)", "", f),
                _c(f"fuente_{m3}", "v5 derivada", "V5 si la fila tiene la derivada de la v5", "V5 if derived from v5", "", f),
                _c(f"{m3}_nivel", "destino", es + " (nivel en la liga de destino, mediana)", en + " (destination level)", "", g)]
    out.append(_c("fuente_norm", "v5", "V5+V3.2 si alguna métrica viene de la v5", "V5+V3.2 if any metric comes from v5", "",
                  "formato_v32/normalizado/<temporada>.csv.gz"))
    return out


def _n(x) -> str:
    """Número en formato español (coma decimal)."""
    return f"{x:g}".replace(".", ",")


def glosario(cfg: dict) -> list[dict]:
    s = cfg["sello"]
    return [
        {"termino": "nivel", "term": "level",
         "es": "Capacidad persistente del jugador en una liga y temporada, sin el ruido de la temporada ni el del muestreo. "
               "Es lo que el jugador «es»; su intervalo se estrecha con el historial.",
         "en": "The player's persistent ability in a league and season, without season or sampling noise. What the "
               "player 'is'; its interval narrows with history."},
        {"termino": "predictivo", "term": "predictive",
         "es": "Lo que el jugador registrará en la temporada siguiente: el nivel más el ruido de la temporada (rachas, "
               "minutos, rol) y del muestreo. Es más ancho que el nivel y no se estrecha mucho con más datos.",
         "en": "What the player will record next season: the level plus season noise (streaks, minutes, role) and "
               "sampling noise. Wider than the level and it does not narrow much with more data."},
        {"termino": "traducción", "term": "translation",
         "es": "Diferencia de dificultad entre dos ligas para una métrica, λ_destino − λ_origen, con su incertidumbre. "
               "Se estima con los puentes de la misma temporada y los traspasos entre temporadas.",
         "en": "Difficulty difference between two leagues for a metric, λ_destination − λ_origin, with its "
               "uncertainty. Estimated from same-season bridges and between-season transfers."},
        {"termino": "probabilidad de umbral", "term": "threshold probability",
         "es": "Probabilidad de que el nivel en la liga de destino supere el percentil 25, 50 o 75 de los jugadores de "
               "esa liga y su rol (≥ 300 min, tres temporadas anteriores).",
         "en": "Probability that the level in the destination league exceeds the 25th, 50th or 75th percentile of "
               "players in that league and role (≥ 300 min, previous three seasons)."},
        {"termino": "sello de fiabilidad", "term": "reliability seal",
         "es": f"Alta, media o baja. **Alta**: exposición acumulada ≥ {_n(s['alta_exposicion'])} veces el punto de "
               f"estabilización de la métrica, ≥ {s['alta_temporadas']} temporadas de historial y DT de la traducción "
               f"≤ {_n(s['alta_conectividad'])} DT de λ entre ligas (0 si sigue en su liga). **Baja**: exposición "
               f"< {_n(s['baja_exposicion'])} vez el punto de estabilización o DT de la traducción > "
               f"{_n(s['baja_conectividad'])} DT de λ entre ligas. **Media**: el resto.",
         "en": f"High, medium or low. **High**: cumulative exposure ≥ {s['alta_exposicion']:g} × the metric's "
               f"stabilisation point, ≥ {s['alta_temporadas']} seasons of history and translation SD ≤ "
               f"{s['alta_conectividad']:g} between-league SDs of λ (0 if staying). **Low**: exposure < "
               f"{s['baja_exposicion']:g} × the stabilisation point or translation SD > {s['baja_conectividad']:g} "
               "between-league SDs. **Medium**: otherwise."},
        {"termino": "punto de estabilización", "term": "stabilisation point",
         "es": "Oportunidades (tiros, posesiones, minutos…) con las que una temporada mide la métrica con fiabilidad 0,5.",
         "en": "Opportunities (shots, possessions, minutes…) at which one season measures the metric with reliability 0.5."},
        {"termino": "puente intra-temporada", "term": "same-season bridge",
         "es": "Jugador que juega en dos competiciones la misma temporada (p. ej. su liga y una competición europea). "
               "Compara las dos ligas sin que el jugador haya cambiado.",
         "en": "Player who plays in two competitions in the same season (e.g. domestic league and a European cup). "
               "Compares the two leagues while the player is unchanged."},
        {"termino": "métrica derivada", "term": "derived metric",
         "es": "Métrica de la v3.2 que la v5 no mide directamente y calcula desde las suyas: TS% y eFG% con draws conjuntos "
               "de T2%, T3%, TL%, 3PAr y FTr (correlación de la capa latente); OREB/100, DREB/100, BLK/100, STL% y PF/100 "
               "convirtiendo la tasa de la v5 con las oportunidades por posesión de la liga.",
         "en": "A v3.2 metric that v5 does not measure directly and computes from its own: TS% and eFG% from joint draws "
               "of 2P%, 3P%, FT%, 3PAr and FTr (latent-layer correlation); OREB/100, DREB/100, BLK/100, STL% and PF/100 "
               "by converting the v5 rate with the league's opportunities per possession."},
        {"termino": "ex ante", "term": "ex ante",
         "es": "Lo que se sabe al fichar: rol, minutos y oportunidades de la temporada siguiente desconocidos. Es la "
               "proyección por defecto; la que fija rol y minutos es un escenario.",
         "en": "What is known when signing: next season's role, minutes and opportunities unknown. The default "
               "projection; fixing role and minutes is a scenario."},
    ]


def generar(cfg: dict) -> dict:
    d = columnas_destinos() + columnas_formato_v32(tuple(cfg.get("publicar_con_v32", [])))
    C.escribir_json(d, DIR / "diccionario_columnas_v5.json")
    g = glosario(cfg)
    C.escribir_json(g, DIR / "glosario_v5.json")
    return {"columnas": len(d), "terminos": len(g)}
