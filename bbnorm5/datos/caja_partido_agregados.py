"""F2 · Caja jugador-partido para las competiciones cuyos totales salen de agregados de temporada (EuroLeague, EuroCup,
NBA, G League, LNB), desde el boxscore oficial guardado en sus brutos de jugada a jugada (`data/raw/<liga>/<t>/pbp_*`).

Identidad: el boxscore oficial usa ids de su fuente (NBA.com en la NBA, UUID en la LNB…), no siempre los de
`data/processed`. Por eso cada línea del boxscore se empareja con la fila del mismo partido de la tabla jugador-partido
(`data/modelos/roles/partidos_jugador`, ya en ids de `data/processed` y con `persona_id`) por su vector de tiro y
anotación (pts, TC, T3 y TL anotados e intentados, asistencias), y se desempata por minutos. Se informa la tasa de
emparejamiento; las líneas sin pareja se conservan con `player_id` vacío y no se usan aguas abajo.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from bbnorm5 import config as C

LIGAS_AGREGADOS = ["euroleague", "eurocup", "nba", "gleague", "lnb"]
CLAVE = ["pts", "fga", "fgm", "fg3a", "fg3m", "fta", "ftm", "ast"]


def _seg(m) -> float:
    """'23:49', 'PT20M29S', '26' → segundos."""
    if m is None:
        return np.nan
    if isinstance(m, (int, float)):
        return float(m) * 60
    s = str(m).strip()
    r = re.fullmatch(r"PT(?:(\d+)M)?(?:([\d.]+)S)?", s)
    if r:
        return 60 * float(r.group(1) or 0) + float(r.group(2) or 0)
    if ":" in s:
        a, b = s.split(":")[:2]
        try:
            return 60 * float(a) + float(b)
        except ValueError:
            return np.nan
    try:
        return float(s) * 60
    except ValueError:
        return np.nan


def _fila(gid, ref, lado, nombre, starter, st: dict) -> dict:
    return {"game_id": str(gid), "fecha": str(ref.get("date") or "")[:10], "fase": ref.get("phase") or "regular",
            "lado": lado, "nombre_box": nombre, "starter": starter, **st}


def lineas_euroleague(gid, g) -> list[dict]:
    out = []
    for k, eq in enumerate(((g["docs"].get("box") or {}).get("Stats")) or []):
        for p in eq.get("PlayersStats") or []:
            st = {"min_s": _seg(p.get("Minutes")), "pts": p.get("Points"),
                  "fgm": (p.get("FieldGoalsMade2") or 0) + (p.get("FieldGoalsMade3") or 0),
                  "fga": (p.get("FieldGoalsAttempted2") or 0) + (p.get("FieldGoalsAttempted3") or 0),
                  "fg3m": p.get("FieldGoalsMade3"), "fg3a": p.get("FieldGoalsAttempted3"),
                  "ftm": p.get("FreeThrowsMade"), "fta": p.get("FreeThrowsAttempted"),
                  "oreb": p.get("OffensiveRebounds"), "dreb": p.get("DefensiveRebounds"), "ast": p.get("Assistances"),
                  "stl": p.get("Steals"), "tov": p.get("Turnovers"), "blk": p.get("BlocksFavour"),
                  "blka": p.get("BlocksAgainst"), "pf": p.get("FoulsCommited"), "pfd": p.get("FoulsReceived"),
                  "id_fuente": str(p.get("Player_ID") or "").strip().lstrip("P")}
            out.append(_fila(gid, g["ref"], k, p.get("Player"), bool(p.get("IsStarter")), st))
    return out


def lineas_nba(gid, g) -> list[dict]:
    out = []
    b = (g["docs"].get("box") or {}).get("boxScoreTraditional") or {}
    for k, lado in enumerate(("homeTeam", "awayTeam")):
        for p in (b.get(lado) or {}).get("players") or []:
            s = p.get("statistics") or {}
            st = {"min_s": _seg(s.get("minutes")), "pts": s.get("points"), "fgm": s.get("fieldGoalsMade"),
                  "fga": s.get("fieldGoalsAttempted"), "fg3m": s.get("threePointersMade"),
                  "fg3a": s.get("threePointersAttempted"), "ftm": s.get("freeThrowsMade"), "fta": s.get("freeThrowsAttempted"),
                  "oreb": s.get("reboundsOffensive"), "dreb": s.get("reboundsDefensive"), "ast": s.get("assists"),
                  "stl": s.get("steals"), "tov": s.get("turnovers"), "blk": s.get("blocks"), "pf": s.get("foulsPersonal"),
                  "id_fuente": str(p.get("personId") or "")}
            out.append(_fila(gid, g["ref"], k, f"{p.get('firstName', '')} {p.get('familyName', '')}".strip(),
                             None, st))
    return out


def lineas_lnb(gid, g) -> list[dict]:
    out = []
    base = ((((g["docs"].get("statistics") or {}).get("statistics") or {}).get("data") or {}).get("base")) or {}
    for k, lado in enumerate(("home", "away")):
        for bloque in (base.get(lado) or {}).get("persons") or []:
            for p in bloque.get("rows") or []:
                s = p.get("statistics") or {}
                st = {"min_s": _seg(s.get("minutes")), "pts": s.get("points"),
                      "fgm": (s.get("pointsTwoMade") or 0) + (s.get("pointsThreeMade") or 0),
                      "fga": (s.get("pointsTwoAttempted") or 0) + (s.get("pointsThreeAttempted") or 0),
                      "fg3m": s.get("pointsThreeMade"), "fg3a": s.get("pointsThreeAttempted"),
                      "ftm": s.get("freeThrowsMade"), "fta": s.get("freeThrowsAttempted"),
                      "oreb": s.get("reboundsOffensive"), "dreb": s.get("reboundsDefensive"), "ast": s.get("assists"),
                      "stl": s.get("steals"), "tov": s.get("turnovers"), "blk": s.get("blocks"),
                      "blka": s.get("blocksReceived"), "pf": s.get("foulsTotal"), "id_fuente": str(p.get("personId") or "")}
                out.append(_fila(gid, g["ref"], k, p.get("personName"), p.get("starter"), st))
    return out


LECTORES = {"euroleague": lineas_euroleague, "eurocup": lineas_euroleague, "nba": lineas_nba, "gleague": lineas_nba,
            "lnb": lineas_lnb}


def boxscores(liga: str, temporada: str) -> pd.DataFrame:
    """Todas las líneas de boxscore oficial de la temporada (todos los paquetes pbp_*; un partido repetido se queda
    con la versión más reciente)."""
    from bbstats.config import load_config, resolve_path
    from bbstats.raw_store import RawStore
    cfg = load_config()
    store = RawStore(resolve_path(cfg, "bruto"))
    juegos: dict = {}
    for f in store.list(liga, temporada, kind="pbp"):
        juegos.update((store.load(f).get("payload") or {}).get("games") or {})
    filas = []
    for gid, g in juegos.items():
        if not isinstance(g, dict) or not (g.get("ref") or {}).get("final", True):
            continue
        try:
            filas += LECTORES[liga](gid, g)
        except Exception:                      # noqa: BLE001 - un partido mal formado no detiene la temporada
            continue
    d = pd.DataFrame(filas)
    if d.empty:
        return d
    for c in [c for c in d.columns if c not in ("game_id", "fecha", "fase", "lado", "nombre_box", "starter", "id_fuente")]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


def emparejar(box: pd.DataFrame, pj: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Identidad por votación a nivel de temporada.

    1. Candidatas: pares (línea de boxscore, fila jugador-partido) del mismo partido con el mismo vector CLAVE.
    2. Para cada id de la fuente del boxscore, el `player_id` con más votos (partidos coincidentes) entre sus candidatas,
       si tiene ≥ 2 votos o ≥ 50 % de sus partidos; si dos ids de la fuente reclaman el mismo `player_id`, gana el de
       más votos y el otro queda sin identidad.
    3. Se aplica la identidad a TODOS sus partidos (también donde el jugada a jugada no reproduce el boxscore).
    4. Equipo y rival de cada (partido, lado): moda de los equipos de sus jugadores identificados en ese partido en la
       tabla jugador-partido; si el partido no está en ella, moda de su equipo más frecuente en la temporada."""
    b = box.copy()
    p = pj[pj["jugo"]].copy()
    for c in CLAVE:
        b[c] = pd.to_numeric(b[c], errors="coerce").fillna(0).astype(float)
        p[c] = pd.to_numeric(p[c], errors="coerce").fillna(0).astype(float)
    b["_k"] = b[CLAVE].astype(int).astype(str).agg("|".join, axis=1)
    p["_k"] = p[CLAVE].astype(int).astype(str).agg("|".join, axis=1)
    jug = b[b["min_s"].fillna(0) > 0]
    cand = jug[["game_id", "_k", "id_fuente"]].merge(p[["game_id", "_k", "player_id"]], on=["game_id", "_k"])
    votos = cand.groupby(["id_fuente", "player_id"]).size().rename("votos").reset_index()
    n_part = jug.groupby("id_fuente")["game_id"].nunique().rename("partidos")
    votos = votos.merge(n_part, on="id_fuente")
    votos = votos[(votos["votos"] >= 2) | (votos["votos"] >= 0.5 * votos["partidos"])]
    votos = votos.sort_values("votos", ascending=False)
    votos = votos.drop_duplicates("id_fuente").drop_duplicates("player_id")
    mapa = dict(zip(votos["id_fuente"], votos["player_id"]))
    b["player_id"] = b["id_fuente"].map(mapa)
    # equipo por (partido, lado)
    eq_pj = p[["game_id", "player_id", "team_id", "opp_id"]].drop_duplicates(["game_id", "player_id"])
    x = b.dropna(subset=["player_id"]).merge(eq_pj, on=["game_id", "player_id"], how="left")
    moda = lambda s: s.dropna().mode().iat[0] if s.notna().any() else np.nan   # noqa: E731
    eq = x.groupby(["game_id", "lado"]).agg(team_id=("team_id", moda), opp_id=("opp_id", moda)).reset_index()
    sin = eq["team_id"].isna()
    if sin.any():
        hab = p.groupby("player_id")["team_id"].agg(lambda s: s.mode().iat[0])
        x2 = b.dropna(subset=["player_id"]).assign(t=lambda z: z["player_id"].map(hab))
        eq2 = x2.groupby(["game_id", "lado"])["t"].agg(moda).rename("t2").reset_index()
        eq = eq.merge(eq2, on=["game_id", "lado"], how="left")
        eq["team_id"] = eq["team_id"].fillna(eq["t2"])
        eq = eq.drop(columns="t2")
    otro = eq[["game_id", "lado", "team_id"]].assign(lado=lambda z: 1 - z["lado"]).rename(columns={"team_id": "opp2"})
    eq = eq.merge(otro, on=["game_id", "lado"], how="left")
    eq["opp_id"] = eq["opp_id"].fillna(eq["opp2"])
    b = b.drop(columns=["_k"]).merge(eq.drop(columns="opp2"), on=["game_id", "lado"], how="left")
    per = p.drop_duplicates("player_id").set_index("player_id")
    for c in ("persona_id", "pos3"):
        if c in per:
            b[c] = b["player_id"].map(per[c])
    info = {"ids_fuente": int(jug["id_fuente"].nunique()), "ids_identificados": int(len(mapa))}
    return b, info


def por_nombre(box: pd.DataFrame, liga: str, temporada: str) -> tuple[pd.DataFrame, dict]:
    """Respaldo sin tabla jugador-partido (LNB 2020-21): nombre normalizado único en la liga-temporada procesada.
    El equipo de cada (partido, lado) es la moda de los equipos de sus jugadores identificados (si un jugador
    estuvo en dos equipos, no aporta)."""
    from bbnorm5.datos.entidades import normalizar
    f = C.RAIZ / "data" / "processed" / temporada / "ligas" / f"{liga}.csv"
    q = pd.read_csv(f, usecols=["fase", "player_id", "team_id", "nombre"], dtype=str)
    q = q[q["fase"].isin(["regular", "playoffs"])].drop_duplicates(["player_id", "team_id"])
    q["n"] = q["nombre"].map(normalizar)
    unico = q.groupby("n")["player_id"].nunique()
    q = q[q["n"].map(unico) == 1]
    pid = q.drop_duplicates("n").set_index("n")["player_id"]
    eq1 = q.groupby("player_id")["team_id"].agg(lambda s: s.iat[0] if s.nunique() == 1 else np.nan)
    b = box.copy()
    b["player_id"] = b["nombre_box"].map(normalizar).map(pid)
    b["_t"] = b["player_id"].map(eq1)
    moda = lambda s: s.dropna().mode().iat[0] if s.notna().any() else np.nan   # noqa: E731
    eq = b.groupby(["game_id", "lado"])["_t"].agg(moda).rename("team_id").reset_index()
    otro = eq.assign(lado=lambda z: 1 - z["lado"]).rename(columns={"team_id": "opp_id"})
    b = b.drop(columns="_t").merge(eq, on=["game_id", "lado"], how="left").merge(otro, on=["game_id", "lado"], how="left")
    jug = b[b["min_s"].fillna(0) > 0]
    return b, {"ids_fuente": int(jug["nombre_box"].nunique()), "ids_identificados": int(jug["player_id"].dropna().nunique()),
               "metodo_identidad": "nombre único"}


def construir(ligas: list[str], temporadas: list[str]) -> pd.DataFrame:
    sal = C.DIR_DATOS / "limpios" / "caja_partido"
    resumen = []
    for t in temporadas:
        fpj = C.RAIZ / "data" / "modelos" / "roles" / "partidos_jugador" / f"{t}.csv.gz"
        pj_all = pd.read_csv(fpj, low_memory=False, dtype={"game_id": str, "player_id": str, "team_id": str,
                                                          "opp_id": str}) if fpj.exists() else pd.DataFrame()
        if len(pj_all):
            pj_all["jugo"] = pj_all["jugo"].astype(str).str.lower().isin(["true", "1"])
        for liga in ligas:
            box = boxscores(liga, t)
            if box.empty:
                resumen.append({"liga": liga, "temporada": t, "estado": "sin boxscore en bruto"})
                continue
            pj = pj_all[pj_all["liga"] == liga] if len(pj_all) else pj_all
            d, info = emparejar(box, pj) if len(pj) else por_nombre(box, liga, t)
            d["liga"], d["temporada"] = liga, t
            d["min"] = d["min_s"] / 60
            d["fg2m"], d["fg2a"] = d["fgm"] - d["fg3m"], d["fga"] - d["fg3a"]
            d["reb"] = d["oreb"] + d["dreb"]
            d["jugo"] = d["min_s"].fillna(0) > 0
            # totales de equipo y rival en el partido (suma de las líneas de cada lado)
            num = ["min", "pts", "fgm", "fga", "fg2m", "fg2a", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "reb",
                   "ast", "stl", "tov", "blk", "pf"]
            tot = d.groupby(["game_id", "lado"])[num].sum()
            own = tot.add_prefix("team_").reset_index()
            opp = tot.add_prefix("opp_").reset_index().assign(lado=lambda x: 1 - x["lado"])
            d = d.merge(own, on=["game_id", "lado"], how="left").merge(opp, on=["game_id", "lado"], how="left")
            (sal / t).mkdir(parents=True, exist_ok=True)
            d.to_parquet(sal / t / f"{liga}.parquet", index=False, compression="zstd")
            jug = d[d["jugo"]]
            fila = {"liga": liga, "temporada": t, "estado": "ok", "partidos": int(d["game_id"].nunique()),
                    "lineas_jugadas": int(len(jug)), "emparejadas": float(jug["player_id"].notna().mean()),
                    "partidos_pj": int(pj["game_id"].nunique()) if len(pj) else 0, **info}
            from bbnorm5.datos.caja_partido import comprobar
            chk = comprobar(jug[jug["player_id"].notna()].assign(jugo=True), liga, t)
            for fase, r in chk.items():
                for k, v in r.items():
                    fila[f"{fase}_{k}"] = v
            resumen.append(fila)
            print(f"  {liga} {t}: {fila['partidos']} partidos · emparejadas {fila['emparejadas']:.3f} · "
                  f"regular {({k: round(v, 3) for k, v in chk.get('regular', {}).items() if k.startswith('ok_')})}", flush=True)
    return pd.DataFrame(resumen)
