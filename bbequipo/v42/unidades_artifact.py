"""D3 · unidades v4.2 en el artifact: tríos, parejas y sinergia de pareja para la página de quintetos.

Lee las estimaciones v4.2 (`data/modelos/v4_2/unidades/{trios,parejas,sinergia_pareja}_v42.csv.gz`, formato en
docs/checkpoints/V42_D3_unidades.md §5) y escribe un fichero pequeño por liga y temporada, con el mismo código que
los datos de la página (JSON comprimido con gzip y en base64; el Artifact sólo sirve tipos de texto):

    artifact/kerno/quintetos/datos_v42/<temporada>/<liga>.gz.txt
    artifact/kerno/quintetos/datos_v42/indice.json          (qué liga-temporada tiene fichero: la página sólo pide esas)

Sólo entran las unidades que la página muestra (los mismos filtros que bbmodel/mesa_quintetos.py: los 20 tríos con más
minutos de cada equipo y fase; parejas con 40+ minutos en regular o total) y que tienen estimación v4.2 (≥ 50
posesiones en la fase total). Los quintetos no van: su examen no pasó (se queda la versión vigente).

Contenido (tablas columnares {"c": [...], "f": [[...], ...]}):
    t  tríos:   team_id, u, poss, v, lo, hi, w, np
    p  parejas: team_id, u, poss, v, lo, hi, w, np, sv, slo, shi, sw
  u   ids de jugador ordenados y unidos por «|» (la columna `unidad` de bbstats); la página la rehace con los
      player_id de sus índices, así que la clave es team_id + u;
  poss posesiones de la fase total (lo que ha visto la v4.2 esa temporada);
  v, lo, hi  Net v4.2 (pts/100) y su rango del 80 % (θ ± z80·√P, temporadas ≤ la mostrada);
  w   peso de la propia temporada (ganancia de Kalman); np, temporadas previas de la unidad;
  sv, slo, shi, sw  lo mismo para la sinergia WOWY de la pareja.

    PYTHONPATH=. python -m bbequipo.v42.unidades_artifact [--salida DIR] [--ligas acb euroleague] [--temporadas 2025-26]
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
DIR_PROC = RAIZ / "data" / "processed"
DIR_V42 = RAIZ / "data" / "modelos" / "v4_2" / "unidades"
SALIDA = RAIZ / "artifact" / "kerno" / "quintetos" / "datos_v42"
TRIOS_POR_EQUIPO_FASE = 20      # bbmodel/mesa_quintetos.py: «los 20 tríos con más minutos de cada equipo y fase»
MIN_PAREJA = 40.0               # bbmodel/mesa_quintetos.py: «parejas con 40+ minutos (regular y total)»


def _clave(u: str) -> str:
    return "|".join(sorted(str(u).split("|")))


def _mostradas(liga: str, temporada: str) -> tuple[set[str], set[str]] | None:
    """Claves team_id#unidad de los tríos y parejas que la página trae para esa liga y temporada."""
    d = DIR_PROC / temporada / "quintetos" / liga
    ft, fp = d / "trios.csv.gz", d / "parejas.csv.gz"
    if not ft.exists() and not fp.exists():
        return None
    tri, par = set(), set()
    if ft.exists():
        t = pd.read_csv(ft, dtype={"team_id": str, "unidad": str}, usecols=["team_id", "unidad", "fase", "min"])
        t = t.sort_values("min", ascending=False).groupby(["team_id", "fase"]).head(TRIOS_POR_EQUIPO_FASE)
        tri = set(t["team_id"] + "#" + t["unidad"].map(_clave))
    if fp.exists():
        p = pd.read_csv(fp, dtype={"team_id": str, "unidad": str}, usecols=["team_id", "unidad", "fase", "min"])
        p = p[(p["min"] >= MIN_PAREJA) & p["fase"].isin(["regular", "total"])]
        par = set(p["team_id"] + "#" + p["unidad"].map(_clave))
    return tri, par


def _leer(tipo: str) -> pd.DataFrame:
    d = pd.read_csv(DIR_V42 / f"{tipo}_v42.csv.gz", dtype={"team_id": str, "unidad": str, "temporada": str})
    d["clave"] = d["team_id"] + "#" + d["unidad"].map(_clave)
    return d


def _r(x, nd: int):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    r = round(float(x), nd)
    return int(r) if r == int(r) else r


def _filas(df: pd.DataFrame, cols: list[tuple[str, int]]) -> list[list]:
    return [[r[c] if nd < 0 else _r(r[c], nd) for c, nd in cols] for r in df.to_dict("records")]


def exportar(salida: Path = SALIDA, ligas: list[str] | None = None, temporadas: list[str] | None = None) -> dict:
    tr, pa, si = _leer("trios"), _leer("parejas"), _leer("sinergia_pareja")
    si = si[["liga", "temporada", "clave", "v42", "v42_lo", "v42_hi", "peso_temporada"]].rename(
        columns={"v42": "sv", "v42_lo": "slo", "v42_hi": "shi", "peso_temporada": "sw"})
    pa = pa.merge(si, on=["liga", "temporada", "clave"], how="left")
    pares = sorted(set(zip(tr["liga"], tr["temporada"])) | set(zip(pa["liga"], pa["temporada"])))
    indice = {"generado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "version": "4.2",
              "fuente": "data/modelos/v4_2/unidades (bbequipo/v42/unidades.py exportar)", "temporadas": {}}
    total, n_t, n_p = 0, 0, 0
    for liga, temp in pares:
        if (ligas and liga not in ligas) or (temporadas and temp not in temporadas):
            continue
        m = _mostradas(liga, temp)
        if m is None:
            continue
        kt, kp = m
        t = tr[(tr["liga"] == liga) & (tr["temporada"] == temp) & tr["clave"].isin(kt)]
        p = pa[(pa["liga"] == liga) & (pa["temporada"] == temp) & pa["clave"].isin(kp)]
        if t.empty and p.empty:
            continue
        t = t.assign(u=t["clave"].str.split("#").str[1]).sort_values(["team_id", "u"])
        p = p.assign(u=p["clave"].str.split("#").str[1]).sort_values(["team_id", "u"])
        ct = [("team_id", -1), ("u", -1), ("poss", 0), ("v42", 2), ("v42_lo", 2), ("v42_hi", 2), ("peso_temporada", 3),
              ("temporadas_previas", 0)]
        cp = ct + [("sv", 2), ("slo", 2), ("shi", 2), ("sw", 3)]
        nom = {"v42": "v", "v42_lo": "lo", "v42_hi": "hi", "peso_temporada": "w", "temporadas_previas": "np"}
        d = {"version": "4.2", "liga": liga, "temporada": temp,
             "t": {"c": [nom.get(c, c) for c, _ in ct], "f": _filas(t, ct)},
             "p": {"c": [nom.get(c, c) for c, _ in cp], "f": _filas(p, cp)}}
        dest = salida / temp / f"{liga}.gz.txt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(d, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        dest.write_bytes(base64.b64encode(gzip.compress(data, 9)))
        b = dest.stat().st_size
        total += b; n_t += len(t); n_p += len(p)
        indice["temporadas"].setdefault(temp, {})[liga] = {"bytes": b, "trios": len(t), "parejas": len(p)}
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "indice.json").write_text(json.dumps(indice, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    nf = sum(len(v) for v in indice["temporadas"].values())
    return {"ficheros": nf, "bytes": total, "trios": n_t, "parejas": n_p, "salida": str(salida)}


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m bbequipo.v42.unidades_artifact")
    ap.add_argument("--salida", type=Path, default=SALIDA)
    ap.add_argument("--ligas", nargs="*", default=None)
    ap.add_argument("--temporadas", nargs="*", default=None)
    a = ap.parse_args()
    r = exportar(a.salida, a.ligas, a.temporadas)
    print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
