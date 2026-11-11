"""F4.1 · Series de carrera: una observación por persona, temporada y métrica, en la escala del enlace y relativa a la
media de su liga-temporada-rol (de la capa de medida F3).

Por cada persona y temporada se toma su **liga principal** (la de más minutos de temporada regular). La observación es
la tasa de esa temporada en la escala del enlace, menos la media del rol en esa liga-temporada (μ_rol de la F3):

    y = enlace(tasa observada) − μ_{liga, temporada, rol}       (posición relativa del jugador en su liga)
    v = varianza de muestreo de y (binomial con la sobredispersión de la F3, Poisson·(1+δ) o φ/N)

- binomial: ŷ = logit((K + 0,5)/(N + 1)); v = infl / (N p̃ (1 − p̃)), infl = 1 + ρ(Σn²/N − 1);
- Poisson:  ŷ = log((K + 0,5)/N);         v = (1 + δ) / (N λ̃);
- normal:   ŷ = K/N;                       v = φ / N;

donde p̃ y λ̃ son la media posterior de la F3 (encogida: no explota con pocos aciertos, a diferencia de la varianza
empírica 1/K + 1/(N − K)). La edad es el año de inicio de la temporada menos el año de nacimiento de la persona (F2).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import special

from bbnorm5 import config as C
from bbnorm5.medida import datos as DM

DIR = C.DIR_DATOS / "carrera"


def nacimiento_persona(temporadas: list[str]) -> pd.Series:
    """Año de nacimiento por persona_v5: mediana de la evidencia de sus nodos (como en F2, puentes inter)."""
    from bbnorm5.datos import entidades as N
    f = DIR / "nacimiento_persona.csv"
    if f.exists():
        return pd.read_csv(f, index_col=0)["anio_nacimiento"]
    per = pd.read_csv(C.DIR_DATOS / "limpios" / "entidades" / "personas_v5.csv", dtype=str)
    cw = pd.read_csv(C.RAIZ / "data" / "processed" / "player_id_crosswalk.csv", dtype=str)
    nac = N.evidencia_nacimiento(cw, N.filas_procesadas(temporadas))
    pm = per.set_index(["fuente_liga", "fuente_id"])["persona_v5"]
    s = pd.Series({pm.get(k): v for k, v in nac.items() if np.isfinite(v) and pm.get(k) is not None})
    s = s.groupby(level=0).median().rename("anio_nacimiento")
    DIR.mkdir(parents=True, exist_ok=True)
    s.to_csv(f)
    return s


def _hiper_preferido(hiper: pd.DataFrame) -> pd.DataFrame:
    h = hiper[hiper["datos"] == "temporada"]
    return h.sort_values("modelo").drop_duplicates(["liga", "temporada", "metrica"], keep="last")


def observaciones(d: pd.DataFrame, metrica: str, hiper: pd.DataFrame, post: pd.DataFrame,
                  nac: pd.Series, modo: str = "empirica") -> pd.DataFrame:
    """Una fila por persona y temporada (liga principal) con y, v, μ, dispersión, edad y exposición."""
    fam = DM.METRICAS[metrica][0]
    u = DM.unidad_metrica(d, metrica, None)
    mins = d.groupby(DM.CLAVE)["min"].sum().rename("min_temp")
    u = u.merge(mins, left_on=DM.CLAVE, right_index=True)
    # liga principal: la de más minutos de la persona en la temporada (sobre todas las ligas, no sólo con N > 0)
    todos = mins.reset_index().sort_values("min_temp").drop_duplicates(["persona_v5", "temporada"], keep="last")
    u = u.merge(todos[DM.CLAVE], on=DM.CLAVE)
    h = _hiper_preferido(hiper)
    h = h[h["metrica"] == metrica]
    mu = h.melt(id_vars=["liga", "temporada"], value_vars=[f"mu_{r}" for r in ("E", "A", "I", "X")],
                var_name="rol", value_name="mu")
    mu["rol"] = mu["rol"].str[3:]
    u = u.merge(mu.dropna(), on=["liga", "temporada", "rol"]).merge(
        h[["liga", "temporada", "disp", "sigma"] + [f"mu_{r}" for r in ("E", "A", "I", "X")]],
        on=["liga", "temporada"])     # medias de todos los roles de la liga-temporada (para el cambio de rol, F4)
    p = post[post["metrica"] == metrica][DM.CLAVE + ["media", "q10", "q50", "q90"]]
    u = u.merge(p, on=DM.CLAVE, how="left")
    K, N, N2g = (u[c].to_numpy(float) for c in ("K", "N", "N2g"))
    disp = u["disp"].to_numpy(float)
    t = u["media"].to_numpy(float)
    if fam == "binomial":
        infl = 1 + disp * np.maximum(N2g / N - 1, 0)
        y = special.logit((K + 0.5) / (N + 1))
        v = infl / (N * t * (1 - t))
    elif fam == "poisson":
        y = np.log((K + 0.5) / N)
        v = (1 + disp) / (N * t)
    else:
        y = K / N
        v = disp / N
    u["y_empirica"] = y - u["mu"].to_numpy(float)
    u["v_empirica"] = v
    # Modo por defecto «empirica» (lo de arriba). Alternativa evaluada y descartada (F4, `f4 --pasos experimento_obs`):
    # «posterior»: verosimilitud gaussiana de la temporada = posterior exacta de la F3 (rejilla) ÷ su prior
    # N(μ_rol, σ²), en la escala del enlace. Sin información (posterior ≈ prior) la precisión tiende a 0 y la temporada
    # no aporta, en lugar de aportar ruido (el logit empírico de 0 o 1 tapones depende de N, no del jugador).
    enl = {"binomial": lambda z: special.logit(np.clip(z, 1e-6, 1 - 1e-6)), "poisson": lambda z: np.log(np.maximum(z, 1e-9))}
    f = enl.get(fam, lambda z: z)
    m_post = f(u["q50"].to_numpy(float))
    s_post = (f(u["q90"].to_numpy(float)) - f(u["q10"].to_numpy(float))) / 2.5631
    s2_prior = u["sigma"].to_numpy(float) ** 2
    prec = 1 / np.maximum(s_post, 1e-6) ** 2 - 1 / s2_prior
    prec = np.maximum(prec, 1e-4)
    u["y_posterior"] = (m_post / s_post ** 2 - u["mu"].to_numpy(float) / s2_prior) / prec - u["mu"].to_numpy(float)
    u["v_posterior"] = 1 / prec
    u["y"], u["v"] = u[f"y_{modo}"], u[f"v_{modo}"]
    u["anio"] = u["temporada"].str[:4].astype(int)
    u["edad"] = u["anio"] - u["persona_v5"].map(nac)
    u["metrica"] = metrica
    u = u[np.isfinite(u["y"]) & np.isfinite(u["v"]) & (u["v"] > 0) & np.isfinite(u["y_empirica"])]
    return u.sort_values(["persona_v5", "anio"]).reset_index(drop=True)


def construir(temporadas: list[str], hiper: pd.DataFrame | None = None, post: pd.DataFrame | None = None,
              modo: str = "empirica") -> pd.DataFrame:
    d = DM.cargar()
    hiper = pd.read_csv(DM.DIR / "hiperparametros.csv") if hiper is None else hiper
    post = pd.read_parquet(DM.DIR / "posteriores.parquet") if post is None else post
    nac = nacimiento_persona(temporadas)
    o = pd.concat([observaciones(d, m, hiper, post, nac, modo) for m in DM.METRICAS], ignore_index=True)
    DIR.mkdir(parents=True, exist_ok=True)
    o.to_parquet(DIR / "observaciones.parquet")
    return o


def cargar() -> pd.DataFrame:
    return pd.read_parquet(DIR / "observaciones.parquet")
