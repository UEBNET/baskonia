"""v5.1 F5 · Landing: efecto del primer año (δ₁) y del segundo (δ₂) por grupo de la Landing vigente, contraídos a través
del perfil latente de la F5, con examen de publicación y el escalón en puntos del Nivel Kerno.

1. **δ por métrica** (F10 bis, `aguas_abajo/landing.py`): residuo frente a la proyección de carrera con la traducción de
   los puentes (primer año) o sin traducción (segundo año en la misma liga), menos el de quienes no cambian en la misma
   liga-temporada; IC por bootstrap de personas más el error común de la traducción.
2. **Contracción a través del perfil latente.** En cada grupo y fase, los δ de las 14 métricas con cargas (F5, factores
   estables z2, z3, z5) se ajustan por mínimos cuadrados ponderados a Λγ; la desviación de cada métrica respecto a Λγ̂
   tiene varianza τ² (momentos) y el δ contraído es el promedio de precisión entre δ y Λγ̂. Las métricas sin cargas
   (zonas y % asistidas) se quedan con su δ. Gana potencia: 3 parámetros en lugar de 14.
3. **Examen de publicación** (fuera de tiempo, el de la F10 bis): δ contraído con las temporadas anteriores aplicado a la
   proyección publicada de la siguiente; se publica como corrección sólo si baja el WIS con IC < 0.
4. **Escalón en puntos del Nivel Kerno:** NK del segundo año (pts/100 + δ₂ de pts/100 del grupo) menos NK del primero,
   en los fichajes del examen de la F3, y su contraste con el percentil realizado en la segunda temporada.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from bbnorm5 import config as C
from bbnorm5.aguas_abajo import landing as LD
from bbnorm5.simulador51 import produccion as PR
from bbnorm5.validacion import fichajes as VF

CARGAS = C.DIR_DATOS / "latente" / "cargas_referencia.csv"
FACTORES = ["F2", "F3", "F5"]                 # perfiles estables de la F5 (z2, z3, z5)
EEUU_PRO = ("EEUU_a_Europa", "otro_desde_EEUU")


def contraer(t: pd.DataFrame) -> pd.DataFrame:
    """δ contraído a través del perfil latente por grupo y fase (columnas delta_lat, se_lat, tau_lat)."""
    L = pd.read_csv(CARGAS, index_col=0)[FACTORES]
    t = t.copy()
    t["delta_lat"], t["se_lat"], t["tau_lat"] = t["delta"], t["se"], np.nan
    for (fase, g), x in t.groupby(["fase", "grupo"]):
        x = x[x["metrica"].isin(L.index)]
        if len(x) < len(FACTORES) + 3:
            continue
        Lm = L.loc[x["metrica"]].to_numpy(float)
        d, se = x["delta"].to_numpy(float), x["se"].to_numpy(float)
        w = 1 / se ** 2
        A = Lm.T @ (w[:, None] * Lm)
        gam = np.linalg.solve(A + 1e-9 * np.eye(len(FACTORES)), Lm.T @ (w * d))
        f = Lm @ gam
        q = float(np.sum(w * (d - f) ** 2))
        tau2 = max(0.0, (q - (len(d) - len(FACTORES))) / float(np.sum(w)))
        if tau2 > 0:
            post = (d / se ** 2 + f / tau2) / (1 / se ** 2 + 1 / tau2)
            sp = np.sqrt(1 / (1 / se ** 2 + 1 / tau2))
        else:
            post, sp = f, np.sqrt(np.einsum("ij,jk,ik->i", Lm, np.linalg.inv(A), Lm))
        t.loc[x.index, "delta_lat"], t.loc[x.index, "se_lat"], t.loc[x.index, "tau_lat"] = post, sp, np.sqrt(tau2)
    t["ic_lo_lat"], t["ic_hi_lat"] = t["delta_lat"] - 1.96 * t["se_lat"], t["delta_lat"] + 1.96 * t["se_lat"]
    t["escala"] = t["delta_escala"] / t["delta"].replace(0, np.nan)
    t["delta_lat_escala"] = t["delta_lat"] * t["escala"]
    return t


def examen_contraido(cfg_l: dict, d: pd.DataFrame) -> pd.DataFrame:
    """Examen de publicación de la F10 bis con el δ contraído (estimado con las temporadas anteriores)."""
    from bbnorm5.validacion import recalibracion as VR
    L = cfg_l["landing"]
    rng = np.random.default_rng(cfg_l["semilla"] + 51)
    p, _ = VR.recalibradas(C.cargar("configs/v5/f8.yaml"))
    qs = ["q5", "q10", "q25", "q50", "q75", "q90", "q95"]
    p = p[["persona_v5", "anio", "liga", "metrica", "obs"] + qs].dropna()
    k = d[["persona_v5", "anio_obj", "liga", "metrica", "fase", "grupo", "grupo_prev"]].rename(columns={"anio_obj": "anio"})
    p = p.merge(k.drop_duplicates(["persona_v5", "anio", "liga", "metrica"]), on=["persona_v5", "anio", "liga", "metrica"])
    p["clave"] = np.where(p["fase"] == "primera", p["grupo"], np.where(p["fase"] == "segunda", p["grupo_prev"], ""))
    sel = p["clave"].isin(EEUU_PRO)
    p = pd.concat([p, p[sel].assign(clave="llegada_EEUU_Europa_pro")], ignore_index=True)
    semi = (p["q90"] - p["q10"]) / 2
    suelo = p.assign(s=semi).loc[semi > 0].groupby("metrica")["s"].quantile(0.05)
    p["semi"] = np.maximum(semi, p["metrica"].map(suelo))
    p["z"] = ((p["obs"] - p["q50"]) / p["semi"]).clip(-4, 4)
    Lc = pd.read_csv(CARGAS, index_col=0)[FACTORES]
    filas = []
    for T in sorted(p["anio"].unique()):
        cal, te = p[p["anio"] < T], p[p["anio"] == T]
        if cal.empty:
            continue
        ref = cal[cal["fase"] == "estable"].groupby("metrica")["z"].mean()
        g = cal[cal["fase"] != "estable"].groupby(["fase", "clave", "metrica"]).agg(
            z=("z", "mean"), sd=("z", "std"), personas=("persona_v5", "nunique")).reset_index()
        g = g[g["personas"] >= 15]
        g["dz"] = g["z"] - g["metrica"].map(ref)
        g["se"] = g["sd"] / np.sqrt(g["personas"])
        # contracción a través del perfil latente, como en contraer()
        g = g.rename(columns={"clave": "grupo", "dz": "delta"}).assign(delta_escala=np.nan)
        g = contraer(g)[["fase", "grupo", "metrica", "delta_lat"]].rename(columns={"grupo": "clave", "delta_lat": "dz"})
        t = te.merge(g, on=["fase", "clave", "metrica"], how="inner")
        if t.empty:
            continue
        t = t.assign(wis_base=LD._wis(t["obs"], t[qs]), wis_delta=LD._wis(t["obs"], t[qs].add(t["dz"] * t["semi"], axis=0)),
                     anio_prueba=T)
        filas.append(t)
    x = pd.concat(filas, ignore_index=True)
    out = []
    for (fase, clave), g in x.groupby(["fase", "clave"]):
        r, lo, hi = VF._boot_ratio(g["persona_v5"].to_numpy(), g["wis_delta"].to_numpy(float),
                                   g["wis_base"].to_numpy(float), cfg_l["bootstrap"], rng)
        out.append({"fase": fase, "grupo": clave, "casos": len(g), "personas": g["persona_v5"].nunique(),
                    "anios_prueba": ",".join(str(a) for a in sorted(g["anio_prueba"].unique())),
                    "wis_con_delta_frente_sin": r, "ic_lo": lo, "ic_hi": hi, "publicar": bool(hi < 0)})
    return pd.DataFrame(out)


def escalon_nk(cfg: dict, t: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Escalón de la Landing en puntos de NK (F3): NK con pts/100 + δ₂ del grupo menos NK del primer año, y su contraste
    con el percentil realizado en la segunda temporada (misma liga de destino)."""
    from bbnorm5.aguas_abajo import nivel_kerno as NK10
    out = PR.dir_salida(cfg)
    k = pd.read_csv(out / "nivel_kerno_examen.csv.gz", low_memory=False, dtype={"team_d": str})
    # en el examen de la F3, «anio» es el año del corte; el banco usa el de la temporada de destino
    k["anio_dest"] = k["corte"].str[:4].astype(int) + 1
    b = PR.banco(cfg)[["persona_v5", "anio", "liga_d", "team_d", "liga_o"]].drop_duplicates(["persona_v5", "anio", "liga_d", "team_d"])
    b = b.rename(columns={"anio": "anio_dest"})
    b["team_d"] = b["team_d"].astype(str)
    k = k.merge(b, on=["persona_v5", "anio_dest", "liga_d", "team_d"], how="left")
    nac = k["persona_v5"].map(LD.nacionalidades())
    k["grupo"] = LD.grupos(k["liga_o"].fillna(""), k["liga_d"], nac)
    d2 = t[(t["fase"] == "segunda") & (t["metrica"] == "pts_p100")].set_index("grupo")["delta_lat_escala"]
    k["delta2_pts"] = k["grupo"].map(d2).fillna(0.0)
    k.loc[~k["grupo"].isin(d2.index), "delta2_pts"] = 0.0
    # contribución del segundo año ≈ C · (1 + δ₂ / pts/100 del primero): NK crudo desplazado con la misma F_ref
    AN, cfg_eq, roles, gm = NK10._referencias()
    filas = []
    for corte, g in k.groupby("corte"):
        F = AN.referencias_nc(cfg_eq, roles, corte, gm)
        t1 = g["temporada_d"].iloc[0]
        t2 = f"{int(t1[:4]) + 1}-{str(int(t1[:4]) + 2)[-2:]}"
        F2 = AN.referencias_nc(cfg_eq, roles, t1, gm)
        r2 = roles[(roles["temporada"] == t2) & (roles["min_total"] >= 300)].copy()
        r2["C2"] = AN.contribucion_realizada(r2, gm)
        r2 = r2.sort_values("min_total", ascending=False).drop_duplicates(["persona_id", "liga"])
        for r in g.itertuples():
            Fr = F.get((r.liga_d, r.pos3)) or F.get((r.liga_d, None))
            F2r = F2.get((r.liga_d, r.pos3)) or F2.get((r.liga_d, None))
            if Fr is None or F2r is None:
                continue
            # NK crudo del primer año → C equivalente en F_ref; el segundo año, con pts/100 + δ₂ (desplazamiento
            # proporcional de C, con los mismos minutos)
            c1 = float(np.interp(r.NK51_crudo / 100, Fr.F, Fr.x)) if Fr.n else np.nan
            f = 1 + r.delta2_pts / max(float(r.pc_q50), 1e-6)
            esc = 100 * float(Fr(np.asarray([c1 * f]))[0]) if np.isfinite(c1) else np.nan
            esc = esc - 100 * float(Fr(np.asarray([c1]))[0]) + r.NK51_crudo if np.isfinite(esc) else np.nan
            x2 = r2[(r2["persona_id"] == r.persona_id) & (r2["liga"] == r.liga_d)]
            pct2 = float(100 * F2r(x2["C2"].iloc[0])) if len(x2) else np.nan
            filas.append({"i": r.Index, "NK_anio2_crudo": esc, "pct_realizado_2": pct2})
    k = k.join(pd.DataFrame(filas).set_index("i"))
    k["escalon_crudo"] = k["NK_anio2_crudo"] - k["NK51_crudo"]
    res = {"escalon_por_grupo": k.groupby("grupo").agg(fichajes=("escalon_crudo", "size"),
                                                       delta2_pts=("delta2_pts", "mean"),
                                                       escalon_medio=("escalon_crudo", "mean")).round(3).to_dict("index")}
    v = k.dropna(subset=["pct_realizado_2"])
    v = v.assign(cambio_real=v["pct_realizado_2"] - v["pct_realizado"])
    res["segundo_anio"] = v.groupby("grupo").agg(fichajes=("cambio_real", "size"), cambio_realizado=("cambio_real", "mean"),
                                                 escalon_previsto=("escalon_crudo", "mean")).round(2).to_dict("index")
    res["spearman_segundo_anio"] = {
        "NK51": float(stats.spearmanr(v["NK51"], v["pct_realizado_2"]).statistic) if len(v) > 10 else np.nan,
        "fichajes": int(len(v))}
    return k, res


def ejecutar(cfg: dict) -> dict:
    out = (C.DIR_DATOS.parent / "v5_1" / "landing")
    out.mkdir(parents=True, exist_ok=True)
    cfg_l = C.cargar("configs/v5/f10.yaml")
    d = LD.residuos(cfg_l)
    t = LD.estimar(cfg_l, d)
    t = contraer(t)
    ex = examen_contraido(cfg_l, d)
    k, esc = escalon_nk(cfg, t)
    t.to_csv(out / "landing_delta_contraido.csv", index=False)
    ex.to_csv(out / "landing_examen_contraido.csv", index=False)
    k[["persona_v5", "anio", "corte", "liga_o", "liga_d", "grupo", "NK51", "NK51_crudo", "NK_anio2_crudo", "escalon_crudo",
       "delta2_pts", "pct_realizado", "pct_realizado_2"]].round(3).to_csv(out / "landing_escalon_nk.csv.gz", index=False)
    eeuu = t[t["grupo"].isin(["EEUU_a_Europa"])][["fase", "metrica", "personas", "delta", "ic_lo", "ic_hi", "delta_lat",
                                                  "ic_lo_lat", "ic_hi_lat", "delta_escala", "delta_lat_escala"]]
    res = {"identificables_directo": int(((t["ic_hi"] - t["ic_lo"]) / 2 <= 0.10).sum()),
           "identificables_contraido": int(((t["ic_hi_lat"] - t["ic_lo_lat"]) / 2 <= 0.10).sum()),
           "celdas": int(len(t)), "examen": ex.round(4).to_dict("records"), **esc,
           "eeuu_a_europa": eeuu.round(3).to_dict("records")}
    C.escribir_json({**C.metadatos(cfg), **res}, out / "meta_landing.json")
    return {k_: v for k_, v in res.items() if k_ != "eeuu_a_europa"}
