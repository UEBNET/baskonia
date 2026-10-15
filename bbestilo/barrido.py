"""¿Cuántos estilos admiten los datos? Barrido previo al entrenamiento (sin red), sobre la entrada de la VaDE.

Para k = 2…14, con los clubes de las temporadas de entrenamiento (rasgos transformados, estandarizados y sin nivel):
  * BIC e ICL de mezclas gaussianas (covarianza diagonal y completa): menos es mejor; ICL penaliza además los
    grupos solapados (prefiere estilos nítidos).
  * k-medias: silueta y estabilidad (ARI medio entre el ajuste completo y 10 submuestras del 80 %).
  * tamaño del grupo más pequeño de la mezcla (un estilo con muy pocos clubes no es un estilo).
Resultado: data/modelos/estilos/barrido_k.json. Se usa para fijar C.N_ESTILOS antes de `entrenar`.
"""
from __future__ import annotations

import json

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.mixture import GaussianMixture

from . import config as C
from .datos import construir


def barrido(ks=range(2, 15), semilla: int = 0) -> dict:
    cj = construir()
    sel = cj.clubes["temporada"].isin(C.TEMPORADAS_ENTRENO).to_numpy()
    X = cj.Xc[sel]
    rng = np.random.default_rng(semilla)
    out = {"k": list(ks), "n_clubes": int(len(X)), "rasgos": C.COLS}
    for cov in ("diag", "full"):
        out[f"bic_{cov}"], out[f"icl_{cov}"], out[f"min_grupo_{cov}"] = [], [], []
    out["silueta"], out["estabilidad"] = [], []
    for k in ks:
        for cov in ("diag", "full"):
            g = GaussianMixture(k, covariance_type=cov, n_init=4, reg_covar=1e-3, random_state=semilla).fit(X)
            r = g.predict_proba(X)
            bic = g.bic(X)
            out[f"bic_{cov}"].append(float(bic))
            out[f"icl_{cov}"].append(float(bic - 2 * (r * np.log(r + 1e-12)).sum()))
            out[f"min_grupo_{cov}"].append(int(np.bincount(r.argmax(1), minlength=k).min()))
        km = KMeans(k, n_init=10, random_state=semilla).fit(X)
        out["silueta"].append(float(silhouette_score(X, km.labels_)))
        aris = []
        for _ in range(10):
            m = rng.random(len(X)) < 0.8
            sub = KMeans(k, n_init=5, random_state=int(rng.integers(1e6))).fit(X[m])
            aris.append(adjusted_rand_score(km.labels_, sub.predict(X)))
        out["estabilidad"].append(float(np.mean(aris)))
        print(f"k={k:2d}  BIC diag {out['bic_diag'][-1]:9.0f}  ICL diag {out['icl_diag'][-1]:9.0f}  "
              f"BIC full {out['bic_full'][-1]:9.0f}  ICL full {out['icl_full'][-1]:9.0f}  "
              f"silueta {out['silueta'][-1]:.3f}  estabilidad {out['estabilidad'][-1]:.3f}  "
              f"grupo mínimo {out['min_grupo_diag'][-1]}", flush=True)
    for c in ("bic_diag", "icl_diag", "bic_full", "icl_full"):
        out[f"k_optimo_{c}"] = int(out["k"][int(np.argmin(out[c]))])
    (C.DIR_SALIDA / "barrido_k.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out
