"""Construcción de las tablas de la capa ESF a partir del bruto (sin red).

Salida por liga y temporada (data/basko/processed/<temporada>/):
  jugadores/<liga>.csv      1 fila = jugador-equipo-fase. Esquema canónico de 480 columnas del repositorio (mismas
                            fórmulas que el resto de ligas) + extensiones de la capa ESF (`EXT_COLS`) + on/off,
                            RAPM, rotación y clutch del motor de quintetos (prefijo `pbp_`). Fases: cada fase real
                            de la competición (primera_fase, segunda_fase, copa…) y `total` = todas las fases juntas.
  equipos/<liga>.csv        1 fila = equipo-fase: récord, puntos, posesiones, ratings, cuatro factores, quintetos.
  partidos/<liga>.csv       1 fila = partido del calendario (también los de temporadas sin acta digital).
  boxscores/<liga>.csv.gz   1 fila = jugador-partido (de la cronología; acta como control).
  eventos/<liga>.csv.gz     jugada a jugada normalizado (todas las acciones, con reloj, marcador y coordenadas).
  tiros/<liga>.csv.gz       1 fila = tiro de campo con coordenadas, zona, distancia y contexto.
  plantillas/<liga>.csv     fichas de equipo: jugadores y entrenadores con licencia y uuid de persona.
  quintetos/<liga>/         quintetos, tríos, parejas, on/off, asistencias, equipos, validación y tramos.
Convenciones: porcentajes 0-100; dato no publicado o no registrado por la mesa = vacío (nunca 0); ninguna fila
ni columna se elimina; todas las ligas tienen exactamente las mismas columnas.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from ..adapters.base import ParsedLeague
from ..adapters.boxscore import aggregate_games
from ..lineups import stints
from ..lineups.schema import PLAYER_COLS, TEAM_COLS
from ..metrics import finalize_columns
from ..pipeline import _phase_frame
from ..schema import COLUMN_NAMES, dictionary_records
from .eventos import procesar_partido, stats_acta
from .extractor import jugado, partidos_calendario

# ------------------------------------------------------------------------------------------ esquema ESF
EXT_SPEC: list[tuple[str, str]] = [
    ("division", "División de la fila: A1 | A2 | cruce (partidos entre divisiones) | todas (total de ligas con divisiones) | "
                 "única (ligas sin divisiones). Junior y Cadete: A1 y A2 son divisiones distintas"),
    ("categoria", "Categoría de la web (nombre oficial de la inscripción en la temporada)"),
    ("nivel", "senior | junior | cadete"),
    ("fase_nombre", "Nombre original de la fase en la web (o 'Todas las fases' en total)"),
    ("fase_tipo", "liga | clasificacion | eliminatoria | copa | total"),
    ("fase_orden", "Orden cronológico de la fase en la temporada (1 = primera); total = 99"),
    ("grupos", "Grupos de la fase en los que ha jugado el equipo"),
    ("club", "Entidad (club) inscrita del equipo"),
    ("cobertura", "acta_y_jugada | solo_acta | sin_acta_digital (temporadas 2018-19 a 2021-22: sólo resultados)"),
    ("partidos_con_acta", "Partidos del jugador con acta digital en la fase"),
    ("partidos_pbp", "Partidos del jugador con jugada a jugada en la fase"),
    ("persona_uuid", "Uuid de la persona federada (acta y fichas de equipo): estable entre partidos, equipos y temporadas; = player_id cuando existe"),
    ("licencia_id", "Id de licencia de la temporada"),
    ("acta_uuid", "Uuid del jugador en el acta digital"),
    ("min_pbp", "Minutos exactos reconstruidos con las entradas y salidas del jugada a jugada"),
    ("min_acta", "Minutos del acta (enteros, redondeados por la mesa)"),
    ("plus_minus_acta", "+/- del acta"),
    ("pf_ofensivas", "Faltas en ataque"), ("pf_antideportivas", "Faltas antideportivas"),
    ("pf_tecnicas", "Faltas técnicas"), ("pf_descalificantes", "Faltas descalificantes"),
    ("pf_tiro", "Faltas personales con tiros libres"), ("tl_viajes", "Viajes a la línea provocados en sus faltas (rival)"),
    ("and1", "Canastas con tiro libre adicional"), ("violaciones", "Violaciones"), ("saltos_ganados", "Saltos iniciales ganados"),
    ("fga_aro", "Tiros de campo a < 1,25 m del aro"), ("fgm_aro", "Canastas a < 1,25 m"), ("fg_pct_aro", "% de acierto en el aro"),
    ("fga_pintura", "Tiros de 2 en la zona (sin el aro)"), ("fgm_pintura", "Canastas en la zona (sin el aro)"),
    ("fg_pct_pintura", "% en la zona (sin el aro)"),
    ("fga_media", "Tiros de media distancia (2 fuera de la zona)"), ("fgm_media", "Canastas de media distancia"),
    ("fg_pct_media", "% de media distancia"),
    ("fg3a_esquina", "Triples de esquina intentados"), ("fg3m_esquina", "Triples de esquina anotados"),
    ("fg3_pct_esquina", "% de triples de esquina"),
    ("fg3a_frontal", "Triples frontales intentados"), ("fg3m_frontal", "Triples frontales anotados"),
    ("fg3_pct_frontal", "% de triples frontales"),
    ("fga_con_coord", "Tiros de campo con coordenadas en el acta"),
    ("frec_aro", "% de sus tiros de campo en el aro"), ("frec_pintura", "% en la zona (sin el aro)"),
    ("frec_media", "% de media distancia"), ("frec_triple_esquina", "% triples de esquina"),
    ("frec_triple_frontal", "% triples frontales"), ("dist_tiro_media", "Distancia media de tiro (m)"),
    ("fgm_asistidos", "Canastas propias asistidas (si la mesa registra asistencias)"),
    ("pct_fgm_asistidos", "% de canastas asistidas"),
    ("pts_q1", "Puntos en el 1.er cuarto"), ("pts_q2", "Puntos en el 2.º cuarto"), ("pts_q3", "Puntos en el 3.er cuarto"),
    ("pts_q4", "Puntos en el 4.º cuarto"), ("pts_ot", "Puntos en prórrogas"),
    ("pct_pts_segunda_mitad", "% de sus puntos en la segunda mitad (3.º, 4.º y prórrogas)"),
    ("clutch_pts", "Puntos en clutch (últimos 5 min del 4.º/prórroga, ±5)"), ("clutch_fga", "Tiros de campo en clutch"),
    ("clutch_fgm", "Canastas en clutch"), ("clutch_fg3a", "Triples intentados en clutch"),
    ("clutch_fg3m", "Triples anotados en clutch"), ("clutch_fta", "Tiros libres intentados en clutch"),
    ("clutch_ftm", "Tiros libres anotados en clutch"), ("clutch_tov", "Pérdidas en clutch"),
    ("clutch_oreb", "Rebotes ofensivos en clutch"), ("clutch_dreb", "Rebotes defensivos en clutch"),
    ("clutch_stl", "Recuperaciones en clutch"), ("clutch_pf", "Faltas en clutch"),
    ("clutch_ts_pct", "TS% en clutch"), ("clutch_pts_p40", "Puntos por 40 minutos de clutch"),
    ("pct_pts_contraataque", "% de puntos al contraataque"),
    ("pct_pts_segunda_oportunidad", "% de puntos de segunda oportunidad"),
    ("pct_pts_tras_perdida", "% de puntos tras pérdida del rival"),
    ("game_score_max", "Mejor Game Score en un partido"), ("pts_max", "Máximo de puntos en un partido"),
    ("pts_std", "Desviación típica de sus puntos por partido (regularidad)"),
    ("game_score_std", "Desviación típica del Game Score por partido"),
    ("partidos_10_pts", "Partidos con 10 o más puntos"), ("partidos_20_pts", "Partidos con 20 o más puntos"),
]
SA_METRICS = ["game_score", "game_score_pg", "game_score_p40", "eff", "eff_pg", "pir_calc", "pie", "uper", "per",
              "ortg", "drtg", "net_rtg", "floor_pct", "pprod", "scposs", "totposs", "stops", "stop_pct", "ows", "dws",
              "ws", "ws_per_40", "tov_ratio"]
EXT_SPEC += [("registra_asistencias", "La mesa registró asistencias en algún partido de la fila (si no, ast vacío y las "
                                      "métricas compuestas las cuentan como 0)"),
             ("registra_tapones", "La mesa registró tapones en algún partido de la fila (si no, blk/blka vacíos y las "
                                  "métricas compuestas los cuentan como 0)")]
EXT_COLS = [c for c, _ in EXT_SPEC]
assert not set(EXT_COLS) & set(COLUMN_NAMES), set(EXT_COLS) & set(COLUMN_NAMES)
PBP_PLAYER_COLS = ["pbp_" + c for c, _ in PLAYER_COLS
                   if c not in ("liga", "temporada", "fase", "team_id", "equipo", "player_id", "nombre")]
PLAYER_COLUMNS = COLUMN_NAMES + EXT_COLS + PBP_PLAYER_COLS

_GAME_SUM = ("pf_ofensivas pf_antideportivas pf_tecnicas pf_descalificantes pf_tiro tl_viajes and1 violaciones "
             "saltos_ganados fga_aro fgm_aro fga_pintura fgm_pintura fga_media fgm_media fg3a_esquina fg3m_esquina "
             "fg3a_frontal fg3m_frontal fga_con_coord dist_tiro_sum fgm_asistidos clutch_pts clutch_fga clutch_fgm "
             "clutch_fg3a clutch_fg3m clutch_fta clutch_ftm clutch_tov clutch_oreb clutch_dreb clutch_stl clutch_pf "
             "q1_pts q2_pts q3_pts q4_pts ot_pts").split()
BOX_COUNT = ["pts", "fgm", "fga", "fg2m", "fg2a", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "reb", "ast", "stl",
             "tov", "blk", "blka", "pf", "pfd", "dunks", "fastbreaks", "pts_fastbreak", "pts_paint", "pts_2ndchance",
             "pts_off_tov"]


# ------------------------------------------------------------------------------------------ fases
def _norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip()


def fase_slug(nombre: str | None) -> str:
    """Nombre de la competición en la web -> clave de fase estable entre temporadas.
    "LVJM-Primera Fase" -> primera_fase · "1ª Mas-Liga Regular" -> liga_regular · "LVCM-Fase Clasificaion" ->
    fase_clasificacion · "CVNRJM-Prim. Fase" -> primera_fase · "Prim.Div.Mas" / "L.V.Cad.Mas." -> liga_regular."""
    s = _norm(nombre)
    s = re.sub(r"^(lvjm|lvcm|lvnrjm|lvnrcm|cvnrjm|cvnrcm)\s*-\s*", "", s)
    s = re.sub(r"^\d\s*a?\s*mas\.?\s*-\s*", "", s)
    s = re.sub(r"[\s-]*(lvjm|lvcm|lvjmas|lvcmas|(jun|cad)\.?\s*mas\.?)$", "", s).strip()
    if (not s or re.match(r"^(prim\.?\s*div|seg\.?\s*div|\d\s*a?\s*div|l\.?\s*v\.?\s*(jun|cad)|c\.?\s*eus|liga vasca)", s)):
        return "liga_regular"
    s = s.replace("prim.", "primera").replace("seg.", "segunda")
    s = re.sub(r"clasif\w*", "clasificacion", s)
    if s in ("copa federacion",):
        return "copa"
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_") or "liga_regular"


def fase_tipo(nombre: str, reglas: list) -> str:
    n = fase_slug(nombre).replace("_", " ")
    for pat, t in reglas:
        if re.search(pat, n):
            return t
    return "liga"


# ------------------------------------------------------------------------------------------ calendario
def tabla_partidos(liga: str, season: str, payload: dict, cfg: dict, divisional: bool = False) -> pd.DataFrame:
    rows = []
    cats = payload.get("categorias") or {}
    for gid, cal in (payload.get("calendario") or {}).items():
        g = (payload.get("grupos") or {}).get(gid) or {}
        for m in partidos_calendario(cal):
            rd = m.get("numMatchDay")
            nombre = m.get("nameCompetition") or g.get("competitionName")
            rows.append({
                "liga": liga, "temporada": season, "game_id": str(m.get("idMatch")),
                "categoria": (cats.get(str(m.get("idCategorySigned"))) or {}).get("categoryRegisteredName")
                or m.get("nameCategorySigned"),
                "competicion_id": str(m.get("idCompetition") or g.get("idCompetition") or ""),
                "fase_nombre": nombre, "fase": fase_slug(nombre),
                "fase_tipo": fase_tipo(nombre or "", cfg.get("fases_tipo") or []),
                "grupo_id": str(gid), "grupo": m.get("nameGroup") or g.get("grupName"), "jornada": rd,
                "fecha": str(m.get("matchDay") or "")[:10] or None, "hora": str(m.get("matchDay") or "")[11:16] or None,
                "local_id": str(m.get("idLocalTeam") or ""), "local": m.get("nameLocalTeam"),
                "club_local": m.get("nameLocalTeamOrganization"),
                "visitante_id": str(m.get("idVisitorTeam") or ""), "visitante": m.get("nameVisitorTeam"),
                "club_visitante": m.get("nameVisitorTeamOrganization"),
                "pts_local": pd.to_numeric(m.get("localScore"), errors="coerce"),
                "pts_visitante": pd.to_numeric(m.get("visitorScore"), errors="coerce"),
                "jugado": jugado(m), "tipo_resultado": m.get("typeResult"),
                "pabellon": m.get("nameField"), "localidad": m.get("nameTown"),
                "universallyid": m.get("universallyid"), "match_call_uuid": m.get("matchCallUuid"),
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.drop_duplicates("game_id", keep="last")
    first = df.groupby("fase")["fecha"].min().sort_values()
    order = {f: i + 1 for i, f in enumerate(first.index)}
    df["fase_orden"] = df["fase"].map(order)
    df = df.sort_values(["fecha", "game_id"]).reset_index(drop=True)
    df["division"] = asignar_division(df, cfg.get("reglas_division") or [], divisional)
    return df


def asignar_division(df: pd.DataFrame, reglas: list, divisional: bool) -> pd.Series:
    """División de cada partido (ver config `reglas_division`). Sin regla: la de los dos equipos en su partido con
    división conocida más cercano en el tiempo (anterior o, si no hay, posterior); si difieren -> "cruce"."""
    if not divisional or df.empty:
        return pd.Series("única", index=df.index, dtype=object)
    div = pd.Series(None, index=df.index, dtype=object)
    for campo, pat, d in reglas:
        col = df["grupo"].map(_norm) if campo == "grupo" else df["fase"].fillna("")
        m = div.isna() & col.fillna("").map(lambda x, pat=pat: bool(re.search(pat, x)))
        div[m] = d
    hist = defaultdict(list)
    for i, r in df[div.notna()].iterrows():
        for t in (r["local_id"], r["visitante_id"]):
            hist[t].append((str(r["fecha"]), div[i]))

    def de(t, f):
        h = sorted(hist.get(t, []))
        antes = [d for fe, d in h if fe <= f]
        return antes[-1] if antes else (h[0][1] if h else None)
    for i in df.index[div.isna()]:
        f = str(df.at[i, "fecha"])
        a, b = de(df.at[i, "local_id"], f), de(df.at[i, "visitante_id"], f)
        div[i] = a if (a and a == b) else ("cruce" if (a or b) else "A1")
    return div


def unidades(partidos: pd.DataFrame, divisional: bool) -> list[dict]:
    """Unidades de agregación: cada fase × división (en orden cronológico), `total` (todas las fases y divisiones) y,
    en ligas con divisiones, `total_a1` y `total_a2` (cada división por separado; los cruces sólo cuentan en total)."""
    out = []
    if partidos.empty:
        return out
    pj = partidos[partidos["jugado"]]
    for fase in pj.sort_values("fase_orden")["fase"].unique():
        sp = pj[pj["fase"] == fase]
        for d in sorted(sp["division"].unique()):
            out.append({"fase": fase, "division": d, "uid": f"{fase}|{d}", "tipo": "fase",
                        "gids": set(sp.loc[sp["division"] == d, "game_id"])})
    out.append({"fase": "total", "division": "todas" if divisional else "única", "uid": "total", "tipo": "total",
                "gids": set(pj["game_id"])})
    if divisional:
        for d in ("A1", "A2"):
            g = set(pj.loc[pj["division"] == d, "game_id"])
            if g:
                out.append({"fase": f"total_{d.lower()}", "division": d, "uid": f"total_{d.lower()}", "tipo": "total", "gids": g})
    return out


def tabla_plantillas(liga: str, season: str, payload: dict) -> pd.DataFrame:
    rows = []
    for tid, card in (payload.get("equipos") or {}).items():
        if not isinstance(card, dict):
            continue
        team = card.get("team") or {}
        club = card.get("club") or {}
        for p in card.get("players") or []:
            tl = p.get("licenseTypeName") or ""
            if not re.search(r"jugador|entrenador", tl, re.I):
                continue
            rows.append({"liga": liga, "temporada": season, "team_id": str(tid), "equipo": team.get("name"),
                         "club": club.get("name"), "tipo_licencia": tl, "licencia_id": str(p.get("idLicense") or ""),
                         "persona_uuid": p.get("uuid"), "nombre": p.get("name"), "apellidos": (p.get("surname") or "").strip(),
                         "nombre_completo": " ".join(f"{p.get('name') or ''} {p.get('surname') or ''}".split())})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------ construcción
def construir_liga(liga: str, lcfg: dict, cfg: dict, season: str, payload: dict, meta: dict | None = None,
                   raw_path: str | None = None) -> dict:
    meta = meta or {}
    notas: list[str] = []
    divisional = bool(lcfg.get("divisiones"))
    partidos = tabla_partidos(liga, season, payload, cfg, divisional)
    units = unidades(partidos, divisional)
    plantillas = tabla_plantillas(liga, season, payload)
    games = payload.get("games") or {}
    lic2uuid = {r.licencia_id: r.persona_uuid for r in plantillas.itertuples() if r.licencia_id} if not plantillas.empty else {}
    club_of = {}
    if not partidos.empty:
        for r in partidos.itertuples():
            club_of[r.local_id] = r.club_local
            club_of[r.visitante_id] = r.club_visitante
    coaches = defaultdict(list)
    if not plantillas.empty:
        for r in plantillas[plantillas["tipo_licencia"].str.contains("ENTRENADOR", case=False)].itertuples():
            if r.nombre_completo and len(r.nombre_completo.replace(".", "").replace(" ", "")) > 3:
                coaches[r.team_id].append(r.nombre_completo)

    from .eventos import norm_nombre
    roster = {}
    if not plantillas.empty:
        for r in plantillas.itertuples():
            if r.licencia_id:
                roster[(r.team_id, norm_nombre(r.nombre_completo))] = r.licencia_id
    box_rows, std_games, ev_rows, shot_rows, results, val_extra = [], [], [], [], [], {}
    info = partidos.set_index("game_id").to_dict("index") if not partidos.empty else {}
    for gid, doc in games.items():
        m = info.get(gid)
        if m is None or not isinstance(doc, dict) or doc.get("sin_datos"):
            continue
        acta, jug = doc.get("acta") or {}, doc.get("jugadas") or []
        fase, div = m["fase"], m["division"]
        pr = procesar_partido(gid, fase, acta, jug, m.get("fecha"), roster)
        pr.game.phase = f"{fase}|{div}"
        for x in pr.eventos:
            x["division"] = div
        for x in pr.tiros:
            x["division"] = div
        gr = stints.build(pr.game, pr.game_min) if pr.game.has_lineups else None
        v = gr.validation() if gr else {"con_quintetos": False, "dif_pm_max": None, "dif_min_max_s": None}
        pm_ok = v.get("dif_pm_max") is None or v["dif_pm_max"] <= 3
        lineup_ok = bool(gr and v["con_quintetos"] and pm_ok and (v["dif_min_max_s"] is None or v["dif_min_max_s"] <= 180))
        if gr:
            results.append(gr)
        # ¿la cronología cuadra con el marcador del acta? (si no, el boxscore sale del acta)
        intern = {str(t.get("teamIdIntern")): str(t.get("teamIdExtern")) for t in acta.get("teams") or []}
        acta_pts = {intern[str(t.get("teamIdIntern"))]: (t.get("data") or {}).get("score") for t in acta.get("teams") or []}
        pbp_pts = Counter()
        for pid, l in pr.lineas.items():
            pbp_pts[pr.jugadores.get(pid, {}).get("team_id")] += l.get("pts", 0)
        pbp_ok = bool(jug) and all(pbp_pts.get(t, 0) == (p or 0) for t, p in acta_pts.items())
        val_extra[gid] = {"pbp_cuadra_marcador": pbp_ok, "quintetos_validos": lineup_ok, "n_eventos": len(jug),
                          "partido_min": pr.game_min, **{k: v.get(k) for k in ("dif_pm_max", "dif_min_max_s", "dif_min_media_s")}}
        if not pbp_ok:
            notas.append(f"partido {gid}: la cronología no cuadra con el acta; boxscore del acta")
        sides = []
        for t in acta.get("teams") or []:
            tid = str(t.get("teamIdExtern"))
            opp = [str(x.get("teamIdExtern")) for x in acta.get("teams") if str(x.get("teamIdExtern")) != tid]
            tot = stats_acta(t.get("data"))
            for k, flag in (("ast", "ast"), ("blk", "blk"), ("blka", "blk"), ("dunks", "dunks")):
                if not pr.registra.get(flag):
                    tot.pop(k, None)
            tot.pop("pir", None)
            tot.pop("fastbreaks", None)
            players = []
            for p in t.get("players") or []:
                pid = pr.canon[str(p.get("actorId"))]
                j = pr.jugadores.get(pid, {})
                a = stats_acta(p.get("data"))
                l = pr.lineas.get(pid, {}) if pbp_ok else {}
                line = {"player_id": pid, "name": j.get("nombre"), "dorsal": p.get("dorsal"), "starter": bool(p.get("starting"))}
                for k in BOX_COUNT:
                    if pbp_ok:
                        line[k] = float(l.get(k, 0))
                    elif k in a:
                        line[k] = a[k]
                for k, flag in (("ast", "ast"), ("blk", "blk"), ("blka", "blk"), ("dunks", "dunks")):
                    if not pr.registra.get(flag) and not (not pbp_ok and a.get(k)):
                        line[k] = None
                if not pbp_ok:
                    for k in ("fastbreaks", "pts_fastbreak", "pts_paint", "pts_2ndchance", "pts_off_tov"):
                        line[k] = None
                sec = gr.seconds.get(pid) if (gr and lineup_ok) else None
                line["min"] = sec / 60 if sec is not None else (float(p["timePlayed"]) if p.get("timePlayed") is not None else None)
                if line["min"] == 0 and any(line.get(k) for k in ("pts", "fga", "fta", "reb", "pf")):
                    line["min"] = float(p.get("timePlayed") or 0) or None
                line["plus_minus"] = float(gr.pm.get(pid, 0)) if (gr and lineup_ok) else (
                    float(p["inOut"]) if p.get("inOut") is not None else None)
                line["pir"] = a.get("pir")
                players.append(line)
                br = {"liga": liga, "temporada": season, "game_id": gid, "fecha": m.get("fecha"), "fase": fase, "division": div,
                      "grupo": m.get("grupo"), "team_id": tid, "equipo": t.get("name"),
                      "rival_id": opp[0] if opp else None, "local": tid == m.get("local_id"),
                      "player_id": pid, "nombre": j.get("nombre"), "dorsal": p.get("dorsal"),
                      "titular": bool(p.get("starting")), "licencia_id": j.get("licencia_id"),
                      "persona_uuid": p.get("uuid") or lic2uuid.get(j.get("licencia_id")), "acta_uuid": p.get("uuid"),
                      "min": line["min"], "min_pbp": sec / 60 if sec is not None else None,
                      "min_acta": p.get("timePlayed"), "plus_minus": line["plus_minus"], "plus_minus_acta": p.get("inOut"),
                      "pir": a.get("pir"), "fuente_box": "jugada_a_jugada" if pbp_ok else "acta",
                      "con_pbp": bool(jug), "jugo": bool((line["min"] or 0) > 0 or any(line.get(k) for k in ("pts", "fga", "fta", "pf", "reb")))}
                for k in BOX_COUNT:
                    br[k] = line.get(k)
                for k in _GAME_SUM:
                    br[k] = float(l.get(k, 0)) if pbp_ok else None
                if not pr.registra.get("ast"):
                    br["fgm_asistidos"] = None
                g = br
                g["game_score"] = (None if g.get("pts") is None else
                                   g["pts"] + 0.4 * g["fgm"] - 0.7 * g["fga"] - 0.4 * (g["fta"] - g["ftm"])
                                   + 0.7 * g["oreb"] + 0.3 * g["dreb"] + g["stl"] + 0.7 * (g.get("ast") or 0)
                                   + 0.7 * (g.get("blk") or 0) - 0.4 * g["pf"] - g["tov"])
                box_rows.append(br)
            if pbp_ok:
                # totales de equipo = suma de la cronología de sus jugadores + lo que sólo es de equipo (rebotes y
                # pérdidas de equipo: valor del acta del equipo − suma del acta de sus jugadores)
                asum = Counter()
                for p in t.get("players") or []:
                    asum.update(stats_acta(p.get("data")))
                tot2 = {}
                for k in ("pts", "fgm", "fga", "fg2m", "fg2a", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "reb",
                          "ast", "stl", "tov", "blk", "pf"):
                    vals = [pl.get(k) for pl in players if pl.get(k) is not None]
                    if vals:
                        tot2[k] = float(sum(vals))
                for k in ("oreb", "dreb", "tov"):
                    if k in tot and k in tot2:
                        tot2[k] += max(0.0, tot[k] - asum.get(k, 0.0))
                tot2["reb"] = tot2.get("oreb", 0.0) + tot2.get("dreb", 0.0)
                tot = tot2
            sides.append({"team_id": tid, "name": t.get("name"), "code": t.get("shortName"), "totals": tot,
                          "players": players})
        if m.get("local_id") and sides and sides[0]["team_id"] != m["local_id"]:
            sides = sides[::-1]
        std_games.append({"game_id": gid, "phase": f"{fase}|{div}", "final": True, "teams": sides, "date": m.get("fecha")})
        ev_rows.extend(pr.eventos)
        shot_rows.extend(pr.tiros)

    boxscores = pd.DataFrame(box_rows)
    # ------------------------------------------------------------------ jugadores por fase + total
    fases = list(partidos.sort_values("fase_orden")["fase"].unique()) if not partidos.empty else []
    lc = {"nombre": lcfg["nombre"], "pais": "España", "fuente": "basketbasko.com (Federación Vasca de Baloncesto)",
          "minutos_partido": float(cfg.get("minutos_partido", 40)), "coef_tl_posesion": 0.4}
    frames = []
    for u in units:
        sel = [g for g in std_games if g["game_id"] in u["gids"]]
        if not sel:
            continue
        parsed: ParsedLeague = aggregate_games(sel, [f"{u['uid']}: {len(sel)} partidos con acta"])
        df = _phase_frame(parsed, u["fase"], liga, lc, season, meta, raw_path)
        if df.empty:
            continue
        sa = _phase_frame(_sin_asistencias(parsed), u["fase"], liga, lc, season, meta, raw_path)
        # ratings que usan asistencias/tapones: si la mesa no los registra se calculan con esos conteos a 0
        sa = sa[["player_id", "team_id"] + SA_METRICS].rename(columns={m: f"{m}__sa" for m in SA_METRICS})
        df = df.merge(sa, on=["player_id", "team_id"], how="left")
        # siempre con los no registrados a 0: idéntico si la mesa registra todo y coherente si registra sólo en parte
        # (la normalización del PER y el contexto de liga usan así la misma base para todos los jugadores)
        df["registra_asistencias"] = pd.to_numeric(df["ast"], errors="coerce").notna()
        df["registra_tapones"] = pd.to_numeric(df["blk"], errors="coerce").notna()
        for m in SA_METRICS:
            df[m] = df[f"{m}__sa"]
        df = df.drop(columns=[f"{m}__sa" for m in SA_METRICS])
        df["division"] = u["division"]
        frames.append(df)
    jugadores = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMN_NAMES + ["division"])
    jugadores = _extensiones(jugadores, boxscores, partidos, units, lcfg, club_of)

    # ------------------------------------------------------------------ quintetos / on-off por fase × división y total
    q_info = {}
    usable = [r for r in results if val_extra.get(r.game.game_id, {}).get("quintetos_validos")]
    if results:   # se escriben en escribir_liga (quintetos/<liga>/)
        q_info = {"results": results, "usable": usable, "units": units, "divisional": divisional}

    # ------------------------------------------------------------------ roster de temporadas sin acta
    sin_acta = plantillas[plantillas["tipo_licencia"].str.contains("JUGADOR", case=False)] if not plantillas.empty else plantillas
    if not sin_acta.empty and std_games == []:
        ros = pd.DataFrame({"liga": liga, "liga_nombre": lcfg["nombre"], "pais": "España", "temporada": season,
                            "fase": "total", "division": "todas" if divisional else "única", "fuente": lc["fuente"], "fecha_extraccion": meta.get("fecha_extraccion"),
                            "archivo_bruto": raw_path, "player_id": sin_acta["persona_uuid"].fillna("lic-" + sin_acta["licencia_id"].astype(str)).values,
                            "nombre": sin_acta["nombre_completo"].values, "team_id": sin_acta["team_id"].values,
                            "equipo": sin_acta["equipo"].values, "minutos_partido": lc["minutos_partido"],
                            "calidad_contexto": "sin_contexto", "categoria": _categoria(payload),
                            "nivel": lcfg.get("nivel"), "fase_nombre": "Todas las fases", "fase_tipo": "total",
                            "fase_orden": 99, "club": sin_acta["club"].values, "cobertura": "sin_acta_digital",
                            "partidos_con_acta": 0, "partidos_pbp": 0, "persona_uuid": sin_acta["persona_uuid"].values,
                            "licencia_id": sin_acta["licencia_id"].values})
        ros["player_uid"] = liga + ":" + ros["player_id"]
        jugadores = pd.concat([jugadores, ros], ignore_index=True)
    jugadores = jugadores.reindex(columns=PLAYER_COLUMNS)

    equipos = _equipos(liga, season, lcfg, partidos, jugadores, units, coaches, club_of)
    if not partidos.empty:
        partidos["con_acta"] = partidos["game_id"].map(lambda g: g in games and not (games[g] or {}).get("sin_datos"))
        for k in ("pbp_cuadra_marcador", "quintetos_validos", "n_eventos", "partido_min", "dif_pm_max", "dif_min_max_s"):
            partidos[k] = partidos["game_id"].map(lambda g, k=k: (val_extra.get(g) or {}).get(k))
    eventos = pd.DataFrame(ev_rows)
    if not eventos.empty:
        eventos.insert(0, "temporada", season)
        eventos.insert(0, "liga", liga)
    tiros = pd.DataFrame(shot_rows)
    if not tiros.empty:
        tiros.insert(0, "temporada", season)
        tiros.insert(0, "liga", liga)
    if not partidos.empty and partidos["universallyid"].isna().all():
        notas.append("temporada sin acta digital en la web: sólo calendario, resultados y plantillas")
    return {"liga": liga, "temporada": season, "lcfg": lcfg, "partidos": partidos, "plantillas": plantillas,
            "boxscores": boxscores, "jugadores": jugadores, "equipos": equipos, "eventos": eventos, "tiros": tiros,
            "quintetos": q_info, "fases": fases, "units": units, "notas": notas, "lc": lc}


def _sin_asistencias(parsed: ParsedLeague) -> ParsedLeague:
    """Copia con asistencias, tapones y tapones recibidos a 0 donde la mesa no los registra."""
    ks = ("ast", "blk", "blka")
    pl = [{**p, **{k: (p.get(k) if p.get(k) is not None else 0.0) for k in ks}} for p in parsed.players]
    tk = [f"{pre}_{k}" for pre in ("team", "opp") for k in ("ast", "blk")]
    te = [{**t, **{k: (t.get(k) if t.get(k) is not None else 0.0) for k in tk}} for t in parsed.teams]
    return ParsedLeague(players=pl, teams=te, notes=[])


def _categoria(payload: dict) -> str | None:
    cats = payload.get("categorias") or {}
    return " / ".join(sorted({c.get("categoryRegisteredName") for c in cats.values() if c.get("categoryRegisteredName")})) or None


def _div(a, b):
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    with np.errstate(divide="ignore", invalid="ignore"):
        return (a / b).where(b > 0)


def _fase_meta(fase: str, division: str, fmeta: pd.DataFrame) -> tuple:
    if fase.startswith("total"):
        return ("Todas las fases" + (f" · {division}" if fase != "total" else ""), "total", 99 if fase == "total" else 100)
    if fase in fmeta.index:
        r = fmeta.loc[fase]
        return (r["fase_nombre"], r["fase_tipo"], r["fase_orden"])
    return (fase, None, None)


def _extensiones(df: pd.DataFrame, box: pd.DataFrame, partidos: pd.DataFrame, units: list, lcfg: dict,
                 club_of: dict) -> pd.DataFrame:
    if df.empty:
        return df.reindex(columns=list(df.columns) + [c for c in EXT_COLS if c not in df.columns])
    df = df.copy()
    df["team_id"] = df["team_id"].astype(str)
    df["player_id"] = df["player_id"].astype(str)
    fmeta = partidos.drop_duplicates("fase").set_index("fase") if not partidos.empty else pd.DataFrame()
    df["categoria"] = partidos["categoria"].dropna().iloc[0] if not partidos.empty and partidos["categoria"].notna().any() else None
    df["nivel"] = lcfg.get("nivel")
    meta = [_fase_meta(f, d, fmeta) for f, d in zip(df["fase"], df["division"])]
    df["fase_nombre"] = [m[0] for m in meta]
    df["fase_tipo"] = [m[1] for m in meta]
    df["fase_orden"] = [m[2] for m in meta]
    df["club"] = df["team_id"].map(club_of)
    if box.empty:
        return df
    b = box.copy()
    b["team_id"] = b["team_id"].astype(str)
    b["player_id"] = b["player_id"].astype(str)
    out_parts = []
    k = ["player_id", "team_id"]
    for u in units:
        sb = b[b["game_id"].isin(u["gids"])]
        if sb.empty:
            continue
        sp = sb[sb["jugo"]]
        agg = sb.groupby(k).agg(partidos_con_acta=("game_id", "nunique"),
                                partidos_pbp=("con_pbp", "sum"),
                                persona_uuid=("persona_uuid", lambda s: s.dropna().iloc[-1] if s.notna().any() else None),
                                licencia_id=("licencia_id", lambda s: s.dropna().iloc[-1] if s.notna().any() else None),
                                acta_uuid=("acta_uuid", lambda s: s.dropna().iloc[-1] if s.notna().any() else None))
        sums = sp.groupby(k)[[c for c in _GAME_SUM] + ["min_pbp", "min_acta", "plus_minus_acta", "pir"]].sum(min_count=1)
        var = sp.groupby(k).agg(game_score_max=("game_score", "max"), pts_max=("pts", "max"),
                                pts_std=("pts", "std"), game_score_std=("game_score", "std"),
                                partidos_10_pts=("pts", lambda s: (s >= 10).sum()),
                                partidos_20_pts=("pts", lambda s: (s >= 20).sum()))
        grp = sb.groupby("team_id")["grupo"].agg(lambda s: " · ".join(sorted({str(x) for x in s.dropna()})))
        a = agg.join(sums).join(var).reset_index()
        a["grupos"] = a["team_id"].map(grp)
        a["fase"], a["division"] = u["fase"], u["division"]
        out_parts.append(a)
    if not out_parts:
        return df
    ext = pd.concat(out_parts, ignore_index=True)
    ext["cobertura"] = np.where(ext["partidos_pbp"] > 0, "acta_y_jugada", "solo_acta")
    ext = ext.rename(columns={"q1_pts": "pts_q1", "q2_pts": "pts_q2", "q3_pts": "pts_q3", "q4_pts": "pts_q4", "ot_pts": "pts_ot"})
    keys = ["player_id", "team_id", "fase", "division"]
    df = df.drop(columns=[c for c in ext.columns if c in df.columns and c not in keys])
    df = df.merge(ext, on=keys, how="left")
    pct = lambda m_, a_: 100 * _div(df[m_], df[a_])  # noqa: E731
    df["fg_pct_aro"] = pct("fgm_aro", "fga_aro")
    df["fg_pct_pintura"] = pct("fgm_pintura", "fga_pintura")
    df["fg_pct_media"] = pct("fgm_media", "fga_media")
    df["fg3_pct_esquina"] = pct("fg3m_esquina", "fg3a_esquina")
    df["fg3_pct_frontal"] = pct("fg3m_frontal", "fg3a_frontal")
    for z, c in (("aro", "fga_aro"), ("pintura", "fga_pintura"), ("media", "fga_media"),
                 ("triple_esquina", "fg3a_esquina"), ("triple_frontal", "fg3a_frontal")):
        df[f"frec_{z}"] = pct(c, "fga_con_coord")
    df["dist_tiro_media"] = _div(df["dist_tiro_sum"], df["fga_con_coord"])
    df["pct_fgm_asistidos"] = pct("fgm_asistidos", "fgm")
    df["pct_pts_segunda_mitad"] = 100 * _div(df[["pts_q3", "pts_q4", "pts_ot"]].sum(axis=1, min_count=1), df["pts"])
    df["clutch_ts_pct"] = 100 * _div(df["clutch_pts"], 2 * (df["clutch_fga"] + 0.44 * df["clutch_fta"]))
    df["clutch_pts_p40"] = np.nan   # se completa con los minutos de clutch del motor de quintetos (escribir_liga)
    df["pct_pts_contraataque"] = pct("pts_fastbreak", "pts")
    df["pct_pts_segunda_oportunidad"] = pct("pts_2ndchance", "pts")
    df["pct_pts_tras_perdida"] = pct("pts_off_tov", "pts")
    return df.drop(columns=["dist_tiro_sum"], errors="ignore")


def _equipos(liga, season, lcfg, partidos, jugadores, units, coaches, club_of) -> pd.DataFrame:
    rows = []
    if partidos.empty:
        return pd.DataFrame()
    pj = partidos[partidos["jugado"]]
    fmeta = partidos.drop_duplicates("fase").set_index("fase")
    for u in units:
        fase = u["fase"]
        sp = pj[pj["game_id"].isin(u["gids"])]
        side = pd.concat([
            sp.assign(team_id=sp["local_id"], equipo=sp["local"], pf=sp["pts_local"], pc=sp["pts_visitante"], es_local=True),
            sp.assign(team_id=sp["visitante_id"], equipo=sp["visitante"], pf=sp["pts_visitante"], pc=sp["pts_local"], es_local=False)])
        for tid, g in side.groupby("team_id"):
            fn, ft, fo = _fase_meta(fase, u["division"], fmeta)
            r = {"liga": liga, "temporada": season, "fase": fase, "division": u["division"], "team_id": str(tid),
                 "equipo": g["equipo"].iloc[-1], "club": club_of.get(str(tid)), "nivel": lcfg.get("nivel"),
                 "fase_nombre": fn, "fase_tipo": ft, "fase_orden": fo,
                 "divisiones_equipo": " · ".join(sorted(set(g["division"]))),
                 "grupos": " · ".join(sorted({str(x) for x in g["grupo"].dropna()})),
                 "gp": len(g), "w": int((g["pf"] > g["pc"]).sum()), "l": int((g["pf"] < g["pc"]).sum()),
                 "pts": g["pf"].sum(), "opp_pts": g["pc"].sum(),
                 "w_local": int(((g["pf"] > g["pc"]) & g["es_local"]).sum()),
                 "w_visitante": int(((g["pf"] > g["pc"]) & ~g["es_local"]).sum()),
                 "partidos_con_acta": int(g["universallyid"].notna().sum()),
                 "entrenadores": " · ".join(dict.fromkeys(coaches.get(str(tid), [])))}
            r["win_pct"] = 100 * r["w"] / r["gp"] if r["gp"] else None
            r["pts_pg"] = r["pts"] / r["gp"] if r["gp"] else None
            r["opp_pts_pg"] = r["opp_pts"] / r["gp"] if r["gp"] else None
            r["margen_pg"] = (r["pts"] - r["opp_pts"]) / r["gp"] if r["gp"] else None
            rows.append(r)
    eq = pd.DataFrame(rows)
    # contexto de equipo y rival calculado por el motor de métricas (fases con acta)
    if not jugadores.empty and "team_poss" in jugadores.columns:
        ctx_cols = [c for c in jugadores.columns if c.startswith(("team_", "opp_")) and c not in ("team_id",)]
        ctx = (jugadores[jugadores["cobertura"].fillna("") != "sin_acta_digital"]
               .dropna(subset=["team_poss"]).drop_duplicates(["team_id", "fase", "division"])[["team_id", "fase", "division", "calidad_contexto"] + ctx_cols])
        eq = eq.merge(ctx, on=["team_id", "fase", "division"], how="left")
        t = lambda k: pd.to_numeric(eq.get(k), errors="coerce")  # noqa: E731
        eq["efg_pct"] = 100 * _div(t("team_fgm") + 0.5 * t("team_fg3m"), t("team_fga"))
        eq["opp_efg_pct"] = 100 * _div(t("opp_fgm") + 0.5 * t("opp_fg3m"), t("opp_fga"))
        eq["ts_pct"] = 100 * _div(t("team_pts"), 2 * (t("team_fga") + 0.44 * t("team_fta")))
        eq["opp_ts_pct"] = 100 * _div(t("opp_pts"), 2 * (t("opp_fga") + 0.44 * t("opp_fta")))
        eq["tov_pct"] = 100 * _div(t("team_tov"), t("team_fga") + 0.44 * t("team_fta") + t("team_tov"))
        eq["opp_tov_pct"] = 100 * _div(t("opp_tov"), t("opp_fga") + 0.44 * t("opp_fta") + t("opp_tov"))
        eq["oreb_pct"] = 100 * _div(t("team_oreb"), t("team_oreb") + t("opp_dreb"))
        eq["dreb_pct"] = 100 * _div(t("team_dreb"), t("team_dreb") + t("opp_oreb"))
        eq["ft_rate"] = 100 * _div(t("team_fta"), t("team_fga"))
        eq["opp_ft_rate"] = 100 * _div(t("opp_fta"), t("opp_fga"))
        eq["fg3a_rate"] = 100 * _div(t("team_fg3a"), t("team_fga"))
        eq["opp_fg3a_rate"] = 100 * _div(t("opp_fg3a"), t("opp_fga"))
        eq["fg_pct"] = 100 * _div(t("team_fgm"), t("team_fga"))
        eq["fg3_pct"] = 100 * _div(t("team_fg3m"), t("team_fg3a"))
        eq["ft_pct"] = 100 * _div(t("team_ftm"), t("team_fta"))
        eq["stl_pg"] = _div(t("team_stl"), t("team_gp"))
        eq["tov_pg"] = _div(t("team_tov"), t("team_gp"))
    # puntos por tipo derivados del jugada a jugada (suma de jugadores)
    if not jugadores.empty:
        js = jugadores[jugadores["cobertura"].fillna("") != "sin_acta_digital"]
        add = js.groupby(["team_id", "fase", "division"])[["pts_fastbreak", "pts_paint", "pts_2ndchance", "pts_off_tov", "clutch_pts",
                                                "fga_aro", "fga_pintura", "fga_media", "fg3a_esquina", "fg3a_frontal",
                                                "fga_con_coord"]].sum(min_count=1).reset_index()
        eq = eq.merge(add, on=["team_id", "fase", "division"], how="left")
    return eq


# ------------------------------------------------------------------------------------------ escritura
def _csv(df: pd.DataFrame, path: Path, gz: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    num = out.select_dtypes(include="number").columns
    out[num] = out[num].round(4)
    out.to_csv(path, index=False, encoding="utf-8", float_format="%.10g", compression="gzip" if gz else None)


def escribir_liga(t: dict, out_dir: Path, liga: str, cfg: dict) -> dict:
    out_dir = Path(out_dir)
    j, e, p = t["jugadores"], t["equipos"], t["partidos"]
    _csv(j, out_dir / "jugadores" / f"{liga}.csv")
    if not e.empty:
        _csv(e, out_dir / "equipos" / f"{liga}.csv")
    if not p.empty:
        _csv(p, out_dir / "partidos" / f"{liga}.csv")
    if not t["plantillas"].empty:
        _csv(t["plantillas"], out_dir / "plantillas" / f"{liga}.csv")
    for name in ("boxscores", "eventos", "tiros"):
        if not t[name].empty:
            _csv(t[name], out_dir / name / f"{liga}.csv.gz", gz=True)
    q = {}
    qi = t.get("quintetos") or {}
    if qi.get("results"):
        j, e, q = _quintetos(t, qi, out_dir, liga, cfg, j, e)
        t["jugadores"], t["equipos"] = j, e
        _csv(j, out_dir / "jugadores" / f"{liga}.csv")
        if not e.empty:
            _csv(e, out_dir / "equipos" / f"{liga}.csv")
    jp = j[j["cobertura"].fillna("") != "sin_acta_digital"] if not j.empty else j
    return {"partidos_calendario": int(p["jugado"].sum()) if not p.empty else 0,
            "partidos_con_acta": int(p["con_acta"].sum()) if not p.empty and "con_acta" in p else 0,
            "filas_jugadores": len(j), "jugadores_total": int((j["fase"] == "total").sum()) if not j.empty else 0,
            "fases": t["fases"], "notas": t["notas"][:50], "quintetos": {k: v for k, v in q.items() if k != "directorio"},
            "con_jugada": int(jp["partidos_pbp"].fillna(0).gt(0).sum()) if not jp.empty else 0}


def _partir_fase(df: pd.DataFrame, scope_div: str | None, divisional: bool) -> pd.DataFrame:
    """fase interna "<fase>|<división>" -> columnas fase y division; "total" de un ámbito de división -> total_a1/a2."""
    if df.empty or "fase" not in df.columns:
        return df
    df = df.copy()
    f = df["fase"].astype(str)
    if scope_div:
        df["fase"] = f.map(lambda x: f"total_{scope_div.lower()}" if x == "total" else x.split("|")[0])
        df["division"] = scope_div
    else:
        df["division"] = f.map(lambda x: x.split("|")[1] if "|" in x else ("todas" if divisional else "única"))
        df["fase"] = f.map(lambda x: x.split("|")[0])
    return df


def _quintetos(t: dict, qi: dict, out_dir: Path, liga: str, cfg: dict, j: pd.DataFrame, e: pd.DataFrame):
    """Quintetos, tríos, parejas, on/off, RAPM, rotación y clutch (motor común bbstats/lineups) por fase × división y
    total; en ligas con divisiones, además un ámbito por división (quintetos/<liga>/division_A1/…) con su total."""
    from ..lineups.run import write_outputs
    names, teams = {}, {}
    for r in qi["results"]:
        names.update({pid: d.get("nombre") for pid, d in r.game.players.items()})
        teams.update(r.game.team_names)
    lc = {**t["lc"], "coef_tl_posesion": 0.4}
    qcfg = {"quintetos": {**cfg.get("quintetos", {}), "excluir_si_dif_min_s": 1e9}}
    base = out_dir / "quintetos" / liga
    scopes = [(None, qi["usable"], [u["uid"] for u in qi["units"] if u["tipo"] == "fase"] + ["total"], base)]
    if qi["divisional"]:
        for d in ("A1", "A2"):
            rs = [r for r in qi["usable"] if r.game.phase.endswith(f"|{d}")]
            if rs:
                scopes.append((d, rs, ["total"], base / f"division_{d}"))
    info, pls, eqs = {}, [], []
    for d, rs, phases, qdir in scopes:
        qdir.mkdir(parents=True, exist_ok=True)
        res = write_outputs(liga, t["temporada"], rs, {}, None, None, names, teams, qdir, qcfg, lc, phases=phases)
        info[d or "todas"] = {k: v for k, v in res.items() if k != "directorio"}
        for f in qdir.glob("*.csv*"):
            if f.name.startswith("tramos") or f.stat().st_size < 10:
                continue
            try:
                df = pd.read_csv(f, dtype={"player_id": str, "team_id": str}, low_memory=False)
            except pd.errors.EmptyDataError:
                continue
            if "fase" in df.columns:
                df = _partir_fase(df, d, qi["divisional"])
                _csv(df, f, gz=f.name.endswith(".gz"))
            if f.name == "jugadores.csv":
                pls.append(df)
            elif f.name == "equipos.csv":
                eqs.append(df)
    keys = ["player_id", "team_id", "fase", "division"]
    if pls:
        pl = pd.concat(pls, ignore_index=True).drop(columns=["liga", "temporada", "equipo", "nombre"], errors="ignore")
        pl = pl.drop_duplicates(keys)
        pl = pl.rename(columns={c: "pbp_" + c for c in pl.columns if c not in keys})
        jj = j.drop(columns=[c for c in PBP_PLAYER_COLS if c in j.columns]).copy()
        jj["player_id"], jj["team_id"] = jj["player_id"].astype(str), jj["team_id"].astype(str)
        j = jj.merge(pl, on=keys, how="left")
        j["clutch_pts_p40"] = 40 * _div(j["clutch_pts"], j["pbp_clutch_min"])
        j = j.reindex(columns=PLAYER_COLUMNS)
    if eqs and not e.empty:
        qe = pd.concat(eqs, ignore_index=True).drop(columns=["liga", "temporada", "equipo"], errors="ignore")
        tk = ["team_id", "fase", "division"]
        qe = qe.drop_duplicates(tk).rename(columns={c: "pbp_" + c for c in qe.columns if c not in tk})
        e = e.drop(columns=[c for c in qe.columns if c in e.columns and c not in tk]).merge(qe, on=tk, how="left")
    return j, e, info


def diccionario() -> pd.DataFrame:
    base = pd.DataFrame(dictionary_records())
    ext = pd.DataFrame([{"columna": c, "grupo": "esf", "origen": "calculado (jugada a jugada / acta ESF)", "descripcion": d}
                        for c, d in EXT_SPEC])
    pbp = pd.DataFrame([{"columna": "pbp_" + c, "grupo": "quintetos_onoff", "origen": "calculado (jugada a jugada)",
                         "descripcion": d} for c, d in PLAYER_COLS
                        if c not in ("liga", "temporada", "fase", "team_id", "equipo", "player_id", "nombre")])
    return pd.concat([base, ext, pbp], ignore_index=True)


def escribir_indice_temporada(out_dir: Path, season: str, cfg: dict, resultados: list[dict]) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    idx = {"temporada": season, "ligas": {}}
    comp = []
    for liga in cfg["ligas"]:
        f = out_dir / "jugadores" / f"{liga}.csv"
        if not f.exists() or not cfg["ligas"][liga].get("activa", True):
            continue
        df = pd.read_csv(f, low_memory=False)
        idx["ligas"][liga] = {"nombre": cfg["ligas"][liga]["nombre"], "filas": len(df),
                              "fases": df.drop_duplicates("fase").sort_values("fase_orden")["fase"].tolist(),
                              "filas_por_fase": df["fase"].value_counts().to_dict()}
        idx["ligas"][liga]["divisiones"] = sorted(df["division"].dropna().unique().tolist())
        for (fase, dv), g in df.groupby(["fase", "division"]):
            r = (g.notna().mean() * 100).round(1)
            r.name = f"{liga}|{fase}|{dv}"
            comp.append(r)
    for r in resultados:
        if r["liga"] in idx["ligas"]:
            idx["ligas"][r["liga"]].update({k: r[k] for k in ("estado", "partidos_calendario", "partidos_con_acta",
                                                               "archivo_bruto", "errores")})
    (out_dir / "indice.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    if comp:
        pd.concat(comp, axis=1).reindex(PLAYER_COLUMNS).to_csv(out_dir / "completitud.csv", encoding="utf-8")
    diccionario().to_csv(out_dir / "diccionario_columnas.csv", index=False, encoding="utf-8")


def escribir_indice_global(root: Path, cfg: dict) -> None:
    root = Path(root)
    out = {"temporadas": [], "ligas": {k: v["nombre"] for k, v in cfg["ligas"].items()}}
    for d in sorted([p for p in root.iterdir() if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}", p.name)], reverse=True):
        f = d / "indice.json"
        if f.exists():
            i = json.loads(f.read_text(encoding="utf-8"))
            out["temporadas"].append({"temporada": d.name, "ligas": {k: {"filas": v["filas"], "fases": v["fases"],
                                                                         "partidos_con_acta": v.get("partidos_con_acta"),
                                                                         "partidos_calendario": v.get("partidos_calendario")}
                                                                     for k, v in i["ligas"].items()}})
    (root / "temporadas.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    diccionario().to_csv(root / "diccionario_columnas.csv", index=False, encoding="utf-8")
