"""v5.1 F0 · paso 1: redes CVAE de los cortes (sólo escribe en experimentos/v3/)."""
import sys
from bbnorm3 import config as C, ablacion
from bbmodel import modelo as A
anios = [int(a) for a in sys.argv[1:]] or [2024, 2023, 2022, 2021]
cfg = C.cargar(C.RAIZ / "configs/normalization_v32.yaml")
f = ablacion._tabla_cache(cfg)
t = None if f.exists() else A.preparar()[0]
f = ablacion.guardar_tabla(t, cfg)
ablacion.entrenar([(cfg, a, s) for a in anios for s in cfg["semillas"]], cfg, f)
print("FIN_REDES", anios, flush=True)
