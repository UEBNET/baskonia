"""Cliente HTTP con reintentos, back-off, pausa de cortesía por dominio y registro de peticiones."""
from __future__ import annotations

import json
import logging
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
            wait = self.delay_s - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_hit[host] = time.monotonic()

    def get(self, url: str, params: dict | None = None, headers: dict | None = None) -> requests.Response:
        self._throttle(url)
        t0 = time.monotonic()
        try:
            resp = self.session.get(url, params=params, headers=headers, timeout=self.timeout_s)
        except requests.RequestException as exc:
            self.log.append(RequestLog(url, params, None, utc_now().isoformat(),
                                       round(time.monotonic() - t0, 3), repr(exc)))
            raise FetchError(f"GET {url} falló: {exc}") from exc
        self.log.append(RequestLog(resp.url, params, resp.status_code, utc_now().isoformat(),
                                   round(time.monotonic() - t0, 3),
                                   None if resp.ok else resp.text[:300]))
        if not resp.ok:
            raise FetchError(f"GET {resp.url} -> HTTP {resp.status_code}")
        return resp

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
