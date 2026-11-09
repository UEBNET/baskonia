"""Normalización de la temporada en curso con los parámetros CONGELADOS (sin reajustar nada).

Cadena publicada (v3.2, docs/normalizacion_v32.md): v2 = algoritmo A (+ B) con el salto de nivel amortiguado, mezclada
con la CVAE jerárquica con un peso por métrica. Aquí, sólo para `temporada`:

1. **A congelado** — σ², τ² y el enlace (m, s, ψ…) de `algoritmo_A/parametros.json`; el entorno μ de cada grupo
   liga|temporada|posición se recentra con los partidos nuevos (una media ponderada con los σ², τ² guardados: la
   misma fórmula que el paso 1 del A, sin reestimar varianzas). `recentrar=False` usa también el μ guardado.
2. **Amortiguada congelada** — desfase δ (media, DT) y λ de cada competición-temporada de `league_offsets.csv`
   (variante `sin_mapeo`, mapeo identidad); una competición-temporada sin nodo usa la media de sus nodos (como
   `amortiguacion.theta`).
3. **B** — la red B no se puede aplicar a filas nuevas (embeddings por persona): se conservan sus filas de la
   temporada cuyo jugador no ha jugado desde entonces (mismos minutos); el resto queda «sólo A», como ya documenta el
   dataset para la temporada en curso.
4. **Identidades estables** — `persona_id` de la tabla nueva se traduce al de los ficheros congelados (por
   liga + id del jugador en cualquier temporada); las personas nuevas reciben ids nuevos por encima del máximo.
5. Dataset normalizado v2 (`bbmodel.dataset_normalizado.construir`) y **v3.2 incremental**: la CVAE de cada fila se
   toma del dataset v3.2 congelado (última recalibración) y se vuelve a mezclar con la v2 al día con exactamente las
   reglas de `bbnorm3.combinacion.ajustar_combinada` (pesos por métrica del examen, salvaguardas). Jugadores sin valor
   CVAE (nuevos en la temporada): sólo v2, la regla de la propia combinación.

Escribe (sólo la temporada en curso): algoritmo_A/traducciones/<t>.csv, algoritmo_B/traducciones/<t>.csv,
normalizacion_amortiguada/traducciones/<t>.csv, normalizado/<t>.csv y v3_2/normalizado/<t>.csv.gz.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from . import TEMPORADA

RAIZ = Path(__file__).resolve().parent.parent
MOD = RAIZ / "data" / "modelos"
DIR_A = MOD / "algoritmo_A"
DIR_B = MOD / "algoritmo_B"
DIR_AM = MOD / "normalizacion_amortiguada"
DIR_V1 = MOD / "normalizado"
DIR_V32 = MOD / "v3_2" / "normalizado"
CFG_V32 = RAIZ / "configs" / "normalization_v32.yaml"


# ============================================================================================ tabla
def tabla() -> pd.DataFrame:
    """Tabla jugador-liga-temporada de TODAS las temporadas (el recorte de valores extremos del A usa todas)."""
    from bbmodel import modelo
    t, _ = modelo.preparar()
    return t


def _params_A() -> dict:
    return json.loads((DIR_A / "parametros.json").read_text(encoding="utf-8"))


# ============================================================================================ A congelado
def z_congelado(t: pd.DataFrame, params: dict, temporada: str = TEMPORADA, recentrar: bool = True) -> dict:
    """z_obs y v_obs por métrica para las filas de `temporada` con σ², τ² (y μ si recentrar=False) guardados."""
    from bbmodel import suerte
    from bbmodel.metricas import CATALOGO
    zs = {}
    sel = (t["temporada"] == temporada).to_numpy()
    for col, p in params["metricas"].items():
        p1 = p["suerte"]
        y, n = suerte.valor_y_exposicion(t, col)
        ok = sel & np.isfinite(y) & np.isfinite(n) & (n > 0) & t["pos3"].notna().to_numpy()
        d = t.loc[ok, ["liga", "temporada", "pos3"]].copy()
        d["y"], d["n"] = y[ok], n[ok]
        por_tiro = CATALOGO[col].exposicion in ("tsa", "fga", "fg3a", "fg2a", "fta", "plays")
        sig = p1["sigma2"]
        med_sig = float(np.median(list(sig.values())))
        s2 = (np.full(len(d), sig.get("todas", med_sig)) if por_tiro
              else d["liga"].map(lambda l: sig.get(l, med_sig)).to_numpy(float))
        t2 = (d["liga"] + "|" + d["pos3"]).map(p1["tau2"]).to_numpy(float)
        g = (d["liga"] + "|" + d["temporada"] + "|" + d["pos3"]).to_numpy()
        if recentrar:
            w = 1.0 / (t2 + s2 / d["n"].to_numpy())
            mu = suerte._media_ponderada(d["y"].to_numpy(), np.where(np.isfinite(w), w, 0.0), g)
            guardado = pd.Series(g).map(p1["mu"]).to_numpy(float)
            mu = np.where(np.isfinite(mu), mu, guardado)
        else:
            mu = pd.Series(g).map(p1["mu"]).to_numpy(float)
        z = pd.DataFrame(index=t.index, columns=["z_obs", "v_obs"], dtype=float)
        z.loc[ok, "z_obs"] = (d["y"].to_numpy() - mu) / np.sqrt(t2)
        z.loc[ok, "v_obs"] = s2 / (d["n"].to_numpy() * t2)
        zs[col] = z
    return zs


def a_congelado(t: pd.DataFrame, temporada: str = TEMPORADA, recentrar: bool = True) -> tuple[pd.DataFrame, dict]:
    """Traducciones del algoritmo A para `temporada` (mismo formato que algoritmo_A/traducciones/<t>.csv)."""
    from bbmodel import modelo
    params = _params_A()
    zs = z_congelado(t, params, temporada, recentrar)
    t27 = t[t["temporada"] == temporada]
    trad = modelo.traducir(t27, {"metricas": params["metricas"], "_z": {c: z.loc[t27.index] for c, z in zs.items()}})
    return trad, zs


# ============================================================================================ amortiguada congelada
def am_congelado(t: pd.DataFrame, zs: dict, temporada: str = TEMPORADA) -> pd.DataFrame:
    """Columnas <m>_am* de `temporada` con los desfases δ y λ guardados (= amortiguacion.traducir con mapeo identidad)."""
    from bbmodel.metricas import CATALOGO, destransformar
    from bbmodel.modelo import Z80, _entorno
    params = _params_A()["metricas"]
    off = pd.read_csv(DIR_AM / "league_offsets.csv")
    resumen = json.loads((DIR_AM / "resumen.json").read_text(encoding="utf-8"))
    if any(resumen.get("mapeos_no_lineales", {}).get(c) for c in resumen.get("mapeos_no_lineales", {})):
        raise RuntimeError("la normalización amortiguada guardada tiene mapeos no lineales: este atajo no los aplica")
    ref = off.loc[off["sd"].eq(0) & off["media"].eq(0), "competicion"].mode().iat[0]       # vara (EuroLeague)
    t27 = t[t["temporada"] == temporada]
    out = t27[["persona_id", "liga", "temporada", "player_id"]].copy().reset_index(drop=True)
    nuevas = {}
    for col in sorted(off["metrica"].unique(), key=list(params).index):
        if col not in params or col not in zs:
            continue
        e, p1 = params[col]["enlace"], params[col]["suerte"]
        o = off[off["metrica"] == col]
        z = zs[col].loc[t27.index]
        z_obs, v_obs = z["z_obs"].to_numpy(float), z["v_obs"].to_numpy(float)
        th, va = np.full(len(t27), np.nan), np.full(len(t27), np.nan)
        ligas = t27["liga"].to_numpy()
        for liga in np.unique(ligas):
            if liga not in e["m"]:
                continue
            s = (ligas == liga) & np.isfinite(z_obs)
            if not s.any():
                continue
            nodo = o[(o["competicion"] == liga) & (o["temporada"] == temporada)]
            if len(nodo):
                dl, dv, lam = float(nodo["media"].iat[0]), float(nodo["sd"].iat[0]) ** 2, float(nodo["lambda"].iat[0])
            else:       # competición-temporada sin nodo (p. ej. liga que empezó tarde): nivel medio de sus nodos
                k = o[o["competicion"] == liga]
                if not len(k):
                    continue
                dl = float(k["media"].mean())
                dv = float((k["sd"] ** 2).mean()) + float(k["tau_escalon"].iat[0]) ** 2
                lam = float(k["lambda"].iat[0])
            if liga == ref:
                lam = 1.0
            psi, sA, s_se = e["psi"][liga], e["s"][liga], e.get("s_se", {}).get(liga, 0.0)
            z_est = z_obs[s] / (1 + v_obs[s] + psi)
            v_est = (v_obs[s] + psi) / (1 + v_obs[s] + psi)
            th[s] = dl + lam * sA * z_est
            va[s] = dv + (lam * sA) ** 2 * v_est + (lam * z_est) ** 2 * s_se ** 2
        pos = t27["pos3"].to_numpy()
        mu = np.array([_entorno(p1, ref, "2025-26", g)[0] if isinstance(g, str) else np.nan for g in pos])
        tau = np.array([_entorno(p1, ref, "2025-26", g)[1] if isinstance(g, str) else np.nan for g in pos])
        sd = np.sqrt(va)
        tr = CATALOGO[col].transf
        nuevas[f"{col}_am"] = destransformar(mu + tau * th, tr)
        nuevas[f"{col}_am_lo"] = destransformar(mu + tau * (th - Z80 * sd), tr)
        nuevas[f"{col}_am_hi"] = destransformar(mu + tau * (th + Z80 * sd), tr)
        nuevas[f"{col}_am_pct"] = 100 * norm.cdf(th)
        nuevas[f"{col}_am_a"] = th
        nuevas[f"{col}_am_sd"] = sd
    return pd.concat([out, pd.DataFrame(nuevas)], axis=1)


# ============================================================================================ identidades
def ids_congelados(temporada: str = TEMPORADA) -> pd.DataFrame:
    """(liga, player_id del modelo) → persona_id de los ficheros del A congelados (todas las temporadas)."""
    filas = []
    for f in sorted((DIR_A / "traducciones").glob("*.csv")):
        filas.append(pd.read_csv(f, usecols=["persona_id", "liga", "player_id", "temporada"], dtype={"player_id": str}))
    return pd.concat(filas, ignore_index=True)


def mapa_personas(t: pd.DataFrame, viejos: pd.DataFrame) -> dict:
    """persona_id de la tabla nueva → persona_id estable. Mayoría de los ids viejos de sus filas (cualquier temporada);
    personas sin ninguna fila conocida: ids nuevos por encima del máximo histórico."""
    v = viejos.drop_duplicates(["liga", "player_id", "temporada"])
    m = t[["persona_id", "liga", "player_id", "temporada"]].astype({"player_id": str}).merge(
        v.rename(columns={"persona_id": "viejo"}), on=["liga", "player_id", "temporada"], how="left")
    # filas sin pareja en su temporada (la temporada en curso con jugadores nuevos): pareja por liga + id en otra temporada
    otra = v.drop_duplicates(["liga", "player_id"], keep="last").set_index(["liga", "player_id"])["persona_id"]
    falta = m["viejo"].isna()
    m.loc[falta, "viejo"] = pd.Series(list(zip(m.loc[falta, "liga"], m.loc[falta, "player_id"])),
                                      index=m.index[falta]).map(otra)
    conocidos = m.dropna(subset=["viejo"]).groupby("persona_id")["viejo"].agg(lambda s: int(s.mode().iat[0]))
    mapa = conocidos.to_dict()
    sig = int(max(viejos["persona_id"].max(), max(mapa.values(), default=0))) + 1
    for p in sorted(set(t["persona_id"].unique()) - set(mapa)):
        mapa[p] = sig
        sig += 1
    return {int(k): int(v) for k, v in mapa.items()}


# ============================================================================================ B vigente
def b_vigente(a_nuevo: pd.DataFrame, temporada: str = TEMPORADA) -> pd.DataFrame:
    """Filas del B guardado de `temporada` cuyo jugador no ha sumado minutos desde entonces (las demás, sin B)."""
    f = DIR_B / "traducciones" / f"{temporada}.csv"
    if not f.exists():
        return pd.DataFrame()
    b = pd.read_csv(f, dtype={"player_id": str}, low_memory=False)
    a = a_nuevo[["liga", "player_id", "persona_id", "min"]].astype({"player_id": str})
    m = b.drop(columns=["persona_id"]).merge(a.rename(columns={"min": "_min_nuevo"}), on=["liga", "player_id"], how="inner")
    m = m[np.isclose(m["min"].astype(float), m["_min_nuevo"].astype(float), atol=0.5)].drop(columns=["_min_nuevo"])
    return m[b.columns]


# ============================================================================================ v3.2 incremental
def _cfg_v32() -> dict:
    import yaml
    return yaml.safe_load(CFG_V32.read_text(encoding="utf-8"))


def recombinar_v32(base: pd.DataFrame, v3: pd.DataFrame, temporadas_liga: dict, cfg: dict) -> pd.DataFrame:
    """Columnas <m>_v31* (combinación publicada) = reglas de bbnorm3.combinacion.ajustar_combinada.nuevas()."""
    from bbmodel.metricas import CATALOGO, destransformar, transformar
    from bbnorm3.combinacion import _cuantiles_mezcla
    from bbnorm3 import datos as D3
    from bbnorm3.prediccion import Z80
    cb = cfg["combinacion"]
    fx = RAIZ / cfg["validacion"].get("dir", "data/modelos/v3_2/validacion") / "examen_v32.json"
    if not fx.exists():
        fx = MOD / "v3_2" / "validacion" / "examen_v32.json"
    ex = json.loads(fx.read_text())
    clave = "combinada_b2_con_conocimiento_feb3"
    w_con = cb.get("peso_v3_conocimiento")
    if w_con is None:
        w_con = ex[clave]["peso_v3_conocimiento_elegido"]
    f_con = cb.get("factor_intervalo_conocimiento")
    if f_con is None:
        f_con = ex[clave].get("factor_intervalo_conocimiento_elegido", 1.0)
    w_met = ex["pesos_finales"]
    out = v3.copy()
    liga = base["liga"].reset_index(drop=True)
    conoc = liga.isin(cb["ligas_conocimiento"]).to_numpy()
    pocas = (liga.map(temporadas_liga).fillna(0) < cb["min_temporadas_liga"]).to_numpy()
    for col in D3.METRICAS:
        if f"{col}_am" not in base or f"{col}_v3" not in v3:
            continue
        tr = CATALOGO[col].transf
        T = lambda x: transformar(pd.to_numeric(x, errors="coerce").to_numpy(float), tr)  # noqa: E731
        m2, s2 = T(base[f"{col}_am"]), (T(base[f"{col}_am_hi"]) - T(base[f"{col}_am_lo"])) / (2 * Z80)
        m3, s3 = T(v3[f"{col}_v3"]), (T(v3[f"{col}_v3_hi"]) - T(v3[f"{col}_v3_lo"])) / (2 * Z80)
        w = np.full(len(v3), float(w_met.get(col, cb["peso_v3"])))
        w[conoc] = float(w_con)
        w[pocas] = 0.0
        sz = pd.to_numeric(v3[f"{col}_v3_sd_entre_z"], errors="coerce").to_numpy(float)
        w[sz > cb["max_discrepancia_redes"]] = 0.0
        sin_v2 = ~np.isfinite(m2) | ~np.isfinite(s2)
        w[sin_v2] = 1.0
        m2, s2 = np.where(sin_v2, m3, m2), np.where(sin_v2, s3, s2)
        sin_v3 = ~np.isfinite(m3) | ~np.isfinite(s3)
        w[sin_v3] = 0.0
        m3, s3 = np.where(sin_v3, m2, m3), np.where(sin_v3, s2, s3)
        s2, s3 = np.maximum(s2, 1e-6), np.maximum(s3, 1e-6)
        media = w * m3 + (1 - w) * m2
        lo, hi = _cuantiles_mezcla(w, m3, s3, m2, s2, (0.1, 0.9))
        fc = np.where(conoc, float(f_con), 1.0)
        lo, hi = media - fc * (media - lo), media + fc * (hi - media)
        out[f"{col}_v31"] = destransformar(media, tr)
        out[f"{col}_v31_lo"] = destransformar(lo, tr)
        out[f"{col}_v31_hi"] = destransformar(hi, tr)
        p2 = pd.to_numeric(base.get(f"{col}_am_pctel"), errors="coerce").to_numpy(float)
        p3 = pd.to_numeric(v3[f"{col}_v3_pctel"], errors="coerce").to_numpy(float)
        out[f"{col}_v31_pctel"] = np.where(np.isfinite(p2) & np.isfinite(p3), w * p3 + (1 - w) * p2,
                                           np.where(np.isfinite(p3), p3, p2))
        out[f"{col}_v31_peso_cvae"] = w
    return out


def v32_incremental(temporada: str = TEMPORADA, temporadas_liga: dict | None = None) -> pd.DataFrame:
    """v3_2/normalizado/<t>.csv.gz con la v2 al día y la CVAE congelada de cada fila."""
    from bbnorm3 import salidas
    from bbnorm3 import datos as D3
    f32 = DIR_V32 / f"{temporada}.csv.gz"
    viejo = pd.read_csv(f32, low_memory=False)
    nuevo = pd.read_csv(DIR_V1 / f"{temporada}.csv", low_memory=False)
    for d in (viejo, nuevo):
        d["player_id"] = d["player_id"].astype(str)
        d["liga"] = d["liga"].astype(str)
    cols_v3 = [c for c in viejo.columns if "_v3" in c and "_v31" not in c and c != "fuente_v3"]
    v3 = nuevo[["liga", "player_id"]].merge(viejo[["liga", "player_id"] + cols_v3 + ["fuente_v3"]]
                                            .drop_duplicates(["liga", "player_id"]), on=["liga", "player_id"], how="left")
    cfg = _cfg_v32()
    if temporadas_liga is None:
        temporadas_liga = {}
    comb_cols = recombinar_v32(nuevo, v3[cols_v3], temporadas_liga, cfg)
    comb = salidas.combinar_normalizado(nuevo, comb_cols, D3.METRICAS, sufijo="_v31",
                                        fuente="V3.2" if cfg.get("version") == "v3.2" else "V3.1")
    comb["fuente_v3"] = v3["fuente_v3"].fillna("v2_incremental").to_numpy()
    comb = comb[[c for c in viejo.columns if c in comb] + [c for c in comb if c not in viejo.columns]]
    comb.round(4).to_csv(f32, index=False)
    return comb


def temporadas_por_liga(t: pd.DataFrame, temporada: str = TEMPORADA) -> dict:
    """Temporadas con datos de cada liga hasta la temporada (salvaguarda «pocas temporadas» de la combinación)."""
    cfg = _cfg_v32()
    mn = cfg.get("datos", {}).get("min_minutos", 0)
    anio = int(temporada[:4])
    s = t[(t["anio"] <= anio) & (t["min"] >= mn)]
    return s.groupby("liga")["anio"].nunique().to_dict()


# ============================================================================================ orden
def ejecutar(temporada: str = TEMPORADA, recentrar: bool = True, progreso=print) -> dict:
    """Pasos 1-5 para `temporada`. Devuelve un resumen."""
    from bbmodel import dataset_normalizado as DN
    t = tabla()
    viejos = ids_congelados(temporada)
    mapa = mapa_personas(t, viejos)
    t = t.assign(persona_id=t["persona_id"].map(mapa).astype(int))
    progreso(f"  tabla: {len(t)} filas · {int((t['temporada'] == temporada).sum())} de {temporada}")
    a, zs = a_congelado(t, temporada, recentrar)
    a.round(4).to_csv(DIR_A / "traducciones" / f"{temporada}.csv", index=False)
    am = am_congelado(t, zs, temporada)
    am.round(4).to_csv(DIR_AM / "traducciones" / f"{temporada}.csv", index=False)
    b = b_vigente(a, temporada)
    if len(b) or (DIR_B / "traducciones" / f"{temporada}.csv").exists():
        b.round(4).to_csv(DIR_B / "traducciones" / f"{temporada}.csv", index=False)
    progreso(f"  A {len(a)} filas · amortiguada {int(am.filter(like='_am').notna().any(axis=1).sum())} · B vigente {len(b)}")
    v1 = DN.construir(temporada)
    v1.to_csv(DIR_V1 / f"{temporada}.csv", index=False, float_format="%.4f")
    comb = v32_incremental(temporada, temporadas_por_liga(t, temporada))
    nuevos = int((comb["fuente_v3"] == "v2_incremental").sum())
    progreso(f"  v3.2: {len(comb)} filas · {nuevos} sólo v2 (sin valor CVAE congelado)")
    return {"filas": int(len(comb)), "solo_v2": nuevos, "b_vigente": int(len(b)),
            "personas_nuevas": int(sum(1 for k, v in mapa.items() if v > viejos["persona_id"].max()))}
