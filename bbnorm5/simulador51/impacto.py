"""v5.1 F4 · Impacto: RAPM multiliga con el perfil de nivel de la v5 en su prior (encargo v5.1 §2; F10 §3.3).

El prior del RAPM multiliga de la v4.0 (β_i ~ N(g(x̃_i; γ), τ²)) toma sus rasgos por bloques (`rapm.tabla_prior`):
latente, estilos, rasgos de la v3.2, rol, edad, puesto y RAPM de la temporada anterior. Aquí se añade un bloque **v5**:
el nivel de carrera filtrado de la F4 de la v5 (η = μ + nivel, sin ver temporadas posteriores) en 13 métricas de
producción, con su máscara. Todo lo demás es igual. La configuración lleva una marca para que la huella de las cachés
sea otra y no se mezclen con las de la F0.

Cadena (sólo escribe en experimentos/v5_1/F4/): ajustes F1 por corte con el bloque v5 → examen de equipo F4 (ΔNet) →
Nivel Kerno e Impacto (anclas). El simulador (minutos) es el reproducido en la F0. Se compara con la F0 en los mismos
fichajes y equipos.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
from scipy import stats

from bbnorm5 import config as C

PERFIL = ["pts_p100", "usg_pct", "ast_pct", "tov_pct", "oreb_pct", "dreb_pct", "stl_p100", "blk_pct", "t2_pct",
          "t3_pct", "tpar", "ftr", "pct_asistidas"]
BASE = C.RAIZ / "experimentos" / "v5_1"


def perfil_v5() -> pd.DataFrame:
    """Nivel filtrado de la F4 de la v5 por persona del crosswalk, temporada y liga (columnas v5_<m>)."""
    n = pd.read_parquet(C.DIR_DATOS / "carrera" / "niveles_carrera.parquet",
                        columns=["persona_v5", "liga", "temporada", "metrica", "mu", "nivel_carrera"])
    n = n[n["metrica"].isin(PERFIL)].assign(eta=lambda x: x["mu"] + x["nivel_carrera"])
    p = n.pivot_table(index=["persona_v5", "liga", "temporada"], columns="metrica", values="eta").reset_index()
    p.columns = [c if c in ("persona_v5", "liga", "temporada") else f"v5_{c}" for c in p.columns]
    per = pd.read_csv(C.DIR_DATOS / "limpios" / "entidades" / "personas_v5.csv", dtype=str)
    cw = per.drop_duplicates(["persona_crosswalk", "persona_v5"])[["persona_crosswalk", "persona_v5"]]
    return p.merge(cw, on="persona_v5").rename(columns={"persona_crosswalk": "persona_id"})


def instalar_bloque_v5():
    """Envuelve rapm.tabla_prior para que añada el bloque v5 (y su máscara) a la tabla de rasgos."""
    from bbequipo import rapm as RP
    if getattr(RP.tabla_prior, "_v51", False):
        return
    original = RP.tabla_prior
    pv = perfil_v5()
    cols = [f"v5_{m}" for m in PERFIL]

    def tabla_prior(perf, cfg):
        T = original(perf, cfg)
        bl = dict(T.attrs["bloques"])
        a = pv[["persona_id", "temporada", "liga"] + cols]
        # liga principal del registro; si no está, la de más observaciones de la persona en esa temporada
        j = T[["persona_id", "temporada", "liga"]].merge(a, on=["persona_id", "temporada", "liga"], how="left")
        falta = j[cols[0]].isna().to_numpy()
        if falta.any():
            alt = a.drop_duplicates(["persona_id", "temporada"]).drop(columns="liga")
            k = T.loc[falta, ["persona_id", "temporada"]].merge(alt, on=["persona_id", "temporada"], how="left")
            j.loc[falta, cols] = k[cols].to_numpy()
        for c in cols:
            T[c] = j[c].to_numpy(float)
        T["m_v5"] = T[cols].notna().all(axis=1).astype(float)
        bl["v5"] = cols
        bl["mascara"] = list(bl["mascara"]) + ["m_v5"]
        T.attrs["bloques"] = bl
        return T

    tabla_prior._v51 = True
    RP.tabla_prior = tabla_prior
    # el bloque v5 entra SÓLO en el prior del RAPM: las redes de sinergia y de conjunto (F2 y F3 de la v4.0, versionadas)
    # se entrenaron con los rasgos vigentes (44 columnas) y los siguen recibiendo igual
    from bbequipo import sinergia as SG
    orig_init = SG.Rasgos.__init__

    def init(self, T, cfg):
        T2 = T.copy(deep=False)
        bl2 = dict(T.attrs["bloques"])
        bl2.pop("v5", None)
        bl2["mascara"] = [c for c in bl2["mascara"] if c != "m_v5"]
        T2.attrs["bloques"] = bl2
        orig_init(self, T2, cfg)

    SG.Rasgos.__init__ = init


def configuracion(cfg_eq: dict) -> dict:
    from bbequipo import config as BC
    return BC.con(cfg_eq, **{"f1.prior.bloque_v51": "nivel_filtrado_v5_13_metricas",
                             "f1.bayes_empirico.tau_rejilla": [1.0, 2.0, 3.0],
                             "f1.prior.ridge_alpha_rejilla": [1.0]})


def _redirigir(sub: str):
    from bbequipo import anclas as AN, equipo as EQ

    def d(nombre):
        def f(cfg):
            x = BASE / sub / nombre
            x.mkdir(parents=True, exist_ok=True)
            return x
        return f
    EQ.dir_salida = d("equipo")
    AN.dir_salida = d("anclas")


def ejecutar(cfg: dict) -> dict:
    os.environ["CERNO_SIMULADOR"] = "v32"
    from bbfit import validacion as V
    V.DIR_VAL = C.RAIZ / cfg["reproducido"]
    from bbequipo import config as BC, equipo as EQ, anclas as AN, rapm as RP, examen_f1 as EX
    instalar_bloque_v5()
    _redirigir("F4")
    cfg_eq = configuracion(BC.cargar())
    tr = RP.tramos(cfg_eq)
    hist = {}
    for a in [int(x) for x in cfg_eq["criterios"]["comunes"]["cortes"]]:
        r = EX.ajuste_corte(cfg_eq, a, tr, "gbm")
        hist[a] = [{k: v for k, v in h.items() if k != "log_marginal_por_alpha_tau"} for h in r["res"].get("historial", [])]
        print(f"  ajuste F1 con el bloque v5, corte {a}", flush=True)
    EQ.main(cfg_eq)
    AN.main(cfg_eq)
    res = comparar()
    res["historial_eb"] = hist
    out = C.DIR_DATOS.parent / "v5_1" / "impacto"
    out.mkdir(parents=True, exist_ok=True)
    C.escribir_json({**C.metadatos(cfg), **res}, out / "meta_impacto.json")
    return res


def _spearman_dif(a: pd.DataFrame, x: str, y: str, real: str, personas: str, B: int, rng) -> dict:
    u, inv = np.unique(a[personas].astype(str), return_inverse=True)
    r1, r2 = stats.spearmanr(a[x], a[real]).statistic, stats.spearmanr(a[y], a[real]).statistic
    bs = []
    for _ in range(B):
        sel = np.repeat(np.arange(len(a)), np.bincount(rng.integers(0, len(u), len(u)), minlength=len(u))[inv])
        bs.append(stats.spearmanr(a[x].to_numpy()[sel], a[real].to_numpy()[sel]).statistic -
                  stats.spearmanr(a[y].to_numpy()[sel], a[real].to_numpy()[sel]).statistic)
    return {"v51": float(r1), "f0": float(r2), "dif": float(r1 - r2), "ic": [float(np.quantile(bs, .025)), float(np.quantile(bs, .975))]}


def comparar(B: int = 500, semilla: int = 20261116) -> dict:
    """v5.1 (bloque v5) frente a la F0 (prior vigente) en los mismos casos: ΔNet de equipo, Impacto frente al on/off."""
    rng = np.random.default_rng(semilla)
    f0, f4 = BASE / "F0" / "v40", BASE / "F4"
    r = {}
    a = json.loads((f0 / "equipo" / "examen" / "resumen_examen_f4.json").read_text())["global_decision"]
    b = json.loads((f4 / "equipo" / "examen" / "resumen_examen_f4.json").read_text())["global_decision"]
    r["f4"] = {k: {"f0": a.get(k), "v51": b.get(k)} for k in ("n", "mae_f4", "mae_persistencia", "mae_aditivo_f1",
                                                             "cobertura_80", "ic95_dif_persistencia")}
    pa = pd.read_csv(f0 / "equipo" / "examen" / "predicciones_f4.csv.gz")
    pb = pd.read_csv(f4 / "equipo" / "examen" / "predicciones_f4.csv.gz")
    k = ["liga", "temporada_ant", "club", "corte"]
    m = pa.merge(pb, on=k, suffixes=("_f0", "_v51"))
    dec = m[m["corte"].isin([2022, 2023, 2024])]
    ea, eb = np.abs(dec["delta_real_f0"] - dec["delta_pred_f0"]), np.abs(dec["delta_real_v51"] - dec["delta_pred_v51"])
    bs = [np.mean(eb.to_numpy()[i] - ea.to_numpy()[i]) for i in (rng.integers(0, len(dec), len(dec)) for _ in range(B))]
    r["f4_pareado"] = {"equipos": int(len(dec)), "mae_f0": float(ea.mean()), "mae_v51": float(eb.mean()),
                       "dif": float((eb - ea).mean()), "ic": [float(np.quantile(bs, .025)), float(np.quantile(bs, .975))]}
    ia = json.loads((f0 / "anclas" / "resumen_anclas.json").read_text())["im"]
    ib = json.loads((f4 / "anclas" / "resumen_anclas.json").read_text())["im"]
    oa, ob = ia["criterio_redefinido_onoff"]["variantes"]["im_onoff"], ib["criterio_redefinido_onoff"]["variantes"]["im_onoff"]
    r["im_onoff"] = {"f0": oa["monotonia"], "v51": ob["monotonia"], "fichajes": [ia["criterio_redefinido_onoff"]["fichajes"],
                                                                                  ib["criterio_redefinido_onoff"]["fichajes"]]}
    r["im_paquete"] = {"f0": ia["paquete"]["monotonia"], "v51": ib["paquete"]["monotonia"]}
    r["im_puerta"] = {"f0": ia["puerta"], "v51": ib["puerta"]}
    # pareado por fichaje: correlación con el on/off del jugador en destino
    xa = pd.read_csv(f0 / "anclas" / "im_examen.csv.gz", low_memory=False)
    xb = pd.read_csv(f4 / "anclas" / "im_examen.csv.gz", low_memory=False)
    kk = [c for c in ("persona_id", "liga_d", "team_d", "corte") if c in xa.columns and c in xb.columns]
    real = "net_rtg_aj_onoff" if "net_rtg_aj_onoff" in xa.columns else None
    if real is None:
        rr = pd.read_csv(C.RAIZ / "data" / "modelos" / "roles" / "player_role_season.csv.gz",
                         usecols=["liga", "temporada", "team_id", "persona_id", "net_rtg_aj_onoff", "min_total"],
                         dtype={"team_id": str}, low_memory=False)
        rr = rr[rr["min_total"] >= 300].rename(columns={"liga": "liga_d", "team_id": "team_d", "temporada": "temporada_d"})
        for x in (xa, xb):
            x["temporada_d"] = x["anio"].map(lambda a_: f"{a_ + 1}-{str(a_ + 2)[-2:]}")
            x["team_d"] = x["team_d"].astype(str)
        xa = xa.merge(rr, on=["liga_d", "team_d", "temporada_d", "persona_id"], how="inner")
        real = "net_rtg_aj_onoff"
    mm = xa[kk + ["IM", real]].merge(xb[kk + ["IM"]], on=kk, suffixes=("_f0", "_v51")).dropna()
    mm = mm[mm["corte"].isin([2022, 2023, 2024]) if mm["corte"].dtype != object else mm["corte"].str[:4].astype(int).isin([2022, 2023, 2024])]
    r["im_onoff_pareado"] = {"fichajes": int(len(mm)), **_spearman_dif(mm, "IM_v51", "IM_f0", real, "persona_id", B, rng)}
    return r
