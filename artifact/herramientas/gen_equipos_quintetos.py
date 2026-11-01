"""Genera quintetos/datos/equipos.gz.txt: «Evaluación de equipos» de la página de Quintetos (todas las ligas y
temporadas). Reconstruido el 01-11-2026 a partir del formato publicado (el generador original no estaba en el
repositorio); comprobado contra la versión publicada en las ligas que ya tenía (mismas cifras).

    python artifact/herramientas/gen_equipos_quintetos.py <data/artifact> <salida.gz.txt>

  filas        una por (temporada, fase, liga, equipo): totales oficiales de equipo y rival de
               data/processed/<t>/ligas/<liga>.csv (columnas team_* / opp_*, iguales en todas las filas del equipo)
  plantillas   «liga:team_id:temporada» → nivel L de la plantilla (media de L ponderada por minutos), edad media
               ponderada, nº de jugadores y lista [nombre, pos3, edad, min, L, e, p] (Atlas: atlas/estilos/jugadores.json)
  clubes       «liga:team_id:temporada» → estilo del mapa, robustez, posición, provisional y etapas de entrenador
               (Atlas: atlas/estilos/clubes.json)
  conv_nivel_club  recta L ≈ a + b · nivel del club (para clubes sin plantilla), con su correlación
"""
from __future__ import annotations

import base64
import glob
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
COLS = ["t", "f", "liga", "id", "k", "eq", "gp", "w", "l", "wl", "pts", "opts", "poss", "ritmo", "ortg", "drtg", "net",
        "efg", "oefg", "tov", "otov", "orb", "drb", "ftr", "oftr", "t3r", "ot3r", "t3", "ot3", "t2", "ot2", "tl",
        "astr", "oastr", "stl", "blk"]


def _r(v, d=2):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v):
        return None
    return int(round(v)) if d == 0 else round(v, d)


def _div(a, b):
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return None
    return 100 * a / b if b else None


def _cols(doc: dict) -> pd.DataFrame:
    if "por_columna" in doc:
        return pd.DataFrame(dict(zip(doc["columnas"], doc["por_columna"])))
    return pd.DataFrame(doc["filas"], columns=doc["columnas"])


def filas_equipo(ent_wl: dict, kmap: dict) -> list[list]:
    out = []
    for f in sorted(glob.glob(str(RAIZ / "data/processed/20*-*/ligas/*.csv"))):
        d = pd.read_csv(f, low_memory=False, dtype={"team_id": str})
        team = [c for c in d.columns if c.startswith(("team_", "opp_")) and c != "team_id"]
        d = d[["liga", "temporada", "fase", "team_id", "equipo"] + team].drop_duplicates(["fase", "team_id"])
        for _, r in d.iterrows():
            t, ph, lg, tid = r["temporada"], r["fase"], r["liga"], str(r["team_id"])
            k = kmap.get((lg, t, tid), f"{lg}:{tid}:{t}")      # clave del Atlas (ids inestables: «c010»…)
            w, l, wl = r.get("team_w"), r.get("team_l"), "oficial"
            if not (pd.notna(w) and pd.notna(l)):
                w, l = ent_wl.get((k, ph), (None, None))
                wl = "entrenadores" if w is not None else None
            fga, fta, tov = r.get("team_fga"), r.get("team_fta"), r.get("team_tov")
            ofga = r.get("opp_fga")
            efg = _div((r.get("team_fgm") or 0) + 0.5 * (r.get("team_fg3m") or 0), fga) if pd.notna(fga) else None
            oefg = _div((r.get("opp_fgm") or 0) + 0.5 * (r.get("opp_fg3m") or 0), ofga) if pd.notna(ofga) else None
            fila = [t, ph, lg, tid, k, r["equipo"], _r(r.get("team_gp"), 0), _r(w, 0), _r(l, 0), wl,
                    _r(r.get("team_pts"), 0), _r(r.get("opp_pts"), 0), _r(r.get("team_poss"), 1), _r(r.get("team_pace")),
                    _r(r.get("team_ortg")), _r(r.get("team_drtg")), _r(r.get("team_netrtg")), _r(efg), _r(oefg),
                    _r(_div(tov, r.get("team_poss"))), _r(_div(r.get("opp_tov"), r.get("opp_poss"))),
                    _r(_div(r.get("team_oreb"), (r.get("team_oreb") or 0) + (r.get("opp_dreb") or 0))),
                    _r(_div(r.get("team_dreb"), (r.get("team_dreb") or 0) + (r.get("opp_oreb") or 0))),
                    _r(_div(fta, fga)), _r(_div(r.get("opp_fta"), ofga)), _r(_div(r.get("team_fg3a"), fga)),
                    _r(_div(r.get("opp_fg3a"), ofga)), _r(_div(r.get("team_fg3m"), r.get("team_fg3a"))),
                    _r(_div(r.get("opp_fg3m"), r.get("opp_fg3a"))), _r(_div(r.get("team_fg2m"), r.get("team_fg2a"))),
                    _r(_div(r.get("opp_fg2m"), r.get("opp_fg2a"))), _r(_div(r.get("team_ftm"), fta)),
                    _r(_div(r.get("team_ast"), r.get("team_fgm"))), _r(_div(r.get("opp_ast"), r.get("opp_fgm"))),
                    _r(_div(r.get("team_stl"), r.get("opp_poss"))), _r(_div(r.get("team_blk"), r.get("opp_fg2a")))]
            out.append(fila)
    return out


def main(art: str, salida: str) -> None:
    A = Path(art) / "atlas" / "estilos"
    cl = _cols(json.loads((A / "clubes.json").read_text(encoding="utf-8")))
    jg = _cols(json.loads((A / "jugadores.json").read_text(encoding="utf-8")))
    clubes, ent_wl = {}, {}
    for _, c in cl.iterrows():
        ents = []
        for e in (c.get("entrenadores") if isinstance(c.get("entrenadores"), list) else []) or []:
            ents.append({"n": e.get("entrenador"), "id": e.get("entrenador_id"), "pj": e.get("n_partidos"),
                         "pr": e.get("n_regular"), "pp": e.get("n_playoffs"), "de": e.get("primer_partido"),
                         "a": e.get("ultimo_partido"), "w": e.get("victorias"), "l": e.get("derrotas"),
                         "int": e.get("interino"), "met": e.get("metodo"), "L": e.get("nivel"), "e": e.get("e"),
                         "p": e.get("p"), "probs": e.get("probs"), "xyz": [e.get("x"), e.get("y"), e.get("z")]})
        k = c["clave"]
        clubes[k] = {"club": c.get("clave_club"), "nom": c.get("nombre_club"), "e": _r(c.get("e"), 0), "p": _r(c.get("p"), 3),
                     "probs": c.get("probs"), "rob": _r(c.get("rob"), 3), "xyz": [_r(c.get(a), 3) for a in ("x", "y", "z")],
                     "prov": bool(c.get("provisional")), "ent": ents}
        if ents:      # victorias de la temporada por los entrenadores (ligas sin W/L de equipo en la fuente)
            ent_wl[(k, "total")] = (sum(e["w"] or 0 for e in ents), sum(e["l"] or 0 for e in ents))
    plant = {}
    for k, g in jg.groupby("clave"):
        w = pd.to_numeric(g["min"], errors="coerce").fillna(0).to_numpy()
        L = pd.to_numeric(g["L"], errors="coerce").to_numpy()
        ed = pd.to_numeric(g["edad"], errors="coerce").to_numpy()
        okL, okE = np.isfinite(L) & (w > 0), np.isfinite(ed) & (w > 0)
        g = g.sort_values("min", ascending=False)
        plant[k] = {"L": _r((L[okL] * w[okL]).sum() / w[okL].sum(), 4) if okL.any() else None,
                    "edad": _r((ed[okE] * w[okE]).sum() / w[okE].sum()) if okE.any() else None, "n": int(len(g)),
                    "j": [[r["nombre"], r["pos3"], _r(r["edad"], 1), _r(r["min"], 0), _r(r["L"], 3), _r(r["e"], 0),
                           _r(r["p"], 3)] for _, r in g.iterrows()]}
    # recta L de la plantilla ≈ a + b · nivel del club
    x = np.array([cl.set_index("clave")["nivel"].get(k, np.nan) for k in plant], float)
    y = np.array([plant[k]["L"] if plant[k]["L"] is not None else np.nan for k in plant], float)
    ok = np.isfinite(x) & np.isfinite(y)
    b, a = np.polyfit(x[ok], y[ok], 1) if ok.sum() > 10 else (np.nan, np.nan)
    conv = {"a": _r(a, 5), "b": _r(b, 5), "r": _r(np.corrcoef(x[ok], y[ok])[0, 1], 4) if ok.sum() > 10 else None}
    kmap = {(c["liga"], c["temporada"], str(c["tid"])): c["clave"] for _, c in cl.iterrows() if "tid" in cl}
    filas = filas_equipo(ent_wl, kmap)
    temps = sorted({f[0] for f in filas})
    doc = {"generado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "temporadas": temps,
           "conv_nivel_club": conv, "columnas": COLS, "filas": filas, "plantillas": plant, "clubes": clubes}
    def limpio(o):
        if isinstance(o, float):
            return o if np.isfinite(o) else None
        if isinstance(o, (np.floating, np.integer)):
            return limpio(o.item())
        if isinstance(o, list):
            return [limpio(v) for v in o]
        if isinstance(o, dict):
            return {k: limpio(v) for k, v in o.items()}
        return o
    doc = limpio(doc)
    raw = gzip.compress(json.dumps(doc, ensure_ascii=False, separators=(",", ":"), allow_nan=False, default=str).encode(), 9)
    Path(salida).write_text(base64.b64encode(raw).decode())
    print(len(filas), "filas ·", len(plant), "plantillas ·", len(clubes), "clubes ·", conv, "·", len(raw), "bytes")


if __name__ == "__main__":
    main(*sys.argv[1:])
