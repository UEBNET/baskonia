"""F8 · Predicciones de la v5 fuera de tiempo y examen principal con fichajes reales (revisión 1.2, criterios 9–11).

**Predicciones de la v5** (`predicciones_v5`): la proyección en contexto de la F6.2 con λ del paso 2 (F7), para cada
persona con temporada previa y cada temporada objetivo de prueba (2023-24, 2024-25 y 2025-26). Todo lo que entra en
la predicción de T se estima con temporadas < T:
- la base de la F4 (`seleccion_base.parquet`: nivel encogido con la carrera hasta T−1);
- λ del paso 2 (GLS con puentes intra y traspasos anteriores a T, `seleccion.modelos_paso2`);
- β del contexto y el factor de varianza de los cambios de liga (temporadas objetivo < T).

Variantes: `base_F4` (sin liga ni contexto), `final` (liga + peso + todos los bloques + recalibración) y el final sin
el estilo de liga o sin el de los compañeros (criterio 11). Por caso se guardan la media, los cuantiles 5–95 % de la
tasa observada, el CRPS y el PIT (sobre 400 draws, con el ruido de muestreo de la exposición observada) y, para el
final, la misma predicción con la exposición de la temporada anterior (conocida en t).

**Banco de fichajes reales** (`banco_v33`): el examen sin fuga del simulador (V32_corte, cortes 2022-23 a 2024-25,
destino con ≥ 300 min), con la producción **aplicada** de la v3.3 reconstruida caso a caso con sus propias funciones
(`bbfit.v32.aplicar`: motor o Atlas según la decisión anidada de cada corte y recalibración de los intervalos con los
cortes anteriores). Los centros reproducen exactamente los MAE de `decisiones_v33.json`.

**Comparación** (`comparar`): mismas personas, misma temporada, misma liga de destino y el mismo valor observado.
- Métricas comunes (misma definición; correlación 0,995–1,000 entre el observado de cada sistema): pts/100, USG%,
  AST%, STL/100 y TOV%.
- Puntuación: WIS (weighted interval score; Bracher et al., 2021): regla propia por intervalos centrales; con los del
  50, 80 y 90 % vale ≈ 0,8 × CRPS (faltan las colas), igual para los dos sistemas.
  La v3.3 sólo guarda los intervalos del 50, 80 y 90 % y su centro, así que se usa el mismo WIS para las dos.
- Intervalo de la diferencia: bootstrap por persona (criterio 9).
"""
from __future__ import annotations

import os
import zlib

import numpy as np
import pandas as pd

from bbnorm5 import config as C
from bbnorm5.carrera import examen as EX
from bbnorm5.ligas import contexto as LC
from bbnorm5.ligas import seleccion as LS
from bbnorm5.medida import datos as DM
from bbnorm5.medida import eb

DIR = C.DIR_DATOS / "validacion"
CUANTILES = [0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.975]
NIVELES = {50: (0.25, 0.75), 80: (0.1, 0.9), 90: (0.05, 0.95)}
COMUNES = ["pts_p100", "usg_pct", "ast_pct", "stl_p100", "tov_pct"]
TODOS = ["peso_liga", "volumen", "companeros", "tipo", "estilo_liga"]
VARIANTES = {
    "base_F4": (False, []),
    "final": (True, TODOS),
    "final_sin_estilo_liga": (True, [b for b in TODOS if b != "estilo_liga"]),
    "final_sin_companeros": (True, [b for b in TODOS if b != "companeros"]),
}
# ex ante (lo que se sabe al fichar): sin el bloque de volumen (usa las oportunidades reales de T), rol de T desconocido
# (mezcla con las probabilidades de transición de rol de los años anteriores) y exposición de T desconocida (la de la
# temporada anterior por un cociente N_T/N_ult sorteado de los años anteriores)
EX_ANTE = {
    "ex_ante": [b for b in TODOS if b != "volumen"],
    "ex_ante_sin_estilo_liga": [b for b in TODOS if b not in ("volumen", "estilo_liga")],
    "ex_ante_sin_companeros": [b for b in TODOS if b not in ("volumen", "companeros")],
}
N_EXPOSICION = 4                       # exposiciones de T sorteadas por caso (× 400 draws)
ROLES = ["E", "A", "I", "X"]          # X: sin reparto de roles (ligas o temporadas sin jugada a jugada)


def _q(nombre: float) -> str:
    return f"q{nombre * 100:g}".replace(".", "_")


# ------------------------------------------------------------------ rol de T desconocido
def con_rol(te: pd.DataFrame, r: str, lp: pd.DataFrame) -> pd.DataFrame:
    """La misma predicción de la F4 + contexto si el rol de T fuera r: media del rol r en la liga de destino (temporada
    previa), desplazamiento y varianza del cambio de rol respecto al último rol, ajuste de liga y Δλ × rol."""
    y = te.copy()
    mu_r = y[["liga"]].merge(lp[lp["rol"] == r][["liga", "mu_prev"]], on="liga", how="left")["mu_prev"].to_numpy(float)
    valido = np.isfinite(mu_r)
    mu_r = np.where(valido, mu_r, y["mu_prev"].to_numpy(float))      # sin media previa de r: peso 0 en la mezcla
    phi, s2r = y["phi_rol"].to_numpy(float), y["s2_R"].to_numpy(float)
    cr_r = (y["rol_ult"] != r).to_numpy(float)
    dmu_r = np.where(cr_r > 0, np.nan_to_num(y["mu_prev_rol_ult"].to_numpy(float) - mu_r), 0.0)
    y["m_nivel"] = y["m_nivel"].to_numpy(float) - phi * y["dmu"].to_numpy(float) + phi * dmu_r
    dv = (cr_r - y["cr"].to_numpy(float)) * s2r
    y["v_nivel"] = y["v_nivel"].to_numpy(float) + dv
    y["v_y_sin_muestreo"] = y["v_y_sin_muestreo"].to_numpy(float) + dv
    ok = (y["cl"] > 0).to_numpy() & y["mu_origen"].notna().to_numpy() & np.isfinite(y["delta_lambda"].to_numpy(float))
    y["ajuste_liga"] = np.where(ok, y["mu_origen"].to_numpy(float) - mu_r + y["delta_lambda"].to_numpy(float), 0.0)
    y["mu_prev"], y["rol"], y["cr"], y["dmu"] = mu_r, r, cr_r, dmu_r
    for rr in ("E", "I"):
        y[f"dl_rol_{rr}"] = y["delta_lambda"] * (rr == r)
    for rr in ("E", "A", "I"):
        y[f"vol_{rr}"] = 0.0
    return y, valido


def prob_rol(tr: pd.DataFrame) -> dict:
    """P(rol de T | último rol, cambio de liga) en los años de entrenamiento (suavizado de Laplace)."""
    t = tr.drop_duplicates(["persona_v5", "anio_obj"])
    out = {}
    for (ru, cl), g in t.groupby(["rol_ult", t["cl"] > 0]):
        n = g["rol"].value_counts().reindex(ROLES, fill_value=0).to_numpy(float) + 1.0
        out[(ru, bool(cl))] = n / n.sum()
    return out


def exante(tr: pd.DataFrame, te: pd.DataFrame, fam: str, bloques: list[str], lp: pd.DataFrame, eta, vo, rng) -> pd.DataFrame:
    cols = [c for b in bloques for c in LC.BLOQUES[b]]
    trl = LC.aplicar(tr, [], None, True)
    r = eta - (trl["mu_prev"] + trl["m_nivel"]).to_numpy()
    w = 1 / (trl["v_y_sin_muestreo"].to_numpy(float) + np.asarray(vo, float))
    ok = np.isfinite(r) & np.isfinite(w)
    grupos = np.concatenate([[k] * len(LC.BLOQUES[b]) for k, b in enumerate(bloques)])
    fit = LC.ajustar_beta(tr[cols].to_numpy(float)[ok], r[ok], w[ok], grupos)
    f = LC.factor_recalibracion(tr, cols, fit, True, eta, vo)
    pr = prob_rol(tr)
    P = np.array([pr.get((ru, bool(c > 0)), np.full(len(ROLES), 1 / len(ROLES))) for ru, c in zip(te["rol_ult"], te["cl"])])
    # exposición de T desconocida: N_ult × cociente N_T / N_ult sacado de los años de entrenamiento (por cambio de liga)
    nu = np.where(np.isfinite(te["N_ult"].to_numpy(float)) & (te["N_ult"].to_numpy(float) > 0),
                  te["N_ult"].to_numpy(float), te["N"].to_numpy(float))
    lr = np.log((tr["N"].to_numpy(float) + 1) / (tr["N_ult"].to_numpy(float) + 1))
    cl_tr, cl_te = (tr["cl"] > 0).to_numpy(), (te["cl"] > 0).to_numpy()
    ok_lr = np.isfinite(lr)
    exps = []
    for _ in range(N_EXPOSICION):
        r = np.where(cl_te, rng.choice(lr[ok_lr & cl_tr], len(te)) if (ok_lr & cl_tr).any() else 0.0,
                     rng.choice(lr[ok_lr & ~cl_tr], len(te)))
        exps.append(np.maximum((nu + 1) * np.exp(r) - 1, 1.0))
    ks_r, tn_r = [], []
    for k, rr in enumerate(ROLES):
        y, valido = con_rol(te, rr, lp)
        P[~valido, k] = 0.0
        y = LC.recalibrar(LC.aplicar(y, cols, fit, True), f)
        dr = [EX.muestras_predictivas(y, fam, rng, ne) for ne in exps]
        ks_r.append(np.concatenate([d[0] for d in dr], axis=1)), tn_r.append(np.concatenate([d[1] for d in dr], axis=1))
    sin = P.sum(axis=1) <= 0
    if sin.any():           # ningún rol con media previa en la liga de destino: el rol observado (casos marginales)
        P[sin, te["rol"].map({r: i for i, r in enumerate(ROLES)}).fillna(3).astype(int).to_numpy()[sin]] = 1.0
    P = P / P.sum(axis=1, keepdims=True)
    u = rng.random(ks_r[0].shape)
    cum = np.cumsum(P, axis=1)
    k = (u[:, :, None] >= cum[:, None, :-1]).sum(axis=2)            # índice del rol de cada draw
    ks = np.choose(k, ks_r)
    tn = np.choose(k, tn_r)
    out = _resumen(ks, tn, te, fam, rng, discreta=False)
    out["p_rol_real"] = P[np.arange(len(te)), te["rol"].map({r: i for i, r in enumerate(ROLES)}).fillna(3).astype(int).to_numpy()]
    out["sin_rol_previo"] = sin
    out["factor_recal"] = f
    return out


# ------------------------------------------------------------------ predicciones de la v5
def base_v5(cfg: dict) -> pd.DataFrame:
    x = pd.read_parquet(C.DIR_DATOS / "ligas" / "seleccion_base.parquet")
    cfg7 = C.cargar("configs/v5/f7.yaml")
    mods = LS.modelos_paso2(cfg7, sorted(int(a) for a in x["anio_obj"].unique()))
    y = LS.con_lambda_paso2(x, mods=mods)
    DIR.mkdir(parents=True, exist_ok=True)
    y.to_parquet(DIR / "base_v5.parquet")
    return y


def _resumen_muestras(y: pd.DataFrame, fam: str, rng, N_muestreo=None) -> pd.DataFrame:
    ks, tn = EX.muestras_predictivas(y, fam, rng, N_muestreo)
    return _resumen(ks, tn, y, fam, rng, discreta=(N_muestreo is None and fam != "normal"))


def _resumen(ks: np.ndarray, tn: np.ndarray, y: pd.DataFrame, fam: str, rng, discreta: bool) -> pd.DataFrame:
    """Media, cuantiles, CRPS y PIT de los draws de la tasa observada frente a la tasa observada de T. Con draws de
    otra exposición la comparación es en la escala de la tasa, sin la discreción común."""
    K, N = y["K"].to_numpy(float), y["N"].to_numpy(float)
    Nr = np.maximum(np.round(N), K) if fam == "binomial" else N
    obs = K / Nr
    r = eb.evaluar(ks, obs, discreta, rng)
    q = np.quantile(ks, CUANTILES, axis=1)
    qn = np.quantile(tn, [0.1, 0.9], axis=1)
    out = pd.DataFrame({"obs": obs, "media": ks.mean(axis=1), "crps": r["crps"].to_numpy(), "pit": r["pit"].to_numpy(),
                        "ancho_nivel80": qn[1] - qn[0]})
    for i, c in enumerate(CUANTILES):
        out[_q(c)] = q[i]
    return out


def predicciones_v5(cfg: dict, x: pd.DataFrame | None = None) -> pd.DataFrame:
    x = pd.read_parquet(DIR / "base_v5.parquet") if x is None else x
    from bbnorm5.carrera import datos as CD
    H = CD._hiper_preferido(pd.read_csv(DM.DIR / "hiperparametros.csv"))
    filas, coefs = [], []
    for T in cfg["examen"]["cortes_prueba"]:
        for met in DM.METRICAS:
            fam = DM.METRICAS[met][0]
            xm = x[x["metrica"] == met]
            tr, te = xm[xm["anio_obj"] < T], xm[xm["anio_obj"] == T]
            if te.empty or tr.empty:
                continue
            eta, vo = LC.observacion(tr, fam)
            for nom, (con_liga, bloques) in VARIANTES.items():
                cols = [c for b in bloques for c in LC.BLOQUES[b]]
                fit = None
                if cols:
                    trl = LC.aplicar(tr, [], None, con_liga)
                    r = eta - (trl["mu_prev"] + trl["m_nivel"]).to_numpy()
                    w = 1 / (trl["v_y_sin_muestreo"].to_numpy(float) + np.asarray(vo, float))
                    ok = np.isfinite(r) & np.isfinite(w)
                    grupos = np.concatenate([[k] * len(LC.BLOQUES[b]) for k, b in enumerate(bloques)])
                    fit = LC.ajustar_beta(tr[cols].to_numpy(float)[ok], r[ok], w[ok], grupos)
                    coefs.append(pd.DataFrame({"prueba": T, "metrica": met, "modelo": nom, "variable": cols,
                                               "beta": fit["beta"], "sd": np.sqrt(np.diag(fit["cov"]))}))
                y = LC.aplicar(te, cols, fit, con_liga)
                f = np.nan
                if con_liga:
                    f = LC.factor_recalibracion(tr, cols, fit, con_liga, eta, vo)
                    y = LC.recalibrar(y, f)
                rng = np.random.default_rng((cfg["semilla"] + zlib.crc32(f"{T}|{met}|{nom}".encode())) % 2 ** 32)
                ident = pd.DataFrame({"persona_v5": y["persona_v5"].to_numpy(), "liga": y["liga"].to_numpy(),
                                      "liga_ult": y["liga_ult"].to_numpy(), "rol": y["rol"].to_numpy(),
                                      "cambio_liga": y["cl"].to_numpy(), "temporadas_hist": y["temporadas_hist"].to_numpy(),
                                      "N": y["N"].to_numpy(float), "N_ult": y["N_ult"].to_numpy(float),
                                      "min_temp": y["min_temp"].to_numpy(float), "edad": y["edad"].to_numpy(float),
                                      "anio": T, "metrica": met, "modelo": nom, "factor_recal": f})
                filas.append(pd.concat([ident, _resumen_muestras(y, fam, rng)], axis=1))
                if nom == "final":
                    # misma predicción con la exposición de la temporada anterior (la que se conoce en t)
                    nu = np.where(np.isfinite(y["N_ult"].to_numpy(float)) & (y["N_ult"].to_numpy(float) > 0),
                                  y["N_ult"].to_numpy(float), y["N"].to_numpy(float))
                    filas.append(pd.concat([ident.assign(modelo="final_exposicion_t"),
                                            _resumen_muestras(y, fam, rng, nu)], axis=1))
            lp = EX._liga_previa(H, met, T)[["liga", "rol", "mu_prev"]]
            for nom, bloques in EX_ANTE.items():
                rng = np.random.default_rng((cfg["semilla"] + zlib.crc32(f"{T}|{met}|{nom}".encode())) % 2 ** 32)
                filas.append(pd.concat([ident.assign(modelo=nom, factor_recal=np.nan).drop(columns="factor_recal"),
                                        exante(tr, te, fam, bloques, lp, eta, vo, rng)], axis=1))
            print(f"  v5 {T} {met}", flush=True)
    p = pd.concat(filas, ignore_index=True)
    p.to_parquet(DIR / "predicciones_v5.parquet")
    pd.concat(coefs).to_csv(DIR / "coeficientes_contexto.csv", index=False)
    return p


# ------------------------------------------------------------------ banco de fichajes reales con la v3.3 aplicada
def banco_v33() -> pd.DataFrame:
    """Producción aplicada de la v3.3 por fichaje (centro e intervalos 50/80/90) y el observado con el equipo real."""
    previo = os.environ.get("CERNO_SIMULADOR")
    os.environ["CERNO_SIMULADOR"] = "v32"          # las ejecuciones del examen V32_corte viven en la carpeta v3_2
    try:
        from bbfit import v32
        c32 = v32.cfg()
        EE = v32.cargar_ejecuciones(c32)
        E = EE["V32_corte"]
        e_all = E["completo"].reset_index(drop=True)
        cortes = sorted(e_all["corte"].unique())
        filas = []
        for k, t in enumerate(cortes):
            prev_c = cortes[:k]
            dec = v32.decidir_dos_fuentes(EE, prev_c, c32) if prev_c else None
            e_t = e_all[e_all["corte"] == t].reset_index(drop=True)
            prev = e_all[e_all["corte"].isin(prev_c)].reset_index(drop=True) if prev_c else None
            r = v32.aplicar(e_t, E, dec, prev, c32, t, cortes)
            fuente = "motor" if dec is None else dec["produccion"]
            for m, p in r["prod"].items():
                if m == "C":
                    continue
                x = r["e"][["persona_id", "nombre", "corte", "liga_o", "team_o", "liga_d", "team_d", "temporada_d",
                            "min_total_real"]].copy()
                x["metrica"], x["fuente_v33"] = m, fuente
                x["real"] = r["e"][f"{m}_real"].to_numpy(float)
                for c in ("pred", "lo50", "hi50", "lo80", "hi80", "lo90", "hi90"):
                    x[f"v33_{c}"] = p[c].to_numpy(float)
                filas.append(x)
    finally:
        if previo is None:
            os.environ.pop("CERNO_SIMULADOR", None)
        else:
            os.environ["CERNO_SIMULADOR"] = previo
    b = pd.concat(filas, ignore_index=True)
    # v4.2 (motor D2, brazo que decide): sólo el centro de producción (sus intervalos aplicados no se guardaron)
    f42 = C.RAIZ / "data" / "modelos" / "v4_2" / "motor" / "validacion" / "v42" / "predicciones.csv.gz"
    if f42.exists():
        mets = sorted(b["metrica"].unique())
        v = pd.read_csv(f42, usecols=["persona_id", "corte", "liga_d", "team_d"] + [f"v_{m}_pred" for m in mets],
                        low_memory=False)
        v = v.melt(id_vars=["persona_id", "corte", "liga_d", "team_d"], var_name="metrica", value_name="v42_pred")
        v["metrica"] = v["metrica"].str[2:-5]
        b = b.merge(v.drop_duplicates(["persona_id", "corte", "liga_d", "team_d", "metrica"]),
                    on=["persona_id", "corte", "liga_d", "team_d", "metrica"], how="left")
    # persona_v5 (el banco usa la persona del crosswalk)
    per = pd.read_csv(C.DIR_DATOS / "limpios" / "entidades" / "personas_v5.csv", dtype=str)
    mp = per.groupby("persona_crosswalk")["persona_v5"].agg(lambda s: s.mode().iloc[0])
    b["persona_v5"] = b["persona_id"].map(mp)
    b["anio"] = b["temporada_d"].str[:4].astype(int)
    DIR.mkdir(parents=True, exist_ok=True)
    b.to_parquet(DIR / "banco_v33.parquet")
    return b


# ------------------------------------------------------------------ puntuaciones
def wis(y, centro, lo: dict, hi: dict) -> np.ndarray:
    """Weighted interval score con intervalos centrales {nivel: (lo, hi)} y centro: aproximación del CRPS."""
    y = np.asarray(y, float)
    tot = 0.5 * np.abs(y - np.asarray(centro, float))
    for a in lo:
        al = 1 - a / 100
        l, h = np.asarray(lo[a], float), np.asarray(hi[a], float)
        tot = tot + al / 2 * ((h - l) + 2 / al * np.maximum(l - y, 0) + 2 / al * np.maximum(y - h, 0))
    return tot / (len(lo) + 0.5)


def _boot_ratio(personas: np.ndarray, a: np.ndarray, b: np.ndarray, B: int, rng) -> tuple[float, float, float]:
    """mean(a)/mean(b) − 1 con IC 95 % por bootstrap de personas."""
    df = pd.DataFrame({"p": personas, "a": a, "b": b}).groupby("p")[["a", "b"]].sum()
    A, Bv = df["a"].to_numpy(), df["b"].to_numpy()
    n = len(df)
    r = np.empty(B)
    for i in range(B):
        k = rng.integers(0, n, n)
        r[i] = A[k].sum() / Bv[k].sum() - 1
    return float(A.sum() / Bv.sum() - 1), float(np.quantile(r, 0.025)), float(np.quantile(r, 0.975))


def recalibrar_oraculo(d: pd.DataFrame, pre: str, centro: str) -> pd.DataFrame:
    """Intervalos de la v3.3 reescalados por métrica para que su cobertura en la propia prueba sea la nominal
    (favorece a la v3.3: usa los datos de la prueba). Sólo como análisis de sensibilidad."""
    d = d.copy()
    for m, g in d.groupby("metrica"):
        y, c = g["y"].to_numpy(float), g[centro].to_numpy(float)
        for a in NIVELES:
            lo, hi = g[f"{pre}lo{a}"].to_numpy(float), g[f"{pre}hi{a}"].to_numpy(float)
            sl, sh = np.maximum(c - lo, 1e-9), np.maximum(hi - c, 1e-9)
            z = np.where(y < c, (c - y) / sl, (y - c) / sh)        # factor que haría entrar cada caso
            f = float(np.nanquantile(z, a / 100))
            d.loc[g.index, f"{pre}lo{a}"] = c - f * sl
            d.loc[g.index, f"{pre}hi{a}"] = c + f * sh
    return d


def comparar(cfg: dict, p: pd.DataFrame | None = None, b: pd.DataFrame | None = None) -> dict:
    p = pd.read_parquet(DIR / "predicciones_v5.parquet") if p is None else p
    b = pd.read_parquet(DIR / "banco_v33.parquet") if b is None else b
    rng = np.random.default_rng(cfg["semilla"])
    B = int(cfg["examen"].get("bootstrap", 1000))
    bb = b[b["metrica"].isin(COMUNES) & (b["min_total_real"] >= cfg["examen"]["min_minutos_destino"])
           & b["anio"].isin(cfg["examen"]["cortes_prueba"])].copy()
    # Factor de definición por métrica (la v3.3 estima las posesiones con otra fórmula: pts/100 y STL/100 ≈ +1,8 %):
    # mediana de real / (100·obs v5) en el corte 2021-22 del banco (fuera de la prueba: sin fugas)
    bv = pd.read_parquet(DIR / "base_v5.parquet", columns=["persona_v5", "liga", "anio_obj", "metrica", "K", "N"])
    bv = bv[bv["metrica"].isin(COMUNES)].drop_duplicates(["persona_v5", "liga", "anio_obj", "metrica"])
    cal = b[(b["corte"] == "2021-22") & b["metrica"].isin(COMUNES) & (b["min_total_real"] >= 300)].merge(
        bv, left_on=["persona_v5", "liga_d", "anio", "metrica"], right_on=["persona_v5", "liga", "anio_obj", "metrica"])
    k = (cal["real"] / (100 * cal["K"] / cal["N"])).replace([np.inf, -np.inf], np.nan).groupby(cal["metrica"]).median()
    pv = p[p["metrica"].isin(COMUNES)].copy()
    esc = 100.0 * pv["metrica"].map(k).fillna(1.0).to_numpy()
    for c in ["obs", "media"] + [_q(q) for q in CUANTILES]:
        pv[c] = pv[c] * esc
    claves = ["persona_v5", "liga", "anio", "metrica"]
    ancho = pv.pivot_table(index=claves, columns="modelo", values=[_q(q) for q in CUANTILES] + ["media", "obs", "crps"],
                           aggfunc="first")
    ancho.columns = [f"{m}__{v}" for v, m in ancho.columns]
    ancho = ancho.reset_index()
    d = bb.merge(ancho, left_on=["persona_v5", "liga_d", "anio", "metrica"], right_on=claves, how="inner")
    n_banco, n_cruce = len(bb), len(d)
    # el observado de la v5 es la liga entera y el del banco el equipo de destino: fuera los casos en que difieren
    # más de un 5 % tras el factor de definición (varios equipos en la liga de destino)
    d["obs_v5"] = d["final__obs"]
    d = d[np.isfinite(d["real"]) & (np.abs(d["real"] / d["obs_v5"].replace(0, np.nan) - 1) <= 0.05)].copy()
    # intervalos recortados al soporte de la métrica (porcentajes en [0, 100], tasas ≥ 0): sólo puede favorecer a quien
    # se salga de él (en USG% la v3.3 tiene un 1 % de casos con límites de ±10¹⁰)
    techo = np.where(d["metrica"].str.endswith("_pct"), 100.0, np.inf)
    cols = [c for c in d.columns if c.startswith("v33_") or "__q" in c or c.endswith("__media")]
    for c in cols:
        d[c] = np.clip(d[c].to_numpy(float), 0.0, techo)
    completos = d[[c for c in cols if c.startswith("v33_") or any(m in c for m in ("ex_ante__", "final__"))]].notna().all(axis=1)
    d = d[completos].copy()
    d["y"] = d["real"]
    out = {"casos_banco": int(n_banco), "con_prediccion_v5": int(n_cruce), "comparables": int(len(d)),
           "personas": int(d["persona_v5"].nunique()), "factor_definicion": k.round(4).to_dict()}

    def puntuar(x: pd.DataFrame, modelo: str) -> np.ndarray:
        if modelo.startswith("v33"):
            pre = "v33_"
            return wis(x["y"], x["v33_pred"], {a: x[f"{pre}lo{a}"] for a in NIVELES}, {a: x[f"{pre}hi{a}"] for a in NIVELES})
        return wis(x["y"], x[f"{modelo}__q50"], {a: x[f"{modelo}__{_q(l)}"] for a, (l, h) in NIVELES.items()},
                   {a: x[f"{modelo}__{_q(h)}"] for a, (l, h) in NIVELES.items()})

    orac = recalibrar_oraculo(d, "v33_", "v33_pred")
    filas = []
    for m, g in list(d.groupby("metrica")) + [("todas", d)]:
        go = orac.loc[g.index]
        s33 = puntuar(g, "v33")
        s33o = puntuar(go, "v33")
        fila = {"metrica": m, "casos": len(g), "personas": g["persona_v5"].nunique()}
        for mod in ("ex_ante", "final", "final_exposicion_t", "base_F4"):
            s5 = puntuar(g, mod)
            # «todas»: cada métrica normalizada por el WIS medio de la v3.3 en esa métrica
            if m == "todas":
                esc = g.groupby("metrica").apply(lambda h: puntuar(h, "v33").mean())
                w = g["metrica"].map(esc).to_numpy()
                a, bref, bor = s5 / w, s33 / w, s33o / w
            else:
                a, bref, bor = s5, s33, s33o
            fila[f"wis_{mod}_frente_v33"], fila[f"ic_lo_{mod}"], fila[f"ic_hi_{mod}"] = _boot_ratio(
                g["persona_v5"].to_numpy(), a, bref, B, rng)
            if mod == "ex_ante":
                fila["wis_ex_ante_frente_v33_oraculo"], fila["ic_lo_oraculo"], fila["ic_hi_oraculo"] = _boot_ratio(
                    g["persona_v5"].to_numpy(), a, bor, B, rng)
        y = g["y"].to_numpy(float)
        for mod, lo, hi in (("v33", g["v33_lo80"], g["v33_hi80"]), ("ex_ante", g["ex_ante__q10"], g["ex_ante__q90"]),
                            ("final", g["final__q10"], g["final__q90"])):
            fila[f"cob80_{mod}"] = float(((y >= lo) & (y <= hi)).mean())
            fila[f"ancho80_{mod}"] = float(np.median(hi - lo))
        for mod in ("ex_ante", "final"):
            fila[f"ratio_ancho80_{mod}_v33"] = float(np.median((g[f"{mod}__q90"] - g[f"{mod}__q10"]) /
                                                               np.maximum(g["v33_hi80"] - g["v33_lo80"], 1e-9)))
            fila[f"mae_{mod}"] = float(np.nanmean(np.abs(y - g[f"{mod}__media"])))
        fila["mae_v33"] = float(np.nanmean(np.abs(y - g["v33_pred"])))
        if "v42_pred" in g:
            fila["mae_v42"] = float(np.nanmean(np.abs(y - g["v42_pred"])))
        filas.append(fila)
    tabla = pd.DataFrame(filas)
    tabla.to_csv(DIR / "examen_fichajes.csv", index=False)
    d.to_parquet(DIR / "examen_fichajes_casos.parquet")
    # criterio 11: navaja del estilo de liga y de compañeros (CRPS propio de la v5, todas las métricas, mismos fichajes)
    nav = []
    fich = d[["persona_v5", "liga_d", "anio"]].drop_duplicates().rename(columns={"liga_d": "liga"})
    q = p.merge(fich, on=["persona_v5", "liga", "anio"])
    pv2 = q.pivot_table(index=["persona_v5", "liga", "anio", "metrica"], columns="modelo", values="crps").dropna()
    pv2 = pv2.div(pv2.groupby(level="metrica")["ex_ante"].transform("mean"), axis=0)
    per = pv2.index.get_level_values("persona_v5").to_numpy()
    for ref, sin in (("ex_ante", "ex_ante_sin_estilo_liga"), ("ex_ante", "ex_ante_sin_companeros"),
                     ("final", "final_sin_estilo_liga"), ("final", "final_sin_companeros"), ("ex_ante", "base_F4")):
        r, lo, hi = _boot_ratio(per, pv2[ref].to_numpy(), pv2[sin].to_numpy(), B, rng)
        nav.append({"comparacion": f"{ref} frente a {sin}", "dif_crps_rel": r, "ic95_lo": lo, "ic95_hi": hi,
                    "supera_navaja": hi < 0, "casos": len(pv2)})
    pd.DataFrame(nav).to_csv(DIR / "navaja_fichajes.csv", index=False)
    out["tabla"] = tabla.round(4).to_dict(orient="records")
    out["navaja"] = nav
    return out
