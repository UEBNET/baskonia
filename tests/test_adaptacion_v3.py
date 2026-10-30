"""Adaptación v3: ADAPT% ascendente hacia el nivel adaptado (D ≤ 0) y coherente con el motor del simulador."""
import numpy as np
import pandas as pd

from bbfit import adaptacion_v3 as A3
from bbfit.simulador import factores_adaptacion


def _curvas():
    filas = []
    for serie in ("prod_p100", "usg_tiro"):
        Dg = -0.04 if serie == "prod_p100" else 0.01           # en el uso los datos no muestran hueco (D > 0)
        filas.append({"serie": serie, "poblacion": "traspasos_bruto", "perfil": "global=global", "n_jugadores": 500,
                      "D": Dg, "D_lo": Dg - 0.03, "D_hi": Dg + 0.03, "kappa": 2.0, "kappa_lo": 1.0, "kappa_hi": 6.0})
        for g, D in (("a", -0.10), ("b", 0.06)):
            filas.append({"serie": serie, "poblacion": "traspasos_bruto", "perfil": f"grupo_nacionalidad={g}",
                          "n_jugadores": 60, "D": D, "D_lo": D - 0.05, "D_hi": D + 0.05, "kappa": 5.0, "kappa_lo": 1.0,
                          "kappa_hi": 30.0})
    filas.append({"serie": "prod_p100", "poblacion": "traspasos_neto", "perfil": "global=global", "n_jugadores": 500,
                  "D": 0.05, "D_lo": 0, "D_hi": 0.1, "kappa": 300, "kappa_lo": 100, "kappa_hi": 500})
    return pd.DataFrame(filas)


def test_d_nunca_positivo_y_contraccion():
    cv = A3.curvas_ascendentes(_curvas())
    assert (cv["D"] <= 0).all()
    a = cv[(cv.serie == "prod_p100") & (cv.grupo == "a")].iloc[0]
    assert -0.10 < a["D"] < -0.04                               # contraído hacia el global
    assert cv[(cv.serie == "usg_tiro") & (cv.grupo == "global")].iloc[0]["acotado"]


def test_curva_del_motor_es_ascendente_y_acaba_en_100():
    pr = {"delta_temporada_media": -0.05 * A3.wbar(2.0, 34), "delta_temporada_sd": 0.0,
          "D_forma_media": -0.05, "kappa_forma_media": 2.0}
    f = factores_adaptacion(pr, G=34, N=10, contraccion=1.0, rng=np.random.default_rng(0), n_sim=5)
    c = f["curva"][0]
    assert np.all(np.diff(c) >= -1e-12)                         # ascendente
    assert abs(c[0] - 0.95) < 1e-9 and abs(c[-1] - 1.0) < 1e-6   # 95 % en el primer partido → 100 %
    assert np.all(c <= 1 + 1e-12)
    assert abs(f["temporada"][0] - c.mean()) < 1e-9             # ADAPT% de la temporada = media de la curva


def test_tabla_priors_forma_v3():
    cv = A3.curvas_ascendentes(_curvas())
    v2 = pd.DataFrame({"nivel": ["global", "celda"], "liga_origen": ["*", "acb"], "liga_destino": ["*", "feb1"],
                       "grupo_nacionalidad": ["*", "a"], "pos3": ["*", "E"], "escalon_destino": ["*", "feb1"],
                       "metrica": ["L_rel", "L_rel"], "serie_curva": ["prod_p100", "prod_p100"],
                       "grupo_curva": ["global", "a"]})
    t = A3.tabla_priors(v2, cv, {"defecto": 34, "feb1": 32})
    assert (t["D_forma_media"] <= 0).all() and (t["delta_temporada_media"] <= 0).all() and (t["delta_media"] <= 0).all()
    assert t.loc[1, "partidos_1a_temporada"] == 32


def test_produccion_sin_doble_conteo():
    """Sólo L_rel (la ADAPT% mostrada) lleva el factor de temporada: la producción y L ya salen de la v3.1."""
    cv = A3.curvas_ascendentes(_curvas())
    v2 = pd.DataFrame({"nivel": ["global"] * 3, "liga_origen": ["*"] * 3, "liga_destino": ["*"] * 3,
                       "grupo_nacionalidad": ["*"] * 3, "pos3": ["*"] * 3, "escalon_destino": ["*"] * 3,
                       "metrica": ["L_rel", "pts_p100", "L"], "serie_curva": ["prod_p100"] * 3,
                       "grupo_curva": ["global"] * 3})
    t = A3.tabla_priors(v2, cv, {"defecto": 34})
    assert t.loc[0, "delta_temporada_media"] < 0
    assert (t.loc[1:, "delta_temporada_media"] == 0).all() and (t.loc[1:, "delta_temporada_sd"] == 0).all()
    f = factores_adaptacion(t.iloc[1].to_dict(), G=34, N=10, contraccion=1.0, rng=np.random.default_rng(0), n_sim=3)
    assert np.allclose(f["temporada"], 1.0)                     # producción de temporada = la de la v3.1


def test_intervalo_de_la_adapt_no_pasa_de_100():
    cv = A3.curvas_ascendentes(_curvas())
    v2 = pd.DataFrame({"nivel": ["global"], "liga_origen": ["*"], "liga_destino": ["*"], "grupo_nacionalidad": ["*"],
                       "pos3": ["*"], "escalon_destino": ["*"], "metrica": ["L_rel"], "serie_curva": ["prod_p100"],
                       "grupo_curva": ["global"]})
    t = A3.tabla_priors(v2, cv, {"defecto": 34})
    f = factores_adaptacion(t.iloc[0].to_dict(), G=34, N=10, contraccion=1.0, rng=np.random.default_rng(1), n_sim=20000)
    assert np.quantile(f["temporada"], 0.95) <= 1.0 + 1e-3
