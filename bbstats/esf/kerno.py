"""Kerno Basque Analytics · sitio de equipos (misma tipología que «Kerno Analytics · Equipos»).

    python -m bbstats.esf kerno [--salida data/basko/artifact/sitio]

Genera, desde la salida procesada de la Federación Vasca (data/basko/processed/<temporada>/), los mismos contratos de
datos que consumen las herramientas del sitio general de equipos (Evaluación, Rotación, Quintetos, Parejas y tríos,
Conexiones, Impacto en pista, La liga, Informe de equipo en PDF, Mapa de estilos), con tres decisiones propias:

* Unidad de análisis = liga × temporada con jugada a jugada (2022-23 en adelante), con TODOS los partidos de la
  temporada (todas las fases y, en Junior y Cadete, las dos divisiones: A1 y A2). Cada equipo lleva su división.
  En los ficheros la temporada completa va como fase «regular» y «total» (mismo contenido): el sitio general separa
  liga regular y playoffs; aquí no hay playoffs, y una sola unidad maximiza la muestra de ligas cortas.
* Los seis estilos son los del sitio general (taxonomía unificada jugador ↔ equipo: Pistons, Isolation, Old-School,
  Spacing, Circulación, Pintura; data/modelos/estilos_unificados/estilos.json). Cada rasgo se mide en z por rangos
  DENTRO de su liga vasca y temporada y se proyecta con la MISMA mezcla gaussiana (probabilidad a posteriori con los
  rasgos observados): un equipo «Spacing» de Primera Nacional lo es frente a Primera Nacional.
* Nivel Kerno vasco: no hay puente de normalización entre las ligas vascas y las profesionales, así que el Nivel Kerno
  se define dentro de cada liga vasca y temporada, con la misma lectura que el general (0–100, 50 = jugador medio de
  su liga, ponderado por minutos, con su rango del 80 %; escala del sitio: 50 + 50·tanh(z/2), 73 = una desviación
  típica por encima). Nace de dos capas:
    Producción = media de z por rangos (contraídos hacia la media de la liga según minutos) de PER, Win Shares por 40,
                 Game Score por 40 y PIE.
    Impacto    = media de z de RAPM (jugada a jugada, ridge) y on/off ajustado por muestra.
    Nivel      = 0,6·Producción + 0,4·Impacto, re-estandarizado a la liga.
  Rango del 80 %: ± 1,2816 · DT de la estimación, que decrece con los minutos (k / (m + k), k = 300 min).
  Sin simulador ni proyección multiliga: lo que no se puede estimar no se muestra.

Además: posición (E/A/I) estimada con la regresión logística de bbmodel.posicion entrenada con las ligas FEB y la
ACB (la Federación Vasca no publica la posición), tiempos muertos, posesiones defensivas y quintetos iniciales por
equipo (como bbstats/lineups/equipo_extras.py), y la pista de cada jugador (zonas de tiro).
"""
from __future__ import annotations

import base64
import gzip
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import logsumexp
from scipy.stats import norm

RAIZ = Path(__file__).resolve().parents[2]
PROC = RAIZ / "data" / "basko" / "processed"
SALIDA = RAIZ / "data" / "basko" / "artifact" / "sitio"
ESTILOS_JSON = RAIZ / "data" / "modelos" / "estilos_unificados" / "estilos.json"

LIGAS = ["esf_1nac", "esf_2nac", "esf_jun", "esf_cad"]
NOMBRE = {"esf_1nac": "Primera Nacional", "esf_2nac": "Segunda Nacional", "esf_jun": "Junior · Liga Vasca",
          "esf_cad": "Cadete · Liga Vasca"}
CORTO = {"esf_1nac": "1ª Nacional", "esf_2nac": "2ª Nacional", "esf_jun": "Junior", "esf_cad": "Cadete"}
FASES = ("regular", "total")              # la temporada completa, con las dos claves que leen las páginas
MIN_PARTIDOS_PBP = 40                     # temporada-liga con jugada a jugada suficiente para entrar
R_ARO, R_CORTA = 1.8, 4.25                # zonas de tiro del sitio general (bbmodel/zonas.py)
K_ESTILO = 150.0                          # contracción de la tasa del jugador hacia su liga (estilos)
K_NIVEL = 300.0                           # contracción y rango del Nivel Kerno
Z80 = 1.2815515655446004
PESO_PROD, PESO_IMP = 0.6, 0.4
PROD = ["per", "ws_per_40", "gs40", "pie"]
IMP = ["pbp_rapm", "pbp_net_rtg_aj_onoff"]
RASGOS = ["ritmo", "triple", "esquina", "aro", "tiros_libres", "autocreacion", "asistencia", "reb_ofensivo",
          "perdidas", "robos", "tapones", "faltas"]
PMIN = 0.01


# ============================================================================================ utilidades
def _num(v, nd=3):
    if v is None:
        return None
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    if not math.isfinite(f):
        return None
    r = round(f, nd)
    return int(r) if r == int(r) and abs(r) < 1e15 else r


def tabla_cf(df: pd.DataFrame, cols: list[str], nd: dict | None = None) -> dict:
    """{"c": columnas, "f": filas} (formato de las páginas de quintetos)."""
    nd = nd or {}
    cols = [c for c in cols if c in df.columns]
    filas = []
    for row in df[cols].itertuples(index=False):
        filas.append([v if isinstance(v, (str, list, dict)) or v is None else _num(v, nd.get(c, 2))
                      for c, v in zip(cols, row)])
    return {"c": cols, "f": filas}


def tabla_cols(df: pd.DataFrame, nd: dict | None = None) -> dict:
    """{"columnas": ..., "filas": ...} (formato del Atlas y de equipos.gz.txt)."""
    t = tabla_cf(df, list(df.columns), nd)
    return {"columnas": t["c"], "filas": t["f"]}


def gz_b64(obj) -> bytes:
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=_num).encode("utf-8")
    return base64.b64encode(gzip.compress(raw, 9))


def escribir(path: Path, obj, claro: bool = False) -> int:
    """<ruta>.gz.txt (gzip en base64) y, si se pide, <ruta> en claro."""
    path.parent.mkdir(parents=True, exist_ok=True)
    b = gz_b64(obj)
    destino = path if path.name.endswith(".gz.txt") else path.with_name(path.name + ".gz.txt")
    destino.write_bytes(b)
    if claro:
        path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=_num), encoding="utf-8")
    return len(b)


def slug(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def titulo(s: str) -> str:
    s = str(s or "").strip()
    if s and s == s.upper():
        s = s.lower()
        s = re.sub(r"(^|[\s\-'’.(/])(\w)", lambda m: m.group(1) + m.group(2).upper(), s)
        s = re.sub(r"(?<=\S\s)(De|Del|La|Las|Los|Y|E)(?=\s)", lambda m: m.group(1).lower(), s)
    return s


def _div(a, b):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(b > 0, a / np.where(b > 0, b, 1.0), np.nan)


def ecdf_z(ref: np.ndarray, w: np.ndarray, x: np.ndarray, pmin: float = PMIN) -> np.ndarray:
    """z = Φ⁻¹(percentil ponderado de x en (ref, w)); percentil medio en empates (bbfit.estilos_unificados)."""
    ok = np.isfinite(ref) & (w > 0)
    out = np.full(len(x), np.nan)
    if ok.sum() < 3:
        return out
    v, ww = ref[ok], w[ok]
    o = np.argsort(v, kind="mergesort")
    v, ww = v[o], ww[o]
    cw = np.concatenate([[0.0], np.cumsum(ww)])
    W = cw[-1]
    fx = np.isfinite(x)
    lo = np.searchsorted(v, x[fx], side="left")
    hi = np.searchsorted(v, x[fx], side="right")
    F = (cw[lo] + 0.5 * (cw[hi] - cw[lo])) / W
    out[fx] = norm.ppf(np.clip(F, pmin, 1 - pmin))
    return out


def contraer(x, m, mu, k):
    return (m * x + k * mu) / (m + k)


def temporadas() -> list[str]:
    """Temporadas con jugada a jugada (alguna liga con ≥ MIN_PARTIDOS_PBP partidos con quintetos válidos)."""
    out = []
    for d in sorted(PROC.glob("20??-??")):
        n = 0
        for liga in LIGAS:
            p = d / "partidos" / f"{liga}.csv"
            if p.exists():
                x = pd.read_csv(p, usecols=lambda c: c in ("quintetos_validos", "con_acta"), low_memory=False)
                if "quintetos_validos" in x:
                    n = max(n, int(x["quintetos_validos"].astype(str).str.lower().eq("true").sum()))
        if n >= MIN_PARTIDOS_PBP:
            out.append(d.name)
    return out


# ============================================================================================ carga
def ids_estables(E: pd.DataFrame) -> dict[str, str]:
    """{team_id de la temporada: id estable}. Id = club (slug); con varios equipos del club en la liga, + su letra o
    su nombre."""
    if E.empty:
        return {}
    d = E.drop_duplicates("team_id")[["team_id", "equipo", "club"]].copy()
    d["team_id"] = d["team_id"].astype(str)
    d["c"] = [slug(c) or slug(e) for c, e in zip(d["club"].fillna(""), d["equipo"].fillna(""))]
    out = {}
    letra = lambda eq: re.search(r'(?:^|\s)"?([A-Da-d])"?\s*$', str(eq).strip())  # noqa: E731
    for c, g in d.groupby("c"):
        if len(g) == 1 and not letra(g["equipo"].iloc[0]):
            out[g["team_id"].iloc[0]] = c
            continue
        usados = set()
        for tid, eq in zip(g["team_id"], g["equipo"]):
            m = letra(eq)
            suf = m.group(1).lower() if m else (slug(eq) if len(g) > 1 else "")
            k = f"{c}-{suf}" if suf else c
            while k in usados:
                k += "-2"
            usados.add(k)
            out[tid] = k
    return out


class Liga:
    """Todo lo de una liga vasca en una temporada (unidad = temporada completa)."""

    def __init__(self, t: str, liga: str):
        self.t, self.liga = t, liga
        base = PROC / t
        ids = {"team_id": str, "player_id": str, "persona_uuid": str}
        self.J = pd.read_csv(base / "jugadores" / f"{liga}.csv", dtype=ids, low_memory=False)
        self.J = self.J[self.J["fase"] == "total"].copy()
        self.E = pd.read_csv(base / "equipos" / f"{liga}.csv", dtype={"team_id": str}, low_memory=False)
        self.Eall = self.E.copy()
        self.E = self.E[self.E["fase"] == "total"].copy()
        self.P = pd.read_csv(base / "partidos" / f"{liga}.csv", dtype={"local_id": str, "visitante_id": str,
                                                                        "game_id": str}, low_memory=False)
        pl = base / "plantillas" / f"{liga}.csv"
        self.PL = pd.read_csv(pl, dtype={"team_id": str}, low_memory=False) if pl.exists() else pd.DataFrame()
        q = base / "quintetos" / liga
        self.qdir = q
        rd = lambda n, **kw: pd.read_csv(q / n, low_memory=False, **kw) if (q / n).exists() else pd.DataFrame()  # noqa: E731
        self.QJ = rd("jugadores.csv", dtype={"team_id": str, "player_id": str})
        self.QE = rd("equipos.csv", dtype={"team_id": str})
        self.Q5 = rd("quintetos.csv.gz", dtype={"team_id": str, "unidad": str})
        self.Q3 = rd("trios.csv.gz", dtype={"team_id": str, "unidad": str})
        self.Q2 = rd("parejas.csv.gz", dtype={"team_id": str, "jugador_a_id": str, "jugador_b_id": str})
        self.QA = rd("asistencias.csv", dtype={"team_id": str, "pasador_id": str, "receptor_id": str})
        self.QV = rd("validacion.csv", dtype={"game_id": str})
        for n in ("QJ", "QE", "Q5", "Q3", "Q2", "QA"):
            d = getattr(self, n)
            if len(d) and "fase" in d:
                setattr(self, n, d[d["fase"] == "total"].copy())
        self.TI = pd.read_csv(base / "tiros" / f"{liga}.csv.gz", dtype={"team_id": str, "player_id": str},
                              low_memory=False) if (base / "tiros" / f"{liga}.csv.gz").exists() else pd.DataFrame()
        self._ev = None
        self._bx = None
        # id estable del equipo entre temporadas (la Federación cambia el id de inscripción cada año): el club; si el club
        # tiene varios equipos en la liga, su letra («BASKONIA "A"», «BASKONIA B») o, si no la tiene, su nombre
        self.sid = ids_estables(self.Eall)
        for n in ("J", "E", "Eall", "PL", "QJ", "QE", "Q5", "Q3", "Q2", "QA", "TI"):
            d = getattr(self, n)
            if len(d) and "team_id" in d:
                d["team_id"] = d["team_id"].astype(str).map(lambda x: self.sid.get(x, x))
        for c in ("local_id", "visitante_id"):
            self.P[c] = self.P[c].astype(str).map(lambda x: self.sid.get(x, x))
        self.nombre_eq = (self.E.set_index("team_id")["equipo"].map(titulo).to_dict() if len(self.E) else {})
        # división de cada equipo (Junior y Cadete): la de más partidos en sus filas por división
        self.division = {}
        if "division" in self.Eall:
            d = self.Eall[self.Eall["division"].isin(["A1", "A2", "única"])]
            for tid, g in d.groupby("team_id"):
                self.division[tid] = g.groupby("division")["gp"].sum().idxmax()

    @property
    def EV(self) -> pd.DataFrame:
        if self._ev is None:
            p = PROC / self.t / "eventos" / f"{self.liga}.csv.gz"
            self._ev = pd.read_csv(p, dtype={"team_id": str, "player_id": str, "game_id": str}, low_memory=False) \
                if p.exists() else pd.DataFrame()
            if len(self._ev):
                self._ev["team_id"] = self._ev["team_id"].map(lambda x: self.sid.get(str(int(float(x))), str(int(float(x)))) if pd.notna(x) and x != "nan" else None)
        return self._ev

    @property
    def BX(self) -> pd.DataFrame:
        if self._bx is None:
            p = PROC / self.t / "boxscores" / f"{self.liga}.csv.gz"
            self._bx = pd.read_csv(p, dtype={"team_id": str, "player_id": str, "game_id": str}, low_memory=False) \
                if p.exists() else pd.DataFrame()
            if len(self._bx):
                self._bx["team_id"] = self._bx["team_id"].astype(str).map(lambda x: self.sid.get(x, x))
        return self._bx

    def coaches(self) -> dict[str, list[str]]:
        out = defaultdict(list)
        if len(self.PL):
            for r in self.PL[self.PL["tipo_licencia"] == "ENTRENADOR/A"].itertuples():
                out[str(r.team_id)].append(titulo(r.nombre_completo))
        return {k: list(dict.fromkeys(v)) for k, v in out.items()}


# ============================================================================================ pista (zonas)
def zonas_jugador(L: Liga) -> pd.DataFrame:
    """fga/fgm por zona del sitio general (aro < 1,8 m, corta < 4,25 m, media, triple de esquina y frontal) y
    canastas asistidas (si la mesa registra asistencias) por equipo-jugador."""
    t = L.TI
    if t.empty:
        return pd.DataFrame(columns=["team_id", "player_id"])
    t = t.copy()
    d = pd.to_numeric(t["distancia_m"], errors="coerce")
    v = pd.to_numeric(t["valor"], errors="coerce")
    z = np.where(v == 3, np.where(t["zona"] == "triple_esquina", "t3_esquina", "t3_frontal"),
                 np.where(d < R_ARO, "aro", np.where(d < R_CORTA, "corta", "media")))
    t["z"] = np.where(d.notna() | (v == 3), z, None)
    t["made"] = t["anotado"].astype(str).str.lower().eq("true").astype(int)
    out = t.groupby(["team_id", "player_id"]).agg(fga_pbp=("valor", "size"), fgm_pbp=("made", "sum"))
    for zz in ["aro", "corta", "media", "t3_esquina", "t3_frontal"]:
        s = t[t["z"] == zz].groupby(["team_id", "player_id"])["made"].agg(["size", "sum"])
        out[f"fga_{zz}"] = s["size"]
        out[f"fgm_{zz}"] = s["sum"]
    out = out.fillna(0).reset_index()
    return out


# ============================================================================================ posición (E/A/I)
_POS_MOD: dict = {}
POS_RASGOS = ["oreb_p100", "dreb_p100", "fg3a_rate", "stl_p100", "fta_rate", "tov_pct", "pts_p100", "ast_pct", "blk_p100"]


def _z_liga(df: pd.DataFrame, cols, grupos=("liga", "temporada"), minmin=100) -> pd.DataFrame:
    X = pd.DataFrame(index=df.index)
    base = pd.to_numeric(df["min"], errors="coerce") >= minmin
    for c in cols:
        v = pd.to_numeric(df[c], errors="coerce")
        g = v[base].groupby([df.loc[base, k] for k in grupos])
        mu, sd = g.mean(), g.std()
        k = pd.MultiIndex.from_frame(df[list(grupos)])
        X[c] = (v.to_numpy() - mu.reindex(k).to_numpy()) / sd.reindex(k).to_numpy()
    return X


def modelo_posicion(cols: tuple[str, ...]):
    """Regresión logística multinomial (bbmodel.posicion) entrenada con FEB 1-3 y ACB (posición oficial)."""
    if cols in _POS_MOD:
        return _POS_MOD[cols]
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from bbmodel.posicion import oficial
    fr = []
    for p in sorted((RAIZ / "data" / "processed").glob("20??-??/ligas/*.csv")):
        if p.stem not in ("feb1", "feb2", "feb3", "acb"):
            continue
        d = pd.read_csv(p, usecols=lambda c: c in set(POS_RASGOS) | {"posicion", "min", "fase", "liga", "temporada"},
                        low_memory=False)
        d = d[d["fase"] == "regular"]
        fr.append(d)
    if not fr:
        _POS_MOD[cols] = None
        return None
    d = pd.concat(fr, ignore_index=True)
    d["g"] = [oficial(x)[0] for x in d["posicion"]]
    X = _z_liga(d, cols)
    ok = d["g"].notna() & np.isfinite(X).all(1) & (pd.to_numeric(d["min"], errors="coerce") >= 150)
    m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=1.0))
    m.fit(X[ok].to_numpy(), d.loc[ok, "g"].to_numpy())
    _POS_MOD[cols] = m
    return m


def posiciones(J: pd.DataFrame) -> pd.Series:
    """pos3 estimada para cada fila (jugadores de UNA liga-temporada); sin datos suficientes, None."""
    J = J.assign(liga="x", temporada="x")
    out = pd.Series([None] * len(J), index=J.index, dtype=object)
    disp = [c for c in POS_RASGOS if c in J and pd.to_numeric(J[c], errors="coerce").notna().sum() > 10]
    X = _z_liga(J, disp)
    for cols in (tuple(disp), tuple(c for c in disp if c not in ("ast_pct", "blk_p100"))):
        m = modelo_posicion(cols)
        if m is None:
            continue
        ok = np.isfinite(X[list(cols)]).all(1) & out.isna()
        if ok.any():
            out[ok] = m.predict(X.loc[ok, list(cols)].to_numpy())
    return out


# ============================================================================================ Nivel Kerno vasco
def nivel_kerno(J: pd.DataFrame) -> pd.DataFrame:
    """Producción, Impacto y Nivel Kerno de cada jugador de UNA liga-temporada (0–100, 50 = jugador medio de la liga
    ponderado por minutos) con su rango del 80 %. Devuelve columnas nk, nk_lo, nk_hi, prod, imp (0–100) y L (z)."""
    m = pd.to_numeric(J["min"], errors="coerce").fillna(0).to_numpy(float)
    gp = pd.to_numeric(J["gp"], errors="coerce").fillna(0).to_numpy(float)
    X = pd.DataFrame(index=J.index)
    X["per"] = pd.to_numeric(J["per"], errors="coerce")
    X["ws_per_40"] = pd.to_numeric(J["ws_per_40"], errors="coerce")
    X["gs40"] = _div(pd.to_numeric(J["game_score_pg"], errors="coerce") * gp * 40, m)
    X["pie"] = pd.to_numeric(J["pie"], errors="coerce")
    X["pbp_rapm"] = pd.to_numeric(J.get("pbp_rapm"), errors="coerce")
    X["pbp_net_rtg_aj_onoff"] = pd.to_numeric(J.get("pbp_net_rtg_aj_onoff"), errors="coerce")
    mref = min(150.0, 0.3 * float(m.max()) if len(m) else 150.0)
    en_ref = m >= mref
    Z = pd.DataFrame(index=J.index)
    for c in PROD + IMP:
        x = X[c].to_numpy(float)
        okr = en_ref & np.isfinite(x)
        if okr.sum() < 5:
            Z[c] = np.nan
            continue
        mu = float(np.average(x[okr], weights=m[okr]))
        xs = np.where(np.isfinite(x), contraer(x, m, mu, K_NIVEL), np.nan)
        Z[c] = ecdf_z(xs[okr], m[okr], xs)
    zp = Z[PROD].mean(1, skipna=True)
    zi = Z[IMP].mean(1, skipna=True)
    zn = np.where(zi.notna(), PESO_PROD * zp + PESO_IMP * zi, zp)
    zn = pd.Series(zn, index=J.index)

    def estandar(z: pd.Series) -> pd.Series:
        ok = en_ref & z.notna().to_numpy()
        if ok.sum() < 5:
            return z
        mu = np.average(z[ok], weights=m[ok])
        sd = math.sqrt(np.average((z[ok] - mu) ** 2, weights=m[ok])) or 1.0
        return (z - mu) / sd

    zn, zp, zi = estandar(zn), estandar(zp), estandar(zi)
    se = np.sqrt(K_NIVEL / (m + K_NIVEL))          # DT de la estimación (en desviaciones de la liga)
    pct = lambda z: 50 + 50 * np.tanh(np.asarray(z, float) / 2)  # noqa: E731  (escala 0–100 del sitio: 73 = +1 DT)
    out = pd.DataFrame(index=J.index)
    out["L"] = zn
    out["nk"] = pct(zn)
    out["nk_lo"] = pct(zn - Z80 * se)
    out["nk_hi"] = pct(zn + Z80 * se)
    out["prod"] = pct(zp)
    out["imp"] = pct(zi)
    out["imp_lo"] = pct(zi - Z80 * se)
    out["imp_hi"] = pct(zi + Z80 * se)
    out["se"] = se
    for c in PROD + IMP:
        out[f"z_{c}"] = Z[c]
    out.loc[m <= 0, ["L", "nk", "nk_lo", "nk_hi", "prod", "imp", "imp_lo", "imp_hi"]] = np.nan
    return out


# ============================================================================================ estilos unificados
def cargar_mezcla() -> dict:
    d = json.loads(ESTILOS_JSON.read_text(encoding="utf-8"))
    mz = d["mezcla"]
    return {"medias": np.array(mz["medias"], float), "covs": np.array(mz["covarianzas"], float),
            "pesos": np.array(mz["pesos"], float), "estilos": d["estilos"], "rasgos": d["rasgos"],
            "asignacion": d.get("asignacion", {"umbral_puro": 0.8, "umbral_mezcla": 0.25}), "json": d}


def posterior(medias, covs, pesos, X) -> np.ndarray:
    """Copia de bbfit.estilos_unificados.posterior (verosimilitud marginal en los rasgos observados)."""
    X = np.atleast_2d(X)
    n, K = len(X), len(pesos)
    out = np.full((n, K), np.nan)
    obs = np.isfinite(X)
    if not n:
        return out
    patrones, inv = np.unique(obs, axis=0, return_inverse=True)
    for ip, pat in enumerate(patrones):
        filas = np.where(inv.ravel() == ip)[0]
        if pat.sum() < 8:
            continue
        xo = X[np.ix_(filas, np.where(pat)[0])]
        Lk = np.empty((len(filas), K))
        for k in range(K):
            S = covs[k][np.ix_(pat, pat)]
            mu = medias[k][pat]
            _, logdet = np.linalg.slogdet(S)
            D = xo - mu
            sol = np.linalg.solve(S, D.T).T
            Lk[:, k] = np.log(pesos[k]) - 0.5 * (np.sum(D * sol, 1) + logdet + pat.sum() * np.log(2 * np.pi))
        out[filas] = np.exp(Lk - logsumexp(Lk, axis=1, keepdims=True))
    return out


def etiqueta(P: np.ndarray, nombres: list[str], asig: dict) -> list:
    """[índice, p, etiqueta] por fila (como estilos_unificados_clubes.gz.txt)."""
    out = []
    for p in P:
        if not np.isfinite(p).all():
            out.append(None)
            continue
        o = np.argsort(-p)
        k1, k2 = int(o[0]), int(o[1])
        p1, p2 = float(p[k1]), float(p[k2])
        if p1 >= asig["umbral_puro"]:
            et = f"{nombres[k1]} puro"
        elif p2 >= asig["umbral_mezcla"]:
            et = f"{nombres[k1]} · {nombres[k2]}"
        else:
            et = nombres[k1]
        out.append([k1, round(p1, 3), et])
    return out


def rasgos_equipo(L: Liga, zon: pd.DataFrame) -> pd.DataFrame:
    E = L.E.set_index("team_id")
    f = lambda c: pd.to_numeric(E[c], errors="coerce")  # noqa: E731
    poss = f("team_poss")
    out = pd.DataFrame(index=E.index)
    out["ritmo"] = f("team_pace")
    out["triple"] = _div(f("team_fg3a"), f("team_fga"))
    out["tiros_libres"] = _div(f("team_fta"), f("team_fga"))
    reg_ast = L.J.groupby("team_id")["registra_asistencias"].apply(lambda s: s.astype(str).str.lower().eq("true").any())
    reg_blk = L.J.groupby("team_id")["registra_tapones"].apply(lambda s: s.astype(str).str.lower().eq("true").any())
    out["asistencia"] = np.where(reg_ast.reindex(E.index).fillna(False), 100 * _div(f("team_ast"), f("team_fgm")), np.nan)
    out["reb_ofensivo"] = 100 * _div(f("team_oreb"), poss)
    out["perdidas"] = 100 * _div(f("team_tov"), f("team_fga") + 0.44 * f("team_fta") + f("team_tov"))
    out["robos"] = 100 * _div(f("team_stl"), poss)
    out["tapones"] = np.where(reg_blk.reindex(E.index).fillna(False), 100 * _div(f("team_blk"), poss), np.nan)
    out["faltas"] = 100 * _div(f("team_pf"), poss)
    if len(zon):
        s = zon.groupby("team_id")[["fga_pbp", "fgm_pbp", "fga_aro", "fga_t3_esquina"]].sum().reindex(E.index)
        out["esquina"] = _div(s["fga_t3_esquina"], s["fga_pbp"])
        out["aro"] = _div(s["fga_aro"], s["fga_pbp"])
    else:
        out["esquina"] = out["aro"] = np.nan
    # canastas propias sin asistencia: sólo si la mesa registra asistencias (boxscores: fgm_asistidos)
    bx = L.BX
    if len(bx) and reg_ast.any():
        b = bx.copy()
        b["fgm_asistidos"] = pd.to_numeric(b["fgm_asistidos"], errors="coerce")
        g = b.groupby("team_id")[["fgm", "fgm_asistidos"]].sum().reindex(E.index)
        out["autocreacion"] = np.where(reg_ast.reindex(E.index).fillna(False), 1 - _div(g["fgm_asistidos"], g["fgm"]), np.nan)
    else:
        out["autocreacion"] = np.nan
    out["gp"] = f("gp")
    return out[RASGOS + ["gp"]]


def rasgos_jugador(L: Liga, zon: pd.DataFrame) -> pd.DataFrame:
    J = L.J.copy()
    f = lambda c: pd.to_numeric(J[c], errors="coerce")  # noqa: E731
    out = pd.DataFrame(index=J.index)
    # ritmo: el del equipo corregido por el ritmo con él en pista (quintetos: poss_on / min_on)
    qj = L.QJ.set_index(["team_id", "player_id"]) if len(L.QJ) else pd.DataFrame()
    k = pd.MultiIndex.from_frame(J[["team_id", "player_id"]])
    if len(qj):
        ppm = _div(qj["poss_on"].reindex(k).to_numpy(float), qj["min_on"].reindex(k).to_numpy(float))
        eq = L.QJ.groupby("team_id")[["poss_on", "min_on"]].sum()
        ppm_eq = J["team_id"].map(pd.Series(_div(eq["poss_on"], eq["min_on"]), index=eq.index)).astype(float).to_numpy()
        mon = qj["min_on"].reindex(k).to_numpy(float)
        ratio = np.where((np.nan_to_num(mon) >= 20) & np.isfinite(ppm) & np.isfinite(ppm_eq), ppm / ppm_eq, 1.0)
    else:
        ratio = 1.0
    out["ritmo"] = f("team_pace") * ratio
    out["triple"] = _div(f("fg3a"), f("fga"))
    z = zon.set_index(["team_id", "player_id"]).reindex(k) if len(zon) else None
    out["esquina"] = _div(z["fga_t3_esquina"].to_numpy(float), z["fga_pbp"].to_numpy(float)) if z is not None else np.nan
    out["aro"] = _div(z["fga_aro"].to_numpy(float), z["fga_pbp"].to_numpy(float)) if z is not None else np.nan
    out["tiros_libres"] = _div(f("fta"), f("fga"))
    reg_ast = J["registra_asistencias"].astype(str).str.lower().eq("true").to_numpy()
    reg_blk = J["registra_tapones"].astype(str).str.lower().eq("true").to_numpy()
    fgm_as = f("fgm_asistidos") if "fgm_asistidos" in J else pd.Series(np.nan, index=J.index)
    out["autocreacion"] = np.where(reg_ast, 1 - _div(fgm_as, f("fgm")), np.nan)
    out["asistencia"] = np.where(reg_ast, f("ast_pct"), np.nan)
    out["reb_ofensivo"] = f("oreb_p100")
    out["perdidas"] = 100 * _div(f("tov"), f("fga") + 0.44 * f("fta") + f("tov"))
    out["robos"] = f("stl_p100")
    out["tapones"] = np.where(reg_blk, f("blk_p100"), np.nan)
    out["faltas"] = f("pf_p100")
    out["min"] = f("min").fillna(0)
    return out[RASGOS + ["min"]]


def puntuar(eq: pd.DataFrame, jg: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """z por rangos dentro de la liga-temporada: equipos sin ponderar; jugadores ponderados por minutos y contraídos."""
    eq, jg = eq.copy(), jg.copy()
    m = jg["min"].to_numpy(float)
    mref = min(150.0, 0.3 * float(m.max())) if len(m) else 150.0
    en_ref = m >= mref
    for r in RASGOS:
        xe = eq[r].to_numpy(float)
        eq[f"z_{r}"] = ecdf_z(xe, np.ones(len(xe)), xe)
        xj = jg[r].to_numpy(float)
        okr = en_ref & np.isfinite(xj)
        mu = float(np.average(xj[okr], weights=m[okr])) if okr.any() else np.nan
        xs = np.where(np.isfinite(xj), contraer(xj, m, mu, K_ESTILO), np.nan)
        jg[f"z_{r}"] = ecdf_z(xs[okr], m[okr], xs) if okr.sum() >= 3 else np.nan
    return eq, jg


# ============================================================================================ extras de equipo
# Tiempos muertos, posesiones defensivas (stops) y quintetos iniciales: misma definición que
# bbstats/lineups/equipo_extras.py (sitio general), leída del jugada a jugada normalizado (eventos/<liga>.csv.gz).
VENTANA_S = 120.0
RACHA = 6
_KIND = {"t2_anotado": ("shot", 2, True), "t2_fallado": ("shot", 2, False), "t3_anotado": ("shot", 3, True),
         "t3_fallado": ("shot", 3, False), "tl_anotado": ("ft", 1, True), "tl_fallado": ("ft", 1, False),
         "rebote_of": ("oreb", 0, None), "rebote_def": ("dreb", 0, None), "perdida": ("tov", 0, None),
         "robo": ("stl", 0, None), "tapon": ("blk", 0, None), "entra": ("in", 0, None), "sale": ("out", 0, None)}


def _plen(p: int, gmin: float) -> float:
    return gmin / 4 * 60 if p <= 4 else 300.0


def _pstart(p: int, gmin: float) -> float:
    q = gmin / 4 * 60
    return q * (p - 1) if p <= 5 else 4 * q + 300.0 * (p - 5)


def analizar_partido(ev: pd.DataFrame, teams: list[str], gmin: float, starters: dict) -> dict | None:
    from ..lineups.model import Event
    from ..lineups.possessions import count_possessions
    import bisect
    if len(teams) != 2 or ev.empty:
        return None
    a, b = teams
    rival = {a: b, b: a}
    evs, tos = [], []
    for r in ev.itertuples(index=False):
        tid = r.team_id if isinstance(r.team_id, str) else None
        if r.tipo == "tiempo_muerto":
            if tid in rival:
                tos.append((int(r.orden), int(r.periodo), float(r.t), tid))
            continue
        k = _KIND.get(r.tipo)
        if not k or tid is None:
            continue
        kind, val, made = k
        evs.append(Event(order=int(r.orden), period=int(r.periodo), t=float(r.t), kind=kind, team=tid,
                         player=r.player_id if isinstance(r.player_id, str) else None, made=made, value=val,
                         pts=val if made else 0))
    evs.sort(key=lambda e: e.order)
    pts = lambda e: e.pts if (e.made and e.kind in ("shot", "ft")) else 0  # noqa: E731
    score = {a: 0, b: 0}
    marcas = [(0.0, -1, 0, 0)]
    for e in evs:
        p = pts(e)
        if p and e.team in score:
            score[e.team] += p
            marcas.append((e.t, e.order, score[a], score[b]))
    ts = [m[0] for m in marcas]
    ords = [m[1] for m in marcas]

    def marcador_en(t):
        i = bisect.bisect_right(ts, t) - 1
        return marcas[max(i, 0)][2], marcas[max(i, 0)][3]

    def marcador_antes_de(order):
        i = bisect.bisect_left(ords, order) - 1
        return marcas[max(i, 0)][2], marcas[max(i, 0)][3]

    _, pid_of = count_possessions(evs, list(teams))
    pos: dict[int, dict] = {}
    for e in evs:
        pid = pid_of.get(e.order)
        if pid is None:
            continue
        d = pos.setdefault(pid, {"dueño": None, "pts": 0, "o0": e.order, "o1": e.order, "t0": e.t, "t1": e.t,
                                 "fin": None, "oreb": False})
        d["o1"], d["t1"] = e.order, e.t
        if d["dueño"] is None and e.kind in ("shot", "ft", "tov", "oreb"):
            d["dueño"] = e.team
        if e.kind == "oreb":
            d["oreb"] = True
        d["fin"] = e
    for e in evs:
        pid = pid_of.get(e.order)
        if pid is not None and pid in pos and pos[pid]["dueño"] == e.team:
            pos[pid]["pts"] += pts(e)
    stl, blk = defaultdict(list), defaultdict(list)
    for e in evs:
        if e.kind == "stl":
            stl[e.team].append(e.t)
        elif e.kind == "blk":
            blk[e.team].append(e.t)
    usados = set()
    for d in sorted(pos.values(), key=lambda d: d["o1"]):
        r = rival.get(d["dueño"])
        if r is None:
            continue
        f = d["fin"]
        if f is not None and f.kind == "tov":
            cand = [(abs(x - f.t), i) for i, x in enumerate(stl[r]) if (r, i) not in usados and abs(x - f.t) <= 3.0]
            if cand:
                usados.add((r, min(cand)[1]))
                d["stl"] = True
        if any(d["t0"] - 1.0 <= x <= d["t1"] + 1.0 for x in blk[r]):
            d["blk"] = True
    out = {}
    for t in teams:
        o = rival[t]
        dfn = Counter()
        for d in pos.values():
            if d["dueño"] == o:
                dfn["pos"] += 1
                dfn["pts"] += d["pts"]
                if d["oreb"]:
                    dfn["pos_oreb"] += 1
                if d["pts"] == 0:
                    dfn["stops"] += 1
                    f = d["fin"]
                    if f is not None and f.kind == "tov":
                        dfn["stop_robo" if d.get("stl") else "stop_perdida"] += 1
                    elif d.get("blk"):
                        dfn["stop_tapon"] += 1
                    else:
                        dfn["stop_fallo"] += 1
                    if d["oreb"]:
                        dfn["stop_tras_oreb"] += 1
            elif d["dueño"] == t:
                dfn["of_pos"] += 1
                dfn["of_pts"] += d["pts"]
        q = starters.get(t)
        out[t] = {"defensa": dict(dfn), "tiempos_muertos": [], "gana": (score[t] > score[o]) if score[t] != score[o] else None,
                  "quinteto_inicial": "|".join(sorted(q)) if q and len(q) == 5 else None}
    propias = sorted((d["o0"], d["t0"], d["pts"], d["dueño"]) for d in pos.values() if d["dueño"] is not None)
    for order, per, t_, t in tos:
        o = rival[t]
        idx = {a: 0, b: 1}
        sa = marcador_antes_de(order)
        ant = marcador_en(max(0.0, t_ - VENTANA_S))
        fin_p = _pstart(per, gmin) + _plen(per, gmin)
        fin_v = min(t_ + VENTANA_S, fin_p) if per >= 4 else t_ + VENTANA_S
        des = marcador_en(fin_v)
        pre = (sa[idx[t]] - ant[idx[t]]) - (sa[idx[o]] - ant[idx[o]])
        post = (des[idx[t]] - sa[idx[t]]) - (des[idx[o]] - sa[idx[o]])
        ato = next((p for p in propias if p[0] > order and p[3] == t), None)
        out[t]["tiempos_muertos"].append({
            "periodo": per, "restante_s": round(fin_p - t_, 1), "margen": sa[idx[t]] - sa[idx[o]],
            "parcial_antes": pre, "parcial_despues": post, "ventana_despues_s": round(fin_v - t_, 1),
            "ato_pts": ato[2] if ato is not None and ato[1] - t_ <= 30 else None})
    return out


def _agregar_extras(partidos: list[tuple[str, dict, bool]]) -> dict:
    sel = partidos
    dfn = Counter()
    for _, d, _ in sel:
        dfn.update(d["defensa"])
    tos = [x for _, d, con in sel if con for x in d["tiempos_muertos"]]
    n_con = sum(1 for _, _, con in sel if con)
    por_cuarto = Counter(min(x["periodo"], 5) for x in tos)
    racha = [x for x in tos if x["parcial_antes"] <= -RACHA]
    ato = [x["ato_pts"] for x in tos if x["ato_pts"] is not None]
    post = [x["parcial_despues"] for x in tos if x["ventana_despues_s"] >= 60]
    q_ini, q_gana = Counter(), Counter()
    for _, d, _ in sel:
        q = d["quinteto_inicial"]
        if q:
            q_ini[q] += 1
            q_gana[q] += 1 if d["gana"] else 0
    media = lambda v: round(sum(v) / len(v), 2) if v else None  # noqa: E731
    return {
        "partidos": len(sel),
        "tiempos_muertos": {
            "partidos_con_registro": n_con, "n": len(tos), "por_partido": round(len(tos) / n_con, 2) if n_con else None,
            "por_cuarto": [por_cuarto.get(i, 0) for i in (1, 2, 3, 4, 5)],
            "ultimos_2min": sum(1 for x in tos if x["periodo"] >= 4 and x["restante_s"] <= 120),
            "parcial_antes_medio": media([x["parcial_antes"] for x in tos]),
            "parcial_despues_medio": media([x["parcial_despues"] for x in tos if x["ventana_despues_s"] >= 60]),
            "tras_racha": len(racha),
            "racha_cortada": sum(1 for x in racha if x["parcial_despues"] >= 0 and x["ventana_despues_s"] >= 60),
            "racha_con_ventana": sum(1 for x in racha if x["ventana_despues_s"] >= 60),
            "racha_parcial_despues_medio": media([x["parcial_despues"] for x in racha if x["ventana_despues_s"] >= 60]),
            "ato_n": len(ato), "ato_pts": sum(ato), "ato_pts2": sum(x * x for x in ato),
            "post_n": len(post), "post_s": sum(post), "post_s2": sum(x * x for x in post),
            "margen_medio": media([x["margen"] for x in tos]),
            "con_ventaja": sum(1 for x in tos if x["margen"] > 0),
            "con_desventaja": sum(1 for x in tos if x["margen"] < 0)},
        "defensa": dict(dfn),
        "quintetos_iniciales": [{"unidad": q, "partidos": n, "victorias": q_gana[q]} for q, n in q_ini.most_common()],
    }


def extras_liga(L: Liga) -> dict:
    ev = L.EV
    if ev.empty:
        return {"liga": L.liga, "temporada": L.t, "partidos": 0, "partidos_con_tiempos_muertos": 0,
                "ventana_s": VENTANA_S, "racha": RACHA, "equipos": {}}
    P = L.P.set_index("game_id")
    bx = L.BX
    tit = bx[bx["titular"].astype(str).str.lower().eq("true")] if len(bx) else bx
    starters = defaultdict(dict)
    for (gid, tid), g in tit.groupby(["game_id", "team_id"]):
        starters[gid][tid] = list(g["player_id"])
    por_eq = defaultdict(list)
    n_part = n_to = 0
    for gid, g in ev.groupby("game_id", sort=False):
        if gid not in P.index:
            continue
        p = P.loc[gid]
        teams = [str(p["local_id"]), str(p["visitante_id"])]
        gmin = float(p["partido_min"]) if pd.notna(p.get("partido_min")) else 40.0
        g = g.sort_values("orden")
        try:
            d = analizar_partido(g, teams, gmin, starters.get(gid, {}))
        except Exception:  # noqa: BLE001 - un partido raro no detiene el resto
            continue
        if not d:
            continue
        n_part += 1
        con = bool((g["tipo"] == "tiempo_muerto").any())
        n_to += con
        for t, x in d.items():
            por_eq[t].append((gid, x, con))
    eqs = {}
    for t, v in sorted(por_eq.items()):
        a = _agregar_extras(v)
        eqs[t] = {"equipo": L.nombre_eq.get(t, t), "regular": a, "total": a}
    return {"liga": L.liga, "temporada": L.t, "partidos": n_part, "partidos_con_tiempos_muertos": n_to,
            "ventana_s": VENTANA_S, "racha": RACHA, "equipos": eqs}


# ============================================================================================ efectos X → Y
def efectos_liga(L: Liga, min_juntos: float = 45) -> pd.DataFrame:
    """Efectos dirigidos X → Y (bbmodel.interacciones.efectos_liga) con todos los partidos de la temporada: con Y en
    pista, Y con X en pista frente a Y sin X (cuota de tiro, eFG%, % asistidas, % en el aro, puntos/100)."""
    pt, ptr = L.qdir / "tiros.csv.gz", L.qdir / "tramos.csv.gz"
    if not pt.exists() or not ptr.exists():
        return pd.DataFrame()
    t = pd.read_csv(pt, dtype={"team_id": str, "player_id": str, "asistente_id": str, "quinteto": str},
                    usecols=["team_id", "player_id", "tipo", "anotado", "puntos", "asistente_id", "quinteto", "x", "y"])
    t = t[t["quinteto"].notna() & (t["quinteto"].str.count(r"\|") == 4)]
    if t.empty:
        return pd.DataFrame()
    t["anotado"] = t["anotado"].astype(str).str.lower().isin(["true", "1"])
    campo = t["tipo"].isin(["T2", "T3"])
    t["fga"] = campo.astype(float)
    t["fgm"] = (campo & t["anotado"]).astype(float)
    t["fg3m"] = ((t["tipo"] == "T3") & t["anotado"]).astype(float)
    t["fgm_asist"] = ((t["fgm"] > 0) & t["asistente_id"].notna() & (t["asistente_id"] != "")).astype(float)
    t["pts"] = pd.to_numeric(t["puntos"], errors="coerce").fillna(0) * t["anotado"]
    x, y = pd.to_numeric(t["x"], errors="coerce"), pd.to_numeric(t["y"], errors="coerce")
    d1 = np.hypot((x - 5.625) / 100 * 28, (y - 50) / 100 * 15)
    d2 = np.hypot((x - 94.375) / 100 * 28, (y - 50) / 100 * 15)
    t["aro"] = np.where(x.notna(), (np.minimum(d1, d2) < R_ARO).astype(float), np.nan) * t["fga"]
    t["team_id"] = t["team_id"].astype(str).map(lambda x: L.sid.get(x, x))
    eq = t.groupby(["team_id", "quinteto"])[["fga"]].sum().rename(columns={"fga": "fga_eq"})
    jug = t.groupby(["team_id", "quinteto", "player_id"])[["fga", "fgm", "fg3m", "fgm_asist", "pts", "aro"]].sum()
    tr = pd.read_csv(ptr, dtype={"team_a": str, "team_b": str, "quinteto_a": str, "quinteto_b": str})
    for c in ("team_a", "team_b"):
        tr[c] = tr[c].astype(str).map(lambda x: L.sid.get(x, x))
    pos = []
    for lado in ("a", "b"):
        p = tr[f"{lado}_fga"] - tr[f"{lado}_oreb"] + tr[f"{lado}_tov"] + 0.44 * tr[f"{lado}_fta"]
        pos.append(pd.DataFrame({"team_id": tr[f"team_{lado}"], "quinteto": tr[f"quinteto_{lado}"], "poss": p, "sec": tr["sec"]}))
    pos = pd.concat(pos).groupby(["team_id", "quinteto"])[["poss", "sec"]].sum()
    filas = []
    for team, lq in pos.reset_index().groupby("team_id"):
        lq = lq.set_index("quinteto")
        lq = lq.join(eq.loc[team] if team in eq.index.get_level_values(0) else pd.DataFrame(columns=["fga_eq"]))
        lq["fga_eq"] = lq["fga_eq"].fillna(0)
        miembros = {q: set(str(q).split("|")) for q in lq.index}
        jugadores = sorted(set().union(*miembros.values()))
        try:
            jt = jug.loc[team]
        except KeyError:
            continue
        for yy in jugadores:
            qs_y = [q for q in lq.index if yy in miembros[q]]
            if not qs_y:
                continue
            sub = lq.loc[qs_y]
            jy = jt[jt.index.get_level_values("player_id") == yy].droplevel("player_id").reindex(qs_y).fillna(0)
            for xx in jugadores:
                if xx == yy:
                    continue
                con = np.array([xx in miembros[q] for q in qs_y])
                c = {}
                for etq, m in (("con", con), ("sin", ~con)):
                    ss, jj = sub[m], jy[m]
                    c[f"sec_{etq}"] = ss["sec"].sum()
                    c[f"poss_{etq}"] = ss["poss"].sum()
                    c[f"fga_eq_{etq}"] = ss["fga_eq"].sum()
                    for k in ("fga", "fgm", "fg3m", "fgm_asist", "pts", "aro"):
                        c[f"{k}_{etq}"] = jj[k].sum()
                if c["sec_con"] < min_juntos * 60 or c["sec_sin"] < 20 * 60:
                    continue
                filas.append({"team_id": team, "y": yy, "x": xx, **c})
    d = pd.DataFrame(filas)
    if d.empty:
        return d
    for e in ("con", "sin"):
        fga = d[f"fga_{e}"].where(d[f"fga_{e}"] > 0)
        d[f"cuota_tiro_{e}"] = 100 * d[f"fga_{e}"] / d[f"fga_eq_{e}"].where(d[f"fga_eq_{e}"] > 0)
        d[f"efg_{e}"] = 100 * (d[f"fgm_{e}"] + 0.5 * d[f"fg3m_{e}"]) / fga
        d[f"pct_asistidas_{e}"] = 100 * d[f"fgm_asist_{e}"] / d[f"fgm_{e}"].where(d[f"fgm_{e}"] > 0)
        d[f"pct_aro_{e}"] = 100 * d[f"aro_{e}"] / fga
        d[f"pts100_{e}"] = 100 * d[f"pts_{e}"] / d[f"poss_{e}"].where(d[f"poss_{e}"] > 0)
    for k in ("cuota_tiro", "efg", "pct_asistidas", "pct_aro", "pts100"):
        d[f"d_{k}"] = d[f"{k}_con"] - d[f"{k}_sin"]
    if not L.J["registra_asistencias"].astype(str).str.lower().eq("true").any():
        d["d_pct_asistidas"] = np.nan
    return d


# ============================================================================================ construcción por liga
UNIDAD = ["fase", "gp", "min", "poss", "pts_for", "pts_against", "plus_minus", "ortg", "drtg", "net_rtg",
          "net_rtg_aj", "net_rtg_suerte", "ritmo", "efg_pct", "opp_efg_pct", "tov_pct", "opp_tov_pct", "oreb_pct",
          "dreb_pct", "ft_rate", "opp_ft_rate", "fg3a_rate", "opp_fg3a_rate", "ast_pct", "min_clutch", "min_basura"]
Q_EXTRA = ["rapm_suma", "net_esperado", "sinergia"]
T_EXTRA = ["net_esperado", "sinergia_rapm"]
P_COLS = ["fase", "min", "poss", "ortg", "drtg", "net_rtg", "net_rtg_aj", "min_a_sin_b", "net_rtg_aj_a_sin_b",
          "min_b_sin_a", "net_rtg_aj_b_sin_a", "min_ninguno", "net_rtg_aj_ninguno", "sinergia", "sinergia_rapm",
          "net_esperado", "pct_min_a_con_b", "pct_min_b_con_a", "ast_a_a_b", "ast_b_a_a"]
J_COLS = ["fase", "gp", "min_on", "poss_on", "min_pct_equipo", "quintetos_distintos", "titular_partidos",
          "cierra_partidos", "relevos_por_partido", "min_por_relevo", "pct_min_q1", "pct_min_q2", "pct_min_q3",
          "pct_min_q4", "pct_min_prorroga", "net_rtg_on", "net_rtg_off", "net_rtg_onoff", "net_rtg_aj_onoff",
          "net_rtg_suerte_onoff", "ortg_onoff", "drtg_onoff", "efg_pct_onoff", "opp_efg_pct_onoff", "tov_pct_onoff",
          "opp_tov_pct_onoff", "oreb_pct_onoff", "dreb_pct_onoff", "ritmo_onoff", "clutch_min", "clutch_net_rtg",
          "basura_min", "net_rtg_onoff_sin_basura", "orapm", "drapm", "rapm", "rapm_poss", "ast_dadas",
          "ast_recibidas", "pct_canastas_asistidas", "pts_generados_asist", "socios_asistencia", "hhi_asistencias",
          "pagerank_asistencias"]
ZONAS = ["aro", "corta", "media", "t3_esquina", "t3_frontal"]
EU_IDS = ["pistons", "isolation", "old_school", "spacing", "circulacion", "pintura"]


def _dos_fases(df: pd.DataFrame) -> pd.DataFrame:
    """La temporada completa como «regular» y como «total» (mismo contenido)."""
    if df.empty:
        return df
    a = df.copy()
    a["fase"] = "regular"
    b = df.copy()
    b["fase"] = "total"
    return pd.concat([a, b], ignore_index=True)


class Temporada:
    """Todas las ligas vascas de una temporada con sus derivados (nivel, posición, estilos, pista, extras)."""

    def __init__(self, t: str, mz: dict):
        self.t = t
        self.ligas: dict[str, Liga] = {}
        self.der: dict[str, dict] = {}
        for liga in LIGAS:
            if not (PROC / t / "jugadores" / f"{liga}.csv").exists():
                continue
            L = Liga(t, liga)
            if L.J.empty or L.E.empty:
                continue
            self.ligas[liga] = L
            zon = zonas_jugador(L)
            nk = nivel_kerno(L.J)
            pos = posiciones(L.J)
            re_, rj = rasgos_equipo(L, zon), rasgos_jugador(L, zon)
            eq, jg = puntuar(re_, rj)
            zc = [f"z_{r}" for r in RASGOS]
            Pe = posterior(mz["medias"], mz["covs"], mz["pesos"], eq[zc].to_numpy(float))
            Pj = posterior(mz["medias"], mz["covs"], mz["pesos"], jg[zc].to_numpy(float))
            Pj[(jg["min"].to_numpy(float) < 40)] = np.nan
            nombres = [e["nombre"] for e in mz["estilos"]]
            self.der[liga] = {"zon": zon, "nk": nk, "pos": pos, "req": eq, "rjg": jg, "Pe": Pe, "Pj": Pj,
                              "eu_e": etiqueta(Pe, nombres, mz["asignacion"]),
                              "eu_j": etiqueta(Pj, nombres, mz["asignacion"])}

    # ---------------------------------------------------------------- quintetos/datos/<t>/<liga>
    def quintetos(self, liga: str) -> dict:
        L, D = self.ligas[liga], self.der[liga]
        jug = L.QJ.copy()
        J = L.J.join(D["nk"]).assign(pos3=D["pos"])
        # catálogo de jugadores: todos los de la liga (caja), ordenados por minutos
        base = J.sort_values("min", ascending=False).drop_duplicates(["player_id"])
        pids = list(dict.fromkeys(list(base["player_id"]) + (list(jug["player_id"]) if len(jug) else [])))
        pix = {p: i for i, p in enumerate(pids)}
        info = base.set_index("player_id")
        rapm = info["pbp_rapm"] if "pbp_rapm" in info else pd.Series(dtype=float)
        rv = rapm.dropna()
        cat = pd.DataFrame({"player_id": pids})
        cat["nombre"] = [titulo(info["nombre"].get(p, "")) if p in info.index else
                         titulo(jug.loc[jug["player_id"] == p, "nombre"].iloc[0]) for p in pids]
        cat["team_id"] = [info["team_id"].get(p) if p in info.index else jug.loc[jug["player_id"] == p, "team_id"].iloc[0]
                          for p in pids]
        cat["L"] = [info["L"].get(p) if p in info.index else None for p in pids]
        cat["estilo"] = None
        cat["p_estilo"] = None
        cat["pos3"] = [info["pos3"].get(p) if p in info.index else None for p in pids]
        cat["edad"] = None
        cat["rapm_el"] = [rapm.get(p) for p in pids]
        cat["orapm_el"] = [info["pbp_orapm"].get(p) if p in info.index else None for p in pids]
        cat["drapm_el"] = [info["pbp_drapm"].get(p) if p in info.index else None for p in pids]
        cat["rapm_pct_el"] = [(float((rv < rapm.get(p)).mean()) if pd.notna(rapm.get(p)) and len(rv) else None) for p in pids]
        cat["nk"] = [info["nk"].get(p) if p in info.index else None for p in pids]
        cat["nk_lo"] = [info["nk_lo"].get(p) if p in info.index else None for p in pids]
        cat["nk_hi"] = [info["nk_hi"].get(p) if p in info.index else None for p in pids]
        cat["imp"] = [info["imp"].get(p) if p in info.index else None for p in pids]
        cat["prod"] = [info["prod"].get(p) if p in info.index else None for p in pids]
        cat["division"] = [L.division.get(str(t)) for t in cat["team_id"]]
        out = {"liga": liga, "nombre_liga": NOMBRE[liga], "temporada": self.t,
               "estilos_nombres": None, "equipos_nombre": L.nombre_eq,
               "jugadores": tabla_cf(cat, list(cat.columns), {"L": 3, "rapm_pct_el": 3, "nk": 1, "nk_lo": 1, "nk_hi": 1,
                                                              "imp": 1, "prod": 1})}
        if len(jug):
            on = jug.copy()
            on["j"] = on["player_id"].map(pix)
            zon = D["zon"]
            if len(zon):
                on = on.merge(zon[["team_id", "player_id"] + [f"{a}_{z}" for z in ZONAS for a in ("fga", "fgm")]],
                              on=["team_id", "player_id"], how="left")
            on = _dos_fases(on)
            cols = ["j", "team_id"] + [c for c in J_COLS if c in on] + [f"{a}_{z}" for z in ZONAS for a in ("fga", "fgm") if f"{a}_{z}" in on]
            out["on_off"] = tabla_cf(on, list(dict.fromkeys(cols)), {"pagerank_asistencias": 4})
        if len(L.QE):
            e = _dos_fases(L.QE)
            out["equipos"] = tabla_cf(e, [c for c in e.columns if c not in ("division",)])
        idx_u = lambda u: [pix.get(p, -1) for p in str(u).split("|")]  # noqa: E731
        if len(L.Q5):
            q = L.Q5[L.Q5["min"] >= 5].copy()     # ligas cortas: 5 minutos (el sitio general usa 10)
            q["u"] = q["unidad"].map(idx_u)
            q = _dos_fases(q)
            out["quintetos"] = tabla_cf(q, ["team_id", "u"] + [c for c in UNIDAD + Q_EXTRA if c in q])
        if len(L.Q3):
            t3 = L.Q3.sort_values("min", ascending=False).groupby("team_id").head(20).copy()
            t3["u"] = t3["unidad"].map(idx_u)
            t3 = _dos_fases(t3)
            out["trios"] = tabla_cf(t3, ["team_id", "u"] + [c for c in UNIDAD + T_EXTRA if c in t3])
        if len(L.Q2):
            p = L.Q2[L.Q2["min"] >= 40].copy()
            p["a"] = p["jugador_a_id"].map(pix)
            p["b"] = p["jugador_b_id"].map(pix)
            p = _dos_fases(p[p["a"].notna() & p["b"].notna()])
            out["parejas"] = tabla_cf(p, ["team_id", "a", "b"] + [c for c in P_COLS if c in p])
        if len(L.QA):
            a = L.QA[L.QA["ast"] >= 2].copy()
            a["p"] = a["pasador_id"].map(pix)
            a["r"] = a["receptor_id"].map(pix)
            a = _dos_fases(a[a["p"].notna() & a["r"].notna()])
            out["asistencias"] = tabla_cf(a, ["team_id", "fase", "p", "r", "ast", "ast_2", "ast_3", "ast_tl",
                                              "pts_asistidos", "min_juntos", "ast_por40_juntos"])
        ef = efectos_liga(L)
        if len(ef):
            ef["xi"] = ef["x"].map(pix)
            ef["yi"] = ef["y"].map(pix)
            ef = ef[ef["xi"].notna() & ef["yi"].notna()]
        D["efectos"] = ef
        out["efectos"] = tabla_cf(ef, ["team_id", "xi", "yi", "fga_con", "fga_sin", "sec_con", "d_cuota_tiro", "d_efg",
                                       "d_pct_asistidas", "d_pct_aro", "d_pts100"], {"sec_con": 0}) if len(ef) else \
            {"c": ["team_id", "xi", "yi", "fga_con", "fga_sin", "sec_con", "d_cuota_tiro", "d_efg", "d_pct_asistidas",
                   "d_pct_aro", "d_pts100"], "f": []}
        if len(L.QV):
            v = L.QV
            cq = v["con_quintetos"].astype(str).str.lower() == "true" if "con_quintetos" in v else pd.Series(True, index=v.index)
            # validado = +/- reconstruido igual al del acta (partidos.quintetos_validos): el acta da minutos enteros
            qv = L.P.set_index("game_id")["quintetos_validos"].astype(str).str.lower().eq("true")
            val = v["game_id"].astype(str).map(qv).fillna(False)
            out["cobertura"] = {"partidos": int(len(v)), "con_quintetos": int(cq.sum()),
                                "validados": int(val[cq].sum()),
                                "usados": int((v["usado_en_quintetos"].astype(str).str.lower() == "true").sum()) if "usado_en_quintetos" in v else int(cq.sum()),
                                "pm_oficial_incoherente": int((v.get("pm_oficial_coherente", pd.Series(True, index=v.index)).astype(str).str.lower() == "false").sum())}
        else:
            n = int(L.P["con_acta"].astype(str).str.lower().eq("true").sum())
            out["cobertura"] = {"partidos": n, "con_quintetos": 0, "validados": 0, "usados": 0, "pm_oficial_incoherente": 0}
        return out

    # ---------------------------------------------------------------- fila de equipos.gz.txt
    def filas_equipos(self, liga: str) -> tuple[list[dict], dict, dict]:
        L, D = self.ligas[liga], self.der[liga]
        J = L.J.join(D["nk"]).assign(pos3=D["pos"])
        f = lambda r, c: pd.to_numeric(r.get(c), errors="coerce")  # noqa: E731
        filas, plant, clubes = [], {}, {}
        co = L.coaches()
        Pe = D["Pe"]
        eu = dict(zip(D["req"].index, D["eu_e"]))
        Pdict = dict(zip(D["req"].index, Pe))
        prov = self.t == max(temporadas())
        gpv = pd.to_numeric(L.E["gp"], errors="coerce")
        umbral = max(2.0, 0.25 * float(gpv.median())) if len(gpv) else 2.0
        for _, r in L.E[gpv >= umbral].iterrows():
            tid = str(r["team_id"])
            k = f"{liga}:{tid}:{self.t}"
            poss, oposs = f(r, "team_poss"), f(r, "opp_poss")
            fga, fgm, fg3a, fg3m = f(r, "team_fga"), f(r, "team_fgm"), f(r, "team_fg3a"), f(r, "team_fg3m")
            ofga, ofgm, ofg3a, ofg3m = f(r, "opp_fga"), f(r, "opp_fgm"), f(r, "opp_fg3a"), f(r, "opp_fg3m")
            fg2a, fg2m, ofg2a, ofg2m = fga - fg3a, fgm - fg3m, ofga - ofg3a, ofgm - ofg3m
            reg_ast = J.loc[J["team_id"] == tid, "registra_asistencias"].astype(str).str.lower().eq("true").any()
            reg_blk = J.loc[J["team_id"] == tid, "registra_tapones"].astype(str).str.lower().eq("true").any()
            pc = lambda a, b: float(100 * a / b) if b and b > 0 and pd.notna(a) else None  # noqa: E731
            base = {"t": self.t, "liga": liga, "id": tid, "k": k, "eq": titulo(r["equipo"]), "gp": f(r, "gp"),
                    "w": f(r, "w"), "l": f(r, "l"), "wl": "oficial", "pts": f(r, "team_pts"), "opts": f(r, "opp_pts_y"),
                    "poss": poss, "ritmo": f(r, "team_pace"), "ortg": f(r, "team_ortg"), "drtg": f(r, "team_drtg"),
                    "net": f(r, "team_netrtg"), "efg": f(r, "efg_pct"), "oefg": f(r, "opp_efg_pct"),
                    "tov": pc(f(r, "team_tov"), poss), "otov": pc(f(r, "opp_tov"), oposs),
                    "orb": f(r, "oreb_pct"), "drb": f(r, "dreb_pct"), "ftr": pc(f(r, "team_fta"), fga),
                    "oftr": pc(f(r, "opp_fta"), ofga), "t3r": pc(fg3a, fga), "ot3r": pc(ofg3a, ofga),
                    "t3": pc(fg3m, fg3a), "ot3": pc(ofg3m, ofg3a), "t2": pc(fg2m, fg2a), "ot2": pc(ofg2m, ofg2a),
                    "tl": pc(f(r, "team_ftm"), f(r, "team_fta")),
                    "astr": pc(f(r, "team_ast"), fgm) if reg_ast else None, "oastr": pc(f(r, "opp_ast"), ofgm) if reg_ast else None,
                    "stl": pc(f(r, "team_stl"), oposs), "blk": pc(f(r, "team_blk"), ofg2a) if reg_blk else None}
            for fz in FASES:
                filas.append({**base, "f": fz})
            # plantilla: jugadores con 100+ minutos (o los 10 con más minutos al principio de la temporada)
            js = J[J["team_id"] == tid].sort_values("min", ascending=False)
            jj = js[js["min"] >= 100]
            if len(jj) < 5:
                jj = js.head(10)
            ek = {pid: (u, p) for pid, u, p in zip(L.J["player_id"], D["eu_j"], D["Pj"])}
            w = jj["min"].astype(float)
            Lpl = float(np.average(jj["L"], weights=w)) if len(jj) and jj["L"].notna().any() and w[jj["L"].notna()].sum() > 0 else None
            if Lpl is not None:
                ok_ = jj["L"].notna()
                Lpl = float(np.average(jj.loc[ok_, "L"], weights=w[ok_]))
            plant[k] = {"L": _num(Lpl, 4), "edad": None, "n": int((js["min"] >= 100).sum()),
                        "j": [[titulo(x.nombre), x.pos3, None, _num(x["min"], 0), _num(x.L, 3),
                               (ek.get(x.player_id, (None,))[0] or [None])[0], (ek.get(x.player_id, (None,))[0] or [None, None])[1]]
                              for _, x in jj.iterrows()]}
            u = eu.get(tid)
            probs = Pdict.get(tid)
            nent = co.get(tid, [])
            gp = int(f(r, "gp") or 0)
            jp = L.P[((L.P["local_id"] == tid) | (L.P["visitante_id"] == tid)) & L.P["pts_local"].notna()]
            fechas = jp["fecha"].dropna().sort_values()
            de, a_ = (fechas.iloc[0], fechas.iloc[-1]) if len(fechas) else (None, None)
            ent = []
            if nent:
                ent.append({"n": " · ".join(nent), "id": slug(nent[0]), "pj": gp, "pr": gp, "pp": 0, "de": de, "a": a_,
                            "w": _num(f(r, "w")), "l": _num(f(r, "l")), "int": 0, "met": "club_unico" if len(nent) == 1 else "licencias",
                            "L": _num(Lpl, 3), "e": u[0] if u else None, "p": u[1] if u else None,
                            "probs": [round(float(x), 3) for x in probs] if probs is not None and np.isfinite(probs).all() else None,
                            "xyz": None})
            clubes[k] = {"club": f"{liga}:{tid}", "nom": titulo(r["equipo"]), "e": u[0] if u else None, "p": u[1] if u else None,
                         "probs": [round(float(x), 3) for x in probs] if probs is not None and np.isfinite(probs).all() else None,
                         "rob": None, "xyz": None, "prov": prov, "ent": ent, "division": L.division.get(tid),
                         "club_nombre": titulo(r.get("club") or "")}
        return filas, plant, clubes

    # ---------------------------------------------------------------- tabla de jugadores del armazón (Nivel Kerno y ficha)
    def jugadores_sitio(self) -> dict:
        cols = ["liga", "team_id", "equipo", "division", "player_id", "nombre", "pos3", "gp", "min", "min_pg", "pts_pg",
                "reb_pg", "nk", "nk_lo", "nk_hi", "prod", "imp", "imp_lo", "imp_hi", "L", "eu", "eu_i", "eu_p",
                "per", "ws_per_40", "gs40", "pie", "ortg", "drtg", "pts_p100", "ts_pct", "efg_pct", "fg2_pct", "fg3_pct",
                "ft_pct", "fta_rate", "fg3a_rate", "usg_pct", "ast_pct", "tov_pct", "oreb_pct", "dreb_pct", "stl_pct",
                "blk_pct", "pf_p100", "rapm", "orapm", "drapm", "onoff", "pct_aro", "pct_corta", "pct_media",
                "pct_t3_esquina", "pct_t3_frontal", "clutch_pts", "registra_asistencias", "registra_tapones"]
        fr = []
        for liga, L in self.ligas.items():
            D = self.der[liga]
            J = L.J.join(D["nk"]).assign(pos3=D["pos"])
            J["liga"] = liga
            J["equipo"] = J["team_id"].map(L.nombre_eq).fillna(J["equipo"].map(titulo))
            J["nombre"] = J["nombre"].map(titulo)
            J["division"] = J["team_id"].map(L.division)
            m = pd.to_numeric(J["min"], errors="coerce")
            J["gs40"] = _div(pd.to_numeric(J["game_score_pg"], errors="coerce") * pd.to_numeric(J["gp"], errors="coerce") * 40, m)
            J["rapm"], J["orapm"], J["drapm"] = J["pbp_rapm"], J["pbp_orapm"], J["pbp_drapm"]
            J["onoff"] = J["pbp_net_rtg_aj_onoff"]
            eu = D["eu_j"]
            J["eu"] = [u[2] if u else None for u in eu]
            J["eu_i"] = [u[0] if u else None for u in eu]
            J["eu_p"] = [u[1] if u else None for u in eu]
            z = D["zon"].set_index(["team_id", "player_id"]) if len(D["zon"]) else None
            k = pd.MultiIndex.from_frame(J[["team_id", "player_id"]])
            for zz in ["aro", "corta", "media", "t3_esquina", "t3_frontal"]:
                J[f"pct_{zz}"] = 100 * _div(z[f"fga_{zz}"].reindex(k).to_numpy(float), z["fga_pbp"].reindex(k).to_numpy(float)) if z is not None else np.nan
            for c in ("registra_asistencias", "registra_tapones"):
                J[c] = J[c].astype(str).str.lower().eq("true")
            fr.append(J[[c for c in cols if c in J]])
        d = pd.concat(fr, ignore_index=True) if fr else pd.DataFrame(columns=cols)
        d = d[pd.to_numeric(d["min"], errors="coerce") > 0]
        return {"temporada": self.t, **tabla_cols(d, {"nk": 1, "nk_lo": 1, "nk_hi": 1, "prod": 1, "imp": 1, "imp_lo": 1,
                                                       "imp_hi": 1, "L": 3, "eu_p": 3, "min": 1})}

    # ---------------------------------------------------------------- estilos unificados (clubes y jugadores)
    def estilos(self, liga: str) -> tuple[dict, dict]:
        L, D = self.ligas[liga], self.der[liga]
        c, j = {}, {}
        eu = dict(zip(D["req"].index, D["eu_e"]))
        Pd = dict(zip(D["req"].index, D["Pe"]))
        ek = {(t, p): u for t, p, u in zip(L.J["team_id"], L.J["player_id"], D["eu_j"])}
        co = L.coaches()
        for tid in L.E["team_id"].astype(str):
            k = f"{liga}:{tid}:{self.t}"
            u = eu.get(tid)
            pr = Pd.get(tid)
            js = L.J[L.J["team_id"] == tid].sort_values("min", ascending=False)
            jj = js[js["min"] >= 100]
            if len(jj) < 5:
                jj = js.head(10)
            ent = {}
            if co.get(tid) and u:
                ent[slug(co[tid][0])] = [u[0], u[1], u[2], [round(float(x), 3) for x in pr]]
            c[k] = {"u": u, "pr": [round(float(x), 3) for x in pr] if pr is not None and np.isfinite(pr).all() else None,
                    "ent": ent, "pl": [ek.get((tid, p)) for p in jj["player_id"]]}
        for (t, p), u in ek.items():
            if u:
                j[f"{liga}|{self.t}|{t}|{p}"] = u
        return c, j


# ============================================================================================ escalas (0–100)
def _q101(v: np.ndarray, w: np.ndarray | None = None) -> list:
    v = np.asarray(v, float)
    ok = np.isfinite(v)
    if ok.sum() < 5:
        return []
    v = v[ok]
    if w is None:
        return [round(float(x), 3) for x in np.percentile(v, np.linspace(0, 100, 101))]
    w = np.asarray(w, float)[ok]
    o = np.argsort(v)
    v, w = v[o], w[o]
    c = (np.cumsum(w) - 0.5 * w) / w.sum()
    return [round(float(x), 3) for x in np.interp(np.linspace(0, 1, 101), c, v)]


def _dt(v, w=None) -> float:
    v = np.asarray(v, float)
    ok = np.isfinite(v)
    if ok.sum() < 3:
        return 1.0
    w = np.ones(ok.sum()) if w is None else np.asarray(w, float)[ok]
    m = np.average(v[ok], weights=w)
    return float(math.sqrt(np.average((v[ok] - m) ** 2, weights=w))) or 1.0


def escalas(Ts: dict[str, Temporada]) -> dict:
    """Bloque de escalas con la misma forma que el del sitio general, medido en las ligas vascas: la referencia de cada
    familia es su propia liga (0 = media de su liga) y la vara (DT), la dispersión del conjunto de ligas vascas."""
    acc = defaultdict(list)
    for t, T in Ts.items():
        for liga, L in T.ligas.items():
            D = T.der[liga]
            J = L.J.join(D["nk"])
            m = pd.to_numeric(J["min"], errors="coerce").fillna(0).to_numpy(float)
            sel = m >= 100
            for fam, col in (("nivel", "L"), ("rapm", "pbp_rapm"), ("orapm", "pbp_orapm"), ("drapm", "pbp_drapm")):
                acc[fam].append((J[col].to_numpy(float)[sel], m[sel]))
            for fam, col in (("rapm_liga", "pbp_rapm"), ("orapm_liga", "pbp_orapm"), ("drapm_liga", "pbp_drapm")):
                acc[fam].append((J[col].to_numpy(float)[sel], m[sel]))
            if len(L.QJ):
                q = L.QJ[pd.to_numeric(L.QJ["poss_on"], errors="coerce") >= 200]
                acc["onoff"].append((q["net_rtg_aj_onoff"].to_numpy(float), q["poss_on"].to_numpy(float)))
            if len(L.QE):
                acc["net_equipo"].append((L.QE["net_rtg"].to_numpy(float), L.QE["poss"].to_numpy(float)))
            if len(L.Q5):
                q = L.Q5[L.Q5["poss"] >= 50]
                acc["net_quinteto"].append((q["net_rtg_aj"].to_numpy(float), q["poss"].to_numpy(float)))
                if "sinergia" in q:
                    acc["sinergia_quinteto"].append((q["sinergia"].to_numpy(float), q["poss"].to_numpy(float)))
            if len(L.Q3):
                q = L.Q3[L.Q3["poss"] >= 100]
                acc["net_trio"].append((q["net_rtg_aj"].to_numpy(float), q["poss"].to_numpy(float)))
            if len(L.Q2):
                q = L.Q2[L.Q2["poss"] >= 150]
                acc["net_pareja"].append((q["net_rtg_aj"].to_numpy(float), q["poss"].to_numpy(float)))
                for fam, col in (("sinergia_pareja", "sinergia"), ("sinergia_rapm", "sinergia_rapm")):
                    if col in q:
                        acc[fam].append((q[col].to_numpy(float), q["poss"].to_numpy(float)))
            ef = D.get("efectos")
            if ef is not None and len(ef):
                for fam in ("d_cuota_tiro", "d_efg", "d_pct_asistidas", "d_pct_aro", "d_pts100"):
                    acc[fam].append((ef[fam].to_numpy(float), ef["sec_con"].to_numpy(float)))
    NOM = {"nivel": ("Nivel Kerno", "desviaciones típicas de su liga"), "rapm": ("RAPM", "pts/100 en su liga"),
           "orapm": ("ORAPM", "pts/100 en su liga"), "drapm": ("DRAPM", "pts/100 en su liga"),
           "rapm_liga": ("RAPM en su liga", "pts/100"), "orapm_liga": ("ORAPM en su liga", "pts/100"),
           "drapm_liga": ("DRAPM en su liga", "pts/100"), "onoff": ("On/off", "pts/100"),
           "net_equipo": ("Net de equipo", "pts/100"), "net_quinteto": ("Net de quinteto", "pts/100"),
           "sinergia_quinteto": ("Sinergia de quinteto", "pts/100 sobre lo esperado por el RAPM"),
           "net_trio": ("Net de trío", "pts/100"), "net_pareja": ("Net de pareja", "pts/100"),
           "sinergia_pareja": ("Sinergia de pareja (WOWY)", "pts/100"), "sinergia_rapm": ("Sinergia frente al RAPM", "pts/100"),
           "d_cuota_tiro": ("Efecto X → Y: cuota de tiro", "pp"), "d_efg": ("Efecto X → Y: eFG%", "pp"),
           "d_pct_asistidas": ("Efecto X → Y: % asistidas", "pp"), "d_pct_aro": ("Efecto X → Y: % en el aro", "pp"),
           "d_pts100": ("Efecto X → Y: puntos/100", "pts/100")}
    fams = {}
    temps = sorted(Ts)
    for fam, (nom, uni) in NOM.items():
        if not acc.get(fam):
            continue
        v = np.concatenate([a for a, _ in acc[fam]])
        w = np.concatenate([b for _, b in acc[fam]])
        ok = np.isfinite(v) & (w > 0)
        mu = float(np.average(v[ok], weights=w[ok])) if ok.any() else 0.0
        f = {"nombre": nom, "unidad": uni, "dt": round(_dt(v, w), 4), "ref_defecto": 0.0 if fam != "onoff" else round(mu, 4),
             "media_el": round(mu, 4), "q_el": _q101(v, w), "n": int(ok.sum()),
             "fuente": "ligas vascas (Federación Vasca), todas las temporadas con jugada a jugada, ponderado por minutos o posesiones"}
        if fam == "nivel":
            f["dt"] = 1.0
            f["ref"] = {t: 0.0 for t in temps}
            f["ligas"] = {t: {l: 0.0 for l in Ts[t].ligas} for t in temps}
        fams[fam] = f
    return {"version": 1, "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "formula": "S = 100·tanh(z/2), z = (valor − media de su liga) / DT de las ligas vascas", "referencia": "su liga",
            "factor": 2, "familias": fams}


# ============================================================================================ salida
def exportar(salida: str | Path | None = None, log=print) -> Path:
    out = Path(salida) if salida else SALIDA
    mz = cargar_mezcla()
    temps = temporadas()
    Ts: dict[str, Temporada] = {}
    for t in temps:
        Ts[t] = Temporada(t, mz)
        log(f"{t}: {', '.join(Ts[t].ligas)}")
    qd = out / "quintetos" / "datos"
    indice = {"generado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "temporadas": {}}
    filas, plant, clubes, euc, euj = [], {}, {}, {}, {}
    for t in sorted(temps, reverse=True):
        T = Ts[t]
        for liga in T.ligas:
            q = T.quintetos(liga)
            n = escribir(qd / t / f"{liga}.gz.txt", q)
            x = extras_liga(T.ligas[liga])
            escribir(qd / t / f"{liga}.extras.gz.txt", x)
            indice["temporadas"].setdefault(t, {})[liga] = {"nombre": NOMBRE[liga], "bytes": n, "quintetos": bool(q.get("quintetos")),
                                                            "cobertura": q.get("cobertura")}
            fz, pz, cz = T.filas_equipos(liga)
            filas += fz
            plant.update(pz)
            clubes.update(cz)
            c, j = T.estilos(liga)
            euc.update(c)
            euj.update(j)
            log(f"  {t} {liga}: {n / 1024:.0f} KB · {len(x['equipos'])} equipos con extras")
    indice["escalas"] = escalas(Ts)
    escribir(qd / "indice.json", indice, claro=True)
    cols = ["t", "f", "liga", "id", "k", "eq", "gp", "w", "l", "wl", "pts", "opts", "poss", "ritmo", "ortg", "drtg", "net",
            "efg", "oefg", "tov", "otov", "orb", "drb", "ftr", "oftr", "t3r", "ot3r", "t3", "ot3", "t2", "ot2", "tl", "astr",
            "oastr", "stl", "blk"]
    F = pd.DataFrame(filas)[cols]
    eq = {"generado": indice["generado"], "temporadas": sorted(temps), "conv_nivel_club": {"a": 0.0, "b": 1.0, "r": 1.0},
          **tabla_cols(F), "plantillas": plant, "clubes": clubes}
    escribir(qd / "equipos.gz.txt", eq)
    est = mz["json"]["estilos"]
    escribir(out / "quintetos" / "estilos_unificados_clubes.gz.txt",
             {"estilos": est, "generado": indice["generado"], "c": euc,
              "nota": "Estilo unificado por club-temporada (clave liga:club:temporada), por entrenador y por jugador de la "
                      "plantilla, con los rasgos medidos frente a su liga vasca y la mezcla del sitio general."})
    escribir(out / "quintetos" / "estilos_unificados.gz.txt",
             {"estilos": [{k: e.get(k) for k in ("id", "nombre", "definicion", "jugador", "rol_jugador", "equipo", "color")} for e in est],
              "generado": indice["generado"], "j": euj})
    for t, T in Ts.items():
        escribir(out / "datos" / "kerno" / f"{t}.json", T.jugadores_sitio())
    meta, clubes, jugadores, br = atlas(Ts, mz, indice["escalas"])
    for n, o in (("meta.json", meta), ("clubes.json", clubes), ("jugadores.json", jugadores), ("brutos.json", br)):
        escribir(out / "atlas" / "estilos" / n, o)
    log(f"escrito {out}")
    return out


# ============================================================================================ Atlas (estilos e informe)
CORTO_R = {"ritmo": "Ritmo", "triple": "3PAr", "esquina": "Esquina", "aro": "Aro", "tiros_libres": "FTr",
           "autocreacion": "Sin asistencia", "asistencia": "AST%", "reb_ofensivo": "Reb. of.", "perdidas": "TOV%",
           "robos": "Robos", "tapones": "Tapones", "faltas": "Faltas"}
BLOQUE_R = {"ritmo": "Estructura", "triple": "Ataque", "esquina": "Ataque", "aro": "Ataque", "tiros_libres": "Ataque",
            "autocreacion": "Ataque", "asistencia": "Ataque", "reb_ofensivo": "Rebote", "perdidas": "Ataque",
            "robos": "Defensa", "tapones": "Defensa", "faltas": "Defensa"}
NIVEL_Q = ["per", "ws_per_40", "gs40", "pie", "pbp_rapm", "pbp_net_rtg_aj_onoff"]


def _pca3(X: np.ndarray):
    Xf = np.nan_to_num(X, nan=0.0)
    mu = Xf.mean(0)
    U, s, Vt = np.linalg.svd(Xf - mu, full_matrices=False)
    R = Vt[:3].T                              # rasgos × 3
    Z = (Xf - mu) @ R
    esc = 1.0 / max(1e-9, float(np.abs(Z).std()))
    return mu, R, esc


def atlas(Ts: dict[str, Temporada], mz: dict, escalas_: dict) -> tuple[dict, dict, dict, dict]:
    zc = [f"z_{r}" for r in RASGOS]
    nombres = [e["nombre"] for e in mz["estilos"]]
    cl_rows, jg_rows, brutos = [], [], []
    for t, T in sorted(Ts.items()):
        prov = t == max(Ts)
        for liga, L in T.ligas.items():
            D = T.der[liga]
            eq, jg = D["req"], D["rjg"]
            co = L.coaches()
            J = L.J.join(D["nk"]).assign(pos3=D["pos"])
            gpv = pd.to_numeric(L.E["gp"], errors="coerce")
            umbral = max(2.0, 0.25 * float(gpv.median())) if len(gpv) else 2.0
            for (_, r), (tid, er), Pe, u in zip(L.E.iterrows(), eq.iterrows(), D["Pe"], D["eu_e"]):
                tid = str(r["team_id"])
                if float(r["gp"] or 0) < umbral:
                    continue
                o = np.argsort(-np.nan_to_num(Pe, nan=-1))
                js = J[J["team_id"] == tid]
                m = js["min"].astype(float)
                Lpl = float(np.average(js["L"].fillna(0), weights=m)) if m.sum() > 0 else None
                ent = []
                if co.get(tid):
                    jp = L.P[((L.P["local_id"] == tid) | (L.P["visitante_id"] == tid)) & L.P["pts_local"].notna()]
                    f_ = jp["fecha"].dropna().sort_values()
                    ent.append({"orden": 1, "entrenador_id": slug(co[tid][0]), "entrenador": " · ".join(co[tid]),
                                "n_partidos": int(r["gp"]), "n_regular": int(r["gp"]), "n_playoffs": 0,
                                "primer_partido": f_.iloc[0] if len(f_) else None, "ultimo_partido": f_.iloc[-1] if len(f_) else None,
                                "victorias": int(r["w"]), "derrotas": int(r["l"]), "interino": 0, "metodo": "club_unico",
                                "nivel": _num(Lpl, 3), "e": u[0] if u else None, "p": u[1] if u else None,
                                "probs": [round(float(x), 3) for x in Pe] if np.isfinite(Pe).all() else None,
                                "x": None, "y": None, "z": None, "eu": u[0] if u else None, "eu_p": u[1] if u else None,
                                "eu_etiqueta": u[2] if u else None})
                cl_rows.append({"clave": f"{liga}:{tid}:{t}", "clave_club": f"{liga}:{tid}", "nombre_club": titulo(r["equipo"]),
                                "liga": liga, "temporada": t, "tid": tid, "provisional": prov, "min_total": float(m.sum()),
                                "jugadores": int((m >= 100).sum()), "cobertura_ab": 1.0, "nivel": _num(Lpl, 3),
                                "net_z": None, "X": [_num(x, 3) for x in er[zc].to_numpy(float)],
                                "e": u[0] if u else None, "p": u[1] if u else None, "rob": None,
                                "probs": [round(float(x), 3) for x in Pe] if np.isfinite(Pe).all() else None,
                                "entrenadores": ent or None,
                                "eu": u[0] if u else None, "eu2": int(o[1]) if u else None, "eu_p": u[1] if u else None,
                                "eu_probs": [round(float(x), 3) for x in Pe] if np.isfinite(Pe).all() else None,
                                "eu_etiqueta": u[2] if u else None, "division": L.division.get(tid)})
            for (i, r), Pj, u in zip(J.iterrows(), D["Pj"], D["eu_j"]):
                if float(r["min"] or 0) < 40:
                    continue
                o = np.argsort(-np.nan_to_num(Pj, nan=-1))
                Rz = jg.loc[i, zc].to_numpy(float)
                jg_rows.append({"nombre": titulo(r["nombre"]), "clave": f"{liga}:{r['team_id']}:{t}",
                                "nombre_club": L.nombre_eq.get(str(r["team_id"]), titulo(r["equipo"])), "liga": liga,
                                "temporada": t, "pos3": r["pos3"], "min": float(r["min"]), "nivel": _num(r["L"], 3),
                                "fuente_norm": "liga", "provisional": prov, "persona_id": r["player_id"], "pid": r["player_id"],
                                "edad": None, "R": [_num(x, 3) for x in Rz],
                                "Q": [_num(x, 3) for x in [r.get("per"), r.get("ws_per_40"), None, r.get("pie"), r.get("pbp_rapm"), r.get("pbp_net_rtg_aj_onoff")]],
                                "L": _num(r["L"], 3), "ctx_plantilla_dev": None, "ctx_comp": None,
                                "rapm_el": _num(r.get("pbp_rapm"), 2), "orapm_el": _num(r.get("pbp_orapm"), 2),
                                "drapm_el": _num(r.get("pbp_drapm"), 2), "rapm_pct": None, "M": [],
                                "e": u[0] if u else None, "p": u[1] if u else None,
                                "eu": u[0] if u else None, "eu2": int(o[1]) if u else None, "eu_p": u[1] if u else None,
                                "eu_probs": [round(float(x), 3) for x in Pj] if np.isfinite(Pj).all() else None,
                                "eu_etiqueta": u[2] if u else None, "nk": _num(r["nk"], 1), "nk_lo": _num(r["nk_lo"], 1),
                                "nk_hi": _num(r["nk_hi"], 1), "prod": _num(r["prod"], 1), "imp": _num(r["imp"], 1)})
                brutos.append([[_num(x, 3) for x in D["rjg"].loc[i, RASGOS].to_numpy(float)], []])
    C = pd.DataFrame(cl_rows)
    Jd = pd.DataFrame(jg_rows)
    # mapa 3D: componentes principales de los 12 rasgos (z de su liga) de jugadores y equipos
    Xall = np.vstack([np.array([[np.nan if v is None else v for v in x] for x in C["X"]], float),
                      np.array([[np.nan if v is None else v for v in x] for x in Jd["R"]], float)])
    mu, Rm, esc = _pca3(Xall)
    proj = lambda X: ((np.nan_to_num(np.asarray(X, float), nan=0.0) - mu) @ Rm) * esc  # noqa: E731
    Zc = proj([[np.nan if v is None else v for v in x] for x in C["X"]])
    Zj = proj([[np.nan if v is None else v for v in x] for x in Jd["R"]])
    C["x"], C["y"], C["z"] = Zc[:, 0], Zc[:, 1], Zc[:, 2]
    Jd["x"], Jd["y"], Jd["z"] = Zj[:, 0], Zj[:, 1], Zj[:, 2]
    for e in [c for c in C["entrenadores"] if c]:
        pass
    medias, covs = mz["medias"], mz["covs"]
    centros = proj(medias)
    estilos = []
    for k, e in enumerate(mz["estilos"]):
        perfil = medias[k]
        o = np.argsort(-np.abs(perfil))[:4]
        desc = " · ".join(f"{CORTO_R[RASGOS[i]]} {'↑' if perfil[i] > 0 else '↓'}" for i in o)
        cm = (esc ** 2) * Rm.T @ covs[k] @ Rm
        sel = C[C["eu"] == k]
        estilos.append({"id": f"E0{k + 1}", "nombre": e["nombre"], "resumen": e.get("equipo") or e.get("definicion", ""),
                        "descriptor": desc, "clubes": int(len(sel)), "nivel_medio": _num(sel["nivel"].astype(float).mean(), 3),
                        "centro": [_num(x, 4) for x in centros[k]], "cov_mapa": [[_num(x, 5) for x in f] for f in cm],
                        "perfil": [_num(x, 3) for x in perfil],
                        "ligas": {l: round(float((sel["liga"] == l).mean()), 3) for l in LIGAS} if len(sel) else {},
                        "ejemplos": " | ".join(f"{a} {b} ({CORTO[c]})" for a, b, c in sel.sort_values("eu_p", ascending=False)[["nombre_club", "temporada", "liga"]].head(4).itertuples(index=False))})
    ejes = []
    for a in range(3):
        r = [float(np.corrcoef(np.nan_to_num(Xall[:, i]), np.concatenate([Zc[:, a], Zj[:, a]]))[0, 1]) for i in range(len(RASGOS))]
        o = np.argsort(r)
        ejes.append({"r": [round(x, 3) for x in r], "positivo": [CORTO_R[RASGOS[i]] for i in o[::-1][:2] if r[i] > 0.25],
                     "negativo": [CORTO_R[RASGOS[i]] for i in o[:2] if r[i] < -0.25]})
    eu_meta = {k: mz["json"][k] for k in ("descripcion", "rasgos", "asignacion", "estilos") if k in mz["json"]}
    meta = {"generado": datetime.now(timezone.utc).date().isoformat(), "red": "estilos_unificados", "n_estilos": 6,
            "rasgos": [{"col": r, "nombre": next((x["nombre"] for x in mz["rasgos"] if x["id"] == r), r), "bloque": BLOQUE_R[r],
                        "transf": "id", "origen": "pbp" if r in ("esquina", "aro", "autocreacion") else "caja", "corto": CORTO_R[r]} for r in RASGOS],
            "crudas": RASGOS, "nivel_cols": NIVEL_Q,
            "escala_club": {"media": [0.0] * 12, "sd": [1.0] * 12}, "escala_jugador": {"media": [0.0] * 12, "sd": [1.0] * 12},
            "nivel_club": {"media": [0.0] * 6, "sd": [1.0] * 6}, "nivel_jugador": {"media": [0.0] * 6, "sd": [1.0] * 6},
            "neutral_club": None, "neutral_jugador": None, "grado_neutralizacion": 0,
            "temporadas_entreno": sorted(Ts), "temporadas_provisionales": [max(Ts)], "min_jugador": 40,
            "pesos": {"mapa": {"rot": Rm.tolist(), "escala": esc, "mu": mu.tolist()}},
            "estilos": estilos, "estilos_vade": False, "ejes": ejes, "evaluacion": None, "referencia_kmedias": None, "analisis": None,
            "referencias": {}, "similitud": {}, "historial": [], "clubes_con_nombre": {}, "contexto": None, "clave_ctx": [],
            "interacciones": None, "escalas": escalas_, "estilos_unificados": eu_meta}
    dec = {"nivel": 3, "min": 0, "min_total": 0, "x": 3, "y": 3, "z": 3, "p": 3, "eu_p": 3, "L": 3}
    clubes = tabla_cols(C.drop(columns=[]), dec)
    jugadores = tabla_cols(Jd, dec)
    br = {"columnas": ["Rb", "Qb"], "nota": "Valores observados en su propia liga, alineados por índice con jugadores.json",
          "filas": brutos}
    return meta, clubes, jugadores, br
