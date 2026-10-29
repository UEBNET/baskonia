"""Flujos de trabajo de la v3: elección de K, examen con puerta de control, dejar fuera una liga y ajuste final."""
from __future__ import annotations

import hashlib
import json
import numpy as np
import pandas as pd
import torch

from . import config as C
from . import datos, examen, modelo, niveles, prediccion

DIR_CACHE = C.RAIZ / "experimentos" / "v3"
DIR_VAL = C.DIR_SALIDA / "validacion"


def _huella(cfg: dict) -> str:
    return hashlib.sha1(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()[:10]


def conjunto(tabla: pd.DataFrame, cfg: dict, hasta_anio: int | None, semillas=None, etiqueta: str = "",
             progreso=print):
    """Datos + deep ensemble (una red por semilla) + posterior de cada red. Reutiliza las redes guardadas."""
    D = datos.construir(tabla, cfg, hasta_anio=hasta_anio)
    DIR_CACHE.mkdir(parents=True, exist_ok=True)
    huella = _huella({k: v for k, v in cfg.items() if k not in ("validacion", "prediccion", "semillas")})
    out = []
    for s in (semillas or cfg["semillas"]):
        f = DIR_CACHE / f"{etiqueta}h{hasta_anio}_{huella}_s{s}.pt"
        if f.exists():
            m = modelo.CVAE(D, cfg, s)
            m.load_state_dict(torch.load(f))
            m.eval()
        else:
            if progreso:
                progreso(f"  entrenando corte ≤ {hasta_anio}, semilla {s}")
            m = modelo.entrenar(D, cfg, s, progreso=None)
            torch.save(m.state_dict(), f)
        out.append((m, niveles.posterior(m, D, cfg)))
    return D, out


# ---------------------------------------------------------------------------------------------- elegir K
def elegir_k(tabla: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Corte de selección (≤ 2022 → 2023): error del examen de cada K con 2 semillas. Se elige el K de menor error
    medio relativo (a igualdad —menos de 0,5 %—, el más pequeño). No usa los cortes del examen."""
    anio = int(cfg["validacion"]["anio_seleccion"])
    filas, preds = [], {}
    for K in cfg["latente"]["K_candidatos"]:
        c = C.con(cfg, **{"latente.K": int(K)})
        D, cj = conjunto(tabla, c, anio, semillas=cfg["semillas"][:2], etiqueta=f"k{K}_")
        r = prediccion.predecir_cambios(cj, D, tabla, anio, c)
        preds[K] = r.assign(e=(r["v3"] - r["real"]).abs())
    ref = preds[int(cfg["latente"]["K"])].groupby("metrica")["e"].mean()
    for K, r in preds.items():
        mae = r.groupby("metrica")["e"].mean()
        filas.append({"K": K, "casos": len(r), "mae_relativo_medio": float((mae / ref).mean()),
                      "cobertura80_bruta": float(r["dentro_80_v3"].mean())})
    out = pd.DataFrame(filas).sort_values("K")
    DIR_VAL.mkdir(parents=True, exist_ok=True)
    out.round(4).to_csv(DIR_VAL / "elegir_k.csv", index=False)
    print(out.round(4).to_string(index=False))
    return out


# ---------------------------------------------------------------------------------------------- examen
def predicciones_corte(tabla: pd.DataFrame, cfg: dict, anio: int) -> pd.DataFrame:
    DIR_VAL.mkdir(parents=True, exist_ok=True)
    f = DIR_VAL / f"predicciones_{anio}.csv.gz"
    if f.exists():
        return pd.read_csv(f)
    D, cj = conjunto(tabla, cfg, anio)
    r = prediccion.predecir_cambios(cj, D, tabla, anio, cfg)
    r.round(5).to_csv(f, index=False)
    return r


def validar(tabla: pd.DataFrame, cfg: dict, f0: bool = True) -> dict:
    """Examen sin fuga: la CVAE se reentrena con ≤ t en cada corte; calibración conforme con el corte anterior."""
    v = cfg["validacion"]
    anios = [int(a) for a in v["anios"]]
    sel = int(v["anio_seleccion"])
    preds = {a: predicciones_corte(tabla, cfg, a) for a in [sel] + anios}
    unidos = []
    for a in anios:
        cal = preds[a - 1] if (a - 1) in preds else preds[sel]
        fac = examen.factores_calibracion(cal, int(v["min_casos_grupo"]))
        r = examen.aplicar_calibracion(preds[a], fac)
        j = examen.unir(r, examen.lineas_base(a))
        if f0:
            j = _f0(j, a)
        unidos.append(j)
        (DIR_VAL / f"calibracion_{a}.json").write_text(json.dumps(fac, indent=1, ensure_ascii=False), encoding="utf-8")
    r = pd.concat(unidos, ignore_index=True)
    r.round(5).to_csv(DIR_VAL / "casos.csv.gz", index=False)
    res = examen.resumen_metricas(r)
    res.round(4).to_csv(DIR_VAL / "resumen_metricas.csv", index=False)
    pares = examen.cobertura_grupos(r, 1)
    pares.round(4).to_csv(DIR_VAL / "pares_origen_destino.csv", index=False)
    pt = examen.puerta(r, cfg)
    pt["mae_rel_v3_percentil"] = examen.mae_rel_medio(r, "v3", "mismo_percentil")
    pt["mae_rel_v3_F0"] = examen.mae_rel_medio(r, "v3", "F0")
    pt["mae_rel_am_percentil"] = examen.mae_rel_medio(r, "am", "mismo_percentil")
    pt["casos"] = int(len(r))
    pt["por_corte"] = {int(a): {"v3_am": examen.mae_rel_medio(g), "cob80": float(g["dentro_80_v3c"].mean()),
                                "cob80_bruta": float(g["dentro_80_v3"].mean())} for a, g in r.groupby("anio")}
    g = examen.grupo(r["liga_o"], r["liga_d"])
    pt["por_grupo"] = {k: {"casos": int((g == k).sum()), "v3_am": examen.mae_rel_medio(r[g == k]),
                           "cob80": float(r.loc[g == k, "dentro_80_v3c"].mean())} for k in sorted(g.unique())}
    (DIR_VAL / "puerta.json").write_text(json.dumps(pt, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    print(json.dumps({k: pt[k] for k in ("pasa", "mae_rel_v3_percentil", "mae_rel_v3_F0")}, default=float))
    print(json.dumps(pt["criterio_1_mae"], default=float))
    return pt


def f0(tabla: pd.DataFrame, cfg: dict) -> None:
    """Calcula y guarda la cobertura de F0 (covarianza completa del grafo amortiguado) en cada corte del examen."""
    from .f0 import f0_corte
    DIR_VAL.mkdir(parents=True, exist_ok=True)
    for a in cfg["validacion"]["anios"]:
        f = DIR_VAL / f"f0_{a}.csv.gz"
        if not f.exists():
            r = f0_corte(tabla, int(a))
            r.round(5).to_csv(f, index=False)
            print(f"  F0 {a}: {len(r)} predicciones, cobertura {r['dentro_80_F0'].mean():.3f}", flush=True)


def _f0(j: pd.DataFrame, anio: int) -> pd.DataFrame:
    """Cobertura de F0 (A amortiguado con la covarianza completa del grafo) si se ha calculado."""
    f = DIR_VAL / f"f0_{anio}.csv.gz"
    if not f.exists():
        return j.assign(dentro_80_F0=np.nan)
    x = pd.read_csv(f)
    x["real_r"] = x["real"].round(3)
    return j.merge(x[examen.CLAVE + ["dentro_80_F0"]].drop_duplicates(examen.CLAVE), on=examen.CLAVE, how="left")


# ---------------------------------------------------------------------------------------------- dejar fuera una liga
def lolo(tabla: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Para cada liga, se reentrena (1 semilla) separando a sus personas de las demás ligas (sin puentes ni
    transiciones con la liga) y se compara su nivel por métrica con el del ajuste completo (misma semilla)."""
    from . import traduccion
    anio = max(int(a) for a in cfg["validacion"]["anios"])
    s = cfg["semillas"][0]
    D, cj = conjunto(tabla, cfg, anio, semillas=[s])
    m, P = cj[0]
    ref_nombre = f"{cfg['referencia_salida']['liga']}|{anio}-{str(anio + 1)[-2:]}"
    filas = []
    for liga in sorted(tabla.loc[tabla["anio"] <= anio, "liga"].unique()):
        if liga == cfg["referencia_salida"]["liga"]:
            continue
        t2 = tabla.copy()
        sel = t2["liga"] == liga
        t2.loc[sel, "persona_id"] = t2.loc[sel, "persona_id"] + 10_000_000   # personas nuevas: sin puentes
        D2, cj2 = conjunto(t2, cfg, anio, semillas=[s], etiqueta=f"lolo_{liga}_")
        m2, P2 = cj2[0]
        for comp in [c for c in D.comps if c.startswith(liga + "|")]:
            R1, R2 = D.comps.index(ref_nombre), D2.comps.index(ref_nombre)
            d1, J1 = traduccion.niveles(m, P, D, R1)
            d2, J2 = traduccion.niveles(m2, P2, D2, R2)
            c1, c2 = D.comps.index(comp), D2.comps.index(comp)
            cov2 = P2.cov_mu()
            sd2 = np.sqrt(np.maximum(traduccion.covarianza_niveles(J2, cov2, R2, c2, c2), 0))
            for k, met in enumerate(datos.METRICAS):
                filas.append({"liga": liga, "competicion": comp, "metrica": met, "nivel_completo": d1[c1, k],
                              "nivel_sin_puentes": d2[c2, k], "sd_sin_puentes": sd2[k],
                              "error": d2[c2, k] - d1[c1, k],
                              "dentro_80": abs(d2[c2, k] - d1[c1, k]) <= 1.2816 * sd2[k]})
        print(f"  lolo {liga}: hecho", flush=True)
    out = pd.DataFrame(filas)
    DIR_VAL.mkdir(parents=True, exist_ok=True)
    out.round(5).to_csv(DIR_VAL / "lolo.csv", index=False)
    print(out.groupby("liga").agg(error_abs=("error", lambda x: np.abs(x).mean()), cob80=("dentro_80", "mean")).round(3))
    return out


def ajustar(tabla: pd.DataFrame, cfg: dict) -> None:
    from . import exportar
    D, cj = conjunto(tabla, cfg, None)
    exportar.todo(tabla, D, cj, cfg)
