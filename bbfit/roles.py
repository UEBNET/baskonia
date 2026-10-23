"""Fase 3 — sistema de roles por minutos.

Unidad básica: la tabla partido × jugador reconstruida de los tramos de quinteto (tramos.csv.gz) y los tiros
(tiros.csv.gz) de cada liga-temporada con jugada a jugada. Donde no hay jugada a jugada suficiente se usa el
respaldo de caja (totales de temporada de ligas/<liga>.csv: min, gp, gs) marcado `fuente = box`.

Por partido: MIN, MIN% = minutos / duración real del partido (con prórrogas; 40' FIBA, 48' NBA y G League),
titular (en pista en el primer tramo), minutos CLOSE (últimos 5' de cada periodo >= 4 con |margen| <= 5 al
empezar el tramo; solape exacto de [t0, t1] con la ventana), minutos del 4.º cuarto, y conteos de uso de los
tiros: intentos propios y del equipo con él en pista (USG% de tiro = (FGA + c·FTA) / (FGA_eq + c·FTA_eq) en pista;
la fuente no da pérdidas por jugador y partido, ver docs/checkpoints/F3.md).

Roles (umbrales en configs/roles.yaml; las etiquetas en minutos se aplican como MIN% = minutos/40):
  RESIDUAL < 5'  ·  PROFUNDIDAD 5-15'  ·  ROTACIÓN 15-22'  ·  solape 22-25': TITULAR si GS% >= 50 % o CLOSE% >= 50 %,
  si no ROTACIÓN  ·  TITULAR >= 25'  ·  GO-TO-GUY: >= 22', top-2 de su equipo en GTI y GTI >= umbral, con
  GTI = Σ w_k·z_k sobre {USG%, PIE, % de canastas no asistidas, USG% clutch} (z dentro de liga-temporada).
  Muestra < N partidos → vector de probabilidad (reparto de estados de partido suavizado con Dirichlet), sin
  etiqueta dura.

Granularidad: competición × temporada × club × entrenador × tramo de rol (bbfit/cambios.py segmenta la serie
partido a partido; un cambio de entrenador abre tramo nuevo; un traspaso crea otro registro de equipo).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import cambios as C
from . import datos as D
from .config import DIR_MOD, cargar

DIR_ROLES = DIR_MOD / "roles"
DIR_CACHE = DIR_ROLES / "_cache"
ROLES = ["RESIDUAL", "PROFUNDIDAD", "ROTACION", "TITULAR", "GO_TO_GUY"]
SUMAS = ["sec", "dur_s", "titular", "sec_close", "sec_close_equipo", "sec_q4", "dur_q4", "pts", "fga", "fgm",
         "fg3a", "fg3m", "fta", "ftm", "fgm_asist", "ast", "fga_cl", "fta_cl", "team_fga_on", "team_fgm_on",
         "team_fta_on", "team_fga_on_cl", "team_fta_on_cl", "poss_on", "pm"]


def _cfg() -> dict:
    return cargar("roles")


# ------------------------------------------------------------------------------------- tabla por partido

def _fin_periodo(per: pd.Series, q: float) -> pd.Series:
    per = per.astype(int)
    return pd.Series(np.where(per <= 4, q * per, 4 * q + 300.0 * (per - 4)), index=per.index)


def _filas_equipo(tr: pd.DataFrame) -> pd.DataFrame:
    base = ["game_id", "fase", "periodo", "t0", "t1", "sec", "margen_inicio"]
    partes = []
    for side, other, sign in (("a", "b", 1), ("b", "a", -1)):
        d = tr[base].copy()
        d["team_id"], d["opp_id"], d["quinteto"] = tr[f"team_{side}"], tr[f"team_{other}"], tr[f"quinteto_{side}"]
        d["margen"] = sign * d["margen_inicio"]
        for k in ("pts", "fga", "fta", "oreb", "tov"):
            d[f"f_{k}"] = tr[f"{side}_{k}"]
        d["o_pts"] = tr[f"{other}_pts"]
        partes.append(d.drop(columns="margen_inicio"))
    return pd.concat(partes, ignore_index=True)


def partidos_jugador(liga: str, temp: str, cfg: dict, pos3: pd.DataFrame | None = None) -> pd.DataFrame:
    """Tabla partido × jugador (incluye ausencias entre su primer y último partido: jugo = False)."""
    tr = D.tramos(liga, temp)
    if tr.empty:
        return pd.DataFrame()
    pc = cfg["partido"]
    tr = tr[tr["fase"].isin(pc["fases"])]
    if tr.empty:
        return pd.DataFrame()
    gmin = D.minutos_partido(liga, cfg)
    q = gmin * 15.0                      # segundos por cuarto
    coef = float(pc["coef_tl"])
    win, marg = float(pc["ventana_cierre_s"]), float(pc["margen_cierre"])

    f = _filas_equipo(tr)
    f["p1"] = _fin_periodo(f["periodo"], q)
    ini = np.maximum(f["t0"], f["p1"] - win)
    fin = np.minimum(f["t1"], f["p1"])
    f["sec_close"] = np.where((f["periodo"] >= 4) & (f["margen"].abs() <= marg), np.clip(fin - ini, 0, None), 0.0)
    f["sec_q4"] = np.where(f["periodo"] == 4, f["sec"], 0.0)
    f["poss_on"] = f["f_fga"] - f["f_oreb"] + f["f_tov"] + coef * f["f_fta"]
    t0min = f.groupby(["game_id", "team_id"])["t0"].transform("min")
    f["titular"] = (f["t0"] == t0min).astype(int)
    # duración del partido (con prórrogas) y del 4.º cuarto
    maxp = tr.groupby("game_id")["periodo"].max()
    dur = _fin_periodo(maxp, q)
    eq = f.groupby(["game_id", "team_id"]).agg(sec_close_equipo=("sec_close", "sum")).reset_index()

    f["player_id"] = f["quinteto"].fillna("").str.split("|")
    x = f.explode("player_id")
    x = x[x["player_id"].notna() & (x["player_id"] != "")]
    g = x.groupby(["game_id", "fase", "team_id", "opp_id", "player_id"], sort=False)
    pj = g.agg(sec=("sec", "sum"), sec_close=("sec_close", "sum"), sec_q4=("sec_q4", "sum"),
               titular=("titular", "max"), poss_on=("poss_on", "sum"), f_pts=("f_pts", "sum"),
               o_pts=("o_pts", "sum")).reset_index()
    pj["pm"] = pj["f_pts"] - pj["o_pts"]
    pj = pj.drop(columns=["f_pts", "o_pts"])
    pj["dur_s"] = pj["game_id"].map(dur).astype(float)
    pj["dur_q4"] = np.where(pj["game_id"].map(maxp) >= 4, q, 0.0)
    pj = pj.merge(eq, on=["game_id", "team_id"], how="left")

    # tiros: intentos propios, canastas asistidas, asistencias dadas, y tiros del equipo con él en pista
    ti = D.tiros(liga, temp)
    cols0 = ["fga", "fgm", "fg3a", "fg3m", "fta", "ftm", "pts", "fgm_asist", "ast", "fga_cl", "fta_cl",
             "team_fga_on", "team_fgm_on", "team_fta_on", "team_fga_on_cl", "team_fta_on_cl"]
    if not ti.empty:
        ti = ti[ti["fase"].isin(pc["fases"]) & ti["game_id"].isin(pj["game_id"].unique())].copy()
    if ti.empty:
        for c in cols0:
            pj[c] = np.nan
    else:
        ti["campo"] = ti["tipo"].isin(["T2", "T3"])
        ti["tl"] = ti["tipo"] == "TL"
        p1 = _fin_periodo(ti["periodo"], q)
        ti["clutch"] = (ti["periodo"] >= 4) & (ti["t"] >= p1 - win) & (ti["margen_previo"].abs() <= marg)
        ti["fga"] = ti["campo"].astype(int)
        ti["fgm"] = (ti["campo"] & ti["anotado"]).astype(int)
        ti["fg3a"] = (ti["tipo"] == "T3").astype(int)
        ti["fg3m"] = ((ti["tipo"] == "T3") & ti["anotado"]).astype(int)
        ti["fta"] = ti["tl"].astype(int)
        ti["ftm"] = (ti["tl"] & ti["anotado"]).astype(int)
        ti["fgm_asist"] = (ti["campo"] & ti["anotado"] & ti["asistente_id"].notna()).astype(int)
        ti["fga_cl"] = (ti["campo"] & ti["clutch"]).astype(int)
        ti["fta_cl"] = (ti["tl"] & ti["clutch"]).astype(int)
        k = ["game_id", "team_id", "player_id"]
        own = ti.groupby(k)[["fga", "fgm", "fg3a", "fg3m", "fta", "ftm", "puntos", "fgm_asist", "fga_cl",
                             "fta_cl"]].sum().rename(columns={"puntos": "pts"}).reset_index()
        a = ti[ti["fgm_asist"] == 1].groupby(["game_id", "team_id", "asistente_id"]).size().rename("ast")
        a = a.reset_index().rename(columns={"asistente_id": "player_id"})
        on = ti[["game_id", "team_id", "quinteto", "fga", "fgm", "fta", "fga_cl", "fta_cl"]].copy()
        on["player_id"] = on["quinteto"].fillna("").str.split("|")
        on = on.explode("player_id")
        on = on[on["player_id"].notna() & (on["player_id"] != "")]
        on = on.groupby(k)[["fga", "fgm", "fta", "fga_cl", "fta_cl"]].sum()
        on.columns = ["team_fga_on", "team_fgm_on", "team_fta_on", "team_fga_on_cl", "team_fta_on_cl"]
        pj = pj.merge(own, on=k, how="left").merge(a, on=k, how="left").merge(on.reset_index(), on=k, how="left")
        for c in cols0:
            pj[c] = pj[c].fillna(0.0)
        if ti["asistente_id"].notna().sum() == 0:      # la fuente no enlaza asistencias: no es «0»
            pj["fgm_asist"] = np.nan
            pj["ast"] = np.nan

    # entrenador y fecha del partido; orden de partidos de cada equipo
    ep = D.entrenadores_partidos(liga, temp)
    tg = pj[["game_id", "fase", "team_id", "opp_id", "dur_s", "dur_q4", "sec_close_equipo"]].drop_duplicates(
        ["game_id", "team_id"])
    if not ep.empty:
        ep = ep.rename(columns={"equipo_id": "team_id"})[["game_id", "team_id", "fecha", "entrenador_id"]]
        ep = ep.drop_duplicates(["game_id", "team_id"])
        tg = tg.merge(ep, on=["game_id", "team_id"], how="left")
    else:
        tg["fecha"], tg["entrenador_id"] = np.nan, np.nan
    tg["_gnum"] = pd.to_numeric(tg["game_id"], errors="coerce")
    tg = tg.sort_values(["team_id", "fecha", "_gnum", "game_id"], na_position="last")
    tg["orden_equipo"] = tg.groupby("team_id").cumcount() + 1
    tg = tg.drop(columns="_gnum")
    pj = pj.merge(tg[["game_id", "team_id", "fecha", "entrenador_id", "orden_equipo"]], on=["game_id", "team_id"],
                  how="left")
    pj["jugo"] = pj["sec"] > 0

    # ausencias: partidos del equipo entre el primero y el último del jugador en los que no salió
    rango = pj.groupby(["team_id", "player_id"])["orden_equipo"].agg(["min", "max"]).reset_index()
    todo = rango.merge(tg, on="team_id")
    todo = todo[(todo["orden_equipo"] >= todo["min"]) & (todo["orden_equipo"] <= todo["max"])]
    falta = todo.merge(pj[["team_id", "player_id", "orden_equipo"]], how="left", indicator=True,
                       on=["team_id", "player_id", "orden_equipo"])
    falta = falta[falta["_merge"] == "left_only"].drop(columns=["_merge", "min", "max"])
    if len(falta):
        falta = falta.assign(sec=0.0, sec_close=0.0, sec_q4=0.0, titular=0, poss_on=0.0, pm=0.0, jugo=False)
        for c in cols0:
            falta[c] = 0.0 if pj[c].notna().any() else np.nan
        pj = pd.concat([pj, falta[pj.columns.intersection(falta.columns)]], ignore_index=True)
    pj["jugo"] = pj["jugo"].astype(bool)
    pj["titular"] = pj["titular"].fillna(0).astype(int)

    # derivadas por partido
    pj["min"] = pj["sec"] / 60.0
    pj["min_pct"] = pj["sec"] / pj["dur_s"]
    den = pj["team_fga_on"] + coef * pj["team_fta_on"]
    pj["usg_tiro"] = np.where(pj["jugo"] & (den > 0), 100 * (pj["fga"] + coef * pj["fta"]) / den.replace(0, np.nan),
                              np.nan)
    tsa = pj["fga"] + coef * pj["fta"]
    pj["ts_pct"] = np.where(tsa > 0, 100 * pj["pts"] / (2 * tsa.replace(0, np.nan)), np.nan)
    pj["close_share"] = np.where(pj["sec_close_equipo"] > 0, pj["sec_close"] / pj["sec_close_equipo"].replace(0, np.nan),
                                 np.nan)
    pj["rango_min"] = pj.groupby(["game_id", "team_id"])["sec"].rank(ascending=False, method="min")
    pj.loc[~pj["jugo"], "rango_min"] = np.nan
    pj["coef_tl"] = coef
    pj.insert(0, "temporada", temp)
    pj.insert(0, "liga", liga)
    pj["persona_id"] = D.persona(liga, pj["player_id"])
    if pos3 is not None and len(pos3):
        pp = pos3[pos3["liga"] == liga].set_index("player_id")["pos3"]
        pj["pos3"] = pj["player_id"].map(pp)
    else:
        pj["pos3"] = np.nan
    pj["fuente"] = "pbp"
    return pj.sort_values(["team_id", "orden_equipo", "sec"], ascending=[True, True, False]).reset_index(drop=True)


# ------------------------------------------------------------------------------------- reglas de rol

def umbrales_pct(cfg: dict) -> dict:
    r = cfg["roles"]
    ref = float(r["referencia_minutos"])
    return {"prof": r["umbral_profundidad_min"] / ref, "rot": r["umbral_rotacion_min"] / ref,
            "tit": r["umbral_titular_min"] / ref, "tit_seguro": r["umbral_titular_seguro_min"] / ref}


def clasificar(min_pct, gs_pct, close_pct, es_gtg, cfg: dict) -> np.ndarray:
    """Etiqueta por la regla de minutos (vectorizada). gs_pct/close_pct en 0-1 (NaN = desconocido)."""
    u = umbrales_pct(cfg)
    r = cfg["roles"]
    m = np.asarray(min_pct, float)
    gs = np.asarray(gs_pct, float)
    cl = np.asarray(close_pct, float)
    solape_tit = (np.nan_to_num(gs, nan=-1) >= r["gs_pct_solape"]) | (np.nan_to_num(cl, nan=-1) >= r["close_pct_solape"])
    out = np.select(
        [m < u["prof"], m < u["rot"], m < u["tit"], m < u["tit_seguro"]],
        ["RESIDUAL", "PROFUNDIDAD", "ROTACION", np.where(solape_tit, "TITULAR", "ROTACION")],
        default="TITULAR").astype(object)
    out[np.asarray(es_gtg, bool) & (m >= u["tit"])] = "GO_TO_GUY"
    out[np.isnan(m)] = None
    return out


def estado_partido(min_pct, titular, close_share, cfg: dict) -> np.ndarray:
    """Estado de rol de un partido (sin GO-TO-GUY, que es un rasgo del tramo)."""
    return clasificar(min_pct, np.asarray(titular, float), close_share, np.zeros(len(np.atleast_1d(min_pct)), bool), cfg)


# ------------------------------------------------------------------------------------- agregación

def agregar(pj: pd.DataFrame, keys: list[str], cfg: dict) -> pd.DataFrame:
    """Métricas complementarias de cada grupo (tramo o temporada) a partir de la tabla por partido."""
    coef = float(cfg["partido"]["coef_tl"])
    j = pj[pj["jugo"]]
    g = j.groupby(keys, sort=False, dropna=False)
    s = g[SUMAS].sum(min_count=1)
    s["gp"] = g.size()
    s["min_sd"] = g["min"].std()
    s["min_media"] = g["min"].mean()
    s["rango_min_medio"] = g["rango_min"].mean()
    s["inicio_orden"] = g["orden_equipo"].min()
    s["fin_orden"] = g["orden_equipo"].max()
    s["inicio_fecha"] = g["fecha"].min()
    s["fin_fecha"] = g["fecha"].max()
    s["n_playoffs"] = g["fase"].apply(lambda x: int((x == "playoffs").sum()))
    aus = pj[~pj["jugo"]].groupby(keys, dropna=False).size()
    s["ausencias"] = aus.reindex(s.index).fillna(0).astype(int)
    o = pd.DataFrame(index=s.index)
    o["gp"] = s["gp"]
    o["ausencias"] = s["ausencias"]
    o["n_playoffs"] = s["n_playoffs"]
    for c in ("inicio_orden", "fin_orden", "inicio_fecha", "fin_fecha"):
        o[c] = s[c]
    o["min_total"] = s["sec"] / 60
    o["min_pg"] = s["min_media"]
    o["min_pct"] = s["sec"] / s["dur_s"]
    o["gs_pct"] = s["titular"] / s["gp"]
    o["min_sd"] = s["min_sd"]
    o["min_cv"] = s["min_sd"] / s["min_media"]
    o["close_pct"] = np.where(s["sec_close_equipo"] > 0, s["sec_close"] / s["sec_close_equipo"].replace(0, np.nan), np.nan)
    o["min_close"] = s["sec_close"] / 60
    o["q4_share"] = np.where(s["dur_q4"] > 0, s["sec_q4"] / s["dur_q4"].replace(0, np.nan), np.nan)
    o["rango_min_equipo"] = s["rango_min_medio"]
    den = s["team_fga_on"] + coef * s["team_fta_on"]
    o["usg_pct"] = 100 * (s["fga"] + coef * s["fta"]) / den.replace(0, np.nan)
    o["intentos_uso"] = s["fga"] + coef * s["fta"]
    o["ast_pct"] = 100 * s["ast"] / (s["team_fgm_on"] - s["fgm"]).replace(0, np.nan)
    o["fgm"] = s["fgm"]
    o["fgm_no_asist"] = s["fgm"] - s["fgm_asist"]
    o["cuota_tiros_pista"] = 100 * s["fga"] / s["team_fga_on"].replace(0, np.nan)
    den_cl = s["team_fga_on_cl"] + coef * s["team_fta_on_cl"]
    o["usg_clutch_bruto"] = 100 * (s["fga_cl"] + coef * s["fta_cl"]) / den_cl.replace(0, np.nan)
    o["intentos_equipo_clutch"] = den_cl
    tsa = s["fga"] + coef * s["fta"]
    o["ts_pct"] = 100 * s["pts"] / (2 * tsa).replace(0, np.nan)
    o["pts"] = s["pts"]
    o["poss_on"] = s["poss_on"]
    o["pm_por40"] = 2400 * s["pm"] / s["sec"].replace(0, np.nan)
    return o.reset_index()


def _anexar_temporada(rec: pd.DataFrame, liga: str, temp: str) -> pd.DataFrame:
    """PIE, PER, USG%/AST% de caja, faltas recibidas (ligas/<liga>.csv, fase total) y on/off contraído y RAPM
    (quintetos/<liga>/jugadores.csv, fase total) del jugador-equipo-temporada."""
    lg = D.ligas(liga, temp)
    cols = {"pie": "pie", "per": "per", "usg_pct": "usg_pct_caja", "ast_pct": "ast_pct_caja", "pfd_p40": "pfd_p40",
            "nombre": "nombre", "gs": "gs_caja", "gp": "gp_caja", "min": "min_caja", "edad": "edad"}
    out = rec.copy()
    if not lg.empty:
        fase = "total" if (lg["fase"] == "total").any() else "regular"
        lg = lg[lg["fase"] == fase]
        lg = lg[[c for c in ["player_id", "team_id"] + list(cols) if c in lg]].rename(columns=cols)
        exacto = lg[~lg["team_id"].astype(str).str.contains(";")].drop_duplicates(["player_id", "team_id"])
        out = out.merge(exacto, on=["player_id", "team_id"], how="left")
        # traspasados fusionados por la fuente (EuroLeague/EuroCup «ASV;ULK»): valores del jugador (temporada)
        fus = lg[lg["team_id"].astype(str).str.contains(";")].drop_duplicates("player_id").set_index("player_id")
        if len(fus):
            falta = out["pie"].isna() & out["player_id"].isin(fus.index) if "pie" in out else None
            if falta is not None:
                for c in fus.columns.drop("team_id"):
                    out.loc[falta, c] = out.loc[falta, "player_id"].map(fus[c])
    jq = D.quintetos_fichero(liga, temp, "jugadores.csv")
    if not jq.empty:
        fase = "total" if (jq["fase"] == "total").any() else "regular"
        jq = jq[jq["fase"] == fase][["player_id", "team_id", "net_rtg_aj_onoff", "rapm", "orapm", "drapm", "rapm_poss"]]
        out = out.merge(jq.drop_duplicates(["player_id", "team_id"]), on=["player_id", "team_id"], how="left")
    for c in list(cols.values()) + ["net_rtg_aj_onoff", "rapm", "orapm", "drapm", "rapm_poss"]:
        if c not in out:
            out[c] = np.nan
    return out


def gti(rec: pd.DataFrame, cfg: dict, lg_no_asist: float) -> pd.DataFrame:
    """GTI = Σ w_k·z_k (z en la referencia de la liga-temporada: MIN% y partidos mínimos), con USG% clutch
    contraído hacia el USG% global y % no asistido contraído hacia la media de la liga."""
    c = cfg["gti"]
    r = rec.copy()
    k = float(c["k_clutch_intentos"])
    n = r["intentos_equipo_clutch"].fillna(0)
    r["usg_clutch"] = (n * r["usg_clutch_bruto"].fillna(0) + k * r["usg_pct"]) / (n + k)
    kf = float(c["k_no_asistidas_fgm"])
    r["pct_no_asistidas"] = 100 * (r["fgm_no_asist"] + kf * lg_no_asist) / (r["fgm"] + kf)
    if not np.isfinite(lg_no_asist):
        r["pct_no_asistidas"] = np.nan
    ref = (r["min_pct"] >= c["min_pct_referencia"]) & (r["gp"] >= c["partidos_referencia"])
    comp = {"usg": "usg_pct", "pie": "pie", "no_asistidas": "pct_no_asistidas", "usg_clutch": "usg_clutch"}
    num = np.zeros(len(r))
    wsum = np.zeros(len(r))
    wtot = 0.0
    for nombre, col in comp.items():
        w = float(c["pesos"].get(nombre, 0))
        v = pd.to_numeric(r[col], errors="coerce")
        base = v[ref]
        mu, sd = base.mean(), base.std()
        z = (v - mu) / sd if sd and np.isfinite(sd) and sd > 0 else pd.Series(np.nan, index=r.index)
        r[f"z_{nombre}"] = z
        ok = z.notna().to_numpy()
        num += np.where(ok, w * z.fillna(0).to_numpy(), 0)
        wsum += np.where(ok, w, 0)
        wtot += w
    r["gti"] = np.where(wsum > 0, num / np.where(wsum > 0, wsum, 1) * wtot, np.nan)
    r["gti_componentes"] = sum(r[f"z_{n}"].notna().astype(int) for n in comp)
    return r


def _etiquetar(rec: pd.DataFrame, cfg: dict, grupo_equipo: list[str]) -> pd.DataFrame:
    u = umbrales_pct(cfg)
    c = cfg["gti"]
    r = rec.copy()
    elegible = (r["min_pct"] >= u["tit"]) & r["gti"].notna()
    r["gti_rango_equipo"] = np.nan
    if elegible.any():
        best = r[elegible].groupby(grupo_equipo + ["player_id"], dropna=False)["gti"].transform("max")
        tmp = r[elegible].assign(_b=best)
        rk = tmp.drop_duplicates(grupo_equipo + ["player_id"]).groupby(grupo_equipo, dropna=False)["_b"].rank(
            ascending=False, method="min")
        mapa = dict(zip(zip(*[tmp.drop_duplicates(grupo_equipo + ["player_id"])[k] for k in grupo_equipo + ["player_id"]]), rk))
        r.loc[elegible, "gti_rango_equipo"] = [mapa[tuple(x)] for x in r.loc[elegible, grupo_equipo + ["player_id"]].to_numpy()]
    wtot = sum(float(v) for v in c["pesos"].values())
    es_gtg = (r["gti_rango_equipo"] <= c["top_equipo"]) & (r["gti"] >= float(c["umbral_absoluto_medio"]) * wtot)
    r["rol_regla"] = clasificar(r["min_pct"], r["gs_pct"], r["close_pct"], es_gtg.fillna(False), cfg)
    return r


def _probabilidades(pj: pd.DataFrame, rec: pd.DataFrame, keys: list[str], cfg: dict, pi: pd.Series) -> pd.DataFrame:
    """Recuento de estados de partido (GO-TO-GUY si el tramo es GO-TO-GUY y el partido es TITULAR), vector
    suavizado p_k = (n_k + α·π_k)/(n + α), entropía H_rol (bits) y etiqueta final."""
    r = rec.copy()
    a = float(cfg["roles"]["dirichlet_alpha"])
    j = pj[pj["jugo"]].merge(r[keys + ["rol_regla"]], on=keys, how="left")
    est = j["estado"].to_numpy(object).copy()
    est[(est == "TITULAR") & (j["rol_regla"].to_numpy(object) == "GO_TO_GUY")] = "GO_TO_GUY"
    j["estado5"] = est
    cnt = j.groupby(keys + ["estado5"], dropna=False).size().unstack(fill_value=0).reindex(columns=ROLES, fill_value=0)
    cnt.columns = [f"n_{k}" for k in ROLES]
    r = r.merge(cnt.reset_index(), on=keys, how="left")
    n = r[[f"n_{k}" for k in ROLES]].fillna(0).to_numpy(float)
    pri = np.array([pi.get(k, 0.0) for k in ROLES])
    pri = pri / pri.sum() if pri.sum() > 0 else np.full(len(ROLES), 1 / len(ROLES))
    p = (n + a * pri) / (n.sum(axis=1, keepdims=True) + a)
    for i, k in enumerate(ROLES):
        r[f"p_{k}"] = p[:, i]
    emp = n / np.maximum(n.sum(axis=1, keepdims=True), 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        h = -np.nansum(np.where(emp > 0, emp * np.log2(emp), 0), axis=1)
    r["H_rol"] = np.where(n.sum(axis=1) > 0, h, np.nan)
    r["H_rol_norm"] = r["H_rol"] / np.log2(len(ROLES))
    pequeno = r["gp"] < int(cfg["roles"]["n_partidos_minimo"])
    r["rol_probabilistico"] = pequeno
    r["rol"] = np.where(pequeno, None, r["rol_regla"])
    r["rol_mas_probable"] = np.array(ROLES)[p.argmax(axis=1)]
    r["rol_mas_probable"] = np.where(pequeno, r["rol_mas_probable"], r["rol_regla"])
    idx = {k: i for i, k in enumerate(ROLES)}
    r["probabilidad"] = [p[i, idx[k]] if isinstance(k, str) else np.nan for i, k in enumerate(r["rol_mas_probable"])]
    return r


# ------------------------------------------------------------------------------------- tramos de rol

def _bloques_entrenador(ent: np.ndarray, minimo: int) -> np.ndarray:
    """Bloques consecutivos con el mismo entrenador; los de menos de `minimo` partidos (interinos de 1-2
    partidos) toman el entrenador del bloque anterior (o del siguiente si es el primero) y se fusionan."""
    e = np.asarray(ent, dtype=object).copy()
    if len(e) == 0:
        return np.zeros(0, int)
    while True:
        b = np.concatenate([[0], np.cumsum(e[1:] != e[:-1])])
        ids, cnt = np.unique(b, return_counts=True)
        if len(ids) == 1:
            return b
        cortos = [i for i, n in enumerate(cnt) if n < minimo]
        if not cortos:
            return b
        i = cortos[0]
        vecino = ids[i - 1] if i > 0 else ids[i + 1]
        e[b == ids[i]] = e[b == vecino][0]


def _tramos_jugadores(pj: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, list[dict]]:
    """Asigna `tramo` (1, 2…) a cada fila: bloques por entrenador y, dentro, cambios detectados (BOCPD).
    Devuelve la tabla con la columna y la lista de inicios de tramo con su motivo y probabilidad."""
    cc = cfg["cambios"]
    j = pj[pj["jugo"]]
    # ruido partido a partido dentro de jugador (pooled) y media de la liga
    def ruido(col, suelo, filtro=None):
        d = j if filtro is None else j[filtro]
        v = d.groupby(["team_id", "player_id"])[col].agg(["var", "size"])
        v = v[v["size"] >= 5]
        s2 = float(np.average(v["var"], weights=v["size"] - 1)) if len(v) else np.nan
        return max(s2 if np.isfinite(s2) else 0.0, suelo ** 2)
    s2_min = ruido("min_pct", float(cc["ruido_sd_min_suelo"]))
    filtro_usg = j["min"] >= float(cc["usg_min_minutos"])
    hay_usg = j["usg_tiro"].notna().any()
    s2_usg = ruido("usg_tiro", 100 * float(cc["ruido_sd_usg_suelo"]), filtro_usg) / 1e4 if hay_usg else np.nan
    mu0 = [float(j["min_pct"].mean())] + ([float(j.loc[filtro_usg, "usg_tiro"].mean()) / 100] if hay_usg else [])
    v0 = [float(cc["prior_sd_media"]) ** 2] + ([float(cc["prior_sd_media_usg"]) ** 2] if hay_usg else [])
    s2 = [s2_min] + ([s2_usg] if hay_usg else [])
    pj = pj.copy()
    pj["tramo"] = np.nan
    inicios: list[dict] = []
    jugador_equipos = j.groupby("player_id")["team_id"].nunique()
    primer_equipo = j.sort_values(["fecha", "orden_equipo"]).drop_duplicates("player_id").set_index("player_id")["team_id"]
    for (team, pid), d in pj.groupby(["team_id", "player_id"], sort=False):
        d = d.sort_values("orden_equipo")
        jug = d[d["jugo"]]
        if jug.empty:
            continue
        ent = jug["entrenador_id"].fillna("__sin_dato__").to_numpy()
        bloque = _bloques_entrenador(ent, int(cc["bloque_entrenador_minimo"]))
        X = [jug["min_pct"].to_numpy()]
        if hay_usg:
            u = np.where(jug["min"].to_numpy() >= float(cc["usg_min_minutos"]), jug["usg_tiro"].to_numpy() / 100, np.nan)
            X.append(u)
        X = np.column_stack(X)
        etiqueta = np.zeros(len(jug), int)
        nt = 0
        for b in np.unique(bloque):
            ib = np.where(bloque == b)[0]
            segs, pi = C.segmentar(X[ib], mu0, v0, s2, cc)
            for si, (a0, a1) in enumerate(segs):
                nt += 1
                etiqueta[ib[a0]: ib[a1] + 1] = nt
                fila0 = jug.iloc[ib[a0]]
                if nt == 1:
                    motivo = "traspaso" if (jugador_equipos.get(pid, 1) > 1 and primer_equipo.get(pid) != team) else "inicio"
                    prob = np.nan
                elif si == 0:
                    motivo, prob = "entrenador", np.nan
                else:
                    motivo, prob = "cambio_detectado", float(pi[a0])
                inicios.append({"team_id": team, "player_id": pid, "tramo": nt, "motivo_inicio": motivo,
                                "prob_cambio": prob, "orden_inicio": int(fila0["orden_equipo"])})
        mapa = dict(zip(jug["orden_equipo"], etiqueta))
        orden = d["orden_equipo"].to_numpy()
        tr = pd.Series([mapa.get(o, np.nan) for o in orden]).ffill().bfill().to_numpy()
        pj.loc[d.index, "tramo"] = tr
    pj["tramo"] = pj["tramo"].astype("Int64")
    return pj, inicios


# ------------------------------------------------------------------------------------- liga-temporada

def procesar_liga_temporada(liga: str, temp: str, cfg: dict, pos3: pd.DataFrame) -> dict:
    """Devuelve {'partidos', 'tramos', 'temporada'} de una liga-temporada (PBP o respaldo de caja)."""
    val = D.validacion(liga, temp)
    ep = D.entrenadores_partidos(liga, temp)
    fases = cfg["partido"]["fases"]
    if len(val):
        n_univ = int(val["fase"].isin(fases).sum())
    else:
        n_univ = ep.loc[ep["fase"].isin(fases), "game_id"].nunique() if len(ep) else 0
    pj = partidos_jugador(liga, temp, cfg, pos3)
    n_pbp = pj["game_id"].nunique() if len(pj) else 0
    cobertura = n_pbp / n_univ if n_univ else (1.0 if n_pbp else 0.0)
    if pj.empty or cobertura < float(cfg["partido"]["cobertura_pbp_minima"]):
        return {"partidos": pd.DataFrame(), "tramos": pd.DataFrame(),
                "temporada": respaldo_caja(liga, temp, cfg, pos3, cobertura), "cobertura": cobertura}
    pj["estado"] = estado_partido(pj["min_pct"], pj["titular"], pj["close_share"], cfg)
    pj.loc[~pj["jugo"], "estado"] = None
    pi = pj.loc[pj["jugo"], "estado"].value_counts(normalize=True)
    pj, inicios = _tramos_jugadores(pj, cfg)
    j = pj[pj["jugo"]]
    tot_fgm = j["fgm"].sum()
    lg_no_asist = float((tot_fgm - j["fgm_asist"].sum()) / tot_fgm) if tot_fgm and j["fgm_asist"].notna().any() else np.nan
    pos = pj.drop_duplicates("player_id").set_index("player_id")

    # temporada (jugador-equipo)
    kt = ["team_id", "player_id"]
    temp_rec = agregar(pj, kt, cfg)
    temp_rec = _anexar_temporada(temp_rec, liga, temp)
    temp_rec = gti(temp_rec, cfg, lg_no_asist)
    temp_rec = _etiquetar(temp_rec, cfg, ["team_id"])
    temp_rec = _probabilidades(pj, temp_rec, kt, cfg, pi)

    # tramos (jugador-equipo-entrenador-tramo)
    ks = ["team_id", "player_id", "tramo"]
    ent = pj[pj["jugo"]].groupby(ks)["entrenador_id"].agg(lambda s: s.mode().iloc[0] if s.notna().any() else np.nan)
    sp = agregar(pj, ks, cfg)
    sp = sp.merge(ent.rename("entrenador_id").reset_index(), on=ks, how="left")
    sp = _anexar_temporada(sp, liga, temp)      # PIE/PER/RAPM: nivel temporada (ver F3.md)
    sp = gti(sp, cfg, lg_no_asist)
    sp = _etiquetar(sp, cfg, ["team_id"])
    sp = _probabilidades(pj, sp, ks, cfg, pi)
    ini = pd.DataFrame(inicios)
    if len(ini):
        sp = sp.merge(ini.drop(columns="orden_inicio"), on=ks, how="left")
    # covariables de cada cambio detectado o por entrenador
    cov_rows = []
    cc = cfg["cambios"]
    equipos = dict(tuple(pj.groupby("team_id", sort=False)))
    ant = sp.set_index(ks)
    for row in sp[sp["tramo"] > 1].to_dict("records"):
        cv = C.covariables_cambio(equipos[row["team_id"]], row["player_id"], int(row["inicio_orden"]),
                                  pos["pos3"].get(row["player_id"]), cc)
        clave = (row["team_id"], row["player_id"], row["tramo"] - 1)
        prev = ant.loc[clave] if clave in ant.index else None
        cv["rol_anterior"] = prev["rol_mas_probable"] if prev is not None else None
        cv["dif_min_pct"] = row["min_pct"] - prev["min_pct"] if prev is not None else np.nan
        cov_rows.append({**{k: row[k] for k in ks}, **cv})
    if cov_rows:
        sp = sp.merge(pd.DataFrame(cov_rows), on=ks, how="left")
    # rol de la temporada: dominante de cada tramo + modal ponderado por minutos
    def modal(df):
        w = df.groupby("rol_mas_probable")["min_total"].sum()
        return w.idxmax() if len(w) else None
    mod = sp.groupby(kt).apply(modal, include_groups=False).rename("rol_modal_minutos")
    seq = sp.sort_values("tramo").groupby(kt)["rol_mas_probable"].agg(lambda s: ">".join(map(str, s))).rename("secuencia_roles")
    ntr = sp.groupby(kt).size().rename("n_tramos")
    temp_rec = temp_rec.merge(pd.concat([mod, seq, ntr], axis=1).reset_index(), on=kt, how="left")
    # rol modal del jugador en toda la liga-temporada (varios equipos)
    modj = sp.groupby("player_id").apply(modal, include_groups=False).rename("rol_modal_jugador_liga")
    temp_rec["rol_modal_jugador_liga"] = temp_rec["player_id"].map(modj)
    for d in (temp_rec, sp):
        d.insert(0, "temporada", temp)
        d.insert(0, "liga", liga)
        d["persona_id"] = D.persona(liga, d["player_id"])
        d["pos3"] = d["player_id"].map(pos["pos3"])
        d["fuente"] = "pbp"
        d["cobertura_pbp"] = cobertura
        d["adapt_pct"] = np.nan        # fase 7
    return {"partidos": pj, "tramos": sp, "temporada": temp_rec, "cobertura": cobertura}


def respaldo_caja(liga: str, temp: str, cfg: dict, pos3: pd.DataFrame, cobertura: float) -> pd.DataFrame:
    """Sin jugada a jugada suficiente: totales de temporada (regular + playoffs) de ligas/<liga>.csv."""
    lg = D.ligas(liga, temp)
    if lg.empty:
        return pd.DataFrame()
    lg = lg[lg["fase"].isin(cfg["partido"]["fases"])].copy()
    for c in ("min", "gp", "gs", "pie", "per", "usg_pct", "ast_pct", "pfd", "pts", "fga", "fta"):
        lg[c] = pd.to_numeric(lg.get(c), errors="coerce")
    g = lg.groupby(["team_id", "player_id"])
    r = g[["min", "gp", "gs", "pfd", "pts", "fga", "fta"]].sum(min_count=1)
    # tasas de temporada: media ponderada por minutos de las fases
    for c in ("pie", "per", "usg_pct", "ast_pct"):
        r[c] = g.apply(lambda d, c=c: np.average(d[c], weights=d["min"]) if d[c].notna().any() and d["min"].sum() > 0
                       else np.nan, include_groups=False)
    r["nombre"] = g["nombre"].first()
    r = r.reset_index()
    gmin = D.minutos_partido(liga, cfg)
    out = pd.DataFrame({"team_id": r["team_id"], "player_id": r["player_id"], "nombre": r["nombre"]})
    out["gp"] = r["gp"]
    out["min_total"] = r["min"]
    out["min_pg"] = r["min"] / r["gp"]
    out["min_pct"] = r["min"] / (r["gp"] * gmin)          # sin prórrogas (la caja no las da): sesgo leve al alza
    out["gs_pct"] = r["gs"] / r["gp"]
    for c in ("close_pct", "q4_share", "min_sd", "min_cv", "pct_no_asistidas", "usg_clutch", "intentos_equipo_clutch",
              "usg_clutch_bruto", "fgm", "fgm_no_asist", "net_rtg_aj_onoff", "rapm"):
        out[c] = np.nan
    out["usg_pct"] = r["usg_pct"]
    out["ast_pct"] = r["ast_pct"]
    out["pie"], out["per"] = r["pie"], r["per"]
    out["pfd_p40"] = 40 * r["pfd"] / r["min"].replace(0, np.nan)
    out["rango_min_equipo"] = out.groupby("team_id")["min_total"].rank(ascending=False, method="min")
    out = gti(out, cfg, np.nan)
    out = _etiquetar(out, cfg, ["team_id"])
    pequeno = out["gp"] < int(cfg["roles"]["n_partidos_minimo"])
    out["rol_probabilistico"] = pequeno
    out["rol"] = np.where(pequeno, None, out["rol_regla"])
    out["rol_mas_probable"] = out["rol_regla"]
    out["probabilidad"] = np.nan          # sin partidos no hay reparto de estados
    for k in ROLES:
        out[f"p_{k}"] = np.where(out["rol_regla"] == k, 1.0, 0.0)
        out[f"n_{k}"] = np.nan
    out.loc[pequeno, [f"p_{k}" for k in ROLES]] = np.nan
    out["H_rol"] = np.nan
    out["rol_modal_minutos"] = out["rol_regla"]
    out["n_tramos"] = 1
    ep = D.entrenadores_partidos(liga, temp)
    if len(ep):
        ne = ep.groupby("equipo_id")["entrenador_id"].agg(lambda s: s.dropna().unique().tolist())
        out["entrenador_id"] = out["team_id"].map(lambda t: ne.get(t, [None])[0] if len(ne.get(t, [])) == 1 else np.nan)
        out["entrenadores_varios"] = out["team_id"].map(lambda t: len(ne.get(t, [])) > 1)
    out.insert(0, "temporada", temp)
    out.insert(0, "liga", liga)
    out["persona_id"] = D.persona(liga, out["player_id"])
    pp = pos3[pos3["liga"] == liga].set_index("player_id")["pos3"] if len(pos3) else pd.Series(dtype=object)
    out["pos3"] = out["player_id"].map(pp)
    out["fuente"] = "box"
    out["cobertura_pbp"] = cobertura
    out["adapt_pct"] = np.nan
    return out


# ------------------------------------------------------------------------------------- estructura de equipo

def estructura_equipos(temp_rec: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Jugadores por rol, reparto de minutos y de uso por rol y concentración (equipo-temporada)."""
    u = umbrales_pct(cfg)
    filas = []
    for (liga, temp, team), d in temp_rec.groupby(["liga", "temporada", "team_id"], sort=False):
        mins = d["min_total"].fillna(0).to_numpy()
        uso = (d["usg_pct"].fillna(0) * d["min_total"].fillna(0)).to_numpy()
        P = d[[f"p_{k}" for k in ROLES]].to_numpy(float)
        P = np.where(np.isnan(P), 0, P)
        fila = {"liga": liga, "temporada": temp, "team_id": team, "fuente": d["fuente"].iloc[0],
                "jugadores_usados": int((mins > 0).sum()),
                "rotacion": int((d["min_pct"] >= u["rot"]).sum()),
                "hhi_minutos": float(((mins / mins.sum()) ** 2).sum()) if mins.sum() else np.nan,
                "hhi_uso": float(((uso / uso.sum()) ** 2).sum()) if uso.sum() else np.nan,
                "cuota_uso_top1": float(np.sort(uso)[::-1][0] / uso.sum()) if uso.sum() else np.nan,
                "cuota_uso_top2": float(np.sort(uso)[::-1][:2].sum() / uso.sum()) if uso.sum() else np.nan,
                "cuota_min_top5": float(np.sort(mins)[::-1][:5].sum() / mins.sum()) if mins.sum() else np.nan,
                "entrenador_principal": d["entrenador_id"].mode().iloc[0] if "entrenador_id" in d and d["entrenador_id"].notna().any() else np.nan}
        for i, k in enumerate(ROLES):
            fila[f"n_{k}"] = int((d["rol_mas_probable"] == k).sum())
            fila[f"n_esperado_{k}"] = float(P[:, i].sum())
            fila[f"cuota_min_{k}"] = float((P[:, i] * mins).sum() / mins.sum()) if mins.sum() else np.nan
            fila[f"cuota_uso_{k}"] = float((P[:, i] * uso).sum() / uso.sum()) if uso.sum() else np.nan
        filas.append(fila)
    return pd.DataFrame(filas)


# ------------------------------------------------------------------------------------- orquestación

def _cache(temp: str, liga: str) -> Path:
    return DIR_CACHE / f"{temp}_{liga}.pkl"


def construir(temporadas: list[str] | None = None, ligas: list[str] | None = None, rehacer: bool = False) -> dict:
    """Procesa todas las ligas-temporada (reanudable: caché por liga-temporada en data/modelos/roles/_cache)."""
    cfg = _cfg()
    DIR_CACHE.mkdir(parents=True, exist_ok=True)
    temporadas = temporadas or D.temporadas()
    informe = {}
    for temp in temporadas:
        lgs = [l for l in D.ligas_temporada(temp) if not ligas or l in ligas]
        pendientes = [l for l in lgs if rehacer or not _cache(temp, l).exists()]
        if not pendientes:
            continue
        pos3 = D.pos3_temporada(temp)
        for liga in pendientes:
            t0 = time.time()
            res = procesar_liga_temporada(liga, temp, cfg, pos3)
            pd.to_pickle(res, _cache(temp, liga))
            informe[f"{liga}|{temp}"] = {"cobertura": round(res["cobertura"], 3), "seg": round(time.time() - t0, 1),
                                         "filas_temporada": len(res["temporada"])}
            print(f"[roles] {liga} {temp}: cobertura {res['cobertura']:.2f}, {len(res['temporada'])} jugador-equipo, "
                  f"{len(res['tramos'])} tramos, {time.time() - t0:.0f}s", flush=True)
    return informe


def consolidar() -> dict:
    """Une las cachés y escribe las salidas versionadas de data/modelos/roles/."""
    cfg = _cfg()
    DIR_ROLES.mkdir(parents=True, exist_ok=True)
    (DIR_ROLES / "partidos_jugador").mkdir(exist_ok=True)
    tramos, temps, por_temp = [], [], {}
    for p in sorted(DIR_CACHE.glob("*.pkl")):
        temp, liga = p.stem.split("_", 1)
        r = pd.read_pickle(p)
        if len(r["tramos"]):
            tramos.append(r["tramos"])
        if len(r["temporada"]):
            temps.append(r["temporada"])
        if len(r["partidos"]):
            por_temp.setdefault(temp, []).append(r["partidos"])
    sp = pd.concat(tramos, ignore_index=True)
    tr = pd.concat(temps, ignore_index=True)
    # tramos de caja (sin partido a partido): un registro = la temporada
    caja = tr[tr["fuente"] == "box"].copy()
    caja["tramo"] = 1
    caja["motivo_inicio"] = "temporada_caja"
    sp = pd.concat([sp, caja[[c for c in caja.columns if c in sp.columns or c == "tramo"]]], ignore_index=True)
    primero = ["liga", "temporada", "team_id", "player_id", "persona_id", "nombre", "pos3", "entrenador_id", "tramo",
               "fuente", "inicio_fecha", "fin_fecha", "inicio_orden", "fin_orden", "gp", "ausencias", "rol",
               "rol_mas_probable", "probabilidad", "rol_probabilistico", "motivo_inicio", "prob_cambio"]
    nom = tr.drop_duplicates(["liga", "temporada", "player_id"]).set_index(["liga", "temporada", "player_id"])["nombre"]
    sp["nombre"] = [nom.get(k, np.nan) for k in zip(sp["liga"], sp["temporada"], sp["player_id"])]
    sp = sp[[c for c in primero if c in sp] + [c for c in sp.columns if c not in primero]]
    sp = sp.rename(columns={"inicio_fecha": "inicio", "fin_fecha": "fin", "gp": "n_partidos"})
    sp.to_csv(DIR_ROLES / "player_role_spells.csv.gz", index=False, float_format="%.4f")
    primero_t = ["liga", "temporada", "team_id", "player_id", "persona_id", "nombre", "pos3", "fuente", "gp",
                 "rol", "rol_mas_probable", "rol_probabilistico", "probabilidad", "rol_modal_minutos",
                 "rol_modal_jugador_liga", "secuencia_roles", "n_tramos"]
    tr = tr[[c for c in primero_t if c in tr] + [c for c in tr.columns if c not in primero_t]]
    tr.to_csv(DIR_ROLES / "player_role_season.csv.gz", index=False, float_format="%.4f")
    est = estructura_equipos(tr, cfg)
    est.to_csv(DIR_ROLES / "team_role_structure.csv", index=False, float_format="%.4f")
    tam = {}
    for temp, partes in por_temp.items():
        d = pd.concat(partes, ignore_index=True)
        p = DIR_ROLES / "partidos_jugador" / f"{temp}.csv.gz"
        d.to_csv(p, index=False, float_format="%.4f")
        tam[temp] = round(p.stat().st_size / 1e6, 1)
    resumen = validar(tr, sp)
    resumen["tamanos_mb_partidos_jugador"] = tam
    (DIR_ROLES / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return resumen


def validar(tr: pd.DataFrame, sp: pd.DataFrame) -> dict:
    """Reparto de roles por competición y comprobaciones con casos conocidos."""
    DIR_ROLES.mkdir(parents=True, exist_ok=True)
    dist = (tr.assign(r=tr["rol_mas_probable"].fillna("NA"))
            .groupby(["liga", "r"]).size().unstack(fill_value=0))
    dist_pct = dist.div(dist.sum(axis=1), axis=0).round(4)
    dist_pct["n"] = dist.sum(axis=1)
    dist_pct.reset_index().to_csv(DIR_ROLES / "distribucion_roles.csv", index=False)
    # casos: máximos anotadores (pts totales) de cada liga-temporada → ¿GO-TO-GUY / TITULAR?
    t = tr.copy()
    t["pts_rank"] = t.groupby(["liga", "temporada"])["pts"].rank(ascending=False, method="first")
    top = t[t["pts_rank"] <= 10]
    casos = top.groupby("liga")["rol_mas_probable"].value_counts(normalize=True).unstack(fill_value=0).round(3)
    casos.reset_index().to_csv(DIR_ROLES / "validacion_top_anotadores.csv", index=False)
    banq = t[(t["min_pg"] < 5) & (t["gp"] >= 5)]
    ejemplos = t[(t["liga"].isin(["euroleague", "acb"])) & (t["pts_rank"] <= 3)][
        ["liga", "temporada", "nombre", "team_id", "min_pg", "usg_pct", "gti", "rol_mas_probable"]]
    ejemplos.to_csv(DIR_ROLES / "validacion_ejemplos.csv", index=False, float_format="%.3f")
    return {"filas_temporada": len(tr), "filas_tramos": len(sp),
            "fuente": tr["fuente"].value_counts().to_dict(),
            "rol_probabilistico_pct": float(tr["rol_probabilistico"].mean()),
            "top10_anotadores_gtg_pct": float((top["rol_mas_probable"] == "GO_TO_GUY").mean()),
            "top10_anotadores_gtg_o_titular_pct": float(top["rol_mas_probable"].isin(["GO_TO_GUY", "TITULAR"]).mean()),
            "menos5min_residual_pct": float((banq["rol_mas_probable"] == "RESIDUAL").mean()) if len(banq) else None,
            "tramos_por_jugador_equipo": float(len(sp) / max(len(tr), 1)),
            "motivos_inicio": sp["motivo_inicio"].value_counts().to_dict() if "motivo_inicio" in sp else {}}


def main(temporadas=None, ligas=None, rehacer=False) -> dict:
    from .registro import experimento
    cfg = _cfg()
    with experimento("roles", "reglas_minutos_bocpd", params={"roles": cfg["roles"], "gti": cfg["gti"],
                                                              "cambios": cfg["cambios"]},
                     semilla=cfg.get("semilla")) as run:
        construir(temporadas, ligas, rehacer)
        res = consolidar()
        run.metricas({k: v for k, v in res.items() if isinstance(v, (int, float)) and v is not None})
        for f in ("distribucion_roles.csv", "validacion_top_anotadores.csv", "resumen.json"):
            run.artefacto(DIR_ROLES / f)
    return res
