"""Métricas de quintetos, tríos, parejas, on/off, RAPM y redes de asistencias.

Todo se calcula a partir de los tramos (bbstats/lineups/stints.py) con las mismas fórmulas en todas las
ligas. Unidad de agregación = filas "equipo en el tramo": totales propios (f_*) y del rival (o_*).

Fórmulas (Dean Oliver / Basketball-Reference / pbpstats):
  posesiones    = TCI − RO + PER + c·TLI           (c = 0,44; en la G League el coeficiente de tiro libre único)
  ORtg / DRtg   = 100 · puntos / posesiones (propias / del rival);  Net = ORtg − DRtg
  *_aj          = ratings con contracción empírica bayesiana hacia la media de la liga:
                  (puntos + k·PPP_liga) / (posesiones + k) · 100   (k = `contraccion_posesiones`, 300 por defecto)
  eFG%, TS%, TOV%, OREB%/DREB%, FTr, 3PAr, AST% de canastas, STL%, BLK% (a favor y del rival)
  ritmo         = posesiones por partido completo de la liga (40 o 48 minutos)
  on/off        = unidad con el jugador en pista frente al resto de minutos de su equipo
  WOWY parejas  = Net con los dos, con A sin B, con B sin A y sin ninguno;
                  sinergia = Net(A+B) − [Net(A sin B) + Net(B sin A) − Net(ninguno)]  (modelo aditivo)
  RAPM          = regresión ridge ponderada por posesiones sobre los tramos (+1 atacantes, +1 defensores),
                  λ = `rapm_lambda`; ORAPM/DRAPM en puntos por 100 posesiones sobre la media (DRAPM > 0 = mejor)
  sinergia de quinteto = Net_aj del quinteto − suma del RAPM de sus 5 jugadores
  red de asistencias: pasador → anotador; centralidad PageRank ponderada por asistencias dentro del equipo,
                  concentración HHI de a quién asiste cada jugador.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from .stints import STAT_KEYS

PHASES = ["regular", "playoffs", "total"]


def team_rows(segments: pd.DataFrame) -> pd.DataFrame:
    """Dos filas por tramo (una por equipo) con estadísticas propias f_* y del rival o_*."""
    if segments.empty:
        return pd.DataFrame()
    base = ["game_id", "fase", "periodo", "t0", "t1", "sec", "clutch"]
    rows = []
    for side, other in (("a", "b"), ("b", "a")):
        d = segments[base].copy()
        d["team_id"] = segments[f"team_{side}"]
        d["opp_id"] = segments[f"team_{other}"]
        d["quinteto"] = segments[f"quinteto_{side}"]
        d["quinteto_rival"] = segments[f"quinteto_{other}"]
        sign = 1 if side == "a" else -1
        d["margen_inicio"] = sign * segments["margen_inicio"]
        for k in STAT_KEYS:
            d[f"f_{k}"] = segments[f"{side}_{k}"]
            d[f"o_{k}"] = segments[f"{other}_{k}"]
        rows.append(d)
    return pd.concat(rows, ignore_index=True)


SUM_COLS = ["sec"] + [f"f_{k}" for k in STAT_KEYS] + [f"o_{k}" for k in STAT_KEYS]


def _div(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(b != 0, a / b, np.nan)
    return out


def rate_metrics(s: pd.DataFrame, lg: dict, game_min: float, coef: float, k: float) -> pd.DataFrame:
    """Métricas de una tabla de sumas (columnas SUM_COLS)."""
    f = lambda c: s[f"f_{c}"].astype(float)  # noqa: E731
    o = lambda c: s[f"o_{c}"].astype(float)  # noqa: E731
    out = pd.DataFrame(index=s.index)
    poss_of = f("fga") - f("oreb") + f("tov") + coef * f("fta")
    poss_def = o("fga") - o("oreb") + o("tov") + coef * o("fta")
    mins = s["sec"].astype(float) / 60
    out["min"] = mins
    out["poss_of"] = poss_of
    out["poss_def"] = poss_def
    out["poss"] = (poss_of + poss_def) / 2
    out["pts_for"] = f("pts")
    out["pts_against"] = o("pts")
    out["plus_minus"] = f("pts") - o("pts")
    out["pm_por40"] = 40 * _div(out["plus_minus"], mins)
    out["ortg"] = 100 * _div(f("pts"), poss_of)
    out["drtg"] = 100 * _div(o("pts"), poss_def)
    out["net_rtg"] = out["ortg"] - out["drtg"]
    ppp = lg.get("ppp", np.nan)
    out["ortg_aj"] = 100 * _div(f("pts") + k * ppp, poss_of + k)
    out["drtg_aj"] = 100 * _div(o("pts") + k * ppp, poss_def + k)
    out["net_rtg_aj"] = out["ortg_aj"] - out["drtg_aj"]
    out["ritmo"] = game_min * _div(out["poss"], mins)
    for pre, g in (("", f), ("opp_", o)):
        out[f"{pre}efg_pct"] = 100 * _div(g("fgm") + 0.5 * g("fg3m"), g("fga"))
        out[f"{pre}ts_pct"] = 100 * _div(g("pts"), 2 * (g("fga") + coef * g("fta")))
        out[f"{pre}tov_pct"] = 100 * _div(g("tov"), g("fga") + coef * g("fta") + g("tov"))
        out[f"{pre}ft_rate"] = 100 * _div(g("fta"), g("fga"))
        out[f"{pre}fg3a_rate"] = 100 * _div(g("fg3a"), g("fga"))
        out[f"{pre}fg2_pct"] = 100 * _div(g("fg2m"), g("fg2a"))
        out[f"{pre}fg3_pct"] = 100 * _div(g("fg3m"), g("fg3a"))
        out[f"{pre}ft_pct"] = 100 * _div(g("ftm"), g("fta"))
        out[f"{pre}ast_pct"] = 100 * _div(g("ast"), g("fgm"))
    out["oreb_pct"] = 100 * _div(f("oreb"), f("oreb") + o("dreb"))
    out["dreb_pct"] = 100 * _div(f("dreb"), f("dreb") + o("oreb"))
    out["stl_pct"] = 100 * _div(f("stl"), poss_def)
    out["blk_pct"] = 100 * _div(f("blk"), o("fg2a"))
    out["pf_por100"] = 100 * _div(f("pf"), poss_def)
    out["opp_pf_por100"] = 100 * _div(o("pf"), poss_of)
    return out


def league_context(rows: pd.DataFrame, coef: float) -> dict:
    s = rows[SUM_COLS].sum()
    poss = s["f_fga"] - s["f_oreb"] + s["f_tov"] + coef * s["f_fta"]
    return {"ppp": float(s["f_pts"] / poss) if poss else np.nan}


def _sum_by(rows: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    g = rows.groupby(keys, sort=False)
    out = g[SUM_COLS].sum()
    out["gp"] = g["game_id"].nunique()
    out["tramos"] = g.size()
    return out.reset_index()


def explode_units(rows: pd.DataFrame, size: int) -> pd.DataFrame:
    """Una fila por (tramo-equipo, combinación de `size` jugadores del quinteto)."""
    if size == 5:
        d = rows.copy()
        d["unidad"] = d["quinteto"]
        return d
    combos = rows["quinteto"].map(lambda q: ["|".join(c) for c in itertools.combinations(q.split("|"), size)]
                                  if q and q.count("|") == 4 else [])
    d = rows.assign(unidad=combos).explode("unidad")
    return d[d["unidad"].notna()]


def unit_table(rows: pd.DataFrame, size: int, lg: dict, game_min: float, coef: float, k: float) -> pd.DataFrame:
    d = explode_units(rows[rows["quinteto"].str.count(r"\|") == 4], size)
    if d.empty:
        return pd.DataFrame()
    s = _sum_by(d, ["team_id", "unidad"])
    team_sec = rows.groupby("team_id")["sec"].sum()
    m = rate_metrics(s, lg, game_min, coef, k)
    out = pd.concat([s[["team_id", "unidad", "gp", "tramos"] + SUM_COLS], m], axis=1)
    out["min_pct_equipo"] = 100 * _div(s["sec"], s["team_id"].map(team_sec))
    out["n_jugadores"] = size
    return out


def onoff_table(rows: pd.DataFrame, lg: dict, game_min: float, coef: float, k: float) -> pd.DataFrame:
    full = rows[rows["quinteto"].str.count(r"\|") == 4]
    d = explode_units(full, 1).rename(columns={"unidad": "player_id"})
    if d.empty:
        return pd.DataFrame()
    on = _sum_by(d, ["team_id", "player_id"])
    team = full.groupby("team_id")[SUM_COLS].sum()
    off = on[["team_id", "player_id"]].copy()
    for c in SUM_COLS:
        off[c] = on["team_id"].map(team[c]).values - on[c].values
    m_on = rate_metrics(on, lg, game_min, coef, k)
    m_off = rate_metrics(off, lg, game_min, coef, k)
    out = on[["team_id", "player_id", "gp", "tramos"]].copy()
    keep = ["min", "poss", "pts_for", "pts_against", "plus_minus", "pm_por40", "ortg", "drtg", "net_rtg", "ortg_aj",
            "drtg_aj", "net_rtg_aj", "ritmo", "efg_pct", "opp_efg_pct", "ts_pct", "opp_ts_pct", "tov_pct",
            "opp_tov_pct", "oreb_pct", "dreb_pct", "ft_rate", "opp_ft_rate", "fg3a_rate", "opp_fg3a_rate", "ast_pct"]
    for c in keep:
        out[f"{c}_on"] = m_on[c].values
        out[f"{c}_off"] = m_off[c].values
    for c in ["ortg", "drtg", "net_rtg", "net_rtg_aj", "ritmo", "efg_pct", "opp_efg_pct", "ts_pct", "opp_ts_pct",
              "tov_pct", "opp_tov_pct", "oreb_pct", "dreb_pct", "ft_rate", "opp_ft_rate", "fg3a_rate", "ast_pct"]:
        out[f"{c}_onoff"] = out[f"{c}_on"] - out[f"{c}_off"]
    out["min_pct_equipo"] = 100 * _div(on["sec"], on["team_id"].map(team["sec"]))
    out["quintetos_distintos"] = d.groupby(["team_id", "player_id"])["quinteto"].nunique().reindex(
        pd.MultiIndex.from_frame(out[["team_id", "player_id"]])).values
    # clutch: últimos 5 minutos del último cuarto o prórroga con ±5 puntos
    cl = d[d["clutch"]]
    if not cl.empty:
        cs = _sum_by(cl, ["team_id", "player_id"])
        cm = rate_metrics(cs, lg, game_min, coef, k)
        cs = pd.concat([cs[["team_id", "player_id"]], cm[["min", "plus_minus", "net_rtg", "net_rtg_aj"]]
                        .add_prefix("clutch_")], axis=1)
        out = out.merge(cs, on=["team_id", "player_id"], how="left")
    return out


def wowy_pairs(rows: pd.DataFrame, pairs: pd.DataFrame, onoff_sums: pd.DataFrame, lg: dict, game_min: float,
               coef: float, k: float) -> pd.DataFrame:
    """Con/sin para cada pareja: ambos, A sin B, B sin A, ninguno."""
    if pairs.empty:
        return pairs
    full = rows[rows["quinteto"].str.count(r"\|") == 4]
    team = full.groupby("team_id")[SUM_COLS].sum()
    on = onoff_sums.set_index(["team_id", "player_id"])[SUM_COLS]
    ab = pairs["unidad"].str.split("|", expand=True)
    sums_both = pairs[SUM_COLS]
    res = {}
    a_on = on.reindex(pd.MultiIndex.from_arrays([pairs["team_id"], ab[0]])).values
    b_on = on.reindex(pd.MultiIndex.from_arrays([pairs["team_id"], ab[1]])).values
    tot = team.reindex(pairs["team_id"]).values
    bo = sums_both.values
    parts = {"a_sin_b": a_on - bo, "b_sin_a": b_on - bo, "ninguno": tot - a_on - b_on + bo}
    for name, arr in parts.items():
        df = pd.DataFrame(arr, columns=SUM_COLS, index=pairs.index)
        m = rate_metrics(df, lg, game_min, coef, k)
        res[f"min_{name}"] = m["min"]
        res[f"net_rtg_{name}"] = m["net_rtg"]
        res[f"net_rtg_aj_{name}"] = m["net_rtg_aj"]
    out = pd.DataFrame(res, index=pairs.index)
    out["sinergia"] = pairs["net_rtg_aj"] - (out["net_rtg_aj_a_sin_b"] + out["net_rtg_aj_b_sin_a"]
                                             - out["net_rtg_aj_ninguno"])
    return out


def on_sums(rows: pd.DataFrame) -> pd.DataFrame:
    full = rows[rows["quinteto"].str.count(r"\|") == 4]
    d = explode_units(full, 1).rename(columns={"unidad": "player_id"})
    return _sum_by(d, ["team_id", "player_id"]) if not d.empty else pd.DataFrame(columns=["team_id", "player_id"] + SUM_COLS)


def rapm(rows: pd.DataFrame, coef: float, lam: float) -> pd.DataFrame:
    """RAPM ridge ponderado por posesiones. Devuelve player_id, orapm, drapm, rapm, poss."""
    full = rows[(rows["quinteto"].str.count(r"\|") == 4) & (rows["quinteto_rival"].str.count(r"\|") == 4)]
    if full.empty:
        return pd.DataFrame(columns=["player_id", "orapm", "drapm", "rapm", "rapm_poss"])
    poss = (full["f_fga"] - full["f_oreb"] + full["f_tov"] + coef * full["f_fta"]).to_numpy(float)
    keep = poss > 0
    full, poss = full[keep], poss[keep]
    pts = full["f_pts"].to_numpy(float)
    players = sorted(set("|".join(full["quinteto"]).split("|")) | set("|".join(full["quinteto_rival"]).split("|")))
    ix = {p: i for i, p in enumerate(players)}
    n = len(players)
    mu = pts.sum() / poss.sum()
    y = 100 * (pts / poss - mu)
    w = poss
    A = np.zeros((2 * n, 2 * n))
    bvec = np.zeros(2 * n)
    off_idx = full["quinteto"].map(lambda q: [ix[p] for p in q.split("|")]).to_list()
    def_idx = full["quinteto_rival"].map(lambda q: [n + ix[p] for p in q.split("|")]).to_list()
    for oi, di, wi, yi in zip(off_idx, def_idx, w, y):
        cols = oi + di
        A[np.ix_(cols, cols)] += wi
        bvec[cols] += wi * yi
    A[np.diag_indices_from(A)] += lam
    beta = np.linalg.solve(A, bvec)
    exposure = np.zeros(n)
    for oi, wi in zip(off_idx, w):
        exposure[oi] += wi
    out = pd.DataFrame({"player_id": players, "orapm": beta[:n], "drapm": -beta[n:]})
    out["rapm"] = out["orapm"] + out["drapm"]
    out["rapm_poss"] = exposure
    return out


def assist_tables(assists: pd.DataFrame, player_fgm: pd.Series, pair_min: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(conexiones pasador→receptor, métricas de red por jugador)."""
    if assists.empty:
        return pd.DataFrame(), pd.DataFrame()
    a = assists.copy()
    a["ast_2"] = (a["tipo"] == "T2").astype(int)
    a["ast_3"] = (a["tipo"] == "T3").astype(int)
    a["ast_tl"] = (a["tipo"] == "TL").astype(int)
    con = a.groupby(["team_id", "pasador_id", "receptor_id"]).agg(
        ast=("tipo", "size"), ast_2=("ast_2", "sum"), ast_3=("ast_3", "sum"), ast_tl=("ast_tl", "sum"),
        pts_asistidos=("puntos", "sum"), gp=("game_id", "nunique")).reset_index()
    tot_pas = con.groupby(["team_id", "pasador_id"])["ast"].transform("sum")
    tot_rec = con.groupby(["team_id", "receptor_id"])["ast"].transform("sum")
    con["pct_ast_pasador"] = 100 * con["ast"] / tot_pas
    con["pct_asistidas_receptor"] = 100 * con["ast"] / tot_rec
    if not pair_min.empty:
        key = con.apply(lambda r: (r["team_id"], "|".join(sorted([r["pasador_id"], r["receptor_id"]]))), axis=1)
        pm = pair_min.set_index(["team_id", "unidad"])["min"]
        con["min_juntos"] = [pm.get(k_, np.nan) for k_ in key]
        con["ast_por40_juntos"] = 40 * _div(con["ast"], con["min_juntos"])
    # métricas de red por jugador
    rows = []
    for tid, g in con.groupby("team_id"):
        nodes = sorted(set(g["pasador_id"]) | set(g["receptor_id"]))
        ix = {p: i for i, p in enumerate(nodes)}
        W = np.zeros((len(nodes), len(nodes)))
        for _, r in g.iterrows():
            W[ix[r["pasador_id"]], ix[r["receptor_id"]]] += r["ast"]
        pr = _pagerank(W)
        for p in nodes:
            out_r = g[g["pasador_id"] == p]
            in_r = g[g["receptor_id"] == p]
            dad, rec = out_r["ast"].sum(), in_r["ast"].sum()
            shares = (out_r["ast"] / dad).to_numpy() if dad else np.array([])
            rows.append({"team_id": tid, "player_id": p, "ast_dadas": int(dad), "ast_recibidas": int(rec),
                         "pts_generados_asist": int(out_r["pts_asistidos"].sum()),
                         "socios_asistencia": int(out_r["receptor_id"].nunique()),
                         "socios_asistido_por": int(in_r["pasador_id"].nunique()),
                         "hhi_asistencias": float((shares ** 2).sum() * 10000) if dad else np.nan,
                         "receptor_principal": out_r.sort_values("ast").iloc[-1]["receptor_id"] if dad else None,
                         "asistente_principal": in_r.sort_values("ast").iloc[-1]["pasador_id"] if rec else None,
                         "pagerank_asistencias": float(pr[ix[p]])})
    net = pd.DataFrame(rows)
    if not net.empty:
        fgm = net["player_id"].map(player_fgm)
        net["pct_canastas_asistidas"] = 100 * _div(net["ast_recibidas"], fgm)
    return con, net


def _pagerank(W: np.ndarray, d: float = 0.85, it: int = 100) -> np.ndarray:
    """PageRank del grafo de asistencias: un jugador es central si recibe asistencias de jugadores centrales."""
    n = len(W)
    if n == 0:
        return np.array([])
    out = W.sum(axis=1, keepdims=True)
    P = np.divide(W, out, out=np.full_like(W, 1.0 / n), where=out > 0)
    r = np.full(n, 1.0 / n)
    for _ in range(it):
        r = (1 - d) / n + d * r @ P
    return r / r.sum()


def expected_net(rows: pd.DataFrame, rmap: pd.Series, coef: float) -> pd.DataFrame:
    """Net esperado de cada quinteto según el RAPM: Σ RAPM propios − Σ RAPM de los rivales que tuvo enfrente,
    ponderado por las posesiones de cada tramo."""
    full = rows[(rows["quinteto"].str.count(r"\|") == 4) & (rows["quinteto_rival"].str.count(r"\|") == 4)]
    if full.empty or rmap.empty:
        return pd.DataFrame(columns=["team_id", "unidad", "net_esperado"])
    val = lambda q: sum(rmap.get(p, 0.0) for p in q.split("|"))  # noqa: E731
    cache: dict = {}
    def v(q):
        if q not in cache:
            cache[q] = val(q)
        return cache[q]
    poss = ((full["f_fga"] - full["f_oreb"] + full["f_tov"] + coef * full["f_fta"])
            + (full["o_fga"] - full["o_oreb"] + full["o_tov"] + coef * full["o_fta"])) / 2
    d = pd.DataFrame({"team_id": full["team_id"], "unidad": full["quinteto"], "w": poss.clip(lower=0),
                      "e": full["quinteto"].map(v) - full["quinteto_rival"].map(v)})
    d["we"] = d["w"] * d["e"]
    g = d.groupby(["team_id", "unidad"])[["we", "w"]].sum()
    return pd.DataFrame({"net_esperado": g["we"] / g["w"].where(g["w"] > 0)}).reset_index()
