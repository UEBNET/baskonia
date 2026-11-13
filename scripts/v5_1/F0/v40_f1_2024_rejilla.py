"""v5.1 F0 · ajuste F1 del corte 2024 con la rejilla reducida del producto (configs/equipo_v40.yaml §f1.producto:
τ ∈ {1, 2, 3}, α = 1; los cuatro cortes publicados eligieron τ* = 1 → 2 tras el GBM y α* = 1). Se guarda con la huella de
la configuración completa para que los exámenes lo reutilicen, con una nota al lado. Sólo escribe en experimentos/v4_0/."""
import json, pickle, time
from bbequipo import config as C, rapm as RP, examen_f1 as EX
cfg = C.cargar()
a = 2024
huella = RP.huella_ajuste(cfg)
dest = C.RAIZ / "experimentos" / "v4_0" / f"ajuste_f1_{a}_gbm_{huella}.pkl"
cfg_r = C.con(cfg, **{"f1.bayes_empirico.tau_rejilla": [1.0, 2.0, 3.0], "f1.prior.ridge_alpha_rejilla": [1.0]})
t0 = time.time()
tr = RP.tramos(cfg)
tr = tr[tr["anio"] <= a].reset_index(drop=True)
T = RP.tabla_prior(EX.perfiles_corte(cfg, a), cfg)
D = RP.construir_diseno(tr, "net")
res = RP.ajustar(D, T, cfg_r, "gbm", ())
dest.write_bytes(pickle.dumps({k: v for k, v in res.items() if k != "XZ"}))
nota = {"corte": a, "rejilla_tau": [1.0, 2.0, 3.0], "rejilla_alpha": [1.0], "motivo": "rejilla completa > 3 h; v5.1 F0",
        "historial": [{k: v for k, v in h.items() if k != "log_marginal_por_alpha_tau"} for h in res.get("historial", [])],
        "tiempo_s": round(time.time() - t0)}
dest.with_suffix(".nota.json").write_text(json.dumps(nota, indent=1, default=str))
print("FIN_2024", round(time.time() - t0), flush=True)
