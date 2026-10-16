"""Interacciones entre jugadores: cómo cambia el juego de Y cuando X está en pista (y por qué: estilo y nivel).

Base (capa de quintetos de bbstats, temporada regular, 8 ligas):
  * tiros.csv.gz: cada tiro con su lanzador, si fue asistido y el quinteto de su equipo en pista.
  * tramos.csv.gz: segundos y estadística de equipo de cada quinteto (posesiones).
  * parejas.csv: Net de la pareja, WOWY, sinergia y sinergia frente al RAPM.

1. Efectos de pareja dirigidos (X → Y), por equipo y temporada: con Y en pista, se compara a Y con X en
   pista y sin X en pista:
     cuota de tiro   tiros de campo de Y / tiros de campo del equipo (¿le quita o le da protagonismo?)
     eFG%            acierto efectivo de Y (¿le genera mejores tiros?)
     % asistidas     parte de las canastas de Y que llegan de pase
     % en el aro     parte de los tiros de Y que son en el aro
     pts/100         puntos de Y por 100 posesiones de su equipo
   con el número de tiros de Y en cada situación (para pesar el ruido).
2. Matrices de estilo × estilo: regresión ponderada de cada efecto sobre p_X ⊗ p_Y (la probabilidad de
   estilo de cada uno, salida de la VaDE) con el NIVEL de X y de Y como controles. Cada celda (s, t) dice
   cuánto cambia un jugador de estilo t al compartir pista con uno de estilo s, a igual nivel. El
   coeficiente del nivel de X dice cuánto mejora a sus compañeros un compañero mejor (el «efecto MVP»).
3. Sinergia de pareja (simétrica): sinergia frente al RAPM de parejas.csv sobre la misma base.
Incertidumbre: bootstrap por equipos-temporada (las parejas de un equipo no son independientes).
"""
from __future__ import annotations

import glob
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
DIR_PROC = RAIZ / "data" / "processed"
DIR_SALIDA = RAIZ / "data" / "modelos" / "interacciones"
COEF_TL = 0.44
EFECTOS = {
    "cuota_tiro": ("Cuota de tiro", "% de los tiros de campo del equipo que lanza Y", "fga"),
    "efg": ("eFG%", "acierto efectivo de Y en tiros de campo", "fga"),
    "pct_asistidas": ("% asistidas", "parte de las canastas de Y que llegan de pase", "fgm"),
    "pct_aro": ("% en el aro", "parte de los tiros de Y que son en el aro (< 1,8 m)", "fga"),
    "pts100": ("Puntos/100", "puntos de Y por 100 posesiones de su equipo", "poss"),
}


def _bool(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().isin(["true", "1"])


def efectos_liga(liga: str, temporada: str, zonas_de=None, min_juntos: float = 60) -> pd.DataFrame:
    """Efectos dirigidos X → Y de una liga-temporada (una fila por equipo, Y, X)."""
    pt = DIR_PROC / temporada / "quintetos" / liga / "tiros.csv.gz"
    ptr = DIR_PROC / temporada / "quintetos" / liga / "tramos.csv.gz"
    if not pt.exists() or not ptr.exists():
        return pd.DataFrame()
    t = pd.read_csv(pt, dtype={"team_id": str, "player_id": str, "asistente_id": str, "quinteto": str},
                    usecols=["fase", "team_id", "player_id", "tipo", "anotado", "puntos", "asistente_id",
                             "quinteto", "x", "y"])
    t = t[(t["fase"] == "regular") & t["quinteto"].notna() & (t["quinteto"].str.count(r"\|") == 4)]
    if t.empty:
        return pd.DataFrame()
    t["anotado"] = _bool(t["anotado"])
    campo = t["tipo"].isin(["T2", "T3"])
    t["fga"] = campo.astype(float)
    t["fgm"] = (campo & t["anotado"]).astype(float)
    t["fg3m"] = ((t["tipo"] == "T3") & t["anotado"]).astype(float)
    t["fgm_asist"] = (t["fgm"] > 0) & t["asistente_id"].notna() & (t["asistente_id"] != "")
    t["fgm_asist"] = t["fgm_asist"].astype(float)
    t["pts"] = pd.to_numeric(t["puntos"], errors="coerce").fillna(0) * t["anotado"]
    if zonas_de is not None:
        t["aro"] = zonas_de(t).astype(float) * t["fga"]
    else:
        t["aro"] = np.nan
    # totales por quinteto del equipo y por (quinteto, lanzador)
    eq = t.groupby(["team_id", "quinteto"])[["fga"]].sum().rename(columns={"fga": "fga_eq"})
    jug = t.groupby(["team_id", "quinteto", "player_id"])[["fga", "fgm", "fg3m", "fgm_asist", "pts", "aro"]].sum()
    # posesiones por quinteto (tramos)
    tr = pd.read_csv(ptr, dtype={"team_a": str, "team_b": str, "quinteto_a": str, "quinteto_b": str})
    tr = tr[tr["fase"] == "regular"]
    pos = []
    for lado in ("a", "b"):
        p = tr[f"{lado}_fga"] - tr[f"{lado}_oreb"] + tr[f"{lado}_tov"] + COEF_TL * tr[f"{lado}_fta"]
        pos.append(pd.DataFrame({"team_id": tr[f"team_{lado}"], "quinteto": tr[f"quinteto_{lado}"], "poss": p,
                                 "sec": tr["sec"]}))
    pos = pd.concat(pos).groupby(["team_id", "quinteto"])[["poss", "sec"]].sum()
    filas = []
    for team, lq in pos.reset_index().groupby("team_id"):
        lq = lq.set_index("quinteto")
        lq = lq.join(eq.loc[team] if team in eq.index.get_level_values(0) else pd.DataFrame(columns=["fga_eq"]))
        lq["fga_eq"] = lq["fga_eq"].fillna(0)
        miembros = {q: set(q.split("|")) for q in lq.index}
        jugadores = sorted(set().union(*miembros.values()))
        try:
            jt = jug.loc[team]
        except KeyError:
            continue
        for y in jugadores:
            qs_y = [q for q in lq.index if y in miembros[q]]
            if not qs_y:
                continue
            sub = lq.loc[qs_y]
            jy = jt[jt.index.get_level_values("player_id") == y].droplevel("player_id").reindex(qs_y).fillna(0)
            for x in jugadores:
                if x == y:
                    continue
                con = np.array([x in miembros[q] for q in qs_y])
                c = {}
                for etiqueta, m in (("con", con), ("sin", ~con)):
                    s = sub[m]; j = jy[m]
                    c[f"sec_{etiqueta}"] = s["sec"].sum()
                    c[f"poss_{etiqueta}"] = s["poss"].sum()
                    c[f"fga_eq_{etiqueta}"] = s["fga_eq"].sum()
                    for k in ("fga", "fgm", "fg3m", "fgm_asist", "pts", "aro"):
                        c[f"{k}_{etiqueta}"] = j[k].sum()
                if c["sec_con"] < min_juntos * 60 or c["sec_sin"] < 30 * 60:
                    continue
                filas.append({"team_id": team, "y": y, "x": x, **c})
    d = pd.DataFrame(filas)
    if d.empty:
        return d
    for e in ("con", "sin"):
        fga = d[f"fga_{e}"].where(d[f"fga_{e}"] > 0)
        d[f"cuota_tiro_{e}"] = 100 * d[f"fga_{e}"] / d[f"fga_eq_{e}"].where(d[f"fga_eq_{e}"] > 0)
        d[f"efg_{e}"] = 100 * (d[f"fgm_{e}"] + 0.5 * d[f"fg3m_{e}"]) / fga
        d[f"pct_asistidas_{e}"] = 100 * d[f"fgm_asist_{e}"] / d[f"fgm_{e}"].where(d[f"fgm_{e}"] > 0)
        d[f"pct_aro_{e}"] = 100 * d[f"aro_{e}"] / fga
        d[f"pts100_{e}"] = 100 * d[f"pts_{e}"] / d[f"poss_{e}"].where(d[f"poss_{e}"] > 0)
    for k in EFECTOS:
        d[f"d_{k}"] = d[f"{k}_con"] - d[f"{k}_sin"]
    d.insert(0, "temporada", temporada)
    d.insert(0, "liga", liga)
    return d


def construir(temporadas: list[str] | None = None, guardar: bool = True) -> pd.DataFrame:
    from . import zonas as Z
    import json
    calib = json.loads((RAIZ / "data" / "modelos" / "pista" / "calibracion.json").read_text(encoding="utf-8"))
    temporadas = temporadas or sorted(p.name for p in DIR_PROC.iterdir() if (p / "quintetos").exists())
    frames = []
    for temp in temporadas:
        for d in sorted((DIR_PROC / temp / "quintetos").iterdir()):
            liga = d.name
            c = calib.get(f"{liga}|{temp}")
            zonas_de = None
            if c and c["acierto"] >= 0.95:
                sis = Z.Sistema(liga, c["regla"], c["eje_largo"], tuple(c["aro"]), tuple(c["escala"]), c["pista_completa"])

                def zonas_de(t, sis=sis):
                    lat, lon = sis.metros(t["x"].to_numpy(float), t["y"].to_numpy(float))
                    ok = t["x"].notna() & t["y"].notna() & ~((t["x"] == 0) & (t["y"] == 0))
                    return pd.Series((np.hypot(lat, lon) < Z.R_ARO) & ok.to_numpy() & (t["tipo"] == "T2").to_numpy(),
                                     index=t.index)
            frames.append(efectos_liga(liga, temp, zonas_de))
    df = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    if guardar:
        DIR_SALIDA.mkdir(parents=True, exist_ok=True)
        for temp, g in df.groupby("temporada"):
            g.round(4).to_csv(DIR_SALIDA / f"efectos_{temp}.csv.gz", index=False, compression="gzip")
    return df


def cargar_efectos() -> pd.DataFrame:
    fr = [pd.read_csv(p, dtype={"team_id": str, "y": str, "x": str}) for p in sorted(glob.glob(str(DIR_SALIDA / "efectos_*.csv.gz")))]
    return pd.concat(fr, ignore_index=True)


# ------------------------------------------------------------------------------------------ estilo × estilo
def _peso(d: pd.DataFrame, k: str) -> np.ndarray:
    """Peso de cada efecto: inversa de su varianza de muestra (aprox.): n efectivo de las dos situaciones."""
    base = EFECTOS[k][2]
    if base == "poss":
        a, b = d["poss_con"], d["poss_sin"]
    elif base == "fgm":
        a, b = d["fgm_con"], d["fgm_sin"]
    else:
        a, b = d["fga_con"], d["fga_sin"]
    a = a.to_numpy(float); b = b.to_numpy(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        n = 1.0 / (1.0 / a + 1.0 / b)
    return np.where(np.isfinite(n) & (n > 0), n, 0.0)


def _diseno(PX: np.ndarray, PY: np.ndarray, LX: np.ndarray, LY: np.ndarray) -> np.ndarray:
    """Columnas: p_X ⊗ p_Y (K·K celdas), nivel de X, nivel de Y, nivel de X × p_Y (K)."""
    K = PX.shape[1]
    celdas = (PX[:, :, None] * PY[:, None, :]).reshape(len(PX), K * K)
    return np.column_stack([celdas, LX, LY, LX[:, None] * PY])


def _wls(X: np.ndarray, y: np.ndarray, w: np.ndarray, ridge: float) -> np.ndarray:
    sw = np.sqrt(w)[:, None]
    A = (X * sw).T @ (X * sw) + ridge * np.eye(X.shape[1])
    return np.linalg.solve(A, (X * sw).T @ (y * sw[:, 0]))


def modelo_estilos(ef: pd.DataFrame, jug: pd.DataFrame, n_boot: int = 60, semilla: int = 3,
                   ridge: float = 5.0) -> dict:
    """Matrices estilo × estilo de cada efecto X → Y, con el nivel como control.

    ef: efectos (construir/cargar_efectos). jug: liga, temporada, player_id (id de la fuente), L y p_E01…p_EK
    (probabilidades de estilo de la VaDE). Devuelve un dict serializable."""
    pcols = sorted(c for c in jug.columns if c.startswith("p_E"))
    K = len(pcols)
    J = jug.drop_duplicates(["liga", "temporada", "player_id"]).set_index(["liga", "temporada", "player_id"])
    d = ef.copy()
    kx = pd.MultiIndex.from_frame(d[["liga", "temporada", "x"]])
    ky = pd.MultiIndex.from_frame(d[["liga", "temporada", "y"]])
    PX = J[pcols].reindex(kx).to_numpy(float); PY = J[pcols].reindex(ky).to_numpy(float)
    LX = J["L"].reindex(kx).to_numpy(float); LY = J["L"].reindex(ky).to_numpy(float)
    ok = np.isfinite(PX).all(1) & np.isfinite(PY).all(1) & np.isfinite(LX) & np.isfinite(LY)
    d = d[ok].reset_index(drop=True); PX, PY, LX, LY = PX[ok], PY[ok], LX[ok], LY[ok]
    # nivel centrado en el jugador medio de la muestra (las celdas se leen «a igual nivel medio»)
    centro = float(np.nanmean(LY))
    LX = LX - centro; LY = LY - centro
    X = _diseno(PX, PY, LX, LY)
    grupos = (d["liga"] + "|" + d["temporada"] + "|" + d["team_id"]).to_numpy()
    ug = np.unique(grupos)
    rng = np.random.default_rng(semilla)
    boots_idx = []
    pos = {g: np.where(grupos == g)[0] for g in ug}
    for _ in range(n_boot):
        el = rng.choice(ug, len(ug), replace=True)
        boots_idx.append(np.concatenate([pos[g] for g in el]))
    out = {"estilos": [c[2:] for c in pcols], "efectos": {}, "n_parejas": int(len(d)),
           "nivel_centro": round(centro, 4),
           "formula": "Δ_Y = p_X · M · p_Y + nivel_x·(L_X − c) + nivel_y·(L_Y − c) + (L_X − c)·(nivel_x_por_estilo_y · p_Y), "
                      "c = nivel_centro",
           "nota": "Celda (s, t): cambio medio del jugador Y de estilo t cuando comparte pista con un X de estilo s, "
                   "frente a cuando X no está, a igual nivel (centrado en el nivel medio de la muestra)."}
    for k, (nombre, desc, _) in EFECTOS.items():
        y = d[f"d_{k}"].to_numpy(float)
        w = _peso(d, k)
        s = np.isfinite(y) & (w > 0)
        if s.sum() < 500:
            continue
        # recorte de colas (diferencias imposibles por muestras mínimas)
        lo, hi = np.quantile(y[s], [0.005, 0.995])
        yy = np.clip(y, lo, hi)
        b = _wls(X[s], yy[s], w[s], ridge)
        B = []
        for idx in boots_idx:
            ii = idx[s[idx]]
            B.append(_wls(X[ii], yy[ii], w[ii], ridge))
        B = np.array(B)
        se = B.std(0)
        M = b[:K * K].reshape(K, K); Mse = se[:K * K].reshape(K, K)
        media = float(np.average(yy[s], weights=w[s]))
        out["efectos"][k] = {
            "nombre": nombre, "descripcion": desc, "n": int(s.sum()), "media": round(media, 3),
            "matriz": np.round(M, 3).tolist(), "matriz_se": np.round(Mse, 3).tolist(),
            # contraste: celda menos la media de su columna (qué estilo de X le va mejor a cada estilo de Y)
            "contraste": np.round(M - M.mean(0, keepdims=True), 3).tolist(),
            "nivel_x": round(float(b[K * K]), 3), "nivel_x_se": round(float(se[K * K]), 3),
            "nivel_y": round(float(b[K * K + 1]), 3), "nivel_y_se": round(float(se[K * K + 1]), 3),
            "nivel_x_por_estilo_y": np.round(b[K * K + 2:], 3).tolist(),
            "nivel_x_por_estilo_y_se": np.round(se[K * K + 2:], 3).tolist()}
    return out


def sinergia_estilos(jug: pd.DataFrame, n_boot: int = 60, semilla: int = 5, ridge: float = 5.0) -> dict:
    """Sinergia de pareja (frente al RAPM, simétrica) según los estilos de los dos jugadores y su nivel."""
    pcols = sorted(c for c in jug.columns if c.startswith("p_E"))
    K = len(pcols)
    J = jug.drop_duplicates(["liga", "temporada", "player_id"]).set_index(["liga", "temporada", "player_id"])
    frames = []
    for p in sorted(glob.glob(str(DIR_PROC / "*" / "quintetos" / "*" / "parejas.csv.gz"))):
        d = pd.read_csv(p, dtype={"team_id": str, "jugador_a_id": str, "jugador_b_id": str},
                        usecols=["liga", "temporada", "fase", "team_id", "jugador_a_id", "jugador_b_id", "min", "poss",
                                 "sinergia", "sinergia_rapm", "net_rtg"])
        frames.append(d[(d["fase"] == "regular") & (d["min"] >= 60)])
    d = pd.concat(frames, ignore_index=True)
    ka = pd.MultiIndex.from_frame(d[["liga", "temporada", "jugador_a_id"]])
    kb = pd.MultiIndex.from_frame(d[["liga", "temporada", "jugador_b_id"]])
    PA = J[pcols].reindex(ka).to_numpy(float); PB = J[pcols].reindex(kb).to_numpy(float)
    LA = J["L"].reindex(ka).to_numpy(float); LB = J["L"].reindex(kb).to_numpy(float)
    ok = np.isfinite(PA).all(1) & np.isfinite(PB).all(1) & np.isfinite(LA) & np.isfinite(LB) & d["sinergia_rapm"].notna().to_numpy()
    d = d[ok].reset_index(drop=True); PA, PB, LA, LB = PA[ok], PB[ok], LA[ok], LB[ok]
    iu = np.triu_indices(K)
    S = 0.5 * (PA[:, :, None] * PB[:, None, :] + PB[:, :, None] * PA[:, None, :])
    S = S * (2 - np.eye(K))[None]          # cada pareja no ordenada una vez
    Xc = S[:, iu[0], iu[1]]
    Lm = np.nanmean(np.concatenate([LA, LB]))
    X = np.column_stack([Xc, (LA - Lm) + (LB - Lm), np.abs(LA - LB)])
    y = d["sinergia_rapm"].to_numpy(float)
    w = d["poss"].to_numpy(float)
    b = _wls(X, y, w, ridge)
    grupos = (d["liga"] + "|" + d["temporada"] + "|" + d["team_id"]).to_numpy()
    ug = np.unique(grupos); pos = {g: np.where(grupos == g)[0] for g in ug}
    rng = np.random.default_rng(semilla)
    B = []
    for _ in range(n_boot):
        idx = np.concatenate([pos[g] for g in rng.choice(ug, len(ug), replace=True)])
        B.append(_wls(X[idx], y[idx], w[idx], ridge))
    se = np.array(B).std(0)
    M = np.zeros((K, K)); Ms = np.zeros((K, K))
    M[iu] = b[:len(iu[0])]; Ms[iu] = se[:len(iu[0])]
    M = M + np.triu(M, 1).T; Ms = Ms + np.triu(Ms, 1).T
    return {"estilos": [c[2:] for c in pcols], "n_parejas": int(len(d)), "nivel_centro": round(float(Lm), 4),
            "constante": "sin constante: la matriz recoge el nivel medio de cada combinación de estilos",
            "formula": "sinergia = p_A · S · p_B + nivel_suma·((L_A − c) + (L_B − c)) + diferencia_nivel·|L_A − L_B|",
            "matriz": np.round(M, 3).tolist(),
            "matriz_se": np.round(Ms, 3).tolist(), "nivel_suma": round(float(b[-2]), 3),
            "nivel_suma_se": round(float(se[-2]), 3), "diferencia_nivel": round(float(b[-1]), 3),
            "diferencia_nivel_se": round(float(se[-1]), 3),
            "nota": "Sinergia frente al RAPM (Net de la pareja − lo esperado por el RAPM de los 10 en pista, contraído "
                    "por la muestra) según el estilo de los dos jugadores, a igual nivel."}
