"""F6.1 · Efectos de liga λ con los puentes intra-temporada: modelo conjunto en NumPyro (NUTS).

Para cada puente p (persona, temporada t, ligas a → b) y métrica m:

    d_pm ~ N(λ_{b,t,m} − λ_{a,t,m} + β_mᵀ Δx_p,  var_pm + σ_c,m²)

- λ_{ℓ,t} ∈ R^14: efecto de la liga ℓ en la temporada t sobre cada métrica (escala del enlace), relativo a la ACB
  (λ_ACB ≡ 0 sólo para estimar; la salida se re-expresa con cualquier liga como 0, porque las diferencias no dependen de
  la referencia).
- Temporadas: paseo aleatorio multivariante suave, λ_{ℓ,t} = λ_{ℓ,t−1} + diag(s_rw) L_Ω ξ_{ℓ,t}; λ_{ℓ,0} =
  diag(s_base) L_Ω ζ_ℓ. Ω (14 × 14) es la correlación entre métricas de los efectos de liga, con prior LKJ(2): una liga
  más física lo es en rebote y en tapones a la vez.
- β_m: contexto (minutos por partido, titularidad, calidad del rival, ritmo), que cambia entre las dos competiciones del
  mismo jugador.
- σ_c,m: variación extra de la diferencia que no es muestreo (papel distinto en cada competición).
- Prior externo opcional: la fuerza de liga por enfrentamientos europeos (F2) como media del λ de pts/100,
  λ_pts ~ media γ·fuerza/100 (γ con prior N(−1, 1)), en las ligas con fuerza estimada.
- Todo no centrado (ζ, ξ estándar).
"""
from __future__ import annotations

import os

os.environ.setdefault("XLA_FLAGS", "--xla_force_host_platform_device_count=4")

import numpy as np
import pandas as pd

from bbnorm5.ligas import datos as LD
from bbnorm5.medida import datos as DM

METRICAS = list(DM.METRICAS)
REF = "acb"
TROZO = 8_192
# bloques de métricas correlacionadas (si el modelo de las 14 es demasiado grande para NUTS): tiro y anotación;
# rebote, defensa y faltas; creación y uso
BLOQUES = {"tiro": ["t2_pct", "t3_pct", "tl_pct", "tpar", "ftr", "pts_p100"],
           "rebote_defensa": ["oreb_pct", "dreb_pct", "blk_pct", "stl_p100", "pf_p40"],
           "creacion": ["ast_pct", "tov_pct", "usg_pct"]}
# F7 (decisión del usuario): bloques reagrupados por la correlación de λ entre métricas que mostró la F6.1
# (pts–USG 0,98, pts–AST 0,92, pts–DREB 0,81, pts–OREB 0,74)
BLOQUES_PASO2 = {"volumen_papel": ["pts_p100", "usg_pct", "ast_pct", "dreb_pct", "oreb_pct"],
                 "tiro": ["t2_pct", "t3_pct", "tl_pct", "tpar", "ftr"],
                 "defensa_cuidado": ["blk_pct", "stl_p100", "pf_p40", "tov_pct"],
                 # F9 bis: zonas de tiro y % asistidas (sólo ligas con jugada a jugada)
                 "zonas": ["pct_aro", "pct_corta", "pct_media", "pct_t3_esquina", "pct_asistidas"]}


def indices(p: pd.DataFrame, temporadas: list[str], metricas: list[str] | None = None) -> dict:
    """Índices para el modelo. Cada métrica se estandariza por la DT de sus diferencias (escala comparable entre métricas:
    pts/100 y USG% viven en una escala 100 veces menor que las demás); la salida se devuelve a la escala del enlace."""
    metricas = metricas or METRICAS
    p = p[p["metrica"].isin(metricas)]
    esc = p.groupby("metrica")["d"].std()
    ligas = sorted(set(p["liga_a"]) | set(p["liga_b"]))
    ligas = [REF] + [l for l in ligas if l != REF]
    il = {l: i for i, l in enumerate(ligas)}
    it = {t: i for i, t in enumerate(temporadas)}
    im = {m: i for i, m in enumerate(metricas)}
    e = p["metrica"].map(esc).to_numpy(float)
    return {"ligas": ligas, "temporadas": temporadas, "metricas": metricas, "escala": esc.reindex(metricas).to_numpy(),
            "a": p["liga_a"].map(il).to_numpy(), "b": p["liga_b"].map(il).to_numpy(),
            "t": p["temporada"].map(it).to_numpy(), "m": p["metrica"].map(im).to_numpy(),
            "t_a": (p["temporada_a"] if "temporada_a" in p else p["temporada"]).map(it).to_numpy(),
            "inter": (p["tipo"] == "traspaso_entre_temporadas").to_numpy() if "tipo" in p else np.zeros(len(p), bool),
            "d": p["d"].to_numpy(float) / e, "var": p["var"].to_numpy(float) / e ** 2,
            "x": p[LD.CONTEXTO].to_numpy(float)}


def _modelo(I, fuerza=None, d=None):
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    L, T, M = len(I["ligas"]), len(I["temporadas"]), len(I["metricas"])
    Lo = numpyro.sample("L_omega", dist.LKJCholesky(M, 2.0))
    s_base = numpyro.sample("s_base", dist.HalfNormal(1.0).expand([M]).to_event(1))
    s_rw = numpyro.sample("s_rw", dist.HalfNormal(0.1).expand([M]).to_event(1))
    zeta = numpyro.sample("zeta", dist.Normal(0, 1).expand([L - 1, M]).to_event(2))
    xi = numpyro.sample("xi", dist.Normal(0, 1).expand([L - 1, T - 1, M]).to_event(3))
    base = zeta @ (s_base[:, None] * Lo).T                                   # (L−1) × M
    if fuerza is not None:
        gamma = numpyro.sample("gamma_fuerza", dist.Normal(-1.0, 1.0))
        if "pts_p100" in I["metricas"]:
            ip = I["metricas"].index("pts_p100")
            f0, fm = jnp.asarray(fuerza["media"]), jnp.asarray(fuerza["hay"])
            base = base.at[:, ip].add(gamma * f0 / 100.0 / I["escala"][ip] * fm)
    inc = xi @ (s_rw[:, None] * Lo).T                                         # (L−1) × (T−1) × M
    lam = base[:, None, :] + jnp.concatenate([jnp.zeros((L - 1, 1, M)), jnp.cumsum(inc, axis=1)], axis=1)
    lam = jnp.concatenate([jnp.zeros((1, T, M)), lam], axis=0)               # referencia = 0
    numpyro.deterministic("lambda", lam * jnp.asarray(I["escala"]))      # de vuelta a la escala del enlace
    beta = numpyro.sample("beta", dist.Normal(0, 0.5).expand([M, len(LD.CONTEXTO)]).to_event(2))
    s_c = numpyro.sample("s_c", dist.HalfNormal(0.5).expand([M]).to_event(1))
    hay_inter = I.get("inter") is not None and np.any(I["inter"])
    if hay_inter:
        # traspasos entre temporadas: su propia varianza extra (la de la proyección F4 ya va en var)
        s_i = numpyro.sample("s_inter", dist.HalfNormal(0.5).expand([M]).to_event(1))
    n = len(I["m"])
    # verosimilitud por trozos de ≤ TROZO filas: idéntica (suma de log-verosimilitudes), pero XLA en CPU pasa a una
    # estrategia ~100 veces más lenta en el gradiente de los gather por encima de ~40.000 filas (F7, paso 2)
    cortes = list(range(0, n, TROZO)) + [n]
    for k, (i0, i1) in enumerate(zip(cortes[:-1], cortes[1:])):
        sl = slice(i0, i1)
        a, b, t, m = I["a"][sl], I["b"][sl], I["t"][sl], I["m"][sl]
        t_a = I["t_a"][sl] if "t_a" in I else t
        mu = lam[b, t, m] - lam[a, t_a, m] + (jnp.asarray(I["x"][sl]) * beta[m]).sum(-1)
        extra = jnp.where(jnp.asarray(I["inter"][sl]), s_i[m] ** 2, s_c[m] ** 2) if hay_inter else s_c[m] ** 2
        sd = jnp.sqrt(jnp.asarray(I["var"][sl]) + extra)
        numpyro.sample("d" if len(cortes) == 2 else f"d_{k}", dist.Normal(mu, sd), obs=None if d is None else d[sl])


def fuerza_prior(I: dict) -> dict:
    """Media de la fuerza por liga (todas las temporadas) frente a la ACB; «hay» = 0 donde no hay enfrentamientos."""
    f = LD.fuerza_enfrentamientos()
    f = f[f["temporada"].isin(I["temporadas"])].groupby("liga")["fuerza"].mean()
    media = np.array([f.get(l, 0.0) for l in I["ligas"][1:]])
    hay = np.array([float(l in f.index) for l in I["ligas"][1:]])
    return {"media": media, "hay": hay}


def ajustar(I: dict, cfg: dict, con_fuerza: bool):
    import jax
    import numpyro
    from numpyro.infer import MCMC, NUTS
    numpyro.enable_x64()
    c = cfg["nuts"]
    mc = MCMC(NUTS(_modelo, target_accept_prob=c["target_accept"], max_tree_depth=c.get("max_tree_depth", 10)),
              num_warmup=c["calentamiento"], num_samples=c["muestras"], num_chains=c["cadenas"],
              chain_method="parallel", progress_bar=False)
    mc.run(jax.random.PRNGKey(cfg["semilla"]), I, fuerza_prior(I) if con_fuerza else None, I["d"],
           extra_fields=("diverging", "num_steps"))
    return mc


def traduccion(lam: np.ndarray, I: dict, temporada: str) -> pd.DataFrame:
    """Matriz de traducción T(a → b) = λ_b − λ_a por métrica (draws × L × L): media y cuantiles 10/90."""
    t = I["temporadas"].index(temporada)
    Lt = lam[:, :, t, :]                                    # draws × L × M
    D = Lt[:, None, :, :] - Lt[:, :, None, :]                # draws × a × b × M
    filas = []
    for ia, la in enumerate(I["ligas"]):
        for ib, lb in enumerate(I["ligas"]):
            for im, m in enumerate(I["metricas"]):
                x = D[:, ia, ib, im]
                filas.append((temporada, la, lb, m, x.mean(), np.quantile(x, 0.1), np.quantile(x, 0.9), x.std()))
    return pd.DataFrame(filas, columns=["temporada", "desde", "hacia", "metrica", "media", "q10", "q90", "sd"])
