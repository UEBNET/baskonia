"""Liga SINTÉTICA (datos inventados, sólo para tests) renderizada en el formato real de cada fuente.

Mismos partidos -> mismas métricas en todas las fuentes: así se comprueba que cada adaptador
interpreta bien su formato y que el motor de métricas es coherente entre ligas.
Temporada: doble vuelta entre 4 equipos (12 partidos, fase regular) + 4 partidos de playoffs.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict

TEAMS = [("T1", "Alfa Basket", "101"), ("T2", "Beta Club", "102"), ("T3", "Gamma BC", "103"),
         ("T4", "Delta Team", "104")]
MINUTES = [32, 30, 28, 26, 24, 22, 20, 18]  # suma 200 = 5 x 40
STATS = ["min", "pts", "fg2m", "fg2a", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "reb", "ast", "stl",
         "tov", "blk", "blka", "pf", "pfd", "plus_minus", "dunks"]
FIRST_ID = 100001


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


def _game(rng, gid, home, away, phase):
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
    if pts[0] == pts[1]:  # en baloncesto no hay empates
        p0 = sides[0]["players"][0]
        p0["ftm"] += 1
        p0["fta"] += 1
        p0["pts"] += 1
        pts[0] += 1
    for s, own, opp in ((sides[0], pts[0], pts[1]), (sides[1], pts[1], pts[0])):
        for p in s["players"]:
            p["plus_minus"] = round((own - opp) * p["min"] / 40)
    return {"game_id": str(gid), "phase": phase, "sides": sides}


def make_games(seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    games, gid = [], FIRST_ID
    for rnd in range(2):
        for i in range(len(TEAMS)):
            for j in range(i + 1, len(TEAMS)):
                home, away = (i, j) if rnd == 0 else (j, i)
                games.append(_game(rng, gid, home, away, "regular"))
                gid += 1
    for home, away in ((0, 3), (3, 0), (1, 2), (2, 1)):
        games.append(_game(rng, gid, home, away, "playoffs"))
        gid += 1
    return games


def by_phase(games: list[dict], phase: str) -> list[dict]:
    return games if phase == "total" else [g for g in games if g["phase"] == phase]


def season_totals(games: list[dict]) -> tuple[dict, dict]:
    """Totales por jugador y equipo (+ rivales), calculados a mano."""
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


def pir(p: dict) -> float:
    return (p["pts"] + p["reb"] + p["ast"] + p["stl"] + p["blk"] + p["pfd"] - (p["fg2a"] + p["fg3a"] - p["fg2m"] - p["fg3m"])
            - (p["fta"] - p["ftm"]) - p["tov"] - p["blka"] - p["pf"])


# ------------------------------------------------------------------ Euroliga (feed v3)
_EL = [("pts", "pointsScored"), ("fg2m", "twoPointersMade"), ("fg2a", "twoPointersAttempted"),
       ("fg3m", "threePointersMade"), ("fg3a", "threePointersAttempted"), ("ftm", "freeThrowsMade"),
       ("fta", "freeThrowsAttempted"), ("oreb", "offensiveRebounds"), ("dreb", "defensiveRebounds"),
       ("reb", "totalRebounds"), ("ast", "assists"), ("stl", "steals"), ("tov", "turnovers"),
       ("blk", "blocks"), ("pf", "foulsCommited")]


def to_euroleague(games: list[dict], phase: str) -> dict:
    pl, tm = season_totals(by_phase(games, phase))
    players = []
    for (pid, ti), P in pl.items():
        code, name, _ = TEAMS[ti]
        players.append({"player": {"code": f"P{pid}", "name": P["name"], "age": 25,
                                   "team": {"code": code, "tvCodes": code, "name": name}},
                        "gamesPlayed": P["gp"], "gamesStarted": P["gs"], "minutesPlayed": P["min"],
                        **{k2: P[k1] for k1, k2 in _EL}, "blocksAgainst": P["blka"], "foulsDrawn": P["pfd"],
                        "pir": pir(P)})
    adv = [{"player": {"code": p["player"]["code"], "team": p["player"]["team"]},
            "trueShootingPercentage": "55.5%", "possesions": 3.0} for p in players]
    teams, opps = [], []
    for ti, T in tm.items():
        code, name, _ = TEAMS[ti]
        base = {"team": {"code": code, "name": name}, "gamesPlayed": T["gp"], "minutesPlayed": T["min"] / 5}
        teams.append({**base, **{k2: T[k1] for k1, k2 in _EL}})
        opps.append({**base, **{k2: T["opp_" + k1] for k1, k2 in _EL}})
    return {"players": {"traditional": {"players": players, "total": len(players)},
                        "advanced": {"players": adv, "total": len(adv)}},
            "teams": {"traditional": {"teams": teams, "total": 4}, "opponentsTraditional": {"teams": opps, "total": 4}}}


# ------------------------------------------------------------------ G League (stats API resultSets)
def _rs(headers: list[str], rows: list[list]) -> dict:
    return {"resultSets": [{"name": "X", "headers": headers, "rowSet": rows}]}


_NBA_TEAM = ["FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "OREB", "DREB", "REB", "AST", "TOV", "STL", "BLK", "PF", "PTS"]


def to_nba_stats(games: list[dict], phase: str) -> dict:
    pl, tm = season_totals(by_phase(games, phase))
    h = ["PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "TEAM_ABBREVIATION", "AGE", "GP", "MIN", "FGM", "FGA", "FG3M", "FG3A",
         "FTM", "FTA", "OREB", "DREB", "REB", "AST", "TOV", "STL", "BLK", "BLKA", "PF", "PFD", "PTS", "PLUS_MINUS",
         "DD2", "TD3"]
    rows = [[int(pid), P["name"], int(TEAMS[ti][2]), TEAMS[ti][0], 27, P["gp"], P["min"], P["fg2m"] + P["fg3m"],
             P["fg2a"] + P["fg3a"], P["fg3m"], P["fg3a"], P["ftm"], P["fta"], P["oreb"], P["dreb"], P["reb"], P["ast"],
             P["tov"], P["stl"], P["blk"], P["blka"], P["pf"], P["pfd"], P["pts"], P["plus_minus"], P["dd2"], P["td3"]]
            for (pid, ti), P in pl.items()]
    adv = [[r[0], 110.0, 105.0, 0.2, 0.55, 0.1, 70.0] for r in rows]

    def tv(T, p):
        return [T[p + "fg2m"] + T[p + "fg3m"], T[p + "fg2a"] + T[p + "fg3a"], T[p + "fg3m"], T[p + "fg3a"], T[p + "ftm"],
                T[p + "fta"], T[p + "oreb"], T[p + "dreb"], T[p + "reb"], T[p + "ast"], T[p + "tov"], T[p + "stl"],
                T[p + "blk"], T[p + "pf"], T[p + "pts"]]
    th = ["TEAM_ID", "TEAM_NAME", "GP", "W", "L", "MIN"]
    trows = [[int(TEAMS[ti][2]), TEAMS[ti][1], T["gp"], T["w"], T["l"], T["min"] / 5] + tv(T, "") for ti, T in tm.items()]
    orows = [[int(TEAMS[ti][2]), TEAMS[ti][1], T["gp"], T["w"], T["l"], T["min"] / 5] + tv(T, "opp_")
             for ti, T in tm.items()]
    return {"Base": _rs(h, rows), "Advanced": _rs(["PLAYER_ID", "OFF_RATING", "DEF_RATING", "USG_PCT", "TS_PCT", "PIE",
                                                   "PACE"], adv),
            "teams_Base": _rs(th + _NBA_TEAM, trows), "teams_Opponent": _rs(th + ["OPP_" + x for x in _NBA_TEAM], orows),
            "playerindex": _rs(["PERSON_ID", "HEIGHT", "WEIGHT", "POSITION", "COUNTRY", "JERSEY_NUMBER"],
                               [[r[0], "6-8", "220", "F", "Spain", "9"] for r in rows])}


# ------------------------------------------------------------------ ACB (api2.acb.com)
_ACB = {"pts": "points", "fg2m": "twoPointersMade", "fg2a": "twoPointersAttempted", "fg3m": "threePointersMade",
        "fg3a": "threePointersAttempted", "ftm": "freeThrowsMade", "fta": "freeThrowsAttempted", "oreb": "offRebounds",
        "dreb": "defRebounds", "reb": "totalRebounds", "ast": "assists", "stl": "steals", "tov": "turnovers",
        "blk": "blocks", "blka": "receivedBlocks", "dunks": "dunks", "pf": "personalFouls", "pfd": "foulsDrawn",
        "plus_minus": "plusMinus"}


def to_acb(games: list[dict]) -> dict:
    rounds = [{"subphaseId": None if g["phase"] == "regular" else 7,
               "matches": [{"id": int(g["game_id"]), "matchStatus": "FINALIZED"}]} for g in games]
    box = {}
    for g in games:
        tbs = []
        for s in g["sides"]:
            code, name, tid = TEAMS[s["team_idx"]]
            players = [{"player": {"id": int(p["player_id"]), "nickname": p["name"], "shirtNumber": p["dorsal"],
                                   "gameRole": "Base"}, "playTime": f"{p['min']}:00", "isStarted": p["starter"],
                        "rating": pir(p), **{v: p[k] for k, v in _ACB.items()}} for p in s["players"]]
            total = {v: sum(p[k] for p in s["players"]) for k, v in _ACB.items() if k != "plus_minus"}
            tbs.append({"team": {"clubId": int(tid), "fullName": name, "abbreviatedName": code},
                        "statsByPeriods": [{"quarter": 0, "stats": {"players": players, "total": total}}]})
        box[g["game_id"]] = {"matchFinished": True, "teamBoxscores": tbs}
    return {"seasons": {"availableFilters": {"seasons": [{"id": 90, "seasonStartYear": 2025}]}},
            "calendar": {"rounds": rounds}, "boxscores": box}


# ------------------------------------------------------------------ LBA (legabasket.it)
_LBA = {"pts": "pun", "fg2m": "t2_r", "fg2a": "t2_t", "fg3m": "t3_r", "fg3a": "t3_t", "ftm": "tl_r", "fta": "tl_t",
        "oreb": "rimbalzi_o", "dreb": "rimbalzi_d", "reb": "rimbalzi_t", "ast": "ass", "stl": "palle_r", "tov": "palle_p",
        "blk": "stoppate_dat", "blka": "stoppate_sub", "pf": "falli_c", "pfd": "falli_sf", "dunks": "sc",
        "plus_minus": "plus_minus"}


def to_lba(games: list[dict]) -> dict:
    champs = {"competitions": [{"id": 596, "year": 2025, "cserie_code": "A1", "ctype_code": "RS"},
                               {"id": 595, "year": 2025, "cserie_code": "A1", "ctype_code": "PO"}],
              "pagination": {"pages": 1}}
    cal, scores = {"596": [], "595": []}, {}
    for g in games:
        h, v = (TEAMS[s["team_idx"]] for s in g["sides"])
        cal["596" if g["phase"] == "regular" else "595"].append(
            {"id": int(g["game_id"]), "game_status": "2", "h_team_id": int(h[2]), "h_team_name": h[1],
             "h_club_code": h[0], "v_team_id": int(v[2]), "v_team_name": v[1], "v_club_code": v[0]})
        sc = {}
        for key, s in zip(("ht", "vt"), g["sides"]):
            rows = [{"player_id": int(p["player_id"]), "player_name": p["name"].split()[0],
                     "player_surname": p["name"].split()[1], "player_num": p["dorsal"], "sf": "1" if p["starter"] else "0",
                     "sec": p["min"] * 60, "val_lega": pir(p), **{v_: p[k] for k, v_ in _LBA.items()}}
                    for p in s["players"]]
            tot = {v_: sum(p[k] for p in s["players"]) for k, v_ in _LBA.items() if k != "plus_minus"}
            sc[key] = {"rows": rows, "totals": {**tot, "sec": 12000}}
        scores[g["game_id"]] = {"match": {}, "scores": sc}
    return {"champs": champs, "calendar": cal, "scores": scores}


# ------------------------------------------------------------------ BBL (páginas de partido)
_BBL = {"pts": "points", "fg2m": "twoPointShotsMade", "fg2a": "twoPointShotsAttempted", "fg3m": "threePointShotsMade",
        "fg3a": "threePointShotsAttempted", "ftm": "freeThrowsMade", "fta": "freeThrowsAttempted",
        "oreb": "offensiveRebounds", "dreb": "defensiveRebounds", "reb": "totalRebounds", "ast": "assists",
        "stl": "steals", "tov": "turnovers", "blk": "blocks", "pf": "foulsCommitted", "pfd": "foulsReceived",
        "plus_minus": "plusMinus"}


def to_bbl_pages(games: list[dict]) -> dict[str, str]:
    pages = {}
    for g in games:
        gd = {"id": g["game_id"], "seasonId": 2025, "competition": "BBL", "status": "OFFICIAL",
              "stage": "MAIN_ROUND" if g["phase"] == "regular" else "SEMI_FINALS"}
        gs = {}
        for key, s in zip(("homeTeam", "guestTeam"), g["sides"]):
            code, name, tid = TEAMS[s["team_idx"]]
            gd[key] = {"teamId": tid, "name": name, "tlc": code}
            ps = [{"secondsPlayed": p["min"] * 60, "isStartingFive": p["starter"],
                   "seasonPlayer": {"playerId": p["player_id"], "firstName": p["name"].split()[0],
                                    "lastName": p["name"].split()[1], "shirtNumber": p["dorsal"], "position": "GUARD"},
                   **{v: p[k] for k, v in _BBL.items()}} for p in s["players"]]
            tot = {v: sum(p[k] for p in s["players"]) for k, v in _BBL.items() if k != "plus_minus"}
            gs[key] = {"gameStat": {**tot, "secondsPlayed": 12000}, "playerStats": ps}
        data = {"props": {"pageProps": {"initialGameData": gd, "initialGameStats": gs}}}
        pages[g["game_id"]] = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'
    return pages


# ------------------------------------------------------------------ LNB (api-prod.lnb.fr)
_LNB = {"gp": "s_games", "gs": "s_games_started", "min": "s_minutes_average", "pts": "s_points_average",
        "fg2m": "s_two_pointers_made_average", "fg2a": "s_two_pointers_attempted_average",
        "fg3m": "s_three_pointers_made_average", "fg3a": "s_three_pointers_attempted_average",
        "ftm": "s_free_throws_made_average", "fta": "s_free_throws_attempted_average",
        "oreb": "s_rebounds_offensive_average", "dreb": "s_rebounds_defensive_average",
        "reb": "s_rebounds_total_average", "ast": "s_assists_average", "blk": "s_blocks_average",
        "blka": "s_blocks_received", "stl": "s_steals_average", "tov": "s_turnovers_average",
        "pf": "s_fouls_total_average", "pfd": "s_fouls_on_average", "plus_minus": "s_plus_minus_points"}
LNB_HIDDEN_K = 7  # el jugador nº 7 de cada equipo no aparece en el ranking (umbral de partidos)


def to_lnb(games: list[dict]) -> dict:
    comps = {302: "regular", 311: "playoffs"}
    out = {"comps": {"data": [{"external_id": 302, "competition_name": "Betclic ÉLITE", "competition_abbrev": "PROA"},
                              {"external_id": 311, "competition_name": "Betclic ÉLITE - Playoffs",
                               "competition_abbrev": "PROA PO"}]},
           "players": {}, "teams": {}, "season_all": {}}
    for cid, phase in comps.items():
        sel = by_phase(games, phase)
        pl, tm = season_totals(sel)
        out["players"][cid] = {"data": [
            {"person": {"external_id": int(pid), "first_name": P["name"].split()[0], "family_name": P["name"].split()[1]},
             "team": {"external_id": int(TEAMS[ti][2]), "team_name": TEAMS[ti][1]}, **{v: P[k] for k, v in _LNB.items()}}
            for (pid, ti), P in pl.items() if not pid.endswith(str(LNB_HIDDEN_K))]}
        out["teams"][cid] = {"data": [
            {"team": {"external_id": int(TEAMS[ti][2]), "team_name": TEAMS[ti][1]}, "s_w_l": f"{int(T['w'])}-{int(T['l'])}",
             **{v: T[k] for k, v in _LNB.items() if k not in ("gs", "blka", "pfd")},
             "s_plus_minus_points": T["pts"] - T["opp_pts"]} for ti, T in tm.items()]}
        for (pid, ti), P in pl.items():
            if pid.endswith(str(LNB_HIDDEN_K)):
                log = [{"two_p": p["fg2m"], "two_pa": p["fg2a"], "three_p": p["fg3m"], "three_pa": p["fg3a"],
                        "ft": p["ftm"], "fta": p["fta"], "or": p["oreb"], "dr": p["dreb"]}
                       for g in sel for s in g["sides"] for p in s["players"] if p["player_id"] == pid]
                out["season_all"][(pid, cid)] = {"data": {"general": {
                    "games": P["gp"], "first_five": P["gs"], "minutes": P["min"], "points": P["pts"], "rebounds": P["reb"],
                    "assists": P["ast"], "steals": P["stl"], "blocks": P["blk"]}, "general_game_log": log}}
    out["rosters"] = {TEAMS[ti][2]: {"data": [
        {"person": {"external_id": int(player_name(ti, k)[0]), "first_name": "Jugador",
                    "family_name": player_name(ti, k)[1].split()[1], "height": 200, "nationality": "France",
                    "dob": "2000-01-01T00:00:00.000Z", "age": 25},
         "player_role": {"playing_position": "Meneur", "shirt_number": str(k + 4)}} for k in range(8)]}
        for ti in range(4)}
    return out


# ------------------------------------------------------------------ Basketball-Reference
def _bref_row(cells: list[tuple]) -> str:
    out = []
    for ds, val, href in cells:
        inner = f'<a href="{href}">{val}</a>' if href else str(val)
        out.append(f'<td data-stat="{ds}">{inner}</td>')
    return "<tr>" + "".join(out) + "</tr>"


def to_bref(games: list[dict]) -> dict[str, str]:
    def players_table(table_id, phase):
        pl, _ = season_totals(by_phase(games, phase))
        rows = []
        for (pid, ti), P in pl.items():
            code = TEAMS[ti][0]
            rows.append(_bref_row([
                ("name_display", P["name"], f"/players/x/p{pid}.html"), ("team_name_abbr", code, f"/teams/{code}/2026.html"),
                ("pos", "PG", None), ("age", 25, None), ("games", int(P["gp"]), None), ("games_started", int(P["gs"]), None),
                ("mp", int(P["min"]), None), ("fg", int(P["fg2m"] + P["fg3m"]), None), ("fga", int(P["fg2a"] + P["fg3a"]), None),
                ("fg3", int(P["fg3m"]), None), ("fg3a", int(P["fg3a"]), None), ("ft", int(P["ftm"]), None),
                ("fta", int(P["fta"]), None), ("orb", int(P["oreb"]), None), ("drb", int(P["dreb"]), None),
                ("trb", int(P["reb"]), None), ("ast", int(P["ast"]), None), ("stl", int(P["stl"]), None),
                ("blk", int(P["blk"]), None), ("tov", int(P["tov"]), None), ("pf", int(P["pf"]), None),
                ("pts", int(P["pts"]), None)]))
        return f'<table id="{table_id}"><tbody>{"".join(rows)}</tbody></table>'

    def team_page(phase):
        _, tm = season_totals(by_phase(games, phase))
        out = []
        for table, pfx in (("totals-team", ""), ("totals-opponent", "opp_")):
            rows = []
            for ti, T in tm.items():
                code, name, _ = TEAMS[ti]
                g = lambda k: int(T[pfx + k])  # noqa: E731
                ds = (lambda k: f"opp_{k}") if pfx else (lambda k: k)
                rows.append(_bref_row([
                    ("team", name, f"/teams/{code}/2026.html"), ("g", int(T["gp"]), None), ("mp", int(T["min"]), None),
                    (ds("fg"), g("fg2m") + g("fg3m"), None), (ds("fga"), g("fg2a") + g("fg3a"), None),
                    (ds("fg3"), g("fg3m"), None), (ds("fg3a"), g("fg3a"), None), (ds("ft"), g("ftm"), None),
                    (ds("fta"), g("fta"), None), (ds("orb"), g("oreb"), None), (ds("drb"), g("dreb"), None),
                    (ds("trb"), g("reb"), None), (ds("ast"), g("ast"), None), (ds("stl"), g("stl"), None),
                    (ds("blk"), g("blk"), None), (ds("tov"), g("tov"), None), (ds("pf"), g("pf"), None),
                    (ds("pts"), g("pts"), None)]))
            out.append(f'<table id="{table}"><tbody>{"".join(rows)}</tbody></table>')
        adv = "".join(_bref_row([("team", TEAMS[ti][1], f"/teams/{TEAMS[ti][0]}/2026.html"), ("wins", int(T["w"]), None),
                                 ("losses", int(T["l"]), None)]) for ti, T in tm.items())
        out.append(f'<!-- <table id="advanced-team"><tbody>{adv}</tbody></table> -->')
        return "<html>" + "".join(out) + "</html>"

    return {"totals": "<html><!--" + players_table("totals_stats", "regular") + "-->"
                      + players_table("totals_stats_post", "playoffs") + "</html>",
            "teams_regular": team_page("regular"), "teams_playoffs": team_page("playoffs")}


# ------------------------------------------------------------------ BasketNews
def to_basketnews(names: list[str]) -> dict:
    players = [{"id": 900 + i, "full_name": n} for i, n in enumerate(names)]
    stats = [{"player_id": 900 + i, "team_id": 1, "usage_percentage": {"value": 22.5, "pct": 50},
              "offensive_rating_ind": {"value": 111.0}} for i in range(len(names))]
    onoff = [{"player_id": 900 + i, "team_id": 1, "net_rating_lineup": {"value": 5.0},
              "net_rating_lineup_diff": {"value": 3.0}, "time_played_lineup": {"value": 600}} for i in range(len(names))]
    stages = [{"stage_id": 1, "total_games": 12, "translations": {"en": {"name": "Regular Season"}}},
              {"stage_id": 2, "total_games": 4, "translations": {"en": {"name": "Playoffs"}}}]
    teams = [{"id": 1, "name": "Alfa Basket"}]
    return {"players": {"success": True, "data": {"stats": stats, "players": players, "teams": teams, "stages": stages}},
            "onoff": {"success": True, "data": {"stats": onoff, "players": players, "teams": teams, "stages": stages}}}
