"""Fase 5 (bbfit/entropia.py) con datos sintéticos."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bbfit import datos as D
from bbfit import entropia as E
from bbfit.config import cargar


@pytest.fixture(scope="module")
def cfg():
    return cargar("entropia")


def test_entropia_bits_extremos():
    assert E.entropia_bits(np.array([1.0, 0, 0])) == pytest.approx(0)
    assert E.entropia_bits(np.full(4, 0.25)) == pytest.approx(2)


def test_dirichlet_intervalo_y_contraccion():
    rng = np.random.default_rng(0)
    C = np.array([[50, 50, 50, 50], [2, 0, 0, 0], [200, 0, 0, 0]], float)
    r = E.entropia_dirichlet(C, np.full(4, 0.25), alpha=4, muestras=500, rng=rng)
    assert r.loc[0, "H_media"] == pytest.approx(2, abs=0.05)
    assert (r["H_lo"] <= r["H_media"]).all() and (r["H_media"] <= r["H_hi"]).all()
    # muestra pequeña: el prior la aleja de 0 y el intervalo es ancho; muestra grande concentrada: cerca de 0
    assert r.loc[1, "H_hi"] - r.loc[1, "H_lo"] > r.loc[2, "H_hi"] - r.loc[2, "H_lo"]
    assert r.loc[2, "H_media"] < r.loc[1, "H_media"]
    assert r.loc[1, "H_bruta"] == 0


def test_dirichlet_categoria_no_observable():
    rng = np.random.default_rng(1)
    r = E.entropia_dirichlet(np.array([[10, 10, np.nan]]), np.full(3, 1 / 3), alpha=1, muestras=300, rng=rng)
    assert r.loc[0, "K"] == 2 and r.loc[0, "H_media"] <= 1.0 + 1e-9


def test_volatilidad_ordena_jugadores(cfg):
    """Dos jugadores con la misma media y ruido intrínseco distinto: σ̂ ordena bien y se descuenta la exposición."""
    rng = np.random.default_rng(2)
    filas = []
    sig = {"estable": 10.0, "volatil": 40.0}
    for g in range(60):
        for pid, s in sig.items():
            for team, opp in (("A", "B"),) if g % 2 == 0 else (("A", "C"),):
                poss = rng.integers(15, 40)
                y = 100 + s * np.sqrt(30 / poss) * rng.standard_normal()
                filas.append({"liga": "sint", "temporada": "2025-26", "game_id": str(g), "team_id": team,
                              "opp_id": opp, "player_id": pid, "jugo": True, "poss_on": poss, "sec": 60 * poss,
                              "pts": y * poss / 100, "ast": 0.0})
        for k in range(6):          # compañeros de relleno con ruido medio
            poss = 30
            filas.append({"liga": "sint", "temporada": "2025-26", "game_id": str(g), "team_id": "A",
                          "opp_id": "B" if g % 2 == 0 else "C", "player_id": f"r{k}", "jugo": True, "poss_on": poss,
                          "sec": 1500, "pts": (100 + 20 * rng.standard_normal()) * poss / 100, "ast": 0.0})
    pj = pd.DataFrame(filas)
    pos3 = pd.Series({("sint", p): "E" for p in pj["player_id"].unique()})
    vol, coefs = E.volatilidad(pj, pos3, cfg)
    v = vol.set_index("player_id")
    assert v.loc["volatil", "sigma"] > 2 * v.loc["estable", "sigma"]
    assert v.loc["estable", "sigma_bruta"] == pytest.approx(10, rel=0.35)
    assert (v["sigma_lo"] <= v["sigma"]).all() and (v["sigma"] <= v["sigma_hi"]).all()


def test_equipos_hhi_y_red(monkeypatch, cfg):
    pj = pd.DataFrame({"liga": "sint", "temporada": "2025-26", "team_id": "A", "player_id": list("abcde"),
                       "jugo": True, "sec": [600.0] * 5, "fga": [10, 10, 10, 10, 10], "fta": 0.0, "coef_tl": 0.44,
                       "game_id": "1"})
    tr = pd.DataFrame({"liga": "sint", "temporada": "2025-26", "team_id": "A", "player_id": list("abcde"),
                       "min_total": 10.0, "H_rol": 0.5})
    ast = pd.DataFrame({"fase": "total", "team_id": "A", "pasador_id": ["a", "b"], "receptor_id": ["b", "a"],
                        "ast": [5, 5]})
    monkeypatch.setattr(D, "quintetos_fichero", lambda liga, temp, nombre: ast.copy())
    eq = E.equipos(pj, tr, cfg).iloc[0]
    assert eq["hhi_uso"] == pytest.approx(0.2) and eq["H_uso"] == pytest.approx(np.log2(5))
    assert eq["n_efectivo_tiros"] == pytest.approx(5)
    assert eq["H_red_pases"] == pytest.approx(1.0) and eq["nodos_red"] == 2
    assert eq["H_rol_medio_minutos"] == pytest.approx(0.5)


def test_estilo_liga_basico_y_categorias_faltantes(cfg):
    acc = pd.DataFrame({"liga": "sint", "temporada": "2025-26", "team_id": "A", "player_id": ["a", "b"],
                        "T2": [100, 5], "T3": [0, 5], "visitas_tl": [10, 1], "ast": [0, 3], "tov": [5, 1],
                        "pfd": [np.nan, np.nan], "oreb": [20, 0], "nivel_categorias": "basico",
                        "origen_zonas": "sin_coordenadas"})
    out = E.estilo_liga(acc, cfg, np.random.default_rng(0)).set_index("player_id")
    assert (out["K_basico"] == 6).all()                      # pfd no publicada → fuera
    assert out.loc["a", "categorias_faltantes"] == "pfd"
    assert out.loc["b", "H_estilo_basico"] > out.loc["a", "H_estilo_basico"]
    assert out.loc["a", "H_estilo"] == out.loc["a", "H_estilo_basico"]
