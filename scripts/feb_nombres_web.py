"""Nombres completos de la web de la FEB para los jugadores que en nuestras fuentes sólo tienen inicial.

Las actas FEB dan «J. BOCCA»; la página del equipo en baloncestoenvivo.feb.es/equipo/<id equipo> da el nombre completo
con el mismo id de jugador (c=<id>) en dos sitios: la plantilla final («JUAN BOCCA …») y las estadísticas acumuladas
(«BOCCA …, JUAN»), que incluyen a quien jugó y se fue a mitad de temporada. Para cada equipo-temporada en el que jugó
alguno de esos jugadores se descargan las dos una vez (pausa entre peticiones).

    python scripts/feb_nombres_web.py   →  data/processed/feb_nombres_web.csv (player_id, nombre, team_id, temporada)

Los usa bbmodel/nombres.py como una variante más de la persona. La plantilla de la web es la del final de la
temporada: quien se fue a mitad de temporada puede no estar.
"""
from __future__ import annotations

import html
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
SALIDA = RAIZ / "data" / "processed" / "feb_nombres_web.csv"
URL = "https://baloncestoenvivo.feb.es/equipo/{}"
PATRON = re.compile(r"c=(\d+)'>([^<]+)<")             # plantilla
PATRON_ACUM = re.compile(r'c=(\d+)">([^<]+)<')          # estadísticas acumuladas (enlaces con comillas dobles)
BOTON_ACUM = "_ctl0$MainContentPlaceHolderMaster$estadAcumLinkButton"
PAUSA = 0.7


def objetivos() -> pd.DataFrame:
    """Equipo-temporadas de los jugadores FEB cuyo nombre canónico es sólo inicial."""
    n = pd.read_csv(RAIZ / "data" / "processed" / "nombres_canonicos.csv", dtype=str)
    ini = n[n["nombre"].str.match(r"^[A-Z][a-z]?\.? ", na=False) & n["fuente_liga"].isin(["feb1", "feb2", "feb3"])]
    ids = set(ini["fuente_id"])
    filas = []
    for f in sorted((RAIZ / "data" / "processed").glob("20*/ligas/feb*.csv")):
        d = pd.read_csv(f, dtype=str, usecols=["player_id", "team_id", "temporada", "fase"], low_memory=False)
        d = d[(d["fase"] == "total") & d["player_id"].isin(ids)]
        filas.append(d[["player_id", "team_id", "temporada"]])
    return pd.concat(filas).dropna().drop_duplicates()


def main() -> None:
    obj = objetivos()
    hechos = pd.read_csv(SALIDA, dtype=str) if SALIDA.exists() and "--rehacer" not in sys.argv else pd.DataFrame(
        columns=["player_id", "nombre", "team_id", "temporada"])
    vistos = set(hechos["team_id"])
    equipos = obj.drop_duplicates("team_id")
    equipos = equipos[~equipos["team_id"].isin(vistos)]
    print(f"{obj['player_id'].nunique()} jugadores con inicial · {len(equipos)} plantillas por descargar", flush=True)
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (cerno-analytics; nombres de plantilla)"
    nuevas = []
    for k, (tid, temp) in enumerate(zip(equipos["team_id"], equipos["temporada"]), 1):
        try:
            r = s.get(URL.format(tid), timeout=30)
            filas = PATRON.findall(r.text) if r.status_code == 200 else []
            if r.status_code == 200 and BOTON_ACUM.replace("$", "_") in r.text:
                from bbstats.adapters.feb import form_fields
                time.sleep(PAUSA)
                a = s.post(URL.format(tid), data={**form_fields(r.text), "__EVENTTARGET": BOTON_ACUM,
                                                  "__EVENTARGUMENT": ""}, timeout=30)
                if a.status_code == 200:
                    filas += PATRON_ACUM.findall(html.unescape(a.text))
        except requests.RequestException as e:          # se reintenta en la siguiente ejecución
            print(f"  {tid}: {e}", flush=True)
            filas = None
        if filas is not None:
            nuevas += [{"player_id": c, "nombre": html.unescape(nm).strip(), "team_id": tid, "temporada": temp}
                       for c, nm in filas]
            if not filas:
                nuevas.append({"player_id": "", "nombre": "", "team_id": tid, "temporada": temp})
        if k % 50 == 0 or k == len(equipos):
            hechos = pd.concat([hechos, pd.DataFrame(nuevas)], ignore_index=True)
            hechos.to_csv(SALIDA, index=False)
            nuevas = []
            print(f"  {k}/{len(equipos)} plantillas", flush=True)
        time.sleep(PAUSA)
    h = hechos[hechos["player_id"].fillna("") != ""]
    cub = obj["player_id"].isin(h["player_id"]).groupby(obj["player_id"]).any()
    print(f"jugadores con inicial que aparecen en alguna plantilla: {int(cub.sum())} de {len(cub)}", flush=True)


if __name__ == "__main__":
    main()
