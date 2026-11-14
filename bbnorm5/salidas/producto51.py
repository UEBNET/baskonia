"""v5.1 F6 · Producto para el artifact: la versión combinada como superposición de la v3.2 y su vara.

1. **Componente v5 por temporada** (`data/v5_1/producto/superposicion/<t>.csv.gz`). Una fila por (liga, player_id,
   team_id) con v5 en alguna métrica: `<m>_v5`, `<m>_v5_lo` y `<m>_v5_hi` de las 25 métricas del esquema v1 que la
   v5.1 cambia (equivalente EuroLeague 2025-26 de la v5, F9 y F1 de la v5.1).

   **La combinación se hace en producción** (`aplicar`), sobre la v3.2 que esté publicada en cada momento: centro e
   intervalo = w·v5 + (1 − w)·v3.2 donde están las dos, la v5 donde sólo está ella, la v3.2 en el resto; percentil
   recalculado entre los jugadores de la EuroLeague de su posición (como `formato_v32.combinar`). Motivo: la v3.2 de
   producción se reajustó con la Liga U (21 ligas) y la recalibración mensual la cambia en 2026-27; combinar con una
   copia fija mezclaría versiones. Las filas sin v5 (Liga U, jugadores nuevos posteriores) siguen con la v3.2;
   `fuente_norm` dice cuál es cuál («V5.1» o «V3.2») y las máscaras `v51_comb` / `v51_solo` (bits en el orden de
   `ORDEN`) qué métricas son combinadas o sólo v5.

2. **Vara** (`data/v5_1/producto/vara_v51.json`). Para expresar los equivalentes EuroLeague 2025-26 en la liga del club
   como hace `vara.json` con la v3.2, pero con la traducción de la v5. En la escala del enlace de cada métrica
   (logit, log o identidad):

       η_d = η_EL − Δ_d,     Δ_d = E[λ(EuroLeague, 2025-26) − λ(d, 2025-26)]

   Cada cola del intervalo del 80 %, como `bbnorm3.destino.desde_el`: sd_EL = |η_EL − η(x)|/z₈₀;
   v_j = max(sd_EL² − sp_EL², 0,1·sd_EL²); sd_d² = v_j + sp_d², con sp_d = DT de λ(d, 2025-26) − λ(origen, t) en los
   draws de la NUTS del paso 2 (la temporada en curso con la varianza de la innovación de un año añadida).

   Valor en la vara de una métrica combinada: w·(conversión v5) + (1 − w)·(conversión v3.2 de `vara.json`), con la
   misma w de la combinada. Las métricas derivadas (TS%, eFG%, por 100 y STL%) no tienen λ propio: se convierten con
   `vara.json`. **SUPUESTO:** se convierte el valor combinado con las dos traducciones, no cada componente con la suya
   (la tabla v1 no lleva los componentes); con la vara en la EuroLeague el resultado es exacto.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from bbnorm5 import config as C
from bbnorm5.medida import datos as DM

DIR = C.DIR_DATOS.parent / "v5_1" / "producto"
COMBINADA = C.DIR_DATOS.parent / "v5_1" / "salidas" / "combinada"
INCREMENTAL = C.DIR_DATOS.parent / "v5_1" / "incremental"
CLAVE = ["liga", "player_id", "team_id"]
# las 25 métricas del esquema v1 que la v5.1 cambia (orden de los bits de las máscaras)
ORDEN = ["pts_p100", "ts_pct", "efg_pct", "fg2_pct", "fg3_pct", "ft_pct", "fg3a_rate", "fta_rate", "usg_pct", "ast_pct",
         "tov_pct", "oreb_pct", "dreb_pct", "oreb_p100", "dreb_p100", "stl_pct", "blk_pct", "stl_p100", "blk_p100",
         "pf_p100", "pct_aro", "pct_corta", "pct_media", "pct_t3_esquina", "pct_asistidas"]
SUF = ("", "_lo", "_hi", "_pctel")
COLUMNAS = [m + s for m in ORDEN for s in SUF]
VARA = ("euroleague", "2025-26")


def _tabla_combinada(t: str) -> Path:
    f = INCREMENTAL / t / "normalizado" / f"{t}.csv.gz"          # temporada en curso: el proceso paralelo
    return f if f.exists() else COMBINADA / "normalizado" / f"{t}.csv.gz"


V5S = ("_v5", "_v5_lo", "_v5_hi")


def superposicion(t: str) -> dict:
    v = pd.read_csv(_tabla_combinada(t), low_memory=False, dtype={"player_id": str, "team_id": str})
    cols = [m + s_ for m in ORDEN for s_ in V5S if m + s_ in v.columns]
    s = v[CLAVE + cols]
    s = s[s[cols].notna().any(axis=1)]
    assert not s.duplicated(CLAVE).any(), "clave de fila duplicada"
    DIR.joinpath("superposicion").mkdir(parents=True, exist_ok=True)
    s.to_csv(DIR / "superposicion" / f"{t}.csv.gz", index=False, compression="gzip")
    return {"temporada": t, "filas": int(len(s)), "de": int(len(v)), "metricas": len(cols) // 3}


def _pctel(c: np.ndarray, v: pd.DataFrame) -> np.ndarray:
    """Percentil entre los jugadores de la EuroLeague de la misma posición de la tabla (= formato_v32._pctel)."""
    out = np.full(len(c), np.nan)
    pos = v["pos3"].astype(str).to_numpy()
    ref = (v["liga"] == VARA[0]).to_numpy() & np.isfinite(c)
    for p in set(pos):
        r = np.sort(c[ref & (pos == p)])
        sel = (pos == p) & np.isfinite(c)
        if len(r):
            out[sel] = 100 * np.searchsorted(r, c[sel], side="right") / len(r)
    return out


def aplicar(v32: pd.DataFrame, sup: pd.DataFrame, pesos: dict) -> pd.DataFrame:
    """Tabla v3.2 vigente (esquema v1) + componente v5 → tabla v5.1. Mismas filas y columnas, más las dos máscaras;
    `fuente_norm` = «V5.1» en las filas con alguna métrica de la v5."""
    v = v32.copy()
    for c in ("player_id", "team_id"):
        v[c] = v[c].astype(str)
    s = sup.copy()
    for c in ("player_id", "team_id"):
        s[c] = s[c].astype(str)
    j = v[CLAVE].merge(s, on=CLAVE, how="left")
    assert len(j) == len(v)
    comb = np.zeros(len(v), np.int64)
    solo = np.zeros(len(v), np.int64)
    for b, m in enumerate(ORDEN):
        if m not in v.columns or m + "_v5" not in j.columns:
            continue
        a = {s_: j[m + s_].to_numpy(float) for s_ in V5S}
        hay5 = np.isfinite(a["_v5"])
        hay32 = np.isfinite(v[m].to_numpy(float)) & np.isfinite(v[m + "_lo"].to_numpy(float))
        ambos, sol = hay5 & hay32, hay5 & ~hay32
        w = float(pesos.get(m, 0.5))
        for s5, s3 in zip(V5S, ("", "_lo", "_hi")):
            x3 = v[m + s3].to_numpy(float)
            v[m + s3] = np.where(ambos, w * a[s5] + (1 - w) * x3, np.where(sol, a[s5], x3))
        if m + "_pctel" in v.columns:
            v[m + "_pctel"] = np.where(hay5, _pctel(v[m].to_numpy(float), v), v[m + "_pctel"].to_numpy(float))
        comb |= np.where(ambos, 1 << b, 0)
        solo |= np.where(sol, 1 << b, 0)
    v["v51_comb"], v["v51_solo"] = comb, solo
    v["fuente_norm"] = np.where((comb | solo) > 0, "V5.1", "V3.2")
    assert len(v) == len(v32)
    return v


def vara(innovacion: bool = True) -> dict:
    """vara_v51.json: Δ_d y sp por nodo de las métricas con λ propio, y la w de todas."""
    from bbnorm5.ligas import modelo as LM
    from bbnorm5.ligas import resumen_paso2 as LR2
    from bbnorm5.salidas import formato_v32 as F
    lam = LR2.cargar(LM.BLOQUES_PASO2, "paso2_")
    meta = json.loads((COMBINADA / "meta.json").read_text())
    w, k = meta["pesos"], meta["factor_unidades"]
    a5 = {m3: m5 for m5, m3 in F.A_V32.items()}
    ligas = None
    out = {"temporada": VARA[1], "z80": 1.2815516, "orden": ORDEN, "metricas": {}}
    for m3 in ORDEN:
        e = {"w": round(float(w.get(m3, 0.5)), 4)}
        m5 = a5.get(m3)
        if m5 in lam:
            z = lam[m5]
            L, T = z["ligas"], list(z["temporadas"])
            ligas = ligas or L
            assert L == ligas, "las ligas de λ difieren entre bloques"
            iv = T.index(VARA[1])
            ref = z["lam"][:, :, iv]                                   # draws × ligas, 2025-26
            e["familia"] = DM.METRICAS[m5][0]
            e["k"] = float(k[m5])
            e["delta"] = {l: round(float((ref[:, L.index(VARA[0])] - ref[:, i]).mean()), 5) for i, l in enumerate(L)}
            inn = float(np.median(np.mean((z["lam"][:, :, -1] - z["lam"][:, :, -2]) ** 2, axis=0))) if innovacion else 0.0
            sp = {}
            for io, lo_ in enumerate(L):
                for it, t in enumerate(T):
                    d = ref - z["lam"][:, io, it][:, None]                 # λ(d, vara) − λ(origen, t)
                    sp[f"{lo_}:{t}"] = [round(float(x), 4) for x in d.std(axis=0)]
                ult = _siguiente(T[-1])                                    # temporada en curso, sin NUTS
                d = ref - z["lam"][:, io, len(T) - 1][:, None]
                sp[f"{lo_}:{ult}"] = [round(float(np.sqrt(x + inn)), 4) for x in d.var(axis=0)]
            e["sp"] = sp
        out["metricas"][m3] = e
    out["ligas"] = ligas
    DIR.mkdir(parents=True, exist_ok=True)
    C.escribir_json(out, DIR / "vara_v51.json")
    return {"metricas_con_lambda": sum("delta" in e for e in out["metricas"].values()),
            "kb": round((DIR / "vara_v51.json").stat().st_size / 1e3)}


def _siguiente(t: str) -> str:
    a = int(t[:4]) + 1
    return f"{a}-{str(a + 1)[-2:]}"


def convertir(v: float, lo: float, hi: float, m3: str, liga_o: str, temp_o: str, liga_d: str, vd: dict) -> dict | None:
    """Referencia (Python) de la conversión v5 que hace el artifact (sin la mezcla con la v3.2). None si la métrica no
    tiene λ propio."""
    from scipy import special
    e = vd["metricas"][m3]
    if "delta" not in e or liga_d not in e["delta"]:
        return None
    fam, kk, z80 = e["familia"], e["k"], vd["z80"]
    enl = {"binomial": lambda x: special.logit(np.clip(x / kk, 1e-6, 1 - 1e-6)),
           "poisson": lambda x: np.log(np.maximum(x / kk, 1e-9))}.get(fam, lambda x: x / kk)
    inv = {"binomial": lambda y: special.expit(y) * kk, "poisson": lambda y: np.exp(y) * kk}.get(fam, lambda y: y * kk)
    L = vd["ligas"]
    nodo = f"{liga_o}:{temp_o}"
    if nodo not in e["sp"]:
        cand = sorted(x for x in e["sp"] if x.startswith(f"{liga_o}:"))
        nodo = cand[-1] if cand else None
    sp = e["sp"].get(nodo) if nodo else None
    sp_e = sp[L.index(VARA[0])] if sp else 0.0
    sp_d = sp[L.index(liga_d)] if sp else 0.0
    ee = float(enl(v))
    ed = ee - e["delta"][liga_d]
    out = {"valor": float(inv(ed))}
    for lado, x, sg in (("lo", lo, -1), ("hi", hi, 1)):
        if x is None or not np.isfinite(x):
            out[lado] = None
            continue
        sd_e = abs(ee - float(enl(x))) / z80
        vj = max(sd_e ** 2 - sp_e ** 2, 0.1 * sd_e ** 2)
        out[lado] = float(inv(ed + sg * z80 * np.sqrt(vj + sp_d ** 2)))
    return out


def generar(temporadas: list[str] | None = None) -> dict:
    ts = temporadas or sorted({f.name[:7] for f in (COMBINADA / "normalizado").glob("*.csv.gz")} |
                              {p.name for p in INCREMENTAL.glob("*") if p.is_dir()})
    res = {"superposicion": [superposicion(t) for t in ts], "vara": vara()}
    C.escribir_json({**C.metadatos({"fase": "v5.1-F6-producto"}), **res}, DIR / "meta.json")
    return res
