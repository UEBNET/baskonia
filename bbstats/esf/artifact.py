"""Datos del Artifact «Kerno Basque Analytics» (data/basko/artifact/, no versionado: se regenera).

    python -m bbstats.esf artifact

Ficheros (JSON comprimido con gzip y en base64, `.json.gz.txt`, como los demás Artifacts de Kerno):
  datos/indice.json                 temporadas, ligas, fases × división, cobertura y validación, diccionario
  datos/<temporada>/<liga>.json.gz.txt   jugadores (todas las fases × división y totales), equipos, partidos,
                                    quintetos principales por equipo
  datos/carreras.json.gz.txt        trayectoria por persona (uuid federado) en todas las temporadas y ligas
"""
from __future__ import annotations

import base64
import gzip
import json
import math
from pathlib import Path

import pandas as pd

from .construir import EXT_SPEC, diccionario
from .pipeline import load_config, ruta

JUG = ("player_id persona_uuid nombre dorsal team_id equipo club fase division fase_nombre fase_tipo fase_orden grupos "
       "cobertura gp gs min min_pg pts pts_pg reb_pg oreb_pg dreb_pg stl_pg tov_pg pf_pg pfd_pg pir pir_pg fga_pg "
       "fg3a_pg fta_pg plus_minus plus_minus_pg pts_p40 reb_p40 stl_p40 tov_p40 pfd_p40 pts_p100 fg_pct fg2_pct fg3_pct "
       "ft_pct efg_pct ts_pct fg3a_rate fta_rate usg_pct oreb_pct dreb_pct reb_pct stl_pct tov_pct pts_share min_pct "
       "per ortg drtg net_rtg ws ws_per_40 game_score_pg pie stop_pct registra_asistencias registra_tapones ast_pg blk_pg ast_pct ast_to "
       "frec_aro fg_pct_aro frec_pintura fg_pct_pintura frec_media fg_pct_media frec_triple_esquina fg3_pct_esquina "
       "frec_triple_frontal fg3_pct_frontal dist_tiro_media fga_con_coord "
       "pts_fastbreak pts_2ndchance pts_off_tov pts_paint pct_pts_contraataque pct_pts_segunda_oportunidad "
       "pct_pts_tras_perdida clutch_pts clutch_ts_pct clutch_pts_p40 pts_std game_score_max pts_max partidos_10_pts "
       "partidos_20_pts and1 pf_ofensivas pf_tiro pts_q1 pts_q2 pts_q3 pts_q4 pct_pts_segunda_mitad "
       "pbp_net_rtg_on pbp_net_rtg_off pbp_net_rtg_onoff pbp_net_rtg_aj_onoff pbp_ortg_on pbp_drtg_on pbp_rapm pbp_orapm "
       "pbp_drapm pbp_min_por_relevo pbp_relevos_por_partido pbp_titular_partidos pbp_pct_min_q4 pbp_clutch_min "
       "pbp_clutch_plus_minus pbp_quintetos_distintos pbp_min_pct_equipo team_pace team_ortg team_drtg team_netrtg").split()
EQ = ("team_id equipo club fase division fase_nombre fase_tipo fase_orden grupos divisiones_equipo entrenadores gp w l "
      "win_pct pts_pg opp_pts_pg margen_pg partidos_con_acta team_pace team_ortg team_drtg team_netrtg efg_pct opp_efg_pct "
      "ts_pct opp_ts_pct tov_pct opp_tov_pct oreb_pct dreb_pct ft_rate opp_ft_rate fg3a_rate opp_fg3a_rate fg_pct fg3_pct "
      "ft_pct pts_fastbreak pts_2ndchance pts_off_tov pts_paint clutch_pts fga_aro fga_pintura fga_media fg3a_esquina "
      "fg3a_frontal fga_con_coord pbp_net_rtg_aj pbp_ritmo pbp_min_clutch pbp_clutch_net_rtg pbp_quintetos_distintos "
      "pbp_quinteto_principal pbp_min_pct_quinteto_principal pbp_net_rtg_quinteto_principal pbp_jugadores_rotacion "
      "pbp_hhi_minutos").split()
PAR = ("game_id fecha fase division grupo jornada local_id local visitante_id visitante pts_local pts_visitante "
       "con_acta pbp_cuadra_marcador quintetos_validos").split()
QUI = "team_id fase division jugadores min poss net_rtg net_rtg_aj ortg drtg".split()


def _gz(obj) -> str:
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return base64.b64encode(gzip.compress(raw, 9)).decode("ascii")


def _tabla(df: pd.DataFrame, cols: list[str]) -> dict:
    cols = [c for c in cols if c in df.columns]
    d = df[cols].copy()
    num = d.select_dtypes(include="number").columns
    d[num] = d[num].round(3)
    filas = []
    for r in d.itertuples(index=False):
        filas.append([None if (isinstance(v, float) and not math.isfinite(v)) else
                      (int(v) if isinstance(v, float) and v.is_integer() else v) for v in r])
    return {"columnas": cols, "filas": filas}


def exportar(salida: str | Path | None = None) -> Path:
    cfg = load_config()
    proc = ruta(cfg, "procesado")
    out = Path(salida) if salida else ruta(cfg, "procesado").parent / "artifact"
    datos = out / "datos"
    datos.mkdir(parents=True, exist_ok=True)
    ligas = {k: v for k, v in cfg["ligas"].items() if v.get("activa", True)}
    indice = {"generado": pd.Timestamp.now(tz="UTC").isoformat(), "fuente": cfg["fuente"]["pagina_publica"],
              "ligas": {k: {"nombre": v["nombre"], "corto": v.get("nombre_corto"), "nivel": v.get("nivel"),
                            "divisiones": bool(v.get("divisiones"))} for k, v in ligas.items()},
              "temporadas": [], "cobertura": [], "totales": {}}
    carreras = []
    tot = {"partidos": 0, "con_acta": 0, "eventos": 0, "tiros": 0, "jugadores": set()}
    for d in sorted([p for p in proc.iterdir() if p.is_dir() and len(p.name) == 7], reverse=True):
        season, por_liga = d.name, {}
        for liga in ligas:
            fj = d / "jugadores" / f"{liga}.csv"
            fp = d / "partidos" / f"{liga}.csv"
            if not fp.exists():
                continue
            p = pd.read_csv(fp, dtype={"game_id": str, "local_id": str, "visitante_id": str}, low_memory=False)
            j = pd.read_csv(fj, dtype={"player_id": str, "team_id": str}, low_memory=False) if fj.exists() else pd.DataFrame()
            fe = d / "equipos" / f"{liga}.csv"
            e = pd.read_csv(fe, dtype={"team_id": str}, low_memory=False) if fe.exists() else pd.DataFrame()
            fq = d / "quintetos" / liga / "quintetos.csv.gz"
            q = pd.DataFrame()
            if fq.exists():
                q = pd.read_csv(fq, dtype={"team_id": str}, low_memory=False)
                for sub in ("division_A1", "division_A2"):
                    f2 = d / "quintetos" / liga / sub / "quintetos.csv.gz"
                    if f2.exists():
                        q = pd.concat([q, pd.read_csv(f2, dtype={"team_id": str}, low_memory=False)], ignore_index=True)
                q = q[q["min"] >= 8].sort_values("min", ascending=False).groupby(["team_id", "fase", "division"]).head(8)
            pj = p[p["jugado"]] if "jugado" in p else p
            ev = d / "eventos" / f"{liga}.csv.gz"
            n_ev = int(pd.read_csv(ev, usecols=["orden"]).shape[0]) if ev.exists() else 0
            ti = d / "tiros" / f"{liga}.csv.gz"
            n_ti = int(pd.read_csv(ti, usecols=["valor"]).shape[0]) if ti.exists() else 0
            con = int(pj["con_acta"].sum()) if "con_acta" in pj else 0
            cob = {"temporada": season, "liga": liga, "partidos": len(pj), "con_acta": con, "eventos": n_ev, "tiros": n_ti,
                   "pbp_cuadra_pct": round(100 * float(pj["pbp_cuadra_marcador"].fillna(False).astype(bool).sum()) / con, 1) if con else None,
                   "quintetos_validos_pct": round(100 * float(pj["quintetos_validos"].fillna(False).astype(bool).sum()) / con, 1) if con else None,
                   "jugadores": int(j.loc[j["fase"] == "total", "player_id"].nunique()) if not j.empty else 0,
                   "equipos": int(pd.concat([pj["local_id"], pj["visitante_id"]]).nunique())}
            indice["cobertura"].append(cob)
            tot["partidos"] += len(pj)
            tot["con_acta"] += con
            tot["eventos"] += n_ev
            tot["tiros"] += n_ti
            if not j.empty:
                tot["jugadores"].update(j.loc[j["fase"] == "total", "persona_uuid"].fillna(j["player_id"]))
            unidades = (j.drop_duplicates(["fase", "division"]).sort_values("fase_orden")[["fase", "division", "fase_nombre", "fase_tipo"]]
                        .to_dict("records") if not j.empty else [])
            if not unidades and not e.empty:
                unidades = e.drop_duplicates(["fase", "division"]).sort_values("fase_orden")[["fase", "division", "fase_nombre", "fase_tipo"]].to_dict("records")
            por_liga[liga] = {"unidades": unidades, "con_acta": con, "partidos": len(pj)}
            (datos / season).mkdir(exist_ok=True)
            doc = {"temporada": season, "liga": liga, "jugadores": _tabla(j, JUG) if not j.empty else None,
                   "equipos": _tabla(e, EQ) if not e.empty else None, "partidos": _tabla(p, PAR),
                   "quintetos": _tabla(q, QUI) if not q.empty else None}
            (datos / season / f"{liga}.json.gz.txt").write_text(_gz(doc), encoding="ascii")
            if not j.empty:
                t = j[(j["fase"] == "total") & (j["gp"].fillna(0) > 0)]
                def v(x, d=1):
                    try:
                        x = float(x)
                    except (TypeError, ValueError):
                        return None
                    return round(x, d) if math.isfinite(x) else None
                for r in t.to_dict("records"):
                    pid = r.get("persona_uuid") if isinstance(r.get("persona_uuid"), str) else r.get("player_id")
                    carreras.append([pid, season, liga, r.get("equipo") if isinstance(r.get("equipo"), str) else None,
                                     int(r.get("gp") or 0), v(r.get("min")), v(r.get("pts_pg")), v(r.get("reb_pg")),
                                     v(r.get("ts_pct")), v(r.get("usg_pct")), v(r.get("per")),
                                     r.get("nombre") if isinstance(r.get("nombre"), str) else None])
        indice["temporadas"].append({"temporada": season, "ligas": por_liga})
    indice["totales"] = {k: (len(v) if isinstance(v, set) else v) for k, v in tot.items()}
    dic = diccionario()
    indice["diccionario"] = dic.where(dic.notna(), None).to_dict("records")
    (datos / "indice.json").write_text(json.dumps(indice, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (datos / "carreras.json.gz.txt").write_text(_gz({"columnas": ["id", "temporada", "liga", "equipo", "gp", "min", "pts_pg",
                                                                  "reb_pg", "ts_pct", "usg_pct", "per", "nombre"],
                                                     "filas": carreras}), encoding="ascii")
    return out
