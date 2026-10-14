"""Clubes y jugadores parecidos (scouting por estilo).

El parecido se mide en los 13 rasgos de estilo sin nivel (la entrada de las redes), no en el mapa 3D: es
más fino y no depende del modelo (6 u 8 estilos). Una distancia se traduce a «parecido» (0-100) con su
percentil entre parejas reales del mismo tipo: 100 = más parecido que cualquier pareja; 50 = como una
pareja típica.

  clubes_parecidos       clubes que juegan como el club de referencia (cualquier liga y temporada).
  jugadores_parecidos    dos modos:
      · "jugador": parecidos a un jugador de referencia (p. ej. uno que se va de la plantilla);
      · "club":    jugadores cuyo propio perfil encaja con el estilo del club de referencia.
    Opcionalmente, sólo en los N clubes más parecidos al de referencia («alguien como X, en un equipo
    que juegue como el mío»). Puntuación = peso · parecido del jugador + (1 − peso) · parecido de su club.

    python -m bbestilo parecidos --club baskonia [--competicion euroleague] [--temporada 2025-26]
                                 [--jugador "Nombre"] [--alcance 30] [--temporadas 2025-26 ...]
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from .datos import Conjunto, club_alias

MIN_REF = 300


def referencias(cj: Conjunto, semilla: int = 3) -> dict:
    """Distribuciones de distancias en los 13 rasgos para traducir distancias a parecido."""
    rng = np.random.default_rng(semilla)
    sel = ~cj.clubes["provisional"].to_numpy()
    Xc = cj.Xc[sel]
    iu = np.triu_indices(len(Xc), 1)
    d_cc = np.sqrt(((Xc[:, None] - Xc[None]) ** 2).sum(-1))[iu]
    J = cj.jugadores
    mj = ((J["min"] >= MIN_REF) & ~J["provisional"]).to_numpy()
    Xj = cj.Xj[mj]
    a, b = rng.integers(0, len(Xj), 200_000), rng.integers(0, len(Xj), 200_000)
    ok = a != b
    d_jj = np.linalg.norm(Xj[a[ok]] - Xj[b[ok]], axis=1)
    pos = dict(zip(cj.clubes["clave"], range(len(cj.clubes))))
    d_jc = np.linalg.norm(Xj - cj.Xc[J.loc[mj, "clave"].map(pos).to_numpy()], axis=1)
    q = np.linspace(0, 100, 101)
    return {"club_club": np.percentile(d_cc, q), "jug_jug": np.percentile(d_jj, q), "jug_club": np.percentile(d_jc, q)}


def mismo_club(clave_club: str) -> set[str]:
    """Todas las claves del mismo club (sus competiciones), según config/clubes.json."""
    for a in club_alias().values():
        if clave_club in a.get("claves", []):
            return set(a["claves"])
    return {clave_club}


def parecido(d: np.ndarray, quant: np.ndarray) -> np.ndarray:
    """100 · (1 − percentil de la distancia entre las parejas de referencia)."""
    return 100.0 - np.interp(d, quant, np.linspace(0, 100, 101))


def clubes_parecidos(cj: Conjunto, clave: str, ref: dict, n: int = 15, temporadas=None, ligas=None,
                     excluir_propio: bool = True) -> pd.DataFrame:
    c = cj.clubes.reset_index(drop=True)
    i = int(np.flatnonzero(c["clave"] == clave)[0])
    d = np.linalg.norm(cj.Xc - cj.Xc[i], axis=1)
    out = c[["clave", "clave_club", "nombre_club", "liga", "temporada", "nivel", "provisional"]].copy()
    out["distancia"], out["parecido"] = d, parecido(d, ref["club_club"])
    m = out["clave"] != clave
    if excluir_propio:
        m &= ~out["clave_club"].isin(mismo_club(c.at[i, "clave_club"]))
    if temporadas:
        m &= out["temporada"].isin(temporadas)
    if ligas:
        m &= out["liga"].isin(ligas)
    return out[m].sort_values("distancia").head(n)


def jugadores_parecidos(cj: Conjunto, clave_club: str, ref: dict, jugador: int | None = None, alcance: int | None = 30,
                        temporadas=None, ligas=None, posiciones=None, min_min: float = MIN_REF, edad_max: float | None = None,
                        nivel_min: float | None = None, peso_jugador: float = 0.7, n: int = 25,
                        excluir_propio: bool = True) -> pd.DataFrame:
    """jugador = índice en cj.jugadores (modo «jugador»); None = modo «club» (encaje con el estilo del club)."""
    c = cj.clubes.reset_index(drop=True)
    pos = dict(zip(c["clave"], range(len(c))))
    ic = pos[clave_club]
    J = cj.jugadores.copy()
    J["i"] = np.arange(len(J))
    J["edad"] = J["temporada"].str[:4].astype(int) - pd.to_numeric(J["anio_nac"], errors="coerce")
    m = (J["min"] >= min_min).to_numpy().copy()
    if temporadas:
        m &= J["temporada"].isin(temporadas).to_numpy()
    if ligas:
        m &= J["liga"].isin(ligas).to_numpy()
    if posiciones:
        m &= J["pos3"].isin(posiciones).to_numpy()
    if edad_max is not None:
        m &= (J["edad"].fillna(99) <= edad_max).to_numpy()
    if nivel_min is not None:
        m &= (J["nivel"] >= nivel_min).to_numpy()
    if excluir_propio:
        m &= (~J["clave_club"].isin(mismo_club(c.at[ic, "clave_club"]))).to_numpy()
    if jugador is not None:
        m &= J["i"].to_numpy() != jugador
        pid = J.at[J.index[jugador], "persona_id"]
        if pd.notna(pid):
            m &= (J["persona_id"] != pid).to_numpy()
    cand = J[m].copy()
    if jugador is not None:
        d_j = np.linalg.norm(cj.Xj[cand["i"].to_numpy()] - cj.Xj[jugador], axis=1)
        p_j = parecido(d_j, ref["jug_jug"])
    else:
        d_j = np.linalg.norm(cj.Xj[cand["i"].to_numpy()] - cj.Xc[ic], axis=1)
        p_j = parecido(d_j, ref["jug_club"])
    ci = cand["clave"].map(pos).to_numpy()
    d_c = np.linalg.norm(cj.Xc[ci] - cj.Xc[ic], axis=1)
    cand["parecido_jugador"], cand["parecido_club"] = p_j, parecido(d_c, ref["club_club"])
    if alcance:
        cercanos = clubes_parecidos(cj, clave_club, ref, n=alcance, temporadas=temporadas, ligas=ligas,
                                    excluir_propio=excluir_propio)["clave"]
        cand = cand[cand["clave"].isin(set(cercanos))]
    cand["puntuacion"] = peso_jugador * cand["parecido_jugador"] + (1 - peso_jugador) * cand["parecido_club"]
    # un jugador con filas en dos competiciones (EuroLeague y su liga) aparece una vez, con su mejor fila
    cand["persona"] = cand["persona_id"].fillna(cand["liga"] + ":" + cand["player_id"].astype(str))
    cand = cand.sort_values("puntuacion", ascending=False).drop_duplicates("persona")
    cols = ["nombre", "nombre_club", "liga", "temporada", "pos3", "edad", "min", "nivel", "parecido_jugador",
            "parecido_club", "puntuacion"]
    return cand.sort_values("puntuacion", ascending=False).head(n)[cols]


def informe(club: str, competicion: str, temporada: str, jugador: str | None, alcance: int | None,
            temporadas: list[str] | None, n: int = 20) -> str:
    from .encaje import conjunto, resolver_club, resolver_jugador
    cj = conjunto()
    clave = resolver_club(cj, club, competicion, temporada)
    ref = referencias(cj)
    temporadas = temporadas or [temporada]
    j = None
    if jugador:
        pl = cj.jugadores[cj.jugadores["clave"] == clave]
        j = resolver_jugador(cj, jugador, temporada)
        if j not in set(pl.index):
            print(f"Aviso: {cj.jugadores.at[j, 'nombre']} no está en la plantilla de {clave}; se usa igualmente como referencia.")
    pd.set_option("display.width", 200)
    out = [f"Clubes que juegan como {clave}:",
           clubes_parecidos(cj, clave, ref, n=10, temporadas=temporadas).round(2).to_string(index=False), ""]
    ref_txt = f"parecidos a {cj.jugadores.at[j, 'nombre']}" if j is not None else "que encajan con el estilo del club"
    out += [f"Jugadores {ref_txt}" + (f", en los {alcance} clubes más parecidos" if alcance else "") + ":",
            jugadores_parecidos(cj, clave, ref, j, alcance, temporadas, n=n,
                                posiciones=[cj.jugadores.at[j, "pos3"]] if j is not None else None).round(1).to_string(index=False)]
    return "\n".join(out)
