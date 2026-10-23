"""Fase 7 — adaptación al cambio de liga (jugadores puente).

INTERFAZ PARA EL SIMULADOR (fase 8). Estable: no cambiar firmas ni claves.

    prior(liga_origen, liga_destino, grupo_nacionalidad, pos3, metrica="L")
        -> dict(delta_media, delta_sd, kappa_media, kappa_sd, n, nivel_fallback)
    grupo_nacionalidad(nacionalidad, liga_origen, liga_destino) -> str
    curva(g, delta, kappa) -> factor = 1 + delta·exp(−g/κ)

Convenio (docs/checkpoints/F7.md):
  * delta es un efecto RELATIVO (fracción) frente a lo esperado tras la normalización amortiguada (ŷ, el valor de
    origen traducido a la escala de la liga de destino): delta = −0,08 → en el partido g = 0 rinde al 92 % de ŷ.
    Negativo = penalización. El factor tiende a 1 (= ŷ) cuando g ≫ κ.
  * kappa en partidos jugados en la liga nueva: el 50 % del hueco se cierra en κ·ln 2 partidos y el 90 % en κ·ln 10.
  * metrica: pts_p100, ts_pct, usg_pct, ast_pct, reb_p100, per (relativas: ŷ·curva(g)), L_rel (relativa compuesta:
    media geométrica de y/ŷ de las 8 métricas del índice L; es el ADAPT% principal) o L (ADITIVA en unidades del
    índice L: L(g) = L̂ + delta·exp(−g/κ) = L̂ + (curva(g, delta, κ) − 1)).
  * nivel_fallback: celda (par + grupo + pos3) → par_grupo → par → escalon_grupo → escalon (escalón de la liga de
    destino) → global_grupo → global; «sin_datos» si aún no existe la tabla (valores por defecto del YAML).

Si data/modelos/adaptacion/adaptation_priors.csv no existe, prior() devuelve los valores por defecto del YAML
(nivel_fallback = «sin_datos»).

Resto del módulo (python -m bbfit adaptacion; detalle y resultados en docs/checkpoints/F7.md):
  1. traspasos entre competiciones (identificar_traspasos) con el persona_id del dataset normalizado;
  2. ŷ = origen traducido a la escala de destino con la normalización amortiguada (esperado_en_destino) y modelo
     jerárquico bayesiano del log-cociente y/ŷ (gibbs_jerarquico, ModeloDelta) con covariables;
  3. curva por partido dentro de jugador con grupo de control (estadisticos_curva, ajustar_kappa, ajustar_curvas);
  4. censura por IPCW (pesos_ipcw) y adaptación de la 2.ª temporada (segunda_temporada);
  5. tabla de priors con proyección a la forma de la interfaz (tabla_priors, proyectar_interfaz);
  6. ADAPT% por traspaso, examen temporal / dejando fuera una liga y calibración (escribir_salidas).
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DIR_MOD, cargar

DIR_SALIDA = DIR_MOD / "adaptacion"
FICHERO_PRIORS = DIR_SALIDA / "adaptation_priors.csv"
METRICAS_PRIOR = ("pts_p100", "ts_pct", "usg_pct", "ast_pct", "reb_p100", "per", "L", "L_rel")
COMODIN = "*"


def cfg() -> dict:
    return cargar("adaptacion")


# ============================================================================================ interfaz: curva
def curva(g, delta, kappa):
    """Factor multiplicativo sobre lo esperado tras la normalización en el partido g (0, 1, 2…) de la liga nueva:
    1 + delta·exp(−g/κ). Acepta escalares o arrays (numpy difunde). κ ≤ 0 o no finito → sin curva (factor 1 + delta
    en g = 0 y 1 después, el límite κ → 0)."""
    g = np.asarray(g, dtype=float)
    delta = np.asarray(delta, dtype=float)
    kappa = np.asarray(kappa, dtype=float)
    k_ok = np.isfinite(kappa) & (kappa > 0)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        dec = np.where(k_ok, np.exp(-np.clip(g, 0, None) / np.where(k_ok, kappa, 1.0)), np.where(g <= 0, 1.0, 0.0))
    f = 1.0 + delta * dec
    return float(f) if np.ndim(f) == 0 else f


def partidos_hasta(fraccion: float, kappa: float) -> float:
    """Partidos para cerrar una fracción del hueco: exp(−g/κ) = 1 − fracción → g = −κ·ln(1 − fracción)."""
    if not (0 < fraccion < 1) or not np.isfinite(kappa):
        return float("nan")
    return float(-kappa * math.log(1 - fraccion))


# ============================================================================================ interfaz: grupo
def _isos(nacionalidad) -> list[str]:
    """Códigos ISO alfa-2 de un texto de nacionalidad («US», «Estados Unidos», «Alemania / Estados Unidos», «DE|US»)."""
    if nacionalidad is None or (isinstance(nacionalidad, float) and math.isnan(nacionalidad)):
        return []
    try:
        from bbmodel.nacionalidad import codigo
    except Exception:  # noqa: BLE001
        codigo = None
    out = []
    for parte in str(nacionalidad).replace("|", "/").split("/"):
        p = parte.strip()
        if not p:
            continue
        c = codigo(p) if codigo else None
        if c is None and len(p) == 2 and p.isalpha():
            c = p.upper()
        if c is None and p.upper() in ("USA", "EEUU", "EE. UU.", "EE.UU."):
            c = "US"
        if c and c not in out:
            out.append(c)
    return out


def grupo_nacionalidad(nacionalidad, liga_origen: str, liga_destino: str) -> str:
    """Grupo de nacionalidad / origen formativo de un traspaso liga_origen → liga_destino (configs/adaptacion.yaml).

    EEUU_a_Europa · otro_desde_EEUU · hacia_EEUU · intra_EEUU · nacional_mismo_pais · extranjero_mismo_pais ·
    europeo_cambia_liga · extranjero_cambia_pais · desconocido. Sin nacionalidad → «desconocido» salvo en los grupos
    que sólo dependen de las ligas (hacia_EEUU, intra_EEUU). Las copas europeas no tienen país (EUR): entrar o salir de
    una copa cuenta como cambio de competición europea."""
    c = cfg()
    paises = c["paises_liga"]
    europa = set(c["paises_europeos"])
    po, pd_ = paises.get(str(liga_origen)), paises.get(str(liga_destino))
    us_o, us_d = po == "US", pd_ == "US"
    if us_o and us_d:
        return "intra_EEUU"
    if us_d:
        return "hacia_EEUU"
    nats = _isos(nacionalidad)
    if not nats:
        return "desconocido"
    if us_o:
        return "EEUU_a_Europa" if "US" in nats else "otro_desde_EEUU"
    if po is not None and po == pd_ and po != "EUR":
        return "nacional_mismo_pais" if po in nats else "extranjero_mismo_pais"
    if any(n in europa for n in nats):
        return "europeo_cambia_liga"
    return "extranjero_cambia_pais"


# ============================================================================================ interfaz: prior
def escalon_de(liga: str) -> str | None:
    """Escalón de nivel de una liga (configs/normalization.yaml → escalones)."""
    for k, ligas in (cargar("normalization").get("escalones") or {}).items():
        if liga in ligas:
            return k
    return None


@lru_cache(maxsize=4)
def _tabla_priors(ruta: str, mtime: float) -> pd.DataFrame:  # mtime en la clave: se relee si cambia el fichero
    return pd.read_csv(ruta, dtype={"liga_origen": str, "liga_destino": str, "grupo_nacionalidad": str, "pos3": str,
                                    "escalon_destino": str, "metrica": str, "nivel": str})


def cargar_priors(ruta: Path | None = None) -> pd.DataFrame | None:
    p = Path(ruta or FICHERO_PRIORS)
    if not p.exists():
        return None
    return _tabla_priors(str(p), p.stat().st_mtime)


def _defecto(nivel: str = "sin_datos") -> dict:
    pr = cfg()["priors"]
    return {"delta_media": 0.0, "delta_sd": float(pr["delta_sd_defecto"]), "kappa_media": float(pr["kappa_defecto"]),
            "kappa_sd": float(pr["kappa_sd_defecto"]), "n": 0, "nivel_fallback": nivel}


def prior(liga_origen: str, liga_destino: str, grupo_nacionalidad: str, pos3: str, metrica: str = "L",
          ruta: Path | None = None) -> dict:
    """Prior de adaptación para un traspaso: dict(delta_media, delta_sd, kappa_media, kappa_sd, n, nivel_fallback).

    Busca en adaptation_priors.csv del nivel más fino al más grueso y usa el primero con n ≥ priors.n_min_celda
    (el nivel global se usa siempre que exista). Las estimaciones de cada nivel ya están contraídas hacia el nivel
    superior (modelo jerárquico), así que la reserva sólo decide cuánta información propia hay."""
    if metrica not in METRICAS_PRIOR:
        raise ValueError(f"métrica desconocida: {metrica!r} (válidas: {', '.join(METRICAS_PRIOR)})")
    t = cargar_priors(ruta)
    if t is None or t.empty:
        return _defecto()
    t = t[t["metrica"] == metrica]
    if t.empty:
        return _defecto()
    n_min = int(cfg()["priors"]["n_min_celda"])
    esc = escalon_de(liga_destino) or COMODIN
    lo, ld, gr, p3 = str(liga_origen), str(liga_destino), str(grupo_nacionalidad), str(pos3)
    claves = [("celda", lo, ld, gr, p3), ("par_grupo", lo, ld, gr, COMODIN), ("par", lo, ld, COMODIN, COMODIN),
              ("escalon_grupo", COMODIN, COMODIN, gr, COMODIN), ("escalon", COMODIN, COMODIN, COMODIN, COMODIN),
              ("global_grupo", COMODIN, COMODIN, gr, COMODIN), ("global", COMODIN, COMODIN, COMODIN, COMODIN)]
    for nivel, a, b, c_, d in claves:
        s = t[(t["nivel"] == nivel) & (t["liga_origen"] == a) & (t["liga_destino"] == b)
              & (t["grupo_nacionalidad"] == c_) & (t["pos3"] == d)]
        if nivel.startswith("escalon"):
            s = s[s["escalon_destino"] == esc]
        if s.empty:
            continue
        r = s.iloc[0]
        if int(r["n"]) < n_min and nivel != "global":
            continue
        return {"delta_media": float(r["delta_media"]), "delta_sd": float(r["delta_sd"]),
                "kappa_media": float(r["kappa_media"]), "kappa_sd": float(r["kappa_sd"]), "n": int(r["n"]),
                "nivel_fallback": nivel}
    return _defecto()


# ================================================================================================ datos
# Métricas que se traducen: las 6 clave (reb_p100 = oreb_p100 + dreb_p100) y las 8 del índice de nivel L
METRICAS_CLAVE = ["pts_p100", "ts_pct", "usg_pct", "ast_pct", "reb_p100", "per"]
METRICAS_BASE = ["pts_p100", "ts_pct", "usg_pct", "ast_pct", "oreb_p100", "dreb_p100", "per", "game_score_p40",
                 "ws_per_40", "ortg", "drtg", "efg_pct"]
DIR_NORM = DIR_MOD / "normalizado"
DIR_TRAD = DIR_MOD / "normalizacion_amortiguada" / "traducciones"
FICHERO_OFFSETS = DIR_MOD / "normalizacion_amortiguada" / "league_offsets.csv"
DIR_PJ = DIR_MOD / "roles" / "partidos_jugador"
DIR_CACHE = DIR_MOD.parent.parent / "experimentos" / "cache_adaptacion"   # no versionado (.gitignore: experimentos/)
COLS_IDENT = ["persona_id", "liga", "temporada", "player_id", "nombre", "team_id", "equipo", "pos3", "edad",
              "anio_nac", "nacionalidad", "gp", "min", "L"]


def nivel_metricas() -> dict:
    """Métricas del índice de nivel L y su signo (bbmodel.contexto.NIVEL: DRtg con signo −)."""
    from bbmodel.contexto import NIVEL
    return dict(NIVEL)


def _temporadas_norm() -> list[str]:
    return sorted(p.stem for p in DIR_NORM.glob("*.csv"))


def cargar_temporadas(temporadas: list[str] | None = None) -> pd.DataFrame:
    """Una fila por jugador-liga-temporada (temporada regular) del dataset normalizado con, por métrica: el valor
    observado `<m>_obs`, el equivalente EuroLeague amortiguado `<m>_am` y la capacidad amortiguada en DT EuroLeague
    `<m>_th` (= `<m>_am_a` de normalizacion_amortiguada/traducciones) con su desviación `<m>_th_sd`."""
    mets = sorted(set(METRICAS_BASE) | set(nivel_metricas()))
    fr = []
    for temp in temporadas or _temporadas_norm():
        p = DIR_NORM / f"{temp}.csv"
        if not p.exists():
            continue
        cab = pd.read_csv(p, nrows=0).columns
        cols = [c for c in COLS_IDENT if c in cab] + [c for m in mets for c in (f"{m}_obs", f"{m}_am") if c in cab]
        d = pd.read_csv(p, usecols=cols, dtype={"player_id": str, "persona_id": str, "team_id": str}, low_memory=False)
        pt = DIR_TRAD / f"{temp}.csv"
        if pt.exists():
            tc = [c for m in mets for c in (f"{m}_am_a", f"{m}_am_sd")]
            t = pd.read_csv(pt, usecols=lambda c: c in {"persona_id", "liga"} | set(tc), dtype={"persona_id": str})
            t = t.drop_duplicates(["liga", "persona_id"])
            t = t.rename(columns={f"{m}_am_a": f"{m}_th" for m in mets} | {f"{m}_am_sd": f"{m}_th_sd" for m in mets})
            d = d.merge(t, on=["liga", "persona_id"], how="left")
        fr.append(d)
    out = pd.concat(fr, ignore_index=True)
    out["anio"] = out["temporada"].str[:4].astype(int)
    return out


def cargar_partidos(temporadas: list[str] | None = None) -> pd.DataFrame:
    """Tabla partido × jugador de la fase 3 (sólo partidos jugados), todas las fases, en orden cronológico."""
    cols = ["liga", "temporada", "game_id", "fase", "team_id", "player_id", "fecha", "jugo", "min", "poss_on", "pts",
            "ast", "fga", "fta", "usg_tiro", "team_fga_on", "team_fta_on", "entrenador_id", "orden_equipo"]
    fr = []
    for temp in temporadas or _temporadas_norm():
        p = DIR_PJ / f"{temp}.csv.gz"
        if not p.exists():
            continue
        d = pd.read_csv(p, usecols=cols, dtype={"player_id": str, "team_id": str, "game_id": str,
                                                "entrenador_id": str}, low_memory=False)
        d = d[d["jugo"].astype(str).str.lower().isin(["true", "1"])].drop(columns=["jugo"])
        fr.append(d)
    out = pd.concat(fr, ignore_index=True)
    out["fecha"] = pd.to_datetime(out["fecha"], errors="coerce")
    return out.sort_values(["liga", "temporada", "player_id", "fecha", "game_id"]).reset_index(drop=True)


def resumen_etapas(pj: pd.DataFrame) -> pd.DataFrame:
    """Por jugador-liga-temporada: primer y último partido, partidos, equipo principal (más minutos) y entrenador
    modal de sus partidos (NaN si la fuente no lo da)."""
    g = pj.groupby(["liga", "temporada", "player_id"], sort=False)
    r = g.agg(fecha_ini=("fecha", "min"), fecha_fin=("fecha", "max"), partidos=("game_id", "nunique")).reset_index()
    mt = pj.groupby(["liga", "temporada", "player_id", "team_id"], sort=False)["min"].sum().reset_index()
    mt = mt.sort_values("min", ascending=False).drop_duplicates(["liga", "temporada", "player_id"])
    r = r.merge(mt[["liga", "temporada", "player_id", "team_id"]].rename(columns={"team_id": "team_pj"}),
                on=["liga", "temporada", "player_id"], how="left")
    en = pj.dropna(subset=["entrenador_id"]).groupby(["liga", "temporada", "player_id"])["entrenador_id"] \
        .agg(lambda s: s.mode().iat[0]).rename("entrenador_id").reset_index()
    r = r.merge(en, on=["liga", "temporada", "player_id"], how="left")
    # partidos que su equipo principal juega desde su primer partido con él (minutos disponibles tras llegar)
    eq = pj[["liga", "temporada", "team_id", "game_id", "fecha"]].drop_duplicates(["liga", "temporada", "team_id", "game_id"])
    pri = pj.merge(r[["liga", "temporada", "player_id", "team_pj"]], left_on=["liga", "temporada", "player_id", "team_id"],
                   right_on=["liga", "temporada", "player_id", "team_pj"])
    pri = pri.groupby(["liga", "temporada", "player_id", "team_pj"])["fecha"].min().rename("f0").reset_index()
    x = pri.merge(eq.rename(columns={"team_id": "team_pj"}), on=["liga", "temporada", "team_pj"])
    disp = x[x["fecha"] >= x["f0"]].groupby(["liga", "temporada", "player_id"])["game_id"].nunique().rename("partidos_equipo_desde_llegada")
    return r.merge(disp.reset_index(), on=["liga", "temporada", "player_id"], how="left")


def _concurrentes() -> set:
    from bbmodel.identidad import CONCURRENTES
    return set(CONCURRENTES)


def identificar_traspasos(tem: pd.DataFrame, etapas: pd.DataFrame, c: dict | None = None) -> pd.DataFrame:
    """Todos los cambios de competición de cada persona (persona_id del dataset normalizado: nombre + crosswalk 0,75).

    * entre temporadas: liga B en t+1 que la persona no jugó en t (ni un minuto), con origen A en t (≥ min minutos).
      A = la liga de t con más minutos que deja (tipo «salida»); si no deja ninguna, la de más minutos (tipo
      «adicion»: p. ej. de ACB a ACB + EuroLeague).
    * dentro de la temporada: A y B en la misma temporada, pareja no concurrente (no copa europea × liga nacional,
      no NBA × G League) y B empieza cuando A ha terminado (tolerancia y solape máximo en el YAML).
    Una fila por (persona, liga_destino, temporada_destino); si hay las dos posibilidades, gana la de dentro de la
    temporada (el origen inmediato)."""
    c = c or cfg()
    tr = c["traspasos"]
    t = tem.merge(etapas, on=["liga", "temporada", "player_id"], how="left")
    t = t[t["persona_id"].notna()]
    conc = _concurrentes()
    filas = []
    por_persona = {p: g for p, g in t.groupby("persona_id", sort=False)}
    for p, g in por_persona.items():
        g = g.sort_values(["anio", "min"], ascending=[True, False])
        anios = sorted(g["anio"].unique())
        por_anio = {a: g[g["anio"] == a] for a in anios}
        ligas_vistas: set = set()
        for a in anios:
            cur = por_anio[a]
            # --- dentro de la temporada
            ok = cur[(cur["min"] >= min(tr["min_minutos_origen"], tr["min_minutos_destino"]))]
            for _, x in ok.iterrows():
                for _, y in ok.iterrows():
                    if x["liga"] == y["liga"] or frozenset({x["liga"], y["liga"]}) in conc:
                        continue
                    if x["min"] < tr["min_minutos_origen"] or y["min"] < tr["min_minutos_destino"]:
                        continue
                    if pd.isna(x["fecha_fin"]) or pd.isna(y["fecha_ini"]):
                        continue
                    if y["fecha_ini"] < x["fecha_fin"] - pd.Timedelta(days=tr["tolerancia_dias_intra"]):
                        continue
                    filas.append(_fila_traspaso(p, x, y, "intra_temporada", y["liga"] in ligas_vistas))
            # --- entre temporadas
            if a - 1 in por_anio:
                prev = por_anio[a - 1]
                prev_ligas = set(prev["liga"])
                orig = prev[prev["min"] >= tr["min_minutos_origen"]]
                if not orig.empty:
                    for _, y in cur.iterrows():
                        if y["liga"] in prev_ligas or y["min"] <= 0:
                            continue
                        deja = orig[~orig["liga"].isin(set(cur["liga"]))]
                        x = (deja if not deja.empty else orig).iloc[0]
                        tipo = "salida" if not deja.empty else "adicion"
                        filas.append(_fila_traspaso(p, x, y, tipo, y["liga"] in ligas_vistas))
            ligas_vistas |= set(cur["liga"])
    m = pd.DataFrame(filas)
    if m.empty:
        return m
    m["_prio"] = (m["tipo"] != "intra_temporada").astype(int)
    m = m.sort_values(["persona_id", "liga_destino", "temporada_destino", "_prio"]) \
        .drop_duplicates(["persona_id", "liga_destino", "temporada_destino"]).drop(columns="_prio")
    return m.reset_index(drop=True)


def _fila_traspaso(p, x, y, tipo: str, regreso: bool) -> dict:
    return {"persona_id": p, "tipo": tipo, "regreso": bool(regreso),
            "liga_origen": x["liga"], "temporada_origen": x["temporada"], "anio_origen": int(x["anio"]),
            "player_id_origen": x["player_id"], "liga_destino": y["liga"], "temporada_destino": y["temporada"],
            "anio_destino": int(y["anio"]), "player_id_destino": y["player_id"], "nombre": y["nombre"],
            "min_origen": float(x["min"]), "min_destino": float(y["min"]), "gp_destino": y["gp"]}


# ================================================================================================ esperado
def cargar_normalizacion() -> dict:
    """Parámetros del algoritmo A (pasos 1-2: μ, τ por liga-temporada-posición; escala s; deriva por edad) y niveles
    amortiguados por competición-temporada (league_offsets.csv: δ, sd, λ, forma)."""
    import json
    params = json.loads((DIR_MOD / "algoritmo_A" / "parametros.json").read_text(encoding="utf-8"))
    off = pd.read_csv(FICHERO_OFFSETS)
    return {"params": params, "offsets": off.set_index(["competicion", "temporada", "metrica"])}


def _tramo_edad(edad) -> str:
    from bbmodel.enlace import tramo_edad
    return tramo_edad(float(edad) if edad is not None and np.isfinite(edad) else np.nan)


def esperado_en_destino(theta, theta_sd, liga_d: str, temp_d: str, pos3: str, metrica: str, norm: dict,
                        anios: int, edad) -> tuple[float, float, float, float]:
    """Traduce la capacidad de origen (θ en DT EuroLeague, `<m>_am_a`) a la escala de la liga de destino.

        θ' = θ + d(edad)·años                          deriva por edad del A (0 dentro de la temporada)
        z_d = (θ' − δ_d)/(λ_d·s_d)                     inversa de θ = δ + λ·F(s·z) con F = identidad (variante elegida)
        ŷ   = T⁻¹(μ_d,pos + τ_d,pos·z_d)               valor esperado en la escala de la liga de destino
        var_T = (τ_d/(λ_d s_d))²·(sd_θ² + sd_δd² + η²)   (escala transformada)
    Devuelve (ŷ, ŷ_lo, ŷ_hi (80 %), centro en la escala transformada). NaN si falta cualquier pieza (no se inventa).
    """
    from bbmodel.metricas import CATALOGO, destransformar
    from bbmodel.modelo import _entorno
    p = norm["params"]["metricas"].get(metrica)
    nan4 = (np.nan, np.nan, np.nan, np.nan)
    if p is None or not np.isfinite(theta) or not isinstance(pos3, str):
        return nan4
    e = p["enlace"]
    if liga_d not in e["s"]:
        return nan4
    if liga_d == "euroleague":
        dl, dsd, lam = 0.0, 0.0, 1.0
    else:
        k = (liga_d, temp_d, metrica)
        if k not in norm["offsets"].index:
            return nan4
        r = norm["offsets"].loc[k]
        if int(r.get("forma_no_lineal", 0)) != 0:
            return nan4          # con mapeo monótono haría falta su inversa (no persistida): no se traduce
        dl, dsd, lam = float(r["media"]), float(r["sd"]), float(r["lambda"])
    der = float(e["deriva"].get(_tramo_edad(edad), 0.0)) * anios
    s = float(e["s"][liga_d])
    mu, tau = _entorno(p["suerte"], liga_d, temp_d, pos3)
    if not (np.isfinite(mu) and np.isfinite(tau) and s > 0):
        return nan4
    zd = (theta + der - dl) / (lam * s)
    cen = mu + tau * zd
    sd_t = tau / (lam * s) * np.sqrt((theta_sd if np.isfinite(theta_sd) else 0.0) ** 2 + dsd ** 2 + float(e.get("eta2", 0.0)))
    tr = CATALOGO[metrica].transf
    z80 = 1.2815515655446004
    return (float(destransformar(cen, tr)), float(destransformar(cen - z80 * sd_t, tr)),
            float(destransformar(cen + z80 * sd_t, tr)), float(cen))


def escala_L(tem: pd.DataFrame) -> dict:
    """Escala del índice L (bbmodel.contexto.escala_nivel) con los valores amortiguados `<m>_am`."""
    from bbmodel.contexto import escala_nivel
    n = tem.copy()
    for m in nivel_metricas():
        n[m] = n[f"{m}_am"]
    return escala_nivel(n)


def valor_el(theta, pos3: str, metrica: str, norm: dict) -> float:
    """Capacidad θ (DT EuroLeague) → valor en la EuroLeague de referencia (2025-26), como en traducir()."""
    from bbmodel.metricas import CATALOGO, destransformar
    from bbmodel.modelo import TEMPORADA_REF, _entorno
    p = norm["params"]["metricas"][metrica]
    mu, tau = _entorno(p["suerte"], "euroleague", TEMPORADA_REF, pos3) if isinstance(pos3, str) else (np.nan, np.nan)
    return float(destransformar(mu + tau * theta, CATALOGO[metrica].transf))


def theta_observado(y_obs, liga: str, temp: str, pos3: str, metrica: str, norm: dict) -> float:
    """Valor observado → capacidad en DT EuroLeague SIN contracción (θ = δ + s·z_obs): la vara del lado destino."""
    from bbmodel.metricas import CATALOGO, transformar
    from bbmodel.modelo import _entorno
    p = norm["params"]["metricas"][metrica]
    if not np.isfinite(y_obs) or not isinstance(pos3, str):
        return np.nan
    mu, tau = _entorno(p["suerte"], liga, temp, pos3)
    if liga == "euroleague":
        dl = 0.0
    else:
        k = (liga, temp, metrica)
        if k not in norm["offsets"].index:
            return np.nan
        dl = float(norm["offsets"].loc[k]["media"])
    s = float(p["enlace"]["s"].get(liga, np.nan))
    z = (float(transformar(y_obs, CATALOGO[metrica].transf)) - mu) / tau
    return dl + s * z


def anadir_esperado(mov: pd.DataFrame, tem: pd.DataFrame, norm: dict, c: dict | None = None) -> pd.DataFrame:
    """Para cada traspaso y métrica: esperado tras la normalización ŷ (y su intervalo del 80 %), observado y, cociente
    y/ŷ y log-cociente; L: efecto aditivo (índice L en la vara EuroLeague) y cociente compuesto (media geométrica de
    los cocientes de sus 8 métricas, DRtg invertido)."""
    c = c or cfg()
    rlo, rhi = c["metricas"]["ratio_recorte"]
    niv = nivel_metricas()
    esc = escala_L(tem)
    key = ["liga", "temporada", "player_id"]
    o = tem.set_index(key)
    filas = []
    for r in mov.itertuples(index=False):
        xo = o.loc[(r.liga_origen, r.temporada_origen, r.player_id_origen)]
        xd = o.loc[(r.liga_destino, r.temporada_destino, r.player_id_destino)]
        if isinstance(xo, pd.DataFrame):
            xo = xo.iloc[0]
        if isinstance(xd, pd.DataFrame):
            xd = xd.iloc[0]
        pos = xd["pos3"] if isinstance(xd["pos3"], str) else xo["pos3"]
        anios = int(r.anio_destino - r.anio_origen)
        f = {"pos3": pos, "edad": xo["edad"] if pd.notna(xo["edad"]) else (xd["edad"] - anios if pd.notna(xd["edad"]) else np.nan)}
        mets = sorted(set(METRICAS_BASE) | set(niv))
        th_e, th_o = {}, {}
        for m in mets:
            th = xo.get(f"{m}_th", np.nan)
            yh, ylo, yhi, _ = esperado_en_destino(th, xo.get(f"{m}_th_sd", np.nan), r.liga_destino,
                                                  r.temporada_destino, pos, m, norm, anios, f["edad"])
            y = xd.get(f"{m}_obs", np.nan)
            f[f"{m}_esp"], f[f"{m}_esp_lo"], f[f"{m}_esp_hi"], f[f"{m}_obs"] = yh, ylo, yhi, y
            if m in niv:
                der = float(norm["params"]["metricas"][m]["enlace"]["deriva"].get(_tramo_edad(f["edad"]), 0.0)) * anios
                th_e[m] = th + der if np.isfinite(th) else np.nan
                th_o[m] = theta_observado(y, r.liga_destino, r.temporada_destino, pos, m, norm)
        # reb_p100 = oreb + dreb (cada uno traducido por separado)
        for suf in ("esp", "esp_lo", "esp_hi", "obs"):
            f[f"reb_p100_{suf}"] = f[f"oreb_p100_{suf}"] + f[f"dreb_p100_{suf}"]
        for m in METRICAS_CLAVE + [m for m in niv if m not in METRICAS_CLAVE]:
            y, yh = f[f"{m}_obs"], f[f"{m}_esp"]
            ok = np.isfinite(y) and np.isfinite(yh) and yh > 0 and y > 0 and rlo <= y / yh <= rhi
            f[f"{m}_ratio"] = y / yh if ok else np.nan
            f[f"{m}_logr"] = float(np.log(y / yh)) if ok else np.nan
        # L: aditivo (misma fórmula que bbmodel.contexto.indice_nivel) y compuesto relativo
        def _L(ths):
            zs = []
            for m, sg in niv.items():
                v = valor_el(ths.get(m, np.nan), pos, m, norm) if np.isfinite(ths.get(m, np.nan)) else np.nan
                zs.append(sg * (v - esc[m][0]) / esc[m][1] if np.isfinite(v) else np.nan)
            zs = np.array(zs, float)
            return float(np.nanmean(zs)) if np.isfinite(zs).sum() >= 5 else np.nan
        f["L_esp"], f["L_obs"] = _L(th_e), _L(th_o)
        f["L_origen"] = xo.get("L", np.nan)
        f["L_delta"] = f["L_obs"] - f["L_esp"]
        lr = [niv[m] * f[f"{m}_logr"] for m in niv if np.isfinite(f[f"{m}_logr"])]
        f["L_logr"] = float(np.mean(lr)) if len(lr) >= 5 else np.nan
        f["L_ratio"] = float(np.exp(f["L_logr"])) if np.isfinite(f["L_logr"]) else np.nan
        f["nacionalidad"] = xd.get("nacionalidad") if pd.notna(xd.get("nacionalidad")) else xo.get("nacionalidad")
        f["team_origen"], f["team_destino"] = xo.get("team_pj", np.nan), xd.get("team_pj", np.nan)
        f["entrenador_origen"], f["entrenador_destino"] = xo.get("entrenador_id", np.nan), xd.get("entrenador_id", np.nan)
        f["fecha_ini_destino"], f["partidos_destino"] = xd.get("fecha_ini", pd.NaT), xd.get("partidos", np.nan)
        f["partidos_equipo_destino"] = xd.get("partidos_equipo_desde_llegada", np.nan)
        filas.append(f)
    return pd.concat([mov.reset_index(drop=True), pd.DataFrame(filas)], axis=1)


# ================================================================================================ covariables
def nacionalidad_persona(tem: pd.DataFrame) -> pd.DataFrame:
    """Nacionalidad (códigos ISO, «US» o «DE|US») por persona_id, combinando: dataset normalizado, nacionalidades.csv,
    crosswalk (FEB, LNB, G League) y la columna de los procesados (FEB). Moda por persona; NaN si ninguna fuente la da
    (no se imputa). Devuelve persona_id, nacionalidad_iso, nacionalidad_fuente_f7."""
    from .config import DIR_PROC
    regs = []
    k = tem[["persona_id", "liga", "temporada", "player_id", "nacionalidad"]].dropna(subset=["persona_id"])
    k1 = k.dropna(subset=["nacionalidad"])
    regs.append(pd.DataFrame({"persona_id": k1["persona_id"], "iso": k1["nacionalidad"].map(lambda v: "|".join(_isos(v))),
                              "fuente": "normalizado"}))
    pn = DIR_MOD / "nacionalidades.csv"
    if pn.exists():
        n = pd.read_csv(pn, dtype={"player_id": str}).dropna(subset=["nacionalidad_iso"])
        n = k[["persona_id", "liga", "temporada", "player_id"]].merge(n[["liga", "temporada", "player_id", "nacionalidad_iso"]],
                                                                     on=["liga", "temporada", "player_id"])
        regs.append(pd.DataFrame({"persona_id": n["persona_id"], "iso": n["nacionalidad_iso"], "fuente": "nacionalidades"}))
    pc = DIR_PROC / "player_id_crosswalk.csv"
    if pc.exists():
        x = pd.read_csv(pc, dtype={"fuente_id": str}).dropna(subset=["nacionalidad_iso"])
        x = x.rename(columns={"fuente_liga": "liga", "fuente_id": "player_id"})[["liga", "player_id", "nacionalidad_iso"]]
        x = k[["persona_id", "liga", "player_id"]].drop_duplicates().merge(x.drop_duplicates(["liga", "player_id"]),
                                                                            on=["liga", "player_id"])
        regs.append(pd.DataFrame({"persona_id": x["persona_id"], "iso": x["nacionalidad_iso"], "fuente": "crosswalk"}))
    for temp in sorted(k["temporada"].unique()):
        for liga in ("feb1", "feb2", "feb3", "lnb", "gleague"):
            p = DIR_PROC / temp / "ligas" / f"{liga}.csv"
            if not p.exists():
                continue
            d = pd.read_csv(p, usecols=lambda c: c in {"player_id", "nacionalidad"}, dtype={"player_id": str})
            if "nacionalidad" not in d:
                continue
            d = d.dropna(subset=["nacionalidad"]).drop_duplicates("player_id")
            d = k[(k["liga"] == liga) & (k["temporada"] == temp)][["persona_id", "player_id"]].merge(d, on="player_id")
            regs.append(pd.DataFrame({"persona_id": d["persona_id"],
                                      "iso": d["nacionalidad"].map(lambda v: "|".join(_isos(v))), "fuente": "procesado"}))
    r = pd.concat(regs, ignore_index=True)
    r = r[r["iso"].astype(str).str.len() > 0]
    moda = r.groupby("persona_id")["iso"].agg(lambda s: s.mode().iat[0]).rename("nacionalidad_iso")
    fu = r.groupby("persona_id")["fuente"].agg(lambda s: "+".join(sorted(set(s)))).rename("nacionalidad_fuente_f7")
    return pd.concat([moda, fu], axis=1).reset_index()


ROLES_ORDEN = ["RESIDUAL", "PROFUNDIDAD", "ROTACION", "TITULAR", "GO_TO_GUY"]
ESTILOS_P = ["p_pistons", "p_isolation", "p_old_school", "p_spacing", "p_circulacion", "p_pintura"]


def salto_nivel(norm: dict, liga_o: str, temp_o: str, liga_d: str, temp_d: str) -> float:
    """Salto de nivel destino − origen (DT EuroLeague): mediana con signo de las 8 métricas de nivel de
    league_offsets.csv (DRtg invertido). Positivo = sube de nivel."""
    vals = []
    for m, sg in nivel_metricas().items():
        dv = []
        for liga, temp in ((liga_d, temp_d), (liga_o, temp_o)):
            if liga == "euroleague":
                dv.append(0.0)
            else:
                k = (liga, temp, m)
                dv.append(float(norm["offsets"].loc[k]["media"]) if k in norm["offsets"].index else np.nan)
        vals.append(sg * (dv[0] - dv[1]))
    vals = np.array(vals, float)
    return float(np.nanmedian(vals)) if np.isfinite(vals).any() else np.nan


def anadir_covariables(mov: pd.DataFrame, tem: pd.DataFrame, nac: pd.DataFrame, norm: dict,
                       c: dict | None = None) -> pd.DataFrame:
    """Covariables del traspaso: grupo de nacionalidad, pos3, edad, roles de origen y destino, arquetipo del jugador y
    distancia de estilo entre equipos (estilos_unificados), cambio de entrenador, salto de nivel, banderas. Lo que no
    existe queda NaN con su bandera `<x>_desconocido` (nunca se imputa un valor)."""
    c = c or cfg()
    m = mov.drop(columns=[x for x in ("nacionalidad_iso", "nacionalidad_fuente_f7") if x in mov]).merge(nac, on="persona_id", how="left")
    m["nacionalidad_desconocida"] = m["nacionalidad_iso"].isna()
    m["grupo_nacionalidad"] = [grupo_nacionalidad(n, a, b) for n, a, b in
                               zip(m["nacionalidad_iso"], m["liga_origen"], m["liga_destino"])]
    m["pais_origen"] = m["liga_origen"].map(c["paises_liga"])
    m["pais_destino"] = m["liga_destino"].map(c["paises_liga"])
    m["escalon_destino"] = m["liga_destino"].map(escalon_de)
    m["escalon_origen"] = m["liga_origen"].map(escalon_de)
    # primera temporada en Europa (estadounidenses que llegan de NBA/G League)
    eur = tem[~tem["liga"].isin(["nba", "gleague"])].groupby("persona_id")["anio"].min()
    m["primer_anio_europa"] = m["persona_id"].map(eur).ge(m["anio_destino"]) & m["pais_origen"].eq("US") & ~m["pais_destino"].eq("US")
    # edad
    m["edad_desconocida"] = m["edad"].isna()
    # roles (fase 3): rol modal del jugador en la liga-temporada
    from .config import DIR_MOD as _DM
    r = pd.read_csv(_DM / "roles" / "player_role_season.csv.gz", dtype={"player_id": str, "team_id": str},
                    usecols=["liga", "temporada", "player_id", "rol_modal_jugador_liga"]).drop_duplicates(["liga", "temporada", "player_id"])
    r["rol_num"] = r["rol_modal_jugador_liga"].map({k: i for i, k in enumerate(ROLES_ORDEN)})
    ro = r.rename(columns={"liga": "liga_origen", "temporada": "temporada_origen", "player_id": "player_id_origen",
                           "rol_modal_jugador_liga": "rol_origen", "rol_num": "rol_origen_num"})
    rd = r.rename(columns={"liga": "liga_destino", "temporada": "temporada_destino", "player_id": "player_id_destino",
                           "rol_modal_jugador_liga": "rol_destino", "rol_num": "rol_destino_num"})
    m = m.merge(ro, on=["liga_origen", "temporada_origen", "player_id_origen"], how="left")
    m = m.merge(rd, on=["liga_destino", "temporada_destino", "player_id_destino"], how="left")
    m["cambio_rol"] = m["rol_destino_num"] - m["rol_origen_num"]
    m["rol_desconocido"] = m["cambio_rol"].isna()
    # estilos (fase 6): arquetipo del jugador en origen y distancia de estilo entre el equipo de origen y el de destino
    de = _DM / "estilos_unificados"
    j = pd.read_csv(de / "jugadores.csv.gz", dtype={"player_id": str, "team_id": str}, low_memory=False)
    j = j[j["nivel"] == "temporada"].sort_values("min", ascending=False).drop_duplicates(["liga", "temporada", "player_id"])
    j = j[["liga", "temporada", "player_id", "estilo"]].rename(columns={
        "liga": "liga_origen", "temporada": "temporada_origen", "player_id": "player_id_origen", "estilo": "arquetipo"})
    m = m.merge(j, on=["liga_origen", "temporada_origen", "player_id_origen"], how="left")
    e = pd.read_csv(de / "equipos.csv", dtype={"team_id": str})
    e = e[e["nivel"] == "temporada"].drop_duplicates(["liga", "temporada", "team_id"]).set_index(["liga", "temporada", "team_id"])[ESTILOS_P]
    def _vec(liga, temp, team):
        k = (liga, temp, str(team))
        return e.loc[k].to_numpy(float) if isinstance(team, str) and k in e.index else None
    dist = []
    for a, b, ta, cc, d, td in zip(m["liga_origen"], m["temporada_origen"], m["team_origen"],
                                   m["liga_destino"], m["temporada_destino"], m["team_destino"]):
        va, vb = _vec(a, b, ta), _vec(cc, d, td)
        dist.append(0.5 * float(np.abs(va - vb).sum()) if va is not None and vb is not None else np.nan)
    m["distancia_estilo_equipo"] = dist            # distancia de variación total entre pertenencias (0 = mismo estilo)
    m["estilo_desconocido"] = m["distancia_estilo_equipo"].isna()
    # entrenador
    eo, ed = m["entrenador_origen"], m["entrenador_destino"]
    m["cambio_entrenador"] = np.where(eo.notna() & ed.notna(), (eo != ed).astype(float), np.nan)
    m["entrenador_desconocido"] = m["cambio_entrenador"].isna()
    # canterano / formado en el club: no hay fuente → NaN + bandera
    m["canterano"] = np.nan
    m["canterano_desconocido"] = True
    # salto de nivel (league_offsets)
    m["salto_nivel"] = [salto_nivel(norm, a, b, cc, d) for a, b, cc, d in
                        zip(m["liga_origen"], m["temporada_origen"], m["liga_destino"], m["temporada_destino"])]
    m["salto_nivel_abs"] = m["salto_nivel"].abs()
    m["direccion"] = np.select([m["salto_nivel"] > 0.15, m["salto_nivel"] < -0.15], ["sube", "baja"], "lateral")
    m["intra_temporada"] = (m["tipo"] == "intra_temporada").astype(float)
    m["adicion"] = (m["tipo"] == "adicion").astype(float)
    return m


# ================================================================================================ curva temporal
SERIES = ("pts_p100", "ts_pct", "usg_tiro", "ast_p100", "prod_p100")


def _series_partido(p: pd.DataFrame) -> pd.DataFrame:
    """Serie por partido y su exposición (la varianza del ruido de un partido ∝ 1/exposición)."""
    poss = p["poss_on"].to_numpy(float)
    tsa = (p["fga"] + 0.44 * p["fta"]).to_numpy(float)
    team = (p["team_fga_on"] + 0.44 * p["team_fta_on"]).to_numpy(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = pd.DataFrame({
            "y_pts_p100": 100 * p["pts"].to_numpy(float) / poss, "w_pts_p100": poss,
            "y_ts_pct": 100 * p["pts"].to_numpy(float) / (2 * tsa), "w_ts_pct": tsa,
            "y_usg_tiro": p["usg_tiro"].to_numpy(float), "w_usg_tiro": team,
            "y_ast_p100": 100 * p["ast"].to_numpy(float) / poss, "w_ast_p100": poss,
            "y_prod_p100": 100 * (p["pts"] + p["ast"]).to_numpy(float) / poss, "w_prod_p100": poss}, index=p.index)
    return out


def construir_series(claves: pd.DataFrame, pj: pd.DataFrame, c: dict | None = None) -> pd.DataFrame:
    """Partidos de cada etapa (claves: id, liga, temporada, player_id) en orden cronológico, con g = 1, 2, … =
    partido jugado número g en esa liga-temporada (sólo los primeros curva.partidos_max) y las series por partido.
    Partidos con < min_posesiones no aportan (exposición 0)."""
    c = c or cfg()
    cv = c["curva"]
    k = claves.rename(columns={"liga": "_l", "temporada": "_t", "player_id": "_p"})
    x = pj.merge(k, left_on=["liga", "temporada", "player_id"], right_on=["_l", "_t", "_p"])
    x = x.sort_values(["id", "fecha", "game_id"])
    x["g"] = x.groupby("id").cumcount() + 1
    x = x[x["g"] <= cv["partidos_max"]]
    s = _series_partido(x)
    poco = x["poss_on"].to_numpy(float) < cv["min_posesiones_partido"]
    for n in SERIES:
        w = s[f"w_{n}"].to_numpy(float)
        ok = np.isfinite(s[f"y_{n}"].to_numpy(float)) & np.isfinite(w) & (w > 0) & ~poco
        s[f"w_{n}"] = np.where(ok, w, 0.0)
        s[f"y_{n}"] = np.where(ok, s[f"y_{n}"], np.nan)
    return pd.concat([x[["id", "g", "orden_equipo", "fecha", "min", "poss_on"]].reset_index(drop=True),
                      s.reset_index(drop=True)], axis=1)


def rejilla_kappa(c: dict | None = None, proyeccion: bool = False) -> np.ndarray:
    """Rejilla logarítmica de κ: la de la forma de la curva o (proyeccion=True) la de la interfaz, que llega más lejos
    para poder representar un efecto que no se cierra en el horizonte."""
    cv = (c or cfg())["curva"]
    kmax = cv["kappa_max_proyeccion"] if proyeccion else cv["kappa_max"]
    return np.geomspace(cv["kappa_min"], kmax, int(cv["kappa_puntos"]) + (24 if proyeccion else 0))


def estadisticos_curva(ser: pd.DataFrame, serie: str, kappas: np.ndarray, base: dict | None = None,
                       min_partidos: int = 8) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Estadísticos suficientes por jugador del modelo dentro de jugador
        r_ig = y_ig / ȳ_i,   r_ig − 1 ≈ D·(φ_g − φ̄_i),   φ_g = exp(−g/κ),   peso = exposición del partido
    (primer orden de y_ig = A_i·(1 + D·φ_g) con A_i libre por jugador: D es el hueco relativo a la asíntota en g = 0;
    negativo = empieza por debajo). `base` (opcional, g → b(g)) divide r por la curva de los que no cambian de liga.
    Devuelve ids, S_xx[i, κ], S_xy[i, κ], S_yy[i]."""
    y, w = ser[f"y_{serie}"].to_numpy(float), ser[f"w_{serie}"].to_numpy(float)
    ok = (w > 0) & np.isfinite(y)
    d = pd.DataFrame({"id": ser["id"].to_numpy()[ok], "g": ser["g"].to_numpy(float)[ok], "y": y[ok], "w": w[ok]})
    if base is not None:
        b = d["g"].map(base).fillna(1.0).to_numpy(float)
        d["y"] = d["y"] / b
    cnt = d.groupby("id")["g"].transform("size")
    d = d[cnt >= min_partidos]
    sw = d.groupby("id")["w"].transform("sum")
    ybar = (d["w"] * d["y"]).groupby(d["id"]).transform("sum") / sw
    d = d[ybar > 0]
    sw, ybar = sw[d.index], ybar[d.index]
    r1 = (d["y"] / ybar - 1).to_numpy(float)
    ids, inv = np.unique(d["id"].to_numpy(), return_inverse=True)
    wv = d["w"].to_numpy(float)
    wv = wv / np.mean(wv)
    swn = np.bincount(inv, weights=wv)
    Sxx = np.zeros((len(ids), len(kappas)))
    Sxy = np.zeros((len(ids), len(kappas)))
    g = d["g"].to_numpy(float)
    for j, k in enumerate(kappas):
        phi = np.exp(-g / k)
        pbar = np.bincount(inv, weights=wv * phi) / swn
        xx = phi - pbar[inv]
        Sxx[:, j] = np.bincount(inv, weights=wv * xx * xx)
        Sxy[:, j] = np.bincount(inv, weights=wv * xx * r1)
    Syy = np.bincount(inv, weights=wv * r1 * r1)
    Syy = np.column_stack([Syy, np.bincount(inv)])     # 2.ª columna: partidos del jugador (para σ²)
    return ids, Sxx, Sxy, Syy


def ajustar_kappa(Sxx: np.ndarray, Sxy: np.ndarray, Syy: np.ndarray, kappas: np.ndarray,
                  pesos: np.ndarray | None = None, previa: dict | None = None) -> dict:
    """Máximo a posteriori en (κ, D) con D común al grupo. Verosimilitud gaussiana dentro de jugador:
        SSE(κ, D) = ΣS_yy − 2·D·ΣS_xy + D²·ΣS_xx,   σ² = ΣS_yy / Σ partidos
    y previas log κ ~ N(log κ0, s_κ²), D ~ N(0, s_D²) (configs/adaptacion.yaml → curva.previa_*): con datos que no
    distinguen la forma (perfil plano en κ) la previa decide y el intervalo lo refleja. Para cada κ de la rejilla,
    D̂(κ) = ΣS_xy/(ΣS_xx + σ²/s_D²); se elige el κ de menor objetivo (refinado con una parábola en log κ)."""
    p = np.ones(len(Syy)) if pesos is None else np.asarray(pesos, float)
    Syy = np.asarray(Syy, float)
    syy_i, n_i = (Syy[:, 0], Syy[:, 1]) if Syy.ndim == 2 else (Syy, np.ones(len(Syy)))
    sxx, sxy, syy = (p[:, None] * Sxx).sum(0), (p[:, None] * Sxy).sum(0), float((p * syy_i).sum())
    s2 = syy / max(float((p * n_i).sum()), 1.0)
    pr = previa if previa is not None else cfg()["curva"]
    k0, sk, sD = float(pr.get("previa_kappa", 5.0)), float(pr.get("previa_log_kappa_sd", 1.0)), float(pr.get("previa_D_sd", 0.15))
    with np.errstate(divide="ignore", invalid="ignore"):
        D = sxy / (sxx + s2 / sD ** 2)
        sse = syy - 2 * D * sxy + D ** 2 * sxx
        obj = sse / (2 * s2) + D ** 2 / (2 * sD ** 2) + (np.log(kappas) - np.log(k0)) ** 2 / (2 * sk ** 2)
    sse = obj
    j = int(np.nanargmin(sse))
    lk = np.log(kappas)
    kap = kappas[j]
    if 0 < j < len(kappas) - 1:
        y0, y1, y2 = sse[j - 1], sse[j], sse[j + 1]
        den = (y0 - 2 * y1 + y2)
        if den > 0:
            h = lk[j + 1] - lk[j]
            kap = float(np.exp(lk[j] + 0.5 * h * (y0 - y2) / den))
    Dk = float(np.interp(np.log(kap), lk, D))
    return {"kappa": float(kap), "D": Dk, "objetivo": float(sse[j]), "borde": j in (0, len(kappas) - 1),
            "sigma2": float(s2), "D_por_kappa": D, "objetivo_por_kappa": sse,
            "hueco_g1": Dk * float(np.exp(-1 / kap)), "hueco_medio_1_5": Dk * float(np.mean(np.exp(-np.arange(1, 6) / kap)))}


def bootstrap_curva(Sxx, Sxy, Syy, kappas, pesos=None, B: int = 200, semilla: int = 0, previa: dict | None = None) -> dict:
    """Intervalos de κ, D y partidos al 50 % / 90 % por remuestreo de jugadores (semilla fija)."""
    rng = np.random.default_rng(semilla)
    n = len(Syy)
    p = np.ones(n) if pesos is None else np.asarray(pesos, float)
    ks, Ds = [], []
    for _ in range(B):
        i = rng.integers(0, n, n)
        r = ajustar_kappa(Sxx[i], Sxy[i], Syy[i], kappas, p[i], previa)
        ks.append(r["kappa"])
        Ds.append(r["D"])
    ks, Ds = np.array(ks), np.array(Ds)
    q = lambda v, a: float(np.nanquantile(v, a))  # noqa: E731
    h15 = Ds * np.array([np.mean(np.exp(-np.arange(1, 6) / k)) for k in ks])
    return {"kappa_sd": float(np.nanstd(ks)), "kappa_lo": q(ks, 0.05), "kappa_hi": q(ks, 0.95),
            "h15_lo": q(h15, 0.05), "h15_hi": q(h15, 0.95),
            "kappa_med": q(ks, 0.5), "D_sd": float(np.nanstd(Ds)), "D_lo": q(Ds, 0.05), "D_hi": q(Ds, 0.95),
            "p_D_negativo": float(np.mean(Ds < 0)), "g50_lo": q(ks * np.log(2), 0.05), "g50_hi": q(ks * np.log(2), 0.95),
            "g90_lo": q(ks * np.log(10), 0.05), "g90_hi": q(ks * np.log(10), 0.95), "_ks": ks, "_Ds": Ds}


def curva_base(ser: pd.DataFrame, serie: str, min_partidos: int = 8) -> dict:
    """Curva media b(g) (cociente partido/media propia) de los jugadores que siguen en su equipo: el «arranque de
    temporada» común a todos. Media ponderada por exposición, suavizada con una media móvil de 5 partidos."""
    y, w = ser[f"y_{serie}"].to_numpy(float), ser[f"w_{serie}"].to_numpy(float)
    ok = (w > 0) & np.isfinite(y)
    d = pd.DataFrame({"id": ser["id"].to_numpy()[ok], "g": ser["g"].to_numpy()[ok], "y": y[ok], "w": w[ok]})
    d = d[d.groupby("id")["g"].transform("size") >= min_partidos]
    ybar = (d["w"] * d["y"]).groupby(d["id"]).transform("sum") / d.groupby("id")["w"].transform("sum")
    d["r"] = d["y"] / ybar
    b = d.groupby("g").apply(lambda x: np.average(x["r"], weights=x["w"]), include_groups=False)
    b = b.rolling(5, center=True, min_periods=1).mean()
    return {int(k): float(v) for k, v in b.items()}


def claves_permanecen(tem_e: pd.DataFrame, c: dict | None = None) -> pd.DataFrame:
    """Grupo de control: personas que siguen en la misma liga y el mismo equipo (id o nombre del equipo; los ids FEB
    cambian cada temporada) de t−1 a t con ≥ min_minutos_observado en las dos."""
    c = c or cfg()
    mn = c["censura"]["min_minutos_observado"]
    t = tem_e[(tem_e["min"] >= mn) & tem_e["persona_id"].notna()][["persona_id", "liga", "anio", "temporada", "player_id",
                                                                   "team_pj", "equipo"]]
    a = t.merge(t.assign(anio=t["anio"] + 1), on=["persona_id", "liga", "anio"], suffixes=("", "_prev"))
    mismo = (a["team_pj"].astype(str) == a["team_pj_prev"].astype(str)) | (a["equipo"].astype(str) == a["equipo_prev"].astype(str))
    a = a[mismo].drop_duplicates(["persona_id", "liga", "temporada"])
    return pd.DataFrame({"id": "S:" + a["persona_id"].astype(str) + ":" + a["liga"] + ":" + a["temporada"],
                         "liga": a["liga"], "temporada": a["temporada"], "player_id": a["player_id"]})


# ================================================================================================ modelo jerárquico
def matriz_diseno(m: pd.DataFrame, c: dict | None = None, columnas: list[str] | None = None) -> tuple[np.ndarray, list[str]]:
    """Matriz de efectos fijos: intercepto, categóricas (con referencia), continuas (NaN → 0) y banderas.
    `columnas` fija el orden (para predecir con un modelo ya ajustado; las columnas que falten valen 0)."""
    c = c or cfg()
    mc = c["modelo"]
    d = pd.DataFrame(index=m.index)
    d["intercepto"] = 1.0
    for var, ref in mc["categoricas"].items():
        v = m[var].astype(object).where(m[var].notna(), "desconocido").astype(str) if var in m else pd.Series("desconocido", index=m.index)
        for nivel in sorted(set(v) - {ref}):
            d[f"{var}={nivel}"] = (v == nivel).astype(float)
    e = (pd.to_numeric(m.get("edad"), errors="coerce") - mc["edad_centro"]) / mc["edad_escala"]
    cont = {"edad_c": e, "edad_c2": e ** 2,
            "rol_origen_c": pd.to_numeric(m.get("rol_origen_num"), errors="coerce") - 2,
            "cambio_rol": pd.to_numeric(m.get("cambio_rol"), errors="coerce"),
            "salto_nivel": pd.to_numeric(m.get("salto_nivel"), errors="coerce"),
            "salto_nivel_abs": pd.to_numeric(m.get("salto_nivel_abs"), errors="coerce"),
            "distancia_estilo_c": pd.to_numeric(m.get("distancia_estilo_equipo"), errors="coerce") - 0.65,
            "cambio_entrenador": pd.to_numeric(m.get("cambio_entrenador"), errors="coerce")}
    for k in mc["continuas"]:
        d[k] = cont[k].fillna(0.0).astype(float)
    for k in mc["banderas"]:
        d[k] = m[k].astype(float).fillna(0.0) if k in m else 0.0
    if columnas is not None:
        d = d.reindex(columns=columnas, fill_value=0.0)
    return d.to_numpy(float), list(d.columns)


def gibbs_jerarquico(y, X, w, g1, g2, n_g1: int, n_g2: int, iteraciones: int = 3000, calentamiento: int = 1000,
                     semilla: int = 0, prior_beta_sd: float = 1.0, a0: float = 1.0, b0: float = 0.001,
                     tau2_min: float = 1e-5, adelgazar: int = 1) -> dict:
    """Muestreador de Gibbs del modelo gaussiano jerárquico
        y_i = X_i·β + u_{g1(i)} + v_{g2(i)} + ε_i,   ε_i ~ N(0, σ²/w_i)
        β ~ N(0, s²·I),  u_j ~ N(0, τ_u²) (pareja origen→destino),  v_k ~ N(0, τ_v²) (escalón de destino),
        σ², τ_u², τ_v² ~ IG(a0, b0).
    Condicionales conjugadas (normal / gamma inversa). w = pesos de precisión (exposición × IPCW, media 1).
    Devuelve las muestras posteriores (tras el calentamiento)."""
    rng = np.random.default_rng(semilla)
    y, X, w = np.asarray(y, float), np.asarray(X, float), np.asarray(w, float)
    n, p = X.shape
    XtWX = X.T @ (X * w[:, None])
    u, v = np.zeros(n_g1), np.zeros(n_g2)
    beta = np.linalg.lstsq(X * np.sqrt(w)[:, None], y * np.sqrt(w), rcond=None)[0]
    s2, tu, tv = float(np.average((y - X @ beta) ** 2, weights=w)), 0.01, 0.01
    sw1, sw2 = np.bincount(g1, weights=w, minlength=n_g1), np.bincount(g2, weights=w, minlength=n_g2)
    keep = []
    for it in range(iteraciones):
        # β
        r = y - u[g1] - v[g2]
        P = XtWX / s2 + np.eye(p) / prior_beta_sd ** 2
        L = np.linalg.cholesky(P)
        mu = np.linalg.solve(P, X.T @ (w * r) / s2)
        beta = mu + np.linalg.solve(L.T, rng.standard_normal(p))
        xb = X @ beta
        # u (pareja)
        r = y - xb - v[g2]
        prec = sw1 / s2 + 1 / tu
        u = np.bincount(g1, weights=w * r, minlength=n_g1) / s2 / prec + rng.standard_normal(n_g1) / np.sqrt(prec)
        # v (escalón)
        r = y - xb - u[g1]
        prec = sw2 / s2 + 1 / tv
        v = np.bincount(g2, weights=w * r, minlength=n_g2) / s2 / prec + rng.standard_normal(n_g2) / np.sqrt(prec)
        # varianzas
        e = y - xb - u[g1] - v[g2]
        s2 = 1 / rng.gamma(a0 + n / 2, 1 / (b0 + 0.5 * float(np.sum(w * e * e))))
        tu = max(1 / rng.gamma(a0 + n_g1 / 2, 1 / (b0 + 0.5 * float(u @ u))), tau2_min)
        tv = max(1 / rng.gamma(a0 + n_g2 / 2, 1 / (b0 + 0.5 * float(v @ v))), tau2_min)
        if it >= calentamiento and (it - calentamiento) % adelgazar == 0:
            keep.append((beta.copy(), u.copy(), v.copy(), s2, tu, tv))
    return {"beta": np.array([k[0] for k in keep]), "u": np.array([k[1] for k in keep]),
            "v": np.array([k[2] for k in keep]), "sigma2": np.array([k[3] for k in keep]),
            "tau2_u": np.array([k[4] for k in keep]), "tau2_v": np.array([k[5] for k in keep])}


def rhat(cadenas: list[np.ndarray]) -> np.ndarray:
    """R̂ de Gelman-Rubin (cadenas × muestras × parámetros)."""
    x = np.stack(cadenas)                      # (m, n, p)
    m_, n_ = x.shape[0], x.shape[1]
    B = n_ * x.mean(1).var(0, ddof=1)
    W = x.var(1, ddof=1).mean(0)
    return np.sqrt(((n_ - 1) / n_ * W + B / n_) / np.where(W > 0, W, np.nan))


class ModeloDelta:
    """Ajuste y predicción del modelo jerárquico de Δ para una métrica (respuesta: log-cociente y/ŷ, o ΔL aditivo)."""

    def __init__(self, c: dict | None = None):
        self.c = c or cfg()

    def ajustar(self, m: pd.DataFrame, respuesta: str, pesos: np.ndarray, semilla: int = 0, cadenas: int | None = None,
                iteraciones: int | None = None, calentamiento: int | None = None) -> "ModeloDelta":
        mc = self.c["modelo"]
        ok = np.isfinite(m[respuesta].to_numpy(float)) & np.isfinite(pesos) & (pesos > 0)
        d = m[ok]
        self.n = int(ok.sum())
        X, self.cols = matriz_diseno(d, self.c)
        # columnas sin variación (categorías ausentes) fuera: no son identificables
        var = X.std(0) > 0
        var[0] = True
        self.cols = [k for k, s in zip(self.cols, var) if s]
        X = X[:, var]
        self.pares = sorted(set(d["liga_origen"] + ">" + d["liga_destino"]))
        self.escalones = sorted(set(d["escalon_destino"].astype(str)))
        ip = {k: i for i, k in enumerate(self.pares)}
        ie = {k: i for i, k in enumerate(self.escalones)}
        g1 = (d["liga_origen"] + ">" + d["liga_destino"]).map(ip).to_numpy(int)
        g2 = d["escalon_destino"].astype(str).map(ie).to_numpy(int)
        self.peso_medio = float(np.mean(pesos[ok]))
        w = pesos[ok] / self.peso_medio
        it = iteraciones or mc["gibbs_iteraciones"]
        cal = calentamiento or mc["gibbs_calentamiento"]
        res = []
        for k in range(cadenas or mc["gibbs_cadenas"]):
            res.append(gibbs_jerarquico(d[respuesta].to_numpy(float), X, w, g1, g2, len(self.pares), len(self.escalones),
                                        it, cal, semilla + 1000 * k, mc["prior_beta_sd"], mc["prior_tau_a"],
                                        mc["prior_tau_b"], mc["tau2_minimo"]))
        self.rhat_max = float(np.nanmax(rhat([r["beta"] for r in res]))) if len(res) > 1 else np.nan
        self.post = {k: np.concatenate([r[k] for r in res]) for k in res[0]}
        return self

    def eta(self, m: pd.DataFrame) -> np.ndarray:
        """Muestras del predictor lineal (muestras × filas): X·β + u_pareja + v_escalón (0 si la pareja o el escalón
        no se vieron en el ajuste: su efecto se integra con la previa, es decir, media 0 y varianza τ²)."""
        X, _ = matriz_diseno(m, self.c, self.cols)
        e = self.post["beta"] @ X.T
        ip = {k: i for i, k in enumerate(self.pares)}
        ie = {k: i for i, k in enumerate(self.escalones)}
        g1 = (m["liga_origen"] + ">" + m["liga_destino"]).map(ip)
        g2 = m["escalon_destino"].astype(str).map(ie)
        rng = np.random.default_rng(0)
        S = e.shape[0]
        for gi, U, T in ((g1, self.post["u"], self.post["tau2_u"]), (g2, self.post["v"], self.post["tau2_v"])):
            vis = gi.notna().to_numpy()
            if vis.any():
                e[:, vis] += U[:, gi[vis].astype(int).to_numpy()]
            if (~vis).any():
                e[:, ~vis] += rng.standard_normal((S, int((~vis).sum()))) * np.sqrt(T)[:, None]
        return e

    def coeficientes(self) -> pd.DataFrame:
        b = self.post["beta"]
        return pd.DataFrame({"coeficiente": self.cols, "media": b.mean(0), "sd": b.std(0),
                             "lo90": np.quantile(b, 0.05, 0), "hi90": np.quantile(b, 0.95, 0),
                             "p_negativo": (b < 0).mean(0)})


# ================================================================================================ censura
def rendimiento_temprano(mov: pd.DataFrame, ser: pd.DataFrame, k: int) -> pd.Series:
    """log(pts/100 de los primeros k partidos en la liga nueva / ŷ pts/100): el predictor de la censura."""
    s = ser[(ser["g"] <= k) & (ser["w_pts_p100"] > 0)]
    pts = (s["y_pts_p100"] * s["w_pts_p100"] / 100).groupby(s["id"]).sum()
    pos = s.groupby("id")["w_pts_p100"].sum()
    p100 = 100 * pts / pos
    y = mov["id"].map(p100)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.log(y / mov["pts_p100_esp"])
    return r.where(np.isfinite(r))


def pesos_ipcw(mov: pd.DataFrame, observado: np.ndarray, c: dict | None = None) -> tuple[np.ndarray, dict]:
    """Probabilidad de seguir observado (llegar a min_minutos_observado en la liga nueva) por logit con las covariables
    del traspaso, el nivel de origen y el rendimiento de los primeros partidos; peso = 1/p en los observados (recorte
    por percentiles, media 1), 0 en los censurados."""
    from sklearn.linear_model import LogisticRegression
    c = c or cfg()
    X, cols = matriz_diseno(mov, c)
    extra = {
        "log_min_origen": np.log1p(mov["min_origen"].to_numpy(float)),
        "L_origen": mov["L_origen"].fillna(0).to_numpy(float),
        "temprano_logr": mov["temprano_logr"].fillna(0).to_numpy(float).clip(-2, 2),
        "temprano_desconocido": mov["temprano_logr"].isna().to_numpy(float)}
    for esc in sorted(set(mov["escalon_destino"].astype(str))):
        extra[f"escalon={esc}"] = (mov["escalon_destino"].astype(str) == esc).to_numpy(float)
    Xc = np.column_stack([X[:, 1:]] + list(extra.values()))
    nombres = cols[1:] + list(extra)
    mu, sd = Xc.mean(0), Xc.std(0)
    sd[sd == 0] = 1
    Z = (Xc - mu) / sd
    lr = LogisticRegression(C=c["censura"]["C_logit"], max_iter=2000)
    lr.fit(Z, observado.astype(int))
    p = lr.predict_proba(Z)[:, 1]
    w = np.where(observado, 1 / np.clip(p, 1e-3, 1), 0.0)
    lo, hi = np.quantile(w[observado], c["censura"]["recorte_pesos"])
    w = np.where(observado, np.clip(w, lo, hi), 0.0)
    w = np.where(observado, w / w[observado].mean(), 0.0)
    coef = dict(zip(nombres, (lr.coef_[0] / sd).round(4)))
    return w, {"p_media_observados": float(p[observado].mean()), "p_media_censurados": float(p[~observado].mean()),
               "observados": int(observado.sum()), "censurados": int((~observado).sum()),
               "coef_temprano_logr": float(coef["temprano_logr"]), "coeficientes": coef, "_p": p}


def marcar_observados(m: pd.DataFrame, c: dict | None = None) -> pd.DataFrame:
    """Bandera de censura: `observado` = no censurado (sigue jugando lo bastante en la liga nueva esa temporada);
    `en_curso` = temporada de destino sin terminar (censura administrativa, fuera del ajuste)."""
    c = c or cfg()
    ce = c["censura"]
    m = m.copy()
    dur = m["liga_destino"].map(lambda l: ce["duracion_partido"].get(l, ce["duracion_partido"]["defecto"])).astype(float)
    disp = m["partidos_equipo_destino"].astype(float) * dur
    m["min_pct_disponible"] = m["min_destino"] / disp.where(disp > 0)
    por_pct = (m["min_pct_disponible"] >= ce["min_pct_disponible"]) & (m["min_destino"] >= ce["min_minutos_absolutos"])
    por_min = m["min_destino"] >= ce["min_minutos_observado"]
    m["observado"] = np.where(m["min_pct_disponible"].notna(), por_pct, por_min)
    m["en_curso"] = m["temporada_destino"].isin(ce["temporadas_en_curso"])
    return m


def claves_series_traspasos(m: pd.DataFrame, tem: pd.DataFrame) -> pd.DataFrame:
    """Etapas por partido de cada traspaso: la temporada de destino y, si sigue en esa liga, la siguiente (g cuenta
    los partidos jugados en la liga nueva en las dos)."""
    k1 = pd.DataFrame({"id": m["id"], "liga": m["liga_destino"], "temporada": m["temporada_destino"],
                       "player_id": m["player_id_destino"]})
    sig = tem[["persona_id", "liga", "anio", "temporada", "player_id"]].drop_duplicates(["persona_id", "liga", "anio"])
    x = m[["id", "persona_id", "liga_destino", "anio_destino"]].assign(anio=m["anio_destino"] + 1)
    x = x.merge(sig, left_on=["persona_id", "liga_destino", "anio"], right_on=["persona_id", "liga", "anio"])
    k2 = x[["id", "liga", "temporada", "player_id"]]
    return pd.concat([k1, k2], ignore_index=True)


def claves_series_permanecen(tem_e: pd.DataFrame, c: dict | None = None) -> pd.DataFrame:
    """Control: temporada t de quien sigue en su equipo (claves_permanecen) y, si sigue en la liga, la t+1."""
    k1 = claves_permanecen(tem_e, c)
    k1["persona_id"] = k1["id"].str.split(":").str[1]
    k1["anio"] = k1["temporada"].str[:4].astype(int) + 1
    sig = tem_e[["persona_id", "liga", "anio", "temporada", "player_id"]].drop_duplicates(["persona_id", "liga", "anio"])
    x = k1[["id", "persona_id", "liga", "anio"]].merge(sig, on=["persona_id", "liga", "anio"])
    return pd.concat([k1[["id", "liga", "temporada", "player_id"]], x[["id", "liga", "temporada", "player_id"]]],
                     ignore_index=True)


def ajustar_curvas(m: pd.DataFrame, ser: pd.DataFrame, sst: pd.DataFrame, c: dict | None = None,
                   perfiles: tuple = ("global", "grupo_nacionalidad", "direccion", "pos3", "escalon_destino")) -> tuple[pd.DataFrame, dict]:
    """κ y D por serie y perfil: movers observados (pesos IPCW), con la curva de los que siguen en su equipo como
    base (neto) y sin base (bruto); y la de los que siguen (control). Devuelve la tabla y las muestras bootstrap."""
    c = c or cfg()
    cv = c["curva"]
    K = rejilla_kappa(c)
    semilla = int(c["semilla"])
    filas, draws = [], {}
    obs = m[m["observado"] & ~m["en_curso"]]
    w_id = dict(zip(obs["id"], obs["w_ipcw"]))
    for serie in SERIES:
        b = curva_base(sst, serie, cv["min_partidos_jugador"])
        ids_s, Sxx_s, Sxy_s, Syy_s = estadisticos_curva(sst, serie, K, None, cv["min_partidos_jugador"])
        r = ajustar_kappa(Sxx_s, Sxy_s, Syy_s, K)
        bs = bootstrap_curva(Sxx_s, Sxy_s, Syy_s, K, None, cv["bootstrap"], semilla)
        filas.append(_fila_curva(serie, "control_permanecen", "global", len(ids_s), r, bs))
        sub = ser[ser["id"].isin(set(obs["id"]))]
        for modo, base in (("neto", b), ("bruto", None)):
            ids, Sxx, Sxy, Syy = estadisticos_curva(sub, serie, K, base, cv["min_partidos_jugador"])
            meta = obs.set_index("id").loc[ids]
            pw = meta["w_ipcw"].to_numpy(float)
            for perfil in perfiles:
                vals = ["global"] if perfil == "global" else sorted(meta[perfil].astype(str).unique())
                for val in vals:
                    s = np.ones(len(ids), bool) if perfil == "global" else (meta[perfil].astype(str) == val).to_numpy()
                    if s.sum() < cv["min_jugadores_grupo"]:
                        continue
                    r = ajustar_kappa(Sxx[s], Sxy[s], Syy[s], K, pw[s])
                    bs = bootstrap_curva(Sxx[s], Sxy[s], Syy[s], K, pw[s], cv["bootstrap"], semilla)
                    f = _fila_curva(serie, f"traspasos_{modo}", f"{perfil}={val}", int(s.sum()), r, bs)
                    f["partidos_1a_temporada_mediana"] = float(meta.loc[s, "partidos_destino"].median())
                    filas.append(f)
                    if modo == "neto":
                        draws[(serie, perfil, val)] = (bs["_ks"], bs["_Ds"], f["partidos_1a_temporada_mediana"])
    return pd.DataFrame(filas), draws


def _fila_curva(serie, poblacion, perfil, n, r, bs) -> dict:
    return {"serie": serie, "poblacion": poblacion, "perfil": perfil, "n_jugadores": n,
            "kappa": r["kappa"], "kappa_lo": bs["kappa_lo"], "kappa_hi": bs["kappa_hi"], "kappa_en_borde": r["borde"],
            "D": r["D"], "D_lo": bs["D_lo"], "D_hi": bs["D_hi"], "p_D_negativo": bs["p_D_negativo"],
            "hueco_medio_partidos_1_5": r["hueco_medio_1_5"], "hueco_1_5_lo": bs["h15_lo"], "hueco_1_5_hi": bs["h15_hi"],
            "partidos_50": r["kappa"] * np.log(2), "partidos_50_lo": bs["g50_lo"], "partidos_50_hi": bs["g50_hi"],
            "partidos_90": r["kappa"] * np.log(10), "partidos_90_lo": bs["g90_lo"], "partidos_90_hi": bs["g90_hi"]}


# ================================================================================================ estimación
def respuesta(metrica: str) -> str:
    """Columna respuesta del modelo: log-cociente y/ŷ (relativas y L_rel) o ΔL aditivo (L)."""
    return {"L": "L_delta", "L_rel": "L_logr"}.get(metrica, f"{metrica}_logr")


def es_aditiva(metrica: str) -> bool:
    return metrica == "L"


def pesos_precision(m: pd.DataFrame, c: dict | None = None) -> np.ndarray:
    """Peso de precisión de cada traspaso: min/(min + ref) (el ruido de muestreo de la temporada baja con los minutos)."""
    ref = (c or cfg())["modelo"]["peso_minutos_ref"]
    mn = m["min_destino"].to_numpy(float)
    return mn / (mn + ref)


def ajustar_modelos(m: pd.DataFrame, metricas: list[str], c: dict | None = None, ipcw: bool = True,
                    excluir: tuple = (), cadenas: int | None = None, iteraciones: int | None = None,
                    calentamiento: int | None = None, semilla: int | None = None) -> dict:
    """Un ModeloDelta por métrica sobre los traspasos observados (no censurados) de temporadas cerradas.
    excluir: covariables continuas o banderas que se quitan (análisis de robustez)."""
    c = c or cfg()
    if excluir:
        c = {**c, "modelo": {**c["modelo"], "continuas": [k for k in c["modelo"]["continuas"] if k not in excluir],
                             "banderas": [k for k in c["modelo"]["banderas"] if k not in excluir]}}
    d = m[m["observado"] & ~m["en_curso"]]
    w = pesos_precision(d, c) * (d["w_ipcw"].to_numpy(float) if ipcw else 1.0)
    out = {}
    for k, met in enumerate(metricas):
        out[met] = ModeloDelta(c).ajustar(d, respuesta(met), w, semilla=(semilla if semilla is not None else c["semilla"]) + k,
                                          cadenas=cadenas, iteraciones=iteraciones, calentamiento=calentamiento)
    return out


def efecto_relativo(eta: np.ndarray, metrica: str) -> np.ndarray:
    """Δ en la escala de la tabla: relativo exp(η) − 1, o aditivo (L)."""
    return eta if es_aditiva(metrica) else np.expm1(eta)


def media_ponderada_muestras(eta: np.ndarray, w: np.ndarray, metrica: str) -> np.ndarray:
    """Muestras de la media (ponderada por IPCW) de Δ sobre un conjunto de traspasos."""
    e = efecto_relativo(eta, metrica)
    return (e * w[None, :]).sum(1) / w.sum()


# ------------------------------------------------------------------------------------------- proyección a la interfaz
def proyectar_interfaz(delta_temp: np.ndarray, D: np.ndarray, kappa_forma: np.ndarray, n1: float, horizonte: int,
                       kappas: np.ndarray, aditiva: bool = False, k_L: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Lleva la trayectoria estimada a la forma de la interfaz f(g) = 1 + δ·exp(−g/κ) (o L̂ + δ·exp(−g/κ)).

    Trayectoria relativa a ŷ en el partido g (por muestra):
        T(g) = (1 + Δ_temp) · (1 + D·φ_g) / (1 + D·w̄),   φ_g = exp(−g/κ_forma),  w̄ = media de φ en g = 1..n1
    (su media en la primera temporada es 1 + Δ_temp; D = hueco transitorio frente a su asíntota). Aditiva (L):
        T(g) = Δ_temp + k_L·D·(φ_g − w̄).
    (δ, κ) = mínimos cuadrados de T(g) − 1 (o T(g)) sobre g = 1..horizonte con δ cerrado para cada κ de la rejilla. Si
    no hay transitorio (D ≈ 0) la mejor aproximación es δ ≈ Δ_temp con κ grande (efecto persistente en el horizonte)."""
    g = np.arange(1, horizonte + 1, dtype=float)
    phi = np.exp(-g[None, :] / kappa_forma[:, None])
    n1 = max(int(round(n1)) if np.isfinite(n1) else 1, 1)
    wbar = phi[:, :min(n1, horizonte)].mean(1)
    if aditiva:
        T = delta_temp[:, None] + k_L * D[:, None] * (phi - wbar[:, None])
    else:
        T = (1 + delta_temp[:, None]) * (1 + D[:, None] * phi) / (1 + D[:, None] * wbar[:, None]) - 1
    E = np.exp(-g[None, :] / kappas[:, None])               # (K, H)
    ee = (E ** 2).sum(1)                                     # (K,)
    te = T @ E.T                                             # (S, K)
    dlt = te / ee[None, :]
    sse = (T ** 2).sum(1)[:, None] - dlt ** 2 * ee[None, :]
    j = np.argmin(sse, axis=1)
    return dlt[np.arange(len(j)), j], kappas[j]


def pendiente_L(m: pd.DataFrame) -> float:
    """k_L: unidades de L por unidad de log-cociente compuesto (pendiente de ΔL sobre log(y/ŷ) de L, por MCP)."""
    d = m[m["observado"] & ~m["en_curso"]][["L_delta", "L_logr", "min_destino"]].dropna()
    if len(d) < 30:
        return float("nan")
    w = d["min_destino"].to_numpy(float)
    x, y = d["L_logr"].to_numpy(float), d["L_delta"].to_numpy(float)
    xm, ym = np.average(x, weights=w), np.average(y, weights=w)
    return float(np.sum(w * (x - xm) * (y - ym)) / np.sum(w * (x - xm) ** 2))


def tabla_priors(m: pd.DataFrame, modelos: dict, draws_curva: dict, c: dict | None = None) -> pd.DataFrame:
    """adaptation_priors.csv: por nivel de la jerarquía y métrica, Δ de temporada (media e intervalo del 90 %), forma de
    la curva (D, κ_forma, partidos al 50/90 %) y los parámetros de la interfaz (δ, κ) con su incertidumbre."""
    c = c or cfg()
    rng = np.random.default_rng(int(c["semilla"]))
    K = rejilla_kappa(c, proyeccion=True)
    H = int(c["curva"]["horizonte_proyeccion"])
    serie_de = c["curva"]["serie_por_metrica"]
    d = m[m["observado"] & ~m["en_curso"]].reset_index(drop=True)
    d["_par"] = d["liga_origen"] + ">" + d["liga_destino"]
    w = d["w_ipcw"].to_numpy(float)
    kL = pendiente_L(m)
    niveles = {
        "celda": ["liga_origen", "liga_destino", "grupo_nacionalidad", "pos3"],
        "par_grupo": ["liga_origen", "liga_destino", "grupo_nacionalidad"],
        "par": ["liga_origen", "liga_destino"],
        "escalon_grupo": ["escalon_destino", "grupo_nacionalidad"],
        "escalon": ["escalon_destino"],
        "global_grupo": ["grupo_nacionalidad"],
        "global": []}
    filas = []
    for met, M in modelos.items():
        ok = np.isfinite(d[respuesta(met)].to_numpy(float))
        eta = M.eta(d)                                           # (S, n)
        S = eta.shape[0]
        serie = serie_de.get(met, "prod_p100")
        for nivel, claves in niveles.items():
            if not claves:
                grupos = [((), np.arange(len(d)))]
            else:
                grupos = [(k if isinstance(k, tuple) else (k,), np.asarray(v))
                          for k, v in d.groupby(claves, dropna=False).indices.items()]
            for key, idx in grupos:
                idx = idx[ok[idx]]
                if len(idx) == 0:
                    continue
                vals = dict(zip(claves, key))
                dt = media_ponderada_muestras(eta[:, idx], w[idx], met)
                gr = vals.get("grupo_nacionalidad")
                dc = draws_curva.get((serie, "grupo_nacionalidad", gr)) if gr is not None else None
                if dc is None:
                    dc = draws_curva.get((serie, "global", "global"))
                ks, Ds, _ = dc
                b = rng.integers(0, len(ks), S)
                pdv = d.loc[idx, "partidos_destino"].to_numpy(float)
                n1 = float(np.nanmedian(pdv)) if np.isfinite(pdv).any() else float("nan")
                dl, kp = proyectar_interfaz(dt, Ds[b], ks[b], n1, H, K, es_aditiva(met), kL if es_aditiva(met) else 1.0)
                fila = {"nivel": nivel, "liga_origen": vals.get("liga_origen", COMODIN),
                        "liga_destino": vals.get("liga_destino", COMODIN),
                        "grupo_nacionalidad": vals.get("grupo_nacionalidad", COMODIN), "pos3": vals.get("pos3", COMODIN),
                        "escalon_destino": vals.get("escalon_destino", escalon_de(vals["liga_destino"]) if "liga_destino" in vals else COMODIN),
                        "metrica": met, "unidad": "aditiva_L" if es_aditiva(met) else "relativa", "n": int(len(idx)),
                        "n_efectivo_ipcw": float(w[idx].sum() ** 2 / (w[idx] ** 2).sum()),
                        "delta_media": float(np.mean(dl)), "delta_sd": float(np.std(dl)),
                        "delta_lo": float(np.quantile(dl, 0.05)), "delta_hi": float(np.quantile(dl, 0.95)),
                        "kappa_media": float(np.mean(kp)), "kappa_sd": float(np.std(kp)),
                        "kappa_lo": float(np.quantile(kp, 0.05)), "kappa_hi": float(np.quantile(kp, 0.95)),
                        "delta_temporada_media": float(np.mean(dt)), "delta_temporada_sd": float(np.std(dt)),
                        "delta_temporada_lo": float(np.quantile(dt, 0.05)), "delta_temporada_hi": float(np.quantile(dt, 0.95)),
                        "p_delta_temporada_negativo": float(np.mean(dt < 0)),
                        "serie_curva": serie, "grupo_curva": gr if (gr is not None and (serie, "grupo_nacionalidad", gr) in draws_curva) else "global",
                        "D_forma_media": float(np.mean(Ds[b])), "kappa_forma_media": float(np.median(ks[b])),
                        "kappa_forma_lo": float(np.quantile(ks[b], 0.05)), "kappa_forma_hi": float(np.quantile(ks[b], 0.95)),
                        "partidos_50": float(np.median(ks[b]) * np.log(2)), "partidos_90": float(np.median(ks[b]) * np.log(10)),
                        "partidos_1a_temporada": n1}
                if nivel == "par":
                    j = M.pares.index(f"{vals['liga_origen']}>{vals['liga_destino']}") if f"{vals['liga_origen']}>{vals['liga_destino']}" in M.pares else None
                    if j is not None:
                        vu = float(np.var(M.post["u"][:, j]))
                        fila["contraccion_par"] = float(1 - vu / np.mean(M.post["tau2_u"]))   # 0 = todo previa, 1 = todo datos
                filas.append(fila)
    return pd.DataFrame(filas)


# ================================================================================================ ADAPT%
Z80 = 1.2815515655446004


def predecir_adapt(M: ModeloDelta, m: pd.DataFrame, metrica: str, c: dict | None = None) -> pd.DataFrame:
    """ADAPT% previsto para cada traspaso: 100·E[y/ŷ] (relativa; L: ΔL aditivo previsto) con intervalo creíble del 80 %
    (sólo incertidumbre del modelo) y predictivo del 80 % (más el ruido de la temporada σ²/w, para comparar con lo
    observado)."""
    eta = M.eta(m)
    # ruido de una temporada nueva: σ²·(peso medio del ajuste)/peso de precisión propio (el IPCW no es precisión)
    w = pesos_precision(m, c) / M.peso_medio
    s2 = M.post["sigma2"][:, None] / np.clip(w, 1e-3, None)[None, :]
    rng = np.random.default_rng(1)
    pred = eta + rng.standard_normal(eta.shape) * np.sqrt(s2)
    f = (lambda x: x) if es_aditiva(metrica) else (lambda x: 100 * np.exp(x))
    out = pd.DataFrame(index=m.index)
    out["pred"] = f(eta.mean(0))
    out["pred_lo"] = f(np.quantile(eta, 0.1, 0))
    out["pred_hi"] = f(np.quantile(eta, 0.9, 0))
    out["pi_lo"] = f(np.quantile(pred, 0.1, 0))
    out["pi_hi"] = f(np.quantile(pred, 0.9, 0))
    out["eta_media"] = eta.mean(0)
    out["eta_sd_pred"] = pred.std(0)
    return out


def observado_adapt(m: pd.DataFrame, metrica: str) -> pd.Series:
    """ADAPT% observado: 100·y/ŷ (L: ΔL aditivo observado)."""
    r = m[respuesta(metrica)].astype(float)
    return r if es_aditiva(metrica) else 100 * np.exp(r)


def adapt_primeros(m: pd.DataFrame, ser: pd.DataFrame, n: int) -> pd.DataFrame:
    """ADAPT% observado en los primeros n partidos en la liga nueva (sumas por partido):
    pts/100 y TS% frente a su ŷ; uso de tiro y producción como cociente de los n primeros partidos frente a su
    temporada multiplicado por el cociente de temporada (USG% y L_rel)."""
    s1 = ser[ser["g"] <= n]
    sa = ser.merge(m[["id", "partidos_destino"]], on="id")
    sa = sa[sa["g"] <= sa["partidos_destino"]]                 # sólo la primera temporada en la liga
    def tasa(d, num, den):
        return num(d).groupby(d["id"]).sum() / den(d).groupby(d["id"]).sum()
    ok = lambda d, k: d[d[f"w_{k}"] > 0]  # noqa: E731
    p_n = 100 * tasa(ok(s1, "pts_p100"), lambda d: d["y_pts_p100"] * d["w_pts_p100"] / 100, lambda d: d["w_pts_p100"])
    t_n = tasa(ok(s1, "ts_pct"), lambda d: d["y_ts_pct"] * d["w_ts_pct"], lambda d: d["w_ts_pct"])
    u_n = tasa(ok(s1, "usg_tiro"), lambda d: d["y_usg_tiro"] * d["w_usg_tiro"], lambda d: d["w_usg_tiro"])
    u_t = tasa(ok(sa, "usg_tiro"), lambda d: d["y_usg_tiro"] * d["w_usg_tiro"], lambda d: d["w_usg_tiro"])
    q_n = tasa(ok(s1, "prod_p100"), lambda d: d["y_prod_p100"] * d["w_prod_p100"], lambda d: d["w_prod_p100"])
    q_t = tasa(ok(sa, "prod_p100"), lambda d: d["y_prod_p100"] * d["w_prod_p100"], lambda d: d["w_prod_p100"])
    out = pd.DataFrame(index=m.index)
    with np.errstate(divide="ignore", invalid="ignore"):
        out["pts_p100"] = 100 * m["id"].map(p_n) / m["pts_p100_esp"]
        out["ts_pct"] = 100 * m["id"].map(t_n) / m["ts_pct_esp"]
        out["usg_pct"] = 100 * np.exp(m["usg_pct_logr"]) * m["id"].map(u_n / u_t)
        out["L_rel"] = 100 * np.exp(m["L_logr"]) * m["id"].map(q_n / q_t)
    out["partidos_disponibles"] = m["id"].map(s1.groupby("id")["g"].max())
    return out.where(np.isfinite(out))


def factor_primeros(D: float, kappa: float, n: int, n1: float) -> float:
    """Cociente medio de los primeros n partidos frente a la media de la temporada según la curva del grupo."""
    g = np.arange(1, max(int(n1) if np.isfinite(n1) else n, 1) + 1)
    phi = np.exp(-g / kappa)
    return float((1 + D * phi[:n].mean()) / (1 + D * phi.mean()))


# ================================================================================================ validación
def _sub_cfg_validacion(c: dict) -> dict:
    v = c["validacion"]
    return {"cadenas": 1, "iteraciones": v["gibbs_iteraciones"], "calentamiento": v["gibbs_calentamiento"]}


def validar_temporal(m: pd.DataFrame, metricas: list[str], c: dict | None = None,
                     casos_lf: pd.DataFrame | None = None) -> pd.DataFrame:
    """Examen sin fuga: para cada corte t, censura (IPCW) y modelo ajustados con los traspasos de destino ≤ t; predicción
    de los de destino t+1. Devuelve una fila por traspaso de prueba y métrica (previsto, intervalo, observado).
    Con casos_lf (validacion_casos.csv.gz de la normalización: ŷ ajustado sólo con ≤ t) añade el examen estricto."""
    c = c or cfg()
    filas = []
    for t in c["validacion"]["cortes"]:
        tr = m[(m["anio_destino"] <= t) & ~m["en_curso"]].copy()
        te = m[(m["anio_destino"] == t + 1) & ~m["en_curso"] & m["observado"]].copy()
        if tr.empty or te.empty:
            continue
        base = tr[np.isfinite(tr["pts_p100_esp"])]
        w, _ = pesos_ipcw(base, base["observado"].to_numpy(), c)
        tr["w_ipcw"] = 0.0
        tr.loc[base.index, "w_ipcw"] = w
        mods = ajustar_modelos(tr, metricas, c, semilla=c["semilla"] + t, **_sub_cfg_validacion(c))
        for met, M in mods.items():
            p = predecir_adapt(M, te, met, c)
            o = observado_adapt(te, met)
            f = pd.DataFrame({"corte": t, "metrica": met, "id": te["id"], "persona_id": te["persona_id"],
                              "liga_origen": te["liga_origen"], "liga_destino": te["liga_destino"],
                              "grupo_nacionalidad": te["grupo_nacionalidad"], "observado": o,
                              "previsto": p["pred"], "pi_lo": p["pi_lo"], "pi_hi": p["pi_hi"],
                              "pred_lo": p["pred_lo"], "pred_hi": p["pred_hi"], "w_ipcw_test": te["w_ipcw"]})
            filas.append(f)
    r = pd.concat(filas, ignore_index=True) if filas else pd.DataFrame()
    if casos_lf is not None and not r.empty:
        r = anadir_estricto(r, m, casos_lf)
    return r


def anadir_estricto(r: pd.DataFrame, m: pd.DataFrame, casos: pd.DataFrame) -> pd.DataFrame:
    """Examen estricto: ŷ de la normalización ajustada sólo con temporadas ≤ t (validacion_casos de la fase 2).
    error_base = |log(real/ŷ_lf)|, error_adapt = |log(real/(ŷ_lf·ADAPT%/100))| (L_rel: media geométrica de sus 8)."""
    niv = nivel_metricas()
    cs = casos.copy()
    cs["persona_id"] = cs["persona_id"].astype(str)
    piv_r = cs.pivot_table(index=["anio", "persona_id", "liga_o", "liga_d"], columns="metrica", values="real")
    piv_a = cs.pivot_table(index=["anio", "persona_id", "liga_o", "liga_d"], columns="metrica", values="amortiguado")
    lr = np.log(piv_r / piv_a)
    if {"oreb_p100", "dreb_p100"} <= set(piv_r.columns):
        lr["reb_p100"] = np.log((piv_r["oreb_p100"] + piv_r["dreb_p100"]) / (piv_a["oreb_p100"] + piv_a["dreb_p100"]))
    comp = pd.concat([sg * lr[k] for k, sg in niv.items() if k in lr], axis=1)
    lr["L_rel"] = comp.mean(1).where(comp.notna().sum(1) >= 5)
    lr = lr.reset_index()
    lr["anio_destino"] = lr["anio"] + 1
    k = m[["id", "persona_id", "liga_origen", "liga_destino", "anio_destino"]].merge(
        lr, left_on=["persona_id", "liga_origen", "liga_destino", "anio_destino"],
        right_on=["persona_id", "liga_o", "liga_d", "anio_destino"])
    k = k.set_index("id")
    r = r.copy()
    vals = []
    for met, idv in zip(r["metrica"], r["id"]):
        vals.append(k.at[idv, met] if (idv in k.index and met in k.columns and not es_aditiva(met)) else np.nan)
    r["logr_estricto"] = np.array(vals, float)
    return r


def resumir_validacion(r: pd.DataFrame, clave: list[str]) -> pd.DataFrame:
    """MAE del log-cociente (o de ΔL) previsto frente a no corregir (ADAPT% = 100 / ΔL = 0), cobertura del 80 %."""
    def f(g):
        ad = (g.name[0] if isinstance(g.name, tuple) else g.name) == "L"     # clave[0] = metrica
        o = g["observado"] if ad else np.log(g["observado"] / 100)
        p = g["previsto"] if ad else np.log(g["previsto"] / 100)
        out = {"n": len(g), "mae_sin_adaptacion": float(np.mean(np.abs(o))), "mae_adapt": float(np.mean(np.abs(o - p))),
               "sesgo_sin": float(np.mean(o)), "sesgo_adapt": float(np.mean(o - p)),
               "cobertura_80": float(np.mean((g["observado"] >= g["pi_lo"]) & (g["observado"] <= g["pi_hi"]))),
               "corr_prev_obs": float(np.corrcoef(p, o)[0, 1]) if len(g) > 2 else np.nan}
        out["mejora_mae_pct"] = 100 * (out["mae_adapt"] / out["mae_sin_adaptacion"] - 1)
        out.update({"n_estricto": 0, "mae_estricto_sin": np.nan, "mae_estricto_adapt": np.nan, "mejora_estricto_pct": np.nan})
        if "logr_estricto" in g and g["logr_estricto"].notna().sum() >= 10:
            h = g[g["logr_estricto"].notna()]
            ph = np.log(h["previsto"] / 100)
            out.update({"n_estricto": len(h), "mae_estricto_sin": float(np.mean(np.abs(h["logr_estricto"]))),
                        "mae_estricto_adapt": float(np.mean(np.abs(h["logr_estricto"] - ph)))})
            out["mejora_estricto_pct"] = 100 * (out["mae_estricto_adapt"] / out["mae_estricto_sin"] - 1)
        return pd.Series(out)
    r = r[np.isfinite(r["observado"]) & np.isfinite(r["previsto"])]
    return r.groupby(clave).apply(f, include_groups=False).reset_index()


def validar_lolo(m: pd.DataFrame, metricas: list[str], c: dict | None = None) -> pd.DataFrame:
    """Dejar fuera una liga: se quitan TODOS los traspasos que la tocan (origen o destino) y se predicen los que llegan a
    ella (su pareja y, si es la única de su escalón, también el escalón salen de la previa)."""
    c = c or cfg()
    filas = []
    for liga in sorted(m["liga_destino"].unique()):
        tr = m[(m["liga_origen"] != liga) & (m["liga_destino"] != liga) & ~m["en_curso"]].copy()
        te = m[(m["liga_destino"] == liga) & m["observado"] & ~m["en_curso"]]
        if te.empty:
            continue
        base = tr[np.isfinite(tr["pts_p100_esp"])]
        w, _ = pesos_ipcw(base, base["observado"].to_numpy(), c)
        tr["w_ipcw"] = 0.0
        tr.loc[base.index, "w_ipcw"] = w
        mods = ajustar_modelos(tr, metricas, c, semilla=c["semilla"] + 7, **_sub_cfg_validacion(c))
        for met, M in mods.items():
            p = predecir_adapt(M, te, met, c)
            filas.append(pd.DataFrame({"liga_fuera": liga, "metrica": met, "id": te["id"],
                                       "observado": observado_adapt(te, met), "previsto": p["pred"],
                                       "pi_lo": p["pi_lo"], "pi_hi": p["pi_hi"]}))
    return pd.concat(filas, ignore_index=True) if filas else pd.DataFrame()


def calibracion(r: pd.DataFrame, bins: int, muestra: str) -> pd.DataFrame:
    """Datos del gráfico de calibración: deciles de ADAPT% previsto → media prevista y observada (media geométrica;
    L: aritmética) con intervalo bootstrap del 90 % de la observada."""
    rng = np.random.default_rng(3)
    filas = []
    for met, g in r[np.isfinite(r["observado"]) & np.isfinite(r["previsto"])].groupby("metrica"):
        ad = met == "L"
        o = g["observado"].to_numpy(float) if ad else np.log(g["observado"].to_numpy(float) / 100)
        p = g["previsto"].to_numpy(float) if ad else np.log(g["previsto"].to_numpy(float) / 100)
        q = pd.qcut(p, min(bins, max(len(np.unique(p)) - 1, 1)), labels=False, duplicates="drop")
        for b in np.unique(q):
            s = q == b
            bo = [np.mean(rng.choice(o[s], s.sum())) for _ in range(200)]
            tr = (lambda x: x) if ad else (lambda x: 100 * np.exp(x))
            filas.append({"muestra": muestra, "metrica": met, "bin": int(b), "n": int(s.sum()),
                          "previsto_medio": float(tr(np.mean(p[s]))), "observado_medio": float(tr(np.mean(o[s]))),
                          "observado_lo": float(tr(np.quantile(bo, 0.05))), "observado_hi": float(tr(np.quantile(bo, 0.95))),
                          "cobertura_80": float(np.mean((g["observado"].to_numpy()[s] >= g["pi_lo"].to_numpy()[s]) &
                                                        (g["observado"].to_numpy()[s] <= g["pi_hi"].to_numpy()[s])))})
    return pd.DataFrame(filas)


# ================================================================================================ supervivencia
def segunda_temporada(m: pd.DataFrame, tem: pd.DataFrame, norm: dict, c: dict | None = None) -> pd.DataFrame:
    """Adaptación entre temporadas: para los traspasos observados cuya temporada siguiente está cerrada, si siguen en la
    liga de destino (observados también en t+1) se mide Δ₂ = log(y₂/ŷ₂) con ŷ₂ = origen traducido a t+1 (deriva de un
    año más) y la ganancia Δ₂ − Δ₁. Seguir es selectivo (quien rinde, sigue): pesos IPCW de seguir con Δ₁ y
    covariables. Devuelve una fila por traspaso (sigue, Δ₁, Δ₂, ganancia, peso)."""
    from sklearn.linear_model import LogisticRegression
    c = c or cfg()
    ce = c["censura"]
    curso = set(ce["temporadas_en_curso"])
    d = m[m["observado"] & ~m["en_curso"]].copy()
    d["temporada_sig"] = (d["anio_destino"] + 1).astype(str) + "-" + (d["anio_destino"] + 2).astype(str).str[-2:]
    d = d[~d["temporada_sig"].isin(curso) & d["temporada_sig"].isin(set(tem["temporada"]))]
    t = tem.set_index(["persona_id", "liga", "temporada"])
    o = tem.set_index(["liga", "temporada", "player_id"])
    filas = []
    for r in d.itertuples(index=False):
        k = (r.persona_id, r.liga_destino, r.temporada_sig)
        f = {"id": r.id, "sigue": False, "d1_pts": r.pts_p100_logr, "d1_L": r.L_logr}
        if k in t.index:
            x2 = t.loc[k]
            x2 = x2.iloc[0] if isinstance(x2, pd.DataFrame) else x2
            if x2["min"] >= ce["min_minutos_observado"]:
                xo = o.loc[(r.liga_origen, r.temporada_origen, r.player_id_origen)]
                xo = xo.iloc[0] if isinstance(xo, pd.DataFrame) else xo
                f["sigue"] = True
                lr = []
                for mm, sg in nivel_metricas().items():
                    yh = esperado_en_destino(xo.get(f"{mm}_th", np.nan), xo.get(f"{mm}_th_sd", np.nan), r.liga_destino,
                                             r.temporada_sig, r.pos3, mm, norm, int(r.anio_destino + 1 - r.anio_origen), r.edad)[0]
                    y2 = x2.get(f"{mm}_obs", np.nan)
                    v = np.log(y2 / yh) if (np.isfinite(yh) and np.isfinite(y2) and yh > 0 and y2 > 0) else np.nan
                    if mm == "pts_p100":
                        f["d2_pts"] = v
                    if np.isfinite(v):
                        lr.append(sg * v)
                f["d2_L"] = float(np.mean(lr)) if len(lr) >= 5 else np.nan
        filas.append(f)
    s = pd.DataFrame(filas)
    if s.empty:
        return s
    s = s.merge(d[["id", "grupo_nacionalidad", "direccion", "escalon_destino", "edad", "pos3", "rol_origen_num",
                   "cambio_rol"]], on="id")
    X = np.column_stack([s["d1_L"].fillna(0), s["d1_L"].isna(), pd.to_numeric(s["edad"], errors="coerce").fillna(27),
                         s["rol_origen_num"].fillna(2), s["cambio_rol"].fillna(0)] +
                        [(s["grupo_nacionalidad"] == g).to_numpy(float) for g in sorted(s["grupo_nacionalidad"].unique())] +
                        [(s["escalon_destino"] == g).to_numpy(float) for g in sorted(s["escalon_destino"].astype(str).unique())])
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1
    lr_ = LogisticRegression(C=ce["C_logit"], max_iter=2000).fit((X - mu) / sd, s["sigue"].astype(int))
    p = lr_.predict_proba((X - mu) / sd)[:, 1]
    w = np.where(s["sigue"], 1 / np.clip(p, 1e-3, 1), 0.0)
    if s["sigue"].any():
        lo, hi = np.quantile(w[s["sigue"]], ce["recorte_pesos"])
        w = np.where(s["sigue"], np.clip(w, lo, hi), 0.0)
    s["w_sigue"] = w
    s["ganancia_pts"] = s.get("d2_pts", np.nan) - s["d1_pts"]
    s["ganancia_L"] = s.get("d2_L", np.nan) - s["d1_L"]
    return s


def resumir_segunda(s: pd.DataFrame, por: str, B: int = 500, semilla: int = 0) -> pd.DataFrame:
    """Ganancia media de la 2.ª temporada (log-cociente compuesto L_rel y pts/100), con y sin IPCW, e intervalo
    bootstrap del 90 %."""
    rng = np.random.default_rng(semilla)
    filas = []
    grupos = [("global", s)] if por == "global" else list(s.groupby(por))
    for k, g in grupos:
        h = g[g["sigue"] & g["ganancia_L"].notna()]
        if len(h) < 10:
            continue
        x, w = h["ganancia_L"].to_numpy(float), h["w_sigue"].to_numpy(float)
        bs = []
        for _ in range(B):
            i = rng.integers(0, len(h), len(h))
            bs.append(np.average(x[i], weights=w[i]))
        filas.append({"perfil": f"{por}={k}", "n_llegadas": len(g), "n_siguen": len(h), "pct_siguen": len(h) / len(g),
                      "ganancia_L_rel_sin_ipcw": float(np.mean(x)), "ganancia_L_rel_ipcw": float(np.average(x, weights=w)),
                      "lo90": float(np.quantile(bs, 0.05)), "hi90": float(np.quantile(bs, 0.95)),
                      "ganancia_pts_ipcw": float(np.average(h["ganancia_pts"].fillna(0), weights=w)),
                      "d1_L_rel_siguen": float(np.mean(h["d1_L"])), "d1_L_rel_no_siguen": float(g.loc[~g["sigue"], "d1_L"].mean())})
    return pd.DataFrame(filas)


def supervivencia(m: pd.DataFrame, por: str = "grupo_nacionalidad", marcas=(5, 10, 20, 30)) -> pd.DataFrame:
    """Fracción de llegadas (temporadas cerradas) que alcanza g partidos en la liga nueva, fracción no censurada y
    rendimiento de los primeros partidos de censurados frente a observados (lo que corrige el IPCW)."""
    d = m[~m["en_curso"] & np.isfinite(m["pts_p100_esp"])]
    filas = []
    for k, g in [("global", d)] + list(d.groupby(por)):
        f = {"perfil": f"{por}={k}" if k != "global" else "global", "llegadas": len(g),
             "pct_observado": float(g["observado"].mean()),
             "temprano_logr_observados": float(g.loc[g["observado"], "temprano_logr"].mean()),
             "temprano_logr_censurados": float(g.loc[~g["observado"], "temprano_logr"].mean())}
        for mk in marcas:
            f[f"pct_llega_{mk}_partidos"] = float((g["partidos_destino"] >= mk).mean())
        filas.append(f)
    return pd.DataFrame(filas)


# ================================================================================================ orquestación
def _huella_cfg() -> str:
    import hashlib
    from .config import DIR_CONFIGS
    t = (DIR_CONFIGS / "adaptacion.yaml").read_bytes() + (DIR_CONFIGS / "normalization.yaml").read_bytes()
    return hashlib.sha1(t).hexdigest()[:10]


def _paso(nombre: str, fn, rehacer: bool = False, huella: bool = True):
    """Paso reanudable: el resultado se guarda en experimentos/cache_adaptacion/<nombre>[_<huella>].pkl."""
    import pickle
    DIR_CACHE.mkdir(parents=True, exist_ok=True)
    p = DIR_CACHE / (f"{nombre}_{_huella_cfg()}.pkl" if huella else f"{nombre}.pkl")
    if p.exists() and not rehacer:
        with open(p, "rb") as f:
            return pickle.load(f)
    t0 = __import__("time").time()
    r = fn()
    tmp = p.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        pickle.dump(r, f, protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(p)
    print(f"  [{nombre}] {__import__('time').time() - t0:.0f} s", flush=True)
    return r


def preparar(rehacer: bool = False) -> dict:
    """Datos, traspasos, esperado, covariables, censura y series por partido (pasos 1-2 y 4 de la fase 7)."""
    c = cfg()

    def _datos():
        tem = cargar_temporadas()
        pj = cargar_partidos()
        et = resumen_etapas(pj)
        return {"tem": tem, "pj": pj, "et": et, "nac": nacionalidad_persona(tem)}
    D = _paso("datos", _datos, rehacer, huella=False)
    tem_e = D["tem"].merge(D["et"], on=["liga", "temporada", "player_id"], how="left")
    mov = _paso("traspasos", lambda: identificar_traspasos(D["tem"], D["et"], c), rehacer)

    def _esperado():
        norm = cargar_normalizacion()
        m = anadir_esperado(mov, tem_e, norm, c)
        m = anadir_covariables(m, D["tem"], D["nac"], norm, c)
        m = marcar_observados(m, c)
        m["id"] = (m["persona_id"].astype(str) + ":" + m["liga_destino"] + ":" + m["temporada_destino"])
        ser = construir_series(claves_series_traspasos(m, D["tem"]), D["pj"], c)
        sst = construir_series(claves_series_permanecen(tem_e, c), D["pj"], c)
        m["temprano_logr"] = rendimiento_temprano(m, ser, c["censura"]["partidos_tempranos"])
        base = m[np.isfinite(m["pts_p100_esp"]) & ~m["en_curso"]]
        w, info = pesos_ipcw(base, base["observado"].to_numpy(), c)
        m["w_ipcw"] = 0.0
        m.loc[base.index, "w_ipcw"] = w
        m["p_observado"] = np.nan
        m.loc[base.index, "p_observado"] = info.pop("_p")
        return {"m": m, "ser": ser, "sst": sst, "info_censura": info, "norm": norm}
    E = _paso("esperado", _esperado, rehacer)
    return {**D, "tem_e": tem_e, **E}


def main(rehacer: bool = False, sin_validacion: bool = False) -> dict:
    """python -m bbfit adaptacion: fase 7 completa (reanudable; caché en experimentos/cache_adaptacion)."""
    import json
    import time
    from .registro import experimento
    c = cfg()
    t0 = time.time()
    metricas = list(c["metricas"]["clave"])
    P = preparar(rehacer)
    m, ser, sst, norm = P["m"], P["ser"], P["sst"], P["norm"]
    obs = m[m["observado"] & ~m["en_curso"]]
    print(f"  traspasos: {len(m)} · observados (temporadas cerradas): {len(obs)} · en curso: {int(m['en_curso'].sum())}", flush=True)
    mods = _paso("modelos", lambda: ajustar_modelos(m, metricas, c), rehacer)
    mods_naive = _paso("modelos_sin_ipcw", lambda: ajustar_modelos(m, metricas, c, ipcw=False, cadenas=1), rehacer)
    mods_sinrol = _paso("modelos_sin_rol", lambda: ajustar_modelos(
        m, ["pts_p100", "per", "L", "L_rel"], c, excluir=("cambio_rol", "rol_origen_c", "rol_desconocido"), cadenas=1), rehacer)
    curvas, draws = _paso("curvas", lambda: ajustar_curvas(m, ser, sst, c), rehacer)
    priors = _paso("priors", lambda: tabla_priors(m, mods, draws, c), rehacer)
    seg = _paso("segunda", lambda: segunda_temporada(m, P["tem"], norm, c), rehacer)
    if not sin_validacion:
        casos = pd.read_csv(DIR_MOD / "normalizacion_amortiguada" / "validacion_casos.csv.gz", dtype={"persona_id": str})
        val_t = _paso("validacion_temporal", lambda: validar_temporal(m, metricas, c, casos), rehacer)
        val_l = _paso("validacion_lolo", lambda: validar_lolo(m, metricas, c), rehacer) if c["validacion"]["dejar_fuera_liga"] else pd.DataFrame()
    else:
        val_t = val_l = pd.DataFrame()
    res = escribir_salidas(m, ser, mods, mods_naive, mods_sinrol, curvas, draws, priors, seg, val_t, val_l, P, c)
    res["segundos"] = round(time.time() - t0)
    params = {k: c[k] for k in ("traspasos", "modelo", "curva", "censura", "priors", "adapt")}
    (DIR_SALIDA / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=_json), encoding="utf-8")
    import re
    with experimento("adaptacion", "fase7", params=params, semilla=c["semilla"]) as run:
        # MLflow sólo admite alfanuméricos, _ - . espacio : / en los nombres de métrica
        run.metricas({re.sub(r"[^0-9A-Za-z_\-. :/]", "_", k): v for k, v in _planos(res).items()
                      if isinstance(v, (int, float)) and np.isfinite(v)})
        for f in ("adaptation_priors.csv", "resumen.json"):
            run.artefacto(DIR_SALIDA / f)
    return res


def _json(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (pd.Timestamp,)):
        return str(o)
    return str(o)


def _planos(d: dict, pre: str = "") -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(_planos(v, f"{pre}{k}."))
        elif isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool):
            out[f"{pre}{k}"[:250]] = float(v)
    return out


def _curva_grupo(curvas: pd.DataFrame, serie: str, grupo) -> tuple[float, float]:
    """(D, κ) MAP de la curva neta del grupo de nacionalidad (o global si el grupo no tiene curva propia)."""
    t = curvas[(curvas["serie"] == serie) & (curvas["poblacion"] == "traspasos_neto")]
    r = t[t["perfil"] == f"grupo_nacionalidad={grupo}"]
    if r.empty:
        r = t[t["perfil"] == "global=global"]
    return (float(r["D"].iat[0]), float(r["kappa"].iat[0])) if not r.empty else (0.0, 1.0)


def contrastes_eeuu(mods: dict, variante: str) -> list[dict]:
    """Hipótesis «más penalización para el estadounidense en su primer año europeo» (sin suponerla): posterior de
    β(EEUU_a_Europa) frente al europeo que cambia de liga (referencia) y frente al extranjero (sobre todo
    estadounidense) que ya estaba en Europa y cambia de país."""
    filas = []
    for met, M in mods.items():
        b = M.post["beta"]
        cols = {k: i for i, k in enumerate(M.cols)}
        ku = "grupo_nacionalidad=EEUU_a_Europa"
        if ku not in cols:
            continue
        for ref in ("europeo_cambia_liga", "extranjero_cambia_pais", "nacional_mismo_pais"):
            kr = f"grupo_nacionalidad={ref}"
            x = b[:, cols[ku]] - (b[:, cols[kr]] if kr in cols else 0.0)
            tr = (lambda v: v) if es_aditiva(met) else np.expm1
            filas.append({"variante": variante, "metrica": met, "contraste": f"EEUU_a_Europa − {ref}",
                          "media": float(np.mean(tr(x))), "lo90": float(np.quantile(tr(x), 0.05)),
                          "hi90": float(np.quantile(tr(x), 0.95)), "p_menor_que_0": float(np.mean(x < 0)),
                          "unidad": "L" if es_aditiva(met) else "relativa"})
    return filas


def escribir_salidas(m, ser, mods, mods_naive, mods_sinrol, curvas, draws, priors, seg, val_t, val_l, P, c) -> dict:
    """Escribe data/modelos/adaptacion/* y devuelve el resumen (cifras clave)."""
    DIR_SALIDA.mkdir(parents=True, exist_ok=True)
    mx = float(c["salida"]["max_mb_fichero"])
    metricas = list(c["metricas"]["clave"])
    N = int(c["adapt"]["primeros_partidos"])
    res: dict = {"version": "fase7", "huella_cfg": _huella_cfg(), "traspasos": {
        "total": int(len(m)), "por_tipo": m["tipo"].value_counts().to_dict(),
        "observados_cerradas": int((m["observado"] & ~m["en_curso"]).sum()),
        "censurados_cerradas": int((~m["observado"] & ~m["en_curso"]).sum()), "en_curso": int(m["en_curso"].sum()),
        "por_grupo": m["grupo_nacionalidad"].value_counts().to_dict(),
        "nacionalidad_desconocida_pct": float(m["nacionalidad_desconocida"].mean()),
        "personas": int(m["persona_id"].nunique()), "pares_liga": int((m["liga_origen"] + ">" + m["liga_destino"]).nunique())}}
    # 1. priors
    priors.round(5).to_csv(DIR_SALIDA / "adaptation_priors.csv", index=False)
    # 2. coeficientes, contrastes
    coefs, hip = [], []
    for var, mm in (("ipcw", mods), ("sin_ipcw", mods_naive), ("sin_rol", mods_sinrol)):
        for met, M in mm.items():
            t = M.coeficientes()
            t.insert(0, "metrica", met)
            t.insert(0, "variante", var)
            extra = pd.DataFrame([{"variante": var, "metrica": met, "coeficiente": k, "media": float(np.mean(v)),
                                   "sd": float(np.std(v)), "lo90": float(np.quantile(v, 0.05)), "hi90": float(np.quantile(v, 0.95))}
                                  for k, v in (("sigma", np.sqrt(M.post["sigma2"])), ("tau_pareja", np.sqrt(M.post["tau2_u"])),
                                               ("tau_escalon", np.sqrt(M.post["tau2_v"])))])
            extra = pd.concat([extra, pd.DataFrame([{"variante": var, "metrica": met, "coeficiente": "n", "media": M.n},
                                                    {"variante": var, "metrica": met, "coeficiente": "rhat_max", "media": M.rhat_max}])])
            coefs += [t, extra]
        hip += contrastes_eeuu(mm, var)
    pd.concat(coefs, ignore_index=True).round(5).to_csv(DIR_SALIDA / "coeficientes.csv", index=False)
    hip = pd.DataFrame(hip)
    # curvas: hipótesis de adaptación más lenta (hueco de los 5 primeros partidos y κ)
    cu = curvas[(curvas["poblacion"] == "traspasos_neto") & (curvas["perfil"].isin(["grupo_nacionalidad=EEUU_a_Europa", "global=global"]))]
    hip.round(5).to_csv(DIR_SALIDA / "hipotesis_eeuu.csv", index=False)
    curvas.round(5).to_csv(DIR_SALIDA / "curvas.csv", index=False)
    res["hipotesis_eeuu"] = {f"{r.variante}|{r.metrica}|{r.contraste}": {"media": r.media, "lo90": r.lo90, "hi90": r.hi90, "p<0": r.p_menor_que_0}
                             for r in hip.itertuples() if r.variante in ("ipcw", "sin_rol")}
    res["curva_eeuu_vs_global"] = {f"{r.serie}|{r.perfil}": {"kappa": r.kappa, "kappa_lo": r.kappa_lo, "kappa_hi": r.kappa_hi,
                                                            "hueco_1_5": r.hueco_medio_partidos_1_5, "lo": r.hueco_1_5_lo, "hi": r.hueco_1_5_hi}
                                   for r in cu.itertuples()}
    cg = curvas[(curvas["perfil"].isin(["global", "global=global"]))]
    res["curva_global"] = {f"{r.serie}|{r.poblacion}": {"kappa": r.kappa, "kappa_lo": r.kappa_lo, "kappa_hi": r.kappa_hi,
                                                        "D": r.D, "D_lo": r.D_lo, "D_hi": r.D_hi, "partidos_50": r.partidos_50,
                                                        "partidos_90": r.partidos_90, "hueco_1_5": r.hueco_medio_partidos_1_5,
                                                        "hueco_1_5_lo": r.hueco_1_5_lo, "hueco_1_5_hi": r.hueco_1_5_hi}
                           for r in cg.itertuples()}
    # 3. censura
    d = m[m["observado"] & ~m["en_curso"]]
    todas = m[~m["en_curso"] & (m["min_destino"] > 0)]
    cen = []
    for met in metricas:
        e1 = media_ponderada_muestras(mods[met].eta(d), d["w_ipcw"].to_numpy(float), met)
        e0 = media_ponderada_muestras(mods_naive[met].eta(d), np.ones(len(d)), met)
        r_all = todas[respuesta(met)].astype(float)
        wa = pesos_precision(todas, c)
        okk = np.isfinite(r_all.to_numpy())
        raw_all = float(np.average(r_all[okk], weights=wa[okk]))
        r_obs = d[respuesta(met)].astype(float)
        cen.append({"metrica": met, "delta_ipcw": float(np.mean(e1)), "delta_ipcw_lo": float(np.quantile(e1, 0.05)),
                    "delta_ipcw_hi": float(np.quantile(e1, 0.95)), "delta_sin_ipcw": float(np.mean(e0)),
                    "delta_sin_ipcw_lo": float(np.quantile(e0, 0.05)), "delta_sin_ipcw_hi": float(np.quantile(e0, 0.95)),
                    "efecto_ipcw": float(np.mean(e1) - np.mean(e0)),
                    "media_bruta_observados": float(r_obs.mean()) if es_aditiva(met) else float(np.expm1(r_obs.mean())),
                    "media_bruta_todas_llegadas_pesos_minutos": raw_all if es_aditiva(met) else float(np.expm1(raw_all))})
    cen = pd.DataFrame(cen)
    cen.round(5).to_csv(DIR_SALIDA / "censura.csv", index=False)
    sv = supervivencia(m)
    sv.round(4).to_csv(DIR_SALIDA / "supervivencia.csv", index=False)
    ic = dict(P["info_censura"])
    res["censura"] = {"logit": {k: v for k, v in ic.items() if k != "coeficientes"},
                      "efecto_por_metrica": cen.set_index("metrica")[["delta_ipcw", "delta_sin_ipcw", "efecto_ipcw"]].to_dict("index")}
    # 4. segunda temporada
    if isinstance(seg, pd.DataFrame) and not seg.empty:
        s2 = pd.concat([resumir_segunda(seg, "global", semilla=c["semilla"]),
                        resumir_segunda(seg, "grupo_nacionalidad", semilla=c["semilla"]),
                        resumir_segunda(seg, "direccion", semilla=c["semilla"])], ignore_index=True)
        s2.round(5).to_csv(DIR_SALIDA / "segunda_temporada.csv", index=False)
        res["segunda_temporada"] = s2.set_index("perfil")[["n_siguen", "ganancia_L_rel_ipcw", "lo90", "hi90"]].to_dict("index")
    # 5. ADAPT% histórico
    h = m[["id", "persona_id", "nombre", "tipo", "regreso", "liga_origen", "temporada_origen", "player_id_origen",
           "liga_destino", "temporada_destino", "player_id_destino", "team_destino", "grupo_nacionalidad", "nacionalidad_iso",
           "nacionalidad_desconocida", "pos3", "edad", "edad_desconocida", "arquetipo", "rol_origen", "rol_destino",
           "cambio_rol", "rol_desconocido", "distancia_estilo_equipo", "estilo_desconocido", "cambio_entrenador",
           "entrenador_desconocido", "canterano", "canterano_desconocido", "salto_nivel", "direccion", "escalon_destino",
           "primer_anio_europa", "min_origen", "min_destino", "partidos_destino", "observado", "en_curso", "p_observado",
           "w_ipcw"]].copy()
    oos = val_t[["id", "metrica", "previsto", "pi_lo", "pi_hi", "corte"]] if not val_t.empty else None
    prim = adapt_primeros(m, ser, N)
    for met in metricas:
        p = predecir_adapt(mods[met], m, met, c)
        if met == "L":
            h["L_esperado"], h["L_observado"] = m["L_esp"], m["L_obs"]
            h["delta_L_obs"], h["delta_L"], h["delta_L_lo"], h["delta_L_hi"] = m["L_delta"], p["pred"], p["pred_lo"], p["pred_hi"]
            h["delta_L_pi_lo"], h["delta_L_pi_hi"] = p["pi_lo"], p["pi_hi"]
            continue
        if met != "L_rel":
            h[f"{met}_esperado"], h[f"{met}_esperado_lo"], h[f"{met}_esperado_hi"] = m[f"{met}_esp"], m[f"{met}_esp_lo"], m[f"{met}_esp_hi"]
            h[f"{met}_observado"] = m[f"{met}_obs"]
        h[f"adapt_{met}_obs"] = observado_adapt(m, met)
        h[f"adapt_{met}"], h[f"adapt_{met}_lo"], h[f"adapt_{met}_hi"] = p["pred"], p["pred_lo"], p["pred_hi"]
        h[f"adapt_{met}_pi_lo"], h[f"adapt_{met}_pi_hi"] = p["pi_lo"], p["pi_hi"]
        if oos is not None:
            o = oos[oos["metrica"] == met].drop_duplicates("id").set_index("id")
            h[f"adapt_{met}_fuera_muestra"] = m["id"].map(o["previsto"])
        serie = c["curva"]["serie_por_metrica"].get(met, "prod_p100")
        fac = np.array([factor_primeros(*_curva_grupo(curvas, serie, g), N, n1)
                        for g, n1 in zip(m["grupo_nacionalidad"], m["partidos_destino"].astype(float))])
        h[f"adapt_{met}_primeros{N}"] = p["pred"].to_numpy() * fac
        if met in prim:
            h[f"adapt_{met}_primeros{N}_obs"] = prim[met]
    h["adapt_pct"], h["adapt_pct_lo"], h["adapt_pct_hi"] = h["adapt_L_rel"], h["adapt_L_rel_lo"], h["adapt_L_rel_hi"]
    h["adapt_pct_obs"] = h["adapt_L_rel_obs"]
    h[f"adapt_pct_primeros{N}"], h[f"adapt_pct_primeros{N}_obs"] = h[f"adapt_L_rel_primeros{N}"], h.get(f"adapt_L_rel_primeros{N}_obs")
    ph = DIR_SALIDA / "adapt_historico.csv.gz"
    h.round(4).to_csv(ph, index=False, compression="gzip")
    # unión con la columna adapt_pct de roles (fase 3): liga, temporada y jugador de destino
    rj = h[["liga_destino", "temporada_destino", "player_id_destino", "team_destino", "adapt_pct", "adapt_pct_lo",
            "adapt_pct_hi", "adapt_pct_obs", f"adapt_pct_primeros{N}"]].rename(columns={
                "liga_destino": "liga", "temporada_destino": "temporada", "player_id_destino": "player_id", "team_destino": "team_id"})
    rj.round(3).to_csv(DIR_SALIDA / "adapt_pct_roles.csv", index=False)
    # 6. validación y calibración
    cal = []
    ins = pd.concat([pd.DataFrame({"metrica": met, "observado": observado_adapt(d, met).to_numpy(),
                                   **{k: v.to_numpy() for k, v in predecir_adapt(mods[met], d, met, c)[["pred", "pi_lo", "pi_hi"]]
                                      .rename(columns={"pred": "previsto"}).items()}}) for met in metricas], ignore_index=True)
    cal.append(calibracion(ins, c["adapt"]["bins_calibracion"], "en_muestra"))
    val_rows = []
    res["validacion"] = {}
    if not val_t.empty:
        val_t.round(5).to_csv(DIR_SALIDA / "validacion_casos.csv.gz", index=False, compression="gzip")
        a = resumir_validacion(val_t, ["metrica", "corte"]).assign(examen="temporal")
        b = resumir_validacion(val_t, ["metrica"]).assign(examen="temporal_conjunto")
        val_rows += [a, b]
        cal.append(calibracion(val_t, c["adapt"]["bins_calibracion"], "fuera_de_muestra_temporal"))
        res["validacion"]["temporal"] = b.set_index("metrica").to_dict("index")
    if not val_l.empty:
        a = resumir_validacion(val_l, ["metrica", "liga_fuera"]).assign(examen="dejar_fuera_liga")
        b = resumir_validacion(val_l, ["metrica"]).assign(examen="dejar_fuera_liga_conjunto")
        val_rows += [a, b]
        cal.append(calibracion(val_l, c["adapt"]["bins_calibracion"], "dejar_fuera_liga"))
        res["validacion"]["dejar_fuera_liga"] = b.set_index("metrica").to_dict("index")
    if val_rows:
        pd.concat(val_rows, ignore_index=True).round(5).to_csv(DIR_SALIDA / "validacion.csv", index=False)
    cal = pd.concat(cal, ignore_index=True)
    cal.round(4).to_csv(DIR_SALIDA / "calibracion.csv", index=False)
    res["calibracion_cobertura_80"] = cal.groupby(["muestra", "metrica"]).apply(
        lambda g: float(np.average(g["cobertura_80"], weights=g["n"])), include_groups=False).unstack(0).to_dict()
    # 7. Δ por grupo (marginal, ponderado por IPCW) y κ / partidos al 50-90 %
    gg = priors[(priors["nivel"] == "global_grupo") | (priors["nivel"] == "global")]
    res["delta_por_grupo"] = {f"{r.metrica}|{r.grupo_nacionalidad}": {
        "n": r.n, "delta_temporada": r.delta_temporada_media, "lo90": r.delta_temporada_lo, "hi90": r.delta_temporada_hi,
        "delta_interfaz": r.delta_media, "kappa_interfaz": r.kappa_media} for r in gg.itertuples()}
    res["modelo"] = {met: {"n": M.n, "rhat_max": M.rhat_max, "sigma": float(np.sqrt(M.post["sigma2"]).mean()),
                           "tau_pareja": float(np.sqrt(M.post["tau2_u"]).mean()),
                           "tau_escalon": float(np.sqrt(M.post["tau2_v"]).mean())} for met, M in mods.items()}
    res["ficheros_mb"] = {p.name: round(p.stat().st_size / 1e6, 2) for p in DIR_SALIDA.iterdir() if p.is_file()}
    grandes = [k for k, v in res["ficheros_mb"].items() if v > mx]
    if grandes:
        raise RuntimeError(f"ficheros > {mx} MB: {grandes}")
    return res


def rellenar_adapt_pct(roles: pd.DataFrame, ruta: Path | None = None) -> pd.DataFrame:
    """Rellena en memoria la columna `adapt_pct` (vacía en la fase 3) de player_role_season / player_role_spells con el
    ADAPT% previsto de la temporada de llegada a la liga (unión por liga, temporada y player_id de destino). Las filas que
    no son la primera temporada tras un cambio de liga quedan en NaN (no hay traspaso que adaptar)."""
    p = Path(ruta or DIR_SALIDA / "adapt_pct_roles.csv")
    a = pd.read_csv(p, dtype={"player_id": str, "team_id": str}).drop_duplicates(["liga", "temporada", "player_id"])
    r = roles.drop(columns=["adapt_pct"], errors="ignore").copy()
    r["player_id"] = r["player_id"].astype(str)
    return r.merge(a[["liga", "temporada", "player_id", "adapt_pct"]], on=["liga", "temporada", "player_id"], how="left")
