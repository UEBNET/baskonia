"""CBA: nombres latinos, fases, Sina y traducción QQ (+ Sina) al data.json de FIBA LiveStats (to_fls)."""
from bbstats.adapters.cba import (_chrono, fase_de, nombre_latino, parse_payload, sina_box, sina_schedule,
                                  to_fls)
from bbstats.config import minutos_partido
from bbstats.lineups.sources.base import Ctx
from bbstats.lineups.sources.cba import CbaPBP
from bbstats.lineups.stints import build

HEAD = ["号码/球员", "时间", "得分", "篮板", "助攻", "投篮", "三分", "罚球", "抢断", "盖帽", "失误", "犯规", "+/-"]


def _row(pid, num, cn, mins, pts, reb, fg, fg3, ft, pm):
    return {"playerId": pid, "row": [num, cn, mins, str(pts), str(reb), "0", fg, fg3, ft, "0", "0", "0", "1", pm]}


def _ev(n, q, t, at, team, txt, pid=None, rid=None, lg="0", rg="0", left=None, right=None):
    return {f"{n}_{n}": {"content": txt, "time": t, "quarter": str(q), "teamId": team, "leftGoal": lg, "rightGoal": rg,
                         "broadcast": {"actionType": at, "player": {"id": pid} if pid else None,
                                       "relatedPlayer": {"id": rid} if rid else None, "team": {"id": team}},
                         "match": {"playerList": {"left": left or [], "right": right or []}}}}


SINA_HTML = """<!-- part01 start --><h2 class="blk_title"><span>辽宁</span>主教练：杨鸣&nbsp;领队：x</h2><table>
<tr><th>球员</th><th>号码</th><th>出场时间</th><th>首发</th><th>2分中-投</th><th>3分中-投</th><th>罚球中-投</th>
<th>进攻篮板</th><th>防守篮板</th><th>助攻</th><th>犯规</th><th>抢断</th><th>失误</th><th>盖帽</th><th>得分</th></tr>
{rows_h}</table><!-- part01 end --><!-- part02 start --><h2 class="blk_title"><span>新疆</span>主教练：乌戈·洛佩斯&nbsp;</h2>
<table><tr><th>球员</th><th>号码</th><th>出场时间</th><th>首发</th><th>2分中-投</th><th>3分中-投</th><th>罚球中-投</th>
<th>进攻篮板</th><th>防守篮板</th><th>助攻</th><th>犯规</th><th>抢断</th><th>失误</th><th>盖帽</th><th>得分</th></tr>
{rows_a}</table>"""


def _srow(sid, cn, num, starter, oreb, dreb, pts):
    return (f'<tr><td><a href="http://cba.sports.sina.com.cn/cba/player/show/{sid}/">{cn}</a></td><td>{num}</td><td>20</td>'
            f'<td>{"是" if starter else ""}</td><td>0-0 (0%)</td><td>0-0 (0%)</td><td>0-0 (0%)</td><td>{oreb}</td>'
            f'<td>{dreb}</td><td>0</td><td>0</td><td>0</td><td>0</td><td>0</td>'
            f'<td><script>document.write("{pts}");</script></td></tr>')


def _game():
    home = [("h%d" % i, str(i), "主%d" % i) for i in range(1, 7)]
    away = [("a%d" % i, str(10 + i), "客%d" % i) for i in range(1, 7)]
    # local: h1 anota un triple asistido por h2 (3 pts); h6 entra por h5; rebote def de h3 (QQ reb 1 = 0 + 1 Sina)
    left = [{"head": HEAD}] + [_row(p, n, c, "20'00", 3 if p == "h1" else 0, 1 if p == "h3" else 0,
                                    "1/1" if p == "h1" else "0/0", "1/1" if p == "h1" else "0/0", "0/0", "+3")
                               for p, n, c in home]
    right = [{"head": HEAD}] + [_row(p, n, c, "20'00", 0, 0, "0/1" if p == "a1" else "0/0", "0/0", "0/0", "-3")
                                for p, n, c in away]
    on_h = ["h1", "h2", "h3", "h4", "h5"]
    on_a = ["a1", "a2", "a3", "a4", "a5"]
    ev = {}
    ev.update(_ev(1, 1, "12:00", "13", "0", "第1节开始"))
    ev.update(_ev(2, 1, "11:40", "1", "T1", "主1收到主2助攻，三分投篮命中", "h1", "h2", "3", "0", on_h, on_a))
    ev.update(_ev(3, 1, "11:20", "2", "T2", "客1的跳投被主4封盖，不中", "a1", None, "3", "0", on_h, on_a))
    ev.update(_ev(4, 1, "11:20", "3", "T1", "主3抢到防守篮板球", "h3", None, "3", "0", on_h, on_a))
    ev.update(_ev(5, 1, "11:00", "4", "T2", "客2失误，球被主5抢断", "a2", None, "3", "0", on_h, on_a))
    ev.update(_ev(6, 1, "10:50", "5", "T2", "客3对主1打手犯规", "a3", None, "3", "0", on_h, on_a))
    ev.update(_ev(7, 1, "10:50", "9", "T1", "主队换人，主6上场，换下主5", "h5", "h6", "3", "0",
                  ["h1", "h2", "h3", "h4", "h6"], on_a))
    ev.update(_ev(8, 1, "10:40", "3", "T2", "客队抢到防守篮板球", None, None, "3", "0"))
    ev.update(_ev(9, 4, "00:00", "15", "0", "全场比赛结束", None, None, "3", "0"))
    ids = list(ev)
    # QQ intercala a veces eventos fuera de orden: el del minuto 11:00 llega al final del índice
    index = list(reversed([ids[0], ids[1], ids[2], ids[3], ids[5], ids[6], ids[7], ids[8], ids[4]]))
    rows_h = "".join(_srow(100 + i, c, n, i <= 5, 0, 1 if p == "h3" else 0, 3 if p == "h1" else 0)
                     for i, (p, n, c) in enumerate(home, 1))
    rows_a = "".join(_srow(200 + i, c, n, i <= 5, 0, 0, 0) for i, (p, n, c) in enumerate(away, 1))
    return {"cal": {"mid": "100008:1", "matchDesc": "CBA常规赛第1轮", "startTime": "2024-12-01 19:35:00",
                    "matchPeriod": "2", "leftId": "T1", "rightId": "T2", "leftGoal": "3", "rightGoal": "0"},
            "stat": {"teamInfo": {"leftId": "T1", "rightId": "T2", "leftName": "辽宁本钢", "rightName": "新疆广汇",
                                  "leftEnName": "LIAO NING", "rightEnName": "XIN JIANG", "leftGoal": "3",
                                  "rightGoal": "0"},
                     "playerStats": {"left": left, "right": right},
                     "teamStats": [{"text": "得分", "leftVal": "3", "rightVal": "0"},
                                   {"text": "篮板", "leftVal": "1", "rightVal": "1"}]},
            "pbp_index": index, "pbp": ev,
            "sina": {"sid": "9", "html": SINA_HTML.format(rows_h=rows_h, rows_a=rows_a)}}


JUG = {"h1": {"cnName": "周琦", "enName": "ZHOU Q.", "birthDate": "1996-01-16", "height": "216.0cm"},
       "a1": {"cnName": "谢里夫·库珀", "enName": "S. COOPER"}}


def test_nombres_y_fases():
    assert nombre_latino("周琦", "ZHOU Q.")["name"] == "Zhou Qi"
    assert nombre_latino("赵继伟", "ZHAO J.W.") == {"first": "Jiwei", "family": "Zhao", "name": "Zhao Jiwei",
                                                   "tipo": "chino"}
    assert nombre_latino("欧阳振翔", "OUYANG Z.X.")["name"] == "Ouyang Zhenxiang"
    assert nombre_latino("阿不都沙拉木", "ABDUSALAM")["name"] == "Abdusalam"
    assert nombre_latino("谢里夫·库珀", "S. COOPER")["name"] == "S. Cooper"
    assert nombre_latino("吉默·弗雷戴特", "Jimmer Fredette")["family"] == "Fredette"
    assert nombre_latino("乌戈·洛佩斯", None, {"乌戈·洛佩斯": "Hugo López"})["family"] == "López"
    assert fase_de("CBA常规赛第4轮") == "regular" and fase_de("CBA季后赛总决赛G1") == "playoffs"
    assert fase_de("CBA季前赛") is None and fase_de("CBA全明星赛") is None


def test_minutos_por_temporada():
    cfg = {"minutos_partido": 40, "temporadas": {"2024-25": {"minutos_partido": 48}}}
    assert minutos_partido(cfg, "2024-25") == 48 and minutos_partido(cfg, "2025-26") == 40
    assert Ctx(league="cba", season="2024-25", cfg=cfg).game_min == 48
    assert minutos_partido({}, "2024-25") == 40


def test_sina():
    rows = sina_box(_game()["sina"]["html"])
    assert [r["equipo"] for r in rows] == ["辽宁", "新疆"] and rows[1]["entrenador"] == "乌戈·洛佩斯"
    assert rows[0]["jugadores"][0]["pts"] == 3 and rows[0]["jugadores"][0]["starter"] is True
    html = ('<tr><td>2020-10-17&nbsp;16:00</td><td><a href="http://cba.sports.sina.com.cn/cba/team/show/7/">江苏</a></td>'
            '<td><a href="http://cba.sports.sina.com.cn/cba/schedule/show/19143/">94&#58;102</a></td>'
            '<td><a href="http://cba.sports.sina.com.cn/cba/team/show/8/">青岛</a></td></tr>')
    assert sina_schedule(html) == [{"sid": "19143", "fecha": "2020-10-17", "local": "江苏", "visitante": "青岛",
                                    "pts_local": 94, "pts_visitante": 102}]


def test_to_fls_y_quintetos():
    g = _game()
    order = _chrono(list(reversed(g["pbp_index"])), g["pbp"])
    assert [g["pbp"][i]["time"] for i in order][:6] == ["12:00", "11:40", "11:20", "11:20", "11:00", "10:50"]
    f = to_fls(g, JUG, {"nombres_latinos": {"乌戈·洛佩斯": "Hugo López"}})
    t1, t2 = f["tm"]["1"], f["tm"]["2"]
    assert t1["name"] == "Liaoning" and t1["coach"] == "Yang Ming" and t2["coach"] == "Hugo López"
    h1 = t1["pl"]["1"]
    assert h1["name"] == "Zhou Qi" and h1["nameLocal"] == "周琦" and h1["sMinutes"] == "20:00"
    assert h1["sThreePointersMade"] == 1 and h1["starter"] == 1 and h1["sFoulsOn"] == 1
    assert t1["pl"]["3"]["sReboundsDefensive"] == 1 and t1["pl"]["3"]["sReboundsOffensive"] == 0
    assert t2["pl"]["1"]["sBlocksReceived"] == 1
    acts = list(reversed(f["pbp"]))
    kinds = [(a["actionType"], a["subType"], a["tno"], a["pno"]) for a in acts]
    assert ("3pt", "", 1, 1) in kinds and ("assist", "", 1, 2) in kinds and ("block", "", 1, 4) in kinds
    assert ("steal", "", 1, 5) in kinds and ("foulon", "", 1, 1) in kinds
    assert kinds.index(("substitution", "out", 1, 5)) < kinds.index(("substitution", "in", 1, 6))
    assert any(a["actionType"] == "rebound" and a.get("qualifier") == ["team"] for a in acts)
    payload = {"fases": {"1": "regular"}, "games": {"1": g}, "jugadores": JUG}
    out = parse_payload(payload, {})
    p = {r["player_id"]: r for r in out["regular"].players}
    assert p["h1"]["nombre"] == "Zhou Qi" and p["h1"]["fecha_nacimiento"] == "1996-01-16" and p["h1"]["pts"] == 3
    cfg = {"minutos_partido": 40, "temporadas": {"2024-25": {"minutos_partido": 48}}}
    ctx = Ctx(league="cba", season="2024-25", cfg=cfg, main_payload=payload)
    src = CbaPBP()
    ref = src.games(ctx)[0]
    game = src.parse(src.fetch(ctx, ref), ref, ctx)
    assert ref["teams"] == ["T1", "T2"] and game.players["h1"]["nombre"] == "Zhou Qi"
    res = build(game, ctx.game_min)
    assert res.anomalies.get("actua_fuera_de_pista", 0) == 0
