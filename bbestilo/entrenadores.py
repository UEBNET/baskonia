"""Estilo de juego por ENTRENADOR: un vector y un estilo por tramo club-temporada-entrenador.

Un club puede tener en una misma temporada dos o tres entrenadores (destituciones, interinos). Cada
tramo (bbstats/entrenadores.py → data/processed/<temp>/entrenadores/<liga>_tramos.csv) recibe aquí su
propio vector de estilo con la MISMA red VaDE y la misma escala que los clubes, sin reentrenar nada:

1. Reparto de minutos del tramo (contraído hacia el de la temporada con el mismo peso n / (n + 8)). Del jugada a jugada (quintetos/<liga>/tramos.csv.gz) se suman los
   segundos de cada jugador en los partidos de ese entrenador. El vector del club es la media de los
   perfiles normalizados (A+B) de sus jugadores ponderada por minutos (datos.agregar), así que con los
   minutos del tramo sale exactamente el club «tal como lo usaba ese entrenador»: a quién daba minutos
   y con qué perfil.
2. Rasgos de equipo que decide el entrenador más allá de la plantilla (ritmo, selección y zona de tiro,
   pase, rebote ofensivo, faltas…). Se miden en los partidos del tramo y en toda la temporada del club,
   con los mismos datos (tramos y tiros del jugada a jugada), y la diferencia del tramo frente a la
   temporada se suma al vector en la escala transformada de cada rasgo, contraída hacia 0 por el tamaño
   del tramo: peso = n / (n + N_CONTRACCION) partidos. Un tramo de 3 partidos se mueve poco; uno de 30,
   casi todo lo que midió.
3. El vector pasa por la misma entrada de la red (escala de club, índice de nivel con la calidad media
   del tramo y neutralización del nivel) y la red da probabilidades por estilo y posición en el mapa.

Donde no hay jugada a jugada (o cubre menos de la mitad de los partidos del tramo) el tramo hereda el
vector del club entero (`metodo = club`) y queda marcado.

Salida: data/modelos/estilos/entrenadores.csv (una fila por tramo) y, al exportar el Atlas, el campo
`entrenadores` de cada club en clubes.json.
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

from bbmodel import zonas as Z
from bbmodel.metricas import destransformar, transformar as transformar_metrica

from . import config as C
from .datos import CRUDAS, Conjunto, _I, _media_w, agregar

DIR_PROC = C.RAIZ / "data" / "processed"
DIR_MOD = C.RAIZ / "data" / "modelos"
SALIDA = C.DIR_SALIDA / "entrenadores.csv"
N_CONTRACCION = 8          # partidos: peso de lo medido en el tramo = n / (n + 8)
MIN_COBERTURA_PBP = 0.5    # parte de los partidos del tramo con jugada a jugada para usar sus minutos
SUMAS = ["pts", "fga", "fgm", "fg3a", "fta", "oreb", "dreb", "tov", "stl", "blk", "ast", "pf"]
# rasgos de equipo medibles en el jugada a jugada (col -> función de las sumas del equipo y del rival)
RASGOS_EQUIPO = ["fg3a_rate", "fta_rate", "ast_pct", "tov_pct", "oreb_p100", "dreb_p100", "stl_p100", "blk_p100",
                 "pf_p100", "pct_aro", "pct_media", "pct_t3_esquina", "pct_asistidas"]


# ----------------------------------------------------------------------------- lectura
def _tramos_entrenador(liga: str, temporada: str) -> pd.DataFrame:
    p = DIR_PROC / temporada / "entrenadores" / f"{liga}_tramos.csv"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p, dtype=str)


def _pbp(liga: str, temporada: str) -> pd.DataFrame | None:
    p = DIR_PROC / temporada / "quintetos" / liga / "tramos.csv.gz"
    if not p.exists():
        return None
    cols = ["game_id", "fase", "sec", "team_a", "team_b", "quinteto_a", "quinteto_b"] + \
        [f"{s}_{c}" for s in "ab" for c in SUMAS]
    return pd.read_csv(p, dtype={"game_id": str, "team_a": str, "team_b": str, "quinteto_a": str, "quinteto_b": str},
                       usecols=lambda c: c in cols)


def _tiros(liga: str, temporada: str, calibracion: dict) -> pd.DataFrame | None:
    p = DIR_PROC / temporada / "quintetos" / liga / "tiros.csv.gz"
    if not p.exists():
        return None
    t = pd.read_csv(p, dtype={"game_id": str, "team_id": str, "player_id": str, "asistente_id": str},
                    usecols=["game_id", "team_id", "tipo", "anotado", "asistente_id", "x", "y"])
    t = t[t["tipo"].isin(["T2", "T3"])].copy()
    t["anotado"] = t["anotado"].astype(str).str.lower().isin(["true", "1"])
    t["asist"] = t["anotado"] & t["asistente_id"].notna() & (t["asistente_id"] != "")
    cal = calibracion.get(f"{liga}|{temporada}")
    t["zona"] = None
    if cal and cal.get("acierto", 0) >= 0.95:
        sis = Z.Sistema(liga, cal["regla"], cal["eje_largo"], tuple(cal["aro"]), tuple(cal["escala"]),
                        cal.get("pista_completa"))
        pz = Z.perfil_tiro(t, sis)       # sólo tiros con coordenadas válidas (mismo índice)
        t.loc[pz.index, "zona"] = pz["zona"]
    return t


def _mapa_ids(temporada: str) -> dict:
    """(liga, id de la fuente) -> id del modelo (la BBL usa «n:<nombre>» en los modelos)."""
    p = DIR_MOD / "contexto" / f"{temporada}.csv"
    if not p.exists():
        return {}
    c = pd.read_csv(p, dtype={"player_id": str, "pid_modelo": str}, usecols=["liga", "player_id", "pid_modelo"])
    c = c[c["pid_modelo"].notna()]
    return {(l, s): m for l, s, m in zip(c["liga"], c["player_id"], c["pid_modelo"])}


# ----------------------------------------------------------------------------- medidas por equipo y partido
def _por_partido(pbp: pd.DataFrame, tiros: pd.DataFrame | None) -> pd.DataFrame:
    """Sumas por (game_id, equipo): propias, del rival, segundos y tiros por zona."""
    lados = []
    for s, o in (("a", "b"), ("b", "a")):
        d = pbp[["game_id", "fase", "sec", f"team_{s}"] + [f"{s}_{c}" for c in SUMAS] + [f"{o}_{c}" for c in SUMAS]].copy()
        d.columns = ["game_id", "fase", "sec", "equipo"] + SUMAS + [f"r_{c}" for c in SUMAS]
        lados.append(d)
    d = pd.concat(lados, ignore_index=True)
    g = d.groupby(["game_id", "equipo"], as_index=False).agg(
        {"fase": "first", "sec": "sum", **{c: "sum" for c in SUMAS}, **{f"r_{c}": "sum" for c in SUMAS}})
    if tiros is not None and len(tiros):
        tz = tiros.groupby(["game_id", "team_id"]).agg(t_fga=("tipo", "size"), t_fgm=("anotado", "sum"),
                                                        t_asist=("asist", "sum"))
        con_zona = tiros[tiros["zona"].notna()]
        zz = con_zona.groupby(["game_id", "team_id", "zona"]).size().unstack(fill_value=0)
        zz = zz.reindex(columns=Z.ZONAS, fill_value=0).add_prefix("z_")
        zz["z_tot"] = zz.sum(axis=1)
        tz = tz.join(zz, how="left").reset_index().rename(columns={"team_id": "equipo"})
        g = g.merge(tz, on=["game_id", "equipo"], how="left")
    return g


def _rasgos(s: pd.Series) -> dict:
    """Rasgos de equipo (escala de su propia liga) a partir de sumas de partidos."""
    def div(a, b):
        return float(a) / float(b) if b and np.isfinite(b) and b > 0 else np.nan
    poss = s["fga"] + 0.44 * s["fta"] - s["oreb"] + s["tov"]
    r_poss = s["r_fga"] + 0.44 * s["r_fta"] - s["r_oreb"] + s["r_tov"]
    out = {"ritmo": div(poss + r_poss, s["sec"] / 60.0 / 40.0 * 2) if s["sec"] else np.nan,
           "fg3a_rate": div(s["fg3a"], s["fga"]) * 100, "fta_rate": div(s["fta"], s["fga"]) * 100,
           "ast_pct": div(s["ast"], s["fgm"]) * 100, "tov_pct": div(s["tov"], poss) * 100,
           "oreb_p100": div(s["oreb"], poss) * 100, "dreb_p100": div(s["dreb"], r_poss) * 100,
           "stl_p100": div(s["stl"], r_poss) * 100, "blk_p100": div(s["blk"], r_poss) * 100,
           "pf_p100": div(s["pf"], r_poss) * 100}
    if "z_tot" in s and np.isfinite(s.get("z_tot", np.nan)) and s["z_tot"] > 0:
        out["pct_aro"] = div(s["z_aro"], s["z_tot"]) * 100
        out["pct_media"] = div(s["z_media"], s["z_tot"]) * 100
        out["pct_t3_esquina"] = div(s["z_t3_esquina"], s["z_tot"]) * 100
    if "t_fgm" in s and np.isfinite(s.get("t_fgm", np.nan)):
        out["pct_asistidas"] = div(s["t_asist"], s["t_fgm"]) * 100
    return out


def _t(col: str, x: float) -> float:
    """Transformación del rasgo `col` (la de bbmodel.metricas para las métricas de jugador)."""
    tr = {r.col: r.transf for r in C.RASGOS}.get(col, "id")
    if not np.isfinite(x):
        return np.nan
    return float(x) if tr == "id" else float(transformar_metrica(np.array([x]), tr)[0])


def _t_inv(col: str, y: float) -> float:
    tr = {r.col: r.transf for r in C.RASGOS}.get(col, "id")
    return float(y) if tr == "id" else float(destransformar(np.array([y]), tr)[0])


# ----------------------------------------------------------------------------- vectores por tramo
def vectores(cj: Conjunto, log=print) -> pd.DataFrame:
    """Una fila por tramo club-temporada-entrenador con su vector (sin transformar) y su calidad media."""
    calibracion = {}
    pc = DIR_MOD / "pista" / "calibracion.json"
    if pc.exists():
        calibracion = json.loads(pc.read_text(encoding="utf-8"))
    clubes = cj.clubes
    jug = cj.jugadores
    filas = []
    for (liga, temp), cl in clubes.groupby(["liga", "temporada"], sort=True):
        tr = _tramos_entrenador(liga, temp)
        if tr.empty:
            continue
        pbp = _pbp(liga, temp)
        mapa = _mapa_ids(temp)
        partido = None
        segs = None
        sd_ritmo = 0.0
        if pbp is not None and len(pbp):
            partido = _por_partido(pbp, _tiros(liga, temp, calibracion))
            sd_ritmo = _sd_ritmo(partido)
            # segundos por (partido, equipo, jugador)
            lados = []
            for s in "ab":
                d = pbp[["game_id", "fase", "sec", f"team_{s}", f"quinteto_{s}"]].copy()
                d.columns = ["game_id", "fase", "sec", "equipo", "q"]
                d["pid"] = d["q"].fillna("").str.split("|")
                lados.append(d.explode("pid").drop(columns="q"))
            segs = pd.concat(lados, ignore_index=True)
            segs = segs[segs["pid"].notna() & (segs["pid"] != "")]
            segs["pid"] = [mapa.get((liga, p), p) for p in segs["pid"]]
            segs = segs.groupby(["game_id", "equipo", "pid"], as_index=False).agg(fase=("fase", "first"), sec=("sec", "sum"))
        for _, club in cl.iterrows():
            team = str(club["team_id"])
            ts = tr[tr["equipo_id"] == team]
            if ts.empty:
                continue
            R, w, idx, Q = cj.plantillas[club["clave"]]
            pids = jug.loc[idx, "player_id"].astype(str).to_numpy()
            v_club = agregar(R, w[None, :])[0]
            q_club = _media_w(Q, w[None, :])[0]
            # rasgos de equipo de la temporada entera (partidos del club con jugada a jugada)
            p_club = partido[partido["equipo"] == team] if partido is not None else None
            base = _rasgos(p_club[p_club["fase"] == "regular"].sum(numeric_only=True)) \
                if p_club is not None and len(p_club) else {}
            for _, t in ts.iterrows():
                ids = [g for g in str(t.get("partidos_ids") or "").split(";") if g]
                n = len(ids)
                fila = {"clave": club["clave"], "liga": liga, "temporada": temp, "team_id": team,
                        "nombre_club": club["nombre_club"], "entrenador_id": t["entrenador_id"],
                        "entrenador": t["entrenador"], "orden": int(t["orden"]), "n_partidos": n,
                        "n_regular": int(t.get("n_regular") or 0), "n_playoffs": int(t.get("n_playoffs") or 0),
                        "primer_partido": t.get("primer_partido"), "ultimo_partido": t.get("ultimo_partido"),
                        "victorias": int(t.get("victorias") or 0), "derrotas": int(t.get("derrotas") or 0),
                        "interino": int(t.get("interino") or 0), "entrenadores_equipo": int(t.get("entrenadores_equipo") or 1)}
                v, q, metodo, cob, peso = v_club.copy(), q_club.copy(), "club", 0.0, 0.0
                if segs is not None and n:
                    st = segs[(segs["equipo"] == team) & segs["game_id"].isin(ids)]
                    if fila["n_regular"] > 0:
                        st = st[st["fase"] == "regular"] if (st["fase"] == "regular").any() else st
                    cob = st["game_id"].nunique() / n
                    if cob >= MIN_COBERTURA_PBP and len(ts) > 1:
                        m = st.groupby("pid")["sec"].sum() / 60.0
                        ws = np.array([m.get(p, 0.0) for p in pids], float)
                        if ws.sum() > 0:
                            # reparto del tramo contraído hacia el de la temporada por el tamaño del tramo
                            n_obs = st["game_id"].nunique()
                            pm = n_obs / (n_obs + N_CONTRACCION)
                            ws = pm * ws / ws.sum() + (1 - pm) * w / w.sum()
                            v = agregar(R, ws[None, :])[0]
                            q = _media_w(Q, ws[None, :])[0]
                            metodo = "minutos_tramo"
                    if cob >= MIN_COBERTURA_PBP and len(ts) > 1 and base:
                        pt = p_club[p_club["game_id"].isin(ids)]
                        med = _rasgos(pt.sum(numeric_only=True))
                        n_obs = pt["game_id"].nunique()
                        peso = n_obs / (n_obs + N_CONTRACCION)
                        for col in RASGOS_EQUIPO:
                            a, b = med.get(col, np.nan), base.get(col, np.nan)
                            k = C.COLS.index(col)
                            if np.isfinite(a) and np.isfinite(b) and np.isfinite(v[k]):
                                v[k] = _t_inv(col, _t(col, v[k]) + peso * (_t(col, a) - _t(col, b)))
                        # ritmo relativo: z del ritmo del equipo en su liga; se desplaza con el ritmo medido
                        a, b = med.get("ritmo", np.nan), base.get("ritmo", np.nan)
                        k = C.COLS.index("ritmo_rel")
                        if np.isfinite(a) and np.isfinite(b) and b > 0 and np.isfinite(v[k]):
                            if sd_ritmo:
                                v[k] = v[k] + peso * (a - b) / sd_ritmo
                        metodo = "minutos_tramo+equipo"
                if len(ts) == 1:
                    metodo = "club_unico"
                fila.update({"metodo": metodo, "cobertura_pbp": round(cob, 3), "peso_equipo": round(peso, 3)})
                fila.update({c: x for c, x in zip(C.COLS, v)})
                fila.update({f"n_{c}": x for c, x in zip(C.NIVEL, q)})
                filas.append(fila)
        log(f"  {liga} {temp}: {sum(1 for f in filas if f['liga'] == liga and f['temporada'] == temp)} tramos")
    return pd.DataFrame(filas)


def _sd_ritmo(partido: pd.DataFrame) -> float:
    """Desviación del ritmo (posesiones por 40 min) entre equipos de la liga-temporada."""
    r = []
    for _, g in partido[partido["fase"] == "regular"].groupby("equipo"):
        r.append(_rasgos(g.sum(numeric_only=True))["ritmo"])
    r = np.array([x for x in r if np.isfinite(x)])
    return float(r.std()) if len(r) > 2 and r.std() > 0 else 0.0


def construir(cj: Conjunto, red, log=print) -> pd.DataFrame:
    """Vectores, entrada de la red y estilo de cada tramo de entrenador."""
    from .evaluar import predecir
    t = vectores(cj, log)
    if t.empty:
        return t
    V = t[C.COLS].to_numpy(float)
    Qm = t[[f"n_{c}" for c in C.NIVEL]].to_numpy(float)
    X = cj.x_club(V, Qm)
    P, Zm = predecir(red, X)
    t["nivel"] = cj.nivel_club.indice(Qm)
    t["e"], t["p"] = P.argmax(1), P.max(1)
    for k in range(P.shape[1]):
        t[f"p{k}"] = P[:, k]
    t["x"], t["y"], t["z"] = Zm[:, 0], Zm[:, 1], Zm[:, 2]
    # cambio frente al club entero (en el mapa y en estilo)
    pos = {c: i for i, c in enumerate(cj.clubes["clave"])}
    Pc, Zc = predecir(red, cj.Xc)
    i = t["clave"].map(pos).to_numpy()
    t["e_club"] = Pc[i].argmax(1)
    t["dist_club"] = np.linalg.norm(Zm - Zc[i], axis=1)
    return t


def main() -> pd.DataFrame:
    from .encaje import conjunto, red_guardada
    cj = conjunto()
    red = red_guardada("vade")
    t = construir(cj, red)
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    t.to_csv(SALIDA, index=False)
    multi = t[t["entrenadores_equipo"] > 1]
    cambia = multi.groupby("clave")["e"].nunique()
    print(f"{len(t)} tramos ({len(multi)} en {multi['clave'].nunique()} clubes con más de un entrenador); "
          f"clubes cuyo estilo cambia con el entrenador: {(cambia > 1).sum()}")
    print(t["metodo"].value_counts().to_string())
    return t
