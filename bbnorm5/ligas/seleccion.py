"""F7 · Sesgo de selección en los traspasos y paso 2 de la F6 (traspasos entre temporadas en λ).

**Problema.** Quien sube de liga suele hacerlo tras una temporada buena, que en parte es suerte. Si se toma esa temporada
como su nivel, en la liga nueva rinde menos de lo esperado (regresión a la media) y λ sale sesgado: la liga de destino
parece más difícil de lo que es.

**Datos.** Para cada persona con temporada en T y temporada previa, de la base de la proyección F4 sin fugas
(`seleccion_base.parquet`): su nivel encogido de la F4 (posición relativa a + media de su rol en la liga de origen),
su última temporada observada en bruto y su temporada T observada.

**Dirección del cambio.** Fuerza de cada liga = −λ de pts/100 de la F6.1 (NUTS, media de las temporadas): en una liga
más fuerte el mismo jugador anota menos. Sube si la fuerza de destino supera a la de origen en más de 0,5 puntos por 100
posesiones, baja si es al revés, y si no es un cambio lateral.

**Modelo de selección.** Logística multinomial (seguir / subir / bajar / lateral) con la temporada previa (posición
relativa en pts, USG%, AST%, T3% y DREB%), los minutos, la edad, el rol, la liga de origen y el nº de temporadas.

**λ con traspasos (GLS por métrica; puentes intra-temporada + traspasos con temporada objetivo < T):**
- `crudo`: d = η_T − η_{t, observado}. Es el sesgo de regresión a la media a la vista.
- `encogido`: d = η_T − (μ_origen + a_F4). El nivel encogido de la F4 ya descuenta la suerte de la temporada previa.
- `encogido_ipw`: además, cada traspaso pesa P(dirección)/P(dirección | x) (estabilizado y recortado).
- `encogido_heckman`: además, el término de Mills de un probit de subir (y otro de bajar) como covariable de los
  traspasos (selección en no observables, identificada por la no linealidad).

**Prueba** (encargo §11): residuo de la temporada T de quienes cambian de liga, predicha con λ de cada variante, por
dirección del cambio. Debe ser ≈ 0 en subidas y bajadas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from bbnorm5 import config as C
from bbnorm5.carrera import datos as CD
from bbnorm5.ligas import contexto as LC
from bbnorm5.ligas import datos as LD
from bbnorm5.ligas import resumen as LR
from bbnorm5.medida import datos as DM

DIR = C.DIR_DATOS / "ligas"
UMBRAL = 0.005               # 0,5 puntos por 100 posesiones
FEAT_Y = ["pts_p100", "usg_pct", "ast_pct", "t3_pct", "dreb_pct"]
VARIANTES = ["paso1", "crudo", "encogido", "encogido_ipw", "encogido_heckman"]


def fuerza_ligas() -> pd.Series:
    z = LR.cargar_lambda(False)["pts_p100"]
    return pd.Series(-z["lam"].mean(axis=(0, 2)), index=z["ligas"])


def preparar(cfg: dict) -> pd.DataFrame:
    x = pd.read_parquet(DIR / "seleccion_base.parquet")
    o = CD.cargar()
    # última temporada en bruto (absoluta) y minutos de esa temporada
    o["eta_abs"] = o["y"] + o["mu"]
    ult = o[["persona_v5", "temporada", "metrica", "eta_abs", "v", "min_temp"]].rename(
        columns={"temporada": "temporada_ult", "eta_abs": "eta_ult", "v": "v_ult", "min_temp": "min_ult"})
    x = x.merge(ult, on=["persona_v5", "temporada_ult", "metrica"], how="left")
    eta, vo = [], []
    for met, g in x.groupby("metrica", sort=False):
        e, v = LC.observacion(g, DM.METRICAS[met][0])
        eta.append(pd.Series(e, index=g.index)), vo.append(pd.Series(np.asarray(v, float), index=g.index))
    x["eta_obs"], x["v_obs"] = pd.concat(eta), pd.concat(vo)
    f = fuerza_ligas()
    dif = x["liga"].map(f) - x["liga_ult"].map(f)
    x["direccion"] = np.select([x["cl"] == 0, dif > UMBRAL, dif < -UMBRAL], ["sigue", "sube", "baja"], "lateral")
    # rasgos de selección (persona-temporada): posición relativa en la temporada previa
    piv = o[o["metrica"].isin(FEAT_Y)].pivot_table(index=["persona_v5", "temporada"], columns="metrica", values="y")
    piv.columns = [f"prev_{c}" for c in piv.columns]
    x = x.merge(piv, left_on=["persona_v5", "temporada_ult"], right_index=True, how="left")
    return x


def matriz_seleccion(p: pd.DataFrame, ligas: list[str]) -> np.ndarray:
    X = [p[[f"prev_{c}" for c in FEAT_Y]].fillna(0).to_numpy(float),
         np.log1p(p["min_ult"].fillna(0)).to_numpy(float)[:, None],
         ((p["edad"].fillna(26) - 26) / 4).to_numpy(float)[:, None], p["edad"].isna().to_numpy(float)[:, None],
         np.log1p(p["temporadas_hist"]).to_numpy(float)[:, None]]
    X += [(p["rol"] == r).to_numpy(float)[:, None] for r in ("E", "A", "I")]
    X += [(p["liga_ult"] == l).to_numpy(float)[:, None] for l in ligas]
    return np.hstack(X)


def modelo_seleccion(tr: pd.DataFrame, te: pd.DataFrame, recorte) -> tuple[pd.DataFrame, dict]:
    """Probabilidades de dirección (multinomial) y probits de subir y bajar; pesos IPW e inversa de Mills."""
    from sklearn.linear_model import LogisticRegression
    ligas = sorted(set(tr["liga_ult"]))
    p_tr = tr.drop_duplicates(["persona_v5", "anio_obj"])
    Xtr = matriz_seleccion(p_tr, ligas)
    mn = LogisticRegression(max_iter=2000, C=1.0).fit(Xtr, p_tr["direccion"])
    marg = p_tr["direccion"].value_counts(normalize=True)
    prob = {}
    for nom, d in (("sube", "sube"), ("baja", "baja")):
        y = (p_tr["direccion"] == d).to_numpy(float)
        prob[nom] = probit(Xtr, y)

    def anotar(df):
        p = df.drop_duplicates(["persona_v5", "anio_obj"])
        X = matriz_seleccion(p, ligas)
        P = pd.DataFrame(mn.predict_proba(X), columns=mn.classes_, index=p.index)
        pk = P.to_numpy()[np.arange(len(p)), P.columns.get_indexer(p["direccion"])]
        w = p["direccion"].map(marg).to_numpy() / np.maximum(pk, 1e-6)
        out = pd.DataFrame({"persona_v5": p["persona_v5"], "anio_obj": p["anio_obj"], "p_dir": pk, "w_ipw": w})
        for nom in ("sube", "baja"):
            xb = np.c_[np.ones(len(X)), X] @ prob[nom]
            out[f"imr_{nom}"] = np.where(p["direccion"] == nom, stats.norm.pdf(xb) / np.maximum(stats.norm.cdf(xb), 1e-9), 0.0)
        return df.merge(out, on=["persona_v5", "anio_obj"], how="left")
    tr2, te2 = anotar(tr), anotar(te)
    lo, hi = np.nanquantile(tr2.loc[tr2["cl"] > 0, "w_ipw"], recorte)
    for d in (tr2, te2):
        d["w_ipw"] = d["w_ipw"].clip(lo, hi)
    diag = {"clases": list(mn.classes_), "auc_sube": _auc(p_tr["direccion"] == "sube", np.c_[np.ones(len(Xtr)), Xtr] @ prob["sube"]),
            "auc_baja": _auc(p_tr["direccion"] == "baja", np.c_[np.ones(len(Xtr)), Xtr] @ prob["baja"]),
            "peso_ipw_q": [float(lo), float(hi)]}
    return pd.concat([tr2, te2]), diag


def probit(X: np.ndarray, y: np.ndarray, l2: float = 1e-3) -> np.ndarray:
    """Probit por máxima verosimilitud (gradiente exacto), con constante y una L2 mínima para la estabilidad."""
    from scipy import optimize
    Xc = np.c_[np.ones(len(X)), X]

    def f(b):
        xb = Xc @ b
        q = 2 * y - 1
        lp = stats.norm.logcdf(q * xb)
        g = q * np.exp(stats.norm.logpdf(xb) - lp)
        return -lp.sum() + 0.5 * l2 * (b[1:] ** 2).sum(), -(Xc.T @ g) + l2 * np.r_[0, b[1:]]
    return optimize.minimize(f, np.zeros(Xc.shape[1]), jac=True, method="L-BFGS-B").x


def _auc(y, s):
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(np.asarray(y), np.asarray(s)))


def gls_paso2(intra: pd.DataFrame, inter: pd.DataFrame, metrica: str, variante: str) -> dict:
    """GLS de λ con puentes intra (contexto de la F6.1) y traspasos (variante); prior débil en λ."""
    a = intra[intra["metrica"] == metrica]
    b = inter[inter["metrica"] == metrica] if variante != "paso1" else inter.iloc[:0]
    ligas = sorted(set(a["liga_a"]) | set(a["liga_b"]) | set(b["liga_ult"]) | set(b["liga"]) | {"acb"})
    ligas = ["acb"] + [l for l in ligas if l != "acb"]
    il = {l: i for i, l in enumerate(ligas)}
    L = len(ligas) - 1
    extra = ["imr_sube", "imr_baja"] if variante == "encogido_heckman" else []

    def bloque(la, lb, ctx, ex, n):
        A = np.zeros((n, L))
        ia, ib = np.array([il[v] for v in la]), np.array([il[v] for v in lb])
        r = np.arange(n)
        A[r[ib > 0], ib[ib > 0] - 1] += 1
        A[r[ia > 0], ia[ia > 0] - 1] -= 1
        return np.hstack([A, ctx, ex])
    Xa = bloque(a["liga_a"], a["liga_b"], a[LD.CONTEXTO].to_numpy(float), np.zeros((len(a), len(extra))), len(a))
    ya, va, wa = a["d"].to_numpy(float), a["var"].to_numpy(float), np.ones(len(a))
    if len(b):
        if variante == "crudo":
            yb = (b["eta_obs"] - b["eta_ult"]).to_numpy(float)
            vb = (b["v_obs"] + b["v_ult"] + 2 * b["s2_u"]).to_numpy(float)
        else:
            yb = (b["eta_obs"] - (b["mu_origen"] + b["m_nivel"])).to_numpy(float)
            vb = (b["v_obs"] + b["v_y_sin_muestreo"]).to_numpy(float)
        wb = b["w_ipw"].to_numpy(float) if variante == "encogido_ipw" else np.ones(len(b))
        Xb = bloque(b["liga_ult"], b["liga"], np.zeros((len(b), len(LD.CONTEXTO))),
                    b[extra].to_numpy(float) if extra else np.zeros((len(b), 0)), len(b))
        ok = np.isfinite(yb) & np.isfinite(vb)
        X, y, v, w = np.vstack([Xa, Xb[ok]]), np.r_[ya, yb[ok]], np.r_[va, vb[ok]], np.r_[wa, wb[ok]]
    else:
        X, y, v, w = Xa, ya, va, wa
    esc = max(float(np.std(y)), 1e-3)          # prior débil de λ: 2 DT de todas las diferencias (intra + traspasos)
    pr = np.r_[np.full(L, 1 / (2 * esc) ** 2), np.full(len(LD.CONTEXTO), 1 / 0.25), np.full(len(extra), 1 / 1.0)]
    s2 = 0.0
    for _ in range(10):
        ww = w / (v + s2)
        H = X.T @ (X * ww[:, None]) + np.diag(pr)
        beta = np.linalg.solve(H, X.T @ (ww * y))
        res = y - X @ beta
        s2n = max(float(np.average(res ** 2 - v, weights=w)), 0.0)
        if abs(s2n - s2) < 1e-6:
            break
        s2 = s2n
    cov = np.linalg.inv(H)
    lam = np.r_[0.0, beta[:L]]
    cl = np.zeros((L + 1, L + 1))
    cl[1:, 1:] = cov[:L, :L]
    return {"ligas": ligas, "lambda": lam, "cov": cl, "theta": beta[L + len(LD.CONTEXTO):], "s_c2": s2,
            "n_inter": int(len(b)), "beta_ctx": beta[L:L + len(LD.CONTEXTO)]}


def modelos_paso2(cfg: dict, anios: list[int], variante: str = "encogido") -> dict:
    """GLS del paso 2 por año objetivo y métrica, con puentes intra y traspasos anteriores al año (sin fugas)."""
    x = preparar(cfg)
    intra = pd.read_parquet(DIR / "pares_intra.parquet")
    mods = {}
    for T in anios:
        inter = x[(x["anio_obj"] < T) & (x["cl"] > 0)]
        it = intra[intra["temporada"].str[:4].astype(int) < T]
        for met in DM.METRICAS:
            mods[(T, met, variante)] = gls_paso2(it, inter, met, variante)
    return mods


def ejecutar(cfg: dict) -> dict:
    x = preparar(cfg)
    intra = pd.read_parquet(DIR / "pares_intra.parquet")
    e = cfg["examen"]
    casos, lams, diags, modelos = [], [], [], {}
    for T in e["cortes_prueba"]:
        tr = x[(x["anio_obj"] < T)]
        te = x[(x["anio_obj"] == T)]
        xs, diag = modelo_seleccion(tr, te, e["recorte_pesos"])
        diags.append({"corte": T, **diag})
        tr, te = xs[xs["anio_obj"] < T], xs[xs["anio_obj"] == T]
        inter = tr[(tr["cl"] > 0)]
        it = intra[intra["temporada"].str[:4].astype(int) < T]
        mov = te[(te["cl"] > 0)].copy()
        for met in DM.METRICAS:
            mm = mov[mov["metrica"] == met]
            for var in VARIANTES:
                g = gls_paso2(it, inter, met, var)
                modelos[(T, met, var)] = g
                il = {l: i for i, l in enumerate(g["ligas"])}
                ok = mm["liga"].isin(il) & mm["liga_ult"].isin(il)
                q = mm[ok]
                ia, ib = q["liga_ult"].map(il).to_numpy(), q["liga"].map(il).to_numpy()
                dl = g["lambda"][ib] - g["lambda"][ia]
                vl = g["cov"][ia, ia] + g["cov"][ib, ib] - 2 * g["cov"][ia, ib]
                sel = (q[["imr_sube", "imr_baja"]].to_numpy(float) @ g["theta"]) if var == "encogido_heckman" else 0.0
                pred = q["mu_origen"] + q["m_nivel"] + dl + sel
                r = q["eta_obs"] - pred
                sd = np.sqrt(q["v_y_sin_muestreo"] + vl + q["v_obs"])
                casos.append(pd.DataFrame({"corte": T, "metrica": met, "variante": var, "persona_v5": q["persona_v5"],
                                           "direccion": q["direccion"], "liga_ult": q["liga_ult"], "liga": q["liga"],
                                           "residuo": r.to_numpy(), "z": (r / sd).to_numpy()}))
                for l in g["ligas"]:
                    lams.append({"corte": T, "metrica": met, "variante": var, "liga": l,
                                 "lambda": g["lambda"][il[l]], "sd": float(np.sqrt(g["cov"][il[l], il[l]])),
                                 "n_inter": g["n_inter"], "theta": ";".join(f"{t:.3f}" for t in g["theta"])})
        print(f"  corte {T}: {len(mov)} filas de cambio de liga", flush=True)
    c = pd.concat(casos, ignore_index=True)
    c.to_parquet(DIR / "seleccion_casos.parquet")
    pd.DataFrame(lams).to_csv(DIR / "lambda_paso2.csv", index=False)
    pd.DataFrame(diags).to_json(DIR / "seleccion_diagnostico.json", orient="records", indent=1)
    import pickle
    with open(DIR / "lambda_paso2_modelos.pkl", "wb") as f:
        pickle.dump(modelos, f)
    s = c.groupby(["variante", "direccion"]).agg(n=("z", "size"), z_medio=("z", "mean"), residuo_medio=("residuo", "mean"))
    s.to_csv(DIR / "sesgo_por_direccion.csv")
    comparar_variantes(c, cfg["semilla"]).to_csv(DIR / "seleccion_variantes.csv", index=False)
    return {"filas": len(c), "z_sube": s["z_medio"].xs("sube", level="direccion").round(3).to_dict()}


def proyeccion_paso2(cfg: dict, variante: str = "encogido") -> pd.DataFrame:
    """La proyección en contexto de la F6.2 con λ del paso 2 (puentes intra + traspasos, misma variante para todos los
    cortes, sin fugas) en lugar de λ sólo con puentes intra. Rehace las columnas que dependen de λ y repite el examen."""
    x = con_lambda_paso2(pd.read_parquet(DIR / "contexto_base.parquet"), variante)
    x.to_parquet(DIR / "contexto_base_paso2.parquet")
    return LC.examen(cfg, x, sufijo="_paso2")


def con_lambda_paso2(x: pd.DataFrame, variante: str = "encogido", mods: dict | None = None) -> pd.DataFrame:
    """Rehace en la base de la proyección en contexto las columnas que dependen de λ con el GLS del paso 2 de cada
    temporada objetivo (estimado sólo con temporadas anteriores: sin fugas). `mods`: {(año, métrica, variante): GLS};
    por defecto, los del examen de la F7."""
    import pickle
    from bbnorm5.ligas import gls
    if mods is None:
        with open(DIR / "lambda_paso2_modelos.pkl", "rb") as f:
            mods = pickle.load(f)
    partes = []
    for (anio, met), g in x.groupby(["anio_obj", "metrica"], sort=False):
        m = mods.get((anio, met, variante))
        if m is None:
            continue
        d = [gls.diferencia(m, a, b) for a, b in zip(g["liga_ult"], g["liga"])]
        dl, vl = np.array([z[0] for z in d]), np.array([z[1] for z in d])
        ok = (g["cl"] > 0) & np.isfinite(dl) & g["mu_origen"].notna()
        g = g.copy()
        g["delta_lambda"] = np.where(ok, dl, 0.0)
        g["var_lambda"] = np.where(ok, vl, 0.0)
        g["ajuste_liga"] = np.where(ok, g["mu_origen"] - g["mu_prev"] + dl, 0.0)
        for p in LC.PERFILES:
            g[f"dl_{p}"] = g["delta_lambda"] * g[f"z_{p}"]
        for r in ("E", "I"):
            g[f"dl_rol_{r}"] = g["delta_lambda"] * (g["rol"] == r)
        partes.append(g)
    return pd.concat(partes, ignore_index=True)


def pares_paso2(cfg: dict, variante: str = "encogido") -> pd.DataFrame:
    """Puentes intra-temporada + traspasos entre temporadas (nivel encogido de la F4 como origen) en el formato de
    `ligas/datos.pares`, para la NUTS del paso 2. Las diferencias de los traspasos se escalan igual que las intra (la
    estandarización por métrica de `modelo.indices` usa todas las filas)."""
    x = preparar(cfg)
    m = x[(x["cl"] > 0)].copy()
    d = m["eta_obs"] - (m["mu_origen"] + m["m_nivel"])
    v = m["v_obs"] + m["v_y_sin_muestreo"]
    inter = pd.DataFrame({"puente": -1, "persona_v5": m["persona_v5"], "temporada": m["anio_obj"].map(lambda a: f"{a}-{str(a + 1)[2:]}"),
                          "temporada_a": m["temporada_ult"], "liga_a": m["liga_ult"], "liga_b": m["liga"],
                          "tipo": "traspaso_entre_temporadas", "metrica": m["metrica"], "d": d, "var": v})
    for c in LD.CONTEXTO:
        inter[c] = 0.0
    inter = inter[np.isfinite(inter["d"]) & np.isfinite(inter["var"]) & (inter["var"] > 0)]
    intra = pd.read_parquet(DIR / "pares_intra.parquet")
    intra["temporada_a"] = intra["temporada"]
    out = pd.concat([intra, inter], ignore_index=True)
    out.to_parquet(DIR / "pares_paso2.parquet")
    return out


def comparar_variantes(c: pd.DataFrame, semilla: int, B: int = 400) -> pd.DataFrame:
    """CRPS normal de cada variante en los cambios de liga, relativo al paso 1 y al encogido (IC 95 % por bootstrap de
    personas), cobertura del 80 % y sesgo medio por dirección."""
    c = c[np.isfinite(c["z"]) & (c["z"] != 0)].copy()
    sd, z = c["residuo"] / c["z"], c["z"]
    c["crps"] = sd * (z * (2 * stats.norm.cdf(z) - 1) + 2 * stats.norm.pdf(z) - 1 / np.sqrt(np.pi))
    c["cub80"] = z.abs() <= stats.norm.ppf(0.9)
    w = c.pivot_table(index=["corte", "metrica", "persona_v5", "direccion"], columns="variante", values="crps").dropna()
    per = w.groupby(level="persona_v5").sum()
    P, n = per.to_numpy(), len(per)
    rng = np.random.default_rng(semilla)
    Bs = np.array([P[rng.integers(0, n, n)].sum(0) for _ in range(B)])
    cols = list(per.columns)
    filas = []
    for j, v in enumerate(cols):
        fila = {"variante": v}
        for ref in ("paso1", "encogido"):
            k = cols.index(ref)
            b = Bs[:, j] / Bs[:, k] - 1
            fila[f"dif_crps_{ref}"] = P.sum(0)[j] / P.sum(0)[k] - 1
            fila[f"ic95_lo_{ref}"], fila[f"ic95_hi_{ref}"] = np.quantile(b, [0.025, 0.975])
        g = c[c["variante"] == v]
        fila["cobertura80"] = g["cub80"].mean()
        for d in ("sube", "baja"):
            fila[f"z_{d}"] = g.loc[g["direccion"] == d, "z"].mean()
        filas.append(fila)
    return pd.DataFrame(filas)
