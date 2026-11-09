"""F1 · Auditoría de varianza y calibración de lo existente (encargo v5.0 §5).

    python -m bbnorm5.f1 --config configs/v5/f1.yaml varianza        # §5.1 componentes de varianza (REML)
    python -m bbnorm5.f1 --config configs/v5/f1.yaml division        # §5.1 división de muestra (partidos pares/impares)
    python -m bbnorm5.f1 --config configs/v5/f1.yaml incertidumbre   # §5.2 descomposición del ancho publicado v3.2
    python -m bbnorm5.f1 --config configs/v5/f1.yaml calibracion     # §5.3 cobertura, PIT, CRPS (v1, v3.2, v4.2)
    python -m bbnorm5.f1 --config configs/v5/f1.yaml nivel           # §5.4 nivel frente a predictivo
    python -m bbnorm5.f1 --config configs/v5/f1.yaml figuras         # figuras del informe (marca Kerno)

Salidas en data/v5/f1/ con metadatos (versión, hash de configuración y de datos de entrada). Registro en MLflow
(experimento «v5_f1»).
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd

from bbnorm5 import config as C


def paso_varianza(cfg: dict) -> pd.DataFrame:
    from bbfit.registro import experimento
    from bbmodel.metricas import CATALOGO
    from bbnorm5.diagnostico import datos_f1, varianza as V
    t, h = datos_f1.tabla(cfg)
    sal = C.dir_fase(cfg) / "varianza"
    sal.mkdir(parents=True, exist_ok=True)
    filas, b_filas, s2_filas = [], [], []
    with experimento("v5_f1", "varianza", params={"hash_datos": h, "hash_config": C.hash_config(cfg)}) as run:
        for col in CATALOGO:
            t0 = time.time()
            d = datos_f1.metrica(t, col, cfg["datos"]["min_minutos"])
            D = V.Datos(d["y"], d["n"], d["persona_id"], d["anio"], d["lt"], d["g_s2"])
            aj = V.ajustar(D)
            r = V.resumen(aj, d["n"].to_numpy(float), d["g_s2"].to_numpy())
            fila = {"metrica": col, "exposicion": CATALOGO[col].exposicion, "transf": CATALOGO[col].transf,
                    **{k: aj[k] for k in ("convergio", "s2a", "s2u", "s2b", "se_log_s2a", "se_log_s2u", "corr_log_a_u",
                                          "n_filas", "n_personas", "n_persona_temporadas", "K_b")},
                    "var_y": float(d["y"].var()), **r, "tiempo_s": round(time.time() - t0, 1)}
            filas.append(fila)
            b_filas += [{"metrica": col, "liga_temporada": k, "b": v} for k, v in aj["b"].items()]
            s2_filas += [{"metrica": col, "grupo": k, "s2": v} for k, v in aj["s2g"].items()]
            run.metricas({f"{col}_n_estab_temp": r["n_estab_temp"], f"{col}_rho_temp": r["rho_temp_nmedio"]})
            print(f"  {col:16s} σ²a {aj['s2a']:.4g} σ²u {aj['s2u']:.4g} σ²b {aj['s2b']:.4g} · ρ_temp {r['rho_temp_nmedio']:.2f}"
                  f" · n*_temp {r['n_estab_temp']:.0f} ({fila['exposicion']}) · {fila['tiempo_s']} s", flush=True)
    out = pd.DataFrame(filas)
    out.to_csv(sal / "componentes.csv", index=False)
    pd.DataFrame(b_filas).to_csv(sal / "efectos_liga_temporada.csv.gz", index=False)
    pd.DataFrame(s2_filas).to_csv(sal / "sigma2_por_grupo.csv", index=False)
    C.escribir_json(C.metadatos(cfg, extra={"hash_datos_entrada": h, "paso": "varianza"}), sal / "meta.json")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bbnorm5.f1")
    ap.add_argument("--config", default="configs/v5/f1.yaml")
    ap.add_argument("paso", choices=["varianza", "division", "incertidumbre", "calibracion", "nivel", "figuras"])
    a = ap.parse_args(argv)
    cfg = C.cargar(a.config)
    np.random.seed(int(cfg["semilla"]))
    t0 = time.time()
    if a.paso == "varianza":
        paso_varianza(cfg)
    else:
        from bbnorm5.diagnostico import pasos_f1
        getattr(pasos_f1, f"paso_{a.paso}")(cfg)
    print(json.dumps({"paso": a.paso, "tiempo_s": round(time.time() - t0)}))


if __name__ == "__main__":
    main()
