"""F3 · bancos de validación del impacto cruzado y de las bajas (prerregistro `configs/ecosistema_v41.yaml → f3`, 09-11-2026).

Tres experimentos sobre los partidos reales (fase regular, data/modelos/roles/partidos_jugador/<t>.csv.gz):
  V-AUS   ausencias: partidos SIN j (único ausente de rotación) frente a partidos CON j de la misma temporada.
  V-MID   altas a mitad de temporada: después frente a antes, con el resto de la rotación constante.
  V-TRANS transiciones t → t+1 de los que siguen en el club (rol oráculo de las altas).
Para cada compañero k que sigue, Δ observado de minutos, uso, cuota de tiro, % asistidas y pts/100, y Δ del Net del equipo.

Predicción con TODO ≤ t (corte t → temporada t+1): motor de minutos v3.3 con los pesos ≤ t (con y sin el movimiento, P5),
uso natural con suma fija, efectos F2-B ≤ t (±π·d̂) y ΔNet = c_cal·ΔT de la capa 4 (β, φ, h ≤ t). Las líneas base y el
examen están en examen_f3.py. Cachés en experimentos/v4_1/bancos/.
"""
from __future__ import annotations

import os
import pickle
import time

import numpy as np
import pandas as pd

from . import config as CE

SUMAS = ["min", "fga", "fta", "fgm", "fgm_asist", "pts", "poss_on", "team_fga_on", "team_fta_on"]
METRICAS = ["minutos", "uso", "cuota_tiro", "pct_asistidas", "pts100"]
EXPOSICION = {"minutos": "partidos", "uso": "team_tsa_on", "cuota_tiro": "team_fga_on", "pct_asistidas": "fgm", "pts100": "poss_on"}
DIR = CE.RAIZ / "experimentos" / "v4_1" / "bancos"


def temp_de(a: int) -> str:
    return f"{a}-{str(a + 1)[-2:]}"


# =============================================================================================== datos por partido
def partidos(temp: str) -> pd.DataFrame | None:
    p = CE.RAIZ / "data" / "modelos" / "roles" / "partidos_jugador" / f"{temp}.csv.gz"
    if not p.exists():
        return None
    cols = ["liga", "temporada", "game_id", "fase", "team_id", "opp_id", "player_id", "persona_id", "orden_equipo", "jugo"] + SUMAS
    d = pd.read_csv(p, usecols=cols, low_memory=False, dtype={"team_id": str, "opp_id": str, "game_id": str, "player_id": str,
                                                              "persona_id": str})
    d = d[d["fase"] == "regular"].copy()
    for c in SUMAS:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0)
    d["orden_equipo"] = pd.to_numeric(d["orden_equipo"], errors="coerce")
    return d


def metricas(A: pd.DataFrame) -> pd.DataFrame:
    """A: sumas por jugador sobre un conjunto de partidos (+ «partidos») → métricas del prerregistro y exposiciones."""
    with np.errstate(invalid="ignore", divide="ignore"):
        tsa = A["team_fga_on"] + 0.44 * A["team_fta_on"]
        out = pd.DataFrame({
            "minutos": A["min"] / A["partidos"],
            "uso": np.where(tsa > 0, 100 * (A["fga"] + 0.44 * A["fta"]) / tsa, np.nan),
            "cuota_tiro": np.where(A["team_fga_on"] > 0, 100 * A["fga"] / A["team_fga_on"], np.nan),
            "pct_asistidas": np.where(A["fgm"] > 0, 100 * A["fgm_asist"] / A["fgm"], np.nan),
            "pts100": np.where(A["poss_on"] > 0, 100 * A["pts"] / A["poss_on"], np.nan)}, index=A.index)
    out["x_partidos"], out["x_team_tsa_on"], out["x_team_fga_on"] = A["partidos"], tsa, A["team_fga_on"]
    out["x_fgm"], out["x_poss_on"] = A["fgm"], A["poss_on"]
    return out


def sumas(d: pd.DataFrame, juegos) -> pd.DataFrame:
    g = d[d["game_id"].isin(set(juegos))]
    A = g.groupby("persona_id")[SUMAS].sum()
    A["partidos"] = len(set(juegos))
    return A


def net_equipo(d: pd.DataFrame, team: str, juegos) -> tuple[float, float]:
    g = d[d["game_id"].isin(set(juegos))]
    pf = g.loc[g["team_id"] == team, "pts"].sum()
    pc = g.loc[g["team_id"] != team, "pts"].sum()
    poss = g.loc[g["team_id"] == team, "poss_on"].sum() / 5.0
    return (100.0 * (pf - pc) / poss if poss > 0 else np.nan), float(poss)


def _delta(A0: pd.DataFrame, A1: pd.DataFrame, comunes) -> pd.DataFrame:
    """Δ = métrica(movimiento) − métrica(base) para los compañeros comunes, con las exposiciones de los dos conjuntos."""
    m0, m1 = metricas(A0.loc[comunes]), metricas(A1.loc[comunes])
    out = pd.DataFrame(index=comunes)
    for k in METRICAS:
        out[f"obs_{k}"] = m1[k] - m0[k]
        out[f"base_{k}"] = m0[k]
        e = EXPOSICION[k]
        x0, x1 = m0[f"x_{e}"], m1[f"x_{e}"]
        out[f"w_{k}"] = 1.0 / (1.0 / np.maximum(x0, 1e-9) + 1.0 / np.maximum(x1, 1e-9))
        out[f"xmin_{k}"] = np.minimum(x0, x1)
    return out


# =============================================================================================== bancos observados
def v_aus(cfg: dict, temp: str, d: pd.DataFrame) -> list[dict]:
    """Eventos (equipo, j) de la temporada: partidos sin j (único ausente de rotación) y con j (sin ausentes de rotación)."""
    ca = cfg["f3"]
    au = pd.read_csv(CE.dir_salida(cfg, "ausencias") / "ausencias.csv.gz", dtype={"team_id": str, "game_id": str,
                                                                                  "persona_id": str, "player_id": str})
    au = au[(au["temporada"] == temp) & (au["umbral"].round(4) == round(float(cfg["ausencias"]["rotacion_min_cuota_minutos"]), 4))]
    out = []
    for (liga, team), g in au.groupby(["liga", "team_id"]):
        dt = d[(d["liga"] == liga) & (d["team_id"] == team)]
        if dt.empty:
            continue
        con_aus = set(g["game_id"])
        for j, gj in g[g["ausentes_rotacion_en_partido"] == 1].groupby("persona_id"):
            g0 = sorted(set(gj["game_id"]))
            jug = dt[(dt["persona_id"] == j) & (dt["min"] > 0)]
            g1 = sorted(set(jug["game_id"]) - con_aus)
            if len(g0) < 1 or len(g1) < 3:
                continue
            A0, A1 = sumas(dt, g1), sumas(dt, g0)                 # base = con j; movimiento = sin j
            comunes = [k for k in A0.index.intersection(A1.index) if k != j and A0.loc[k, "min"] > 0 and A1.loc[k, "min"] > 0]
            if not comunes:
                continue
            D = _delta(A0, A1, comunes)
            mj = metricas(A0.loc[[j]]).iloc[0] if j in A0.index else None
            n0, p0 = net_equipo(d[d["liga"] == liga], team, g1)
            n1, p1 = net_equipo(d[d["liga"] == liga], team, g0)
            out.append({"banco": "V-AUS", "liga": liga, "temporada": temp, "team": team, "movs": [("baja", j, None)],
                        "comp": D, "mover_base": {j: (None if mj is None else mj.to_dict())},
                        "net_obs": n1 - n0, "w_net": 1.0 / (1.0 / max(p0, 1e-9) + 1.0 / max(p1, 1e-9)), "poss_min": min(p0, p1),
                        "n_sin": len(g0), "n_con": len(g1)})
    return out


def v_mid(cfg: dict, temp: str, d: pd.DataFrame, roles: pd.DataFrame) -> list[dict]:
    """Altas a mitad de temporada con el resto de la rotación constante (prerregistro f3.v_mid)."""
    umbral = float(cfg["ausencias"]["rotacion_min_cuota_minutos"])
    out = []
    for (liga, team), dt in d.groupby(["liga", "team_id"]):
        ords = dt.groupby("game_id")["orden_equipo"].first().dropna()
        n = len(ords)
        if n < 20:
            continue
        jugado = dt[dt["min"] > 0]
        primero = jugado.groupby("persona_id")["orden_equipo"].min()
        for a, fo in primero.items():
            if not (0.15 * n <= fo <= 0.85 * n):
                continue
            antes = list(ords[ords < fo].index)
            despues = list(ords[ords >= fo].index)
            if len(antes) < 3 or (jugado[(jugado["persona_id"] == a)]["game_id"].nunique() < 5):
                continue
            A0, A1 = sumas(dt, antes), sumas(dt, despues)
            if a not in A1.index or A1.loc[a, "min"] < umbral * A1["min"].sum():
                continue
            rot = set(A0.index[A0["min"] >= umbral * A0["min"].sum()]) | set(A1.index[A1["min"] >= umbral * A1["min"].sum()])
            rot.discard(a)
            if any((p not in A0.index) or (p not in A1.index) or A0.loc[p, "min"] <= 0 or A1.loc[p, "min"] <= 0 for p in rot):
                continue
            comunes = [k for k in A0.index.intersection(A1.index) if k != a and A0.loc[k, "min"] > 0 and A1.loc[k, "min"] > 0]
            if not comunes:
                continue
            rr = roles[(roles["liga"] == liga) & (roles["team_id"] == team) & (roles["persona_id"] == a)]["rol"]
            rol = str(rr.iloc[0]) if len(rr) and isinstance(rr.iloc[0], str) else None
            n0, p0 = net_equipo(d[d["liga"] == liga], team, antes)
            n1, p1 = net_equipo(d[d["liga"] == liga], team, despues)
            out.append({"banco": "V-MID", "liga": liga, "temporada": temp, "team": team, "movs": [("alta", a, rol)],
                        "comp": _delta(A0, A1, comunes), "mover_base": {}, "net_obs": n1 - n0,
                        "w_net": 1.0 / (1.0 / max(p0, 1e-9) + 1.0 / max(p1, 1e-9)), "poss_min": min(p0, p1),
                        "n_antes": len(antes), "n_despues": len(despues)})
    return out


def v_trans(cfg: dict, ins, d0: pd.DataFrame, d1: pd.DataFrame, roles1: pd.DataFrame) -> list[dict]:
    """Transiciones t → t+1 por club (mapa de clubes de la v3.2): los que siguen con ≥ 300 min en las dos temporadas."""
    S, V = ins.S, ins.V
    mapa = V.mapa_clubes(ins.roles, ins.temp, ins.temp1)
    mm = float(cfg["criterios"]["f2"]["realizado_min_minutos"])
    out = []
    for (liga, team), dt1 in d1.groupby(["liga", "team_id"]):
        club_t = V.club_en_t(ins.c, liga, team, None, mapa)
        g0 = ins.c.por_club.get(club_t) if club_t is not None else None
        if g0 is None or g0.empty:
            continue
        l0, t0 = str(g0["liga"].mode().iloc[0]), str(g0["team_id"].astype(str).mode().iloc[0])
        dt0 = d0[(d0["liga"] == l0) & (d0["team_id"] == t0)]
        if dt0.empty:
            continue
        A0, A1 = sumas(dt0, dt0["game_id"].unique()), sumas(dt1, dt1["game_id"].unique())
        A0["partidos"], A1["partidos"] = dt0["game_id"].nunique(), dt1["game_id"].nunique()
        sig = [k for k in A0.index.intersection(A1.index) if A0.loc[k, "min"] >= mm and A1.loc[k, "min"] >= mm]
        if not sig:
            continue
        altas = [p for p in A1.index if p not in A0.index and A1.loc[p, "min"] > 0]
        bajas = [p for p in A0.index if p not in A1.index and A0.loc[p, "min"] > 0]
        rl = roles1[(roles1["liga"] == liga) & (roles1["team_id"] == team)].set_index("persona_id")["rol"]
        movs = [("alta", a, str(rl.get(a)) if isinstance(rl.get(a), str) else None) for a in altas] + [("baja", b, None) for b in bajas]
        mb = metricas(A0.loc[bajas]) if bajas else pd.DataFrame()
        n0, p0 = net_equipo(d0[d0["liga"] == l0], t0, dt0["game_id"].unique())
        n1, p1 = net_equipo(d1[d1["liga"] == liga], team, dt1["game_id"].unique())
        out.append({"banco": "V-TRANS", "liga": liga, "temporada": ins.temp1, "team": team, "liga0": l0, "team0": t0,
                    "club_t": club_t, "movs": movs, "comp": _delta(A0, A1, sig),
                    "mover_base": {b: mb.loc[b].to_dict() for b in bajas}, "net_obs": n1 - n0,
                    "w_net": 1.0 / (1.0 / max(p0, 1e-9) + 1.0 / max(p1, 1e-9)), "poss_min": min(p0, p1),
                    "miembros0": [(p, 1.0) for p in A0.index[A0["min"] > 0]]})
    return out


# =============================================================================================== predicción ≤ t
class Predictor:
    """Escenarios de un equipo con los insumos del corte t (motor ≤ t, β/φ/h ≤ t, F2-B ≤ t, c de la capa 4 ≤ t)."""

    def __init__(self, cfg: dict, a: int, progreso=print):
        import yaml
        from .impacto_pista import InsumosCorte
        self.cfg, self.a = cfg, a
        self.ins = InsumosCorte(cfg, a, progreso)
        if "rol_asignado" not in self.ins.c.cfg:
            v33 = yaml.safe_load((CE.RAIZ / "configs" / "simulation_v33.yaml").read_text(encoding="utf-8"))
            self.ins.c.cfg["rol_asignado"] = v33["rol_asignado"]
        cfg40 = self.ins.cfg40
        p = CE.RAIZ / cfg40["f2"]["salida"] / "dirigidos" / "examen" / f"modelos_corte_{a}.pkl"
        self.f2b = pickle.loads(p.read_bytes())["modelos"]
        pf = pd.read_csv(CE.RAIZ / cfg40["salida"] / "equipo" / "examen" / "predicciones_f4.csv.gz", usecols=["corte", "grupo", "c_cal"])
        pf = pf[pf["corte"] == a]
        self.c_grupo = pf.groupby("grupo")["c_cal"].first().to_dict()
        self.c_def = float(pf["c_cal"].median()) if len(pf) else 0.43
        self.f1c = cfg["f1"]

    def escenario(self, liga: str, team: str, club_t, miembros, roles: dict, n_sim: int, semilla: int) -> dict | None:
        from .escenarios import ajustar_suma
        from .. import equipo as EQ
        ins, S = self.ins, self.ins.S
        pr = ins.minutos(liga, team, club_t, miembros, n_sim, semilla)
        if pr is None:
            return None
        P, Pm = pr
        gm = float(S.minutos_partido(liga))
        pids = list(P["persona_id"].astype(str))
        M = Pm * gm
        fuerza = {pids.index(p): r for p, r in roles.items() if p in pids and r}
        if fuerza:
            S.forzar_roles(M, fuerza, 5 * gm, gm, liga, ins.c, np.random.default_rng(semilla + 7777))
        M = ajustar_suma(M, 5 * gm, gm, np.array([i in fuerza for i in range(len(pids))]))
        ref = ins.c.ref["uso"].get(liga, (20.0, 5.0))
        usg = np.full(len(pids), np.nan)
        for i, r in P.reset_index(drop=True).iterrows():
            rr = r.get("_reg")
            if isinstance(rr, dict):
                usg[i] = S._uso_natural(ins.c, rr, liga)[0]
        usg = np.clip(np.where(np.isfinite(usg), usg, ref[0] - 0.5 * ref[1]), 5, 45)
        U2, _ = S.redistribuir_uso(M, np.repeat(usg[None, :], n_sim, 0), float(self.f1c["uso_medio_pista"]),
                                   float(self.f1c["uso_amortiguar"]))
        v = EQ.valor_equipo(ins, liga, pids, M / gm, np.random.default_rng(semilla))
        return {"pids": pids, "M": M, "Pm": M / gm, "U": (U2 * M).sum(0) / np.maximum(M.sum(0), 1e-9), "T": v["T"], "gm": gm}

    def f2b_delta(self, e: dict, x: str, ks: list[str], signo: float) -> dict:
        """±π_kx·d̂(x→k) con π del escenario en que x está (alta: el nuevo; baja: la base)."""
        from .escenarios import pares_en_pista
        pids = e["pids"]
        if x not in pids:
            return {}
        ix = pids.index(x)
        Z = self.ins.z(pids)
        P = pares_en_pista(e["Pm"])
        p = e["Pm"].mean(0)
        out = {}
        con_x = np.abs(Z[ix]).sum() > 0
        for k in ks:
            if k not in pids:
                continue
            ik = pids.index(k)
            X = np.hstack([Z[ix], Z[ik], Z[ix] * Z[ik]])[None, :]
            pi = P[ik, ix] / max(p[ik], 1e-9)
            ok = con_x and np.abs(Z[ik]).sum() > 0
            out[k] = {m: (signo * pi * float(mod.predecir(X)[0]) if ok else 0.0) for m, mod in self.f2b.items()} | {"pi": pi, "con_perfil": bool(ok)}
        return out

    def c(self, liga: str) -> float:
        from .. import equipo as EQ
        return float(self.c_grupo.get(EQ.GRUPOS_LIGA.get(liga, "otras"), self.c_def))


def predecir_evento(pr: Predictor, ev: dict, base: dict, n_sim: int, semilla: int, corregida: bool = False) -> pd.DataFrame | None:
    """Añade al evento las predicciones del modelo para cada compañero (Δmin, Δuso, F2-B) y el ΔNet del equipo.
    `corregida` (V-TRANS, POST HOC 09-11-2026): plantilla de t con su presencia real (como la de t+1) y rol oráculo sólo para
    las altas con presencia ≥ 0,5 (las de media temporada entran por el motor con su presencia: forzar_roles no la usa)."""
    liga, team, movs = ev["liga"], ev["team"], ev["movs"]
    S = pr.ins.S
    if ev["banco"] == "V-TRANS":
        minp = float(S.cfg_sim()["plantilla"]["minimo_presencia"])
        r1 = pr.ins.roles[pr.ins.roles["temporada"] == pr.ins.temp1]
        mi = S.miembros_reales(r1, liga, team, minp)
        roles_a = {a: r for t, a, r in movs if t == "alta" and r}
        if corregida:
            r0 = pr.ins.roles[pr.ins.roles["temporada"] == pr.ins.temp]
            mi0 = S.miembros_reales(r0, ev["liga0"], ev["team0"], minp)
            pres = dict(mi)
            roles_a = {a: r for a, r in roles_a.items() if pres.get(a, 0.0) >= 0.5}
        else:
            mi0 = ev["miembros0"]
        e0 = pr.escenario(ev["liga0"], ev["team0"], ev["club_t"], mi0, {}, n_sim, semilla)
        e1 = pr.escenario(liga, team, ev["club_t"], mi, roles_a, n_sim, semilla)
    else:
        e0 = base["e"]
        mi = base["miembros"]
        if movs[0][0] == "baja":
            e1 = pr.escenario(liga, team, base["club_t"], [m for m in mi if m[0] != movs[0][1]], {}, n_sim, semilla)
        else:
            e0 = pr.escenario(liga, team, base["club_t"], [m for m in mi if m[0] != movs[0][1]], {}, n_sim, semilla)
            e1 = pr.escenario(liga, team, base["club_t"], mi if any(m[0] == movs[0][1] for m in mi) else mi + [(movs[0][1], 1.0)],
                              {movs[0][1]: movs[0][2]} if movs[0][2] else {}, n_sim, semilla)
    if e0 is None or e1 is None:
        return None
    D = ev["comp"].copy()
    m0 = dict(zip(e0["pids"], e0["M"].mean(0))); m1 = dict(zip(e1["pids"], e1["M"].mean(0)))
    u0 = dict(zip(e0["pids"], e0["U"])); u1 = dict(zip(e1["pids"], e1["U"]))
    D["pred_minutos"] = [m1.get(k, np.nan) - m0.get(k, np.nan) for k in D.index]
    D["pred_uso"] = [u1.get(k, np.nan) - u0.get(k, np.nan) for k in D.index]
    for m in ("cuota_tiro", "pct_asistidas", "pts100"):
        D[f"pred_{m}"] = 0.0
    D["f2b_con_perfil"] = False
    ks = list(D.index)
    for t, x, _ in movs:
        dd = pr.f2b_delta(e1 if t == "alta" else e0, x, ks, 1.0 if t == "alta" else -1.0)
        for k, v in dd.items():
            D.loc[k, "pred_cuota_tiro"] += v["d_cuota_tiro"]
            D.loc[k, "pred_pct_asistidas"] += v["d_pct_asistidas"]
            D.loc[k, "pred_pts100"] += v["d_pts100"]
            D.loc[k, "f2b_con_perfil"] = D.loc[k, "f2b_con_perfil"] or v["con_perfil"]
    D["gm"] = e1["gm"]
    # datos ≤ el movimiento para la línea base (ii): minutos y cuotas de quien se mueve
    mv = []
    for t, x, r in movs:
        if t == "baja":
            b = ev["mover_base"].get(x) or {}
            mv.append({"tipo": t, "m": b.get("minutos", m0.get(x, np.nan)), "uso": b.get("uso", np.nan), "cuota_tiro": b.get("cuota_tiro", np.nan)})
        else:
            cen = float(pr.ins.c.mod["min_rol"].get((liga, r), pr.ins.c.mod["min_rol_global"].get(r, 0.4))) * e1["gm"] if r else m1.get(x, np.nan)
            pv = base.get("previa", {}).get(x, {})
            mv.append({"tipo": t, "m": cen, "uso": pv.get("uso", np.nan), "cuota_tiro": pv.get("cuota_tiro", np.nan)})
    D.attrs["movers"] = mv
    eq = {"pred_net": pr.c(liga) * float(e1["T"].mean() - e0["T"].mean()), "net_obs": ev["net_obs"], "w_net": ev["w_net"],
          "poss_min": ev["poss_min"]}
    D.attrs["equipo"] = eq
    return D


def previa_jugadores(d_prev: pd.DataFrame | None) -> dict:
    """Cuotas (uso, cuota de tiro) de cada persona en la temporada anterior (todas sus filas): información ≤ t de las altas."""
    if d_prev is None or d_prev.empty:
        return {}
    A = d_prev.groupby("persona_id")[SUMAS].sum()
    A["partidos"] = d_prev.groupby("persona_id")["game_id"].nunique()
    m = metricas(A)
    return {p: {"uso": u, "cuota_tiro": c} for p, u, c in zip(m.index, m["uso"], m["cuota_tiro"])}


def corte(cfg: dict, a: int, n_sim: int = 200, progreso=print) -> pd.DataFrame:
    """Bancos de la temporada t+1 (V-AUS, V-MID) y de la transición t → t+1 (V-TRANS) con predicciones ≤ t. Caché."""
    DIR.mkdir(parents=True, exist_ok=True)
    cp = DIR / f"corte_{a}.pkl"
    if cp.exists():
        return pickle.loads(cp.read_bytes())
    t0 = time.time()
    os.environ.setdefault("CERNO_SIMULADOR", "v32")
    pr = Predictor(cfg, a, progreso)
    ins, S, V = pr.ins, pr.ins.S, pr.ins.V
    t, t1 = ins.temp, ins.temp1
    d0, d1 = partidos(t), partidos(t1)
    roles1 = pd.read_csv(CE.RAIZ / pr.ins.cfg40["insumos"]["roles"], usecols=["liga", "temporada", "team_id", "persona_id", "rol"],
                         dtype={"team_id": str, "persona_id": str}, low_memory=False)
    roles1 = roles1[roles1["temporada"] == t1]
    previa = previa_jugadores(d0)
    eventos = v_aus(cfg, t1, d1) + v_mid(cfg, t1, d1, roles1) + v_trans(cfg, ins, d0, d1, roles1)
    if progreso:
        progreso(f"  F3 corte {a}: eventos " + str(pd.Series([e["banco"] for e in eventos]).value_counts().to_dict()) +
                 f" · {time.time() - t0:.0f} s", flush=True)
    mapa = V.mapa_clubes(ins.roles, t, t1)
    r1 = ins.roles[ins.roles["temporada"] == t1]
    minp = float(S.cfg_sim()["plantilla"]["minimo_presencia"])
    bases, filas, equipos = {}, [], []
    rng = np.random.default_rng(CE.semilla(cfg, f"bancos|{a}"))
    for i, ev in enumerate(eventos):
        key = (ev["liga"], ev["team"])
        sem = int(CE.semilla(cfg, f"bancos|{a}|{key}"))
        if ev["banco"] != "V-TRANS":
            if key not in bases:
                club_t = V.club_en_t(ins.c, ev["liga"], ev["team"], None, mapa)
                mi = S.miembros_reales(r1, ev["liga"], ev["team"], minp)
                bases[key] = {"club_t": club_t, "miembros": mi,
                              "e": pr.escenario(ev["liga"], ev["team"], club_t, mi, {}, n_sim, sem) if mi else None}
            b = bases[key]
            if b["e"] is None:
                continue
        else:
            b = {}
        b = {**b, "previa": previa}
        try:
            D = predecir_evento(pr, ev, b, n_sim, sem)
        except Exception as exc:                         # un equipo raro no detiene el banco (se cuenta)
            if progreso:
                progreso(f"    evento {ev['banco']} {key} omitido: {exc}", flush=True)
            continue
        if D is None:
            continue
        mov_id = f"{ev['banco']}|{ev['liga']}|{ev['team']}|{i}"
        D = D.reset_index().rename(columns={"index": "persona_id"})
        mvs = D.attrs["movers"]
        D["evento"], D["banco"], D["anio"], D["liga"], D["team"] = mov_id, ev["banco"], a, ev["liga"], ev["team"]
        D["movers"] = [mvs] * len(D)
        filas.append(D)
        eqd = D.attrs["equipo"]
        equipos.append({"evento": mov_id, "banco": ev["banco"], "anio": a, "liga": ev["liga"], "team": ev["team"],
                        "n_movs": len(ev["movs"]), "tipo": ev["movs"][0][0] if len(ev["movs"]) == 1 else "varios", **eqd})
        if progreso and (i + 1) % 250 == 0:
            progreso(f"    F3 corte {a}: {i + 1}/{len(eventos)} eventos · {time.time() - t0:.0f} s", flush=True)
    C = pd.concat(filas, ignore_index=True) if filas else pd.DataFrame()
    E = pd.DataFrame(equipos)
    res = {"companeros": C, "equipos": E, "segundos": round(time.time() - t0)}
    cp.write_bytes(pickle.dumps(res))
    if progreso:
        progreso(f"  F3 corte {a}: {len(C)} filas de compañeros, {len(E)} eventos · {time.time() - t0:.0f} s", flush=True)
    return res


def corte_trans_corregida(cfg: dict, a: int, n_sim: int = 200, progreso=print) -> pd.DataFrame:
    """[POST HOC, 09-11-2026] V-TRANS con la corrección de presencias (ver predecir_evento). Banco «V-TRANS-c», informado
    junto al literal prerregistrado. Caché experimentos/v4_1/bancos/corte_<a>_trans_c.pkl."""
    cp = DIR / f"corte_{a}_trans_c.pkl"
    if cp.exists():
        return pickle.loads(cp.read_bytes())
    t0 = time.time()
    os.environ.setdefault("CERNO_SIMULADOR", "v32")
    pr = Predictor(cfg, a, progreso)
    ins = pr.ins
    d0, d1 = partidos(ins.temp), partidos(ins.temp1)
    roles1 = pd.read_csv(CE.RAIZ / ins.cfg40["insumos"]["roles"], usecols=["liga", "temporada", "team_id", "persona_id", "rol"],
                         dtype={"team_id": str, "persona_id": str}, low_memory=False)
    roles1 = roles1[roles1["temporada"] == ins.temp1]
    previa = previa_jugadores(d0)
    filas, equipos = [], []
    for i, ev in enumerate(v_trans(cfg, ins, d0, d1, roles1)):
        sem = int(CE.semilla(cfg, f"bancos|{a}|{(ev['liga'], ev['team'])}"))
        try:
            D = predecir_evento(pr, ev, {"previa": previa}, n_sim, sem, corregida=True)
        except Exception as exc:
            if progreso:
                progreso(f"    evento V-TRANS-c {ev['team']} omitido: {exc}", flush=True)
            continue
        if D is None:
            continue
        mov_id = f"V-TRANS-c|{ev['liga']}|{ev['team']}|{i}"
        D = D.reset_index().rename(columns={"index": "persona_id"})
        mvs, eqd = D.attrs["movers"], D.attrs["equipo"]
        D["evento"], D["banco"], D["anio"], D["liga"], D["team"] = mov_id, "V-TRANS-c", a, ev["liga"], ev["team"]
        D["movers"] = [mvs] * len(D)
        filas.append(D)
        equipos.append({"evento": mov_id, "banco": "V-TRANS-c", "anio": a, "liga": ev["liga"], "team": ev["team"],
                        "n_movs": len(ev["movs"]), "tipo": "varios", **eqd})
    res = {"companeros": pd.concat(filas, ignore_index=True) if filas else pd.DataFrame(), "equipos": pd.DataFrame(equipos),
           "segundos": round(time.time() - t0)}
    cp.write_bytes(pickle.dumps(res))
    if progreso:
        progreso(f"  V-TRANS-c corte {a}: {len(equipos)} eventos · {time.time() - t0:.0f} s", flush=True)
    return res
