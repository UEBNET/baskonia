"""F1 · Pasos §5.1 (división de muestra), §5.2, §5.3 y §5.4. Llamados desde `python -m bbnorm5.f1 <paso>`.

Escalas. Para comparar métricas entre sí todo se expresa en la escala estandarizada de la v3.2 (z = (T(x) − c_m)/s_m,
la de `real_z` en los casos del examen) o en DT de capacidad (θ, vara EuroLeague) según el paso; se indica en cada
salida.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy.stats import norm

from bbnorm5 import config as C

Z = {0.5: norm.ppf(0.75), 0.8: norm.ppf(0.9), 0.95: norm.ppf(0.975)}


# ================================================================================================ utilidades de calibración
def crps_normal(y, mu, sd):
    """CRPS de una normal N(mu, sd²) en y (forma cerrada; Gneiting y Raftery 2007)."""
    z = (y - mu) / sd
    return sd * (z * (2 * norm.cdf(z) - 1) + 2 * norm.pdf(z) - 1 / np.sqrt(np.pi))


def medidas(y, mu, sd=None) -> dict:
    y, mu = np.asarray(y, float), np.asarray(mu, float)
    e = y - mu
    out = {"n": int(len(y)), "mae": float(np.mean(np.abs(e))), "rmse": float(np.sqrt(np.mean(e ** 2))),
           "sesgo": float(np.mean(e))}
    if sd is not None:
        sd = np.asarray(sd, float)
        z = e / sd
        for p, q in Z.items():
            out[f"cob{int(p * 100)}"] = float(np.mean(np.abs(z) <= q))
        out["crps"] = float(np.mean(crps_normal(y, mu, sd)))
        out["sd_mediana"] = float(np.median(sd))
        out["pit_ks"] = float(np.max(np.abs(np.sort(norm.cdf(z)) - (np.arange(1, len(z) + 1) - 0.5) / len(z))))
    else:
        out["crps"] = out["mae"]          # una predicción puntual es una distribución degenerada: CRPS = MAE
    return out


def diagnostico_cobertura(c80: float) -> str:
    """Regla obligatoria del encargo §5.3."""
    if not np.isfinite(c80):
        return "—"
    return "infraconfiado" if c80 > 0.88 else "sobreconfiado" if c80 < 0.72 else "en rango"


# ======================================================================================================== §5.1 división
def paso_division(cfg: dict) -> pd.DataFrame:
    from bbnorm5.diagnostico import division
    d = division.cargar(cfg["datos"]["temporadas"], C.RAIZ)
    m = division.mitades(d, int(cfg["division_muestra"]["min_partidos"]))
    filas = [division.estimar(m, col) for col in division.DEF]
    out = pd.DataFrame(filas)
    sal = C.dir_fase(cfg) / "varianza"
    out.to_csv(sal / "division_muestra.csv", index=False)
    entradas = [C.RAIZ / "data" / "modelos" / "roles" / "partidos_jugador" / f"{t}.csv.gz" for t in cfg["datos"]["temporadas"]]
    C.escribir_json(C.metadatos(cfg, entradas, {"paso": "division"}), sal / "division_meta.json")
    print(out[["metrica", "jugadores_temporada", "r_mitades", "rho_spearman_brown", "n_estab_clasico",
               "n_estab_momentos", "unidad_exposicion"]].round(3).to_string())
    return out


# ================================================================================================= §5.2 incertidumbre
def paso_incertidumbre(cfg: dict) -> pd.DataFrame:
    """Varianza de la traducción de un jugador de su liga o a la liga d, en DT de capacidad de d (z_d):
        jugador     v_j / s_d²                         (incertidumbre propia del nivel del jugador, v3.2)
        traducción  Var(δ_o − δ_d) / s_d²               (nivel relativo de las dos ligas, covarianza conjunta)
        temporada   ψ_d + σ²_d/(n τ²_{d,pos}) + η²/s_d²  (contexto, ruido de muestra y cambio real a t+1)
    Las dos primeras forman el intervalo de NIVEL; las tres, el PREDICTIVO de la temporada siguiente (el del motor del
    simulador, bbfit/simulador.py). SUPUESTO: exposición en destino = la del jugador en origen."""
    from bbmodel.metricas import CATALOGO
    from bbnorm3.destino import sd_par_matriz
    from bbnorm5.diagnostico import datos_f1
    temp = "2025-26"
    dd = C.RAIZ / cfg["v32"]["destino"]
    const = json.loads((dd / "constantes.json").read_text(encoding="utf-8"))["metricas"]
    A = json.loads((C.RAIZ / "data" / "modelos" / "algoritmo_A" / "parametros.json").read_text(encoding="utf-8"))["metricas"]
    cap = pd.read_csv(dd / "capacidad" / f"{temp}.csv.gz", low_memory=False)
    t, _ = datos_f1.tabla(cfg)
    t = t[t["temporada"] == temp]
    cap = cap[cap["min"] >= 300].copy()
    cap["player_id"] = cap["player_id"].astype(str)
    t = t.assign(player_id=t["player_id"].astype(str))
    filas = []
    for col, k in const.items():
        if col not in CATALOGO or f"{col}_vj" not in cap:
            continue
        expo = __import__("bbmodel.metricas", fromlist=["EXPOSICIONES"]).EXPOSICIONES[CATALOGO[col].exposicion]
        x = cap[["liga", "player_id", "pos3", f"{col}_vj"]].merge(
            t[["liga", "player_id", expo]], on=["liga", "player_id"], how="left").dropna()
        x = x[x[expo] > 0]
        cv = json.loads((dd / "covarianza" / f"{col}.json").read_text(encoding="utf-8"))
        T = sd_par_matriz(cv)
        ix = {n: i for i, n in enumerate(cv["nodos"])}
        s2 = A[col]["suerte"]["sigma2"]
        ligas = sorted(set(x["liga"]) & set(k["s"]) | {"euroleague"})
        for lo in sorted(set(x["liga"])):
            xo = x[x["liga"] == lo]
            if len(xo) < 20 or f"{lo}:{temp}" not in ix:
                continue
            for ld in ligas:
                if f"{ld}:{temp}" not in ix:
                    continue
                sd_ = 1.0 if ld == "euroleague" else float(k["s"].get(ld, np.nan))
                vpar = 0.0 if lo == ld else float(T[ix[f"{lo}:{temp}"], ix[f"{ld}:{temp}"]]) ** 2
                tau2 = xo["pos3"].map(lambda p: k["tau2"].get(f"{ld}|{p}", np.nan)).to_numpy(float)
                jug = xo[f"{col}_vj"].to_numpy(float) / sd_ ** 2
                tra = np.full(len(xo), vpar / sd_ ** 2)
                tem = float(k["psi"].get(ld, np.nan)) + s2.get(ld, s2.get("todas", np.nan)) / (xo[expo].to_numpy(float) * tau2) \
                    + float(k.get("eta2", 0.0)) / sd_ ** 2
                tot = jug + tra + tem
                filas.append({"metrica": col, "liga_o": lo, "liga_d": ld, "n_jugadores": len(xo),
                              "frac_jugador": float(np.median(jug / tot)), "frac_traduccion": float(np.median(tra / tot)),
                              "frac_temporada": float(np.median(tem / tot)),
                              "sd_nivel": float(np.median(np.sqrt(jug + tra))), "sd_predictivo": float(np.median(np.sqrt(tot))),
                              "razon_predictivo_nivel": float(np.median(np.sqrt(tot / (jug + tra))))})
    out = pd.DataFrame(filas)
    sal = C.dir_fase(cfg) / "incertidumbre"
    sal.mkdir(parents=True, exist_ok=True)
    out.to_csv(sal / "descomposicion_pares.csv.gz", index=False)
    res = out.groupby("metrica")[["frac_jugador", "frac_traduccion", "frac_temporada", "sd_nivel", "sd_predictivo",
                                  "razon_predictivo_nivel"]].median()
    res_el = out[out["liga_d"] == "euroleague"].groupby("metrica")[["frac_jugador", "frac_traduccion", "frac_temporada"]].median()
    res = res.join(res_el.add_suffix("_a_el"))
    res.to_csv(sal / "descomposicion_metrica.csv")
    C.escribir_json(C.metadatos(cfg, [dd / "constantes.json", dd / "capacidad" / f"{temp}.csv.gz"],
                                {"paso": "incertidumbre", "temporada": temp,
                                 "supuesto": "exposición en destino = exposición en origen"}), sal / "meta.json")
    print(res.round(3).to_string())
    return out


# ================================================================================================== §5.3 calibración
def _escala_metrica(c: pd.DataFrame) -> dict:
    """(c_m, s_m) de la estandarización de la v3.2, recuperados exactamente de real_z = (T(real) − c)/s."""
    from bbmodel.metricas import CATALOGO, transformar
    out = {}
    for m, g in c.groupby("metrica"):
        x = transformar(g["real"].to_numpy(float), CATALOGO[m].transf)
        ok = np.isfinite(x) & np.isfinite(g["real_z"].to_numpy(float))
        a, b = np.polyfit(x[ok], g["real_z"].to_numpy(float)[ok], 1)      # real_z = a·T + b → s = 1/a, c = −b/a
        out[m] = (-b / a, 1 / a)
    return out


def _z(c: pd.DataFrame, col: str, esc: dict) -> np.ndarray:
    from bbmodel.metricas import CATALOGO, transformar
    out = np.full(len(c), np.nan)
    for m, idx in c.groupby("metrica").groups.items():
        cm, sm = esc[m]
        out[c.index.get_indexer(idx)] = (transformar(c.loc[idx, col].to_numpy(float), CATALOGO[m].transf) - cm) / sm
    return out


def casos_movimientos(cfg: dict) -> pd.DataFrame:
    """Examen fuera de tiempo de la v3.2 (cambios de liga t → t+1, ≥ 300 min en ambas, cortes anidados 2022–2024),
    con todas las variantes en la misma escala z. Fuente: casos_combinada_v32.csv.gz (ya calculado; no se reentrena)."""
    c = pd.read_csv(C.RAIZ / cfg["v32"]["casos"], low_memory=False)
    c = c[c["anio"].isin(cfg["calibracion"]["cortes"])].reset_index(drop=True)
    esc = _escala_metrica(c)
    for col in ("mismo_percentil", "algoritmo_A", "am"):
        c[f"{col}_z"] = _z(c, col, esc)
    return c


MODELOS_MOV = {   # nombre → (centro, sd) en z; sd None = sólo punto
    "v3.2 publicada (predictiva recalibrada)": ("v3_centro_z", "sd_v32c"),
    "v3.2 sin recalibrar": ("v3_centro_z", "v3_sd_z"),
    "CVAE sola": ("cvae_centro_z", "cvae_sd_z"),
    "v2 = A+B amortiguado (intervalo F0, de nivel)": ("v2_centro_z", "v2_sd_z"),
    "v1 algoritmo A (punto)": ("algoritmo_A_z", None),
    "mismo percentil (punto)": ("mismo_percentil_z", None),
}


def _tramo(x, cortes):
    b = [-np.inf] + list(cortes) + [np.inf]
    et = [f"<{cortes[0]}"] + [f"{a}-{b_}" for a, b_ in zip(cortes[:-1], cortes[1:])] + [f"≥{cortes[-1]}"]
    return pd.cut(x, b, labels=et, right=False).astype(str)


def calibracion_movimientos(cfg: dict) -> pd.DataFrame:
    c = casos_movimientos(cfg)
    c["sd_v32c"] = c["v3_sd_z"] * c["kappa"]
    c["tramo_min_d"] = _tramo(c["min_d"].to_numpy(float), cfg["calibracion"]["tramos_minutos"])
    filas = []
    for nombre, (mu, sd) in MODELOS_MOV.items():
        ok = c[mu].notna() & c["real_z"].notna() & (c[sd].notna() & (c[sd] > 0) if sd else True)
        cc = c[ok]
        for por in ([], ["metrica"], ["liga_o"], ["liga_d"], ["pos3"], ["tramo_min_d"], ["anio"]):
            grupos = [((), cc)] if not por else cc.groupby(por)
            for clave, g in grupos:
                if len(g) < 30:
                    continue
                r = medidas(g["real_z"], g[mu], g[sd] if sd else None)
                filas.append({"modelo": nombre, "por": "+".join(por) or "global",
                              "grupo": clave if not isinstance(clave, tuple) else "|".join(map(str, clave)) or "todo",
                              **r, "diagnostico": diagnostico_cobertura(r.get("cob80", np.nan))})
    return pd.DataFrame(filas), c


def casos_historial(cfg: dict) -> pd.DataFrame:
    """Examen de la v4.2 D1 reconstruido caso a caso con sus propias funciones (bbequipo/v42/historial.py, sin
    modificarlas): jugadores con ≥ 300 min en t y t+1 (cualquier liga), objetivo = valor v3.2 de t+1 en la vara
    EuroLeague. Para cada caso:
      v4.2   centro m_t (Kalman ≤ t), var P_t + τ² + c·v_{t+1}            (su examen)
      v3.2   centro y_t,             var v_t + v_{t+1}                    (intervalo PUBLICADO de las dos temporadas,
                                                                           sin cambio real: cota de su calibración)
    Escala: DT de la métrica en la escala de trabajo (como el examen D1)."""
    from bbequipo.v42 import historial as H
    d = H.cargar([t for t in H.CFG["temporadas"] if int(t[:4]) <= max(cfg["calibracion"]["cortes"]) + 1])
    filas = []
    for m in H.METRICAS:
        o_all = H.observaciones(d, m)
        for t in cfg["calibracion"]["cortes"]:
            tr = o_all[o_all["anio"] <= t]
            par = H.ajustar(tr)
            f = H.filtrar(tr, par["tau2"], par["c"], par["pp"])
            a = f[(f["anio"] == t) & (f["min"] >= H.MIN_EXAMEN)].set_index("persona_id")
            b = o_all[(o_all["anio"] == t + 1) & (o_all["min"] >= H.MIN_EXAMEN)].set_index("persona_id")
            k = a.index.intersection(b.index)
            a, b = a.loc[k], b.loc[k]
            sd = float(np.sqrt(par["var_y"]))
            filas.append(pd.DataFrame({
                "metrica": m, "anio": t, "persona_id": k, "pos3": a["pos3"].to_numpy(), "min_t": a["min"].to_numpy(),
                "real": b["y"].to_numpy() / sd,
                "v42_mu": a["m"].to_numpy() / sd, "v42_sd": np.sqrt(a["P"] + par["tau2"] + par["c"] * b["v"]).to_numpy() / sd,
                "v32_mu": a["y"].to_numpy() / sd, "v32_sd": np.sqrt(a["v"] + b["v"]).to_numpy() / sd,
                "v32_sd_nivel_t": np.sqrt(a["v"]).to_numpy() / sd, "v42_sd_nivel_t": np.sqrt(a["P"]).to_numpy() / sd,
                "tau2": par["tau2"] / sd ** 2, "c": par["c"]}))
        print(f"  historial {m}", flush=True)
    return pd.concat(filas, ignore_index=True)


def resumen_historial(h: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for nombre, mu, sd in (("v4.2 D1 (Kalman)", "v42_mu", "v42_sd"), ("v3.2 publicada (nivel t ⊕ nivel t+1)", "v32_mu", "v32_sd")):
        for por in ([], ["metrica"], ["pos3"], ["anio"]):
            grupos = [((), h)] if not por else h.groupby(por)
            for clave, g in grupos:
                r = medidas(g["real"], g[mu], g[sd])
                filas.append({"modelo": nombre, "por": "+".join(por) or "global",
                              "grupo": "|".join(map(str, clave)) if isinstance(clave, tuple) and clave else
                              (str(clave) if clave != () else "todo"), **r,
                              "diagnostico": diagnostico_cobertura(r["cob80"])})
    return pd.DataFrame(filas)


def paso_calibracion(cfg: dict) -> None:
    from bbfit.registro import experimento
    sal = C.dir_fase(cfg) / "calibracion"
    sal.mkdir(parents=True, exist_ok=True)
    with experimento("v5_f1", "calibracion", params={"hash_config": C.hash_config(cfg)}) as run:
        res, c = calibracion_movimientos(cfg)
        res.to_csv(sal / "movimientos_resumen.csv", index=False)
        # PIT de la v3.2 publicada y de la v2 (para los histogramas)
        pit = pd.DataFrame({"metrica": c["metrica"], "anio": c["anio"],
                            "pit_v32": norm.cdf((c["real_z"] - c["v3_centro_z"]) / (c["v3_sd_z"] * c["kappa"])),
                            "pit_v32_sin_recal": norm.cdf((c["real_z"] - c["v3_centro_z"]) / c["v3_sd_z"]),
                            "pit_v2": norm.cdf((c["real_z"] - c["v2_centro_z"]) / c["v2_sd_z"])})
        pit.round(4).to_csv(sal / "movimientos_pit.csv.gz", index=False)
        h = casos_historial(cfg)
        h.round(5).to_csv(sal / "historial_casos.csv.gz", index=False)
        hr = resumen_historial(h)
        hr.to_csv(sal / "historial_resumen.csv", index=False)
        g = res[res["por"] == "global"].set_index("modelo")
        run.metricas({"cob80_v32": g.loc["v3.2 publicada (predictiva recalibrada)", "cob80"],
                      "cob80_v2": g.loc["v2 = A+B amortiguado (intervalo F0, de nivel)", "cob80"]})
    C.escribir_json(C.metadatos(cfg, [C.RAIZ / cfg["v32"]["casos"]], {"paso": "calibracion"}), sal / "meta.json")
    print(res[res["por"] == "global"].round(3).to_string())
    print(hr[hr["por"] == "global"].round(3).to_string())


# ================================================================================================= §5.4 nivel
def paso_nivel(cfg: dict) -> pd.DataFrame:
    """¿Cuánto más estrecho sería un intervalo de CREDIBILIDAD del nivel bien calibrado?

    Con los componentes de varianza de §5.1 (por métrica), la posterior del nivel de la temporada θ_it = a_i + u_it de
    un jugador con exposición n en esa temporada, dentro de su liga-temporada (sin traducción):
        una temporada:      Var₁ = 1 / (1/(σ²_a + σ²_u) + n/σ²)
        con su historial ≤ t (modelo anidado; ȳ_s media ponderada de la temporada s, v_s = σ²_u + 1/W_s):
            Var(a | datos) = 1 / (1/σ²_a + Σ_{s≤t} 1/v_s),  k_t = σ²_u / v_t
            Var(θ_t | datos) = (1 − k_t)² Var(a | datos) + σ²_u (1/W_t) / v_t
    Se compara con la DT propia publicada por la v3.2 (√v_j de destino/capacidad) en DT de capacidad θ:
        sd_θ = s_ℓ · sd_T / τ_{ℓ,pos}   (constantes lineales de la v3.2)
    SUPUESTO: la escala del componente de varianza (σ²_a + σ²_u) y τ² de la v1 miden la misma dispersión dentro de liga."""
    from bbmodel.metricas import CATALOGO
    from bbnorm5.diagnostico import datos_f1
    comp = pd.read_csv(C.dir_fase(cfg) / "varianza" / "componentes.csv").set_index("metrica")
    s2g = pd.read_csv(C.dir_fase(cfg) / "varianza" / "sigma2_por_grupo.csv")
    dd = C.RAIZ / cfg["v32"]["destino"]
    const = json.loads((dd / "constantes.json").read_text(encoding="utf-8"))["metricas"]
    t, _ = datos_f1.tabla(cfg)
    temp = "2025-26"
    cap = pd.read_csv(dd / "capacidad" / f"{temp}.csv.gz", low_memory=False)
    cap = cap[cap["min"] >= 300].assign(player_id=lambda x: x["player_id"].astype(str))
    filas = []
    for col in comp.index:
        if f"{col}_vj" not in cap or col not in const:
            continue
        k = const[col]
        s2a, s2u = comp.loc[col, "s2a"], comp.loc[col, "s2u"]
        d = datos_f1.metrica(t, col, cfg["datos"]["min_minutos"])
        g = s2g[s2g["metrica"] == col].set_index("grupo")["s2"]
        d["w"] = d["n"] / d["g_s2"].map(g).to_numpy(float)
        d = d[d["anio"] <= int(temp[:4])]
        # por persona-temporada: W_s (todas sus ligas de la temporada)
        ps = d.groupby(["persona_id", "anio"])["w"].sum().rename("W").reset_index().sort_values(["persona_id", "anio"])
        ps["v"] = s2u + 1 / ps["W"]
        ps["prec_acum"] = ps.groupby("persona_id")["v"].transform(lambda v: (1 / v).cumsum())
        ps["var_a"] = 1 / (1 / s2a + ps["prec_acum"])
        kt = s2u / ps["v"]
        ps["var_hist"] = (1 - kt) ** 2 * ps["var_a"] + s2u * (1 / ps["W"]) / ps["v"]
        ps["var_1"] = 1 / (1 / (s2a + s2u) + ps["W"])
        ps["n_temporadas"] = ps.groupby("persona_id").cumcount() + 1
        fila_t = d[d["temporada"] == temp].merge(ps[ps["anio"] == int(temp[:4])], on=["persona_id", "anio"])
        fila_t = fila_t.merge(t.loc[t["temporada"] == temp, ["persona_id", "liga", "player_id"]].assign(
            player_id=lambda x: x["player_id"].astype(str)), on=["persona_id", "liga"])
        x = fila_t.merge(cap[["liga", "player_id", f"{col}_vj"]], on=["liga", "player_id"])
        if len(x) < 50:
            continue
        tau = np.sqrt(x.apply(lambda r: k["tau2"].get(f"{r['liga']}|{r['pos3']}", np.nan), axis=1).to_numpy(float))
        s = x["liga"].map(lambda l: 1.0 if l == "euroleague" else k["s"].get(l, np.nan)).to_numpy(float)
        conv = s / tau
        pub = np.sqrt(x[f"{col}_vj"].to_numpy(float))
        sd1 = np.sqrt(x["var_1"].to_numpy(float)) * conv
        sdh = np.sqrt(x["var_hist"].to_numpy(float)) * conv
        filas.append({"metrica": col, "n": len(x), "sd_publicada_theta": float(np.nanmedian(pub)),
                      "sd_credibilidad_1temp_theta": float(np.nanmedian(sd1)),
                      "sd_credibilidad_historial_theta": float(np.nanmedian(sdh)),
                      "razon_1temp": float(np.nanmedian(sd1 / pub)), "razon_historial": float(np.nanmedian(sdh / pub)),
                      "c_equivalente_1temp": float(np.nanmedian((sd1 / pub) ** 2)),
                      "temporadas_medianas": float(x["n_temporadas"].median())})
    out = pd.DataFrame(filas)
    sal = C.dir_fase(cfg) / "nivel"
    sal.mkdir(parents=True, exist_ok=True)
    out.to_csv(sal / "nivel_frente_publicado.csv", index=False)
    C.escribir_json(C.metadatos(cfg, [dd / "capacidad" / f"{temp}.csv.gz"], {"paso": "nivel", "temporada": temp}),
                    sal / "meta.json")
    print(out.round(3).to_string())
    return out


def paso_figuras(cfg: dict) -> None:
    from bbnorm5.diagnostico import figuras
    figuras.todas(cfg)


def paso_simulacion(cfg: dict) -> pd.DataFrame:
    """§5.4 · Prueba por simulación de la v4.2 D1 y de la sobrecobertura con intervalos exactos
    (bbnorm5/diagnostico/simulacion_d1.py)."""
    from bbnorm5.diagnostico import simulacion_d1 as S
    r = S.ejecutar(cfg, list(cfg["simulacion"]["metricas"]), int(cfg["simulacion"]["repeticiones"]))
    sal = C.dir_fase(cfg) / "nivel"
    sal.mkdir(parents=True, exist_ok=True)
    r.to_csv(sal / "simulacion_d1.csv", index=False)
    C.escribir_json(C.metadatos(cfg, extra={"paso": "simulacion"}), sal / "simulacion_meta.json")
    print(r.groupby("metrica").mean(numeric_only=True).round(3).to_string())
    return r
