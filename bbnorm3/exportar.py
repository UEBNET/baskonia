"""Ajuste final (todas las temporadas) → data/modelos/v3/ (rutas nuevas; la v1/v2 no se toca).

Ver bbnorm3/salidas.py para el esquema de cada fichero. Etiquetas de los resultados: los niveles y traducciones son
estimaciones del modelo (LECTURA); el examen fuera de muestra está en data/modelos/v3/validacion/ (DATO).
"""
from __future__ import annotations

import itertools
import json

import numpy as np
import pandas as pd
import torch
from scipy.stats import norm

from bbmodel.metricas import CATALOGO, destransformar

from . import config as C
from . import datos, salidas, traduccion
from .datos import METRICAS, METRICAS_NIVEL, POSICIONES, matrices_filas

Z80 = norm.ppf(0.9)
IDENTIDAD = ["nombre", "equipo", "pos3", "anio_nac", "gp", "min"]


# ---------------------------------------------------------------------------------------------- niveles
def _var_contraste(J, cov, coef, R):
    """Var(Σ_c coef_c δ_c) por métrica, con δ_c lineal en (μ_c − μ_R) y la covarianza conjunta de μ (K × nC × nC)."""
    A = coef[:, None, None] * J                       # (nC, M, K)
    sa = A.sum(0)                                     # (M, K)
    out = np.zeros(J.shape[1])
    for k in range(cov.shape[0]):
        S = cov[k]
        a = A[:, :, k]                                # (nC, M)
        out += np.einsum("cm,cd,dm->m", a, S, a) - 2 * sa[:, k] * (a.T @ S[:, R]) + sa[:, k] ** 2 * S[R, R]
    return np.maximum(out, 0)


def tabla_niveles(D, cj, cfg) -> tuple[pd.DataFrame, pd.DataFrame]:
    ref = f"{cfg['referencia_salida']['liga']}|{cfg['referencia_salida']['temporada']}"
    R = D.comps.index(ref)
    w = np.bincount(D.idx["comp"], minlength=len(D.comps)).astype(float)
    w /= w.sum()
    deltas, vars_g, vars_a, Js, covs = [], [], [], [], []
    acb = {c: D.comps.index(f"acb|{c.split('|')[1]}") if f"acb|{c.split('|')[1]}" in D.comps else None
           for c in D.comps}
    for m, P in cj:
        d, J = traduccion.niveles(m, P, D, R)
        cov = P.cov_mu()
        vg, va = [], []
        for c in range(len(D.comps)):
            coef = -w.copy(); coef[c] += 1.0                  # δ_c − Σ w δ  (gauge en la media)
            vg.append(_var_contraste(J, cov, coef, R))
            if acb[D.comps[c]] is not None and acb[D.comps[c]] != c:
                coef = np.zeros(len(D.comps)); coef[c] = 1.0; coef[acb[D.comps[c]]] = -1.0
                va.append(_var_contraste(J, cov, coef, R))
            else:
                va.append(np.zeros(len(METRICAS)))
        deltas.append(d); vars_g.append(np.array(vg)); vars_a.append(np.array(va)); Js.append(J); covs.append(cov)
    dg = [d - (w[:, None] * d).sum(0) for d in deltas]
    da = [d - np.array([d[acb[c]] if acb[c] is not None else np.full(d.shape[1], np.nan) for c in D.comps])
          for d in deltas]
    media_g, media_a = np.mean(dg, 0), np.mean(da, 0)
    var_g = np.mean(vars_g, 0) + np.var(dg, 0)               # dentro de cada red + entre redes (deep ensemble)
    var_a = np.mean(vars_a, 0) + np.var(da, 0)
    n_puentes = _puentes_por_comp(D, cfg)
    filas = []
    for c, comp in enumerate(D.comps):
        liga, temp = comp.split("|")
        for k, met in enumerate(METRICAS):
            sg, sa = np.sqrt(var_g[c, k]), np.sqrt(var_a[c, k])
            filas.append({"competicion": liga, "temporada": temp, "metrica": met, "escalon": D.escalon_de_liga.get(liga),
                          "nivel_gauge_media": media_g[c, k], "sd_gauge_media": sg,
                          "lo80_gauge_media": media_g[c, k] - Z80 * sg, "hi80_gauge_media": media_g[c, k] + Z80 * sg,
                          "nivel_acb0": media_a[c, k], "sd_acb0": sa,
                          "lo80_acb0": media_a[c, k] - Z80 * sa, "hi80_acb0": media_a[c, k] + Z80 * sa,
                          "n_puentes": n_puentes.get(comp, 0), "peso_gauge": w[c]})
    niv = pd.DataFrame(filas)
    # covarianza conjunta (gauge en la media) del índice de nivel (media con signo de las 8 métricas de nivel)
    kk = [METRICAS.index(m) for m in METRICAS_NIVEL]
    sg = np.array([METRICAS_NIVEL[m] for m in METRICAS_NIVEL], float) / len(kk)
    cov_rows = []
    nC = len(D.comps)
    Pg = np.eye(nC) - np.outer(np.ones(nC), w)
    for J, cov in zip(Js, covs):
        Jl = np.einsum("cmk,m->ck", J[:, kk, :], sg)          # jacobiano del índice de nivel (nC × K)
        Sig = np.zeros((nC, nC))
        for k in range(cov.shape[0]):
            S = cov[k]
            St = S - S[:, [R]] - S[[R], :] + S[R, R]          # covarianza de (μ_c − μ_R)
            Sig += (Jl[:, k][:, None] * St) * Jl[:, k][None, :]
        cov_rows.append(Pg @ Sig @ Pg.T)
    idx_nivel = np.array([np.einsum("cm,m->c", d[:, kk], sg) for d in dg])
    Sig = np.mean(cov_rows, 0) + np.cov(idx_nivel.T, bias=True)
    ii, jj = np.triu_indices(nC)
    covdf = pd.DataFrame({"competicion_a": [D.comps[i] for i in ii], "competicion_b": [D.comps[j] for j in jj],
                          "cov_indice_nivel": Sig[ii, jj]})
    return niv, covdf, (deltas, Js, covs, R)


def _puentes_por_comp(D, cfg) -> dict:
    mm = cfg["datos"]["min_minutos_puente"]
    t = D.t[D.t["min"] >= mm]
    por = t.groupby(["persona_id", "anio"])["comp"].agg(set)
    cuenta = {}
    for (p, a), cs in por.items():
        otras = set(cs) | por.get((p, a - 1), set()) | por.get((p, a + 1), set())
        for c in cs:
            if len(otras - {c}):
                cuenta[c] = cuenta.get(c, 0) + 1
    return cuenta


def grafo_puentes(D, cfg) -> pd.DataFrame:
    """Personas con ≥ 150 min en las dos ligas (misma temporada o consecutivas), por pareja de ligas."""
    mm = cfg["datos"]["min_minutos_puente"]
    t = D.t[D.t["min"] >= mm][["persona_id", "anio", "liga"]].drop_duplicates()
    pares = {}
    for p, g in t.groupby("persona_id"):
        vistos = set()
        for (a1, l1), (a2, l2) in itertools.combinations(zip(g["anio"], g["liga"]), 2):
            if l1 != l2 and abs(a1 - a2) <= 1:
                vistos.add(tuple(sorted((l1, l2))))
        for k in vistos:
            pares[k] = pares.get(k, 0) + 1
    return pd.DataFrame([{"liga_a": a, "liga_b": b, "personas": n} for (a, b), n in sorted(pares.items())]) \
        .sort_values("personas", ascending=False)


# ---------------------------------------------------------------------------------------------- traducción de jugadores
@torch.no_grad()
def traducir_filas(tabla: pd.DataFrame, D, cj, cfg) -> pd.DataFrame:
    """Equivalente en la competición de referencia (EuroLeague 2025-26) de cada fila jugador-liga-temporada.
    Filas del entrenamiento: posterior conjunta (niveles.py). Resto (< min_minutos): codificador + prior por nivel.
    Intervalo del 80 % de la CAPACIDAD traducida (sin ruido de muestra en destino), igual que <m>_am_lo/_hi."""
    ref = f"{cfg['referencia_salida']['liga']}|{cfg['referencia_salida']['temporada']}"
    R = D.comps.index(ref)
    lR = int(D.comp_liga[R])
    t = tabla[tabla["pos3"].notna()].copy()
    t["comp"] = t["liga"] + "|" + t["temporada"]
    # competición-temporada sin filas de entrenamiento (p. ej. una liga en curso sin nadie con 100 min): nivel y
    # entorno de la última temporada de esa liga en el ajuste, más el paso aleatorio κ² de una temporada
    ultima = {}
    for c in D.comps:
        l, tt = c.split("|")
        if l not in ultima or tt > ultima[l].split("|")[1]:
            ultima[l] = c
    t["comp_ajuste"] = np.where(t["comp"].isin(D.comps), t["comp"], t["liga"].map(ultima))
    t = t[t["comp_ajuste"].notna()]
    extra_kappa = np.where(t["comp"] == t["comp_ajuste"], 0.0, cfg["prior"]["kappa"] ** 2)
    t["ps"] = t["persona_id"].astype(str) + "|" + t["anio"].astype(str)
    ps_idx = {p: i for i, p in enumerate(D.ps)}
    en_ent = t["ps"].map(ps_idx)
    grupos_R = np.array([D.grupos.index(f"{ref}|{p}") for p in t["pos3"]])
    S = int(cfg["prediccion"]["muestras"])
    rng = np.random.default_rng(int(cfg["semillas"][0]))
    Yn, Mn, Vn = matrices_filas(t, D.esc)
    liga_n = np.array([D.ligas.index(l) for l in t["liga"]])
    comp_n = np.array([D.comps.index(c) for c in t["comp_ajuste"]])
    pos_n = t["pos3"].map({p: i for i, p in enumerate(POSICIONES)}).to_numpy()
    logmin = np.log(np.clip(t["min"].to_numpy(float), 1, None)) / 7.0
    # 1) por red: media y varianza de (u − μ_R) y factor específico de cada fila (poca memoria: filas × K)
    ok = en_ent.notna().to_numpy()
    ips = en_ent[ok].astype(int).to_numpy()
    per_idx = {p: i for i, p in enumerate(D.personas)}
    pi = t["persona_id"].map(per_idx)
    okp = pi.notna().to_numpy()
    margen = cfg["prediccion"].get("margen_soporte")
    if margen is not None:
        from .prediccion import soporte
        lo_s, hi_s = soporte(D, float(margen))
    partes = []
    from .flujo import DIR_CACHE, _huella
    for i_red, (m, P) in enumerate(cj):
        K = m.K
        f_cache = DIR_CACHE / f"traducir_{_huella(cfg)}_{len(t)}_red{i_red}.npz"
        if f_cache.exists():                           # reanudación: lo ya calculado para esta red
            x = np.load(f_cache)
            partes.append((m, P, x["media"], x["var"], x["z"], x["vz"]))
            continue
        media = np.zeros((len(t), K)); var = np.zeros((len(t), K))
        media[ok] = P.media[ips] - P.media[P.nPS + R]
        # varianza de (u − μ_R) por dimensión: diag de la inversa en el contraste (una resolución por fila única)
        unicos, inv = np.unique(ips, return_inverse=True)
        vu = P.var_contrastes(unicos, np.full(len(unicos), P.nPS + R))
        var[ok] = vu[inv]
        # filas fuera del entrenamiento: experto del codificador ⊗ prior N(μ_c, s²)
        if (~ok).any():
            mm_, lp = m.codificar(torch.as_tensor(Yn[~ok]), torch.as_tensor(Mn[~ok]), torch.as_tensor(Vn[~ok]),
                                  torch.as_tensor(liga_n[~ok]), torch.as_tensor(pos_n[~ok]),
                                  torch.as_tensor(logmin[~ok], dtype=torch.float32))
            prec = np.exp(lp.numpy()) + 1.0                     # experto + prior N(0, 1) en coordenadas relativas
            rmed = mm_.numpy() * np.exp(lp.numpy()) / prec
            sl = P.s[liga_n[~ok]][:, None]
            media[~ok] = P.media[P.nPS + comp_n[~ok]] + sl * rmed - P.media[P.nPS + R]
            cu, ci = np.unique(comp_n[~ok], return_inverse=True)
            vc = P.var_contrastes(P.nPS + cu, np.full(len(cu), P.nPS + R))
            var[~ok] = sl ** 2 / prec + vc[ci] + extra_kappa[~ok][:, None]
        z = np.zeros((len(t), len(METRICAS))); vz = np.zeros_like(z)
        if m.usar_unicidad:
            vz[:] = m.s2Z.numpy()[None, :]
            prec_z = m.precision_unicidad().numpy()
            z[okp] = m.Z.numpy()[pi[okp].astype(int)]
            vz[okp] = 1.0 / (prec_z[pi[okp].astype(int)] + 1.0 / m.s2Z.numpy()[None, :])
        np.savez(f_cache, media=media, var=var, z=z, vz=vz)
        partes.append((m, P, media, var, z, vz))
    # 2) Monte Carlo por bloques de filas (las muestras de todas las filas a la vez no caben en memoria)
    n = len(t)
    centro = np.zeros((n, len(METRICAS))); entre = np.zeros_like(centro)
    lo = np.zeros_like(centro); hi = np.zeros_like(centro)
    bloque = 1000
    for a in range(0, n, bloque):
        sl_ = slice(a, min(a + bloque, n))
        nb = sl_.stop - sl_.start
        cent_b, mues_b = [], []
        for m, P, media, var, z, vz in partes:
            K = m.K
            eps = rng.standard_normal((nb, S, K))
            r = (media[sl_, None, :] + np.sqrt(np.maximum(var[sl_], 0))[:, None, :] * eps) / P.s[lR]
            yh = m.decodificar(torch.as_tensor(r.reshape(-1, K), dtype=torch.float32),
                               torch.full((nb * S,), lR), torch.as_tensor(np.repeat(grupos_R[sl_], S))).numpy()
            yh = yh.reshape(nb, S, -1).astype(float)
            yh = yh + z[sl_, None, :] + np.sqrt(vz[sl_])[:, None, :] * rng.standard_normal(yh.shape)
            if margen is not None:
                yh = np.clip(yh, lo_s[lR][None, None, :], hi_s[lR][None, None, :])
            cent_b.append(yh.mean(1)); mues_b.append(yh)
        centro[sl_] = np.mean(cent_b, 0)
        entre[sl_] = np.std(cent_b, 0)                  # discrepancia entre las redes (salvaguarda de la v3.1)
        lo[sl_], hi[sl_] = np.quantile(np.concatenate(mues_b, 1), [0.1, 0.9], axis=1)
    # percentil entre los jugadores de la referencia de su posición (sus propios equivalentes)
    out = {"persona_id": t["persona_id"].to_numpy(), "player_id": t["player_id"].to_numpy(),
           "team_id": t["team_id"].to_numpy(), "liga": t["liga"].to_numpy(), "temporada": t["temporada"].to_numpy(),
           "fuente_v3": np.where(en_ent.notna(), "posterior_conjunta",
                                 np.where(extra_kappa > 0, "codificador_nivel_temporada_anterior", "codificador"))}
    for c in IDENTIDAD:
        if c in t:
            out[c] = t[c].to_numpy()
    for col in METRICAS:
        out[f"{col}_obs__tabla"] = pd.to_numeric(t[col], errors="coerce").to_numpy()
    es_ref = (t["comp"] == ref).to_numpy()
    for k, col in enumerate(METRICAS):
        tr = CATALOGO[col].transf
        c, s = D.esc.c[col], D.esc.s[col]
        out[f"{col}_v3"] = destransformar(c + s * centro[:, k], tr)
        out[f"{col}_v3_lo"] = destransformar(c + s * lo[:, k], tr)
        out[f"{col}_v3_hi"] = destransformar(c + s * hi[:, k], tr)
        out[f"{col}_v3_sd"] = (out[f"{col}_v3_hi"] - out[f"{col}_v3_lo"]) / (2 * Z80)
        out[f"{col}_v3_sd_entre_z"] = entre[:, k]
        pct = np.full(len(t), np.nan)
        for p in POSICIONES:
            refv = np.sort(centro[es_ref & (t["pos3"] == p).to_numpy(), k])
            sel = (t["pos3"] == p).to_numpy()
            if len(refv):
                pct[sel] = 100 * np.searchsorted(refv, centro[sel, k], side="right") / len(refv)
        out[f"{col}_v3_pctel"] = pct
    return pd.DataFrame(out, index=t.index)


def _e(n, i, j):
    a = np.zeros(n); a[i] = 1.0; a[j] -= 1.0
    return a


# ---------------------------------------------------------------------------------------------- todo
def todo(tabla: pd.DataFrame, D, cj, cfg, normalizado: bool = True) -> pd.DataFrame:
    out = C.dir_salida(cfg)
    out.mkdir(parents=True, exist_ok=True)
    niv, covdf, (deltas, Js, covs, R) = tabla_niveles(D, cj, cfg)
    niv.round(5).to_csv(out / "niveles.csv", index=False)
    covdf.round(6).to_csv(out / "niveles_covarianza.csv.gz", index=False)
    grafo_puentes(D, cfg).to_csv(out / "puentes.csv", index=False)
    # traducción cruzada T_m(a → b): competiciones de la temporada de referencia
    temp = cfg["referencia_salida"]["temporada"]
    comps = [c for c, x in enumerate(D.comps) if x.endswith("|" + temp)]
    pares = [(a, b) for a in comps for b in comps if a != b]
    (out / "traduccion_cruzada").mkdir(exist_ok=True)
    res_por_red = [traduccion.traduccion_cruzada(d, J, cov, R, pares) for d, J, cov in zip(deltas, Js, covs)]
    for k, met in enumerate(METRICAS):
        filas = []
        for i, (a, b) in enumerate(pares):
            med = np.array([rr[i]["media"][k] for rr in res_por_red])
            sd_in = np.array([rr[i]["sd"][k] for rr in res_por_red])
            sd_m = np.array([rr[i]["sd_marginal_sumada"][k] for rr in res_por_red])
            sd = float(np.sqrt(np.mean(sd_in ** 2) + med.var()))
            filas.append({"origen": D.comps[a], "destino": D.comps[b], "media": med.mean(), "sd": sd,
                          "lo80": med.mean() - Z80 * sd, "hi80": med.mean() + Z80 * sd,
                          "sd_varianzas_marginales_sumadas": float(np.sqrt(np.mean(sd_m ** 2) + med.var()))})
        pd.DataFrame(filas).round(5).to_csv(out / "traduccion_cruzada" / f"{met}.csv", index=False)
    # residuos de ciclo por triángulo de ligas (temporada de referencia)
    filas = []
    for a, b, c in itertools.combinations(comps, 3):
        res = np.mean([traduccion.residuo_ciclo(m, P, D, (a, b, c), n=200) for m, P in cj], 0)
        filas.append({"a": D.comps[a], "b": D.comps[b], "c": D.comps[c],
                      "residuo_medio_abs_dt": float(np.abs(res).mean()),
                      **{f"res_{met}": float(res[k]) for k, met in enumerate(METRICAS)}})
    pd.DataFrame(filas).round(5).to_csv(out / "ciclo.csv", index=False)
    # dataset normalizado v3
    trad = traducir_filas(tabla, D, cj, cfg)
    if normalizado:
        _normalizado(trad, out / "normalizado")
    escribir_resumen(D, cj, cfg)
    print(f"Salidas v3 en {out}", flush=True)
    return trad


def _norm_nombre(x: pd.Series) -> pd.Series:
    import unicodedata
    return x.astype(str).map(lambda v: " ".join(unicodedata.normalize("NFKD", v).encode("ascii", "ignore")
                                              .decode().lower().replace(".", " ").split()))


def escribir_resumen(D, cj, cfg) -> None:
    out = C.dir_salida(cfg)
    resumen = {"version": cfg["version"], "semillas": cfg["semillas"], "K": cfg["latente"]["K"],
               "filas_entrenamiento": int(len(D.t)), "personas_temporada": len(D.ps), "competiciones": len(D.comps),
               "ipw": D.info_ipw, "referencia_salida": cfg["referencia_salida"],
               "escala_liga": {l: float(np.mean([P.s[i] for _, P in cj])) for i, l in enumerate(D.ligas)},
               "unicidad_omega2": {met: float(np.mean([m.s2Z.numpy()[k] for m, _ in cj])) for k, met in enumerate(METRICAS)}}
    (out / "resumen.json").write_text(json.dumps(resumen, indent=1, ensure_ascii=False, default=float), encoding="utf-8")


def _normalizado(trad: pd.DataFrame, dir_out, columnas_nuevas=None, sufijo: str = "_v3", fuente: str = "V3") -> None:
    """Esquema del dataset normalizado v1 (data/modelos/normalizado/<t>.csv) + columnas v3 (salidas.combinar_normalizado).
    Las filas son las de la tabla actual; las columnas del v1 se unen por (player_id, team_id, liga, temporada) y
    quedan vacías en las filas que el v1 no tiene (p. ej. partidos de 2026-27 posteriores a su cálculo)."""
    dir_v1 = C.RAIZ / "data" / "modelos" / "normalizado"
    dir_out.mkdir(parents=True, exist_ok=True)
    clave = ["player_id", "team_id", "liga", "temporada"]
    for temp, g in trad.groupby("temporada"):
        f1 = dir_v1 / f"{temp}.csv"
        if not f1.exists():
            continue
        v1 = pd.read_csv(f1, low_memory=False)
        g = g.copy()
        for c in ("player_id", "team_id"):
            g[c] = g[c].astype(str); v1[c] = v1[c].astype(str)
        # 1) cruce por (player_id, team_id, liga, temporada); 2) si falla (p. ej. ids de la BBL que han cambiado de
        # formato), por (nombre normalizado, team_id, liga, temporada), sólo con emparejamientos únicos
        v1 = v1.reset_index(drop=True)
        fila = g[clave].reset_index(drop=True).merge(v1[clave].assign(_f=np.arange(len(v1))).drop_duplicates(clave, keep=False),
                                                     on=clave, how="left")["_f"]
        if "nombre" in v1 and "nombre" in g:
            k2 = ["_nom", "team_id", "liga", "temporada"]
            a = g.assign(_nom=_norm_nombre(g["nombre"]))[k2].reset_index(drop=True)
            b = v1.assign(_nom=_norm_nombre(v1["nombre"]), _f=np.arange(len(v1)))[k2 + ["_f"]].drop_duplicates(k2, keep=False)
            b = b[~b["_f"].isin(fila.dropna())]
            fila = fila.fillna(a.merge(b, on=k2, how="left")["_f"])
        fila = fila.fillna(-1).astype(int).to_numpy()
        base = v1.reindex(fila).reset_index(drop=True)   # filas sin pareja en el v1: vacías
        base = base[v1.columns].copy()               # mismo orden de columnas que el v1
        for c in clave:
            base[c] = g[c].to_numpy()
        # fila del v1 calculada con otros partidos (temporada en curso): no se mezcla un valor viejo con uno nuevo
        gp1, gp3 = pd.to_numeric(base.get("gp"), errors="coerce"), pd.to_numeric(g["gp"], errors="coerce").to_numpy() \
            if "gp" in g else None
        desact = (np.isfinite(gp1) & np.isfinite(gp3) & (gp1.to_numpy() != gp3)) if gp3 is not None else np.zeros(len(base), bool)
        # filas del v1 que la tabla actual no traduce (p. ej. sin posición estimada): se conservan con su valor v1
        resto = v1.loc[~v1.index.isin(fila[fila >= 0])]
        if len(resto):
            g_resto = pd.DataFrame({c: resto[c].to_numpy() for c in ["persona_id"] + IDENTIDAD + clave if c in resto})
            g_resto["fuente_v3"] = "solo_v1"
            base = pd.concat([base, resto[v1.columns]], ignore_index=True)
            desact = np.r_[desact, np.zeros(len(resto), bool)]
            g = pd.concat([g.reset_index(drop=True), g_resto], ignore_index=True)
        # identidad y valor observado de la tabla actual (también en las filas que el v1 no tiene)
        g = g.reset_index(drop=True)
        for c in ["persona_id"] + IDENTIDAD:
            if c in base and c in g:
                base[c] = g[c].to_numpy()
        for col in METRICAS:
            if f"{col}_obs" in base:
                base[f"{col}_obs"] = base[f"{col}_obs"].fillna(pd.Series(g[f"{col}_obs__tabla"].to_numpy()))
        v3cols = g[[c for c in g.columns if "_v3" in c and not c.endswith("__tabla")]]
        if columnas_nuevas is not None:                 # v3.1: combinación con las columnas v1 de la misma fila
            v3cols = columnas_nuevas(base.assign(_v1_desactualizado=desact), v3cols)
        comb = salidas.combinar_normalizado(base, v3cols, METRICAS, sufijo=sufijo, fuente=fuente)
        comb["fuente_v3"] = g["fuente_v3"].to_numpy()
        comb.round(4).to_csv(dir_out / f"{temp}.csv.gz", index=False)
