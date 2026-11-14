"""v5.1 F6 · Producto para el artifact: la versión combinada como superposición de la v3.2 y su vara.

1. **Superposición por temporada** (`data/v5_1/producto/superposicion/<t>.csv.gz`). Una fila por (liga, player_id,
   team_id) con valor combinado de la v5.1 en alguna métrica, con:
   - las 100 columnas que la v5.1 cambia (25 métricas × valor, `_lo`, `_hi`, `_pctel`; esquema v1);
   - `v51_comb` y `v51_solo`: máscaras de bits en el orden de `ORDEN` (métrica combinada w·v5 + (1 − w)·v3.2, o sólo
     v5 por no haber v3.2).

   La producción la aplica fila a fila sobre su tabla v3.2 (`aplicar`): las filas que la v5.1 no cubre (Liga U,
   jugadores que el botón añada después de la última ejecución, métricas sin v5) siguen con la v3.2. `fuente_norm` dice
   cuál es cuál («V5.1» o «V3.2»).

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


def superposicion(t: str) -> dict:
    v = pd.read_csv(_tabla_combinada(t), low_memory=False, dtype={"player_id": str, "team_id": str})
    comb = np.zeros(len(v), np.int64)
    solo = np.zeros(len(v), np.int64)
    for b, m in enumerate(ORDEN):
        f = v.get(f"fuente_{m}")
        if f is None:
            continue
        comb |= np.where(f.eq("COMB"), 1 << b, 0)
        solo |= np.where(f.eq("V5"), 1 << b, 0)
    s = v[CLAVE + COLUMNAS].assign(v51_comb=comb, v51_solo=solo)
    s = s[(comb | solo) > 0]
    assert not s.duplicated(CLAVE).any(), "clave de fila duplicada"
    DIR.joinpath("superposicion").mkdir(parents=True, exist_ok=True)
    s.to_csv(DIR / "superposicion" / f"{t}.csv.gz", index=False, compression="gzip")
    return {"temporada": t, "filas": int(len(s)), "de": int(len(v)), "combinadas": int((comb > 0).sum())}


def aplicar(v32: pd.DataFrame, sup: pd.DataFrame) -> pd.DataFrame:
    """Tabla v3.2 (esquema v1) → tabla v5.1: en cada fila con superposición, sus 100 columnas pasan a ser las de la
    v5.1 donde la máscara de su métrica lo dice; `fuente_norm` = «V5.1» en esas filas. Mismas filas y columnas
    (más las dos máscaras)."""
    v = v32.copy()
    for c in ("player_id", "team_id"):
        v[c] = v[c].astype(str)
    s = sup.copy()
    for c in ("player_id", "team_id"):
        s[c] = s[c].astype(str)
    j = v[CLAVE].merge(s, on=CLAVE, how="left")
    comb = j["v51_comb"].fillna(0).astype(np.int64).to_numpy()
    solo = j["v51_solo"].fillna(0).astype(np.int64).to_numpy()
    for b, m in enumerate(ORDEN):
        k = ((comb | solo) >> b) & 1 == 1
        for s_ in SUF:
            c = m + s_
            if c in v.columns:
                v[c] = np.where(k, j[c].to_numpy(float), v[c].to_numpy(float))
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
