"""v3.1: normalización combinada v2 (A+B amortiguado, `<m>_am`) + CVAE jerárquica corregida.

Regla (configs/normalization_v31.yaml → combinacion), en la escala de trabajo de cada métrica (transformada y
estandarizada), caso a caso:

    centro = w · centro_CVAE + (1 − w) · centro_v2
    predictiva = mezcla de N(centro_CVAE, sd_CVAE²) y N(centro_v2, sd_v2²) con pesos w y 1 − w

* w = `peso_v3` (0,5), fijado de antemano.
* Salvaguardas generales (fijadas de antemano), w = 0 (sólo v2) si:
  - la liga de origen o la de destino tiene menos de `min_temporadas_liga` temporadas en el ajuste (la CVAE no tiene
    con qué anclar su nivel: es lo que le pasó a la Tercera FEB en el corte 2023);
  - las 5 redes de la CVAE discrepan más de `max_discrepancia_redes` DT en esa métrica para ese jugador.
* Ajuste ESPECÍFICO por conocimiento (`ligas_conocimiento`, hoy sólo la Tercera FEB): en los casos con origen o
  destino en esas ligas, w = `peso_v3_conocimiento` y la anchura del intervalo se multiplica por
  `factor_intervalo_conocimiento`, los dos elegidos mirando el examen. Es sobreajuste asumido por el CEO y se informa
  por separado.
* La parte v2 usa el centro de `<m>_am` y la anchura de F0 (el intervalo del A amortiguado con la covarianza
  completa del grafo, sin el doble conteo de la v2).
* Recalibración conforme igual que la v3: factor por métrica y grupo con el corte anterior.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from bbmodel.metricas import CATALOGO, destransformar, transformar

from . import config as C
from . import datos, examen, flujo, prediccion

COLS_V3 = ["v3", "v3_lo", "v3_hi", "v3_centro_z", "v3_sd_z", "v3_sd_entre_z", "dentro_80_v3"]


def temporadas_por_liga(tabla: pd.DataFrame, cfg: dict, anio: int) -> dict:
    t = tabla[(tabla["anio"] <= anio) & (tabla["min"] >= cfg["datos"]["min_minutos"])]
    return t.groupby("liga")["anio"].nunique().to_dict()


def predicciones_cvae(tabla: pd.DataFrame, cfg: dict, anio: int) -> tuple[pd.DataFrame, datos.Escala]:
    f = flujo.dir_val(cfg) / f"predicciones_cvae_{anio}.csv.gz"
    D, cj = flujo.conjunto(tabla, cfg, anio)
    if f.exists():
        return pd.read_csv(f), D.esc
    r = prediccion.predecir_cambios(cj, D, tabla, anio, cfg)
    r.round(5).to_csv(f, index=False)
    return r, D.esc


def lineas_base(cfg: dict, anio: int) -> pd.DataFrame:
    """<m>_am, F0 y mismo percentil del corte; para el corte de selección, las recalculadas con ≤ 2022."""
    v = cfg["validacion"]
    if anio == int(v["anio_seleccion"]):
        d = C.RAIZ / v["lineas_base_seleccion"]
        base = examen.lineas_base(anio, d / f"sin_mapeo_{anio}.csv.gz", d / f"b_{anio}.csv")
    else:
        base = examen.lineas_base(anio)
    f0 = pd.read_csv(flujo.dir_val(cfg) / f"f0_{anio}.csv.gz")
    f0["real_r"] = f0["real"].round(3)
    f0 = f0.drop_duplicates(examen.CLAVE, keep=False)
    base = base.merge(f0[examen.CLAVE + ["centro_t_F0", "sd_t_F0", "dentro_80_F0"]], on=examen.CLAVE, how="left")
    return base


def componentes(tabla: pd.DataFrame, cfg: dict, anio: int) -> pd.DataFrame:
    """Una fila por caso y métrica con las dos partes (CVAE y v2) en la escala de trabajo estandarizada."""
    r, esc = predicciones_cvae(tabla, cfg, anio)
    j = examen.unir(r, lineas_base(cfg, anio))
    out = []
    for col, g in j.groupby("metrica"):
        tr = CATALOGO[col].transf
        c, s = esc.c[col], esc.s[col]
        g = g.assign(v2_centro_z=(transformar(g["am"], tr) - c) / s, v2_sd_z=g["sd_t_F0"] / s)
        out.append(g)
    j = pd.concat(out, ignore_index=True)
    j["temporadas_o"] = j["liga_o"].map(temporadas_por_liga(tabla, cfg, anio)).fillna(0)
    j["temporadas_d"] = j["liga_d"].map(temporadas_por_liga(tabla, cfg, anio)).fillna(0)
    j.attrs["esc"] = esc
    return j


def pesos(j: pd.DataFrame, cfg: dict, peso_conocimiento: float | None) -> tuple[np.ndarray, pd.Series]:
    cb = cfg["combinacion"]
    w = np.full(len(j), float(cb["peso_v3"]))
    motivo = pd.Series("general", index=j.index)
    conoc = j["liga_o"].isin(cb["ligas_conocimiento"]) | j["liga_d"].isin(cb["ligas_conocimiento"])
    if peso_conocimiento is not None:
        w[conoc.to_numpy()] = float(peso_conocimiento)
        motivo[conoc] = "conocimiento"
    pocas = (j["temporadas_o"] < cb["min_temporadas_liga"]) | (j["temporadas_d"] < cb["min_temporadas_liga"])
    w[pocas.to_numpy()] = 0.0
    motivo[pocas] = "salvaguarda_temporadas"
    disc = j["v3_sd_entre_z"] > cb["max_discrepancia_redes"]
    w[disc.to_numpy()] = 0.0
    motivo[disc & ~pocas] = "salvaguarda_discrepancia"
    sin_v2 = j["v2_sd_z"].isna() | j["v2_centro_z"].isna()
    w[sin_v2.to_numpy()] = 1.0                        # sin parte v2 (no debería ocurrir en el examen): sólo CVAE
    return w, motivo


def combinar(j: pd.DataFrame, cfg: dict, peso_conocimiento: float | None) -> pd.DataFrame:
    """Devuelve el mismo formato que las predicciones de la CVAE (columnas v3_*), con la combinación dentro, para
    reutilizar la calibración y la puerta de examen.py. Conserva la CVAE sola en cvae_* y el peso usado."""
    esc = j.attrs["esc"]
    w, motivo = pesos(j, cfg, peso_conocimiento)
    c3, s3 = j["v3_centro_z"].to_numpy(), j["v3_sd_z"].to_numpy()
    c2, s2 = j["v2_centro_z"].fillna(0).to_numpy(), j["v2_sd_z"].fillna(1).to_numpy()
    media = w * c3 + (1 - w) * c2
    var = w * (s3 ** 2 + c3 ** 2) + (1 - w) * (s2 ** 2 + c2 ** 2) - media ** 2
    sd = np.sqrt(np.maximum(var, 1e-8))
    out = j.rename(columns={c: c.replace("v3", "cvae") for c in COLS_V3}).copy()
    out["v3_centro_z"], out["v3_sd_z"], out["peso_cvae"], out["motivo_peso"] = media, sd, w, motivo.to_numpy()
    # cuantiles 10/90 de la mezcla por bisección (para la cobertura bruta y el intervalo en unidades reales)
    lo_z, hi_z = _cuantiles_mezcla(w, c3, s3, c2, s2, (0.1, 0.9))
    out["dentro_80_v3"] = (out["real_z"] >= lo_z) & (out["real_z"] <= hi_z)
    v, vl, vh = [], [], []
    for col, g in out.groupby("metrica", sort=False):
        tr = CATALOGO[col].transf
        c, s = esc.c[col], esc.s[col]
        i = g.index
        v.append(pd.Series(destransformar(c + s * media[i], tr), index=i))
        vl.append(pd.Series(destransformar(c + s * lo_z[i], tr), index=i))
        vh.append(pd.Series(destransformar(c + s * hi_z[i], tr), index=i))
    out["v3"], out["v3_lo"], out["v3_hi"] = pd.concat(v), pd.concat(vl), pd.concat(vh)
    return out


def _cuantiles_mezcla(w, c3, s3, c2, s2, qs):
    from scipy.stats import norm
    res = []
    for q in qs:
        lo = np.minimum(c3 - 6 * s3, c2 - 6 * s2)
        hi = np.maximum(c3 + 6 * s3, c2 + 6 * s2)
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            F = w * norm.cdf((mid - c3) / s3) + (1 - w) * norm.cdf((mid - c2) / s2)
            lo = np.where(F < q, mid, lo)
            hi = np.where(F < q, hi, mid)
        res.append(0.5 * (lo + hi))
    return res


# ---------------------------------------------------------------------------------------------- examen
def _es_conocimiento(r: pd.DataFrame, cfg: dict) -> pd.Series:
    ligas = cfg["combinacion"]["ligas_conocimiento"]
    return r["liga_o"].isin(ligas) | r["liga_d"].isin(ligas)


def _calibrado(comb: dict, cfg: dict, factor_conocimiento: float | None = None) -> pd.DataFrame:
    """Recalibración conforme con el corte anterior y, si se da, factor de anchura extra en los casos con ligas de
    conocimiento (FEB3)."""
    from .prediccion import Z80
    v = cfg["validacion"]
    sel = int(v["anio_seleccion"])
    unidos = []
    for a in [int(x) for x in v["anios"]]:
        cal = comb[a - 1] if (a - 1) in comb else comb[sel]
        fac = examen.factores_calibracion(cal, int(v["min_casos_grupo"]))
        unidos.append(examen.aplicar_calibracion(comb[a], fac))
    r = pd.concat(unidos, ignore_index=True)
    if factor_conocimiento is not None:
        k = np.where(_es_conocimiento(r, cfg), r["kappa"] * factor_conocimiento, r["kappa"])
        half = k * Z80 * r["v3_sd_z"]
        r = r.assign(kappa=k, dentro_80_v3c=((r["real_z"] >= r["v3_centro_z"] - half) &
                                             (r["real_z"] <= r["v3_centro_z"] + half)).to_numpy())
    return r


def factor_intervalo_conocimiento(r: pd.DataFrame, cfg: dict) -> float:
    """SOBREAJUSTE: factor que lleva al 80 % la cobertura de los casos con ligas de conocimiento en el examen."""
    from .prediccion import Z80
    c = _es_conocimiento(r, cfg)
    e = (r.loc[c, "real_z"] - r.loc[c, "v3_centro_z"]).abs() / (r.loc[c, "kappa"] * r.loc[c, "v3_sd_z"])
    return float(np.quantile(e, 0.8) / Z80) if c.any() else 1.0


def _evaluar(comb: dict, cfg: dict, factor_conocimiento: float | None = None) -> tuple[pd.DataFrame, dict]:
    v = cfg["validacion"]
    r = _calibrado(comb, cfg, factor_conocimiento)
    pt = examen.puerta(r, cfg)
    pt["mae_rel_percentil"] = examen.mae_rel_medio(r, "v3", "mismo_percentil")
    pt["mae_rel_F0"] = examen.mae_rel_medio(r, "v3", "F0")
    pt["por_corte"] = {int(a): {"frente_am": examen.mae_rel_medio(g),
                                "ic95": examen.bootstrap_persona(g, "v3", "am", int(v["bootstrap"]),
                                                                 int(v["semilla_bootstrap"]))["ic95"],
                                "cob80": float(g["dentro_80_v3c"].mean())} for a, g in r.groupby("anio")}
    g = examen.grupo(r["liga_o"], r["liga_d"])
    pt["por_grupo"] = {k: {"personas": int(r.loc[g == k, "persona_id"].nunique()),
                           "frente_am": examen.mae_rel_medio(r[g == k]),
                           "cob80": float(r.loc[g == k, "dentro_80_v3c"].mean())} for k in sorted(g.unique())}
    conoc = r["liga_o"].isin(cfg["combinacion"]["ligas_conocimiento"]) | r["liga_d"].isin(cfg["combinacion"]["ligas_conocimiento"])
    pt["casos_conocimiento"] = {"personas": int(r.loc[conoc, "persona_id"].nunique()),
                                "frente_am": examen.mae_rel_medio(r[conoc]) if conoc.any() else None,
                                "resto_frente_am": examen.mae_rel_medio(r[~conoc])}
    if "motivo_peso" in r:
        pt["pesos"] = r.groupby("motivo_peso")["peso_cvae"].agg(["size", "mean"]).round(3).to_dict("index")
    return r, pt


def validar_combinada(tabla: pd.DataFrame, cfg: dict) -> dict:
    """Examen de la v3.1 (mismos cortes que la v3.0). Informa tres cosas por separado:
       1. CVAE corregida sola;  2. combinación con la regla fijada de antemano (sin ajuste por conocimiento);
       3. combinación con el peso por conocimiento de la FEB3 elegido mirando el examen (SOBREAJUSTE asumido)."""
    v = cfg["validacion"]
    anios = [int(v["anio_seleccion"])] + [int(a) for a in v["anios"]]
    comp = {a: componentes(tabla, cfg, a) for a in anios}
    dv = flujo.dir_val(cfg)
    informe = {"aviso": "Los cortes 2023 y 2024 ya se habían visto al diseñar la v3.1: los resultados son orientativos; "
                        "la decisión debe tomarse con el examen limpio 2025-26 → 2026-27."}
    # 1. CVAE sola
    sola = {a: comp[a] for a in anios}
    r1, p1 = _evaluar(sola, cfg)
    informe["cvae_sola"] = p1
    # 2. regla fijada de antemano
    r2, p2 = _evaluar({a: combinar(comp[a], cfg, None) for a in anios}, cfg)
    informe["combinada_regla_fija"] = p2
    # 3. peso por conocimiento (FEB3) elegido con el examen
    rejilla = {}
    for w in cfg["combinacion"]["pesos_candidatos"]:
        r3, _ = _evaluar({a: combinar(comp[a], cfg, w) for a in anios}, cfg)
        conoc = r3["liga_o"].isin(cfg["combinacion"]["ligas_conocimiento"]) | \
            r3["liga_d"].isin(cfg["combinacion"]["ligas_conocimiento"])
        rejilla[w] = examen.mae_rel_medio(r3[conoc])
    w_opt = min(rejilla, key=rejilla.get)
    comb3 = {a: combinar(comp[a], cfg, w_opt) for a in anios}
    f_opt = factor_intervalo_conocimiento(_calibrado(comb3, cfg), cfg)
    r3, p3 = _evaluar(comb3, cfg, f_opt)
    p3["peso_v3_conocimiento_elegido"] = w_opt
    p3["factor_intervalo_conocimiento_elegido"] = f_opt
    p3["rejilla_conocimiento_frente_am"] = rejilla
    informe["combinada_con_conocimiento_feb3"] = p3
    r3.round(5).to_csv(dv / "casos_combinada.csv.gz", index=False)
    examen.resumen_metricas(r3).round(4).to_csv(dv / "resumen_metricas_combinada.csv", index=False)
    (dv / "examen_v31.json").write_text(json.dumps(informe, indent=1, ensure_ascii=False, default=float),
                                        encoding="utf-8")
    for k in ("cvae_sola", "combinada_regla_fija", "combinada_con_conocimiento_feb3"):
        p = informe[k]
        print(k, json.dumps({"pasa": p["pasa"], "frente_am": p["criterio_1_mae"]["estimacion"],
                             "ic95": p["criterio_1_mae"]["ic95"], "cob": p["criterio_2_cobertura"]["cobertura_media"],
                             "por_corte": p["por_corte"]}, default=float), flush=True)
    print("peso FEB3 elegido:", w_opt, rejilla, "factor de intervalo FEB3:", round(f_opt, 3))
    return informe


# ---------------------------------------------------------------------------------------------- ajuste final
def ajustar_combinada(tabla: pd.DataFrame, cfg: dict) -> None:
    """CVAE corregida con todas las temporadas (niveles, traducción cruzada, ciclo, puentes en data/modelos/v3_1/) y
    dataset normalizado combinado data/modelos/v3_1/normalizado/<t>.csv.gz con el esquema del v1."""
    from . import exportar
    from .prediccion import Z80
    cb = cfg["combinacion"]
    w_con = cb.get("peso_v3_conocimiento")
    if w_con is None:
        f = flujo.dir_val(cfg) / "examen_v31.json"
        w_con = json.loads(f.read_text())["combinada_con_conocimiento_feb3"]["peso_v3_conocimiento_elegido"]
    f_con = cb.get("factor_intervalo_conocimiento")
    if f_con is None:
        f = flujo.dir_val(cfg) / "examen_v31.json"
        f_con = json.loads(f.read_text())["combinada_con_conocimiento_feb3"].get("factor_intervalo_conocimiento_elegido", 1.0)
    D, cj = flujo.conjunto(tabla, cfg, None)
    trad = exportar.todo(tabla, D, cj, cfg, normalizado=False)
    temporadas = temporadas_por_liga(tabla, cfg, int(tabla["anio"].max()))
    resumen = {"peso_v3": cb["peso_v3"], "peso_v3_conocimiento": w_con, "factor_intervalo_conocimiento": f_con}

    def nuevas(base: pd.DataFrame, v3: pd.DataFrame) -> pd.DataFrame:
        out = v3.copy()
        liga = base["liga"].reset_index(drop=True)
        conoc = liga.isin(cb["ligas_conocimiento"]).to_numpy()
        pocas = (liga.map(temporadas).fillna(0) < cb["min_temporadas_liga"]).to_numpy()
        for col in datos.METRICAS:
            if f"{col}_am" not in base or f"{col}_v3" not in v3:
                continue
            tr = CATALOGO[col].transf
            T = lambda x: transformar(pd.to_numeric(x, errors="coerce").to_numpy(float), tr)  # noqa: E731
            m2, s2 = T(base[f"{col}_am"]), (T(base[f"{col}_am_hi"]) - T(base[f"{col}_am_lo"])) / (2 * Z80)
            m3, s3 = T(v3[f"{col}_v3"]), (T(v3[f"{col}_v3_hi"]) - T(v3[f"{col}_v3_lo"])) / (2 * Z80)
            w = np.full(len(v3), float(cb["peso_v3"]))
            w[conoc] = float(w_con)
            w[pocas] = 0.0
            sz = v3[f"{col}_v3_sd_entre_z"].to_numpy(float)
            w[sz > cb["max_discrepancia_redes"]] = 0.0
            sin_v2 = ~np.isfinite(m2) | ~np.isfinite(s2)
            w[sin_v2] = 1.0                               # fila que el v1 no tiene (p. ej. partidos nuevos de 2026-27)
            m2, s2 = np.where(sin_v2, m3, m2), np.where(sin_v2, s3, s2)
            s2, s3 = np.maximum(s2, 1e-6), np.maximum(s3, 1e-6)
            media = w * m3 + (1 - w) * m2
            lo, hi = _cuantiles_mezcla(w, m3, s3, m2, s2, (0.1, 0.9))
            fc = np.where(conoc, float(f_con), 1.0)          # anchura extra en la Tercera FEB (conocimiento)
            lo, hi = media - fc * (media - lo), media + fc * (hi - media)
            out[f"{col}_v31"] = destransformar(media, tr)
            out[f"{col}_v31_lo"] = destransformar(lo, tr)
            out[f"{col}_v31_hi"] = destransformar(hi, tr)
            p2 = pd.to_numeric(base.get(f"{col}_am_pctel"), errors="coerce").to_numpy(float)
            p3 = v3[f"{col}_v3_pctel"].to_numpy(float)
            out[f"{col}_v31_pctel"] = np.where(np.isfinite(p2), w * p3 + (1 - w) * p2, p3)
            out[f"{col}_v31_peso_cvae"] = w
        return out

    exportar._normalizado(trad, C.dir_salida(cfg) / "normalizado", columnas_nuevas=nuevas, sufijo="_v31",
                          fuente="V3.1")
    (C.dir_salida(cfg) / "resumen_combinada.json").write_text(json.dumps(resumen, indent=1, default=float),
                                                              encoding="utf-8")
    print("Dataset normalizado v3.1 en", C.dir_salida(cfg) / "normalizado", flush=True)
