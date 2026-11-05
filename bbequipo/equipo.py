"""F4 · Composición, Δ de equipo y examen §11.4 (capa 4; encargo §9). Sobre F1 + F2 + F3 congelados:

    T(R) = E_{S ~ P(·|R)}[ f(S) ],   f(S) = Σ_{i∈S} β_i + Σ_{i<j∈S} φ_ij + Σ_{i∈S} h(z_i)
    Net̂(R) = T(R) − media de la liga-temporada;   Δ̂Net = Net̂(R'_{t+1}) − Net̂(R_t)

* P(S | R): la cuota de posesiones de cada jugador p_i = minutos_i / minutos de un puesto (Σ_i p_i = 5). En t, los minutos
  observados; en t+1, los proyectados con el motor de minutos de la v3.3 (Plackett-Luce sobre nivel × encaje, tendencia
  del entrenador, restricciones posicionales; pesos de la utilidad ajustados sólo con temporadas ≤ t) por Monte Carlo.
  Lo aditivo (β, h) sólo necesita las cuotas p_i (exacto); el término de parejas usa P(i,j en pista) ≈ p_i p_j
  renormalizado a las 10 parejas de un quinteto.
* Incertidumbre propagada: β ~ N(β̂, sd) por jugador y simulación; minutos por simulación del motor; la traducción entre
  ligas va dentro de la sd de β (escala común de F1). φ y h fijos (de segundo orden).
* Jugadores de t+1 sin β ≤ t: prior del perfil si lo hay; si no, el nivel de «jugador nuevo» de su liga (media ponderada de
  β de los jugadores en su primera temporada, ≤ t) [DECISIÓN F3 (c)].
* Examen §11.4: transiciones reales equipo-temporada t → t+1 (`reemplazo/libro_roles_equipos.csv`: mismo club, misma
  liga), plantilla real de t+1 (pertenencia y presencia), todo lo demás ≤ t. Líneas base: persistencia (Δ = 0), aditivo F1
  (sin φ ni h), GBM directo sobre transiciones (cortes anteriores). Métricas: MAE de ΔNet, Spearman, cobertura del 80 %
  (intervalos del Monte Carlo ensanchados con los residuos de los cortes anteriores), por grupo de liga y global.
Salidas: data/modelos/v4_0/equipo/.
"""
from __future__ import annotations

import json
import os
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from . import examen_f1 as EX
from . import rapm as RP
from . import sinergia as SG
from . import conjunto as CJ

GRUPOS_LIGA = {"nba": "nba", "gleague": "eeuu_menor", "ncaa": "eeuu_menor", "euroleague": "europa_top", "eurocup": "europa_top",
               "acb": "europa_top", "lba": "europa_media", "lnb": "europa_media", "bsl": "europa_media", "vtb": "europa_media",
               "bcl": "europa_media", "bbl": "europa_menor", "bnxt": "europa_menor", "gbl": "europa_menor", "fec": "europa_menor",
               "feb1": "feb", "feb2": "feb", "feb3": "feb", "cba": "otras", "nbl": "otras"}


def dir_salida(cfg: dict) -> Path:
    d = C.RAIZ / cfg["f4"]["salida"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sim():
    """bbfit.simulador con el entorno de corte de la v3.2/v3.3 (cachés existentes); fijado antes de importar bbfit."""
    cfg = C.cargar()
    os.environ.setdefault("CERNO_SIMULADOR", cfg["insumos"].get("simulador_env_corte", "v32"))
    from bbfit import simulador as S  # noqa: E402
    from bbfit import validacion as V  # noqa: E402
    from bbfit import sim_insumos as SI  # noqa: E402
    from bbfit import reemplazo as RE  # noqa: E402
    return S, V, SI, RE


# =============================================================================================== transiciones de equipo
def transiciones(cfg: dict) -> pd.DataFrame:
    """Transiciones reales equipo-temporada t → t+1 del libro de roles (fila TOTAL): club estable, Net ajustado de la fase
    regular en t y t+1."""
    l = pd.read_csv(C.RAIZ / "data/modelos/reemplazo/libro_roles_equipos.csv", low_memory=False, dtype={"team_id_ant": str, "team_id_nuevo": str})
    l = l[(l["rol"] == "TOTAL") & l["delta_net"].notna() & ~l["temporada_en_curso"].astype(bool)].copy()
    l["anio"] = l["temporada_ant"].str[:4].astype(int)
    l["grupo"] = l["liga"].map(GRUPOS_LIGA).fillna("otras")
    return l[["liga", "grupo", "club", "temporada_ant", "temporada_nueva", "anio", "team_id_ant", "team_id_nuevo", "n_retornos",
              "n_salidas", "n_llegadas", "min_liberados", "min_absorbidos", "uso_liberado", "uso_absorbido", "net_ant", "net_nuevo",
              "delta_net"]].reset_index(drop=True)


# =============================================================================================== insumos de un corte
class Insumos:
    """Todo lo que F4 necesita del corte t: β (F1), z y M_r (F2), h (F3 aditiva), corte v3.3 (motor de minutos), roles."""

    def __init__(self, cfg: dict, a: int, tr_all: pd.DataFrame, progreso=print):
        self.cfg, self.a = cfg, a
        self.temp = f"{a}-{str(a + 1)[-2:]}"
        self.temp1 = f"{a + 1}-{str(a + 2)[-2:]}"
        aj = EX.ajuste_corte(cfg, a, tr_all, "gbm", progreso=None)
        self.aj = aj
        tb = aj["tb"].copy()
        tb["anio"] = tb["temporada"].str[:4].astype(int)
        self.tb = tb
        # β más reciente ≤ t por persona (y su sd); prior del perfil de t para quien tiene perfil sin β
        ult = tb.sort_values("anio").drop_duplicates("persona_id", keep="last").set_index("persona_id")
        self.beta = ult["beta"].to_dict(); self.beta_sd = ult["beta_sd"].to_dict(); self.beta_anio = ult["anio"].to_dict()
        pr = aj["res"]["priors"][0]
        T = aj["T"]
        self.prior = dict(zip(T["clave"], pr.predecir(T))) if pr is not None else {}
        self.tau = float(np.sqrt(aj["res"].get("tau2", np.nan))) if np.isfinite(aj["res"].get("tau2", np.nan)) else float(np.nanmedian(tb["beta_sd"]))
        # nivel de «jugador nuevo» por liga (primera temporada en los datos, ≤ t; 2020-21 no cuenta) y media de liga
        liga = tb["liga_principal"] if "liga_principal" in tb else None
        if liga is not None:
            prim = tb.groupby("persona_id")["anio"].transform("min")
            nuevos = tb[(tb["anio"] == prim) & (tb["anio"] > 2020)]
            w = np.maximum(nuevos["poss"], 1.0)
            self.nivel_nuevo = nuevos.assign(w=w).groupby("liga_principal").apply(lambda g: np.average(g["beta"], weights=g["w"])).to_dict()
            self.media_liga = tb.assign(w=np.maximum(tb["poss"], 1.0)).groupby("liga_principal").apply(lambda g: np.average(g["beta"], weights=g["w"])).to_dict()
        else:
            self.nivel_nuevo, self.media_liga = {}, {}
        self.nivel_nuevo_global = float(np.mean(list(self.nivel_nuevo.values()))) if self.nivel_nuevo else 0.0
        # F2: rasgos z y M_r del corte
        self.R = SG.Rasgos(T, cfg)
        ex2 = json.loads((SG.dir_salida(cfg) / "examen" / "resumen_examen_f2a.json").read_text(encoding="utf-8"))
        rango = ex2["decisiones"]["rango"]
        self.Mr, _ = SG.truncar(np.load(SG.dir_salida(cfg) / "examen" / f"M_corte_{a}.npy"), None if rango == "completa" else int(rango))
        # F3 aditiva del corte (si está): h_i = g({i}) − g(∅)
        suf = "aditiva" if cfg["f3"].get("rho_lineal", False) else "completa"
        p3 = CJ.dir_salida(cfg) / "examen" / f"red_corte_{a}_{suf}.pkl"
        self.red = CJ.ConjuntoNet(self.R.Z, cfg).cargar(pickle.loads(p3.read_bytes()), int(cfg["semilla"])) if p3.exists() else None
        self._h = {}
        # v3.3: corte, roles, pesos PL del corte
        S, V, SI, RE = _sim()
        self.S, self.V, self.SI, self.RE = S, V, SI, RE
        self.c = S.cargar_corte(self.temp, cfg["insumos"].get("fuente_corte", "V32_corte"), pesos=False)
        self.roles = SI._leer_roles_temporada()
        pesos = pesos_pl(self, progreso)
        self.c.w_util = pesos["utilidad"]; self.c.calib = pesos.get("calibracion", {})
        self.cfg_re = RE._cfg()
        if progreso:
            progreso(f"  insumos corte {a}: β de {len(self.beta)} personas · perfiles {len(T)} · F3 {'sí' if self.red else 'no'} · "
                     f"nivel nuevo {self.nivel_nuevo_global:+.2f} · pesos PL {len(pesos['utilidad'])}", flush=True)

    # ---- valor de un jugador
    def valor(self, pid: str, liga: str) -> tuple[float, float, str]:
        """(β, sd, fuente) de la persona con información ≤ t."""
        if pid in self.beta and np.isfinite(self.beta[pid]):
            return float(self.beta[pid]), float(self.beta_sd.get(pid, self.tau)), "beta"
        k = f"{pid}|{self.temp}"
        if k in self.prior and np.isfinite(self.prior[k]):
            return float(self.prior[k]), self.tau, "prior"
        return float(self.nivel_nuevo.get(liga, self.nivel_nuevo_global)), self.tau * 1.5, "nuevo"

    def z(self, pids: list[str]) -> np.ndarray:
        return self.R.de([f"{p}|{self.temp}" for p in pids])

    def h(self, pids: list[str]) -> np.ndarray:
        if self.red is None:
            return np.zeros(len(pids))
        cero = len(self.R.idx)
        falta = [p for p in pids if p not in self._h]
        if falta:
            I = np.array([[self.R.idx.get(f"{p}|{self.temp}", cero)] + [cero] * 9 for p in falta])
            for p, v in zip(falta, self.red.predecir(I)):
                self._h[p] = float(v)
        return np.array([self._h[p] for p in pids])

    # ---- minutos
    def cuotas_observadas(self, liga: str, team_id: str, temp: str) -> pd.DataFrame:
        """p_i = minutos_i / (minutos del equipo / 5) en la temporada `temp` (observado)."""
        g = self.roles[(self.roles["liga"] == liga) & (self.roles["team_id"].astype(str) == str(team_id)) & (self.roles["temporada"] == temp)]
        g = g.sort_values("min_total", ascending=False).drop_duplicates("persona_id")
        tot = g["min_total"].sum() / 5.0
        return pd.DataFrame({"persona_id": g["persona_id"].to_numpy(), "p": g["min_total"].to_numpy(float) / tot,
                             "pos3": g["pos3"].to_numpy(object)})

    def cuotas_proyectadas(self, liga: str, team_id1: str, club_t: str | None, n_sim: int, semilla: int) -> tuple[pd.DataFrame, np.ndarray] | None:
        """Plantilla real de t+1 (pertenencia y presencia) con minutos proyectados por el motor v3.3 (≤ t): matriz
        (n_sim × n) de cuotas p_i por simulación."""
        S, RE = self.S, self.RE
        r1 = self.roles[self.roles["temporada"] == self.temp1]
        miembros = S.miembros_reales(r1, liga, team_id1, float(S.cfg_sim()["plantilla"]["minimo_presencia"]))
        if len(miembros) < 7:
            return None
        club_d = club_t or f"{liga}|{team_id1}"
        P = S.plantilla(self.c, club_d, liga, miembros)
        if P.empty or len(P) < 7:
            return None
        P["encaje"] = pd.to_numeric(P.get("encaje_pos", 0.0), errors="coerce").fillna(0.0)
        P["nivel"] = S.utilidad(self.c, P) * float(self.c.calib.get("escala_utilidad", 1.0))
        ent = r1[(r1["liga"] == liga) & (r1["team_id"].astype(str) == str(team_id1))]["entrenador_id"].dropna()
        entrenador = ent.mode().iloc[0] if len(ent) else S.entrenador_equipo(self.c, liga, team_id1)
        rot, rot_sd, curva = S.tendencia(self.c, entrenador, liga)
        gm = S.minutos_partido(liga)
        pl = pd.DataFrame({"player_id": P["persona_id"].to_numpy(), "nivel": P["nivel"].to_numpy(float), "pos3": P["pos3"].to_numpy(object)})
        _, M = RE.asignar_minutos(pl, total_min=5 * gm, minutos_partido=gm, rotacion_media=rot, rotacion_sd=rot_sd, curva=curva,
                                  n_sim=n_sim, semilla=semilla, cfg=self.cfg_re, devolver_simulaciones=True,
                                  presencia=P["presencia"].to_numpy(float))
        return P[["persona_id", "pos3", "presencia", "nuevo", "sin_dato"]].reset_index(drop=True), M / gm


def pesos_pl(ins: "Insumos", progreso=print) -> dict:
    """Pesos de la utilidad Plackett-Luce ajustados SÓLO con temporadas s ≤ t cuyo corte s−1 existe (hay redes CVAE por corte
    desde 2021-22: para t = 2021 no hay temporada de ajuste y se usan los pesos iniciales de la configuración). Misma
    verosimilitud que validacion.entrenar_pesos. Caché en experimentos/v4_0/pesos_pl_<t>.json."""
    S, V = ins.S, ins.V
    cfg_sim = S.cfg_sim()
    dest = C.RAIZ / "experimentos" / "v4_0" / f"pesos_pl_{ins.temp}.json"
    if dest.exists():
        return json.loads(dest.read_text())
    temps = [x for x in cfg_sim["historico"]["temporadas"] if x <= ins.temp]
    fuente = ins.cfg["insumos"].get("fuente_corte", "V32_corte")
    disponibles = {"2021-22", "2022-23", "2023-24", "2024-25"}
    bloques, extras = [], []
    for s in temps[1:]:
        prev = temps[temps.index(s) - 1]
        if prev not in disponibles:
            continue
        c_prev = S.cargar_corte(prev, fuente, pesos=False)
        bloques += V.bloques_utilidad(c_prev, ins.roles, s, cfg_sim)
        extras.append(V.rotacion_extra(c_prev, ins.roles, s))
    w = V.ajustar_utilidad(bloques, cfg_sim) if bloques else dict(cfg_sim["utilidad"]["inicial"])
    res = {"utilidad": w, "calibracion": {"rotacion_extra": float(np.median(extras)) if extras else 1.0, "disponibilidad": 0.85},
           "equipos_entrenamiento": len(bloques), "temporadas": [s for s in temps[1:] if temps[temps.index(s) - 1] in disponibles]}
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(res, indent=1))
    if progreso:
        progreso(f"  pesos PL ≤ {ins.temp}: {len(bloques)} equipos · " + ", ".join(f"{k} {v:+.2f}" for k, v in w.items() if not k.startswith("_")), flush=True)
    return res


# =============================================================================================== valor de un equipo
def valor_equipo(ins: Insumos, liga: str, pids: list[str], Pm: np.ndarray, rng, con_f2: bool = True, con_f3: bool = True,
                 muestrear_beta: bool = True) -> dict:
    """T por simulación: Pm (n_sim × n) cuotas; β ~ N(β̂, sd); parejas con P_ij ≈ p_i p_j renormalizado a 10; h aditiva."""
    n_sim, n = Pm.shape
    b = np.array([ins.valor(p, liga) [0] for p in pids]); sd = np.array([ins.valor(p, liga)[1] for p in pids])
    fuente = [ins.valor(p, liga)[2] for p in pids]
    B = b[None, :] + (rng.normal(size=(n_sim, n)) * sd[None, :] if muestrear_beta else 0.0)
    T_add = (Pm * B).sum(1)
    T_phi = np.zeros(n_sim); T_h = np.zeros(n_sim)
    if con_f2:
        Z = ins.z(pids)
        Phi = Z @ ins.Mr @ Z.T; np.fill_diagonal(Phi, 0.0)
        # Σ_{i<j} P_ij φ_ij con P_ij = p_i p_j · 10 / Σ_{i<j} p_i p_j
        pp = (Pm.sum(1) ** 2 - (Pm ** 2).sum(1)) / 2.0          # Σ_{i<j} p_i p_j
        T_phi = 0.5 * np.einsum("si,ij,sj->s", Pm, Phi, Pm) * 10.0 / np.maximum(pp, 1e-9)
    if con_f3:
        T_h = Pm @ ins.h(pids)
    return {"T": T_add + T_phi + T_h, "T_aditivo": T_add, "T_phi": T_phi, "T_h": T_h, "beta": b, "sd": sd, "fuente": fuente}


# =============================================================================================== examen por corte
def examen_corte(cfg: dict, a: int, tr_all: pd.DataFrame, trans: pd.DataFrame, progreso=print, solo_ligas=None) -> pd.DataFrame:
    f4 = cfg["f4"]
    n_sim = int(f4["monte_carlo"]["simulaciones"])
    rng = np.random.default_rng(int(cfg["semilla"]) + a)
    t0 = time.time()
    ins = Insumos(cfg, a, tr_all, progreso)
    S, V = ins.S, ins.V
    tr = trans[trans["anio"] == a].copy()
    if solo_ligas:
        tr = tr[tr["liga"].isin(solo_ligas)]
    mapa = V.mapa_clubes(ins.roles, ins.temp, ins.temp1)
    filas = []
    for liga, g in tr.groupby("liga"):
        gm = S.minutos_partido(liga)
        # todos los equipos de la liga en t (observado) y en t+1 (proyectado) para centrar dentro de la liga-temporada
        T_t, T_t1 = {}, {}
        for row in g.itertuples():
            q = ins.cuotas_observadas(liga, row.team_id_ant, ins.temp)
            if len(q) < 5:
                continue
            Pm = np.tile(q["p"].to_numpy(float), (1, 1))
            v = valor_equipo(ins, liga, list(q["persona_id"]), Pm, rng, muestrear_beta=False)
            T_t[row.club] = {"T": float(v["T"][0]), "T_aditivo": float(v["T_aditivo"][0])}
            club_t = V.club_en_t(ins.c, liga, row.team_id_nuevo, None, mapa)
            pr = ins.cuotas_proyectadas(liga, row.team_id_nuevo, club_t, n_sim, int(cfg["semilla"]) + hash((liga, row.club)) % 10000)
            if pr is None:
                continue
            P, Pm1 = pr
            v1 = valor_equipo(ins, liga, list(P["persona_id"]), Pm1, rng)
            # diagnóstico: minutos reales de t+1 (oráculo) con los mismos β
            q1 = ins.cuotas_observadas(liga, row.team_id_nuevo, ins.temp1)
            vo = valor_equipo(ins, liga, list(q1["persona_id"]), np.tile(q1["p"].to_numpy(float), (1, 1)), rng, muestrear_beta=False) if len(q1) >= 5 else None
            altas = P["nuevo"].to_numpy(float) > 0.5
            T_t1[row.club] = {"T": v1["T"], "T_aditivo": v1["T_aditivo"], "T_phi": v1["T_phi"], "T_h": v1["T_h"],
                              "T_oraculo": float(vo["T"][0]) if vo is not None else np.nan,
                              "min_altas": float((Pm1[:, altas].sum(1) / 5.0).mean()) if altas.any() else 0.0,
                              "n_plantilla": int(len(P)), "n_sin_beta": int(sum(f != "beta" for f in v1["fuente"])),
                              "n_nuevo": int(sum(f == "nuevo" for f in v1["fuente"]))}
        if len(T_t1) < 3:
            continue
        m_t = np.mean([v["T"] for v in T_t.values()]); m_t_add = np.mean([v["T_aditivo"] for v in T_t.values()])
        M1 = np.mean([v["T"] for v in T_t1.values()], axis=0); M1_add = np.mean([v["T_aditivo"] for v in T_t1.values()], axis=0)
        m_or = np.nanmean([v["T_oraculo"] for v in T_t1.values()])
        for row in g.itertuples():
            if row.club not in T_t1 or row.club not in T_t:
                continue
            x, y = T_t[row.club], T_t1[row.club]
            d = (y["T"] - M1) - (x["T"] - m_t)
            d_add = (y["T_aditivo"] - M1_add) - (x["T_aditivo"] - m_t_add)
            filas.append({"corte": a, "liga": liga, "grupo": row.grupo, "club": row.club, "temporada_ant": row.temporada_ant,
                          "temporada_nueva": row.temporada_nueva, "net_ant": row.net_ant, "net_nuevo": row.net_nuevo, "delta_real": row.delta_net,
                          "delta_pred": float(d.mean()), "delta_sd": float(d.std()), "delta_p10": float(np.quantile(d, .10)), "delta_p90": float(np.quantile(d, .90)),
                          "delta_p25": float(np.quantile(d, .25)), "delta_p75": float(np.quantile(d, .75)), "delta_p05": float(np.quantile(d, .05)), "delta_p95": float(np.quantile(d, .95)),
                          "delta_aditivo": float(d_add.mean()), "delta_phi": float((y["T_phi"]).mean()), "delta_h": float(y["T_h"].mean()),
                          "delta_oraculo_minutos": float((y["T_oraculo"] - m_or) - (x["T"] - m_t)) if np.isfinite(y["T_oraculo"]) else np.nan,
                          "nethat_t": float(x["T"] - m_t), "nethat_t1": float((y["T"] - M1).mean()),
                          "min_altas": y["min_altas"], "n_plantilla": y["n_plantilla"], "n_sin_beta": y["n_sin_beta"], "n_nuevo": y["n_nuevo"],
                          "n_salidas": row.n_salidas, "n_llegadas": row.n_llegadas, "min_liberados": row.min_liberados, "min_absorbidos": row.min_absorbidos,
                          "uso_liberado": row.uso_liberado, "uso_absorbido": row.uso_absorbido})
        if progreso:
            e = pd.DataFrame([f for f in filas if f["liga"] == liga])
            progreso(f"    corte {a} {liga}: {len(e)} equipos · MAE Δ̂ {np.mean(np.abs(e['delta_real'] - e['delta_pred'])):.2f} · "
                     f"persistencia {np.mean(np.abs(e['delta_real'])):.2f} · oráculo minutos {np.nanmean(np.abs(e['delta_real'] - e['delta_oraculo_minutos'])):.2f} · "
                     f"corr {np.corrcoef(e['delta_real'], e['delta_pred'])[0, 1] if len(e) > 2 else np.nan:+.2f} · {time.time() - t0:.0f} s", flush=True)
    return pd.DataFrame(filas)


# =============================================================================================== métricas y examen completo
def _boot(d: pd.DataFrame, f, B: int, semilla: int) -> list[float]:
    rng = np.random.default_rng(semilla)
    vals = []
    for _ in range(B):
        ii = rng.integers(0, len(d), len(d)); vals.append(f(d.iloc[ii]))
    return [float(np.quantile(vals, 0.025)), float(np.quantile(vals, 0.975))]


def gbm_directo(pred: pd.DataFrame, cortes: list[int]) -> np.ndarray:
    """Línea base (c): GBM supervisado directo sobre las transiciones (rasgos del libro + Δ̂ aditivo), entrenado SÓLO con
    los cortes anteriores a cada corte (el primero: NaN)."""
    from sklearn.ensemble import HistGradientBoostingRegressor
    cols = ["net_ant", "n_salidas", "n_llegadas", "min_liberados", "min_absorbidos", "uso_liberado", "uso_absorbido", "delta_aditivo", "min_altas"]
    X = pred[cols].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    y = pred["delta_real"].to_numpy(float)
    out = np.full(len(pred), np.nan)
    for k, a in enumerate(cortes[1:], 1):
        tr = pred["corte"].isin(cortes[:k]).to_numpy(); te = (pred["corte"] == a).to_numpy()
        if tr.sum() < 50 or te.sum() == 0:
            continue
        m = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_depth=3, min_samples_leaf=20, l2_regularization=1.0, random_state=0)
        out[te] = m.fit(X[tr], y[tr]).predict(X[te])
    return out


def calibrar_intervalos(pred: pd.DataFrame, cortes: list[int], nivel: float = 0.8) -> pd.DataFrame:
    """Intervalo del 80 % conformal: Δ̂ ± q con q el cuantil 0,8 de |residuo| de los cortes anteriores, escalado por la sd
    del Monte Carlo (q = cuantil de |residuo|/sd_MC); el primer corte usa sus propios residuos (sólo informativo)."""
    pred = pred.copy()
    pred["lo80"] = np.nan; pred["hi80"] = np.nan; pred["factor_80"] = np.nan
    for k, a in enumerate(cortes):
        prev = pred[pred["corte"].isin(cortes[:k])] if k else pred[pred["corte"] == a]
        r = (np.abs(prev["delta_real"] - prev["delta_pred"]) / np.maximum(prev["delta_sd"], 1e-6)).to_numpy(float)
        q = float(np.quantile(r, nivel)) if len(r) else np.nan
        sel = pred["corte"] == a
        pred.loc[sel, "factor_80"] = q
        pred.loc[sel, "lo80"] = pred.loc[sel, "delta_pred"] - q * pred.loc[sel, "delta_sd"]
        pred.loc[sel, "hi80"] = pred.loc[sel, "delta_pred"] + q * pred.loc[sel, "delta_sd"]
    return pred


def metricas(e: pd.DataFrame, B: int, semilla: int) -> dict:
    from scipy.stats import spearmanr
    y = e["delta_real"].to_numpy(float)
    out = {"n": int(len(e))}
    mae = lambda d, col: float(np.mean(np.abs(d["delta_real"] - d[col])))
    for nombre, col in (("f4", "delta_pred"), ("aditivo_f1", "delta_aditivo"), ("oraculo_minutos", "delta_oraculo_minutos"), ("gbm_directo", "delta_gbm")):
        if col not in e or e[col].isna().all():
            continue
        d = e[e[col].notna()]
        out[f"mae_{nombre}"] = mae(d, col)
        out[f"spearman_{nombre}"] = float(spearmanr(d["delta_real"], d[col]).correlation) if len(d) > 3 else np.nan
    out["mae_persistencia"] = float(np.mean(np.abs(y)))
    out["mae_media_liga_cero"] = out["mae_persistencia"]
    # diferencias con IC95 (bootstrap de transiciones)
    for nombre, col in (("persistencia", None), ("aditivo_f1", "delta_aditivo"), ("gbm_directo", "delta_gbm")):
        if col is not None and (col not in e or e[col].isna().all()):
            continue
        d = e if col is None else e[e[col].notna()]
        f = (lambda x: float(np.mean(np.abs(x["delta_real"] - x["delta_pred"])) - np.mean(np.abs(x["delta_real"])))) if col is None else \
            (lambda x, c=col: float(np.mean(np.abs(x["delta_real"] - x["delta_pred"])) - np.mean(np.abs(x["delta_real"] - x[c]))))
        out[f"dif_mae_f4_menos_{nombre}"] = f(d); out[f"ic95_dif_{nombre}"] = _boot(d, f, B, semilla)
    if "lo80" in e and e["lo80"].notna().any():
        d = e[e["lo80"].notna()]
        out["cobertura_80"] = float(np.mean((d["delta_real"] >= d["lo80"]) & (d["delta_real"] <= d["hi80"])))
        out["cobertura_80_mc_crudo"] = float(np.mean((d["delta_real"] >= d["delta_p10"]) & (d["delta_real"] <= d["delta_p90"])))
        out["anchura_80_media"] = float(np.mean(d["hi80"] - d["lo80"]))
    # sesgo por tercil de minutos proyectados de las altas
    if "min_altas" in e and len(e) >= 30:
        terc = pd.qcut(e["min_altas"].rank(method="first"), 3, labels=["bajo", "medio", "alto"])
        out["sesgo_por_tercil_min_altas"] = {str(k): {"n": int((terc == k).sum()), "sesgo": float(np.mean((e["delta_pred"] - e["delta_real"])[terc == k])),
                                                      "min_altas_media": float(e["min_altas"][terc == k].mean())} for k in ["bajo", "medio", "alto"]}
    return out


def main(cfg: dict, progreso=print, solo_ligas=None, cortes=None) -> dict:
    from bbfit.registro import experimento
    t0 = time.time()
    out_dir = dir_salida(cfg) / "examen"; out_dir.mkdir(parents=True, exist_ok=True)
    tr_all = RP.tramos(cfg, None, progreso)
    trans = transiciones(cfg)
    cortes = [int(a) for a in (cortes or cfg["criterios"]["comunes"]["cortes"])]
    dec = [a for a in cortes if a in [int(x) for x in cfg["criterios"]["comunes"]["cortes_decision"]]]
    B, sem = int(cfg["criterios"]["comunes"]["bootstrap"]), int(cfg["criterios"]["comunes"]["semilla_bootstrap"])
    crit = cfg["criterios"]["f4"]
    partes = []
    with experimento(cfg["mlflow"], "F4_examen", params={"cortes": cortes, "simulaciones": cfg["f4"]["monte_carlo"]["simulaciones"]}):
        for a in cortes:
            cache = out_dir / f"predicciones_corte_{a}.pkl"
            if cache.exists() and not solo_ligas:
                partes.append(pickle.loads(cache.read_bytes())); continue
            e = examen_corte(cfg, a, tr_all, trans, progreso, solo_ligas)
            if not solo_ligas:
                cache.write_bytes(pickle.dumps(e))
            partes.append(e)
        pred = pd.concat(partes, ignore_index=True)
        pred["delta_gbm"] = gbm_directo(pred, cortes)
        pred = calibrar_intervalos(pred, cortes)
        res = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "cortes": cortes, "cortes_decision": dec,
               "transiciones": int(len(pred)), "por_corte": {}, "por_grupo": {}, "global_decision": None}
        for a in cortes:
            res["por_corte"][a] = metricas(pred[pred["corte"] == a], B, sem)
        d = pred[pred["corte"].isin(dec)]
        res["global_decision"] = metricas(d, B, sem)
        for g, x in d.groupby("grupo"):
            res["por_grupo"][g] = metricas(x, B, sem)
        for l, x in d.groupby("liga"):
            res.setdefault("por_liga", {})[l] = {"n": int(len(x)), "mae_f4": float(np.mean(np.abs(x["delta_real"] - x["delta_pred"]))),
                                                 "mae_persistencia": float(np.mean(np.abs(x["delta_real"])))}
        gd = res["global_decision"]
        lo, hi = crit["cobertura_80"]
        res["puerta_11_4"] = {
            "mejora_persistencia_ic95_excluye_0": bool(gd["ic95_dif_persistencia"][1] < 0),
            "no_empeora_aditivo": bool(gd.get("ic95_dif_aditivo_f1", [0, 0])[0] <= 0) if "ic95_dif_aditivo_f1" in gd else None,
            "no_detras_gbm_significativo": bool(gd.get("ic95_dif_gbm_directo", [0, 0])[0] <= 0) if "ic95_dif_gbm_directo" in gd else None,
            "cobertura_en_rango": bool(lo <= gd.get("cobertura_80", np.nan) <= hi) if "cobertura_80" in gd else None,
            "sospecha_fuga": bool(gd["mae_f4"] < 0.6 * gd["mae_persistencia"]),
        }
        res["puerta_11_4"]["pasa"] = bool(all(v for k, v in res["puerta_11_4"].items() if k not in ("sospecha_fuga",) and v is not None)) and not res["puerta_11_4"]["sospecha_fuga"]
        res["tiempo_s"] = round(time.time() - t0)
        suf = "_" + "-".join(solo_ligas) if solo_ligas else ""
        pred.round(4).to_csv(out_dir / f"predicciones_f4{suf}.csv.gz", index=False)
        (out_dir / f"resumen_examen_f4{suf}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    if progreso:
        progreso(f"  examen F4: {res['transiciones']} transiciones · MAE F4 {gd['mae_f4']:.2f} · persistencia {gd['mae_persistencia']:.2f} · "
                 f"aditivo {gd.get('mae_aditivo_f1', np.nan):.2f} · GBM {gd.get('mae_gbm_directo', np.nan):.2f} · cobertura {gd.get('cobertura_80', np.nan):.2f} · "
                 f"puerta {res['puerta_11_4']} · {res['tiempo_s']} s", flush=True)
    return res
