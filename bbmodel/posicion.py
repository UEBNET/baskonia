"""Posición: tres grupos comparables en todas las ligas.

Las fuentes publican la posición de forma distinta (Base/Escolta…, PG/SG…, G/F/C, «1/2 - Meneur»)
y EuroLeague, EuroCup y LBA no la publican. Usamos tres grupos, más robustos que cinco:
    E = exterior (bases y escoltas, 1-2)
    A = alero (3)
    I = interior (ala-pívots y pívots, 4-5)

Donde falta, se estima con una regresión logística multinomial entrenada con los jugadores que sí
tienen posición oficial. Sus rasgos son el perfil estadístico relativo a su liga y temporada
(z-scores): asistencias, rebote, tapones, triples, robos, tiros libres y pérdidas. Si la fuente da
una pista parcial (G League «F» = alero o interior), sólo se elige entre esos grupos.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

GRUPOS = ["E", "A", "I"]
NOMBRES = {"E": "Exterior", "A": "Alero", "I": "Interior"}
_A5 = {"Base": 1, "Escolta": 2, "Alero": 3, "Ala-pívot": 4, "Pívot": 5, "POINT_GUARD": 1, "SHOOTING_GUARD": 2,
       "SMALL_FORWARD": 3, "POWER_FORWARD": 4, "CENTER": 5, "PG": 1, "SG": 2, "SF": 3, "PF": 4, "C": 5, "C-F": 5}
_PISTA = {"G": ["E"], "G-F": ["E", "A"], "F-G": ["A", "E"], "F": ["A", "I"], "F-C": ["I", "A"]}
RASGOS = ["ast_pct", "oreb_p100", "dreb_p100", "blk_p100", "fg3a_rate", "stl_p100", "fta_rate", "tov_pct", "pts_p100"]


def _a_grupo(p5: int) -> str:
    return "E" if p5 <= 2 else ("A" if p5 == 3 else "I")


def oficial(raw) -> tuple[str | None, list[str] | None]:
    """(grupo exacto, o None) y (candidatos si la fuente sólo da una pista)."""
    if raw is None or (isinstance(raw, float) and np.isnan(raw)) or str(raw).strip() == "":
        return None, None
    t = str(raw).strip()
    if t in _A5:
        return _a_grupo(_A5[t]), None
    m = re.match(r"^(\d)", t)  # LNB «1/2 - Meneur/Arrière»: la primera es la principal
    if m and 1 <= int(m.group(1)) <= 5:
        return _a_grupo(int(m.group(1))), None
    if t in _PISTA:
        return None, _PISTA[t]
    return None, None


def _rasgos(t: pd.DataFrame) -> pd.DataFrame:
    """z-score de cada rasgo dentro de su liga y temporada (jugadores con 100+ minutos)."""
    X = pd.DataFrame(index=t.index)
    base = t["min"] >= 100
    for c in RASGOS:
        v = pd.to_numeric(t[c], errors="coerce")
        g = v[base].groupby([t.loc[base, "liga"], t.loc[base, "temporada"]])
        mu = g.mean().rename("mu"); sd = g.std().rename("sd")
        k = pd.MultiIndex.from_frame(t[["liga", "temporada"]])
        X[c] = ((v.to_numpy() - mu.reindex(k).to_numpy()) / sd.reindex(k).to_numpy())
    return X.clip(-4, 4)


def asignar(t: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Añade `pos3` (E/A/I) y `pos3_estimada` (0 oficial, 1 estimada, 2 elegida entre una pista)."""
    t = t.copy()
    of = t["posicion"].map(oficial)
    exacta = of.map(lambda x: x[0])
    pista = of.map(lambda x: x[1])
    X = _rasgos(t)
    completo = X.notna().all(axis=1)
    entreno = exacta.notna() & completo & (t["min"] >= 200)
    modelo = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, C=1.0))
    y = exacta[entreno].to_numpy()
    # calidad: validación cruzada y «dejando fuera una liga» (¿generaliza a una liga que no vio?)
    pred_cv = cross_val_predict(modelo, X[entreno], y, cv=5)
    info = {"acierto_cv": float(np.mean(pred_cv == y)), "n_entreno": int(entreno.sum()), "acierto_sin_su_liga": {}}
    for liga in sorted(t.loc[entreno, "liga"].unique()):
        tr = entreno & (t["liga"] != liga); te = entreno & (t["liga"] == liga)
        m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, C=1.0)).fit(X[tr], exacta[tr])
        info["acierto_sin_su_liga"][liga] = float(np.mean(m.predict(X[te]) == exacta[te]))
    modelo.fit(X[entreno], y)
    clases = list(modelo.classes_)
    proba = np.full((len(t), len(clases)), np.nan)
    proba[completo.to_numpy()] = modelo.predict_proba(X[completo])

    pos, est = [], []
    for i, (ex, pi) in enumerate(zip(exacta, pista)):
        if ex is not None and not (isinstance(ex, float) and np.isnan(ex)):
            pos.append(ex); est.append(0); continue
        if np.isnan(proba[i]).any():
            pos.append(None); est.append(None); continue
        cands = pi or clases
        p = {c: proba[i][clases.index(c)] for c in cands}
        pos.append(max(p, key=p.get)); est.append(2 if pi else 1)
    t["pos3"] = pos
    t["pos3_estimada"] = est
    return t, info


def consolidar_por_persona(t: pd.DataFrame) -> pd.DataFrame:
    """Una persona tiene la misma posición en todas sus filas: la oficial más frecuente si existe,
    si no la estimada más frecuente (ponderada por minutos). Evita que un jugador cambie de grupo
    al cambiar de liga sólo porque una fuente no publica la posición."""
    t = t.copy()
    def elegir(g):
        of = g[g["pos3_estimada"] == 0]
        base = of if len(of) else g[g["pos3"].notna()]
        if not len(base):
            return None
        return base.groupby("pos3")["min"].sum().idxmax()
    pp = t.groupby("persona_id").apply(elegir, include_groups=False)
    t["pos3"] = t["persona_id"].map(pp).where(lambda s: s.notna(), t["pos3"])
    return t
