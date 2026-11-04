"""F3 · Función de conjunto (capa 3; encargo §8, CONDICIONAL). Sobre F1 + F2, congelando β y M_r:

    y_s = [F1] + [F2: Σφ_A − Σφ_B] + g(S_A) − g(S_B) + ε_s,     g(S) = ρ( Σ_{i∈S} ϕ(z_i) )

* z_i: los rasgos estandarizados del perfil (los mismos de F2; sin perfil → 0). ϕ: ℝ^p → ℝ^h (una capa oculta), suma sobre
  los cinco jugadores (invariante a permutaciones), ρ: ℝ^h → ℝ (una capa oculta). Pequeña y muy regularizada (AdamW con
  decaimiento de pesos), 5 semillas promediadas. Pérdida: error cuadrático ponderado por posesiones sobre el RESIDUO de
  F1 + F2.
* Examen §11.3 (puerta dura): en el corte t se ajusta con los tramos ≤ t (perfiles de corte_<t>, β y M del corte) y se
  evalúa en los tramos de t+1 con algún QUINTETO NO VISTO (conjunto de 5 personas que no aparece en ningún tramo ≤ t):
  cociente RMSE(F1+F2+F3)/RMSE(F1+F2) con IC95 por bootstrap de partidos; se publica sólo si el IC95 superior < 1 en los
  tres cortes de decisión. Si no, ablación negativa.
Salidas: data/modelos/v4_0/conjunto/.
"""
from __future__ import annotations

import json
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from . import examen_f1 as EX
from . import rapm as RP
from . import sinergia as SG


def dir_salida(cfg: dict) -> Path:
    d = C.RAIZ / cfg["f3"]["salida"]
    d.mkdir(parents=True, exist_ok=True)
    return d


# =============================================================================================== residuo de F1 + F2
def phi_tramos(tr: pd.DataFrame, R: SG.Rasgos, Mr: np.ndarray) -> np.ndarray:
    """Σφ_A − Σφ_B por tramo con M_r (las claves de `tr` deben ser las de perfil)."""
    m = Mr[np.triu_indices(R.p)]
    out = np.zeros(len(tr))
    for idx, U in SG.rasgos_tramos(tr, R):
        out[idx] = U @ m
    return out


def claves_perfil(tr: pd.DataFrame, temporada: str) -> pd.DataFrame:
    """Mismas filas con las claves persona|temporada (para usar el perfil de esa temporada ≤ t)."""
    t = tr.copy()
    t["A"] = t["A"].map(lambda q: tuple(k.rsplit("|", 1)[0] + "|" + temporada for k in q))
    t["B"] = t["B"].map(lambda q: tuple(k.rsplit("|", 1)[0] + "|" + temporada for k in q))
    return t


def indices_z(tr: pd.DataFrame, R: SG.Rasgos) -> np.ndarray:
    """(n × 10) índices en R.Z (+ fila 0 extra para quien no tiene perfil): A en 0..4, B en 5..9."""
    cero = len(R.idx)
    g = R.idx.get
    return np.array([[g(k, cero) for k in q] for q in (tuple(a) + tuple(b) for a, b in zip(tr["A"], tr["B"]))], dtype=np.int64)


def quintetos(tr: pd.DataFrame) -> set:
    """Conjuntos de 5 personas (sin temporada) de los quintetos de `tr`."""
    out = set()
    for col in ("A", "B"):
        for q in tr[col]:
            out.add(frozenset(k.rsplit("|", 1)[0] for k in q))
    return out


def no_vistos(tr1: pd.DataFrame, vistos: set) -> tuple[np.ndarray, np.ndarray]:
    """Por tramo de t+1: (algún quinteto no visto, los dos no vistos)."""
    a = np.array([frozenset(k.rsplit("|", 1)[0] for k in q) not in vistos for q in tr1["A"]])
    b = np.array([frozenset(k.rsplit("|", 1)[0] for k in q) not in vistos for q in tr1["B"]])
    return a | b, a & b


# =============================================================================================== red deep sets
class ConjuntoNet:
    """g(S) = ρ(Σ ϕ(z)). Entrenamiento con AdamW, promedio de `semillas` redes. Predice g(S_A) − g(S_B)."""

    def __init__(self, Z: np.ndarray, cfg: dict):
        import torch
        f3 = cfg["f3"]
        self.cfg = f3
        self.Z = torch.tensor(np.vstack([Z, np.zeros((1, Z.shape[1]))]), dtype=torch.float32)   # última fila: sin perfil
        self.p = Z.shape[1]
        self.redes = []

    def _red(self, semilla: int):
        import torch
        from torch import nn
        torch.manual_seed(semilla)
        h, hr = int(self.cfg["oculta_phi"]), int(self.cfg["oculta_rho"])
        phi = nn.Sequential(nn.Linear(self.p, h), nn.ReLU(), nn.Linear(h, h))
        if self.cfg.get("rho_lineal", False):             # ablación: g(S) = Σ_i h(z_i), aditiva por jugador (sin estructura de conjunto)
            rho = nn.Linear(h, 1)
        else:
            rho = nn.Sequential(nn.Linear(h, hr), nn.ReLU(), nn.Linear(hr, 1))
        return nn.ModuleDict({"phi": phi, "rho": rho})

    def _g(self, red, I):
        """I: (n × 10) índices → g(A) − g(B), (n,)."""
        Zb = self.Z[I]                                        # n × 10 × p
        H = red["phi"](Zb)                                    # n × 10 × h
        gA = red["rho"](H[:, :5].sum(1)).squeeze(-1)
        gB = red["rho"](H[:, 5:].sum(1)).squeeze(-1)
        return gA - gB

    def ajustar(self, I: np.ndarray, r: np.ndarray, w: np.ndarray, semilla_base: int, progreso=None) -> dict:
        import torch
        It = torch.tensor(I); rt = torch.tensor(r, dtype=torch.float32); wt = torch.tensor(w / w.mean(), dtype=torch.float32)
        n = len(I); lote = int(self.cfg["lote"]); pasos = int(self.cfg["pasos"])
        self.redes = []; curvas = []
        for s in range(int(self.cfg["semillas"])):
            red = self._red(semilla_base + s)
            opt = torch.optim.AdamW(red.parameters(), lr=float(self.cfg["lr"]), weight_decay=float(self.cfg["decaimiento_pesos"]))
            gen = torch.Generator().manual_seed(semilla_base + 1000 + s)
            curva = []
            for paso in range(pasos):
                ii = torch.randint(0, n, (lote,), generator=gen)
                pred = self._g(red, It[ii])
                loss = (wt[ii] * (rt[ii] - pred) ** 2).mean()
                opt.zero_grad(); loss.backward(); opt.step()
                if paso % 250 == 0 or paso == pasos - 1:
                    curva.append(float(loss))
            red.eval(); self.redes.append(red); curvas.append(curva)
            if progreso:
                progreso(f"    semilla {s}: pérdida {curva[0]:.4f} → {curva[-1]:.4f}", flush=True)
        return {"curvas": curvas}

    def predecir(self, I: np.ndarray, por_semilla: bool = False) -> np.ndarray:
        import torch
        It = torch.tensor(I)
        out = []
        with torch.no_grad():
            for red in self.redes:
                out.append(np.concatenate([self._g(red, It[a:a + 65536]).numpy() for a in range(0, len(It), 65536)]))
        out = np.array(out)
        return out if por_semilla else out.mean(0)

    def estado(self) -> list:
        return [{k: v.numpy() for k, v in red.state_dict().items()} for red in self.redes]

    def cargar(self, estado: list, semilla_base: int = 0) -> "ConjuntoNet":
        import torch
        self.redes = []
        for s, sd in enumerate(estado):
            red = self._red(semilla_base + s)
            red.load_state_dict({k: torch.tensor(v) for k, v in sd.items()}); red.eval()
            self.redes.append(red)
        return self


def diagnostico_g(cfg: dict, a: int, progreso=print) -> dict:
    """[POST HOC, lectura] ¿Qué mira g? Para el corte a: g(S) de los quintetos de t+1 (perfiles de t) frente a rasgos
    agregados del quinteto (suma, media, máximo de cada rasgo z; nº de jugadores sin perfil). Correlaciones y un ridge de
    g sobre esos agregados (R²: cuánto de g es explicable por agregados simples)."""
    from sklearn.linear_model import RidgeCV
    tr_all = RP.tramos(cfg, None, progreso=None)
    aj = EX.ajuste_corte(cfg, a, tr_all, "gbm", progreso=None)
    R = SG.Rasgos(aj["T"], cfg)
    temp_t = f"{a}-{str(a + 1)[-2:]}"
    tr1 = claves_perfil(tr_all[tr_all["anio"] == a + 1].reset_index(drop=True), temp_t)
    estado = pickle.loads((dir_salida(cfg) / "examen" / f"red_corte_{a}.pkl").read_bytes())
    red = ConjuntoNet(R.Z, cfg).cargar(estado, int(cfg["semilla"]))
    # quintetos únicos de t+1 (lado A y B), g(S) = red con B = quinteto vacío (todo sin perfil → g(∅) constante)
    Q = pd.unique(pd.Series(list(tr1["A"]) + list(tr1["B"])))
    I = np.array([[R.idx.get(k, len(R.idx)) for k in q] + [len(R.idx)] * 5 for q in Q])
    g = red.predecir(I)                                   # g(S) − g(∅)
    Zq = np.vstack([R.Z, np.zeros((1, R.p))])[I[:, :5]]     # n × 5 × p
    sin_perfil = (I[:, :5] == len(R.idx)).sum(1)
    agg = {f"suma_{c}": Zq[:, :, j].sum(1) for j, c in enumerate(R.columnas)}
    agg.update({f"max_{c}": Zq[:, :, j].max(1) for j, c in enumerate(R.columnas)})
    agg["sin_perfil"] = sin_perfil.astype(float)
    A = pd.DataFrame(agg)
    cor = A.corrwith(pd.Series(g)).sort_values(key=np.abs, ascending=False)
    X = A.to_numpy(float); X = (X - X.mean(0)) / np.where(X.std(0) > 0, X.std(0), 1)
    rd = RidgeCV(alphas=[0.1, 1, 10, 100]).fit(X, g)
    out = {"corte": a, "quintetos": int(len(Q)), "sd_g": float(np.std(g)), "r2_agregados_lineales": float(rd.score(X, g)),
           "correlaciones_mayores": {k: float(v) for k, v in cor.head(15).items()},
           "g_por_sin_perfil": {int(k): float(np.mean(g[sin_perfil == k])) for k in np.unique(sin_perfil)}}
    (dir_salida(cfg) / "examen" / f"diagnostico_g_{a}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    if progreso:
        progreso(f"  diagnóstico g corte {a}: sd {out['sd_g']:.3f} · R² agregados {out['r2_agregados_lineales']:.3f} · {list(out['correlaciones_mayores'].items())[:6]}", flush=True)
    return out


# =============================================================================================== examen §11.3
def _rmse_pond(e: np.ndarray, w: np.ndarray) -> float:
    return float(np.sqrt(np.sum(w * e ** 2) / np.sum(w)))


def _cociente_bootstrap(e0, e1, w, grupos, B, semilla) -> tuple[float, list[float]]:
    """Cociente RMSE(e1)/RMSE(e0) y su IC95 por bootstrap de grupos (partidos)."""
    g, inv = np.unique(grupos, return_inverse=True)
    s0 = np.bincount(inv, w * e0 ** 2); s1 = np.bincount(inv, w * e1 ** 2); sw = np.bincount(inv, w)
    rng = np.random.default_rng(semilla)
    coc = []
    for _ in range(B):
        ii = rng.integers(0, len(g), len(g))
        coc.append(np.sqrt(s1[ii].sum() / s0[ii].sum()))
    return float(np.sqrt(s1.sum() / s0.sum())), [float(np.quantile(coc, 0.025)), float(np.quantile(coc, 0.975))]


def examen_corte(cfg: dict, a: int, tr_all: pd.DataFrame, progreso=print) -> dict:
    t0 = time.time()
    aj = EX.ajuste_corte(cfg, a, tr_all, "gbm", progreso=None)
    R = SG.Rasgos(aj["T"], cfg)
    ex2 = json.loads((SG.dir_salida(cfg) / "examen" / "resumen_examen_f2a.json").read_text(encoding="utf-8"))
    rango = ex2["decisiones"]["rango"]
    Mr, _ = SG.truncar(np.load(SG.dir_salida(cfg) / "examen" / f"M_corte_{a}.npy"), None if rango == "completa" else int(rango))
    temp_t = f"{a}-{str(a + 1)[-2:]}"
    # ajuste: tramos ≤ a, residuo de F1 + F2
    tr = tr_all[tr_all["anio"] <= a].reset_index(drop=True)
    mu, _ = SG.mu_f1(cfg, aj, tr)
    r = tr["y"].to_numpy(float) - mu - phi_tramos(tr, R, Mr)
    w = tr["poss"].to_numpy(float)
    I = indices_z(tr, R)
    red = ConjuntoNet(R.Z, cfg)
    aj3 = red.ajustar(I, r, w, int(cfg["semilla"]), progreso)
    pred_in = red.predecir(I)
    out = {"corte": a, "tramos_ajuste": int(len(tr)), "rango_f2": rango, "p": R.p, "curvas": aj3["curvas"],
           "rmse_en_muestra": {"f1_f2": _rmse_pond(r, w), "f1_f2_f3": _rmse_pond(r - pred_in, w)}}
    # examen: tramos de t+1, perfiles de la temporada t, quintetos no vistos
    tr1 = tr_all[tr_all["anio"] == a + 1].reset_index(drop=True)
    if tr1.empty:
        out["tiempo_s"] = round(time.time() - t0)
        return out, red
    mu1, _ = SG.mu_f1(cfg, aj, tr1)
    tr1_t = claves_perfil(tr1, temp_t)
    phi1 = phi_tramos(tr1_t, R, Mr)
    y1 = tr1["y"].to_numpy(float); w1 = tr1["poss"].to_numpy(float)
    e_f1 = y1 - mu1; e_f12 = e_f1 - phi1
    I1 = indices_z(tr1_t, R)
    g1 = red.predecir(I1, por_semilla=True)
    e_f123 = e_f12 - g1.mean(0)
    alguno, ambos = no_vistos(tr1, quintetos(tr))
    con_perfil = (I1 < len(R.idx)).mean(1)
    partido = (tr1["liga"] + "|" + tr1["temporada"] + "|" + tr1["game_id"].astype(str)).to_numpy()
    B, sem = int(cfg["criterios"]["comunes"]["bootstrap"]), int(cfg["criterios"]["comunes"]["semilla_bootstrap"])
    out["tramos_t1"] = int(len(tr1)); out["fraccion_quinteto_no_visto"] = float(alguno.mean()); out["fraccion_ambos_no_vistos"] = float(ambos.mean())
    out["fraccion_puestos_con_perfil_t1"] = float(con_perfil.mean())
    out["sd_g_t1"] = float(np.std(g1.mean(0))); out["sd_entre_semillas_t1"] = float(np.mean(np.std(g1, 0)))
    out["corr_g_residuo_t1"] = float(np.corrcoef(g1.mean(0), e_f12)[0, 1]) if np.std(g1.mean(0)) > 0 else 0.0
    out["conjuntos"] = {}
    for nombre, sel in (("quinteto_no_visto", alguno), ("ambos_no_vistos", ambos), ("todos", np.ones(len(tr1), bool))):
        if sel.sum() == 0:
            continue
        c, ic = _cociente_bootstrap(e_f12[sel], e_f123[sel], w1[sel], partido[sel], B, sem)
        c2, ic2 = _cociente_bootstrap(e_f1[sel], e_f12[sel], w1[sel], partido[sel], B, sem)
        out["conjuntos"][nombre] = {"tramos": int(sel.sum()), "rmse_f1": _rmse_pond(e_f1[sel], w1[sel]), "rmse_f1_f2": _rmse_pond(e_f12[sel], w1[sel]),
                                    "rmse_f1_f2_f3": _rmse_pond(e_f123[sel], w1[sel]), "cociente_f3": c, "ic95_f3": ic,
                                    "cociente_f2_sobre_f1": c2, "ic95_f2_sobre_f1": ic2,
                                    "por_semilla": [float(_rmse_pond(e_f12[sel] - g1[k][sel], w1[sel])) for k in range(len(g1))]}
    out["tiempo_s"] = round(time.time() - t0)
    if progreso:
        q = out["conjuntos"]["quinteto_no_visto"]
        progreso(f"    corte {a}: tramos t+1 {len(tr1)} · no vistos {alguno.mean():.1%} · RMSE F1+F2 {q['rmse_f1_f2']:.3f} → F3 {q['rmse_f1_f2_f3']:.3f} · "
                 f"cociente {q['cociente_f3']:.5f} {np.round(q['ic95_f3'], 5).tolist()} · sd g {out['sd_g_t1']:.3f} · {out['tiempo_s']} s", flush=True)
    return out, red


def ablacion_aditiva(cfg: dict, progreso=print) -> dict:
    """Ablación [POST HOC, diagnóstica]: ¿lo que gana F3 es estructura de quinteto o una corrección aditiva por jugador que
    F1 no captó? Misma red con ρ lineal (g(S) = Σ_i h(z_i)) en cada corte; se compara su cociente con el de la red completa."""
    cfg_a = C.con(cfg, **{"f3.rho_lineal": True})
    tr_all = RP.tramos(cfg, None, progreso=None)
    out_dir = dir_salida(cfg) / "examen"
    base = json.loads((out_dir / "resumen_examen_f3.json").read_text(encoding="utf-8"))
    res = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "cortes": {}}
    for a in [int(x) for x in cfg["criterios"]["comunes"]["cortes"]]:
        r, _ = examen_corte(cfg_a, a, tr_all, progreso)
        q = r["conjuntos"]["quinteto_no_visto"]; q0 = base["cortes"][str(a)]["conjuntos"]["quinteto_no_visto"]
        res["cortes"][a] = {"aditiva": {"cociente": q["cociente_f3"], "ic95": q["ic95_f3"], "rmse": q["rmse_f1_f2_f3"], "sd_g": r["sd_g_t1"]},
                            "completa": {"cociente": q0["cociente_f3"], "ic95": q0["ic95_f3"], "rmse": q0["rmse_f1_f2_f3"], "sd_g": base["cortes"][str(a)]["sd_g_t1"]},
                            "rmse_f1_f2": q["rmse_f1_f2"]}
        if progreso:
            progreso(f"    ablación corte {a}: aditiva {q['cociente_f3']:.5f} {np.round(q['ic95_f3'], 5).tolist()} · completa {q0['cociente_f3']:.5f}", flush=True)
    (out_dir / "ablacion_aditiva_f3.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    return res


def main(cfg: dict, progreso=print) -> dict:
    from bbfit.registro import experimento
    t0 = time.time()
    out_dir = dir_salida(cfg) / "examen"; out_dir.mkdir(parents=True, exist_ok=True)
    tr_all = RP.tramos(cfg, None, progreso)
    cortes = [int(a) for a in cfg["criterios"]["comunes"]["cortes"]]
    dec = [int(a) for a in cfg["criterios"]["comunes"]["cortes_decision"]]
    umbral = float(cfg["criterios"]["f3"]["cociente_rmse_quintetos_no_vistos_ic95_superior_menor_que"])
    resultado = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "cortes": {}}
    with experimento(cfg["mlflow"], "F3_examen", params={"cortes": cortes, **{k: v for k, v in cfg["f3"].items() if not isinstance(v, (dict, list))}}):
        for a in cortes:
            r, red = examen_corte(cfg, a, tr_all, progreso)
            resultado["cortes"][a] = r
            (out_dir / f"red_corte_{a}.pkl").write_bytes(pickle.dumps(red.estado()))
        q = [resultado["cortes"][a]["conjuntos"]["quinteto_no_visto"] for a in dec if "conjuntos" in resultado["cortes"][a]]
        resultado["puerta_11_3"] = {"cortes": dec, "cociente_por_corte": [x["cociente_f3"] for x in q], "ic95_por_corte": [x["ic95_f3"] for x in q],
                                    "umbral_ic95_superior": umbral, "pasa_en_todos": bool(all(x["ic95_f3"][1] < umbral for x in q)),
                                    "pasa_en_alguno": bool(any(x["ic95_f3"][1] < umbral for x in q))}
        resultado["decisiones"] = {"publicar_f3": resultado["puerta_11_3"]["pasa_en_todos"] if cfg["f3"].get("publicar_solo_si_mejora", True) else True,
                                   "regla": "§11.3: IC95 superior del cociente RMSE(F1+F2+F3)/RMSE(F1+F2) en quintetos no vistos < 1 en los tres cortes de decisión"}
        resultado["tiempo_s"] = round(time.time() - t0)
        (out_dir / "resumen_examen_f3.json").write_text(json.dumps(resultado, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    if progreso:
        progreso(f"  examen F3: {resultado['puerta_11_3']} · publicar {resultado['decisiones']['publicar_f3']} · {resultado['tiempo_s']} s", flush=True)
    return resultado


# =============================================================================================== producto (sólo si pasa)
def exportar(cfg: dict, progreso=print) -> dict:
    """Ajuste con todas las temporadas sobre el residuo de F1 + F2 producto. Sólo si el examen §11.3 lo autoriza."""
    from bbfit.registro import experimento
    from .examen_f1 import perfiles_completo
    t0 = time.time()
    out = dir_salida(cfg)
    ex = json.loads((out / "examen" / "resumen_examen_f3.json").read_text(encoding="utf-8"))
    if not ex["decisiones"]["publicar_f3"]:
        doc = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "publicado": False,
               "motivo": "no supera la puerta §11.3; ablación negativa (ver examen/resumen_examen_f3.json)"}
        (out / "F3_conjunto.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
        if progreso:
            progreso("  F3 producto: NO se publica (puerta §11.3)", flush=True)
        return doc
    tr = RP.tramos(cfg, None, progreso)
    temps = sorted(tr["temporada"].unique())
    T = RP.tabla_prior(perfiles_completo(cfg, temps), cfg)
    tipo = cfg["f1"]["prior"].get("elegido") or json.loads((RP.dir_salida(cfg) / "examen" / "resumen_examen.json").read_text())["decisiones"]["prior"]["elegido"]
    pr = cfg["f1"].get("producto") or {}
    cfg_p = C.con(cfg, **{"f1.bayes_empirico.tau_rejilla": pr.get("tau_rejilla", cfg["f1"]["bayes_empirico"]["tau_rejilla"]),
                          "f1.prior.ridge_alpha_rejilla": pr.get("ridge_alpha_rejilla", cfg["f1"]["prior"]["ridge_alpha_rejilla"])}) if pr else cfg
    res = pickle.loads((C.RAIZ / "experimentos" / "v4_0" / f"producto_f1_net_{tipo}_{RP.huella_ajuste(cfg_p)}.pkl").read_bytes())
    D = RP.construir_diseno(tr, "net")
    tb = RP.tabla_beta(res, D).merge(RP.ligas_jugador(tr), on="clave", how="left")
    aj = {"corte": None, "D": D, "res": res, "T": T, "tb": tb}
    R = SG.Rasgos(T, cfg)
    Mr = np.load(SG.dir_salida(cfg) / "M_rango.npy")
    mu, _ = SG.mu_f1(cfg, aj, tr)
    r = tr["y"].to_numpy(float) - mu - phi_tramos(tr, R, Mr)
    w = tr["poss"].to_numpy(float)
    with experimento(cfg["mlflow"], "F3_producto", params={"tramos": len(tr)}):
        red = ConjuntoNet(R.Z, cfg)
        aj3 = red.ajustar(indices_z(tr, R), r, w, int(cfg["semilla"]), progreso)
        (out / "redes.pkl").write_bytes(pickle.dumps({"estado": red.estado(), "rasgos": R.exportable(), "cfg_f3": cfg["f3"]}))
        doc = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "publicado": True, "tramos": int(len(tr)),
               "curvas": aj3["curvas"], "formula": "g(S) = ρ(Σ_i ϕ(z_i)); Δ = g(S_A) − g(S_B) sobre F1 + F2; z sin perfil = 0",
               "tiempo_s": round(time.time() - t0)}
        (out / "F3_conjunto.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    if progreso:
        progreso(f"  F3 producto publicado · {doc['tiempo_s']} s", flush=True)
    return doc
