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
  net esperado  = Σ RAPM de los 5 propios − Σ RAPM de los 5 rivales en cada tramo, ponderado por posesiones
  sinergia (quinteto) / sinergia_rapm (tríos y parejas) = poss/(poss+k) · (Net − Net esperado)
  suerte        = DRtg/Net con el % de triples y de tiros libres del rival sustituido por la media de la liga
  basura        = minutos de la basura (criterio Cleaning the Glass escalado); clutch = últimos 5 min, ±5
  red de asistencias: pasador → anotador; centralidad PageRank ponderada por asistencias dentro del equipo,
                  concentración HHI de a quién asiste cada jugador.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from .schema import ONOFF_BASE, ONOFF_DIFF
from .stints import STAT_KEYS

PHASES = ["regular", "playoffs", "total"]


def team_rows(segments: pd.DataFrame) -> pd.DataFrame:
    """Dos filas por tramo (una por equipo) con estadísticas propias f_* y del rival o_*."""
    if segments.empty:
        return pd.DataFrame()
    segments = segments.copy()
    if "basura" not in segments:
        segments["basura"] = False
    base = ["game_id", "fase", "periodo", "t0", "t1", "sec", "clutch", "basura"]
    rows = []
    for side, other in (("a", "b"), ("b", "a")):
        d = segments[base].copy()
        d["team_id"] = segments[f"team_{side}"]
        d["opp_id"] = segments[f"team_{other}"]
        d["quinteto"] = segments[f"quinteto_{side}"]
        d["quinteto_rival"] = segments[f"quinteto_{other}"]
        sign = 1 if side == "a" else -1
        d["margen_inicio"] = sign * segments["margen_inicio"]
        d["sec_clutch"] = segments["sec"].where(segments["clutch"].astype(bool), 0.0)
        d["sec_basura"] = segments["sec"].where(segments["basura"].astype(bool), 0.0)
        for k in STAT_KEYS:
            d[f"f_{k}"] = segments[f"{side}_{k}"]
            d[f"o_{k}"] = segments[f"{other}_{k}"]
        rows.append(d)
    return pd.concat(rows, ignore_index=True)


SUM_COLS = ["sec", "sec_clutch", "sec_basura"] + [f"f_{k}" for k in STAT_KEYS] + [f"o_{k}" for k in STAT_KEYS]


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
    # "suerte": el % de triples y de tiros libres del rival apenas depende de la defensa; se sustituye por
    # la media de la liga (puntos del rival esperados con sus mismos intentos)
    o_pts_l = (o("pts") - 3 * o("fg3m") + 3 * o("fg3a") * lg.get("fg3_pct", np.nan)
               - o("ftm") + o("fta") * lg.get("ft_pct", np.nan))
    out["drtg_suerte"] = 100 * _div(o_pts_l, poss_def)
    out["net_rtg_suerte"] = out["ortg"] - out["drtg_suerte"]
    out["net_rtg_suerte_aj"] = out["ortg_aj"] - 100 * _div(o_pts_l + k * ppp, poss_def + k)
    out["min_clutch"] = s["sec_clutch"].astype(float) / 60
    out["min_basura"] = s["sec_basura"].astype(float) / 60
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
    return {"ppp": float(s["f_pts"] / poss) if poss else np.nan,
            "fg3_pct": float(s["f_fg3m"] / s["f_fg3a"]) if s["f_fg3a"] else 0.0,
            "ft_pct": float(s["f_ftm"] / s["f_fta"]) if s["f_fta"] else 0.0}


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
    for c in ONOFF_BASE:
        out[f"{c}_on"] = m_on[c].values
        out[f"{c}_off"] = m_off[c].values
    for c in ONOFF_DIFF:
        out[f"{c}_onoff"] = out[f"{c}_on"] - out[f"{c}_off"]
    out["min_pct_equipo"] = 100 * _div(on["sec"], on["team_id"].map(team["sec"]))
    out["quintetos_distintos"] = d.groupby(["team_id", "player_id"])["quinteto"].nunique().reindex(
        pd.MultiIndex.from_frame(out[["team_id", "player_id"]])).values
    out["basura_min"] = on["sec_basura"].values / 60
    # sin minutos de la basura
    nb = d[~d["basura"].astype(bool)]
    if not nb.empty:
        on_nb = _sum_by(nb, ["team_id", "player_id"])
        team_nb = full[~full["basura"].astype(bool)].groupby("team_id")[SUM_COLS].sum()
        off_nb = on_nb[["team_id", "player_id"]].copy()
        for c in SUM_COLS:
            off_nb[c] = on_nb["team_id"].map(team_nb[c]).values - on_nb[c].values
        a_on, a_off = rate_metrics(on_nb, lg, game_min, coef, k), rate_metrics(off_nb, lg, game_min, coef, k)
        x = on_nb[["team_id", "player_id"]].assign(
            net_rtg_on_sin_basura=a_on["net_rtg"].values,
            net_rtg_onoff_sin_basura=(a_on["net_rtg"] - a_off["net_rtg"]).values,
            net_rtg_aj_onoff_sin_basura=(a_on["net_rtg_aj"] - a_off["net_rtg_aj"]).values)
        out = out.merge(x, on=["team_id", "player_id"], how="left")
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


def expected_net(rows: pd.DataFrame, rmap: pd.Series, coef: float, size: int = 5) -> pd.DataFrame:
    """Net esperado de cada unidad (quinteto, trío o pareja) según el RAPM: en cada tramo, Σ RAPM de los 5
    propios − Σ RAPM de los 5 rivales, ponderado por las posesiones de los tramos en que la unidad estuvo en
    pista. La diferencia entre el net real y éste mide lo que la unidad rinde por encima de sus piezas."""
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
    d = pd.DataFrame({"team_id": full["team_id"], "quinteto": full["quinteto"], "w": poss.clip(lower=0),
                      "e": full["quinteto"].map(v) - full["quinteto_rival"].map(v)})
    d = explode_units(d, size)
    d["we"] = d["w"] * d["e"]
    g = d.groupby(["team_id", "unidad"])[["we", "w"]].sum()
    return pd.DataFrame({"net_esperado": g["we"] / g["w"].where(g["w"] > 0)}).reset_index()


def rotation_table(rows: pd.DataFrame) -> pd.DataFrame:
    """Uso de cada jugador en la rotación: titularidades, partidos cerrados, relevos (entradas a pista) y
    reparto de sus minutos por periodo."""
    full = rows[rows["quinteto"].str.count(r"\|") == 4]
    if full.empty:
        return pd.DataFrame()
    d = explode_units(full[["game_id", "team_id", "periodo", "t0", "t1", "sec", "quinteto"]], 1)
    d = d.rename(columns={"unidad": "player_id"}).sort_values(["team_id", "player_id", "game_id", "t0"])
    keys = ["team_id", "player_id"]
    first = full.loc[full.groupby(["game_id", "team_id"])["t0"].idxmin(), ["game_id", "team_id", "quinteto"]]
    last = full.loc[full.groupby(["game_id", "team_id"])["t1"].idxmax(), ["game_id", "team_id", "quinteto"]]
    cnt = lambda f: (explode_units(f, 1).rename(columns={"unidad": "player_id"})  # noqa: E731
                     .groupby(keys).size())
    prev_t1 = d.groupby(keys + ["game_id"])["t1"].shift()
    d["nuevo_relevo"] = prev_t1.isna() | ((d["t0"] - prev_t1).abs() > 0.05)
    g = d.groupby(keys)
    out = pd.DataFrame({"min": g["sec"].sum() / 60, "gp": g["game_id"].nunique(),
                        "relevos": g["nuevo_relevo"].sum()})
    out["titular_partidos"] = cnt(first).reindex(out.index).fillna(0).astype(int)
    out["cierra_partidos"] = cnt(last).reindex(out.index).fillna(0).astype(int)
    out["min_por_partido"] = _div(out["min"], out["gp"])
    out["relevos_por_partido"] = _div(out["relevos"], out["gp"])
    out["min_por_relevo"] = _div(out["min"], out["relevos"])
    per = d.assign(p=d["periodo"].clip(upper=5)).pivot_table(index=keys, columns="p", values="sec", aggfunc="sum",
                                                             fill_value=0)
    for p_, name in ((1, "q1"), (2, "q2"), (3, "q3"), (4, "q4"), (5, "prorroga")):
        col = per[p_] if p_ in per.columns else 0
        out[f"pct_min_{name}"] = 100 * _div(pd.Series(col, index=per.index).reindex(out.index).fillna(0) / 60,
                                            out["min"])
    return out.drop(columns=["min", "gp"]).reset_index()


def team_table(rows: pd.DataFrame, q5: pd.DataFrame, players: pd.DataFrame, lg: dict, game_min: float,
               coef: float, k: float, names: dict) -> pd.DataFrame:
    """Resumen por equipo de su estructura de quintetos y rotación."""
    full = rows[rows["quinteto"].str.count(r"\|") == 4]
    if full.empty:
        return pd.DataFrame()
    s = _sum_by(full, ["team_id"])
    m = rate_metrics(s, lg, game_min, coef, k)
    keep = ["min", "poss", "ortg", "drtg", "net_rtg", "net_rtg_aj", "drtg_suerte", "net_rtg_suerte", "ritmo",
            "efg_pct", "opp_efg_pct", "tov_pct", "opp_tov_pct", "oreb_pct", "dreb_pct", "ft_rate", "opp_ft_rate",
            "min_clutch", "min_basura"]
    out = pd.concat([s[["team_id", "gp"]], m[keep]], axis=1).set_index("team_id")
    cl = full[full["clutch"].astype(bool)]
    if not cl.empty:
        cs = _sum_by(cl, ["team_id"])
        out["clutch_net_rtg"] = pd.Series(rate_metrics(cs, lg, game_min, coef, k)["net_rtg"].values,
                                          index=cs["team_id"])
    nm = lambda u: " / ".join(names.get(p) or p for p in u.split("|"))  # noqa: E731
    if not q5.empty:
        for tid, g in q5.groupby("team_id"):
            g = g.sort_values("min", ascending=False)
            top = g.iloc[0]
            out.loc[tid, "quintetos_distintos"] = len(g)
            out.loc[tid, "quintetos_100_poss"] = int((g["poss"] >= 100).sum())
            out.loc[tid, "quinteto_principal"] = nm(top["unidad"])
            out.loc[tid, "min_pct_quinteto_principal"] = top["min_pct_equipo"]
            out.loc[tid, "net_rtg_quinteto_principal"] = top["net_rtg"]
            out.loc[tid, "min_pct_top5_quintetos"] = g["min_pct_equipo"].head(5).sum()
    first = full.loc[full.groupby(["game_id", "team_id"])["t0"].idxmin(), ["team_id", "quinteto"]]
    for tid, g in first.groupby("team_id"):
        vc = g["quinteto"].value_counts()
        u = vc.index[0]
        out.loc[tid, "quinteto_titular_habitual"] = nm(u)
        out.loc[tid, "partidos_quinteto_titular"] = int(vc.iloc[0])
        out.loc[tid, "quintetos_titulares_distintos"] = len(vc)
        if not q5.empty:
            r = q5[(q5["team_id"] == tid) & (q5["unidad"] == u)]
            out.loc[tid, "net_rtg_quinteto_titular"] = r["net_rtg"].iloc[0] if len(r) else np.nan
    if not players.empty and "min_pct_equipo" in players:
        for tid, g in players.groupby("team_id"):
            sh = g["min_pct_equipo"].fillna(0) / 500   # cuota de los minutos-jugador del equipo (suma = 1)
            out.loc[tid, "jugadores_usados"] = int((g["min_pct_equipo"] > 0).sum())
            out.loc[tid, "jugadores_rotacion"] = int((g["min_pct_equipo"] >= 25).sum())
            out.loc[tid, "hhi_minutos"] = float((sh ** 2).sum() * 10000)
            if "pagerank_asistencias" in g:
                pr = g["pagerank_asistencias"].dropna()
                out.loc[tid, "hhi_pagerank_asistencias"] = float(((pr / pr.sum()) ** 2).sum() * 10000) if len(pr) else np.nan
    return out.reset_index()
