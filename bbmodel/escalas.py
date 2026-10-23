"""Escalas de lectura ±100 de la Mesa (Atlas de Estilos y Quintetos y conexiones).

Una sola regla para todas las cifras de nivel e impacto:

    S = 100 · tanh(z / 2),   z = (valor − referencia Euroliga) / DT de la familia

* 0 = la media de la Euroliga (de esa temporada); ±46 = una desviación típica; ±76 = dos; ±91 = tres; nunca pasa
  de ±100 (satura en los extremos y es casi lineal en el centro: |z| < 1 → pendiente ≈ 50 puntos por DT).
* Nivel (índice L de jugador; nivel conjunto de quintetos y parejas; nivel de compañeros y rivales; club):
  referencia = media de L de los jugadores de la Euroliga de la temporada, ponderada por minutos; DT = la de L
  de todos los jugadores de todas las ligas (ponderada por minutos, temporadas completas). Así la media de cada
  liga se lee directamente: «NBA +21, Liga Endesa −22».
* Impacto (net rating, on/off, RAPM, sinergia, efectos X → Y): referencia = 0 (media de la Euroliga; en las cifras
  de pista la media de cualquier liga es 0 por construcción) y DT = la de esa familia en la Euroliga.
* Percentiles: cuantiles 0-100 de cada familia en la Euroliga (y, para el nivel, de cada temporada).

Las páginas leen el bloque «escalas» de data/artifact/atlas/estilos/meta.json y de
data/artifact/quintetos/datos/indice.json (idéntico en los dos). `python -m bbmodel escalas` lo recalcula y lo
escribe en ambos ficheros sin regenerar el resto; `bbestilo exportar` y `bbmodel mesa-quintetos` también lo
incluyen.
"""
from __future__ import annotations

import glob
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
DIR_MOD = RAIZ / "data" / "modelos"
DIR_PROC = RAIZ / "data" / "processed"
REF = "euroleague"
PROVISIONALES = {"2026-27"}
FORMULA = "S = 100·tanh(z/2), z = (valor − referencia) / DT"


def _wstats(v: np.ndarray, w: np.ndarray) -> tuple[float, float]:
    ok = np.isfinite(v) & np.isfinite(w) & (w > 0)
    v, w = v[ok], w[ok]
    if not len(v):
        return float("nan"), float("nan")
    m = np.average(v, weights=w)
    return float(m), float(np.sqrt(np.average((v - m) ** 2, weights=w)))


def _wq(v: np.ndarray, w: np.ndarray, n: int = 101) -> list[float]:
    """Cuantiles ponderados 0..100."""
    ok = np.isfinite(v) & np.isfinite(w) & (w > 0)
    v, w = v[ok], w[ok]
    if not len(v):
        return []
    o = np.argsort(v)
    v, w = v[o], w[o]
    c = (np.cumsum(w) - 0.5 * w) / w.sum()
    return [round(float(x), 3) for x in np.interp(np.linspace(0, 1, n), c, v)]


def _r(x, d=4):
    return None if x is None or not np.isfinite(x) else round(float(x), d)


def _nivel() -> dict:
    p = DIR_MOD / "contexto" / "por_jugador_liga.csv"
    c = pd.read_csv(p, dtype={"player_id": str})
    c = c[np.isfinite(c["L"]) & (c["min"] > 0)]
    comp = c[~c["temporada"].isin(PROVISIONALES)]
    _, sd = _wstats(comp["L"].to_numpy(float), comp["min"].to_numpy(float))
    ref, ligas, q = {}, {}, {}
    for (t, l), g in c.groupby(["temporada", "liga"]):
        m, _ = _wstats(g["L"].to_numpy(float), g["min"].to_numpy(float))
        ligas.setdefault(t, {})[l] = _r(m)
        if l == REF:
            ref[t] = _r(m)
            q[t] = _wq(g["L"].to_numpy(float), g["min"].to_numpy(float))
    el = comp[comp["liga"] == REF]
    m_all, _ = _wstats(el["L"].to_numpy(float), el["min"].to_numpy(float))
    return {"nombre": "Nivel", "unidad": "índice L (desviaciones típicas de jugador)", "dt": _r(sd),
            "ref": ref, "ref_defecto": _r(m_all), "ligas": ligas, "q_el": q,
            "fuente": "data/modelos/contexto/por_jugador_liga.csv (L ponderado por minutos)"}


def _familia(nombre: str, unidad: str, v, w, fuente: str, ref=0.0) -> dict:
    v, w = np.asarray(v, float), np.asarray(w, float)
    m, sd = _wstats(v, w)
    return {"nombre": nombre, "unidad": unidad, "dt": _r(sd), "ref_defecto": _r(ref if ref is not None else m),
            "media_el": _r(m), "q_el": _wq(v, w), "n": int(np.isfinite(v).sum()), "fuente": fuente}


def _leer_el(nombre: str) -> pd.DataFrame:
    fr = []
    for p in sorted(glob.glob(str(DIR_PROC / "*" / "quintetos" / REF / nombre))):
        t = Path(p).parts[-4]
        if t in PROVISIONALES:
            continue
        d = pd.read_csv(p, low_memory=False)
        d["temporada"] = t
        fr.append(d)
    return pd.concat(fr, ignore_index=True) if fr else pd.DataFrame()


def calcular() -> dict:
    fam: dict[str, dict] = {}
    fam["nivel"] = _nivel()
    # impacto individual traducido a la Euroliga (dataset normalizado)
    fr = []
    for p in sorted(glob.glob(str(DIR_MOD / "normalizado" / "20*.csv"))):
        n = pd.read_csv(p, usecols=lambda c: c in {"liga", "temporada", "min", "rapm", "orapm", "drapm",
                                                    "rapm_am", "orapm_am", "drapm_am"}, low_memory=False)
        fr.append(n)
    if fr:
        n = pd.concat(fr, ignore_index=True)
        from .contexto import usar_amortiguado
        n = usar_amortiguado(n, "escalas", ["rapm", "orapm", "drapm"])
        n = n[(n["liga"] == REF) & ~n["temporada"].isin(PROVISIONALES)]
        for k, nm in (("rapm", "RAPM"), ("orapm", "ORAPM"), ("drapm", "DRAPM")):
            if k in n:
                f = _familia(nm, "pts/100 posesiones (vara Euroliga)", n[k], n["min"],
                             "data/modelos/normalizado/*.csv, jugadores de la Euroliga (ponderado por minutos)", ref=None)
                f["ref"] = {t: _r(_wstats(g[k].to_numpy(float), g["min"].to_numpy(float))[0]) for t, g in n.groupby("temporada")}
                fam[k] = f
    q = _leer_el("quintetos.csv.gz")
    if len(q):
        q = q[q["fase"] == "regular"]
        qq = q[q["poss"] >= 100]  # la dispersión «real» de los quintetos: los de muestra suficiente, Net ajustado
        fam["net_quinteto"] = _familia("Net de quinteto", "pts/100", qq["net_rtg_aj"], qq["poss"],
                                       "quintetos de la Euroliga con 100+ posesiones, temporada regular, Net ajustado, ponderado por posesiones")
        fam["sinergia_quinteto"] = _familia("Sinergia de quinteto", "pts/100 sobre lo esperado por el RAPM", qq["sinergia"], qq["poss"],
                                            "quintetos de la Euroliga con 100+ posesiones, temporada regular, ponderado por posesiones")
    t = _leer_el("trios.csv.gz")
    if len(t):
        t = t[t["fase"] == "regular"]
        tt = t[t["poss"] >= 300]
        fam["net_trio"] = _familia("Net de trío", "pts/100", tt["net_rtg_aj"], tt["poss"],
                                   "tríos de la Euroliga con 300+ posesiones, temporada regular, Net ajustado, ponderado por posesiones")
    pa = _leer_el("parejas.csv.gz")
    if len(pa):
        pa = pa[pa["fase"] == "regular"]
        pp = pa[pa["poss"] >= 500]
        fam["net_pareja"] = _familia("Net de pareja", "pts/100", pp["net_rtg_aj"], pp["poss"],
                                     "parejas de la Euroliga con 500+ posesiones, temporada regular, Net ajustado, ponderado por posesiones")
        fam["sinergia_pareja"] = _familia("Sinergia de pareja (WOWY)", "pts/100", pp["sinergia"], pp["poss"],
                                          "parejas de la Euroliga con 500+ posesiones, temporada regular, ponderado por posesiones")
        fam["sinergia_rapm"] = _familia("Sinergia frente al RAPM", "pts/100", pp["sinergia_rapm"], pp["poss"],
                                        "parejas de la Euroliga con 500+ posesiones, temporada regular, ponderado por posesiones")
    j = _leer_el("jugadores.csv")
    if len(j):
        j = j[j["fase"] == "regular"]
        jj = j[j["poss_on"] >= 500]
        fam["onoff"] = _familia("On/off", "pts/100", jj["net_rtg_onoff"], jj["poss_on"],
                                "jugadores de la Euroliga con 500+ posesiones en pista, temporada regular, ponderado por posesiones", ref=None)
        fam["rapm_liga"] = _familia("RAPM en su liga", "pts/100", j["rapm"], j["poss_on"],
                                    "jugadores de la Euroliga, temporada regular (RAPM sin traducir)", ref=None)
        fam["orapm_liga"] = _familia("ORAPM en su liga", "pts/100", j["orapm"], j["poss_on"],
                                     "jugadores de la Euroliga, temporada regular (RAPM sin traducir)", ref=None)
        fam["drapm_liga"] = _familia("DRAPM en su liga", "pts/100", j["drapm"], j["poss_on"],
                                     "jugadores de la Euroliga, temporada regular (RAPM sin traducir)", ref=None)
    e = _leer_el("equipos.csv")
    if len(e):
        e = e[e["fase"] == "regular"]
        fam["net_equipo"] = _familia("Net de equipo", "pts/100", e["net_rtg"], e["poss"],
                                     "equipos de la Euroliga, temporada regular, ponderado por posesiones")
    efs = [pd.read_csv(p) for p in sorted(glob.glob(str(DIR_MOD / "interacciones" / "efectos_*.csv.gz")))]
    if efs:
        ef = pd.concat(efs, ignore_index=True)
        ef = ef[(ef["liga"] == REF) & ~ef["temporada"].isin(PROVISIONALES)]
        for k, nm, u in (("d_cuota_tiro", "Efecto X → Y: cuota de tiro", "pp"), ("d_efg", "Efecto X → Y: eFG%", "pp"),
                         ("d_pct_asistidas", "Efecto X → Y: % asistidas", "pp"), ("d_pct_aro", "Efecto X → Y: % en el aro", "pp"),
                         ("d_pts100", "Efecto X → Y: puntos/100", "pts/100")):
            fam[k] = _familia(nm, u, ef[k], ef["sec_con"], "parejas dirigidas de la Euroliga (60+ min juntos), ponderado por segundos juntos")
    return {"version": 1, "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "formula": FORMULA,
            "referencia": REF, "factor": 2, "familias": fam}


def escribir(salida: str = "data/artifact") -> dict:
    esc = calcular()
    raiz = Path(salida)
    meta = raiz / "atlas" / "estilos" / "meta.json"
    if meta.exists():
        m = json.loads(meta.read_text(encoding="utf-8"))
        m["escalas"] = esc
        meta.write_text(json.dumps(m, ensure_ascii=False, separators=(",", ":"), default=float), encoding="utf-8")
        print(f"escalas → {meta}")
    ind = raiz / "quintetos" / "datos" / "indice.json"
    if ind.exists():
        i = json.loads(ind.read_text(encoding="utf-8"))
        i["escalas"] = esc
        ind.write_text(json.dumps(i, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"escalas → {ind}")
    return esc


if __name__ == "__main__":
    e = calcular()
    for k, f in e["familias"].items():
        print(k, f["dt"], f.get("ref_defecto"), f.get("n"))
