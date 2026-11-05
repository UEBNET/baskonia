"""F2-B · Efectos dirigidos sobre compañeros (capa 2; encargo §7).

    d_k(X → Y) = m_k(x̃_X, x̃_Y; θ_k) + ruido,   k ∈ {cuota de tiro, eFG%, % asistidas, % en el aro, pts/100}

Datos: data/modelos/interacciones/efectos_<t>.csv.gz (bbmodel.interacciones): para cada pareja de compañeros (X, Y) de un
equipo-temporada, cómo cambian las cinco métricas de Y con X en pista frente a sin X (d_k = con − sin), con los tamaños
muestrales de cada situación. Peso de cada fila: n_ef = 1/(1/n_con + 1/n_sin) con la exposición de la métrica (tiros de
campo, canastas o posesiones). Rasgos: z_X y z_Y (los mismos rasgos estandarizados que la sinergia) y su producto
elemento a elemento (para el ridge; el GBM lo aprende solo). Candidatos ridge | GBM por efecto, elegidos en el corte de
selección. Intervalos del 80 %: cuantiles del residuo fuera de muestra del corte anterior por tramo de n_ef (conformal
con recencia, como A4 de la v3.2); en el primer corte, en muestra (marcado).
Examen (§11.2): por corte t, modelo ≤ t y parejas de t+1 con perfiles de la temporada t: MAE frente a Δ = 0 y Δ = media de
la liga en t (IC95 por bootstrap de equipos-temporada); cobertura del 80 % en [0,75, 0,85]. Se publican sólo los efectos
que pasan. Las cuotas de tiro se renormalizan al 100 % al aplicarlas a un quinteto (F4: `renormalizar_cuotas`).
Salidas: data/modelos/v4_0/sinergia/dirigidos/.
"""
from __future__ import annotations

import json
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from . import rapm as RP
from . import sinergia as SG

EFECTOS = {"d_cuota_tiro": ("fga", "cuota de tiro (%)"), "d_efg": ("fga", "eFG% (puntos)"), "d_pct_asistidas": ("fgm", "% asistidas"),
           "d_pct_aro": ("fga", "% en el aro"), "d_pts100": ("poss", "pts/100")}


def dir_salida(cfg: dict) -> Path:
    d = C.RAIZ / cfg["f2"]["salida"] / "dirigidos"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cargar_interacciones(cfg: dict, temporadas) -> pd.DataFrame:
    """Filas X→Y con claves persona|temporada (crosswalk) y peso efectivo por efecto."""
    from bbfit.datos import persona
    fr = []
    for t in temporadas:
        p = C.ruta(cfg, "interacciones") / f"efectos_{t}.csv.gz"
        if p.exists():
            e = pd.read_csv(p, dtype={"x": str, "y": str, "team_id": str}, low_memory=False)
            e["temporada"] = t
            fr.append(e)
    e = pd.concat(fr, ignore_index=True)
    for col in ("x", "y"):
        e[f"persona_{col}"] = ""
        for liga, g in e.groupby("liga"):
            e.loc[g.index, f"persona_{col}"] = persona(liga, g[col].astype(str)).to_numpy()
        e[f"clave_{col}"] = e[f"persona_{col}"] + "|" + e["temporada"]
    for k, (exp, _) in EFECTOS.items():
        n1, n0 = pd.to_numeric(e[f"{exp}_con"], errors="coerce"), pd.to_numeric(e[f"{exp}_sin"], errors="coerce")
        e[f"w_{k}"] = 1.0 / (1.0 / np.maximum(n1, 1e-9) + 1.0 / np.maximum(n0, 1e-9))
        e[k] = pd.to_numeric(e[k], errors="coerce")
    e["anio"] = e["temporada"].str[:4].astype(int)
    return e


def rasgos_pareja(e: pd.DataFrame, R: SG.Rasgos, temporada_perfil: str | None = None) -> np.ndarray:
    """[z_X, z_Y, z_X ⊙ z_Y] para cada fila; `temporada_perfil` fuerza la temporada del perfil (examen: la t para filas de t+1)."""
    kx = e["clave_x"] if temporada_perfil is None else e["persona_x"] + "|" + temporada_perfil
    ky = e["clave_y"] if temporada_perfil is None else e["persona_y"] + "|" + temporada_perfil
    zx, zy = R.de(list(kx)), R.de(list(ky))
    return np.hstack([zx, zy, zx * zy]), (np.abs(zx).sum(1) > 0) & (np.abs(zy).sum(1) > 0)


class ModeloEfecto:
    def __init__(self, tipo: str, cfg: dict):
        self.tipo, self.cfg = tipo, cfg
        self.modelo, self.media_y = None, 0.0

    def ajustar(self, X, y, w):
        ok = np.isfinite(y) & np.isfinite(w) & (w > 0)
        X, y, w = X[ok], y[ok], w[ok]
        self.media_y = float(np.average(y, weights=w))
        if self.tipo == "ridge":
            from sklearn.linear_model import RidgeCV
            self.modelo = RidgeCV(alphas=[float(a) for a in self.cfg["f2"]["dirigidos"].get("ridge_alpha_rejilla", [1, 10, 100, 1000])]).fit(X, y, sample_weight=w)
        else:
            from sklearn.ensemble import HistGradientBoostingRegressor
            g = self.cfg["f2"]["dirigidos"]["gbm"]
            self.modelo = HistGradientBoostingRegressor(max_iter=int(g["max_iter"]), learning_rate=float(g["learning_rate"]),
                                                        max_depth=int(g["max_depth"]), min_samples_leaf=int(g["min_samples_leaf"]),
                                                        l2_regularization=float(g["l2_regularization"]), random_state=int(self.cfg["semilla"])).fit(X, y, sample_weight=w)
        return self

    def predecir(self, X):
        return self.modelo.predict(X)


def calibracion(res: np.ndarray, w: np.ndarray, bins: int, nivel: float = 0.80) -> dict:
    """Semiamplitud del intervalo (cuantil 1 − (1 − nivel)/2... dos colas) por tramo de peso efectivo."""
    ok = np.isfinite(res)
    res, w = res[ok], w[ok]
    cortes = np.quantile(w, np.linspace(0, 1, bins + 1))
    cortes[0], cortes[-1] = -np.inf, np.inf
    lo, hi = [], []
    for k in range(bins):
        m = (w > cortes[k]) & (w <= cortes[k + 1])
        if m.sum() < 30:
            m = np.ones(len(res), bool)
        lo.append(float(np.quantile(res[m], (1 - nivel) / 2))); hi.append(float(np.quantile(res[m], 1 - (1 - nivel) / 2)))
    return {"cortes": cortes.tolist(), "lo": lo, "hi": hi, "nivel": nivel}


def aplicar_calibracion(cal: dict, w: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    k = np.clip(np.searchsorted(np.array(cal["cortes"]), w, side="left") - 1, 0, len(cal["lo"]) - 1)
    return np.array(cal["lo"])[k], np.array(cal["hi"])[k]


# =============================================================================================== examen
def examen(cfg: dict, progreso=print) -> dict:
    from bbfit.registro import experimento
    from .examen_f1 import perfiles_corte
    f2 = cfg["f2"]["dirigidos"]
    t0 = time.time()
    out_dir = dir_salida(cfg) / "examen"; out_dir.mkdir(parents=True, exist_ok=True)
    temps = list(cfg["perfil"]["temporadas"])
    E = cargar_interacciones(cfg, temps)
    cortes = [int(a) for a in cfg["criterios"]["comunes"]["cortes"]]
    sel = int(cfg["f1"]["comprobaciones_d2"]["corte"])
    B, sem = int(cfg["criterios"]["comunes"]["bootstrap"]), int(cfg["criterios"]["comunes"]["semilla_bootstrap"])
    candidatos = list(f2["modelo_candidatos"])
    minw = float(f2["min_poss_con"])
    resultado = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "cortes": {}, "decisiones": {}}
    cal_prev = {}                                    # residuos fuera de muestra del corte anterior, por efecto y candidato
    with experimento(cfg["mlflow"], "F2B_examen", params={"cortes": cortes}):
        for a in cortes:
            temp_t, temp_t1 = f"{a}-{str(a + 1)[-2:]}", f"{a + 1}-{str(a + 2)[-2:]}"
            T = RP.tabla_prior(perfiles_corte(cfg, a), cfg)
            R = SG.Rasgos(T, cfg)
            tr = E[(E["anio"] <= a) & (E["poss_con"] >= minw)].reset_index(drop=True)
            te = E[(E["anio"] == a + 1) & (E["poss_con"] >= minw)].reset_index(drop=True)
            Xtr, ok_tr = rasgos_pareja(tr, R)
            Xte, ok_te = rasgos_pareja(te, R, temporada_perfil=temp_t)
            te = te[ok_te].reset_index(drop=True); Xte = Xte[ok_te]
            media_liga = tr[tr["anio"] == a].groupby("liga")[list(EFECTOS)].mean()
            res_c = {"temporada_examen": temp_t1, "parejas_ajuste": int(ok_tr.sum()), "parejas_examen": int(len(te)),
                     "parejas_examen_sin_perfil": int((~ok_te).sum()), "efectos": {}}
            clus = (te["liga"] + "|" + te["temporada"] + "|" + te["team_id"].astype(str)).to_numpy()
            cal_new = {}
            for k in EFECTOS:
                y_tr, w_tr = tr[k].to_numpy(float), tr[f"w_{k}"].to_numpy(float)
                y_te, w_te = te[k].to_numpy(float), te[f"w_{k}"].to_numpy(float)
                okt = np.isfinite(y_te) & np.isfinite(w_te)
                base0 = np.zeros(len(te))
                basem = te["liga"].map(media_liga[k]).fillna(float(np.nanmean(y_tr))).to_numpy(float)
                ek = {"n": int(okt.sum())}
                for cand in candidatos:
                    mod = ModeloEfecto(cand, cfg).ajustar(Xtr[ok_tr], y_tr[ok_tr], w_tr[ok_tr])
                    pred = mod.predecir(Xte)
                    e_m = np.abs(y_te - pred); e_0 = np.abs(y_te - base0); e_l = np.abs(y_te - basem)
                    rng = np.random.default_rng(sem)
                    u, inv = np.unique(clus, return_inverse=True)
                    idx_por = [np.where(inv == c)[0] for c in range(len(u))]
                    d0, dl = [], []
                    for _ in range(min(B, 1000)):
                        pick = rng.integers(0, len(u), len(u)); ii = np.concatenate([idx_por[c] for c in pick]); ii = ii[okt[ii]]
                        mae_m = np.average(e_m[ii], weights=w_te[ii]); d0.append(mae_m - np.average(e_0[ii], weights=w_te[ii])); dl.append(mae_m - np.average(e_l[ii], weights=w_te[ii]))
                    # intervalo del 80 %: calibración con los residuos fuera de muestra del corte anterior (o en muestra)
                    res_oos = y_te - pred
                    if (k, cand) in cal_prev:
                        cal = calibracion(cal_prev[(k, cand)][0], cal_prev[(k, cand)][1], int(f2["bins_calibracion"]))
                        fuente_cal = "corte_anterior"
                    else:
                        cal = calibracion(y_tr[ok_tr] - mod.predecir(Xtr[ok_tr]), w_tr[ok_tr], int(f2["bins_calibracion"]))
                        fuente_cal = "en_muestra"
                    lo, hi = aplicar_calibracion(cal, w_te)
                    cob = float(np.average(((res_oos >= lo) & (res_oos <= hi))[okt], weights=w_te[okt]))
                    cal_new[(k, cand)] = (res_oos[okt], w_te[okt])
                    ek[cand] = {"mae": float(np.average(e_m[okt], weights=w_te[okt])), "mae_0": float(np.average(e_0[okt], weights=w_te[okt])),
                                "mae_media_liga": float(np.average(e_l[okt], weights=w_te[okt])),
                                "dif_0": float(np.average(e_m[okt], weights=w_te[okt]) - np.average(e_0[okt], weights=w_te[okt])),
                                "dif_0_ic95": [float(np.quantile(d0, 0.025)), float(np.quantile(d0, 0.975))],
                                "dif_media_liga_ic95": [float(np.quantile(dl, 0.025)), float(np.quantile(dl, 0.975))],
                                "cobertura_80": cob, "calibracion": fuente_cal,
                                "pasa": bool(np.quantile(d0, 0.975) < 0 and np.quantile(dl, 0.975) < 0),
                                "sd_pred": float(np.std(pred)), "sd_real": float(np.std(y_te[okt]))}
                res_c["efectos"][k] = ek
                if progreso:
                    progreso(f"    corte {a} {k}: " + " · ".join(f"{c}: MAE {ek[c]['mae']:.3f} (0: {ek[c]['mae_0']:.3f}, liga: {ek[c]['mae_media_liga']:.3f}) "
                                                               f"Δ0 {np.round(ek[c]['dif_0_ic95'], 3).tolist()} cob {ek[c]['cobertura_80']:.3f}" for c in candidatos), flush=True)
            cal_prev = cal_new
            resultado["cortes"][a] = res_c
        # decisión por efecto en el corte de selección: candidato de menor MAE; publica si pasa en los cortes de decisión
        dec = [a for a in cortes if a != int(cfg["criterios"]["comunes"]["corte_calibracion"])]
        decisiones = {}
        for k in EFECTOS:
            cand = min(candidatos, key=lambda c: resultado["cortes"][sel]["efectos"][k][c]["mae"])
            pasa = [resultado["cortes"][a]["efectos"][k][cand]["pasa"] for a in dec]
            cob = [resultado["cortes"][a]["efectos"][k][cand]["cobertura_80"] for a in dec]
            rango = cfg["criterios"]["f2"]["dirigidos_cobertura_80"]
            decisiones[k] = {"candidato": cand, "pasa_mae_por_corte": pasa, "cobertura_por_corte": cob,
                             "publicar": bool(all(pasa) and all(rango[0] <= c <= rango[1] for c in cob))}
        resultado["decisiones"] = decisiones
        n_pasan = sum(1 for d in decisiones.values() if all(d["pasa_mae_por_corte"]))
        resultado["puerta_11_2_dirigidos"] = {"efectos_con_mae_mejor": n_pasan, "minimo": int(cfg["criterios"]["f2"]["dirigidos_mae_mejor_que_0_y_media_liga_en"]),
                                             "cumple": bool(n_pasan >= int(cfg["criterios"]["f2"]["dirigidos_mae_mejor_que_0_y_media_liga_en"])),
                                             "publicados": [k for k, d in decisiones.items() if d["publicar"]]}
        resultado["tiempo_s"] = round(time.time() - t0)
        (out_dir / "resumen_examen_f2b.json").write_text(json.dumps(resultado, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    if progreso:
        progreso(f"  examen F2-B: {resultado['puerta_11_2_dirigidos']} · {resultado['tiempo_s']} s", flush=True)
    return resultado


def renormalizar_cuotas(cuotas: np.ndarray) -> np.ndarray:
    """Cuotas de tiro de los cinco de un quinteto, renormalizadas al 100 %."""
    c = np.maximum(np.asarray(cuotas, float), 0.0)
    return 100.0 * c / c.sum() if c.sum() > 0 else c


# =============================================================================================== producto
def exportar(cfg: dict, progreso=print) -> dict:
    """Ajuste con todas las temporadas de los efectos PUBLICADOS por el examen (modelo por efecto elegido en la selección),
    calibración del intervalo del 80 % con residuos fuera de muestra (5 pliegues por equipo-temporada) y predicción para
    todas las parejas observadas. Salidas en data/modelos/v4_0/sinergia/dirigidos/."""
    from bbfit.registro import experimento
    from .examen_f1 import perfiles_completo
    f2 = cfg["f2"]["dirigidos"]
    t0 = time.time()
    out = dir_salida(cfg)
    ex = json.loads((out / "examen" / "resumen_examen_f2b.json").read_text(encoding="utf-8"))
    publicados = ex["puerta_11_2_dirigidos"]["publicados"]
    temps = list(cfg["perfil"]["temporadas"])
    E = cargar_interacciones(cfg, temps)
    E = E[E["poss_con"] >= float(f2["min_poss_con"])].reset_index(drop=True)
    T = RP.tabla_prior(perfiles_completo(cfg, [t for t in temps if (C.dir_salida(cfg) / "perfiles" / f"{t}.csv.gz").exists()]), cfg)
    R = SG.Rasgos(T, cfg)
    X, ok = rasgos_pareja(E, R)
    E, X = E[ok].reset_index(drop=True), X[ok]
    clus = (E["liga"] + "|" + E["temporada"] + "|" + E["team_id"].astype(str)).to_numpy()
    u, inv = np.unique(clus, return_inverse=True)
    rng = np.random.default_rng(int(cfg["semilla"]))
    fold_c = rng.integers(0, 5, len(u)); fold = fold_c[inv]
    modelos, calib, doc_ef = {}, {}, {}
    pred_cols = {}
    with experimento(cfg["mlflow"], "F2B_producto", params={"publicados": publicados, "parejas": len(E)}):
        for k in publicados:
            cand = ex["decisiones"][k]["candidato"]
            y, w = E[k].to_numpy(float), E[f"w_{k}"].to_numpy(float)
            oos = np.full(len(E), np.nan)
            for f in range(5):
                tr_, te_ = fold != f, fold == f
                m = ModeloEfecto(cand, cfg).ajustar(X[tr_], y[tr_], w[tr_])
                oos[te_] = y[te_] - m.predecir(X[te_])
            cal = calibracion(oos, w, int(f2["bins_calibracion"]))
            mod = ModeloEfecto(cand, cfg).ajustar(X, y, w)
            pred = mod.predecir(X)
            lo, hi = aplicar_calibracion(cal, w)
            okk = np.isfinite(y)
            modelos[k], calib[k] = mod, cal
            pred_cols[k] = (pred, pred + lo, pred + hi)
            doc_ef[k] = {"candidato": cand, "n": int(okk.sum()), "mae_cv": float(np.average(np.abs(oos[okk]), weights=w[okk])),
                         "mae_0": float(np.average(np.abs(y[okk]), weights=w[okk])),
                         "cobertura_80_cv": float(np.average(((oos >= lo) & (oos <= hi))[okk], weights=w[okk])),
                         "sd_pred": float(np.std(pred)), "sd_real": float(np.std(y[okk]))}
            if progreso:
                progreso(f"    {k} ({cand}): MAE CV {doc_ef[k]['mae_cv']:.3f} frente a 0 {doc_ef[k]['mae_0']:.3f} · cobertura CV {doc_ef[k]['cobertura_80_cv']:.3f}", flush=True)
        (out / "modelos.pkl").write_bytes(pickle.dumps({"modelos": modelos, "rasgos": R, "calibracion": calib, "publicados": publicados}))
        tab = E[["liga", "temporada", "team_id", "persona_x", "persona_y", "poss_con", "poss_sin"]].copy()
        for k in publicados:
            tab[f"{k}_real"] = E[k]
            tab[f"{k}_pred"], tab[f"{k}_lo80"], tab[f"{k}_hi80"] = pred_cols[k]
        for t, g in tab.groupby("temporada"):
            g.round(3).to_csv(out / f"efectos_{t}.csv.gz", index=False)
        doc = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "publicados": publicados, "no_publicados": [k for k in EFECTOS if k not in publicados],
               "parejas": int(len(E)), "efectos": doc_ef, "calibracion": {k: {kk: vv for kk, vv in v.items() if kk != "cortes"} for k, v in calib.items()},
               "rasgos": R.exportable(), "tiempo_s": round(time.time() - t0)}
        (out / "resumen_producto.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    if progreso:
        progreso(f"  F2-B producto: {publicados} · {doc['tiempo_s']} s", flush=True)
    return doc


def predecir(modelos: dict, zx: np.ndarray, zy: np.ndarray) -> dict:
    """d̂_k(X → Y) para parejas nuevas a partir de sus z (F4): {efecto: (pred, lo80, hi80)} con la calibración global
    (tramo de peso medio)."""
    X = np.hstack([zx, zy, zx * zy])
    out = {}
    for k, mod in modelos["modelos"].items():
        pred = mod.predecir(X)
        cal = modelos["calibracion"][k]
        mid = len(cal["lo"]) // 2
        out[k] = (pred, pred + cal["lo"][mid], pred + cal["hi"][mid])
    return out


def modelos_corte(cfg: dict, a: int, R: SG.Rasgos, efectos=None, progreso=None) -> dict:
    """Modelos publicados (GBM) ajustados SÓLO con interacciones de temporadas ≤ a y los rasgos del corte (para IM sin fuga).
    Caché: dirigidos/examen/modelos_corte_<a>.pkl."""
    import pickle
    out_dir = dir_salida(cfg) / "examen"; out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"modelos_corte_{a}.pkl"
    if dest.exists():
        return pickle.loads(dest.read_bytes())
    f2 = cfg["f2"]["dirigidos"]
    efectos = list(efectos or cfg["criterios"]["f5"]["im_onoff"]["complemento_companeros"]["efectos"])
    E = cargar_interacciones(cfg, [t for t in cfg["perfil"]["temporadas"] if int(t[:4]) <= a])
    tr = E[(E["anio"] <= a) & (E["poss_con"] >= float(f2["min_poss_con"]))].reset_index(drop=True)
    X, ok = rasgos_pareja(tr, R)
    mods = {}
    for k in efectos:
        y, w = tr[k].to_numpy(float), tr[f"w_{k}"].to_numpy(float)
        mods[k] = ModeloEfecto("gbm", cfg).ajustar(X[ok], y[ok], w[ok])
        if progreso:
            progreso(f"    F2-B corte {a}: {k} ajustado con {int(ok.sum())} parejas", flush=True)
    dest.write_bytes(pickle.dumps({"modelos": mods, "parejas": int(ok.sum()), "corte": a}))
    return {"modelos": mods, "parejas": int(ok.sum()), "corte": a}


def efectos_sobre_companeros(modelos: dict, zx: np.ndarray, Zy: np.ndarray, cuotas_y: np.ndarray) -> dict:
    """Agregado del efecto de X sobre su plantilla: Σ_Y (cuota_Y / 5) · d̂_k(X → Y) para cada efecto k; y el detalle por Y."""
    if len(Zy) == 0:
        return {k: 0.0 for k in modelos["modelos"]} | {"detalle": {}}
    X = np.hstack([np.repeat(zx[None, :], len(Zy), 0), Zy, zx[None, :] * Zy])
    out = {"detalle": {}}
    w = np.asarray(cuotas_y, float) / 5.0
    for k, mod in modelos["modelos"].items():
        d = mod.predecir(X)
        out[k] = float(np.sum(w * d)); out["detalle"][k] = d
    return out
