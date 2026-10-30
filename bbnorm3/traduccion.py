"""Niveles por métrica, matriz de traducción cruzada T_m(a → b) y consistencia de ciclo.

Nivel de la competición c en la métrica m, en la vara de una competición de referencia R (por defecto la del gauge:
la media ponderada de todas): dónde caería el jugador medio de c si jugara en R, en desviaciones típicas de
capacidad de los jugadores de R,
    δ_{c,m} = media_p [ g_m((μ_c − μ_R)/s_R, R, p) − g_m(0, R, p) ] / τ_{R,m}
Depende sólo de μ_c − μ_R, así que es invariante al gauge. Su incertidumbre usa el jacobiano J = ∂δ/∂μ_c y la
covarianza conjunta de los μ:  Var(δ_c) = J (Σ_cc + Σ_RR − 2Σ_cR) Jᵀ.
Traducción cruzada:  T_m(a → b) = δ_{a,m} − δ_{b,m}  (cuánto mejora —en DT de capacidad de R— la posición relativa
de un jugador medio de a al pasar a b; > 0 si b es más débil en m), con
    Var = J_a Σ̃_aa J_aᵀ + J_b Σ̃_bb J_bᵀ − 2 J_a Σ̃_ab J_bᵀ,   Σ̃_xy = Σ_xy − Σ_xR − Σ_Ry + Σ_RR
(es decir, Σ_aa + Σ_bb − 2Σ_ab en las coordenadas del latente, sin sumar varianzas marginales).
"""
from __future__ import annotations

import numpy as np
import torch

from .datos import METRICAS, POSICIONES, Datos
from .modelo import CVAE


def _grupos_de(D: Datos, comp: str) -> list[int]:
    return [D.grupos.index(f"{comp}|{p}") for p in POSICIONES if f"{comp}|{p}" in D.grupos]


@torch.no_grad()
def _tau_ref(modelo: CVAE, post, D: Datos, comp_ref: int) -> np.ndarray:
    """DT de capacidad (decodificada, sin ruido) de los jugadores de la competición de referencia, por métrica."""
    filas = np.where(D.idx["comp"] == comp_ref)[0]
    u = post.media[D.idx["ps"][filas]]
    mu = post.media[post.nPS + comp_ref]
    l = D.comp_liga[comp_ref]
    r = torch.as_tensor((u - mu) / post.s[l], dtype=torch.float32)
    y = modelo.decodificar(r, torch.as_tensor(np.full(len(filas), l)), torch.as_tensor(D.idx["grupo"][filas]))
    y = y.numpy() - modelo.bG.detach().numpy()[D.idx["grupo"][filas]]
    return np.maximum(y.std(0), 1e-3)


def niveles(modelo: CVAE, post, D: Datos, comp_ref: int, mu_lat: np.ndarray | None = None):
    """δ (nC × 33) y jacobianos J (nC × 33 × K) respecto de μ_c, en la vara de comp_ref."""
    mu_lat = post.media[post.nPS:post.nPS + post.nC] if mu_lat is None else mu_lat
    l = int(D.comp_liga[comp_ref])
    grupos = _grupos_de(D, D.comps[comp_ref])
    tau = _tau_ref(modelo, post, D, comp_ref)
    nC, K = mu_lat.shape
    x = torch.as_tensor((mu_lat - mu_lat[comp_ref]) / post.s[l], dtype=torch.float32).requires_grad_(True)
    out = torch.zeros(nC, len(METRICAS))
    for g in grupos:
        lt = torch.full((nC,), l, dtype=torch.long)
        gt = torch.full((nC,), g, dtype=torch.long)
        out = out + (modelo.decodificar(x, lt, gt) - modelo.decodificar(torch.zeros_like(x), lt, gt)) / len(grupos)
    out = out / torch.as_tensor(tau, dtype=torch.float32)
    J = np.zeros((nC, len(METRICAS), K))
    for m in range(len(METRICAS)):
        gr, = torch.autograd.grad(out[:, m].sum(), x, retain_graph=True)
        J[:, m, :] = gr.numpy() / post.s[l]
    return out.detach().numpy().astype(float), J


def covarianza_niveles(J: np.ndarray, cov_mu: np.ndarray, comp_ref: int, a: int, b: int) -> np.ndarray:
    """Cov(δ_a,m, δ_b,m) por métrica (33,), con Σ̃_ab = Σ_ab − Σ_aR − Σ_Rb + Σ_RR en cada dimensión latente."""
    R = comp_ref
    st = cov_mu[:, a, b] - cov_mu[:, a, R] - cov_mu[:, R, b] + cov_mu[:, R, R]     # (K,) — dims independientes
    return np.einsum("mk,k,mk->m", J[a], st, J[b])


def traduccion_cruzada(delta: np.ndarray, J: np.ndarray, cov_mu: np.ndarray, comp_ref: int, pares) -> list[dict]:
    from scipy.stats import norm
    z80 = norm.ppf(0.9)
    out = []
    for a, b in pares:
        media = delta[a] - delta[b]
        var = (covarianza_niveles(J, cov_mu, comp_ref, a, a) + covarianza_niveles(J, cov_mu, comp_ref, b, b)
               - 2 * covarianza_niveles(J, cov_mu, comp_ref, a, b))
        sd = np.sqrt(np.maximum(var, 0))
        var_marg = covarianza_niveles(J, cov_mu, comp_ref, a, a) + covarianza_niveles(J, cov_mu, comp_ref, b, b)
        out.append({"a": a, "b": b, "media": media, "sd": sd, "lo80": media - z80 * sd, "hi80": media + z80 * sd,
                    "sd_marginal_sumada": np.sqrt(np.maximum(var_marg, 0))})
    return out


@torch.no_grad()
def residuo_ciclo(modelo: CVAE, post, D: Datos, triangulo: tuple[int, int, int], n: int = 400, semilla: int = 0) -> np.ndarray:
    """Residuo de ciclo a → b → c → a por métrica (DT de la escala de trabajo) para jugadores de a.

    Cada paso traduce DECODIFICANDO en la competición siguiente y volviendo a CODIFICAR desde las métricas
    (como haría un usuario que encadena traducciones): r_a → ŷ_b → r̂_b → ŷ_c → r̂_c → ŷ_a, y se compara ŷ_a con la
    decodificación directa en a. Con un codificador que invierte bien al decodificador, el residuo es ≈ 0."""
    rng = np.random.default_rng(semilla)
    a, b, c = triangulo
    filas = np.where(D.idx["comp"] == a)[0]
    filas = rng.choice(filas, min(n, len(filas)), replace=False)
    u = post.media[D.idx["ps"][filas]]
    pos = D.idx["pos"][filas]

    def grupo_en(comp, p):
        nombre = f"{D.comps[comp]}|{POSICIONES[p]}"
        return D.grupos.index(nombre) if nombre in D.grupos else _grupos_de(D, D.comps[comp])[0]

    def dec(uu, comp):
        l = D.comp_liga[comp]
        r = torch.as_tensor((uu - post.media[post.nPS + comp]) / post.s[l], dtype=torch.float32)
        g = torch.as_tensor([grupo_en(comp, p) for p in pos])
        return modelo.decodificar(r, torch.full((len(uu),), int(l)), g)

    def enc(y, comp):
        l = D.comp_liga[comp]
        ones = torch.ones_like(y)
        m, _ = modelo.codificar(y, ones, torch.full_like(y, 0.02), torch.full((len(y),), int(l)),
                                torch.as_tensor(pos), torch.full((len(y),), float(np.log(1000) / 7)))
        return post.media[post.nPS + comp] + post.s[l] * m.numpy()

    directo = dec(u, a).numpy()
    ub = enc(dec(u, b), b)
    uc = enc(dec(ub, c), c)
    vuelta = dec(uc, a).numpy()
    return (vuelta - directo).mean(0)
