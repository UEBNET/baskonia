"""Cliente HTTP con reintentos, back-off, pausa de cortesía por dominio y registro de peticiones."""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .utils import utc_now

log = logging.getLogger(__name__)

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


class FetchError(RuntimeError):
    pass


class _CurlResponse:
    """Respuesta mínima compatible con requests.Response para el transporte curl."""

    def __init__(self, url: str, status: int, content: bytes) -> None:
        self.url, self.status_code, self.content = url, status, content
        self.ok = 200 <= status < 400
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"

    @property
    def text(self) -> str:
        return self.content.decode(self.encoding or "utf-8", errors="replace")

    def json(self):
        return json.loads(self.content)


@dataclass
class RequestLog:
    url: str
    params: dict | None
    status: int | None
    fetched_at: str
    elapsed_s: float
    error: str | None = None


@dataclass
class HttpClient:
    """Cliente compartido por los adaptadores.

    - `delay_s`: pausa mínima entre peticiones al mismo dominio (cortesía con las webs).
    - `timeout_s`: timeout de cada petición.
    - `log`: lista de peticiones realizadas (se guarda en el JSON bruto para trazabilidad).
    """
    delay_s: float = 1.0
    domain_delays: dict = field(default_factory=dict)  # p.ej. {"www.basketball-reference.com": 3.5}
    curl_domains: tuple = ()  # dominios que rechazan la huella TLS de requests: se usa el binario curl
    timeout_s: float = 30.0
    retries: int = 3
    user_agent: str = DEFAULT_UA
    log: list[RequestLog] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.session = requests.Session()
        retry = Retry(total=self.retries, backoff_factor=1.5,
                      status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=("GET", "POST"), raise_on_status=False)
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({"User-Agent": self.user_agent,
                                     "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"})
        self._last_hit: dict[str, float] = {}

    def _throttle(self, url: str) -> None:
        host = urlparse(url).netloc
        last = self._last_hit.get(host)
        if last is not None:
            wait = self.domain_delays.get(host, self.delay_s) - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_hit[host] = time.monotonic()

    def get(self, url: str, params: dict | None = None, headers: dict | None = None,
            ok_status: tuple = ()) -> requests.Response:
        return self.request("GET", url, params=params, headers=headers, ok_status=ok_status)

    def request(self, method: str, url: str, params: dict | None = None, headers: dict | None = None,
                data: dict | None = None, json_body: Any = None, ok_status: tuple = ()) -> requests.Response:
        """`ok_status`: códigos no-2xx que se devuelven sin lanzar error (p.ej. 404 esperados)."""
        self._throttle(url)
        t0 = time.monotonic()
        if urlparse(url).netloc in self.curl_domains and method == "GET" and shutil.which("curl"):
            resp = self._curl_get(url, params, headers)
            self.log.append(RequestLog(resp.url, params, resp.status_code, utc_now().isoformat(),
                                       round(time.monotonic() - t0, 3), None if resp.ok else resp.text[:300]))
            if not resp.ok and resp.status_code not in ok_status:
                raise FetchError(f"{method} {resp.url} -> HTTP {resp.status_code}")
            return resp
        try:
            resp = self.session.request(method, url, params=params, headers=headers, data=data, json=json_body,
                                        timeout=self.timeout_s)
        except requests.RequestException as exc:
            self.log.append(RequestLog(url, params, None, utc_now().isoformat(),
                                       round(time.monotonic() - t0, 3), repr(exc)))
            raise FetchError(f"{method} {url} falló: {exc}") from exc
        self.log.append(RequestLog(resp.url, params, resp.status_code, utc_now().isoformat(),
                                   round(time.monotonic() - t0, 3),
                                   None if resp.ok else resp.text[:300]))
        if not resp.ok and resp.status_code not in ok_status:
            raise FetchError(f"{method} {resp.url} -> HTTP {resp.status_code}")
        return resp

    def _curl_get(self, url: str, params: dict | None, headers: dict | None) -> "_CurlResponse":
        req = requests.Request("GET", url, params=params).prepare()
        cmd = ["curl", "-sS", "-L", "--compressed", "-m", str(int(self.timeout_s)), "-A", self.user_agent,
               "-w", "\n%{http_code}"]
        for k, v in (headers or {}).items():
            cmd += ["-H", f"{k}: {v}"]
        cmd.append(req.url)
        for attempt in range(self.retries + 1):
            proc = subprocess.run(cmd, capture_output=True, timeout=self.timeout_s + 10)
            body, _, code = proc.stdout.rpartition(b"\n")
            status = int(code or 0) if code.strip().isdigit() else 0
            if status not in (0, 429, 500, 502, 503, 504) or attempt == self.retries:
                break
            time.sleep(1.5 * 2 ** attempt)
        if status == 0:
            raise FetchError(f"GET {url} (curl) falló: {proc.stderr.decode(errors='replace')[:200]}")
        return _CurlResponse(req.url, status, body)

    def post_json(self, url: str, data: dict | None = None, json_body: Any = None,
                  headers: dict | None = None) -> Any:
        resp = self.request("POST", url, data=data, json_body=json_body, headers=headers)
        try:
            return resp.json()
        except ValueError as exc:
            raise FetchError(f"Respuesta no JSON en {resp.url}: {resp.text[:200]!r}") from exc

    def get_json(self, url: str, params: dict | None = None, headers: dict | None = None) -> Any:
        resp = self.get(url, params=params, headers=headers)
        try:
            return resp.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise FetchError(f"Respuesta no JSON en {resp.url}: {resp.text[:200]!r}") from exc

    def get_text(self, url: str, params: dict | None = None, headers: dict | None = None) -> str:
        resp = self.get(url, params=params, headers=headers)
        if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding
        return resp.text

    def request_log(self) -> list[dict]:
        return [r.__dict__ for r in self.log]
