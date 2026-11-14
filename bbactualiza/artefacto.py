"""Ficheros del artifact que dependen de la temporada en curso y publicación incremental.

Se generan en data/artifact/ (no versionado; mismas rutas que usan las herramientas existentes) y `empaquetar()` deja
en la carpeta de publicación un único lote `lote0.json` {ruta publicada: fichero local} con SÓLO esas rutas
(.gz.txt = gzip en base64, como artifact/empaquetar.py; los JSON de menos de 256 KB, también en claro). Las demás
rutas del artifact (temporadas anteriores, páginas, PDF) no se tocan: la publicación es un parche. Desde la v4.2 el lote
se reparte entre los tres artifacts (Jugadores, Equipos, Metodología) con `bbactualiza.sitios`: `lote_<sitio>_<n>.json`
y el resumen `sitios.json`.
"""
from __future__ import annotations

import base64
import gzip
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import TEMPORADA

RAIZ = Path(__file__).resolve().parent.parent
DA = RAIZ / "data" / "artifact"
PREVIA = "2025-26"


def _empaquetar_mod():
    spec = importlib.util.spec_from_file_location("empaquetar_artifact", RAIZ / "artifact" / "empaquetar.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _py(*args: str) -> None:
    env = {**os.environ, "PYTHONPATH": str(RAIZ), "MLFLOW_DISABLE_AGENT_HINT": "1"}
    subprocess.run([sys.executable, *args], cwd=RAIZ, env=env, check=True, stdout=sys.stderr)   # stdout: sólo el informe


# ============================================================================================ tablas de datos
def tablas(temporada: str = TEMPORADA) -> None:
    """datos/<t>/{indice,regular,playoffs,total}.json (y la temporada anterior, que usa de referencia el informe)."""
    from bbstats.pipeline import export_artifact
    for t in (temporada, PREVIA):
        export_artifact(RAIZ / "data" / "processed", t, DA)


def nacionalidades_json(temporada: str = TEMPORADA) -> None:
    from bbmodel.dataset_normalizado import _columnar, _dump
    from bbmodel.nacionalidad import SALIDA
    nac = pd.read_csv(SALIDA, dtype={"player_id": str}).dropna(subset=["nacionalidad"])
    g = nac[nac["temporada"] == temporada]
    g = g.assign(player_uid=g["liga"] + ":" + g["player_id"])
    _dump(_columnar(g[["player_uid", "nacionalidad", "nacionalidad_fuente"]].drop_duplicates("player_uid")),
          DA / temporada / "nacionalidades.json")


def evaluacion(temporada: str = TEMPORADA) -> None:
    """Evaluación de ligas (descriptiva): la de la temporada y la de la anterior (sus «puentes» usan la siguiente)."""
    from concurrent.futures import ProcessPoolExecutor
    pares = [(temporada, "regular"), (temporada, "total"), (PREVIA, "regular")]
    with ProcessPoolExecutor(max_workers=min(len(pares), os.cpu_count() or 1)) as ex:   # cada par, en su proceso
        list(ex.map(_evaluar_par, pares))


def _evaluar_par(par: tuple[str, str]) -> None:
    from bbmodel import evaluacion_ligas as EL
    EL.main(str(DA), solo={par})


def normalizados(temporada: str = TEMPORADA) -> None:
    """datos/normalizados/<t>/regular.json, normalizacion/jugadores_<t>.json (v3.2) e índice de todas las temporadas."""
    from bbmodel.dataset_normalizado import NOMBRES_LIGA, METRICAS, _columnar, _dump, explorador
    from bbmodel.nombres import aplicar
    dir_v1, dir_v32 = RAIZ / "data/modelos/normalizado", RAIZ / "data/modelos/v3_2/normalizado"
    cols = pd.read_csv(dir_v1 / f"{temporada}.csv", nrows=0).columns
    df = pd.read_csv(dir_v32 / f"{temporada}.csv.gz", low_memory=False)[list(cols)]
    df["fuente_norm"] = "V3.2"
    df = aplicar(df, fuente=False)
    _dump(_columnar(df), DA / "normalizados" / temporada / "regular.json")
    _dump(explorador(df), DA / "normalizacion" / f"jugadores_{temporada}.json")
    # índice: recuento por liga de cada temporada (= bbnorm3.artifact.main sin reescribir las demás temporadas)
    indice = {"generado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "temporadas": {},
              "descripcion": "Equivalente EuroLeague 2025-26 de todos los jugadores con la normalización v3.2 "
                             "(combinación de A+B amortiguado y la CVAE jerárquica), temporada regular",
              "metricas": METRICAS}
    for f in sorted(dir_v32.glob("*.csv.gz")):
        t = f.name[:7]
        ligas = pd.read_csv(f, usecols=["liga"], dtype=str)["liga"].value_counts().sort_index()
        pi = RAIZ / "data/processed" / t / "indice.json"
        fechas = {k: v.get("fecha_extraccion") for k, v in json.loads(pi.read_text(encoding="utf-8")).get("ligas", {}).items()} \
            if pi.exists() else {}
        indice["temporadas"][t] = {"temporada": t, "fases": ["regular"], "fases_con_datos": ["regular"],
                                   "ligas": {l: {"nombre": NOMBRES_LIGA.get(l, l), "fases": {"regular": int(n)},
                                                 "fecha_extraccion": fechas.get(l), "a_mas_b": int(n)}
                                             for l, n in ligas.items()}}
    _dump(indice, DA / "normalizados" / "indice.json")


def _v51_tabla(temporada: str):
    """Tabla v5.1 de una temporada: la v3.2 publicada (esquema v1) con el componente v5 combinado (bbnorm5.producto51)."""
    from bbnorm5.salidas import producto51 as P
    sup = P.DIR / "superposicion" / f"{temporada}.csv.gz"
    if not sup.exists():
        return None
    cols = pd.read_csv(RAIZ / "data/modelos/normalizado" / f"{temporada}.csv", nrows=0).columns
    v32 = pd.read_csv(RAIZ / "data/modelos/v3_2/normalizado" / f"{temporada}.csv.gz", low_memory=False)[list(cols)]
    pesos = {m: e["w"] for m, e in json.loads((P.DIR / "vara_v51.json").read_text(encoding="utf-8"))["metricas"].items()}
    df = P.aplicar(v32, pd.read_csv(sup, dtype={"player_id": str, "team_id": str}), pesos)
    # <m>_am*: copias de la v3.2 que ninguna página lee (compactar las quita cuando son idénticas a <m>; en la v5.1 no lo son)
    return df.drop(columns=[m + s for m in P.ORDEN for s in ("_am", "_am_lo", "_am_hi", "_am_pctel") if m + s in df.columns])


def normalizados_v51(temporada: str = TEMPORADA) -> dict:
    """v5.1 (encargo v5.1 F6): datos/normalizados/<t>/regular_v51.json (mismo esquema que regular.json, más las máscaras
    v51_comb y v51_solo) y datos/normalizados/vara_v51.json."""
    from bbmodel.dataset_normalizado import _columnar, _dump
    from bbmodel.nombres import aplicar
    from bbnorm5.salidas import producto51 as P
    df = _v51_tabla(temporada)
    if df is None:
        return {"temporada": temporada, "filas": 0}
    df = aplicar(df, fuente=False)
    _dump(_columnar(df), DA / "normalizados" / temporada / "regular_v51.json")
    _dump(json.loads((P.DIR / "vara_v51.json").read_text(encoding="utf-8")), DA / "normalizados" / "vara_v51.json")
    return {"temporada": temporada, "filas": int(len(df)), "v51": int((df["fuente_norm"] == "V5.1").sum())}


def normalizados_v51_todas() -> list[dict]:
    from bbnorm5.salidas import producto51 as P
    ts = sorted(f.name[:7] for f in (P.DIR / "superposicion").glob("*.csv.gz"))
    return [normalizados_v51(t) for t in ts]


def compactar() -> None:
    _py("artifact/herramientas/compactar.py", str(DA))


# ============================================================================================ atlas
def atlas_estilos() -> None:
    _py("-m", "bbestilo", "exportar", "--salida", str(DA / "atlas" / "estilos"), "--todas-las-ligas")


def informe(temporada: str = TEMPORADA) -> None:
    """Lectura de fichaje de la temporada (referencias de la última temporada completa, como `bbestilo informe`)."""
    from bbestilo import informe as I
    from bbestilo.exportar import _sin_nan
    a = I._tabla(I._leer_json(DA / "atlas" / "estilos" / "jugadores.json"))
    meta = I._leer_json(DA / "atlas" / "estilos" / "meta.json")
    prov = set(meta.get("temporadas_provisionales") or [])
    completas = [t for t in sorted(a["temporada"].unique()) if t not in prov]
    pool = temporada if temporada not in prov else max(completas)
    d = I.construir(temporada, a, DA, RAIZ / "data/modelos/v3_2/normalizado", pool)
    sal = DA / "atlas" / "informe"
    sal.mkdir(parents=True, exist_ok=True)
    (sal / f"{temporada}.json").write_text(json.dumps(_sin_nan(d), ensure_ascii=False, separators=(",", ":"),
                                                      allow_nan=False), encoding="utf-8")


# ============================================================================================ quintetos
def quintetos(temporada: str = TEMPORADA) -> None:
    """Mesa de quintetos (todas las temporadas: el índice las lista), equipos y estilos unificados de Equipos y quintetos."""
    _py("-m", "bbmodel", "mesa-quintetos", "--salida", str(DA))
    _py("artifact/herramientas/gen_equipos_quintetos.py", str(DA), str(DA / "quintetos" / "datos" / "equipos.gz.txt"))
    # los generadores de estilos unificados leen la disposición PUBLICADA (rutas .gz.txt): carpeta de enlaces
    orig = DA / "_publicado"
    shutil.rmtree(orig, ignore_errors=True)
    (orig / "atlas" / "estilos").mkdir(parents=True)
    for n in ("jugadores", "clubes"):
        (orig / "atlas" / "estilos" / f"{n}.json.gz.txt").symlink_to(DA / "atlas" / "estilos" / f"{n}.json")
    (orig / "atlas" / "estilos" / "meta.json").symlink_to(DA / "atlas" / "estilos" / "meta.json")
    qd = orig / "quintetos" / "datos"
    qd.mkdir(parents=True)
    (qd / "equipos.gz.txt").symlink_to(DA / "quintetos" / "datos" / "equipos.gz.txt")
    for f in sorted((DA / "quintetos" / "datos").glob("20*/*.gz.txt")):
        if f.name.endswith(".extras.gz.txt"):
            continue                                  # (sin «jugadores»: el generador no los admite)
        (qd / f.parent.name).mkdir(exist_ok=True)
        (qd / f.parent.name / f.name).symlink_to(f)
    _py("artifact/herramientas/gen_eu_quintetos.py", str(orig), str(RAIZ / "artifact/quintetos/estilos_unificados.gz.txt"))
    _py("artifact/herramientas/gen_eu_clubes_quintetos.py", str(orig),
        str(RAIZ / "artifact/quintetos/estilos_unificados_clubes.gz.txt"))


# ============================================================================================ publicación
def mapa(temporada: str = TEMPORADA) -> dict[str, Path]:
    """Rutas publicadas que dependen de la temporada en curso → fichero local."""
    m: dict[str, Path] = {"datos/temporadas.json": DA / "temporadas.json", "datos/actualizacion.json": DA / "actualizacion.json"}
    for p in sorted((DA / temporada).glob("*.json")):
        if p.name != "evaluacion_playoffs.json":
            m[f"datos/{temporada}/{p.name}"] = p
    if (DA / PREVIA / "evaluacion_regular.json").exists():          # «puentes» hacia la temporada en curso
        m[f"datos/{PREVIA}/evaluacion_regular.json"] = DA / PREVIA / "evaluacion_regular.json"
    for rel in (f"normalizados/{temporada}/regular.json", f"normalizados/{temporada}/regular_v51.json",
                "normalizados/vara_v51.json", "normalizados/indice.json",
                f"normalizacion/jugadores_{temporada}.json"):
        if (DA / rel).exists():
            m[f"datos/{rel}"] = DA / rel
    for p in sorted((DA / "atlas" / "estilos").glob("*.json")):
        m[f"atlas/estilos/{p.name}"] = p
    if (DA / "atlas" / "informe" / f"{temporada}.json").exists():
        m[f"atlas/informe/{temporada}.json"] = DA / "atlas" / "informe" / f"{temporada}.json"
    for p in sorted((DA / "simulador").glob("*.json")):
        if p.name != "paridad.json":
            m[f"atlas/simulador/{p.name}"] = p
    q = DA / "quintetos" / "datos"
    for p in sorted((q / temporada).glob("*")):
        m[f"quintetos/datos/{temporada}/{p.name}"] = p
    for n in ("indice.json", "equipos.gz.txt"):
        if (q / n).exists():
            m[f"quintetos/datos/{n}"] = q / n
    for n in ("estilos_unificados.gz.txt", "estilos_unificados_clubes.gz.txt"):
        m[f"quintetos/{n}"] = RAIZ / "artifact" / "quintetos" / n
    for rel, src in _v40().items():
        m[rel] = src
    for rel, src in _v42(temporada).items():
        m[rel] = src
    return {k: v for k, v in m.items() if v.exists()}


def _v42(temporada: str = TEMPORADA) -> dict[str, Path]:
    """Tríos y parejas v4.2 de la temporada en curso (bbequipo.v42.actualizar; los publican Equipos y Metodología).
    La previa del historial v4.2 (atlas/v42/historial/<t>) sólo depende de temporadas cerradas: no cambia."""
    d = RAIZ / "artifact" / "kerno" / "quintetos" / "datos_v42"
    out = {f"quintetos/datos_v42/{temporada}/{p.name}": p for p in sorted((d / temporada).glob("*.gz.txt"))}
    if (d / "indice.json").exists():
        out["quintetos/datos_v42/indice.json"] = d / "indice.json"
    return out


def _v40() -> dict[str, Path]:
    d = DA / "atlas_v40"
    out = {f"atlas/v40/{p.name}": p for p in sorted(d.glob("*.json"))} if d.exists() else {}
    e = DA / "v40"
    if e.exists():
        out.update({f"v40/{p.name}": p for p in sorted(e.glob("*.json"))})
    return out


def empaquetar(salida: Path, temporada: str = TEMPORADA) -> dict:
    """Carpeta de publicación con un único lote (parche) de las rutas de la temporada en curso."""
    E = _empaquetar_mod()
    salida = Path(salida)
    comp = salida / "comprimidos"
    shutil.rmtree(comp, ignore_errors=True)
    comp.mkdir(parents=True)
    final: dict[str, str] = {}
    for pub, src in mapa(temporada).items():
        if src.suffix == ".json":
            dst = comp / (pub.replace("/", "__") + ".gz.txt")
            b = src.read_bytes()        # gzip estándar: ≈ 10 veces más rápido que zopfli (≈ 4 % más grande)
            dst.write_bytes(base64.b64encode(E._gzip(b) if os.environ.get("BBACTUALIZA_ZOPFLI") else gzip.compress(b, 9)))
            final[pub + ".gz.txt"] = str(dst)
            if src.stat().st_size <= E.UMBRAL:     # los pequeños también en claro (como artifact/empaquetar.py); los
                final[pub] = str(src)              # grandes nunca se publicaron en claro: nada que borrar
        else:
            final[pub] = str(src)
    orden = sorted(final, key=lambda k: (not k.endswith(("indice.json", "temporadas.json", "indice.json.gz.txt")), k))
    lote = {k: final[k] for k in orden}
    (salida / "lote0.json").write_text(json.dumps(lote, ensure_ascii=False, indent=0), encoding="utf-8")
    tam = sum(Path(v).stat().st_size for v in lote.values() if v)
    info = {"ficheros": len(lote), "mb": round(tam / 1e6, 1), "lote": str(salida / "lote0.json")}
    # v4.2: tres artifacts (Jugadores, Equipos, Metodología); cada uno recibe sólo las rutas de su manifiesto, en lotes
    # que caben en una publicación (bbactualiza.sitios)
    from . import sitios
    r = sitios.repartir(lote, salida)
    info["sitios"] = {s: {k: v[k] for k in ("url", "ficheros", "mb")} | {"lotes": len(v["lotes"])}
                      for s, v in r["sitios"].items()}
    info["rutas_nuevas"], info["sin_sitio"] = r["rutas_nuevas"], r["sin_sitio"]
    return info
