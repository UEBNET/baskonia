"""Motor de métricas: a partir de totales de jugador + equipo + rival calcula, con las MISMAS
fórmulas para todas las ligas, la estadística por partido/36/40/100 posesiones, eficiencia de
tiro, ratios avanzados y ratings (PER, ORtg/DRtg, Win Shares, PIE, Game Score, ...).

Convenciones:
  * Todos los porcentajes en escala 0-100.
  * División por cero o dato ausente -> NaN (celda en blanco), nunca se elimina la fila.
  * Fórmulas de Basketball-Reference (Dean Oliver / John Hollinger), parametrizadas por la
    duración del partido de cada liga (40' FIBA, 48' NBA).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .schema import (COLUMN_NAMES, COUNTING_NAMES, RATE_BASE, SOURCE_METRIC_NAMES, TEAM_STATS)

_TEAM_SUMMABLE = [s for s in TEAM_STATS if s not in {"gp", "w", "l"}]


def _div(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.asarray(a, dtype="float64") / np.asarray(b, dtype="float64")
    r = np.where(np.isfinite(r), r, np.nan)
    return pd.Series(r, index=a.index if isinstance(a, pd.Series) else b.index)


def _num(df: pd.DataFrame, cols) -> pd.DataFrame:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        df = pd.concat([df, pd.DataFrame(np.nan, index=df.index, columns=missing)], axis=1)
    df[list(cols)] = df[list(cols)].apply(pd.to_numeric, errors="coerce")
    return df


# ---------------------------------------------------------------------------------------------
# Contexto de equipo y liga
# ---------------------------------------------------------------------------------------------
def build_team_context(players: pd.DataFrame, teams: pd.DataFrame, game_min: float,
                       coef_tl: float = 0.4) -> pd.DataFrame:
    """Completa la tabla de equipos (sumando jugadores donde falte) y calcula posesiones/ritmo.

    `coef_tl`: fracción de los tiros libres intentados que cierra una posesión. 0,4 (0,44 en la fórmula
    simple) en ligas con dos tiros libres por falta. En ligas de tiro libre único (G League) cada visita a
    la línea es un solo intento, así que el coeficiente es mucho mayor: se configura en `coef_tl_posesion`.
    """
    team_cols = [f"team_{s}" for s in TEAM_STATS] + [f"opp_{s}" for s in _TEAM_SUMMABLE]
    teams = teams.copy() if teams is not None and len(teams) else pd.DataFrame(columns=["team_id"])
    teams["team_id"] = teams["team_id"].astype(str)
    teams = _num(teams, team_cols)

    # Totales reconstruidos desde jugadores (para rellenar huecos, nunca sobrescribir)
    agg = players.groupby("team_id", dropna=False)[[s for s in _TEAM_SUMMABLE if s in players]].sum(min_count=1)
    agg.columns = [f"team_{c}" for c in agg.columns]
    gp = players.groupby("team_id", dropna=False)["gp"].max().rename("team_gp")
    agg = agg.join(gp)
    agg.index = agg.index.astype(str)
    teams = teams.set_index("team_id")
    missing = [t for t in agg.index if t not in teams.index]
    if missing:
        teams = pd.concat([teams, pd.DataFrame(index=pd.Index(missing, name="team_id"))])
        teams = _num(teams, team_cols)
    for c in agg.columns:
        teams[c] = teams[c].fillna(agg[c].reindex(teams.index))
    teams = teams.reset_index().rename(columns={"index": "team_id"})

    # Minutos: algunas fuentes publican minutos de partido (40/48 x G) en vez de minutos-jugador
    for pfx in ("team_", "opp_"):
        per_game = _div(teams[f"{pfx}min"], teams["team_gp"])
        teams[f"{pfx}min"] = np.where(per_game < 70, teams[f"{pfx}min"] * 5, teams[f"{pfx}min"])
    teams["opp_min"] = teams["opp_min"].fillna(teams["team_min"])

    t, o = (lambda c: teams[f"team_{c}"]), (lambda c: teams[f"opp_{c}"])
    c_full, c_simple = coef_tl, coef_tl + 0.04
    t_part = (t("fga") + c_full * t("fta")
              - 1.07 * _div(t("oreb"), t("oreb") + o("dreb")) * (t("fga") - t("fgm")) + t("tov"))
    o_part = (o("fga") + c_full * o("fta")
              - 1.07 * _div(o("oreb"), o("oreb") + t("dreb")) * (o("fga") - o("fgm")) + o("tov"))
    full = 0.5 * (t_part + o_part)
    simple = t("fga") + c_simple * t("fta") - t("oreb") + t("tov")
    teams["team_poss"] = full.fillna(simple)
    teams["opp_poss"] = full.fillna(o("fga") + c_simple * o("fta") - o("oreb") + o("tov")).fillna(teams["team_poss"])
    teams["team_pace"] = game_min * _div(teams["team_poss"] + teams["opp_poss"], 2 * (teams["team_min"] / 5))
    teams["team_ortg"] = 100 * _div(t("pts"), teams["team_poss"])
    teams["team_drtg"] = 100 * _div(o("pts"), teams["opp_poss"])
    teams["team_netrtg"] = teams["team_ortg"] - teams["team_drtg"]
    teams["calidad_contexto"] = np.where(o("fga").notna() & o("pts").notna(), "completo",
                                         np.where(t("fga").notna(), "parcial", "sin_contexto"))
    return teams


def league_context(teams: pd.DataFrame, game_min: float) -> dict:
    s = lambda c: teams[c].sum(min_count=1)  # noqa: E731
    lg = {c: s(f"team_{c}") for c in _TEAM_SUMMABLE + ["gp"]}
    lg["ft_pts"] = lg["pts"] - 2 * lg["fg2m"] - 3 * lg["fg3m"]
    lg["poss"] = s("team_poss")
    lg["pace"] = game_min * lg["poss"] / (lg["min"] / 5) if lg["min"] else np.nan
    lg["ortg"] = 100 * lg["pts"] / lg["poss"] if lg["poss"] else np.nan
    lg["pts_per_game"] = lg["pts"] / lg["gp"] if lg["gp"] else np.nan
    return {k: (float(v) if v is not None and not pd.isna(v) else np.nan) for k, v in lg.items()}


# ---------------------------------------------------------------------------------------------
# Métricas de jugador
# ---------------------------------------------------------------------------------------------
def compute_player_metrics(players: pd.DataFrame, teams: pd.DataFrame, game_min: float,
                           single_ft: bool = False, coef_tl: float = 0.4) -> pd.DataFrame:
    """`single_ft`: liga con tiro libre único que vale 2 o 3 puntos (G League). Entonces los puntos de
    tiro libre son pts - 2*T2 - 3*T3 y cada visita a la línea anota con probabilidad FT% (no 1-(1-FT%)^2)."""
    df = players.copy()
    df["team_id"] = df["team_id"].astype(str)
    df = _num(df, COUNTING_NAMES + SOURCE_METRIC_NAMES)
    # Jugadores traspasados que la fuente agrega en una fila ("ASV;ULK"): contexto del último equipo
    known = set(teams["team_id"].astype(str)) if teams is not None and len(teams) else set()
    orig_team = df["team_id"].copy()
    multi = df["team_id"].str.contains(";", regex=False)
    if multi.any():
        df.loc[multi, "team_id"] = df.loc[multi, "team_id"].map(
            lambda t: next((x for x in reversed(t.split(";")) if not known or x in known), t.split(";")[-1]))
    teams = build_team_context(df, teams, game_min, coef_tl=coef_tl)
    lg = league_context(teams, game_min)

    ctx_cols = [c for c in teams.columns if c.startswith(("team_", "opp_")) and c != "team_id"]
    df = df.drop(columns=[c for c in ctx_cols + ["calidad_contexto"] if c in df.columns])
    df = df.copy().merge(teams[["team_id", "calidad_contexto"] + ctx_cols].copy(), on="team_id", how="left")
    df = df.assign(calidad_contexto=df["calidad_contexto"].fillna("sin_contexto"), lg_pace=lg["pace"],
                   lg_ortg=lg["ortg"], lg_pts_per_game=lg["pts_per_game"])

    o: dict[str, pd.Series] = {}
    c = lambda k: df[k]  # noqa: E731
    t = lambda k: df[f"team_{k}"]  # noqa: E731
    op = lambda k: df[f"opp_{k}"]  # noqa: E731
    mp, gp = c("min"), c("gp")
    tm_mp5 = t("min") / 5  # minutos de partido del equipo

    # PIR: si la fuente no lo publica se calcula con la fórmula oficial
    pir_calc = (c("pts") + c("reb") + c("ast") + c("stl") + c("blk") + c("pfd")
                - (c("fga") - c("fgm")) - (c("fta") - c("ftm")) - c("tov") - c("blka") - c("pf"))
    o["pir_calc"] = pir_calc
    df["pir"] = df["pir"].fillna(pir_calc)

    # --- tasas por partido / 36 / 40 / 100 posesiones ---
    on_court = df["team_poss"] * _div(mp, tm_mp5)
    o["poss_on_court"] = on_court
    o["min_pg"] = _div(mp, gp)
    for s in RATE_BASE:
        o[f"{s}_pg"] = _div(c(s), gp)
        o[f"{s}_p36"] = 36 * _div(c(s), mp)
        o[f"{s}_p40"] = 40 * _div(c(s), mp)
        o[f"{s}_p100"] = 100 * _div(c(s), on_court)

    # --- tiro ---
    tsa = c("fga") + 0.44 * c("fta")
    o.update({
        "fg_pct": 100 * _div(c("fgm"), c("fga")),
        "fg2_pct": 100 * _div(c("fg2m"), c("fg2a")),
        "fg3_pct": 100 * _div(c("fg3m"), c("fg3a")),
        "ft_pct": 100 * _div(c("ftm"), c("fta")),
        "efg_pct": 100 * _div(c("fgm") + 0.5 * c("fg3m"), c("fga")),
        "ts_pct": 100 * _div(c("pts"), 2 * tsa),
        "tsa": tsa,
        "pts_per_fga": _div(c("pts"), c("fga")),
        "pts_per_tsa": _div(c("pts"), tsa),
        "fg3a_rate": 100 * _div(c("fg3a"), c("fga")),
        "fta_rate": 100 * _div(c("fta"), c("fga")),
        "ft_per_fga": _div(c("ftm"), c("fga")),
        "fg2a_share": 100 * _div(c("fg2a"), c("fga")),
        "pct_pts_2": 100 * _div(2 * c("fg2m"), c("pts")),
        "pct_pts_3": 100 * _div(3 * c("fg3m"), c("pts")),
        "pct_pts_ft": 100 * _div(c("ftm"), c("pts")),
        "pct_pts_paint": 100 * _div(c("pts_paint"), c("pts")),
        "pct_pts_fastbreak": 100 * _div(c("pts_fastbreak"), c("pts")),
        "dunk_rate": 100 * _div(c("dunks"), c("fg2a")),
    })

    # --- ratios avanzados ---
    plays = c("fga") + 0.44 * c("fta") + c("tov")
    o.update({
        "min_pct": 100 * _div(mp, tm_mp5),
        "usg_pct": 100 * _div(plays * tm_mp5, mp * (t("fga") + 0.44 * t("fta") + t("tov"))),
        "ast_pct": 100 * _div(c("ast"), _div(mp, tm_mp5) * t("fgm") - c("fgm")),
        "tov_pct": 100 * _div(c("tov"), plays),
        "oreb_pct": 100 * _div(c("oreb") * tm_mp5, mp * (t("oreb") + op("dreb"))),
        "dreb_pct": 100 * _div(c("dreb") * tm_mp5, mp * (t("dreb") + op("oreb"))),
        "reb_pct": 100 * _div(c("reb") * tm_mp5, mp * (t("reb") + op("reb"))),
        "stl_pct": 100 * _div(c("stl") * tm_mp5, mp * df["opp_poss"]),
        "blk_pct": 100 * _div(c("blk") * tm_mp5, mp * (op("fga") - op("fg3a"))),
        "ast_to": _div(c("ast"), c("tov")),
        "ast_ratio": 100 * _div(c("ast"), plays + c("ast")),
        "tov_ratio": 100 * _div(c("tov"), plays + c("ast")),
        "stl_to_tov": _div(c("stl"), c("tov")),
        "blk_to_pf": _div(c("blk"), c("pf")),
        "stl_plus_blk_p40": 40 * _div(c("stl") + c("blk"), mp),
        "pfd_to_pf": _div(c("pfd"), c("pf")),
        "pts_share": 100 * _div(c("pts"), t("pts")),
        "reb_share": 100 * _div(c("reb"), t("reb")),
        "ast_share": 100 * _div(c("ast"), t("ast")),
        "fga_share": 100 * _div(c("fga"), t("fga")),
        "poss_used": plays,
    })

    # --- índices compuestos ---
    gmsc = (c("pts") + 0.4 * c("fgm") - 0.7 * c("fga") - 0.4 * (c("fta") - c("ftm")) + 0.7 * c("oreb")
            + 0.3 * c("dreb") + c("stl") + 0.7 * c("ast") + 0.7 * c("blk") - 0.4 * c("pf") - c("tov"))
    eff = (c("pts") + c("reb") + c("ast") + c("stl") + c("blk")
           - (c("fga") - c("fgm")) - (c("fta") - c("ftm")) - c("tov"))
    o.update({"game_score": gmsc, "game_score_pg": _div(gmsc, gp), "game_score_p40": 40 * _div(gmsc, mp),
              "eff": eff, "eff_pg": _div(eff, gp)})
    pie_num = (c("pts") + c("fgm") + c("ftm") - c("fga") - c("fta") + c("dreb") + 0.5 * c("oreb")
               + c("ast") + c("stl") + 0.5 * c("blk") - c("pf") - c("tov"))
    game_tot = sum((t(k) + op(k)) * w for k, w in [("pts", 1), ("fgm", 1), ("ftm", 1), ("fga", -1),
                                                    ("fta", -1), ("dreb", 1), ("oreb", 0.5), ("ast", 1),
                                                    ("stl", 1), ("blk", 0.5), ("pf", -1), ("tov", -1)])
    o["pie"] = 100 * _div(pie_num, game_tot)

    # --- PER (Hollinger) ---
    factor = (2 / 3) - _ratio(0.5 * lg["ast"], lg["fgm"]) / (2 * _ratio(lg["fgm"], lg["ftm"]))
    vop = _ratio(lg["pts"], lg["fga"] - lg["oreb"] + lg["tov"] + 0.44 * lg["fta"])
    drbp = _ratio(lg["reb"] - lg["oreb"], lg["reb"])
    tm_ast_fg = _div(t("ast"), t("fgm"))
    uper = _div(1, mp) * (
        c("fg3m") + (2 / 3) * c("ast") + (2 - factor * tm_ast_fg) * c("fgm")
        + _ft_points(df, "", single_ft) * 0.5 * (1 + (1 - tm_ast_fg) + (2 / 3) * tm_ast_fg)
        - vop * c("tov") - vop * drbp * (c("fga") - c("fgm"))
        - vop * 0.44 * (0.44 + 0.56 * drbp) * (c("fta") - c("ftm"))
        + vop * (1 - drbp) * (c("reb") - c("oreb")) + vop * drbp * c("oreb")
        + vop * c("stl") + vop * drbp * c("blk")
        - c("pf") * (_ratio(lg["ft_pts"] if single_ft else lg["ftm"], lg["pf"]) - 0.44 * _ratio(lg["fta"], lg["pf"]) * vop))
    aper = uper * _div(pd.Series(lg["pace"], index=df.index), df["team_pace"])
    w = mp.where(aper.notna(), 0).fillna(0)
    lg_aper = float((aper.fillna(0) * w).sum() / w.sum()) if w.sum() > 0 else np.nan
    o["uper"] = uper
    o["per"] = aper * (15 / lg_aper) if lg_aper and np.isfinite(lg_aper) else aper * np.nan

    # --- Rating ofensivo / defensivo individual (Dean Oliver) ---
    o.update(_oliver(df, lg, single_ft))

    # --- Win Shares ---
    lg_ppp = _ratio(lg["pts"], lg["poss"])
    mppw = 0.32 * lg["pts_per_game"] * _div(df["team_pace"], pd.Series(lg["pace"], index=df.index))
    ows = _div(o["pprod"] - 0.92 * lg_ppp * o["totposs"], mppw)
    dws = _div(_div(mp, t("min")) * df["opp_poss"] * (1.08 * lg_ppp - o["drtg"] / 100), mppw)
    o.update({"ows": ows, "dws": dws, "ws": ows + dws,
              "ws_per_40": 40 * _div(ows + dws, mp), "ws_per_48": 48 * _div(ows + dws, mp)})

    df["team_id"] = orig_team
    out = pd.concat([df, pd.DataFrame(o, index=df.index)], axis=1)
    out = out.loc[:, ~out.columns.duplicated(keep="last")]
    _normalize_source_pct(out)
    return out


def _ratio(a: float, b: float) -> float:
    try:
        return float(a) / float(b) if b and np.isfinite(b) else np.nan
    except (TypeError, ZeroDivisionError):
        return np.nan


def _ft_points(df: pd.DataFrame, prefix: str, single_ft: bool) -> pd.Series:
    """Puntos anotados de tiro libre (= TL anotados salvo en ligas de tiro libre único)."""
    ftm = df[f"{prefix}ftm"]
    if not single_ft:
        return ftm
    return (df[f"{prefix}pts"] - 2 * df[f"{prefix}fg2m"] - 3 * df[f"{prefix}fg3m"]).fillna(ftm)


def _oliver(df: pd.DataFrame, lg: dict, single_ft: bool = False) -> dict[str, pd.Series]:
    c = lambda k: df[k]  # noqa: E731
    t = lambda k: df[f"team_{k}"]  # noqa: E731
    op = lambda k: df[f"opp_{k}"]  # noqa: E731
    score_p = (lambda p: p) if single_ft else (lambda p: 1 - (1 - p) ** 2)  # noqa: E731
    miss_p = (lambda p: 1 - p) if single_ft else (lambda p: (1 - p) ** 2)  # noqa: E731
    mp, fg, fga, fta = c("min"), c("fgm"), c("fga"), c("fta")
    ft = c("ftm")  # tiros libres anotados (para probabilidades)
    ftp = _ft_points(df, "", single_ft)  # puntos de tiro libre
    t_ftp = _ft_points(df, "team_", single_ft)
    pts, fg3, ast, orb, tov = c("pts"), c("fg3m"), c("ast"), c("oreb"), c("tov")
    tm_mp = t("min")
    share = _div(mp, tm_mp / 5)

    ft_pct = _div(ft, fta).fillna(0)
    shot_pts = _div(pts - ftp, 2 * fga).fillna(0)
    q_ast = (share * (1.14 * _div(t("ast") - ast, t("fgm")))
             + _div((t("ast") / tm_mp) * mp * 5 - ast, (t("fgm") / tm_mp) * mp * 5 - fg) * (1 - share))
    fg_part = fg * (1 - 0.5 * shot_pts * q_ast)
    ast_part = 0.5 * _div((t("pts") - t_ftp) - (pts - ftp), 2 * (t("fga") - fga)) * ast
    ft_part = score_p(ft_pct) * 0.4 * fta
    tm_ft_pct = _div(t("ftm"), t("fta"))
    tm_sc_poss = t("fgm") + score_p(tm_ft_pct) * t("fta") * 0.4
    tm_orb_pct = _div(t("oreb"), t("oreb") + (op("reb") - op("oreb")))
    tm_play_pct = _div(tm_sc_poss, t("fga") + t("fta") * 0.4 + t("tov"))
    tm_orb_w = _div((1 - tm_orb_pct) * tm_play_pct,
                    (1 - tm_orb_pct) * tm_play_pct + tm_orb_pct * (1 - tm_play_pct))
    orb_part = orb * tm_orb_w * tm_play_pct
    orb_adj = 1 - _div(t("oreb"), tm_sc_poss) * tm_orb_w * tm_play_pct
    sc_poss = (fg_part + ast_part + ft_part) * orb_adj + orb_part
    fgx_poss = (fga - fg) * (1 - 1.07 * tm_orb_pct)
    ftx_poss = miss_p(ft_pct) * 0.4 * fta
    tot_poss = sc_poss + fgx_poss + ftx_poss + tov

    pprod_fg = 2 * (fg + 0.5 * fg3) * (1 - 0.5 * shot_pts * q_ast)
    pprod_ast = (2 * _div(t("fgm") - fg + 0.5 * (t("fg3m") - fg3), t("fgm") - fg) * 0.5
                 * _div((t("pts") - t_ftp) - (pts - ftp), 2 * (t("fga") - fga)) * ast)
    pprod_orb = orb * tm_orb_w * tm_play_pct * _div(t("pts"), tm_sc_poss)
    pprod = (pprod_fg + pprod_ast + ftp) * orb_adj + pprod_orb
    ortg = 100 * _div(pprod, tot_poss)

    # Defensa
    dor_pct = _div(op("oreb"), op("oreb") + t("dreb"))
    dfg_pct = _div(op("fgm"), op("fga"))
    fmwt = _div(dfg_pct * (1 - dor_pct), dfg_pct * (1 - dor_pct) + (1 - dfg_pct) * dor_pct)
    stops1 = c("stl") + c("blk") * fmwt * (1 - 1.07 * dor_pct) + c("dreb") * (1 - fmwt)
    opp_ft_pct = _div(op("ftm"), op("fta"))
    stops2 = ((_div(op("fga") - op("fgm") - t("blk"), tm_mp) * fmwt * (1 - 1.07 * dor_pct)
               + _div(op("tov") - t("stl"), tm_mp)) * mp
              + _div(c("pf"), t("pf")) * 0.4 * op("fta") * miss_p(opp_ft_pct))
    stops = stops1 + stops2
    stop_pct = _div(stops * op("min"), df["team_poss"] * mp)
    tm_drtg = 100 * _div(op("pts"), df["team_poss"])
    d_pts_sc = _div(op("pts"), op("fgm") + score_p(opp_ft_pct) * op("fta") * 0.4)
    drtg = tm_drtg + 0.2 * (100 * d_pts_sc * (1 - stop_pct) - tm_drtg)
    return {"pprod": pprod, "scposs": sc_poss, "totposs": tot_poss, "ortg": ortg,
            "floor_pct": 100 * _div(sc_poss, tot_poss), "stops": stops, "stop_pct": 100 * stop_pct,
            "drtg": drtg, "net_rtg": ortg - drtg}


def _normalize_source_pct(df: pd.DataFrame) -> None:
    """Las fuentes mezclan 0-1 y 0-100: se llevan todos los % oficiales a 0-100."""
    for col in SOURCE_METRIC_NAMES:
        if not col.endswith(("_pct", "_rate")) and not col.startswith("src_pct_") and col != "src_pie":
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        if s.notna().any() and s.abs().max() <= 1.5:
            df[col] = s * 100


def finalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Reordena al esquema canónico, añadiendo vacías las columnas que falten."""
    return df.reindex(columns=COLUMN_NAMES).copy()
