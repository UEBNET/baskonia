"""Las dos redes neuronales de estilos de juego.

Las dos comparten el mismo contrato:
  * entrada: vector de estilo de 13 rasgos (transformado y estandarizado);
  * una capa latente de 3 neuronas, que ES el mapa 3D (clubes y jugadores en el mismo espacio);
  * una ÚLTIMA capa de 12 neuronas, una por estilo, cuyas salidas suman 1. El estilo asignado es la
    neurona con mayor salida.

Red 1 · IDEC (Improved Deep Embedded Clustering; Xie et al. 2016, Guo et al. 2017)
    codificador 13-64-32-3 · decodificador 3-32-64-13 · capa de agrupamiento con 12 centroides
    en el mapa y núcleo t de Student: q_k ∝ (1 + ‖z − μ_k‖²/α)^(−(α+1)/2).
    Determinista: cada club es un punto; un estilo es una región alrededor de su centroide.

Red 2 · VaDE (Variational Deep Embedding; Jiang et al. 2017)
    codificador 13-64-32 → (μ_z, log σ²_z) en 3D · decodificador 3-32-64-13 con varianza común ·
    previa de mezcla de 12 gaussianas p(z) = Σ π_k N(μ_k, diag σ²_k). La capa de salida da la
    probabilidad a posteriori de cada componente: γ_k = π_k N(z | μ_k, σ²_k) / Σ_j π_j N(z | μ_j, σ²_j).
    Probabilística: cada club es una nube (μ_z, σ_z); cada estilo, un elipsoide con su propia forma.

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


class RedIDEC(_Mapa):
    nombre = "IDEC"

    def __init__(self, d_in: int, ocultas=(64, 32), d_lat: int = 3, k: int = 12, alpha: float = 1.0):
        super().__init__()
        self.config = {"d_in": d_in, "ocultas": list(ocultas), "d_lat": d_lat, "k": k, "alpha": alpha}
        self.enc = _mlp([d_in, *ocultas, d_lat])
        self.dec = _mlp([d_lat, *reversed(ocultas), d_in])
        self.centroides = nn.Parameter(torch.zeros(k, d_lat))
        self.alpha = alpha
        self._init_mapa(d_lat)

    def codificar(self, x):
        return self.enc(x)

    def reconstruir(self, z):
        return self.dec(z)

    def logits(self, z):
        d2 = ((z[:, None, :] - self.centroides[None]) ** 2).sum(-1)
        return -(self.alpha + 1) / 2 * torch.log1p(d2 / self.alpha)

    def q(self, z):
        """Capa de salida: 12 neuronas, núcleo t de Student normalizado."""
        return F.softmax(self.logits(z), dim=1)

    def salida(self, x):
        return self.q(self.codificar(x))

    def centros(self) -> torch.Tensor:
        return self.centroides

    def permutar(self, orden: torch.Tensor) -> None:
        with torch.no_grad():
            self.centroides.copy_(self.centroides[orden])

    @staticmethod
    def objetivo(q: torch.Tensor) -> torch.Tensor:
        """Distribución objetivo P de DEC: refuerza las asignaciones seguras y normaliza por tamaño."""
        w = q ** 2 / q.sum(0, keepdim=True)
        return w / w.sum(1, keepdim=True)


class RedVaDE(_Mapa):
    nombre = "VaDE"

    def __init__(self, d_in: int, ocultas=(64, 32), d_lat: int = 3, k: int = 12):
        super().__init__()
        self.config = {"d_in": d_in, "ocultas": list(ocultas), "d_lat": d_lat, "k": k}
        self.tronco = _mlp([d_in, *ocultas], activa_final=True)
        self.cab_mu = nn.Linear(ocultas[-1], d_lat)
        self.cab_logvar = nn.Linear(ocultas[-1], d_lat)
        self.dec = _mlp([d_lat, *reversed(ocultas), d_in])
        # varianza de reconstrucción COMÚN a los 13 rasgos: con una por rasgo la red puede declarar
        # «ruido» un rasgo difícil (p. ej. el ritmo) y dejar de representarlo en el mapa
        self.logvar_x = nn.Parameter(torch.zeros(1))
        self.pi_logits = nn.Parameter(torch.zeros(k))
        self.mu_c = nn.Parameter(torch.zeros(k, d_lat))
        self.logvar_c = nn.Parameter(torch.zeros(k, d_lat))
        self._init_mapa(d_lat)

    # --- codificador
    def posterior(self, x):
        h = self.tronco(x)
        return self.cab_mu(h), self.cab_logvar(h).clamp(-8.0, 4.0)

    def codificar(self, x):
        return self.cab_mu(self.tronco(x))

    def reconstruir(self, z):
        return self.dec(z)

    # --- previa de mezcla
    def _gmm(self, separar: bool = False):
        log_pi = F.log_softmax(self.pi_logits, 0)
        mu, lv = self.mu_c, self.logvar_c.clamp(-6.0, 4.0)
        if separar:
            return log_pi.detach(), mu.detach(), lv.detach()
        return log_pi, mu, lv

    def logits(self, z, separar: bool = False):
        log_pi, mu, lv = self._gmm(separar)
        return log_pi[None] - 0.5 * (((z[:, None, :] - mu[None]) ** 2) / lv.exp()[None] + lv[None] + LOG2PI).sum(-1)

    def gamma(self, z, separar: bool = False):
        """Capa de salida: 12 neuronas, probabilidad a posteriori de cada componente."""
        return F.softmax(self.logits(z, separar), dim=1)

    def salida(self, x):
        return self.gamma(self.codificar(x))

    def centros(self) -> torch.Tensor:
        return self.mu_c

    def permutar(self, orden: torch.Tensor) -> None:
        with torch.no_grad():
            self.mu_c.copy_(self.mu_c[orden])
            self.logvar_c.copy_(self.logvar_c[orden])
            self.pi_logits.copy_(self.pi_logits[orden])

    def perdida(self, x, beta: float = 1.0, separar: bool = False) -> torch.Tensor:
        """−ELBO por muestra (VaDE, una muestra de Monte Carlo con reparametrización).
        separar=True: la previa de mezcla no recibe gradiente (muestras auxiliares de jugadores)."""
        mu_z, lv_z = self.posterior(x)
        z = mu_z + torch.randn_like(mu_z) * (0.5 * lv_z).exp()
        lvx = self.logvar_x.clamp(-6.0, 3.0)
        rec = 0.5 * (((x - self.dec(z)) ** 2) / lvx.exp() + lvx + LOG2PI).sum(1)
        log_pi, mu_c, lv_c = self._gmm(separar)
        g = F.softmax(self.logits(z, separar), dim=1)
        kl_z = 0.5 * (lv_c[None] + (lv_z[:, None, :] - lv_c[None]).exp()
                      + ((mu_z[:, None, :] - mu_c[None]) ** 2) / lv_c.exp()[None]).sum(-1)
        kl = (g * kl_z).sum(1) - (g * (log_pi[None] - torch.log(g + 1e-10))).sum(1) - 0.5 * (1 + lv_z).sum(1)
        return rec + beta * kl


REDES = {"idec": RedIDEC, "vade": RedVaDE}


def crear(tipo: str, config: dict) -> _Mapa:
    cfg = dict(config)
    return REDES[tipo](**cfg)
