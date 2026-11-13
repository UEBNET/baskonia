"""Cliente de la API pública que usa basketbasko.com para «Resultados - Federación Vasca».

La web es un WordPress con el plugin de Optimal Way Consulting: el HTML de la página pública declara en
`owbasketSettings` las URL de dos servicios que el widget consulta desde el navegador de cualquier visitante:

  ESB      https://esb.optimalwayconsulting.com/esf/1/<clave pública>/...   calendario, grupos, equipos
           (la respuesta es el JSON en base64: {"result","errorCode","message","messageData"})
  msstats  https://msstats.optimalwayconsulting.com/v1/esf/...              acta digital y jugada a jugada

Las URL se leen de la página en cada ejecución (si la web rota la clave, el extractor la sigue); si la página
no responde se usan las de reserva de config/basko.json. Uso autorizado por el propietario del proyecto.
"""
from __future__ import annotations

import base64
import json
import re
from typing import Any

from ..http import FetchError, HttpClient

_HEAD = {"Origin": "https://basketbasko.com", "Referer": "https://basketbasko.com/", "Accept": "application/json"}


class EsfError(RuntimeError):
    pass


def _decode(text: str) -> Any:
    try:
        doc = json.loads(text)
    except ValueError:
        doc = text
    if isinstance(doc, str):
        doc = json.loads(base64.b64decode(doc).decode("utf-8"))
    return doc


def urls_de_pagina(html: str) -> dict:
    """{"esb": url, "msstats": url, "fede": "esf"} declaradas en owbasketSettings/owbasket del HTML público."""
    out = {}
    for k in ("esb", "msstats", "fede"):
        m = re.search(r'"%s":\{"url":"([^"]*)"' % k, html or "")
        if m and m.group(1):
            out[k] = m.group(1).replace("\\/", "/")
    return out


class EsfClient:
    def __init__(self, http: HttpClient, fuente: dict) -> None:
        self.http = http
        self.fuente = fuente
        self.esb_url = fuente.get("esb_url_reserva")
        self.ms_url = fuente.get("msstats_url_reserva")
        self.fede = fuente.get("fede", "esf")
        self.origen_urls = "reserva (config/basko.json)"

    def descubrir(self) -> dict:
        try:
            html = self.http.get(self.fuente["pagina_publica"], headers={"Accept": "text/html"}).text
            u = urls_de_pagina(html)
            if u.get("esb"):
                self.esb_url, self.origen_urls = u["esb"], "página pública"
            if u.get("msstats"):
                self.ms_url = u["msstats"]
            if u.get("fede"):
                self.fede = u["fede"]
        except FetchError:
            pass
        return {"esb": self.esb_url, "msstats": self.ms_url, "fede": self.fede, "origen": self.origen_urls}

    # ------------------------------------------------------------------ ESB
    def esb(self, path: str, vacio_si_no_existe: bool = True) -> Any:
        resp = self.http.get(f"{self.esb_url}/{path}", headers=_HEAD)
        doc = _decode(resp.text)
        if isinstance(doc, dict) and doc.get("result") == "ERROR":
            if vacio_si_no_existe and str(doc.get("errorCode")) in ("11",):
                return None
            raise EsfError(f"ESB {path}: {doc.get('errorCode')} {doc.get('message')}")
        return doc.get("messageData") if isinstance(doc, dict) and "messageData" in doc else doc

    # ------------------------------------------------------------------ msstats
    def acta(self, uid: str) -> dict:
        """Acta digital del partido (boxscore por jugador y periodo, entradas/salidas, coordenadas de tiro)."""
        return self._ms(f"{self.fede}/getJsonWithMatchStats/{uid}?currentSeason=true")

    def jugadas(self, uid: str) -> list:
        """Jugada a jugada del partido (cronología con reloj, actor, tipo de acción y marcador)."""
        out = self._ms(f"{self.fede}/getJsonWithMatchMoves/{uid}?currentSeason=true")
        return out if isinstance(out, list) else []

    def _ms(self, path: str) -> Any:
        resp = self.http.get(f"{self.ms_url}/{path}", headers=_HEAD, ok_status=(400, 404))
        if resp.status_code != 200 or not resp.text.strip():
            return {}
        try:
            return resp.json()
        except ValueError:
            return {}
