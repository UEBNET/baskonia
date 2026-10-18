"""Datos del Atlas de Estilos (artifact/estilos/), modelo final: VaDE de 6 estilos con el nivel neutralizado.

    estilos/meta.json        rasgos, escalas, índice de nivel y neutralizador, pesos de la red, los 6 estilos
                             (nombre, perfil, elipsoide en el mapa, ligas), nombres de los ejes, evaluación,
                             análisis complementarios, referencias y evolución de las iteraciones (historial/)
    estilos/clubes.json      un registro por club-competición-temporada: mapa, estilo y 6 salidas, nivel,
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


NOMBRES = "estilos.json"     # config/: nombre y resumen de cada estilo del modelo final
DIR_HISTORIAL = C.DIR_SALIDA / "historial"
ITERACIONES = [   # (id, carpeta en historial/ o "" = modelo final, red, etiqueta)
    ("v1_vade", "v1_12estilos", "vade", "v1 · VaDE 12"),
    ("v1_idec", "v1_12estilos", "idec", "v1 · IDEC 12"),
    ("v2_vade", "v2_8estilos", "vade", "v2 · VaDE 8"),
    ("v2_idec", "v2_8estilos", "idec", "v2 · IDEC 8"),
    ("v3_vade", "v3_6estilos", "vade", "v3 · VaDE 6 (5 semillas)"),
    ("v4_vade", "v4_6estilos_box", "vade", "v4 · VaDE 6 (13 rasgos de caja)"),
    ("v5_vade", "v5_6estilos_8ligas", "vade", "v5 · VaDE 6 (17 rasgos, 8 ligas)"),
    ("final", "", "vade", "Final · VaDE 6 (17 rasgos, 12 ligas, entrenadores)"),
]
# Métricas normalizadas de cada jugador que el Atlas proyecta al contexto del equipo de destino
CLAVE_CTX = ["usg_pct", "pts_p100", "ts_pct", "efg_pct", "ast_pct", "tov_pct", "dreb_pct", "drtg", "per",
             "ws_per_40", "rapm", "pct_asistidas", "pct_t3_esquina"]


def _normalizados() -> pd.DataFrame:
    """Dataset normalizado (bbmodel) indexado por (liga, temporada, id del modelo)."""
    from bbmodel.nacionalidad import id_modelo
    fr = []
    for p in sorted((C.RAIZ / "data" / "modelos" / "normalizado").glob("*.csv")):
        n = pd.read_csv(p, dtype={"player_id": str}, low_memory=False)
        n["pid_modelo"] = id_modelo(n["liga"], n["player_id"], n["nombre"])
        fr.append(n)
    n = pd.concat(fr, ignore_index=True)
    return n.drop_duplicates(["liga", "temporada", "pid_modelo"]).set_index(["liga", "temporada", "pid_modelo"])


def contexto_meta() -> dict | None:
    """Sensibilidad al contexto (bbmodel/contexto.py) de las métricas clave y contexto de referencia."""
    ps = C.RAIZ / "data" / "modelos" / "contexto" / "sensibilidad.csv"
    pa = C.RAIZ / "data" / "modelos" / "algoritmo_A" / "parametros.json"
    if not ps.exists() or not pa.exists():
        return None
    from bbmodel.metricas import CATALOGO
    sens = pd.read_csv(ps).set_index("metrica")
    par = json.loads(pa.read_text(encoding="utf-8"))["metricas"]
    mets = []
    for c in CLAVE_CTX:
        if c not in sens.index or c not in par:
            continue
        r = sens.loc[c]
        t2 = par[c]["suerte"]["tau2"]
        claro = abs(r["beta_comp"]) > 2 * r["beta_comp_se"]
        mets.append({"col": c, "nombre": CATALOGO[c].nombre, "transf": CATALOGO[c].transf, "sentido": CATALOGO[c].sentido,
                     "beta": _r(r["beta_comp"] if claro else 0.0, 4), "beta_estimado": _r(r["beta_comp"], 4),
                     "se": _r(r["beta_comp_se"], 4), "claro": bool(claro),
                     "tau": {p_: _r(np.sqrt(t2.get(f"euroleague|{p_}", np.nan)), 5) for p_ in ("E", "A", "I")}})
    ctx = pd.concat([pd.read_csv(p) for p in sorted((C.RAIZ / "data" / "modelos" / "contexto").glob("20*.csv"))])
    ref = (ctx[ctx["liga"] == "euroleague"].groupby("temporada")["ctx_plantilla_ref"].first().round(4).to_dict())
    todas = pd.read_csv(ps)
    return {"metricas": mets, "ref_euroleague": ref,
            "sensibilidad": [{k: (_r(v, 4) if isinstance(v, (float, np.floating)) else v) for k, v in fila.items()}
                             for fila in todas.to_dict("records")],
            "nota": "Proyección al contexto del destino: en la escala transformada de cada métrica, "
                    "x_destino = T⁻¹(T(x_normalizado) + τ_pos · β · (Δ contexto)), con Δ contexto = nivel medio de los "
                    "compañeros en el destino (ponderado por minutos, sin él) − contexto de su equipo de origen. "
                    "β sólo se aplica si es claro (|β| > 2 errores típicos)."}


def nombres_estilos(archivo: str = NOMBRES) -> dict:
    p = C.RAIZ / "config" / archivo
    try:
        return {k: v for k, v in json.loads(p.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    except FileNotFoundError:
        return {}


def evaluacion_iteracion(carpeta: str, red: str) -> dict | None:
    """Evaluación guardada de una iteración (historial/) o del modelo final (carpeta = "")."""
    p = (DIR_HISTORIAL / carpeta if carpeta else C.DIR_SALIDA) / "evaluacion.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8")).get(red)


def historial() -> list[dict]:
    """Métricas clave de cada iteración para la tabla de evolución del modelo."""
    claves = ["salida_max_media", "tamano_min", "eta2_nivel", "nmi_estilo_liga", "ari_semillas_medio",
              "ari_final_semillas_medio", "estabilidad_mapa", "ari_temporal_reserva", "robustez_reparto_minutos",
              "silueta_rasgos", "trustworthiness_k10"]
    out = []
    for id_, carpeta, red, etiqueta in ITERACIONES:
        ev = evaluacion_iteracion(carpeta, red)
        if ev is None:
            continue
        fila = {"id": id_, "etiqueta": etiqueta, "k": len(ev["tamanos"]), **{k: _r(ev.get(k)) for k in claves}}
        fila["mahalanobis_min"] = _r(ev["diferenciacion"]["mahalanobis_min"])
        fila["parejas"] = f'{ev["diferenciacion"]["pares_distintos_holm_05"]}/{ev["diferenciacion"]["pares"]}'
        fila["replicabilidad"] = _r(ev["replicabilidad"]["correlacion_media"])
        out.append(fila)
    return out


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


def main(salida: str) -> None:
    d = Path(salida)
    d.mkdir(parents=True, exist_ok=True)
    cj = conjunto()
    red = red_guardada(RED)
    rd = C.DIR_SALIDA / RED
    ev = json.loads((C.DIR_SALIDA / "evaluacion.json").read_text(encoding="utf-8"))
    an = C.DIR_SALIDA / "analisis.json"
    est = pd.read_csv(rd / "estilos.csv")
    pesos = json.loads((rd / "pesos.json").read_text(encoding="utf-8"))
    rob = pd.read_csv(rd / "clubes.csv")
    assert (rob["clave"].to_numpy() == cj.clubes["clave"].to_numpy()).all(), "clubes.csv no corresponde a los datos"
    P, Z = predecir(red, cj.Xc)
    sel = cj.clubes["temporada"].isin(C.TEMPORADAS_ENTRENO).to_numpy()
    nombres = nombres_estilos()
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
    from .similares import referencias as ref_parecido
    meta = {"generado": date.today().isoformat(), "red": RED, "n_estilos": len(est),
            "rasgos": [r.__dict__ for r in C.RASGOS], "crudas": CRUDAS, "nivel_cols": list(C.NIVEL),
            "escala_club": cj.escala_club.a_dict(), "escala_jugador": cj.escala_jugador.a_dict(),
            "nivel_club": cj.nivel_club.a_dict(), "nivel_jugador": cj.nivel_jugador.a_dict(),
            "neutral_club": cj.neutral_club.a_dict(), "neutral_jugador": cj.neutral_jugador.a_dict(),
            "grado_neutralizacion": C.GRADO_NEUTRALIZACION,
            "temporadas_entreno": C.TEMPORADAS_ENTRENO, "temporadas_provisionales": C.TEMPORADAS_PROVISIONALES,
            "min_jugador": C.MIN_JUGADOR, "pesos": pesos, "estilos": estilos, "ejes": ejes(Z[sel], cj.Xc[sel]),
            "evaluacion": {k: v for k, v in ev[RED].items() if k != "ari_matriz"},
            "referencia_kmedias": ev.get("referencia_kmedias"),
            "analisis": json.loads(an.read_text(encoding="utf-8")) if an.exists() else None,
            "referencias": {k: _lista(np.percentile(v, np.linspace(0, 100, 101)), 4)
                            for k, v in referencias_distancia(red, cj).items()},
            "similitud": {k: _lista(v, 4) for k, v in ref_parecido(cj).items()},
            "historial": historial(),
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
    # ---- pista, contexto y valores observados (brutos) desde el dataset normalizado
    N = _normalizados()
    kN = pd.MultiIndex.from_frame(cj.jugadores.loc[m, ["liga", "temporada", "player_id"]])
    NN = N.reindex(kN)
    for col_n, col_j in (("L", "L"), ("ctx_plantilla_dev", "ctx_plantilla_dev"), ("ctx_comp", "ctx_comp"),
                         ("rapm", "rapm_el"), ("orapm", "orapm_el"), ("drapm", "drapm_el"), ("rapm_pctel", "rapm_pct")):
        J[col_j] = NN[col_n].to_numpy(float) if col_n in NN else np.nan
    J["M"] = [_lista(v, 3) for v in NN[list(CLAVE_CTX)].to_numpy(float)]
    obs_r, obs_q = [], []
    for i, (_, fila) in zip(J.index, NN.iterrows()):
        R0 = pos_R[i].copy()
        for met in C.METRICAS_ESTILO:
            v = fila.get(f"{met}_obs", np.nan)
            R0[_I[met]] = v if v is not None else np.nan
        obs_r.append(_lista(R0, 3))
        obs_q.append(_lista([fila.get(f"{met}_obs", np.nan) for met in C.NIVEL], 3))
    brutos = {"columnas": ["Rb", "Qb"], "nota": "Valores observados en su propia liga, alineados por índice con jugadores.json",
              "filas": [[r, q] for r, q in zip(obs_r, obs_q)]}
    J["persona_id"] = J["persona_id"].where(J["persona_id"].notna(), J["liga"] + ":" + J["player_id"].astype(str))
    J = J.drop(columns=["player_id"])

    # ---- modelo final
    dec = {"nivel": 3, "net_z": 3, "min": 0, "min_total": 0, "cobertura_ab": 3, "edad": 1,
           "x": 3, "y": 3, "z": 3, "p": 3, "rob": 3}
    c["x"], c["y"], c["z"] = Z[:, 0], Z[:, 1], Z[:, 2]
    c["e"], c["p"], c["rob"] = P.argmax(1), P.max(1), rob["robustez"].to_numpy()
    c["probs"] = [_lista(p, 3) for p in P]
    # ---- etapas de entrenador (club-temporada-entrenador), cada una con su estilo (entrenadores.py)
    from . import entrenadores as ENT
    te = ENT.construir(cj, red, log=lambda *_: None)
    if len(te):
        te.to_csv(ENT.SALIDA, index=False)
        pk = [f"p{k}" for k in range(P.shape[1])]
        por_club = {}
        for _, t in te.sort_values(["clave", "orden"]).iterrows():
            por_club.setdefault(t["clave"], []).append({
                "orden": int(t["orden"]), "entrenador_id": t["entrenador_id"], "entrenador": t["entrenador"],
                "n_partidos": int(t["n_partidos"]), "n_regular": int(t["n_regular"]), "n_playoffs": int(t["n_playoffs"]),
                "primer_partido": t["primer_partido"], "ultimo_partido": t["ultimo_partido"],
                "victorias": int(t["victorias"]), "derrotas": int(t["derrotas"]), "interino": int(t["interino"]),
                "metodo": t["metodo"], "nivel": _r(t["nivel"], 3), "e": int(t["e"]), "p": _r(t["p"], 3),
                "probs": _lista(t[pk].to_numpy(float), 3), "x": _r(t["x"], 3), "y": _r(t["y"], 3), "z": _r(t["z"], 3)})
        c["entrenadores"] = [por_club.get(k) for k in c["clave"]]
    Pj, Zj = predecir(red, cj.Xj[m])
    J["x"], J["y"], J["z"] = Zj[:, 0], Zj[:, 1], Zj[:, 2]
    J["e"], J["p"] = Pj.argmax(1), Pj.max(1)
    meta["contexto"] = contexto_meta()
    meta["clave_ctx"] = CLAVE_CTX
    pi = C.DIR_SALIDA / "interacciones.json"
    meta["interacciones"] = json.loads(pi.read_text(encoding="utf-8")) if pi.exists() else None
    try:  # escalas de lectura ±100 (Euroliga = 0), mismo bloque que Quintetos: bbmodel/escalas.py
        from bbmodel.escalas import calcular as _escalas
        meta["escalas"] = _escalas()
    except Exception as e:  # noqa: BLE001
        print(f"escalas: no se pudieron calcular ({e})")
    dec.update({"L": 3, "ctx_plantilla_dev": 3, "ctx_comp": 3, "rapm_el": 2, "orapm_el": 2, "drapm_el": 2, "rapm_pct": 1})
    for nombre, obj in (("meta.json", meta), ("clubes.json", _columnar(c, dec)), ("jugadores.json", _columnar(J, dec)),
                        ("brutos.json", brutos)):
        (d / nombre).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=float), encoding="utf-8")
    print("escrito", d, {p.name: p.stat().st_size for p in d.glob("*.json")})
