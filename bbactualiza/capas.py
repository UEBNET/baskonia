"""Capas que dependen de los partidos de la temporada en curso, aplicadas sólo a esa temporada.

Regla común: los ficheros que guardan TODAS las temporadas se reescriben sustituyendo sólo las filas de la temporada en
curso (`empalmar`); el histórico queda byte a byte como estaba salvo que la orden original lo reescriba de forma
determinista (estilos unificados con la mezcla guardada, entropía).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from . import TEMPORADA

RAIZ = Path(__file__).resolve().parent.parent
MOD = RAIZ / "data" / "modelos"


def empalmar(ruta: Path, nuevo: pd.DataFrame, temporada: str = TEMPORADA, col: str = "temporada", **to_csv) -> int:
    """Sustituye en `ruta` (CSV, también .gz) las filas de `temporada` por las de `nuevo`. Devuelve filas nuevas."""
    ruta = Path(ruta)
    nuevo = nuevo[nuevo[col] == temporada]
    if ruta.exists():
        viejo = pd.read_csv(ruta, low_memory=False, dtype=str, keep_default_na=False, na_values=[""])
        cols = list(viejo.columns) + [c for c in nuevo.columns if c not in viejo.columns]
        es = (viejo[col] == temporada).to_numpy()
        corte = int(np.argmax(es)) if es.any() else len(viejo)     # las filas nuevas van donde estaban las viejas
        antes, despues = viejo.iloc[:corte], viejo.iloc[corte:]
        # el histórico se reescribe con sus mismos textos (dtype=str); las filas nuevas, con el formato de to_csv
        out = pd.concat([antes[antes[col] != temporada],
                         _como_texto(nuevo.reindex(columns=cols), to_csv.get("float_format")),
                         despues[despues[col] != temporada]], ignore_index=True)[cols]
    else:
        out = nuevo
    out.to_csv(ruta, index=False, **({} if ruta.exists() else to_csv))
    return int(len(nuevo))


def _como_texto(df: pd.DataFrame, float_format: str | None) -> pd.DataFrame:
    """Filas como las escribiría to_csv (mismo texto por celda), leídas de vuelta como texto."""
    import io
    buf = io.StringIO()
    df.to_csv(buf, index=False, float_format=float_format)
    buf.seek(0)
    return pd.read_csv(buf, dtype=str, keep_default_na=False, na_values=[""])


# ============================================================================================ pista e interacciones
def pista(temporada: str = TEMPORADA) -> int:
    """Rasgos de pista de la temporada; la calibración de zonas de las demás temporadas se conserva."""
    from bbmodel import pista as P
    cal_f = P.DIR_SALIDA / "calibracion.json"
    cal = json.loads(cal_f.read_text(encoding="utf-8")) if cal_f.exists() else {}
    nueva: dict = {}
    frames = [P.filas_liga(d.name, temporada, nueva) for d in sorted((P.DIR_PROC / temporada / "quintetos").iterdir())]
    df = pd.concat(frames, ignore_index=True)
    df.round(4).to_csv(P.DIR_SALIDA / f"{temporada}.csv", index=False)
    cal = {k: v for k, v in cal.items() if not k.endswith("|" + temporada)}
    cal.update(nueva)
    cal_f.write_text(json.dumps(cal, indent=1, ensure_ascii=False), encoding="utf-8")
    return int(len(df))


def interacciones(temporada: str = TEMPORADA) -> int:
    from bbmodel import interacciones as I
    return int(len(I.construir([temporada])))


def nacionalidades(temporada: str = TEMPORADA) -> int:
    """Nacionalidades (reglas, sin red) y sólo las filas de la temporada en el CSV global."""
    from bbmodel import nacionalidad as N
    return empalmar(N.SALIDA, N.construir(), temporada)


def contexto(temporada: str = TEMPORADA) -> int:
    """Contexto de nivel con la escala fija 2020-26 (sin la regresión de sensibilidad, que es un ajuste)."""
    from bbmodel import contexto as C
    ctx = C.construir(guardar=False)
    cols = ["liga", "temporada", "team_id", "player_id", "pid_modelo", "nombre", "min", "L", "L_usado",
            "ctx_plantilla", "ctx_plantilla_dev", "sec_pista", "ctx_comp_pista", "ctx_riv_pista",
            "ctx_comp", "ctx_comp_dev", "ctx_riv", "ctx_riv_dev", "fuente_ctx",
            "ctx_plantilla_ref", "ctx_comp_ref", "ctx_riv_ref", "L_banquillo"]
    g = ctx[ctx["temporada"] == temporada]
    g[cols].round(4).to_csv(C.DIR_SALIDA / f"{temporada}.csv", index=False)
    jl = C.por_jugador_liga(ctx).round(4)
    return empalmar(C.DIR_SALIDA / "por_jugador_liga.csv", jl, temporada)


# ============================================================================================ encaje
def roles(temporada: str = TEMPORADA) -> int:
    """Roles por minutos y tramos (reglas y BOCPD por jugador, sin parámetros que ajustar) de la temporada, empalmados
    en las salidas globales de data/modelos/roles (`roles.consolidar` reescribiría todo con sólo las cachés locales)."""
    from bbfit import roles as R
    R.construir([temporada], rehacer=True)
    cfg = R._cfg()
    tramos, temps, partidos = [], [], []
    for p in sorted(R.DIR_CACHE.glob(f"{temporada}_*.pkl")):
        r = pd.read_pickle(p)
        if len(r["tramos"]):
            tramos.append(r["tramos"])
        if len(r["temporada"]):
            temps.append(r["temporada"])
        if len(r["partidos"]):
            partidos.append(r["partidos"])
    sp, tr = pd.concat(tramos, ignore_index=True), pd.concat(temps, ignore_index=True)
    caja = tr[tr["fuente"] == "box"].copy()
    caja["tramo"] = 1
    caja["motivo_inicio"] = "temporada_caja"
    sp = pd.concat([sp, caja[[c for c in caja.columns if c in sp.columns or c == "tramo"]]], ignore_index=True)
    nom = tr.drop_duplicates(["liga", "temporada", "player_id"]).set_index(["liga", "temporada", "player_id"])["nombre"]
    sp["nombre"] = [nom.get(k, np.nan) for k in zip(sp["liga"], sp["temporada"], sp["player_id"])]
    sp = sp.rename(columns={"inicio_fecha": "inicio", "fin_fecha": "fin", "gp": "n_partidos"})
    empalmar(R.DIR_ROLES / "player_role_spells.csv.gz", sp, temporada, float_format="%.4f")
    n = empalmar(R.DIR_ROLES / "player_role_season.csv.gz", tr, temporada, float_format="%.4f")
    empalmar(R.DIR_ROLES / "team_role_structure.csv", R.estructura_equipos(tr, cfg), temporada, float_format="%.4f")
    if partidos:
        pd.concat(partidos, ignore_index=True).to_csv(R.DIR_ROLES / "partidos_jugador" / f"{temporada}.csv.gz",
                                                     index=False, float_format="%.4f")
    return n


def entropia(temporada: str = TEMPORADA) -> dict:
    """Entropía y volatilidad. La orden se rehace entera (la contracción agrupa temporadas), pero su muestreo Monte Carlo
    consume la secuencia aleatoria liga a liga: con filas nuevas, el histórico se movería en los decimales. Por eso se
    guarda una copia antes y se empalman sólo las filas de la temporada en curso."""
    import shutil
    import tempfile
    from bbfit import entropia as E
    d = MOD / "entropia"
    ficheros = [d / "jugadores.csv.gz", d / "equipos.csv"]
    tmp = Path(tempfile.mkdtemp())
    for f in ficheros:
        if f.exists():
            shutil.copy(f, tmp / f.name)
    res = E.main(None)
    for f in ficheros:
        if (tmp / f.name).exists():
            nuevo = pd.read_csv(f, low_memory=False)
            shutil.copy(tmp / f.name, f)
            empalmar(f, nuevo, temporada, float_format="%.4f")
    shutil.rmtree(tmp, ignore_errors=True)
    return res


def estilos() -> dict:
    """Estilos unificados: la mezcla se ajusta sólo con 2020-26 y semilla fija (= la guardada); 2026-27 se asigna."""
    from bbfit import estilos_unificados as EU
    return EU.ejecutar(reusar_k=True)


# ============================================================================================ simulador
def _sim(version: str = "v33"):
    os.environ["CERNO_SIMULADOR"] = version


def simulador(salida: Path) -> dict:
    """Dataset del simulador v3.3 (v3.2 + Tercera FEB con la v2) y exportación al navegador (pesos congelados)."""
    _sim("v33")
    import shutil
    from bbfit import sim_exportar as E
    from bbfit import sim_insumos as SI
    SI.dataset_simulador(progreso=None)
    # piezas ajustadas con temporadas ≤ t de las temporadas base (2024-25, 2025-26): sólo dependen del histórico,
    # que no cambia; se guardan congeladas y se ahorran ≈ 4,5 min por actualización. La de la temporada en curso se rehace.
    SI.DIR_CACHE.mkdir(parents=True, exist_ok=True)
    for f in sorted((MOD / "simulador" / "v3_3" / "congelado").glob("modelos_hasta_*.pkl")):
        if TEMPORADA not in f.name and not (SI.DIR_CACHE / f.name).exists():
            shutil.copy(f, SI.DIR_CACHE / f.name)
    return E.exportar(salida)
