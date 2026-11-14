"""F5 · Alternativa neuronal (encargo §9): red con embeddings de entidad (jugador y liga) que predice el vector de las
14 métricas de la temporada siguiente desde el historial, con su propia incertidumbre.

Entrada por persona y temporada objetivo t (todo lo anterior a t):
- última temporada observada: y (14, relativo a la media del rol en su liga, como en F4/F5), su varianza de muestreo
  v y la máscara de métricas observadas;
- media ponderada por precisión de todas las temporadas anteriores, por métrica, y nº de temporadas;
- edad (y si falta), años desde la última, cambio de liga y de rol hacia t, rol (one-hot);
- embedding del jugador (8) y de la liga de destino (4), aprendidos.
Salida: media μ (14) y log-varianza s (14) del nivel de t sin el muestreo. Pérdida: −log N(y_t; μ, e^s + c·v_t) en las
métricas observadas (c de la F4).

Se entrena con todas las transiciones anteriores al corte (temporadas objetivo < T) y se evalúa con el mismo examen y
las mismas funciones que la F4/F5. Criterio de adopción (encargo): mejora del CRPS con IC al 95 % de la diferencia
(bootstrap por persona) que no cruce 0 y sin degradar la calibración. Si no, se documenta y se descarta.
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

from bbnorm5.carrera import datos as CD
from bbnorm5.carrera import examen as EX
from bbnorm5.latente import examen as LX
from bbnorm5.latente import modelo as ML
from bbnorm5.medida import datos as DM

ROLES = ["E", "A", "I", "X"]


def _tabla(o: pd.DataFrame) -> pd.DataFrame:
    """Ancho: una fila por persona-temporada con y_m, v_m (NaN si no observada)."""
    w = o.pivot_table(index=["persona_v5", "anio"], columns="metrica", values=["y", "v"])
    w.columns = [f"{a}_{b}" for a, b in w.columns]
    b = o.drop_duplicates(["persona_v5", "anio"]).set_index(["persona_v5", "anio"])[["liga", "rol", "edad"]]
    return w.join(b).reset_index().sort_values(["persona_v5", "anio"])


def ejemplos(w: pd.DataFrame, anios_obj: list[int]) -> pd.DataFrame:
    """Un ejemplo por persona y temporada objetivo (con al menos una temporada previa)."""
    filas = []
    for anio in anios_obj:
        h = w[w["anio"] < anio]
        t = w[w["anio"] == anio]
        if t.empty or h.empty:
            continue
        ult = h.drop_duplicates("persona_v5", keep="last").set_index("persona_v5")
        n = h.groupby("persona_v5").size()
        med = {}
        for m in ML.METRICAS:
            p = 1 / h[f"v_{m}"]
            med[m] = (h[f"y_{m}"] * p).groupby(h["persona_v5"]).sum() / p.groupby(h["persona_v5"]).sum()
        t = t.set_index("persona_v5")
        t = t[t.index.isin(ult.index)]
        x = pd.DataFrame(index=t.index)
        for m in ML.METRICAS:
            x[f"ult_y_{m}"] = ult.loc[t.index, f"y_{m}"]
            x[f"ult_v_{m}"] = ult.loc[t.index, f"v_{m}"]
            x[f"med_y_{m}"] = med[m].reindex(t.index)
            x[f"obj_y_{m}"] = t[f"y_{m}"]
            x[f"obj_v_{m}"] = t[f"v_{m}"]
        x["n_temp"] = n.reindex(t.index)
        x["gap"] = anio - ult.loc[t.index, "anio"]
        x["cl"] = (t["liga"] != ult.loc[t.index, "liga"]).astype(float)
        x["cr"] = (t["rol"] != ult.loc[t.index, "rol"]).astype(float)
        x["edad"] = t["edad"]
        x["rol"], x["liga"], x["anio"] = t["rol"], t["liga"], anio
        filas.append(x.reset_index())
    return pd.concat(filas, ignore_index=True)


def _tensores(e: pd.DataFrame, jug: dict, lig: dict):
    import torch
    M = ML.METRICAS
    yl = e[[f"ult_y_{m}" for m in M]].to_numpy(float)
    vl = e[[f"ult_v_{m}" for m in M]].to_numpy(float)
    ym = e[[f"med_y_{m}" for m in M]].to_numpy(float)
    ml_ = np.isfinite(yl)
    mm = np.isfinite(ym)
    ed = e["edad"].to_numpy(float)
    num = np.c_[np.nan_to_num(yl), np.log(np.nan_to_num(vl, nan=1.0)), ml_, np.nan_to_num(ym), mm,
                np.log1p(e["n_temp"]), e["gap"], e["cl"], e["cr"], np.nan_to_num((ed - 26) / 4), np.isnan(ed),
                *(e["rol"] == r for r in ROLES)].astype(np.float32)
    y = e[[f"obj_y_{m}" for m in M]].to_numpy(float)
    v = e[[f"obj_v_{m}" for m in M]].to_numpy(float)
    mk = np.isfinite(y)
    ij = e["persona_v5"].map(jug).fillna(0).astype(int).to_numpy()
    il = e["liga"].map(lig).fillna(0).astype(int).to_numpy()
    T = lambda a, dt=torch.float32: torch.tensor(a, dtype=dt)
    return T(num), T(np.nan_to_num(y)), T(np.nan_to_num(v, nan=1.0)), T(mk), T(ij, torch.long), T(il, torch.long)


def entrenar(e: pd.DataFrame, c: np.ndarray, epocas: int, semilla: int):
    import torch
    import torch.nn as nn
    torch.manual_seed(semilla)
    jug = {p: i + 1 for i, p in enumerate(e["persona_v5"].unique())}
    lig = {l: i + 1 for i, l in enumerate(sorted(e["liga"].unique()))}
    X, Y, V, MK, IJ, IL = _tensores(e, jug, lig)
    Mm = len(ML.METRICAS)

    class Red(nn.Module):
        def __init__(self):
            super().__init__()
            self.ej = nn.Embedding(len(jug) + 1, 8)
            self.el = nn.Embedding(len(lig) + 1, 4)
            nn.init.normal_(self.ej.weight, std=0.01)
            self.f = nn.Sequential(nn.Linear(X.shape[1] + 12, 96), nn.ReLU(), nn.Linear(96, 96), nn.ReLU(),
                                   nn.Linear(96, 2 * Mm))

        def forward(self, x, ij, il):
            h = self.f(torch.cat([x, self.ej(ij), self.el(il)], 1))
            return h[:, :Mm], h[:, Mm:]
    red = Red()
    opt = torch.optim.Adam(red.parameters(), lr=2e-3, weight_decay=1e-5)
    ct = torch.tensor(c, dtype=torch.float32)
    n = len(X)
    for ep in range(epocas):
        perm = torch.randperm(n)
        for i in range(0, n, 512):
            b = perm[i:i + 512]
            mu, s = red(X[b], IJ[b], IL[b])
            var = torch.exp(s) + ct[None] * V[b]
            nll = 0.5 * (torch.log(var) + (Y[b] - mu) ** 2 / var) * MK[b]
            loss = nll.sum() / MK[b].sum() + 1e-4 * red.ej.weight[IJ[b]].pow(2).sum() / len(b)
            opt.zero_grad()
            loss.backward()
            opt.step()
    red.eval()
    return red, jug, lig


def ejecutar(cfg: dict) -> dict:
    import torch
    from bbnorm5.f5 import DIR
    o = CD.cargar()
    h = pd.read_csv(DM.DIR / "hiperparametros.csv")
    hp = CD._hiper_preferido(h)
    w = _tabla(o)
    fact = pd.read_parquet(DIR / "examen_casos.parquet")
    elegido = [m for m in fact["modelo"].unique() if m.endswith("_corr_r3") or (m.startswith("K") and "_corr" in m and not m.startswith("K0"))]
    nombre_fact = sorted(elegido)[0]
    casos = []
    for anio in cfg["examen"]["cortes"]:
        f4 = LX.f4_por_metrica(o[o["anio"] < anio], hp, anio)
        c = np.array([np.exp(f4[m]["th"]["log_c"]) for m in ML.METRICAS])
        tr = ejemplos(w, [a for a in sorted(w["anio"].unique()) if a < anio])
        red, jug, lig = entrenar(tr, c, cfg["neuronal"]["epocas"], cfg["semilla"] + anio)
        te = ejemplos(w, [anio])
        X, _, _, _, IJ, IL = _tensores(te, jug, lig)
        with torch.no_grad():
            mu, s = red(X, IJ, IL)
        mu, var = mu.numpy(), np.exp(s.numpy())
        for k, met in enumerate(ML.METRICAS):
            fam = DM.METRICAS[met][0]
            om = o[o["metrica"] == met]
            obj = EX.objetivo(om, om[om["anio"] < anio], anio, hp, met)
            pm = pd.DataFrame({"persona_v5": te["persona_v5"], "m_nivel": mu[:, k], "v_nivel": var[:, k],
                               "v_y_sin_muestreo": var[:, k], "temporadas_hist": te["n_temp"]})
            x = obj.merge(pm, on="persona_v5")
            rng = np.random.default_rng((cfg["semilla"] + zlib.crc32(f"{met}|{anio}|red".encode())) % 2 ** 32)
            casos.append(EX.evaluar(x, fam, "neuronal", rng).assign(metrica=met, anio=anio))
        print(f"  {anio}: red entrenada con {len(tr)} transiciones", flush=True)
    red_c = pd.concat(casos, ignore_index=True)
    red_c.to_parquet(DIR / "neuronal_casos.parquet")
    f = fact[fact["modelo"] == nombre_fact]
    k = ["metrica", "anio", "persona_v5"]
    m = f[k + ["crps", "pit", "cambio_liga"]].merge(red_c[k + ["crps", "pit"]], on=k, suffixes=("_fact", "_red"))
    rng = np.random.default_rng(cfg["semilla"])
    filas = []
    for met, g in list(m.groupby("metrica")) + [("todas", m.assign(crps_fact=m["crps_fact"] / m.groupby("metrica")["crps_fact"].transform("mean"),
                                                                     crps_red=m["crps_red"] / m.groupby("metrica")["crps_fact"].transform("mean")))]:
        d = (g["crps_red"] - g["crps_fact"]).to_numpy()
        per = g["persona_v5"].to_numpy()
        up, inv = np.unique(per, return_inverse=True)
        sums = np.bincount(inv, weights=d)
        cnt = np.bincount(inv)
        bs = []
        for _ in range(500):
            i = rng.integers(0, len(up), len(up))
            bs.append(sums[i].sum() / cnt[i].sum())
        lo, hi = np.quantile(bs, [0.025, 0.975])
        filas.append({"metrica": met, "casos": len(g), "crps_fact": g["crps_fact"].mean(), "crps_red": g["crps_red"].mean(),
                      "dif_red_menos_fact": d.mean(), "ic95_lo": lo, "ic95_hi": hi,
                      "cob80_fact": (np.abs(g["pit_fact"] - 0.5) <= 0.4).mean(),
                      "cob80_red": (np.abs(g["pit_red"] - 0.5) <= 0.4).mean()})
    r = pd.DataFrame(filas)
    t = r[r["metrica"] == "todas"].iloc[0]
    r["adoptar"] = bool(t["ic95_hi"] < 0 and abs(t["cob80_red"] - 0.8) <= abs(t["cob80_fact"] - 0.8) + 0.01)
    r.to_csv(DIR / "neuronal_frente_factorial.csv", index=False)
    return {"adoptar": bool(r["adoptar"].iloc[0]), "dif_rel": float(t["dif_red_menos_fact"]),
            "ic95": [float(t["ic95_lo"]), float(t["ic95_hi"])]}
