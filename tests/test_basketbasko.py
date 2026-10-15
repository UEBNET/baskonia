"""Extractor de la intranet de Basket Basko con una API simulada (mismas rutas y formato que la real)."""
from __future__ import annotations

import json

import pytest

from basketbasko.client import AuthError, BasketBaskoClient
from basketbasko.extract import extraer, find_teams, leer_bruto
from basketbasko.transform import procesar
from bbstats.http import HttpClient

ESB = "https://esb.test/esf/1/k"
ST = "https://stats.test/v1"
T1, T2, RIV = "team-1", "team-2", "team-rival"


def _stats(acc_pts, name):
    return {"accumulated": {"pts": acc_pts, "t2m": 10, "t2a": 20}, "computed": {"pir": acc_pts / 2},
            "advanced": {"offRtg": 101.5}, "name": name}


def team_payload(uuid, name, opp):
    return {"header": {"team": {"uuid": uuid, "name": name}, "competitions": [{"name": "Junior Masc."}]},
            "season": {"totals": _stats(300, None), "averages": _stats(60, None)},
            "games": [{"matchCallUuid": f"m-{uuid}-1", "opponent": {"uuid": opp, "name": "Rival"},
                       "teamPoints": 70, "opponentPoints": 60, "home": True, **_stats(70, None)},
                      {"matchCallUuid": f"m-{uuid}-2", "opponent": {"uuid": opp, "name": "Rival"},
                       "teamPoints": 55, "opponentPoints": 65, "home": False, **_stats(55, None)}],
            "roster": [{"uuid": f"p1-{uuid}", "name": "Ane", "dorsal": 7,
                        "totals": _stats(100, None), "averages": _stats(20, None)},
                       {"uuid": f"p2-{uuid}", "name": "Iker", "dorsal": 12,
                        "totals": _stats(50, None), "averages": _stats(10, None)}]}


class Resp:
    def __init__(self, url, status, body, headers=None):
        self.url, self.status_code, self._b = url, status, body
        self.ok = 200 <= status < 400
        self.headers = headers or {}
        self.text = json.dumps(body)

    def json(self):
        return self._b


class FakeApi(HttpClient):
    def __init__(self, expire_after=None):
        super().__init__(delay_s=0)
        self.calls, self.logins, self.expire_after = [], 0, expire_after

    def request(self, method, url, params=None, headers=None, data=None, json_body=None, ok_status=()):
        self.calls.append((method, url))
        if url == f"{ESB}/public/club/login":
            if json_body != {"username": "club", "password": "pw"}:
                return Resp(url, 200, {"result": "ERROR", "message": "ERRORCODEx0001"})
            self.logins += 1
            return Resp(url, 200, {"name": "Club Test"}, {"authorization": f"Bearer tok{self.logins}"})
        auth = self.session.headers.get("Authorization")
        if self.expire_after is not None and len(self.calls) == self.expire_after:
            auth = None   # simula caducidad del token
        if not auth:
            return Resp(url, 200, {"result": "ERROR", "errorCode": None, "message": "ERRORCODEx0004"})
        routes = {
            f"{ESB}/auth/my-club": {"name": "Club Test"},
            f"{ESB}/auth/my-teams": [{"teamUuid": T1, "teamName": "Junior A", "category": {"name": "Junior"}},
                                     {"teamUuid": T2, "teamName": "Cadete A", "category": {"name": "Cadete"}}],
            f"{ST}/esf/teams/{T1}/stats": team_payload(T1, "Junior A", RIV),
            f"{ST}/esf/teams/{T2}/stats": team_payload(T2, "Cadete A", RIV),
            f"{ST}/esf/teams/{RIV}/stats": team_payload(RIV, "Rival", T1),
        }
        if url in routes:
            return Resp(url, 200, routes[url])
        if "/players/" in url:
            return Resp(url, 200, {"season": {"totals": {"advanced": {"usgPer": 22.0}}}})
        if "/matches/" in url:
            return Resp(url, 200, {"home": {"players": [{"uuid": "p1", "name": "Ane", **_stats(18, "Ane")}]}})
        return Resp(url, 404, {})


def cfg(tmp_path, **kw):
    return {"url_esb": ESB, "url_stats": ST, "federacion": "esf", "pausa_s": 0, "max_peticiones": 500,
            "directorio_datos": str(tmp_path), "incluir_jugadores": True, "incluir_partidos": True,
            "incluir_rivales": False, **kw}


def test_login_incorrecto(tmp_path):
    c = BasketBaskoClient(cfg(tmp_path), "club", "mal", http=FakeApi())
    with pytest.raises(AuthError):
        c.login()


def test_extraccion_completa_y_procesado(tmp_path):
    api = FakeApi()
    c = BasketBaskoClient(cfg(tmp_path), "club", "pw", http=api)
    raw = extraer(c, cfg(tmp_path), progreso=lambda *_: None)
    bruto = leer_bruto(raw)
    assert set(bruto["equipos"]) == {T1, T2}            # sin rivales por defecto
    assert len(bruto["jugadores"]) == 4 and len(bruto["partidos"]) == 4
    res = procesar(bruto, tmp_path / "processed")
    assert res["club"] == {"equipos": 2, "partidos": 4, "ganados": 2, "jugadores": 4}
    t1 = next(e for e in res["equipos"] if e["equipo"] == "Junior A")
    assert t1["maximos_anotadores"][0] == {"jugador": "Ane", "valor": 20.0}
    assert t1["pts_favor_pp"] == 62.5
    for f in ("equipos.csv", "jugadores.csv", "partidos.csv", "boxscores.csv", "resumen.json",
              "historico.csv", "dashboard.html"):
        assert (tmp_path / "processed" / f).exists()
    html = (tmp_path / "processed" / "dashboard.html").read_text()
    assert "/*__DATA__*/null" not in html and "Junior A" in html
    # Segunda ejecución: los partidos ya jugados salen de la caché, no se piden otra vez
    api.calls.clear()
    extraer(BasketBaskoClient(cfg(tmp_path), "club", "pw", http=api), cfg(tmp_path), progreso=lambda *_: None)
    assert not any("/matches/" in u for _, u in api.calls)


def test_rivales_y_relogin(tmp_path):
    api = FakeApi(expire_after=4)
    c = BasketBaskoClient(cfg(tmp_path, incluir_rivales=True), "club", "pw", http=api)
    bruto = leer_bruto(extraer(c, c.cfg, progreso=lambda *_: None))
    assert RIV in bruto["equipos"] and bruto["equipos"][RIV]["propio"] is False
    assert api.logins >= 2 and not bruto["meta"]["errores"]


def test_limite_de_peticiones(tmp_path):
    c = BasketBaskoClient(cfg(tmp_path, max_peticiones=5), "club", "pw", http=FakeApi())
    bruto = leer_bruto(extraer(c, c.cfg, progreso=lambda *_: None))
    assert any("Límite" in e for e in bruto["meta"]["errores"])


def test_find_teams_anidado():
    data = {"result": "OK", "data": {"seasons": [{"teams": [{"uuid": "a", "name": "X", "category": "Mini"}]}]}}
    assert find_teams(data) == [{"uuid": "a", "nombre": "X", "categoria": "Mini", "competicion": None}]
