"""v5.1 F0 · paso 4: reproducir el examen de fichajes del simulador v3.2 (V32_corte, inicio, adaptación) con las cachés
regeneradas. La configuración se pone en estado de examen SÓLO en memoria (como bbfit.v32.config_examen, sin escribir el
fichero versionado) y backtest(guardar=True): nada se escribe fuera de experimentos/."""
import json, os, pickle, sys, time
os.environ["CERNO_SIMULADOR"] = "v32"
VARIANTE = sys.argv[2] if len(sys.argv) > 2 else ""
if VARIANTE:
    os.environ["CERNO_SIM_VARIANTE"] = VARIANTE          # p. ej. sin_adaptacion (NK₂)
from bbfit import config as BC
c = BC.cargar("simulation")                       # dict en caché: las lecturas siguientes devuelven este objeto
apagados = {x.removeprefix("sin_") for x in VARIANTE.split("+") if x}
for p in ("redistribuir_uso", "uso_eficiencia", "companeros", "adaptacion", "ruido_personal"):
    c["pasos"][p] = p not in apagados
c["produccion"]["factor_ajustes_ts"] = [1.0, 1.0]
c["v32"]["produccion_publicada"] = "motor"
c["v32"]["aplicar_recalibracion"] = False
from bbfit import validacion as V
from bbfit.sim_insumos import RAIZ
out = RAIZ / "experimentos" / "v5_1" / "F0"
out.mkdir(parents=True, exist_ok=True)
# resultados completos (predicciones por fichaje) en experimentos/, no en la carpeta versionada
V.DIR_VAL = out / "validacion"
V.DIR_VAL.mkdir(parents=True, exist_ok=True)
fase = sys.argv[1]
t0 = time.time()
if fase == "v32":
    r = V.backtest("V32", "inicio", adaptacion=True, guardar=True)
else:
    r = V.backtest("V32_corte", "inicio", adaptacion=True, pesos_de="V32_inicio_adapt", guardar=True)
(out / f"resumen_{fase}{'_' + VARIANTE if VARIANTE else ''}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str))
print("FIN_EXAMEN", fase, round(time.time() - t0), flush=True)
