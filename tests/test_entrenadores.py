"""Entrenadores: normalización de nombres, alias, imputación de huecos y tramos (datos sintéticos)."""
from __future__ import annotations

import json

import pandas as pd

from bbstats.entrenadores import (Alias, construir_tramos, extractor_fiba_livestats, imputar, nombre_visible,
                                  parse_bref_coaches, slug)


def test_nombres_y_slug():
    assert nombre_visible("IVANOVIC, DUSKO") == "Dusko Ivanovic"
    assert nombre_visible("Dusko Ivanović") == "Dusko Ivanović"
    assert slug("IVANOVIC, DUSKO") == slug("Dusko Ivanović") == "dusko-ivanovic"
    assert slug("Đorđević, Aleksandar") == "aleksandar-djordjevic"
    assert nombre_visible("PARKER, TJ") == "TJ Parker"
    assert nombre_visible("O'SHEA, CHRIS") == "Chris O'Shea"
    assert nombre_visible("-") is None and nombre_visible("  ") is None and nombre_visible(None) is None


def test_alias(tmp_path):
    p = tmp_path / "alias.json"
    p.write_text(json.dumps({"alias": {"aito-garcia-reneses": "alejandro-garcia-reneses",
                                       "ramon-diaz-sanchez": "ramon-diaz"}}), encoding="utf-8")
    a = Alias.load(p)
    assert a.id_de("GARCIA RENESES, AITO") == "alejandro-garcia-reneses"
    assert a.id_de("Ramón Díaz Sánchez") == a.id_de("Ramon Diaz") == "ramon-diaz"


def _partidos(seq):
    """seq: lista de (entrenador | None, resultado) para un único equipo, en orden de fecha."""
    rows = []
    for k, (c, r) in enumerate(seq):
        rows.append({"liga": "x", "temporada": "2025-26", "game_id": f"g{k:02d}", "fecha": f"2025-10-{k + 1:02d}",
                     "fase": "playoffs" if k == len(seq) - 1 else "regular", "equipo_id": "T1", "equipo": "Equipo",
                     "resultado": r, "entrenador": c, "entrenador_id": slug(c), "entrenador_id_fuente": None,
                     "fuente": "test" if c else None, "metodo": "partido" if c else None, "imputado": 0})
    return pd.DataFrame(rows)


def test_imputar_y_tramos():
    seq = [(None, "V"), ("Ana Uno", "V"), (None, "D"), ("Ana Uno", "D"), ("Bea Dos", "V"), (None, "D"),
           ("Carla Tres", "V"), ("Carla Tres", "V"), ("Bea Dos", "D"), ("Ana Uno", "V")]
    df = imputar(_partidos(seq))
    ids = list(df["entrenador_id"])
    assert ids[0] == "ana-uno" and df.loc[0, "metodo"] == "tramo_borde"       # borde inicial
    assert ids[2] == "ana-uno" and df.loc[2, "metodo"] == "tramo"             # entre dos del mismo
    assert pd.isna(ids[5]) or ids[5] is None                                  # entre dos distintos: vacío
    assert int(df["imputado"].sum()) == 2
    t = construir_tramos(df).set_index("entrenador_id")
    assert list(t.sort_values("orden").index) == ["ana-uno", "bea-dos", "carla-tres"]
    assert t.loc["ana-uno", "n_partidos"] == 5 and t.loc["ana-uno", "n_tramos_consecutivos"] == 2
    assert t.loc["ana-uno", "n_imputados"] == 2 and t.loc["ana-uno", "n_playoffs"] == 1
    assert (t.loc["ana-uno", "victorias"], t.loc["ana-uno", "derrotas"]) == (3, 2)
    assert t.loc["carla-tres", "interino"] == 1                               # entre dos tramos de Bea
    assert t.loc["ana-uno", "interino"] == 0
    assert t.loc["ana-uno", "partidos_ids"].split(";")[:2] == ["g00", "g01"]
    assert set(t["entrenadores_equipo"]) == {3}


def test_bref_y_fiba():
    html = ('<p><strong>Coach:</strong> <a href="/coaches/jenkita01c.html">Taylor Jenkins</a> (44-29), '
            '<a href="/coaches/iisaltu01c.html">Tuomas Iisalo</a> (4-5)</p>')
    c = parse_bref_coaches(html)
    assert [(x["id"], x["v"], x["d"]) for x in c] == [("jenkita01c", 44, 29), ("iisaltu01c", 4, 5)]
    doc = {"tm": {"1": {"name": "Local", "code": "LOC", "full_score": 80, "coach": "J. Pérez",
                        "coachDetails": {"firstName": "Juan", "familyName": "Pérez"}},
                  "2": {"name": "Visitante", "code": "VIS", "score": 75, "coach": "Ana Ruiz"}}}
    s = extractor_fiba_livestats(doc)
    assert [x["entrenador"] for x in s] == ["Juan Pérez", "Ana Ruiz"]
    assert [x["puntos"] for x in s] == [80.0, 75.0]
