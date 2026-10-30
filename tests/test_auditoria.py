"""Auditoría de identidades: nombres compatibles entre formatos y detección de personas mezcladas."""
import pandas as pd

from bbfit.auditoria import auditar_roles, compatibles, fichas, latino


def test_nombres_compatibles_entre_formatos():
    assert compatibles(fichas("SIMMONS, KOBI"), fichas("Kobi Simmons"))
    assert compatibles(fichas("DJ Stewart Jr"), fichas("STEWART, DJ"))
    assert compatibles(fichas("Ludde Hakanson"), fichas("Ludvig  Hakanson"))
    assert not compatibles(fichas("AJ Lawson"), fichas("Dusan Radosavljevic"))
    assert not compatibles(fichas("Pablo Sevilla"), fichas("Kobi Simmons"))
    assert not latino("Τομά Ερτελ") and latino("Thomas Heurtel")


def test_detecta_persona_mezclada():
    r = pd.DataFrame({"liga": ["acb", "acb", "bcl", "acb"], "temporada": ["2025-26", "2026-27", "2024-25", "2026-27"],
                      "team_id": ["3", "3", "1", "3"], "persona_id": ["P1", "P1", "P2", "P2"],
                      "nombre": ["Kobi Simmons", "SIMMONS, KOBI", "Dusan Radosavljevic", "AJ Lawson"]})
    a = auditar_roles(r)
    assert a["mezcladas"] == 1 and a["ejemplos"][0]["persona_id"] == "P2"
