"""F9 · Salidas de la v5 por jugador, métrica y **cada liga de destino posible** (encargo §13).

Para cada persona que jugó alguna de las dos últimas temporadas y cada liga de destino L se construye la fila de la
temporada objetivo como la del examen de la F8, pero con L supuesta:

1. **Carrera (F4).** Nivel filtrado hasta la última temporada, proyectado a la objetivo con la edad, el hueco, el
   cambio de liga y la media del rol en L (`MC.predecir`, modelo «completo», como `ligas/contexto.base_corte`).
2. **Traducción.** Δλ = λ_L − λ_origen del GLS del paso 2 (variante encogido) estimado con todas las temporadas.
3. **Contexto publicado ex ante** (criterio 11 y decisión 2 de la F8): peso de la liga, tipo de jugador y compañeros,
   sin volumen ni estilo de liga. El rol en L es desconocido (mezcla con las probabilidades de transición) y la
   exposición también (N_ult por un cociente sorteado). Compañeros: el equipo medio de L en la última temporada
   frente a su equipo de la última temporada.
4. **Resúmenes.**
   - Nivel: tasa persistente, cuantiles 10/25/50/75/90.
   - Predictivo: tasa observada de la temporada objetivo, cuantiles 2,5/10/25/50/75/90/97,5, con la recalibración
     por métrica y grupo si se adoptó (decisión 4 de la F8).
   - Traducción: Δλ con su DT en la escala del enlace, y el efecto en la mediana del nivel frente a quedarse en su
     liga, en la escala de la métrica.
   - Probabilidades de umbral P(nivel > u_k), con u_k los percentiles 25, 50 y 75 de la tasa observada en L × rol
     (≥ 300 min, tres últimas temporadas). El rol es el de su última temporada.
   - Sello de fiabilidad (regla en `sello`).

Escala: la de la métrica en fracción (tasa por oportunidad); `formato_v32.py` la pasa a las unidades de la v3.2.
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

from bbnorm5 import config as C
from bbnorm5.carrera import datos as CD
from bbnorm5.carrera import examen as EX
from bbnorm5.carrera import modelo as MC
from bbnorm5.ligas import contexto as LC
from bbnorm5.ligas import gls
from bbnorm5.ligas import seleccion as LS
from bbnorm5.medida import datos as DM
from bbnorm5.validacion import fichajes as VF

DIR = C.DIR_DATOS / "salidas"
BLOQUES = ["peso_liga", "companeros", "tipo"]           # = VF.EX_ANTE["ex_ante_sin_estilo_liga"]
Q_NIVEL = [0.1, 0.25, 0.5, 0.75, 0.9]
Q_PRED = [0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975]
UMBRALES = (25, 50, 75)
TROZO = 3000


def _nom(q: float) -> str:
    return f"q{q * 100:g}".replace(".", "_")


# ------------------------------------------------------------------ filas hipotéticas
def filas_destino(o: pd.DataFrame, h: pd.DataFrame, met: str, anio: int, perf: pd.DataFrame, ctx: pd.DataFrame,
                  mods: dict) -> pd.DataFrame:
    om = o[o["metrica"] == met]
    hist = om[om["anio"] < anio]
    M = MC.matrices(hist)
    tau0 = float(h[(h["metrica"] == met) & (h["temporada"].str[:4].astype(int) < anio)]["sigma"].median())
    mod = MC.ajustar(M, "completo", tau0)
    ult = hist.sort_values("anio").drop_duplicates("persona_v5", keep="last")
    ult = ult[ult["anio"] >= anio - 2]
    lp = EX._liga_previa(h, met, anio)
    disp = lp.drop_duplicates("liga")[["liga", "disp_prev", "sigma_prev"]]
    ligas = sorted(disp["liga"])
    u = ult[["persona_v5", "anio", "liga", "rol", "edad", "N", "N2g", "temporada"]].rename(
        columns={"anio": "anio_ult", "liga": "liga_ult", "rol": "rol_ult", "edad": "edad_ult", "N": "N_ult",
                 "temporada": "temporada_ult"})
    x = u.merge(pd.DataFrame({"liga": ligas}), how="cross")
    x["anio"] = anio
    x["gap"] = (anio - x["anio_ult"]).astype(float)
    x["edad"] = x["edad_ult"] + x["gap"]
    x["cl"] = (x["liga"] != x["liga_ult"]).astype(float)
    x["cr"] = 0.0
    x["dmu"] = 0.0
    x["rol"] = x["rol_ult"]
    x = x.merge(disp, on="liga", how="left")
    mu = lp[["liga", "rol", "mu_prev"]]
    x = x.merge(mu.rename(columns={"rol": "rol_ult", "mu_prev": "mu_prev_rol_ult"}), on=["liga", "rol_ult"], how="left")
    # media de partida: la de su rol en L o, si L no tiene ese rol (ligas sólo con X), la primera disponible; la mezcla
    # de roles la sustituye por la de cada rol y le da peso 0 a los que L no tiene
    x["mu_prev"] = x["mu_prev_rol_ult"].fillna(x["liga"].map(mu.drop_duplicates("liga").set_index("liga")["mu_prev"]))
    x = x.merge(mu.rename(columns={"liga": "liga_ult", "rol": "rol_ult", "mu_prev": "mu_origen"}),
                on=["liga_ult", "rol_ult"], how="left")
    x = MC.predecir(M, mod, x)
    x["N"], x["K"] = x["N_ult"], 0.0
    x["metrica"], x["anio_obj"] = met, anio
    x["s2_u"] = float(np.exp(2 * mod["th"].get("log_s_u", -30)))
    # tipo de jugador: perfiles estables de la última temporada (F5)
    z = perf.set_index(["persona_v5", "temporada"])[LC.PERFILES]
    zz = np.nan_to_num(z.reindex(pd.MultiIndex.from_arrays([x["persona_v5"], x["temporada_ult"]])).to_numpy())
    for k, p in enumerate(LC.PERFILES):
        x[f"z_{p}"] = zz[:, k]
    # compañeros: equipo medio de L en su última temporada frente a su equipo de la última temporada
    est = [f"comp_{e}" for e in LC.ESTILOS]
    c = ctx[ctx["temporada"] <= f"{anio - 1}-{str(anio)[2:]}"]
    medio = c.sort_values("temporada").groupby("liga").apply(
        lambda g: g[g["temporada"] == g["temporada"].max()][est].mean())
    propio = c.groupby(["persona_v5", "liga", "temporada"])[est].mean()
    prev = propio.reindex(pd.MultiIndex.from_arrays([x["persona_v5"], x["liga_ult"], x["temporada_ult"]])).to_numpy()
    dest = medio.reindex(x["liga"]).to_numpy()
    dc = np.nan_to_num(dest - prev)
    for k, e in enumerate(LC.ESTILOS[:-1]):
        x[f"dcomp_{e}"] = dc[:, k]
    for r in ("E", "A", "I"):
        x[f"vol_{r}"] = 0.0
    x["min_temp"] = np.nan
    return LS.con_lambda_paso2(x, mods=mods)


# ------------------------------------------------------------------ umbrales y sello
def umbrales(o: pd.DataFrame, met: str, anio: int, min_jugadores: int = 20) -> pd.DataFrame:
    """Percentiles de la tasa observada (≥ 300 min, tres temporadas anteriores) por liga × rol; si la liga no tiene ese
    rol con `min_jugadores` (p. ej. ligas sólo con rol X), los de la liga entera (`rol` = «todos»)."""
    b = o[(o["metrica"] == met) & (o["anio"] < anio) & (o["anio"] >= anio - 3) & (o["min_temp"] >= 300) & (o["N"] > 0)]
    b = b.assign(tasa=b["K"] / b["N"])
    qs = [u / 100 for u in UMBRALES]
    filas = []
    for clave, g in list(b.groupby(["liga", "rol"])) + [((l, "todos"), g) for l, g in b.groupby("liga")]:
        if len(g) >= min_jugadores:
            filas.append({"liga": clave[0], "rol": clave[1],
                          **{f"umbral_p{u}": float(v) for u, v in zip(UMBRALES, g["tasa"].quantile(qs))}})
    return pd.DataFrame(filas)


def n_estabilizacion() -> pd.Series:
    """Oportunidades con fiabilidad de una temporada 0,5 (F3), mediana entre ligas y temporadas."""
    h = CD._hiper_preferido(pd.read_csv(DM.DIR / "hiperparametros.csv"))
    return h.groupby("metrica")["n_estab"].median()


def sello(exp_rel: np.ndarray, hist: np.ndarray, conect: np.ndarray, reglas: dict) -> np.ndarray:
    """Sello de fiabilidad (regla publicada en el glosario):
    - **alta**: exposición acumulada ≥ `alta_exposicion` × n* de la métrica, ≥ `alta_temporadas` temporadas de historial
      y conectividad del par origen-destino ≤ `alta_conectividad` (DT de Δλ en DT de λ entre ligas; 0 si no cambia);
    - **baja**: exposición < `baja_exposicion` × n*, o conectividad > `baja_conectividad`;
    - **media**: el resto."""
    alta = (exp_rel >= reglas["alta_exposicion"]) & (hist >= reglas["alta_temporadas"]) & (conect <= reglas["alta_conectividad"])
    baja = (exp_rel < reglas["baja_exposicion"]) | (conect > reglas["baja_conectividad"])
    return np.where(baja, "baja", np.where(alta, "alta", "media"))


# ------------------------------------------------------------------ resumen por trozos
def _resumir(te: pd.DataFrame, fam: str, aj: dict, lp: pd.DataFrame, rng, um: pd.DataFrame, recal: dict | None,
             n_draws: int, guardar_draws: bool):
    ks, tn, P, sin, f = VF.muestras_exante(te, fam, aj, lp, rng)
    out = pd.DataFrame(index=te.index)
    qn = np.quantile(tn, Q_NIVEL, axis=1)
    for i, q in enumerate(Q_NIVEL):
        out[f"nivel_{_nom(q)}"] = qn[i]
    out["nivel_media"] = tn.mean(axis=1)
    qp = np.quantile(ks, Q_PRED, axis=1)
    for i, q in enumerate(Q_PRED):
        out[f"pred_{_nom(q)}"] = qp[i]
    out["pred_media"] = ks.mean(axis=1)
    if recal is not None:
        from bbnorm5.validacion import recalibracion as VR
        k = pd.Series(te["metrica"].map(recal["metrica"]).fillna(recal["global"]).to_numpy(float), index=te.index) * \
            pd.Series(VR.grupo(te["liga_ult"], te["liga"]), index=te.index).map(recal["grupo"]).fillna(1.0)
        c = out["pred_q50"]
        for q in Q_PRED:
            out[f"pred_{_nom(q)}"] = c + k * (out[f"pred_{_nom(q)}"] - c)
        out["factor_recal_grupo"] = k
    uu = te[["liga", "rol_ult"]].merge(um.rename(columns={"rol": "rol_ult"}), on=["liga", "rol_ult"], how="left")
    todos = te[["liga"]].merge(um[um["rol"] == "todos"].drop(columns="rol"), on="liga", how="left")
    out["umbral_referencia"] = np.where(uu["umbral_p50"].notna(), te["rol_ult"].to_numpy(), "todos")
    for u in UMBRALES:
        v = uu[f"umbral_p{u}"].fillna(todos[f"umbral_p{u}"]).to_numpy(float)
        out[f"umbral_p{u}"] = v
        out[f"p_supera_p{u}"] = np.where(np.isfinite(v), (tn > v[:, None]).mean(axis=1), np.nan)
    out["p_rol_E"], out["p_rol_A"], out["p_rol_I"], out["p_rol_X"] = P[:, 0], P[:, 1], P[:, 2], P[:, 3]
    dr = None
    if guardar_draws:
        sel = rng.choice(tn.shape[1], n_draws, replace=False)
        dr = (tn[:, sel].astype(np.float32), ks[:, sel].astype(np.float32))
    return out, dr


def generar(cfg: dict, metricas: list[str] | None = None, parte: str | None = None) -> dict:
    """Todas las métricas en un proceso o, con `metricas` y `parte`, sólo esas (para repartir entre procesos);
    `unir` junta las partes y añade las derivadas."""
    anio = int(cfg["anio_objetivo"])
    o = CD.cargar()
    H = CD._hiper_preferido(pd.read_csv(DM.DIR / "hiperparametros.csv"))
    perf = pd.read_parquet(C.DIR_DATOS / "latente" / "perfiles_latentes.parquet")
    ctx = pd.read_parquet(C.DIR_DATOS / "contexto" / "contexto_companeros.parquet")
    base = pd.read_parquet(C.DIR_DATOS / "validacion" / "base_v5.parquet")
    cfg7 = C.cargar("configs/v5/f7.yaml")
    mods = LS.modelos_paso2(cfg7, [anio])
    nst = n_estabilizacion()
    recal = None
    if cfg.get("recalibracion", {}).get("aplicar"):
        from bbnorm5.validacion import recalibracion as VR
        p = pd.read_parquet(C.DIR_DATOS / "validacion" / "predicciones_v5.parquet")
        recal = VR.factores(p[(p["modelo"] == VR.MODELO) & (p["anio"] == anio - 1)])
    nd = int(cfg["draws"]["por_caso"])
    temp_obj = f"{anio}-{str(anio + 1)[2:]}"
    salida = DIR / temp_obj
    salida.mkdir(parents=True, exist_ok=True)
    partes, draws = [], []
    for met in (metricas or list(DM.METRICAS)):
        fam = DM.METRICAS[met][0]
        x = filas_destino(o, H, met, anio, perf, ctx, mods)
        tr = base[base["metrica"] == met]
        eta, vo = LC.observacion(tr, fam)
        aj = VF.ajuste_exante(tr, BLOQUES, eta, vo)
        lp = EX._liga_previa(H, met, anio)[["liga", "rol", "mu_prev"]]
        um = umbrales(o, met, anio)
        rng = np.random.default_rng((cfg["semilla"] + zlib.crc32(f"{anio}|{met}".encode())) % 2 ** 32)
        res = []
        for i in range(0, len(x), TROZO):
            te = x.iloc[i:i + TROZO]
            propia = (te["cl"] == 0).to_numpy()
            r, dr = _resumir(te, fam, aj, lp, rng, um, recal, nd, guardar_draws=True)
            res.append(r)
            if dr is not None and propia.any():
                draws.append(pd.DataFrame({"persona_v5": te["persona_v5"].to_numpy()[propia], "metrica": met,
                                           "liga": te["liga"].to_numpy()[propia],
                                           "nivel": list(dr[0][propia]), "predictivo": list(dr[1][propia])}))
        r = pd.concat(res)
        # exposición acumulada y conectividad
        nacum = o[(o["metrica"] == met) & (o["anio"] < anio)].groupby("persona_v5")["N"].sum()
        sd_entre = float(np.std(mods[(anio, met, "encogido")]["lambda"]))
        y = x[["persona_v5", "metrica", "liga_ult", "temporada_ult", "rol_ult", "edad", "temporadas_hist", "liga", "cl",
               "delta_lambda", "var_lambda", "N_ult"]].rename(columns={"liga": "liga_destino", "liga_ult": "liga_origen",
                                                                      "cl": "cambio_liga"})
        y["temporada_objetivo"] = temp_obj
        y["traduccion_media"] = y["delta_lambda"]
        y["traduccion_dt"] = np.sqrt(y["var_lambda"])
        y["traduccion_q10"] = y["delta_lambda"] - 1.2816 * y["traduccion_dt"]
        y["traduccion_q90"] = y["delta_lambda"] + 1.2816 * y["traduccion_dt"]
        y = pd.concat([y.drop(columns=["delta_lambda", "var_lambda"]), r], axis=1)
        propio = y[y["cambio_liga"] == 0].set_index("persona_v5")["nivel_q50"]
        y["traduccion_efecto_nivel"] = y["nivel_q50"] - y["persona_v5"].map(propio)
        y["exposicion_acumulada"] = y["persona_v5"].map(nacum)
        y["exposicion_relativa"] = y["exposicion_acumulada"] / float(nst[met])
        y["conectividad"] = np.where(y["cambio_liga"] > 0, y["traduccion_dt"] / sd_entre, 0.0)
        y["sello"] = sello(y["exposicion_relativa"].to_numpy(float), y["temporadas_hist"].to_numpy(float),
                           y["conectividad"].to_numpy(float), cfg["sello"])
        partes.append(y)
        print(f"  {met}: {len(y)} filas", flush=True)
    t = pd.concat(partes, ignore_index=True)
    d = pd.concat(draws, ignore_index=True)
    if parte is not None:
        t.to_parquet(salida / f"destinos_parte{parte}.parquet")
        d.to_parquet(salida / f"draws_parte{parte}.parquet")
        return {"parte": parte, "metricas": metricas, "filas": len(t)}
    t.to_parquet(salida / "destinos.parquet")
    d.to_parquet(salida / "draws_liga_actual.parquet")
    entradas = [C.DIR_DATOS / "carrera" / "observaciones.parquet", C.DIR_DATOS / "latente" / "perfiles_latentes.parquet",
                C.DIR_DATOS / "contexto" / "contexto_companeros.parquet", C.DIR_DATOS / "validacion" / "base_v5.parquet",
                C.DIR_DATOS / "ligas" / "pares_paso2.parquet", DM.DIR / "hiperparametros.csv"]
    meta = {**C.metadatos(cfg, [e for e in entradas if e.exists()], {"paso": "destinos"}), "temporada_objetivo": temp_obj,
            "temporadas_entrenamiento": sorted(o.loc[o["anio"] < anio, "temporada"].unique().tolist()),
            "lambda": "GLS del paso 2, variante encogido, todas las temporadas", "bloques_contexto": BLOQUES,
            "recalibracion_grupo": recal is not None, "draws_por_caso": nd, "filas": len(t),
            "personas": int(t["persona_v5"].nunique()), "n_estabilizacion": nst.round(1).to_dict(),
            "regla_sello": cfg["sello"]}
    C.escribir_json(meta, salida / "meta.json")
    return {"filas": len(t), "personas": meta["personas"], "draws": len(d)}


# ------------------------------------------------------------------ unión de partes y métricas derivadas (F9 bis)
def derivadas(t: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """TS% y eFG% (draws conjuntos de sus componentes) y variantes «por 100 posesiones» de la v3.2 (razón de la liga
    de destino en la última temporada), con las mismas columnas que las demás métricas. Escala: fracción."""
    from bbnorm5.salidas import derivadas as DV
    anio = int(cfg["anio_objetivo"])
    ult = f"{anio - 1}-{str(anio)[2:]}"
    clave = ["persona_v5", "liga_destino"]
    base_cols = ["persona_v5", "liga_origen", "temporada_ult", "rol_ult", "edad", "temporadas_hist", "liga_destino",
                 "cambio_liga", "temporada_objetivo", "sello", "exposicion_acumulada", "exposicion_relativa",
                 "conectividad", "traduccion_media", "traduccion_dt", "traduccion_q10", "traduccion_q90"]
    filas = []
    # 1. TS% y eFG%
    w = {m: t[t["metrica"] == m].set_index(clave) for m in DV.COMPONENTES}
    idx = w[DV.COMPONENTES[0]].index
    for m in DV.COMPONENTES[1:]:
        idx = idx.intersection(w[m].index)
    w = {m: v.loc[idx] for m, v in w.items()}
    R = DV.correlacion()
    rng = np.random.default_rng(cfg["semilla"] + 7)
    qn, qp = [0.1, 0.25, 0.5, 0.75, 0.9], [0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975]
    nv = DV.tiro_compuesto({m: (w[m]["nivel_q10"].to_numpy(), w[m]["nivel_q50"].to_numpy(), w[m]["nivel_q90"].to_numpy())
                            for m in DV.COMPONENTES}, R, rng, cuantiles=qn)
    pr = DV.tiro_compuesto({m: (w[m]["pred_q10"].to_numpy(), w[m]["pred_q50"].to_numpy(), w[m]["pred_q90"].to_numpy())
                            for m in DV.COMPONENTES}, R, rng, cuantiles=qp)
    ref = w["t2_pct"].reset_index()
    sello_min = pd.concat([w[m]["sello"].map({"baja": 0, "media": 1, "alta": 2}) for m in DV.COMPONENTES], axis=1).min(axis=1)
    for nom in ("efg_pct", "ts_pct"):
        f = ref[[c for c in base_cols if c in ref.columns]].copy()
        f["metrica"] = nom
        for q in qn:
            f[f"nivel_{_nom(q)}"] = nv[nom][q]
        f["nivel_media"] = nv[nom]["media"]
        for q in qp:
            f[f"pred_{_nom(q)}"] = pr[nom][q]
        f["pred_media"] = pr[nom]["media"]
        f["sello"] = sello_min.map({0: "baja", 1: "media", 2: "alta"}).to_numpy()   # el peor de sus componentes
        for u in UMBRALES:          # sin umbrales propios para las derivadas (VERIFICAR: percentiles de TS% y eFG%)
            f[f"p_supera_p{u}"] = np.nan
        f["derivada"] = "tiro_compuesto"
        filas.append(f)
    # 2. variantes por 100 posesiones (conversión de unidades con la razón de la liga de destino)
    raz = DV.razones()
    raz = raz[raz["temporada"] == ult].set_index("liga")
    for m32, (m5, col) in DV.POR_100.items():
        x = t[t["metrica"] == m5].copy()
        r = 1.0 if col is None else x["liga_destino"].map(raz[col]).to_numpy(float)
        cols = [c for c in x.columns if c.startswith(("nivel_q", "pred_q")) or c in ("nivel_media", "pred_media")]
        for c in cols:
            x[c] = x[c].to_numpy(float) * r
        x = x.drop(columns=[c for c in x.columns if c.startswith("umbral_p")])
        x["metrica"] = m32
        x["derivada"] = f"por_100:{m5}"
        filas.append(x)
    return pd.concat(filas, ignore_index=True)


def unir(cfg: dict) -> dict:
    anio = int(cfg["anio_objetivo"])
    temp_obj = f"{anio}-{str(anio + 1)[2:]}"
    salida = DIR / temp_obj
    partes = sorted(salida.glob("destinos_parte*.parquet"))
    t = pd.concat([pd.read_parquet(f) for f in partes], ignore_index=True)
    t["derivada"] = ""
    dv = derivadas(t, cfg)
    t = pd.concat([t, dv], ignore_index=True)
    t.to_parquet(salida / "destinos.parquet")
    d = pd.concat([pd.read_parquet(f) for f in sorted(salida.glob("draws_parte*.parquet"))], ignore_index=True)
    d.to_parquet(salida / "draws_liga_actual.parquet")
    for f in partes + sorted(salida.glob("draws_parte*.parquet")):
        f.unlink()
    nst = n_estabilizacion()
    entradas = [C.DIR_DATOS / "carrera" / "observaciones.parquet", C.DIR_DATOS / "latente" / "perfiles_latentes.parquet",
                C.DIR_DATOS / "contexto" / "contexto_companeros.parquet", C.DIR_DATOS / "validacion" / "base_v5.parquet",
                C.DIR_DATOS / "ligas" / "pares_paso2.parquet", DM.DIR / "hiperparametros.csv"]
    o = CD.cargar()
    meta = {**C.metadatos(cfg, [e for e in entradas if e.exists()], {"paso": "destinos"}), "temporada_objetivo": temp_obj,
            "temporadas_entrenamiento": sorted(o.loc[o["anio"] < anio, "temporada"].unique().tolist()),
            "lambda": "GLS del paso 2, variante encogido, todas las temporadas", "bloques_contexto": BLOQUES,
            "recalibracion_grupo": bool(cfg.get("recalibracion", {}).get("aplicar")),
            "draws_por_caso": int(cfg["draws"]["por_caso"]), "filas": len(t), "personas": int(t["persona_v5"].nunique()),
            "metricas_modeladas": sorted(t.loc[t["derivada"] == "", "metrica"].unique().tolist()),
            "metricas_derivadas": sorted(dv["metrica"].unique().tolist()),
            "n_estabilizacion": nst.round(1).to_dict(), "regla_sello": cfg["sello"]}
    C.escribir_json(meta, salida / "meta.json")
    return {"filas": len(t), "personas": meta["personas"], "derivadas": len(dv), "draws": len(d)}
