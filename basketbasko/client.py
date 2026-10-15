"""Cliente autenticado de la intranet: login con usuario/contraseña, JWT y re-login automático."""
from __future__ import annotations

import logging
import os
from typing import Any

from bbstats.http import FetchError, HttpClient

log = logging.getLogger(__name__)


class ApiError(RuntimeError):
    """La API respondió, pero con un error de negocio ({"result": "ERROR", ...}) o un código no esperado."""


class AuthError(ApiError):
    pass


class BasketBaskoClient:
    """Envuelve las dos APIs de la intranet.

    El login (`POST <esb>/public/club/login` con `{username, password}`) devuelve el JWT en la cabecera
    `Authorization` de la respuesta; la web lo reenvía tal cual en la cabecera `Authorization` de cada
    petición posterior (ESB y estadísticas). Si una petición devuelve 401/403 se repite el login una vez.
    """

    def __init__(self, cfg: dict, usuario: str | None = None, password: str | None = None,
                 http: HttpClient | None = None) -> None:
        self.cfg = cfg
        self.usuario = usuario or os.environ.get("BB_USUARIO", "")
        self.password = password or os.environ.get("BB_PASSWORD", "")
        self.http = http or HttpClient(delay_s=float(cfg.get("pausa_s", 1.5)), timeout_s=40, retries=2)
        origen = cfg.get("origen_web", "https://clubes.basketbasko.com")
        self.http.session.headers.update({"Origin": origen, "Referer": origen + "/",
                                          "Accept": "application/json, text/plain, */*"})
        self.token: str | None = None
        self.peticiones = 0
        self.max_peticiones = int(cfg.get("max_peticiones", 1500))

    # ------------------------------------------------------------------ autenticación
    def login(self) -> dict:
        if not self.usuario or not self.password:
            raise AuthError("Faltan credenciales: define las variables de entorno BB_USUARIO y BB_PASSWORD")
        self.http.session.headers.pop("Authorization", None)
        resp = self.http.request("POST", f"{self.cfg['url_esb']}/public/club/login",
                                 json_body={"username": self.usuario, "password": self.password},
                                 ok_status=(400, 401, 403))
        self.peticiones += 1
        body = _json(resp)
        token = resp.headers.get("Authorization") or resp.headers.get("authorization")
        if not resp.ok or not token or _is_error(body):
            raise AuthError(f"Login rechazado (HTTP {resp.status_code}): {_error_msg(body)}")
        self.token = token
        self.http.session.headers["Authorization"] = token
        log.info("Login correcto en la intranet")
        return body if isinstance(body, dict) else {}

    # ------------------------------------------------------------------ peticiones
    def esb(self, path: str) -> Any:
        return self._get(f"{self.cfg['url_esb']}{path}")

    def stats(self, path: str) -> Any:
        return self._get(f"{self.cfg['url_stats']}/{self.cfg.get('federacion', 'esf')}{path}")

    def _get(self, url: str, _retry: bool = True) -> Any:
        if self.token is None:
            self.login()
        if self.peticiones >= self.max_peticiones:
            raise ApiError(f"Límite de {self.max_peticiones} peticiones alcanzado (max_peticiones)")
        self.peticiones += 1
        resp = self.http.get(url, ok_status=(401, 403, 404))
        body = _json(resp)
        if resp.status_code in (401, 403) or _is_auth_error(body):
            if _retry:
                log.info("Token caducado o rechazado; repitiendo login")
                self.login()
                return self._get(url, _retry=False)
            raise AuthError(f"Sin permiso para {url} (HTTP {resp.status_code}): {_error_msg(body)}")
        if resp.status_code == 404:
            raise ApiError(f"No encontrado: {url}")
        if _is_error(body):
            raise ApiError(f"{url}: {_error_msg(body)}")
        # Algunas versiones envían un token renovado en cada respuesta
        nuevo = resp.headers.get("Authorization") if hasattr(resp, "headers") else None
        if nuevo and nuevo != self.token:
            self.token = nuevo
            self.http.session.headers["Authorization"] = nuevo
        return body


def _json(resp) -> Any:
    try:
        return resp.json()
    except ValueError as exc:
        raise FetchError(f"Respuesta no JSON en {resp.url}: {resp.text[:200]!r}") from exc


def _is_error(body: Any) -> bool:
    return isinstance(body, dict) and str(body.get("result", "")).upper() == "ERROR"


def _error_msg(body: Any) -> str:
    if isinstance(body, dict):
        return str(body.get("message") or body.get("errorCode") or body)[:200]
    return str(body)[:200]


def _is_auth_error(body: Any) -> bool:
    # La ESB responde 200 con {"result":"ERROR","message":"ERRORCODEx0004"} cuando falta o caduca el token
    return _is_error(body) and str(body.get("message", "")).upper() == "ERRORCODEX0004"
