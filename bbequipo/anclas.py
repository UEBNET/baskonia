"""F5 · Métricas ancla en [0, 100] (encargo §10; puerta §11.5).

NIVEL CERNO (NC) = 100 · E_pred[ F_ref(C) ]: percentil esperado de la contribución de temporada C del jugador en el destino
(C = minutos/partido ÷ minutos del partido × pts/100, la del motor v3.2/v3.3) bajo su distribución predictiva, con F_ref la
distribución de C realizada en la población de referencia (DECISIÓN 1: liga de destino × puesto pos3, últimas 3 temporadas,
ponderada por minutos). NC₁ = primera temporada (con adaptación, titular); NC₂ = sin el coste de adaptación (variante
`sin_adaptacion` del examen v3.2). Rango: F_ref de los cuantiles predictivos 10 y 90.

IMPACTO (IM) = 100 · E_pred[ F_mov(Δ̂Net) ]: percentil esperado del Δ contrafactual del equipo (capa 4: plantilla real de t+1
con y sin el jugador, minutos del motor v3.3, β/φ/h, calibración c del grupo de liga) entre los Δ̂ de los fichajes reales
comparables (DECISIÓN 3: mismo grupo de liga élite / doméstica alta / resto; cortes ≤ t).

Examen §11.5 (`exam`): separación (pares del mismo corte y liga de destino con NC_a ≥ NC_b + 10 → a supera a b en C realizada en
≥ 62 %, IC95 inferior > 0,55), calibración por deciles (percentil realizado medio dentro de ±7), monotonía de IM (Spearman con
el ΔNet realizado del equipo ≥ el de la línea base aditiva; IC95 > 0), cobertura del 80 % de los rangos en [0,75, 0,85].
Salidas: data/modelos/v4_0/equipo/anclas/.
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
from . import equipo as EQ
from . import rapm as RP

NIVELES_Q = [("lo90", 0.05), ("lo80", 0.10), ("lo50", 0.25), ("pred", 0.50), ("hi50", 0.75), ("hi80", 0.90), ("hi90", 0.95)]


def dir_salida(cfg: dict) -> Path:
    d = C.RAIZ / cfg["f5"]["salida"] / "anclas"
    d.mkdir(parents=True, exist_ok=True)
    return d


def grupo_im(cfg: dict, liga: str) -> str:
    for g, ligas in cfg["f5"]["impacto"]["referencia"]["grupos"].items():
        if liga in ligas:
            return g
    return "resto"


# =============================================================================================== distribuciones de referencia
class Empirica:
    """CDF empírica ponderada."""

    def __init__(self, x, w=None):
        x = np.asarray(x, float); w = np.ones_like(x) if w is None else np.asarray(w, float)
        ok = np.isfinite(x) & np.isfinite(w) & (w > 0)
        o = np.argsort(x[ok]); self.x = x[ok][o]; cw = np.cumsum(w[ok][o]); self.F = (cw - 0.5 * w[ok][o]) / cw[-1] if len(cw) else np.array([])
        self.n = int(ok.sum())

    def __call__(self, v):
        if self.n == 0:
            return np.full(np.shape(v), np.nan)
        return np.interp(np.asarray(v, float), self.x, self.F, left=0.0, right=1.0)

    def exportable(self):
        qs = np.linspace(0, 1, 21)
        return {"n": self.n, "cuantiles": {f"{q:.2f}": float(np.interp(q, self.F, self.x)) for q in qs}} if self.n else {"n": 0}


def contribucion_realizada(roles: pd.DataFrame, gm_de) -> pd.Series:
    """C = (min_pg / gm) · 100·pts/poss_on por jugador-equipo-temporada (0 si < 50 min en la temporada)."""
    gm = roles["liga"].map(gm_de).astype(float)
    p100 = 100.0 * roles["pts"] / roles["poss_on"].replace(0, np.nan)
    c = (roles["min_pg"] / gm) * p100
    return c.where(roles["min_total"] >= 50, 0.0)


def referencias_nc(cfg: dict, roles: pd.DataFrame, temp: str, gm_de) -> dict:
    """F_ref por (liga, pos3) con las `temporadas` últimas ≤ temp, ponderada por minutos."""
    ref = cfg["f5"]["nivel_cerno"]["referencia"]
    anio = int(temp[:4]); temps = [f"{a}-{str(a + 1)[-2:]}" for a in range(anio - int(ref["temporadas"]) + 1, anio + 1)]
    r = roles[roles["temporada"].isin(temps) & (roles["min_total"] >= 100) & roles["pos3"].notna()].copy()
    r["C"] = contribucion_realizada(r, gm_de)
    out = {}
    for (l, p), g in r.groupby(["liga", "pos3"]):
        out[(l, p)] = Empirica(g["C"], g["min_total"])
    for l, g in r.groupby("liga"):                          # sin puesto: la liga entera
        out[(l, None)] = Empirica(g["C"], g["min_total"])
    return out


def muestras_predictivas(fila: pd.Series, prefijo: str, n: int, rng, minimo: float = 0.0) -> np.ndarray:
    """Muestras de la predictiva a partir de sus cuantiles (lo90, lo80, lo50, pred, hi50, hi80, hi90): función cuantil lineal
    a trozos, colas prolongadas con la pendiente del último tramo."""
    q = []; v = []
    for suf, p in NIVELES_Q:
        x = fila.get(f"{prefijo}_{suf}", np.nan)
        if np.isfinite(x):
            q.append(p); v.append(float(x))
    if len(q) < 2:
        return np.full(n, v[0] if v else np.nan)
    q, v = np.array(q), np.maximum.accumulate(np.array(v))           # monótona
    u = rng.uniform(0.005, 0.995, n)
    out = np.interp(u, q, v)
    izq = u < q[0]; der = u > q[-1]
    if izq.any() and len(q) > 1:
        out[izq] = v[0] - (q[0] - u[izq]) * (v[1] - v[0]) / max(q[1] - q[0], 1e-6)
    if der.any() and len(q) > 1:
        out[der] = v[-1] + (u[der] - q[-1]) * (v[-1] - v[-2]) / max(q[-1] - q[-2], 1e-6)
    return np.maximum(out, minimo)


def percentil_esperado(F: Empirica, muestras: np.ndarray) -> tuple[float, float, float]:
    """(100·E[F(C)], 100·F(q10), 100·F(q90))."""
    if F is None or F.n == 0 or not np.isfinite(muestras).any():
        return np.nan, np.nan, np.nan
    return float(100 * np.mean(F(muestras))), float(100 * F(np.quantile(muestras, 0.10))), float(100 * F(np.quantile(muestras, 0.90)))


# =============================================================================================== NC: examen
def _v():
    cfg = C.cargar()
    os.environ.setdefault("CERNO_SIMULADOR", cfg["insumos"].get("simulador_env_corte", "v32"))
    from bbfit import v32, simulador as S, sim_insumos as SI  # noqa: E402
    return v32, S, SI


def nivel_cerno_examen(cfg: dict, progreso=print) -> pd.DataFrame:
    """NC₁ y NC₂ de los fichajes reales del examen v3.2 (V32_corte, 4 cortes) con F_ref de su liga de destino × pos3 (3
    temporadas ≤ t), y su percentil realizado."""
    v32, S, SI = _v()
    c32 = v32.cfg()
    EE = v32.cargar_ejecuciones(c32); E = EE["V32_corte"]
    e_all = E["completo"].reset_index(drop=True)
    sin_ad = E.get("sin_adaptacion")
    roles = SI._leer_roles_temporada()
    gm_de = {l: S.minutos_partido(l) for l in roles["liga"].unique()}
    rng = np.random.default_rng(int(cfg["semilla"]))
    n_m = 400
    filas = []
    cortes = sorted(e_all["corte"].unique())
    for t in cortes:
        e_t = e_all[e_all["corte"] == t].reset_index(drop=True)
        t1 = e_t["temporada_d"].iloc[0] if "temporada_d" in e_t else f"{int(t[:4]) + 1}-{str(int(t[:4]) + 2)[-2:]}"
        Fref = referencias_nc(cfg, roles, t, gm_de)
        r1 = roles[roles["temporada"] == t1]
        pos = r1.drop_duplicates(["liga", "team_id", "persona_id"]).set_index(["liga", "team_id", "persona_id"])["pos3"]
        sa = None
        if sin_ad is not None:
            sa = sin_ad[sin_ad["corte"] == t].drop_duplicates(["persona_id", "liga_d", "team_d"]).set_index(["persona_id", "liga_d", "team_d"])
        for row in e_t.itertuples():
            p3 = pos.get((row.liga_d, str(row.team_d), row.persona_id), None)
            if isinstance(p3, float) and np.isnan(p3):
                p3 = None
            F = Fref.get((row.liga_d, p3)) or Fref.get((row.liga_d, None))
            if F is None or F.n < 30:
                continue
            fila = e_t.loc[row.Index]
            m1 = muestras_predictivas(fila, "v_C", n_m, rng)
            nc1, lo1, hi1 = percentil_esperado(F, m1)
            nc2 = lo2 = hi2 = np.nan
            if sa is not None and (row.persona_id, row.liga_d, row.team_d) in sa.index:
                m2 = muestras_predictivas(sa.loc[(row.persona_id, row.liga_d, row.team_d)], "v_C", n_m, rng)
                nc2, lo2, hi2 = percentil_esperado(F, m2)
            c_real = fila.get("C_real", np.nan)
            filas.append({"corte": t, "temporada_d": t1, "persona_id": row.persona_id, "liga_d": row.liga_d, "team_d": str(row.team_d), "pos3": p3,
                          "n_ref": F.n, "C_pred": fila.get("v_C_pred", np.nan), "C_real": c_real, "eval": bool(fila.get("eval_min", True)) and np.isfinite(c_real),
                          "NC1": nc1, "NC1_lo80": lo1, "NC1_hi80": hi1, "NC2": nc2, "NC2_lo80": lo2, "NC2_hi80": hi2,
                          "pct_realizado": float(100 * F(c_real)) if np.isfinite(c_real) else np.nan,
                          "min_real": fila.get("min_real", np.nan), "min_total_real": fila.get("min_total_real", np.nan)})
        if progreso:
            d = pd.DataFrame([f for f in filas if f["corte"] == t])
            progreso(f"    NC corte {t}: {len(d)} fichajes · NC₁ medio {d['NC1'].mean():.1f} (DT {d['NC1'].std():.1f}) · pct realizado medio {d['pct_realizado'].mean():.1f}", flush=True)
    return pd.DataFrame(filas)


def examen_separacion(d: pd.DataFrame, col_nc: str, col_real: str, por: list[str], umbral: float, B: int, semilla: int) -> dict:
    """Pares (mismo grupo `por`) con NC_a ≥ NC_b + umbral: fracción con real_a > real_b; IC95 por bootstrap de fichajes."""
    rng = np.random.default_rng(semilla)
    d = d[d[col_nc].notna() & d[col_real].notna()].reset_index(drop=True)
    def frac(idx):
        x = d.iloc[idx]
        num = den = 0
        for _, g in x.groupby(por):
            nc = g[col_nc].to_numpy(); re = g[col_real].to_numpy()
            if len(g) < 2:
                continue
            A = nc[:, None] - nc[None, :] >= umbral
            num += int((A & (re[:, None] > re[None, :])).sum()); den += int(A.sum())
        return num / den if den else np.nan, den
    f0, n_pares = frac(np.arange(len(d)))
    bs = [frac(rng.integers(0, len(d), len(d)))[0] for _ in range(B)]
    return {"fraccion": f0, "pares": n_pares, "ic95": [float(np.nanquantile(bs, .025)), float(np.nanquantile(bs, .975))], "fichajes": int(len(d))}


def examen_calibracion(d: pd.DataFrame, col: str, col_real: str, tol: float) -> dict:
    x = d[d[col].notna() & d[col_real].notna()]
    dec = pd.qcut(x[col].rank(method="first"), 10, labels=False)
    t = x.groupby(dec).agg(n=(col, "size"), previsto=(col, "mean"), realizado=(col_real, "mean"))
    t["desvio"] = t["realizado"] - t["previsto"]
    return {"deciles": t.round(2).to_dict("index"), "max_desvio_abs": float(t["desvio"].abs().max()), "tolerancia": tol,
            "pasa": bool((t["desvio"].abs() <= tol).all())}


def cobertura(d: pd.DataFrame, lo: str, hi: str, real: str) -> float:
    x = d[d[lo].notna() & d[real].notna()]
    return float(np.mean((x[real] >= x[lo]) & (x[real] <= x[hi]))) if len(x) else np.nan


# =============================================================================================== IM: Δ contrafactual por fichaje
def impacto_corte(cfg: dict, a: int, tr_all: pd.DataFrame, e_all: pd.DataFrame, trans: pd.DataFrame, progreso=print) -> pd.DataFrame:
    """Para los fichajes del corte a (t → t+1): Δ̂ raw = T(plantilla real de t+1) − T(sin el fichaje), minutos del motor v3.3
    (≤ t), β/φ/h del corte; realizado: ΔNet del equipo (transiciones). Caché por corte."""
    n_sim = int(cfg["f5"]["impacto"].get("simulaciones", 200))
    cache = dir_salida(cfg) / f"im_corte_{a}.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    t0 = time.time()
    ins = EQ.Insumos(cfg, a, tr_all, progreso)
    S, V = ins.S, ins.V
    t = ins.temp
    e_t = e_all[e_all["corte"] == t]
    mapa = V.mapa_clubes(ins.roles, ins.temp, ins.temp1)
    rng = np.random.default_rng(int(cfg["semilla"]) + a)
    real = trans[(trans["anio"] == a)].set_index(["liga", "team_id_nuevo"])["delta_net"]
    from . import dirigidos as DG
    mods_f2b = DG.modelos_corte(cfg, a, ins.R, progreso=progreso)
    filas = []
    for (liga, team), g in e_t.groupby(["liga_d", "team_d"]):
        team = str(team)
        club_t = V.club_en_t(ins.c, liga, team, None, mapa)
        pr = ins.cuotas_proyectadas(liga, team, club_t, n_sim, int(rng.integers(1e9)))
        if pr is None:
            continue
        P, Pm = pr
        pids = list(P["persona_id"])
        v_con = EQ.valor_equipo(ins, liga, pids, Pm, rng)
        gm = S.minutos_partido(liga)
        for row in g.itertuples():
            pid = row.persona_id
            if pid not in pids:
                continue
            miembros = [(p, float(x)) for p, x in zip(P["persona_id"], P["presencia"]) if p != pid]
            if len(miembros) < 7:
                continue
            Ps = S.plantilla(ins.c, club_t or f"{liga}|{team}", liga, miembros)
            Ps["encaje"] = pd.to_numeric(Ps.get("encaje_pos", 0.0), errors="coerce").fillna(0.0)
            Ps["nivel"] = S.utilidad(ins.c, Ps) * float(ins.c.calib.get("escala_utilidad", 1.0))
            ent = ins.roles[(ins.roles["temporada"] == ins.temp1) & (ins.roles["liga"] == liga) & (ins.roles["team_id"].astype(str) == team)]["entrenador_id"].dropna()
            entrenador = ent.mode().iloc[0] if len(ent) else S.entrenador_equipo(ins.c, liga, team)
            rot, rot_sd, curva = S.tendencia(ins.c, entrenador, liga)
            pl = pd.DataFrame({"player_id": Ps["persona_id"].to_numpy(), "nivel": Ps["nivel"].to_numpy(float), "pos3": Ps["pos3"].to_numpy(object)})
            _, Ms = ins.RE.asignar_minutos(pl, total_min=5 * gm, minutos_partido=gm, rotacion_media=rot, rotacion_sd=rot_sd, curva=curva, n_sim=n_sim,
                                           semilla=int(rng.integers(1e9)), cfg=ins.cfg_re, devolver_simulaciones=True, presencia=Ps["presencia"].to_numpy(float))
            v_sin = EQ.valor_equipo(ins, liga, list(Ps["persona_id"]), Ms / gm, rng)
            d_raw = v_con["T"] - v_sin["T"]
            i = pids.index(pid)
            b, sd, fuente = ins.valor(pid, liga)
            p_new = float(Pm[:, i].mean())
            # complemento F2-B: efecto de X sobre los números de sus compañeros, agregado con sus cuotas proyectadas (sin X)
            otros = [j for j in range(len(pids)) if j != i]
            comp = DG.efectos_sobre_companeros(mods_f2b, ins.z([pid])[0], ins.z([pids[j] for j in otros]), Pm[:, otros].mean(0))
            filas.append({"corte": t, "anio": a, "persona_id": pid, "liga_d": liga, "team_d": team, "grupo_im": grupo_im(cfg, liga),
                          "delta_raw": float(d_raw.mean()), "delta_raw_sd": float(d_raw.std()),
                          **{f"delta_raw_p{int(q * 100):02d}": float(np.quantile(d_raw, q)) for q in (0.05, 0.10, 0.25, 0.75, 0.90, 0.95)},
                          "aditivo_jugador": float(p_new * b), "coste_oportunidad": float((v_con["T_aditivo"] - v_sin["T_aditivo"]).mean() - p_new * b),
                          "sinergia_phi": float((v_con["T_phi"] - v_sin["T_phi"]).mean()), "correccion_h": float((v_con["T_h"] - v_sin["T_h"]).mean()),
                          "comp_pts100": comp.get("d_pts100", np.nan), "comp_cuota_tiro": comp.get("d_cuota_tiro", np.nan), "comp_pct_asistidas": comp.get("d_pct_asistidas", np.nan),
                          "beta": b, "beta_sd": sd, "fuente_beta": fuente, "cuota_minutos": p_new, "minutos_proyectados": p_new * gm,
                          "n_plantilla": len(pids), "delta_net_real_equipo": float(real.get((liga, team), np.nan))})
        if progreso and len(filas) % 200 < len(g):
            progreso(f"    IM corte {a}: {len(filas)} fichajes · {time.time() - t0:.0f} s", flush=True)
    out = pd.DataFrame(filas)
    cache.write_bytes(pickle.dumps(out))
    if progreso:
        progreso(f"  IM corte {a}: {len(out)} fichajes · Δ̂ raw medio {out['delta_raw'].mean():+.2f} (DT {out['delta_raw'].std():.2f}) · {time.time() - t0:.0f} s", flush=True)
    return out


def impacto_examen(cfg: dict, progreso=print, cortes=None) -> pd.DataFrame:
    v32, S, SI = _v()
    c32 = v32.cfg()
    e_all = v32.cargar_ejecuciones(c32)["V32_corte"]["completo"].reset_index(drop=True)
    tr_all = RP.tramos(cfg, None, progreso=None)
    trans = EQ.transiciones(cfg)
    extra = EQ.filtrar_contrato(cfg, EQ.transiciones_extra(cfg, trans))
    trans = pd.concat([trans, extra], ignore_index=True) if len(extra) else trans
    partes = [impacto_corte(cfg, a, tr_all, e_all, trans, progreso) for a in (cortes or [int(x) for x in cfg["criterios"]["comunes"]["cortes"]])]
    return pd.concat(partes, ignore_index=True)


def calibrar_im(d: pd.DataFrame, pred_f4: pd.DataFrame, cfg: dict, cortes: list[int]) -> pd.DataFrame:
    """Δ̂Net = c_grupo(corte) · Δ̂ raw (c de la calibración de F4 del corte, cortes anteriores); F_mov por grupo IM con los
    fichajes de cortes ≤ t (el primer corte, los suyos); IM, rango y percentil realizado del ΔNet del equipo."""
    d = d.copy()
    cc = pred_f4.groupby(["corte", "grupo"])["c_cal"].mean().to_dict(); c_pool = pred_f4.groupby("corte")["c_cal"].mean().to_dict()
    d["grupo_f4"] = d["liga_d"].map(EQ.GRUPOS_LIGA).fillna("otras")
    d["c"] = [cc.get((a, g), c_pool.get(a, 0.4)) for a, g in zip(d["anio"], d["grupo_f4"])]
    for col in ["delta_raw", "delta_raw_sd"] + [c for c in d.columns if c.startswith("delta_raw_p")]:
        d[col.replace("delta_raw", "delta_net")] = d[col] * d["c"]
    d["aditivo_b"] = d["c"] * d["aditivo_jugador"]
    rng = np.random.default_rng(int(cfg["semilla"]))
    d["IM"] = np.nan; d["IM_lo80"] = np.nan; d["IM_hi80"] = np.nan; d["IM_aditivo"] = np.nan; d["pct_real_equipo"] = np.nan; d["n_mov"] = 0
    for k, a in enumerate(cortes):
        prev = d[d["anio"].isin(cortes[:k + 1])]                      # ≤ t (incluye el propio corte: escala, no resultado)
        for g in d["grupo_im"].unique():
            Fm = Empirica(prev.loc[prev["grupo_im"] == g, "delta_net"])
            Fr = Empirica(prev.loc[(prev["grupo_im"] == g) & prev["delta_net_real_equipo"].notna(), "delta_net_real_equipo"].drop_duplicates())
            sel = (d["anio"] == a) & (d["grupo_im"] == g)
            if Fm.n < 30:
                continue
            for i in d.index[sel]:
                fila = d.loc[i]
                q = {"lo90": fila["delta_net_p05"], "lo80": fila["delta_net_p10"], "lo50": fila["delta_net_p25"], "pred": fila["delta_net"],
                     "hi50": fila["delta_net_p75"], "hi80": fila["delta_net_p90"], "hi90": fila["delta_net_p95"]}
                m = muestras_predictivas(pd.Series({f"x_{k2}": v for k2, v in q.items()}), "x", 300, rng, minimo=-1e9)
                im, lo, hi = percentil_esperado(Fm, m)
                d.loc[i, ["IM", "IM_lo80", "IM_hi80", "n_mov"]] = [im, lo, hi, Fm.n]
                d.loc[i, "IM_aditivo"] = float(100 * Fm(fila["aditivo_b"]))
                if np.isfinite(fila["delta_net_real_equipo"]) and Fr.n >= 20:
                    d.loc[i, "pct_real_equipo"] = float(100 * Fr(fila["delta_net_real_equipo"]))
    return d


def calibrar_nc(nc: pd.DataFrame, cortes: list[int], col: str = "NC1", min_prev: int = 300) -> pd.DataFrame:
    """Capa de calibración de NC [DECISIÓN en el corte de calibración 2021]: el percentil esperado crudo subestima el percentil
    realizado de los fichajes que llegan a jugar (la población del examen es la de quienes jugaron ≥ el mínimo; la predictiva
    incluye la posibilidad de no jugar). NC publicado = g(NC crudo) con g isotónica (monótona) ajustada con los cortes
    ANTERIORES sobre (NC crudo → percentil realizado); el primer corte usa la suya (informativo). Se aplica igual al rango
    (lo80/hi80) y a NC₂. Las columnas `*_crudo` conservan el valor sin calibrar."""
    from sklearn.isotonic import IsotonicRegression
    nc = nc.copy()
    for c in (col, f"{col}_lo80", f"{col}_hi80", "NC2", "NC2_lo80", "NC2_hi80"):
        nc[f"{c}_crudo"] = nc[c]
    nc["nc_calibrado_con"] = None
    for k, a in enumerate(cortes):
        prev = nc[nc["anio"].isin(cortes[:k]) & nc["eval"]] if k else nc[(nc["anio"] == a) & nc["eval"]]
        sel = nc["anio"] == a
        if len(prev) < min_prev:
            continue
        g = IsotonicRegression(y_min=0.0, y_max=100.0, out_of_bounds="clip").fit(prev[f"{col}_crudo"], prev["pct_realizado"])
        # rango del 80 %: cuantiles 10 y 90 del percentil realizado condicionados al decil de NC crudo (cortes anteriores);
        # el rango crudo (F_ref de los cuantiles de C) no es un intervalo del percentil realizado y la isotónica lo comprimiría
        bordes = np.quantile(prev[f"{col}_crudo"], np.linspace(0, 1, 11)); bordes[0], bordes[-1] = -np.inf, np.inf
        bins_prev = np.clip(np.searchsorted(bordes, prev[f"{col}_crudo"], side="right") - 1, 0, 9)
        q10 = np.array([np.quantile(prev["pct_realizado"][bins_prev == b], 0.10) if (bins_prev == b).sum() >= 20 else np.nan for b in range(10)])
        q90 = np.array([np.quantile(prev["pct_realizado"][bins_prev == b], 0.90) if (bins_prev == b).sum() >= 20 else np.nan for b in range(10)])
        q10 = pd.Series(q10).interpolate(limit_direction="both").to_numpy(); q90 = pd.Series(q90).interpolate(limit_direction="both").to_numpy()
        for base in (col, "NC2"):
            v = nc.loc[sel, f"{base}_crudo"].to_numpy(float); ok = np.isfinite(v)
            centro = np.full(len(v), np.nan); centro[ok] = g.predict(v[ok]); nc.loc[sel, base] = centro
            b = np.clip(np.searchsorted(bordes, np.nan_to_num(v, nan=0.0), side="right") - 1, 0, 9)
            lo = np.where(ok, q10[b], np.nan); hi = np.where(ok, q90[b], np.nan)
            nc.loc[sel, f"{base}_lo80"] = np.minimum(lo, centro); nc.loc[sel, f"{base}_hi80"] = np.maximum(hi, centro)
        nc.loc[sel, "nc_calibrado_con"] = "cortes_anteriores" if k else "propio_corte"
    return nc


def examen_im_onoff(im: pd.DataFrame, cfg: dict, cortes: list[int], dec: list[int], B: int, sem: int) -> tuple[dict, pd.DataFrame]:
    """Criterio prerregistrado `criterios.f5.im_onoff` (decisión b del CEO): IM frente al Net on/off realizado del fichaje en el
    destino. Calibración isotónica de IM crudo con cortes anteriores; variante IM+comp (combinación lineal de Δ̂Net y comp_pts100
    ajustada con cortes anteriores sobre el on/off, → percentil → isotónica); se adopta sólo si mejora el Spearman con IC95 > 0.
    Devuelve el resumen y las filas con IM_onoff, IM_comp y el subíndice «efecto sobre compañeros»."""
    from scipy.stats import spearmanr
    from sklearn.isotonic import IsotonicRegression
    crit = cfg["criterios"]["f5"]["im_onoff"]
    rr = pd.read_csv(C.RAIZ / cfg["insumos"]["roles"], usecols=["liga", "temporada", "team_id", "persona_id", "net_rtg_aj_onoff", "min_total"],
                     dtype={"team_id": str}, low_memory=False).rename(columns={"liga": "liga_d", "team_id": "team_d", "temporada": "temporada_d"})
    e = im[im["IM"].notna()].copy()
    e["temporada_d"] = e["anio"].map(lambda a: f"{a + 1}-{str(a + 2)[-2:]}")
    e = e.merge(rr, on=["liga_d", "team_d", "temporada_d", "persona_id"], how="left")
    e["onoff_ok"] = e["net_rtg_aj_onoff"].notna() & (e["min_total"] >= float(crit["min_minutos"]))
    e["pct_onoff"] = np.nan
    for (a, g), x in e[e["onoff_ok"]].groupby(["anio", "grupo_im"]):
        e.loc[x.index, "pct_onoff"] = x["net_rtg_aj_onoff"].rank(pct=True) * 100
    e["IM_crudo"] = e["IM"]
    e["comp_pct"] = np.nan                                   # subíndice: percentil de comp_pts100 entre los fichajes del grupo (≤ t)
    for col in ("IM_onoff", "IM_onoff_lo80", "IM_onoff_hi80", "IM_comp", "IM_comp_lo80", "IM_comp_hi80", "IM_comp_crudo"):
        e[col] = np.nan
    rng = np.random.default_rng(sem)
    def rango(prev, col_c, col_y, v):
        bordes = np.quantile(prev[col_c], np.linspace(0, 1, 11)); bordes[0], bordes[-1] = -np.inf, np.inf
        bp = np.clip(np.searchsorted(bordes, prev[col_c], side="right") - 1, 0, 9)
        q10 = pd.Series([np.quantile(prev[col_y][bp == b], .10) if (bp == b).sum() >= 20 else np.nan for b in range(10)]).interpolate(limit_direction="both").to_numpy()
        q90 = pd.Series([np.quantile(prev[col_y][bp == b], .90) if (bp == b).sum() >= 20 else np.nan for b in range(10)]).interpolate(limit_direction="both").to_numpy()
        b = np.clip(np.searchsorted(bordes, np.nan_to_num(v), side="right") - 1, 0, 9)
        return q10[b], q90[b]
    for k, a in enumerate(cortes):
        sel = e["anio"] == a
        prev = e[e["anio"].isin(cortes[:k]) & e["onoff_ok"]] if k else e[sel & e["onoff_ok"]]
        hasta = e[e["anio"] <= a]
        for g in e["grupo_im"].unique():
            sg = sel & (e["grupo_im"] == g)
            Fc = Empirica(hasta.loc[hasta["grupo_im"] == g, "comp_pts100"])
            if Fc.n >= 30:
                e.loc[sg, "comp_pct"] = 100 * Fc(e.loc[sg, "comp_pts100"])
        if len(prev) < 300:
            continue
        g1 = IsotonicRegression(y_min=0, y_max=100, out_of_bounds="clip").fit(prev["IM_crudo"], prev["pct_onoff"])
        v = e.loc[sel, "IM_crudo"].to_numpy(float)
        e.loc[sel, "IM_onoff"] = g1.predict(np.nan_to_num(v, nan=50.0))
        lo, hi = rango(prev, "IM_crudo", "pct_onoff", v); e.loc[sel, "IM_onoff_lo80"] = np.minimum(lo, e.loc[sel, "IM_onoff"]); e.loc[sel, "IM_onoff_hi80"] = np.maximum(hi, e.loc[sel, "IM_onoff"])
        # variante IM+comp: y = on/off ~ Δ̂Net + comp_pts100 (cortes anteriores) → puntuación → percentil entre los fichajes del grupo → isotónica
        A = np.c_[prev["delta_net"], prev["comp_pts100"].fillna(0.0), np.ones(len(prev))]
        coef = np.linalg.lstsq(A, prev["net_rtg_aj_onoff"], rcond=None)[0]
        sc_prev = A @ coef
        e.loc[sel, "IM_comp_crudo"] = np.nan
        for g in e["grupo_im"].unique():
            pg = prev["grupo_im"] == g
            sg = sel & (e["grupo_im"] == g)
            if pg.sum() < 30 or sg.sum() == 0:
                continue
            Fs = Empirica(sc_prev[pg.to_numpy()])
            sc = np.c_[e.loc[sg, "delta_net"], e.loc[sg, "comp_pts100"].fillna(0.0), np.ones(sg.sum())] @ coef
            e.loc[sg, "IM_comp_crudo"] = 100 * Fs(sc)
        prev_c = prev.copy(); prev_c["sc_pct"] = np.nan
        for g in prev["grupo_im"].unique():
            pg = (prev["grupo_im"] == g).to_numpy()
            if pg.sum() >= 30:
                prev_c.loc[prev.index[pg], "sc_pct"] = 100 * Empirica(sc_prev[pg])(sc_prev[pg])
        okp = prev_c["sc_pct"].notna()
        if okp.sum() >= 300:
            g2 = IsotonicRegression(y_min=0, y_max=100, out_of_bounds="clip").fit(prev_c.loc[okp, "sc_pct"], prev_c.loc[okp, "pct_onoff"])
            v2 = e.loc[sel, "IM_comp_crudo"].to_numpy(float); ok2 = np.isfinite(v2)
            outc = np.full(len(v2), np.nan); outc[ok2] = g2.predict(v2[ok2]); e.loc[sel, "IM_comp"] = outc
            lo, hi = rango(prev_c[okp], "sc_pct", "pct_onoff", np.nan_to_num(v2, nan=50.0))
            e.loc[sel, "IM_comp_lo80"] = np.where(ok2, np.minimum(lo, outc), np.nan); e.loc[sel, "IM_comp_hi80"] = np.where(ok2, np.maximum(hi, outc), np.nan)
    d = e[e["anio"].isin(dec) & e["onoff_ok"] & e["IM_onoff"].notna()]
    def mono(col):
        r1 = spearmanr(d[col], d["net_rtg_aj_onoff"]).correlation; r0 = spearmanr(d["IM_aditivo"], d["net_rtg_aj_onoff"]).correlation
        bs, bsd = [], []
        for _ in range(min(B, 1000)):
            ii = rng.integers(0, len(d), len(d)); x = d.iloc[ii]
            a1 = spearmanr(x[col], x["net_rtg_aj_onoff"]).correlation; a0 = spearmanr(x["IM_aditivo"], x["net_rtg_aj_onoff"]).correlation
            bs.append(a1); bsd.append(a1 - a0)
        return {"spearman": float(r1), "ic95": [float(np.quantile(bs, .025)), float(np.quantile(bs, .975))], "spearman_aditivo": float(r0),
                "ic95_diferencia_vs_aditivo": [float(np.quantile(bsd, .025)), float(np.quantile(bsd, .975))]}
    res = {"fichajes": int(len(d)), "por_corte": {str(a): int((d["anio"] == a).sum()) for a in dec}, "variantes": {}}
    for nombre, col in (("im_onoff", "IM_onoff"), ("im_comp", "IM_comp")):
        dd = d[d[col].notna()]
        if len(dd) < 100:
            continue
        res["variantes"][nombre] = {"n": int(len(dd)), "monotonia": mono(col),
                                    "calibracion": examen_calibracion(dd, col, "pct_onoff", float(crit["calibracion_deciles_tolerancia"])),
                                    "cobertura_80": cobertura(dd, f"{col}_lo80", f"{col}_hi80", "pct_onoff"), "anchura_80_media": float((dd[f"{col}_hi80"] - dd[f"{col}_lo80"]).mean())}
    # ¿adoptar IM+comp? Spearman mayor con IC95 de la diferencia > 0
    if "im_comp" in res["variantes"]:
        dd = d[d["IM_comp"].notna()]
        bs = []
        for _ in range(min(B, 1000)):
            ii = rng.integers(0, len(dd), len(dd)); x = dd.iloc[ii]
            bs.append(spearmanr(x["IM_comp"], x["net_rtg_aj_onoff"]).correlation - spearmanr(x["IM_onoff"], x["net_rtg_aj_onoff"]).correlation)
        res["comp_frente_a_im"] = {"dif_spearman": float(spearmanr(dd["IM_comp"], dd["net_rtg_aj_onoff"]).correlation - spearmanr(dd["IM_onoff"], dd["net_rtg_aj_onoff"]).correlation),
                                   "ic95": [float(np.quantile(bs, .025)), float(np.quantile(bs, .975))]}
        res["comp_frente_a_im"]["adoptar"] = bool(res["comp_frente_a_im"]["ic95"][0] > 0)
    # subíndice «efecto sobre compañeros»: ¿añade algo al on/off más allá de IM? correlación parcial simple
    dd = d[d["comp_pct"].notna()]
    res["subindice_companeros"] = {"n": int(len(dd)), "spearman_onoff": float(spearmanr(dd["comp_pct"], dd["net_rtg_aj_onoff"]).correlation),
                                   "spearman_con_im": float(spearmanr(dd["comp_pct"], dd["IM_onoff"]).correlation),
                                   "media_comp_pts100": float(dd["comp_pts100"].mean()), "sd_comp_pts100": float(dd["comp_pts100"].std())}
    elegida = "im_comp" if res.get("comp_frente_a_im", {}).get("adoptar") else "im_onoff"
    v = res["variantes"].get(elegida) or res["variantes"]["im_onoff"]
    lo_c, hi_c = crit["cobertura_80"]
    res["puerta_im_onoff"] = {"variante": elegida,
                              "monotonia_mejor_que_aditivo_ic95": bool(v["monotonia"]["ic95_diferencia_vs_aditivo"][0] > 0),
                              "calibracion": v["calibracion"]["pasa"], "cobertura_en_rango": bool(lo_c <= v["cobertura_80"] <= hi_c)}
    res["puerta_im_onoff"]["pasa"] = all(x for k2, x in res["puerta_im_onoff"].items() if k2 != "variante")
    res["estado_im"] = "referente" if res["puerta_im_onoff"]["pasa"] else crit["estado_si_no_pasa"]
    return res, e


# =============================================================================================== examen completo
def main(cfg: dict, progreso=print) -> dict:
    from bbfit.registro import experimento
    from scipy.stats import spearmanr
    t0 = time.time()
    out = dir_salida(cfg)
    crit = cfg["criterios"]["f5"]; B = int(cfg["criterios"]["comunes"]["bootstrap"]); sem = int(cfg["criterios"]["comunes"]["semilla_bootstrap"])
    cortes = [int(x) for x in cfg["criterios"]["comunes"]["cortes"]]; dec = [int(x) for x in cfg["criterios"]["comunes"]["cortes_decision"]]
    with experimento(cfg["mlflow"], "F5_examen", params={"cortes": cortes}):
        cache_nc = out / "nc_examen_crudo.csv.gz"
        if cache_nc.exists():
            nc = pd.read_csv(cache_nc)
            if "anio" not in nc:
                nc["anio"] = nc["corte"].str[:4].astype(int)
        else:
            nc = nivel_cerno_examen(cfg, progreso); nc["anio"] = nc["corte"].str[:4].astype(int); nc.to_csv(cache_nc, index=False)
        nc = calibrar_nc(nc, cortes)
        nc.round(3).to_csv(out / "nc_examen.csv.gz", index=False)
        im = impacto_examen(cfg, progreso)
        pred_f4 = pd.read_csv(EQ.dir_salida(cfg) / "examen" / "predicciones_f4.csv.gz")
        im = calibrar_im(im, pred_f4, cfg, cortes)
        im.round(3).to_csv(out / "im_examen.csv.gz", index=False)
        res = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "cortes": cortes, "cortes_decision": dec, "nc": {}, "im": {}}
        d = nc[nc["anio"].isin(dec) & nc["eval"]]
        sep = crit["nc_separacion"]
        res["nc"]["fichajes_decision"] = int(len(d))
        res["nc"]["separacion"] = examen_separacion(d, "NC1", "C_real", ["corte", "liga_d"], float(sep["diferencia_minima"]), min(B, 300), sem)
        res["nc"]["calibracion"] = examen_calibracion(d, "NC1", "pct_realizado", float(crit["nc_calibracion_deciles_tolerancia"]))
        res["nc"]["cobertura_80"] = cobertura(d, "NC1_lo80", "NC1_hi80", "pct_realizado")
        res["nc"]["nc2"] = {"media": float(d["NC2"].mean()), "media_nc1": float(d["NC1"].mean()), "corr_nc1_nc2": float(d[["NC1", "NC2"]].corr().iloc[0, 1])}
        res["nc"]["crudo"] = {"media_nc1": float(d["NC1_crudo"].mean()), "media_pct_realizado": float(d["pct_realizado"].mean()),
                              "calibracion": examen_calibracion(d, "NC1_crudo", "pct_realizado", float(crit["nc_calibracion_deciles_tolerancia"])),
                              "cobertura_80": cobertura(d, "NC1_lo80_crudo", "NC1_hi80_crudo", "pct_realizado"),
                              "separacion": examen_separacion(d, "NC1_crudo", "C_real", ["corte", "liga_d"], float(sep["diferencia_minima"]), 100, sem)}
        res["nc"]["anchura_80_media"] = float((d["NC1_hi80"] - d["NC1_lo80"]).mean())
        res["nc"]["corr_nc1_pct_realizado"] = float(d[["NC1", "pct_realizado"]].corr().iloc[0, 1])
        res["nc"]["por_corte"] = {str(a): {"n": int((d["anio"] == a).sum()), "separacion": examen_separacion(d[d["anio"] == a], "NC1", "C_real", ["liga_d"], float(sep["diferencia_minima"]), 100, sem)["fraccion"],
                                           "cobertura_80": cobertura(d[d["anio"] == a], "NC1_lo80", "NC1_hi80", "pct_realizado")} for a in dec}
        s = res["nc"]["separacion"]
        res["nc"]["puerta"] = {"separacion": bool(s["fraccion"] >= float(sep["fraccion_minima"]) and s["ic95"][0] > float(sep["ic95_inferior_minimo"])),
                               "calibracion": res["nc"]["calibracion"]["pasa"],
                               "cobertura": bool(0.75 <= res["nc"]["cobertura_80"] <= 0.85)}
        res["nc"]["puerta"]["pasa"] = all(res["nc"]["puerta"].values())
        # IM
        e = im[im["anio"].isin(dec) & im["IM"].notna() & im["delta_net_real_equipo"].notna()]
        res["im"]["fichajes_decision"] = int(len(e)); res["im"]["equipos"] = int(e[["liga_d", "team_d", "corte"]].drop_duplicates().shape[0])
        rng = np.random.default_rng(sem)
        rho = spearmanr(e["IM"], e["delta_net_real_equipo"]).correlation; rho_b = spearmanr(e["IM_aditivo"], e["delta_net_real_equipo"]).correlation
        bs = []; bsd = []
        for _ in range(min(B, 1000)):
            ii = rng.integers(0, len(e), len(e)); x = e.iloc[ii]
            r1 = spearmanr(x["IM"], x["delta_net_real_equipo"]).correlation; r2 = spearmanr(x["IM_aditivo"], x["delta_net_real_equipo"]).correlation
            bs.append(r1); bsd.append(r1 - r2)
        res["im"]["monotonia"] = {"spearman_im": float(rho), "ic95": [float(np.quantile(bs, .025)), float(np.quantile(bs, .975))], "spearman_aditivo": float(rho_b),
                                  "ic95_diferencia": [float(np.quantile(bsd, .025)), float(np.quantile(bsd, .975))]}
        res["im"]["calibracion"] = examen_calibracion(e, "IM", "pct_real_equipo", float(crit["nc_calibracion_deciles_tolerancia"]))
        # cobertura de IM: el ΔNet realizado del equipo frente al rango de Δ̂Net del fichaje (en pts/100)
        res["im"]["cobertura_80_delta"] = cobertura(e, "delta_net_p10", "delta_net_p90", "delta_net_real_equipo")
        # nivel de paquete (equipo): el ΔNet realizado existe por EQUIPO, no por fichaje; IM del paquete = percentil de la suma de
        # los Δ̂Net de las altas del equipo entre los paquetes del grupo (cortes ≤ t); percentil realizado del ΔNet del equipo
        paq = e.groupby(["anio", "corte", "liga_d", "team_d", "grupo_im"]).agg(delta_paquete=("delta_net", "sum"), aditivo_paquete=("aditivo_b", "sum"),
                                                                              n_altas=("persona_id", "size"), delta_real=("delta_net_real_equipo", "first")).reset_index()
        paq["IM_paquete"] = np.nan; paq["IM_paquete_aditivo"] = np.nan; paq["pct_real"] = np.nan
        for a in dec:
            for g in paq["grupo_im"].unique():
                prev = paq[(paq["anio"] <= a) & (paq["grupo_im"] == g)]
                sel = (paq["anio"] == a) & (paq["grupo_im"] == g)
                if len(prev) < 30:
                    continue
                Fp = Empirica(prev["delta_paquete"]); Fa = Empirica(prev["aditivo_paquete"]); Fr = Empirica(prev["delta_real"])
                paq.loc[sel, "IM_paquete"] = 100 * Fp(paq.loc[sel, "delta_paquete"]); paq.loc[sel, "IM_paquete_aditivo"] = 100 * Fa(paq.loc[sel, "aditivo_paquete"])
                paq.loc[sel, "pct_real"] = 100 * Fr(paq.loc[sel, "delta_real"])
        pq = paq[paq["IM_paquete"].notna()]
        rp = spearmanr(pq["IM_paquete"], pq["delta_real"]).correlation; rpa = spearmanr(pq["IM_paquete_aditivo"], pq["delta_real"]).correlation
        bsp = []; bspd = []
        for _ in range(min(B, 1000)):
            ii = rng.integers(0, len(pq), len(pq)); x = pq.iloc[ii]
            r1 = spearmanr(x["IM_paquete"], x["delta_real"]).correlation; r2 = spearmanr(x["IM_paquete_aditivo"], x["delta_real"]).correlation
            bsp.append(r1); bspd.append(r1 - r2)
        res["im"]["paquete"] = {"equipos": int(len(pq)), "altas_media": float(pq["n_altas"].mean()),
                                "monotonia": {"spearman_im": float(rp), "ic95": [float(np.quantile(bsp, .025)), float(np.quantile(bsp, .975))], "spearman_aditivo": float(rpa),
                                              "ic95_diferencia": [float(np.quantile(bspd, .025)), float(np.quantile(bspd, .975))]},
                                "calibracion": examen_calibracion(pq, "IM_paquete", "pct_real", float(crit["nc_calibracion_deciles_tolerancia"]))}
        pq.round(3).to_csv(out / "im_paquetes.csv.gz", index=False)
        # [POST HOC, diagnóstico] contraparte realizada POR FICHAJE: Net on/off ajustado del jugador en el equipo de destino (t+1)
        rr = pd.read_csv(C.RAIZ / cfg["insumos"]["roles"], usecols=["liga", "temporada", "team_id", "persona_id", "net_rtg_aj_onoff", "min_total"],
                         dtype={"team_id": str}, low_memory=False).rename(columns={"liga": "liga_d", "team_id": "team_d", "temporada": "temporada_d"})
        e2 = im[im["anio"].isin(dec) & im["IM"].notna()].copy()
        e2["temporada_d"] = e2["anio"].map(lambda a: f"{a + 1}-{str(a + 2)[-2:]}")
        e2 = e2.merge(rr, on=["liga_d", "team_d", "temporada_d", "persona_id"], how="left")
        e2 = e2[e2["net_rtg_aj_onoff"].notna() & (e2["min_total"] >= 300)].copy()
        e2["pct_onoff"] = e2.groupby("grupo_im")["net_rtg_aj_onoff"].rank(pct=True) * 100
        ro = spearmanr(e2["IM"], e2["net_rtg_aj_onoff"]).correlation; roa = spearmanr(e2["IM_aditivo"], e2["net_rtg_aj_onoff"]).correlation
        bso = []; bsod = []
        for _ in range(min(B, 1000)):
            ii = rng.integers(0, len(e2), len(e2)); x = e2.iloc[ii]
            r1 = spearmanr(x["IM"], x["net_rtg_aj_onoff"]).correlation; r2 = spearmanr(x["IM_aditivo"], x["net_rtg_aj_onoff"]).correlation
            bso.append(r1); bsod.append(r1 - r2)
        res["im"]["onoff_fichaje"] = {"fichajes": int(len(e2)), "definicion": "Net on/off ajustado del fichaje en el destino (≥ 300 min); percentil entre los fichajes del grupo",
                                      "monotonia": {"spearman_im": float(ro), "ic95": [float(np.quantile(bso, .025)), float(np.quantile(bso, .975))], "spearman_aditivo": float(roa),
                                                    "ic95_diferencia": [float(np.quantile(bsod, .025)), float(np.quantile(bsod, .975))]},
                                      "calibracion": examen_calibracion(e2, "IM", "pct_onoff", float(crit["nc_calibracion_deciles_tolerancia"]))}
        res["im"]["puerta"] = {"monotonia_no_peor_que_aditivo": bool(rho >= rho_b), "ic95_excluye_0": bool(res["im"]["monotonia"]["ic95"][0] > 0),
                               "calibracion_por_fichaje": res["im"]["calibracion"]["pasa"],
                               "calibracion_por_paquete": res["im"]["paquete"]["calibracion"]["pasa"],
                               "nota": "el ΔNet realizado es del equipo: la calibración por fichaje compara objetos distintos (POST HOC: se evalúa también por paquete)"}
        res["im"]["puerta"]["pasa_literal"] = bool(res["im"]["puerta"]["monotonia_no_peor_que_aditivo"] and res["im"]["puerta"]["ic95_excluye_0"] and res["im"]["puerta"]["calibracion_por_fichaje"])
        res["im"]["puerta"]["pasa_por_paquete"] = bool(res["im"]["puerta"]["monotonia_no_peor_que_aditivo"] and res["im"]["puerta"]["ic95_excluye_0"] and res["im"]["puerta"]["calibracion_por_paquete"])
        res["im"]["puerta"]["pasa"] = res["im"]["puerta"]["pasa_literal"]
        # criterio redefinido (decisión b del CEO), prerregistrado en criterios.f5.im_onoff
        if "comp_pts100" in im:
            res_oo, im_oo = examen_im_onoff(im, cfg, cortes, dec, B, sem)
            res["im"]["criterio_redefinido_onoff"] = res_oo
            im_oo.round(3).to_csv(out / "im_examen.csv.gz", index=False)
        else:
            res_oo = None
        estado_im = res_oo["estado_im"] if res_oo else "en_examen"
        res["puerta_11_5"] = {"nc": res["nc"]["puerta"]["pasa"], "im_literal": res["im"]["puerta"]["pasa"],
                              "im_redefinido_onoff": res_oo["puerta_im_onoff"] if res_oo else None, "estado_im": estado_im,
                              "pasa": res["nc"]["puerta"]["pasa"] and res["im"]["puerta"]["pasa"],
                              "anti_manipulacion": "recalcular con el examen limpio 2025-26 → 2026-27 antes de comunicar cifras (temporada en curso)"}
        res["tiempo_s"] = round(time.time() - t0)
        (out / "resumen_anclas.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    if progreso:
        progreso(f"  F5 examen: NC {res['nc']['puerta']} · IM {res['im']['puerta']} · {res['tiempo_s']} s", flush=True)
    return res


# =============================================================================================== producto
def exportar(cfg: dict, progreso=print) -> dict:
    """Referencias versionadas para producción: F_ref (liga × pos3, tres últimas temporadas) de la última temporada con datos y
    F_mov por grupo de liga con todos los fichajes del examen (Δ̂Net calibrado), más la calibración c por grupo."""
    v32, S, SI = _v()
    out = dir_salida(cfg)
    roles = SI._leer_roles_temporada()
    temp = sorted(roles["temporada"].unique())[-1]
    gm_de = {l: S.minutos_partido(l) for l in roles["liga"].unique()}
    Fref = referencias_nc(cfg, roles, temp, gm_de)
    ref = {"temporada": temp, "temporadas": int(cfg["f5"]["nivel_cerno"]["referencia"]["temporadas"]), "ponderacion": "minutos",
           "F_ref": {f"{l}|{p or 'todas'}": F.exportable() for (l, p), F in Fref.items() if F.n >= 30}}
    (out / f"referencias_nc_{temp}.json").write_text(json.dumps(ref, indent=1, ensure_ascii=False), encoding="utf-8")
    im = pd.read_csv(out / "im_examen.csv.gz") if (out / "im_examen.csv.gz").exists() else None
    mov = {"generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "F_mov": {}, "fichajes": 0}
    if im is not None:
        cal = json.loads((EQ.dir_salida(cfg) / "calibracion.json").read_text(encoding="utf-8"))
        for g, d in im.groupby("grupo_im"):
            mov["F_mov"][g] = Empirica(d["delta_net"]).exportable()
            mov["F_mov"][g]["F_real_equipo"] = Empirica(d["delta_net_real_equipo"].dropna().drop_duplicates()).exportable()
        mov["fichajes"] = int(len(im)); mov["c_por_grupo_f4"] = {g: v["prediccion"]["c"] for g, v in cal["por_grupo"].items()}
        mov["c_conjunto_f4"] = cal["conjunto"]["prediccion"]["c"]
    (out / "referencia_im.json").write_text(json.dumps(mov, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    res = json.loads((out / "resumen_anclas.json").read_text(encoding="utf-8")) if (out / "resumen_anclas.json").exists() else {}
    estado_im = res.get("puerta_11_5", {}).get("estado_im", "en_examen")
    doc = {"version": cfg["version"], "generado": mov["generado"], "referencias_nc": f"referencias_nc_{temp}.json", "referencia_im": "referencia_im.json",
           "grupos_nc": len(ref["F_ref"]), "grupos_im": list(mov["F_mov"]),
           "estado": {"nivel_cerno": "referente" if res.get("nc", {}).get("puerta", {}).get("pasa") else "en_examen", "impacto": estado_im,
                      "impacto_criterio": "criterios.f5.im_onoff (decisión b del CEO, 05-11-2026); el literal §11.5 no se cumple por construcción",
                      "complemento_companeros": "subíndice aparte (no se adopta dentro de IM: no mejora el Spearman con IC95)"}}
    (out / "F5_anclas.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    if progreso:
        progreso(f"  F5 producto: F_ref {len(ref['F_ref'])} liga×puesto ({temp}) · F_mov {list(mov['F_mov'])} con {mov['fichajes']} fichajes", flush=True)
    return doc


def _empirica_de(exp: dict) -> Empirica | None:
    if not exp or exp.get("n", 0) == 0:
        return None
    F = Empirica([]); q = exp["cuantiles"]
    F.F = np.array([float(k) for k in q]); F.x = np.array(list(q.values()), float); F.n = exp["n"]
    return F


def nivel_cerno(res_sim: dict, liga_d: str, pos3: str | None, ref: dict, n: int = 400, semilla: int = 0) -> dict:
    """NC₁ (y rango) a partir de la salida del simulador v3.x (`res["contribucion"]` o `res["C"]` con cuantiles) y las
    referencias versionadas (`referencias_nc_<t>.json`). Devuelve también el percentil de la mediana predictiva."""
    F = _empirica_de(ref["F_ref"].get(f"{liga_d}|{pos3}")) or _empirica_de(ref["F_ref"].get(f"{liga_d}|todas"))
    if F is None:
        return {"NC": np.nan, "motivo": "sin población de referencia"}
    c = res_sim.get("contribucion") or res_sim.get("C") or {}
    fila = pd.Series({f"C_{k}": c.get(k if k != "pred" else "mediana", c.get(k, np.nan)) for k, _ in NIVELES_Q})
    m = muestras_predictivas(fila, "C", n, np.random.default_rng(semilla))
    nc, lo, hi = percentil_esperado(F, m)
    return {"NC": nc, "NC_lo80": lo, "NC_hi80": hi, "pct_mediana": float(100 * F(np.nanmedian(m))), "n_ref": F.n}


def impacto(delta: dict, liga_d: str, cfg: dict, ref_im: dict, n: int = 300, semilla: int = 0) -> dict:
    """IM (y rango) a partir de la salida de `equipo.Equipo.delta` (Δ̂Net calibrado con lo80/hi80 y sd) y F_mov del grupo."""
    g = grupo_im(cfg, liga_d)
    F = _empirica_de((ref_im.get("F_mov") or {}).get(g))
    if F is None:
        return {"IM": np.nan, "motivo": f"sin fichajes de referencia en {g}"}
    rng = np.random.default_rng(semilla)
    sd = float(np.sqrt(delta.get("sd_mc", 0.0) ** 2 + delta.get("s0", 0.0) ** 2))
    m = delta["delta_net"] + rng.normal(0, max(sd, 1e-6), n)
    im, lo, hi = percentil_esperado(F, m)
    return {"IM": im, "IM_lo80": lo, "IM_hi80": hi, "grupo": g, "n_mov": F.n, "delta_net": delta["delta_net"]}
