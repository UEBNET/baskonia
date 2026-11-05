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
    l = filtrar_contrato(cfg, l)
    return l[["liga", "grupo", "club", "temporada_ant", "temporada_nueva", "anio", "team_id_ant", "team_id_nuevo", "n_retornos",
              "n_salidas", "n_llegadas", "min_liberados", "min_absorbidos", "uso_liberado", "uso_absorbido", "net_ant", "net_nuevo",
              "delta_net"]].reset_index(drop=True)


def transiciones_extra(cfg: dict, trans: pd.DataFrame, min_minutos: float = 100.0, min_comunes: int = 3) -> pd.DataFrame:
    """Ligas con tramos pero ausentes del libro de roles (LBA y LNB: sus `team_id` cambian cada temporada): equipos enlazados
    t → t+1 por plantilla compartida (≥ min_comunes jugadores con ≥ min_minutos; sin ambigüedad: el segundo candidato < min_comunes),
    Net ajustado de la fase regular de `quintetos/<liga>/equipos.csv`. Mismas columnas que el libro."""
    from bbfit import datos as D
    r = pd.read_csv(C.RAIZ / cfg["insumos"]["roles"], usecols=["liga", "temporada", "team_id", "persona_id", "min_total", "usg_pct"],
                    dtype={"team_id": str}, low_memory=False)
    ligas = sorted(set(r["liga"]) - set(trans["liga"]) - {"ncaa"})
    filas = []
    for lg in ligas:
        x = r[(r["liga"] == lg) & (r["min_total"] >= min_minutos)]
        temps = sorted(x["temporada"].unique())
        nets = {}
        for t in temps:
            try:
                e = D.quintetos_fichero(lg, t, "equipos.csv")
            except Exception:
                continue
            if e is None or e.empty or "net_rtg_aj" not in e:
                continue
            e = e[e["fase"] == "regular"]
            nets.update({(t, str(k)): float(v) for k, v in zip(e["team_id"], e["net_rtg_aj"])})
        for t0, t1 in zip(temps[:-1], temps[1:]):
            if int(t1[:4]) != int(t0[:4]) + 1:          # sólo temporadas consecutivas
                continue
            A = x[x["temporada"] == t0].groupby("team_id"); B = x[x["temporada"] == t1].groupby("team_id")
            sa = {k: set(g["persona_id"]) for k, g in A}; sb = {k: set(g["persona_id"]) for k, g in B}
            ma = {k: g.set_index("persona_id")["min_total"] for k, g in A}; mb = {k: g.set_index("persona_id")["min_total"] for k, g in B}
            for tb, pb in sb.items():
                sc = sorted(((len(pa & pb), ta) for ta, pa in sa.items()), reverse=True)
                if not sc or sc[0][0] < min_comunes or (len(sc) > 1 and sc[1][0] >= min_comunes):
                    continue
                ta = sc[0][1]
                n0, n1 = nets.get((t0, ta)), nets.get((t1, tb))
                if n0 is None or n1 is None:
                    continue
                pa = sa[ta]; salen = pa - pb; llegan = pb - pa
                filas.append({"liga": lg, "grupo": GRUPOS_LIGA.get(lg, "otras"), "club": f"{lg}|{ta}", "temporada_ant": t0, "temporada_nueva": t1,
                              "anio": int(t0[:4]), "team_id_ant": ta, "team_id_nuevo": tb, "n_retornos": len(pa & pb), "n_salidas": len(salen),
                              "n_llegadas": len(llegan), "min_liberados": float(ma[ta][list(salen)].sum() / max(ma[ta].sum(), 1)),
                              "min_absorbidos": float(mb[tb][list(llegan)].sum() / max(mb[tb].sum(), 1)), "uso_liberado": np.nan, "uso_absorbido": np.nan,
                              "net_ant": n0, "net_nuevo": n1, "delta_net": n1 - n0})
    return pd.DataFrame(filas)


def filtrar_contrato(cfg: dict, trans: pd.DataFrame) -> pd.DataFrame:
    """Sólo transiciones cuya liga-temporada de partida t está incluida en el contrato de datos (D6): si t no tiene tramos de
    quinteto válidos (p. ej. NCAA 2024-25, CBA 2024-25, VTB 2021-22) ningún jugador tiene β y la capa 4 no tiene nada que
    decir; la temporada t+1 sólo necesita el Net realizado."""
    inv = pd.read_csv(C.dir_salida(cfg) / "contrato" / "inventario_tramos.csv", usecols=["liga", "temporada", "decision"])
    ok = set(zip(inv.loc[inv["decision"] != "excluida", "liga"], inv.loc[inv["decision"] != "excluida", "temporada"]))
    sel = [(l, t) in ok for l, t in zip(trans["liga"], trans["temporada_ant"])]
    return trans[sel].reset_index(drop=True)


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
        t2 = np.atleast_1d(np.asarray(aj["res"].get("tau2", np.nan), float)).ravel()[0]
        self.tau = float(np.sqrt(t2)) if np.isfinite(t2) and t2 > 0 else float(np.nanmedian(tb["beta_sd"]))
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
        if not p3.exists() and cfg["f4"].get("exigir_f3", True):
            raise FileNotFoundError(f"falta la red F3 del corte {a} ({p3.name}): ejecute `python -m bbequipo conjunto-redes-corte`")
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
    if bloques:
        w = V.ajustar_utilidad(bloques, cfg_sim)
    else:                                              # pesos iniciales: el peso de los minutos previos vale para club y fuera
        w = dict(cfg_sim["utilidad"]["inicial"])
        if "logit_min_previo" in w:
            w.setdefault("lmin_club", w["logit_min_previo"]); w.setdefault("lmin_fuera", w["logit_min_previo"])
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
            T1 = y["T"] - M1; T1_add = y["T_aditivo"] - M1_add
            T0 = x["T"] - m_t; T0_add = x["T_aditivo"] - m_t_add
            q = lambda v, k: float(np.quantile(v, k))
            filas.append({"corte": a, "liga": liga, "grupo": row.grupo, "club": row.club, "temporada_ant": row.temporada_ant,
                          "temporada_nueva": row.temporada_nueva, "net_ant": row.net_ant, "net_nuevo": row.net_nuevo, "delta_real": row.delta_net,
                          "T0": float(T0), "T0_aditivo": float(T0_add), "T1": float(T1.mean()), "T1_sd": float(T1.std()),
                          "T1_p05": q(T1, .05), "T1_p10": q(T1, .10), "T1_p25": q(T1, .25), "T1_p75": q(T1, .75), "T1_p90": q(T1, .90), "T1_p95": q(T1, .95),
                          "T1_aditivo": float(T1_add.mean()), "T1_phi": float(y["T_phi"].mean()), "T1_h": float(y["T_h"].mean()),
                          "T1_oraculo": float(y["T_oraculo"] - m_or) if np.isfinite(y["T_oraculo"]) else np.nan,
                          "delta_pred_crudo": float(T1.mean() - T0), "delta_oraculo_crudo": float((y["T_oraculo"] - m_or) - T0) if np.isfinite(y["T_oraculo"]) else np.nan,
                          "min_altas": y["min_altas"], "n_plantilla": y["n_plantilla"], "n_sin_beta": y["n_sin_beta"], "n_nuevo": y["n_nuevo"],
                          "n_salidas": row.n_salidas, "n_llegadas": row.n_llegadas, "min_liberados": row.min_liberados, "min_absorbidos": row.min_absorbidos,
                          "uso_liberado": row.uso_liberado, "uso_absorbido": row.uso_absorbido})
        if progreso:
            e = pd.DataFrame([f for f in filas if f["liga"] == liga])
            progreso(f"    corte {a} {liga}: {len(e)} equipos · MAE Δ̂ crudo {np.mean(np.abs(e['delta_real'] - e['delta_pred_crudo'])):.2f} · "
                     f"persistencia {np.mean(np.abs(e['delta_real'])):.2f} · corr(T1', Net t+1) {np.corrcoef(e['T1'], e['net_nuevo'])[0, 1] if len(e) > 2 else np.nan:+.2f} "
                     f"(persistencia {np.corrcoef(e['net_ant'], e['net_nuevo'])[0, 1] if len(e) > 2 else np.nan:+.2f}) · sd T1' {e['T1'].std():.1f} frente a {e['net_nuevo'].std():.1f} · {time.time() - t0:.0f} s", flush=True)
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
    cols = ["net_ant", "n_salidas", "n_llegadas", "min_liberados", "min_absorbidos", "uso_liberado", "uso_absorbido", "T1_aditivo", "T0_aditivo", "min_altas"]
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


def calibrar_prediccion(pred: pd.DataFrame, cortes: list[int]) -> pd.DataFrame:
    """Capa de calibración [DECISIÓN en el corte de calibración 2021]: la fuerza proyectada de t+1 (T1', centrada en su liga)
    correlaciona con el Net realizado de t+1 más que la persistencia pero está sobredispersa (β de t aplicados a otra
    plantilla y otra temporada). Predicción: Net̂_{t+1} = c·T1' + d·Net_t (sin intercepto; c, d por mínimos cuadrados con los
    cortes ANTERIORES; el primer corte usa los suyos, sólo informativo) y Δ̂ = Net̂_{t+1} − Net_t. La persistencia es el caso
    c = 0, d = 1. Por grupo de liga cuando el grupo tiene ≥ 40 transiciones previas (los grupos difieren: NBA c ≈ 0,7, Europa
    media c ≈ 0,2 y d ≈ 0,7 en el corte de calibración); si no, conjunta. Se aplica igual a la línea base aditiva (con
    T1'_aditivo) y al oráculo de minutos. `delta_pred_crudo` = T1' − T0'."""
    pred = pred.copy()
    for col in ("c_cal", "d_cal", "c_cal_aditivo", "d_cal_aditivo"):
        pred[col] = np.nan
    def ajustar(prev, colT):
        A = np.c_[prev[colT].to_numpy(float), prev["net_ant"].to_numpy(float)]; y = prev["net_nuevo"].to_numpy(float)
        ok = np.isfinite(A).all(1) & np.isfinite(y)
        if ok.sum() < 20:
            return 1.0, 0.0
        cd = np.linalg.lstsq(A[ok], y[ok], rcond=None)[0]
        return float(np.clip(cd[0], 0.0, 1.5)), float(np.clip(cd[1], -0.5, 1.5))
    MIN_GRUPO = 40                                     # transiciones previas del grupo de liga para calibrar por grupo; si no, conjunta
    for k_, a in enumerate(cortes):
        prev = pred[pred["corte"].isin(cortes[:k_])] if k_ else pred[pred["corte"] == a]
        c0, d0 = ajustar(prev, "T1"); ca0, da0 = ajustar(prev, "T1_aditivo")
        for grp in pred.loc[pred["corte"] == a, "grupo"].unique():
            pg = prev[prev["grupo"] == grp]
            if len(pg) >= MIN_GRUPO:
                c, d = ajustar(pg, "T1"); ca, da = ajustar(pg, "T1_aditivo")
            else:
                c, d, ca, da = c0, d0, ca0, da0
            sel = (pred["corte"] == a) & (pred["grupo"] == grp)
            n0 = pred.loc[sel, "net_ant"]
            pred.loc[sel, ["c_cal", "d_cal", "c_cal_aditivo", "d_cal_aditivo"]] = [c, d, ca, da]
            pred.loc[sel, "delta_pred"] = c * pred.loc[sel, "T1"] + (d - 1.0) * n0
            pred.loc[sel, "delta_sd"] = c * pred.loc[sel, "T1_sd"]
            for q in ("p05", "p10", "p25", "p75", "p90", "p95"):
                pred.loc[sel, f"delta_{q}"] = c * pred.loc[sel, f"T1_{q}"] + (d - 1.0) * n0
            pred.loc[sel, "delta_aditivo"] = ca * pred.loc[sel, "T1_aditivo"] + (da - 1.0) * n0
            pred.loc[sel, "delta_oraculo_minutos"] = c * pred.loc[sel, "T1_oraculo"] + (d - 1.0) * n0
    return pred


def corregir_sesgo_minutos(pred: pd.DataFrame, cortes: list[int], umbral: float) -> pd.DataFrame:
    """Capa de calibración del sesgo por minutos de las altas (encargo §9.2, prerregistrada): si en los cortes anteriores el
    sesgo medio de Δ̂ en algún tercil de minutos proyectados de las altas supera ±umbral, se resta ese sesgo por tercil
    (terciles y sesgos de los cortes ANTERIORES; el primer corte, sin corrección)."""
    pred = pred.copy(); pred["sesgo_tercil"] = 0.0; pred["tercil_altas"] = None
    for k_, a in enumerate(cortes):
        if k_ == 0:
            continue
        prev = pred[pred["corte"].isin(cortes[:k_])]
        q1, q2 = prev["min_altas"].quantile([1 / 3, 2 / 3])
        terc = lambda x: np.where(x <= q1, "bajo", np.where(x <= q2, "medio", "alto"))
        tp = terc(prev["min_altas"].to_numpy(float))
        sesgo = {t: float(np.mean((prev["delta_pred"] - prev["delta_real"])[tp == t])) for t in ("bajo", "medio", "alto")}
        if max(abs(v) for v in sesgo.values()) <= umbral:
            continue
        sel = pred["corte"] == a
        tt = terc(pred.loc[sel, "min_altas"].to_numpy(float))
        corr = np.array([sesgo[t] for t in tt])
        pred.loc[sel, "tercil_altas"] = tt; pred.loc[sel, "sesgo_tercil"] = corr
        for c in ("delta_pred", "delta_p05", "delta_p10", "delta_p25", "delta_p75", "delta_p90", "delta_p95"):
            pred.loc[sel, c] = pred.loc[sel, c] - corr
    return pred


def calibrar_intervalos(pred: pd.DataFrame, cortes: list[int], nivel: float = 0.8, min_grupo: int = 40) -> pd.DataFrame:
    """Intervalo del 80 % conformal con escala «Monte Carlo + ruido irreducible»: semianchura = q · √(sd_MC² + s0²), donde s0²
    es la varianza del residuo de los cortes ANTERIORES no explicada por la sd del Monte Carlo (media(res²) − media(sd_MC²),
    acotada en 0) y q el cuantil `nivel` de |res|/√(sd_MC² + s0²) en esos cortes. Ambos por grupo de liga si el grupo tiene
    ≥ min_grupo transiciones previas; si no, conjuntos. Motivo [DECISIÓN en el corte de calibración]: la sd del Monte Carlo
    (β y minutos) es pequeña frente al ruido de temporada de un equipo y, sola, infracubre donde ese ruido es grande. El
    primer corte usa sus propios residuos (sólo informativo)."""
    pred = pred.copy()
    pred["lo80"] = np.nan; pred["hi80"] = np.nan; pred["factor_80"] = np.nan; pred["s0_80"] = np.nan; pred["factor_80_fuente"] = None
    pred["frac_sin_beta"] = pred["n_sin_beta"] / pred["n_plantilla"].clip(lower=1)
    def escala(d):
        res = (d["delta_real"] - d["delta_pred"]).to_numpy(float); sd = d["delta_sd"].to_numpy(float)
        s0 = float(np.sqrt(max(np.mean(res ** 2) - np.mean(sd ** 2), 0.0)))
        q = float(np.quantile(np.abs(res) / np.sqrt(sd ** 2 + s0 ** 2), nivel))
        return s0, q
    for k, a in enumerate(cortes):
        prev = pred[pred["corte"].isin(cortes[:k])] if k else pred[pred["corte"] == a]
        s0_pool, q_pool = escala(prev)
        sel_c = pred["corte"] == a
        for grp in pred.loc[sel_c, "grupo"].unique():
            pg = prev[prev["grupo"] == grp]
            sel = sel_c & (pred["grupo"] == grp)
            if len(pg) >= min_grupo:
                s0, q = escala(pg); fuente = "grupo"
            else:
                s0, q = s0_pool, q_pool; fuente = "conjunto"
            semi = q * np.sqrt(pred.loc[sel, "delta_sd"] ** 2 + s0 ** 2)
            pred.loc[sel, "factor_80"] = q; pred.loc[sel, "s0_80"] = s0; pred.loc[sel, "factor_80_fuente"] = fuente
            pred.loc[sel, "lo80"] = pred.loc[sel, "delta_pred"] - semi
            pred.loc[sel, "hi80"] = pred.loc[sel, "delta_pred"] + semi
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
    if "delta_pred_crudo" in e:
        out["mae_f4_sin_calibrar"] = mae(e, "delta_pred_crudo"); out["c_cal_medio"] = float(e["c_cal"].mean()); out["d_cal_medio"] = float(e["d_cal"].mean())
        out["corr_T1_net_t1"] = float(np.corrcoef(e["T1"], e["net_nuevo"])[0, 1]) if len(e) > 3 else np.nan
        out["corr_persistencia_net_t1"] = float(np.corrcoef(e["net_ant"], e["net_nuevo"])[0, 1]) if len(e) > 3 else np.nan
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
    if "sesgo_tercil" in e:
        out["correccion_sesgo_media_abs"] = float(np.mean(np.abs(e["sesgo_tercil"])))
    if "factor_80_fuente" in e:
        out["factor_80_fuente"] = {str(k): int(v) for k, v in e["factor_80_fuente"].value_counts().items()}
    # sesgo por tercil de minutos proyectados de las altas (tras la corrección)
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
    extra = filtrar_contrato(cfg, transiciones_extra(cfg, trans))
    if len(extra):
        trans = pd.concat([trans, extra], ignore_index=True)
        if progreso:
            progreso(f"  transiciones: {len(trans)} ({len(extra)} enlazadas por plantilla en {sorted(extra['liga'].unique())})", flush=True)
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
        pred = pred.merge(trans[["liga", "temporada_ant", "club"]].drop_duplicates(), on=["liga", "temporada_ant", "club"], how="inner")
        pred = calibrar_prediccion(pred, cortes)
        pred = corregir_sesgo_minutos(pred, cortes, float(cfg["f4"]["sesgo_minutos"]["umbral_calibracion_net"]))
        pred["delta_gbm"] = gbm_directo(pred, cortes)
        pred = calibrar_intervalos(pred, cortes)
        res = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "cortes": cortes, "cortes_decision": dec,
               "transiciones": int(len(pred)), "por_corte": {}, "por_grupo": {}, "global_decision": None}
        for a in cortes:
            res["por_corte"][a] = metricas(pred[pred["corte"] == a], B, sem)
        d = pred[pred["corte"].isin(dec)]
        if d.empty:                                   # prueba sin cortes de decisión: resumen con lo que hay (informativo)
            d = pred; res["aviso"] = "sin cortes de decisión: resumen informativo con los cortes ejecutados"
        res["global_decision"] = metricas(d, B, sem)
        for g, x in d.groupby("grupo"):
            res["por_grupo"][g] = metricas(x, B, sem)
        for l, x in d.groupby("liga"):
            res.setdefault("por_liga", {})[l] = {"n": int(len(x)), "mae_f4": float(np.mean(np.abs(x["delta_real"] - x["delta_pred"]))),
                                                 "mae_persistencia": float(np.mean(np.abs(x["delta_real"])))}
        gd = res["global_decision"]
        lo, hi = crit["cobertura_80"]
        gd.setdefault("mae_f4", np.nan); gd.setdefault("ic95_dif_persistencia", [np.nan, np.nan])
        res["puerta_11_4"] = {
            "mejora_persistencia_ic95_excluye_0": bool(gd["ic95_dif_persistencia"][1] < 0),
            "no_empeora_aditivo": bool(gd.get("ic95_dif_aditivo_f1", [0, 0])[0] <= 0) if "ic95_dif_aditivo_f1" in gd else None,
            "no_detras_gbm_significativo": bool(gd.get("ic95_dif_gbm_directo", [0, 0])[0] <= 0) if "ic95_dif_gbm_directo" in gd else None,
            "cobertura_en_rango": bool(lo <= gd.get("cobertura_80", np.nan) <= hi) if "cobertura_80" in gd else None,
            "sospecha_fuga": bool(gd["mae_f4"] < 0.6 * gd["mae_persistencia"]) if np.isfinite(gd["mae_f4"]) else None,
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


# =============================================================================================== producto
def calibracion_producto(pred: pd.DataFrame, cfg: dict, nivel: float = 0.8, min_grupo: int = 40) -> dict:
    """Coeficientes de la capa 4 para producción, con TODOS los cortes del examen: (c, d) de la predicción y (s0, q) de los
    intervalos por grupo de liga (≥ min_grupo transiciones) y conjuntos; sesgo por tercil de minutos de las altas."""
    def cd(d):
        A = np.c_[d["T1"].to_numpy(float), d["net_ant"].to_numpy(float)]; y = d["net_nuevo"].to_numpy(float)
        ok = np.isfinite(A).all(1) & np.isfinite(y)
        if ok.sum() < 20:
            return None
        x = np.linalg.lstsq(A[ok], y[ok], rcond=None)[0]
        return {"c": float(np.clip(x[0], 0, 1.5)), "d": float(np.clip(x[1], -0.5, 1.5)), "n": int(ok.sum())}
    def esc(d):
        res = (d["delta_real"] - d["delta_pred"]).to_numpy(float); sd = d["delta_sd"].to_numpy(float)
        s0 = float(np.sqrt(max(np.mean(res ** 2) - np.mean(sd ** 2), 0.0)))
        return {"s0": s0, "q": float(np.quantile(np.abs(res) / np.sqrt(sd ** 2 + s0 ** 2), nivel)), "n": int(len(d))}
    out = {"conjunto": {"prediccion": cd(pred), "intervalo": esc(pred)}, "por_grupo": {}}
    for g, d in pred.groupby("grupo"):
        if len(d) >= min_grupo:
            out["por_grupo"][g] = {"prediccion": cd(d), "intervalo": esc(d)}
    q1, q2 = pred["min_altas"].quantile([1 / 3, 2 / 3])
    terc = np.where(pred["min_altas"] <= q1, "bajo", np.where(pred["min_altas"] <= q2, "medio", "alto"))
    out["sesgo_minutos_altas"] = {"cortes_terciles": [float(q1), float(q2)],
                                  "sesgo": {t: float(np.mean((pred["delta_pred"] - pred["delta_real"])[terc == t])) for t in ("bajo", "medio", "alto")},
                                  "umbral": float(cfg["f4"]["sesgo_minutos"]["umbral_calibracion_net"])}
    return out


class Equipo:
    """Capa 4 en producción: Net̂ de una plantilla y Δ̂ de un cambio de plantilla (altas/bajas), con intervalos calibrados.
    Insumos de producto: β de F1 (todas las temporadas), M_r de F2, redes F3 aditivas, motor de minutos v3.3 (pesos finales)
    y la calibración de `calibracion.json`."""

    def __init__(self, cfg: dict, temporada: str, progreso=print):
        from .examen_f1 import perfiles_completo
        self.cfg, self.temp = cfg, temporada
        tr = RP.tramos(cfg, None, progreso=None)
        temps = sorted(tr["temporada"].unique())
        T = RP.tabla_prior(perfiles_completo(cfg, [t for t in temps if (C.dir_salida(cfg) / "perfiles" / f"{t}.csv.gz").exists()]), cfg)
        tipo = cfg["f1"]["prior"].get("elegido") or json.loads((RP.dir_salida(cfg) / "examen" / "resumen_examen.json").read_text())["decisiones"]["prior"]["elegido"]
        pr = cfg["f1"].get("producto") or {}
        cfg_p = C.con(cfg, **{"f1.bayes_empirico.tau_rejilla": pr.get("tau_rejilla", cfg["f1"]["bayes_empirico"]["tau_rejilla"]),
                              "f1.prior.ridge_alpha_rejilla": pr.get("ridge_alpha_rejilla", cfg["f1"]["prior"]["ridge_alpha_rejilla"])}) if pr else cfg
        res = pickle.loads((C.RAIZ / "experimentos" / "v4_0" / f"producto_f1_net_{tipo}_{RP.huella_ajuste(cfg_p)}.pkl").read_bytes())
        D = RP.construir_diseno(tr, "net")
        tb = RP.tabla_beta(res, D).merge(RP.ligas_jugador(tr), on="clave", how="left")
        tb["anio"] = tb["temporada"].str[:4].astype(int)
        ult = tb.sort_values("anio").drop_duplicates("persona_id", keep="last").set_index("persona_id")
        self.beta, self.beta_sd = ult["beta"].to_dict(), ult["beta_sd"].to_dict()
        prior = res["priors"][0]
        self.prior = dict(zip(T["clave"], prior.predecir(T))) if prior is not None else {}
        t2 = np.atleast_1d(np.asarray(res.get("tau2", np.nan), float)).ravel()[0]
        self.tau = float(np.sqrt(t2)) if np.isfinite(t2) and t2 > 0 else float(np.nanmedian(tb["beta_sd"]))
        prim = tb.groupby("persona_id")["anio"].transform("min")
        nuevos = tb[(tb["anio"] == prim) & (tb["anio"] > 2020)].assign(w=lambda d: np.maximum(d["poss"], 1.0))
        self.nivel_nuevo = nuevos.groupby("liga_principal").apply(lambda g: np.average(g["beta"], weights=g["w"])).to_dict()
        self.nivel_nuevo_global = float(np.mean(list(self.nivel_nuevo.values())))
        self.R = SG.Rasgos(T, cfg)
        self.Mr = np.load(SG.dir_salida(cfg) / "M_rango.npy")
        est = pickle.loads((CJ.dir_salida(cfg) / "redes.pkl").read_bytes())
        self.red = CJ.ConjuntoNet(self.R.Z, cfg).cargar(est["estado"], int(cfg["semilla"]))
        self._h = {}
        S, V, SI, RE = _sim()
        self.S, self.V, self.SI, self.RE = S, V, SI, RE
        self.c = S.cargar_corte(temporada, "V32")             # producción: fuente V32 y pesos finales de la utilidad
        self.roles = SI._leer_roles_temporada()
        self.cfg_re = RE._cfg()
        self.cal = json.loads((dir_salida(cfg) / "calibracion.json").read_text(encoding="utf-8"))
        if progreso:
            progreso(f"  capa 4 ({temporada}): β de {len(self.beta)} personas · perfiles {len(T)} · nivel nuevo {self.nivel_nuevo_global:+.2f}", flush=True)

    # mismas reglas que Insumos
    valor = Insumos.valor
    z = Insumos.z
    h = Insumos.h

    def _perfil_clave(self, pid):            # perfil más reciente ≤ temporada
        for t in sorted({k.rsplit("|", 1)[1] for k in self.R.idx if k.startswith(pid + "|")}, reverse=True):
            if t <= self.temp:
                return f"{pid}|{t}"
        return f"{pid}|{self.temp}"

    def plantilla_minutos(self, liga: str, team_id: str, miembros: list[tuple[str, float]], n_sim: int, semilla: int, entrenador=None):
        S, RE = self.S, self.RE
        P = S.plantilla(self.c, f"{liga}|{team_id}", liga, miembros, team_d=team_id)
        if P.empty or len(P) < 7:
            raise ValueError("plantilla con menos de 7 jugadores")
        P["encaje"] = pd.to_numeric(P.get("encaje_pos", 0.0), errors="coerce").fillna(0.0)
        P["nivel"] = S.utilidad(self.c, P) * float(self.c.calib.get("escala_utilidad", 1.0))
        ent = entrenador or S.entrenador_equipo(self.c, liga, team_id)
        rot, rot_sd, curva = S.tendencia(self.c, ent, liga)
        gm = S.minutos_partido(liga)
        pl = pd.DataFrame({"player_id": P["persona_id"].to_numpy(), "nivel": P["nivel"].to_numpy(float), "pos3": P["pos3"].to_numpy(object)})
        _, M = RE.asignar_minutos(pl, total_min=5 * gm, minutos_partido=gm, rotacion_media=rot, rotacion_sd=rot_sd, curva=curva, n_sim=n_sim,
                                  semilla=semilla, cfg=self.cfg_re, devolver_simulaciones=True, presencia=P["presencia"].to_numpy(float))
        return P.reset_index(drop=True), M / gm

    def fuerza(self, liga: str, team_id: str, miembros: list[tuple[str, float]], n_sim: int | None = None, semilla: int = 0) -> dict:
        """T(R) por simulación (pts/100 en la escala común de β) y detalle por jugador."""
        n_sim = n_sim or int(self.cfg["f4"]["monte_carlo"]["simulaciones"])
        P, Pm = self.plantilla_minutos(liga, team_id, miembros, n_sim, semilla)
        rng = np.random.default_rng(semilla)
        pids = list(P["persona_id"])
        v = valor_equipo(self, liga, pids, Pm, rng)
        det = pd.DataFrame({"persona_id": pids, "beta": v["beta"], "sd": v["sd"], "fuente": v["fuente"], "cuota_media": Pm.mean(0),
                            "h": self.h(pids), "minutos_media": Pm.mean(0) * self.S.minutos_partido(liga)})
        return {"T": v["T"], "T_aditivo": v["T_aditivo"], "T_phi": v["T_phi"], "T_h": v["T_h"], "detalle": det}

    def delta(self, liga: str, team_id: str, plantilla: list[tuple[str, float]], altas: list[str], bajas: list[str],
              net_actual: float, n_sim: int | None = None, semilla: int = 0) -> dict:
        """Δ̂Net de pasar de `plantilla` a plantilla ∪ altas ∖ bajas, con la calibración del grupo de liga y el intervalo del 80 %."""
        grp = GRUPOS_LIGA.get(liga, "otras")
        cal = self.cal["por_grupo"].get(grp, self.cal["conjunto"])
        c, d = cal["prediccion"]["c"], cal["prediccion"]["d"]; s0, q = cal["intervalo"]["s0"], cal["intervalo"]["q"]
        R0 = [(p, x) for p, x in plantilla if p not in set(bajas)]
        R1 = R0 + [(p, 1.0) for p in altas if p not in {x for x, _ in R0}]
        f0 = self.fuerza(liga, team_id, plantilla, n_sim, semilla); f1 = self.fuerza(liga, team_id, R1, n_sim, semilla + 1)
        # T' centrado: la media de la liga se aproxima con la fuerza actual del propio equipo frente a su Net actual
        # (Net̂_act = T0' ⇒ media de liga ≈ T0 − Net_act / c'); Δ̂ = c·(T1' − T0') + (d − 1)·Net_act con T1' − T0' = T1 − T0
        dT = f1["T"] - f0["T"].mean()
        delta = c * dT + (d - 1.0) * net_actual
        sd = float(c * dT.std()); semi = q * np.sqrt(sd ** 2 + s0 ** 2)
        m = float(delta.mean())
        return {"delta_net": m, "lo80": m - semi, "hi80": m + semi, "sd_mc": sd, "s0": s0, "q": q, "c": c, "d": d,
                "delta_crudo": float(dT.mean()), "descomposicion": {"aditivo_beta": float(c * (f1["T_aditivo"] - f0["T_aditivo"].mean()).mean()),
                                                                    "sinergia_phi": float(c * (f1["T_phi"] - f0["T_phi"].mean()).mean()),
                                                                    "correccion_jugador_h": float(c * (f1["T_h"] - f0["T_h"].mean()).mean()),
                                                                    "regresion_a_la_media": float((d - 1.0) * net_actual)},
                "plantilla_nueva": f1["detalle"], "plantilla_actual": f0["detalle"]}


def exportar(cfg: dict, progreso=print) -> dict:
    """Producto de la capa 4: calibración con todos los cortes del examen (`calibracion.json`), Net̂ proyectado de todos los
    equipos de la última temporada con plantilla (`equipos_<t>.csv.gz`) y resumen."""
    from bbfit.registro import experimento
    t0 = time.time()
    out = dir_salida(cfg)
    pred = pd.read_csv(out / "examen" / "predicciones_f4.csv.gz")
    cal = calibracion_producto(pred, cfg)
    cal["version"] = cfg["version"]; cal["generado"] = time.strftime("%Y-%m-%dT%H:%M:%S"); cal["transiciones"] = int(len(pred))
    (out / "calibracion.json").write_text(json.dumps(cal, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    roles = pd.read_csv(C.RAIZ / cfg["insumos"]["roles"], usecols=["liga", "temporada", "team_id", "persona_id", "min_total"], dtype={"team_id": str}, low_memory=False)
    temp = sorted(roles["temporada"].unique())[-1]
    eq = Equipo(cfg, temp, progreso)
    n_sim = int(cfg["f4"]["monte_carlo"]["simulaciones"])
    filas = []
    with experimento(cfg["mlflow"], "F4_producto", params={"temporada": temp, "simulaciones": n_sim}):
        r1 = eq.roles[eq.roles["temporada"] == temp]
        for (liga, team), g in r1.groupby(["liga", "team_id"]):
            miembros = [(p, float(x)) for p, x in zip(g["persona_id"], g["presencia"])]
            if len(miembros) < 7:
                continue
            try:
                f = eq.fuerza(liga, str(team), miembros, n_sim=min(n_sim, 300), semilla=hash((liga, team)) % 10000)
            except Exception as e:  # noqa: BLE001
                if progreso:
                    progreso(f"    {liga} {team}: {e}", flush=True)
                continue
            filas.append({"liga": liga, "temporada": temp, "team_id": str(team), "T": float(f["T"].mean()), "T_sd": float(f["T"].std()),
                          "T_aditivo": float(f["T_aditivo"].mean()), "T_phi": float(f["T_phi"].mean()), "T_h": float(f["T_h"].mean()),
                          "n_plantilla": int(len(f["detalle"])), "n_sin_beta": int((f["detalle"]["fuente"] != "beta").sum())})
        e = pd.DataFrame(filas)
        e["T_centrada"] = e["T"] - e.groupby("liga")["T"].transform("mean")
        e["grupo"] = e["liga"].map(GRUPOS_LIGA).fillna("otras")
        e["c_cal"] = [cal["por_grupo"].get(g, cal["conjunto"])["prediccion"]["c"] for g in e["grupo"]]
        e["net_proyectado_relativo"] = e["c_cal"] * e["T_centrada"]       # parte de Net̂ que viene de la plantilla (sin el Net previo)
        e.round(3).to_csv(out / f"equipos_{temp}.csv.gz", index=False)
        doc = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "temporada": temp, "equipos": int(len(e)),
               "calibracion": "calibracion.json", "tiempo_s": round(time.time() - t0)}
        (out / "F4_equipo.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    if progreso:
        progreso(f"  F4 producto: {len(e)} equipos de {temp} · {doc['tiempo_s']} s", flush=True)
    return doc
