"""Datos del Atlas de Estilos (artifact/estilos/), red VaDE v2 (8 estilos, nivel neutralizado).

    estilos/meta.json        rasgos, escalas, índice de nivel y neutralizador, pesos de la red, los 8 estilos
                             (nombre, perfil, elipsoide en el mapa, ligas), nombres de los ejes, evaluación,
                             comparativa con IDEC y con la v1, análisis complementarios y referencias
    estilos/clubes.json      un registro por club-competición-temporada: mapa, estilo y 8 salidas, nivel,
                             entrada de la red y sumas ponderadas para simular fichajes en el navegador
    estilos/jugadores.json   un registro por jugador-equipo-temporada (100+ min): mapa, estilo, nivel y sus
                             filas «crudas» (estilo y calidad) para simular su fichaje

Formato columnar {"columnas": [...], "filas": [[...]]}.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from .datos import CRUDAS, _I
from .encaje import conjunto, red_guardada, referencias_distancia
from .evaluar import predecir

RED = "vade"


def _r(x, d=4):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return x
    return None if not np.isfinite(x) else round(x, d)


def _lista(a, d=3):
    return [_r(x, d) for x in np.asarray(a, float).ravel()]


def _columnar(df: pd.DataFrame, dec: dict | None = None) -> dict:
    dec = dec or {}
    filas = []
    for fila in df.itertuples(index=False):
        filas.append([_r(v, dec.get(c, 4)) if isinstance(v, (float, np.floating)) else
                      (v.item() if isinstance(v, np.generic) else v) for c, v in zip(df.columns, fila)])
    return {"columnas": list(df.columns), "filas": filas}


MODELOS = {"k8": ("", "estilos_v2.json"), "k6": ("k6", "estilos_k6.json")}   # carpeta (bajo DIR_SALIDA) y nombres


def nombres_estilos(archivo: str = "estilos_v2.json") -> dict:
    p = C.RAIZ / "config" / archivo
    try:
        return {k: v for k, v in json.loads(p.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    except FileNotFoundError:
        return {}


def ejes(Z: np.ndarray, X: np.ndarray) -> list[dict]:
    """Nombre de cada eje del mapa: los rasgos (entrada sin nivel) más correlacionados con él."""
    out = []
    for j in range(Z.shape[1]):
        r = np.array([np.corrcoef(Z[:, j], X[:, k])[0, 1] for k in range(X.shape[1])])
        pos, neg = np.argsort(-r)[:2], np.argsort(r)[:2]
        out.append({"r": _lista(r, 3),
                    "positivo": [C.RASGOS[k].corto for k in pos if r[k] > 0.25],
                    "negativo": [C.RASGOS[k].corto for k in neg if r[k] < -0.25]})
    return out


def _modelo(cj, carpeta: Path, nombres: dict) -> tuple[dict, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Bloque de meta de un modelo y sus predicciones (clubes y jugadores)."""
    red = red_guardada(RED, carpeta)
    rd = carpeta / RED
    ev = json.loads((carpeta / "evaluacion.json").read_text(encoding="utf-8"))
    comp = pd.read_csv(carpeta / "comparativa.csv")
    an = carpeta / "analisis.json"
    est = pd.read_csv(rd / "estilos.csv")
    pesos = json.loads((rd / "pesos.json").read_text(encoding="utf-8"))
    P, Z = predecir(red, cj.Xc)
    sel = cj.clubes["temporada"].isin(C.TEMPORADAS_ENTRENO).to_numpy()
    # elipsoides de los estilos en coordenadas del mapa: Σ_mapa = s² Rᵀ Σ R
    rot, esc = np.array(pesos["mapa"]["rot"]), pesos["mapa"]["escala"]
    estilos = []
    for k, fila in est.iterrows():
        cm = esc ** 2 * rot.T @ np.array(pesos["salida"]["cov"][k]) @ rot
        n = nombres.get(fila["estilo"], {})
        estilos.append({"id": fila["estilo"], "nombre": n.get("nombre", fila["estilo"]), "resumen": n.get("resumen", ""),
                        "descriptor": fila["descriptor"], "clubes": int(fila["clubes"]), "nivel_medio": _r(fila["nivel_medio"], 3),
                        "centro": [_r(fila["x"], 4), _r(fila["y"], 4), _r(fila["z"], 4)], "cov_mapa": [_lista(f, 5) for f in cm],
                        "perfil": [_r(fila[f"z_{c}"], 3) for c in C.COLS], "ligas": json.loads(fila["ligas"].replace("'", '"')),
                        "ejemplos": fila["ejemplos"]})
    ref = referencias_distancia(red, cj)
    bloque = {"n_estilos": len(est), "pesos": pesos, "estilos": estilos, "ejes": ejes(Z[sel], cj.Xc[sel]),
              "evaluacion": {k: v for k, v in ev[RED].items() if k != "ari_matriz"},
              "evaluacion_idec": {k: v for k, v in ev["idec"].items() if k != "ari_matriz"},
              "referencia_kmedias": ev.get("referencia_kmedias"), "comparativa": json.loads(comp.to_json(orient="records")),
              "analisis": json.loads(an.read_text(encoding="utf-8")) if an.exists() else None,
              "referencias": {k: _lista(np.percentile(v, np.linspace(0, 100, 101)), 4) for k, v in ref.items()}}
    m = (cj.jugadores["min"] >= C.MIN_JUGADOR).to_numpy()
    Pj, Zj = predecir(red, cj.Xj[m])
    rob = pd.read_csv(rd / "clubes.csv")
    assert (rob["clave"].to_numpy() == cj.clubes["clave"].to_numpy()).all(), "clubes.csv no corresponde a los datos"
    return bloque, P, Z, rob["robustez"].to_numpy(), Pj, Zj


def comparar_modelos(cj, carpetas: dict) -> dict:
    """Correspondencia entre las particiones de dos modelos sobre los clubes de entrenamiento."""
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score
    sel = cj.clubes["temporada"].isin(C.TEMPORADAS_ENTRENO).to_numpy()
    lab = {k: predecir(red_guardada(RED, d), cj.Xc[sel])[0].argmax(1) for k, d in carpetas.items()}
    if len(lab) < 2:
        return {}
    (a, la), (b, lb) = list(lab.items())[:2]
    tab = pd.crosstab(pd.Series(la, name=a), pd.Series(lb, name=b))
    return {"modelos": [a, b], "ari": float(adjusted_rand_score(la, lb)), "nmi": float(normalized_mutual_info_score(la, lb)),
            "tabla": tab.to_numpy().tolist(),
            "pureza": float(tab.max(1).sum() / tab.to_numpy().sum())}


def main(salida: str) -> None:
    d = Path(salida)
    d.mkdir(parents=True, exist_ok=True)
    cj = conjunto()
    carpetas = {k: C.DIR_SALIDA / sub for k, (sub, _) in MODELOS.items() if (C.DIR_SALIDA / sub / RED / "modelo.pt").exists()}
    v1 = C.DIR_SALIDA / "v1_12estilos" / "evaluacion.json"
    from .similares import referencias as ref_parecido
    meta = {"generado": date.today().isoformat(), "red": RED, "modelos": {}, "modelo_defecto": "k8",
            "rasgos": [r.__dict__ for r in C.RASGOS], "crudas": CRUDAS, "nivel_cols": list(C.NIVEL),
            "escala_club": cj.escala_club.a_dict(), "escala_jugador": cj.escala_jugador.a_dict(),
            "nivel_club": cj.nivel_club.a_dict(), "nivel_jugador": cj.nivel_jugador.a_dict(),
            "neutral_club": cj.neutral_club.a_dict(), "neutral_jugador": cj.neutral_jugador.a_dict(),
            "grado_neutralizacion": C.GRADO_NEUTRALIZACION,
            "temporadas_entreno": C.TEMPORADAS_ENTRENO, "temporadas_provisionales": C.TEMPORADAS_PROVISIONALES,
            "min_jugador": C.MIN_JUGADOR,
            "evaluacion_v1": (json.loads(v1.read_text(encoding="utf-8")).get("vade") if v1.exists() else None),
            "similitud": {k: _lista(v, 4) for k, v in ref_parecido(cj).items()},
            "comparacion_modelos": comparar_modelos(cj, carpetas),
            "clubes_con_nombre": {k: v for k, v in json.loads(C.CLUBES.read_text(encoding="utf-8")).items() if not k.startswith("_")}}

    # ---- clubes (comunes) y jugadores (comunes)
    from .analisis import _equipos
    eq = _equipos()
    c = cj.clubes[["clave", "clave_club", "nombre_club", "liga", "temporada", "team_id", "provisional", "min_total",
                   "jugadores", "cobertura_ab", "nivel"]].copy()
    c = c.merge(eq[["liga", "temporada", "team_id", "net_z"]], on=["liga", "temporada", "team_id"], how="left")
    assert (c["clave"].to_numpy() == cj.clubes["clave"].to_numpy()).all()
    c["X"] = [_lista(x, 3) for x in cj.Xc]
    S, W, SQ, WQ = [], [], [], []
    for k in c["clave"]:
        R, w, _, Q = cj.plantillas[k]
        ok, okq = np.isfinite(R), np.isfinite(Q)
        u2 = R[:, _I["usg_pct"]] ** 2
        S.append(_lista(list((np.where(ok, R, 0) * w[:, None]).sum(0)) + [np.nansum(u2 * w)], 3))
        W.append(_lista(list((ok * w[:, None]).sum(0)) + [(np.isfinite(u2) * w).sum()], 2))
        SQ.append(_lista((np.where(okq, Q, 0) * w[:, None]).sum(0), 3))
        WQ.append(_lista((okq * w[:, None]).sum(0), 2))
    c["S"], c["W"], c["SQ"], c["WQ"] = S, W, SQ, WQ
    c = c.drop(columns=["team_id"])
    m = (cj.jugadores["min"] >= C.MIN_JUGADOR).to_numpy()
    J = cj.jugadores.loc[m, ["nombre", "clave", "nombre_club", "liga", "temporada", "pos3", "min", "nivel", "fuente_norm",
                             "provisional", "persona_id", "player_id"]].copy()
    J["edad"] = J["temporada"].str[:4].astype(int) - pd.to_numeric(cj.jugadores.loc[m, "anio_nac"], errors="coerce")
    pos_R, pos_Q = {}, {}
    for _, (R, w, idx, Q) in cj.plantillas.items():
        for k, i in enumerate(idx):
            pos_R[i], pos_Q[i] = R[k], Q[k]
    J["R"] = [_lista(pos_R[i], 3) for i in J.index]
    J["Q"] = [_lista(pos_Q[i], 3) for i in J.index]
    J["persona_id"] = J["persona_id"].where(J["persona_id"].notna(), J["liga"] + ":" + J["player_id"].astype(str))
    J = J.drop(columns=["player_id"])

    # ---- cada modelo: su bloque de meta y sus columnas
    dec = {"nivel": 3, "net_z": 3, "min": 0, "min_total": 0, "cobertura_ab": 3, "edad": 1}
    for k, carpeta in carpetas.items():
        bloque, P, Z, rob, Pj, Zj = _modelo(cj, carpeta, nombres_estilos(MODELOS[k][1]))
        meta["modelos"][k] = bloque
        c[f"{k}_x"], c[f"{k}_y"], c[f"{k}_z"] = Z[:, 0], Z[:, 1], Z[:, 2]
        c[f"{k}_e"], c[f"{k}_p"], c[f"{k}_rob"] = P.argmax(1), P.max(1), rob
        c[f"{k}_probs"] = [_lista(p, 3) for p in P]
        J[f"{k}_x"], J[f"{k}_y"], J[f"{k}_z"] = Zj[:, 0], Zj[:, 1], Zj[:, 2]
        J[f"{k}_e"], J[f"{k}_p"] = Pj.argmax(1), Pj.max(1)
        dec.update({f"{k}_{x}": 3 for x in ("x", "y", "z", "p", "rob")})
    for nombre, obj in (("meta.json", meta), ("clubes.json", _columnar(c, dec)), ("jugadores.json", _columnar(J, dec))):
        (d / nombre).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=float), encoding="utf-8")
    print("escrito", d, list(carpetas), {p.name: p.stat().st_size for p in d.glob("*.json")})
