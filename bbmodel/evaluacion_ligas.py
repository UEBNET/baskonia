"""Evaluación estadística de ligas para la pestaña «Evaluación de ligas» de la Mesa Multiliga.

Lee los CSV procesados (data/processed/<temporada>/ligas/*.csv) y escribe, junto a los JSON del
Artifact, <salida>/<temporada>/evaluacion_<fase>.json con:
  * por métrica y liga: n, cobertura, media ponderada por minutos, sd, mediana, 21 cuantiles
  * por métrica: Kruskal-Wallis (H, p, eps2), eta2 ponderado, CV entre ligas, partición de varianza
    liga / equipo / jugador, y estadísticos por pares (Hedges g, Cliff delta, KS, W1/sigma, JSD)
  * análisis transversales: Shapley del ORtg de liga, efecto de la escala (pg / p40 / p100),
    posición, dispersión de equipos, discriminabilidad (proxy A-distance, LDA), jugadores puente.
Uso: python -m bbmodel evaluacion-ligas [--salida data/artifact]
Después se publican esos JSON con el resto de datos del Artifact (ruta datos/<temporada>/).
"""
import itertools
import json
import math
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.spatial.distance import jensenshannon
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

RAIZ = Path(__file__).resolve().parent.parent
DATA = RAIZ / "data" / "processed"
RNG = np.random.default_rng(20261012)

LIGAS = ["euroleague", "eurocup", "acb", "lba", "bbl", "lnb", "nba", "gleague"]
PARES = list(itertools.combinations(range(len(LIGAS)), 2))
# minutos mínimos para entrar en la población de jugadores, por fase (la temporada en curso usa 30)
UMBRAL = {"regular": 200, "playoffs": 60, "total": 200}
UMBRAL_EN_CURSO = 30
QS = np.linspace(0, 1, 21)
MIN_N = 10        # jugadores mínimos por liga para cuantiles y pares
MIN_N_TEAM = 8    # equipos mínimos por liga

from bbstats.pipeline import pista_artifact, pista_diccionario  # noqa: E402
from bbstats.schema import dictionary_records  # noqa: E402

DIC = dictionary_records() + pista_diccionario()   # + columnas de pista (q_*: on/off, RAPM, rotación, zonas)
GRUPO = {d["columna"]: d["grupo"] for d in DIC}
DESC = {d["columna"]: d["descripcion"] for d in DIC}
ORDEN = [d["columna"] for d in DIC]
ID_NUM = {"altura_cm", "peso_kg", "edad"}
EQUIPO_LIGA = {"team_poss", "opp_poss", "team_pace", "team_ortg", "team_drtg", "team_netrtg"}


def r4(x):
    """Redondeo a 4 cifras significativas (None si no es finito)."""
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    if x == 0:
        return 0.0
    return float(f"{x:.4g}")


def load(season, phase):
    files = sorted((DATA / season / "ligas").glob("*.csv"))
    if not files:
        return None
    df = pd.concat([pd.read_csv(f, low_memory=False, dtype={"player_id": str, "team_id": str}) for f in files],
                   ignore_index=True)
    df = df[df["fase"] == phase].reset_index(drop=True)
    if len(df):
        df = pista_artifact(df, DATA, season)
    return df if len(df) else None


def wmean(x, w):
    return float(np.sum(w * x) / np.sum(w)) if np.sum(w) > 0 else np.nan


def wsd(x, w):
    m = wmean(x, w)
    return float(math.sqrt(np.sum(w * (x - m) ** 2) / np.sum(w))) if np.sum(w) > 0 else np.nan


def kind_of(c):
    g = GRUPO.get(c, "")
    if c.startswith("lg_"):
        return "liga"
    if g in ("contexto_equipo", "contexto_rival") or c in EQUIPO_LIGA:
        return "equipo"
    return "jugador"


# --------------------------------------------------------------------- posición (réplica de la página)
POS_MAP = {"Base": 1, "Escolta": 2, "Alero": 3, "Ala-pívot": 4, "Pívot": 5, "POINT_GUARD": 1, "SHOOTING_GUARD": 2,
           "SMALL_FORWARD": 3, "POWER_FORWARD": 4, "CENTER": 5, "PG": 1, "SG": 2, "SF": 3, "PF": 4, "C": 5, "C-F": 5}
POS_CANDS = {"G": [1, 2], "G-F": [1, 2], "F": [3, 4], "F-G": [3, 4], "F-C": [3, 4]}
POS_FEATS = ["ast_pct", "oreb_pct", "dreb_pct", "blk_pct", "fg3a_rate", "stl_pct", "fta_rate", "tov_pct"]


def official_pos(raw):
    if raw is None or (isinstance(raw, float) and math.isnan(raw)) or raw == "":
        return None, None
    t = str(raw).strip()
    if t in POS_MAP:
        return POS_MAP[t], None
    m = re.match(r"^(\d)", t)
    if m and 1 <= int(m.group(1)) <= 5:
        return int(m.group(1)), None
    if t in POS_CANDS:
        return None, POS_CANDS[t]
    return None, None


def estimate_positions(df):
    """Misma lógica que derive() en la página: posición oficial, o centroide más cercano en z por liga."""
    mins = df.groupby("liga")["min"].apply(lambda s: min(100, np.sort(s.fillna(0).values)[int(len(s) * 0.4)]))
    ok = df["min"].fillna(0) >= df["liga"].map(mins)
    z = pd.DataFrame(index=df.index)
    for f in POS_FEATS:
        v = pd.to_numeric(df[f], errors="coerce")
        g = v[ok].groupby(df.loc[ok, "liga"])
        m, s, n = g.mean(), g.std(ddof=0), g.count()
        mm, ss, nn = df["liga"].map(m), df["liga"].map(s), df["liga"].map(n)
        z[f] = np.where((nn >= 5) & v.notna(), (v - mm) / ss.clip(lower=1e-9), np.nan)
    off = [official_pos(x) for x in df["posicion"]]
    cent = {}
    for p in range(1, 6):
        mask = np.array([o[0] == p for o in off]) & ok.values
        cent[p] = z[mask].mean()
    pos, est = [], []
    for k, (o, c) in enumerate(off):
        if o:
            pos.append(o); est.append(0); continue
        zr = z.iloc[k]
        fs = zr.dropna().index
        if len(fs) < 3:
            pos.append(None); est.append(None); continue
        cands = c or [1, 2, 3, 4, 5]
        best = min(cands, key=lambda q: float(((zr[fs] - cent[q][fs].fillna(0)) ** 2).sum()))
        pos.append(best); est.append(2 if c else 1)
    df["pos_rep"] = pos
    df["pos_est"] = est
    return df


# --------------------------------------------------------------------- estadísticos por métrica
def js_div(a, b, bins=20):
    pooled = np.concatenate([a, b])
    lo, hi = np.quantile(pooled, [0.01, 0.99])
    if hi <= lo:
        return 0.0
    edges = np.linspace(lo, hi, bins + 1)
    pa = np.histogram(np.clip(a, lo, hi), edges)[0] + 1e-9
    pb = np.histogram(np.clip(b, lo, hi), edges)[0] + 1e-9
    return float(jensenshannon(pa / pa.sum(), pb / pb.sum(), base=2) ** 2)


def metric_block(df_el, df_teams, df_all, c):
    """df_el: jugadores elegibles; df_teams: una fila por (liga, equipo); df_all: todas las filas."""
    k = kind_of(c)
    per = []
    vals = {}
    for li, l in enumerate(LIGAS):
        if k == "jugador":
            sub = df_el[df_el.liga == l]
            v = pd.to_numeric(sub[c], errors="coerce")
            msk = v.notna()
            x, w = v[msk].values.astype(float), sub.loc[msk, "min"].values.astype(float)
            n_el = len(sub)
            min_n = MIN_N
        elif k == "equipo":
            sub = df_teams[df_teams.liga == l]
            v = pd.to_numeric(sub[c], errors="coerce")
            msk = v.notna()
            x, w = v[msk].values.astype(float), np.ones(int(msk.sum()))
            n_el = len(sub)
            min_n = MIN_N_TEAM
        else:
            sub = df_all[df_all.liga == l]
            v = pd.to_numeric(sub[c], errors="coerce").dropna()
            x = v.values[:1].astype(float); w = np.ones(len(x)); n_el = 1 if len(sub) else 0; min_n = 1
        if len(x) == 0 or n_el == 0:
            per.append(None); continue
        ent = {"n": int(len(x)), "cov": r4(len(x) / n_el), "m": r4(wmean(x, w)), "sd": r4(wsd(x, w) if len(x) > 1 else None),
               "med": r4(np.median(x))}
        if len(x) >= min_n and k != "liga":
            ent["q"] = [r4(q) for q in np.quantile(x, QS)]
            vals[li] = (x, w)
        per.append(ent)
    out = {"c": c, "k": k, "l": per}
    if len(vals) >= 2:
        groups = [vals[i][0] for i in vals]
        allx = np.concatenate(groups); allw = np.concatenate([vals[i][1] for i in vals])
        N = len(allx)
        try:
            H, p = stats.kruskal(*groups)
            out["kw"] = [r4(H), r4(p) if p > 0 else 0.0, r4(H / (N - 1))]
        except ValueError:
            out["kw"] = None
        gm = wmean(allx, allw)
        sst = float(np.sum(allw * (allx - gm) ** 2))
        ssb = sum(float(np.sum(vals[i][1])) * (wmean(vals[i][0], vals[i][1]) - gm) ** 2 for i in vals) if sst > 0 else 0
        out["eta2"] = r4(ssb / sst) if sst > 0 else None
        means = np.array([wmean(vals[i][0], vals[i][1]) for i in vals])
        out["cv"] = r4(np.std(means) / abs(np.mean(means))) if abs(np.mean(means)) > 1e-12 else None
        # partición jerárquica liga / equipo / jugador (sólo métricas de jugador)
        if k == "jugador" and sst > 0:
            d = df_el[["liga", "team_id", "min"]].copy()
            d[c + "__v"] = pd.to_numeric(df_el[c], errors="coerce")
            c = c + "__v"
            d = d[d[c].notna() & d.liga.isin([LIGAS[i] for i in vals])]
            d["wx"] = d["min"] * d[c]
            lg = d.groupby("liga").agg(W=("min", "sum"), WX=("wx", "sum")); lg["m"] = lg.WX / lg.W
            tm = d.groupby(["liga", "team_id"]).agg(W=("min", "sum"), WX=("wx", "sum")).reset_index(); tm["m"] = tm.WX / tm.W
            tm["ml"] = tm.liga.map(lg.m)
            ss_l = float((lg.W * (lg.m - gm) ** 2).sum()); ss_t = float((tm.W * (tm.m - tm.ml) ** 2).sum())
            out["vd"] = [r4(ss_l / sst), r4(ss_t / sst), r4(max(0.0, 1 - (ss_l + ss_t) / sst))]
        # pares
        pw = {"g": [], "d": [], "ks": [], "w1": [], "js": []}
        for i, j in PARES:
            if i in vals and j in vals:
                a, b = vals[i][0], vals[j][0]
                na, nb = len(a), len(b)
                sp = math.sqrt(((na - 1) * np.var(a, ddof=1) + (nb - 1) * np.var(b, ddof=1)) / (na + nb - 2))
                J = 1 - 3 / (4 * (na + nb) - 9)
                g = (np.mean(a) - np.mean(b)) / sp * J if sp > 0 else 0.0
                U = stats.mannwhitneyu(a, b, alternative="two-sided").statistic
                dl = 2 * U / (na * nb) - 1
                ks = stats.ks_2samp(a, b).statistic
                w1 = stats.wasserstein_distance(a, b) / sp if sp > 0 else 0.0
                pw["g"].append(r4(g)); pw["d"].append(r4(dl)); pw["ks"].append(r4(ks)); pw["w1"].append(r4(w1)); pw["js"].append(r4(js_div(a, b)))
            else:
                for kk in pw:
                    pw[kk].append(None)
        out["pw"] = pw
    return out


# --------------------------------------------------------------------- análisis transversales
def team_table(df):
    t = df.drop_duplicates(["liga", "team_id"])
    return t[~t.team_id.astype(str).str.contains(";")].copy()


def gl_poss_factor(df):
    """Cociente posesiones oficiales G League / posesiones del pipeline (con jugadores, ponderado)."""
    g = df[(df.liga == "gleague") & df.src_poss.notna() & df.poss_on_court.notna()]
    if len(g) < 20:
        return None
    return float(g.src_poss.sum() / g.poss_on_court.sum())


def shapley_block(teams, gl_factor):
    rows = {}
    for l in LIGAS:
        t = teams[teams.liga == l]
        if len(t) == 0 or t.team_poss.isna().all():
            continue
        s = t[["team_gp", "team_pts", "team_fga", "team_fgm", "team_fg3m", "team_fg2m", "team_fta", "team_ftm", "team_oreb", "team_tov",
               "team_poss", "team_ast", "team_fg3a"]].sum()
        poss = s.team_poss * (gl_factor if (l == "gleague" and gl_factor) else 1.0)
        e = (s.team_fgm + 0.5 * s.team_fg3m) / s.team_fga
        ftpts = s.team_pts - 2 * s.team_fg2m - 3 * s.team_fg3m
        pft = ftpts / s.team_fta
        a = s.team_fta / poss; tv = s.team_tov / poss; o = s.team_oreb / poss
        sh = s.team_fga / poss
        r = sh - (1 - 0.44 * a + o - tv)
        ppp = s.team_pts / poss
        mins = t.team_min.sum() / 5 if t.team_min.notna().all() else np.nan
        mp = float(df_minpart.get(l, 40))
        pace = mp * poss / mins if mins and mins > 0 else np.nan
        rows[l] = {"e": e, "pft": pft, "a": a, "t": tv, "o": o, "r": r, "ppp": ppp, "pace": pace, "fg3a_rate": s.team_fg3a / s.team_fga,
                   "ast_fgm": s.team_ast / s.team_fgm, "pts_pg": s.team_pts / s.team_gp, "teams": int(len(t))}
    fac = ["e", "pft", "a", "t", "o", "r"]

    def v(f):
        return 2 * f["e"] * (1 - 0.44 * f["a"] + f["o"] - f["t"] + f["r"]) + f["pft"] * f["a"]

    for l in rows:  # comprobación de la identidad
        assert abs(v(rows[l]) - rows[l]["ppp"]) < 1e-9, (l, v(rows[l]), rows[l]["ppp"])
    n = len(fac)
    shap = {}
    for ref in rows:
        shap[ref] = {}
        for l in rows:
            phi = {}
            for k in fac:
                others = [f for f in fac if f != k]
                tot = 0.0
                for size in range(n):
                    for S in itertools.combinations(others, size):
                        wgt = math.factorial(size) * math.factorial(n - size - 1) / math.factorial(n)
                        base = {f: (rows[l][f] if f in S else rows[ref][f]) for f in fac}
                        with_k = dict(base); with_k[k] = rows[l][k]
                        tot += wgt * (v(with_k) - v(base))
                phi[k] = r4(100 * tot)
            shap[ref][l] = phi
    lg = {l: {k: r4(vv * (100 if k in ("e", "a", "t", "o", "r", "ppp", "fg3a_rate", "ast_fgm") else 1)) if k != "teams" else vv
              for k, vv in rows[l].items()} for l in rows}
    return {"liga": lg, "shapley": shap, "factores": fac, "gl_factor": r4(gl_factor)}


BASES = ["pts", "reb", "ast", "stl", "blk", "tov", "fga", "fta", "fg3a", "oreb", "dreb", "pf"]


def eta2_w(d, c):
    v = pd.to_numeric(d[c], errors="coerce")
    m = v.notna()
    x, w, l = v[m].values, d.loc[m, "min"].values, d.loc[m, "liga"].values
    if len(np.unique(l)) < 2:
        return None, None
    gm = wmean(x, w)
    sst = np.sum(w * (x - gm) ** 2)
    means = {}
    ssb = 0
    for li in np.unique(l):
        mm = l == li
        if mm.sum() < MIN_N:
            continue
        means[li] = wmean(x[mm], w[mm])
        ssb += w[mm].sum() * (means[li] - gm) ** 2
    vals = np.array(list(means.values()))
    return (ssb / sst if sst > 0 else None), (vals.max() / vals.min() if vals.min() > 0 else None)


def scale_block(el):
    out = []
    for b in BASES:
        row = {"b": b}
        for suf in ("pg", "p40", "p100"):
            c = f"{b}_{suf}"
            if c in el:
                e2, rr = eta2_w(el, c)
                row[suf] = [r4(e2), r4(rr)]
        out.append(row)
    return out


KEYM = ["pts_p100", "ast_p100", "reb_p100", "ts_pct", "efg_pct", "fg3_pct", "fg3a_rate", "fta_rate", "usg_pct", "ast_pct", "tov_pct",
        "oreb_pct", "dreb_pct", "stl_pct", "blk_pct", "per", "ortg", "drtg", "ws_per_40", "pie", "game_score_p40", "altura_cm", "edad", "min_pct"]


def wls_r2(y, w, X):
    sw = np.sqrt(w)
    beta, *_ = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)
    res = y - X @ beta
    ym = wmean(y, w)
    return 1 - np.sum(w * res ** 2) / np.sum(w * (y - ym) ** 2)


def position_block(el):
    out = {}
    for c in KEYM:
        if c not in el:
            continue
        d = el[["liga", "pos_rep", "pos_est", "min", c]].copy()
        d[c] = pd.to_numeric(d[c], errors="coerce")
        d = d[d[c].notna() & d.pos_rep.notna()]
        if d.liga.nunique() < 2 or len(d) < 50:
            continue
        tab = {}
        for l in LIGAS:
            row = []
            for p in range(1, 6):
                s = d[(d.liga == l) & (d.pos_rep == p)]
                row.append([r4(wmean(s[c].values, s["min"].values)), int(len(s))] if len(s) >= 5 else None)
            tab[l] = row
        y, w = d[c].values.astype(float), d["min"].values.astype(float)
        L = pd.get_dummies(d.liga).values.astype(float)
        P = pd.get_dummies(d.pos_rep.astype(int)).values.astype(float)
        LP = pd.get_dummies(d.liga + "_" + d.pos_rep.astype(int).astype(str)).values.astype(float)
        r2 = [wls_r2(y, w, L), wls_r2(y, w, P), wls_r2(y, w, np.hstack([L, P[:, 1:]])), wls_r2(y, w, LP)]
        out[c] = {"tab": tab, "r2": [r4(x) for x in r2]}
    return out


def team_spread(teams):
    out = {}
    for l in LIGAS:
        t = teams[teams.liga == l]
        if len(t) < 3:
            continue
        ent = {"n": int(len(t))}
        for c in ("team_pace", "team_ortg", "team_drtg", "team_netrtg"):
            v = pd.to_numeric(t[c], errors="coerce").dropna()
            if len(v) >= 3:
                ent[c] = [r4(v.mean()), r4(v.std(ddof=1)), r4(v.min()), r4(v.max())]
        out[l] = ent
    return out


EXCL_FEAT = {"poss_on_court", "poss_used", "totposs", "scposs", "pprod", "stops", "ows", "dws", "ws", "eff", "game_score", "pir_calc",
             "tsa", "uper"}


def pick_features(el, groups, avoid_suffix=()):
    feats = []
    for c in ORDEN:
        if GRUPO.get(c) not in groups or c in EXCL_FEAT or c.startswith(("src_", "bn_")) or c.endswith(avoid_suffix):
            continue
        if c not in el:
            continue
        v = pd.to_numeric(el[c], errors="coerce")
        cov = v.notna().groupby(el.liga).mean()
        if len(cov) == len(LIGAS) and cov.min() >= 0.85 and v.std() > 0:
            feats.append(c)
    return feats


def discrim_block(el):
    res = {}
    sets = {"posesion": pick_features(el, {"tiro", "ratios", "por_100_pos", "ratings"}),
            "conteos_pg": [f"{b}_pg" for b in BASES], "conteos_p40": [f"{b}_p40" for b in BASES],
            "conteos_p100": [f"{b}_p100" for b in BASES]}
    for name, feats in sets.items():
        d = el[["liga"] + feats].copy()
        for f in feats:
            d[f] = pd.to_numeric(d[f], errors="coerce")
        d = d.dropna()
        if d.liga.nunique() < len(LIGAS):
            continue
        X, y = d[feats].values, d.liga.values
        mdl = make_pipeline(StandardScaler(), LogisticRegression(max_iter=4000, C=1.0, class_weight="balanced"))
        cv = StratifiedKFold(5, shuffle=True, random_state=7)
        pred = cross_val_predict(mdl, X, y, cv=cv)
        cm = pd.crosstab(pd.Series(y, name="r"), pd.Series(pred, name="p")).reindex(index=LIGAS, columns=LIGAS, fill_value=0)
        cmn = (cm.T / cm.sum(axis=1)).T
        bal = float(np.mean(np.diag(cmn.values)))
        pad = []
        for i, j in PARES:
            m = np.isin(y, [LIGAS[i], LIGAS[j]])
            yy = (y[m] == LIGAS[i]).astype(int)
            pp = cross_val_predict(mdl, X[m], yy, cv=StratifiedKFold(5, shuffle=True, random_state=7))
            tpr = np.mean(pp[yy == 1] == 1); tnr = np.mean(pp[yy == 0] == 0)
            err = 1 - (tpr + tnr) / 2
            pad.append(r4(max(0.0, 2 * (1 - 2 * err))))
        ent = {"feats": feats, "n": int(len(d)), "bal_acc": r4(bal), "azar": r4(1 / len(LIGAS)), "cm": [[r4(x) for x in row] for row in cmn.values], "pad": pad}
        if name == "posesion":
            Xs = StandardScaler().fit_transform(X)
            lda = LinearDiscriminantAnalysis(solver="eigen", shrinkage="auto", n_components=2).fit(Xs, y)
            Z = lda.transform(Xs)
            pts = []
            for li, l in enumerate(LIGAS):
                idx = np.where(y == l)[0]
                if len(idx) > 220:
                    idx = RNG.choice(idx, 220, replace=False)
                pts += [[li, r4(Z[k, 0]), r4(Z[k, 1])] for k in idx]
            cents = {l: [r4(Z[y == l, 0].mean()), r4(Z[y == l, 1].mean())] for l in LIGAS}
            ent["lda"] = {"pts": pts, "cent": cents, "evr": [r4(x) for x in lda.explained_variance_ratio_[:2]]}
        res[name] = ent
    return res


# --------------------------------------------------------------------- jugadores puente
SUFIJOS = {"jr", "sr", "ii", "iii", "iv"}


def name_key(n):
    if not isinstance(n, str):
        return None
    if "," in n:
        last, first = n.split(",", 1)
        n = first + " " + last
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()
    toks = [t for t in re.sub(r"[^a-z ]", " ", n).split() if t not in SUFIJOS and len(t) > 1]
    return " ".join(sorted(set(toks))) if toks else None


def team_tokens(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return {t for t in re.sub(r"[^a-z ]", " ", s).split() if len(t) > 3}


PAIRM = ["pts_p40", "pts_p100", "ts_pct", "efg_pct", "usg_pct", "ast_pct", "tov_pct", "reb_pct", "stl_pct", "blk_pct", "per", "ortg", "drtg",
         "game_score_p40", "pie", "min_pg"]


def bridges(reg, cur):
    reg = reg.copy(); reg["key"] = reg.nombre.map(name_key)
    same = {}
    for (i, j) in PARES:
        a = reg[reg.liga == LIGAS[i]]; b = reg[reg.liga == LIGAS[j]]
        m = a.merge(b, on="key", suffixes=("_a", "_b"))
        if len(m) == 0:
            continue
        mismo_club = int(sum(len(team_tokens(x) & team_tokens(y)) > 0 for x, y in zip(m.equipo_a, m.equipo_b)))
        ent = {"n": int(len(m)), "mismo_club": mismo_club}
        mm = m[(m.min_a >= 100) & (m.min_b >= 100)]
        ent["n100"] = int(len(mm))
        if len(mm) >= 8:
            w = 2 / (1 / mm.min_a + 1 / mm.min_b)
            dif = {}
            for c in PAIRM:
                xa = pd.to_numeric(mm[c + "_a"], errors="coerce"); xb = pd.to_numeric(mm[c + "_b"], errors="coerce")
                ok = xa.notna() & xb.notna()
                if ok.sum() < 8:
                    continue
                dd = (xa[ok] - xb[ok]).values; ww = w[ok].values
                est = wmean(dd, ww)
                boots = []
                for _ in range(2000):
                    k = RNG.integers(0, len(dd), len(dd))
                    boots.append(wmean(dd[k], ww[k]))
                lo, hi = np.quantile(boots, [0.025, 0.975])
                base = wmean(xb[ok].values, ww)
                dif[c] = [r4(est), r4(lo), r4(hi), r4(100 * est / base) if abs(base) > 1e-9 else None, int(ok.sum())]
            ent["dif"] = dif
            ent["ej"] = [x for x in mm.sort_values("min_a", ascending=False).nombre_b.head(6)]
        same[f"{i}-{j}"] = ent
    cross = {}
    if cur is not None:
        cur = cur.copy(); cur["key"] = cur.nombre.map(name_key)
        prev = reg.drop_duplicates(["key", "liga"])[["key", "liga"]]
        m = cur[["key", "liga"]].drop_duplicates().merge(prev, on="key", suffixes=("_27", "_26"))
        tab = m.groupby(["liga_26", "liga_27"]).size()
        cross = {f"{a}>{b}": int(n) for (a, b), n in tab.items()}
    return {"mismo_ano": same, "entre_temporadas": cross}


# --------------------------------------------------------------------- principal
df_minpart = {}


def main(salida="data/artifact"):
  OUT = Path(salida)
  temporadas = sorted(p.name for p in DATA.iterdir() if p.is_dir() and (p / "ligas").exists())
  en_curso = temporadas[-1]
  for i, season in enumerate(temporadas):
   siguiente = load(temporadas[i + 1], "regular") if i + 1 < len(temporadas) else None
   for phase in ("regular", "playoffs", "total"):
    thr = UMBRAL_EN_CURSO if season == en_curso else UMBRAL[phase]
    df = load(season, phase)
    if df is None:
        continue
    df["min"] = pd.to_numeric(df["min"], errors="coerce").fillna(0)
    for l, mp in df.groupby("liga")["minutos_partido"].first().items():
        df_minpart[l] = mp
    df = estimate_positions(df)
    el = df[df["min"] >= thr].copy()
    teams = team_table(df)
    cols = [c for c in ORDEN if c in df.columns and (GRUPO.get(c) != "identidad" or c in ID_NUM)]
    metricas = []
    for c in cols:
        v = pd.to_numeric(df[c], errors="coerce")
        if v.notna().sum() == 0:
            continue
        metricas.append(metric_block(el, teams, df, c))
    glf = gl_poss_factor(df)
    res = {
        "temporada": season, "fase": phase, "umbral_min": thr, "ligas": LIGAS, "pares": PARES,
        "n_elegibles": {l: int((el.liga == l).sum()) for l in LIGAS}, "n_filas": {l: int((df.liga == l).sum()) for l in LIGAS},
        "n_equipos": {l: int((teams.liga == l).sum()) for l in LIGAS},
        "metricas": metricas,
        "ortg": shapley_block(teams, glf),
        "escala": scale_block(el),
        "posicion": position_block(el),
        "equipos": team_spread(teams),
        "discrim": discrim_block(el) if el.liga.nunique() == len(LIGAS) else None,
        "pos_estimada": {l: [int(((el.liga == l) & (el.pos_est == 0)).sum()), int(((el.liga == l) & (el.pos_est > 0)).sum())] for l in LIGAS},
    }
    if phase == "regular" and season != en_curso:
        res["puentes"] = bridges(df, siguiente)
        # validación G League: oficial vs pipeline
        g = df[(df.liga == "gleague") & (df["min"] > 0)]
        vg = {}
        for a, b in [("src_pace", "team_pace"), ("src_ortg", "team_ortg"), ("src_drtg", "team_drtg"), ("src_usg_pct", "usg_pct"), ("src_ts_pct", "ts_pct")]:
            m = g[[a, b, "min"]].dropna()
            vg[a] = [r4(wmean(m[a].values, m["min"].values)), r4(wmean(m[b].values, m["min"].values))]
        res["validacion_gl"] = vg
    (OUT / season).mkdir(parents=True, exist_ok=True)
    with open(OUT / season / f"evaluacion_{phase}.json", "w") as f:
        json.dump(res, f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    print(season, phase, len(metricas), "métricas", {l: res["n_elegibles"][l] for l in LIGAS})


if __name__ == "__main__":
    main()
