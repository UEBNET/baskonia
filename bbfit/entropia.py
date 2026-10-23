"""Fase 5 — entropía y volatilidad.

(1) H_estilo del jugador: entropía (bits) de su reparto de acciones = tiros por zona (aro, corta, media, triple
    de esquina y frontal; calibración de coordenadas de bbmodel/zonas.py en data/modelos/pista/calibracion.json o,
    si falta la liga-temporada, calibrada al vuelo), visitas al tiro libre (c·FTA), asistencias, pérdidas, faltas
    recibidas y rebotes ofensivos (caja de temporada). Sin coordenadas, el tiro se parte sólo en T2/T3
    (`nivel_categorias = basico`); `H_estilo_basico` existe para todos y es comparable entre ligas.
    Estimación bayesiana: p ~ Dirichlet(conteos + α·π_liga) → distribución de H (media e intervalo).
(2) H_rol: entropía del reparto de estados de rol partido a partido (fase 3) con el mismo tratamiento Dirichlet.
(3) Volatilidad intrínseca σ_i: producción por posesión de cada partido y_ig = 100·(PTS + w·AST)/posesiones en
    pista; se quita el contexto con un modelo con efecto fijo de jugador-equipo, rival (efecto fijo), minutos
    (log) y calidad de los compañeros presentes (media de su nivel μ_j ponderada por segundos): residuo e_ig.
    Heterocedasticidad por exposición: z_ig = e_ig·√(pos_ig/P0) → var(z) = σ_i² a P0 posesiones.
    log s_i² (corregido de sesgo) se contrae por grupo (liga × pos3): bayes empírico normal-normal con varianza
    de muestreo 2/(n_i − 1); σ_i = exp(media posterior/2) con intervalo.
(4) Equipo: Herfindahl y entropía del reparto de USG% (volumen de uso), de tiros y de minutos, y entropía de la
    red de pases (asistencias A→B), normalizada por log2 del número de aristas posibles.
Parámetros en configs/entropia.yaml.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy import stats

from . import datos as D
from .config import DIR_MOD, cargar
from .roles import ROLES

DIR_ENT = DIR_MOD / "entropia"
DIR_ROLES = DIR_MOD / "roles"


def _cfg() -> dict:
    return cargar("entropia")


def entropia_bits(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return -np.nansum(np.where(p > 0, p * np.log2(p), 0.0), axis=-1)


def entropia_dirichlet(conteos: np.ndarray, prior: np.ndarray, alpha: float, muestras: int, rng: np.random.Generator,
                       nivel: float = 0.9) -> pd.DataFrame:
    """Distribución posterior de H (bits) con p ~ Dirichlet(conteos + α·prior), fila a fila (NaN en conteos =
    categoría no observable: se excluye)."""
    C = np.asarray(conteos, float)
    n, K = C.shape
    pri = np.broadcast_to(np.asarray(prior, float), (n, K)).copy()
    ok = ~np.isnan(C)
    pri = np.where(ok, pri, 0.0)
    s = pri.sum(axis=1, keepdims=True)
    pri = np.where(s > 0, pri / np.where(s > 0, s, 1), 0.0)
    A = np.where(ok, np.nan_to_num(C) + alpha * pri, 0.0)
    A = np.where(ok & (A <= 0), 1e-6, A)
    out = np.full((n, 3), np.nan)
    lo, hi = (1 - nivel) / 2, 1 - (1 - nivel) / 2
    for i0 in range(0, n, 2000):
        a = A[i0:i0 + 2000]
        G = rng.gamma(np.where(a > 0, a, 1.0)[:, None, :], size=(len(a), muestras, K))
        G = np.where((a > 0)[:, None, :], G, 0.0)
        P = G / G.sum(axis=2, keepdims=True)
        H = entropia_bits(P)
        out[i0:i0 + 2000] = np.c_[H.mean(1), np.quantile(H, lo, axis=1), np.quantile(H, hi, axis=1)]
    k = ok.sum(axis=1)
    res = pd.DataFrame(out, columns=["H_media", "H_lo", "H_hi"])
    res["H_bruta"] = entropia_bits(np.where(ok, np.nan_to_num(C), 0) / np.maximum(np.nan_to_num(C).sum(1, keepdims=True), 1))
    res["K"] = k
    res["H_norm"] = res["H_media"] / np.log2(np.maximum(k, 2))
    return res


# =============================================================================== (1) estilo

def _sistema(liga: str, temp: str, ti: pd.DataFrame, cal: dict, minimo: float):
    from bbmodel import zonas as Z
    campo = ti[ti["tipo"].isin(["T2", "T3"])]
    if campo.empty or campo[["x", "y"]].notna().all(axis=1).mean() < 0.5:
        return None, "sin_coordenadas"
    c = cal.get(f"{liga}|{temp}")
    if c:
        sis = Z.Sistema(liga, c["regla"], c["eje_largo"], tuple(c["aro"]), tuple(c["escala"]), c.get("pista_completa"))
        return (sis, "calibracion.json") if c["acierto"] >= minimo else (None, "acierto_bajo")
    if liga not in Z.INICIAL or ti[["x", "y"]].dropna().empty:
        return None, "sin_coordenadas"
    sis, ac = Z.calibrar(liga, ti)
    return (sis, "al_vuelo") if ac >= minimo else (None, "acierto_bajo")


def acciones(liga: str, temp: str, cfg: dict, cal: dict, fases: list[str], coef: float) -> pd.DataFrame:
    """Conteos de acciones por jugador-equipo (tiros por zona y básicos de tiros.csv.gz; resto de la caja)."""
    from bbmodel import zonas as Z
    e = cfg["estilo"]
    ti = D.tiros(liga, temp)
    out = None
    nivel = "basico"
    origen = "sin_tiros"
    if not ti.empty:
        ti = ti[ti["fase"].isin(fases)]
        campo = ti[ti["tipo"].isin(["T2", "T3"])]
        k = ["team_id", "player_id"]
        base = campo.groupby(k + ["tipo"]).size().unstack(fill_value=0).reindex(columns=["T2", "T3"], fill_value=0)
        tl = ti[ti["tipo"] == "TL"].groupby(k).size().rename("fta")
        out = base.join(tl, how="outer").fillna(0)
        out["visitas_tl"] = coef * out["fta"]
        sis, origen = _sistema(liga, temp, ti, cal, float(e["acierto_minimo_zonas"]))
        if sis is not None:
            p = Z.perfil_tiro(campo, sis)
            zz = p.groupby(k + ["zona"]).size().unstack(fill_value=0).reindex(columns=e["categorias_tiro_zonas"], fill_value=0)
            # tiros sin coordenadas válidas de un jugador: la parte por zonas sólo es usable si cubre >= 90 %
            out = out.join(zz, how="left")
            cub = zz.sum(axis=1).reindex(out.index).fillna(0) / (out["T2"] + out["T3"]).replace(0, np.nan)
            out["cobertura_zonas"] = cub
            nivel = "zonas"
        out = out.reset_index()
    lg = D.ligas(liga, temp)
    if not lg.empty:
        lg = lg[lg["fase"].isin(fases)].copy()
        cols = {"ast": "ast", "tov": "tov", "pfd": "pfd", "oreb": "oreb"}
        for c_ in cols:
            lg[c_] = pd.to_numeric(lg.get(c_), errors="coerce")
        caja = lg.groupby(["team_id", "player_id"])[list(cols)].sum(min_count=1).reset_index()
        # traspasados fusionados por la fuente: se asigna al único equipo del jugador en los tiros
        if out is not None:
            fus = caja[caja["team_id"].astype(str).str.contains(";")]
            caja = caja[~caja["team_id"].astype(str).str.contains(";")]
            out = out.merge(caja, on=["team_id", "player_id"], how="outer" if not len(fus) else "left")
            if len(fus):
                f = fus.drop(columns="team_id").drop_duplicates("player_id").set_index("player_id")
                falta = out["ast"].isna() & out["player_id"].isin(f.index)
                for c_ in cols:
                    out.loc[falta, c_] = out.loc[falta, "player_id"].map(f[c_])
                out.loc[falta, "caja_fusionada"] = True
        else:
            out = caja
    if out is None:
        return pd.DataFrame()
    out["nivel_categorias"] = nivel
    out["origen_zonas"] = origen
    out.insert(0, "temporada", temp)
    out.insert(0, "liga", liga)
    return out


def estilo_liga(acc: pd.DataFrame, cfg: dict, rng) -> pd.DataFrame:
    e = cfg["estilo"]
    caja = e["categorias_caja"]
    bas = e["categorias_tiro_basicas"] + caja
    filas = acc.copy()
    for c_ in bas:
        if c_ not in filas:
            filas[c_] = np.nan
    # la liga no publica una categoría (p. ej. faltas recibidas en la NBA): NaN para todos, no 0
    for c_ in caja:
        if filas[c_].notna().sum() == 0:
            filas[c_] = np.nan
    Cb = filas[bas].to_numpy(float, copy=True)
    publicada = ~filas[bas].isna().all().to_numpy()
    Cb[np.isnan(Cb) & publicada[None, :]] = 0.0          # jugador sin fila de caja en una categoría publicada: 0
    pri = np.nansum(Cb, axis=0)
    rb = entropia_dirichlet(Cb, pri / pri.sum() if pri.sum() else np.ones(len(bas)), float(e["alpha_prior"]),
                            int(e["muestras"]), rng, float(e["nivel_intervalo"]))
    filas[["H_estilo_basico", "H_estilo_basico_lo", "H_estilo_basico_hi", "H_estilo_basico_bruta", "K_basico",
           "H_estilo_basico_norm"]] = rb.to_numpy()
    zon = e["categorias_tiro_zonas"]
    if (filas["nivel_categorias"] == "zonas").any() and all(z in filas for z in zon):
        cats = zon + caja
        Cz = filas[cats].to_numpy(float, copy=True)
        Cz[np.isnan(Cz) & (~filas[cats].isna().all().to_numpy())[None, :]] = 0.0
        malo = (filas["cobertura_zonas"].fillna(0) < 0.9).to_numpy()
        Cz[malo] = np.nan
        pri = np.nansum(Cz, axis=0)
        rz = entropia_dirichlet(np.where(malo[:, None], 0, Cz), pri / pri.sum() if pri.sum() else np.ones(len(cats)),
                                float(e["alpha_prior"]), int(e["muestras"]), rng, float(e["nivel_intervalo"]))
        rz.loc[malo] = np.nan
        filas[["H_estilo", "H_estilo_lo", "H_estilo_hi", "H_estilo_bruta", "K_estilo", "H_estilo_norm"]] = rz.to_numpy()
        filas.loc[malo, "nivel_categorias"] = "basico"
    else:
        filas[["H_estilo", "H_estilo_lo", "H_estilo_hi", "H_estilo_bruta", "K_estilo", "H_estilo_norm"]] = \
            filas[["H_estilo_basico", "H_estilo_basico_lo", "H_estilo_basico_hi", "H_estilo_basico_bruta", "K_basico",
                   "H_estilo_basico_norm"]].to_numpy()
    tot = np.nansum(Cb, axis=1)
    filas["acciones"] = tot
    filas["muestra_pequena"] = tot < float(e["min_acciones"])
    falta = np.isnan(Cb[:, len(e["categorias_tiro_basicas"]):])
    filas["categorias_faltantes"] = [";".join(np.array(caja)[m]) for m in falta]
    return filas


# =============================================================================== (2) rol

def entropia_rol(tr: pd.DataFrame, cfg: dict, rng) -> pd.DataFrame:
    e = cfg["estilo"]
    t = tr[tr["fuente"] == "pbp"].copy()
    out = []
    for (liga, temp), d in t.groupby(["liga", "temporada"]):
        N = d[[f"n_{k}" for k in ROLES]].to_numpy(float)
        N = np.nan_to_num(N)
        pri = N.sum(0)
        r = entropia_dirichlet(N, pri / pri.sum() if pri.sum() else np.ones(len(ROLES)), float(cargar("roles")["roles"]["dirichlet_alpha"]),
                               int(e["muestras"]), rng, float(e["nivel_intervalo"]))
        dd = d[["liga", "temporada", "team_id", "player_id"]].copy()
        dd[["H_rol_post", "H_rol_lo", "H_rol_hi"]] = r[["H_media", "H_lo", "H_hi"]].to_numpy()
        out.append(dd)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


# =============================================================================== (3) volatilidad

def _residuos_liga(d: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    v = cfg["volatilidad"]
    d = d.copy()
    d["clave"] = d["team_id"].astype(str) + "|" + d["player_id"].astype(str)
    w = d["poss_on"].to_numpy(float)
    # nivel μ de cada jugador-equipo (1.ª pasada) y calidad de los compañeros presentes en el partido
    mu = (d["y"] * d["poss_on"]).groupby(d["clave"]).sum() / d["poss_on"].groupby(d["clave"]).sum()
    d["mu"] = d["clave"].map(mu)
    tot = d.groupby(["game_id", "team_id"]).apply(lambda g: pd.Series({"S": (g["sec"] * g["mu"]).sum(),
                                                                       "T": g["sec"].sum()}), include_groups=False)
    d = d.merge(tot.reset_index(), on=["game_id", "team_id"], how="left")
    d["ctx_comp"] = (d["S"] - d["sec"] * d["mu"]) / (d["T"] - d["sec"]).replace(0, np.nan)
    d["log_min"] = np.log(d["sec"] / 60)
    d["ctx_comp"] = d["ctx_comp"].fillna(d["ctx_comp"].mean())
    # efecto fijo de jugador-equipo por centrado ponderado; rival como variables indicadoras
    X = pd.get_dummies(d["opp_id"].astype(str), drop_first=True, dtype=float)
    X["log_min"] = d["log_min"]
    X["ctx_comp"] = d["ctx_comp"]
    Y = d["y"].astype(float)
    sw = pd.Series(w, index=d.index).groupby(d["clave"]).transform("sum")

    def centrar(s):
        return s - (s * w).groupby(d["clave"]).transform("sum") / sw
    Xc = X.apply(centrar)
    Yc = centrar(Y)
    sq = np.sqrt(w)
    beta, *_ = np.linalg.lstsq(Xc.to_numpy() * sq[:, None], Yc.to_numpy() * sq, rcond=None)
    d["resid"] = Yc.to_numpy() - Xc.to_numpy() @ beta
    d["z"] = d["resid"] * np.sqrt(d["poss_on"] / float(v["posesiones_referencia"]))
    d.attrs["coef_log_min"] = float(beta[-2])
    d.attrs["coef_ctx_comp"] = float(beta[-1])
    return d


def volatilidad(pj: pd.DataFrame, pos3: pd.Series, cfg: dict) -> tuple[pd.DataFrame, dict]:
    v = cfg["volatilidad"]
    j = pj[pj["jugo"] & (pj["poss_on"] >= float(v["min_posesiones_partido"]))].copy()
    ast = j["ast"].fillna(0) if "ast" in j else 0
    j["y"] = 100 * (j["pts"] + float(v["peso_ast"]) * ast) / j["poss_on"]
    j["sin_ast"] = j["ast"].isna() if "ast" in j else True
    filas, coefs = [], {}
    for (liga, temp), d in j.groupby(["liga", "temporada"]):
        if len(d) < 50:
            continue
        r = _residuos_liga(d, cfg)
        coefs[f"{liga}|{temp}"] = {"log_min": r.attrs["coef_log_min"], "ctx_comp": r.attrs["coef_ctx_comp"]}
        g = r.groupby(["team_id", "player_id"])
        s = pd.DataFrame({"n_partidos_vol": g.size(), "s2": g["z"].apply(lambda z: float((z ** 2).sum())),
                          "y_media": g["y"].mean(), "sin_ast": g["sin_ast"].any()}).reset_index()
        s["s2"] = s["s2"] / (s["n_partidos_vol"] - 1).clip(lower=1)
        s["liga"], s["temporada"] = liga, temp
        filas.append(s)
    s = pd.concat(filas, ignore_index=True)
    s = s[s["n_partidos_vol"] >= int(v["min_partidos"])].copy()
    df = s["n_partidos_vol"] - 1
    s["log_s2"] = np.log(s["s2"].clip(lower=1e-6)) + 1 / df          # E[log s²] ≈ log σ² − 1/gl
    s["var_muestreo"] = 2 / df
    s["pos3"] = [pos3.get((l, p), np.nan) for l, p in zip(s["liga"], s["player_id"])]
    s["pos3"] = s["pos3"].fillna("NA")
    z = float(stats.norm.ppf(0.5 + float(v["nivel_intervalo"]) / 2))
    out = []
    for _, d in s.groupby(list(v["grupos"])):
        m = np.average(d["log_s2"], weights=1 / d["var_muestreo"])
        tau2 = max(0.0, float(d["log_s2"].var()) - float(d["var_muestreo"].mean())) if len(d) > 2 else 0.0
        w = tau2 / (tau2 + d["var_muestreo"]) if tau2 > 0 else 0.0 * d["var_muestreo"]
        d = d.copy()
        d["log_s2_post"] = w * d["log_s2"] + (1 - w) * m
        d["log_s2_sd"] = np.sqrt(w * d["var_muestreo"]) if tau2 > 0 else 0.0
        d["tau2_grupo"] = tau2
        d["w_contraccion"] = w
        out.append(d)
    s = pd.concat(out, ignore_index=True)
    s["sigma"] = np.exp(s["log_s2_post"] / 2)
    s["sigma_lo"] = np.exp((s["log_s2_post"] - z * s["log_s2_sd"]) / 2)
    s["sigma_hi"] = np.exp((s["log_s2_post"] + z * s["log_s2_sd"]) / 2)
    s["sigma_bruta"] = np.sqrt(s["s2"])
    return s.drop(columns=["s2"]), coefs


# =============================================================================== (4) equipo

def _hhi_h(x: np.ndarray) -> tuple[float, float, float]:
    x = np.asarray(x, float)
    x = x[np.isfinite(x) & (x > 0)]
    if not len(x):
        return np.nan, np.nan, np.nan
    p = x / x.sum()
    h = float(entropia_bits(p))
    return float((p ** 2).sum()), h, float(2 ** h)


def equipos(pj: pd.DataFrame, tr: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    j = pj[pj["jugo"]]
    g = j.groupby(["liga", "temporada", "team_id", "player_id"]).agg(sec=("sec", "sum"), fga=("fga", "sum"),
                                                                     fta=("fta", "sum"), coef=("coef_tl", "first")).reset_index()
    g["uso"] = g["fga"] + g["coef"] * g["fta"]
    h_rol = tr.assign(w=tr["min_total"]).dropna(subset=["H_rol"])
    h_rol = (h_rol["H_rol"] * h_rol["w"]).groupby([h_rol["liga"], h_rol["temporada"], h_rol["team_id"]]).sum() / \
        h_rol["w"].groupby([h_rol["liga"], h_rol["temporada"], h_rol["team_id"]]).sum()
    filas = []
    cache_ast = {}
    for (liga, temp, team), d in g.groupby(["liga", "temporada", "team_id"]):
        f = {"liga": liga, "temporada": temp, "team_id": team, "jugadores": len(d)}
        for nombre, col in (("uso", "uso"), ("tiros", "fga"), ("minutos", "sec")):
            hhi, h, ne = _hhi_h(d[col].to_numpy())
            f[f"hhi_{nombre}"], f[f"H_{nombre}"], f[f"n_efectivo_{nombre}"] = hhi, h, ne
            f[f"H_{nombre}_norm"] = h / np.log2(len(d)) if len(d) > 1 and np.isfinite(h) else np.nan
        key = (liga, temp)
        if key not in cache_ast:
            a = D.quintetos_fichero(liga, temp, "asistencias.csv")
            if len(a):
                fase = "total" if (a["fase"] == "total").any() else "regular"
                a = a[a["fase"] == fase]
            cache_ast[key] = a
        a = cache_ast[key]
        if len(a):
            e = a[a["team_id"] == team]
            hhi, h, ne = _hhi_h(e["ast"].to_numpy())
            nodos = len(set(e["pasador_id"]) | set(e["receptor_id"]))
            f.update({"H_red_pases": h, "hhi_red_pases": hhi, "aristas_red": int((e["ast"] > 0).sum()), "nodos_red": nodos,
                      "H_red_pases_norm": h / np.log2(nodos * (nodos - 1)) if nodos > 1 and np.isfinite(h) else np.nan,
                      "H_pasadores": _hhi_h(e.groupby("pasador_id")["ast"].sum().to_numpy())[1],
                      "H_receptores": _hhi_h(e.groupby("receptor_id")["ast"].sum().to_numpy())[1],
                      "asistencias": float(e["ast"].sum())})
        else:
            f.update({"H_red_pases": np.nan, "sin_red_pases": True})
        f["H_rol_medio_minutos"] = h_rol.get((liga, temp, team), np.nan)
        filas.append(f)
    return pd.DataFrame(filas)


# =============================================================================== orquestación

def main(temporadas: list[str] | None = None) -> dict:
    from .registro import experimento
    cfg = _cfg()
    rcfg = cargar("roles")
    DIR_ENT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(int(cfg["semilla"]))
    with experimento("entropia", "entropia_v1", params=cfg, semilla=cfg["semilla"]) as run:
        tr = pd.read_csv(DIR_ROLES / "player_role_season.csv.gz", dtype={"team_id": str, "player_id": str}, low_memory=False)
        temps = temporadas or sorted(tr["temporada"].unique())
        tr = tr[tr["temporada"].isin(temps)]
        partes = [pd.read_csv(DIR_ROLES / "partidos_jugador" / f"{t}.csv.gz",
                              dtype={"team_id": str, "player_id": str, "game_id": str, "opp_id": str}, low_memory=False)
                  for t in temps if (DIR_ROLES / "partidos_jugador" / f"{t}.csv.gz").exists()]
        pj = pd.concat(partes, ignore_index=True)
        pj["jugo"] = pj["jugo"].astype(str).str.lower().isin(["true", "1"])
        cal_p = DIR_MOD / "pista" / "calibracion.json"
        cal = json.loads(cal_p.read_text()) if cal_p.exists() else {}
        est = []
        for (liga, temp), _ in tr.groupby(["liga", "temporada"]):
            acc = acciones(liga, temp, cfg, cal, rcfg["partido"]["fases"], float(rcfg["partido"]["coef_tl"]))
            if len(acc):
                est.append(estilo_liga(acc, cfg, rng))
                print(f"[entropia] estilo {liga} {temp}: {len(acc)}", flush=True)
        est = pd.concat(est, ignore_index=True)
        hr = entropia_rol(tr, cfg, rng)
        pos3 = tr.drop_duplicates(["liga", "player_id"]).set_index(["liga", "player_id"])["pos3"]
        vol, coefs = volatilidad(pj, pos3, cfg)
        base = tr[["liga", "temporada", "team_id", "player_id", "persona_id", "nombre", "pos3", "fuente", "gp",
                   "min_total", "rol_mas_probable", "H_rol", "H_rol_norm"] + [f"n_{k}" for k in ROLES]]
        jug = base.merge(est, on=["liga", "temporada", "team_id", "player_id"], how="outer")
        jug = jug.merge(hr, on=["liga", "temporada", "team_id", "player_id"], how="left")
        jug = jug.merge(vol.drop(columns=["pos3"]), on=["liga", "temporada", "team_id", "player_id"], how="left")
        jug.to_csv(DIR_ENT / "jugadores.csv.gz", index=False, float_format="%.4f")
        eq = equipos(pj, tr, cfg)
        eq.to_csv(DIR_ENT / "equipos.csv", index=False, float_format="%.4f")
        ok = jug["H_estilo"].notna()
        res = {"jugadores": len(jug), "con_H_estilo": int(ok.sum()),
               "nivel_categorias": jug["nivel_categorias"].value_counts().to_dict(),
               "origen_zonas": est.groupby(["liga", "temporada"])["origen_zonas"].first().value_counts().to_dict(),
               "H_estilo_basico_mediana_por_liga": jug.groupby("liga")["H_estilo_basico"].median().round(3).to_dict(),
               "con_sigma": int(jug["sigma"].notna().sum()),
               "sigma_mediana_por_liga": jug.groupby("liga")["sigma"].median().round(2).to_dict(),
               "coef_contexto": coefs, "equipos": len(eq),
               "corr_H_estilo_H_rol": float(jug[["H_estilo_basico", "H_rol_post"]].corr().iloc[0, 1])}
        (DIR_ENT / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        run.metricas({"jugadores": res["jugadores"], "con_sigma": res["con_sigma"]})
        run.artefacto(DIR_ENT / "resumen.json")
    return res
