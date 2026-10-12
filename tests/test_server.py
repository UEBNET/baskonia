from __future__ import annotations

import json
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from bbstats import server


@pytest.fixture
def srv(monkeypatch):
    def fake_ejecutar(ligas=None, temporada=None, config=None, progreso=None, **kw):
        progreso("[acb] descargando...")
        return {"temporada": temporada or "2025-26", "ligas": [{"liga": l, "estado": "ok"} for l in ligas or ["acb"]]}

    monkeypatch.setattr(server.api, "ejecutar", fake_ejecutar)
    monkeypatch.setenv("BBSTATS_TOKEN", "secreto")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(None))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    server._JOBS.clear()


def _call(url, data=None, token="secreto"):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with opener.open(req, timeout=5) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def test_ejecutar_job_flow(srv):
    code, body = _call(f"{srv}/api/ejecutar", {"ligas": ["acb", "nba"]})
    assert code == 202
    for _ in range(50):
        code, job = _call(f"{srv}/api/trabajo/{body['job_id']}")
        if job["estado"] != "en_curso":
            break
        time.sleep(0.05)
    assert job["estado"] == "terminado"
    assert [l["liga"] for l in job["informe"]["ligas"]] == ["acb", "nba"]
    assert job["progreso"] == ["[acb] descargando..."]


def test_auth_and_dictionary(srv):
    assert _call(f"{srv}/api/diccionario", token="malo")[0] == 401
    code, d = _call(f"{srv}/api/diccionario")
    assert code == 200 and len(d) > 300 and d[0]["columna"] == "liga"
