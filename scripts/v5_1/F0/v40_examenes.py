"""v5.1 F0 · paso 6b: reproducir el examen de equipo (F4), el Nivel Kerno y el Impacto (F5 de la v4.0) con las cachés
regeneradas. Las carpetas de salida de equipo.py y anclas.py se redirigen a experimentos/v5_1/F0/v40/ y el examen del
simulador se lee de experimentos/v5_1/F0/validacion/ (el reproducido): nada se escribe en data/."""
import json, os, sys, time
from pathlib import Path
os.environ["CERNO_SIMULADOR"] = "v32"
from bbfit import validacion as V
from bbfit.sim_insumos import RAIZ
BASE = RAIZ / "experimentos" / "v5_1" / "F0"
V.DIR_VAL = BASE / "validacion"
from bbequipo import config as C, equipo as EQ, anclas as AN


def _dir(sub):
    def f(cfg):
        d = BASE / "v40" / sub
        d.mkdir(parents=True, exist_ok=True)
        return d
    return f


EQ.dir_salida = _dir("equipo")
AN.dir_salida = _dir("anclas")
cfg = C.cargar()
t0 = time.time()
que = sys.argv[1:] or ["f4", "anclas"]
cortes = None
for x in que:
    if x.startswith("cortes="):
        cortes = [int(a) for a in x.split("=")[1].split(",")]
if "f4" in que:
    r4 = EQ.main(cfg, cortes=cortes)
    print("FIN_F4", round(time.time() - t0), flush=True)
if "anclas" in que:
    ra = AN.main(cfg)
    print("FIN_ANCLAS", round(time.time() - t0), flush=True)
