"""Evaluación y comparación de las dos redes.

Todo se mide sobre los clubes reales de las temporadas de entrenamiento salvo donde se indica.
Bloques:
  1. Reparto y confianza: tamaño de cada estilo, entropía del reparto, salida máxima media.
  2. Separación: silueta en el mapa 3D y en los 13 rasgos, Davies-Bouldin, Calinski-Harabasz.
     Referencia: k-medias con 12 grupos directamente sobre los 13 rasgos (sin red).
  3. Estabilidad: ARI entre las 5 semillas; robustez frente al reparto de minutos (plantillas
     remuestreadas que conservan el estilo); reproducibilidad temporal (red entrenada sin 2024-25 ni
     2025-26 frente a la red completa, sobre esos clubes).
  4. Fidelidad del mapa: trustworthiness y continuidad (k = 10), estrés y correlación de Spearman
     entre distancias del mapa y del perfil; R² de reconstrucción por rasgo.
  5. Diferenciación estadística de los 12 estilos: distancia de Mahalanobis entre sus perfiles medios
     (covarianza intra-estilo común), prueba de permutación por pareja con corrección de Holm, η² por
     rasgo y replicabilidad de los perfiles entre 2020-23 y 2023-26. Las pruebas entre grupos formados
     con los mismos datos son optimistas por construcción; la replicabilidad temporal no lo es.
  6. Uso: persistencia del estilo de un club de una temporada a la siguiente y coherencia de las
     plantillas (cuota de minutos de la plantilla en el estilo de su club).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import torch
from scipy.stats import spearmanr
from sklearn.cluster import KMeans
from sklearn.manifold import trustworthiness
from sklearn.metrics import (adjusted_rand_score, calinski_harabasz_score, davies_bouldin_score,
                             normalized_mutual_info_score, silhouette_score)

from . import config as C
from .datos import Conjunto, remuestrear


def _t(a) -> torch.Tensor:
    return torch.tensor(np.asarray(a), dtype=torch.float32)


@torch.no_grad()
def predecir(red, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(probabilidades de las 12 neuronas, coordenadas en el mapa)."""
    x = _t(X)
    return red.salida(x).numpy(), red.mapa(x).numpy()


def _holm(p: np.ndarray) -> np.ndarray:
    orden = np.argsort(p)
    m = len(p)
    aj = np.empty(m)
    acum = 0.0
    for r, i in enumerate(orden):
        acum = max(acum, min(1.0, (m - r) * p[i]))
        aj[i] = acum
    return aj


def diferenciacion(X: np.ndarray, lab: np.ndarray, rng: np.random.Generator, n_perm: int = 9999) -> dict:
    """n_perm = 9.999: con 66 parejas, Holm necesita p < 0,05/66 ≈ 0,00076 en la más extrema, y el p
    mínimo de una permutación es 1/(n_perm + 1)."""
    k = C.N_ESTILOS
    presentes = [a for a in range(k) if (lab == a).sum() >= 3]
    medias = np.array([X[lab == a].mean(0) for a in range(k)])
    resid = np.vstack([X[lab == a] - medias[a] for a in presentes])
    S = np.cov(resid.T) + 1e-6 * np.eye(X.shape[1])
    Si = np.linalg.inv(S)
    pares, D2, pv = [], [], []
    for i, a in enumerate(presentes):
        for b in presentes[i + 1:]:
            Xa, Xb = X[lab == a], X[lab == b]
            d = medias[a] - medias[b]
            d2 = float(d @ Si @ d)
            Z = np.vstack([Xa, Xb])
            na = len(Xa)
            # permutación: reparte las etiquetas al azar y recalcula la distancia entre medias
            nul = []
            for i0 in range(0, n_perm, 1000):
                P = np.argsort(rng.random((min(1000, n_perm - i0), len(Z))), axis=1)
                dd = Z[P[:, :na]].mean(1) - Z[P[:, na:]].mean(1)
                nul.append(np.einsum("pi,ij,pj->p", dd, Si, dd))
            nul = np.concatenate(nul)
            pares.append((a, b))
            D2.append(d2)
            pv.append((1 + (nul >= d2).sum()) / (n_perm + 1))
    D = np.sqrt(np.array(D2))
    aj = _holm(np.array(pv))
    tot = ((X - X.mean(0)) ** 2).sum(0)
    entre = sum(((lab == a).sum() * (medias[a] - X.mean(0)) ** 2) for a in presentes)
    eta2 = entre / tot
    return {"pares": len(pares), "pares_distintos_holm_05": int((aj < 0.05).sum()),
            "mahalanobis_min": float(D.min()), "mahalanobis_mediana": float(np.median(D)),
            "pareja_mas_cercana": [int(pares[int(D.argmin())][0]) + 1, int(pares[int(D.argmin())][1]) + 1],
            "eta2_por_rasgo": {r.col: float(e) for r, e in zip(C.RASGOS, eta2)},
            "p_max_ajustado": float(aj.max())}


def replicabilidad(X: np.ndarray, lab: np.ndarray, temporadas: np.ndarray) -> dict:
    """Correlación entre el perfil medio de cada estilo en 2020-23 y en 2023-26."""
    t1 = np.isin(temporadas, C.TEMPORADAS_ENTRENO[:3])
    cors = []
    for a in range(C.N_ESTILOS):
        s1, s2 = t1 & (lab == a), ~t1 & (lab == a)
        if s1.sum() >= 5 and s2.sum() >= 5:
            cors.append(float(np.corrcoef(X[s1].mean(0), X[s2].mean(0))[0, 1]))
    return {"estilos_comparables": len(cors), "correlacion_media": float(np.mean(cors)) if cors else None,
            "correlacion_min": float(np.min(cors)) if cors else None}


def persistencia(clubes: pd.DataFrame, lab: np.ndarray) -> dict:
    d = clubes[["clave_club", "temporada"]].copy()
    d["e"] = lab
    d["anio"] = d["temporada"].str[:4].astype(int)
    sig = d.assign(anio=d["anio"] - 1).rename(columns={"e": "e_sig"})[["clave_club", "anio", "e_sig"]]
    m = d.merge(sig, on=["clave_club", "anio"])
    p = np.bincount(lab, minlength=C.N_ESTILOS) / len(lab)
    return {"parejas": int(len(m)), "mismo_estilo": float((m["e"] == m["e_sig"]).mean()),
            "por_azar": float((p ** 2).sum())}


def coherencia_plantillas(cj: Conjunto, red, sel: np.ndarray, lab_club: np.ndarray) -> dict:
    J = cj.jugadores
    pj, _ = predecir(red, cj.Xj)
    ej = pj.argmax(1)
    claves = cj.clubes["clave"].to_numpy()[sel]
    estilo = dict(zip(claves, lab_club))
    m = J["clave"].isin(set(claves)).to_numpy() & (J["min"] >= C.MIN_JUGADOR).to_numpy()
    d = pd.DataFrame({"clave": J.loc[m, "clave"], "min": J.loc[m, "min"], "e": ej[m]})
    d["mismo"] = d["e"].to_numpy() == d["clave"].map(estilo).to_numpy()
    cuota = d.groupby("clave").apply(lambda g: np.average(g["mismo"], weights=g["min"]), include_groups=False)
    pw = np.bincount(d["e"], weights=d["min"], minlength=C.N_ESTILOS)
    pw = pw / pw.sum()
    pc = np.bincount(lab_club, minlength=C.N_ESTILOS) / len(lab_club)
    return {"cuota_minutos_en_estilo_del_club": float(cuota.mean()), "por_azar": float((pw * pc).sum()),
            "reparto_jugadores": (pw).round(4).tolist()}


def evaluar(red, redes: list, ari: np.ndarray, cj: Conjunto, red_reserva=None, semilla: int = 7) -> dict:
    rng = np.random.default_rng(semilla)
    sel = cj.clubes["temporada"].isin(C.TEMPORADAS_ENTRENO).to_numpy()
    X = cj.Xc[sel]
    P, Z = predecir(red, X)
    lab = P.argmax(1)
    tam = np.bincount(lab, minlength=C.N_ESTILOS)
    pk = tam / tam.sum()
    ent = float(-(pk[pk > 0] * np.log(pk[pk > 0])).sum() / np.log(C.N_ESTILOS))
    out = {"clubes": int(sel.sum()), "tamanos": tam.tolist(), "tamano_min": int(tam.min()), "tamano_max": int(tam.max()),
           "entropia_reparto": ent, "salida_max_media": float(P.max(1).mean()),
           "clubes_con_salida_max_05": float((P.max(1) >= 0.5).mean())}
    # separación
    out["silueta_mapa"] = float(silhouette_score(Z, lab))
    out["silueta_rasgos"] = float(silhouette_score(X, lab))
    out["davies_bouldin_mapa"] = float(davies_bouldin_score(Z, lab))
    out["calinski_harabasz_mapa"] = float(calinski_harabasz_score(Z, lab))
    # estabilidad
    off = ari[~np.eye(len(ari), dtype=bool)]
    out["ari_semillas_medio"] = float(off.mean()) if len(off) else None
    out["ari_semillas_min"] = float(off.min()) if len(off) else None
    E = [predecir(r, X)[0].argmax(1) for r in redes]
    # estabilidad del MAPA: correlación entre las distancias club-club de cada pareja de semillas
    iu = np.triu_indices(len(X), 1)
    D = [np.sqrt(((Zs[:, None] - Zs[None]) ** 2).sum(-1))[iu] for Zs in (predecir(r, X)[1] for r in redes)]
    cm = [np.corrcoef(D[i], D[j])[0, 1] for i in range(len(D)) for j in range(i + 1, len(D))]
    out["estabilidad_mapa"] = float(np.mean(cm)) if cm else None
    ligas = cj.clubes.loc[sel, "liga"].to_numpy()
    out["nmi_estilo_liga"] = float(normalized_mutual_info_score(ligas, lab))
    out["pureza_liga_media"] = float(np.mean([pd.Series(ligas[lab == a]).value_counts(normalize=True).iloc[0]
                                              for a in range(C.N_ESTILOS) if (lab == a).any()]))
    nmi = [normalized_mutual_info_score(E[i], E[j]) for i in range(len(E)) for j in range(i + 1, len(E))]
    out["nmi_semillas_medio"] = float(np.mean(nmi)) if nmi else None
    Xb, origen = remuestrear(cj, 40, rng, list(cj.clubes.loc[sel, "clave"]))
    pos = {c: i for i, c in enumerate(np.flatnonzero(sel))}
    lab_b = predecir(red, Xb)[0].argmax(1)
    ref = lab[[pos[o] for o in origen]]
    out["robustez_reparto_minutos"] = float((lab_b == ref).mean())
    if red_reserva is not None:
        res = cj.clubes["temporada"].isin(["2024-25", "2025-26"]).to_numpy()
        a = predecir(red, cj.Xc[res])[0].argmax(1)
        b = predecir(red_reserva, cj.Xc[res])[0].argmax(1)
        out["ari_temporal_reserva"] = float(adjusted_rand_score(a, b))
    # fidelidad
    out["trustworthiness_k10"] = float(trustworthiness(X, Z, n_neighbors=10))
    out["continuidad_k10"] = float(trustworthiness(Z, X, n_neighbors=10))
    dx = np.sqrt(((X[:, None] - X[None]) ** 2).sum(-1))[iu]
    dz = np.sqrt(((Z[:, None] - Z[None]) ** 2).sum(-1))[iu]
    s = (dz @ dx) / (dx @ dx)
    out["estres_mapa"] = float(((dz - s * dx) ** 2).sum() / ((s * dx) ** 2).sum())
    out["spearman_distancias"] = float(spearmanr(dx, dz).statistic)
    with torch.no_grad():
        rec = red.reconstruir(red.codificar(_t(X))).numpy()
    r2 = 1 - ((rec - X) ** 2).mean(0) / X.var(0)
    out["r2_reconstruccion"] = {r.col: float(v) for r, v in zip(C.RASGOS, r2)}
    out["r2_medio"] = float(r2.mean())
    # diferenciación y uso
    out["diferenciacion"] = diferenciacion(X, lab, rng)
    out["replicabilidad"] = replicabilidad(X, lab, cj.clubes.loc[sel, "temporada"].to_numpy())
    out["persistencia"] = persistencia(cj.clubes[sel], lab)
    out["coherencia_plantillas"] = coherencia_plantillas(cj, red, sel, lab)
    return out


def referencia_kmedias(cj: Conjunto, semilla: int = 7) -> dict:
    sel = cj.clubes["temporada"].isin(C.TEMPORADAS_ENTRENO).to_numpy()
    X = cj.Xc[sel]
    lab = KMeans(C.N_ESTILOS, n_init=50, random_state=semilla).fit_predict(X)
    return {"silueta_rasgos": float(silhouette_score(X, lab)),
            "tamanos": np.bincount(lab, minlength=C.N_ESTILOS).tolist()}


# Métricas de la comparativa: (clave, nombre, mejor = "max" | "min" | None)
COMPARATIVA = [
    ("entropia_reparto", "Equilibrio del reparto (entropía, 1 = igual)", "max"),
    ("tamano_min", "Estilo más pequeño (clubes)", "max"),
    ("salida_max_media", "Confianza media de la neurona ganadora", "max"),
    ("silueta_mapa", "Silueta en el mapa 3D", "max"),
    ("silueta_rasgos", "Silueta en los 13 rasgos", "max"),
    ("davies_bouldin_mapa", "Davies-Bouldin en el mapa (menos es mejor)", "min"),
    ("ari_semillas_medio", "Estabilidad de los estilos entre semillas (ARI medio)", "max"),
    ("estabilidad_mapa", "Estabilidad del mapa entre semillas (r de distancias)", "max"),
    ("robustez_reparto_minutos", "Robustez al reparto de minutos", "max"),
    ("ari_temporal_reserva", "Reproducibilidad temporal (ARI, red sin 2024-26)", "max"),
    ("trustworthiness_k10", "Fidelidad del mapa: trustworthiness", "max"),
    ("continuidad_k10", "Fidelidad del mapa: continuidad", "max"),
    ("spearman_distancias", "Correlación distancias mapa / perfil", "max"),
    ("r2_medio", "R² medio de reconstrucción", "max"),
    ("nmi_estilo_liga", "Información compartida estilo-liga (NMI; alto = estilos ligados a una liga)", None),
]


def tabla_comparativa(ev: dict) -> pd.DataFrame:
    filas = []
    for clave, nombre, mejor in COMPARATIVA:
        v = {t: ev[t].get(clave) for t in ev}
        gana = None
        if mejor and all(x is not None for x in v.values()):
            gana = (max if mejor == "max" else min)(v, key=v.get)
        filas.append({"metrica": clave, "nombre": nombre, **{t: v[t] for t in ev}, "mejor": gana})
    for t in ev:
        d = ev[t]["diferenciacion"]
        ev[t]["_pares"] = f'{d["pares_distintos_holm_05"]}/{d["pares"]}'
    filas.append({"metrica": "pares_distintos", "nombre": "Parejas de estilos distintas (permutación, Holm 5 %)",
                  **{t: ev[t]["_pares"] for t in ev}, "mejor": None})
    filas.append({"metrica": "mahalanobis_min", "nombre": "Distancia de Mahalanobis mínima entre estilos",
                  **{t: ev[t]["diferenciacion"]["mahalanobis_min"] for t in ev},
                  "mejor": max(ev, key=lambda t: ev[t]["diferenciacion"]["mahalanobis_min"])})
    filas.append({"metrica": "replicabilidad", "nombre": "Replicabilidad de perfiles 2020-23 / 2023-26 (r medio)",
                  **{t: ev[t]["replicabilidad"]["correlacion_media"] for t in ev},
                  "mejor": max(ev, key=lambda t: ev[t]["replicabilidad"]["correlacion_media"] or -1)})
    for t in ev:
        ev[t].pop("_pares", None)
    return pd.DataFrame(filas)
