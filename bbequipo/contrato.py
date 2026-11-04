"""F0 · contrato de datos del modelo de equipo (encargo §3 y §5.2): inventario de los tramos de quinteto por
liga-temporada, cobertura del jugada a jugada y decisión de inclusión en F1–F3, con las reglas fijadas en
configs/equipo_v40.yaml → contrato (basura fuera, clutch covariable, exposición = posesiones, localía h_s).

Salidas (data/modelos/v4_0/contrato/): inventario_tramos.csv (una fila por liga-temporada) y contrato_datos.json
(decisiones, totales y la configuración aplicada). Todo lo que figura aquí se ha medido en los ficheros [DATO].
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C

COLS_TRAMOS = ["game_id", "fase", "sec", "team_a", "team_b", "quinteto_a", "quinteto_b", "n_a", "n_b", "clutch", "basura",
               "a_fga", "a_fta", "a_oreb", "a_tov", "b_fga", "b_fta", "b_oreb", "b_tov"]


def posesiones(df: pd.DataFrame, lado: str) -> np.ndarray:
    """Posesiones estimadas de un lado del tramo: fga + 0,44·fta − oreb + tov (contrato.tramos.posesiones)."""
    g = lambda c: pd.to_numeric(df[f"{lado}_{c}"], errors="coerce").fillna(0).to_numpy(float)  # noqa: E731
    return g("fga") + 0.44 * g("fta") - g("oreb") + g("tov")


def filtrar_tramos(df: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, dict]:
    """Aplica el contrato a los tramos de una liga-temporada: fuera basura, sólo 5 contra 5, posesiones mínimas,
    fases admitidas. Devuelve los tramos que entran (con `poss` y `h`) y el recuento de lo que se descarta."""
    t = cfg["contrato"]["tramos"]
    n0 = len(df)
    out = df.copy()
    out["poss"] = 0.5 * (posesiones(out, "a") + posesiones(out, "b"))
    out["h"] = 1.0                                           # team_a es el local (bbstats.lineups: teams = [local, visitante])
    info = {"tramos": int(n0)}
    if t.get("basura") == "excluir":
        b = out["basura"].astype(str).str.lower().isin(["true", "1"])
        info["basura_excluidos"] = int(b.sum())
        out = out[~b]
    if t.get("quintetos_completos", True):
        c = (pd.to_numeric(out["n_a"], errors="coerce") == 5) & (pd.to_numeric(out["n_b"], errors="coerce") == 5)
        info["incompletos_excluidos"] = int((~c).sum())
        out = out[c]
    fases = t.get("fases")
    if fases:
        f = out["fase"].isin(fases)
        info["fase_excluidos"] = int((~f).sum())
        out = out[f]
    mp = float(t.get("min_posesiones_tramo", 0))
    p = out["poss"] >= mp
    info["posesiones_minimas_excluidos"] = int((~p).sum())
    out = out[p]
    info["tramos_validos"] = int(len(out))
    return out, info


def _validacion(dir_liga: Path) -> dict:
    p = dir_liga / "validacion.csv"
    if not p.exists():
        return {}
    v = pd.read_csv(p, low_memory=False)
    b = lambda c: v[c].astype(str).str.lower().isin(["true", "1"]) if c in v else pd.Series(False, index=v.index)  # noqa: E731
    return {"partidos_validacion": int(len(v)), "partidos_con_quintetos": int(b("con_quintetos").sum()),
            "partidos_usados": int(b("usado_en_quintetos").sum()), "partidos_validos": int(b("valido").sum()),
            "con_coordenadas": float(b("con_coordenadas").mean()) if len(v) else np.nan}


def inventario_liga_temporada(temp: str, liga: str, cfg: dict) -> dict | None:
    d = C.ruta(cfg, "quintetos", temporada=temp) / liga
    p = d / "tramos.csv.gz"
    if not p.exists():
        return None
    df = pd.read_csv(p, usecols=lambda c: c in COLS_TRAMOS, low_memory=False)
    val = _validacion(d)
    partidos_pbp = int(df["game_id"].nunique())
    tr, info = filtrar_tramos(df, cfg)
    quint = pd.unique(pd.concat([tr["quinteto_a"], tr["quinteto_b"]], ignore_index=True)) if len(tr) else []
    partidos_total = val.get("partidos_validacion") or partidos_pbp
    fila = {"liga": liga, "temporada": temp, "partidos_total": int(partidos_total), "partidos_pbp": partidos_pbp,
            "fraccion_partidos_con_quintetos": (val.get("partidos_usados", partidos_pbp) / partidos_total) if partidos_total
            else np.nan,
            "tramos": info["tramos"], "tramos_validos": info["tramos_validos"],
            "tramos_por_partido": info["tramos_validos"] / max(partidos_pbp, 1),
            "fraccion_5v5": 1 - info.get("incompletos_excluidos", 0) / max(info["tramos"] - info.get("basura_excluidos", 0), 1),
            "fraccion_basura": info.get("basura_excluidos", 0) / max(info["tramos"], 1),
            "fraccion_clutch": float(tr["clutch"].astype(str).str.lower().isin(["true", "1"]).mean()) if len(tr) else np.nan,
            "posesiones": float(tr["poss"].sum()), "segundos": float(pd.to_numeric(tr["sec"], errors="coerce").sum()),
            "quintetos_distintos": int(len(quint)),
            "posesiones_por_quinteto_mediana": float(tr.groupby("quinteto_a")["poss"].sum().median()) if len(tr) else np.nan,
            "con_coordenadas": val.get("con_coordenadas", np.nan),
            "parejas": (d / "parejas.csv.gz").exists(), "equipos": (d / "equipos.csv").exists()}
    e = C.ruta(cfg, "interacciones") / f"efectos_{temp}.csv.gz"
    if e.exists():
        ef = pd.read_csv(e, usecols=["liga"], low_memory=False)
        fila["efectos_dirigidos"] = int((ef["liga"] == liga).sum())
    else:
        fila["efectos_dirigidos"] = 0
    return fila


def decidir(inv: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Decisión por liga-temporada con las reglas de contrato.cobertura (fijadas en F0, antes de entrenar F1)."""
    c = cfg["contrato"]["cobertura"]
    out = inv.copy()
    dec, motivo = [], []
    for _, r in out.iterrows():
        f, tpp = r["fraccion_partidos_con_quintetos"], r["tramos_por_partido"]
        if not np.isfinite(f) or f < float(c["min_partidos_con_quintetos"]):
            dec.append("excluida"); motivo.append(f"partidos con quintetos {f:.0%} < {c['min_partidos_con_quintetos']:.0%}"
                                                  if np.isfinite(f) else "sin validación de quintetos")
        elif tpp < float(c["min_tramos_por_partido"]):
            dec.append("excluida"); motivo.append(f"{tpp:.1f} tramos por partido < {c['min_tramos_por_partido']} (quintetos casi fijos)")
        elif f < float(c["aviso_cobertura_parcial"]):
            dec.append("incluida_con_aviso"); motivo.append(f"cobertura parcial {f:.0%}")
        else:
            dec.append("incluida"); motivo.append("")
    out["decision"], out["motivo"] = dec, motivo
    return out


def cobertura_bloques(cfg: dict, temporadas: list[str]) -> dict:
    """Filas por liga-temporada en roles, estilos, pista y capacidad, y cobertura del crosswalk (persona_id)."""
    from .perfiles import bloque_estilos, bloque_roles
    out = {}
    rol = bloque_roles(cfg).groupby(["liga", "temporada"]).size()
    est = bloque_estilos(cfg).groupby(["liga", "temporada"]).size()
    cw = pd.read_csv(C.ruta(cfg, "crosswalk"), dtype=str, usecols=["fuente_liga", "fuente_id"])
    cw_set = set(zip(cw["fuente_liga"], cw["fuente_id"]))
    for temp in temporadas:
        p = C.ruta(cfg, "destino") / "capacidad" / f"{temp}.csv.gz"
        if not p.exists():
            continue
        cap = pd.read_csv(p, usecols=["liga", "player_id", "min"], dtype={"player_id": str})
        pis = C.ruta(cfg, "pista") / f"{temp}.csv"
        pista = pd.read_csv(pis, usecols=["liga", "player_id"], dtype={"player_id": str}).groupby("liga").size() \
            if pis.exists() else pd.Series(dtype=int)
        for liga, g in cap.groupby("liga"):
            en_cw = np.mean([(liga, pid) in cw_set for pid in g["player_id"]]) if len(g) else np.nan
            out[f"{liga}|{temp}"] = {"capacidad": int(len(g)), "capacidad_min_300": int((g["min"] >= 300).sum()),
                                     "roles": int(rol.get((liga, temp), 0)), "estilos": int(est.get((liga, temp), 0)),
                                     "pista": int(pista.get(liga, 0)), "crosswalk_fraccion": float(en_cw)}
    return out


def generar(cfg: dict, temporadas: list[str] | None = None, progreso=print) -> dict:
    t0 = time.time()
    temporadas = temporadas or list(cfg["perfil"]["temporadas"])
    filas = []
    for temp in temporadas:
        raiz = C.ruta(cfg, "quintetos", temporada=temp)
        if not raiz.exists():
            continue
        for liga in sorted(p.name for p in raiz.iterdir() if p.is_dir()):
            f = inventario_liga_temporada(temp, liga, cfg)
            if f:
                filas.append(f)
                if progreso:
                    progreso(f"  {temp} {liga}: {f['tramos_validos']} tramos válidos de {f['tramos']}, "
                             f"{f['fraccion_partidos_con_quintetos']:.0%} partidos con quintetos", flush=True)
    inv = decidir(pd.DataFrame(filas), cfg)
    out = C.dir_salida(cfg) / "contrato"
    out.mkdir(parents=True, exist_ok=True)
    inv.round(5).to_csv(out / "inventario_tramos.csv", index=False)
    bloques = cobertura_bloques(cfg, temporadas)
    inc = inv[inv["decision"] != "excluida"]
    doc = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "huella_config": C.huella(cfg),
           "reglas": cfg["contrato"],
           "totales": {"liga_temporadas": int(len(inv)), "incluidas": int((inv["decision"] == "incluida").sum()),
                       "incluidas_con_aviso": int((inv["decision"] == "incluida_con_aviso").sum()),
                       "excluidas": int((inv["decision"] == "excluida").sum()),
                       "tramos_validos_incluidos": int(inc["tramos_validos"].sum()),
                       "posesiones_incluidas": float(inc["posesiones"].sum()),
                       "partidos_pbp_incluidos": int(inc["partidos_pbp"].sum())},
           "por_temporada": {t: {"tramos_validos": int(g["tramos_validos"].sum()), "ligas": int(len(g)),
                                 "excluidas": sorted(g.loc[g["decision"] == "excluida", "liga"].tolist())}
                             for t, g in inv.groupby("temporada")},
           "excluidas": inv.loc[inv["decision"] == "excluida", ["liga", "temporada", "motivo"]].to_dict("records"),
           "con_aviso": inv.loc[inv["decision"] == "incluida_con_aviso", ["liga", "temporada", "motivo"]].to_dict("records"),
           "huecos_declarados_comprobados": _comprobar_huecos(inv, cfg),
           "cobertura_bloques": bloques, "tiempo_s": round(time.time() - t0)}
    (out / "contrato_datos.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    if progreso:
        progreso(f"  contrato: {doc['totales']} → {out}", flush=True)
    return doc


def _comprobar_huecos(inv: pd.DataFrame, cfg: dict) -> list[dict]:
    """Los huecos declarados en el encargo (§3) frente a lo medido: ¿la regla los excluye?"""
    out = []
    idx = inv.set_index(["liga", "temporada"])
    for h in cfg["contrato"]["cobertura"].get("ligas_sin_pbp_declaradas", []):
        temps = h.get("temporadas") or sorted({t for l, t in idx.index if l == h["liga"]})
        for t in temps:
            if (h["liga"], t) in idx.index:
                r = idx.loc[(h["liga"], t)]
                out.append({"liga": h["liga"], "temporada": t, "motivo_declarado": h["motivo"], "decision": r["decision"],
                            "fraccion_partidos_con_quintetos": float(r["fraccion_partidos_con_quintetos"]),
                            "tramos_por_partido": float(r["tramos_por_partido"])})
            else:
                out.append({"liga": h["liga"], "temporada": t, "motivo_declarado": h["motivo"], "decision": "sin_fichero"})
    return out
