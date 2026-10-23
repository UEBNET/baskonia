"""Encaje de un jugador en un club: ¿encaja en su estilo o es «una oveja de cada madre»?

Para un club de destino (p. ej. Baskonia EuroLeague 2025-26) y un jugador (con su perfil normalizado
de su liga y temporada), y para cada red:

  1. Situación en el mapa: punto del club destino, del jugador y del club actual del jugador, y sus
     estilos (neurona ganadora de la capa de salida).
  2. Distancias en el mapa (unidades = desviaciones típicas del perfil de estilo) con su percentil de
     referencia: jugador-club frente a lo lejos que está cada jugador de su propio club; club-club
     frente a todas las parejas de clubes.
  3. Afinidad: salida del jugador en la neurona del estilo del club y similitud entre las dos salidas
     de la capa de estilos (1 − divergencia de Jensen-Shannon, en base 2).
  4. Plantilla: reparto de minutos por estilo, dispersión de la plantilla en el mapa (media ponderada
     de la distancia a su centro) y su percentil entre todos los clubes, y los compañeros más parecidos.
  5. Simulación: el club se recalcula con el fichaje (agregación exacta por minutos). El jugador toma
     el ritmo de su nuevo equipo; sus minutos salen de todos a prorrata o del jugador al que sustituye.
     `simular_plantilla` hace lo mismo con varios fichajes y bajas a la vez (informe_plantilla).
"""
from __future__ import annotations

import unicodedata
from pathlib import Path
from functools import lru_cache

import numpy as np
import pandas as pd
import torch

from . import config as C
from .datos import Conjunto, _I, _media_w, agregar, club_alias, construir
from .entrenar import cargar
from .resultados import nombre_estilo


@lru_cache(maxsize=1)
def conjunto(ligas: list[str] | None = None) -> Conjunto:
    return construir(ligas=ligas)


def red_guardada(tipo: str, carpeta=None):
    """Red guardada en <carpeta>/<tipo>/modelo.pt (por defecto, la carpeta de resultados activa)."""
    return _red_guardada(tipo, str(carpeta or C.DIR_SALIDA))


@lru_cache(maxsize=8)
def _red_guardada(tipo: str, carpeta: str):
    return cargar(Path(carpeta) / tipo / "modelo.pt")[0]


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()


def resolver_club(cj: Conjunto, club: str, competicion: str, temporada: str) -> str:
    """Clave club-competición-temporada a partir de un alias de config/clubes.json, una clave
    «liga:club_id» o parte del nombre."""
    alias = club_alias()
    claves = []
    if club.lower() in alias:
        claves = [c for c in alias[club.lower()]["claves"] if c.startswith(competicion + ":")]
    elif ":" in club:
        claves = [club]
    else:
        c = cj.clubes[(cj.clubes["liga"] == competicion) & cj.clubes["nombre_club"].map(_norm).str.contains(_norm(club))]
        claves = sorted(c["clave_club"].unique())
    if not claves:
        raise ValueError(f"No encuentro el club «{club}» en {competicion}")
    clave = f"{claves[0]}:{temporada}"
    if clave not in set(cj.clubes["clave"]):
        raise ValueError(f"{claves[0]} no tiene datos en {temporada}")
    return clave


def resolver_jugador(cj: Conjunto, nombre: str, temporada: str | None = None) -> int:
    """Índice (en cj.jugadores) de la fila jugador-equipo con más minutos de su temporada más reciente."""
    J = cj.jugadores
    partes = _norm(nombre).split()
    m = J["nombre"].map(_norm).map(lambda n: all(p in n for p in partes)) & (J["min"] >= C.MIN_JUGADOR)
    if temporada:
        m &= J["temporada"] == temporada
    if not m.any():
        raise ValueError(f"No encuentro a «{nombre}» con {C.MIN_JUGADOR}+ minutos")
    c = J[m]
    c = c[c["temporada"] == c["temporada"].max()]
    return int(c["min"].idxmax())


def _js(p: np.ndarray, q: np.ndarray) -> float:
    m = 0.5 * (p + q)
    kl = lambda a, b: float(np.sum(a * (np.log2(a + 1e-12) - np.log2(b + 1e-12))))
    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


@torch.no_grad()
def _pred(red, X):
    x = torch.tensor(np.atleast_2d(X), dtype=torch.float32)
    return red.salida(x).numpy(), red.mapa(x).numpy()


def simular_plantilla(cj: Conjunto, clave_destino: str, fichajes: list[tuple[int, float | None]],
                      bajas: list[int] = ()) -> tuple[np.ndarray, np.ndarray, list[float]]:
    """Vector de estilo (sin transformar) y medias de calidad del club destino con VARIOS fichajes y bajas.

    fichajes = [(índice en cj.jugadores, minutos | None)]; None = su cuota de minutos actual en su equipo
    aplicada a los minutos totales del destino. bajas = índices de jugadores de la plantilla que salen.
    Los minutos totales del club no cambian: los que siguen se reescalan a prorrata para dejar sitio a
    los fichajes (si las bajas liberan más minutos de los que ocupan los fichajes, los que siguen ganan
    minutos). Cada fichaje toma el ritmo del club destino. Devuelve (vector, medias de calidad, minutos)."""
    R, w, idx, Q = cj.plantillas[clave_destino]
    pos = {int(i): k for k, i in enumerate(idx)}
    T = w.sum()
    ritmo_club = agregar(R, w[None])[0][C.COLS.index("ritmo_rel")]
    w = w.copy()
    for b in bajas:
        if int(b) not in pos:
            raise ValueError(f"{cj.jugadores.at[b, 'nombre']} no está en la plantilla de {clave_destino}")
        w[pos[int(b)]] = 0.0
    filas, qs, mins = [], [], []
    for jx, m in fichajes:
        Rj, wj, idxj, Qj = cj.plantillas[cj.jugadores.at[jx, "clave"]]
        k = list(idxj).index(jx)
        fila = Rj[k].copy()
        fila[_I["ritmo_rel"]] = ritmo_club
        filas.append(fila)
        qs.append(Qj[k])
        mins.append(float(wj[k] / wj.sum() * T) if m is None else float(m))
    F = sum(mins)
    if F >= T or w.sum() <= 0:
        raise ValueError("Los fichajes no pueden ocupar todos los minutos del club")
    W = np.concatenate([w * (T - F) / w.sum(), mins])[None]
    return agregar(np.vstack([R, *filas]), W)[0], _media_w(np.vstack([Q, *qs]), W)[0], mins


def simular(cj: Conjunto, clave_destino: str, idx_jugador: int, minutos: float | None = None,
            sustituye: int | None = None) -> tuple[np.ndarray, np.ndarray, float]:
    """Un solo fichaje. `sustituye` es el índice en cj.jugadores del jugador cuyos minutos hereda (sale de
    la plantilla y, si no se dan minutos, el fichaje juega los suyos)."""
    if minutos is None and sustituye is not None:
        R, w, idx, Q = cj.plantillas[clave_destino]
        minutos = float(w[list(idx).index(sustituye)])
    V, Qm, mins = simular_plantilla(cj, clave_destino, [(idx_jugador, minutos)],
                                    [sustituye] if sustituye is not None else [])
    return V, Qm, mins[0]


def encaje(red, cj: Conjunto, clave_destino: str, idx_jugador: int, minutos: float | None = None,
           sustituye: int | None = None, referencias: dict | None = None) -> dict:
    C_ = cj.clubes.set_index("clave")
    J = cj.jugadores
    i_dest = list(C_.index).index(clave_destino)
    clave_j = J.at[idx_jugador, "clave"]
    i_orig = list(C_.index).index(clave_j)
    j_pos = idx_jugador
    Pc, Zc = _pred(red, cj.Xc[[i_dest, i_orig]])
    Pj, Zj = _pred(red, cj.Xj[[j_pos]])
    e_dest, e_orig, e_jug = (int(Pc[0].argmax()), int(Pc[1].argmax()), int(Pj[0].argmax()))
    ref = referencias or referencias_distancia(red, cj)
    d_jc = float(np.linalg.norm(Zj[0] - Zc[0]))
    d_cc = float(np.linalg.norm(Zc[1] - Zc[0]))
    # plantilla del destino
    pl = J[(J["clave"] == clave_destino) & (J["min"] >= C.MIN_JUGADOR)]
    Pp, Zp = _pred(red, cj.Xj[pl.index.to_numpy()])
    wp = pl["min"].to_numpy(float)
    centro = np.average(Zp, axis=0, weights=wp)
    disp = float(np.average(np.linalg.norm(Zp - centro, axis=1), weights=wp))
    reparto = np.bincount(Pp.argmax(1), weights=wp, minlength=C.N_ESTILOS) / wp.sum()
    dist_comp = np.linalg.norm(Zp - Zj[0], axis=1)
    cerca = pl.assign(d=dist_comp, estilo=[nombre_estilo(k) for k in Pp.argmax(1)]).sort_values("d").head(3)
    # simulación
    V, Qm, mins = simular(cj, clave_destino, idx_jugador, minutos, sustituye)
    Ps, Zs = _pred(red, cj.x_club(V[None], Qm[None]))
    return {
        "red": red.nombre,
        "club": {"clave": clave_destino, "nombre": C_.at[clave_destino, "nombre_club"], "estilo": nombre_estilo(e_dest),
                 "p": float(Pc[0, e_dest]), "mapa": [round(float(v), 3) for v in Zc[0]], "nivel": float(C_.at[clave_destino, "nivel"])},
        "jugador": {"nombre": J.at[idx_jugador, "nombre"], "equipo": J.at[idx_jugador, "equipo"],
                    "liga": J.at[idx_jugador, "liga"], "temporada": J.at[idx_jugador, "temporada"],
                    "min": float(J.at[idx_jugador, "min"]), "estilo": nombre_estilo(e_jug), "p": float(Pj[0, e_jug]),
                    "mapa": [round(float(v), 3) for v in Zj[0]], "nivel": float(J.at[idx_jugador, "nivel"]),
                    "fuente_norm": J.at[idx_jugador, "fuente_norm"]},
        "club_jugador": {"clave": clave_j, "nombre": C_.at[clave_j, "nombre_club"], "estilo": nombre_estilo(e_orig),
                         "mapa": [round(float(v), 3) for v in Zc[1]]},
        "distancias": {"jugador_club": d_jc, "pct_jugador_club": float((ref["jugador_su_club"] <= d_jc).mean() * 100),
                       "club_club": d_cc, "pct_club_club": float((ref["club_club"] <= d_cc).mean() * 100)},
        "afinidad": {"p_estilo_club": float(Pj[0, e_dest]), "similitud_salidas": 1 - _js(Pj[0], Pc[0])},
        "plantilla": {"jugadores": int(len(pl)), "dispersion": disp,
                      "pct_dispersion": float((ref["dispersion"] <= disp).mean() * 100),
                      "cuota_estilo_club": float(reparto[e_dest]), "cuota_estilo_jugador": float(reparto[e_jug]),
                      "reparto": {nombre_estilo(k): float(v) for k, v in enumerate(reparto) if v > 0},
                      "nivel_medio": float(np.average(pl["nivel"].fillna(0), weights=wp)),
                      "mas_parecidos": [(r.nombre, r.estilo, float(r.d)) for r in cerca.itertuples()]},
        "simulacion": {"minutos": mins, "sustituye": None if sustituye is None else J.at[sustituye, "nombre"],
                       "mapa": [round(float(v), 3) for v in Zs[0]], "estilo": nombre_estilo(int(Ps[0].argmax())),
                       "p": float(Ps[0].max()), "desplazamiento": float(np.linalg.norm(Zs[0] - Zc[0])),
                       "p_estilo_actual": float(Ps[0, e_dest])},
    }


@torch.no_grad()
def referencias_distancia(red, cj: Conjunto) -> dict:
    """Distribuciones de referencia (temporadas de entrenamiento) para leer las distancias."""
    sel = ~cj.clubes["provisional"].to_numpy()
    _, Zc = _pred(red, cj.Xc)
    pos = dict(zip(cj.clubes["clave"], range(len(cj.clubes))))
    J = cj.jugadores
    m = ((J["min"] >= C.MIN_JUGADOR) & ~J["provisional"]).to_numpy()
    _, Zj = _pred(red, cj.Xj[m])
    cj_idx = J.loc[m, "clave"].map(pos).to_numpy()
    d_j = np.linalg.norm(Zj - Zc[cj_idx], axis=1)
    Zt = Zc[sel]
    iu = np.triu_indices(len(Zt), 1)
    d_cc = np.sqrt(((Zt[:, None] - Zt[None]) ** 2).sum(-1))[iu]
    df = pd.DataFrame({"c": cj_idx, "w": J.loc[m, "min"].to_numpy(float), "x": Zj[:, 0], "y": Zj[:, 1], "z": Zj[:, 2]})
    disp = []
    for _, g in df.groupby("c"):
        Z = g[["x", "y", "z"]].to_numpy()
        c = np.average(Z, axis=0, weights=g["w"])
        disp.append(np.average(np.linalg.norm(Z - c, axis=1), weights=g["w"]))
    return {"jugador_su_club": d_j, "club_club": d_cc, "dispersion": np.array(disp)}


def informe_plantilla(jugadores: list[str], club: str = "baskonia", competicion: str = "euroleague",
                      temporada: str = "2025-26", minutos: list[float] | None = None, bajas: list[str] = ()) -> str:
    """Simulación de varios fichajes (y bajas) a la vez sobre el club destino."""
    cj = conjunto()
    red = red_guardada("vade")
    destino = resolver_club(cj, club, competicion, temporada)
    pl = cj.jugadores[cj.jugadores["clave"] == destino]
    idx_bajas = []
    for b in bajas:
        cand = pl[pl["nombre"].map(_norm).map(lambda n: all(p in n for p in _norm(b).split()))]
        if cand.empty:
            raise ValueError(f"«{b}» no está en la plantilla de {destino}")
        idx_bajas.append(int(cand["min"].idxmax()))
    js = [resolver_jugador(cj, n) for n in jugadores]
    mins = list(minutos or []) + [None] * (len(js) - len(minutos or []))
    i_dest = list(cj.clubes["clave"]).index(destino)
    P0, Z0 = _pred(red, cj.Xc[[i_dest]])
    V, Qm, asignados = simular_plantilla(cj, destino, list(zip(js, mins)), idx_bajas)
    P1, Z1 = _pred(red, cj.x_club(V[None], Qm[None]))
    e0, e1 = int(P0[0].argmax()), int(P1[0].argmax())
    nivel1 = float(cj.nivel_club.indice(Qm[None])[0])
    out = [f"Club destino   {cj.clubes.at[i_dest, 'nombre_club']} ({destino}) · estilo {nombre_estilo(e0)} (p = {P0[0, e0]:.2f})"]
    for jx, m in zip(js, asignados):
        Pj, Zj = _pred(red, cj.Xj[[jx]])
        out.append(f"Fichaje        {cj.jugadores.at[jx, 'nombre']} ({cj.jugadores.at[jx, 'equipo']}, {cj.jugadores.at[jx, 'liga']} "
                   f"{cj.jugadores.at[jx, 'temporada']}) · {m:.0f} min · estilo {nombre_estilo(int(Pj[0].argmax()))} · "
                   f"distancia al club {np.linalg.norm(Zj[0] - Z0[0]):.2f}")
    for b in idx_bajas:
        out.append(f"Baja           {cj.jugadores.at[b, 'nombre']} ({cj.jugadores.at[b, 'min']:.0f} min)")
    out.append(f"Resultado      estilo {nombre_estilo(e1)} (p = {P1[0, e1]:.2f}) · el club se desplaza {np.linalg.norm(Z1[0] - Z0[0]):.2f}"
               f" · su estilo actual pasa de p = {P0[0, e0]:.2f} a {P1[0, e0]:.2f}"
               f" · nivel {cj.clubes.at[i_dest, 'nivel']:+.2f} → {nivel1:+.2f}")
    return "\n".join(out)


def informe(jugador: str, club: str = "baskonia", competicion: str = "euroleague", temporada: str = "2025-26",
            redes=("vade",), minutos: float | None = None, sustituye: str | None = None,
            temporada_jugador: str | None = None) -> str:
    cj = conjunto()
    destino = resolver_club(cj, club, competicion, temporada)
    j = resolver_jugador(cj, jugador, temporada_jugador)
    s = None
    if sustituye:
        pl = cj.jugadores[cj.jugadores["clave"] == destino]
        cand = pl[pl["nombre"].map(_norm).map(lambda n: all(p in n for p in _norm(sustituye).split()))]
        if cand.empty:
            raise ValueError(f"«{sustituye}» no está en la plantilla de {destino}")
        s = int(cand["min"].idxmax())
    out = []
    for tipo in redes:
        r = encaje(red_guardada(tipo), cj, destino, j, minutos, s)
        c, p, d, a, pl, sim = r["club"], r["jugador"], r["distancias"], r["afinidad"], r["plantilla"], r["simulacion"]
        out.append(f"=== Red {r['red']} ===")
        out.append(f"Club destino   {c['nombre']} ({destino}) · estilo {c['estilo']} (p = {c['p']:.2f}) · mapa {c['mapa']}")
        out.append(f"Jugador        {p['nombre']} · {p['equipo']} ({p['liga']} {p['temporada']}, {p['min']:.0f} min, datos {p['fuente_norm']})"
                   f" · estilo {p['estilo']} (p = {p['p']:.2f}) · mapa {p['mapa']}")
        out.append(f"Su club        {r['club_jugador']['nombre']} · estilo {r['club_jugador']['estilo']} · mapa {r['club_jugador']['mapa']}")
        out.append(f"Distancias     jugador→club destino {d['jugador_club']:.2f} (percentil {d['pct_jugador_club']:.0f} de la distancia de cada jugador a su propio club)")
        out.append(f"               club del jugador→club destino {d['club_club']:.2f} (percentil {d['pct_club_club']:.0f} entre parejas de clubes)")
        out.append(f"Afinidad       neurona del estilo del club en el jugador: {a['p_estilo_club']:.2f} · similitud de las salidas: {a['similitud_salidas']:.2f}")
        out.append(f"Plantilla      {pl['jugadores']} jugadores · dispersión {pl['dispersion']:.2f} (percentil {pl['pct_dispersion']:.0f}; alto = «una oveja de cada madre»)")
        out.append(f"               minutos en el estilo del club {pl['cuota_estilo_club']:.0%} · en el estilo del jugador {pl['cuota_estilo_jugador']:.0%}")
        out.append("               más parecidos al jugador: " + ", ".join(f"{n} ({e}, {x:.2f})" for n, e, x in pl["mas_parecidos"]))
        out.append(f"Nivel          jugador {p['nivel']:+.2f} · plantilla {pl['nivel_medio']:+.2f} (z con signo; capa aparte del estilo)")
        out.append(f"Simulación     con {sim['minutos']:.0f} min" + (f" (hereda los de {sim['sustituye']})" if sim["sustituye"] else " (a prorrata)")
                   + f": estilo {sim['estilo']} (p = {sim['p']:.2f}), el club se desplaza {sim['desplazamiento']:.2f};"
                   f" su estilo actual pasa a p = {sim['p_estilo_actual']:.2f}")
        out.append("")
    return "\n".join(out)
