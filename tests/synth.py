"""Generador de una liga SINTÉTICA (datos inventados, sólo para tests) y renderizado de la misma
en el formato de cada fuente. Permite comprobar que todos los adaptadores producen las mismas
columnas y las mismas métricas a partir de los mismos datos."""
from __future__ import annotations

import json
import random
from collections import defaultdict

TEAMS = [("T1", "Alfa Basket", "101"), ("T2", "Beta Club", "102"), ("T3", "Gamma BC", "103"),
         ("T4", "Delta Team", "104")]
MINUTES = [32, 30, 28, 26, 24, 22, 20, 18]  # suma 200 = 5 x 40
STATS = ["min", "pts", "fg2m", "fg2a", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "reb", "ast", "stl",
         "tov", "blk", "blka", "pf", "pfd", "plus_minus", "dunks"]


def player_name(team_idx: int, k: int) -> tuple[str, str]:
    return f"{30000 + team_idx * 100 + k}", f"Jugador {chr(65 + team_idx)}{k}"


def _line(rng: random.Random, minutes: int) -> dict:
    f = minutes / 30
    fg2a = int(rng.randint(3, 10) * f)
    fg2m = rng.randint(0, fg2a)
    fg3a = int(rng.randint(0, 7) * f)
    fg3m = rng.randint(0, fg3a)
    fta = int(rng.randint(0, 6) * f)
    ftm = rng.randint(0, fta)
    oreb, dreb = rng.randint(0, 3), rng.randint(0, 7)
    return {"min": minutes, "fg2m": fg2m, "fg2a": fg2a, "fg3m": fg3m, "fg3a": fg3a, "ftm": ftm, "fta": fta,
            "pts": 2 * fg2m + 3 * fg3m + ftm, "oreb": oreb, "dreb": dreb, "reb": oreb + dreb,
            "ast": rng.randint(0, 7), "stl": rng.randint(0, 3), "tov": rng.randint(0, 4),
            "blk": rng.randint(0, 2), "blka": rng.randint(0, 1), "pf": rng.randint(0, 5),
            "pfd": rng.randint(0, 5), "dunks": min(fg2m, rng.randint(0, 1))}


def make_games(seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    games = []
    gid = 100000
    for rnd in range(2):
        for i in range(len(TEAMS)):
            for j in range(i + 1, len(TEAMS)):
                home, away = (i, j) if rnd == 0 else (j, i)
                gid += 1
                sides = []
                for ti in (home, away):
                    players = []
                    for k, m in enumerate(MINUTES):
                        pid, name = player_name(ti, k)
                        line = _line(rng, m)
                        line.update({"player_id": pid, "name": name, "starter": k < 5, "dorsal": str(k + 4)})
                        players.append(line)
                    sides.append({"team_idx": ti, "players": players})
                pts = [sum(p["pts"] for p in s["players"]) for s in sides]
                if pts[0] == pts[1]:  # en baloncesto no hay empates: tiro libre extra
                    p0 = sides[0]["players"][0]
                    p0["ftm"] += 1
                    p0["fta"] += 1
                    p0["pts"] += 1
                    pts[0] += 1
                for s, own, opp in ((sides[0], pts[0], pts[1]), (sides[1], pts[1], pts[0])):
                    for p in s["players"]:
                        p["plus_minus"] = round((own - opp) * p["min"] / 40)
                games.append({"game_id": str(gid), "sides": sides})
    return games


def season_totals(games: list[dict]) -> tuple[dict, dict]:
    """Totales de temporada por jugador y por equipo (+ rivales), calculados a mano."""
    pl: dict = defaultdict(lambda: defaultdict(float))
    tm: dict = defaultdict(lambda: defaultdict(float))
    for g in games:
        tots = []
        for s in g["sides"]:
            t = defaultdict(float)
            for p in s["players"]:
                for k in STATS:
                    t[k] += p[k]
            tots.append(t)
        for idx, s in enumerate(g["sides"]):
            ti = s["team_idx"]
            own, opp = tots[idx], tots[1 - idx]
            T = tm[ti]
            T["gp"] += 1
            T["w"] += own["pts"] > opp["pts"]
            T["l"] += own["pts"] < opp["pts"]
            for k in STATS:
                T[k] += own[k]
                T["opp_" + k] += opp[k]
            for p in s["players"]:
                P = pl[(p["player_id"], ti)]
                P["name"] = p["name"]
                P["gp"] += 1
                P["gs"] += p["starter"]
                for k in STATS:
                    P[k] += p[k]
                tens = sum(p[c] >= 10 for c in ("pts", "reb", "ast", "stl", "blk"))
                P["dd2"] += tens >= 2
                P["td3"] += tens >= 3
    return pl, tm


# ------------------------------------------------------------------ FIBA LiveStats data.json
def to_fiba(game: dict) -> dict:
    tm = {}
    for n, s in zip(("1", "2"), game["sides"]):
        code, name, _ = TEAMS[s["team_idx"]]
        pl = {}
        tot = defaultdict(float)
        for i, p in enumerate(s["players"], 1):
            first, family = p["name"].split(" ", 1)
            pl[str(i)] = {"firstName": first, "familyName": family, "name": p["name"],
                          "personId": p["player_id"], "shirtNumber": p["dorsal"], "playingPosition": "G",
                          "starter": 1 if p["starter"] else 0, "sMinutes": f"{p['min']}:00",
                          "sPoints": p["pts"], "sFieldGoalsMade": p["fg2m"] + p["fg3m"],
                          "sFieldGoalsAttempted": p["fg2a"] + p["fg3a"], "sTwoPointersMade": p["fg2m"],
                          "sTwoPointersAttempted": p["fg2a"], "sThreePointersMade": p["fg3m"],
                          "sThreePointersAttempted": p["fg3a"], "sFreeThrowsMade": p["ftm"],
                          "sFreeThrowsAttempted": p["fta"], "sReboundsOffensive": p["oreb"],
                          "sReboundsDefensive": p["dreb"], "sReboundsTotal": p["reb"], "sAssists": p["ast"],
                          "sSteals": p["stl"], "sTurnovers": p["tov"], "sBlocks": p["blk"],
                          "sBlocksReceived": p["blka"], "sFoulsPersonal": p["pf"], "sFoulsOn": p["pfd"],
                          "sPlusMinusPoints": p["plus_minus"]}
            for k in STATS:
                tot[k] += p[k]
        tm[n] = {"name": name, "code": code, "score": tot["pts"], "pl": pl,
                 "tot_sPoints": tot["pts"], "tot_sTwoPointersMade": tot["fg2m"],
                 "tot_sTwoPointersAttempted": tot["fg2a"], "tot_sThreePointersMade": tot["fg3m"],
                 "tot_sThreePointersAttempted": tot["fg3a"], "tot_sFreeThrowsMade": tot["ftm"],
                 "tot_sFreeThrowsAttempted": tot["fta"], "tot_sReboundsOffensive": tot["oreb"],
                 "tot_sReboundsDefensive": tot["dreb"], "tot_sAssists": tot["ast"], "tot_sSteals": tot["stl"],
                 "tot_sTurnovers": tot["tov"], "tot_sBlocks": tot["blk"], "tot_sFoulsPersonal": tot["pf"],
                 "tot_sMinutes": "200:00"}
    return {"tm": tm, "period": 4, "clock": "00:00", "periodType": "REGULAR"}


# ------------------------------------------------------------------ ACB HTML
def to_acb_html(game: dict) -> str:
    out = ["<html><head><title>Alfa - Beta | ACB.com</title></head><body><p>Jornada 1 · 05/10/2025</p>"]
    for s in game["sides"]:
        code, name, tid = TEAMS[s["team_idx"]]
        out.append(f'<div class="cabecera_equipo"><a href="/club/plantilla/id/{tid}">{name}</a></div>')
        out.append("<table><thead><tr>"
                   '<th rowspan="2">D</th><th rowspan="2">Nombre</th><th rowspan="2">Min</th><th rowspan="2">P</th>'
                   '<th rowspan="2">T2</th><th rowspan="2">T2 %</th><th rowspan="2">T3</th><th rowspan="2">T3 %</th>'
                   '<th rowspan="2">T1</th><th rowspan="2">T1 %</th><th colspan="2">REB</th>'
                   '<th rowspan="2">A</th><th rowspan="2">BR</th><th rowspan="2">BP</th><th rowspan="2">C</th>'
                   '<th colspan="2">TAP</th><th rowspan="2">M</th><th colspan="2">FP</th>'
                   '<th rowspan="2">+/-</th><th rowspan="2">V</th></tr>'
                   "<tr><th>T</th><th>D+O</th><th>F</th><th>C</th><th>C</th><th>F</th></tr></thead><tbody>")
        tot = defaultdict(float)
        for p in s["players"]:
            v = (p["pts"] + p["reb"] + p["ast"] + p["stl"] + p["blk"] + p["pfd"] - (p["fg2a"] + p["fg3a"] - p["fg2m"] - p["fg3m"])
                 - (p["fta"] - p["ftm"]) - p["tov"] - p["blka"] - p["pf"])
            star = "*" if p["starter"] else ""
            slug = p["name"].lower().replace(" ", "-")
            out.append(
                f"<tr><td>{star}{p['dorsal']}</td><td><a href=\"/jugador/ver/{p['player_id']}-{slug}\">{p['name']}</a></td>"
                f"<td>{p['min']}:00</td><td>{p['pts']}</td><td>{p['fg2m']}/{p['fg2a']}</td><td>-</td>"
                f"<td>{p['fg3m']}/{p['fg3a']}</td><td>-</td><td>{p['ftm']}/{p['fta']}</td><td>-</td>"
                f"<td>{p['reb']}</td><td>{p['dreb']}+{p['oreb']}</td><td>{p['ast']}</td><td>{p['stl']}</td>"
                f"<td>{p['tov']}</td><td>0</td><td>{p['blk']}</td><td>{p['blka']}</td><td>{p['dunks']}</td>"
                f"<td>{p['pf']}</td><td>{p['pfd']}</td><td>{p['plus_minus']}</td><td>{v}</td></tr>")
            for k in STATS:
                tot[k] += p[k]
        out.append("<tr><td></td><td>Equipo</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td>"
                   "<td></td><td>0</td><td>0+0</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td>"
                   "<td></td><td></td><td></td><td></td></tr>")
        t = {k: int(v) for k, v in tot.items()}
        out.append(
            f"<tr><td>Total</td><td></td><td>200:00</td><td>{t['pts']}</td><td>{t['fg2m']}/{t['fg2a']}</td><td>-</td>"
            f"<td>{t['fg3m']}/{t['fg3a']}</td><td>-</td><td>{t['ftm']}/{t['fta']}</td><td>-</td><td>{t['reb']}</td>"
            f"<td>{t['dreb']}+{t['oreb']}</td><td>{t['ast']}</td><td>{t['stl']}</td><td>{t['tov']}</td><td>0</td>"
            f"<td>{t['blk']}</td><td>{t['blka']}</td><td>{t['dunks']}</td><td>{t['pf']}</td><td>{t['pfd']}</td>"
            f"<td></td><td></td></tr>")
        out.append("</tbody></table>")
    out.append("</body></html>")
    return "".join(out)


def acb_calendar_html(game_ids: list[str]) -> str:
    links = "".join(f'<a href="/partido/estadisticas/id/{g}">Estadísticas</a>' for g in game_ids)
    return f"<html><body>{links}</body></html>"


# ------------------------------------------------------------------ Euroliga v3
def to_euroleague(games: list[dict]) -> dict:
    pl, tm = season_totals(games)
    players = []
    for (pid, ti), P in pl.items():
        code, name, _ = TEAMS[ti]
        players.append({
            "playerRanking": 1,
            "player": {"code": f"P{pid}", "name": P["name"], "age": 25,
                       "team": {"code": code, "tvCodes": code, "name": name}},
            "gamesPlayed": P["gp"], "gamesStarted": P["gs"], "minutesPlayed": P["min"],
            "pointsScored": P["pts"], "twoPointersMade": P["fg2m"], "twoPointersAttempted": P["fg2a"],
            "twoPointersPercentage": f"{100 * P['fg2m'] / P['fg2a']:.1f}%" if P["fg2a"] else "0%",
            "threePointersMade": P["fg3m"], "threePointersAttempted": P["fg3a"],
            "freeThrowsMade": P["ftm"], "freeThrowsAttempted": P["fta"], "offensiveRebounds": P["oreb"],
            "defensiveRebounds": P["dreb"], "totalRebounds": P["reb"], "assists": P["ast"], "steals": P["stl"],
            "turnovers": P["tov"], "blocks": P["blk"], "blocksAgainst": P["blka"], "foulsCommited": P["pf"],
            "foulsDrawn": P["pfd"], "pir": None})
    adv = [{"player": {"code": p["player"]["code"], "team": p["player"]["team"]},
            "trueShootingPercentage": "55.5%", "possessions": 100} for p in players]
    teams, opps = [], []
    for ti, T in tm.items():
        code, name, _ = TEAMS[ti]
        base = {"team": {"code": code, "name": name}, "gamesPlayed": T["gp"], "minutesPlayed": T["min"]}
        teams.append({**base, **{k2: T[k1] for k1, k2 in _EL_MAP}})
        opps.append({**base, **{k2: T["opp_" + k1] for k1, k2 in _EL_MAP}})
    return {"players": {"traditional": [{"players": players, "total": len(players)}],
                        "advanced": [{"players": adv, "total": len(adv)}], "misc": [], "scoring": []},
            "teams": {"traditional": [{"teams": teams, "total": 4}],
                      "opponentsTraditional": [{"teams": opps, "total": 4}]}}


_EL_MAP = [("pts", "pointsScored"), ("fg2m", "twoPointersMade"), ("fg2a", "twoPointersAttempted"),
           ("fg3m", "threePointersMade"), ("fg3a", "threePointersAttempted"), ("ftm", "freeThrowsMade"),
           ("fta", "freeThrowsAttempted"), ("oreb", "offensiveRebounds"), ("dreb", "defensiveRebounds"),
           ("reb", "totalRebounds"), ("ast", "assists"), ("stl", "steals"), ("tov", "turnovers"),
           ("blk", "blocks"), ("pf", "foulsCommited")]


# ------------------------------------------------------------------ NBA resultSets
def _rs(headers: list[str], rows: list[list]) -> dict:
    return {"resultSets": [{"name": "X", "headers": headers, "rowSet": rows}]}


def to_nba(games: list[dict]) -> dict:
    pl, tm = season_totals(games)
    h = ["PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "TEAM_ABBREVIATION", "AGE", "GP", "W", "L", "MIN", "FGM", "FGA",
         "FG3M", "FG3A", "FTM", "FTA", "OREB", "DREB", "REB", "AST", "TOV", "STL", "BLK", "BLKA", "PF", "PFD",
         "PTS", "PLUS_MINUS", "DD2", "TD3"]
    rows = []
    for (pid, ti), P in pl.items():
        code, _, tid = TEAMS[ti]
        rows.append([int(pid), P["name"], int(tid), code, 27, P["gp"], 0, 0, P["min"], P["fg2m"] + P["fg3m"],
                     P["fg2a"] + P["fg3a"], P["fg3m"], P["fg3a"], P["ftm"], P["fta"], P["oreb"], P["dreb"],
                     P["reb"], P["ast"], P["tov"], P["stl"], P["blk"], P["blka"], P["pf"], P["pfd"], P["pts"],
                     P["plus_minus"], P["dd2"], P["td3"]])
    adv_h = ["PLAYER_ID", "OFF_RATING", "DEF_RATING", "USG_PCT", "TS_PCT", "PIE", "PACE"]
    adv = [[r[0], 110.0, 105.0, 0.2, 0.55, 0.1, 70.0] for r in rows]
    th = ["TEAM_ID", "TEAM_NAME", "GP", "W", "L", "MIN", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "OREB",
          "DREB", "REB", "AST", "TOV", "STL", "BLK", "PF", "PTS"]
    oh = ["TEAM_ID", "TEAM_NAME", "GP", "W", "L", "MIN"] + ["OPP_" + x for x in th[6:]]
    trows, orows = [], []
    for ti, T in tm.items():
        _, name, tid = TEAMS[ti]
        vals = lambda p: [T[p + "fg2m"] + T[p + "fg3m"], T[p + "fg2a"] + T[p + "fg3a"], T[p + "fg3m"],  # noqa: E731
                          T[p + "fg3a"], T[p + "ftm"], T[p + "fta"], T[p + "oreb"], T[p + "dreb"], T[p + "reb"],
                          T[p + "ast"], T[p + "tov"], T[p + "stl"], T[p + "blk"], T[p + "pf"], T[p + "pts"]]
        game_min = T["min"] / 5  # NBA publica minutos de partido
        trows.append([int(tid), name, T["gp"], T["w"], T["l"], game_min] + vals(""))
        orows.append([int(tid), name, T["gp"], T["w"], T["l"], game_min] + vals("opp_"))
    idx_h = ["PERSON_ID", "HEIGHT", "WEIGHT", "POSITION", "COUNTRY", "JERSEY_NUMBER", "TEAM_CITY", "TEAM_NAME"]
    idx = [[r[0], "6-8", "220", "F", "Spain", "9", "City", "Club"] for r in rows]
    return {"Base": _rs(h, rows), "Advanced": _rs(adv_h, adv), "teams_Base": _rs(th, trows),
            "teams_Opponent": _rs(oh, orows), "playerindex": _rs(idx_h, idx),
            "hustle": _rs(["PLAYER_ID", "DEFLECTIONS", "CONTESTED_SHOTS"], [[r[0], 10, 50] for r in rows])}


# ------------------------------------------------------------------ tabla HTML genérica
def to_html_table(games: list[dict]) -> str:
    pl, _ = season_totals(games)
    head = ["Joueur", "Equipe", "G", "MIN", "PTS", "2PM", "2PA", "3PM", "3PA", "FTM", "FTA", "OREB", "DREB",
            "REB", "AST", "STL", "TOV", "BLK", "PF"]
    rows = []
    for (pid, ti), P in pl.items():
        rows.append([P["name"], TEAMS[ti][1], P["gp"], P["min"], P["pts"], P["fg2m"], P["fg2a"], P["fg3m"],
                     P["fg3a"], P["ftm"], P["fta"], P["oreb"], P["dreb"], P["reb"], P["ast"], P["stl"], P["tov"],
                     P["blk"], P["pf"]])
    th = "".join(f"<th>{h}</th>" for h in head)
    trs = "".join("<tr>" + "".join(f"<td>{int(v) if isinstance(v, float) else v}</td>" for v in r) + "</tr>"
                  for r in rows)
    return f"<html><body><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></body></html>"


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
