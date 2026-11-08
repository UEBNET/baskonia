"""F2 · Impacto en pista (encargo v4.1 §3.3, §4 F2, criterios §6.2; prerregistro en configs/ecosistema_v41.yaml → f2,
escrito el 08-11-2026 antes de calcular).

    v_j(R) = β_j + h(z_j) + Σ_k π_jk(R)·φ_jk  [+ γᵀ c_j(R)]  [+ δ·Σ_k π_jk·g(f_jk)]
    IMPACTO EN PISTA = g_iso( 100 · E_pred[ F_grupo(v_j) ] )

  · β_j ~ N(β̂_j, sd_j): valor del jugador con información ≤ t (F1 v4.0 por corte, `rapm_multiliga/examen/beta_corte_<t>`).
  · h(z_j): corrección no lineal por jugador (red aditiva de la F3 v4.0 del corte).
  · φ_jk = z_jᵀ M_r z_k: sinergia de pareja por perfiles (F2-A v4.0 del corte, rango del examen).
  · π_jk = P_jk / p_j: fracción de las posesiones de j con k en pista, con P_jk ≈ p_j p_k · 10 / Σ p_i p_l por simulación
    (la aproximación de la capa 4) y las cuotas p del motor de minutos v3.3 con pesos ≤ t sobre la plantilla REAL de t+1.
  · F_grupo: distribución de v̂ de los jugadores de las plantillas del mismo grupo de liga y corte (prerregistro `f2.escala`).
  · g_iso: calibración isotónica con los cortes anteriores frente al percentil del on/off realizado (P4: net_rtg_aj_onoff,
    ≥ 300 min), con su rango del 80 % por deciles; exactamente la maquinaria del IMPACTO v4.0 (V40_F5 §3.1).

Examen principal: las MISMAS filas de fichajes que im_examen.csv.gz (comparación pareada con el IMPACTO v4.0), bootstrap
de equipos-temporada. Banco de contextualidad: jugadores que siguen en el club de t a t+1. Candidatos (contexto c_j y
familiaridad) con sus reglas de entrada prerregistradas.

Salidas: data/modelos/v4_1/impacto_pista/; cachés por corte en experimentos/v4_1/impacto_pista/.
"""
from __future__ import annotations

import json
import math
import os
import pickle
import time

import numpy as np
import pandas as pd

from . import config as CE

Z80 = 1.2815515655446004


# =============================================================================================== insumos de un corte
class InsumosCorte:
    """Lo que el Impacto en pista necesita del corte t (todo ≤ t), sin reajustar el F1: β por corte versionados, rasgos z
    de los perfiles del corte, M_r del corte, red F3 aditiva del corte y el motor de minutos v3.3 con pesos ≤ t."""

    def __init__(self, cfg: dict, a: int, progreso=print):
        from .. import equipo as EQ, rapm as RP, sinergia as SG, conjunto as CJ
        from ..examen_f1 import perfiles_corte
        cfg40 = CE.cargar_v40(cfg)
        self.cfg41, self.cfg, self.cfg40, self.a = cfg, cfg40, cfg40, a     # cfg = v4.0 (lo que esperan pesos_pl e Insumos.h)
        self.temp = f"{a}-{str(a + 1)[-2:]}"
        self.temp1 = f"{a + 1}-{str(a + 2)[-2:]}"
        dv = CE.RAIZ / cfg40["salida"]
        tb = pd.read_csv(dv / "rapm_multiliga" / "examen" / f"beta_corte_{a}.csv.gz")
        tb["anio"] = tb["temporada"].str[:4].astype(int)
        ult = tb.sort_values("anio").drop_duplicates("persona_id", keep="last").set_index("persona_id")
        self.beta, self.beta_sd = ult["beta"].to_dict(), ult["beta_sd"].to_dict()
        self.tau = float(np.nanmedian(tb["beta_sd"]))
        prim = tb.groupby("persona_id")["anio"].transform("min")
        nuevos = tb[(tb["anio"] == prim) & (tb["anio"] > 2020)].assign(w=lambda d: np.maximum(d["poss"], 1.0))
        self.nivel_nuevo = nuevos.groupby("liga_principal").apply(lambda g: np.average(g["beta"], weights=g["w"])).to_dict()
        self.nivel_nuevo_global = float(np.mean(list(self.nivel_nuevo.values()))) if self.nivel_nuevo else 0.0
        T = RP.tabla_prior(perfiles_corte(cfg40, a), cfg40)
        self.R = SG.Rasgos(T, cfg40)
        ex2 = json.loads((SG.dir_salida(cfg40) / "examen" / "resumen_examen_f2a.json").read_text(encoding="utf-8"))
        rango = ex2["decisiones"]["rango"]
        self.Mr, _ = SG.truncar(np.load(SG.dir_salida(cfg40) / "examen" / f"M_corte_{a}.npy"),
                                None if rango == "completa" else int(rango))
        w, V_ = np.linalg.eigh(self.Mr)
        self.P4 = V_[:, np.argsort(-np.abs(w))[:4]]                     # 4 componentes de la sinergia (rasgos u = z·P4)
        suf = "aditiva" if cfg40["f3"].get("rho_lineal", False) else "completa"
        p3 = CJ.dir_salida(cfg40) / "examen" / f"red_corte_{a}_{suf}.pkl"
        self.red = CJ.ConjuntoNet(self.R.Z, cfg40).cargar(pickle.loads(p3.read_bytes()), int(cfg40["semilla"])) if p3.exists() else None
        self._h = {}
        os.environ.setdefault("CERNO_SIMULADOR", cfg40["insumos"].get("simulador_env_corte", "v32"))
        S, V, SI, RE = EQ._sim()
        self.S, self.V, self.SI, self.RE = S, V, SI, RE
        self.c = S.cargar_corte(self.temp, cfg40["insumos"].get("fuente_corte", "V32_corte"), pesos=False)
        self.roles = SI._leer_roles_temporada()
        pesos = EQ.pesos_pl(self, progreso)
        self.c.w_util = pesos["utilidad"]; self.c.calib = pesos.get("calibracion", {})
        self.cfg_re = RE._cfg()
        self.EQ = EQ

    # misma lógica que bbequipo.equipo.Insumos (valor sin prior: los β ≤ t versionados; sin β → nivel de jugador nuevo)
    def valor(self, pid: str, liga: str) -> tuple[float, float, str]:
        if pid in self.beta and np.isfinite(self.beta[pid]):
            return float(self.beta[pid]), float(self.beta_sd.get(pid, self.tau)), "beta"
        return float(self.nivel_nuevo.get(liga, self.nivel_nuevo_global)), self.tau * 1.5, "nuevo"

    def z(self, pids):
        return self.R.de([f"{p}|{self.temp}" for p in pids])

    def h(self, pids):
        from .. import equipo as EQ
        return EQ.Insumos.h(self, pids)

    def minutos(self, liga: str, team1: str, club_t: str | None, miembros, n_sim: int, semilla: int):
        """Cuotas del motor v3.3 (≤ t) para una lista de miembros [(persona, presencia)] del equipo de t+1."""
        S, RE = self.S, self.RE
        club_d = club_t or f"{liga}|{team1}"
        P = S.plantilla(self.c, club_d, liga, miembros)
        if P.empty or len(P) < 7:
            return None
        P["encaje"] = pd.to_numeric(P.get("encaje_pos", 0.0), errors="coerce").fillna(0.0)
        P["nivel"] = S.utilidad(self.c, P) * float(self.c.calib.get("escala_utilidad", 1.0))
        r1 = self.roles[self.roles["temporada"] == self.temp1]
        ent = r1[(r1["liga"] == liga) & (r1["team_id"].astype(str) == str(team1))]["entrenador_id"].dropna()
        entrenador = ent.mode().iloc[0] if len(ent) else S.entrenador_equipo(self.c, liga, team1)
        rot, rot_sd, curva = S.tendencia(self.c, entrenador, liga)
        gm = S.minutos_partido(liga)
        pl = pd.DataFrame({"player_id": P["persona_id"].to_numpy(), "nivel": P["nivel"].to_numpy(float), "pos3": P["pos3"].to_numpy(object)})
        _, M = RE.asignar_minutos(pl, total_min=5 * gm, minutos_partido=gm, rotacion_media=rot, rotacion_sd=rot_sd, curva=curva,
                                  n_sim=n_sim, semilla=semilla, cfg=self.cfg_re, devolver_simulaciones=True,
                                  presencia=P["presencia"].to_numpy(float))
        return P.reset_index(drop=True), M / gm


# =============================================================================================== valor en pista de una plantilla
def pi_matriz(Pm: np.ndarray) -> np.ndarray:
    """π_jk por simulación (n_sim × n × n): fracción de las posesiones de j con k en pista."""
    pp = (Pm.sum(1) ** 2 - (Pm ** 2).sum(1)) / 2.0
    P = np.einsum("si,sj->sij", Pm, Pm) * (10.0 / np.maximum(pp, 1e-9))[:, None, None]
    idx = np.arange(Pm.shape[1])
    P[:, idx, idx] = 0.0
    return P / np.maximum(Pm[:, :, None], 1e-9)


def valor_en_pista(ins, liga: str, pids: list[str], Pm: np.ndarray, rng, fam: np.ndarray | None = None) -> dict:
    """v_j por simulación (n_sim × n) y sus componentes, más los rasgos de contexto c_j y de familiaridad."""
    n_sim, n = Pm.shape
    vals = [ins.valor(p, liga) for p in pids]
    b = np.array([x[0] for x in vals]); sd = np.array([x[1] for x in vals])
    Z = ins.z(pids)
    Phi = Z @ ins.Mr @ Z.T
    np.fill_diagonal(Phi, 0.0)
    PI = pi_matriz(Pm)
    syn = np.einsum("sjk,jk->sj", PI, Phi)
    h = ins.h(pids)
    B = b[None, :] + rng.normal(size=(n_sim, n)) * sd[None, :]
    v = B + h[None, :] + syn
    pim = PI.mean(0)
    w = pim / np.maximum(pim.sum(1, keepdims=True), 1e-9)
    U = Z @ ins.P4
    out = {"v": v, "beta": b, "beta_sd": sd, "fuente": [x[2] for x in vals], "h": h, "syn": syn.mean(0),
           "cuota": Pm.mean(0), "nivel_companeros": w @ b, "perfil_companeros": w @ U}
    if fam is not None:
        out["fam"] = (pim * fam).sum(1)
    return out


def pares_temporada(tr_t: pd.DataFrame) -> dict:
    """Posesiones compartidas en pista (mismo lado) por pareja de personas en una temporada, en TODAS las ligas:
    {(persona_menor, persona_mayor): posesiones}. Tramos en formato bbequipo.rapm.tramos (A/B = claves «persona|temp»)."""
    if tr_t is None or tr_t.empty:
        return {}
    filas_a, filas_b, pesos = [], [], []
    for lado in ("A", "B"):
        Q = np.array([[k.split("|")[0] for k in q] for q in tr_t[lado]], dtype=object)
        w = tr_t["poss"].to_numpy(float)
        for x in range(5):
            for y in range(x + 1, 5):
                filas_a.append(Q[:, x]); filas_b.append(Q[:, y]); pesos.append(w)
    a_, b_ = np.concatenate(filas_a), np.concatenate(filas_b)
    lo, hi = np.where(a_ < b_, a_, b_), np.where(a_ < b_, b_, a_)
    s_ = pd.Series(np.concatenate(pesos)).groupby([lo, hi]).sum()
    return dict(zip(s_.index, s_.to_numpy()))


def familiaridad_matriz(pares: dict, pids: list[str]) -> np.ndarray:
    """g(f_jk) = log(1 + f_jk/100), f_jk = posesiones que j y k compartieron en pista en la temporada anterior (prerregistro)."""
    n = len(pids)
    F = np.zeros((n, n))
    for x in range(n):
        for y in range(x + 1, n):
            k = (pids[x], pids[y]) if pids[x] < pids[y] else (pids[y], pids[x])
            F[x, y] = F[y, x] = pares.get(k, 0.0)
    return np.log1p(F / 100.0)


# =============================================================================================== un corte
def corte(cfg: dict, a: int, im: pd.DataFrame, tr_all: pd.DataFrame, progreso=print) -> pd.DataFrame:
    """v_j de toda la plantilla REAL de t+1 de cada equipo con fichajes del examen IM (motor ≤ t), y de los mismos
    jugadores en su plantilla de t (cuotas observadas) para el banco de contextualidad. Caché por corte."""
    cp = CE.RAIZ / "experimentos" / "v4_1" / "impacto_pista" / f"corte_{a}.pkl"
    if cp.exists():
        return pickle.loads(cp.read_bytes())
    cf = cfg["f2"]
    n_sim = int(cf.get("simulaciones", 300))
    t0 = time.time()
    ins = InsumosCorte(cfg, a, progreso)
    S, V = ins.S, ins.V
    mapa = V.mapa_clubes(ins.roles, ins.temp, ins.temp1)
    rng = np.random.default_rng(CE.semilla(cfg, f"impacto_pista|{a}"))
    pares = pares_temporada(tr_all[tr_all["temporada"] == ins.temp])
    umbral_rot = 5.0 * float(cfg["criterios"]["propuestas_ajuste"]["P1"].get("umbral", 0.075))   # P1: ≥ 7,5 % de los minutos del equipo
    filas = []
    e = im[im["anio"] == a]
    r0 = ins.roles[ins.roles["temporada"] == ins.temp]
    r1 = ins.roles[ins.roles["temporada"] == ins.temp1]
    for (liga, team), g in e.groupby(["liga_d", "team_d"]):
        team = str(team)
        club_t = V.club_en_t(ins.c, liga, team, None, mapa)
        miembros = S.miembros_reales(r1, liga, team, float(S.cfg_sim()["plantilla"]["minimo_presencia"]))
        pr = ins.minutos(liga, team, club_t, miembros, n_sim, int(rng.integers(1e9)))
        if pr is None:
            continue
        P, Pm = pr
        pids = list(P["persona_id"].astype(str))
        fam = familiaridad_matriz(pares, pids)
        v1 = valor_en_pista(ins, liga, pids, Pm, rng, fam)
        # plantilla de t del mismo club (para los que siguen): cuotas observadas en t (p = minutos / (minutos del equipo / 5))
        v0 = None
        g0 = ins.c.por_club.get(club_t) if club_t is not None else None
        if g0 is not None and g0["persona_id"].nunique() >= 7:
            g0 = g0.sort_values("min_total", ascending=False).drop_duplicates("persona_id")
            p0 = g0["min_total"].to_numpy(float) / (g0["min_total"].sum() / 5.0)
            pids0 = list(g0["persona_id"].astype(str))
            lt = str(g0["liga"].mode().iloc[0])
            v0 = {"pids": pids0, "p0": dict(zip(pids0, p0)), "liga0": dict(zip(pids0, g0["liga"].astype(str))),
                  "team0": dict(zip(pids0, g0["team_id"].astype(str))),
                  **valor_en_pista(ins, lt, pids0, p0[None, :].repeat(20, 0), rng)}
            cu1 = dict(zip(pids, Pm.mean(0)))
            altas_rot = sum(1 for q in set(pids) - set(pids0) if cu1[q] >= umbral_rot)
            bajas_rot = sum(1 for q in set(pids0) - set(pids) if v0["p0"][q] >= umbral_rot)
        fichajes = set(g["persona_id"].astype(str))
        for j, p in enumerate(pids):
            vv = v1["v"][:, j]
            fila = {"anio": a, "liga": liga, "team": team, "persona_id": p, "fichaje": p in fichajes,
                    "v_media": float(vv.mean()), "v_sd": float(vv.std()), "beta": float(v1["beta"][j]),
                    "beta_sd": float(v1["beta_sd"][j]), "fuente_beta": v1["fuente"][j], "h": float(v1["h"][j]),
                    "sinergia": float(v1["syn"][j]), "cuota": float(v1["cuota"][j]),
                    "nivel_companeros": float(v1["nivel_companeros"][j]),
                    **{f"perfil_companeros_{k}": float(v1["perfil_companeros"][j, k]) for k in range(4)},
                    "familiaridad": float(v1["fam"][j]), "n_plantilla": len(pids)}
            if v0 is not None and p in v0["pids"]:
                i0 = v0["pids"].index(p)
                fila.update({"v0_media": float(v0["v"][:, i0].mean()), "sinergia0": float(v0["syn"][i0]),
                             "nivel_companeros0": float(v0["nivel_companeros"][i0]),
                             **{f"perfil_companeros0_{k}": float(v0["perfil_companeros"][i0, k]) for k in range(4)},
                             "cuota0": float(v0["p0"][p]), "liga0": v0["liga0"][p], "team0": v0["team0"][p], "sigue": True, "altas_rotacion": altas_rot, "bajas_rotacion": bajas_rot,
                             "altas_equipo": len(set(pids) - set(v0["pids"])), "bajas_equipo": len(set(v0["pids"]) - set(pids))})
            filas.append(fila)
        if progreso and len(filas) % 500 < len(pids):
            progreso(f"    Impacto en pista corte {a}: {len(filas)} jugadores · {time.time() - t0:.0f} s", flush=True)
    out = pd.DataFrame(filas)
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_bytes(pickle.dumps(out))
    if progreso:
        progreso(f"  corte {a}: {len(out)} jugadores ({int(out['fichaje'].sum())} fichajes) · {time.time() - t0:.0f} s", flush=True)
    return out


# =============================================================================================== producto
class InsumosProduccion:
    """Adaptador de la capa 4 de producción (bbequipo.equipo.Equipo) a valor_en_pista (añade P4, los 4 componentes de M_r)."""

    def __init__(self, eq):
        self.eq, self.Mr = eq, eq.Mr
        w, V_ = np.linalg.eigh(self.Mr)
        self.P4 = V_[:, np.argsort(-np.abs(w))[:4]]

    def valor(self, pid, liga):
        return self.eq.valor(pid, liga)

    def z(self, pids):
        return self.eq.z(pids)

    def h(self, pids):
        return self.eq.h(pids)


def referencia(cfg: dict, R: pd.DataFrame, e: pd.DataFrame, res: dict) -> dict:
    """Referencia publicable: F_grupo (v̂ de las plantillas de todos los cortes), isotónica y rango por deciles con TODOS
    los cortes (como referencia_im.json de la v4.0) y el sello que fija la puerta F2-a (prerregistro)."""
    from sklearn.isotonic import IsotonicRegression
    from ..anclas import Empirica
    from . import examen_impacto as EX
    F = {g: Empirica(x["v_media"]).exportable() for g, x in R[R["v_media"].notna()].groupby("grupo")}
    ok = e[e["onoff_ok"] & e["c_IP"].notna()]
    iso = IsotonicRegression(y_min=0, y_max=100, out_of_bounds="clip").fit(ok["c_IP"], ok["pct_onoff"])
    bordes = np.quantile(ok["c_IP"], np.linspace(0, 1, 11))
    lo, hi = EX._rango(ok, "c_IP", "pct_onoff", (bordes[:-1] + bordes[1:]) / 2)
    pasa = bool(res["puerta"]["pasa"])
    ctx_ok = bool(res.get("contextualidad", {}).get("pasa", False))
    return {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "F_grupo": F,
            "isotonica": {"x": iso.X_thresholds_.tolist(), "y": iso.y_thresholds_.tolist()},
            "rango_deciles": {"bordes": bordes.tolist(), "q10": lo.tolist(), "q90": hi.tolist()},
            "fichajes_calibracion": int(len(ok)), "puerta_f2a": pasa,
            "sello": "SEGUN_FIABILIDAD" if pasa else "EXPERIMENTAL",
            "sello_cambio_por_movimientos": "SEGUN_FIABILIDAD" if (pasa and ctx_ok) else ("BAJA" if pasa else "EXPERIMENTAL"),
            "nota": ("Impacto en pista = percentil esperado (0–100) del on/off del jugador con estos compañeros y minutos, "
                     "calibrado; si la puerta F2-a no pasa, el IMPACTO v4.0 sigue siendo el ancla y éste se muestra EXPERIMENTAL")}


def escala_producto(ref: dict, liga: str, cfg40: dict, V: np.ndarray) -> pd.DataFrame:
    """V: n_sim × n muestras de v_j → crudo 100·E[F_grupo(v)] → isotónica → rango 80 % por deciles."""
    from ..anclas import _empirica_de, grupo_im
    F = _empirica_de(ref["F_grupo"].get(grupo_im(cfg40, liga)))
    if F is None:
        return pd.DataFrame({"impacto_pista": np.full(V.shape[1], np.nan)})
    cr = 100.0 * F(V).mean(0)
    iso = ref["isotonica"]
    cal = np.interp(cr, iso["x"], iso["y"])
    rd = ref["rango_deciles"]
    b = np.clip(np.searchsorted(np.r_[-np.inf, rd["bordes"][1:-1], np.inf], cr, side="right") - 1, 0, 9)
    lo, hi = np.minimum(np.asarray(rd["q10"])[b], cal), np.maximum(np.asarray(rd["q90"])[b], cal)
    return pd.DataFrame({"impacto_pista": cal, "impacto_pista_lo80": lo, "impacto_pista_hi80": hi, "impacto_pista_crudo": cr,
                         "impacto_pista_sello": ref.get("sello", "EXPERIMENTAL"), "ip_v_media": V.mean(0)})


# =============================================================================================== orquestación
def ejecutar(cfg: dict, cortes=None, progreso=print) -> dict:
    """Cortes (caché), familiaridad (si existe su JSON), examen §6.2, contextualidad, referencia de producto y salidas."""
    from . import examen_impacto as EX
    from .sinergia_mixta import tramos_ampliados
    cfg40 = CE.cargar_v40(cfg)
    im = pd.read_csv(CE.RAIZ / cfg40["salida"] / "equipo" / "anclas" / "im_examen.csv.gz", dtype={"team_d": str, "persona_id": str})
    tr = tramos_ampliados(cfg)
    R = pd.concat([corte(cfg, int(a), im, tr, progreso) for a in (cortes or cfg["comunes"]["cortes"])], ignore_index=True)
    d = CE.dir_salida(cfg, "impacto_pista")
    pf = d / "familiaridad.json"
    fam = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else None
    res, e = EX.ejecutar(cfg, R, im, fam, progreso)
    dfam = EX.delta_por_corte(fam, [int(c) for c in cfg["comunes"]["cortes"]])
    res["contextualidad"] = EX.contextualidad(cfg, R, int(cfg["comunes"]["bootstrap"]),
                                              int(cfg["comunes"]["semilla_bootstrap"]) + 7, dfam or None)
    if fam:
        res["familiaridad"] = {k: fam[k] for k in ("global", "elite_club")}
        pr = d / "familiaridad_robustez.json"
        if pr.exists():
            res["familiaridad_robustez_post_hoc"] = json.loads(pr.read_text(encoding="utf-8"))
    # movimiento del Impacto en pista frente al impacto marginal (IM v4.0) en las mismas filas
    m = e[e["IP"].notna() & e["IM_onoff"].notna() & e["anio"].isin([int(c) for c in cfg["comunes"]["cortes_decision"]])]
    res["movimiento_frente_IM"] = {"n": int(len(m)), "spearman_IP_IM": EX.spearman(m["IP"], m["IM_onoff"]),
                                   "dif_abs_media": float((m["IP"] - m["IM_onoff"]).abs().mean()),
                                   "frac_cambio_quintil": float((np.ceil(m["IP"] / 20).clip(1, 5) != np.ceil(m["IM_onoff"] / 20).clip(1, 5)).mean())}
    ref = referencia(cfg, _con_grupo(R, cfg40), e, res)
    (d / "referencia_impacto_pista.json").write_text(json.dumps(ref, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    (d / "examen_f2.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=_json), encoding="utf-8")
    cols = ["anio", "liga_d", "team_d", "grupo_im", "persona_id", "net_rtg_aj_onoff", "pct_onoff", "onoff_ok", "IM_onoff",
            "IM_aditivo", "v_media", "v_sd", "beta", "h", "sinergia", "cuota", "familiaridad", "c_IP", "IP", "IP_lo80", "IP_hi80",
            "IP_ctx", "IP_fam", "net_onoff", "xnet_onoff", "y_f2e"]
    e[[c for c in dict.fromkeys(cols) if c in e]].round(4).to_csv(d / "examen_filas.csv.gz", index=False)
    R.round(4).to_csv(d / "plantillas_cortes.csv.gz", index=False)
    return res


def _con_grupo(R: pd.DataFrame, cfg40: dict) -> pd.DataFrame:
    from ..anclas import grupo_im
    return R.assign(grupo=R["liga"].map(lambda l: grupo_im(cfg40, l)))


def _json(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return str(o)
