"""F8 · Validación de la capa de ligas con el GLS del paso 2 (el mismo estimador que alimenta la proyección):

- **LOLO** (dejar fuera una liga, como la F1): se quitan de la liga L (a) sus puentes de la misma temporada, (b) sus
  traspasos o (c) ambos, y se compara su λ con el estimado con todo. Error relativo = |λ sin − λ con| / DT de λ entre
  ligas; cobertura del 80 % del intervalo sin los datos.
- **Jugadores puente dejados fuera** (encargo §12): 5 grupos de personas; para las de cada grupo se quitan todos sus
  puentes y traspasos, se reestima λ y se predice su diferencia entre la competición B y la A conociendo sólo A.
  Cobertura, z y CRPS normal; paso 1 (sólo puentes intra) frente a paso 2 (con traspasos).
- **SBC de λ**: datos sintéticos con el diseño real (mismos puentes, traspasos, varianzas y contexto) y λ, β y la
  varianza extra sacados del propio ajuste; se reestima y se guarda el rango del λ verdadero en su posterior.
  Uniforme si el estimador está calibrado.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from bbnorm5 import config as C
from bbnorm5.ligas import datos as LD
from bbnorm5.ligas import seleccion as LS
from bbnorm5.medida import datos as DM

DIR = C.DIR_DATOS / "validacion"
Z80 = stats.norm.ppf(0.9)


def _datos(cfg7: dict, T: int):
    x = LS.preparar(cfg7)
    intra = pd.read_parquet(C.DIR_DATOS / "ligas" / "pares_intra.parquet")
    return intra[intra["temporada"].str[:4].astype(int) < T], x[(x["anio_obj"] < T) & (x["cl"] > 0)]


def _lam(g: dict, liga: str, ref: str) -> tuple[float, float]:
    il = {l: i for i, l in enumerate(g["ligas"])}
    if liga not in il or ref not in il:
        return np.nan, np.nan
    a, b = il[ref], il[liga]
    return float(g["lambda"][b] - g["lambda"][a]), float(np.sqrt(g["cov"][a, a] + g["cov"][b, b] - 2 * g["cov"][a, b]))


def lolo(cfg7: dict, T: int = 2026) -> pd.DataFrame:
    intra, inter = _datos(cfg7, T)
    ligas = sorted(set(intra["liga_a"]) | set(intra["liga_b"]) | set(inter["liga"]))
    filas = []
    for met in DM.METRICAS:
        full = LS.gls_paso2(intra, inter, met, "encogido")
        lam_full = {l: _lam(full, l, "acb")[0] for l in ligas}
        sd_entre = float(np.nanstd([v for v in lam_full.values()]))
        for L in ligas:
            ref = "euroleague" if L == "acb" else "acb"
            v_full, _ = _lam(full, L, ref)
            fi = (intra["liga_a"] == L) | (intra["liga_b"] == L)
            ft = (inter["liga_ult"] == L) | (inter["liga"] == L)
            for var, a, b in (("sin_puentes_intra", intra[~fi], inter), ("sin_traspasos", intra, inter[~ft]),
                              ("sin_nada", intra[~fi], inter[~ft])):
                g = LS.gls_paso2(a, b, met, "encogido")
                v, s = _lam(g, L, ref)
                filas.append({"metrica": met, "liga": L, "variante": var,
                              "puentes_intra": int((fi & (intra["metrica"] == met)).sum()),
                              "traspasos": int((ft & (inter["metrica"] == met)).sum()), "lambda_completo": v_full, "lambda_sin": v, "sd_sin": s,
                              "error_rel": abs(v - v_full) / sd_entre if np.isfinite(v) else np.nan,
                              "sd_rel": s / sd_entre if np.isfinite(s) else np.nan,
                              "cubre80": bool(abs(v - v_full) <= Z80 * s) if np.isfinite(v) else np.nan})
        print(f"  lolo {met}", flush=True)
    d = pd.DataFrame(filas)
    d.to_csv(DIR / "lolo_v5.csv", index=False)
    return d


def puentes_fuera(cfg7: dict, T: int = 2026, k: int = 5, semilla: int = 0) -> pd.DataFrame:
    intra, inter = _datos(cfg7, T)
    personas = intra["persona_v5"].unique()
    rng = np.random.default_rng(semilla)
    grupo = dict(zip(personas, rng.integers(0, k, len(personas))))
    intra = intra.assign(grupo=intra["persona_v5"].map(grupo))
    filas = []
    for met in DM.METRICAS:
        a_m = intra[intra["metrica"] == met]
        for gk in range(k):
            fuera = set(a_m.loc[a_m["grupo"] == gk, "persona_v5"])
            te = a_m[a_m["grupo"] == gk]
            for var in ("paso1", "encogido"):
                g = LS.gls_paso2(a_m[a_m["grupo"] != gk], inter[~inter["persona_v5"].isin(fuera)], met, var)
                il = {l: i for i, l in enumerate(g["ligas"])}
                ok = te["liga_a"].isin(il) & te["liga_b"].isin(il)
                q = te[ok]
                ia, ib = q["liga_a"].map(il).to_numpy(), q["liga_b"].map(il).to_numpy()
                mu = g["lambda"][ib] - g["lambda"][ia] + q[LD.CONTEXTO].to_numpy(float) @ g["beta_ctx"]
                vl = g["cov"][ia, ia] + g["cov"][ib, ib] - 2 * g["cov"][ia, ib]
                sd = np.sqrt(q["var"].to_numpy(float) + g["s_c2"] + vl)
                z = (q["d"].to_numpy(float) - mu) / sd
                crps = sd * (z * (2 * stats.norm.cdf(z) - 1) + 2 * stats.norm.pdf(z) - 1 / np.sqrt(np.pi))
                filas.append(pd.DataFrame({"metrica": met, "grupo": gk, "variante": var, "persona_v5": q["persona_v5"],
                                           "liga_a": q["liga_a"], "liga_b": q["liga_b"], "z": z, "crps": crps,
                                           "sd": sd, "sd_lambda": np.sqrt(vl)}))
        print(f"  puentes fuera {met}", flush=True)
    d = pd.concat(filas, ignore_index=True)
    d.to_parquet(DIR / "puentes_fuera.parquet")
    return d


def sbc_lambda(cfg7: dict, T: int = 2026, R: int = 100, semilla: int = 0) -> pd.DataFrame:
    """Rango normalizado u = Φ((λ* − λ̂)/sd) del λ verdadero (relativo a la ACB) en R réplicas por métrica."""
    intra, inter = _datos(cfg7, T)
    rng = np.random.default_rng(semilla)
    filas = []
    for met in DM.METRICAS:
        a = intra[intra["metrica"] == met].reset_index(drop=True)
        b = inter[inter["metrica"] == met].reset_index(drop=True)
        g = LS.gls_paso2(a, b, met, "encogido")
        il = {l: i for i, l in enumerate(g["ligas"])}
        L = len(g["ligas"])
        Lc = np.linalg.cholesky(g["cov"][1:, 1:] + 1e-12 * np.eye(L - 1))
        ia, ib = a["liga_a"].map(il).to_numpy(), a["liga_b"].map(il).to_numpy()
        ja, jb = b["liga_ult"].map(il).to_numpy(), b["liga"].map(il).to_numpy()
        va = a["var"].to_numpy(float) + g["s_c2"]
        vb = (b["v_obs"] + b["v_y_sin_muestreo"]).to_numpy(float) + g["s_c2"]
        xa = a[LD.CONTEXTO].to_numpy(float) @ g["beta_ctx"]
        mu_b = (b["mu_origen"] + b["m_nivel"]).to_numpy(float)
        okb = np.isfinite(vb) & np.isfinite(mu_b)
        for r in range(R):
            lam = np.r_[0.0, g["lambda"][1:] + Lc @ rng.standard_normal(L - 1)]
            a2 = a.copy()
            a2["d"] = lam[ib] - lam[ia] + xa + np.sqrt(va) * rng.standard_normal(len(a))
            b2 = b.copy()
            b2["eta_obs"] = mu_b + lam[jb] - lam[ja] + np.sqrt(np.where(okb, vb, 1.0)) * rng.standard_normal(len(b))
            b2.loc[~okb, "eta_obs"] = np.nan
            h = LS.gls_paso2(a2, b2, met, "encogido")
            hl = {l: i for i, l in enumerate(h["ligas"])}
            for l in g["ligas"][1:]:
                if l in hl:
                    sd = float(np.sqrt(h["cov"][hl[l], hl[l]]))
                    filas.append({"metrica": met, "replica": r, "liga": l,
                                  "u": float(stats.norm.cdf((lam[il[l]] - h["lambda"][hl[l]]) / sd))})
        print(f"  sbc {met}", flush=True)
    d = pd.DataFrame(filas)
    d.to_csv(DIR / "sbc_lambda.csv.gz", index=False)
    return d
