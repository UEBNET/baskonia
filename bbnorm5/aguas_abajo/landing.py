"""F10 · Landing: efecto de la primera temporada en una liga nueva (δ), por métrica y grupo de origen-destino.

Idea (encargo §14.4). La proyección de la v5 para la temporada t+1 de quien cambia de liga es

    η̂ = μ_rol(destino) + nivel de carrera + Δλ(origen → destino)

Si existe una adaptación, el observado de la primera temporada queda sistemáticamente por debajo (o por encima) de η̂:

    η_obs − η̂ = δ_grupo + ruido.

**Identificación.** Δλ tiene que venir sólo de los puentes de la misma temporada (paso 1 de la F6): el paso 2 se estima
con los propios traspasos y absorbería δ (sería circular). Se compara con los jugadores que no cambian de liga en la
misma liga de destino y temporada, para quitar el sesgo medio del modelo en cada liga-temporada.

**Pasajero o permanente.** Si δ es adaptación, la segunda temporada en la liga nueva vuelve a la línea (o la supera,
porque el nivel de carrera ya incorpora parte de la primera temporada baja). Si δ es un cambio de papel o un error de
traducción, persiste.

Unidades: DT del residuo (η_obs − η̂ dividido por su DT predictiva sin contexto) y la escala de la métrica en el punto
medio de los casos.

**Grupos** (F10 bis): los de la Landing vigente (`bbfit.adaptacion.grupo_nacionalidad`, configs/adaptacion.yaml), con la
nacionalidad unida por persona (v3.2 normalizada de todas las temporadas y crosswalk): NCAA_a_profesional,
EEUU_a_Europa, otro_desde_EEUU, hacia_EEUU, intra_EEUU, nacional_mismo_pais, extranjero_mismo_pais,
europeo_cambia_liga, extranjero_cambia_pais y desconocido. (La primera versión de la F10 usaba los grupos de la
recalibración, en los que «europa» incluía llegadas desde la NCAA, la CBA y la NBL: corregido.)

**Traducción publicada.** Además del residuo con la traducción del paso 1 (δ total), se mide con la del paso 2 (la
publicada): como el flujo EE. UU. → Europa va casi siempre en un sentido, el paso 2 absorbe la caída media del primer año;
el residuo con la publicada dice si la proyección actual ya la recoge.

**Examen de publicación** (`examen_publicacion`): δ estimado con las temporadas anteriores, aplicado como
desplazamiento a la proyección publicada (ex ante, recalibrada) de la temporada siguiente; se publica sólo si baja el WIS
con IC que no cruza 0 (la misma regla que el estilo de liga, criterio 11).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from bbnorm5 import config as C
from bbnorm5.ligas import contexto as LC
from bbnorm5.medida import datos as DM
from bbnorm5.validacion import fichajes as VF

ENTRADA = C.DIR_DATOS / "ligas" / "seleccion_base.parquet"
PUBLICADA = C.DIR_DATOS / "validacion" / "base_v5.parquet"        # mismas transiciones con la traducción del paso 2
PERSONAS = C.DIR_DATOS / "limpios" / "entidades" / "personas_v5.csv"
V32 = C.RAIZ / "data" / "modelos" / "v3_2" / "normalizado"
CROSSWALK = C.RAIZ / "data" / "processed" / "player_id_crosswalk.csv"


def nacionalidades() -> pd.Series:
    """Nacionalidad por persona v5: la más frecuente entre la v3.2 normalizada (todas las temporadas) y el crosswalk."""
    per = pd.read_csv(PERSONAS, dtype=str)[["fuente_liga", "fuente_id", "persona_v5"]].drop_duplicates(
        ["fuente_liga", "fuente_id"])
    partes = []
    for f in sorted(V32.glob("20*.csv.gz")):
        v = pd.read_csv(f, usecols=["liga", "player_id", "nacionalidad"], dtype=str)
        partes.append(v.rename(columns={"liga": "fuente_liga", "player_id": "fuente_id"}))
    cw = pd.read_csv(CROSSWALK, dtype=str, usecols=["fuente_liga", "fuente_id", "nacionalidad_iso"])
    partes.append(cw.rename(columns={"nacionalidad_iso": "nacionalidad"}))
    n = pd.concat(partes).dropna(subset=["nacionalidad"]).merge(per, on=["fuente_liga", "fuente_id"])
    return n.groupby("persona_v5")["nacionalidad"].agg(lambda s: s.mode().iloc[0])


def grupos(liga_o: pd.Series, liga_d: pd.Series, nac: pd.Series) -> np.ndarray:
    """Grupo de traspaso de la Landing vigente para cada fila (sólo lectura de bbfit.adaptacion)."""
    from bbfit.adaptacion import grupo_nacionalidad
    clave = pd.DataFrame({"o": liga_o.astype(str).to_numpy(), "d": liga_d.astype(str).to_numpy(),
                          "n": nac.to_numpy(object)})
    u = clave.drop_duplicates()
    u["g"] = [grupo_nacionalidad(None if (isinstance(n, float) or n is None) else n, o, d)
              for o, d, n in zip(u["o"], u["d"], u["n"])]
    return clave.merge(u, on=["o", "d", "n"], how="left")["g"].to_numpy()
# escala publicada (como la v3.2): porcentajes y tasas por 100; faltas por 40 minutos
UNIDAD = {"pf_p40": 40.0}


def residuos(cfg: dict, x: pd.DataFrame | None = None) -> pd.DataFrame:
    """Residuo de cada transición con la traducción del paso 1, ajustado por el de quienes no cambian de liga en la
    misma liga de destino, temporada y métrica."""
    x = pd.read_parquet(ENTRADA) if x is None else x
    L = cfg["landing"]
    partes = []
    for m, g in x.groupby("metrica", sort=True):
        fam = DM.METRICAS[m][0]
        eta, vo = LC.observacion(g, fam)
        pred = (g["mu_prev"] + g["m_nivel"] + g["ajuste_liga"]).to_numpy(float)
        v = np.asarray(vo, float) + (g["v_y_sin_muestreo"] + g["var_lambda"]).to_numpy(float)
        # derivada de la escala publicada respecto de η en la predicción (δ en DT → δ en la escala de la métrica)
        if fam == "binomial":
            p = 1 / (1 + np.exp(-pred))
            deriv = p * (1 - p)
        elif fam == "poisson":
            deriv = np.exp(pred)
        else:
            deriv = np.ones(len(g))
        deriv = deriv * UNIDAD.get(m, 100.0)
        partes.append(g[["persona_v5", "anio_obj", "anio_ult", "liga", "liga_ult", "cl", "min_temp", "var_lambda"]]
                      .assign(metrica=m, e=eta - pred, v=v, deriv=deriv))
    d = pd.concat(partes, ignore_index=True)
    # residuo con la traducción publicada (paso 2), mismas transiciones
    pub = pd.read_parquet(PUBLICADA, columns=["persona_v5", "anio_obj", "liga", "metrica", "ajuste_liga", "var_lambda"])
    pub = pub.drop_duplicates(["persona_v5", "anio_obj", "liga", "metrica"]).rename(
        columns={"ajuste_liga": "ajuste_pub", "var_lambda": "var_lambda_pub"})
    aj1 = x[["persona_v5", "anio_obj", "liga", "metrica", "ajuste_liga"]].drop_duplicates(
        ["persona_v5", "anio_obj", "liga", "metrica"])
    d = d.merge(aj1, on=["persona_v5", "anio_obj", "liga", "metrica"], how="left").merge(
        pub, on=["persona_v5", "anio_obj", "liga", "metrica"], how="left")
    d = d[np.isfinite(d["e"]) & np.isfinite(d["v"]) & (d["v"] > 0) & (d["min_temp"] >= L["min_minutos"])].copy()
    d["r"] = d["e"] / np.sqrt(d["v"])
    vp = d["v"] - d["var_lambda"] + d["var_lambda_pub"].fillna(d["var_lambda"])
    d["r_pub"] = (d["e"] + d["ajuste_liga"] - d["ajuste_pub"].fillna(d["ajuste_liga"])) / np.sqrt(vp)
    nac = d["persona_v5"].map(nacionalidades())
    d["nacionalidad"] = nac
    d["grupo"] = np.where(d["cl"] > 0, grupos(d["liga_ult"], d["liga"], nac), "misma_liga")
    # ¿la temporada de origen fue la primera en su liga? (el caso anterior de la misma persona cambió de liga)
    prev = (d[["persona_v5", "metrica", "anio_obj", "cl", "liga_ult", "liga"]]
            .rename(columns={"anio_obj": "anio_ult", "cl": "cl_prev", "liga_ult": "liga_prev_o", "liga": "liga_prev_d"}))
    d = d.merge(prev, on=["persona_v5", "metrica", "anio_ult"], how="left")
    d["fase"] = np.where(d["cl"] > 0, "primera", np.where(d["cl_prev"] > 0, "segunda", "estable"))
    seg = d["fase"] == "segunda"
    d["grupo_prev"] = ""
    d.loc[seg, "grupo_prev"] = grupos(d.loc[seg, "liga_prev_o"].fillna(""), d.loc[seg, "liga_prev_d"].fillna(""),
                                      d.loc[seg, "nacionalidad"])
    # referencia: media de quienes no cambian (ni cambiaron el año anterior) en la misma liga, temporada y métrica
    ref = d[d["fase"] == "estable"].groupby(["metrica", "liga", "anio_obj"])[["r", "r_pub"]].mean()
    d = d.join(ref.rename(columns={"r": "r_ref", "r_pub": "r_ref_pub"}), on=["metrica", "liga", "anio_obj"])
    d["r_adj"] = d["r"] - d["r_ref"]
    d["r_adj_pub"] = d["r_pub"] - d["r_ref_pub"]
    return d[np.isfinite(d["r_adj"])]


def _boot_media(personas: np.ndarray, y: np.ndarray, B: int, rng) -> tuple[float, float]:
    """Media de y y su DT por bootstrap de personas (cada persona pesa por sus filas)."""
    u, inv = np.unique(personas, return_inverse=True)
    s, n = np.bincount(inv, y), np.bincount(inv).astype(float)
    w = rng.multinomial(len(u), np.full(len(u), 1 / len(u)), size=B).astype(float)
    medias = (w @ s) / (w @ n)
    return float(s.sum() / n.sum()), float(np.std(medias, ddof=1))


def _eb(d: np.ndarray, se: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Contracción hacia la media de los grupos (DerSimonian-Laird): devuelve δ contraída, media y τ."""
    w = 1 / se ** 2
    mu = float(np.sum(w * d) / np.sum(w))
    q = float(np.sum(w * (d - mu) ** 2))
    tau2 = max(0.0, (q - (len(d) - 1)) / (np.sum(w) - np.sum(w ** 2) / np.sum(w))) if len(d) > 1 else 0.0
    b = tau2 / (tau2 + se ** 2) if tau2 > 0 else np.zeros_like(se)
    return mu + b * (d - mu), mu, float(np.sqrt(tau2))


def estimar(cfg: dict, d: pd.DataFrame) -> pd.DataFrame:
    """δ (primera temporada) y su persistencia (segunda temporada) por métrica y grupo, con IC por bootstrap de
    personas más la incertidumbre de la traducción del paso 1 (común a los traspasos del mismo par de ligas)."""
    L, B = cfg["landing"], cfg["bootstrap"]
    rng = np.random.default_rng(cfg["semilla"])
    filas = []
    for (m, fase), gm in d[d["fase"] != "estable"].groupby(["metrica", "fase"]):
        col = "grupo" if fase == "primera" else "grupo_prev"
        for gr, g in list(gm.groupby(col)) + [("todos", gm)]:
            if gr in ("misma_liga", ""):
                continue
            delta, se_b = _boot_media(g["persona_v5"].to_numpy(), g["r_adj"].to_numpy(float), B, rng)
            # traducción: el error de Δλ es común a todas las filas del mismo par → no se promedia
            se_l = 0.0
            if fase == "primera":
                par = g.groupby(["liga_ult", "liga"]).agg(n=("r", "size"), vl=("var_lambda", "mean"), v=("v", "mean"))
                se_l = float(np.sqrt(np.sum((par["n"] / par["n"].sum()) ** 2 * par["vl"] / par["v"])))
            se = float(np.hypot(se_b, se_l))
            # con la traducción publicada (paso 2): ¿la proyección actual ya recoge la caída?
            dpub, se_pub = _boot_media(g["persona_v5"].to_numpy(), g["r_adj_pub"].fillna(g["r_adj"]).to_numpy(float),
                                       B, rng)
            filas.append({"metrica": m, "fase": fase, "grupo": gr, "personas": g["persona_v5"].nunique(),
                          "delta_publicada": dpub, "se_publicada": se_pub,
                          "filas": len(g), "delta": delta, "se_bootstrap": se_b, "se_traduccion": se_l, "se": se,
                          "ic_lo": delta - 1.96 * se, "ic_hi": delta + 1.96 * se,
                          "delta_escala": delta * float(np.median(np.sqrt(g["v"]) * g["deriv"])),
                          "familia": DM.METRICAS[m][0]})
    t = pd.DataFrame(filas)
    # contracción entre grupos dentro de cada métrica y fase (sin el agregado «todos»)
    t["delta_eb"], t["media_grupos"], t["tau"] = np.nan, np.nan, np.nan
    for (m, fase), idx in t[t["grupo"] != "todos"].groupby(["metrica", "fase"]).groups.items():
        e, mu, tau = _eb(t.loc[idx, "delta"].to_numpy(float), t.loc[idx, "se"].to_numpy(float))
        t.loc[idx, "delta_eb"], t.loc[idx, "media_grupos"], t.loc[idx, "tau"] = e, mu, tau
    ic = (t["ic_hi"] - t["ic_lo"]) / 2
    t["identificable"] = (t["personas"] >= L["identificable"]["min_personas"]) & (ic <= L["identificable"]["semiancho_ic95"])
    t["relevante"] = (t["delta"].abs() >= L["relevante"]) & ((t["ic_lo"] > 0) | (t["ic_hi"] < 0))
    return t


def persistencia(t: pd.DataFrame) -> pd.DataFrame:
    """Primera frente a segunda temporada (mismo grupo del cambio): ¿vuelve hacia 0?"""
    a = t[t["fase"] == "primera"].set_index(["metrica", "grupo"])
    b = t[t["fase"] == "segunda"].set_index(["metrica", "grupo"])
    j = a[["delta", "se", "relevante"]].join(b[["delta", "se", "personas"]], rsuffix="_2", how="inner")
    j["recupera"] = np.sign(j["delta"]) * j["delta_2"]          # < 0: la segunda va en sentido contrario (vuelve)
    j["persiste"] = j["relevante"] & (np.sign(j["delta_2"]) == np.sign(j["delta"])) & \
        (np.abs(j["delta_2"]) > 1.96 * j["se_2"])
    j["pasajero"] = j["relevante"] & (np.abs(j["delta_2"] - j["delta"]) > 1.96 * np.hypot(j["se"], j["se_2"])) & \
        ~j["persiste"]
    return j.reset_index()


def _wis(y, q: pd.DataFrame) -> np.ndarray:
    return VF.wis(y, q["q50"], {50: q["q25"], 80: q["q10"], 90: q["q5"]}, {50: q["q75"], 80: q["q90"], 90: q["q95"]})


def examen_publicacion(cfg: dict, d: pd.DataFrame) -> pd.DataFrame:
    """¿Publicar δ mejora la proyección publicada de la temporada siguiente? δ por métrica y grupo estimado con las
    temporadas anteriores (en unidades del semiancho del 80 % de la proyección, frente a quienes no cambian) y aplicado
    como desplazamiento. Primera temporada (grupo del cambio) y segunda (grupo del cambio anterior: recuperación)."""
    from bbnorm5.validacion import recalibracion as VR
    L, B = cfg["landing"], cfg["bootstrap"]
    rng = np.random.default_rng(cfg["semilla"] + 31)
    p, _ = VR.recalibradas(C.cargar("configs/v5/f8.yaml"))
    qs = ["q5", "q10", "q25", "q50", "q75", "q90", "q95"]
    p = p[["persona_v5", "anio", "liga", "metrica", "obs"] + qs].dropna()
    k = d[["persona_v5", "anio_obj", "liga", "metrica", "fase", "grupo", "grupo_prev"]].rename(columns={"anio_obj": "anio"})
    p = p.merge(k.drop_duplicates(["persona_v5", "anio", "liga", "metrica"]), on=["persona_v5", "anio", "liga", "metrica"])
    p["clave"] = np.where(p["fase"] == "primera", p["grupo"], np.where(p["fase"] == "segunda", p["grupo_prev"], ""))
    # grupos agrupados para el examen (más casos): p. ej. todas las llegadas profesionales de EE. UU. a Europa
    for nuevo, viejos in (L.get("grupos_agrupados") or {}).items():
        sel = p["clave"].isin(viejos)
        p = pd.concat([p, p[sel].assign(clave=nuevo)], ignore_index=True)
    # semiancho del 80 % con suelo por métrica (cuantiles discretos en sucesos raros: anchura 0) y z recortada
    semi = (p["q90"] - p["q10"]) / 2
    suelo = p.assign(s=semi).loc[semi > 0].groupby("metrica")["s"].quantile(0.05)
    p["semi"] = np.maximum(semi, p["metrica"].map(suelo))
    p["z"] = ((p["obs"] - p["q50"]) / p["semi"]).clip(-4, 4)
    filas = []
    for T in sorted(p["anio"].unique()):
        cal, te = p[p["anio"] < T], p[p["anio"] == T]
        if cal.empty:
            continue
        ref = cal[cal["fase"] == "estable"].groupby("metrica")["z"].mean()
        dz = (cal[cal["fase"] != "estable"].groupby(["fase", "clave", "metrica"])
              .agg(z=("z", "mean"), personas=("persona_v5", "nunique")))
        dz = dz[dz["personas"] >= L["examen_min_personas"]].reset_index()
        dz["dz"] = dz["z"] - dz["metrica"].map(ref)
        t = te.merge(dz[["fase", "clave", "metrica", "dz"]], on=["fase", "clave", "metrica"], how="inner")
        if t.empty:
            continue
        s = t["semi"]
        t = t.assign(wis_base=_wis(t["obs"], t[qs]), wis_delta=_wis(t["obs"], t[qs].add(t["dz"] * s, axis=0)),
                     anio_prueba=T)
        filas.append(t)
    x = pd.concat(filas, ignore_index=True)
    out = []
    for (fase, clave), g in x.groupby(["fase", "clave"]):
        r, lo, hi = VF._boot_ratio(g["persona_v5"].to_numpy(), g["wis_delta"].to_numpy(float),
                                   g["wis_base"].to_numpy(float), B, rng)
        out.append({"fase": fase, "grupo": clave, "casos": len(g), "personas": g["persona_v5"].nunique(),
                    "anios_prueba": ",".join(str(a) for a in sorted(g["anio_prueba"].unique())),
                    "metricas": g["metrica"].nunique(), "wis_con_delta_frente_sin": r, "ic_lo": lo, "ic_hi": hi,
                    "publicar": bool(hi < 0)})
    return pd.DataFrame(out)


def ejecutar(cfg: dict) -> dict:
    out_dir = C.dir_fase(cfg)
    d = residuos(cfg)
    t = estimar(cfg, d)
    p = persistencia(t)
    ex = examen_publicacion(cfg, d)
    t.to_csv(out_dir / "landing_delta.csv", index=False)
    p.to_csv(out_dir / "landing_persistencia.csv", index=False)
    ex.to_csv(out_dir / "landing_examen_publicacion.csv", index=False)
    pr = t[(t["fase"] == "primera") & (t["grupo"] != "todos")]
    res = {"transiciones": int(len(d)), "primera": int((d["fase"] == "primera").sum()),
           "segunda": int((d["fase"] == "segunda").sum()),
           "celdas": int(len(pr)), "identificables": int(pr["identificable"].sum()),
           "relevantes": int(pr["relevante"].sum()),
           "persisten": int(p["persiste"].sum()), "pasajeros": int(p["pasajero"].sum()),
           "media_abs_delta": float(pr["delta"].abs().mean()),
           "semiancho_ic_mediano": float(((pr["ic_hi"] - pr["ic_lo"]) / 2).median()),
           "examen_publicacion": ex.round(4).to_dict("records")}
    C.escribir_json({**C.metadatos(cfg, [ENTRADA]), **res}, out_dir / "meta_landing.json")
    return res
