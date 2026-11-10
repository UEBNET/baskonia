"""F1 §5.4 · ¿Prueban la v4.2 D1 (c < 1) y la sobrecobertura del intervalo publicado que los rangos de la v3.2 son
demasiado anchos? Prueba por simulación con intervalos EXACTAMENTE calibrados por construcción.

Se toman la estructura real (personas, temporadas, exposiciones) y los componentes de varianza REML de una métrica
(§5.1). Se simulan niveles θ_it = a_i + u_it y observaciones y_r = θ_it + ε_r, Var(ε_r) = σ²/n_r. Para cada
persona-temporada se calcula la posterior EXACTA del nivel con sólo esa temporada (como publica la v3.2: una estimación
por temporada):
    v_t = 1 / (1/(σ²_a + σ²_u) + W_t),   m_t = v_t · Σ_r w_r y_r     (W_t = Σ_r n_r/σ²)
Por construcción el intervalo m_t ± z·√v_t cubre θ_t el 80 %. Sobre (m_t, v_t) se aplican:
  (a) la prueba «nivel t ⊕ nivel t+1»: |m_{t+1} − m_t| ≤ z·√(v_t + v_{t+1});
  (b) el ajuste de la v4.2 D1 (bbequipo.v42.historial.ajustar: y = m, v = v), que estima τ² y c.
Si (a) da sobrecobertura y (b) da c < 1 con intervalos exactos, esos dos resultados no prueban que el intervalo
publicado sea ancho: son el efecto de usar medias a posteriori (contraídas y con la misma previa) como observaciones.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

Z80 = 1.2815515655446004


def simular(d: pd.DataFrame, s2a: float, s2u: float, s2: float, rng: np.random.Generator) -> pd.DataFrame:
    """d: filas reales (persona_id, anio, n). Devuelve una fila por persona-temporada con θ, m, v."""
    per = d["persona_id"].to_numpy()
    up, ip = np.unique(per, return_inverse=True)
    a = rng.normal(0, np.sqrt(s2a), len(up))[ip]
    clave = pd.Series(per.astype(str)) + "|" + d["anio"].astype(str).to_numpy()
    uk, ik = np.unique(clave.to_numpy(), return_inverse=True)
    u = rng.normal(0, np.sqrt(s2u), len(uk))[ik]
    n = d["n"].to_numpy(float)
    y = a + u + rng.normal(0, np.sqrt(s2 / n))
    w = n / s2
    x = pd.DataFrame({"k": ik, "persona_id": per, "anio": d["anio"].to_numpy(), "w": w, "wy": w * y,
                      "theta": a + u, "min": d["min"].to_numpy(float), "pos3": d["pos3"].to_numpy()})
    g = x.groupby("k").agg(persona_id=("persona_id", "first"), anio=("anio", "first"), W=("w", "sum"),
                           WY=("wy", "sum"), theta=("theta", "first"), min=("min", "sum"), pos3=("pos3", "first"))
    g["v"] = 1 / (1 / (s2a + s2u) + g["W"])
    g["y"] = g["v"] * g["WY"]
    return g.reset_index(drop=True)


def evaluar(g: pd.DataFrame, min_examen: float = 300.0) -> dict:
    from bbequipo.v42 import historial as H
    cob_theta = float(np.mean(np.abs(g["theta"] - g["y"]) <= Z80 * np.sqrt(g["v"])))
    o = g[["persona_id", "anio", "y", "v", "min", "pos3"]].sort_values(["persona_id", "anio"]).reset_index(drop=True)
    sig = o.groupby("persona_id").shift(-1)
    par = (sig["anio"] == o["anio"] + 1) & (o["min"] >= min_examen) & (sig["min"] >= min_examen)
    a, b = o[par], sig[par]
    cob_par = float(np.mean(np.abs(b["y"].to_numpy() - a["y"].to_numpy()) <= Z80 * np.sqrt(a["v"].to_numpy() + b["v"].to_numpy())))
    aj = H.ajustar(o)
    return {"cobertura_theta_80": cob_theta, "cobertura_t_mas_t1_80": cob_par, "n_pares": int(par.sum()),
            "d1_c": aj["c"], "d1_tau2": aj["tau2"]}


def ejecutar(cfg: dict, metricas: list[str], repeticiones: int = 3) -> pd.DataFrame:
    from bbnorm5 import config as C
    from bbnorm5.diagnostico import datos_f1
    comp = pd.read_csv(C.dir_fase(cfg) / "varianza" / "componentes.csv").set_index("metrica")
    t, _ = datos_f1.tabla(cfg)
    rng = np.random.default_rng(int(cfg["semilla"]))
    filas = []
    for m in metricas:
        d = datos_f1.metrica(t, m, cfg["datos"]["min_minutos"])
        s2 = float(comp.loc[m, "s2_ruido_tipico"])
        for r in range(repeticiones):
            g = simular(d, comp.loc[m, "s2a"], comp.loc[m, "s2u"], s2, rng)
            filas.append({"metrica": m, "repeticion": r, **evaluar(g)})
            print(f"  {m} rep {r}: {filas[-1]}", flush=True)
    return pd.DataFrame(filas)
