"""F3 · Comprobación de la contracción: el peso de lo observado crece con la exposición como prec = τ⁻² + n/σ²_m.

En la escala del enlace (logit o log), con la tasa media p de la unidad, la observación de N oportunidades aporta una
precisión N·g(p)/infl (g = p(1 − p) en la binomial, p en la Poisson; infl = 1 + ρ(n̄_g − 1) o 1 + δ) y el prior,
1/σ². El peso teórico de lo observado es w = N/(N + n*_u), con n*_u = infl/(σ² g(p)). El peso empírico es la
fracción del camino que la posterior recorre desde la media del rol hasta la tasa cruda:
w_emp = (η_post − μ_r)/(η_obs − μ_r), con η_post = enlace(media posterior). Se comparan por tramos de exposición.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import special

from bbnorm5.medida import datos as D


def contraccion(post: pd.DataFrame, hiper: pd.DataFrame) -> pd.DataFrame:
    h = hiper[(hiper["datos"] == "temporada")]
    h = h.sort_values("modelo").drop_duplicates(["liga", "temporada", "metrica"], keep="last")
    p = post.merge(h[["liga", "temporada", "metrica", "modelo", "sigma", "disp", "mu_E", "mu_A", "mu_I", "mu_X"]],
                   on=["liga", "temporada", "metrica", "modelo"])
    fam = p["metrica"].map(lambda m: D.METRICAS[m][0])
    p = p[fam != "normal"].copy()
    fam = fam[fam != "normal"]
    b = (fam == "binomial").to_numpy()
    mu = np.choose(p["rol"].map({"E": 0, "A": 1, "I": 2, "X": 3}).to_numpy(),
                   [p[c].to_numpy() for c in ("mu_E", "mu_A", "mu_I", "mu_X")])
    K, N, G = p["K"].to_numpy(float), p["N"].to_numpy(float), p["G"].to_numpy(float)
    m = p["media"].to_numpy(float)
    enl = lambda x: np.where(b, special.logit(np.clip(x, 1e-6, 1 - 1e-6)), np.log(np.maximum(x, 1e-9)))
    eta_obs = enl((K + 0.5) / (N + 1.0))
    eta_post = enl(m)
    g = np.where(b, m * (1 - m), m)
    infl = np.where(b, 1 + p["disp"].to_numpy() * np.maximum(N / np.maximum(G, 1) - 1, 0), 1 + p["disp"].to_numpy())
    n_star = infl / (p["sigma"].to_numpy() ** 2 * g)
    p["w_teorico"] = N / (N + n_star)
    p["w_empirico"] = (eta_post - mu) / (eta_obs - mu)
    p["n_rel"] = N / n_star
    ok = np.abs(eta_obs - mu) > 0.25          # el cociente es inestable si la tasa cruda está junto a la media del rol
    p = p[ok & np.isfinite(p["w_empirico"])]
    p["tramo"] = pd.cut(p["n_rel"], [0, 0.25, 0.5, 1, 2, 4, 8, np.inf],
                        labels=["< 0,25", "0,25–0,5", "0,5–1", "1–2", "2–4", "4–8", "≥ 8"])
    return p.groupby("tramo", observed=True).agg(unidades=("w_empirico", "size"),
                                                 w_teorico=("w_teorico", "median"),
                                                 w_empirico=("w_empirico", "median")).reset_index()


def sensibilidad_estabilizacion(d: pd.DataFrame, metricas=("t2_pct", "t3_pct", "pts_p100")) -> pd.DataFrame:
    """n* mediano entre ligas-temporada según el prior (con o sin media por rol) y la población (todas las unidades o
    ≥ 100 minutos, como la F1). Separa lo que es verosimilitud de lo que es prior o población al comparar con la F1."""
    from bbnorm5.medida import eb
    mins = d.groupby(D.CLAVE)["min"].sum()
    res = []
    for (_, _), x in d.groupby(["liga", "temporada"]):
        for met in metricas:
            u = D.unidad_metrica(x, met, None)
            if len(u) < 30:
                continue
            fam = D.METRICAS[met][0]
            mm = np.asarray(u.set_index(D.CLAVE).index.map(mins))
            for nom, uu in (("todas · por rol", u), ("todas · sin rol", u.assign(rol="E")),
                            ("≥ 100 min · por rol", u[mm >= 100]), ("≥ 100 min · sin rol", u[mm >= 100].assign(rol="E"))):
                if fam == "normal":
                    m = eb.ajustar_normal(uu)
                    n = m["phi"] / m["tau2"]
                else:
                    n = eb.puntos_estabilizacion(eb.ajustar(uu, fam, True), uu)["n_estab"]
                res.append((met, nom, n))
    r = pd.DataFrame(res, columns=["metrica", "variante", "n_estab"])
    return r.groupby(["metrica", "variante"])["n_estab"].median().unstack().reset_index()
