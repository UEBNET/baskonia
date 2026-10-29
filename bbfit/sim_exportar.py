"""Fase 8 — exportación del simulador v2 para el navegador (Atlas: «Simular fichajes» y «Simular equipo completo»).

Decisión: el MOTOR se ejecuta en el navegador (port en JavaScript de bbfit.simulador.simular en artifact/atlas/index.html)
con insumos precalculados, en vez de resultados precalculados por pareja jugador × club:
  * el usuario puede elegir cualquier jugador × cualquier club y marcar bajas o añadir varios fichajes (escenario de
    plantilla), lo que haría inabarcable precalcular todas las combinaciones (≈ 20.000 jugadores × 900 clubes);
  * la simulación de un fichaje son ~600 iteraciones de Plackett-Luce sobre ~15 jugadores: milisegundos en JS;
  * los insumos caben de sobra en el límite (< 40 MB; ≈ 10 MB en claro, ≈ 3 MB comprimidos).
La paridad Python ↔ JS se comprueba con Playwright (medias de minutos, roles y producción dentro del error Monte Carlo).

Ficheros (data/artifact/simulador/, publicados en atlas/simulador/):
  meta.json       versión, configuración, pesos (utilidad, calibración, Fit), constantes de traducción por temporada base
                  y liga, referencias de liga, tendencias de entrenador, priors de adaptación, estilos unificados
  jugadores.json  insumos de cada registro jugador-equipo-temporada (θ y su sd por métrica, L, rol, uso, σ, estilo…)
  clubes.json     club de destino × temporada: plantilla (registros, presencia, minutos previos en el club),
                  entrenador (rotación y curva), ritmo y estilo del equipo

    python -m bbfit exportar-simulador [--salida data/artifact/simulador]
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from . import sim_insumos as SI
from . import simulador as S
from .config import DIR_CONFIGS, DIR_MOD, RAIZ, cargar

SALIDA = RAIZ / "data" / "artifact" / "simulador"
METS = ["pts_p100", "ts_pct", "usg_pct", "ast_pct", "oreb_p100", "dreb_p100", "stl_p100", "blk_p100", "tov_pct", "rapm"]


def _r(x, d=4):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(x) else round(x, d)


def _isos(nac) -> str | None:
    from .adaptacion import _isos as iso
    v = iso(nac)
    return "/".join(v) if v else None


def _registros(c: S.Corte, filas: pd.DataFrame) -> list[list]:
    from bbmodel.nacionalidad import id_modelo
    ids = SI.estilos_ids()
    f = filas.copy()
    f["pid"] = id_modelo(f["liga"], f["player_id"].astype(str), f["nombre"].fillna(""))
    out = []
    for r in f.to_dict("records"):
        r["persona_id"] = r["persona_id"]
        ctx = S._ctx_origen(c, r)
        hr = r.get("H_rol_post") if np.isfinite(S._f(r.get("H_rol_post"))) else r.get("H_rol")
        out.append([f"{r['liga']}|{r['temporada']}|{r['player_id']}", str(r["pid"]), str(r["persona_id"]), r.get("nombre"),
                    r["liga"], r["temporada"], str(r["team_id"]), r.get("club"),
                    r.get("pos3") if isinstance(r.get("pos3"), str) else None, _r(r.get("edad"), 1), _isos(r.get("nacionalidad")),
                    _r(r.get("gp"), 0), _r(r.get("min_total"), 0), _r(r.get("min_pct"), 4), _r(r.get("gs_pct"), 3),
                    r.get("rol_mas_probable") if isinstance(r.get("rol_mas_probable"), str) else None,
                    _r(r.get("L"), 3), _r(r.get("L_sd"), 3), _r(S._k_nivel(r), 3), _r(ctx, 3),
                    _r(r.get("usg_pct_obs"), 2), _r(r.get("ast_pct_obs"), 2), _r(r.get("gti"), 2), _r(r.get("sigma"), 2),
                    _r(hr, 3), [_r(r.get(f"eu_{i}"), 3) for i in ids],
                    [_r(r.get(f"{m}_th"), 3) for m in METS], [_r(r.get(f"{m}_thsd"), 3) for m in METS]])
    return out


COLS_JUG = ["id", "pid", "persona", "nombre", "liga", "temporada", "team", "club", "pos3", "edad", "nac", "gp", "min_total",
            "min_pct", "gs_pct", "rol", "L", "L_sd", "kL", "ctx", "usg", "ast", "gti", "sigma", "hrol", "eu", "th", "sd"]


def _constantes_base(c: S.Corte, ligas: list[str]) -> dict:
    const, nodos = c.trad["constantes"], c.trad["nodos"]
    out = {}
    for liga in ligas:
        d = {"metricas": {}, "ref": {"uso": list(c.ref["uso"].get(liga, (20.0, 5.0))),
                                     "banquillo": _r(c.ref["banquillo"].get(liga)), "pos": c.ref["pos"].get(liga),
                                     "sigma": _r(c.ref["sigma"].get(liga)), "sigma_p80": _r(c.ref["sigma_p80"].get(liga)),
                                     "ritmo": _r(c.ref["ritmo"].get(liga))},
             "min_residual": _r(c.mod["min_rol"].get((liga, "RESIDUAL"), c.mod["min_rol_global"].get("RESIDUAL", 0.06))),
             "min_rol": {r: _r(c.mod["min_rol"].get((liga, r), c.mod["min_rol_global"].get(r)), 4)
                         for r in ["RESIDUAL", "PROFUNDIDAD", "ROTACION", "TITULAR", "GO_TO_GUY"]},
             "tendencia": list(_tend(c, None, liga)), "nivel": _r(S._nivel_liga(c, liga))}
        for m in METS:
            k = const.get(m)
            if k is None or liga not in k["s"]:
                continue
            dl, vd = SI._nodo(nodos.get(m, {}), liga, c.temp)
            if not np.isfinite(dl):
                dl, vd = k["m"].get(liga, 0.0), 0.05
            mu = {p: _r(SI.entorno(k, liga, c.temp, p)[0], 5) for p in "EAI"}
            tau = {p: _r(SI.entorno(k, liga, c.temp, p)[1], 5) for p in "EAI"}
            d["metricas"][m] = {"s": _r(k["s"][liga], 5), "psi": _r(k["psi"].get(liga, 0.0), 5),
                                "sigma2": _r(k["sigma2"].get(liga, k["sigma2"].get("todas")), 6), "nodo": [_r(dl, 5), _r(vd, 6)],
                                "mu": mu, "tau": tau}
        out[liga] = d
    return out


def _tend(c: S.Corte, ent, liga):
    c0 = dict(c.calib)
    c.calib = {}
    r, sd, curva = S.tendencia(c, ent, liga)
    c.calib = c0
    return [_r(r, 3), _r(sd, 3), [_r(x, 5) for x in curva]]


def _priors() -> dict | None:
    from . import adaptacion as AD
    t = AD.cargar_priors()
    if t is None:
        return None
    t = t[t["metrica"].isin(["pts_p100", "ts_pct", "usg_pct", "ast_pct", "reb_p100", "L", "L_rel"])]
    cols = ["nivel", "liga_origen", "liga_destino", "grupo_nacionalidad", "pos3", "escalon_destino", "metrica", "n",
            "delta_media", "delta_sd", "kappa_media", "kappa_sd"] + S.PRIOR_EXTRA
    t = t[cols]
    return {"columnas": cols, "filas": [[(_r(v, 5) if isinstance(v, (float, np.floating)) else (int(v) if isinstance(v, (int, np.integer)) else v))
                                         for v in fila] for fila in t.itertuples(index=False)]}


def _clubes(c: S.Corte, temp_dest: str, roles: pd.DataFrame, cfg: dict) -> tuple[list[dict], set]:
    """Clubes de destino de temp_dest con su plantilla (registros de la temporada base c.temp)."""
    from . import validacion as V
    ids = SI.estilos_ids()
    r1 = roles[roles["temporada"] == temp_dest]
    mapa = V.mapa_clubes(roles, c.temp, temp_dest) if len(r1) else {}
    eq_dest = []
    if len(r1):
        eq1 = SI._equipo_ligas(temp_dest)
        k1 = eq1.set_index(["liga", "team_id"])
        for (liga, team), g in r1.groupby(["liga", "team_id"]):
            row = k1.loc[(liga, team)] if (liga, team) in k1.index else None
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            cod = row.get("equipo_codigo") if row is not None else None
            club1 = f"{liga}|{cod}" if liga.startswith("feb") and isinstance(cod, str) else f"{liga}|{team}"
            eq_dest.append((liga, team, row.get("equipo") if row is not None else team, club1,
                            [(p, 1.0) for p in g.sort_values("min_total", ascending=False)["persona_id"]],
                            f"plantilla {temp_dest} (jugadores que ya han jugado)"))
    vistos = {(x[0], x[1]) for x in eq_dest}
    # competiciones sin datos de temp_dest (temporada sin empezar): plantilla de la temporada base
    con_dest = set(r1["liga"].unique())
    for e in c.eq.itertuples(index=False):
        if e.liga in con_dest or (e.liga, e.team_id) in vistos:
            continue
        eq_dest.append((e.liga, e.team_id, e.equipo, e.club, S.miembros_actuales(c, e.club),
                        f"plantilla {c.temp} (sin datos de {temp_dest})"))
    out, usados = [], set()
    for liga, team, nombre, club1, miembros, esc in eq_dest:
        club_t = V.club_en_t(c, liga, team, club1, mapa)
        et = c.eq[c.eq["club"] == club_t].iloc[0] if club_t is not None and (c.eq["club"] == club_t).any() else None
        e1 = None
        ent = None
        if len(r1):
            x = r1[(r1["liga"] == liga) & (r1["team_id"] == team)]
            if x["entrenador_id"].notna().any():
                ent = x["entrenador_id"].dropna().mode().iat[0]
        if ent is None and et is not None and isinstance(et.get("entrenador"), str):
            ent = et["entrenador"]
        pl = []
        rc = c.por_club.get(club_t) if club_t else None
        for p, pres in miembros:
            if p not in c.prin.index:
                pl.append([None, _r(pres, 3), None, p])
                continue
            r = c.prin.loc[p]
            rid = f"{r['liga']}|{r['temporada']}|{r['player_id']}"
            lmc = None
            if rc is not None:
                xx = rc[rc["persona_id"] == p]
                if len(xx):
                    lmc = _r(float(S._logit(S._f(xx.sort_values("min_total").iloc[-1]["min_pct"]))), 3)
            pl.append([rid, _r(pres, 3), lmc, p])
            usados.add(p)
        out.append({"liga": liga, "team": str(team), "nombre": nombre, "temporada": temp_dest, "base": c.temp,
                    "club_t": club_t, "escenario": esc, "entrenador": ent, "tendencia": _tend(c, ent, liga),
                    "ritmo": _r(et.get("team_pace")) if et is not None else None,
                    "eu": et.get("eu") if et is not None and isinstance(et.get("eu"), str) else None,
                    "eu_probs": [_r(et.get(f"eu_{i}"), 3) for i in ids] if et is not None else None,
                    "plantilla": pl})
    return out, usados


def exportar(salida: str | Path = SALIDA) -> dict:
    cfg = cargar("simulation")
    ex = cfg["exportar"]
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    roles = SI._leer_roles_temporada()
    P = json.loads((S.DIR_SIM / "pesos.json").read_text(encoding="utf-8")) if (S.DIR_SIM / "pesos.json").exists() else {}
    bases = {SI.siguiente(t): t for t in ex["temporadas_base"]}       # destino → base
    meta_bases, clubes, filas_jug, usados_por_base = {}, [], [], {}
    ligas_todas = set()
    for dest, base in bases.items():
        c = S.cargar_corte(base)
        clubs, usados = _clubes(c, dest, roles, cfg)
        clubes += clubs
        ligas = sorted(set(c.reg["liga"]) | {x["liga"] for x in clubs})
        ligas_todas |= set(ligas)
        meta_bases[base] = {"destino": dest, "ligas": _constantes_base(c, ligas),
                            "estilo_objetivo": {k: [_r(x, 4) for x in v] for k, v in c.ref["estilo_objetivo"].items()},
                            "entrenadores": {}}
        for cl in clubs:
            if cl["entrenador"]:
                meta_bases[base]["entrenadores"][cl["entrenador"]] = cl["tendencia"]
        # registros de la temporada base: candidatos (≥ min minutos) y miembros de alguna plantilla
        r = c.reg[(c.reg["min_total"] >= ex["minimo_minutos_jugador"]) | (c.reg["principal"] & c.reg["persona_id"].isin(usados))]
        filas_jug += _registros(c, r)
    # registros de la temporada en curso como candidatos (provisionales)
    for t in ex.get("temporadas_candidatas_extra", []):
        c = S.cargar_corte(t)
        r = c.reg[c.reg["min_total"] >= ex["minimo_minutos_jugador"]]
        filas_jug += _registros(c, r)
    vistos, jug = set(), []
    for f in filas_jug:
        if f[0] in vistos:
            continue
        vistos.add(f[0])
        jug.append(f)
    st = yaml.safe_load((DIR_CONFIGS / "styles.yaml").read_text(encoding="utf-8"))
    doc = json.loads((DIR_MOD / "estilos_unificados" / "estilos.json").read_text(encoding="utf-8"))
    estilos = [{"id": e["id"], "nombre": st["estilos"][e["id"]]["nombre"], "color": st["estilos"][e["id"]]["color"],
                "rol_jugador": st["estilos"][e["id"]].get("rol_jugador"), "jugador": st["estilos"][e["id"]].get("jugador"),
                "equipo": st["estilos"][e["id"]].get("equipo")} for e in doc["estilos"]]
    ad = cargar("adaptacion")
    rcfg = cargar("roles")
    from .roles import umbrales_pct
    c0 = S.cargar_corte(ex["temporada_base"])
    const = c0.trad["constantes"]
    meta = {"generado": date.today().isoformat(), "version": cfg["version"], "semilla": cfg["semilla"],
            "n_sim": int(ex.get("simulaciones_navegador", 600)), "intervalos": cfg["intervalos"],
            "metricas": METS, "transf": {m: const[m]["transf"] for m in METS if m in const},
            "exposicion": {m: const[m]["exposicion"] for m in METS if m in const},
            "deriva": {m: const[m]["deriva"] for m in METS if m in const},
            "roles": ["RESIDUAL", "PROFUNDIDAD", "ROTACION", "TITULAR", "GO_TO_GUY"],
            "roles_umbral": umbrales_pct(rcfg), "roles_solape": {"gs": rcfg["roles"]["gs_pct_solape"]},
            "min_partido": rcfg["partido"]["minutos_reglamentarios"],
            "asignacion": {k: cargar("reemplazo")["asignacion"][k] for k in ("max_min_partido", "min_por_pos3")},
            "go_to_guy": cfg["rol_go_to_guy"], "produccion": cfg["produccion"], "plantilla": cfg["plantilla"],
            "utilidad_rasgos": S.RASGOS_UTIL, "utilidad": P.get("utilidad", cfg["utilidad"]["inicial"]),
            "calibracion": P.get("calibracion", {}), "fit": P.get("fit"), "componentes": S.COMPONENTES,
            "calibracion_salida": P.get("calibracion_salida"),
            "beta_uso": {k: list(v) for k, v in c0.mod["beta_uso"].items()},
            "companeros_ts": list(c0.mod["companeros"].get("ts_pct", (0.0, 0.0))),
            "adaptacion": {"partidos": cfg["adaptacion"]["partidos_temporada"], "primeros": cfg["adaptacion"]["primeros_partidos"],
                           "contraccion": cfg["adaptacion"]["contraccion"],
                           "priors": _priors(), "n_min": ad["priors"]["n_min_celda"],
                           "defecto": [0.0, ad["priors"]["delta_sd_defecto"], ad["priors"]["kappa_defecto"], ad["priors"]["kappa_sd_defecto"]],
                           "paises_liga": ad["paises_liga"], "paises_europeos": ad["paises_europeos"],
                           "escalones": cargar("normalization").get("escalones")},
            "avisos": cfg["avisos"], "estilos": estilos, "bases": meta_bases,
            "validacion": P.get("validacion_resumen"),
            "nota": "Motor en el navegador: port de bbfit.simulador.simular (docs/checkpoints/F8.md)."}
    jcols = {"columnas": COLS_JUG, "filas": jug}
    cl = {"columnas": list(clubes[0].keys()) if clubes else [], "filas": [list(x.values()) for x in clubes]}
    tam = {}
    for nombre, obj in (("meta.json", meta), ("jugadores.json", jcols), ("clubes.json", cl)):
        p = salida / nombre
        txt = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=_r)
        txt = re.sub(r"(?<=[,\[:])-?(?:NaN|Infinity)(?=[,\]}])", "null", txt)     # JSON válido para el navegador
        p.write_text(txt, encoding="utf-8")
        tam[nombre] = p.stat().st_size
    total = sum(tam.values()) / 1e6
    if total > float(ex["max_mb"]):
        raise RuntimeError(f"exportación de {total:.1f} MB > {ex['max_mb']} MB")
    print(f"simulador v2 exportado en {salida}: {len(jug)} registros, {len(clubes)} clubes · "
          + ", ".join(f"{k} {v / 1e6:.1f} MB" for k, v in tam.items()))
    return {"registros": len(jug), "clubes": len(clubes), "mb": round(total, 2)}


def paridad(carpeta: str | Path = SALIDA, n: int = 6, n_sim: int = 3000, semilla: int = 11) -> list[dict]:
    """Casos de referencia (Python) para comparar con el motor JS: n fichajes al azar (registro de la temporada base)
    a clubes de destino exportados. → <carpeta>/paridad.json"""
    carpeta = Path(carpeta)
    cl = json.loads((carpeta / "clubes.json").read_text(encoding="utf-8"))
    jg = json.loads((carpeta / "jugadores.json").read_text(encoding="utf-8"))
    clubes = [dict(zip(cl["columnas"], f)) for f in cl["filas"]]
    jug = [dict(zip(jg["columnas"], f)) for f in jg["filas"]]
    rng = np.random.default_rng(semilla)
    ex = cargar("simulation")["exportar"]
    out = []
    cand_cl = [x for x in clubes if x["base"] == ex["temporada_base"] and len(x["plantilla"]) >= 8
               and x["liga"] in ("euroleague", "acb", "lnb", "feb1", "eurocup", "nba", "bbl")]
    cand_j = [x for x in jug if x["temporada"] == ex["temporada_base"] and (x["min_total"] or 0) >= 600 and x["th"][0] is not None]
    c = S.cargar_corte(ex["temporada_base"])
    for k in range(n):
        club = cand_cl[int(rng.integers(len(cand_cl)))]
        rec = cand_j[int(rng.integers(len(cand_j)))]
        r = S.simular(c, rec["persona"], club["liga"], club["team"], [(p[3], p[1]) for p in club["plantilla"]],
                      entrenador=club["entrenador"], ritmo=club["ritmo"], team_eu=club["eu"], team_eu_probs=club["eu_probs"],
                      n_sim=n_sim, detalle=False, club_t=club["club_t"])
        out.append({"rec": rec["id"], "club": f"{club['liga']}|{club['team']}|{club['temporada']}",
                    "minutos": r["minutos"]["media"], "roles": r["roles"], "pts_p100": r["produccion_p100"]["pts_p100"]["media"],
                    "ts_pct": r["produccion_p100"]["ts_pct"]["media"], "usg_pct": r["produccion_p100"]["usg_pct"]["media"],
                    "adapt": r["adaptacion"]["adapt_pct_temporada"]["media"], "d_net": r["equipo"]["d_net"],
                    "fit": r["fit"]["total"], "nombre": r["nombre"], "club_nombre": club["nombre"]})
    (carpeta / "paridad.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return out
