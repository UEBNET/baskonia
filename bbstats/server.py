"""Mini API HTTP (sólo librería estándar) para conectar un botón "EJECUTAR" de un Artifact / web.

    python -m bbstats servidor --puerto 8765

Endpoints (JSON, con CORS):
    POST /api/ejecutar      {"ligas": ["acb"], "temporada": "2025-26"}  -> {"job_id": ...}
    POST /api/reprocesar    {"ligas": [...], "temporada": "..."}       -> {"job_id": ...}
    GET  /api/trabajo/<id>  -> {"estado": "en_curso|terminado|error", "progreso": [...], "informe": {...}}
    GET  /api/estado        -> estado de ligas y último informe
    GET  /api/datos?liga=acb&temporada=2025-26  -> filas procesadas
    GET  /api/diccionario   -> diccionario de columnas

Si se define la variable de entorno BBSTATS_TOKEN, las peticiones deben llevar la cabecera
'Authorization: Bearer <token>'. Sólo se ejecuta un trabajo de descarga a la vez.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import api

_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


def _start_job(kind: str, body: dict, config: str | None) -> tuple[int, dict]:
    with _LOCK:
        running = [j for j in _JOBS.values() if j["estado"] == "en_curso"]
        if running:
            return 409, {"error": "Ya hay una ejecución en curso", "job_id": running[0]["id"]}
        job_id = uuid.uuid4().hex[:12]
        job = {"id": job_id, "tipo": kind, "estado": "en_curso", "progreso": [], "informe": None}
        _JOBS[job_id] = job

    def work():
        fn = api.ejecutar if kind == "ejecutar" else api.reprocesar
        try:
            job["informe"] = fn(ligas=body.get("ligas") or None, temporada=body.get("temporada"),
                                config=config, progreso=job["progreso"].append)
            job["estado"] = "terminado"
        except Exception as exc:  # noqa: BLE001
            job["estado"] = "error"
            job["progreso"].append(f"ERROR: {exc}")

    threading.Thread(target=work, daemon=True).start()
    return 202, {"job_id": job_id, "estado": "en_curso"}


def make_handler(config: str | None):
    token = os.environ.get("BBSTATS_TOKEN")

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, payload) -> None:
            data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _authorized(self) -> bool:
            if not token:
                return True
            return self.headers.get("Authorization", "") == f"Bearer {token}"

        def do_OPTIONS(self):  # noqa: N802
            self._send(204, {})

        def do_GET(self):  # noqa: N802
            if not self._authorized():
                return self._send(401, {"error": "no autorizado"})
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if u.path == "/api/estado":
                return self._send(200, api.estado(q.get("temporada"), config))
            if u.path == "/api/datos":
                return self._send(200, api.datos(q.get("liga"), q.get("temporada"), config))
            if u.path == "/api/diccionario":
                return self._send(200, api.diccionario())
            if u.path.startswith("/api/trabajo/"):
                job = _JOBS.get(u.path.rsplit("/", 1)[-1])
                return self._send(200 if job else 404, job or {"error": "trabajo no encontrado"})
            return self._send(404, {"error": "ruta no encontrada"})

        def do_POST(self):  # noqa: N802
            if not self._authorized():
                return self._send(401, {"error": "no autorizado"})
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return self._send(400, {"error": "JSON inválido"})
            path = urlparse(self.path).path
            if path in ("/api/ejecutar", "/api/reprocesar"):
                code, payload = _start_job(path.rsplit("/", 1)[-1], body, config)
                return self._send(code, payload)
            return self._send(404, {"error": "ruta no encontrada"})

        def log_message(self, fmt, *args):  # silenciar log por petición
            pass

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8765, config: str | None = None) -> None:
    srv = ThreadingHTTPServer((host, port), make_handler(config))
    print(f"bbstats API escuchando en http://{host}:{port}  (Ctrl+C para parar)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
