"""Línea de comandos de la v4.1 (capa E · ecosistema del club).

    python -m bbequipo.ecosistema orden-sinergias [--version a b] [--ligas L …] [--procesos 3] [--sin-nulo] [--sin-predictiva]
    python -m bbequipo.ecosistema orden-sinergias-resumen          # rehace resumen.json desde las filas guardadas
    python -m bbequipo.ecosistema sinergia-mixta [--version a b] [--etapas 2 3 5]   # modelo mixto REML (estimador principal)
    python -m bbequipo.ecosistema puntos-esperados [--temporadas T …] [--ligas L …]   # capa XP (docs/puntos_esperados.md)
    python -m bbequipo.ecosistema beneficio-xp [--segmento global|elite_club]      # beneficio del punto esperado
    python -m bbequipo.ecosistema potencia-trios [--segmento elite_club|global]    # EMD de la puerta F3-T
    python -m bbequipo.ecosistema benchmark                        # F0.3 benchmark de decisión sobre la v4.0
    python -m bbequipo.ecosistema ausencias                        # F0.5 auditoría de ausencias (banco V-AUS)
    python -m bbequipo.ecosistema inventario                       # F0.6/F0.7 Fit, ADAPT y referencias fijas a club/temporada
"""
from __future__ import annotations

import argparse
import json
import time

import pandas as pd

from . import config as CE


def _registro(cfg, run, params, metricas, artefactos=()):
    try:
        from bbfit.registro import experimento
        with experimento(cfg["mlflow"], run, params=params, semilla=cfg["semilla"]) as r:
            r.metricas({k: v for k, v in metricas.items() if isinstance(v, (int, float))})
            for a in artefactos:
                r.artefacto(a)
    except Exception as e:                                   # el registro nunca bloquea un cálculo
        print(f"  (MLflow no disponible: {e})")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bbequipo.ecosistema", description="CERNO v4.1: capa E (ecosistema del club)")
    ap.add_argument("--config", default=None)
    sub = ap.add_subparsers(dest="orden", required=True)
    o = sub.add_parser("orden-sinergias", help="F0.4: prueba de orden de sinergias (§2.2), versiones (a) y (b)")
    o.add_argument("--version", nargs="*", default=["a", "b"])
    o.add_argument("--ligas", nargs="*", default=None)
    o.add_argument("--procesos", type=int, default=3)
    o.add_argument("--sin-nulo", action="store_true")
    o.add_argument("--sin-predictiva", action="store_true")
    sub.add_parser("orden-sinergias-resumen", help="F0.4: resumen.json desde las filas guardadas")
    sm = sub.add_parser("sinergia-mixta", help="F0.4 (CEO 06-11-2026): prueba de orden por modelo mixto (REML)")
    sm.add_argument("--version", nargs="*", default=["a", "b"])
    sm.add_argument("--etapas", nargs="*", type=int, default=[2, 3, 5])
    sm.add_argument("--ligas", nargs="*", default=None)
    xp = sub.add_parser("puntos-esperados", help="capa XP: punto esperado de cada tiro, tramos y jugadores (catálogo del YAML)")
    xp.add_argument("--temporadas", nargs="*", default=None)
    xp.add_argument("--ligas", nargs="*", default=None)
    bx = sub.add_parser("beneficio-xp", help="prueba prerregistrada de beneficio del punto esperado como resultado de tramo")
    bx.add_argument("--segmento", default="global", choices=["global", "elite_club"])
    po = sub.add_parser("potencia-trios", help="efecto mínimo detectable de la puerta F3-T (tríos por perfiles)")
    po.add_argument("--segmento", default="elite_club", choices=["global", "elite_club"])
    sub.add_parser("benchmark", help="F0.3: benchmark de decisión sobre la v4.0")
    sub.add_parser("ausencias", help="F0.5: auditoría de ausencias (banco V-AUS)")
    sub.add_parser("inventario", help="F0.6/F0.7: residuos de Fit y ADAPT; referencias fijas a club y temporada")
    a = ap.parse_args(argv)
    cfg = CE.cargar(CE.RAIZ / a.config if a.config else None)
    t0 = time.time()
    if a.orden == "orden-sinergias":
        from . import orden_sinergias as OS
        for v in a.version:
            r = OS.ejecutar(cfg, v, ligas=a.ligas, procesos=a.procesos, con_nulo=not a.sin_nulo,
                            con_pred=not a.sin_predictiva)
            print(f"[{v}] {r['tramos']} tramos · {r['ligas_temporada']} ligas-temporada · {len(r['ligas'])} competiciones "
                  f"· {r['segundos']} s")
        if not a.ligas:
            _resumen_orden(cfg)
    elif a.orden == "sinergia-mixta":
        from . import sinergia_mixta as SM
        r = SM.ejecutar(cfg, versiones=a.version, etapas=a.etapas, ligas=a.ligas)
        met = {f"{v}_{o}_{s}_sigma": r["versiones"][v][o][s].get("sigma") for v in r["versiones"] for o in r["versiones"][v]
               for s in ("global", "elite_club") if isinstance(r["versiones"][v][o], dict) and s in r["versiones"][v][o]}
        if not a.ligas:
            _registro(cfg, "F0_sinergia_mixta", {"etapas": cfg["sinergia_mixta"]["etapas"]},
                      {k: v for k, v in met.items() if v is not None},
                      [CE.dir_salida(cfg, "sinergia_mixta") / "resumen.json"])
    elif a.orden == "puntos-esperados":
        from . import puntos_esperados as PE
        r = PE.ejecutar(cfg, temporadas=a.temporadas, ligas=a.ligas)
        print(f"capa XP: {r['ligas_temporada']} ligas-temporada · {r['segundos']} s")
    elif a.orden == "beneficio-xp":
        from . import beneficio_xp as BX
        r = BX.ejecutar(cfg, segmento=a.segmento)
        print(json.dumps(r["segmentos"], ensure_ascii=False, indent=1, default=float)[:3000])
    elif a.orden == "potencia-trios":
        from . import potencia as PO
        r = PO.potencia_trios(cfg, segmento=a.segmento)
        print(json.dumps({k: r[k] for k in ("real", "emd", "informativo", "lectura")}, ensure_ascii=False, indent=1, default=float))
    elif a.orden == "orden-sinergias-resumen":
        _resumen_orden(cfg)
    elif a.orden == "benchmark":
        from . import benchmark
        r = benchmark.ejecutar(cfg, progreso=None)
        A, Bi, Cd = r["A_nivel_cerno"], r["B_impacto"], r["C_delta_net"]
        _registro(cfg, "F0_benchmark", {"cortes": r["cortes_decision"]},
                  {**{f"nc_spearman_{s}": A[s]["spearman_NC1_pct"] for s in A},
                   **{f"im_spearman_{s}": Bi[s]["spearman_IM_onoff"] for s in Bi},
                   **{f"mae_f4_{s}": Cd[s]["mae_f4"] for s in Cd}},
                  [CE.dir_salida(cfg, "benchmark") / "benchmark.json"])
        print(f"benchmark → {CE.dir_salida(cfg, 'benchmark') / 'benchmark.json'}")
    elif a.orden == "ausencias":
        from . import ausencias
        r = ausencias.ejecutar(cfg, progreso=None)
        _registro(cfg, "F0_ausencias", {"umbrales": list(r["por_umbral"])},
                  {f"un_ausente_{u}_{s}": v[s]["equipo_partidos_un_ausente"] for u, v in r["por_umbral"].items()
                   for s in ("global", "elite_club")}, [CE.dir_salida(cfg, "ausencias") / "resumen.json"])
        print(json.dumps(r["por_umbral"], ensure_ascii=False, indent=1, default=float))
    elif a.orden == "inventario":
        from . import inventario
        r = inventario.ejecutar(cfg, progreso=None)
        _registro(cfg, "F0_inventario", {}, {"fit_adapt": r["fit_adapt"]["apariciones"],
                                             "club_temporada": r["club_temporada"]["apariciones"]},
                  [CE.dir_salida(cfg, "inventario") / "resumen.json"])
        print(json.dumps(r["fit_adapt"]["por_clase"], ensure_ascii=False))
    print(f"hecho en {time.time() - t0:.0f} s")


def _resumen_orden(cfg):
    from . import orden_sinergias as OS
    d = CE.dir_salida(cfg, "orden_sinergias")
    res = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "config": cfg["orden_sinergias"], "versiones": {}}
    for v in ("a", "b"):
        f = CE.RAIZ / "experimentos" / "v4_1" / "orden_sinergias" / f"filas_{v}.csv.gz"
        if not f.exists():
            f = d / f"filas_obs_{v}.csv.gz"                    # sin réplicas: sólo V observado
        if not f.exists():
            continue
        filas = pd.read_csv(f, low_memory=False)
        p = d / f"predictiva_{v}.csv.gz"
        pred = pd.read_csv(p) if p.exists() else pd.DataFrame()
        info = json.loads((d / f"info_{v}.json").read_text())
        r = OS.resumir(cfg, filas, pred)
        r["datos"] = {"ligas_temporada": len(info), "competiciones": sorted({i["liga"] for i in info}),
                      "tramos": int(sum(i["tramos"] for i in info)),
                      "lambda_a_distribucion": pd.Series([x for i in info for x in i["lambdas"]]).value_counts().to_dict()
                      if v == "a" else None,
                      "sin_prior": int(sum(i.get("sin_prior", 0) for i in info)) if v == "b" else None}
        res["versiones"][v] = r
    (d / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    met = {}
    for v, r in res["versiones"].items():
        for seg in ("global", "elite_club"):
            for k in ("pareja_propio", "trio_propio", "quinteto_propio"):
                x = r[seg].get(k)
                if x:
                    met[f"{v}_{seg}_{k}_V"] = x["V"]
                    if "V_corregido" in x:
                        met[f"{v}_{seg}_{k}_Vcorr"] = x["V_corregido"]
    _registro(cfg, "F0_orden_sinergias", {"min_pos": cfg["orden_sinergias"]["min_posesiones_tercio"]}, met,
              [d / "resumen.json"])
    print(json.dumps({v: {s: {k: {kk: r[s][k].get(kk) for kk in ("n_filas", "V", "V_r80", "V_nulo", "V_corregido",
                                                                     "V_corregido_r80")}
                              for k in r[s] if k.endswith("propio")} for s in ("global", "elite_club")}
                      for v, r in res["versiones"].items()}, indent=1, default=float))


if __name__ == "__main__":
    main()
