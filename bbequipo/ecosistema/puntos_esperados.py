"""Capa XP · puntos esperados por tiro y sus agregados (tiro → tramo → jugador). Orden del CEO del 07-11-2026.
Planteamiento completo: docs/puntos_esperados.md. Configuración: configs/ecosistema_v41.yaml → puntos_esperados.

Para qué sirve:
  1. Resultado de tramo con menos ruido: y_xp = 100·(xp_local − xp_visitante)/posesiones quita la suerte del tiro (que
     el mismo tiro entre o no) del diferencial de cada tramo.
  2. Métricas de jugador explícitas y ampliables: calidad de selección de tiro, acierto sobre lo esperado (con su
     contracción), mezcla de zonas, Net en pista sin la suerte del tiro…

Modelo xp1 (sin redes ni ajustes opacos):
  · Tiro de campo: p(anota | zona, liga-temporada), con la tasa de la zona contraída hacia la de su tipo (T2/T3) de la
    misma liga-temporada: p_z = (anotados_z + m·p_tipo)/(intentos_z + m). Zonas de bbmodel/zonas.py con la calibración de
    coordenadas de data/modelos/pista/calibracion.json; sin coordenadas (o calibración < umbral) → «sin_zona» = p_tipo.
  · Tiro libre: TL% del tirador contraído hacia la liga: (TLa + m·p_liga)/(TLi + m).
  · xp = p × valor (2, 3 o 1). La tasa de la liga-temporada es el instrumento de medida de esa temporada (contexto, no
    predicción): usarla para medir la temporada t no introduce fuga en un examen ≤ t → t+1.

AMPLIAR: (1) declarar el campo en `puntos_esperados.catalogo` (grano, unidad, estado, definición); (2) implementarlo aquí
con @campo(grano, nombre); (3) los tests comprueban que todo campo no «propuesto» del catálogo tiene función y viceversa.

Salidas: data/modelos/v4_1/puntos_esperados/{modelo_<t>.csv, jugadores_<t>.csv.gz, calidad.json, catalogo.json} (versionado)
y experimentos/v4_1/puntos_esperados/{tiros,tramos}/<t>/<liga>.csv.gz (no versionado, regenerable).
"""
from __future__ import annotations

import json
import time
from typing import Callable

import numpy as np
import pandas as pd

from . import config as CE

# =============================================================================================== registro de campos
CAMPOS: dict[tuple[str, str], Callable] = {}


def campo(grano: str, nombre: str):
    """Registra la función que calcula un campo del catálogo (grano «jugador»: recibe la tabla agregada por jugador)."""
    def deco(f):
        CAMPOS[(grano, nombre)] = f
        return f
    return deco


# Los campos de grano tiro y tramo los produce el propio cálculo (anotar_tiros, tramos_xp); se registran para que el
# contraste catálogo ↔ código sea completo.
for _n in ("zona", "dist_m", "p_acierto", "xp", "residuo_tiro", "asistido"):
    CAMPOS[("tiro", _n)] = None
for _n in ("xp_a", "xp_b", "pts_tiros_a", "pts_tiros_b", "y_xp"):
    CAMPOS[("tramo", _n)] = None


def catalogo(cfg: dict, estados=("validado", "experimental")) -> dict:
    return {k: v for k, v in cfg["puntos_esperados"]["catalogo"].items() if v["estado"] in estados}


def _div(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(b > 0, a / b, np.nan)


# ---- campos de jugador (la tabla agregada A trae sumas por jugador: fga, fta, pts_campo, pts_libres, xp_campo, xp_libres,
#      fga_<zona>, tlm, poss_on, xp_for_on, xp_against_on, pts_for_on, pts_against_on, y la contracción del acierto)
@campo("jugador", "tiros_campo")
def _f(A): return A["fga"]                                                     # noqa: E704
@campo("jugador", "tiros_libres")
def _f(A): return A["fta"]                                                     # noqa: E704,F811
@campo("jugador", "intentos_ts")
def _f(A): return A["fga"] + 0.44 * A["fta"]                                   # noqa: E704,F811
@campo("jugador", "puntos_tiro")
def _f(A): return A["pts_campo"] + A["pts_libres"]                             # noqa: E704,F811
@campo("jugador", "xp_campo")
def _f(A): return A["xp_campo"]                                                # noqa: E704,F811
@campo("jugador", "xp_libres")
def _f(A): return A["xp_libres"]                                               # noqa: E704,F811
@campo("jugador", "xp_total")
def _f(A): return A["xp_campo"] + A["xp_libres"]                               # noqa: E704,F811
@campo("jugador", "pps")
def _f(A): return _div(A["pts_campo"] + A["pts_libres"], A["fga"] + 0.44 * A["fta"])   # noqa: E704,F811
@campo("jugador", "xpps")
def _f(A): return _div(A["xp_campo"] + A["xp_libres"], A["fga"] + 0.44 * A["fta"])     # noqa: E704,F811
@campo("jugador", "calidad_seleccion")
def _f(A): return _div(A["xp_campo"], A["fga"])                                # noqa: E704,F811
@campo("jugador", "acierto_sobre_esperado")
def _f(A): return _div(A["pts_campo"] + A["pts_libres"] - A["xp_campo"] - A["xp_libres"], A["fga"] + 0.44 * A["fta"])  # noqa: E704,F811,E501
@campo("jugador", "acierto_sobre_esperado_campo")
def _f(A): return _div(A["pts_campo"] - A["xp_campo"], A["fga"])               # noqa: E704,F811
@campo("jugador", "acierto_sobre_esperado_contraido")
def _f(A): return A["_ase_contraido"]                                          # noqa: E704,F811
@campo("jugador", "fiabilidad_acierto")
def _f(A): return A["_fiab"]                                                   # noqa: E704,F811
@campo("jugador", "tl_pct_contraido")
def _f(A): return A["_tl_contraido"]                                           # noqa: E704,F811
for _z in ("aro", "corta", "media", "t3_esquina", "t3_frontal", "sin_zona"):
    CAMPOS[("jugador", f"pct_tc_{_z}")] = (lambda A, z=_z: _div(A[f"fga_{z}"], A["fga"]))
@campo("jugador", "poss_on")
def _f(A): return A["poss_on"]                                                 # noqa: E704,F811
@campo("jugador", "xortg_on")
def _f(A): return 100 * _div(A["xp_for_on"], A["poss_on"])                     # noqa: E704,F811
@campo("jugador", "xdrtg_on")
def _f(A): return 100 * _div(A["xp_against_on"], A["poss_on"])                 # noqa: E704,F811
@campo("jugador", "xnet_on")
def _f(A): return 100 * _div(A["xp_for_on"] - A["xp_against_on"], A["poss_on"])    # noqa: E704,F811
@campo("jugador", "net_on")
def _f(A): return 100 * _div(A["pts_for_on"] - A["pts_against_on"], A["poss_on"])  # noqa: E704,F811


# =============================================================================================== modelo de tiro
def _calibraciones(cfg: dict) -> dict:
    return json.loads((CE.RAIZ / cfg["puntos_esperados"]["calibracion_coordenadas"]).read_text(encoding="utf-8"))


def zonas(t: pd.DataFrame, liga: str, temp: str, cfg: dict, calib: dict) -> tuple[pd.Series, pd.Series, bool]:
    """Zona y distancia de cada tiro de campo (bbmodel.zonas); «sin_zona» sin coordenadas o con calibración pobre."""
    from bbmodel import zonas as Z
    cp = cfg["puntos_esperados"]
    zona = pd.Series(cp["sin_coordenadas"], index=t.index, dtype=object)
    dist = pd.Series(np.nan, index=t.index)
    c = calib.get(f"{liga}|{temp}")
    ok_cal = bool(c and c["acierto"] >= float(cp["umbral_acierto_calibracion"]))
    if ok_cal:
        sis = Z.Sistema(liga, c["regla"], c["eje_largo"], tuple(c["aro"]), tuple(c["escala"]), c["pista_completa"])
        campo_ = t["tipo"].isin(["T2", "T3"])
        s = t[campo_ & t["x"].notna() & t["y"].notna() & ~((t["x"] == 0) & (t["y"] == 0))]
        if len(s):
            p = Z.perfil_tiro(s, sis)
            zona.loc[p.index] = p["zona"]
            dist.loc[p.index] = p["dist_m"]
    zona[t["tipo"] == "TL"] = "tiro_libre"
    return zona, dist, ok_cal


def modelo_lt(t: pd.DataFrame, cfg: dict) -> dict:
    """Tasas del modelo xp1 de una liga-temporada: por tipo, por zona (contraídas al tipo) y TL de liga."""
    cc = cfg["puntos_esperados"]["contraccion"]
    m_z = float(cc["zona_hacia_tipo"])
    out = {"tipo": {}, "zona": {}, "tl_liga": np.nan}
    for tipo in ("T2", "T3"):
        s = t[t["tipo"] == tipo]
        out["tipo"][tipo] = float(s["anotado"].mean()) if len(s) else np.nan
    for (tipo, z), s in t[t["tipo"].isin(["T2", "T3"])].groupby(["tipo", "zona"]):
        p_t = out["tipo"][tipo]
        out["zona"][(tipo, z)] = {"n": int(len(s)), "anotados": int(s["anotado"].sum()),
                                  "p": float((s["anotado"].sum() + m_z * p_t) / (len(s) + m_z))}
    tl = t[t["tipo"] == "TL"]
    out["tl_liga"] = float(tl["anotado"].mean()) if len(tl) else np.nan
    return out


def anotar_tiros(t: pd.DataFrame, mod: dict, cfg: dict) -> pd.DataFrame:
    """Campos de grano tiro: p_acierto, xp, residuo_tiro, asistido (zona y dist_m ya vienen)."""
    cc = cfg["puntos_esperados"]
    t = t.copy()
    valor = t["tipo"].map({"T2": 2.0, "T3": 3.0, "TL": 1.0}).astype(float)
    p = np.full(len(t), np.nan)
    campo_ = t["tipo"].isin(["T2", "T3"]).to_numpy()
    claves = list(zip(t["tipo"], t["zona"]))
    p[campo_] = [mod["zona"].get(k, {"p": mod["tipo"][k[0]]})["p"] for k, c in zip(claves, campo_) if c]
    tl = (t["tipo"] == "TL").to_numpy()
    if tl.any():
        if cc["tl_modelo"] == "liga":
            p[tl] = mod["tl_liga"]
        else:
            m = float(cc["contraccion"]["tl_tirador_hacia_liga"])
            g = t[tl].groupby("player_id")["anotado"].agg(["sum", "size"])
            pj = (g["sum"] + m * mod["tl_liga"]) / (g["size"] + m)
            p[tl] = t.loc[tl, "player_id"].map(pj).to_numpy(float)
    t["p_acierto"] = p
    t["xp"] = p * valor
    t["residuo_tiro"] = t["puntos"].astype(float) - t["xp"]
    t["asistido"] = t["asistente_id"].notna() & t["anotado"].astype(bool)
    return t


# =============================================================================================== tramos
def tramos_xp(tr: pd.DataFrame, t: pd.DataFrame) -> pd.DataFrame:
    """xp y puntos (desde los tiros) de cada lado de cada tramo. Emparejamiento: mismo partido, quinteto atacante y
    rival, y t0 ≤ t ≤ t1. Un tiro justo en el cambio pertenece al tramo que TERMINA en ese instante (comprobado: con esta
    regla los puntos de los tramos se reproducen exactos en el 100 % de los de ACB y NBA 2024-25 y el 99,9 % de EuroLeague
    y LBA; con la contraria, 99,5–99,8 %)."""
    lados = []
    for lado, qo, qd in (("a", "quinteto_a", "quinteto_b"), ("b", "quinteto_b", "quinteto_a")):
        lados.append(pd.DataFrame({"fila": tr.index.to_numpy(), "lado": lado, "game_id": tr["game_id"].to_numpy(),
                                   "q": tr[qo].astype(str).to_numpy(), "qr": tr[qd].astype(str).to_numpy(),
                                   "t0": tr["t0"].to_numpy(float), "t1": tr["t1"].to_numpy(float)}))
    L = pd.concat(lados, ignore_index=True)
    s = pd.DataFrame({"i": t.index.to_numpy(), "game_id": t["game_id"].to_numpy(), "q": t["quinteto"].astype(str).to_numpy(),
                      "qr": t["quinteto_rival"].astype(str).to_numpy(), "t": t["t"].to_numpy(float),
                      "xp": t["xp"].to_numpy(float), "puntos": t["puntos"].to_numpy(float)})
    m = s.merge(L, on=["game_id", "q", "qr"], how="inner")
    m = m[(m["t"] >= m["t0"]) & (m["t"] <= m["t1"])]
    m = m.sort_values(["i", "t1", "t0"]).drop_duplicates("i", keep="first")  # tiro en el límite: el tramo que termina ahí
    g = m.groupby(["fila", "lado"])[["xp", "puntos"]].sum().unstack("lado").fillna(0.0)
    out = pd.DataFrame(index=tr.index)
    for lado in ("a", "b"):
        out[f"xp_{lado}"] = g[("xp", lado)].reindex(tr.index).fillna(0.0) if ("xp", lado) in g else 0.0
        out[f"pts_tiros_{lado}"] = g[("puntos", lado)].reindex(tr.index).fillna(0.0) if ("puntos", lado) in g else 0.0
    out.attrs["tiros_emparejados"] = float(len(m) / max(len(s), 1))
    return out


# =============================================================================================== jugadores
def agregar_jugadores(t: pd.DataFrame, tr: pd.DataFrame, liga: str, temp: str, cfg: dict) -> pd.DataFrame:
    """Tabla por jugador (liga, temporada, equipo, jugador) con todos los campos «jugador» del catálogo."""
    zs = cfg["puntos_esperados"]["zonas"] + [cfg["puntos_esperados"]["sin_coordenadas"]]
    t = t.copy()
    t["fga"] = t["tipo"].isin(["T2", "T3"]).astype(float)
    t["fta"] = (t["tipo"] == "TL").astype(float)
    t["pts_campo"] = np.where(t["fga"] > 0, t["puntos"], 0.0)
    t["pts_libres"] = np.where(t["fta"] > 0, t["puntos"], 0.0)
    t["xp_campo"] = np.where(t["fga"] > 0, t["xp"], 0.0)
    t["xp_libres"] = np.where(t["fta"] > 0, t["xp"], 0.0)
    t["res_campo"] = np.where(t["fga"] > 0, t["residuo_tiro"], 0.0)
    t["res2_campo"] = t["res_campo"] ** 2
    t["tlp"] = np.where(t["fta"] > 0, t["p_acierto"], np.nan)
    for z in zs:
        t[f"fga_{z}"] = ((t["zona"] == z) & (t["fga"] > 0)).astype(float)
    k = ["team_id", "player_id"]
    sumas = ["fga", "fta", "pts_campo", "pts_libres", "xp_campo", "xp_libres", "res_campo", "res2_campo"] + [f"fga_{z}" for z in zs]
    A = t.groupby(k)[sumas].sum()
    A["_tl_contraido"] = t.groupby(k)["tlp"].first()
    A["nombre"] = t.groupby(k)["nombre"].first() if "nombre" in t else None
    # acierto sobre lo esperado (campo), contraído: varianza de ruido por tiro σ²_e (media de res² dentro de jugador) y
    # varianza entre jugadores por momentos, ambas de la liga-temporada
    n = A["fga"].to_numpy(float)
    ase = _div(A["res_campo"], n)
    ok = n >= 20
    s2e = float(np.sum(A["res2_campo"][ok]) / max(np.sum(n[ok]), 1))
    if ok.sum() > 10:
        w = n[ok]
        mu = float(np.sum(w * ase[ok]) / w.sum())
        tau2 = max(float(np.sum(w * (ase[ok] - mu) ** 2) / w.sum() - s2e * ok.sum() / w.sum()), 0.0)
    else:
        mu, tau2 = 0.0, 0.0
    fiab = np.where(n > 0, tau2 / (tau2 + s2e / np.maximum(n, 1)), 0.0) if tau2 > 0 else np.zeros(len(n))
    A["_fiab"] = fiab
    A["_ase_contraido"] = np.where(n > 0, mu + fiab * (np.nan_to_num(ase) - mu), np.nan)
    # en pista (tramos del contrato): xp y puntos a favor y en contra
    on = []
    for lado, q, f, c in (("a", "quinteto_a", "a", "b"), ("b", "quinteto_b", "b", "a")):
        d = pd.DataFrame({"team_id": tr[f"team_{lado}"].astype(str).to_numpy(), "q": tr[q].astype(str).to_numpy(),
                          "poss_on": tr["poss"].to_numpy(float), "xp_for_on": tr[f"xp_{f}"].to_numpy(float),
                          "xp_against_on": tr[f"xp_{c}"].to_numpy(float),
                          "pts_for_on": pd.to_numeric(tr[f"{f}_pts"]).to_numpy(float),
                          "pts_against_on": pd.to_numeric(tr[f"{c}_pts"]).to_numpy(float)})
        d["player_id"] = d["q"].str.split("|")
        on.append(d.explode("player_id").drop(columns="q"))
    O = pd.concat(on).groupby(["team_id", "player_id"])[["poss_on", "xp_for_on", "xp_against_on", "pts_for_on",
                                                         "pts_against_on"]].sum()
    A.index = pd.MultiIndex.from_arrays([A.index.get_level_values(0).astype(str), A.index.get_level_values(1).astype(str)],
                                        names=k)
    A = A.join(O, how="outer").fillna({c: 0.0 for c in sumas + list(O.columns)})
    out = pd.DataFrame({"liga": liga, "temporada": temp, "team_id": A.index.get_level_values(0),
                        "player_id": A.index.get_level_values(1), "nombre": A["nombre"].to_numpy()})
    for nombre, v in catalogo(cfg).items():
        if v["grano"] == "jugador":
            out[nombre] = np.asarray(CAMPOS[("jugador", nombre)](A), float)
    return out


# =============================================================================================== orquestación
def lt(temp: str, liga: str, cfg: dict, calib: dict) -> dict | None:
    """Una liga-temporada: tiros anotados, tramos con xp (todas las filas del fichero), jugadores y calidad."""
    from .. import config as C40
    from ..contrato import filtrar_tramos
    cfg40 = CE.cargar_v40(cfg)
    d = C40.ruta(cfg40, "quintetos", temporada=temp) / liga
    if not (d / "tiros.csv.gz").exists() or not (d / "tramos.csv.gz").exists():
        return None
    t = pd.read_csv(d / "tiros.csv.gz", low_memory=False)
    t = t[t["tipo"].isin(["T2", "T3", "TL"])].copy()
    if t.empty:
        return None
    t["anotado"] = t["anotado"].astype(str).str.lower().isin(["true", "1"])
    t["puntos"] = pd.to_numeric(t["puntos"], errors="coerce").fillna(0.0)
    t["zona"], t["dist_m"], ok_cal = zonas(t, liga, temp, cfg, calib)
    mod = modelo_lt(t, cfg)
    t = anotar_tiros(t, mod, cfg)
    tr_all = pd.read_csv(d / "tramos.csv.gz", low_memory=False)
    x = tramos_xp(tr_all, t)
    tr_c, _ = filtrar_tramos(tr_all, cfg40)                                   # índice original conservado
    tr_c = tr_c.join(x, how="left")
    tr_c["y_xp"] = 100.0 * (tr_c["xp_a"] - tr_c["xp_b"]) / tr_c["poss"]
    J = agregar_jugadores(t, tr_c, liga, temp, cfg)
    pts_tr = float(tr_all["a_pts"].sum() + tr_all["b_pts"].sum())
    calidad = {"liga": liga, "temporada": temp, "tiros": int(len(t)), "calibracion_ok": ok_cal,
               "frac_tc_con_zona": float((t.loc[t["tipo"] != "TL", "zona"] != cfg["puntos_esperados"]["sin_coordenadas"]).mean()),
               "tiros_emparejados_con_tramo": x.attrs["tiros_emparejados"],
               "puntos_reconstruidos_en_tramos": float((x["pts_tiros_a"].sum() + x["pts_tiros_b"].sum()) / pts_tr) if pts_tr else np.nan,
               "tramos_con_puntos_exactos": float(((x["pts_tiros_a"] == pd.to_numeric(tr_all["a_pts"])) &
                                                   (x["pts_tiros_b"] == pd.to_numeric(tr_all["b_pts"]))).mean()),
               "xp_sobre_puntos": float(t["xp"].sum() / max(t["puntos"].sum(), 1)),
               "p_tl_liga": mod["tl_liga"], "p_t2": mod["tipo"]["T2"], "p_t3": mod["tipo"]["T3"]}
    modelo = pd.DataFrame([{"liga": liga, "temporada": temp, "tipo": k[0], "zona": k[1], **v} for k, v in mod["zona"].items()])
    cols_t = ["game_id", "periodo", "t", "team_id", "player_id", "tipo", "anotado", "puntos", "quinteto", "quinteto_rival"] + \
             [c for c, v in cfg["puntos_esperados"]["catalogo"].items() if v["grano"] == "tiro" and v["estado"] != "propuesto"]
    cols_r = ["game_id", "periodo", "t0", "t1", "team_a", "team_b", "quinteto_a", "quinteto_b", "poss", "a_pts", "b_pts"] + \
             [c for c, v in cfg["puntos_esperados"]["catalogo"].items() if v["grano"] == "tramo" and v["estado"] != "propuesto"]
    return {"tiros": t[cols_t], "tramos": tr_c[cols_r], "jugadores": J, "modelo": modelo, "calidad": calidad}


def ejecutar(cfg: dict, temporadas=None, ligas=None, progreso=print) -> dict:
    cp = cfg["puntos_esperados"]
    calib = _calibraciones(cfg)
    dv = CE.dir_salida(cfg, "puntos_esperados")
    dn = CE.RAIZ / cp["salidas"]["no_versionado"]
    from bbfit.datos import persona
    cal, t0 = [], time.time()
    for temp in temporadas or cp["temporadas"]:
        dq = CE.RAIZ / "data" / "processed" / temp / "quintetos"
        if not dq.exists():
            continue
        Js, Ms = [], []
        for dl in sorted(p for p in dq.iterdir() if p.is_dir()):
            if ligas and dl.name not in ligas:
                continue
            r = lt(temp, dl.name, cfg, calib)
            if r is None:
                continue
            for k in ("tiros", "tramos"):
                f = dn / k / temp / f"{dl.name}.csv.gz"
                f.parent.mkdir(parents=True, exist_ok=True)
                r[k].to_csv(f, index=False, float_format="%.5g")
            J = r["jugadores"]
            J.insert(4, "persona_id", persona(dl.name, J["player_id"].astype(str)).astype(str).to_numpy())
            Js.append(J)
            Ms.append(r["modelo"])
            cal.append(r["calidad"])
            if progreso:
                c = r["calidad"]
                progreso(f"  xp {temp} {dl.name}: {c['tiros']} tiros · zona {c['frac_tc_con_zona']:.2f} · emparejados "
                         f"{c['tiros_emparejados_con_tramo']:.3f} · xp/puntos {c['xp_sobre_puntos']:.3f} · {time.time() - t0:.0f} s",
                         flush=True)
        if Js and not ligas:
            pd.concat(Js, ignore_index=True).to_csv(dv / f"jugadores_{temp}.csv.gz", index=False, float_format="%.5g")
            pd.concat(Ms, ignore_index=True).to_csv(dv / f"modelo_{temp}.csv", index=False, float_format="%.5g")
    if not ligas:
        (dv / "calidad.json").write_text(json.dumps(cal, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
        (dv / "catalogo.json").write_text(json.dumps({"version_modelo": cp["version_modelo"], "catalogo": cp["catalogo"]},
                                                     ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ligas_temporada": len(cal), "segundos": round(time.time() - t0)}


def cargar_tramos(cfg: dict, temp: str, liga: str) -> pd.DataFrame:
    """Tramos anotados (contrato v4.0) con xp_a, xp_b, y_xp; los calcula si no están en la caché."""
    f = CE.RAIZ / cfg["puntos_esperados"]["salidas"]["no_versionado"] / "tramos" / temp / f"{liga}.csv.gz"
    if not f.exists():
        r = lt(temp, liga, cfg, _calibraciones(cfg))
        f.parent.mkdir(parents=True, exist_ok=True)
        r["tramos"].to_csv(f, index=False, float_format="%.5g")
    return pd.read_csv(f, low_memory=False)
