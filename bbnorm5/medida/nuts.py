"""F3.3 · Contraste en NumPyro (NUTS) del modelo **por partido** en ligas-temporada representativas.

Para cada métrica de tiro (oportunidades enteras) y liga-temporada:

    k_g ~ Binomial(n_g, p_u)                         (modelo «bin»)
    k_g ~ BetaBinomial(n_g, c·p_u, c·(1 − p_u)),  c = (1 − ρ)/ρ      (modelo «bb»)
    logit p_u = μ_r(u) + σ·z_u,  z_u ~ N(0, 1)       (no centrado)
    μ_r ~ N(0, 2²),  σ ~ HalfNormal(1),  ρ ~ Beta(1, 30)

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


def _modelo(idx_u, rol_u, n, k=None, nr=3, sobred=True):
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    mu = numpyro.sample("mu", dist.Normal(0, 2).expand([nr]).to_event(1))
    s = numpyro.sample("sigma", dist.HalfNormal(1.0))
    nu = rol_u.shape[0]
    z = numpyro.sample("z", dist.Normal(0, 1).expand([nu]).to_event(1))
    eta = mu[rol_u] + s * z
    p = numpyro.deterministic("p", jnp.clip(1 / (1 + jnp.exp(-eta)), 1e-6, 1 - 1e-6))
    pg = p[idx_u]
    if sobred:
        rho = numpyro.sample("rho", dist.Beta(1.0, 30.0))
        c = (1 - rho) / rho
        numpyro.sample("k", dist.BetaBinomial(c * pg, c * (1 - pg), n), obs=k)
    else:
        numpyro.sample("k", dist.Binomial(n, probs=pg), obs=k)


def ajustar(d: pd.DataFrame, metrica: str, sobred: bool, cfg: dict):
    import arviz as az
    import jax
    import numpyro
    from numpyro.infer import MCMC, NUTS
    _, kc, nc, _ = D.METRICAS[metrica]
    x = d[d[nc] > 0]
    u = x.groupby(D.CLAVE + ["rol"], sort=False).size().reset_index()[D.CLAVE + ["rol"]]
    roles = [r for r in ("E", "A", "I", "X") if (u["rol"] == r).any()]
    u["iu"] = np.arange(len(u))
    x = x.merge(u, on=D.CLAVE + ["rol"])
    idx_u = x["iu"].to_numpy()
    rol_u = u["rol"].map({r: i for i, r in enumerate(roles)}).to_numpy()
    n = x[nc].to_numpy().astype(np.int32)
    k = x[kc].to_numpy().astype(np.int32)
    c = cfg["nuts"]
    mc = MCMC(NUTS(_modelo, target_accept_prob=0.9), num_warmup=c["calentamiento"], num_samples=c["muestras"],
              num_chains=c["cadenas"], chain_method="parallel", progress_bar=False)
    mc.run(jax.random.PRNGKey(cfg["semilla"]), idx_u, rol_u, n, k, len(roles), sobred)
    idata = az.from_numpyro(mc, log_likelihood=True)
    div = int(mc.get_extra_fields()["diverging"].sum())
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
                var = ["mu", "sigma"] + (["rho"] if sob else [])
                sm = az.summary(idata, var_names=var)
                zs = az.summary(idata, var_names=["z"])
                loo = az.loo(idata, pointwise=True)
                ids[nom] = idata
                h = hip[(hip.liga == liga) & (hip.temporada == temp) & (hip.metrica == met) & (hip.datos == "temporada")
                        & (hip.modelo == ("jer_sd" if sob else "jer"))].iloc[0]
                filas.append({"liga": liga, "temporada": temp, "metrica": met, "modelo": nom,
                              "partidos_obs": int(idata.observed_data["k"].size), "unidades": len(u),
                              "rhat_max": float(pd.concat([sm["r_hat"], zs["r_hat"]]).max()),
                              "ess_bulk_min": float(pd.concat([sm["ess_bulk"], zs["ess_bulk"]]).min()),
                              "ess_tail_min": float(pd.concat([sm["ess_tail"], zs["ess_tail"]]).min()),
                              "divergencias": div, "elpd_loo": float(loo.elpd_loo), "se_elpd": float(loo.se),
                              "pareto_k_malos": int((loo.pareto_k > 0.7).sum()),
                              "sigma_nuts": float(sm.loc["sigma", "mean"]), "sigma_nuts_sd": float(sm.loc["sigma", "sd"]),
                              "sigma_eb": float(h["sigma"]),
                              "rho_nuts": float(sm.loc["rho", "mean"]) if sob else 0.0,
                              "rho_nuts_hdi": f"{sm.loc['rho', 'hdi_3%']:.4f}–{sm.loc['rho', 'hdi_97%']:.4f}" if sob else "",
                              "rho_eb_momentos": float(h["disp"])})
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
