"""Extractor (adaptador) por liga de la Federación Vasca: descarga y guarda el bruto SIN TOCAR.

Una liga de config/basko.json = una o varias categorías de la web (`categorias`: idCategory, estable entre
temporadas; p.ej. 46 = Primera División Masculina, 54 = Liga Vasca Junior Masculina). Recorrido por temporada:

  CategoryRegistered/getVisibleWeb/<año>/<zona>/<sexo>      categorías inscritas en la temporada (idCategoryRegistred)
  CategoryRegistered/getByIdAndCompetitions/<cr>             fases (competiciones) de la categoría
  Competition/getCompetitionGroupVisibleWeb/<cr>/            grupos de cada fase
  FCBQWeb/getAllGamesByGrupWithMatchRecords/<grupo>          calendario y resultados del grupo (jornada a jornada)
  FCBQWeb/getTeamCard/<equipo>                               plantilla con licencias, uuid de persona y cuerpo técnico
  msstats …/getJsonWithMatchStats/<universallyid>            acta digital del partido
  msstats …/getJsonWithMatchMoves/<universallyid>            jugada a jugada

El acta digital (y con ella el jugada a jugada) existe desde 2022-23; de 2018-19 a 2021-22 la web sólo publica
calendario y resultados: esos partidos se guardan igualmente (equipos, marcador, fase, grupo, fecha).

Bruto INCREMENTAL (como el resto del repositorio): cada ejecución guarda sólo los partidos nuevos (`games`) y
fichas de equipo nuevas o refrescadas (`equipos`), en paquetes de `partidos_por_paquete`; el calendario completo
va en cada paquete. RawStore.load_season() une los paquetes. Nada se sobrescribe: cada paquete lleva su fecha.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..adapters.base import BaseAdapter, NoDataYet
from ..http import FetchError, HttpClient
from .cliente import EsfClient, EsfError


def partidos_calendario(cal: dict) -> list[dict]:
    """Partidos de un calendario de grupo (respuesta original de getAllGamesByGrupWithMatchRecords)."""
    out = []
    for rd in ((cal or {}).get("rounds") or {}).values():
        for m in ((rd or {}).get("matches") or {}).values():
            if isinstance(m, dict):
                out.append(m)
    return out


def jugado(m: dict) -> bool:
    return str(m.get("localScore") or "").strip() != "" and str(m.get("visitorScore") or "").strip() != ""


def _fecha(m: dict) -> str | None:
    return str(m.get("matchDay") or "")[:10] or None


def _reciente(f: str | None, dias: int) -> bool:
    try:
        return date.fromisoformat(f) >= date.today() - timedelta(days=dias)
    except (TypeError, ValueError):
        return True


def acta_valida(doc: dict | None) -> bool:
    st = (doc or {}).get("acta") or {}
    return bool(st.get("teams"))


class EsfAdapter(BaseAdapter):
    name = "esf"
    version = "1.0"

    def __init__(self, league: str, cfg: dict, global_cfg: dict) -> None:
        super().__init__(league, cfg)
        self.g = global_cfg
        self.client: EsfClient | None = None

    @property
    def source_url(self) -> str:
        return self.g["fuente"]["pagina_publica"]

    def fetch(self, season: str, http: HttpClient, previous_payload: Any | None = None,
              progreso=lambda m: None) -> dict:
        fuente = self.g["fuente"]
        self.client = c = EsfClient(http, fuente)
        urls = c.descubrir()
        prev = previous_payload if isinstance(previous_payload, dict) else {}
        prev_games, prev_teams = prev.get("games") or {}, prev.get("equipos") or {}
        year = int(season[:4])
        cats = c.esb(f"CategoryRegistered/getVisibleWeb/{year}/{fuente['zona']}/{fuente['sexo']}") or []
        wanted = [str(x) for x in self.cfg["categorias"]]
        sel = [x for x in cats if str(x.get("idCategory")) in wanted]
        if not sel:
            raise NoDataYet(f"{self.league} {season}: la categoría {wanted} no existe en la temporada")
        categorias, competiciones, grupos, calendario = {}, {}, {}, {}
        for cat in sel:
            cr = str(cat["idCategoryRegistred"])
            categorias[cr] = cat
            competiciones[cr] = c.esb(f"CategoryRegistered/getByIdAndCompetitions/{cr}")
            gs = c.esb(f"Competition/getCompetitionGroupVisibleWeb/{cr}/") or []
            for g in gs:
                gid = str(g["idGroup"])
                grupos[gid] = g
                calendario[gid] = c.esb(f"FCBQWeb/getAllGamesByGrupWithMatchRecords/{gid}")
        todos = [m for cal in calendario.values() for m in partidos_calendario(cal)]
        if not todos:
            raise NoDataYet(f"{self.league} {season}: sin partidos en el calendario")
        progreso(f"[{self.league} {season}] {len(grupos)} grupos, {len(todos)} partidos en calendario "
                 f"({sum(jugado(m) for m in todos)} jugados)")

        # fichas de equipo: nuevas siempre; en la temporada en curso se refrescan (altas de licencia)
        actual = season == self.g.get("temporada_por_defecto")
        equipos_ids = sorted({str(m.get(k)) for m in todos for k in ("idLocalTeam", "idVisitorTeam") if m.get(k)})
        new_teams = {}
        for tid in equipos_ids:
            if tid in prev_teams and not actual:
                continue
            try:
                new_teams[tid] = c.esb(f"FCBQWeb/getTeamCard/{tid}")
            except (FetchError, EsfError) as exc:
                self.soft_fail(f"equipo {tid}: {exc}")

        dias = int(self.g.get("reintentar_sin_datos_dias", 30))
        block = int(self.g.get("partidos_por_paquete", 350))
        new: dict[str, dict] = {}
        n_new = reused = sin_acta = sin_datos = 0
        base = {"claves_incrementales": ["games", "equipos"], "urls": urls, "categorias": categorias,
                "competiciones": competiciones, "grupos": grupos, "calendario": calendario}
        for m in sorted(todos, key=lambda x: (str(x.get("matchDay")), int(x.get("idMatch") or 0))):
            mid = str(m.get("idMatch"))
            if not jugado(m):
                continue
            uid = m.get("universallyid")
            if not uid:
                sin_acta += 1          # temporada sin acta digital: el partido queda en el calendario
                continue
            old = prev_games.get(mid)
            if old and (acta_valida(old) or (old.get("sin_datos") and not _reciente(_fecha(m), dias))):
                reused += 1
                continue
            try:
                acta = c.acta(uid)
                jug = c.jugadas(uid)
            except FetchError as exc:
                self.soft_fail(f"partido {mid}: {exc}")
                continue
            doc = {"universallyid": uid, "acta": acta, "jugadas": jug}
            if not (acta or {}).get("teams"):
                doc = {"universallyid": uid, "sin_datos": True, "acta": acta, "jugadas": jug}
                sin_datos += 1
            new[mid] = doc
            n_new += 1
            if n_new % 50 == 0:
                progreso(f"[{self.league} {season}] {n_new} partidos descargados")
            if len(new) >= block:
                self.save_partial(season, {**base, "games": new, "equipos": new_teams})
                new, new_teams = {}, {}
        return {**base, "incremental": True, "games": new, "equipos": new_teams,
                "partidos_nuevos": n_new, "reutilizados": reused, "sin_acta_digital": sin_acta,
                "sin_datos": sin_datos}

    def parse(self, payload: Any, season: str):  # la construcción vive en construir.py (varias tablas)
        from .construir import construir_liga
        return construir_liga(self.league, self.cfg, self.g, season, payload)
