"""Red neuronal de estilos de juego: VaDE (Variational Deep Embedding; Jiang et al. 2017).

  * entrada: vector de estilo de 13 rasgos (transformado, estandarizado y sin nivel);
  * una capa latente de 3 neuronas, que ES el mapa 3D (clubes y jugadores en el mismo espacio);
  * una ÚLTIMA capa de 6 neuronas, una por estilo, cuyas salidas suman 1. El estilo asignado es la
    neurona con mayor salida.

Codificador 13-64-32 → (μ_z, log σ²_z) en 3D · decodificador 3-32-64-13 con varianza común ·
previa de mezcla de k gaussianas p(z) = Σ π_k N(μ_k, Σ_k) con covarianza completa. La capa de salida da
la probabilidad a posteriori de cada componente: γ_k = π_k N(z | μ_k, Σ_k) / Σ_j π_j N(z | μ_j, Σ_j).
Probabilística: cada club es una nube (μ_z, σ_z); cada estilo, un elipsoide con su forma y orientación.
(Iteraciones anteriores con una IDEC de contraste y con 12 y 8 estilos: data/modelos/estilos/historial/.)

Las activaciones ocultas son GELU (aproximación tanh), reproducible exactamente en el navegador.
"""
from __future__ import annotations

import math

import torch
import torch.nn as nn
import torch.nn.functional as F

LOG2PI = math.log(2 * math.pi)


def _mlp(dims: list[int], activa_final: bool = False) -> nn.Sequential:
    capas: list[nn.Module] = []
    for i, (a, b) in enumerate(zip(dims[:-1], dims[1:])):
        capas.append(nn.Linear(a, b))
        if i < len(dims) - 2 or activa_final:
            capas.append(nn.GELU(approximate="tanh"))
    return nn.Sequential(*capas)


class _Mapa(nn.Module):
    """Transformación rígida del latente al mapa mostrado: centrado, rotación de componentes
    principales (los ejes ordenados por varianza) y una escala única. No cambia las distancias
    relativas ni las asignaciones; sólo orienta el mapa."""

    def _init_mapa(self, d: int) -> None:
        self.register_buffer("mapa_centro", torch.zeros(d))
        self.register_buffer("mapa_rot", torch.eye(d))
        self.register_buffer("mapa_escala", torch.tensor(1.0))

    def codificar(self, x: torch.Tensor) -> torch.Tensor:  # pragma: no cover - lo define cada red
        raise NotImplementedError

    def mapa(self, x: torch.Tensor) -> torch.Tensor:
        return (self.codificar(x) - self.mapa_centro) @ self.mapa_rot * self.mapa_escala

    def a_mapa(self, z: torch.Tensor) -> torch.Tensor:
        return (z - self.mapa_centro) @ self.mapa_rot * self.mapa_escala


class RedVaDE(_Mapa):
    """VaDE con previa de mezcla de k gaussianas en el mapa. covarianza = "completa" (v2: elipsoides con
    orientación libre, matriz 3×3 por estilo) o "diag" (v1: ejes alineados). Los parámetros de la mezcla
    no se aprenden por gradiente: los reestima un paso M tras cada época (ver entrenar._paso_m)."""
    nombre = "VaDE"

    def __init__(self, d_in: int, ocultas=(64, 32), d_lat: int = 3, k: int = 12, covarianza: str = "diag"):
        super().__init__()
        self.config = {"d_in": d_in, "ocultas": list(ocultas), "d_lat": d_lat, "k": k, "covarianza": covarianza}
        self.covarianza = covarianza
        self.tronco = _mlp([d_in, *ocultas], activa_final=True)
        self.cab_mu = nn.Linear(ocultas[-1], d_lat)
        self.cab_logvar = nn.Linear(ocultas[-1], d_lat)
        self.dec = _mlp([d_lat, *reversed(ocultas), d_in])
        # varianza de reconstrucción COMÚN a los 13 rasgos: con una por rasgo la red puede declarar
        # «ruido» un rasgo difícil (p. ej. el ritmo) y dejar de representarlo en el mapa
        self.logvar_x = nn.Parameter(torch.zeros(1))
        self.pi_logits = nn.Parameter(torch.zeros(k))
        self.mu_c = nn.Parameter(torch.zeros(k, d_lat))
        if covarianza == "completa":
            self.chol_c = nn.Parameter(torch.eye(d_lat).repeat(k, 1, 1))   # factor de Cholesky de Σ_k
        else:
            self.logvar_c = nn.Parameter(torch.zeros(k, d_lat))
        self._init_mapa(d_lat)

    PARAMS_MEZCLA = ("pi_logits", "mu_c", "logvar_c", "chol_c")

    # --- codificador
    def posterior(self, x):
        h = self.tronco(x)
        return self.cab_mu(h), self.cab_logvar(h).clamp(-8.0, 4.0)

    def codificar(self, x):
        return self.cab_mu(self.tronco(x))

    def reconstruir(self, z):
        return self.dec(z)

    # --- previa de mezcla
    def _gmm(self):
        """(log π, μ, precisión Σ⁻¹ (k, d, d), log|Σ|), siempre sin gradiente."""
        log_pi = F.log_softmax(self.pi_logits, 0).detach()
        mu = self.mu_c.detach()
        if self.covarianza == "completa":
            L = torch.tril(self.chol_c.detach())
            eye = torch.eye(L.shape[-1]).expand_as(L)
            Linv = torch.linalg.solve_triangular(L, eye, upper=False)
            prec = Linv.transpose(-1, -2) @ Linv
            logdet = 2 * torch.log(torch.diagonal(L, dim1=-2, dim2=-1).abs()).sum(-1)
        else:
            lv = self.logvar_c.detach().clamp(-6.0, 4.0)
            prec = torch.diag_embed(torch.exp(-lv))
            logdet = lv.sum(-1)
        return log_pi, mu, prec, logdet

    def logits(self, z, separar: bool = True):
        log_pi, mu, prec, logdet = self._gmm()
        d = z[:, None, :] - mu[None]
        maha = torch.einsum("nki,kij,nkj->nk", d, prec, d)
        return log_pi[None] - 0.5 * (maha + logdet[None] + z.shape[1] * LOG2PI)

    def gamma(self, z, separar: bool = True):
        """Capa de salida: k neuronas, probabilidad a posteriori de cada componente."""
        return F.softmax(self.logits(z), dim=1)

    def salida(self, x):
        return self.gamma(self.codificar(x))

    def centros(self) -> torch.Tensor:
        return self.mu_c

    def covarianzas(self) -> torch.Tensor:
        if self.covarianza == "completa":
            L = torch.tril(self.chol_c.detach())
            return L @ L.transpose(-1, -2)
        return torch.diag_embed(self.logvar_c.detach().exp())

    def fijar_mezcla(self, mu: torch.Tensor, cov: torch.Tensor) -> None:
        with torch.no_grad():
            self.mu_c.copy_(mu)
            self.pi_logits.zero_()
            if self.covarianza == "completa":
                self.chol_c.copy_(torch.linalg.cholesky(cov))
            else:
                self.logvar_c.copy_(torch.log(torch.diagonal(cov, dim1=-2, dim2=-1)))

    def permutar(self, orden: torch.Tensor) -> None:
        with torch.no_grad():
            self.mu_c.copy_(self.mu_c[orden])
            self.pi_logits.copy_(self.pi_logits[orden])
            if self.covarianza == "completa":
                self.chol_c.copy_(self.chol_c[orden])
            else:
                self.logvar_c.copy_(self.logvar_c[orden])

    def perdida(self, x, beta: float = 1.0, separar: bool = True) -> torch.Tensor:
        """−ELBO por muestra (VaDE, una muestra de Monte Carlo con reparametrización). La mezcla entra
        como constante (la reestima el paso M)."""
        mu_z, lv_z = self.posterior(x)
        z = mu_z + torch.randn_like(mu_z) * (0.5 * lv_z).exp()
        lvx = self.logvar_x.clamp(-6.0, 3.0)
        rec = 0.5 * (((x - self.dec(z)) ** 2) / lvx.exp() + lvx + LOG2PI).sum(1)
        log_pi, mu_c, prec, logdet = self._gmm()
        g = F.softmax(self.logits(z), dim=1)
        d = mu_z[:, None, :] - mu_c[None]
        # E_q[−log p(z|c)] − constantes = ½ (log|Σ_c| + tr(Σ_c⁻¹ diag σ²_z) + (μ_z − μ_c)ᵀ Σ_c⁻¹ (μ_z − μ_c))
        traza = torch.einsum("kjj,nj->nk", prec, lv_z.exp())
        kl_z = 0.5 * (logdet[None] + traza + torch.einsum("nki,kij,nkj->nk", d, prec, d))
        kl = (g * kl_z).sum(1) - (g * (log_pi[None] - torch.log(g + 1e-10))).sum(1) - 0.5 * (1 + lv_z).sum(1)
        return rec + beta * kl


REDES = {"vade": RedVaDE}


def crear(tipo: str, config: dict) -> _Mapa:
    cfg = dict(config)
    return REDES[tipo](**cfg)
