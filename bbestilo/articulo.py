"""Artículo científico en PDF con los resultados de los estilos de juego (modelo final: VaDE de 6 estilos con 17
rasgos, 13 de caja y 4 de jugada a jugada), la evolución de las iteraciones anteriores (data/modelos/estilos/historial/)
y las capas de contexto de nivel y química de estilos (data/modelos/contexto/, data/modelos/estilos/interacciones.json).

    python -m bbestilo articulo [--fuentes DIR]  →  docs/articulo/estilos_de_juego_baskonia.pdf
                                                     (y copia en artifact/articulo/ para el Atlas)

Genera las figuras (figuras.py), compone el artículo en HTML con las cifras leídas de
data/modelos/estilos/ y lo imprime a PDF con Chromium sin interfaz. Si se pasa una carpeta de fuentes
(woff/ttf de Source Serif 4, IBM Plex Sans/Mono y Barlow Condensed) se incrustan; si no, se usan las del sistema.
"""
from __future__ import annotations

import html
import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from . import figuras
from .entrenar import HIPER

LIGAS = figuras.LIGAS
SALIDA = C.RAIZ / "docs" / "articulo"
NOMBRE_PDF = "estilos_de_juego_baskonia.pdf"


def n(x, d=2, signo=False):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "–"
    s = f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("+" + s) if signo and x > 0 else s


def pc(x, d=0):
    return "–" if x is None else n(100 * x, d) + " %"


def p_txt(p):
    if p is None:
        return "–"
    return "p < 0,001" if p < 0.001 else f"p = {n(p, 3)}"


def e(s):
    return html.escape(str(s))


def tabla(cab: list[str], filas: list[list], num: set[int] | None = None, cls: str = "") -> str:
    num = num or set()
    th = "".join(f'<th class="{"r" if i in num else ""}">{c}</th>' for i, c in enumerate(cab))
    tr = "".join("<tr>" + "".join(f'<td class="{"r" if i in num else ""}">{v}</td>' for i, v in enumerate(f)) + "</tr>" for f in filas)
    return f'<table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>'


def figura(src: str, n_fig: int, pie: str, ancho: str = "100%") -> str:
    return f'<figure><img src="figuras/{src}" style="width:{ancho}"><figcaption><b>Figura {n_fig}.</b> {pie}</figcaption></figure>'


CSS = """
@page { size: A4; margin: 20mm 21mm 20mm 21mm; @bottom-center { content: counter(page); font: 8.5pt 'IBM Plex Sans', sans-serif; color: #7a6450; } }
html { font-family: 'Source Serif 4', 'DejaVu Serif', Georgia, serif; font-size: 10.2pt; line-height: 1.42; color: #24190f; }
body { margin: 0; }
h1 { font-family: 'Barlow Condensed', 'Arial Narrow', sans-serif; font-size: 25pt; line-height: 1.05; margin: 0 0 6pt; letter-spacing: .01em; color: #3a2a1c; }
h2 { font-family: 'Barlow Condensed', 'Arial Narrow', sans-serif; font-size: 15.5pt; margin: 16pt 0 5pt; color: #3a2a1c; break-after: avoid; }
h3 { font-family: 'IBM Plex Sans', sans-serif; font-size: 10.2pt; margin: 11pt 0 3pt; color: #3a2a1c; break-after: avoid; }
p { margin: 0 0 6pt; text-align: justify; hyphens: auto; }
.autores { font-family: 'IBM Plex Sans', sans-serif; font-size: 9pt; color: #6b4f38; margin-bottom: 10pt; }
.resumen { background: #f9f3eb; border-left: 3pt solid #6b4f38; padding: 8pt 11pt; margin: 8pt 0 10pt; font-size: 9.6pt; }
.resumen p { margin-bottom: 4pt; }
.clave { font-family: 'IBM Plex Sans', sans-serif; font-size: 8.5pt; color: #6b4f38; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-family: 'IBM Plex Sans', sans-serif; font-size: 8pt; break-inside: avoid; }
caption, .tcap { font-family: 'IBM Plex Sans', sans-serif; font-size: 8.4pt; text-align: left; margin: 8pt 0 2pt; color: #3a2a1c; break-after: avoid; }
th { text-align: left; border-bottom: 1pt solid #3a2a1c; padding: 3pt 5pt; font-weight: 600; background: #f9f3eb; }
td { border-bottom: .5pt solid #e3d0b8; padding: 2.6pt 5pt; vertical-align: top; }
td.r, th.r { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
table.corr th { white-space: normal; font-size: 7.4pt; }
figure { margin: 8pt 0 10pt; break-inside: avoid; text-align: center; }
figcaption { font-family: 'IBM Plex Sans', sans-serif; font-size: 8.2pt; text-align: left; color: #3a2a1c; margin-top: 3pt; }
.eq { font-family: 'IBM Plex Mono', monospace; font-size: 8.6pt; background: #fcf9f5; border: .5pt solid #e3d0b8; padding: 5pt 8pt; margin: 4pt 0 8pt; white-space: pre-wrap; break-inside: avoid; }
code { font-family: 'IBM Plex Mono', monospace; font-size: 8.4pt; }
ul, ol { margin: 0 0 6pt 14pt; padding: 0; } li { margin-bottom: 2.5pt; text-align: justify; }
.refs li { font-size: 8.6pt; margin-bottom: 2pt; text-align: left; }
.sw { display: inline-block; width: 7pt; height: 7pt; border-radius: 50%; margin-right: 3pt; vertical-align: 0; }
.salto { break-before: page; }
.resumen.ejecutivo { background: #fcf9f5; border-left-color: #2f7a4c; }
.resumen .rt { font-family: 'Barlow Condensed', 'Arial Narrow', sans-serif; font-size: 13pt; font-weight: 700; color: #3a2a1c; margin-bottom: 3pt; text-align: left; }
.resumen ul { margin: 0 0 2pt 12pt; } .resumen li { margin-bottom: 3pt; }
"""


def _fuentes_css(fuentes: Path | None, d: Path) -> str:
    if not fuentes or not (fuentes / "fuentes.css").exists():
        return ""
    (d / "fuentes").mkdir(exist_ok=True)
    css = (fuentes / "fuentes.css").read_text()
    for f in fuentes.glob("*.woff*"):
        shutil.copy(f, d / "fuentes" / f.name)
    import re
    return re.sub(r"url\(https://fonts\.gstatic\.com/[^)]*/([^/)]+)\)", r"url(fuentes/\1)", css)


def _campo(x: dict, ruta: str):
    """x["a"]["b"] para ruta "a.b"."""
    for k in ruta.split("."):
        x = x[k]
    return x


ITERACIONES = [   # (id, carpeta en historial/ o "" = modelo final, red, etiqueta corta); como exportar.ITERACIONES
    ("v1_vade", "v1_12estilos", "vade", "v1 VaDE 12"), ("v1_idec", "v1_12estilos", "idec", "v1 IDEC 12"),
    ("v2_vade", "v2_8estilos", "vade", "v2 VaDE 8"), ("v2_idec", "v2_8estilos", "idec", "v2 IDEC 8"),
    ("v3_vade", "v3_6estilos", "vade", "v3 VaDE 6"), ("v4_vade", "v4_6estilos_box", "vade", "v4 VaDE 6 (13 caja)"),
    ("final", "", "vade", "Final VaDE 6 (17)"),
]
# Acuerdo de la partición de la v3 con las redes de la v4 (13 rasgos de caja), medido al entrenar la v4 con
# centralidad(). No se puede recalcular con la entrada actual de 17 rasgos (cambia la neutralización y la escala).
CENTRALIDAD_V3 = {"nuevas": 0.35, "consenso": 0.41, "todas": 0.46}
# Sistema de coordenadas de cada fuente (bbmodel/zonas.py)
UNIDADES_PISTA = {"euroleague": "cm desde el aro", "eurocup": "cm desde el aro", "acb": "mm desde el aro, ejes cambiados",
                  "nba": "décimas de pie desde el aro", "gleague": "décimas de pie desde el aro",
                  "lba": "% de la pista completa (28 × 15 m)", "lnb": "% de la pista completa (28 × 15 m)",
                  "bbl": "unidades propias, media pista",
                  "bcl": "unidades de fiba.basketball, media pista", "fec": "unidades de fiba.basketball, media pista",
                  "bsl": "% de la pista completa (28 × 15 m)", "gbl": "% de la pista completa (28 × 15 m)"}


def _leer_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _historial() -> dict:
    out = {}
    for id_, carpeta, red, _ in ITERACIONES:
        p = (C.DIR_SALIDA / "historial" / carpeta if carpeta else C.DIR_SALIDA) / "evaluacion.json"
        if p.exists():
            ev = json.loads(p.read_text(encoding="utf-8"))
            if red in ev:
                out[id_] = ev[red]
    return out


def _etiquetas(carpeta: str) -> pd.Series:
    p = (C.DIR_SALIDA / "historial" / carpeta if carpeta else C.DIR_SALIDA) / "vade" / "clubes.csv"
    c = pd.read_csv(p)
    return c.loc[~c["provisional"]].set_index("clave")["estilo"]


def _acuerdo(a: str, b: str) -> dict:
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score
    x, y = _etiquetas(a), _etiquetas(b)
    x, y = x.align(y, join="inner")
    return {"ari": adjusted_rand_score(x, y), "nmi": normalized_mutual_info_score(x, y)}


def centralidad() -> dict:
    """Acuerdo (ARI) del modelo final y de la partición de la v3 con las redes de las 10 semillas y con su consenso:
    comprueba si ampliar el consenso de 5 a 10 semillas da una partición más representativa. (Se usó al entrenar
    la v4; sus cifras para la v3 están en CENTRALIDAD_V3. El artículo ya no lo llama.)"""
    from sklearn.metrics import adjusted_rand_score as ari
    from .encaje import conjunto
    from .entrenar import cargar, etiquetas
    import torch
    cj = conjunto()
    sel = cj.clubes["temporada"].isin(C.TEMPORADAS_ENTRENO).to_numpy()
    X = torch.tensor(cj.Xc[sel], dtype=torch.float32)
    claves = cj.clubes.loc[sel, "clave"].to_numpy()
    d = C.DIR_SALIDA / "vade" / "semillas"
    sem = sorted(int(p.stem) for p in d.glob("*.pt"))
    E = [etiquetas(cargar(d / f"{s}.pt")[0], X) for s in sem]
    cons = np.load(C.DIR_SALIDA / "vade" / "consenso.npy")
    lab = {"final": _etiquetas("").loc[claves].to_numpy()}
    if (C.DIR_SALIDA / "historial" / "v3_6estilos").exists():
        lab["v3"] = _etiquetas("v3_6estilos").loc[claves].to_numpy()
    nuevas = [i for i, s in enumerate(sem) if s not in C.SEMILLAS[:5]]
    return {k: {"todas": float(np.mean([ari(v, e) for e in E])), "nuevas": float(np.mean([ari(v, E[i]) for i in nuevas])) if nuevas else None,
                "consenso": float(ari(v, cons))} for k, v in lab.items()}


def ejemplo_simulacion() -> dict:
    """Escenario de ejemplo para el artículo (el mismo criterio que el Atlas): Baskonia EuroLeague 2025-26 ficha a
    los dos jugadores de 2025-26 (800+ min, de otros clubes y fuera de la NBA) cuyo perfil más se parece al estilo del club, y sale el
    jugador de la plantilla con más minutos."""
    from .encaje import _pred, conjunto, red_guardada, referencias_distancia, simular_plantilla
    from .similares import mismo_club
    cj, red = conjunto(), red_guardada("vade")
    clave = "euroleague:BAS:2025-26"
    i = list(cj.clubes["clave"]).index(clave)
    J = cj.jugadores
    propio = mismo_club(cj.clubes.at[i, "clave_club"])
    m = ((J["temporada"] == "2025-26") & (J["min"] >= 800) & (J["liga"] != "nba") & ~J["clave_club"].isin(propio)).to_numpy()
    idx = np.flatnonzero(m)
    d = np.linalg.norm(cj.Xj[idx] - cj.Xc[i], axis=1)
    persona = J["persona_id"].fillna(J["liga"] + ":" + J["player_id"].astype(str))
    fich, vistos = [], set()
    for k in np.argsort(d):
        pid = persona.iat[idx[k]]
        if pid in vistos:
            continue
        vistos.add(pid)
        fich.append(int(J.index[idx[k]]))
        if len(fich) == 2:
            break
    pl = J[(J["clave"] == clave) & (J["min"] >= C.MIN_JUGADOR)].sort_values("min", ascending=False)
    baja = int(pl.index[0])
    P0, Z0 = _pred(red, cj.Xc[[i]])
    V, Qm, mins = simular_plantilla(cj, clave, [(j, None) for j in fich], [baja])
    P1, Z1 = _pred(red, cj.x_club(V[None], Qm[None]))
    Pp, Zp = _pred(red, cj.Xj[pl.index.to_numpy()])
    Pf, Zf = _pred(red, cj.Xj[fich])
    ref = referencias_distancia(red, cj)
    corto = lambda s: str(s).split(",")[0].title()  # noqa: E731
    e0 = int(P0[0].argmax())
    return {
        "club": cj.clubes.at[i, "nombre_club"], "temporada": "2025-26",
        "antes": {"p": P0[0].tolist(), "xyz": Z0[0].tolist(), "e": e0, "nivel": float(cj.clubes.at[i, "nivel"])},
        "despues": {"p": P1[0].tolist(), "xyz": Z1[0].tolist(), "e": int(P1[0].argmax()),
                    "nivel": float(cj.nivel_club.indice(Qm[None])[0])},
        "plantilla": [{"nombre": corto(r.nombre), "min": float(r.min), "e": int(Pp[k].argmax()), "xyz": Zp[k].tolist()}
                      for k, r in enumerate(pl.itertuples()) if r.Index != baja],
        "bajas": [{"nombre": corto(J.at[baja, "nombre"]), "nombre_completo": J.at[baja, "nombre"], "min": float(J.at[baja, "min"]),
                   "e": int(Pp[0].argmax()), "xyz": Zp[0].tolist()}],
        "fichajes": [{"nombre": corto(J.at[j, "nombre"]), "nombre_completo": J.at[j, "nombre"], "equipo": J.at[j, "nombre_club"],
                      "liga": J.at[j, "liga"], "min": mm, "e": int(Pf[k].argmax()), "xyz": Zf[k].tolist(),
                      "d": float(np.linalg.norm(Zf[k] - Z0[0])), "pct": float((ref["jugador_su_club"] <= np.linalg.norm(Zf[k] - Z0[0])).mean() * 100),
                      "afin": float(Pf[k, e0]), "nivel": float(J.at[j, "nivel"])}
                     for k, (j, mm) in enumerate(zip(fich, mins))],
        "desplazamiento": float(np.linalg.norm(Z1[0] - Z0[0])),
        "pct_desplazamiento": float((ref["club_club"] <= np.linalg.norm(Z1[0] - Z0[0])).mean() * 100),
    }


def construir(fuentes: Path | None = None, chrome: str | None = None) -> Path:
    R = C.DIR_SALIDA
    d = SALIDA
    d.mkdir(parents=True, exist_ok=True)
    trabajo = d / "_trabajo"
    trabajo.mkdir(exist_ok=True)
    EJ = ejemplo_simulacion()
    F = figuras.todas(trabajo / "figuras", fuentes, EJ)
    ev = json.loads((R / "evaluacion.json").read_text(encoding="utf-8"))
    V = ev["vade"]
    H = _historial()
    V1, I1, V2, I2, V3, V4 = (H.get(k, {}) for k in ("v1_vade", "v1_idec", "v2_vade", "v2_idec", "v3_vade", "v4_vade"))
    A = json.loads((R / "analisis.json").read_text(encoding="utf-8"))
    reg = json.loads((R / "vade" / "registro.json").read_text(encoding="utf-8"))
    reg4 = _leer_json(R / "historial" / "v4_6estilos_box" / "vade" / "registro.json") or {}
    est = pd.read_csv(R / "vade" / "estilos.csv")
    cl = pd.read_csv(R / "vade" / "clubes.csv")
    nom = {}
    p = C.RAIZ / "config" / "estilos.json"
    if p.exists():
        nom = {k: v for k, v in json.loads(p.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    nom4 = {k: v for k, v in (_leer_json(R / "historial" / "v4_6estilos_box" / "nombres.json") or {}).items() if not k.startswith("_")}
    nombre = lambda s: nom.get(s, {}).get("nombre", s)  # noqa: E731
    nombre4 = lambda s: nom4.get(s, {}).get("nombre", s)  # noqa: E731
    sw = lambda k: f'<span class="sw" style="background:{figuras.COL[k]}"></span>'  # noqa: E731
    sn = lambda s: f"{sw(int(s[1:]) - 1)}«{e(nombre(s))}»"  # noqa: E731
    from .redes import RedVaDE
    NR = len(C.RASGOS)
    n_pbp = sum(r.origen.endswith("(jugada a jugada)") for r in C.RASGOS)
    n_caja = NR - n_pbp
    n_par = sum(t.numel() for t in RedVaDE(NR, HIPER["vade"]["ocultas"], 3, C.N_ESTILOS, "completa").parameters())
    ent = cl[~cl["provisional"]]
    n_cl, n_prov = len(ent), int(cl["provisional"].sum())
    hv = HIPER["vade"]
    neu, bk, ex, enc, con, lg = (A["neutralizacion"], A["baskonia"], A["exito"], A["encaje"], A["continuidad"], A["ligas"])
    bar = _leer_json(R / "barrido_k.json") or A["barrido_k"]
    cons = reg.get("consenso") or {}
    cons4 = reg4.get("consenso") or {}
    semillas = V.get("semillas", C.SEMILLAS)
    n_sem = len(semillas)
    tam_cons = np.bincount(np.load(R / "vade" / "consenso.npy"), minlength=C.N_ESTILOS) if (R / "vade" / "consenso.npy").exists() else np.array([0])
    r2 = np.array(neu["r2_club"])
    top_r2 = np.argsort(-r2)[:4]
    c_antes = np.array(neu["corr_nivel_antes"])
    ed, ec, ea = enc["d_nivel~distancia"], enc["d_cuota~distancia"], enc["d_nivel~afinidad"]
    dist_l = lg["distancias"]
    cerca = lambda l: ", ".join([f"{LIGAS[m]} ({n(v)})" for m, v in sorted(dist_l[l].items(), key=lambda x: x[1]) if m != l][:2])  # noqa: E731
    hay = lambda c: (R / "historial" / c).exists()  # noqa: E731
    ac_23 = _acuerdo("v2_8estilos", "v3_6estilos") if hay("v2_8estilos") and hay("v3_6estilos") else {}
    ac_34 = _acuerdo("v3_6estilos", "v4_6estilos_box") if hay("v3_6estilos") and hay("v4_6estilos_box") else {}
    ac_v4 = _acuerdo("v4_6estilos_box", "") if hay("v4_6estilos_box") else {}
    c3 = CENTRALIDAD_V3
    sem4 = V4.get("semillas", C.SEMILLAS)
    a4 = cons4.get("ari_final_semillas") or []
    c4 = {"todas": V4.get("ari_final_semillas_medio"), "consenso": cons4.get("ari_final_consenso"),
          "nuevas": float(np.mean([a for s_, a in zip(sem4, a4) if s_ not in C.SEMILLAS[:5]])) if a4 else None}
    g = _campo
    mil = lambda x: f"{int(x):,}".replace(",", ".")  # noqa: E731
    rasgo = {r.col: k for k, r in enumerate(C.RASGOS)}

    # ---------------------------------------------------------------- jugada a jugada, contexto y química
    cal = _leer_json(C.RAIZ / "data" / "modelos" / "pista" / "calibracion.json") or {}
    acierto = [v["acierto"] for v in cal.values()]
    val = (_leer_json(C.RAIZ / "data" / "artifact" / "normalizacion" / "resumen.json") or {}).get("validacion", {})
    mej = lambda m: val.get(m, {}).get("todos", {}).get("mejora_AB")  # noqa: E731
    casos_val = val.get("rapm", {}).get("todos", {}).get("casos")
    ps = C.RAIZ / "data" / "modelos" / "contexto" / "sensibilidad.csv"
    S = pd.read_csv(ps).set_index("metrica") if ps.exists() else pd.DataFrame()
    bta = lambda m: n(S.at[m, "beta_comp"], 2, True) if m in S.index else "–"  # noqa: E731
    btr = lambda m: n(S.at[m, "beta_riv"], 2, True) if m in S.index else "–"  # noqa: E731
    claras = int((S["beta_comp"].abs() > 2 * S["beta_comp_se"]).sum()) if len(S) else 0
    claras_riv = int((S["beta_riv"].abs() > 2 * S["beta_riv_se"]).sum()) if len(S) else 0
    IN = _leer_json(R / "interacciones.json") or {}
    EF, SIN = IN.get("efectos", {}), IN.get("sinergia", {})
    import glob as _glob
    pares = pd.concat([pd.read_csv(q, usecols=["liga", "temporada"]) for q in sorted(_glob.glob(str(C.RAIZ / "data" / "modelos" / "interacciones" / "efectos_*.csv.gz")))]) \
        if _glob.glob(str(C.RAIZ / "data" / "modelos" / "interacciones" / "efectos_*.csv.gz")) else pd.DataFrame(columns=["liga", "temporada"])
    try:
        from .exportar import CLAVE_CTX
    except Exception:  # noqa: BLE001
        CLAVE_CTX = []
    est_ids = IN.get("estilos", list(est["estilo"]))

    def mat(k, cual="matriz"):
        return np.array(EF[k][cual]) if k in EF else np.zeros((C.N_ESTILOS, C.N_ESTILOS))

    def filas_signo(k):
        """Estilos de X ordenados por el efecto medio sobre los seis estilos de Y, con su rango y celdas claras."""
        M, SE = mat(k), mat(k, "matriz_se")
        out = [{"s": est_ids[i], "media": M[i].mean(), "min": M[i].min(), "max": M[i].max(),
                "claras": int((np.abs(M[i]) > 2 * SE[i]).sum())} for i in range(len(M))]
        return sorted(out, key=lambda r: r["media"])

    def rango(r):
        return f'{n(r["min"], 1, True)} a {n(r["max"], 1, True)}'

    def celda(k, i, j):
        M = mat(k)
        return f"{sn(est_ids[i])} → {sn(est_ids[j])} ({n(M[i, j], 1, True)})"

    fc, fe, fa = filas_signo("cuota_tiro"), filas_signo("efg"), filas_signo("pct_asistidas")
    Mc = mat("cuota_tiro")
    ic_max = np.unravel_index(np.argmax(Mc), Mc.shape)
    SM, SSE = np.array(SIN.get("matriz", np.zeros((C.N_ESTILOS, C.N_ESTILOS)))), np.array(SIN.get("matriz_se", np.ones((C.N_ESTILOS, C.N_ESTILOS))))
    tri = [(SM[i, j], SSE[i, j], i, j) for i in range(len(SM)) for j in range(i + 1)]
    tri_o = sorted(tri, key=lambda x: -x[0])
    par_txt = lambda x: (f"dos {sn(est_ids[x[2]])}" if x[2] == x[3] else f"{sn(est_ids[x[3]])} con {sn(est_ids[x[2]])}") + f" ({n(x[0], 2, True)} ± {n(x[1], 2)})"  # noqa: E731
    peor = tri_o[-1]
    fila_peor = SM[peor[2]]
    neg_peor = int((fila_peor < 0).sum())
    neg_peor_claras = int((fila_peor < -2 * SSE[peor[2]]).sum())
    seis = lambda k: "todos los estilos" if k == C.N_ESTILOS else f"{k} de los {C.N_ESTILOS} estilos"  # noqa: E731
    baja_todos = lambda r: "baja en los seis estilos de Y" if r["max"] < 0 else "baja de media"  # noqa: E731
    gam = np.array(EF.get("cuota_tiro", {}).get("nivel_x_por_estilo_y", [0] * C.N_ESTILOS))
    gse = np.array(EF.get("cuota_tiro", {}).get("nivel_x_por_estilo_y_se", [1] * C.N_ESTILOS))
    g_min = int(np.argmin(gam))
    ef_ = lambda k, c="nivel_x": n(EF[k][c], 2, True) if k in EF else "–"  # noqa: E731

    # ---------------------------------------------------------------- tablas
    t_rasgos = tabla(["Bloque", "Rasgo", "Origen", "Transf.", "R² del nivel (clubes)"],
                     [[r.bloque, e(r.nombre), e(r.origen), {"id": "—", "raiz": "√x", "log1": "log(1+x)", "proporcion": "arcsen √p"}.get(r.transf, r.transf), pc(r2[k])]
                      for k, r in enumerate(C.RASGOS)], {4})
    filas_cal = []
    for l in LIGAS:
        v = {k: x for k, x in cal.items() if k.split("|")[0] == l}
        if not v:
            continue
        a_ = [x["acierto"] for x in v.values()]
        filas_cal.append([LIGAS[l], UNIDADES_PISTA.get(l, "–"), "/".join(sorted({x["regla"].upper() for x in v.values()})), len(v),
                          f"{pc(min(a_), 1)} – {pc(max(a_), 1)}"])
    t_pista = tabla(["Liga", "Coordenadas de la fuente", "Línea de 3", "Ligas-temporada", "Separa 2 y 3 (mín. – máx.)"], filas_cal, {3, 4})
    nl = pd.DataFrame(neu["nivel_por_liga"]).set_index("liga")
    cnt = ent.groupby("liga").size()
    t_ligas = tabla(["Liga", "Clubes-temporada (2020-26)", "Nivel medio (z)", "Desv. del nivel"],
                    [[LIGAS[l], int(cnt.get(l, 0)), n(nl.loc[l, "mean"], 2, True), n(nl.loc[l, "std"])] for l in LIGAS if l in nl.index],
                    {1, 2, 3})
    t_hiper = tabla(["Hiperparámetro", "Valor"], [
        ["Arquitectura", f"{NR} → 64 → 32 → (μ, log σ²) ∈ ℝ³; decodificador 3 → 32 → 64 → {NR}; GELU (aprox. tanh)"],
        ["Capa de salida", f"{C.N_ESTILOS} neuronas; mezcla gaussiana de covarianza completa, π uniforme"],
        ["Parámetros entrenables", f"{n_par:,}".replace(",", ".")],
        ["Muestras por época", f"{n_cl} clubes + {n_cl * C.BOOTSTRAP_POR_CLUB:,} plantillas remuestreadas + jugadores con 150+ min (peso {n(C.PESO_JUGADORES, 1)})".replace(",", ".")],
        ["Remuestreo de plantilla", f"minutos × Gamma({C.K_GAMMA:g}, 1/{C.K_GAMMA:g}); {C.BOOTSTRAP_POR_CLUB} por club"],
        ["Optimizador", f"Adam, tasa {hv['lr']:g} (coseno), lote {hv['lote']}, decaimiento {hv['wd']:g}"],
        ["Épocas", f"{hv['epocas_pre']} de preentreno + {hv['epocas']} + {hv['epocas_afinado']} de ajuste fino (tasa {hv['lr_afinado']:g})"],
        ["Peso del estrés MDS", f"λ = {hv['lambda_estres']:g}"],
        ["Calentamiento de β", f"0,1 → 1 en {hv['calentamiento']} épocas"],
        ["Paso M", f"amortiguación {hv['amortiguacion']:g}; suelo de varianza {pc(hv['suelo_var'])} de la varianza media; resiembra < {pc(hv['min_cuota'])}"],
        ["Semillas", f"{n_sem}: " + ", ".join(str(s) for s in semillas) + "; consenso por co-asociación y enlace medio"],
        ["Neutralización", "regresión en [1, L, L²] por rasgo; residuo reescalado a desviación 1"],
    ])
    col_it = [k for k, *_ in ITERACIONES if k in H]
    lab_it = {k: lab for k, _, _, lab in ITERACIONES}
    filas_it = [("Rasgos de entrada", lambda x: x.get("_nr"), 0),
                ("Estilos (neuronas de salida)", lambda x: len(x["tamanos"]), 0), ("Nivel explicado por el estilo (η²)", "eta2_nivel", 3),
                ("Estilo ligado a la liga (NMI)", "nmi_estilo_liga", 3), ("Pureza de liga media", "pureza_liga_media", 2),
                ("Seguridad media de la asignación", "salida_max_media", 2), ("Estilo más pequeño (clubes)", "tamano_min", 0),
                ("Estabilidad de los estilos entre semillas (ARI)", "ari_semillas_medio", 2), ("Centralidad del modelo (ARI con semillas)", "ari_final_semillas_medio", 2),
                ("Estabilidad del mapa (r)", "estabilidad_mapa", 3), ("Reproducibilidad temporal (ARI)", "ari_temporal_reserva", 2),
                ("Robustez al reparto de minutos", "robustez_reparto_minutos", 2), ("Trustworthiness (k = 10)", "trustworthiness_k10", 3),
                ("Silueta en los rasgos de entrada", "silueta_rasgos", 3), ("Mahalanobis mínima entre estilos", "diferenciacion.mahalanobis_min", 2),
                ("Replicabilidad de perfiles (r)", "replicabilidad.correlacion_media", 2), ("Persistencia del estilo", "persistencia.mismo_estilo", 2)]
    for k in col_it:
        H[k]["_nr"] = NR if k == "final" else 13

    def val_(x, f):
        try:
            return f(x) if callable(f) else g(x, f)
        except (KeyError, TypeError):
            return None
    t_it = tabla([f"Métrica ({n_cl} clubes, 2020-26)"] + [lab_it[k] for k in col_it],
                 [[nm] + [n(val_(H[k], f), dd) for k in col_it] for nm, f, dd in filas_it]
                 + [["Parejas de estilos distintas (Holm 5 %)"] + [f'{H[k]["diferenciacion"]["pares_distintos_holm_05"]}/{H[k]["diferenciacion"]["pares"]}' for k in col_it]],
                 set(range(1, len(col_it) + 1)), "corr")
    filas_est = []
    for k, r in est.iterrows():
        ligas = json.loads(r["ligas"].replace("'", '"'))
        top = ", ".join(f"{LIGAS[l]} {pc(v)}" for l, v in sorted(ligas.items(), key=lambda x: -x[1])[:2])
        filas_est.append([f'{sw(k)}<b>{e(nombre(r["estilo"]))}</b><br><span class="clave">{r["estilo"]}</span>',
                          e(nom.get(r["estilo"], {}).get("resumen", r["descriptor"])), int(r["clubes"]),
                          n(r["nivel_medio"], 2, True), top])
    t_est = tabla(["Estilo", "Rasgos que lo definen", "Clubes", "Nivel", "Ligas principales"], filas_est, {2, 3})
    filas_bk = []
    for r in bk["temporadas"]:
        k = int(r["estilo"][1:]) - 1
        filas_bk.append([r["temporada"] + ("*" if r["provisional"] else ""), LIGAS[r["liga"]], f'{sw(k)}{e(nombre(r["estilo"]))}',
                         n(r["p"]), n(r["nivel"], 2, True),
                         ", ".join(f'{e(m["club"])} ({n(m["d"])})' for m in r["mas_parecidos"][:3]),
                         n(r.get("desplazamiento")) + (f' (p{n(r.get("pct_desplazamiento"), 0)})' if r.get("desplazamiento") is not None else "")])
    t_bk = tabla(["Temp.", "Competición", "Estilo", "p", "Nivel", "Clubes más parecidos esa temporada (distancia)", "Cambio"], filas_bk, {3, 4, 6})
    t_enc = tabla(["Modelo (MCO, errores HC3)", "Coeficiente", "IC 95 %", "p", "R²"],
                  [[f"Δ nivel ~ {x}", n(m["coef"], 3, True), f'{n(m["ic95"][0], 3, True)} a {n(m["ic95"][1], 3, True)}', p_txt(m["p"]), n(m["r2"], 3)]
                   for x, m in (("distancia", ed), ("afinidad", ea), ("distancia (Δ cuota de minutos)", ec))], {1, 3, 4})
    t_ter = tabla(["Tercil de distancia", "n", "Distancia media", "Δ nivel medio", "Δ cuota de minutos"],
                  [[r["tercil"], r["n"], n(r["distancia"]), n(r["d_nivel"], 3, True), n(100 * r["d_cuota"], 1, True) + " pp"] for r in enc["por_tercil"]], {1, 2, 3, 4})
    t_con = tabla(["Cuartil de continuidad", "n", "Continuidad media", "Desplazamiento en el mapa", "Conserva el estilo"],
                  [[r["cuartil"], r["n"], pc(r["continuidad"]), n(r["desplazamiento"]), pc(r["mismo_estilo"])] for r in con["por_cuartil"]], {1, 2, 3, 4})
    unid = {"cuota_tiro": "pp", "efg": "pp", "pct_asistidas": "pp", "pct_aro": "pp", "pts100": "puntos"}
    t_mvp = tabla(["Efecto sobre Y", "Qué mide", "Parejas", "Nivel del compañero X", "Nivel del propio Y"],
                  [[f'{e(v["nombre"])} ({unid.get(k, "")})', e(v["descripcion"]), f'{v["n"]:,}'.replace(",", "."),
                    f'{n(v["nivel_x"], 2, True)} ± {n(v["nivel_x_se"], 2)}', f'{n(v["nivel_y"], 2, True)} ± {n(v["nivel_y_se"], 2)}']
                   for k, v in EF.items()], {2, 3, 4})
    t_ej = tabla(["Movimiento", "Jugador", "Procedencia", "Minutos", "Estilo propio", "Distancia al club (percentil)", "Afinidad"],
                 [["Fichaje", e(f["nombre_completo"]), f'{e(f["equipo"])} ({LIGAS[f["liga"]]})', n(f["min"], 0), f'{sw(f["e"])}{e(nombre(est.iloc[f["e"]]["estilo"]))}',
                   f'{n(f["d"])} (p{n(f["pct"], 0)})', n(f["afin"])] for f in EJ["fichajes"]]
                 + [["Baja", e(b["nombre_completo"]), "plantilla", n(b["min"], 0), f'{sw(b["e"])}{e(nombre(est.iloc[b["e"]]["estilo"]))}', "–", "–"] for b in EJ["bajas"]],
                 {3, 5, 6})
    sig_ex = ex["p_estilo_dado_nivel"] is not None and ex["p_estilo_dado_nivel"] < 0.05
    por_ex = sorted(ex["por_estilo"], key=lambda r: -r["resid"])
    mejor_ex, peor_ex = por_ex[0], por_ex[-1]
    sig_enc = ed["p"] < 0.05
    t_riesgos = tabla(["Riesgo", "Qué puede pasar", "Prob.", "Impacto", "Mitigación"], [
        ["Leer el estilo como una categoría rígida", "Tratar a dos clubes como opuestos por tener etiquetas distintas cuando están en la frontera", "Alta", "Medio",
         f"Leer siempre la probabilidad de la neurona ganadora y la distancia en el mapa; el Atlas muestra el reparto entre los {C.N_ESTILOS} estilos"],
        ["Confundir encaje con rendimiento", "Fichar por parecido de estilo esperando que el jugador rinda más", "Media", "Alto",
         f"El encaje no predice el rendimiento ({p_txt(ed['p'])}, coeficiente {n(ed['coef'], 3, True)}); la capa de nivel se valora aparte"],
        ["Leer la química como causal", "Fichar por la matriz de sinergia esperando el efecto medio de una celda", "Media", "Medio",
         "Son asociaciones a igual nivel con errores bootstrap; mirar el error de cada celda y contrastar con vídeo y cuerpo técnico"],
        ["Simulación demasiado literal", "El jugador no reproduce en el nuevo club su perfil anterior (otro rol, otros minutos, otro entrenador)", "Media", "Medio",
         "Usar la simulación para comparar escenarios entre sí; proyectar sus números al contexto del destino (sección 6.1) y probar varios repartos de minutos"],
        ["Errores heredados de la normalización", "Traducciones A+B sesgadas en ligas con pocos jugadores puente o en muestras pequeñas", "Baja", "Medio",
         "Mínimo de 100 minutos por jugador; columna de fuente (A+B o sólo A); revisar los casos de pocos minutos"],
        ["Coordenadas de tiro mal calibradas", "Un cambio del sistema de coordenadas de una fuente desplaza las zonas de tiro", "Baja", "Medio",
         f"Calibración automática por liga y temporada contra la línea de triple; sin zonas si separa 2 y 3 en menos del 95 % (hoy, {pc(min(acierto), 1) if acierto else '–'} o más)"],
        ["Datos provisionales de 2026-27", "Estilos que cambian a medida que avanza la temporada", "Alta", "Bajo",
         "Marcados como provisionales; no entran en el entrenamiento; reevaluar con cada carga"],
        ["Deriva temporal", "Cambios de reglas o de tendencia (más triple, más ritmo) que desplazan a todos los clubes", "Media", "Medio",
         f"Reentrenar cada verano y vigilar la reproducibilidad temporal (ARI {n(V.get('ari_temporal_reserva'), 2)}) y la replicabilidad"],
        ["Posiciones estimadas", "Cuotas de interiores y exteriores con error en EuroLeague, EuroCup, LBA y parte de la G League", "Media", "Bajo",
         f"Son 2 de {NR} rasgos; sustituir por posiciones oficiales cuando existan"],
        ["Fronteras inestables entre estilos", "Un club cambia de etiqueta al reentrenar sin haber cambiado de juego, sobre todo si cambian los rasgos", "Media", "Bajo",
         f"Consenso de {n_sem} semillas; robustez al reparto de minutos {pc(V.get('robustez_reparto_minutos'))}; usar la distancia, más estable (r = {n(V.get('estabilidad_mapa'), 2)}); revisar los nombres en cada versión"],
        ["Fuentes de datos externas", "Cambios en las webs de las ligas que rompen la extracción", "Media", "Medio",
         "Pruebas automáticas del extractor y validación de totales por equipo en cada carga"],
        ["Uso fuera de la dirección deportiva", "Interpretaciones sin contexto si el Atlas se comparte", "Baja", "Medio",
         "El Atlas es privado; compartir con una nota de uso y el artículo"],
    ])

    # ---------------------------------------------------------------- numeración de figuras, tablas y secciones
    ORDEN_FIG = ["arquitectura", "iteraciones", "mapas_iter", "correspondencia", "entrenamiento", "ari_semillas", "neutralizacion",
                 "perfiles", "mapa", "liga_estilo", "baskonia", "barrido", "exito", "sensibilidad", "quimica", "sinergia", "simulacion"]
    fn = {k: i + 1 for i, k in enumerate([k for k in ORDEN_FIG if F.get(k)])}
    fr = lambda k: f"Figura {fn[k]}" if k in fn else "figura no disponible"  # noqa: E731
    ORDEN_TAB = ["rasgos", "pista", "ligas", "hiper", "iter", "estilos", "baskonia", "encaje", "terciles", "continuidad", "mvp", "ejemplo", "riesgos"]
    tn = {k: i + 1 for i, k in enumerate(ORDEN_TAB)}

    def fig(clave, pie, ancho="100%"):
        if not F.get(clave):
            return ""
        return figura(F[clave], fn[clave], pie, ancho)

    def tcap(clave, texto):
        return f'<p class="tcap"><b>Tabla {tn[clave]}.</b> {texto}</p>'

    # ---------------------------------------------------------------- cifras para el texto
    ultimo = {l: [r for r in bk["temporadas"] if r["liga"] == l and not r["provisional"]][-1] for l in ("euroleague", "acb")}
    hoy = date.today().strftime("%d-%m-%Y")
    pur_max = max(((l, v, r["estilo"]) for _, r in est.iterrows() for l, v in json.loads(r["ligas"].replace("'", '"')).items()), key=lambda x: x[1])
    desp_bk = [r["pct_desplazamiento"] for r in bk["temporadas"] if r.get("pct_desplazamiento") is not None and not r["provisional"]]
    bk_el = [r for r in bk["temporadas"] if r["liga"] == "euroleague" and not r["provisional"]]
    mas_rep = pd.Series([r["estilo"] for r in bk_el]).value_counts()
    rep_top = [s_ for s_, c_ in mas_rep.items() if c_ == mas_rep.iloc[0]]
    txt_rep = (f"«{e(nombre(rep_top[0]))}» es el estilo más repetido del equipo de EuroLeague ({mas_rep.iloc[0]} de {len(bk_el)} temporadas)"
               if len(rep_top) == 1 else
               " y ".join(f"«{e(nombre(s_))}»" for s_ in rep_top) + f" son los estilos más repetidos del equipo de EuroLeague ({mas_rep.iloc[0]} de {len(bk_el)} temporadas cada uno)")
    signo_enc = "positivo" if ed["coef"] > 0 else "negativo"
    kk = bar["k"]
    previo = "bic_diag" in bar
    k_est = "estabilidad" if previo else "estabilidad_kmedias"
    est_k = lambda k: bar[k_est][kk.index(k)] if k in kk else None  # noqa: E731
    bic_c, icl_c = ("bic_diag", "icl_diag") if previo else ("bic_rasgos", "icl_rasgos")
    k_bic, k_icl = kk[int(np.argmin(bar[bic_c]))], kk[int(np.argmin(bar[icl_c]))]
    bic_v = lambda k: bar[bic_c][kk.index(k)]  # noqa: E731
    k_full = kk[int(np.argmin(bar["bic_full"]))] if previo else None
    par_full = NR + NR * (NR + 1) // 2 + 1
    a0, a1 = EJ["antes"], EJ["despues"]
    cambia = a0["e"] != a1["e"]
    # v4 → final: los mayores trasvases de clubes entre estilos
    if hay("v4_6estilos_box"):
        x4, xf = _etiquetas("v4_6estilos_box").align(_etiquetas(""), join="inner")
        ct = pd.crosstab(x4, xf)
        flujos = sorted(((ct.at[i, j], i, j, ct.loc[i].sum()) for i in ct.index for j in ct.columns), reverse=True)[:3]
        txt_flujos = "; ".join(f"{c_} de los {t_} clubes de «{e(nombre4(i))}» pasan a {sn(j)}" for c_, i, j, t_ in flujos)
    else:
        txt_flujos = ""
    mejora = lambda a_, b_: "sube" if a_ > b_ else "baja"  # noqa: E731
    n_pares = len(pares)
    n_ligas_p, n_temp_p = pares["liga"].nunique(), pares["temporada"].nunique()
    n_reg = EF.get("cuota_tiro", {}).get("n", 0)
    cr = lambda m: f"{pc(r2[rasgo[m]])}" if m in rasgo else "–"  # noqa: E731
    menos_mas = lambda m: "menos" if c_antes[rasgo[m]] < 0 else "más"  # noqa: E731

    cuerpo = f"""
<h1>Seis estilos de juego independientes del nivel en ocho ligas de baloncesto</h1>
<p style="font-size:12.5pt;margin-top:-2pt;color:#6b4f38;text-align:left">Un autoencoder variacional de mezcla gaussiana con rasgos de caja y de jugada a jugada para comparar clubes, buscar jugadores parecidos, simular fichajes y medir la química entre estilos en Saski Baskonia</p>
<div class="autores">Dirección Deportiva · Saski Baskonia &nbsp;|&nbsp; Modelado y análisis: Claude Code (Anthropic) &nbsp;|&nbsp; {hoy} &nbsp;|&nbsp; Código: paquetes <code>bbestilo</code> y <code>bbmodel</code>, rama <code>claude/basketball-stats-extractor-jpas93</code></div>

<div class="resumen ejecutivo">
<p class="rt">Resumen ejecutivo</p>
<ul>
<li><b>Qué es.</b> Un modelo que asigna a cada club, competición y temporada de las ocho ligas uno de <b>seis estilos de juego</b> y lo sitúa, con sus jugadores, en un mapa 3D. Trabaja sobre {NR} rasgos normalizados a la vara EuroLeague ({n_caja} de estadística de caja y {n_pbp} de jugada a jugada: dónde se tira y cuántas canastas llegan de pase) y <b>quita el nivel</b>: dice cómo juega un equipo, no cuán bueno es (el estilo sólo explica el {pc(V["eta2_nivel"], 1)} del nivel de los clubes).</li>
<li><b>Cuánto fiarse.</b> La red asigna el estilo con una seguridad media de {n(V["salida_max_media"], 2)}; el mapa es casi idéntico entre {n_sem} redes entrenadas por separado (r = {n(V["estabilidad_mapa"], 2)}) y los perfiles de los estilos se repiten entre 2020-23 y 2023-26 (r = {n(V["replicabilidad"]["correlacion_media"], 2)}). Las fronteras entre estilos son más débiles que el mapa: el estilo es un continuo y la distancia entre clubes es la medida más fiable.</li>
<li><b>Cómo se llegó.</b> Cinco iteraciones: 12 estilos sin tratar el nivel (los estilos reflejaban la liga y la calidad), 8 con el nivel neutralizado, 6 (los que piden los criterios estadísticos), una v4 sólo con la red VaDE y consenso de {n_sem} redes, y el modelo final, que añade los {n_pbp} rasgos de jugada a jugada. Éstos mejoran la estabilidad y redefinen buena parte de los estilos (acuerdo con la v4: ARI = {n(ac_v4.get("ari"), 2)}).</li>
<li><b>Baskonia.</b> En 2025-26 juega «{e(nombre(ultimo["euroleague"]["estilo"]))}» en la EuroLeague y «{e(nombre(ultimo["acb"]["estilo"]))}» en la Liga Endesa. Es de los clubes que más cambian de estilo de un año a otro (mediana de sus cambios en el percentil {n(float(np.median(desp_bk)), 0)}).</li>
<li><b>Lo que dicen los datos.</b> {"A igual nivel, el estilo se asocia con ganar (" + pc(ex["eta2_parcial_estilo"], 0) + " del net rating que no explica el nivel)" if sig_ex else "A igual nivel, el estilo no se asocia con ganar"}; parecerse al estilo del nuevo club <b>no</b> mejora el rendimiento del fichaje; cada 10 puntos de continuidad de la plantilla multiplican por {n(con["or_mismo_estilo_por_10pp"], 2)} la probabilidad de conservar el estilo; y la química entre estilos importa: a igual nivel, la mejor pareja de compañeros, {par_txt(tri_o[0])}, rinde esos puntos por 100 posesiones por encima de lo que predice su RAPM, y la peor es {par_txt(peor)}.</li>
<li><b>Contexto.</b> Los números de un jugador dependen de con quién juega: con compañeros mejores usa menos balón (USG% {bta("usg_pct")} desviaciones por unidad de nivel) y más de sus canastas son asistidas ({bta("pct_asistidas")}). El modelo mide esa sensibilidad y la usa para proyectar a un fichaje al entorno de su nuevo club.</li>
<li><b>Cómo usarlo.</b> El Atlas de Estilos permite comparar clubes y ligas, buscar clubes que juegan como Baskonia y jugadores parecidos, y <b>simular varios fichajes y bajas a la vez</b> para ver cómo cambiaría el estilo y la cohesión de la plantilla.</li>
<li><b>Riesgos principales.</b> Leer la etiqueta como una categoría rígida, tomar el encaje o la química como predicción de rendimiento y tomar la simulación al pie de la letra (sección 11).</li>
</ul>
</div>

<div class="resumen">
<p><b>Resumen.</b> Se presenta un modelo que asigna a cada club, competición y temporada uno de seis estilos de juego y lo sitúa, junto con sus jugadores, en un mapa tridimensional común. Los datos son los equivalentes EuroLeague de un estudio previo de normalización entre ligas (algoritmos A y B), agregados por minutos para {n_cl} clubes-temporada de ocho competiciones entre 2020-21 y 2025-26 (más {n_prov} de 2026-27, provisionales). A los {n_caja} rasgos de estadística de caja se añaden {n_pbp} de jugada a jugada (porcentaje de tiros en el aro, de media distancia y triples de esquina, y de canastas asistidas), para los que las coordenadas de tiro de ocho fuentes con sistemas distintos se calibran automáticamente con la línea de triple oficial. Como la vara común traslada el nivel de cada liga a las métricas de estilo, cada uno de los {NR} rasgos se depura de la parte explicada por un índice de calidad, que explicaba hasta el {pc(r2.max())} de algunos rasgos. El modelo es un VaDE (autoencoder variacional con previa de mezcla) de {mil(n_par)} parámetros con una capa latente de tres neuronas (el mapa) y una capa de salida de seis (los estilos), covarianzas completas, regularización de estrés MDS, consenso de {n_sem} semillas y ajuste fino desde el consenso. Se documentan las cinco iteraciones que llevaron a él (12, 8 y 6 estilos con una red IDEC de contraste en las tres primeras, consenso ampliado y rasgos de jugada a jugada).</p>
<p>En el modelo final el estilo explica el {pc(V["eta2_nivel"], 1)} del nivel (v1: {pc(V1.get("eta2_nivel"), 0)}) y la información compartida entre estilo y liga es {n(V["nmi_estilo_liga"], 2)} (v1: {n(V1.get("nmi_estilo_liga"), 2)}). Las {V["diferenciacion"]["pares"]} parejas de estilos difieren en pruebas de permutación con corrección de Holm ({V["diferenciacion"]["pares_distintos_holm_05"]} significativas), los perfiles se replican entre periodos (r = {n(V["replicabilidad"]["correlacion_media"], 2)}) y el mapa es estable (r = {n(V["estabilidad_mapa"], 2)}) y fiel a las distancias del perfil (trustworthiness {n(V["trustworthiness_k10"], 2)}). En el barrido previo al entrenamiento, el ICL tiene su mínimo en K = {k_icl}. A igual nivel, {"el estilo explica un η² parcial del " + pc(ex["eta2_parcial_estilo"], 0) + " del net rating" if sig_ex else "el estilo no explica el net rating"}; en {mil(enc["casos"])} cambios de club, parecerse al estilo del destino no mejora el rendimiento del jugador (coeficiente {n(ed["coef"], 3, True)} por unidad de distancia, de signo {signo_enc}); y la continuidad de la plantilla predice conservar el estilo (OR = {n(con["or_mismo_estilo_por_10pp"], 2)} por cada 10 puntos). Una capa de contexto estima, con efectos fijos de jugador, cuánto cambia cada métrica con el nivel de los compañeros, y {mil(n_pares)} parejas dirigidas de compañeros dan matrices de química estilo × estilo con controles de nivel.</p>
<p class="clave"><b>Palabras clave:</b> baloncesto · estilo de juego · agrupamiento profundo · VaDE · autoencoder variacional · normalización entre ligas · jugada a jugada · zonas de tiro · RAPM · química de quintetos · scouting · simulación de fichajes</p>
</div>

<h2>1. Introducción</h2>
<p>La dirección deportiva necesita responder a preguntas que las estadísticas brutas no permiten comparar entre ligas: cómo ha jugado su equipo en cada temporada y competición, qué clubes de otras ligas juegan de forma parecida, y si uno o varios jugadores que se estudian encajan en esa forma de jugar o añadirían a la plantilla perfiles ajenos al del resto («una oveja de cada madre»). Un estudio previo del club resolvió la comparabilidad del rendimiento individual trasladando las métricas de los jugadores de ocho ligas a la vara de la EuroLeague 2025-26 (algoritmos A, B y su media A+B). Este trabajo construye sobre esos datos un modelo de <i>estilo de juego</i> de los clubes.</p>
<p>El modelo final es el resultado de cinco iteraciones (sección 4). La primera, con doce estilos y dos redes (IDEC y VaDE), mostró que la vara común arrastraba el nivel de cada liga a las métricas de estilo. La segunda neutralizó el nivel, redujo los estilos a ocho y reforzó la red VaDE. La tercera bajó a seis estilos, el número que prefieren los criterios de información, y mejoró la estabilidad. La cuarta retiró la red de contraste y duplicó el número de redes del consenso. La última añade {n_pbp} rasgos de jugada a jugada (dónde tira cada jugador y cuántas de sus canastas llegan de pase), que dan una partición más estable y en buena parte distinta. La sección 6 añade dos capas que no entran en la red: el contexto de nivel de cada jugador (con quién y contra quién juega) y la química entre los estilos de los compañeros.</p>
<p>Las contribuciones son: (i) un procedimiento de neutralización del nivel compatible con la normalización entre ligas y aplicable a cualquier plantilla simulada; (ii) rasgos de tiro por zonas a partir de las coordenadas de ocho fuentes con sistemas distintos, calibradas automáticamente con la línea de triple; (iii) un VaDE con covarianzas completas, regularización de estrés y consenso de semillas, con un mapa 3D compartido por clubes y jugadores; (iv) una evaluación de estabilidad, fidelidad y diferenciación estadística, y su evolución a lo largo de las iteraciones; (v) análisis complementarios sobre el número de estilos, el éxito, el efecto del encaje y la continuidad de las plantillas; (vi) una capa de contexto de nivel y matrices de química estilo × estilo entre compañeros; y (vii) herramientas de decisión: búsqueda de clubes y jugadores parecidos y simulación exacta de varios fichajes y bajas.</p>

<h2>2. Datos</h2>
<h3>2.1 Fuentes, periodo y normalización previa</h3>
<p>Se usan las estadísticas de temporada regular de ocho competiciones (EuroLeague, EuroCup, Liga Endesa, NBA, G League, LBA, BBL y LNB) entre 2020-21 y 2026-27, extraídas de sus fuentes oficiales con el paquete <code>bbstats</code>, incluido su jugada a jugada (tiros con coordenadas, asistencias y quintetos en pista). Cada jugador-liga-temporada tiene su equivalente EuroLeague por dos algoritmos del estudio de normalización: A (bayes empírico para quitar la suerte de las muestras pequeñas y un «tipo de cambio» por liga y métrica estimado por EM con 4.336 jugadores puente) y B (red neuronal multitarea que aprende un «ADN» del jugador separando nivel, liga, temporada, posición y equipo). Se usa la media A+B en la escala transformada de cada métrica, que en el examen fuera de muestra del estudio mejoró en un 20 % la predicción de los cambios de liga frente a la práctica habitual de comparar percentiles. Donde B no tiene al jugador (menos de 150 minutos o la temporada en curso) se usa A. En 2026-27, B sólo traduce cuatro filas, por lo que esa temporada se trata como provisional y no entra en el entrenamiento. Las traducciones cubren el 99-100 % de los minutos jugados en cada liga, y B el 95-97 %.</p>
<h3>2.2 Unidad de análisis y agregación</h3>
<p>La unidad es el club-competición-temporada: Baskonia EuroLeague 2025-26 y Baskonia Liga Endesa 2025-26 son dos observaciones. El vector de un club es la media de los vectores de sus jugadores ponderada por los minutos que jugaron en él, es decir, el perfil medio de los cinco jugadores en pista. La agregación es exacta y lineal en los minutos, lo que permite recalcular el club con uno o varios fichajes, bajas o cualquier otro reparto de minutos. Los rasgos no lineales se construyen con momentos ponderados: la concentración del uso es E<sub>w</sub>[USG²]/E<sub>w</sub>[USG]² (1 = uso repartido) y las cuotas de minutos de interiores y exteriores salen de la posición estimada del estudio. El ritmo no forma parte del estudio de normalización: se añade como el z del ritmo del equipo dentro de su liga y temporada. Los {n_pbp} rasgos de jugada a jugada (sección 2.3) se agregan igual y se transforman con el arcoseno de la raíz, que estabiliza la varianza de una proporción. La Tabla {tn["rasgos"]} recoge los {NR} rasgos.</p>
{tcap("rasgos", f"Los {NR} rasgos de estilo, su origen, la transformación aplicada tras agregar y la parte de su varianza entre clubes que explicaba el índice de nivel antes de neutralizar. A+B (jugada a jugada) = métrica del jugada a jugada normalizada a la vara EuroLeague con los algoritmos A y B.")}
{t_rasgos}
<h3>2.3 Jugada a jugada: zonas de tiro y canastas asistidas</h3>
<p>Los rasgos nuevos salen de la capa de jugada a jugada (<code>bbmodel/pista.py</code> y <code>bbmodel/zonas.py</code>): el porcentaje de los tiros de campo de cada jugador que son en el aro (a menos de 1,8 m), de media distancia (de 4,25 m a la línea de triple) y triples de esquina, y el porcentaje de sus canastas que llegan de una asistencia (la fuente enlaza la asistencia con la canasta). Medir la zona exige resolver un problema previo: cada fuente publica las coordenadas en su propio sistema (Tabla {tn["pista"]}): centímetros o décimas de pie desde el aro, milímetros con los ejes cambiados, porcentaje de la pista completa con dos canastas o unidades propias de media pista. Para cada liga y temporada se ajustan la posición del aro y la escala de modo que la línea de triple oficial (FIBA: arco de 6,75 m y esquinas a 6,60 m; NBA: 7,24 m y 6,71 m) separe lo mejor posible los tiros que la propia fuente anota como de 2 y de 3. En las {len(cal)} ligas-temporada con tiros, la separación acierta entre el {pc(min(acierto), 1) if acierto else "–"} y el {pc(max(acierto), 1) if acierto else "–"} de los tiros; si bajara del 95 %, esa liga-temporada quedaría sin zonas. Donde no hay jugada a jugada (LNB 2020-21), la media del club ignora a los jugadores sin dato y, si falta en todo el club, el rasgo queda en el valor del club medio.</p>
<p>Las cuatro métricas se traducen a la vara EuroLeague con los algoritmos A y B igual que las de caja, con los tiros de campo con coordenadas (o las canastas) como exposición. En el examen fuera de muestra del estudio de normalización ({casos_val or "–"} cambios de liga), A+B reduce el error cuadrático frente a comparar el mismo percentil un {n(mej("pct_aro"), 0)} % en los tiros en el aro, un {n(mej("pct_media"), 0)} % en la media distancia, un {n(mej("pct_t3_esquina"), 0)} % en los triples de esquina y un {n(mej("pct_asistidas"), 0)} % en las canastas asistidas; en el RAPM (Sill, 2010), que no entra en el estilo pero sí en la capa de contexto (sección 6), la mejora es del {n(mej("rapm"), 0)} %.</p>
{tcap("pista", "Sistema de coordenadas de cada fuente y calidad de la calibración automática: proporción de tiros que la línea de triple calibrada clasifica como la propia fuente (2 o 3), en la peor y la mejor temporada.")}
{t_pista}
<h3>2.4 Capa de nivel</h3>
<p>Ocho métricas normalizadas miden cuánto rinde un equipo y no cómo juega: PER, Game Score por 40', Win Shares por 40', ORtg, DRtg, puntos por 100 posesiones, TS% y eFG%. Su media de z con signo (DRtg invertido) define un índice de nivel L para cada club (z entre clubes) y para cada jugador (z entre jugadores con 150 o más minutos, ponderado por minutos). Estas métricas no entran en la red. La Tabla {tn["ligas"]} resume el nivel por liga: la vara común conserva las diferencias de nivel (NBA {n(nl.loc["nba", "mean"], 2, True)}, EuroLeague {n(nl.loc["euroleague", "mean"], 2, True)}, BBL {n(nl.loc["bbl", "mean"], 2, True)}), que son precisamente las que no deben confundirse con el estilo.</p>
{tcap("ligas", "Clubes-temporada de entrenamiento y nivel medio por liga.")}
{t_ligas}

<h2>3. Métodos</h2>
<h3>3.1 Neutralización del nivel</h3>
<p>Para cada rasgo transformado y estandarizado x<sub>k</sub> se ajusta, sobre los clubes de entrenamiento, una regresión en una base cuadrática del nivel y se conserva el residuo reescalado a desviación 1:</p>
<div class="eq">x̃_k = ( x_k − β₀k − β₁k · L − β₂k · L² ) / s_k ,   con β por mínimos cuadrados y s_k la desviación del residuo</div>
<p>Los jugadores tienen su propia regresión (sobre jugadores, ponderada por minutos). El nivel se recalcula para cualquier reparto de minutos (plantillas remuestreadas, fichajes simulados) antes de neutralizar. Esta operación no duplica la normalización entre ligas: la normalización pone a todos los jugadores en la misma escala, condición necesaria para que una regresión común sea válida en ocho ligas; la neutralización quita de los rasgos de estilo la parte que se predice por la calidad, sea cual sea la liga. Por el teorema de Frisch–Waugh–Lovell, los residuos son ortogonales a L y L² en la muestra de ajuste. Las diferencias entre ligas que no se deben al nivel (por ejemplo, el volumen de triples o el ritmo) se conservan.</p>
<h3>3.2 Arquitectura</h3>
<p>La red ({fr("arquitectura")}) es un VaDE (Jiang et al., 2017). Un codificador de dos capas ocultas (64 y 32 neuronas, GELU) produce la media μ<sub>z</sub> y la log-varianza de una posterior gaussiana en ℝ³; μ<sub>z</sub> es el punto del club en el mapa. La previa sobre z es una mezcla de seis gaussianas con covarianza completa, de modo que cada estilo es un elipsoide con su centro, su forma y su orientación. La capa de salida tiene seis neuronas: la probabilidad a posteriori de cada componente, γ<sub>k</sub> = π<sub>k</sub>N(z | μ<sub>k</sub>, Σ<sub>k</sub>) / Σ<sub>j</sub> π<sub>j</sub>N(z | μ<sub>j</sub>, Σ<sub>j</sub>). El estilo asignado es la neurona de mayor salida. El decodificador (3 → 32 → 64 → {NR}) usa una varianza de reconstrucción común a los {NR} rasgos; con una varianza por rasgo, la red de la v1 trataba como ruido rasgos difíciles como el ritmo.</p>
{fig("arquitectura", f"Arquitectura del VaDE final. La entrada son los {NR} rasgos sin nivel; el mapa 3D es la media de la posterior; la capa de salida es la responsabilidad de cada una de las {C.N_ESTILOS} componentes de la mezcla.")}
<h3>3.3 Función de pérdida</h3>
<div class="eq">ℒ = −ELBO + λ · estrés
−ELBO = ½ Σ_j [ (x_j − x̂_j)² / σ²_x + log σ²_x ] + β [ Σ_k γ_k · ½ ( log|Σ_k| + tr(Σ_k⁻¹ diag σ²_z) + (μ_z − μ_k)ᵀ Σ_k⁻¹ (μ_z − μ_k) )
        − Σ_k γ_k log(π_k / γ_k) − ½ Σ_j (1 + log σ²_zj) ]
estrés = Σ_(i&lt;j) ( ‖z_i − z_j‖ − ‖x_i − x_j‖ )² / Σ_(i&lt;j) ‖x_i − x_j‖²     (por lote, escala fija)</div>
<p>El término de estrés de MDS métrico (Kruskal, 1964) hace que la distancia en el mapa se lea en las mismas unidades que la distancia entre perfiles de estilo (desviaciones típicas), que es lo que la dirección deportiva necesita para comparar un club con un jugador. Su peso es λ = {n(hv["lambda_estres"], 0)}{", igual al número de rasgos," if hv["lambda_estres"] == NR else ""} porque el −ELBO suma sobre los {NR} rasgos. β crece de 0,1 a 1 en las primeras {hv["calentamiento"]} épocas para evitar el colapso de la posterior.</p>
<h3>3.4 Entrenamiento y consenso</h3>
<p>Cada época recorre: (a) los {n_cl} clubes reales; (b) {C.BOOTSTRAP_POR_CLUB} plantillas remuestreadas por club, multiplicando los minutos de cada jugador por una Gamma({C.K_GAMMA:g}, 1/{C.K_GAMMA:g}) (coeficiente de variación del 50 %), con su nivel recalculado; y (c) los jugadores con 150 o más minutos, con peso {n(C.PESO_JUGADORES, 1)}, para que el codificador conozca la región donde caen los jugadores sin que éstos definan los estilos. Tras un preentreno como autoencoder determinista con estrés, la mezcla se inicializa por EM sobre el mapa preentrenado. Los parámetros de la red se optimizan con Adam; los de la mezcla no reciben gradiente: tras cada época se reestiman con un paso M amortiguado sobre los clubes (reales y remuestreados), con π uniforme, un suelo de varianza y resiembra de las componentes con menos del 1 % de los clubes. Este esquema evita el colapso en pocas componentes que mostró el VaDE original.</p>
<p>Se entrenan {n_sem} redes con semillas distintas. Su partición de consenso se obtiene de la matriz de co-asociación (fracción de redes que asignan dos clubes al mismo estilo) con agrupamiento jerárquico de enlace medio (Fred y Jain, 2005). La red cuya partición más se parece al consenso (semilla {V.get("semilla_final", "–")}) recibe una mezcla fijada en la media y la covarianza de cada grupo de consenso en su propio mapa, y se ajustan {hv["epocas_afinado"]} épocas más sólo el codificador y el decodificador, de modo que el mapa se adapta a los estilos acordados. Los grupos de consenso tienen entre {int(tam_cons.min())} y {int(tam_cons.max())} clubes. Finalmente, el mapa se orienta con sus ejes principales (eje 1 = mayor varianza), con un signo determinista y una escala única, y los estilos se numeran por la posición de su centro en el eje 1. La Tabla {tn["hiper"]} recoge los hiperparámetros.</p>
{tcap("hiper", "Hiperparámetros del VaDE final.")}
{t_hiper}
<h3>3.5 Evaluación</h3>
<p>Se evalúa sobre los {n_cl} clubes: reparto (entropía, tamaño mínimo); seguridad de la asignación; separación (silueta en el mapa y en los rasgos); estabilidad de los estilos (ARI entre semillas; Hubert y Arabie, 1985) y del mapa (correlación de las distancias club-club entre semillas); robustez al reparto de minutos (40 plantillas remuestreadas por club); reproducibilidad temporal (red entrenada sin 2024-25 ni 2025-26 frente a la red completa, sobre esos clubes); fidelidad del mapa (trustworthiness y continuidad, k = 10; Venna y Kaski, 2001); diferenciación (Mahalanobis entre perfiles medios con covarianza intra-estilo común y prueba de permutación con 9.999 réplicas por pareja y corrección de Holm); replicabilidad de los perfiles entre 2020-23 y 2023-26; y neutralidad (η² del nivel explicado por el estilo, NMI entre estilo y liga). Las mismas métricas se calcularon en todas las iteraciones, lo que permite compararlas (sección 4); las que dependen del espacio de entrada (silueta en los rasgos, trustworthiness, Mahalanobis) se miden en los rasgos de cada iteración: 13 hasta la v4 y {NR} en el modelo final.</p>
<h3>3.6 Análisis complementarios</h3>
<ul>
<li><b>Número de estilos.</b> Antes de entrenar (<code>bbestilo/barrido.py</code>), BIC e ICL (Schwarz, 1978; Biernacki et al., 2000) de mezclas gaussianas con covarianza diagonal y completa sobre los {NR} rasgos sin nivel, silueta y estabilidad de k-medias por submuestreo (80 %, 10 réplicas) y tamaño del grupo más pequeño, de K = {kk[0]} a K = {kk[-1]}.</li>
<li><b>Estilo y éxito.</b> Net rating del equipo estandarizado dentro de su liga y temporada frente al estilo, comparando por F los modelos anidados net ~ L y net ~ L + estilo.</li>
<li><b>Efecto del encaje.</b> Jugadores que cambian de club entre temporadas consecutivas con 300 o más minutos en ambas. La variable explicativa es la distancia en el mapa entre el jugador (temporada t) y su club de destino en la temporada t, antes de su llegada; las respuestas, el cambio en su índice de nivel y en su cuota de minutos. Se controla por nivel inicial, edad (y su cuadrado), cambio de liga y nivel del club de destino, con errores robustos HC3 (MacKinnon y White, 1985).</li>
<li><b>Continuidad.</b> Proporción de los minutos de t+1 jugados por quienes ya estaban en t, frente al desplazamiento del club en el mapa (Spearman) y a conservar el estilo (logit).</li>
<li><b>Ligas y temporadas.</b> Tablas de contingencia estilo × liga y estilo × temporada (χ², V de Cramér) y distancias entre los centroides de liga en el mapa.</li>
</ul>
<h3>3.7 Herramientas de decisión</h3>
<p><b>Simulación de fichajes y bajas.</b> Para un club destino con minutos totales T, un conjunto de bajas B y de fichajes F con minutos m<sub>f</sub>, la plantilla nueva conserva T: los jugadores que siguen reescalan sus minutos por (T − Σm<sub>f</sub>) / (T − Σ<sub>b∈B</sub> m<sub>b</sub>) y cada fichaje entra con su vector de jugador (con el ritmo del club destino). Como la agregación es lineal en los minutos, el vector del club con el escenario es exacto; su nivel se recalcula, se neutraliza y la red da su punto en el mapa y su reparto entre estilos. Por defecto, un fichaje juega su cuota de minutos actual aplicada a T. El cálculo se implementa igual en Python (<code>simular_plantilla</code>) y en el navegador (Atlas), con diferencias máximas de 0,006 en el mapa.</p>
<p><b>Clubes y jugadores parecidos.</b> El parecido se mide en los {NR} rasgos sin nivel y se expresa como 100 menos el percentil de la distancia entre parejas reales del mismo tipo (club-club, jugador-jugador o jugador-su club). Se buscan clubes que juegan como el de referencia y jugadores parecidos a uno dado, o cuyo perfil encaja con el estilo del club, opcionalmente sólo dentro de los clubes más parecidos al de referencia. La puntuación de un jugador combina su parecido y el de su club (por defecto, 0,7 y 0,3).</p>

<h2>4. Iteraciones del modelo</h2>
<p>Las cinco iteraciones usaron los mismos {n_cl} clubes y las mismas métricas de evaluación. La Tabla {tn["iter"]} y la {fr("iteraciones")} resumen su evolución; la {fr("mapas_iter")} muestra el cambio más importante, el de la neutralización del nivel, y la {fr("correspondencia")}, el último, el de los rasgos de jugada a jugada.</p>
<p><b>v1: doce estilos y dos redes.</b> Se entrenaron una IDEC (Xie et al., 2016; Guo et al., 2017), autoencoder con capa de agrupamiento de núcleo t de Student, y un VaDE con covarianzas diagonales, ambas con doce neuronas de salida y sin tratar el nivel. Las dos dieron estilos diferenciables, pero muy ligados a la liga y a la calidad: el estilo explicaba el {pc(V1.get("eta2_nivel"), 0)} del nivel en el VaDE ({pc(I1.get("eta2_nivel"), 0)} en la IDEC) y la información compartida con la liga era {n(V1.get("nmi_estilo_liga"), 2)}. Dos o tres estilos agrupaban casi sólo a clubes NBA. En el mapa de la v1, cada liga ocupa su propia región ({fr("mapas_iter")}, izquierda).</p>
<p><b>v2: ocho estilos con el nivel neutralizado.</b> Se neutralizó el nivel (sección 3.1), se redujeron los estilos a ocho y se reforzó el VaDE: covarianzas completas, paso M amortiguado, consenso de cinco semillas y ajuste fino con la mezcla fijada en el consenso. El estilo pasó a explicar el {pc(V2.get("eta2_nivel"), 1)} del nivel y la NMI con la liga bajó a {n(V2.get("nmi_estilo_liga"), 2)}; las ligas se mezclan en el mapa ({fr("mapas_iter")}, centro). El VaDE asignaba con más seguridad que la IDEC ({n(V2.get("salida_max_media"), 2)} frente a {n(I2.get("salida_max_media"), 2)}) y su mapa era más estable ({n(V2.get("estabilidad_mapa"), 2)} frente a {n(I2.get("estabilidad_mapa"), 2)}), aunque la IDEC separaba algo mejor en los rasgos. Pero el barrido de K de entonces indicaba que los datos respaldaban entre cuatro y seis estilos y la estabilidad de los estilos entre semillas era sólo {n(V2.get("ari_semillas_medio"), 2)}.</p>
<p><b>v3: seis estilos.</b> Con el mismo procedimiento y seis neuronas de salida mejoraron casi todas las métricas de estabilidad y separación: ARI entre semillas {n(V3.get("ari_semillas_medio"), 2)} (v2: {n(V2.get("ari_semillas_medio"), 2)}), reproducibilidad temporal {n(V3.get("ari_temporal_reserva"), 2)} ({n(V2.get("ari_temporal_reserva"), 2)}), silueta en los rasgos {n(V3.get("silueta_rasgos"), 3)} ({n(V2.get("silueta_rasgos"), 3)}) y Mahalanobis mínima {n(g(V3, "diferenciacion.mahalanobis_min") if V3 else None, 2)} ({n(g(V2, "diferenciacion.mahalanobis_min") if V2 else None, 2)}), con la misma neutralidad al nivel. La mayoría de los estilos de ocho se repartieron entre uno o dos de seis{f" (acuerdo entre la v2 y la v3: ARI = {n(ac_23['ari'], 2)}, NMI = {n(ac_23['nmi'], 2)})" if ac_23 else ""}.</p>
<p><b>v4: sólo VaDE y consenso de {len(sem4)} redes.</b> Con la decisión de quedarse con seis estilos y con la red VaDE, se retiró la IDEC del proyecto y el cálculo se dedicó a duplicar el consenso (de cinco a {len(sem4)} semillas), para que la partición dependa menos de un conjunto concreto de redes. La ampliación mostró que la partición de la v3 estaba ligada a sus cinco semillas: frente a las cinco semillas nuevas, su acuerdo medio era ARI = {n(c3["nuevas"], 2)} (v4: {n(c4["nuevas"], 2)}), y con el consenso de las {len(sem4)}, {n(c3["consenso"], 2)} ({n(c4["consenso"], 2)}). Frente al conjunto de las {len(sem4)} redes, la v4 era la partición más central (ARI medio {n(c4["todas"], 2)} frente a {n(c3["todas"], 2)}). Las métricas de acuerdo de la Tabla {tn["iter"]} bajaron algo respecto a la v3 (ARI entre semillas {n(V4.get("ari_semillas_medio"), 2)} frente a {n(V3.get("ari_semillas_medio"), 2)}; reproducibilidad temporal {n(V4.get("ari_temporal_reserva"), 2)} frente a {n(V3.get("ari_temporal_reserva"), 2)}) porque se miden sobre redes más diversas y frente a una red de reserva de una sola semilla, de la que el consenso amplio se aleja: la estimación de la v3 era optimista. La v4 ganó en seguridad ({n(V4.get("salida_max_media"), 2)}), en tamaño del estilo más pequeño ({V4.get("tamano_min", "–")} clubes), en robustez al reparto de minutos ({n(V4.get("robustez_reparto_minutos"), 2)}) y en neutralidad (η² {n(V4.get("eta2_nivel"), 3)}). Su partición coincidía sólo en parte con la de la v3{f" (ARI = {n(ac_34['ari'], 2)}, NMI = {n(ac_34['nmi'], 2)})" if ac_34 else ""}: la etiqueta de los clubes situados entre dos estilos depende del conjunto de redes. La v4 se conserva completa, con sus nombres, en <code>historial/v4_6estilos_box/</code>.</p>
<p><b>v4 → final: jugada a jugada.</b> El modelo final añade a los {n_caja} rasgos de caja de la v4 los {n_pbp} de jugada a jugada de la sección 2.3 (tiros en el aro, media distancia, triples de esquina y canastas asistidas), con el mismo procedimiento: neutralización del nivel, {n_sem} semillas, consenso y ajuste fino. Antes de entrenar se repitió el barrido de K con los {NR} rasgos (sección 5.7): el ICL con covarianza diagonal tiene su mínimo en K = {k_icl}, el BIC es casi plano entre 6 y 11 y la estabilidad de k-medias cae a partir de 6, por lo que se mantuvieron seis estilos. Con la misma configuración, mejoran todas las métricas de acuerdo y de estructura: ARI entre semillas {n(V["ari_semillas_medio"], 2)} (v4: {n(V4.get("ari_semillas_medio"), 2)}), reproducibilidad temporal {n(V["ari_temporal_reserva"], 2)} ({n(V4.get("ari_temporal_reserva"), 2)}), estabilidad del mapa {n(V["estabilidad_mapa"], 3)} ({n(V4.get("estabilidad_mapa"), 3)}), replicabilidad de los perfiles {n(V["replicabilidad"]["correlacion_media"], 2)} ({n(g(V4, "replicabilidad.correlacion_media") if V4 else None, 2)}), Mahalanobis mínima {n(V["diferenciacion"]["mahalanobis_min"], 2)} ({n(g(V4, "diferenciacion.mahalanobis_min") if V4 else None, 2)}) y persistencia del estilo de un año a otro {pc(V["persistencia"]["mismo_estilo"])} ({pc(g(V4, "persistencia.mismo_estilo") if V4 else None)}). La seguridad media de la asignación {mejora(V["salida_max_media"], V4.get("salida_max_media", 0))} a {n(V["salida_max_media"], 2)} ({n(V4.get("salida_max_media"), 2)}) y la neutralidad empeora algo, aunque sigue siendo muy alta: η² del nivel {n(V["eta2_nivel"], 3)} ({n(V4.get("eta2_nivel"), 3)}) y NMI con la liga {n(V["nmi_estilo_liga"], 2)} ({n(V4.get("nmi_estilo_liga"), 2)}). Es previsible: la distribución del tiro por zonas depende en parte de la liga (geometría de la línea de triple, reglamento y cultura de juego), y esas diferencias no se deben al nivel, por lo que la neutralización las conserva.</p>
<p>La partición cambia mucho: frente a la v4, ARI = {n(ac_v4.get("ari"), 2)} y NMI = {n(ac_v4.get("nmi"), 2)} sobre los mismos {n_cl} clubes ({fr("correspondencia")}). Dónde se tira y cómo se llega a la canasta son dimensiones que la estadística de caja sólo veía de forma indirecta (a través del 3PAr, los tiros libres y el rebote ofensivo), y redefinen los estilos: {txt_flujos}. Por eso los estilos se volvieron a nombrar a partir de su nuevo perfil (<code>config/estilos.json</code>); los nombres de la v4 no se aplican al modelo final.</p>
{tcap("iter", f"Evaluación de cada iteración con los mismos clubes y métricas. IDEC = red de contraste (retirada desde la v4). La silueta, la trustworthiness y la Mahalanobis se miden en los rasgos de entrada de cada iteración (13 hasta la v4; {NR} en el modelo final).")}
{t_it}
{fig("iteraciones", f"Evolución de ocho métricas a lo largo de las iteraciones. Puntos rellenos unidos = VaDE; huecos = IDEC; verde = modelo final ({NR} rasgos).")}
{fig("mapas_iter", "Plano de los ejes 1 y 2 del mapa en la v1, la v2 y el modelo final, con cada club coloreado por su liga. Sin neutralizar (v1), las ligas ocupan regiones propias; tras neutralizar el nivel, se mezclan y el mapa ordena estilos, no ligas.")}
{fig("correspondencia", f"Clubes de 2020-21 a 2025-26 según su estilo en la v4 (filas: 13 rasgos de caja, con los nombres de la v4) y en el modelo final (columnas: {NR} rasgos, con jugada a jugada).", "86%")}

<h2>5. Resultados del modelo final</h2>
<h3>5.1 Entrenamiento y estabilidad entre redes</h3>
<p>Las {n_sem} redes convergieron sin colapso: el estilo más pequeño mantuvo en todas las épocas más del {pc(min(r["cuota_min"] for r in reg["registro"]), 0)} de las muestras de club ({fr("entrenamiento")}). El acuerdo medio entre las particiones de dos semillas es ARI = {n(V["ari_semillas_medio"], 2)} (mínimo {n(V["ari_semillas_min"], 2)}); el modelo final coincide con el consenso con ARI = {n(cons.get("ari_final_consenso"), 2)} y con las semillas, de media, con {n(V["ari_final_semillas_medio"], 2)} ({fr("ari_semillas")}). El mapa es mucho más estable que las fronteras: la correlación media de las distancias club-club entre semillas es {n(V["estabilidad_mapa"], 3)}. Los estilos tienen entre {V["tamano_min"]} y {V["tamano_max"]} clubes (entropía del reparto {n(V["entropia_reparto"], 3)}).</p>
{fig("entrenamiento", "Pérdida por época y cuota del estilo más pequeño y más grande durante el entrenamiento de la red base y su ajuste fino desde el consenso.", "88%")}
{fig("ari_semillas", f"Izquierda: acuerdo (ARI) entre las particiones de las {n_sem} semillas. Derecha: acuerdo de cada semilla con la partición de consenso y con el modelo final; línea discontinua: modelo final frente al consenso.", "94%")}
<h3>5.2 Neutralización del nivel</h3>
<p>El nivel explicaba una parte muy grande de varios rasgos de estilo de los clubes: {", ".join(f"{e(C.RASGOS[k].corto)} {pc(r2[k])}" for k in top_r2)} ({fr("neutralizacion")}). Son rasgos en los que, en la vara EuroLeague, los mejores jugadores producen más (rebote, asistencias, tiros libres) o cometen menos faltas. Otros rasgos apenas dependían del nivel (ritmo, rebote ofensivo, concentración del uso, posiciones). Entre los de jugada a jugada, el nivel explicaba el {cr("pct_t3_esquina")} de los triples de esquina y el {cr("pct_asistidas")} de las canastas asistidas (los clubes con mejores jugadores tiran {menos_mas("pct_t3_esquina")} triples de esquina y tienen {menos_mas("pct_asistidas")} canastas asistidas: sus jugadores se fabrican más sus tiros), pero poco de los tiros en el aro ({cr("pct_aro")}) o de media distancia ({cr("pct_media")}). Tras neutralizar, el estilo explica el {pc(V["eta2_nivel"], 1)} de la varianza del nivel y la pureza media de liga de los estilos es {pc(V["pureza_liga_media"])}. {"Ningún estilo tiene más de la mitad de sus clubes en una sola liga; el" if pur_max[1] <= 0.5 else "El"} más concentrado es «{e(nombre(pur_max[2]))}», con un {pc(pur_max[1])} de clubes de la {LIGAS[pur_max[0]]}.</p>
{fig("neutralizacion", "Parte de la varianza entre clubes de cada rasgo de estilo explicada por el índice de nivel (regresión cuadrática) antes de neutralizar.", "82%")}
<h3>5.3 Calidad</h3>
<p>Las {V["diferenciacion"]["pares"]} parejas de estilos son distintas tras la corrección de Holm ({V["diferenciacion"]["pares_distintos_holm_05"]}/{V["diferenciacion"]["pares"]}) y la distancia de Mahalanobis mínima entre perfiles medios es {n(V["diferenciacion"]["mahalanobis_min"], 2)} desviaciones. Estas pruebas son optimistas por construcción, porque los grupos se forman con los mismos datos; la replicabilidad entre periodos (r = {n(V["replicabilidad"]["correlacion_media"], 2)}) no lo es y es la evidencia principal de que los estilos describen algo estable. La silueta en los {NR} rasgos es baja ({n(V["silueta_rasgos"], 3)}; k-medias directo, {n(ev["referencia_kmedias"]["silueta_rasgos"], 3)}): los estilos son una partición útil de un continuo, no grupos separados. La fidelidad del mapa es alta: trustworthiness {n(V["trustworthiness_k10"], 3)}, continuidad {n(V["continuidad_k10"], 3)} y correlación de Spearman entre distancias del mapa y del perfil {n(V["spearman_distancias"], 2)}. Un club conserva su estilo al año siguiente en el {pc(V["persistencia"]["mismo_estilo"])} de los casos (por azar, {pc(V["persistencia"]["por_azar"])}), y al perturbar los minutos de su plantilla, en el {pc(V["robustez_reparto_minutos"])}.</p>
<h3>5.4 Los seis estilos</h3>
<p>La Tabla {tn["estilos"]} y la {fr("perfiles")} describen los seis estilos por su perfil medio (rasgos sin nivel, en desviaciones típicas frente al club medio). Los nombres son interpretativos y se han puesto a partir de esos perfiles; los identificadores E01-E06 ordenan los estilos por el eje 1 del mapa ({fr("mapa")}). Los rasgos de jugada a jugada están entre los que más separan los estilos: «{e(nombre("E01"))}» y «{e(nombre("E06"))}» se oponen sobre todo en los triples de esquina y en las canastas asistidas, y «{e(nombre("E02"))}» y «{e(nombre("E04"))}», en los tiros en el aro.</p>
{tcap("estilos", "Los seis estilos: rasgos que los definen, número de clubes (2020-26), nivel medio (no interviene en la asignación) y ligas con más clubes en el estilo.")}
{t_est}
{fig("perfiles", f"Perfil medio de cada estilo en los {NR} rasgos sin nivel (desviaciones típicas frente al club medio).")}
{fig("mapa", "Proyecciones del mapa 3D: clubes de 2020-21 a 2025-26 coloreados por estilo (forma de marcador como apoyo); rombos = centros de los estilos.")}
<h3>5.5 Ligas y temporadas</h3>
<p>El estilo sigue asociado a la liga, pero de forma moderada (χ² = {n(lg["chi2_liga"], 0)}, V de Cramér = {n(lg["v_cramer_liga"], 2)}, {p_txt(lg["p_liga"])}), lo que es esperable: el reglamento y la cultura de juego de cada liga influyen en cómo se juega a igual nivel ({fr("liga_estilo")}). Las ligas más parecidas en estilo a la EuroLeague son {cerca("euroleague")}; a la Liga Endesa, {cerca("acb")}. La asociación entre estilo y temporada es {"débil pero significativa" if lg["p_temporada"] < 0.05 else "no significativa"} (V = {n(lg["v_cramer_temporada"], 2)}, {p_txt(lg["p_temporada"])}).</p>
{fig("liga_estilo", "Porcentaje de los clubes de cada liga (2020-21 a 2025-26) asignados a cada estilo.", "86%")}
<h3>5.6 Saski Baskonia</h3>
<p>La Tabla {tn["baskonia"]} y la {fr("baskonia")} recogen el estilo de Baskonia en cada temporada y competición, sus tres clubes más parecidos de esa temporada en cualquier liga y el desplazamiento respecto al año anterior (con su percentil entre todos los clubes). En 2025-26, el equipo de EuroLeague se asigna a «{e(nombre(ultimo["euroleague"]["estilo"]))}» (p = {n(ultimo["euroleague"]["p"])}) y el de Liga Endesa a «{e(nombre(ultimo["acb"]["estilo"]))}» (p = {n(ultimo["acb"]["p"])}). {txt_rep}. Baskonia cambia de estilo más que la mayoría de los clubes: la mediana de sus desplazamientos entre temporadas está en el percentil {n(float(np.median(desp_bk)), 0)} de todos los clubes (desplazamiento mediano de un club: {n(bk["desplazamiento_mediano_clubes"])}), coherente con una plantilla que se renueva mucho cada verano.</p>
{tcap("baskonia", "Baskonia por temporada. p = salida de la neurona ganadora; cambio = distancia al punto del año anterior (percentil entre todos los clubes). * provisional.")}
{t_bk}
{fig("baskonia", "Trayectoria de Baskonia en el plano de los ejes 1 y 2 (EuroLeague y Liga Endesa); color del punto = estilo; rombos = centros de los estilos; gris = resto de clubes.", "78%")}
<h3>5.7 Hallazgos complementarios</h3>
<p><b>Número de estilos.</b> El barrido se hizo antes de entrenar la red, sobre los {bar.get("n_clubes", n_cl)} clubes de entrenamiento y los {NR} rasgos sin nivel ({fr("barrido")}). Con covarianza diagonal, el ICL, que penaliza además los grupos solapados, tiene su mínimo en K = {k_icl}; el BIC baja mucho hasta K = 6 (de {n(bic_v(5), 0)} con K = 5 a {n(bic_v(6), 0)}) y después queda casi plano hasta K = 11 (mínimo {n(min(bar[bic_c]), 0)} con K = {k_bic}). {f"Con covarianza completa, ambos criterios prefieren K = {k_full}, porque cada componente añade {par_full} parámetros con sólo {bar.get('n_clubes', n_cl)} clubes. " if previo else ""}La estabilidad de k-medias es {n(est_k(5), 2)} con K = 5 y {n(est_k(6), 2)} con K = 6, y cae a {n(est_k(7), 2)} con K = 7 y {n(est_k(8), 2)} con K = 8. Seis es el número más alto que respaldan a la vez el ICL y la estabilidad, y el que se mantiene.</p>
{fig("barrido", f"Barrido de K previo al entrenamiento ({NR} rasgos sin nivel): criterios de información normalizados con covarianza diagonal, con su mínimo en un círculo (izquierda), y estabilidad y silueta de k-medias (derecha). Línea de puntos: K = {C.N_ESTILOS}.", "92%")}
<p><b>Estilo y éxito.</b> En {ex["clubes"]} clubes con net rating, el nivel explica el {pc(ex["r2_nivel"])} del net rating estandarizado (r = {n(ex["r_nivel_net"], 2)}). Sin controlar el nivel, el estilo explica el {pc(ex["r2_estilo"], 1)} (F = {n(ex["f_estilo_sin_control"], 2)}, {p_txt(ex["p_estilo_sin_control"])}); dado el nivel, {"añade un η² parcial del " + pc(ex["eta2_parcial_estilo"], 1) + f" (F = {n(ex['f_estilo_dado_nivel'], 2)}, {p_txt(ex['p_estilo_dado_nivel'])})" if sig_ex else f"no añade información significativa (F = {n(ex['f_estilo_dado_nivel'], 2)}, {p_txt(ex['p_estilo_dado_nivel'])})"}. Esta asociación tiene una parte mecánica: varios rasgos de estilo (pérdidas, rebote, tiros libres) son los «cuatro factores» de Dean Oliver, que determinan la eficiencia, y la distribución del tiro también la condiciona (la media distancia es el tiro de campo menos eficiente). El estilo con mayor net rating residual es «{e(nombre(mejor_ex["estilo"]))}» ({n(mejor_ex["resid"], 2, True)} σ ± {n(mejor_ex["ic95"], 2)}) y el de menor, «{e(nombre(peor_ex["estilo"]))}» ({n(peor_ex["resid"], 2, True)} σ ± {n(peor_ex["ic95"], 2)}) ({fr("exito")}).</p>
{fig("exito", "Net rating del equipo no explicado por el nivel, por estilo (media e IC 95 %).", "72%")}
<p><b>Efecto del encaje.</b> Se identificaron {mil(enc["casos"])} cambios de club con 300 o más minutos en ambas temporadas. {"La distancia de estilo entre el jugador y su destino se asocia con su cambio de nivel, pero en sentido contrario al de la hipótesis del encaje y con un tamaño muy pequeño" if (sig_enc and ed["coef"] > 0) else ("La distancia de estilo entre el jugador y su destino se asocia con su cambio de nivel" if sig_enc else "La distancia de estilo entre el jugador y su destino no se asocia de forma significativa con su cambio de nivel")} (Tabla {tn["encaje"]}): {n(ed["coef"], 3, True)} por unidad de distancia (IC 95 % {n(ed["ic95"][0], 3, True)} a {n(ed["ic95"][1], 3, True)}, {p_txt(ed["p"])}). Con la afinidad (la salida del jugador en la neurona del estilo del club) el coeficiente es {n(ea["coef"], 3, True)} ({p_txt(ea["p"])}), y sobre la cuota de minutos, {n(100 * ec["coef"], 2, True)} puntos por unidad de distancia ({p_txt(ec["p"])}). La relación no es monótona por terciles (Tabla {tn["terciles"]}; Spearman {n(enc["spearman_distancia_dnivel"], 3)}). Parecerse al estilo del club no es un predictor del rendimiento individual tras el fichaje.</p>
{tcap("encaje", "Efecto del encaje: regresiones con controles de nivel inicial, edad, edad², cambio de liga y nivel del club de destino.")}
{t_enc}
{tcap("terciles", "Cambios de club por tercil de distancia de estilo (medias sin ajustar).")}
{t_ter}
<p><b>Continuidad de plantilla.</b> En {con["parejas"]} pares de temporadas consecutivas, la continuidad media fue {pc(con["continuidad_media"])}. Una plantilla más continua se desplaza menos en el mapa (Spearman {n(con["spearman_continuidad_desplazamiento"], 2)}, {p_txt(con["p_spearman"])}) y conserva más a menudo su estilo: cada 10 puntos de continuidad multiplican por {n(con["or_mismo_estilo_por_10pp"], 2)} la odds de conservarlo ({p_txt(con["p_logit"])}; Tabla {tn["continuidad"]}).</p>
{tcap("continuidad", "Continuidad de plantilla, desplazamiento en el mapa y conservación del estilo, por cuartiles.")}
{t_con}

<h2>6. Contexto de nivel y química de estilos</h2>
<p>El estilo describe cómo juega un equipo a igual nivel, pero los números de un jugador también dependen de con quién juega: no es lo mismo promediar 15 puntos al lado del MVP de la EuroLeague que en un equipo de la BBL. Esta sección añade dos capas construidas con los quintetos del jugada a jugada (<code>docs/contexto_y_quimica.md</code>): el contexto de nivel de cada jugador (6.1) y los efectos entre compañeros, resumidos por estilo (6.2 y 6.3). Ninguna de las dos entra en la red: sirven para leer los perfiles, para proyectar fichajes y para pensar en parejas y quintetos.</p>
<h3>6.1 Contexto de nivel</h3>
<p><b>Medida.</b> El nivel L de cada jugador-liga-temporada es el índice de la sección 2.4, en la vara EuroLeague. En cada tramo del jugada a jugada se toma la media de L de sus cuatro compañeros y de los cinco rivales, ponderada por los segundos del tramo (contexto en pista); además, la media de L de sus compañeros de plantilla ponderada por sus minutos (contexto de plantilla, que existe también donde no hay quintetos: BBL 2020-23 y LNB 2020-21). Cada contexto se expresa como desviación respecto al de un jugador medio de su liga y temporada: la diferencia entre ligas ya la recoge el tipo de cambio de A y B (los jugadores puente cambian de liga y de compañeros a la vez), de modo que aquí sólo cuenta la diferencia dentro de la liga (<code>bbmodel/contexto.py</code>).</p>
<p><b>Sensibilidad.</b> Para cada métrica normalizada se estima cuánto cambia la capacidad de un jugador en la vara EuroLeague (algoritmo A) cuando cambia su entorno, con un efecto fijo de persona: se compara al mismo jugador en plantillas distintas, de modo que su calidad propia no confunde la estimación:</p>
<div class="eq">y_it = α_i + β · Δplantilla_it + β_riv · Δrivales_it + tramos de edad + ε_it     (pesos 1/varianza de y; errores por bootstrap de personas)</div>
<p>Se usa el contexto de plantilla y no el de pista porque el de pista mezcla el rol: quien mejora pasa a jugar con los titulares y su contexto sube por su propio nivel. Con hasta {mil(S["filas"].max()) if len(S) else 0} filas de {mil(S["personas"].max()) if len(S) else 0} jugadores que cambian de entorno (300 o más minutos), {claras} de las {len(S)} métricas tienen un β claro, mayor que dos errores típicos ({fr("sensibilidad")}). Con compañeros una unidad de nivel mejores, el jugador usa menos balón (USG% {bta("usg_pct")} desviaciones típicas), reparte menos (AST% {bta("ast_pct")}) y anota menos por posesión (puntos por 100 posesiones {bta("pts_p100")}), pero más de sus canastas llegan de pase ({bta("pct_asistidas")}) y tira más triples de esquina ({bta("pct_t3_esquina")}): pasa a un papel de acompañante. Su DRtg individual mejora ({bta("drtg")}; menos es mejor) y sus Win Shares por 40' suben ({bta("ws_per_40")}), porque ambas métricas reparten entre los cinco en pista el éxito del equipo. También sube su RAPM ({bta("rapm")}): una parte del contexto se filtra en el RAPM, cuya contracción ridge (Hoerl y Kennard, 1970) no separa por completo a un jugador de sus compañeros habituales. El nivel de los rivales tiene efectos más imprecisos ({claras_riv} métricas claras), con el signo esperado en el acierto (eFG% {btr("efg_pct")}) y el rebote defensivo ({btr("dreb_p100")}).</p>
<p><b>Uso.</b> El dataset normalizado incluye una versión «con compañeros de nivel medio» de las {claras} métricas con β claro, y el Atlas proyecta {len(CLAVE_CTX) or "las"} métricas clave de cualquier jugador al entorno de una plantilla concreta. En la escala transformada T de cada métrica:</p>
<div class="eq">x_destino = T⁻¹( T(x) + τ_pos · β · Δ ),    Δ = contexto de plantilla en el destino (sin él) − contexto en su equipo de origen</div>
<p>donde τ<sub>pos</sub> es la desviación típica de la capacidad real en la EuroLeague para su posición (algoritmo A) y β sólo se aplica si es claro. Así, un fichaje que llega a una plantilla mejor que la suya se proyecta con menos uso y más canastas asistidas, que es lo que cabe esperar de su nuevo papel.</p>
{fig("sensibilidad", "Sensibilidad β de cada métrica normalizada al nivel del entorno, con efecto fijo de jugador (± 2 errores típicos bootstrap). Puntos rellenos: nivel de los compañeros de plantilla (oscuros si |β| > 2 errores típicos); huecos: nivel de los rivales. En negrita, las métricas que entran en el vector de estilo.", "92%")}
<h3>6.2 Efectos entre compañeros (X → Y)</h3>
<p><b>Datos.</b> Para cada pareja de compañeros de un equipo y temporada, con Y en pista se compara a Y cuando X también está en pista y cuando no: su cuota de tiro (tiros de campo de Y / tiros del equipo), su eFG%, el porcentaje de sus canastas asistidas, el de sus tiros en el aro y sus puntos por 100 posesiones del equipo, con el número de tiros o de posesiones de cada situación para pesar el ruido (<code>bbmodel/interacciones.py</code>). Hay {mil(n_pares)} parejas dirigidas con 60 o más minutos juntos en la temporada regular de las {n_ligas_p} ligas y {n_temp_p} temporadas; {mil(n_reg)} tienen la probabilidad de estilo de los dos jugadores ({mil(IN.get("jugadores_con_estilo", 0))} jugadores-liga-temporada con estilo, salida de la VaDE) y entran en el modelo (<code>bbestilo/quimica.py</code>).</p>
<p><b>Modelo.</b> Cada efecto se regresa por mínimos cuadrados ponderados, con una pequeña penalización ridge, sobre el producto de las probabilidades de estilo de X y de Y, con el nivel de los dos como control y una interacción del nivel de X con el estilo de Y:</p>
<div class="eq">Δ_Y = p_Xᵀ · M · p_Y + β_X · (L_X − c) + β_Y · (L_Y − c) + (L_X − c) · (γ · p_Y),     c = nivel medio de la muestra ({n(IN.get("nivel_centro"), 2, True)})</div>
<p>La celda M<sub>st</sub> es el cambio medio de un jugador de estilo t al compartir pista con uno de estilo s, a igual nivel; β<sub>X</sub> mide cuánto cambia un jugador cuando su compañero es mejor. Los errores típicos salen de 60 réplicas bootstrap por equipos-temporada, porque las parejas de un mismo equipo no son independientes (Efron y Tibshirani, 1993).</p>
<p><b>El «efecto MVP».</b> Un compañero mejor cambia el juego de todos (Tabla {tn["mvp"]}): por cada unidad de nivel del compañero, Y lanza una parte menor de los tiros del equipo ({ef_("cuota_tiro")} puntos porcentuales) y anota menos por posesión ({ef_("pts100")} puntos por 100 posesiones), pero con mejor acierto (eFG% {ef_("efg")} puntos) y con más canastas asistidas ({ef_("pct_asistidas")} puntos): el compañero mejor concentra el tiro y le genera tiros mejores. Es el mismo patrón que la sensibilidad de la sección 6.1, medido ahora dentro de la temporada y no entre temporadas. {f"El efecto sobre la cuota de tiro es mayor cuando Y es de «{e(nombre(est_ids[g_min]))}»: su cuota baja otros {n(-gam[g_min], 2)} ± {n(gse[g_min], 2)} puntos por unidad de nivel del compañero." if gam[g_min] < 0 else ""}</p>
{tcap("mvp", "Efecto del nivel de los dos jugadores sobre cada efecto X → Y, por unidad de nivel (± error típico bootstrap). Nivel del compañero X = «efecto MVP»; nivel del propio Y = cómo cambia el efecto cuando el jugador que lo recibe es mejor. pp = puntos porcentuales.")}
{t_mvp}
<p><b>Por estilo.</b> La {fr("quimica")} muestra las matrices del eFG% y de la cuota de tiro. Las filas se leen como «qué hace un compañero de este estilo a los demás». Con un compañero de {sn(fc[0]["s"])} en pista, la cuota de tiro de los demás {baja_todos(fc[0])} ({rango(fc[0])} puntos), igual que con uno de {sn(fc[1]["s"])} ({rango(fc[1])}): son jugadores que se quedan los tiros. Los de {sn(fc[-1]["s"])} ({rango(fc[-1])}) y {sn(fc[-2]["s"])} ({rango(fc[-2])}) los dan; el mayor aumento es {celda("cuota_tiro", *ic_max)}. En el acierto, un compañero de {sn(fe[0]["s"])} baja el eFG% de {"todos los estilos" if fe[0]["claras"] == C.N_ESTILOS else f"{fe[0]['claras']} de los seis estilos"} ({rango(fe[0])} puntos), compatible con menos espacio en la pintura, mientras que {sn(fe[-1]["s"])} ({rango(fe[-1])}) y {sn(fe[-2]["s"])} ({rango(fe[-2])}) lo suben. En las canastas asistidas (no representadas), los compañeros de {sn(fa[-1]["s"])} ({rango(fa[-1])} puntos) y {sn(fa[-2]["s"])} ({rango(fa[-2])}) son los que más las aumentan, y los de {sn(fa[0]["s"])} ({rango(fa[0])}), los que más las reducen.</p>
{fig("quimica", "Química de estilos: cambio del eFG% (izquierda) y de la cuota de tiro (derecha) de un jugador Y (columnas) cuando comparte pista con un compañero X (filas), frente a cuando X no está, a igual nivel de los dos (puntos porcentuales). * = mayor que dos errores típicos (bootstrap por equipos-temporada); en gris, celdas no claras.")}
<h3>6.3 Sinergia de parejas</h3>
<p>La sinergia de una pareja es su net rating juntos menos lo que predice el RAPM de los diez jugadores en pista (contraído según la muestra), en puntos por 100 posesiones. Sobre {mil(SIN.get("n_parejas", 0))} parejas con 60 o más minutos juntos se regresa en la forma simétrica p<sub>A</sub>ᵀ S p<sub>B</sub>, con la suma de los niveles de los dos y su diferencia como controles ({fr("sinergia")}). A más nivel conjunto, más sinergia ({n(SIN.get("nivel_suma"), 2, True)} ± {n(SIN.get("nivel_suma_se"), 2)} por unidad de nivel); la diferencia de nivel entre los dos no importa ({n(SIN.get("diferencia_nivel"), 2, True)} ± {n(SIN.get("diferencia_nivel_se"), 2)}). A igual nivel, la mejor combinación es {par_txt(tri_o[0])}, seguida de {par_txt(tri_o[1])}; la peor, {par_txt(peor)}, y {sn(est_ids[peor[2]])} tiene sinergia negativa con {seis(neg_peor)} (clara, mayor que dos errores típicos, en {neg_peor_claras}). Dos jugadores que se fabrican sus propios tiros se estorban, mientras que el juego de pase y triple se refuerza a sí mismo y combina bien con la presión exterior.</p>
{fig("sinergia", "Sinergia de pareja frente al RAPM (puntos por 100 posesiones) según el estilo de los dos compañeros, a igual nivel; matriz simétrica (se muestra la mitad inferior) con el error típico bootstrap por equipos-temporada debajo de cada celda. * = mayor que dos errores típicos.", "74%")}
<h3>6.4 Limitaciones de estas capas</h3>
<ul>
<li>Son asociaciones, no efectos causales: el entrenador decide quién juega con quién y contra qué rivales, y las parejas que funcionan juegan más minutos juntas, lo que selecciona la muestra.</li>
<li>La comparación con y sin X en pista mezcla el cambio de compañeros y de rivales de cada situación; el modelo controla el nivel de X y de Y, no el del resto del quinteto.</li>
<li>El RAPM de una temporada es ruidoso y, por la contracción, arrastra parte del contexto (β = {bta("rapm")}); la sinergia frente al RAPM hereda ese sesgo.</li>
<li>El contexto se mide con un índice de nivel de caja; en la BBL 2020-23 no hay quintetos (sólo tiros y asistencias), en la LNB 2020-21 no hay jugada a jugada y la NBA y la G League 2026-27 aún no han empezado.</li>
<li>Las celdas de estilos que rara vez coinciden en una plantilla tienen más error (por ejemplo, {par_txt(peor)}).</li>
</ul>

<h2>7. Herramientas de decisión: el Atlas de Estilos</h2>
<p>El modelo se usa a través del Atlas de Estilos, una página interactiva que ejecuta la red en el navegador con los pesos exportados. Tiene cinco pestañas: <b>Comparar clubes</b> (mapa 3D con filtros de temporada, liga, estilo, nivel y capas, y comparación de hasta cuatro equipos o ligas por perfil, reparto entre estilos y distancias); <b>Simular fichajes</b> (club destino, bajas y uno o varios fichajes con sus minutos; estilo antes y después, encaje de cada fichaje, minutos por estilo y dispersión de la plantilla, y escenarios guardados); <b>Buscar parecidos</b> (clubes que juegan como el de referencia y jugadores parecidos o que encajan con su estilo, que se pueden llevar al simulador); <b>Ligas y estilos</b>; y <b>Hallazgos y modelo</b>. Los datos exportados incluyen también la sensibilidad al contexto (sección 6.1), para proyectar las métricas de un fichaje al entorno del destino, y las matrices de química (secciones 6.2 y 6.3).</p>
<p><b>Ejemplo.</b> La Tabla {tn["ejemplo"]} y la {fr("simulacion")} muestran el escenario de ejemplo del Atlas: {e(EJ["club"])} (EuroLeague {EJ["temporada"]}) incorpora a los dos jugadores de esa temporada (fuera de la NBA) cuyo perfil más se parece al estilo del club y pierde al jugador de la plantilla con más minutos. Con ese escenario el club {"cambia de «" + e(nombre(est.iloc[a0["e"]]["estilo"])) + "» a «" + e(nombre(est.iloc[a1["e"]]["estilo"])) + "»" if cambia else "mantiene su estilo, «" + e(nombre(est.iloc[a0["e"]]["estilo"])) + "»"}: la neurona de su estilo actual pasa de {n(a0["p"][a0["e"]])} a {n(a1["p"][a0["e"]])}, el club se desplaza {n(EJ["desplazamiento"])} en el mapa (percentil {n(EJ["pct_desplazamiento"], 0)} de las distancias entre clubes) y su nivel pasa de {n(a0["nivel"], 2, True)} a {n(a1["nivel"], 2, True)}.</p>
{tcap("ejemplo", "Escenario de ejemplo. Distancia = jugador → club en el mapa (percentil frente a lo lejos que está cada jugador de su propio club); afinidad = salida del jugador en la neurona del estilo del club.")}
{t_ej}
{fig("simulacion", "Escenario de ejemplo. Izquierda: plantilla que sigue (círculos, tamaño = minutos, color = estilo del jugador), baja (✕), fichajes (rombos) y el club hoy (cuadrado) y con el escenario (rombo naranja). Derecha: salida de las seis neuronas del club hoy y con el escenario.")}

<h2>8. Discusión</h2>
<p><b>Lo esperado y lo obtenido.</b> Se esperaba que neutralizar el nivel deshiciera los estilos «de liga» de la v1 sin destruir la estructura del estilo, y así ha sido: la asociación estilo-nivel cae de un η² de {pc(V1.get("eta2_nivel"), 0)} a {pc(V["eta2_nivel"], 1)}, la información compartida con la liga baja de {n(V1.get("nmi_estilo_liga"), 2)} a {n(V["nmi_estilo_liga"], 2)}, y los perfiles siguen siendo diferenciables y replicables. Se esperaba que menos estilos dieran asignaciones más seguras y estables: la seguridad media del VaDE pasa de {n(V1.get("salida_max_media"), 2)} (12 estilos) a {n(V["salida_max_media"], 2)} (6), y el acuerdo entre semillas de {n(V1.get("ari_semillas_medio"), 2)} a {n(V["ari_semillas_medio"], 2)}. No se esperaba encontrar grupos nítidos, y no los hay: el estilo de juego de los clubes, medido con estos {NR} rasgos, es un continuo con una resolución estable de hasta seis estilos. La recomendación práctica es leer la etiqueta junto con la probabilidad de la neurona ganadora y, sobre todo, la distancia en el mapa, que es la medida más estable.</p>
<p><b>Lo que añade el jugada a jugada.</b> Los {n_pbp} rasgos de tiro y creación hacen el modelo más estable (ARI entre semillas {n(V4.get("ari_semillas_medio"), 2)} → {n(V["ari_semillas_medio"], 2)}; reproducibilidad temporal {n(V4.get("ari_temporal_reserva"), 2)} → {n(V["ari_temporal_reserva"], 2)}; replicabilidad {n(g(V4, "replicabilidad.correlacion_media") if V4 else None, 2)} → {n(V["replicabilidad"]["correlacion_media"], 2)}) y cambian lo que distingue a los estilos: la oposición principal pasa a ser la de los equipos que se fabrican sus tiros (media distancia, canastas sin asistencia) frente a los que circulan el balón hacia el triple de esquina, una dimensión que la estadística de caja apenas veía. El precio es una partición distinta de la v4 (ARI {n(ac_v4.get("ari"), 2)}) y una asociación algo mayor con la liga, que es real: la NBA y la LNB concentran «{e(nombre("E01"))}» ({pc(lg["liga_x_estilo"]["nba"].get("E01"))} y {pc(lg["liga_x_estilo"]["lnb"].get("E01"))} de sus clubes).</p>
<p><b>Lo inesperado.</b> Varios resultados contradicen intuiciones habituales. Primero, a igual nivel individual el estilo {"sí se asocia" if sig_ex else "no se asocia"} con el net rating del equipo, con estilos que ganan sistemáticamente más («{e(nombre(mejor_ex["estilo"]))}») y otros que ganan menos («{e(nombre(peor_ex["estilo"]))}»). Segundo, parecerse al estilo del nuevo club no se traduce en mejor rendimiento del jugador; {"si acaso, los jugadores que llegan a clubes de estilo distinto mejoran ligeramente más, lo que es compatible con fichajes de complementariedad" if ed["coef"] > 0 else "la relación es débil"}. Tercero, el RAPM, que se suele tomar como una medida del jugador aislada de su entorno, sube con el nivel de los compañeros ({bta("rapm")}), y un compañero de {sn(fe[0]["s"])} baja el acierto de {"todos los demás" if fe[0]["claras"] == C.N_ESTILOS else "casi todos los demás"}.</p>
<p><b>Para la dirección deportiva.</b> Neutralizar el nivel separa la pregunta «¿encaja este jugador?» de «¿es bueno este jugador?», que la capa de nivel responde aparte. Los resultados sugieren usar el modelo para cuatro decisiones: (i) definir y mantener una identidad de juego, ya que la continuidad de la plantilla es el principal predictor de conservar el estilo y Baskonia cambia de estilo más que la mayoría de los clubes; (ii) orientar la plantilla hacia estilos que, a igual nivel, se asocian con más net rating; (iii) usar la distancia del jugador al club y la simulación de escenarios para decidir si se busca similitud (reforzar la identidad) o complementariedad (cubrir un rasgo que falta), no como predictor del rendimiento individual; y (iv) pensar en parejas: con el equipo de EuroLeague en «{e(nombre(ultimo["euroleague"]["estilo"]))}» y el de Liga Endesa en «{e(nombre(ultimo["acb"]["estilo"]))}», la matriz de sinergia sugiere priorizar jugadores de juego de pase y triple o de presión exterior y evitar acumular creadores individuales, siempre leyendo los números de cada candidato proyectados al contexto de la plantilla.</p>

<h2>9. Conclusiones</h2>
<ol>
<li>Con los datos normalizados a la vara EuroLeague, el estilo de juego sólo es comparable entre ligas si se neutraliza antes el nivel: sin hacerlo, la red aprende ligas y calidad ({pc(V1.get("eta2_nivel"), 0)} del nivel explicado en la v1); tras hacerlo, {pc(V["eta2_nivel"], 1)}.</li>
<li>Seis estilos es la resolución que respaldan los datos (mínimo del ICL y BIC casi plano entre seis y once) y la que da asignaciones más seguras y más estables entre redes y temporadas que ocho y doce, que añaden fronteras poco reproducibles.</li>
<li>Los rasgos de jugada a jugada (zonas de tiro con coordenadas calibradas en las ocho fuentes y canastas asistidas) hacen el modelo más estable y replicable, y redefinen los estilos en torno a cómo se fabrica el tiro.</li>
<li>El VaDE con covarianzas completas, consenso de {n_sem} semillas y ajuste fino da asignaciones seguras ({n(V["salida_max_media"], 2)}) y un mapa muy estable (r = {n(V["estabilidad_mapa"], 2)}); la distancia en el mapa es más fiable que la etiqueta.</li>
<li>A igual nivel, {"el estilo se asocia con ganar" if sig_ex else "el estilo no se asocia con ganar"}; parecerse al estilo del destino no mejora el rendimiento de un fichaje; y la continuidad de la plantilla sostiene la identidad.</li>
<li>Los números de un jugador dependen del nivel de sus compañeros (menos uso y más canastas asistidas con compañeros mejores), y la química entre estilos es medible: el juego de pase y triple se potencia en pareja y la creación individual, no.</li>
<li>Baskonia cambia de estilo más que la mayoría de los clubes; mantener una identidad requiere más continuidad o fichajes elegidos para el estilo buscado, que el simulador permite evaluar antes de decidir.</li>
<li>El modelo es una herramienta descriptiva y de escenarios, no un predictor de rendimiento: se complementa con la capa de nivel y con el criterio del cuerpo técnico.</li>
</ol>

<h2>10. Dificultades encontradas</h2>
<ul>
<li><b>Sesgo de nivel.</b> El más importante: la vara común trasladaba el nivel al estilo (NMI estilo-liga {n(V1.get("nmi_estilo_liga"), 2)} en la v1), motivo de la v2.</li>
<li><b>Mapa degenerado y colapso.</b> Sin el término de estrés, la IDEC dejaba el mapa casi en dos dimensiones y el VaDE colapsaba en dos componentes. El estrés de escala fija y el paso M con π uniforme y resiembra lo resolvieron; con estrés normalizado (invariante a la escala), la IDEC colapsó en un solo estilo porque su núcleo depende de la escala absoluta.</li>
<li><b>Rasgos tratados como ruido.</b> Con una varianza de reconstrucción por rasgo, el VaDE representaba mal el ritmo y la concentración del uso (R² 0,08 y 0,15); se pasó a una varianza común.</li>
<li><b>Potencia de las pruebas.</b> Con 999 permutaciones, la corrección de Holm sobre 66 parejas no podía declarar ninguna significativa (p mínimo 0,001 × 66); se pasó a 9.999.</li>
<li><b>Consenso dependiente de las semillas.</b> El consenso de cinco redes de la v3 no se sostenía frente a cinco redes nuevas (ARI {n(c3["nuevas"], 2)}); se amplió a {len(sem4)}.</li>
<li><b>Consenso degenerado.</b> En la v2, la partición de consenso por enlace medio produjo un grupo muy pequeño y, con paso M durante el ajuste fino, la red se alejaba del consenso (ARI 0,57). Fijar la mezcla del consenso y entrenar sólo codificador y decodificador lo resolvió.</li>
<li><b>Número de estilos.</b> El encargo inicial (12 neuronas) y la segunda versión (8) iban por encima de lo que respaldan los datos; hicieron falta dos iteraciones para llegar a 6. Con {NR} rasgos, el BIC y el ICL con covarianza completa prefieren tres estilos por el peso de su penalización ({par_full} parámetros por componente), por lo que la decisión se apoyó en la versión diagonal y en la estabilidad.</li>
<li><b>Coordenadas de ocho fuentes.</b> Cada liga usa un sistema distinto (centímetros, décimas de pie, milímetros con los ejes cambiados, porcentaje de la pista completa o unidades propias de media pista); calibrarlas a mano no era viable por liga y temporada, y se resolvió ajustando aro y escala contra la línea de triple oficial con la propia anotación de 2 y 3 de la fuente.</li>
<li><b>Rol frente a contexto.</b> El contexto en pista mezcla el rol del jugador con su entorno (quien mejora juega con los titulares); la sensibilidad se estimó con el contexto de plantilla y efectos fijos de persona. Aun así, el RAPM arrastra parte del contexto.</li>
<li><b>Etiquetas que cambian con los rasgos.</b> Añadir el jugada a jugada cambió buena parte de la partición (ARI {n(ac_v4.get("ari"), 2)} con la v4), lo que obligó a renombrar los estilos y a archivar la v4 completa para poder comparar.</li>
<li><b>Datos.</b> La posición se estima en EuroLeague, EuroCup, LBA y parte de la G League (≈77 % de acierto); los traspasos en EuroLeague y EuroCup vienen en una fila (se asignan al último equipo); LBA y LNB cambian el identificador de equipo cada temporada (se enlazan por nombre y continuidad de plantilla); la LNB no publica totales de rivales ni tiene jugada a jugada en 2020-21; la BBL no tiene quintetos en 2020-23; 2026-27 sólo tiene unas jornadas y el algoritmo A.</li>
</ul>

<h2>11. Riesgos asociados</h2>
<p>La Tabla {tn["riesgos"]} recoge los riesgos de usar el modelo en decisiones deportivas, con una valoración cualitativa de su probabilidad e impacto y la mitigación prevista.</p>
{tcap("riesgos", "Riesgos del modelo y de su uso.")}
{t_riesgos}
<h3>Limitaciones</h3>
<ul>
<li>Los rasgos describen al jugador en pista y, desde el modelo final, dónde tira y cómo llega a la canasta, pero no el sistema del entrenador: no hay tipos de jugada (pick and roll, aislamiento, transición), defensas zonales ni datos de seguimiento (distancia del defensor, velocidad).</li>
<li>Las zonas se miden por la distancia al aro con coordenadas de calidad variable entre fuentes; la calibración garantiza la línea de triple, no la precisión de cada tiro cerca del aro.</li>
<li>Las traducciones A+B reducen el ruido y parte del contexto de equipo; el estilo medido es el de los jugadores que el club pone en pista, y su contexto de nivel no se descuenta antes de situarlos en el mapa.</li>
<li>La neutralización es lineal-cuadrática en un índice de nivel; un nivel multidimensional podría dejar restos de asociación con aspectos concretos de la calidad.</li>
<li>El análisis del efecto del encaje y la química son observacionales: los clubes eligen a quién fichan y los entrenadores con quién juega cada uno, lo que puede sesgar las estimaciones en cualquier dirección.</li>
<li>La simulación supone que el jugador lleva su perfil al nuevo club, con el ritmo del destino; la proyección de contexto corrige su nivel de entorno, pero no modela cambios de rol decididos por el entrenador.</li>
</ul>

<h2>12. Mejoras propuestas</h2>
<h3>12.1 Del modelo</h3>
<ol>
<li><b>Datos de juego más finos:</b> tipos de jugada (pick and roll, aislamiento, transición), defensa por posesión y datos de seguimiento, cuando estén disponibles para las ocho ligas; las zonas de tiro y las canastas asistidas ya están incorporadas.</li>
<li><b>Contexto dentro del estilo:</b> situar a los jugadores con sus métricas «con compañeros de nivel medio» (sección 6.1), para que el perfil de un jugador no dependa de la plantilla en la que jugó.</li>
<li><b>Química en el simulador:</b> usar los efectos X → Y y la sinergia de parejas para estimar cómo cambia el juego del resto de la plantilla con un fichaje, no sólo su vector medio.</li>
<li><b>Neutralización dentro de la red:</b> un VaDE condicional (decodificador condicionado al nivel) o con penalización de independencia (HSIC) entre el mapa y el nivel, en lugar de residualizar antes.</li>
<li><b>Estructura temporal y de club:</b> efectos aleatorios de club y dinámica entre temporadas (un VaDE secuencial) para separar identidad estable y cambio.</li>
<li><b>Número de estilos con incertidumbre:</b> mezclas de proceso de Dirichlet que estimen K y su incertidumbre, y probabilidades de salida calibradas.</li>
<li><b>Arquetipos de jugador:</b> una segunda red para los roles individuales y una matriz de compatibilidad rol × estilo, para que la simulación pueda cambiar el rol del fichaje.</li>
<li><b>Evaluación causal del encaje y de la química:</b> emparejamiento, variables instrumentales o cambios de plantilla a mitad de temporada para aislar el efecto del encaje y de cada pareja sobre el rendimiento y los minutos.</li>
</ol>
<h3>12.2 Del proyecto</h3>
<ol>
<li><b>Actualización automática:</b> reentrenar y reexportar el Atlas con cada carga de datos (la rutina de actualización del proyecto ya descarga las ligas), con un informe de cambios de estilo de los clubes seguidos.</li>
<li><b>Seguimiento del modelo:</b> registrar en cada reentrenamiento la reproducibilidad temporal, la replicabilidad, la neutralidad y la calidad de la calibración de coordenadas, y avisar si empeoran.</li>
<li><b>Validación con el cuerpo técnico:</b> contrastar los nombres de los estilos, la posición de una muestra de clubes y las parejas de la matriz de química con la opinión de entrenadores y analistas, y ajustar los nombres.</li>
<li><b>Entrenador como covariable:</b> enlazar cada club-temporada con su entrenador para medir cuánto estilo viaja con él, útil para la elección de entrenador.</li>
<li><b>Integración con el scouting:</b> llevar el encaje, la proyección de contexto y la simulación a las fichas de jugadores seguidos y guardar los escenarios evaluados en un registro compartido.</li>
</ol>

<h2>13. Reproducibilidad</h2>
<p>Todo el proceso es reproducible desde el repositorio, en este orden: <code>python -m bbmodel pista</code> (zonas de tiro, canastas asistidas y RAPM por jugador-equipo, con la calibración de coordenadas en <code>data/modelos/pista/calibracion.json</code>); <code>python -m bbmodel ajustar</code>, <code>python -m bbmodel ajustar-b</code> y <code>python -m bbmodel dataset-normalizado</code> (algoritmos A y B con las métricas de pista; validación fuera de muestra con <code>python -m bbmodel mesa-normalizacion</code>); <code>python -m bbmodel contexto</code> (contexto de nivel y sensibilidad, <code>data/modelos/contexto/</code>); <code>python -m bbmodel interacciones</code> (efectos X → Y entre compañeros, <code>data/modelos/interacciones/</code>); <code>python -m bbestilo barrido</code> (número de estilos, <code>barrido_k.json</code>); <code>python -m bbestilo entrenar</code> (VaDE, {n_sem} semillas, consenso y ajuste fino); <code>python -m bbestilo analisis</code>; <code>python -m bbestilo quimica</code> (matrices de química, <code>interacciones.json</code>); <code>python -m bbestilo exportar</code> (datos del Atlas de Estilos); <code>python -m bbestilo encaje --jugador "A" "B" --baja "C"</code> (simulación de varios fichajes); <code>python -m bbestilo parecidos</code>; y <code>python -m bbestilo articulo</code> (este documento). El modelo final, sus semillas, la red de reserva, las tablas de clubes, jugadores y estilos y todas las métricas están en <code>data/modelos/estilos/</code>; las iteraciones anteriores, en <code>data/modelos/estilos/historial/</code> (la v4 completa, con modelos y nombres; las anteriores se reproducen con <code>--estilos 12 --sin-neutralizar</code> y <code>--estilos 8</code> sobre el código de su commit).</p>

<h2>Referencias</h2>
<ol class="refs">
<li>Biernacki, C., Celeux, G. y Govaert, G. (2000). Assessing a mixture model for clustering with the integrated completed likelihood. <i>IEEE Transactions on Pattern Analysis and Machine Intelligence</i>, 22(7), 719-725.</li>
<li>Efron, B. y Tibshirani, R. J. (1993). <i>An Introduction to the Bootstrap</i>. Chapman &amp; Hall.</li>
<li>Fred, A. L. N. y Jain, A. K. (2005). Combining multiple clusterings using evidence accumulation. <i>IEEE Transactions on Pattern Analysis and Machine Intelligence</i>, 27(6), 835-850.</li>
<li>Frisch, R. y Waugh, F. V. (1933). Partial time regressions as compared with individual trends. <i>Econometrica</i>, 1(4), 387-401.</li>
<li>Guo, X., Gao, L., Liu, X. y Yin, J. (2017). Improved deep embedded clustering with local structure preservation. <i>IJCAI</i>, 1753-1759.</li>
<li>Hendrycks, D. y Gimpel, K. (2016). Gaussian Error Linear Units (GELUs). arXiv:1606.08415.</li>
<li>Hoerl, A. E. y Kennard, R. W. (1970). Ridge regression: biased estimation for nonorthogonal problems. <i>Technometrics</i>, 12(1), 55-67.</li>
<li>Holm, S. (1979). A simple sequentially rejective multiple test procedure. <i>Scandinavian Journal of Statistics</i>, 6(2), 65-70.</li>
<li>Hubert, L. y Arabie, P. (1985). Comparing partitions. <i>Journal of Classification</i>, 2, 193-218.</li>
<li>Jiang, Z., Zheng, Y., Tan, H., Tang, B. y Zhou, H. (2017). Variational Deep Embedding: an unsupervised and generative approach to clustering. <i>IJCAI</i>, 1965-1972.</li>
<li>Kingma, D. P. y Ba, J. (2015). Adam: a method for stochastic optimization. <i>ICLR</i>.</li>
<li>Kingma, D. P. y Welling, M. (2014). Auto-encoding variational Bayes. <i>ICLR</i>.</li>
<li>Kruskal, J. B. (1964). Multidimensional scaling by optimizing goodness of fit to a nonmetric hypothesis. <i>Psychometrika</i>, 29, 1-27.</li>
<li>MacKinnon, J. G. y White, H. (1985). Some heteroskedasticity-consistent covariance matrix estimators with improved finite sample properties. <i>Journal of Econometrics</i>, 29(3), 305-325.</li>
<li>Oliver, D. (2004). <i>Basketball on Paper: Rules and Tools for Performance Analysis</i>. Potomac Books.</li>
<li>Rousseeuw, P. J. (1987). Silhouettes: a graphical aid to the interpretation and validation of cluster analysis. <i>Journal of Computational and Applied Mathematics</i>, 20, 53-65.</li>
<li>Schwarz, G. (1978). Estimating the dimension of a model. <i>The Annals of Statistics</i>, 6(2), 461-464.</li>
<li>Sill, J. (2010). Improved NBA adjusted +/- using regularization and out-of-sample testing. <i>MIT Sloan Sports Analytics Conference</i>.</li>
<li>Venna, J. y Kaski, S. (2001). Neighborhood preservation in nonlinear projection methods: an experimental study. <i>ICANN</i>, 485-491.</li>
<li>Xie, J., Girshick, R. y Farhadi, A. (2016). Unsupervised deep embedding for clustering analysis. <i>ICML</i>, 478-487.</li>
<li>Saski Baskonia, Dirección Deportiva (2026). Normalización de ligas hacia la EuroLeague: algoritmos A y B; Jugada a jugada en los modelos: zonas de tiro, contexto de nivel y química de estilos. Documentación interna (<code>docs/algoritmo_A.md</code>, <code>docs/algoritmo_B.md</code>, <code>docs/contexto_y_quimica.md</code>).</li>
</ol>
"""
    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Estilos de juego · Saski Baskonia</title>
<style>{_fuentes_css(fuentes, trabajo)}{CSS}</style></head><body>{cuerpo}</body></html>"""
    (trabajo / "articulo.html").write_text(doc, encoding="utf-8")
    pdf = d / NOMBRE_PDF
    chrome = chrome or _chrome()
    subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf}", "--virtual-time-budget=10000", (trabajo / "articulo.html").as_uri()],
                   check=True, capture_output=True, timeout=180)
    destino = C.RAIZ / "artifact" / "articulo"
    destino.mkdir(parents=True, exist_ok=True)
    shutil.copy(pdf, destino / NOMBRE_PDF)
    return pdf


def _chrome() -> str:
    import glob
    for c in sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")) + [shutil.which("chromium") or "",
                                                                                      shutil.which("google-chrome") or ""]:
        if c and Path(c).exists():
            return c
    raise RuntimeError("No encuentro Chromium para imprimir el PDF")
