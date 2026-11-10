"""F3.3 · Contraste en NumPyro (NUTS) del modelo **por partido** en ligas-temporada representativas.

Para cada métrica de tiro (oportunidades enteras) y liga-temporada (y, en la familia de conteos, robos por posesión
del rival con k_g ~ Poisson(n_g λ_u) frente a k_g ~ GammaPoisson, es decir, BinNeg1 con Var = μ(1 + δ)):

    k_g ~ Binomial(n_g, p_u)                         (modelo «bin»)
    k_g ~ BetaBinomial(n_g, c·p_u, c·(1 − p_u)),  c = (1 − ρ)/ρ      (modelo «bb»)
    logit p_u = μ_r(u) + σ·z_u,  z_u ~ N(0, 1)       (no centrado)
    μ_r ~ N(0, 2²),  σ ~ HalfNormal(1),  log c ~ N(5, 2²)   (en la Poisson, log δ ~ N(−3, 2²))

La verosimilitud se escribe a mano (`_loglik`, la misma fórmula que `eb.loglik`) y entra con `numpyro.factor`; la
log-verosimilitud por partido se guarda para el LOO. Primer intento descartado: `dist.BetaBinomial` con ρ ~ Beta(1, 30)
en precisión simple dio R̂ 1,54, ESS 7 y divergencias en todas las muestras en ACB T3% (ρ ≈ 0, concentraciones
enormes), y un elpd ~870 puntos por encima de la binomial, incompatible con ρ ≈ 0.

Sirve para tres cosas:
1. diagnósticos de la inferencia completa (R̂, ESS, divergencias);
2. LOO-PSIS por partido entre «bin» y «bb»: ¿hay sobredispersión dentro de jugador?;
3. comparar con el Bayes empírico de la F3.2: σ y ρ (allí por momentos y con la aproximación ρ_ef en la unidad) y
   las posteriores de cada jugador.
"""
from __future__ import annotations

import os

os.environ.setdefault("XLA_FLAGS", "--xla_force_host_platform_device_count=4")

import numpy as np
import pandas as pd

from bbnorm5.medida import datos as D

DIR = D.DIR / "nuts"
KMAX_POISSON = 16      # máximo de robos de un jugador en un partido + margen (comprobado en `ajustar`)


def _loglik(k, n, eta, familia: str, sobred: bool, lc=None):
    """Log-verosimilitud por partido, la misma fórmula que el Bayes empírico (`eb.loglik`), con su coeficiente
    combinatorio, para que el LOO compare modelos con la misma constante."""
    import jax.numpy as jnp
    from jax.scipy.special import betaln, gammaln
    if familia == "poisson":
        m = n * jnp.exp(eta)
        if not sobred:
            return k * jnp.log(m) - m - gammaln(k + 1)
        # forma exacta y estable cuando δ → 0 (k entero): lgamma(k+s) − lgamma(s) + k·log δ = Σ_{j<k} log(m + jδ),
        # y (m/δ)·log(1+δ) → m. Con gammaln directo, s = m/δ ~ 10¹² y la diferencia es ruido numérico.
        d = jnp.exp(lc)
        j = jnp.arange(KMAX_POISSON)[None, :]
        suma = jnp.where(j < k[:, None], jnp.log(m[:, None] + j * d), 0.0).sum(axis=1)
        l1p = jnp.where(d < 1e-6, 1 - d / 2, jnp.log1p(d) / d)
        return suma - gammaln(k + 1) - m * l1p - k * jnp.log1p(d)
    lch = gammaln(n + 1) - gammaln(k + 1) - gammaln(n - k + 1)
    if not sobred:
        return lch + k * jax_log_expit(eta) + (n - k) * jax_log_expit(-eta)
    c = jnp.exp(lc)
    p = jnp.clip(1 / (1 + jnp.exp(-eta)), 1e-9, 1 - 1e-9)
    return lch + betaln(k + c * p, n - k + c * (1 - p)) - betaln(c * p, c * (1 - p))


def jax_log_expit(x):
    import jax.numpy as jnp
    return -jnp.logaddexp(0.0, -x)


def _modelo(idx_u, rol_u, n, k=None, nr=3, sobred=True, familia="binomial", centrado=False):
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    mu = numpyro.sample("mu", dist.Normal(0, 2).expand([nr]).to_event(1))
    s = numpyro.sample("sigma", dist.HalfNormal(1.0))
    nu = rol_u.shape[0]
    if centrado:     # datos que dominan al prior (n por jugador ≫ n*): la parametrización centrada mezcla mejor
        eta = numpyro.sample("eta", dist.Normal(mu[rol_u], s).to_event(1))
        numpyro.deterministic("z", (eta - mu[rol_u]) / s)
    else:
        z = numpyro.sample("z", dist.Normal(0, 1).expand([nu]).to_event(1))
        eta = mu[rol_u] + s * z
    numpyro.deterministic("p", jnp.exp(eta) if familia == "poisson" else 1 / (1 + jnp.exp(-eta)))
    lc = None
    if sobred and familia == "poisson":
        lc = numpyro.sample("log_delta", dist.Normal(-3.0, 2.0))      # δ: exceso de varianza de la BinNeg1
        numpyro.deterministic("delta", jnp.exp(lc))
    elif sobred:
        lc = numpyro.sample("log_c", dist.Normal(5.0, 2.0))           # c = (1 − ρ)/ρ: concentración por partido
        numpyro.deterministic("rho", 1 / (1 + jnp.exp(lc)))
    ll = _loglik(k, n, eta[idx_u], familia, sobred, lc)
    numpyro.deterministic("ll", ll)
    numpyro.factor("verosimilitud", ll.sum())


def ajustar(d: pd.DataFrame, metrica: str, sobred: bool, cfg: dict):
    import arviz as az
    import jax
    import numpyro
    from numpyro.infer import MCMC, NUTS
    # doble precisión: con ρ ≈ 0 la beta-binomial tiene concentraciones c ~ 10⁴ y en float32 las diferencias de lgamma
    # pierden precisión; el gradiente sale ruidoso y la NUTS agota la profundidad del árbol en cada iteración
    numpyro.enable_x64()
    fam, kc, nc, _ = D.METRICAS[metrica]
    x = d[d[nc] > 0]
    u = x.groupby(D.CLAVE + ["rol"], sort=False).size().reset_index()[D.CLAVE + ["rol"]]
    roles = [r for r in ("E", "A", "I", "X") if (u["rol"] == r).any()]
    u["iu"] = np.arange(len(u))
    x = x.merge(u, on=D.CLAVE + ["rol"])
    idx_u = x["iu"].to_numpy()
    rol_u = u["rol"].map({r: i for i, r in enumerate(roles)}).to_numpy()
    n = x[nc].to_numpy(float)
    k = x[kc].to_numpy(float)
    if fam == "poisson" and k.max() >= KMAX_POISSON:
        raise ValueError(f"{metrica}: k máximo {k.max()} ≥ {KMAX_POISSON}")
    c = cfg["nuts"]
    mc = MCMC(NUTS(_modelo, target_accept_prob=0.9), num_warmup=c["calentamiento"], num_samples=c["muestras"],
              num_chains=c["cadenas"], chain_method="parallel", progress_bar=False)
    # regla fijada antes de ver los diagnósticos: centrada si la exposición mediana por jugador supera 10·n* (EB)
    n_u = np.bincount(idx_u, weights=n)
    from bbnorm5.medida import eb
    uu = D.unidad_metrica(d, metrica, None)
    m_eb = eb.ajustar(uu, fam, False)
    n_star = eb.puntos_estabilizacion(m_eb, uu)["n_estab"]
    centrado = bool(np.median(n_u) > 10 * n_star)
    mc.run(jax.random.PRNGKey(cfg["semilla"]), idx_u, rol_u, n.astype(np.float64), k.astype(np.float64), len(roles),
           sobred, fam, centrado)
    idata = az.from_numpyro(mc, log_likelihood=False)
    ll = idata.posterior["ll"]
    idata.add_groups({"log_likelihood": {"k": ll.values}}, coords={"chain": ll["chain"].values, "draw": ll["draw"].values})
    idata.posterior = idata.posterior.drop_vars("ll")
    div = int(mc.get_extra_fields()["diverging"].sum())
    idata.attrs["centrado"] = int(centrado)
    return idata, u, roles, div


def ejecutar(cfg: dict) -> dict:
    import arviz as az
    DIR.mkdir(parents=True, exist_ok=True)
    post_eb = pd.read_parquet(D.DIR / "posteriores.parquet")
    hip = pd.read_csv(D.DIR / "hiperparametros.csv")
    filas, comp, jug = [], [], []
    for liga, temp in cfg["nuts"]["ligas_temporada"]:
        d = pd.read_parquet(D.DIR / "partidos.parquet", filters=[("liga", "==", liga), ("temporada", "==", temp)])
        for met in cfg["nuts"]["metricas"]:
            ids = {}
            for sob in (False, True):
                nom = "bb" if sob else "bin"
                idata, u, roles, div = ajustar(d, met, sob, cfg)
                fam = D.METRICAS[met][0]
                par_sd = "rho" if fam == "binomial" else "delta"
                var = ["mu", "sigma"] + ([par_sd, "log_c" if fam == "binomial" else "log_delta"] if sob else [])
                sm = az.summary(idata, var_names=var)
                zs = az.summary(idata, var_names=["z"])
                loo = az.loo(idata, pointwise=True)
                ids[nom] = idata
                h = hip[(hip.liga == liga) & (hip.temporada == temp) & (hip.metrica == met) & (hip.datos == "temporada")
                        & (hip.modelo == ("jer_sd" if sob else "jer"))].iloc[0]
                filas.append({"liga": liga, "temporada": temp, "metrica": met, "modelo": nom,
                              "partidos_obs": int(idata.log_likelihood["k"].shape[-1]), "unidades": len(u),
                              "rhat_max": float(pd.concat([sm["r_hat"], zs["r_hat"]]).max()),
                              "ess_bulk_min": float(pd.concat([sm["ess_bulk"], zs["ess_bulk"]]).min()),
                              "ess_tail_min": float(pd.concat([sm["ess_tail"], zs["ess_tail"]]).min()),
                              "parametrizacion": "centrada" if idata.attrs.get("centrado") else "no centrada",
                              "divergencias": div, "elpd_loo": float(loo.elpd_loo), "se_elpd": float(loo.se),
                              "pareto_k_malos": int((loo.pareto_k > 0.7).sum()),
                              "sigma_nuts": float(sm.loc["sigma", "mean"]), "sigma_nuts_sd": float(sm.loc["sigma", "sd"]),
                              "sigma_eb": float(h["sigma"]),
                              "sobred_parametro": par_sd,
                              "sobred_nuts": float(sm.loc[par_sd, "mean"]) if sob else 0.0,
                              "sobred_nuts_hdi94": f"{sm.loc[par_sd, 'hdi_3%']:.4f}–{sm.loc[par_sd, 'hdi_97%']:.4f}" if sob else "",
                              "sobred_eb_momentos": float(h["disp"])})
                pd.DataFrame(filas).to_csv(DIR / "diagnosticos_parcial.csv", index=False)
                print(f"  {liga} {temp} {met} {nom}: R̂ {filas[-1]['rhat_max']:.3f}, ESS {filas[-1]['ess_bulk_min']:.0f}, "
                      f"div {div}, elpd {filas[-1]['elpd_loo']:.1f}", flush=True)
                # posteriores por jugador frente al EB
                p = idata.posterior["p"].stack(m=("chain", "draw")).values
                pe = post_eb[(post_eb.liga == liga) & (post_eb.temporada == temp) & (post_eb.metrica == met)
                             & (post_eb.modelo == ("jer_sd" if sob else "jer"))]
                x = u.assign(media_nuts=p.mean(axis=1), sd_nuts=p.std(axis=1)).merge(pe, on=D.CLAVE + ["rol"])
                jug.append(x[D.CLAVE + ["rol", "K", "N", "media_nuts", "sd_nuts", "media", "sd"]].assign(
                    metrica=met, modelo=nom))
            cmp = az.compare(ids, ic="loo")
            comp.append(cmp.reset_index().rename(columns={"index": "modelo"}).assign(liga=liga, temporada=temp,
                                                                                      metrica=met))
    r = pd.DataFrame(filas)
    r.to_csv(DIR / "diagnosticos.csv", index=False)
    pd.concat(comp).to_csv(DIR / "comparacion_loo.csv", index=False)
    j = pd.concat(jug)
    j.to_csv(DIR / "posteriores_nuts_frente_eb.csv.gz", index=False)
    acuerdo = j.groupby(["liga", "temporada", "metrica", "modelo"]).apply(
        lambda g: pd.Series({"corr_media": np.corrcoef(g["media_nuts"], g["media"])[0, 1],
                             "dif_media_abs": float((g["media_nuts"] - g["media"]).abs().mean()),
                             "ratio_sd": float((g["sd"] / g["sd_nuts"]).median())}), include_groups=False).reset_index()
    acuerdo.to_csv(DIR / "acuerdo_eb.csv", index=False)
    return {"ajustes": len(r), "rhat_max": float(r["rhat_max"].max()), "ess_min": float(r["ess_bulk_min"].min()),
            "divergencias": int(r["divergencias"].sum())}
