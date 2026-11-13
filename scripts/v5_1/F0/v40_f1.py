"""v5.1 F0 · paso 6a: tramos y ajustes F1 por corte del RAPM multiliga (sólo escribe en experimentos/v4_0/)."""
import time
from bbequipo import config as C, rapm as RP, examen_f1 as EX
cfg = C.cargar()
t0 = time.time()
tr = RP.tramos(cfg)
print("tramos", len(tr), round(time.time() - t0), flush=True)
for a in [2021, 2022, 2023, 2024]:
    EX.ajuste_corte(cfg, a, tr, "gbm")
    print("ajuste_f1", a, round(time.time() - t0), flush=True)
print("FIN_V40_F1", flush=True)
