"""v5.1 F0 · paso 2: algoritmo A ajustado hasta cada corte (sólo escribe en experimentos/cache_normalizacion/)."""
import pickle, sys, time
from bbmodel import modelo, amortiguacion as AM
a = int(sys.argv[1])
f = AM.DIR_CACHE / f"A_hasta_{a}.pkl"
if f.exists():
    print("ya estaba", f, flush=True); sys.exit(0)
t0 = time.time()
t = modelo.preparar()[0]
nb = int(AM.config()["validacion"]["bootstrap"])
r = modelo.ajustar(t, hasta_anio=a, n_boot=nb, progreso=None)
tmp = f.with_suffix(".tmp"); tmp.write_bytes(pickle.dumps(r)); tmp.replace(f)
print("FIN_A", a, round(time.time() - t0), "s", flush=True)
