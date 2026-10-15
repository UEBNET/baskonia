"""Zonas de tiro a partir de las coordenadas del jugada a jugada (las 8 ligas).

Cada fuente usa su propio sistema de coordenadas:
  * EuroLeague / EuroCup: centímetros, x lateral, y a lo largo desde el aro (aro en 0, 0).
  * NBA / G League: décimas de pie, x lateral, y a lo largo desde el aro (aro en 0, 0).
  * ACB: milímetros, x a lo largo desde el aro, y lateral.
  * LBA / LNB: porcentaje de la pista completa (x a lo largo, 0-100 = 28 m; y lateral, 0-100 = 15 m).
  * BBL: unidades propias, media pista; se ajustan aro y escala.
En todas se ajustan (o se comprueban) la posición del aro y la escala con la línea de triple oficial:
el ajuste es el que mejor separa los tiros de 2 de los de 3 que anota la propia fuente. La tasa de
acierto de esa separación queda como medida de calidad de la calibración.

Zonas (distancia al aro en metros):
  aro       < 1,8 m              (bandejas, mates, tiros bajo el aro)
  corta     1,8 – 4,25 m         (pintura, flotadoras, ganchos)
  media     4,25 m – línea de 3  (media distancia)
  triple esquina / triple frontal (por la geometría de la línea)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize

# geometría de la línea de triple: (radio del arco, distancia lateral del tramo recto, hasta dónde llega
# el tramo recto medido desde el aro a lo largo de la pista), en metros
LINEA = {"fiba": (6.75, 6.60, 1.42), "nba": (7.24, 6.71, 2.73)}
ZONAS = ["aro", "corta", "media", "t3_esquina", "t3_frontal"]
R_ARO, R_CORTA = 1.8, 4.25


@dataclass
class Sistema:
    """Cómo pasar de (x, y) de la fuente a (lateral, longitudinal) en metros desde el aro."""
    liga: str
    regla: str                    # fiba | nba
    eje_largo: str                # "x" o "y": cuál de las dos coordenadas va a lo largo de la pista
    aro: tuple[float, float]      # posición del aro en unidades de la fuente (x, y)
    escala: tuple[float, float]   # metros por unidad (x, y)
    pista_completa: float | None = None   # longitud de la pista en unidades del eje largo (si hay dos aros)

    def metros(self, x, y):
        x = np.asarray(x, float); y = np.asarray(y, float)
        if self.pista_completa:            # dos canastas: se refleja la mitad lejana
            if self.eje_largo == "x":
                x = np.where(x > self.pista_completa / 2, self.pista_completa - x, x)
            else:
                y = np.where(y > self.pista_completa / 2, self.pista_completa - y, y)
        dx = (x - self.aro[0]) * self.escala[0]
        dy = (y - self.aro[1]) * self.escala[1]
        lat, lon = (dy, dx) if self.eje_largo == "x" else (dx, dy)
        return lat, lon


def es_triple(lat, lon, regla: str):
    r, lado, recto = LINEA[regla]
    d = np.hypot(lat, lon)
    return np.where(lon <= recto, np.abs(lat) >= lado, d >= r)


def zona(lat, lon, regla: str) -> np.ndarray:
    d = np.hypot(lat, lon)
    t3 = es_triple(lat, lon, regla)
    _, lado, recto = LINEA[regla]
    esquina = t3 & (lon <= recto + 0.3) & (np.abs(lat) >= lado - 0.3)
    out = np.where(d < R_ARO, "aro", np.where(d < R_CORTA, "corta", "media")).astype(object)
    out[t3] = np.where(esquina[t3], "t3_esquina", "t3_frontal")
    return out


# Sistemas de partida; los marcados con ajustar=True se afinan con los datos.
INICIAL = {
    "euroleague": (Sistema("euroleague", "fiba", "y", (0.0, 0.0), (0.01, 0.01)), False),
    "eurocup": (Sistema("eurocup", "fiba", "y", (0.0, 0.0), (0.01, 0.01)), False),
    "nba": (Sistema("nba", "nba", "y", (0.0, 0.0), (0.03048, 0.03048)), False),
    "gleague": (Sistema("gleague", "nba", "y", (0.0, 0.0), (0.03048, 0.03048)), False),
    "acb": (Sistema("acb", "fiba", "x", (0.0, 0.0), (0.001, 0.001)), True),
    "lba": (Sistema("lba", "fiba", "x", (5.625, 50.0), (0.28, 0.15), pista_completa=100.0), True),
    "lnb": (Sistema("lnb", "fiba", "x", (5.625, 50.0), (0.28, 0.15), pista_completa=100.0), True),
    "bbl": (Sistema("bbl", "fiba", "y", (140.0, 30.0), (0.0536, 0.0536)), True),
}


def _validas(t: pd.DataFrame) -> pd.DataFrame:
    s = t[t["tipo"].isin(["T2", "T3"]) & t["x"].notna() & t["y"].notna()]
    return s[~((s["x"] == 0) & (s["y"] == 0))]


def acierto(sis: Sistema, t: pd.DataFrame) -> float:
    s = _validas(t)
    lat, lon = sis.metros(s["x"].to_numpy(), s["y"].to_numpy())
    return float((es_triple(lat, lon, sis.regla) == (s["tipo"] == "T3").to_numpy()).mean())


def calibrar(liga: str, t: pd.DataFrame, muestra: int = 40000, semilla: int = 0) -> tuple[Sistema, float]:
    """Sistema de coordenadas de una liga y su acierto separando 2 y 3 (0-1)."""
    sis, ajustar = INICIAL[liga]
    s = _validas(t)
    if len(s) > muestra:
        s = s.sample(muestra, random_state=semilla)
    if not ajustar or s.empty:
        return sis, acierto(sis, s)
    x, y = s["x"].to_numpy(float), s["y"].to_numpy(float)
    lab = (s["tipo"] == "T3").to_numpy()

    def sistema(p):
        return Sistema(liga, sis.regla, sis.eje_largo, (p[0], p[1]), (p[2] * sis.escala[0], p[3] * sis.escala[1]),
                       sis.pista_completa)

    def perdida(p):
        # error suave: distancia (con signo) de cada tiro a la línea, en metros, a través de una sigmoide
        lat, lon = sistema(p).metros(x, y)
        r, lado, recto = LINEA[sis.regla]
        m = np.where(lon <= recto, np.abs(lat) - lado, np.hypot(lat, lon) - r)
        prob3 = 1 / (1 + np.exp(-m / 0.15))
        return float(np.mean(np.where(lab, 1 - prob3, prob3)))

    mejor = None
    for f in (0.8, 1.0, 1.25):
        p0 = np.array([sis.aro[0], sis.aro[1], f, f])
        r = minimize(perdida, p0, method="Nelder-Mead", options={"maxiter": 4000, "xatol": 1e-4, "fatol": 1e-6})
        if mejor is None or r.fun < mejor.fun:
            mejor = r
    out = sistema(mejor.x)
    return out, acierto(out, s)


def perfil_tiro(t: pd.DataFrame, sis: Sistema) -> pd.DataFrame:
    """Añade lat, lon (m), distancia y zona a cada tiro de campo con coordenadas."""
    s = _validas(t).copy()
    lat, lon = sis.metros(s["x"].to_numpy(), s["y"].to_numpy())
    s["lat_m"], s["lon_m"] = lat, lon
    s["dist_m"] = np.hypot(lat, lon)
    s["zona"] = zona(lat, lon, sis.regla)
    # la fuente manda en 2 o 3: un T2 con distancia de triple (pie sobre la línea) se queda como media
    s.loc[(s["tipo"] == "T2") & s["zona"].str.startswith("t3"), "zona"] = "media"
    s.loc[(s["tipo"] == "T3") & ~s["zona"].str.startswith("t3"), "zona"] = "t3_frontal"
    return s
