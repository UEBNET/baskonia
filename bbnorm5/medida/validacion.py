"""F3.2 · Ajuste por liga-temporada y validación decisiva: ajustar con la primera mitad de los partidos de cada
jugador (por fecha) y predecir la segunda.

Modelos comparados (por métrica):
- `crudo`: la tasa observada en la primera mitad, sin encoger, como si fuera la verdadera (sólo ruido binomial o de
  Poisson en la segunda mitad). Es la referencia ingenua.
- `jer`: jerárquico con media por rol, sin sobredispersión dentro de jugador.
- `jer_sd`: jerárquico con la sobredispersión dentro de jugador estimada por momentos en la primera mitad.
- Familia normal: un solo modelo (`jer`), cuya φ ya es la varianza dentro de jugador entre partidos.
- `+deriva` (`jer_sd_d`, y `jer_d` en la normal): el preferido más una deriva del nivel entre mitades,
  η₂ = η₁ + d, d ~ N(0, τ²_d). τ²_d se estima por momentos (`deriva_momentos`) con los casos de **las otras ligas**
  (dejar una liga fuera), así que la liga evaluada no participa en su propia τ²_d.

Se condiciona en las oportunidades de la segunda mitad (cuántos tiros, rebotes disponibles…): la capa de medida
responde «dado el volumen, cuánto acierta»; el volumen y el rol son otra capa (F6–F7).

Evaluación (unidades con ≥ 3 partidos y ≥ 50 minutos en cada mitad): PIT aleatorizado (discretas), cobertura de los
intervalos centrales del 50, 80 y 95 % (|PIT − 0,5| ≤ nivel/2) y CRPS de la tasa de la segunda mitad.
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

from bbnorm5.medida import datos as D
from bbnorm5.medida import eb

S = 400
MIN_UNIDADES = 30
EVAL_MIN_PARTIDOS = 3
EVAL_MIN_MINUTOS = 50.0


def _semilla(base: int, *claves) -> int:
    return (base + zlib.crc32("|".join(map(str, claves)).encode())) % (2 ** 32)


def _hiper(m: dict, u: pd.DataFrame, **extra) -> list[dict]:
    """Hiperparámetros por liga-temporada. Con σ común a la liga (etiquetas «temporada|rol»), una fila por temporada con
    sus medias de rol, su tasa media y su n*, y la σ y la dispersión comunes."""
    nr = len(m["roles"])
    if m["familia"] == "normal":
        mus = dict(zip(m["roles"], m["mu"]))
        sig, disp = m["tau2"] ** 0.5, m["phi"]
    else:
        mus = dict(zip(m["roles"], m["par"][:nr]))
        sig, disp = float(np.exp(m["par"][nr])), m["disp"]
    comun = any("|" in r for r in m["roles"])
    grupos = u.groupby("temporada") if comun else [(extra.get("temporada"), u)]
    filas = []
    for temp, x in grupos:
        t = float(x["K"].sum() / x["N"].sum())
        t = min(max(t, 1e-6), 1 - 1e-6) if m["familia"] == "binomial" else max(t, 1e-6)    # n* sin división por 0
        if m["familia"] == "normal":
            nst, ng = disp / sig ** 2, np.nan
        elif m["familia"] == "binomial":
            ng = float(np.median(x["N2g"] / x["N"]))
            nst = (1 + disp * (ng - 1)) / (sig ** 2 * t * (1 - t))
        else:
            nst, ng = (1 + disp) / (sig ** 2 * t), np.nan
        pref = f"{temp}|" if comun else ""
        filas.append({**extra, "temporada": temp, "tasa_media": t, "sigma": sig, "n_estab": nst, "n_partido_medio": ng,
                      "disp": disp, "logL": m["logL"], "unidades": len(x), "sigma_comun_liga": comun,
                      **{f"mu_{r}": mus.get(pref + r, np.nan) for r in eb.ROLES}})
    return filas


def _ajustes(u: pd.DataFrame, familia: str) -> dict:
    if familia == "normal":
        return {"jer": eb.ajustar_normal(u)}
    return {"jer": eb.ajustar(u, familia, False), "jer_sd": eb.ajustar(u, familia, True)}


def _con_deriva(tasa: np.ndarray, fam: str, tau2: float, rng) -> np.ndarray:
    d = np.sqrt(tau2) * rng.standard_normal(tasa.shape)
    if fam == "binomial":
        from scipy import special
        return special.expit(special.logit(np.clip(tasa, 1e-9, 1 - 1e-9)) + d)
    if fam == "poisson":
        return tasa * np.exp(d)
    return tasa + d


def deriva_momentos(casos: pd.DataFrame, hiper: pd.DataFrame) -> pd.DataFrame:
    """τ²_d por métrica y liga, dejando fuera esa liga.

    En la escala de la tasa, D = r₂ − r₁ (tasas crudas de cada mitad) tiene varianza ≈ τ²_d·g(p)² + v₁ + v₂, con
    g(p) = p(1 − p) (binomial, deriva en logit) o p (Poisson, deriva en log) y v_h la varianza de muestreo de la mitad
    h con la sobredispersión de la liga-temporada. p es la media posterior de la primera mitad (encogida: no explota
    con pocos aciertos, a diferencia del logit empírico, que en simulación y en los datos infla τ²_d en tapones, robos
    y libres). Se estandariza e = D/g y se despeja τ²_d con pesos 1/(v + τ²)² iterados (DerSimonian–Laird), ≥ 0."""
    c = casos[casos["modelo"] == "crudo"].copy()
    pm = casos[casos["modelo"].isin(["jer_sd", "jer"])].sort_values("modelo").drop_duplicates(
        D.CLAVE + ["metrica"], keep="last")[D.CLAVE + ["metrica", "pred_media"]].rename(columns={"pred_media": "p1"})
    c = c.merge(pm, on=D.CLAVE + ["metrica"])
    h = hiper[(hiper["datos"] == "mitad1") & hiper["modelo"].isin(["jer_sd", "jer"])]
    h = h.sort_values("modelo").drop_duplicates(["liga", "temporada", "metrica"], keep="last")
    c = c.merge(h[["liga", "temporada", "metrica", "disp"]], on=["liga", "temporada", "metrica"])
    fam = c["metrica"].map(lambda m: D.METRICAS[m][0]).to_numpy()
    K1, N1, K2, N2, disp, p = (c[x].to_numpy(float) for x in ("K", "N", "K_2", "N_2", "disp", "p1"))
    G1, G2 = c["G1"].to_numpy(float), c["G2"].to_numpy(float)
    Dr = K2 / N2 - K1 / N1
    infl = lambda n, g: 1 + disp * np.maximum(n / np.maximum(g, 1) - 1, 0)
    e = np.full(len(c), np.nan)
    v = np.full(len(c), np.nan)
    b = fam == "binomial"
    g = p * (1 - p)
    e[b] = (Dr / g)[b]
    v[b] = ((infl(N1, G1) / N1 + infl(N2, G2) / N2) / g)[b]
    po = fam == "poisson"
    e[po] = (Dr / p)[po]
    v[po] = ((1 + disp) * (1 / N1 + 1 / N2) / p)[po]
    no = fam == "normal"
    e[no] = Dr[no]
    v[no] = (disp * (1 / N1 + 1 / N2))[no]
    c["e"], c["v"] = e, v
    c = c[np.isfinite(c["e"]) & np.isfinite(c["v"])]

    def tau2(x):
        t = 0.0
        for _ in range(30):
            w = 1 / (x["v"] + t) ** 2
            t_new = max(float((w * (x["e"] ** 2 - x["v"])).sum() / w.sum()), 0.0)
            if abs(t_new - t) < 1e-8:
                break
            t = t_new
        return t
    filas = []
    for met, x in c.groupby("metrica"):
        filas.append({"metrica": met, "liga": "todas", "tau2_d": tau2(x)})
        for liga in x["liga"].unique():
            filas.append({"metrica": met, "liga": liga, "tau2_d": tau2(x[x["liga"] != liga])})
    return pd.DataFrame(filas)


def _etiquetar(u: pd.DataFrame, sigma_comun: bool) -> pd.DataFrame:
    """Con σ común a las temporadas de una liga, cada temporada conserva sus propias medias de rol."""
    return u.assign(rol=u["temporada"] + "|" + u["rol"]) if sigma_comun else u


def liga_temporada(d: pd.DataFrame, liga: str, temporada: str, semilla: int, metricas=None, deriva: dict | None = None,
                   sigma_comun: bool = False):
    """Devuelve (casos de validación por unidad, hiperparámetros, posteriores de la temporada completa).
    deriva: {métrica: τ²_d} estimada sin esta liga; si se da, añade los modelos con deriva entre mitades."""
    casos, hiper, post = [], [], []
    minutos = d.groupby(D.CLAVE + ["mitad"]).agg(min=("min", "sum"), G=("game_id", "nunique")).unstack("mitad")
    minutos.columns = [f"{a}{b}" for a, b in minutos.columns]
    for met in (metricas or D.METRICAS):
        fam = D.METRICAS[met][0]
        rng = np.random.default_rng(_semilla(semilla, liga, temporada, met))
        u1 = _etiquetar(D.unidad_metrica(d, met, 1), sigma_comun)
        if len(u1) < MIN_UNIDADES:
            continue
        # ---- validación: primera mitad → segunda
        u2 = _etiquetar(D.unidad_metrica(d, met, 2), sigma_comun)
        mods = _ajustes(u1, fam)
        for nom, m in mods.items():
            hiper.extend(_hiper(m, u1, liga=liga, temporada=temporada, metrica=met, modelo=nom, datos="mitad1"))
        ev = u1.reset_index().merge(u2[D.CLAVE + ["K", "N", "N2g"]], on=D.CLAVE, suffixes=("", "_2"))
        ev = ev.merge(minutos, left_on=D.CLAVE, right_index=True)
        ev = ev[(ev["G1"] >= EVAL_MIN_PARTIDOS) & (ev["G2"] >= EVAL_MIN_PARTIDOS) & (ev["min1"] >= EVAL_MIN_MINUTOS)
                & (ev["min2"] >= EVAL_MIN_MINUTOS) & (ev["N_2"] > 0)]
        if len(ev) == 0:
            continue
        fila = ev["index"].to_numpy()
        N2 = ev["N_2"].to_numpy(float)
        N2r = np.maximum(np.round(N2), ev["K_2"].to_numpy()) if fam == "binomial" else N2
        y = ev["K_2"].to_numpy(float) / N2r
        base = ev[D.CLAVE + ["rol", "K", "N", "G1", "G2", "min1", "min2", "K_2", "N_2"]].reset_index(drop=True)
        cand = dict(mods)
        cand["crudo"] = None
        if deriva and met in deriva:
            pref = "jer" if fam == "normal" else "jer_sd"
            cand[pref + "_d"] = mods[pref]
        for nom, m in cand.items():
            if nom == "crudo":
                t1 = (ev["K"] / ev["N"]).to_numpy(float)
                tasa = np.repeat(t1[:, None], S, axis=1)
                disp = 0.0
                phi = mods["jer"]["phi"] if fam == "normal" else 0.0
            else:
                if fam == "normal":
                    sub = {**m, "m_post": m["m_post"][fila], "v_post": m["v_post"][fila]}
                    tasa = eb.muestras_tasa(sub, S, rng)
                    phi = m["phi"]
                    disp = 0.0
                else:
                    tasa = eb.muestras_tasa({**m, "W": m["W"][fila]}, S, rng)
                    disp, phi = m["disp"], 0.0
                if nom.endswith("_d"):
                    tasa = _con_deriva(tasa, fam, deriva[met], rng)
            K2 = eb.muestras_conteo(tasa, N2r if fam == "binomial" else N2, ev["N2g_2"].to_numpy(float), fam, disp,
                                    rng, phi)
            r = eb.evaluar(K2 / N2r[:, None], y, fam != "normal", rng)
            casos.append(base.assign(metrica=met, modelo=nom, pred_media=(K2 / N2r[:, None]).mean(axis=1), obs=y,
                                     pit=r["pit"].to_numpy(), crps=r["crps"].to_numpy()))
        # ---- temporada completa: hiperparámetros y posterior de cada unidad
        u = _etiquetar(D.unidad_metrica(d, met, None), sigma_comun)
        for nom, m in _ajustes(u, fam).items():
            hiper.extend(_hiper(m, u, liga=liga, temporada=temporada, metrica=met, modelo=nom, datos="temporada"))
            if fam == "normal":
                ps = pd.DataFrame({"media": m["m_post"], "sd": np.sqrt(m["v_post"])})
                ps["q10"], ps["q50"], ps["q90"] = (ps["media"] + z * ps["sd"] for z in (-1.2815515655, 0, 1.2815515655))
            else:
                ps = eb.resumen_posterior(m)
            post.append(pd.concat([u[D.CLAVE + ["rol", "K", "N", "G"]].reset_index(drop=True), ps], axis=1)
                        .assign(metrica=met, modelo=nom, obs=u["K"].to_numpy() / u["N"].to_numpy()))
    cat = lambda x: pd.concat(x, ignore_index=True) if x else pd.DataFrame()
    return cat(casos), pd.DataFrame(hiper), cat(post)


def resumen(casos: pd.DataFrame, por: list[str]) -> pd.DataFrame:
    c = casos.copy()
    for a in (50, 80, 95):
        c[f"cob{a}"] = (np.abs(c["pit"] - 0.5) <= a / 200).astype(float)
    g = c.groupby(por)
    r = g.agg(casos=("pit", "size"), cob50=("cob50", "mean"), cob80=("cob80", "mean"), cob95=("cob95", "mean"),
              crps=("crps", "mean"), pit_media=("pit", "mean")).reset_index()
    return r
