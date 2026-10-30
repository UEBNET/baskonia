"""Skill .claude/skills/actualizar-temporada: lectura de fechas y control de incidencias."""
import importlib.util
from datetime import date
from pathlib import Path

RUTA = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "actualizar-temporada" / "actualizar_delta.py"
spec = importlib.util.spec_from_file_location("actualizar_delta", RUTA)
delta = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delta)


def test_fecha_iso_y_recortada():
    assert delta.fecha_partido("2026-10-14", "2026-27") == date(2026, 10, 14)
    assert delta.fecha_partido("Fri, 02 Oc", "2026-27") == date(2026, 10, 2)
    assert delta.fecha_partido("Sun, 10 Ja", "2026-27") == date(2027, 1, 10)
    # meses ambiguos: decide el día de la semana (7-3-2027 es domingo; 7-5-2027, viernes)
    assert delta.fecha_partido("Sun, 07 Ma", "2026-27") == date(2027, 3, 7)
    assert delta.fecha_partido("Fri, 07 Ma", "2026-27") == date(2027, 5, 7)
    assert delta.fecha_partido(None, "2026-27") is None
    assert delta.fecha_partido("sin fecha", "2026-27") is None


def test_incidencias():
    hoy = date(2026, 10, 29)
    ok = {"partidos": 30, "ultima_fecha": "2026-10-27", "columnas_ok": True}
    assert delta.incidencias("acb", {"partidos": 27}, ok, {"estado": "ok"}, hoy) == []
    assert any("SIN PARTIDOS" in i for i in delta.incidencias("nba", {}, {"partidos": 0}, None, hoy))
    assert "normal" in delta.incidencias("gleague", {}, {"partidos": 0}, None, hoy)[0]
    atrasada = {**ok, "ultima_fecha": "2026-10-14"}
    assert any("días" in i for i in delta.incidencias("acb", {}, atrasada, None, hoy))
    assert any("menos partidos" in i for i in delta.incidencias("acb", {"partidos": 40}, ok, None, hoy))
