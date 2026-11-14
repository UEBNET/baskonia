"""F10 · Nivel Kerno recalculado con la v5 (encargo §14.2) y su examen frente al NK₁ vigente.

El NK vigente (bbequipo/anclas.py, «nivel_cerno»): NK = 100·E[F_ref(C)], con C la contribución por partido de la
predictiva del simulador y F_ref la distribución de C en la liga de destino × puesto (3 temporadas ≤ t, ponderada por
minutos). Se calibra con una isotónica ajustada en los cortes anteriores (NK crudo → percentil realizado).

Variantes v5 (mismos fichajes, misma F_ref, misma calibración):
- **v5 predictivo:** C = minutos del motor v3.3 × pts/100 predictivos de la v5 (por_partido.py, ρ estimada).
- **v5 nivel (propuesta del encargo):** C = minutos esperados del motor × pts/100 del **intervalo de nivel** de la v5
  (sin el ruido de la temporada). Mide cuánto vale el jugador en esa liga y puesto, no lo que hará esa temporada.

Examen (el del NK vigente, F5 de la v4.0): separación de pares (NK_a ≥ NK_b + 10 → C_real_a > C_real_b en el mismo
corte y liga), correlación de rangos con el percentil realizado y cobertura del rango del 80 %. Se compara en los fichajes
comunes, con IC por bootstrap de personas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from bbnorm5 import config as C
from bbnorm5.aguas_abajo import por_partido as PP

NC = C.RAIZ / "data" / "modelos" / "v4_0" / "equipo" / "anclas" / "nc_examen.csv.gz"
PRED = C.DIR_DATOS / "validacion" / "predicciones_v5.parquet"
Z80 = stats.norm.ppf(0.9)


def _referencias():
    from bbequipo import anclas as AN
    v32, S, SI = AN._v()
    cfg = AN.C.cargar()
    roles = SI._leer_roles_temporada()
    gm = {l: S.minutos_partido(l) for l in roles["liga"].unique()}
    return AN, cfg, roles, gm


def _sd_nivel(d: pd.DataFrame) -> np.ndarray:
    """DT del nivel de pts/100 en la escala del examen: anchura del 80 % del nivel de la F8, reescalada."""
    p = pd.read_parquet(PRED, columns=["persona_v5", "anio", "liga", "metrica", "modelo", "ancho_nivel80", "q50"])
    p = p[(p["metrica"] == "pts_p100") & (p["modelo"] == PP.MODELO.replace("_recal", ""))]
    p = p.drop_duplicates(["persona_v5", "anio", "liga"])
    j = d[["persona_v5", "anio", "liga"]].merge(p, on=["persona_v5", "anio", "liga"], how="left")
    escala = d[f"{PP.MODELO}__q50"].to_numpy(float) / j["q50"].to_numpy(float)
    return j["ancho_nivel80"].to_numpy(float) * escala / (2 * Z80)


def contribuciones(cfg: dict) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
    """Fichajes del prototipo con draws de C predictiva (v5), de C de nivel (v5) y de C de la v3.3 ensamblada igual."""
    S = cfg["por_partido"]["draws"]
    rng = np.random.default_rng(cfg["semilla"] + 7)
    d = PP.pits(PP.casos())
    partes, Cp, Cn, Ce = [], [], [], []
    for anio in sorted(d["anio"].unique()):
        t = d[d["anio"] == anio].reset_index(drop=True)
        s = PP.simular(t, PP.dependencias(d, anio), S, rng, companeros=False)
        sd = _sd_nivel(t)
        nivel = t[f"{PP.MODELO}__q50"].to_numpy(float)[:, None] + sd[:, None] * rng.standard_normal((len(t), S))
        m_esp = s["M"].mean(axis=1, keepdims=True)                     # minutos esperados del motor
        Cn.append(m_esp / t["gm"].to_numpy(float)[:, None] * np.maximum(nivel, 0))
        Cp.append(s["C_v5"])
        Ce.append(s["C_v33e"])
        partes.append(t.assign(sd_nivel=sd))
    return pd.concat(partes, ignore_index=True), np.vstack(Cp), np.vstack(Cn), np.vstack(Ce)


def ejecutar(cfg: dict) -> dict:
    out_dir = C.dir_fase(cfg)
    AN, cfg_eq, roles, gm = _referencias()
    d, Cp, Cn, Ce = contribuciones(cfg)
    nc = pd.read_csv(NC, low_memory=False, dtype={"team_d": str})
    d["team_d"] = d["team_d"].astype(str)
    j = d.reset_index().merge(nc, on=["persona_id", "liga_d", "team_d", "temporada_d"], how="inner", suffixes=("", "_nc"))
    filas = []
    for corte, g in j.groupby("corte"):
        F = AN.referencias_nc(cfg_eq, roles, corte, gm)
        for r in g.itertuples():
            Fr = F.get((r.liga_d, r.pos3)) or F.get((r.liga_d, None))
            if Fr is None or Fr.n < 30:
                continue
            i = r.index
            vp, lop, hip = AN.percentil_esperado(Fr, Cp[i])
            vn, lon, hin = AN.percentil_esperado(Fr, Cn[i])
            ve, loe, hie = AN.percentil_esperado(Fr, Ce[i])
            filas.append({"i": i, "V5P": vp, "V5P_lo80": lop, "V5P_hi80": hip, "V5N": vn, "V5N_lo80": lon, "V5N_hi80": hin,
                          "V33E": ve, "V33E_lo80": loe, "V33E_hi80": hie})
    k = j.merge(pd.DataFrame(filas), left_on="index", right_on="i")
    # misma calibración isotónica que el NK vigente (cortes anteriores; el primero, el suyo: informativo)
    cortes = sorted(k["anio_nc"].unique()) if "anio_nc" in k else sorted(k["corte"].str[:4].astype(int).unique())
    k["anio"] = k["corte"].str[:4].astype(int)
    for v in ("V5P", "V5N", "V33E"):
        x = (k.drop(columns=[c for c in k.columns if c.startswith("NC2")])
             .rename(columns={v: "X", f"{v}_lo80": "X_lo80", f"{v}_hi80": "X_hi80"})
             .pipe(lambda z: z.assign(NC2=z["X"], NC2_lo80=z["X_lo80"], NC2_hi80=z["X_hi80"])))   # NC₂: relleno, se descarta
        x = AN.calibrar_nc(x, cortes, col="X")
        for suf in ("", "_lo80", "_hi80"):
            k[f"{v}{suf}"] = x[f"X{suf}"].to_numpy()
            k[f"{v}{suf}_crudo"] = x[f"X{suf}_crudo"].to_numpy()
    k = k[k["eval"]].copy()
    k.round(3).to_csv(out_dir / "nivel_kerno_examen.csv.gz", index=False)
    return resumir(cfg, k, AN)


def _spearman_boot(k: pd.DataFrame, cols: list[str], B: int, rng) -> dict:
    per = k["persona_v5"].to_numpy()
    u, inv = np.unique(per, return_inverse=True)
    base = {c: stats.spearmanr(k[c], k["pct_realizado"]).statistic for c in cols}
    bs = {c: [] for c in cols}
    for _ in range(B):
        # remuestreo por personas: cada persona entra con todas sus filas tantas veces como salga
        f = np.bincount(rng.integers(0, len(u), len(u)), minlength=len(u))[inv]
        sel = np.repeat(np.arange(len(k)), f)
        for c in cols:
            bs[c].append(stats.spearmanr(k[c].to_numpy()[sel], k["pct_realizado"].to_numpy()[sel]).statistic)
    out = {c: {"rho": float(base[c]), "ic": [float(np.quantile(bs[c], .025)), float(np.quantile(bs[c], .975))]} for c in cols}
    for c in cols[1:]:
        dif = np.array(bs[c]) - np.array(bs[cols[0]])
        out[c]["frente_a_" + cols[0]] = {"dif": float(base[c] - base[cols[0]]),
                                          "ic": [float(np.quantile(dif, .025)), float(np.quantile(dif, .975))]}
    return out


def resumir(cfg: dict, k: pd.DataFrame, AN) -> dict:
    out_dir = C.dir_fase(cfg)
    rng = np.random.default_rng(cfg["semilla"] + 11)
    cols = ["NC1", "V33E", "V5P", "V5N"]
    res = {"fichajes": int(len(k)), "personas": int(k["persona_v5"].nunique()),
           "cortes": sorted(k["corte"].unique().tolist())}
    res["spearman_pct_realizado"] = _spearman_boot(k, cols, cfg["bootstrap"] // 2, rng)
    res["separacion"] = {c: AN.examen_separacion(k, c, "C_real", ["corte", "liga_d"], 10.0, 100, cfg["semilla"])
                         for c in cols}
    res["cobertura80"] = {c: float(((k["pct_realizado"] >= k[f"{c}_lo80"]) & (k["pct_realizado"] <= k[f"{c}_hi80"])).mean())
                          for c in cols}
    res["anchura80"] = {c: float((k[f"{c}_hi80"] - k[f"{c}_lo80"]).mean()) for c in cols}
    res["anchura80_cruda"] = {c: float((k[f"{c}_hi80_crudo"] - k[f"{c}_lo80_crudo"]).mean()) for c in ("V5P", "V5N")}
    res["corr_nc1"] = {c: float(k[["NC1", c]].corr().iloc[0, 1]) for c in ("V33E", "V5P", "V5N")}
    # aportación de la producción v5 con el mismo ensamblaje (minutos, dependencia, F_ref y calibración)
    res["spearman_v5_frente_v33e"] = _spearman_boot(k, ["V33E", "V5P", "V5N"], cfg["bootstrap"] // 2, rng)
    sub = k[k["corte"] != k["corte"].min()]                  # calibradas con cortes anteriores
    res["sin_primer_corte"] = {"fichajes": int(len(sub)),
                               "separacion": {c: AN.examen_separacion(sub, c, "C_real", ["corte", "liga_d"], 10.0, 100,
                                                                      cfg["semilla"])["fraccion"] for c in cols},
                               "cobertura80": {c: float(((sub["pct_realizado"] >= sub[f"{c}_lo80"]) &
                                                         (sub["pct_realizado"] <= sub[f"{c}_hi80"])).mean()) for c in cols}}
    C.escribir_json({**C.metadatos(cfg, [NC, PP.V33, PP.CASOS, PRED]), **res}, out_dir / "meta_nivel_kerno.json")
    return res
