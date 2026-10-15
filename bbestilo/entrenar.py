"""Entrenamiento de la red VaDE (varias semillas), consenso y modelo final.

Muestras de entrenamiento (temporadas 2020-21 a 2025-26):
  * clubes reales: un vector por club-competición-temporada (escala de club);
  * plantillas remuestreadas: BOOTSTRAP_POR_CLUB por club, con el reparto de minutos perturbado
    (minutos × Gamma(4, 1/4)). Enseñan a la red que un estilo no depende de quién jugó 30 minutos
    más o menos, y multiplican por 25 una muestra de unos 1.000 clubes;
  * jugadores (auxiliares, peso 0,3; escala de jugador): sólo para que el codificador conozca la zona
    del espacio donde caen los jugadores. NO definen los estilos (el paso M de la mezcla sólo usa clubes).

Se entrenan 10 semillas; su partición de CONSENSO (co-asociación) define los estilos, y la semilla más
cercana al consenso se ajusta con la mezcla fijada en él. La dispersión entre semillas mide la estabilidad.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn.functional as F
from sklearn.metrics import adjusted_rand_score
from sklearn.mixture import GaussianMixture

from . import config as C
from .datos import Conjunto, remuestrear
from .redes import RedVaDE, crear

torch.set_num_threads(max(1, torch.get_num_threads()))

HIPER = {
    "vade": {"ocultas": [64, 32], "epocas_pre": 100, "epocas": 120, "lr": 1e-3, "lote": 512,
             "calentamiento": 30, "wd": 1e-5, "lambda_estres": float(len(C.COLS)), "amortiguacion": 0.5,
             "suelo_var": 0.02, "min_cuota": 0.01, "covarianza": "completa",
             "epocas_afinado": 40, "lr_afinado": 3e-4, "paso_m_afinado": False},
}


@dataclass
class Muestras:
    Xc: torch.Tensor      # clubes reales (entrenamiento)
    Xb: torch.Tensor      # plantillas remuestreadas
    Xj: torch.Tensor      # jugadores (auxiliares)
    idx_c: np.ndarray     # índices de los clubes reales en cj.clubes


def muestras(cj: Conjunto, temporadas: list[str], semilla: int) -> Muestras:
    rng = np.random.default_rng(semilla)
    sel = cj.clubes["temporada"].isin(temporadas).to_numpy()
    claves = list(cj.clubes.loc[sel, "clave"])
    Xb, _ = remuestrear(cj, C.BOOTSTRAP_POR_CLUB, rng, claves)
    js = (cj.jugadores["temporada"].isin(temporadas) & (cj.jugadores["min"] >= C.MIN_ESCALA_JUGADOR)).to_numpy()
    t = lambda a: torch.tensor(a, dtype=torch.float32)
    return Muestras(t(cj.Xc[sel]), t(Xb), t(cj.Xj[js]), np.flatnonzero(sel))


def _lotes(n: int, lote: int, gen: torch.Generator):
    perm = torch.randperm(n, generator=gen)
    for i in range(0, n, lote):
        yield perm[i:i + lote]


def estres(z: torch.Tensor, x: torch.Tensor) -> torch.Tensor:
    """Estrés de MDS métrico entre las distancias del mapa y las de los 13 rasgos estandarizados:
    Σ(d_z − d_x)² / Σ d_x². La escala es fija (1 unidad del mapa = 1 desviación típica del perfil),
    así que la distancia en el mapa 3D se lee en las mismas unidades que el perfil de estilo y el
    núcleo de la capa de salida trabaja siempre a la misma escala."""
    dz, dx = torch.pdist(z), torch.pdist(x)
    return ((dz - dx) ** 2).sum() / (dx * dx).sum().clamp_min(1e-9)


def _preentrenar(red, X, w, hp, gen):
    """Autoencoder determinista (codificador → decodificador): error cuadrático ponderado + estrés."""
    opt = torch.optim.Adam(red.parameters(), lr=hp["lr"], weight_decay=hp["wd"])
    for _ in range(hp["epocas_pre"]):
        for b in _lotes(len(X), hp["lote"], gen):
            z = red.codificar(X[b])
            rec = red.reconstruir(z)
            loss = (w[b] * ((rec - X[b]) ** 2).mean(1)).sum() / w[b].sum() + hp["lambda_estres"] * estres(z, X[b])
            opt.zero_grad()
            loss.backward()
            opt.step()


def _todo(M: Muestras):
    X = torch.cat([M.Xc, M.Xb, M.Xj])
    n_club = len(M.Xc) + len(M.Xb)
    es_club = torch.zeros(len(X), dtype=torch.bool)
    es_club[:n_club] = True
    w = torch.where(es_club, torch.tensor(1.0), torch.tensor(C.PESO_JUGADORES))
    return X, es_club, w


@torch.no_grad()
def _paso_m(red: RedVaDE, Z: torch.Tensor, hp: dict, primero: bool = False) -> torch.Tensor:
    """Paso M de la mezcla sobre los latentes de los clubes (reales y remuestreados): medias y
    covarianzas ponderadas por γ, con amortiguación, suelo de varianza y resiembra de componentes
    vacías. La previa de pesos es uniforme (π_k = 1/k): evita el colapso de VaDE en pocas
    componentes sin forzar que los estilos tengan el mismo tamaño."""
    g = red.gamma(Z)
    nk = g.sum(0)
    mu = (g.T @ Z) / nk[:, None].clamp_min(1e-9)
    d = Z[:, None, :] - mu[None]
    cov = torch.einsum("nk,nki,nkj->kij", g, d, d) / nk[:, None, None].clamp_min(1e-9)
    if red.covarianza != "completa":
        cov = torch.diag_embed(torch.diagonal(cov, dim1=-2, dim2=-1))
    eye = torch.eye(Z.shape[1])
    cov = cov + hp["suelo_var"] * Z.var(0).mean() * eye
    a = 0.0 if primero else hp["amortiguacion"]
    mu_n = a * red.mu_c + (1 - a) * mu
    cov_n = a * red.covarianzas() + (1 - a) * cov
    vacias = torch.nonzero(nk < hp["min_cuota"] * len(Z)).flatten()
    if len(vacias):
        peor = red.logits(Z).logsumexp(1).argsort()[: len(vacias)]   # los peor explicados
        mu_n[vacias] = Z[peor]
        cov_n[vacias] = torch.diag_embed(torch.diagonal(cov, dim1=-2, dim2=-1).median(0).values)
    red.fijar_mezcla(mu_n, cov_n)
    return nk


def _bucle_vade(red: RedVaDE, M: Muestras, hp: dict, gen, epocas: int, lr: float, registro=None,
                calentar: bool = True, primero_m: bool = True, paso_m: bool = True) -> None:
    X, es_club, w = _todo(M)
    params = [p for n, p in red.named_parameters() if n not in RedVaDE.PARAMS_MEZCLA]
    opt = torch.optim.Adam(params, lr=lr, weight_decay=hp["wd"])
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epocas)
    Xclub = X[es_club]
    for ep in range(epocas):
        beta = min(1.0, 0.1 + 0.9 * ep / max(1, hp["calentamiento"])) if calentar else 1.0
        tot = 0.0
        for b in _lotes(len(X), hp["lote"], gen):
            perd = red.perdida(X[b], beta)
            loss = (w[b] * perd).sum() / w[b].sum() + hp["lambda_estres"] * estres(red.codificar(X[b]), X[b])
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += loss.item()
        sched.step()
        if paso_m:
            nk = _paso_m(red, red.codificar(Xclub).detach(), hp, primero=(primero_m and ep == 0))
        else:
            with torch.no_grad():
                nk = red.gamma(red.codificar(Xclub)).sum(0)
        if registro is not None and ep % 10 == 0:
            registro.append({"epoca": ep, "perdida": tot, "cuota_min": float(nk.min() / nk.sum()),
                             "cuota_max": float(nk.max() / nk.sum())})


def entrenar_vade(M: Muestras, semilla: int, hp=None, registro=None) -> RedVaDE:
    hp = {**HIPER["vade"], **(hp or {})}
    torch.manual_seed(semilla)
    gen = torch.Generator().manual_seed(semilla)
    red = RedVaDE(M.Xc.shape[1], hp["ocultas"], C.D_MAPA, C.N_ESTILOS, hp["covarianza"])
    X, es_club, w = _todo(M)
    _preentrenar(red, X, w, hp, gen)
    with torch.no_grad():
        red.cab_logvar.bias.fill_(-4.0)
        red.cab_logvar.weight.mul_(0.01)
        Z = red.codificar(M.Xc).numpy()
        rec = red.reconstruir(red.codificar(X))
        red.logvar_x.copy_(torch.log(((rec - X) ** 2).mean() + 1e-3).reshape(1))
    tipo_cov = "full" if hp["covarianza"] == "completa" else "diag"
    gmm = GaussianMixture(C.N_ESTILOS, covariance_type=tipo_cov, n_init=5, reg_covar=1e-3, random_state=semilla).fit(Z)
    cov = gmm.covariances_ if tipo_cov == "full" else np.stack([np.diag(c) for c in gmm.covariances_])
    red.fijar_mezcla(torch.tensor(gmm.means_, dtype=torch.float32), torch.tensor(cov, dtype=torch.float32))
    _bucle_vade(red, M, hp, gen, hp["epocas"], hp["lr"], registro)
    return red


def consenso(etiquetas_semillas: list[np.ndarray], k: int) -> np.ndarray:
    """Partición de consenso: matriz de co-asociación (fracción de semillas que ponen juntos a dos
    clubes) y agrupamiento jerárquico de enlace medio sobre 1 − co-asociación, cortado en k grupos."""
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform
    E = np.stack(etiquetas_semillas)
    co = (E[:, :, None] == E[:, None, :]).mean(0)
    D = squareform(1.0 - co, checks=False)
    return fcluster(linkage(D, method="average"), k, criterion="maxclust") - 1


def afinar_vade(red: RedVaDE, M: Muestras, etiq: np.ndarray, semilla: int, hp=None, registro=None) -> RedVaDE:
    """Ajuste fino de la red base desde la partición de consenso: la mezcla se fija en la media y la
    covarianza de cada grupo de consenso en el mapa de esa red y sólo se entrenan el codificador y el
    decodificador (β = 1), de modo que el mapa se adapta a los estilos acordados por las semillas. Con el
    paso M activo durante el ajuste, el modelo se alejaba del consenso (ARI 0,57 frente a 0,69)."""
    hp = {**HIPER["vade"], **(hp or {})}
    torch.manual_seed(semilla + 1000)
    gen = torch.Generator().manual_seed(semilla + 1000)
    with torch.no_grad():
        Z = red.codificar(M.Xc)
        glob = torch.cov(Z.T) + 1e-3 * torch.eye(Z.shape[1])
        mus, covs = [], []
        for k in range(C.N_ESTILOS):
            Zk = Z[torch.tensor(etiq == k)]
            mus.append(Zk.mean(0) if len(Zk) else Z.mean(0))
            covs.append(torch.cov(Zk.T) + hp["suelo_var"] * Z.var(0).mean() * torch.eye(Z.shape[1]) if len(Zk) >= 5 else glob)
        red.fijar_mezcla(torch.stack(mus), torch.stack(covs))
    red.train()
    _bucle_vade(red, M, hp, gen, hp["epocas_afinado"], hp["lr_afinado"], registro, calentar=False, primero_m=False,
                paso_m=hp.get("paso_m_afinado", True))
    red.eval()
    return red


ENTRENADORES = {"vade": entrenar_vade}


@torch.no_grad()
def orientar(red, Xc: torch.Tensor) -> None:
    """Fija el mapa (centro, ejes principales con signo determinista, escala) y ordena los estilos
    por su posición en el mapa (E01 = el más negativo en el eje 1)."""
    Z = red.codificar(Xc)
    centro = Z.mean(0)
    Zc = Z - centro
    _, S, Vt = torch.linalg.svd(Zc, full_matrices=False)
    rot = Vt.T.clone()
    coords = Zc @ rot
    # signo: la correlación más fuerte de cada eje con un rasgo de entrada es positiva
    Xs = (Xc - Xc.mean(0)) / Xc.std(0)
    cs = (coords - coords.mean(0)) / coords.std(0)
    corr = (cs.T @ Xs) / len(Xc)
    for j in range(rot.shape[1]):
        k = corr[j].abs().argmax()
        if corr[j, k] < 0:
            rot[:, j] = -rot[:, j]
    escala = 1.0 / torch.sqrt((coords ** 2).sum(1).mean() / coords.shape[1])
    red.mapa_centro.copy_(centro)
    red.mapa_rot.copy_(rot)
    red.mapa_escala.copy_(escala)
    m = red.a_mapa(red.centros())
    orden = torch.tensor(sorted(range(len(m)), key=lambda i: (round(float(m[i, 0]), 6), float(m[i, 1]))))
    red.permutar(orden)


@torch.no_grad()
def etiquetas(red, X: torch.Tensor) -> np.ndarray:
    return red.salida(X).argmax(1).numpy()


def entrenar_semillas(tipo: str, cj: Conjunto, semillas=None, temporadas=None, log=print) -> dict:
    """Entrena la red con varias semillas y construye el modelo final:
    partición de CONSENSO de las semillas (co-asociación), la semilla más cercana a ese consenso
    como base y un ajuste fino desde el consenso; el modelo final resume el acuerdo de todas las redes."""
    semillas = semillas or C.SEMILLAS
    temporadas = temporadas or C.TEMPORADAS_ENTRENO
    redes, regs, Ms = [], [], []
    for s in semillas:
        M = muestras(cj, temporadas, s)
        reg: list = []
        red = ENTRENADORES[tipo](M, s, registro=reg)
        red.eval()
        orientar(red, M.Xc)
        redes.append(red)
        regs.append(reg)
        Ms.append(M)
        tam = np.bincount(etiquetas(red, M.Xc), minlength=C.N_ESTILOS)
        log(f"  {tipo} semilla {s}: tamaños {tam.tolist()}")
    Xc = torch.tensor(cj.Xc[cj.clubes["temporada"].isin(temporadas).to_numpy()], dtype=torch.float32)
    E = [etiquetas(r, Xc) for r in redes]
    n = len(redes)
    ari = np.ones((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            ari[i, j] = ari[j, i] = adjusted_rand_score(E[i], E[j])
    out = {"redes": redes, "ari": ari, "regs": regs, "semillas": semillas}
    if tipo == "vade" and n > 1:
        cons = consenso(E, C.N_ESTILOS)
        a_c = [adjusted_rand_score(e, cons) for e in E]
        i = int(np.argmax(a_c))
        log(f"  consenso: ARI de cada semilla con el consenso {np.round(a_c, 3).tolist()}; base = semilla {semillas[i]}")
        base = crear(tipo, redes[i].config)
        base.load_state_dict(redes[i].state_dict())
        reg: list = []
        final = afinar_vade(base, Ms[i], cons, semillas[i], registro=reg)
        orientar(final, Ms[i].Xc)
        a_f = adjusted_rand_score(etiquetas(final, Xc), cons)
        log(f"  afinado desde el consenso: ARI con el consenso {a_f:.3f}")
        out.update({"final": final, "indice_base": i, "registro_final": regs[i] + reg, "etiquetas_consenso": cons,
                    "consenso": {"ari_semillas_consenso": a_c, "ari_final_consenso": a_f,
                                 "ari_final_semillas": [adjusted_rand_score(etiquetas(final, Xc), e) for e in E]}})
    else:
        i = int(np.argmax((ari.sum(1) - 1) / max(1, n - 1)))
        out.update({"final": redes[i], "indice_base": i, "registro_final": regs[i]})
    return out


def guardar(red, tipo: str, semilla: int, ruta) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"tipo": tipo, "config": red.config, "semilla": semilla, "estado": red.state_dict()}, ruta)


def cargar(ruta):
    d = torch.load(ruta, weights_only=False)
    red = crear(d["tipo"], d["config"])
    red.load_state_dict(d["estado"])
    red.eval()
    return red, d


def exportar_pesos(red, tipo: str) -> dict:
    """Pesos en JSON para ejecutar la red en el navegador (mapa 3D y simulación de fichajes)."""
    sd = {k: v.detach().cpu().numpy().round(6).tolist() for k, v in red.state_dict().items()}
    capas = [(sd[f"tronco.{i}.weight"], sd[f"tronco.{i}.bias"]) for i in (0, 2)]
    capas.append((sd["cab_mu.weight"], sd["cab_mu.bias"]))
    log_pi, mu, prec, logdet = red._gmm()
    salida = {"log_pi": log_pi.numpy().round(6).tolist(), "mu": mu.numpy().round(6).tolist(),
              "prec": prec.numpy().round(6).tolist(), "logdet": logdet.numpy().round(6).tolist(),
              "cov": red.covarianzas().numpy().round(6).tolist()}
    return {"tipo": tipo, "activacion": "gelu_tanh",
            "capas": [{"W": W, "b": b} for W, b in capas],
            "salida": salida,
            "mapa": {"centro": sd["mapa_centro"], "rot": sd["mapa_rot"], "escala": float(sd["mapa_escala"])}}


def resumen_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1)
