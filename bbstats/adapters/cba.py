"""CBA (Chinese Basketball Association): Tencent Sports (QQ) + Sina, partido a partido, todo público.

QQ (matchweb.sports.qq.com; JSON sin token, sólo User-Agent de navegador):
    /matchUnion/list?columnId=100008&startTime=AAAA-MM-01&endTime=AAAA-MM-DD&...   calendario de un mes
        mid = "100008:<id>" (<id> = el scheduleId oficial de la CBA), matchDesc (CBA常规赛…, CBA季后赛…,
        CBA季前赛, CBA全明星赛), startTime, left* = local, right* = visitante, matchPeriod 2 = terminado
    /kbs/matchStat?mid=100008:<id>            boxscore: playerStats (fila por jugador con playerId de QQ:
        minutos "30'40", pts, reb TOTAL, ast, TC/T3/TL "m/a", rob, tap, pérd, faltas, +/-), teamStats (totales
        de equipo CON rebotes y pérdidas de equipo), teamInfo (ids de equipo QQ, nombre chino y enName)
    /textLive/index?competitionId=100008&matchId=<id>            ids de los eventos (más reciente primero)
    /textLive/detail?competitionId=100008&matchId=<id>&ids=a,b   eventos: broadcast.actionType (1 canasta,
        2 fallo, 3 rebote, 4 pérdida, 5 falta, 6/7 TL anotado/fallado, 9 cambio, 10 tiempo muerto, 11 salto,
        13/14 inicio/fin de periodo, 15 fin), player/relatedPlayer (id QQ), team, texto en chino; desde 2025-26
        además match.playerList = los cinco en pista. Sin jugada a jugada: 2020-21 y ene-may 2025.
    /player/baseInfo?playerId=<id>&from=web   ficha: cnName, enName ("ZHAO J.W.", "S. COOPER", a veces el
        nombre completo), fecha de nacimiento, altura
Sina (cba.sports.sina.com.cn; HTML GBK):
    /cba/schedule/all/?qleagueid=<L>     calendario de la temporada (L en config temporadas.<t>.sina_liga)
    /cba/schedule/show/<id>/             boxscore con rebotes OF/DEF, titulares y entrenador principal
Se casan por fecha y marcador (local, visitante); los jugadores, por lado + dorsal (+ nombre chino).

Traducción al data.json de FIBA LiveStats (`to_fls`) para reutilizar el jugada a jugada de FibaLiveStatsPBP.
Ids: jugador = playerId de QQ (estable entre temporadas), equipo = id de equipo QQ (estable).
Nombres latinos (`nombre_latino`): chinos → pinyin (pypinyin) guiado por las iniciales del enName de QQ,
«Apellido Nombre» (周琦 → "Zhou Qi"); minorías con enName de una palabra → esa palabra; extranjeros → enName
("S. Cooper"). `nombres_latinos` en la config ({"nombre chino": "Nombre latino"}) manda sobre todo lo demás.
Bruto INCREMENTAL: sólo los partidos nuevos; de cada uno se guarda el JSON de QQ (los eventos sin imágenes ni
textos de patrocinio) y el trozo de HTML de Sina con las dos tablas.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

from ..http import FetchError, HttpClient
from ..utils import to_float
from .base import AdapterError, NoDataYet, ParsedLeague
from .boxscore import aggregate_by_phase
from .fiba_livestats import FibaLiveStatsAdapter, parse_fiba_game

QQ = "https://matchweb.sports.qq.com"
COMP = "100008"
LIST_URL = QQ + "/matchUnion/list?today={d1}&startTime={d1}&endTime={d2}&columnId=100008&index=3&isInit=true&timestamp=1"
STAT_URL = QQ + "/kbs/matchStat?mid=100008:{mid}"
TL_INDEX_URL = QQ + "/textLive/index?competitionId=100008&matchId={mid}"
TL_DETAIL_URL = QQ + "/textLive/detail?competitionId=100008&matchId={mid}&ids={ids}"
PLAYER_URL = QQ + "/player/baseInfo?playerId={pid}&from=web"
SINA = "http://cba.sports.sina.com.cn"
SINA_LIST_URL = SINA + "/cba/schedule/all/?qleagueid={liga}&qmonth=&qteamid="
SINA_GAME_URL = SINA + "/cba/schedule/show/{sid}/"
HEADERS = {"Referer": "https://sports.qq.com/", "Accept": "application/json, text/plain, */*"}


def fase_de(desc: str) -> str | None:
    """matchDesc de QQ -> fase: 常规赛 = regular, 季后赛 = playoffs (final incluida); el resto (季前赛,
    全明星赛, 保级, 杯赛…) fuera."""
    d = str(desc or "")
    if any(x in d for x in ("全明星", "季前", "保级", "杯", "附加")):
        return None
    if "常规赛" in d:
        return "regular"
    if "季后赛" in d or "总决赛" in d:
        return "playoffs"
    return None


# =============================================================================================== nombres
_COMPOUND = ("欧阳", "司马", "上官", "诸葛", "东方", "皇甫", "尉迟", "公孙", "慕容", "长孙", "宇文", "司徒",
             "夏侯", "轩辕", "令狐", "端木", "独孤", "南宫", "西门", "百里", "呼延", "申屠", "太史", "澹台")

# apellidos chinos frecuentes (para distinguir un nombre chino de una transliteración sin «·»: 阿的江, 乌戈…)
_SURNAMES = set("王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任"
                "沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴"
                "莫孔向汤常温康施文牛樊葛邢安齐易乔伍庞颜倪庄聂章鲁岳翟殷詹申欧耿关兰焦俞左柳甘祝包宁尚符舒阮柯"
                "纪梅童凌毕单季裴霍涂成苗谷盛曲翁冉骆蓝路游辛靳管柴蒙鲍华喻祁蒲房滕屈饶解牟艾尤阳时穆农司卓古吉"
                "缪简车项连芦麦褚娄窦戚岑景党宫费卜冷晏席卫米柏宗瞿桂全佟应臧闵苟邬边卞姬师和仇栾隋商刁沙荣巫寇"
                "桑郎甄丛仲虞敖巩明佘池查麻苑迟邝逄彰偰容原")

try:   # opcional: sin pypinyin los chinos quedan con el enName de QQ ("Zhao J.W.")
    from pypinyin import Style, pinyin as _pinyin
except ImportError:  # pragma: no cover
    _pinyin = None


def _py(ch: str, initial: str | None = None) -> str | None:
    """Pinyin (sin tonos) de un carácter; con `initial`, la lectura que empieza por esa letra (polifónicos)."""
    if _pinyin is None:
        return None
    opts = [o.replace("ü", "u").replace("v", "u") for o in
            (_pinyin(ch, style=Style.NORMAL, heteronym=True, v_to_u=True) or [[""]])[0] if o]
    if not opts or not re.fullmatch(r"[a-z]+", opts[0]):
        return None
    if initial:
        for o in opts:
            if o[0] == initial.lower():
                return o
    return opts[0]


# lecturas de apellido y de nombre de pila de caracteres polifónicos (pypinyin da la lectura común)
_SURNAME_PY = {"曾": "zeng", "单": "shan", "仇": "qiu", "解": "xie", "查": "zha", "区": "ou", "朴": "piao", "盖": "ge",
               "乐": "yue", "缪": "miao", "覃": "qin", "翟": "zhai", "繁": "po", "种": "chong", "员": "yun"}
_GIVEN_PY = {"长": "chang", "乐": "le", "重": "chong", "行": "xing", "的": "di"}


def _py_phrase(cn: str) -> list[str] | None:
    """Pinyin carácter a carácter con el diccionario de frases de pypinyin (polifónicos: 长锁 -> chang suo)."""
    if _pinyin is None:
        return None
    sy = [(x[0] if x else "").replace("ü", "u").replace("v", "u")
          for x in _pinyin(cn, style=Style.NORMAL, v_to_u=True)]
    if sy:
        sy[0] = _SURNAME_PY.get(cn[0], sy[0])
        sy[1:] = [_GIVEN_PY.get(c, x) for c, x in zip(cn[1:], sy[1:])]
    return sy if sy and all(re.fullmatch(r"[a-z]+", x) for x in sy) and len(sy) == len(cn) else None


def _cap(s: str) -> str:
    return " ".join(w[:1].upper() + w[1:].lower() if w else w for w in s.split(" "))


def nombre_latino(cn: str | None, en: str | None, override: dict | None = None) -> dict:
    """{"first", "family", "name", "tipo"} latinos a partir del nombre chino y el enName de QQ.

    tipo: "chino" (pinyin), "minoria" (nombre uigur/… de una palabra), "extranjero", "override", "sin_latino"."""
    cn, en = (cn or "").strip(), re.sub(r"\s+", " ", (en or "").strip())
    ov = (override or {}).get(cn)
    if ov:
        parts = ov.split(" ", 1)
        return {"first": parts[0] if len(parts) > 1 else "", "family": parts[-1], "name": ov, "tipo": "override"}
    m = re.fullmatch(r"([A-Z][A-Z' -]*?)\s+((?:[A-Z]\.)+)", en)
    if m and cn and "·" not in cn:                                         # "ZHAO J.W." (chino)
        fam_en = m.group(1).replace(" ", "")
        inits = re.findall(r"[A-Z]", m.group(2))
        n_fam = len(cn) - len(inits)
        if n_fam < 1:
            n_fam = 2 if cn[:2] in _COMPOUND else 1
        given_cn = cn[n_fam:]
        sy = [_py(c, inits[i] if i < len(inits) else None) for i, c in enumerate(given_cn)]
        if sy and all(sy):
            given = "".join(sy).capitalize()
            family = fam_en.capitalize()
            return {"first": given, "family": family, "name": f"{family} {given}", "tipo": "chino"}
        family, given = fam_en.capitalize(), m.group(2)
        return {"first": given, "family": family, "name": f"{family} {given}", "tipo": "chino"}
    if re.fullmatch(r"[A-Z][A-Z'-]+", en):                                  # "ABDUSALAM" (minoría)
        return {"first": "", "family": en.capitalize(), "name": en.capitalize(), "tipo": "minoria"}
    m = re.fullmatch(r"((?:[A-Z]\.\s?)+)\s*([A-Za-z].*)", en)               # "S. COOPER", "D. LE DEE"
    if m:
        first = m.group(1).replace(" ", "")
        family = _cap(m.group(2)) if m.group(2).isupper() else m.group(2)
        return {"first": first, "family": family, "name": f"{first} {family}", "tipo": "extranjero"}
    if en and re.search(r"[A-Za-z]", en):                                    # "Jimmer Fredette"
        en2 = _cap(en) if en.isupper() else en
        parts = en2.split(" ", 1)
        return {"first": parts[0] if len(parts) > 1 else "", "family": parts[-1], "name": en2,
                "tipo": "extranjero"}
    if cn and "·" not in cn and re.fullmatch(r"[一-鿿]{2,4}", cn):  # sin enName: pinyin directo
        n_fam = 2 if cn[:2] in _COMPOUND else 1
        sy = _py_phrase(cn)
        if sy and n_fam == 1 and cn[0] not in _SURNAMES:      # transliteración (阿的江 -> Adijiang)
            w = "".join(sy).capitalize()
            return {"first": "", "family": w, "name": w, "tipo": "transliterado"}
        if sy:
            family = "".join(sy[:n_fam]).capitalize()
            given = "".join(sy[n_fam:]).capitalize()
            return {"first": given, "family": family, "name": f"{family} {given}", "tipo": "chino"}
    return {"first": "", "family": cn, "name": cn, "tipo": "sin_latino"}


def entrenador_latino(cn: str | None, override: dict | None = None) -> dict | None:
    """Entrenador (Sina sólo lo da en chino) -> {"first", "family", "name", "tipo"}: override de la config
    ("Nombre Apellido") o pinyin; los extranjeros (nombre transliterado, con «·») sin override quedan en chino."""
    cn = (cn or "").strip()
    if not cn:
        return None
    ov = (override or {}).get(cn)
    if ov:
        parts = ov.split(" ", 1)
        return {"first": parts[0] if len(parts) > 1 else "", "family": parts[-1], "name": ov, "tipo": "override"}
    return nombre_latino(cn, None)


def equipo_latino(en: str | None, cn: str | None) -> str:
    """enName de QQ ("LIAO NING") -> "Liaoning"; si no hay, el nombre chino."""
    en = (en or "").strip()
    return "".join(en.split()).capitalize() if en else (cn or "")


# =============================================================================================== Sina
_TAG = re.compile(r"<[^>]+>")


def _txt(s: str) -> str:
    s = re.sub(r'document\.write\("([^"]*)"\);?', r"\1", s)
    s = _TAG.sub(" ", s).replace("&nbsp;", " ").replace("&#58;", ":")
    return re.sub(r"\s+", " ", s).strip()


def sina_schedule(html: str) -> list[dict]:
    """Calendario de Sina: [{"sid", "fecha", "local", "visitante", "pts_local", "pts_visitante"}]."""
    out, seen = [], set()
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html or "", re.S):
        m = re.search(r"schedule/show/(\d+)/", row)
        d = re.search(r"(\d{4}-\d{2}-\d{2})", row)
        if not m or not d or m.group(1) in seen:
            continue
        sc = re.search(r"(\d+)\s*(?:&nbsp;)?\s*(?::|&#58;)\s*(?:&nbsp;)?\s*(\d+)", _TAG.sub(" ", row.split(m.group(0), 1)[1]))
        teams = [_txt(t) for t in re.findall(r"team/show/\d+/[^>]*>(.*?)</a>", row, re.S)]
        seen.add(m.group(1))
        out.append({"sid": m.group(1), "fecha": d.group(1), "local": teams[0] if teams else None,
                    "visitante": teams[1] if len(teams) > 1 else None,
                    "pts_local": int(sc.group(1)) if sc else None, "pts_visitante": int(sc.group(2)) if sc else None})
    return out


def sina_slice(html: str) -> str | None:
    """Trozo del HTML del partido de Sina con las dos tablas (y el entrenador de cada equipo)."""
    a = (html or "").find("<!-- part01 start -->")
    if a < 0:
        return None
    ends = [m.end() for m in re.finditer("</table>", html[a:])]
    return html[a:a + ends[1]] if len(ends) >= 2 else None


SINA_COLS = {"球员": "name", "号码": "dorsal", "出场时间": "min", "首发": "starter", "2分中-投": "fg2",
             "3分中-投": "fg3", "罚球中-投": "ft", "进攻篮板": "oreb", "防守篮板": "dreb", "助攻": "ast",
             "犯规": "pf", "抢断": "stl", "失误": "tov", "盖帽": "blk", "得分": "pts"}


def sina_box(fragment: str | None) -> list[dict]:
    """[{"equipo", "entrenador", "jugadores": [...], "total": {...}}] (orden de la página: local, visitante)."""
    out = []
    for part in re.split(r"<!-- part0\d start -->", fragment or "")[1:]:
        h2 = re.search(r"<h2[^>]*>(.*?)</h2>", part, re.S)
        team = re.search(r"<span>(.*?)</span>", h2.group(1)).group(1).strip() if h2 and "<span>" in h2.group(1) else None
        coach = re.search(r"主教练：([^&<]*)", h2.group(1)) if h2 else None
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", part, re.S)
        if not rows:
            continue
        head = [_txt(c) for c in re.findall(r"<th[^>]*>(.*?)</th>", rows[0], re.S)]
        cols = [SINA_COLS.get(h) for h in head]
        players, total = [], None
        for r in rows[1:]:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
            if len(cells) != len(cols):
                continue
            rec: dict[str, Any] = {}
            pid = re.search(r"player/show/(\d+)/", cells[0])
            for c, v in zip(cols, cells):
                if c:
                    rec[c] = _txt(v)
            for c in ("fg2", "fg3", "ft"):
                m = re.match(r"(\d+)-(\d+)", rec.get(c) or "")
                rec[c] = (int(m.group(1)), int(m.group(2))) if m else None
            for c in ("min", "oreb", "dreb", "ast", "pf", "stl", "tov", "blk", "pts"):
                rec[c] = to_float(rec.get(c))
            rec["starter"] = rec.get("starter") == "是"
            if pid:
                rec["sina_id"] = pid.group(1)
                players.append(rec)
            else:
                total = rec
        out.append({"equipo": team, "entrenador": coach.group(1).strip() if coach else None,
                    "jugadores": players, "total": total})
    return out


# =============================================================================================== QQ -> data.json
def _mmss(v: Any) -> str | None:
    """"30'40" -> "30:40", "46'" -> "46:00"."""
    s = str(v or "").strip()
    m = re.fullmatch(r"(\d+)'(\d*)", s)
    if m:
        return f"{int(m.group(1))}:{int(m.group(2) or 0):02d}"
    return s if re.fullmatch(r"\d+:\d{2}", s) else None


def _ma(v: Any) -> tuple[float | None, float | None]:
    m = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", str(v or ""))
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)


QQ_HEAD = {"号码/球员": "num", "时间": "min", "得分": "pts", "篮板": "reb", "助攻": "ast", "投篮": "fg",
           "三分": "fg3", "罚球": "ft", "抢断": "stl", "盖帽": "blk", "失误": "tov", "犯规": "pf", "+/-": "pm"}
TEAM_STAT = {"得分": "sPoints", "篮板": "sReboundsTotal", "助攻": "sAssists", "抢断": "sSteals", "盖帽": "sBlocks",
             "失误": "sTurnovers", "犯规": "sFoulsPersonal"}
TEAM_STAT_MA = {"投篮": ("sFieldGoalsMade", "sFieldGoalsAttempted"),
                "三分": ("sThreePointersMade", "sThreePointersAttempted"),
                "罚球": ("sFreeThrowsMade", "sFreeThrowsAttempted")}


def _box_rows(side: list) -> list[dict]:
    if not side:
        return []
    head = (side[0] or {}).get("head") or []
    keys = [QQ_HEAD.get(h) for h in head]
    out = []
    for r in side[1:]:
        row = r.get("row") or []
        if not r.get("playerId"):
            continue
        rec = {"pid": str(r["playerId"]), "dorsal": row[0] if row else None, "cn": row[1] if len(row) > 1 else ""}
        rest = row[2:]
        for k, v in zip(keys[1:], rest):
            if k:
                rec[k] = v
        out.append(rec)
    return out


def _same_name(a: str, b: str) -> bool:
    a, b = (a or "").replace("-", "·"), (b or "").replace("-", "·")
    return bool(a and b) and (a == b or a in b or b in a or a.split("·")[-1] == b.split("·")[-1])


def _match_sina(qrows: list[dict], srows: list[dict]) -> dict[str, dict]:
    """playerId QQ -> fila de Sina: mismo dorsal (y nombre compatible si el dorsal se repite) o mismo nombre."""
    out, used = {}, set()
    by_d: dict[str, list] = {}
    for i, s in enumerate(srows):
        by_d.setdefault(str(s.get("dorsal") or "").strip(), []).append(i)
    for q in qrows:
        cand = [i for i in by_d.get(str(q.get("dorsal") or "").strip(), []) if i not in used]
        if len(cand) > 1:
            cand = [i for i in cand if _same_name(q["cn"], srows[i].get("name"))] or cand[:1]
        if not cand:
            cand = [i for i, s in enumerate(srows) if i not in used and _same_name(q["cn"], s.get("name"))][:1]
        if cand:
            used.add(cand[0])
            out[q["pid"]] = srows[cand[0]]
    return out


_RE_ASSIST = re.compile(r"收到(.+?)助攻")
_RE_BLOCK = re.compile(r"被(.+?)封盖")
_RE_STEAL = re.compile(r"被(.+?)抢断")
_RE_FOUL_ON = re.compile(r"对(.+?)(?:的)?(?:打手|个人|进攻|防守|技术|违体|恶意|投篮)?犯规")
_RE_SUB = re.compile(r"(.+?)上场，换下(.+)$")


def _quarter(e: dict) -> int:
    q = str(e.get("quarter") or (e.get("match") or {}).get("quarter") or "1").upper().lstrip("Q")
    return int(q) if q.isdigit() else 1


def _clock_s(v: Any) -> float:
    m = re.fullmatch(r"(\d+):(\d+)", str(v or ""))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else 0.0


def _chrono(ids: list[str], evs: dict) -> list[str]:
    """Orden real de los eventos: periodo y reloj (descendente); a igualdad, el orden del índice de QQ (el
    índice invertido casi siempre es cronológico, pero QQ intercala a veces eventos de otro periodo)."""
    pos = {i: n for n, i in enumerate(ids)}
    ok = [i for i in ids if isinstance(evs.get(i), dict)]
    return sorted(ok, key=lambda i: (_quarter(evs[i]), -_clock_s(evs[i].get("time") or evs[i].get("quarterTime")),
                                     pos[i]))


def _first_touch(block: list[dict], k: str) -> tuple[set, dict]:
    """Jugadores del equipo `k` que estaban en pista al empezar el bloque (periodo): los que actúan antes de
    entrar. Si salen más de 5 (falta algún cambio en el texto), los que salen sin haber entrado y, después,
    los que actúan antes. Devuelve (quinteto, {pno: "in" | "act" | "out"} del primer evento de cada uno)."""
    first: dict[str, str] = {}
    pos: dict[str, int] = {}
    for i, a in enumerate(block):
        n = str(a["pno"])
        if str(a["tno"]) == k and a["pno"] and n not in first:
            first[n] = a["subType"] if a["actionType"] == "substitution" and a["subType"] in ("in", "out") else "act"
            pos[n] = i
    want = {n for n, v in first.items() if v != "in"}
    if len(want) > 5:
        sure = sorted((n for n in want if first[n] == "out"), key=pos.get)
        rest = sorted((n for n in want if first[n] != "out"), key=pos.get)
        want = set((sure + rest)[:5])
    return want, first


def _period_starts(pbp: list[dict], tm: dict, qq_period: dict, period_start: dict,
                   opts: dict | None = None) -> tuple[list[dict], int]:
    """QQ no anota los cambios entre periodos. Quinteto con que empieza cada periodo (desde el 2.º), por equipo:
    los jugadores cuyo primer evento del periodo no es una entrada; si son menos de 5, se completa con los
    cinco en pista que da QQ en el primer evento del periodo (desde 2025-26) y, si no, con los que acabaron el
    periodo anterior. Si difiere del quinteto que se lleva, se insertan al inicio del periodo las salidas y
    entradas que faltan (qualifier "entre_periodos"). La lista de QQ sola no basta: a veces no aplica un cambio.
    Devuelve (pbp renumerado, nº de periodos-equipo corregidos)."""
    opts = opts or {}
    if not any(a["actionType"] == "substitution" for a in pbp):
        for a in pbp:
            a.pop("_on", None)
        return pbp, 0
    cur = {k: {n for n, p in tm[k]["pl"].items() if p.get("starter")} for k in ("1", "2")}

    def per_of(a):
        return a["period"] + (4 if a.get("periodType") == "OVERTIME" else 0)

    out: list[dict] = []
    n_fix = 0
    i = 0
    while i < len(pbp):
        per = per_of(pbp[i])
        j = i
        while j < len(pbp) and per_of(pbp[j]) == per:
            j += 1
        block = pbp[i:j]
        if per == 1:
            # titulares: los que actúan en el 1.er periodo antes de entrar; se completan con los de la fuente
            # (Sina; a veces marca mal el quinteto inicial) que no entran después
            for k in ("1", "2"):
                want, first1 = _first_touch(block, k)
                for n in sorted(cur[k] - want):
                    if len(want) < 5 and first1.get(n) != "in":
                        want.add(n)
                if len(want) == 5 and want != cur[k]:
                    cur[k] = want
                    n_fix += 1
                    for n, p in tm[k]["pl"].items():
                        p["starter"] = 1 if n in want else 0
        if per > 1:
            ins = []
            for k in ("1", "2"):
                want, first = _first_touch(block, k)
                if len(want) < 5:
                    for pool in ((qq_period.get(per) or {}).get(k) or set(), cur[k]):
                        for n in sorted(pool - want):
                            if len(want) < 5 and first.get(n) != "in":
                                want.add(n)
                if len(want) != 5 or want == cur[k]:
                    continue
                gt = period_start.get(per) or block[0]["gt"]
                base = {"period": block[0]["period"], "periodType": block[0].get("periodType"), "gt": gt,
                        "s1": block[0].get("s1"), "s2": block[0].get("s2"), "success": 0, "tno": int(k),
                        "actionType": "substitution", "qualifier": ["entre_periodos"]}
                ins += [{**base, "subType": "out", "pno": int(n)} for n in sorted(cur[k] - want)]
                ins += [{**base, "subType": "in", "pno": int(n)} for n in sorted(want - cur[k])]
                n_fix += 1                      # (el quinteto que se lleva se actualiza al recorrer el bloque)
            # tras el evento de inicio de periodo, si lo hay
            lead = 1 if block and block[0]["actionType"] == "period" else 0
            block = block[:lead] + ins + block[lead:]
        for a in block:
            k, n = str(a["tno"]), str(a["pno"])
            on = (a.get("_on") or {}).get(k)
            if a["actionType"] == "substitution" and a["tno"] and a["pno"]:
                if opts.get("descartar", True) and (a["subType"] == "in" and n in cur[k]
                                                    or a["subType"] == "out" and n not in cur[k]):
                    continue                    # cambio imposible con el quinteto que se lleva: se descarta
                (cur[k].add if a["subType"] == "in" else cur[k].discard)(n)
            elif opts.get("reparar", True) and a["pno"] and k in cur and n not in cur[k] and on and n in on \
                    and on != cur[k] \
                    and a["actionType"] not in ("period", "game", "timeout"):
                # actúa quien no está en pista y QQ sí lo tiene en pista: falta un cambio en el texto
                base = {kk: a.get(kk) for kk in ("period", "periodType", "gt", "s1", "s2")}
                for x in sorted(cur[k] - on):
                    out.append({**base, "actionType": "substitution", "subType": "out", "success": 0, "tno": int(k),
                                "pno": int(x), "qualifier": ["sin_anotar"]})
                for x in sorted(on - cur[k]):
                    out.append({**base, "actionType": "substitution", "subType": "in", "success": 0, "tno": int(k),
                                "pno": int(x), "qualifier": ["sin_anotar"]})
                cur[k] = set(on)
                n_fix += 1
            out.append(a)
        i = j
    renum = {}
    for a in out:
        a.pop("_on", None)
    for n, a in enumerate(out, 1):
        if "actionNumber" in a:
            renum[a["actionNumber"]] = n
        a["actionNumber"] = n
    for a in out:
        if a.get("previousAction") is not None:
            a["previousAction"] = renum.get(a["previousAction"])
    return out, n_fix


def to_fls(g: dict, jugadores: dict | None = None, cfg: dict | None = None) -> dict:
    """Partido del bruto (QQ + Sina) -> estructura del data.json de FIBA LiveStats (tm, pbp)."""
    cfg = cfg or {}
    over = cfg.get("nombres_latinos") or {}
    jugadores = jugadores or {}
    cal, st = g.get("cal") or {}, g.get("stat") or {}
    ti = st.get("teamInfo") or {}
    ids = {"1": str(ti.get("leftId") or cal.get("leftId") or ""), "2": str(ti.get("rightId") or cal.get("rightId") or "")}
    side_of = {v: k for k, v in ids.items() if v}
    notes: list[str] = []
    ps = st.get("playerStats") or {}
    qrows = {"1": _box_rows(ps.get("left") or []), "2": _box_rows(ps.get("right") or [])}
    sina = sina_box((g.get("sina") or {}).get("html"))
    sina_side: dict[str, dict] = {}
    if len(sina) == 2:
        score = {k: to_float(ti.get(("left" if k == "1" else "right") + "Goal")) for k in ("1", "2")}
        pts = [sum(p.get("pts") or 0 for p in s["jugadores"]) for s in sina]
        if (pts[0], pts[1]) == (score["1"], score["2"]) or score["1"] is None:
            sina_side = {"1": sina[0], "2": sina[1]}
        elif (pts[1], pts[0]) == (score["1"], score["2"]):
            sina_side = {"1": sina[1], "2": sina[0]}      # Sina pone a veces primero al visitante
        else:
            # puntos que no cuadran (alguna fila de Sina sin puntos): por el nombre corto del equipo
            names_qq = {k: str(ti.get(("left" if k == "1" else "right") + "Name") or "") for k in ("1", "2")}
            for k in ("1", "2"):
                hit = [s_ for s_ in sina if s_.get("equipo") and s_["equipo"] in names_qq[k]]
                if len(hit) == 1:
                    sina_side[k] = hit[0]
            if len(sina_side) != 2 or sina_side["1"] is sina_side["2"]:
                sina_side = {}
            notes.append(f"Sina: puntos {pts[0]:g}-{pts[1]:g} distintos del marcador QQ"
                         + ("; casado por nombre de equipo" if sina_side else ""))
    elif g.get("sina") is not None:
        notes.append("Sina: boxscore ilegible")
    tm: dict[str, dict] = {}
    pno: dict[str, tuple[str, str]] = {}
    names: dict[str, dict[str, str]] = {"1": {}, "2": {}}
    split_ok = {"1": False, "2": False}
    for k, lr in (("1", "left"), ("2", "right")):
        cn_team = ti.get(lr + "Name") or cal.get(lr + "Name")
        t = {"name": equipo_latino(ti.get(lr + "EnName"), cn_team), "nameLocal": cn_team,
             "nameFull": ti.get(lr + "FullCnName"), "code": None, "teamId": ids[k],
             "score": to_float(ti.get(lr + "Goal") or cal.get(lr + "Goal")), "pl": {}, "shot": []}
        ss = sina_side.get(k)
        smap = _match_sina(qrows[k], ss["jugadores"]) if ss else {}
        if ss and ss.get("entrenador"):
            c = entrenador_latino(ss["entrenador"], over)
            t["coach"] = c["name"]
            t["coachDetails"] = {"firstName": c["first"], "familyName": c["family"], "nameLocal": ss["entrenador"],
                                 "nameType": c["tipo"]}
        ok = bool(ss) and all(p["pid"] in smap for p in qrows[k] if (to_float(p.get("reb")) or 0) > 0)
        for i, q in enumerate(qrows[k], 1):
            n = str(i)
            pno[q["pid"]] = (k, n)
            info = jugadores.get(q["pid"]) or {}
            nm = nombre_latino(info.get("cnName") or q["cn"], info.get("enName"), over)
            line = {"personId": q["pid"], "firstName": nm["first"], "familyName": nm["family"], "name": nm["name"],
                    "nameLocal": info.get("cnName") or q["cn"], "nameShort": q["cn"], "nameType": nm["tipo"],
                    "shirtNumber": q.get("dorsal"), "playingPosition": info.get("position") or None,
                    "height": to_float(str(info.get("height") or "").replace("cm", "")),
                    "dateOfBirth": info.get("birthDate") or None, "sMinutes": _mmss(q.get("min"))}
            for a, b in (("pts", "sPoints"), ("reb", "sReboundsTotal"), ("ast", "sAssists"), ("stl", "sSteals"),
                         ("blk", "sBlocks"), ("tov", "sTurnovers"), ("pf", "sFoulsPersonal")):
                if to_float(q.get(a)) is not None:
                    line[b] = to_float(q.get(a))
            pm = to_float(str(q.get("pm") or "").replace("+", ""))
            if pm is not None:
                line["sPlusMinusPoints"] = pm
            for a, (bm, ba) in (("fg", ("sFieldGoalsMade", "sFieldGoalsAttempted")),
                                ("fg3", ("sThreePointersMade", "sThreePointersAttempted")),
                                ("ft", ("sFreeThrowsMade", "sFreeThrowsAttempted"))):
                m_, a_ = _ma(q.get(a))
                if m_ is not None:
                    line[bm], line[ba] = m_, a_
            s = smap.get(q["pid"])
            if s is not None:
                line["starter"] = 1 if s.get("starter") else 0
                if s.get("oreb") is not None and s.get("dreb") is not None and \
                        s["oreb"] + s["dreb"] == (line.get("sReboundsTotal") or 0):
                    line["sReboundsOffensive"], line["sReboundsDefensive"] = s["oreb"], s["dreb"]
                elif (line.get("sReboundsTotal") or 0) > 0:
                    ok = False
                if s.get("oreb") is not None and s.get("dreb") is not None:
                    line["_sina_reb"] = (s["oreb"], s["dreb"])
                line["sinaId"] = s.get("sina_id")
            t["pl"][n] = line
            names[k][q["cn"]] = q["pid"]
            if info.get("cnName"):
                names[k].setdefault(info["cnName"], q["pid"])
        split_ok[k] = ok
        for row in st.get("teamStats") or []:
            lab = row.get("text")
            v = row.get("leftVal" if k == "1" else "rightVal")
            if lab in TEAM_STAT and to_float(v) is not None:
                t["tot_" + TEAM_STAT[lab]] = to_float(v)
            if lab in TEAM_STAT_MA:
                m_, a_ = _ma(row.get("leftExt" if k == "1" else "rightExt"))
                if m_ is not None:
                    t["tot_" + TEAM_STAT_MA[lab][0]], t["tot_" + TEAM_STAT_MA[lab][1]] = m_, a_
        if not ok:
            for p in t["pl"].values():
                p.pop("sReboundsOffensive", None)
                p.pop("sReboundsDefensive", None)
        tm[k] = t

    # ------------------------------------------------------------------ jugada a jugada
    evs = g.get("pbp") or {}
    order = _chrono(list(reversed(g.get("pbp_index") or [])), evs)
    pbp: list[dict] = []
    last_made: dict[str, int] = {}
    drawn: dict[str, int] = {}
    blocked: dict[str, int] = {}
    first_five: dict[str, list] = {}

    def other(k):
        return "2" if k == "1" else "1"

    def who(name: str, k: str | None) -> str | None:
        name = (name or "").strip()
        if not name or not k:
            return None
        if name in names[k]:
            return names[k][name]
        hits = [pid for n, pid in names[k].items() if _same_name(n, name)]
        return hits[0] if len(hits) == 1 else None

    def add(at, k, pid, e, **kw):
        n = pno.get(pid, (k, "0"))[1] if pid else "0"
        a = {"actionNumber": len(pbp) + 1, "actionType": at, "subType": kw.pop("subType", ""),
             "success": kw.pop("success", 0), "tno": int(k) if k else 0, "pno": int(n), **e, **kw}
        if cur_on:
            a["_on"] = cur_on
        pbp.append(a)
        return a

    def on_court(e: dict) -> dict[str, set]:
        """Cinco en pista que da QQ en el evento (desde 2025-26), sólo si son 5 jugadores del boxscore."""
        pl = (e.get("match") or {}).get("playerList") or {}
        out = {}
        for k, lr in (("1", "left"), ("2", "right")):
            ids_ = {str(x) for x in pl.get(lr) or []}
            if len(ids_) == 5 and all(pno.get(x, ("",))[0] == k for x in ids_):
                out[k] = ids_
        return out

    for eid in order:                                         # quinteto inicial = el primero que da QQ
        e = evs.get(eid)
        if isinstance(e, dict):
            for k, v in on_court(e).items():
                first_five.setdefault(k, sorted(v))
        if len(first_five) == 2:
            break
    cur = {k: set(v) for k, v in first_five.items()}
    period_start: dict[int, Any] = {}
    qq_period: dict[int, dict] = {}            # cinco en pista que da QQ en el primer evento de cada periodo
    cur_on: dict = {}

    for eid in order:
        e = evs.get(eid)
        if not isinstance(e, dict):
            continue
        b = e.get("broadcast") or {}
        at = str(b.get("actionType") or "")
        txt = str(e.get("content") or "")
        tid = str((b.get("team") or {}).get("id") or e.get("teamId") or "")
        k = side_of.get(tid)
        pid = str((b.get("player") or {}).get("id") or "") or None
        rid = str((b.get("relatedPlayer") or {}).get("id") or "") or None
        if pid and pid in pno and k is None:
            k = pno[pid][0]
        per = _quarter(e)
        if at == "13":
            period_start[per] = e.get("time") or e.get("quarterTime")
        cur_on = {k_: {pno[x][1] for x in v} for k_, v in on_court(e).items()}
        base = {"period": per - 4 if per > 4 else per, "periodType": "OVERTIME" if per > 4 else "REGULAR",
                "gt": e.get("time") or e.get("quarterTime") or "00:00", "s1": e.get("leftGoal"),
                "s2": e.get("rightGoal"), "qqId": eid}
        if at not in ("9", "13", "14", "15") and per not in qq_period:
            qq_period[per] = cur_on
        if at in ("1", "2") and k:
            v = "3pt" if "三分" in txt else "2pt"
            made = at == "1"
            sh = add(v, k, pid, base, success=1 if made else 0)
            if made:
                last_made[k] = sh["actionNumber"]
                ma = _RE_ASSIST.search(txt)
                ast = rid if rid in pno and pno[rid][0] == k else (who(ma.group(1), k) if ma else None)
                if ma and ast:
                    add("assist", k, ast, base, previousAction=sh["actionNumber"])
            else:
                mb = _RE_BLOCK.search(txt)
                if mb:
                    blk = who(mb.group(1), other(k))
                    if blk:
                        add("block", other(k), blk, base)
                        if pid:
                            blocked[pid] = blocked.get(pid, 0) + 1
        elif at in ("6", "7") and k:
            made = at == "6"
            ft = add("freethrow", k, pid, base, success=1 if made else 0)
            if made:
                last_made[k] = ft["actionNumber"]
        elif at == "3" and k:
            sub = "offensive" if "进攻篮板" in txt else "defensive"
            a = add("rebound", k, pid if pid in pno else None, base, subType=sub)
            if a["pno"] == 0:
                a["qualifier"] = ["team"]
        elif at == "4" and k:
            add("turnover", k, pid if pid in pno else None, base)
            ms = _RE_STEAL.search(txt)
            if ms:
                stl = who(ms.group(1), other(k))
                if stl:
                    add("steal", other(k), stl, base)
        elif at == "5" and k:
            add("foul", k, pid if pid in pno else None, base,
                subType="technical" if "技术" in txt else ("offensive" if "进攻犯规" in txt else "personal"))
            mf = _RE_FOUL_ON.search(txt)
            if mf:
                victim = who(mf.group(1), other(k))
                if victim:
                    add("foulon", other(k), victim, base)
                    drawn[victim] = drawn.get(victim, 0) + 1
        elif at == "9" and k:
            m = _RE_SUB.search(txt.split("，", 1)[-1] if "换人，" in txt else txt)
            p_in = who(m.group(1), k) if m else None
            p_out = who(m.group(2), k) if m else None
            p_in = p_in or (rid if rid in pno else None)     # QQ: player = sale, relatedPlayer = entra
            p_out = p_out or (pid if pid in pno else None)
            if p_out:
                add("substitution", k, p_out, base, subType="out")
                cur.get(k, set()).discard(p_out)
            if p_in:
                add("substitution", k, p_in, base, subType="in")
                if k in cur:
                    cur[k].add(p_in)
        elif at == "10":
            add("timeout", k, None, base)
        elif at == "11" and k:
            add("jumpball", k, pid if pid in pno else None, base)
        elif at in ("13", "14"):
            add("period", None, None, base, subType="start" if at == "13" else "end")
        elif at == "15":
            add("game", None, None, base, subType="end")
    pbp, n_sync = _period_starts(pbp, tm, qq_period, period_start,
                                 {"descartar": cfg.get("descartar_cambios_imposibles", True),
                                  "reparar": cfg.get("reparar_con_quinteto_qq", True)})
    # rebotes OF/DEF: Sina si cuadra con el total de QQ; si no, el jugada a jugada (también tipado OF/DEF) si cuadra
    reb_pbp: dict[str, list] = {}
    team_reb: dict[str, list] = {"1": [0, 0], "2": [0, 0]}
    for a in pbp:
        if a["actionType"] == "rebound" and a["tno"]:
            i = 0 if a["subType"] == "offensive" else 1
            if a["pno"]:
                pid_ = tm[str(a["tno"])]["pl"][str(a["pno"])]["personId"]
                reb_pbp.setdefault(pid_, [0, 0])[i] += 1
            else:
                team_reb[str(a["tno"])][i] += 1
    for k in ("1", "2"):
        t = tm[k]
        if not split_ok[k] and pbp:
            good = True
            for p in t["pl"].values():
                o, d_ = reb_pbp.get(p["personId"], [0, 0])
                if o + d_ != (p.get("sReboundsTotal") or 0):
                    good = False
                    break
            if good:
                for p in t["pl"].values():
                    p["sReboundsOffensive"], p["sReboundsDefensive"] = reb_pbp.get(p["personId"], [0, 0])
                split_ok[k] = True
                notes.append(f"lado {k}: rebotes OF/DEF del jugada a jugada (Sina no cuadra)")
        if not split_ok[k] and all("_sina_reb" in p or not (p.get("sReboundsTotal") or 0) for p in t["pl"].values()):
            # QQ y Sina difieren en ±1-2 rebotes de algún jugador: total de QQ, ofensivos de Sina (acotados)
            n_adj = 0
            for p in t["pl"].values():
                tot = p.get("sReboundsTotal") or 0
                o, d_ = p.get("_sina_reb") or (0, 0)
                n_adj += (o + d_) != tot
                p["sReboundsOffensive"] = min(o, tot)
                p["sReboundsDefensive"] = tot - p["sReboundsOffensive"]
            split_ok[k] = True
            notes.append(f"lado {k}: rebotes OF/DEF de Sina ajustados al total de QQ en {n_adj} jugadores")
        if split_ok[k]:
            pl_or = sum(p.get("sReboundsOffensive") or 0 for p in t["pl"].values())
            pl_dr = sum(p.get("sReboundsDefensive") or 0 for p in t["pl"].values())
            tr = (t.get("tot_sReboundsTotal") or 0) - pl_or - pl_dr
            if tr == 0:
                t["tot_sReboundsOffensive"], t["tot_sReboundsDefensive"] = pl_or, pl_dr
            elif pbp and sum(team_reb[k]) == tr:          # rebotes de equipo del jugada a jugada
                t["tot_sReboundsOffensive"] = pl_or + team_reb[k][0]
                t["tot_sReboundsDefensive"] = pl_dr + team_reb[k][1]
        else:
            notes.append(f"lado {k}: sin desglose de rebotes OF/DEF")
    for pid, (k, n) in pno.items():
        p = tm[k]["pl"][n]
        p.pop("_sina_reb", None)
        if pbp:
            p["sFoulsOn"] = drawn.get(pid, 0)
            p["sBlocksReceived"] = blocked.get(pid, 0)
        if "starter" not in p and first_five.get(k):
            p["starter"] = 1 if pid in first_five[k] else 0
    if n_sync:
        notes.append(f"{n_sync} cambios de quinteto sin anotar en QQ, reconstruidos")
    pbp.reverse()                       # FIBA LiveStats: orden descendente de actionNumber
    final = str(cal.get("matchPeriod") or "2") == "2"
    return {"tm": tm, "pbp": pbp, "status": "complete" if final else "live", "matchDate": cal.get("startTime"),
            "period": None, "notas": notes, "rebotes_desglosados": split_ok}


# =============================================================================================== adaptador
def _months(start_year: int, until: str) -> list[tuple[str, str]]:
    """Meses de la temporada (septiembre del año de inicio a julio siguiente) hasta `until` (AAAA-MM-DD)."""
    out = []
    y, m = start_year, 9
    while (y, m) <= (start_year + 1, 7):
        d1 = dt.date(y, m, 1)
        if d1.isoformat() > until:
            break
        nxt = dt.date(y + (m == 12), m % 12 + 1, 1)
        out.append((d1.isoformat(), (nxt - dt.timedelta(days=1)).isoformat()))
        y, m = nxt.year, nxt.month
    return out


def _compact_event(e: dict) -> dict:
    """Evento de QQ sin imágenes, textos de patrocinio ni fichas completas: lo que usa `to_fls`."""
    b = e.get("broadcast") or {}

    def pl(x):
        return {k: x.get(k) for k in ("id", "name", "teamId", "jerseyNum")} if isinstance(x, dict) else None

    m = e.get("match") or {}
    lst = m.get("playerList") or {}
    return {"content": e.get("content"), "time": e.get("time"), "quarter": e.get("quarter"),
            "quarterTime": e.get("quarterTime"), "teamId": e.get("teamId"), "leftGoal": e.get("leftGoal"),
            "rightGoal": e.get("rightGoal"), "version": e.get("version"), "ctype": e.get("ctype"),
            "broadcast": {"actionType": b.get("actionType"), "summary": b.get("summary"), "player": pl(b.get("player")),
                          "relatedPlayer": pl(b.get("relatedPlayer")),
                          "team": {"id": (b.get("team") or {}).get("id")} if b.get("team") else None},
            "match": {"quarter": m.get("quarter"),
                      "playerList": {s: [p.get("id") for p in lst.get(s) or [] if isinstance(p, dict)]
                                     for s in ("left", "right")} if lst else None}}


class CBAAdapter(FibaLiveStatsAdapter):
    """CBA: calendario, boxscore y jugada a jugada de QQ + rebotes OF/DEF, titulares y entrenador de Sina.

    Config: `temporadas.<t>.sina_liga` (qleagueid de Sina), `fecha_corte` (global o por temporada, "AAAA-MM-DD":
    sólo partidos hasta ese día), `nombres_latinos` ({"中文名": "Nombre latino"}, jugadores y entrenadores),
    `lote_eventos` (ids por petición de textLive/detail, 400 por defecto)."""
    name = "cba"
    version = "1.0"

    def _json(self, http: HttpClient, url: str) -> Any:
        return http.get(url, headers=HEADERS).json()

    def _sina_text(self, http: HttpClient, url: str) -> str:
        resp = http.get(url)
        return resp.content.decode("gbk", errors="replace")

    def _calendar(self, http: HttpClient, start_year: int, corte: str) -> dict[str, dict]:
        cal: dict[str, dict] = {}
        for d1, d2 in _months(start_year, corte):
            try:
                r = self._json(http, LIST_URL.format(d1=d1, d2=d2))
            except (FetchError, ValueError) as exc:
                self.soft_fail(f"calendario {d1[:7]}: {exc}")
                continue
            for day in ((r or {}).get("data") or {}).values():
                for m in day or []:
                    mid = str(m.get("mid") or "").split(":")[-1]
                    if not mid or str(m.get("competitionId") or COMP) != COMP:
                        continue
                    if str(m.get("startTime") or "")[:10] > corte:
                        continue
                    cal[mid] = {k: m.get(k) for k in ("mid", "matchDesc", "startTime", "matchPeriod", "leftId",
                                                      "leftName", "leftGoal", "rightId", "rightName", "rightGoal")}
        return cal

    def _pbp(self, http: HttpClient, mid: str) -> tuple[list, dict]:
        idx = self._json(http, TL_INDEX_URL.format(mid=mid))
        ids = idx[1] if isinstance(idx, list) and len(idx) > 1 and isinstance(idx[1], list) else []
        evs: dict[str, dict] = {}
        lote = int(self.cfg.get("lote_eventos", 400))
        for i in range(0, len(ids), lote):
            d = self._json(http, TL_DETAIL_URL.format(mid=mid, ids=",".join(ids[i:i + lote])))
            if isinstance(d, list) and len(d) > 1 and isinstance(d[1], dict):
                evs.update({k: _compact_event(v) for k, v in d[1].items() if isinstance(v, dict)})
        return [i for i in ids if i in evs], evs

    def fetch(self, season: str, http: HttpClient, previous_payload: Any | None = None) -> Any:
        sc = self.season_cfg(season)
        today = dt.date.today().isoformat()
        corte = min(str(sc.get("fecha_corte") or self.cfg.get("fecha_corte") or "9999-12-31"), today)
        prev = previous_payload if isinstance(previous_payload, dict) else {}
        prev_games, prev_jug = prev.get("games") or {}, prev.get("jugadores") or {}
        cal = self._calendar(http, sc["start_year"], corte)
        fases, fechas = {}, {}
        for mid, m in cal.items():
            ph = fase_de(m.get("matchDesc"))
            if ph and str(m.get("matchPeriod")) == "2":
                fases[mid], fechas[mid] = ph, m.get("startTime")
        meses = sc.get("meses")         # pruebas: sólo esos meses ("AAAA-MM")
        if meses:
            fases = {k: v for k, v in fases.items() if str(fechas[k])[:7] in meses}
            fechas = {k: fechas[k] for k in fases}
        if not fases:
            raise NoDataYet(f"cba {season}: aún no hay partidos terminados")
        todo = sorted((m for m in fases if m not in prev_games), key=lambda i: fechas[i] or "")
        sina_list: list[dict] = []
        if todo and sc.get("sina_liga"):
            try:
                sina_list = sina_schedule(self._sina_text(http, SINA_LIST_URL.format(liga=sc["sina_liga"])))
            except FetchError as exc:
                self.soft_fail(f"Sina calendario: {exc}")
        sina_idx = {(s["fecha"], s["pts_local"], s["pts_visitante"]): s for s in sina_list}
        new: dict[str, dict] = {}
        jug_new: dict[str, dict] = {}
        seen_j: set[str] = set()
        n_new = 0
        block = int(self.cfg.get("partidos_por_paquete", 150))
        for mid in todo:
            m = cal[mid]
            try:
                stat = (self._json(http, STAT_URL.format(mid=mid)) or {}).get("data") or {}
            except (FetchError, ValueError) as exc:
                self.soft_fail(f"{mid} matchStat: {exc}")
                continue
            if not (stat.get("playerStats") or {}).get("left"):
                self.soft_fail(f"{mid}: matchStat sin boxscore")
                continue
            g: dict[str, Any] = {"cal": m, "stat": {k: stat.get(k) for k in ("teamInfo", "playerStats", "teamStats",
                                                                             "periodGoals")}}
            try:
                g["pbp_index"], g["pbp"] = self._pbp(http, mid)
            except (FetchError, ValueError) as exc:
                self.soft_fail(f"{mid} textLive: {exc}")
                g["pbp_index"], g["pbp"] = [], {}
            key = (str(m.get("startTime") or "")[:10], int(to_float(m.get("leftGoal")) or -1),
                   int(to_float(m.get("rightGoal")) or -1))
            s = sina_idx.get(key)
            if s:
                try:
                    g["sina"] = {"sid": s["sid"], "html": sina_slice(self._sina_text(http, SINA_GAME_URL.format(sid=s["sid"])))}
                except FetchError as exc:
                    self.soft_fail(f"{mid} Sina {s['sid']}: {exc}")
                    g["sina"] = None
            else:
                g["sina"] = None
                if sc.get("sina_liga"):
                    self.soft_fail(f"{mid}: sin partido de Sina con fecha y marcador {key}")
            for side in ("left", "right"):
                for r in ((stat.get("playerStats") or {}).get(side) or [])[1:]:
                    pid = str(r.get("playerId") or "")
                    if pid and pid not in prev_jug and pid not in seen_j:
                        seen_j.add(pid)
                        try:
                            info = (self._json(http, PLAYER_URL.format(pid=pid)) or {}).get("data") or {}
                        except (FetchError, ValueError) as exc:
                            self.soft_fail(f"jugador {pid}: {exc}")
                            continue
                        jug_new[pid] = {k: info.get(k) for k in ("cnName", "enName", "birthDate", "height",
                                                                  "weight", "position", "jerseyNum")}
            new[mid] = g
            n_new += 1
            if len(new) >= block:
                self.save_partial(season, {"claves_incrementales": ["games", "fechas", "jugadores"],
                                           "fases": fases, "fechas": fechas, "games": new, "jugadores": jug_new})
                new, jug_new = {}, {}
        return {"incremental": True, "claves_incrementales": ["games", "fechas", "jugadores"], "fases": fases,
                "fechas": fechas, "games": new, "jugadores": jug_new, "reused_games": len(fases) - len(todo),
                "partidos_nuevos": n_new}

    def parse(self, payload: Any, season: str) -> dict[str, ParsedLeague]:
        return parse_payload(payload, self.cfg)


def season_docs(payload: dict, cfg: dict) -> dict[str, dict]:
    """{mid: data.json traducido} de los partidos de liga regular y playoffs del bruto."""
    fases = payload.get("fases") or {}
    jug = payload.get("jugadores") or {}
    return {mid: to_fls(g, jug, cfg) for mid, g in (payload.get("games") or {}).items()
            if isinstance(g, dict) and fases.get(mid) in ("regular", "playoffs")}


def team_names(docs: dict[str, dict]) -> dict[str, str]:
    """team_id -> nombre latino más reciente de la temporada (los patrocinios cambian el nombre chino)."""
    out: dict[str, tuple[str, str]] = {}
    for d in docs.values():
        for k in ("1", "2"):
            t = d["tm"][k]
            key = str(d.get("matchDate") or "")
            if t["teamId"] not in out or key >= out[t["teamId"]][0]:
                out[t["teamId"]] = (key, t["name"])
    return {k: v[1] for k, v in out.items()}


def parse_payload(payload: dict, cfg: dict) -> dict[str, ParsedLeague]:
    fases = payload.get("fases") or {}
    docs = season_docs(payload, cfg)
    names = team_names(docs)
    games, notes = [], []
    n_split = 0
    for mid in sorted(docs, key=lambda m: (str(docs[m].get("matchDate") or ""), m)):
        d = docs[mid]
        t1, t2 = d["tm"]["1"]["teamId"], d["tm"]["2"]["teamId"]
        g = parse_fiba_game(mid, d, fases[mid], ((t1, names.get(t1)), (t2, names.get(t2))))
        g["date"] = str(d.get("matchDate") or "")[:10] or None
        for side, k in zip(g["teams"], ("1", "2")):
            side["code"] = d["tm"][k].get("nameLocal")
            pls = {str(p.get("personId")): p for p in d["tm"][k]["pl"].values()}
            for line in side["players"]:
                p = pls.get(line["player_id"]) or {}
                line["name"] = p.get("name") or line.get("name")
                if p.get("dateOfBirth"):
                    line["fecha_nacimiento"] = p["dateOfBirth"]
                if p.get("nameType") in ("chino", "minoria"):     # nombre chino (pinyin) o de minoría → China
                    line["nacionalidad"] = "CN"
                if p.get("height"):
                    line["altura_cm"] = p["height"]
        n_split += all(d.get("rebotes_desglosados", {}).values())
        games.append(g)
    if not games:
        raise AdapterError("cba: el bruto no contiene partidos de liga regular ni playoffs")
    notes.append(f"{len(games)} partidos QQ; {n_split} con rebotes OF/DEF de Sina en los dos equipos; "
                 f"{sum(1 for d in docs.values() if d['pbp'])} con jugada a jugada")
    return aggregate_by_phase(games, notes)
