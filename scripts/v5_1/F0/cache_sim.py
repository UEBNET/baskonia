"""v5.1 F0 · paso 3: cachés del simulador v3.2 (sólo escribe en experimentos/)."""
import os, sys, time
os.environ["CERNO_SIMULADOR"] = "v32"
from bbfit import simulador as S, sim_insumos as SI
parte = sys.argv[1] if len(sys.argv) > 1 else "todo"
t0 = time.time()
if parte in ("todo", "v32"):
    print("dataset", SI.dataset_simulador(progreso=None), flush=True)
if parte in ("todo", "v32"):
    for t in ["2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]:
        S.cargar_corte(t, "V32", pesos=False); print("V32", t, round(time.time() - t0), flush=True)
if parte in ("todo", "corte"):
    for t in ["2021-22", "2022-23", "2023-24", "2024-25"]:
        S.cargar_corte(t, "V32_corte", pesos=False); print("V32_corte", t, round(time.time() - t0), flush=True)
print("FIN_SIM", flush=True)
